"""
WeekView — 7-day week view for the RASK! calendar.

Renders a Google-Calendar-style week view with:
  - All-day event area at top (collapsible rows)
  - 7 day columns with 24-hour time grid
  - Time ruler on the left
  - Current time red line
  - Hour / half-hour grid lines
  - Event blocks positioned absolutely by time
  - Overlapping event layout (side-by-side columns)
  - Drag-to-create events
  - Drag-to-move / drag-to-resize via EventWidget
  - Click to select date / event
  - Double-click to create event
  - Smooth scrolling
  - Auto-scroll to current time on load
"""
from __future__ import annotations

from datetime import datetime, timedelta
from typing import Optional

from PySide6.QtCore import Qt, Signal, QTimer, QRectF, QPoint
from PySide6.QtGui import QPainter, QColor, QPen, QBrush, QFont, QCursor
from PySide6.QtWidgets import (
    QWidget, QScrollArea, QVBoxLayout, QFrame, QScrollBar,
)

from .controller import CalendarController
from .model import CalendarModel, DayEvents, EventLayout
from .selection import SelectionManager
from .event_renderer import EventRenderer, EventRenderOptions
from .event_widget import EventWidget
from .animation import HoverGlow
from .theme import (
    Surface, Gold, Text, Border, NowLine, Metrics, Spacing,
    qcolor, with_alpha, lighten, darken,
    font_header, font_body, font_small, font_time_label,
)
from ...core.shamsi import ShamsiDate, to_persian_digits, SHAMSI_WEEKDAYS_SHORT_EN
from ...calendar.event import Event
from ...calendar.enums import CalendarViewKind


# ──────────────────────────────── Layout constants ─────────────────────────

_RULER_W   = Metrics.TIME_RULER_WIDTH
_HOUR_H    = Metrics.HOUR_HEIGHT
_SNAP      = Metrics.SNAP_MINUTES
_MIN_EVT_H = Metrics.MIN_EVENT_HEIGHT
_ALLDAY_ROW_H  = Metrics.ALL_DAY_ROW_HEIGHT
_ALLDAY_MAX    = Metrics.ALL_DAY_MAX_ROWS
_DAY_HEADER_H  = 46
_RESIZE_H      = Metrics.RESIZE_HANDLE_H
_DRAG_THRESH   = Metrics.DRAG_THRESHOLD
_SCROLL_STEP   = Metrics.SCROLL_STEP


# ──────────────────────────────── Helpers ──────────────────────────────────

def _iranian_week_offset(containing: ShamsiDate) -> list[ShamsiDate]:
    """Return 7 ShamsiDates for Saturday..Friday of the week containing *containing*."""
    py_wd = containing.to_gregorian().weekday()
    # Python weekday: Mon=0 Tue=1 Wed=2 Thu=3 Fri=4 Sat=5 Sun=6
    # Iranian:        Mon=2 Tue=3 Wed=4 Thu=5 Fri=6 Sat=0 Sun=1
    offset_map = {5: 0, 6: 1, 0: 2, 1: 3, 2: 4, 3: 5, 4: 6}
    day_offset = offset_map.get(py_wd, 0)
    saturday = containing.add_days(-day_offset)
    return [saturday.add_days(i) for i in range(7)]


# ══════════════════════════════════════════════════════════════════════════
#  WeekView  — the public widget
# ══════════════════════════════════════════════════════════════════════════

