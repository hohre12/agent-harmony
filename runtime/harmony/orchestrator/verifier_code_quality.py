"""Server-side code quality verification — magic numbers, duplicate code,
unused imports, N+1 queries, hardcoded strings.

These checks run server-side so agents cannot self-report clean results.
Violations are informational (not hard gate failures) and flow into the
audit agent's review context.
"""

from __future__ import annotations

import ast
import hashlib
import re
from collections import defaultdict
from pathlib import Path

from harmony.orchestrator.verifier import _git_changed_files, _safe_cwd

_SUPPORTED_EXTS = {".py", ".ts", ".tsx", ".js", ".jsx"}

_EXCLUDED_PATH_PARTS = {
    "config", "settings", ".env", "setup.py", "setup.cfg",
    "constants", "const.", "enums",
    "test_", "_test.", ".test.", ".spec.", "__tests__", "conftest",
    "generated", "migrations", "__pycache__", "node_modules",
}

_MAX_VIOLATIONS_PER_CHECK = 20


# ---------------------------------------------------------------------------
# Shared infrastructure
# ---------------------------------------------------------------------------

def _load_changed_sources(cwd: str) -> dict[str, str]:
    """Load changed source files, filtered by extension and exclusion rules."""
    out = _git_changed_files(cwd)
    if not out.strip():
        return {}
    sources: dict[str, str] = {}
    for filepath in out.strip().split("\n"):
        filepath = filepath.strip()
        if not filepath:
            continue
        p = Path(cwd) / filepath
        if p.suffix not in _SUPPORTED_EXTS or not p.exists():
            continue
        sources[filepath] = p.read_text(encoding="utf-8", errors="ignore")
    return sources


def _is_excluded(filepath: str) -> bool:
    """Check if a filepath should be excluded from quality checks."""
    fp_lower = filepath.lower()
    return any(part in fp_lower for part in _EXCLUDED_PATH_PARTS)


def _is_test_file(filepath: str) -> bool:
    fp_lower = filepath.lower()
    return any(p in fp_lower for p in (
        "test_", "_test.", ".test.", ".spec.", "__tests__", "conftest",
    ))


# ---------------------------------------------------------------------------
# 1. Magic numbers
# ---------------------------------------------------------------------------

_MAGIC_ALLOWLIST = {0, 1, -1, 2, 10, 100, 200, 201, 204, 301, 302, 400, 401, 403, 404, 500}
_CONST_ASSIGN_PY = re.compile(r'^[A-Z_][A-Z0-9_]*\s*=')
_CONST_ASSIGN_JS = re.compile(r'^\s*(?:export\s+)?const\s+[A-Z_][A-Z0-9_]*\s*=')


def verify_magic_numbers(sources: dict[str, str]) -> dict:
    """Detect numeric literals that should be named constants."""
    violations: list[dict] = []
    for filepath, content in sources.items():
        if _is_excluded(filepath):
            continue
        if filepath.endswith(".py"):
            violations.extend(_magic_numbers_python(filepath, content))
        elif Path(filepath).suffix in (".ts", ".tsx", ".js", ".jsx"):
            violations.extend(_magic_numbers_js(filepath, content))
    return {
        "violations": violations[:_MAX_VIOLATIONS_PER_CHECK],
        "violation_count": len(violations),
        "verified": True,
    }


def _magic_numbers_python(filepath: str, source: str) -> list[dict]:
    results: list[dict] = []
    lines = source.splitlines()
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return results
    for node in ast.walk(tree):
        if not isinstance(node, ast.Constant) or not isinstance(node.value, (int, float)):
            continue
        if node.value in _MAGIC_ALLOWLIST:
            continue
        lineno = getattr(node, "lineno", 0)
        if lineno <= 0 or lineno > len(lines):
            continue
        line = lines[lineno - 1]
        # Skip constant assignments (ALL_CAPS = ...)
        if _CONST_ASSIGN_PY.match(line.strip()):
            continue
        # Skip range() calls, enum definitions, default args
        if "range(" in line or "enum" in line.lower():
            continue
        results.append({
            "file": filepath, "line": lineno,
            "value": node.value, "context": line.strip()[:100],
        })
    return results


