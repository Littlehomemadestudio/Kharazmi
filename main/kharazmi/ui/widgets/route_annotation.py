"""
RouteAnnotation — distinctive visual overlays for special route insights.

Three eye-catching, animated annotations that appear near nodes:
  - BreakthroughFlash: A BIG BLUE electric flash / lightning bolt that
    represents a radical alternative way. Pulsing blue glow, electric arcs.
  - SkipWhirl: A BIG WHIRLY ARROW showing you can skip a part.
    Spiraling orange arrow with description.
  - LoopCurl: A BIG CIRCLING ARROW animation showing a repeatable loop.
    Spinning green circular arrow.

All three are:
  - Colorful and instantly recognizable (distinct from gold nodes)
  - Anchored to specific nodes but float nearby
  - Animated (pulsing, spinning, or flashing)
  - Show description text on hover
"""
from __future__ import annotations

import math
from typing import Optional

from PySide6.QtCore import Qt, QRectF, QPointF, Signal, QTimer, QPropertyAnimation, QEasingCurve
from PySide6.QtGui import (
    QPainter, QPainterPath, QColor, QPen, QBrush, QFont,
    QFontMetrics, QLinearGradient, QRadialGradient, QConicalGradient,
    QPolygonF,
)
from PySide6.QtWidgets import (
    QGraphicsObject, QGraphicsItem, QGraphicsSceneMouseEvent,
    QGraphicsSceneHoverEvent, QStyleOptionGraphicsItem, QWidget,
)

from ...ai import Insight
from ..theme import Palette


# ────────────────────────────────────────────────────────────────────
# 1. BREAKTHROUGH — Blue electric flash
# ────────────────────────────────────────────────────────────────────

