"""Build phase prompts — task execution, fix."""

from __future__ import annotations


def build_task(task_id: str, task_title: str, tag: str = "", checkpoint_step: str = "", checkpoint: str = "", progress: str = "", subtasks: list | None = None, team_config: dict | None = None, thresholds: dict | None = None, project_language: str = "", frontend_framework: str = "") -> str:
    tag_display = tag or "v1"
    resume_hint = ""
    if checkpoint_step:
        resume_hint = (
            f"\n**RESUME FROM CHECKPOINT**: This task was previously interrupted at: {checkpoint_step}\n"
            f"Previous progress: {checkpoint}\n"
            "Continue from where it left off — do NOT restart from scratch.\n\n"
        )
    progress_line = f"**[{progress}]** " if progress else ""

    subtask_block = _subtask_block(subtasks)
    team_block = _team_block(team_config)
    accountability_block = _accountability_block(thresholds)
    lf_block = _lang_framework_block(project_language, frontend_framework)

    return (
        f"{progress_line}Execute task {task_id}: \"{task_title}\"\n\n"
        f"{resume_hint}"
        f"{subtask_block}"
        f"{team_block}"
        f"{lf_block}\n"
        f"{accountability_block}\n"
        f"**Execution**: Run `/agent-harmony:team-executor {tag_display}:{task_id}`\n\n"
        "After completing the task, call harmony_pipeline_next with:\n"
        f'{{"step":"build_task","task_id":"{task_id}","task_title":"{task_title}","success":true}}\n\n'
        "If execution fails, report the failure:\n"
        f'{{"step":"build_task","task_id":"{task_id}","success":false,"issues":[...]}}'
    )


def _accountability_block(thresholds: dict | None = None) -> str:
    """Build the ACCOUNTABILITY warning block with quality thresholds."""
    # Format thresholds into readable lines
    threshold_lines = ""
    if thresholds:
        metric_labels = {
            "build": "Build passes",
            "tests": "All tests pass",
            "lint": "Zero lint errors",
            "test_coverage": "Test coverage >= {v}%",
            "max_file_lines": "No file exceeds {v} lines",
            "max_function_lines": "No function exceeds {v} lines",
            "security_critical": "Zero critical security issues",
            "a11y_critical": "Zero critical accessibility issues",
            "design_token_violations": "Design token violations <= {v}",
        }
        lines = []
        for key, val in thresholds.items():
            label = metric_labels.get(key)
            if label:
                lines.append(f"  - {label.format(v=val)}")
            else:
                lines.append(f"  - {key}: {val}")
        threshold_lines = "\n".join(lines)

    return (
        "---\n"
        "**ACCOUNTABILITY NOTICE**\n\n"
        "Your output will be independently verified by a DIFFERENT agent who has\n"
        "NO context about your process, reasoning, or intentions. The verifier\n"
        "sees ONLY your code, tests, and files — nothing else.\n\n"
        "After verification, a FRESH agent acting as a senior engineer will audit\n"
        "your code from scratch. This auditor has never seen your work before and\n"
        "will judge it purely on what is written.\n\n"
        "**Metrics that will be measured against your output:**\n"
        f"{threshold_lines}\n\n"
        "If verification or audit fails, you will be sent back to fix the issues.\n"
        "There is NO round limit and NO auto-pass — the loop continues until\n"
        "every threshold is met and the auditor is satisfied.\n\n"
        "The auditor will specifically check for:\n"
        "  - Logic bugs (wrong conditions, off-by-one, null access, race conditions)\n"
        "  - Magic numbers/strings (must be named constants)\n"
        "  - Duplicated code (must extract shared functions/components)\n"
        "  - Unclear naming, dead code, god files/functions\n"
        "  - N+1 queries, unbounded fetches, missing memoization\n"
        "  - Tests with meaningful assertions covering edge cases and error paths\n\n"
        "Write code as if a stranger will judge it with no benefit of the doubt.\n"
        "---"
    )


def _subtask_block(subtasks: list | None) -> str:
    if not subtasks:
        return ""
    lines = ["\n**Subtasks:**"]
    for st in subtasks:
        agent = st.get("assigned_agent") or st.get("agent", "")
        agent_tag = f" ({agent})" if agent else ""
        lines.append(f"  - [{st.get('id', '?')}] {st.get('title', '')}{agent_tag}")
        if st.get("description"):
            lines.append(f"    Description: {st['description']}")
        if st.get("test"):
            lines.append(f"    Acceptance: {st['test']}")
    return "\n".join(lines) + "\n"


