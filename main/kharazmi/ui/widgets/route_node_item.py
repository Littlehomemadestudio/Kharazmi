"""
RouteNodeItem — a QGraphicsItem that renders a single RouteStep.

TRULY DYNAMIC SIZING:
  - Node width and height grow to fit the FULL title and description.
  - NO eliding, NO truncation, NO "…" — everything is shown.
  - Long descriptions wrap to multiple lines (up to a max, then the
    node grows taller).
  - Min width 240px, max width 600px (beyond that we wrap).

Each node shows:
  - Step ID badge + kind icon
  - Title (always full, wraps if needed)
  - Success probability ring
  - Duration
  - Location
  - Description (full, wrapped)
  - Fallback indicator
  - Sub-goals list (each on its own line)
  - Cost estimate
  - Risk-level color stripe + badge
  - Branch label

Color scheme by risk level:
  low → green, medium → gold, high → orange, severe → red
"""
from __future__ import annotations

import math
from typing import Optional

from PySide6.QtCore import Qt, QRectF, QPointF, Signal, QSizeF, QTimer, QPropertyAnimation, QEasingCurve, Property
from PySide6.QtGui import (
    QPainter, QPainterPath, QColor, QPen, QBrush, QFont, QLinearGradient,
    QFontMetrics, QPolygonF, QTextOption, QTextDocument,
)
from PySide6.QtWidgets import (
    QGraphicsObject, QGraphicsItem, QGraphicsSceneMouseEvent,
    QGraphicsSceneHoverEvent, QStyleOptionGraphicsItem, QWidget,
)

from ...ai import RouteStep
from ..theme import Palette


# Sizing constants
MIN_NODE_WIDTH = 240
MAX_NODE_WIDTH = 600
PADDING = 14
TITLE_HEIGHT = 22
META_HEIGHT = 16
RING_RADIUS = 22
LINE_SPACING = 4

_RISK_COLORS = {
    "low":      "#5A8A5A",
    "medium":   "#D4AF37",
    "high":     "#A87A4A",
    "severe":   "#A85A5A",
}

_KIND_ICONS = {
    "action":     "▶",
    "decision":   "◇",
    "milestone":  "★",
    "wait":       "⏸",
    "checkpoint": "✓",
}


def _wrap_text_to_width(text: str, max_width: float, font: QFont) -> list[str]:
    """Word-wrap text to fit max_width. Returns list of lines."""
    if not text:
        return []
    fm = QFontMetrics(font)
    words = text.split()
    if not words:
        return [""]
    lines = []
    current = ""
    for word in words:
        if current:
            test = current + " " + word
        else:
            test = word
        if fm.horizontalAdvance(test) <= max_width:
            current = test
        else:
            if current:
                lines.append(current)
            # If the single word is too long, hard-break it
            if fm.horizontalAdvance(word) > max_width:
                # Hard-break the word
                cur_part = ""
                for ch in word:
                    if fm.horizontalAdvance(cur_part + ch) <= max_width:
                        cur_part += ch
                    else:
                        if cur_part:
                            lines.append(cur_part)
                        cur_part = ch
                current = cur_part
            else:
                current = word
    if current:
        lines.append(current)
    return lines


