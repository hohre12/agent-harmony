---
name: build-refs
description: Generated specialist agents analyze PRD/architecture documents from their respective domain perspectives, create domain-based reference documents in docs/refs/, and update the reference document sections in each agent file. Use after running /generate-agents.
---

# Build Refs Skill

Usage: `/build-refs`

**Prerequisite**: Specialist agents must exist in `.claude/agents/`.
(Requires prior execution of `/generate-agents`)

---

## Purpose

Each specialist agent analyzes the PRD or architecture document from its own domain perspective
and generates a content-based domain reference document (`docs/refs/{domain}.md`).

Domain filenames are named **based on content**, not agent role names:
- `database.md`, `api-spec.md`, `auth-spec.md`, `frontend-spec.md`, etc.
- Multiple agents can cross-reference the same domain file, maintaining a Single Source of Truth

When tasks are subsequently executed, agents can quickly consult their own domain file
and related domain files as needed, instead of repeatedly reading the entire PRD.

```
/generate-agents
    ↓
/build-refs   ← Design domain map → Generate domain reference docs + Update agent files
    ↓
/agent-harmony:run      ← Pipeline generates tasks and runs team-executor automatically
    ↓
/team-executor → Agents reference docs/refs/ during task execution
```

---

## Execution Steps

### Step 1. Verify Prerequisites

Verify the following:

**Reference documents** (abort immediately if none exist):
- At least one of `docs/prd.md` or `docs/architecture.md` must exist

**Agent list** (abort immediately if none exist):
- Specialist agents other than `expert-agent.md` must exist in `.claude/agents/`
- If none exist: instruct the user to run `/generate-agents` first

If `docs/refs/` already exists, confirm with the user:
```
⚠️  docs/refs/ already exists. Overwriting will regenerate all reference documents.
Do you want to continue?
```

### Step 2. Collect Agent List

Read all `.md` files in the `.claude/agents/` directory using the Read tool to get their **full contents**:
- Exclude `expert-agent.md`
- Extract from each file:
  - The `name` field from frontmatter
  - The `## Core Expertise` section (for domain map design)
  - The `## Reference Document Coverage` section (to verify required items)
  - The full file contents (retained for prompt injection in Step 5)

### Step 3. Create Domain Map

Design a **domain map** based on the agent list and analysis of the `## Core Expertise` sections.

**Map the following for each agent:**
- `domain_file`: The domain file this agent will write and own (`docs/refs/` subpath included)
- `ref_files`: List of other domain files this agent should reference

**Domain filename conventions** (do not use agent role names — name based on content):

| Agent Type | Domain Filename |
|---|---|
| DB / Data agent | `database.md` |
| Backend / API agent | `api-spec.md` |
| Frontend agent | `frontend-spec.md` |
| Auth / Security agent | `auth-spec.md` |
| AI / ML agent | `ai-spec.md` |
| Infra / DevOps agent | `infrastructure.md` |
| Architecture / Orchestration agent | `architecture.md` |
| Test / QA agent | `test-spec.md` |

For types not listed above, choose a name that best represents the domain's content.

**Domain map example:**
```
| Agent | domain_file | ref_files |
|---------|------------|-----------|
| backend-agent | docs/refs/api-spec.md | docs/refs/database.md, docs/refs/auth-spec.md |
| db-agent | docs/refs/database.md | docs/refs/api-spec.md |
| frontend-agent | docs/refs/frontend-spec.md | docs/refs/api-spec.md, docs/refs/auth-spec.md |
| auth-agent | docs/refs/auth-spec.md | docs/refs/database.md |
```

### Step 4. Create docs/refs/ Directory

```bash
mkdir -p docs/refs
```

### Step 5. Generate Reference Documents per Agent (Parallel)

Based on the domain map created in Step 3, **spawn each agent as a Task in parallel**.

- `subagent_type`: **Always use `general-purpose`**
  - Project-local agents (`.claude/agents/`) cannot be used directly as a Task `subagent_type`
  - Instead, inject the full agent file contents into the prompt so it operates in that role
- Spawn all agents in parallel at once (sequential execution is prohibited)

**Required preparation before spawning**: Replace `{...}` placeholders in the prompt template below with actual values:
- `{agent_file_content}` → The **full file contents** of `.claude/agents/{name}.md` read in Step 2
- `{name}` → Agent name (e.g., `backend-agent`)
- `{domain}` → Domain description (e.g., `API server`)
- `{domain_file}` → Assigned domain file path (e.g., `docs/refs/api-spec.md`)
- `{ref_a}`, `{ref_b}`, etc. → Actual file paths from the ref_files list
  - For agents with no ref_files, remove the "Related domains" line from the prompt

