"""
The Event entity — the central object of the calendar subsystem.

An Event is anything that appears on the calendar: a meeting, an
appointment, a birthday, a focus-time block, an out-of-office block,
a task with a due date, etc.

Events may be one-off or recurring (via a RecurrenceRule). When
recurring, the UI expands the rule into virtual "occurrences" for
display, but the underlying storage is a single Event.
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Optional

from .enums import (
    EventType, Availability, EventStatus,
)
from .recurrence import RecurrenceRule
from .attendees import Reminder, Attendee


@dataclass
class Event:
    """
    A calendar event.

    Identity: `id` (string).
    Time: `start` and `end` (datetime). For all-day events, `all_day`
    is True and the time-of-day portion is ignored.
    """
    id: str
    calendar_id: str
    title: str
    description: str = ""
    location: str = ""
    start: datetime = field(default_factory=datetime.utcnow)
    end: datetime = field(default_factory=lambda: datetime.utcnow() + timedelta(hours=1))
    all_day: bool = False
    timezone: str = "local"

    # Classification
    event_type: EventType = EventType.NORMAL
    availability: Availability = Availability.BUSY
    status: EventStatus = EventStatus.CONFIRMED
    color: Optional[str] = None   # overrides calendar color if set

    # Recurrence
    recurrence: Optional[RecurrenceRule] = None

    # People
    attendees: list[Attendee] = field(default_factory=list)
    reminders: list[Reminder] = field(default_factory=list)

    # Task-specific (when event_type == TASK)
    completed: bool = False

    # Attachments (file paths — local-only)
    attachments: list[str] = field(default_factory=list)

    # Meeting link (e.g. a video call URL)
    meeting_link: str = ""

    # Metadata
    created_at: datetime = field(default_factory=datetime.utcnow)
    updated_at: datetime = field(default_factory=datetime.utcnow)

    def __post_init__(self) -> None:
        if not self.id:
            self.id = f"evt-{uuid.uuid4().hex[:12]}"
        if self.end < self.start:
            self.end = self.start + timedelta(hours=1)

    # ---- Mutators ----
    def touch(self) -> None:
        self.updated_at = datetime.utcnow()

    def set_time(self, start: datetime, end: datetime) -> None:
        if end < start:
            raise ValueError("Event end precedes start")
        self.start = start
        self.end = end
        self.touch()

    def move_to(self, new_start: datetime) -> None:
        """Move the event to start at new_start, preserving duration."""
        duration = self.end - self.start
        self.start = new_start
        self.end = new_start + duration
        self.touch()

    def set_duration(self, minutes: int) -> None:
        self.end = self.start + timedelta(minutes=minutes)
        self.touch()

    def add_attendee(self, attendee: Attendee) -> None:
        # Replace existing with same email
        self.attendees = [
            a for a in self.attendees if a.email != attendee.email or
            (not a.email and a.name != attendee.name)
        ]
        self.attendees.append(attendee)
        self.touch()

    def remove_attendee(self, email_or_name: str) -> None:
        self.attendees = [
            a for a in self.attendees
            if a.email != email_or_name and a.name != email_or_name
        ]
        self.touch()

    def add_reminder(self, reminder: Reminder) -> None:
        # Replace existing with same minutes_before
        self.reminders = [
            r for r in self.reminders if r.minutes_before != reminder.minutes_before
        ]
        self.reminders.append(reminder)
        self.touch()

    def complete(self) -> None:
        """Mark a TASK-type event as completed."""
        self.completed = True
        self.status = EventStatus.CONFIRMED
        self.touch()

    # ---- Derived properties ----
    @property
    def duration(self) -> timedelta:
        return self.end - self.start

    @property
    def duration_minutes(self) -> int:
        return int(self.duration.total_seconds() // 60)

    @property
    def is_recurring(self) -> bool:
        return self.recurrence is not None

    @property
    def is_task(self) -> bool:
        return self.event_type == EventType.TASK

    @property
    def is_all_day(self) -> bool:
        return self.all_day

    @property
    def is_meeting(self) -> bool:
        return self.event_type == EventType.MEETING or bool(self.attendees)

    @property
    def effective_color(self, calendar_color: str = "#D4AF37") -> str:
        return self.color if self.color else calendar_color

    def overlaps(self, other_start: datetime, other_end: datetime) -> bool:
        return self.start < other_end and other_start < self.end

    # ---- Serialisation ----
    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "calendar_id": self.calendar_id,
            "title": self.title,
            "description": self.description,
            "location": self.location,
            "start": self.start.isoformat(),
            "end": self.end.isoformat(),
            "all_day": self.all_day,
            "timezone": self.timezone,
            "event_type": self.event_type.value,
            "availability": self.availability.value,
            "status": self.status.value,
            "color": self.color,
            "recurrence": self.recurrence.to_dict() if self.recurrence else None,
            "attendees": [a.to_dict() for a in self.attendees],
            "reminders": [r.to_dict() for r in self.reminders],
            "completed": self.completed,
            "attachments": list(self.attachments),
            "meeting_link": self.meeting_link,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
        }

    @classmethod
    def from_dict(cls, data: dict) -> "Event":
        recurrence = None
        if data.get("recurrence"):
            try:
                recurrence = RecurrenceRule.from_dict(data["recurrence"])
            except Exception:
                recurrence = None
        return cls(
            id=data.get("id", ""),
            calendar_id=data.get("calendar_id", ""),
            title=data.get("title", "Untitled"),
            description=data.get("description", ""),
            location=data.get("location", ""),
            start=_parse_dt(data.get("start")) or datetime.utcnow(),
            end=_parse_dt(data.get("end")) or datetime.utcnow() + timedelta(hours=1),
            all_day=data.get("all_day", False),
            timezone=data.get("timezone", "local"),
            event_type=EventType(data.get("event_type", "normal")),
            availability=Availability(data.get("availability", "busy")),
            status=EventStatus(data.get("status", "confirmed")),
            color=data.get("color"),
            recurrence=recurrence,
            attendees=[Attendee.from_dict(a) for a in data.get("attendees", [])],
            reminders=[Reminder.from_dict(r) for r in data.get("reminders", [])],
            completed=data.get("completed", False),
            attachments=list(data.get("attachments", [])),
            meeting_link=data.get("meeting_link", ""),
            created_at=_parse_dt(data.get("created_at")) or datetime.utcnow(),
            updated_at=_parse_dt(data.get("updated_at")) or datetime.utcnow(),
        )

    @classmethod
    def create(cls, calendar_id: str, title: str,
               start: datetime, end: Optional[datetime] = None,
               **kwargs) -> "Event":
        if end is None:
            end = start + timedelta(hours=1)
        return cls(
            id=f"evt-{uuid.uuid4().hex[:12]}",
            calendar_id=calendar_id,
            title=title,
            start=start,
            end=end,
            **kwargs,
        )


def _parse_dt(value) -> Optional[datetime]:
    if not value:
        return None
    if isinstance(value, datetime):
        return value
    try:
        return datetime.fromisoformat(value)
    except (ValueError, TypeError):
        return None
