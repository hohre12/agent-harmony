# Agent Harmony

**One prompt. A few choices. Then sit back.**

```
You: /agent-harmony:harmony I want to build a SaaS dashboard with auth and billing

Harmony: asks 5-7 smart questions (multiple choice — just pick letters)
Harmony: generates a 600+ line PRD
Harmony: assembles a specialized agent team
Harmony: builds, tests, reviews, audits — task by task
Harmony: "All 23 tasks complete. Here's your project."

You: approved 3 times. Wrote 0 lines of code.
```

[한국어 README](README.ko.md)

---

> Don't lose context. Don't micromanage agents. Don't review every file.
> **Harmony does it all. You just approve.**

---

## The Problem

Claude Code is powerful. But alone, it writes code in one pass — no review, no audit, no quality gate. The result works, but it's fragile.

Agent Harmony adds what's missing: **the entire development process**.

| | Passes | Review | Quality |
|---|---|---|---|
| Claude Code alone | 1 | None | Works, but fragile |
| Claude Code + you reviewing | 3-5 | Manual | Production-grade |
| **Claude Code + Harmony** | **5+** | **Automated** | **Production-grade, hands-free** |

## Quick Start

```bash
/plugin marketplace add hohre12/jwbae-plugins
/plugin install agent-harmony@jwbae-plugins

# Official plugin command
/agent-harmony:harmony a real-time chat app with rooms, auth, and file sharing

# Shorthand that works in many installed environments after plugin install
/harmony a real-time chat app with rooms, auth, and file sharing
```

That's the public installation path: marketplace → plugin install → run Harmony.

## What Happens After You Hit Enter

```
Phase 1 — Interview                        You answer a few multiple-choice questions
Phase 2 — PRD Generation                   Comprehensive spec, auto-generated
Phase 3 — Setup (automatic)                Agent team + tasks + reference docs
Phase 4 — Build (fully automatic)          For each task:
                                             design → implement → self-review
                                             → quality gate → production audit
                                             → fix until it passes
Phase 5 — Delivery                         Production-ready project
```

**You interact most in Phase 1.** After that, Harmony runs the pipeline and only comes back when it needs approval, explicit manual override, or an abort decision.

## Harness Engineering

Prompt engineering asks nicely. **Harness engineering gives automation the best shot at its highest-quality output.**

Every step in the pipeline is a constraint — not a suggestion.

```
 1. PRD Generation
    Agents can't build without clear requirements.
    600+ line spec generated from your interview — not a vague brief.

 2. Dynamic Agent Team (project-scoped, not shared globally)
    Specialized agents created FOR your project's tech stack and domains.
    A FastAPI project gets different agents than a Next.js project.
    Agents are scoped to your project only — no cross-project contamination.

 3. Expert Reference Docs (anti-hallucination)
    Each agent receives verified domain knowledge documents.
    Agents work from facts, not from training data memory.

 4. Accountability Pressure
    Every agent knows: a different agent will blindly judge your work
    with zero context about your intentions. This changes first-pass quality.

  5. Server-Cross-Checked Verification
     Build, test, lint, coverage — cross-checked outside the working agent where measurable.
     Agents cannot quietly hand-wave measurable quality signals.

  6. Infinite Quality Loop (with user-approved takeover checkpoints)
     Fails audit? → fix → re-audit. Repeat.
     After repeated failures, Harmony pauses so you can keep retrying, take over manually, or abort.
```

Harmony keeps automatic retries running by default. To control token/cost spend, it pauses after repeated failures and lets you choose: continue retrying, manual override, or abort.

Manual override ends Harmony's automatic verification loop. From that point on, the user takes direct responsibility for the outcome.

### Quality Thresholds

Code-enforced. Not prompt-suggested.

| Metric | Requirement | Measured by |
|--------|-------------|-------------|
| Build | Must pass | Actual build command |
| Tests | Must pass | Full test suite |
| Lint | Zero errors | Project linter |
| Coverage | >= 70% | pytest --cov / jest --coverage |
| File size | <= 400 lines | wc -l |
| Function size | <= 60 lines | AST / brace counting |
| Security | 0 critical | bandit / npm audit + secret scan |

## What Gets Generated

```
your-project/
├── docs/prd.md                    # 600+ line PRD from your conversation
├── .claude/agents/                # Specialized agent team for YOUR project
├── .claude/skills/team-executor/  # Task execution workflow
├── .harmony/state.json            # Pipeline state (auto-managed)
├── CLAUDE.md                      # Project rules
├── src/                           # Your actual project code
└── tests/                         # With real coverage
```

## Session Resilience

Session crashed? Rate limited? Just run it again.

```bash
/agent-harmony:harmony
/harmony
# → "Resume from task 15/23? (a) Resume (b) Start over"
```

State is saved after every step. Nothing is lost.

## Best Fit

| Great for | Why |
|-----------|-----|
| Web apps (Next.js, FastAPI, Django) | Predictable structure, clear agent roles |
| API servers | Standard patterns, highly testable |
| CLI tools | Simple structure, few agents needed |
| SaaS MVPs | Interview captures requirements well |

| Less ideal | Why |
|-----------|-----|
| Large existing codebases | Too many implicit dependencies to capture |
| ML/data pipelines | Experimental workflow vs linear tasks |
| Real-time systems | Integration testing is hard to automate |

## Commands

| Command | What it does |
|---------|-------------|
| `/agent-harmony:harmony [idea]` | **The one command.** Idea → production-ready project |
| `/harmony [idea]` | Shorthand used in many installed environments after plugin install |
| `/project-init` | Initialize project structure (used internally) |
| `/codebase-init` | Initialize from existing codebase |
| `/generate-agents` | Create specialized agent team |
| `/build-refs` | Generate domain reference docs |

## Known Behavior

### Permission Mode During Setup

During `/project-init` or `/codebase-init`, Claude Code may switch from bypass to "accept edits" mode. This is a [platform-level protection](https://code.claude.com/docs/en/permission-modes.md) for `.claude/` and `.mcp.json` files.

**This only happens once, during initial setup.** Press `Shift+Tab` to switch back to bypass mode after initialization.

## Installation

```bash
# Public installation path: add marketplace → install plugin
/plugin marketplace add hohre12/jwbae-plugins
/plugin install agent-harmony@jwbae-plugins
```

No `pip install` needed. Python runtime bootstraps automatically on first use.

## Requirements

- Claude Code CLI (Max Plan or API key)
- Python 3.10+ (auto-bootstrapped)
- git
- macOS or Linux (Windows via WSL)

## License

MIT

## Version

1.0.4
