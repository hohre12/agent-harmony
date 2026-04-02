"""Tests for server-side verification module."""

import json
import os
import tempfile
from pathlib import Path

import pytest

from harmony.orchestrator.verifier import (
    run_cmd,
    verify_build_evidence,
    verify_design_doc,
    verify_file_sizes,
    verify_function_sizes,
    verify_prd_sections,
    verify_task_structure,
    verify_files_exist,
)
from harmony.orchestrator.verifier_frontend import (
    verify_design_tokens,
    cross_verify_quality_scores,
)


class TestRunCmd:
    def test_echo(self):
        code, out = run_cmd(["echo", "hello"])
        assert code == 0
        assert "hello" in out

    def test_missing_command(self):
        code, out = run_cmd(["nonexistent_command_xyz"])
        assert code == -1

    def test_timeout(self):
        code, out = run_cmd(["sleep", "10"], timeout=1)
        assert code == -1


def _build_deep_prd(
    *,
    total_lines: int = 120,
    include_code_blocks: bool = True,
    include_tables: bool = True,
    include_schema: bool = True,
    include_error_mentions: bool = True,
    feature_lines: int = 12,
    technical_lines: int = 10,
    data_model_lines: int = 8,
    api_lines: int = 10,
) -> str:
    """Helper: build a realistic PRD string with controllable depth."""
    sections: list[str] = []
    sections.append("# Project PRD\n")

    # Put padding early (as an appendix section) so it doesn't inflate the
    # last real section's content count.  We insert a placeholder here and
    # replace it after we know how many lines are needed.
    _PADDING_PLACEHOLDER = "<<PADDING>>"

    sections.append("## Overview\nThis project is a web app.\nIt does things.\nMore detail here.\n")
    sections.append("## Problem Statement\nUsers cannot do X.\nThis causes Y.\nWe need Z.\n")
    sections.append("## Target Users\nDevelopers.\nDesigners.\nManagers.\n")

    # Feature section
    feat = ["## Core Features"]
    for i in range(feature_lines):
        feat.append(f"- Feature detail line {i}")
    sections.append("\n".join(feat) + "\n")

    # Technical section
    tech = ["## Technical Architecture"]
    for i in range(technical_lines):
        tech.append(f"Architecture detail line {i}")
    if include_code_blocks:
        tech.append("```\nservice -> db -> cache\n```")
    sections.append("\n".join(tech) + "\n")

    # Data model section
    dm = ["## Data Model"]
    for i in range(data_model_lines):
        dm.append(f"Model detail line {i}")
    if include_schema:
        dm.append("```sql\nCREATE TABLE users (id serial primary key, name text);\n```")
    if include_tables:
        dm.append("| Column | Type | Description |")
        dm.append("|--------|------|-------------|")
        dm.append("| id | int | Primary key |")
    sections.append("\n".join(dm) + "\n")

    # API section
    api = ["## API Design"]
    for i in range(api_lines):
        api.append(f"API detail line {i}")
    if include_code_blocks:
        api.append('```json\n{"status": "ok"}\n```')
    if include_error_mentions:
        api.append("On error, the API returns a 4xx status with an error message.")
        api.append("Failure scenarios include network timeouts and auth failures.")
    sections.append("\n".join(api) + "\n")

    # Appendix section — padding goes here so it doesn't inflate real sections
    sections.append("## Appendix\n" + _PADDING_PLACEHOLDER)

    body = "\n".join(sections)
    # Calculate how many padding lines we need
    current = len(body.replace(_PADDING_PLACEHOLDER, "").splitlines())
    if current < total_lines:
        padding = "\n".join([f"Additional note {i}." for i in range(total_lines - current)])
    else:
        padding = "Supplementary notes."
    body = body.replace(_PADDING_PLACEHOLDER, padding)
    return body


