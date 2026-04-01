"""Pipeline engine — drives the full harmony pipeline step by step.

The agent calls 3 MCP tools:
  harmony_pipeline_start   → start or resume
  harmony_pipeline_next    → report step result, get next instruction
  harmony_pipeline_respond → pass user input during interactive steps

Each returns a dict:
  {"step": str, "prompt": str, "expect": "user_input"|"step_result", ...}
"""

from __future__ import annotations

import json
from pathlib import Path

from harmony.orchestrator.state import SessionState, TaskState, DEFAULT_STATE_PATH, _now_iso
from harmony.orchestrator import prompts


# ====================================================================== #
#  Public API (called by MCP server)
# ====================================================================== #


def start_pipeline(user_request: str, state_path: str = DEFAULT_STATE_PATH) -> str:
    """Entry point. Check for existing session, return first instruction."""
    state = SessionState.load(state_path)

    # Resume existing session
    if state is not None and state.pipeline_phase != "done":
        result = _make_response(
            step="resume",
            prompt=prompts.resume_prompt(
                state.pipeline_phase, state.pipeline_step, state.project_name
            ),
            expect="user_input",
        )
        return json.dumps(result, ensure_ascii=False)

    # Fresh start
    import uuid
    state = SessionState(
        session_id=uuid.uuid4().hex,
        pipeline_phase="init",
        pipeline_step="start",
        user_request=user_request,
        started_at=_now_iso(),
        updated_at=_now_iso(),
    )
    state.save(state_path)

    result = _make_response(
        step="init",
        prompt=prompts.interview_start(user_request),
        expect="step_result" if user_request else "user_input",
    )
    return json.dumps(result, ensure_ascii=False)


def pipeline_next(step_result_json: str, state_path: str = DEFAULT_STATE_PATH) -> str:
    """Process step result from agent, return next instruction."""
    state = SessionState.load(state_path)
    if state is None:
        return json.dumps({"error": "No session. Call harmony_pipeline_start first."})

    try:
        result = json.loads(step_result_json)
    except (json.JSONDecodeError, TypeError) as e:
        return json.dumps({"error": f"Invalid JSON in step_result: {e}"})

    response = _advance(state, result, is_user_input=False)
    state.save(state_path)
    return json.dumps(response, ensure_ascii=False)


def pipeline_respond(user_input: str, state_path: str = DEFAULT_STATE_PATH) -> str:
    """Process user input during interactive steps, return next instruction."""
    state = SessionState.load(state_path)
    if state is None:
        return json.dumps({"error": "No session. Call harmony_pipeline_start first."})

    response = _advance(state, {"user_input": user_input}, is_user_input=True)
    state.save(state_path)
    return json.dumps(response, ensure_ascii=False)


# ====================================================================== #
#  State machine
# ====================================================================== #


def _advance(state: SessionState, data: dict, is_user_input: bool) -> dict:
    """Core state machine. Routes to phase handler based on pipeline_phase."""
    phase = state.pipeline_phase

    handlers = {
        "init": lambda: _handle_init(state, data),
        "interview": lambda: _handle_interview(state, data, is_user_input),
        "prd_gen": lambda: _handle_prd_gen(state, data),
        "prd_review": lambda: _handle_prd_review(state, data, is_user_input),
        "setup": lambda: _handle_setup(state, data),
        "build": lambda: _handle_build(state, data, is_user_input),
        "verify": lambda: _handle_verify(state, data),
        "harden": lambda: _handle_harden(state, data),
        "delivery": lambda: _handle_delivery(state, data),
        "done": lambda: _make_response(step="done", prompt="Pipeline complete.", expect="none"),
    }

    handler = handlers.get(phase)
    if handler:
        return handler()

    # Unknown phase — recover by resuming
    return _resume_to_current_step(state)


# ---- Phase: init ------------------------------------------------------- #

def _handle_init(state: SessionState, data: dict) -> dict:
    step = data.get("step", "")

    if step == "context_check":
        if data.get("has_prd"):
            state.pipeline_phase = "prd_review"
            state.pipeline_step = "review"
            state.prd_path = "docs/prd.md"
            return _make_response(
                step="prd_review",
                prompt=prompts.prd_review(),
                expect="user_input",
            )
        if data.get("has_docs"):
            doc_paths = data.get("doc_paths", [])
            state.interview_context["existing_docs"] = ", ".join(doc_paths)
        if data.get("has_code"):
            state.interview_context["has_existing_code"] = "true"

    # Start interview
    state.pipeline_phase = "interview"
    state.pipeline_step = ""

    if not state.user_request and data.get("user_input"):
        state.user_request = data["user_input"]

    return _next_interview_question(state)


