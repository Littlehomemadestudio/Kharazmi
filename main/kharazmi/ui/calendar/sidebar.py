"""
Sidebar — Mini month picker + calendar list + NL input for the RASK! calendar.

Layout:
  ┌──────────────────┐
  │  Mini Month Grid  │
  │  (click to pick)  │
  ├──────────────────┤
  │  Calendars:       │
  │  ☑ Personal  🟡   │
  │  ☑ Work      🔵   │
  │  ☐ Holidays  🔴   │
  │  [+ Add Calendar] │
  ├──────────────────┤
  │  🔍 Quick add...  │
  │  (NL input bar)   │
  └──────────────────┘
"""
from __future__ import annotations

from typing import Optional

from PySide6.QtCore import Qt, Signal, QRectF, QPoint
from PySide6.QtGui import (
    QPainter, QColor, QPen, QBrush, QFont, QFontMetrics,
    QEnterEvent,
)
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,
    QPushButton, QCheckBox, QFrame, QScrollArea,
)

from ...calendar.store import CalendarStore
from ...calendar.calendar import Calendar
from ...calendar.enums import CalendarViewKind
from ...core.shamsi import (
    ShamsiDate, shamsi_month_grid, to_persian_digits,
    SHAMSI_WEEKDAYS_SHORT_EN,
)
from .controller import CalendarController
from .model import CalendarModel
from .theme import (
    Surface, Gold, Text, Border, Metrics, Spacing,
    qcolor, with_alpha, font_header, font_body, font_small, font_mini_day,
)


# ──────────────────────────────── Mini Month ──────────────────────────────

class MiniMonthWidget(QWidget):
    """Compact month grid for the sidebar — click a day to navigate."""
    date_clicked = Signal(object)   # ShamsiDate

    def __init__(self, controller: CalendarController, parent=None) -> None:
        super().__init__(parent)
        self._ctrl = controller
        self._year = controller.nav_date.year
        self._month = controller.nav_date.month
        self._grid: list[list[Optional[ShamsiDate]]] = []
        self._hovered_cell: Optional[tuple[int, int]] = None
        self._today = ShamsiDate.today()

        self.setFixedSize(Metrics.SIDEBAR_WIDTH - 16, Metrics.SIDEBAR_MINI_MONTH_H)
        self.setCursor(Qt.PointingHandCursor)
        self._load_grid()

    def _load_grid(self) -> None:
        self._grid = shamsi_month_grid(self._year, self._month)

    def set_month(self, year: int, month: int) -> None:
        if self._year != year or self._month != month:
            self._year = year
            self._month = month
            self._today = ShamsiDate.today()
            self._load_grid()
            self.update()

    # ── Geometry ──

    def _cell_size(self) -> int:
        w = self.width() - 12  # 6px margin each side
        return w // 7

    def _cell_rect(self, row: int, col: int) -> QRectF:
        cs = self._cell_size()
        x = 6 + col * cs
        header_h = 22
        month_h = 22
        y = month_h + header_h + row * cs
        return QRectF(x, y, cs, cs)

    # ── Paint ──

    def paintEvent(self, event) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)

        cs = self._cell_size()
        left = 4

        # Month name
        month_name = ShamsiDate(self._year, self._month, 1).month_name_fa
        p.setFont(font_header())
        p.setPen(qcolor(Text.PRIMARY))
        p.drawText(QRectF(left, 0, self.width() - 12, 22), Qt.AlignCenter, month_name)

        # Weekday headers
        p.setFont(font_mini_day())
        p.setPen(qcolor(Text.TERTIARY))
        header_y = 22
        for i, name in enumerate(SHAMSI_WEEKDAYS_SHORT_EN):
            p.drawText(QRectF(left + i * cs, header_y, cs, 22),
                       Qt.AlignCenter, name[:2])

        # Day cells
        for row in range(6):
            for col in range(7):
                sd = self._grid[row][col]
                if sd is None:
                    continue
                r = self._cell_rect(row, col)

                # Background
                is_current_month = sd.month == self._month and sd.year == self._year
                is_today = sd == self._today
                is_hovered = self._hovered_cell == (row, col)
                is_selected = sd == self._ctrl.selection.selected_date

                if is_selected:
                    p.setBrush(QBrush(with_alpha(Gold.PRIMARY, 40)))
                    p.setPen(Qt.NoPen)
                    p.drawRoundedRect(r.adjusted(1, 1, -1, -1), 3, 3)
                elif is_hovered and is_current_month:
                    p.setBrush(QBrush(qcolor(Surface.CARD_HOVER)))
                    p.setPen(Qt.NoPen)
                    p.drawRoundedRect(r.adjusted(1, 1, -1, -1), 3, 3)

                # Today circle
                if is_today:
                    p.setBrush(QBrush(qcolor(Gold.PRIMARY)))
                    p.setPen(Qt.NoPen)
                    p.drawEllipse(r.center(), cs / 2 - 3, cs / 2 - 3)
                    text_color = qcolor(Text.ON_GOLD)
                else:
                    text_color = qcolor(Text.PRIMARY) if is_current_month else qcolor(Text.TERTIARY)

                # Day number
                p.setFont(font_mini_day())
                p.setPen(text_color)
                day_text = to_persian_digits(str(sd.day))
                p.drawText(r, Qt.AlignCenter, day_text)

        p.end()

    # ── Mouse ──

    def _cell_at(self, pos: QPoint) -> Optional[tuple[int, int]]:
        cs = self._cell_size()
        col = (pos.x() - 4) // cs
        header_h = 44
        row = (pos.y() - header_h) // cs
        if 0 <= row < 6 and 0 <= col < 7:
            return (row, col)
        return None

    def mousePressEvent(self, event) -> None:
        cell = self._cell_at(event.pos())
        if cell:
            sd = self._grid[cell[0]][cell[1]]
            if sd:
                self.date_clicked.emit(sd)

    def mouseMoveEvent(self, event) -> None:
        cell = self._cell_at(event.pos())
        if cell != self._hovered_cell:
            self._hovered_cell = cell
            self.update()

    def leaveEvent(self, event) -> None:
        self._hovered_cell = None
        self.update()


