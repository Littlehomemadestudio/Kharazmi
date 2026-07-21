"""
GlassTitleBar — Custom frameless window title bar with glassmorphic effect.

Features:
  - Frosted-glass blurred background (simulated with semi-transparent layers)
  - Gold accent line at the top
  - Custom min / max / close buttons with hover glow animations
  - Draggable window movement
  - Double-click to maximize/restore
  - App icon + title on the left

This replaces the default OS title bar for a premium, branded look.
"""
from __future__ import annotations

from typing import Optional

from PySide6.QtCore import Qt, Signal, QTimer, QPropertyAnimation, QEasingCurve, QSize
from PySide6.QtGui import (
    QPainter, QColor, QPen, QBrush, QFont, QIcon, QPixmap,
    QPainterPath, QLinearGradient, QRadialGradient,
)
from PySide6.QtWidgets import (
    QWidget, QHBoxLayout, QVBoxLayout, QLabel, QPushButton,
    QSizePolicy, QApplication,
)

from ..theme import Palette


class _TitleBarButton(QPushButton):
    """A custom title bar button (minimize / maximize / close) with glow."""

    def __init__(self, icon_char: str, color: str, hover_color: str,
                 parent=None) -> None:
        super().__init__(icon_char, parent)
        self._color = color
        self._hover_color = hover_color
        self._hovered = False
        self.setFixedSize(46, 32)
        self.setCursor(Qt.PointingHandCursor)
        self._apply_style()

    def _apply_style(self) -> None:
        if self._hovered:
            bg = f"rgba(255, 255, 255, 0.08)"
        else:
            bg = "transparent"
        self.setStyleSheet(f"""
            QPushButton {{
                background: {bg};
                color: {self._color};
                border: none;
                font-size: 16px;
                font-weight: bold;
                border-radius: 0px;
            }}
            QPushButton:hover {{
                color: {self._hover_color};
                background: rgba(255, 255, 255, 0.12);
            }}
        """)

    def enterEvent(self, event) -> None:
        self._hovered = True
        self._apply_style()
        super().enterEvent(event)

    def leaveEvent(self, event) -> None:
        self._hovered = False
        self._apply_style()
        super().leaveEvent(event)


class GlassTitleBar(QWidget):
    """
    Custom glassmorphic title bar for frameless windows.

    Signals:
        minimize_clicked()
        maximize_clicked()
        close_clicked()
    """

    minimize_clicked = Signal()
    maximize_clicked = Signal()
    close_clicked = Signal()

    TITLE_BAR_HEIGHT = 40

    def __init__(self, title: str = "RASK!", icon: Optional[QPixmap] = None,
                 parent=None) -> None:
        super().__init__(parent)
        self.setFixedHeight(self.TITLE_BAR_HEIGHT)
        self._drag_pos = None
        self._title = title

        layout = QHBoxLayout(self)
        layout.setContentsMargins(12, 0, 0, 0)
        layout.setSpacing(8)

        # App icon
        if icon:
            icon_label = QLabel()
            icon_label.setPixmap(icon.scaled(20, 20, Qt.KeepAspectRatio, Qt.SmoothTransformation))
            icon_label.setStyleSheet("background: transparent;")
            layout.addWidget(icon_label)

        # App name
        self._title_label = QLabel(title)
        self._title_label.setFont(QFont("Segoe UI", 11, QFont.Bold))
        self._title_label.setStyleSheet(f"""
            color: {Palette.GOLD_BRIGHT};
            background: transparent;
            letter-spacing: 2px;
        """)
        layout.addWidget(self._title_label)

        layout.addStretch()

        # Window control buttons
        self._min_btn = _TitleBarButton("─", Palette.TEXT_SECONDARY, Palette.GOLD_BRIGHT)
        self._min_btn.clicked.connect(self.minimize_clicked.emit)
        layout.addWidget(self._min_btn)

        self._max_btn = _TitleBarButton("□", Palette.TEXT_SECONDARY, Palette.GOLD_BRIGHT)
        self._max_btn.clicked.connect(self.maximize_clicked.emit)
        layout.addWidget(self._max_btn)

        self._close_btn = _TitleBarButton("✕", "#A06060", "#FF4444")
        self._close_btn.clicked.connect(self.close_clicked.emit)
        layout.addWidget(self._close_btn)

    def set_title(self, title: str) -> None:
        self._title = title
        self._title_label.setText(title)

    # ── Drag to move ──

    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.LeftButton:
            self._drag_pos = event.globalPosition().toPoint() - self.window().frameGeometry().topLeft()
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event) -> None:
        if self._drag_pos and event.buttons() & Qt.LeftButton:
            self.window().move(event.globalPosition().toPoint() - self._drag_pos)
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event) -> None:
        self._drag_pos = None
        super().mouseReleaseEvent(event)

    def mouseDoubleClickEvent(self, event) -> None:
        if event.button() == Qt.LeftButton:
            self.maximize_clicked.emit()

    # ── Paint the glass effect ──

    def paintEvent(self, event) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing, True)
        try:
            # Glass background — semi-transparent dark with subtle gradient
            grad = QLinearGradient(0, 0, 0, self.height())
            grad.setColorAt(0, QColor(17, 17, 20, 230))  # slightly lighter at top
            grad.setColorAt(1, QColor(10, 10, 11, 240))   # darker at bottom
            p.fillRect(self.rect(), QBrush(grad))

            # Gold accent line at the very top — 2px glowing
            accent_grad = QLinearGradient(0, 0, self.width(), 0)
            accent_grad.setColorAt(0.0, QColor(212, 175, 55, 0))
            accent_grad.setColorAt(0.2, QColor(212, 175, 55, 180))
            accent_grad.setColorAt(0.5, QColor(245, 200, 66, 220))
            accent_grad.setColorAt(0.8, QColor(212, 175, 55, 180))
            accent_grad.setColorAt(1.0, QColor(212, 175, 55, 0))
            p.fillRect(0, 0, self.width(), 2, QBrush(accent_grad))

            # Subtle bottom border
            p.setPen(QPen(QColor(42, 42, 51, 100), 1))
            p.drawLine(0, self.height() - 1, self.width(), self.height() - 1)
        finally:
            p.end()