# ---- Phase: interview -------------------------------------------------- #

def _handle_interview(state: SessionState, data: dict, is_user_input: bool) -> dict:
    if is_user_input:
        current_q = state.pipeline_step
        if current_q:
            state.interview_answers[current_q] = data["user_input"]
            _update_context_from_answer(state, current_q, data["user_input"])

    return _next_interview_question(state)


def _next_interview_question(state: SessionState) -> dict:
    sequence = state.interview_question_sequence()
    answered = set(state.interview_answers.keys())
    remaining = [q for q in sequence if q not in answered]

    if not remaining:
        state.pipeline_phase = "prd_gen"
        state.pipeline_step = "generate"
        return _make_response(
            step="generate_prd",
            prompt=prompts.generate_prd(state.interview_context),
            expect="step_result",
        )

    next_q = remaining[0]
    state.pipeline_step = next_q
    return _make_response(
        step=f"interview_{next_q}",
        prompt=prompts.interview_question(next_q, state.interview_context),
        expect="user_input",
    )


# Choice letter → human-readable mapping per question
_CHOICE_MAP: dict[str, dict[str, str]] = {
    "target_users": {
        "a": "Developers / technical users",
        "b": "General consumers (non-technical)",
        "c": "Internal team / company employees",
        "d": "Enterprise clients (B2B)",
        "e": "Myself only (personal tool)",
    },
    "core_problem": {
        "a": "Manual repetitive work that should be automated",
        "b": "Existing tools are too expensive",
        "c": "Existing tools are too complex / bad UX",
        "d": "No good solution exists yet",
        "e": "Internal process that needs systematizing",
    },
    "tech_stack": {
        "a": "Next.js + TypeScript + Prisma + PostgreSQL",
        "b": "React + TypeScript + Node.js + Express",
        "c": "Python + FastAPI + PostgreSQL",
        "d": "React Native + Expo + TypeScript",
        "e": "Python + Click/Typer (CLI)",
    },
    "project_stage": {
        "a": "Prototype",
        "b": "MVP",
        "c": "Production",
    },
    "design": {
        "a": "Clean & minimal (shadcn/ui)",
        "b": "Bold & creative (custom design)",
        "c": "Match a reference",
        "d": "Functional only (handle design separately)",
    },
    "auth": {
        "a": "Email + password",
        "b": "Social login only (Google, GitHub)",
        "c": "Email + social login (both)",
        "d": "Magic link (passwordless)",
        "e": "No authentication needed",
    },
    "monetization": {
        "a": "Free forever (open source / personal)",
        "b": "Freemium (free + paid)",
        "c": "Subscription only",
        "d": "One-time purchase",
        "e": "Not decided yet",
    },
    "deployment": {
        "a": "Vercel",
        "b": "AWS",
        "c": "Railway / Render",
        "d": "Self-hosted / Docker",
        "e": "Local only",
    },
}


def _resolve_answer(question_id: str, raw_answer: str) -> str:
    """Convert short letter answers to full text. Pass through free text."""
    letter = raw_answer.strip().lower().rstrip(")")
    # Extract just the letter if answer is like "a) Developers" or "a"
    if letter and letter[0] in "abcdef":
        letter = letter[0]
    choices = _CHOICE_MAP.get(question_id, {})
    return choices.get(letter, raw_answer)


def _update_context_from_answer(state: SessionState, question_id: str, answer: str) -> None:
    """Derive structured context from raw answers."""
    ctx = state.interview_context
    ctx["user_request"] = state.user_request

    # Resolve short letters to full text
    resolved = _resolve_answer(question_id, answer)
    ctx[question_id] = resolved

    # Only detect project_type if not already set (first match wins)
    if "project_type" not in ctx:
        resolved_lower = resolved.lower()
        if question_id == "target_users" and "myself" in resolved_lower:
            ctx["project_type"] = "personal"
        elif "cli" in resolved_lower or "command-line" in resolved_lower:
            ctx["project_type"] = "cli"
        elif "library" in resolved_lower or "package" in resolved_lower:
            ctx["project_type"] = "library"
        elif "api" in resolved_lower and "only" in resolved_lower:
            ctx["project_type"] = "api"


