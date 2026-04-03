"""Server-side verification — core checks (build evidence, file/function sizes, PRD, tasks).

Frontend-specific checks (design tokens, build-and-test detection, quality-score
orchestration) live in ``verifier_frontend.py``.
"""

from __future__ import annotations

import ast
import re
import subprocess
from pathlib import Path


def _safe_cwd(cwd: str) -> str:
    """Validate cwd is a safe, existing directory."""
    p = Path(cwd).resolve()
    if not p.exists() or not p.is_dir():
        raise ValueError(f"Invalid cwd: {cwd}")
    return str(p)


def run_cmd(cmd: list[str], cwd: str = ".", timeout: int = 30) -> tuple[int, str]:
    """Run a command and return (returncode, stdout). Stderr merged into stdout."""
    try:
        r = subprocess.run(
            cmd, capture_output=True, text=True, cwd=cwd, timeout=timeout,
        )
        return r.returncode, (r.stdout + r.stderr).strip()
    except (subprocess.TimeoutExpired, FileNotFoundError, OSError) as e:
        return -1, str(e)


def verify_build_evidence(cwd: str = ".") -> dict:
    """Check git for evidence that code was actually written/changed."""
    cwd = _safe_cwd(cwd)
    code, out = run_cmd(["git", "diff", "--stat", "HEAD"], cwd=cwd)
    if code != 0:
        code, out = run_cmd(["git", "diff", "--stat"], cwd=cwd)
    has_changes = bool(out.strip())
    files_changed = 0
    if has_changes:
        for line in out.strip().split("\n"):
            if "changed" in line:
                parts = line.strip().split()
                if parts and parts[0].isdigit():
                    files_changed = int(parts[0])
    if not has_changes:
        # Also check recent commits (team-executor may have already committed)
        code2, out2 = run_cmd(["git", "log", "--oneline", "--stat", "-1"], cwd=cwd)
        if code2 == 0 and out2.strip():
            # Check if the last commit was recent (within the session)
            has_changes = "changed" in out2
            if has_changes:
                for line in out2.strip().split("\n"):
                    if "changed" in line:
                        parts = line.strip().split()
                        if parts and parts[0].isdigit():
                            files_changed = int(parts[0])
    return {
        "has_changes": has_changes,
        "files_changed": files_changed,
        "raw": out[:500],
    }


def _git_changed_files(cwd: str) -> str:
    """Get list of changed files using merge-base for accuracy across multi-commit tasks."""
    # Try merge-base against main/master/develop for the most accurate diff
    for base in ("main", "master", "develop"):
        code, merge_base = run_cmd(["git", "merge-base", base, "HEAD"], cwd=cwd)
        if code == 0 and merge_base.strip():
            code, out = run_cmd(["git", "diff", "--name-only", "--diff-filter=ACMR", merge_base.strip()], cwd=cwd)
            if code == 0 and out.strip():
                return out
    # Fallback to HEAD~1
    code, out = run_cmd(["git", "diff", "--name-only", "--diff-filter=ACMR", "HEAD~1"], cwd=cwd)
    if code == 0 and out.strip():
        return out
    # Last resort: all tracked files
    code, out = run_cmd(["git", "ls-files"], cwd=cwd)
    return out if code == 0 else ""


def verify_file_sizes(cwd: str = ".") -> dict:
    """Find the largest source file by line count among recently changed files."""
    cwd = _safe_cwd(cwd)
    out = _git_changed_files(cwd)
    if not out.strip():
        return {"max_file_lines": 0, "largest_file": "", "verified": False}
    source_exts = {".py", ".ts", ".tsx", ".js", ".jsx", ".vue", ".svelte", ".go", ".rs", ".java"}
    max_lines = 0
    largest_file = ""
    for filepath in out.strip().split("\n"):
        filepath = filepath.strip()
        if not filepath:
            continue
        p = Path(cwd) / filepath
        if p.suffix not in source_exts or not p.exists():
            continue
        try:
            line_count = len(p.read_text(encoding="utf-8", errors="ignore").splitlines())
            if line_count > max_lines:
                max_lines = line_count
                largest_file = filepath
        except (OSError, UnicodeDecodeError):
            continue
    return {
        "max_file_lines": max_lines,
        "largest_file": largest_file,
        "verified": True,
    }


