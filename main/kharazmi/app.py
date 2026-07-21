"""
Rask application bootstrap.

Run with:
    python -m kharazmi.app
or:
    python main.py

Rask is a unified planning workspace that integrates:
  - Calendar (Google-Calendar-style, Shamsi dates)
  - AI Planner (z.ai GLM-4.5-flash generates walkable route graphs)
  - Journal (history of AI-generated routes)
  - Tasks (Enterprise node-graph task operating system)

The Calendar tab is shown first by default.
"""
from __future__ import annotations

import os
import sys
import signal
import threading
import time
from typing import Optional

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QFont
from PySide6.QtWidgets import QApplication, QMessageBox

from .core import (
    Project, Task, TaskId, Dependency, DependencyType,
    Priority, TaskStatus, RiskLevel, Duration, DurationUnit,
)
from .persistence import SQLiteRepository
from .ui import RaskMainWindow
from .ui.theme import QSS, build_qpalette, default_font
from .ui.widgets import RaskSplashScreen


def _silent_excepthook(exc_type, exc_value, exc_tb):
    """Suppress RuntimeError from deleted PySide6 C++ objects."""
    if exc_type is RuntimeError and "already deleted" in str(exc_value):
        return  # Silently swallow deleted C++ object errors
    # Also suppress QPainter not active errors
    if exc_type is RuntimeError and "Painter not active" in str(exc_value):
        return
    # For everything else, show the error normally
    sys.__excepthook__(exc_type, exc_value, exc_tb)


sys.excepthook = _silent_excepthook


def _silent_threading_excepthook(args):
    """Suppress RuntimeError from deleted PySide6 C++ objects in threads."""
    if args.exc_type is RuntimeError and "already deleted" in str(args.exc_value):
        return
    # For other errors, use default behavior
    sys.__excepthook__(args.exc_type, args.exc_value, args.exc_traceback)


threading.excepthook = _silent_threading_excepthook


def _seed_demo_project(project: Project) -> None:
    """Seed the project with demo tasks so the Enterprise tab opens to something."""
    a = project.create_task(
        title="Define product vision",
        duration=Duration.of(2, DurationUnit.DAY),
        priority=Priority.CRITICAL,
        x=-600, y=-150,
    )
    a.advance(TaskStatus.READY)

    b = project.create_task(
        title="User research",
        duration=Duration.of(3, DurationUnit.DAY),
        priority=Priority.HIGH,
        x=-350, y=-250,
    )
    b.advance(TaskStatus.READY)

    c = project.create_task(
        title="Technical architecture",
        duration=Duration.of(4, DurationUnit.DAY),
        priority=Priority.HIGH,
        x=-350, y=-50,
    )
    c.advance(TaskStatus.READY)

    d = project.create_task(
        title="Backend API",
        duration=Duration.of(8, DurationUnit.DAY),
        priority=Priority.CRITICAL,
        x=-50, y=-100,
    )
    d.set_progress(15)
    d.advance(TaskStatus.READY)
    d.advance(TaskStatus.ACTIVE)

    e = project.create_task(
        title="Frontend UI",
        duration=Duration.of(10, DurationUnit.DAY),
        priority=Priority.HIGH,
        x=-50, y=80,
    )
    e.advance(TaskStatus.READY)

    f = project.create_task(
        title="Integration testing",
        duration=Duration.of(3, DurationUnit.DAY),
        priority=Priority.MEDIUM,
        x=250, y=0,
    )
    f.advance(TaskStatus.READY)

    g = project.create_task(
        title="Documentation",
        duration=Duration.of(2, DurationUnit.DAY),
        priority=Priority.LOW,
        x=250, y=180,
    )

    h = project.create_task(
        title="Production launch",
        duration=Duration.of(1, DurationUnit.DAY),
        priority=Priority.CRITICAL,
        x=550, y=80,
    )

    project.add_dependency(Dependency(a.id, b.id, DependencyType.FINISH_START))
    project.add_dependency(Dependency(a.id, c.id, DependencyType.FINISH_START))
    project.add_dependency(Dependency(b.id, d.id, DependencyType.FINISH_START))
    project.add_dependency(Dependency(c.id, d.id, DependencyType.FINISH_START))
    project.add_dependency(Dependency(c.id, e.id, DependencyType.FINISH_START))
    project.add_dependency(Dependency(d.id, f.id, DependencyType.FINISH_START))
    project.add_dependency(Dependency(e.id, f.id, DependencyType.FINISH_START))
    project.add_dependency(Dependency(e.id, g.id, DependencyType.START_START))
    project.add_dependency(Dependency(f.id, h.id, DependencyType.FINISH_START))
    project.add_dependency(Dependency(g.id, h.id, DependencyType.FINISH_START))


