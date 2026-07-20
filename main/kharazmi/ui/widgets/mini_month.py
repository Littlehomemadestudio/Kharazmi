"""
MiniMonthWidget — small month grid shown in the sidebar.

Clicking a day jumps the main view to that date. The current
selection is highlighted in gold.
"""
from __future__ import annotations

from typing import Optional

from PySide6.QtCore import Qt, Signal, QPoint, QSize
from PySide6.QtGui import (
    QPainter, QPen, QBrush, QColor, QFont, QFontMetrics,
)
from PySide6.QtWidgets import (
    QWidget, QGridLayout, QLabel, QFrame, QHBoxLayout, QPushButton,
    QToolButton, QSizePolicy,
)

from ...core.shamsi import (
    ShamsiDate, shamsi_month_grid, days_in_month,
    SHAMSI_MONTHS_FA, SHAMSI_MONTHS_EN, SHAMSI_WEEKDAYS_SHORT_EN,
)
from ..theme import Palette


class MiniDayCell(QLabel):
    """A single day cell in the mini month."""
    clicked = Signal(object)  # ShamsiDate

    def __init__(self, date: Optional[ShamsiDate], is_today: bool = False,
                 is_selected: bool = False, in_month: bool = True,
                 has_events: bool = False, parent: QWidget = None) -> None:
        super().__init__(parent)
        self.date = date
        self._is_today = is_today
        self._is_selected = is_selected
        self._in_month = in_month
        self._has_events = has_events
        self.setAlignment(Qt.AlignCenter)
        self.setFixedSize(28, 24)
        self.setCursor(Qt.PointingHandCursor if date else Qt.ArrowCursor)
        self.setText(str(date.day) if date else "")
        self._apply_style()

    def _apply_style(self) -> None:
        if self.date is None:
            self.setStyleSheet("background: transparent;")
            return
        if self._is_today:
            bg = Palette.GOLD_PRIMARY
            fg = Palette.TEXT_ON_GOLD
            border = Palette.GOLD_BRIGHT
        elif self._is_selected:
            bg = Palette.BG_SELECTED
            fg = Palette.GOLD_BRIGHT
            border = Palette.GOLD_PRIMARY
        elif self._in_month:
            bg = "transparent"
            fg = Palette.TEXT_PRIMARY if self._has_events else Palette.TEXT_SECONDARY
            border = "transparent"
        else:
            bg = "transparent"
            fg = Palette.TEXT_TERTIARY
            border = "transparent"
        self.setStyleSheet(
            f"background-color: {bg}; color: {fg}; "
            f"border: 1px solid {border}; border-radius: 3px; "
            f"font-size: 11px; font-weight: {'bold' if self._has_events else 'normal'};"
        )

    def set_selected(self, selected: bool) -> None:
        self._is_selected = selected
        self._apply_style()

    def set_has_events(self, has_events: bool) -> None:
        self._has_events = has_events
        self._apply_style()

    def mousePressEvent(self, event) -> None:
        if self.date is not None and event.button() == Qt.LeftButton:
            self.clicked.emit(self.date)
        super().mousePressEvent(event)


