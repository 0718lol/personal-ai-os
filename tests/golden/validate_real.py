#!/usr/bin/env python3
"""真实语料验证:导入指定 PDF/文件,跑真实用例,输出 wiki 页面、lint 与检索/问答指标。

用法:
  .venv/bin/python tests/golden/validate_real.py <文件路径...>
结果写入 tests/golden/real_results.json。
"""
from __future__ import annotations

import json
import sys
import time
import urllib.request
from datetime import datetime
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from run_baseline import Server, import_bytes  # noqa: E402

PORT = int(__import__("os").environ.get("BASELINE_PORT", "48778"))
SERVER = Server.__new__(Server)  # 占位,main 里真正初始化


def main() -> None:
    files = [Path(p) for p in sys.argv[1:]]
    if not files:
        raise SystemExit("用法: validate_real.py <文件路径...>")
    for f in files:
        if not f.exists():
            raise SystemExit(f"文件不存在: {f}")

    server = Server()
    try:
        title_map = {}
        for f in files:
            resp = import_bytes(server, f.name, f.read_bytes())
            title_map[f.name] = resp["source"]["title"]
            status = "duplicate" if resp.get("duplicate") else "imported"
            print(f"导入[{status}]: {f.name}")

        # wiki 状态
        pages = server.get("/api/wiki/pages")
        lint = server.get("/api/wiki/lint")
        print(f"\nwiki 页面 {len(pages)} 个;lint: {'干净' if lint['clean'] else lint['summary']}")

        cases = json.loads((HERE / "real_cases_resume.json").read_text(encoding="utf-8"))["cases"]
        records = []
        for case in cases:
            q = case["question"]
            search = server.get(f"/api/search?limit=12&q={urllib.request.quote(q)}")["results"]
            chat = server.post("/api/chat", {"question": q})
            answer = chat.get("answer", "")
            citations = chat.get("citations", [])
            abstained = "没有在当前资料库里找到" in answer or not citations
            kw_in = any(k in answer + " ".join(c.get("snippet", "") for c in citations) for k in case["any_keywords"])
            records.append({
                "id": case["id"], "category": case["category"], "question": q,
                "top1": search[0]["title"] if search else "",
                "abstained": abstained, "kw_hit": kw_in,
                "n_citations": len(citations),
                "top_citation": citations[0]["title"] if citations else "",
            })
            time.sleep(0.02)

        facts = [r for r in records if r["category"] == "fact_single"]
        noans = [r for r in records if r["category"] == "no_answer"]
        metrics = {
            "fact_kw_hit": round(sum(1 for r in facts if r["kw_hit"]) / max(len(facts), 1), 3),
            "no_answer_correct_abstain": round(sum(1 for r in noans if r["abstained"]) / max(len(noans), 1), 3),
        }
        out = {
            "run_at": datetime.now().isoformat(timespec="seconds"),
            "files": [f.name for f in files],
            "metrics": metrics,
            "wiki_pages": [{"slug": p["slug"], "kind": p["kind"], "evidence": p["evidence_count"]} for p in pages],
            "lint": {"clean": lint["clean"], "summary": lint["summary"]},
            "records": records,
        }
        (HERE / "real_results.json").write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
        print(json.dumps(metrics, ensure_ascii=False))
        for r in records:
            flag = "PASS" if (r["kw_hit"] if r["category"] == "fact_single" else r["abstained"]) else "FAIL"
            print(f"{flag} {r['id']} top1={r['top1'][:22]!r} {r['question']}")
        print("\n结果已写入 tests/golden/real_results.json")
    finally:
        server.stop()


if __name__ == "__main__":
    main()
