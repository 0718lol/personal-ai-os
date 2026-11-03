"""只读 MCP server 回归:initialize / tools/list / tools/call 基本行为与只读约束。"""
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


class McpServerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        env = dict(os.environ, PERSONAL_AI_OS_DATA_DIR=cls.tmp.name)
        # 通过 server 的导入路径初始化数据库 schema
        subprocess.run(
            [sys.executable, "-c", "import server; server.ensure_db()"],
            cwd=ROOT, env=env, check=True, capture_output=True,
        )
        cls.env = env

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def _rpc(self, messages):
        proc = subprocess.run(
            [sys.executable, "mcp_server.py"],
            cwd=ROOT,
            input="".join(json.dumps(m) + "\n" for m in messages),
            capture_output=True,
            text=True,
            env=self.env,
            timeout=60,
        )
        self.assertEqual(proc.returncode, 0, proc.stderr)
        return [json.loads(line) for line in proc.stdout.splitlines() if line.strip()]

    def test_initialize_and_list_tools(self):
        responses = self._rpc([
            {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}},
            {"jsonrpc": "2.0", "method": "notifications/initialized"},
            {"jsonrpc": "2.0", "id": 2, "method": "tools/list"},
        ])
        by_id = {r["id"]: r for r in responses}
        self.assertIn("result", by_id[1])
        self.assertEqual(by_id[1]["result"]["serverInfo"]["name"], "personal-ai-os-readonly")
        tools = by_id[2]["result"]["tools"]
        self.assertEqual(
            sorted(t["name"] for t in tools),
            ["wiki_lint", "wiki_list_pages", "wiki_read_page", "wiki_search"],
        )

    def test_list_pages_and_lint_on_empty_db(self):
        responses = self._rpc([
            {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}},
            {"jsonrpc": "2.0", "id": 2, "method": "tools/call", "params": {"name": "wiki_list_pages", "arguments": {}}},
            {"jsonrpc": "2.0", "id": 3, "method": "tools/call", "params": {"name": "wiki_lint", "arguments": {}}},
        ])
        by_id = {r["id"]: r for r in responses}
        self.assertEqual(json.loads(by_id[2]["result"]["content"][0]["text"]), [])
        lint = json.loads(by_id[3]["result"]["content"][0]["text"])
        self.assertIn("issues", lint)

    def test_read_missing_page_returns_error_result(self):
        responses = self._rpc([
            {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}},
            {"jsonrpc": "2.0", "id": 2, "method": "tools/call", "params": {"name": "wiki_read_page", "arguments": {"slug": "no-such-page"}}},
        ])
        result = next(r for r in responses if r.get("id") == 2)["result"]
        self.assertTrue(result.get("isError"))
        self.assertIn("不存在", result["content"][0]["text"])

    def test_unknown_tool_and_method(self):
        responses = self._rpc([
            {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}},
            {"jsonrpc": "2.0", "id": 2, "method": "tools/call", "params": {"name": "write_something", "arguments": {}}},
            {"jsonrpc": "2.0", "id": 3, "method": "bogus/method"},
        ])
        by_id = {r["id"]: r for r in responses}
        self.assertTrue(by_id[2]["result"].get("isError"))
        self.assertEqual(by_id[3]["error"]["code"], -32601)


if __name__ == "__main__":
    unittest.main()
