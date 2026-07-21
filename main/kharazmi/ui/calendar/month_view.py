"""
MonthView — Custom-painted month grid for the RASK! calendar.

Renders a full month as a 6×7 grid (Saturday through Friday — Iranian week)
using QPainter. Each cell shows the Shamsi day number, event chips rendered
via EventRenderer.paint_month_chip(), and an overflow indicator ("+N more").

Features:
  - Today highlight (gold ring around day number)
  - Weekend highlight (Friday = distinct background tint)
  - Selected date highlight (gold left border + active bg)
  - Hover effects on cells
  - Infinite month navigation via CalendarController
  - Animated transitions between months (PageTransition)
  - Drag-and-drop event movement
  - Double-click to create event
  - Right-click context menu on events and cells
  - Keyboard navigation (arrows, Page Up/Down, Home, End)
  - Zoom support (Ctrl+wheel to change max visible event chips)
"""
from __future__ import annotations

from datetime import datetime, timedelta
from typing import Optional

from PySide6.QtCore import (
    Qt, QRectF, QPointF, QSize, Signal, QPoint, QTimer,
)
from PySide6.QtGui import (
    QPainter, QPen, QBrush, QColor, QFont, QPainterPath,
    QMouseEvent, QWheelEvent, QKeyEvent, QContextMenuEvent,
    QFontMetrics, QCursor, QPixmap,
)
from PySide6.QtWidgets import QWidget, QMenu, QSizePolicy

from .controller import CalendarController
from .model import CalendarModel, DayEvents
from .selection import SelectionManager
from .event_renderer import EventRenderer, EventRenderOptions
from .animation import PageTransition, HoverGlow
from .theme import (
    Surface, Gold, Text, Border, Metrics, Spacing,
    qcolor, with_alpha, lighten, darken,
    font_month_title, font_header, font_body, font_small, font_mini_day,
)
from ...core.shamsi import (
    ShamsiDate, shamsi_month_grid, days_in_month, to_persian_digits,
    SHAMSI_WEEKDAYS_SHORT_EN, SHAMSI_WEEKDAYS_FA,
)
from ...calendar.event import Event
from ...calendar.enums import CalendarViewKind


# ──────────────────────────────── Constants ──────────────────────────────────

_COLS = 7        # Saturday through Friday
_ROWS = 6        # Max weeks in a month

# Drag interaction states
_DRAG_NONE = "none"
_DRAG_PENDING = "pending"
_DRAG_ACTIVE = "active"


# ──────────────────────────────── MonthView ──────────────────────────────────