def _team_block(team_config: dict | None) -> str:
    if not team_config:
        return ""
    main_arch = team_config.get("main_architect", "")
    review = team_config.get("review_agent", "")
    db = team_config.get("db_agent", "")
    e2e = team_config.get("e2e_agent", "")
    lines = ["\n**Team Roles (assigned by pipeline — use these exact agent names):**"]
    if main_arch:
        lines.append(f"  - Team Lead / Design: `{main_arch}`")
    if review:
        lines.append(f"  - Code Review: `{review}`")
    if db:
        lines.append(f"  - Database: `{db}`")
    if e2e:
        lines.append(f"  - E2E Testing: `{e2e}`")
    agent_table = team_config.get("agent_type_table", {})
    if isinstance(agent_table, dict):
        for agent_name, role in agent_table.items():
            if agent_name not in (main_arch, review, db, e2e):
                role_desc = role if isinstance(role, str) else role.get("role", "")
                lines.append(f"  - {role_desc}: `{agent_name}`")
    return "\n".join(lines) + "\n"


def _lang_framework_block(project_language: str = "", frontend_framework: str = "") -> str:
    parts = []
    if frontend_framework and "skip" not in frontend_framework.lower() and "specified" not in frontend_framework.lower():
        parts.append(f"\n**Frontend Framework: {frontend_framework}** — All frontend code MUST use this framework. Do NOT use Vanilla HTML/CSS/JS unless this explicitly says so.\n")
    if project_language:
        lang_lower = project_language.lower()
        if "english" in lang_lower:
            parts.append("\n**Project Language: English** — All code comments, variable names, commit messages, documentation, and UI text must be in English.\n")
        elif "same" not in lang_lower and "conversation" not in lang_lower:
            parts.append(f"\n**Project Language: {project_language}** — Code comments, documentation, and UI text should be in {project_language}.\n")
    return "".join(parts)


_ORCHESTRATOR_NOTICE = (
    "---\n"
    "**ORCHESTRATOR ROLE — READ CAREFULLY**\n\n"
    "You are the ORCHESTRATOR. You coordinate specialist agents.\n"
    "You do NOT write code, design docs, or tests yourself.\n\n"
    "**Allowed tools:** TeamCreate, Agent, SendMessage, AskUserQuestion, Read, Glob, Grep, Bash (git only)\n"
    "**Forbidden for project files:** Edit, Write, NotebookEdit\n\n"
    "If you catch yourself writing code or design docs directly: STOP.\n"
    "Spawn the assigned specialist agent and let THEM do it.\n"
    "Your job is to delegate, monitor, and verify — not to implement.\n"
    "---\n"
)

_COLLABORATION_PROTOCOL = (
    "\n**Autonomous Collaboration Protocol** (include when spawning each agent):\n"
    "```\n"
    "1. Proactive Communication: Ask related agents via SendMessage when stuck\n"
    "2. Dependency Awareness: Check prerequisites with relevant agents\n"
    "3. Completion Notification: Notify dependent agents when done\n"
    "4. Design First: Agree on interfaces before implementation\n"
    "5. Conflict Avoidance: Coordinate when modifying same files\n"
    "6. Tags: [ASK] question, [NOTIFY] done, [AGREE] consensus, [REVIEW] review, [ESCALATE] leader\n"
    "```\n"
)


