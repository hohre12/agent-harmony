"""Tests for harmony.orchestrator.templates — template generation."""

from __future__ import annotations

import json

from harmony.orchestrator.templates import generate_template


class TestTeamExecutor:
    def _base_config(self, **overrides) -> str:
        cfg = {
            "project_name": "TestProject",
            "main_architect": "architect-agent",
            "code_architect": "architect-agent",
            "db_agent": None,
            "review_agent": "review-agent",
            "e2e_agent": None,
            "agent_type_table": [
                {"characteristics": "Backend API implementation", "agent": "backend-agent"},
                {"characteristics": "Frontend UI components", "agent": "frontend-agent"},
            ],
            "git_mode": "monorepo",
        }
        cfg.update(overrides)
        return json.dumps(cfg)

    def test_generates_valid_markdown(self):
        result = generate_template("team-executor", self._base_config())
        assert result.startswith("---")
        assert "name: team-executor" in result
        assert "TestProject" in result

    def test_contains_workflow_sections(self):
        result = generate_template("team-executor", self._base_config())
        assert "### 1. Understand the Task" in result
        assert "### 2. Create Branch" in result
        assert "### 3. Team Creation" in result
        assert "### 4. Spawn Implementation" in result
        assert "### 6. Review" in result

    def test_self_review_included(self):
        result = generate_template("team-executor", self._base_config())
        assert "Self-Review" in result
        assert "self-review" in result.lower()

    def test_agent_names_substituted(self):
        result = generate_template("team-executor", self._base_config())
        assert "architect-agent" in result
        assert "review-agent" in result
        assert "backend-agent" in result

    def test_optional_db_agent_excluded(self):
        result = generate_template("team-executor", self._base_config(db_agent=None))
        assert "DB schema, indexes" not in result

    def test_optional_db_agent_included(self):
        result = generate_template("team-executor", self._base_config(db_agent="db-agent"))
        assert "db-agent" in result
        assert "DB schema" in result

    def test_optional_e2e_agent_excluded(self):
        result = generate_template("team-executor", self._base_config(e2e_agent=None))
        assert "E2E test design" not in result

    def test_optional_e2e_agent_included(self):
        result = generate_template("team-executor", self._base_config(e2e_agent="e2e-agent"))
        assert "e2e-agent" in result

    def test_multi_git_mode(self):
        result = generate_template("team-executor", self._base_config(
            git_mode="multi-git",
            sub_project_map=[
                {"agent": "backend-agent", "path": "./backend", "domain": "API"},
            ],
        ))
        assert "Sub-project Structure" in result
        assert "./backend" in result

    def test_monorepo_no_subproject(self):
        result = generate_template("team-executor", self._base_config())
        assert "Sub-project Structure" not in result

    def test_code_architect_same_as_main(self):
        result = generate_template("team-executor", self._base_config(
            code_architect="architect-agent",
        ))
        assert "also handles code structure" in result

    def test_code_architect_different(self):
        result = generate_template("team-executor", self._base_config(
            code_architect="code-architect-agent",
        ))
        assert "code-architect-agent" in result

    def test_unknown_template(self):
        result = generate_template("nonexistent", "{}")
        assert "Unknown template" in result
