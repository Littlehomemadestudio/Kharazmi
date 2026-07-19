"""
Kharazmi application bootstrap.

Run with:
    python -m kharazmi.app
or:
    python main.py
"""
from __future__ import annotations

import sys
import signal
from typing import Optional

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QFont
from PySide6.QtWidgets import QApplication

from .core import (
    Project, Task, TaskId, Dependency, DependencyType,
    Priority, TaskStatus, RiskLevel, Duration, DurationUnit,
)
from .persistence import SQLiteRepository
from .ui import MainWindow
from .ui.theme import QSS, build_qpalette, default_font


def _seed_demo_project(project: Project) -> None:
    """Populate the project with a small demo so the app opens to something interesting."""
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

    # Dependencies
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

    # High-DPI handling (Qt6 does this by default; keep for clarity)
    QApplication.setHighDpiScaleFactorRoundingPolicy(
        Qt.HighDpiScaleFactorRoundingPolicy.PassThrough
    )

    app = QApplication(argv)
    app.setApplicationName("Kharazmi")
    app.setApplicationDisplayName("Kharazmi")
    app.setApplicationVersion("2.0.0")
    app.setOrganizationName("Littlehomemadestudio")

    # Apply theme globally
    app.setStyleSheet(QSS)
    app.setPalette(build_qpalette())
    app.setFont(default_font())

    # Try to load the latest autosave, else seed a demo
    repo = SQLiteRepository()
    project: Optional[Project] = None

    if "--demo" in argv or "--new" in argv:
        project = Project(name="Demo Project",
                          description="A seeded example project showing Kharazmi's capabilities.")
    else:
        # Try loading the most recent autosave across all projects
        try:
            projects = repo.list_projects()
            if projects:
                # Take the first project (alphabetical)
                pid = projects[0]["id"]
                loaded = repo.load_latest(pid)
                if loaded is not None and loaded.task_count > 0:
                    project = loaded
        except Exception:
            pass

    if project is None:
        project = Project(name="Untitled Project",
                          description="A new Kharazmi project.")
        if "--empty" not in argv:
            _seed_demo_project(project)

    # Show main window
    window = MainWindow(project)
    window.show()

    # Auto-recalc on startup
    QTimer.singleShot(100, window._recalculate)

    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
