"""M2/P1 知识编译层:wiki 页面 + 证据关联 + ChangeSet + 版本快照 + lint + compose。

架构(对齐总规划的六类核心对象):
- 证据层:chunks / wiki_evidence(页面↔chunk 的可溯源关联);
- 知识层:wiki_pages(topic/entity/compose/manual)+ [[双向链接]] + 文件镜像
  (data/wiki/*.md、index.md、追加式 log.md);
- 治理层:每次编译产生 ChangeSet(落在 wiki_pending_ops,diff+原因+证据),
  wiki_auto_apply 开启时自动应用(留完整审计),关闭时进待审队列;
  origin='manual' 的页面受人工修订保护,自动编译不得覆盖(rebuild force 可越权);
  lint 输出孤儿页/断链/重复实体/陈旧证据/疑似矛盾/空页。

关键语义:
- Wiki 是可重新生成的知识视图,原始资料才是事实来源;
- 删除的自动页可由 rebuild 重生;手工页(origin=manual)与重定向页
  (origin=redirect,别名合并产物)永不被自动清理;
- 回滚也产生新快照,历史只增不删。

零第三方依赖;不 import server,避免循环。
"""
from __future__ import annotations

import difflib
import json
import re
import sqlite3
import uuid
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

LINK_RE = re.compile(r"\[\[([^\]\[]+)\]\]")
ENT_RE = re.compile(r"[A-Za-z][A-Za-z0-9+#/\.]{1,}")
SLUG_BAD = re.compile(r"[\\/:*?\"<>|\s]+")
MAX_ENTITIES_PER_SOURCE = 12
CLAIMS_PER_PAGE = 5
QUOTE_LEN = 160
SNIPPET_LEN = 110

STOP_ENTITIES = {
    "ai", "api", "app", "com", "cn", "csv", "dmg", "demo", "doc", "docs", "github",
    "http", "https", "io", "json", "md", "pdf", "qq", "the", "and", "for", "with",
    "www", "yaml", "yml", "txt", "zip", "png", "jpg", "html", "css", "js", "py",
}

# 疑似矛盾检测:数值 + 单位(同页不同来源、同单位、不同数值)
NUM_UNIT_RE = re.compile(r"(\d+(?:\.\d+)?)\s*(%|万元|亿元|万|亿|元|天|年|个月|人|万|GB|QPS|节|分钟|家|份|轮)")

_DIR: Path | None = None


def init(data_dir: Path) -> None:
    global _DIR
    _DIR = Path(data_dir) / "wiki"
    _DIR.mkdir(parents=True, exist_ok=True)


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def slugify(title: str) -> str:
    slug = SLUG_BAD.sub("-", title.strip().lower()).strip("-")
    return slug[:80] or "page"


def _diff(old: str, new: str) -> str:
    if old == new:
        return ""
    return "\n".join(
        difflib.unified_diff(
            old.splitlines(), new.splitlines(),
            fromfile="current", tofile="proposed", lineterm="",
        )
    )


def get_config(conn: sqlite3.Connection, key: str, default: str) -> str:
    row = conn.execute("SELECT value FROM settings WHERE key = ?", (key,)).fetchone()
    return row["value"] if row else default


def set_config(conn: sqlite3.Connection, key: str, value: str) -> None:
    conn.execute(
        "INSERT INTO settings(key, value) VALUES (?, ?) "
        "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
        (key, value),
    )


# ---------------------------------------------------------------- extraction

def extract_entities(conn: sqlite3.Connection, source_id: str) -> list[tuple[str, int]]:
    """从一份资料的 chunks 提取拉丁实体(词频驱动,复数归并,停用词过滤)。"""
    counts: Counter[str] = Counter()
    for row in conn.execute("SELECT content FROM chunks WHERE source_id = ?", (source_id,)):
        for tok in ENT_RE.findall(row["content"]):
            tok = tok.lower().rstrip(".")
            if len(tok) < 2 or tok in STOP_ENTITIES or tok.isdigit():
                continue
            counts[tok] += 1
    for tok in list(counts):
        if tok.endswith("s") and tok[:-1] in counts:
            counts[tok[:-1]] += counts.pop(tok)
    ranked = sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))
    return ranked[:MAX_ENTITIES_PER_SOURCE]


def _quote(content: str) -> str:
    return re.sub(r"\s+", " ", content).strip()[:QUOTE_LEN]


def _alias_map(conn: sqlite3.Connection) -> dict[str, str]:
    """别名/标题/slug → 规范 slug(用于实体归并,避免同名异页)。"""
    mapping: dict[str, str] = {}
    for row in conn.execute("SELECT slug, title, aliases FROM wiki_pages").fetchall():
        mapping[row["slug"].lower()] = row["slug"]
        mapping[row["title"].lower()] = row["slug"]
        try:
            for alias in json.loads(row["aliases"] or "[]"):
                mapping[str(alias).lower()] = row["slug"]
        except (ValueError, TypeError):
            pass
    return mapping


def _page_aliases(row: sqlite3.Row | dict) -> list[str]:
    try:
        return list(json.loads(row["aliases"] or "[]"))
    except (ValueError, TypeError):
        return []


# ---------------------------------------------------------------- page bodies

