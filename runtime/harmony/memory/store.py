"""Agent Memory Store — persistent cross-session learning.

NOT just "save a markdown file." This is a queryable knowledge base:

  - Each agent role has isolated memory (no cross-contamination)
  - Memories are tagged with project, category, and timestamp
  - Auto-injected into agent context when orchestrator assigns tasks
  - Deduplication: same insight is not stored twice
  - Decay: memories older than N sessions get relevance-scored

What makes this different from Ralph Wiggum Loop's "Git is memory":
  Git remembers WHAT was done. Memory remembers WHY and WHAT WORKED.
  "Don't use raw SQL for this project — ORM is required per harness"
  "Entity User has implicit relation to Billing via subscription field"
  "Test coverage drops when touching auth module — add extra tests"
"""

from __future__ import annotations

import json
import hashlib
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional


MEMORY_DIR = ".harmony/memory"


@dataclass
class MemoryEntry:
    """A single memory entry."""
    id: str
    agent_role: str           # e.g., backend-agent, frontend-agent
    category: str             # pattern, mistake, insight, domain, decision
    content: str              # the actual learning
    project: str = ""         # project name (for cross-project filtering)
    tags: list[str] = field(default_factory=list)
    created_at: str = ""
    session_id: str = ""
    relevance_score: float = 1.0  # decays over time

    def content_hash(self) -> str:
        return hashlib.sha256(f"{self.agent_role}:{self.category}:{self.content}".encode()).hexdigest()[:12]


@dataclass
class AgentMemory:
    """Memory store for a single agent role."""
    agent_role: str
    entries: list[MemoryEntry] = field(default_factory=list)

    def _path(self, base: str = MEMORY_DIR) -> Path:
        return Path(base) / f"{self.agent_role}.json"

    def save(self, base: str = MEMORY_DIR) -> Path:
        p = self._path(base)
        p.parent.mkdir(parents=True, exist_ok=True)
        data = {"agent_role": self.agent_role, "entries": [asdict(e) for e in self.entries]}
        p.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
        return p

    @classmethod
    def load(cls, agent_role: str, base: str = MEMORY_DIR) -> "AgentMemory":
        p = Path(base) / f"{agent_role}.json"
        if not p.exists():
            return cls(agent_role=agent_role)
        data = json.loads(p.read_text(encoding="utf-8"))
        entries = [MemoryEntry(**e) for e in data.get("entries", [])]
        mem = cls(agent_role=agent_role)
        mem.entries = entries
        return mem

    def add(self, category: str, content: str, project: str = "", tags: list[str] | None = None, session_id: str = "") -> MemoryEntry | None:
        """Add a memory entry. Returns None if duplicate."""
        entry = MemoryEntry(
            id="",
            agent_role=self.agent_role,
            category=category,
            content=content,
            project=project,
            tags=tags or [],
            created_at=datetime.now(timezone.utc).isoformat(),
            session_id=session_id,
        )
        entry.id = entry.content_hash()

        # Deduplication
        existing_ids = {e.content_hash() for e in self.entries}
        if entry.id in existing_ids:
            return None

        self.entries.append(entry)
        return entry

    def query(
        self,
        category: str | None = None,
        project: str | None = None,
        tags: list[str] | None = None,
        limit: int = 20,
    ) -> list[MemoryEntry]:
        """Query memories with filters."""
        results = self.entries

        if category:
            results = [e for e in results if e.category == category]
        if project:
            results = [e for e in results if e.project == project or e.project == ""]
        if tags:
            tag_set = set(tags)
            results = [e for e in results if tag_set & set(e.tags)]

        # Sort by relevance then recency
        results.sort(key=lambda e: (e.relevance_score, e.created_at), reverse=True)
        return results[:limit]

    def context_prompt(self, project: str = "", limit: int = 10) -> str:
        """Generate a context block for agent prompt injection.

        This is what gets prepended to an agent's task prompt so it
        remembers learnings from previous sessions.
        """
        relevant = self.query(project=project, limit=limit)
        if not relevant:
            return ""

        lines = [
            f"## Previous Learnings ({self.agent_role})",
            f"From {len(relevant)} stored memories (most relevant first):",
            "",
        ]

        for entry in relevant:
            tag_str = f" [{', '.join(entry.tags)}]" if entry.tags else ""
            lines.append(f"- **[{entry.category}]** {entry.content}{tag_str}")

        lines.append("")
        lines.append("Apply these learnings to your current task. Do not repeat past mistakes.")
        return "\n".join(lines)

    def consolidate(self, max_entries: int = 100) -> int:
        """Remove oldest low-relevance entries when memory exceeds max_entries.

        Returns the number of entries removed.
        """
        if len(self.entries) <= max_entries:
            return 0
        # Sort by relevance (low first), then by age (oldest first)
        self.entries.sort(key=lambda e: (e.relevance_score, e.created_at))
        remove_count = len(self.entries) - max_entries
        self.entries = self.entries[remove_count:]
        return remove_count

    def forget(self, entry_id: str) -> bool:
        """Remove a specific memory entry."""
        before = len(self.entries)
        self.entries = [e for e in self.entries if e.id != entry_id]
        return len(self.entries) < before

    def stats(self) -> dict:
        categories = {}
        for e in self.entries:
            categories[e.category] = categories.get(e.category, 0) + 1
        return {
            "agent_role": self.agent_role,
            "total_entries": len(self.entries),
            "categories": categories,
        }


# ====================================================================== #
#  Cross-agent memory operations
# ====================================================================== #


def list_all_agents(base: str = MEMORY_DIR) -> list[str]:
    """List all agent roles that have stored memories."""
    p = Path(base)
    if not p.exists():
        return []
    return [f.stem for f in p.glob("*.json")]


def global_context(project: str = "", limit_per_agent: int = 5, base: str = MEMORY_DIR) -> str:
    """Generate cross-agent context for orchestrator-level decisions."""
    agents = list_all_agents(base)
    if not agents:
        return ""

    sections = []
    for agent_role in agents:
        mem = AgentMemory.load(agent_role, base)
        ctx = mem.context_prompt(project, limit_per_agent)
        if ctx:
            sections.append(ctx)

    if not sections:
        return ""

    return "\n---\n".join(sections)
