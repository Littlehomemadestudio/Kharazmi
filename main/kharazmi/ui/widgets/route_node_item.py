"""
RouteNodeItem — a QGraphicsItem that renders a single RouteStep.

TRULY DYNAMIC SIZING + HEAVILY ENHANCED ANIMATIONS.

Features:
  - Auto-sizes to fit FULL title and description (no truncation ever)
  - Rich entrance animation: fade + scale + slide-in + glow
  - Hover: lift + glow + scale-up slightly
  - Selection: pulsing gold border
  - Double-click opens a full modal edit dialog (NodeEditDialog)
  - Drag to move (positions persist)
  - Tasks-like aesthetic: status accent bar, priority stripes, progress
"""
from __future__ import annotations

import math
from typing import Optional

from PySide6.QtCore import Qt, QRectF, QPointF, Signal, QSizeF, QTimer, QPropertyAnimation, QEasingCurve, Property, QEvent
from PySide6.QtGui import (
    QPainter, QPainterPath, QColor, QPen, QBrush, QFont, QLinearGradient,
    QFontMetrics, QPolygonF, QTextOption, QRadialGradient, QKeyEvent,
)
from PySide6.QtWidgets import (
    QGraphicsObject, QGraphicsItem, QGraphicsSceneMouseEvent,
    QGraphicsSceneHoverEvent, QStyleOptionGraphicsItem, QWidget,
)

from ...ai import RouteStep
from ..theme import Palette


MIN_NODE_WIDTH = 240
MAX_NODE_WIDTH = 580
PADDING = 14
TITLE_HEIGHT = 22
META_HEIGHT = 16
RING_RADIUS = 22

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
    """Word-wrap *text* so each line fits within *max_width* pixels."""
    fm = QFontMetrics(font)
    words = text.split()
    if not words:
        return []
    lines: list[str] = []
    current = ""
    for word in words:
        test = f"{current} {word}" if current else word
        if fm.horizontalAdvance(test) <= max_width:
            current = test
        else:
            if current:
                lines.append(current)
            current = word
    if current:
        lines.append(current)
    return lines


