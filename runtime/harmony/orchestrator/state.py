"""Session state management for the harmony development loop.

Saves/loads state to .harmony/state.json so development can resume
after rate limits, crashes, or intentional pauses.
"""

from __future__ import annotations

import json
import os
import uuid
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional


DEFAULT_STATE_PATH = ".harmony/state.json"

# Deterministic quality thresholds — tasks must meet ALL to pass the gate.
DEFAULT_QUALITY_THRESHOLDS: dict = {
    "build": True,              # Must compile / build successfully
    "tests": True,              # All tests must pass
    "lint": True,               # Zero lint errors (warnings OK)
    "test_coverage": 70.0,      # Minimum test coverage % (production level)
    "max_file_lines": 400,      # No single file exceeds this
    "max_function_lines": 60,   # No single function exceeds this
    "security_critical": 0,     # Zero critical security issues
    "a11y_critical": 0,         # Zero critical accessibility issues
    "design_token_violations": 10,  # Max hardcoded color/spacing values (frontend)
}

STAGE_THRESHOLDS: dict[str, dict] = {
    "prototype": {
        "test_coverage": 50.0,
        "max_file_lines": 600,
        "max_function_lines": 80,
    },
    "mvp": {
        "test_coverage": 70.0,
        "max_file_lines": 400,
        "max_function_lines": 60,
    },
    "production": {
        "test_coverage": 80.0,
        "max_file_lines": 300,
        "max_function_lines": 40,
        "a11y_critical": 0,
        "design_token_violations": 5,  # Strict for production
    },
}


def thresholds_for_stage(stage: str) -> dict:
    """Return quality thresholds adjusted for the given project stage."""
    base = dict(DEFAULT_QUALITY_THRESHOLDS)
    overrides = STAGE_THRESHOLDS.get(stage, {})
    base.update(overrides)
    return base


@dataclass
class SubtaskState:
    """State of a subtask within a main task."""

    id: str
    title: str
    description: str = ""
    test: str = ""  # Acceptance criteria
    assigned_agent: str = ""
    status: str = "pending"  # pending | in_progress | completed | failed


@dataclass
class TaskState:
    """State of a single development task."""

    id: str
    title: str
    status: str = "pending"  # pending | in_progress | completed | failed
    assigned_agent: str = ""
    subtasks: list[SubtaskState] = field(default_factory=list)
    retry_count: int = 0
    max_retries: int = 3
    last_error: str = ""
    completed_at: str = ""
    checkpoint: str = ""  # JSON — last known good state within a task (for mid-task resume)
    checkpoint_step: str = ""  # Human-readable step name (e.g., "3/5 files written")
    quality_scores: dict = field(default_factory=dict)  # Deterministic metrics per gate run
    audit_round: int = 0  # Number of audit rounds completed
    auditor_id: str = ""  # ID of the agent that performed the audit
    audit_nonce: str = ""  # Server-generated nonce for audit verification

    def is_terminal(self) -> bool:
        """Return True if the task is in a terminal state (completed only).

        Tasks never auto-terminate from retries — quality gate loops until thresholds are met.
        """
        return self.status == "completed"

    # Keys where lower is better (score must be <= threshold)
    _UPPER_BOUND_KEYS = frozenset({"max_file_lines", "max_function_lines", "security_critical", "a11y_critical", "design_token_violations"})

    def gate_passed(self, thresholds: dict) -> bool:
        """Check if quality_scores meet all thresholds."""
        if not self.quality_scores:
            return False
        for key, threshold in thresholds.items():
            score = self.quality_scores.get(key)
            if score is None:
                return False
            if isinstance(threshold, bool):
                if score != threshold:
                    return False
            elif isinstance(threshold, (int, float)):
                if key in self._UPPER_BOUND_KEYS:
                    # Score must be <= threshold (lower is better)
                    if score > threshold:
                        return False
                else:
                    # Score must be >= threshold (higher is better)
                    if score < threshold:
                        return False
        return True


