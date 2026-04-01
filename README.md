# Agent Harmony

**One trigger, production-grade output.** You describe what to build. Agent Harmony orchestrates the entire development process — from PRD to tested, reviewed, audited code.

[한국어 README](README.ko.md)

> **What this is**: A development process orchestrator for Claude Code. It doesn't generate code — Claude does that. Agent Harmony ensures every piece of code goes through design, implementation, self-review, quality gate, and production audit before it's considered done.

> **What this is NOT**: An AI coding tool. It's a quality and process layer on top of one.

## How It Works

```
You: /agent-harmony:run I want to build a SaaS that analyzes code quality

Agent Harmony:
  1. Deep interview — asks clarifying questions → generates a complete PRD
  2. Auto-setup — creates specialized agent team, reference docs, tasks
  3. Multi-pass build — each task goes through:
     design → implement → self-review → quality gate → production audit → fix
  4. Production-grade codebase, tested and reviewed
```

## Why This Exists

When you use Claude Code alone, the loop is: **write code → done**. One pass. No review.

When a human reviews, the loop is: **write → review → "fix this" → rewrite → review → done**. Multiple passes. Much higher quality.

Agent Harmony automates the human review loop:

| Approach | Passes | Quality |
|----------|--------|---------|
| Claude Code alone | 1 | Works, but fragile |
| Claude Code + human review | 3-5 | Production-grade |
| **Claude Code + Agent Harmony** | **5** | **Production-grade, no human needed** |

```
For each task:
  1. Team designs → agents implement in isolated worktrees
  2. Each agent self-reviews before reporting done
  3. Review agent checks against quality criteria
  4. Quality gate: build + test + lint (deterministic)
  5. Production audit: fresh agent reviews like a senior engineer
  6. Issues found? → fix → re-audit (max 2 rounds)
```

## Quick Start

```bash
# Add marketplace & install plugin
/plugin marketplace add hohre12/jwbae-plugins
/plugin install agent-harmony@jwbae-plugins

# Build something
/agent-harmony:run a todo app with authentication and team collaboration
```

That's it. One command.

## The Pipeline

```
Phase 1: Conversation → PRD
  User describes idea → deep interview (multiple choice + AI recommendations)
  → comprehensive PRD generated

Phase 2: Environment Setup (automatic)
  /project-init → /generate-agents → /build-refs → task generation
  → agent team, reference docs, task list ready

Phase 3: Build with Multi-Pass Quality (automatic)
  For each task:
    /team-executor → quality gate → production audit → fix if needed
  → all tasks pass quality checks

Phase 4: Delivery
  → production-ready project with passing tests
```

## What Gets Generated

```
{project}/
├── docs/
│   ├── prd.md                        # Comprehensive PRD from conversation
│   ├── refs/                         # Domain reference docs per agent
│   └── tasks/                        # Design docs per task
├── .claude/
│   ├── agents/                       # Project-specific agent team
│   ├── skills/
│   │   └── team-executor/SKILL.md    # Task execution skill
│   └── settings.local.json           # Team features enabled
├── .harmony/
│   └── state.json                    # Pipeline state + tasks (auto-managed)
├── CLAUDE.md                         # Project rules and conventions
└── README.md                         # Project documentation
```

## Multi-Pass Quality System

Each task goes through 5 quality layers:

| Layer | Type | What It Catches |
|-------|------|----------------|
| **Self-Review** | Per agent | Missing requirements, dead code, untested functions |
| **Code Review** | Review agent | Integration issues, security holes, error handling gaps |
| **Quality Gate** | Deterministic | Build failures, test failures, lint violations, oversized files |
| **Production Audit** | Fresh agent | PRD compliance, edge cases, UX issues |
| **Fix Loop** | Iterative | Persistent issues → escalation to user (no auto-pass) |

### Deterministic Quality Thresholds

The quality gate runs actual tools and enforces numeric thresholds. Tasks **cannot pass** unless ALL metrics meet the criteria:

| Metric | Threshold | How It's Measured |
|--------|-----------|-------------------|
| Build | Must pass | Project build command |
| Tests | Must pass | Full test suite |
| Lint | Zero errors | Project linter |
| Test coverage | >= 60% | pytest --cov / jest --coverage |
| Max file lines | <= 500 | wc -l on source files |
| Max function lines | <= 80 | Line count of largest function |
| Security (critical) | 0 | bandit / npm audit + secret grep |

No auto-pass after N rounds. If thresholds can't be met, the pipeline escalates to the user.

## Recommended Plugins

Agent Harmony works best with these companion plugins:

| Plugin | Purpose |
|--------|---------|
| `frontend-design` | Professional UI design direction — prevents "AI slop" aesthetic |

```bash
/plugin install frontend-design@claude-plugins-official
```

Agent Harmony will suggest installing missing plugins when relevant.

## Best Fit

| Works Well | Why |
|-----------|-----|
| CRUD web apps (Next.js, FastAPI) | Predictable structure, clear agent roles |
| CLI tools | Simple structure, few agents needed |
| API servers | Standard patterns, testable |
| SaaS MVPs | Interview captures requirements well |

| Less Ideal | Why |
|-----------|-----|
| Large existing codebases | Hard to capture all implicit dependencies |
| Mobile apps (React Native) | Complex build/test pipelines |
| ML/data pipelines | Experimental workflow vs linear tasks |
| Real-time systems | Integration testing is hard to automate |

## Session Resilience

Development survives interruptions:

```bash
# Session crashes or rate limit hit
# Just run /agent-harmony:run again — it detects saved state
/agent-harmony:run
# → "Resume from task 15/23? (a) Resume (b) Start over"
```

## Commands

### The One Command

| Command | Description |
|---------|-------------|
| `/agent-harmony:run [description]` | **One prompt to production.** Conversation → PRD → setup → build → deliver |

### Pipeline Commands (used by /agent-harmony:run internally, also available individually)

| Command | Description |
|---------|-------------|
| `/project-init` | Initialize new project structure |
| `/codebase-init` | Initialize from existing codebase |
| `/generate-agents` | Create project-specific agent team |
| `/build-refs` | Generate domain reference docs |

## Architecture

```
Global Agents (part of this plugin):
└── expert-agent           Analyzes PRD → creates project-specific agent team

Per-Project Team (created by expert-agent):
├── architect-agent        System design & team orchestration
├── backend-agent          Backend implementation
├── frontend-agent         Frontend implementation
├── review-agent           Code review & quality verification
└── ...                    (varies by project)

The expert-agent creates the team.
The team designs, implements, and reviews collaboratively.
Multi-pass quality ensures everything is production-grade.
```

## Installation

```bash
# Install as Claude Code plugin
/plugin install agent-harmony@jwbae-plugins

# Or manually
git clone https://github.com/hohre12/agent-harmony ~/.claude/plugins/agent-harmony
```

No `pip install` needed. Python runtime bootstraps automatically on first use.

## Requirements

- Claude Code CLI (Max Plan or API key)
- Python 3.10+ (runtime engine — venv auto-bootstrapped)
- git (branch management, worktrees)
- macOS or Linux (Windows via WSL)
- Optional: tmux (for split-pane agent view — works without it)

## License

Open source. MIT License.

## Version

4.0.0
