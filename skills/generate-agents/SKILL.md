---
name: generate-agents
description: The expert-agent analyzes the PRD or architecture.md to automatically generate specialized agents needed for the project. Use after running /project-init or /codebase-init.
---

# Generate Agents Skill

Usage: `/generate-agents`

**Prerequisites**: `.claude/agents/expert-agent.md` must exist.
(Requires running `/project-init` or `/codebase-init` first)

---

## Execution Steps

### Step 1. Check Reference Documents

Check for reference documents in the following priority order:

1. `docs/prd.md` — new projects (project-init path)
2. `docs/architecture.md` — existing projects (codebase-init path)
3. If both exist → read both

If neither exists, stop immediately and notify the user.

### Step 2. Spawn expert-agent

Use the `Agent` tool to spawn with **`subagent_type: expert-agent`** and **delegate the entire agent generation workflow**.

```
Read docs/prd.md (or docs/architecture.md),
analyze the project to determine the list of specialized agents needed,
get user confirmation, and create the agent files.

For each agent, include the following:
- role: agent role name (e.g., backend-expert)
- responsibility: single-responsibility one-line description
- domains: list of responsible domains
- tools: apply the following criteria based on role:
    Architecture/orchestration agents: Read, Edit, Write, Glob, Grep, Bash, WebFetch, WebSearch, SendMessage, Agent
    Implementation agents: Read, Edit, Write, Glob, Grep, Bash, WebFetch, WebSearch, SendMessage
    Read-only agents (analysis/review): Read, Glob, Grep, Bash, WebFetch, WebSearch, SendMessage (exclude Write/Edit)
- mcpServers: include only actually needed MCP servers (stitch/supabase/github/context7 etc.; omit if unnecessary)
- model: select based on role —
    opus: architecture/orchestration, security/review, AI/ML (roles where complex judgment, reasoning, and coordination are key)
    sonnet: backend/frontend implementation, DB/infrastructure, testing/QA, design/UI (roles focused on implementation, generation, and repetitive tasks)
- memory: `project` (always included for all agents)
- permissionMode: default
- constraints: things the agent must never do
- related_agents: other agents it collaborates with
- conventions: concrete conventions for the agent's technical domain, extracted from PRD/architecture.md
  (library versions, file paths, code patterns, config values, naming rules — no placeholders)
```

> expert-agent autonomously performs Steps 3~4 below. It uses `AskUserQuestion` to get user confirmation before creating files, so when the Agent completes, agent files are already created.

### Step 3. Agent List Review *(performed by expert-agent)*

expert-agent presents the analysis results to the user for confirmation:

```
Analyzed agent list:
1. {role}-agent: {responsibility}
2. {role}-agent: {responsibility}
...

Shall I proceed with creating these agents? (Let me know if any agents should be removed)
```

### Step 4. Agent File Creation *(performed by expert-agent)*

After user confirmation, expert-agent creates each agent as `.claude/agents/{role}-agent.md`.

**All agents follow the "Markdown skeleton + optional XML sections" structure:**

