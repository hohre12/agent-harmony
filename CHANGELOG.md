# Changelog

All notable changes to Agent Harmony will be documented in this file.

## [1.0.5] - 2026-04-03

### Added

- **3-phase team execution enforcement** — build_task split into build_team_setup → build_team_execute → build_team_merge
  - Phase 1: Server verifies design doc written by architect agents
  - Phase 2: Server verifies worktree branches exist (proof of agent spawning)
  - Phase 3: Server verifies build evidence after review and merge
  - Main session is structurally enforced as orchestrator — cannot bypass agent spawning
- **Worktree branch verification** (`verify_team_execution`) — checks git branches matching `feature/{tag}-{task_id}*/wt-*`
- **Orchestrator role notice** — every build prompt explicitly states main session must not write code directly
- **Design philosophy document** (`docs/DESIGN_PHILOSOPHY.md`) — trust problem, harness engineering principles, 7 core design principles

### Fixed

- Substring false positive in branch matching (`wt-1` incorrectly matching `wt-11`) — now uses segment-based matching
- `lstrip("* ")` replaced with `removeprefix("* ")` for correct branch name parsing
- Git command failure in `verify_team_execution` now returns explicit error instead of misleading "no branches"
- `_handle_team_merge` missing task validation — added `_safe_get_task` call
- Stale step names in unrecognized-step warning — added 3 new phase names
- `_lang_framework_block` missing "Do NOT use Vanilla HTML/CSS/JS" constraint
- `build_task` inline code duplication — now uses shared `_subtask_block`/`_team_block` helpers
- Harness engineering attribution — credited to Martin Fowler/OpenAI, not self-coined

### Changed

- README (EN/KO) revamped — problem-first framing, build loop diagrams, 3-tier quality gate tables

## [1.0.4] - 2026-04-03

### Added

- **Project-context-aware production audit** — audit agent reads PRD + refs + CLAUDE.md before reviewing
  - 9 audit categories (A-I): Bugs, Code Quality, Architecture, Business Logic, Database, API, Frontend/UX, Tests, Performance
  - Categories auto-skipped when not applicable to the project
  - Per-category verdict required, not just overall PASS/FAIL
  - Domain-specific checks: state machine transitions, schema quality, UX flow for target user
- **Auto-detect project linter** — server prefers ruff over flake8, npm run lint over eslint
- **Server-detected violations mandatory** — audit agent must address each or explain why false positive

### Fixed

- Lint verification always ran flake8 even when project uses ruff (caused 5+ retry loops)

## [1.0.3] - 2026-04-03

### Added

- **Frontend framework interview question** — asks user to choose React/Vue/Svelte/Vanilla/etc. for projects with a frontend
- Answer flows through PRD generation and build prompts so agents use the chosen framework

### Fixed

- `from __future__ import annotations` false positive in unused import checker (was 18 false positives per project)
- Quality thresholds not refreshed on session resume (stale values from older plugin versions persisted)
- Design token checker scanned entire repo instead of changed files only (caused 204 false positives)
- Design token checker flagged `var()` lines and CSS custom property definitions as violations
- `frontend_framework` answer collected but never passed to PRD generation or build prompts

## [1.0.2] - 2026-04-02

### Added

- **Server-side code quality verifiers** — 5 new checks that agents cannot self-report:
  - Magic numbers: AST-based (Python), regex (JS/TS) detection of numeric literals that should be constants
  - Duplicate code: sliding-window hash detection of 4+ line repeated blocks across files
  - Unused imports: AST (Python), regex (JS/TS) with noqa/star/__all__/__init__ handling
  - N+1 query patterns: loop+query detection for Python ORM and JS/TS await patterns
  - Hardcoded strings: cross-file repeated string literal detection (3+ occurrences)
- **Comprehensive review criteria** — audit/review/self-review now check: logic bugs, DRY violations, magic numbers, common components, naming, N+1 queries, performance, test quality
- **CLAUDE.md user choice** — existing CLAUDE.md detected → user picks: keep+append / replace / skip
- **Permission mode notice** — Shift+Tab reminder in skill completion reports and README

### Changed

- Production quality thresholds: max_file_lines 300→350, max_function_lines 40→50 (prevents over-fragmentation)
- README EN/KO: rewritten with harness engineering narrative, strong first impression
- `/harmony` shorthand documented alongside `/agent-harmony:harmony`

## [1.0.1] - 2026-04-01

### Architecture

- **Python orchestrator replaces long prompts** — Pipeline logic moved from 450-line SKILL.md to Python state machine. Most operating prompts stay short (< 50 lines each), while PRD generation remains intentionally longer as an exception.
- **New MCP tools**: `harmony_pipeline_start`, `harmony_pipeline_next`, `harmony_pipeline_respond`, `harmony_generate_template`
- **Template generator** — team-executor SKILL.md generated by Python code instead of agent copying a 330-line template

### Removed

- **3-layer methodology as a standalone subsystem** — Replaced by a Python-orchestrated multi-pass quality loop
- Removed agents: `ontology-architect`, `harness-engineer`, `loop-designer`
- Removed skill: `/apply-3layers`
- Removed runtime modules: ontology, metrics, harness, drift, codegen, hooks, verify, harden, design
- Removed skills: `/generate-prd`, `/opencode-export`, `/restructure-tasks`, `/update-readme`
- Removed `cli.py` (duplicate of MCP server)

### Added

- **Harness-engineered development loop** — Per-task build → quality gate → production audit → fix loop, followed by project-level verification and hardening
- **Multi-pass quality system** — Each task goes through: implement → self-review → quality gate → production audit → fix loop
- **Self-review requirement** — Implementation agents must review their own code before reporting completion
- **Production audit** — Fresh agent reviews each task against PRD, error handling, security, edge cases
- **Memory consolidation** — Auto-cleanup when entries exceed 100 per agent
- **Pipeline state machine** (`pipeline.py`) — Manages full pipeline: interview → PRD → setup → build → delivery
- **Prompt module** (`prompts.py`) — All step prompts as Python functions, each under 50 lines
- **Template module** (`templates.py`) — Generates team-executor SKILL.md from configuration

### Changed

- Plugin structure: `commands/*.md` → `skills/*/SKILL.md` (Claude Code standard)
- `harmony/SKILL.md`: 450 lines → 25 lines (thin entry point)
- Task generation: moved from separate skill to pipeline (Python orchestrator generates tasks directly)
- MCP tools: 25 → 13 (removed 3-layer tools, added pipeline tools)
- `bypassPermissions` removed from agent files; kept in project settings with explicit manual override checkpoints for cost control, where the user can end Harmony's automatic loop and take responsibility for the result
- Language: hardcoded Korean → auto-detect from user's initial prompt
- Max global cycles: 5 → 10 (configurable)
- `.mcp.json` paths use `${CLAUDE_PLUGIN_ROOT}` for plugin compatibility
- Public distribution docs now consistently use marketplace → plugin install as the supported path
- README examples now show both `/agent-harmony:harmony` and `/harmony`

### Fixed

- Version mismatch between pyproject.toml and plugin.json (both 1.0.1)
- Removed `click` dependency (cli.py deleted)
- Clarified that PRD generation is the deliberate long-prompt exception to the short-prompt rule

## [3.0.0] - 2026-03-15

### Initial Release

- 3-layer methodology (ontology, harness, quality gate)
- Phase-based development loop (3A build → 3B verify → 3C harden → 3D final gate)
- Session state management with crash recovery
- Agent memory system
- MCP server with 25 tools