def _magic_numbers_js(filepath: str, source: str) -> list[dict]:
    results: list[dict] = []
    num_re = re.compile(r'(?<![a-zA-Z_$.\[])(-?\d+\.?\d*)\b')
    for i, line in enumerate(source.splitlines(), 1):
        stripped = line.strip()
        if not stripped or stripped.startswith("//") or stripped.startswith("*"):
            continue
        if _CONST_ASSIGN_JS.match(stripped):
            continue
        if "import " in stripped or "require(" in stripped:
            continue
        for m in num_re.finditer(stripped):
            try:
                val = float(m.group(1))
                if val in _MAGIC_ALLOWLIST:
                    continue
                # Skip array indices [0], [1]
                pos = m.start()
                if pos > 0 and stripped[pos - 1] == "[":
                    continue
                results.append({
                    "file": filepath, "line": i,
                    "value": val, "context": stripped[:100],
                })
            except ValueError:
                continue
    return results


# ---------------------------------------------------------------------------
# 2. Duplicate code
# ---------------------------------------------------------------------------

def verify_duplicate_code(sources: dict[str, str]) -> dict:
    """Detect blocks of 4+ consecutive similar lines appearing in multiple locations."""
    window_size = 4
    hash_map: dict[str, list[tuple[str, int]]] = defaultdict(list)
    for filepath, content in sources.items():
        if _is_test_file(filepath):
            continue
        lines = content.splitlines()
        normalized = []
        line_nums = []
        for i, line in enumerate(lines, 1):
            stripped = line.strip()
            if not stripped or stripped.startswith("#") or stripped.startswith("//"):
                continue
            if stripped.startswith("import ") or stripped.startswith("from "):
                continue
            if stripped in ("}", ")", "]", "pass", "return", "break", "continue"):
                continue
            norm = stripped.lower().replace(" ", "")
            normalized.append(norm)
            line_nums.append(i)
        for j in range(len(normalized) - window_size + 1):
            block = "\n".join(normalized[j:j + window_size])
            h = hashlib.md5(block.encode()).hexdigest()
            hash_map[h].append((filepath, line_nums[j]))

    violations: list[dict] = []
    for h, locations in hash_map.items():
        if len(locations) < 2:
            continue
        # Filter: must be in different files or separated by >10 lines in same file
        unique_files = set(f for f, _ in locations)
        if len(unique_files) < 2:
            locs_sorted = sorted(locations, key=lambda x: x[1])
            if all(locs_sorted[i + 1][1] - locs_sorted[i][1] < 10
                   for i in range(len(locs_sorted) - 1)):
                continue
        violations.append({
            "locations": [{"file": f, "start_line": l} for f, l in locations[:5]],
            "count": len(locations),
        })
    return {
        "violations": violations[:_MAX_VIOLATIONS_PER_CHECK],
        "violation_count": len(violations),
        "verified": True,
    }


# ---------------------------------------------------------------------------
# 3. Unused imports
# ---------------------------------------------------------------------------

def verify_unused_imports(sources: dict[str, str]) -> dict:
    """Detect imports that are never referenced in the file."""
    violations: list[dict] = []
    for filepath, content in sources.items():
        if _is_excluded(filepath):
            continue
        if filepath.endswith("__init__.py"):
            continue
        if filepath.endswith(".py"):
            violations.extend(_unused_imports_python(filepath, content))
        elif Path(filepath).suffix in (".ts", ".tsx", ".js", ".jsx"):
            violations.extend(_unused_imports_js(filepath, content))
    return {
        "violations": violations[:_MAX_VIOLATIONS_PER_CHECK],
        "violation_count": len(violations),
        "verified": True,
    }


