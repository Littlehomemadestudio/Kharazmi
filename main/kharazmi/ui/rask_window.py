"""
RaskMainWindow — the unified application window.

Integrates all of Rask's capabilities into a single tabbed interface:

  1. Calendar  — Google-Calendar-style planner (Shamsi dates, multi-calendar,
                 recurring events, drag-and-drop, natural-language input)
  2. AI Planner — the analysis screen: type a goal, AI asks clarifying
                 questions, generates a walkable node-graph route with
                 success probabilities, fallbacks, time estimates
  3. Journal   — history of all AI-generated routes
  4. Tasks     — the Enterprise node-graph task operating system (CPM,
                 PERT, Monte Carlo, Gantt, Kanban, Timeline, Statistics)

The Calendar is the first/default view, exactly as the user requested.
"""
from __future__ import annotations

import os
from datetime import datetime, timedelta
from typing import Optional

from PySide6.QtCore import Qt, Signal, QTimer, QSize
from PySide6.QtGui import (
    QAction, QKeySequence, QIcon, QPixmap, QPainter, QColor, QBrush, QFont,
)
from PySide6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QSplitter, QFrame,
    QStatusBar, QLabel, QMessageBox, QFileDialog, QMenu, QTabWidget,
    QApplication, QToolButton, QSizePolicy, QPushButton,
)

from ..core import (
    Project, Task, TaskId, Duration, DurationUnit,
    ShamsiDate, format_shamsi, TaskStatus, Priority,
    DomainEvent, TaskCreated, TaskDeleted, TaskUpdated,
    DependencyAdded, DependencyRemoved, ScheduleRecalculated,
)
from ..calendar import CalendarStore
from ..calendar.store import EventRemoved, CalendarRemoved
from ..ai import AIService, JournalStore, Route
from ..commands import UndoStack
from ..services import TaskService, SchedulingService, ExportService
from ..persistence import SQLiteRepository, CalendarRepository
from .theme import Palette, QSS, build_qpalette, default_font
from .icons import get_icon
from .views import (
    CalendarView, AIPlannerView, JournalView,
    GraphsView, SimulationView, DashboardView,
)
from .widgets import (
    MainToolbar, StatusBar,
    CommandPaletteDialog, PaletteItem, MinimapOverlay,
    start_tour, TourOverlay,
    GlassTitleBar, FramelessWindowMixin, RaskSplashScreen,
    GoldParticleBackground,
)
from .dialogs import (
    TaskEditorDialog, ProjectSettingsDialog, AdvisorDialog,
    EventEditorDialog, CalendarSettingsDialog, AISettingsDialog,
)