class BreakthroughFlash(QGraphicsObject):
    """
    A BIG BLUE FLASH — electric lightning bolt with pulsing glow.
    Represents a radical alternative way to achieve the goal.
    Instantly recognizable by its vivid blue color and lightning icon.
    """
    annotationClicked = Signal(str)

    def __init__(self, insight: Insight, anchor_step_id: str,
                 parent: QGraphicsItem = None) -> None:
        super().__init__(parent)
        self.insight = insight
        self.anchor_step_id = anchor_step_id
        self._hovered = False
        self._pulse_phase = 0.0
        self._width = 120
        self._height = 120

        self.setFlag(QGraphicsItem.ItemIsMovable, True)
        self.setFlag(QGraphicsItem.ItemSendsGeometryChanges, True)
        self.setAcceptHoverEvents(True)
        self.setZValue(35)  # above nodes, above regular insight bubbles

        # Pulsing animation
        self._pulse_timer = QTimer(self)
        self._pulse_timer.timeout.connect(self._tick_pulse)
        self._pulse_timer.start(40)  # ~25fps

    def _tick_pulse(self) -> None:
        self._pulse_phase += 0.08
        if self._pulse_phase > 2 * math.pi:
            self._pulse_phase -= 2 * math.pi
        self.update()

    def boundingRect(self) -> QRectF:
        return QRectF(-20, -20, self._width + 40, self._height + 40)

    def paint(self, painter: QPainter, option: QStyleOptionGraphicsItem,
              widget: QWidget = None) -> None:
        painter.setRenderHint(QPainter.Antialiasing, True)

        # Pulsing intensity
        pulse = 0.5 + 0.5 * math.sin(self._pulse_phase)

        # --- Outer glow (pulsing blue) ---
        glow_alpha = int(30 + 50 * pulse)
        glow_radius = 60 + 20 * pulse
        center_x = self._width / 2
        center_y = self._height / 2

        glow_grad = QRadialGradient(center_x, center_y, glow_radius)
        blue_glow = QColor(60, 140, 255, glow_alpha)
        glow_grad.setColorAt(0, blue_glow)
        glow_grad.setColorAt(0.5, QColor(60, 140, 255, int(glow_alpha * 0.4)))
        glow_grad.setColorAt(1, QColor(60, 140, 255, 0))
        painter.setBrush(QBrush(glow_grad))
        painter.setPen(Qt.NoPen)
        painter.drawEllipse(QRectF(-10, -10, self._width + 20, self._height + 20))

        # --- Inner circle (dark with blue border) ---
        inner_r = 38 + 4 * pulse
        inner_grad = QRadialGradient(center_x, center_y, inner_r)
        inner_grad.setColorAt(0, QColor(20, 50, 100, 200))
        inner_grad.setColorAt(0.7, QColor(15, 35, 80, 220))
        inner_grad.setColorAt(1, QColor(40, 120, 255, 180))
        painter.setBrush(QBrush(inner_grad))
        border_blue = QColor(80, 170, 255, int(180 + 75 * pulse))
        painter.setPen(QPen(border_blue, 3))
        painter.drawEllipse(QRectF(
            center_x - inner_r, center_y - inner_r,
            inner_r * 2, inner_r * 2
        ))

        # --- Lightning bolt icon ---
        bolt_color = QColor(140, 210, 255, int(200 + 55 * pulse))
        painter.setPen(Qt.NoPen)
        painter.setBrush(QBrush(bolt_color))
        # Draw a stylized lightning bolt
        bolt_path = QPainterPath()
        cx, cy = center_x, center_y
        bolt_path.moveTo(cx - 4, cy - 22)
        bolt_path.lineTo(cx + 10, cy - 22)
        bolt_path.lineTo(cx + 2, cy - 4)
        bolt_path.lineTo(cx + 14, cy - 4)
        bolt_path.lineTo(cx - 6, cy + 24)
        bolt_path.lineTo(cx + 2, cy + 4)
        bolt_path.lineTo(cx - 10, cy + 4)
        bolt_path.closeSubpath()
        painter.drawPath(bolt_path)

        # --- Small electric arcs (2-3 flickering lines) ---
        arc_alpha = int(120 + 100 * pulse)
        painter.setPen(QPen(QColor(100, 200, 255, arc_alpha), 1.5))
        # Arc 1
        painter.drawLine(int(cx + inner_r - 5), int(cy - 8),
                         int(cx + inner_r + 15), int(cy - 18))
        painter.drawLine(int(cx + inner_r + 15), int(cy - 18),
                         int(cx + inner_r + 8), int(cy - 3))
        # Arc 2
        painter.drawLine(int(cx - inner_r + 5), int(cy + 6),
                         int(cx - inner_r - 12), int(cy + 16))
        painter.drawLine(int(cx - inner_r - 12), int(cy + 16),
                         int(cx - inner_r - 4), int(cy + 2))

        # --- "BREAKTHROUGH" label below ---
        label_font = QFont("Inter", 7, QFont.Bold)
        painter.setFont(label_font)
        painter.setPen(QPen(QColor(80, 170, 255, 220)))
        fm = QFontMetrics(label_font)
        label = "⚡ BREAKTHROUGH"
        lw = fm.horizontalAdvance(label)
        painter.drawText(int(center_x - lw / 2), int(self._height + 8), label)

    def hoverEnterEvent(self, event: QGraphicsSceneHoverEvent) -> None:
        self._hovered = True
        self.setZValue(45)
        self.setToolTip(
            f"<b style='color:#50AAFF'>⚡ BREAKTHROUGH</b><br><br>"
            f"{self.insight.body}"
        )
        self.update()
        super().hoverEnterEvent(event)

    def hoverLeaveEvent(self, event: QGraphicsSceneHoverEvent) -> None:
        self._hovered = False
        self.setZValue(35)
        self.update()
        super().hoverLeaveEvent(event)

    def mousePressEvent(self, event: QGraphicsSceneMouseEvent) -> None:
        self.annotationClicked.emit(self.anchor_step_id)
        super().mousePressEvent(event)


# ────────────────────────────────────────────────────────────────────
# 2. SKIP — Whirly orange spiral arrow
# ────────────────────────────────────────────────────────────────────

