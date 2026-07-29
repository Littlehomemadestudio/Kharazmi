# پنجره اصلی RASK — رابط کاربری یکپارچه با تب‌های تقویم، برنامه‌ریز، و وظایف
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

    # ساخت پنجره اصلی برنامه با پروژه و خدمات‌ها
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
        QTimer.singleShot(1500, self._maybe_show_tour)

        # ---- Calendar autosave ----
        self._autosave_timer = QTimer(self)
        self._autosave_timer.setInterval(60000)
        self._autosave_timer.timeout.connect(self._autosave)
        self._autosave_timer.start()

    # ---- UI building ----
    # ساخت رابط کاربری با نوار عنوان شیشه‌ای
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

    # ساخت منوهای برنامه
    def _build_menu(self) -> None:
        menubar = self.menuBar()

        # File menu
        file_menu = menubar.addMenu("فایل")

        # New actions
        self._action_new_event = QAction(get_icon("plus"), "رویداد جدید...", self)
        self._action_new_event.setShortcut(QKeySequence("Ctrl+E"))
        self._action_new_event.triggered.connect(self._on_new_event)
        file_menu.addAction(self._action_new_event)

        self._action_new_task = QAction(get_icon("plus"), "وظیفه جدید...", self)
        self._action_new_task.setShortcut(QKeySequence("Ctrl+T"))
        self._action_new_task.triggered.connect(self._on_new_task)
        file_menu.addAction(self._action_new_task)

        file_menu.addSeparator()

        self._action_save = QAction(get_icon("save"), "ذخیره", self)
        self._action_save.setShortcut(QKeySequence.Save)
        self._action_save.triggered.connect(self._on_save)
        file_menu.addAction(self._action_save)

        file_menu.addSeparator()

        self._action_ai_settings = QAction("تنظیمات هوش مصنوعی...", self)
        self._action_ai_settings.triggered.connect(self._on_ai_settings)
        file_menu.addAction(self._action_ai_settings)

        self._action_manage_calendars = QAction("مدیریت تقویم‌ها...", self)
        self._action_manage_calendars.triggered.connect(self._on_manage_calendars)
        file_menu.addAction(self._action_manage_calendars)

        file_menu.addSeparator()

        self._action_export_json = QAction("صادر کردن وظایف به JSON...", self)
        self._action_export_json.triggered.connect(lambda: self._on_export("json"))
        file_menu.addAction(self._action_export_json)

        self._action_export_calendar = QAction("صادر کردن تقویم به JSON...", self)
        self._action_export_calendar.triggered.connect(self._on_export_calendar)
        file_menu.addAction(self._action_export_calendar)

        file_menu.addSeparator()

        self._action_quit = QAction("خروج", self)
        self._action_quit.setShortcut(QKeySequence.Quit)
        self._action_quit.triggered.connect(self.close)
        file_menu.addAction(self._action_quit)

        # Edit menu
        edit_menu = menubar.addMenu("ویرایش")
        self._action_undo = QAction(get_icon("undo"), "برگشت", self)
        self._action_undo.setShortcut(QKeySequence.Undo)
        self._action_undo.triggered.connect(self._on_undo)
        edit_menu.addAction(self._action_undo)

        self._action_redo = QAction(get_icon("redo"), "دوباره", self)
        self._action_redo.setShortcut(QKeySequence.Redo)
        self._action_redo.triggered.connect(self._on_redo)
        edit_menu.addAction(self._action_redo)

        # View menu
        view_menu = menubar.addMenu("نمایش")
        self._action_tab_home = QAction("رفتن به خانه", self)
        self._action_tab_home.setShortcut(QKeySequence("Ctrl+0"))
        self._action_tab_home.triggered.connect(lambda: self._switch_tab(0))
        view_menu.addAction(self._action_tab_home)

        self._action_tab_calendar = QAction("رفتن به تقویم", self)
        self._action_tab_calendar.setShortcut(QKeySequence("Ctrl+1"))
        self._action_tab_calendar.triggered.connect(lambda: self._switch_tab(1))
        view_menu.addAction(self._action_tab_calendar)

        self._action_tab_ai = QAction("رفتن به برنامه‌ریز", self)
        self._action_tab_ai.setShortcut(QKeySequence("Ctrl+2"))
        self._action_tab_ai.triggered.connect(lambda: self._switch_tab(2))
        view_menu.addAction(self._action_tab_ai)

        self._action_tab_graphs = QAction("رفتن به نمودارها", self)
        self._action_tab_graphs.setShortcut(QKeySequence("Ctrl+3"))
        self._action_tab_graphs.triggered.connect(lambda: self._switch_tab(3))
        view_menu.addAction(self._action_tab_graphs)

        self._action_tab_simulation = QAction("رفتن به شبیه‌سازی", self)
        self._action_tab_simulation.setShortcut(QKeySequence("Ctrl+4"))
        self._action_tab_simulation.triggered.connect(lambda: self._switch_tab(4))
        view_menu.addAction(self._action_tab_simulation)

        self._action_tab_journal = QAction("رفتن به یادداشت‌ها", self)
        self._action_tab_journal.setShortcut(QKeySequence("Ctrl+5"))
        self._action_tab_journal.triggered.connect(lambda: self._switch_tab(5))
        view_menu.addAction(self._action_tab_journal)

        self._action_tab_tasks = QAction("رفتن به وظایف", self)
        self._action_tab_tasks.setShortcut(QKeySequence("Ctrl+6"))
        self._action_tab_tasks.triggered.connect(lambda: self._switch_tab(2))
        view_menu.addAction(self._action_tab_tasks)

        view_menu.addSeparator()

        self._action_fullscreen = QAction("تغییر تمام‌صفحه", self)
        self._action_fullscreen.setShortcut(QKeySequence("F11"))
        self._action_fullscreen.triggered.connect(self.toggle_fullscreen)
        view_menu.addAction(self._action_fullscreen)

        view_menu.addSeparator()

        self._action_toggle_theme = QAction("تغییر تم (روشن/تیره)", self)
        self._action_toggle_theme.triggered.connect(self._toggle_theme)
        view_menu.addAction(self._action_toggle_theme)

        # Schedule menu (for Enterprise features)
        sched_menu = menubar.addMenu("زمان‌بندی")
        self._action_recalc = QAction(get_icon("play"), "محاسبه مجدد CPM", self)
        self._action_recalc.setShortcut(QKeySequence("Ctrl+R"))
        self._action_recalc.triggered.connect(self._recalculate)
        sched_menu.addAction(self._action_recalc)

        self._action_advisor = QAction(get_icon("warning"), "گزارش مشاور", self)
        self._action_advisor.triggered.connect(self._on_advisor)
        sched_menu.addAction(self._action_advisor)

        # Help menu
        help_menu = menubar.addMenu("کمک")
        self._action_tour = QAction("تور معرفی", self)
        self._action_tour.setShortcut(QKeySequence("F1"))
        self._action_tour.triggered.connect(self._on_show_tour)
        help_menu.addAction(self._action_tour)

        help_menu.addSeparator()

        self._action_about = QAction("درباره رَسک", self)
        self._action_about.triggered.connect(self._on_about)
        help_menu.addAction(self._action_about)

    # ساخت محتوای اصلی شامل تب‌ها
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
        self._tabs.addTab(dash_container, "🏠  خانه")

        # ---- Tab 1: Calendar ----
        self.calendar_view = CalendarView(self.calendar_store, ai_service=self.ai_service)
        cal_container = QWidget()
        cal_layout = QVBoxLayout(cal_container)
        cal_layout.setContentsMargins(0, 0, 0, 0)
        cal_layout.addWidget(self.calendar_view)
        self._tabs.addTab(cal_container, "📅  تقویم")

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
        self._tabs.addTab(graphs_container, "📊  نمودارها")

        # ---- Tab 4: Simulation ----
        self.simulation_view = SimulationView()
        sim_container = QWidget()
        sim_layout = QVBoxLayout(sim_container)
        sim_layout.setContentsMargins(0, 0, 0, 0)
        sim_layout.addWidget(self.simulation_view)
        self._tabs.addTab(sim_container, "🧪  شبیه‌سازی")

        # ---- Tab 5: Journal ----
        self.journal_view = JournalView(self.journal_store)
        journal_container = QWidget()
        journal_layout = QVBoxLayout(journal_container)
        journal_layout.setContentsMargins(0, 0, 0, 0)
        journal_layout.addWidget(self.journal_view)
        self._tabs.addTab(journal_container, "📖  یادداشت‌ها")

    # ساخت تب یکپارچه برنامه‌ریز و وظایف
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

        self._tabs.addTab(container, "✦  برنامه‌ریز و وظایف")

    # سبک دکمه حالت (برای سازگاری قبلی)
    def _mode_button_style(self, active: bool) -> str:
        """Kept for backward compat — no longer used."""
        return ""

    # تغییر فضای کاری (برای سازگاری قبلی)
    def _switch_workspace(self, mode: str) -> None:
        """Kept for backward compat — no longer used."""
        pass

    # ساخت فضای کاری وظایف (برای سازگاری قبلی)
    def _build_tasks_workspace(self) -> None:
        """Kept for backward compat — no longer used."""
        pass

    # ساخت نوار وضعیت پایین پنجره
    def _build_statusbar(self) -> None:
        self.statusbar = StatusBar(self)
        self.setStatusBar(self.statusbar)
        today = ShamsiDate.today()
        self.statusbar.update_project_named(
            f"  ◆  RASK   •   {today.format('d MMMM yyyy')}  •  {today.weekday_fa}"
        )
        self._refresh_statusbar()

    # به‌روزرسانی نوار وضعیت با شمارش‌ها
    def _refresh_statusbar(self) -> None:
        # Show counts
        cal_count = self.calendar_store.event_count
        task_count = self.project.task_count
        journal_count = len(self.journal_store)
        ai_status = "● هوش مصنوعی آماده" if self.ai_service.is_configured else "○ هوش مصنوعی تنظیم نشده"
        self.statusbar.show_message(
            f"{cal_count} رویداد · {task_count} وظیفه · {journal_count} یادداشت   |   {ai_status}",
            0,
        )

    # ---- Tab switching ----
    # تغییر تب فعال
    def _switch_tab(self, idx: int) -> None:
        if 0 <= idx < self._tabs.count():
            self._tabs.setCurrentIndex(idx)

    # ---- Project events ----
    # پردازش رویدادهای پروژه
    def _on_project_event(self, event: DomainEvent) -> None:
        QTimer.singleShot(0, self._refresh_enterprise)

    # پردازش رویدادهای فروشگاه تقویم
    def _on_calendar_store_event(self, event) -> None:
        QTimer.singleShot(0, self._refresh_statusbar)
        # Persist deletions and updates immediately so they don't "come back" or get lost on restart
        from ..calendar.store import EventUpdated
        if isinstance(event, (EventRemoved, CalendarRemoved)):
            self._persist_calendar()
        elif isinstance(event, EventUpdated):
            # Persist updates immediately so renamed/modified events are saved
            self._persist_calendar()
        else:
            # For additions, use a delayed save to batch rapid changes
            QTimer.singleShot(1000, self._autosave)

    # به‌روزرسانی وضعیت دکمه‌های برگشت‌پذیری
    def _on_undo_stack_changed(self) -> None:
        self._action_undo.setEnabled(self.undo_stack.can_undo())
        self._action_redo.setEnabled(self.undo_stack.can_redo())

    # به‌روزرسانی نمای گراف وظایف و نوار وضعیت
    def _refresh_enterprise(self) -> None:
        # Refresh the unified graph view (sync tasks)
        if hasattr(self, "ai_planner_view") and hasattr(self.ai_planner_view, "graph_view"):
            self.ai_planner_view.graph_view._sync_tasks_to_canvas()
        self._refresh_statusbar()

    # دریافت وظیفه انتخاب‌شده (دیگر استفاده نمی‌شود)
    def _get_selected_task(self) -> Optional[Task]:
        # No longer used — selection is handled by the unified graph view
        return None

    # ---- Cross-tab interactions ----
    # بارگذاری مسیر یادداشت روزانه در برنامه‌ریز
    def _on_journal_entry_selected(self, entry) -> None:
        """Load a journal entry's route into the AI planner view."""
        if entry.route is not None:
            self._switch_tab(2)  # Planner & Tasks tab
            self.ai_planner_view.set_route(entry.route, entry_id=entry.id)
            # Also update graphs and simulation views
            self.graphs_view.set_route(entry.route)
            self.simulation_view.set_route(entry.route)
            self.statusbar.show_message(
                f"مسیر بارگذاری شد از {entry.timestamp[:10]} در برنامه‌ریز", 3000
            )

    # همگام‌سازی مسیر انتخاب‌شده از نمودارها با شبیه‌سازی
    def _on_graphs_route_selected(self, route: Route) -> None:
        """When a route is selected in the Graphs view, also update Simulation."""
        self.simulation_view.set_route(route)

    # همگام‌سازی مسیر به‌روزرسانی‌شده برنامه‌ریز با نمودارها و شبیه‌سازی
    def _on_planner_route_updated(self, route: Route) -> None:
        """When AI Planner generates/updates a route, sync Graphs and Simulation views."""
        self.graphs_view.set_route(route)
        self.simulation_view.set_route(route)

    # ---- Actions ----
    # ایجاد رویداد جدید
    def _on_new_event(self) -> None:
        self._switch_tab(1)  # Calendar tab
        dlg = EventEditorDialog(None, self.calendar_store, self)
        if dlg.exec():
            pass

    # ایجاد وظیفه جدید
    def _on_new_task(self) -> None:
        self._switch_tab(2)  # Planner & Tasks tab
        if hasattr(self, "ai_planner_view") and hasattr(self.ai_planner_view, "graph_view"):
            self.ai_planner_view.graph_view._on_add_task()

    # ذخیره تمام داده‌ها
    def _on_save(self) -> None:
        self.repository.save_snapshot(self.project, kind="manual")
        self.calendar_repository.save(self.calendar_store, kind="manual")
        self.statusbar.show_message("همه داده‌ها ذخیره شد", 3000)

    # باز کردن تنظیمات هوش مصنوعی
    def _on_ai_settings(self) -> None:
        dlg = AISettingsDialog(self.ai_service, self)
        dlg.exec()
        self._refresh_statusbar()

    # باز کردن مدیریت تقویم‌ها
    def _on_manage_calendars(self) -> None:
        dlg = CalendarSettingsDialog(self.calendar_store, self)
        dlg.exec()

    # صادرکردن وظایف به فرمت JSON
    def _on_export(self, fmt: str) -> None:
        path, _ = QFileDialog.getSaveFileName(
            self, f"صادر کردن {fmt.upper()}",
            f"{self.project.name}.{fmt}",
            f"{fmt.upper()} files (*.{fmt});;All files (*)"
        )
        if not path:
            return
        try:
            if fmt == "json":
                self.export_service.to_json(path)
            self.statusbar.show_message(f"صادر شد → {path}", 4000)
        except Exception as e:
            QMessageBox.warning(self, "صادر کردن ناموفق", str(e))

    # صادرکردن تقویم به فرمت JSON
    def _on_export_calendar(self) -> None:
        path, _ = QFileDialog.getSaveFileName(
            self, "صادر کردن تقویم به JSON",
            "calendar.json",
            "JSON files (*.json);;All files (*)"
        )
        if not path:
            return
        try:
            import json
            with open(path, "w", encoding="utf-8") as f:
                json.dump(self.calendar_store.to_dict(), f, ensure_ascii=False, indent=2)
            self.statusbar.show_message(f"صادر شد → {path}", 4000)
        except Exception as e:
            QMessageBox.warning(self, "صادر کردن ناموفق", str(e))

    # برگشت عملیات اخیر
    def _on_undo(self) -> None:
        if self.undo_stack.undo(self.project):
            self._recalculate()

    # انجام مجدد عملیات برگشت‌خورده
    def _on_redo(self) -> None:
        if self.undo_stack.redo(self.project):
            self._recalculate()

    # باز کردن گزارش مشاور پروژه
    def _on_advisor(self) -> None:
        dlg = AdvisorDialog(self.project, self)
        dlg.exec()

    # نمایش درباره برنامه
    def _on_about(self) -> None:
        QMessageBox.about(
            self,
            "درباره رَسک",
            "<h3>رَسک</h3>"
            "<p>رَسک یک فضای کاری برنامه‌ریزی یکپارچه است که شامل:</p>"
            "<ul>"
            "<li><b>تقویم</b> — برنامه‌ریز سبک گوگل با تاریخ شمسی، "
            "چند تقویم، رویدادهای تکراری و ورودی زبان طبیعی.</li>"
            "<li><b>برنامه‌ریز هوشمند</b> — هدف خود را به زبان ساده شرح دهید "
            "و هوش مصنوعی (GLM-4.5-flash) مسیری از مراحل به هم پیوسته "
            "با احتمال موفقیت، پشتیبان و تخمین زمان می‌سازد.</li>"
            "<li><b>یادداشت‌ها</b> — هر مسیر ساخته‌شده با هوش مصنوعی "
            "برای بازبینی بعدی ذخیره می‌شود.</li>"
            "<li><b>وظایف</b> — سیستم عامل گراف وظایف سازمانی "
            "با روش مسیر بحرانی، PERT و شبیه‌سازی مونت‌کارلو.</li>"
            "</ul>"
            "<p style='color:#D4AF37'><b>نسخه ۳.۰</b></p>"
        )

    # ---- Enterprise-side helpers ----
    # دابل‌کلیک روی نوار کناری (دیگر استفاده نمی‌شود)
    def _on_sidebar_double_clicked(self, task_id_str: str) -> None:
        # No longer used — sidebar was removed
        pass

    # دابل‌کلیک روی وظیفه (دیگر استفاده نمی‌شود)
    def _on_task_double_clicked(self, task_id_str: str) -> None:
        # No longer used — handled by unified graph view
        pass

    # محاسبه مجدد زمان‌بندی پروژه
    def _recalculate(self) -> None:
        result = self.scheduling.recalculate()
        if not result.ok and result.cycle_error:
            self.statusbar.show_message(
                f"⚠  Cycle: {result.cycle_error}", 8000
            )
        self._refresh_enterprise()

    # ---- Tour ----
    # نمایش تور معرفی در اولین اجرا
    def _maybe_show_tour(self) -> None:
        import json
        from pathlib import Path
        seen_path = Path.home() / ".rask" / "tour_seen_rask_v2.json"
        if not seen_path.exists():
            self._on_show_tour()
            try:
                seen_path.parent.mkdir(parents=True, exist_ok=True)
                seen_path.write_text(json.dumps({"seen": True}), encoding="utf-8")
            except Exception:
                pass

    # شروع تور معرفی
    def _on_show_tour(self) -> None:
        start_tour(self)

    # ---- Autosave ----
    # ذخیره خودکار تقویم و یادداشت‌ها
    def _autosave(self) -> None:
        try:
            self.calendar_repository.save(self.calendar_store, kind="autosave")
        except Exception:
            pass
        try:
            self.journal_store.save()
        except Exception:
            pass

    # ذخیره فوری فروشگاه تقویم
    def _persist_calendar(self) -> None:
        """Immediately persist the calendar store (used after deletions)."""
        try:
            self.calendar_repository.save(self.calendar_store, kind="manual")
        except Exception:
            pass

    # ---- Theme switching ----
    # تغییر تم بین روشن و تیره
    def _toggle_theme(self) -> None:
        """Switch between Light and Dark theme."""
        from .theme import current_mode, set_theme, QSS, build_qpalette
        from .calendar.theme import set_calendar_theme
        new_mode = "dark" if current_mode() == "light" else "light"
        set_theme(new_mode)
        set_calendar_theme(new_mode)
        # Re-apply global stylesheet and palette
        app = QApplication.instance()
        if app:
            app.setStyleSheet(QSS)
            app.setPalette(build_qpalette())
        self._reapply_theme()

    # بازسازی تمام سبک‌های درخطی برای تم فعلی
    def _reapply_theme(self) -> None:
        """Rebuild all inline styles for the current theme."""
        from .theme import Palette, QSS, build_qpalette
        # Central widget background
        central = self.centralWidget()
        if central:
            central.setStyleSheet(f"background: {Palette.BG_DEEPEST};")
        # Tab widget
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
                font-size: 14px;
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
        # Main window base stylesheet
        self.setStyleSheet(QSS)
        self.setPalette(build_qpalette())
        # Force all children to re-polish
        for child in self.findChildren(QWidget):
            try:
                child.style().unpolish(child)
                child.style().polish(child)
            except Exception:
                pass
        # Update the window icon to match current theme gold
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
        # Update status bar
        self.update_statusbar()
        # Update title bar
        if hasattr(self, '_title_bar') and self._title_bar:
            try:
                self._title_bar._reapply_theme()
            except Exception:
                pass
        # Update all view widgets
        for view_attr in ('dashboard_view', 'calendar_view', 'ai_planner_view',
                          'graphs_view', 'simulation_view', 'journal_view'):
            view = getattr(self, view_attr, None)
            if view is not None:
                try:
                    if hasattr(view, '_reapply_theme'):
                        view._reapply_theme()
                    else:
                        view.update()
                except Exception:
                    pass
        # Force repaint of all child widgets
        for child in self.findChildren(QWidget):
            try:
                child.update()
            except Exception:
                pass
        self.update()

    # ---- Close ----
    # ذخیره خودکار هنگام بستن پنجره
    def closeEvent(self, event) -> None:
        try:
            self.repository.save_snapshot(self.project, kind="autosave")
            self.calendar_repository.save(self.calendar_store, kind="autosave")
            self.journal_store.save()
        except Exception:
            pass
        super().closeEvent(event)
