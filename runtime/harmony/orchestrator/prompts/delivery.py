"""Delivery phase prompts — verify, final check, summary, resume."""

from __future__ import annotations


def verify_prd_compliance() -> str:
    return (
        "**CRITICAL: You MUST use the Agent tool to spawn a NEW agent for this verification.**\n"
        "Do NOT verify yourself — use a fresh agent with no build context.\n\n"
        "Call Agent with this prompt:\n\n"
        '  "You are an independent QA engineer verifying PRD compliance.\n'
        "  Read docs/prd.md Section 4 (Core Features). For EACH feature:\n"
        "  1. Search the codebase (use Grep/Glob) for its implementation\n"
        "  2. Classify: implemented / partial / missing\n"
        "  3. Cite specific files as evidence\n"
        '  Be strict — partial implementations should be flagged."\n\n'
        "After the Agent returns, call harmony_pipeline_next with:\n"
        '{"step":"verify_prd","auditor_id":"<agent-id>","gaps":[{"feature":"X","status":"partial","missing":"Y"}]}\n'
        'If all implemented: {"step":"verify_prd","auditor_id":"<agent-id>","gaps":[]}\n\n'
        "CRITICAL: auditor_id is REQUIRED. The pipeline will REJECT results without it."
    )


def verify_fix_gaps(gaps: list[dict]) -> str:
    gap_text = "\n".join(
        f"- {g.get('feature','?')}: {g.get('status','?')} — {g.get('missing','')}"
        for g in gaps
    )
    return (
        f"Fix these PRD compliance gaps:\n\n{gap_text}\n\n"
        "Implement the missing parts, then call harmony_pipeline_next with:\n"
        '{"step":"verify_fix","success":true}'
    )


def final_check() -> str:
    return (
        "Final integration check:\n"
        "1. Install dependencies (npm install / pip install)\n"
        "2. Full build verification\n"
        "3. Run all tests\n"
        "4. Smoke test if web app (start server, check main route)\n\n"
        "Call harmony_pipeline_next with:\n"
        '{"step":"final_check","success":true/false,"details":"..."}'
    )


def delivery_summary(stats: dict) -> str:
    return (
        "Show the user the completion report:\n\n"
        f"Project: {stats.get('project_name', '')}\n"
        f"Tasks completed: {stats.get('completed', 0)}/{stats.get('total', 0)}\n"
        f"Tests passing: {stats.get('tests', '?')}\n\n"
        "---\n"
        "Pipeline artifacts:\n"
        "  [KEEP]     docs/prd.md, docs/refs/, docs/tasks/ — project documentation\n"
        "  [KEEP]     .claude/agents/ — agent definitions for future sessions\n"
        "  [REVIEW]   .claude/settings.local.json — has bypassPermissions enabled\n"
        "  [OPTIONAL] .harmony/ — pipeline state, safe to delete after completion\n"
        "---\n\n"
        "Next steps:\n"
        "  a) Deploy\n"
        "  b) Add features\n"
        "  c) Review code\n"
        "  d) Clean up pipeline state (.harmony/)\n"
        "  e) Done\n"
    )


def resume_prompt(pipeline_phase: str, pipeline_step: str, project_name: str) -> str:
    return (
        f"A previous session was found:\n"
        f"  Project: {project_name}\n"
        f"  Phase: {pipeline_phase}\n"
        f"  Step: {pipeline_step}\n\n"
        "You MUST call the AskUserQuestion tool to present these choices:\n"
        "  a) Resume from where I left off\n"
        "  b) Start over\n"
        "  c) Show detailed status\n"
        "  → Recommended: a) Resume\n\n"
        "Do NOT just print the choices as text. Use the AskUserQuestion tool.\n"
        "After the user responds, interpret their answer and call harmony_pipeline_respond with the letter (a/b/c)."
    )
