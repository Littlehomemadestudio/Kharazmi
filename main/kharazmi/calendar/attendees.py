"""
Reminder and Attendee value objects.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from .enums import ReminderMethod, AttendeeStatus


@dataclass(frozen=True)
class Reminder:
    """
    A reminder for an event.

    `minutes_before` is how many minutes before the event's start time
    the reminder should fire. Google Calendar supports multiple
    reminders per event.
    """
    minutes_before: int = 30
    method: ReminderMethod = ReminderMethod.POPUP

    def __post_init__(self) -> None:
        if self.minutes_before < 0:
            raise ValueError("minutes_before must be >= 0")

    def to_dict(self) -> dict:
        return {
            "minutes_before": self.minutes_before,
            "method": self.method.value,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "Reminder":
        return cls(
            minutes_before=int(data.get("minutes_before", 30)),
            method=ReminderMethod(data.get("method", "popup")),
        )


@dataclass(frozen=True)
class Attendee:
    """A person invited to an event."""
    name: str
    email: str = ""
    status: AttendeeStatus = AttendeeStatus.NEEDS_ACTION
    is_organizer: bool = False

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "email": self.email,
            "status": self.status.value,
            "is_organizer": self.is_organizer,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "Attendee":
        return cls(
            name=data.get("name", ""),
            email=data.get("email", ""),
            status=AttendeeStatus(data.get("status", "needs_action")),
            is_organizer=data.get("is_organizer", False),
        )
