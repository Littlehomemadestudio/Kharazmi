# نوار وضعیت — نمایش اطلاعات وضعیت پایین صفحه
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
    # سازنده — مقداردهی اولیه شیء
    def __init__(self, parent: QWidget = None) -> None:
        super().__init__(parent)
        self.setSizeGripEnabled(False)
        self._apply_style()

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

    # اعمال سبک بصری
    def _apply_style(self) -> None:
        self.setStyleSheet(f"""
            QStatusBar {{
                background-color: {Palette.BG_SECONDARY};
                color: {Palette.TEXT_SECONDARY};
                border-top: 1px solid {Palette.BORDER_SUBTLE};
                font-size: 12px;
                padding: 2px 0;
            }}
            QStatusBar::item {{ border: none; }}
        """)

    # بروزرسانی پروژه
    def update_project(self, project: Project) -> None:
        self._project_label.setText(
            f"  ◆  {project.name.upper()}   "
            f"({project.task_count} وظیفه · {project.dependency_count} وابستگی)"
        )

    # بروزرسانی پروژه named
    def update_project_named(self, text: str) -> None:
        """Set the project label to an arbitrary string (for Basic plan)."""
        self._project_label.setText(text)

    # بروزرسانی آمار
    def update_stats(self, total: int, done: int, active: int,
                     blocked: int, critical: int, completion: float) -> None:
        self._stats_label.setText(
            f"  انجام‌شده: {done}  ·  فعال: {active}  ·  مسدود: {blocked}  "
            f"·  بحرانی: {critical}  ·  پیشرفت: {completion:.1f}%"
        )

    # بروزرسانی schedule
    def update_schedule(self, duration_str: str, critical_count: int) -> None:
        self._schedule_label.setText(
            f"⏱  مدت پروژه: {duration_str}   ·   وظایف بحرانی: {critical_count}"
        )

    # نمایش message
    def show_message(self, text: str, timeout_ms: int = 4000) -> None:
        self._message_label.setText(text)
        if timeout_ms > 0:
            self._message_timer.start(timeout_ms)

    # بازسازی سبک‌ها برای تم فعلی
    def _reapply_theme(self) -> None:
        self._apply_style()
        self._project_label.setStyleSheet(
            f"color: {Palette.GOLD_BRIGHT}; font-weight: bold; "
            f"font-family: 'JetBrains Mono', monospace; padding: 0 12px;"
        )
        self._stats_label.setStyleSheet(f"color: {Palette.TEXT_SECONDARY}; padding: 0 12px;")
        self._schedule_label.setStyleSheet(
            f"color: {Palette.TEXT_TERTIARY}; padding: 0 12px; "
            f"font-family: 'JetBrains Mono', monospace;"
        )
        self._message_label.setStyleSheet(
            f"color: {Palette.GOLD_PRIMARY}; padding: 0 12px; "
            f"font-family: 'JetBrains Mono', monospace;"
        )
        self.update()
