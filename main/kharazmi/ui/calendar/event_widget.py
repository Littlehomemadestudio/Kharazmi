"""
EventWidget — Interactive event card for the RASK! calendar Day/Week view.

A custom-painted QWidget representing a single timed event. Supports:
  - Hover highlight (tracked via enterEvent/leaveEvent)
  - Selection state (gold ring)
  - Drag-to-move (click and drag the card body)
  - Drag-to-resize (drag the bottom 6px handle)
  - 15-minute snap increments during drag/resize
  - Right-click context menu (Edit, Delete, Toggle Complete, Change Color)
  - Signals for all interactions

Rendering is delegated to EventRenderer so visual style stays centralised.
"""
from __future__ import annotations

from datetime import datetime, timedelta
from typing import Optional

from PySide6.QtCore import Qt, Signal, QPoint, QRectF, QTimer
from PySide6.QtGui import QPainter, QCursor, QMouseEvent, QContextMenuEvent
from PySide6.QtWidgets import QWidget, QMenu

from ...calendar.event import Event
from .theme import Metrics, Surface, Gold, Text, EventColors, font_body, font_small, qcolor
from .event_renderer import EventRenderer, EventRenderOptions
from .animation import HoverGlow


# ──────────────────────────────── Mouse State ─────────────────────────────

class _MouseState:
    """Tracks the current mouse interaction mode."""
    NONE = "none"
    PRESS = "press"          # mouse pressed, but not yet dragged past threshold
    DRAG_MOVE = "drag_move"  # actively dragging the event body
    DRAG_RESIZE = "drag_resize"  # actively dragging the resize handle


# ──────────────────────────────── EventWidget ─────────────────────────────

