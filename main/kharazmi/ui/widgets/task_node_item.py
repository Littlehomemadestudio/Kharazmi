"""
TaskNodeItem — the QGraphicsItem that renders a single task in the
node-graph view.

Each node is a rounded rectangle showing:
  - Title (top)
  - Status indicator dot
  - Duration bar
  - Priority stripes
  - Progress bar
  - Critical-path glow (if applicable)

Nodes are draggable, selectable, and emit signals when interacted with.
"""
from __future__ import annotations

from PySide6.QtCore import (
    Qt, QRectF, QPointF, QSizeF, QEvent, Signal,
)
from PySide6.QtGui import (
    QPainter, QPainterPath, QColor, QPen, QBrush, QFont, QLinearGradient,
    QRadialGradient, QFontMetrics, QPolygonF,
)
from PySide6.QtWidgets import (
    QGraphicsItem, QGraphicsObject, QGraphicsSceneMouseEvent,
    QGraphicsSceneHoverEvent, QStyleOptionGraphicsItem, QWidget,
)

from ...core import Task, TaskStatus
from ..theme import Palette, status_color


NODE_WIDTH = 220
NODE_HEIGHT = 96


class TaskNodeItem(QGraphicsObject):
    """
    A draggable task node.

    Signals:
      - nodeDoubleClicked(task_id): emitted on double-click
      - nodeMoved(task_id, x, y):   emitted after a drag ends
    """
    nodeDoubleClicked = Signal(str)
    nodeMoved = Signal(str, float, float)

    def __init__(self, task: Task, parent: QGraphicsItem = None) -> None:
        super().__init__(parent)
        self.task = task
        self._hovered = False
        self._drag_started_pos: QPointF | None = None

        self.setFlag(QGraphicsItem.ItemIsMovable, True)
        self.setFlag(QGraphicsItem.ItemIsSelectable, True)
        self.setFlag(QGraphicsItem.ItemSendsGeometryChanges, True)
        self.setAcceptHoverEvents(True)
        self.setPos(task.x, task.y)

        self.setZValue(10)

    # ---- Geometry ----
    def boundingRect(self) -> QRectF:
        # Expand slightly for the critical-path glow
        if self.task.is_critical:
            return QRectF(-6, -6, NODE_WIDTH + 12, NODE_HEIGHT + 12)
        return QRectF(0, 0, NODE_WIDTH, NODE_HEIGHT)

    def shape(self) -> QPainterPath:
        path = QPainterPath()
        path.addRoundedRect(0, 0, NODE_WIDTH, NODE_HEIGHT, 8, 8)
        return path

    # ---- Painting ----
    def paint(self, painter: QPainter, option: QStyleOptionGraphicsItem,
              widget: QWidget = None) -> None:
        painter.setRenderHint(QPainter.Antialiasing, True)

        # 1. Critical-path glow
        if self.task.is_critical:
            glow = QRadialGradient(NODE_WIDTH / 2, NODE_HEIGHT / 2, NODE_WIDTH * 0.7)
            glow.setColorAt(0, QColor(245, 200, 66, 70))
            glow.setColorAt(1, QColor(245, 200, 66, 0))
            painter.setBrush(QBrush(glow))
            painter.setPen(Qt.NoPen)
            painter.drawRoundedRect(-6, -6, NODE_WIDTH + 12, NODE_HEIGHT + 12, 12, 12)

        # 2. Selection / hover halo
        selected = self.isSelected()
        if selected:
            painter.setBrush(QBrush(QColor(Palette.GOLD_MUTED)))
            painter.setPen(QPen(QColor(Palette.GOLD_BRIGHT), 2))
            painter.drawRoundedRect(-2, -2, NODE_WIDTH + 4, NODE_HEIGHT + 4, 10, 10)
        elif self._hovered:
            painter.setBrush(QBrush(QColor(0, 0, 0, 80)))
            painter.setPen(QPen(QColor(Palette.GOLD_PRIMARY), 1))
            painter.drawRoundedRect(-1, -1, NODE_WIDTH + 2, NODE_HEIGHT + 2, 9, 9)

        # 3. Background gradient
        bg = QLinearGradient(0, 0, 0, NODE_HEIGHT)
        bg.setColorAt(0, QColor(Palette.BG_ELEVATED))
        bg.setColorAt(1, QColor(Palette.BG_TERTIARY))
        painter.setBrush(QBrush(bg))
        border_color = QColor(Palette.GOLD_PRIMARY) if self.task.is_critical else QColor(Palette.BORDER_NORMAL)
        border_width = 1.5 if self.task.is_critical else 1.0
        painter.setPen(QPen(border_color, border_width))
        painter.drawRoundedRect(0, 0, NODE_WIDTH, NODE_HEIGHT, 8, 8)

        # 4. Left status accent bar
        sc = QColor(status_color(self.task.status.value))
        painter.setBrush(QBrush(sc))
        painter.setPen(Qt.NoPen)
        path = QPainterPath()
        path.addRoundedRect(QRectF(0, 0, 4, NODE_HEIGHT), 2, 2)
        painter.fillPath(path, QBrush(sc))

        # 5. Title
        title_font = QFont("Inter", 10, QFont.DemiBold)
        painter.setFont(title_font)
        title_color = QColor(Palette.GOLD_BRIGHT) if self.task.is_critical else QColor(Palette.TEXT_PRIMARY)
        painter.setPen(QPen(title_color))
        title = self._elide_text(self.task.title, NODE_WIDTH - 50, title_font)
        painter.drawText(QRectF(12, 8, NODE_WIDTH - 50, 22), Qt.AlignLeft | Qt.AlignVCenter, title)

        # 6. Status pill (top right)
        status_text = self.task.status.value.upper()
        pill_font = QFont("Inter", 7, QFont.Bold)
        painter.setFont(pill_font)
        fm = QFontMetrics(pill_font)
        pill_w = fm.horizontalAdvance(status_text) + 12
        pill_h = 14
        pill_x = NODE_WIDTH - pill_w - 8
        pill_y = 10
        painter.setBrush(QBrush(sc))
        painter.setPen(Qt.NoPen)
        painter.drawRoundedRect(QRectF(pill_x, pill_y, pill_w, pill_h), 7, 7)
        painter.setPen(QPen(QColor(Palette.TEXT_PRIMARY)))
        painter.drawText(QRectF(pill_x, pill_y, pill_w, pill_h),
                         Qt.AlignCenter, status_text)

        # 7. Duration line
        meta_font = QFont("JetBrains Mono", 8)
        painter.setFont(meta_font)
        painter.setPen(QPen(QColor(Palette.TEXT_SECONDARY)))
        dur_text = self.task.duration.humanize()
        if self.task.pert is not None:
            dur_text += "  σ=" + f"{self.task.pert.std_dev:.0f}m"
        painter.drawText(QRectF(12, 32, NODE_WIDTH - 24, 14), Qt.AlignLeft, dur_text)

        # 8. Slack / dates
        if self.task.early_start is not None and self.task.slack is not None:
            date_str = ""
            if self.task.early_start is not None:
                from ...core.shamsi import ShamsiDate
                sd = ShamsiDate.from_datetime(self.task.early_start)
                date_str = f"{sd.month_name_en[:3]} {sd.day}"
            if self.task.is_critical:
                slack_str = "CRITICAL"
            else:
                slack_str = f"slack {self.task.slack.total_slack.humanize()}"
            painter.setPen(QPen(QColor(Palette.GOLD_PRIMARY if self.task.is_critical else Palette.TEXT_TERTIARY)))
            painter.drawText(QRectF(12, 46, NODE_WIDTH - 24, 14), Qt.AlignLeft, f"{date_str}  •  {slack_str}")

        # 9. Priority stripes (bottom right)
        p_count = int(self.task.priority) + 1
        for i in range(p_count):
            painter.setBrush(QBrush(QColor(Palette.GOLD_PRIMARY)))
            painter.setPen(Qt.NoPen)
            painter.drawRect(QRectF(NODE_WIDTH - 8 - (p_count - i) * 6, NODE_HEIGHT - 10, 4, 6))

        # 10. Progress bar
        bar_x = 12
        bar_y = NODE_HEIGHT - 14
        bar_w = NODE_WIDTH - 24 - (p_count * 6 + 4)
        bar_h = 4
        painter.setBrush(QBrush(QColor(Palette.BG_DEEPEST)))
        painter.setPen(QPen(QColor(Palette.BORDER_SUBTLE), 0.5))
        painter.drawRoundedRect(QRectF(bar_x, bar_y, bar_w, bar_h), 2, 2)
        if self.task.progress.percent > 0:
            fill_w = int(bar_w * self.task.progress.percent / 100)
            painter.setBrush(QBrush(QColor(Palette.GOLD_BRIGHT if self.task.is_critical else Palette.GOLD_PRIMARY)))
            painter.setPen(Qt.NoPen)
            painter.drawRoundedRect(QRectF(bar_x, bar_y, fill_w, bar_h), 2, 2)

        # 11. Resource dots
        if self.task.resources:
            for i, alloc in enumerate(self.task.resources[:5]):
                painter.setBrush(QBrush(QColor(Palette.GOLD_DEEP)))
                painter.setPen(Qt.NoPen)
                painter.drawEllipse(QPointF(bar_x + 2 + i * 8, bar_y - 8), 2, 2)

    def _elide_text(self, text: str, max_width: float, font: QFont) -> str:
        fm = QFontMetrics(font)
        if fm.horizontalAdvance(text) <= max_width:
            return text
        elided = text
        while elided and fm.horizontalAdvance(elided + "…") > max_width:
            elided = elided[:-1]
        return elided + "…" if elided else "…"

    # ---- Interaction ----
    def hoverEnterEvent(self, event: QGraphicsSceneHoverEvent) -> None:
        self._hovered = True
        self.setZValue(20)
        self.update()
        super().hoverEnterEvent(event)

    def hoverLeaveEvent(self, event: QGraphicsSceneHoverEvent) -> None:
        self._hovered = False
        self.setZValue(10 if not self.isSelected() else 15)
        self.update()
        super().hoverLeaveEvent(event)

    def mousePressEvent(self, event: QGraphicsSceneMouseEvent) -> None:
        if event.button() == Qt.LeftButton:
            self._drag_started_pos = self.pos()
        super().mousePressEvent(event)

    def mouseDoubleClickEvent(self, event: QGraphicsSceneMouseEvent) -> None:
        if event.button() == Qt.LeftButton:
            self.nodeDoubleClicked.emit(str(self.task.id))
        super().mouseDoubleClickEvent(event)

    def mouseReleaseEvent(self, event: QGraphicsSceneMouseEvent) -> None:
        super().mouseReleaseEvent(event)
        if self._drag_started_pos is not None:
            new_pos = self.pos()
            if (new_pos - self._drag_started_pos).manhattanLength() > 2:
                self.task.x = new_pos.x()
                self.task.y = new_pos.y()
                self.task.touch()
                self.nodeMoved.emit(str(self.task.id), new_pos.x(), new_pos.y())
            self._drag_started_pos = None

    def itemChange(self, change, value):
        if change == QGraphicsItem.ItemSelectedHasChanged:
            self.setZValue(15 if self.isSelected() else 10)
            self.update()
        return super().itemChange(change, value)

    # ---- Public API ----
    def refresh_from_task(self) -> None:
        """Re-read task data (in case it changed externally) and repaint."""
        self.update()

    @property
    def anchor_in(self) -> QPointF:
        """Anchor point for incoming edges (left side)."""
        return self.mapToScene(QPointF(0, NODE_HEIGHT / 2))

    @property
    def anchor_out(self) -> QPointF:
        """Anchor point for outgoing edges (right side)."""
        return self.mapToScene(QPointF(NODE_WIDTH, NODE_HEIGHT / 2))

    @property
    def anchor_top(self) -> QPointF:
        return self.mapToScene(QPointF(NODE_WIDTH / 2, 0))

    @property
    def anchor_bottom(self) -> QPointF:
        return self.mapToScene(QPointF(NODE_WIDTH / 2, NODE_HEIGHT))