def build_team_setup(
    task_id: str, task_title: str, tag: str = "", progress: str = "",
    subtasks: list | None = None, team_config: dict | None = None,
    thresholds: dict | None = None, project_language: str = "",
    frontend_framework: str = "",
) -> str:
    """Phase 1/3: Team creation and design document via architect agents."""
    tag_display = tag or "v1"
    progress_line = f"**[{progress}]** " if progress else ""

    main_arch = (team_config or {}).get("main_architect", "architect-agent")
    code_arch = (team_config or {}).get("code_architect", main_arch)
    db_agent = (team_config or {}).get("db_agent", "")

    design_agents = f"`{main_arch}`"
    if code_arch and code_arch != main_arch:
        design_agents += f", `{code_arch}`"
    if db_agent:
        # Check if any subtask is DB-related
        has_db = any("db" in (st.get("assigned_agent", "") + st.get("title", "")).lower()
                      for st in (subtasks or []))
        if has_db:
            design_agents += f", `{db_agent}`"

    return (
        f"{progress_line}**Phase 1/3: Team Setup** — Task {task_id}: \"{task_title}\"\n\n"
        f"{_ORCHESTRATOR_NOTICE}\n"
        f"{_subtask_block(subtasks)}"
        f"{_team_block(team_config)}"
        f"{_lang_framework_block(project_language, frontend_framework)}\n"
        f"**Steps:**\n\n"
        f"1. Run `whoami` to get your username\n"
        f"2. Create feature branch: `feature/{tag_display}-{task_id}_{{task-name}}/{{user}}`\n"
        f"3. `TeamCreate` with name `team-{tag_display}-{task_id}`\n"
        f"4. Spawn design agents ({design_agents}) to write the design document:\n"
        f"   - Path: `docs/tasks/{tag_display}-{task_id}-{{task-name}}-plan.md`\n"
        f"   - Required: Overview, Implementation File List, Build Sequence + domain sections\n"
        f"   - Minimum 80 lines with code blocks\n"
        f"{_COLLABORATION_PROTOCOL}"
        f"5. Wait for design agents to complete\n"
        f"6. Review and approve the design document\n"
        f"7. Send `shutdown_request` to design agents\n\n"
        f"{_accountability_block(thresholds)}\n\n"
        f"After completing, call harmony_pipeline_next with:\n"
        f'{{"step":"build_team_setup","task_id":"{task_id}","task_title":"{task_title}",'
        f'"team_name":"team-{tag_display}-{task_id}","success":true}}\n\n'
        f"If setup fails:\n"
        f'{{"step":"build_team_setup","task_id":"{task_id}","success":false,"issues":[...]}}'
    )


def build_team_execute(
    task_id: str, task_title: str, tag: str = "", progress: str = "",
    subtasks: list | None = None, team_config: dict | None = None,
    thresholds: dict | None = None, project_language: str = "",
    frontend_framework: str = "",
) -> str:
    """Phase 2/3: Spawn implementation agents in worktrees."""
    tag_display = tag or "v1"
    progress_line = f"**[{progress}]** " if progress else ""

    review_agent = (team_config or {}).get("review_agent", "review-agent")

    worktree_lines = []
    agent_lines = []
    for st in (subtasks or []):
        st_id = st.get("id", "?")
        agent = st.get("assigned_agent") or st.get("agent", "unknown")
        worktree_lines.append(
            f"   git worktree add .worktrees/wt-{st_id} "
            f"-b feature/{tag_display}-{task_id}_{{task-name}}/wt-{st_id}/{{user}} "
            f"feature/{tag_display}-{task_id}_{{task-name}}/{{user}}"
        )
        desc = st.get("description", st.get("title", ""))
        agent_lines.append(f"   - Subtask {st_id}: `{agent}` in `.worktrees/wt-{st_id}` — {desc}")

    worktree_block = "\n".join(worktree_lines) if worktree_lines else "   (create worktrees per subtask)"
    agent_block = "\n".join(agent_lines) if agent_lines else "   (spawn agents per subtask)"

    return (
        f"{progress_line}**Phase 2/3: Implementation** — Task {task_id}: \"{task_title}\"\n\n"
        f"{_ORCHESTRATOR_NOTICE}\n"
        f"Design document is approved. Now spawn implementation agents.\n\n"
        f"{_lang_framework_block(project_language, frontend_framework)}\n"
        f"**Steps:**\n\n"
        f"1. Ensure `.worktrees/` is in `.gitignore`\n"
        f"2. Create worktrees for each subtask:\n"
        f"```bash\n{worktree_block}\n```\n\n"
        f"3. Spawn implementation agents **CONCURRENTLY** — one per subtask:\n"
        f"{agent_block}\n\n"
        f"   Each agent receives:\n"
        f"   - The design document\n"
        f"   - Their subtask details and acceptance criteria\n"
        f"   - Their worktree path (they work ONLY in their worktree)\n"
        f"   - The self-review checklist (11 items) and accountability notice\n"
        f"{_COLLABORATION_PROTOCOL}\n"
        f"4. Also spawn `{review_agent}` to prepare for code review\n"
        f"5. Wait for ALL implementation agents to complete\n\n"
        f"**CRITICAL**: Each agent MUST work in their assigned worktree.\n"
        f"Do NOT write code yourself. Do NOT implement in the main branch.\n\n"
        f"After all agents complete, call harmony_pipeline_next with:\n"
        f'{{"step":"build_team_execute","task_id":"{task_id}","task_title":"{task_title}",'
        f'"success":true}}\n\n'
        f"If execution fails:\n"
        f'{{"step":"build_team_execute","task_id":"{task_id}","success":false,"issues":[...]}}'
    )


