# Design Philosophy

## The Trust Problem

AI coding tools have a fundamental flaw: **the same AI that writes your code is the one judging its quality.**

That's grading your own homework.

When you ask Claude Code to "build a dashboard with auth," it writes the code, runs some tests, and says "done." But who verified the tests are meaningful? Who checked the auth doesn't have bypass routes? Who confirmed the error handling covers edge cases?

Nobody. The writer and the reviewer are the same entity, in the same context, with the same blind spots.

Harmony exists because we believe **AI-generated code deserves the same rigor as human-written code** — independent review, measurable quality gates, and separation of concerns between writing and auditing.

---

## Harness Engineering

Harmony is built on the principle of [**Harness Engineering**](https://martinfowler.com/articles/harness-engineering.html) — the discipline of designing constraints, feedback loops, and verification systems around AI agents.

Prompt engineering asks an AI to do something well. Harness engineering makes it structurally difficult to do something poorly.

The difference:

| Approach | Method | Failure mode |
|----------|--------|-------------|
| Prompt engineering | "Write clean, well-tested code" | AI agrees, then doesn't |
| Harness engineering | Server rejects code that doesn't meet coverage threshold | Cannot proceed without meeting the bar |

Every step in Harmony's pipeline is a **constraint**, not a suggestion. The AI doesn't choose whether to write tests — it cannot pass the quality gate without them. It doesn't choose whether to follow the spec — a separate auditor will catch deviations.

This isn't about distrusting AI. It's about building systems where trust is **earned through verification**, not assumed through prompting.

---

## Core Principles

### 1. Separation of Writer and Auditor

The agent that writes code never audits it. A completely fresh agent — with no knowledge of the implementation decisions, shortcuts taken, or trade-offs made — reviews the output cold.

This isn't a suggestion in a prompt. It's a structural guarantee. The audit agent spawns in a new context with only the PRD, reference docs, and the code itself. No shared memory. No sympathy.

**Why this matters:** When the same agent writes and reviews, it has motivated reasoning. It remembers *why* it made a choice and unconsciously accepts it. A cold auditor sees only what exists, not what was intended.

### 2. Server-Side Truth

Agents report metrics. Harmony verifies them.

When an agent says "test coverage is 85%," the server cross-checks by running the actual coverage tool. When an agent says "zero lint errors," the server runs the linter independently.

Agents cannot hand-wave quality signals. Measurable metrics are measured — outside the agent's control.

**Why this matters:** Language models are optimized to produce plausible output. "All tests pass" is a plausible thing to say. The server doesn't care about plausibility — it cares about the exit code.

### 3. Quality Is Non-Negotiable

Harmony's quality gate doesn't have a "close enough" mode.

If coverage is 68% and the threshold is 70%, the task fails. The agent fixes, re-measures, and tries again. There is no automatic pass after N retries.

After persistent failures (every 5 rounds), Harmony pauses and gives you three options:
- **Keep trying** — let the agent continue fixing
- **Take over manually** — you fix it yourself
- **Abort** — stop the task entirely

What you'll notice is missing: "Accept as-is." That option doesn't exist. If the bar is wrong, change the bar. But don't ship code that doesn't meet it.

**Why this matters:** The moment you add a "skip" button, every failure becomes a candidate for skipping. Quality gates only work if they're gates, not suggestions.

### 4. Vertical Slices, Not Horizontal Layers

Harmony never generates tasks like "Set up database schema" → "Build all API endpoints" → "Create all UI pages."

Every task is a **vertical slice** — a complete feature that cuts through all layers: database, API, UI, and tests. "User Authentication" includes the users table, the auth endpoints, the login page, and the integration tests.

**Why this matters:** Horizontal tasks create integration debt. You build a perfect database schema, then discover it doesn't match what the API needs. Vertical slices force integration from day one — bugs surface in task 1, not task 20.

### 5. Accountability Pressure

Every agent knows, before it writes a single line: **a different agent will judge this work with zero context.**

This isn't just an auditing mechanism — it's a behavioral lever. When agents know their output will be cold-reviewed, first-pass quality measurably improves. The code they write when they know it'll be audited is different from the code they write when they know it won't be.

We include this information in every build prompt. The agent can't game it — the audit happens regardless.

### 6. Spec-Driven Development

Nothing is built without a spec. Harmony generates a comprehensive PRD (Product Requirements Document) before any code is written.

The PRD isn't a vague brief. It's a 200+ line document with:
- Exact data models (table schemas, not "we'll need a users table")
- API contracts (request/response examples, not "CRUD endpoints")
- Acceptance criteria per feature (testable conditions, not "should work well")

Every audit checks code against this spec. "Does this match what was specified?" is a concrete question with a concrete answer.

**Why this matters:** Without a spec, "is this correct?" has no answer. The agent thinks it's correct. The auditor thinks it could be better. Neither has a source of truth. The PRD is that source of truth.

### 7. State Machine Resilience

AI coding sessions are fragile. Context windows fill up. Rate limits hit. Laptops close. Harmony treats all of these as expected events, not exceptions.

The entire pipeline state lives in `.harmony/state.json` — every completed task, every quality score, every audit result. If the session crashes at task 15 of 23, you restart and resume from task 15. Not task 1. Not "let me re-analyze the codebase."

State is saved after every step with atomic writes and automatic backups. The state file is tracked in git, so you can even resume on a different machine.

**Why this matters:** Real projects take hours of AI compute. A pipeline that can't survive a rate limit is a pipeline you can't trust with real work.

---

## What Harmony Is Not

- **Not a code generator.** It's a development process that happens to use AI for code generation.
- **Not a prompt wrapper.** The pipeline logic runs server-side, outside the LLM's context.
- **Not a linter or testing tool.** It orchestrates existing tools (pytest, jest, bandit, eslint) into a coherent quality pipeline.
- **Not a replacement for human judgment.** It handles the 90% of development that's structural and repeatable, so you can focus on the 10% that requires real decisions.

---

## The Pipeline, Philosophically

```
Interview     →  Understand what to build (not guess)
PRD           →  Write it down precisely (not vaguely)
Agent Team    →  Assign specialists (not one generalist)
Build         →  Implement with accountability (not hope)
Quality Gate  →  Measure, don't ask (not self-report)
Audit         →  Independent review (not self-review)
Verify        →  Check against spec (not vibes)
Harden        →  Security review (not afterthought)
Deliver       →  Integration test (not "it works on my machine")
```

Each phase exists because skipping it is how software projects fail — whether the developer is human or AI.