class TestVerifyPrdSections:
    def test_valid_prd_with_depth(self, tmp_path):
        """A fully fleshed-out PRD passes all checks."""
        prd = tmp_path / "prd.md"
        prd.write_text(_build_deep_prd())
        result = verify_prd_sections(str(prd))
        assert result["exists"]
        assert result["valid"]
        assert result["missing_sections"] == []
        assert result["depth_issues"] == []
        assert result["has_code_blocks"]
        assert result["has_tables"]
        assert result["error_mention_count"] >= 1

    def test_valid_prd_sections_only(self, tmp_path):
        """Legacy-style test: sections present but PRD is thin (< 100 lines, no code blocks).
        This should now be INVALID due to critical depth issues."""
        prd = tmp_path / "prd.md"
        prd.write_text(
            "# Project\n## Overview\nStuff\n## Problem Statement\nStuff\n"
            "## Target Users\nStuff\n## Core Features\nStuff\n"
            "## Technical Architecture\nStuff\n## Data Model\nStuff\n## API Design\nStuff\n"
        )
        result = verify_prd_sections(str(prd))
        assert result["exists"]
        assert result["missing_sections"] == []
        # But should fail due to depth issues (too short, no code blocks)
        assert not result["valid"]
        assert len(result["depth_issues"]) > 0

    def test_missing_sections(self, tmp_path):
        prd = tmp_path / "prd.md"
        prd.write_text("# Project\n## Overview\nStuff\n")
        result = verify_prd_sections(str(prd))
        assert result["exists"]
        assert not result["valid"]
        assert len(result["missing_sections"]) > 0

    def test_file_not_found(self):
        result = verify_prd_sections("/nonexistent/prd.md")
        assert not result["exists"]
        assert not result["valid"]

    # --- Minimum PRD length ---

    def test_prd_under_100_lines_invalid(self, tmp_path):
        """A PRD with all sections but only 50 lines should fail."""
        prd = tmp_path / "prd.md"
        prd.write_text(_build_deep_prd(total_lines=50))
        result = verify_prd_sections(str(prd))
        assert not result["valid"]
        assert any("100" in issue for issue in result["depth_issues"])

    def test_prd_over_100_lines_no_length_issue(self, tmp_path):
        """A PRD with 120 lines should not trigger the length issue."""
        prd = tmp_path / "prd.md"
        prd.write_text(_build_deep_prd(total_lines=120))
        result = verify_prd_sections(str(prd))
        assert not any("100" in issue and "lines" in issue for issue in result["depth_issues"])

    # --- Section depth thresholds ---

    def test_shallow_feature_section(self, tmp_path):
        """Feature section with < 10 content lines should be flagged as shallow."""
        prd = tmp_path / "prd.md"
        prd.write_text(_build_deep_prd(feature_lines=3))
        result = verify_prd_sections(str(prd))
        assert any("feature" in s for s in result["shallow_sections"])

    def test_deep_feature_section_not_shallow(self, tmp_path):
        """Feature section with >= 10 content lines should NOT be shallow."""
        prd = tmp_path / "prd.md"
        prd.write_text(_build_deep_prd(feature_lines=12))
        result = verify_prd_sections(str(prd))
        assert not any("feature" in s for s in result["shallow_sections"])

    def test_shallow_technical_section(self, tmp_path):
        """Technical section with < 8 content lines should be flagged."""
        prd = tmp_path / "prd.md"
        prd.write_text(_build_deep_prd(technical_lines=2))
        result = verify_prd_sections(str(prd))
        assert any("technical" in s for s in result["shallow_sections"])

    def test_shallow_api_section(self, tmp_path):
        """API section with < 8 content lines should be flagged."""
        prd = tmp_path / "prd.md"
        # Disable code blocks and error mentions in API section so only
        # api_lines count toward the section's content.
        prd.write_text(_build_deep_prd(
            api_lines=2, include_code_blocks=False,
            include_error_mentions=False, include_schema=False,
        ))
        result = verify_prd_sections(str(prd))
        assert any("api" in s for s in result["shallow_sections"])

    def test_shallow_data_model_section(self, tmp_path):
        """Data model section with < 5 content lines should be flagged."""
        prd = tmp_path / "prd.md"
        # Disable schema and tables so only data_model_lines count.
        prd.write_text(_build_deep_prd(
            data_model_lines=1, include_schema=False,
            include_tables=False, include_code_blocks=False,
        ))
        result = verify_prd_sections(str(prd))
        assert any("data model" in s for s in result["shallow_sections"])

    # --- Content depth indicators ---

    def test_no_code_blocks_flagged(self, tmp_path):
        """PRD without code blocks should have a depth issue and be invalid."""
        prd = tmp_path / "prd.md"
        prd.write_text(_build_deep_prd(include_code_blocks=False, include_schema=False))
        result = verify_prd_sections(str(prd))
        assert not result["has_code_blocks"]
        assert not result["valid"]
        assert any("code block" in issue for issue in result["depth_issues"])

    def test_has_tables_detected(self, tmp_path):
        """PRD with table markers should set has_tables=True."""
        prd = tmp_path / "prd.md"
        prd.write_text(_build_deep_prd(include_tables=True))
        result = verify_prd_sections(str(prd))
        assert result["has_tables"]

    def test_no_tables_detected(self, tmp_path):
        """PRD without table markers should set has_tables=False."""
        prd = tmp_path / "prd.md"
        prd.write_text(_build_deep_prd(include_tables=False))
        result = verify_prd_sections(str(prd))
        assert not result["has_tables"]

    def test_no_schema_evidence_flagged(self, tmp_path):
        """PRD without schema/CREATE TABLE/JSON should flag depth issue."""
        prd = tmp_path / "prd.md"
        prd.write_text(_build_deep_prd(include_schema=False, include_code_blocks=False))
        result = verify_prd_sections(str(prd))
        assert any("schema" in issue.lower() or "json" in issue.lower()
                    for issue in result["depth_issues"])

    def test_no_error_mentions_flagged(self, tmp_path):
        """PRD without error/failure mentions should flag depth issue."""
        prd = tmp_path / "prd.md"
        prd.write_text(_build_deep_prd(include_error_mentions=False))
        result = verify_prd_sections(str(prd))
        assert any("error" in issue or "failure" in issue for issue in result["depth_issues"])
        assert result["error_mention_count"] == 0

    def test_error_mentions_counted(self, tmp_path):
        """PRD with error mentions should report the count."""
        prd = tmp_path / "prd.md"
        prd.write_text(_build_deep_prd(include_error_mentions=True))
        result = verify_prd_sections(str(prd))
        assert result["error_mention_count"] >= 2  # "error" + "failure" in the helper

    # --- Return structure backward compatibility ---

    def test_return_structure_has_all_fields(self, tmp_path):
        """All expected fields are present in the return dict."""
        prd = tmp_path / "prd.md"
        prd.write_text(_build_deep_prd())
        result = verify_prd_sections(str(prd))
        assert "exists" in result
        assert "missing_sections" in result
        assert "shallow_sections" in result
        assert "depth_issues" in result
        assert "has_tables" in result
        assert "has_code_blocks" in result
        assert "error_mention_count" in result
        assert "valid" in result
        assert "file_lines" in result

    def test_file_not_found_return_structure(self):
        """FILE_NOT_FOUND path should still return backward-compatible dict."""
        result = verify_prd_sections("/nonexistent/prd.md")
        assert "exists" in result
        assert "missing_sections" in result
        assert "valid" in result


class TestVerifyTaskStructure:
    def test_valid_vertical_slices(self):
        tasks = [
            {
                "id": "1",
                "title": "User Auth [LEAD: architect-agent]",
                "subtasks": [
                    {"id": "1.1", "title": "Auth DB schema (db-agent)", "description": "Create auth tables", "test": "Verify tables exist"},
                    {"id": "1.2", "title": "Auth API endpoints (backend-agent)", "description": "Login/register APIs", "test": "Test auth flow"},
                    {"id": "1.3", "title": "Auth UI components (frontend-agent)", "description": "Login form", "test": "Render test"},
                ],
            }
        ]
        result = verify_task_structure(tasks)
        assert result["valid"]
        assert result["issues"] == []

    def test_horizontal_layer_detected(self):
        tasks = [
            {"id": "1", "title": "Set up database schema", "subtasks": [
                {"id": "1.1", "title": "Create tables (db-agent)"},
            ]},
        ]
        result = verify_task_structure(tasks)
        assert not result["valid"]
        assert any("horizontal-layer" in i for i in result["issues"])

    def test_empty_subtasks(self):
        tasks = [{"id": "1", "title": "Auth [LEAD: arch]", "subtasks": []}]
        result = verify_task_structure(tasks)
        assert not result["valid"]
        assert any("no subtasks" in i for i in result["issues"])

    def test_single_agent_subtasks(self):
        tasks = [
            {
                "id": "1",
                "title": "Feature [LEAD: arch]",
                "subtasks": [
                    {"id": "1.1", "title": "Part A (backend-agent)"},
                    {"id": "1.2", "title": "Part B (backend-agent)"},
                    {"id": "1.3", "title": "Part C (backend-agent)"},
                ],
            }
        ]
        result = verify_task_structure(tasks)
        assert not result["valid"]
        assert any("same agent" in i for i in result["issues"])

    def test_no_tasks(self):
        result = verify_task_structure([])
        assert not result["valid"]


