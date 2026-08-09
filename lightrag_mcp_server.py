#!/usr/bin/env python3
"""
MCP server for LightRAG.

Default workflow for this project:
- MCP process runs on VPS through SSH.
- LightRAG API is called locally on VPS at http://127.0.0.1:9621.
"""

import asyncio
import json
import os
from pathlib import Path
from typing import Any

import requests
from mcp import types
from mcp.server import Server
from mcp.server.stdio import stdio_server


LIGHTRAG_URL = os.getenv("LIGHTRAG_URL", "http://127.0.0.1:9621").rstrip("/")
LIGHTRAG_API_KEY = os.getenv("LIGHTRAG_API_KEY", "")
REQUEST_TIMEOUT = int(os.getenv("LIGHTRAG_TIMEOUT_SECONDS", "180"))
SOURCE_ID_PREFIX = "[[SOURCE_ID:"
SOURCE_ID_SUFFIX = "]]"

server = Server("lightrag-knowledge-base")


def _headers() -> dict[str, str]:
    headers = {"Content-Type": "application/json"}
    if LIGHTRAG_API_KEY:
        headers["X-API-Key"] = LIGHTRAG_API_KEY
    return headers


def _ok_response(data: Any) -> list[types.TextContent]:
    return [types.TextContent(type="text", text=json.dumps(data, ensure_ascii=False, indent=2))]


def _err_response(message: str) -> list[types.TextContent]:
    return [types.TextContent(type="text", text=message)]


def _auth_headers() -> dict[str, str] | None:
    if LIGHTRAG_API_KEY:
        return {"X-API-Key": LIGHTRAG_API_KEY}
    return None


def _safe_json(resp: requests.Response) -> Any:
    try:
        return resp.json()
    except Exception:
        return {"raw_text": resp.text}


def _source_marker(source_id: str) -> str:
    return f"{SOURCE_ID_PREFIX}{source_id}{SOURCE_ID_SUFFIX}"


def _extract_documents(payload: dict[str, Any]) -> list[dict[str, Any]]:
    statuses = payload.get("statuses", {})
    documents: list[dict[str, Any]] = []

    if isinstance(statuses, dict):
        for status_key, status_value in statuses.items():
            if isinstance(status_value, list):
                for item in status_value:
                    if isinstance(item, dict):
                        doc = dict(item)
                        doc.setdefault("status", status_key)
                        documents.append(doc)
            elif isinstance(status_value, dict):
                doc = dict(status_value)
                doc.setdefault("id", status_key)
                documents.append(doc)
    elif isinstance(statuses, list):
        for item in statuses:
            if isinstance(item, dict):
                documents.append(dict(item))

    return documents


def _get_doc_id(doc: dict[str, Any]) -> str | None:
    for key in ("id", "doc_id", "document_id"):
        value = doc.get(key)
        if isinstance(value, str) and value:
            return value
    return None


def _match_docs_by_file_name(documents: list[dict[str, Any]], file_name: str) -> list[str]:
    target_name = file_name.lower()
    doc_ids: list[str] = []

    for doc in documents:
        doc_path = str(doc.get("file_path", ""))
        if not doc_path:
            continue
        if Path(doc_path).name.lower() == target_name:
            doc_id = _get_doc_id(doc)
            if doc_id:
                doc_ids.append(doc_id)

    return doc_ids


def _match_docs_by_source_id(documents: list[dict[str, Any]], source_id: str) -> list[str]:
    source_marker = _source_marker(source_id).lower()
    source_id_lc = source_id.lower()
    doc_ids: list[str] = []

    for doc in documents:
        doc_id = _get_doc_id(doc)
        if not doc_id:
            continue
        haystack = " ".join(
            [
                str(doc.get("file_path", "")),
                str(doc.get("content_summary", "")),
                str(doc.get("description", "")),
            ]
        ).lower()
        if source_marker in haystack or source_id_lc in haystack:
            doc_ids.append(doc_id)

    return doc_ids


def _delete_documents_by_ids(doc_ids: list[str]) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    for doc_id in doc_ids:
        resp = requests.delete(
            f"{LIGHTRAG_URL}/documents/{doc_id}",
            headers=_auth_headers(),
            timeout=REQUEST_TIMEOUT,
        )
        results.append({"doc_id": doc_id, "status_code": resp.status_code, "data": _safe_json(resp)})
    return results


