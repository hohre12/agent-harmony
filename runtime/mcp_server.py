#!/usr/bin/env python3
"""Agent Harmony MCP Server — pipeline orchestrator and memory tools.

Protocol: MCP (Model Context Protocol) over stdio using JSON-RPC 2.0.

Usage (via .mcp.json):
  {"mcpServers": {"harmony": {"command": "setup.sh", "args": ["mcp_server.py"]}}}
"""

from __future__ import annotations

import json
import os
import sys
import traceback
from typing import Callable

RUNTIME_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, RUNTIME_DIR)


# ====================================================================== #
#  Tool definitions (7 tools)
# ====================================================================== #

TOOLS = [
    # --- Pipeline ---
    {
        "name": "harmony_pipeline_start",
        "description": "Start or resume the harmony pipeline. Call this when user says /agent-harmony:harmony. Returns the first step instruction.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "user_request": {"type": "string", "description": "What the user wants to build (may be empty)", "default": ""},
                "state_path": {"type": "string", "default": ".harmony/state.json"},
            },
        },
    },
    {
        "name": "harmony_pipeline_next",
        "description": "Report step result and get next instruction. Call after completing a code/mechanical step.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "step_result": {"type": "string", "description": "JSON with step result"},
                "state_path": {"type": "string", "default": ".harmony/state.json"},
            },
            "required": ["step_result"],
        },
    },
    {
        "name": "harmony_pipeline_respond",
        "description": "Pass user's answer during interactive steps (interview, PRD review, escalation). Returns next instruction.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "user_input": {"type": "string", "description": "The user's response"},
                "state_path": {"type": "string", "default": ".harmony/state.json"},
            },
            "required": ["user_input"],
        },
    },
    # --- Template ---
    {
        "name": "harmony_generate_template",
        "description": "Generate a SKILL.md file from configuration. Returns the complete file content to write to disk.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "template_name": {"type": "string", "enum": ["team-executor"]},
                "config_json": {"type": "string", "description": "JSON config for template generation"},
            },
            "required": ["template_name", "config_json"],
        },
    },
    # --- Memory ---
    {
        "name": "harmony_memory_save",
        "description": "Save an agent's learning to persistent memory. Memories survive across sessions.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "agent_role": {"type": "string", "description": "Agent role (e.g., 'backend-agent')"},
                "category": {"type": "string", "enum": ["pattern", "mistake", "insight", "domain", "decision"]},
                "content": {"type": "string", "description": "The learning to remember"},
                "project": {"type": "string", "default": ""},
                "tags": {"type": "array", "items": {"type": "string"}},
            },
            "required": ["agent_role", "category", "content"],
        },
    },
    {
        "name": "harmony_memory_load",
        "description": "Load an agent's memories. Returns previous learnings for context injection.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "agent_role": {"type": "string", "description": "Agent role"},
                "project": {"type": "string", "default": ""},
                "category": {"type": "string"},
                "limit": {"type": "integer", "default": 20},
            },
            "required": ["agent_role"],
        },
    },
    # --- Checkpoint ---
    {
        "name": "harmony_checkpoint_save",
        "description": "Save a mid-task checkpoint so work survives rate limits.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "task_id": {"type": "string", "description": "Current task ID"},
                "checkpoint_step": {"type": "string", "description": "Human-readable step name"},
                "checkpoint_data": {"type": "string", "default": ""},
                "state_path": {"type": "string", "default": ".harmony/state.json"},
            },
            "required": ["task_id", "checkpoint_step"],
        },
    },
]


# ====================================================================== #
#  Tool handlers
# ====================================================================== #


def _validate_path(path: str) -> str:
    """Validate that a path is safe — no traversal, no absolute paths, no symlink escape."""
    from pathlib import Path as P, PurePosixPath
    # Check each path component for traversal
    for part in PurePosixPath(path).parts:
        if part == "..":
            raise ValueError(f"Path traversal denied: {path}")
    if path.startswith("/"):
        raise ValueError(f"Absolute path denied: {path}")
    resolved = P(path).resolve()
    cwd = P.cwd().resolve()
    if resolved != cwd and not str(resolved).startswith(str(cwd) + os.sep):
        raise ValueError(f"Path escapes project directory: {path}")
    return path


def _validate_agent_role(role: str) -> str:
    """Validate agent_role — allowlist safe characters only."""
    if not role or not isinstance(role, str):
        raise ValueError("agent_role must be a non-empty string")
    import re
    if not re.match(r'^[a-zA-Z0-9_-]+$', role):
        raise ValueError(f"Invalid agent_role: {role} — only [a-zA-Z0-9_-] allowed")
    if len(role) > 100:
        raise ValueError(f"agent_role too long: {len(role)} chars")
    return role


def _handle_pipeline_start(arguments: dict) -> str:
    from harmony.orchestrator.pipeline import start_pipeline
    return start_pipeline(
        user_request=arguments.get("user_request", ""),
        state_path=arguments.get("state_path", ".harmony/state.json"),
    )


def _handle_pipeline_next(arguments: dict) -> str:
    from harmony.orchestrator.pipeline import pipeline_next
    return pipeline_next(
        step_result_json=arguments["step_result"],
        state_path=arguments.get("state_path", ".harmony/state.json"),
    )


