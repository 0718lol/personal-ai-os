"""Portable project briefs and reviewed execution receipts."""
import hashlib
import json
import uuid

FORMAT = 'personal-ai-os.task.v1'
RECEIPT_FORMAT = 'agent-hub.receipt.v1'


def export_task(conn, project_id):
    project = conn.execute('SELECT * FROM collections WHERE id=?',(project_id,)).fetchone()
    if not project:
        raise LookupError('没有找到这个项目')
    evidence=[]
    for row in conn.execute('SELECT c.* FROM chunks c JOIN source_heads h ON h.source_id=c.source_id WHERE h.project_id=? ORDER BY c.id LIMIT 16',(project_id,)):
        evidence.append({'kind':'source','id':row['source_id'],'chunk_id':row['id'],'title':row['title'],
            'text':row['content'][:1800],'page_start':row['page_start'],'page_end':row['page_end']})
    for kind,table,column,extra in [('note','notes','body',''),('memory','memories','body'," AND status='approved'"),('task','tasks','title'," AND status!='done'")]:
        for row in conn.execute(f'SELECT * FROM {table} WHERE id IN (SELECT item_id FROM collection_items WHERE collection_id=? AND item_type=?)'+extra+' ORDER BY updated_at DESC LIMIT 8',(project_id,kind)):
            evidence.append({'kind':kind,'id':row['id'],'title':row['title'],'text':row[column][:1800]})
    payload={'format':FORMAT,'handoff_id':str(uuid.uuid4()),'project':{'id':project_id,'name':project['name'],'goal':project['description']},'evidence':evidence}
    payload['evidence_hash']=hashlib.sha256(json.dumps(evidence,sort_keys=True,ensure_ascii=False).encode()).hexdigest()
    conn.execute('INSERT INTO handoff_exports(id,project_id,evidence_hash) VALUES (?,?,?)',(payload['handoff_id'],project_id,payload['evidence_hash']))
    return payload


def stage_receipt(conn,project_id,payload,now):
    if not isinstance(payload, dict):
        raise ValueError('执行回执必须是 JSON 对象')
    if payload.get('format') != RECEIPT_FORMAT:
        raise ValueError('不支持的执行回执格式')
    for key, limit in [('artifacts',20),('deployments',5)]:
        items = payload.get(key, [])
        if not isinstance(items,list) or len(items)>limit or not all(isinstance(item,dict) for item in items):
            raise ValueError('执行回执的产物或发布记录格式不正确')
    origin=conn.execute('SELECT * FROM handoff_exports WHERE id=? AND project_id=?',(str(payload.get('handoff_id') or ''),project_id)).fetchone()
    if not origin or payload.get('evidence_hash') != origin['evidence_hash']:
        raise ValueError('回执与这个项目导出的任务不匹配')
    encoded=json.dumps(payload,ensure_ascii=False,sort_keys=True)
    if len(encoded)>1_000_000:
        raise ValueError('执行回执过大')
    receipt_id=hashlib.sha256(encoded.encode()).hexdigest()
    conn.execute("INSERT OR IGNORE INTO handoff_returns(id,project_id,payload,status,created_at) VALUES (?,?,?,'pending',?)",(receipt_id,project_id,encoded,now))
    return {'id':receipt_id,'status':conn.execute('SELECT status FROM handoff_returns WHERE id=?',(receipt_id,)).fetchone()['status']}


def receipt_markdown(payload):
    lines=['# AgentHub 执行回执','',str(payload.get('objective') or ''),'',f"会话：{payload.get('conversation_id','')}",f"任务：{payload.get('handoff_id','')}",f"资料指纹：{payload.get('evidence_hash','')}"]
    for artifact in payload.get('artifacts',[])[:20]:
        lines.extend(['',f"产物：{artifact.get('name','')} · v{artifact.get('version','')}",f"内容指纹：{artifact.get('content_hash','')}",f"沙箱状态：{artifact.get('sandbox_status','untested')}",str(artifact.get('sandbox_output') or '')[:2000]])
    for job in payload.get('deployments',[])[:5]:
        lines.extend(['',f"发布：{job.get('status','')} · {job.get('target','')}",f"输入指纹：{job.get('input_hash','')}",f"交付地址：{job.get('url','')}"])
    lines.extend(['','此记录来自导入的执行回执；运行结果与地址已由用户审核。'])
    return '\n'.join(lines)