Prompt to send to each agent:

```
Below is the agent definition for {name}. Operate with this role and expertise.

---AGENT DEFINITION START---
{agent_file_content}
---AGENT DEFINITION END---

The required items specified in the `## Reference Document Coverage` section of the agent definition above
must all be included in the final document without omission.

Read the following documents, extract only the content related to your domain ({domain}),
and write {domain_file}.

Documents to reference:
- docs/prd.md (if it exists)
- docs/architecture.md (if it exists)

Writing rules:
1. Include only content directly related to your domain (do not summarize the entire PRD)
2. All required items specified in `## Reference Document Coverage` must be included — rewrite if any are missing
3. Prioritize specific numbers, constraints, business rules, API specs, data models, etc.
4. No length limit — write as much as needed to include all required items. Avoid unnecessary repetition, introductions, or explanations, but do not arbitrarily compress content

Document format:
---
# {Domain Name} Reference Document
> Source: {list of actual source documents that exist} | Generated: {date}

## Core Requirements
{Domain-related functional requirements}

## Data/Interface Specs
{Domain-related data models, APIs, schemas, etc.}

## Business Rules & Constraints
{Domain-related business logic and constraints}

## Related Domains
{Interface points with other domains}
---

After completing the document, replace the ## Reference Documents section of .claude/agents/{name}.md with the following:

## Reference Documents

> **Primary domain**: `{domain_file}` (core reference)
> **Related domains**: `docs/refs/{ref_a}`, `docs/refs/{ref_b}` (remove this line if no ref_files)
> **Source document**: {only files that actually exist — include docs/prd.md if present, include docs/architecture.md if present}
> **Design docs**: Created under `docs/tasks/` when tasks are executed
```

> **Note**: Each agent must not include content outside its own domain.
> Overlapping areas (e.g., authentication flow) should be included in the `ref_files` of all relevant agents for cross-referencing.

### Step 6. Completion Verification

After all Tasks are complete, verify the generated files:
- Use Glob to verify that `docs/refs/*.md` files exist
- Read each `.claude/agents/{name}.md` to confirm that the `## Reference Documents` section actually contains `docs/refs/` paths
  - If placeholders (in the form `{domain}.md`) remain unchanged → re-spawn that agent to retry the section update

---

## Completion Report

```
✅ Reference document generation complete

Domain map:
| Agent | Assigned Domain File | Related Domains |
|---------|--------------|------------|
| {agent} | docs/refs/{domain}.md | docs/refs/{a}.md |
...

Generated domain reference documents:
- docs/refs/{domain}.md  ← {domain description}
- docs/refs/{domain}.md  ← {domain description}
...

Updated agents:
- .claude/agents/{name}.md  (## Reference Documents section updated)
- .claude/agents/{name}.md  (## Reference Documents section updated)
...

Next step:
→ /agent-harmony:run      → Run the full pipeline (tasks generated automatically)
```

---

## Rules

- Abort immediately if neither `docs/prd.md` nor `docs/architecture.md` exists
- Abort immediately if only `expert-agent.md` exists in `.claude/agents/` → instruct user to run `/generate-agents` first
- The domain map must be designed before spawning any agents
- Domain filenames must be content-based, not agent role-based (formats like `backend-agent-reference.md` are prohibited)
- Each `domain_file` in the domain map must be unique per agent (if two agents share the same `domain_file`, parallel write conflicts will occur) — resolve by moving one to `ref_files`
- Reference documents per agent must be generated in parallel (sequential execution is prohibited)
- When spawning Tasks, `subagent_type` must always be `general-purpose` — using a project agent name as `subagent_type` will not work
- Inject the full agent file contents into the prompt so the agent operates in that role — use the contents read in Step 2
- Each agent extracts only content related to its own domain — copying the entire PRD is prohibited
- Generated documents have no length limit — write as much as needed to include all required items
- If an agent file lacks a `## Reference Documents` section, insert it immediately before `## Core Expertise`
- List only files that actually exist in the source document list (verify whether `docs/prd.md` or `docs/architecture.md` exists before listing)
- For agents with no `ref_files`, do not include the "Related domains" line
- Do not modify `expert-agent.md`