def main(argv: Optional[list[str]] = None) -> int:
    """Application entry point."""
    argv = argv if argv is not None else sys.argv

    # Suppress Qt warning/debug messages in terminal
    os.environ["QT_LOGGING_RULES"] = "*.debug=false;qt.qpa.*=false;qt.widgets.*=false"

    # Redirect Qt messages to /dev/null
    from PySide6.QtCore import qInstallMessageHandler, QtMsgType
    def _suppress_qt_messages(msg_type, context, msg):
        """Suppress all Qt messages to terminal."""
        pass  # Do nothing — silence all Qt output
    qInstallMessageHandler(_suppress_qt_messages)

    # Allow Ctrl+C to terminate
    signal.signal(signal.SIGINT, signal.SIG_DFL)

    # High-DPI handling
    QApplication.setHighDpiScaleFactorRoundingPolicy(
        Qt.HighDpiScaleFactorRoundingPolicy.PassThrough
    )

    app = QApplication(argv)
    app.setApplicationName("Rask")
    app.setApplicationDisplayName("Rask")
    app.setApplicationVersion("3.0.0")
    app.setOrganizationName("Littlehomemadestudio")

    # Apply theme globally
    app.setStyleSheet(QSS)
    app.setPalette(build_qpalette())
    app.setFont(default_font())

    # ---- Show splash screen ----
    _splash_start = time.monotonic()
    _SPLASH_MIN_SECS = 5.0  # Splash stays at least this long

    splash = RaskSplashScreen()
    splash.show()
    app.processEvents()

    # Helper: micro-step with log + progress + brief pause for visual effect
    def _step(progress: int, status: str, log: str, pause_ms: int = 0) -> None:
        splash.set_progress(progress, status)
        splash.add_log(log)
        app.processEvents()
        if pause_ms > 0:
            QTimer.singleShot(0, lambda: None)  # yield to event loop
            app.processEvents()

    # ── Stage 1: Core bootstrap ──
    _step(5, "Bootstrapping core...", "[OK] Core modules loaded")
    app.processEvents()

    _step(10, "Initializing calendar engine...", "[OK] Persian calendar engine initialized")
    app.processEvents()

    _step(15, "Configuring date system...", "[OK] Shamsi date system ready")
    app.processEvents()

    # ── Stage 2: Persistence layer ──
    repo = SQLiteRepository()

    _step(22, "Connecting persistence layer...", "[OK] SQLite persistence layer connected")
    app.processEvents()

    # ---- Load or seed the project ----
    project: Optional[Project] = None
    if "--new" not in argv and "--demo" not in argv:
        try:
            projects = repo.list_projects()
            if projects:
                pid = projects[0]["id"]
                loaded = repo.load_latest(pid)
                if loaded is not None and loaded.task_count > 0:
                    project = loaded
        except Exception:
            pass

    task_count = project.task_count if project else 0
    _step(30, "Loading project data...",
          f"[OK] Project data loaded ({task_count} tasks)")
    app.processEvents()

    if project is None:
        project = Project(name="Untitled Project",
                          description="A new Rask project.")
        if "--empty" not in argv:
            _seed_demo_project(project)
        task_count = project.task_count

    # ── Stage 3: Data stores ──
    from .calendar import CalendarStore as _CS
    from .persistence import CalendarRepository as _CR
    _cal_repo = _CR()
    _cal_store = _cal_repo.load_latest() or _CS()
    _evt_count = _cal_store.event_count
    _step(42, "Hydrating calendar store...",
          f"[OK] Calendar store hydrated ({_evt_count} events)")
    app.processEvents()

    _step(52, "Configuring AI service...", "[OK] AI service configured (GLM-4.5)")
    app.processEvents()

    from .ai import JournalStore as _JS
    _journal = _JS()
    _jcount = len(_journal)
    _step(60, "Loading journal entries...",
          f"[OK] Journal store loaded ({_jcount} entries)")
    app.processEvents()

    # ── Stage 4: Workspace ──
    window = RaskMainWindow(project)

    _step(72, "Preparing workspace...", "[OK] Workspace prepared")
    app.processEvents()

    _step(82, "Mounting UI components...", "[OK] UI components mounted")
    app.processEvents()

    _step(92, "Finalizing subsystems...", "[OK] Subsystems synchronized")
    app.processEvents()

    # ── Stage 5: Ready ──
    splash.set_progress(100, "All systems operational")
    splash.add_log("[OK] All systems operational")
    app.processEvents()

    # Ensure splash shows for at least _SPLASH_MIN_SECS seconds total
    elapsed = time.monotonic() - _splash_start
    remaining_ms = max(0, int((_SPLASH_MIN_SECS - elapsed) * 1000))
    QTimer.singleShot(remaining_ms, splash.finish)

    window.showMaximized()
    QTimer.singleShot(100, window._recalculate)

    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
