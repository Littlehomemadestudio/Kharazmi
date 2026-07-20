"""
InsightBubble — a floating overlay box that appears around the route graph.

Shows AI-generated insights (alternatives, breakthroughs, questions,
warnings, improvements) as rounded, color-coded boxes that float on
top of the canvas near relevant nodes.

Each bubble is:
  - Draggable (user can reposition)
  - Selectable
  - Color-coded by kind:
    alternative → blue
    breakthrough → bright gold
    question → teal
    warning → red
    improvement → muted gold

Bubbles can be anchored to a specific step (then float near its node)
or positioned freely on the canvas.
"""
from __future__ import annotations

import math
from typing import Optional

from PySide6.QtCore import Qt, QRectF, QPointF, Signal
from PySide6.QtGui import (
    QPainter, QPainterPath, QColor, QPen, QBrush, QFont, QLinearGradient,
    QFontMetrics, QPolygonF,
)
from PySide6.QtWidgets import (
    QGraphicsObject, QGraphicsItem, QGraphicsSceneMouseEvent,
    QGraphicsSceneHoverEvent, QStyleOptionGraphicsItem, QWidget,
)

from ...ai import Insight
from ..theme import Palette


_KIND_COLORS = {
    "alternative":  "#5A7FA8",   # blue
    "breakthrough": "#F5C842",   # bright gold
    "question":     "#5AA8A8",   # teal
    "warning":      "#A85A5A",   # red
    "improvement":  "#D4AF37",   # muted gold
}

_KIND_ICONS = {
    "alternative":  "⇄",   # alternative
    "breakthrough": "✦",   # breakthrough
    "question":     "?",   # question
    "warning":      "⚠",   # warning
    "improvement":  "↗",   # improvement
}

MIN_BUBBLE_WIDTH = 180
MAX_BUBBLE_WIDTH = 280


