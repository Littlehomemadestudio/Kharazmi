"""
CalendarStore — the in-memory container for all calendars and events.

This is the calendar subsystem's equivalent of the Enterprise plan's
Project aggregate root. It owns Calendar and Event objects, enforces
invariants, and emits events that the UI listens to.

A single CalendarStore is shared by the entire Basic plan window.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Callable, Iterator, Optional

from .calendar import Calendar
from .event import Event
from .enums import EventType, EventStatus
from .recurrence import RecurrenceRule


# ---- Events emitted by the store ----

@dataclass(frozen=True)
class CalendarEvent:
    """Base class for store events (not to be confused with calendar Event)."""
    pass


@dataclass(frozen=True)
class CalendarAdded(CalendarEvent):
    calendar_id: str = ""


@dataclass(frozen=True)
class CalendarRemoved(CalendarEvent):
    calendar_id: str = ""


@dataclass(frozen=True)
class CalendarUpdated(CalendarEvent):
    calendar_id: str = ""


@dataclass(frozen=True)
class CalendarVisibilityChanged(CalendarEvent):
    calendar_id: str = ""
    visible: bool = True


@dataclass(frozen=True)
class EventAdded(CalendarEvent):
    event_id: str = ""


@dataclass(frozen=True)
class EventUpdated(CalendarEvent):
    event_id: str = ""


@dataclass(frozen=True)
class EventRemoved(CalendarEvent):
    event_id: str = ""


StoreListener = Callable[[CalendarEvent], None]


class CalendarStore:
    """
    In-memory container for calendars + events.

    Thread-unsafe (we run everything on the Qt main thread). All
    mutations go through this class so invariants are enforced.
    """

    def __init__(self) -> None:
        self._calendars: dict[str, Calendar] = {}
        self._events: dict[str, Event] = {}
        self._listeners: list[StoreListener] = []

        # Seed a default calendar
        default = Calendar(
            id="cal-default",
            name="Personal",
            color="#D4AF37",
            is_default=True,
        )
        self._calendars[default.id] = default

    # ---- Subscription ----
    def subscribe(self, listener: StoreListener) -> None:
        self._listeners.append(listener)

    def _emit(self, event: CalendarEvent) -> None:
        for listener in list(self._listeners):
            try:
                listener(event)
            except Exception:
                pass

    # ---- Calendar CRUD ----
    def add_calendar(self, calendar: Calendar) -> Calendar:
        if calendar.id in self._calendars:
            raise ValueError(f"Calendar {calendar.id} already exists")
        self._calendars[calendar.id] = calendar
        self._emit(CalendarAdded(calendar_id=calendar.id))
        return calendar

    def create_calendar(self, name: str, color: str = "#D4AF37",
                        description: str = "") -> Calendar:
        cal = Calendar.create(name=name, color=color, description=description)
        return self.add_calendar(cal)

    def get_calendar(self, cal_id: str) -> Optional[Calendar]:
        return self._calendars.get(cal_id)

    def require_calendar(self, cal_id: str) -> Calendar:
        cal = self.get_calendar(cal_id)
        if cal is None:
            raise KeyError(f"No such calendar: {cal_id}")
        return cal

    def update_calendar(self, cal_id: str, **changes) -> None:
        cal = self.require_calendar(cal_id)
        for k, v in changes.items():
            if hasattr(cal, k):
                setattr(cal, k, v)
        self._emit(CalendarUpdated(calendar_id=cal_id))

    def set_calendar_visible(self, cal_id: str, visible: bool) -> None:
        cal = self.get_calendar(cal_id)
        if cal is None or cal.visible == visible:
            return
        cal.visible = visible
        self._emit(CalendarVisibilityChanged(calendar_id=cal_id, visible=visible))

    def delete_calendar(self, cal_id: str) -> None:
        cal = self.get_calendar(cal_id)
        if cal is None or cal.is_default:
            return  # can't delete default
        # Delete all events on this calendar
        events_to_remove = [
            eid for eid, evt in self._events.items() if evt.calendar_id == cal_id
        ]
        for eid in events_to_remove:
            del self._events[eid]
            self._emit(EventRemoved(event_id=eid))
        del self._calendars[cal_id]
        self._emit(CalendarRemoved(calendar_id=cal_id))

    def calendars(self) -> Iterator[Calendar]:
        return iter(self._calendars.values())

    def visible_calendars(self) -> Iterator[Calendar]:
        return (c for c in self._calendars.values() if c.visible)

    @property
    def calendar_count(self) -> int:
        return len(self._calendars)

    # ---- Event CRUD ----
    def add_event(self, event: Event) -> Event:
        if event.calendar_id not in self._calendars:
            raise KeyError(f"Calendar {event.calendar_id} does not exist")
        if event.id in self._events:
            raise ValueError(f"Event {event.id} already exists")
        self._events[event.id] = event
        self._emit(EventAdded(event_id=event.id))
        return event

    def create_event(self, calendar_id: str, title: str,
                     start: datetime, end: Optional[datetime] = None,
                     **kwargs) -> Event:
        evt = Event.create(calendar_id=calendar_id, title=title,
                            start=start, end=end, **kwargs)
        return self.add_event(evt)

    def get_event(self, event_id: str) -> Optional[Event]:
        return self._events.get(event_id)

    def require_event(self, event_id: str) -> Event:
        evt = self.get_event(event_id)
        if evt is None:
            raise KeyError(f"No such event: {event_id}")
        return evt

    def update_event(self, event_id: str, **changes) -> None:
        evt = self.require_event(event_id)
        for k, v in changes.items():
            if hasattr(evt, k):
                setattr(evt, k, v)
        evt.touch()
        self._emit(EventUpdated(event_id=event_id))

    def delete_event(self, event_id: str) -> None:
        if event_id in self._events:
            del self._events[event_id]
            self._emit(EventRemoved(event_id=event_id))

    def events(self) -> Iterator[Event]:
        return iter(self._events.values())

    def events_in_calendar(self, cal_id: str) -> Iterator[Event]:
        return (e for e in self._events.values() if e.calendar_id == cal_id)

    @property
    def event_count(self) -> int:
        return len(self._events)

    # ---- Queries ----
    def events_in_range(self, start: datetime, end: datetime,
                        include_invisible: bool = False) -> list[Event]:
        """
        Return all events (including expanded recurring occurrences)
        that overlap the [start, end) window.

        Recurring events are expanded on-the-fly: each occurrence
        becomes a virtual Event with the same id but a different
        start/end. The original Event is preserved unchanged.
        """
        visible_cal_ids = (
            {c.id for c in self._calendars.values()}
            if include_invisible else
            {c.id for c in self.visible_calendars()}
        )
        results: list[Event] = []
        for evt in self._events.values():
            if evt.calendar_id not in visible_cal_ids:
                continue
            if evt.status == EventStatus.CANCELLED:
                continue
            if not evt.is_recurring:
                if evt.overlaps(start, end):
                    results.append(evt)
            else:
                # Expand recurrence
                duration = evt.duration
                for occ_start in evt.recurrence.expand(evt.start, start, end):
                    occ_end = occ_start + duration
                    if occ_start < end and start < occ_end:
                        # Clone the event but with new times
                        occ = Event(
                            id=evt.id,
                            calendar_id=evt.calendar_id,
                            title=evt.title,
                            description=evt.description,
                            location=evt.location,
                            start=occ_start,
                            end=occ_end,
                            all_day=evt.all_day,
                            timezone=evt.timezone,
                            event_type=evt.event_type,
                            availability=evt.availability,
                            status=evt.status,
                            color=evt.color,
                            recurrence=None,  # occurrence is not itself recurring
                            attendees=list(evt.attendees),
                            reminders=list(evt.reminders),
                            completed=evt.completed,
                            attachments=list(evt.attachments),
                            meeting_link=evt.meeting_link,
                            created_at=evt.created_at,
                            updated_at=evt.updated_at,
                        )
                        results.append(occ)
        return results

    def events_on_day(self, day: datetime.date) -> list[Event]:
        """All events on the given calendar day."""
        start = datetime.combine(day, datetime.min.time())
        end = datetime.combine(day, datetime.max.time())
        return self.events_in_range(start, end)

    def search(self, query: str) -> list[Event]:
        """Search events by title, description, location, or attendee."""
        q = query.lower().strip()
        if not q:
            return []
        results = []
        for evt in self._events.values():
            if (q in evt.title.lower() or
                q in evt.description.lower() or
                q in evt.location.lower() or
                any(q in a.name.lower() or q in a.email.lower() for a in evt.attendees)):
                results.append(evt)
        return results

    # ---- Serialisation ----
    def to_dict(self) -> dict:
        return {
            "calendars": [c.to_dict() for c in self._calendars.values()],
            "events": [e.to_dict() for e in self._events.values()],
        }

    @classmethod
    def from_dict(cls, data: dict) -> "CalendarStore":
        store = cls()
        # Replace default calendar if data has calendars
        if data.get("calendars"):
            store._calendars.clear()
            for c_data in data["calendars"]:
                try:
                    cal = Calendar.from_dict(c_data)
                    store._calendars[cal.id] = cal
                except Exception:
                    continue
            # Ensure there's always a default
            if not any(c.is_default for c in store._calendars.values()):
                first = next(iter(store._calendars.values()), None)
                if first:
                    first.is_default = True
        for e_data in data.get("events", []):
            try:
                evt = Event.from_dict(e_data)
                if evt.calendar_id in store._calendars:
                    store._events[evt.id] = evt
            except Exception:
                continue
        return store
