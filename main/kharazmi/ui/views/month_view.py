"""
MonthView — full-month grid view (Google-Calendar style).

Shows a 6x7 grid (Saturday..Friday) of day cells, each containing
up to N event chips. Overflow is shown as "+N more".

Clicking a day jumps to DayView for that date. Double-clicking a day
creates a new event for that date. Clicking an event chip opens it
for editing.
"""
from __future__ import annotations

from datetime import datetime, timedelta
from typing import Optional

from PySide6.QtCore import Qt, QRectF, QPointF, QSize, Signal, QPoint, QTimer, QMimeData
from PySide6.QtGui import (
    QPainter, QPen, QBrush, QColor, QFont, QPainterPath, QMouseEvent,
    QDragEnterEvent, QDropEvent, QFontMetrics, QPixmap,
)
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QFrame, QGridLayout,
    QScrollArea, QSizePolicy, QPushButton,
)

from ...calendar import (
    CalendarStore, Event as CalEvent, Calendar,
    EventAdded, EventUpdated, EventRemoved, CalendarVisibilityChanged,
    EventType,
)
from ...core.shamsi import (
    ShamsiDate, shamsi_month_grid, days_in_month,
    SHAMSI_MONTHS_FA, SHAMSI_MONTHS_EN, SHAMSI_WEEKDAYS_SHORT_EN,
)
from ..theme import Palette


class MonthEventChip(QFrame):
    """A small chip representing an event in the month grid."""
    clicked = Signal(str)
    doubleClicked = Signal(str)

    DRAG_MIME = "application/x-kharazmi-event-id"

    def __init__(self, event: CalEvent, calendar: Optional[Calendar],
                 parent: QWidget = None) -> None:
        super().__init__(parent)
        self.evt = event
        self.calendar = calendar
        self.setFixedHeight(20)
        self.setCursor(Qt.PointingHandCursor)
        color = event.color or (calendar.color if calendar else Palette.GOLD_PRIMARY)
        text_color = Palette.TEXT_ON_GOLD if self._is_dark(color) else Palette.TEXT_PRIMARY
        self.setStyleSheet(f"""
            QFrame {{
                background-color: {color};
                border-left: 2px solid {color};
                border-radius: 2px;
                margin: 1px 2px;
            }}
        """)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(4, 0, 4, 0)
        layout.setSpacing(4)

        # Time (only if not all-day)
        if not event.all_day and event.event_type != EventType.HOLIDAY:
            time_str = event.start.strftime("%H:%M")
            time_lbl = QLabel(time_str)
            time_lbl.setStyleSheet(
                f"color: {text_color}; font-size: 9px; "
                f"font-family: 'JetBrains Mono', monospace; background: transparent;"
            )
            layout.addWidget(time_lbl)

        # Title
        title = QLabel(event.title)
        title.setStyleSheet(
            f"color: {text_color}; font-size: 11px; "
            f"font-weight: {'bold' if event.event_type == EventType.HOLIDAY else 'normal'}; "
            f"background: transparent;"
        )
        title.setWordWrap(False)
        layout.addWidget(title, stretch=1)

    def _is_dark(self, hex_color: str) -> bool:
        try:
            hex_color = hex_color.lstrip("#")
            r = int(hex_color[0:2], 16)
            g = int(hex_color[2:4], 16)
            b = int(hex_color[4:6], 16)
            return (0.299 * r + 0.587 * g + 0.114 * b) < 128
        except Exception:
            return False

    def mousePressEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.LeftButton:
            self.clicked.emit(self.evt.id)
            self._drag_start = event.position().toPoint()
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        if event.buttons() & Qt.LeftButton and hasattr(self, "_drag_start"):
            delta = event.position().toPoint() - self._drag_start
            if delta.manhattanLength() > 5:
                from PySide6.QtCore import QDrag
                drag = QDrag(self)
                mime = QMimeData()
                mime.setData(self.DRAG_MIME, str(self.evt.id).encode())
                drag.setMimeData(mime)
                pm = QPixmap(self.size())
                self.render(pm)
                drag.setPixmap(pm)
                drag.setHotSpot(self._drag_start)
                drag.exec_(Qt.MoveAction)
        super().mouseMoveEvent(event)

    def mouseDoubleClickEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.LeftButton:
            self.doubleClicked.emit(self.evt.id)
        super().mouseDoubleClickEvent(event)