class WeekView(QWidget):
    """
    7-day week view (Saturday → Friday) for the RASK! calendar.

    Layout
    ------
    ┌──────────────────────────────────────────────────────────────┐
    │  _DayHeaderBar   (fixed, day names + day numbers)            │
    ├──────────────────────────────────────────────────────────────┤
    │  _AllDayArea     (fixed, all-day event chips)                │
    ├──────────────────────────────────────────────────────────────┤
    │  QScrollArea → _TimeGrid   (scrollable 24 h timeline)       │
    │   └── EventWidget children                                   │
    └──────────────────────────────────────────────────────────────┘
    """

    create_event_requested = Signal(object)   # datetime
    event_activated        = Signal(str)      # event_id

    # ── Construction ──────────────────────────────────────────────────────

    def __init__(self, controller: CalendarController, parent=None):
        super().__init__(parent)
        self._ctrl  = controller
        self._model = controller.model
        self._sel   = controller.selection

        # -- Week state --
        self._week_dates:  list[ShamsiDate]  = []
        self._day_events:  list[DayEvents]   = []

        # -- Event widgets --
        self._evt_widgets: dict[str, EventWidget] = {}

        # -- Drag-move / drag-resize tracking --
        self._drag_move_origin_start: dict[str, datetime] = {}
        self._drag_move_origin_end:   dict[str, datetime] = {}
        self._drag_move_last_delta:   dict[str, int]      = {}
        self._drag_resize_origin_end: dict[str, datetime] = {}
        self._drag_resize_last_delta: dict[str, int]      = {}
        self._drag_move_origin_col:   dict[str, int]      = {}

        # -- Build UI --
        self._build_ui()

        # -- Signals --
        self._ctrl.events_changed.connect(self.refresh)
        self._ctrl.date_changed.connect(self._on_date_changed)
        self._sel.selection_changed.connect(self._on_selection_changed)

        # -- Now-line timer (60 s) --
        self._now_timer = QTimer(self)
        self._now_timer.timeout.connect(self._tick_now)
        self._now_timer.start(60_000)

        # -- Initial week --
        self.set_week(ShamsiDate.today())

    # ── UI construction ───────────────────────────────────────────────────

    def _build_ui(self) -> None:
        self.setStyleSheet(f"background-color: {Surface.CANVAS};")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # 1) Day-header bar
        self._header = _DayHeaderBar(self._ctrl, self)
        layout.addWidget(self._header)

        # 2) All-day event area
        self._allday = _AllDayArea(self._ctrl, self)
        layout.addWidget(self._allday)

        # 3) Scrollable time grid
        self._scroll = QScrollArea(self)
        self._scroll.setWidgetResizable(True)
        self._scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self._scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self._scroll.setFrameShape(QFrame.NoFrame)
        self._scroll.setStyleSheet(
            f"QScrollArea {{ background:{Surface.CANVAS}; border:none; }}"
        )

        # Smooth scrolling
        sb = self._scroll.verticalScrollBar()
        sb.setSingleStep(_SCROLL_STEP)
        sb.setStyleSheet(
            "QScrollBar:vertical {"
            "  background: transparent; width: 10px; margin: 0;"
            "}"
            "QScrollBar::handle:vertical {"
            "  background: #3A3A45; border-radius: 4px; min-height: 30px;"
            "}"
            "QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {"
            "  height: 0;"
            "}"
            "QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {"
            "  background: none;"
            "}"
        )

        self._grid = _TimeGrid(self._ctrl, self)
        self._scroll.setWidget(self._grid)

        layout.addWidget(self._scroll, 1)

        # Sync column alignment when scrollbar appears / disappears
        if hasattr(sb, 'visibilityChanged'):
            sb.visibilityChanged.connect(self._sync_column_alignment)

    # ── Public API ────────────────────────────────────────────────────────

    def set_week(self, containing: ShamsiDate) -> None:
        """Display the Iranian week (Sat–Fri) that contains *containing*."""
        self._week_dates = _iranian_week_offset(containing)
        self._layout_events()
        self._create_event_widgets()
        self._header.set_dates(self._week_dates)
        self._allday.set_data(self._week_dates, self._day_events)
        self._grid.set_data(self._week_dates, self._day_events)
        self._sync_column_alignment()
        self.update()

    def refresh(self) -> None:
        """Reload events from the model and reposition everything."""
        self._layout_events()
        self._create_event_widgets()
        self._allday.set_data(self._week_dates, self._day_events)
        self._grid.set_data(self._week_dates, self._day_events)
        self._sync_column_alignment()
        self.update()

    def scroll_to_current_time(self) -> None:
        """Auto-scroll so the current time marker is visible."""
        now = datetime.now()
        y = (now.hour * 60 + now.minute) / 60.0 * _HOUR_H
        viewport_h = self._scroll.viewport().height()
        target = max(0, int(y - viewport_h / 3))
        self._scroll.verticalScrollBar().setValue(target)

    # ── Event layout (collision detection) ────────────────────────────────

    def _layout_events(self) -> None:
        """Compute DayEvents with timed_layout for each day of the week."""
        self._day_events = []
        for d in self._week_dates:
            de = self._model.day_events(d)
            de.timed_layout = self._model.compute_timed_layout(de.timed)
            self._day_events.append(de)

    # ── Event widget lifecycle ────────────────────────────────────────────

    def _create_event_widgets(self) -> None:
        """Destroy old EventWidgets and create fresh ones from layout data."""
        # Teardown
        for w in self._evt_widgets.values():
            w.setParent(None)
            w.deleteLater()
        self._evt_widgets.clear()
        self._drag_move_origin_start.clear()
        self._drag_move_origin_end.clear()
        self._drag_move_last_delta.clear()
        self._drag_resize_origin_end.clear()
        self._drag_resize_last_delta.clear()
        self._drag_move_origin_col.clear()

        # Build
        for day_idx, de in enumerate(self._day_events):
            for layout in de.timed_layout:
                evt   = layout.event
                color = self._model.event_color(evt)
                w = EventWidget(evt, color, self._grid)
                self._evt_widgets[evt.id] = w

                # Signals
                w.clicked.connect(self._on_evt_clicked)
                w.double_clicked.connect(self._on_evt_double_clicked)
                w.drag_started.connect(self._on_evt_drag_started)
                w.drag_moved.connect(self._on_evt_drag_moved)
                w.drag_ended.connect(self._on_evt_drag_ended)
                w.resize_started.connect(self._on_evt_resize_started)
                w.resize_moved.connect(self._on_evt_resize_moved)
                w.resize_ended.connect(self._on_evt_resize_ended)

                w.show()

        self._position_event_widgets()

        # Restore selection highlight
        sel_id = self._sel.selected_event_id
        if sel_id and sel_id in self._evt_widgets:
            self._evt_widgets[sel_id].set_selected(True)

    def _position_event_widgets(self) -> None:
        """Place every EventWidget at its correct pixel position."""
        col_w = self._grid.col_width()
        for day_idx, de in enumerate(self._day_events):
            x0 = self._grid.col_left(day_idx)
            for layout in de.timed_layout:
                w = self._evt_widgets.get(layout.event.id)
                if w is None:
                    continue

                evt = layout.event
                start_min = evt.start.hour * 60 + evt.start.minute
                end_min   = evt.end.hour   * 60 + evt.end.minute
                dur_min   = max(end_min - start_min, 15)

                y = start_min / 60.0 * _HOUR_H
                h = max(dur_min / 60.0 * _HOUR_H, _MIN_EVT_H)

                evt_x = x0 + layout.left * col_w + 1
                evt_w = layout.width * col_w - 2

                w.setGeometry(int(evt_x), int(y), max(int(evt_w), 20), int(h))

    # ── Column alignment sync ─────────────────────────────────────────────

    def _sync_column_alignment(self) -> None:
        """Ensure header & all-day widths match the grid viewport width."""
        # The scroll-area viewport width may differ from the outer widget
        # width when a vertical scrollbar is present.  We add a right
        # margin to header / all-day so the column edges line up exactly.
        vp_w = self._scroll.viewport().width()
        outer_w = self.width()
        sb_w = max(0, outer_w - vp_w)
        self._header.set_right_margin(sb_w)
        self._allday.set_right_margin(sb_w)

    # ── EventWidget signal handlers ───────────────────────────────────────

    def _day_index_for_event(self, event_id: str) -> int:
        for idx, de in enumerate(self._day_events):
            for layout in de.timed_layout:
                if layout.event.id == event_id:
                    return idx
        return -1

    def _on_evt_clicked(self, event_id: str) -> None:
        idx = self._day_index_for_event(event_id)
        self._sel.selected_event_id = event_id
        if 0 <= idx < len(self._week_dates):
            self._sel.selected_date = self._week_dates[idx]

    def _on_evt_double_clicked(self, event_id: str) -> None:
        self._sel.selected_event_id = event_id
        self.event_activated.emit(event_id)

    # ── Drag-move ──

    def _on_evt_drag_started(self, event_id: str) -> None:
        w = self._evt_widgets.get(event_id)
        if w is None:
            return
        self._drag_move_origin_start[event_id] = w.event.start
        self._drag_move_origin_end[event_id]   = w.event.end
        self._drag_move_last_delta[event_id]   = 0
        self._drag_move_origin_col[event_id]   = self._day_index_for_event(event_id)
        w.raise_()

    def _on_evt_drag_moved(self, event_id: str, delta_minutes: int) -> None:
        self._drag_move_last_delta[event_id] = delta_minutes
        origin = self._drag_move_origin_start.get(event_id)
        if origin is None:
            return
        w = self._evt_widgets.get(event_id)
        if w is None:
            return

        new_start = origin + timedelta(minutes=delta_minutes)
        new_start_min = max(0, new_start.hour * 60 + new_start.minute)
        new_y = new_start_min / 60.0 * _HOUR_H

        # Check if cursor moved to a different day column
        global_pos = QCursor.pos()
        grid_pos   = self._grid.mapFromGlobal(global_pos)
        new_col    = self._grid.column_at(grid_pos)
        origin_col = self._drag_move_origin_col.get(event_id, -1)

        if 0 <= new_col < 7 and new_col != origin_col:
            # Move to different column
            col_w = self._grid.col_width()
            # Find the layout to get the left/width fractions
            for de in self._day_events:
                for layout in de.timed_layout:
                    if layout.event.id == event_id:
                        new_x = self._grid.col_left(new_col) + layout.left * col_w + 1
                        w.move(int(new_x), int(new_y))
                        return
            # Fallback: full-width
            new_x = self._grid.col_left(new_col) + 1
            w.move(int(new_x), int(new_y))
        else:
            w.move(w.x(), int(new_y))

    def _on_evt_drag_ended(self, event_id: str) -> None:
        w = self._evt_widgets.get(event_id)
        delta = self._drag_move_last_delta.get(event_id, 0)
        origin = self._drag_move_origin_start.get(event_id)
        origin_col = self._drag_move_origin_col.get(event_id, -1)

        if w and origin is not None:
            new_start = origin + timedelta(minutes=delta)

            # Check for cross-day move
            global_pos = QCursor.pos()
            grid_pos   = self._grid.mapFromGlobal(global_pos)
            new_col    = self._grid.column_at(grid_pos)

            if 0 <= new_col < 7 and new_col != origin_col and new_col < len(self._week_dates):
                # Compute the day offset
                target_date = self._week_dates[new_col]
                new_start = target_date.to_datetime(new_start.hour, new_start.minute)

            self._ctrl.move_event(event_id, new_start)

        self._drag_move_origin_start.pop(event_id, None)
        self._drag_move_origin_end.pop(event_id, None)
        self._drag_move_last_delta.pop(event_id, None)
        self._drag_move_origin_col.pop(event_id, None)

    # ── Drag-resize ──

    def _on_evt_resize_started(self, event_id: str) -> None:
        w = self._evt_widgets.get(event_id)
        if w is None:
            return
        self._drag_resize_origin_end[event_id] = w.event.end
        self._drag_resize_last_delta[event_id] = 0

    def _on_evt_resize_moved(self, event_id: str, delta_minutes: int) -> None:
        self._drag_resize_last_delta[event_id] = delta_minutes
        origin_end = self._drag_resize_origin_end.get(event_id)
        if origin_end is None:
            return
        w = self._evt_widgets.get(event_id)
        if w is None:
            return

        new_end = origin_end + timedelta(minutes=delta_minutes)
        # Don't allow end ≤ start
        if new_end <= w.event.start:
            new_end = w.event.start + timedelta(minutes=_SNAP)

        new_end_min = new_end.hour * 60 + new_end.minute
        start_min   = w.event.start.hour * 60 + w.event.start.minute
        dur_min     = max(new_end_min - start_min, _SNAP)
        new_h       = max(dur_min / 60.0 * _HOUR_H, _MIN_EVT_H)

        w.resize(w.width(), int(new_h))

    def _on_evt_resize_ended(self, event_id: str) -> None:
        w = self._evt_widgets.get(event_id)
        delta = self._drag_resize_last_delta.get(event_id, 0)
        origin_end = self._drag_resize_origin_end.get(event_id)
        if w and origin_end is not None:
            new_end = origin_end + timedelta(minutes=delta)
            if new_end <= w.event.start:
                new_end = w.event.start + timedelta(minutes=_SNAP)
            self._ctrl.resize_event(event_id, new_end)

        self._drag_resize_origin_end.pop(event_id, None)
        self._drag_resize_last_delta.pop(event_id, None)

    # ── Controller signal handlers ────────────────────────────────────────

    def _on_date_changed(self) -> None:
        self.set_week(self._ctrl.nav_date)

    def _on_selection_changed(self) -> None:
        sel_id = self._sel.selected_event_id
        for eid, w in self._evt_widgets.items():
            w.set_selected(eid == sel_id)
        self._header.update()
        self._allday.update()

    # ── Now-line tick ─────────────────────────────────────────────────────

    def _tick_now(self) -> None:
        self._grid.update()

    # ── Resize ────────────────────────────────────────────────────────────

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self._position_event_widgets()
        self._sync_column_alignment()
        self._header.update()
        self._allday.update()
        self._grid.update()


