"""Frontend-specific verification — design tokens, build/test detection, quality score orchestration."""

from __future__ import annotations

import json
import re
from pathlib import Path

from harmony.orchestrator.verifier import (
    _safe_cwd,
    run_cmd,
    verify_build_evidence,
    verify_file_sizes,
    verify_function_sizes,
)


def verify_design_tokens(cwd: str = ".") -> dict:
    """Grep source files for hardcoded color/spacing values outside design token files."""
    cwd = _safe_cwd(cwd)
    token_file_patterns = {"token", "theme", "design", "palette", "variable", "custom-propert"}
    color_pattern = re.compile(r'(?:^|[\s:,"\'])(?:#[0-9a-fA-F]{3,8}|rgba?\s*\(|hsla?\s*\()', re.MULTILINE)
    spacing_pattern = re.compile(
        r'(?:margin|padding|gap|width|height|top|bottom|left|right)\s*:\s*\d+px',
        re.IGNORECASE,
    )
    source_exts = {".tsx", ".jsx", ".vue", ".svelte", ".css", ".scss", ".less"}
    violations: list[dict] = []
    code, out = run_cmd(["git", "ls-files"], cwd=cwd)
    if code != 0 or not out.strip():
        return {"violation_count": 0, "violations": [], "verified": False}
    for filepath in out.strip().split("\n"):
        filepath = filepath.strip()
        if not filepath:
            continue
        p = Path(cwd) / filepath
        if p.suffix not in source_exts or not p.exists():
            continue
        if any(pat in filepath.lower() for pat in token_file_patterns):
            continue

        try:
            content = p.read_text(encoding="utf-8", errors="ignore")
            for i, line in enumerate(content.splitlines(), 1):
                if color_pattern.search(line):
                    violations.append({"file": filepath, "line": i, "type": "color", "content": line.strip()[:100]})
                if spacing_pattern.search(line):
                    violations.append({"file": filepath, "line": i, "type": "spacing", "content": line.strip()[:100]})
        except OSError:
            continue
    return {
        "violation_count": len(violations),
        "violations": violations[:20],
        "verified": True,
    }


def verify_design_brief_content(brief_path: str = "docs/refs/design-brief.md") -> dict:
    """Check that a design brief contains required design system sections."""
    p = Path(brief_path)
    if not p.exists():
        return {"exists": False, "missing_sections": ["FILE_NOT_FOUND"], "valid": False}

    content = p.read_text(encoding="utf-8", errors="ignore").lower()

    required_sections = ["color", "typography", "spacing", "component"]
    missing = []
    for section in required_sections:
        if section not in content:
            missing.append(section)

    return {
        "exists": True,
        "missing_sections": missing,
        "valid": len(missing) == 0,
        "file_lines": len(content.splitlines()),
    }


def _verify_node_project(cwd: str) -> dict:
    """Run Node.js build/test/lint commands."""
    results: dict = {}
    code, out = run_cmd(["npm", "run", "build", "--if-present"], cwd=cwd, timeout=120)
    results["build"] = code == 0
    code, out = run_cmd(["npx", "jest", "--coverage", "--ci", "--passWithNoTests"], cwd=cwd, timeout=120)
    results["tests"] = code == 0
    for line in out.split("\n"):
        if "All files" in line or "Stmts" in line:
            parts = line.split("|")
            for part in parts:
                try:
                    val = float(part.strip())
                    if 0 <= val <= 100:
                        results["test_coverage"] = val
                        break
                except ValueError:
                    continue
    code, out = run_cmd(["npx", "eslint", ".", "--format", "json", "--max-warnings", "99999"], cwd=cwd, timeout=60)
    try:
        lint_data = json.loads(out)
        error_count = sum(f.get("errorCount", 0) for f in lint_data)
        results["lint"] = error_count == 0
    except (json.JSONDecodeError, TypeError):
        pass
    return results