class MonthDayCell(QFrame):
    """A day cell in the month grid."""
    cellClicked = Signal(object)               # ShamsiDate
    cellDoubleClicked = Signal(object)         # ShamsiDate
    eventClicked = Signal(str)                 # event_id
    eventDoubleClicked = Signal(str)           # event_id
    eventDropped = Signal(str, object)         # event_id, ShamsiDate

    def __init__(self, date: Optional[ShamsiDate], is_today: bool = False,
                 in_month: bool = True, parent: QWidget = None) -> None:
        super().__init__(parent)
        self.date = date
        self.is_today = is_today
        self.in_month = in_month
        self.setAcceptDrops(True)
        self.setMinimumHeight(110)
        self.setObjectName("monthCell")
        self._apply_style()

        layout = QVBoxLayout(self)
        layout.setContentsMargins(2, 2, 2, 2)
        layout.setSpacing(0)

        # Day number row
        header = QHBoxLayout()
        header.setContentsMargins(2, 2, 2, 0)
        header.setSpacing(0)
        if date is not None:
            day_lbl = QLabel(str(date.day))
            if is_today:
                day_lbl.setStyleSheet(
                    f"background-color: {Palette.GOLD_PRIMARY}; "
                    f"color: {Palette.TEXT_ON_GOLD}; "
                    f"border-radius: 9px; min-width: 16px; min-height: 16px; "
                    f"max-width: 18px; max-height: 18px; "
                    f"font-size: 11px; font-weight: bold; padding: 0;"
                )
            else:
                day_lbl.setStyleSheet(
                    f"color: {Palette.TEXT_PRIMARY if in_month else Palette.TEXT_TERTIARY}; "
                    f"font-size: 11px; font-weight: bold; "
                    f"font-family: 'JetBrains Mono', monospace; padding: 0 2px;"
                )
            header.addWidget(day_lbl)

            # Persian weekday (small)
            wd_lbl = QLabel(date.weekday_short_en)
            wd_lbl.setStyleSheet(
                f"color: {Palette.TEXT_TERTIARY}; font-size: 8px; padding: 0 4px;"
            )
            header.addWidget(wd_lbl)

        header.addStretch()
        layout.addLayout(header)

        # Events container
        self._events_container = QWidget()
        self._events_layout = QVBoxLayout(self._events_container)
        self._events_layout.setContentsMargins(0, 0, 0, 0)
        self._events_layout.setSpacing(1)
        layout.addWidget(self._events_container, stretch=1)

        # Overflow indicator
        self._overflow = QLabel("")
        self._overflow.setStyleSheet(
            f"color: {Palette.GOLD_PRIMARY}; font-size: 10px; "
            f"padding: 0 4px;"
        )
        layout.addWidget(self._overflow)

    def _apply_style(self) -> None:
        bg = Palette.BG_SECONDARY if self.in_month else Palette.BG_DEEPEST
        border = Palette.GOLD_PRIMARY if self.is_today else Palette.BORDER_SUBTLE
        border_w = "2px" if self.is_today else "1px"
        self.setStyleSheet(f"""
            QFrame#monthCell {{
                background-color: {bg};
                border: {border_w} solid {border};
                border-radius: 2px;
            }}
            QFrame#monthCell:hover {{
                background-color: {Palette.BG_TERTIARY};
            }}
        """)

    def set_events(self, events: list[tuple[CalEvent, Optional[Calendar]]],
                   max_visible: int = 4) -> None:
        # Clear old
        while self._events_layout.count():
            item = self._events_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        # Sort: all-day first, then by start time
        sorted_events = sorted(
            events,
            key=lambda ec: (not ec[0].all_day, ec[0].start)
        )
        for evt, cal in sorted_events[:max_visible]:
            chip = MonthEventChip(evt, cal)
            chip.clicked.connect(self.eventClicked.emit)
            chip.doubleClicked.connect(self.eventDoubleClicked.emit)
            self._events_layout.addWidget(chip)

        if len(sorted_events) > max_visible:
            self._overflow.setText(f"+ {len(sorted_events) - max_visible} more")
        else:
            self._overflow.setText("")

    def dragEnterEvent(self, event: QDragEnterEvent) -> None:
        if self.date is not None and event.mimeData().hasFormat(MonthEventChip.DRAG_MIME):
            event.acceptProposedAction()
            self.setStyleSheet(f"""
                QFrame#monthCell {{
                    background-color: {Palette.BG_SELECTED};
                    border: 2px dashed {Palette.GOLD_BRIGHT};
                    border-radius: 2px;
                }}
            """)
        else:
            event.ignore()

    def dragLeaveEvent(self, event) -> None:
        self._apply_style()
        super().dragLeaveEvent(event)

    def dropEvent(self, event: QDropEvent) -> None:
        if self.date is not None and event.mimeData().hasFormat(MonthEventChip.DRAG_MIME):
            event_id = bytes(event.mimeData().data(MonthEventChip.DRAG_MIME)).decode()
            self.eventDropped.emit(event_id, self.date)
            event.acceptProposedAction()
        self._apply_style()

    def mousePressEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.LeftButton and self.date is not None:
            self.cellClicked.emit(self.date)
        super().mousePressEvent(event)

    def mouseDoubleClickEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.LeftButton and self.date is not None:
            self.cellDoubleClicked.emit(self.date)
        super().mouseDoubleClickEvent(event)


