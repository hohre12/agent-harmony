# Agent Harmony

### The AI that writes your code shouldn't be the one reviewing it.

Claude Code writes code in one pass — no review, no audit, no quality gate. It works. But would you ship code that no one else has looked at?

**Harmony adds what's missing: independent review, server-verified quality gates, and a full development pipeline — from requirements to production.**

```
You: /harmony build a SaaS dashboard with auth and billing

Harmony: asks 8 targeted questions (just pick a/b/c)
Harmony: writes a 200+ line PRD with data models and API contracts
Harmony: assembles a specialized 5-agent team for YOUR tech stack
Harmony: builds → tests → audits → fixes — per task, automatically
Harmony: "12 tasks complete. 87% coverage. 0 security issues. Here's your project."
```

> **You approved 3 times. Wrote 0 lines of code. Every line was independently audited.**

[한국어 README](README.ko.md)  ·  [Design Philosophy](docs/DESIGN_PHILOSOPHY.md)

---

## Why This Exists

Every AI coding tool has the same blind spot: **the AI grades its own homework.**

It writes the code, runs the tests, and says "done." But who verified the tests are meaningful? Who checked the auth doesn't leak? Who confirmed the error handling works?

Harmony fixes this with three structural guarantees:

| Problem | How Harmony Solves It |
|---------|----------------------|
| Writer reviews own code | **Separate auditor** — fresh agent, zero shared context |
| Agent says "tests pass" | **Server cross-verifies** — runs coverage tool independently |
| Quality is "suggested" | **Code-enforced gates** — can't proceed without meeting thresholds |

