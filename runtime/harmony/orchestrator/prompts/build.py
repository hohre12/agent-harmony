"""Build phase prompts — task execution, fix."""

from __future__ import annotations


def build_task(task_id: str, task_title: str, tag: str = "", checkpoint_step: str = "", checkpoint: str = "", progress: str = "", subtasks: list | None = None, team_config: dict | None = None, thresholds: dict | None = None, project_language: str = "") -> str:
    tag_display = tag or "v1"
    resume_hint = ""
    if checkpoint_step:
        resume_hint = (
            f"\n**RESUME FROM CHECKPOINT**: This task was previously interrupted at: {checkpoint_step}\n"
            f"Previous progress: {checkpoint}\n"
            "Continue from where it left off — do NOT restart from scratch.\n\n"
        )
    progress_line = f"**[{progress}]** " if progress else ""

    subtask_block = ""
    if subtasks:
        lines = ["\n**Subtasks:**"]
        for st in subtasks:
            agent = st.get("assigned_agent") or st.get("agent", "")
            agent_tag = f" ({agent})" if agent else ""
            lines.append(f"  - [{st.get('id', '?')}] {st.get('title', '')}{agent_tag}")
            if st.get("description"):
                lines.append(f"    Description: {st['description']}")
            if st.get("test"):
                lines.append(f"    Acceptance: {st['test']}")
        subtask_block = "\n".join(lines) + "\n"

    # Team config block — code-enforced agent role assignments
    team_block = ""
    if team_config:
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
        team_block = "\n".join(lines) + "\n"

    # Accountability pressure block — agents perform better when they know
    # their output will be independently verified by a blind reviewer.
    accountability_block = _accountability_block(thresholds)

    lang_block = ""
    if project_language:
        lang_lower = project_language.lower()
        if "english" in lang_lower:
            lang_block = "\n**Project Language: English** — All code comments, variable names, commit messages, documentation, and UI text must be in English.\n"
        elif "same" not in lang_lower and "conversation" not in lang_lower:
            lang_block = f"\n**Project Language: {project_language}** — Code comments, documentation, and UI text should be in {project_language}.\n"

    return (
        f"{progress_line}Execute task {task_id}: \"{task_title}\"\n\n"
        f"{resume_hint}"
        f"{subtask_block}"
        f"{team_block}"
        f"{lang_block}\n"
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
        "Write code as if a stranger will judge it with no benefit of the doubt.\n"
        "---"
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