def _topic_body(conn: sqlite3.Connection, source: sqlite3.Row, entities: list[tuple[str, int]]) -> str:
    status = "已被取代(供回溯)" if source["superseded"] else "现行版本"
    lines = [
        f"# {source['title']}",
        "",
        "- 页面类型:主题页(自动生成)",
        f"- 来源文件:{source['original_name']} · {source['kind']} · 解析:{source['parser_engine'] or 'text'}",
        f"- 规模:{source['page_count'] or 0} 页 / {source['char_count'] or 0} 字 · 状态:{status}",
        "",
        "## 相关实体",
    ]
    if entities:
        for name, cnt in entities:
            lines.append(f"- [[{slugify(name)}]](提及 {cnt} 次)")
    else:
        lines.append("(未提取到实体)")
    lines += ["", "## 内容块索引", "", "| 块 | 页码 | 摘录 |", "|---|---|---|"]
    for row in conn.execute(
        "SELECT chunk_index, page_start, page_end, content FROM chunks WHERE source_id = ? ORDER BY chunk_index",
        (source["id"],),
    ):
        head = re.sub(r"\s+", " ", row["content"]).strip()[:SNIPPET_LEN]
        pages = f"p{row['page_start']}" if row["page_start"] == row["page_end"] else f"p{row['page_start']}-p{row['page_end']}"
        lines.append(f"| chunk {row['chunk_index']} | {pages} | {head}… |")
    lines += [
        "",
        "## 证据",
        "",
        "> 每条结论可回溯到 chunk;被取代资料的证据会在 lint 中标记为陈旧。",
    ]
    return "\n".join(lines) + "\n"


def _entity_body(name: str, pairs: list[dict[str, Any]], aliases: list[str]) -> str:
    lines = [
        f"# {name}",
        "",
        "- 页面类型:实体页(自动提取)",
        f"- 提及 {len(pairs)} 个内容块",
    ]
    if aliases:
        lines.append(f"- 别名:{'、'.join(aliases)}")
    lines += ["", "## 提及位置", ""]
    for pair in pairs:
        pages = f"p{pair['page_start']}" if pair["page_start"] == pair["page_end"] else f"p{pair['page_start']}-p{pair['page_end']}"
        lines.append(f"- [[{pair['topic_slug']}]] chunk {pair['chunk_index']}({pages}):{pair['quote']}…")
    return "\n".join(lines) + "\n"


def _source_pairs(conn: sqlite3.Connection, source: sqlite3.Row, topic_slug: str) -> list[dict[str, Any]]:
    return [
        {
            "chunk_id": r["id"], "chunk_index": r["chunk_index"],
            "page_start": r["page_start"], "page_end": r["page_end"],
            "source_id": source["id"], "topic_slug": topic_slug, "quote": _quote(r["content"]),
        }
        for r in conn.execute(
            "SELECT id, chunk_index, page_start, page_end, content FROM chunks WHERE source_id = ? ORDER BY chunk_index",
            (source["id"],),
        )
    ]


# ---------------------------------------------------------------- compile plan

def _plan_for_source(conn: sqlite3.Connection, source: sqlite3.Row, amap: dict[str, str]) -> tuple[dict[str, dict], dict[str, list]]:
    """单份资料的编译计划。返回 (entries{slug:entry}, evidence_pairs{slug:pairs})。"""
    entries: dict[str, dict] = {}
    pairs_by_slug: dict[str, list] = {}
    slug = slugify(source["title"])
    entities = extract_entities(conn, source["id"])
    entries[slug] = {
        "slug": slug, "title": source["title"], "kind": "topic",
        "body": _topic_body(conn, source, entities),
        "note": f"来源编译:{source['original_name']}", "aliases": [],
    }
    pairs = _source_pairs(conn, source, slug)
    pairs_by_slug[slug] = pairs
    for name, _cnt in entities:
        ent_slug = slugify(name)
        canonical = amap.get(ent_slug, ent_slug)
        if canonical not in entries:
            existing = conn.execute("SELECT title FROM wiki_pages WHERE slug = ?", (canonical,)).fetchone()
            entries[canonical] = {
                "slug": canonical, "title": existing["title"] if existing else name, "kind": "entity",
                "body": "", "note": f"实体编译:{source['title']}",
                "aliases": [name] if canonical != ent_slug else [],
            }
            pairs_by_slug[canonical] = []
        elif name.lower() != canonical.lower() and name not in entries[canonical]["aliases"]:
            entries[canonical]["aliases"].append(name)
        ent_pairs = [p for p in pairs if p["quote"].lower().find(name) >= 0]
        if not ent_pairs:
            ent_pairs = [
                dict(p, quote=_quote(r["content"]))
                for p in pairs
                for r in [conn.execute("SELECT content FROM chunks WHERE id = ?", (p["chunk_id"],)).fetchone()]
                if name in r["content"].lower()
            ]
        pairs_by_slug[canonical] = pairs_by_slug.get(canonical, []) + ent_pairs
    for canonical, e_pairs in pairs_by_slug.items():
        if canonical in entries and entries[canonical]["kind"] == "entity":
            entries[canonical]["body"] = _entity_body(entries[canonical]["title"], e_pairs, entries[canonical]["aliases"])
    return entries, pairs_by_slug


def update_pages_for_source(conn: sqlite3.Connection, source_id: str) -> None:
    """资料入库后的增量编译:主题页 + 相关实体页(只动受影响页面)。"""
    if _DIR is None:
        return
    source = conn.execute("SELECT * FROM sources WHERE id = ?", (source_id,)).fetchone()
    if source is None:
        return
    entries, pairs_by = _plan_for_source(conn, source, _alias_map(conn))
    _apply_plan(conn, entries, pairs_by, dry_run=False, force=False)


