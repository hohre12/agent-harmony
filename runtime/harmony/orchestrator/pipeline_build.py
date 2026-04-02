"""Pipeline build phase — task execution, quality gate, audit, fix, escalation.

Split from pipeline.py to keep file sizes manageable.
"""

from __future__ import annotations

import json
import uuid

from harmony.orchestrator.state import SessionState, TaskState, _now_iso
from harmony.orchestrator import prompts
from harmony.orchestrator import verifier
from harmony.orchestrator import verifier_frontend
from harmony.orchestrator.utils import make_response

# The MCP server always runs in the target project's root directory.
_PROJECT_CWD = "."


# ---- Phase: build ------------------------------------------------------ #

def _handle_build(state: SessionState, data: dict, is_user_input: bool = False) -> dict:
    step = data.get("step", "")

    # --- Escalation response (user chose action) ---
    if is_user_input and (step.startswith("escalate") or state.pipeline_step.startswith("escalate")):
        answer = data.get("user_input", "").strip().lower()
        if answer in ("b", "skip"):
            return _next_build_task(state)
        if answer in ("d", "abort"):
            state.pipeline_phase = "done"
            return make_response(step="done", prompt="Pipeline aborted by user.", expect="none")
        # a (manual fix) or c (different approach) — continue build
        return _next_build_task(state)

    dispatch = {
        "build_task": _handle_build_task,
        "quality_gate": _handle_quality_gate,
        "audit": _handle_audit,
        "design_audit": _handle_design_audit,
        "fix": _handle_fix,
    }
    handler = dispatch.get(step)
    if handler:
        return handler(state, data)
    return _next_build_task(state)


def _handle_build_task(state: SessionState, data: dict) -> dict:
    """Handle build_task step result."""
    task_id = data.get("task_id", "")
    task_title = data.get("task_title", "")
    if data.get("success"):
        # Verify that code was actually written
        evidence = verifier.verify_build_evidence(cwd=_PROJECT_CWD)
        if not evidence["has_changes"]:
            return make_response(
                step="build_task",
                prompt=(
                    f"Build evidence check FAILED for task {task_id}: \"{task_title}\"\n\n"
                    "No git changes detected. The team-executor must produce actual code changes.\n"
                    "Re-run the task and ensure code is written and committed.\n\n"
                    f"Call harmony_pipeline_next with:\n"
                    f'{{"step":"build_task","task_id":"{task_id}","task_title":"{task_title}","success":true}}'
                ),
                expect="step_result",
                metadata={"task_id": task_id, "task_title": task_title},
            )
        state.pipeline_step = f"gate_{task_id}"
        return make_response(
            step="quality_gate",
            prompt=prompts.quality_gate(task_id, task_title, state.quality_thresholds),
            expect="step_result",
            metadata={"task_id": task_id, "task_title": task_title},
        )
    else:
        return _build_fix_or_escalate(state, task_id, task_title, data.get("issues", []))


def _handle_quality_gate(state: SessionState, data: dict) -> dict:
    """Handle quality_gate step result."""
    task_id = data.get("task_id", "")
    task_title = data.get("task_title", "")
    scores = data.get("scores", {})
    task = state._task_by_id(task_id)
    task.quality_scores = scores

    # Server-side cross-verification of reported scores
    verification = verifier_frontend.cross_verify_quality_scores(scores, cwd=_PROJECT_CWD)
    if not verification["verified"]:
        mismatch_details = "; ".join(
            f"{k}: reported={v['reported']}, actual={v['actual']}"
            for k, v in verification["mismatches"].items()
        )
        issues = [{"severity": "MUST-FIX", "file": "quality gate",
                    "what": f"Score mismatch detected: {mismatch_details}. Re-measure and report accurate scores."}]
        return _build_fix_or_escalate(state, task_id, task_title, issues, scores)

    # Measure design token violations and add to scores
    design_check = verifier_frontend.verify_design_tokens(cwd=_PROJECT_CWD)
    if design_check.get("verified"):
        scores["design_token_violations"] = design_check.get("violation_count", 0)
        task.quality_scores = scores

    # Fail gate when critical metrics are unverified
    unverified = verification.get("unverified", [])
    critical_unverified = [m for m in unverified if m in ("build", "tests")]
    if critical_unverified:
        issues = [{"severity": "MUST-FIX", "file": "quality gate",
                    "what": f"Critical metrics {critical_unverified} could not be verified server-side. "
                            "Install the project's test runner (pytest/jest) and re-run."}]
        return _build_fix_or_escalate(state, task_id, task_title, issues, scores)

    # Use server-measured values where available (trust actual over reported)
    actual = verification.get("actual", {})
    for key, actual_val in actual.items():
        scores[key] = actual_val
    task.quality_scores = scores

    if task.gate_passed(state.quality_thresholds):
        state.pipeline_step = f"audit_{task_id}"
        # Generate nonce for audit verification
        audit_nonce = uuid.uuid4().hex[:12]
        task.audit_nonce = audit_nonce
        audit_prompt = prompts.production_audit(task_id, task_title)
        audit_prompt += f"\n\nAUDIT_NONCE: {audit_nonce}\nYou MUST include this nonce in your response: \"audit_nonce\":\"{audit_nonce}\""
        return make_response(
            step="audit",
            prompt=audit_prompt,
            expect="step_result",
            metadata={"task_id": task_id, "task_title": task_title, "audit_nonce": audit_nonce},
        )
    else:
        failed = _gate_failures(scores, state.quality_thresholds)
        issues = [{"severity": "MUST-FIX", "file": "quality gate", "what": f}
                  for f in failed]
        return _build_fix_or_escalate(state, task_id, task_title, issues, scores)


