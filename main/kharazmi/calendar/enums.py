"""
Calendar domain enums.

The Basic plan's calendar subsystem has its own value types, distinct
from the Enterprise task-graph domain. These enums define the legal
values for events and calendars.
"""
from __future__ import annotations

from enum import Enum, unique


@unique
class EventType(str, Enum):
    """What kind of calendar entry this is."""
    NORMAL = "normal"
    MEETING = "meeting"
    APPOINTMENT = "appointment"
    BIRTHDAY = "birthday"
    HOLIDAY = "holiday"
    FOCUS_TIME = "focus_time"
    OUT_OF_OFFICE = "out_of_office"
    WORKING_LOCATION = "working_location"
    TASK = "task"           # Google Tasks appear as checkbox items
    REMINDER = "reminder"


@unique
class Availability(str, Enum):
    """How this event affects the user's free/busy status."""
    BUSY = "busy"
    FREE = "free"
    TENTATIVE = "tentative"
    WORKING_ELSEWHERE = "working_elsewhere"


@unique
class RecurrenceFrequency(str, Enum):
    """How often a recurring event repeats."""
    DAILY = "daily"
    WEEKLY = "weekly"
    MONTHLY = "monthly"
    YEARLY = "yearly"


@unique
class ReminderMethod(str, Enum):
    """How a reminder is delivered."""
    POPUP = "popup"
    EMAIL = "email"


@unique
class AttendeeStatus(str, Enum):
    """RSVP response of an attendee."""
    NEEDS_ACTION = "needs_action"
    ACCEPTED = "accepted"
    DECLINED = "declined"
    TENTATIVE = "tentative"


@unique
class EventStatus(str, Enum):
    """Status of an event."""
    CONFIRMED = "confirmed"
    TENTATIVE = "tentative"
    CANCELLED = "cancelled"


@unique
class CalendarViewKind(str, Enum):
    """The set of legal calendar views."""
    DAY = "day"
    WEEK = "week"
    MONTH = "month"
    YEAR = "year"
    SCHEDULE = "schedule"
    CUSTOM = "custom"   # N-day view


@unique
class Weekday(int, Enum):
    """Iranian week: Saturday=0 ... Friday=6."""
    SATURDAY = 0
    SUNDAY = 1
    MONDAY = 2
    TUESDAY = 3
    WEDNESDAY = 4
    THURSDAY = 5
    FRIDAY = 6
