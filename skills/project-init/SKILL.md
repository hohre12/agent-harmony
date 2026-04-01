---
name: project-init
description: Fully sets up a new project that only has docs/prd.md. Auto-generates the .claude structure, .mcp.json, CLAUDE.md, and expert-agent.md.
---

# Project Init Skill

Usage: `/project-init`

**Prerequisite**: A `docs/prd.md` file must exist in the current directory.

---

## Execution Order

### Step 1. Analyze PRD

- Read `docs/prd.md` (if missing, abort immediately and notify the user)
- Extract the following:
  - **Project name** and **one-line description**
  - **Tech stack**: language, framework, DB, cache, cloud services
  - **External services**: Supabase, GitHub, payments, AI APIs, etc.
  - **Platform**: web / mobile / backend / full-stack
  - **Core domain areas**: auth, real-time, AI, etc.
  - **Sub-project structure** (for multi-git setups): list of sub-project directories and their responsible domains (e.g., `backend/` — API server, `frontend/` — web client)

### Step 1.5. Detect Git Structure

Check whether a `.git` folder exists in the root directory:

- `.git` exists at root → **monorepo mode** (root is the git project)
- `.git` does not exist at root → **multi-git mode** (sub-projects each have independent git repos)

> The detection result is used as a branching condition when generating CLAUDE.md in Step 6.

### Step 2. Create Directory Structure

Create the following structure using a **merge approach**:

```
{project-root}/
├── .claude/
│   ├── agent-memory/
│   ├── agents/
│   └── skills/
└── docs/
    └── prd.md  (already exists)
```

**Merge rules (when `.claude/` folder already exists):**

- Directory missing → create it
- Directory exists → keep it, enter and check contents
- File missing → create it
- File exists with same name → overwrite
- File exists with different name → leave untouched

> No user confirmation needed before overwriting. Merge silently.
> In the completion report, distinguish between "newly added" and "overwritten" items.

### Step 3. Generate .mcp.json

Select the necessary MCP servers based on PRD analysis and generate `.mcp.json`.

**Always included:**
```json
"context7": {
  "command": "npx",
  "args": ["-y", "@upstash/context7-mcp"]
}
```

**Conditionally included (based on PRD tech stack):**

| Detected in PRD | MCP to add |
|---|---|
| UI/design work | `stitch`: `npx @_davideast/stitch-mcp proxy` |
| Supabase usage | `supabase`: Supabase MCP |
| GitHub integration | `github`: GitHub MCP |
| Web search needed (research, news) | `exa`: Exa MCP |
| Direct filesystem access | `filesystem`: Filesystem MCP |
| Notion API usage | `notion`: Notion MCP |

**Final `.mcp.json` format:**
```json
{
  "mcpServers": {
    // selected servers
  }
}
```

### Step 4. Generate CLAUDE.md

Create `CLAUDE.md` at the project root. Branch based on PRD content + **the Git structure detected in Step 1.5**:

**[monorepo mode]** (`.git` exists at root):

```markdown
# {project name}

{one-line project description}

## Tech Stack
{tech stack list extracted from PRD}

## Project Structure
{expected directory structure based on PRD}

## Git Structure
- Type: **monorepo**

## Development Rules
- Agent definitions: `.claude/agents/`
- Skill definitions: `.claude/skills/`
- Task management: managed by harmony pipeline (`.harmony/state.json`)
- Base branch: `main`
- Branch strategy: `feature/{tag}-{task-id}_{task-name}/{user}` (`{user}` = `whoami`)
- Branch chaining: if a previous task branch exists for the same tag, branch off of it (to include prior task code)
- Commits: use the `/commit` skill

## Reference Documents
- `docs/prd.md`: Project Requirements Document (PRD)
- `docs/refs/`: Per-agent domain reference documents (generated after running `/build-refs`)

## Language
All responses must match the language used in the user's initial prompt.
```

**[multi-git mode]** (`.git` does not exist at root):

```markdown
# {project name}

{one-line project description}

## Tech Stack
{tech stack list extracted from PRD}

## Project Structure
{expected directory structure based on PRD}

## Git Structure
- Type: **multi-git** (root is not a git project)
- Sub-project list:
  - `{sub-project-dir}/` — {responsible domain}  ← list each sub-project identified from PRD here

## Development Rules
- Agent definitions: `.claude/agents/`
- Skill definitions: `.claude/skills/`
- Task management: managed by harmony pipeline (`.harmony/state.json`)
- Run Claude: from the root folder
- Branch creation/commits/pushes: run inside each sub-project
  - Base branch: `main`
  - Branch strategy: `feature/{tag}-{task-id}_{task-name}/{user}` (`{user}` = `whoami`)
  - Commits: use the `/commit` skill
- **Caution**: The root folder is not a git project. Git commands must be run inside sub-project directories.

## Reference Documents
- `docs/prd.md`: Project Requirements Document (PRD)
- `docs/refs/`: Per-agent domain reference documents (generated after running `/build-refs`)

## Language
All responses must match the language used in the user's initial prompt.
```

### Step 5. Copy expert-agent.md

Copy the plugin's expert-agent into the project. Search in this order:

1. Plugin directory: find the `agent-harmony` plugin and copy `agents/expert-agent.md`
2. Fallback: `~/.claude/agents/expert-agent.md`

```bash
# The expert-agent.md is bundled with the agent-harmony plugin.
# Use Glob to find it: ~/.claude/plugins/agent-harmony/agents/expert-agent.md
# or a similar plugin installation path.
# Copy it to the project:
cp {found_path}/agents/expert-agent.md .claude/agents/expert-agent.md
```

If expert-agent.md cannot be found in any location, abort immediately and notify the user.

### Step 6. Generate .claude/settings.local.json

Create the settings file to enable agent team features and permissions:

```json
{
  "env": {
    "CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS": "1"
  },
  "permissions": {
    "allow": [
      "Bash(*)",
      "Edit(*)",
      "Read(*)",
      "WebFetch(*)",
      "WebSearch"
    ],
    "defaultMode": "bypassPermissions"
  },
  "teammateMode": "auto"
}
```

> Without this file, the `team-executor` skill's team features (`TeamCreate`, `SendMessage`, etc.) will not work.
>
> **Note**: `bypassPermissions` enables fully autonomous development (no approval prompts). Users can change this to `"default"` in `.claude/settings.local.json` if they prefer manual approval for each action.

---

## Completion Report

After all steps are complete, report to the user in the following format:

```
✅ Project initialization complete: {project name}

[Newly Added]
- .claude/agent-memory/
- .claude/agents/
- .claude/agents/expert-agent.md  (copied from plugin)
- .claude/skills/
- .claude/settings.local.json  (team features enabled)
- CLAUDE.md

[Overwritten]
- .mcp.json  (included MCPs: {list})

[Preserved Existing Files]
- .claude/settings.json  (kept as-is)
- .claude/{other existing files}

Next steps:
1. /generate-agents → Generate specialized agents
2. /build-refs     → Generate per-agent domain reference documents
3. /agent-harmony:run        → Run the full pipeline (or continue individually)
```

## Rules

- If `docs/prd.md` does not exist, abort immediately
- Even if `.claude/` already exists, proceed with **merge approach** without asking for overwrite confirmation
  - Same filename → overwrite
  - Different filename → keep existing file
  - Missing folder/file → create new
- If `.mcp.json` already exists → overwrite (single file)
- MCP server selection must be justified based on PRD tech stack
- After all files are created, output the structure in tree format
- In the completion report, distinguish between "newly added", "overwritten", and "preserved (existing file kept as-is)" items