def _unused_imports_python(filepath: str, source: str) -> list[dict]:
    results: list[dict] = []
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return results

    # Check for noqa on import lines
    lines = source.splitlines()
    noqa_lines: set[int] = set()
    for i, line in enumerate(lines, 1):
        if "# noqa" in line or "# type: ignore" in line:
            noqa_lines.add(i)

    # Check for __all__ — if defined, all listed names are "used"
    all_names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id == "__all__":
                    if isinstance(node.value, (ast.List, ast.Tuple)):
                        for elt in node.value.elts:
                            if isinstance(elt, ast.Constant) and isinstance(elt.value, str):
                                all_names.add(elt.value)

    # Collect imports
    imports: list[tuple[str, int, str]] = []  # (local_name, lineno, statement)
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                name = alias.asname or alias.name.split(".")[0]
                if node.lineno not in noqa_lines:
                    imports.append((name, node.lineno, f"import {alias.name}"))
        elif isinstance(node, ast.ImportFrom):
            if node.module and "TYPE_CHECKING" in source[: source.find("\n", 0) * 5 if "\n" in source else len(source)]:
                # Rough check — skip TYPE_CHECKING block imports
                pass
            for alias in node.names:
                if alias.name == "*":
                    continue
                name = alias.asname or alias.name
                if node.lineno not in noqa_lines:
                    imports.append((name, node.lineno, f"from {node.module} import {alias.name}"))

    # Collect all name references (excluding import nodes themselves)
    used_names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Name):
            used_names.add(node.id)
        elif isinstance(node, ast.Attribute):
            used_names.add(node.attr)

    for local_name, lineno, statement in imports:
        if local_name in all_names:
            continue
        if local_name not in used_names:
            results.append({
                "file": filepath, "line": lineno,
                "import_name": local_name, "statement": statement,
            })
    return results


def _unused_imports_js(filepath: str, source: str) -> list[dict]:
    results: list[dict] = []
    lines = source.splitlines()
    import_re = re.compile(
        r'''import\s+(?:type\s+)?(?:\{([^}]+)\}|(\w+)|\*\s+as\s+(\w+))\s+from'''
    )
    require_re = re.compile(
        r'''(?:const|let|var)\s+(?:\{([^}]+)\}|(\w+))\s*=\s*require\s*\('''
    )
    # Side-effect imports (no bindings)
    side_effect_re = re.compile(r'''import\s+['"]''')

    for i, line in enumerate(lines, 1):
        stripped = line.strip()
        if side_effect_re.match(stripped):
            continue

        names: list[str] = []
        m = import_re.search(stripped)
        if m:
            if m.group(1):  # named imports { a, b, c }
                names = [n.strip().split(" as ")[-1].strip() for n in m.group(1).split(",") if n.strip()]
            elif m.group(2):  # default import
                names = [m.group(2)]
            elif m.group(3):  # namespace import
                names = [m.group(3)]
        else:
            m = require_re.search(stripped)
            if m:
                if m.group(1):
                    names = [n.strip().split(":")[0].strip() for n in m.group(1).split(",") if n.strip()]
                elif m.group(2):
                    names = [m.group(2)]

        if not names:
            continue

        # Check each name against rest of file
        rest = "\n".join(lines[i:])  # everything after import line
        for name in names:
            if not name or name.startswith("type "):
                continue
            name = name.strip()
            if not re.search(rf'\b{re.escape(name)}\b', rest):
                results.append({
                    "file": filepath, "line": i,
                    "import_name": name, "statement": stripped[:100],
                })
    return results


# ---------------------------------------------------------------------------
# 4. N+1 query patterns
# ---------------------------------------------------------------------------

_PYTHON_QUERY_RE = re.compile(
    r'\.\s*(?:query|filter|filter_by|get|all|first|count|delete|update|'
    r'execute|fetchone|fetchall|fetchmany|objects)\s*\('
)
_PYTHON_QUERY_CONTEXT_RE = re.compile(
    r'(?:session|db|cursor|Model|objects|repository|repo|store|dao)',
    re.IGNORECASE,
)
_PYTHON_BATCH_RE = re.compile(
    r'(?:prefetch_related|select_related|bulk_create|bulk_update|in_bulk)',
)

