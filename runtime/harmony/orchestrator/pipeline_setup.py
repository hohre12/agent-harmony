"""Pipeline setup phase — project init, agent generation, task decomposition."""

from __future__ import annotations

import json
import os
from pathlib import Path

from harmony.orchestrator.state import SessionState, TaskState, SubtaskState
from harmony.orchestrator import prompts
from harmony.orchestrator import verifier
from harmony.orchestrator import verifier_frontend
from harmony.orchestrator.utils import make_response


_SETTINGS_LOCAL = {
    "env": {
        "CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS": "1",
    },
    "permissions": {
        "allow": [
            "Bash(*)",
            "Edit(*)",
            "Read(*)",
            "Write(*)",
            "Glob(*)",
            "Grep(*)",
            "WebFetch(*)",
            "WebSearch",
            "mcp__harmony__*",
            "mcp__context7__*",
            "mcp__stitch__*",
            "mcp__github__*",
            "mcp__supabase__*",
            "mcp__notion__*",
        ],
        "defaultMode": "bypassPermissions",
    },
    "teammateMode": "auto",
}


def ensure_settings_local() -> None:
    """Ensure .claude/settings.local.json exists with required permissions.

    Merges into existing file if present (preserves user additions).
    Creates .claude/ directory if missing.
    """
    path = Path(".claude/settings.local.json")
    path.parent.mkdir(parents=True, exist_ok=True)

    existing: dict = {}
    if path.exists():
        try:
            existing = json.loads(path.read_text())
        except (json.JSONDecodeError, OSError):
            existing = {}

    # Merge: ensure our keys are present without removing user additions
    merged = {**existing}

    # env
    merged_env = {**merged.get("env", {}), **_SETTINGS_LOCAL["env"]}
    merged["env"] = merged_env

    # permissions.allow — union of existing + required
    merged_perms = merged.get("permissions", {})
    existing_allow = set(merged_perms.get("allow", []))
    required_allow = set(_SETTINGS_LOCAL["permissions"]["allow"])
    merged_perms["allow"] = sorted(existing_allow | required_allow)
    merged_perms["defaultMode"] = "bypassPermissions"
    merged["permissions"] = merged_perms

    # teammateMode
    merged["teammateMode"] = "auto"

    path.write_text(json.dumps(merged, indent=2, ensure_ascii=False) + "\n")


_SETUP_SEQUENCE = [
    "design_direction", "project_init", "generate_agents", "build_refs",
    "generate_tasks", "setup_team_executor",
]


def _validate_and_store_tasks(state: SessionState, tasks_data: list) -> dict | None:
    """Validate task data and store in state. Returns error response or None on success."""
    if not isinstance(tasks_data, list) or not tasks_data:
        return make_response(
            step="generate_tasks",
            prompt="Task generation returned no tasks. Try again.\n\n" + prompts.generate_tasks(),
            expect="step_result",
        )
    try:
        for t in tasks_data:
            if not isinstance(t, dict) or "id" not in t or "title" not in t:
                raise ValueError(f"Invalid task format: {t}")
            subtasks = [
                SubtaskState(
                    id=str(st.get("id", "")),
                    title=st.get("title", ""),
                    description=st.get("description", ""),
                    test=st.get("test", ""),
                    assigned_agent=st.get("agent", ""),
                )
                for st in t.get("subtasks", [])
            ]
            state.tasks.append(TaskState(
                id=str(t["id"]),
                title=t["title"],
                assigned_agent=t.get("agent", ""),
                subtasks=subtasks,
            ))
    except (TypeError, ValueError):
        state.tasks.clear()
        return make_response(
            step="generate_tasks",
            prompt="Task format invalid. Each task needs 'id' and 'title'.\n\n" + prompts.generate_tasks(),
            expect="step_result",
        )
    # Server-side vertical-slice validation
    task_check = verifier.verify_task_structure(tasks_data)
    if not task_check["valid"]:
        issue_text = "; ".join(task_check["issues"][:5])
        state.tasks.clear()
        return make_response(
            step="generate_tasks",
            prompt=f"Task structure validation FAILED:\n{issue_text}\n\nRestructure as vertical slices.\n\n" + prompts.generate_tasks(),
            expect="step_result",
        )
    return None