class RaskMainWindow(QMainWindow, FramelessWindowMixin):
    """
    The unified Rask window.

    Tabs:
      - Calendar (default, shown first)
      - AI Planner
      - Journal
      - Tasks (the Enterprise node-graph view)
    """

    def __init__(self, project: Optional[Project] = None) -> None:
        super().__init__()
        # ---- Domain state ----
        self.project = project or Project(name="My Project")
        self.undo_stack = UndoStack()
        self.scheduling = SchedulingService(self.project)
        self.task_service = TaskService(self.project, self.undo_stack, self.scheduling)
        self.export_service = ExportService(self.project)
        self.repository = SQLiteRepository()
        self.calendar_repository = CalendarRepository()
        self.calendar_store = self.calendar_repository.load_latest() or CalendarStore()
        if not self.calendar_repository.has_snapshot():
            # Seed a Work calendar as starter
            self.calendar_store.create_calendar("Work", color="#5A7FA8")
        self.ai_service = AIService()
        self.journal_store = JournalStore()

        # ---- Window setup ----
        self.setWindowTitle("RASK — Calendar · AI Planner · Tasks")
        self.resize(1600, 1000)
        self.setMinimumSize(1100, 700)

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

        # ---- Frameless window with glass title bar ----
        self._init_frameless(title="RASK!", icon=pm)

        self.setStyleSheet(QSS)
        self.setPalette(build_qpalette())
        self.setFont(default_font())

        # ---- Build UI ----
        self._build_ui_with_titlebar()
        self._build_menu()
        self._build_statusbar()

        # ---- Subscribe to events ----
        self.project.subscribe(self._on_project_event)
        self.calendar_store.subscribe(self._on_calendar_store_event)
        self.undo_stack.subscribe(self._on_undo_stack_changed)

        # ---- Wire cross-tab interactions ----
        self.journal_view.entrySelected.connect(self._on_journal_entry_selected)
        self.journal_view.goToPlannerRequested.connect(lambda: self._switch_tab(2))
        self.ai_planner_view.routeUpdated.connect(self._on_planner_route_updated)

        # ---- Auto-recalc ----
        QTimer.singleShot(100, self._recalculate)

        # ---- Show tour on first run ----
        QTimer.singleShot(600, self._maybe_show_tour)

        # ---- Calendar autosave ----
        self._autosave_timer = QTimer(self)
        self._autosave_timer.setInterval(60000)
        self._autosave_timer.timeout.connect(self._autosave)
        self._autosave_timer.start()

    # ---- UI building ----
    def _build_ui_with_titlebar(self) -> None:
        """Build the main layout with the glass title bar on top."""
        central = QWidget()
        central.setStyleSheet(f"background: {Palette.BG_DEEPEST};")
        main_layout = QVBoxLayout(central)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # Add glass title bar at the top
        self._add_titlebar_to_layout(main_layout)

        # Build content below title bar
        self._build_content()
        main_layout.addWidget(self._tabs)

        self.setCentralWidget(central)

    def _build_menu(self) -> None:
        menubar = self.menuBar()

        # File menu
        file_menu = menubar.addMenu("&File")

        # New actions
        self._action_new_event = QAction(get_icon("plus"), "New &Event...", self)
        self._action_new_event.setShortcut(QKeySequence("Ctrl+E"))
        self._action_new_event.triggered.connect(self._on_new_event)
        file_menu.addAction(self._action_new_event)

        self._action_new_task = QAction(get_icon("plus"), "New &Task...", self)
        self._action_new_task.setShortcut(QKeySequence("Ctrl+T"))
        self._action_new_task.triggered.connect(self._on_new_task)
        file_menu.addAction(self._action_new_task)

        file_menu.addSeparator()

        self._action_save = QAction(get_icon("save"), "&Save", self)
        self._action_save.setShortcut(QKeySequence.Save)
        self._action_save.triggered.connect(self._on_save)
        file_menu.addAction(self._action_save)

        file_menu.addSeparator()

        self._action_ai_settings = QAction("AI &Settings...", self)
        self._action_ai_settings.triggered.connect(self._on_ai_settings)
        file_menu.addAction(self._action_ai_settings)

        self._action_manage_calendars = QAction("Manage &Calendars...", self)
        self._action_manage_calendars.triggered.connect(self._on_manage_calendars)
        file_menu.addAction(self._action_manage_calendars)

        file_menu.addSeparator()

        self._action_export_json = QAction("Export Tasks as &JSON...", self)
        self._action_export_json.triggered.connect(lambda: self._on_export("json"))
        file_menu.addAction(self._action_export_json)

        self._action_export_calendar = QAction("Export &Calendar as JSON...", self)
        self._action_export_calendar.triggered.connect(self._on_export_calendar)
        file_menu.addAction(self._action_export_calendar)

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

        # View menu
        view_menu = menubar.addMenu("&View")
        self._action_tab_home = QAction("Go to &Home", self)
        self._action_tab_home.setShortcut(QKeySequence("Ctrl+0"))
        self._action_tab_home.triggered.connect(lambda: self._switch_tab(0))
        view_menu.addAction(self._action_tab_home)

        self._action_tab_calendar = QAction("Go to &Calendar", self)
        self._action_tab_calendar.setShortcut(QKeySequence("Ctrl+1"))
        self._action_tab_calendar.triggered.connect(lambda: self._switch_tab(1))
        view_menu.addAction(self._action_tab_calendar)

        self._action_tab_ai = QAction("Go to &AI Planner", self)
        self._action_tab_ai.setShortcut(QKeySequence("Ctrl+2"))
        self._action_tab_ai.triggered.connect(lambda: self._switch_tab(2))
        view_menu.addAction(self._action_tab_ai)

        self._action_tab_graphs = QAction("Go to &Graphs", self)
        self._action_tab_graphs.setShortcut(QKeySequence("Ctrl+3"))
        self._action_tab_graphs.triggered.connect(lambda: self._switch_tab(3))
        view_menu.addAction(self._action_tab_graphs)

        self._action_tab_simulation = QAction("Go to &Simulation", self)
        self._action_tab_simulation.setShortcut(QKeySequence("Ctrl+4"))
        self._action_tab_simulation.triggered.connect(lambda: self._switch_tab(4))
        view_menu.addAction(self._action_tab_simulation)

        self._action_tab_journal = QAction("Go to &Journal", self)
        self._action_tab_journal.setShortcut(QKeySequence("Ctrl+5"))
        self._action_tab_journal.triggered.connect(lambda: self._switch_tab(5))
        view_menu.addAction(self._action_tab_journal)

        self._action_tab_tasks = QAction("Go to &Tasks", self)
        self._action_tab_tasks.setShortcut(QKeySequence("Ctrl+6"))
        self._action_tab_tasks.triggered.connect(lambda: self._switch_tab(2))
        view_menu.addAction(self._action_tab_tasks)

        # Schedule menu (for Enterprise features)
        sched_menu = menubar.addMenu("&Schedule")
        self._action_recalc = QAction(get_icon("play"), "&Recalculate CPM", self)
        self._action_recalc.setShortcut(QKeySequence("Ctrl+R"))
        self._action_recalc.triggered.connect(self._recalculate)
        sched_menu.addAction(self._action_recalc)

        self._action_advisor = QAction(get_icon("warning"), "&Advisor Report", self)
        self._action_advisor.triggered.connect(self._on_advisor)
        sched_menu.addAction(self._action_advisor)

        # Help menu
        help_menu = menubar.addMenu("&Help")
        self._action_tour = QAction("Take the &Tour", self)
        self._action_tour.setShortcut(QKeySequence("F1"))
        self._action_tour.triggered.connect(self._on_show_tour)
        help_menu.addAction(self._action_tour)

        help_menu.addSeparator()

        self._action_about = QAction("&About Rask", self)
        self._action_about.triggered.connect(self._on_about)
        help_menu.addAction(self._action_about)

    def _build_content(self) -> None:
        # Tab widget — Calendar is first (default)
        self._tabs = QTabWidget()
        self._tabs.setTabPosition(QTabWidget.North)
        self._tabs.setStyleSheet(f"""
            QTabWidget::pane {{
                border: 1px solid {Palette.BORDER_SUBTLE};
                border-radius: 4px;
                top: -1px;
                background: {Palette.BG_PRIMARY};
            }}
            QTabBar::tab {{
                background: {Palette.BG_SECONDARY};
                color: {Palette.TEXT_SECONDARY};
                padding: 10px 22px;
                border: 1px solid {Palette.BORDER_SUBTLE};
                border-bottom: none;
                border-top-left-radius: 4px;
                border-top-right-radius: 4px;
                margin-right: 2px;
                font-size: 12px;
                font-weight: bold;
                letter-spacing: 1px;
                text-transform: uppercase;
                min-width: 120px;
            }}
            QTabBar::tab:selected {{
                background: {Palette.BG_PRIMARY};
                color: {Palette.GOLD_BRIGHT};
                border-color: {Palette.BORDER_GOLD};
                border-bottom: 2px solid {Palette.GOLD_PRIMARY};
            }}
            QTabBar::tab:hover:!selected {{
                background: {Palette.BG_TERTIARY};
                color: {Palette.TEXT_PRIMARY};
            }}
        """)

        # ---- Tab 0: Dashboard ----
        self.dashboard_view = DashboardView(
            self.calendar_store, self.journal_store, self.project
        )
        self.dashboard_view.calendarTabRequested.connect(lambda: self._switch_tab(1))
        self.dashboard_view.plannerTabRequested.connect(lambda: self._switch_tab(2))
        self.dashboard_view.newEventRequested.connect(self._on_new_event)
        dash_container = QWidget()
        dash_layout = QVBoxLayout(dash_container)
        dash_layout.setContentsMargins(0, 0, 0, 0)
        dash_layout.addWidget(self.dashboard_view)
        self._tabs.addTab(dash_container, "🏠  Home")

        # ---- Tab 1: Calendar ----
        self.calendar_view = CalendarView(self.calendar_store, ai_service=self.ai_service)
        cal_container = QWidget()
        cal_layout = QVBoxLayout(cal_container)
        cal_layout.setContentsMargins(0, 0, 0, 0)
        cal_layout.addWidget(self.calendar_view)
        self._tabs.addTab(cal_container, "📅  Calendar")

        # ---- Tab 2: AI Planner + Tasks
        # The AI Planner view holds the route workspace + chat. The Tasks
        # graph view is embedded as a mode-switchable workspace within the
        # same tab — the user can switch between "AI Planner" and "Tasks"
        # using a toolbar at the top of the tab.
        self._build_planner_tasks_tab()

        # ---- Tab 3: Graphs ----
        self.graphs_view = GraphsView(self.journal_store)
        self.graphs_view.routeSelected.connect(self._on_graphs_route_selected)
        graphs_container = QWidget()
        graphs_layout = QVBoxLayout(graphs_container)
        graphs_layout.setContentsMargins(0, 0, 0, 0)
        graphs_layout.addWidget(self.graphs_view)
        self._tabs.addTab(graphs_container, "📊  Graphs")

        # ---- Tab 4: Simulation ----
        self.simulation_view = SimulationView()
        sim_container = QWidget()
        sim_layout = QVBoxLayout(sim_container)
        sim_layout.setContentsMargins(0, 0, 0, 0)
        sim_layout.addWidget(self.simulation_view)
        self._tabs.addTab(sim_container, "🧪  Simulation")

        # ---- Tab 5: Journal ----
        self.journal_view = JournalView(self.journal_store)
        journal_container = QWidget()
        journal_layout = QVBoxLayout(journal_container)
        journal_layout.setContentsMargins(0, 0, 0, 0)
        journal_layout.addWidget(self.journal_view)
        self._tabs.addTab(journal_container, "📖  Journal")

    def _build_planner_tasks_tab(self) -> None:
        """Build the UNIFIED AI Planner + Tasks tab.

        No more separate Tasks workspace. The AIPlannerView now contains
        the UnifiedGraphView which holds BOTH AI route nodes AND Tasks nodes
        on the same canvas.
        """
        container = QWidget()
        layout = QVBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # Single unified workspace (no mode switcher)
        self.ai_planner_view = AIPlannerView(
            self.ai_service, self.journal_store, self.calendar_store, self.project
        )
        layout.addWidget(self.ai_planner_view)

        self._tabs.addTab(container, "✦  Planner & Tasks")

    def _mode_button_style(self, active: bool) -> str:
        """Kept for backward compat — no longer used."""
        return ""

    def _switch_workspace(self, mode: str) -> None:
        """Kept for backward compat — no longer used."""
        pass

    def _build_tasks_workspace(self) -> None:
        """Kept for backward compat — no longer used."""
        pass

    def _build_statusbar(self) -> None:
        self.statusbar = StatusBar(self)
        self.setStatusBar(self.statusbar)
        today = ShamsiDate.today()
        self.statusbar.update_project_named(
            f"  ◆  RASK   •   {today.format('d MMMM yyyy')}  •  {today.weekday_fa}"
        )
        self._refresh_statusbar()

    def _refresh_statusbar(self) -> None:
        # Show counts
        cal_count = self.calendar_store.event_count
        task_count = self.project.task_count
        journal_count = len(self.journal_store)
        ai_status = "● AI ready" if self.ai_service.is_configured else "○ AI not configured"
        self.statusbar.show_message(
            f"{cal_count} events · {task_count} tasks · {journal_count} journal entries   |   {ai_status}",
            0,
        )

    # ---- Tab switching ----
    def _switch_tab(self, idx: int) -> None:
        if 0 <= idx < self._tabs.count():
            self._tabs.setCurrentIndex(idx)

    # ---- Project events ----
    def _on_project_event(self, event: DomainEvent) -> None:
        QTimer.singleShot(0, self._refresh_enterprise)

    def _on_calendar_store_event(self, event) -> None:
        QTimer.singleShot(0, self._refresh_statusbar)
        # Persist deletions immediately so they don't "come back" on restart
        if isinstance(event, (EventRemoved, CalendarRemoved)):
            self._persist_calendar()
        else:
            # For additions/updates, use a delayed save to batch rapid changes
            QTimer.singleShot(1000, self._autosave)

    def _on_undo_stack_changed(self) -> None:
        self._action_undo.setEnabled(self.undo_stack.can_undo())
        self._action_redo.setEnabled(self.undo_stack.can_redo())

    def _refresh_enterprise(self) -> None:
        # Refresh the unified graph view (sync tasks)
        if hasattr(self, "ai_planner_view") and hasattr(self.ai_planner_view, "graph_view"):
            self.ai_planner_view.graph_view._sync_tasks_to_canvas()
        self._refresh_statusbar()

    def _get_selected_task(self) -> Optional[Task]:
        # No longer used — selection is handled by the unified graph view
        return None

    # ---- Cross-tab interactions ----
    def _on_journal_entry_selected(self, entry) -> None:
        """Load a journal entry's route into the AI planner view."""
        if entry.route is not None:
            self._switch_tab(2)  # Planner & Tasks tab
            self.ai_planner_view.set_route(entry.route)
            # Also update graphs and simulation views
            self.graphs_view.set_route(entry.route)
            self.simulation_view.set_route(entry.route)
            self.statusbar.show_message(
                f"Loaded route from {entry.timestamp[:10]} into AI Planner", 3000
            )

    def _on_graphs_route_selected(self, route: Route) -> None:
        """When a route is selected in the Graphs view, also update Simulation."""
        self.simulation_view.set_route(route)

    def _on_planner_route_updated(self, route: Route) -> None:
        """When AI Planner generates/updates a route, sync Graphs and Simulation views."""
        self.graphs_view.set_route(route)
        self.simulation_view.set_route(route)

    # ---- Actions ----
    def _on_new_event(self) -> None:
        self._switch_tab(1)  # Calendar tab
        dlg = EventEditorDialog(None, self.calendar_store, self)
        if dlg.exec():
            pass

    def _on_new_task(self) -> None:
        self._switch_tab(2)  # Planner & Tasks tab
        if hasattr(self, "ai_planner_view") and hasattr(self.ai_planner_view, "graph_view"):
            self.ai_planner_view.graph_view._on_add_task()

    def _on_save(self) -> None:
        self.repository.save_snapshot(self.project, kind="manual")
        self.calendar_repository.save(self.calendar_store, kind="manual")
        self.statusbar.show_message("All data saved", 3000)

    def _on_ai_settings(self) -> None:
        dlg = AISettingsDialog(self.ai_service, self)
        dlg.exec()
        self._refresh_statusbar()

    def _on_manage_calendars(self) -> None:
        dlg = CalendarSettingsDialog(self.calendar_store, self)
        dlg.exec()

    def _on_export(self, fmt: str) -> None:
        path, _ = QFileDialog.getSaveFileName(
            self, f"Export {fmt.upper()}",
            f"{self.project.name}.{fmt}",
            f"{fmt.upper()} files (*.{fmt});;All files (*)"
        )
        if not path:
            return
        try:
            if fmt == "json":
                self.export_service.to_json(path)
            self.statusbar.show_message(f"Exported → {path}", 4000)
        except Exception as e:
            QMessageBox.warning(self, "Export Failed", str(e))

    def _on_export_calendar(self) -> None:
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

    def _on_undo(self) -> None:
        if self.undo_stack.undo(self.project):
            self._recalculate()

    def _on_redo(self) -> None:
        if self.undo_stack.redo(self.project):
            self._recalculate()

    def _on_advisor(self) -> None:
        dlg = AdvisorDialog(self.project, self)
        dlg.exec()

    def _on_about(self) -> None:
        QMessageBox.about(
            self,
            "About Rask",
            "<h3>Rask</h3>"
            "<p>Rask is a unified planning workspace combining:</p>"
            "<ul>"
            "<li><b>Calendar</b> — Google-Calendar-style planner with Persian "
            "Shamsi dates, multiple calendars, recurring events, and natural-"
            "language input.</li>"
            "<li><b>AI Planner</b> — describe a goal in plain language and "
            "the AI (z.ai GLM-4.5-flash) builds a walkable route of "
            "interconnected steps with success probabilities, fallbacks, and "
            "time estimates.</li>"
            "<li><b>Journal</b> — every AI-generated route is saved for "
            "later review.</li>"
            "<li><b>Tasks</b> — the Enterprise node-graph task operating "
            "system with Critical Path Method, PERT, and Monte Carlo "
            "simulation.</li>"
            "</ul>"
            "<p style='color:#D4AF37'><b>Version 3.0</b></p>"
        )

    # ---- Enterprise-side helpers ----
    def _on_sidebar_double_clicked(self, task_id_str: str) -> None:
        # No longer used — sidebar was removed
        pass

    def _on_task_double_clicked(self, task_id_str: str) -> None:
        # No longer used — handled by unified graph view
        pass

    def _recalculate(self) -> None:
        result = self.scheduling.recalculate()
        if not result.ok and result.cycle_error:
            self.statusbar.show_message(
                f"⚠  Cycle: {result.cycle_error}", 8000
            )
        self._refresh_enterprise()

    # ---- Tour ----
    def _maybe_show_tour(self) -> None:
        import json
        from pathlib import Path
        seen_path = Path.home() / ".rask" / "tour_seen_rask.json"
        if not seen_path.exists():
            self._on_show_tour()
            try:
                seen_path.parent.mkdir(parents=True, exist_ok=True)
                seen_path.write_text(json.dumps({"seen": True}), encoding="utf-8")
            except Exception:
                pass

    def _on_show_tour(self) -> None:
        # Use the Enterprise tour as a base; the unified tour is similar
        start_tour(self, plan="enterprise")

    # ---- Autosave ----
    def _autosave(self) -> None:
        try:
            self.calendar_repository.save(self.calendar_store, kind="autosave")
        except Exception:
            pass

    def _persist_calendar(self) -> None:
        """Immediately persist the calendar store (used after deletions)."""
        try:
            self.calendar_repository.save(self.calendar_store, kind="manual")
        except Exception:
            pass

    # ---- Close ----
    def closeEvent(self, event) -> None:
        try:
            self.repository.save_snapshot(self.project, kind="autosave")
            self.calendar_repository.save(self.calendar_store, kind="autosave")
        except Exception:
            pass
        super().closeEvent(event)