This isn't prompt engineering. It's [**harness engineering**](https://martinfowler.com/articles/harness-engineering.html) — making it structurally difficult to produce low-quality output. [Read the full philosophy →](docs/DESIGN_PHILOSOPHY.md)

---

## Quick Start

```bash
/plugin marketplace add hohre12/jwbae-plugins
/plugin install agent-harmony@jwbae-plugins

# Then just:
/harmony a real-time chat app with rooms, auth, and file sharing
```

No `pip install`. Python runtime bootstraps automatically on first run.

---

## What Happens After You Hit Enter

```
Phase 1 — Interview              You answer 8-12 targeted questions (a/b/c)
Phase 2 — PRD Generation         200+ line spec with schemas, APIs, acceptance criteria
Phase 3 — PRD Review             You approve, edit, or restart
Phase 4 — Setup (automatic)      Agent team + design system + tasks + reference docs
Phase 5 — Build (automatic)      For each vertical-slice task:
                                   design doc → multi-agent implementation
                                   → quality gate (server-verified)
                                   → independent production audit
                                   → fix loop until ALL thresholds pass
Phase 6 — Verify                 Fresh QA agent checks every PRD feature is implemented
Phase 7 — Harden                 Security review — automated scanners + AI analysis
Phase 8 — Delivery               Full build + integration test + summary report
```

**You interact in Phases 1-3.** After that, Harmony runs autonomously and only pauses when it genuinely needs your input.

---

## Quality Gates — Code-Enforced, Not Prompt-Suggested

Metrics are measured by the server, not self-reported by agents.

| Metric | Prototype | MVP | Production |
|--------|-----------|-----|------------|
| Build passes | Required | Required | Required |
| All tests pass | Required | Required | Required |
| Zero lint errors | Required | Required | Required |
| Test coverage | >= 50% | >= 70% | >= 80% |
| Max file size | 600 lines | 400 lines | 350 lines |
| Max function size | 80 lines | 60 lines | 50 lines |
| Security criticals | 0 | 0 | 0 |
| A11y criticals | 0 | 0 | 0 |

The stage is set during the interview. "Prototype" is lenient. "Production" is strict. There is no "skip" button.

---

## Multi-Agent Team

Harmony doesn't use one agent for everything. It creates a **project-specific team** based on your tech stack:

```
┌─────────────────────────────────────────────────────┐
│  Main Architect — system design, coordination       │
│  Code Architect — design docs, code structure       │
│  DB Agent — schema, migrations, query optimization  │
│  Review Agent — independent code audit              │
│  E2E Agent — integration testing                    │
│  + Domain specialists (frontend, backend, etc.)     │
└─────────────────────────────────────────────────────┘
```

A FastAPI project gets different agents than a Next.js project. Agents work in **parallel worktrees**, merge through review, and are scoped to your project only.

Each agent receives domain-specific reference documents — verified knowledge, not training-data hallucination.

---

## The Build Loop (Per Task)

This is where the real value is. For every task:

```
  ┌──────────────┐
  │  Team builds  │  Design doc → concurrent implementation → self-review
  └──────┬───────┘
         ▼
  ┌──────────────┐
  │ Quality gate  │  Server measures: build, tests, lint, coverage, security
  └──────┬───────┘
         ▼ pass
  ┌──────────────┐
  │  Cold audit   │  Fresh agent. No shared context. Reads only code + PRD.
  └──────┬───────┘
         ▼ pass
  ┌──────────────┐
  │   Complete    │
  └──────────────┘

  Any failure → fix → loop back. No round limit.
  Escalates to you every 5 rounds for: retry / manual takeover / abort.

Harmony keeps automatic retries running by default. To control cost,
it pauses after repeated failures so you can choose what to do next.
```

**Accountability pressure**: Every agent knows a different agent will blindly judge its work. This changes first-pass quality.

---

## What Gets Generated

```
your-project/
├── docs/
│   ├── prd.md                     # Full PRD from your interview
│   ├── refs/                      # Domain reference docs (anti-hallucination)
│   └── tasks/                     # Design docs per task
├── .claude/agents/                # Your project's specialized agent team
├── .harmony/state.json            # Pipeline state (resumable, git-tracked)
├── CLAUDE.md                      # Project conventions
├── src/                           # Your actual code
└── tests/                         # With real coverage
```

---

## Session Resilience

Rate limited? Laptop closed? Session crashed? Just run it again.

```bash
/harmony
# → "Resume from task 8/12? (a) Resume  (b) Start over  (c) Status"
```

State is saved after **every step** with atomic writes. The state file is git-tracked — you can resume on a different machine.

---

## Best Fit

| Great for | Why |
|-----------|-----|
| Web apps (Next.js, FastAPI, Django) | Predictable structure, clear agent roles |
| API servers | Standard patterns, highly testable |
| CLI tools | Simple structure, fast pipeline |
| SaaS MVPs | Interview captures requirements precisely |

| Less ideal for | Why |
|----------------|-----|
| Large existing codebases (50k+ lines) | Too many implicit dependencies |
| ML / data pipelines | Experimental workflow doesn't fit linear tasks |
| Hardware / embedded | Integration testing can't be automated easily |

---

## Commands

| Command | Description |
|---------|-------------|
| `/harmony [idea]` | **The one command.** Idea → production-ready project |
| `/agent-harmony:harmony [idea]` | Fully qualified name (always works) |

Internal commands (used by the pipeline):

| Command | Description |
|---------|-------------|
| `/project-init` | Scaffold new project |
| `/codebase-init` | Initialize from existing code |
| `/generate-agents` | Create specialized agent team |
| `/build-refs` | Generate domain reference docs |

---

## Known Behavior

### Permission Mode During Setup

During project initialization, Claude Code may switch from bypass to "accept edits" mode — this is a [platform-level protection](https://code.claude.com/docs/en/permission-modes.md) for `.claude/` and `.mcp.json` files.

**Happens once.** Press `Shift+Tab` to return to bypass mode after initialization.

---

## Requirements

- Claude Code CLI (Max Plan or API key)
- Python 3.10+ (auto-bootstrapped)
- git
- macOS or Linux (Windows via WSL)

## Installation

```bash
/plugin marketplace add hohre12/jwbae-plugins
/plugin install agent-harmony@jwbae-plugins
```

## License

MIT

## Version

1.0.4
