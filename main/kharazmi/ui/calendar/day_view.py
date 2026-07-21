"""
DayView — Single-day detailed view for the RASK! calendar.

Renders a 24-hour timeline (like Google Calendar's day view) with:
  - Day header showing the Persian date with gold accent for today
  - All-day event area at the top
  - Time ruler on the left with Shamsi/Persian digit labels
  - Hour / half-hour / quarter-hour grid lines
  - Current-time red line with dot (auto-updates every 60 seconds)
  - Timed event blocks positioned via collision layout (side-by-side overlap)
  - Drag-to-create (click empty space, drag down, snap to 15 min)
  - Drag-to-move (handled by EventWidget, committed here)
  - Drag-to-resize (bottom handle, handled by EventWidget, committed here)
  - Click to select, double-click to create / activate
  - Smooth scrolling with auto-scroll to current time on load

All dates and time labels use the Shamsi calendar with Persian digits.
"""
from __future__ import annotations

from datetime import datetime, timedelta
from typing import Optional

from PySide6.QtCore import Qt, Signal, QTimer, QRectF, QPoint, QDateTime
from PySide6.QtGui import QPainter, QColor, QPen, QBrush, QFont, QCursor, QMouseEvent
from PySide6.QtWidgets import QWidget, QScrollArea, QVBoxLayout, QFrame

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
from ...core.shamsi import ShamsiDate, to_persian_digits, format_shamsi
from ...calendar.event import Event
from ...calendar.enums import CalendarViewKind


# ──────────────────────────────── Layout constants ──────────────────────────

_HOUR_HEIGHT: int = Metrics.HOUR_HEIGHT          # 60 px per hour
_RULER_W: int = Metrics.TIME_RULER_WIDTH         # 52 px
_ALL_DAY_ROW_H: int = Metrics.ALL_DAY_ROW_HEIGHT # 28 px
_ALL_DAY_MAX: int = Metrics.ALL_DAY_MAX_ROWS     # 3
_SNAP_MIN: int = Metrics.SNAP_MINUTES            # 15 min
_MIN_EVENT_H: int = Metrics.MIN_EVENT_HEIGHT     # 22 px
_EVENT_PAD: int = Metrics.EVENT_PAD              # 4 px
_SCROLL_STEP: int = Metrics.SCROLL_STEP          # 30 px
_DRAG_THRESHOLD: int = Metrics.DRAG_THRESHOLD    # 5 px
_NOW_LINE_W: int = Metrics.NOW_LINE_WIDTH        # 2 px

_CONTENT_HEIGHT: int = 24 * _HOUR_HEIGHT         # 1440 px for full day
_ALL_DAY_PAD: int = 4
_ALL_DAY_CHIP_H: int = 24
_ALL_DAY_CHIP_GAP: int = 2
_HEADER_H: int = 40
_NOW_TIMER_MS: int = 60_000                      # 1 minute refresh


# ──────────────────────────────── _DayGridWidget ────────────────────────────