class TestVerifyFilesExist:
    def test_all_exist(self, tmp_path):
        (tmp_path / "a.py").touch()
        (tmp_path / "b.py").touch()
        result = verify_files_exist(["a.py", "b.py"], str(tmp_path))
        assert result["all_exist"]

    def test_some_missing(self, tmp_path):
        (tmp_path / "a.py").touch()
        result = verify_files_exist(["a.py", "missing.py"], str(tmp_path))
        assert not result["all_exist"]
        assert "missing.py" in result["missing"]


class TestVerifyFunctionSizes:
    def test_python_function_measurement(self, tmp_path):
        """Test AST-based function size measurement for Python files."""
        # Create a git repo with a Python file
        import subprocess
        subprocess.run(["git", "init"], cwd=str(tmp_path), capture_output=True)
        subprocess.run(["git", "config", "user.email", "test@test.com"], cwd=str(tmp_path), capture_output=True)
        subprocess.run(["git", "config", "user.name", "Test"], cwd=str(tmp_path), capture_output=True)

        py_file = tmp_path / "app.py"
        # Create a file with a 10-line function
        lines = ["def big_function():"]
        for i in range(9):
            lines.append(f"    x_{i} = {i}")
        py_file.write_text("\n".join(lines) + "\n")

        subprocess.run(["git", "add", "."], cwd=str(tmp_path), capture_output=True)
        subprocess.run(["git", "commit", "-m", "init"], cwd=str(tmp_path), capture_output=True)

        result = verify_function_sizes(str(tmp_path))
        assert result["verified"]
        assert result["max_function_lines"] == 10
        assert result["largest_function"] == "big_function"

    def test_no_functions(self, tmp_path):
        """Test with file containing no functions."""
        import subprocess
        subprocess.run(["git", "init"], cwd=str(tmp_path), capture_output=True)
        subprocess.run(["git", "config", "user.email", "test@test.com"], cwd=str(tmp_path), capture_output=True)
        subprocess.run(["git", "config", "user.name", "Test"], cwd=str(tmp_path), capture_output=True)

        py_file = tmp_path / "constants.py"
        py_file.write_text("X = 1\nY = 2\n")
        subprocess.run(["git", "add", "."], cwd=str(tmp_path), capture_output=True)
        subprocess.run(["git", "commit", "-m", "init"], cwd=str(tmp_path), capture_output=True)

        result = verify_function_sizes(str(tmp_path))
        assert result["verified"]
        assert result["max_function_lines"] == 0


class TestMeasureJsFunctions:
    def test_js_function_detected(self, tmp_path):
        """Test brace-counting heuristic for JS/TS files."""
        import subprocess as sp
        sp.run(["git", "init"], cwd=str(tmp_path), capture_output=True)
        sp.run(["git", "config", "user.email", "t@t.com"], cwd=str(tmp_path), capture_output=True)
        sp.run(["git", "config", "user.name", "T"], cwd=str(tmp_path), capture_output=True)

        js_file = tmp_path / "app.js"
        lines = ["function bigFunc() {"]
        for i in range(14):
            lines.append(f"  const x_{i} = {i};")
        lines.append("}")
        js_file.write_text("\n".join(lines) + "\n")

        sp.run(["git", "add", "."], cwd=str(tmp_path), capture_output=True)
        sp.run(["git", "commit", "-m", "init"], cwd=str(tmp_path), capture_output=True)

        result = verify_function_sizes(str(tmp_path))
        assert result["verified"]
        assert result["max_function_lines"] == 16
        assert "bigFunc" in result["largest_function"]

    def test_js_template_literals_not_miscounted(self, tmp_path):
        """Template literals with braces should not inflate function size."""
        import subprocess as sp
        sp.run(["git", "init"], cwd=str(tmp_path), capture_output=True)
        sp.run(["git", "config", "user.email", "t@t.com"], cwd=str(tmp_path), capture_output=True)
        sp.run(["git", "config", "user.name", "T"], cwd=str(tmp_path), capture_output=True)

        js_file = tmp_path / "render.js"
        # 6-line function whose template literal contains extra braces
        source = (
            "function render() {\n"
            "  const a = 1;\n"
            "  const html = `<div>{some braces {nested}}</div>`;\n"
            "  const b = 2;\n"
            "  return html;\n"
            "}\n"
        )
        js_file.write_text(source)

        sp.run(["git", "add", "."], cwd=str(tmp_path), capture_output=True)
        sp.run(["git", "commit", "-m", "init"], cwd=str(tmp_path), capture_output=True)

        result = verify_function_sizes(str(tmp_path))
        assert result["verified"]
        # The function is exactly 6 lines.  Without Node.js cleaning the
        # template-literal braces would confuse brace counting.
        assert result["max_function_lines"] == 6
        assert result["largest_function"] == "render"

    def test_js_comments_not_miscounted(self, tmp_path):
        """Braces inside comments should not affect function measurement."""
        import subprocess as sp
        sp.run(["git", "init"], cwd=str(tmp_path), capture_output=True)
        sp.run(["git", "config", "user.email", "t@t.com"], cwd=str(tmp_path), capture_output=True)
        sp.run(["git", "config", "user.name", "T"], cwd=str(tmp_path), capture_output=True)

        js_file = tmp_path / "util.js"
        source = (
            "function helper() {\n"
            "  // closing brace in comment: }\n"
            "  const x = 1;\n"
            "  /* another } brace */\n"
            "  return x;\n"
            "}\n"
        )
        js_file.write_text(source)

        sp.run(["git", "add", "."], cwd=str(tmp_path), capture_output=True)
        sp.run(["git", "commit", "-m", "init"], cwd=str(tmp_path), capture_output=True)

        result = verify_function_sizes(str(tmp_path))
        assert result["verified"]
        assert result["max_function_lines"] == 6
        assert result["largest_function"] == "helper"


