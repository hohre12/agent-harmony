"""Tests for harmony.orchestrator.pipeline — full pipeline state machine."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pytest

from harmony.orchestrator.pipeline import start_pipeline, pipeline_next, pipeline_respond
from harmony.orchestrator.pipeline_setup import ensure_settings_local
from harmony.orchestrator.state import SessionState, TaskState


@pytest.fixture
def state_path(tmp_path: Path) -> str:
    return str(tmp_path / "state.json")


# --- Helpers for mocking verifier calls ---

def _mock_build_evidence_ok(*args, **kwargs):
    return {"has_changes": True, "files_changed": 5, "raw": "5 files changed"}


def _mock_build_evidence_empty(*args, **kwargs):
    return {"has_changes": False, "files_changed": 0, "raw": ""}


def _mock_quality_verified(*args, **kwargs):
    return {"verified": True, "mismatches": {}, "actual": {}, "warnings": [], "build_evidence": {}}


def _mock_quality_mismatch(*args, **kwargs):
    return {
        "verified": False,
        "mismatches": {"max_file_lines": {"reported": 200, "actual": 500}},
        "actual": {"max_file_lines": 500},
        "warnings": [],
        "build_evidence": {},
    }


def _mock_prd_valid(*args, **kwargs):
    return {"exists": True, "missing_sections": [], "valid": True, "file_lines": 100}


def _mock_prd_invalid(*args, **kwargs):
    return {"exists": True, "missing_sections": ["data model", "api"], "valid": False, "file_lines": 10}


def _mock_task_structure_valid(*args, **kwargs):
    return {"valid": True, "issues": [], "task_count": 2}


def _mock_task_structure_invalid(*args, **kwargs):
    return {"valid": False, "issues": ["Task 1: no subtasks defined"], "task_count": 2}


class TestStartPipeline:
    def test_fresh_start_with_request(self, state_path):
        result = json.loads(start_pipeline("build a todo app", state_path))
        assert result["step"] == "init"
        assert "todo app" in result["prompt"]
        assert result["expect"] == "step_result"

    def test_fresh_start_empty(self, state_path):
        result = json.loads(start_pipeline("", state_path))
        assert result["step"] == "init"
        assert result["expect"] == "user_input"

    def test_resume_existing_session(self, state_path):
        state = SessionState(
            session_id="test123",
            pipeline_phase="interview",
            pipeline_step="tech_stack",
            project_name="test",
        )
        state.save(state_path)

        result = json.loads(start_pipeline("", state_path))
        assert result["step"] == "resume"
        assert "interview" in result["prompt"]


class TestInterviewFlow:
    def test_context_check_fresh(self, state_path):
        start_pipeline("build a blog", state_path)
        result = json.loads(pipeline_next(
            json.dumps({"step": "context_check", "fresh": True}),
            state_path,
        ))
        assert "interview" in result["step"]
        assert result["expect"] == "user_input"

    def test_context_check_has_prd(self, state_path):
        start_pipeline("build a blog", state_path)
        result = json.loads(pipeline_next(
            json.dumps({"step": "context_check", "has_prd": True}),
            state_path,
        ))
        assert result["step"] == "prd_review"

    def test_interview_advances_questions(self, state_path):
        start_pipeline("build a blog", state_path)
        pipeline_next(json.dumps({"step": "context_check", "fresh": True}), state_path)

        result = json.loads(pipeline_respond("a) Developers", state_path))
        assert "interview" in result["step"]

        state = SessionState.load(state_path)
        assert "target_users" in state.interview_answers

    def test_short_letter_resolved_to_full_text(self, state_path):
        start_pipeline("build a blog", state_path)
        pipeline_next(json.dumps({"step": "context_check", "fresh": True}), state_path)

        # Answer with just "b"
        pipeline_respond("b", state_path)

        state = SessionState.load(state_path)
        # Should be resolved to full text, not just "b"
        assert state.interview_context["target_users"] == "General consumers (non-technical)"

    def test_free_text_preserved(self, state_path):
        start_pipeline("build a blog", state_path)
        pipeline_next(json.dumps({"step": "context_check", "fresh": True}), state_path)

        pipeline_respond("20-30대 여성 소비자", state_path)

        state = SessionState.load(state_path)
        # Free text should be kept as-is
        assert state.interview_context["target_users"] == "20-30대 여성 소비자"

    def test_interview_completes_to_prd_gen(self, state_path):
        start_pipeline("build a CLI tool", state_path)
        pipeline_next(json.dumps({"step": "context_check", "fresh": True}), state_path)

        state = SessionState.load(state_path)
        state.interview_context["project_type"] = "cli"
        for q in state.interview_question_sequence():
            state.interview_answers[q] = f"answer for {q}"
        state.save(state_path)

        result = json.loads(pipeline_respond("last answer", state_path))
        assert result["step"] == "generate_prd"
        assert result["expect"] == "step_result"


class TestPRDFlow:
    @patch("harmony.orchestrator.pipeline.verifier.verify_prd_sections", _mock_prd_valid)
    def test_prd_gen_success(self, state_path):
        state = SessionState(
            session_id="test",
            pipeline_phase="prd_gen",
            pipeline_step="generate",
            interview_context={"user_request": "todo app"},
        )
        state.save(state_path)

        result = json.loads(pipeline_next(
            json.dumps({"step": "generate_prd", "success": True, "prd_path": "docs/prd.md"}),
            state_path,
        ))
        assert result["step"] == "prd_review"

    @patch("harmony.orchestrator.pipeline.verifier.verify_prd_sections", _mock_prd_invalid)
    def test_prd_gen_missing_sections_retries(self, state_path):
        """PRD with missing sections triggers re-generation."""
        state = SessionState(
            session_id="test",
            pipeline_phase="prd_gen",
            pipeline_step="generate",
            interview_context={"user_request": "todo app"},
        )
        state.save(state_path)

        result = json.loads(pipeline_next(
            json.dumps({"step": "generate_prd", "success": True, "prd_path": "docs/prd.md"}),
            state_path,
        ))
        assert result["step"] == "generate_prd"
        assert "missing required sections" in result["prompt"]

    def test_prd_approve(self, state_path):
        state = SessionState(
            session_id="test",
            pipeline_phase="prd_review",
            pipeline_step="review",
        )
        state.save(state_path)

        result = json.loads(pipeline_respond("a", state_path))
        loaded = SessionState.load(state_path)
        assert loaded.pipeline_phase == "setup"


class TestSetupFlow:
    def test_setup_sequence(self, state_path):
        state = SessionState(session_id="test", pipeline_phase="setup")
        state.save(state_path)

        result = json.loads(pipeline_next(json.dumps({"step": "", "success": True}), state_path))
        assert "project_init" in result["step"]

        result = json.loads(pipeline_next(
            json.dumps({"step": "project_init", "success": True}),
            state_path,
        ))
        assert "generate_agents" in result["step"]

    def test_setup_skips_completed(self, state_path):
        state = SessionState(
            session_id="test",
            pipeline_phase="setup",
            setup_progress={"project_init": "done", "generate_agents": "done"},
        )
        state.save(state_path)

        result = json.loads(pipeline_next(json.dumps({"step": "", "success": True}), state_path))
        assert "build_refs" in result["step"]

    def test_generate_tasks_empty_retries(self, state_path):
        state = SessionState(
            session_id="test",
            pipeline_phase="setup",
            setup_progress={"project_init": "done", "generate_agents": "done", "build_refs": "done"},
        )
        state.save(state_path)

        # Trigger generate_tasks step
        pipeline_next(json.dumps({"step": "", "success": True}), state_path)

        # Return empty tasks -> should retry
        result = json.loads(pipeline_next(
            json.dumps({"step": "generate_tasks", "success": True, "tasks": []}),
            state_path,
        ))
        assert result["step"] == "generate_tasks"
        assert "no tasks" in result["prompt"].lower() or "Try again" in result["prompt"]

    def test_generate_tasks_invalid_format_retries(self, state_path):
        state = SessionState(
            session_id="test",
            pipeline_phase="setup",
            setup_progress={"project_init": "done", "generate_agents": "done", "build_refs": "done"},
        )
        state.save(state_path)

        pipeline_next(json.dumps({"step": "", "success": True}), state_path)

        # Return string instead of list -> should retry
        result = json.loads(pipeline_next(
            json.dumps({"step": "generate_tasks", "success": True, "tasks": "not a list"}),
            state_path,
        ))
        assert result["step"] == "generate_tasks"

    @patch("harmony.orchestrator.pipeline_setup.verifier.verify_task_structure", _mock_task_structure_valid)
    def test_setup_generates_tasks_then_executor(self, state_path):
        state = SessionState(
            session_id="test",
            pipeline_phase="setup",
            setup_progress={"project_init": "done", "generate_agents": "done", "build_refs": "done"},
        )
        state.save(state_path)

        # Next should be generate_tasks
        result = json.loads(pipeline_next(json.dumps({"step": "", "success": True}), state_path))
        assert "generate_tasks" in result["step"]

        # Complete generate_tasks with task data
        result = json.loads(pipeline_next(
            json.dumps({"step": "generate_tasks", "success": True, "tasks": [
                {"id": "1", "title": "Auth"},
                {"id": "2", "title": "Dashboard"},
            ]}),
            state_path,
        ))
        assert "setup_team_executor" in result["step"]

        loaded = SessionState.load(state_path)
        assert loaded.total_tasks == 2

    @patch("harmony.orchestrator.pipeline_setup.verifier.verify_task_structure", _mock_task_structure_valid)
    def test_setup_stores_subtasks(self, state_path):
        """Verify subtasks are persisted in state, not discarded."""
        state = SessionState(
            session_id="test",
            pipeline_phase="setup",
            setup_progress={"project_init": "done", "generate_agents": "done", "build_refs": "done"},
        )
        state.save(state_path)

        pipeline_next(json.dumps({"step": "", "success": True}), state_path)

        result = json.loads(pipeline_next(
            json.dumps({"step": "generate_tasks", "success": True, "tasks": [
                {"id": "1", "title": "Auth [LEAD: architect]", "subtasks": [
                    {"id": "1.1", "title": "DB schema (db-agent)", "description": "Create user table", "test": "Table exists", "agent": "db-agent"},
                    {"id": "1.2", "title": "API endpoints (backend-agent)", "description": "Auth REST API", "test": "Login returns token", "agent": "backend-agent"},
                ]},
            ]}),
            state_path,
        ))
        loaded = SessionState.load(state_path)
        assert loaded.total_tasks == 1
        assert len(loaded.tasks[0].subtasks) == 2
        assert loaded.tasks[0].subtasks[0].id == "1.1"
        assert loaded.tasks[0].subtasks[0].description == "Create user table"
        assert loaded.tasks[0].subtasks[1].assigned_agent == "backend-agent"

    @patch("harmony.orchestrator.pipeline_setup.verifier.verify_task_structure", _mock_task_structure_invalid)
    def test_setup_generates_tasks_fails_vertical_slice(self, state_path):
        """Tasks that fail vertical-slice validation are rejected."""
        state = SessionState(
            session_id="test",
            pipeline_phase="setup",
            setup_progress={"project_init": "done", "generate_agents": "done", "build_refs": "done"},
        )
        state.save(state_path)

        pipeline_next(json.dumps({"step": "", "success": True}), state_path)

        result = json.loads(pipeline_next(
            json.dumps({"step": "generate_tasks", "success": True, "tasks": [
                {"id": "1", "title": "Auth"},
                {"id": "2", "title": "Dashboard"},
            ]}),
            state_path,
        ))
        assert result["step"] == "generate_tasks"
        assert "validation FAILED" in result["prompt"]

    def test_setup_all_done_goes_to_build(self, state_path):
        state = SessionState(
            session_id="test",
            pipeline_phase="setup",
            setup_progress={s: "done" for s in [
                "project_init", "generate_agents", "build_refs",
                "generate_tasks", "setup_team_executor",
            ]},
            tasks=[TaskState(id="1", title="Auth", status="pending")],
            total_tasks=1,
        )
        state.save(state_path)

        result = json.loads(pipeline_next(json.dumps({"step": "", "success": True}), state_path))
        loaded = SessionState.load(state_path)
        assert loaded.pipeline_phase == "build"


class TestSetupFlowDesignDirection:
    def test_design_direction_skipped_for_cli(self, state_path):
        """Verify design_direction is skipped for CLI projects."""
        state = SessionState(
            session_id="test", pipeline_phase="setup",
            interview_context={"tech_stack": "Python + Click/Typer (CLI)", "design": ""},
        )
        state.save(state_path)
        result = json.loads(pipeline_next(
            json.dumps({"step": "", "success": True}), state_path,
        ))
        # Should skip to project_init, not design_direction
        assert result["step"] != "design_direction"


class TestBuildFlow:
    def test_resume_resets_in_progress_task(self, state_path):
        state = SessionState(
            session_id="test",
            pipeline_phase="build",
            pipeline_step="task_2",
            tasks=[
                TaskState(id="1", title="Auth", status="completed"),
                TaskState(id="2", title="Dashboard", status="in_progress"),
                TaskState(id="3", title="Settings", status="pending"),
            ],
            total_tasks=3,
        )
        state.save(state_path)

        # Simulate resume -- pipeline_next with empty triggers _next_build_task
        result = json.loads(pipeline_next(
            json.dumps({"step": "", "success": True}),
            state_path,
        ))
        assert result["step"] == "build_task"
        # Task 2 should be picked up (was reset from in_progress to pending)
        assert result["metadata"]["task_id"] == "2"

    @patch("harmony.orchestrator.pipeline_build.verifier.verify_build_evidence", _mock_build_evidence_ok)
    def test_build_task_success_triggers_quality_gate(self, state_path):
        state = SessionState(session_id="test", pipeline_phase="build")
        state.save(state_path)

        result = json.loads(pipeline_next(
            json.dumps({"step": "build_task", "task_id": "1", "task_title": "Auth", "success": True}),
            state_path,
        ))
        assert result["step"] == "quality_gate"

    @patch("harmony.orchestrator.pipeline_build.verifier.verify_build_evidence", _mock_build_evidence_empty)
    def test_build_task_no_evidence_retries(self, state_path):
        """Build that produces no git changes is rejected."""
        state = SessionState(session_id="test", pipeline_phase="build")
        state.save(state_path)

        result = json.loads(pipeline_next(
            json.dumps({"step": "build_task", "task_id": "1", "task_title": "Auth", "success": True}),
            state_path,
        ))
        assert result["step"] == "build_task"
        assert "evidence check FAILED" in result["prompt"]

    @patch("harmony.orchestrator.pipeline_build.verifier_frontend.cross_verify_quality_scores", _mock_quality_verified)
    def test_quality_gate_pass_triggers_audit(self, state_path):
        state = SessionState(
            session_id="test", pipeline_phase="build",
            tasks=[TaskState(id="1", title="Auth", status="in_progress")],
        )
        state.save(state_path)

        scores = {
            "build": True, "tests": True, "lint": True,
            "test_coverage": 80.0, "max_file_lines": 200,
            "max_function_lines": 40, "security_critical": 0,
            "a11y_critical": 0,
        }
        result = json.loads(pipeline_next(
            json.dumps({"step": "quality_gate", "task_id": "1", "task_title": "Auth", "scores": scores}),
            state_path,
        ))
        assert result["step"] == "audit"

    @patch("harmony.orchestrator.pipeline_build.verifier_frontend.cross_verify_quality_scores", _mock_quality_mismatch)
    def test_quality_gate_score_mismatch_triggers_fix(self, state_path):
        """Cross-verification mismatch triggers fix/escalate."""
        state = SessionState(
            session_id="test", pipeline_phase="build",
            tasks=[TaskState(id="1", title="Auth", status="in_progress")],
        )
        state.save(state_path)

        scores = {
            "build": True, "tests": True, "lint": True,
            "test_coverage": 80.0, "max_file_lines": 200,
            "max_function_lines": 40, "security_critical": 0,
            "a11y_critical": 0,
        }
        result = json.loads(pipeline_next(
            json.dumps({"step": "quality_gate", "task_id": "1", "task_title": "Auth", "scores": scores}),
            state_path,
        ))
        assert result["step"] == "fix"

    @patch("harmony.orchestrator.pipeline_build.verifier_frontend.cross_verify_quality_scores", _mock_quality_verified)
    def test_quality_gate_fail_triggers_fix(self, state_path):
        state = SessionState(
            session_id="test", pipeline_phase="build",
            tasks=[TaskState(id="1", title="Auth", status="in_progress")],
        )
        state.save(state_path)

        scores = {
            "build": True, "tests": True, "lint": False,
            "test_coverage": 30.0, "max_file_lines": 200,
            "max_function_lines": 40, "security_critical": 0,
        }
        result = json.loads(pipeline_next(
            json.dumps({"step": "quality_gate", "task_id": "1", "task_title": "Auth", "scores": scores}),
            state_path,
        ))
        assert result["step"] == "fix"

    @patch("harmony.orchestrator.pipeline_build.verifier_frontend.cross_verify_quality_scores", _mock_quality_verified)
    def test_quality_gate_fail_always_routes_to_fix(self, state_path):
        """Quality gate failure always routes to fix — no escalation, no round limit."""
        state = SessionState(
            session_id="test", pipeline_phase="build",
            tasks=[TaskState(id="1", title="Auth", status="in_progress", retry_count=10)],
        )
        state.save(state_path)

        scores = {"build": False, "tests": False, "lint": False,
                  "test_coverage": 0, "max_file_lines": 2000,
                  "max_function_lines": 200, "security_critical": 5}
        result = json.loads(pipeline_next(
            json.dumps({"step": "quality_gate", "task_id": "1", "task_title": "Auth", "scores": scores}),
            state_path,
        ))
        assert result["step"] == "fix"  # Always fix, never escalate

    def test_audit_fail_always_routes_to_fix(self, state_path):
        """Audit failure always routes to fix — no auto-pass, no round limit."""
        state = SessionState(
            session_id="test", pipeline_phase="build",
            tasks=[TaskState(id="1", title="Auth", status="in_progress", audit_round=10,
                             audit_nonce="test-nonce-123")],
        )
        state.save(state_path)

        result = json.loads(pipeline_next(
            json.dumps({"step": "audit", "task_id": "1", "auditor_id": "agent-test-12345",
                         "audit_nonce": "test-nonce-123",
                         "verdict": "NEEDS_FIX", "issues": []}),
            state_path,
        ))
        assert result["step"] == "fix"  # Always fix, never escalate

    def test_audit_pass_moves_to_next_task(self, state_path):
        state = SessionState(
            session_id="test",
            pipeline_phase="build",
            tasks=[
                TaskState(id="1", title="Auth", status="in_progress",
                          audit_nonce="test-nonce-123"),
                TaskState(id="2", title="Dashboard", status="pending"),
            ],
            total_tasks=2,
        )
        state.save(state_path)

        result = json.loads(pipeline_next(
            json.dumps({"step": "audit", "task_id": "1", "auditor_id": "agent-test-12345",
                         "audit_nonce": "test-nonce-123", "verdict": "PASS"}),
            state_path,
        ))
        assert result["step"] == "build_task"
        loaded = SessionState.load(state_path)
        assert loaded.tasks[0].status == "completed"

    def test_audit_pass_last_task_goes_to_verify(self, state_path):
        state = SessionState(
            session_id="test",
            pipeline_phase="build",
            tasks=[TaskState(id="1", title="Auth", status="in_progress",
                             audit_nonce="test-nonce-123")],
            total_tasks=1,
        )
        state.save(state_path)

        result = json.loads(pipeline_next(
            json.dumps({"step": "audit", "task_id": "1", "auditor_id": "agent-test-12345",
                         "audit_nonce": "test-nonce-123", "verdict": "PASS"}),
            state_path,
        ))
        loaded = SessionState.load(state_path)
        assert loaded.pipeline_phase == "verify"

    def test_audit_rejects_missing_auditor_id(self, state_path):
        """Audit without auditor_id is rejected and must be re-submitted."""
        state = SessionState(
            session_id="test", pipeline_phase="build",
            pipeline_step="audit_1",
            tasks=[TaskState(id="1", title="Auth", status="in_progress",
                             quality_scores={"build": True, "tests": True, "lint": True,
                                             "test_coverage": 80.0, "max_file_lines": 200,
                                             "max_function_lines": 40, "security_critical": 0,
                                             "a11y_critical": 0})],
        )
        state.save(state_path)
        result = json.loads(pipeline_next(
            json.dumps({"step": "audit", "task_id": "1", "task_title": "Auth",
                         "verdict": "PASS"}),  # no auditor_id
            state_path,
        ))
        # Should be rejected -- task NOT completed
        assert result["step"] == "audit"
        assert "REJECTED" in result["prompt"]
        loaded = SessionState.load(state_path)
        assert loaded.tasks[0].status != "completed"

    def test_fix_success_triggers_quality_gate(self, state_path):
        state = SessionState(session_id="test", pipeline_phase="build",
                             tasks=[TaskState(id="1", title="Auth", status="in_progress")])
        state.save(state_path)

        result = json.loads(pipeline_next(
            json.dumps({"step": "fix", "task_id": "1", "task_title": "Auth", "success": True}),
            state_path,
        ))
        assert result["step"] == "quality_gate"

    def test_prd_gen_failure_retries(self, state_path):
        state = SessionState(
            session_id="test",
            pipeline_phase="prd_gen",
            pipeline_step="generate",
            interview_context={"user_request": "todo app"},
        )
        state.save(state_path)

        result = json.loads(pipeline_next(
            json.dumps({"step": "generate_prd", "success": False}),
            state_path,
        ))
        assert "retry" in result["step"]

    def test_checkpoint_resume_uses_checkpoint_data(self, state_path):
        """Verify that interrupted tasks with checkpoint data resume from checkpoint."""
        state = SessionState(
            session_id="test", pipeline_phase="build",
            tasks=[TaskState(id="1", title="Auth", status="in_progress",
                             checkpoint_step="3/5 files written",
                             checkpoint="files: a.py, b.py, c.py")],
        )
        state.save(state_path)
        # Trigger build phase by sending a generic step
        result = json.loads(pipeline_next(
            json.dumps({"step": "continue"}), state_path,
        ))
        assert result["step"] == "build_task"
        assert "RESUME FROM CHECKPOINT" in result["prompt"]
        assert "3/5 files written" in result["prompt"]

    def test_resume_continues_from_saved_state(self, state_path):
        state = SessionState(
            session_id="test",
            pipeline_phase="build",
            pipeline_step="task_3",
            tasks=[
                TaskState(id="1", title="Auth", status="completed"),
                TaskState(id="2", title="Dashboard", status="completed"),
                TaskState(id="3", title="Settings", status="pending"),
            ],
            total_tasks=3,
        )
        state.save(state_path)

        # Start pipeline detects existing session -> resume prompt
        result = json.loads(start_pipeline("", state_path))
        assert result["step"] == "resume"
        assert "build" in result["prompt"]


class TestVerifyFlow:
    def test_verify_no_gaps_goes_to_harden(self, state_path):
        state = SessionState(session_id="test", pipeline_phase="verify")
        state.save(state_path)

        result = json.loads(pipeline_next(
            json.dumps({"step": "verify_prd", "auditor_id": "agent-xyz", "gaps": []}),
            state_path,
        ))
        assert result["step"] == "harden_security"
        loaded = SessionState.load(state_path)
        assert loaded.pipeline_phase == "harden"

    def test_verify_with_gaps_triggers_fix(self, state_path):
        state = SessionState(session_id="test", pipeline_phase="verify")
        state.save(state_path)

        result = json.loads(pipeline_next(
            json.dumps({"step": "verify_prd", "auditor_id": "agent-xyz",
                         "gaps": [{"feature": "Auth", "status": "partial"}]}),
            state_path,
        ))
        assert result["step"] == "verify_fix"

    def test_verify_high_rounds_still_routes_to_fix(self, state_path):
        """Verify always routes to fix regardless of round count — no escalation."""
        state = SessionState(session_id="test", pipeline_phase="verify", verify_round=20)
        state.save(state_path)

        result = json.loads(pipeline_next(
            json.dumps({"step": "verify_prd", "auditor_id": "agent-xyz",
                         "gaps": [{"feature": "Auth"}]}),
            state_path,
        ))
        assert result["step"] == "verify_fix"

    def test_verify_without_auditor_id_rejected(self, state_path):
        """Verify PRD without auditor_id is rejected."""
        state = SessionState(session_id="test", pipeline_phase="verify")
        state.save(state_path)

        result = json.loads(pipeline_next(
            json.dumps({"step": "verify_prd", "gaps": []}),
            state_path,
        ))
        assert result["step"] == "verify_prd"
        assert "REJECTED" in result["prompt"]

    def test_verify_escalation_accept_continues(self, state_path):
        """Verify that accepting gaps during escalation moves to harden."""
        state = SessionState(
            session_id="test", pipeline_phase="verify",
            pipeline_step="verify_escalate",
        )
        state.save(state_path)
        result = json.loads(pipeline_respond("b", state_path))
        assert result["step"] == "harden_security"

    def test_verify_escalation_abort(self, state_path):
        """Verify that aborting during escalation ends pipeline."""
        state = SessionState(
            session_id="test", pipeline_phase="verify",
            pipeline_step="verify_escalate",
        )
        state.save(state_path)
        result = json.loads(pipeline_respond("d", state_path))
        assert result["step"] == "done"


class TestHardenFlow:
    def test_harden_no_criticals_goes_to_delivery(self, state_path):
        state = SessionState(session_id="test", pipeline_phase="harden")
        state.save(state_path)

        result = json.loads(pipeline_next(
            json.dumps({"step": "harden_security", "auditor_id": "agent-xyz", "critical_count": 0}),
            state_path,
        ))
        assert result["step"] == "final_check"
        loaded = SessionState.load(state_path)
        assert loaded.pipeline_phase == "delivery"

    def test_harden_with_criticals_triggers_fix(self, state_path):
        state = SessionState(session_id="test", pipeline_phase="harden")
        state.save(state_path)

        result = json.loads(pipeline_next(
            json.dumps({"step": "harden_security", "auditor_id": "agent-xyz",
                         "critical_count": 2, "criticals": [{"file": "a.py"}]}),
            state_path,
        ))
        assert result["step"] == "harden_fix"

    def test_harden_without_auditor_id_rejected(self, state_path):
        """Harden security without auditor_id is rejected."""
        state = SessionState(session_id="test", pipeline_phase="harden")
        state.save(state_path)

        result = json.loads(pipeline_next(
            json.dumps({"step": "harden_security", "critical_count": 0}),
            state_path,
        ))
        assert result["step"] == "harden_security"
        assert "REJECTED" in result["prompt"]

    def test_harden_escalation_accept_continues(self, state_path):
        """Verify that accepting risks during escalation moves to delivery."""
        state = SessionState(
            session_id="test", pipeline_phase="harden",
            pipeline_step="harden_escalate",
        )
        state.save(state_path)
        result = json.loads(pipeline_respond("b", state_path))
        assert result["step"] == "final_check"


class TestDeliveryFlow:
    def test_final_check_success(self, state_path):
        state = SessionState(session_id="test", pipeline_phase="delivery", pipeline_step="final_check")
        state.save(state_path)

        result = json.loads(pipeline_next(
            json.dumps({"step": "final_check", "success": True}),
            state_path,
        ))
        assert result["step"] == "summary"
        loaded = SessionState.load(state_path)
        assert loaded.pipeline_phase == "done"


class TestQuestionSequence:
    def test_cli_skips_design_auth_deployment(self):
        state = SessionState(interview_context={"project_type": "cli"})
        seq = state.interview_question_sequence()
        assert "design" not in seq
        assert "auth" not in seq
        assert "deployment" not in seq

    def test_web_includes_all(self):
        state = SessionState(interview_context={"project_type": "web"})
        seq = state.interview_question_sequence()
        assert "design" in seq
        assert "auth" in seq
        assert "deployment" in seq


class TestResumeFlow:
    def test_resume_from_verify(self, state_path):
        state = SessionState(session_id="test", pipeline_phase="verify")
        state.save(state_path)
        result = json.loads(start_pipeline("test", state_path))
        assert result["step"] == "resume"

    def test_resume_from_harden(self, state_path):
        state = SessionState(session_id="test", pipeline_phase="harden")
        state.save(state_path)
        result = json.loads(start_pipeline("test", state_path))
        assert result["step"] == "resume"

    def test_resume_from_delivery(self, state_path):
        state = SessionState(session_id="test", pipeline_phase="delivery")
        state.save(state_path)
        result = json.loads(start_pipeline("test", state_path))
        assert result["step"] == "resume"

    def test_resume_option_a_resumes(self, state_path):
        """Verify choosing 'a' during resume actually resumes from current phase."""
        state = SessionState(
            session_id="test", pipeline_phase="build",
            pipeline_step="awaiting_resume",
            tasks=[TaskState(id="1", title="Auth", status="pending")],
        )
        state.save(state_path)
        result = json.loads(pipeline_respond("a", state_path))
        assert result["step"] == "build_task"  # Should resume to build

    def test_resume_option_b_starts_over(self, state_path):
        """Verify choosing 'b' during resume resets session."""
        state = SessionState(
            session_id="test", pipeline_phase="build",
            pipeline_step="awaiting_resume",
            interview_answers={"q1": "a1"},
        )
        state.save(state_path)
        result = json.loads(pipeline_respond("b", state_path))
        assert result["step"] == "init"
        # Verify state was reset
        loaded = SessionState.load(state_path)
        assert loaded.interview_answers == {}


class TestDesignDirection:
    def test_design_direction_runs_for_frontend(self, state_path):
        """Verify design_direction step is returned for React projects."""
        state = SessionState(
            session_id="test", pipeline_phase="setup",
            interview_context={"tech_stack": "Next.js + TypeScript", "design": "Clean & minimal"},
        )
        state.save(state_path)
        result = json.loads(pipeline_next(
            json.dumps({"step": "", "success": True}), state_path,
        ))
        assert result["step"] == "design_direction"
        assert "frontend-design" in result["prompt"] or "design" in result["prompt"].lower()


class TestDesignAudit:
    def test_frontend_task_triggers_design_audit(self, state_path):
        """Frontend tasks should get design quality audit after production audit passes."""
        state = SessionState(
            session_id="test", pipeline_phase="build",
            pipeline_step="audit_1",
            tasks=[TaskState(id="1", title="Landing Page UI", status="in_progress",
                             audit_nonce="test-nonce-123",
                             quality_scores={"build": True, "tests": True, "lint": True,
                                             "test_coverage": 80.0, "max_file_lines": 200,
                                             "max_function_lines": 40, "security_critical": 0,
                                             "a11y_critical": 0, "design_token_violations": 3})],
        )
        state.save(state_path)
        result = json.loads(pipeline_next(
            json.dumps({"step": "audit", "task_id": "1", "task_title": "Landing Page UI",
                         "auditor_id": "agent-abc12345", "audit_nonce": "test-nonce-123",
                         "verdict": "PASS"}),
            state_path,
        ))
        assert result["step"] == "design_audit"
        assert "Anti-AI" in result["prompt"] or "design" in result["prompt"].lower()

    def test_non_frontend_task_skips_design_audit(self, state_path):
        """Non-frontend tasks should skip design audit and complete directly."""
        state = SessionState(
            session_id="test", pipeline_phase="build",
            pipeline_step="audit_1",
            tasks=[TaskState(id="1", title="Auth API", status="in_progress",
                             audit_nonce="test-nonce-123"),
                   TaskState(id="2", title="Database Schema", status="pending")],
            total_tasks=2,
        )
        state.save(state_path)
        result = json.loads(pipeline_next(
            json.dumps({"step": "audit", "task_id": "1", "task_title": "Auth API",
                         "auditor_id": "agent-abc12345", "audit_nonce": "test-nonce-123",
                         "verdict": "PASS"}),
            state_path,
        ))
        # Should go directly to next build task, not design_audit
        assert result["step"] == "build_task"
        loaded = SessionState.load(state_path)
        assert loaded.tasks[0].status == "completed"

    def test_design_audit_pass_completes_task(self, state_path):
        """Design audit PASS should complete the task."""
        state = SessionState(
            session_id="test", pipeline_phase="build",
            pipeline_step="audit_1",
            tasks=[TaskState(id="1", title="Dashboard UI", status="in_progress",
                             audit_round=-1)],  # -1 = design audit in progress
        )
        state.save(state_path)
        result = json.loads(pipeline_next(
            json.dumps({"step": "design_audit", "task_id": "1", "task_title": "Dashboard UI",
                         "auditor_id": "agent-test-12345", "verdict": "PASS"}),
            state_path,
        ))
        loaded = SessionState.load(state_path)
        assert loaded.tasks[0].status == "completed"

    def test_design_audit_fail_routes_to_fix(self, state_path):
        """Design audit NEEDS_FIX should route to fix step."""
        state = SessionState(
            session_id="test", pipeline_phase="build",
            pipeline_step="audit_1",
            tasks=[TaskState(id="1", title="Dashboard UI", status="in_progress",
                             audit_round=-1)],
        )
        state.save(state_path)
        result = json.loads(pipeline_next(
            json.dumps({"step": "design_audit", "task_id": "1", "task_title": "Dashboard UI",
                         "auditor_id": "agent-test-12345",
                         "verdict": "NEEDS_FIX",
                         "issues": [{"severity": "MUST-FIX", "file": "Dashboard.tsx",
                                     "what": "hardcoded colors"}]}),
            state_path,
        ))
        assert result["step"] == "fix"
        loaded = SessionState.load(state_path)
        assert loaded.tasks[0].audit_round == 0  # Reset for normal flow


class TestAuditNonceField:
    @patch("harmony.orchestrator.pipeline_build.verifier_frontend.cross_verify_quality_scores", _mock_quality_verified)
    def test_nonce_stored_in_task_field(self, state_path):
        """Verify audit_nonce is stored in TaskState.audit_nonce, not checkpoint."""
        state = SessionState(
            session_id="test", pipeline_phase="build",
            pipeline_step="gate_1",
            quality_thresholds={
                "build": True, "tests": True, "lint": True,
                "test_coverage": 70.0, "max_file_lines": 400,
                "max_function_lines": 60, "security_critical": 0,
                "a11y_critical": 0, "design_token_violations": 10,
            },
            tasks=[TaskState(id="1", title="Backend API", status="in_progress")],
        )
        state.save(state_path)

        scores = {
            "build": True, "tests": True, "lint": True,
            "test_coverage": 80.0, "max_file_lines": 200,
            "max_function_lines": 40, "security_critical": 0,
            "a11y_critical": 0, "design_token_violations": 3,
        }
        result = json.loads(pipeline_next(
            json.dumps({"step": "quality_gate", "task_id": "1", "task_title": "Backend API", "scores": scores}),
            state_path,
        ))
        # Should move to audit step
        if result["step"] == "audit":
            # Load state and verify nonce is stored in audit_nonce field
            loaded = SessionState.load(state_path)
            task = loaded._task_by_id("1")
            assert task.audit_nonce  # Should be non-empty
            assert task.checkpoint == ""  # checkpoint should NOT be overwritten


class TestUnknownPhaseRecovery:
    def test_unknown_phase_recovers(self, state_path):
        """Unknown pipeline phase triggers recovery."""
        state = SessionState(
            session_id="test", pipeline_phase="unknown_xyz",
        )
        state.save(state_path)
        result = json.loads(pipeline_next(
            json.dumps({"step": "anything"}), state_path,
        ))
        # Should recover — either return done or resume
        assert result["step"] in ("done", "resume", "init")


class TestEnsureSettingsLocal:
    def test_creates_file_from_scratch(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        ensure_settings_local()
        path = tmp_path / ".claude" / "settings.local.json"
        assert path.exists()
        data = json.loads(path.read_text())
        assert data["permissions"]["defaultMode"] == "bypassPermissions"
        assert "Bash(*)" in data["permissions"]["allow"]
        assert "mcp__harmony__*" in data["permissions"]["allow"]
        assert data["teammateMode"] == "auto"
        assert data["env"]["CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS"] == "1"

    def test_merges_with_existing(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        claude_dir = tmp_path / ".claude"
        claude_dir.mkdir()
        existing = {"permissions": {"allow": ["CustomTool(*)"], "defaultMode": "default"}, "myKey": 123}
        (claude_dir / "settings.local.json").write_text(json.dumps(existing))

        ensure_settings_local()
        data = json.loads((claude_dir / "settings.local.json").read_text())
        # User's custom tool preserved
        assert "CustomTool(*)" in data["permissions"]["allow"]
        # Required tools added
        assert "Bash(*)" in data["permissions"]["allow"]
        assert "mcp__harmony__*" in data["permissions"]["allow"]
        # Mode overridden
        assert data["permissions"]["defaultMode"] == "bypassPermissions"
        # User's extra key preserved
        assert data["myKey"] == 123
