"""
ScheduleView — agenda-style list view (like Google Calendar's schedule view).

Shows upcoming events as a vertical list grouped by day:

  Today — Saturday, 5 Bahman 1405
  ────────────────────────────────────────
  09:00  Team standup              [Work]
  13:00  Lunch with Sarah          [Personal]

  Tomorrow — Sunday, 6 Bahman 1405
  ────────────────────────────────────────
  10:00  Project review            [Work]
  ...
"""
from __future__ import annotations

from datetime import datetime, timedelta
from typing import Optional

from PySide6.QtCore import Qt, Signal, QTimer, QSize
from PySide6.QtGui import (
    QPainter, QPen, QBrush, QColor, QFont, QMouseEvent,
)
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QFrame, QScrollArea,
    QSizePolicy, QPushButton, QSpacerItem,
)

from ...calendar import (
    CalendarStore, Event as CalEvent, Calendar,
    EventAdded, EventUpdated, EventRemoved, CalendarVisibilityChanged,
    EventType,
)
from ...core.shamsi import (
    ShamsiDate, format_shamsi, SHAMSI_MONTHS_FA, SHAMSI_WEEKDAYS_FA,
)
from ..theme import Palette


class ScheduleEventRow(QFrame):
    """A single event row in the schedule view."""
    clicked = Signal(str)
    doubleClicked = Signal(str)

    def __init__(self, event: CalEvent, calendar: Optional[Calendar],
                 parent: QWidget = None) -> None:
        super().__init__(parent)
        self.evt = event
        self.calendar = calendar
        self.setFixedHeight(56)
        self.setCursor(Qt.PointingHandCursor)
        self.setObjectName("scheduleRow")
        color = event.color or (calendar.color if calendar else Palette.GOLD_PRIMARY)
        self.setStyleSheet(f"""
            QFrame#scheduleRow {{
                background-color: {Palette.BG_TERTIARY};
                border-left: 3px solid {color};
                border-radius: 3px;
                margin: 2px 0;
            }}
            QFrame#scheduleRow:hover {{
                background-color: {Palette.BG_ELEVATED};
            }}
        """)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(12, 6, 12, 6)
        layout.setSpacing(12)

        # Time column
        time_col = QVBoxLayout()
        time_col.setSpacing(0)
        start_time = event.start.strftime("%H:%M")
        end_time = event.end.strftime("%H:%M")
        start_lbl = QLabel(start_time)
        start_lbl.setStyleSheet(
            f"color: {Palette.GOLD_BRIGHT}; font-size: 12px; "
            f"font-weight: bold; font-family: 'JetBrains Mono', monospace;"
        )
        end_lbl = QLabel(end_time)
        end_lbl.setStyleSheet(
            f"color: {Palette.TEXT_TERTIARY}; font-size: 10px; "
            f"font-family: 'JetBrains Mono', monospace;"
        )
        time_col.addWidget(start_lbl)
        time_col.addWidget(end_lbl)
        layout.addLayout(time_col)

        # Vertical separator
        sep = QFrame()
        sep.setFixedSize(1, 36)
        sep.setStyleSheet(f"background-color: {Palette.BORDER_SUBTLE};")
        layout.addWidget(sep)

        # Title + meta
        info_col = QVBoxLayout()
        info_col.setSpacing(2)
        title = QLabel(event.title)
        title.setStyleSheet(
            f"color: {Palette.TEXT_PRIMARY}; font-size: 13px; "
            f"font-weight: bold; background: transparent;"
        )
        info_col.addWidget(title)

        # Meta line
        meta_parts = []
        if event.location:
            meta_parts.append(f"📍 {event.location}")
        if event.attendees:
            meta_parts.append(f"👥 {' + '.join(a.name for a in event.attendees[:2])}"
                              + (f" +{len(event.attendees)-2}" if len(event.attendees) > 2 else ""))
        if calendar:
            meta_parts.append(f"[{calendar.name}]")
        if event.is_recurring:
            meta_parts.append("🔁 recurring")
        if event.event_type != EventType.NORMAL:
            meta_parts.append(f"({event.event_type.value})")
        if meta_parts:
            meta = QLabel("  •  ".join(meta_parts))
            meta.setStyleSheet(
                f"color: {Palette.TEXT_SECONDARY}; font-size: 10px; "
                f"background: transparent;"
            )
            info_col.addWidget(meta)
        layout.addLayout(info_col, stretch=1)

        # Calendar color dot
        dot = QFrame()
        dot.setFixedSize(8, 8)
        dot.setStyleSheet(
            f"background-color: {color}; border-radius: 4px;"
        )
        layout.addWidget(dot)

    def mousePressEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.LeftButton:
            self.clicked.emit(self.evt.id)
        super().mousePressEvent(event)

    def mouseDoubleClickEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.LeftButton:
            self.doubleClicked.emit(self.evt.id)
        super().mouseDoubleClickEvent(event)