class EventWidget(QWidget):
    """
    Interactive event card widget for Day/Week timeline views.

    Renders via EventRenderer and provides drag-to-move, drag-to-resize,
    hover effects, selection, and a context menu.
    """

    # ── Signals ──
    clicked = Signal(str)                    # event_id
    double_clicked = Signal(str)             # event_id
    drag_started = Signal(str)               # event_id
    drag_moved = Signal(str, int)            # event_id, delta_minutes
    drag_ended = Signal(str)                 # event_id
    resize_started = Signal(str)             # event_id
    resize_moved = Signal(str, int)          # event_id, delta_minutes
    resize_ended = Signal(str)               # event_id
    toggle_complete_requested = Signal(str)  # event_id

    # ── Construction ──

    def __init__(self, event: Event, color: str, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)

        self._event: Event = event
        self._color: str = color
        self._hovered: bool = False
        self._selected: bool = False

        # Mouse / drag state
        self._mouse_state: str = _MouseState.NONE
        self._press_pos: Optional[QPoint] = None          # global pos at press
        self._drag_origin_pos: Optional[QPoint] = None     # widget pos at drag start
        self._drag_origin_start: Optional[datetime] = None  # event.start at drag start
        self._drag_origin_end: Optional[datetime] = None    # event.end at drag start
        self._last_snap_minutes: int = 0                    # last emitted snap delta

        # Resize state
        self._resize_origin_height: int = 0                 # widget height at resize start
        self._resize_origin_end: Optional[datetime] = None  # event.end at resize start

        # Hover glow animation
        self._glow = HoverGlow(self, Metrics.ANIM_FAST_MS)

        # Widget configuration
        self.setMinimumHeight(Metrics.MIN_EVENT_HEIGHT)
        self.setMouseTracking(True)
        self.setAttribute(Qt.WA_Hover, False)  # we handle hover ourselves
        self.setFocusPolicy(Qt.StrongFocus)

    # ── Public API ──

    @property
    def event_id(self) -> str:
        """The unique identifier of the displayed event."""
        return self._event.id

    @property
    def event(self) -> Event:
        """Current event data."""
        return self._event

    def set_event(self, event: Event) -> None:
        """Update the event data and repaint."""
        self._event = event
        self.update()

    @property
    def color(self) -> str:
        """The calendar color for the left border."""
        return self._color

    @color.setter
    def color(self, value: str) -> None:
        self._color = value
        self.update()

    @property
    def hovered(self) -> bool:
        return self._hovered

    @property
    def selected(self) -> bool:
        return self._selected

    def set_selected(self, selected: bool) -> None:
        """Set the visual selection state and repaint."""
        if self._selected != selected:
            self._selected = selected
            self.update()

    def is_dragging(self) -> bool:
        """Whether a drag or resize operation is in progress."""
        return self._mouse_state in (_MouseState.DRAG_MOVE, _MouseState.DRAG_RESIZE)

    # ── Rendering ──

    def paintEvent(self, event) -> None:  # noqa: N802 — Qt naming
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        try:
            rect = QRectF(0, 0, self.width(), self.height())

            options = EventRenderOptions(
                show_time=True,
                show_icon=True,
                show_location=True,
                show_attendees=bool(self._event.attendees),
                show_completion=True,
                show_priority=True,
                compact=self.height() < Metrics.MIN_EVENT_HEIGHT + 12,
                hovered=self._hovered,
                selected=self._selected,
                dragging=self.is_dragging(),
            )

            EventRenderer.paint(painter, rect, self._event, self._color, options)

            # ── Resize handle indicator ──
            # Draw a subtle grip at the bottom when hovered or selected
            if self._hovered or self._selected:
                self._paint_resize_handle(painter, rect)
        finally:
            painter.end()

    def _paint_resize_handle(self, painter: QPainter, rect: QRectF) -> None:
        """Paint the resize grip indicator at the bottom edge."""
        handle_h = Metrics.RESIZE_HANDLE_H
        handle_rect = QRectF(
            rect.left() + Metrics.EVENT_LEFT_BORDER + Metrics.EVENT_PAD,
            rect.bottom() - handle_h,
            rect.width() - Metrics.EVENT_LEFT_BORDER - 2 * Metrics.EVENT_PAD,
            handle_h,
        )

        # Draw three small centered dots as a grip indicator
        cx = handle_rect.center().x()
        cy = handle_rect.center().y()
        dot_color = qcolor(Text.TERTIARY)
        dot_color.setAlpha(120)
        painter.setPen(Qt.NoPen)
        painter.setBrush(dot_color)

        for offset in (-6, 0, 6):
            painter.drawEllipse(QPoint(int(cx + offset), int(cy)), 1, 1)

    # ── Hit Testing ──

    def _is_in_resize_zone(self, pos: QPoint) -> bool:
        """Return True if `pos` is within the bottom resize handle zone."""
        return pos.y() >= self.height() - Metrics.RESIZE_HANDLE_H

    # ── Snap ──

    @staticmethod
    def _snap_minutes(minutes: int) -> int:
        """Snap to the nearest 15-minute increment."""
        snap = Metrics.SNAP_MINUTES
        return round(minutes / snap) * snap

    @staticmethod
    def _pixels_to_minutes(pixels: int) -> int:
        """Convert a vertical pixel delta to minutes (based on HOUR_HEIGHT)."""
        return int(pixels * 60 / Metrics.HOUR_HEIGHT)

    # ── Mouse Events ──

    def mousePressEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        if event.button() == Qt.LeftButton:
            self._press_pos = event.globalPosition().toPoint()
            self._drag_origin_pos = self.pos()
            self._drag_origin_start = self._event.start
            self._drag_origin_end = self._event.end
            self._resize_origin_height = self.height()
            self._last_snap_minutes = 0

            if self._is_in_resize_zone(event.position().toPoint()):
                self._mouse_state = _MouseState.PRESS  # will become DRAG_RESIZE
                self._resize_origin_end = self._event.end
            else:
                self._mouse_state = _MouseState.PRESS  # will become DRAG_MOVE

            event.accept()
        else:
            event.ignore()

    def mouseMoveEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        # ── Cursor shape ──
        if self._mouse_state == _MouseState.NONE:
            if self._is_in_resize_zone(event.position().toPoint()):
                self.setCursor(QCursor(Qt.SizeVerCursor))
            else:
                self.setCursor(QCursor(Qt.OpenHandCursor))
            event.accept()
            return

        if self._press_pos is None:
            event.ignore()
            return

        global_pos = event.globalPosition().toPoint()
        delta = global_pos - self._press_pos

        # ── Threshold check: don't start drag until past threshold ──
        if self._mouse_state == _MouseState.PRESS:
            if abs(delta.y()) < Metrics.DRAG_THRESHOLD and abs(delta.x()) < Metrics.DRAG_THRESHOLD:
                event.accept()
                return
            # Crossed threshold — decide which mode
            if self._is_in_resize_zone(self._press_pos - self.mapToGlobal(QPoint(0, 0))):
                self._mouse_state = _MouseState.DRAG_RESIZE
                self.setCursor(QCursor(Qt.SizeVerCursor))
                self.resize_started.emit(self._event.id)
            else:
                self._mouse_state = _MouseState.DRAG_MOVE
                self.setCursor(QCursor(Qt.ClosedHandCursor))
                self.drag_started.emit(self._event.id)

        # ── Drag move ──
        if self._mouse_state == _MouseState.DRAG_MOVE:
            delta_minutes = self._snap_minutes(self._pixels_to_minutes(delta.y()))
            if delta_minutes != self._last_snap_minutes:
                self._last_snap_minutes = delta_minutes
                self.drag_moved.emit(self._event.id, delta_minutes)
            event.accept()
            return

        # ── Drag resize ──
        if self._mouse_state == _MouseState.DRAG_RESIZE:
            delta_minutes = self._snap_minutes(self._pixels_to_minutes(delta.y()))
            if delta_minutes != self._last_snap_minutes:
                self._last_snap_minutes = delta_minutes
                self.resize_moved.emit(self._event.id, delta_minutes)
            event.accept()
            return

        event.ignore()

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        if event.button() == Qt.LeftButton:
            state = self._mouse_state
            press_pos = self._press_pos

            # Reset state
            self._mouse_state = _MouseState.NONE
            self._press_pos = None
            self._drag_origin_pos = None
            self._drag_origin_start = None
            self._drag_origin_end = None
            self._resize_origin_height = 0
            self._resize_origin_end = None

            if state == _MouseState.DRAG_MOVE:
                self.setCursor(QCursor(Qt.OpenHandCursor))
                self.drag_ended.emit(self._event.id)
                event.accept()
                return

            if state == _MouseState.DRAG_RESIZE:
                self.setCursor(QCursor(Qt.SizeVerCursor))
                self.resize_ended.emit(self._event.id)
                event.accept()
                return

            # Was just a press without crossing threshold → click
            if state == _MouseState.PRESS:
                self.clicked.emit(self._event.id)
                event.accept()
                return

        event.ignore()

    def mouseDoubleClickEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        if event.button() == Qt.LeftButton:
            self.double_clicked.emit(self._event.id)
            event.accept()
        else:
            event.ignore()

    # ── Hover ──

    def enterEvent(self, event) -> None:  # noqa: N802
        self._hovered = True
        self._glow.enter()
        self.update()
        super().enterEvent(event)

    def leaveEvent(self, event) -> None:  # noqa: N802
        self._hovered = False
        self._glow.leave()
        self.update()
        super().leaveEvent(event)

    # ── Context Menu ──

    def contextMenuEvent(self, event: QContextMenuEvent) -> None:  # noqa: N802
        menu = QMenu(self)
        menu.setStyleSheet(self._context_menu_stylesheet())

        action_edit = menu.addAction("✏️  Edit")
        menu.addSeparator()
        action_delete = menu.addAction("🗑  Delete")

        # Toggle complete — always available for any event type
        menu.addSeparator()
        if self._event.completed:
            action_toggle = menu.addAction("☐  Mark Incomplete")
        else:
            action_toggle = menu.addAction("☑  Mark Complete")

        # Change color submenu
        menu.addSeparator()
        color_menu = menu.addMenu("🎨  Change Color")
        for c in EventColors.all():
            color_action = color_menu.addAction(self._color_swatch_text(c))
            color_action.setData(c)

        # Execute and handle
        chosen = menu.exec(event.globalPos())

        if chosen is None:
            return

        if chosen == action_edit:
            self.double_clicked.emit(self._event.id)

        elif chosen == action_delete:
            self._context_action = "delete"
            self.clicked.emit(self._event.id)

        elif chosen == action_toggle:
            self.toggle_complete_requested.emit(self._event.id)

        elif chosen.data() is not None:
            # Color change
            new_color = chosen.data()
            if isinstance(new_color, str) and new_color.startswith("#"):
                self._color = new_color
                self.update()

    def _context_action_value(self) -> Optional[str]:
        """Return and clear the last context-menu action intent."""
        val = getattr(self, "_context_action", None)
        self._context_action = None
        return val

    @staticmethod
    def _color_swatch_text(hex_color: str) -> str:
        """Produce a menu label for a color swatch."""
        name_map = {
            "#D4AF37": "Gold",
            "#5A7FA8": "Blue",
            "#4A9A8A": "Teal",
            "#C07060": "Coral",
            "#8A6AAA": "Purple",
            "#5A9A5A": "Green",
            "#C08A4A": "Orange",
            "#B06080": "Pink",
            "#6A7A8A": "Slate",
            "#7A6AB0": "Lavender",
        }
        name = name_map.get(hex_color, hex_color)
        return f"  ●  {name}"

    @staticmethod
    def _context_menu_stylesheet() -> str:
        """Dark-themed stylesheet for the context menu."""
        return (
            "QMenu {"
            "  background-color: #1A1A1E;"
            "  color: #F5F0DC;"
            "  border: 1px solid #2A2A33;"
            "  border-radius: 6px;"
            "  padding: 4px 0px;"
            "}"
            "QMenu::item {"
            "  padding: 6px 24px 6px 16px;"
            "  border-radius: 3px;"
            "}"
            "QMenu::item:selected {"
            "  background-color: #2A2A32;"
            "}"
            "QMenu::separator {"
            "  height: 1px;"
            "  background: #2A2A33;"
            "  margin: 4px 8px;"
            "}"
        )

    # ── Keyboard ──

    def keyPressEvent(self, event) -> None:  # noqa: N802
        """Handle keyboard interaction when the widget has focus."""
        if event.key() in (Qt.Key_Return, Qt.Key_Enter):
            self.double_clicked.emit(self._event.id)
            event.accept()
        elif event.key() == Qt.Key_Delete:
            self._context_action = "delete"
            self.clicked.emit(self._event.id)
            event.accept()
        elif event.key() == Qt.Key_Space:
            self.clicked.emit(self._event.id)
            event.accept()
        else:
            super().keyPressEvent(event)
