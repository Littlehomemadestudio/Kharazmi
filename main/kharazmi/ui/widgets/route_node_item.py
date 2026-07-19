"""
RouteNodeItem — a QGraphicsItem that renders a single RouteStep.

Distinct from the Enterprise TaskNodeItem — this one shows:
  - Step ID and title
  - Duration estimate
  - Success probability (as a colored ring + percentage)
  - Risk level badge
  - Location
  - Fallback indicator (if any)
  - Sub-goals count
  - Dependency arrows in/out

Color scheme is tied to risk level:
  low      → green-ish gold
  medium   → gold
  high     → orange
  severe   → red

Steps with low success probability get a pulsing border.
"""
from __future__ import annotations

import math
from typing import Optional

from PySide6.QtCore import Qt, QRectF, QPointF, Signal
from PySide6.QtGui import (
    QPainter, QPainterPath, QColor, QPen, QBrush, QFont, QLinearGradient,
    QRadialGradient, QFontMetrics, QPolygonF,
)
from PySide6.QtWidgets import (
    QGraphicsObject, QGraphicsItem, QGraphicsSceneMouseEvent,
    QGraphicsSceneHoverEvent, QStyleOptionGraphicsItem, QWidget,
)

from ...ai import RouteStep
from ..theme import Palette


NODE_WIDTH = 240
NODE_HEIGHT = 120


_RISK_COLORS = {
    "low":      "#5A8A5A",  # muted green
    "medium":   "#D4AF37",  # gold
    "high":     "#A87A4A",  # orange
    "severe":   "#A85A5A",  # red
}


