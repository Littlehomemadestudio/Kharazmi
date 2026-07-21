"""
CalendarView — Main calendar container for the RASK! calendar.

Layout (mirrors Google Calendar's desktop UI):

  ┌──────────────────────────────────────────────────────────────────┐
  │ Toolbar: ☰ | Today | ‹ › | [Month Title] | Day|Week|Month|Year │
  ├──────────────┬───────────────────────────────────────────────────┤
  │  Sidebar     │                                                   │
  │  ┌─────────┐ │                                                   │
  │  │ Mini    │ │           Main view area                          │
  │  │ Month   │ │    (MonthView / WeekView / DayView / YearView)   │
  │  └─────────┘ │                                                   │
  │              │                                                   │
  │  Calendars:  │                                                   │
  │  ☑ Personal  │                                                   │
  │  ☑ Work      │                                                   │
  │  ☐ Holidays  │                                                   │
  │              │                                                   │
  │  ⚡Quick add │                                                   │
  └──────────────┴───────────────────────────────────────────────────┘

Keyboard shortcuts (Google Calendar style):
  c / n    → create event
  t        → today
  d        → day view
  w        → week view
  m        → month view
  y        → year view
  + / -    → next/prev
  /        → focus quick add
"""
from __future__ import annotations

from datetime import datetime, timedelta
from typing import Optional

from PySide6.QtCore import Qt, Signal, QTimer, QSize
from PySide6.QtGui import (
    QAction, QKeySequence, QShortcut, QIcon, QPixmap, QPainter,
    QColor, QBrush, QFont, QPen,
)
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QSplitter, QFrame,
    QPushButton, QToolButton, QLabel, QStackedWidget,
    QSizePolicy, QMenu,
)

from ...calendar.store import CalendarStore
from ...calendar.event import Event
from ...calendar.enums import CalendarViewKind
from ...calendar.natural_language import parse as nl_parse
from ...core.shamsi import ShamsiDate, format_shamsi, to_persian_digits
from ..theme import Palette
from ..dialogs import EventEditorDialog, CalendarSettingsDialog
from .controller import CalendarController
from .model import CalendarModel
from .sidebar import CalendarSidebar
from .month_view import MonthView
from .week_view import WeekView
from .day_view import DayView
from .year_view import YearView
from .theme import Surface, Gold, Text, Border, Metrics, font_header, font_body
from .animation import HoverGlow


# ──────────────────────────────── View Button ─────────────────────────────

class _ViewButton(QPushButton):
    """Styled toggle button for view switching."""

    def __init__(self, label: str, parent=None) -> None:
        super().__init__(label, parent)
        self.setCheckable(True)
        self.setFont(font_body())
        self.setCursor(Qt.PointingHandCursor)
        self._hover_glow = HoverGlow(self)
        self._apply_style(False)

    def set_checked(self, checked: bool) -> None:
        self.setChecked(checked)
        self._apply_style(checked)

    def _apply_style(self, checked: bool) -> None:
        if checked:
            self.setStyleSheet(f"""
                QPushButton {{
                    background: {Gold.MUTED};
                    color: {Gold.BRIGHT};
                    border: 1px solid {Gold.DEEP};
                    border-radius: 6px;
                    padding: 6px 16px;
                    font-weight: 600;
                    font-size: 12px;
                }}
            """)
        else:
            self.setStyleSheet(f"""
                QPushButton {{
                    background: transparent;
                    color: {Text.SECONDARY};
                    border: 1px solid transparent;
                    border-radius: 6px;
                    padding: 6px 16px;
                    font-size: 12px;
                }}
                QPushButton:hover {{
                    background: {Surface.CARD};
                    color: {Text.PRIMARY};
                    border-color: {Border.NORMAL};
                }}
            """)

    def enterEvent(self, event) -> None:
        self._hover_glow.enter()
        super().enterEvent(event)

    def leaveEvent(self, event) -> None:
        self._hover_glow.leave()
        super().leaveEvent(event)


# ──────────────────────────────── Toolbar ─────────────────────────────────

