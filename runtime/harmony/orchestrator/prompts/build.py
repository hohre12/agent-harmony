"""Build phase prompts — task execution, fix."""

from __future__ import annotations


def build_task(task_id: str, task_title: str, tag: str = "", checkpoint_step: str = "", checkpoint: str = "", progress: str = "", subtasks: list | None = None, team_config: dict | None = None) -> str:
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

    return (
        f"{progress_line}Execute task {task_id}: \"{task_title}\"\n\n"
        f"{resume_hint}"
        f"{subtask_block}"
        f"{team_block}\n"
        f"**Execution**: Run `/agent-harmony:team-executor {tag_display}:{task_id}`\n\n"
        "After completing the task, call harmony_pipeline_next with:\n"
        f'{{"step":"build_task","task_id":"{task_id}","task_title":"{task_title}","success":true}}\n\n'
        "If execution fails, report the failure:\n"
        f'{{"step":"build_task","task_id":"{task_id}","success":false,"issues":[...]}}'
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


