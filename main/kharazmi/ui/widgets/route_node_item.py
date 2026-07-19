"""
RouteNodeItem — a QGraphicsItem that renders a single RouteStep.

Auto-sizes to fit its content (long titles = wider nodes).

Each node shows:
  - Step ID badge (top-left)
  - Title (auto-wrapped if very long, but preferred on one line)
  - Duration (top-right)
  - Success probability ring (left)
  - Location, description
  - Fallback indicator, sub-goals count
  - Risk-level color stripe + badge

Color scheme is tied to risk level:
  low      → green-ish gold
  medium   → gold
  high     → orange
  severe   → red
"""
from __future__ import annotations

import math
from typing import Optional

from PySide6.QtCore import Qt, QRectF, QPointF, Signal, QSizeF
from PySide6.QtGui import (
    QPainter, QPainterPath, QColor, QPen, QBrush, QFont, QLinearGradient,
    QRadialGradient, QFontMetrics, QPolygonF, QTextOption,
)
from PySide6.QtWidgets import (
    QGraphicsObject, QGraphicsItem, QGraphicsSceneMouseEvent,
    QGraphicsSceneHoverEvent, QStyleOptionGraphicsItem, QWidget,
)

from ...ai import RouteStep
from ..theme import Palette


# Min/max width — node can grow between these
MIN_NODE_WIDTH = 220
MAX_NODE_WIDTH = 480
NODE_HEIGHT = 130  # slightly taller for richer content

_RISK_COLORS = {
    "low":      "#5A8A5A",
    "medium":   "#D4AF37",
    "high":     "#A87A4A",
    "severe":   "#A85A5A",
}


