"""
TimeGridView — shared base for Day / Week / Custom N-day views.

Renders a vertical time grid (00:00 to 23:59) with one or more day
columns. Events are positioned absolutely within their day column
based on start/end times.

This is the workhorse view — DayView and WeekView are thin wrappers
that just set the number of columns.
"""
from __future__ import annotations

from datetime import datetime, timedelta, time
from typing import Optional

from PySide6.QtCore import Qt, QRectF, QPointF, QSize, Signal, QPoint, QTimer
from PySide6.QtGui import (
    QPainter, QPen, QBrush, QColor, QFont, QPainterPath, QMouseEvent,
    QWheelEvent, QKeyEvent, QFontMetrics, QLinearGradient,
)
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QFrame, QScrollArea,
    QGridLayout, QSizePolicy, QApplication,
)

from ...calendar import (
    CalendarStore, Event as CalEvent, Calendar,
    EventAdded, EventUpdated, EventRemoved,
    CalendarVisibilityChanged,
)
from ...core.shamsi import (
    ShamsiDate, iterate_week, days_in_month,
    SHAMSI_WEEKDAYS_FA, SHAMSI_WEEKDAYS_SHORT_EN, SHAMSI_MONTHS_FA,
)
from ..theme import Palette
from ..widgets.event_block import EventBlock


HOURS_PER_DAY = 24
PX_PER_MINUTE = 1.0  # 1px per minute → 60px per hour → 1440px per day
HOUR_HEIGHT = int(60 * PX_PER_MINUTE)
TIME_COLUMN_WIDTH = 60
DAY_HEADER_HEIGHT = 60


