"""Quality gate and production audit prompts.

The quality gate is DETERMINISTIC — it runs actual tools and extracts numeric metrics.
The production audit is AI-based but informed by gate results.
"""

from __future__ import annotations


def quality_gate(task_id: str, task_title: str, thresholds: dict) -> str:
    """Prompt for deterministic quality gate — extracts numeric metrics."""
    threshold_text = ", ".join(f"{k}={v}" for k, v in thresholds.items())
    return (
        f"Quality gate for task {task_id}: \"{task_title}\"\n\n"
        "Run these checks and extract EXACT numbers:\n"
        "1. BUILD: run build command → build: true/false\n"
        "2. TESTS: run test suite with coverage → tests: true/false, test_coverage: number\n"
        "   (Python: pytest --cov | grep TOTAL, Node: jest --coverage | grep All files)\n"
        "3. LINT: run linter → lint: true/false (zero errors)\n"
        "4. FILE SIZE: wc -l on changed source files → max_file_lines: largest count\n"
        "5. FUNCTION SIZE: count lines of largest function → max_function_lines: number\n"
        "6. SECURITY: run scanner + grep for hardcoded secrets → security_critical: count\n"
        "   (Python: bandit -r . -f json, Node: npm audit --json)\n"
        "   (grep -rn 'password.*=.*[\"\\']' for hardcoded secrets)\n\n"
        f"Thresholds (ALL must be met): {threshold_text}\n\n"
        "Call harmony_pipeline_next with:\n"
        f'{{"step":"quality_gate","task_id":"{task_id}","task_title":"{task_title}","scores":{{\n'
        '  "build":true/false, "tests":true/false, "test_coverage":<N>,\n'
        '  "lint":true/false, "max_file_lines":<N>, "max_function_lines":<N>,\n'
        '  "security_critical":<N>\n'
        "}}"
    )


def production_audit(task_id: str, task_title: str) -> str:
    """Prompt for AI-based production audit — runs after quality gate passes."""
    return (
        f'Production audit for task {task_id}: "{task_title}"\n\n'
        "Spawn a fresh Agent for this audit (clean context, no build history).\n"
        "Agent prompt:\n\n"
        '  "You are a senior engineer performing a production audit.\n'
        f'  Task: {task_title}\n'
        "  1. Run: git diff --name-only HEAD~1 to find changed files\n"
        "  2. Read docs/prd.md for the relevant feature spec\n"
        "  3. Review ONLY the changed files against:\n"
        "     - PRD compliance: does the code implement what the spec says?\n"
        "     - Error handling: network failures, empty states, invalid input\n"
        "     - Security: input validation, auth checks, no hardcoded secrets\n"
        "     - Edge cases: empty lists, zero values, boundary conditions\n"
        "     - Integration: imports resolve, API contracts match\n"
        "     - Code structure: no god files, clear separation of concerns\n"
        '  4. For each issue: file:line, severity (MUST-FIX/SHOULD-FIX), what, how to fix"\n\n'
        "After the Agent returns, call harmony_pipeline_next with:\n"
        f'{{"step":"audit","task_id":"{task_id}","verdict":"PASS"/"NEEDS_FIX","issues":[...]}}'
    )