def rebuild_all(conn: sqlite3.Connection, dry_run: bool = False, force: bool = False) -> list[dict[str, Any]]:
    """全量重编译:聚合所有现行资料;dry_run 只返回变更单;force 可越过人工保护。"""
    if _DIR is None:
        return []
    amap = _alias_map(conn)
    entries: dict[str, dict] = {}
    pairs_by: dict[str, list] = {}
    for source in conn.execute("SELECT * FROM sources WHERE superseded = 0 ORDER BY created_at").fetchall():
        src_entries, src_pairs = _plan_for_source(conn, source, amap)
        for slug, entry in src_entries.items():
            if slug in entries:
                if entries[slug]["kind"] == "entity":
                    entries[slug]["aliases"] = sorted(set(entries[slug]["aliases"]) | set(entry["aliases"]))
                    pairs_by[slug] = pairs_by.get(slug, []) + src_pairs.get(slug, [])
            else:
                entries[slug] = entry
                pairs_by[slug] = src_pairs.get(slug, [])
    for slug, entry in entries.items():
        if entry["kind"] == "entity":
            entry["body"] = _entity_body(entry["title"], pairs_by.get(slug, []), entry["aliases"])

    existing = {r["slug"]: r for r in conn.execute("SELECT * FROM wiki_pages").fetchall()}
    deletions = [
        {"slug": slug, "title": row["title"], "kind": row["kind"]}
        for slug, row in existing.items()
        if slug not in entries and row["origin"] == "auto"
    ]
    if dry_run:
        changes = _plan_changes(conn, entries, existing, force=force)
        for d in deletions:
            changes.append({"slug": d["slug"], "title": d["title"], "kind": d["kind"], "action": "delete", "diff": "(删除:来源已不存在或被取代)"})
        return changes
    return _apply_plan(conn, entries, pairs_by, dry_run=False, force=force, deletions=deletions)


def _plan_changes(
    conn: sqlite3.Connection, entries: dict[str, dict], existing: dict[str, sqlite3.Row], force: bool = False
) -> list[dict[str, Any]]:
    changes: list[dict[str, Any]] = []
    for slug in sorted(entries):
        entry = entries[slug]
        old = existing.get(slug)
        if old is None:
            action, diff = "create", "(新建)"
        elif old["origin"] == "manual" and not force:
            action, diff = "skipped", "(人工修订保护:跳过正文覆盖)"
        else:
            action = "update" if old["body"] != entry["body"] else "none"
            diff = _diff(old["body"], entry["body"])
        changes.append({"slug": slug, "title": entry["title"], "kind": entry["kind"], "action": action, "diff": diff})
    return changes


def _record_changeset(
    conn: sqlite3.Connection, entry: dict[str, Any], action: str, diff: str, pairs: list, status: str
) -> None:
    current = conn.execute("SELECT body FROM wiki_pages WHERE slug = ?", (entry["slug"],)).fetchone()
    conn.execute(
        "INSERT INTO wiki_pending_ops(id, slug, op_type, proposed_title, proposed_body, diff_text, note, "
        "source, payload, status, created_at, resolved_at, base_body) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (
            str(uuid.uuid4()), entry["slug"], action, entry["title"], entry.get("body", ""),
            diff, entry.get("note", ""), "compile",
            json.dumps({"evidence": pairs, "kind": entry.get("kind", "manual"), "aliases": entry.get("aliases", [])}, ensure_ascii=False), status, now_iso(), now_iso() if status != "pending" else "",
            current["body"] if current else "",
        ),
    )


def _apply_plan(
    conn: sqlite3.Connection,
    entries: dict[str, dict],
    pairs_by: dict[str, list],
    dry_run: bool,
    force: bool,
    deletions: list[dict] | None = None,
) -> list[dict[str, Any]]:
    """执行编译计划:受人工保护则跳过;auto_apply 关闭时进待审;全部留 ChangeSet 审计。"""
    existing = {r["slug"]: r for r in conn.execute("SELECT * FROM wiki_pages").fetchall()}
    changes = _plan_changes(conn, entries, existing, force=force)
    auto_apply = get_config(conn, "wiki_auto_apply", "1") == "1"
    if dry_run:
        return changes

    created = now_iso()
    for change in changes:
        if change["action"] == "none":
            continue
        entry = entries[change["slug"]]
        pairs = pairs_by.get(change["slug"], [])
        if change["action"] == "skipped":
            _log("skip", change["slug"], "人工修订保护:自动编译未覆盖")
            continue
        if auto_apply:
            page_id, _ = _write_page(conn, entry, origin="auto")
            _set_evidence(conn, page_id, pairs)
            _set_claims(conn, page_id, pairs)
            _record_changeset(conn, entry, change["action"], change["diff"], pairs, status="applied")
            _log(change["action"], change["slug"], entry.get("note", ""))
        else:
            _record_changeset(conn, entry, change["action"], change["diff"], pairs, status="pending")
            _log("propose", change["slug"], f"编译变更进待审({change['action']})")

    for d in (deletions or []):
        if auto_apply:
            conn.execute("DELETE FROM wiki_pages WHERE slug = ?", (d["slug"],))
            _record_changeset(conn, {"slug": d["slug"], "title": d["title"], "body": "", "note": "rebuild 清理"},
                              "delete", "(来源已不存在或被取代)", [], status="applied")
            _log("delete", d["slug"], "rebuild 清理(来源已不存在或被取代)")
        else:
            _record_changeset(conn, {"slug": d["slug"], "title": d["title"], "body": "", "note": "rebuild 清理"},
                              "delete", "(来源已不存在或被取代)", [], status="pending")
    _write_files(conn)
    return changes


