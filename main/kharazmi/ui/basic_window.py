"""
BasicMainWindow — the slim window for the Basic plan.

Shows ONLY:
  - Menu bar (File / Edit / Help, with limited options)
  - GoogleCalendarView (the full Google-Calendar-style experience)
  - Status bar (minimal)

Does NOT show:
  - The node graph, gantt, kanban, timeline, statistics views
  - The inspector panel
  - The command console
  - The command palette
  - The sidebar / outline tree
  - The toolbar with CPM / Monte Carlo / etc.

This is the calendar mode — full Google-Calendar-like experience
with Shamsi dates, multiple calendars, recurring events, drag-and-drop,
and natural-language input. Switch to Enterprise via the menu.
"""
from __future__ import annotations

from datetime import datetime, timedelta
from typing import Optional

from PySide6.QtCore import Qt, Signal, QTimer, QSize
from PySide6.QtGui import (
    QAction, QKeySequence, QIcon, QPixmap, QPainter, QColor, QBrush, QFont,
)
from PySide6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QSplitter, QFrame,
    QStatusBar, QLabel, QMessageBox, QFileDialog, QMenu,
)

from ..core import (
    Project, Task, TaskId, Duration, DurationUnit,
    ShamsiDate, format_shamsi, TaskStatus, Priority,
    DomainEvent, TaskCreated, TaskDeleted, TaskUpdated,
    DependencyAdded, DependencyRemoved, ScheduleRecalculated,
)
from ..calendar import CalendarStore
from ..commands import UndoStack
from ..services import TaskService, SchedulingService, ExportService
from ..persistence import SQLiteRepository, CalendarRepository
from .theme import Palette, QSS, build_qpalette, default_font
from .icons import get_icon
from .calendar import CalendarView
from .widgets import StatusBar, start_tour, TourOverlay
from .dialogs import (
    TaskEditorDialog, ProjectSettingsDialog, PlanSelectionDialog,
    load_saved_plan, save_plan,
    EventEditorDialog, CalendarSettingsDialog,
)