class TestVerifyDesignTokens:
    def test_detects_hardcoded_colors(self, tmp_path):
        """Test detection of hardcoded color values in source files."""
        import subprocess
        subprocess.run(["git", "init"], cwd=str(tmp_path), capture_output=True)
        subprocess.run(["git", "config", "user.email", "test@test.com"], cwd=str(tmp_path), capture_output=True)
        subprocess.run(["git", "config", "user.name", "Test"], cwd=str(tmp_path), capture_output=True)

        css_file = tmp_path / "app.css"
        css_file.write_text("body { color: #ff0000; background: rgb(255, 0, 0); }\n")
        subprocess.run(["git", "add", "."], cwd=str(tmp_path), capture_output=True)
        subprocess.run(["git", "commit", "-m", "init"], cwd=str(tmp_path), capture_output=True)

        result = verify_design_tokens(str(tmp_path))
        assert result["verified"]
        assert result["violation_count"] >= 1

    def test_skips_token_files(self, tmp_path):
        """Test that token/theme files are not flagged."""
        import subprocess
        subprocess.run(["git", "init"], cwd=str(tmp_path), capture_output=True)
        subprocess.run(["git", "config", "user.email", "test@test.com"], cwd=str(tmp_path), capture_output=True)
        subprocess.run(["git", "config", "user.name", "Test"], cwd=str(tmp_path), capture_output=True)

        token_file = tmp_path / "design-tokens.css"
        token_file.write_text(":root { --color-primary: #ff0000; }\n")
        subprocess.run(["git", "add", "."], cwd=str(tmp_path), capture_output=True)
        subprocess.run(["git", "commit", "-m", "init"], cwd=str(tmp_path), capture_output=True)

        result = verify_design_tokens(str(tmp_path))
        assert result["verified"]
        assert result["violation_count"] == 0


class TestVerifyDesignTokensTsx:
    def test_detects_hardcoded_colors_in_tsx(self, tmp_path):
        """Test detection of hardcoded colors in .tsx files."""
        import subprocess
        subprocess.run(["git", "init"], cwd=str(tmp_path), capture_output=True)
        subprocess.run(["git", "config", "user.email", "test@test.com"], cwd=str(tmp_path), capture_output=True)
        subprocess.run(["git", "config", "user.name", "Test"], cwd=str(tmp_path), capture_output=True)

        tsx_file = tmp_path / "Button.tsx"
        tsx_file.write_text('export const Button = () => <button style={{color: "#ff0000"}}>Click</button>\n')
        subprocess.run(["git", "add", "."], cwd=str(tmp_path), capture_output=True)
        subprocess.run(["git", "commit", "-m", "init"], cwd=str(tmp_path), capture_output=True)

        result = verify_design_tokens(str(tmp_path))
        assert result["verified"]
        assert result["violation_count"] >= 1

    def test_detects_hardcoded_spacing(self, tmp_path):
        """Test detection of hardcoded px spacing values."""
        import subprocess
        subprocess.run(["git", "init"], cwd=str(tmp_path), capture_output=True)
        subprocess.run(["git", "config", "user.email", "test@test.com"], cwd=str(tmp_path), capture_output=True)
        subprocess.run(["git", "config", "user.name", "Test"], cwd=str(tmp_path), capture_output=True)

        css_file = tmp_path / "layout.css"
        css_file.write_text(".container { margin: 16px; padding: 24px; }\n")
        subprocess.run(["git", "add", "."], cwd=str(tmp_path), capture_output=True)
        subprocess.run(["git", "commit", "-m", "init"], cwd=str(tmp_path), capture_output=True)

        result = verify_design_tokens(str(tmp_path))
        assert result["verified"]
        assert result["violation_count"] >= 1


class TestVerifyDesignBriefContent:
    def test_valid_brief(self, tmp_path):
        brief = tmp_path / "design-brief.md"
        brief.write_text(
            "# Design Brief\n## Color Palette\nprimary: #000\n"
            "## Typography\nfont: Inter\n## Spacing\nbase: 4px\n"
            "## Component Style\nbutton: rounded\n"
        )
        from harmony.orchestrator.verifier_frontend import verify_design_brief_content
        result = verify_design_brief_content(str(brief))
        assert result["valid"]

    def test_missing_sections(self, tmp_path):
        brief = tmp_path / "design-brief.md"
        brief.write_text("# Design Brief\n## Color Palette\nprimary: #000\n")
        from harmony.orchestrator.verifier_frontend import verify_design_brief_content
        result = verify_design_brief_content(str(brief))
        assert not result["valid"]
        assert len(result["missing_sections"]) > 0

    def test_file_not_found(self):
        from harmony.orchestrator.verifier_frontend import verify_design_brief_content
        result = verify_design_brief_content("/nonexistent/brief.md")
        assert not result["valid"]


class TestSafeCwd:
    def test_valid_directory(self, tmp_path):
        from harmony.orchestrator.verifier import _safe_cwd
        result = _safe_cwd(str(tmp_path))
        assert result  # Should not raise

    def test_nonexistent_directory(self):
        from harmony.orchestrator.verifier import _safe_cwd
        import pytest
        with pytest.raises(ValueError, match="Invalid cwd"):
            _safe_cwd("/nonexistent/path/xyz")

    def test_file_not_directory(self, tmp_path):
        from harmony.orchestrator.verifier import _safe_cwd
        import pytest
        f = tmp_path / "file.txt"
        f.write_text("x")
        with pytest.raises(ValueError, match="Invalid cwd"):
            _safe_cwd(str(f))