def build_team_merge(
    task_id: str, task_title: str, tag: str = "",
    subtasks: list | None = None, team_config: dict | None = None,
) -> str:
    """Phase 3/3: Review, merge worktrees, commit."""
    tag_display = tag or "v1"

    review_agent = (team_config or {}).get("review_agent", "review-agent")
    e2e_agent = (team_config or {}).get("e2e_agent", "")

    merge_lines = []
    for st in (subtasks or []):
        st_id = st.get("id", "?")
        merge_lines.append(
            f"   git merge feature/{tag_display}-{task_id}_{{task-name}}/wt-{st_id}/{{user}}"
        )
    merge_block = "\n".join(merge_lines) if merge_lines else "   (merge each worktree branch)"

    cleanup_lines = []
    for st in (subtasks or []):
        st_id = st.get("id", "?")
        cleanup_lines.append(f"   git worktree remove .worktrees/wt-{st_id}")
    cleanup_block = "\n".join(cleanup_lines) if cleanup_lines else "   (remove worktrees)"

    e2e_step = ""
    if e2e_agent:
        e2e_step = (
            f"4. Spawn `{e2e_agent}` for E2E testing\n"
            f"5. "
        )
    else:
        e2e_step = "4. "

    return (
        f"**Phase 3/3: Review & Merge** — Task {task_id}: \"{task_title}\"\n\n"
        f"{_ORCHESTRATOR_NOTICE}\n"
        f"All implementation agents have completed. Now review and merge.\n\n"
        f"**Steps:**\n\n"
        f"1. `{review_agent}` reviews ALL code across worktrees\n"
        f"   - Use the quality criteria (bugs, code quality, architecture, tests)\n"
        f"   - Report MUST-FIX and SHOULD-FIX issues\n"
        f"2. If MUST-FIX issues: route to responsible agents for fixes\n"
        f"   - Re-review until ALL MUST-FIX issues are resolved\n"
        f"3. Merge each worktree to the feature branch:\n"
        f"```bash\n"
        f"   git checkout feature/{tag_display}-{task_id}_{{task-name}}/{{user}}\n"
        f"{merge_block}\n"
        f"```\n"
        f"   On conflict: spawn responsible agent to resolve\n\n"
        f"{e2e_step}Clean up worktrees:\n"
        f"```bash\n{cleanup_block}\n```\n\n"
        f"{'6' if e2e_agent else '5'}. Final commit via `/commit`\n"
        f"{'7' if e2e_agent else '6'}. `git push -u origin feature/{tag_display}-{task_id}_{{task-name}}/{{user}}`\n"
        f"{'8' if e2e_agent else '7'}. `TeamDelete` to clean up the team\n\n"
        f"After completing, call harmony_pipeline_next with:\n"
        f'{{"step":"build_team_merge","task_id":"{task_id}","task_title":"{task_title}","success":true}}\n\n'
        f"If merge fails:\n"
        f'{{"step":"build_team_merge","task_id":"{task_id}","success":false,"issues":[...]}}'
    )


def fix_issues(task_id: str, issues: list[dict]) -> str:
    issue_text = "\n".join(
        f"- [{i.get('severity','?')}] {i.get('file','?')}: {i.get('what','?')}"
        for i in issues
    )
    return (
        f"Fix the following issues for task {task_id}:\n\n"
        f"{issue_text}\n\n"
        "After fixing, call harmony_pipeline_next with:\n"
        f'{{"step":"fix","task_id":"{task_id}","success":true/false}}'
    )