class RouteNodeItem(QGraphicsObject):
    """
    A draggable route-step node.

    Auto-sizes horizontally to fit the title and description.

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
        self._width: float = MIN_NODE_WIDTH
        self._height: float = NODE_HEIGHT

        self.setFlag(QGraphicsItem.ItemIsMovable, True)
        self.setFlag(QGraphicsItem.ItemIsSelectable, True)
        self.setFlag(QGraphicsItem.ItemSendsGeometryChanges, True)
        self.setAcceptHoverEvents(True)
        self.setZValue(10)

        # Compute auto-size based on content
        self._compute_size()

    def _compute_size(self) -> None:
        """Compute width/height to fit content."""
        # Title font
        title_font = QFont("Inter", 10, QFont.DemiBold)
        fm_title = QFontMetrics(title_font)
        # Description font
        desc_font = QFont("Inter", 9)
        fm_desc = QFontMetrics(desc_font)
        # Location font
        loc_font = QFont("Inter", 9)
        fm_loc = QFontMetrics(loc_font)

        # Title width (single line preferred, but cap at MAX)
        title_w = fm_title.horizontalAdvance(self.step.title)
        # Description width (allow 2 lines)
        desc_w = fm_desc.horizontalAdvance(self.step.description) if self.step.description else 0
        # Location width
        loc_w = fm_loc.horizontalAdvance(f"📍 {self.step.location}") if self.step.location else 0
        # Fallback indicator
        fb_w = fm_desc.horizontalAdvance("↩ fallback") if self.step.fallback else 0
        # Sub-goals
        sg_w = fm_desc.horizontalAdvance(f"◆ {len(self.step.sub_goals)} sub-goals") if self.step.sub_goals else 0
        # Cost
        cost_w = fm_desc.horizontalAdvance(self.step.cost_estimate) if self.step.cost_estimate else 0

        # Padding for: ID badge + ring column on left + duration on right
        # Left padding for ring column = 60px, right padding = 90px (for duration)
        content_max_w = max(title_w, desc_w * 0.7, loc_w, fb_w, sg_w, cost_w)
        needed_w = content_max_w + 60 + 90 + 24  # left pad + right pad + h padding

        self._width = max(MIN_NODE_WIDTH, min(MAX_NODE_WIDTH, needed_w))

        # Height grows if description is long enough to need 2 lines
        desc_lines = 1
        if self.step.description and desc_w > self._width - 80:
            desc_lines = 2
        # Extra height for description second line
        self._height = NODE_HEIGHT + (desc_lines - 1) * 16

    # ---- Geometry ----
    def boundingRect(self) -> QRectF:
        return QRectF(-8, -8, self._width + 16, self._height + 16)

    def shape(self) -> QPainterPath:
        path = QPainterPath()
        path.addRoundedRect(0, 0, self._width, self._height, 10, 10)
        return path

    @property
    def size(self) -> QSizeF:
        return QSizeF(self._width, self._height)

    # ---- Painting ----
    def paint(self, painter: QPainter, option: QStyleOptionGraphicsItem,
              widget: QWidget = None) -> None:
        painter.setRenderHint(QPainter.Antialiasing, True)
        painter.setRenderHint(QPainter.TextAntialiasing, True)

        risk_color_str = _RISK_COLORS.get(self.step.risk_level, _RISK_COLORS["medium"])
        risk_color = QColor(risk_color_str)

        # 1. Selection / hover halo
        if self.isSelected():
            painter.setBrush(QBrush(QColor(255, 255, 255, 30)))
            painter.setPen(QPen(QColor(Palette.GOLD_BRIGHT), 2))
            painter.drawRoundedRect(-2, -2, self._width + 4, self._height + 4, 12, 12)
        elif self._hovered:
            painter.setBrush(QBrush(QColor(0, 0, 0, 80)))
            painter.setPen(QPen(risk_color, 1))
            painter.drawRoundedRect(-1, -1, self._width + 2, self._height + 2, 11, 11)

        # 2. Background gradient
        bg = QLinearGradient(0, 0, 0, self._height)
        bg.setColorAt(0, QColor(Palette.BG_ELEVATED))
        bg.setColorAt(1, QColor(Palette.BG_TERTIARY))
        painter.setBrush(QBrush(bg))
        painter.setPen(QPen(risk_color, 1.5))
        painter.drawRoundedRect(0, 0, self._width, self._height, 10, 10)

        # 3. Left risk-color stripe
        painter.setBrush(QBrush(risk_color))
        painter.setPen(Qt.NoPen)
        path = QPainterPath()
        path.addRoundedRect(QRectF(0, 0, 4, self._height), 2, 2)
        painter.fillPath(path, QBrush(risk_color))

        # 4. Step ID badge (top-left)
        id_font = QFont("JetBrains Mono", 8, QFont.Bold)
        painter.setFont(id_font)
        painter.setBrush(QBrush(risk_color))
        painter.setPen(Qt.NoPen)
        painter.drawRoundedRect(QRectF(10, 10, 40, 18), 4, 4)
        painter.setPen(QPen(QColor(Palette.TEXT_ON_GOLD)))
        painter.drawText(QRectF(10, 10, 40, 18), Qt.AlignCenter, self.step.id.upper())

        # 5. Title (auto-elide if too long even for max width)
        title_font = QFont("Inter", 10, QFont.DemiBold)
        painter.setFont(title_font)
        painter.setPen(QPen(QColor(Palette.TEXT_PRIMARY)))
        title_x = 58
        title_w = self._width - title_x - 90  # leave room for duration
        title = self._elide_text(self.step.title, title_w, title_font)
        painter.drawText(QRectF(title_x, 8, title_w, 22),
                         Qt.AlignLeft | Qt.AlignVCenter, title)

        # 6. Duration (top-right)
        dur_font = QFont("JetBrains Mono", 9, QFont.Bold)
        painter.setFont(dur_font)
        dur_text = f"⏱ {self.step.duration_minutes}m"
        painter.setPen(QPen(QColor(Palette.GOLD_BRIGHT)))
        painter.drawText(QRectF(self._width - 90, 8, 80, 22),
                         Qt.AlignRight | Qt.AlignVCenter, dur_text)

        # 7. Success probability ring (left side, below ID)
        ring_center = QPointF(34, 64)
        ring_radius = 18
        painter.setBrush(Qt.NoBrush)
        painter.setPen(QPen(QColor(Palette.BG_DEEPEST), 5))
        painter.drawEllipse(ring_center, ring_radius, ring_radius)
        prob = max(0.0, min(1.0, self.step.success_probability))
        prob_color = QColor(risk_color)
        if prob > 0.7:
            prob_color = QColor(Palette.GOLD_BRIGHT)
        elif prob < 0.4:
            prob_color = QColor(Palette.STATUS_BLOCKED)
        painter.setPen(QPen(prob_color, 5, Qt.SolidLine, Qt.RoundCap))
        start_angle = 90 * 16
        span_angle = int(-prob * 360 * 16)
        painter.drawArc(
            QRectF(ring_center.x() - ring_radius, ring_center.y() - ring_radius,
                   ring_radius * 2, ring_radius * 2),
            start_angle, span_angle,
        )
        painter.setFont(QFont("JetBrains Mono", 8, QFont.Bold))
        painter.setPen(QPen(QColor(Palette.TEXT_PRIMARY)))
        painter.drawText(
            QRectF(ring_center.x() - ring_radius, ring_center.y() - ring_radius,
                   ring_radius * 2, ring_radius * 2),
            Qt.AlignCenter, f"{int(prob * 100)}%"
        )

        # 8. Location (right of ring)
        text_x = 64
        text_w = self._width - text_x - 12
        if self.step.location:
            loc_font = QFont("Inter", 9)
            painter.setFont(loc_font)
            painter.setPen(QPen(QColor(Palette.TEXT_SECONDARY)))
            loc_text = self._elide_text(f"📍 {self.step.location}", text_w, loc_font)
            painter.drawText(QRectF(text_x, 42, text_w, 16), Qt.AlignLeft, loc_text)

        # 9. Description (truncated, may wrap to 2 lines)
        if self.step.description:
            desc_font = QFont("Inter", 9)
            painter.setFont(desc_font)
            painter.setPen(QPen(QColor(Palette.TEXT_SECONDARY)))
            # Use QTextOption for word-wrap
            desc_rect = QRectF(text_x, 64, text_w, 32)
            # Manually wrap to 2 lines max
            desc = self._wrap_text(self.step.description, text_w, desc_font, max_lines=2)
            painter.drawText(desc_rect, Qt.AlignLeft | Qt.AlignTop | Qt.TextWordWrap, desc)

        # 10. Bottom row: fallback + sub-goals + cost
        bottom_y = self._height - 22
        x = 12
        if self.step.fallback:
            painter.setFont(QFont("Inter", 8, QFont.Bold))
            painter.setPen(QPen(QColor(Palette.GOLD_PRIMARY)))
            painter.drawText(QRectF(x, bottom_y, 90, 14), Qt.AlignLeft, "↩ fallback")
            x += 90
        if self.step.sub_goals:
            painter.setPen(QPen(QColor(Palette.TEXT_TERTIARY)))
            painter.drawText(QRectF(x, bottom_y, 100, 14), Qt.AlignLeft,
                             f"◆ {len(self.step.sub_goals)} sub-goal{'s' if len(self.step.sub_goals) != 1 else ''}")
            x += 100
        if self.step.cost_estimate:
            painter.setFont(QFont("JetBrains Mono", 8))
            painter.setPen(QPen(QColor(Palette.TEXT_TERTIARY)))
            cost = self._elide_text(self.step.cost_estimate, 100, painter.font())
            painter.drawText(QRectF(self._width - 110, bottom_y, 98, 14),
                             Qt.AlignRight, cost)

        # 11. Risk badge (top-right corner)
        risk_font = QFont("Inter", 7, QFont.Bold)
        painter.setFont(risk_font)
        risk_text = self.step.risk_level.upper()
        fm = QFontMetrics(risk_font)
        rw = fm.horizontalAdvance(risk_text) + 10
        painter.setBrush(QBrush(risk_color))
        painter.setPen(Qt.NoPen)
        painter.drawRoundedRect(QRectF(self._width - rw - 8, self._height - 22, rw, 14), 3, 3)
        painter.setPen(QPen(QColor(Palette.TEXT_ON_GOLD)))
        painter.drawText(QRectF(self._width - rw - 8, self._height - 22, rw, 14),
                         Qt.AlignCenter, risk_text)

    def _elide_text(self, text: str, max_width: float, font: QFont) -> str:
        fm = QFontMetrics(font)
        if fm.horizontalAdvance(text) <= max_width:
            return text
        elided = text
        while elided and fm.horizontalAdvance(elided + "…") > max_width:
            elided = elided[:-1]
        return elided + "…" if elided else "…"

    def _wrap_text(self, text: str, max_width: float, font: QFont,
                   max_lines: int = 2) -> str:
        """Word-wrap text to fit max_width, capped at max_lines."""
        fm = QFontMetrics(font)
        words = text.split()
        lines = []
        current = ""
        for word in words:
            test = (current + " " + word).strip()
            if fm.horizontalAdvance(test) <= max_width:
                current = test
            else:
                if current:
                    lines.append(current)
                current = word
                if len(lines) >= max_lines - 1:
                    break
        if current and len(lines) < max_lines:
            lines.append(current)
        # If we have leftover words and hit max_lines, elide the last line
        if len(lines) == max_lines:
            # Check if we dropped words
            consumed = " ".join(lines).split()
            if len(consumed) < len(words):
                # Elide last line
                last = lines[-1]
                while last and fm.horizontalAdvance(last + "…") > max_width:
                    last = last[:-1]
                lines[-1] = last + "…" if last else "…"
        return "\n".join(lines)

    # ---- Interaction ----
    def hoverEnterEvent(self, event: QGraphicsSceneHoverEvent) -> None:
        self._hovered = True
        self.setZValue(20)
        self.update()
        # Tooltip with full info
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
        return self.mapToScene(QPointF(0, self._height / 2))

    @property
    def anchor_out(self) -> QPointF:
        return self.mapToScene(QPointF(self._width, self._height / 2))
