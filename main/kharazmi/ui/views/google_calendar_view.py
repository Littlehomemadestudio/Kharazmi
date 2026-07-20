"""
GoogleCalendarView — the main container for the Basic plan.

Layout (mirrors Google Calendar's desktop UI):

  ┌──────────────────────────────────────────────────────────────────┐
  │ Top bar: Search | Today | ‹ › | [Day|Week|Month|Year|Schedule]   │
  │         Natural-language input bar                                │
  ├──────────────┬───────────────────────────────────────────────────┤
  │  Sidebar     │                                                   │
  │  ┌─────────┐ │                                                   │
  │  │ Mini    │ │                                                   │
  │  │ Month   │ │           Main view (Day/Week/Month/Year/Schedule)│
  │  └─────────┘ │                                                   │
  │              │                                                   │
  │  Calendars:  │                                                   │
  │  ☑ Personal  │                                                   │
  │  ☑ Work      │                                                   │
  │  ☐ Holidays  │                                                   │
  └──────────────┴───────────────────────────────────────────────────┘

Keyboard shortcuts (Google Calendar style):
  c / n    → create event
  t        → today
  d        → day view
  w        → week view
  m        → month view
  y        → year view
  a        → agenda/schedule view
  + / -    → next/prev
  /        → focus search
"""
from __future__ import annotations

from datetime import datetime, timedelta
from typing import Optional

from PySide6.QtCore import Qt, Signal, QTimer
from PySide6.QtGui import (
    QAction, QKeySequence, QFont, QColor, QShortcut, QIcon, QPixmap, QPainter,
    QBrush, QKeyEvent,
)
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, QPushButton,
    QFrame, QSplitter, QComboBox, QToolButton, QSizePolicy, QScrollArea,
    QMessageBox, QApplication, QCheckBox, QSpacerItem,
)

from ...calendar import (
    CalendarStore, Event as CalEvent, Calendar, CalendarViewKind,
    CalendarEvent, EventAdded, EventUpdated, EventRemoved,
    CalendarVisibilityChanged, parse, ParsedEvent,
    create_holiday_calendar, create_holiday_events,
    RecurrenceRule, RecurrenceFrequency, ByDay, Weekday,
)
from ...core.shamsi import (
    ShamsiDate, format_shamsi, iterate_week,
    SHAMSI_MONTHS_FA, SHAMSI_WEEKDAYS_FA, SHAMSI_WEEKDAYS_SHORT_EN,
)
from ..theme import Palette
from ..icons import get_icon
from ..widgets import (
    MiniMonthWidget, CalendarListWidget,
    NaturalLanguageInput,
)
from ..views import (
    DayView, WeekView, MonthView, YearView, ScheduleView, CustomView,
)
from ..dialogs import EventEditorDialog, CalendarSettingsDialog


