"""
SpecialEdgeItem — visually distinctive edges for Breakthrough / Skip / Loop.

Three edge types that CONNECT TWO NODES with instantly recognizable visuals:

  BreakthroughEdge — BLUE electric flash alternative path.
    Jagged/zigzag (lightning-bolt) path, pulsing blue glow,
    ⚡ icon at midpoint, "BREAKTHROUGH" label.

  SkipEdge — ORANGE whirly arrow skipping section.
    Curved path arcing ABOVE the nodes (jumping over),
    spiral decorations, "SKIP" label.

  LoopEdge — GREEN circling arrow showing repetition.
    Path that curves DOWN then loops back UP with a visible
    loop/circle in the middle, ⟳ icon, "LOOP" label.

All three:
  - Accept source and target RouteNodeItem references
  - Follow nodes via `_update_path()`
  - Use animated elements (QTimer)
  - Support hover effects
  - Use the Palette theme
  - ZValue above regular edges, below nodes
"""
from __future__ import annotations

import math
from typing import Optional

from PySide6.QtCore import Qt, QRectF, QPointF, QTimer, QPropertyAnimation, QEasingCurve
from PySide6.QtGui import (
    QPainter, QPen, QBrush, QColor, QFont, QPainterPath, QPolygonF,
    QRadialGradient, QFontMetrics,
)
from PySide6.QtWidgets import (
    QGraphicsPathItem, QGraphicsItem, QStyleOptionGraphicsItem, QWidget,
)

from ...ai import RouteEdge
from ..theme import Palette


# ────────────────────────────────────────────────────────────────────
# Shared helpers
# ────────────────────────────────────────────────────────────────────

def _draw_arrowhead(painter: QPainter, tip: QPointF, angle: float,
                    size: float, color: QColor) -> None:
    """Draw a filled triangular arrowhead at *tip* pointing along *angle*."""
    p1 = QPointF(
        tip.x() - size * math.cos(angle - math.pi / 6),
        tip.y() - size * math.sin(angle - math.pi / 6),
    )
    p2 = QPointF(
        tip.x() - size * math.cos(angle + math.pi / 6),
        tip.y() - size * math.sin(angle + math.pi / 6),
    )
    arrow = QPolygonF([tip, p1, p2])
    painter.setBrush(QBrush(color))
    painter.setPen(Qt.NoPen)
    painter.drawPolygon(arrow)


def _draw_label_pill(painter: QPainter, center: QPointF, text: str,
                     text_color: QColor, border_color: QColor,
                     font: QFont) -> None:
    """Draw a label with a rounded-rect pill background at *center*."""
    painter.setFont(font)
    fm = QFontMetrics(font)
    tw = fm.horizontalAdvance(text) + 14
    th = fm.height() + 6
    rect = QRectF(center.x() - tw / 2, center.y() - th / 2, tw, th)

    painter.setBrush(QBrush(QColor(Palette.BG_ELEVATED)))
    painter.setPen(QPen(border_color, 1.2))
    painter.drawRoundedRect(rect, 6, 6)

    painter.setPen(QPen(text_color))
    painter.drawText(rect, Qt.AlignCenter, text)


def _compute_anchors(source, target):
    """Return (src_anchor, tgt_anchor) in scene coordinates, following
    the same anchor-selection logic as UnifiedEdgeItem."""
    src_pos = source.pos()
    tgt_pos = target.pos()
    src_size = source.size
    tgt_size = target.size

    dx = tgt_pos.x() - src_pos.x()
    dy = tgt_pos.y() - src_pos.y()

    if dx >= 0:
        src_anchor = source.anchor_out
        tgt_anchor = target.anchor_in
    else:
        src_anchor = QPointF(source.mapToScene(QPointF(0, src_size.height() / 2)))
        tgt_anchor = QPointF(target.mapToScene(QPointF(tgt_size.width(), tgt_size.height() / 2)))

    if abs(dy) > abs(dx) * 2.5:
        if dy >= 0:
            src_anchor = source.anchor_bottom
            tgt_anchor = target.anchor_top
        else:
            src_anchor = QPointF(source.mapToScene(QPointF(src_size.width() / 2, 0)))
            tgt_anchor = QPointF(target.mapToScene(QPointF(tgt_size.width() / 2, tgt_size.height())))

    return src_anchor, tgt_anchor