def _verify_python_project(cwd: str) -> dict:
    """Run Python build/test/lint commands."""
    from pathlib import Path as P
    results: dict = {}
    # Syntax check changed files
    code_check, files_out = run_cmd(["git", "diff", "--name-only", "--diff-filter=ACMR", "HEAD~1"], cwd=cwd)
    build_ok = True
    if code_check == 0:
        for f in files_out.strip().split("\n"):
            f = f.strip()
            if f.endswith(".py") and (P(cwd) / f).exists():
                rc, _ = run_cmd(["python3", "-m", "py_compile", str(P(cwd) / f)], cwd=cwd, timeout=10)
                if rc != 0:
                    build_ok = False
                    break
    results["build"] = build_ok
    code, out = run_cmd(["python3", "-m", "pytest", "--tb=no", "-q", "--co"], cwd=cwd, timeout=30)
    if code == 0:
        code, out = run_cmd(["python3", "-m", "pytest", "--tb=short", "-q", "--cov", "--cov-report=term-missing"], cwd=cwd, timeout=120)
        results["tests"] = code == 0
        for line in out.split("\n"):
            if "TOTAL" in line:
                parts = line.split()
                for part in parts:
                    part = part.rstrip("%")
                    try:
                        val = float(part)
                        if 0 <= val <= 100:
                            results["test_coverage"] = val
                    except ValueError:
                        continue
    code, out = run_cmd(["python3", "-m", "flake8", "--count", "--statistics"], cwd=cwd, timeout=30)
    if code != -1:
        results["lint"] = code == 0
    return results


def verify_build_and_tests(cwd: str = ".") -> dict:
    """Auto-detect and run build/test commands."""
    cwd = _safe_cwd(cwd)
    p = Path(cwd)
    if (p / "package.json").exists():
        return _verify_node_project(cwd)
    if (p / "pyproject.toml").exists() or (p / "setup.py").exists():
        return _verify_python_project(cwd)
    return {}


def cross_verify_quality_scores(reported: dict, cwd: str = ".") -> dict:
    """Cross-verify agent-reported quality scores against server-side measurements."""
    cwd = _safe_cwd(cwd)
    mismatches: dict[str, dict] = {}
    actual: dict = {}
    warnings: list[str] = []
    unverified: list[str] = []
    file_result = verify_file_sizes(cwd)
    if file_result["verified"]:
        actual_max = file_result["max_file_lines"]
        actual["max_file_lines"] = actual_max
        reported_max = reported.get("max_file_lines")
        if reported_max is not None and isinstance(reported_max, (int, float)):
            if actual_max > reported_max + 2:
                mismatches["max_file_lines"] = {
                    "reported": reported_max,
                    "actual": actual_max,
                    "file": file_result["largest_file"],
                }
    else:
        unverified.append("max_file_lines")
    func_result = verify_function_sizes(cwd)
    if func_result["verified"]:
        actual_func = func_result["max_function_lines"]
        actual["max_function_lines"] = actual_func
        reported_func = reported.get("max_function_lines")
        if reported_func is not None and isinstance(reported_func, (int, float)):
            if actual_func > reported_func + 2:
                mismatches["max_function_lines"] = {
                    "reported": reported_func,
                    "actual": actual_func,
                    "function": func_result["largest_function"],
                    "file": func_result["file"],
                }
    else:
        unverified.append("max_function_lines")
    bt_result = verify_build_and_tests(cwd)
    for key in ("build", "tests", "lint", "test_coverage"):
        if key in bt_result:
            actual[key] = bt_result[key]
            reported_val = reported.get(key)
            if reported_val is not None:
                if isinstance(bt_result[key], bool):
                    if bt_result[key] != reported_val:
                        mismatches[key] = {"reported": reported_val, "actual": bt_result[key]}
                elif isinstance(bt_result[key], (int, float)) and isinstance(reported_val, (int, float)):
                    if abs(bt_result[key] - reported_val) > 2:
                        mismatches[key] = {"reported": reported_val, "actual": bt_result[key]}
        else:
            unverified.append(key)
    evidence = verify_build_evidence(cwd)
    if not evidence["has_changes"]:
        warnings.append("No git changes detected — build may not have produced code")

    return {
        "verified": len(mismatches) == 0,
        "mismatches": mismatches,
        "actual": actual,
        "warnings": warnings,
        "unverified": unverified,
        "build_evidence": evidence,
    }