def _handle_pipeline_respond(arguments: dict) -> str:
    from harmony.orchestrator.pipeline import pipeline_respond
    return pipeline_respond(
        user_input=arguments["user_input"],
        state_path=arguments.get("state_path", ".harmony/state.json"),
    )


def _handle_generate_template(arguments: dict) -> str:
    from harmony.orchestrator.templates import generate_template
    return generate_template(
        template_name=arguments["template_name"],
        config_json=arguments["config_json"],
    )


def _handle_memory_save(arguments: dict) -> str:
    _validate_agent_role(arguments["agent_role"])
    from harmony.memory.store import AgentMemory
    mem = AgentMemory.load(arguments["agent_role"])
    entry = mem.add(
        category=arguments["category"],
        content=arguments["content"],
        project=arguments.get("project", ""),
        tags=arguments.get("tags", []),
    )
    if entry:
        removed = mem.consolidate(max_entries=100)
        mem.save()
        return json.dumps({"saved": True, "id": entry.id, "total": len(mem.entries), "consolidated": removed})
    return json.dumps({"saved": False, "reason": "duplicate"})


def _handle_memory_load(arguments: dict) -> str:
    _validate_agent_role(arguments["agent_role"])
    from harmony.memory.store import AgentMemory
    from dataclasses import asdict
    mem = AgentMemory.load(arguments["agent_role"])
    entries = mem.query(
        category=arguments.get("category"),
        project=arguments.get("project"),
        limit=arguments.get("limit", 20),
    )
    return json.dumps({
        "agent_role": arguments["agent_role"],
        "entries": [asdict(e) for e in entries],
        "context_prompt": mem.context_prompt(arguments.get("project", "")),
        "stats": mem.stats(),
    }, indent=2, ensure_ascii=False)


def _handle_checkpoint_save(arguments: dict) -> str:
    from harmony.orchestrator.state import SessionState
    sp = arguments.get("state_path", ".harmony/state.json")
    state = SessionState.load(sp)
    if state is None:
        return "ERROR: No session state found."
    task = state._task_by_id(arguments["task_id"])
    task.checkpoint_step = arguments["checkpoint_step"]
    task.checkpoint = arguments.get("checkpoint_data", "")
    state.save(sp)
    return f"Checkpoint saved for task {arguments['task_id']}: {arguments['checkpoint_step']}"


_TOOL_HANDLERS: dict[str, Callable[[dict], str]] = {
    "harmony_pipeline_start": _handle_pipeline_start,
    "harmony_pipeline_next": _handle_pipeline_next,
    "harmony_pipeline_respond": _handle_pipeline_respond,
    "harmony_generate_template": _handle_generate_template,
    "harmony_memory_save": _handle_memory_save,
    "harmony_memory_load": _handle_memory_load,
    "harmony_checkpoint_save": _handle_checkpoint_save,
}


def handle_tool_call(name: str, arguments: dict) -> str:
    """Dispatch a tool call and return the result as a string."""
    for key in ("state_path",):
        if key in arguments:
            _validate_path(arguments[key])

    handler = _TOOL_HANDLERS.get(name)
    if handler:
        return handler(arguments)
    return f"Unknown tool: {name}"


# ====================================================================== #
#  MCP Protocol (JSON-RPC 2.0 over stdio)
# ====================================================================== #


def send_response(response: dict):
    msg = json.dumps(response, ensure_ascii=False)
    sys.stdout.write(msg + "\n")
    sys.stdout.flush()


def handle_message(message: dict) -> dict | None:
    method = message.get("method", "")
    msg_id = message.get("id")
    params = message.get("params", {})

    if method == "initialize":
        return {
            "jsonrpc": "2.0",
            "id": msg_id,
            "result": {
                "protocolVersion": "2024-11-05",
                "capabilities": {"tools": {}},
                "serverInfo": {"name": "agent-harmony", "version": "4.0.0"},
            },
        }

    if method == "notifications/initialized":
        return None

    if method == "tools/list":
        return {"jsonrpc": "2.0", "id": msg_id, "result": {"tools": TOOLS}}

    if method == "tools/call":
        tool_name = params.get("name", "")
        arguments = params.get("arguments", {})
        try:
            result_text = handle_tool_call(tool_name, arguments)
            return {
                "jsonrpc": "2.0", "id": msg_id,
                "result": {"content": [{"type": "text", "text": result_text}]},
            }
        except Exception as e:
            return {
                "jsonrpc": "2.0", "id": msg_id,
                "result": {"content": [{"type": "text", "text": f"Error: {e}\n{traceback.format_exc()}"}], "isError": True},
            }

    if method == "ping":
        return {"jsonrpc": "2.0", "id": msg_id, "result": {}}

    if msg_id is not None:
        return {"jsonrpc": "2.0", "id": msg_id, "error": {"code": -32601, "message": f"Method not found: {method}"}}

    return None


def main():
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            message = json.loads(line)
        except json.JSONDecodeError:
            send_response({"jsonrpc": "2.0", "id": None, "error": {"code": -32700, "message": "Parse error"}})
            continue
        response = handle_message(message)
        if response is not None:
            send_response(response)


if __name__ == "__main__":
    main()
