"""Template generator — produces SKILL.md files from configuration.

Replaces the 330-line team-executor template that was previously embedded in a SKILL.md file.
Python generates the exact file content; the agent just writes it to disk.
"""

from __future__ import annotations

import json


def generate_template(template_name: str, config_json: str) -> str:
    """Generate a template file. Returns the full file content as a string."""
    config = json.loads(config_json)

    if template_name == "team-executor":
        return _generate_team_executor(config)

    return f"Unknown template: {template_name}"


# ====================================================================== #
#  team-executor
# ====================================================================== #


def _build_agent_table_rows(cfg: dict) -> str:
    """Build the agent type table rows for the team-executor template."""
    main_arch = cfg.get("main_architect", "architect-agent")
    code_arch = cfg.get("code_architect", main_arch)
    db_agent = cfg.get("db_agent")
    review_agent = cfg.get("review_agent", main_arch)
    e2e_agent = cfg.get("e2e_agent")
    agent_table = cfg.get("agent_type_table", [])

    rows = f"| System architecture design, inter-agent coordination | `{main_arch}` |\n"
    if code_arch != main_arch:
        rows += f"| Code structure design, specifications | `{code_arch}` |\n"
    if db_agent:
        rows += f"| DB schema, indexes, migrations | `{db_agent}` |\n"
    if isinstance(agent_table, dict):
        for agent_name, role in agent_table.items():
            if agent_name not in (main_arch, code_arch, db_agent, review_agent, e2e_agent):
                rows += f"| {role} | `{agent_name}` |\n"
    else:
        for entry in agent_table:
            rows += f"| {entry.get('characteristics', '')} | `{entry.get('agent', '')}` |\n"
    rows += f"| Code review, quality verification | `{review_agent}` |\n"
    if e2e_agent:
        rows += f"| E2E test design and implementation | `{e2e_agent}` |\n"
    return rows


def _build_design_section(cfg: dict) -> str:
    """Build the design agents section."""
    main_arch = cfg.get("main_architect", "architect-agent")
    code_arch = cfg.get("code_architect", main_arch)
    db_agent = cfg.get("db_agent")
    if code_arch == main_arch:
        section = f"Default: {main_arch} (also handles code structure design)"
    else:
        section = f"Default: {code_arch} + {main_arch}"
    if db_agent:
        section += f"\n   - If DB-related subtasks exist: also add {db_agent}"
    return section


def _build_git_section(cfg: dict) -> tuple[str, str]:
    """Build git-related sections. Returns (git_section, branch_create)."""
    git_mode = cfg.get("git_mode", "monorepo")
    if git_mode == "multi-git":
        sub_map = cfg.get("sub_project_map", [])
        sub_map_table = "| Agent | Sub-project path | Domain |\n|---|---|---|\n"
        for row in sub_map:
            sub_map_table += f"| {row.get('agent','')} | {row.get('path','')} | {row.get('domain','')} |\n"
        git_section = f"\n## Sub-project Structure\n\n{sub_map_table}\n\nNote: Branch creation, commits, and pushes must run inside each sub-project directory.\nDo not run git commands from the root."
        branch_create = (
            "- Branch creation must be performed inside each sub-project directory\n"
            "- Branch name format: `feature/{tag}-{task-id}_{task-name}/{user}`"
        )
    else:
        git_section = ""
        branch_create = "- Branch name format: `feature/{tag}-{task-id}_{task-name}/{user}`"
    return git_section, branch_create


def _build_e2e_section(cfg: dict) -> str:
    """Build optional E2E testing section."""
    e2e_agent = cfg.get("e2e_agent")
    if e2e_agent:
        return f"\n#### 6-3. E2E Testing (if applicable)\n\n- If E2E testing is needed: spawn `{e2e_agent}`\n"
    return ""


