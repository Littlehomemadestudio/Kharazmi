"""Enumerations for the Kharazmi domain model.

These are the only legal values for the corresponding fields — the
"serious logic" of the application. Anything that does not fit one of
these enumerations is rejected at the entity boundary.
"""
from __future__ import annotations

from enum import Enum, IntEnum, unique


@unique
class TaskStatus(str, Enum):
    """Lifecycle of a task. Transitions are constrained — see Task.advance()."""
    DRAFT = "draft"            # Just created, not yet ready to start
    READY = "ready"            # Dependencies satisfied, can be started
    ACTIVE = "active"          # Currently being worked on
    BLOCKED = "blocked"        # Cannot proceed (missing dep, resource, etc.)
    DONE = "done"              # Completed successfully
    CANCELLED = "cancelled"    # Willfully abandoned
    DEFERRED = "deferred"      # Postponed to a later cycle


@unique
class Priority(IntEnum):
    """Numeric priority. Higher value = more important."""
    TRIVIAL = 0
    LOW = 1
    MEDIUM = 2
    HIGH = 3
    CRITICAL = 4


@unique
class DependencyType(str, Enum):
    """
    The four standard precedence relations used in project management
    (the same four MS Project uses). Anything else is not a dependency.

    FS = Finish-to-Start  (successor starts after predecessor finishes)
    FF = Finish-to-Finish (successor finishes after predecessor finishes)
    SS = Start-to-Start   (successor starts after predecessor starts)
    SF = Start-to-Finish  (successor finishes after predecessor starts)
    """
    FINISH_START = "FS"
    FINISH_FINISH = "FF"
    START_START = "SS"
    START_FINISH = "SF"


@unique
class RiskLevel(str, Enum):
    """Qualitative risk used by Monte Carlo simulation."""
    NEGLIGIBLE = "negligible"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    SEVERE = "severe"


@unique
class DurationUnit(str, Enum):
    MINUTE = "minute"
    HOUR = "hour"
    DAY = "day"
    WEEK = "week"


@unique
class ViewKind(str, Enum):
    """The set of legal views in the workspace."""
    GRAPH = "graph"          # Node-based neural-network-of-tasks (main)
    GANTT = "gantt"          # Time-scaled bar chart
    KANBAN = "kanban"        # Status columns
    TIMELINE = "timeline"    # Chronological list
    STATS = "stats"          # Analytics dashboard


# Legal status transitions — anything else is rejected.
LEGAL_TRANSITIONS: dict[TaskStatus, frozenset[TaskStatus]] = {
    TaskStatus.DRAFT:     frozenset({TaskStatus.READY, TaskStatus.CANCELLED, TaskStatus.DEFERRED}),
    TaskStatus.READY:     frozenset({TaskStatus.ACTIVE, TaskStatus.BLOCKED, TaskStatus.CANCELLED, TaskStatus.DEFERRED}),
    TaskStatus.ACTIVE:    frozenset({TaskStatus.DONE, TaskStatus.BLOCKED, TaskStatus.DEFERRED}),
    TaskStatus.BLOCKED:   frozenset({TaskStatus.READY, TaskStatus.ACTIVE, TaskStatus.CANCELLED}),
    TaskStatus.DEFERRED:  frozenset({TaskStatus.READY, TaskStatus.CANCELLED}),
    TaskStatus.DONE:      frozenset(),  # terminal
    TaskStatus.CANCELLED: frozenset(),  # terminal
}
