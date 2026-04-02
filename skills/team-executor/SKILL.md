---
name: team-executor
description: Executes tasks by spawning agents concurrently for autonomous collaboration. Usage: /agent-harmony:team-executor {tag}:{main_task_id}
---

# Team Execution Skill

Usage: `/agent-harmony:team-executor {tag}:{main_task_id}`

- `tag`: Session tag (e.g., `d8fd057d`)
- `main_task_id`: Main task number (e.g., `3`)
- Example: `/agent-harmony:team-executor d8fd057d:1`

## Task & Team Config Source

- Task data: `.harmony/state.json` → `tasks` array (find by task id)
- Team config: `.harmony/state.json` → `team_config` object
- Agent definitions: `.claude/agents/*.md`

Read these FIRST before proceeding.

### Team Config Fields
```
team_config: {
  "main_architect": "agent who leads design & coordination",
  "code_architect": "agent for code structure (may be same as main)",
  "db_agent": "agent for DB work (null if none)",
  "review_agent": "agent for code review",
  "e2e_agent": "agent for E2E testing (null if none)",
  "agent_type_table": {"agent-name": "role description", ...},
  "git_mode": "monorepo | multi-git"
}
```

## Naming Conventions

- `{user}`: Extract via `whoami` (run once, reuse)
- Branch: `feature/{tag}-{task-id}_{task-name}/{user}`
- Design doc: `docs/tasks/{tag}-{task-id}-{task-name}-plan.md`
- Team name: `team-{tag}-{task-id}`
- Worktree branch: `feature/{tag}-{task-id}_{task-name}/wt-{subtask-id}/{user}`

## Execution Workflow

### 1. Load Task & Team Config

- Read `.harmony/state.json`
- Find the task by `main_task_id` in the `tasks` array
- Read `team_config` for agent role assignments
- Identify subtasks and their assigned agents
- Read `.claude/agents/*.md` for agent definitions

### 2. Create Branch

- Extract `{user}` via `whoami`
- Branch name: `feature/{tag}-{task-id}_{task-name}/{user}`

**Branch Chaining:**
> Branch from the latest feature branch with the same `tag` and `{user}`. If none exist, branch from `develop`, `main`, or `master` (in that order).

### 3. Team Creation and Design (Phase 1)

> **This step must never be skipped.**

#### 3-1. Create Team
- Create a team via `TeamCreate` (team name: `team-{tag}-{task-id}`)

#### 3-2. Check for Existing Design Document
- Check if `docs/tasks/{tag}-{task-id}-*-plan.md` exists
- If sufficient → move to Step 4
- If insufficient → proceed to 3-3

#### 3-3. Spawn Design Agents Concurrently
- Use `main_architect` and `code_architect` from team_config
- If DB-related subtasks exist: also add `db_agent`
- Deliver: main task info, subtask list, design doc path
- Include **Autonomous Collaboration Protocol** (below)

#### 3-4. Required Design Document Contents
1. **Overview**: Feature description, dependencies, flow
2. **API Design** (if applicable): Endpoints, DTOs
3. **Data Model** (if applicable): Schema, entities
4. **Implementation File List**: Files per subtask
5. **Key Decisions**: Design choices and rationale
6. **Build Sequence**: Implementation order

#### 3-5. Team Lead Review
- Review and approve the design document
- Send `shutdown_request` to design agents → proceed to implementation

### 4. Spawn Implementation Agents (Phase 2)

#### 4-1. Create Worktrees
```bash
grep -q '.worktrees/' .gitignore || echo '.worktrees/' >> .gitignore
git worktree add .worktrees/wt-{subtask-id} -b feature/{tag}-{task-id}_{task-name}/wt-{subtask-id}/{user} feature/{tag}-{task-id}_{task-name}/{user}
```

