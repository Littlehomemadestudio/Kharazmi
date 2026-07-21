"""
YearView — 12-month overview for the RASK! calendar.

Renders a 4×3 grid of mini-month calendars with:
  - Persian month names and weekday headers
  - Day numbers in Persian digits
  - Event indicator dots
  - Today highlight (gold circle)
  - Selected day highlight
  - Hover effect on individual days
  - Click → select + jump to month view
  - Double-click → jump to day view
  - Cached event data for fast repaints
"""
from __future__ import annotations

from typing import Optional

from PySide6.QtCore import Qt, Signal, QRectF, QSize
from PySide6.QtGui import QPainter, QColor, QPen, QBrush, QFont, QFontMetrics
from PySide6.QtWidgets import QWidget, QToolTip

from .controller import CalendarController
from .model import CalendarModel
from .selection import SelectionManager
from .theme import (
    Surface, Gold, Text, Border, Metrics, Spacing,
    qcolor, with_alpha,
    font_header, font_body, font_small, font_mini_day,
)
from ...core.shamsi import (
    ShamsiDate, shamsi_month_grid, days_in_month, to_persian_digits,
    SHAMSI_MONTHS_FA, SHAMSI_WEEKDAYS_SHORT_EN,
)
from ...calendar.enums import CalendarViewKind


# ────────────────────────────── Layout Constants ─────────────────────────────

_COLS = 4
_ROWS = 3
_WEEK_DAYS = 7          # Sat .. Fri
_GRID_ROWS = 6          # max weeks in a month

# Derived from theme Metrics
_CELL = Metrics.YEAR_CELL_SIZE
_MONTH_PAD = Metrics.YEAR_MONTH_PAD
_YEAR_HEADER_H = Metrics.YEAR_HEADER_H

# Mini-month internal measurements
_MONTH_NAME_H = 20      # height for the month name label
_WKDAY_H = 16           # height for the weekday header row
_DOT_R = 2              # radius of the event indicator dot
_DOT_GAP = 1            # gap between multiple dots
_MAX_DOTS = 3           # max event dots per cell

# ────────────────────────────── Pre-computed Colors ──────────────────────────

_C_BG           = qcolor(Surface.CANVAS)
_C_CARD         = qcolor(Surface.CARD)
_C_CARD_HOVER   = qcolor(Surface.CARD_HOVER)
_C_TEXT_PRI     = qcolor(Text.PRIMARY)
_C_TEXT_SEC     = qcolor(Text.SECONDARY)
_C_TEXT_TER     = qcolor(Text.TERTIARY)
_C_TEXT_MUTED   = with_alpha(Text.SECONDARY, 50)
_C_GOLD         = qcolor(Gold.PRIMARY)
_C_GOLD_BRIGHT  = qcolor(Gold.BRIGHT)
_C_GOLD_GLOW    = Gold.GLOW
_C_WEEKEND      = qcolor(Text.WEEKEND)
_C_WEEKEND_DIM  = with_alpha(Text.WEEKEND, 80)
_C_BORDER       = qcolor(Border.SUBTLE)
_C_HOVER_BG     = qcolor(Surface.CARD_HOVER)
_C_SELECT_BG    = with_alpha(Gold.PRIMARY, 35)
_C_OTHER_MONTH  = with_alpha(Text.TERTIARY, 40)
_C_TODAY_CIRCLE = qcolor(Gold.PRIMARY)

_PEN_BORDER     = QPen(_C_BORDER, 1)
_PEN_NO_BORDER  = QPen(Qt.NoPen)
_BRUSH_NONE     = QBrush(Qt.NoBrush)


# ═════════════════════════════════════════════════════════════════════════════
#  YearView
# ═════════════════════════════════════════════════════════════════════════════

