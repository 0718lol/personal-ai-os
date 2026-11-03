"""M1 检索层:三路召回 + RRF 融合 + 问答置信度门控。

针对 M0 基线缺陷 D1/D2:
- D1(中文检索失效):FTS5 unicode61 把连续中文当单 token。这里增加一路
  「中文双字(bigram)FTS」腿,把查询与文档都切成滑动双字后匹配;
  另加一路纯 stdlib 的字符 n-gram 哈希嵌入向量腿(无第三方依赖、离线可用)。
- D2(无答案防护弱):confidence() 只在 /api/chat 使用;/api/search 永远
  返回原始结果。门控规则:查询含词库中完全不存在的拉丁词 → 拒答;
  bigram/字符两级覆盖率、多个拉丁词命中、或"单一来源专名"才放行。

融合:三路各自排序后用 RRF(k=60,见 RAG评测研究笔记 K41)合成。
 Like 兜底(整句子串)只在三路全空时启用,且视为强证据。
"""
from __future__ import annotations

import hashlib
import math
import re
import sqlite3
import struct
from typing import Any

EMBED_DIM = 384
RRF_K = 60
CONF_THRESHOLD = 0.45       # ≥ 此覆盖率:正常回答
LOW_THRESHOLD = 0.18        # 介于两者之间:低置信回答(带免责声明);低于则硬拒答
LATIN_MULTI = 2             # top1 命中 ≥2 个不同拉丁词即放行
VEC_FLOOR = 0.02            # 向量腿最低余弦
LIKE_MIN_LEN = 4            # LIKE 兜底最小查询长度

# 功能字:虚词/疑问词,不参与覆盖度计算(否则"是什么/多少"会虚增覆盖)
_FUNCTION_CHARS = set("的吗呢吧嘛啊呀哦是的了谁什么怎样如何多少几哪个哪里这些那还都很挺被把")
# 短语停用表:问题里的高频功能双字,不做短语级证据(如"是否通过英语六级"的"通过")
_STOP_BIGRAMS = {"通过", "是否", "进行", "已经", "可以", "有关", "关于", "还是", "这个", "那个", "以及", "或者"}

_LAT = re.compile(r"[a-z0-9][a-z0-9+\-.]*")
_CJK = re.compile(r"[\u4e00-\u9fff]+")

_CHUNK_FIELDS = """
  chunks.id AS chunk_id, chunks.source_id, chunks.chunk_index, chunks.title,
  chunks.page_start, chunks.page_end, chunks.content,
  sources.kind, sources.created_at, sources.parser_engine, sources.page_count
"""


def latin_tokens(text: str) -> list[str]:
    return [t for t in dict.fromkeys(_LAT.findall(text.lower())) if len(t) >= 2]


def cjk_bigrams(text: str) -> list[str]:
    out: list[str] = []
    for run in _CJK.findall(text):
        if len(run) == 1:
            out.append(run)
            continue
        out.extend(run[i:i + 2] for i in range(len(run) - 1))
    return out


def cjk_chars(text: str) -> list[str]:
    seen: list[str] = []
    for run in _CJK.findall(text):
        for ch in run:
            seen.append(ch)
    return seen


# ---------------------------------------------------------------- embedding

def _h(term: str) -> int:
    return int.from_bytes(hashlib.blake2b(term.encode("utf-8"), digest_size=8).digest(), "big")


def embed(text: str) -> list[float]:
    """字符 n-gram 符号哈希嵌入:拉丁词 + CJK 双字/单字,L2 归一。零依赖、确定性。"""
    vec = [0.0] * EMBED_DIM

    def add(term: str, weight: float) -> None:
        hv = _h(term)
        i1, i2 = hv % EMBED_DIM, (hv >> 16) % EMBED_DIM
        s1 = 1.0 if (hv >> 8) & 1 else -1.0
        s2 = 1.0 if (hv >> 9) & 1 else -1.0
        vec[i1] += s1 * weight
        vec[i2] += s2 * weight

    for tok in latin_tokens(text):
        add("w:" + tok, 1.0)
    for run in _CJK.findall(text):
        for i in range(len(run) - 1):
            add("b:" + run[i:i + 2], 1.0)
        for ch in run:
            add("u:" + ch, 0.4)
    norm = math.sqrt(sum(v * v for v in vec)) or 1.0
    return [v / norm for v in vec]


def pack_vector(vec: list[float]) -> bytes:
    return struct.pack(f"<{EMBED_DIM}f", *vec)


def unpack_vector(blob: bytes) -> list[float]:
    return list(struct.unpack(f"<{EMBED_DIM}f", blob))


def cosine(a: list[float], b: list[float]) -> float:
    return sum(x * y for x, y in zip(a, b))


def chunk_hash(content: str) -> str:
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