class MonthView(QWidget):
    """
    QPainter-based month grid view.

    Renders the current Shamsi month as a 6×7 grid of day cells with
    event chips, overflow indicators, and full mouse/keyboard interaction.
    """

    # ── Signals ──
    create_event_requested = Signal(object)   # datetime
    event_activated = Signal(str)             # event_id
    event_context_menu = Signal(str, QPoint)  # event_id, global_pos

    # ── Constructor ──

    def __init__(self, controller: CalendarController, parent=None) -> None:
        super().__init__(parent)

        self._controller = controller
        self._model: CalendarModel = controller.model
        self._selection: SelectionManager = controller.selection

        # Current displayed month
        self._year: int = controller.nav_date.year
        self._month: int = controller.nav_date.month

        # Grid data: 6×7 list of Optional[ShamsiDate]
        self._grid: list[list[Optional[ShamsiDate]]] = []

        # Per-cell event data: keyed by (row, col)
        self._cell_events: dict[tuple[int, int], list[tuple[Event, str]]] = {}

        # Today (cached, updated on refresh)
        self._today: ShamsiDate = ShamsiDate.today()

        # Layout metrics (recomputed on resize)
        self._header_height: int = Metrics.MONTH_ROW_HEIGHT
        self._cell_width: float = 0.0
        self._cell_height: float = 0.0

        # Interaction state
        self._hovered_cell: Optional[tuple[int, int]] = None
        self._hovered_event_id: Optional[str] = None

        # Drag state
        self._drag_state: str = _DRAG_NONE
        self._drag_event_id: Optional[str] = None
        self._drag_press_pos: Optional[QPoint] = None
        self._drag_ghost_pos: Optional[QPointF] = None
        self._drag_origin_date: Optional[ShamsiDate] = None

        # Zoom: max visible event chips per cell
        self._max_visible_events: int = 3

        # Page transition
        self._transition = PageTransition(self)
        self._transition_opacity: float = 1.0
        self._transition_anim = None

        # Widget configuration
        self.setMouseTracking(True)
        self.setFocusPolicy(Qt.StrongFocus)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.setMinimumSize(490, 420)

        # Hover glow per cell (we just track one for performance)
        self._cell_glow = HoverGlow(self, Metrics.ANIM_FAST_MS)

        # Connect controller signals
        self._controller.date_changed.connect(self._on_date_changed)
        self._controller.events_changed.connect(self.refresh)
        self._controller.selection_changed.connect(self._on_selection_changed)

        # Initial load
        self.refresh()

    # ── Public API ──

    def set_month(self, year: int, month: int) -> None:
        """Set the displayed Shamsi month and reload data."""
        if self._year == year and self._month == month:
            return

        old_year, old_month = self._year, self._month
        self._year = year
        self._month = month

        # Determine transition direction
        direction = "left"
        if (year, month) < (old_year, old_month):
            direction = "right"

        self._load_grid()
        self._animate_transition(direction)
        self.update()

    def refresh(self) -> None:
        """Reload events from the model and repaint."""
        self._today = ShamsiDate.today()
        self._load_grid()
        self.update()

    def sizeHint(self) -> QSize:  # noqa: N802
        """Preferred size based on cell metrics."""
        w = _COLS * 130
        h = self._header_height + _ROWS * Metrics.MONTH_CELL_MIN_HEIGHT
        return QSize(w, h)

    # ── Data Loading ──

    def _load_grid(self) -> None:
        """Compute the 6×7 grid and fetch events for every cell."""
        self._grid = shamsi_month_grid(self._year, self._month)
        self._cell_events.clear()

        # Build a set of all Shamsi dates that appear in the grid
        all_dates: set[ShamsiDate] = set()
        for row in range(_ROWS):
            for col in range(_COLS):
                sd = self._grid[row][col] if row < len(self._grid) and col < len(self._grid[row]) else None
                if sd is not None:
                    all_dates.add(sd)

        # Batch-fetch events for each day
        for sd in all_dates:
            day_evts = self._model.events_on_day(sd)
            pairs: list[tuple[Event, str]] = []
            for evt in day_evts:
                color = self._model.event_color(evt)
                pairs.append((evt, color))
            # Sort: all-day first, then by start time
            pairs.sort(key=lambda p: (not p[0].all_day, p[0].start))

        # Assign events to cells
        for row in range(_ROWS):
            for col in range(_COLS):
                sd = self._grid[row][col] if row < len(self._grid) and col < len(self._grid[row]) else None
                if sd is not None:
                    day_evts = self._model.events_on_day(sd)
                    pairs = []
                    for evt in day_evts:
                        color = self._model.event_color(evt)
                        pairs.append((evt, color))
                    pairs.sort(key=lambda p: (not p[0].all_day, p[0].start))
                    self._cell_events[(row, col)] = pairs
                else:
                    self._cell_events[(row, col)] = []

    # ── Transition Animation ──

    def _animate_transition(self, direction: str) -> None:
        """Animate a month-change transition (fade)."""
        from PySide6.QtCore import QAbstractAnimation, QVariantAnimation, QEasingCurve

        if self._transition_anim:
            try:
                if self._transition_anim.state() == QAbstractAnimation.Running:
                    self._transition_anim.stop()
            except RuntimeError:
                self._transition_anim = None

        self._transition_opacity = 0.0

        anim = QVariantAnimation(self)
        anim.setStartValue(0.0)
        anim.setEndValue(1.0)
        anim.setDuration(Metrics.ANIM_DURATION_MS)
        anim.setEasingCurve(QEasingCurve(QEasingCurve.OutCubic))

        def _tick(v: float) -> None:
            self._transition_opacity = v
            self.update()

        anim.valueChanged.connect(_tick)
        anim.start(QAbstractAnimation.DeleteWhenStopped)
        self._transition_anim = anim

    # ── Controller Signal Handlers ──

    def _on_date_changed(self) -> None:
        """Navigation date changed — update displayed month."""
        nav = self._controller.nav_date
        self.set_month(nav.year, nav.month)

    def _on_selection_changed(self) -> None:
        """Selection changed — repaint to show new selected date."""
        self.update()

    # ── Layout Computation ──

    def _recompute_layout(self) -> None:
        """Recompute cell dimensions from the current widget size."""
        w = self.width()
        h = self.height()

        self._header_height = Metrics.MONTH_ROW_HEIGHT
        self._cell_width = w / _COLS
        available_h = h - self._header_height
        self._cell_height = max(available_h / _ROWS, Metrics.MONTH_CELL_MIN_HEIGHT)

    def _header_rect(self) -> QRectF:
        """Bounding rect for the weekday header row."""
        return QRectF(0, 0, self.width(), self._header_height)

    def _cell_rect(self, row: int, col: int) -> QRectF:
        """Bounding rect for the cell at (row, col)."""
        x = col * self._cell_width
        y = self._header_height + row * self._cell_height
        return QRectF(x, y, self._cell_width, self._cell_height)

    # ── Hit Testing ──

    def _cell_at(self, pos: QPoint | QPointF) -> Optional[tuple[int, int]]:
        """Return (row, col) for the given position, or None."""
        if isinstance(pos, QPointF):
            px, py = pos.x(), pos.y()
        else:
            px, py = pos.x(), pos.y()

        if py < self._header_height:
            return None

        col = int(px / self._cell_width)
        row = int((py - self._header_height) / self._cell_height)

        if 0 <= row < _ROWS and 0 <= col < _COLS:
            return (row, col)
        return None

    def _date_at(self, pos: QPoint | QPointF) -> Optional[ShamsiDate]:
        """Return the ShamsiDate at the given position, or None."""
        cell = self._cell_at(pos)
        if cell is None:
            return None
        row, col = cell
        if row < len(self._grid) and col < len(self._grid[row]):
            return self._grid[row][col]
        return None

    def _event_at(self, pos: QPoint | QPointF) -> Optional[str]:
        """Return the event_id at the given position, or None."""
        cell = self._cell_at(pos)
        if cell is None:
            return None
        row, col = cell
        events = self._cell_events.get((row, col), [])
        if not events:
            return None

        # Check if the click is in the event chip area
        cell_rect = self._cell_rect(row, col)
        if isinstance(pos, QPointF):
            local_y = pos.y() - cell_rect.top()
        else:
            local_y = pos.y() - cell_rect.top()

        day_num_h = Metrics.MONTH_DAY_NUMBER_H
        pad = Metrics.MONTH_CELL_PAD
        chip_h = Metrics.MONTH_EVENT_CHIP_H
        gap = Metrics.MONTH_EVENT_GAP

        # Event chips start below the day number
        chip_start_y = day_num_h + pad
        chip_end_y = chip_start_y + min(len(events), self._max_visible_events) * (chip_h + gap)

        if local_y < chip_start_y or local_y > chip_end_y:
            return None

        # Determine which chip
        chip_offset = local_y - chip_start_y
        chip_index = int(chip_offset / (chip_h + gap))
        if 0 <= chip_index < min(len(events), self._max_visible_events):
            return events[chip_index][0].id
        return None

    def _snap_to_grid(self, pos: QPoint | QPointF) -> Optional[tuple[int, int]]:
        """Snap a position to the nearest cell (row, col)."""
        return self._cell_at(pos)

    # ── Painting ──

    def paintEvent(self, event) -> None:  # noqa: N802
        self._recompute_layout()

        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, True)
        try:
            # Apply transition opacity
            painter.setOpacity(self._transition_opacity)

            # 1. Background
            self._paint_background(painter)

            # 2. Weekday header
            self._paint_header(painter)

            # 3. Day cells
            for row in range(_ROWS):
                for col in range(_COLS):
                    sd = None
                    if row < len(self._grid) and col < len(self._grid[row]):
                        sd = self._grid[row][col]
                    cell_rect = self._cell_rect(row, col)
                    self._paint_cell(painter, cell_rect, sd, row, col)

            # 4. Grid lines (on top of fills, below chips)
            self._paint_grid_lines(painter)

            # 5. Drag ghost
            if self._drag_state == _DRAG_ACTIVE and self._drag_ghost_pos is not None:
                self._paint_drag_ghost(painter)
        finally:
            painter.end()

    def _paint_background(self, painter: QPainter) -> None:
        """Fill the entire widget with the canvas background."""
        painter.setPen(Qt.NoPen)
        painter.setBrush(QBrush(qcolor(Surface.CANVAS)))
        painter.drawRect(self.rect())

    def _paint_header(self, painter: QPainter) -> None:
        """Paint the weekday header row (Saturday through Friday)."""
        header_rect = self._header_rect()

        # Background
        painter.setPen(Qt.NoPen)
        painter.setBrush(QBrush(qcolor(Surface.PANEL)))
        painter.drawRect(header_rect)

        # Bottom border
        border_y = header_rect.bottom() - 1
        painter.setPen(QPen(qcolor(Border.NORMAL), 1))
        painter.drawLine(
            QPointF(header_rect.left(), border_y),
            QPointF(header_rect.right(), border_y),
        )

        # Weekday labels
        painter.setFont(font_header())
        col_w = self.width() / _COLS

        for col in range(_COLS):
            # Friday is the last column (col index 6) — Iranian weekend
            is_friday = (col == 6)
            color = qcolor(Text.WEEKEND) if is_friday else qcolor(Text.SECONDARY)

            label = SHAMSI_WEEKDAYS_SHORT_EN[col]
            text_rect = QRectF(col * col_w, 0, col_w, header_rect.height())
            painter.setPen(QPen(color))
            painter.drawText(text_rect, Qt.AlignCenter, label)

    def _paint_cell(self, painter: QPainter, rect: QRectF,
                    shamsi_date: Optional[ShamsiDate],
                    row: int, col: int) -> None:
        """Paint a single day cell."""
        is_current_month = (
            shamsi_date is not None
            and shamsi_date.year == self._year
            and shamsi_date.month == self._month
        )
        is_today = (shamsi_date is not None and shamsi_date == self._today)
        is_friday = (shamsi_date is not None and shamsi_date.is_friday)
        is_selected = (
            shamsi_date is not None
            and shamsi_date == self._selection.selected_date
        )
        is_hovered = (self._hovered_cell == (row, col))

        # ── Cell background ──
        bg = qcolor(Surface.CANVAS)
        if not is_current_month and shamsi_date is not None:
            bg = darken(Surface.CANVAS, 0.03)
        if is_friday and is_current_month:
            bg = with_alpha(Surface.PANEL, 40)
            # Blend with existing bg
            blended = QColor(bg)
            blended.setAlpha(40)
            bg = qcolor(Surface.CANVAS)
            bg = QColor(
                (bg.red() + blended.red()) // 2,
                (bg.green() + blended.green()) // 2,
                (bg.blue() + blended.blue()) // 2,
            )
        if is_hovered:
            bg = qcolor(Surface.CARD_HOVER)
        if is_selected:
            bg = qcolor(Surface.CARD_ACTIVE)

        painter.setPen(Qt.NoPen)
        painter.setBrush(QBrush(bg))

        # Rounded corners for edge cells
        r = Metrics.MONTH_CORNER_RADIUS
        cr = 0  # no per-cell rounding in a tight grid; just fill
        if cr > 0:
            painter.drawRoundedRect(rect, cr, cr)
        else:
            painter.drawRect(rect)

        # ── Selected cell left gold border ──
        if is_selected:
            bar_w = 3.0
            bar_rect = QRectF(rect.left(), rect.top(), bar_w, rect.height())
            painter.setBrush(QBrush(qcolor(Gold.PRIMARY)))
            painter.setPen(Qt.NoPen)
            painter.drawRect(bar_rect)

        # ── Friday tint overlay ──
        if is_friday and is_current_month and not is_hovered and not is_selected:
            overlay = with_alpha(Text.WEEKEND, 8)
            painter.setBrush(QBrush(overlay))
            painter.setPen(Qt.NoPen)
            painter.drawRect(rect)

        if shamsi_date is None:
            return

        pad = Metrics.MONTH_CELL_PAD

        # ── Day number ──
        day_num_rect = QRectF(
            rect.left() + pad,
            rect.top() + pad,
            rect.width() - 2 * pad,
            Metrics.MONTH_DAY_NUMBER_H,
        )

        if is_today:
            self._paint_today_badge(painter, day_num_rect, shamsi_date)
        else:
            day_color = qcolor(Text.PRIMARY) if is_current_month else qcolor(Text.TERTIARY)
            day_font = font_body()
            painter.setFont(day_font)
            painter.setPen(QPen(day_color))
            day_text = to_persian_digits(str(shamsi_date.day))
            # Right-align for RTL layout, with vertical centering
            painter.drawText(day_num_rect, Qt.AlignRight | Qt.AlignVCenter, day_text)

        # ── Event chips ──
        events = self._cell_events.get((row, col), [])
        self._paint_events_in_cell(painter, rect, events, shamsi_date, row, col)

    def _paint_today_badge(self, painter: QPainter, rect: QRectF,
                           shamsi_date: ShamsiDate) -> None:
        """Paint the today indicator: gold circle behind the day number."""
        day_text = to_persian_digits(str(shamsi_date.day))
        painter.setFont(font_body())

        # Measure text to size the circle
        fm = QFontMetrics(font_body())
        text_w = fm.horizontalAdvance(day_text)
        text_h = fm.height()

        # Circle center — right-aligned for RTL layout
        badge_r = max(text_w, text_h) / 2 + 4
        cx = rect.right() - badge_r - 2
        cy = rect.center().y()

        # Gold filled circle
        painter.setPen(Qt.NoPen)
        painter.setBrush(QBrush(qcolor(Gold.PRIMARY)))
        painter.drawEllipse(QPointF(cx, cy), badge_r, badge_r)

        # Day number in dark text on gold
        painter.setPen(QPen(qcolor(Text.ON_GOLD)))
        badge_text_rect = QRectF(cx - badge_r, cy - badge_r, badge_r * 2, badge_r * 2)
        painter.drawText(badge_text_rect, Qt.AlignCenter, day_text)

    def _paint_events_in_cell(self, painter: QPainter, cell_rect: QRectF,
                              events: list[tuple[Event, str]],
                              shamsi_date: ShamsiDate,
                              row: int, col: int) -> None:
        """Paint event chips inside a day cell."""
        if not events:
            return

        pad = Metrics.MONTH_CELL_PAD
        chip_h = Metrics.MONTH_EVENT_CHIP_H
        gap = Metrics.MONTH_EVENT_GAP

        # Chips start below the day number
        y = cell_rect.top() + Metrics.MONTH_DAY_NUMBER_H + pad
        x = cell_rect.left() + pad
        chip_w = cell_rect.width() - 2 * pad

        if chip_w < 20:
            return

        visible_count = min(len(events), self._max_visible_events)
        selected_event_id = self._selection.selected_event_id
        hovered_event_id = self._hovered_event_id

        for i in range(visible_count):
            evt, color = events[i]

            # Skip the dragged event in its original cell (show dimmed)
            is_dragged = (
                self._drag_state == _DRAG_ACTIVE
                and evt.id == self._drag_event_id
            )

            chip_rect = QRectF(x, y, chip_w, chip_h)

            is_hovered = (evt.id == hovered_event_id)
            is_selected = (evt.id == selected_event_id)

            if is_dragged:
                # Dimmed placeholder
                painter.save()
                painter.setOpacity(0.3)
                EventRenderer.paint_month_chip(
                    painter, chip_rect, evt, color,
                    hovered=False, selected=False,
                )
                painter.restore()
            else:
                EventRenderer.paint_month_chip(
                    painter, chip_rect, evt, color,
                    hovered=is_hovered, selected=is_selected,
                )

            y += chip_h + gap

        # ── Overflow indicator ──
        overflow_count = len(events) - self._max_visible_events
        if overflow_count > 0:
            overflow_y = y
            overflow_rect = QRectF(x, overflow_y, chip_w, Metrics.MONTH_OVERFLOW_H)
            painter.setFont(font_mini_day())
            painter.setPen(QPen(qcolor(Gold.PRIMARY)))
            overflow_text = to_persian_digits(f"+{overflow_count}") + " more"
            painter.drawText(overflow_rect, Qt.AlignLeft | Qt.AlignVCenter, overflow_text)

    def _paint_grid_lines(self, painter: QPainter) -> None:
        """Paint grid lines between cells."""
        painter.setPen(QPen(qcolor(Border.SUBTLE), 1))
        painter.setBrush(Qt.NoBrush)

        w = self.width()
        h = self.height()

        # Vertical lines
        for col in range(1, _COLS):
            x = col * self._cell_width
            painter.drawLine(
                QPointF(x, self._header_height),
                QPointF(x, h),
            )

        # Horizontal lines
        for row in range(_ROWS):
            y = self._header_height + row * self._cell_height
            painter.drawLine(QPointF(0, y), QPointF(w, y))

        # Header bottom line (stronger)
        painter.setPen(QPen(qcolor(Border.NORMAL), 1))
        painter.drawLine(
            QPointF(0, self._header_height),
            QPointF(w, self._header_height),
        )

    def _paint_drag_ghost(self, painter: QPainter) -> None:
        """Paint the semi-transparent drag ghost at cursor position."""
        if self._drag_event_id is None or self._drag_ghost_pos is None:
            return

        # Find the event
        evt = self._model.store.get_event(self._drag_event_id)
        if evt is None:
            return

        color = self._model.event_color(evt)

        # Ghost size
        ghost_w = min(self._cell_width - 2 * Metrics.MONTH_CELL_PAD, 160)
        ghost_h = Metrics.MONTH_EVENT_CHIP_H
        ghost_rect = QRectF(
            self._drag_ghost_pos.x() - ghost_w / 2,
            self._drag_ghost_pos.y() - ghost_h / 2,
            ghost_w,
            ghost_h,
        )

        painter.save()
        painter.setOpacity(Metrics.DRAG_OPACITY)
        EventRenderer.paint_month_chip(
            painter, ghost_rect, evt, color,
            hovered=True, selected=False,
        )
        painter.restore()

    # ── Mouse Events ──

    def mousePressEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        if event.button() == Qt.LeftButton:
            pos = event.position()

            # Check if an event chip was clicked
            event_id = self._event_at(pos.toPoint())
            if event_id is not None:
                self._selection.selected_event_id = event_id
                self._drag_state = _DRAG_PENDING
                self._drag_event_id = event_id
                self._drag_press_pos = event.globalPosition().toPoint()
                sd = self._date_at(pos.toPoint())
                self._drag_origin_date = sd
            else:
                # Click on cell — select the date
                sd = self._date_at(pos.toPoint())
                if sd is not None:
                    self._selection.selected_date = sd
                self._drag_state = _DRAG_NONE
                self._drag_event_id = None

            self.update()
            event.accept()
        else:
            event.ignore()

    def mouseMoveEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        pos = event.position()

        # Update hovered cell
        cell = self._cell_at(pos)
        old_hovered = self._hovered_cell
        self._hovered_cell = cell

        # Update hovered event
        self._hovered_event_id = self._event_at(pos.toPoint())

        # Handle drag
        if self._drag_state == _DRAG_PENDING and self._drag_press_pos is not None:
            global_pos = event.globalPosition().toPoint()
            delta = global_pos - self._drag_press_pos
            if delta.manhattanLength() >= Metrics.DRAG_THRESHOLD:
                self._drag_state = _DRAG_ACTIVE
                self.setCursor(QCursor(Qt.ClosedHandCursor))

        if self._drag_state == _DRAG_ACTIVE:
            self._drag_ghost_pos = pos
            self.update()
            event.accept()
            return

        # Repaint on hover change
        if old_hovered != self._hovered_cell:
            self.update()

        event.accept()

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        if event.button() == Qt.LeftButton:
            if self._drag_state == _DRAG_ACTIVE:
                # Drop the event at the target date
                pos = event.position()
                target_date = self._date_at(pos.toPoint())
                if target_date is not None and self._drag_event_id is not None:
                    evt = self._model.store.get_event(self._drag_event_id)
                    if evt is not None:
                        # Calculate new start datetime
                        old_start = evt.start
                        new_start = target_date.to_datetime(
                            old_start.hour, old_start.minute
                        )
                        self._controller.move_event(self._drag_event_id, new_start)

            self._drag_state = _DRAG_NONE
            self._drag_event_id = None
            self._drag_press_pos = None
            self._drag_ghost_pos = None
            self._drag_origin_date = None
            self.setCursor(QCursor(Qt.ArrowCursor))
            self.update()
            event.accept()
        else:
            event.ignore()

    def mouseDoubleClickEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        if event.button() == Qt.LeftButton:
            pos = event.position()

            # Check if an event was double-clicked
            event_id = self._event_at(pos.toPoint())
            if event_id is not None:
                self.event_activated.emit(event_id)
                event.accept()
                return

            # Otherwise, double-click on empty cell → create event
            sd = self._date_at(pos.toPoint())
            if sd is not None:
                dt = sd.to_datetime(9, 0)  # Default 9:00 AM
                self.create_event_requested.emit(dt)
                event.accept()
            else:
                event.ignore()
        else:
            event.ignore()

    # ── Context Menu ──

    def contextMenuEvent(self, event: QContextMenuEvent) -> None:  # noqa: N802
        pos = event.pos()
        event_id = self._event_at(pos)
        sd = self._date_at(pos)

        menu = QMenu(self)
        menu.setStyleSheet(self._menu_stylesheet())

        if event_id is not None:
            # Event context menu
            evt = self._model.store.get_event(event_id)
            if evt is not None:
                action_edit = menu.addAction("✏️  Edit Event")
                menu.addSeparator()
                action_delete = menu.addAction("🗑  Delete")

                menu.addSeparator()
                if evt.completed:
                    action_toggle = menu.addAction("☐  Mark Incomplete")
                else:
                    action_toggle = menu.addAction("☑  Mark Complete")

                chosen = menu.exec(event.globalPos())
                if chosen is None:
                    return

                if chosen == action_edit:
                    self.event_activated.emit(event_id)
                elif chosen == action_delete:
                    self._controller.delete_event(event_id)
                elif chosen == action_toggle:
                    self._controller.toggle_event_completed(event_id)
                else:
                    self.event_context_menu.emit(event_id, event.globalPos())
                return

        if sd is not None:
            # Cell context menu
            action_new = menu.addAction("➕  New Event")
            action_today = menu.addAction("📍  Go to Today")

            chosen = menu.exec(event.globalPos())
            if chosen is None:
                return

            if chosen == action_new:
                dt = sd.to_datetime(9, 0)
                self.create_event_requested.emit(dt)
            elif chosen == action_today:
                self._controller.go_today()
            return

        event.ignore()

    @staticmethod
    def _menu_stylesheet() -> str:
        """Dark-themed stylesheet for context menus."""
        return (
            "QMenu {"
            "  background-color: #1A1A1E;"
            "  color: #F5F0DC;"
            "  border: 1px solid #2A2A33;"
            "  border-radius: 6px;"
            "  padding: 4px 0px;"
            "}"
            "QMenu::item {"
            "  padding: 6px 24px 6px 16px;"
            "  border-radius: 3px;"
            "}"
            "QMenu::item:selected {"
            "  background-color: #2A2A32;"
            "}"
            "QMenu::separator {"
            "  height: 1px;"
            "  background: #2A2A33;"
            "  margin: 4px 8px;"
            "}"
        )

    # ── Keyboard Navigation ──

    def keyPressEvent(self, event: QKeyEvent) -> None:  # noqa: N802
        key = event.key()
        modifiers = event.modifiers()

        # Arrow keys → move selection
        if key == Qt.Key_Left:
            self._selection.move("left", extend=bool(modifiers & Qt.ShiftModifier))
            self._ensure_selected_visible()
            event.accept()
            return

        if key == Qt.Key_Right:
            self._selection.move("right", extend=bool(modifiers & Qt.ShiftModifier))
            self._ensure_selected_visible()
            event.accept()
            return

        if key == Qt.Key_Up:
            self._selection.move("up", extend=bool(modifiers & Qt.ShiftModifier))
            self._ensure_selected_visible()
            event.accept()
            return

        if key == Qt.Key_Down:
            self._selection.move("down", extend=bool(modifiers & Qt.ShiftModifier))
            self._ensure_selected_visible()
            event.accept()
            return

        # Page Up / Page Down → previous / next month
        if key == Qt.Key_PageUp:
            self._controller.go_prev()
            event.accept()
            return

        if key == Qt.Key_PageDown:
            self._controller.go_next()
            event.accept()
            return

        # Home → first day of month
        if key == Qt.Key_Home:
            self._selection.move("home")
            event.accept()
            return

        # End → last day of month
        if key == Qt.Key_End:
            self._selection.move("end")
            event.accept()
            return

        # Enter/Return → activate
        if key in (Qt.Key_Return, Qt.Key_Enter):
            sel_event = self._selection.selected_event_id
            if sel_event:
                self.event_activated.emit(sel_event)
            else:
                sel_date = self._selection.selected_date
                dt = sel_date.to_datetime(9, 0)
                self.create_event_requested.emit(dt)
            event.accept()
            return

        # Delete → delete selected event
        if key == Qt.Key_Delete:
            sel_event = self._selection.selected_event_id
            if sel_event:
                self._controller.delete_event(sel_event)
            event.accept()
            return

        # T → go to today
        if key == Qt.Key_T:
            self._controller.go_today()
            event.accept()
            return

        super().keyPressEvent(event)

    def _ensure_selected_visible(self) -> None:
        """If the selected date is outside the current month, navigate to it."""
        sel = self._selection.selected_date
        if sel.year != self._year or sel.month != self._month:
            self._controller.go_to_date(sel)
        else:
            self.update()

    # ── Zoom (Wheel Event) ──

    def wheelEvent(self, event: QWheelEvent) -> None:  # noqa: N802
        modifiers = event.modifiers()

        if modifiers & Qt.ControlModifier:
            # Zoom: adjust max visible events per cell
            delta = event.angleDelta().y()
            if delta > 0:
                self._max_visible_events = min(self._max_visible_events + 1, 10)
            else:
                self._max_visible_events = max(self._max_visible_events - 1, 1)
            self.update()
            event.accept()
            return

        # Default: scroll to change month
        delta = event.angleDelta().y()
        if delta > 0:
            self._controller.go_prev()
        else:
            self._controller.go_next()
        event.accept()

    # ── Resize ──

    def resizeEvent(self, event) -> None:  # noqa: N802
        """Recalculate layout on resize."""
        self._recompute_layout()
        self.update()
        super().resizeEvent(event)

    # ── Focus ──

    def focusInEvent(self, event) -> None:  # noqa: N802
        self.update()
        super().focusInEvent(event)

    def focusOutEvent(self, event) -> None:  # noqa: N802
        self.update()
        super().focusOutEvent(event)