**Sections written in Markdown** (using ## headers):
- Role definition, responsibilities, core expertise
- Execution steps, coding rules, project rules & conventions, constraints, final checklist

**`## Project Rules & Conventions` writing guide:**
- Place after `## Coding Rules`, before `## Collaborating Agents`
- Organize with `###` subsections per technical area of responsibility
- Only concrete values extracted from PRD/architecture.md (no placeholders):
  Library versions, file paths/directory patterns, code patterns (function signatures, decorators, class names), config values, error response formats
- Include in detail for implementation agents; keep brief for orchestration/review agents

**Sections using XML tags** (only when needed):
- `<constraints>`: when strictly separating hard rules from soft guidelines
- `<output_format>`: when output format is complex or must be enforced
- `<examples>`: when input/output pairs are needed

```markdown
---
name: {role}-agent
description: "Use this agent when [specific trigger condition with concrete examples]. Specializes in [domain expertise]."
model: {opus or sonnet — see model selection guide below}
color: {color by role type}
tools: Read, Edit, Write, Glob, Grep, Bash, WebFetch, WebSearch, SendMessage
# Read-Only agents (review/security): remove Write, Edit from above
mcpServers:           # only if needed; remove this field entirely if not needed
  - {mcp-server-name}
memory: project
permissionMode: default
---

You are the {Role Name}. {Core mission in one line}.

## Memory

**MANDATORY**: When all assigned subtasks are complete, save learnings via `harmony_memory_save`:

```
harmony_memory_save({
  "agent_role": "{role}-agent",
  "category": "pattern",  // pattern | mistake | insight | domain | decision
  "content": "what you learned",
  "tags": ["relevant", "tags"]
})
```

- Save: discovered patterns/conventions, design decisions, issues and solutions, key file paths
- Do NOT save: content already in CLAUDE.md, task-specific details, generic knowledge

## Reference Documents

> **Primary domain**: `docs/refs/{domain}.md` (core reference)
> **Related domains**: `docs/refs/{a}.md`, `docs/refs/{b}.md` (remove this line if none)
> **Source document**: `docs/prd.md` or `docs/architecture.md` (only include files that actually exist)
> **Design docs**: Created under `docs/tasks/` when tasks are executed

## Core Expertise

- **{Domain 1}**: {specific tech, libraries, versions, patterns}
- **{Domain 2}**: {specific tech, libraries, versions, patterns}
- **{Domain 3}**: {specific tech, libraries, versions, patterns}

## Execution Steps

1. {First required step}
2. {Second step}
3. {Completion criteria and approach}

## Coding Rules

- {Language/framework version specification}
- {Naming conventions}
- {Error handling approach}

## Project Rules & Conventions

### {Technical sub-area 1 — e.g., App Structure}
- {Specific rule: file paths, directory patterns, library versions}
- {Code pattern example: class names, function signatures, decorators}

### {Technical sub-area 2 — e.g., Auth/Security}
- {Specific rule: algorithms, config values, storage location}

### {Technical sub-area 3 — e.g., Error Handling}
- {Error class hierarchy, response format, logging patterns}

## Collaborating Agents

> **Autonomous collaboration**: Communicate directly with related agents via `SendMessage`. Only report to the team lead for `[ESCALATE]` (blocking/mediation needed) and final completion.

| Agent | Collaboration Point |
|---------|------------|
| {agent-name} | {collaboration scenario: what outputs are exchanged} |

## Out of Scope

- {Description of another agent's domain} → `{agent-name}`

<constraints>
  CRITICAL: {Key constraint — for Read-Only agents, explicitly state "Never use Write or Edit tools."}
  - {Role boundary rule}
  - {Quality standard}
</constraints>

<!-- output_format: only include when output format is complex or must be strictly enforced; omit if simple -->
<output_format>
  {Result structure, format, required items}
</output_format>

<!-- examples: only include when input/output patterns are needed; omit for simple agents -->
<examples>
  <example>
    <input>{Representative request example}</input>
    <output>{Expected output example}</output>
  </example>
</examples>

## Final Checklist

- [ ] {Self-verification item 1}
- [ ] {Self-verification item 2}
- [ ] {Self-verification item 3}
```

**Role color guide:**

| Role Type | Color |
|---|---|
| Architecture / Orchestration | `purple` |
| Backend Implementation | `blue` |
| Frontend Implementation | `cyan` |
| DB / Infrastructure | `orange` |
| AI / ML | `yellow` |
| Testing / QA | `green` |
| Design / UI | `pink` |
| Security / Review | `red` |

**Model selection guide:**

| Role Type | Model | Reason |
|---|---|---|
| Architecture / Orchestration | `opus` | Complex system design, multi-agent coordination, deep reasoning required |
| Security / Review | `opus` | Vulnerability analysis, code auditing, complex judgment required |
| AI / ML | `opus` | Model selection, algorithm design, high-level reasoning required |
| Backend Implementation | `sonnet` | Code generation, API implementation, sufficient for repetitive tasks |
| Frontend Implementation | `sonnet` | UI component generation, styling, repetitive coding tasks |
| DB / Infrastructure | `sonnet` | Query writing, schema design, config file management |
| Testing / QA | `sonnet` | Test code generation, validation logic, repetitive tasks |
| Design / UI | `sonnet` | Design implementation, asset management, repetitive tasks |

> **Principle**: Use `opus` for agents where complex judgment/reasoning/orchestration is key; use `sonnet` for agents focused on implementation/generation/repetitive tasks.

**Memory inclusion criteria (`memory: project`):**

**Include in all agents** — remembering project conventions, architectural decisions, and progress context improves team collaboration quality.

> All agents must include a `## Memory` section (placed after role description, before `## Reference Documents`) with mandatory save instructions to `.claude/agent-memory/{role}-agent/MEMORY.md`.

**Read-Only agents (analysis only, no implementation):**
- `tools`: `Read, Glob, Grep, Bash, WebFetch, WebSearch, SendMessage` (no Write/Edit)
- First line of `<constraints>`: `CRITICAL: Never use Write or Edit tools. You are a read-only analysis agent.`

---

### Step 5. Clean Up expert-agent.md

The project-local expert-agent has completed its role and should be deleted:

```bash
rm .claude/agents/expert-agent.md
```

> Do not delete the plugin's `agents/expert-agent.md`. If `/generate-agents` is re-run, the plugin version will be used.

---

## Completion Report

```
✅ Agent generation complete

Generated agents ({n} total):
- .claude/agents/{role}-agent.md           # {one-line description} | {opus/sonnet} | memory: project
- .claude/agents/{role}-agent.md           # {one-line description} | {opus/sonnet} | memory: project
...

Next steps:
1. /build-refs   → Generate domain reference documents for each agent (recommended)
2. /agent-harmony:run      → Run the full pipeline (tasks generated automatically)
```

## Rules

- Stop immediately if expert-agent.md does not exist
- Merge agents with overlapping roles (no duplicate agents)
- All agents must follow the single responsibility principle
- `tools` should only include what is actually needed (Read-Only agents: exclude Write/Edit)
- **Always generate an Architecture/Orchestration agent named `architect-agent`** — team lead for `/team-executor`, never omitted or merged
- **Always generate a Testing/QA agent** when the project has 2 or more services or sub-projects — cross-service integration tests cannot be delegated to implementation agents
- **Always generate a Design/UI agent** when the PRD has a dedicated UI/UX section (screen layouts, design tokens, color system, typography) — design spec extraction cannot be absorbed into the frontend agent
- Agent count scales with project complexity — 3~4 for simple projects, 7~10 for complex projects
- If `.claude/agents/` files already exist, review the list before overwriting
- After all agent files are created, always delete `.claude/agents/expert-agent.md` — the plugin's `agents/expert-agent.md` remains for future re-runs
- `model` must be selected per role — do not unify all agents to sonnet
- `memory: project` must be included in all agents
- `## Memory` section must be included in all agents (after role description, before `## Reference Documents`)
- **All generated agent files must be written entirely in English** — no Korean in section headers, descriptions, rules, or any content