class _CalendarToolbar(QWidget):
    """Top toolbar with navigation and view switching."""
    today_clicked = Signal()
    prev_clicked = Signal()
    next_clicked = Signal()
    view_change_requested = Signal(str)
    new_event_clicked = Signal()

    def __init__(self, controller: CalendarController, parent=None) -> None:
        super().__init__(parent)
        self._ctrl = controller
        self.setFixedHeight(Metrics.TOOLBAR_HEIGHT)
        self.setStyleSheet(f"background: {Surface.PANEL};")

        layout = QHBoxLayout(self)
        layout.setContentsMargins(12, 6, 12, 6)
        layout.setSpacing(8)

        # New event button
        new_btn = QPushButton("+ رویداد جدید")
        new_btn.setFont(font_body())
        new_btn.setCursor(Qt.PointingHandCursor)
        new_btn.setStyleSheet(f"""
            QPushButton {{
                background: {Gold.PRIMARY};
                color: {Text.ON_GOLD};
                border: 1px solid {Gold.DEEP};
                border-radius: 8px;
                padding: 8px 20px;
                font-weight: 600;
                font-size: 13px;
            }}
            QPushButton:hover {{
                background: {Gold.BRIGHT};
            }}
            QPushButton:pressed {{
                background: {Gold.DEEP};
            }}
        """)
        new_btn.clicked.connect(self.new_event_clicked.emit)
        layout.addWidget(new_btn)

        # Today button
        today_btn = QPushButton("امروز")
        today_btn.setFont(font_body())
        today_btn.setCursor(Qt.PointingHandCursor)
        today_btn.setStyleSheet(f"""
            QPushButton {{
                background: {Surface.CARD};
                color: {Text.PRIMARY};
                border: 1px solid {Border.NORMAL};
                border-radius: 6px;
                padding: 7px 18px;
                font-size: 13px;
            }}
            QPushButton:hover {{
                border-color: {Gold.DEEP};
                color: {Gold.BRIGHT};
            }}
        """)
        today_btn.clicked.connect(self.today_clicked.emit)
        layout.addWidget(today_btn)

        # Prev button
        prev_btn = QPushButton("‹")
        prev_btn.setFixedSize(34, 34)
        prev_btn.setCursor(Qt.PointingHandCursor)
        prev_btn.setStyleSheet(f"""
            QPushButton {{
                background: transparent;
                color: {Text.SECONDARY};
                border: 1px solid {Border.NORMAL};
                border-radius: 6px;
                font-size: 18px;
                font-weight: bold;
            }}
            QPushButton:hover {{
                color: {Gold.BRIGHT};
                border-color: {Gold.DEEP};
            }}
        """)
        prev_btn.clicked.connect(self.prev_clicked.emit)
        layout.addWidget(prev_btn)

        # Next button
        next_btn = QPushButton("›")
        next_btn.setFixedSize(34, 34)
        next_btn.setCursor(Qt.PointingHandCursor)
        next_btn.setStyleSheet(f"""
            QPushButton {{
                background: transparent;
                color: {Text.SECONDARY};
                border: 1px solid {Border.NORMAL};
                border-radius: 6px;
                font-size: 18px;
                font-weight: bold;
            }}
            QPushButton:hover {{
                color: {Gold.BRIGHT};
                border-color: {Gold.DEEP};
            }}
        """)
        next_btn.clicked.connect(self.next_clicked.emit)
        layout.addWidget(next_btn)

        # Title
        self._title_label = QLabel("")
        self._title_label.setFont(QFont("Segoe UI", 16, QFont.Bold))
        self._title_label.setStyleSheet(f"color: {Text.PRIMARY};")
        layout.addWidget(self._title_label)
        layout.addStretch()

        # View switcher buttons
        self._view_buttons: dict[str, _ViewButton] = {}
        for kind, label in [
            (CalendarViewKind.DAY, "Day"),
            (CalendarViewKind.WEEK, "Week"),
            (CalendarViewKind.MONTH, "Month"),
            (CalendarViewKind.YEAR, "Year"),
        ]:
            btn = _ViewButton(label)
            btn.clicked.connect(lambda checked, k=kind.value: self.view_change_requested.emit(k))
            layout.addWidget(btn)
            self._view_buttons[kind.value] = btn

        self._update_view_buttons()

    def _update_view_buttons(self) -> None:
        current = self._ctrl.view_kind.value
        for val, btn in self._view_buttons.items():
            btn.set_checked(val == current)

    def update_title(self) -> None:
        self._title_label.setText(self._ctrl.nav_title())

    def update_view_buttons(self) -> None:
        self._update_view_buttons()


