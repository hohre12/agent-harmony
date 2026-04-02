"""Interview and PRD prompts."""

from __future__ import annotations


_RESPOND_HINT = (
    "\n\nYou MUST call the AskUserQuestion tool to present the choices. "
    "Do NOT just print them as text. "
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
    # -- Collect interview context ----------------------------------------
    ctx_lines = [
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
            ctx_lines.append(f"{key.title()}: {context[key]}")
    context_block = "\n".join(ctx_lines)

    return (
        "Generate docs/prd.md — a COMPREHENSIVE Product Requirements Document.\n"
        "Target length: at least 200 lines. Be specific and concrete, not generic.\n\n"
        "=== INTERVIEW CONTEXT ===\n"
        f"{context_block}\n\n"
        "=== GLOBAL RULES ===\n"
        "- Write the PRD in the SAME LANGUAGE the user used during the interview.\n"
        "- Use the interview context to INFER any missing details. Make reasonable "
        "assumptions based on the project type, stack, and target users.\n"
        "- If a detail truly cannot be inferred, make a sensible default choice and "
        'record it under "Open Questions" so the user can revisit it.\n'
        "- Do NOT leave any section blank or write placeholder text like 'TBD'.\n\n"
        "=== REQUIRED SECTIONS (write each one in full detail) ===\n\n"
        "## 1. Overview\n"
        "- Project name\n"
        "- One-line description (what it does, for whom)\n"
        "- Tech stack summary (language, framework, database, deployment)\n\n"
        "## 2. Problem Statement\n"
        "- The specific pain point users face today\n"
        "- Current alternatives / workarounds the user might try\n"
        "- Why those alternatives are insufficient (cost, complexity, limitations)\n\n"
        "## 3. Target Users\n"
        "- Primary user persona: who they are, their role, their technical level\n"
        "- Environment: where and how they will use this (desktop, mobile, CLI, etc.)\n"
        "- Key motivations and frustrations\n\n"
        "## 4. Core Features\n"
        "For EACH feature listed in the context, write:\n"
        "- **Description**: What the feature does in 2-3 sentences\n"
        "- **User flow**: Step-by-step from the user's perspective "
        "(e.g., 1. User clicks X → 2. System shows Y → 3. User confirms → 4. Result)\n"
        "- **Error / failure scenarios**: What can go wrong and how the system handles it "
        "(e.g., network failure → retry with exponential backoff; invalid input → "
        "inline validation message)\n"
        "- **Acceptance criteria**: 3-5 testable statements "
        '(e.g., "Given a logged-in user, when they submit the form with valid data, '
        'then a new record is created and a success toast appears within 2 seconds")\n\n'
        "## 5. Technical Architecture\n"
        "- **System component diagram**: Draw an ASCII diagram showing all major "
        "components (client, server, database, external services, queues, etc.) "
        "and the connections between them.\n"
        "- **Data flow**: Describe the step-by-step sequence for the MAIN user flow, "
        "from the moment the user triggers an action to the final response. "
        "Example format:\n"
        "  1. User submits form in React component\n"
        "  2. Frontend sends POST /api/resource with JSON body\n"
        "  3. API middleware validates JWT token\n"
        "  4. Controller calls service layer\n"
        "  5. Service writes to PostgreSQL via Prisma\n"
        "  6. Service publishes event to queue\n"
        "  7. Response 201 returned with created resource\n"
        "- **Component responsibilities**: For each component, list what it owns "
        "and which other components it communicates with (and how: REST, WebSocket, "
        "direct function call, message queue, etc.)\n\n"
        "## 6. Data Model\n"
        "- Full schema for EVERY entity: field name, type, constraints "
        "(NOT NULL, UNIQUE, DEFAULT, etc.), and relationships (FK references)\n"
        "- If the stack uses SQL: provide actual CREATE TABLE statements\n"
        "- If NoSQL: provide the document structure with types\n"
        "- Index strategy: list indexes needed for performance-critical queries "
        "and explain why each index exists\n\n"
        "## 7. API Design\n"
        "For EACH endpoint:\n"
        "- HTTP method + path (e.g., POST /api/v1/users)\n"
        "- Brief description\n"
        "- Authentication: required or public\n"
        "- Request body: full JSON example with realistic sample data\n"
        "- Success response: status code + full JSON example\n"
        "- Error responses: list each error case with status code and JSON body\n"
        "Example:\n"
        "```\n"
        "POST /api/v1/tasks\n"
        "Auth: Bearer token required\n"
        "Request:\n"
        '  { "title": "Buy groceries", "due_date": "2025-03-15" }\n'
        "Response 201:\n"
        '  { "id": "abc-123", "title": "Buy groceries", "due_date": "2025-03-15", '
        '"status": "pending", "created_at": "2025-03-10T09:00:00Z" }\n'
        "Error 401:\n"
        '  { "error": "unauthorized", "message": "Invalid or expired token" }\n'
        "Error 422:\n"
        '  { "error": "validation_error", "details": [{"field": "title", '
        '"message": "must not be empty"}] }\n'
        "```\n\n"
        "## 8. UI/UX\n"
        "- Design principles (e.g., mobile-first, accessibility-first, minimal clicks)\n"
        "- Key screens: list each screen with its purpose and main elements\n"
        "- Layout structure: describe the overall layout "
        "(sidebar + content, top nav + cards, etc.)\n"
        "- Responsive behavior: how the layout adapts to mobile vs desktop\n\n"
        "## 9. Non-Functional Requirements\n"
        "Provide SPECIFIC numbers for each:\n"
        "- Performance: target response time (e.g., API p95 < 200ms, page load < 2s)\n"
        "- Availability: uptime target (e.g., 99.9%)\n"
        "- Scalability: expected concurrent users / requests per second\n"
        "- Security: authentication method, data encryption, input validation strategy\n"
        "- Browser / platform support\n\n"
        "## 10. Success Metrics\n"
        "List 3-5 metrics that are QUANTIFIED and MEASURABLE:\n"
        "- Example: 'User registration to first action < 3 minutes'\n"
        "- Example: 'API error rate < 0.1% in production'\n"
        "- Example: '80% of users complete onboarding without support'\n\n"
        "## 11. Out of Scope\n"
        "Explicitly list features and concerns that are NOT part of this version. "
        "Be specific (e.g., 'Multi-language i18n support', 'Native mobile app', "
        "'Advanced analytics dashboard').\n\n"
        "## 12. Implementation Phases\n"
        "Break the build into ordered phases based on dependency:\n"
        "- Phase 1: Foundation — what must be built first (project setup, data model, auth)\n"
        "- Phase 2: Core — the primary user-facing features\n"
        "- Phase 3: Polish — secondary features, error handling, edge cases\n"
        "- Phase 4: Launch — deployment, monitoring, documentation\n"
        "For each phase, list the specific deliverables.\n\n"
        "## 13. Open Questions\n"
        "List any assumptions you made and decisions that need user confirmation.\n\n"
        "=== END OF STRUCTURE ===\n\n"
        'After writing the complete PRD to docs/prd.md, call harmony_pipeline_next with '
        '{"step":"generate_prd","success":true,"prd_path":"docs/prd.md"}'
    )


def prd_review() -> str:
    return (
        "Show the user a summary of the PRD:\n"
        "- Project name, target users, stage, stack, feature count\n\n"
        "You MUST call the AskUserQuestion tool to present these choices:\n"
        "  a) Approve — start building\n"
        "  b) Show full PRD\n"
        "  c) Change something\n"
        "  d) Start over\n\n"
        "Do NOT proceed until user chooses a).\n"
        "Interpret their answer and call harmony_pipeline_respond with the letter (a/b/c/d)."
    )


# ====================================================================== #
#  Choice resolution (moved from pipeline.py for separation of concerns)
# ====================================================================== #

# Choice letter → human-readable mapping per question
CHOICE_MAP: dict[str, dict[str, str]] = {
    "target_users": {
        "a": "Developers / technical users",
        "b": "General consumers (non-technical)",
        "c": "Internal team / company employees",
        "d": "Enterprise clients (B2B)",
        "e": "Myself only (personal tool)",
    },
    "core_problem": {
        "a": "Manual repetitive work that should be automated",
        "b": "Existing tools are too expensive",
        "c": "Existing tools are too complex / bad UX",
        "d": "No good solution exists yet",
        "e": "Internal process that needs systematizing",
    },
    "tech_stack": {
        "a": "Next.js + TypeScript + Prisma + PostgreSQL",
        "b": "React + TypeScript + Node.js + Express",
        "c": "Python + FastAPI + PostgreSQL",
        "d": "React Native + Expo + TypeScript",
        "e": "Python + Click/Typer (CLI)",
    },
    "project_stage": {
        "a": "Prototype",
        "b": "MVP",
        "c": "Production",
    },
    "design": {
        "a": "Clean & minimal (shadcn/ui)",
        "b": "Bold & creative (custom design)",
        "c": "Match a reference",
        "d": "Functional only (handle design separately)",
    },
    "auth": {
        "a": "Email + password",
        "b": "Social login only (Google, GitHub)",
        "c": "Email + social login (both)",
        "d": "Magic link (passwordless)",
        "e": "No authentication needed",
    },
    "monetization": {
        "a": "Free forever (open source / personal)",
        "b": "Freemium (free + paid)",
        "c": "Subscription only",
        "d": "One-time purchase",
        "e": "Not decided yet",
    },
    "deployment": {
        "a": "Vercel",
        "b": "AWS",
        "c": "Railway / Render",
        "d": "Self-hosted / Docker",
        "e": "Local only",
    },
}


def resolve_answer(question_id: str, raw_answer: str) -> str:
    """Convert short letter answers to full text. Handles multi-select (e.g., 'a, b, c')."""
    choices = CHOICE_MAP.get(question_id, {})
    if not choices:
        return raw_answer

    # Check for multi-select (comma-separated letters)
    parts = [p.strip().lower().rstrip(")") for p in raw_answer.split(",")]
    if len(parts) > 1:
        resolved_parts = []
        for part in parts:
            letter = part[0] if part and part[0] in "abcdef" else ""
            resolved_parts.append(choices.get(letter, part))
        return ", ".join(resolved_parts)

    # Single answer
    letter = raw_answer.strip().lower().rstrip(")")
    if letter and letter[0] in "abcdef":
        letter = letter[0]
    return choices.get(letter, raw_answer)
