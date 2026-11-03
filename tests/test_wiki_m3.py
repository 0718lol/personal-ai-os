"""M3 知识层增强回归:lint 状态持久化 / 结论级 claim / 页面记忆聚合。"""
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


class WikiM3Tests(unittest.TestCase):
    def setUp(self):
        self.data_dir = tempfile.TemporaryDirectory()
        self.port = 48341
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
        boundary = "----m3testboundary"
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

    def _make_lint_issue(self):
        """制造一条断链提示:手工页面引用不存在的页面。"""
        op = self.post("/api/wiki/propose", {
            "slug": "断链测试页", "title": "断链测试页",
            "body": "# 断链测试页\n\n参见 [[不存在的页面]]。", "note": "制造断链",
        })
        self.post(f"/api/wiki/ops/{op['op_id']}/apply", {})
        lint = self.get("/api/wiki/lint")
        issues = [i for i in lint["issues"] if i["type"] == "broken_link"]
        self.assertTrue(issues)
        return issues[0]

    def test_lint_status_persist_and_restore(self):
        issue = self._make_lint_issue()
        self.assertEqual(issue["status"], "open")
        lint = self.get("/api/wiki/lint")
        self.assertGreaterEqual(lint["open_count"], 1)
        # 忽略后 open_count 下降,状态持久化
        result = self.post("/api/wiki/lint/status", {"key": issue["key"], "status": "ignored"})
        self.assertEqual(result["status"], "ignored")
        lint2 = self.get("/api/wiki/lint")
        target = next(i for i in lint2["issues"] if i["key"] == issue["key"])
        self.assertEqual(target["status"], "ignored")
        self.assertEqual(lint2["open_count"], lint["open_count"] - 1)
        # 恢复为 open
        self.post("/api/wiki/lint/status", {"key": issue["key"], "status": "open"})
        lint3 = self.get("/api/wiki/lint")
        target3 = next(i for i in lint3["issues"] if i["key"] == issue["key"])
        self.assertEqual(target3["status"], "open")
        self.assertEqual(lint3["open_count"], lint["open_count"])

    def test_lint_status_rejects_invalid_input(self):
        issue = self._make_lint_issue()
        with self.assertRaises(urllib.error.HTTPError) as ctx:
            self.post("/api/wiki/lint/status", {"key": issue["key"], "status": "bogus"})
        self.assertEqual(ctx.exception.code, 400)
        with self.assertRaises(urllib.error.HTTPError) as ctx:
            self.post("/api/wiki/lint/status", {"key": "not-exist|xxx|yyy", "status": "ignored"})
        self.assertEqual(ctx.exception.code, 400)

    def test_page_claims_generated_with_confidence(self):
        self.upload("员工手册.md", HANDBOOK)
        page = self.get("/api/wiki/pages/员工手册.md")
        self.assertTrue(page["claims"])
        for claim in page["claims"]:
            self.assertIn(claim["confidence"], {"high", "medium", "low"})
            self.assertTrue(claim["text"])
            self.assertTrue(claim["source_title"])
        # 数值+单位句应产生 high 置信 claim
        self.assertTrue(any(c["confidence"] == "high" for c in page["claims"]))

    def test_page_memories_aggregation(self):
        self.upload("员工手册.md", HANDBOOK)
        # 与页面标题相关的记忆应被聚合
        self.post("/api/memories", {
            "title": "报销制度记忆", "body": "员工手册规定一线城市住宿每晚 600 元以内。",
            "status": "approved", "memory_type": "fact",
        })
        # 无关记忆不应出现
        self.post("/api/memories", {
            "title": "无关记忆", "body": "今天天气不错,适合散步。",
            "status": "approved", "memory_type": "fact",
        })
        result = self.get("/api/wiki/pages/员工手册.md/memories")
        self.assertEqual(result["slug"], "员工手册.md")
        titles = [m["title"] for m in result["memories"]]
        self.assertIn("报销制度记忆", titles)
        self.assertNotIn("无关记忆", titles)
        # 页面详情同样携带 memories
        page = self.get("/api/wiki/pages/员工手册.md")
        page_titles = [m["title"] for m in page["memories"]]
        self.assertIn("报销制度记忆", page_titles)

    def test_page_memories_404_for_missing_page(self):
        with self.assertRaises(urllib.error.HTTPError) as ctx:
            self.get("/api/wiki/pages/不存在的页面/memories")
        self.assertEqual(ctx.exception.code, 404)


if __name__ == "__main__":
    unittest.main()
