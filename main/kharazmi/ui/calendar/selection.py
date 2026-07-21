"""
SelectionManager — Keyboard navigation and selection for the calendar.

Manages:
  - Current selected date (Shamsi)
  - Current selected event ID
  - Multi-date selection (Shift+Click, Shift+Arrow)
  - Keyboard navigation (arrows, page up/down, Home, End)
  - Focus tracking (which view has focus)

Emits signals that views listen to for repaints.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Optional

from PySide6.QtCore import QObject, Signal

from ...core.shamsi import ShamsiDate, shamsi_month_grid


class SelectionManager(QObject):
    """Centralized selection state for the calendar subsystem."""

    # ── Signals ──
    selection_changed = Signal()          # date or event selection changed
    date_activated = Signal(object)       # double-click / Enter on a date
    event_activated = Signal(str)         # double-click / Enter on an event

    def __init__(self) -> None:
        super().__init__()
        self._selected_date: ShamsiDate = ShamsiDate.today()
        self._anchor_date: Optional[ShamsiDate] = None   # for shift-select range
        self._selected_event_id: Optional[str] = None
        self._hovered_date: Optional[ShamsiDate] = None
        self._hovered_event_id: Optional[str] = None

    # ── Properties ──

    @property
    def selected_date(self) -> ShamsiDate:
        return self._selected_date

    @selected_date.setter
    def selected_date(self, d: ShamsiDate) -> None:
        if self._selected_date != d:
            self._selected_date = d
            self.selection_changed.emit()

    @property
    def anchor_date(self) -> Optional[ShamsiDate]:
        return self._anchor_date

    @property
    def selected_event_id(self) -> Optional[str]:
        return self._selected_event_id

    @selected_event_id.setter
    def selected_event_id(self, eid: Optional[str]) -> None:
        if self._selected_event_id != eid:
            self._selected_event_id = eid
            self.selection_changed.emit()

    @property
    def hovered_date(self) -> Optional[ShamsiDate]:
        return self._hovered_date

    @hovered_date.setter
    def hovered_date(self, d: Optional[ShamsiDate]) -> None:
        self._hovered_date = d

    @property
    def hovered_event_id(self) -> Optional[str]:
        return self._hovered_event_id

    @hovered_event_id.setter
    def hovered_event_id(self, eid: Optional[str]) -> None:
        self._hovered_event_id = eid

    # ── Range Selection ──

    def selection_range(self) -> Optional[tuple[ShamsiDate, ShamsiDate]]:
        """Return (start, end) if a range is selected via Shift, else None."""
        if self._anchor_date and self._anchor_date != self._selected_date:
            a = self._anchor_date.to_gregorian()
            b = self._selected_date.to_gregorian()
            if a <= b:
                return (self._anchor_date, self._selected_date)
            else:
                return (self._selected_date, self._anchor_date)
        return None

    def start_range(self) -> None:
        """Begin a shift-selection (anchor = current date)."""
        self._anchor_date = self._selected_date

    def end_range(self) -> None:
        """End a shift-selection."""
        self._anchor_date = None

    # ── Keyboard Navigation ──

    def move(self, direction: str, extend: bool = False) -> None:
        """
        Move selection in the given direction.

        direction: 'left', 'right', 'up', 'down', 'page_up', 'page_down',
                   'home', 'end'
        extend: if True, extend range (Shift key held)
        """
        d = self._selected_date

        if direction == "left":
            new = d.add_days(-1)
        elif direction == "right":
            new = d.add_days(1)
        elif direction == "up":
            new = d.add_days(-7)
        elif direction == "down":
            new = d.add_days(7)
        elif direction == "page_up":
            new = d.add_months(-1)
        elif direction == "page_down":
            new = d.add_months(1)
        elif direction == "home":
            new = ShamsiDate(d.year, d.month, 1)
        elif direction == "end":
            from ...core.shamsi import days_in_month
            new = ShamsiDate(d.year, d.month, days_in_month(d.year, d.month))
        elif direction == "today":
            new = ShamsiDate.today()
        else:
            return

        if extend:
            if self._anchor_date is None:
                self._anchor_date = d
        else:
            self._anchor_date = None

        self._selected_date = new
        self.selection_changed.emit()

    def go_to_today(self) -> None:
        self._anchor_date = None
        self._selected_date = ShamsiDate.today()
        self.selection_changed.emit()

    # ── Date Activation ──

    def activate_date(self, d: ShamsiDate) -> None:
        """User double-clicked / pressed Enter on a date."""
        self._selected_date = d
        self.date_activated.emit(d)

    def activate_event(self, event_id: str) -> None:
        """User double-clicked / pressed Enter on an event."""
        self._selected_event_id = event_id
        self.event_activated.emit(event_id)