def verify_prd_sections(prd_path: str = "docs/prd.md") -> dict:
    """Check that a PRD file contains required sections with content depth."""
    p = Path(prd_path)
    if not p.exists():
        return {"exists": False, "missing_sections": ["FILE_NOT_FOUND"], "valid": False}
    content = p.read_text(encoding="utf-8", errors="ignore")
    content_lower = content.lower()
    required_sections = [
        "overview",
        "problem",
        "target user",
        "feature",
        "technical",
        "data model",
        "api",
    ]
    missing = []
    for section in required_sections:
        # Match section keyword in a header line (# or ##) — allow plural/suffix
        pattern = rf'(?:^|\n)#{{1,3}}\s+.*\b{re.escape(section)}'
        if not re.search(pattern, content_lower):
            missing.append(section)

    # --- Section depth thresholds ---
    # Map keywords to minimum content lines required
    _section_min_lines: dict[str, int] = {
        "feature": 10,
        "technical": 8,
        "architecture": 8,
        "data model": 5,
        "api": 8,
    }

    def _min_lines_for(header: str) -> int:
        """Return the minimum content-line threshold for a section header."""
        h = header.lower()
        for keyword, minimum in _section_min_lines.items():
            if keyword in h:
                return minimum
        return 3  # default for all other sections

    # Walk sections and measure content lines
    shallow_sections: list[str] = []
    lines = content_lower.splitlines()
    current_section = ""
    section_content_lines = 0
    for line in lines:
        if line.strip().startswith("#"):
            if current_section and section_content_lines < _min_lines_for(current_section):
                shallow_sections.append(current_section)
            current_section = line.strip()
            section_content_lines = 0
        elif line.strip():
            section_content_lines += 1
    # Check last section
    if current_section and section_content_lines < _min_lines_for(current_section):
        shallow_sections.append(current_section)

    # --- Content depth indicators ---
    depth_issues: list[str] = []
    total_lines = len(lines)

    # 1. Minimum PRD length
    if total_lines < 100:
        depth_issues.append(
            f"PRD is only {total_lines} lines — minimum 100 expected for adequate depth"
        )

    # 2. Code blocks (``` markers) — schemas, API examples, architecture
    has_code_blocks = "```" in content
    if not has_code_blocks:
        depth_issues.append(
            "PRD contains no code blocks — expected schema definitions, "
            "API examples, or architecture diagrams"
        )

    # 3. Table markers (|) — structured data
    has_tables = bool(re.search(r'^\s*\|.*\|', content, re.MULTILINE))

    # 4. Schema / structured-data evidence in data-model or API sections
    has_schema_evidence = bool(
        re.search(r'create\s+table', content_lower)
        or re.search(r'schema', content_lower)
        or re.search(r'(?:\{[\s\S]*?"[a-z_]+")', content)  # JSON-like object
    )
    if "data model" not in missing and "api" not in missing and not has_schema_evidence:
        depth_issues.append(
            "Data-model / API sections lack schema definitions, "
            "CREATE TABLE statements, or JSON examples"
        )

    # 5. Error / failure scenario mentions
    error_mentions = len(re.findall(r'\b(?:error|fail|failure|exception)\b', content_lower))
    if error_mentions < 1:
        depth_issues.append(
            "PRD does not discuss error or failure scenarios"
        )

    # --- Determine validity ---
    # Critical depth issues that make the PRD invalid:
    #   - PRD under 100 lines
    #   - No code blocks at all
    has_critical_depth_issues = (total_lines < 100) or (not has_code_blocks)

    return {
        "exists": True,
        "missing_sections": missing,
        "shallow_sections": shallow_sections,
        "depth_issues": depth_issues,
        "has_tables": has_tables,
        "has_code_blocks": has_code_blocks,
        "error_mention_count": error_mentions,
        "valid": len(missing) == 0 and not has_critical_depth_issues,
        "file_lines": total_lines,
    }