# ---------------------------------------------------------------- indexing

def index_source(conn: sqlite3.Connection, source_id: str) -> None:
    """为一份资料的全部 chunk 补齐 content_hash / bigram 索引 / 向量。幂等。"""
    rows = conn.execute(
        "SELECT id, content, content_hash FROM chunks WHERE source_id = ?", (source_id,)
    ).fetchall()
    qvec = None
    for row in rows:
        chunk_id, content, chash = row["id"], row["content"], row["content_hash"]
        if not chash:
            chash = chunk_hash(content)
            conn.execute("UPDATE chunks SET content_hash = ? WHERE id = ?", (chash, chunk_id))
        body = " ".join(cjk_bigrams(content))
        conn.execute("DELETE FROM chunks_bigram WHERE chunk_id = ?", (chunk_id,))
        conn.execute(
            "INSERT INTO chunks_bigram(chunk_id, body) VALUES (?, ?)", (chunk_id, body)
        )
        if qvec is None:
            qvec = embed(content)
        conn.execute(
            "INSERT OR REPLACE INTO chunk_vectors(chunk_id, dim, vector) VALUES (?, ?, ?)",
            (chunk_id, EMBED_DIM, pack_vector(qvec)),
        )


def backfill_indexes(conn: sqlite3.Connection) -> None:
    """启动时把旧数据补齐到三路索引(幂等,量级小,直接全量检查)。"""
    rows = conn.execute(
        """
        SELECT c.id FROM chunks c
        LEFT JOIN chunks_bigram b ON b.chunk_id = c.id
        LEFT JOIN chunk_vectors v ON v.chunk_id = c.id
        WHERE b.chunk_id IS NULL OR v.chunk_id IS NULL
           OR (c.content_hash IS NULL OR c.content_hash = '')
        """
    ).fetchall()
    if not rows:
        return
    by_source: dict[str, list[int]] = {}
    for row in rows:
        sid = conn.execute("SELECT source_id FROM chunks WHERE id = ?", (row["id"],)).fetchone()
        if sid:
            by_source.setdefault(sid["source_id"], []).append(row["id"])
    for source_id in by_source:
        index_source(conn, source_id)


# ---------------------------------------------------------------- search

def _fts_query(query: str) -> str:
    """原文 FTS 腿的 MATCH 表达式:拉丁词 + 多字中文段(单字如"的"太泛,剔除)。"""
    lats = [t for t in dict.fromkeys(_LAT.findall(query.lower())) if len(t) >= 2]
    runs = [r for r in dict.fromkeys(_CJK.findall(query)) if len(r) >= 2]
    tokens = (lats + runs)[:12]
    return " OR ".join(tokens) if tokens else (query.strip() or query)


def _load_rows(conn: sqlite3.Connection, ids: list[int]) -> dict[int, dict[str, Any]]:
    if not ids:
        return {}
    marks = ",".join("?" * len(ids))
    rows = conn.execute(
        f"SELECT {_CHUNK_FIELDS} FROM chunks JOIN sources ON sources.id = chunks.source_id "
        f"WHERE chunks.id IN ({marks}) AND sources.superseded = 0",
        ids,
    ).fetchall()
    return {r["chunk_id"]: dict(r) for r in rows}


def _snippet(content: str, qb: list[str], lats: list[str]) -> str:
    pos = -1
    for b in qb:
        pos = content.find(b)
        if pos >= 0:
            break
    if pos < 0:
        low = content.lower()
        for t in lats:
            pos = low.find(t)
            if pos >= 0:
                break
    if pos < 0:
        return content[:260]
    start = max(0, pos - 60)
    prefix = "…" if start else ""
    return prefix + content[start:start + 420]


def _informative_chars(text: str) -> list[str]:
    out: list[str] = []
    for run in _CJK.findall(text):
        for ch in run:
            if ch not in _FUNCTION_CHARS:
                out.append(ch)
    return list(dict.fromkeys(out))


def _chunk_total(conn: sqlite3.Connection) -> int:
    row = conn.execute(
        "SELECT COUNT(*) FROM chunks JOIN sources ON sources.id = chunks.source_id "
        "WHERE sources.superseded = 0"
    ).fetchone()
    return max(row[0], 1)


def _char_df(conn: sqlite3.Connection, ch: str) -> int:
    row = conn.execute(
        "SELECT COUNT(*) FROM chunks c JOIN sources s ON s.id = c.source_id "
        "WHERE s.superseded = 0 AND c.content LIKE ?",
        (f"%{ch}%",),
    ).fetchone()
    return row[0]


