import json
import os
import subprocess
import sys
from pathlib import Path
import tempfile
import time
import unittest
import urllib.error
import urllib.request


class ProjectWorkflowTests(unittest.TestCase):
    def setUp(self):
        self.data_dir = tempfile.TemporaryDirectory()
        self.port = 48123
        env = {**os.environ, "PORT": str(self.port), "PERSONAL_AI_OS_DATA_DIR": self.data_dir.name}
        self.process = subprocess.Popen(
            [sys.executable, str(Path(__file__).resolve().parent.parent / "server.py")], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, env=env
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

    def post(self, path, payload):
        request = urllib.request.Request(
            f"http://127.0.0.1:{self.port}{path}",
            data=json.dumps(payload).encode(),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(request) as response:
            return json.loads(response.read())

    def test_project_note_task_resume_flow(self):
        project = self.post("/api/projects", {"name": "发布计划", "goal": "完成首个版本"})
        project_id = project["id"]
        note = self.post("/api/notes", {
            "title": "今天进展",
            "body": "决策: 保持本地优先\nTODO: 补齐发布检查",
            "project_id": project_id,
        })
        self.assertEqual(len(note["tasks"]), 1)
        detail = self.get(f"/api/projects/{project_id}")
        self.assertEqual(detail["project"]["counts"]["notes"], 1)
        self.assertEqual(detail["project"]["counts"]["tasks"], 1)
        self.assertEqual(detail["project"]["resume"]["next_step"], "补齐发布检查")
        self.assertEqual(detail["project"]["resume"]["decision"], "保持本地优先")


if __name__ == "__main__":
    unittest.main()
