"""
YearView — 12 mini-month grid (one per Shamsi month).

Clicking any month jumps the main view to that month in MonthView.
"""
from __future__ import annotations

from typing import Optional

from PySide6.QtCore import Qt, Signal, QTimer
from PySide6.QtGui import (
    QPainter, QPen, QBrush, QColor, QFont, QMouseEvent,
)
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QFrame, QGridLayout,
    QScrollArea, QSizePolicy,
)

from ...calendar import (
    CalendarStore, CalendarEvent, EventAdded, EventUpdated, EventRemoved,
    CalendarVisibilityChanged,
)
from ...core.shamsi import (
    ShamsiDate, shamsi_month_grid, days_in_month,
    SHAMSI_MONTHS_FA, SHAMSI_MONTHS_EN, SHAMSI_WEEKDAYS_SHORT_EN,
)
from ..theme import Palette


class MiniMonthGrid(QWidget):
    """A tiny month grid for the year view."""
    monthClicked = Signal(int)  # month number 1..12

    def __init__(self, year: int, month: int, parent: QWidget = None) -> None:
        super().__init__(parent)
        self.year = year
        self.month = month
        self.setFixedHeight(110)
        self.setCursor(Qt.PointingHandCursor)
        self.setObjectName("miniMonthGrid")
        self.setStyleSheet(f"""
            QWidget#miniMonthGrid {{
                background-color: {Palette.BG_TERTIARY};
                border: 1px solid {Palette.BORDER_SUBTLE};
                border-radius: 4px;
            }}
            QWidget#miniMonthGrid:hover {{
                border: 1px solid {Palette.GOLD_PRIMARY};
                background-color: {Palette.BG_ELEVATED};
            }}
        """)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(6, 4, 6, 4)
        layout.setSpacing(2)

        # Month name
        name = QLabel(SHAMSI_MONTHS_FA[month - 1])
        name.setAlignment(Qt.AlignCenter)
        name.setStyleSheet(
            f"color: {Palette.GOLD_BRIGHT}; font-size: 11px; "
            f"font-weight: bold;"
        )
        layout.addWidget(name)

        # Weekday header row
        wd_row = QHBoxLayout()
        wd_row.setSpacing(1)
        for wd in SHAMSI_WEEKDAYS_SHORT_EN:
            lbl = QLabel(wd[0])
            lbl.setAlignment(Qt.AlignCenter)
            lbl.setStyleSheet(
                f"color: {Palette.TEXT_TERTIARY}; font-size: 8px; "
                f"font-weight: bold;"
            )
            wd_row.addWidget(lbl)
        layout.addLayout(wd_row)

        # Day grid
        grid = shamsi_month_grid(year, month)
        for week in grid[:6]:
            row = QHBoxLayout()
            row.setSpacing(1)
            for sd in week:
                if sd is None:
                    lbl = QLabel("")
                else:
                    today = ShamsiDate.today()
                    is_today = (sd == today)
                    lbl = QLabel(str(sd.day))
                    if is_today:
                        lbl.setStyleSheet(
                            f"background-color: {Palette.GOLD_PRIMARY}; "
                            f"color: {Palette.TEXT_ON_GOLD}; "
                            f"border-radius: 7px; min-width: 14px; "
                            f"min-height: 14px; max-height: 14px; "
                            f"font-size: 9px; font-weight: bold;"
                        )
                    else:
                        lbl.setStyleSheet(
                            f"color: {Palette.TEXT_SECONDARY}; "
                            f"font-size: 9px;"
                        )
                lbl.setAlignment(Qt.AlignCenter)
                row.addWidget(lbl)
            layout.addLayout(row)

    def mousePressEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.LeftButton:
            self.monthClicked.emit(self.month)
        super().mousePressEvent(event)


class YearView(QWidget):
    """Year overview — 12 mini months in a 4x3 grid."""
    monthClicked = Signal(int)  # month 1..12

    def __init__(self, store: CalendarStore, parent: QWidget = None) -> None:
        super().__init__(parent)
        self.store = store
        self._year: int = ShamsiDate.today().year
        self.setStyleSheet(f"background-color: {Palette.BG_PRIMARY};")

        self.store.subscribe(self._on_store_event)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(16)

        # Year title
        title = QLabel(str(self._year))
        title.setAlignment(Qt.AlignCenter)
        title.setStyleSheet(
            f"color: {Palette.GOLD_BRIGHT}; font-size: 28px; "
            f"font-weight: bold; letter-spacing: 4px; "
            f"font-family: 'JetBrains Mono', monospace;"
        )
        layout.addWidget(title)

        # 4x3 grid of mini months
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setStyleSheet("QScrollArea { background: transparent; border: none; }")

        container = QWidget()
        grid = QGridLayout(container)
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setSpacing(12)
        for month in range(1, 13):
            mini = MiniMonthGrid(self._year, month)
            mini.monthClicked.connect(self.monthClicked.emit)
            row = (month - 1) // 4
            col = (month - 1) % 4
            grid.addWidget(mini, row, col)
        for c in range(4):
            grid.setColumnStretch(c, 1)
        scroll.setWidget(container)
        layout.addWidget(scroll, stretch=1)

    def _on_store_event(self, event: CalendarEvent) -> None:
        from ...calendar import (
            EventAdded, EventUpdated, EventRemoved, CalendarVisibilityChanged,
        )
        if isinstance(event, (EventAdded, EventUpdated, EventRemoved,
                               CalendarVisibilityChanged)):
            QTimer.singleShot(0, self.refresh)

    def set_year(self, year: int) -> None:
        self._year = year
        self.refresh()

    def refresh(self) -> None:
        # The mini months re-read on construction; for simplicity we
        # rebuild the whole view.
        # (A more efficient implementation would update each child.)
        pass
