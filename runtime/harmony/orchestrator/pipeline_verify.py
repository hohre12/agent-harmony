"""Pipeline verify, harden, delivery, and resume phases.

Split from pipeline.py to keep file sizes manageable.
"""

from __future__ import annotations

from harmony.orchestrator.state import SessionState
from harmony.orchestrator import prompts
from harmony.orchestrator.utils import make_response


# ---- Phase: verify (PRD compliance -- whole project) ---------------------- #

def _verify_check_auditor(data: dict) -> dict | None:
    """Check auditor_id, return rejection response or None."""
    auditor_id = data.get("auditor_id", "")
    if not auditor_id or len(auditor_id) < 8:
        return make_response(
            step="verify_prd",
            prompt="REJECTED: verification missing valid auditor_id.\n"
                   "You MUST spawn a NEW agent via the Agent tool and include its ID (min 8 chars).\n\n"
                   + prompts.verify_prd_compliance(),
            expect="step_result",
        )
    return None


def _verify_handle_gaps(state, gaps: list, verify_round: int) -> dict:
    """Handle PRD compliance gaps — fix or escalate."""
    if verify_round > 2:
        gap_text = "\n".join(f"- {g}" for g in gaps[:10])
        return make_response(
            step="verify_escalate",
            prompt=(
                f"PRD verification failed after {verify_round} rounds.\n\n"
                f"Remaining gaps:\n{gap_text}\n\n"
                "You MUST call the AskUserQuestion tool to present these choices:\n"
                "  a) Show details — I'll fix manually\n"
                "  b) Accept gaps and continue to security hardening\n"
                "  c) Try a different approach\n"
                "  d) Abort\n"
                "  → Recommended: b)\n\n"
                "Interpret their answer and call harmony_pipeline_respond with the letter."
            ),
            expect="user_input",
        )
    return make_response(
        step="verify_fix",
        prompt=prompts.verify_fix_gaps(gaps),
        expect="step_result",
        metadata={"verify_round": verify_round},
    )


def _handle_verify(state: SessionState, data: dict, is_user_input: bool = False) -> dict:
    if is_user_input:
        answer = data.get("user_input", "").strip().lower()
        if answer in ("b", "accept"):
            state.pipeline_phase = "harden"
            state.pipeline_step = "security_review"
            return make_response(
                step="harden_security",
                prompt=prompts.harden_security_review(),
                expect="step_result",
            )
        if answer in ("d", "abort"):
            state.pipeline_phase = "done"
            return make_response(step="done", prompt="Pipeline aborted by user.", expect="none")
        # a (manual fix) or c (different approach) — re-verify
        return make_response(
            step="verify_prd",
            prompt=prompts.verify_prd_compliance(),
            expect="step_result",
        )

    step = data.get("step", "")

    if step == "verify_prd":
        rejection = _verify_check_auditor(data)
        if rejection:
            return rejection
        gaps = data.get("gaps", [])
        if not gaps:
            state.pipeline_phase = "harden"
            state.pipeline_step = "security_review"
            return make_response(
                step="harden_security",
                prompt=prompts.harden_security_review(),
                expect="step_result",
            )
        verify_round = state.verify_round + 1
        state.verify_round = verify_round
        return _verify_handle_gaps(state, gaps, verify_round)

    if step == "verify_fix":
        # After fixing gaps, re-verify
        state.pipeline_step = "prd_compliance"
        return make_response(
            step="verify_prd",
            prompt=prompts.verify_prd_compliance(),
            expect="step_result",
        )

    # Default: start verification
    return make_response(
        step="verify_prd",
        prompt=prompts.verify_prd_compliance(),
        expect="step_result",
    )


# ---- Phase: harden (security + quality -- whole project) ------------------- #

def _harden_check_auditor(data: dict) -> dict | None:
    """Check auditor_id for security review, return rejection or None."""
    auditor_id = data.get("auditor_id", "")
    if not auditor_id or len(auditor_id) < 8:
        return make_response(
            step="harden_security",
            prompt="REJECTED: security review missing valid auditor_id.\n"
                   "You MUST spawn a NEW agent via the Agent tool and include its ID (min 8 chars).\n\n"
                   + prompts.harden_security_review(),
            expect="step_result",
        )
    return None


