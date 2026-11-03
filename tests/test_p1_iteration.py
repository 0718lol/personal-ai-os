"""P1 迭代回归:别名合并、人工修订保护、ChangeSet、疑似矛盾、compose、损坏文件。"""
import json
import os
import subprocess
import sys
import tempfile
import time
import unittest
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ABSTAIN = "没有在当前资料库里找到"

HANDBOOK = """# 远帆科技员工手册(节选)

员工出差住宿报销标准:一线城市每晚 600 元以内,二线城市每晚 450 元以内,超支部分自理。
单笔报销金额超过 5000 元的,除直属主管审批外,还需要 CTO 会签。
"""

MEETING_03 = """# 2026 年 3 月经营会纪要

决策:H2 研发预算定为 1200 万元,优先投入网关与消息队列两条产品线。
"""

MEETING_04 = """# 2026 年 4 月经营会纪要

决策:H2 研发预算上调至 1500 万元,追加部分用于招聘。
"""

ATHENA_V1 = """# Athena 数据网关产品规格 v2.4

Athena 单节点标称吞吐为 35000 QPS,最大并发连接 2000。
"""

ATHENA_V2 = """# Athena 数据网关产品规格 v2.5

Athena 单节点标称吞吐为 52000 QPS,最大并发连接 2000。
"""


