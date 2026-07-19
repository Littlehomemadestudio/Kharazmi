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
from ..ai import AIService, JournalStore
from ..commands import UndoStack
from ..services import TaskService, SchedulingService, ExportService
from ..persistence import SQLiteRepository, CalendarRepository
from .theme import Palette, QSS, build_qpalette, default_font
from .icons import get_icon
from .views import (
    GoogleCalendarView, AIPlannerView, JournalView,
    NodeGraphView, GanttView, KanbanView, TimelineView, StatisticsView,
)
from .widgets import (
    MainToolbar, StatusBar, InspectorPanel, ConsolePanel,
    CommandPaletteDialog, PaletteItem, MinimapOverlay,
    start_tour, TourOverlay,
)
from .dialogs import (
    TaskEditorDialog, ProjectSettingsDialog, AdvisorDialog,
    EventEditorDialog, CalendarSettingsDialog, AISettingsDialog,
)


class RaskMainWindow(QMainWindow):
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
        self.setWindowTitle("Rask — Calendar · AI Planner · Tasks")
        self.resize(1600, 1000)
        self.setMinimumSize(1100, 700)

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

        # ---- Build UI ----
        self._build_menu()
        self._build_content()
        self._build_statusbar()

        # ---- Subscribe to events ----
        self.project.subscribe(self._on_project_event)
        self.calendar_store.subscribe(self._on_calendar_store_event)
        self.undo_stack.subscribe(self._on_undo_stack_changed)

        # ---- Wire cross-tab interactions ----
        self.journal_view.entrySelected.connect(self._on_journal_entry_selected)

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
        self._action_tab_calendar = QAction("Go to &Calendar", self)
        self._action_tab_calendar.setShortcut(QKeySequence("Ctrl+1"))
        self._action_tab_calendar.triggered.connect(lambda: self._switch_tab(0))
        view_menu.addAction(self._action_tab_calendar)

        self._action_tab_ai = QAction("Go to &AI Planner", self)
        self._action_tab_ai.setShortcut(QKeySequence("Ctrl+2"))
        self._action_tab_ai.triggered.connect(lambda: self._switch_tab_and_workspace(1, "ai"))
        view_menu.addAction(self._action_tab_ai)

        self._action_tab_journal = QAction("Go to &Journal", self)
        self._action_tab_journal.setShortcut(QKeySequence("Ctrl+3"))
        self._action_tab_journal.triggered.connect(lambda: self._switch_tab(2))
        view_menu.addAction(self._action_tab_journal)

        self._action_tab_tasks = QAction("Go to &Tasks (Enterprise)", self)
        self._action_tab_tasks.setShortcut(QKeySequence("Ctrl+4"))
        self._action_tab_tasks.triggered.connect(lambda: self._switch_tab_and_workspace(1, "tasks"))
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

        # ---- Tab 1: Calendar ----
        self.calendar_view = GoogleCalendarView(self.calendar_store)
        cal_container = QWidget()
        cal_layout = QVBoxLayout(cal_container)
        cal_layout.setContentsMargins(0, 0, 0, 0)
        cal_layout.addWidget(self.calendar_view)
        self._tabs.addTab(cal_container, "📅  Calendar")

        # ---- Tab 2: AI Planner + Tasks (MERGED into one workspace) ----
        # The AI Planner view holds the route workspace + chat. The Tasks
        # graph view is embedded as a mode-switchable workspace within the
        # same tab — the user can switch between "AI Planner" and "Tasks"
        # using a toolbar at the top of the tab.
        self._build_planner_tasks_tab()

        # ---- Tab 3: Journal ----
        self.journal_view = JournalView(self.journal_store)
        journal_container = QWidget()
        journal_layout = QVBoxLayout(journal_container)
        journal_layout.setContentsMargins(0, 0, 0, 0)
        journal_layout.addWidget(self.journal_view)
        self._tabs.addTab(journal_container, "📖  Journal")

        self.setCentralWidget(self._tabs)

    def _build_planner_tasks_tab(self) -> None:
        """Build the merged AI Planner + Tasks tab.

        The tab has a top mode-switcher (AI Planner / Tasks) that toggles
        between two stacked workspaces sharing the same window.
        """
        container = QWidget()
        layout = QVBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # Mode switcher bar at the top
        mode_bar = QFrame()
        mode_bar.setFixedHeight(40)
        mode_bar.setStyleSheet(
            f"background-color: {Palette.BG_SECONDARY}; "
            f"border-bottom: 1px solid {Palette.BORDER_SUBTLE};"
        )
        mode_layout = QHBoxLayout(mode_bar)
        mode_layout.setContentsMargins(12, 4, 12, 4)
        mode_layout.setSpacing(6)

        mode_label = QLabel("WORKSPACE:")
        mode_label.setStyleSheet(
            f"color: {Palette.TEXT_TERTIARY}; font-size: 10px; "
            f"font-weight: bold; letter-spacing: 1.5px;"
        )
        mode_layout.addWidget(mode_label)

        from PySide6.QtWidgets import QButtonGroup, QToolButton
        self._mode_group = QButtonGroup(self)
        self._mode_group.setExclusive(True)

        ai_btn = QToolButton()
        ai_btn.setText("✦  AI Planner")
        ai_btn.setCheckable(True)
        ai_btn.setChecked(True)
        ai_btn.setStyleSheet(self._mode_button_style(True))
        ai_btn.clicked.connect(lambda: self._switch_workspace("ai"))
        self._mode_group.addButton(ai_btn)
        mode_layout.addWidget(ai_btn)

        tasks_btn = QToolButton()
        tasks_btn.setText("◆  Tasks")
        tasks_btn.setCheckable(True)
        tasks_btn.setStyleSheet(self._mode_button_style(False))
        tasks_btn.clicked.connect(lambda: self._switch_workspace("tasks"))
        self._mode_group.addButton(tasks_btn)
        mode_layout.addWidget(tasks_btn)

        mode_layout.addStretch()

        # Right-side: small Enterprise toolbar (undo/redo/recalc/layout)
        from .widgets import MainToolbar
        # We'll use menu actions instead of a full toolbar for simplicity
        # But add quick buttons for the most-used Enterprise actions
        self._tasks_recalc_btn = QToolButton()
        self._tasks_recalc_btn.setText("▶  Recalc")
        self._tasks_recalc_btn.setStyleSheet(f"""
            QToolButton {{
                background-color: transparent;
                color: {Palette.TEXT_SECONDARY};
                border: 1px solid {Palette.BORDER_NORMAL};
                border-radius: 3px;
                padding: 4px 10px;
                font-size: 11px;
            }}
            QToolButton:hover {{
                border: 1px solid {Palette.GOLD_PRIMARY};
                color: {Palette.GOLD_BRIGHT};
            }}
        """)
        self._tasks_recalc_btn.clicked.connect(self._recalculate)
        mode_layout.addWidget(self._tasks_recalc_btn)

        layout.addWidget(mode_bar)

        # Stacked widget with both workspaces
        from PySide6.QtWidgets import QStackedWidget
        self._workspace_stack = QStackedWidget()

        # Workspace 1: AI Planner
        self.ai_planner_view = AIPlannerView(self.ai_service, self.journal_store, self.calendar_store)
        self._workspace_stack.addWidget(self.ai_planner_view)

        # Workspace 2: Tasks (Enterprise)
        self._build_tasks_workspace()

        layout.addWidget(self._workspace_stack, stretch=1)

        self._tabs.addTab(container, "✦  Planner & Tasks")

    def _mode_button_style(self, active: bool) -> str:
        if active:
            return f"""
                QToolButton {{
                    background-color: {Palette.BG_SELECTED};
                    color: {Palette.GOLD_BRIGHT};
                    border: 1px solid {Palette.BORDER_GOLD};
                    border-radius: 3px;
                    padding: 4px 12px;
                    font-size: 11px;
                    font-weight: bold;
                }}
            """
        return f"""
            QToolButton {{
                background-color: transparent;
                color: {Palette.TEXT_SECONDARY};
                border: 1px solid {Palette.BORDER_NORMAL};
                border-radius: 3px;
                padding: 4px 12px;
                font-size: 11px;
            }}
            QToolButton:hover {{
                background-color: {Palette.BG_TERTIARY};
                color: {Palette.TEXT_PRIMARY};
            }}
        """

    def _switch_workspace(self, mode: str) -> None:
        """Switch between AI Planner and Tasks workspaces."""
        if mode == "ai":
            self._workspace_stack.setCurrentIndex(0)
        elif mode == "tasks":
            self._workspace_stack.setCurrentIndex(1)
        # Update button styles
        for i, btn in enumerate(self._mode_group.buttons()):
            btn.setStyleSheet(self._mode_button_style(btn.isChecked()))

    def _build_tasks_workspace(self) -> None:
        """Build the Enterprise Tasks workspace (graph + sidebar + inspector)."""
        from .main_window import CentralWidget, SidebarTree
        self.enterprise_central = CentralWidget()
        self.enterprise_sidebar = SidebarTree(self.project)
        self.enterprise_sidebar.setMinimumWidth(220)
        self.enterprise_sidebar.setMaximumWidth(280)
        self.enterprise_sidebar.taskDoubleClicked.connect(self._on_sidebar_double_clicked)
        self.inspector = InspectorPanel(self.project, self.task_service)
        # Build the views
        self._views: dict[str, QWidget] = {
            "graph": NodeGraphView(self.project, self.task_service),
            "gantt": GanttView(self.project, self.task_service),
            "kanban": KanbanView(self.project, self.task_service),
            "timeline": TimelineView(self.project, self.task_service),
            "stats": StatisticsView(self.project, self.task_service, self.scheduling),
        }
        for view in self._views.values():
            if hasattr(view, "taskDoubleClicked"):
                view.taskDoubleClicked.connect(self._on_task_double_clicked)
        # Console
        self.console = ConsolePanel(
            self.project, self.task_service, self.scheduling, self.export_service
        )
        self.console.set_repository(self.repository)
        self.enterprise_central.set_console(self.console)
        # Default to graph view
        self.enterprise_central.set_view(self._views["graph"])

        # Layout: sidebar | central | inspector
        tasks_widget = QWidget()
        layout = QHBoxLayout(tasks_widget)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(self.enterprise_sidebar)
        layout.addWidget(self.enterprise_central, stretch=1)
        layout.addWidget(self.inspector)
        self._workspace_stack.addWidget(tasks_widget)

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

    def _switch_tab_and_workspace(self, tab_idx: int, workspace: str) -> None:
        """Switch to a tab AND a workspace within that tab."""
        if 0 <= tab_idx < self._tabs.count():
            self._tabs.setCurrentIndex(tab_idx)
        # If we have a workspace stack, switch it too
        if hasattr(self, "_workspace_stack"):
            self._switch_workspace(workspace)
            # Update the mode buttons to reflect the new workspace
            if hasattr(self, "_mode_group"):
                target_idx = 0 if workspace == "ai" else 1
                btns = list(self._mode_group.buttons())
                if 0 <= target_idx < len(btns):
                    btns[target_idx].setChecked(True)
                    for btn in btns:
                        btn.setStyleSheet(self._mode_button_style(btn.isChecked()))

    # ---- Project events ----
    def _on_project_event(self, event: DomainEvent) -> None:
        QTimer.singleShot(0, self._refresh_enterprise)

    def _on_calendar_store_event(self, event) -> None:
        QTimer.singleShot(0, self._refresh_statusbar)
        QTimer.singleShot(1000, self._autosave)

    def _on_undo_stack_changed(self) -> None:
        self._action_undo.setEnabled(self.undo_stack.can_undo())
        self._action_redo.setEnabled(self.undo_stack.can_redo())

    def _refresh_enterprise(self) -> None:
        # Refresh sidebar + current view + inspector
        if hasattr(self, "enterprise_sidebar"):
            self.enterprise_sidebar.refresh()
        if hasattr(self, "inspector"):
            self.inspector.load_task(self._get_selected_task())
        # Refresh current enterprise view
        # (the central widget holds the active view)
        self._refresh_statusbar()

    def _get_selected_task(self) -> Optional[Task]:
        graph_view = self._views.get("graph")
        if isinstance(graph_view, NodeGraphView):
            for item in graph_view._scene.selectedItems():
                if hasattr(item, "task"):
                    return item.task
        return None

    # ---- Cross-tab interactions ----
    def _on_journal_entry_selected(self, entry) -> None:
        """Load a journal entry's route into the AI planner view."""
        if entry.route is not None:
            self._switch_tab_and_workspace(1, "ai")  # Planner & Tasks tab, AI workspace
            self.ai_planner_view.set_route(entry.route)
            self.statusbar.show_message(
                f"Loaded route from {entry.timestamp[:10]} into AI Planner", 3000
            )

    # ---- Actions ----
    def _on_new_event(self) -> None:
        self._switch_tab(0)
        dlg = EventEditorDialog(None, self.calendar_store, self)
        if dlg.exec():
            pass

    def _on_new_task(self) -> None:
        self._switch_tab_and_workspace(1, "tasks")
        dlg = TaskEditorDialog(None, self.task_service, self)
        if dlg.exec():
            self._recalculate()

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
        self._switch_tab_and_workspace(1, "tasks")
        graph_view = self._views["graph"]
        if isinstance(graph_view, NodeGraphView):
            node = graph_view._node_items.get(task_id_str)
            if node is not None:
                graph_view._scene.clearSelection()
                node.setSelected(True)
                graph_view.centerOn(node)

    def _on_task_double_clicked(self, task_id_str: str) -> None:
        task = self.project.get_task(TaskId(task_id_str))
        if task is None:
            return
        dlg = TaskEditorDialog(task, self.task_service, self)
        if dlg.exec():
            self._recalculate()

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

    # ---- Close ----
    def closeEvent(self, event) -> None:
        try:
            self.repository.save_snapshot(self.project, kind="autosave")
            self.calendar_repository.save(self.calendar_store, kind="autosave")
        except Exception:
            pass
        super().closeEvent(event)