@server.list_tools()
async def list_tools() -> list[types.Tool]:
    return [
        types.Tool(
            name="search_knowledge_base",
            description=(
                "Search in LightRAG knowledge base. "
                "Use for architecture decisions, notes, docs, troubleshooting context."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Question or topic to search"},
                    "mode": {
                        "type": "string",
                        "enum": ["naive", "local", "global", "hybrid", "mix"],
                        "default": "mix",
                        "description": "Retrieval mode. Recommended default: mix",
                    },
                    "only_need_context": {
                        "type": "boolean",
                        "default": False,
                        "description": "Return context snippets instead of final generated answer",
                    },
                },
                "required": ["query"],
            },
        ),
        types.Tool(
            name="add_text_to_knowledge_base",
            description="Add raw text note to LightRAG knowledge base.",
            inputSchema={
                "type": "object",
                "properties": {
                    "text": {"type": "string", "description": "Text content to store"},
                    "description": {"type": "string", "description": "Optional title/summary"},
                },
                "required": ["text"],
            },
        ),
        types.Tool(
            name="upsert_text_to_knowledge_base",
            description=(
                "Upsert text note in LightRAG by source_id: "
                "delete old version(s) for source_id, then add new text."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "text": {"type": "string", "description": "Text content to store"},
                    "source_id": {
                        "type": "string",
                        "description": "Stable source key, for example local file path",
                    },
                    "description": {"type": "string", "description": "Optional title/summary"},
                    "replace_existing": {
                        "type": "boolean",
                        "default": True,
                        "description": "Delete old docs with same source_id before insert",
                    },
                },
                "required": ["text", "source_id"],
            },
        ),
        types.Tool(
            name="add_file_to_knowledge_base",
            description="Add local file to LightRAG knowledge base by file path on server.",
            inputSchema={
                "type": "object",
                "properties": {
                    "file_path": {
                        "type": "string",
                        "description": "Absolute path on server, for example /opt/LightRAG/data/inputs/my.md",
                    },
                    "description": {"type": "string", "description": "Optional title/summary"},
                    "replace_existing": {
                        "type": "boolean",
                        "default": True,
                        "description": "Delete old docs with the same file name before upload",
                    },
                },
                "required": ["file_path"],
            },
        ),
        types.Tool(
            name="scan_inputs_folder",
            description="Trigger /documents/scan to enqueue files from inputs folder.",
            inputSchema={"type": "object", "properties": {}},
        ),
        types.Tool(
            name="knowledge_base_status",
            description="Check LightRAG health and pipeline status.",
            inputSchema={"type": "object", "properties": {}},
        ),
        types.Tool(
            name="list_documents",
            description="List documents and statuses from LightRAG.",
            inputSchema={"type": "object", "properties": {}},
        ),
    ]