# ══════════════════════════════════════════════════════════════════════════
#  _DayHeaderBar — fixed row with weekday names + day numbers
# ══════════════════════════════════════════════════════════════════════════

class _DayHeaderBar(QWidget):

    def __init__(self, controller: CalendarController, parent=None):
        super().__init__(parent)
        self._ctrl = controller
        self._dates: list[ShamsiDate] = []
        self._right_margin: int = 0
        self.setFixedHeight(_DAY_HEADER_H)

    def set_dates(self, dates: list[ShamsiDate]) -> None:
        self._dates = dates
        self.update()

    def set_right_margin(self, margin: int) -> None:
        if self._right_margin != margin:
            self._right_margin = margin
            self.update()

    # ── Geometry ──

    def _col_width(self) -> float:
        usable = self.width() - _RULER_W - self._right_margin
        return max(usable / 7.0, 1.0)

    # ── Paint ──

    def paintEvent(self, event) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        try:
            self._paint(p)
        finally:
            p.end()

    def _paint(self, p: QPainter) -> None:
        w = self.width() - self._right_margin
        h = self.height()
        today    = ShamsiDate.today()
        sel_date = self._ctrl.selection.selected_date

        # Background
        p.fillRect(0, 0, w, h, qcolor(Surface.PANEL))

        # Ruler area
        p.fillRect(0, 0, _RULER_W, h, qcolor(Surface.CANVAS))
        p.setPen(QPen(qcolor(Border.NORMAL), 1))
        p.drawLine(int(_RULER_W) - 1, 0, int(_RULER_W) - 1, h)

        # Bottom border
        p.setPen(QPen(qcolor(Border.SUBTLE), 1))
        p.drawLine(0, h - 1, w, h - 1)

        col_w = self._col_width()

        for i in range(7):
            x = _RULER_W + i * col_w
            d = self._dates[i] if i < len(self._dates) else None

            # Column separator
            if i > 0:
                p.setPen(QPen(qcolor(Border.SUBTLE), 1))
                p.drawLine(int(x), 0, int(x), h)

            if d is None:
                continue

            is_today    = d == today
            is_selected = d == sel_date
            is_weekend  = (i == 0) or (i == 6)   # Sat / Fri

            # Today column background
            if is_today:
                p.fillRect(QRectF(x, 0, col_w, h), with_alpha(Gold.PRIMARY, 22))

            # Selected-day border (non-today)
            if is_selected and not is_today:
                p.setPen(QPen(qcolor(Gold.PRIMARY), 1.5))
                p.setBrush(Qt.NoBrush)
                p.drawRect(QRectF(x + 0.5, 0.5, col_w - 1, h - 1))

            # ── Weekday name ──
            p.setFont(font_small())
            wd_color = qcolor(Text.WEEKEND) if is_weekend else qcolor(Text.SECONDARY)
            p.setPen(QPen(wd_color))
            p.drawText(
                QRectF(x, 4, col_w, 14),
                Qt.AlignCenter,
                SHAMSI_WEEKDAYS_SHORT_EN[i],
            )

            # ── Day number ──
            if is_today:
                cx = int(x + col_w / 2)
                cy = int(h / 2 + 6)
                r  = 13
                p.setPen(Qt.NoPen)
                p.setBrush(QBrush(qcolor(Gold.PRIMARY)))
                p.drawEllipse(QPoint(cx, cy), r, r)

                p.setFont(font_header())
                p.setPen(QPen(qcolor(Text.ON_GOLD)))
                p.drawText(
                    QRectF(x, cy - 9, col_w, 18),
                    Qt.AlignCenter,
                    to_persian_digits(str(d.day)),
                )
            else:
                p.setFont(font_header())
                day_color = qcolor(Text.WEEKEND) if is_weekend else qcolor(Text.PRIMARY)
                p.setPen(QPen(day_color))
                p.drawText(
                    QRectF(x, h / 2 - 3, col_w, 18),
                    Qt.AlignCenter,
                    to_persian_digits(str(d.day)),
                )


