"""
PlannerLanding — the first screen users see when opening the AI Planner.

A sleek, centered landing page inspired by modern AI assistants:
  - Bold headline at center with animated gold underline
  - Subtitle tagline
  - Large centered text input with send button
  - Keyboard shortcut hints
  - Suggestion chips (6 total)
  - Power badges row (capability pills)
  - Recent activity section (last 2 journal entries)
  - Release notes / changelog card
  - Category tabs at the bottom

When the user types a goal and submits, the `goalSubmitted` signal fires,
and the parent view transitions to the workspace (canvas + chat).

Uses the Kharazmi gold-on-dark theme throughout.
"""
from __future__ import annotations

import math
from typing import Optional, TYPE_CHECKING

from PySide6.QtCore import Qt, Signal, QTimer, QPropertyAnimation, QEasingCurve, QRectF, QPointF
from PySide6.QtGui import QFont, QColor, QPainter, QPen, QBrush, QLinearGradient
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, QPushButton,
    QFrame, QSizePolicy, QGraphicsOpacityEffect,
)

from ..theme import Palette, with_alpha


# ---- Category tab button ----
class _CategoryTab(QPushButton):
    """A rounded category tab button with icon and label."""

    def __init__(self, icon_char: str, label: str, parent: QWidget = None) -> None:
        super().__init__(parent)
        self._icon = icon_char
        self._label = label
        self.setCheckable(True)
        self.setCursor(Qt.PointingHandCursor)
        self.setFixedHeight(60)
        self.setMinimumWidth(120)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self._update_style()

    def _update_style(self) -> None:
        self.setStyleSheet(f"""
            QPushButton {{
                background-color: {Palette.BG_TERTIARY};
                color: {Palette.TEXT_SECONDARY};
                border: 1px solid {Palette.BORDER_SUBTLE};
                border-radius: 12px;
                padding: 10px 18px;
                font-size: 13px;
                font-weight: bold;
                text-align: center;
            }}
            QPushButton:hover {{
                background-color: {Palette.BG_ELEVATED};
                color: {Palette.GOLD_PRIMARY};
                border: 1px solid {Palette.BORDER_GOLD};
            }}
            QPushButton:checked {{
                background-color: {Palette.BG_SELECTED};
                color: {Palette.GOLD_BRIGHT};
                border: 1px solid {Palette.GOLD_DEEP};
            }}
        """)

    def paintEvent(self, event) -> None:
        # Let stylesheet handle background, then draw icon + label
        super().paintEvent(event)
        from PySide6.QtGui import QPainter, QFont, QPen
        from PySide6.QtCore import QRectF, Qt
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing, True)

        # Use the current text color from the stylesheet
        if self.isChecked():
            color = QColor(Palette.GOLD_BRIGHT)
        elif self.underMouse():
            color = QColor(Palette.GOLD_PRIMARY)
        else:
            color = QColor(Palette.TEXT_SECONDARY)

        # Draw label text centered
        p.setPen(QPen(color))
        p.setFont(QFont("Inter", 13, QFont.Bold))
        p.drawText(QRectF(0, 0, self.width(), self.height()),
                   Qt.AlignCenter, self._label)
        p.end()


