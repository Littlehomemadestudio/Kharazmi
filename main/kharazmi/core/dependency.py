"""Dependency (edge) between two tasks."""
from __future__ import annotations

from dataclasses import dataclass, field

from .enums import DependencyType
from .value_objects import TaskId, Duration


@dataclass(frozen=True)
class Dependency:
    """
    A precedence relation between two tasks.

    predecessor -> successor with a typed relationship (FS/FF/SS/SF)
    and an optional lead/lag. Positive lag = delay; negative lag = lead.

    The Dependency is immutable — to change it, remove it and add a new one.
    """
    predecessor_id: TaskId
    successor_id: TaskId
    type: DependencyType = DependencyType.FINISH_START
    lag: Duration = field(default_factory=lambda: Duration(0))

    def __post_init__(self) -> None:
        if self.predecessor_id == self.successor_id:
            raise ValueError("A task cannot depend on itself")

    @property
    def key(self) -> tuple:
        """Stable identity for set membership / dedup."""
        return (self.predecessor_id.value, self.successor_id.value, self.type.value)

    def to_dict(self) -> dict:
        return {
            "predecessor": str(self.predecessor_id),
            "successor": str(self.successor_id),
            "type": self.type.value,
            "lag_minutes": self.lag.minutes,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "Dependency":
        return cls(
            predecessor_id=TaskId(data["predecessor"]),
            successor_id=TaskId(data["successor"]),
            type=DependencyType(data.get("type", "FS")),
            lag=Duration(int(data.get("lag_minutes", 0))),
        )
