"""Tests for harmony.memory.store — agent memory system."""

from __future__ import annotations

from pathlib import Path

import pytest

from harmony.memory.store import AgentMemory, MemoryEntry, global_context


class TestAddAndDedup:
    def test_add_entry(self):
        mem = AgentMemory(agent_role="test-agent")
        e = mem.add("pattern", "Always use ORM")
        assert e is not None
        assert len(mem.entries) == 1

    def test_dedup_rejects_same(self):
        mem = AgentMemory(agent_role="test-agent")
        mem.add("pattern", "Always use ORM")
        e2 = mem.add("pattern", "Always use ORM")
        assert e2 is None
        assert len(mem.entries) == 1

    def test_different_content_accepted(self):
        mem = AgentMemory(agent_role="test-agent")
        mem.add("pattern", "Use ORM")
        mem.add("mistake", "Forgot indexes")
        assert len(mem.entries) == 2


class TestQuery:
    def test_by_category(self):
        mem = AgentMemory(agent_role="test")
        mem.add("pattern", "A")
        mem.add("mistake", "B")
        mem.add("pattern", "C")
        results = mem.query(category="pattern")
        assert len(results) == 2

    def test_by_project(self):
        mem = AgentMemory(agent_role="test")
        mem.add("insight", "Global thing")
        mem.add("insight", "Project specific", project="myapp")
        results = mem.query(project="myapp")
        assert len(results) == 2  # both match (empty project = global)

    def test_limit(self):
        mem = AgentMemory(agent_role="test")
        for i in range(10):
            mem.add("insight", f"Thing {i}")
        results = mem.query(limit=3)
        assert len(results) == 3


class TestContextPrompt:
    def test_empty_memory(self):
        mem = AgentMemory(agent_role="test")
        assert mem.context_prompt() == ""

    def test_has_content(self):
        mem = AgentMemory(agent_role="backend-agent")
        mem.add("pattern", "Always use ORM")
        mem.add("mistake", "Forgot to add indexes")
        ctx = mem.context_prompt()
        assert "Previous Learnings" in ctx
        assert "Always use ORM" in ctx
        assert "backend-agent" in ctx


class TestConsolidate:
    def test_no_op_under_limit(self):
        mem = AgentMemory(agent_role="test")
        mem.add("pattern", "Learning 1")
        assert mem.consolidate(max_entries=100) == 0

    def test_removes_excess(self):
        mem = AgentMemory(agent_role="test")
        for i in range(15):
            mem.add("pattern", f"Learning {i}")
        removed = mem.consolidate(max_entries=10)
        assert removed == 5
        assert len(mem.entries) == 10


class TestForget:
    def test_forget_entry(self):
        mem = AgentMemory(agent_role="test")
        e = mem.add("pattern", "Remove me")
        assert mem.forget(e.id)
        assert len(mem.entries) == 0

    def test_forget_nonexistent(self):
        mem = AgentMemory(agent_role="test")
        assert not mem.forget("nonexistent-id")


class TestPersistence:
    def test_save_load(self, tmp_path: Path):
        mem = AgentMemory(agent_role="backend-agent")
        mem.add("pattern", "Use ORM", project="test")
        mem.add("mistake", "Forgot indexes")
        mem.save(str(tmp_path))

        loaded = AgentMemory.load("backend-agent", str(tmp_path))
        assert len(loaded.entries) == 2
        assert loaded.entries[0].content == "Use ORM"

    def test_load_missing(self, tmp_path: Path):
        loaded = AgentMemory.load("ghost", str(tmp_path))
        assert len(loaded.entries) == 0


class TestStats:
    def test_stats(self):
        mem = AgentMemory(agent_role="test")
        mem.add("pattern", "A")
        mem.add("pattern", "B")
        mem.add("mistake", "C")
        stats = mem.stats()
        assert stats["total_entries"] == 3
        assert stats["categories"]["pattern"] == 2
        assert stats["categories"]["mistake"] == 1