class _DayGridWidget(QWidget):
    """
    Custom-painted 24-hour grid that hosts EventWidget children.

    Paints the time ruler labels, grid lines, current-time indicator,
    drag-to-create selection rectangle, and a hover time guide line.
    EventWidgets are positioned as child widgets on top of this grid.

    Parented inside the QScrollArea of DayView.
    """

    def __init__(self, day_view: "DayView", parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._day_view = day_view

        self.setMinimumHeight(_CONTENT_HEIGHT)
        self.setMinimumWidth(300)
        self.setMouseTracking(True)

        # Drag-to-create state
        self._drag_creating: bool = False
        self._drag_create_start_y: int = 0
        self._drag_create_current_y: int = 0

        # Hover time guide (subtle dashed line at snapped cursor position)
        self._hover_y: Optional[int] = None

    # ── Coordinate ↔ Time conversion ────────────────────────────────────────

    def y_to_datetime(self, y: int) -> datetime:
        """Convert a Y pixel position to a datetime, snapped to 15 min."""
        day = self._day_view._day
        total_minutes = y * 60 / _HOUR_HEIGHT
        snapped = round(total_minutes / _SNAP_MIN) * _SNAP_MIN
        snapped = max(0, min(24 * 60 - _SNAP_MIN, snapped))
        return day.to_datetime(hour=int(snapped // 60), minute=int(snapped % 60))

    def datetime_to_y(self, dt: datetime) -> int:
        """Convert a datetime to a Y pixel position within this grid."""
        day_dt = self._day_view._day.to_datetime()
        delta_minutes = (dt - day_dt).total_seconds() / 60.0
        return int(delta_minutes * _HOUR_HEIGHT / 60)

    def column_left(self) -> int:
        """X coordinate where the day column starts (after the time ruler)."""
        return _RULER_W

    def column_width(self) -> int:
        """Pixel width of the day column area."""
        return max(self.width() - _RULER_W, 100)

    # ── Snap helper ─────────────────────────────────────────────────────────

    @staticmethod
    def _snap_y(y: int) -> int:
        """Snap a Y pixel position to the nearest 15-minute grid line."""
        minutes = y * 60 / _HOUR_HEIGHT
        snapped = round(minutes / _SNAP_MIN) * _SNAP_MIN
        return int(snapped * _HOUR_HEIGHT / 60)

    # ── Painting ────────────────────────────────────────────────────────────

    def paintEvent(self, event) -> None:  # noqa: N802
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, True)
        painter.setRenderHint(QPainter.TextAntialiasing, True)

        self._paint_background(painter)
        self._paint_grid_lines(painter)
        self._paint_time_ruler(painter)
        self._paint_now_line(painter)
        self._paint_hover_line(painter)
        self._paint_drag_create(painter)

        painter.end()

    def _paint_background(self, p: QPainter) -> None:
        """Fill the ruler and day-column backgrounds."""
        w, h = self.width(), self.height()
        cl = self.column_left()
        cw = self.column_width()

        # Ruler background (darker)
        p.setPen(Qt.NoPen)
        p.setBrush(QBrush(qcolor(Surface.CANVAS)))
        p.drawRect(0, 0, _RULER_W, h)

        # Day column background
        p.setBrush(QBrush(qcolor(Surface.PANEL)))
        p.drawRect(cl, 0, cw, h)

        # Thin vertical separator between ruler and column
        sep_pen = QPen(qcolor(Border.SUBTLE), 1.0)
        sep_pen.setCosmetic(True)
        p.setPen(sep_pen)
        p.drawLine(cl, 0, cl, h)

    def _paint_grid_lines(self, p: QPainter) -> None:
        """Draw hour, half-hour, and quarter-hour horizontal lines."""
        cl = self.column_left()
        cr = self.width()

        for hour in range(25):
            y = hour * _HOUR_HEIGHT

            # ── Full-hour line ──
            pen = QPen(qcolor(Border.SUBTLE), 1.0)
            pen.setCosmetic(True)
            p.setPen(pen)
            p.drawLine(cl, y, cr, y)

            if hour >= 24:
                continue

            # ── Sub-ticks within the hour ──
            for sub in range(1, 4):
                sub_y = y + sub * (_HOUR_HEIGHT // 4)

                if sub == 2:
                    # Half-hour — slightly visible dashed line across the column
                    c = qcolor(Border.SUBTLE)
                    c.setAlpha(120)
                    pen = QPen(c, 1.0)
                    pen.setCosmetic(True)
                    p.setPen(pen)
                    p.drawLine(cl, sub_y, cr, sub_y)
                else:
                    # Quarter-hour — very subtle, short line on the left only
                    c = qcolor(Border.SUBTLE)
                    c.setAlpha(50)
                    pen = QPen(c, 1.0)
                    pen.setCosmetic(True)
                    p.setPen(pen)
                    p.drawLine(cl + 1, sub_y, cl + 24, sub_y)

    def _paint_time_ruler(self, p: QPainter) -> None:
        """Render hour labels (۸:۰۰, ۹:۰۰, …) on the left ruler area."""
        font = font_time_label()
        p.setFont(font)
        fm = p.fontMetrics()

        for hour in range(24):
            y = hour * _HOUR_HEIGHT

            # Hour label right-aligned in the ruler
            label = to_persian_digits(f"{hour:02d}:۰۰")
            p.setPen(QPen(qcolor(Text.TERTIARY)))

            rect = QRectF(0, y - fm.height() - 2, _RULER_W - 10, fm.height())
            p.drawText(rect, Qt.AlignRight | Qt.AlignVCenter, label)

    def _paint_now_line(self, p: QPainter) -> None:
        """Paint the red current-time line with a circular dot."""
        day = self._day_view._day
        if day != ShamsiDate.today():
            return

        now = datetime.now()
        total_minutes = now.hour * 60 + now.minute + now.second / 60.0
        now_y = int(total_minutes * _HOUR_HEIGHT / 60)

        cl = self.column_left()
        cr = self.width()

        # Red line spanning the day column
        pen = QPen(NowLine.COLOR, _NOW_LINE_W)
        pen.setCosmetic(True)
        p.setPen(pen)
        p.drawLine(cl, now_y, cr, now_y)

        # Red dot at the left edge of the day column
        dot_r = 5.0
        p.setPen(Qt.NoPen)
        p.setBrush(QBrush(NowLine.DOT))
        p.drawEllipse(QRectF(cl - dot_r, now_y - dot_r, dot_r * 2, dot_r * 2))

    def _paint_hover_line(self, p: QPainter) -> None:
        """Draw a subtle dashed guide line at the mouse hover position."""
        if self._hover_y is None or self._drag_creating:
            return

        cl = self.column_left()
        cr = self.width()

        c = qcolor(Text.TERTIARY)
        c.setAlpha(50)
        pen = QPen(c, 1.0, Qt.DashLine)
        pen.setCosmetic(True)
        p.setPen(pen)
        p.drawLine(cl, self._hover_y, cr, self._hover_y)

    def _paint_drag_create(self, p: QPainter) -> None:
        """Paint the translucent selection rectangle during drag-to-create."""
        if not self._drag_creating:
            return

        cl = self.column_left()
        cw = self.column_width()

        y_top = min(self._drag_create_start_y, self._drag_create_current_y)
        y_bot = max(self._drag_create_start_y, self._drag_create_current_y)

        min_drag_px = _HOUR_HEIGHT * _SNAP_MIN / 60  # 15-min worth of pixels
        if y_bot - y_top < min_drag_px:
            # Not enough drag yet — just show a thin indicator at start
            p.setPen(Qt.NoPen)
            p.setBrush(QBrush(with_alpha(Gold.PRIMARY, 25)))
            p.drawRect(cl + 2, y_top, cw - 4, 3)
            return

        rect = QRectF(cl + 2, y_top, cw - 4, y_bot - y_top)

        # Translucent gold fill
        p.setPen(Qt.NoPen)
        p.setBrush(QBrush(with_alpha(Gold.PRIMARY, 30)))
        p.drawRoundedRect(rect, 4, 4)

        # Gold border
        p.setPen(QPen(with_alpha(Gold.PRIMARY, 100), 1.5))
        p.setBrush(Qt.NoBrush)
        p.drawRoundedRect(rect, 4, 4)

        # Time label inside the selection
        start_dt = self.y_to_datetime(y_top)
        end_dt = self.y_to_datetime(y_bot)
        start_str = to_persian_digits(f"{start_dt.hour:02d}:{start_dt.minute:02d}")
        end_str = to_persian_digits(f"{end_dt.hour:02d}:{end_dt.minute:02d}")
        time_label = f"{start_str} – {end_str}"

        label_font = font_small()
        p.setFont(label_font)
        p.setPen(QPen(qcolor(Gold.PRIMARY)))
        label_fm = p.fontMetrics()
        label_rect = QRectF(
            rect.left() + 6, rect.top() + 3,
            rect.width() - 12, label_fm.height(),
        )
        p.drawText(label_rect, Qt.AlignLeft | Qt.AlignTop, time_label)

    # ── Mouse events (drag-to-create) ──────────────────────────────────────

    def mousePressEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        if event.button() == Qt.LeftButton:
            pos = event.position().toPoint()
            if pos.x() >= self.column_left():
                # Click inside the day column — begin drag-to-create
                self._drag_creating = True
                self._drag_create_start_y = self._snap_y(pos.y())
                self._drag_create_current_y = self._drag_create_start_y
                self._day_view._deselect_all()
                self.update()
                event.accept()
                return

        # Click on the ruler area — deselect only
        self._day_view._deselect_all()

    def mouseMoveEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        pos = event.position().toPoint()

        # Update hover guide line
        if pos.x() >= self.column_left():
            self._hover_y = self._snap_y(pos.y())
        else:
            self._hover_y = None

        if self._drag_creating:
            self._drag_create_current_y = self._snap_y(pos.y())
            self.update()
            event.accept()
            return

        self.update()

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        if event.button() == Qt.LeftButton and self._drag_creating:
            self._drag_creating = False

            y_top = min(self._drag_create_start_y, self._drag_create_current_y)
            y_bot = max(self._drag_create_start_y, self._drag_create_current_y)

            min_drag_px = _HOUR_HEIGHT * _SNAP_MIN / 60
            if y_bot - y_top >= min_drag_px:
                # Significant drag — create an event spanning the selection
                start_dt = self.y_to_datetime(y_top)
                end_dt = self.y_to_datetime(y_bot)
                self._day_view.create_event_requested.emit(start_dt)
                self._day_view._controller.create_event_at(start_dt, end_dt)
            # else: just a click in empty space — already deselected above

            self.update()
            event.accept()
            return

        event.ignore()

    def mouseDoubleClickEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        if event.button() == Qt.LeftButton:
            pos = event.position().toPoint()
            if pos.x() >= self.column_left():
                # Cancel any residual drag-to-create from the first click
                self._drag_creating = False

                dt = self.y_to_datetime(self._snap_y(pos.y()))
                self._day_view.create_event_requested.emit(dt)
                self._day_view._controller.create_event_at(dt)
                event.accept()
                return
        event.ignore()

    def leaveEvent(self, event) -> None:  # noqa: N802
        self._hover_y = None
        self.update()
        super().leaveEvent(event)


# ──────────────────────────────── _AllDayArea ───────────────────────────────

class _AllDayArea(QWidget):
    """
    Renders all-day event chips above the time grid.

    Shows up to ALL_DAY_MAX_ROWS chips. If there are more, a
    "+N more" indicator is shown. The left side has a "کل‌روز"
    label aligned with the time ruler.
    """

    def __init__(self, day_view: "DayView", parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._day_view = day_view
        self._events: list[Event] = []
        self._colors: dict[str, str] = {}
        self._hovered_idx: int = -1
        self._selected_id: Optional[str] = None
        self.setMouseTracking(True)
        self._update_height()

    def set_events(self, events: list[Event], colors: dict[str, str]) -> None:
        """Replace the displayed all-day events and repaint."""
        self._events = list(events)
        self._colors = dict(colors)
        self._hovered_idx = -1
        self._selected_id = None
        self._update_height()
        self.update()

    def _update_height(self) -> None:
        n = max(len(self._events), 1)
        rows = min(n, _ALL_DAY_MAX)
        self.setFixedHeight(rows * _ALL_DAY_ROW_H + _ALL_DAY_PAD * 2)

    # ── Painting ────────────────────────────────────────────────────────────

    def paintEvent(self, event) -> None:  # noqa: N802
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing, True)

        w, h = self.width(), self.height()

        # Background
        p.setPen(Qt.NoPen)
        p.setBrush(QBrush(qcolor(Surface.CANVAS)))
        p.drawRect(0, 0, w, h)

        # Bottom border
        border_pen = QPen(qcolor(Border.SUBTLE), 1.0)
        border_pen.setCosmetic(True)
        p.setPen(border_pen)
        p.drawLine(0, h - 1, w, h - 1)

        # "کل‌روز" label on the ruler area
        if self._events:
            label_font = font_small()
            p.setFont(label_font)
            p.setPen(QPen(qcolor(Text.TERTIARY)))
            p.drawText(
                QRectF(0, 0, _RULER_W - 10, h),
                Qt.AlignRight | Qt.AlignVCenter,
                "کل\u200cروز",
            )

        # Event chips
        chip_x = _RULER_W + _ALL_DAY_PAD
        chip_w = w - chip_x - _ALL_DAY_PAD

        for i, evt in enumerate(self._events):
            if i >= _ALL_DAY_MAX:
                # Overflow indicator
                remaining = len(self._events) - _ALL_DAY_MAX
                overflow_label = f"+{to_persian_digits(str(remaining))} مورد دیگر"
                p.setFont(font_small())
                p.setPen(QPen(qcolor(Text.TERTIARY)))
                y_center = _ALL_DAY_PAD + _ALL_DAY_MAX * _ALL_DAY_ROW_H - _ALL_DAY_ROW_H // 2
                p.drawText(
                    QRectF(chip_x, y_center - 10, chip_w, 20),
                    Qt.AlignLeft | Qt.AlignVCenter,
                    overflow_label,
                )
                break

            y = _ALL_DAY_PAD + i * (_ALL_DAY_CHIP_H + _ALL_DAY_CHIP_GAP)
            chip_rect = QRectF(chip_x, y, chip_w, _ALL_DAY_CHIP_H)
            color = self._colors.get(evt.id, Gold.PRIMARY)
            hovered = (i == self._hovered_idx)
            selected = (evt.id == self._selected_id)
            EventRenderer.paint_all_day_chip(p, chip_rect, evt, color, hovered, selected)

        p.end()

    # ── Hit testing ─────────────────────────────────────────────────────────

    def _chip_index_at(self, pos: QPoint) -> int:
        """Return the index of the chip at *pos*, or -1 if none."""
        chip_x = _RULER_W + _ALL_DAY_PAD
        if pos.x() < chip_x:
            return -1
        for i in range(min(len(self._events), _ALL_DAY_MAX)):
            y = _ALL_DAY_PAD + i * (_ALL_DAY_CHIP_H + _ALL_DAY_CHIP_GAP)
            if y <= pos.y() <= y + _ALL_DAY_CHIP_H:
                return i
        return -1

    # ── Mouse events ────────────────────────────────────────────────────────

    def mouseMoveEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        old = self._hovered_idx
        self._hovered_idx = self._chip_index_at(event.position().toPoint())
        if self._hovered_idx != old:
            self.update()

    def mousePressEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        if event.button() == Qt.LeftButton:
            idx = self._chip_index_at(event.position().toPoint())
            if 0 <= idx < len(self._events):
                eid = self._events[idx].id
                self._selected_id = eid
                self._day_view._controller.selection.selected_event_id = eid
            else:
                self._selected_id = None
                self._day_view._deselect_all()
            self.update()

    def mouseDoubleClickEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        if event.button() == Qt.LeftButton:
            idx = self._chip_index_at(event.position().toPoint())
            if 0 <= idx < len(self._events):
                eid = self._events[idx].id
                self._day_view._controller.selection.selected_event_id = eid
                self._day_view.event_activated.emit(eid)

    def leaveEvent(self, event) -> None:  # noqa: N802
        self._hovered_idx = -1
        self.update()
        super().leaveEvent(event)


# ──────────────────────────────── _DayHeader ────────────────────────────────

class _DayHeader(QWidget):
    """
    Renders the day name and full Persian date in the header bar.

    Example: «سه‌شنبه  ۱۵  مرداد  ۱۴۰۳»

    When the displayed day is today, the text is gold and a small
    «امروز» badge appears next to the date.
    """

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._day: Optional[ShamsiDate] = None
        self._is_today: bool = False
        self.setFixedHeight(_HEADER_H)

    def set_day(self, shamsi: ShamsiDate) -> None:
        """Update the displayed date."""
        self._day = shamsi
        self._is_today = (shamsi == ShamsiDate.today())
        self.update()

    def paintEvent(self, event) -> None:  # noqa: N802
        if self._day is None:
            return

        p = QPainter(self)
        p.setRenderHint(QPainter.TextAntialiasing, True)

        w, h = self.width(), self.height()

        # Background
        p.setPen(Qt.NoPen)
        p.setBrush(QBrush(qcolor(Surface.CANVAS)))
        p.drawRect(0, 0, w, h)

        # Bottom border
        border_pen = QPen(qcolor(Border.SUBTLE), 1.0)
        border_pen.setCosmetic(True)
        p.setPen(border_pen)
        p.drawLine(0, h - 1, w, h - 1)

        # Date string: "سه‌شنبه  ۱۵  مرداد  ۱۴۰۳"
        date_text = self._day.format("EEEE  dd  MMMM  yyyy", use_persian_digits=True)

        header_font = font_header()
        p.setFont(header_font)

        if self._is_today:
            p.setPen(QPen(qcolor(Gold.PRIMARY)))
        else:
            p.setPen(QPen(qcolor(Text.PRIMARY)))

        text_x = _RULER_W + Spacing.MD
        text_area_w = w - text_x - Spacing.MD
        p.drawText(
            QRectF(text_x, 0, text_area_w, h),
            Qt.AlignLeft | Qt.AlignVCenter,
            date_text,
        )

        # "امروز" badge for today
        if self._is_today:
            badge_text = "امروز"
            badge_font = font_small()
            p.setFont(badge_font)
            badge_fm = p.fontMetrics()
            badge_w = badge_fm.horizontalAdvance(badge_text) + 14

            # Measure the main date text width to position the badge
            p.setFont(header_font)
            main_fm = p.fontMetrics()
            date_text_w = main_fm.horizontalAdvance(date_text)

            badge_x = text_x + date_text_w + Spacing.LG
            badge_rect = QRectF(badge_x, h / 2 - 10, badge_w, 20)

            # Badge background
            p.setPen(Qt.NoPen)
            p.setBrush(QBrush(with_alpha(Gold.PRIMARY, 40)))
            p.drawRoundedRect(badge_rect, 10, 10)

            # Badge text
            p.setFont(badge_font)
            p.setPen(QPen(qcolor(Gold.PRIMARY)))
            p.drawText(badge_rect, Qt.AlignCenter, badge_text)

        p.end()


# ──────────────────────────────── DayView ───────────────────────────────────

class DayView(QWidget):
    """
    Single-day detailed calendar view with a 24-hour timeline.

    Layout
    ──────
    ┌───────────────────────────────────────────┐
    │  سه‌شنبه ۱۵ مرداد ۱۴۰۳  [امروز]          │  ← Day header
    ├───────────────────────────────────────────┤
    │ کل‌روز:  [Event1] [Event2]                │  ← All-day area
    ├──────┬────────────────────────────────────┤
    │ ۸:۰۰ │                                    │
    │      │  ┌──────────────┐                  │
    │ ۹:۰۰ │  │ Team Standup │                  │
    │      │  └──────────────┘                  │
    │۱۰:۰۰ │  ┌──────────┐ ┌──────────────┐   │  ← Overlapping
    │      │  │ Design   │ │ Code Review  │   │
    │ ...  │  └──────────┘ └──────────────┘   │
    └──────┴────────────────────────────────────┘

    Interaction
    ───────────
    * Click empty space → deselect
    * Click event → select
    * Double-click empty space → create 1-hour event
    * Drag on empty space → create event spanning the drag
    * Drag event body → move (snap 15 min)
    * Drag event bottom handle → resize (snap 15 min)
    * All event mutations go through CalendarController
    """

    create_event_requested = Signal(object)   # datetime
    event_activated = Signal(str)             # event_id

    def __init__(self, controller: CalendarController, parent=None) -> None:
        super().__init__(parent)

        self._controller = controller
        self._day: ShamsiDate = ShamsiDate.today()
        self._day_events: DayEvents = DayEvents(date=self._day)
        self._event_widgets: dict[str, EventWidget] = {}

        # Drag-move tracking: event_id → (orig_start, orig_end, orig_x, orig_y, orig_w, orig_h)
        self._move_origins: dict[str, tuple[datetime, datetime, int, int, int, int]] = {}
        self._last_move_delta: dict[str, int] = {}

        # Drag-resize tracking: event_id → (orig_start, orig_end, orig_x, orig_y, orig_w, orig_h)
        self._resize_origins: dict[str, tuple[datetime, datetime, int, int, int, int]] = {}
        self._last_resize_delta: dict[str, int] = {}

        self._setup_ui()
        self._connect_signals()

        # Current-time line auto-refresh (every 60 s)
        self._now_timer = QTimer(self)
        self._now_timer.timeout.connect(self._on_now_tick)
        self._now_timer.start(_NOW_TIMER_MS)

        # Initial data load
        self.refresh()

        # Scroll to the current time after the widget is laid out
        QTimer.singleShot(0, self.scroll_to_current_time)

    # ── UI construction ─────────────────────────────────────────────────────

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # Header
        self._header = _DayHeader(self)
        self._header.set_day(self._day)
        layout.addWidget(self._header)

        # All-day area
        self._all_day_area = _AllDayArea(self)
        layout.addWidget(self._all_day_area)

        # Scroll area containing the time grid
        self._scroll_area = QScrollArea(self)
        self._scroll_area.setWidgetResizable(True)
        self._scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self._scroll_area.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self._scroll_area.setFrameShape(QFrame.NoFrame)
        self._scroll_area.setStyleSheet(self._scroll_area_stylesheet())

        # The 24-hour grid widget
        self._grid = _DayGridWidget(self)
        self._scroll_area.setWidget(self._grid)

        # Scroll speed
        self._scroll_area.verticalScrollBar().setSingleStep(_SCROLL_STEP)

        layout.addWidget(self._scroll_area, 1)

    @staticmethod
    def _scroll_area_stylesheet() -> str:
        return (
            f"QScrollArea {{ background: {Surface.CANVAS}; border: none; }}"
            f"QScrollBar:vertical {{"
            f"  background: transparent; width: 8px; margin: 0;"
            f"}}"
            f"QScrollBar::handle:vertical {{"
            f"  background: {Border.NORMAL}; border-radius: 4px; min-height: 30px;"
            f"}}"
            f"QScrollBar::handle:vertical:hover {{"
            f"  background: {Border.STRONG};"
            f"}}"
            f"QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{"
            f"  height: 0; background: none;"
            f"}}"
            f"QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {{"
            f"  background: none;"
            f"}}"
        )

    def _connect_signals(self) -> None:
        """Wire controller signals to this view's handlers."""
        self._controller.events_changed.connect(self._on_events_changed)
        self._controller.date_changed.connect(self._on_date_changed)
        self._controller.selection.selection_changed.connect(self._on_selection_changed)

    # ── Public API ──────────────────────────────────────────────────────────

    def set_day(self, shamsi: ShamsiDate) -> None:
        """Change the displayed day and reload all events."""
        if self._day == shamsi:
            return
        self._day = shamsi
        self._header.set_day(shamsi)
        self.refresh()

    def refresh(self) -> None:
        """Reload events from the model, recompute layout, and reposition widgets."""
        self._day_events = self._controller.model.day_events(self._day)
        self._layout_events()
        self._create_event_widgets()
        self._update_all_day_area()
        self._header.set_day(self._day)
        self._grid.update()

    def scroll_to_current_time(self) -> None:
        """Scroll the grid so the current time is visible (≈1/3 from the top)."""
        if self._day == ShamsiDate.today():
            now = datetime.now()
            minutes = now.hour * 60 + now.minute
            target_y = int(minutes * _HOUR_HEIGHT / 60)
            viewport_h = self._scroll_area.viewport().height()
            scroll_y = max(0, target_y - viewport_h // 3)
        else:
            # For non-today days, start at 8:00 AM
            scroll_y = 8 * _HOUR_HEIGHT

        self._scroll_area.verticalScrollBar().setValue(scroll_y)

    # ── Event layout ────────────────────────────────────────────────────────

    def _layout_events(self) -> None:
        """Compute collision-aware layout for timed events."""
        self._day_events.timed_layout = self._controller.model.compute_timed_layout(
            self._day_events.timed
        )

    def _create_event_widgets(self) -> None:
        """Synchronise EventWidget children with the current layout data."""
        current_ids: set[str] = set()
        selected_id = self._controller.selection.selected_event_id

        for layout_item in self._day_events.timed_layout:
            evt = layout_item.event
            current_ids.add(evt.id)
            color = self._controller.model.event_color(evt)

            if evt.id in self._event_widgets:
                # Update existing widget with fresh event data
                w = self._event_widgets[evt.id]
                w.set_event(evt)
                w.color = color
            else:
                # Create a new EventWidget
                w = EventWidget(evt, color, self._grid)
                w.clicked.connect(self._on_event_clicked)
                w.double_clicked.connect(self._on_event_double_clicked)
                w.drag_started.connect(self._on_event_drag_started)
                w.drag_moved.connect(self._on_event_drag_moved)
                w.drag_ended.connect(self._on_event_drag_ended)
                w.resize_started.connect(self._on_event_resize_started)
                w.resize_moved.connect(self._on_event_resize_moved)
                w.resize_ended.connect(self._on_event_resize_ended)
                w.toggle_complete_requested.connect(self._controller.toggle_event_completed)
                self._event_widgets[evt.id] = w
                w.show()

            # Selection state
            w.set_selected(evt.id == selected_id)

            # Position the widget according to layout data
            # Skip if the widget is currently being dragged or resized
            if not w.is_dragging():
                self._position_event_widget(w, layout_item)

        # Remove widgets for events that no longer exist on this day
        stale_ids = [eid for eid in self._event_widgets if eid not in current_ids]
        for eid in stale_ids:
            w = self._event_widgets.pop(eid)
            w.setParent(None)
            w.deleteLater()

    def _position_event_widget(self, widget: EventWidget, layout_item: EventLayout) -> None:
        """Position an EventWidget absolutely on the grid using layout data."""
        col_left = self._grid.column_left()
        col_w = self._grid.column_width()

        day_dt = self._day.to_datetime()

        # Compute minutes from midnight for start and end
        start_offset_min = (layout_item.event.start - day_dt).total_seconds() / 60.0
        end_offset_min = (layout_item.event.end - day_dt).total_seconds() / 60.0

        # Clip to 00:00–24:00 bounds
        start_offset_min = max(0.0, start_offset_min)
        end_offset_min = min(24.0 * 60, end_offset_min)

        y = int(start_offset_min * _HOUR_HEIGHT / 60)
        h = max(int((end_offset_min - start_offset_min) * _HOUR_HEIGHT / 60), _MIN_EVENT_H)

        x = col_left + int(layout_item.left * col_w) + _EVENT_PAD
        w = int(layout_item.width * col_w) - _EVENT_PAD * 2
        w = max(w, 30)

        widget.setGeometry(x, y, w, h)

    def _update_all_day_area(self) -> None:
        """Push all-day event data into the all-day area widget."""
        colors: dict[str, str] = {}
        for evt in self._day_events.all_day:
            colors[evt.id] = self._controller.model.event_color(evt)
        self._all_day_area.set_events(self._day_events.all_day, colors)

    # ── Deselect helper ─────────────────────────────────────────────────────

    def _deselect_all(self) -> None:
        """Clear the current event selection."""
        self._controller.selection.selected_event_id = None

    # ── Event click / activate ──────────────────────────────────────────────

    def _on_event_clicked(self, event_id: str) -> None:
        self._controller.selection.selected_event_id = event_id

    def _on_event_double_clicked(self, event_id: str) -> None:
        self._controller.selection.selected_event_id = event_id
        self.event_activated.emit(event_id)

    # ── Drag-to-move ────────────────────────────────────────────────────────

    def _on_event_drag_started(self, event_id: str) -> None:
        w = self._event_widgets.get(event_id)
        if w is None:
            return
        geo = w.geometry()
        self._move_origins[event_id] = (
            w.event.start, w.event.end,
            geo.x(), geo.y(), geo.width(), geo.height(),
        )
        self._last_move_delta[event_id] = 0

    def _on_event_drag_moved(self, event_id: str, delta_minutes: int) -> None:
        self._last_move_delta[event_id] = delta_minutes
        origin = self._move_origins.get(event_id)
        if origin is None:
            return
        orig_y = origin[3]
        delta_y = int(delta_minutes * _HOUR_HEIGHT / 60)

        w = self._event_widgets.get(event_id)
        if w:
            w.move(w.x(), orig_y + delta_y)

    def _on_event_drag_ended(self, event_id: str) -> None:
        delta = self._last_move_delta.pop(event_id, 0)
        origin = self._move_origins.pop(event_id, None)

        if origin is not None:
            orig_start = origin[0]
            new_start = orig_start + timedelta(minutes=delta)
            self._controller.move_event(event_id, new_start)
        else:
            self.refresh()

    # ── Drag-to-resize ──────────────────────────────────────────────────────

    def _on_event_resize_started(self, event_id: str) -> None:
        w = self._event_widgets.get(event_id)
        if w is None:
            return
        geo = w.geometry()
        self._resize_origins[event_id] = (
            w.event.start, w.event.end,
            geo.x(), geo.y(), geo.width(), geo.height(),
        )
        self._last_resize_delta[event_id] = 0

    def _on_event_resize_moved(self, event_id: str, delta_minutes: int) -> None:
        self._last_resize_delta[event_id] = delta_minutes
        origin = self._resize_origins.get(event_id)
        if origin is None:
            return
        orig_h = origin[5]
        delta_y = int(delta_minutes * _HOUR_HEIGHT / 60)
        new_h = max(orig_h + delta_y, _MIN_EVENT_H)

        w = self._event_widgets.get(event_id)
        if w:
            w.resize(w.width(), new_h)

    def _on_event_resize_ended(self, event_id: str) -> None:
        delta = self._last_resize_delta.pop(event_id, 0)
        origin = self._resize_origins.pop(event_id, None)

        if origin is not None:
            orig_end = origin[1]
            new_end = orig_end + timedelta(minutes=delta)
            self._controller.resize_event(event_id, new_end)
        else:
            self.refresh()

    # ── Controller signal handlers ──────────────────────────────────────────

    def _on_events_changed(self) -> None:
        """External mutation — reload and reposition."""
        self.refresh()

    def _on_date_changed(self) -> None:
        """Navigation date changed — update the displayed day."""
        self._day = self._controller.nav_date
        self._header.set_day(self._day)
        self.refresh()
        QTimer.singleShot(0, self.scroll_to_current_time)

    def _on_selection_changed(self) -> None:
        """Selection changed — update widget selection rings."""
        selected_id = self._controller.selection.selected_event_id
        for eid, w in self._event_widgets.items():
            w.set_selected(eid == selected_id)

    def _on_now_tick(self) -> None:
        """Periodic timer — repaint the grid to advance the now-line."""
        self._grid.update()

    # ── Widget resize ───────────────────────────────────────────────────────

    def resizeEvent(self, event) -> None:  # noqa: N802
        super().resizeEvent(event)
        # Reposition event widgets because the column width may have changed
        self._reposition_all_widgets()

    def _reposition_all_widgets(self) -> None:
        """Reposition every EventWidget using the current layout data."""
        for layout_item in self._day_events.timed_layout:
            eid = layout_item.event.id
            w = self._event_widgets.get(eid)
            if w and not w.is_dragging():
                self._position_event_widget(w, layout_item)