def _handle_audit(state: SessionState, data: dict) -> dict:
    """Handle audit step result."""
    task_id = data.get("task_id", "")
    task_title = data.get("task_title", "")
    task = state._task_by_id(task_id)

    # Verify audit nonce
    expected_nonce = task.audit_nonce

    received_nonce = data.get("audit_nonce", "")

    if not expected_nonce or received_nonce != expected_nonce:
        return make_response(
            step="audit",
            prompt=f"REJECTED: audit nonce mismatch for task {task_id}.\n"
                   "The audit response must come from the agent that received the audit prompt.\n\n"
                   + prompts.production_audit(task_id, task_title),
            expect="step_result",
            metadata={"task_id": task_id, "task_title": task_title},
        )

    auditor_id = data.get("auditor_id", "")
    if not auditor_id or len(auditor_id) < 8:
        return make_response(
            step="audit",
            prompt=f"REJECTED: audit for task {task_id} has invalid auditor_id: '{auditor_id}'.\n"
                   "You MUST spawn a NEW agent via the Agent tool and include its ID.\n\n"
                   + prompts.production_audit(task_id, task_title),
            expect="step_result",
            metadata={"task_id": task_id, "task_title": task_title},
        )
    if data.get("verdict") == "PASS":
        task.auditor_id = auditor_id
        # Check if this is a frontend task that needs design audit
        task_title_lower = data.get("task_title", "").lower()
        has_frontend = any(kw in task_title_lower for kw in (
            "ui", "frontend", "page", "component", "landing", "dashboard", "layout",
        ))
        if has_frontend and task.audit_round == 0:
            # Run design quality audit as additional pass
            task.audit_round = -1  # Mark as "design audit in progress"
            return make_response(
                step="design_audit",
                prompt=prompts.design_quality_audit(task_id, task_title),
                expect="step_result",
                metadata={"task_id": task_id, "task_title": task_title},
            )
        task.status = "completed"
        task.completed_at = _now_iso()
        return _next_build_task(state)
    else:
        task.audit_round += 1
        if task.audit_round >= 3:
            return make_response(
                step="escalate",
                prompt=prompts.escalation(
                    task_title, data.get("issues", []), task.quality_scores
                ),
                expect="user_input",
                metadata={"task_id": task_id},
            )
        return make_response(
            step="fix",
            prompt=prompts.fix_issues(task_id, data.get("issues", [])),
            expect="step_result",
            metadata={"task_id": task_id, "task_title": task_title,
                       "audit_round": task.audit_round},
        )


