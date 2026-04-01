"""Tests for harmony.orchestrator.state — session state management."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from harmony.orchestrator.state import SessionState, TaskState


class TestTaskState:
    def test_initial_state(self):
        t = TaskState(id="1", title="Test task")
        assert t.status == "pending"
        assert t.retry_count == 0
        assert t.checkpoint == ""
        assert t.checkpoint_step == ""

    def test_is_terminal_completed(self):
        t = TaskState(id="1", title="T", status="completed")
        assert t.is_terminal()

    def test_is_terminal_exhausted(self):
        t = TaskState(id="1", title="T", status="failed", retry_count=3, max_retries=3)
        assert t.is_terminal()

    def test_not_terminal_failed_with_retries(self):
        t = TaskState(id="1", title="T", status="failed", retry_count=1, max_retries=3)
        assert not t.is_terminal()

    def test_checkpoint_fields(self):
        t = TaskState(id="1", title="T", checkpoint='{"step": 3}', checkpoint_step="3/5 files written")
        assert t.checkpoint_step == "3/5 files written"
        assert json.loads(t.checkpoint)["step"] == 3

    def test_gate_passed_all_met(self):
        t = TaskState(id="1", title="T", quality_scores={
            "build": True, "tests": True, "lint": True,
            "test_coverage": 80.0, "max_file_lines": 200,
            "max_function_lines": 40, "security_critical": 0,
        })
        thresholds = {
            "build": True, "tests": True, "lint": True,
            "test_coverage": 60.0, "max_file_lines": 500,
            "max_function_lines": 80, "security_critical": 0,
        }
        assert t.gate_passed(thresholds)

    def test_gate_failed_coverage_low(self):
        t = TaskState(id="1", title="T", quality_scores={
            "build": True, "tests": True, "lint": True,
            "test_coverage": 30.0, "max_file_lines": 200,
            "max_function_lines": 40, "security_critical": 0,
        })
        thresholds = {"test_coverage": 60.0}
        assert not t.gate_passed(thresholds)

    def test_gate_failed_file_too_large(self):
        t = TaskState(id="1", title="T", quality_scores={
            "max_file_lines": 800,
        })
        thresholds = {"max_file_lines": 500}
        assert not t.gate_passed(thresholds)

    def test_gate_failed_security_issues(self):
        t = TaskState(id="1", title="T", quality_scores={
            "security_critical": 3,
        })
        thresholds = {"security_critical": 0}
        assert not t.gate_passed(thresholds)

    def test_gate_empty_scores(self):
        t = TaskState(id="1", title="T")
        assert not t.gate_passed({"build": True})

    def test_gate_missing_metric(self):
        t = TaskState(id="1", title="T", quality_scores={"build": True})
        thresholds = {"build": True, "tests": True}
        assert not t.gate_passed(thresholds)


class TestSessionState:
    def test_create_new(self):
        tasks = [{"id": "1", "title": "Auth"}, {"id": "2", "title": "Dashboard"}]
        state = SessionState.create_new("myapp", tasks)
        assert state.project_name == "myapp"
        assert state.total_tasks == 2
        assert state.pipeline_phase == "init"
        assert state.git_branch.startswith("harmony/dev-")

    def test_save_load(self, tmp_path: Path):
        tasks = [{"id": "1", "title": "Auth"}]
        state = SessionState.create_new("test", tasks)
        state.pipeline_phase = "build"
        path = str(tmp_path / "state.json")
        state.save(path)

        loaded = SessionState.load(path)
        assert loaded is not None
        assert loaded.pipeline_phase == "build"
        assert loaded.total_tasks == 1

    def test_load_missing(self, tmp_path: Path):
        loaded = SessionState.load(str(tmp_path / "nope.json"))
        assert loaded is None

    def test_load_corrupted(self, tmp_path: Path):
        p = tmp_path / "bad.json"
        p.write_text("not valid json {{{")
        loaded = SessionState.load(str(p))
        assert loaded is None

    def test_next_pending_task(self):
        state = SessionState.create_new("test", [
            {"id": "1", "title": "A"},
            {"id": "2", "title": "B"},
        ])
        t = state.next_pending_task()
        assert t.id == "1"

    def test_mark_in_progress(self):
        state = SessionState.create_new("test", [{"id": "1", "title": "A"}])
        state.mark_in_progress("1")
        assert state.tasks[0].status == "in_progress"

    def test_mark_completed(self):
        state = SessionState.create_new("test", [{"id": "1", "title": "A"}])
        state.mark_completed("1")
        assert state.tasks[0].status == "completed"
        assert state.tasks[0].completed_at != ""

    def test_mark_failed(self):
        state = SessionState.create_new("test", [{"id": "1", "title": "A"}])
        state.mark_failed("1", "Timeout")
        assert state.tasks[0].status == "failed"
        assert state.tasks[0].retry_count == 1
        assert state.tasks[0].last_error == "Timeout"

    def test_can_retry(self):
        state = SessionState.create_new("test", [{"id": "1", "title": "A"}])
        state.mark_failed("1", "err")
        assert state.can_retry("1")
        state.mark_failed("1", "err")
        state.mark_failed("1", "err")
        assert not state.can_retry("1")

    def test_all_tasks_terminal(self):
        state = SessionState.create_new("test", [
            {"id": "1", "title": "A"},
            {"id": "2", "title": "B"},
        ])
        state.mark_completed("1")
        assert not state.all_tasks_terminal()
        state.mark_completed("2")
        assert state.all_tasks_terminal()

    def test_add_fix_tasks(self):
        state = SessionState.create_new("test", [{"id": "1", "title": "A"}])
        state.add_fix_tasks([{"title": "Fix X", "agent": "backend"}])
        assert state.total_tasks == 2
        assert state.tasks[1].title == "Fix X"

    def test_progress_summary(self):
        state = SessionState.create_new("test", [{"id": "1", "title": "A"}])
        state.pipeline_phase = "build"
        summary = state.progress_summary()
        assert "build" in summary
        assert "harmony/dev-" in summary

    def test_setup_progress(self):
        state = SessionState.create_new("test", [])
        state.setup_progress["project_init"] = "done"
        state.setup_progress["generate_agents"] = "done"
        assert len(state.setup_progress) == 2

    def test_persistence(self, tmp_path: Path):
        state = SessionState.create_new("test", [])
        state.pipeline_phase = "build"
        state.setup_progress["setup_tasks"] = "done"
        state.verify_round = 1
        path = str(tmp_path / "state.json")
        state.save(path)

        loaded = SessionState.load(path)
        assert loaded.pipeline_phase == "build"
        assert loaded.setup_progress["setup_tasks"] == "done"
        assert loaded.verify_round == 1


class TestInterviewSequence:
    def test_cli_skips_questions(self):
        state = SessionState(interview_context={"project_type": "cli"})
        seq = state.interview_question_sequence()
        assert "design" not in seq
        assert "auth" not in seq

    def test_web_includes_all(self):
        state = SessionState(interview_context={"project_type": "web"})
        seq = state.interview_question_sequence()
        assert "design" in seq
        assert "auth" in seq
        assert "deployment" in seq

    def test_base_questions_always_present(self):
        state = SessionState(interview_context={})
        seq = state.interview_question_sequence()
        assert "target_users" in seq
        assert "core_problem" in seq
        assert "features" in seq
        assert "tech_stack" in seq
        assert "project_stage" in seq
