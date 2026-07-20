"""
PlannerLanding — the first screen users see when opening the AI Planner.

A sleek, centered landing page inspired by modern AI assistants:
  - Bold headline at center
  - Subtitle tagline
  - Large centered text input with send button
  - Function category tabs at the bottom

When the user types a goal and submits, the `goalSubmitted` signal fires,
and the parent view transitions to the workspace (canvas + chat).

Uses the Kharazmi gold-on-dark theme throughout.
"""
from __future__ import annotations

from PySide6.QtCore import Qt, Signal, QTimer, QPropertyAnimation, QEasingCurve
from PySide6.QtGui import QFont, QColor, QPainter, QPen, QBrush
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, QPushButton,
    QFrame, QSizePolicy, QGraphicsOpacityEffect,
)

from ..theme import Palette


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
                font-size: 12px;
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
        # Let stylesheet handle everything
        super().paintEvent(event)


class PlannerLanding(QWidget):
    """Landing page for the AI Planner — shown before the user starts a plan."""

    goalSubmitted = Signal(str)  # Emits the goal text

    def __init__(self, parent: QWidget = None) -> None:
        super().__init__(parent)
        self._selected_category = "plan"
        self._particles: list[dict] = []
        self._tick = 0

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

        # Particle animation timer
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
        self.update()

    def paintEvent(self, event) -> None:
        """Draw floating gold particles behind all content."""
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, True)
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
        painter.end()

    def _build_ui(self) -> None:
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        # Central content container — transparent so particles show through
        content = QWidget(self)
        content.setStyleSheet("background-color: transparent;")
        layout = QVBoxLayout(content)
        layout.setContentsMargins(60, 0, 60, 40)
        layout.setSpacing(0)
        layout.addStretch(3)

        # ---- Logo / brand ----
        brand_row = QHBoxLayout()
        brand_row.addStretch()
        brand_label = QLabel("✦ KHARAZMI")
        brand_label.setStyleSheet(f"""
            color: {Palette.GOLD_BRIGHT};
            font-size: 14px;
            font-weight: bold;
            letter-spacing: 6px;
        """)
        brand_row.addWidget(brand_label)
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

        layout.addSpacing(12)

        # ---- Subtitle ----
        subtitle = QLabel("با هوش مصنوعی رَسک تعامل کنید و مسیر دستیابی به هدفتان را بسازید")
        subtitle.setAlignment(Qt.AlignCenter)
        subtitle.setWordWrap(True)
        subtitle.setStyleSheet(f"""
            color: {Palette.TEXT_SECONDARY};
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

        layout.addSpacing(50)

        # ---- Category tabs ----
        tabs_row = QHBoxLayout()
        tabs_row.setSpacing(12)
        tabs_row.addStretch()

        categories = [
            ("🗺", "برنامه‌ریزی", "plan"),
            ("📅", "زمان‌بندی", "schedule"),
            ("📊", "تحلیل", "analyze"),
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

    def _on_tab_clicked(self, key: str) -> None:
        self._selected_category = key
        for tab in self._tab_buttons:
            tab.setChecked(tab.property("category_key") == key)

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