def _generate_team_executor(cfg: dict) -> str:
    project = cfg.get("project_name", "Project")
    main_arch = cfg.get("main_architect", "architect-agent")
    review_agent = cfg.get("review_agent", main_arch)

    table_rows = _build_agent_table_rows(cfg)
    design_agents = _build_design_section(cfg)
    git_section, branch_create = _build_git_section(cfg)
    e2e_section = _build_e2e_section(cfg)

    return f"""---
name: team-executor
description: Executes {project} tasks by spawning agents concurrently for autonomous collaboration. Usage: /team-executor {{tag}}:{{main_task_id}}
---

# Team Execution Skill

Usage: `/team-executor {{tag}}:{{main_task_id}}`

- `tag`: Task file tag (e.g., `v1`)
- `main_task_id`: Main task number (e.g., `3`)
- Example: `/team-executor v1:1`

## Task File Rules

- Task file: `.harmony/state.json (tasks managed by harmony pipeline)`
- `{{user}}`: Automatically extracted via `whoami` command at runtime
- Use `{{tag}}-{{task-id}}` prefix in all paths:
  - Branch: `feature/{{tag}}-{{task-id}}_{{task-name}}/{{user}}`
  - Design document: `docs/tasks/{{tag}}-{{task-id}}-{{task-name}}-plan.md`
  - Team name: `team-{{tag}}-{{task-id}}`
  - Worktree branch: `feature/{{tag}}-{{task-id}}_{{task-name}}/wt-{{subtask-id}}/{{user}}`
{git_section}

## Execution Workflow

### 1. Understand the Task

- Load the main task from `.harmony/state.json (tasks managed by harmony pipeline)` using the tag
- Review task content (title, description, details, subtasks)
- Identify subtasks and dependencies
- Extract agent types from subtask titles: `{{title}} ({{agent-name}})` → spawn `{{agent-name}}`
- Update main task status to `"in-progress"` via harmony pipeline

### 2. Create Branch

- Extract `{{user}}` via `whoami` (run once, reuse)
{branch_create}

**Branch Chaining:**

> Branch from the latest feature branch with the same `tag` and `{{user}}`. If none exist, branch from `develop`, `main`, or `master` (in that order).

### 3. Team Creation and Design (Phase 1)

> **This step must never be skipped.**

#### 3-1. Create Team

- Create a team via `TeamCreate` (team name: `team-{{tag}}-{{task-id}}`)

#### 3-2. Check for Existing Design Document

- Check if `docs/tasks/{{tag}}-{{task-id}}-*-plan.md` exists
- If sufficient → move to Step 4
- If insufficient → proceed to 3-3

#### 3-3. Spawn Design Agents Concurrently

1. Spawn design agents concurrently:
   - {design_agents}
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
git worktree add .worktrees/wt-{{subtask-id}} -b feature/{{tag}}-{{task-id}}_{{task-name}}/wt-{{subtask-id}}/{{user}} feature/{{tag}}-{{task-id}}_{{task-name}}/{{user}}
```

#### 4-2. Spawn Agents Concurrently

- Update all subtasks to `"in-progress"` via harmony pipeline
- Spawn all implementation agents + `{review_agent}` concurrently
- Each agent receives: task info, subtasks, design doc, worktree path
- **Self-Review Requirement** for every implementation agent:

  After completing implementation, perform a self-review before reporting done:
  1. Requirements check: every design doc item implemented
  2. Error handling: all user-facing paths handle failures
  3. Edge cases: boundary conditions handled
  4. Code quality: no dead code, consistent naming
  5. Tests: every public function has at least one test

### 5. Progress Monitoring

- Receive progress reports from agents
- Mediate blocking/disagreements
- **User escalation**: [ESCALATE] → decide or ask user via `AskUserQuestion`

### 6. Review, Fix Loop, and Completion

#### 6-1. Code Review with Quality Criteria

`{review_agent}` reviews ALL implementations against:

1. **Design Compliance**: Every design doc item implemented
2. **Error Handling**: try/catch, empty states, validation
3. **Security**: Input validation, auth checks, no secrets
4. **Integration**: API contracts match, imports resolve
5. **Test Coverage**: Every public function tested

For each issue: File:line, Severity (MUST-FIX/SHOULD-FIX), What, How to fix.

#### 6-2. Fix Loop

If MUST-FIX issues found:
1. Route to responsible agent → fix in worktree
2. `{review_agent}` re-reviews fixed items only
3. Max 2 fix rounds → escalate if unresolved
{e2e_section}
#### 6-4. Worktree Merge

```bash
git checkout feature/{{tag}}-{{task-id}}_{{task-name}}/{{user}} && git merge feature/{{tag}}-{{task-id}}_{{task-name}}/wt-{{subtask-id}}/{{user}}
```
- On conflict: spawn responsible agent to resolve
- Cleanup: `git worktree remove .worktrees/wt-{{subtask-id}}`

#### 6-5. Task Completion

- Update subtasks to `"done"` via harmony pipeline
- When all subtasks done: update main task to `"done"`
- Send `shutdown_request` to all agents → `TeamDelete`

### 7. Verification and Wrap-up

- Verify file existence against design doc
- Final commit: `/commit`
- Push: `git push -u origin feature/{{tag}}-{{task-id}}_{{task-name}}/{{user}}`
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

## Agent Types

| Task Characteristics | subagent_type |
|---------------------|---------------|
{table_rows}

## Rules

- Agent definitions: `.claude/agents/`
- `.worktrees/` directory: add to `.gitignore`
- The team lead directly performs the team leader role
- The Autonomous Collaboration Protocol must be delivered when spawning each agent
- Commits: use the `/commit` skill
"""
