"""TimelineView — chronological list of tasks with bars showing duration."""
from __future__ import annotations

from datetime import datetime
from typing import Optional

from PySide6.QtCore import Qt, QRectF, Signal, QSize
from PySide6.QtGui import (
    QPainter, QPen, QBrush, QColor, QFont, QAction,
)
from PySide6.QtWidgets import (
    QWidget, QScrollArea, QVBoxLayout, QHBoxLayout, QLabel, QFrame,
    QTableWidget, QTableWidgetItem, QHeaderView, QTreeWidget,
    QTreeWidgetItem, QStyledItemDelegate, QStyleOptionViewItem,
    QAbstractItemView, QToolBar, QStyle,
)

from ...core import Project, Task, TaskStatus
from ...services import TaskService
from ..theme import Palette, status_color
from ..icons import get_icon


class TimelineView(QTreeWidget):
    """
    Hierarchical list of tasks grouped by week, with duration bars.
    """
    taskDoubleClicked = Signal(str)

    def __init__(self, project: Project, task_service: TaskService,
                 parent: QWidget = None) -> None:
        super().__init__(parent)
        self.project = project
        self.task_service = task_service
        self.setSelectionMode(QAbstractItemView.SingleSelection)
        self.setRootIsDecorated(True)
        self.setAlternatingRowColors(True)
        self.setHeaderLabels([
            "Task", "Status", "Priority", "Duration", "Start", "End", "Slack", "Progress"
        ])
        self.header().setSectionResizeMode(0, QHeaderView.Stretch)
        for i in range(1, 8):
            self.header().setSectionResizeMode(i, QHeaderView.ResizeToContents)
        self.setStyleSheet(f"QTreeWidget::item {{ padding: 6px 4px; }}")

        self.itemDoubleClicked.connect(self._on_double_clicked)
        self._rebuild()

    def refresh(self) -> None:
        self._rebuild()

    def _rebuild(self) -> None:
        self.clear()
        # Group tasks by ISO week of early_start
        from collections import defaultdict
        by_week: dict[str, list[Task]] = defaultdict(list)
        no_week: list[Task] = []

        for t in self.project.tasks():
            if t.early_start:
                iso = t.early_start.isocalendar()
                key = f"{iso[0]}-W{iso[1]:02d}"
                by_week[key].append(t)
            else:
                no_week.append(t)

        for week_key in sorted(by_week.keys()):
            tasks = by_week[week_key]
            tasks.sort(key=lambda t: (t.early_start or datetime.max, t.title.lower()))
            # Compute week date range
            week_start = tasks[0].early_start
            from datetime import timedelta
            for t in tasks:
                if t.early_start and t.early_start < week_start:
                    week_start = t.early_start
            # ISO week Monday
            week_monday = week_start - timedelta(days=week_start.weekday())
            week_sunday = week_monday + timedelta(days=6)
            week_label = f"Week of {week_monday.strftime('%b %d')} – {week_sunday.strftime('%b %d, %Y')}"

            parent = QTreeWidgetItem(self, [week_label, "", "", "", "", "", "", ""])
            f = parent.font(0)
            f.setBold(True)
            f.setCapitalization(QFont.AllUppercase)
            parent.setFont(0, f)
            parent.setForeground(0, QColor(Palette.GOLD_PRIMARY))
            parent.setBackground(0, QColor(Palette.BG_TERTIARY))
            for c in range(1, 8):
                parent.setBackground(c, QColor(Palette.BG_TERTIARY))

            for t in tasks:
                row = QTreeWidgetItem(parent, [
                    t.title,
                    t.status.value,
                    t.priority.name,
                    t.duration.humanize(),
                    t.early_start.strftime("%b %d %H:%M") if t.early_start else "—",
                    t.early_finish.strftime("%b %d %H:%M") if t.early_finish else "—",
                    t.slack.total_slack.humanize() if t.slack else "—",
                    f"{t.progress.percent}%",
                ])
                # Color by criticality
                if t.is_critical:
                    row.setForeground(0, QColor(Palette.GOLD_BRIGHT))
                    f = row.font(0)
                    f.setBold(True)
                    row.setFont(0, f)
                else:
                    row.setForeground(0, QColor(Palette.TEXT_PRIMARY))
                row.setForeground(1, QColor(status_color(t.status.value)))
                if t.slack and t.slack.is_critical:
                    row.setForeground(6, QColor(Palette.GOLD_BRIGHT))

            self.expandItem(parent)

        # Unscheduled
        if no_week:
            no_week.sort(key=lambda t: t.title.lower())
            parent = QTreeWidgetItem(self, ["Unscheduled", "", "", "", "", "", "", ""])
            f = parent.font(0)
            f.setBold(True)
            f.setCapitalization(QFont.AllUppercase)
            parent.setFont(0, f)
            parent.setForeground(0, QColor(Palette.TEXT_TERTIARY))
            parent.setBackground(0, QColor(Palette.BG_TERTIARY))
            for c in range(1, 8):
                parent.setBackground(c, QColor(Palette.BG_TERTIARY))
            for t in no_week:
                QTreeWidgetItem(parent, [
                    t.title, t.status.value, t.priority.name,
                    t.duration.humanize(), "—", "—", "—", f"{t.progress.percent}%",
                ])
            self.expandItem(parent)

    def _on_double_clicked(self, item: QTreeWidgetItem, column: int) -> None:
        # Only emit for leaf items (tasks), not week groupings
        if item.parent() is None:
            return
        # We don't have task_id directly here; search by title
        title = item.text(0)
        for t in self.project.tasks():
            if t.title == title:
                self.taskDoubleClicked.emit(str(t.id))
                return