class ScheduleView(QScrollArea):
    """Agenda-style list of upcoming events."""

    eventDoubleClicked = Signal(str)
    eventClicked = Signal(str)

    def __init__(self, store: CalendarStore, parent: QWidget = None) -> None:
        super().__init__(parent)
        self.store = store
        self._days_ahead = 30  # show next 30 days by default
        self.setWidgetResizable(True)
        self.setFrameShape(QFrame.NoFrame)
        self.setStyleSheet(f"QScrollArea {{ background-color: {Palette.BG_PRIMARY}; border: none; }}")

        self._container = QWidget()
        self._container.setStyleSheet(f"background-color: {Palette.BG_PRIMARY};")
        self._layout = QVBoxLayout(self._container)
        self._layout.setContentsMargins(20, 20, 20, 20)
        self._layout.setSpacing(0)
        self.setWidget(self._container)

        self.store.subscribe(self._on_store_event)
        self.refresh()

    def _on_store_event(self, event: CalEvent) -> None:
        from ...calendar import (
            EventAdded, EventUpdated, EventRemoved, CalendarVisibilityChanged,
        )
        if isinstance(event, (EventAdded, EventUpdated, EventRemoved,
                               CalendarVisibilityChanged)):
            QTimer.singleShot(0, self.refresh)

    def set_days_ahead(self, days: int) -> None:
        self._days_ahead = days
        self.refresh()

    def refresh(self) -> None:
        # Clear
        while self._layout.count():
            item = self._layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        today = ShamsiDate.today()
        now = datetime.now()

        # Header
        title = QLabel("Schedule")
        title.setStyleSheet(
            f"color: {Palette.GOLD_BRIGHT}; font-size: 22px; "
            f"font-weight: bold; padding: 0 0 12px 0; "
            f"border-bottom: 1px solid {Palette.BORDER_SUBTLE};"
        )
        self._layout.addWidget(title)

        subtitle = QLabel(
            f"Next {self._days_ahead} days  •  starting {today.format('d MMMM yyyy')}"
        )
        subtitle.setStyleSheet(
            f"color: {Palette.TEXT_TERTIARY}; font-size: 11px; padding: 8px 0 16px 0;"
        )
        self._layout.addWidget(subtitle)

        any_events = False
        for day_offset in range(self._days_ahead):
            sd = today.add_days(day_offset)
            day_start = sd.to_datetime(0, 0)
            day_end = sd.to_datetime(23, 59)
            events = self.store.events_in_range(day_start, day_end)
            if not events:
                continue
            any_events = True

            # Day header
            if day_offset == 0:
                day_label = "Today"
            elif day_offset == 1:
                day_label = "Tomorrow"
            else:
                day_label = sd.weekday_short_en
            header = QLabel(
                f"{day_label}  —  {sd.weekday_fa}, {sd.day} {sd.month_name_fa} {sd.year}"
            )
            header.setStyleSheet(
                f"color: {Palette.GOLD_PRIMARY}; font-size: 13px; "
                f"font-weight: bold; padding: 16px 0 6px 0; "
                f"letter-spacing: 0.3px;"
            )
            self._layout.addWidget(header)

            # Divider
            divider = QFrame()
            divider.setFixedHeight(1)
            divider.setStyleSheet(f"background-color: {Palette.BORDER_SUBTLE};")
            self._layout.addWidget(divider)

            # Events (sorted by start time)
            events.sort(key=lambda e: (not e.all_day, e.start))
            for evt in events:
                cal = self.store.get_calendar(evt.calendar_id)
                row = ScheduleEventRow(evt, cal)
                row.clicked.connect(self.eventClicked.emit)
                row.doubleClicked.connect(self.eventDoubleClicked.emit)
                self._layout.addWidget(row)

        if not any_events:
            empty = QLabel(f"No events in the next {self._days_ahead} days.")
            empty.setStyleSheet(
                f"color: {Palette.TEXT_TERTIARY}; font-size: 13px; "
                f"padding: 40px; font-style: italic;"
            )
            empty.setAlignment(Qt.AlignCenter)
            self._layout.addWidget(empty)

        self._layout.addStretch()
