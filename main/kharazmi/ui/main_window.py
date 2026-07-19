"""
MainWindow — the top-level window that ties everything together.

Layout:
  ┌────────────────────────────────────────────────────────────┐
  │ MenuBar                                                     │
  ├────────────────────────────────────────────────────────────┤
  │ MainToolbar                                                 │
  ├──────────┬──────────────────────────────────┬──────────────┤
  │ Sidebar  │  Central widget (current view)    │  Inspector   │
  │ (tree)   │  + Console (bottom, collapsible)  │  Panel       │
  │          │                                   │              │
  ├──────────┴───────────────────────────────────┴──────────────┤
  │ StatusBar                                                   │
  └────────────────────────────────────────────────────────────┘
"""
from __future__ import annotations

from datetime import datetime
from typing import Optional

from PySide6.QtCore import Qt, Signal, QTimer, QEvent, QSize
from PySide6.QtGui import (
    QAction, QKeySequence, QShortcut, QCloseEvent, QIcon,
)
from PySide6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QSplitter, QFrame,
    QDockWidget, QTreeWidget, QTreeWidgetItem, QLabel, QMenu,
    QFileDialog, QMessageBox, QApplication, QSizePolicy, QToolButton,
    QAbstractItemView, QHeaderView, QPushButton,
)

from ..core import (
    Project, Task, TaskId, DependencyType, ViewKind, TaskStatus,
    DomainEvent, TaskCreated, TaskDeleted, TaskUpdated, TaskStatusChanged,
    DependencyAdded, DependencyRemoved, ScheduleRecalculated, CycleDetected,
    ShamsiDate, format_shamsi, to_persian_digits,
)
from ..commands import UndoStack
from ..services import (
    TaskService, SchedulingService, LocalAdvisor, ExportService,
)
from ..persistence import SQLiteRepository
from .theme import Palette, QSS, build_qpalette, default_font
from .icons import get_icon
from .widgets import (
    MainToolbar, StatusBar, InspectorPanel, ConsolePanel,
    CommandPaletteDialog, PaletteItem, MinimapOverlay,
    start_tour, TourOverlay,
)
from .views import (
    NodeGraphView, GanttView, KanbanView, TimelineView, StatisticsView,
)
from .dialogs import (
    TaskEditorDialog, ProjectSettingsDialog, AdvisorDialog,
    PlanSelectionDialog, load_saved_plan, save_plan,
)


class SidebarTree(QTreeWidget):
    """Left sidebar: project outline."""
    taskDoubleClicked = Signal(str)

    def __init__(self, project: Project, parent: QWidget = None) -> None:
        super().__init__(parent)
        self.project = project
        self.setHeaderHidden(True)
        self.setSelectionMode(QAbstractItemView.SingleSelection)
        self.setStyleSheet(f"""
            QTreeWidget {{
                background-color: {Palette.BG_SECONDARY};
                border: none;
                border-right: 1px solid {Palette.BORDER_SUBTLE};
                outline: 0;
            }}
            QTreeWidget::item {{
                padding: 6px 8px;
            }}
        """)
        self.itemDoubleClicked.connect(self._on_double_clicked)

    def _on_double_clicked(self, item: QTreeWidgetItem, column: int) -> None:
        tid = item.data(0, Qt.UserRole)
        if tid:
            self.taskDoubleClicked.emit(tid)

    def refresh(self) -> None:
        self.clear()

        # Project root
        root = QTreeWidgetItem(self, [f"◆  {self.project.name}"])
        root.setForeground(0, self._gold())
        f = root.font(0)
        f.setBold(True)
        root.setFont(0, f)
        self.expandItem(root)

        # Group tasks by status
        by_status: dict[TaskStatus, list[Task]] = {}
        for t in self.project.tasks():
            by_status.setdefault(t.status, []).append(t)

        for status in TaskStatus:
            tasks = by_status.get(status, [])
            if not tasks:
                continue
            status_node = QTreeWidgetItem(root, [
                f"  {status.value.upper()}  ({len(tasks)})"
            ])
            status_node.setForeground(0, self._text_secondary())
            f = status_node.font(0)
            f.setBold(True)
            f.setCapitalization(QFont.AllUppercase if False else QFont.MixedCase)  # type: ignore[name-defined]
            status_node.setFont(0, f)
            self.expandItem(status_node)

            for t in sorted(tasks, key=lambda x: x.title.lower()):
                icon = "★" if t.is_critical else "•"
                label = f"    {icon}  {t.title}"
                task_node = QTreeWidgetItem(status_node, [label])
                task_node.setData(0, Qt.UserRole, str(t.id))
                if t.is_critical:
                    task_node.setForeground(0, self._gold_bright())
                    f = task_node.font(0)
                    f.setBold(True)
                    task_node.setFont(0, f)
                else:
                    task_node.setForeground(0, self._text_primary())
        self.expandItem(root)

    def _gold(self):
        from PySide6.QtGui import QColor
        return QColor(Palette.GOLD_PRIMARY)

    def _gold_bright(self):
        from PySide6.QtGui import QColor
        return QColor(Palette.GOLD_BRIGHT)

    def _text_primary(self):
        from PySide6.QtGui import QColor
        return QColor(Palette.TEXT_PRIMARY)

    def _text_secondary(self):
        from PySide6.QtGui import QColor
        return QColor(Palette.TEXT_TERTIARY)


