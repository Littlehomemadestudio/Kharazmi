"""
EventRenderer — QPainter-based event card rendering.

Renders calendar events as rounded cards with:
  - Colored left border (calendar color)
  - Priority color indicator
  - Title text
  - Time text (for timed events)
  - Icons for event type
  - AI-generated badge
  - Completion badge (checkbox)
  - Attendee avatars
  - Location pin
  - Hover highlight
  - Selection ring
"""
from __future__ import annotations

from datetime import datetime
from typing import Optional

from PySide6.QtCore import Qt, QRectF, QPointF
from PySide6.QtGui import (
    QPainter, QColor, QPen, QBrush, QFont, QLinearGradient,
    QPainterPath, QPolygonF, QFontMetrics,
)
from PySide6.QtWidgets import QStyleOptionViewItem

from ...calendar.event import Event
from ...calendar.enums import EventType, EventStatus
from ...core.shamsi import format_shamsi
from .theme import (
    Surface, Gold, Text, Border, Metrics, PRIORITY_COLORS,
    EVENT_TYPE_ICONS, qcolor, with_alpha, lighten, darken,
    font_body, font_small, font_header,
)


# ──────────────────────────────── Render Context ──────────────────────────

class EventRenderOptions:
    """Controls what gets rendered on an event card."""
    def __init__(
        self,
        show_time: bool = True,
        show_icon: bool = True,
        show_location: bool = True,
        show_attendees: bool = False,
        show_completion: bool = True,
        show_priority: bool = True,
        compact: bool = False,
        hovered: bool = False,
        selected: bool = False,
        dragging: bool = False,
    ) -> None:
        self.show_time = show_time
        self.show_icon = show_icon
        self.show_location = show_location
        self.show_attendees = show_attendees
        self.show_completion = show_completion
        self.show_priority = show_priority
        self.compact = compact
        self.hovered = hovered
        self.selected = selected
        self.dragging = dragging


# ──────────────────────────────── Renderer ────────────────────────────────

