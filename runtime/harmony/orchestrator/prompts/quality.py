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
        "   (grep -rn 'password.*=.*[\"\\']' for hardcoded secrets)\n"
        "7. ACCESSIBILITY (frontend only): → a11y_critical: count\n"
        "   - If project has frontend (React/Next.js/Vue): run axe-core or eslint-plugin-jsx-a11y\n"
        "   - Check: missing alt text, missing aria-labels, non-semantic elements, color contrast\n"
        "   - If no frontend: a11y_critical: 0\n"
        "8. FRONTEND DESIGN (frontend only — informational, not gated):\n"
        "   - grep for hardcoded color values (e.g., #fff, rgb()) outside design token files\n"
        "   - grep for hardcoded px values in layout (should use spacing tokens)\n"
        "   - Report findings as warnings (not gate failures)\n\n"
        "IMPORTANT: Report EXACT numbers for ALL metrics. If a metric cannot be measured\n"
        "(e.g., no frontend = no a11y check), report the metric as 0 or true as appropriate.\n"
        "Do NOT omit any metric — omitted metrics cause automatic gate failure.\n\n"
        f"Thresholds (ALL must be met): {threshold_text}\n\n"
        "Call harmony_pipeline_next with:\n"
        f'{{"step":"quality_gate","task_id":"{task_id}","task_title":"{task_title}","scores":{{\n'
        '  "build":true/false, "tests":true/false, "test_coverage":<N>,\n'
        '  "lint":true/false, "max_file_lines":<N>, "max_function_lines":<N>,\n'
        '  "security_critical":<N>, "a11y_critical":<N>\n'
        "}}"
    )


def production_audit(task_id: str, task_title: str) -> str:
    """Prompt for AI-based production audit — runs after quality gate passes."""
    return (
        f'Production audit for task {task_id}: "{task_title}"\n\n'
        "**CRITICAL: You MUST use the Agent tool to spawn a NEW agent for this audit.**\n"
        "Do NOT review the code yourself — you built it, so you are biased.\n"
        "The Agent tool creates a fresh context with no memory of the build.\n\n"
        "Call Agent with this prompt (copy exactly):\n\n"
        '  "You are a senior engineer performing a production audit.\n'
        "  You have NO context about how this code was built. You are an independent reviewer.\n"
        f'  Task: {task_title}\n'
        "  1. Find the task branch base: git merge-base HEAD main (or develop/master)\n"
        "     Then run: git diff --name-only <merge-base>...HEAD to find ALL changed files\n"
        "     Do NOT use HEAD~1 — tasks may span multiple commits.\n"
        "  2. Read docs/prd.md for the relevant feature spec\n"
        "  3. Review ONLY the changed files. Be STRICT. Look for:\n"
        "     - PRD compliance: does the code implement what the spec says?\n"
        "     - Error handling: network failures, empty states, invalid input\n"
        "     - Security: input validation, auth checks, no hardcoded secrets\n"
        "     - Edge cases: empty lists, zero values, boundary conditions\n"
        "     - Integration: imports resolve, API contracts match\n"
        "     - Code structure: no god files (>400 lines), clear separation\n"
        "     - Test quality: tests must have meaningful assertions — reject tests that\n"
        "       only call functions without asserting results, or use trivial expect(true)\n"
        "     - Frontend (if applicable):\n"
        "       * Responsive design: components work at mobile/tablet/desktop widths\n"
        "       * Empty states: what shows when data is empty or loading?\n"
        "       * Error states: what shows when API calls fail?\n"
        "       * Loading states: skeleton/spinner during async operations\n"
        "       * Design token usage: colors/spacing from tokens, not hardcoded values\n"
        "       * Accessibility: semantic HTML, aria attributes, keyboard navigation\n"
        '  4. For each issue: file:line, severity (MUST-FIX/SHOULD-FIX), what, how to fix\n'
        '  5. Default to NEEDS_FIX. Only verdict PASS if genuinely no issues found."\n\n'
        "After the Agent returns, call harmony_pipeline_next with:\n"
        f'{{"step":"audit","task_id":"{task_id}","auditor_id":"<agent-id-from-Agent-tool>","verdict":"PASS"/"NEEDS_FIX","issues":[...]}}\n\n'
        "CRITICAL: auditor_id is REQUIRED. The pipeline will REJECT audit results without it.\n"
        "Use the agent ID returned by the Agent tool."
    )
