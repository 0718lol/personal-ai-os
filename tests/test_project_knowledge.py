"""Knowledge retrieval, document heads and model waits across project boundaries."""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parent.parent

CHECK = r'''
import io
import json
import sqlite3
import threading
import urllib.request
from unittest.mock import patch
import server
import mcp_server

server.ensure_db()
server.Handler.log_message = lambda *a: None
httpd = server.ThreadingHTTPServer(('127.0.0.1', 0), server.Handler)
threading.Thread(target=httpd.serve_forever, daemon=True).start()
base = f'http://127.0.0.1:{httpd.server_port}'
def post(path, payload):
    request = urllib.request.Request(base + path, data=json.dumps(payload).encode(), headers={'Content-Type': 'application/json'})
    with urllib.request.urlopen(request, timeout=10) as response:
        return json.load(response)
def upload(project, text):
    boundary = 'project-knowledge-test'
    body = (f'--{boundary}\r\nContent-Disposition: form-data; name="project_id"\r\n\r\n{project}\r\n'
            f'--{boundary}\r\nContent-Disposition: form-data; name="file"; filename="requirements.md"\r\nContent-Type: text/markdown\r\n\r\n{text}\r\n--{boundary}--\r\n').encode()
    request = urllib.request.Request(base + '/api/sources/upload', data=body, headers={'Content-Type': f'multipart/form-data; boundary={boundary}'})
    with urllib.request.urlopen(request) as response:
        return json.load(response)['source']['id']
a = post('/api/projects', {'name':'A'})['id']
b = post('/api/projects', {'name':'B'})['id']
sa = upload(a, 'ProjectAlpha 项目的预算为 73921 元。')
sb = upload(b, 'ProjectBeta 项目的预算为 16248 元。')
with server.connect() as conn:
    assert not conn.execute('SELECT superseded FROM sources WHERE id=?',(sa,)).fetchone()[0]
    assert all(r['source_id'] == sa for r in server.search_chunks(conn, '项目预算', project_id=a))
    assert all(r['source_id'] == sb for r in server.search_chunks(conn, '项目预算', project_id=b))
# Shared content remains valid for B after updating A's head.
assert upload(b, 'ProjectAlpha 项目的预算为 73921 元。') == sa
sa2 = upload(a, 'ProjectAlpha 项目的预算为 88000 元。')
with server.connect() as conn:
    assert not conn.execute('SELECT superseded FROM sources WHERE id=?',(sa,)).fetchone()[0]
    assert {r['source_id'] for r in server.search_chunks(conn,'ProjectAlpha 预算',project_id=a)} == {sa2}
    assert {r['source_id'] for r in server.search_chunks(conn,'ProjectAlpha 预算',project_id=b)} == {sa}
    assert conn.execute('SELECT superseded FROM sources WHERE id=?',(sb,)).fetchone()[0]
# Notes, tasks and approved memories are citeable; candidates and archives are excluded.
note = post('/api/notes', {'project_id':a,'title':'青岚预算','body':'青岚项目预算 91234 元。\nTODO: 核对青岚预算'})['note']
mem = post('/api/memories', {'project_id':a,'title':'报告语言','body':'我偏好的报告语言是西班牙语。','status':'approved'})
post('/api/memories', {'project_id':b,'title':'报告语言','body':'报告语言是日语。','status':'approved'})
post('/api/memories', {'project_id':a,'title':'秘密候选','body':'候选暗号 tortoise','status':'candidate'})
answer = post('/api/chat', {'project_id':a,'question':'青岚项目预算是多少？'})
assert '91234' in answer['answer'], answer
assert any(c['item_type']=='note' and c['item_id']==note['id'] for c in answer['citations'])
answer = post('/api/chat', {'project_id':a,'question':'我偏好的报告语言是什么？'})
assert '西班牙语' in answer['answer'] and '日语' not in answer['answer'], answer
with server.connect() as conn:
    assert not server.search_chunks(conn, 'tortoise', project_id=a)
    conn.execute("UPDATE memories SET status='archived' WHERE id=?",(mem['id'],))
with server.connect() as conn:
    assert not any(r['item_type']=='memory' for r in server.search_chunks(conn,'西班牙语',project_id=a))
# MCP uses the same scoped query and can remain read-only.
result = mcp_server.call_tool('wiki_search', {'query':'ProjectAlpha 预算','project_id':b})
assert {r['source_id'] for r in json.loads(result['content'][0]['text'])['results']} == {sa}
# A second writer works while a model request is in flight, including a brand-new conversation.
post('/api/settings', {'base_url':'http://127.0.0.1:9/v1','model':'test'})
entered, release = threading.Event(), threading.Event()
captured = []
def delayed(settings, question, contexts, history):
    captured.append(history)
    entered.set()
    assert release.wait(5)
    return '已核对预算。'
results, errors = [], []
def chat():
    try: results.append(post('/api/chat',{'project_id':a,'question':'青岚项目预算是多少？'}))
    except Exception as exc: errors.append(exc)
with patch.object(server,'call_llm',delayed):
    thread = threading.Thread(target=chat)
    thread.start()
    assert entered.wait(5)
    try:
        with sqlite3.connect(server.DB_PATH, timeout=0.2) as conn:
            conn.execute("INSERT INTO settings(key,value) VALUES ('writer_probe','ok')")
    finally:
        release.set()
        thread.join(5)
    assert not errors, errors
    second = post('/api/chat',{'project_id':a,'conversation_id':results[0]['conversation_id'],'question':'那它的预算呢？'})
    assert len(captured[-1]) == 2 and captured[-1][0]['role']=='user', captured
httpd.shutdown()
httpd.server_close()
'''