class EventRenderer:
    """Static methods for painting event cards."""

    @staticmethod
    def paint(
        painter: QPainter,
        rect: QRectF,
        event: Event,
        color: str,
        options: EventRenderOptions = EventRenderOptions(),
    ) -> None:
        """Paint a single event card into `rect`."""
        painter.save()
        painter.setRenderHint(QPainter.Antialiasing, True)

        c = qcolor(color)
        r = Metrics.EVENT_CORNER_RADIUS
        border_w = Metrics.EVENT_LEFT_BORDER
        pad = Metrics.EVENT_PAD

        # ── Background ──
        bg_color = qcolor(Surface.CARD)
        if options.hovered:
            bg_color = qcolor(Surface.CARD_HOVER)
        if options.selected:
            bg_color = qcolor(Surface.CARD_ACTIVE)

        # Card body path
        card_path = QPainterPath()
        card_path.addRoundedRect(rect, r, r)
        painter.setPen(Qt.NoPen)
        painter.setBrush(QBrush(bg_color))
        painter.drawPath(card_path)

        # ── Left color bar ──
        bar_rect = QRectF(rect.left(), rect.top(), border_w, rect.height())
        bar_path = QPainterPath()
        # Left bar with rounded corners on the left side only
        bar_path.moveTo(rect.left() + r, rect.top())
        bar_path.lineTo(rect.left() + border_w, rect.top())
        bar_path.lineTo(rect.left() + border_w, rect.bottom())
        bar_path.lineTo(rect.left() + r, rect.bottom())
        bar_path.arcTo(QRectF(rect.left(), rect.bottom() - 2*r, 2*r, 2*r), 270, 90)
        bar_path.lineTo(rect.left(), rect.top() + r)
        bar_path.arcTo(QRectF(rect.left(), rect.top(), 2*r, 2*r), 180, 90)
        bar_path.closeSubpath()

        bar_color = c
        if event.completed:
            bar_color = qcolor("#5A8A5A")  # done green
        painter.setBrush(QBrush(bar_color))
        painter.drawPath(bar_path)

        # ── Selection ring ──
        if options.selected:
            painter.setPen(QPen(qcolor(Gold.PRIMARY), 1.5))
            painter.setBrush(Qt.NoBrush)
            painter.drawRoundedRect(rect.adjusted(0.5, 0.5, -0.5, -0.5), r, r)

        # ── Hover glow ──
        if options.hovered and not options.selected:
            glow = with_alpha(Gold.PRIMARY, 25)
            painter.setPen(QPen(glow, 1))
            painter.setBrush(Qt.NoBrush)
            painter.drawRoundedRect(rect.adjusted(0.5, 0.5, -0.5, -0.5), r, r)

        # ── Dragging effect ──
        if options.dragging:
            painter.setOpacity(0.75)

        # ── Content area ──
        content_left = rect.left() + border_w + pad
        content_right = rect.right() - pad
        content_top = rect.top() + pad
        content_width = content_right - content_left

        if content_width < 20:
            painter.restore()
            return

        y = content_top

        # ── Completion checkbox ──
        if options.show_completion and event.is_task:
            check_size = 12 if not options.compact else 10
            check_rect = QRectF(content_left, y, check_size, check_size)
            painter.setPen(QPen(qcolor(Border.STRONG), 1))
            painter.setBrush(QBrush(qcolor(Surface.ELEVATED)))
            painter.drawRoundedRect(check_rect, 2, 2)
            if event.completed:
                painter.setPen(QPen(qcolor("#5A8A5A"), 1.5))
                painter.setBrush(Qt.NoBrush)
                # Draw checkmark
                cx, cy = check_rect.center().x(), check_rect.center().y()
                painter.drawLine(QPointF(cx - 3, cy), QPointF(cx - 1, cy + 3))
                painter.drawLine(QPointF(cx - 1, cy + 3), QPointF(cx + 4, cy - 3))
            content_left += check_size + pad

        # ── Priority dot ──
        if options.show_priority and not options.compact:
            pri_color = PRIORITY_COLORS.get(0, "#5C5749")
            # No priority field on Event directly; skip for now
            # Could be derived from event_type or custom field

        # ── Title ──
        title_font = font_body() if not options.compact else font_small()
        if event.completed:
            title_font.setStrikeOut(True)
        painter.setFont(title_font)

        title_color = qcolor(Text.PRIMARY) if not event.completed else qcolor(Text.TERTIARY)
        painter.setPen(QPen(title_color))

        title_text = event.title
        if options.show_icon:
            icon = EVENT_TYPE_ICONS.get(event.event_type.value, "")
            if icon:
                title_text = f"{icon}  {title_text}"

        fm = QFontMetrics(title_font)
        elided = fm.elidedText(title_text, Qt.ElideRight, int(content_width))
        painter.drawText(
            QRectF(content_left, y, content_width, fm.height()),
            Qt.AlignLeft | Qt.AlignVCenter,
            elided,
        )
        y += fm.height() + 1

        # ── Time ──
        if options.show_time and not event.all_day:
            time_font = font_small()
            painter.setFont(time_font)
            painter.setPen(QPen(qcolor(Text.TERTIARY)))

            time_text = f"{format_shamsi(event.start, 'HH:mm')} – {format_shamsi(event.end, 'HH:mm')}"
            if event.is_recurring:
                time_text += "  ↻"
            painter.drawText(
                QRectF(content_left, y, content_width, fm.height()),
                Qt.AlignLeft | Qt.AlignVCenter,
                time_text,
            )
            y += fm.height() + 1

        # ── Location ──
        if options.show_location and event.location and not options.compact:
            loc_font = font_small()
            painter.setFont(loc_font)
            painter.setPen(QPen(qcolor(Text.TERTIARY)))
            loc_text = f"📍 {event.location}"
            fm_loc = QFontMetrics(loc_font)
            elided_loc = fm_loc.elidedText(loc_text, Qt.ElideRight, int(content_width))
            painter.drawText(
                QRectF(content_left, y, content_width, fm_loc.height()),
                Qt.AlignLeft | Qt.AlignVCenter,
                elided_loc,
            )

        # ── Attendees (compact dots) ──
        if options.show_attendees and event.attendees:
            dot_y = rect.bottom() - pad - 6
            dot_x = content_left
            for i, att in enumerate(event.attendees[:5]):
                painter.setBrush(QBrush(with_alpha(color, 150)))
                painter.setPen(Qt.NoPen)
                painter.drawEllipse(QPointF(dot_x + 3, dot_y + 3), 3, 3)
                dot_x += 8

        painter.restore()

    @staticmethod
    def paint_month_chip(
        painter: QPainter,
        rect: QRectF,
        event: Event,
        color: str,
        hovered: bool = False,
        selected: bool = False,
    ) -> None:
        """Paint a compact event chip for the month view."""
        painter.save()
        painter.setRenderHint(QPainter.Antialiasing, True)

        c = qcolor(color)
        r = 3  # small corner radius for chips

        # Background
        bg = with_alpha(color, 35)
        if hovered:
            bg = with_alpha(color, 55)
        if selected:
            bg = with_alpha(color, 70)

        painter.setPen(Qt.NoPen)
        painter.setBrush(QBrush(bg))
        painter.drawRoundedRect(rect, r, r)

        # Left dot
        dot_r = 3
        dot_rect = QRectF(rect.left() + 4, rect.center().y() - dot_r, dot_r * 2, dot_r * 2)
        painter.setBrush(QBrush(c))
        painter.drawEllipse(dot_rect)

        # Title
        font = font_small()
        if event.completed:
            font.setStrikeOut(True)
        painter.setFont(font)
        painter.setPen(QPen(qcolor(Text.PRIMARY)))

        text_left = dot_rect.right() + 3
        text_width = rect.right() - text_left - 2
        if text_width > 0:
            fm = QFontMetrics(font)
            title = event.title
            if event.is_task:
                title = ("☑ " if event.completed else "☐ ") + title
            elided = fm.elidedText(title, Qt.ElideRight, int(text_width))
            painter.drawText(
                QRectF(text_left, rect.top(), text_width, rect.height()),
                Qt.AlignLeft | Qt.AlignVCenter,
                elided,
            )

        # Selection ring
        if selected:
            painter.setPen(QPen(qcolor(Gold.PRIMARY), 1))
            painter.setBrush(Qt.NoBrush)
            painter.drawRoundedRect(rect.adjusted(0.5, 0.5, -0.5, -0.5), r, r)

        painter.restore()

    @staticmethod
    def paint_all_day_chip(
        painter: QPainter,
        rect: QRectF,
        event: Event,
        color: str,
        hovered: bool = False,
        selected: bool = False,
    ) -> None:
        """Paint an all-day event chip (used in week/day view header)."""
        painter.save()
        painter.setRenderHint(QPainter.Antialiasing, True)

        c = qcolor(color)
        r = 4

        # Filled background with event color
        bg = with_alpha(color, 45)
        if hovered:
            bg = with_alpha(color, 65)

        painter.setPen(Qt.NoPen)
        painter.setBrush(QBrush(bg))
        painter.drawRoundedRect(rect, r, r)

        # Left bar
        bar = QRectF(rect.left(), rect.top(), 3, rect.height())
        painter.setBrush(QBrush(c))
        painter.drawRoundedRect(bar, 1, 1)

        # Title
        font = font_small()
        painter.setFont(font)
        painter.setPen(QPen(qcolor(Text.PRIMARY)))

        text_left = rect.left() + 5
        text_width = rect.right() - text_left - 2
        if text_width > 0:
            fm = QFontMetrics(font)
            elided = fm.elidedText(event.title, Qt.ElideRight, int(text_width))
            painter.drawText(
                QRectF(text_left, rect.top(), text_width, rect.height()),
                Qt.AlignLeft | Qt.AlignVCenter,
                elided,
            )

        if selected:
            painter.setPen(QPen(qcolor(Gold.PRIMARY), 1))
            painter.setBrush(Qt.NoBrush)
            painter.drawRoundedRect(rect.adjusted(0.5, 0.5, -0.5, -0.5), r, r)

        painter.restore()
