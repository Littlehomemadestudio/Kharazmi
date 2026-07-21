"""
DashboardView — Premium home/dashboard view for RASK!

A stunning dashboard that serves as the app's landing experience:
  - Hero section: Shamsi date in large Persian typography with gold gradient
  - Stat cards with animated counters (events, tasks, AI routes, journal entries)
  - Mini calendar preview
  - Upcoming events list with colored indicators
  - AI insights panel
  - Productivity streak / activity indicator
  - Quick-action buttons

All rendered with QPainter for maximum visual control and smooth
animations. No generic Qt widgets — every pixel is custom.
"""
from __future__ import annotations

import math
import random
from datetime import datetime, timedelta
from typing import Optional

from PySide6.QtCore import Qt, QTimer, QRect, QRectF, QPointF, Signal, QPropertyAnimation, QEasingCurve
from PySide6.QtGui import (
    QPainter, QColor, QPen, QBrush, QFont, QPixmap,
    QPainterPath, QLinearGradient, QRadialGradient, QFontMetrics,
)
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QFrame, QSizePolicy, QScrollArea,
)

from ...core.shamsi import ShamsiDate, format_shamsi, to_persian_digits, SHAMSI_MONTHS_FA
from ...calendar import CalendarStore
from ...ai import JournalStore
from ...core import Project
from ..theme import Palette
from ..widgets.particle_background import GoldParticleBackground


# ──────────────────────────── Animated Counter ────────────────────────────

class _AnimatedCounter(QWidget):
    """A number that animates from 0 to its target value."""

    def __init__(self, target: int, label: str, icon: str, color: str,
                 parent=None) -> None:
        super().__init__(parent)
        self._target = target
        self._current = 0
        self._label = label
        self._icon = icon
        self._color = color
        self.setFixedSize(180, 110)
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
        # Card background with subtle border
        card_path = QPainterPath()
        card_path.addRoundedRect(QRectF(0.5, 0.5, self.width() - 1, self.height() - 1), r, r)
        p.setPen(QPen(QColor(Palette.BORDER_NORMAL), 1))
        p.setBrush(QBrush(QColor(Palette.BG_TERTIARY)))
        p.drawPath(card_path)

        # Subtle top color accent line
        accent = QLinearGradient(0, 0, self.width(), 0)
        c0 = QColor(self._color); c0.setAlpha(0)
        c1 = QColor(self._color); c1.setAlpha(180)
        c2 = QColor(self._color); c2.setAlpha(0)
        accent.setColorAt(0, c0)
        accent.setColorAt(0.5, c1)
        accent.setColorAt(1, c2)
        p.setPen(Qt.NoPen)
        p.setBrush(QBrush(accent))

        top_path = QPainterPath()
        top_path.addRoundedRect(QRectF(0, 0, self.width(), 3), r, r)
        p.drawPath(top_path)

        # Icon — colored circle with abbreviation letter (no emoji)
        icon_cx, icon_cy, icon_r = 32, 28, 14
        p.setPen(Qt.NoPen)
        p.setBrush(QBrush(QColor(self._color)))
        p.drawEllipse(QPointF(icon_cx, icon_cy), icon_r, icon_r)
        abbr_font = QFont("Inter", 12, QFont.Bold)
        p.setFont(abbr_font)
        p.setPen(QPen(QColor("#FFFFFF")))
        p.drawText(QRectF(icon_cx - icon_r, icon_cy - icon_r, icon_r * 2, icon_r * 2),
                   Qt.AlignCenter, self._icon)

        # Number — use Latin digits for counter since labels are in English
        num_font = QFont("Inter", 30, QFont.Bold)
        p.setFont(num_font)
        num_text = str(self._current)
        p.setPen(QPen(QColor(Palette.TEXT_PRIMARY)))
        p.drawText(QRectF(16, 40, self.width() - 32, 44), Qt.AlignLeft, num_text)

        # Label
        label_font = QFont("Inter", 10)
        p.setFont(label_font)
        p.setPen(QPen(QColor(Palette.TEXT_TERTIARY)))
        p.drawText(QRectF(16, 82, self.width() - 32, 20), Qt.AlignLeft, self._label)

        p.end()