# ---- Phase: prd_gen ---------------------------------------------------- #

def _handle_prd_gen(state: SessionState, data: dict) -> dict:
    if data.get("success"):
        state.prd_path = data.get("prd_path", "docs/prd.md")
        state.pipeline_phase = "prd_review"
        state.pipeline_step = "review"
        return _make_response(
            step="prd_review",
            prompt=prompts.prd_review(),
            expect="user_input",
        )
    return _make_response(
        step="generate_prd_retry",
        prompt="PRD generation failed. Try again.\n" + prompts.generate_prd(state.interview_context),
        expect="step_result",
    )


# ---- Phase: prd_review ------------------------------------------------- #

def _handle_prd_review(state: SessionState, data: dict, is_user_input: bool) -> dict:
    if not is_user_input:
        return _make_response(step="prd_review", prompt=prompts.prd_review(), expect="user_input")

    answer = data.get("user_input", "").strip().lower()

    if answer in ("a", "approve"):
        state.prd_approved = True
        state.pipeline_phase = "setup"
        state.pipeline_step = ""
        return _next_setup_step(state)

    if answer in ("d", "start over"):
        state.pipeline_phase = "interview"
        state.pipeline_step = ""
        state.interview_answers.clear()
        return _next_interview_question(state)

    return _make_response(
        step="prd_review_continue",
        prompt="Show the user what they requested, then ask for approval again."
        + "\n\nWhen done, call harmony_pipeline_respond with the user's final answer.",
        expect="user_input",
    )


# ---- Phase: setup ------------------------------------------------------ #

_SETUP_SEQUENCE = [
    "project_init", "generate_agents", "build_refs",
    "generate_tasks", "setup_team_executor",
]


def _handle_setup(state: SessionState, data: dict) -> dict:
    step = data.get("step", "")

    # generate_tasks returns tasks in the result — validate and store
    if step == "generate_tasks" and data.get("success"):
        tasks_data = data.get("tasks", [])

        # Validate: must be a non-empty list of dicts with id and title
        if not isinstance(tasks_data, list) or not tasks_data:
            return _make_response(
                step="generate_tasks",
                prompt="Task generation returned no tasks. Try again.\n\n" + prompts.generate_tasks(),
                expect="step_result",
            )

        try:
            for t in tasks_data:
                if not isinstance(t, dict) or "id" not in t or "title" not in t:
                    raise ValueError(f"Invalid task format: {t}")
                state.tasks.append(TaskState(
                    id=str(t["id"]),
                    title=t["title"],
                    assigned_agent=t.get("agent", ""),
                ))
        except (TypeError, ValueError):
            state.tasks.clear()
            return _make_response(
                step="generate_tasks",
                prompt="Task format invalid. Each task needs 'id' and 'title'.\n\n" + prompts.generate_tasks(),
                expect="step_result",
            )

        state.total_tasks = len(state.tasks)
        state.setup_progress[step] = "done"
        return _next_setup_step(state)

    if step and data.get("success"):
        state.setup_progress[step] = "done"
    return _next_setup_step(state)


