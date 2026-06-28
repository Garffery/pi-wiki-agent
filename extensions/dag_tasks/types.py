"""
Types for DAG Tasks extension
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

TaskStatus = Literal["pending", "in_progress", "completed"]
TaskManageAction = Literal["create", "update", "complete", "done_archive", "archive", "purge", "list", "history"]
TaskOperationKind = Literal["created", "started", "completed", "done_archived", "updated", "unblocked", "archived", "purged", "skipped"]
ArchiveReason = Literal["completed", "selected"]


@dataclass
class DagTask:
    """A task in the DAG."""
    id: str
    title: str
    description: str = ""
    context: str | None = None
    status: TaskStatus = "pending"
    active_form: str | None = None
    owner: str | None = None
    blocks: list[str] = field(default_factory=list)
    blocked_by: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)
    created_at: float = 0.0
    started_at: float | None = None
    completed_at: float | None = None
    updated_at: float = 0.0


@dataclass
class StoreData:
    """Store persistence format."""
    next_id: int = 1
    tasks: list[DagTask] = field(default_factory=list)


@dataclass
class TaskOperation:
    """Result of a task operation."""
    kind: TaskOperationKind
    id: str | None = None
    title: str | None = None
    count: int | None = None
    total: int | None = None
    changed: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


@dataclass
class ArchivedDagTask:
    """An archived task."""
    archived_at: float
    archive_reason: ArchiveReason
    task: DagTask


@dataclass
class TaskManageResultDetails:
    """Details returned from task_manage."""
    action: TaskManageAction | None = None
    operations: list[TaskOperation] = field(default_factory=list)
    tasks: list[DagTask] = field(default_factory=list)
    history: list[ArchivedDagTask] = field(default_factory=list)
    guidance: str | None = None


@dataclass
class TaskNextResultDetails:
    """Details returned from task_next."""
    ready: list[DagTask] = field(default_factory=list)
    active: list[DagTask] = field(default_factory=list)
    blocked: list[DagTask] = field(default_factory=list)
    completed_count: int = 0
    total_count: int = 0


@dataclass
class DagTasksConfig:
    """Configuration for DAG tasks."""
    task_scope: Literal["memory", "session", "project"] = "session"
    auto_archive_completed: Literal["never", "on_list_complete", "on_task_complete"] = "on_list_complete"
    animate_active_tasks: bool = False