# ══════════════════════════════════════════════════════════════════════════
#  _AllDayArea — collapsible rows of all-day event chips
# ══════════════════════════════════════════════════════════════════════════

class _AllDayArea(QWidget):

    def __init__(self, controller: CalendarController, parent=None):
        super().__init__(parent)
        self._ctrl  = controller
        self._model = controller.model
        self._dates: list[ShamsiDate]  = []
        self._day_events: list[DayEvents] = []
        self._right_margin: int = 0
        self._hovered_event_id: Optional[str] = None
        self.setMouseTracking(True)

    def set_data(self, dates: list[ShamsiDate], day_events: list[DayEvents]) -> None:
        self._dates = dates
        self._day_events = day_events
        self._adjust_height()
        self.update()

    def set_right_margin(self, margin: int) -> None:
        if self._right_margin != margin:
            self._right_margin = margin
            self.update()

    def _adjust_height(self) -> None:
        max_rows = 0
        for de in self._day_events:
            max_rows = max(max_rows, len(de.all_day))
        rows = min(max(max_rows, 1), _ALLDAY_MAX)
        self.setFixedHeight(rows * _ALLDAY_ROW_H + 2)

    # ── Geometry ──

    def _col_width(self) -> float:
        usable = self.width() - _RULER_W - self._right_margin
        return max(usable / 7.0, 1.0)

    # ── Paint ──

    def paintEvent(self, event) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        try:
            self._paint(p)
        finally:
            p.end()

    def _paint(self, p: QPainter) -> None:
        w = self.width() - self._right_margin
        h = self.height()

        # Background
        p.fillRect(0, 0, w, h, qcolor(Surface.PANEL))

        # Ruler area — label
        p.fillRect(0, 0, _RULER_W, h, qcolor(Surface.CANVAS))
        p.setPen(QPen(qcolor(Border.NORMAL), 1))
        p.drawLine(int(_RULER_W) - 1, 0, int(_RULER_W) - 1, h)

        # "All day" label
        p.setFont(font_small())
        p.setPen(QPen(qcolor(Text.TERTIARY)))
        p.drawText(QRectF(2, 0, _RULER_W - 4, h), Qt.AlignCenter, "All day")

        # Bottom border
        p.setPen(QPen(qcolor(Border.SUBTLE), 1))
        p.drawLine(0, h - 1, w, h - 1)

        col_w = self._col_width()
        sel_event_id = self._ctrl.selection.selected_event_id

        for day_idx, de in enumerate(self._day_events):
            x = _RULER_W + day_idx * col_w

            # Column separator
            if day_idx > 0:
                p.setPen(QPen(qcolor(Border.SUBTLE), 1))
                p.drawLine(int(x), 0, int(x), h)

            # All-day chips
            for row_idx, evt in enumerate(de.all_day[:_ALLDAY_MAX]):
                chip = QRectF(x + 2, row_idx * _ALLDAY_ROW_H + 1,
                              col_w - 4, _ALLDAY_ROW_H - 2)
                color = self._model.event_color(evt)
                EventRenderer.paint_all_day_chip(
                    p, chip, evt, color,
                    hovered=(evt.id == self._hovered_event_id),
                    selected=(evt.id == sel_event_id),
                )

            # Overflow indicator
            if len(de.all_day) > _ALLDAY_MAX:
                oy = _ALLDAY_MAX * _ALLDAY_ROW_H
                p.setFont(font_small())
                p.setPen(QPen(qcolor(Text.TERTIARY)))
                p.drawText(
                    QRectF(x + 4, oy, col_w - 8, 14),
                    Qt.AlignLeft | Qt.AlignTop,
                    f"+{len(de.all_day) - _ALLDAY_MAX}",
                )

    # ── Hit testing ──

    def _hit_test(self, pos: QPoint) -> tuple[int, int]:
        """Return (col_index, row_index). (-1, -1) if outside."""
        if pos.x() < _RULER_W:
            return -1, -1
        col_w = self._col_width()
        col = int((pos.x() - _RULER_W) / col_w)
        row = int(pos.y() / _ALLDAY_ROW_H)
        return col, row

    # ── Mouse ──

    def mousePressEvent(self, event) -> None:
        if event.button() != Qt.LeftButton:
            return
        col, row = self._hit_test(event.position().toPoint())
        if 0 <= col < len(self._day_events):
            de = self._day_events[col]
            if 0 <= row < len(de.all_day):
                self._ctrl.selection.selected_event_id = de.all_day[row].id
                self._ctrl.selection.selected_date = de.date
            else:
                if col < len(self._dates):
                    self._ctrl.selection.selected_date = self._dates[col]
                self._ctrl.selection.selected_event_id = None
        self.update()

    def mouseDoubleClickEvent(self, event) -> None:
        if event.button() != Qt.LeftButton:
            return
        col, row = self._hit_test(event.position().toPoint())
        if 0 <= col < len(self._day_events):
            de = self._day_events[col]
            if 0 <= row < len(de.all_day):
                # Activate the event
                parent = self._find_week_view()
                if parent:
                    parent.event_activated.emit(de.all_day[row].id)
            else:
                # Create new all-day event
                if col < len(self._dates):
                    d = self._dates[col]
                    start_dt = d.to_datetime(0, 0)
                    parent = self._find_week_view()
                    if parent:
                        parent.create_event_requested.emit(start_dt)
        self.update()

    def mouseMoveEvent(self, event) -> None:
        col, row = self._hit_test(event.position().toPoint())
        new_hovered: Optional[str] = None
        if 0 <= col < len(self._day_events):
            de = self._day_events[col]
            if 0 <= row < len(de.all_day):
                new_hovered = de.all_day[row].id
        if new_hovered != self._hovered_event_id:
            self._hovered_event_id = new_hovered
            self.update()

    def _find_week_view(self) -> Optional[WeekView]:
        w = self.parent()
        while w is not None:
            if isinstance(w, WeekView):
                return w
            w = w.parent()
        return None