@dataclass
class SessionState:
    """Full session state for the development loop."""

    session_id: str = ""
    project_name: str = ""
    prd_path: str = "docs/prd.md"
    started_at: str = ""
    updated_at: str = ""
    git_branch: str = ""

    # Pipeline state
    pipeline_phase: str = "init"  # init|interview|prd_gen|prd_review|setup|build|verify|harden|delivery|done
    pipeline_step: str = ""

    # Phase 1: Interview + PRD
    user_request: str = ""
    interview_answers: dict[str, str] = field(default_factory=dict)
    interview_context: dict[str, str] = field(default_factory=dict)
    prd_approved: bool = False

    # Phase 2: Setup
    setup_progress: dict[str, str] = field(default_factory=dict)
    team_config: dict = field(default_factory=dict)  # Agent role mapping (main_architect, review_agent, etc.)

    # Phase 3: Build
    total_tasks: int = 0
    tasks: list[TaskState] = field(default_factory=list)

    # Phase 3B/3C: Verify + Harden
    verify_round: int = 0
    harden_round: int = 0

    # Quality thresholds (deterministic gate)
    quality_thresholds: dict = field(default_factory=lambda: dict(DEFAULT_QUALITY_THRESHOLDS))

    # ------------------------------------------------------------------ #
    #  Persistence
    # ------------------------------------------------------------------ #

    def save(self, path: str = DEFAULT_STATE_PATH) -> Path:
        """Serialize state to JSON on disk using atomic write."""
        import tempfile
        self.updated_at = _now_iso()
        p = Path(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        # Ensure .harmony/ is in .gitignore
        _ensure_gitignore_entry(p.parent.name)
        data = asdict(self)
        content = json.dumps(data, indent=2, ensure_ascii=False)
        # Atomic write: write to temp file, then rename
        fd, tmp_path = tempfile.mkstemp(dir=str(p.parent), suffix=".tmp")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                f.write(content)
            # Keep backup of previous state
            if p.exists():
                backup = p.with_suffix(".json.bak")
                try:
                    backup.write_text(p.read_text(encoding="utf-8"), encoding="utf-8")
                except OSError:
                    pass
            os.replace(tmp_path, str(p))
        except BaseException:
            # Clean up temp file on any failure
            try:
                os.unlink(tmp_path)
            except OSError:
                pass
            raise
        return p

    @classmethod
    def load(cls, path: str = DEFAULT_STATE_PATH) -> Optional["SessionState"]:
        """Load state from JSON. Falls back to .bak if primary is corrupted."""
        p = Path(path)
        for candidate in (p, p.with_suffix(".json.bak")):
            if not candidate.exists():
                continue
            try:
                data = json.loads(candidate.read_text(encoding="utf-8"))
                raw_tasks = data.pop("tasks", [])
                tasks = []
                for t in raw_tasks:
                    raw_subtasks = t.pop("subtasks", [])
                    subtasks = [SubtaskState(**st) for st in raw_subtasks]
                    task = TaskState(**t)
                    task.subtasks = subtasks
                    tasks.append(task)
                state = cls(**data)
                state.tasks = tasks
                return state
            except (json.JSONDecodeError, TypeError, KeyError):
                continue
        return None

    # ------------------------------------------------------------------ #
    #  Factory
    # ------------------------------------------------------------------ #

    @classmethod
    def create_new(
        cls,
        project_name: str,
        tasks: list[dict],
        prd_path: str = "docs/prd.md",
    ) -> "SessionState":
        """Create a fresh session from a task list.

        Each item in *tasks* must have at least ``id`` and
        ``title``.  Optionally it may include ``agent`` (assigned agent name)
        and ``max_retries``.
        """
        sid = uuid.uuid4().hex
        now = _now_iso()
        task_states: list[TaskState] = []
        for t in tasks:
            subtasks = [
                SubtaskState(
                    id=str(st.get("id", "")),
                    title=st.get("title", ""),
                    description=st.get("description", ""),
                    test=st.get("test", ""),
                    assigned_agent=st.get("agent", ""),
                )
                for st in t.get("subtasks", [])
            ]
            task_states.append(
                TaskState(
                    id=str(t["id"]),
                    title=t["title"],
                    assigned_agent=t.get("agent", ""),
                    max_retries=t.get("max_retries", 3),
                    subtasks=subtasks,
                )
            )
        branch = f"harmony/dev-{sid[:8]}"
        return cls(
            session_id=sid,
            project_name=project_name,
            prd_path=prd_path,
            total_tasks=len(task_states),
            tasks=task_states,
            started_at=now,
            updated_at=now,
            git_branch=branch,
        )

    # ------------------------------------------------------------------ #
    #  Task helpers
    # ------------------------------------------------------------------ #

    def _task_by_id(self, task_id: str) -> TaskState:
        for t in self.tasks:
            if t.id == task_id:
                return t
        raise ValueError(f"Task {task_id!r} not found in session state")

    def next_pending_task(self) -> Optional[TaskState]:
        """Return the next pending task in order, or None if none remain."""
        for t in self.tasks:
            if t.status == "pending":
                return t
        return None

    def mark_in_progress(self, task_id: str) -> TaskState:
        """Mark a task as in-progress."""
        t = self._task_by_id(task_id)
        t.status = "in_progress"
        self.updated_at = _now_iso()
        return t

    def mark_completed(self, task_id: str) -> TaskState:
        """Mark a task as completed."""
        t = self._task_by_id(task_id)
        t.status = "completed"
        t.completed_at = _now_iso()
        self.updated_at = _now_iso()
        return t

    def mark_failed(self, task_id: str, error: str = "") -> TaskState:
        """Mark a task as failed and increment retry count."""
        t = self._task_by_id(task_id)
        t.status = "failed"
        t.retry_count += 1
        t.last_error = error
        self.updated_at = _now_iso()
        return t

    def can_retry(self, task_id: str) -> bool:
        """Return True if the task has retries remaining."""
        t = self._task_by_id(task_id)
        return t.retry_count < t.max_retries

    def reset_for_retry(self, task_id: str) -> TaskState:
        """Reset a failed task back to pending for retry."""
        t = self._task_by_id(task_id)
        if t.status != "failed":
            raise ValueError(f"Task {task_id!r} is not failed (status={t.status!r})")
        t.status = "pending"
        self.updated_at = _now_iso()
        return t

    # ------------------------------------------------------------------ #
    #  Aggregate queries
    # ------------------------------------------------------------------ #

    def counts(self) -> dict[str, int]:
        """Return a status-count mapping."""
        c: dict[str, int] = {"pending": 0, "in_progress": 0, "completed": 0, "failed": 0}
        for t in self.tasks:
            c[t.status] = c.get(t.status, 0) + 1
        return c

    def all_tasks_terminal(self) -> bool:
        """True when every task is completed or has exhausted retries."""
        return all(t.is_terminal() for t in self.tasks)

    def progress_summary(self) -> str:
        """Return a human-readable progress string."""
        c = self.counts()
        total = len(self.tasks)
        pct = (c["completed"] / total * 100) if total else 0
        lines = [
            f"Session  : {self.session_id[:8]}",
            f"Phase    : {self.pipeline_phase}",
            f"Step     : {self.pipeline_step}",
            f"Branch   : {self.git_branch}",
            f"Progress : {c['completed']}/{total} tasks completed ({pct:.0f}%)",
        ]
        if total:
            lines.extend([
                f"  pending     : {c['pending']}",
                f"  in_progress : {c['in_progress']}",
                f"  completed   : {c['completed']}",
                f"  failed      : {c['failed']}",
            ])
        lines.append(f"Updated  : {self.updated_at}")
        return "\n".join(lines)

    def interview_question_sequence(self) -> list[str]:
        """Return the ordered list of interview question IDs for this project.

        Skips irrelevant questions based on accumulated context.
        """
        ctx = self.interview_context
        project_type = ctx.get("project_type", "")

        base = ["target_users", "core_problem", "features", "tech_stack", "project_stage", "project_language"]

        # Add conditional questions — skip irrelevant ones for CLI/library
        if project_type not in ("cli", "library", "personal"):
            base.append("design")
        elif project_type == "personal":
            # Personal projects still need design if they have a frontend
            tech = ctx.get("tech_stack", "").lower()
            features = ctx.get("features", "").lower()
            request = ctx.get("user_request", "").lower()
            all_text = f"{tech} {features} {request}"
            frontend_hints = (
                "react", "next", "vue", "angular", "svelte", "frontend",
                "dashboard", "대시보드", "ui", "화면", "web", "웹",
                "html", "css", "tailwind", "page", "페이지",
            )
            if any(kw in all_text for kw in frontend_hints):
                base.append("design")
        if project_type not in ("cli", "library", "api", "personal"):
            base.append("auth")
        if project_type not in ("cli", "personal"):
            base.append("monetization")
        if project_type not in ("cli", "library", "personal"):
            base.append("deployment")

        return base

    def add_fix_tasks(self, fix_tasks: list[dict]) -> None:
        """Append fix tasks (from verify or harden) to the task list."""
        for ft in fix_tasks:
            tid = ft.get("id", f"fix-{uuid.uuid4().hex[:6]}")
            self.tasks.append(
                TaskState(
                    id=str(tid),
                    title=ft["title"],
                    assigned_agent=ft.get("agent", ""),
                    max_retries=ft.get("max_retries", 2),
                )
            )
        self.total_tasks = len(self.tasks)
        self.updated_at = _now_iso()


# ---------------------------------------------------------------------- #
#  Utility
# ---------------------------------------------------------------------- #

def _now_iso() -> str:
    """Return the current UTC time in ISO-8601 format."""
    return datetime.now(timezone.utc).isoformat()


def _ensure_gitignore_entry(dirname: str) -> None:
    """Add dirname to .gitignore if not already present. Non-fatal on error."""
    entry = f"{dirname}/"
    gitignore = Path(".gitignore")
    try:
        content = gitignore.read_text(encoding="utf-8") if gitignore.exists() else ""
        if entry not in content.splitlines():
            with gitignore.open("a", encoding="utf-8") as f:
                if content and not content.endswith("\n"):
                    f.write("\n")
                f.write(f"{entry}\n")
    except OSError:
        pass
