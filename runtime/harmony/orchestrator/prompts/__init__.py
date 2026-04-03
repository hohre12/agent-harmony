"""Step-specific prompts for the harmony pipeline.

Split by domain to keep each file short and focused:
  interview.py  — interview questions, PRD generation/review
  setup.py      — project init, agent gen, build refs, task gen
  build.py      — task execution, fix issues
  quality.py    — quality gate, production audit
  security.py   — security review, hardening
  delivery.py   — verify, final check, summary, resume
"""

from harmony.orchestrator.prompts.interview import (
    interview_start,
    interview_question,
    generate_prd,
    prd_review,
    resolve_answer,
)
from harmony.orchestrator.prompts.setup import (
    setup_step,
    generate_tasks,
    setup_team_executor,
)
from harmony.orchestrator.prompts.build import (
    build_task,
    build_team_setup,
    build_team_execute,
    build_team_merge,
    fix_issues,
)
from harmony.orchestrator.prompts.quality import (
    quality_gate,
    production_audit,
)
from harmony.orchestrator.prompts.security import (
    harden_security_review,
    harden_fix_criticals,
)
from harmony.orchestrator.prompts.delivery import (
    verify_prd_compliance,
    verify_fix_gaps,
    final_check,
    delivery_summary,
    resume_prompt,
)
from harmony.orchestrator.prompts.design import (
    design_quality_audit,
    design_brief_requirements,
    DESIGN_CHECKLIST,
)

__all__ = [
    "interview_start", "interview_question", "generate_prd", "prd_review", "resolve_answer",
    "setup_step", "generate_tasks", "setup_team_executor",
    "build_task", "build_team_setup", "build_team_execute", "build_team_merge", "fix_issues",
    "quality_gate", "production_audit",
    "harden_security_review", "harden_fix_criticals",
    "verify_prd_compliance", "verify_fix_gaps",
    "final_check", "delivery_summary", "resume_prompt",
    "design_quality_audit", "design_brief_requirements", "DESIGN_CHECKLIST",
]