class MiniMonthWidget(QWidget):
    """A compact month picker for the sidebar."""

    dateSelected = Signal(object)  # ShamsiDate
    monthChanged = Signal(object)  # ShamsiDate (first of month)

    def __init__(self, parent: QWidget = None) -> None:
        super().__init__(parent)
        self._current: ShamsiDate = ShamsiDate.today()
        self._selected: ShamsiDate = ShamsiDate.today()
        self._dates_with_events: set[str] = set()  # "yyyy-mm-dd" strings

        self.setObjectName("miniMonth")
        self.setStyleSheet(f"""
            QWidget#miniMonth {{
                background-color: {Palette.BG_TERTIARY};
                border: 1px solid {Palette.BORDER_SUBTLE};
                border-radius: 6px;
            }}
        """)

        layout = QGridLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(2)

        # Header row: ‹  Month Year  ›
        header = QHBoxLayout()
        header.setSpacing(4)

        self._prev_btn = QToolButton()
        self._prev_btn.setText("‹")
        self._prev_btn.setFixedSize(20, 20)
        self._prev_btn.setStyleSheet(self._nav_style())
        self._prev_btn.clicked.connect(lambda: self._navigate_month(-1))
        header.addWidget(self._prev_btn)

        self._title = QLabel("")
        self._title.setAlignment(Qt.AlignCenter)
        self._title.setStyleSheet(
            f"color: {Palette.GOLD_BRIGHT}; font-size: 11px; font-weight: bold; "
            f"font-family: 'JetBrains Mono', monospace;"
        )
        header.addWidget(self._title, stretch=1)

        self._next_btn = QToolButton()
        self._next_btn.setText("›")
        self._next_btn.setFixedSize(20, 20)
        self._next_btn.setStyleSheet(self._nav_style())
        self._next_btn.clicked.connect(lambda: self._navigate_month(1))
        header.addWidget(self._next_btn)

        layout.addLayout(header, 0, 0, 1, 7)

        # Weekday header row
        for col, wd in enumerate(SHAMSI_WEEKDAYS_SHORT_EN):
            lbl = QLabel(wd[0])
            lbl.setAlignment(Qt.AlignCenter)
            lbl.setStyleSheet(
                f"color: {Palette.TEXT_TERTIARY}; font-size: 9px; "
                f"font-weight: bold; padding: 2px;"
            )
            layout.addWidget(lbl, 1, col)

        # 6 rows of day cells (initialized empty)
        self._cells: list[MiniDayCell] = []
        for row in range(6):
            for col in range(7):
                cell = MiniDayCell(None)
                cell.clicked.connect(self._on_day_clicked)
                self._cells.append(cell)
                layout.addWidget(cell, row + 2, col)

        self._refresh()

    def _nav_style(self) -> str:
        return f"""
            QToolButton {{
                background-color: transparent;
                color: {Palette.GOLD_PRIMARY};
                border: none;
                font-size: 14px;
                font-weight: bold;
            }}
            QToolButton:hover {{
                color: {Palette.GOLD_BRIGHT};
            }}
        """

    def _navigate_month(self, delta: int) -> None:
        self._current = self._current.add_months(delta)
        self._refresh()
        self.monthChanged.emit(ShamsiDate(self._current.year, self._current.month, 1))

    def _on_day_clicked(self, sd: ShamsiDate) -> None:
        self._selected = sd
        # If clicked on a date outside the current month, navigate to it
        if sd.year != self._current.year or sd.month != self._current.month:
            self._current = ShamsiDate(sd.year, sd.month, 1)
        self._refresh()
        self.dateSelected.emit(sd)

    def set_selected(self, sd: ShamsiDate) -> None:
        self._selected = sd
        self._current = ShamsiDate(sd.year, sd.month, 1)
        self._refresh()

    def set_dates_with_events(self, dates: set[ShamsiDate]) -> None:
        self._dates_with_events = {f"{d.year}-{d.month:02d}-{d.day:02d}" for d in dates}
        self._refresh()

    def _refresh(self) -> None:
        self._title.setText(f"{SHAMSI_MONTHS_FA[self._current.month - 1]}  {self._current.year}")
        today = ShamsiDate.today()
        grid = shamsi_month_grid(self._current.year, self._current.month)

        # Also compute overflow dates from prev/next month
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
                        # Previous month overflow
                        first_real = next((d for d in week if d is not None), None)
                        if first_real is not None:
                            offset = (first_real.day - 1) - col
                            if offset >= 0 and offset < prev_last_day:
                                sd = ShamsiDate(prev_month.year, prev_month.month,
                                                prev_last_day - offset)
                                in_month = False
                            else:
                                cell.date = None
                                cell.setText("")
                                cell._apply_style()
                                continue
                        else:
                            cell.date = None
                            cell.setText("")
                            cell._apply_style()
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
                            cell.setText("")
                            cell._apply_style()
                            continue
                else:
                    in_month = True

                is_today = (sd == today)
                is_selected = (sd == self._selected)
                date_key = f"{sd.year}-{sd.month:02d}-{sd.day:02d}"
                has_events = date_key in self._dates_with_events

                cell.date = sd
                cell._is_today = is_today
                cell._is_selected = is_selected
                cell._in_month = in_month
                cell._has_events = has_events
                cell.setText(str(sd.day))
                cell._apply_style()