def verify_task_structure(tasks: list[dict]) -> dict:
    """Validate vertical-slice task structure."""
    issues: list[str] = []
    if not tasks:
        return {"valid": False, "issues": ["No tasks provided"]}
    horizontal_keywords = [
        "set up database", "setup database", "create schema", "all api",
        "build all", "create all ui", "all pages", "all endpoints",
        "database layer", "api layer", "ui layer", "frontend layer",
        "backend layer", "infrastructure setup",
    ]
    for task in tasks:
        title = task.get("title", "").lower()
        task_id = task.get("id", "?")
        subtasks = task.get("subtasks", [])
        # Only flag if the title starts with or is primarily a horizontal pattern
        title_words = title.split("[")[0].strip()
        for kw in horizontal_keywords:
            if kw in title_words:
                issues.append(f"Task {task_id}: horizontal-layer pattern detected: '{kw}'")
                break
        if not subtasks:
            issues.append(f"Task {task_id}: no subtasks defined")
        elif len(subtasks) < 2:
            issues.append(f"Task {task_id}: only {len(subtasks)} subtask — too few for vertical slice")
        if subtasks:
            agents: set[str] = set()
            for st in subtasks:
                st_title = st.get("title", "")
                if "(" in st_title and ")" in st_title:
                    agent = st_title.split("(")[-1].rstrip(")")
                    agents.add(agent.strip())
            if len(agents) <= 1 and len(subtasks) > 1:
                issues.append(f"Task {task_id}: all subtasks assigned to same agent — not a vertical slice")
        for st in subtasks:
            st_id = st.get("id", "?")
            if not st.get("description"):
                issues.append(f"Subtask {st_id}: missing description field")
            if not st.get("test"):
                issues.append(f"Subtask {st_id}: missing test acceptance criteria")
    return {
        "valid": len(issues) == 0,
        "issues": issues,
        "task_count": len(tasks),
    }


def _measure_python_functions(filepath: str, source: str) -> tuple[int, str]:
    """Measure largest function in Python file via AST. Returns (max_lines, func_name)."""
    max_lines = 0
    largest = ""
    try:
        tree = ast.parse(source)
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                end_lineno = getattr(node, "end_lineno", None)
                if end_lineno is None:
                    continue
                func_lines = end_lineno - node.lineno + 1
                if func_lines > max_lines:
                    max_lines = func_lines
                    largest = node.name
    except SyntaxError:
        pass
    return max_lines, largest


def _clean_js_source_via_node(filepath: str) -> str | None:
    """Strip comments, strings, and template literals from a JS/TS file using Node.js.

    Returns the cleaned source text, or *None* if Node.js is unavailable or
    the script fails for any reason.
    """
    # Inline Node.js script that removes syntactic noise so that subsequent
    # brace-counting is accurate.  Processing order matters:
    #   1. multi-line comments   /*...*/
    #   2. single-line comments  //...
    #   3. template literals     `...`  (may span multiple lines)
    #   4. single-quoted strings '...'
    #   5. double-quoted strings "..."
    # Replaced content is substituted with empty strings (comments) or ""
    # (string-like constructs) so that line numbers are preserved.
    node_script = (
        "const s=require('fs').readFileSync(process.argv[1],'utf8');"
        "let c=s"
        r".replace(/\/\*[\s\S]*?\*\//g,function(m){return m.replace(/[^\n]/g,'')})"
        r".replace(/\/\/[^\n]*/g,'')"
        r".replace(/`[^`]*`/g,'\"\"')"
        ".replace(/'[^']*'/g,'\"\"')"
        ".replace(/\"[^\"]*\"/g,'\"\"');"
        "process.stdout.write(c)"
    )
    try:
        r = subprocess.run(
            ["node", "-e", node_script, filepath],
            capture_output=True, text=True, timeout=10,
        )
        if r.returncode == 0:
            return r.stdout
    except (FileNotFoundError, subprocess.TimeoutExpired, OSError):
        pass
    return None


def _brace_count_functions(source: str) -> tuple[int, str]:
    """Measure largest function in source via brace counting.

    Expects *cleaned* source (comments and strings already stripped) for
    accurate results, but also works on raw source as a fallback.

    Returns ``(max_lines, func_name)``.
    """
    lines = source.splitlines()
    max_lines = 0
    largest = ""
    in_func = False
    brace_depth = 0
    func_start = 0
    func_name = ""
    for i, line in enumerate(lines):
        stripped = line.strip()
        if not in_func and ("function " in stripped or "=>" in stripped or stripped.startswith("async ")):
            if "{" in stripped:
                in_func = True
                brace_depth = stripped.count("{") - stripped.count("}")
                func_start = i
                for token in stripped.split():
                    if token not in ("function", "async", "export", "default", "const", "let", "var"):
                        func_name = token.split("(")[0].split("=")[0].strip()
                        break
        elif in_func:
            brace_depth += stripped.count("{") - stripped.count("}")
            if brace_depth <= 0:
                func_len = i - func_start + 1
                if func_len > max_lines:
                    max_lines = func_len
                    largest = func_name
                in_func = False
    return max_lines, largest


