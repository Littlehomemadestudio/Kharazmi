"""KanbanView — task board grouped by status."""
from __future__ import annotations

from typing import Optional

from PySide6.QtCore import Qt, Signal, QSize, QPoint, QMimeData
from PySide6.QtGui import (
    QPainter, QPen, QBrush, QColor, QFont, QAction, QDragEnterEvent,
    QDropEvent, QMouseEvent, QPixmap,
)
from PySide6.QtWidgets import (
    QWidget, QScrollArea, QVBoxLayout, QHBoxLayout, QLabel, QFrame,
    QSizePolicy, QGridLayout, QPushButton, QToolButton, QMenu,
    QGraphicsDropShadowEffect, QSpacerItem,
)

from ...core import (
    Project, Task, TaskId, TaskStatus, Priority,
)
from ...services import TaskService
from ..theme import Palette, status_color
from ..icons import get_icon


STATUS_ORDER = [
    TaskStatus.DRAFT,
    TaskStatus.READY,
    TaskStatus.ACTIVE,
    TaskStatus.BLOCKED,
    TaskStatus.DEFERRED,
    TaskStatus.DONE,
    TaskStatus.CANCELLED,
]


class KanbanCard(QFrame):
    """A single task card."""
    cardClicked = Signal(str)
    cardDoubleClicked = Signal(str)
    statusChangeRequested = Signal(str, str)  # task_id, new_status

    DRAG_MIME = "application/x-kharazmi-task-id"

    def __init__(self, task: Task, parent: QWidget = None) -> None:
        super().__init__(parent)
        self.task = task
        self.setFrameShape(QFrame.NoFrame)
        self.setFixedWidth(220)
        self.setMinimumHeight(110)
        self.setCursor(Qt.PointingHandCursor)
        self.setAcceptDrops(False)
        self.setObjectName("kanbanCard")
        self.setStyleSheet(f"""
            QFrame#kanbanCard {{
                background-color: {Palette.BG_TERTIARY};
                border: 1px solid {Palette.BORDER_NORMAL};
                border-left: 3px solid {status_color(task.status.value)};
                border-radius: 4px;
                padding: 8px;
            }}
            QFrame#kanbanCard:hover {{
                border: 1px solid {Palette.BORDER_GOLD};
                border-left: 3px solid {status_color(task.status.value)};
                background-color: {Palette.BG_ELEVATED};
            }}
        """)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 8, 10, 8)
        layout.setSpacing(4)

        # Title
        title = QLabel(task.title)
        title.setWordWrap(True)
        title.setStyleSheet(
            f"color: {Palette.GOLD_BRIGHT if task.is_critical else Palette.TEXT_PRIMARY}; "
            f"font-weight: {'bold' if task.is_critical else 'normal'}; "
            f"font-size: 13px;"
        )
        layout.addWidget(title)

        # Duration / progress
        meta = QLabel(f"{task.duration.humanize()}  •  {task.progress.percent}%")
        meta.setStyleSheet(f"color: {Palette.TEXT_SECONDARY}; font-size: 11px;")
        layout.addWidget(meta)

        # Tags
        if task.tags:
            tags_label = QLabel(" ".join(f"#{t}" for t in sorted(str(x) for x in task.tags)))
            tags_label.setStyleSheet(f"color: {Palette.GOLD_PRIMARY}; font-size: 10px; font-family: 'JetBrains Mono', monospace;")
            tags_label.setWordWrap(True)
            layout.addWidget(tags_label)

        # Priority dots
        prio_row = QHBoxLayout()
        prio_row.setSpacing(3)
        for i in range(5):
            dot = QFrame()
            dot.setFixedSize(8, 8)
            color = Palette.GOLD_PRIMARY if i < int(task.priority) + 1 else Palette.BG_DEEPEST
            dot.setStyleSheet(f"background-color: {color}; border-radius: 4px;")
            prio_row.addWidget(dot)
        prio_row.addStretch()
        # Critical badge
        if task.is_critical:
            crit = QLabel("CRITICAL")
            crit.setStyleSheet(
                f"background-color: {Palette.GOLD_PRIMARY}; color: {Palette.TEXT_ON_GOLD}; "
                f"font-size: 9px; font-weight: bold; padding: 1px 6px; border-radius: 3px; "
                f"letter-spacing: 0.8px;"
            )
            prio_row.addWidget(crit)
        layout.addLayout(prio_row)

        layout.addStretch()

    def mousePressEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.LeftButton:
            self.cardClicked.emit(str(self.task.id))
            self._drag_start = event.position().toPoint()
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        if event.buttons() & Qt.LeftButton and hasattr(self, "_drag_start"):
            delta = event.position().toPoint() - self._drag_start
            if delta.manhattanLength() > 5:
                from PySide6.QtCore import QDrag
                drag = QDrag(self)
                mime = QMimeData()
                mime.setText(self.DRAG_MIME)
                mime.setData(self.DRAG_MIME, str(self.task.id).encode())
                drag.setMimeData(mime)
                # Pixmap preview
                pm = QPixmap(self.size())
                self.render(pm)
                drag.setPixmap(pm)
                drag.setHotSpot(self._drag_start)
                drag.exec_(Qt.MoveAction)
        super().mouseMoveEvent(event)

    def mouseDoubleClickEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.LeftButton:
            self.cardDoubleClicked.emit(str(self.task.id))
        super().mouseDoubleClickEvent(event)