def _write_page(conn: sqlite3.Connection, entry: dict[str, Any], origin: str) -> tuple[str, str]:
    """写入页面正文;有变化时产生新快照。返回 (page_id, action)。"""
    created = now_iso()
    row = conn.execute("SELECT * FROM wiki_pages WHERE slug = ?", (entry["slug"],)).fetchone()
    body, title = entry["body"], entry["title"]
    if row is None:
        page_id = str(uuid.uuid4())
        conn.execute(
            "INSERT INTO wiki_pages(id, slug, title, kind, body, origin, aliases, created_at, updated_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (page_id, entry["slug"], title, entry["kind"], body, origin,
             json.dumps(entry.get("aliases", []), ensure_ascii=False), created, created),
        )
        conn.execute(
            "INSERT INTO wiki_revisions(page_id, rev, body, note, created_at) VALUES (?, 1, ?, ?, ?)",
            (page_id, body, entry.get("note") or "create", created),
        )
        return page_id, "create"
    merged_aliases = sorted(set(_page_aliases(row)) | set(entry.get("aliases", [])))
    if row["body"] != body or row["title"] != title or json.dumps(_page_aliases(row), ensure_ascii=False) != json.dumps(merged_aliases, ensure_ascii=False):
        new_rev = conn.execute(
            "SELECT COALESCE(MAX(rev), 0) + 1 FROM wiki_revisions WHERE page_id = ?", (row["id"],)
        ).fetchone()[0]
        conn.execute(
            "UPDATE wiki_pages SET title = ?, body = ?, origin = ?, aliases = ?, updated_at = ? WHERE id = ?",
            (title, body, origin, json.dumps(merged_aliases, ensure_ascii=False), created, row["id"]),
        )
        conn.execute(
            "INSERT INTO wiki_revisions(page_id, rev, body, note, created_at) VALUES (?, ?, ?, ?, ?)",
            (row["id"], new_rev, body, entry.get("note") or "auto-update", created),
        )
        return row["id"], "update"
    return row["id"], "none"


def _set_evidence(conn: sqlite3.Connection, page_id: str, pairs: list) -> None:
    conn.execute("DELETE FROM wiki_evidence WHERE page_id = ?", (page_id,))
    created = now_iso()
    for pair in pairs:
        conn.execute(
            "INSERT OR IGNORE INTO wiki_evidence(page_id, chunk_id, source_id, quote, created_at) "
            "VALUES (?, ?, ?, ?, ?)",
            (page_id, pair["chunk_id"], pair["source_id"], pair["quote"], created),
        )

def _set_claims(conn: sqlite3.Connection, page_id: str, pairs: list) -> None:
    """从证据 chunk 抽取结论级 claim(数值+单位→high,含数字→medium,其余→low)。"""
    conn.execute("DELETE FROM wiki_claims WHERE page_id = ?", (page_id,))
    created = now_iso()
    for pair in pairs[:CLAIMS_PER_PAGE]:
        chunk = conn.execute("SELECT content FROM chunks WHERE id = ?", (pair["chunk_id"],)).fetchone()
        if chunk is None:
            continue
        text, confidence = "", "low"
        for sent in _key_sentences(chunk["content"], limit=4):
            if NUM_UNIT_RE.search(sent):
                text, confidence = sent, "high"
                break
            if re.search(r"\d", sent) and not text:
                text, confidence = sent, "medium"
        if not text:
            head = _key_sentences(chunk["content"], limit=1)
            if head:
                text, confidence = head[0], "low"
        if not text:
            continue
        conn.execute(
            "INSERT INTO wiki_claims(id, page_id, chunk_id, source_id, text, confidence, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (str(uuid.uuid4()), page_id, pair["chunk_id"], pair["source_id"], text, confidence, created),
        )


# ---------------------------------------------------------------- alias merge

def merge_pages(conn: sqlite3.Connection, from_slug: str, into_slug: str) -> dict[str, Any]:
    """别名合并:证据并入目标页,源页转为重定向存根(历史保留)。"""
    src = conn.execute("SELECT * FROM wiki_pages WHERE slug = ?", (from_slug,)).fetchone()
    dst = conn.execute("SELECT * FROM wiki_pages WHERE slug = ?", (into_slug,)).fetchone()
    if src is None or dst is None:
        raise LookupError("合并双方都必须是已存在的页面")
    if from_slug == into_slug:
        raise ValueError("不能把页面合并到它自己")
    aliases = sorted(set(_page_aliases(dst)) | {src["title"], src["slug"]})
    conn.execute(
        "UPDATE wiki_pages SET aliases = ?, updated_at = ? WHERE id = ?",
        (json.dumps(aliases, ensure_ascii=False), now_iso(), dst["id"]),
    )
    conn.execute(
        "INSERT OR IGNORE INTO wiki_evidence(page_id, chunk_id, source_id, quote, created_at) "
        f"SELECT '{dst['id']}', chunk_id, source_id, quote, created_at FROM wiki_evidence WHERE page_id = ?",
        (src["id"],),
    )
    conn.execute("DELETE FROM wiki_evidence WHERE page_id = ?", (src["id"],))
    stub = f"# {src['title']}\n\n已合并到 [[{into_slug}]]。本页保留作为重定向,证据已并入目标页。\n"
    conn.execute(
        "UPDATE wiki_pages SET body = ?, origin = 'redirect', updated_at = ? WHERE id = ?",
        (stub, now_iso(), src["id"]),
    )
    _write_files(conn)
    _log("merge", from_slug, f"并入 {into_slug};别名 {aliases}")
    return {"from": from_slug, "into": into_slug, "aliases": aliases}