class ProjectKnowledgeTests(unittest.TestCase):
    def test_scoped_evidence_and_nonblocking_model(self):
        with tempfile.TemporaryDirectory() as data:
            result = subprocess.run([sys.executable, '-c', CHECK], cwd=ROOT,
                env={**os.environ,'PERSONAL_AI_OS_DATA_DIR':data}, capture_output=True,text=True,timeout=30)
            self.assertEqual(result.returncode,0,result.stdout+result.stderr)

RECEIPT_CHECK = r'''
import json
from unittest.mock import patch
import server
import handoff
server.ensure_db()
handler=server.Handler.__new__(server.Handler)
responses=[]
with patch.object(server,'json_response',lambda _,payload,*a:responses.append(payload)):
    handler.create_project({'name':'交接项目','goal':'做一个预算页面'})
    project=responses[-1]['id']
    handler.create_note({'project_id':project,'body':'预算为 100 元。'})
with server.connect() as conn:
    exported=handoff.export_task(conn,project)
    receipt={'format':handoff.RECEIPT_FORMAT,'handoff_id':exported['handoff_id'],
        'evidence_hash':exported['evidence_hash'],'objective':'预算页面','artifacts':[
        {'name':'index.html','version':1,'content_hash':'abc','sandbox_status':'untested'}],
        'deployments':[]}
    staged=handoff.stage_receipt(conn,project,receipt,server.now_iso())
    assert staged['status']=='pending'
    assert handoff.stage_receipt(conn,project,receipt,server.now_iso())['id']==staged['id']
with server.connect() as conn:
    assert not conn.execute("SELECT 1 FROM notes WHERE title='AgentHub 执行回执'").fetchone()
    try:
        handoff.stage_receipt(conn,'another-project',receipt,server.now_iso())
        assert False,'another project accepted the receipt'
    except ValueError:
        pass
handler.path='/api/receipts/'+staged['id']+'/approve'
with patch.object(server,'json_response',lambda _,payload,*a:responses.append(payload)):
    handler.do_POST()
    assert responses[-1]['status']=='approved'
with server.connect() as conn:
    results=server.search_chunks(conn,'执行回执',project_id=project)
    assert any('未验证' in item['content'] or 'untested' in item['content'] for item in results)
'''


class HandoffTests(unittest.TestCase):
    def test_receipts_require_review_and_original_project(self):
        with tempfile.TemporaryDirectory() as data:
            result=subprocess.run([sys.executable,'-c',RECEIPT_CHECK],cwd=ROOT,
                env={**os.environ,'PERSONAL_AI_OS_DATA_DIR':data},capture_output=True,text=True,timeout=30)
            self.assertEqual(result.returncode,0,result.stdout+result.stderr)
