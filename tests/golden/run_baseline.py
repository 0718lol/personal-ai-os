#!/usr/bin/env python3
"""M0 基线评测:隔离数据目录启动服务,导入合成语料,运行黄金测试集,输出基线指标。

用法: .venv/bin/python tests/golden/run_baseline.py
输出: tests/golden/baseline_results.json 与 tests/golden/BASELINE.md
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
from datetime import datetime
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent
FIXTURES = HERE / "fixtures"
PORT = int(os.environ.get("BASELINE_PORT", "48777"))
BASE = f"http://127.0.0.1:{PORT}"
ABSTAIN_MARKER = "没有在当前资料库里找到"

BASELINE_DOCS = [
    ("员工手册.md", "text/markdown"),
    ("Athena产品规格.md", "text/markdown"),
    ("Hermes产品规格.md", "text/markdown"),
    ("2026-03经营会纪要.md", "text/markdown"),
    ("2026-04经营会纪要.md", "text/markdown"),
    ("RAG评测研究笔记.md", "text/markdown"),
    ("平台FAQ.md", "text/markdown"),
    ("新人入职指南.pdf", "application/pdf"),
    ("2025年度报告草稿.pdf", "application/pdf"),
    ("2025季度经营指标.csv", "text/csv"),
]


def multipart(filename: str, content: bytes, ctype: str) -> tuple[bytes, dict[str, str]]:
    boundary = "----goldenBoundary7f3a9c1d"
    body = bytearray()
    body += f"--{boundary}\r\n".encode()
    body += f'Content-Disposition: form-data; name="file"; filename="{filename}"\r\n'.encode()
    body += f"Content-Type: {ctype}\r\n\r\n".encode()
    body += content
    body += b"\r\n"
    body += f"--{boundary}--\r\n".encode()
    return bytes(body), {"Content-Type": f"multipart/form-data; boundary={boundary}"}


class Server:
    def __init__(self) -> None:
        self.data_dir = tempfile.mkdtemp(prefix="paios-baseline-")
        env = {**os.environ, "PORT": str(PORT), "PERSONAL_AI_OS_DATA_DIR": self.data_dir}
        self.log_file = open(HERE / "server_run.log", "w", encoding="utf-8")
        self.proc = subprocess.Popen(
            [sys.executable, str(ROOT / "server.py")],
            env=env, stdout=self.log_file, stderr=subprocess.STDOUT,
        )
        for _ in range(100):
            try:
                self.get("/api/health")
                return
            except Exception:
                time.sleep(0.2)
        raise RuntimeError("服务未能在 20 秒内启动,详见 tests/golden/server_run.log")

    def get(self, path: str) -> dict:
        with urllib.request.urlopen(f"{BASE}{path}", timeout=30) as resp:
            return json.loads(resp.read())

    def post(self, path: str, payload: dict) -> dict:
        req = urllib.request.Request(
            f"{BASE}{path}", data=json.dumps(payload).encode(),
            headers={"Content-Type": "application/json"}, method="POST",
        )
        with urllib.request.urlopen(req, timeout=60) as resp:
            return json.loads(resp.read())

    def stop(self) -> None:
        self.proc.terminate()
        try:
            self.proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            self.proc.kill()
        self.log_file.close()


def import_bytes(server: Server, filename: str, content: bytes) -> dict:
    ctype = "application/pdf" if filename.endswith(".pdf") else ("text/csv" if filename.endswith(".csv") else "text/markdown")
    body, headers = multipart(filename, content, ctype)
    req = urllib.request.Request(f"{BASE}/api/sources/upload", data=body, headers=headers, method="POST")
    with urllib.request.urlopen(req, timeout=60) as resp:
        return json.loads(resp.read())


def import_doc(server: Server, name: str) -> dict:
    return import_bytes(server, name, (FIXTURES / name).read_bytes())


def run_retrieval_case(server: Server, case: dict, title_map: dict[str, str]) -> dict:
    question = case["question"]
    search = server.get(f"/api/search?limit=12&q={urllib.request.quote(question)}")
    results = search.get("results", [])
    titles = [r["title"] for r in results]
    expected_titles = {title_map[d] for d in case.get("expected_docs", [])}
    top5_hit = any(t in expected_titles for t in titles[:5]) if expected_titles else None
    top12_hit = any(t in expected_titles for t in titles) if expected_titles else None

    chat = server.post("/api/chat", {"question": question})
    answer = chat.get("answer", "")
    citations = chat.get("citations", [])
    tier = chat.get("confidence", "confident")
    cite_titles = [c.get("title", "") for c in citations]
    cite_hit = any(t in expected_titles for t in cite_titles) if expected_titles else None
    cite_both = all(t in cite_titles for t in expected_titles) if len(expected_titles) > 1 else None

    kws = case.get("any_keywords", [])
    kw_in_answer = any(k in answer for k in kws) if kws else None
    cite_text = " ".join(c.get("snippet", "") for c in citations)
    kw_in_evidence = any(k in answer + cite_text for k in kws) if kws else None

    abstained = ABSTAIN_MARKER in answer or not citations
    record = {
        "id": case["id"], "category": case["category"], "question": question,
        "search_top5_hit": top5_hit, "search_top12_hit": top12_hit,
        "search_top1_title": titles[0] if titles else "",
        "citation_hit": cite_hit, "citations_cover_both": cite_both,
        "kw_in_answer": kw_in_answer, "kw_in_evidence": kw_in_evidence,
        "abstained": abstained, "tier": tier, "n_citations": len(citations),
    }
    if case["category"] == "no_answer":
        record["correct_abstain"] = abstained
        record["junk_citation"] = bool(citations) and tier == "confident"
        record["any_citation"] = bool(citations)
    if case["category"] == "conflict":
        markers = case.get("conflict_markers", [])
        record["conflict_surfaced"] = all(m in answer + cite_text for m in markers)
    return record


def ops_dedup(server: Server, title_map: dict[str, str]) -> list[dict]:
    out: list[dict] = []

    def chunk_count(title: str) -> int:
        sources = server.get("/api/sources")
        match = [s for s in sources if s["title"] == title]
        if not match:
            return -1
        detail = server.get(f"/api/sources/{match[0]['id']}")
        return len(detail.get("chunks", []))

    # OP01 完全重复导入
    before = chunk_count(title_map["员工手册.md"])
    dup = import_doc(server, "员工手册.md")
    after = chunk_count(title_map["员工手册.md"])
    out.append({
        "id": "OP01", "name": "重复导入同一文件",
        "duplicate_flag": dup.get("duplicate"),
        "chunk_count_unchanged": before == after,
        "pass": bool(dup.get("duplicate")) and before == after,
    })

    # OP02 同内容不同文件名
    dup2 = import_doc(server, "员工手册-副本.md")
    sources = server.get("/api/sources")
    handbook_sources = [s for s in sources if "员工手册" in s["title"]]
    out.append({
        "id": "OP02", "name": "相同内容改名导入",
        "duplicate_flag": dup2.get("duplicate"),
        "source_count_with_same_content": len(handbook_sources),
        "pass": bool(dup2.get("duplicate")) and len(handbook_sources) == 1,
    })
    return out


def ops_update(server: Server, title_map: dict[str, str]) -> list[dict]:
    out: list[dict] = []

    # OP03 同名资料内容更新(旧版应被取代/标记,当前行为待记录)
    sources_before = server.get("/api/sources")
    v2_content = (FIXTURES / "Athena产品规格.v2.md").read_bytes()
    upd = import_bytes(server, "Athena产品规格.md", v2_content)
    sources_after = server.get("/api/sources")
    athena_sources = [s for s in sources_after if "Athena产品规格" in s["title"]]
    out.append({
        "id": "OP03", "name": "同名资料内容更新",
        "duplicate_flag": upd.get("duplicate"),
        "athena_source_count_before": len([s for s in sources_before if "Athena产品规格" in s["title"]]),
        "athena_source_count_after": len(athena_sources),
        "old_marked_superseded": any(s.get("superseded") for s in athena_sources),
        "pass": None,  # 记录行为,不做 pass/fail 判定
    })

    # OP04/OP05 更新后的检索:新值与旧值哪个被返回
    q = "Athena 单节点标称吞吐是多少 QPS?"
    r1 = server.get(f"/api/search?limit=12&q={urllib.request.quote(q)}")
    tops = [(x["title"], x["content"][:200]) for x in r1.get("results", [])[:3]]
    old_found = any("35000" in c for _, c in tops)
    new_found = any("52000" in c for _, c in tops)
    chat = server.post("/api/chat", {"question": q})
    out.append({
        "id": "OP04", "name": "更新后检索返回新旧哪个版本",
        "old_version_in_top3": old_found, "new_version_in_top3": new_found,
        "old_in_chat_evidence": any("35000" in c.get("snippet", "") for c in chat.get("citations", [])),
        "new_in_chat_evidence": any("52000" in c.get("snippet", "") for c in chat.get("citations", [])),
        "pass": None,
    })
    q2 = "Athena 从哪个版本开始支持 Kafka 数据源?"
    chat2 = server.post("/api/chat", {"question": q2})
    out.append({
        "id": "OP05", "name": "更新后版本号问题的新旧证据",
        "citations": [c.get("snippet", "")[:120] for c in chat2.get("citations", [])[:3]],
        "pass": None,
    })
    return out


def summarize(records: list[dict], ops: list[dict]) -> dict:
    def rate(items: list[dict], key: str) -> float | None:
        vals = [r[key] for r in items if r.get(key) is not None]
        return round(sum(1 for v in vals if v) / len(vals), 3) if vals else None

    by_cat: dict[str, list[dict]] = {}
    for r in records:
        by_cat.setdefault(r["category"], []).append(r)

    summary: dict[str, dict] = {}
    for cat, items in by_cat.items():
        summary[cat] = {
            "n": len(items),
            "search_top5_hit": rate(items, "search_top5_hit"),
            "citation_hit": rate(items, "citation_hit"),
            "kw_in_answer": rate(items, "kw_in_answer"),
            "kw_in_evidence": rate(items, "kw_in_evidence"),
        }
    if "no_answer" in summary:
        summary["no_answer"]["correct_abstain"] = rate(by_cat["no_answer"], "abstained")
        summary["no_answer"]["answered_with_citations"] = rate(by_cat["no_answer"], "any_citation")
        summary["no_answer"]["low_tier_answered"] = round(
            sum(1 for r in by_cat["no_answer"] if r.get("tier") == "low") / len(by_cat["no_answer"]), 3)
        summary["no_answer"]["junk_citation"] = round(
            sum(1 for r in by_cat["no_answer"] if r.get("n_citations", 0) > 0 and r.get("tier") == "confident") / len(by_cat["no_answer"]), 3)
    if "conflict" in summary:
        summary["conflict"]["conflict_surfaced"] = rate(by_cat["conflict"], "conflict_surfaced")
    overall = {
        "search_top5_hit": rate(records, "search_top5_hit"),
        "citation_hit": rate(records, "citation_hit"),
        "kw_in_answer": rate(records, "kw_in_answer"),
    }
    return {"overall": overall, "by_category": summary}


def write_report(summary: dict, records: list[dict], ops: list[dict], title_map: dict, out_json: Path, out_md: Path) -> None:
    failures = [r for r in records if r["category"] == "fact_single" and not (r["citation_hit"] and r["kw_in_evidence"])]
    cross_fails = [r for r in records if r["category"] == "fact_cross" and not r.get("citations_cover_both")]
    lines = [
        "# 当前版本检索评测报告",
        "",
        f"- 运行时间:{datetime.now().isoformat(timespec='seconds')}",
        f"- 黄金集:55 个评测用例 + 5 个操作性用例(tests/golden/golden_cases.json)",
        f"- 环境:隔离数据目录,无模型 API key(走 local_answer 降级路径)",
        "",
        "## 总体指标",
        "",
        "| 指标 | 数值 |",
        "|---|---|",
    ]
    for k, v in summary["overall"].items():
        lines.append(f"| {k} | {v} |")
    lines += ["", "## 分类别指标", "", "| 类别 | n | search@5 | citation_hit | kw_in_answer | kw_in_evidence | 附加 |", "|---|---|---|---|---|---|---|"]
    for cat, s in summary["by_category"].items():
        extra = []
        for k in ("correct_abstain", "low_tier_answered", "answered_with_citations", "junk_citation", "conflict_surfaced"):
            if k in s:
                extra.append(f"{k}={s[k]}")
        lines.append(f"| {cat} | {s['n']} | {s['search_top5_hit']} | {s['citation_hit']} | {s['kw_in_answer']} | {s['kw_in_evidence']} | {', '.join(extra)} |")
    lines += ["", "## 操作性用例(导入/更新行为)", "", "| id | 名称 | 关键观察 | pass |", "|---|---|---|---|"]
    for o in ops:
        obs = {k: v for k, v in o.items() if k not in ("id", "name", "pass")}
        lines.append(f"| {o['id']} | {o['name']} | `{json.dumps(obs, ensure_ascii=False)}` | {o.get('pass')} |")
    lines += ["", f"## fact_single 未达标用例({len(failures)} 条)", ""]
    for r in failures:
        lines.append(f"- {r['id']} `{r['question']}` top1={r['search_top1_title']!r} abstained={r['abstained']}")
    lines += ["", f"## fact_cross 引用未覆盖全部文档({len(cross_fails)} 条)", ""]
    for r in cross_fails:
        lines.append(f"- {r['id']} `{r['question']}`")
    out_md.write_text("\n".join(lines) + "\n", encoding="utf-8")
    out_json.write_text(json.dumps({
        "summary": summary, "records": records, "ops": ops, "title_map": title_map,
    }, ensure_ascii=False, indent=2), encoding="utf-8")


def main() -> None:
    server = Server()
    try:
        title_map: dict[str, str] = {}
        for name, _ctype in BASELINE_DOCS:
            resp = import_doc(server, name)
            title_map[name] = resp["source"]["title"]
        print("导入完成:", {k: v for k, v in title_map.items()})

        ops: list[dict] = []
        # 先做重复导入两项(在全部评测前,不污染评测状态)
        ops += ops_dedup(server, title_map)
        records = []
        cases = json.loads((HERE / "golden_cases.json").read_text(encoding="utf-8"))["cases"]
        for case in cases:
            records.append(run_retrieval_case(server, case, title_map))
        # 更新行为放到评测之后,再复测受影响的查询
        ops += ops_update(server, title_map)

        summary = summarize(records, ops)
        out_json = HERE / "baseline_results.json"
        out_md = HERE / "BASELINE.md"
        write_report(summary, records, ops, title_map, out_json, out_md)
        print(json.dumps(summary, ensure_ascii=False, indent=2))
        print(f"\n报告已写入: {out_md.name}, {out_json.name}")
    finally:
        server.stop()


if __name__ == "__main__":
    main()