# ---------------------------------------------------------------- files

def _log(action: str, slug: str, detail: str) -> None:
    if _DIR is None:
        return
    log_path = _DIR / "log.md"
    header = "# 操作日志(追加式,勿手改)\n\n| 时间 | 操作 | 页面 | 说明 |\n|---|---|---|---|\n"
    if not log_path.exists():
        log_path.write_text(header, encoding="utf-8")
    with open(log_path, "a", encoding="utf-8") as fh:
        fh.write(f"| {now_iso()} | {action} | {slug} | {detail} |\n")


def _write_index(conn: sqlite3.Connection) -> None:
    if _DIR is None:
        return
    groups: dict[str, list[str]] = {"topic": [], "entity": [], "other": []}
    for row in conn.execute(
        "SELECT p.*, (SELECT COUNT(*) FROM wiki_evidence e WHERE e.page_id = p.id) AS evidence_count "
        "FROM wiki_pages p ORDER BY p.kind, p.slug"
    ):
        line = f"- [[{row['slug']}]] {row['title']}(证据 {row['evidence_count']} 条)"
        groups.get(row["kind"], groups["other"]).append(line)
    lines = ["# 知识库索引", "", f"> 自动维护于 {now_iso()};页面正文见同名 .md 文件。",
             "", f"## 主题页({len(groups['topic'])})", *groups["topic"], "",
             f"## 实体页({len(groups['entity'])})", *groups["entity"], ""]
    if groups["other"]:
        lines += [f"## 其他页面({len(groups['other'])})", *groups["other"], ""]
    (_DIR / "index.md").write_text("\n".join(lines), encoding="utf-8")


def _write_files(conn: sqlite3.Connection) -> None:
    if _DIR is None:
        return
    for row in conn.execute("SELECT slug, body FROM wiki_pages").fetchall():
        (_DIR / f"{slugify(row['slug'])}.md").write_text(row["body"], encoding="utf-8")
    _write_index(conn)


# ---------------------------------------------------------------- pending ops / rollback

def propose(conn: sqlite3.Connection, slug: str, title: str, body: str, note: str, aliases: list[str] | None = None) -> dict[str, Any]:
    """外部/LLM 修改入口:只生成 pending diff,不动正文。"""
    if _DIR is None:
        raise RuntimeError("wiki 未初始化")
    existing = conn.execute("SELECT * FROM wiki_pages WHERE slug = ?", (slug,)).fetchone()
    op_type = "update" if existing else "create"
    current_body = existing["body"] if existing else ""
    diff = _diff(current_body, body)
    op_id = str(uuid.uuid4())
    conn.execute(
        "INSERT INTO wiki_pending_ops(id, slug, op_type, proposed_title, proposed_body, diff_text, note, "
        "source, payload, status, created_at, resolved_at, base_body) VALUES (?, ?, ?, ?, ?, ?, ?, 'agent', ?, 'pending', ?, '', ?)",
        (op_id, slug, op_type, title or slug, body, diff, note,
         json.dumps({"aliases": aliases or []}, ensure_ascii=False), now_iso(), current_body),
    )
    _log("propose", slug, f"pending op {op_id[:8]}({op_type})")
    return {"op_id": op_id, "op_type": op_type, "diff": diff, "status": "pending"}


def resolve_op(conn: sqlite3.Connection, op_id: str, apply: bool) -> dict[str, Any]:
    op = conn.execute("SELECT * FROM wiki_pending_ops WHERE id = ?", (op_id,)).fetchone()
    if op is None:
        raise LookupError("没有找到这条待审修改")
    if op["status"] != "pending":
        raise ValueError(f"该修改已处理({op['status']})")
    if not apply:
        conn.execute(
            "UPDATE wiki_pending_ops SET status = 'discarded', resolved_at = ? WHERE id = ?",
            (now_iso(), op_id),
        )
        _log("discard", op["slug"], f"op {op_id[:8]}")
        return {"op_id": op_id, "status": "discarded"}

    current = conn.execute("SELECT body, origin FROM wiki_pages WHERE slug = ?", (op["slug"],)).fetchone()
    if op["base_body"] is None:
        raise ValueError("旧版待审修改缺少基线，请丢弃后重新生成")
    if ((op["op_type"] == "create" and current is not None)
            or (op["op_type"] != "create" and current is None)
            or (current is not None and current["body"] != op["base_body"])):
        raise ValueError("页面已变化，请丢弃这条过期待审修改后重新生成")
    if op["source"] == "compile" and current is not None and current["origin"] == "manual":
        raise ValueError("页面已由人工维护，请丢弃此自动编译修改")

    if op["op_type"] == "delete":
        conn.execute("DELETE FROM wiki_pages WHERE slug = ?", (op["slug"],))
        conn.execute(
            "UPDATE wiki_pending_ops SET status = 'applied', resolved_at = ? WHERE id = ?", (now_iso(), op_id)
        )
        _write_files(conn)
        _log("delete", op["slug"], f"待审删除应用 {op_id[:8]}")
        return {"op_id": op_id, "status": "applied", "action": "delete"}

    payload: Any = {}
    try:
        payload = json.loads(op["payload"] or "{}")
    except ValueError:
        pass
    if isinstance(payload, list):  # 兼容早期编译队列的证据数组
        payload = {"evidence": payload}
    if not isinstance(payload, dict):
        raise ValueError("待审修改格式无效，请丢弃后重新生成")
    origin = "manual" if op["source"] == "agent" else "auto"
    entry = {
        "slug": op["slug"], "title": op["proposed_title"], "body": op["proposed_body"],
        "note": f"待审修改应用:{op['note']}",
        "aliases": payload.get("aliases", []) if op["source"] == "agent" else [],
    }
    kind = payload.get("kind", "manual") if op["op_type"] == "create" else _page_kind(conn, op["slug"])
    entry["kind"] = kind
    page_id, action = _write_page(conn, entry, origin=origin)
    if op["source"] == "compile":
        try:
            evidence = payload.get("evidence", [])
            _set_evidence(conn, page_id, evidence)
            _set_claims(conn, page_id, evidence)
        except ValueError:
            pass
    conn.execute(
        "UPDATE wiki_pending_ops SET status = 'applied', resolved_at = ? WHERE id = ?", (now_iso(), op_id)
    )
    _write_files(conn)
    _log("apply", op["slug"], f"op {op_id[:8]}({op['source']})")
    return {"op_id": op_id, "status": "applied", "page_id": page_id, "action": action}