def _coverage(conn: sqlite3.Connection, query: str, contents: str | list[str]) -> float | None:
    """信息字 IDF 加权覆盖率:问题中的实义字有多少(按稀有度加权)落在证据里。

    contents 可以是单个 chunk 或 top3 证据集(联合计算)。
    功能字(是什么/多少/哪)不计入;df=0 的字权重最高——问了一个库里
    完全没有的字,覆盖度会被显著压低。纯拉丁查询返回 None,交给拉丁规则。
    """
    chars = _informative_chars(query)
    if not chars:
        return None
    if isinstance(contents, str):
        contents = [contents]
    joined = "\n".join(contents)
    n = _chunk_total(conn)
    total = matched = 0.0
    for ch in chars:
        weight = math.log((n + 1) / (_char_df(conn, ch) + 0.5))
        total += weight
        if ch in joined:
            matched += weight
    return round(matched / total, 3) if total > 0 else None


def search_chunks(conn: sqlite3.Connection, query: str, limit: int = 8) -> list[dict[str, Any]]:
    """三路召回 + RRF 融合。返回附带 confidence_signals 的结果列表。"""
    q = (query or "").strip()
    if not q:
        return []
    lats = latin_tokens(q)
    qb = list(dict.fromkeys(cjk_bigrams(q)))[:80]

    candidates: dict[int, dict[str, Any]] = {}
    legs: list[dict[int, float]] = []
    signals: dict[int, dict[str, Any]] = {}

    # 腿 A:原文 FTS(拉丁词/整段),与 M0 相同
    try:
        rows = conn.execute(
            f"""
            SELECT {_CHUNK_FIELDS},
                   snippet(chunks_fts, 1, '<mark>', '</mark>', '...', 18) AS snippet,
                   bm25(chunks_fts) AS rank
            FROM chunks_fts
            JOIN chunks ON chunks_fts.rowid = chunks.id
            JOIN sources ON chunks.source_id = sources.id
            WHERE chunks_fts MATCH ? AND sources.superseded = 0
            ORDER BY rank LIMIT 50
            """,
            (_fts_query(q),),
        ).fetchall()
    except sqlite3.OperationalError:
        rows = []
    leg_a: dict[int, float] = {}
    for r in rows:
        d = dict(r)
        candidates[d["chunk_id"]] = d
        leg_a[d["chunk_id"]] = -d["rank"]
        signals.setdefault(d["chunk_id"], {})["snippet"] = d.pop("snippet", "")
    legs.append(leg_a)

    # 腿 B:中文双字 FTS
    leg_b: dict[int, float] = {}
    if qb:
        try:
            rows = conn.execute(
                """
                SELECT cb.chunk_id, cb.body, bm25(chunks_bigram) AS rank
                FROM chunks_bigram cb
                JOIN chunks ON chunks.id = cb.chunk_id
                JOIN sources ON chunks.source_id = sources.id
                WHERE chunks_bigram MATCH ? AND sources.superseded = 0
                ORDER BY rank LIMIT 50
                """,
                (" OR ".join(qb),),
            ).fetchall()
        except sqlite3.OperationalError:
            rows = []
        for r in rows:
            cid = r["chunk_id"]
            leg_b[cid] = -r["rank"]
            if cid in candidates:
                candidates[cid]["_bigram_body"] = r["body"]
            else:
                candidates[cid] = {"_bigram_body": r["body"]}
    legs.append(leg_b)

    # 腿 C:哈希嵌入向量(余弦)
    leg_c: dict[int, float] = {}
    qvec = embed(q)
    for r in conn.execute(
        """
        SELECT cv.chunk_id, cv.vector FROM chunk_vectors cv
        JOIN chunks ON chunks.id = cv.chunk_id
        JOIN sources ON chunks.source_id = sources.id
        WHERE sources.superseded = 0
        """
    ).fetchall():
        sim = cosine(qvec, unpack_vector(r["vector"]))
        if sim >= VEC_FLOOR:
            leg_c[r["chunk_id"]] = sim
    legs.append(leg_c)

    missing = [cid for cid in dict.fromkeys(list(leg_b) + list(leg_c)) if cid not in candidates or "content" not in candidates[cid]]
    for cid, row in _load_rows(conn, missing).items():
        candidates.setdefault(cid, {}).update(row)

    # RRF 融合
    fused: dict[int, float] = {}
    for leg in legs:
        for pos, (cid, _score) in enumerate(
            sorted(leg.items(), key=lambda kv: kv[1], reverse=True), start=1
        ):
            fused[cid] = fused.get(cid, 0.0) + 1.0 / (RRF_K + pos)
    if not fused and len(q) >= LIKE_MIN_LEN:
        like = f"%{q}%"
        for r in conn.execute(
            f"""
            SELECT {_CHUNK_FIELDS} FROM chunks
            JOIN sources ON chunks.source_id = sources.id
            WHERE sources.superseded = 0 AND (chunks.content LIKE ? OR chunks.title LIKE ?)
            ORDER BY chunks.id DESC LIMIT 3
            """,
            (like, like),
        ).fetchall():
            d = dict(r)
            candidates[d["chunk_id"]] = d
            fused[d["chunk_id"]] = 0.0
            signals.setdefault(d["chunk_id"], {})["source"] = "like_fallback"

    results: list[dict[str, Any]] = []
    for cid, score in sorted(fused.items(), key=lambda kv: kv[1], reverse=True)[:limit]:
        d = candidates.get(cid)
        if not d or "content" not in d:
            continue
        body = d.get("_bigram_body") or " ".join(cjk_bigrams(d["content"]))
        cov = _coverage(conn, q, d["content"])
        low = d["content"].lower()
        hit_lats = [t for t in lats if t in low]
        sig = signals.get(cid, {})
        d.setdefault("snippet", sig.get("snippet") or _snippet(d["content"], qb, lats))
        d["rank"] = round(score, 6)
        d["confidence_signals"] = {
            "source": sig.get("source", "fused"),
            "coverage": cov,
            "latin_hits": hit_lats,
            "legs": [name for name, leg in (("fts", leg_a), ("bigram", leg_b), ("vector", leg_c)) if cid in leg],
            "vector_cos": round(leg_c[cid], 4) if cid in leg_c else None,
        }
        results.append(d)
    return results