class P1IterationTests(unittest.TestCase):
    def setUp(self):
        self.data_dir = tempfile.TemporaryDirectory()
        self.port = 48531
        env = {**os.environ, "PORT": str(self.port), "PERSONAL_AI_OS_DATA_DIR": self.data_dir.name}
        self.process = subprocess.Popen(
            [sys.executable, str(ROOT / "server.py")], stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL, env=env,
        )
        for _ in range(50):
            try:
                self.get("/api/health")
                break
            except (urllib.error.URLError, ConnectionError):
                time.sleep(0.1)
        else:
            self.fail("server did not start")

    def tearDown(self):
        self.process.terminate()
        self.process.wait(timeout=5)
        self.data_dir.cleanup()

    def get(self, path):
        from urllib.parse import quote
        with urllib.request.urlopen(f"http://127.0.0.1:{self.port}{quote(path, safe='/?=&%')}") as response:
            return json.loads(response.read())

    def post(self, path, payload, expect_error=False):
        from urllib.parse import quote
        request = urllib.request.Request(
            f"http://127.0.0.1:{self.port}{quote(path, safe='/?=&%')}",
            data=json.dumps(payload).encode(),
            headers={"Content-Type": "application/json"}, method="POST",
        )
        try:
            with urllib.request.urlopen(request) as response:
                return json.loads(response.read())
        except urllib.error.HTTPError as exc:
            if expect_error:
                return {"status": exc.code, "body": json.loads(exc.read())}
            raise

    def upload(self, filename, content: bytes):
        boundary = "----p1boundary"
        ctype = "application/pdf" if filename.endswith(".pdf") else "text/markdown"
        body = (
            f"--{boundary}\r\n"
            f'Content-Disposition: form-data; name="file"; filename="{filename}"\r\n'
            f"Content-Type: {ctype}\r\n\r\n"
        ).encode() + content + f"\r\n--{boundary}--\r\n".encode()
        request = urllib.request.Request(
            f"http://127.0.0.1:{self.port}/api/sources/upload", data=body,
            headers={"Content-Type": f"multipart/form-data; boundary={boundary}"}, method="POST",
        )
        with urllib.request.urlopen(request) as response:
            return json.loads(response.read())

    def page(self, slug):
        return self.get(f"/api/wiki/pages/{slug}")

    # 1. 别名合并:证据并入目标页,源页变重定向存根,rebuild 不清理
    def test_alias_merge_creates_redirect_stub(self):
        self.upload("员工手册.md", HANDBOOK.encode("utf-8"))
        op = self.post("/api/wiki/propose", {"slug": "首席技术官", "title": "首席技术官",
                                             "body": "# 首席技术官\n\nCTO 的中文全称。\n", "note": "手工"})
        self.post(f"/api/wiki/ops/{op['op_id']}/apply", {})
        result = self.post("/api/wiki/pages/首席技术官/merge", {"into": "cto"})
        self.assertIn("首席技术官", result["aliases"])  # 来源页标题进入目标页别名表

        target = self.page("cto")
        self.assertIn("首席技术官", target["aliases"])
        stub = self.page("首席技术官")
        self.assertEqual(stub["origin"], "redirect")
        self.assertIn("[[cto]]", stub["body"])
        self.assertEqual(len(target["evidence"]), len(stub["evidence"]) + 1)  # 证据已并入目标(stub 至多剩 0-1 条)

        # rebuild 不得清理重定向页,也不得覆盖其正文
        changes = self.post("/api/wiki/rebuild", {"dry_run": False})["changes"]
        pages = {p["slug"] for p in self.get("/api/wiki/pages")}
        self.assertIn("首席技术官", pages)
        self.assertEqual(self.page("首席技术官")["origin"], "redirect")

    # 2. 人工修订保护:手工改过的页面不被后续编译覆盖,force 可越权
    def test_manual_protection_with_force_escape(self):
        self.upload("Athena产品规格.md", ATHENA_V1.encode("utf-8"))
        slug = "athena产品规格.md"
        original = self.page(slug)["body"]
        proposed = original + "\n## 人工备注\n\n此处为人工补充的采购结论。\n"
        op = self.post("/api/wiki/propose", {"slug": slug, "body": proposed, "note": "采购备注"})
        self.post(f"/api/wiki/ops/{op['op_id']}/apply", {})
        self.assertEqual(self.page(slug)["origin"], "manual")

        # 同名新版本导入:正文不得被覆盖
        self.upload("Athena产品规格.md", ATHENA_V2.encode("utf-8"))
        body = self.page(slug)["body"]
        self.assertIn("人工备注", body)

        # dry_run 报告 skipped
        changes = self.post("/api/wiki/rebuild", {"dry_run": True})["changes"]
        skipped = [c for c in changes if c["slug"] == slug and c["action"] == "skipped"]
        self.assertEqual(len(skipped), 1)

        # force 越权后恢复自动管理
        self.post("/api/wiki/rebuild", {"dry_run": False, "force": True})
        self.assertEqual(self.page(slug)["origin"], "auto")
        self.assertNotIn("人工备注", self.page(slug)["body"])

    # 3. ChangeSet:auto_apply 关闭时编译进待审,应用后生效;开启时自动应用且留审计
    def test_changeset_queue_and_auto_apply(self):
        self.post("/api/wiki/settings", {"auto_apply": False})
        self.assertEqual(self.get("/api/wiki/settings")["auto_apply"], False)

        self.upload("员工手册.md", HANDBOOK.encode("utf-8"))
        pending = self.get("/api/wiki/pending")
        compile_ops = [o for o in pending if o["source"] == "compile"]
        self.assertTrue(compile_ops, "auto_apply 关闭时应产生待审编译变更")
        self.assertTrue(any(o["slug"] == "员工手册.md" for o in compile_ops))
        self.assertTrue(all(o["diff_text"] for o in compile_ops))
        # 待审期间不应已生成页面
        self.assertNotIn("员工手册.md", {p["slug"] for p in self.get("/api/wiki/pages")})

        # 应用一条编译变更
        target = compile_ops[0]
        result = self.post(f"/api/wiki/ops/{target['id']}/apply", {})
        self.assertEqual(result["status"], "applied")
        self.assertIn("员工手册", self.page(target["slug"])["body"])
        self.assertIn(self.page(target["slug"])["kind"], ("topic", "entity"))

        # 恢复自动模式:上传后直接生成页面,且留 applied 级 ChangeSet(通过 pending 不含它验证)
        self.post("/api/wiki/settings", {"auto_apply": True})
        self.upload("2026-03经营会纪要.md", MEETING_03.encode("utf-8"))
        self.assertIn("2026-03经营会纪要.md", {p["slug"] for p in self.get("/api/wiki/pages")})
        still_pending = [o for o in self.get("/api/wiki/pending") if o["slug"] == "2026-03经营会纪要.md"]
        self.assertEqual(still_pending, [])

    def test_compile_update_can_be_reviewed_and_applied(self):
        self.upload("Athena产品规格.md", ATHENA_V1.encode())
        self.post("/api/wiki/settings", {"auto_apply": False})
        self.upload("Athena产品规格.md", ATHENA_V2.encode())
        ops = self.get("/api/wiki/pending")
        op = next(o for o in ops if o["slug"] == "athena产品规格.md" and o["op_type"] == "update")
        self.post(f"/api/wiki/ops/{op['id']}/apply", {})
        self.assertIn("52000", self.page(op["slug"])["body"])
        self.assertTrue(self.page(op["slug"])["evidence"])

    def test_stale_proposal_cannot_overwrite_newer_revision(self):
        self.upload("Athena产品规格.md", ATHENA_V1.encode())
        slug = "athena产品规格.md"
        old = self.post("/api/wiki/propose", {"slug": slug, "body": "旧提案"})
        newer = self.post("/api/wiki/propose", {"slug": slug, "body": "人工确认的新正文"})
        self.post(f"/api/wiki/ops/{newer['op_id']}/apply", {})
        result = self.post(f"/api/wiki/ops/{old['op_id']}/apply", {}, expect_error=True)
        self.assertEqual(result["status"], 400)
        self.assertEqual(self.page(slug)["body"], "人工确认的新正文")
        self.post(f"/api/wiki/ops/{old['op_id']}/discard", {})

    def test_pending_create_cannot_replace_existing_page(self):
        first = self.post("/api/wiki/propose", {"slug": "review-test", "body": "first"})
        second = self.post("/api/wiki/propose", {"slug": "review-test", "body": "second"})
        self.post(f"/api/wiki/ops/{first['op_id']}/apply", {})
        result = self.post(f"/api/wiki/ops/{second['op_id']}/apply", {}, expect_error=True)
        self.assertEqual(result["status"], 400)
        self.assertEqual(self.page("review-test")["body"], "first")

    # 4. 疑似矛盾 lint:同页不同来源、同单位、不同数值
    def test_suspected_conflict_detected(self):
        self.upload("2026-03经营会纪要.md", MEETING_03.encode("utf-8"))
        self.upload("2026-04经营会纪要.md", MEETING_04.encode("utf-8"))
        self.post("/api/wiki/rebuild", {"dry_run": False})
        lint = self.get("/api/wiki/lint")
        conflicts = [i for i in lint["issues"] if i["type"] == "suspected_conflict"]
        self.assertTrue(conflicts, "1200万 vs 1500万 应被标记为疑似矛盾")
        joined = " ".join(i["detail"] for i in conflicts)
        self.assertIn("1200", joined)
        self.assertIn("1500", joined)

    # 5. compose:抽取式生成提纲并保存为受保护页面
    def test_compose_generates_cited_draft(self):
        self.upload("员工手册.md", HANDBOOK.encode("utf-8"))
        result = self.post("/api/wiki/compose", {"slugs": ["员工手册.md"], "template": "outline",
                                                 "title": "报销制度提纲", "save": True})
        md = result["markdown"]
        self.assertIn("# 提纲:报销制度提纲", md)
        self.assertIn("## 员工手册.md", md)
        self.assertIn("[[员工手册.md]]", md)
        self.assertEqual(result["saved_slug"], "报销制度提纲")
        saved = self.page("报销制度提纲")
        self.assertEqual(saved["origin"], "manual")
        self.assertGreater(len(saved["evidence"]), 0)

    # 6. 损坏 PDF 与空文件:优雅降级,不 500
    def test_damaged_pdf_and_empty_file_degrade_gracefully(self):
        bad = self.upload("broken.pdf", b"%PDF-1.4 this is not a real pdf body")
        self.assertFalse(bad.get("duplicate"))
        self.assertIn(bad["source"]["status"], ("ready", "empty"))

        empty = self.upload("empty.md", b"")
        self.assertEqual(empty["source"]["status"], "empty")

        # 损坏文件不产生 wiki 主题页崩溃;页面列表仍可用
        pages = self.get("/api/wiki/pages")
        self.assertIsInstance(pages, list)

    # 7. 编译 ChangeSet 留痕:默认自动模式下,每次编译产生 applied 审计记录
    def test_changeset_audit_trail_on_auto(self):
        self.upload("员工手册.md", HANDBOOK.encode("utf-8"))
        # 审计记录不进 pending(已自动应用),但可直接查询 ops 历史:
        # 通过 propose+discard 验证 pending 端点只返回 pending;审计验证用 lint/页面足够,
        # 这里用数据库直查。
        import sqlite3
        db = sqlite3.connect(Path(self.data_dir.name) / "personal_ai_os.sqlite3")
        rows = db.execute(
            "SELECT status, source, op_type FROM wiki_pending_ops WHERE source='compile' AND slug='员工手册.md'"
        ).fetchall()
        db.close()
        self.assertTrue(rows)
        self.assertIn(("applied", "compile", "create"), rows)


if __name__ == "__main__":
    unittest.main()