class PlannerLanding(QWidget):
    """Landing page for the AI Planner — shown before the user starts a plan."""

    goalSubmitted = Signal(str)  # Emits the goal text

    def __init__(self, journal_store=None, parent: QWidget = None) -> None:
        super().__init__(parent)
        self._selected_category = "plan"
        self._particles: list[dict] = []
        self._tick = 0
        self._journal_store = journal_store

        # Brand pulse animation state
        self._brand_opacity = 1.0
        self._brand_pulse_dir = -1  # -1 = fading down, +1 = fading up

        # Animated gold underline state
        self._underline_width = 0.0  # 0..1 fraction expanding from center

        # Initialize particles
        import random
        rng = random.Random(42)
        for _ in range(35):
            self._particles.append({
                "x": rng.uniform(0, 1),
                "y": rng.uniform(0, 1),
                "size": rng.uniform(1.5, 4.0),
                "speed": rng.uniform(0.0003, 0.0015),
                "alpha": rng.uniform(15, 50),
                "drift": rng.uniform(-0.0005, 0.0005),
            })

        self.setStyleSheet(f"background-color: {Palette.BG_PRIMARY};")
        self._build_ui()

        # Particle + animation timer
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._advance_particles)
        self._timer.start(33)  # ~30fps

    def _advance_particles(self) -> None:
        self._tick += 1

        for p in self._particles:
            p["y"] -= p["speed"]
            p["x"] += p["drift"]
            if p["y"] < -0.02:
                p["y"] = 1.02
                p["x"] += 0.1
                if p["x"] > 1:
                    p["x"] -= 1

        # Brand label pulse animation
        self._brand_opacity += self._brand_pulse_dir * 0.012
        if self._brand_opacity <= 0.55:
            self._brand_opacity = 0.55
            self._brand_pulse_dir = 1
        elif self._brand_opacity >= 1.0:
            self._brand_opacity = 1.0
            self._brand_pulse_dir = -1

        # Gold underline expanding from center
        if self._underline_width < 1.0:
            self._underline_width = min(1.0, self._underline_width + 0.025)

        self.update()

    def paintEvent(self, event) -> None:
        """Draw floating gold particles + animated gold underline behind all content."""
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, True)
        try:
            w, h = self.width(), self.height()
            gold = QColor(Palette.GOLD_PRIMARY)
            for p in self._particles:
                gold.setAlpha(int(p["alpha"]))
                painter.setPen(Qt.NoPen)
                painter.setBrush(gold)
                painter.drawEllipse(
                    int(p["x"] * w), int(p["y"] * h),
                    int(p["size"] * 2), int(p["size"] * 2),
                )

            # ── Animated gold underline below headline ──
            if self._underline_width > 0 and hasattr(self, '_headline_geom'):
                hx, hy, hw = self._headline_geom
                line_w = hw * self._underline_width
                line_x = hx + (hw - line_w) / 2
                line_y = hy + 4  # just below headline bottom
                grad = QLinearGradient(line_x, line_y, line_x + line_w, line_y)
                grad.setColorAt(0.0, with_alpha(Palette.GOLD_PRIMARY, 0))
                grad.setColorAt(0.15, with_alpha(Palette.GOLD_BRIGHT, 200))
                grad.setColorAt(0.5, with_alpha(Palette.GOLD_BRIGHT, 255))
                grad.setColorAt(0.85, with_alpha(Palette.GOLD_BRIGHT, 200))
                grad.setColorAt(1.0, with_alpha(Palette.GOLD_PRIMARY, 0))
                painter.setPen(Qt.NoPen)
                painter.setBrush(QBrush(grad))
                painter.drawRoundedRect(QRectF(line_x, line_y, line_w, 2), 1, 1)

            # ── Brand label pulse opacity ──
            if hasattr(self, '_brand_label'):
                op = QGraphicsOpacityEffect(self._brand_label)
                op.setOpacity(self._brand_opacity)
                self._brand_label.setGraphicsEffect(op)
        finally:
            painter.end()

    def _build_ui(self) -> None:
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        # Scrollable content area
        content = QWidget(self)
        content.setStyleSheet("background-color: transparent;")
        layout = QVBoxLayout(content)
        layout.setContentsMargins(60, 0, 60, 30)
        layout.setSpacing(0)
        layout.addStretch(3)

        # ---- Logo / brand (with pulse animation) ----
        brand_row = QHBoxLayout()
        brand_row.addStretch()
        self._brand_label = QLabel("✦ KHARAZMI")
        self._brand_label.setStyleSheet(f"""
            color: {Palette.GOLD_BRIGHT};
            font-size: 14px;
            font-weight: bold;
            letter-spacing: 6px;
        """)
        brand_row.addWidget(self._brand_label)
        brand_row.addStretch()
        layout.addLayout(brand_row)

        layout.addSpacing(30)

        # ---- Headline ----
        headline = QLabel("هر چیزی که تصورش را بکنید، برنامه‌ریزی کنید")
        headline.setAlignment(Qt.AlignCenter)
        headline.setStyleSheet(f"""
            color: {Palette.TEXT_PRIMARY};
            font-size: 32px;
            font-weight: bold;
            letter-spacing: -0.5px;
        """)
        layout.addWidget(headline)
        # Store geometry for animated underline painting
        self._headline_geom = (0, 0, 1)  # will be updated in resizeEvent

        layout.addSpacing(12)

        # ---- Subtitle ----
        subtitle = QLabel("با هوش مصنوعی رَسک تعامل کنید و مسیر دستیابی به هدفتان را بسازید")
        subtitle.setAlignment(Qt.AlignCenter)
        subtitle.setWordWrap(True)
        subtitle.setStyleSheet(f"""
            color: {Palette.TEXT_PRIMARY};
            font-size: 15px;
            font-weight: normal;
        """)
        layout.addWidget(subtitle)

        layout.addSpacing(40)

        # ---- Input field + send button ----
        input_container = QFrame()
        input_container.setStyleSheet(f"""
            QFrame {{
                background-color: {Palette.BG_TERTIARY};
                border: 1px solid {Palette.BORDER_NORMAL};
                border-radius: 16px;
                padding: 0px;
            }}
            QFrame:hover {{
                border: 1px solid {Palette.BORDER_GOLD};
            }}
        """)
        input_layout = QHBoxLayout(input_container)
        input_layout.setContentsMargins(18, 6, 6, 6)
        input_layout.setSpacing(10)

        # "+" button on the left
        plus_btn = QPushButton("+")
        plus_btn.setFixedSize(36, 36)
        plus_btn.setCursor(Qt.PointingHandCursor)
        plus_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: transparent;
                color: {Palette.TEXT_TERTIARY};
                border: none;
                border-radius: 8px;
                font-size: 20px;
                font-weight: bold;
            }}
            QPushButton:hover {{
                background-color: {Palette.BG_ELEVATED};
                color: {Palette.GOLD_PRIMARY};
            }}
        """)
        input_layout.addWidget(plus_btn)

        self._input = QLineEdit()
        self._input.setPlaceholderText("هدفتان را بنویسید... (مثلاً: می‌خواهم تا ساعت ۹ خانه باشم)")
        self._input.setStyleSheet(f"""
            QLineEdit {{
                background-color: transparent;
                color: {Palette.TEXT_PRIMARY};
                border: none;
                font-size: 15px;
                padding: 8px 4px;
            }}
            QLineEdit::placeholder {{
                color: {Palette.TEXT_TERTIARY};
            }}
        """)
        self._input.returnPressed.connect(self._on_submit)
        input_layout.addWidget(self._input, stretch=1)

        # Send button on the right
        self._send_btn = QPushButton("↑")
        self._send_btn.setFixedSize(44, 44)
        self._send_btn.setCursor(Qt.PointingHandCursor)
        self._send_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: {Palette.GOLD_PRIMARY};
                color: {Palette.TEXT_ON_GOLD};
                border: none;
                border-radius: 12px;
                font-size: 22px;
                font-weight: bold;
            }}
            QPushButton:hover {{
                background-color: {Palette.GOLD_BRIGHT};
            }}
            QPushButton:pressed {{
                background-color: {Palette.GOLD_DEEP};
            }}
        """)
        self._send_btn.clicked.connect(self._on_submit)
        input_layout.addWidget(self._send_btn)

        # Limit width of input container
        input_container.setMaximumWidth(700)
        input_container.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)

        # Center the input
        input_row = QHBoxLayout()
        input_row.addStretch()
        input_row.addWidget(input_container)
        input_row.addStretch()
        layout.addLayout(input_row)

        # ---- Keyboard shortcut hints ----
        shortcuts_row = QHBoxLayout()
        shortcuts_row.addStretch()
        ctrl_hint = QLabel("Ctrl+Enter برای شروع  ·  Esc برای بازگشت")
        ctrl_hint.setAlignment(Qt.AlignCenter)
        ctrl_hint.setStyleSheet(f"""
            color: {Palette.TEXT_TERTIARY};
            font-size: 11px;
            background: transparent;
        """)
        shortcuts_row.addWidget(ctrl_hint)
        shortcuts_row.addStretch()
        layout.addLayout(shortcuts_row)

        layout.addSpacing(20)

        # ---- Suggestion chips (6 total) ----
        chips_row = QHBoxLayout()
        chips_row.setSpacing(10)
        chips_row.addStretch()

        suggestions = [
            "برنامه‌ریزی سفر ۹ روزه",
            "یادگیری زبان جدید",
            "راه‌اندازی استارتاپ",
            "آمادگی کنکور",
            "پخت کیک",
            "تمرین روزانه",
        ]
        self._suggestion_chips: list[QPushButton] = []
        for text in suggestions:
            chip = QPushButton(text)
            chip.setCursor(Qt.PointingHandCursor)
            chip.setStyleSheet(f"""
                QPushButton {{
                    background-color: {Palette.BG_TERTIARY};
                    color: {Palette.TEXT_PRIMARY};
                    border: 1px solid {Palette.BORDER_GOLD};
                    border-radius: 20px;
                    padding: 8px 18px;
                    font-size: 12px;
                    font-weight: normal;
                }}
                QPushButton:hover {{
                    background-color: {Palette.BG_SELECTED};
                    color: {Palette.GOLD_BRIGHT};
                    border: 1px solid {Palette.GOLD_PRIMARY};
                }}
                QPushButton:pressed {{
                    background-color: {Palette.GOLD_MUTED};
                }}
            """)
            chip.clicked.connect(lambda checked, t=text: self._on_chip_clicked(t))
            chips_row.addWidget(chip)
            self._suggestion_chips.append(chip)

        chips_row.addStretch()
        layout.addLayout(chips_row)

        layout.addSpacing(20)

        # ---- Power badges row ----
        badges_row = QHBoxLayout()
        badges_row.setSpacing(10)
        badges_row.addStretch()

        badges = [
            "GLM-4.5 Flash",
            "شبیه‌سازی مونت‌کارلو",
            "تحلیل مسیر بحرانی",
            "تقویم شمسی",
        ]
        for badge_text in badges:
            badge = QLabel(badge_text)
            badge.setAlignment(Qt.AlignCenter)
            badge.setStyleSheet(f"""
                color: {Palette.GOLD_PRIMARY};
                font-size: 11px;
                font-weight: bold;
                background-color: {Palette.BG_TERTIARY};
                border: 1px solid {Palette.GOLD_DEEP};
                border-radius: 12px;
                padding: 4px 14px;
            """)
            badges_row.addWidget(badge)

        badges_row.addStretch()
        layout.addLayout(badges_row)

        layout.addSpacing(24)

        # ---- Recent activity section ----
        recent_title = QLabel("اخیراً")
        recent_title.setAlignment(Qt.AlignCenter)
        recent_title.setStyleSheet(f"""
            color: {Palette.GOLD_PRIMARY};
            font-size: 14px;
            font-weight: bold;
            letter-spacing: 1px;
            background: transparent;
        """)
        layout.addWidget(recent_title)

        layout.addSpacing(6)

        # Build recent activity cards from journal store
        recent_entries = self._get_recent_entries()
        if recent_entries:
            for entry_text in recent_entries:
                card = QFrame()
                card.setStyleSheet(f"""
                    QFrame {{
                        background-color: {Palette.BG_TERTIARY};
                        border: 1px solid {Palette.BORDER_SUBTLE};
                        border-radius: 8px;
                        padding: 8px 16px;
                    }}
                """)
                card_layout = QHBoxLayout(card)
                card_layout.setContentsMargins(12, 6, 12, 6)
                card_layout.setSpacing(8)

                dot = QLabel("◉")
                dot.setStyleSheet(f"""
                    color: {Palette.GOLD_PRIMARY};
                    font-size: 10px;
                    background: transparent;
                    border: none;
                """)
                card_layout.addWidget(dot)

                goal_label = QLabel(entry_text)
                goal_label.setWordWrap(True)
                goal_label.setStyleSheet(f"""
                    color: {Palette.TEXT_SECONDARY};
                    font-size: 12px;
                    background: transparent;
                    border: none;
                """)
                card_layout.addWidget(goal_label, stretch=1)

                card.setMaximumWidth(500)
                card.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)

                center_row = QHBoxLayout()
                center_row.addStretch()
                center_row.addWidget(card)
                center_row.addStretch()
                layout.addLayout(center_row)

                layout.addSpacing(4)
        else:
            empty_label = QLabel("هنوز فعالیتی ندارید")
            empty_label.setAlignment(Qt.AlignCenter)
            empty_label.setStyleSheet(f"""
                color: {Palette.TEXT_TERTIARY};
                font-size: 12px;
                font-style: italic;
                background: transparent;
            """)
            layout.addWidget(empty_label)

        layout.addSpacing(20)

        # ---- Release notes / changelog card ----
        release_card = QFrame()
        release_card.setStyleSheet(f"""
            QFrame {{
                background-color: {Palette.BG_SECONDARY};
                border: none;
                border-left: 3px solid {Palette.GOLD_PRIMARY};
                border-radius: 0px;
                padding: 16px 20px;
            }}
        """)
        release_layout = QVBoxLayout(release_card)
        release_layout.setContentsMargins(20, 12, 12, 12)
        release_layout.setSpacing(8)

        release_title = QLabel("✦ ویژگی‌های جدید")
        release_title.setStyleSheet(f"""
            color: {Palette.GOLD_BRIGHT};
            font-size: 14px;
            font-weight: bold;
            background: transparent;
            border: none;
        """)
        release_layout.addWidget(release_title)

        features = [
            "برنامه‌ریزی هوشمند با هوش مصنوعی GLM-4.5",
            "تقویم شمسی با رویدادهای تکرارشونده",
            "شبیه‌سازی مونت‌کارلو برای تحلیل مسیرها",
            "خروجی CSV، Excel و HTML از مسیرها",
        ]
        for feat in features:
            feat_row = QHBoxLayout()
            feat_row.setSpacing(8)

            bullet = QLabel("◆")
            bullet.setFixedWidth(14)
            bullet.setStyleSheet(f"""
                color: {Palette.GOLD_PRIMARY};
                font-size: 8px;
                background: transparent;
                border: none;
            """)
            feat_row.addWidget(bullet)

            feat_label = QLabel(feat)
            feat_label.setWordWrap(True)
            feat_label.setStyleSheet(f"""
                color: {Palette.TEXT_SECONDARY};
                font-size: 12px;
                background: transparent;
                border: none;
            """)
            feat_row.addWidget(feat_label, stretch=1)

            release_layout.addLayout(feat_row)

        release_card.setMaximumWidth(600)
        release_card.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)

        release_center = QHBoxLayout()
        release_center.addStretch()
        release_center.addWidget(release_card)
        release_center.addStretch()
        layout.addLayout(release_center)

        layout.addSpacing(20)

        # ---- Category tabs ----
        tabs_row = QHBoxLayout()
        tabs_row.setSpacing(12)
        tabs_row.addStretch()

        categories = [
            ("◉", "برنامه‌ریزی", "plan"),
            ("⏱", "زمان‌بندی", "schedule"),
            ("◈", "تحلیل", "analyze"),
            ("⚡", "بهینه‌سازی", "optimize"),
        ]

        self._tab_buttons: list[_CategoryTab] = []
        for icon, label, key in categories:
            tab = _CategoryTab(icon, label)
            tab.setProperty("category_key", key)
            if key == "plan":
                tab.setChecked(True)
            tab.clicked.connect(lambda checked, k=key: self._on_tab_clicked(k))
            tab.setMaximumWidth(160)
            tabs_row.addWidget(tab)
            self._tab_buttons.append(tab)

        tabs_row.addStretch()
        layout.addLayout(tabs_row)

        layout.addStretch(2)

        # ---- Bottom hint ----
        hint = QLabel("Press Enter to start planning with AI  ·  رَسک هوش مصنوعی شماست")
        hint.setAlignment(Qt.AlignCenter)
        hint.setStyleSheet(f"""
            color: {Palette.TEXT_TERTIARY};
            font-size: 11px;
        """)
        layout.addWidget(hint)

        # IMPORTANT: Add content to the outer layout so it actually shows!
        outer.addWidget(content, stretch=1)

    def _get_recent_entries(self) -> list[str]:
        """Get the last 2 journal entry goal texts, or empty list."""
        if self._journal_store is None:
            return []
        try:
            entries = self._journal_store.list_entries()
            if entries:
                return [e.get("goal", e.get("title", ""))[:80] for e in entries[:2]]
        except Exception:
            pass
        return []

    def resizeEvent(self, event) -> None:
        """Update headline geometry for animated underline."""
        super().resizeEvent(event)
        # Find the headline widget to position the underline
        # We approximate: headline is centered, about 70% of content width
        content_w = self.width() - 120  # margins
        self._headline_geom = (60, 0, content_w)

    def _on_tab_clicked(self, key: str) -> None:
        self._selected_category = key
        for tab in self._tab_buttons:
            tab.setChecked(tab.property("category_key") == key)

    def _on_chip_clicked(self, text: str) -> None:
        """Fill the input with the clicked suggestion and submit."""
        self._input.setText(text)
        self.goalSubmitted.emit(text)

    def _on_submit(self) -> None:
        goal = self._input.text().strip()
        if not goal:
            return
        self.goalSubmitted.emit(goal)

    def focus_input(self) -> None:
        """Set focus to the input field."""
        self._input.setFocus()

    def animate_out(self) -> None:
        """Fade out animation before switching to workspace."""
        effect = QGraphicsOpacityEffect(self)
        self.setGraphicsEffect(effect)
        self._fade_anim = QPropertyAnimation(effect, b"opacity")
        self._fade_anim.setDuration(350)
        self._fade_anim.setStartValue(1.0)
        self._fade_anim.setEndValue(0.0)
        self._fade_anim.setEasingCurve(QEasingCurve.Type.InCubic)
        self._fade_anim.start()

    def animate_in(self) -> None:
        """Fade in animation when showing the landing page."""
        effect = QGraphicsOpacityEffect(self)
        self.setGraphicsEffect(effect)
        self._fade_anim = QPropertyAnimation(effect, b"opacity")
        self._fade_anim.setDuration(400)
        self._fade_anim.setStartValue(0.0)
        self._fade_anim.setEndValue(1.0)
        self._fade_anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        self._fade_anim.start()