class TestVerifyBuildAndTests:
    """Tests for build/test/lint verification — uses mock subprocess."""

    def test_returns_empty_for_unknown_project(self, tmp_path):
        """Unknown project type returns empty dict."""
        import subprocess as sp
        sp.run(["git", "init"], cwd=str(tmp_path), capture_output=True)
        sp.run(["git", "config", "user.email", "t@t.com"], cwd=str(tmp_path), capture_output=True)
        sp.run(["git", "config", "user.name", "T"], cwd=str(tmp_path), capture_output=True)
        (tmp_path / "main.go").write_text("package main")
        sp.run(["git", "add", "."], cwd=str(tmp_path), capture_output=True)
        sp.run(["git", "commit", "-m", "init"], cwd=str(tmp_path), capture_output=True)
        from harmony.orchestrator.verifier_frontend import verify_build_and_tests
        result = verify_build_and_tests(str(tmp_path))
        assert result == {}

    def test_detects_python_project(self, tmp_path):
        """Python project with pyproject.toml is detected."""
        import subprocess as sp
        sp.run(["git", "init"], cwd=str(tmp_path), capture_output=True)
        sp.run(["git", "config", "user.email", "t@t.com"], cwd=str(tmp_path), capture_output=True)
        sp.run(["git", "config", "user.name", "T"], cwd=str(tmp_path), capture_output=True)
        (tmp_path / "pyproject.toml").write_text('[project]\nname="test"')
        (tmp_path / "app.py").write_text("x = 1\n")
        sp.run(["git", "add", "."], cwd=str(tmp_path), capture_output=True)
        sp.run(["git", "commit", "-m", "init"], cwd=str(tmp_path), capture_output=True)
        from harmony.orchestrator.verifier_frontend import verify_build_and_tests
        result = verify_build_and_tests(str(tmp_path))
        assert "build" in result  # At least detected the project type


class TestVerifyGoProject:
    """Tests for Go project detection and verification."""

    def test_detects_go_project(self, tmp_path):
        """Go project with go.mod is detected."""
        import subprocess as sp
        sp.run(["git", "init"], cwd=str(tmp_path), capture_output=True)
        sp.run(["git", "config", "user.email", "t@t.com"], cwd=str(tmp_path), capture_output=True)
        sp.run(["git", "config", "user.name", "T"], cwd=str(tmp_path), capture_output=True)
        (tmp_path / "go.mod").write_text("module example.com/test\n\ngo 1.21\n")
        (tmp_path / "main.go").write_text('package main\n\nfunc main() {}\n')
        sp.run(["git", "add", "."], cwd=str(tmp_path), capture_output=True)
        sp.run(["git", "commit", "-m", "init"], cwd=str(tmp_path), capture_output=True)
        from unittest.mock import patch
        from harmony.orchestrator.verifier_frontend import verify_build_and_tests
        call_log = []

        def mock_run_cmd(cmd, cwd=None, timeout=30):
            call_log.append(cmd)
            if cmd[:2] == ["go", "build"]:
                return (0, "")
            if cmd[:2] == ["go", "test"] and "-coverprofile=coverage.out" in cmd:
                return (0, "ok  \texample.com/test\tcoverage: 85.0% of statements\n")
            if cmd[:2] == ["go", "test"]:
                return (0, "ok  \texample.com/test\t0.010s\n")
            if cmd[0] == "golangci-lint":
                return (0, "")
            return (0, "")

        with patch("harmony.orchestrator.verifier_frontend.run_cmd", side_effect=mock_run_cmd):
            result = verify_build_and_tests(str(tmp_path))
        assert result["build"] is True
        assert result["tests"] is True
        assert result["lint"] is True
        assert result["test_coverage"] == 85.0

    def test_go_build_failure(self, tmp_path):
        """Go project with build failure."""
        import subprocess as sp
        sp.run(["git", "init"], cwd=str(tmp_path), capture_output=True)
        sp.run(["git", "config", "user.email", "t@t.com"], cwd=str(tmp_path), capture_output=True)
        sp.run(["git", "config", "user.name", "T"], cwd=str(tmp_path), capture_output=True)
        (tmp_path / "go.mod").write_text("module example.com/test\n\ngo 1.21\n")
        sp.run(["git", "add", "."], cwd=str(tmp_path), capture_output=True)
        sp.run(["git", "commit", "-m", "init"], cwd=str(tmp_path), capture_output=True)
        from unittest.mock import patch
        from harmony.orchestrator.verifier_frontend import verify_build_and_tests

        def mock_run_cmd(cmd, cwd=None, timeout=30):
            if cmd[:2] == ["go", "build"]:
                return (1, "build error")
            if cmd[:2] == ["go", "test"] and "-coverprofile=coverage.out" in cmd:
                return (1, "")
            if cmd[:2] == ["go", "test"]:
                return (0, "ok")
            if cmd[0] == "golangci-lint":
                return (-1, "not found")  # not installed
            return (0, "")

        with patch("harmony.orchestrator.verifier_frontend.run_cmd", side_effect=mock_run_cmd):
            result = verify_build_and_tests(str(tmp_path))
        assert result["build"] is False
        assert result["tests"] is True
        assert "lint" not in result  # golangci-lint not available

    def test_go_no_coverage_parsed_when_tests_fail(self, tmp_path):
        """Coverage not parsed when go test with coverage fails."""
        import subprocess as sp
        sp.run(["git", "init"], cwd=str(tmp_path), capture_output=True)
        sp.run(["git", "config", "user.email", "t@t.com"], cwd=str(tmp_path), capture_output=True)
        sp.run(["git", "config", "user.name", "T"], cwd=str(tmp_path), capture_output=True)
        (tmp_path / "go.mod").write_text("module example.com/test\n\ngo 1.21\n")
        sp.run(["git", "add", "."], cwd=str(tmp_path), capture_output=True)
        sp.run(["git", "commit", "-m", "init"], cwd=str(tmp_path), capture_output=True)
        from unittest.mock import patch
        from harmony.orchestrator.verifier_frontend import verify_build_and_tests

        def mock_run_cmd(cmd, cwd=None, timeout=30):
            if cmd[:2] == ["go", "build"]:
                return (0, "")
            if cmd[:2] == ["go", "test"] and "-coverprofile=coverage.out" in cmd:
                return (1, "FAIL")
            if cmd[:2] == ["go", "test"]:
                return (1, "FAIL")
            if cmd[0] == "golangci-lint":
                return (-1, "not found")
            return (0, "")

        with patch("harmony.orchestrator.verifier_frontend.run_cmd", side_effect=mock_run_cmd):
            result = verify_build_and_tests(str(tmp_path))
        assert result["build"] is True
        assert result["tests"] is False
        assert "test_coverage" not in result