def _page_kind(conn: sqlite3.Connection, slug: str) -> str:
    row = conn.execute("SELECT kind FROM wiki_pages WHERE slug = ?", (slug,)).fetchone()
    return row["kind"] if row else "manual"


def rollback(conn: sqlite3.Connection, slug: str, rev: int) -> dict[str, Any]:
    page = conn.execute("SELECT * FROM wiki_pages WHERE slug = ?", (slug,)).fetchone()
    if page is None:
        raise LookupError("没有找到这个页面")
    target = conn.execute(
        "SELECT * FROM wiki_revisions WHERE page_id = ? AND rev = ?", (page["id"], rev)
    ).fetchone()
    if target is None:
        raise LookupError(f"没有找到 rev {rev}")
    entry = {"slug": slug, "title": page["title"], "kind": page["kind"],
             "body": target["body"], "note": f"回滚到 rev {rev}", "aliases": []}
    _, action = _write_page(conn, entry, origin=page["origin"])
    _write_files(conn)
    _log("rollback", slug, f"到 rev {rev}")
    return {"slug": slug, "rolled_back_to": rev, "action": action}


# ---------------------------------------------------------------- lint

def lint(conn: sqlite3.Connection) -> dict[str, Any]:
    """孤儿页 / 断链 / 重复实体 / 陈旧证据 / 疑似矛盾 / 空页。只报告,不修改。"""
    pages = conn.execute("SELECT * FROM wiki_pages").fetchall()
    by_slug = {p["slug"]: p for p in pages}
    inbound: Counter[str] = Counter()
    issues: list[dict[str, str]] = []

    for page in pages:
        if page["origin"] == "redirect":
            continue
        for m in LINK_RE.findall(page["body"]):
            target = slugify(m.strip())
            if target != page["slug"] and target not in by_slug:
                issues.append({"type": "broken_link", "severity": "error", "slug": page["slug"],
                               "detail": f"链接目标 [[{target}]] 不存在"})
            else:
                inbound[target] += 1

    seen_titles: dict[str, list[str]] = {}
    for page in pages:
        if page["kind"] == "entity" and page["origin"] != "redirect":
            seen_titles.setdefault(page["title"].lower(), []).append(page["slug"])
    for title, slugs in seen_titles.items():
        if len(slugs) > 1:
            issues.append({"type": "duplicate_entity", "severity": "warning", "slug": ",".join(slugs),
                           "detail": f"实体「{title}」有 {len(slugs)} 个页面,建议 merge_pages"})

    for page in pages:
        if page["origin"] == "redirect":
            continue
        ev_rows = conn.execute(
            "SELECT e.*, s.superseded, s.title AS source_title FROM wiki_evidence e "
            "JOIN sources s ON s.id = e.source_id WHERE e.page_id = ?",
            (page["id"],),
        ).fetchall()
        stale = [e for e in ev_rows if e["superseded"]]
        if stale:
            names = ", ".join(sorted({e["source_title"] for e in stale}))
            issues.append({"type": "stale_evidence", "severity": "warning", "slug": page["slug"],
                           "detail": f"证据来自被取代资料:{names};建议执行 rebuild"})
        if page["kind"] == "entity" and inbound[page["slug"]] == 0:
            issues.append({"type": "orphan", "severity": "warning", "slug": page["slug"],
                           "detail": "没有任何页面链接到它"})
        if page["kind"] == "entity" and not ev_rows:
            issues.append({"type": "empty_page", "severity": "warning", "slug": page["slug"], "detail": "没有证据支撑"})
        issues.extend(_suspected_conflicts(page, ev_rows))

    states = {
        row["issue_key"]: row["status"]
        for row in conn.execute("SELECT issue_key, status FROM wiki_lint_states").fetchall()
    }
    for issue in issues:
        issue["key"] = f"{issue['type']}|{issue['slug']}|{issue['detail']}"
        issue["status"] = states.get(issue["key"], "open")
    summary = Counter(i["type"] for i in issues)
    open_count = sum(1 for i in issues if i["status"] == "open")
    return {"pages": len(pages), "issues": issues, "summary": dict(summary),
            "open_count": open_count, "clean": open_count == 0}


