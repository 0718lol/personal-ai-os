"""M2 知识编译层回归:页面生成/证据/幂等/待审 diff/回滚/lint。"""
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

HANDBOOK = """# 远帆科技员工手册(节选)

员工出差住宿报销标准:一线城市每晚 600 元以内,二线城市每晚 450 元以内,超支部分自理。
单笔报销金额超过 5000 元的,除直属主管审批外,还需要 CTO 会签后才能进入付款流程。
标准办公时间为 9:30 至 18:30;每周三为全员远程日。
"""

ATHENA_V1 = """# Athena 数据网关产品规格 v2.4

Athena 单节点标称吞吐为 35000 QPS,最大并发连接 2000。
"""

ATHENA_V2 = """# Athena 数据网关产品规格 v2.5

Athena 单节点标称吞吐为 52000 QPS,最大并发连接 2000。
"""


class WikiM2Tests(unittest.TestCase):
    def setUp(self):
        self.data_dir = tempfile.TemporaryDirectory()
        self.port = 48331
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

    def post(self, path, payload):
        request = urllib.request.Request(
            f"http://127.0.0.1:{self.port}{path}",
            data=json.dumps(payload).encode(),
            headers={"Content-Type": "application/json"}, method="POST",
        )
        with urllib.request.urlopen(request) as response:
            return json.loads(response.read())

    def upload(self, filename, content):
        boundary = "----m2testboundary"
        body = (
            f"--{boundary}\r\n"
            f'Content-Disposition: form-data; name="file"; filename="{filename}"\r\n'
            f"Content-Type: text/markdown\r\n\r\n"
        ).encode() + content.encode() + f"\r\n--{boundary}--\r\n".encode()
        request = urllib.request.Request(
            f"http://127.0.0.1:{self.port}/api/sources/upload", data=body,
            headers={"Content-Type": f"multipart/form-data; boundary={boundary}"}, method="POST",
        )
        with urllib.request.urlopen(request) as response:
            return json.loads(response.read())

    def wiki_dir(self):
        return Path(self.data_dir.name) / "wiki"

    def test_upload_generates_topic_entity_and_files(self):
        self.upload("员工手册.md", HANDBOOK)
        pages = {p["slug"]: p for p in self.get("/api/wiki/pages")}
        self.assertIn("员工手册.md", pages)
        self.assertEqual(pages["员工手册.md"]["kind"], "topic")
        self.assertIn("cto", pages)
        self.assertEqual(pages["cto"]["kind"], "entity")
        self.assertGreater(pages["cto"]["evidence_count"], 0)

        page = self.get("/api/wiki/pages/cto")
        self.assertTrue(page["evidence"])
        self.assertTrue(all(ev["quote"] for ev in page["evidence"]))
        self.assertIn("[[员工手册.md]]", page["body"])
        topic = self.get("/api/wiki/pages/员工手册.md")
        self.assertIn("[[cto]]", topic["body"])

        self.assertTrue((self.wiki_dir() / "index.md").exists())
        self.assertTrue((self.wiki_dir() / "log.md").exists())
        self.assertTrue((self.wiki_dir() / "cto.md").exists())
        index = (self.wiki_dir() / "index.md").read_text(encoding="utf-8")
        self.assertIn("[[cto]]", index)
        log = (self.wiki_dir() / "log.md").read_text(encoding="utf-8")
        self.assertIn("create", log)

    def test_rebuild_is_idempotent(self):
        self.upload("员工手册.md", HANDBOOK)
        changes = self.post("/api/wiki/rebuild", {"dry_run": True})["changes"]
        self.assertEqual([c for c in changes if c["action"] != "none"], [])

    def test_supersede_marks_stale_evidence_and_rebuild_prunes(self):
        self.upload("Athena产品规格.md", ATHENA_V1)
        self.upload("Athena产品规格.md", ATHENA_V2)
        lint = self.get("/api/wiki/lint")
        self.assertFalse(lint["clean"])
        self.assertIn("stale_evidence", lint["summary"])

        # 主题页应已是新版内容(slug 统一转小写)
        topic = self.get("/api/wiki/pages/athena产品规格.md")
        self.assertIn("52000", topic["body"])
        self.assertNotIn("35000", topic["body"])

        # rebuild 清理陈旧证据
        changes = self.post("/api/wiki/rebuild", {"dry_run": False})["changes"]
        lint2 = self.get("/api/wiki/lint")
        self.assertNotIn("stale_evidence", lint2["summary"])
        athena = self.get("/api/wiki/pages/athena")
        joined = " ".join(ev["quote"] for ev in athena["evidence"])
        self.assertNotIn("35000", joined)

    def test_propose_apply_rollback_flow(self):
        self.upload("员工手册.md", HANDBOOK)
        slug = "员工手册.md"
        original = self.get(f"/api/wiki/pages/{urllib.request.quote(slug)}")["body"]

        proposed = original + "\n## 补充\n\n参见 [[不存在的页面]]。\n"
        op = self.post("/api/wiki/propose", {"slug": slug, "body": proposed, "note": "补充章节"})
        self.assertEqual(op["op_type"], "update")
        self.assertIn("+## 补充", op["diff"])
        pending = self.get("/api/wiki/pending")
        self.assertEqual(len(pending), 1)

        # discard 不改正文
        self.post(f"/api/wiki/ops/{op['op_id']}/discard", {})
        self.assertEqual(self.get(f"/api/wiki/pages/{urllib.request.quote(slug)}")["body"], original)

        # apply 应用并生成快照
        op2 = self.post("/api/wiki/propose", {"slug": slug, "body": proposed, "note": "补充章节"})
        result = self.post(f"/api/wiki/ops/{op2['op_id']}/apply", {})
        self.assertEqual(result["status"], "applied")
        page = self.get(f"/api/wiki/pages/{urllib.request.quote(slug)}")
        self.assertIn("## 补充", page["body"])
        self.assertGreaterEqual(len(page["revisions"]), 2)

        # lint 发现断链
        lint = self.get("/api/wiki/lint")
        self.assertTrue(any(i["type"] == "broken_link" for i in lint["issues"]))

        # rollback 回到最初正文,且历史只增不删
        rev1 = page["revisions"][0]["rev"]
        rolled = self.post(f"/api/wiki/pages/{urllib.request.quote(slug)}/rollback", {"rev": rev1})
        self.assertEqual(rolled["action"], "update")
        page2 = self.get(f"/api/wiki/pages/{urllib.request.quote(slug)}")
        self.assertEqual(page2["body"], original)
        self.assertEqual(page2["revisions"][-1]["note"], f"回滚到 rev {rev1}")

    def test_dry_run_does_not_modify(self):
        self.upload("员工手册.md", HANDBOOK)
        before = self.get("/api/wiki/pages/员工手册.md")["body"]
        changes = self.post("/api/wiki/rebuild", {"dry_run": True})["changes"]
        after = self.get("/api/wiki/pages/员工手册.md")["body"]
        self.assertEqual(before, after)
        self.assertTrue(all(c["action"] == "none" for c in changes))

    def test_manual_pages_survive_rebuild(self):
        self.upload("员工手册.md", HANDBOOK)
        op = self.post("/api/wiki/propose", {"slug": "我的读书笔记", "title": "我的读书笔记", "body": "# 我的读书笔记\n\n手工页面。", "note": "手工"})
        self.post(f"/api/wiki/ops/{op['op_id']}/apply", {})
        self.post("/api/wiki/rebuild", {"dry_run": False})
        pages = {p["slug"] for p in self.get("/api/wiki/pages")}
        self.assertIn("我的读书笔记", pages)


if __name__ == "__main__":
    unittest.main()