class TestVerifyRustProject:
    """Tests for Rust project detection and verification."""

    def test_detects_rust_project(self, tmp_path):
        """Rust project with Cargo.toml is detected."""
        import subprocess as sp
        sp.run(["git", "init"], cwd=str(tmp_path), capture_output=True)
        sp.run(["git", "config", "user.email", "t@t.com"], cwd=str(tmp_path), capture_output=True)
        sp.run(["git", "config", "user.name", "T"], cwd=str(tmp_path), capture_output=True)
        (tmp_path / "Cargo.toml").write_text('[package]\nname = "test"\nversion = "0.1.0"\n')
        (tmp_path / "src").mkdir()
        (tmp_path / "src" / "main.rs").write_text("fn main() {}\n")
        sp.run(["git", "add", "."], cwd=str(tmp_path), capture_output=True)
        sp.run(["git", "commit", "-m", "init"], cwd=str(tmp_path), capture_output=True)
        from unittest.mock import patch
        from harmony.orchestrator.verifier_frontend import verify_build_and_tests

        def mock_run_cmd(cmd, cwd=None, timeout=30):
            if cmd[:2] == ["cargo", "build"]:
                return (0, "")
            if cmd[:2] == ["cargo", "test"]:
                return (0, "test result: ok. 5 passed; 0 failed\n")
            if cmd[:2] == ["cargo", "clippy"]:
                return (0, "")
            return (0, "")

        with patch("harmony.orchestrator.verifier_frontend.run_cmd", side_effect=mock_run_cmd):
            result = verify_build_and_tests(str(tmp_path))
        assert result["build"] is True
        assert result["tests"] is True
        assert result["lint"] is True
        # Rust coverage is intentionally omitted
        assert "test_coverage" not in result

    def test_rust_clippy_not_installed(self, tmp_path):
        """Lint is omitted when clippy is not available."""
        import subprocess as sp
        sp.run(["git", "init"], cwd=str(tmp_path), capture_output=True)
        sp.run(["git", "config", "user.email", "t@t.com"], cwd=str(tmp_path), capture_output=True)
        sp.run(["git", "config", "user.name", "T"], cwd=str(tmp_path), capture_output=True)
        (tmp_path / "Cargo.toml").write_text('[package]\nname = "test"\nversion = "0.1.0"\n')
        sp.run(["git", "add", "."], cwd=str(tmp_path), capture_output=True)
        sp.run(["git", "commit", "-m", "init"], cwd=str(tmp_path), capture_output=True)
        from unittest.mock import patch
        from harmony.orchestrator.verifier_frontend import verify_build_and_tests

        def mock_run_cmd(cmd, cwd=None, timeout=30):
            if cmd[:2] == ["cargo", "build"]:
                return (0, "")
            if cmd[:2] == ["cargo", "test"]:
                return (0, "ok")
            if cmd[:2] == ["cargo", "clippy"]:
                return (-1, "not found")
            return (0, "")

        with patch("harmony.orchestrator.verifier_frontend.run_cmd", side_effect=mock_run_cmd):
            result = verify_build_and_tests(str(tmp_path))
        assert result["build"] is True
        assert result["tests"] is True
        assert "lint" not in result

    def test_rust_build_failure(self, tmp_path):
        """Rust project with build failure."""
        import subprocess as sp
        sp.run(["git", "init"], cwd=str(tmp_path), capture_output=True)
        sp.run(["git", "config", "user.email", "t@t.com"], cwd=str(tmp_path), capture_output=True)
        sp.run(["git", "config", "user.name", "T"], cwd=str(tmp_path), capture_output=True)
        (tmp_path / "Cargo.toml").write_text('[package]\nname = "test"\nversion = "0.1.0"\n')
        sp.run(["git", "add", "."], cwd=str(tmp_path), capture_output=True)
        sp.run(["git", "commit", "-m", "init"], cwd=str(tmp_path), capture_output=True)
        from unittest.mock import patch
        from harmony.orchestrator.verifier_frontend import verify_build_and_tests

        def mock_run_cmd(cmd, cwd=None, timeout=30):
            if cmd[:2] == ["cargo", "build"]:
                return (1, "error[E0308]: mismatched types")
            if cmd[:2] == ["cargo", "test"]:
                return (1, "FAILED")
            if cmd[:2] == ["cargo", "clippy"]:
                return (1, "warnings")
            return (0, "")

        with patch("harmony.orchestrator.verifier_frontend.run_cmd", side_effect=mock_run_cmd):
            result = verify_build_and_tests(str(tmp_path))
        assert result["build"] is False
        assert result["tests"] is False
        assert result["lint"] is False


