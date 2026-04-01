"""Tests for harmony.orchestrator.pipeline — full pipeline state machine."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from harmony.orchestrator.pipeline import start_pipeline, pipeline_next, pipeline_respond
from harmony.orchestrator.state import SessionState, TaskState


@pytest.fixture
def state_path(tmp_path: Path) -> str:
    return str(tmp_path / "state.json")


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

        # Return empty tasks → should retry
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

        # Return string instead of list → should retry
        result = json.loads(pipeline_next(
            json.dumps({"step": "generate_tasks", "success": True, "tasks": "not a list"}),
            state_path,
        ))
        assert result["step"] == "generate_tasks"

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

        # Simulate resume — pipeline_next with empty triggers _next_build_task
        result = json.loads(pipeline_next(
            json.dumps({"step": "", "success": True}),
            state_path,
        ))
        assert result["step"] == "build_task"
        # Task 2 should be picked up (was reset from in_progress to pending)
        assert result["metadata"]["task_id"] == "2"

    def test_build_task_success_triggers_quality_gate(self, state_path):
        state = SessionState(session_id="test", pipeline_phase="build")
        state.save(state_path)

        result = json.loads(pipeline_next(
            json.dumps({"step": "build_task", "task_id": "1", "task_title": "Auth", "success": True}),
            state_path,
        ))
        assert result["step"] == "quality_gate"

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
        }
        result = json.loads(pipeline_next(
            json.dumps({"step": "quality_gate", "task_id": "1", "task_title": "Auth", "scores": scores}),
            state_path,
        ))
        assert result["step"] == "audit"

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

    def test_quality_gate_fail_max_retries_escalates(self, state_path):
        state = SessionState(
            session_id="test", pipeline_phase="build",
            tasks=[TaskState(id="1", title="Auth", status="in_progress", retry_count=2, max_retries=3)],
        )
        state.save(state_path)

        scores = {"build": False, "tests": False, "lint": False,
                  "test_coverage": 0, "max_file_lines": 2000,
                  "max_function_lines": 200, "security_critical": 5}
        result = json.loads(pipeline_next(
            json.dumps({"step": "quality_gate", "task_id": "1", "task_title": "Auth", "scores": scores}),
            state_path,
        ))
        assert result["step"] == "escalate"

    def test_audit_fail_3_rounds_escalates_no_autopass(self, state_path):
        state = SessionState(
            session_id="test", pipeline_phase="build",
            tasks=[TaskState(id="1", title="Auth", status="in_progress", audit_round=2)],
        )
        state.save(state_path)

        result = json.loads(pipeline_next(
            json.dumps({"step": "audit", "task_id": "1", "verdict": "NEEDS_FIX", "issues": []}),
            state_path,
        ))
        assert result["step"] == "escalate"  # NOT auto-pass

    def test_audit_pass_moves_to_next_task(self, state_path):
        state = SessionState(
            session_id="test",
            pipeline_phase="build",
            tasks=[
                TaskState(id="1", title="Auth", status="in_progress"),
                TaskState(id="2", title="Dashboard", status="pending"),
            ],
            total_tasks=2,
        )
        state.save(state_path)

        result = json.loads(pipeline_next(
            json.dumps({"step": "audit", "task_id": "1", "verdict": "PASS"}),
            state_path,
        ))
        assert result["step"] == "build_task"
        loaded = SessionState.load(state_path)
        assert loaded.tasks[0].status == "completed"

    def test_audit_pass_last_task_goes_to_verify(self, state_path):
        state = SessionState(
            session_id="test",
            pipeline_phase="build",
            tasks=[TaskState(id="1", title="Auth", status="in_progress")],
            total_tasks=1,
        )
        state.save(state_path)

        result = json.loads(pipeline_next(
            json.dumps({"step": "audit", "task_id": "1", "verdict": "PASS"}),
            state_path,
        ))
        loaded = SessionState.load(state_path)
        assert loaded.pipeline_phase == "verify"

    def test_escalation_skip_goes_to_verify(self, state_path):
        state = SessionState(session_id="test", pipeline_phase="build", pipeline_step="escalate_1")
        state.save(state_path)

        result = json.loads(pipeline_respond("b", state_path))
        loaded = SessionState.load(state_path)
        assert loaded.pipeline_phase == "verify"

    def test_escalation_abort(self, state_path):
        state = SessionState(session_id="test", pipeline_phase="build", pipeline_step="escalate_1")
        state.save(state_path)

        result = json.loads(pipeline_respond("d", state_path))
        loaded = SessionState.load(state_path)
        assert loaded.pipeline_phase == "done"

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

        # Start pipeline detects existing session → resume prompt
        result = json.loads(start_pipeline("", state_path))
        assert result["step"] == "resume"
        assert "build" in result["prompt"]


class TestVerifyFlow:
    def test_verify_no_gaps_goes_to_harden(self, state_path):
        state = SessionState(session_id="test", pipeline_phase="verify")
        state.save(state_path)

        result = json.loads(pipeline_next(
            json.dumps({"step": "verify_prd", "gaps": []}),
            state_path,
        ))
        assert result["step"] == "harden_security"
        loaded = SessionState.load(state_path)
        assert loaded.pipeline_phase == "harden"

    def test_verify_with_gaps_triggers_fix(self, state_path):
        state = SessionState(session_id="test", pipeline_phase="verify")
        state.save(state_path)

        result = json.loads(pipeline_next(
            json.dumps({"step": "verify_prd", "gaps": [{"feature": "Auth", "status": "partial"}]}),
            state_path,
        ))
        assert result["step"] == "verify_fix"

    def test_verify_max_rounds_skips_to_harden(self, state_path):
        state = SessionState(session_id="test", pipeline_phase="verify", verify_round=2)
        state.save(state_path)

        result = json.loads(pipeline_next(
            json.dumps({"step": "verify_prd", "gaps": [{"feature": "Auth"}]}),
            state_path,
        ))
        assert result["step"] == "harden_security"


class TestHardenFlow:
    def test_harden_no_criticals_goes_to_delivery(self, state_path):
        state = SessionState(session_id="test", pipeline_phase="harden")
        state.save(state_path)

        result = json.loads(pipeline_next(
            json.dumps({"step": "harden_security", "critical_count": 0}),
            state_path,
        ))
        assert result["step"] == "final_check"
        loaded = SessionState.load(state_path)
        assert loaded.pipeline_phase == "delivery"

    def test_harden_with_criticals_triggers_fix(self, state_path):
        state = SessionState(session_id="test", pipeline_phase="harden")
        state.save(state_path)

        result = json.loads(pipeline_next(
            json.dumps({"step": "harden_security", "critical_count": 2, "criticals": [{"file": "a.py"}]}),
            state_path,
        ))
        assert result["step"] == "harden_fix"


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