def set_lint_status(conn: sqlite3.Connection, issue_key: str, status: str) -> dict[str, Any]:
    """持久化 lint 处理状态(open/resolved/ignored);只接受当前存在的提示。"""
    if status not in {"open", "resolved", "ignored"}:
        raise ValueError("status 必须是 open / resolved / ignored 之一")
    if issue_key not in {i["key"] for i in lint(conn)["issues"]}:
        raise LookupError("没有找到这条检查提示")
    conn.execute(
        "INSERT INTO wiki_lint_states(issue_key, status, updated_at) VALUES (?, ?, ?) "
        "ON CONFLICT(issue_key) DO UPDATE SET status = excluded.status, updated_at = excluded.updated_at",
        (issue_key, status, now_iso()),
    )
    return {"key": issue_key, "status": status}


def _suspected_conflicts(page: sqlite3.Row, ev_rows: list) -> list[dict[str, str]]:
    """同页、不同现行来源、同单位、不同数值 → 疑似矛盾(warning)。"""
    by_source: dict[str, list[tuple[str, str]]] = {}
    for e in ev_rows:
        if e["superseded"]:
            continue
        hits = NUM_UNIT_RE.findall(e["quote"] or "")
        if hits:
            by_source.setdefault(e["source_title"], []).extend((v, u) for v, u in hits)
    sources = list(by_source)
    issues: list[dict[str, str]] = []
    for i in range(len(sources)):
        for j in range(i + 1, len(sources)):
            a, b = by_source[sources[i]], by_source[sources[j]]
            units_a = {u: v for v, u in a}
            units_b = {u: v for v, u in b}
            for unit in set(units_a) & set(units_b):
                if units_a[unit] != units_b[unit]:
                    issues.append({
                        "type": "suspected_conflict", "severity": "warning", "slug": page["slug"],
                        "detail": f"「{unit}」口径不一致:{sources[i]}={units_a[unit]}{unit} vs "
                                  f"{sources[j]}={units_b[unit]}{unit};建议人工核对",
                    })
    return issues


# ---------------------------------------------------------------- compose(应用层)

_SENT_SPLIT = re.compile(r"[。;;!!??\n]+")


def _key_sentences(text: str, limit: int = 5) -> list[str]:
    scored: list[tuple[int, str]] = []
    for sent in _SENT_SPLIT.split(text):
        sent = sent.strip()
        if not (8 <= len(sent) <= 90):
            continue
        score = 0
        if re.search(r"\d", sent):
            score += 3
        if ENT_RE.search(sent):
            score += 2
        if sent.startswith("【"):
            score += 1
        scored.append((score, sent))
    scored.sort(key=lambda kv: -kv[0])
    seen, out = set(), []
    for _, sent in scored:
        key = sent[:20]
        if key in seen:
            continue
        seen.add(key)
        out.append(sent)
        if len(out) >= limit:
            break
    return out


def compose(conn: sqlite3.Connection, slugs: list[str], template: str, title: str, save: bool) -> dict[str, Any]:
    """基于指定主题页抽取式生成周报/提纲/学习材料(无 key 也可用,全部带出处)。"""
    if template not in ("outline", "weekly", "study"):
        raise ValueError("template 必须是 outline / weekly / study 之一")
    sections: list[dict[str, Any]] = []
    used_pairs: list[dict] = []
    for slug in slugs:
        page = conn.execute("SELECT * FROM wiki_pages WHERE slug = ?", (slug,)).fetchone()
        if page is None:
            raise LookupError(f"没有找到页面 {slug}")
        ev = conn.execute(
            "SELECT e.chunk_id, e.source_id, c.chunk_index, c.page_start, c.page_end, c.content, s.title AS source_title "
            "FROM wiki_evidence e JOIN chunks c ON c.id = e.chunk_id "
            "JOIN sources s ON s.id = e.source_id WHERE e.page_id = ? AND s.superseded = 0 ORDER BY c.chunk_index",
            (page["id"],),
        ).fetchall()
        if not ev:
            src = conn.execute(
                "SELECT id FROM sources WHERE superseded = 0 AND lower(title) = lower(?)", (page["title"],)
            ).fetchone()
            if src:
                ev = conn.execute(
                    "SELECT c.id AS chunk_id, c.source_id, c.chunk_index, c.page_start, c.page_end, c.content, s.title AS source_title "
                    "FROM chunks c JOIN sources s ON s.id = c.source_id "
                    "LEFT JOIN wiki_evidence e ON e.chunk_id = c.id AND e.page_id = ? "
                    "WHERE s.id = ? ORDER BY c.chunk_index", (page["id"], src["id"]),
                ).fetchall()
        bullets: list[str] = []
        for row in ev:
            for sent in _key_sentences(row["content"], limit=4):
                pages = f"p{row['page_start']}" if row["page_start"] == row["page_end"] else f"p{row['page_start']}-{row['page_end']}"
                bullets.append(f"- {sent}([[{slug}]] {pages})")
            used_pairs.append({"chunk_id": row["chunk_id"], "source_id": row["source_id"],
                               "page_start": row["page_start"], "page_end": row["page_end"],
                               "topic_slug": slug, "quote": _quote(row["content"])})
        sections.append({"slug": slug, "title": page["title"], "bullets": bullets})

    if template == "outline":
        lines = [f"# 提纲:{title or '、'.join(s['title'] for s in sections)}", "", f"> 生成于 {now_iso()},抽取式整理,出处见各条尾注。", ""]
        for s in sections:
            lines += [f"## {s['title']}", *s["bullets"], ""]
    elif template == "weekly":
        lines = [f"# 周报素材:{title or now_iso()[:10]}", "", f"> 本期覆盖 {len(sections)} 份资料,以下为按资料分组的要点。", ""]
        for s in sections:
            lines += [f"## {s['title']}", *s["bullets"], ""]
    else:  # study
        lines = [f"# 学习材料:{title or '、'.join(s['title'] for s in sections)}", ""]
        for s in sections:
            bullets = s["bullets"] or ["(无可用要点)"]
            lines += [f"## {s['title']}", "### 核心要点", *bullets, "",
                      "### 自测", f"- 用自己的话概括《{s['title']}》讲了什么?", "- 哪些结论有出处?分别在哪一页?", ""]
    markdown = "\n".join(lines)
    result: dict[str, Any] = {"template": template, "markdown": markdown, "sections": len(sections)}
    if save:
        page_title = title or f"{template}-{now_iso()[:16]}"
        entry = {"slug": slugify(page_title), "title": page_title, "kind": "compose",
                 "body": markdown, "note": f"compose({template})", "aliases": []}
        page_id, action = _write_page(conn, entry, origin="manual")
        _set_evidence(conn, page_id, used_pairs)
        _write_files(conn)
        _log("compose", entry["slug"], f"{template},{len(sections)} 份资料")
        result["saved_slug"] = entry["slug"]
        result["action"] = action
    return result