class BasicMainWindow(QMainWindow):
    """The Basic plan window — Google-Calendar-style experience."""

    def __init__(self, project: Optional[Project] = None) -> None:
        super().__init__()
        # Keep a Project reference for compatibility, but the Basic plan
        # primarily uses the CalendarStore, not the task graph.
        self.project = project or Project(name="My Calendar")
        self.undo_stack = UndoStack()
        self.scheduling = SchedulingService(self.project)
        self.task_service = TaskService(self.project, self.undo_stack, self.scheduling)
        self.export_service = ExportService(self.project)
        self.repository = SQLiteRepository()
        self.calendar_repository = CalendarRepository()

        # Load or create the calendar store
        self.calendar_store = self.calendar_repository.load_latest()
        if self.calendar_store is None:
            self.calendar_store = CalendarStore()
            # Add a Work calendar as a starter
            self.calendar_store.create_calendar("Work", color="#5A7FA8")

        self.setWindowTitle("Rask — Basic Calendar")
        self.resize(1400, 900)
        self.setMinimumSize(1000, 650)

        # Theme
        self.setStyleSheet(QSS)
        self.setPalette(build_qpalette())
        self.setFont(default_font())

        # Window icon
        pm = QPixmap(32, 32)
        pm.fill(Qt.transparent)
        p = QPainter(pm)
        p.setRenderHint(QPainter.Antialiasing, True)
        p.setBrush(QBrush(QColor(Palette.GOLD_PRIMARY)))
        p.setPen(Qt.NoPen)
        p.drawEllipse(4, 4, 24, 24)
        p.setBrush(QBrush(QColor(Palette.GOLD_BRIGHT)))
        p.drawEllipse(8, 8, 16, 16)
        p.end()
        self.setWindowIcon(QIcon(pm))

        # Build UI
        self._build_menu()
        self._build_content()
        self._build_statusbar()

        # Show tour on first run
        QTimer.singleShot(500, self._maybe_show_tour)

        # Autosave on a timer
        self._autosave_timer = QTimer(self)
        self._autosave_timer.setInterval(60000)  # every 60s
        self._autosave_timer.timeout.connect(self._autosave)
        self._autosave_timer.start()

    def _build_menu(self) -> None:
        menubar = self.menuBar()

        # File menu
        file_menu = menubar.addMenu("&File")

        self._action_new_event = QAction(get_icon("plus"), "&New Event...", self)
        self._action_new_event.setShortcut(QKeySequence("N"))
        self._action_new_event.triggered.connect(self._on_new_event)
        file_menu.addAction(self._action_new_event)

        file_menu.addSeparator()

        self._action_save = QAction(get_icon("save"), "&Save", self)
        self._action_save.setShortcut(QKeySequence.Save)
        self._action_save.triggered.connect(self._on_save)
        file_menu.addAction(self._action_save)

        file_menu.addSeparator()

        self._action_manage_calendars = QAction("Manage &Calendars...", self)
        self._action_manage_calendars.triggered.connect(self._on_manage_calendars)
        file_menu.addAction(self._action_manage_calendars)

        self._action_export = QAction("Export Events as &JSON...", self)
        self._action_export.triggered.connect(self._on_export)
        file_menu.addAction(self._action_export)

        file_menu.addSeparator()

        self._action_switch_plan = QAction("&Switch to Enterprise Plan...", self)
        self._action_switch_plan.triggered.connect(self._on_switch_plan)
        file_menu.addAction(self._action_switch_plan)

        file_menu.addSeparator()

        self._action_quit = QAction("&Quit", self)
        self._action_quit.setShortcut(QKeySequence.Quit)
        self._action_quit.triggered.connect(self.close)
        file_menu.addAction(self._action_quit)

        # Edit menu
        edit_menu = menubar.addMenu("&Edit")

        self._action_undo = QAction(get_icon("undo"), "&Undo", self)
        self._action_undo.setShortcut(QKeySequence.Undo)
        self._action_undo.triggered.connect(self._on_undo)
        edit_menu.addAction(self._action_undo)

        self._action_redo = QAction(get_icon("redo"), "&Redo", self)
        self._action_redo.setShortcut(QKeySequence.Redo)
        self._action_redo.triggered.connect(self._on_redo)
        edit_menu.addAction(self._action_redo)

        # Help menu
        help_menu = menubar.addMenu("&Help")
        self._action_tour = QAction("Take the &Tour", self)
        self._action_tour.setShortcut(QKeySequence("F1"))
        self._action_tour.triggered.connect(self._on_show_tour)
        help_menu.addAction(self._action_tour)

        help_menu.addSeparator()

        self._action_shortcuts = QAction("&Keyboard Shortcuts", self)
        self._action_shortcuts.triggered.connect(self._on_show_shortcuts)
        help_menu.addAction(self._action_shortcuts)

        help_menu.addSeparator()

        self._action_about = QAction("&About Rask", self)
        self._action_about.triggered.connect(self._on_about)
        help_menu.addAction(self._action_about)

    def _build_content(self) -> None:
        self.calendar_view = CalendarView(self.calendar_store)
        self.calendar_view.setObjectName("centralWidget")
        self.setCentralWidget(self.calendar_view)

    def _build_statusbar(self) -> None:
        self.statusbar = StatusBar(self)
        self.setStatusBar(self.statusbar)
        today = ShamsiDate.today()
        self.statusbar.update_project_named(
            f"  ◆  KHARAZMI BASIC   •   {today.format('d MMMM yyyy')}  •  {today.weekday_fa}"
        )
        # Count events
        self._refresh_statusbar()

    def _refresh_statusbar(self) -> None:
        # Subscribe to store changes
        from ..calendar import CalendarEvent, EventAdded, EventUpdated, EventRemoved
        self.calendar_store.subscribe(self._on_calendar_store_event)
        self.statusbar.show_message(
            f"{self.calendar_store.event_count} events across "
            f"{self.calendar_store.calendar_count} calendars",
            0,
        )

    def _on_calendar_store_event(self, event) -> None:
        QTimer.singleShot(0, lambda: self.statusbar.show_message(
            f"{self.calendar_store.event_count} events across "
            f"{self.calendar_store.calendar_count} calendars",
            0,
        ))
        # Persist deletions and updates immediately so they don't get lost
        from ..calendar.store import EventRemoved, CalendarRemoved, EventUpdated
        if isinstance(event, (EventRemoved, CalendarRemoved, EventUpdated)):
            self._autosave()
        else:
            # For additions, use a delayed save to batch rapid changes
            QTimer.singleShot(1000, self._autosave)

    # ---- Actions ----
    def _on_new_event(self) -> None:
        dlg = EventEditorDialog(None, self.calendar_store, self)
        dlg.exec()

    def _on_save(self) -> None:
        self.calendar_repository.save(self.calendar_store, kind="manual")
        self.statusbar.show_message("Calendar saved", 3000)

    def _on_manage_calendars(self) -> None:
        dlg = CalendarSettingsDialog(self.calendar_store, self)
        dlg.exec()

    def _on_export(self) -> None:
        path, _ = QFileDialog.getSaveFileName(
            self, "Export Calendar as JSON",
            "calendar.json",
            "JSON files (*.json);;All files (*)"
        )
        if not path:
            return
        try:
            import json
            with open(path, "w", encoding="utf-8") as f:
                json.dump(self.calendar_store.to_dict(), f, ensure_ascii=False, indent=2)
            self.statusbar.show_message(f"Exported → {path}", 4000)
        except Exception as e:
            QMessageBox.warning(self, "Export Failed", str(e))

    def _on_switch_plan(self) -> None:
        """Switch from Basic to the Enterprise plan."""
        ret = QMessageBox.question(
            self, "Switch Plan",
            "Switch to the Enterprise plan?\n\n"
            "Enterprise is the full node-graph task operating system with "
            "Critical Path Method, PERT estimates, Monte Carlo simulation, "
            "Gantt/Kanban/Timeline/Statistics views, an integrated console, "
            "and a command palette.\n\n"
            "Your calendar events are preserved. You can switch back to "
            "Basic anytime via File → Switch Plan.",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if ret == QMessageBox.Yes:
            save_plan("enterprise")
            QMessageBox.information(
                self, "Restart Required",
                "Plan changed to Enterprise. Please restart Rask to "
                "enter the node-graph mode."
            )
            self.close()

    def _on_undo(self) -> None:
        # Calendar store doesn't have undo (yet); this is a no-op
        self.statusbar.show_message("Undo not available in Basic plan", 2000)

    def _on_redo(self) -> None:
        self.statusbar.show_message("Redo not available in Basic plan", 2000)

    # ---- Tour ----
    def _maybe_show_tour(self) -> None:
        """Show the tour if the user hasn't seen it yet."""
        import json
        from pathlib import Path
        seen_path = Path.home() / ".rask" / "tour_seen_basic.json"
        if not seen_path.exists():
            self._on_show_tour()
            try:
                seen_path.parent.mkdir(parents=True, exist_ok=True)
                seen_path.write_text(json.dumps({"seen": True}), encoding="utf-8")
            except Exception:
                pass

    def _on_show_tour(self) -> None:
        start_tour(self)

    def _on_show_shortcuts(self) -> None:
        QMessageBox.information(
            self, "Keyboard Shortcuts",
            "<h3>Keyboard Shortcuts</h3>"
            "<table cellpadding='4'>"
            "<tr><td><b>c</b> or <b>n</b></td><td>Create new event</td></tr>"
            "<tr><td><b>t</b></td><td>Jump to today</td></tr>"
            "<tr><td><b>d</b></td><td>Day view</td></tr>"
            "<tr><td><b>w</b></td><td>Week view</td></tr>"
            "<tr><td><b>m</b></td><td>Month view</td></tr>"
            "<tr><td><b>y</b></td><td>Year view</td></tr>"
            "<tr><td><b>a</b></td><td>Schedule (agenda) view</td></tr>"
            "<tr><td><b>+</b> / <b>-</b></td><td>Next / previous period</td></tr>"
            "<tr><td><b>/</b></td><td>Focus search box</td></tr>"
            "<tr><td><b>Del</b></td><td>Delete selected event (in editor)</td></tr>"
            "</table>"
        )

    def _on_about(self) -> None:
        QMessageBox.about(
            self,
            "About Rask — Basic",
            "<h3>Rask — Basic Plan</h3>"
            "<p>A full Google-Calendar-style planner using the Persian "
            "Shamsi calendar.</p>"
            "<p>Features:</p>"
            "<ul>"
            "<li>Multiple calendars with colors and visibility</li>"
            "<li>Day / Week / Month / Year / Schedule views</li>"
            "<li>Recurring events (daily, weekly, monthly, yearly)</li>"
            "<li>Drag-and-drop to reschedule</li>"
            "<li>Natural-language event creation</li>"
            "<li>Built-in Persian holidays calendar</li>"
            "<li>Reminders, attendees, locations, meeting links</li>"
            "<li>Local SQLite persistence</li>"
            "</ul>"
            "<p>Upgrade to Enterprise via File → Switch to Enterprise Plan "
            "for the node-graph task operating system with CPM, PERT, and "
            "Monte Carlo simulation.</p>"
            "<p style='color:#D4AF37'><b>Version 2.0 — Basic</b></p>"
        )

    def _autosave(self) -> None:
        try:
            self.calendar_repository.save(self.calendar_store, kind="autosave")
        except Exception:
            pass

    def closeEvent(self, event) -> None:
        # Final autosave on close
        try:
            self.calendar_repository.save(self.calendar_store, kind="autosave")
        except Exception:
            pass
        super().closeEvent(event)