def _next_setup_step(state: SessionState) -> dict:
    for step_name in _SETUP_SEQUENCE:
        if state.setup_progress.get(step_name) != "done":
            state.pipeline_step = step_name
            actual_step = step_name
            if step_name == "project_init" and state.interview_context.get("has_existing_code"):
                actual_step = "codebase_init"
            return _make_response(
                step=actual_step,
                prompt=prompts.setup_step(actual_step),
                expect="step_result",
            )

    # All setup done → move to build
    state.pipeline_phase = "build"
    state.pipeline_step = "executing"
    return _next_build_task(state)


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
            return _make_response(step="done", prompt="Pipeline aborted by user.", expect="none")
        # a (manual fix) or c (different approach) — continue build
        return _next_build_task(state)

    # --- Build task completed → run quality gate ---
    if step == "build_task":
        task_id = data.get("task_id", "")
        task_title = data.get("task_title", "")
        if data.get("success"):
            state.pipeline_step = f"gate_{task_id}"
            return _make_response(
                step="quality_gate",
                prompt=prompts.quality_gate(task_id, task_title, state.quality_thresholds),
                expect="step_result",
                metadata={"task_id": task_id, "task_title": task_title},
            )
        else:
            return _build_fix_or_escalate(state, task_id, task_title, data.get("issues", []))

    # --- Quality gate result (deterministic) ---
    if step == "quality_gate":
        task_id = data.get("task_id", "")
        task_title = data.get("task_title", "")
        scores = data.get("scores", {})
        task = state._task_by_id(task_id)
        task.quality_scores = scores

        if task.gate_passed(state.quality_thresholds):
            # Gate passed → proceed to AI audit
            state.pipeline_step = f"audit_{task_id}"
            return _make_response(
                step="audit",
                prompt=prompts.production_audit(task_id, task_title),
                expect="step_result",
                metadata={"task_id": task_id, "task_title": task_title},
            )
        else:
            # Gate failed → fix and re-gate
            failed = _gate_failures(scores, state.quality_thresholds)
            issues = [{"severity": "MUST-FIX", "file": "quality gate", "what": f}
                      for f in failed]
            return _build_fix_or_escalate(state, task_id, task_title, issues, scores)

    # --- Audit result (AI-based) ---
    if step == "audit":
        task_id = data.get("task_id", "")
        task_title = data.get("task_title", "")
        task = state._task_by_id(task_id)
        if data.get("verdict") == "PASS":
            task.status = "completed"
            task.completed_at = _now_iso()
            return _next_build_task(state)
        else:
            task.audit_round += 1
            if task.audit_round >= 3:
                # 3 rounds failed → escalate (NO auto-pass)
                return _make_response(
                    step="escalate",
                    prompt=prompts.escalation(
                        task_title, data.get("issues", []), task.quality_scores
                    ),
                    expect="user_input",
                    metadata={"task_id": task_id},
                )
            return _make_response(
                step="fix",
                prompt=prompts.fix_issues(task_id, data.get("issues", [])),
                expect="step_result",
                metadata={"task_id": task_id, "task_title": task_title,
                           "audit_round": task.audit_round},
            )

    # --- Fix result → re-run quality gate ---
    if step == "fix":
        task_id = data.get("task_id", "")
        task_title = data.get("task_title", "")
        audit_round = data.get("audit_round", 0)
        if data.get("success"):
            # After fix, re-run quality gate (deterministic check)
            state.pipeline_step = f"gate_{task_id}"
            return _make_response(
                step="quality_gate",
                prompt=prompts.quality_gate(task_id, task_title, state.quality_thresholds),
                expect="step_result",
                metadata={"task_id": task_id, "task_title": task_title},
            )
        # Fix failed → escalate
        return _make_response(
            step="escalate",
            prompt=prompts.escalation(task_title, [], None),
            expect="user_input",
            metadata={"task_id": task_id},
        )

    # Default: continue
    return _next_build_task(state)