class SkipWhirl(QGraphicsObject):
    """
    A BIG WHIRLY ARROW — spiraling orange arrow with skip description.
    Shows that you can skip a part entirely.
    Instantly recognizable by its vivid orange color and spiral arrow.
    """
    annotationClicked = Signal(str)

    def __init__(self, insight: Insight, anchor_step_id: str,
                 parent: QGraphicsItem = None) -> None:
        super().__init__(parent)
        self.insight = insight
        self.anchor_step_id = anchor_step_id
        self._hovered = False
        self._spin_angle = 0.0
        self._width = 120
        self._height = 120

        self.setFlag(QGraphicsItem.ItemIsMovable, True)
        self.setFlag(QGraphicsItem.ItemSendsGeometryChanges, True)
        self.setAcceptHoverEvents(True)
        self.setZValue(35)

        # Spinning animation
        self._spin_timer = QTimer(self)
        self._spin_timer.timeout.connect(self._tick_spin)
        self._spin_timer.start(50)  # ~20fps

    def _tick_spin(self) -> None:
        self._spin_angle += 3.0
        if self._spin_angle >= 360:
            self._spin_angle -= 360
        self.update()

    def boundingRect(self) -> QRectF:
        return QRectF(-20, -20, self._width + 40, self._height + 40)

    def paint(self, painter: QPainter, option: QStyleOptionGraphicsItem,
              widget: QWidget = None) -> None:
        painter.setRenderHint(QPainter.Antialiasing, True)

        cx = self._width / 2
        cy = self._height / 2

        # --- Outer glow (orange) ---
        glow_grad = QRadialGradient(cx, cy, 55)
        glow_grad.setColorAt(0, QColor(255, 140, 30, 45))
        glow_grad.setColorAt(0.6, QColor(255, 120, 20, 20))
        glow_grad.setColorAt(1, QColor(255, 100, 10, 0))
        painter.setBrush(QBrush(glow_grad))
        painter.setPen(Qt.NoPen)
        painter.drawEllipse(QRectF(-8, -8, self._width + 16, self._height + 16))

        # --- Spiral path (whirly arrow) ---
        painter.save()
        painter.translate(cx, cy)
        painter.rotate(self._spin_angle * 0.15)  # slow rotation

        # Draw a bold spiral arrow
        spiral_path = QPainterPath()
        for t in range(0, 300):
            angle = t * 0.08
            r = 8 + t * 0.06
            x = r * math.cos(angle)
            y = r * math.sin(angle)
            if t == 0:
                spiral_path.moveTo(x, y)
            else:
                spiral_path.lineTo(x, y)

        # Gradient along the spiral
        orange_pen = QPen(QColor(255, 160, 40, 200), 4, Qt.SolidLine, Qt.RoundCap)
        painter.setPen(orange_pen)
        painter.setBrush(Qt.NoBrush)
        painter.drawPath(spiral_path)

        # Arrowhead at the end of the spiral
        end_angle = 299 * 0.08
        end_r = 8 + 299 * 0.06
        end_x = end_r * math.cos(end_angle)
        end_y = end_r * math.sin(end_angle)
        arrow_angle = end_angle + math.pi / 2

        arrow_size = 14
        p1 = QPointF(
            end_x - arrow_size * math.cos(arrow_angle - math.pi / 5),
            end_y - arrow_size * math.sin(arrow_angle - math.pi / 5),
        )
        p2 = QPointF(
            end_x - arrow_size * math.cos(arrow_angle + math.pi / 5),
            end_y - arrow_size * math.sin(arrow_angle + math.pi / 5),
        )
        arrow = QPolygonF([QPointF(end_x, end_y), p1, p2])
        painter.setPen(Qt.NoPen)
        painter.setBrush(QBrush(QColor(255, 170, 50, 230)))
        painter.drawPolygon(arrow)

        painter.restore()

        # --- Central "SKIP" circle ---
        circle_grad = QRadialGradient(cx, cy, 22)
        circle_grad.setColorAt(0, QColor(80, 40, 0, 220))
        circle_grad.setColorAt(1, QColor(50, 25, 0, 240))
        painter.setBrush(QBrush(circle_grad))
        painter.setPen(QPen(QColor(255, 160, 40, 200), 2.5))
        painter.drawEllipse(QRectF(cx - 22, cy - 22, 44, 44))

        # "SKIP" text
        skip_font = QFont("Inter", 9, QFont.Bold)
        painter.setFont(skip_font)
        painter.setPen(QPen(QColor(255, 200, 100)))
        fm = QFontMetrics(skip_font)
        skip_text = "SKIP"
        sw = fm.horizontalAdvance(skip_text)
        painter.drawText(int(cx - sw / 2), int(cy + 4), skip_text)

        # --- Label below ---
        label_font = QFont("Inter", 7, QFont.Bold)
        painter.setFont(label_font)
        painter.setPen(QPen(QColor(255, 160, 40, 220)))
        fm2 = QFontMetrics(label_font)
        label = "↻ SKIP"
        lw = fm2.horizontalAdvance(label)
        painter.drawText(int(cx - lw / 2), int(self._height + 8), label)

    def hoverEnterEvent(self, event: QGraphicsSceneHoverEvent) -> None:
        self._hovered = True
        self.setZValue(45)
        self.setToolTip(
            f"<b style='color:#FFA028'>↻ SKIP</b><br><br>"
            f"{self.insight.body}"
        )
        self.update()
        super().hoverEnterEvent(event)

    def hoverLeaveEvent(self, event: QGraphicsSceneHoverEvent) -> None:
        self._hovered = False
        self.setZValue(35)
        self.update()
        super().hoverLeaveEvent(event)

    def mousePressEvent(self, event: QGraphicsSceneMouseEvent) -> None:
        self.annotationClicked.emit(self.anchor_step_id)
        super().mousePressEvent(event)