def _handle_design_audit(state: SessionState, data: dict) -> dict:
    """Handle design quality audit result."""
    task_id = data.get("task_id", "")
    task_title = data.get("task_title", "")
    task = state._task_by_id(task_id)

    # Require auditor_id
    auditor_id = data.get("auditor_id", "")
    if not auditor_id or len(auditor_id) < 8:
        return make_response(
            step="design_audit",
            prompt=f"REJECTED: design audit for task {task_id} has invalid auditor_id.\n"
                   "You MUST spawn a NEW agent and include its ID.\n\n"
                   + prompts.design_quality_audit(task_id, task_title),
            expect="step_result",
            metadata={"task_id": task_id, "task_title": task_title},
        )

    if data.get("verdict") == "PASS":
        task.status = "completed"
        task.completed_at = _now_iso()
        return _next_build_task(state)
    else:
        # Design issues found — route to fix
        task.audit_round = 0  # Reset for normal audit flow after fix
        return make_response(
            step="fix",
            prompt=prompts.fix_issues(task_id, data.get("issues", [])),
            expect="step_result",
            metadata={"task_id": task_id, "task_title": task_title},
        )


def _handle_fix(state: SessionState, data: dict) -> dict:
    """Handle fix step result."""
    task_id = data.get("task_id", "")
    task_title = data.get("task_title", "")
    if data.get("success"):
        state.pipeline_step = f"gate_{task_id}"
        return make_response(
            step="quality_gate",
            prompt=prompts.quality_gate(task_id, task_title, state.quality_thresholds),
            expect="step_result",
            metadata={"task_id": task_id, "task_title": task_title},
        )
    return make_response(
        step="escalate",
        prompt=prompts.escalation(task_title, [], None),
        expect="user_input",
        metadata={"task_id": task_id},
    )


def _build_fix_or_escalate(
    state: SessionState, task_id: str, task_title: str,
    issues: list[dict], scores: dict | None = None,
) -> dict:
    """Route to fix or escalate based on retry count."""
    task = state._task_by_id(task_id)
    task.retry_count += 1
    if task.retry_count >= task.max_retries:
        return make_response(
            step="escalate",
            prompt=prompts.escalation(task_title, issues, scores),
            expect="user_input",
            metadata={"task_id": task_id},
        )
    return make_response(
        step="fix",
        prompt=prompts.fix_issues(task_id, issues),
        expect="step_result",
        metadata={"task_id": task_id, "task_title": task_title},
    )


def _gate_failures(scores: dict, thresholds: dict) -> list[str]:
    """Return human-readable list of failed threshold checks."""
    failures = []
    for key, min_val in thresholds.items():
        score = scores.get(key)
        if score is None:
            failures.append(f"{key}: not measured (required: {min_val})")
            continue
        if isinstance(min_val, bool):
            if score != min_val:
                failures.append(f"{key}: {score} (required: {min_val})")
        elif key in TaskState._UPPER_BOUND_KEYS:
            if score > min_val:
                failures.append(f"{key}: {score} (max allowed: {min_val})")
        else:
            if score < min_val:
                failures.append(f"{key}: {score} (minimum: {min_val})")
    return failures


def _next_build_task(state: SessionState) -> dict:
    """Find the next pending task. Uses checkpoint data for interrupted tasks."""
    tag = state.session_id[:8] if state.session_id else "v1"

    # Check for interrupted tasks with checkpoint data first
    for t in state.tasks:
        if t.status == "in_progress":
            if t.checkpoint_step:
                # Has checkpoint — resume from where it left off
                completed = sum(1 for tt in state.tasks if tt.status == "completed")
                total = len(state.tasks)
                progress = f"Task {completed + 1}/{total}"
                state.pipeline_step = f"task_{t.id}"
                return make_response(
                    step="build_task",
                    prompt=prompts.build_task(
                        t.id, t.title,
                        tag=tag,
                        checkpoint_step=t.checkpoint_step,
                        checkpoint=t.checkpoint,
                        progress=progress,
                    ),
                    expect="step_result",
                    metadata={"task_id": t.id, "task_title": t.title},
                )
            else:
                # No checkpoint — reset to pending (full restart)
                t.status = "pending"

    task = state.next_pending_task()
    if task is not None:
        completed = sum(1 for t in state.tasks if t.status == "completed")
        total = len(state.tasks)
        progress = f"Task {completed + 1}/{total}"
        state.mark_in_progress(task.id)
        state.pipeline_step = f"task_{task.id}"
        return make_response(
            step="build_task",
            prompt=prompts.build_task(task.id, task.title, tag=tag, progress=progress),
            expect="step_result",
            metadata={"task_id": task.id, "task_title": task.title},
        )

    # All tasks done -> verify (PRD compliance check)
    state.pipeline_phase = "verify"
    state.pipeline_step = "prd_compliance"
    return make_response(
        step="verify_prd",
        prompt=prompts.verify_prd_compliance(),
        expect="step_result",
    )