class FramelessWindowMixin:
    """
    Mixin to make any QMainWindow frameless with a GlassTitleBar.

    Usage:
        class MyWindow(QMainWindow, FramelessWindowMixin):
            def __init__(self):
                super().__init__()
                self._init_frameless(title="RASK!", icon=my_pixmap)
                # ... build your UI ...

    Provides:
        - Custom glass title bar
        - Window resize from edges
        - Min / Max / Close functionality
        - Particle background (optional)
    """

    def _init_frameless(self, title: str = "RASK!",
                        icon: Optional[QPixmap] = None) -> None:
        """Call this in __init__ after super().__init__()."""
        from PySide6.QtCore import Qt

        self.setWindowFlags(
            Qt.FramelessWindowHint |
            Qt.WindowSystemMenuHint
        )
        self.setAttribute(Qt.WA_TranslucentBackground, False)

        # Title bar
        self._title_bar = GlassTitleBar(title, icon, self)
        self._title_bar.minimize_clicked.connect(self.showMinimized)
        self._title_bar.maximize_clicked.connect(self._toggle_maximize)
        self._title_bar.close_clicked.connect(self.close)

        # Resize handles
        self._resize_margin = 6
        self._resizing = False
        self._resize_dir = None
        self._resize_start_geo = None
        self._resize_start_pos = None

    def _toggle_maximize(self) -> None:
        if self.isMaximized():
            self.showNormal()
        else:
            self.showMaximized()

    def toggle_fullscreen(self) -> None:
        """Toggle between fullscreen and normal mode."""
        if self.isFullScreen():
            self.showNormal()
        else:
            self.showFullScreen()

    def _add_titlebar_to_layout(self, layout: QVBoxLayout) -> None:
        """Insert the title bar at the top of a VBoxLayout."""
        layout.insertWidget(0, self._title_bar)

    # ── Resize from edges ──

    def _edge_at(self, pos) -> str:
        """Return which edge(s) the cursor is near."""
        m = self._resize_margin
        w, h = self.width(), self.height()
        x, y = pos.x(), pos.y()

        edges = ""
        if y < m:
            edges += "t"
        if y > h - m:
            edges += "b"
        if x < m:
            edges += "l"
        if x > w - m:
            edges += "r"
        return edges

    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.LeftButton:
            edge = self._edge_at(event.position().toPoint())
            if edge:
                self._resizing = True
                self._resize_dir = edge
                self._resize_start_geo = self.geometry()
                self._resize_start_pos = event.globalPosition().toPoint()
                event.accept()
                return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event) -> None:
        if self._resizing and self._resize_dir:
            delta = event.globalPosition().toPoint() - self._resize_start_pos
            geo = self._resize_start_geo

            dx, dy = 0, 0
            dw, dh = 0, 0

            if 't' in self._resize_dir:
                dy = delta.y()
                dh = -delta.y()
            if 'b' in self._resize_dir:
                dh = delta.y()
            if 'l' in self._resize_dir:
                dx = delta.x()
                dw = -delta.x()
            if 'r' in self._resize_dir:
                dw = delta.x()

            new_geo = geo.adjusted(dx, dy, dx + dw, dy + dh)
            if new_geo.width() >= self.minimumWidth() and new_geo.height() >= self.minimumHeight():
                self.setGeometry(new_geo)
            event.accept()
            return

        # Update cursor for edge detection
        if not self.isMaximized():
            edge = self._edge_at(event.position().toPoint())
            cursors = {
                't': Qt.SizeVerCursor, 'b': Qt.SizeVerCursor,
                'l': Qt.SizeHorCursor, 'r': Qt.SizeHorCursor,
                'tl': Qt.SizeFDiagCursor, 'br': Qt.SizeFDiagCursor,
                'tr': Qt.SizeBDiagCursor, 'bl': Qt.SizeBDiagCursor,
            }
            if edge in cursors:
                self.setCursor(cursors[edge])
            else:
                self.setCursor(Qt.ArrowCursor)
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event) -> None:
        self._resizing = False
        self._resize_dir = None
        super().mouseReleaseEvent(event)
