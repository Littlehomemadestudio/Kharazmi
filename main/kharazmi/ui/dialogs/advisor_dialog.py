"""Advisor report dialog."""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QFont, QColor
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QFrame, QScrollArea,
    QPushButton, QSizePolicy, QWidget,
)

from ...services import LocalAdvisor, Advice
from ...core import Project
from ..theme import Palette


class AdviceCard(QFrame):
    def __init__(self, advice: Advice, parent: QWidget = None) -> None:
        super().__init__(parent)
        self.advice = advice
        severity_color = {
            "info":     Palette.GOLD_PRIMARY,
            "warning":  Palette.GOLD_BRIGHT,
            "critical": Palette.STATUS_BLOCKED,
        }.get(advice.severity, Palette.TEXT_PRIMARY)
        self.setObjectName("adviceCard")
        self.setStyleSheet(f"""
            QFrame#adviceCard {{
                background-color: {Palette.BG_TERTIARY};
                border: 1px solid {Palette.BORDER_NORMAL};
                border-left: 3px solid {severity_color};
                border-radius: 4px;
                padding: 10px;
            }}
        """)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 10, 12, 10)
        layout.setSpacing(4)

        header = QHBoxLayout()
        kind_label = QLabel(advice.kind.upper())
        kind_label.setStyleSheet(
            f"color: {severity_color}; font-size: 9px; font-weight: bold; "
            f"letter-spacing: 1.5px;"
        )
        header.addWidget(kind_label)
        sev_label = QLabel(advice.severity.upper())
        sev_label.setStyleSheet(
            f"color: {Palette.TEXT_TERTIARY}; font-size: 9px; "
            f"font-weight: bold; letter-spacing: 1.5px;"
        )
        header.addWidget(sev_label)
        header.addStretch()
        layout.addLayout(header)

        title = QLabel(advice.title)
        title.setStyleSheet(
            f"color: {Palette.TEXT_PRIMARY}; font-size: 13px; font-weight: bold;"
        )
        title.setWordWrap(True)
        layout.addWidget(title)

        detail = QLabel(advice.detail)
        detail.setStyleSheet(f"color: {Palette.TEXT_SECONDARY}; font-size: 12px;")
        detail.setWordWrap(True)
        layout.addWidget(detail)


class AdvisorDialog(QDialog):
    def __init__(self, project: Project, parent=None) -> None:
        super().__init__(parent)
        self.project = project
        self.setWindowTitle("Advisor — Recommendations")
        self.setMinimumWidth(560)
        self.setMinimumHeight(500)
        self.setStyleSheet(f"background-color: {Palette.BG_PRIMARY};")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(10)

        title = QLabel("LOCAL ADVISOR")
        title.setStyleSheet(
            f"color: {Palette.GOLD_PRIMARY}; font-size: 13px; font-weight: bold; "
            f"letter-spacing: 2px;"
        )
        layout.addWidget(title)

        subtitle = QLabel(
            "Deterministic, rule-based analysis of the project. No external services."
        )
        subtitle.setStyleSheet(f"color: {Palette.TEXT_TERTIARY}; font-size: 11px;")
        subtitle.setWordWrap(True)
        layout.addWidget(subtitle)

        # Scrollable advice list
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        container = QWidget()
        container_layout = QVBoxLayout(container)
        container_layout.setContentsMargins(0, 0, 0, 0)
        container_layout.setSpacing(8)

        advisor = LocalAdvisor()
        advices = advisor.analyze(project)
        if not advices:
            empty = QLabel("No advice — the project looks clean.")
            empty.setStyleSheet(f"color: {Palette.TEXT_TERTIARY}; padding: 20px;")
            container_layout.addWidget(empty)
        else:
            for a in advices:
                container_layout.addWidget(AdviceCard(a))
        container_layout.addStretch()
        scroll.setWidget(container)
        layout.addWidget(scroll)

        close_btn = QPushButton("Close")
        close_btn.setProperty("variant", "primary")
        close_btn.clicked.connect(self.accept)
        layout.addWidget(close_btn)
