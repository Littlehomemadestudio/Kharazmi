"""
DashboardView — Revamped premium home/dashboard view for RASK!

A stunning, fully Persian dashboard that serves as the app's landing experience:
  - Hero section: Shamsi date in centered Persian typography with animated glow
  - Stat cards in 2x2 grid with Persian labels and left-border color accents
  - Quick action buttons in Persian
  - Upcoming events list with colored indicators
  - Productivity section with thicker progress rings and Persian labels
  - Gold particle background

All rendered with QPainter for maximum visual control.
"""
from __future__ import annotations

import math
from datetime import datetime, timedelta
from typing import Optional

from PySide6.QtCore import Qt, QTimer, QRect, QRectF, QPointF, Signal
from PySide6.QtGui import (
    QPainter, QColor, QPen, QBrush, QFont,
    QPainterPath, QLinearGradient, QRadialGradient, QFontMetrics,
)
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QFrame, QSizePolicy, QScrollArea, QGridLayout,
)

from ...core.shamsi import ShamsiDate, format_shamsi, to_persian_digits, SHAMSI_MONTHS_FA
from ...calendar import CalendarStore
from ...ai import JournalStore
from ...core import Project
from ..theme import Palette
from ..widgets.particle_background import GoldParticleBackground


# ──────────────────────────── Helper ────────────────────────────

def _greeting_fa() -> str:
    """Return a Persian greeting based on the current hour."""
    hour = datetime.now().hour
    if 5 <= hour < 12:
        return "صبح بخیر"
    elif 12 <= hour < 17:
        return "ظهر بخیر"
    elif 17 <= hour < 21:
        return "عصر بخیر"
    else:
        return "شب بخیر"


# ──────────────────────────── Hero Widget ────────────────────────────

