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
        "9. CODE QUALITY (server-side verified — informational):\n"
        "   The server automatically detects: magic numbers, duplicate code blocks,\n"
        "   unused imports, N+1 query patterns, and hardcoded repeated strings.\n"
        "   These are reported as warnings and passed to the production audit.\n"
        "   Fix proactively — the audit agent WILL see these violations.\n\n"
        "IMPORTANT: Report EXACT numbers for ALL metrics. If a metric cannot be measured\n"
        "(e.g., no frontend = no a11y check), report the metric as 0 or true as appropriate.\n"
        "Do NOT omit any metric — omitted metrics cause automatic gate failure.\n\n"
        "ACCOUNTABILITY: Your measurements will be cross-verified server-side.\n"
        "If your reported scores do not match actual measurements, the gate fails\n"
        "and you will be asked to re-measure. Report only what you can verify.\n\n"
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
        "  You see ONLY the code output — not the process, reasoning, or intentions.\n\n"
        "  YOUR AUDIT STANDARDS:\n"
        "  - Be RUTHLESS. Give NO benefit of the doubt.\n"
        "  - If something MIGHT be wrong, flag it as MUST-FIX — not SHOULD-FIX.\n"
        "  - You are accountable for your judgment: if you pass code that later\n"
        "    breaks in production, it reflects on YOU. Err on the side of rejection.\n"
        "  - Treat every file as if written by an untrusted stranger.\n\n"
        f'  Task: {task_title}\n'
        "  1. Find the task branch base: git merge-base HEAD main (or develop/master)\n"
        "     Then run: git diff --name-only <merge-base>...HEAD to find ALL changed files\n"
        "     Do NOT use HEAD~1 — tasks may span multiple commits.\n"
        "  2. Read docs/prd.md for the relevant feature spec\n"
        "  3. Review ONLY the changed files. Be STRICT. Look for:\n"
        "     **Bugs & Logic:**\n"
        "     - Logic errors: wrong conditionals, off-by-one, inverted boolean, missing return\n"
        "     - Null/undefined: unguarded access to optional values, missing null checks\n"
        "     - Race conditions: shared state without synchronization, async ordering issues\n"
        "     - Type mismatches: string where number expected, wrong enum values\n"
        "     - Boundary conditions: empty arrays, zero/negative values, max int, long strings\n\n"
        "     **Code Quality:**\n"
        "     - DRY violations: duplicated logic that should be extracted to shared functions\n"
        "     - Magic numbers/strings: hardcoded values that should be named constants\n"
        "     - Common components: repeated UI patterns that should be shared components\n"
        "     - Naming: unclear, inconsistent, or misleading variable/function/class names\n"
        "     - Dead code: unused imports, unreachable branches, commented-out code\n"
        "     - God files (>400 lines) or god functions (>60 lines): must be split\n\n"
        "     **Architecture & Integration:**\n"
        "     - PRD compliance: does the code implement what the spec says?\n"
        "     - Integration: imports resolve, API contracts match, types align\n"
        "     - Error handling: network failures, empty states, invalid input — all handled\n"
        "     - Security: input validation, auth checks, no hardcoded secrets\n\n"
        "     **Performance:**\n"
        "     - N+1 queries: DB calls inside loops\n"
        "     - Unnecessary re-renders: missing memoization, wrong dependency arrays\n"
        "     - Missing pagination: unbounded data fetches\n"
        "     - Expensive operations in hot paths: regex compilation in loops, sync I/O\n\n"
        "     **Test Quality:**\n"
        "     - Tests must have meaningful assertions — reject tests that\n"
        "       only call functions without asserting results, or use trivial expect(true)\n"
        "     - Edge case coverage: are boundary conditions actually tested?\n"
        "     - Error path coverage: are failure scenarios tested, not just happy paths?\n\n"
        "     **Frontend (if applicable):**\n"
        "     - Responsive design: components work at mobile/tablet/desktop widths\n"
        "     - Empty/error/loading states: what shows in each state?\n"
        "     - Design token usage: colors/spacing from tokens, not hardcoded values\n"
        "     - Accessibility: semantic HTML, aria attributes, keyboard navigation\n"
        "     - Common UI patterns: repeated layouts/cards/buttons should be shared components\n"
        "     **Server-Detected Violations (check quality_scores in .harmony/state.json):**\n"
        "     The server has already detected code quality issues stored in the task's\n"
        "     quality_scores._code_quality_details field. Review these violations:\n"
        "     - magic_numbers: numeric literals that should be named constants\n"
        "     - duplicate_code: repeated code blocks that should be shared functions\n"
        "     - unused_imports: imports that are never referenced\n"
        "     - nplus1_queries: DB/ORM calls inside loops\n"
        "     - hardcoded_strings: repeated string literals that should be constants\n"
        "     Flag these as MUST-FIX if they are genuine issues.\n\n"
        '  4. For each issue: file:line, severity (MUST-FIX/SHOULD-FIX), what, how to fix\n'
        '  5. Default to NEEDS_FIX. Only verdict PASS if genuinely no issues found.\n'
        '  6. Remember: passing bad code is worse than flagging a false positive."\n\n'
        "After the Agent returns, call harmony_pipeline_next with:\n"
        f'{{"step":"audit","task_id":"{task_id}","auditor_id":"<agent-id-from-Agent-tool>","verdict":"PASS"/"NEEDS_FIX","issues":[...]}}\n\n'
        "CRITICAL: auditor_id is REQUIRED. The pipeline will REJECT audit results without it.\n"
        "Use the agent ID returned by the Agent tool."
    )
