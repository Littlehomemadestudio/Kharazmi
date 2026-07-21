"""
CalendarController — Navigation, CRUD, and command orchestration.

The controller sits between the model and the views. It manages:
  - Current view kind (month / week / day / year)
  - Current navigation date (which month/week/day is in view)
  - Event creation via double-click or drag
  - Event editing via dialog
  - Drag-and-drop movement
  - Event resize
  - Natural-language input parsing
  - Store subscription → view refresh
"""
from __future__ import annotations

from datetime import datetime, timedelta
from typing import Optional

from PySide6.QtCore import QObject, Signal, QTimer
from PySide6.QtWidgets import QWidget

from ...calendar.store import CalendarStore, CalendarEvent, EventAdded, EventUpdated, EventRemoved
from ...calendar.event import Event
from ...calendar.enums import CalendarViewKind, EventType, EventStatus
from ...calendar.natural_language import parse as nl_parse
from ...core.shamsi import ShamsiDate, days_in_month
from .model import CalendarModel
from .selection import SelectionManager


class CalendarController(QObject):
    """Orchestrates calendar navigation and mutations."""

    # ── Signals ──
    view_changed = Signal(str)           # CalendarViewKind value
    date_changed = Signal()              # navigation date changed
    events_changed = Signal()            # events added/updated/removed
    selection_changed = Signal()         # forwarded from SelectionManager

    def __init__(self, store: CalendarStore, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._model = CalendarModel(store)
        self._selection = SelectionManager()
        self._view_kind: CalendarViewKind = CalendarViewKind.MONTH
        self._nav_date: ShamsiDate = ShamsiDate.today()  # the "focal" date

        # Wire store events → refresh
        store.subscribe(self._on_store_event)

        # Forward selection signals
        self._selection.selection_changed.connect(self.selection_changed.emit)

    # ── Properties ──

    @property
    def model(self) -> CalendarModel:
        return self._model

    @property
    def selection(self) -> SelectionManager:
        return self._selection

    @property
    def view_kind(self) -> CalendarViewKind:
        return self._view_kind

    @property
    def nav_date(self) -> ShamsiDate:
        return self._nav_date

    # ── View Switching ──

    def set_view(self, kind: CalendarViewKind) -> None:
        if self._view_kind != kind:
            self._view_kind = kind
            self.view_changed.emit(kind.value)

    def set_view_value(self, val: str) -> None:
        try:
            self.set_view(CalendarViewKind(val))
        except ValueError:
            pass

    # ── Navigation ──

    def go_today(self) -> None:
        self._nav_date = ShamsiDate.today()
        self._selection.go_to_today()
        self.date_changed.emit()

    def go_next(self) -> None:
        if self._view_kind == CalendarViewKind.MONTH:
            self._nav_date = self._nav_date.add_months(1)
        elif self._view_kind == CalendarViewKind.WEEK:
            self._nav_date = self._nav_date.add_days(7)
        elif self._view_kind == CalendarViewKind.DAY:
            self._nav_date = self._nav_date.add_days(1)
        elif self._view_kind == CalendarViewKind.YEAR:
            self._nav_date = ShamsiDate(self._nav_date.year + 1, 1, 1)
        self.date_changed.emit()

    def go_prev(self) -> None:
        if self._view_kind == CalendarViewKind.MONTH:
            self._nav_date = self._nav_date.add_months(-1)
        elif self._view_kind == CalendarViewKind.WEEK:
            self._nav_date = self._nav_date.add_days(-7)
        elif self._view_kind == CalendarViewKind.DAY:
            self._nav_date = self._nav_date.add_days(-1)
        elif self._view_kind == CalendarViewKind.YEAR:
            self._nav_date = ShamsiDate(self._nav_date.year - 1, 1, 1)
        self.date_changed.emit()

    def go_to_date(self, d: ShamsiDate) -> None:
        self._nav_date = d
        self._selection.selected_date = d
        self.date_changed.emit()

    # ── Navigation Title ──

    def nav_title(self) -> str:
        d = self._nav_date
        if self._view_kind == CalendarViewKind.MONTH:
            return f"{d.month_name_fa} {d.year}"
        elif self._view_kind == CalendarViewKind.WEEK:
            # Show the week range
            wd = d.to_gregorian().weekday()
            offset_map = {5: 0, 6: 1, 0: 2, 1: 3, 2: 4, 3: 5, 4: 6}
            day_offset = offset_map.get(wd, 0)
            sat = d.add_days(-day_offset)
            fri = sat.add_days(6)
            return f"{sat.month_name_fa} {sat.day} – {fri.day}"
        elif self._view_kind == CalendarViewKind.DAY:
            return f"{d.weekday_fa} {d.day} {d.month_name_fa}"
        elif self._view_kind == CalendarViewKind.YEAR:
            return str(d.year)
        return ""

    # ── Event CRUD ──

    def create_event_at(
        self,
        start: datetime,
        end: Optional[datetime] = None,
        title: str = "",
        all_day: bool = False,
    ) -> Event:
        """Create a new event at the given time. Returns the new event."""
        if end is None:
            if all_day:
                end = start + timedelta(days=1)
            else:
                end = start + timedelta(hours=1)

        # Use the default calendar
        default_cal = None
        for cal in self._model.calendars():
            if cal.is_default:
                default_cal = cal
                break
        if default_cal is None:
            default_cal = next(iter(self._model.calendars()), None)
        cal_id = default_cal.id if default_cal else "cal-default"

        evt = self._model.create_event(
            cal_id, title or "رویداد جدید", start, end,
            all_day=all_day,
        )
        self._selection.selected_event_id = evt.id
        return evt

    def create_event_from_nl(self, text: str) -> Optional[Event]:
        """Parse natural language text and create an event."""
        parsed = nl_parse(text)
        if parsed is None:
            return None

        now = datetime.utcnow()
        start = parsed.start or now
        end = parsed.end or (start + timedelta(hours=1))

        default_cal = None
        for cal in self._model.calendars():
            if cal.is_default:
                default_cal = cal
                break
        if default_cal is None:
            default_cal = next(iter(self._model.calendars()), None)
        cal_id = default_cal.id if default_cal else "cal-default"

        evt = self._model.create_event(
            cal_id, parsed.title or "رویداد", start, end,
            all_day=parsed.all_day,
        )
        return evt

    def move_event(self, event_id: str, new_start: datetime) -> None:
        self._model.move_event(event_id, new_start)
        self.events_changed.emit()

    def resize_event(self, event_id: str, new_end: datetime) -> None:
        self._model.resize_event(event_id, new_end)
        self.events_changed.emit()

    def delete_event(self, event_id: str) -> None:
        self._model.delete_event(event_id)
        self.events_changed.emit()

    def toggle_event_completed(self, event_id: str) -> None:
        """Toggle the completed state of an event. Uses store.update_event
        so the change is properly emitted and persisted.

        When marking a non-task event complete, its event_type is changed
        to TASK so it gets the checkbox rendering."""
        evt = self._model.store.get_event(event_id)
        if evt:
            new_completed = not evt.completed
            updates: dict = {
                "completed": new_completed,
            }
            # When marking complete, promote to TASK type if not already
            if new_completed and evt.event_type != EventType.TASK:
                updates["event_type"] = EventType.TASK
            self._model.store.update_event(event_id, **updates)
            # events_changed will be emitted via the store subscription

    # ── Store Events ──

    def _on_store_event(self, event: CalendarEvent) -> None:
        """Forward store events to views."""
        QTimer.singleShot(0, self.events_changed.emit)