# ══════════════════════════════════════════════════════════════════════════
#  _TimeGrid — scrollable 24-hour time grid with EventWidget children
# ══════════════════════════════════════════════════════════════════════════

class _TimeGrid(QWidget):
    """
    Custom-painted widget that draws the time ruler, hour/half-hour grid
    lines, day separators, and the now-line.  EventWidget children are
    positioned on top for timed events.

    Mouse interactions on empty space:
      - Click            → select date/time
      - Double-click     → create 1-hour event
      - Click + drag     → drag-to-create with custom duration
    """

    def __init__(self, controller: CalendarController, parent=None):
        super().__init__(parent)
        self._ctrl  = controller
        self._model = controller.model
        self._dates: list[ShamsiDate]  = []
        self._day_events: list[DayEvents] = []

        # Drag-to-create
        self._press_pos:      Optional[QPoint] = None
        self._drag_creating:  bool  = False
        self._create_col:     int   = -1
        self._create_start_min: int = 0
        self._create_end_min:   int = 0

        # Hover
        self._hovered_col: int = -1

        # Size
        self.setFixedHeight(24 * _HOUR_H)
        self.setMinimumWidth(400)
        self.setMouseTracking(True)

    def set_data(self, dates: list[ShamsiDate], day_events: list[DayEvents]) -> None:
        self._dates = dates
        self._day_events = day_events
        self.update()

    # ── Geometry helpers (public — used by WeekView too) ──────────────────

    def col_width(self) -> float:
        return max((self.width() - _RULER_W) / 7.0, 1.0)

    def col_left(self, col: int) -> float:
        return _RULER_W + col * self.col_width()

    def column_at(self, pos: QPoint) -> int:
        """Day-column index for a point, or -1 if in the ruler area."""
        if pos.x() < _RULER_W:
            return -1
        c = int((pos.x() - _RULER_W) / self.col_width())
        return max(0, min(c, 6))

    @staticmethod
    def snap_min(m: int) -> int:
        """Snap to the nearest 15-minute increment."""
        return round(m / _SNAP) * _SNAP

    # ── Painting ──────────────────────────────────────────────────────────

    def paintEvent(self, event) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        try:
            self._paint_bg(p)
            self._paint_grid(p)
            self._paint_ruler(p)
            self._paint_now_line(p)
            self._paint_drag_preview(p)
        finally:
            p.end()

    # Background

    def _paint_bg(self, p: QPainter) -> None:
        p.fillRect(self.rect(), qcolor(Surface.CANVAS))

        col_w = self.col_width()
        today = ShamsiDate.today()

        # Weekend column tint (Saturday=0, Friday=6)
        for idx in (0, 6):
            x = self.col_left(idx)
            p.fillRect(QRectF(x, 0, col_w, self.height()),
                       with_alpha(Surface.PANEL, 200))

        # Today column highlight
        for i, d in enumerate(self._dates):
            if d == today:
                x = self.col_left(i)
                p.fillRect(QRectF(x, 0, col_w, self.height()),
                           with_alpha(Gold.PRIMARY, 12))
                break

    # Grid lines

    def _paint_grid(self, p: QPainter) -> None:
        w = self.width()
        h = self.height()
        col_w = self.col_width()

        hour_pen     = QPen(qcolor(Border.SUBTLE), 1)
        half_hr_pen  = QPen(qcolor(Border.SUBTLE), 1, Qt.DotLine)
        col_sep_pen  = QPen(qcolor(Border.NORMAL), 1)

        # Horizontal hour + half-hour lines
        for hour in range(25):
            y = hour * _HOUR_H
            p.setPen(hour_pen)
            p.drawLine(int(_RULER_W), int(y), w, int(y))

            if hour < 24:
                half_y = y + _HOUR_H / 2
                p.setPen(half_hr_pen)
                p.drawLine(int(_RULER_W), int(half_y), w, int(half_y))

        # Vertical column separators
        p.setPen(col_sep_pen)
        for i in range(8):
            x = _RULER_W + i * col_w
            p.drawLine(int(x), 0, int(x), h)

    # Time ruler

    def _paint_ruler(self, p: QPainter) -> None:
        p.fillRect(QRectF(0, 0, _RULER_W, self.height()), qcolor(Surface.CANVAS))

        # Right border of ruler
        p.setPen(QPen(qcolor(Border.NORMAL), 1))
        p.drawLine(int(_RULER_W) - 1, 0, int(_RULER_W) - 1, self.height())

        p.setFont(font_time_label())
        p.setPen(QPen(qcolor(Text.TERTIARY)))
        for hour in range(24):
            y = hour * _HOUR_H
            label = f"{hour:02d}:00"
            p.drawText(QRectF(0, y - 8, _RULER_W - 6, 16),
                       Qt.AlignRight | Qt.AlignVCenter, label)

    # Current-time red line

    def _paint_now_line(self, p: QPainter) -> None:
        today = ShamsiDate.today()
        # Only draw when today is in the displayed week
        if not any(d == today for d in self._dates):
            return

        now = datetime.now()
        minutes = now.hour * 60 + now.minute
        y = minutes / 60.0 * _HOUR_H

        # Red line across all day columns
        p.setPen(QPen(NowLine.COLOR, NowLine.WIDTH))
        p.drawLine(int(_RULER_W), int(y), self.width(), int(y))

        # Red dot on the left edge
        p.setPen(Qt.NoPen)
        p.setBrush(QBrush(NowLine.DOT))
        p.drawEllipse(QPoint(int(_RULER_W), int(y)), 4, 4)

    # Drag-to-create preview

    def _paint_drag_preview(self, p: QPainter) -> None:
        if not self._drag_creating or self._create_col < 0:
            return

        col_w = self.col_width()
        x = self.col_left(self._create_col)

        s = min(self._create_start_min, self._create_end_min)
        e = max(self._create_start_min, self._create_end_min)

        y1 = s / 60.0 * _HOUR_H
        y2 = e / 60.0 * _HOUR_H
        h  = max(y2 - y1, _MIN_EVT_H)

        rect = QRectF(x + 1, y1, col_w - 2, h)

        # Semi-transparent gold fill
        p.setPen(QPen(qcolor(Gold.PRIMARY), 1.5))
        p.setBrush(QBrush(with_alpha(Gold.PRIMARY, 40)))
        r = Metrics.EVENT_CORNER_RADIUS
        p.drawRoundedRect(rect, r, r)

        # Left bar
        bar = QRectF(rect.left(), rect.top(),
                      Metrics.EVENT_LEFT_BORDER, rect.height())
        p.setPen(Qt.NoPen)
        p.setBrush(QBrush(qcolor(Gold.PRIMARY)))
        p.drawRoundedRect(bar, 1, 1)

        # Time label inside
        if h > 22:
            p.setFont(font_small())
            p.setPen(QPen(qcolor(Text.PRIMARY)))
            sh, sm = divmod(s, 60)
            eh, em = divmod(e, 60)
            txt = f"{sh:02d}:{sm:02d} – {eh:02d}:{em:02d}"
            p.drawText(rect.adjusted(8, 4, -4, -4),
                       Qt.AlignLeft | Qt.AlignTop, txt)

    # ── Mouse events ──────────────────────────────────────────────────────

    def mousePressEvent(self, event) -> None:
        if event.button() != Qt.LeftButton:
            event.ignore()
            return

        pos = event.position().toPoint()
        self._press_pos = pos

        col = self.column_at(pos)
        if col < 0:
            event.ignore()
            return

        minute = int(pos.y() / _HOUR_H * 60)
        snap   = self.snap_min(minute)

        self._create_col        = col
        self._create_start_min  = snap
        self._create_end_min    = snap
        self._drag_creating     = False

        # Select the date
        if col < len(self._dates):
            self._ctrl.selection.selected_date = self._dates[col]
            self._ctrl.selection.selected_event_id = None

        event.accept()

    def mouseMoveEvent(self, event) -> None:
        pos = event.position().toPoint()

        if self._press_pos is not None:
            delta = pos - self._press_pos

            # Threshold: don't start drag-to-create until moved past it
            if not self._drag_creating:
                if abs(delta.y()) >= _DRAG_THRESH:
                    self._drag_creating = True

            if self._drag_creating:
                minute = int(pos.y() / _HOUR_H * 60)
                self._create_end_min = self.snap_min(minute)
                self.update()

            event.accept()
            return

        # Hover cursor
        col = self.column_at(pos)
        if col != self._hovered_col:
            self._hovered_col = col
            self.setCursor(
                QCursor(Qt.CrossCursor) if col >= 0 else QCursor(Qt.ArrowCursor)
            )

    def mouseReleaseEvent(self, event) -> None:
        if event.button() != Qt.LeftButton or self._press_pos is None:
            event.ignore()
            return

        was_dragging = self._drag_creating
        self._press_pos = None
        self._drag_creating = False

        if was_dragging:
            self._finish_drag_create()
        # A simple click on empty space just selects the date (already
        # done in mousePressEvent).

        self._create_col = -1
        self.update()
        event.accept()

    def mouseDoubleClickEvent(self, event) -> None:
        if event.button() != Qt.LeftButton:
            event.ignore()
            return

        pos = event.position().toPoint()
        col = self.column_at(pos)
        if col < 0 or col >= len(self._dates):
            event.ignore()
            return

        minute = int(pos.y() / _HOUR_H * 60)
        snap   = self.snap_min(minute)
        d      = self._dates[col]
        start  = d.to_datetime(snap // 60, snap % 60)

        parent = self._find_week_view()
        if parent:
            parent.create_event_requested.emit(start)
        event.accept()

    def _finish_drag_create(self) -> None:
        """Compute start/end datetimes from the drag and emit creation signal."""
        col = self._create_col
        if col < 0 or col >= len(self._dates):
            return

        s = min(self._create_start_min, self._create_end_min)
        e = max(self._create_start_min, self._create_end_min)
        if e - s < _SNAP:
            e = s + _SNAP

        # Clamp to 0..24*60
        s = max(0, min(s, 24 * 60))
        e = max(s + _SNAP, min(e, 24 * 60))

        d      = self._dates[col]
        start  = d.to_datetime(s // 60, s % 60)

        parent = self._find_week_view()
        if parent:
            parent.create_event_requested.emit(start)

    def _find_week_view(self) -> Optional[WeekView]:
        w = self.parent()
        while w is not None:
            if isinstance(w, WeekView):
                return w
            w = w.parent()
        return None

    # ── Wheel forwarding ──────────────────────────────────────────────────

    def wheelEvent(self, event) -> None:
        # Forward to the QScrollArea so the grid scrolls
        w = self.parent()
        while w is not None:
            if isinstance(w, QScrollArea):
                w.wheelEvent(event)
                return
            w = w.parent()
        super().wheelEvent(event)
