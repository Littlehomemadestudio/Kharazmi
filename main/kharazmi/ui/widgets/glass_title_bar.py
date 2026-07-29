# نوار عنوان شیشه‌ای — نوار عنوان سفارشی با افکت شیشه‌ای و دکمه‌های کنترل
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

    # ساخت دکمه نوار عنوان با آیکون و رنگ
    def __init__(self, icon_char: str, color: str, hover_color: str,
                 parent=None) -> None:
        super().__init__(icon_char, parent)
        self._color = color
        self._hover_color = hover_color
        self._hovered = False
        self.setFixedSize(46, 32)
        self.setCursor(Qt.PointingHandCursor)
        self._apply_style()

    # اعمال سبک بصری دکمه بر اساس حالت هاور
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

    # مدیریت ورود ماوس به دکمه
    def enterEvent(self, event) -> None:
        self._hovered = True
        self._apply_style()
        super().enterEvent(event)

    # مدیریت خروج ماوس از دکمه
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
    theme_toggle_clicked = Signal()

    TITLE_BAR_HEIGHT = 40

    # ساخت نوار عنوان شیشه‌ای با آیکون و دکمه‌ها
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

        # Theme toggle button
        self._theme_btn = _TitleBarButton("◐", Palette.TEXT_SECONDARY, Palette.GOLD_BRIGHT)
        self._theme_btn.setToolTip("تغییر تم روشن/تیره")
        self._theme_btn.clicked.connect(self.theme_toggle_clicked.emit)
        layout.addWidget(self._theme_btn)

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

    # تنظیم عنوان نوار عنوان
    def set_title(self, title: str) -> None:
        self._title = title
        self._title_label.setText(title)

    # بازسازی سبک‌های درخطی برای تم فعلی
    def _reapply_theme(self) -> None:
        """Update inline styles for the current theme."""
        self._title_label.setStyleSheet(f"""
            color: {Palette.GOLD_BRIGHT};
            background: transparent;
            letter-spacing: 2px;
        """)
        self._theme_btn._color = Palette.TEXT_SECONDARY
        self._theme_btn._hover_color = Palette.GOLD_BRIGHT
        self._theme_btn._apply_style()
        self._min_btn._color = Palette.TEXT_SECONDARY
        self._min_btn._hover_color = Palette.GOLD_BRIGHT
        self._min_btn._apply_style()
        self._max_btn._color = Palette.TEXT_SECONDARY
        self._max_btn._hover_color = Palette.GOLD_BRIGHT
        self._max_btn._apply_style()
        self.update()

    # ── Drag to move ──

    # مدیریت فشردن ماوس برای شروع کشیدن
    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.LeftButton:
            self._drag_pos = event.globalPosition().toPoint() - self.window().frameGeometry().topLeft()
        super().mousePressEvent(event)

    # مدیریت حرکت ماوس برای جابجایی پنجره
    def mouseMoveEvent(self, event) -> None:
        if self._drag_pos and event.buttons() & Qt.LeftButton:
            self.window().move(event.globalPosition().toPoint() - self._drag_pos)
        super().mouseMoveEvent(event)

    # مدیریت رها کردن ماوس
    def mouseReleaseEvent(self, event) -> None:
        self._drag_pos = None
        super().mouseReleaseEvent(event)

    # مدیریت دابل‌کلیک برای بیشینه‌سازی
    def mouseDoubleClickEvent(self, event) -> None:
        if event.button() == Qt.LeftButton:
            self.maximize_clicked.emit()

    # ── Paint the glass effect ──

    # رسم افکت شیشه‌ای و خط طلایی
    def paintEvent(self, event) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing, True)
        try:
            # Glass background — theme-aware gradient
            bg = QColor(Palette.BG_SECONDARY)
            bg_top = QColor(bg.red(), bg.green(), bg.blue(), 230)
            bg_bot = QColor(Palette.BG_DEEPEST)
            bg_bot.setAlpha(240)
            grad = QLinearGradient(0, 0, 0, self.height())
            grad.setColorAt(0, bg_top)
            grad.setColorAt(1, bg_bot)
            p.fillRect(self.rect(), QBrush(grad))

            # Gold accent line at the very top — 2px glowing
            gold = QColor(Palette.GOLD_PRIMARY)
            gold_bright = QColor(Palette.GOLD_BRIGHT)
            accent_grad = QLinearGradient(0, 0, self.width(), 0)
            accent_grad.setColorAt(0.0, QColor(gold.red(), gold.green(), gold.blue(), 0))
            accent_grad.setColorAt(0.2, QColor(gold.red(), gold.green(), gold.blue(), 180))
            accent_grad.setColorAt(0.5, QColor(gold_bright.red(), gold_bright.green(), gold_bright.blue(), 220))
            accent_grad.setColorAt(0.8, QColor(gold.red(), gold.green(), gold.blue(), 180))
            accent_grad.setColorAt(1.0, QColor(gold.red(), gold.green(), gold.blue(), 0))
            p.fillRect(0, 0, self.width(), 2, QBrush(accent_grad))

            # Subtle bottom border
            border = QColor(Palette.BORDER_NORMAL)
            border.setAlpha(100)
            p.setPen(QPen(border, 1))
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

    # مقداردهی اولیه پنجره بدون قاب با نوار عنوان شیشه‌ای
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
        self._title_bar.theme_toggle_clicked.connect(self._on_title_bar_theme_toggle)

        # Resize handles
        self._resize_margin = 6
        self._resizing = False
        self._resize_dir = None
        self._resize_start_geo = None
        self._resize_start_pos = None

    # تغییر حالت بین بیشینه و عادی
    def _toggle_maximize(self) -> None:
        if self.isMaximized():
            self.showNormal()
        else:
            self.showMaximized()

    # مدیریت تغییر تم از دکمه نوار عنوان
    def _on_title_bar_theme_toggle(self) -> None:
        from ..theme import current_mode, set_theme, QSS, build_qpalette
        new_mode = "dark" if current_mode() == "light" else "light"
        set_theme(new_mode)
        app = QApplication.instance()
        if app:
            app.setStyleSheet(QSS)
            app.setPalette(build_qpalette())
        if hasattr(self, '_reapply_theme') and callable(self._reapply_theme):
            self._reapply_theme()

    # تغییر حالت تمام‌صفحه
    def toggle_fullscreen(self) -> None:
        if self.isFullScreen():
            self.showNormal()
            # Show the title bar when exiting fullscreen
            if hasattr(self, '_title_bar') and self._title_bar:
                self._title_bar.show()
        else:
            # Hide the title bar when entering fullscreen
            if hasattr(self, '_title_bar') and self._title_bar:
                self._title_bar.hide()
            self.showFullScreen()

    # مدیریت فشردن کلید Escape برای خروج از تمام‌صفحه
    def keyPressEvent(self, event) -> None:
        from PySide6.QtCore import Qt
        if event.key() == Qt.Key_Escape and self.isFullScreen():
            self.toggle_fullscreen()
            event.accept()
            return
        super().keyPressEvent(event)

    # افزودن نوار عنوان به بالای لایه‌بندی
    def _add_titlebar_to_layout(self, layout: QVBoxLayout) -> None:
        layout.insertWidget(0, self._title_bar)

    # ── Resize from edges ──

    # تشخیص لبه نزدیک به مکان‌نما برای تغییر اندازه
    def _edge_at(self, pos) -> str:
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

    # مدیریت فشردن ماوس برای شروع تغییر اندازه
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

    # مدیریت حرکت ماوس برای تغییر اندازه پنجره
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

    # مدیریت رها کردن ماوس برای پایان تغییر اندازه
    def mouseReleaseEvent(self, event) -> None:
        self._resizing = False
        self._resize_dir = None
        super().mouseReleaseEvent(event)
