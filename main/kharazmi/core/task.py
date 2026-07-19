"""The Task entity — the central object of the domain."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional

from .enums import TaskStatus, Priority, RiskLevel, DurationUnit, LEGAL_TRANSITIONS
from .value_objects import (
    TaskId, Duration, Progress, PertEstimate, Tag, ResourceAllocation,
    TimeWindow, Slack,
)


@dataclass
class Task:
    """
    A unit of work in the project graph.

    A Task has identity (TaskId), intrinsic properties (title, duration,
    priority), scheduling metadata (early/late start/finish, slack),
    operational state (status, progress), and resources.

    The scheduling metadata (early_start, late_start, early_finish,
    late_finish, slack) is NOT set by the user — it is computed by the
    Critical Path algorithm and injected by the SchedulingService.
    """
    id: TaskId
    title: str
    description: str = ""
    duration: Duration = field(default_factory=lambda: Duration(60))
    priority: Priority = Priority.MEDIUM
    status: TaskStatus = TaskStatus.DRAFT
    risk: RiskLevel = RiskLevel.LOW
    progress: Progress = field(default_factory=lambda: Progress(0))
    tags: set[Tag] = field(default_factory=set)
    resources: list[ResourceAllocation] = field(default_factory=list)
    pert: Optional[PertEstimate] = None

    # Optional external constraint — earliest this task may start
    earliest_start: Optional[datetime] = None
    # Optional external constraint — latest this task may finish
    latest_finish: Optional[datetime] = None

    # Position in the node-graph UI (x, y). Pure UI concern but stored
    # on the entity so layouts persist across sessions.
    x: float = 0.0
    y: float = 0.0

    # --- Computed by SchedulingService (CPM/PERT) ---
    # These are intentionally Optional — they are only valid after a
    # successful schedule calculation.
    early_start: Optional[datetime] = None
    early_finish: Optional[datetime] = None
    late_start: Optional[datetime] = None
    late_finish: Optional[datetime] = None
    slack: Optional[Slack] = None

    created_at: datetime = field(default_factory=datetime.utcnow)
    updated_at: datetime = field(default_factory=datetime.utcnow)

    # --- Lifecycle ---
    def advance(self, new_status: TaskStatus) -> None:
        """Transition to a new status. Raises if the transition is illegal."""
        legal = LEGAL_TRANSITIONS.get(self.status, frozenset())
        if new_status not in legal:
            raise ValueError(
                f"Illegal transition: {self.status.value} -> {new_status.value}"
            )
        self.status = new_status
        self.touch()

    def set_progress(self, percent: int) -> None:
        self.progress = Progress(percent)
        if self.progress.is_complete and self.status != TaskStatus.DONE:
            # Auto-flip to DONE — terminal state
            if self.status in (TaskStatus.ACTIVE, TaskStatus.READY):
                self.status = TaskStatus.DONE
        self.touch()

    def set_duration(self, amount: float, unit: DurationUnit) -> None:
        self.duration = Duration.of(amount, unit)
        self.touch()

    def add_tag(self, tag: Tag) -> None:
        self.tags.add(tag)
        self.touch()

    def remove_tag(self, tag: Tag) -> None:
        self.tags.discard(tag)
        self.touch()

    def assign_resource(self, alloc: ResourceAllocation) -> None:
        # Replace any existing allocation for the same resource name
        self.resources = [
            r for r in self.resources if r.resource.name != alloc.resource.name
        ]
        self.resources.append(alloc)
        self.touch()

    def unassign_resource(self, resource_name: str) -> None:
        self.resources = [r for r in self.resources if r.resource.name != resource_name]
        self.touch()

    def touch(self) -> None:
        self.updated_at = datetime.utcnow()

    # --- Derived properties ---
    @property
    def is_critical(self) -> bool:
        return self.slack is not None and self.slack.is_critical

    @property
    def is_terminal(self) -> bool:
        return self.status in (TaskStatus.DONE, TaskStatus.CANCELLED)

    @property
    def is_active(self) -> bool:
        return self.status == TaskStatus.ACTIVE

    @property
    def effective_duration(self) -> Duration:
        """PERT expected duration if available, else plain duration."""
        if self.pert is not None:
            return self.pert.expected
        return self.duration

    @property
    def remaining_duration(self) -> Duration:
        return Duration(int(self.duration.minutes * self.progress.remaining_fraction))

    def to_dict(self) -> dict:
        """Serialise to a JSON-friendly dict."""
        return {
            "id": str(self.id),
            "title": self.title,
            "description": self.description,
            "duration_minutes": self.duration.minutes,
            "priority": int(self.priority),
            "status": self.status.value,
            "risk": self.risk.value,
            "progress": self.progress.percent,
            "tags": sorted(str(t) for t in self.tags),
            "resources": [
                {"name": r.resource.name,
                 "capacity": r.resource.capacity_per_day,
                 "load": r.load}
                for r in self.resources
            ],
            "pert": (
                None if self.pert is None else
                {
                    "optimistic": self.pert.optimistic.minutes,
                    "most_likely": self.pert.most_likely.minutes,
                    "pessimistic": self.pessimistic_minutes_or_none(),
                }
            ),
            "earliest_start": _dt(self.earliest_start),
            "latest_finish": _dt(self.latest_finish),
            "x": self.x,
            "y": self.y,
            "created_at": _dt(self.created_at),
            "updated_at": _dt(self.updated_at),
        }

    def pessimistic_minutes_or_none(self) -> Optional[int]:
        return None if self.pert is None else self.pert.pessimistic.minutes

    @classmethod
    def from_dict(cls, data: dict) -> "Task":
        from .value_objects import Resource
        pert = None
        if data.get("pert"):
            p = data["pert"]
            pert = PertEstimate(
                optimistic=Duration(int(p["optimistic"])),
                most_likely=Duration(int(p["most_likely"])),
                pessimistic=Duration(int(p["pessimistic"])),
            )
        return cls(
            id=TaskId(data["id"]),
            title=data["title"],
            description=data.get("description", ""),
            duration=Duration(int(data.get("duration_minutes", 60))),
            priority=Priority(int(data.get("priority", 2))),
            status=TaskStatus(data.get("status", "draft")),
            risk=RiskLevel(data.get("risk", "low")),
            progress=Progress(int(data.get("progress", 0))),
            tags={Tag(t) for t in data.get("tags", [])},
            resources=[
                ResourceAllocation(
                    Resource(r["name"], r.get("capacity", 1.0)),
                    r.get("load", 1.0),
                )
                for r in data.get("resources", [])
            ],
            pert=pert,
            earliest_start=_parse_dt(data.get("earliest_start")),
            latest_finish=_parse_dt(data.get("latest_finish")),
            x=float(data.get("x", 0.0)),
            y=float(data.get("y", 0.0)),
            created_at=_parse_dt(data.get("created_at")) or datetime.utcnow(),
            updated_at=_parse_dt(data.get("updated_at")) or datetime.utcnow(),
        )


def _dt(value: Optional[datetime]) -> Optional[str]:
    return None if value is None else value.isoformat()


def _parse_dt(value: Optional[str]) -> Optional[datetime]:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value)
    except (ValueError, TypeError):
        return None
