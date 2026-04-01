---
name: run
description: "One prompt to production. Orchestrates the full pipeline: interview → PRD → setup → build → deliver."
---

# /agent-harmony:run

Usage: `/agent-harmony:run [what you want to build]`

Examples:
- `/agent-harmony:run a SaaS tool that analyzes code quality`
- `/agent-harmony:run a CLI that converts markdown to PDFs`
- `/agent-harmony:run` (no description — the system will ask)

## Execution

Call `harmony_pipeline_start` with the user's request.

The orchestrator returns step-by-step instructions. For each step:
1. Execute exactly what the prompt says
2. If `expect` is `"user_input"` → show the prompt to the user, then call `harmony_pipeline_respond` with their answer
3. If `expect` is `"step_result"` → do the work, then call `harmony_pipeline_next` with the result JSON
4. Repeat until the pipeline returns `"done"`

Do not skip steps. Do not improvise the order. The Python orchestrator manages the pipeline.
