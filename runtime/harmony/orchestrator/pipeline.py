"""Pipeline engine — drives the full harmony pipeline step by step.

Public API: start_pipeline, pipeline_next, pipeline_respond.
Each returns {"step": str, "prompt": str, "expect": "user_input"|"step_result", ...}
"""

from __future__ import annotations

import json
import os
from pathlib import Path, PurePosixPath

from harmony.orchestrator.state import SessionState, DEFAULT_STATE_PATH, _now_iso
from harmony.orchestrator import prompts
from harmony.orchestrator import verifier
from harmony.orchestrator.prompts.interview import resolve_answer

from harmony.orchestrator.utils import make_response
from harmony.orchestrator.pipeline_build import _handle_build
from harmony.orchestrator.pipeline_verify import (
    _handle_verify, _handle_harden, _handle_delivery, _resume_to_current_step,
)
from harmony.orchestrator.pipeline_setup import _handle_setup, _next_setup_step


# ====================================================================== #
#  Path validation
# ====================================================================== #

_ALLOWED_PRD_EXTENSIONS = {".md"}


def _validate_prd_path(path: str) -> str:
    """Validate prd_path from agent data — prevent path traversal and restrict extension.

    Rules:
    - Must not contain '..' components
    - Must be a relative path (not absolute)
    - Must resolve to within the current working directory
    - Must have an allowed extension (.md)

    Returns the validated path string, or raises ValueError.
    """
    if not path or not isinstance(path, str):
        raise ValueError("prd_path must be a non-empty string")
    # Reject absolute paths
    if path.startswith("/") or path.startswith("\\"):
        raise ValueError(f"Absolute prd_path denied: {path}")
    # Reject traversal components
    for part in PurePosixPath(path).parts:
        if part == "..":
            raise ValueError(f"Path traversal denied in prd_path: {path}")
    # Verify extension
    ext = PurePosixPath(path).suffix.lower()
    if ext not in _ALLOWED_PRD_EXTENSIONS:
        raise ValueError(
            f"Invalid prd_path extension '{ext}': only {_ALLOWED_PRD_EXTENSIONS} allowed"
        )
    # Verify resolved path stays within project directory
    resolved = Path(path).resolve()
    cwd = Path.cwd().resolve()
    if resolved != cwd and not str(resolved).startswith(str(cwd) + os.sep):
        raise ValueError(f"prd_path escapes project directory: {path}")
    return path


# ====================================================================== #
#  Public API
# ====================================================================== #