_JS_QUERY_RE = re.compile(
    r'await\s+\w+\.\s*(?:find|findOne|findMany|findById|findUnique|findFirst|'
    r'query|exec|execute|aggregate|count|create|update|delete|remove|save)\s*\('
)
_JS_BATCH_RE = re.compile(
    r'(?:include|populate|with_|createMany|insertMany|bulkCreate|bulkWrite)',
)


def verify_nplus1_queries(sources: dict[str, str]) -> dict:
    """Detect database/ORM calls inside loops."""
    violations: list[dict] = []
    for filepath, content in sources.items():
        if _is_test_file(filepath):
            continue
        if filepath.endswith(".py"):
            violations.extend(_nplus1_python(filepath, content))
        elif Path(filepath).suffix in (".ts", ".tsx", ".js", ".jsx"):
            violations.extend(_nplus1_js(filepath, content))
    return {
        "violations": violations[:_MAX_VIOLATIONS_PER_CHECK],
        "violation_count": len(violations),
        "verified": True,
    }


def _nplus1_python(filepath: str, source: str) -> list[dict]:
    results: list[dict] = []
    lines = source.splitlines()
    loop_stack: list[tuple[int, int]] = []  # (indent_level, line_number)
    for i, line in enumerate(lines, 1):
        stripped = line.lstrip()
        indent = len(line) - len(stripped)
        # Pop loops we've exited
        while loop_stack and indent <= loop_stack[-1][0]:
            loop_stack.pop()
        if re.match(r'^(for|while)\b', stripped):
            loop_stack.append((indent, i))
            continue
        if loop_stack and _PYTHON_QUERY_RE.search(stripped):
            if _PYTHON_BATCH_RE.search(stripped):
                continue
            if _PYTHON_QUERY_CONTEXT_RE.search(stripped) or ".objects" in stripped:
                results.append({
                    "file": filepath,
                    "loop_line": loop_stack[-1][1],
                    "query_line": i,
                    "loop_context": lines[loop_stack[-1][1] - 1].strip()[:80],
                    "query_context": stripped.strip()[:80],
                })
    return results


def _nplus1_js(filepath: str, source: str) -> list[dict]:
    results: list[dict] = []
    lines = source.splitlines()
    # Track loops via brace depth
    loop_starts: list[tuple[int, int]] = []  # (brace_depth_at_start, line_number)
    brace_depth = 0
    loop_re = re.compile(r'\b(?:for|while)\s*\(|\.(?:forEach|map|flatMap|reduce|filter|find|some|every)\s*\(')

    for i, line in enumerate(lines, 1):
        stripped = line.strip()
        # Check for loop start
        if loop_re.search(stripped):
            loop_starts.append((brace_depth, i))
        # Track braces
        brace_depth += stripped.count("{") - stripped.count("}")
        # Pop loops we've exited
        while loop_starts and brace_depth <= loop_starts[-1][0]:
            loop_starts.pop()
        # Check for query inside loop
        if loop_starts and _JS_QUERY_RE.search(stripped):
            if _JS_BATCH_RE.search(stripped):
                continue
            results.append({
                "file": filepath,
                "loop_line": loop_starts[-1][1],
                "query_line": i,
                "loop_context": lines[loop_starts[-1][1] - 1].strip()[:80],
                "query_context": stripped[:80],
            })
    return results


# ---------------------------------------------------------------------------
# 5. Hardcoded repeated strings
# ---------------------------------------------------------------------------

_COMMON_KEYS = {
    "id", "name", "type", "data", "error", "message", "status", "result",
    "value", "key", "index", "content", "title", "description", "label",
    "text", "url", "path", "src", "href", "class", "style", "children",
    "onClick", "onChange", "onSubmit", "default", "none", "null", "true",
    "false", "utf-8", "utf8", "GET", "POST", "PUT", "DELETE", "PATCH",
}


