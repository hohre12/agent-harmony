"""Build phase prompts — task execution, fix, escalation."""

from __future__ import annotations


def build_task(task_id: str, task_title: str, tag: str = "", checkpoint_step: str = "", checkpoint: str = "", progress: str = "") -> str:
    tag_display = tag or "v1"
    resume_hint = ""
    if checkpoint_step:
        resume_hint = (
            f"\n**RESUME FROM CHECKPOINT**: This task was previously interrupted at: {checkpoint_step}\n"
            f"Previous progress: {checkpoint}\n"
            "Continue from where it left off — do NOT restart from scratch.\n\n"
        )
    progress_line = f"**[{progress}]** " if progress else ""
    return (
        f"{progress_line}Execute task {task_id}: \"{task_title}\"\n\n"
        f"{resume_hint}"
        f"Run: /team-executor {tag_display}:{task_id}\n\n"
        "After team-executor completes, call harmony_pipeline_next with:\n"
        f'{{"step":"build_task","task_id":"{task_id}","task_title":"{task_title}","success":true}}\n\n'
        "If team-executor fails, report the failure:\n"
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


def escalation(task_title: str, issues: list[dict], scores: dict | None = None) -> str:
    issue_text = "\n".join(f"- {i.get('what', '?')}" for i in issues[:5])
    score_text = ""
    if scores:
        score_text = "\nQuality scores:\n" + "\n".join(
            f"  {k}: {v}" for k, v in scores.items()
        ) + "\n"
    return (
        f'Task "{task_title}" is not passing quality checks.\n\n'
        f"Issues:\n{issue_text}\n"
        f"{score_text}\n"
        "You MUST call the AskUserQuestion tool to present these choices:\n"
        "  a) Show details — I'll fix manually\n"
        "  b) Skip this task\n"
        "  c) Try a different approach\n"
        "  d) Abort\n"
        "  → Recommended: c)\n\n"
        "Interpret their answer and call harmony_pipeline_respond with the letter (a/b/c/d)."
    )