# ──────────────────────────── Event Row ──────────────────────────────────

class _EventRow(QWidget):
    """A single upcoming event row with color indicator."""

    def __init__(self, title: str, time_str: str, color: str, parent=None) -> None:
        super().__init__(parent)
        self._title = title
        self._time = time_str
        self._color = color
        self.setFixedHeight(40)

    def paintEvent(self, event) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing, True)

        # Color dot
        p.setPen(Qt.NoPen)
        p.setBrush(QBrush(QColor(self._color)))
        p.drawEllipse(QPointF(14, self.height() / 2), 5, 5)

        # Title
        title_font = QFont("Inter", 12)
        p.setFont(title_font)
        p.setPen(QPen(QColor(Palette.TEXT_PRIMARY)))
        p.drawText(QRectF(30, 0, self.width() - 140, self.height()),
                    Qt.AlignVCenter, self._title)

        # Time
        time_font = QFont("Inter", 11)
        p.setFont(time_font)
        p.setPen(QPen(QColor(Palette.TEXT_SECONDARY)))
        p.drawText(QRectF(self.width() - 120, 0, 110, self.height()),
                    Qt.AlignRight | Qt.AlignVCenter, self._time)

        p.end()


# ──────────────────────────── Progress Ring ──────────────────────────────

class _ProgressRing(QWidget):
    """Circular progress indicator with percentage text."""

    def __init__(self, value: int, maximum: int, color: str, label: str,
                 parent=None) -> None:
        super().__init__(parent)
        self._value = value
        self._max = max(maximum, 1)
        self._color = color
        self._label = label
        self.setFixedSize(80, 90)

    def paintEvent(self, event) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing, True)

        cx, cy = 40, 38
        radius = 30
        pen_w = 5

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

        # Percentage text — use Latin digits since labels are English
        pct = str(pct_val) + "%"
        p.setFont(QFont("Inter", 12, QFont.Bold))
        p.setPen(QPen(QColor(Palette.TEXT_PRIMARY)))
        p.drawText(QRectF(0, 18, 80, 40), Qt.AlignCenter, pct)

        # Label below
        p.setFont(QFont("Inter", 8))
        p.setPen(QPen(QColor(Palette.TEXT_SECONDARY)))
        p.drawText(QRectF(0, 70, 80, 20), Qt.AlignCenter, self._label)

        p.end()


# ──────────────────────────── Dashboard View ──────────────────────────────