#### 4-2. Spawn Agents Concurrently
- Spawn implementation agents based on subtask `assigned_agent` fields
- Also spawn the `review_agent` from team_config
- Each agent receives: task info, subtasks, design doc, worktree path
- **Self-Review Requirement** for every implementation agent:

  **WARNING: After implementation, your work enters a BLIND REVIEW.**
  A different agent — with ZERO context about your process, reasoning, or
  conversations — will review ONLY your code output. That reviewer judges
  the code as if a stranger wrote it. After that, a fresh senior-engineer
  agent performs a production audit from scratch.

  Before reporting done, verify ALL of the following:
  1. Requirements: every design doc item implemented
  2. Bugs: no logic errors, off-by-one, null access, race conditions
  3. Error handling: all user-facing paths handle failures gracefully
  4. Edge cases: empty lists, zero values, boundary conditions, null inputs
  5. Constants: no magic numbers/strings — use named constants
  6. DRY: no duplicated logic — extract shared functions/components
  7. Common components: repeated UI patterns extracted to shared components
  8. Naming: clear, consistent, meaningful variable/function/class names
  9. No dead code, no god functions (>60 lines), no god files (>400 lines)
  10. Tests: every public function tested with meaningful assertions
  11. Performance: no N+1 queries, no unbounded fetches, proper memoization

  Ask yourself: if this code were submitted by a stranger with no explanation,
  would it pass a senior engineer's review? If not, fix it before reporting done.

### 5. Progress Monitoring
- Receive progress reports from agents
- Mediate blocking/disagreements
- **User escalation**: [ESCALATE] → decide or ask user via `AskUserQuestion`

### 6. Review, Fix Loop, and Completion

#### 6-1. Code Review with Quality Criteria
The `review_agent` (from team_config) reviews ALL implementations against:

**Bugs & Logic:**
1. Logic errors: wrong conditionals, off-by-one, inverted boolean, missing return
2. Null/undefined access: unguarded optional values, missing null checks
3. Race conditions: shared state without sync, async ordering issues
4. Boundary conditions: empty arrays, zero/negative values, max int

**Code Quality:**
5. DRY violations: duplicated logic → extract to shared functions/utilities
6. Magic numbers/strings: hardcoded values → named constants
7. Common components: repeated UI/logic patterns → shared components
8. Naming: unclear, inconsistent, or misleading names
9. Dead code: unused imports, unreachable branches, commented-out code
10. File/function size: no god files (>400 lines) or god functions (>60 lines)

**Architecture & Integration:**
11. Design compliance: every design doc item implemented
12. Error handling: try/catch, empty states, validation — all paths covered
13. Security: input validation, auth checks, no secrets
14. Integration: API contracts match, imports resolve, types align

**Performance:**
15. N+1 queries: DB calls inside loops
16. Missing memoization / unnecessary re-renders (frontend)
17. Unbounded data fetches: missing pagination or limits

**Test Quality:**
18. Every public function tested with meaningful assertions
19. Edge cases and error paths tested, not just happy paths

For each issue: File:line, Severity (MUST-FIX/SHOULD-FIX), What, How to fix.

#### 6-2. Fix Loop
If MUST-FIX issues found:
1. Route to responsible agent → fix in worktree
2. `review_agent` re-reviews fixed items only
3. Repeat until ALL MUST-FIX issues are resolved — no round limit

#### 6-3. E2E Testing (if applicable)
- If `e2e_agent` exists in team_config: spawn for E2E testing

#### 6-4. Worktree Merge
```bash
git checkout feature/{tag}-{task-id}_{task-name}/{user} && git merge feature/{tag}-{task-id}_{task-name}/wt-{subtask-id}/{user}
```
- On conflict: spawn responsible agent to resolve
- Cleanup: `git worktree remove .worktrees/wt-{subtask-id}`

#### 6-5. Task Completion
- When all subtasks done: task is complete
- Send `shutdown_request` to all agents → `TeamDelete`

### 7. Verification and Wrap-up
- Verify file existence against design doc
- Final commit: `/commit`
- Push: `git push -u origin feature/{tag}-{task-id}_{task-name}/{user}`
- Output final status summary

## Autonomous Collaboration Protocol

```
### Core Principles
1. Proactive Communication: Ask related agents via SendMessage when stuck
2. Dependency Awareness: Check prerequisites with relevant agents
3. Completion Notification: Notify dependent agents when done
4. Design First: Agree on interfaces before implementation
5. Conflict Avoidance: Coordinate when modifying same files
6. Team Leader Reporting: Only [ESCALATE] and final completion to lead

### Communication Tags
| Tag | Purpose |
|-----|---------|
| [ASK] | Question/Request |
| [NOTIFY] | Completion/change notification |
| [AGREE] | Consensus request |
| [REVIEW] | Review request |
| [ESCALATE] | Team leader mediation |
| [USER-ASK] | Needs user input |
```

## Rules

- Agent definitions: `.claude/agents/`
- `.worktrees/` directory: add to `.gitignore`
- The team lead directly performs the team leader role
- The Autonomous Collaboration Protocol must be delivered when spawning each agent
- Commits: use the `/commit` skill
