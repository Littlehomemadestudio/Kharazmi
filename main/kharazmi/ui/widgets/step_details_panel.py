"""
StepDetailsPanel — collapsible panel that expands when a route step is clicked.

When collapsed, shows a thin bar with "Step details" label.
When expanded (after clicking a node), shows full details:
  - Title
  - ID, duration, success probability, risk
  - Location, description
  - Fallback strategy
  - Sub-goals list
  - Dependencies
  - Cost estimate

A close button collapses the panel.
"""
from __future__ import annotations

from typing import Optional

from PySide6.QtCore import Qt, Signal, QTimer, QPropertyAnimation, QEasingCurve, QPoint
from PySide6.QtGui import QFont, QColor
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QFrame,
    QScrollArea, QSizePolicy, QGraphicsOpacityEffect,
)

from ...ai import RouteStep
from ..theme import Palette


class StepDetailsPanel(QFrame):
    """
    Collapsible panel showing details of the currently-selected step.

    Collapsed by default. Expands to a fixed height when a step is selected.
    """

    stepEditRequested = Signal(str)  # step_id

    COLLAPSED_HEIGHT = 32
    EXPANDED_HEIGHT = 280

    def __init__(self, parent: QWidget = None) -> None:
        super().__init__(parent)
        self._step: Optional[RouteStep] = None
        self._expanded = False

        self.setObjectName("stepDetailsPanel")
        self.setStyleSheet(f"""
            QFrame#stepDetailsPanel {{
                background-color: {Palette.BG_SECONDARY};
                border-top: 2px solid {Palette.GOLD_PRIMARY};
            }}
        """)
        self.setFixedHeight(self.COLLAPSED_HEIGHT)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # Header (always visible)
        header = QFrame()
        header.setFixedHeight(self.COLLAPSED_HEIGHT)
        header.setStyleSheet(f"background-color: {Palette.BG_TERTIARY}; border: none;")
        header_layout = QHBoxLayout(header)
        header_layout.setContentsMargins(12, 4, 12, 4)
        header_layout.setSpacing(8)

        self._title = QLabel("STEP DETAILS — click a node to expand")
        self._title.setStyleSheet(
            f"color: {Palette.GOLD_PRIMARY}; font-size: 11px; "
            f"font-weight: bold; letter-spacing: 2px; background: transparent; border: none;"
        )
        header_layout.addWidget(self._title)
        header_layout.addStretch()

        self._close_btn = QPushButton("✕")
        self._close_btn.setFixedSize(20, 20)
        self._close_btn.setStyleSheet(f"""
            QPushButton {{
                background: transparent;
                color: {Palette.TEXT_TERTIARY};
                border: none;
                font-size: 12px;
                font-weight: bold;
            }}
            QPushButton:hover {{
                color: {Palette.STATUS_BLOCKED};
            }}
        """)
        self._close_btn.clicked.connect(self.collapse)
        self._close_btn.hide()
        header_layout.addWidget(self._close_btn)
        layout.addWidget(header)

        # Content (only visible when expanded)
        self._content = QFrame()
        self._content.setStyleSheet(f"background-color: {Palette.BG_SECONDARY}; border: none;")
        content_layout = QVBoxLayout(self._content)
        content_layout.setContentsMargins(16, 8, 16, 12)
        content_layout.setSpacing(6)

        # Title
        self._step_title = QLabel("")
        self._step_title.setStyleSheet(
            f"color: {Palette.TEXT_PRIMARY}; font-size: 14px; font-weight: bold; "
            f"background: transparent; border: none;"
        )
        self._step_title.setWordWrap(True)
        content_layout.addWidget(self._step_title)

        # Meta row
        self._meta = QLabel("")
        self._meta.setStyleSheet(
            f"color: {Palette.TEXT_TERTIARY}; font-size: 10px; "
            f"font-family: 'JetBrains Mono', monospace; background: transparent; border: none;"
        )
        self._meta.setWordWrap(True)
        content_layout.addWidget(self._meta)

        # Description
        self._description = QLabel("")
        self._description.setStyleSheet(
            f"color: {Palette.TEXT_SECONDARY}; font-size: 12px; "
            f"background: transparent; border: none;"
        )
        self._description.setWordWrap(True)
        self._description.setTextFormat(Qt.RichText)
        content_layout.addWidget(self._description)

        # Scrollable details area
        self._details_scroll = QScrollArea()
        self._details_scroll.setWidgetResizable(True)
        self._details_scroll.setFrameShape(QFrame.NoFrame)
        self._details_scroll.setStyleSheet("QScrollArea { background: transparent; border: none; }")
        self._details_label = QLabel("")
        self._details_label.setStyleSheet(
            f"color: {Palette.TEXT_PRIMARY}; font-size: 12px; background: transparent; border: none;"
        )
        self._details_label.setWordWrap(True)
        self._details_label.setTextFormat(Qt.RichText)
        self._details_label.setAlignment(Qt.AlignTop | Qt.AlignLeft)
        self._details_scroll.setWidget(self._details_label)
        content_layout.addWidget(self._details_scroll, stretch=1)

        layout.addWidget(self._content)
        self._content.hide()

    def show_step(self, step: RouteStep) -> None:
        """Expand the panel and show details for the given step."""
        self._step = step
        self._step_title.setText(step.title)
        self._meta.setText(
            f"ID: {step.id}    "
            f"⏱ {step.duration_minutes}m    "
            f"✓ {step.success_probability:.0%}    "
            f"⚠ {step.risk_level.upper()}"
        )
        # Build rich details
        parts = []
        if step.location:
            parts.append(f"<b>📍 Location:</b> {step.location}")
        if step.description:
            parts.append(f"<b>What to do:</b><br>{step.description}")
        if step.fallback:
            parts.append(f"<b>↩ Fallback:</b> {step.fallback}")
        if step.sub_goals:
            parts.append("<b>◆ Sub-goals:</b>")
            for sg in step.sub_goals:
                parts.append(f"  • {sg}")
        if step.depends_on:
            parts.append(f"<b>Depends on:</b> {', '.join(step.depends_on)}")
        if step.cost_estimate:
            parts.append(f"<b>$ Cost:</b> {step.cost_estimate}")
        self._details_label.setText("<br><br>".join(parts))

        self._title.setText(f"STEP DETAILS — {step.id.upper()}")
        self._content.show()
        self._close_btn.show()
        self._expanded = True
        self.setFixedHeight(self.EXPANDED_HEIGHT)

    def collapse(self) -> None:
        self._step = None
        self._content.hide()
        self._close_btn.hide()
        self._title.setText("STEP DETAILS — click a node to expand")
        self._expanded = False
        self.setFixedHeight(self.COLLAPSED_HEIGHT)

    @property
    def is_expanded(self) -> bool:
        return self._expanded