class GoogleCalendarView(QWidget):
    """
    The full Google-Calendar-style experience.

    Owns a CalendarStore and renders all the views.
    """

    eventEditRequested = Signal(str)  # event_id
    viewKindChanged = Signal(str)

    def __init__(self, store: CalendarStore, parent: QWidget = None) -> None:
        super().__init__(parent)
        self.store = store
        self._view_kind: CalendarViewKind = CalendarViewKind.MONTH
        self._current_date: ShamsiDate = ShamsiDate.today()
        self._custom_days = 4

        self.setStyleSheet(f"background-color: {Palette.BG_PRIMARY};")

        # Ensure the holidays calendar exists
        self._ensure_holidays_calendar()

        # Build UI
        self._build_ui()
        self._build_views()
        self._switch_view(CalendarViewKind.MONTH)

        # Subscribe to store events for mini-month updates
        self.store.subscribe(self._on_store_event)

        # Wire keyboard shortcuts
        self._wire_shortcuts()

        # Initial refresh
        QTimer.singleShot(100, self._refresh_mini_month)

    def _ensure_holidays_calendar(self) -> None:
        """Add the read-only Persian holidays calendar if not present."""
        if self.store.get_calendar("cal-holidays") is None:
            self.store.add_calendar(create_holiday_calendar())
            for evt in create_holiday_events():
                try:
                    self.store.add_event(evt)
                except Exception:
                    pass

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # Top bar
        layout.addWidget(self._build_topbar())

        # Natural-language input
        self._nl_input = NaturalLanguageInput()
        self._nl_input.eventParsed.connect(self._on_nl_parsed)
        layout.addWidget(self._nl_input)

        # Main content: sidebar + view
        splitter = QSplitter(Qt.Horizontal, self)
        splitter.setHandleWidth(2)
        splitter.setStyleSheet(
            f"QSplitter::handle {{ background: {Palette.BG_DEEPEST}; }}"
        )

        # Sidebar
        sidebar = self._build_sidebar()
        splitter.addWidget(sidebar)

        # View container
        self._view_container = QFrame()
        self._view_container.setObjectName("viewContainer")
        self._view_container.setStyleSheet(
            f"QFrame#viewContainer {{ background-color: {Palette.BG_PRIMARY}; }}"
        )
        self._view_layout = QVBoxLayout(self._view_container)
        self._view_layout.setContentsMargins(0, 0, 0, 0)
        self._view_layout.setSpacing(0)
        splitter.addWidget(self._view_container)

        splitter.setStretchFactor(0, 0)
        splitter.setStretchFactor(1, 1)
        splitter.setSizes([260, 1000])

        layout.addWidget(splitter, stretch=1)

    def _build_topbar(self) -> QWidget:
        bar = QFrame()
        bar.setFixedHeight(56)
        bar.setStyleSheet(
            f"background-color: {Palette.BG_SECONDARY}; "
            f"border-bottom: 1px solid {Palette.BORDER_SUBTLE};"
        )
        layout = QHBoxLayout(bar)
        layout.setContentsMargins(16, 8, 16, 8)
        layout.setSpacing(12)

        # Today button
        today_btn = QPushButton("Today")
        today_btn.setProperty("variant", "primary")
        today_btn.setFixedHeight(36)
        today_btn.clicked.connect(self._go_today)
        layout.addWidget(today_btn)

        # Prev/Next
        prev_btn = QToolButton()
        prev_btn.setText("‹")
        prev_btn.setFixedSize(36, 36)
        prev_btn.setStyleSheet(self._nav_style())
        prev_btn.clicked.connect(lambda: self._navigate(-1))
        layout.addWidget(prev_btn)

        next_btn = QToolButton()
        next_btn.setText("›")
        next_btn.setFixedSize(36, 36)
        next_btn.setStyleSheet(self._nav_style())
        next_btn.clicked.connect(lambda: self._navigate(1))
        layout.addWidget(next_btn)

        # Current period title
        self._title_label = QLabel("")
        self._title_label.setStyleSheet(
            f"color: {Palette.GOLD_BRIGHT}; font-size: 18px; "
            f"font-weight: bold; letter-spacing: 0.5px; padding: 0 12px;"
        )
        layout.addWidget(self._title_label)

        layout.addStretch()

        # Search
        self._search = QLineEdit()
        self._search.setPlaceholderText("🔍  Search events...")
        self._search.setFixedWidth(280)
        self._search.setFixedHeight(36)
        self._search.setStyleSheet(f"""
            QLineEdit {{
                background-color: {Palette.BG_TERTIARY};
                color: {Palette.TEXT_PRIMARY};
                border: 1px solid {Palette.BORDER_NORMAL};
                border-radius: 4px;
                padding: 6px 12px;
                font-size: 12px;
            }}
            QLineEdit:focus {{
                border: 1px solid {Palette.GOLD_PRIMARY};
            }}
        """)
        self._search.returnPressed.connect(self._on_search)
        layout.addWidget(self._search)

        # View selector
        self._view_combo = QComboBox()
        for kind in [CalendarViewKind.DAY, CalendarViewKind.WEEK,
                     CalendarViewKind.MONTH, CalendarViewKind.YEAR,
                     CalendarViewKind.SCHEDULE]:
            self._view_combo.addItem(kind.value.title(), kind)
        self._view_combo.setFixedHeight(36)
        self._view_combo.setStyleSheet(f"""
            QComboBox {{
                background-color: {Palette.BG_TERTIARY};
                color: {Palette.TEXT_PRIMARY};
                border: 1px solid {Palette.BORDER_NORMAL};
                border-radius: 4px;
                padding: 6px 14px;
                font-size: 12px;
                min-width: 110px;
            }}
        """)
        self._view_combo.currentIndexChanged.connect(
            lambda _: self._switch_view(self._view_combo.currentData())
        )
        layout.addWidget(self._view_combo)

        # New event button
        new_btn = QPushButton("+ Event")
        new_btn.setProperty("variant", "primary")
        new_btn.setFixedHeight(36)
        new_btn.clicked.connect(self._on_new_event)
        layout.addWidget(new_btn)

        return bar

    def _nav_style(self) -> str:
        return f"""
            QToolButton {{
                background-color: {Palette.BG_TERTIARY};
                color: {Palette.GOLD_BRIGHT};
                border: 1px solid {Palette.BORDER_NORMAL};
                border-radius: 4px;
                font-size: 20px;
                font-weight: bold;
            }}
            QToolButton:hover {{
                background-color: {Palette.BG_ELEVATED};
                border: 1px solid {Palette.GOLD_PRIMARY};
            }}
        """

    def _build_sidebar(self) -> QWidget:
        sidebar = QWidget()
        sidebar.setStyleSheet(f"background-color: {Palette.BG_SECONDARY};")
        sidebar.setMinimumWidth(240)
        sidebar.setMaximumWidth(320)
        layout = QVBoxLayout(sidebar)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(10)

        # Mini month
        self._mini_month = MiniMonthWidget()
        self._mini_month.dateSelected.connect(self._on_mini_month_date)
        self._mini_month.monthChanged.connect(self._on_mini_month_changed)
        layout.addWidget(self._mini_month)

        # Calendar list
        self._cal_list = CalendarListWidget(self.store)
        self._cal_list.calendarEditRequested.connect(self._on_edit_calendar)
        self._cal_list.createCalendarRequested.connect(self._on_create_calendar)
        layout.addWidget(self._cal_list, stretch=1)

        # Bottom: today info
        today = ShamsiDate.today()
        today_label = QLabel(
            f"Today: {today.format('d MMMM yyyy')}\n{today.weekday_fa}"
        )
        today_label.setStyleSheet(
            f"color: {Palette.TEXT_TERTIARY}; font-size: 11px; "
            f"padding: 8px; font-family: 'JetBrains Mono', monospace;"
        )
        today_label.setAlignment(Qt.AlignCenter)
        layout.addWidget(today_label)

        return sidebar

    def _build_views(self) -> None:
        self._views: dict[CalendarViewKind, QWidget] = {
            CalendarViewKind.DAY: DayView(self.store),
            CalendarViewKind.WEEK: WeekView(self.store),
            CalendarViewKind.MONTH: MonthView(self.store),
            CalendarViewKind.YEAR: YearView(self.store),
            CalendarViewKind.SCHEDULE: ScheduleView(self.store),
        }
        # Wire common signals
        for view in self._views.values():
            if hasattr(view, "eventDoubleClicked"):
                view.eventDoubleClicked.connect(self._on_event_double_clicked)
            if hasattr(view, "eventClicked"):
                view.eventClicked.connect(self._on_event_clicked)
            if hasattr(view, "cellDoubleClicked"):
                view.cellDoubleClicked.connect(self._on_day_double_clicked)
            if hasattr(view, "dayDoubleClicked"):
                view.dayDoubleClicked.connect(self._on_day_double_clicked)
            if hasattr(view, "eventMoveRequested"):
                view.eventMoveRequested.connect(self._on_event_move)
            if hasattr(view, "eventResizeRequested"):
                view.eventResizeRequested.connect(self._on_event_resize)
            if hasattr(view, "eventDropped"):
                view.eventDropped.connect(self._on_event_dropped)
            if hasattr(view, "monthClicked"):
                view.monthClicked.connect(self._on_year_month_clicked)

    # ---- View switching ----
    def _switch_view(self, kind: CalendarViewKind) -> None:
        self._view_kind = kind
        # Clear current view
        while self._view_layout.count():
            item = self._view_layout.takeAt(0)
            if item.widget():
                item.widget().setParent(None)
        # Add new view
        view = self._views[kind]
        self._view_layout.addWidget(view)
        # Update view's anchor date
        if hasattr(view, "set_anchor_date"):
            view.set_anchor_date(self._current_date)
        elif hasattr(view, "set_year"):
            view.set_year(self._current_date.year)
        # Update title
        self._update_title()
        # Update combo (without triggering)
        for i in range(self._view_combo.count()):
            if self._view_combo.itemData(i) == kind:
                self._view_combo.blockSignals(True)
                self._view_combo.setCurrentIndex(i)
                self._view_combo.blockSignals(False)
                break
        self.viewKindChanged.emit(kind.value)

    def _update_title(self) -> None:
        kind = self._view_kind
        if kind == CalendarViewKind.MONTH:
            self._title_label.setText(
                f"{SHAMSI_MONTHS_FA[self._current_date.month - 1]}  {self._current_date.year}"
            )
        elif kind == CalendarViewKind.WEEK:
            days = iterate_week(self._current_date)
            first, last = days[0], days[-1]
            if first.month == last.month:
                self._title_label.setText(
                    f"{first.day} – {last.day}  {first.month_name_fa}  {first.year}"
                )
            else:
                self._title_label.setText(
                    f"{first.day} {first.month_name_fa} – {last.day} {last.month_name_fa}  {last.year}"
                )
        elif kind == CalendarViewKind.DAY:
            self._title_label.setText(
                f"{self._current_date.day}  {self._current_date.month_name_fa}  {self._current_date.year}"
            )
        elif kind == CalendarViewKind.YEAR:
            self._title_label.setText(str(self._current_date.year))
        elif kind == CalendarViewKind.SCHEDULE:
            self._title_label.setText("Schedule")

    # ---- Navigation ----
    def _go_today(self) -> None:
        self._current_date = ShamsiDate.today()
        self._apply_to_view()
        self._refresh_mini_month()

    def _navigate(self, delta: int) -> None:
        kind = self._view_kind
        if kind == CalendarViewKind.MONTH:
            self._current_date = self._current_date.add_months(delta)
        elif kind == CalendarViewKind.WEEK:
            self._current_date = self._current_date.add_days(7 * delta)
        elif kind == CalendarViewKind.YEAR:
            self._current_date = self._current_date.add_years(delta)
        elif kind == CalendarViewKind.SCHEDULE:
            # No-op for schedule (shows next 30 days always)
            return
        else:
            self._current_date = self._current_date.add_days(delta)
        self._apply_to_view()
        self._refresh_mini_month()

    def _apply_to_view(self) -> None:
        view = self._views.get(self._view_kind)
        if view is None:
            return
        if hasattr(view, "set_anchor_date"):
            view.set_anchor_date(self._current_date)
        elif hasattr(view, "set_year"):
            view.set_year(self._current_date.year)
        elif hasattr(view, "refresh"):
            view.refresh()
        self._update_title()

    # ---- Mini month ----
    def _on_mini_month_date(self, sd: ShamsiDate) -> None:
        self._current_date = sd
        # Switch to Day view
        self._switch_view(CalendarViewKind.DAY)
        self._apply_to_view()

    def _on_mini_month_changed(self, first_of_month: ShamsiDate) -> None:
        # If we're in month view, navigate to that month
        if self._view_kind == CalendarViewKind.MONTH:
            self._current_date = first_of_month
            self._apply_to_view()

    def _refresh_mini_month(self) -> None:
        self._mini_month.set_selected(self._current_date)
        # Compute dates with events for the visible month
        dates_with_events: set[ShamsiDate] = set()
        year = self._mini_month._current.year
        month = self._mini_month._current.month
        first = ShamsiDate(year, month, 1).to_datetime(0, 0)
        last_day = ShamsiDate(year, month, days_in_month_safe(year, month)).to_datetime(23, 59)
        for evt in self.store.events_in_range(first, last_day):
            sd = ShamsiDate.from_gregorian(evt.start.date())
            dates_with_events.add(sd)
        self._mini_month.set_dates_with_events(dates_with_events)

    def _on_store_event(self, event: CalendarEvent) -> None:
        QTimer.singleShot(0, self._refresh_mini_month)

    # ---- Year view ----
    def _on_year_month_clicked(self, month: int) -> None:
        self._current_date = ShamsiDate(self._current_date.year, month, 1)
        self._switch_view(CalendarViewKind.MONTH)
        self._apply_to_view()
        self._refresh_mini_month()

    # ---- Event interaction ----
    def _on_event_double_clicked(self, event_id: str) -> None:
        evt = self.store.get_event(event_id)
        if evt is None:
            return
        dlg = EventEditorDialog(evt, self.store, self)
        dlg.exec()
        self._refresh_mini_month()

    def _on_event_clicked(self, event_id: str) -> None:
        # Could show a quick popover here; for now, just select
        pass

    def _on_event_move(self, event_id: str, new_start: datetime) -> None:
        evt = self.store.get_event(event_id)
        if evt is None:
            return
        duration = evt.duration
        self.store.update_event(event_id, start=new_start, end=new_start + duration)

    def _on_event_resize(self, event_id: str, new_duration: int) -> None:
        evt = self.store.get_event(event_id)
        if evt is None:
            return
        new_end = evt.start + timedelta(minutes=new_duration)
        self.store.update_event(event_id, end=new_end)

    def _on_event_dropped(self, event_id_str: str, target_date: ShamsiDate) -> None:
        evt = self.store.get_event(event_id_str)
        if evt is None:
            return
        # Preserve time-of-day
        hour = evt.start.hour
        minute = evt.start.minute
        new_start = target_date.to_datetime(hour, minute)
        duration = evt.duration
        self.store.update_event(event_id_str, start=new_start,
                                  end=new_start + duration)

    def _on_day_double_clicked(self, sd: ShamsiDate) -> None:
        # Create a new event starting at 9am on this day
        start = sd.to_datetime(9, 0)
        dlg = EventEditorDialog(None, self.store, self)
        # Pre-fill start time
        dlg._start_dt.setDateTime(start)
        dlg._end_dt.setDateTime(start + timedelta(hours=1))
        dlg.exec()
        self._refresh_mini_month()

    # ---- New event ----
    def _on_new_event(self) -> None:
        dlg = EventEditorDialog(None, self.store, self)
        # Pre-fill with current date at 9am
        start = self._current_date.to_datetime(9, 0)
        dlg._start_dt.setDateTime(start)
        dlg._end_dt.setDateTime(start + timedelta(hours=1))
        dlg.exec()
        self._refresh_mini_month()

    # ---- Natural language ----
    def _on_nl_parsed(self, parsed: ParsedEvent) -> None:
        """Open the event editor pre-filled with parsed values."""
        # Find a writable calendar
        cal_id = "cal-default"
        for cal in self.store.calendars():
            if cal.visible and not cal.is_readonly:
                cal_id = cal.id
                break

        # Create the event directly from parsed data
        end = parsed.start + timedelta(minutes=parsed.duration_minutes or 60)
        # Build recurrence if specified
        recurrence = None
        if parsed.recurrence == "daily":
            recurrence = RecurrenceRule(freq=RecurrenceFrequency.DAILY)
        elif parsed.recurrence == "weekly" or parsed.recurrence == "weekly_weekday":
            recurrence = RecurrenceRule(freq=RecurrenceFrequency.WEEKLY)
        elif parsed.recurrence == "monthly":
            recurrence = RecurrenceRule(freq=RecurrenceFrequency.MONTHLY)
        elif parsed.recurrence == "yearly":
            recurrence = RecurrenceRule(freq=RecurrenceFrequency.YEARLY)
        elif parsed.recurrence == "weekdays":
            recurrence = RecurrenceRule(
                freq=RecurrenceFrequency.WEEKLY,
                by_day=(ByDay(Weekday.MONDAY), ByDay(Weekday.TUESDAY),
                         ByDay(Weekday.WEDNESDAY), ByDay(Weekday.THURSDAY),
                         ByDay(Weekday.FRIDAY)),
            )

        # Build attendees
        from ...calendar import Attendee
        attendees = [Attendee(name=name) for name in parsed.attendees]

        from ...calendar import EventType, Availability
        try:
            event_type = EventType(parsed.event_type)
        except ValueError:
            event_type = EventType.NORMAL

        evt = CalEvent.create(
            calendar_id=cal_id,
            title=parsed.title,
            start=parsed.start,
            end=end,
            all_day=parsed.all_day,
            event_type=event_type,
            availability=Availability.BUSY,
            recurrence=recurrence,
            attendees=attendees,
        )
        self.store.add_event(evt)
        self._refresh_mini_month()

        # Jump to that date
        self._current_date = ShamsiDate.from_datetime(parsed.start)
        self._switch_view(CalendarViewKind.DAY)
        self._apply_to_view()

    # ---- Calendar management ----
    def _on_edit_calendar(self, cal_id: str) -> None:
        dlg = CalendarSettingsDialog(self.store, self)
        dlg.exec()
        self._refresh_mini_month()

    def _on_create_calendar(self) -> None:
        dlg = CalendarSettingsDialog(self.store, self)
        dlg.exec()
        self._refresh_mini_month()

    # ---- Search ----
    def _on_search(self) -> None:
        query = self._search.text().strip()
        if not query:
            return
        results = self.store.search(query)
        if not results:
            QMessageBox.information(self, "Search", f"No events matching '{query}'.")
            return
        # Show results in a simple list dialog
        from PySide6.QtWidgets import QDialog, QListWidget, QListWidgetItem, QPushButton
        dlg = QDialog(self)
        dlg.setWindowTitle(f"Search: '{query}'  ({len(results)} results)")
        dlg.setMinimumSize(500, 400)
        layout = QVBoxLayout(dlg)
        list_widget = QListWidget()
        for evt in sorted(results, key=lambda e: e.start):
            from ...core.shamsi import format_shamsi
            label = f"{format_shamsi(evt.start, include_time=True)}  —  {evt.title}"
            if evt.location:
                label += f"  📍 {evt.location}"
            item = QListWidgetItem(label)
            item.setData(Qt.UserRole, evt.id)
            list_widget.addItem(item)
        layout.addWidget(list_widget)
        open_btn = QPushButton("Open")
        open_btn.clicked.connect(lambda: self._open_search_result(list_widget, dlg))
        layout.addWidget(open_btn)
        dlg.exec()

    def _open_search_result(self, list_widget, dlg) -> None:
        item = list_widget.currentItem()
        if item is None:
            return
        event_id = item.data(Qt.UserRole)
        dlg.accept()
        self._on_event_double_clicked(event_id)

    # ---- Keyboard shortcuts (Google Calendar style) ----
    def _wire_shortcuts(self) -> None:
        # c / n → new event
        QShortcut(QKeySequence("c"), self, activated=self._on_new_event)
        QShortcut(QKeySequence("n"), self, activated=self._on_new_event)
        # t → today
        QShortcut(QKeySequence("t"), self, activated=self._go_today)
        # d / w / m / y / a → view switch
        QShortcut(QKeySequence("d"), self,
                   activated=lambda: self._switch_view(CalendarViewKind.DAY))
        QShortcut(QKeySequence("w"), self,
                   activated=lambda: self._switch_view(CalendarViewKind.WEEK))
        QShortcut(QKeySequence("m"), self,
                   activated=lambda: self._switch_view(CalendarViewKind.MONTH))
        QShortcut(QKeySequence("y"), self,
                   activated=lambda: self._switch_view(CalendarViewKind.YEAR))
        QShortcut(QKeySequence("a"), self,
                   activated=lambda: self._switch_view(CalendarViewKind.SCHEDULE))
        # + / - → next/prev
        QShortcut(QKeySequence("+"), self, activated=lambda: self._navigate(1))
        QShortcut(QKeySequence("="), self, activated=lambda: self._navigate(1))
        QShortcut(QKeySequence("-"), self, activated=lambda: self._navigate(-1))
        # / → focus search
        QShortcut(QKeySequence("/"), self, activated=self._search.setFocus)


def days_in_month_safe(year: int, month: int) -> int:
    """Avoid circular import."""
    from ...core.shamsi import days_in_month
    return days_in_month(year, month)
