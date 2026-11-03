"""An upload success response must not escape before its DB transaction commits."""
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# Run in a separate interpreter so importing server cannot touch a user's data.
CHECK = r'''
import io
import json
import sqlite3
from contextlib import contextmanager
from unittest.mock import patch
import server

server.ensure_db()
original_connect = server.connect
pending_transaction = False

@contextmanager
def tracked_connect():
    global pending_transaction
    with original_connect() as conn:
        pending_transaction = True
        try:
            yield conn
        finally:
            pending_transaction = False

def upload():
    boundary = "commit-test-boundary"
    content = "# 手册\n\nAthena 支持每晚 600 元的住宿报销。".encode()
    body = (f'--{boundary}\r\nContent-Disposition: form-data; name="file"; '
            'filename="手册.md"\r\nContent-Type: text/markdown\r\n\r\n').encode()
    body += content + f'\r\n--{boundary}--\r\n'.encode()
    handler = server.Handler.__new__(server.Handler)
    handler.headers = {"content-type": f"multipart/form-data; boundary={boundary}",
                       "content-length": str(len(body))}
    handler.rfile = io.BytesIO(body)
    responses = []
    def capture(handler, payload, *args):
        assert not pending_transaction, "response sent while transaction is still open"
        with sqlite3.connect(server.DB_PATH) as reader:
            source_id = payload["source"]["id"]
            assert reader.execute("SELECT COUNT(*) FROM sources WHERE id=?", (source_id,)).fetchone()[0] == 1
            assert reader.execute("SELECT COUNT(*) FROM chunks WHERE source_id=?", (source_id,)).fetchone()[0] > 0
            assert reader.execute("SELECT COUNT(*) FROM wiki_pages").fetchone()[0] > 0
        responses.append(payload)
    with patch.object(server, "connect", tracked_connect), patch.object(server, "json_response", capture):
        handler.upload_source()
    return responses[0]

first = upload()
second = upload()
assert first["duplicate"] is False
assert second["duplicate"] is True
assert first["source"]["id"] == second["source"]["id"]
'''


class UploadCommitTests(unittest.TestCase):
    def test_new_and_duplicate_upload_respond_only_after_commit(self):
        with tempfile.TemporaryDirectory() as data_dir:
            result = subprocess.run(
                [sys.executable, "-c", CHECK], cwd=ROOT,
                env={**os.environ, "PERSONAL_AI_OS_DATA_DIR": data_dir},
                capture_output=True, text=True, timeout=30,
            )
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
