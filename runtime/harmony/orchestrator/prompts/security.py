"""Security review and hardening prompts."""

from __future__ import annotations


def harden_security_review() -> str:
    """Prompt for whole-project security review — uses actual tools + AI analysis."""
    return (
        "**CRITICAL: You MUST use the Agent tool to spawn a NEW agent for this security review.**\n"
        "Do NOT review yourself — use a fresh agent with no build context.\n\n"
        "Call Agent with this prompt:\n\n"
        '  "You are an independent security auditor. Review the ENTIRE codebase.\n\n'
        "  Step 1: Run automated scanners\n"
        "  - Python projects: bandit -r . -f json\n"
        "  - Node.js projects: npm audit --json\n"
        "  - All projects: grep -rn for hardcoded secrets:\n"
        '    grep -rn \'password.*=.*["\\x27]\\|api_key.*=.*["\\x27]\\|secret.*=.*["\\x27]\' '
        "--include='*.py' --include='*.ts' --include='*.js' --include='*.env'\n\n"
        "  Step 2: AI review of scanner results + manual inspection\n"
        "  - SQL injection: raw queries without parameterization\n"
        "  - XSS: unescaped user input in HTML/templates\n"
        "  - CSRF: state-changing endpoints without CSRF protection\n"
        "  - Auth bypasses: endpoints missing auth middleware\n"
        "  - Input validation: missing or insufficient validation\n"
        "  - Error leaking: stack traces or internal details exposed to users\n\n"
        "  Step 3: Quality issues\n"
        "  - Unhandled promise rejections / uncaught exceptions\n"
        "  - Missing error boundaries (React)\n"
        "  - Race conditions in async code\n"
        "  - Resource leaks (unclosed connections, file handles)\n\n"
        '  For each issue: {file, line, severity (critical/warning), description, fix}"\n\n'
        "After the Agent returns, call harmony_pipeline_next with:\n"
        '{"step":"harden_security","critical_count":N,"criticals":[...]}'
    )


def harden_fix_criticals(criticals: list[dict]) -> str:
    crit_text = "\n".join(
        f"- [{c.get('severity','?')}] {c.get('file','?')}:{c.get('line','?')} — {c.get('description','?')}"
        for c in criticals
    )
    return (
        f"Fix these critical issues:\n\n{crit_text}\n\n"
        "After fixing, call harmony_pipeline_next with:\n"
        '{"step":"harden_fix","success":true}'
    )
