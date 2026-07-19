"""
EventBlock — a colored block representing an event in a time grid.

Used by DayView and WeekView. Supports:
  - Drag to move (preserves duration)
  - Drag bottom edge to resize duration
  - Click to select
  - Double-click to edit
  - Color from the event's calendar (or override)
  - Title, time, and (optionally) location/attendees
"""
from __future__ import annotations

from datetime import datetime, timedelta
from typing import Optional

from PySide6.QtCore import Qt, QRectF, QPointF, Signal, QMimeData, QPoint
from PySide6.QtGui import (
    QPainter, QPen, QBrush, QColor, QFont, QPainterPath, QLinearGradient,
    QMouseEvent, QDragEnterEvent, QDropEvent, QFontMetrics, QPixmap,
)
from PySide6.QtWidgets import (
    QWidget, QFrame, QLabel, QVBoxLayout, QHBoxLayout, QSizePolicy,
)

from ...calendar import Event as CalEvent, Calendar, EventType, Availability
from ..theme import Palette


# Pixels per minute (used to convert event duration to height)
DEFAULT_PX_PER_MINUTE = 1.0


class EventBlock(QFrame):
    """
    A colored event block in a time grid.

    The block is positioned absolutely by its parent view; this widget
    just renders the visual and handles interaction.
    """
    clicked = Signal(str)              # event_id
    doubleClicked = Signal(str)        # event_id
    moveRequested = Signal(str, datetime)  # event_id, new_start
    resizeRequested = Signal(str, int)    # event_id, new_duration_minutes

    DRAG_MIME = "application/x-kharazmi-event-id"

    def __init__(self, evt: CalEvent, calendar: Optional[Calendar],
                 px_per_minute: float = DEFAULT_PX_PER_MINUTE,
                 parent: QWidget = None) -> None:
        super().__init__(parent)
        self.evt = evt  # NOT self.event — that would shadow QFrame.event()!
        self.calendar = calendar
        self._px_per_minute = px_per_minute
        self._drag_mode: Optional[str] = None  # "move" | "resize"
        self._drag_start_pos: Optional[QPoint] = None
        self._drag_start_time: Optional[datetime] = None
        self._drag_start_duration: Optional[int] = None

        self.setCursor(Qt.OpenHandCursor if evt.availability != Availability.FREE
                       else Qt.PointingHandCursor)
        self.setObjectName("eventBlock")

        # Compute height
        height = max(20, int(evt.duration_minutes * px_per_minute))
        self.setMinimumHeight(20)
        self._expected_height = height

        self._apply_style()

        layout = QVBoxLayout(self)
        layout.setContentsMargins(6, 4, 6, 4)
        layout.setSpacing(0)

        # Title
        title_label = QLabel(evt.title)
        title_color = Palette.TEXT_ON_GOLD if self._is_dark_color(self._effective_color()) else Palette.TEXT_PRIMARY
        title_label.setStyleSheet(
            f"color: {title_color}; font-size: 11px; "
            f"font-weight: bold; background: transparent;"
        )
        title_label.setWordWrap(True)
        layout.addWidget(title_label)

        # Time
        time_str = f"{evt.start.strftime('%H:%M')} – {evt.end.strftime('%H:%M')}"
        time_label = QLabel(time_str)
        time_label.setStyleSheet(
            f"color: {title_color}; font-size: 9px; "
            f"font-family: 'JetBrains Mono', monospace; background: transparent;"
        )
        layout.addWidget(time_label)

        # Location
        if evt.location and height > 60:
            loc_label = QLabel(f"📍 {evt.location}")
            loc_label.setStyleSheet(
                f"color: {title_color}; font-size: 9px; background: transparent;"
            )
            loc_label.setWordWrap(True)
            layout.addWidget(loc_label)

        # Attendees
        if evt.attendees and height > 80:
            att_label = QLabel(f"👥 {' + '.join(a.name for a in evt.attendees[:3])}"
                                + (f" +{len(evt.attendees)-3}" if len(evt.attendees) > 3 else ""))
            att_label.setStyleSheet(
                f"color: {title_color}; font-size: 9px; background: transparent;"
            )
            layout.addWidget(att_label)

        # Set tooltip
        self.setToolTip(self._build_tooltip())

    def _effective_color(self) -> str:
        if self.evt.color:
            return self.evt.color
        if self.calendar:
            return self.calendar.color
        return Palette.GOLD_PRIMARY

    def _is_dark_color(self, hex_color: str) -> bool:
        """Return True if the color is dark enough that white text is needed."""
        try:
            hex_color = hex_color.lstrip("#")
            r = int(hex_color[0:2], 16)
            g = int(hex_color[2:4], 16)
            b = int(hex_color[4:6], 16)
            # Perceived brightness (ITU-R BT.601)
            brightness = 0.299 * r + 0.587 * g + 0.114 * b
            return brightness < 128
        except Exception:
            return False

    def _apply_style(self) -> None:
        color = self._effective_color()
        # Event-type specific styling
        if self.evt.event_type == EventType.FOCUS_TIME:
            border_style = "2px solid"
            border_color = Palette.GOLD_BRIGHT
        elif self.evt.event_type == EventType.OUT_OF_OFFICE:
            border_style = "2px dashed"
            border_color = color
        elif self.evt.event_type == EventType.TASK:
            border_style = "2px dotted"
            border_color = color
        else:
            border_style = "1px solid"
            border_color = color

        bg_alpha = "FF" if self.evt.availability != Availability.TENTATIVE else "80"
        # Strip # and add alpha
        bg_color = color.lstrip("#") + bg_alpha

        self.setStyleSheet(f"""
            QFrame#eventBlock {{
                background-color: #{bg_color};
                border: {border_style} {border_color};
                border-radius: 3px;
            }}
        """)

    def _build_tooltip(self) -> str:
        parts = [f"<b>{self.evt.title}</b>"]
        parts.append(f"{self.evt.start.strftime('%H:%M')} – {self.evt.end.strftime('%H:%M')}")
        if self.evt.location:
            parts.append(f"📍 {self.evt.location}")
        if self.evt.attendees:
            parts.append("👥 " + ", ".join(a.name for a in self.evt.attendees))
        if self.evt.is_recurring:
            parts.append(f"🔁 {self.evt.recurrence.to_rrule_str()}")
        if self.evt.event_type != EventType.NORMAL:
            parts.append(f"Type: {self.evt.event_type.value}")
        return "<br>".join(parts)

    # ---- Interaction ----
    def mousePressEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.LeftButton:
            self._drag_start_pos = event.position().toPoint()
            self._drag_start_time = self.evt.start
            self._drag_start_duration = self.evt.duration_minutes
            self.clicked.emit(self.evt.id)
            # Decide drag mode based on position
            if event.position().y() >= self.height() - 8 and self.height() > 30:
                self._drag_mode = "resize"
                self.setCursor(Qt.SizeVerCursor)
            else:
                self._drag_mode = "move"
                self.setCursor(Qt.ClosedHandCursor)
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        if not (event.buttons() & Qt.LeftButton) or self._drag_mode is None:
            return
        if self._drag_start_pos is None:
            return

        delta_y = event.position().toPoint().y() - self._drag_start_pos.y()
        delta_minutes = int(delta_y / self._px_per_minute)

        if self._drag_mode == "move":
            # Snap to 15-minute grid
            snapped_minutes = round(delta_minutes / 15) * 15
            new_start = self._drag_start_time + timedelta(minutes=snapped_minutes)
            # Don't actually move during drag — let the parent view decide
            # We emit moveRequested with the new start
            self.moveRequested.emit(self.evt.id, new_start)
        elif self._drag_mode == "resize":
            new_duration = max(15, self._drag_start_duration + delta_minutes)
            # Snap to 15-minute grid
            new_duration = round(new_duration / 15) * 15
            if new_duration != self._drag_start_duration:
                self.resizeRequested.emit(self.evt.id, new_duration)
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        self._drag_mode = None
        self._drag_start_pos = None
        self.setCursor(Qt.OpenHandCursor if self.evt.availability != Availability.FREE
                       else Qt.PointingHandCursor)
        super().mouseReleaseEvent(event)

    def mouseDoubleClickEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.LeftButton:
            self.doubleClicked.emit(self.evt.id)
        super().mouseDoubleClickEvent(event)