@server.call_tool()
async def call_tool(name: str, arguments: dict[str, Any]) -> list[types.TextContent]:
    try:
        if name == "search_knowledge_base":
            payload = {
                "query": arguments["query"],
                "mode": arguments.get("mode", "mix"),
                "only_need_context": bool(arguments.get("only_need_context", False)),
            }
            resp = requests.post(
                f"{LIGHTRAG_URL}/query",
                json=payload,
                headers=_headers(),
                timeout=REQUEST_TIMEOUT,
            )
            return _ok_response({"status_code": resp.status_code, "data": resp.json()})

        if name == "add_text_to_knowledge_base":
            description = arguments.get("description", "")
            payload = {
                "text": arguments["text"],
                "description": description,
                "file_source": description or "mcp:text",
            }
            resp = requests.post(
                f"{LIGHTRAG_URL}/documents/text",
                json=payload,
                headers=_headers(),
                timeout=REQUEST_TIMEOUT,
            )
            return _ok_response({"status_code": resp.status_code, "data": resp.json()})

        if name == "upsert_text_to_knowledge_base":
            source_id = arguments["source_id"]
            replace_existing = bool(arguments.get("replace_existing", True))
            deleted_doc_ids: list[str] = []
            delete_results: list[dict[str, Any]] = []

            if replace_existing:
                docs_resp = requests.get(
                    f"{LIGHTRAG_URL}/documents",
                    headers=_auth_headers(),
                    timeout=60,
                )
                docs_payload = _safe_json(docs_resp)
                if docs_resp.status_code == 200 and isinstance(docs_payload, dict):
                    documents = _extract_documents(docs_payload)
                    deleted_doc_ids = _match_docs_by_source_id(documents, source_id)
                    if deleted_doc_ids:
                        delete_results = _delete_documents_by_ids(deleted_doc_ids)

            source_marker = _source_marker(source_id)
            text = arguments["text"]
            if source_marker not in text:
                text = f"{source_marker}\n{text}"

            payload = {
                "text": text,
                "description": arguments.get("description", source_id),
                "file_source": source_id,
            }
            resp = requests.post(
                f"{LIGHTRAG_URL}/documents/text",
                json=payload,
                headers=_headers(),
                timeout=REQUEST_TIMEOUT,
            )
            return _ok_response(
                {
                    "status_code": resp.status_code,
                    "data": _safe_json(resp),
                    "replace_existing": replace_existing,
                    "deleted_doc_ids": deleted_doc_ids,
                    "delete_results": delete_results,
                    "source_id": source_id,
                }
            )

        if name == "add_file_to_knowledge_base":
            file_path = Path(arguments["file_path"])
            if not file_path.exists() or not file_path.is_file():
                return _err_response(f"File not found: {file_path}")

            replace_existing = bool(arguments.get("replace_existing", True))
            deleted_doc_ids: list[str] = []
            delete_results: list[dict[str, Any]] = []

            if replace_existing:
                docs_resp = requests.get(
                    f"{LIGHTRAG_URL}/documents",
                    headers=_auth_headers(),
                    timeout=60,
                )
                docs_payload = _safe_json(docs_resp)
                if docs_resp.status_code == 200 and isinstance(docs_payload, dict):
                    documents = _extract_documents(docs_payload)
                    deleted_doc_ids = _match_docs_by_file_name(documents, file_path.name)
                    if deleted_doc_ids:
                        delete_results = _delete_documents_by_ids(deleted_doc_ids)

            with file_path.open("rb") as fh:
                files = {"file": (file_path.name, fh)}
                data = {"description": arguments.get("description", file_path.name)}
                resp = requests.post(
                    f"{LIGHTRAG_URL}/documents/file",
                    files=files,
                    data=data,
                    headers=_auth_headers(),
                    timeout=REQUEST_TIMEOUT,
                )
                if resp.status_code == 404:
                    fh.seek(0)
                    files = {"file": (file_path.name, fh)}
                    resp = requests.post(
                        f"{LIGHTRAG_URL}/documents/upload",
                        files=files,
                        data=data,
                        headers=_auth_headers(),
                        timeout=REQUEST_TIMEOUT,
                    )
            return _ok_response(
                {
                    "status_code": resp.status_code,
                    "data": _safe_json(resp),
                    "replace_existing": replace_existing,
                    "deleted_doc_ids": deleted_doc_ids,
                    "delete_results": delete_results,
                }
            )

        if name == "scan_inputs_folder":
            resp = requests.post(
                f"{LIGHTRAG_URL}/documents/scan",
                headers=_auth_headers(),
                timeout=REQUEST_TIMEOUT,
            )
            return _ok_response({"status_code": resp.status_code, "data": _safe_json(resp)})

        if name == "knowledge_base_status":
            health = requests.get(
                f"{LIGHTRAG_URL}/health",
                headers=_auth_headers(),
                timeout=30,
            )
            pipeline = requests.get(
                f"{LIGHTRAG_URL}/documents/pipeline_status",
                headers=_auth_headers(),
                timeout=30,
            )
            return _ok_response(
                {
                    "health_status_code": health.status_code,
                    "health": _safe_json(health),
                    "pipeline_status_code": pipeline.status_code,
                    "pipeline": _safe_json(pipeline),
                }
            )

        if name == "list_documents":
            resp = requests.get(
                f"{LIGHTRAG_URL}/documents",
                headers=_auth_headers(),
                timeout=60,
            )
            return _ok_response({"status_code": resp.status_code, "data": _safe_json(resp)})

        return _err_response(f"Unknown tool: {name}")
    except Exception as exc:
        return _err_response(f"LightRAG MCP error: {exc}")


async def main() -> None:
    async with stdio_server() as (read_stream, write_stream):
        await server.run(read_stream, write_stream, server.create_initialization_options())


if __name__ == "__main__":
    asyncio.run(main())
