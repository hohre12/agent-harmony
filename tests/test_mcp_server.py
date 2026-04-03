"""Tests for the MCP server — protocol and tool dispatch."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

# Import the MCP server handler directly
from mcp_server import handle_message, handle_tool_call, TOOLS


class TestProtocol:
    def test_initialize(self):
        resp = handle_message({"jsonrpc": "2.0", "method": "initialize", "params": {}, "id": 1})
        assert resp["id"] == 1
        assert resp["result"]["serverInfo"]["name"] == "agent-harmony"
        assert resp["result"]["serverInfo"]["version"] == "1.0.3"

    def test_tools_list(self):
        resp = handle_message({"jsonrpc": "2.0", "method": "tools/list", "id": 2})
        tools = resp["result"]["tools"]
        assert len(tools) == 6
        names = {t["name"] for t in tools}
        assert "harmony_pipeline_start" in names
        assert "harmony_pipeline_next" in names
        assert "harmony_pipeline_respond" in names
        assert "harmony_memory_save" in names
        assert "harmony_memory_load" in names
        assert "harmony_checkpoint_save" in names

    def test_no_removed_tools(self):
        names = {t["name"] for t in TOOLS}
        assert "harmony_ontology_validate" not in names
        assert "harmony_orchestrate_init" not in names
        assert "harmony_orchestrate_next" not in names

    def test_ping(self):
        resp = handle_message({"jsonrpc": "2.0", "method": "ping", "id": 3})
        assert resp["result"] == {}

    def test_unknown_method(self):
        resp = handle_message({"jsonrpc": "2.0", "method": "unknown/method", "id": 4})
        assert "error" in resp

    def test_notification_no_response(self):
        resp = handle_message({"jsonrpc": "2.0", "method": "notifications/initialized"})
        assert resp is None


class TestToolCalls:
    def test_unknown_tool(self):
        result = handle_tool_call("nonexistent_tool", {})
        assert "Unknown tool" in result

    def test_memory_save_and_load(self, tmp_path: Path, monkeypatch):
        import harmony.memory.store as store_mod
        monkeypatch.setattr(store_mod, "MEMORY_DIR", str(tmp_path))

        import uuid
        unique = uuid.uuid4().hex[:8]
        result = handle_tool_call("harmony_memory_save", {
            "agent_role": f"test-agent-{unique}",
            "category": "pattern",
            "content": f"Unique learning {unique}",
        })
        data = json.loads(result)
        assert data["saved"] is True

        result = handle_tool_call("harmony_memory_load", {"agent_role": f"test-agent-{unique}"})
        data = json.loads(result)
        assert len(data["entries"]) == 1

    def test_path_traversal_blocked(self):
        try:
            result = handle_tool_call("harmony_pipeline_start", {"user_request": "test", "state_path": "../../../etc/state.json"})
            assert False, "Should have raised ValueError"
        except Exception as e:
            assert "traversal" in str(e).lower()

    def test_pipeline_start(self, tmp_path: Path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        result = handle_tool_call("harmony_pipeline_start", {
            "user_request": "build a blog",
            "state_path": ".harmony/state.json",
        })
        data = json.loads(result)
        assert data["step"] == "init"
        assert "blog" in data["prompt"]

    def test_pipeline_next_invalid_json(self, tmp_path: Path, monkeypatch):
        from harmony.orchestrator.state import SessionState
        monkeypatch.chdir(tmp_path)
        SessionState(session_id="test", pipeline_phase="setup").save(".harmony/state.json")

        result = handle_tool_call("harmony_pipeline_next", {
            "step_result": "not valid json",
            "state_path": ".harmony/state.json",
        })
        data = json.loads(result)
        assert "error" in data

    def test_pipeline_respond(self, tmp_path: Path, monkeypatch):
        from harmony.orchestrator.state import SessionState
        monkeypatch.chdir(tmp_path)
        SessionState(
            session_id="test",
            pipeline_phase="interview",
            pipeline_step="target_users",
            user_request="blog",
        ).save(".harmony/state.json")

        result = handle_tool_call("harmony_pipeline_respond", {
            "user_input": "a) Developers",
            "state_path": ".harmony/state.json",
        })
        data = json.loads(result)
        assert "interview" in data["step"]

    def test_checkpoint_save(self, tmp_path: Path, monkeypatch):
        from harmony.orchestrator.state import SessionState, TaskState
        monkeypatch.chdir(tmp_path)
        state = SessionState(session_id="test", tasks=[TaskState(id="1", title="Auth", status="in_progress")])
        state.save(".harmony/state.json")

        result = handle_tool_call("harmony_checkpoint_save", {
            "task_id": "1",
            "checkpoint_step": "3/5 files",
            "state_path": ".harmony/state.json",
        })
        assert "Checkpoint saved" in result

    def test_absolute_path_blocked(self):
        try:
            handle_tool_call("harmony_pipeline_start", {"state_path": "/etc/passwd"})
            assert False, "Should have raised"
        except ValueError as e:
            assert "Absolute path" in str(e)


class TestAgentRoleValidation:
    def test_path_traversal_in_agent_role(self):
        """Verify agent_role with path traversal is rejected."""
        resp = handle_message({
            "jsonrpc": "2.0", "method": "tools/call", "id": 99,
            "params": {
                "name": "harmony_memory_save",
                "arguments": {
                    "agent_role": "../../etc/passwd",
                    "category": "pattern",
                    "content": "test",
                },
            },
        })
        result_text = resp["result"]["content"][0]["text"]
        assert "Error" in result_text or "Invalid" in result_text

    def test_slash_in_agent_role(self):
        """Verify agent_role with slash is rejected."""
        resp = handle_message({
            "jsonrpc": "2.0", "method": "tools/call", "id": 100,
            "params": {
                "name": "harmony_memory_save",
                "arguments": {
                    "agent_role": "some/path",
                    "category": "pattern",
                    "content": "test",
                },
            },
        })
        result_text = resp["result"]["content"][0]["text"]
        assert "Error" in result_text or "Invalid" in result_text