# ────────────────────────────────────────────────────────────────────
# 1. BREAKTHROUGH EDGE — Blue electric flash
# ────────────────────────────────────────────────────────────────────

class BreakthroughEdge(QGraphicsPathItem):
    """
    A thick blue edge with a jagged/zigzag (lightning-bolt) path,
    pulsing blue glow, ⚡ icon at midpoint, and "BREAKTHROUGH" label.

    Represents a radical alternative way — an electric flash of insight.
    """

    # Color constants
    COLOR = QColor("#3C8CFF")
    GLOW_COLOR = QColor(60, 140, 255, 50)
    LABEL_COLOR = QColor(100, 190, 255)

    def __init__(self, edge: RouteEdge, source, target,
                 parent: QGraphicsItem = None) -> None:
        super().__init__(parent)
        self.edge = edge
        self._source = source
        self._target = target
        self._hovered = False

        # Pulse animation state
        self._pulse_phase = 0.0
        self._pulse_timer = QTimer(self)
        self._pulse_timer.timeout.connect(self._tick_pulse)
        self._pulse_timer.start(45)  # ~22 fps

        pen = QPen(self.COLOR, 3.0, Qt.SolidLine)
        pen.setCapStyle(Qt.RoundCap)
        pen.setJoinStyle(Qt.RoundJoin)
        self.setPen(pen)
        self.setZValue(5)
        self.setAcceptHoverEvents(True)

        self._update_path()

    # ── path computation ──────────────────────────────────────────

    def _update_path(self) -> None:
        """Compute a jagged / zigzag lightning-bolt path from source
        anchor to target anchor."""
        src_anchor, tgt_anchor = _compute_anchors(self._source, self._target)

        dx = tgt_anchor.x() - src_anchor.x()
        dy = tgt_anchor.y() - src_anchor.y()
        length = math.hypot(dx, dy)
        if length < 1:
            self.setPath(QPainterPath())
            return

        # Direction unit vector and perpendicular
        ux, uy = dx / length, dy / length
        px, py = -uy, ux  # perpendicular

        path = QPainterPath()
        path.moveTo(src_anchor)

        # Number of zigzag segments — more for longer edges
        num_segments = max(6, int(length / 30))
        segment_len = length / num_segments

        # Amplitude of the zigzag perpendicular offset
        amplitude = min(18, length * 0.06)

        for i in range(1, num_segments + 1):
            # Base position along the line
            t = i / num_segments
            base_x = src_anchor.x() + dx * t
            base_y = src_anchor.y() + dy * t

            # Alternate perpendicular offset (skip the very last point)
            if i < num_segments:
                sign = 1 if i % 2 == 0 else -1
                offset = amplitude * sign
                # Add slight randomness feel by varying amplitude
                offset *= (0.7 + 0.3 * math.sin(i * 1.7))
                base_x += px * offset
                base_y += py * offset

            path.lineTo(QPointF(base_x, base_y))

        self.setPath(path)

    # ── animation ─────────────────────────────────────────────────

    def _tick_pulse(self) -> None:
        self._pulse_phase += 0.10
        if self._pulse_phase > 2 * math.pi:
            self._pulse_phase -= 2 * math.pi
        self.update()

    # ── painting ──────────────────────────────────────────────────

    def paint(self, painter: QPainter, option: QStyleOptionGraphicsItem,
              widget: QWidget = None) -> None:
        painter.setRenderHint(QPainter.Antialiasing, True)

        path = self.path()
        if path.elementCount() < 2:
            return

        pulse = 0.5 + 0.5 * math.sin(self._pulse_phase)

        # 1. Outer pulsing glow
        glow_alpha = int(25 + 45 * pulse)
        glow_width = 10 + 6 * pulse
        glow_pen = QPen(QColor(60, 140, 255, glow_alpha), glow_width, Qt.SolidLine)
        glow_pen.setCapStyle(Qt.RoundCap)
        glow_pen.setJoinStyle(Qt.RoundJoin)
        painter.setPen(glow_pen)
        painter.drawPath(path)

        # 2. Inner glow (tighter)
        inner_alpha = int(15 + 30 * pulse)
        inner_pen = QPen(QColor(80, 170, 255, inner_alpha), glow_width + 8, Qt.SolidLine)
        inner_pen.setCapStyle(Qt.RoundCap)
        inner_pen.setJoinStyle(Qt.RoundJoin)
        painter.setPen(inner_pen)
        painter.drawPath(path)

        # 3. Main zigzag edge line
        main_color = self.COLOR.lighter(110 + int(40 * pulse)) if self._hovered else self.COLOR
        pen = QPen(main_color, 3.0 + (0.8 if self._hovered else 0), Qt.SolidLine)
        pen.setCapStyle(Qt.RoundCap)
        pen.setJoinStyle(Qt.RoundJoin)
        painter.setPen(pen)
        painter.drawPath(path)

        # 4. Arrowhead at target
        tgt_anchor = self._target.anchor_in
        src_pos = self._source.pos()
        tgt_pos = self._target.pos()
        tgt_size = self._target.size
        dx = tgt_pos.x() - src_pos.x()
        dy = tgt_pos.y() - src_pos.y()
        if abs(dy) > abs(dx) * 2.5:
            if dy >= 0:
                tgt_anchor = self._target.anchor_top
            else:
                tgt_anchor = QPointF(self._target.mapToScene(
                    QPointF(tgt_size.width() / 2, tgt_size.height())))
        elif dx < 0:
            tgt_anchor = QPointF(self._target.mapToScene(
                QPointF(tgt_size.width(), tgt_size.height() / 2)))

        pt_before = path.pointAtPercent(max(0, 1.0 - 0.04))
        angle = math.atan2(tgt_anchor.y() - pt_before.y(),
                           tgt_anchor.x() - pt_before.x())
        arrow_color = QColor(100, 190, 255) if not self._hovered else QColor(150, 210, 255)
        _draw_arrowhead(painter, tgt_anchor, angle, 15, arrow_color)

        # 5. ⚡ Lightning bolt icon at midpoint
        mid = path.pointAtPercent(0.5)
        bolt_size = 14
        bx, by = mid.x(), mid.y()
        # Draw a small lightning bolt
        bolt_path = QPainterPath()
        bolt_path.moveTo(bx - 2, by - bolt_size)
        bolt_path.lineTo(bx + 5, by - bolt_size)
        bolt_path.lineTo(bx + 1, by - 2)
        bolt_path.lineTo(bx + 7, by - 2)
        bolt_path.lineTo(bx - 3, by + bolt_size)
        bolt_path.lineTo(bx + 1, by + 2)
        bolt_path.lineTo(bx - 5, by + 2)
        bolt_path.closeSubpath()
        bolt_alpha = int(200 + 55 * pulse)
        painter.setPen(Qt.NoPen)
        painter.setBrush(QBrush(QColor(140, 210, 255, bolt_alpha)))
        painter.drawPath(bolt_path)

        # 6. "BREAKTHROUGH" label
        label_y = mid.y() - 22
        label_center = QPointF(mid.x(), label_y)
        label_font = QFont("Inter", 8, QFont.Bold)
        _draw_label_pill(
            painter, label_center, "⚡ BREAKTHROUGH",
            self.LABEL_COLOR, QColor(60, 140, 255, 120),
            label_font,
        )

    # ── hover ─────────────────────────────────────────────────────

    def hoverEnterEvent(self, event) -> None:
        self._hovered = True
        self.setZValue(8)
        bright = self.COLOR.lighter(140)
        pen = QPen(bright, 3.8, Qt.SolidLine)
        pen.setCapStyle(Qt.RoundCap)
        pen.setJoinStyle(Qt.RoundJoin)
        self.setPen(pen)
        super().hoverEnterEvent(event)

    def hoverLeaveEvent(self, event) -> None:
        self._hovered = False
        self.setZValue(5)
        pen = QPen(self.COLOR, 3.0, Qt.SolidLine)
        pen.setCapStyle(Qt.RoundCap)
        pen.setJoinStyle(Qt.RoundJoin)
        self.setPen(pen)
        super().hoverLeaveEvent(event)

    def itemChange(self, change, value):
        if change == QGraphicsItem.ItemSceneHasChanged:
            self._update_path()
        return super().itemChange(change, value)