class YearView(QWidget):
    """
    A 4×3 grid of mini-month calendars for a Shamsi year.

    Signals
    -------
    month_activated : (int, int)
        Emitted on single-click; carries (year, month) so the parent can
        switch to month view on that month.
    day_activated : ShamsiDate
        Emitted on double-click; carries the Shamsi date so the parent can
        switch to day view on that date.
    """

    month_activated = Signal(int, int)       # year, month
    day_activated   = Signal(object)          # ShamsiDate

    # ──────────────────────────── Constructor ────────────────────────────────

    def __init__(self, controller: CalendarController, parent=None):
        super().__init__(parent)

        self._ctrl = controller
        self._model: CalendarModel = controller.model
        self._sel: SelectionManager = controller.selection

        self._year: int = ShamsiDate.today().year

        # Hover tracking: (month_index 0-11, grid_row 0-5, grid_col 0-6)
        self._hover: Optional[tuple[int, int, int]] = None

        # Event cache:  month_index (0-11) → { day_number → [color_hex, …] }
        self._event_cache: dict[int, dict[int, list[str]]] = {}

        # Pre-compute month grids (rebuild only when the year changes)
        self._grids: list[list[list[Optional[ShamsiDate]]]] = []
        self._rebuild_grids()

        # Connect controller signals
        self._ctrl.events_changed.connect(self.refresh)
        self._ctrl.date_changed.connect(self._on_date_changed)
        self._sel.selection_changed.connect(self.update)

        self.setMouseTracking(True)
        self.setFocusPolicy(Qt.StrongFocus)
        self.setMinimumSize(self._compute_min_size())

    # ──────────────────────────── Public API ─────────────────────────────────

    def set_year(self, year: int) -> None:
        """Set the displayed Shamsi year and rebuild the grid."""
        if self._year == year:
            return
        self._year = year
        self._rebuild_grids()
        self._load_event_cache()
        self.update()

    def refresh(self) -> None:
        """Reload events from the model and repaint."""
        self._load_event_cache()
        self.update()

    # ──────────────────────────── Size Hints ─────────────────────────────────

    def sizeHint(self) -> QSize:                                # noqa: N802
        return self._compute_ideal_size()

    # ──────────────────────────── Paint ──────────────────────────────────────

    def paintEvent(self, event) -> None:                       # noqa: N802
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing, True)
        p.setRenderHint(QPainter.TextAntialiasing, True)

        # Canvas background
        p.fillRect(self.rect(), _C_BG)

        # Year header
        self._paint_year_header(p)

        # Mini months
        for idx in range(12):
            rect = self._month_rect(idx)
            self._paint_mini_month(p, rect, self._year, idx + 1, idx)

        p.end()

    # ──────────────────────────── Mouse Events ───────────────────────────────

    def mousePressEvent(self, ev) -> None:                     # noqa: N802
        if ev.button() != Qt.LeftButton:
            return
        cell = self._cell_at(ev.position().toPoint())
        if cell is None:
            return
        mi, row, col = cell
        sd = self._shamsi_at(mi, row, col)
        if sd is None:
            return
        self._sel.selected_date = sd
        self.month_activated.emit(sd.year, sd.month)
        self.update()

    def mouseDoubleClickEvent(self, ev) -> None:               # noqa: N802
        if ev.button() != Qt.LeftButton:
            return
        cell = self._cell_at(ev.position().toPoint())
        if cell is None:
            return
        mi, row, col = cell
        sd = self._shamsi_at(mi, row, col)
        if sd is None:
            return
        self._sel.selected_date = sd
        self.day_activated.emit(sd)

    def mouseMoveEvent(self, ev) -> None:                      # noqa: N802
        cell = self._cell_at(ev.position().toPoint())
        if cell == self._hover:
            return

        self._hover = cell
        self.update()

        # Tooltip with event count
        if cell is not None:
            mi, row, col = cell
            sd = self._shamsi_at(mi, row, col)
            if sd is not None:
                ev_cache = self._event_cache.get(mi, {})
                dots = ev_cache.get(sd.day, [])
                if dots:
                    n = len(dots)
                    tip = f"{to_persian_digits(str(n))} رویداد"
                    QToolTip.showText(ev.globalPosition().toPoint(), tip, self)
                else:
                    QToolTip.hideText()
            else:
                QToolTip.hideText()
        else:
            QToolTip.hideText()

    def leaveEvent(self, ev) -> None:                           # noqa: N802
        if self._hover is not None:
            self._hover = None
            self.update()
        QToolTip.hideText()

    # ──────────────────────── Internal: Grid Data ────────────────────────────

    def _rebuild_grids(self) -> None:
        """Recompute the 6×7 grids for all 12 months."""
        self._grids = [
            shamsi_month_grid(self._year, m) for m in range(1, 13)
        ]

    def _load_event_cache(self) -> None:
        """
        Load event data for all 12 months from the model.

        For each month we build a map:  day_number → [color_hex, …]
        so the painter can quickly look up whether a day has events
        and what colours to draw for the indicator dots.

        Multi-day events that cross month boundaries are handled by
        clipping the span to the current month's day range.
        """
        self._event_cache.clear()

        for mi in range(12):
            month = mi + 1
            month_first = ShamsiDate(self._year, month, 1)
            month_last_day = days_in_month(self._year, month)
            month_last = ShamsiDate(self._year, month, month_last_day)

            events = self._model.events_in_month(self._year, month)
            day_map: dict[int, list[str]] = {}

            for evt in events:
                color = self._model.event_color(evt)

                # Convert event boundaries to Shamsi
                s_start = ShamsiDate.from_datetime(evt.start)
                s_end = (
                    ShamsiDate.from_datetime(evt.end)
                    if evt.end is not None
                    else s_start
                )

                # Clip the event span to the current month
                eff_start_day: int
                if s_start < month_first:
                    eff_start_day = 1
                elif s_start <= month_last:
                    eff_start_day = s_start.day
                else:
                    # Event starts after this month — skip
                    continue

                eff_end_day: int
                if s_end > month_last:
                    eff_end_day = month_last_day
                elif s_end >= month_first:
                    eff_end_day = s_end.day
                else:
                    # Event ends before this month — skip
                    continue

                if eff_end_day < eff_start_day:
                    continue

                for d in range(eff_start_day, eff_end_day + 1):
                    day_map.setdefault(d, []).append(color)

            self._event_cache[mi] = day_map

    def _on_date_changed(self) -> None:
        """Respond to navigation date changes from the controller."""
        nav = self._ctrl.nav_date
        if nav.year != self._year:
            self.set_year(nav.year)
        else:
            self.update()

    # ──────────────────────── Internal: Layout ───────────────────────────────

    def _mini_month_size(self) -> tuple[float, float]:
        """Return (width, height) of one mini-month block."""
        w = _WEEK_DAYS * _CELL + 2 * _MONTH_PAD
        h = _MONTH_NAME_H + _WKDAY_H + _GRID_ROWS * _CELL + 2 * _MONTH_PAD
        return w, h

    def _month_rect(self, month_index: int) -> QRectF:
        """QRectF for the mini-month at *month_index* (0=Farvardin … 11=Esfand)."""
        mw, mh = self._mini_month_size()
        col = month_index % _COLS
        row = month_index // _COLS

        # Centre the grid horizontally within the widget
        total_grid_w = _COLS * mw + (_COLS - 1) * _MONTH_PAD
        offset_x = max((self.width() - total_grid_w) / 2, _MONTH_PAD)

        x = offset_x + col * (mw + _MONTH_PAD)
        y = _YEAR_HEADER_H + row * (mh + _MONTH_PAD)

        return QRectF(x, y, mw, mh)

    def _cell_rect(self, month_rect: QRectF, row: int, col: int) -> QRectF:
        """QRectF for a single day cell inside a mini-month."""
        x = month_rect.x() + _MONTH_PAD + col * _CELL
        y = month_rect.y() + _MONTH_PAD + _MONTH_NAME_H + _WKDAY_H + row * _CELL
        return QRectF(x, y, _CELL, _CELL)

    def _cell_at(self, pos) -> Optional[tuple[int, int, int]]:
        """
        Determine which (month_index, grid_row, grid_col) the point falls on.

        Returns None if the point is outside any mini-month or on
        non-interactive space (month name, weekday headers, padding).
        """
        fx = pos.x()
        fy = pos.y()
        for mi in range(12):
            mr = self._month_rect(mi)
            if not mr.contains(fx, fy):
                continue
            # Inside this mini-month — locate the cell
            local_x = fx - mr.x() - _MONTH_PAD
            local_y = fy - mr.y() - _MONTH_PAD
            if local_x < 0 or local_y < 0:
                return None
            col = int(local_x / _CELL)
            row = int((local_y - _MONTH_NAME_H - _WKDAY_H) / _CELL)
            if not (0 <= col < _WEEK_DAYS and 0 <= row < _GRID_ROWS):
                return None
            return (mi, row, col)
        return None

    def _shamsi_at(self, mi: int, row: int, col: int) -> Optional[ShamsiDate]:
        """Return the ShamsiDate at a grid cell, or None if it's empty."""
        if 0 <= mi < len(self._grids):
            grid = self._grids[mi]
            if 0 <= row < len(grid) and 0 <= col < len(grid[row]):
                return grid[row][col]
        return None

    def _compute_min_size(self) -> QSize:
        mw, mh = self._mini_month_size()
        total_w = int(_COLS * mw + (_COLS + 1) * _MONTH_PAD)
        total_h = int(_YEAR_HEADER_H + _ROWS * mh + (_ROWS + 1) * _MONTH_PAD)
        return QSize(total_w, total_h)

    def _compute_ideal_size(self) -> QSize:
        return self._compute_min_size()

    # ──────────────────────── Internal: Painting ─────────────────────────────

    def _paint_year_header(self, p: QPainter) -> None:
        """Paint the year number at the top."""
        font = font_header()
        p.setFont(font)
        p.setPen(_C_TEXT_PRI)

        year_text = to_persian_digits(str(self._year))
        fm = QFontMetrics(font)
        tw = fm.horizontalAdvance(year_text)
        x = (self.width() - tw) / 2
        p.drawText(QRectF(x, 0, tw, _YEAR_HEADER_H), Qt.AlignCenter, year_text)

    def _paint_mini_month(self, p: QPainter, rect: QRectF,
                          year: int, month: int, mi: int) -> None:
        """Paint one mini-month inside *rect*."""
        # ── Card background ──
        p.setPen(_PEN_BORDER)
        p.setBrush(_C_CARD)
        r = rect.adjusted(0.5, 0.5, -0.5, -0.5)
        p.drawRoundedRect(r, 4, 4)

        # ── Month name ──
        p.setPen(_C_TEXT_PRI)
        p.setFont(font_small())
        month_name = SHAMSI_MONTHS_FA[mi]
        p.drawText(
            QRectF(rect.x(), rect.y() + _MONTH_PAD, rect.width(), _MONTH_NAME_H),
            Qt.AlignCenter,
            month_name,
        )

        # ── Weekday headers ──
        p.setFont(font_mini_day())
        header_y = rect.y() + _MONTH_PAD + _MONTH_NAME_H
        for ci, wk in enumerate(SHAMSI_WEEKDAYS_SHORT_EN):
            cx = rect.x() + _MONTH_PAD + ci * _CELL
            cell_rect = QRectF(cx, header_y, _CELL, _WKDAY_H)
            # Friday (index 6) gets weekend colour; Saturday (index 0) also
            if ci == 6:
                p.setPen(_C_WEEKEND_DIM)
            elif ci == 0:
                p.setPen(_C_WEEKEND_DIM)
            else:
                p.setPen(_C_TEXT_TER)
            p.drawText(cell_rect, Qt.AlignCenter, wk)

        # ── Day cells ──
        today = ShamsiDate.today()
        selected = self._sel.selected_date
        grid = self._grids[mi] if mi < len(self._grids) else []
        ev_cache = self._event_cache.get(mi, {})

        p.setFont(font_mini_day())

        for row in range(_GRID_ROWS):
            for col in range(_WEEK_DAYS):
                cell = self._cell_rect(rect, row, col)
                sd: Optional[ShamsiDate] = (
                    grid[row][col]
                    if row < len(grid) and col < len(grid[row])
                    else None
                )

                if sd is None:
                    continue

                is_today = (sd == today)
                is_selected = (sd == selected)
                is_friday = (col == 6)
                is_saturday = (col == 0)
                is_other_month = (sd.month != month)
                is_hovered = (self._hover == (mi, row, col))

                # ── Cell background ──
                if is_selected:
                    p.setPen(_PEN_NO_BORDER)
                    p.setBrush(_C_SELECT_BG)
                    p.drawRoundedRect(cell.adjusted(1, 1, -1, -1), 3, 3)
                elif is_hovered and not is_other_month:
                    p.setPen(_PEN_NO_BORDER)
                    p.setBrush(_C_HOVER_BG)
                    p.drawRoundedRect(cell.adjusted(1, 1, -1, -1), 3, 3)

                # ── Today gold circle ──
                if is_today:
                    p.setPen(QPen(_C_TODAY_CIRCLE, 1.5))
                    p.setBrush(Qt.NoBrush)
                    circle_r = min(cell.width(), cell.height()) / 2 - 2
                    center = cell.center()
                    p.drawEllipse(center, circle_r, circle_r)

                # ── Day number ──
                if is_other_month:
                    p.setPen(_C_OTHER_MONTH)
                elif is_today:
                    p.setPen(_C_GOLD_BRIGHT)
                elif is_friday or is_saturday:
                    p.setPen(_C_WEEKEND)
                elif is_selected:
                    p.setPen(_C_TEXT_PRI)
                else:
                    p.setPen(_C_TEXT_SEC)

                day_text = to_persian_digits(str(sd.day))
                text_rect = cell.adjusted(0, 0, 0, -3)  # leave room for dots
                p.drawText(text_rect, Qt.AlignCenter, day_text)

                # ── Event dots ──
                colors = ev_cache.get(sd.day)
                if colors and not is_other_month:
                    n_dots = min(len(colors), _MAX_DOTS)
                    dot_total_w = n_dots * (_DOT_R * 2) + (n_dots - 1) * _DOT_GAP
                    left_edge = cell.center().x() - dot_total_w / 2
                    dot_y = cell.bottom() - _DOT_R - 1

                    p.setPen(Qt.NoPen)
                    for di in range(n_dots):
                        dot_color = qcolor(colors[di])
                        p.setBrush(dot_color)
                        dx = left_edge + di * (_DOT_R * 2 + _DOT_GAP) + _DOT_R
                        p.drawEllipse(QRectF(dx - _DOT_R, dot_y - _DOT_R,
                                             _DOT_R * 2, _DOT_R * 2))
