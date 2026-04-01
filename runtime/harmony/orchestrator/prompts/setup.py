"""Setup phase prompts — project init, agents, refs, tasks, executor."""

from __future__ import annotations


_SETUP_STEPS = [
    ("project_init", "Run /project-init now.", "Project structure"),
    ("codebase_init", "Run /codebase-init now.", "Project structure"),
    ("generate_agents", "Run /generate-agents now.", "Agent team"),
    ("build_refs", "Run /build-refs now.", "Reference docs"),
    ("generate_tasks", "", "Task decomposition"),
    ("setup_team_executor", "", "Team executor"),
]
_SETUP_INDEX = {s[0]: (i, s) for i, s in enumerate(_SETUP_STEPS)}


def setup_step(step_name: str) -> str:
    idx, entry = _SETUP_INDEX.get(step_name, (0, (step_name, f"Run /{step_name} now.", step_name)))
    total = 5
    step_num = min(idx + 1, total)
    instruction, label = entry[1], entry[2]

    if step_name == "generate_tasks":
        return f"[Step {step_num}/{total}] {label}\n\n" + generate_tasks()
    if step_name == "setup_team_executor":
        return f"[Step {step_num}/{total}] {label}\n\n" + setup_team_executor()

    return (
        f"[Step {step_num}/{total}] {label}\n\n"
        f"{instruction}\n\n"
        "When complete, call harmony_pipeline_next with "
        f'{{"step":"{step_name}","success":true}}'
    )


def generate_tasks() -> str:
    return (
        "Read docs/prd.md and decompose the project into vertical-slice tasks.\n\n"
        "CRITICAL — Vertical Slice Rule:\n"
        "- Each task MUST be a complete FEATURE cutting through ALL layers\n"
        "- WRONG: 'Set up database schema', 'Build all API endpoints', 'Create all UI pages'\n"
        "- RIGHT: 'User Auth (DB schema + API + UI + tests)', 'Dashboard (DB + API + UI + tests)'\n"
        "- If a task only touches ONE layer, it is WRONG. Restructure it.\n\n"
        "Rules:\n"
        "- Each task should be independently implementable and testable\n"
        "- Order tasks by dependency (foundational first)\n"
        "- For each task, create 4-8 subtasks covering all layers needed\n"
        "- Read .claude/agents/*.md to assign the right agent to each subtask\n"
        "- Subtask title format: '{title} ({agent-name})'\n"
        "- Main task title format: '{title} [LEAD: {architect-agent-name}]'\n\n"
        "Return JSON via harmony_pipeline_next:\n"
        '{"step":"generate_tasks","success":true,"tasks":[\n'
        '  {"id":"1","title":"Task [LEAD: agent]","subtasks":[\n'
        '    {"id":"1.1","title":"Subtask (agent-name)","description":"...","test":"..."}\n'
        "  ]}\n"
        "]}"
    )


def setup_team_executor() -> str:
    return (
        "Read .claude/agents/*.md and classify agents by role:\n"
        "- main_architect: purple agent for system coordination\n"
        "- code_architect: other purple agent (or same as main)\n"
        "- db_agent: orange agent (null if none)\n"
        "- review_agent: red agent (or green, or main_architect)\n"
        "- e2e_agent: green agent for E2E testing (null if none)\n\n"
        "Then call harmony_generate_template with:\n"
        '- template_name: "team-executor"\n'
        "- config_json with: project_name, main_architect, code_architect, "
        "db_agent, review_agent, e2e_agent, agent_type_table, git_mode\n\n"
        "Write the returned content to .claude/skills/team-executor/SKILL.md\n\n"
        "When complete, call harmony_pipeline_next with:\n"
        '{"step":"setup_team_executor","success":true}'
    )