# ---------------------------------------------------------------- read APIs

def list_pages(conn: sqlite3.Connection) -> list[dict[str, Any]]:
    rows = conn.execute(
        "SELECT p.*, (SELECT COUNT(*) FROM wiki_evidence e WHERE e.page_id = p.id) AS evidence_count "
        "FROM wiki_pages p ORDER BY p.kind, p.slug"
    ).fetchall()
    return [dict(r) for r in rows]


def get_page(conn: sqlite3.Connection, slug: str) -> dict[str, Any] | None:
    page = conn.execute("SELECT * FROM wiki_pages WHERE slug = ?", (slug,)).fetchone()
    if page is None:
        return None
    data = dict(page)
    data["aliases"] = _page_aliases(page)
    data["evidence"] = [
        dict(r) for r in conn.execute(
            "SELECT e.*, c.page_start, c.page_end, s.title AS source_title, s.superseded "
            "FROM wiki_evidence e JOIN chunks c ON c.id = e.chunk_id "
            "JOIN sources s ON s.id = e.source_id WHERE e.page_id = ? ORDER BY c.chunk_index",
            (page["id"],),
        )
    ]
    data["claims"] = [
        dict(r) for r in conn.execute(
            "SELECT cl.id, cl.text, cl.confidence, cl.chunk_id, cl.source_id, c.page_start, c.page_end, s.title AS source_title "
            "FROM wiki_claims cl JOIN chunks c ON c.id = cl.chunk_id "
            "JOIN sources s ON s.id = cl.source_id WHERE cl.page_id = ? ORDER BY cl.created_at",
            (page["id"],),
        )
    ]
    data["memories"] = page_memories(conn, page)
    data["revisions"] = [
        dict(r) for r in conn.execute(
            "SELECT rev, note, created_at FROM wiki_revisions WHERE page_id = ? ORDER BY rev", (page["id"],)
        )
    ]
    data["links_out"] = sorted({slugify(m.strip()) for m in LINK_RE.findall(page["body"])})
    data["links_in"] = sorted(
        r["slug"] for r in conn.execute("SELECT slug, body FROM wiki_pages").fetchall()
        if r["slug"] != slug and slug in {slugify(m.strip()) for m in LINK_RE.findall(r["body"])}
    )
    return data


def pending_ops(conn: sqlite3.Connection) -> list[dict[str, Any]]:
    rows = conn.execute(
        "SELECT * FROM wiki_pending_ops WHERE status = 'pending' ORDER BY created_at"
    ).fetchall()
    return [dict(r) for r in rows]


def page_memories(conn: sqlite3.Connection, page: sqlite3.Row) -> list[dict[str, Any]]:
    """按 wiki 页面聚合相关记忆:标题/别名分词命中,或记忆来源与页面证据来源相同。"""
    terms: set[str] = set()
    for text in [page["title"], *_page_aliases(page)]:
        for part in re.split(r"[^\w\u4e00-\u9fff]+", text.lower()):
            if len(part) >= 2 and part not in STOP_ENTITIES:
                terms.add(part)
    src_ids = {
        r["source_id"] for r in conn.execute(
            "SELECT source_id FROM wiki_evidence WHERE page_id = ?", (page["id"],)
        )
    }
    matched: dict[str, dict[str, Any]] = {}
    for m in conn.execute("SELECT * FROM memories ORDER BY created_at DESC").fetchall():
        text = f"{m['title']} {m['body']}".lower()
        if (m["source_id"] and m["source_id"] in src_ids) or any(t in text for t in terms):
            matched[m["id"]] = dict(m)
    return list(matched.values())
