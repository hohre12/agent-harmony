"""Interview and PRD prompts."""

from __future__ import annotations


_RESPOND_HINT = (
    "\n\nUse AskUserQuestion to present the choices. "
    "Interpret the user's answer (even if natural language) and call "
    "harmony_pipeline_respond with the LETTER only (a, b, c, etc.). "
    "If the user gives a free-text answer, pass their full text."
)


# ====================================================================== #
#  Interview start
# ====================================================================== #


def interview_start(user_request: str) -> str:
    if user_request:
        return (
            f'The user wants to build: "{user_request}"\n\n'
            "First, check existing context:\n"
            "1. Does docs/prd.md exist? If yes, tell the user and call harmony_pipeline_next "
            'with {"step":"context_check","has_prd":true}\n'
            "2. Are there any .md design/spec documents in the project root (e.g., *-design.md, "
            "*-spec.md, architecture.md)? If yes, tell the user which documents you found and "
            'call harmony_pipeline_next with {"step":"context_check","has_docs":true,"doc_paths":["file1.md","file2.md"]}\n'
            "3. Is this an existing project with code (package.json, pyproject.toml, etc.)? "
            'If yes, call harmony_pipeline_next with {"step":"context_check","has_code":true}\n'
            '4. Fresh start: call harmony_pipeline_next with {"step":"context_check","fresh":true}\n'
        )
    return (
        "Ask the user: What do you want to build?\n\n"
        "Let them describe freely. When they respond, call harmony_pipeline_respond "
        "with their answer."
    )


# ====================================================================== #
#  Interview questions
# ====================================================================== #


def interview_question(question_id: str, context: dict) -> str:
    generators = {
        "target_users": _q_target_users,
        "core_problem": _q_core_problem,
        "features": _q_features,
        "tech_stack": _q_tech_stack,
        "project_stage": _q_project_stage,
        "design": _q_design,
        "auth": _q_auth,
        "monetization": _q_monetization,
        "deployment": _q_deployment,
    }
    gen = generators.get(question_id)
    if gen is None:
        return f"Unknown question: {question_id}"
    return gen(context)


def _q_target_users(ctx: dict) -> str:
    return (
        "Ask the user:\n\n"
        "Who will use this?\n"
        "  a) Developers / technical users\n"
        "  b) General consumers (non-technical)\n"
        "  c) Internal team / company employees\n"
        "  d) Enterprise clients (B2B)\n"
        "  e) Myself only (personal tool)\n"
        "  f) Other — describe your users\n\n"
        f"  → Recommended: based on \"{ctx.get('user_request', '')}\", suggest the best fit."
        + _RESPOND_HINT
    )


def _q_core_problem(ctx: dict) -> str:
    return (
        "Ask the user:\n\n"
        "What problem does this solve?\n"
        "  a) Manual repetitive work that should be automated\n"
        "  b) Existing tools are too expensive\n"
        "  c) Existing tools are too complex / bad UX\n"
        "  d) No good solution exists yet\n"
        "  e) Internal process that needs systematizing\n"
        "  f) Other — describe the problem\n\n"
        "  → Recommend based on context."
        + _RESPOND_HINT
    )


def _q_features(ctx: dict) -> str:
    context_summary = ""
    if ctx.get("user_request"):
        context_summary += f"Project: {ctx['user_request']}\n"
    if ctx.get("target_users"):
        context_summary += f"Users: {ctx['target_users']}\n"
    if ctx.get("core_problem"):
        context_summary += f"Problem: {ctx['core_problem']}\n"
    return (
        f"Context so far:\n{context_summary}\n"
        "Based on this, suggest 5-7 features:\n\n"
        "Present as:\n"
        "  a) ✓ Feature 1 — description\n"
        "  b) ✓ Feature 2 — description\n"
        "  c) Feature 3 — description\n"
        "  d) Feature 4 — description\n"
        "  e) Add your own\n\n"
        "  ✓ = Recommended. User can pick multiple: 'a, b, c' or add custom."
        + _RESPOND_HINT
    )