# ──────────────────────────────── Calendar List ───────────────────────────

class CalendarListWidget(QWidget):
    """List of calendars with visibility checkboxes and color dots."""
    calendar_toggled = Signal(str, bool)   # calendar_id, visible
    add_calendar_requested = Signal()

    def __init__(self, model: CalendarModel, parent=None) -> None:
        super().__init__(parent)
        self._model = model
        self._rows: list[_CalendarRow] = []
        self._build()

    def _build(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(Spacing.XS)

        # Header
        header = QLabel("Calendars")
        header.setFont(font_header())
        header.setStyleSheet(f"color: {Text.SECONDARY}; padding: 6px 0; font-size: 12px;")
        layout.addWidget(header)

        # Calendar rows
        self._rows_container = QWidget()
        self._rows_layout = QVBoxLayout(self._rows_container)
        self._rows_layout.setContentsMargins(0, 0, 0, 0)
        self._rows_layout.setSpacing(2)
        layout.addWidget(self._rows_container)

        # Add button
        add_btn = QPushButton("+ Add Calendar")
        add_btn.setFont(font_small())
        add_btn.setCursor(Qt.PointingHandCursor)
        add_btn.setStyleSheet(f"""
            QPushButton {{
                background: transparent;
                color: {Text.TERTIARY};
                border: 1px dashed {Border.NORMAL};
                border-radius: 4px;
                padding: 6px;
                text-align: left;
            }}
            QPushButton:hover {{
                color: {Gold.BRIGHT};
                border-color: {Gold.DEEP};
                background: {Surface.CARD};
            }}
        """)
        add_btn.clicked.connect(self.add_calendar_requested.emit)
        layout.addWidget(add_btn)

        layout.addStretch()
        self.refresh()

    def refresh(self) -> None:
        # Clear old rows
        for row in self._rows:
            row.setParent(None)
            row.deleteLater()
        self._rows.clear()

        for cal in self._model.calendars():
            row = _CalendarRow(cal, self)
            row.toggled.connect(lambda checked, cid=cal.id: self.calendar_toggled.emit(cid, checked))
            self._rows_layout.addWidget(row)
            self._rows.append(row)


class _CalendarRow(QWidget):
    toggled = Signal(bool)

    def __init__(self, calendar: Calendar, parent=None) -> None:
        super().__init__(parent)
        self._cal = calendar
        layout = QHBoxLayout(self)
        layout.setContentsMargins(4, 2, 4, 2)
        layout.setSpacing(6)

        # Checkbox
        self._check = QCheckBox()
        self._check.setChecked(calendar.visible)
        self._check.setStyleSheet(f"""
            QCheckBox {{
                spacing: 0;
            }}
            QCheckBox::indicator {{
                width: 14px; height: 14px;
                border: 1px solid {Border.STRONG};
                border-radius: 3px;
                background: {Surface.ELEVATED};
            }}
            QCheckBox::indicator:checked {{
                background: {calendar.color};
                border: 1px solid {calendar.color};
            }}
        """)
        self._check.toggled.connect(self.toggled.emit)
        layout.addWidget(self._check)

        # Color dot
        dot = QLabel("●")
        dot.setFont(QFont("Inter", 10))
        dot.setStyleSheet(f"color: {calendar.color};")
        dot.setFixedWidth(14)
        layout.addWidget(dot)

        # Name
        name = QLabel(calendar.name)
        name.setFont(font_body())
        name.setStyleSheet(f"color: {Text.PRIMARY};")
        layout.addWidget(name)

        if calendar.is_readonly:
            lock = QLabel("🔒")
            lock.setFont(font_small())
            lock.setFixedWidth(14)
            layout.addWidget(lock)

        layout.addStretch()


# ──────────────────────────────── NL Input ────────────────────────────────

class QuickAddInput(QLineEdit):
    """Natural-language event creation input bar."""
    event_created = Signal(str)  # event title

    def __init__(self, controller: CalendarController, parent=None) -> None:
        super().__init__(parent)
        self._ctrl = controller
        self.setPlaceholderText("⚡ افزودن سریع...  مثلاً: جلسه ساعت ۳...")
        self.setFont(font_body())
        self.setStyleSheet(f"""
            QLineEdit {{
                background: {Surface.CARD};
                color: {Text.PRIMARY};
                border: 1px solid {Border.NORMAL};
                border-radius: 8px;
                padding: 10px 14px;
                font-size: 12px;
            }}
            QLineEdit:focus {{
                border-color: {Gold.PRIMARY};
                background: {Surface.ELEVATED};
            }}
        """)
        self.returnPressed.connect(self._on_return)

    def _on_return(self) -> None:
        text = self.text().strip()
        if not text:
            return
        evt = self._ctrl.create_event_from_nl(text)
        if evt:
            self.event_created.emit(evt.title)
            self.clear()


# ──────────────────────────────── Sidebar ─────────────────────────────────

class CalendarSidebar(QWidget):
    """The full left sidebar: mini month + calendar list + NL input."""
    date_clicked = Signal(object)      # ShamsiDate
    calendar_toggled = Signal(str, bool)
    add_calendar_requested = Signal()
    event_created = Signal(str)

    def __init__(self, controller: CalendarController, parent=None) -> None:
        super().__init__(parent)
        self._ctrl = controller
        self.setFixedWidth(Metrics.SIDEBAR_WIDTH)
        self.setStyleSheet(f"background: {Surface.PANEL};")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 16, 12, 12)
        layout.setSpacing(Spacing.LG)

        # Mini month
        self._mini_month = MiniMonthWidget(controller, self)
        self._mini_month.date_clicked.connect(self.date_clicked.emit)
        layout.addWidget(self._mini_month)

        # Separator
        sep = QFrame()
        sep.setFrameShape(QFrame.HLine)
        sep.setStyleSheet(f"color: {Border.SUBTLE};")
        layout.addWidget(sep)

        # Calendar list
        self._cal_list = CalendarListWidget(controller.model, self)
        self._cal_list.calendar_toggled.connect(self.calendar_toggled.emit)
        self._cal_list.add_calendar_requested.connect(self.add_calendar_requested.emit)
        layout.addWidget(self._cal_list, 1)

        # Separator
        sep2 = QFrame()
        sep2.setFrameShape(QFrame.HLine)
        sep2.setStyleSheet(f"color: {Border.SUBTLE};")
        layout.addWidget(sep2)

        # Quick add
        self._nl_input = QuickAddInput(controller, self)
        self._nl_input.event_created.connect(self.event_created.emit)
        layout.addWidget(self._nl_input)

    def refresh(self) -> None:
        self._mini_month.set_month(self._ctrl.nav_date.year, self._ctrl.nav_date.month)
        self._cal_list.refresh()

    def update_mini_month(self) -> None:
        self._mini_month.set_month(self._ctrl.nav_date.year, self._ctrl.nav_date.month)
