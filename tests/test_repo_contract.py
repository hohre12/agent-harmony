from __future__ import annotations

import json
import re
from pathlib import Path

import harmony


ROOT = Path(__file__).resolve().parents[1]


def _read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


class TestVersioning:
    def test_versions_aligned_to_current_release(self):
        pyproject = _read("pyproject.toml")
        plugin = json.loads(_read(".claude-plugin/plugin.json"))
        changelog = _read("CHANGELOG.md")

        pyproject_version = re.search(r'^version\s*=\s*"([^"]+)"', pyproject, re.MULTILINE)
        assert pyproject_version is not None
        assert pyproject_version.group(1) == "1.0.3"
        assert plugin["version"] == "1.0.3"
        assert harmony.__version__ == "1.0.3"
        assert "## [1.0.3]" in changelog


class TestPublicDocs:
    def test_readme_shows_marketplace_install_path(self):
        readme = _read("README.md")
        assert "/plugin marketplace add" in readme
        assert "/plugin install agent-harmony@jwbae-plugins" in readme

    def test_readme_shows_both_command_examples(self):
        readme = _read("README.md")
        assert "/agent-harmony:harmony" in readme
        assert "/harmony" in readme

    def test_readme_mentions_manual_override_for_cost_control(self):
        readme = _read("README.md")
        assert "자동 재시도" in readme or "automatic retries" in readme.lower()
        assert "수동 인수" in readme or "manual override" in readme.lower() or "manual takeover" in readme.lower()

    def test_changelog_mentions_prd_prompt_exception(self):
        changelog = _read("CHANGELOG.md")
        assert "PRD" in changelog
        assert "50 lines" in changelog or "50줄" in changelog
        assert "exception" in changelog.lower() or "예외" in changelog