class MonthView(QWidget):
    """Full month grid view."""

    cellClicked = Signal(object)               # ShamsiDate
    cellDoubleClicked = Signal(object)         # ShamsiDate
    eventClicked = Signal(str)
    eventDoubleClicked = Signal(str)
    eventDropped = Signal(str, object)         # event_id, ShamsiDate

    def __init__(self, store: CalendarStore, parent: QWidget = None) -> None:
        super().__init__(parent)
        self.store = store
        self._current: ShamsiDate = ShamsiDate.today()
        self.setStyleSheet(f"background-color: {Palette.BG_PRIMARY};")

        self.store.subscribe(self._on_store_event)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # Weekday header
        header = QWidget()
        header.setFixedHeight(28)
        header.setStyleSheet(f"background-color: {Palette.BG_SECONDARY}; border-bottom: 1px solid {Palette.BORDER_SUBTLE};")
        header_layout = QHBoxLayout(header)
        header_layout.setContentsMargins(0, 0, 0, 0)
        header_layout.setSpacing(1)
        for wd in SHAMSI_WEEKDAYS_SHORT_EN:
            lbl = QLabel(wd.upper())
            lbl.setAlignment(Qt.AlignCenter)
            lbl.setStyleSheet(
                f"color: {Palette.TEXT_TERTIARY}; font-size: 10px; "
                f"font-weight: bold; letter-spacing: 1.5px; "
                f"background-color: {Palette.BG_SECONDARY};"
            )
            header_layout.addWidget(lbl, stretch=1)
        layout.addWidget(header)

        # Month grid
        self._grid_container = QWidget()
        self._grid_layout = QGridLayout(self._grid_container)
        self._grid_layout.setContentsMargins(0, 0, 0, 0)
        self._grid_layout.setSpacing(1)
        layout.addWidget(self._grid_container, stretch=1)

        self._cells: list[MonthDayCell] = []
        for row in range(6):
            for col in range(7):
                cell = MonthDayCell(None)
                cell.cellClicked.connect(self.cellClicked.emit)
                cell.cellDoubleClicked.connect(self.cellDoubleClicked.emit)
                cell.eventClicked.connect(self.eventClicked.emit)
                cell.eventDoubleClicked.connect(self.eventDoubleClicked.emit)
                cell.eventDropped.connect(self.eventDropped.emit)
                self._cells.append(cell)
                self._grid_layout.addWidget(cell, row, col)
        for c in range(7):
            self._grid_layout.setColumnStretch(c, 1)
        for r in range(6):
            self._grid_layout.setRowStretch(r, 1)

        self.refresh()

    def _on_store_event(self, event: CalEvent) -> None:
        from ...calendar import (
            EventAdded, EventUpdated, EventRemoved, CalendarVisibilityChanged,
        )
        if isinstance(event, (EventAdded, EventUpdated, EventRemoved,
                               CalendarVisibilityChanged)):
            QTimer.singleShot(0, self.refresh)

    def set_anchor_date(self, sd: ShamsiDate) -> None:
        self._current = ShamsiDate(sd.year, sd.month, 1)
        self.refresh()

    def refresh(self) -> None:
        today = ShamsiDate.today()
        grid = shamsi_month_grid(self._current.year, self._current.month)
        prev_month = self._current.add_months(-1)
        next_month = self._current.add_months(1)
        prev_last_day = days_in_month(prev_month.year, prev_month.month)

        idx = 0
        for row, week in enumerate(grid):
            for col, sd in enumerate(week):
                cell = self._cells[idx]
                idx += 1
                if sd is None:
                    if row == 0:
                        first_real = next((d for d in week if d is not None), None)
                        if first_real is not None:
                            offset = (first_real.day - 1) - col
                            if offset >= 0 and offset < prev_last_day:
                                sd = ShamsiDate(prev_month.year, prev_month.month,
                                                prev_last_day - offset)
                                in_month = False
                            else:
                                cell.date = None
                                cell.set_events([])
                                continue
                        else:
                            cell.date = None
                            cell.set_events([])
                            continue
                    else:
                        last_real_idx = max((i for i, d in enumerate(week) if d is not None),
                                             default=-1)
                        if col > last_real_idx and last_real_idx >= 0:
                            offset = col - last_real_idx
                            sd = ShamsiDate(next_month.year, next_month.month, offset)
                            in_month = False
                        else:
                            cell.date = None
                            cell.set_events([])
                            continue
                else:
                    in_month = True

                is_today = (sd == today)
                cell.date = sd
                cell.is_today = is_today
                cell.in_month = in_month
                cell._apply_style()

                # Fetch events for this day
                day_start = sd.to_datetime(0, 0)
                day_end = sd.to_datetime(23, 59)
                events = self.store.events_in_range(day_start, day_end)
                events_with_cal = [
                    (e, self.store.get_calendar(e.calendar_id)) for e in events
                ]
                cell.set_events(events_with_cal)
