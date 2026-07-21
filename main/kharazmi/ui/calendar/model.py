"""
CalendarModel — Data layer for the RASK! calendar.

Wraps CalendarStore and adds Shamsi-aware date-range queries,
event layout computation, and filtering. Views never access
CalendarStore directly — they go through this model.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, date
from typing import Optional

from ...calendar.store import CalendarStore
from ...calendar.event import Event
from ...calendar.calendar import Calendar
from ...calendar.enums import CalendarViewKind, EventType
from ...core.shamsi import ShamsiDate, shamsi_month_grid, days_in_month


# ──────────────────────────────── Layout Types ────────────────────────────

@dataclass
class EventLayout:
    """Computed position for a timed event in a Day/Week view."""
    event: Event
    left: float = 0.0      # fraction 0..1
    width: float = 1.0     # fraction 0..1
    column: int = 0
    total_columns: int = 1


@dataclass
class DayEvents:
    """Events for a single day, split into all-day and timed."""
    date: ShamsiDate
    all_day: list[Event] = field(default_factory=list)
    timed: list[Event] = field(default_factory=list)
    timed_layout: list[EventLayout] = field(default_factory=list)


# ──────────────────────────────── Model ───────────────────────────────────

class CalendarModel:
    """
    Shamsi-aware data model for the calendar views.

    All date queries are in Jalali. Internally converts to Gregorian
    for CalendarStore range queries.
    """

    def __init__(self, store: CalendarStore) -> None:
        self._store = store

    # ── Store Access ──

    @property
    def store(self) -> CalendarStore:
        return self._store

    def calendars(self) -> list[Calendar]:
        return list(self._store.calendars())

    def visible_calendars(self) -> list[Calendar]:
        return list(self._store.visible_calendars())

    def calendar_for_event(self, event: Event) -> Optional[Calendar]:
        return self._store.get_calendar(event.calendar_id)

    def event_color(self, event: Event) -> str:
        """Return the display color for an event (event override, or calendar color)."""
        if event.color:
            return event.color
        cal = self.calendar_for_event(event)
        return cal.color if cal else "#D4AF37"

    # ── Shamsi Date Range Queries ──

    def events_on_day(self, shamsi: ShamsiDate) -> list[Event]:
        """All events on a Shamsi day."""
        g = shamsi.to_gregorian()
        return self._store.events_on_day(g)

    def events_in_shamsi_range(
        self, start: ShamsiDate, end: ShamsiDate,
    ) -> list[Event]:
        """All events in [start, end) Shamsi date range."""
        g_start = datetime.combine(start.to_gregorian(), datetime.min.time())
        g_end = datetime.combine(
            end.to_gregorian() + timedelta(days=1), datetime.min.time()
        )
        return self._store.events_in_range(g_start, g_end)

    def events_in_month(self, year: int, month: int) -> list[Event]:
        """All events in a Shamsi month."""
        first = ShamsiDate(year, month, 1)
        dim = days_in_month(year, month)
        last = ShamsiDate(year, month, dim)
        return self.events_in_shamsi_range(first, last)

    def events_in_week(self, containing: ShamsiDate) -> list[Event]:
        """All events in the Iranian week containing `containing`."""
        # Iranian week: Sat=0 .. Fri=6
        wd = containing.to_gregorian().weekday()
        # Python weekday: Mon=0 .. Sun=6
        # Iranian week starts Saturday
        # Sat in Python = 5, Sun=6, Mon=0, Tue=1, Wed=2, Thu=3, Fri=4
        offset_map = {5: 0, 6: 1, 0: 2, 1: 3, 2: 4, 3: 5, 4: 6}
        day_offset = offset_map.get(wd, 0)
        sat = containing.add_days(-day_offset)
        fri = sat.add_days(6)
        return self.events_in_shamsi_range(sat, fri)

    # ── Structured Day Queries ──

    def day_events(self, shamsi: ShamsiDate) -> DayEvents:
        """Get events for a day, split into all-day and timed."""
        all_events = self.events_on_day(shamsi)
        all_day = []
        timed = []
        for e in all_events:
            if e.all_day:
                all_day.append(e)
            else:
                timed.append(e)
        return DayEvents(date=shamsi, all_day=all_day, timed=timed)

    # ── Event Layout (collision detection) ──

    def compute_timed_layout(self, events: list[Event]) -> list[EventLayout]:
        """
        Compute overlap layout for timed events.

        Uses a greedy column-assignment algorithm:
        1. Sort events by start time, then by duration (longer first).
        2. For each event, find the first column that doesn't overlap.
        3. After assignment, compute width fractions.
        """
        if not events:
            return []

        sorted_events = sorted(
            events,
            key=lambda e: (e.start, -(e.end - e.start).total_seconds()),
        )

        # Column assignment
        columns: list[list[Event]] = []
        event_columns: dict[str, int] = {}

        for evt in sorted_events:
            placed = False
            for col_idx, col in enumerate(columns):
                # Check if evt overlaps any event in this column
                overlaps = False
                for existing in col:
                    if evt.start < existing.end and existing.start < evt.end:
                        overlaps = True
                        break
                if not overlaps:
                    col.append(evt)
                    event_columns[evt.id] = col_idx
                    placed = True
                    break
            if not placed:
                event_columns[evt.id] = len(columns)
                columns.append([evt])

        # Compute max columns per time slot
        total_cols = max(len(columns), 1)

        # Build layout
        layouts: list[EventLayout] = []
        for evt in sorted_events:
            col = event_columns[evt.id]
            # Find how many columns are actually overlapping at this event's time
            max_col = 0
            for other_evt, other_col in event_columns.items():
                other = next((e for e in sorted_events if e.id == other_evt), None)
                if other and evt.start < other.end and other.start < evt.end:
                    max_col = max(max_col, other_col)
            local_total = max_col + 1

            width = 1.0 / local_total
            left = col * width
            layouts.append(EventLayout(
                event=evt,
                left=left,
                width=width,
                column=col,
                total_columns=local_total,
            ))

        return layouts

    # ── Month Grid ──

    def month_grid(self, year: int, month: int) -> list[list[Optional[ShamsiDate]]]:
        """6×7 grid of ShamsiDate for the month (Sat..Fri)."""
        return shamsi_month_grid(year, month)

    # ── CRUD ──

    def create_event(self, calendar_id: str, title: str,
                     start: datetime, end: Optional[datetime] = None,
                     **kwargs) -> Event:
        return self._store.create_event(calendar_id, title, start, end, **kwargs)

    def update_event(self, event_id: str, **changes) -> None:
        self._store.update_event(event_id, **changes)

    def delete_event(self, event_id: str) -> None:
        self._store.delete_event(event_id)

    def move_event(self, event_id: str, new_start: datetime) -> None:
        evt = self._store.get_event(event_id)
        if evt:
            evt.move_to(new_start)

    def resize_event(self, event_id: str, new_end: datetime) -> None:
        evt = self._store.get_event(event_id)
        if evt:
            evt.set_time(evt.start, new_end)

    # ── Search ──

    def search(self, query: str) -> list[Event]:
        return self._store.search(query)
