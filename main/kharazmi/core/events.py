"""Domain events emitted by the project aggregate root.

The UI subscribes to these events to refresh its views — there is no
direct coupling between the domain and the widgets.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Optional

from .value_objects import TaskId


@dataclass(frozen=True)
class DomainEvent:
    """Base event. All events are immutable and carry a timestamp."""
    occurred_at: datetime = field(default_factory=datetime.utcnow)


@dataclass(frozen=True)
class TaskCreated(DomainEvent):
    task_id: TaskId = None  # type: ignore[assignment]
    title: str = ""


@dataclass(frozen=True)
class TaskUpdated(DomainEvent):
    task_id: TaskId = None  # type: ignore[assignment]
    field: str = ""
    old: Any = None
    new: Any = None


@dataclass(frozen=True)
class TaskDeleted(DomainEvent):
    task_id: TaskId = None  # type: ignore[assignment]


@dataclass(frozen=True)
class TaskStatusChanged(DomainEvent):
    task_id: TaskId = None  # type: ignore[assignment]
    old: str = ""
    new: str = ""


@dataclass(frozen=True)
class DependencyAdded(DomainEvent):
    predecessor_id: TaskId = None  # type: ignore[assignment]
    successor_id: TaskId = None  # type: ignore[assignment]
    dep_type: str = "FS"


@dataclass(frozen=True)
class DependencyRemoved(DomainEvent):
    predecessor_id: TaskId = None  # type: ignore[assignment]
    successor_id: TaskId = None  # type: ignore[assignment]


@dataclass(frozen=True)
class CycleDetected(DomainEvent):
    """Emitted when an attempted dependency would create a cycle (and was rejected)."""
    attempted_edge: tuple = ()
    cycle: tuple = ()


@dataclass(frozen=True)
class ProjectReset(DomainEvent):
    pass


@dataclass(frozen=True)
class ProjectLoaded(DomainEvent):
    source: str = ""
    task_count: int = 0


@dataclass(frozen=True)
class ScheduleRecalculated(DomainEvent):
    """Emitted after CPM/PERT runs."""
    project_duration_minutes: int = 0
    critical_path: tuple = ()
    recalculated_at: datetime = field(default_factory=datetime.utcnow)