class RouteNodeItem(QGraphicsObject):
    """
    A draggable, editable route-step node.

    Auto-sizes to fit FULL content. NO truncation.

    Signals:
      - nodeClicked(step_id)
      - nodeDoubleClicked(step_id)
      - nodeMoved(step_id, x, y)
      - nodeEdited(step_id, new_title, new_description)
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
        self._height: float = 140

        # Animation state — for entrance animation
        self._opacity = 0.0
        self._scale = 0.7

        self.setFlag(QGraphicsItem.ItemIsMovable, True)
        self.setFlag(QGraphicsItem.ItemIsSelectable, True)
        self.setFlag(QGraphicsItem.ItemSendsGeometryChanges, True)
        self.setAcceptHoverEvents(True)
        self.setZValue(10)

        # Compute auto-size
        self._compute_size()

        # Set initial opacity to 0 for entrance animation
        self.setOpacity(0.0)
        self.setScale(0.7)

    def _compute_size(self) -> None:
        """Compute width/height to fit ALL content (no truncation)."""
        title_font = QFont("Inter", 11, QFont.DemiBold)
        body_font = QFont("Inter", 9)
        meta_font = QFont("Inter", 9)
        small_font = QFont("Inter", 8)
        mono_font = QFont("JetBrains Mono", 9)

        fm_title = QFontMetrics(title_font)
        fm_body = QFontMetrics(body_font)
        fm_meta = QFontMetrics(meta_font)
        fm_mono = QFontMetrics(mono_font)

        # Available content width (excluding left ring column + right padding)
        left_col_width = RING_RADIUS * 2 + 16  # ring + spacing
        right_padding = 14
        content_max_width = MAX_NODE_WIDTH - left_col_width - right_padding - PADDING * 2

        # Start with min width, grow if needed
        target_width = MIN_NODE_WIDTH

        # Title — measure full width, grow node if needed
        title_text = self.step.title or "Untitled step"
        title_w = fm_title.horizontalAdvance(title_text)
        # If title fits in current target_width, single line. Else, wrap.
        avail_title_w = target_width - left_col_width - right_padding - PADDING
        if title_w > avail_title_w:
            # Try to grow width up to MAX
            needed_w = title_w + left_col_width + right_padding + PADDING * 2
            target_width = max(target_width, min(MAX_NODE_WIDTH, needed_w))
        avail_title_w = target_width - left_col_width - right_padding - PADDING
        title_lines = _wrap_text_to_width(title_text, avail_title_w, title_font)
        if not title_lines:
            title_lines = ["Untitled step"]

        # Description — full text, wrapped
        desc_lines = []
        if self.step.description:
            avail_desc_w = target_width - left_col_width - right_padding - PADDING
            desc_lines = _wrap_text_to_width(self.step.description, avail_desc_w, body_font)

        # Location
        loc_text = f"📍 {self.step.location}" if self.step.location else ""
        loc_lines = []
        if loc_text:
            avail_loc_w = target_width - left_col_width - right_padding - PADDING
            loc_lines = _wrap_text_to_width(loc_text, avail_loc_w, meta_font)

        # Sub-goals — each on its own line
        sub_goal_lines = []
        if self.step.sub_goals:
            avail_sg_w = target_width - left_col_width - right_padding - PADDING - 20
            for sg in self.step.sub_goals:
                sg_lines = _wrap_text_to_width(f"◆ {sg}", avail_sg_w, small_font)
                sub_goal_lines.extend(sg_lines)

        # Fallback
        fb_lines = []
        if self.step.fallback:
            avail_fb_w = target_width - left_col_width - right_padding - PADDING - 20
            fb_lines = _wrap_text_to_width(f"↩ {self.step.fallback}", avail_fb_w, small_font)

        # Cost
        cost_w = fm_mono.horizontalAdvance(self.step.cost_estimate) if self.step.cost_estimate else 0

        # Compute total height
        # Layout:
        #   padding top (8)
        #   title lines (TITLE_HEIGHT * len(title_lines))
        #   meta row (META_HEIGHT) — duration + branch + kind
        #   spacing (8)
        #   ring column starts here (left side)
        #   location lines (META_HEIGHT * len(loc_lines))
        #   description lines (14 * len(desc_lines))
        #   spacing (6)
        #   sub-goal lines (12 * len(sub_goal_lines))
        #   fallback lines (12 * len(fb_lines))
        #   padding bottom (8) + risk badge row (14)

        title_h = TITLE_HEIGHT * len(title_lines)
        meta_h = META_HEIGHT
        loc_h = META_HEIGHT * len(loc_lines) if loc_lines else 0
        desc_h = 14 * len(desc_lines) if desc_lines else 0
        sub_goals_h = 14 * len(sub_goal_lines) if sub_goal_lines else 0
        fallback_h = 14 * len(fb_lines) if fb_lines else 0

        # The ring takes up vertical space on the left; we need at least
        # ring_radius * 2 + 16 of vertical content to look balanced
        ring_h = RING_RADIUS * 2 + 16

        content_h = (
            8 +  # top padding
            title_h +
            4 +
            meta_h +
            8 +
            loc_h +
            (4 if loc_h else 0) +
            desc_h +
            (6 if desc_h else 0) +
            sub_goals_h +
            (4 if sub_goals_h else 0) +
            fallback_h +
            8 +  # bottom padding
            16  # risk badge row
        )
        # Ensure at least ring_h
        content_h = max(content_h, ring_h + 30)

        self._width = target_width
        self._height = content_h

        # Cache for painting
        self._title_lines = title_lines
        self._desc_lines = desc_lines
        self._loc_lines = loc_lines
        self._sub_goal_lines = sub_goal_lines
        self._fb_lines = fb_lines

    # ---- Geometry ----
    def boundingRect(self) -> QRectF:
        return QRectF(-8, -8, self._width + 16, self._height + 16)

    def shape(self) -> QPainterPath:
        path = QPainterPath()
        path.addRoundedRect(0, 0, self._width, self._height, 12, 12)
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
        kind_icon = _KIND_ICONS.get(self.step.kind, "▶")

        # 1. Selection / hover halo
        if self.isSelected():
            painter.setBrush(QBrush(QColor(255, 255, 255, 30)))
            painter.setPen(QPen(QColor(Palette.GOLD_BRIGHT), 2))
            painter.drawRoundedRect(-2, -2, self._width + 4, self._height + 4, 14, 14)
        elif self._hovered:
            painter.setBrush(QBrush(QColor(0, 0, 0, 80)))
            painter.setPen(QPen(risk_color, 1))
            painter.drawRoundedRect(-1, -1, self._width + 2, self._height + 2, 13, 13)

        # 2. Background gradient
        bg = QLinearGradient(0, 0, 0, self._height)
        bg.setColorAt(0, QColor(Palette.BG_ELEVATED))
        bg.setColorAt(1, QColor(Palette.BG_TERTIARY))
        painter.setBrush(QBrush(bg))
        painter.setPen(QPen(risk_color, 1.5))
        painter.drawRoundedRect(0, 0, self._width, self._height, 12, 12)

        # 3. Left risk-color stripe
        painter.setBrush(QBrush(risk_color))
        painter.setPen(Qt.NoPen)
        path = QPainterPath()
        path.addRoundedRect(QRectF(0, 0, 4, self._height), 2, 2)
        painter.fillPath(path, QBrush(risk_color))

        # 4. Step ID badge + kind icon (top-left)
        id_font = QFont("JetBrains Mono", 8, QFont.Bold)
        painter.setFont(id_font)
        painter.setBrush(QBrush(risk_color))
        painter.setPen(Qt.NoPen)
        painter.drawRoundedRect(QRectF(10, 10, 50, 18), 4, 4)
        painter.setPen(QPen(QColor(Palette.TEXT_ON_GOLD)))
        painter.drawText(QRectF(10, 10, 50, 18), Qt.AlignCenter,
                         f"{kind_icon} {self.step.id.upper()}")

        # 5. Branch label (top-left, below ID badge)
        branch_font = QFont("Inter", 7, QFont.Bold)
        painter.setFont(branch_font)
        painter.setPen(QPen(QColor(Palette.TEXT_TERTIARY)))
        painter.drawText(QRectF(10, 30, 80, 12), Qt.AlignLeft,
                         self.step.branch.upper())

        # 6. Title (full, wrapped)
        title_font = QFont("Inter", 11, QFont.DemiBold)
        painter.setFont(title_font)
        painter.setPen(QPen(QColor(Palette.TEXT_PRIMARY)))
        title_x = 70
        title_w = self._width - title_x - 14
        y = 10
        for line in self._title_lines:
            painter.drawText(QRectF(title_x, y, title_w, TITLE_HEIGHT),
                             Qt.AlignLeft | Qt.AlignVCenter, line)
            y += TITLE_HEIGHT

        # 7. Meta row (duration + risk badge, top-right)
        dur_font = QFont("JetBrains Mono", 9, QFont.Bold)
        painter.setFont(dur_font)
        painter.setPen(QPen(QColor(Palette.GOLD_BRIGHT)))
        dur_text = f"⏱ {self.step.duration_minutes}m"
        painter.drawText(QRectF(self._width - 90, 10, 80, 18),
                         Qt.AlignRight | Qt.AlignVCenter, dur_text)

        # Risk badge (top-right, below duration)
        risk_font = QFont("Inter", 7, QFont.Bold)
        painter.setFont(risk_font)
        risk_text = self.step.risk_level.upper()
        fm = QFontMetrics(risk_font)
        rw = fm.horizontalAdvance(risk_text) + 10
        painter.setBrush(QBrush(risk_color))
        painter.setPen(Qt.NoPen)
        painter.drawRoundedRect(QRectF(self._width - rw - 10, 30, rw, 14), 3, 3)
        painter.setPen(QPen(QColor(Palette.TEXT_ON_GOLD)))
        painter.drawText(QRectF(self._width - rw - 10, 30, rw, 14),
                         Qt.AlignCenter, risk_text)

        # 8. Success probability ring (left side, below branch label)
        ring_center = QPointF(34, 80)
        ring_radius = RING_RADIUS
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
        painter.setFont(QFont("JetBrains Mono", 9, QFont.Bold))
        painter.setPen(QPen(QColor(Palette.TEXT_PRIMARY)))
        painter.drawText(
            QRectF(ring_center.x() - ring_radius, ring_center.y() - ring_radius,
                   ring_radius * 2, ring_radius * 2),
            Qt.AlignCenter, f"{int(prob * 100)}%"
        )

        # 9. Right-side content (location, description, sub-goals, fallback)
        text_x = 70
        text_w = self._width - text_x - 14
        y = 50

        # Location
        if self._loc_lines:
            loc_font = QFont("Inter", 9)
            painter.setFont(loc_font)
            painter.setPen(QPen(QColor(Palette.TEXT_SECONDARY)))
            for line in self._loc_lines:
                painter.drawText(QRectF(text_x, y, text_w, META_HEIGHT),
                                 Qt.AlignLeft | Qt.AlignVCenter, line)
                y += META_HEIGHT
            y += 4

        # Description (full, wrapped)
        if self._desc_lines:
            desc_font = QFont("Inter", 9)
            painter.setFont(desc_font)
            painter.setPen(QPen(QColor(Palette.TEXT_SECONDARY)))
            for line in self._desc_lines:
                painter.drawText(QRectF(text_x, y, text_w, 14),
                                 Qt.AlignLeft | Qt.AlignVCenter, line)
                y += 14
            y += 6

        # Sub-goals
        if self._sub_goal_lines:
            sg_font = QFont("Inter", 8)
            painter.setFont(sg_font)
            painter.setPen(QPen(QColor(Palette.TEXT_TERTIARY)))
            for line in self._sub_goal_lines:
                painter.drawText(QRectF(text_x + 4, y, text_w - 4, 14),
                                 Qt.AlignLeft | Qt.AlignVCenter, line)
                y += 14
            y += 4

        # Fallback
        if self._fb_lines:
            fb_font = QFont("Inter", 8, QFont.Bold)
            painter.setFont(fb_font)
            painter.setPen(QPen(QColor(Palette.GOLD_PRIMARY)))
            for line in self._fb_lines:
                painter.drawText(QRectF(text_x + 4, y, text_w - 4, 14),
                                 Qt.AlignLeft | Qt.AlignVCenter, line)
                y += 14

        # 10. Cost estimate (bottom-right)
        if self.step.cost_estimate:
            cost_font = QFont("JetBrains Mono", 8)
            painter.setFont(cost_font)
            painter.setPen(QPen(QColor(Palette.TEXT_TERTIARY)))
            painter.drawText(QRectF(self._width - 110, self._height - 22, 98, 14),
                             Qt.AlignRight, self.step.cost_estimate)

    # ---- Entrance animation ----
    def animate_entrance(self, delay_ms: int = 0) -> None:
        """Fade-in + scale-up animation, with optional delay."""
        def _start():
            # Animate opacity 0 → 1
            self._opacity_anim = QPropertyAnimation(self, b"opacity")
            self._opacity_anim.setDuration(400)
            self._opacity_anim.setStartValue(0.0)
            self._opacity_anim.setEndValue(1.0)
            self._opacity_anim.setEasingCurve(QEasingCurve.OutCubic)
            self._opacity_anim.start()
            # Animate scale 0.7 → 1.0
            self._scale_anim = QPropertyAnimation(self, b"scale")
            self._scale_anim.setDuration(400)
            self._scale_anim.setStartValue(0.7)
            self._scale_anim.setEndValue(1.0)
            self._scale_anim.setEasingCurve(QEasingCurve.OutBack)
            self._scale_anim.start()
        if delay_ms > 0:
            QTimer.singleShot(delay_ms, _start)
        else:
            _start()

    # ---- Interaction ----
    def hoverEnterEvent(self, event: QGraphicsSceneHoverEvent) -> None:
        self._hovered = True
        self.setZValue(20)
        self.update()
        tip_parts = [f"<b>{self.step.title}</b>"]
        tip_parts.append(f"ID: {self.id_display}")
        tip_parts.append(f"Duration: {self.step.duration_minutes} min")
        tip_parts.append(f"Success: {self.step.success_probability:.0%}")
        tip_parts.append(f"Risk: {self.step.risk_level}")
        tip_parts.append(f"Branch: {self.step.branch}")
        tip_parts.append(f"Kind: {self.step.kind}")
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

    @property
    def id_display(self) -> str:
        return self.step.id.upper()

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

    @property
    def anchor_top(self) -> QPointF:
        return self.mapToScene(QPointF(self._width / 2, 0))

    @property
    def anchor_bottom(self) -> QPointF:
        return self.mapToScene(QPointF(self._width / 2, self._height))
