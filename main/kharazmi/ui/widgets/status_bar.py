"""StatusBar — bottom status bar showing project info and alerts."""
from __future__ import annotations

from PySide6.QtCore import Qt, Signal, QTimer
from PySide6.QtGui import QFont, QColor
from PySide6.QtWidgets import (
    QStatusBar, QLabel, QWidget, QHBoxLayout, QFrame,
)

from ...core import Project
from ..theme import Palette
from ..icons import get_icon


class StatusBar(QStatusBar):
    def __init__(self, parent: QWidget = None) -> None:
        super().__init__(parent)
        self.setSizeGripEnabled(False)
        self.setStyleSheet(f"""
            QStatusBar {{
                background-color: {Palette.BG_SECONDARY};
                color: {Palette.TEXT_SECONDARY};
                border-top: 1px solid {Palette.BORDER_SUBTLE};
                font-size: 11px;
                padding: 2px 0;
            }}
            QStatusBar::item {{ border: none; }}
        """)

        self._project_label = QLabel("")
        self._project_label.setStyleSheet(
            f"color: {Palette.GOLD_BRIGHT}; font-weight: bold; "
            f"font-family: 'JetBrains Mono', monospace; padding: 0 12px;"
        )
        self.addWidget(self._project_label)

        self._stats_label = QLabel("")
        self._stats_label.setStyleSheet(f"color: {Palette.TEXT_SECONDARY}; padding: 0 12px;")
        self.addWidget(self._stats_label, stretch=1)

        # Right side
        self._schedule_label = QLabel("")
        self._schedule_label.setStyleSheet(
            f"color: {Palette.TEXT_TERTIARY}; padding: 0 12px; "
            f"font-family: 'JetBrains Mono', monospace;"
        )
        self.addPermanentWidget(self._schedule_label)

        self._message_label = QLabel("")
        self._message_label.setStyleSheet(
            f"color: {Palette.GOLD_PRIMARY}; padding: 0 12px; "
            f"font-family: 'JetBrains Mono', monospace;"
        )
        self.addPermanentWidget(self._message_label)

        # Auto-clear timer for messages
        self._message_timer = QTimer(self)
        self._message_timer.setSingleShot(True)
        self._message_timer.timeout.connect(lambda: self._message_label.setText(""))

    def update_project(self, project: Project) -> None:
        self._project_label.setText(
            f"  ◆  {project.name.upper()}   "
            f"({project.task_count} tasks · {project.dependency_count} deps)"
        )

    def update_stats(self, total: int, done: int, active: int,
                     blocked: int, critical: int, completion: float) -> None:
        self._stats_label.setText(
            f"  Done: {done}  ·  Active: {active}  ·  Blocked: {blocked}  "
            f"·  Critical: {critical}  ·  Completion: {completion:.1f}%"
        )

    def update_schedule(self, duration_str: str, critical_count: int) -> None:
        self._schedule_label.setText(
            f"⏱  Project span: {duration_str}   ·   Critical tasks: {critical_count}"
        )

    def show_message(self, text: str, timeout_ms: int = 4000) -> None:
        self._message_label.setText(text)
        if timeout_ms > 0:
            self._message_timer.start(timeout_ms)
