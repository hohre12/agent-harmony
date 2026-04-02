"""Tests for server-side verification module."""

import json
import os
import tempfile
from pathlib import Path

import pytest

from harmony.orchestrator.verifier import (
    run_cmd,
    verify_build_evidence,
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


class TestVerifyPrdSections:
    def test_valid_prd(self, tmp_path):
        prd = tmp_path / "prd.md"
        prd.write_text(
            "# Project\n## Overview\nStuff\n## Problem Statement\nStuff\n"
            "## Target Users\nStuff\n## Core Features\nStuff\n"
            "## Technical Architecture\nStuff\n## Data Model\nStuff\n## API Design\nStuff\n"
        )
        result = verify_prd_sections(str(prd))
        assert result["exists"]
        assert result["valid"]
        assert result["missing_sections"] == []

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