def _harden_handle_criticals(state, data: dict, criticals: int, harden_round: int) -> dict:
    """Handle critical security issues — fix or escalate."""
    if harden_round > 2:
        crit_text = "\n".join(
            f"- {c.get('file','?')}:{c.get('line','?')} — {c.get('description','?')}"
            for c in data.get("criticals", [])[:10]
        )
        return make_response(
            step="harden_escalate",
            prompt=(
                f"Security hardening failed after {harden_round} rounds.\n"
                f"{criticals} critical issue(s) remain.\n\n"
                f"Issues:\n{crit_text}\n\n"
                "You MUST call the AskUserQuestion tool to present these choices:\n"
                "  a) Show details — I'll fix manually\n"
                "  b) Accept risks and continue to delivery\n"
                "  c) Try a different approach\n"
                "  d) Abort\n"
                "  → Recommended: a)\n\n"
                "Interpret their answer and call harmony_pipeline_respond with the letter."
            ),
            expect="user_input",
        )
    return make_response(
        step="harden_fix",
        prompt=prompts.harden_fix_criticals(data.get("criticals", [])),
        expect="step_result",
        metadata={"harden_round": harden_round},
    )


def _handle_harden(state: SessionState, data: dict, is_user_input: bool = False) -> dict:
    if is_user_input:
        answer = data.get("user_input", "").strip().lower()
        if answer in ("b", "accept"):
            state.pipeline_phase = "delivery"
            state.pipeline_step = "final_check"
            return make_response(
                step="final_check",
                prompt=prompts.final_check(),
                expect="step_result",
            )
        if answer in ("d", "abort"):
            state.pipeline_phase = "done"
            return make_response(step="done", prompt="Pipeline aborted by user.", expect="none")
        # a (manual fix) or c (different approach) — re-harden
        return make_response(
            step="harden_security",
            prompt=prompts.harden_security_review(),
            expect="step_result",
        )

    step = data.get("step", "")

    if step == "harden_security":
        rejection = _harden_check_auditor(data)
        if rejection:
            return rejection
        criticals = data.get("critical_count", 0)
        if criticals == 0:
            state.pipeline_phase = "delivery"
            state.pipeline_step = "final_check"
            return make_response(
                step="final_check",
                prompt=prompts.final_check(),
                expect="step_result",
            )
        harden_round = state.harden_round + 1
        state.harden_round = harden_round
        return _harden_handle_criticals(state, data, criticals, harden_round)

    if step == "harden_fix":
        # After fixing, re-review
        state.pipeline_step = "security_review"
        return make_response(
            step="harden_security",
            prompt=prompts.harden_security_review(),
            expect="step_result",
        )

    # Default: start hardening
    return make_response(
        step="harden_security",
        prompt=prompts.harden_security_review(),
        expect="step_result",
    )


# ---- Phase: delivery --------------------------------------------------- #

def _handle_delivery(state: SessionState, data: dict) -> dict:
    step = data.get("step", "")

    if step == "final_check":
        if data.get("success"):
            state.pipeline_phase = "done"
            state.pipeline_step = "complete"
            c = state.counts()
            return make_response(
                step="summary",
                prompt=prompts.delivery_summary({
                    "project_name": state.project_name,
                    "completed": c.get("completed", 0),
                    "total": state.total_tasks,
                }),
                expect="none",
            )
        return make_response(
            step="final_fix",
            prompt="Final integration check failed. Fix the issues and re-run.\n"
            "Call harmony_pipeline_next with "
            '{"step":"final_check","success":true/false}',
            expect="step_result",
        )

    state.pipeline_phase = "done"
    return make_response(step="done", prompt="Pipeline complete.", expect="none")


# ---- Resume ------------------------------------------------------------ #

def _resume_to_current_step(state: SessionState) -> dict:
    """Resume to the current pipeline step."""
    from harmony.orchestrator.pipeline import _next_interview_question, _next_setup_step
    from harmony.orchestrator.pipeline_build import _next_build_task

    phase = state.pipeline_phase

    if phase == "interview":
        return _next_interview_question(state)
    if phase == "prd_gen":
        return make_response(
            step="generate_prd",
            prompt=prompts.generate_prd(state.interview_context),
            expect="step_result",
        )
    if phase == "prd_review":
        return make_response(step="prd_review", prompt=prompts.prd_review(), expect="user_input")
    if phase == "setup":
        return _next_setup_step(state)
    if phase == "build":
        return _next_build_task(state)
    if phase == "verify":
        return make_response(step="verify_prd", prompt=prompts.verify_prd_compliance(), expect="step_result")
    if phase == "harden":
        return make_response(step="harden_security", prompt=prompts.harden_security_review(), expect="step_result")
    if phase == "delivery":
        return make_response(step="final_check", prompt=prompts.final_check(), expect="step_result")

    return make_response(step="done", prompt="Pipeline complete.", expect="none")