class RouteNodeItem(QGraphicsObject):
    """
    A draggable route-step node.

    Signals:
      - nodeClicked(step_id)
      - nodeDoubleClicked(step_id)
      - nodeMoved(step_id, x, y)
    """
    nodeClicked = Signal(str)
    nodeDoubleClicked = Signal(str)
    nodeMoved = Signal(str, float, float)

    def __init__(self, step: RouteStep, parent: QGraphicsItem = None) -> None:
        super().__init__(parent)
        self.step = step
        self._hovered = False
        self._drag_started_pos: Optional[QPointF] = None

        self.setFlag(QGraphicsItem.ItemIsMovable, True)
        self.setFlag(QGraphicsItem.ItemIsSelectable, True)
        self.setFlag(QGraphicsItem.ItemSendsGeometryChanges, True)
        self.setAcceptHoverEvents(True)
        self.setZValue(10)

    # ---- Geometry ----
    def boundingRect(self) -> QRectF:
        # Extra space for success ring
        return QRectF(-8, -8, NODE_WIDTH + 16, NODE_HEIGHT + 16)

    def shape(self) -> QPainterPath:
        path = QPainterPath()
        path.addRoundedRect(0, 0, NODE_WIDTH, NODE_HEIGHT, 10, 10)
        return path

    # ---- Painting ----
    def paint(self, painter: QPainter, option: QStyleOptionGraphicsItem,
              widget: QWidget = None) -> None:
        painter.setRenderHint(QPainter.Antialiasing, True)

        risk_color_str = _RISK_COLORS.get(self.step.risk_level, _RISK_COLORS["medium"])
        risk_color = QColor(risk_color_str)

        # 1. Selection / hover halo
        if self.isSelected():
            painter.setBrush(QBrush(QColor(255, 255, 255, 30)))
            painter.setPen(QPen(QColor(Palette.GOLD_BRIGHT), 2))
            painter.drawRoundedRect(-2, -2, NODE_WIDTH + 4, NODE_HEIGHT + 4, 12, 12)
        elif self._hovered:
            painter.setBrush(QBrush(QColor(0, 0, 0, 80)))
            painter.setPen(QPen(risk_color, 1))
            painter.drawRoundedRect(-1, -1, NODE_WIDTH + 2, NODE_HEIGHT + 2, 11, 11)

        # 2. Background gradient
        bg = QLinearGradient(0, 0, 0, NODE_HEIGHT)
        bg.setColorAt(0, QColor(Palette.BG_ELEVATED))
        bg.setColorAt(1, QColor(Palette.BG_TERTIARY))
        painter.setBrush(QBrush(bg))
        painter.setPen(QPen(risk_color, 1.5))
        painter.drawRoundedRect(0, 0, NODE_WIDTH, NODE_HEIGHT, 10, 10)

        # 3. Left risk-color stripe
        painter.setBrush(QBrush(risk_color))
        painter.setPen(Qt.NoPen)
        path = QPainterPath()
        path.addRoundedRect(QRectF(0, 0, 4, NODE_HEIGHT), 2, 2)
        painter.fillPath(path, QBrush(risk_color))

        # 4. Step ID badge (top-left)
        id_font = QFont("JetBrains Mono", 8, QFont.Bold)
        painter.setFont(id_font)
        painter.setBrush(QBrush(risk_color))
        painter.setPen(Qt.NoPen)
        painter.drawRoundedRect(QRectF(10, 10, 36, 18), 4, 4)
        painter.setPen(QPen(QColor(Palette.TEXT_ON_GOLD)))
        painter.drawText(QRectF(10, 10, 36, 18), Qt.AlignCenter, self.step.id.upper())

        # 5. Title
        title_font = QFont("Inter", 10, QFont.DemiBold)
        painter.setFont(title_font)
        painter.setPen(QPen(QColor(Palette.TEXT_PRIMARY)))
        title = self._elide_text(self.step.title, NODE_WIDTH - 60, title_font)
        painter.drawText(QRectF(54, 8, NODE_WIDTH - 64, 22),
                         Qt.AlignLeft | Qt.AlignVCenter, title)

        # 6. Duration (top-right)
        dur_font = QFont("JetBrains Mono", 9, QFont.Bold)
        painter.setFont(dur_font)
        dur_text = f"⏱ {self.step.duration_minutes}m"
        painter.setPen(QPen(QColor(Palette.GOLD_BRIGHT)))
        painter.drawText(QRectF(NODE_WIDTH - 80, 8, 70, 22),
                         Qt.AlignRight | Qt.AlignVCenter, dur_text)

        # 7. Success probability ring (left side, below ID)
        ring_center = QPointF(34, 64)
        ring_radius = 16
        # Background ring
        painter.setBrush(Qt.NoBrush)
        painter.setPen(QPen(QColor(Palette.BG_DEEPEST), 4))
        painter.drawEllipse(ring_center, ring_radius, ring_radius)
        # Foreground arc
        prob = max(0.0, min(1.0, self.step.success_probability))
        prob_color = QColor(risk_color)
        if prob > 0.7:
            prob_color = QColor(Palette.GOLD_BRIGHT)
        elif prob < 0.4:
            prob_color = QColor(Palette.STATUS_BLOCKED)
        painter.setPen(QPen(prob_color, 4, Qt.SolidLine, Qt.RoundCap))
        # Draw arc from -90° (top) clockwise
        start_angle = 90 * 16
        span_angle = int(-prob * 360 * 16)
        painter.drawArc(
            QRectF(ring_center.x() - ring_radius, ring_center.y() - ring_radius,
                   ring_radius * 2, ring_radius * 2),
            start_angle, span_angle,
        )
        # Probability text inside ring
        painter.setFont(QFont("JetBrains Mono", 8, QFont.Bold))
        painter.setPen(QPen(QColor(Palette.TEXT_PRIMARY)))
        painter.drawText(
            QRectF(ring_center.x() - ring_radius, ring_center.y() - ring_radius,
                   ring_radius * 2, ring_radius * 2),
            Qt.AlignCenter, f"{int(prob * 100)}%"
        )

        # 8. Location (right of ring)
        if self.step.location:
            loc_font = QFont("Inter", 9)
            painter.setFont(loc_font)
            painter.setPen(QPen(QColor(Palette.TEXT_SECONDARY)))
            loc_text = self._elide_text(f"📍 {self.step.location}", NODE_WIDTH - 70, loc_font)
            painter.drawText(QRectF(60, 42, NODE_WIDTH - 70, 16), Qt.AlignLeft, loc_text)

        # 9. Description (truncated)
        if self.step.description:
            desc_font = QFont("Inter", 9)
            painter.setFont(desc_font)
            painter.setPen(QPen(QColor(Palette.TEXT_SECONDARY)))
            desc = self._elide_text(self.step.description, NODE_WIDTH - 24, desc_font)
            painter.drawText(QRectF(12, 64, NODE_WIDTH - 24, 18), Qt.AlignLeft, desc)

        # 10. Bottom row: fallback indicator + sub-goals + depends-on
        bottom_y = NODE_HEIGHT - 22
        x = 12

        # Fallback icon
        if self.step.fallback:
            painter.setFont(QFont("Inter", 8, QFont.Bold))
            painter.setPen(QPen(QColor(Palette.GOLD_PRIMARY)))
            painter.drawText(QRectF(x, bottom_y, 80, 14), Qt.AlignLeft, "↩ fallback")
            x += 80

        # Sub-goals count
        if self.step.sub_goals:
            painter.setPen(QPen(QColor(Palette.TEXT_TERTIARY)))
            painter.drawText(QRectF(x, bottom_y, 80, 14), Qt.AlignLeft,
                             f"◆ {len(self.step.sub_goals)} sub-goal{'s' if len(self.step.sub_goals) != 1 else ''}")
            x += 80

        # Cost estimate (right-aligned)
        if self.step.cost_estimate:
            painter.setFont(QFont("JetBrains Mono", 8))
            painter.setPen(QPen(QColor(Palette.TEXT_TERTIARY)))
            cost = self._elide_text(self.step.cost_estimate, 80, painter.font())
            painter.drawText(QRectF(NODE_WIDTH - 90, bottom_y, 78, 14),
                             Qt.AlignRight, cost)

        # 11. Risk badge (top-right corner)
        risk_font = QFont("Inter", 7, QFont.Bold)
        painter.setFont(risk_font)
        risk_text = self.step.risk_level.upper()
        fm = QFontMetrics(risk_font)
        rw = fm.horizontalAdvance(risk_text) + 10
        painter.setBrush(QBrush(risk_color))
        painter.setPen(Qt.NoPen)
        painter.drawRoundedRect(QRectF(NODE_WIDTH - rw - 8, NODE_HEIGHT - 22, rw, 14), 3, 3)
        painter.setPen(QPen(QColor(Palette.TEXT_ON_GOLD)))
        painter.drawText(QRectF(NODE_WIDTH - rw - 8, NODE_HEIGHT - 22, rw, 14),
                         Qt.AlignCenter, risk_text)

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
        # Show full description as tooltip
        tip_parts = [f"<b>{self.step.title}</b>"]
        tip_parts.append(f"ID: {self.step.id}")
        tip_parts.append(f"Duration: {self.step.duration_minutes} min")
        tip_parts.append(f"Success: {self.step.success_probability:.0%}")
        tip_parts.append(f"Risk: {self.step.risk_level}")
        if self.step.location:
            tip_parts.append(f"📍 {self.step.location}")
        if self.step.description:
            tip_parts.append(f"\n{self.step.description}")
        if self.step.fallback:
            tip_parts.append(f"\n<b>Fallback:</b> {self.step.fallback}")
        if self.step.sub_goals:
            tip_parts.append("\n<b>Sub-goals:</b>")
            for sg in self.step.sub_goals:
                tip_parts.append(f"  • {sg}")
        if self.step.depends_on:
            tip_parts.append(f"\n<b>Depends on:</b> {', '.join(self.step.depends_on)}")
        if self.step.cost_estimate:
            tip_parts.append(f"\n<b>Cost:</b> {self.step.cost_estimate}")
        self.setToolTip("\n".join(tip_parts))
        super().hoverEnterEvent(event)

    def hoverLeaveEvent(self, event: QGraphicsSceneHoverEvent) -> None:
        self._hovered = False
        self.setZValue(10 if not self.isSelected() else 15)
        self.update()
        super().hoverLeaveEvent(event)

    def mousePressEvent(self, event: QGraphicsSceneMouseEvent) -> None:
        if event.button() == Qt.LeftButton:
            self._drag_started_pos = self.pos()
            self.nodeClicked.emit(self.step.id)
        super().mousePressEvent(event)

    def mouseDoubleClickEvent(self, event: QGraphicsSceneMouseEvent) -> None:
        if event.button() == Qt.LeftButton:
            self.nodeDoubleClicked.emit(self.step.id)
        super().mouseDoubleClickEvent(event)

    def mouseReleaseEvent(self, event: QGraphicsSceneMouseEvent) -> None:
        super().mouseReleaseEvent(event)
        if self._drag_started_pos is not None:
            new_pos = self.pos()
            if (new_pos - self._drag_started_pos).manhattanLength() > 2:
                self.nodeMoved.emit(self.step.id, new_pos.x(), new_pos.y())
            self._drag_started_pos = None

    # ---- Anchors ----
    @property
    def anchor_in(self) -> QPointF:
        """Left-middle anchor for incoming edges."""
        return self.mapToScene(QPointF(0, NODE_HEIGHT / 2))

    @property
    def anchor_out(self) -> QPointF:
        """Right-middle anchor for outgoing edges."""
        return self.mapToScene(QPointF(NODE_WIDTH, NODE_HEIGHT / 2))