# ────────────────────────────────────────────────────────────────────
# 3. LOOP — Spinning green circular arrow
# ────────────────────────────────────────────────────────────────────

class LoopCurl(QGraphicsObject):
    """
    A BIG CIRCLING ARROW — spinning green loop arrow animation.
    Shows that this step can be repeated/looped if you need more of the target.
    Instantly recognizable by its vivid green color and circular arrow.
    """
    annotationClicked = Signal(str)

    def __init__(self, insight: Insight, anchor_step_id: str,
                 parent: QGraphicsItem = None) -> None:
        super().__init__(parent)
        self.insight = insight
        self.anchor_step_id = anchor_step_id
        self._hovered = False
        self._spin_angle = 0.0
        self._width = 120
        self._height = 120

        self.setFlag(QGraphicsItem.ItemIsMovable, True)
        self.setFlag(QGraphicsItem.ItemSendsGeometryChanges, True)
        self.setAcceptHoverEvents(True)
        self.setZValue(35)

        # Spinning animation
        self._spin_timer = QTimer(self)
        self._spin_timer.timeout.connect(self._tick_spin)
        self._spin_timer.start(35)  # ~28fps for smooth spin

    def _tick_spin(self) -> None:
        self._spin_angle += 4.0
        if self._spin_angle >= 360:
            self._spin_angle -= 360
        self.update()

    def boundingRect(self) -> QRectF:
        return QRectF(-20, -20, self._width + 40, self._height + 40)

    def paint(self, painter: QPainter, option: QStyleOptionGraphicsItem,
              widget: QWidget = None) -> None:
        painter.setRenderHint(QPainter.Antialiasing, True)

        cx = self._width / 2
        cy = self._height / 2

        # --- Outer glow (green) ---
        glow_grad = QRadialGradient(cx, cy, 55)
        glow_grad.setColorAt(0, QColor(40, 200, 100, 40))
        glow_grad.setColorAt(0.6, QColor(30, 180, 80, 18))
        glow_grad.setColorAt(1, QColor(20, 160, 60, 0))
        painter.setBrush(QBrush(glow_grad))
        painter.setPen(Qt.NoPen)
        painter.drawEllipse(QRectF(-8, -8, self._width + 16, self._height + 16))

        # --- Spinning circular arrow ---
        painter.save()
        painter.translate(cx, cy)
        painter.rotate(self._spin_angle)

        ring_r = 32
        # Draw an arc (almost full circle, with gap for arrowhead)
        arc_path = QPainterPath()
        arc_rect = QRectF(-ring_r, -ring_r, ring_r * 2, ring_r * 2)
        # Arc from 30° to 330° (leaving a gap for the arrowhead)
        arc_path.arcMoveTo(arc_rect, 30)
        arc_path.arcTo(arc_rect, 30, 300)

        # Bold green arc
        green_pen = QPen(QColor(60, 220, 120, 220), 5, Qt.SolidLine, Qt.RoundCap)
        painter.setPen(green_pen)
        painter.setBrush(Qt.NoBrush)
        painter.drawPath(arc_path)

        # Arrowhead at the start of the arc (pointing in the direction of rotation)
        # The arc starts at 30° on the ellipse
        start_angle_rad = math.radians(30)
        arrow_tip_x = ring_r * math.cos(start_angle_rad)
        arrow_tip_y = -ring_r * math.sin(start_angle_rad)

        # Tangent direction at start (perpendicular to radius, in rotation direction)
        tangent_angle = start_angle_rad + math.pi / 2  # clockwise rotation

        arrow_size = 16
        p1 = QPointF(
            arrow_tip_x - arrow_size * math.cos(tangent_angle - math.pi / 5),
            arrow_tip_y + arrow_size * math.sin(tangent_angle - math.pi / 5),
        )
        p2 = QPointF(
            arrow_tip_x - arrow_size * math.cos(tangent_angle + math.pi / 5),
            arrow_tip_y + arrow_size * math.sin(tangent_angle + math.pi / 5),
        )
        arrow = QPolygonF([QPointF(arrow_tip_x, arrow_tip_y), p1, p2])
        painter.setPen(Qt.NoPen)
        painter.setBrush(QBrush(QColor(80, 240, 140, 240)))
        painter.drawPolygon(arrow)

        # Second arrowhead at the end of the arc
        end_angle_rad = math.radians(330)
        end_tip_x = ring_r * math.cos(end_angle_rad)
        end_tip_y = -ring_r * math.sin(end_angle_rad)
        end_tangent = end_angle_rad + math.pi / 2

        ep1 = QPointF(
            end_tip_x - arrow_size * math.cos(end_tangent - math.pi / 5),
            end_tip_y + arrow_size * math.sin(end_tangent - math.pi / 5),
        )
        ep2 = QPointF(
            end_tip_x - arrow_size * math.cos(end_tangent + math.pi / 5),
            end_tip_y + arrow_size * math.sin(end_tangent + math.pi / 5),
        )
        arrow2 = QPolygonF([QPointF(end_tip_x, end_tip_y), ep1, ep2])
        painter.setBrush(QBrush(QColor(60, 220, 120, 200)))
        painter.drawPolygon(arrow2)

        painter.restore()

        # --- Central "LOOP" circle ---
        circle_grad = QRadialGradient(cx, cy, 18)
        circle_grad.setColorAt(0, QColor(0, 50, 20, 220))
        circle_grad.setColorAt(1, QColor(0, 35, 15, 240))
        painter.setBrush(QBrush(circle_grad))
        painter.setPen(QPen(QColor(60, 220, 120, 200), 2.5))
        painter.drawEllipse(QRectF(cx - 18, cy - 18, 36, 36))

        # "×2" text (implies loop/repeat)
        loop_font = QFont("Inter", 10, QFont.Bold)
        painter.setFont(loop_font)
        painter.setPen(QPen(QColor(140, 255, 180)))
        fm = QFontMetrics(loop_font)
        loop_text = "×2"
        lw = fm.horizontalAdvance(loop_text)
        painter.drawText(int(cx - lw / 2), int(cy + 5), loop_text)

        # --- Label below ---
        label_font = QFont("Inter", 7, QFont.Bold)
        painter.setFont(label_font)
        painter.setPen(QPen(QColor(60, 220, 120, 220)))
        fm2 = QFontMetrics(label_font)
        label = "⟳ LOOP"
        llw = fm2.horizontalAdvance(label)
        painter.drawText(int(cx - llw / 2), int(self._height + 8), label)

    def hoverEnterEvent(self, event: QGraphicsSceneHoverEvent) -> None:
        self._hovered = True
        self.setZValue(45)
        self.setToolTip(
            f"<b style='color:#40DC80'>⟳ LOOP</b><br><br>"
            f"{self.insight.body}"
        )
        self.update()
        super().hoverEnterEvent(event)

    def hoverLeaveEvent(self, event: QGraphicsSceneHoverEvent) -> None:
        self._hovered = False
        self.setZValue(35)
        self.update()
        super().hoverLeaveEvent(event)

    def mousePressEvent(self, event: QGraphicsSceneMouseEvent) -> None:
        self.annotationClicked.emit(self.anchor_step_id)
        super().mousePressEvent(event)