# ────────────────────────────────────────────────────────────────────
# 2. SKIP EDGE — Orange whirly arrow skipping section
# ────────────────────────────────────────────────────────────────────

class SkipEdge(QGraphicsPathItem):
    """
    An orange edge that curves UPWARD (arcing above the nodes) to
    visually show "jumping over" the skipped section.

    Spiral/whirl decorations along the path, "SKIP" label near midpoint,
    arrowhead at target.  Feels like bypassing something.
    """

    COLOR = QColor("#FF8C1E")
    GLOW_COLOR = QColor(255, 140, 30, 40)
    LABEL_COLOR = QColor(255, 200, 100)

    def __init__(self, edge: RouteEdge, source, target,
                 parent: QGraphicsItem = None) -> None:
        super().__init__(parent)
        self.edge = edge
        self._source = source
        self._target = target
        self._hovered = False

        # Spin animation for spiral decorations
        self._spin_phase = 0.0
        self._spin_timer = QTimer(self)
        self._spin_timer.timeout.connect(self._tick_spin)
        self._spin_timer.start(50)  # ~20 fps

        pen = QPen(self.COLOR, 2.8, Qt.SolidLine)
        pen.setCapStyle(Qt.RoundCap)
        pen.setJoinStyle(Qt.RoundJoin)
        self.setPen(pen)
        self.setZValue(5)
        self.setAcceptHoverEvents(True)

        self._update_path()

    # ── path computation ──────────────────────────────────────────

    def _update_path(self) -> None:
        """Compute an upward-arching bezier path from source to target.
        The arc goes well ABOVE the nodes to show 'jumping over'."""
        src_anchor, tgt_anchor = _compute_anchors(self._source, self._target)

        dx = tgt_anchor.x() - src_anchor.x()
        dy = tgt_anchor.y() - src_anchor.y()
        length = math.hypot(dx, dy)
        if length < 1:
            self.setPath(QPainterPath())
            return

        # The arc should go UPWARD (negative Y in Qt) significantly
        # Height of the arc above the midpoint line
        arc_height = max(100, length * 0.35)

        # Midpoint between the two anchors
        mid_x = (src_anchor.x() + tgt_anchor.x()) / 2
        mid_y = (src_anchor.y() + tgt_anchor.y()) / 2

        # The control point is ABOVE the midpoint
        # In Qt, Y decreases upward, so subtract arc_height
        cp_y = mid_y - arc_height

        path = QPainterPath()
        path.moveTo(src_anchor)

        # Use a quadratic-like cubic with two control points arcing upward
        # Control point 1: above the source end
        cp1_x = src_anchor.x() + dx * 0.25
        cp1_y = src_anchor.y() - arc_height * 0.8

        # Control point 2: above the target end
        cp2_x = tgt_anchor.x() - dx * 0.25
        cp2_y = tgt_anchor.y() - arc_height * 0.8

        path.cubicTo(QPointF(cp1_x, cp1_y), QPointF(cp2_x, cp2_y), tgt_anchor)

        self.setPath(path)

    # ── animation ─────────────────────────────────────────────────

    def _tick_spin(self) -> None:
        self._spin_phase += 0.08
        if self._spin_phase > 2 * math.pi:
            self._spin_phase -= 2 * math.pi
        self.update()

    # ── painting ──────────────────────────────────────────────────

    def paint(self, painter: QPainter, option: QStyleOptionGraphicsItem,
              widget: QWidget = None) -> None:
        painter.setRenderHint(QPainter.Antialiasing, True)

        path = self.path()
        if path.elementCount() < 2:
            return

        # 1. Outer glow
        glow_pen = QPen(QColor(255, 140, 30, 30), 10, Qt.SolidLine)
        glow_pen.setCapStyle(Qt.RoundCap)
        painter.setPen(glow_pen)
        painter.drawPath(path)

        # 2. Main arc line
        main_color = self.COLOR.lighter(120) if self._hovered else self.COLOR
        pen = QPen(main_color, 2.8 + (0.8 if self._hovered else 0), Qt.SolidLine)
        pen.setCapStyle(Qt.RoundCap)
        pen.setJoinStyle(Qt.RoundJoin)
        painter.setPen(pen)
        painter.drawPath(path)

        # 3. Spiral decorations along the path (3 small spirals)
        for t_val in (0.25, 0.5, 0.75):
            sp = path.pointAtPercent(t_val)
            # Tangent angle at this point
            sp_before = path.pointAtPercent(max(0, t_val - 0.02))
            sp_after = path.pointAtPercent(min(1, t_val + 0.02))
            tangent = math.atan2(sp_after.y() - sp_before.y(),
                                 sp_after.x() - sp_before.x())

            self._draw_spiral(painter, sp, tangent, self._spin_phase + t_val * 6)

        # 4. Arrowhead at target
        tgt_anchor = self._target.anchor_in
        src_pos = self._source.pos()
        tgt_pos = self._target.pos()
        tgt_size = self._target.size
        dx = tgt_pos.x() - src_pos.x()
        dy = tgt_pos.y() - src_pos.y()
        if abs(dy) > abs(dx) * 2.5:
            if dy >= 0:
                tgt_anchor = self._target.anchor_top
            else:
                tgt_anchor = QPointF(self._target.mapToScene(
                    QPointF(tgt_size.width() / 2, tgt_size.height())))
        elif dx < 0:
            tgt_anchor = QPointF(self._target.mapToScene(
                QPointF(tgt_size.width(), tgt_size.height() / 2)))

        pt_before = path.pointAtPercent(max(0, 1.0 - 0.04))
        angle = math.atan2(tgt_anchor.y() - pt_before.y(),
                           tgt_anchor.x() - pt_before.x())
        arrow_color = QColor(255, 170, 50) if not self._hovered else QColor(255, 200, 100)
        _draw_arrowhead(painter, tgt_anchor, angle, 14, arrow_color)

        # 5. "SKIP" label near the top of the arc (at ~0.45 to be above midpoint)
        label_pos = path.pointAtPercent(0.45)
        # Offset upward for readability
        tangent_at_label = math.atan2(
            path.pointAtPercent(0.47).y() - path.pointAtPercent(0.43).y(),
            path.pointAtPercent(0.47).x() - path.pointAtPercent(0.43).x(),
        )
        label_offset_x = -math.sin(tangent_at_label) * 16
        label_offset_y = math.cos(tangent_at_label) * 16
        # Always push label upward (above the arc)
        label_center = QPointF(label_pos.x(), label_pos.y() - 18)

        desc_text = self.edge.label or "bypass section"
        label_font = QFont("Inter", 8, QFont.Bold)
        _draw_label_pill(
            painter, label_center, f"↻ SKIP — {desc_text}",
            self.LABEL_COLOR, QColor(255, 140, 30, 120),
            label_font,
        )

    def _draw_spiral(self, painter: QPainter, center: QPointF,
                     tangent_angle: float, phase: float) -> None:
        """Draw a small spiral/whirl decoration at *center*."""
        painter.save()
        painter.translate(center)
        painter.rotate(math.degrees(tangent_angle))

        spiral_path = QPainterPath()
        spiral_path.moveTo(0, 0)
        for t in range(30):
            angle = t * 0.35 + phase
            r = 2 + t * 0.3
            x = r * math.cos(angle)
            y = r * math.sin(angle)
            spiral_path.lineTo(x, y)

        alpha = int(140 + 60 * math.sin(phase))
        pen = QPen(QColor(255, 170, 50, alpha), 1.5, Qt.SolidLine, Qt.RoundCap)
        painter.setPen(pen)
        painter.setBrush(Qt.NoBrush)
        painter.drawPath(spiral_path)

        painter.restore()

    # ── hover ─────────────────────────────────────────────────────

    def hoverEnterEvent(self, event) -> None:
        self._hovered = True
        self.setZValue(8)
        bright = self.COLOR.lighter(140)
        pen = QPen(bright, 3.6, Qt.SolidLine)
        pen.setCapStyle(Qt.RoundCap)
        pen.setJoinStyle(Qt.RoundJoin)
        self.setPen(pen)
        super().hoverEnterEvent(event)

    def hoverLeaveEvent(self, event) -> None:
        self._hovered = False
        self.setZValue(5)
        pen = QPen(self.COLOR, 2.8, Qt.SolidLine)
        pen.setCapStyle(Qt.RoundCap)
        pen.setJoinStyle(Qt.RoundJoin)
        self.setPen(pen)
        super().hoverLeaveEvent(event)

    def itemChange(self, change, value):
        if change == QGraphicsItem.ItemSceneHasChanged:
            self._update_path()
        return super().itemChange(change, value)