# ──────────────────────────────── CalendarView ────────────────────────────

class CalendarView(QWidget):
    """
    Main calendar view — the widget that goes into the Calendar tab.

    Contains: toolbar, sidebar, and stacked sub-views (Month/Week/Day/Year).
    """

    def __init__(self, store: CalendarStore, parent=None) -> None:
        super().__init__(parent)
        self._store = store
        self._ctrl = CalendarController(store, self)

        self._build_ui()
        self._wire_signals()
        self._setup_shortcuts()

        # Show the month view initially
        self._ctrl.set_view(CalendarViewKind.MONTH)
        self._show_current_view()

    # ── UI Building ──

    def _build_ui(self) -> None:
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # Toolbar
        self._toolbar = _CalendarToolbar(self._ctrl, self)
        main_layout.addWidget(self._toolbar)

        # Body: sidebar + views
        body = QWidget()
        body_layout = QHBoxLayout(body)
        body_layout.setContentsMargins(0, 0, 0, 0)
        body_layout.setSpacing(0)

        # Sidebar
        self._sidebar = CalendarSidebar(self._ctrl, self)
        body_layout.addWidget(self._sidebar)

        # Separator line
        sep = QFrame()
        sep.setFrameShape(QFrame.VLine)
        sep.setStyleSheet(f"color: {Border.SUBTLE};")
        body_layout.addWidget(sep)

        # Stacked views
        self._stack = QStackedWidget()
        self._month_view = MonthView(self._ctrl, self._stack)
        self._week_view = WeekView(self._ctrl, self._stack)
        self._day_view = DayView(self._ctrl, self._stack)
        self._year_view = YearView(self._ctrl, self._stack)

        self._stack.addWidget(self._month_view)
        self._stack.addWidget(self._week_view)
        self._stack.addWidget(self._day_view)
        self._stack.addWidget(self._year_view)

        body_layout.addWidget(self._stack, 1)
        main_layout.addWidget(body, 1)

    # ── Signal Wiring ──

    def _wire_signals(self) -> None:
        # Toolbar → controller
        self._toolbar.today_clicked.connect(self._ctrl.go_today)
        self._toolbar.prev_clicked.connect(self._ctrl.go_prev)
        self._toolbar.next_clicked.connect(self._ctrl.go_next)
        self._toolbar.new_event_clicked.connect(self._on_new_event)
        self._toolbar.view_change_requested.connect(self._ctrl.set_view_value)

        # Controller → toolbar/sidebar refresh
        self._ctrl.view_changed.connect(lambda _: self._on_view_changed())
        self._ctrl.date_changed.connect(self._on_date_changed)
        self._ctrl.events_changed.connect(self._on_events_changed)
        self._ctrl.selection_changed.connect(self._on_selection_changed)

        # Sidebar
        self._sidebar.date_clicked.connect(self._on_sidebar_date_clicked)
        self._sidebar.calendar_toggled.connect(self._on_calendar_toggled)
        self._sidebar.add_calendar_requested.connect(self._on_add_calendar)

        # View signals
        self._month_view.create_event_requested.connect(self._on_create_event_at)
        self._month_view.event_activated.connect(self._on_event_activated)
        self._week_view.create_event_requested.connect(self._on_create_event_at)
        self._week_view.event_activated.connect(self._on_event_activated)
        self._day_view.create_event_requested.connect(self._on_create_event_at)
        self._day_view.event_activated.connect(self._on_event_activated)
        self._year_view.month_activated.connect(self._on_year_month_activated)
        self._year_view.day_activated.connect(self._on_year_day_activated)

    # ── Shortcuts ──

    def _setup_shortcuts(self) -> None:
        # Google Calendar style shortcuts
        QShortcut(QKeySequence("C"), self, self._on_new_event)
        QShortcut(QKeySequence("N"), self, self._on_new_event)
        QShortcut(QKeySequence("T"), self, self._ctrl.go_today)
        QShortcut(QKeySequence("D"), self, lambda: self._ctrl.set_view(CalendarViewKind.DAY))
        QShortcut(QKeySequence("W"), self, lambda: self._ctrl.set_view(CalendarViewKind.WEEK))
        QShortcut(QKeySequence("M"), self, lambda: self._ctrl.set_view(CalendarViewKind.MONTH))
        QShortcut(QKeySequence("Y"), self, lambda: self._ctrl.set_view(CalendarViewKind.YEAR))
        QShortcut(QKeySequence("Plus"), self, self._ctrl.go_next)
        QShortcut(QKeySequence("Minus"), self, self._ctrl.go_prev)

    # ── View Switching ──

    def _show_current_view(self) -> None:
        kind = self._ctrl.view_kind
        if kind == CalendarViewKind.MONTH:
            self._stack.setCurrentWidget(self._month_view)
            self._month_view.set_month(self._ctrl.nav_date.year, self._ctrl.nav_date.month)
            self._month_view.refresh()
        elif kind == CalendarViewKind.WEEK:
            self._stack.setCurrentWidget(self._week_view)
            self._week_view.set_week(self._ctrl.nav_date)
            self._week_view.refresh()
        elif kind == CalendarViewKind.DAY:
            self._stack.setCurrentWidget(self._day_view)
            self._day_view.set_day(self._ctrl.nav_date)
            self._day_view.refresh()
        elif kind == CalendarViewKind.YEAR:
            self._stack.setCurrentWidget(self._year_view)
            self._year_view.set_year(self._ctrl.nav_date.year)
            self._year_view.refresh()

    # ── Slot Handlers ──

    def _on_view_changed(self) -> None:
        self._toolbar.update_view_buttons()
        self._show_current_view()

    def _on_date_changed(self) -> None:
        self._toolbar.update_title()
        self._sidebar.update_mini_month()
        self._show_current_view()

    def _on_events_changed(self) -> None:
        self._month_view.refresh()
        self._week_view.refresh()
        self._day_view.refresh()
        self._year_view.refresh()

    def _on_selection_changed(self) -> None:
        self._month_view.update()
        self._sidebar.update_mini_month()

    def _on_sidebar_date_clicked(self, d: ShamsiDate) -> None:
        self._ctrl.go_to_date(d)

    def _on_calendar_toggled(self, cal_id: str, visible: bool) -> None:
        self._store.set_calendar_visible(cal_id, visible)
        self._on_events_changed()

    def _on_add_calendar(self) -> None:
        dlg = CalendarSettingsDialog(self._store, self)
        dlg.exec()
        self._sidebar.refresh()
        self._on_events_changed()

    def _on_new_event(self) -> None:
        dlg = EventEditorDialog(None, self._store, self)
        if dlg.exec():
            self._on_events_changed()

    def _on_create_event_at(self, start_dt) -> None:
        """User double-clicked to create an event at a time."""
        evt = self._ctrl.create_event_at(start_dt)
        if evt:
            dlg = EventEditorDialog(evt, self._store, self)
            if dlg.exec():
                self._on_events_changed()

    def _on_event_activated(self, event_id: str) -> None:
        """User double-clicked an event to edit it."""
        evt = self._store.get_event(event_id)
        if evt:
            dlg = EventEditorDialog(evt, self._store, self)
            if dlg.exec():
                self._on_events_changed()

    def _on_year_month_activated(self, year: int, month: int) -> None:
        self._ctrl.go_to_date(ShamsiDate(year, month, 1))
        self._ctrl.set_view(CalendarViewKind.MONTH)

    def _on_year_day_activated(self, d) -> None:
        if isinstance(d, ShamsiDate):
            self._ctrl.go_to_date(d)
            self._ctrl.set_view(CalendarViewKind.DAY)

    # ── Public API ──

    @property
    def controller(self) -> CalendarController:
        return self._ctrl

    def refresh(self) -> None:
        """Force refresh all views."""
        self._show_current_view()
        self._sidebar.refresh()