class TimeGridView(QWidget):
    """Base class for DayView, WeekView, CustomView."""

    eventDoubleClicked = Signal(str)
    eventMoveRequested = Signal(str, datetime)
    eventResizeRequested = Signal(str, int)
    dayDoubleClicked = Signal(object)  # ShamsiDate

    def __init__(self, store: CalendarStore, num_days: int = 1,
                 parent: QWidget = None) -> None:
        super().__init__(parent)
        self.store = store
        self.num_days = num_days
        self._anchor_date: ShamsiDate = ShamsiDate.today()
        self._px_per_minute = PX_PER_MINUTE

        self.setStyleSheet(f"background-color: {Palette.BG_PRIMARY};")

        # Subscribe to store events
        self.store.subscribe(self._on_store_event)

        self._build_ui()
        self.refresh()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # Header row: empty space | day headers
        self._header = QWidget()
        self._header.setFixedHeight(DAY_HEADER_HEIGHT)
        self._header.setStyleSheet(f"background-color: {Palette.BG_SECONDARY}; border-bottom: 1px solid {Palette.BORDER_SUBTLE};")
        header_layout = QHBoxLayout(self._header)
        header_layout.setContentsMargins(0, 0, 0, 0)
        header_layout.setSpacing(1)
        # Time column spacer
        spacer = QWidget()
        spacer.setFixedWidth(TIME_COLUMN_WIDTH)
        spacer.setStyleSheet(f"background-color: {Palette.BG_SECONDARY}; border-right: 1px solid {Palette.BORDER_SUBTLE};")
        header_layout.addWidget(spacer)
        # Day headers (added dynamically in _refresh_headers)
        self._header_layout = header_layout
        layout.addWidget(self._header)

        # Scrollable time grid
        self._scroll = QScrollArea()
        self._scroll.setWidgetResizable(True)
        self._scroll.setFrameShape(QFrame.NoFrame)
        self._scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self._scroll.setStyleSheet(f"QScrollArea {{ background-color: {Palette.BG_PRIMARY}; border: none; }}")

        self._grid_container = QWidget()
        self._grid_layout = QHBoxLayout(self._grid_container)
        self._grid_layout.setContentsMargins(0, 0, 0, 0)
        self._grid_layout.setSpacing(1)
        self._grid_layout.addWidget(self._build_time_column())
        self._day_columns: list[QWidget] = []
        self._day_column_layouts: list[QVBoxLayout] = []
        for i in range(self.num_days):
            col = self._build_day_column()
            self._grid_layout.addWidget(col, stretch=1)
            self._day_columns.append(col)
            self._day_column_layouts.append(col.layout())

        total_height = HOURS_PER_DAY * HOUR_HEIGHT
        self._grid_container.setFixedHeight(total_height)
        self._scroll.setWidget(self._grid_container)
        layout.addWidget(self._scroll, stretch=1)

    def _build_time_column(self) -> QWidget:
        col = QWidget()
        col.setFixedWidth(TIME_COLUMN_WIDTH)
        col.setStyleSheet(f"background-color: {Palette.BG_SECONDARY}; border-right: 1px solid {Palette.BORDER_SUBTLE};")
        col_layout = QVBoxLayout(col)
        col_layout.setContentsMargins(0, 0, 0, 0)
        col_layout.setSpacing(0)
        # Hour labels
        for hour in range(HOURS_PER_DAY):
            lbl = QLabel(f"{hour:02d}:00")
            lbl.setFixedHeight(HOUR_HEIGHT)
            lbl.setAlignment(Qt.AlignTop | Qt.AlignRight)
            lbl.setStyleSheet(
                f"color: {Palette.TEXT_TERTIARY}; font-size: 10px; "
                f"font-family: 'JetBrains Mono', monospace; padding: 2px 8px 0 0; "
                f"background: transparent;"
            )
            col_layout.addWidget(lbl)
        return col

    def _build_day_column(self) -> QWidget:
        col = QWidget()
        col.setStyleSheet(f"background-color: {Palette.BG_PRIMARY};")
        col_layout = QVBoxLayout(col)
        col_layout.setContentsMargins(0, 0, 0, 0)
        col_layout.setSpacing(0)
        # Hour rows (background grid)
        for hour in range(HOURS_PER_DAY):
            row = QWidget()
            row.setFixedHeight(HOUR_HEIGHT)
            row.setStyleSheet(
                f"background-color: {'transparent' if hour % 2 == 0 else Palette.BG_SECONDARY}; "
                f"border-bottom: 1px solid {Palette.BORDER_SUBTLE};"
            )
            # Make this row clickable for "click empty time to create event"
            row.mousePressEvent = lambda e, h=hour, parent=self: parent._on_empty_click(e, h)
            col_layout.addWidget(row)
        return col

    # ---- Store events ----
    def _on_store_event(self, event) -> None:
        from ...calendar import (
            EventAdded, EventUpdated, EventRemoved,
            CalendarVisibilityChanged,
        )
        if isinstance(event, (EventAdded, EventUpdated, EventRemoved,
                               CalendarVisibilityChanged)):
            QTimer.singleShot(0, self.refresh)

    # ---- Public API ----
    def set_anchor_date(self, sd: ShamsiDate) -> None:
        self._anchor_date = sd
        self.refresh()

    def set_num_days(self, n: int) -> None:
        if n == self.num_days:
            return
        # Rebuild columns
        self.num_days = n
        # Remove old day columns (keep time column at index 0)
        while len(self._day_columns) > 0:
            col = self._day_columns.pop()
            self._day_column_layouts.pop()
            self._grid_layout.removeWidget(col)
            col.deleteLater()
        # Add new ones
        for i in range(n):
            col = self._build_day_column()
            self._grid_layout.addWidget(col, stretch=1)
            self._day_columns.append(col)
            self._day_column_layouts.append(col.layout())
        self.refresh()

    def refresh(self) -> None:
        self._refresh_headers()
        self._refresh_events()

    def _refresh_headers(self) -> None:
        # Remove old day headers (keep the spacer at index 0)
        while self._header_layout.count() > 1:
            item = self._header_layout.takeAt(1)
            if item.widget():
                item.widget().deleteLater()
        # Compute day list
        days = self._get_visible_days()
        today = ShamsiDate.today()
        for sd in days:
            header = self._make_day_header(sd, sd == today)
            self._header_layout.addWidget(header, stretch=1)

    def _make_day_header(self, sd: ShamsiDate, is_today: bool) -> QWidget:
        header = QWidget()
        header.setStyleSheet(f"background-color: {Palette.BG_SECONDARY};")
        layout = QVBoxLayout(header)
        layout.setContentsMargins(4, 8, 4, 8)
        layout.setSpacing(2)

        # Weekday name
        wd_label = QLabel(sd.weekday_short_en.upper())
        wd_label.setStyleSheet(
            f"color: {Palette.TEXT_TERTIARY}; font-size: 10px; "
            f"font-weight: bold; letter-spacing: 1px;"
        )
        wd_label.setAlignment(Qt.AlignCenter)
        layout.addWidget(wd_label)

        # Day number (in a circle if today)
        day_label = QLabel(str(sd.day))
        if is_today:
            day_label.setStyleSheet(
                f"background-color: {Palette.GOLD_PRIMARY}; color: {Palette.TEXT_ON_GOLD}; "
                f"border-radius: 12px; min-width: 24px; min-height: 24px; "
                f"max-width: 24px; max-height: 24px; font-size: 13px; "
                f"font-weight: bold; padding: 0;"
            )
        else:
            day_label.setStyleSheet(
                f"color: {Palette.TEXT_PRIMARY}; font-size: 13px; "
                f"font-weight: bold; padding: 0;"
            )
        day_label.setAlignment(Qt.AlignCenter)
        day_label.setFixedHeight(24)
        layout.addWidget(day_label, alignment=Qt.AlignCenter)

        # Persian month name
        month_label = QLabel(sd.month_name_fa)
        month_label.setStyleSheet(
            f"color: {Palette.TEXT_TERTIARY}; font-size: 9px;"
        )
        month_label.setAlignment(Qt.AlignCenter)
        layout.addWidget(month_label)

        return header

    def _get_visible_days(self) -> list[ShamsiDate]:
        """Return the list of days this view should show."""
        # Default: num_days starting from anchor
        return [self._anchor_date.add_days(i) for i in range(self.num_days)]

    def _refresh_events(self) -> None:
        # Clear existing event blocks from each day column
        # Each column has HOURS_PER_DAY hour-row children at the top
        for col_layout in self._day_column_layouts:
            # Remove all widgets except the hour rows (first HOURS_PER_DAY)
            while col_layout.count() > HOURS_PER_DAY:
                item = col_layout.takeAt(HOURS_PER_DAY)
                if item.widget():
                    item.widget().deleteLater()

        # Get visible days
        days = self._get_visible_days()
        if len(days) != len(self._day_columns):
            return

        # For each day, fetch events and position them
        for day_idx, sd in enumerate(days):
            day_start = sd.to_datetime(0, 0)
            day_end = sd.to_datetime(23, 59)
            events = self.store.events_in_range(day_start, day_end)

            # Filter to events that start on this day (avoid duplicates for multi-day)
            day_events = [e for e in events if e.start.date() == sd.to_gregorian()]
            # Sort by start time
            day_events.sort(key=lambda e: e.start)

            # Simple layout: position events; detect overlaps and split into columns
            self._layout_events_for_day(day_idx, day_events)

    def _layout_events_for_day(self, day_idx: int, events: list[CalEvent]) -> None:
        """Position events in the day column, handling overlaps."""
        if not events:
            return
        col_layout = self._day_column_layouts[day_idx]
        col_widget = self._day_columns[day_idx]

        # Compute overlap groups (events that overlap each other)
        # Simple greedy: sort by start; for each event, find max overlap count
        # in its overlap group
        groups = self._compute_overlap_groups(events)

        for group in groups:
            # Within a group, assign each event a sub-column index
            sub_columns = self._assign_sub_columns(group)
            n_cols = max(sub_columns.values()) + 1 if sub_columns else 1
            for evt in group:
                sub_col = sub_columns.get(evt.id, 0)
                block = EventBlock(evt, self.store.get_calendar(evt.calendar_id),
                                    px_per_minute=self._px_per_minute,
                                    parent=col_widget)
                # Position: absolute
                start_minutes = evt.start.hour * 60 + evt.start.minute
                top = int(start_minutes * self._px_per_minute)
                height = max(20, int(evt.duration_minutes * self._px_per_minute))
                col_width = (col_widget.width() - 4) // n_cols
                x = 2 + sub_col * col_width
                block.setGeometry(x, top, col_width - 2, height)
                block.show()
                block.raise_()
                # Connect signals
                block.doubleClicked.connect(self.eventDoubleClicked.emit)
                block.moveRequested.connect(self._on_event_move)
                block.resizeRequested.connect(self._on_event_resize)

    def _compute_overlap_groups(self, events: list[CalEvent]) -> list[list[CalEvent]]:
        """Group events that overlap (directly or transitively)."""
        if not events:
            return []
        sorted_events = sorted(events, key=lambda e: e.start)
        groups: list[list[CalEvent]] = []
        current_group: list[CalEvent] = [sorted_events[0]]
        current_end = sorted_events[0].end
        for evt in sorted_events[1:]:
            if evt.start < current_end:
                current_group.append(evt)
                if evt.end > current_end:
                    current_end = evt.end
            else:
                groups.append(current_group)
                current_group = [evt]
                current_end = evt.end
        groups.append(current_group)
        return groups

    def _assign_sub_columns(self, group: list[CalEvent]) -> dict[str, int]:
        """Assign each event in an overlap group to a sub-column."""
        # Greedy: for each event, find the lowest sub-column index whose
        # previous event in that column has ended.
        sorted_events = sorted(group, key=lambda e: e.start)
        columns: list[datetime] = []  # end time of last event in each column
        assignment: dict[str, int] = {}
        for evt in sorted_events:
            placed = False
            for i, col_end in enumerate(columns):
                if evt.start >= col_end:
                    columns[i] = evt.end
                    assignment[evt.id] = i
                    placed = True
                    break
            if not placed:
                columns.append(evt.end)
                assignment[evt.id] = len(columns) - 1
        return assignment

    # ---- Event interaction ----
    def _on_event_move(self, event_id: str, new_start: datetime) -> None:
        evt = self.store.get_event(event_id)
        if evt is None:
            return
        # Don't actually mutate during drag — emit signal and let controller handle
        self.eventMoveRequested.emit(event_id, new_start)

    def _on_event_resize(self, event_id: str, new_duration: int) -> None:
        self.eventResizeRequested.emit(event_id, new_duration)

    def _on_empty_click(self, event: QMouseEvent, hour: int) -> None:
        """Click on empty space → emit signal to create event."""
        if event.button() != Qt.LeftButton:
            return
        if event.type() != QMouseEvent.MouseButtonDblClick:
            return
        # Determine which day column was clicked
        # (sender is the row widget; we need to find which column it's in)
        sender = self.sender()
        if sender is None:
            return
        # Find the column index by walking the layout
        for i, col in enumerate(self._day_columns):
            if sender.parent() == col or sender in [col_layout.itemAt(j).widget() for j, _ in enumerate(range(col.layout().count()))]:
                days = self._get_visible_days()
                if i < len(days):
                    self.dayDoubleClicked.emit(days[i])
                    return

    # ---- Resize event ----
    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        # Re-layout events to fit new width
        QTimer.singleShot(0, self._refresh_events)


# ---- Concrete views ----

class DayView(TimeGridView):
    """Single-day time grid."""
    def __init__(self, store: CalendarStore, parent: QWidget = None) -> None:
        super().__init__(store, num_days=1, parent=parent)

    def _get_visible_days(self) -> list[ShamsiDate]:
        return [self._anchor_date]


class WeekView(TimeGridView):
    """7-day time grid (Saturday through Friday, Iranian week)."""
    def __init__(self, store: CalendarStore, parent: QWidget = None) -> None:
        super().__init__(store, num_days=7, parent=parent)

    def _get_visible_days(self) -> list[ShamsiDate]:
        return iterate_week(self._anchor_date)


class CustomView(TimeGridView):
    """N-day time grid (3, 4, 5, 7, 10, or 14 days)."""
    def __init__(self, store: CalendarStore, num_days: int = 4,
                 parent: QWidget = None) -> None:
        super().__init__(store, num_days=num_days, parent=parent)

    def _get_visible_days(self) -> list[ShamsiDate]:
        return [self._anchor_date.add_days(i) for i in range(self.num_days)]