class _HeroWidget(QWidget):
    """Custom-painted hero section with centered Shamsi date, greeting, and glow."""

    def __init__(self, today: ShamsiDate, parent=None) -> None:
        super().__init__(parent)
        self._today = today
        self.setFixedHeight(220)
        self._tick = 0
        self._timer = QTimer(self)
        self._timer.setInterval(50)
        self._timer.timeout.connect(self._on_tick)
        self._timer.start()

    def _on_tick(self) -> None:
        self._tick += 1
        self.update()

    def paintEvent(self, event) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing, True)

        w, h = self.width(), self.height()

        # ── Animated glow behind the date ──
        pulse = 0.5 + 0.5 * math.sin(self._tick * 0.04)
        glow_alpha = int(18 + 12 * pulse)
        glow_r = 140 + 20 * pulse
        glow_grad = QRadialGradient(QPointF(w / 2, h / 2 - 10), glow_r)
        glow_grad.setColorAt(0, QColor(212, 175, 55, glow_alpha))
        glow_grad.setColorAt(0.6, QColor(212, 175, 55, glow_alpha // 3))
        glow_grad.setColorAt(1, QColor(212, 175, 55, 0))
        p.setPen(Qt.NoPen)
        p.setBrush(QBrush(glow_grad))
        p.drawEllipse(QPointF(w / 2, h / 2 - 10), glow_r, glow_r)

        # ── "امروز" badge ──
        badge_text = "امروز"
        badge_font = QFont("Segoe UI", 10)
        p.setFont(badge_font)
        fm = QFontMetrics(badge_font)
        badge_w = fm.horizontalAdvance(badge_text) + 20
        badge_h = 24
        badge_x = (w - badge_w) / 2
        badge_y = 14

        badge_path = QPainterPath()
        badge_path.addRoundedRect(QRectF(badge_x, badge_y, badge_w, badge_h), 12, 12)
        p.setPen(Qt.NoPen)
        badge_fill = QColor(Palette.GOLD_PRIMARY)
        badge_fill.setAlpha(35)
        p.setBrush(QBrush(badge_fill))
        p.drawPath(badge_path)

        badge_border = QColor(Palette.GOLD_PRIMARY)
        badge_border.setAlpha(80)
        p.setPen(QPen(badge_border, 1))
        p.setBrush(Qt.NoBrush)
        p.drawPath(badge_path)

        p.setPen(QPen(QColor(Palette.GOLD_BRIGHT)))
        p.drawText(QRectF(badge_x, badge_y, badge_w, badge_h),
                   Qt.AlignCenter, badge_text)

        # ── Date display ──
        day_text = to_persian_digits(str(self._today.day))
        month_text = SHAMSI_MONTHS_FA[self._today.month - 1]
        year_text = to_persian_digits(str(self._today.year))
        weekday_text = self._today.weekday_fa

        # Big centered day number with gold gradient
        day_font = QFont("Segoe UI", 80, QFont.Bold)
        p.setFont(day_font)

        day_grad = QLinearGradient(0, 40, 0, 140)
        day_grad.setColorAt(0, QColor(245, 200, 66))
        day_grad.setColorAt(0.5, QColor(212, 175, 55))
        day_grad.setColorAt(1, QColor(140, 112, 18))
        p.setPen(QPen(QBrush(day_grad), 1))
        p.drawText(QRectF(0, 38, w, 100), Qt.AlignHCenter | Qt.AlignTop, day_text)

        # Month name centered below day
        month_font = QFont("Segoe UI", 28, QFont.Bold)
        p.setFont(month_font)
        p.setPen(QPen(QColor(Palette.GOLD_BRIGHT)))
        p.drawText(QRectF(0, 130, w, 40), Qt.AlignHCenter, month_text)

        # Year + Weekday on one line
        year_week_font = QFont("Segoe UI", 13)
        p.setFont(year_week_font)
        year_weekday = f"{year_text}  ·  {weekday_text}"
        p.setPen(QPen(QColor(Palette.TEXT_SECONDARY)))
        p.drawText(QRectF(0, 170, w, 24), Qt.AlignHCenter, year_weekday)

        # ── Greeting ──
        greeting = _greeting_fa()
        greet_font = QFont("Segoe UI", 12)
        p.setFont(greet_font)
        p.setPen(QPen(QColor(Palette.TEXT_TERTIARY)))
        p.drawText(QRectF(0, 194, w, 20), Qt.AlignHCenter, greeting)

        # ── Subtle divider ──
        div_grad = QLinearGradient(0, 0, w, 0)
        div_grad.setColorAt(0, QColor(212, 175, 55, 0))
        div_grad.setColorAt(0.2, QColor(212, 175, 55, 50))
        div_grad.setColorAt(0.5, QColor(212, 175, 55, 70))
        div_grad.setColorAt(0.8, QColor(212, 175, 55, 50))
        div_grad.setColorAt(1, QColor(212, 175, 55, 0))
        p.setPen(Qt.NoPen)
        p.setBrush(QBrush(div_grad))
        p.drawRect(QRectF(0, h - 1, w, 1))

        p.end()


# ──────────────────────────── Stat Card ────────────────────────────

class _StatCard(QWidget):
    """A stat card with left-border accent, QPainter-drawn icon, and Persian label."""

    def __init__(self, target: int, label: str, icon_type: str, color: str,
                 parent=None) -> None:
        super().__init__(parent)
        self._target = target
        self._current = 0
        self._label = label
        self._icon_type = icon_type  # "calendar", "checkmark", "star", "book"
        self._color = color
        self.setFixedSize(200, 120)
        self._anim_timer = QTimer(self)
        self._anim_timer.setInterval(30)
        self._anim_timer.timeout.connect(self._tick)
        self._anim_timer.start()

    def _tick(self) -> None:
        if self._current < self._target:
            step = max(1, (self._target - self._current) // 8)
            self._current = min(self._current + step, self._target)
            self.update()
        else:
            self._anim_timer.stop()

    def paintEvent(self, event) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing, True)

        r = 12
        # Card background
        card_path = QPainterPath()
        card_path.addRoundedRect(QRectF(0.5, 0.5, self.width() - 1, self.height() - 1), r, r)
        p.setPen(QPen(QColor(Palette.BORDER_NORMAL), 1))
        p.setBrush(QBrush(QColor(Palette.BG_TERTIARY)))
        p.drawPath(card_path)

        # Left color accent border
        accent_path = QPainterPath()
        accent_path.addRoundedRect(QRectF(0, 0, 4, self.height()), r, r)
        accent_fill = QColor(self._color)
        accent_fill.setAlpha(220)
        p.setPen(Qt.NoPen)
        p.setBrush(QBrush(accent_fill))
        p.drawPath(accent_path)

        # ── Draw icon ──
        icon_x, icon_y = 170, 18
        p.setPen(Qt.NoPen)
        p.setBrush(QBrush(QColor(self._color).lighter(130)))

        if self._icon_type == "calendar":
            # Calendar: rectangle with small squares
            cal_x, cal_y = icon_x - 10, icon_y - 4
            p.drawRoundedRect(QRectF(cal_x, cal_y, 20, 18), 3, 3)
            # Top bar
            p.setBrush(QBrush(QColor(self._color)))
            p.drawRoundedRect(QRectF(cal_x, cal_y, 20, 6), 3, 3)
            # Grid dots
            p.setBrush(QBrush(QColor(Palette.TEXT_TERTIARY)))
            for row in range(2):
                for col in range(3):
                    p.drawEllipse(QPointF(cal_x + 4 + col * 6, cal_y + 10 + row * 5), 1.2, 1.2)

        elif self._icon_type == "checkmark":
            # Checkmark in circle
            p.drawEllipse(QPointF(icon_x, icon_y + 5), 12, 12)
            p.setPen(QPen(QColor("#FFFFFF"), 2.5, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
            p.setBrush(Qt.NoBrush)
            check_path = QPainterPath()
            check_path.moveTo(icon_x - 5, icon_y + 5)
            check_path.lineTo(icon_x - 1, icon_y + 9)
            check_path.lineTo(icon_x + 6, icon_y + 1)
            p.drawPath(check_path)

        elif self._icon_type == "star":
            # 5-point star
            p.setBrush(QBrush(QColor(self._color).lighter(120)))
            p.setPen(Qt.NoPen)
            star_path = QPainterPath()
            cx_s, cy_s, outer_r, inner_r = icon_x, icon_y + 5, 12, 5
            for i in range(5):
                angle_outer = math.radians(-90 + i * 72)
                angle_inner = math.radians(-90 + i * 72 + 36)
                ox = cx_s + outer_r * math.cos(angle_outer)
                oy = cy_s + outer_r * math.sin(angle_outer)
                ix = cx_s + inner_r * math.cos(angle_inner)
                iy = cy_s + inner_r * math.sin(angle_inner)
                if i == 0:
                    star_path.moveTo(ox, oy)
                else:
                    star_path.lineTo(ox, oy)
                star_path.lineTo(ix, iy)
            star_path.closeSubpath()
            p.drawPath(star_path)

        elif self._icon_type == "book":
            # Open book shape
            p.setPen(QPen(QColor(self._color).lighter(130), 2))
            p.setBrush(Qt.NoBrush)
            # Left page
            p.drawLine(QPointF(icon_x - 10, icon_y + 2), QPointF(icon_x, icon_y + 10))
            p.drawLine(QPointF(icon_x - 10, icon_y + 2), QPointF(icon_x - 10, icon_y + 18))
            p.drawLine(QPointF(icon_x - 10, icon_y + 18), QPointF(icon_x, icon_y + 10))
            # Right page
            p.drawLine(QPointF(icon_x + 10, icon_y + 2), QPointF(icon_x, icon_y + 10))
            p.drawLine(QPointF(icon_x + 10, icon_y + 2), QPointF(icon_x + 10, icon_y + 18))
            p.drawLine(QPointF(icon_x + 10, icon_y + 18), QPointF(icon_x, icon_y + 10))
            # Spine
            p.drawLine(QPointF(icon_x, icon_y), QPointF(icon_x, icon_y + 10))

        # ── Number (Persian digits) ──
        num_text = to_persian_digits(str(self._current))
        num_font = QFont("Segoe UI", 28, QFont.Bold)
        p.setFont(num_font)
        p.setPen(QPen(QColor(Palette.TEXT_PRIMARY)))
        p.drawText(QRectF(20, 20, 140, 50), Qt.AlignLeft | Qt.AlignVCenter, num_text)

        # ── Label ──
        label_font = QFont("Segoe UI", 10)
        p.setFont(label_font)
        p.setPen(QPen(QColor(Palette.TEXT_TERTIARY)))
        p.drawText(QRectF(20, 75, 160, 24), Qt.AlignLeft | Qt.AlignVCenter, self._label)

        p.end()


# ──────────────────────────── Event Row ──────────────────────────────────

class _EventRow(QWidget):
    """A single upcoming event row with color indicator and Persian layout."""

    def __init__(self, title: str, time_str: str, color: str, parent=None) -> None:
        super().__init__(parent)
        self._title = title
        self._time = time_str
        self._color = color
        self.setFixedHeight(44)

    def paintEvent(self, event) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing, True)

        w, h = self.width(), self.height()

        # Color dot
        p.setPen(Qt.NoPen)
        p.setBrush(QBrush(QColor(self._color)))
        p.drawEllipse(QPointF(w - 14, h / 2), 5, 5)

        # Title (right-aligned for RTL)
        title_font = QFont("Segoe UI", 12)
        p.setFont(title_font)
        p.setPen(QPen(QColor(Palette.TEXT_PRIMARY)))
        p.drawText(QRectF(0, 0, w - 30, h),
                    Qt.AlignRight | Qt.AlignVCenter, self._title)

        # Time (left side)
        time_font = QFont("Segoe UI", 11)
        p.setFont(time_font)
        p.setPen(QPen(QColor(Palette.TEXT_SECONDARY)))
        p.drawText(QRectF(10, 0, 120, h),
                    Qt.AlignLeft | Qt.AlignVCenter, self._time)

        # Subtle bottom line
        p.setPen(QPen(QColor(Palette.BORDER_SUBTLE), 1))
        p.drawLine(QPointF(10, h - 0.5), QPointF(w - 10, h - 0.5))

        p.end()


# ──────────────────────────── Progress Ring ──────────────────────────────

class _ProgressRing(QWidget):
    """Circular progress indicator with thicker ring and Persian label."""

    def __init__(self, value: int, maximum: int, color: str, label: str,
                 parent=None) -> None:
        super().__init__(parent)
        self._value = value
        self._max = max(maximum, 1)
        self._color = color
        self._label = label
        self.setFixedSize(90, 100)

    def paintEvent(self, event) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing, True)

        cx, cy = 45, 42
        radius = 32
        pen_w = 8

        # Background ring
        p.setPen(QPen(QColor(Palette.BORDER_NORMAL), pen_w, Qt.SolidLine, Qt.RoundCap))
        p.setBrush(Qt.NoBrush)
        p.drawEllipse(QPointF(cx, cy), radius, radius)

        # Progress arc
        frac = self._value / self._max if self._max > 0 else 0
        pct_val = int(frac * 100)
        span = int(frac * 360 * 16)
        p.setPen(QPen(QColor(self._color), pen_w, Qt.SolidLine, Qt.RoundCap))
        arc_rect = QRect(int(cx - radius), int(cy - radius),
                         int(radius * 2), int(radius * 2))
        p.drawArc(arc_rect, 90 * 16, -span)

        # Percentage text — Persian digits
        pct = to_persian_digits(str(pct_val)) + "٪"
        p.setFont(QFont("Segoe UI", 12, QFont.Bold))
        p.setPen(QPen(QColor(Palette.TEXT_PRIMARY)))
        p.drawText(QRectF(0, 18, 90, 44), Qt.AlignCenter, pct)

        # Label below
        p.setFont(QFont("Segoe UI", 9))
        p.setPen(QPen(QColor(Palette.TEXT_SECONDARY)))
        p.drawText(QRectF(0, 78, 90, 20), Qt.AlignCenter, self._label)

        p.end()


# ──────────────────────────── Section Header ────────────────────────────

class _SectionHeader(QWidget):
    """A section header with Persian title and optional badge."""

    def __init__(self, title: str, badge_text: str = "", parent=None) -> None:
        super().__init__(parent)
        self._title = title
        self._badge = badge_text
        self.setFixedHeight(36)

    def paintEvent(self, event) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing, True)

        w = self.width()

        # Title
        title_font = QFont("Segoe UI", 12, QFont.Bold)
        p.setFont(title_font)
        p.setPen(QPen(QColor(Palette.GOLD_PRIMARY)))
        title_rect = QRectF(0, 4, w - 60, 28)
        p.drawText(title_rect, Qt.AlignRight | Qt.AlignVCenter, self._title)

        # Badge
        if self._badge:
            badge_font = QFont("Segoe UI", 9, QFont.Bold)
            p.setFont(badge_font)
            fm = QFontMetrics(badge_font)
            bw = max(fm.horizontalAdvance(self._badge) + 14, 24)
            bh = 20
            bx = 0
            by = 8

            badge_path = QPainterPath()
            badge_path.addRoundedRect(QRectF(bx, by, bw, bh), 10, 10)
            p.setPen(Qt.NoPen)
            badge_fill = QColor(Palette.GOLD_PRIMARY)
            badge_fill.setAlpha(30)
            p.setBrush(QBrush(badge_fill))
            p.drawPath(badge_path)

            p.setPen(QPen(QColor(Palette.GOLD_BRIGHT)))
            p.drawText(QRectF(bx, by, bw, bh), Qt.AlignCenter, self._badge)

        # Subtle underline
        line_grad = QLinearGradient(0, 0, w, 0)
        line_grad.setColorAt(0, QColor(Palette.GOLD_PRIMARY, 0))
        line_grad.setColorAt(0.3, QColor(Palette.GOLD_PRIMARY, 40))
        line_grad.setColorAt(0.7, QColor(Palette.GOLD_PRIMARY, 40))
        line_grad.setColorAt(1, QColor(Palette.GOLD_PRIMARY, 0))
        p.setPen(Qt.NoPen)
        p.setBrush(QBrush(line_grad))
        p.drawRect(QRectF(0, 34, w, 1))

        p.end()


# ──────────────────────────── Dashboard View ──────────────────────────────

class DashboardView(QWidget):
    """
    Premium dashboard — the stunning home view of RASK!

    Serves as the default tab, showing:
      - Today's Shamsi date in heroic centered Persian typography
      - Stat cards in 2x2 grid
      - Quick action buttons in Persian
      - Upcoming events
      - Productivity section
      - Gold particle background
    """

    calendarTabRequested = Signal()
    plannerTabRequested = Signal()
    newEventRequested = Signal()

    def __init__(self, calendar_store: CalendarStore,
                 journal_store: JournalStore,
                 project: Project,
                 parent=None) -> None:
        super().__init__(parent)
        self._store = calendar_store
        self._journal = journal_store
        self._project = project
        self._today = ShamsiDate.today()

        # Build UI
        self._build_ui()

        # Refresh timer
        self._refresh_timer = QTimer(self)
        self._refresh_timer.setInterval(60000)
        self._refresh_timer.timeout.connect(self._refresh)
        self._refresh_timer.start()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # Scroll area
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        scroll.setStyleSheet(f"""
            QScrollArea {{
                background: {Palette.BG_DEEPEST};
                border: none;
            }}
            QScrollBar:vertical {{
                background: transparent;
                width: 8px;
            }}
            QScrollBar::handle:vertical {{
                background: {Palette.BORDER_STRONG};
                border-radius: 4px;
                min-height: 20px;
            }}
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
                height: 0;
            }}
        """)

        # Content widget — centered, max-width 900px
        content = QWidget()
        content.setStyleSheet(f"background: {Palette.BG_DEEPEST};")

        # Outer layout to center the inner content
        outer_layout = QHBoxLayout(content)
        outer_layout.setContentsMargins(0, 0, 0, 0)
        outer_layout.setSpacing(0)

        # Left stretch
        outer_layout.addStretch()

        # Inner content container (max 900px)
        inner = QWidget()
        inner.setMaximumWidth(900)
        inner.setStyleSheet(f"background: transparent;")
        self._content_layout = QVBoxLayout(inner)
        self._content_layout.setContentsMargins(40, 30, 40, 30)
        self._content_layout.setSpacing(32)

        outer_layout.addWidget(inner)

        # Right stretch
        outer_layout.addStretch()

        # Particle background
        self._particles = GoldParticleBackground(self, particle_count=40)

        # ── Hero Section ──
        self._build_hero()

        # ── Stat Cards (2x2 grid) ──
        self._build_stat_cards()

        # ── Quick Actions ──
        self._build_quick_actions()

        # ── Upcoming Events ──
        self._build_upcoming_events()

        # ── Productivity Section ──
        self._build_productivity()

        self._content_layout.addStretch()

        scroll.setWidget(content)
        layout.addWidget(scroll)

    def _build_hero(self) -> None:
        """Build the hero section with centered Shamsi date."""
        self._hero_widget = _HeroWidget(self._today, self)
        self._content_layout.addWidget(self._hero_widget)

    def _build_stat_cards(self) -> None:
        """Build stat cards in a 2x2 grid."""
        grid_widget = QWidget()
        grid_widget.setStyleSheet("background: transparent;")
        grid = QGridLayout(grid_widget)
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setSpacing(16)

        event_count = self._store.event_count
        task_count = self._project.task_count
        journal_count = len(self._journal)

        cards_data = [
            (event_count, "رویدادها", "calendar", Palette.GOLD_PRIMARY),
            (task_count, "وظایف", "checkmark", "#5A7FA8"),
            (0, "مسیرهای AI", "star", "#8A6AAA"),  # AI routes placeholder
            (journal_count, "یادداشت‌ها", "book", Palette.STATUS_DONE),
        ]

        for idx, (target, label, icon_type, color) in enumerate(cards_data):
            card = _StatCard(target, label, icon_type, color, grid_widget)
            row, col = divmod(idx, 2)
            # Right-align for RTL: col 0 = right, col 1 = left
            if col == 0:
                grid.addWidget(card, row, 1)  # right side
            else:
                grid.addWidget(card, row, 0)  # left side

        grid.setColumnStretch(0, 1)
        grid.setColumnStretch(1, 1)

        self._content_layout.addWidget(grid_widget)

    def _build_quick_actions(self) -> None:
        """Build quick action buttons in Persian."""
        row = QWidget()
        row.setStyleSheet("background: transparent;")
        row_layout = QHBoxLayout(row)
        row_layout.setContentsMargins(0, 0, 0, 0)
        row_layout.setSpacing(12)

        actions = [
            ("رویداد جدید", self.newEventRequested.emit, Palette.GOLD_PRIMARY),
            ("برنامه‌ریز هوشمند", self.plannerTabRequested.emit, "#8A6AAA"),
            ("تقویم", self.calendarTabRequested.emit, "#5A7FA8"),
        ]

        for label, callback, color in actions:
            btn = QPushButton(label)
            btn.setFont(QFont("Segoe UI", 12, QFont.Bold))
            btn.setCursor(Qt.PointingHandCursor)
            btn.setFixedHeight(48)
            btn.setMinimumWidth(140)
            btn.setStyleSheet(f"""
                QPushButton {{
                    background: {Palette.BG_TERTIARY};
                    color: {Palette.TEXT_PRIMARY};
                    border: 1px solid {Palette.BORDER_NORMAL};
                    border-right: 3px solid {color};
                    border-radius: 10px;
                    padding: 10px 24px;
                    text-align: center;
                }}
                QPushButton:hover {{
                    background: {Palette.BG_ELEVATED};
                    border-color: {color};
                    color: {Palette.GOLD_BRIGHT};
                }}
                QPushButton:pressed {{
                    background: {Palette.BG_HOVER};
                }}
            """)
            btn.clicked.connect(callback)
            row_layout.addWidget(btn, stretch=1)

        self._content_layout.addWidget(row)

    def _build_upcoming_events(self) -> None:
        """Build upcoming events section with Persian header."""
        # Get upcoming events
        events = self._store.upcoming_events(7) if hasattr(self._store, 'upcoming_events') else []
        event_count = len(events)

        badge = to_persian_digits(str(event_count)) if event_count else ""
        header = _SectionHeader("رویدادهای آینده", badge, self)
        self._content_layout.addWidget(header)

        # Card container
        card = QWidget()
        card.setStyleSheet(
            f"background: {Palette.BG_TERTIARY};"
            f" border: 1px solid {Palette.BORDER_NORMAL};"
            f" border-radius: 12px;"
        )
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(20, 16, 20, 16)
        card_layout.setSpacing(0)

        if events:
            for evt in events[:5]:
                time_str = format_shamsi(evt.start, include_time=True) if hasattr(evt, 'start') and evt.start else ""
                color = evt.color if hasattr(evt, 'color') and evt.color else Palette.GOLD_PRIMARY
                row = _EventRow(evt.title, time_str, color, card)
                card_layout.addWidget(row)
        else:
            # Empty state
            empty = QLabel("هیچ رویدادی در هفته آینده ندارید")
            empty.setFont(QFont("Segoe UI", 11))
            empty.setAlignment(Qt.AlignCenter)
            empty.setStyleSheet(
                f"color: {Palette.TEXT_TERTIARY}; background: transparent; padding: 16px 0;"
            )
            card_layout.addWidget(empty)

        self._content_layout.addWidget(card)

    def _build_productivity(self) -> None:
        """Build productivity insights section with progress rings."""
        header = _SectionHeader("بهره‌وری", "", self)
        self._content_layout.addWidget(header)

        # Card container
        card = QWidget()
        card.setStyleSheet(
            f"background: {Palette.BG_TERTIARY};"
            f" border: 1px solid {Palette.BORDER_NORMAL};"
            f" border-radius: 12px;"
        )
        card_layout = QHBoxLayout(card)
        card_layout.setContentsMargins(24, 20, 24, 20)
        card_layout.setSpacing(32)

        # Compute done task count
        task_count = self._project.task_count
        done_count = (sum(1 for t in self._project.tasks()
                         if t.status.value == "done")
                     if task_count > 0 else 0)

        # Progress rings with Persian labels
        rings_data = [
            (done_count, task_count, Palette.GOLD_PRIMARY, "وظایف"),
            (len(self._journal), max(len(self._journal), 1), "#8A6AAA", "یادداشت‌ها"),
        ]
        for val, mx, color, label in rings_data:
            ring = _ProgressRing(val, mx, color, label, card)
            card_layout.addWidget(ring)

        # Tip text
        tip_container = QWidget()
        tip_container.setStyleSheet("background: transparent;")
        tip_layout = QVBoxLayout(tip_container)
        tip_layout.setContentsMargins(0, 0, 0, 0)
        tip_layout.setSpacing(6)

        tip_title = QLabel("نکته روز")
        tip_title.setFont(QFont("Segoe UI", 12, QFont.Bold))
        tip_title.setStyleSheet(
            f"color: {Palette.GOLD_BRIGHT}; background: transparent;"
        )
        tip_title.setAlignment(Qt.AlignRight)
        tip_layout.addWidget(tip_title)

        tip_text = QLabel(
            "برنامه‌ریزی روزانه خود را با هوش مصنوعی در ۳۰ ثانیه انجام دهید "
            "— اهداف را به گام‌های عملی تقسیم کنید."
        )
        tip_text.setFont(QFont("Segoe UI", 11))
        tip_text.setWordWrap(True)
        tip_text.setAlignment(Qt.AlignRight)
        tip_text.setStyleSheet(
            f"color: {Palette.TEXT_SECONDARY}; background: transparent;"
        )
        tip_layout.addWidget(tip_text)

        card_layout.addWidget(tip_container, stretch=1)

        self._content_layout.addWidget(card)

    def _refresh(self) -> None:
        self._today = ShamsiDate.today()
        self.update()

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self._particles.setGeometry(self.rect())