class TestVerifyJavaProject:
    """Tests for Java project detection and verification."""

    def test_detects_maven_project(self, tmp_path):
        """Java project with pom.xml is detected and uses Maven."""
        import subprocess as sp
        sp.run(["git", "init"], cwd=str(tmp_path), capture_output=True)
        sp.run(["git", "config", "user.email", "t@t.com"], cwd=str(tmp_path), capture_output=True)
        sp.run(["git", "config", "user.name", "T"], cwd=str(tmp_path), capture_output=True)
        (tmp_path / "pom.xml").write_text('<project></project>')
        sp.run(["git", "add", "."], cwd=str(tmp_path), capture_output=True)
        sp.run(["git", "commit", "-m", "init"], cwd=str(tmp_path), capture_output=True)
        from unittest.mock import patch
        from harmony.orchestrator.verifier_frontend import verify_build_and_tests
        call_log = []

        def mock_run_cmd(cmd, cwd=None, timeout=30):
            call_log.append(cmd)
            if cmd[:2] == ["mvn", "compile"]:
                return (0, "BUILD SUCCESS")
            if cmd[:2] == ["mvn", "test"]:
                return (0, "BUILD SUCCESS")
            return (0, "")

        with patch("harmony.orchestrator.verifier_frontend.run_cmd", side_effect=mock_run_cmd):
            result = verify_build_and_tests(str(tmp_path))
        assert result["build"] is True
        assert result["tests"] is True
        # Lint and coverage intentionally omitted for Java
        assert "lint" not in result
        assert "test_coverage" not in result
        # Verify Maven commands were used, not Gradle
        assert any(c[0] == "mvn" for c in call_log)

    def test_detects_gradle_project(self, tmp_path):
        """Java project with build.gradle is detected and uses Gradle."""
        import subprocess as sp
        sp.run(["git", "init"], cwd=str(tmp_path), capture_output=True)
        sp.run(["git", "config", "user.email", "t@t.com"], cwd=str(tmp_path), capture_output=True)
        sp.run(["git", "config", "user.name", "T"], cwd=str(tmp_path), capture_output=True)
        (tmp_path / "build.gradle").write_text("apply plugin: 'java'\n")
        sp.run(["git", "add", "."], cwd=str(tmp_path), capture_output=True)
        sp.run(["git", "commit", "-m", "init"], cwd=str(tmp_path), capture_output=True)
        from unittest.mock import patch
        from harmony.orchestrator.verifier_frontend import verify_build_and_tests
        call_log = []

        def mock_run_cmd(cmd, cwd=None, timeout=30):
            call_log.append(cmd)
            if cmd[:2] == ["gradle", "build"]:
                return (0, "BUILD SUCCESSFUL")
            if cmd[:2] == ["gradle", "test"]:
                return (0, "BUILD SUCCESSFUL")
            return (0, "")

        with patch("harmony.orchestrator.verifier_frontend.run_cmd", side_effect=mock_run_cmd):
            result = verify_build_and_tests(str(tmp_path))
        assert result["build"] is True
        assert result["tests"] is True
        # Verify Gradle commands were used, not Maven
        assert any(c[0] == "gradle" for c in call_log)
        assert not any(c[0] == "mvn" for c in call_log)

    def test_detects_gradle_kts_project(self, tmp_path):
        """Java/Kotlin project with build.gradle.kts is detected and uses Gradle."""
        import subprocess as sp
        sp.run(["git", "init"], cwd=str(tmp_path), capture_output=True)
        sp.run(["git", "config", "user.email", "t@t.com"], cwd=str(tmp_path), capture_output=True)
        sp.run(["git", "config", "user.name", "T"], cwd=str(tmp_path), capture_output=True)
        (tmp_path / "build.gradle.kts").write_text('plugins { java }\n')
        sp.run(["git", "add", "."], cwd=str(tmp_path), capture_output=True)
        sp.run(["git", "commit", "-m", "init"], cwd=str(tmp_path), capture_output=True)
        from unittest.mock import patch
        from harmony.orchestrator.verifier_frontend import verify_build_and_tests

        def mock_run_cmd(cmd, cwd=None, timeout=30):
            if cmd[:2] == ["gradle", "build"]:
                return (0, "BUILD SUCCESSFUL")
            if cmd[:2] == ["gradle", "test"]:
                return (0, "BUILD SUCCESSFUL")
            return (0, "")

        with patch("harmony.orchestrator.verifier_frontend.run_cmd", side_effect=mock_run_cmd):
            result = verify_build_and_tests(str(tmp_path))
        assert result["build"] is True
        assert result["tests"] is True

    def test_maven_build_failure(self, tmp_path):
        """Maven project with build failure."""
        import subprocess as sp
        sp.run(["git", "init"], cwd=str(tmp_path), capture_output=True)
        sp.run(["git", "config", "user.email", "t@t.com"], cwd=str(tmp_path), capture_output=True)
        sp.run(["git", "config", "user.name", "T"], cwd=str(tmp_path), capture_output=True)
        (tmp_path / "pom.xml").write_text('<project></project>')
        sp.run(["git", "add", "."], cwd=str(tmp_path), capture_output=True)
        sp.run(["git", "commit", "-m", "init"], cwd=str(tmp_path), capture_output=True)
        from unittest.mock import patch
        from harmony.orchestrator.verifier_frontend import verify_build_and_tests

        def mock_run_cmd(cmd, cwd=None, timeout=30):
            if cmd[:2] == ["mvn", "compile"]:
                return (1, "BUILD FAILURE")
            if cmd[:2] == ["mvn", "test"]:
                return (1, "BUILD FAILURE")
            return (0, "")

        with patch("harmony.orchestrator.verifier_frontend.run_cmd", side_effect=mock_run_cmd):
            result = verify_build_and_tests(str(tmp_path))
        assert result["build"] is False
        assert result["tests"] is False


class TestProjectDetectionPriority:
    """Tests to verify correct project type detection ordering."""

    def test_go_not_detected_without_go_mod(self, tmp_path):
        """A directory with .go files but no go.mod is not detected as Go."""
        import subprocess as sp
        sp.run(["git", "init"], cwd=str(tmp_path), capture_output=True)
        sp.run(["git", "config", "user.email", "t@t.com"], cwd=str(tmp_path), capture_output=True)
        sp.run(["git", "config", "user.name", "T"], cwd=str(tmp_path), capture_output=True)
        (tmp_path / "main.go").write_text("package main")
        sp.run(["git", "add", "."], cwd=str(tmp_path), capture_output=True)
        sp.run(["git", "commit", "-m", "init"], cwd=str(tmp_path), capture_output=True)
        from harmony.orchestrator.verifier_frontend import verify_build_and_tests
        result = verify_build_and_tests(str(tmp_path))
        assert result == {}

    def test_python_takes_priority_over_go(self, tmp_path):
        """When both pyproject.toml and go.mod exist, Python is chosen."""
        import subprocess as sp
        sp.run(["git", "init"], cwd=str(tmp_path), capture_output=True)
        sp.run(["git", "config", "user.email", "t@t.com"], cwd=str(tmp_path), capture_output=True)
        sp.run(["git", "config", "user.name", "T"], cwd=str(tmp_path), capture_output=True)
        (tmp_path / "pyproject.toml").write_text('[project]\nname="test"')
        (tmp_path / "go.mod").write_text("module test\n\ngo 1.21\n")
        (tmp_path / "app.py").write_text("x = 1\n")
        sp.run(["git", "add", "."], cwd=str(tmp_path), capture_output=True)
        sp.run(["git", "commit", "-m", "init"], cwd=str(tmp_path), capture_output=True)
        from harmony.orchestrator.verifier_frontend import verify_build_and_tests
        result = verify_build_and_tests(str(tmp_path))
        # Python project detected — should have "build" key from Python verifier
        assert "build" in result


