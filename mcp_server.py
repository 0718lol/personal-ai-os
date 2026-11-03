"""只读 MCP server: 通过 stdio JSON-RPC 暴露知识库检索与 wiki 阅读能力。

严格只读: 以 SQLite 只读模式打开数据库, 不提供任何写操作工具。
启动: python mcp_server.py (数据目录由 PERSONAL_AI_OS_DATA_DIR 控制, 默认 ./data)
"""
from __future__ import annotations

import json
import os
import sqlite3
import sys
from pathlib import Path
from typing import Any

import retrieval
import wiki

ROOT = Path(__file__).resolve().parent
DATA_DIR = Path(os.environ.get("PERSONAL_AI_OS_DATA_DIR", str(ROOT / "data"))).expanduser()
DB_PATH = DATA_DIR / "personal_ai_os.sqlite3"

PROTOCOL_VERSION = "2024-11-05"
SERVER_INFO = {"name": "personal-ai-os-readonly", "version": "1.0.0"}

TOOLS: list[dict[str, Any]] = [
    {
        "name": "wiki_search",
        "description": "在知识库中检索, 返回带置信档(confident/low/abstain)的证据片段。",
        "inputSchema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "检索问题, 支持中英文"},
                "limit": {"type": "integer", "description": "返回片段数, 默认 8", "default": 8},
            },
            "required": ["query"],
        },
    },
    {
        "name": "wiki_read_page",
        "description": "读取一个知识页面的正文、证据、结论与修订历史。",
        "inputSchema": {
            "type": "object",
            "properties": {"slug": {"type": "string", "description": "页面 slug"}},
            "required": ["slug"],
        },
    },
    {
        "name": "wiki_list_pages",
        "description": "列出全部知识页面(标题/slug/类型/证据数)。",
        "inputSchema": {"type": "object", "properties": {}},
    },
    {
        "name": "wiki_lint",
        "description": "列出知识库检查问题(断链/孤立页/陈旧证据/疑似矛盾等)及处理状态。",
        "inputSchema": {"type": "object", "properties": {}},
    },
]


def _connect() -> sqlite3.Connection:
    if not DB_PATH.exists():
        raise FileNotFoundError(f"数据库不存在: {DB_PATH}")
    conn = sqlite3.connect(f"file:{DB_PATH}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    return conn


def _text_result(payload: Any) -> dict[str, Any]:
    return {"content": [{"type": "text", "text": json.dumps(payload, ensure_ascii=False, default=str)}]}


def call_tool(name: str, args: dict[str, Any]) -> dict[str, Any]:
    """执行只读工具调用, 返回 MCP tools/call 响应。"""
    conn = _connect()
    try:
        if name == "wiki_search":
            query = str(args.get("query", "")).strip()
            if not query:
                raise ValueError("query 不能为空")
            limit = max(1, min(int(args.get("limit", 8) or 8), 20))
            results = retrieval.search_chunks(conn, query, limit=limit)
            level, reason = retrieval.confidence(conn, results, query)
            return _text_result({"confidence": level, "reason": reason, "results": results})
        if name == "wiki_read_page":
            slug = str(args.get("slug", "")).strip()
            page = wiki.get_page(conn, slug)
            if page is None:
                raise ValueError(f"页面不存在: {slug}")
            return _text_result(page)
        if name == "wiki_list_pages":
            return _text_result(wiki.list_pages(conn))
        if name == "wiki_lint":
            return _text_result(wiki.lint(conn))
        raise ValueError(f"未知工具: {name}")
    finally:
        conn.close()


def _handle(message: dict[str, Any]) -> dict[str, Any] | None:
    method = message.get("method", "")
    msg_id = message.get("id")
    if method == "initialize":
        return {"jsonrpc": "2.0", "id": msg_id, "result": {"protocolVersion": PROTOCOL_VERSION, "capabilities": {"tools": {}}, "serverInfo": SERVER_INFO}}
    if method == "notifications/initialized":
        return None
    if method == "ping":
        return {"jsonrpc": "2.0", "id": msg_id, "result": {}}
    if method == "tools/list":
        return {"jsonrpc": "2.0", "id": msg_id, "result": {"tools": TOOLS}}
    if method == "tools/call":
        params = message.get("params") or {}
        try:
            result = call_tool(str(params.get("name", "")), params.get("arguments") or {})
            return {"jsonrpc": "2.0", "id": msg_id, "result": result}
        except Exception as exc:  # noqa: BLE001 - 错误需回传客户端
            return {"jsonrpc": "2.0", "id": msg_id, "result": {"content": [{"type": "text", "text": f"错误: {exc}"}], "isError": True}}
    if msg_id is not None:
        return {"jsonrpc": "2.0", "id": msg_id, "error": {"code": -32601, "message": f"未知方法: {method}"}}
    return None


def serve(stream_in=None, stream_out=None) -> None:
    stream_in = stream_in or sys.stdin
    stream_out = stream_out or sys.stdout
    for line in stream_in:
        line = line.strip()
        if not line:
            continue
        try:
            message = json.loads(line)
        except json.JSONDecodeError:
            continue
        response = _handle(message)
        if response is not None:
            stream_out.write(json.dumps(response, ensure_ascii=False) + "\n")
            stream_out.flush()


if __name__ == "__main__":
    serve()
