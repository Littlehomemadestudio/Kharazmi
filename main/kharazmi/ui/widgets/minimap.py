"""
MinimapOverlay — a tiny overview of the entire node graph shown in
the corner of the node graph view.

Shows the entire scene as a small rectangle and highlights the
current viewport. Clicking on the minimap scrolls the view.
"""
from __future__ import annotations

from PySide6.QtCore import Qt, QRectF, QPointF, Signal, QSize
from PySide6.QtGui import (
    QPainter, QPen, QBrush, QColor, QFont, QPainterPath, QMouseEvent,
)
from PySide6.QtWidgets import QWidget

from ..theme import Palette


class MinimapOverlay(QWidget):
    """A small overview map overlay."""

    def __init__(self, view, parent: QWidget = None) -> None:
        super().__init__(parent)
        self._view = view
        self.setFixedSize(180, 120)
        self.setAttribute(Qt.WA_StyledBackground)
        self.setStyleSheet(f"""
            MinimapOverlay {{
                background-color: rgba(8, 8, 10, 220);
                border: 1px solid {Palette.BORDER_GOLD};
                border-radius: 4px;
            }}
        """)
        self.setCursor(Qt.PointingHandCursor)

    def update_minimap(self) -> None:
        self.update()

    def paintEvent(self, event) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing, True)
        try:
            scene = self._view.scene()
            if scene is None:
                return
            items_rect = scene.itemsBoundingRect()
            if items_rect.isNull():
                items_rect = QRectF(0, 0, 100, 100)

            # Compute scale to fit
            margin = 6
            w = self.width() - 2 * margin
            h = self.height() - 2 * margin
            sx = w / max(items_rect.width(), 1)
            sy = h / max(items_rect.height(), 1)
            s = min(sx, sy)

            # Map items_rect to local
            def to_local(pt: QPointF) -> QPointF:
                x = margin + (pt.x() - items_rect.left()) * s
                y = margin + (pt.y() - items_rect.top()) * s
                return QPointF(x, y)

            # Background
            p.fillRect(self.rect(), QColor(8, 8, 10, 200))

            # Draw nodes as tiny rectangles
            from .task_node_item import TaskNodeItem
            from .edge_item import EdgeItem
            for item in scene.items():
                if isinstance(item, TaskNodeItem):
                    r = item.sceneBoundingRect()
                    top_left = to_local(r.topLeft())
                    bot_right = to_local(r.bottomRight())
                    rect = QRectF(top_left, bot_right)
                    color = QColor(Palette.GOLD_BRIGHT) if item.task.is_critical else QColor(Palette.TEXT_TERTIARY)
                    p.setBrush(QBrush(color))
                    p.setPen(Qt.NoPen)
                    p.drawRect(rect)

            # Viewport rectangle
            viewport_rect = self._view.mapToScene(self._view.viewport().rect()).boundingRect()
            tl = to_local(viewport_rect.topLeft())
            br = to_local(viewport_rect.bottomRight())
            p.setBrush(Qt.NoBrush)
            p.setPen(QPen(QColor(Palette.GOLD_BRIGHT), 1.5))
            p.drawRect(QRectF(tl, br))
        finally:
            p.end()

    def mousePressEvent(self, event: QMouseEvent) -> None:
        self._navigate_to(event.position())
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        if event.buttons() & Qt.LeftButton:
            self._navigate_to(event.position())
        super().mouseMoveEvent(event)

    def _navigate_to(self, pos: QPointF) -> None:
        scene = self._view.scene()
        if scene is None:
            return
        items_rect = scene.itemsBoundingRect()
        if items_rect.isNull():
            return
        margin = 6
        w = self.width() - 2 * margin
        h = self.height() - 2 * margin
        s = min(w / max(items_rect.width(), 1),
                h / max(items_rect.height(), 1))
        scene_x = items_rect.left() + (pos.x() - margin) / s
        scene_y = items_rect.top() + (pos.y() - margin) / s
        self._view.centerOn(QPointF(scene_x, scene_y))