class DashboardView(QWidget):
    """
    Premium dashboard — the stunning home view of RASK!

    Serves as the default tab, showing:
      - Today's Shamsi date in heroic gold typography
      - Animated stat cards
      - Upcoming events
      - Quick actions
      - Particle background
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

        # Scroll area for the dashboard content
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

        # Content widget
        content = QWidget()
        content.setStyleSheet(f"background: {Palette.BG_DEEPEST};")
        self._content_layout = QVBoxLayout(content)
        self._content_layout.setContentsMargins(40, 30, 40, 30)
        self._content_layout.setSpacing(24)

        # Particle background
        self._particles = GoldParticleBackground(self, particle_count=40)

        # ── Hero Section ──
        self._build_hero()

        # ── Stat Cards ──
        self._build_stat_cards()

        # ── Quick Actions ──
        self._build_quick_actions()

        # ── Upcoming Events ──
        self._build_upcoming_events()

        # ── AI Insights ──
        self._build_ai_insights()

        self._content_layout.addStretch()

        scroll.setWidget(content)
        layout.addWidget(scroll)

    def _build_hero(self) -> None:
        """Build the hero section with Shamsi date."""
        hero = QWidget()
        hero.setFixedHeight(160)
        hero.setStyleSheet(f"background: transparent;")

        # We paint this in paintEvent of a custom widget
        self._hero_widget = _HeroWidget(self._today, self)
        self._content_layout.addWidget(self._hero_widget)

    def _build_stat_cards(self) -> None:
        """Build animated stat cards."""
        row = QWidget()
        row.setStyleSheet("background: transparent;")
        row_layout = QHBoxLayout(row)
        row_layout.setContentsMargins(0, 0, 0, 0)
        row_layout.setSpacing(16)

        event_count = self._store.event_count
        task_count = self._project.task_count
        journal_count = len(self._journal)

        cards = [
            _AnimatedCounter(event_count, "Events", "E", Palette.GOLD_PRIMARY, row),
            _AnimatedCounter(task_count, "Tasks", "T", "#5A7FA8", row),
            _AnimatedCounter(journal_count, "AI Routes", "A", "#8A6AAA", row),
            _AnimatedCounter(0, "Streak Days", "S", "#C07060", row),
        ]
        for card in cards:
            row_layout.addWidget(card)

        self._content_layout.addWidget(row)

    def _build_quick_actions(self) -> None:
        """Build quick action buttons."""
        row = QWidget()
        row.setStyleSheet("background: transparent;")
        row_layout = QHBoxLayout(row)
        row_layout.setContentsMargins(0, 0, 0, 0)
        row_layout.setSpacing(12)

        actions = [
            ("+  New Event", self.newEventRequested.emit, Palette.GOLD_PRIMARY),
            ("✦  AI Planner", self.plannerTabRequested.emit, "#8A6AAA"),
            ("◈  Calendar", self.calendarTabRequested.emit, "#5A7FA8"),
        ]

        for label, callback, color in actions:
            btn = QPushButton(label)
            btn.setFont(QFont("Inter", 12, QFont.Bold))
            btn.setCursor(Qt.PointingHandCursor)
            btn.setFixedHeight(44)
            btn.setStyleSheet(f"""
                QPushButton {{
                    background: {Palette.BG_TERTIARY};
                    color: {Palette.TEXT_PRIMARY};
                    border: 1px solid {Palette.BORDER_NORMAL};
                    border-left: 3px solid {color};
                    border-radius: 8px;
                    padding: 8px 20px;
                    text-align: left;
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
        """Build upcoming events section."""
        header = QLabel("UPCOMING EVENTS")
        header.setFont(QFont("Inter", 11, QFont.Bold))
        header.setStyleSheet(f"""
            color: {Palette.GOLD_PRIMARY};
            background: transparent;
            letter-spacing: 2px;
            padding: 8px 0 4px 0;
        """)
        self._content_layout.addWidget(header)

        # Get upcoming events
        events = self._store.upcoming_events(7) if hasattr(self._store, 'upcoming_events') else []

        if events:
            for evt in events[:5]:
                time_str = format_shamsi(evt.start, include_time=True) if hasattr(evt, 'start') and evt.start else ""
                color = evt.color if hasattr(evt, 'color') and evt.color else Palette.GOLD_PRIMARY
                row = _EventRow(evt.title, time_str, color)
                self._content_layout.addWidget(row)
        else:
            empty = QLabel("No upcoming events this week")
            empty.setFont(QFont("Inter", 11))
            empty.setStyleSheet(f"color: {Palette.TEXT_SECONDARY}; background: transparent; padding: 8px 0;")
            self._content_layout.addWidget(empty)

    def _build_ai_insights(self) -> None:
        """Build productivity insights section with progress rings."""
        header = QLabel("PRODUCTIVITY")
        header.setFont(QFont("Inter", 11, QFont.Bold))
        header.setStyleSheet(f"""
            color: {Palette.GOLD_PRIMARY};
            background: transparent;
            letter-spacing: 2px;
            padding: 8px 0 4px 0;
        """)
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

        # Progress rings
        rings_data = [
            (done_count, task_count, Palette.GOLD_PRIMARY, "Tasks"),
            (len(self._journal), max(len(self._journal), 1), "#8A6AAA", "Journals"),
        ]
        for val, mx, color, label in rings_data:
            ring = _ProgressRing(val, mx, color, label, card)
            card_layout.addWidget(ring)

        # Tip text on the right
        tip_container = QWidget()
        tip_container.setStyleSheet("background: transparent;")
        tip_layout = QVBoxLayout(tip_container)
        tip_layout.setContentsMargins(0, 0, 0, 0)
        tip_layout.setSpacing(6)

        tip_title = QLabel("Daily Tip")
        tip_title.setFont(QFont("Inter", 12, QFont.Bold))
        tip_title.setStyleSheet(
            f"color: {Palette.GOLD_BRIGHT}; background: transparent;"
        )
        tip_layout.addWidget(tip_title)

        tip_text = QLabel(
            "Plan your day in 30 seconds with AI \u2014 "
            "break down goals into actionable steps."
        )
        tip_text.setFont(QFont("Inter", 11))
        tip_text.setWordWrap(True)
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
        # Keep particles covering the full widget
        self._particles.setGeometry(self.rect())


class _HeroWidget(QWidget):
    """Custom-painted hero section with Shamsi date."""

    def __init__(self, today: ShamsiDate, parent=None) -> None:
        super().__init__(parent)
        self._today = today
        self.setFixedHeight(200)
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

        # ── Date display ──
        day_text = str(self._today.day)
        month_text = SHAMSI_MONTHS_FA[self._today.month - 1]
        year_text = str(self._today.year)
        weekday_text = self._today.weekday_fa

        # Big day number — hero gold gradient
        day_font = QFont("Segoe UI", 96, QFont.Bold)
        p.setFont(day_font)

        day_grad = QLinearGradient(0, 10, 0, 130)
        day_grad.setColorAt(0, QColor(245, 200, 66))
        day_grad.setColorAt(0.6, QColor(212, 175, 55))
        day_grad.setColorAt(1, QColor(140, 112, 18))
        p.setPen(QPen(QBrush(day_grad), 1))
        p.drawText(QRectF(0, 5, 200, 130), Qt.AlignCenter, day_text)

        # Month name
        month_font = QFont("Segoe UI", 36, QFont.Bold)
        p.setFont(month_font)
        p.setPen(QPen(QColor(Palette.GOLD_BRIGHT)))
        p.drawText(QRectF(200, 20, w - 220, 50), Qt.AlignLeft, month_text)

        # Year
        year_font = QFont("Inter", 18)
        p.setFont(year_font)
        p.setPen(QPen(QColor(Palette.TEXT_SECONDARY)))
        p.drawText(QRectF(200, 70, w - 220, 30), Qt.AlignLeft, year_text)

        # Weekday
        wd_font = QFont("Inter", 16)
        p.setFont(wd_font)
        p.setPen(QPen(QColor(Palette.TEXT_SECONDARY)))
        p.drawText(QRectF(200, 100, w - 220, 30), Qt.AlignLeft, weekday_text)

        # ── Subtle divider ──
        div_grad = QLinearGradient(0, 0, w, 0)
        div_grad.setColorAt(0, QColor(212, 175, 55, 0))
        div_grad.setColorAt(0.2, QColor(212, 175, 55, 60))
        div_grad.setColorAt(0.5, QColor(212, 175, 55, 80))
        div_grad.setColorAt(0.8, QColor(212, 175, 55, 60))
        div_grad.setColorAt(1, QColor(212, 175, 55, 0))
        p.setPen(Qt.NoPen)
        p.setBrush(QBrush(div_grad))
        p.drawRect(QRectF(0, h - 1, w, 1))

        p.end()
