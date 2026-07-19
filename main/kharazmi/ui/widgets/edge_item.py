"""
EdgeItem — the QGraphicsItem that renders a dependency between two
task nodes.

Edges are curved bezier lines. The style depends on the dependency
type:
  - FS: solid line, arrow at end
  - FF: dashed line, arrow at end
  - SS: dotted line, arrow at start
  - SF: dash-dot line

Critical-path edges are rendered in gold; others are muted gray.
A small badge in the middle shows the dependency type label.
"""
from __future__ import annotations

from PySide6.QtCore import Qt, QRectF, QPointF, QLineF
from PySide6.QtGui import (
    QPainter, QPainterPath, QColor, QPen, QBrush, QFont, QPolygonF,
    QLinearGradient,
)
from PySide6.QtWidgets import (
    QGraphicsItem, QGraphicsPathItem, QGraphicsObject,
    QStyleOptionGraphicsItem, QWidget,
)

from ...core import Dependency, DependencyType
from ..theme import Palette


HEAD_SIZE = 9


class EdgeItem(QGraphicsObject):
    """
    A dependency edge between two TaskNodeItems.

    Tracks the source and target nodes; recomputes its path whenever
    either moves.
    """
    def __init__(self, dependency: Dependency,
                 source_item, target_item,
                 is_critical: bool = False,
                 parent: QGraphicsItem = None) -> None:
        super().__init__(parent)
        self.dependency = dependency
        self.source_item = source_item
        self.target_item = target_item
        self._is_critical = is_critical
        self._path = QPainterPath()

        self.setZValue(5)
        self.setFlag(QGraphicsItem.ItemIsSelectable, True)
        self.setAcceptHoverEvents(True)

        # Track source/target position changes
        if source_item is not None:
            try:
                source_item.xChanged.connect(self._recompute_path)
                source_item.yChanged.connect(self._recompute_path)
            except Exception:
                pass
        if target_item is not None:
            try:
                target_item.xChanged.connect(self._recompute_path)
                target_item.yChanged.connect(self._recompute_path)
            except Exception:
                pass

        self._recompute_path()

    def boundingRect(self) -> QRectF:
        return self._path.boundingRect().adjusted(-10, -10, 10, 10)

    def shape(self) -> QPainterPath:
        # Wider hit area for easier selection
        stroker = QPainterPath()
        stroker.addPath(self._path)
        from PySide6.QtGui import QPainterPathStroker
        ps = QPainterPathStroker()
        ps.setWidth(10)
        return ps.createStroke(self._path)

    def paint(self, painter: QPainter, option: QStyleOptionGraphicsItem,
              widget: QWidget = None) -> None:
        painter.setRenderHint(QPainter.Antialiasing, True)

        # Pick color based on criticality
        if self._is_critical:
            base_color = QColor(Palette.GOLD_BRIGHT)
            glow_color = QColor(245, 200, 66, 60)
        else:
            base_color = QColor(Palette.TEXT_TERTIARY)
            glow_color = QColor(0, 0, 0, 0)

        # Pen style based on dependency type
        pen = QPen(base_color, 2 if self._is_critical else 1.4)
        pen.setCapStyle(Qt.RoundCap)
        dt = self.dependency.type
        if dt == DependencyType.FINISH_START:
            pen.setStyle(Qt.SolidLine)
        elif dt == DependencyType.FINISH_FINISH:
            pen.setStyle(Qt.DashLine)
        elif dt == DependencyType.START_START:
            pen.setStyle(Qt.DotLine)
        else:  # START_FINISH
            pen.setStyle(Qt.DashDotLine)

        if self.isSelected():
            pen.setColor(QColor(Palette.GOLD_BRIGHT))
            pen.setWidthF(pen.widthF() + 0.6)

        # Glow underlay for critical edges
        if self._is_critical:
            glow_pen = QPen(glow_color, 6)
            glow_pen.setCapStyle(Qt.RoundCap)
            painter.setPen(glow_pen)
            painter.drawPath(self._path)

        # Main stroke
        painter.setPen(pen)
        painter.drawPath(self._path)

        # Arrow head — at the END (target) for FS/FF, at the START (source) for SS/SF
        if dt in (DependencyType.FINISH_START, DependencyType.FINISH_FINISH):
            self._draw_arrow(painter, self._path, at_end=True, color=base_color)
        else:
            self._draw_arrow(painter, self._path, at_end=False, color=base_color)

        # Type badge
        self._draw_badge(painter, color=base_color)

    def _draw_arrow(self, painter: QPainter, path: QPainterPath,
                    at_end: bool, color: QColor) -> None:
        # Sample the path to get tangent direction at the tip
        try:
            length = path.length()
            if length < 1:
                return
            if at_end:
                tip = path.pointAtPercent(1.0)
                # Slightly before the tip to compute tangent
                back = path.pointAtPercent(max(0.0, 1.0 - HEAD_SIZE / length))
                direction = tip - back
            else:
                tip = path.pointAtPercent(0.0)
                ahead = path.pointAtPercent(min(1.0, HEAD_SIZE / length))
                direction = tip - ahead

            import math
            mag = math.hypot(direction.x(), direction.y())
            if mag < 1e-3:
                return
            ux, uy = direction.x() / mag, direction.y() / mag
            # Perpendicular
            px, py = -uy, ux
            p1 = tip
            p2 = QPointF(tip.x() - ux * HEAD_SIZE + px * HEAD_SIZE * 0.5,
                         tip.y() - uy * HEAD_SIZE + py * HEAD_SIZE * 0.5)
            p3 = QPointF(tip.x() - ux * HEAD_SIZE - px * HEAD_SIZE * 0.5,
                         tip.y() - uy * HEAD_SIZE - py * HEAD_SIZE * 0.5)
            poly = QPolygonF([p1, p2, p3])
            painter.setBrush(QBrush(color))
            painter.setPen(Qt.NoPen)
            painter.drawPolygon(poly)
        except Exception:
            pass

    def _draw_badge(self, painter: QPainter, color: QColor) -> None:
        try:
            mid = self._path.pointAtPercent(0.5)
            label = self.dependency.type.value
            font = QFont("JetBrains Mono", 7, QFont.Bold)
            painter.setFont(font)
            from PySide6.QtGui import QFontMetrics
            fm = QFontMetrics(font)
            w = fm.horizontalAdvance(label) + 8
            h = fm.height() + 2
            rect = QRectF(mid.x() - w / 2, mid.y() - h / 2, w, h)
            painter.setBrush(QBrush(QColor(Palette.BG_DEEPEST)))
            painter.setPen(QPen(color, 0.8))
            painter.drawRoundedRect(rect, 3, 3)
            painter.setPen(QPen(color))
            painter.drawText(rect, Qt.AlignCenter, label)
        except Exception:
            pass

    def _recompute_path(self) -> None:
        if self.source_item is None or self.target_item is None:
            return
        dt = self.dependency.type

        # Pick anchors based on dep type
        if dt == DependencyType.FINISH_START:
            start = self.source_item.anchor_out
            end = self.target_item.anchor_in
        elif dt == DependencyType.FINISH_FINISH:
            start = self.source_item.anchor_out
            end = self.target_item.anchor_out
        elif dt == DependencyType.START_START:
            start = self.source_item.anchor_in
            end = self.target_item.anchor_in
        else:  # START_FINISH
            start = self.source_item.anchor_in
            end = self.target_item.anchor_out

        # Map to LOCAL coordinates (this item's coord system)
        start_local = self.mapFromScene(start)
        end_local = self.mapFromScene(end)

        path = QPainterPath(start_local)
        # Cubic bezier with horizontal control points for a smooth S-curve
        dx = end_local.x() - start_local.x()
        cx1 = start_local.x() + dx * 0.5
        cx2 = end_local.x() - dx * 0.5
        path.cubicTo(QPointF(cx1, start_local.y()),
                     QPointF(cx2, end_local.y()),
                     end_local)
        self._path = path
        self.prepareGeometryChange()
        self.update()

    def set_critical(self, critical: bool) -> None:
        if self._is_critical != critical:
            self._is_critical = critical
            self.setZValue(8 if critical else 5)
            self.update()
