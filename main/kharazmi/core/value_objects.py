"""Value objects — immutable, identity-less domain primitives."""
from __future__ import annotations

import re
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Optional

from .enums import DurationUnit


_ID_RE = re.compile(r"^[A-Za-z0-9_\-]+$")


@dataclass(frozen=True)
class TaskId:
    """Strongly-typed task identifier. Always a non-empty string."""
    value: str

    def __post_init__(self) -> None:
        if not self.value or not _ID_RE.match(self.value):
            raise ValueError(f"Invalid TaskId: {self.value!r}")

    @classmethod
    def generate(cls, prefix: str = "T") -> "TaskId":
        return cls(f"{prefix}{uuid.uuid4().hex[:8].upper()}")

    def __str__(self) -> str:
        return self.value


@dataclass(frozen=True)
class Duration:
    """
    A typed duration. Stored canonically as minutes internally so all
    arithmetic is exact regardless of unit chosen by the user.
    """
    minutes: int

    def __post_init__(self) -> None:
        if self.minutes < 0:
            raise ValueError("Duration cannot be negative")

    @classmethod
    def of(cls, amount: float, unit: DurationUnit) -> "Duration":
        if unit == DurationUnit.MINUTE:
            m = int(round(amount))
        elif unit == DurationUnit.HOUR:
            m = int(round(amount * 60))
        elif unit == DurationUnit.DAY:
            m = int(round(amount * 60 * 8))   # 8-hour workday
        elif unit == DurationUnit.WEEK:
            m = int(round(amount * 60 * 8 * 5))  # 5-day workweek
        else:
            raise ValueError(f"Unknown unit: {unit}")
        return cls(m)

    @property
    def hours(self) -> float:
        return self.minutes / 60.0

    @property
    def days(self) -> float:
        return self.minutes / (60.0 * 8)

    @property
    def weeks(self) -> float:
        return self.minutes / (60.0 * 8 * 5)

    def to_unit(self, unit: DurationUnit) -> float:
        if unit == DurationUnit.MINUTE:
            return float(self.minutes)
        if unit == DurationUnit.HOUR:
            return self.hours
        if unit == DurationUnit.DAY:
            return self.days
        return self.weeks

    def as_timedelta(self) -> timedelta:
        return timedelta(minutes=self.minutes)

    def __add__(self, other: "Duration") -> "Duration":
        return Duration(self.minutes + other.minutes)

    def __sub__(self, other: "Duration") -> "Duration":
        return Duration(max(0, self.minutes - other.minutes))

    def humanize(self) -> str:
        if self.minutes < 60:
            return f"{self.minutes}m"
        if self.minutes < 60 * 8:
            h = self.minutes / 60.0
            return f"{h:.1f}h" if h != int(h) else f"{int(h)}h"
        d = self.minutes / (60 * 8)
        if d < 5:
            return f"{d:.1f}d" if d != int(d) else f"{int(d)}d"
        w = self.minutes / (60 * 8 * 5)
        return f"{w:.1f}w" if w != int(w) else f"{int(w)}w"


@dataclass(frozen=True)
class TimeWindow:
    """A half-open [start, end) time window on the absolute calendar."""
    start: datetime
    end: datetime

    def __post_init__(self) -> None:
        if self.end < self.start:
            raise ValueError("TimeWindow end precedes start")

    @property
    def duration(self) -> Duration:
        delta = self.end - self.start
        return Duration(int(delta.total_seconds() // 60))

    def overlaps(self, other: "TimeWindow") -> bool:
        return self.start < other.end and other.start < self.end

    def contains(self, moment: datetime) -> bool:
        return self.start <= moment < self.end


@dataclass(frozen=True)
class Slack:
    """
    Result of CPM analysis on a task.

    total_slack: how long the task can slip without delaying the project.
    free_slack:  how long the task can slip without delaying any successor.
    """
    total_slack: Duration
    free_slack: Duration

    @property
    def is_critical(self) -> bool:
        return self.total_slack.minutes == 0

    @property
    def is_near_critical(self) -> bool:
        # Within 5% of project duration or 1 day, whichever is smaller
        return self.total_slack.minutes <= 60 * 8


@dataclass(frozen=True)
class PertEstimate:
    """
    Three-point estimate used by PERT.

    Expected duration = (o + 4m + p) / 6
    Std deviation     = (p - o) / 6
    Variance          = ((p - o) / 6) ^ 2
    """
    optimistic: Duration
    most_likely: Duration
    pessimistic: Duration

    def __post_init__(self) -> None:
        if not (self.optimistic.minutes <= self.most_likely.minutes <= self.pessimistic.minutes):
            raise ValueError("PERT requires optimistic <= most_likely <= pessimistic")

    @property
    def expected(self) -> Duration:
        o, m, p = self.optimistic.minutes, self.most_likely.minutes, self.pessimistic.minutes
        return Duration(int(round((o + 4 * m + p) / 6)))

    @property
    def std_dev(self) -> float:
        return (self.pessimistic.minutes - self.optimistic.minutes) / 6.0

    @property
    def variance(self) -> float:
        return self.std_dev ** 2


@dataclass(frozen=True)
class Tag:
    """A simple immutable tag/label."""
    name: str

    def __post_init__(self) -> None:
        if not self.name or not _ID_RE.match(self.name):
            raise ValueError(f"Invalid Tag name: {self.name!r}")

    def __str__(self) -> str:
        return self.name


@dataclass(frozen=True)
class Resource:
    """A named, typed resource that can be allocated to a task."""
    name: str
    capacity_per_day: float = 1.0  # 1.0 = full-time, 0.5 = half-time, etc.

    def __post_init__(self) -> None:
        if not self.name:
            raise ValueError("Resource name is required")
        if not (0 < self.capacity_per_day <= 1.0):
            raise ValueError("capacity_per_day must be in (0, 1.0]")


@dataclass(frozen=True)
class ResourceAllocation:
    """How much of a resource a task consumes."""
    resource: Resource
    load: float  # 0..capacity_per_day

    def __post_init__(self) -> None:
        if not (0 < self.load <= self.resource.capacity_per_day):
            raise ValueError(
                f"load {self.load} out of range for resource {self.resource.name}"
            )


@dataclass(frozen=True)
class Progress:
    """Completion percentage, clamped to [0, 100]."""
    percent: int

    def __post_init__(self) -> None:
        if not (0 <= self.percent <= 100):
            raise ValueError("Progress must be 0..100")

    @property
    def is_complete(self) -> bool:
        return self.percent >= 100

    @property
    def remaining_fraction(self) -> float:
        return (100 - self.percent) / 100.0