class TestCrossVerifyQualityScores:
    def test_mismatches_detected(self, tmp_path):
        """File size mismatch is detected."""
        import subprocess as sp
        sp.run(["git", "init"], cwd=str(tmp_path), capture_output=True)
        sp.run(["git", "config", "user.email", "t@t.com"], cwd=str(tmp_path), capture_output=True)
        sp.run(["git", "config", "user.name", "T"], cwd=str(tmp_path), capture_output=True)
        # Create a 50-line file
        big_file = tmp_path / "big.py"
        big_file.write_text("\n".join([f"x_{i} = {i}" for i in range(50)]) + "\n")
        sp.run(["git", "add", "."], cwd=str(tmp_path), capture_output=True)
        sp.run(["git", "commit", "-m", "init"], cwd=str(tmp_path), capture_output=True)
        from harmony.orchestrator.verifier_frontend import cross_verify_quality_scores
        # Agent claims max_file_lines is 10 but actual is 50
        result = cross_verify_quality_scores({"max_file_lines": 10}, cwd=str(tmp_path))
        assert not result["verified"]
        assert "max_file_lines" in result["mismatches"]

    def test_no_mismatches_when_accurate(self, tmp_path):
        """No mismatches when reported scores are accurate."""
        import subprocess as sp
        sp.run(["git", "init"], cwd=str(tmp_path), capture_output=True)
        sp.run(["git", "config", "user.email", "t@t.com"], cwd=str(tmp_path), capture_output=True)
        sp.run(["git", "config", "user.name", "T"], cwd=str(tmp_path), capture_output=True)
        small_file = tmp_path / "small.py"
        small_file.write_text("x = 1\ny = 2\n")
        sp.run(["git", "add", "."], cwd=str(tmp_path), capture_output=True)
        sp.run(["git", "commit", "-m", "init"], cwd=str(tmp_path), capture_output=True)
        from harmony.orchestrator.verifier_frontend import cross_verify_quality_scores
        result = cross_verify_quality_scores({"max_file_lines": 2}, cwd=str(tmp_path))
        assert result["verified"]


# ---------------------------------------------------------------------------
# Design document verification
# ---------------------------------------------------------------------------

def _build_good_design_doc(task_id: str = "2") -> str:
    """Build a design doc that passes all quality checks."""
    lines = [
        f"# Task {task_id}: Feature X — Design Document\n",
        "## 1. Overview\n",
        "Feature description here with enough detail.",
        "Dependencies on previous tasks.",
        "High-level flow description.",
        "",
        "### Data Flow",
        "```",
        "Input -> Process -> Output",
        "```\n",
        "## 2. API Design\n",
        "### Endpoints",
        "- GET /api/v1/items — list items",
        "- POST /api/v1/items — create item",
        "```json",
        '{"id": "string", "title": "string"}',
        "```\n",
        "## 3. Data Model\n",
        "```sql",
        "CREATE TABLE items (id SERIAL PRIMARY KEY, title TEXT);",
        "```\n",
        "## 4. Implementation File List\n",
        f"- Subtask {task_id}.1: src/routes/items.py",
        f"- Subtask {task_id}.2: src/models/items.py",
        f"- Subtask {task_id}.3: tests/test_items.py\n",
        "## 5. Key Decisions\n",
        "- Use PostgreSQL for JSONB support",
        "- REST over GraphQL for simplicity\n",
        "## 6. Build Sequence\n",
        "1. Data model first",
        "2. API routes",
        "3. Tests",
    ]
    # Pad to exceed minimum line count
    lines.extend([f"# Detail line {i}" for i in range(50)])
    return "\n".join(lines)


class TestVerifyDesignDoc:
    def test_no_tasks_dir(self, tmp_path):
        result = verify_design_doc("1", cwd=str(tmp_path))
        assert not result["valid"]
        assert not result["exists"]

    def test_no_doc_found(self, tmp_path):
        (tmp_path / "docs" / "tasks").mkdir(parents=True)
        result = verify_design_doc("99", cwd=str(tmp_path))
        assert not result["valid"]
        assert not result["exists"]

    def test_good_design_doc_passes(self, tmp_path):
        tasks_dir = tmp_path / "docs" / "tasks"
        tasks_dir.mkdir(parents=True)
        doc = tasks_dir / "abc-2-feature-x-plan.md"
        doc.write_text(_build_good_design_doc("2"))
        result = verify_design_doc("2", cwd=str(tmp_path))
        assert result["valid"], f"Issues: {result.get('issues')}"
        assert result["exists"]
        assert result["line_count"] >= 80

    def test_too_short_fails(self, tmp_path):
        tasks_dir = tmp_path / "docs" / "tasks"
        tasks_dir.mkdir(parents=True)
        doc = tasks_dir / "abc-3-short-plan.md"
        doc.write_text("# Task 3\n\nToo short.\n")
        result = verify_design_doc("3", cwd=str(tmp_path))
        assert not result["valid"]
        assert any("minimum" in i.lower() for i in result["issues"])

    def test_missing_required_sections(self, tmp_path):
        tasks_dir = tmp_path / "docs" / "tasks"
        tasks_dir.mkdir(parents=True)
        doc = tasks_dir / "abc-4-missing-plan.md"
        # Long enough but missing required sections
        content = "# Task 4\n\n" + "\n".join([f"Line {i}" for i in range(100)])
        doc.write_text(content)
        result = verify_design_doc("4", cwd=str(tmp_path))
        assert not result["valid"]
        assert any("Overview" in i for i in result["issues"])

    def test_no_code_blocks_fails(self, tmp_path):
        tasks_dir = tmp_path / "docs" / "tasks"
        tasks_dir.mkdir(parents=True)
        # Has sections but no code blocks
        content = (
            "# Task 5 Design\n\n## 1. Overview\nDesc\n\n"
            "## Implementation File List\nfiles\n\n"
            "## Build Sequence\nsteps\n\n"
            "## API Design\nendpoints\n\n"
        ) + "\n".join([f"Detail {i}" for i in range(80)])
        doc = tasks_dir / "abc-5-no-code-plan.md"
        doc.write_text(content)
        result = verify_design_doc("5", cwd=str(tmp_path))
        assert not result["valid"]
        assert any("code block" in i.lower() for i in result["issues"])