def _informative_bigrams(text: str) -> list[str]:
    """两字均非功能字的滑动双字(短语级证据的最小单位)。"""
    out: list[str] = []
    for run in _CJK.findall(text):
        for i in range(len(run) - 1):
            a, b = run[i], run[i + 1]
            if a in _FUNCTION_CHARS or b in _FUNCTION_CHARS:
                continue
            gram = a + b
            if gram in _STOP_BIGRAMS:
                continue
            out.append(gram)
    return list(dict.fromkeys(out))[:80]


def _latin_df(conn: sqlite3.Connection, token: str) -> int:
    like = f"%{token}%"
    row = conn.execute(
        """
        SELECT COUNT(DISTINCT s.id) FROM chunks c
        JOIN sources s ON s.id = c.source_id
        WHERE s.superseded = 0 AND (c.content LIKE ? OR c.title LIKE ?)
        """,
        (like, like),
    ).fetchone()
    return row[0] if row else 0


def confidence(conn: sqlite3.Connection, results: list[dict[str, Any]], query: str) -> tuple[str, str]:
    """问答路径的三档置信判定;/api/search 不经过这里。

    返回 ("confident" | "low" | "abstain", reason):
    - confident:证据充分,正常回答
    - low:仅部分相关,回答须带"低置信"免责声明并附引用
    - abstain:硬拒答(空结果 / 查询含库中完全不存在的拉丁词 / 覆盖过低)
    真实语料验证(2026-11-03,简历 PDF)表明单一硬阈值会把"换了措辞的有效
    问题"一并拦掉,因此引入中间档。
    """
    if not results:
        return "abstain", "no_results"
    sig = results[0].get("confidence_signals", {})
    if sig.get("source") == "like_fallback":
        return "confident", "like_exact"
    if any(_latin_df(conn, t) == 0 for t in latin_tokens(query)):
        return "abstain", "unknown_term"
    # 覆盖度按 top3 证据集联合计算:问题的证据往往分散在多个 chunk,
    # 只看 top1 会把"答案不在第一名"的有效问题错杀(真实语料验证结论)。
    # confident 档要求单 chunk 覆盖(证据集中在一条里才足以自信作答);
    # union-3 只用于低置信档——它会被 CSV 表头这类顺带匹配垫高,不能作为自信依据。
    cov_top1 = sig.get("coverage")
    cov3 = _coverage(conn, query, [r.get("content", "") for r in results[:3]])
    if cov_top1 is not None and cov_top1 >= CONF_THRESHOLD:
        return "confident", "cjk_coverage"
    if len(sig.get("latin_hits") or []) >= LATIN_MULTI:
        return "confident", "latin_multi"
    if (cov3 is not None and cov3 >= LOW_THRESHOLD) or (cov_top1 is not None and cov_top1 >= LOW_THRESHOLD):
        return "low", "partial_coverage"
    # 短语级证据:问题里任一信息双字真实出现在证据集(如"云深/科技/教育"),
    # 说明存在相关内容,但覆盖率不足 → 低置信档而非硬拒答。
    # IDF 字符覆盖在"问题措辞字"(候选人/间/做)缺席时会被压得过低,
    # 真实语料验证(2026-11-03)确认必须用短语信号兜底。
    joined = "\n".join(r.get("content", "") for r in results[:3])
    if any(gram in joined for gram in _informative_bigrams(query)):
        return "low", "phrase_evidence"
    return "abstain", "low_confidence"
