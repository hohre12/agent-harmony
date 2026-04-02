"""Tests for harmony.orchestrator.prompts — verify prompt quality."""

from __future__ import annotations

import pytest

from harmony.orchestrator import prompts


class TestPromptLength:
    """Every prompt must be under 50 lines."""

    MAX_LINES = 50

    def _check_length(self, text: str, name: str):
        lines = text.strip().split("\n")
        assert len(lines) <= self.MAX_LINES, (
            f"Prompt '{name}' is {len(lines)} lines (max {self.MAX_LINES})"
        )

    def test_interview_start_with_request(self):
        self._check_length(prompts.interview_start("build a todo app"), "interview_start")

    def test_interview_start_empty(self):
        self._check_length(prompts.interview_start(""), "interview_start_empty")

    def test_all_interview_questions(self):
        ctx = {"user_request": "test"}
        for q_id in ["target_users", "core_problem", "features", "tech_stack",
                      "project_stage", "design", "auth", "monetization", "deployment"]:
            text = prompts.interview_question(q_id, ctx)
            self._check_length(text, f"interview_{q_id}")

    def test_generate_prd(self):
        ctx = {"user_request": "test", "target_users": "devs", "tech_stack": "Next.js"}
        self._check_length(prompts.generate_prd(ctx), "generate_prd")

    def test_prd_review(self):
        self._check_length(prompts.prd_review(), "prd_review")

    def test_setup_steps(self):
        for step in ["project_init", "generate_agents", "build_refs", "generate_tasks"]:
            self._check_length(prompts.setup_step(step), f"setup_{step}")

    def test_build_task(self):
        self._check_length(prompts.build_task("1", "Auth"), "build_task")

    def test_quality_gate(self):
        thresholds = {"build": True, "tests": True, "test_coverage": 60.0}
        self._check_length(prompts.quality_gate("1", "Auth", thresholds), "quality_gate")

    def test_production_audit(self):
        self._check_length(prompts.production_audit("1", "Auth"), "production_audit")

    def test_fix_issues(self):
        issues = [{"severity": "MUST-FIX", "file": "auth.ts", "what": "missing validation"}]
        self._check_length(prompts.fix_issues("1", issues), "fix_issues")

    def test_escalation(self):
        issues = [{"what": "test failure"}]
        self._check_length(prompts.escalation("Auth", issues), "escalation")

    def test_final_check(self):
        self._check_length(prompts.final_check(), "final_check")

    def test_delivery_summary(self):
        self._check_length(prompts.delivery_summary({"project_name": "test"}), "delivery_summary")

    def test_resume_prompt(self):
        self._check_length(prompts.resume_prompt("build", "task_3", "myapp"), "resume")


class TestPromptCallbacks:
    """Prompts must contain callback instructions."""

    def test_interview_has_respond_hint(self):
        text = prompts.interview_question("target_users", {})
        assert "harmony_pipeline_respond" in text

    def test_prd_gen_has_next_hint(self):
        text = prompts.generate_prd({"user_request": "test"})
        assert "harmony_pipeline_next" in text

    def test_setup_has_next_hint(self):
        text = prompts.setup_step("project_init")
        assert "harmony_pipeline_next" in text

    def test_build_has_next_hint(self):
        text = prompts.build_task("1", "Auth")
        assert "harmony_pipeline_next" in text

    def test_quality_gate_has_next_hint(self):
        text = prompts.quality_gate("1", "Auth", {"build": True})
        assert "harmony_pipeline_next" in text

    def test_quality_gate_has_thresholds(self):
        text = prompts.quality_gate("1", "Auth", {"test_coverage": 60.0, "max_file_lines": 500})
        assert "test_coverage" in text
        assert "max_file_lines" in text

    def test_security_review_has_tool_commands(self):
        text = prompts.harden_security_review()
        assert "bandit" in text or "npm audit" in text
        assert "grep" in text

    def test_audit_has_next_hint(self):
        text = prompts.production_audit("1", "Auth")
        assert "harmony_pipeline_next" in text


class TestQualityGatePrompt:
    def test_contains_all_threshold_keys(self):
        from harmony.orchestrator.state import DEFAULT_QUALITY_THRESHOLDS
        prompt = prompts.quality_gate("1", "Auth", DEFAULT_QUALITY_THRESHOLDS)
        for key in DEFAULT_QUALITY_THRESHOLDS:
            assert key in prompt

    def test_contains_null_metric_guidance(self):
        from harmony.orchestrator.state import DEFAULT_QUALITY_THRESHOLDS
        prompt = prompts.quality_gate("1", "Auth", DEFAULT_QUALITY_THRESHOLDS)
        assert "omit" in prompt.lower() or "null" in prompt.lower() or "cannot be measured" in prompt.lower()

    def test_contains_a11y_check(self):
        from harmony.orchestrator.state import DEFAULT_QUALITY_THRESHOLDS
        prompt = prompts.quality_gate("1", "Auth", DEFAULT_QUALITY_THRESHOLDS)
        assert "a11y" in prompt.lower() or "accessibility" in prompt.lower()


class TestProductionAuditPrompt:
    def test_requires_agent_spawning(self):
        prompt = prompts.production_audit("1", "Auth")
        assert "Agent tool" in prompt or "spawn" in prompt.lower()

    def test_requires_auditor_id(self):
        prompt = prompts.production_audit("1", "Auth")
        assert "auditor_id" in prompt

    def test_uses_merge_base(self):
        prompt = prompts.production_audit("1", "Auth")
        assert "merge-base" in prompt
        # The prompt mentions HEAD~1 only to warn AGAINST using it
        assert "Do NOT use HEAD~1" in prompt or "Do not use HEAD~1" in prompt


class TestSecurityReviewPrompt:
    def test_requires_auditor_id(self):
        prompt = prompts.harden_security_review()
        assert "auditor_id" in prompt


class TestDesignQualityAudit:
    def test_contains_anti_ai_checklist(self):
        from harmony.orchestrator.prompts.design import design_quality_audit
        prompt = design_quality_audit("1", "Landing Page")
        assert "Anti-AI" in prompt
        assert "line-height" in prompt.lower() or "Line-height" in prompt
        assert "typography" in prompt.lower()

    def test_requires_agent_spawning(self):
        from harmony.orchestrator.prompts.design import design_quality_audit
        prompt = design_quality_audit("1", "Landing Page")
        assert "Agent tool" in prompt
        assert "auditor_id" in prompt

    def test_design_checklist_has_sections(self):
        from harmony.orchestrator.prompts.design import DESIGN_CHECKLIST
        assert "Typography" in DESIGN_CHECKLIST
        assert "Spacing" in DESIGN_CHECKLIST
        assert "Anti-AI" in DESIGN_CHECKLIST
        assert "hover" in DESIGN_CHECKLIST.lower()

    def test_design_brief_requirements(self):
        from harmony.orchestrator.prompts.design import design_brief_requirements
        reqs = design_brief_requirements()
        assert "Color" in reqs
        assert "Typography" in reqs
        assert "Spacing" in reqs
        assert "Component" in reqs
        assert "Motion" in reqs


class TestVerifyPrompt:
    def test_requires_auditor_id(self):
        prompt = prompts.verify_prd_compliance()
        assert "auditor_id" in prompt