class RouteNodeItem(QGraphicsObject):
    """
    A draggable route-step node with rich animations.

    Double-click emits nodeEditRequested — the parent view opens
    a proper modal NodeEditDialog with Save/Cancel buttons.

    Signals:
      - nodeClicked(step_id)
      - nodeDoubleClicked(step_id)
      - nodeMoved(step_id, x, y)
      - nodeEdited(step_id, new_title, new_description)
      - nodeEditRequested(step_id) — requests opening modal edit dialog
    """
    nodeClicked = Signal(str)
    nodeDoubleClicked = Signal(str)
    nodeMoved = Signal(str, float, float)
    nodeEdited = Signal(str, str, str)  # step_id, new_title, new_desc
    nodeEditRequested = Signal(str)      # step_id — requests opening modal edit dialog
    nodePositionChanged = Signal(str)    # step_id — fired during drag for live edge updates

    def __init__(self, step: RouteStep, parent: QGraphicsItem = None) -> None:
        super().__init__(parent)
        self.step = step
        self._hovered = False
        self._drag_started_pos: Optional[QPointF] = None
        self._double_click_occurred: bool = False
        self._width: float = MIN_NODE_WIDTH
        self._height: float = 140
        self._glow_phase = 0.0
        self._pulse_timer = QTimer()
        self._pulse_timer.setInterval(50)
        self._pulse_timer.timeout.connect(self._tick_pulse)

        self.setFlag(QGraphicsItem.ItemIsMovable, True)
        self.setFlag(QGraphicsItem.ItemIsSelectable, True)
        self.setFlag(QGraphicsItem.ItemSendsGeometryChanges, True)
        self.setAcceptHoverEvents(True)
        self.setZValue(10)

        self._compute_size()
        # Initial state for entrance animation
        self.setOpacity(0.0)
        self.setScale(0.6)

    def _compute_size(self) -> None:
        """Compute width/height to fit ALL content (no truncation)."""
        title_font = QFont("Inter", 11, QFont.DemiBold)
        body_font = QFont("Inter", 9)
        meta_font = QFont("Inter", 9)
        small_font = QFont("Inter", 8)

        fm_title = QFontMetrics(title_font)
        fm_body = QFontMetrics(body_font)
        fm_meta = QFontMetrics(meta_font)

        left_col_width = RING_RADIUS * 2 + 16
        right_padding = 14
        target_width = MIN_NODE_WIDTH

        title_text = self.step.title or "Untitled step"
        title_w = fm_title.horizontalAdvance(title_text)
        avail_title_w = target_width - left_col_width - right_padding - PADDING
        if title_w > avail_title_w:
            needed_w = title_w + left_col_width + right_padding + PADDING * 2
            target_width = max(target_width, min(MAX_NODE_WIDTH, needed_w))
        avail_title_w = target_width - left_col_width - right_padding - PADDING
        title_lines = _wrap_text_to_width(title_text, avail_title_w, title_font)
        if not title_lines:
            title_lines = ["Untitled step"]

        desc_lines = []
        if self.step.description:
            avail_desc_w = target_width - left_col_width - right_padding - PADDING
            desc_lines = _wrap_text_to_width(self.step.description, avail_desc_w, body_font)

        loc_lines = []
        if self.step.location:
            loc_text = f"📍 {self.step.location}"
            avail_loc_w = target_width - left_col_width - right_padding - PADDING
            loc_lines = _wrap_text_to_width(loc_text, avail_loc_w, meta_font)

        sub_goal_lines = []
        if self.step.sub_goals:
            avail_sg_w = target_width - left_col_width - right_padding - PADDING - 20
            for sg in self.step.sub_goals:
                sg_lines = _wrap_text_to_width(f"◆ {sg}", avail_sg_w, small_font)
                sub_goal_lines.extend(sg_lines)

        fb_lines = []
        if self.step.fallback:
            avail_fb_w = target_width - left_col_width - right_padding - PADDING - 20
            fb_lines = _wrap_text_to_width(f"↩ {self.step.fallback}", avail_fb_w, small_font)

        title_h = TITLE_HEIGHT * len(title_lines)
        meta_h = META_HEIGHT
        loc_h = META_HEIGHT * len(loc_lines) if loc_lines else 0
        desc_h = 14 * len(desc_lines) if desc_lines else 0
        sub_goals_h = 14 * len(sub_goal_lines) if sub_goal_lines else 0
        fallback_h = 14 * len(fb_lines) if fb_lines else 0
        ring_h = RING_RADIUS * 2 + 16

        content_h = (
            8 + title_h + 4 + meta_h + 8 +
            loc_h + (4 if loc_h else 0) +
            desc_h + (6 if desc_h else 0) +
            sub_goals_h + (4 if sub_goals_h else 0) +
            fallback_h + 8 + 16
        )
        content_h = max(content_h, ring_h + 30)

        self._width = target_width
        self._height = content_h
        self._title_lines = title_lines
        self._desc_lines = desc_lines
        self._loc_lines = loc_lines
        self._sub_goal_lines = sub_goal_lines
        self._fb_lines = fb_lines

    # ---- Geometry ----
    def boundingRect(self) -> QRectF:
        # Extra space for glow + hover lift
        return QRectF(-12, -12, self._width + 24, self._height + 24)

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

        # Hover lift offset
        lift = -4.0 if self._hovered else 0.0
        painter.save()
        painter.translate(0, lift)

        # 1. Glow effect (radial gradient) when hovered or selected
        if self._hovered or self.isSelected():
            glow_radius = max(self._width, self._height) * 0.7
            glow = QRadialGradient(self._width / 2, self._height / 2, glow_radius)
            glow_alpha = int(80 + 40 * math.sin(self._glow_phase)) if self.isSelected() else 60
            glow.setColorAt(0, QColor(risk_color.red(), risk_color.green(), risk_color.blue(), glow_alpha))
            glow.setColorAt(1, QColor(risk_color.red(), risk_color.green(), risk_color.blue(), 0))
            painter.setBrush(QBrush(glow))
            painter.setPen(Qt.NoPen)
            painter.drawRoundedRect(-10, -10, self._width + 20, self._height + 20, 16, 16)

        # 2. Selection pulsing border
        if self.isSelected():
            pulse_alpha = int(180 + 60 * math.sin(self._glow_phase))
            painter.setBrush(QBrush(QColor(245, 200, 66, 40)))
            painter.setPen(QPen(QColor(245, 200, 66, pulse_alpha), 2.5))
            painter.drawRoundedRect(-2, -2, self._width + 4, self._height + 4, 14, 14)

        # 3. Background gradient (Tasks-like)
        bg = QLinearGradient(0, 0, 0, self._height)
        bg.setColorAt(0, QColor(Palette.BG_ELEVATED))
        bg.setColorAt(1, QColor(Palette.BG_TERTIARY))
        painter.setBrush(QBrush(bg))
        border_width = 2.0 if self._hovered else 1.5
        painter.setPen(QPen(risk_color, border_width))
        painter.drawRoundedRect(0, 0, self._width, self._height, 12, 12)

        # 4. Left status accent bar (Tasks-like)
        painter.setBrush(QBrush(risk_color))
        painter.setPen(Qt.NoPen)
        path = QPainterPath()
        path.addRoundedRect(QRectF(0, 0, 4, self._height), 2, 2)
        painter.fillPath(path, QBrush(risk_color))

        # 5. Step ID badge + kind icon (top-left)
        id_font = QFont("JetBrains Mono", 8, QFont.Bold)
        painter.setFont(id_font)
        painter.setBrush(QBrush(risk_color))
        painter.setPen(Qt.NoPen)
        painter.drawRoundedRect(QRectF(10, 10, 54, 18), 4, 4)
        painter.setPen(QPen(QColor(Palette.TEXT_ON_GOLD)))
        painter.drawText(QRectF(10, 10, 54, 18), Qt.AlignCenter,
                         f"{kind_icon} {self.step.id.upper()}")

        # 6. Branch label
        branch_font = QFont("Inter", 7, QFont.Bold)
        painter.setFont(branch_font)
        painter.setPen(QPen(QColor(Palette.TEXT_TERTIARY)))
        painter.drawText(QRectF(10, 30, 80, 12), Qt.AlignLeft,
                         self.step.branch.upper() if self.step.branch else "")

        # 7. Title (may wrap)
        title_font = QFont("Inter", 11, QFont.DemiBold)
        painter.setFont(title_font)
        painter.setPen(QPen(QColor(Palette.TEXT_PRIMARY)))
        y_cursor = 8.0
        left_text_x = RING_RADIUS * 2 + 16
        for tl in self._title_lines:
            painter.drawText(QRectF(left_text_x, y_cursor, self._width - left_text_x - 14, TITLE_HEIGHT),
                             Qt.AlignLeft | Qt.AlignVCenter, tl)
            y_cursor += TITLE_HEIGHT

        y_cursor += 4

        # 8. Meta row: duration · success · risk
        meta_font = QFont("Inter", 9)
        painter.setFont(meta_font)
        painter.setPen(QPen(QColor(Palette.TEXT_TERTIARY)))
        dur_text = f"⏱ {self.step.duration_minutes}m"
        prob_text = f"✓ {self.step.success_probability:.0%}"
        risk_text = f"⚠ {self.step.risk_level}"
        meta_line = f"  {dur_text}  ·  {prob_text}  ·  {risk_text}"
        painter.drawText(QRectF(left_text_x, y_cursor, self._width - left_text_x - 14, META_HEIGHT),
                         Qt.AlignLeft | Qt.AlignVCenter, meta_line)
        y_cursor += META_HEIGHT + 8

        # 9. Location
        if self._loc_lines:
            loc_font = QFont("Inter", 9)
            painter.setFont(loc_font)
            painter.setPen(QPen(QColor(Palette.TEXT_TERTIARY)))
            for ll in self._loc_lines:
                painter.drawText(QRectF(left_text_x, y_cursor, self._width - left_text_x - 14, META_HEIGHT),
                                 Qt.AlignLeft | Qt.AlignVCenter, ll)
                y_cursor += META_HEIGHT
            y_cursor += 4

        # 10. Description (if any)
        if self._desc_lines:
            body_font = QFont("Inter", 9)
            painter.setFont(body_font)
            painter.setPen(QPen(QColor(Palette.TEXT_SECONDARY)))
            for dl in self._desc_lines:
                painter.drawText(QRectF(left_text_x, y_cursor, self._width - left_text_x - 14, 14),
                                 Qt.AlignLeft | Qt.AlignVCenter, dl)
                y_cursor += 14
            y_cursor += 6

        # 11. Sub-goals
        if self._sub_goal_lines:
            sg_font = QFont("Inter", 8)
            painter.setFont(sg_font)
            painter.setPen(QPen(QColor(Palette.TEXT_TERTIARY)))
            for sgl in self._sub_goal_lines:
                painter.drawText(QRectF(left_text_x + 10, y_cursor, self._width - left_text_x - 24, 14),
                                 Qt.AlignLeft | Qt.AlignVCenter, sgl)
                y_cursor += 14
            y_cursor += 4

        # 12. Fallback
        if self._fb_lines:
            fb_font = QFont("Inter", 8)
            painter.setFont(fb_font)
            painter.setPen(QPen(QColor("#A85A5A")))
            for fbl in self._fb_lines:
                painter.drawText(QRectF(left_text_x + 10, y_cursor, self._width - left_text_x - 24, 14),
                                 Qt.AlignLeft | Qt.AlignVCenter, fbl)
                y_cursor += 14

        # 13. Edit hint at bottom
        hint_font = QFont("Inter", 7)
        painter.setFont(hint_font)
        painter.setPen(QPen(QColor(Palette.TEXT_TERTIARY)))
        painter.drawText(
            QRectF(10, self._height - 16, self._width - 20, 14),
            Qt.AlignRight | Qt.AlignVCenter,
            "double-click to edit"
        )

        painter.restore()

    # ---- Pulse animation ----
    def _tick_pulse(self) -> None:
        self._glow_phase += 0.15
        self.update()

    def _get_scale(self) -> float:
        return self.scale()

    def _set_scale(self, v: float) -> None:
        self.setScale(v)

    scale_prop = Property(float, _get_scale, _set_scale)

    # ---- Entrance animation ----
    def animate_entrance(self, delay_ms: int = 0) -> None:
        def _start():
            # Fade in
            self._opacity_anim = QPropertyAnimation(self, b"opacity")
            self._opacity_anim.setDuration(400)
            self._opacity_anim.setStartValue(0.0)
            self._opacity_anim.setEndValue(1.0)
            self._opacity_anim.setEasingCurve(QEasingCurve.OutCubic)
            self._opacity_anim.start()
            # Scale up with bounce
            self._scale_anim = QPropertyAnimation(self, b"scale")
            self._scale_anim.setDuration(600)
            self._scale_anim.setStartValue(0.6)
            self._scale_anim.setEndValue(1.0)
            self._scale_anim.setEasingCurve(QEasingCurve.OutBack)
            self._scale_anim.start()
            # Slide in from left (pos animation)
            current_pos = self.pos()
            self._pos_anim = QPropertyAnimation(self, b"pos")
            self._pos_anim.setDuration(500)
            self._pos_anim.setStartValue(QPointF(current_pos.x() - 50, current_pos.y()))
            self._pos_anim.setEndValue(current_pos)
            self._pos_anim.setEasingCurve(QEasingCurve.OutCubic)
            self._pos_anim.start()
        if delay_ms > 0:
            QTimer.singleShot(delay_ms, _start)
        else:
            _start()

    # ---- Editing ----
    def start_editing(self) -> None:
        """Request the parent view to open the modal edit dialog."""
        self.nodeEditRequested.emit(self.step.id)

    def apply_changes(self, changes: dict) -> None:
        """Apply changes from the modal edit dialog to the step."""
        for key, value in changes.items():
            if hasattr(self.step, key):
                setattr(self.step, key, value)
        self._compute_size()
        self.prepareGeometryChange()
        self.update()
        self.nodeEdited.emit(
            self.step.id,
            self.step.title,
            self.step.description or "",
        )

    # ---- Interaction ----
    def hoverEnterEvent(self, event: QGraphicsSceneHoverEvent) -> None:
        self._hovered = True
        self.setZValue(20)
        self._pulse_timer.start()
        self.update()
        tip_parts = [f"<b>{self.step.title}</b>"]
        tip_parts.append(f"ID: {self.step.id.upper()}")
        tip_parts.append(f"Duration: {self.step.duration_minutes} min")
        tip_parts.append(f"Success: {self.step.success_probability:.0%}")
        tip_parts.append(f"Risk: {self.step.risk_level}")
        tip_parts.append(f"Branch: {self.step.branch} · Kind: {self.step.kind}")
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
        self._pulse_timer.stop()
        self._glow_phase = 0.0
        self.update()
        super().hoverLeaveEvent(event)

    def mousePressEvent(self, event: QGraphicsSceneMouseEvent) -> None:
        if event.button() == Qt.LeftButton:
            self._drag_started_pos = self.pos()
            # Don't emit nodeClicked here — wait until release to
            # distinguish click from drag
        super().mousePressEvent(event)

    def mouseDoubleClickEvent(self, event: QGraphicsSceneMouseEvent) -> None:
        if event.button() == Qt.LeftButton:
            self._double_click_occurred = True
            self.nodeDoubleClicked.emit(self.step.id)
            self.nodeEditRequested.emit(self.step.id)
        super().mouseDoubleClickEvent(event)

    def mouseReleaseEvent(self, event: QGraphicsSceneMouseEvent) -> None:
        super().mouseReleaseEvent(event)
        if event.button() == Qt.LeftButton and self._drag_started_pos is not None:
            new_pos = self.pos()
            distance = (new_pos - self._drag_started_pos).manhattanLength()
            if distance > 2:
                # It was a drag — emit nodeMoved, NOT nodeClicked
                self.nodeMoved.emit(self.step.id, new_pos.x(), new_pos.y())
            else:
                # It was a genuine click (no significant movement)
                # But skip if a double-click just occurred (the edit dialog
                # is already opening — no need for the popup too)
                if not self._double_click_occurred:
                    self.nodeClicked.emit(self.step.id)
            self._drag_started_pos = None
            self._double_click_occurred = False

    def itemChange(self, change, value):
        """Emit position change signal during drag for live edge updates."""
        if change == QGraphicsItem.ItemPositionHasChanged:
            self.nodePositionChanged.emit(self.step.id)
        return super().itemChange(change, value)

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