def start_pipeline(user_request: str, state_path: str = DEFAULT_STATE_PATH) -> str:
    """Entry point. Check for existing session, return first instruction."""
    state = SessionState.load(state_path)

    # Resume existing session
    if state is not None and state.pipeline_phase != "done":
        result = make_response(
            step="resume",
            prompt=prompts.resume_prompt(
                state.pipeline_phase, state.pipeline_step, state.project_name
            ),
            expect="user_input",
        )
        state.pipeline_step = "awaiting_resume"
        state.save(state_path)
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

    result = make_response(
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
#  State machine router
# ====================================================================== #

def _handle_resume(state: SessionState, data: dict) -> dict:
    """Handle user response to resume prompt."""
    answer = data.get("user_input", "").strip().lower()
    if answer in ("a", "resume"):
        state.pipeline_step = ""
        # Refresh quality thresholds from current plugin version
        # (fixes stale thresholds when plugin is upgraded mid-session)
        from harmony.orchestrator.state import thresholds_for_stage
        stage = state.interview_context.get("project_stage", "").lower()
        if stage:
            state.quality_thresholds = thresholds_for_stage(stage)
        return _resume_to_current_step(state)
    if answer in ("b", "start over"):
        import uuid
        state.session_id = uuid.uuid4().hex
        state.pipeline_phase = "init"
        state.pipeline_step = ""
        state.interview_answers.clear()
        state.interview_context.clear()
        state.setup_progress.clear()
        state.tasks.clear()
        state.total_tasks = 0
        state.prd_approved = False
        state.verify_round = 0
        state.harden_round = 0
        state.team_config = {}
        from harmony.orchestrator.state import DEFAULT_QUALITY_THRESHOLDS
        state.quality_thresholds = dict(DEFAULT_QUALITY_THRESHOLDS)
        return make_response(
            step="init",
            prompt=prompts.interview_start(""),
            expect="user_input",
        )
    if answer in ("c", "status"):
        return make_response(
            step="resume",
            prompt=state.progress_summary() + "\n\n" + prompts.resume_prompt(
                state.pipeline_phase, state.pipeline_step, state.project_name
            ),
            expect="user_input",
        )
    return make_response(
        step="resume",
        prompt=prompts.resume_prompt(state.pipeline_phase, state.pipeline_step, state.project_name),
        expect="user_input",
    )


def _advance(state: SessionState, data: dict, is_user_input: bool) -> dict:
    """Core state machine. Routes to phase handler based on pipeline_phase."""
    phase = state.pipeline_phase

    # Handle resume response before routing to phase handler
    if state.pipeline_step == "awaiting_resume" and is_user_input:
        return _handle_resume(state, data)

    handlers = {
        "init": lambda: _handle_init(state, data),
        "interview": lambda: _handle_interview(state, data, is_user_input),
        "prd_gen": lambda: _handle_prd_gen(state, data),
        "prd_review": lambda: _handle_prd_review(state, data, is_user_input),
        "setup": lambda: _handle_setup(state, data),
        "build": lambda: _handle_build(state, data, is_user_input),
        "verify": lambda: _handle_verify(state, data, is_user_input),
        "harden": lambda: _handle_harden(state, data, is_user_input),
        "delivery": lambda: _handle_delivery(state, data),
        "done": lambda: make_response(step="done", prompt="Pipeline complete.", expect="none"),
    }

    handler = handlers.get(phase)
    if handler:
        return handler()

    # Unknown phase — recover by resuming
    return _resume_to_current_step(state)

# ---- Phase: init -------------------------------------------------------- #
def _handle_init(state: SessionState, data: dict) -> dict:
    step = data.get("step", "")

    if step == "context_check":
        if data.get("has_prd"):
            state.pipeline_phase = "prd_review"
            state.pipeline_step = "review"
            state.prd_path = "docs/prd.md"
            return make_response(
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

# ---- Phase: interview --------------------------------------------------- #
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
        return make_response(
            step="generate_prd",
            prompt=prompts.generate_prd(state.interview_context),
            expect="step_result",
        )

    next_q = remaining[0]
    state.pipeline_step = next_q
    return make_response(
        step=f"interview_{next_q}",
        prompt=prompts.interview_question(next_q, state.interview_context),
        expect="user_input",
    )


def _update_context_from_answer(state: SessionState, question_id: str, answer: str) -> None:
    """Derive structured context from raw answers."""
    ctx = state.interview_context
    ctx["user_request"] = state.user_request

    # Resolve short letters to full text
    resolved = resolve_answer(question_id, answer)
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


# ---- Phase: prd_gen ----------------------------------------------------- #
def _handle_prd_gen(state: SessionState, data: dict) -> dict:
    if data.get("success"):
        prd_path = data.get("prd_path", "docs/prd.md")
        # Validate prd_path to prevent path traversal
        try:
            prd_path = _validate_prd_path(prd_path)
        except ValueError:
            prd_path = "docs/prd.md"  # Fall back to safe default
        # Server-side PRD section validation
        prd_check = verifier.verify_prd_sections(prd_path)
        if not prd_check["valid"]:
            retry = int(state.interview_context.get("_prd_retries", "0")) + 1
            state.interview_context["_prd_retries"] = str(retry)
            if retry > 3:
                # Max retries — proceed with what we have
                state.prd_path = prd_path
                state.pipeline_phase = "prd_review"
                state.pipeline_step = "review"
                return make_response(
                    step="prd_review",
                    prompt=prompts.prd_review(),
                    expect="user_input",
                )
            missing = ", ".join(prd_check["missing_sections"])
            return make_response(
                step="generate_prd",
                prompt=f"PRD is missing required sections: {missing}\n\nRewrite the PRD to include all required sections.\n\n"
                + prompts.generate_prd(state.interview_context),
                expect="step_result",
            )
        state.prd_path = prd_path
        state.pipeline_phase = "prd_review"
        state.pipeline_step = "review"
        return make_response(
            step="prd_review",
            prompt=prompts.prd_review(),
            expect="user_input",
        )
    return make_response(
        step="generate_prd_retry",
        prompt="PRD generation failed. Try again.\n" + prompts.generate_prd(state.interview_context),
        expect="step_result",
    )


# ---- Phase: prd_review -------------------------------------------------- #
def _handle_prd_review(state: SessionState, data: dict, is_user_input: bool) -> dict:
    if not is_user_input:
        return make_response(step="prd_review", prompt=prompts.prd_review(), expect="user_input")

    answer = data.get("user_input", "").strip().lower()

    if answer in ("a", "approve"):
        state.prd_approved = True
        # Apply stage-based quality thresholds
        stage = state.interview_context.get("project_stage", "").lower()
        if "prototype" in stage:
            stage_key = "prototype"
        elif "production" in stage or "full" in stage:
            stage_key = "production"
        else:
            stage_key = "mvp"
        from harmony.orchestrator.state import thresholds_for_stage
        state.quality_thresholds = thresholds_for_stage(stage_key)
        state.pipeline_phase = "setup"
        state.pipeline_step = ""
        return _next_setup_step(state)

    if answer in ("d", "start over"):
        state.pipeline_phase = "interview"
        state.pipeline_step = ""
        state.interview_answers.clear()
        return _next_interview_question(state)

    if answer in ("b", "show"):
        return make_response(
            step="prd_review_show",
            prompt="Read docs/prd.md and show the FULL content to the user.\n\n"
            "After showing, call harmony_pipeline_respond with the user's next choice:\n"
            "  a) Approve  b) Show full PRD  c) Change something  d) Start over",
            expect="user_input",
        )

    if answer in ("c", "change"):
        return make_response(
            step="prd_review_change",
            prompt="Ask the user: What would you like to change in the PRD?\n\n"
            "Use the AskUserQuestion tool. After receiving their changes,\n"
            "apply the requested modifications to docs/prd.md, then call\n"
            "harmony_pipeline_respond with 'a' to re-show the review prompt.",
            expect="user_input",
        )

    # Unrecognized — re-prompt
    return make_response(
        step="prd_review",
        prompt=prompts.prd_review(),
        expect="user_input",
    )