def _build_fix_or_escalate(
    state: SessionState, task_id: str, task_title: str,
    issues: list[dict], scores: dict | None = None,
) -> dict:
    """Route to fix or escalate based on retry count."""
    task = state._task_by_id(task_id)
    task.retry_count += 1
    if task.retry_count >= task.max_retries:
        return _make_response(
            step="escalate",
            prompt=prompts.escalation(task_title, issues, scores),
            expect="user_input",
            metadata={"task_id": task_id},
        )
    return _make_response(
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
        elif key.startswith("max_"):
            if score > min_val:
                failures.append(f"{key}: {score} (max allowed: {min_val})")
        else:
            if score < min_val:
                failures.append(f"{key}: {score} (minimum: {min_val})")
    return failures


def _next_build_task(state: SessionState) -> dict:
    """Find the next pending task. Resets any in_progress tasks first (crash recovery)."""
    for t in state.tasks:
        if t.status == "in_progress":
            t.status = "pending"
    task = state.next_pending_task()
    if task is not None:
        state.mark_in_progress(task.id)
        state.pipeline_step = f"task_{task.id}"
        return _make_response(
            step="build_task",
            prompt=prompts.build_task(task.id, task.title),
            expect="step_result",
            metadata={"task_id": task.id, "task_title": task.title},
        )

    # All tasks done → verify (PRD compliance check)
    state.pipeline_phase = "verify"
    state.pipeline_step = "prd_compliance"
    return _make_response(
        step="verify_prd",
        prompt=prompts.verify_prd_compliance(),
        expect="step_result",
    )


# ---- Phase: verify (PRD compliance — whole project) ---------------------- #

def _handle_verify(state: SessionState, data: dict) -> dict:
    step = data.get("step", "")

    if step == "verify_prd":
        gaps = data.get("gaps", [])
        if not gaps:
            # All features verified → harden
            state.pipeline_phase = "harden"
            state.pipeline_step = "security_review"
            return _make_response(
                step="harden_security",
                prompt=prompts.harden_security_review(),
                expect="step_result",
            )
        else:
            # Gaps found → fix tasks
            verify_round = state.verify_round + 1
            state.verify_round = verify_round
            if verify_round > 2:
                # Max 2 rounds, accept and move on
                state.pipeline_phase = "harden"
                state.pipeline_step = "security_review"
                return _make_response(
                    step="harden_security",
                    prompt=prompts.harden_security_review(),
                    expect="step_result",
                )
            return _make_response(
                step="verify_fix",
                prompt=prompts.verify_fix_gaps(gaps),
                expect="step_result",
                metadata={"verify_round": verify_round},
            )

    if step == "verify_fix":
        # After fixing gaps, re-verify
        state.pipeline_step = "prd_compliance"
        return _make_response(
            step="verify_prd",
            prompt=prompts.verify_prd_compliance(),
            expect="step_result",
        )

    # Default: start verification
    return _make_response(
        step="verify_prd",
        prompt=prompts.verify_prd_compliance(),
        expect="step_result",
    )


# ---- Phase: harden (security + quality — whole project) ------------------- #

def _handle_harden(state: SessionState, data: dict) -> dict:
    step = data.get("step", "")

    if step == "harden_security":
        criticals = data.get("critical_count", 0)
        if criticals == 0:
            # No critical issues → delivery
            state.pipeline_phase = "delivery"
            state.pipeline_step = "final_check"
            return _make_response(
                step="final_check",
                prompt=prompts.final_check(),
                expect="step_result",
            )
        else:
            harden_round = state.harden_round + 1
            state.harden_round = harden_round
            if harden_round > 2:
                # Max 2 rounds, proceed with warnings
                state.pipeline_phase = "delivery"
                state.pipeline_step = "final_check"
                return _make_response(
                    step="final_check",
                    prompt=prompts.final_check(),
                    expect="step_result",
                )
            return _make_response(
                step="harden_fix",
                prompt=prompts.harden_fix_criticals(data.get("criticals", [])),
                expect="step_result",
                metadata={"harden_round": harden_round},
            )

    if step == "harden_fix":
        # After fixing, re-review
        state.pipeline_step = "security_review"
        return _make_response(
            step="harden_security",
            prompt=prompts.harden_security_review(),
            expect="step_result",
        )

    # Default: start hardening
    return _make_response(
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
            return _make_response(
                step="summary",
                prompt=prompts.delivery_summary({
                    "project_name": state.project_name,
                    "completed": c.get("completed", 0),
                    "total": state.total_tasks,
                }),
                expect="none",
            )
        return _make_response(
            step="final_fix",
            prompt="Final integration check failed. Fix the issues and re-run.\n"
            "Call harmony_pipeline_next with "
            '{"step":"final_check","success":true/false}',
            expect="step_result",
        )

    state.pipeline_phase = "done"
    return _make_response(step="done", prompt="Pipeline complete.", expect="none")


# ---- Resume ------------------------------------------------------------ #

def _resume_to_current_step(state: SessionState) -> dict:
    """Resume to the current pipeline step."""
    phase = state.pipeline_phase

    if phase == "interview":
        return _next_interview_question(state)
    if phase == "prd_gen":
        return _make_response(
            step="generate_prd",
            prompt=prompts.generate_prd(state.interview_context),
            expect="step_result",
        )
    if phase == "prd_review":
        return _make_response(step="prd_review", prompt=prompts.prd_review(), expect="user_input")
    if phase == "setup":
        return _next_setup_step(state)
    if phase == "build":
        return _next_build_task(state)
    if phase == "verify":
        return _make_response(step="verify_prd", prompt=prompts.verify_prd_compliance(), expect="step_result")
    if phase == "harden":
        return _make_response(step="harden_security", prompt=prompts.harden_security_review(), expect="step_result")
    if phase == "delivery":
        return _make_response(step="final_check", prompt=prompts.final_check(), expect="step_result")

    return _make_response(step="done", prompt="Pipeline complete.", expect="none")


# ====================================================================== #
#  Helpers
# ====================================================================== #


def _make_response(
    step: str,
    prompt: str,
    expect: str,
    metadata: dict | None = None,
) -> dict:
    """Build a standardized response dict."""
    resp = {"step": step, "prompt": prompt, "expect": expect}
    if metadata:
        resp["metadata"] = metadata
    return resp
