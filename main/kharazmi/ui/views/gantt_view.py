"""GanttView — time-scaled bar chart of tasks."""
from __future__ import annotations

from datetime import datetime, timedelta
from typing import Optional

from PySide6.QtCore import Qt, QRectF, QPointF, QSize, Signal, QDate
from PySide6.QtGui import (
    QPainter, QPen, QBrush, QColor, QFont, QPainterPath, QMouseEvent,
    QAction, QWheelEvent,
)
from PySide6.QtWidgets import (
    QWidget, QScrollArea, QVBoxLayout, QHBoxLayout, QLabel, QFrame,
    QGraphicsView, QGraphicsScene, QGraphicsRectItem, QGraphicsTextItem,
    QGraphicsItem, QStyleOptionGraphicsItem, QToolTip,
)

from ...core import Project, Task, TaskStatus, TaskId
from ...services import TaskService
from ..theme import Palette, status_color
from ..icons import get_icon


BAR_HEIGHT = 26
ROW_HEIGHT = 36
DAY_WIDTH = 50  # pixels per day
HEADER_HEIGHT = 40
LEFT_PANEL_WIDTH = 220


class GanttView(QGraphicsView):
    """Time-scaled Gantt chart."""

    taskDoubleClicked = Signal(str)

    def __init__(self, project: Project, task_service: TaskService,
                 parent: QWidget = None) -> None:
        super().__init__(parent)
        self.project = project
        self.task_service = task_service

        self._scene = QGraphicsScene(self)
        self.setScene(self._scene)
        self.setRenderHint(QPainter.Antialiasing, True)
        self.setRenderHint(QPainter.TextAntialiasing, True)
        self.setBackgroundBrush(QBrush(QColor(Palette.BG_PRIMARY)))
        self.setAlignment(Qt.AlignLeft | Qt.AlignTop)

        self._start_date: Optional[datetime] = None
        self._end_date: Optional[datetime] = None

        # Connect scene selection to forward
        self._scene.selectionChanged.connect(self._on_selection_changed)

        self._rebuild()

    def refresh(self) -> None:
        self._rebuild()

    def _compute_window(self) -> None:
        starts = [t.early_start for t in self.project.tasks() if t.early_start]
        ends = [t.early_finish for t in self.project.tasks() if t.early_finish]
        if not starts or not ends:
            now = datetime.utcnow()
            self._start_date = now.replace(hour=0, minute=0, second=0, microsecond=0)
            self._end_date = self._start_date + timedelta(days=14)
            return
        self._start_date = min(starts).replace(hour=0, minute=0, second=0, microsecond=0) - timedelta(days=1)
        self._end_date = max(ends).replace(hour=0, minute=0, second=0, microsecond=0) + timedelta(days=2)

    def _rebuild(self) -> None:
        self._scene.clear()
        self._compute_window()
        if self._start_date is None or self._end_date is None:
            return

        # Build list of tasks in start order
        tasks = sorted(
            self.project.tasks(),
            key=lambda t: (t.early_start or datetime.max, t.title.lower())
        )

        # Background
        total_days = (self._end_date - self._start_date).days + 1
        total_width = LEFT_PANEL_WIDTH + total_days * DAY_WIDTH
        total_height = HEADER_HEIGHT + max(1, len(tasks)) * ROW_HEIGHT + 20
        self._scene.setSceneRect(0, 0, total_width, total_height)

        # Draw header (date ruler)
        self._draw_header(total_days)

        # Draw left panel (task list)
        self._draw_left_panel(tasks)

        # Draw rows
        self._draw_rows(tasks, total_days)

    def _draw_header(self, total_days: int) -> None:
        # Background bar
        bg = QGraphicsRectItem(0, 0, LEFT_PANEL_WIDTH + total_days * DAY_WIDTH, HEADER_HEIGHT)
        bg.setBrush(QBrush(QColor(Palette.BG_SECONDARY)))
        bg.setPen(QPen(QColor(Palette.BORDER_SUBTLE), 1))
        self._scene.addItem(bg)

        # "Task" label on left
        label = QGraphicsTextItem("TASK")
        label.setDefaultTextColor(QColor(Palette.TEXT_TERTIARY))
        f = QFont("Inter", 9, QFont.Bold)
        f.setLetterSpacing(QFont.AbsoluteSpacing, 1.2)
        label.setFont(f)
        label.setPos(10, 12)
        self._scene.addItem(label)

        # Date columns
        for i in range(total_days):
            d = self._start_date + timedelta(days=i)
            x = LEFT_PANEL_WIDTH + i * DAY_WIDTH
            # Weekend background
            if d.weekday() >= 5:
                weekend = QGraphicsRectItem(x, 0, DAY_WIDTH, HEADER_HEIGHT + self.sceneRect().height() - HEADER_HEIGHT)
                weekend.setBrush(QBrush(QColor(Palette.BG_DEEPEST)))
                weekend.setPen(Qt.NoPen)
                weekend.setZValue(-10)
                self._scene.addItem(weekend)
            # Date label
            date_label = QGraphicsTextItem(d.strftime("%b %d"))
            date_label.setDefaultTextColor(QColor(Palette.TEXT_SECONDARY))
            date_label.setFont(QFont("JetBrains Mono", 8))
            date_label.setPos(x + 4, 4)
            self._scene.addItem(date_label)
            # Day-of-week
            dow = QGraphicsTextItem(d.strftime("%a")[0])
            dow.setDefaultTextColor(QColor(Palette.TEXT_TERTIARY))
            dow.setFont(QFont("Inter", 7))
            dow.setPos(x + 4, 22)
            self._scene.addItem(dow)
            # Vertical line
            line = QGraphicsRectItem(x, 0, 1, HEADER_HEIGHT)
            line.setBrush(QBrush(QColor(Palette.BORDER_SUBTLE)))
            line.setPen(Qt.NoPen)
            self._scene.addItem(line)

    def _draw_left_panel(self, tasks: list[Task]) -> None:
        for i, task in enumerate(tasks):
            y = HEADER_HEIGHT + i * ROW_HEIGHT
            # Row background (alternating)
            if i % 2 == 0:
                bg = QGraphicsRectItem(0, y, LEFT_PANEL_WIDTH, ROW_HEIGHT)
                bg.setBrush(QBrush(QColor(Palette.BG_SECONDARY)))
                bg.setPen(Qt.NoPen)
                bg.setZValue(-5)
                self._scene.addItem(bg)
            # Title
            title = QGraphicsTextItem(task.title)
            title.setDefaultTextColor(
                QColor(Palette.GOLD_BRIGHT if task.is_critical else Palette.TEXT_PRIMARY)
            )
            title.setFont(QFont("Inter", 9, QFont.DemiBold if task.is_critical else QFont.Normal))
            title.setPos(8, y + 8)
            title.setTextWidth(LEFT_PANEL_WIDTH - 16)
            title.setToolTip(f"{task.title}\nID: {task.id}\nStatus: {task.status.value}")
            self._scene.addItem(title)

            # Vertical separator
            sep = QGraphicsRectItem(LEFT_PANEL_WIDTH - 1, y, 1, ROW_HEIGHT)
            sep.setBrush(QBrush(QColor(Palette.BORDER_SUBTLE)))
            sep.setPen(Qt.NoPen)
            self._scene.addItem(sep)

    def _draw_rows(self, tasks: list[Task], total_days: int) -> None:
        for i, task in enumerate(tasks):
            y = HEADER_HEIGHT + i * ROW_HEIGHT
            # Row stripe
            if i % 2 == 0:
                bg = QGraphicsRectItem(LEFT_PANEL_WIDTH, y, total_days * DAY_WIDTH, ROW_HEIGHT)
                bg.setBrush(QBrush(QColor(Palette.BG_SECONDARY)))
                bg.setPen(Qt.NoPen)
                bg.setZValue(-5)
                self._scene.addItem(bg)

            # Horizontal line at bottom
            line = QGraphicsRectItem(0, y + ROW_HEIGHT - 1,
                                     LEFT_PANEL_WIDTH + total_days * DAY_WIDTH, 1)
            line.setBrush(QBrush(QColor(Palette.BORDER_SUBTLE)))
            line.setPen(Qt.NoPen)
            self._scene.addItem(line)

            # Task bar
            if task.early_start and task.early_finish and self._start_date:
                bar_x = LEFT_PANEL_WIDTH + (task.early_start - self._start_date).total_seconds() / 86400 * DAY_WIDTH
                bar_w = max(DAY_WIDTH * 0.4,
                            (task.early_finish - task.early_start).total_seconds() / 86400 * DAY_WIDTH)
                bar_y = y + (ROW_HEIGHT - BAR_HEIGHT) // 2
                bar = GanttBar(task, QRectF(bar_x, bar_y, bar_w, BAR_HEIGHT))
                self._scene.addItem(bar)

                # Slack region (if any)
                if task.slack and task.slack.total_slack.minutes > 0 and task.late_start:
                    slack_x = LEFT_PANEL_WIDTH + (task.late_start - self._start_date).total_seconds() / 86400 * DAY_WIDTH
                    slack_w = (task.early_finish and task.late_start) and (
                        (task.late_start - task.early_finish).total_seconds() / 86400 * DAY_WIDTH
                    ) or 0
                    if slack_w > 1:
                        slack = QGraphicsRectItem(slack_x, bar_y + BAR_HEIGHT - 4, slack_w, 4)
                        slack.setBrush(QBrush(QColor(Palette.STATUS_DRAFT)))
                        slack.setPen(Qt.NoPen)
                        slack.setZValue(2)
                        self._scene.addItem(slack)

    def _on_selection_changed(self) -> None:
        pass

    def mouseDoubleClickEvent(self, event: QMouseEvent) -> None:
        item = self.itemAt(event.position().toPoint())
        if isinstance(item, GanttBar):
            self.taskDoubleClicked.emit(str(item.task.id))
        super().mouseDoubleClickEvent(event)