class KanbanColumn(QFrame):
    """A vertical column of cards for one status."""
    cardDropped = Signal(str, str)  # task_id, target_status

    def __init__(self, status: TaskStatus, parent: QWidget = None) -> None:
        super().__init__(parent)
        self.status = status
        self.setAcceptDrops(True)
        self.setMinimumWidth(240)
        self.setMaximumWidth(280)
        self.setObjectName("kanbanColumn")
        self.setStyleSheet(f"""
            QFrame#kanbanColumn {{
                background-color: {Palette.BG_SECONDARY};
                border: 1px solid {Palette.BORDER_SUBTLE};
                border-radius: 6px;
            }}
        """)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(6)

        # Header
        header = QHBoxLayout()
        title = QLabel(status.value.upper())
        title.setStyleSheet(
            f"color: {status_color(status.value)}; "
            f"font-size: 11px; font-weight: bold; letter-spacing: 1.5px;"
        )
        header.addWidget(title)
        header.addStretch()
        self.count_label = QLabel("0")
        self.count_label.setStyleSheet(
            f"color: {Palette.TEXT_TERTIARY}; font-size: 11px; font-weight: bold; "
            f"background-color: {Palette.BG_DEEPEST}; padding: 1px 8px; border-radius: 8px;"
        )
        header.addWidget(self.count_label)
        layout.addLayout(header)

        # Cards container
        self.cards_layout = QVBoxLayout()
        self.cards_layout.setSpacing(6)
        layout.addLayout(self.cards_layout)
        layout.addStretch()

    def dragEnterEvent(self, event: QDragEnterEvent) -> None:
        if event.mimeData().hasFormat(KanbanCard.DRAG_MIME):
            event.acceptProposedAction()
            self.setStyleSheet(f"""
                QFrame#kanbanColumn {{
                    background-color: {Palette.BG_SELECTED};
                    border: 2px dashed {Palette.GOLD_PRIMARY};
                    border-radius: 6px;
                }}
            """)
        else:
            event.ignore()

    def dragLeaveEvent(self, event) -> None:
        self.setStyleSheet(f"""
            QFrame#kanbanColumn {{
                background-color: {Palette.BG_SECONDARY};
                border: 1px solid {Palette.BORDER_SUBTLE};
                border-radius: 6px;
            }}
        """)
        super().dragLeaveEvent(event)

    def dropEvent(self, event: QDropEvent) -> None:
        mime = event.mimeData()
        if mime.hasFormat(KanbanCard.DRAG_MIME):
            task_id = bytes(mime.data(KanbanCard.DRAG_MIME)).decode()
            self.cardDropped.emit(task_id, self.status.value)
            event.acceptProposedAction()
        self.setStyleSheet(f"""
            QFrame#kanbanColumn {{
                background-color: {Palette.BG_SECONDARY};
                border: 1px solid {Palette.BORDER_SUBTLE};
                border-radius: 6px;
            }}
        """)

    def set_cards(self, cards: list[KanbanCard]) -> None:
        # Clear old
        while self.cards_layout.count():
            item = self.cards_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        for card in cards:
            self.cards_layout.addWidget(card)
        self.count_label.setText(str(len(cards)))


class KanbanView(QScrollArea):
    """The kanban board."""

    taskDoubleClicked = Signal(str)

    def __init__(self, project: Project, task_service: TaskService,
                 parent: QWidget = None) -> None:
        super().__init__(parent)
        self.project = project
        self.task_service = task_service

        self.setWidgetResizable(True)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.setFrameShape(QFrame.NoFrame)

        container = QWidget()
        self._container_layout = QHBoxLayout(container)
        self._container_layout.setContentsMargins(12, 12, 12, 12)
        self._container_layout.setSpacing(10)

        self._columns: dict[TaskStatus, KanbanColumn] = {}
        for status in STATUS_ORDER:
            col = KanbanColumn(status)
            col.cardDropped.connect(self._on_card_dropped)
            self._columns[status] = col
            self._container_layout.addWidget(col)

        self._container_layout.addStretch()
        self.setWidget(container)

        self._rebuild()

    def refresh(self) -> None:
        self._rebuild()

    def _rebuild(self) -> None:
        for status in STATUS_ORDER:
            tasks = [t for t in self.project.tasks() if t.status == status]
            tasks.sort(key=lambda t: (-int(t.priority), t.title.lower()))
            cards = [KanbanCard(t) for t in tasks]
            for card in cards:
                card.cardDoubleClicked.connect(self.taskDoubleClicked.emit)
            self._columns[status].set_cards(cards)

    def _on_card_dropped(self, task_id_str: str, new_status_str: str) -> None:
        new_status = TaskStatus(new_status_str)
        self.task_service.change_status(TaskId(task_id_str), new_status)
        self._rebuild()