from PySide6.QtGui import QFont


class CentralWidget(QFrame):
    """Container for the current view + console below."""

    def __init__(self, parent: QWidget = None) -> None:
        super().__init__(parent)
        self.setObjectName("centralWidget")
        self.setStyleSheet(f"QFrame#centralWidget {{ background-color: {Palette.BG_PRIMARY}; }}")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self._splitter = QSplitter(Qt.Vertical, self)
        self._splitter.setHandleWidth(2)
        self._splitter.setStyleSheet("QSplitter::handle { background: #08080A; }")

        # View container
        self._view_container = QFrame()
        self._view_container.setStyleSheet(f"background-color: {Palette.BG_PRIMARY};")
        self._view_layout = QVBoxLayout(self._view_container)
        self._view_layout.setContentsMargins(0, 0, 0, 0)
        self._view_layout.setSpacing(0)
        self._splitter.addWidget(self._view_container)

        # Console
        self._console: Optional[ConsolePanel] = None
        self._console_visible = True

        self._splitter.setSizes([600, 200])
        layout.addWidget(self._splitter)

    def set_view(self, widget: QWidget) -> None:
        # Clear old
        while self._view_layout.count():
            item = self._view_layout.takeAt(0)
            if item.widget():
                item.widget().setParent(None)
        self._view_layout.addWidget(widget)

    def set_console(self, console: ConsolePanel) -> None:
        if self._console is not None:
            self._splitter.removeWidget(self._console)
        self._console = console
        self._splitter.addWidget(console)

    def toggle_console(self) -> None:
        if self._console is None:
            return
        self._console_visible = not self._console_visible
        self._console.setVisible(self._console_visible)

    def show_console(self) -> None:
        if self._console is not None and not self._console_visible:
            self.toggle_console()