class GanttBar(QGraphicsRectItem):
    """A clickable task bar in the Gantt chart."""

    def __init__(self, task: Task, rect: QRectF) -> None:
        super().__init__(rect)
        self.task = task
        self.setFlag(QGraphicsItem.ItemIsSelectable, True)
        self.setAcceptHoverEvents(True)
        self.setZValue(3)
        self._refresh_brush()

    def _refresh_brush(self) -> None:
        if self.task.is_critical:
            color = QColor(Palette.GOLD_BRIGHT)
        else:
            color = QColor(status_color(self.task.status.value))
        # Gradient: lighter at top
        from PySide6.QtGui import QLinearGradient
        grad = QLinearGradient(0, self.rect().top(), 0, self.rect().bottom())
        light = QColor(color)
        light = light.lighter(130)
        grad.setColorAt(0, light)
        grad.setColorAt(1, color)
        self.setBrush(QBrush(grad))
        self.setPen(QPen(color.darker(150), 1))

    def paint(self, painter: QPainter, option: QStyleOptionGraphicsItem, widget=None) -> None:
        super().paint(painter, option, widget)
        # Progress overlay
        if self.task.progress.percent > 0:
            r = self.rect()
            fill_w = r.width() * self.task.progress.percent / 100
            painter.fillRect(QRectF(r.left(), r.top(), fill_w, r.height()),
                             QColor(255, 255, 255, 50))
        # Title text inside bar
        if r.width() > 60:
            painter.setPen(QPen(QColor(Palette.TEXT_ON_GOLD) if self.task.is_critical
                                else QColor(Palette.TEXT_PRIMARY)))
            painter.setFont(QFont("Inter", 8, QFont.DemiBold))
            painter.drawText(r.adjusted(6, 0, -4, 0),
                             Qt.AlignLeft | Qt.AlignVCenter,
                             self._elide(self.task.title, r.width() - 12))

    def _elide(self, text: str, max_w: float) -> str:
        from PySide6.QtGui import QFontMetrics
        fm = QFontMetrics(QFont("Inter", 8, QFont.DemiBold))
        if fm.horizontalAdvance(text) <= max_w:
            return text
        while text and fm.horizontalAdvance(text + "…") > max_w:
            text = text[:-1]
        return text + "…" if text else "…"

    def hoverEnterEvent(self, event):
        self.setZValue(10)
        self.setToolTip(
            f"<b>{self.task.title}</b><br>"
            f"Status: {self.task.status.value}<br>"
            f"Duration: {self.task.duration.humanize()}<br>"
            f"Progress: {self.task.progress.percent}%<br>"
            f"Critical: {'YES' if self.task.is_critical else 'no'}"
        )
        super().hoverEnterEvent(event)

    def hoverLeaveEvent(self, event):
        self.setZValue(3)
        super().hoverLeaveEvent(event)

    def mouseDoubleClickEvent(self, event):
        # Let the view handle it
        super().mouseDoubleClickEvent(event)
