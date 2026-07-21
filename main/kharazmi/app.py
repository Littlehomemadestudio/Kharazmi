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

import sys
import signal
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

    splash.set_progress(20, "Loading project data...")
    app.processEvents()

    # ---- Load or seed the project ----
    repo = SQLiteRepository()
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

    splash.set_progress(40, "Preparing workspace...")
    app.processEvents()

    if project is None:
        project = Project(name="Untitled Project",
                          description="A new Rask project.")
        if "--empty" not in argv:
            _seed_demo_project(project)

    splash.set_progress(60, "Initializing calendar...")
    app.processEvents()

    # ---- Show the unified Rask window ----
    window = RaskMainWindow(project)

    splash.set_progress(80, "Starting AI services...")
    app.processEvents()

    splash.set_progress(100, "Ready!")
    app.processEvents()

    # Ensure splash shows for at least _SPLASH_MIN_SECS seconds total
    elapsed = time.monotonic() - _splash_start
    remaining_ms = max(0, int((_SPLASH_MIN_SECS - elapsed) * 1000))
    QTimer.singleShot(remaining_ms, splash.finish)

    window.show()
    QTimer.singleShot(100, window._recalculate)

    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