# ────────────────────────────────────────────────────────────────────
# 3. LOOP EDGE — Green circling arrow showing repetition
# ────────────────────────────────────────────────────────────────────

class LoopEdge(QGraphicsPathItem):
    """
    A green edge whose path curves DOWN and then loops back UP,
    with a visible loop/circle in the middle, a ⟳ icon at the loop
    point, and a "LOOP" label.  Feels like going around again.
    """

    COLOR = QColor("#3CDC78")
    GLOW_COLOR = QColor(60, 220, 120, 40)
    LABEL_COLOR = QColor(140, 255, 180)

    def __init__(self, edge: RouteEdge, source, target,
                 parent: QGraphicsItem = None) -> None:
        super().__init__(parent)
        self.edge = edge
        self._source = source
        self._target = target
        self._hovered = False

        # Spin animation for the ⟳ icon
        self._spin_phase = 0.0
        self._spin_timer = QTimer(self)
        self._spin_timer.timeout.connect(self._tick_spin)
        self._spin_timer.start(35)  # ~28 fps

        pen = QPen(self.COLOR, 2.8, Qt.SolidLine)
        pen.setCapStyle(Qt.RoundCap)
        pen.setJoinStyle(Qt.RoundJoin)
        self.setPen(pen)
        self.setZValue(5)
        self.setAcceptHoverEvents(True)

        self._update_path()

    # ── path computation ──────────────────────────────────────────

    def _update_path(self) -> None:
        """Compute a path that curves DOWN then loops back UP with a
        visible loop/circle in the middle of the edge."""
        src_anchor, tgt_anchor = _compute_anchors(self._source, self._target)

        dx = tgt_anchor.x() - src_anchor.x()
        dy = tgt_anchor.y() - src_anchor.y()
        length = math.hypot(dx, dy)
        if length < 1:
            self.setPath(QPainterPath())
            return

        # Midpoint
        mid_x = (src_anchor.x() + tgt_anchor.x()) / 2
        mid_y = (src_anchor.y() + tgt_anchor.y()) / 2

        # Loop circle parameters
        loop_radius = max(22, min(40, length * 0.07))
        # The loop center is BELOW the midpoint
        loop_center_y = mid_y + loop_radius + 15

        path = QPainterPath()
        path.moveTo(src_anchor)

        # First segment: source to loop entry point (left side of loop)
        # Control point pushes down toward loop
        loop_entry_x = mid_x - loop_radius
        loop_entry_y = loop_center_y

        cp1_x = src_anchor.x() + dx * 0.35
        cp1_y = loop_center_y + loop_radius * 0.5

        path.cubicTo(QPointF(cp1_x, cp1_y),
                      QPointF(loop_entry_x - loop_radius * 0.5, loop_entry_y),
                      QPointF(loop_entry_x, loop_entry_y))

        # The loop itself: a full circle drawn as two semicircular arcs
        loop_rect = QRectF(mid_x - loop_radius, loop_center_y - loop_radius,
                           loop_radius * 2, loop_radius * 2)

        # Draw the loop as arc: start from the left (180°) go full circle
        path.arcTo(loop_rect, 180, -360)

        # After the loop, continue to target
        # Exit from the right side of the loop
        loop_exit_x = mid_x + loop_radius
        loop_exit_y = loop_center_y

        cp2_x = tgt_anchor.x() - dx * 0.35
        cp2_y = loop_center_y + loop_radius * 0.5

        path.cubicTo(QPointF(loop_exit_x + loop_radius * 0.5, loop_exit_y),
                      QPointF(cp2_x, cp2_y),
                      tgt_anchor)

        self.setPath(path)

        # Store loop center for icon drawing
        self._loop_center = QPointF(mid_x, loop_center_y)
        self._loop_radius = loop_radius

    # ── animation ─────────────────────────────────────────────────

    def _tick_spin(self) -> None:
        self._spin_phase += 4.0
        if self._spin_phase >= 360:
            self._spin_phase -= 360
        self.update()

    # ── painting ──────────────────────────────────────────────────

    def paint(self, painter: QPainter, option: QStyleOptionGraphicsItem,
              widget: QWidget = None) -> None:
        painter.setRenderHint(QPainter.Antialiasing, True)

        path = self.path()
        if path.elementCount() < 2:
            return

        # 1. Outer glow
        glow_pen = QPen(QColor(60, 220, 120, 25), 10, Qt.SolidLine)
        glow_pen.setCapStyle(Qt.RoundCap)
        painter.setPen(glow_pen)
        painter.drawPath(path)

        # 2. Main edge line
        main_color = self.COLOR.lighter(120) if self._hovered else self.COLOR
        pen = QPen(main_color, 2.8 + (0.8 if self._hovered else 0), Qt.SolidLine)
        pen.setCapStyle(Qt.RoundCap)
        pen.setJoinStyle(Qt.RoundJoin)
        painter.setPen(pen)
        painter.drawPath(path)

        # 3. Loop circle highlight — redraw the loop arc with emphasis
        if hasattr(self, '_loop_center'):
            lc = self._loop_center
            lr = self._loop_radius
            loop_rect = QRectF(lc.x() - lr, lc.y() - lr, lr * 2, lr * 2)

            # Brighter loop arc
            loop_pen = QPen(QColor(80, 240, 140, 180), 4, Qt.SolidLine, Qt.RoundCap)
            painter.setPen(loop_pen)
            painter.setBrush(Qt.NoBrush)
            painter.drawArc(loop_rect, 180 * 16, -360 * 16)

            # ⟳ icon — spinning arrow on the loop
            self._draw_loop_icon(painter, lc, lr)

        # 4. Arrowhead at target
        tgt_anchor = self._target.anchor_in
        src_pos = self._source.pos()
        tgt_pos = self._target.pos()
        tgt_size = self._target.size
        dx = tgt_pos.x() - src_pos.x()
        dy = tgt_pos.y() - src_pos.y()
        if abs(dy) > abs(dx) * 2.5:
            if dy >= 0:
                tgt_anchor = self._target.anchor_top
            else:
                tgt_anchor = QPointF(self._target.mapToScene(
                    QPointF(tgt_size.width() / 2, tgt_size.height())))
        elif dx < 0:
            tgt_anchor = QPointF(self._target.mapToScene(
                QPointF(tgt_size.width(), tgt_size.height() / 2)))

        pt_before = path.pointAtPercent(max(0, 1.0 - 0.04))
        angle = math.atan2(tgt_anchor.y() - pt_before.y(),
                           tgt_anchor.x() - pt_before.x())
        arrow_color = QColor(80, 240, 140) if not self._hovered else QColor(140, 255, 180)
        _draw_arrowhead(painter, tgt_anchor, angle, 14, arrow_color)

        # 5. "LOOP" label near the loop point
        if hasattr(self, '_loop_center'):
            label_center = QPointF(self._loop_center.x(),
                                   self._loop_center.y() - self._loop_radius - 16)
            label_font = QFont("Inter", 8, QFont.Bold)
            _draw_label_pill(
                painter, label_center, "⟳ LOOP",
                self.LABEL_COLOR, QColor(60, 220, 120, 120),
                label_font,
            )

    def _draw_loop_icon(self, painter: QPainter, center: QPointF,
                        radius: float) -> None:
        """Draw a spinning ⟳ icon at the loop center."""
        painter.save()
        painter.translate(center)
        painter.rotate(self._spin_phase)

        # Small spinning arrow circle
        icon_r = radius * 0.45
        icon_rect = QRectF(-icon_r, -icon_r, icon_r * 2, icon_r * 2)

        # Arc (almost full circle)
        arc_pen = QPen(QColor(140, 255, 180, 200), 2.5, Qt.SolidLine, Qt.RoundCap)
        painter.setPen(arc_pen)
        painter.setBrush(Qt.NoBrush)
        painter.drawArc(icon_rect, 30 * 16, 300 * 16)

        # Small arrowhead at the arc start
        start_angle_rad = math.radians(30)
        ax = icon_r * math.cos(start_angle_rad)
        ay = -icon_r * math.sin(start_angle_rad)
        tangent = start_angle_rad + math.pi / 2
        arrow_sz = 8
        p1 = QPointF(
            ax - arrow_sz * math.cos(tangent - math.pi / 5),
            ay + arrow_sz * math.sin(tangent - math.pi / 5),
        )
        p2 = QPointF(
            ax - arrow_sz * math.cos(tangent + math.pi / 5),
            ay + arrow_sz * math.sin(tangent + math.pi / 5),
        )
        arrow = QPolygonF([QPointF(ax, ay), p1, p2])
        painter.setPen(Qt.NoPen)
        painter.setBrush(QBrush(QColor(140, 255, 180, 220)))
        painter.drawPolygon(arrow)

        painter.restore()

    # ── hover ─────────────────────────────────────────────────────

    def hoverEnterEvent(self, event) -> None:
        self._hovered = True
        self.setZValue(8)
        bright = self.COLOR.lighter(140)
        pen = QPen(bright, 3.6, Qt.SolidLine)
        pen.setCapStyle(Qt.RoundCap)
        pen.setJoinStyle(Qt.RoundJoin)
        self.setPen(pen)
        super().hoverEnterEvent(event)

    def hoverLeaveEvent(self, event) -> None:
        self._hovered = False
        self.setZValue(5)
        pen = QPen(self.COLOR, 2.8, Qt.SolidLine)
        pen.setCapStyle(Qt.RoundCap)
        pen.setJoinStyle(Qt.RoundJoin)
        self.setPen(pen)
        super().hoverLeaveEvent(event)

    def itemChange(self, change, value):
        if change == QGraphicsItem.ItemSceneHasChanged:
            self._update_path()
        return super().itemChange(change, value)