def _handle_setup(state: SessionState, data: dict) -> dict:
    # Handle task generation escalation response
    if data.get("user_input") and state.pipeline_step == "task_escalate":
        answer = data.get("user_input", "").strip().lower()
        if answer in ("b", "skip"):
            # Skip validation and proceed with whatever tasks exist
            state.setup_progress["generate_tasks"] = "done"
            return _next_setup_step(state)
        if answer in ("c", "abort"):
            state.pipeline_phase = "done"
            return make_response(step="done", prompt="Pipeline aborted by user.", expect="none")
        # a (try again) — reset retries and re-run
        state.interview_context["_task_retries"] = "0"
        return make_response(
            step="generate_tasks",
            prompt=prompts.generate_tasks(),
            expect="step_result",
        )

    step = data.get("step", "")

    # generate_tasks returns tasks in the result — validate and store
    if step == "generate_tasks" and data.get("success"):
        tasks_data = data.get("tasks", [])
        error = _validate_and_store_tasks(state, tasks_data)
        if error is not None:
            retry = int(state.interview_context.get("_task_retries", "0")) + 1
            state.interview_context["_task_retries"] = str(retry)
            if retry > 3:
                # Escalate to user
                return make_response(
                    step="task_escalate",
                    prompt="Task generation failed 3 times. Vertical-slice validation keeps failing.\n\n"
                           "You MUST call the AskUserQuestion tool:\n"
                           "  a) Try again with different approach\n"
                           "  b) Skip validation and proceed\n"
                           "  c) Abort\n",
                    expect="user_input",
                )
            return error
        state.total_tasks = len(state.tasks)
        state.setup_progress[step] = "done"
        return _next_setup_step(state)

    if step == "design_direction" and data.get("success"):
        # Verify design brief content, not just existence
        brief_check = verifier_frontend.verify_design_brief_content("docs/refs/design-brief.md")
        if not brief_check.get("valid"):
            missing = ", ".join(brief_check.get("missing_sections", []))
            return make_response(
                step="design_direction",
                prompt=(
                    f"Design brief incomplete — missing: {missing}\n"
                    "docs/refs/design-brief.md must include sections for:\n"
                    "- Color palette (with hex values and CSS custom properties)\n"
                    "- Typography (font families, sizes, weights)\n"
                    "- Spacing scale (consistent spacing tokens)\n"
                    "- Component style (button, input, card patterns)\n\n"
                    "After creating/updating it, call harmony_pipeline_next with:\n"
                    '{"step":"design_direction","success":true}'
                ),
                expect="step_result",
            )
        state.setup_progress[step] = "done"
        return _next_setup_step(state)

    # setup_team_executor returns team_config — store in state
    if step == "setup_team_executor" and data.get("success"):
        team_cfg = data.get("team_config", {})
        if isinstance(team_cfg, dict) and team_cfg:
            state.team_config = team_cfg
        state.setup_progress[step] = "done"
        return _next_setup_step(state)

    if step and data.get("success"):
        state.setup_progress[step] = "done"
    return _next_setup_step(state)


def _next_setup_step(state: SessionState) -> dict:
    from harmony.orchestrator.pipeline_build import _next_build_task

    # Ensure settings.local.json exists before any setup step runs
    try:
        ensure_settings_local()
    except OSError:
        pass  # Non-fatal — target dir may not be writable in tests

    for step_name in _SETUP_SEQUENCE:
        if state.setup_progress.get(step_name) != "done":
            state.pipeline_step = step_name
            actual_step = step_name

            # Skip design_direction for non-frontend or "handle separately"
            if step_name == "design_direction":
                design_choice = state.interview_context.get("design", "")
                # Check multiple interview fields for frontend indicators
                tech = state.interview_context.get("tech_stack", "").lower()
                request = state.interview_context.get("user_request", "").lower()
                features = state.interview_context.get("features", "").lower()
                all_context = f"{tech} {request} {features}"
                frontend_keywords = (
                    "react", "next", "vue", "angular", "svelte", "frontend",
                    "web app", "webapp", "landing", "dashboard", "tailwind",
                    "css", "ui", "website", "page", "remix", "nuxt", "astro",
                    "프론트엔드", "대시보드", "웹", "화면", "디자인", "페이지",
                )
                has_frontend = any(kw in all_context for kw in frontend_keywords)
                if not has_frontend or "separately" in design_choice.lower() or "functional" in design_choice.lower():
                    state.setup_progress[step_name] = "done"
                    continue
                # Frontend project — run design direction step
                return make_response(
                    step="design_direction",
                    prompt=(
                        "Establish design direction for the frontend.\n\n"
                        "If the `frontend-design` skill is available, run it:\n"
                        "  /frontend-design:frontend-design\n\n"
                        "If not available, create a design brief manually:\n"
                        "1. Read the user's design preference from interview context\n"
                        "2. Define: color palette, typography, spacing scale, component style\n"
                        "3. Write to docs/refs/design-brief.md\n\n"
                        "After completing, call harmony_pipeline_next with:\n"
                        '{"step":"design_direction","success":true}'
                    ),
                    expect="step_result",
                )

            if step_name == "project_init" and state.interview_context.get("has_existing_code"):
                actual_step = "codebase_init"
            return make_response(
                step=actual_step,
                prompt=prompts.setup_step(actual_step),
                expect="step_result",
            )

    # All setup done -> move to build
    state.pipeline_phase = "build"
    state.pipeline_step = "executing"
    return _next_build_task(state)