def verify_hardcoded_strings(sources: dict[str, str]) -> dict:
    """Detect string literals repeated 3+ times across files."""
    string_map: dict[str, list[tuple[str, int]]] = defaultdict(list)
    for filepath, content in sources.items():
        if _is_test_file(filepath) or _is_excluded(filepath):
            continue
        if filepath.endswith(".py"):
            _collect_strings_python(filepath, content, string_map)
        elif Path(filepath).suffix in (".ts", ".tsx", ".js", ".jsx"):
            _collect_strings_js(filepath, content, string_map)

    violations: list[dict] = []
    for string_val, locations in string_map.items():
        if len(locations) < 3:
            continue
        violations.append({
            "string": string_val[:60],
            "count": len(locations),
            "locations": [{"file": f, "line": l} for f, l in locations[:5]],
        })
    # Sort by count descending
    violations.sort(key=lambda v: v["count"], reverse=True)
    return {
        "violations": violations[:_MAX_VIOLATIONS_PER_CHECK],
        "violation_count": len(violations),
        "verified": True,
    }


def _should_skip_string(s: str) -> bool:
    if len(s) < 4 or len(s) > 200:
        return True
    if s.lower() in _COMMON_KEYS:
        return True
    if s.startswith(("http://", "https://", "/", "./", "../")):
        return True
    if "{" in s or "%s" in s or "${" in s or "%d" in s:
        return True
    if all(c in " \t\n\r" for c in s):
        return True
    if re.match(r'^[^a-zA-Z0-9]+$', s):
        return True
    return False


def _collect_strings_python(filepath: str, source: str, string_map: dict) -> None:
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            s = node.value
            if _should_skip_string(s):
                continue
            lineno = getattr(node, "lineno", 0)
            if lineno > 0:
                string_map[s].append((filepath, lineno))


def _collect_strings_js(filepath: str, source: str, string_map: dict) -> None:
    str_re = re.compile(r'''(?:["'])([^"']{4,})(?:["'])''')
    for i, line in enumerate(source.splitlines(), 1):
        stripped = line.strip()
        if stripped.startswith("//") or stripped.startswith("*"):
            continue
        if "import " in stripped or "require(" in stripped:
            continue
        for m in str_re.finditer(stripped):
            s = m.group(1)
            if _should_skip_string(s):
                continue
            string_map[s].append((filepath, i))


# ---------------------------------------------------------------------------
# Orchestrator
# ---------------------------------------------------------------------------

def verify_code_quality(cwd: str = ".") -> dict:
    """Run all code quality verifiers and return aggregated results."""
    cwd = _safe_cwd(cwd)
    sources = _load_changed_sources(cwd)
    if not sources:
        return {
            "magic_numbers": {"violations": [], "violation_count": 0, "verified": True},
            "duplicate_code": {"violations": [], "violation_count": 0, "verified": True},
            "unused_imports": {"violations": [], "violation_count": 0, "verified": True},
            "nplus1_queries": {"violations": [], "violation_count": 0, "verified": True},
            "hardcoded_strings": {"violations": [], "violation_count": 0, "verified": True},
            "total_violations": 0,
            "verified": True,
        }
    magic = verify_magic_numbers(sources)
    dupes = verify_duplicate_code(sources)
    imports = verify_unused_imports(sources)
    nplus1 = verify_nplus1_queries(sources)
    strings = verify_hardcoded_strings(sources)
    total = (
        magic["violation_count"]
        + dupes["violation_count"]
        + imports["violation_count"]
        + nplus1["violation_count"]
        + strings["violation_count"]
    )
    return {
        "magic_numbers": magic,
        "duplicate_code": dupes,
        "unused_imports": imports,
        "nplus1_queries": nplus1,
        "hardcoded_strings": strings,
        "total_violations": total,
        "verified": True,
    }
