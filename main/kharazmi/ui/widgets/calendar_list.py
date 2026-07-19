"""
CalendarListWidget — sidebar list of calendars with visibility toggles.

Each row shows:
  [checkbox]  [color swatch]  Calendar name            (event count)

Clicking the checkbox toggles visibility. Double-clicking the name
opens the calendar settings dialog.
"""
from __future__ import annotations

from typing import Optional

from PySide6.QtCore import Qt, Signal, QSize
from PySide6.QtGui import (
    QPainter, QPen, QBrush, QColor, QFont, QMouseEvent, QPaintEvent, QAction,
)
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QCheckBox, QFrame,
    QPushButton, QToolButton, QScrollArea, QSizePolicy, QMenu,
    QInputDialog, QMessageBox, QColorDialog,
)

from ...calendar import (
    CalendarStore, Calendar, CALENDAR_COLORS,
    CalendarAdded, CalendarRemoved, CalendarUpdated,
    CalendarVisibilityChanged,
)
from ..theme import Palette


class CalendarRow(QWidget):
    """A single calendar row in the list."""
    visibilityToggled = Signal(str, bool)
    calendarActivated = Signal(str)  # double-click → edit

    def __init__(self, calendar: Calendar, event_count: int = 0,
                 parent: QWidget = None) -> None:
        super().__init__(parent)
        self.calendar = calendar
        self.event_count = event_count

        self.setFixedHeight(32)
        self.setCursor(Qt.PointingHandCursor)
        self.setObjectName("calRow")
        self._apply_style()

        layout = QHBoxLayout(self)
        layout.setContentsMargins(8, 0, 8, 0)
        layout.setSpacing(8)

        # Visibility checkbox
        self._checkbox = QCheckBox()
        self._checkbox.setChecked(calendar.visible)
        self._checkbox.setStyleSheet(
            f"QCheckBox::indicator {{ width: 14px; height: 14px; "
            f"border: 1px solid {Palette.BORDER_STRONG}; "
            f"background: {Palette.BG_DEEPEST}; border-radius: 2px; }}"
            f"QCheckBox::indicator:checked {{ background: {calendar.color}; "
            f"border: 1px solid {calendar.color}; }}"
        )
        self._checkbox.toggled.connect(
            lambda checked: self.visibilityToggled.emit(calendar.id, checked)
        )
        layout.addWidget(self._checkbox)

        # Color swatch
        swatch = QFrame()
        swatch.setFixedSize(10, 10)
        swatch.setStyleSheet(
            f"background-color: {calendar.color}; border-radius: 5px;"
        )
        layout.addWidget(swatch)

        # Name
        name = QLabel(calendar.name)
        name.setStyleSheet(
            f"color: {Palette.TEXT_PRIMARY}; font-size: 12px; "
            f"font-weight: {'bold' if calendar.is_default else 'normal'};"
        )
        layout.addWidget(name, stretch=1)

        # Readonly badge
        if calendar.is_readonly:
            ro = QLabel("⊘")
            ro.setStyleSheet(
                f"color: {Palette.TEXT_TERTIARY}; font-size: 11px;"
            )
            ro.setToolTip("Read-only calendar")
            layout.addWidget(ro)

        # Event count
        count = QLabel(str(event_count))
        count.setStyleSheet(
            f"color: {Palette.TEXT_TERTIARY}; font-size: 10px; "
            f"font-family: 'JetBrains Mono', monospace; "
            f"background-color: {Palette.BG_DEEPEST}; padding: 1px 6px; "
            f"border-radius: 7px;"
        )
        layout.addWidget(count)

    def _apply_style(self) -> None:
        self.setStyleSheet(
            f"QWidget#calRow {{ background: transparent; border: none; }}"
            f"QWidget#calRow:hover {{ background-color: {Palette.BG_HOVER}; }}"
        )

    def mouseDoubleClickEvent(self, event) -> None:
        if event.button() == Qt.LeftButton and not self.calendar.is_readonly:
            self.calendarActivated.emit(self.calendar.id)
        super().mouseDoubleClickEvent(event)


class CalendarListWidget(QWidget):
    """Sidebar widget listing all calendars."""

    calendarVisibilityChanged = Signal(str, bool)
    calendarEditRequested = Signal(str)
    createCalendarRequested = Signal()

    def __init__(self, store: CalendarStore, parent: QWidget = None) -> None:
        super().__init__(parent)
        self.store = store

        self.setObjectName("calList")
        self.setStyleSheet(f"""
            QWidget#calList {{
                background-color: {Palette.BG_TERTIARY};
                border: 1px solid {Palette.BORDER_SUBTLE};
                border-radius: 6px;
            }}
        """)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # Header
        header = QWidget()
        header.setFixedHeight(28)
        header_layout = QHBoxLayout(header)
        header_layout.setContentsMargins(10, 0, 10, 0)
        title = QLabel("MY CALENDARS")
        title.setStyleSheet(
            f"color: {Palette.TEXT_TERTIARY}; font-size: 10px; "
            f"font-weight: bold; letter-spacing: 1.5px;"
        )
        header_layout.addWidget(title)
        header_layout.addStretch()

        # Add button
        add_btn = QToolButton()
        add_btn.setText("+")
        add_btn.setFixedSize(18, 18)
        add_btn.setStyleSheet(
            f"QToolButton {{ background: transparent; color: {Palette.GOLD_BRIGHT}; "
            f"border: none; font-size: 14px; font-weight: bold; }}"
            f"QToolButton:hover {{ color: {Palette.GOLD_PRIMARY}; }}"
        )
        add_btn.setToolTip("Add a new calendar")
        add_btn.clicked.connect(self.createCalendarRequested.emit)
        header_layout.addWidget(add_btn)
        layout.addWidget(header)

        # Scrollable list
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setStyleSheet("QScrollArea { background: transparent; border: none; }")

        container = QWidget()
        self._list_layout = QVBoxLayout(container)
        self._list_layout.setContentsMargins(4, 4, 4, 4)
        self._list_layout.setSpacing(0)
        self._list_layout.addStretch()
        scroll.setWidget(container)
        layout.addWidget(scroll, stretch=1)

        # Subscribe to store events
        self.store.subscribe(self._on_store_event)

        self.refresh()

    def _on_store_event(self, event) -> None:
        # Refresh on any calendar change
        from ...calendar import (
            CalendarAdded, CalendarRemoved, CalendarUpdated,
            CalendarVisibilityChanged, EventAdded, EventUpdated, EventRemoved,
        )
        if isinstance(event, (CalendarAdded, CalendarRemoved, CalendarUpdated,
                               CalendarVisibilityChanged, EventAdded, EventUpdated,
                               EventRemoved)):
            self.refresh()

    def refresh(self) -> None:
        # Clear (preserving the stretch)
        while self._list_layout.count() > 1:
            item = self._list_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        # Count events per calendar
        counts: dict[str, int] = {}
        for evt in self.store.events():
            counts[evt.calendar_id] = counts.get(evt.calendar_id, 0) + 1

        # Add rows
        for cal in sorted(self.store.calendars(), key=lambda c: (not c.is_default, c.name.lower())):
            row = CalendarRow(cal, counts.get(cal.id, 0))
            row.visibilityToggled.connect(self._on_visibility_toggled)
            row.calendarActivated.connect(self.calendarEditRequested.emit)
            self._list_layout.insertWidget(self._list_layout.count() - 1, row)

    def _on_visibility_toggled(self, cal_id: str, visible: bool) -> None:
        self.store.set_calendar_visible(cal_id, visible)
        self.calendarVisibilityChanged.emit(cal_id, visible)
