"""M1 检索层回归:中文召回、拒答门控、版本化更新、索引回填。"""
import json
import os
import sqlite3
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
出差期间餐补为每日 100 元,不需要提供发票。
标准办公时间为 9:30 至 18:30;每周三为全员远程日。
"""

ATHENA_V1 = """# Athena 数据网关产品规格 v2.4

Athena 数据网关单节点最大并发连接数为 2000,单节点标称吞吐为 35000 QPS。
认证方式:支持 OIDC 与服务账号两种方式;不支持 LDAP。
"""

ATHENA_V2 = """# Athena 数据网关产品规格 v2.5

Athena 数据网关单节点最大并发连接数为 2000,单节点标称吞吐为 52000 QPS。
认证方式:支持 OIDC 与服务账号两种方式;不支持 LDAP。
"""


class RetrievalM1Tests(unittest.TestCase):
    def setUp(self):
        self.data_dir = tempfile.TemporaryDirectory()
        self.port = 48231
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
        with urllib.request.urlopen(f"http://127.0.0.1:{self.port}{path}") as response:
            return json.loads(response.read())

    def post_json(self, path, payload):
        request = urllib.request.Request(
            f"http://127.0.0.1:{self.port}{path}",
            data=json.dumps(payload).encode(),
            headers={"Content-Type": "application/json"}, method="POST",
        )
        with urllib.request.urlopen(request) as response:
            return json.loads(response.read())

    def upload(self, filename, content):
        boundary = "----m1testboundary"
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

    def chat(self, question):
        return self.post_json("/api/chat", {"question": question})

    def search(self, q):
        return self.get(f"/api/search?limit=12&q={urllib.request.quote(q)}")["results"]

    def _db(self):
        return sqlite3.connect(Path(self.data_dir.name) / "personal_ai_os.sqlite3")

    def test_chinese_question_retrieves_and_cites(self):
        self.upload("员工手册.md", HANDBOOK)
        result = self.chat("一线城市出差住宿报销上限是多少?")
        self.assertNotIn(ABSTAIN, result["answer"])
        self.assertTrue(result["citations"], "应当有引用")
        self.assertEqual(result["citations"][0]["title"], "员工手册.md")
        texts = result["answer"] + " ".join(c["snippet"] for c in result["citations"])
        self.assertIn("600", texts)

    def test_unknown_term_abstains_without_citations(self):
        self.upload("员工手册.md", HANDBOOK)
        result = self.chat("Athena 的官方定价是多少?")
        self.assertIn(ABSTAIN, result["answer"])
        self.assertEqual(result["citations"], [])

    def test_weak_overlap_question_is_not_confident(self):
        self.upload("员工手册.md", HANDBOOK)
        result = self.chat("公司现在一共有多少名员工?")
        # 三档语义:弱相关不得以 confident 档回答,只能是低置信(带免责)或硬拒答
        self.assertNotEqual(result.get("confidence"), "confident")
        self.assertTrue("低置信" in result["answer"] or ABSTAIN in result["answer"])

    def test_exact_substring_like_fallback_still_answers(self):
        self.upload("员工手册.md", HANDBOOK)
        result = self.chat("标准办公时间为 9:30 至 18:30")
        self.assertNotIn(ABSTAIN, result["answer"])
        self.assertTrue(result["citations"])

    def test_same_name_update_supersedes_old_version(self):
        self.upload("Athena产品规格.md", ATHENA_V1)
        result = self.upload("Athena产品规格.md", ATHENA_V2)
        self.assertFalse(result.get("duplicate"))
        sources = self.get("/api/sources")
        athena = [s for s in sources if s["title"] == "Athena产品规格.md"]
        self.assertEqual(len(athena), 2)
        superseded = [s for s in athena if s.get("superseded")]
        self.assertEqual(len(superseded), 1)

        hits = self.search("Athena 单节点标称吞吐是多少 QPS?")
        joined = " ".join(h["content"] for h in hits)
        self.assertIn("52000", joined)
        self.assertNotIn("35000", joined)

        chat = self.chat("Athena 单节点标称吞吐是多少 QPS?")
        evidence = chat["answer"] + " ".join(c["snippet"] for c in chat["citations"])
        self.assertIn("52000", evidence)
        self.assertNotIn("35000", evidence)

    def test_indexes_backfilled_for_every_chunk(self):
        self.upload("员工手册.md", HANDBOOK)
        with self._db() as conn:
            chunks = conn.execute("SELECT COUNT(*) FROM chunks").fetchone()[0]
            bigrams = conn.execute("SELECT COUNT(*) FROM chunks_bigram").fetchone()[0]
            vectors = conn.execute("SELECT COUNT(*) FROM chunk_vectors").fetchone()[0]
            empty_hash = conn.execute(
                "SELECT COUNT(*) FROM chunks WHERE content_hash = '' OR content_hash IS NULL"
            ).fetchone()[0]
        self.assertGreater(chunks, 0)
        self.assertEqual(bigrams, chunks)
        self.assertEqual(vectors, chunks)
        self.assertEqual(empty_hash, 0)

    def test_duplicate_import_still_idempotent(self):
        first = self.upload("员工手册.md", HANDBOOK)
        second = self.upload("员工手册.md", HANDBOOK)
        self.assertFalse(first.get("duplicate"))
        self.assertTrue(second.get("duplicate"))

    def test_delete_source_cleans_indexes(self):
        uploaded = self.upload("员工手册.md", HANDBOOK)
        source_id = uploaded["source"]["id"]
        request = urllib.request.Request(
            f"http://127.0.0.1:{self.port}/api/sources/{source_id}", method="DELETE"
        )
        with urllib.request.urlopen(request) as response:
            json.loads(response.read())
        with self._db() as conn:
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM chunks_bigram").fetchone()[0], 0)
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM chunk_vectors").fetchone()[0], 0)


if __name__ == "__main__":
    unittest.main()