class InsightBubble(QGraphicsObject):
    """
    A floating insight overlay box.

    Draggable, selectable, auto-sized to fit content.
    """
    bubbleClicked = Signal(str)  # insight id (we use a generated one)
    bubbleMoved = Signal(str, float, float)

    def __init__(self, insight: Insight, bubble_id: str,
                 parent: QGraphicsItem = None) -> None:
        super().__init__(parent)
        self.insight = insight
        self.bubble_id = bubble_id
        self._hovered = False
        self._drag_started_pos: Optional[QPointF] = None
        self._width: float = MIN_BUBBLE_WIDTH
        self._height: float = 100

        self.setFlag(QGraphicsItem.ItemIsMovable, True)
        self.setFlag(QGraphicsItem.ItemIsSelectable, True)
        self.setFlag(QGraphicsItem.ItemSendsGeometryChanges, True)
        self.setAcceptHoverEvents(True)
        self.setZValue(30)  # above nodes

        self._compute_size()

    def _compute_size(self) -> None:
        title_font = QFont("Inter", 10, QFont.DemiBold)
        body_font = QFont("Inter", 9)
        fm_title = QFontMetrics(title_font)
        fm_body = QFontMetrics(body_font)

        title_w = fm_title.horizontalAdvance(self.insight.title)
        # Body wrapped at MAX width
        body_w = fm_body.horizontalAdvance(self.insight.body)

        # Try to fit body in 3 lines
        target_w = max(title_w + 40, 180)
        # Increase width if body doesn't fit
        for w in [180, 220, 260, 280]:
            lines = self._wrap_count(self.insight.body, w - 24, body_font)
            if lines <= 3:
                target_w = w
                break
            target_w = w

        self._width = target_w
        body_lines = self._wrap_count(self.insight.body, self._width - 24, body_font)
        body_lines = min(body_lines, 4)
        self._height = 38 + body_lines * 16 + 12  # header + body + padding

    def _wrap_count(self, text: str, max_width: float, font: QFont) -> int:
        fm = QFontMetrics(font)
        words = text.split()
        lines = 1
        current = ""
        for word in words:
            test = (current + " " + word).strip()
            if fm.horizontalAdvance(test) <= max_width:
                current = test
            else:
                if current:
                    lines += 1
                current = word
        return lines

    # ---- Geometry ----
    def boundingRect(self) -> QRectF:
        return QRectF(-4, -4, self._width + 8, self._height + 8)

    def shape(self) -> QPainterPath:
        path = QPainterPath()
        path.addRoundedRect(0, 0, self._width, self._height, 12, 12)
        return path

    # ---- Painting ----
    def paint(self, painter: QPainter, option: QStyleOptionGraphicsItem,
              widget: QWidget = None) -> None:
        painter.setRenderHint(QPainter.Antialiasing, True)
        painter.setRenderHint(QPainter.TextAntialiasing, True)

        kind_color_str = _KIND_COLORS.get(self.insight.kind, _KIND_COLORS["improvement"])
        kind_color = QColor(kind_color_str)
        icon = _KIND_ICONS.get(self.insight.kind, "•")

        # Shadow / hover halo
        if self._hovered or self.isSelected():
            painter.setBrush(QBrush(QColor(kind_color.red(), kind_color.green(), kind_color.blue(), 40)))
            painter.setPen(QPen(Qt.NoPen))
            painter.drawRoundedRect(-4, -4, self._width + 8, self._height + 8, 14, 14)

        # Background — semi-transparent dark with colored border
        bg = QLinearGradient(0, 0, 0, self._height)
        bg.setColorAt(0, QColor(Palette.BG_TERTIARY))
        bg.setColorAt(1, QColor(Palette.BG_SECONDARY))
        painter.setBrush(QBrush(bg))
        painter.setPen(QPen(kind_color, 2 if self._hovered or self.isSelected() else 1.5))
        painter.drawRoundedRect(0, 0, self._width, self._height, 12, 12)

        # Left color stripe
        painter.setBrush(QBrush(kind_color))
        painter.setPen(Qt.NoPen)
        path = QPainterPath()
        path.addRoundedRect(QRectF(0, 0, 4, self._height), 2, 2)
        painter.fillPath(path, QBrush(kind_color))

        # Icon (top-left)
        icon_font = QFont("Inter", 12, QFont.Bold)
        painter.setFont(icon_font)
        painter.setPen(QPen(kind_color))
        painter.drawText(QRectF(10, 6, 22, 22), Qt.AlignCenter, icon)

        # Kind label (top-left next to icon)
        kind_font = QFont("Inter", 8, QFont.Bold)
        painter.setFont(kind_font)
        painter.setPen(QPen(QColor(Palette.TEXT_TERTIARY)))
        kind_text = self.insight.kind.upper()
        painter.drawText(QRectF(34, 8, self._width - 44, 14),
                         Qt.AlignLeft | Qt.AlignVCenter, kind_text)

        # Title
        title_font = QFont("Inter", 10, QFont.DemiBold)
        painter.setFont(title_font)
        painter.setPen(QPen(QColor(Palette.TEXT_PRIMARY)))
        title = self._elide_text(self.insight.title, self._width - 24, title_font)
        painter.drawText(QRectF(12, 24, self._width - 24, 18),
                         Qt.AlignLeft | Qt.AlignVCenter, title)

        # Body (wrapped)
        body_font = QFont("Inter", 9)
        painter.setFont(body_font)
        painter.setPen(QPen(QColor(Palette.TEXT_SECONDARY)))
        body = self._wrap_text(self.insight.body, self._width - 24, body_font, max_lines=4)
        painter.drawText(QRectF(12, 44, self._width - 24, self._height - 50),
                         Qt.AlignLeft | Qt.AlignTop | Qt.TextWordWrap, body)

    def _elide_text(self, text: str, max_width: float, font: QFont) -> str:
        fm = QFontMetrics(font)
        if fm.horizontalAdvance(text) <= max_width:
            return text
        elided = text
        while elided and fm.horizontalAdvance(elided + "…") > max_width:
            elided = elided[:-1]
        return elided + "…" if elided else "…"

    def _wrap_text(self, text: str, max_width: float, font: QFont,
                   max_lines: int = 4) -> str:
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
        # Elide last line if we dropped words
        if len(lines) == max_lines:
            consumed = " ".join(lines).split()
            if len(consumed) < len(words):
                last = lines[-1]
                while last and fm.horizontalAdvance(last + "…") > max_width:
                    last = last[:-1]
                lines[-1] = last + "…" if last else "…"
        return "\n".join(lines)

    # ---- Interaction ----
    def hoverEnterEvent(self, event: QGraphicsSceneHoverEvent) -> None:
        self._hovered = True
        self.setZValue(40)
        self.update()
        self.setToolTip(
            f"<b>{self.insight.title}</b><br>"
            f"<i>{self.insight.kind}</i><br><br>"
            f"{self.insight.body}"
        )
        super().hoverEnterEvent(event)

    def hoverLeaveEvent(self, event: QGraphicsSceneHoverEvent) -> None:
        self._hovered = False
        self.setZValue(30)
        self.update()
        super().hoverLeaveEvent(event)

    def mousePressEvent(self, event: QGraphicsSceneMouseEvent) -> None:
        if event.button() == Qt.LeftButton:
            self._drag_started_pos = self.pos()
            self.bubbleClicked.emit(self.bubble_id)
        super().mousePressEvent(event)

    def mouseReleaseEvent(self, event: QGraphicsSceneMouseEvent) -> None:
        super().mouseReleaseEvent(event)
        if self._drag_started_pos is not None:
            new_pos = self.pos()
            if (new_pos - self._drag_started_pos).manhattanLength() > 2:
                self.bubbleMoved.emit(self.bubble_id, new_pos.x(), new_pos.y())
            self._drag_started_pos = None