def _q_tech_stack(ctx: dict) -> str:
    return (
        "Ask the user:\n\n"
        "What tech stack should we use?\n"
        "  a) Next.js + TypeScript + Prisma + PostgreSQL\n"
        "  b) React + TypeScript + Node.js + Express\n"
        "  c) Python + FastAPI + PostgreSQL\n"
        "  d) React Native + Expo + TypeScript\n"
        "  e) Python + Click/Typer (CLI)\n"
        "  f) Other — specify\n\n"
        "  → Recommend based on project type and features."
        + _RESPOND_HINT
    )


def _q_project_stage(ctx: dict) -> str:
    return (
        "Ask the user:\n\n"
        "What level of completeness?\n"
        "  a) Prototype — prove the idea works\n"
        "  b) MVP — first usable version\n"
        "  c) Production — full features, ready to launch\n"
        "  d) Other\n\n"
        "  → Recommended: b) MVP — launch, get feedback, iterate."
        + _RESPOND_HINT
    )


def _q_design(ctx: dict) -> str:
    return (
        "Ask the user:\n\n"
        "How should the frontend look?\n"
        "  a) Clean & minimal — shadcn/ui style\n"
        "  b) Bold & creative — custom design\n"
        "  c) Match a reference — I have designs\n"
        "  d) I'll handle design separately\n"
        "  e) Other\n\n"
        "  → Recommended: a) Clean & minimal — fastest with consistent quality."
        + _RESPOND_HINT
    )


def _q_auth(ctx: dict) -> str:
    return (
        "Ask the user:\n\n"
        "How should users log in?\n"
        "  a) Email + password\n"
        "  b) Social login only (Google, GitHub)\n"
        "  c) Email + social login (both)\n"
        "  d) Magic link (passwordless)\n"
        "  e) No authentication needed\n"
        "  f) Other\n\n"
        "  → Recommended: c) Email + social — widest coverage."
        + _RESPOND_HINT
    )


def _q_monetization(ctx: dict) -> str:
    return (
        "Ask the user:\n\n"
        "How will this make money?\n"
        "  a) Free forever (open source / personal)\n"
        "  b) Freemium (free + paid)\n"
        "  c) Subscription only\n"
        "  d) One-time purchase\n"
        "  e) Not decided yet\n"
        "  f) Other\n\n"
        "  → Recommended: b) Freemium — lets users try before buying."
        + _RESPOND_HINT
    )


def _q_deployment(ctx: dict) -> str:
    return (
        "Ask the user:\n\n"
        "Where should this run?\n"
        "  a) Vercel\n"
        "  b) AWS\n"
        "  c) Railway / Render\n"
        "  d) Self-hosted / Docker\n"
        "  e) Local only\n"
        "  f) Other\n\n"
        "  → Recommend based on stack."
        + _RESPOND_HINT
    )


# ====================================================================== #
#  PRD
# ====================================================================== #


def generate_prd(context: dict) -> str:
    parts = [
        "Generate docs/prd.md with the following specs:\n",
        f"Project: {context.get('user_request', '')}",
        f"Type: {context.get('project_type', '')}",
        f"Target users: {context.get('target_users', '')}",
        f"Problem: {context.get('core_problem', '')}",
        f"Features: {context.get('features', '')}",
        f"Stack: {context.get('tech_stack', '')}",
        f"Stage: {context.get('project_stage', '')}",
    ]
    for key in ("auth", "design", "monetization", "deployment"):
        if context.get(key):
            parts.append(f"{key.title()}: {context[key]}")

    parts.append(
        "\nStructure: Overview, Problem Statement, Target Users, Core Features, "
        "Technical Architecture, Data Model, API Design, UI/UX, Non-Functional Requirements, "
        "Success Metrics, Out of Scope, Open Questions."
    )
    parts.append(
        '\nAfter writing, call harmony_pipeline_next with '
        '{"step":"generate_prd","success":true,"prd_path":"docs/prd.md"}'
    )
    return "\n".join(parts)


def prd_review() -> str:
    return (
        "Show the user a summary of the PRD:\n"
        "- Project name, target users, stage, stack, feature count\n\n"
        "Use AskUserQuestion to ask:\n"
        "  a) Approve — start building\n"
        "  b) Show full PRD\n"
        "  c) Change something\n"
        "  d) Start over\n\n"
        "Do NOT proceed until user chooses a).\n"
        "Interpret their answer and call harmony_pipeline_respond with the letter (a/b/c/d)."
    )
