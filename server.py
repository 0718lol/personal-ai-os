import hashlib
import importlib.util
import json
import mimetypes
import os
import re
import sqlite3
import urllib.error
import urllib.parse
import urllib.request
import uuid
import traceback
from contextlib import contextmanager
from datetime import datetime, timezone
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

try:
    from pypdf import PdfReader
except Exception:
    PdfReader = None


ROOT = Path(__file__).resolve().parent
PUBLIC_DIR = ROOT / "public"
DATA_DIR = Path(os.environ.get("PERSONAL_AI_OS_DATA_DIR", str(ROOT / "data"))).expanduser()
UPLOAD_DIR = DATA_DIR / "uploads"
DB_PATH = DATA_DIR / "personal_ai_os.sqlite3"

DATA_DIR.mkdir(exist_ok=True)
UPLOAD_DIR.mkdir(exist_ok=True)


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


@contextmanager
def connect():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = WAL")
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def ensure_db() -> None:
    DATA_DIR.mkdir(exist_ok=True)
    UPLOAD_DIR.mkdir(exist_ok=True)
    init_db()


def init_db() -> None:
    with connect() as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS settings (
              key TEXT PRIMARY KEY,
              value TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS sources (
              id TEXT PRIMARY KEY,
              title TEXT NOT NULL,
              original_name TEXT NOT NULL,
              kind TEXT NOT NULL,
              mime_type TEXT NOT NULL,
              file_path TEXT NOT NULL,
              checksum TEXT NOT NULL,
              size_bytes INTEGER NOT NULL,
              status TEXT NOT NULL,
              error TEXT NOT NULL DEFAULT '',
              text_content TEXT NOT NULL DEFAULT '',
              parser_engine TEXT NOT NULL DEFAULT '',
              page_count INTEGER NOT NULL DEFAULT 0,
              char_count INTEGER NOT NULL DEFAULT 0,
              quality_json TEXT NOT NULL DEFAULT '{}',
              created_at TEXT NOT NULL,
              updated_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS chunks (
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              source_id TEXT NOT NULL REFERENCES sources(id) ON DELETE CASCADE,
              chunk_index INTEGER NOT NULL,
              title TEXT NOT NULL,
              content TEXT NOT NULL,
              page_start INTEGER NOT NULL DEFAULT 0,
              page_end INTEGER NOT NULL DEFAULT 0,
              created_at TEXT NOT NULL
            );

            CREATE VIRTUAL TABLE IF NOT EXISTS chunks_fts USING fts5(
              title,
              content,
              source_id UNINDEXED,
              content='chunks',
              content_rowid='id'
            );

            CREATE TRIGGER IF NOT EXISTS chunks_ai AFTER INSERT ON chunks BEGIN
              INSERT INTO chunks_fts(rowid, title, content, source_id)
              VALUES (new.id, new.title, new.content, new.source_id);
            END;

            CREATE TRIGGER IF NOT EXISTS chunks_ad AFTER DELETE ON chunks BEGIN
              INSERT INTO chunks_fts(chunks_fts, rowid, title, content, source_id)
              VALUES('delete', old.id, old.title, old.content, old.source_id);
            END;

            CREATE TRIGGER IF NOT EXISTS chunks_au AFTER UPDATE ON chunks BEGIN
              INSERT INTO chunks_fts(chunks_fts, rowid, title, content, source_id)
              VALUES('delete', old.id, old.title, old.content, old.source_id);
              INSERT INTO chunks_fts(rowid, title, content, source_id)
              VALUES (new.id, new.title, new.content, new.source_id);
            END;

            CREATE TABLE IF NOT EXISTS notes (
              id TEXT PRIMARY KEY,
              title TEXT NOT NULL,
              body TEXT NOT NULL,
              title_source TEXT NOT NULL DEFAULT 'explicit',
              created_at TEXT NOT NULL,
              updated_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS tasks (
              id TEXT PRIMARY KEY,
              title TEXT NOT NULL,
              status TEXT NOT NULL,
              source_type TEXT NOT NULL,
              source_id TEXT NOT NULL,
              created_at TEXT NOT NULL,
              updated_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS conversations (
              id TEXT PRIMARY KEY,
              title TEXT NOT NULL,
              created_at TEXT NOT NULL,
              updated_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS messages (
              id TEXT PRIMARY KEY,
              conversation_id TEXT NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
              role TEXT NOT NULL,
              content TEXT NOT NULL,
              citations_json TEXT NOT NULL DEFAULT '[]',
              created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS events (
              id TEXT PRIMARY KEY,
              kind TEXT NOT NULL,
              title TEXT NOT NULL,
              detail TEXT NOT NULL,
              project_id TEXT NOT NULL DEFAULT '',
              created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS collections (
              id TEXT PRIMARY KEY,
              name TEXT NOT NULL,
              description TEXT NOT NULL DEFAULT '',
              color TEXT NOT NULL DEFAULT '#2f5d46',
              created_at TEXT NOT NULL,
              updated_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS collection_items (
              collection_id TEXT NOT NULL REFERENCES collections(id) ON DELETE CASCADE,
              item_type TEXT NOT NULL,
              item_id TEXT NOT NULL,
              created_at TEXT NOT NULL,
              PRIMARY KEY(collection_id, item_type, item_id)
            );

            CREATE TABLE IF NOT EXISTS memories (
              id TEXT PRIMARY KEY,
              title TEXT NOT NULL,
              body TEXT NOT NULL,
              status TEXT NOT NULL,
              memory_type TEXT NOT NULL,
              confidence REAL NOT NULL DEFAULT 0.5,
              source_type TEXT NOT NULL DEFAULT '',
              source_id TEXT NOT NULL DEFAULT '',
              created_at TEXT NOT NULL,
              updated_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS agents (
              id TEXT PRIMARY KEY,
              name TEXT NOT NULL,
              purpose TEXT NOT NULL,
              instructions TEXT NOT NULL,
              tools_json TEXT NOT NULL DEFAULT '[]',
              schedule TEXT NOT NULL DEFAULT '',
              enabled INTEGER NOT NULL DEFAULT 1,
              created_at TEXT NOT NULL,
              updated_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS agent_runs (
              id TEXT PRIMARY KEY,
              agent_id TEXT NOT NULL REFERENCES agents(id) ON DELETE CASCADE,
              status TEXT NOT NULL,
              input TEXT NOT NULL,
              output TEXT NOT NULL,
              logs_json TEXT NOT NULL DEFAULT '[]',
              created_at TEXT NOT NULL,
              updated_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS connectors (
              id TEXT PRIMARY KEY,
              name TEXT NOT NULL,
              kind TEXT NOT NULL,
              status TEXT NOT NULL,
              description TEXT NOT NULL,
              config_json TEXT NOT NULL DEFAULT '{}',
              created_at TEXT NOT NULL,
              updated_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS playbooks (
              id TEXT PRIMARY KEY,
              audience TEXT NOT NULL,
              name TEXT NOT NULL,
              scenario TEXT NOT NULL,
              outcome TEXT NOT NULL,
              collection_name TEXT NOT NULL,
              tasks_json TEXT NOT NULL DEFAULT '[]',
              memories_json TEXT NOT NULL DEFAULT '[]',
              agents_json TEXT NOT NULL DEFAULT '[]',
              created_at TEXT NOT NULL,
              updated_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS insights (
              id TEXT PRIMARY KEY,
              project_id TEXT NOT NULL DEFAULT '',
              note_id TEXT NOT NULL DEFAULT '',
              kind TEXT NOT NULL,
              title TEXT NOT NULL,
              body TEXT NOT NULL,
              source_quote TEXT NOT NULL DEFAULT '',
              confidence REAL NOT NULL DEFAULT 0.65,
              status TEXT NOT NULL DEFAULT 'open',
              created_at TEXT NOT NULL,
              updated_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS deliverables (
              id TEXT PRIMARY KEY,
              project_id TEXT NOT NULL DEFAULT '',
              template TEXT NOT NULL,
              title TEXT NOT NULL,
              body TEXT NOT NULL,
              created_at TEXT NOT NULL,
              updated_at TEXT NOT NULL
            );
            """
        )
        note_columns = {row["name"] for row in conn.execute("PRAGMA table_info(notes)").fetchall()}
        if "title_source" not in note_columns:
            conn.execute("ALTER TABLE notes ADD COLUMN title_source TEXT NOT NULL DEFAULT 'explicit'")
        ensure_column(conn, "sources", "parser_engine", "TEXT NOT NULL DEFAULT ''")
        ensure_column(conn, "sources", "page_count", "INTEGER NOT NULL DEFAULT 0")
        ensure_column(conn, "sources", "char_count", "INTEGER NOT NULL DEFAULT 0")
        ensure_column(conn, "sources", "quality_json", "TEXT NOT NULL DEFAULT '{}'")
        ensure_column(conn, "chunks", "page_start", "INTEGER NOT NULL DEFAULT 0")
        ensure_column(conn, "chunks", "page_end", "INTEGER NOT NULL DEFAULT 0")
        ensure_column(conn, "events", "project_id", "TEXT NOT NULL DEFAULT ''")
        ensure_column(conn, "insights", "project_id", "TEXT NOT NULL DEFAULT ''")
        ensure_column(conn, "insights", "note_id", "TEXT NOT NULL DEFAULT ''")
        ensure_column(conn, "deliverables", "project_id", "TEXT NOT NULL DEFAULT ''")
        seed_defaults(conn)
        localize_default_records(conn)
        backfill_pdf_evidence_chunks(conn)


def seed_defaults(conn: sqlite3.Connection) -> None:
    created = now_iso()
    if conn.execute("SELECT count(*) FROM collections").fetchone()[0] == 0:
        conn.execute(
            "INSERT INTO collections(id, name, description, color, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?)",
            ("inbox", "收件箱", "临时收集的资料、笔记和想法，等待后续整理。", "#a75f37", created, created),
        )
    if conn.execute("SELECT count(*) FROM agents").fetchone()[0] == 0:
        agents = [
            ("researcher", "研究助手", "基于本地资料生成带引用的研究摘要。", "优先搜索本地上下文。使用引用。明确标注不确定性。", ["local_search", "source_reader"], ""),
            ("planner", "计划助手", "把笔记、任务和对话整理成行动计划。", "找出未完成任务、过期决策和下一步行动。", ["task_writer", "memory_reader"], "daily"),
            ("librarian", "资料管理员", "检查资料库、解析失败和索引质量。", "检查解析失败、重复资料、薄弱元数据和缺失工作区。", ["source_reader", "parser_report"], ""),
            ("reviewer", "审核助手", "审核记忆、决策质量和过期假设。", "找出矛盾、过期事实和尚未批准的记忆候选。", ["memory_reader", "activity_log"], "weekly"),
        ]
        for agent_id, name, purpose, instructions, tools, schedule in agents:
            conn.execute(
                """
                INSERT INTO agents(id, name, purpose, instructions, tools_json, schedule, enabled, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, 1, ?, ?)
                """,
                (agent_id, name, purpose, instructions, json.dumps(tools), schedule, created, created),
            )
    if conn.execute("SELECT count(*) FROM connectors").fetchone()[0] == 0:
        connectors = [
            ("folder", "文件夹监听", "local", "planned", "把选定本地文件夹同步进资料库。", {"permission": "read"}),
            ("notion", "Notion", "cloud", "planned", "把页面和数据库采集到工作区。", {"permission": "oauth"}),
            ("github", "GitHub", "cloud", "planned", "索引仓库、issue、PR 和文档。", {"permission": "token"}),
            ("browser", "浏览器采集", "local", "planned", "保存网页链接和页面快照。", {"permission": "extension"}),
            ("calendar", "日历", "cloud", "planned", "把日程用于计划和每日简报。", {"permission": "oauth"}),
        ]
        for connector_id, name, kind, status, description, config in connectors:
            conn.execute(
                """
                INSERT INTO connectors(id, name, kind, status, description, config_json, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (connector_id, name, kind, status, description, json.dumps(config), created, created),
            )
    if conn.execute("SELECT count(*) FROM playbooks").fetchone()[0] == 0:
        playbooks = [
            {
                "id": "research-lab",
                "audience": "研究生 / 科研人员 / 文献工作者",
                "name": "研究实验室",
                "scenario": "长期阅读论文、PDF、实验记录和竞品资料，需要能追溯来源、做文献综述、沉淀研究问题。",
                "outcome": "形成可检索的研究库、带引用的问答、待办实验计划和可审核研究记忆。",
                "collection": "研究实验室",
                "tasks": ["导入 5 篇核心论文", "让研究助手生成带引用的摘要", "审核并批准长期研究记忆"],
                "memories": ["研究输出必须能追溯到来源和页码", "未知或证据不足的结论必须明确标注"],
                "agents": ["researcher", "librarian", "reviewer"],
            },
            {
                "id": "founder-command",
                "audience": "创业者 / 产品经理 / 独立开发者",
                "name": "创业指挥台",
                "scenario": "同时推进需求、竞品、用户反馈、路线图和周计划，需要一个不会遗忘上下文的项目驾驶舱。",
                "outcome": "把资料、决策、TODO、风险和下一步行动聚合成每日可执行计划。",
                "collection": "创业指挥台",
                "tasks": ["导入竞品笔记", "记录当前产品决策", "运行计划助手梳理下一步行动"],
                "memories": ["用户体验优先级高于技术偏好", "每个重要决策都需要保留理由"],
                "agents": ["planner", "researcher", "reviewer"],
            },
            {
                "id": "developer-brain",
                "audience": "程序员 / 技术负责人",
                "name": "开发者大脑",
                "scenario": "管理代码库、技术文档、issue、设计决策和调试记录，需要快速找上下文并生成实施计划。",
                "outcome": "代码相关知识、架构约束、任务和 agent run 统一进入可审计工作流。",
                "collection": "开发者大脑",
                "tasks": ["导入架构文档", "记录未解决问题", "运行资料管理员检查解析和索引质量"],
                "memories": ["代码变更需要可验证", "不要把密钥写入代码"],
                "agents": ["librarian", "planner", "reviewer"],
            },
            {
                "id": "writer-studio",
                "audience": "写作者 / 自媒体 / 内容研究者",
                "name": "写作工作室",
                "scenario": "收集素材、观点、采访记录、草稿和发布计划，需要从资料到选题到大纲一体化。",
                "outcome": "把素材库变成选题、结构化大纲、写作任务和长期风格记忆。",
                "collection": "写作工作室",
                "tasks": ["导入素材资料", "记录 3 个文章角度", "运行研究助手生成证据大纲"],
                "memories": ["输出要保留个人观点和证据边界", "避免没有来源的断言"],
                "agents": ["researcher", "planner"],
            },
            {
                "id": "analyst-desk",
                "audience": "咨询顾问 / 投资研究 / 行业分析师",
                "name": "分析师工作台",
                "scenario": "跟踪公司、政策、市场、新闻和会议纪要，需要按主题沉淀证据和风险。",
                "outcome": "形成事件线索、风险清单、证据摘要和周期性复盘。",
                "collection": "分析师工作台",
                "tasks": ["导入近期报告", "记录待回答问题", "运行审核助手查找过期假设"],
                "memories": ["区分事实、判断和假设", "过期信息需要标注时间"],
                "agents": ["researcher", "reviewer", "planner"],
            },
        ]
        for item in playbooks:
            conn.execute(
                """
                INSERT INTO playbooks(id, audience, name, scenario, outcome, collection_name, tasks_json, memories_json, agents_json, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    item["id"],
                    item["audience"],
                    item["name"],
                    item["scenario"],
                    item["outcome"],
                    item["collection"],
                    json.dumps(item["tasks"], ensure_ascii=False),
                    json.dumps(item["memories"], ensure_ascii=False),
                    json.dumps(item["agents"], ensure_ascii=False),
                    created,
                    created,
                ),
            )


def ensure_column(conn: sqlite3.Connection, table: str, column: str, definition: str) -> None:
    columns = {row["name"] for row in conn.execute(f"PRAGMA table_info({table})").fetchall()}
    if column not in columns:
        conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")


def localize_default_records(conn: sqlite3.Connection) -> None:
    created = now_iso()
    conn.execute(
        """
        UPDATE collections
        SET name = '收件箱',
            description = '临时收集的资料、笔记和想法，等待后续整理。',
            updated_at = ?
        WHERE id = 'inbox' AND name = 'Inbox'
        """,
        (created,),
    )
    agent_updates = {
        "researcher": ("研究助手", "基于本地资料生成带引用的研究摘要。", "优先搜索本地上下文。使用引用。明确标注不确定性。"),
        "planner": ("计划助手", "把笔记、任务和对话整理成行动计划。", "找出未完成任务、过期决策和下一步行动。"),
        "librarian": ("资料管理员", "检查资料库、解析失败和索引质量。", "检查解析失败、重复资料、薄弱元数据和缺失工作区。"),
        "reviewer": ("审核助手", "审核记忆、决策质量和过期假设。", "找出矛盾、过期事实和尚未批准的记忆候选。"),
    }
    for agent_id, (name, purpose, instructions) in agent_updates.items():
        conn.execute(
            "UPDATE agents SET name = ?, purpose = ?, instructions = ?, updated_at = ? WHERE id = ?",
            (name, purpose, instructions, created, agent_id),
        )
    connector_updates = {
        "folder": ("文件夹监听", "把选定本地文件夹同步进资料库。"),
        "notion": ("Notion", "把页面和数据库采集到工作区。"),
        "github": ("GitHub", "索引仓库、issue、PR 和文档。"),
        "browser": ("浏览器采集", "保存网页链接和页面快照。"),
        "calendar": ("日历", "把日程用于计划和每日简报。"),
    }
    for connector_id, (name, description) in connector_updates.items():
        conn.execute(
            "UPDATE connectors SET name = ?, description = ?, updated_at = ? WHERE id = ?",
            (name, description, created, connector_id),
        )
    playbook_updates = {
        "research-lab": ("研究实验室", "研究实验室", ["导入 5 篇核心论文", "让研究助手生成带引用的摘要", "审核并批准长期研究记忆"]),
        "founder-command": ("创业指挥台", "创业指挥台", ["导入竞品笔记", "记录当前产品决策", "运行计划助手梳理下一步行动"]),
        "developer-brain": ("开发者大脑", "开发者大脑", ["导入架构文档", "记录未解决问题", "运行资料管理员检查解析和索引质量"]),
        "writer-studio": ("写作工作室", "写作工作室", ["导入素材资料", "记录 3 个文章角度", "运行研究助手生成证据大纲"]),
        "analyst-desk": ("分析师工作台", "分析师工作台", ["导入近期报告", "记录待回答问题", "运行审核助手查找过期假设"]),
    }
    for playbook_id, (name, collection_name, tasks) in playbook_updates.items():
        conn.execute(
            "UPDATE playbooks SET name = ?, collection_name = ?, tasks_json = ?, updated_at = ? WHERE id = ?",
            (name, collection_name, json.dumps(tasks, ensure_ascii=False), created, playbook_id),
        )


def backfill_pdf_evidence_chunks(conn: sqlite3.Connection) -> None:
    sources = conn.execute(
        """
        SELECT id, title, kind, text_content, quality_json, page_count
        FROM sources
        WHERE kind = 'pdf' AND status = 'ready' AND text_content != ''
        """
    ).fetchall()
    for source in sources:
        stats = conn.execute(
            "SELECT count(*) AS total, COALESCE(max(page_start), 0) AS max_page FROM chunks WHERE source_id = ?",
            (source["id"],),
        ).fetchone()
        if not stats or int(stats["total"] or 0) == 0 or int(stats["max_page"] or 0) > 0:
            continue
        chunks = evidence_chunks(source["text_content"], "pdf")
        if not chunks:
            continue
        created = now_iso()
        try:
            quality = json.loads(source["quality_json"] or "{}")
        except json.JSONDecodeError:
            quality = {}
        quality["page_count"] = int(source["page_count"] or quality.get("page_count") or 0)
        quality = enrich_quality(quality, chunks, "pdf")
        conn.execute("DELETE FROM chunks WHERE source_id = ?", (source["id"],))
        for index, chunk in enumerate(chunks):
            conn.execute(
                "INSERT INTO chunks(source_id, chunk_index, title, content, page_start, page_end, created_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
                (source["id"], index, source["title"], chunk["content"], int(chunk["page_start"] or 0), int(chunk["page_end"] or 0), created),
            )
        conn.execute(
            "UPDATE sources SET quality_json = ?, updated_at = ? WHERE id = ?",
            (json.dumps(quality, ensure_ascii=False), created, source["id"]),
        )


def row_dict(row: sqlite3.Row) -> dict[str, Any]:
    return dict(row)


def add_event(conn: sqlite3.Connection, kind: str, title: str, detail: str = "", project_id: str = "") -> None:
    conn.execute(
        "INSERT INTO events(id, kind, title, detail, project_id, created_at) VALUES (?, ?, ?, ?, ?, ?)",
        (str(uuid.uuid4()), kind, title, detail, project_id, now_iso()),
    )


def link_project_item(conn: sqlite3.Connection, project_id: str, item_type: str, item_id: str) -> None:
    if not project_id:
        return
    project = conn.execute("SELECT id FROM collections WHERE id = ?", (project_id,)).fetchone()
    if not project:
        raise ValueError("项目不存在")
    conn.execute(
        """
        INSERT OR IGNORE INTO collection_items(collection_id, item_type, item_id, created_at)
        VALUES (?, ?, ?, ?)
        """,
        (project_id, item_type, item_id, now_iso()),
    )


def project_counts(conn: sqlite3.Connection, project_id: str) -> dict[str, int]:
    def count(item_type: str, join_sql: str = "", where_sql: str = "") -> int:
        row = conn.execute(
            f"""
            SELECT count(*) AS total
            FROM collection_items ci
            {join_sql}
            WHERE ci.collection_id = ? AND ci.item_type = ? {where_sql}
            """,
            (project_id, item_type),
        ).fetchone()
        return int(row["total"] or 0)

    return {
        "sources": count("source"),
        "notes": count("note"),
        "tasks": count("task", "JOIN tasks ON tasks.id = ci.item_id", "AND tasks.status != 'done'"),
        "done_tasks": count("task", "JOIN tasks ON tasks.id = ci.item_id", "AND tasks.status = 'done'"),
        "memories": count("memory", "JOIN memories ON memories.id = ci.item_id", "AND memories.status = 'approved'"),
        "memory_candidates": count("memory", "JOIN memories ON memories.id = ci.item_id", "AND memories.status = 'candidate'"),
    }


def project_resume(conn: sqlite3.Connection, project_id: str) -> dict[str, Any]:
    project = conn.execute("SELECT * FROM collections WHERE id = ?", (project_id,)).fetchone()
    if not project:
        return {}
    counts = project_counts(conn, project_id)
    latest_event = conn.execute(
        "SELECT * FROM events WHERE project_id = ? ORDER BY created_at DESC LIMIT 1",
        (project_id,),
    ).fetchone()
    latest_note = conn.execute(
        """
        SELECT notes.*
        FROM collection_items ci
        JOIN notes ON notes.id = ci.item_id
        WHERE ci.collection_id = ? AND ci.item_type = 'note'
        ORDER BY notes.updated_at DESC
        LIMIT 1
        """,
        (project_id,),
    ).fetchone()
    next_tasks = conn.execute(
        """
        SELECT tasks.*
        FROM collection_items ci
        JOIN tasks ON tasks.id = ci.item_id
        WHERE ci.collection_id = ? AND ci.item_type = 'task' AND tasks.status != 'done'
        ORDER BY tasks.created_at DESC
        LIMIT 3
        """,
        (project_id,),
    ).fetchall()
    open_question = extract_first_marker(latest_note["body"] if latest_note else "", ("问题", "QUESTION", "待确认"))
    decision = extract_first_marker(latest_note["body"] if latest_note else "", ("决策", "DECISION", "决定"))
    progress = latest_event["title"] if latest_event else "还没有项目活动。"
    if latest_note:
        progress = f"最近笔记：{safe_title(latest_note['title'] if latest_note['title'] != '无标题' else latest_note['body'][:80])}"
    next_step = next_tasks[0]["title"] if next_tasks else "补一条 TODO，明确最小下一步。"
    blocker = open_question or ("有待审核记忆需要确认。" if counts["memory_candidates"] else "暂无明确卡点。")
    health = "推进中"
    if not counts["tasks"]:
        health = "缺少下一步"
    elif counts["sources"] and not counts["notes"]:
        health = "资料待整理"
    elif counts["memory_candidates"]:
        health = "上下文待确认"
    return {
        "health": health,
        "progress": progress,
        "next_step": next_step,
        "blocker": blocker,
        "decision": decision or "暂无明确决策记录。",
        "last_activity_at": (latest_event["created_at"] if latest_event else project["updated_at"]),
        "next_tasks": [row_dict(row) for row in next_tasks],
    }


def extract_first_marker(body: str, labels: tuple[str, ...]) -> str:
    for line in str(body or "").splitlines():
        for label in labels:
            match = re.match(rf"^(?:[-*]\s*)?{re.escape(label)}[:：](.+)$", line.strip(), re.I)
            if match:
                return match.group(1).strip()[:260]
    return ""


def public_project(conn: sqlite3.Connection, row: sqlite3.Row, include_resume: bool = True) -> dict[str, Any]:
    data = row_dict(row)
    data["display_name"] = data["name"]
    data["goal"] = data.get("description", "")
    data["counts"] = project_counts(conn, data["id"])
    if include_resume:
        data["resume"] = project_resume(conn, data["id"])
    return data


def normalize_text(text: str) -> str:
    text = text.replace("\x00", " ")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def chunk_text(text: str, size: int = 1400, overlap: int = 180) -> list[str]:
    clean = normalize_text(text)
    if not clean:
        return []
    chunks: list[str] = []
    start = 0
    while start < len(clean):
        end = min(len(clean), start + size)
        boundary = max(clean.rfind("\n\n", start, end), clean.rfind(". ", start, end))
        if boundary > start + int(size * 0.45):
            end = boundary + 1
        piece = clean[start:end].strip()
        if piece:
            chunks.append(piece)
        if end >= len(clean):
            break
        start = max(0, end - overlap)
    return chunks


def split_pdf_pages(text: str) -> list[dict[str, Any]]:
    matches = list(re.finditer(r"(?:^|\n)Page\s+(\d+)\s*\n", text))
    if not matches:
        clean = normalize_text(re.sub(r"^Page\s+\d+\s*\n", "", text))
        return [{"page": 0, "text": clean}] if clean else []
    pages = []
    for index, match in enumerate(matches):
        start = match.end()
        end = matches[index + 1].start() if index + 1 < len(matches) else len(text)
        page_text = normalize_text(text[start:end])
        if page_text:
            pages.append({"page": int(match.group(1)), "text": page_text})
    return pages


def evidence_chunks(text: str, kind: str, size: int = 1400, overlap: int = 180) -> list[dict[str, Any]]:
    if kind == "pdf":
        chunks: list[dict[str, Any]] = []
        for page in split_pdf_pages(text):
            for piece in chunk_text(page["text"], size=size, overlap=min(overlap, 120)):
                chunks.append({"content": piece, "page_start": page["page"], "page_end": page["page"]})
        return chunks
    return [{"content": piece, "page_start": 0, "page_end": 0} for piece in chunk_text(text, size=size, overlap=overlap)]


def enrich_quality(quality: dict[str, Any], chunks: list[dict[str, Any]], kind: str) -> dict[str, Any]:
    enriched = dict(quality)
    enriched["evidence_chunks"] = len(chunks)
    if kind == "pdf":
        page_count = int(enriched.get("page_count") or 0)
        pages_with_text = sorted({item["page_start"] for item in chunks if item.get("page_start")})
        enriched["pages_with_text"] = len(pages_with_text)
        enriched["page_coverage"] = round(len(pages_with_text) / page_count, 3) if page_count else 0
        enriched["citation_granularity"] = "page"
    else:
        enriched["citation_granularity"] = "document"
    return enriched


def extract_text(path: Path, filename: str, mime_type: str) -> tuple[str, str, dict[str, Any]]:
    suffix = path.suffix.lower()
    if suffix == ".pdf" or "pdf" in mime_type:
        return extract_pdf(path)

    raw = path.read_bytes()
    for encoding in ("utf-8", "utf-16", "latin-1"):
        try:
            text = normalize_text(raw.decode(encoding))
            return text, "text", {"engine": f"text-{encoding}", "page_count": 0, "char_count": len(text)}
        except UnicodeDecodeError:
            continue
    text = normalize_text(raw.decode("utf-8", errors="ignore"))
    return text, "text", {"engine": "text-utf-8-ignore", "page_count": 0, "char_count": len(text)}


def module_available(name: str) -> bool:
    return importlib.util.find_spec(name) is not None


def command_available(name: str) -> bool:
    paths = os.environ.get("PATH", "").split(os.pathsep)
    return any((Path(path) / name).exists() for path in paths)


def extract_pdf(path: Path) -> tuple[str, str, dict[str, Any]]:
    attempts: list[dict[str, str]] = []
    for extractor in (
        extract_pdf_docling_cli,
        extract_pdf_marker_cli,
        extract_pdf_mineru_cli,
        extract_pdf_pymupdf4llm,
        extract_pdf_pymupdf,
        extract_pdf_node_helper,
        extract_pdf_markitdown,
        extract_pdf_pypdf,
        extract_pdf_rough,
    ):
        name = extractor.__name__.replace("extract_pdf_", "")
        try:
            text, meta = extractor(path)
            text = normalize_text(text)
            if enough_pdf_text(text):
                meta = {**meta, "engine": meta.get("engine", name), "char_count": len(text), "attempts": attempts}
                return text, "pdf", meta
            attempts.append({"engine": name, "status": "empty-or-low-text"})
        except Exception as exc:
            attempts.append({"engine": name, "status": "failed", "error": str(exc)[:240]})
    rough = rough_pdf_text(path)
    if enough_pdf_text(rough):
        return rough, "pdf", {"engine": "rough-fallback", "page_count": 0, "char_count": len(rough), "attempts": attempts}
    return "", "pdf", {"engine": "none", "page_count": 0, "char_count": 0, "attempts": attempts}


def enough_pdf_text(text: str) -> bool:
    compact = re.sub(r"\s+", "", text)
    if len(compact) < 24:
        return False
    signal = sum(1 for char in compact if char.isalnum())
    printable = sum(1 for char in compact if char.isprintable() and char != "\ufffd")
    controls = len(re.findall(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f-\x9f]", text))
    return signal >= 18 and printable / max(len(compact), 1) >= 0.58 and controls / max(len(text), 1) <= 0.01


def extract_pdf_docling_cli(path: Path) -> tuple[str, dict[str, Any]]:
    if not command_available("docling"):
        raise RuntimeError("docling CLI not installed")
    import subprocess
    import tempfile

    with tempfile.TemporaryDirectory() as tmp:
        subprocess.run(["docling", str(path), "--to", "md", "--output", tmp], check=True, capture_output=True, text=True, timeout=240)
        outputs = sorted(Path(tmp).glob("*.md"))
        if not outputs:
            raise RuntimeError("docling produced no markdown")
        return outputs[0].read_text(encoding="utf-8", errors="ignore"), {"engine": "docling-cli", "page_count": 0}


def extract_pdf_marker_cli(path: Path) -> tuple[str, dict[str, Any]]:
    command = "marker_single" if command_available("marker_single") else "marker"
    if not command_available(command):
        raise RuntimeError("marker CLI not installed")
    import subprocess
    import tempfile

    with tempfile.TemporaryDirectory() as tmp:
        subprocess.run([command, str(path), "--output_dir", tmp], check=True, capture_output=True, text=True, timeout=360)
        outputs = sorted(Path(tmp).rglob("*.md"))
        if not outputs:
            raise RuntimeError("marker produced no markdown")
        return outputs[0].read_text(encoding="utf-8", errors="ignore"), {"engine": "marker-cli", "page_count": 0}


def extract_pdf_mineru_cli(path: Path) -> tuple[str, dict[str, Any]]:
    command = "mineru" if command_available("mineru") else "magic-pdf"
    if not command_available(command):
        raise RuntimeError("MinerU CLI not installed")
    import subprocess
    import tempfile

    with tempfile.TemporaryDirectory() as tmp:
        subprocess.run([command, "-p", str(path), "-o", tmp], check=True, capture_output=True, text=True, timeout=420)
        outputs = sorted(Path(tmp).rglob("*.md"))
        if not outputs:
            raise RuntimeError("MinerU produced no markdown")
        return outputs[0].read_text(encoding="utf-8", errors="ignore"), {"engine": "mineru-cli", "page_count": 0}


def extract_pdf_pymupdf4llm(path: Path) -> tuple[str, dict[str, Any]]:
    if not module_available("pymupdf4llm"):
        raise RuntimeError("pymupdf4llm not installed")
    import pymupdf4llm

    text = pymupdf4llm.to_markdown(str(path))
    return text, {"engine": "pymupdf4llm", "page_count": count_pdf_pages(path)}


def extract_pdf_pymupdf(path: Path) -> tuple[str, dict[str, Any]]:
    if not module_available("fitz"):
        raise RuntimeError("PyMuPDF not installed")
    import fitz

    doc = fitz.open(str(path))
    parts = []
    for index, page in enumerate(doc):
        text = page.get_text("text", sort=True)
        if text.strip():
            parts.append(f"Page {index + 1}\n{text.strip()}")
    return "\n\n".join(parts), {"engine": "pymupdf", "page_count": len(doc)}


def extract_pdf_node_helper(path: Path) -> tuple[str, dict[str, Any]]:
    helper = ROOT / "pdf_extract_node.mjs"
    node_modules = ROOT / "node_modules"
    if not helper.exists() or not node_modules.exists():
        raise RuntimeError("Node PDF helper dependencies not installed")
    import subprocess

    completed = subprocess.run(
        ["node", str(helper), str(path)],
        check=True,
        capture_output=True,
        text=True,
        timeout=180,
    )
    json_line = next((line for line in reversed(completed.stdout.splitlines()) if line.strip().startswith("{")), "")
    if not json_line:
        raise RuntimeError("Node PDF helper produced no JSON")
    payload = json.loads(json_line)
    return payload.get("text", ""), payload.get("meta", {"engine": "node-helper"})


def extract_pdf_markitdown(path: Path) -> tuple[str, dict[str, Any]]:
    if not module_available("markitdown"):
        raise RuntimeError("markitdown not installed")
    from markitdown import MarkItDown

    result = MarkItDown(enable_plugins=False).convert(str(path))
    return result.text_content, {"engine": "markitdown", "page_count": count_pdf_pages(path)}


def extract_pdf_pypdf(path: Path) -> tuple[str, dict[str, Any]]:
    if PdfReader is None:
        raise RuntimeError("pypdf not installed")
    reader = PdfReader(str(path))
    pages = []
    for index, page in enumerate(reader.pages):
        try:
            page_text = page.extract_text() or ""
        except Exception as exc:
            page_text = f"[Page {index + 1} extraction failed: {exc}]"
        if page_text.strip():
            pages.append(f"Page {index + 1}\n{page_text.strip()}")
    return "\n\n".join(pages), {"engine": "pypdf", "page_count": len(reader.pages)}


def extract_pdf_rough(path: Path) -> tuple[str, dict[str, Any]]:
    text = rough_pdf_text(path)
    if not enough_pdf_text(text):
        return "", {"engine": "rough-fallback", "page_count": 0}
    return text, {"engine": "rough-fallback", "page_count": 0}


def count_pdf_pages(path: Path) -> int:
    if PdfReader is None:
        return 0
    try:
        return len(PdfReader(str(path)).pages)
    except Exception:
        return 0


def rough_pdf_text(path: Path) -> str:
    raw = path.read_bytes()
    text = raw.decode("latin-1", errors="ignore")
    pieces: list[str] = []
    for match in re.finditer(r"\((?:\\.|[^\\)]){2,}\)", text):
        value = match.group(0)[1:-1]
        value = value.replace(r"\(", "(").replace(r"\)", ")").replace(r"\\", "\\")
        value = re.sub(r"\\[nrtbf]", " ", value)
        if re.search(r"[A-Za-z\u4e00-\u9fff]{2,}", value):
            pieces.append(value)
    for match in re.finditer(r"<([0-9A-Fa-f]{8,})>", text):
        hex_value = match.group(1)
        try:
            decoded = bytes.fromhex(hex_value).decode("utf-16-be", errors="ignore")
        except ValueError:
            decoded = ""
        if re.search(r"[A-Za-z\u4e00-\u9fff]{2,}", decoded):
            pieces.append(decoded)
    return normalize_text("\n".join(pieces))


def safe_title(filename: str, title: str | None = None) -> str:
    base = (title or filename or "未命名").strip()
    base = re.sub(r"\s+", " ", base)
    return base[:160] or "未命名"


def source_summary(row: sqlite3.Row) -> dict[str, Any]:
    data = row_dict(row)
    data.pop("text_content", None)
    return data


def fts_query(query: str) -> str:
    tokens = re.findall(r"[\w\u4e00-\u9fff]+", query.lower())
    return " OR ".join(tokens[:12]) if tokens else query


def search_chunks(conn: sqlite3.Connection, query: str, limit: int = 8) -> list[dict[str, Any]]:
    q = query.strip()
    if not q:
        return []
    results: list[dict[str, Any]] = []
    try:
        rows = conn.execute(
            """
            SELECT chunks.id AS chunk_id, chunks.source_id, chunks.chunk_index, chunks.title,
                   chunks.page_start, chunks.page_end,
                   snippet(chunks_fts, 1, '<mark>', '</mark>', '...', 18) AS snippet,
                   chunks.content, sources.kind, sources.created_at, sources.parser_engine, sources.page_count,
                   bm25(chunks_fts) AS rank
            FROM chunks_fts
            JOIN chunks ON chunks_fts.rowid = chunks.id
            JOIN sources ON chunks.source_id = sources.id
            WHERE chunks_fts MATCH ?
            ORDER BY rank
            LIMIT ?
            """,
            (fts_query(q), limit),
        ).fetchall()
        results = [row_dict(row) for row in rows]
    except sqlite3.OperationalError:
        results = []

    if len(results) < limit:
        like = f"%{q}%"
        seen = {item["chunk_id"] for item in results}
        rows = conn.execute(
            """
            SELECT chunks.id AS chunk_id, chunks.source_id, chunks.chunk_index, chunks.title,
                   chunks.page_start, chunks.page_end,
                   substr(chunks.content, 1, 260) AS snippet, chunks.content,
                   sources.kind, sources.created_at, sources.parser_engine, sources.page_count, 10.0 AS rank
            FROM chunks
            JOIN sources ON chunks.source_id = sources.id
            WHERE chunks.content LIKE ? OR chunks.title LIKE ?
            ORDER BY chunks.id DESC
            LIMIT ?
            """,
            (like, like, limit),
        ).fetchall()
        for row in rows:
            item = row_dict(row)
            if item["chunk_id"] not in seen:
                results.append(item)
                seen.add(item["chunk_id"])
            if len(results) >= limit:
                break
    return results


def extract_tasks(body: str) -> list[str]:
    tasks = []
    for line in body.splitlines():
        match = re.match(r"^(?:[-*]\s*\[\s?\]|TODO[:：]?|待办[:：]?|任务[:：]?)(.+)$", line.strip(), re.I)
        if match:
            title = match.group(1).strip(" -:：")
            if title:
                tasks.append(title[:220])
    return tasks


INSIGHT_LABELS = {
    "decision": ("决策", "决定", "DECISION"),
    "question": ("问题", "待确认", "QUESTION"),
    "risk": ("风险", "卡点", "阻塞", "RISK", "BLOCKER"),
    "follow_up": ("跟进", "FOLLOWUP", "FOLLOW-UP"),
    "action": ("行动", "ACTION"),
}


def extract_insights(body: str) -> list[dict[str, Any]]:
    insights: list[dict[str, Any]] = []
    for line in str(body or "").splitlines():
        clean = line.strip()
        if not clean:
            continue
        task_match = re.match(r"^(?:[-*]\s*\[\s?\]|TODO[:：]?|待办[:：]?|任务[:：]?)(.+)$", clean, re.I)
        if task_match:
            title = task_match.group(1).strip(" -:：")
            if title:
                insights.append({"kind": "action", "title": title[:160], "body": title, "source_quote": clean, "confidence": 0.82})
            continue
        for kind, labels in INSIGHT_LABELS.items():
            for label in labels:
                match = re.match(rf"^(?:[-*]\s*)?{re.escape(label)}[:：](.+)$", clean, re.I)
                if not match:
                    continue
                text = match.group(1).strip(" -:：")
                if text:
                    insights.append({"kind": kind, "title": safe_title(text[:120]), "body": text, "source_quote": clean, "confidence": 0.76})
                break
            else:
                continue
            break
    return dedupe_insights(insights)


def dedupe_insights(insights: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen = set()
    result = []
    for insight in insights:
        key = (insight["kind"], insight["body"].strip().lower())
        if key in seen:
            continue
        seen.add(key)
        result.append(insight)
    return result


def save_insights(conn: sqlite3.Connection, project_id: str, note_id: str, insights: list[dict[str, Any]]) -> list[dict[str, Any]]:
    created = now_iso()
    saved = []
    for insight in insights:
        insight_id = str(uuid.uuid4())
        conn.execute(
            """
            INSERT INTO insights(id, project_id, note_id, kind, title, body, source_quote, confidence, status, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'open', ?, ?)
            """,
            (
                insight_id,
                project_id,
                note_id,
                insight["kind"],
                insight["title"],
                insight["body"],
                insight.get("source_quote", ""),
                float(insight.get("confidence") or 0.65),
                created,
                created,
            ),
        )
        saved.append({"id": insight_id, **insight, "project_id": project_id, "note_id": note_id, "created_at": created, "updated_at": created})
    return saved


def insight_label(kind: str) -> str:
    return {
        "decision": "决策",
        "question": "问题",
        "risk": "风险",
        "follow_up": "跟进",
        "action": "行动",
    }.get(kind, kind)


def deliverable_title(project_name: str, template: str) -> str:
    label = {
        "weekly": "项目周报",
        "plan": "下一步计划",
        "review": "项目复盘",
        "client": "客户汇报",
        "risk": "风险清单",
    }.get(template, "项目交付物")
    return f"{project_name} - {label}"


def build_deliverable(conn: sqlite3.Connection, project: sqlite3.Row, template: str) -> str:
    project_id = project["id"]
    resume = project_resume(conn, project_id)
    tasks = conn.execute(
        """
        SELECT tasks.*
        FROM collection_items ci
        JOIN tasks ON tasks.id = ci.item_id
        WHERE ci.collection_id = ? AND ci.item_type = 'task'
        ORDER BY tasks.updated_at DESC
        LIMIT 20
        """,
        (project_id,),
    ).fetchall()
    insights = conn.execute("SELECT * FROM insights WHERE project_id = ? ORDER BY created_at DESC LIMIT 30", (project_id,)).fetchall()
    notes = conn.execute(
        """
        SELECT notes.*
        FROM collection_items ci
        JOIN notes ON notes.id = ci.item_id
        WHERE ci.collection_id = ? AND ci.item_type = 'note'
        ORDER BY notes.updated_at DESC
        LIMIT 8
        """,
        (project_id,),
    ).fetchall()
    sources = conn.execute(
        """
        SELECT sources.*
        FROM collection_items ci
        JOIN sources ON sources.id = ci.item_id
        WHERE ci.collection_id = ? AND ci.item_type = 'source'
        ORDER BY sources.created_at DESC
        LIMIT 8
        """,
        (project_id,),
    ).fetchall()
    grouped = group_insights(insights)
    sections = [
        f"# {deliverable_title(project['name'], template)}",
        f"生成时间：{now_iso()}",
        "",
        "项目状态",
        f"- 当前状态：{resume.get('health', '待推进')}",
        f"- 上次进展：{resume.get('progress', '暂无')}",
        f"- 当前卡点：{resume.get('blocker', '暂无明确卡点')}",
        f"- 下一步：{resume.get('next_step', '暂无下一步')}",
        f"- 最近决策：{resume.get('decision', '暂无明确决策')}",
        "",
    ]
    if template == "weekly":
        sections += markdown_list_section("本周完成/更新", [task["title"] for task in tasks if task["status"] == "done"] or [note_preview_text(note) for note in notes[:4]])
        sections += markdown_list_section("下周重点", [task["title"] for task in tasks if task["status"] != "done"][:8])
    elif template == "plan":
        sections += markdown_list_section("下一步行动", [task["title"] for task in tasks if task["status"] != "done"][:10])
        sections += markdown_list_section("需要确认的问题", [item["body"] for item in grouped.get("question", [])])
    elif template == "review":
        sections += markdown_list_section("关键决策", [item["body"] for item in grouped.get("decision", [])])
        sections += markdown_list_section("经验和风险", [item["body"] for item in grouped.get("risk", [])])
    elif template == "client":
        sections += markdown_list_section("近期进展", [note_preview_text(note) for note in notes[:5]])
        sections += markdown_list_section("需要客户确认", [item["body"] for item in grouped.get("question", [])])
    elif template == "risk":
        sections += markdown_list_section("风险清单", [item["body"] for item in grouped.get("risk", [])])
        sections += markdown_list_section("跟进行动", [item["body"] for item in grouped.get("follow_up", [])] + [task["title"] for task in tasks if task["status"] != "done"][:5])
    sections += markdown_list_section("决策记录", [item["body"] for item in grouped.get("decision", [])])
    sections += markdown_list_section("最近资料", [source["title"] for source in sources])
    sections += markdown_list_section("最近笔记", [note_preview_text(note) for note in notes[:6]])
    return "\n".join(sections).strip() + "\n"


def group_insights(insights: list[sqlite3.Row]) -> dict[str, list[sqlite3.Row]]:
    grouped: dict[str, list[sqlite3.Row]] = {}
    for insight in insights:
        grouped.setdefault(insight["kind"], []).append(insight)
    return grouped


def markdown_list_section(title: str, items: list[str]) -> list[str]:
    clean = [str(item or "").strip() for item in items if str(item or "").strip()]
    if not clean:
        return [title, "- 暂无", ""]
    return [title, *[f"- {item}" for item in clean], ""]


def note_preview_text(note: sqlite3.Row) -> str:
    title = display_note_title(note)
    body = re.sub(r"\s+", " ", str(note["body"] or "")).strip()
    if body and title != body:
        return f"{title}：{body[:180]}"
    return title


def get_settings(conn: sqlite3.Connection) -> dict[str, str]:
    data = {row["key"]: row["value"] for row in conn.execute("SELECT key, value FROM settings").fetchall()}
    base_url = data.get("base_url", "https://api.openai.com/v1")
    return {
        "provider": data.get("provider", "openai-compatible"),
        "base_url": base_url,
        "model": data.get("model", "gpt-4.1-mini"),
        "api_key_configured": "yes" if data.get("api_key") else ("local" if is_local_model_url(base_url) else "no"),
        "local_provider": "yes" if is_local_model_url(base_url) else "no",
    }


def get_secret_settings(conn: sqlite3.Connection) -> dict[str, str]:
    data = {row["key"]: row["value"] for row in conn.execute("SELECT key, value FROM settings").fetchall()}
    base_url = data.get("base_url", "https://api.openai.com/v1").rstrip("/")
    return {
        "base_url": base_url,
        "model": data.get("model", "gpt-4.1-mini"),
        "api_key": data.get("api_key", "") or ("local" if is_local_model_url(base_url) else ""),
    }


def is_local_model_url(base_url: str) -> bool:
    host = urllib.parse.urlparse(str(base_url or "")).hostname or ""
    return host in {"localhost", "127.0.0.1", "0.0.0.0", "::1"} or host.startswith("192.168.") or host.startswith("10.") or host.startswith("172.")


def discover_local_models() -> dict[str, Any]:
    candidates = [
        {"provider": "Ollama", "base_url": "http://127.0.0.1:11434/v1", "models_url": "http://127.0.0.1:11434/v1/models", "kind": "openai"},
        {"provider": "Ollama", "base_url": "http://localhost:11434/v1", "models_url": "http://localhost:11434/v1/models", "kind": "openai"},
        {"provider": "LM Studio", "base_url": "http://127.0.0.1:1234/v1", "models_url": "http://127.0.0.1:1234/v1/models", "kind": "openai"},
        {"provider": "LM Studio", "base_url": "http://localhost:1234/v1", "models_url": "http://localhost:1234/v1/models", "kind": "openai"},
        {"provider": "LocalAI", "base_url": "http://127.0.0.1:8080/v1", "models_url": "http://127.0.0.1:8080/v1/models", "kind": "openai"},
        {"provider": "LocalAI", "base_url": "http://localhost:8080/v1", "models_url": "http://localhost:8080/v1/models", "kind": "openai"},
        {"provider": "Jan", "base_url": "http://127.0.0.1:1337/v1", "models_url": "http://127.0.0.1:1337/v1/models", "kind": "openai"},
        {"provider": "Jan", "base_url": "http://localhost:1337/v1", "models_url": "http://localhost:1337/v1/models", "kind": "openai"},
        {"provider": "Ollama", "base_url": "http://127.0.0.1:11434/v1", "models_url": "http://127.0.0.1:11434/api/tags", "kind": "ollama"},
    ]
    found = []
    seen: set[tuple[str, str]] = set()
    for candidate in candidates:
        result = probe_model_candidate(candidate)
        if not result:
            continue
        key = (result["base_url"], result["model"])
        if key in seen:
            continue
        seen.add(key)
        found.append(result)
    return {
        "found": found,
        "checked": [{"provider": item["provider"], "base_url": item["base_url"]} for item in candidates],
        "recommended": found[0] if found else None,
    }


def probe_model_candidate(candidate: dict[str, str]) -> dict[str, Any] | None:
    req = urllib.request.Request(candidate["models_url"], headers={"Accept": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=0.8) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except Exception:
        return None
    models = extract_model_names(data, candidate["kind"])
    if not models:
        return None
    return {
        "provider": candidate["provider"],
        "base_url": candidate["base_url"],
        "model": models[0],
        "models": models[:12],
        "api_key": "local",
        "requires_api_key": False,
    }


def extract_model_names(data: Any, kind: str) -> list[str]:
    if kind == "ollama":
        raw_models = data.get("models", []) if isinstance(data, dict) else []
        return [str(item.get("name") or item.get("model") or "").strip() for item in raw_models if isinstance(item, dict) and (item.get("name") or item.get("model"))]
    raw_models = data.get("data", []) if isinstance(data, dict) else []
    names = []
    for item in raw_models:
        if isinstance(item, dict) and item.get("id"):
            names.append(str(item["id"]).strip())
        elif isinstance(item, str):
            names.append(item.strip())
    return [name for name in names if name]


def public_agent(row: sqlite3.Row) -> dict[str, Any]:
    data = row_dict(row)
    data["tools"] = json.loads(data.pop("tools_json") or "[]")
    data["enabled"] = bool(data["enabled"])
    return data


def public_connector(row: sqlite3.Row) -> dict[str, Any]:
    data = row_dict(row)
    data["config"] = json.loads(data.pop("config_json") or "{}")
    return data


def public_run(row: sqlite3.Row) -> dict[str, Any]:
    data = row_dict(row)
    data["logs"] = json.loads(data.pop("logs_json") or "[]")
    return data


def public_playbook(row: sqlite3.Row) -> dict[str, Any]:
    data = row_dict(row)
    data["tasks"] = json.loads(data.pop("tasks_json") or "[]")
    data["memories"] = json.loads(data.pop("memories_json") or "[]")
    data["agents"] = json.loads(data.pop("agents_json") or "[]")
    return data


def display_agent_name(agent_id: str) -> str:
    return {
        "researcher": "研究助手",
        "planner": "计划助手",
        "librarian": "资料管理员",
        "reviewer": "审核助手",
    }.get(agent_id, agent_id)


def display_note_title(note: sqlite3.Row) -> str:
    title = str(note["title"] or "").strip()
    if title and title != "无标题":
        return title
    body = str(note["body"] or "").strip()
    return safe_title(body[:80]) if body else "无标题"


def cite_location(item: dict[str, Any] | sqlite3.Row) -> str:
    if isinstance(item, sqlite3.Row):
        keys = item.keys()
        page_start = int(item["page_start"] or 0) if "page_start" in keys else 0
        page_end = int(item["page_end"] or 0) if "page_end" in keys else 0
    else:
        page_start = int(item.get("page_start") or 0)
        page_end = int(item.get("page_end") or 0)
    if not page_start:
        return "全文"
    if page_end and page_end != page_start:
        return f"第 {page_start}-{page_end} 页"
    return f"第 {page_start} 页"


def create_memory_candidates(conn: sqlite3.Connection, body: str, source_type: str, source_id: str) -> list[str]:
    created = now_iso()
    created_titles = []
    for line in body.splitlines():
        match = re.match(r"^(?:MEMORY[:：]?|记忆[:：]?|偏好[:：]?|事实[:：]?)(.+)$", line.strip(), re.I)
        if not match:
            continue
        text = match.group(1).strip(" -:：")
        if not text:
            continue
        memory_id = str(uuid.uuid4())
        title = safe_title(text[:80])
        conn.execute(
            """
            INSERT INTO memories(id, title, body, status, memory_type, confidence, source_type, source_id, created_at, updated_at)
            VALUES (?, ?, ?, 'candidate', 'fact', 0.62, ?, ?, ?, ?)
            """,
            (memory_id, title, text, source_type, source_id, created, created),
        )
        created_titles.append(title)
    return created_titles


def run_agent_locally(conn: sqlite3.Connection, agent: sqlite3.Row, user_input: str) -> tuple[str, list[dict[str, Any]]]:
    agent_id = agent["id"]
    logs: list[dict[str, Any]] = [{"step": "start", "detail": f"{agent['name']} 已启动", "time": now_iso()}]
    if agent_id == "researcher":
        query = user_input or "最近资料"
        contexts = search_chunks(conn, query, 5)
        logs.append({"step": "search", "detail": f"已选择 {len(contexts)} 个内容块", "time": now_iso()})
        if not contexts:
            return "没有匹配到本地资料。请先导入资料，或提供更具体的研究问题。", logs
        lines = [f"研究摘要：{query}", ""]
        for index, item in enumerate(contexts, start=1):
            text = re.sub(r"\s+", " ", item["content"]).strip()[:420]
            lines.append(f"[{index}] {item['title']} · {cite_location(item)}: {text}")
        return "\n".join(lines), logs
    if agent_id == "planner":
        tasks = conn.execute("SELECT * FROM tasks WHERE status != 'done' ORDER BY created_at DESC LIMIT 8").fetchall()
        logs.append({"step": "task_scan", "detail": f"{len(tasks)} 个待处理任务", "time": now_iso()})
        if not tasks:
            return "当前没有待处理任务。可以写一条包含 TODO: 或 待办: 的笔记，或创建计划笔记。", logs
        return "计划队列：\n" + "\n".join(f"- {row['title']}" for row in tasks), logs
    if agent_id == "librarian":
        failed = conn.execute("SELECT title, status, error, parser_engine FROM sources WHERE status != 'ready' ORDER BY created_at DESC LIMIT 8").fetchall()
        engines = conn.execute("SELECT parser_engine, count(*) AS count FROM sources GROUP BY parser_engine ORDER BY count DESC").fetchall()
        logs.append({"step": "source_audit", "detail": f"{len(failed)} 份资料需要处理", "time": now_iso()})
        lines = ["资料库审核：", "解析引擎："]
        lines.extend(f"- {row['parser_engine'] or '未知'}: {row['count']}" for row in engines)
        if failed:
            lines.append("需要处理：")
            lines.extend(f"- {row['title']} ({row['status']}): {row['error']}" for row in failed)
        return "\n".join(lines), logs
    if agent_id == "reviewer":
        candidates = conn.execute("SELECT * FROM memories WHERE status = 'candidate' ORDER BY created_at DESC LIMIT 8").fetchall()
        logs.append({"step": "memory_scan", "detail": f"{len(candidates)} 条候选记忆", "time": now_iso()})
        if not candidates:
            return "当前没有等待审核的记忆候选。", logs
        return "记忆候选：\n" + "\n".join(f"- {row['title']}: {row['body']}" for row in candidates), logs
    logs.append({"step": "noop", "detail": "这个智能体还没有本地运行器", "time": now_iso()})
    return "智能体模板已存在，但还没有实现对应的本地运行器。", logs


def local_answer(question: str, contexts: list[dict[str, Any]]) -> str:
    if not contexts:
        return "没有在当前资料库里找到足够相关的内容。可以先导入文件、写一条笔记，或换一个更具体的问题。"
    bullets = []
    for item in contexts[:4]:
        text = re.sub(r"\s+", " ", item["content"]).strip()
        bullets.append(f"- [{item['title']} · {cite_location(item)}] {text[:320]}")
    return "我先基于本地检索结果给出可追溯摘要。当前没有配置模型 API key，所以没有进行生成式推理。\n\n" + "\n".join(bullets)


def call_llm(settings: dict[str, str], question: str, contexts: list[dict[str, Any]]) -> str:
    if not settings["api_key"]:
        return local_answer(question, contexts)
    evidence = "\n\n".join(
        f"[{idx + 1}] {item['title']} / {cite_location(item)} / chunk {item['chunk_index']}\n{item['content'][:1200]}"
        for idx, item in enumerate(contexts[:6])
    )
    prompt = (
        "Answer in Chinese by default. Use only the provided sources for factual claims. "
        "If sources are insufficient, say so. Include bracket citations like [1].\n\n"
        f"Question: {question}\n\nSources:\n{evidence or 'No local sources found.'}"
    )
    payload = {
        "model": settings["model"],
        "messages": [
            {"role": "system", "content": "You produce concise, cited answers for a local-first personal AI workspace."},
            {"role": "user", "content": prompt},
        ],
        "temperature": 0.2,
    }
    req = urllib.request.Request(
        f"{settings['base_url']}/chat/completions",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json", "Authorization": f"Bearer {settings['api_key']}"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=45) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        return data["choices"][0]["message"]["content"].strip()
    except Exception as exc:
        return f"模型调用失败，已回退到本地摘要。\n\n错误：{exc}\n\n{local_answer(question, contexts)}"


def json_response(handler: BaseHTTPRequestHandler, payload: Any, status: int = 200) -> None:
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    handler.send_response(status)
    handler.send_header("Content-Type", "application/json; charset=utf-8")
    handler.send_header("Content-Length", str(len(body)))
    handler.end_headers()
    handler.wfile.write(body)


def internal_error(handler: BaseHTTPRequestHandler, exc: Exception) -> None:
    error_id = str(uuid.uuid4())[:8]
    print(f"[error:{error_id}] {exc}")
    traceback.print_exc()
    json_response(
        handler,
        {"detail": "服务处理失败。请刷新页面后重试。", "error_id": error_id},
        HTTPStatus.INTERNAL_SERVER_ERROR,
    )


def read_json(handler: BaseHTTPRequestHandler) -> dict[str, Any]:
    length = int(handler.headers.get("Content-Length", "0"))
    if not length:
        return {}
    return json.loads(handler.rfile.read(length).decode("utf-8"))


def route_parts(path: str) -> tuple[str, dict[str, list[str]]]:
    parsed = urllib.parse.urlparse(path)
    return parsed.path, urllib.parse.parse_qs(parsed.query)


class Handler(BaseHTTPRequestHandler):
    server_version = "PersonalAIOS/0.1"

    def log_message(self, fmt: str, *args: Any) -> None:
        print(f"{self.address_string()} - {fmt % args}")

    def do_GET(self) -> None:
        try:
            path, query = route_parts(self.path)
            if path == "/api/health":
                return json_response(self, {"status": "ok", "time": now_iso()})
            if path == "/api/dashboard":
                return self.dashboard()
            if path == "/api/projects":
                return self.list_projects()
            if path.startswith("/api/projects/"):
                return self.get_project(path.rsplit("/", 1)[-1])
            if path == "/api/collections":
                return self.list_projects()
            if path == "/api/playbooks":
                return self.list_playbooks()
            if path == "/api/settings":
                with connect() as conn:
                    return json_response(self, get_settings(conn))
            if path == "/api/models/discover":
                return json_response(self, discover_local_models())
            if path == "/api/sources":
                project_id = query.get("project_id", [""])[0]
                with connect() as conn:
                    if project_id:
                        rows = conn.execute(
                            """
                            SELECT sources.*
                            FROM collection_items ci
                            JOIN sources ON sources.id = ci.item_id
                            WHERE ci.collection_id = ? AND ci.item_type = 'source'
                            ORDER BY sources.created_at DESC
                            """,
                            (project_id,),
                        ).fetchall()
                    else:
                        rows = conn.execute("SELECT * FROM sources ORDER BY created_at DESC").fetchall()
                    return json_response(self, [source_summary(row) for row in rows])
            if path.startswith("/api/sources/"):
                return self.get_source(path.rsplit("/", 1)[-1])
            if path == "/api/search":
                q = query.get("q", [""])[0]
                limit = int(query.get("limit", ["12"])[0])
                with connect() as conn:
                    return json_response(self, {"query": q, "results": search_chunks(conn, q, min(max(limit, 1), 30))})
            if path == "/api/notes":
                project_id = query.get("project_id", [""])[0]
                with connect() as conn:
                    if project_id:
                        rows = conn.execute(
                            """
                            SELECT notes.*
                            FROM collection_items ci
                            JOIN notes ON notes.id = ci.item_id
                            WHERE ci.collection_id = ? AND ci.item_type = 'note'
                            ORDER BY notes.updated_at DESC
                            """,
                            (project_id,),
                        ).fetchall()
                    else:
                        rows = conn.execute("SELECT * FROM notes ORDER BY updated_at DESC").fetchall()
                    return json_response(self, [row_dict(row) for row in rows])
            if path == "/api/tasks":
                project_id = query.get("project_id", [""])[0]
                with connect() as conn:
                    if project_id:
                        rows = conn.execute(
                            """
                            SELECT tasks.*
                            FROM collection_items ci
                            JOIN tasks ON tasks.id = ci.item_id
                            WHERE ci.collection_id = ? AND ci.item_type = 'task'
                            ORDER BY tasks.created_at DESC
                            """,
                            (project_id,),
                        ).fetchall()
                    else:
                        rows = conn.execute("SELECT * FROM tasks ORDER BY created_at DESC").fetchall()
                    return json_response(self, [row_dict(row) for row in rows])
            if path == "/api/insights":
                return self.list_insights(query)
            if path == "/api/deliverables":
                return self.list_deliverables(query)
            if path == "/api/memories":
                return self.list_memories(query)
            if path == "/api/agents":
                return self.list_agents()
            if path == "/api/runs":
                return self.list_runs()
            if path == "/api/connectors":
                return self.list_connectors()
            if path.startswith("/api/conversations/"):
                return self.get_conversation(path.rsplit("/", 1)[-1])
            return self.static_file(path)
        except Exception as exc:
            return internal_error(self, exc)

    def do_POST(self) -> None:
        try:
            path, _query = route_parts(self.path)
            if path == "/api/settings":
                return self.save_settings(read_json(self))
            if path == "/api/projects":
                return self.create_project(read_json(self))
            if path == "/api/collections":
                return self.create_project(read_json(self))
            if path.startswith("/api/playbooks/") and path.endswith("/apply"):
                playbook_id = path.split("/")[-2]
                return self.apply_playbook(playbook_id)
            if path == "/api/sources/upload":
                return self.upload_source()
            if path == "/api/notes":
                return self.create_note(read_json(self))
            if path.startswith("/api/notes/") and path.endswith("/organize"):
                note_id = path.split("/")[-2]
                return self.organize_note(note_id, read_json(self))
            if path == "/api/deliverables":
                return self.create_deliverable(read_json(self))
            if path.startswith("/api/tasks/") and path.endswith("/toggle"):
                task_id = path.split("/")[-2]
                return self.toggle_task(task_id)
            if path == "/api/memories":
                return self.create_memory(read_json(self))
            if path.startswith("/api/memories/") and path.endswith("/status"):
                memory_id = path.split("/")[-2]
                return self.update_memory_status(memory_id, read_json(self))
            if path.startswith("/api/agents/") and path.endswith("/run"):
                agent_id = path.split("/")[-2]
                return self.run_agent(agent_id, read_json(self))
            if path.startswith("/api/connectors/") and path.endswith("/toggle"):
                connector_id = path.split("/")[-2]
                return self.toggle_connector(connector_id)
            if path == "/api/chat":
                return self.chat(read_json(self))
            return json_response(self, {"detail": "没有找到对应接口或页面"}, HTTPStatus.NOT_FOUND)
        except Exception as exc:
            return internal_error(self, exc)

    def do_DELETE(self) -> None:
        try:
            path, _query = route_parts(self.path)
            if path.startswith("/api/sources/"):
                return self.delete_source(path.rsplit("/", 1)[-1])
            return json_response(self, {"detail": "没有找到对应接口或页面"}, HTTPStatus.NOT_FOUND)
        except Exception as exc:
            return internal_error(self, exc)

    def static_file(self, path: str) -> None:
        if path in ("", "/"):
            file_path = PUBLIC_DIR / "index.html"
        elif path.startswith("/assets/"):
            file_path = PUBLIC_DIR / path.removeprefix("/assets/")
        else:
            file_path = PUBLIC_DIR / path.lstrip("/")
        if not file_path.resolve().is_relative_to(PUBLIC_DIR.resolve()) or not file_path.exists():
            return json_response(self, {"detail": "没有找到对应接口或页面"}, HTTPStatus.NOT_FOUND)
        body = file_path.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", mimetypes.guess_type(str(file_path))[0] or "application/octet-stream")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def dashboard(self) -> None:
        with connect() as conn:
            counts = {
                "sources": conn.execute("SELECT count(*) FROM sources").fetchone()[0],
                "chunks": conn.execute("SELECT count(*) FROM chunks").fetchone()[0],
                "notes": conn.execute("SELECT count(*) FROM notes").fetchone()[0],
                "tasks": conn.execute("SELECT count(*) FROM tasks WHERE status != 'done'").fetchone()[0],
                "memories": conn.execute("SELECT count(*) FROM memories WHERE status = 'approved'").fetchone()[0],
                "memory_candidates": conn.execute("SELECT count(*) FROM memories WHERE status = 'candidate'").fetchone()[0],
                "agents": conn.execute("SELECT count(*) FROM agents WHERE enabled = 1").fetchone()[0],
                "runs": conn.execute("SELECT count(*) FROM agent_runs").fetchone()[0],
                "parse_failures": conn.execute("SELECT count(*) FROM sources WHERE status != 'ready'").fetchone()[0],
            }
            events = [row_dict(row) for row in conn.execute("SELECT * FROM events ORDER BY created_at DESC LIMIT 12")]
            recent = [source_summary(row) for row in conn.execute("SELECT * FROM sources ORDER BY created_at DESC LIMIT 6")]
            tasks = [row_dict(row) for row in conn.execute("SELECT * FROM tasks WHERE status != 'done' ORDER BY created_at DESC LIMIT 8")]
            memories = [row_dict(row) for row in conn.execute("SELECT * FROM memories ORDER BY created_at DESC LIMIT 8")]
            agents = [public_agent(row) for row in conn.execute("SELECT * FROM agents ORDER BY name")]
            runs = [public_run(row) for row in conn.execute("SELECT agent_runs.*, agents.name AS agent_name FROM agent_runs JOIN agents ON agents.id = agent_runs.agent_id ORDER BY agent_runs.created_at DESC LIMIT 5")]
            connectors = [public_connector(row) for row in conn.execute("SELECT * FROM connectors ORDER BY name")]
            projects = [public_project(conn, row) for row in conn.execute("SELECT * FROM collections ORDER BY updated_at DESC LIMIT 8")]
            parser_stats = [row_dict(row) for row in conn.execute("SELECT COALESCE(NULLIF(parser_engine, ''), 'unknown') AS engine, count(*) AS count FROM sources GROUP BY engine ORDER BY count DESC")]
            json_response(self, {
                "counts": counts,
                "events": events,
                "projects": projects,
                "recent_sources": recent,
                "tasks": tasks,
                "memories": memories,
                "agents": agents,
                "runs": runs,
                "connectors": connectors,
                "parser_stats": parser_stats,
                "settings": get_settings(conn),
            })

    def save_settings(self, payload: dict[str, Any]) -> None:
        with connect() as conn:
            pairs = {
                "provider": str(payload.get("provider") or "openai-compatible").strip(),
                "base_url": str(payload.get("base_url") or "https://api.openai.com/v1").strip().rstrip("/"),
                "model": str(payload.get("model") or "gpt-4.1-mini").strip(),
            }
            api_key = str(payload.get("api_key") or "").strip()
            if api_key:
                pairs["api_key"] = api_key
            for key, value in pairs.items():
                conn.execute(
                    "INSERT INTO settings(key, value) VALUES (?, ?) ON CONFLICT(key) DO UPDATE SET value = excluded.value",
                    (key, value),
                )
            add_event(conn, "settings", "模型设置已更新", pairs["model"])
        with connect() as conn:
            json_response(self, get_settings(conn))

    def list_projects(self) -> None:
        with connect() as conn:
            rows = conn.execute("SELECT * FROM collections ORDER BY created_at DESC").fetchall()
            json_response(self, [public_project(conn, row) for row in rows])

    def create_project(self, payload: dict[str, Any]) -> None:
        name = str(payload.get("name") or "").strip()
        if not name:
            return json_response(self, {"detail": "项目名称不能为空"}, 400)
        project_id = str(uuid.uuid4())
        created = now_iso()
        with connect() as conn:
            conn.execute(
                "INSERT INTO collections(id, name, description, color, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?)",
                (project_id, name[:120], str(payload.get("goal") or payload.get("description") or "").strip(), str(payload.get("color") or "#2f5d46"), created, created),
            )
            add_event(conn, "project", f"已创建项目：{name[:80]}", str(payload.get("goal") or payload.get("description") or "").strip(), project_id)
            row = conn.execute("SELECT * FROM collections WHERE id = ?", (project_id,)).fetchone()
            json_response(self, public_project(conn, row))

    def get_project(self, project_id: str) -> None:
        with connect() as conn:
            project = conn.execute("SELECT * FROM collections WHERE id = ?", (project_id,)).fetchone()
            if not project:
                return json_response(self, {"detail": "没有找到这个项目"}, HTTPStatus.NOT_FOUND)
            sources = conn.execute(
                """
                SELECT sources.*
                FROM collection_items ci
                JOIN sources ON sources.id = ci.item_id
                WHERE ci.collection_id = ? AND ci.item_type = 'source'
                ORDER BY sources.created_at DESC
                LIMIT 8
                """,
                (project_id,),
            ).fetchall()
            notes = conn.execute(
                """
                SELECT notes.*
                FROM collection_items ci
                JOIN notes ON notes.id = ci.item_id
                WHERE ci.collection_id = ? AND ci.item_type = 'note'
                ORDER BY notes.updated_at DESC
                LIMIT 8
                """,
                (project_id,),
            ).fetchall()
            tasks = conn.execute(
                """
                SELECT tasks.*
                FROM collection_items ci
                JOIN tasks ON tasks.id = ci.item_id
                WHERE ci.collection_id = ? AND ci.item_type = 'task'
                ORDER BY tasks.created_at DESC
                LIMIT 12
                """,
                (project_id,),
            ).fetchall()
            memories = conn.execute(
                """
                SELECT memories.*
                FROM collection_items ci
                JOIN memories ON memories.id = ci.item_id
                WHERE ci.collection_id = ? AND ci.item_type = 'memory'
                ORDER BY memories.created_at DESC
                LIMIT 8
                """,
                (project_id,),
            ).fetchall()
            events = conn.execute(
                "SELECT * FROM events WHERE project_id = ? ORDER BY created_at DESC LIMIT 16",
                (project_id,),
            ).fetchall()
            insights = conn.execute(
                "SELECT * FROM insights WHERE project_id = ? ORDER BY created_at DESC LIMIT 16",
                (project_id,),
            ).fetchall()
            deliverables = conn.execute(
                "SELECT * FROM deliverables WHERE project_id = ? ORDER BY created_at DESC LIMIT 8",
                (project_id,),
            ).fetchall()
            json_response(self, {
                "project": public_project(conn, project),
                "sources": [source_summary(row) for row in sources],
                "notes": [row_dict(row) for row in notes],
                "tasks": [row_dict(row) for row in tasks],
                "memories": [row_dict(row) for row in memories],
                "events": [row_dict(row) for row in events],
                "insights": [row_dict(row) for row in insights],
                "deliverables": [row_dict(row) for row in deliverables],
            })

    def list_playbooks(self) -> None:
        with connect() as conn:
            rows = conn.execute("SELECT * FROM playbooks ORDER BY name").fetchall()
            json_response(self, [public_playbook(row) for row in rows])

    def apply_playbook(self, playbook_id: str) -> None:
        created = now_iso()
        with connect() as conn:
            playbook = conn.execute("SELECT * FROM playbooks WHERE id = ?", (playbook_id,)).fetchone()
            if not playbook:
                return json_response(self, {"detail": "没有找到这个场景方案"}, HTTPStatus.NOT_FOUND)
            data = public_playbook(playbook)
            collection = conn.execute("SELECT * FROM collections WHERE name = ?", (data["collection_name"],)).fetchone()
            if collection:
                collection_id = collection["id"]
            else:
                collection_id = str(uuid.uuid4())
                conn.execute(
                    "INSERT INTO collections(id, name, description, color, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?)",
                    (collection_id, data["collection_name"], data["scenario"], "#315f77", created, created),
                )
            task_ids = []
            for title in data["tasks"]:
                task_id = str(uuid.uuid4())
                conn.execute(
                    "INSERT INTO tasks(id, title, status, source_type, source_id, created_at, updated_at) VALUES (?, ?, 'open', 'playbook', ?, ?, ?)",
                    (task_id, title, playbook_id, created, created),
                )
                link_project_item(conn, collection_id, "task", task_id)
                task_ids.append(task_id)
            memory_ids = []
            for body in data["memories"]:
                memory_id = str(uuid.uuid4())
                conn.execute(
                    """
                    INSERT INTO memories(id, title, body, status, memory_type, confidence, source_type, source_id, created_at, updated_at)
                    VALUES (?, ?, ?, 'candidate', 'principle', 0.7, 'playbook', ?, ?, ?)
                    """,
                    (memory_id, safe_title(body[:80]), body, playbook_id, created, created),
                )
                link_project_item(conn, collection_id, "memory", memory_id)
                memory_ids.append(memory_id)
            run_id = str(uuid.uuid4())
            output = (
                f"已应用「{data['name']}」，适用对象：{data['audience']}。\n\n"
                f"工作区：{data['collection_name']}\n"
                f"初始任务：{len(task_ids)} 个\n"
                f"待审记忆：{len(memory_ids)} 条\n"
                f"建议智能体：{'、'.join(display_agent_name(agent_id) for agent_id in data['agents'])}"
            )
            conn.execute(
                """
                INSERT INTO agent_runs(id, agent_id, status, input, output, logs_json, created_at, updated_at)
                VALUES (?, 'planner', 'completed', ?, ?, ?, ?, ?)
                """,
                (
                    run_id,
                    f"应用场景方案 {playbook_id}",
                    output,
                    json.dumps([{"step": "apply_playbook", "detail": data["name"], "time": created}], ensure_ascii=False),
                    created,
                    created,
                ),
            )
            add_event(conn, "playbook", f"已应用项目模板：{data['name']}", data["audience"], collection_id)
            json_response(self, {"playbook": data, "collection_id": collection_id, "task_ids": task_ids, "memory_ids": memory_ids, "run_id": run_id})

    def parse_multipart(self) -> dict:
        """Parse multipart/form-data into {field: value}, files as dicts
        with filename/type/content. Replacement for the removed cgi module
        (Python 3.13+)."""
        content_type = self.headers.get("content-type", "")
        form: dict = {}
        if not content_type.startswith("multipart/form-data"):
            return form
        boundary_match = re.search(r'boundary=("?)([^";]+)\1', content_type)
        if not boundary_match:
            return form
        length = int(self.headers.get("content-length") or 0)
        body = self.rfile.read(length) if length else b""
        delimiter = b"--" + boundary_match.group(2).encode("utf-8")
        for raw_part in body.split(delimiter)[1:]:
            if raw_part.startswith(b"--"):
                continue  # closing delimiter
            part = raw_part
            if part.startswith(b"\r\n"):
                part = part[2:]
            if part.endswith(b"\r\n"):
                part = part[:-2]
            header_blob, separator, value = part.partition(b"\r\n\r\n")
            if not separator:
                continue
            headers = {}
            for line in header_blob.decode("utf-8", "replace").split("\r\n"):
                name, _, header_value = line.partition(":")
                headers[name.strip().lower()] = header_value.strip()
            disposition = headers.get("content-disposition", "")
            name_match = re.search(r'name="([^"]*)"', disposition)
            if not name_match:
                continue
            field = name_match.group(1)
            filename_match = re.search(r'filename="([^"]*)"', disposition)
            if filename_match:
                form[field] = {
                    "filename": filename_match.group(1),
                    "type": headers.get("content-type") or "",
                    "content": value,
                }
            else:
                form[field] = value.decode("utf-8", "replace")
        return form

    def upload_source(self) -> None:
        form = self.parse_multipart()
        file_item = form.get("file")
        if not isinstance(file_item, dict) or not file_item["filename"]:
            return json_response(self, {"detail": "请选择要导入的文件"}, 400)
        title_value = form.get("title", "")
        project_id = str(form.get("project_id", "") or "").strip()
        source_id = str(uuid.uuid4())
        original_name = Path(file_item["filename"]).name
        suffix = Path(original_name).suffix.lower()
        stored_path = UPLOAD_DIR / f"{source_id}{suffix}"
        content = file_item["content"]
        stored_path.write_bytes(content)
        checksum = hashlib.sha256(content).hexdigest()
        mime_type = file_item["type"] or mimetypes.guess_type(original_name)[0] or "application/octet-stream"
        source_title = safe_title(original_name, title_value)
        created = now_iso()

        try:
            with connect() as conn:
                existing = conn.execute("SELECT id, title FROM sources WHERE checksum = ?", (checksum,)).fetchone()
                if existing:
                    stored_path.unlink(missing_ok=True)
                    link_project_item(conn, project_id, "source", existing["id"])
                    add_event(conn, "source", f"资料已关联到项目：{existing['title']}", "重复文件未重新导入", project_id)
                    return json_response(self, {"duplicate": True, "source": row_dict(existing)})

            text, kind, quality = extract_text(stored_path, original_name, mime_type)
            status = "ready" if text else "empty"
            error = "" if text else ("PDF 解析器没有抽取到可用文本。" if kind == "pdf" else "没有找到可抽取文本。")
            chunks = evidence_chunks(text, kind)
            quality = enrich_quality(quality, chunks, kind)
            with connect() as conn:
                conn.execute(
                    """
                    INSERT INTO sources(id, title, original_name, kind, mime_type, file_path, checksum, size_bytes,
                                        status, error, text_content, parser_engine, page_count, char_count, quality_json,
                                        created_at, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        source_id,
                        source_title,
                        original_name,
                        kind,
                        mime_type,
                        str(stored_path),
                        checksum,
                        len(content),
                        status,
                        error,
                        text,
                        str(quality.get("engine") or ""),
                        int(quality.get("page_count") or 0),
                        len(text),
                        json.dumps(quality, ensure_ascii=False),
                        created,
                        created,
                    ),
                )
                for index, chunk in enumerate(chunks):
                    conn.execute(
                        "INSERT INTO chunks(source_id, chunk_index, title, content, page_start, page_end, created_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
                        (source_id, index, source_title, chunk["content"], int(chunk["page_start"] or 0), int(chunk["page_end"] or 0), created),
                    )
                link_project_item(conn, project_id, "source", source_id)
                add_event(conn, "source", f"已导入资料：{source_title}", f"{len(chunks)} 个内容块 · {quality.get('engine', 'unknown')}", project_id)
                source = conn.execute("SELECT * FROM sources WHERE id = ?", (source_id,)).fetchone()
                json_response(self, {"duplicate": False, "source": source_summary(source), "chunks": len(chunks)})
        except Exception:
            stored_path.unlink(missing_ok=True)
            raise

    def get_source(self, source_id: str) -> None:
        with connect() as conn:
            row = conn.execute("SELECT * FROM sources WHERE id = ?", (source_id,)).fetchone()
            if not row:
                return json_response(self, {"detail": "没有找到这份资料"}, HTTPStatus.NOT_FOUND)
            chunks = [row_dict(item) for item in conn.execute("SELECT id, chunk_index, content, page_start, page_end FROM chunks WHERE source_id = ? ORDER BY chunk_index", (source_id,))]
            data = row_dict(row)
            data["chunks"] = chunks
            json_response(self, data)

    def delete_source(self, source_id: str) -> None:
        with connect() as conn:
            row = conn.execute("SELECT * FROM sources WHERE id = ?", (source_id,)).fetchone()
            if not row:
                return json_response(self, {"detail": "没有找到这份资料"}, HTTPStatus.NOT_FOUND)
            Path(row["file_path"]).unlink(missing_ok=True)
            conn.execute("DELETE FROM sources WHERE id = ?", (source_id,))
            add_event(conn, "source", f"已删除资料：{row['title']}", "")
            json_response(self, {"status": "deleted"})

    def create_note(self, payload: dict[str, Any]) -> None:
        body = str(payload.get("body") or "").strip()
        if not body:
            return json_response(self, {"detail": "笔记内容不能为空"}, 400)
        note_id = str(uuid.uuid4())
        title_input = str(payload.get("title") or "").strip()
        title_source = "explicit" if title_input and title_input != "无标题" else "empty"
        title = safe_title(title_input) if title_source == "explicit" else "无标题"
        project_id = str(payload.get("project_id") or "").strip()
        created = now_iso()
        with connect() as conn:
            conn.execute(
                "INSERT INTO notes(id, title, body, title_source, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?)",
                (note_id, title, body, title_source, created, created),
            )
            link_project_item(conn, project_id, "note", note_id)
            created_tasks = []
            for task_title in extract_tasks(body):
                task_id = str(uuid.uuid4())
                conn.execute(
                    "INSERT INTO tasks(id, title, status, source_type, source_id, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
                    (task_id, task_title, "open", "note", note_id, created, created),
                )
                link_project_item(conn, project_id, "task", task_id)
                created_tasks.append(task_title)
            memories = create_memory_candidates(conn, body, "note", note_id)
            for memory_title in memories:
                memory = conn.execute(
                    "SELECT id FROM memories WHERE title = ? AND source_type = 'note' AND source_id = ? ORDER BY created_at DESC LIMIT 1",
                    (memory_title, note_id),
                ).fetchone()
                if memory:
                    link_project_item(conn, project_id, "memory", memory["id"])
            insights = save_insights(conn, project_id, note_id, extract_insights(body))
            add_event(conn, "note", f"已保存笔记：{title}", f"{len(created_tasks)} 个任务 · {len(memories)} 条待审记忆 · {len(insights)} 条洞察", project_id)
            note = conn.execute("SELECT * FROM notes WHERE id = ?", (note_id,)).fetchone()
            json_response(self, {"note": row_dict(note), "tasks": created_tasks, "memories": memories, "insights": insights})

    def organize_note(self, note_id: str, payload: dict[str, Any]) -> None:
        project_id = str(payload.get("project_id") or "").strip()
        with connect() as conn:
            note = conn.execute("SELECT * FROM notes WHERE id = ?", (note_id,)).fetchone()
            if not note:
                return json_response(self, {"detail": "没有找到这条笔记"}, HTTPStatus.NOT_FOUND)
            if not project_id:
                linked = conn.execute(
                    "SELECT collection_id FROM collection_items WHERE item_type = 'note' AND item_id = ? ORDER BY created_at DESC LIMIT 1",
                    (note_id,),
                ).fetchone()
                project_id = linked["collection_id"] if linked else ""
            conn.execute("DELETE FROM insights WHERE note_id = ? AND (? = '' OR project_id = ?)", (note_id, project_id, project_id))
            insights = save_insights(conn, project_id, note_id, extract_insights(note["body"]))
            add_event(conn, "insight", f"已整理笔记：{display_note_title(note)}", f"{len(insights)} 条结构化洞察", project_id)
            json_response(self, {"note": row_dict(note), "insights": insights})

    def list_insights(self, query: dict[str, list[str]]) -> None:
        project_id = query.get("project_id", [""])[0]
        kind = query.get("kind", [""])[0]
        sql = "SELECT * FROM insights"
        params: list[Any] = []
        conditions = []
        if project_id:
            conditions.append("project_id = ?")
            params.append(project_id)
        if kind:
            conditions.append("kind = ?")
            params.append(kind)
        if conditions:
            sql += " WHERE " + " AND ".join(conditions)
        sql += " ORDER BY created_at DESC"
        with connect() as conn:
            rows = conn.execute(sql, params).fetchall()
            json_response(self, [row_dict(row) for row in rows])

    def list_deliverables(self, query: dict[str, list[str]]) -> None:
        project_id = query.get("project_id", [""])[0]
        sql = "SELECT * FROM deliverables"
        params: list[Any] = []
        if project_id:
            sql += " WHERE project_id = ?"
            params.append(project_id)
        sql += " ORDER BY created_at DESC"
        with connect() as conn:
            rows = conn.execute(sql, params).fetchall()
            json_response(self, [row_dict(row) for row in rows])

    def create_deliverable(self, payload: dict[str, Any]) -> None:
        project_id = str(payload.get("project_id") or "").strip()
        template = str(payload.get("template") or "weekly").strip()
        if not project_id:
            return json_response(self, {"detail": "请选择项目"}, 400)
        with connect() as conn:
            project = conn.execute("SELECT * FROM collections WHERE id = ?", (project_id,)).fetchone()
            if not project:
                return json_response(self, {"detail": "没有找到这个项目"}, HTTPStatus.NOT_FOUND)
            body = build_deliverable(conn, project, template)
            deliverable_id = str(uuid.uuid4())
            created = now_iso()
            title = deliverable_title(project["name"], template)
            conn.execute(
                """
                INSERT INTO deliverables(id, project_id, template, title, body, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (deliverable_id, project_id, template, title, body, created, created),
            )
            add_event(conn, "deliverable", f"已生成交付物：{title}", template, project_id)
            row = conn.execute("SELECT * FROM deliverables WHERE id = ?", (deliverable_id,)).fetchone()
            json_response(self, row_dict(row))

    def toggle_task(self, task_id: str) -> None:
        with connect() as conn:
            row = conn.execute("SELECT * FROM tasks WHERE id = ?", (task_id,)).fetchone()
            if not row:
                return json_response(self, {"detail": "没有找到这个任务"}, HTTPStatus.NOT_FOUND)
            status = "done" if row["status"] != "done" else "open"
            conn.execute("UPDATE tasks SET status = ?, updated_at = ? WHERE id = ?", (status, now_iso(), task_id))
            json_response(self, row_dict(conn.execute("SELECT * FROM tasks WHERE id = ?", (task_id,)).fetchone()))

    def list_memories(self, query: dict[str, list[str]]) -> None:
        status = query.get("status", [""])[0]
        project_id = query.get("project_id", [""])[0]
        sql = "SELECT memories.* FROM memories"
        params: list[Any] = []
        conditions = []
        if project_id:
            sql += " JOIN collection_items ci ON ci.item_id = memories.id"
            conditions.append("ci.collection_id = ? AND ci.item_type = 'memory'")
            params.append(project_id)
        if status:
            conditions.append("memories.status = ?")
            params.append(status)
        if conditions:
            sql += " WHERE " + " AND ".join(conditions)
        sql += " ORDER BY memories.created_at DESC"
        with connect() as conn:
            rows = conn.execute(sql, params).fetchall()
            json_response(self, [row_dict(row) for row in rows])

    def create_memory(self, payload: dict[str, Any]) -> None:
        body = str(payload.get("body") or "").strip()
        if not body:
            return json_response(self, {"detail": "记忆内容不能为空"}, 400)
        memory_id = str(uuid.uuid4())
        title = safe_title(str(payload.get("title") or body[:80]))
        status = str(payload.get("status") or "candidate")
        project_id = str(payload.get("project_id") or "").strip()
        if status not in {"candidate", "approved", "archived"}:
            status = "candidate"
        created = now_iso()
        with connect() as conn:
            conn.execute(
                """
                INSERT INTO memories(id, title, body, status, memory_type, confidence, source_type, source_id, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, 'manual', '', ?, ?)
                """,
                (memory_id, title, body, status, str(payload.get("memory_type") or "fact"), float(payload.get("confidence") or 0.8), created, created),
            )
            link_project_item(conn, project_id, "memory", memory_id)
            add_event(conn, "memory", f"已保存记忆：{title}", status, project_id)
            row = conn.execute("SELECT * FROM memories WHERE id = ?", (memory_id,)).fetchone()
            json_response(self, row_dict(row))

    def update_memory_status(self, memory_id: str, payload: dict[str, Any]) -> None:
        status = str(payload.get("status") or "").strip()
        if status not in {"candidate", "approved", "archived"}:
            return json_response(self, {"detail": "记忆状态无效"}, 400)
        with connect() as conn:
            row = conn.execute("SELECT * FROM memories WHERE id = ?", (memory_id,)).fetchone()
            if not row:
                return json_response(self, {"detail": "没有找到这条记忆"}, HTTPStatus.NOT_FOUND)
            conn.execute("UPDATE memories SET status = ?, updated_at = ? WHERE id = ?", (status, now_iso(), memory_id))
            add_event(conn, "memory", f"记忆已更新为 {status}: {row['title']}", "")
            json_response(self, row_dict(conn.execute("SELECT * FROM memories WHERE id = ?", (memory_id,)).fetchone()))

    def list_agents(self) -> None:
        with connect() as conn:
            rows = conn.execute("SELECT * FROM agents ORDER BY name").fetchall()
            json_response(self, [public_agent(row) for row in rows])

    def run_agent(self, agent_id: str, payload: dict[str, Any]) -> None:
        created = now_iso()
        user_input = str(payload.get("input") or "").strip()
        run_id = str(uuid.uuid4())
        with connect() as conn:
            agent = conn.execute("SELECT * FROM agents WHERE id = ?", (agent_id,)).fetchone()
            if not agent:
                return json_response(self, {"detail": "没有找到这个智能体"}, HTTPStatus.NOT_FOUND)
            output, logs = run_agent_locally(conn, agent, user_input)
            conn.execute(
                """
                INSERT INTO agent_runs(id, agent_id, status, input, output, logs_json, created_at, updated_at)
                VALUES (?, ?, 'completed', ?, ?, ?, ?, ?)
                """,
                (run_id, agent_id, user_input, output, json.dumps(logs, ensure_ascii=False), created, now_iso()),
            )
            add_event(conn, "agent", f"已运行智能体：{agent['name']}", user_input[:120])
            row = conn.execute("SELECT agent_runs.*, agents.name AS agent_name FROM agent_runs JOIN agents ON agents.id = agent_runs.agent_id WHERE agent_runs.id = ?", (run_id,)).fetchone()
            json_response(self, public_run(row))

    def list_runs(self) -> None:
        with connect() as conn:
            rows = conn.execute("SELECT agent_runs.*, agents.name AS agent_name FROM agent_runs JOIN agents ON agents.id = agent_runs.agent_id ORDER BY agent_runs.created_at DESC").fetchall()
            json_response(self, [public_run(row) for row in rows])

    def list_connectors(self) -> None:
        with connect() as conn:
            rows = conn.execute("SELECT * FROM connectors ORDER BY name").fetchall()
            json_response(self, [public_connector(row) for row in rows])

    def toggle_connector(self, connector_id: str) -> None:
        with connect() as conn:
            row = conn.execute("SELECT * FROM connectors WHERE id = ?", (connector_id,)).fetchone()
            if not row:
                return json_response(self, {"detail": "没有找到这个连接器"}, HTTPStatus.NOT_FOUND)
            status = "enabled" if row["status"] != "enabled" else "planned"
            conn.execute("UPDATE connectors SET status = ?, updated_at = ? WHERE id = ?", (status, now_iso(), connector_id))
            add_event(conn, "connector", f"{row['name']} 已切换为 {status}", "")
            json_response(self, public_connector(conn.execute("SELECT * FROM connectors WHERE id = ?", (connector_id,)).fetchone()))

    def chat(self, payload: dict[str, Any]) -> None:
        question = str(payload.get("question") or "").strip()
        if not question:
            return json_response(self, {"detail": "问题不能为空"}, 400)
        created = now_iso()
        conversation_id = str(payload.get("conversation_id") or str(uuid.uuid4()))
        with connect() as conn:
            conv = conn.execute("SELECT id FROM conversations WHERE id = ?", (conversation_id,)).fetchone()
            if not conv:
                conn.execute("INSERT INTO conversations(id, title, created_at, updated_at) VALUES (?, ?, ?, ?)", (conversation_id, safe_title(question), created, created))
            contexts = search_chunks(conn, question, 8)
            answer = call_llm(get_secret_settings(conn), question, contexts)
            citations = [
                {
                    "source_id": item["source_id"],
                    "chunk_id": item["chunk_id"],
                    "title": item["title"],
                    "page_start": item.get("page_start", 0),
                    "page_end": item.get("page_end", 0),
                    "location": cite_location(item),
                    "snippet": re.sub(r"<.*?>", "", item["snippet"]),
                }
                for item in contexts[:6]
            ]
            conn.execute("INSERT INTO messages(id, conversation_id, role, content, citations_json, created_at) VALUES (?, ?, ?, ?, ?, ?)", (str(uuid.uuid4()), conversation_id, "user", question, "[]", created))
            conn.execute("INSERT INTO messages(id, conversation_id, role, content, citations_json, created_at) VALUES (?, ?, ?, ?, ?, ?)", (str(uuid.uuid4()), conversation_id, "assistant", answer, json.dumps(citations, ensure_ascii=False), now_iso()))
            conn.execute("UPDATE conversations SET updated_at = ? WHERE id = ?", (now_iso(), conversation_id))
            add_event(conn, "chat", f"已提问：{question[:80]}", f"{len(citations)} 条引用")
            json_response(self, {"conversation_id": conversation_id, "answer": answer, "citations": citations})

    def get_conversation(self, conversation_id: str) -> None:
        with connect() as conn:
            conv = conn.execute("SELECT * FROM conversations WHERE id = ?", (conversation_id,)).fetchone()
            if not conv:
                return json_response(self, {"detail": "没有找到这段对话"}, HTTPStatus.NOT_FOUND)
            messages = [row_dict(row) for row in conn.execute("SELECT * FROM messages WHERE conversation_id = ? ORDER BY created_at", (conversation_id,))]
            for message in messages:
                message["citations"] = json.loads(message.pop("citations_json") or "[]")
            json_response(self, {"conversation": row_dict(conv), "messages": messages})


def main() -> None:
    ensure_db()
    port = int(os.environ.get("PORT", "8000"))
    host = os.environ.get("HOST", "127.0.0.1")
    server = ThreadingHTTPServer((host, port), Handler)
    print(f"Personal AI OS listening on {host}:{port}")
    server.serve_forever()


if __name__ == "__main__":
    main()