class MainWindow(QMainWindow):
    """The application's main window."""

    def __init__(self, project: Optional[Project] = None) -> None:
        super().__init__()
        self.project = project or Project(name="Untitled Project")
        self.undo_stack = UndoStack()
        self.scheduling = SchedulingService(self.project)
        self.task_service = TaskService(self.project, self.undo_stack, self.scheduling)
        self.export_service = ExportService(self.project)
        self.repository = SQLiteRepository()

        self.setWindowTitle("Rask — Task Operating System")
        self.resize(1600, 1000)
        self.setMinimumSize(1200, 750)

        # Apply theme
        self.setStyleSheet(QSS)
        self.setPalette(build_qpalette())
        self.setFont(default_font())

        # Set window icon (gold dot)
        from PySide6.QtGui import QPixmap, QPainter, QColor, QBrush
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
        self._build_toolbar()
        self._build_central()
        self._build_sidebar()
        self._build_inspector()
        self._build_statusbar()
        self._build_minimap()

        # Views registry
        self._views: dict[str, QWidget] = {}
        self._current_view_kind: ViewKind = ViewKind.GRAPH
        self._build_views()

        # Subscribe to project events
        self.project.subscribe(self._on_project_event)

        # Connect undo stack
        self.undo_stack.subscribe(self._on_undo_stack_changed)

        # Wire toolbar signals
        self._wire_toolbar()

        # Initial state
        self._refresh_all()
        self._switch_view(ViewKind.GRAPH)

        # Auto-recalc on startup
        QTimer.singleShot(100, self._recalculate)
        # Show tour on first run
        QTimer.singleShot(600, self._maybe_show_tour)

    # ---- Building UI ----
    def _build_menu(self) -> None:
        menubar = self.menuBar()

        # File menu
        file_menu = menubar.addMenu("&File")
        self._action_new_task = QAction(get_icon("plus"), "&New Task", self)
        self._action_new_task.setShortcut(QKeySequence("N"))
        self._action_new_task.triggered.connect(self._on_new_task)
        file_menu.addAction(self._action_new_task)

        file_menu.addSeparator()

        self._action_save = QAction(get_icon("save"), "&Save Snapshot", self)
        self._action_save.setShortcut(QKeySequence.Save)
        self._action_save.triggered.connect(self._on_save)
        file_menu.addAction(self._action_save)

        self._action_open = QAction(get_icon("open"), "&Open Project...", self)
        self._action_open.setShortcut(QKeySequence.Open)
        self._action_open.triggered.connect(self._on_open)
        file_menu.addAction(self._action_open)

        file_menu.addSeparator()

        self._action_export_json = QAction("Export &JSON...", self)
        self._action_export_json.triggered.connect(lambda: self._on_export("json"))
        file_menu.addAction(self._action_export_json)

        self._action_export_csv = QAction("Export &CSV...", self)
        self._action_export_csv.triggered.connect(lambda: self._on_export("csv"))
        file_menu.addAction(self._action_export_csv)

        self._action_export_mermaid = QAction("Export &Mermaid...", self)
        self._action_export_mermaid.triggered.connect(lambda: self._on_export("mermaid"))
        file_menu.addAction(self._action_export_mermaid)

        file_menu.addSeparator()

        self._action_settings = QAction(get_icon("settings"), "Project &Settings...", self)
        self._action_settings.triggered.connect(self._on_project_settings)
        file_menu.addAction(self._action_settings)

        file_menu.addSeparator()

        self._action_switch_plan = QAction("&Switch to Basic Plan...", self)
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

        edit_menu.addSeparator()

        self._action_delete = QAction(get_icon("trash"), "&Delete Selected", self)
        self._action_delete.setShortcut(QKeySequence.Delete)
        self._action_delete.triggered.connect(self._on_delete)
        edit_menu.addAction(self._action_delete)

        # Schedule menu
        sched_menu = menubar.addMenu("&Schedule")
        self._action_recalc = QAction(get_icon("play"), "&Recalculate CPM", self)
        self._action_recalc.setShortcut(QKeySequence("Ctrl+R"))
        self._action_recalc.triggered.connect(self._recalculate)
        sched_menu.addAction(self._action_recalc)

        self._action_layout = QAction(get_icon("graph"), "Auto &Layout", self)
        self._action_layout.setShortcut(QKeySequence("Ctrl+L"))
        self._action_layout.triggered.connect(self._on_layout)
        sched_menu.addAction(self._action_layout)

        self._action_mc = QAction(get_icon("stats"), "Run &Monte Carlo", self)
        self._action_mc.triggered.connect(self._on_monte_carlo)
        sched_menu.addAction(self._action_mc)

        self._action_advisor = QAction(get_icon("warning"), "&Advisor Report", self)
        self._action_advisor.triggered.connect(self._on_advisor)
        sched_menu.addAction(self._action_advisor)

        # View menu
        view_menu = menubar.addMenu("&View")
        for kind in ViewKind:
            action = QAction(kind.value.capitalize(), self)
            action.triggered.connect(lambda _=False, k=kind: self._switch_view(k))
            view_menu.addAction(action)

        view_menu.addSeparator()
        self._action_toggle_console = QAction("Toggle &Console", self)
        self._action_toggle_console.setShortcut(QKeySequence("`"))
        self._action_toggle_console.triggered.connect(self._toggle_console)
        view_menu.addAction(self._action_toggle_console)

        # Help menu (no docs per spec, just an about)
        help_menu = menubar.addMenu("&Help")
        self._action_tour = QAction("Take the &Tour", self)
        self._action_tour.setShortcut(QKeySequence("F1"))
        self._action_tour.triggered.connect(self._on_show_tour)
        help_menu.addAction(self._action_tour)

        help_menu.addSeparator()

        self._action_about = QAction("&About Rask", self)
        self._action_about.triggered.connect(self._on_about)
        help_menu.addAction(self._action_about)

    def _build_toolbar(self) -> None:
        self.toolbar = MainToolbar(self)
        self.addToolBar(self.toolbar)

    def _build_central(self) -> None:
        self.central_widget = CentralWidget(self)
        self.setCentralWidget(self.central_widget)

    def _build_sidebar(self) -> None:
        self.sidebar = SidebarTree(self.project, self)
        self.sidebar.setMinimumWidth(220)
        self.sidebar.setMaximumWidth(300)
        self.sidebar.taskDoubleClicked.connect(self._on_sidebar_double_clicked)
        dock = QDockWidget("Outline", self)
        dock.setWidget(self.sidebar)
        dock.setFeatures(QDockWidget.NoDockWidgetFeatures)
        dock.setTitleBarWidget(QWidget())  # hide title bar
        self.addDockWidget(Qt.LeftDockWidgetArea, dock)

    def _build_inspector(self) -> None:
        self.inspector = InspectorPanel(self.project, self.task_service, self)
        dock = QDockWidget("Inspector", self)
        dock.setWidget(self.inspector)
        dock.setFeatures(QDockWidget.NoDockWidgetFeatures)
        dock.setTitleBarWidget(QWidget())
        self.addDockWidget(Qt.RightDockWidgetArea, dock)

    def _build_statusbar(self) -> None:
        self.statusbar = StatusBar(self)
        self.setStatusBar(self.statusbar)

    def _build_minimap(self) -> None:
        # Minimap is overlaid on the graph view itself, not the main window
        pass

    def _build_views(self) -> None:
        self._views[ViewKind.GRAPH.value] = NodeGraphView(self.project, self.task_service)
        self._views[ViewKind.GANTT.value] = GanttView(self.project, self.task_service)
        self._views[ViewKind.KANBAN.value] = KanbanView(self.project, self.task_service)
        self._views[ViewKind.TIMELINE.value] = TimelineView(self.project, self.task_service)
        self._views[ViewKind.STATS.value] = StatisticsView(
            self.project, self.task_service, self.scheduling
        )

        # Connect common signals
        for view in self._views.values():
            if hasattr(view, "taskDoubleClicked"):
                view.taskDoubleClicked.connect(self._on_task_double_clicked)

        # Console
        self.console = ConsolePanel(
            self.project, self.task_service, self.scheduling, self.export_service
        )
        self.console.set_repository(self.repository)
        self.central_widget.set_console(self.console)

        # Minimap overlay on graph view
        graph_view = self._views[ViewKind.GRAPH.value]
        if isinstance(graph_view, NodeGraphView):
            self._minimap = MinimapOverlay(graph_view, graph_view)
            self._minimap.move(20, 20)
            self._minimap.show()
            # Update minimap on viewport changes
            graph_view.horizontalScrollBar().valueChanged.connect(self._minimap.update_minimap)
            graph_view.verticalScrollBar().valueChanged.connect(self._minimap.update_minimap)

    def _wire_toolbar(self) -> None:
        self.toolbar.newTaskRequested.connect(self._on_new_task)
        self.toolbar.deleteRequested.connect(self._on_delete)
        self.toolbar.undoRequested.connect(self._on_undo)
        self.toolbar.redoRequested.connect(self._on_redo)
        self.toolbar.layoutRequested.connect(self._on_layout)
        self.toolbar.scheduleRequested.connect(self._recalculate)
        self.toolbar.monteCarloRequested.connect(self._on_monte_carlo)
        self.toolbar.advisorRequested.connect(self._on_advisor)
        self.toolbar.saveRequested.connect(self._on_save)
        self.toolbar.openRequested.connect(self._on_open)
        self.toolbar.exportRequested.connect(lambda: self._on_export("json"))
        self.toolbar.commandPaletteRequested.connect(self._open_command_palette)
        self.toolbar.viewChanged.connect(lambda v: self._switch_view(ViewKind(v)))

    # ---- View switching ----
    def _switch_view(self, kind: ViewKind) -> None:
        self._current_view_kind = kind
        view = self._views[kind.value]
        self.central_widget.set_view(view)
        self.toolbar.set_active_view(kind.value)
        if hasattr(view, "refresh"):
            view.refresh()
        if kind == ViewKind.GRAPH and isinstance(view, NodeGraphView):
            view.fit_all()
        self.statusbar.show_message(f"Switched to {kind.value} view")

    # ---- Project events ----
    def _on_project_event(self, event: DomainEvent) -> None:
        # Defer UI updates to the next event loop tick so heavy operations
        # don't block the command that triggered them.
        QTimer.singleShot(0, lambda: self._handle_event(event))

    def _handle_event(self, event: DomainEvent) -> None:
        if isinstance(event, CycleDetected):
            self.statusbar.show_message(
                f"⚠  Cycle rejected: {' -> '.join(event.cycle)}", 8000
            )
            return
        if isinstance(event, ScheduleRecalculated):
            self.statusbar.show_message("Schedule recalculated", 2000)
        self._refresh_all()

    def _refresh_all(self) -> None:
        # Refresh sidebar
        self.sidebar.refresh()
        # Refresh current view
        view = self._views.get(self._current_view_kind.value)
        if view is not None and hasattr(view, "refresh"):
            view.refresh()
        # Refresh inspector
        if hasattr(self, "inspector"):
            self.inspector.load_task(self._get_selected_task())
        # Refresh status bar
        self._refresh_statusbar()
        # Refresh minimap
        if hasattr(self, "_minimap"):
            self._minimap.update_minimap()

    def _refresh_statusbar(self) -> None:
        self.statusbar.update_project(self.project)
        stats = self.task_service.statistics()
        self.statusbar.update_stats(
            stats["total"], stats["done"], stats["active"],
            stats["blocked"], stats["critical_count"], stats["completion_pct"],
        )
        cpm = self.scheduling.last_cpm
        if cpm and cpm.ok:
            self.statusbar.update_schedule(
                cpm.project_duration.humanize(), len(cpm.critical_path)
            )
        else:
            self.statusbar.update_schedule("—", 0)

    def _get_selected_task(self) -> Optional[Task]:
        # Try to read the selection from the current view
        view = self._views.get(self._current_view_kind.value)
        if isinstance(view, NodeGraphView):
            selected = view._scene.selectedItems()
            for item in selected:
                if hasattr(item, "task"):
                    return item.task
        return None

    # ---- Undo stack ----
    def _on_undo_stack_changed(self) -> None:
        self.toolbar.update_undo_redo(
            self.undo_stack.can_undo(), self.undo_stack.can_redo(),
            self.undo_stack.next_undo_name() or "",
            self.undo_stack.next_redo_name() or "",
        )
        self._action_undo.setEnabled(self.undo_stack.can_undo())
        self._action_redo.setEnabled(self.undo_stack.can_redo())

    # ---- Actions ----
    def _on_new_task(self) -> None:
        dlg = TaskEditorDialog(None, self.task_service, self)
        if dlg.exec():
            self._recalculate()
            self._refresh_all()

    def _on_delete(self) -> None:
        task = self._get_selected_task()
        if task is None:
            self.statusbar.show_message("No task selected", 2000)
            return
        self.task_service.delete_task(task.id)
        self.inspector.load_task(None)
        self._refresh_all()

    def _on_undo(self) -> None:
        if self.undo_stack.undo(self.project):
            self._recalculate()
            self._refresh_all()

    def _on_redo(self) -> None:
        if self.undo_stack.redo(self.project):
            self._recalculate()
            self._refresh_all()

    def _on_layout(self) -> None:
        view = self._views.get(ViewKind.GRAPH.value)
        if isinstance(view, NodeGraphView):
            view.auto_layout()
            self._refresh_all()

    def _on_monte_carlo(self) -> None:
        self._switch_view(ViewKind.STATS)
        stats_view = self._views[ViewKind.STATS.value]
        if hasattr(stats_view, "_run_monte_carlo"):
            stats_view._run_monte_carlo()

    def _on_advisor(self) -> None:
        dlg = AdvisorDialog(self.project, self)
        dlg.exec()

    def _on_save(self) -> None:
        self.repository.save_snapshot(self.project, kind="manual")
        self.statusbar.show_message(f"Saved '{self.project.name}'", 3000)

    def _on_open(self) -> None:
        # Simple project picker
        projects = self.repository.list_projects()
        if not projects:
            QMessageBox.information(self, "Open Project",
                                    "No saved projects found. Use File > Save first.")
            return
        # Build a tiny dialog
        from PySide6.QtWidgets import QDialog, QVBoxLayout, QListWidget, QPushButton, QHBoxLayout
        dlg = QDialog(self)
        dlg.setWindowTitle("Open Project")
        dlg.setMinimumWidth(400)
        layout = QVBoxLayout(dlg)
        list_widget = QListWidget()
        for p in projects:
            list_widget.addItem(f"{p['name']}  ({p['id']})")
        layout.addWidget(list_widget)
        btn_row = QHBoxLayout()
        open_btn = QPushButton("Open")
        cancel_btn = QPushButton("Cancel")
        btn_row.addWidget(open_btn)
        btn_row.addWidget(cancel_btn)
        layout.addLayout(btn_row)
        open_btn.clicked.connect(dlg.accept)
        cancel_btn.clicked.connect(dlg.reject)

        if dlg.exec() and list_widget.currentRow() >= 0:
            pid = projects[list_widget.currentRow()]["id"]
            proj = self.repository.load_latest(pid)
            if proj is None:
                QMessageBox.warning(self, "Open Project", "Failed to load project.")
                return
            # Replace current project state
            self.project.clear()
            for t in proj.tasks():
                self.project._tasks[t.id.value] = t
            for d in proj.dependencies():
                self.project._deps[d.key] = d
            self.project.name = proj.name
            self.project.description = proj.description
            self._recalculate()
            self._refresh_all()
            self.statusbar.show_message(f"Loaded '{proj.name}'", 3000)

    def _on_export(self, fmt: str) -> None:
        path, _ = QFileDialog.getSaveFileName(
            self, f"Export {fmt.upper()}",
            f"{self.project.name}.{fmt if fmt != 'mermaid' else 'mmd'}",
            f"{fmt.upper()} files (*.{fmt if fmt != 'mermaid' else 'mmd'});;All files (*)"
        )
        if not path:
            return
        try:
            if fmt == "json":
                self.export_service.to_json(path)
            elif fmt == "csv":
                self.export_service.to_csv_tasks(path)
                self.export_service.to_csv_deps(path + ".deps.csv")
            elif fmt == "mermaid":
                self.export_service.to_mermaid(path)
            self.statusbar.show_message(f"Exported {fmt.upper()} → {path}", 4000)
        except Exception as e:
            QMessageBox.warning(self, "Export Failed", str(e))

    def _on_project_settings(self) -> None:
        dlg = ProjectSettingsDialog(self.project, self)
        if dlg.exec():
            self._refresh_all()

    def _on_about(self) -> None:
        QMessageBox.about(
            self,
            "About Rask",
            "<h3>Rask — Task Operating System</h3>"
            "<p>Named after Al-Khwarizmi, the Persian polymath whose name "
            "gave us <i>algorithm</i>.</p>"
            "<p>Rask treats a project as a directed graph of tasks "
            "governed by real scheduling mathematics: Critical Path Method, "
            "PERT, topological ordering, cycle detection, and Monte Carlo "
            "risk analysis.</p>"
            "<p>Dates are shown in the Persian Shamsi (Jalali) calendar.</p>"
            "<p style='color:#D4AF37'><b>Version 2.0 — Enterprise</b></p>"
        )

    def _on_switch_plan(self) -> None:
        """Switch from Enterprise down to the Basic plan."""
        ret = QMessageBox.question(
            self, "Switch Plan",
            "Switch to the Basic plan?\n\n"
            "Basic is a full Google-Calendar-style experience: multiple "
            "calendars, events with recurrence and reminders, day/week/"
            "month/year/schedule views, drag-and-drop, natural-language "
            "input, and Persian Shamsi dates.\n\n"
            "The node graph, Gantt, Kanban, console, and statistics views "
            "will be hidden. Your tasks are preserved. You can switch "
            "back anytime via File → Switch Plan.",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if ret == QMessageBox.Yes:
            save_plan("basic")
            QMessageBox.information(
                self, "Restart Required",
                "Plan changed to Basic. Please restart Rask to "
                "enter the calendar mode."
            )
            self.close()

    def _on_show_tour(self) -> None:
        """Show the guided tour."""
        start_tour(self, plan="enterprise")

    def _maybe_show_tour(self) -> None:
        """Show the tour on first run only."""
        import json
        from pathlib import Path
        seen_path = Path.home() / ".rask" / "tour_seen_enterprise.json"
        if not seen_path.exists():
            self._on_show_tour()
            try:
                seen_path.parent.mkdir(parents=True, exist_ok=True)
                seen_path.write_text(json.dumps({"seen": True}), encoding="utf-8")
            except Exception:
                pass

    def _on_sidebar_double_clicked(self, task_id_str: str) -> None:
        # Switch to graph view and select the task
        self._switch_view(ViewKind.GRAPH)
        graph_view = self._views[ViewKind.GRAPH.value]
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
            self._refresh_all()

    def _recalculate(self) -> None:
        result = self.scheduling.recalculate()
        if not result.ok and result.cycle_error:
            self.statusbar.show_message(
                f"⚠  Cycle: {result.cycle_error}", 8000
            )
        self._refresh_all()

    def _toggle_console(self) -> None:
        self.central_widget.toggle_console()

    # ---- Command palette ----
    def _open_command_palette(self) -> None:
        commands: list[PaletteItem] = self._build_palette_items()
        dlg = CommandPaletteDialog(self, self.project, commands)
        dlg.itemActivated.connect(self._on_palette_activated)
        dlg.exec()

    def _build_palette_items(self) -> list[PaletteItem]:
        items: list[PaletteItem] = []
        # Commands
        items.append(PaletteItem(
            "Create new task", subtitle="action", kind="action",
            payload=lambda: self._on_new_task(),
        ))
        items.append(PaletteItem(
            "Recalculate schedule (CPM)", subtitle="action",
            payload=lambda: self._recalculate(),
        ))
        items.append(PaletteItem(
            "Auto-layout graph", subtitle="action",
            payload=lambda: self._on_layout(),
        ))
        items.append(PaletteItem(
            "Run Monte Carlo simulation", subtitle="action",
            payload=lambda: self._on_monte_carlo(),
        ))
        items.append(PaletteItem(
            "Show advisor report", subtitle="action",
            payload=lambda: self._on_advisor(),
        ))
        items.append(PaletteItem(
            "Save project snapshot", subtitle="action",
            payload=lambda: self._on_save(),
        ))
        items.append(PaletteItem(
            "Open project...", subtitle="action",
            payload=lambda: self._on_open(),
        ))
        items.append(PaletteItem(
            "Export as JSON", subtitle="action",
            payload=lambda: self._on_export("json"),
        ))
        items.append(PaletteItem(
            "Export as Mermaid", subtitle="action",
            payload=lambda: self._on_export("mermaid"),
        ))
        for kind in ViewKind:
            items.append(PaletteItem(
                f"Switch to {kind.value} view", subtitle="view",
                payload=lambda k=kind: self._switch_view(k),
            ))
        items.append(PaletteItem(
            "Project settings...", subtitle="action",
            payload=lambda: self._on_project_settings(),
        ))
        items.append(PaletteItem(
            "Toggle console", subtitle="action",
            payload=lambda: self._toggle_console(),
        ))
        # Tasks
        for t in sorted(self.project.tasks(), key=lambda x: x.title.lower()):
            items.append(PaletteItem(
                t.title,
                subtitle=f"{t.status.value} · {t.duration.humanize()} · {str(t.id)}",
                kind="task",
                payload=lambda tid=str(t.id): self._on_sidebar_double_clicked(tid),
            ))
        return items

    def _on_palette_activated(self, payload) -> None:
        if callable(payload):
            payload()
        elif isinstance(payload, str):
            # It's a view kind name
            try:
                self._switch_view(ViewKind(payload))
            except ValueError:
                pass

    # ---- Keyboard ----
    def keyPressEvent(self, event) -> None:
        # Ctrl+P → command palette
        if event.matches(QKeySequence("Ctrl+P")):
            self._open_command_palette()
            return
        if event.matches(QKeySequence("Ctrl+`")):
            self._toggle_console()
            return
        super().keyPressEvent(event)

    # ---- Close ----
    def closeEvent(self, event: QCloseEvent) -> None:
        # Autosave on exit
        try:
            self.repository.save_snapshot(self.project, kind="autosave")
        except Exception:
            pass
        super().closeEvent(event)