def _measure_js_functions(source: str, filepath: str = "") -> tuple[int, str]:
    """Measure largest function in a JS/TS file.

    Uses Node.js to strip comments, strings, and template literals before
    brace-counting, which is much more accurate than raw brace counting
    (avoids false positives from braces inside template literals, JSX,
    destructuring patterns in strings, etc.).

    Falls back to raw-source brace counting when Node.js is unavailable.

    Returns ``(max_lines, func_name)``.
    """
    if filepath:
        cleaned = _clean_js_source_via_node(filepath)
        if cleaned is not None:
            return _brace_count_functions(cleaned)
    # Fallback: brace-count on the raw source (less accurate)
    return _brace_count_functions(source)


def verify_function_sizes(cwd: str = ".") -> dict:
    """Measure the largest function by line count using Python AST for .py files, regex for others."""
    cwd = _safe_cwd(cwd)
    out = _git_changed_files(cwd)
    if not out.strip():
        return {"max_function_lines": 0, "largest_function": "", "file": "", "verified": False}
    max_lines = 0
    largest_func = ""
    largest_file = ""
    for filepath in out.strip().split("\n"):
        filepath = filepath.strip()
        if not filepath:
            continue
        p = Path(cwd) / filepath
        if not p.exists():
            continue
        try:
            source = p.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        if p.suffix == ".py":
            func_lines, func_name = _measure_python_functions(filepath, source)
        elif p.suffix in (".ts", ".tsx", ".js", ".jsx"):
            func_lines, func_name = _measure_js_functions(source, str(p))
        else:
            continue
        if func_lines > max_lines:
            max_lines = func_lines
            largest_func = func_name
            largest_file = filepath
    return {
        "max_function_lines": max_lines,
        "largest_function": largest_func,
        "file": largest_file,
        "verified": True,
    }


def verify_design_doc(task_id: str, cwd: str = ".") -> dict:
    """Verify that a task's design document meets minimum quality standards.

    Checks: existence, minimum line count, required sections, code blocks.
    Returns dict with valid=True/False and details.
    """
    cwd = _safe_cwd(cwd)
    # Find design doc by glob pattern: docs/tasks/*-{task_id}-*-plan.md
    task_dir = Path(cwd) / "docs" / "tasks"
    if not task_dir.exists():
        return {"valid": False, "exists": False, "issues": ["docs/tasks/ directory not found"]}

    matches = list(task_dir.glob(f"*-{task_id}-*-plan.md"))
    if not matches:
        return {"valid": False, "exists": False, "issues": [f"No design doc found for task {task_id}"]}

    doc_path = matches[0]
    content = doc_path.read_text(encoding="utf-8", errors="ignore")
    lines = content.splitlines()
    line_count = len(lines)
    content_lower = content.lower()
    issues: list[str] = []

    # 1. Minimum line count
    min_lines = 80
    if line_count < min_lines:
        issues.append(
            f"Design doc is only {line_count} lines — minimum {min_lines} expected. "
            "Use TeamCreate + architect agents to write a thorough design doc."
        )

    # 2. Required sections
    required_sections = [
        ("overview", "Overview"),
        ("implementation file list", "Implementation File List"),
        ("build sequence", "Build Sequence"),
    ]
    # At least one of these should exist
    optional_sections = [
        ("api design", "API Design"),
        ("data model", "Data Model"),
        ("key decision", "Key Decisions"),
    ]
    for keyword, label in required_sections:
        if keyword not in content_lower:
            issues.append(f"Missing required section: {label}")

    has_optional = any(kw in content_lower for kw, _ in optional_sections)
    if not has_optional:
        issues.append(
            "Missing domain sections — need at least one of: API Design, Data Model, Key Decisions"
        )

    # 3. Code blocks (architecture diagrams, schemas, file lists)
    has_code_blocks = "```" in content
    if not has_code_blocks:
        issues.append("No code blocks found — expected schemas, file structures, or code examples")

    # 4. Subtask coverage — doc should reference subtask IDs or mention subtask count
    subtask_refs = len(re.findall(rf'{task_id}\.\d+', content))
    if subtask_refs == 0:
        # Also check for "subtask" or "sub-task" mentions
        if "subtask" not in content_lower and "sub-task" not in content_lower:
            issues.append("Design doc does not reference subtask IDs — each subtask should be addressed")

    return {
        "valid": len(issues) == 0,
        "exists": True,
        "file": str(doc_path.relative_to(cwd)),
        "line_count": line_count,
        "has_code_blocks": has_code_blocks,
        "issues": issues,
    }


def verify_files_exist(paths: list[str], cwd: str = ".") -> dict:
    """Check that expected output files exist."""
    missing = []
    for p in paths:
        full = Path(cwd) / p
        if not full.exists():
            missing.append(p)
    return {"all_exist": len(missing) == 0, "missing": missing}
