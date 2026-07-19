"""
StepDetailsPopup — a floating, closeable popup window showing step details.

Appears as a frameless window near the cursor when a node is clicked.
Can be dragged around. Has a close button. Shows full step info with
inline editing of title/description/duration/risk/etc.
"""
from __future__ import annotations

from typing import Optional

from PySide6.QtCore import Qt, Signal, QPoint, QPropertyAnimation, QEasingCurve, QTimer
from PySide6.QtGui import QFont, QColor, QMouseEvent
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QLineEdit,
    QTextEdit, QSpinBox, QDoubleSpinBox, QComboBox, QFrame, QSizePolicy,
    QApplication,
)

from ...ai import RouteStep
from ..theme import Palette


class StepDetailsPopup(QFrame):
    """
    A floating popup that shows step details and allows inline editing.

    Frameless, draggable, closeable.
    """
    closed = Signal()
    stepEdited = Signal(str, str, str)  # step_id, new_title, new_description
    stepFieldChanged = Signal(str, str, object)  # step_id, field_name, new_value

    def __init__(self, step: RouteStep, parent: QWidget = None) -> None:
        super().__init__(parent)
        self.step = step
        self._dragging = False
        self._drag_offset = QPoint()

        self.setWindowFlags(Qt.FramelessWindowHint | Qt.Tool)
        self.setAttribute(Qt.WA_StyledBackground, True)
        self.setStyleSheet(f"""
            StepDetailsPopup {{
                background-color: {Palette.BG_TERTIARY};
                border: 1px solid {Palette.GOLD_PRIMARY};
                border-radius: 8px;
            }}
        """)
        self.setFixedWidth(380)
        self.setMinimumHeight(400)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # Header (draggable)
        header = QFrame()
        header.setFixedHeight(36)
        header.setStyleSheet(
            f"background-color: {Palette.BG_ELEVATED}; "
            f"border-bottom: 1px solid {Palette.BORDER_SUBTLE}; "
            f"border-top-left-radius: 8px; border-top-right-radius: 8px;"
        )
        header_layout = QHBoxLayout(header)
        header_layout.setContentsMargins(12, 4, 8, 4)
        header_layout.setSpacing(8)

        icon = QLabel("◆")
        icon.setStyleSheet(
            f"color: {Palette.GOLD_BRIGHT}; font-size: 14px; "
            f"font-weight: bold; background: transparent; border: none;"
        )
        header_layout.addWidget(icon)
        title = QLabel(f"STEP {step.id.upper()} — DETAILS")
        title.setStyleSheet(
            f"color: {Palette.GOLD_PRIMARY}; font-size: 11px; "
            f"font-weight: bold; letter-spacing: 1.5px; "
            f"background: transparent; border: none;"
        )
        header_layout.addWidget(title)
        header_layout.addStretch()

        close_btn = QPushButton("✕")
        close_btn.setFixedSize(24, 24)
        close_btn.setStyleSheet(f"""
            QPushButton {{
                background: transparent;
                color: {Palette.TEXT_TERTIARY};
                border: none;
                font-size: 14px;
                font-weight: bold;
                border-radius: 4px;
            }}
            QPushButton:hover {{
                background-color: {Palette.STATUS_BLOCKED};
                color: {Palette.TEXT_PRIMARY};
            }}
        """)
        close_btn.clicked.connect(self._on_close)
        header_layout.addWidget(close_btn)
        layout.addWidget(header)

        # Content
        content = QWidget()
        content.setStyleSheet(f"background-color: {Palette.BG_TERTIARY};")
        content_layout = QVBoxLayout(content)
        content_layout.setContentsMargins(16, 12, 16, 16)
        content_layout.setSpacing(8)

        # Title editor
        content_layout.addWidget(self._make_label("TITLE"))
        self._title_edit = QLineEdit(step.title)
        self._title_edit.setStyleSheet(self._input_style())
        self._title_edit.textChanged.connect(
            lambda t: self.stepFieldChanged.emit(step.id, "title", t)
        )
        content_layout.addWidget(self._title_edit)

        # Description editor
        content_layout.addWidget(self._make_label("DESCRIPTION"))
        self._desc_edit = QTextEdit()
        self._desc_edit.setPlainText(step.description)
        self._desc_edit.setFixedHeight(80)
        self._desc_edit.setStyleSheet(self._input_style())
        self._desc_edit.textChanged.connect(
            lambda: self.stepFieldChanged.emit(step.id, "description", self._desc_edit.toPlainText())
        )
        content_layout.addWidget(self._desc_edit)

        # Duration + success probability row
        row1 = QHBoxLayout()
        row1.addWidget(self._make_label("DURATION (MIN)"))
        row1.addStretch()
        row1.addWidget(self._make_label("SUCCESS (%)"))
        content_layout.addLayout(row1)
        row2 = QHBoxLayout()
        self._dur_spin = QSpinBox()
        self._dur_spin.setRange(1, 9999)
        self._dur_spin.setValue(step.duration_minutes)
        self._dur_spin.setStyleSheet(self._input_style())
        self._dur_spin.valueChanged.connect(
            lambda v: self.stepFieldChanged.emit(step.id, "duration_minutes", v)
        )
        row2.addWidget(self._dur_spin)
        row2.addStretch()
        self._prob_spin = QDoubleSpinBox()
        self._prob_spin.setRange(0.0, 1.0)
        self._prob_spin.setSingleStep(0.05)
        self._prob_spin.setDecimals(2)
        self._prob_spin.setValue(step.success_probability)
        self._prob_spin.setStyleSheet(self._input_style())
        self._prob_spin.valueChanged.connect(
            lambda v: self.stepFieldChanged.emit(step.id, "success_probability", v)
        )
        row2.addWidget(self._prob_spin)
        content_layout.addLayout(row2)

        # Risk + branch row
        row3 = QHBoxLayout()
        row3.addWidget(self._make_label("RISK LEVEL"))
        row3.addStretch()
        row3.addWidget(self._make_label("BRANCH"))
        content_layout.addLayout(row3)
        row4 = QHBoxLayout()
        self._risk_combo = QComboBox()
        for r in ["low", "medium", "high", "severe"]:
            self._risk_combo.addItem(r)
        self._risk_combo.setCurrentText(step.risk_level)
        self._risk_combo.setStyleSheet(self._input_style())
        self._risk_combo.currentTextChanged.connect(
            lambda v: self.stepFieldChanged.emit(step.id, "risk_level", v)
        )
        row4.addWidget(self._risk_combo)
        row4.addStretch()
        self._branch_edit = QLineEdit(step.branch)
        self._branch_edit.setStyleSheet(self._input_style())
        self._branch_edit.textChanged.connect(
            lambda t: self.stepFieldChanged.emit(step.id, "branch", t)
        )
        row4.addWidget(self._branch_edit)
        content_layout.addLayout(row4)

        # Location
        content_layout.addWidget(self._make_label("LOCATION"))
        self._loc_edit = QLineEdit(step.location)
        self._loc_edit.setStyleSheet(self._input_style())
        self._loc_edit.textChanged.connect(
            lambda t: self.stepFieldChanged.emit(step.id, "location", t)
        )
        content_layout.addWidget(self._loc_edit)

        # Fallback
        content_layout.addWidget(self._make_label("FALLBACK (if this step fails)"))
        self._fb_edit = QTextEdit()
        self._fb_edit.setPlainText(step.fallback)
        self._fb_edit.setFixedHeight(50)
        self._fb_edit.setStyleSheet(self._input_style())
        self._fb_edit.textChanged.connect(
            lambda: self.stepFieldChanged.emit(step.id, "fallback", self._fb_edit.toPlainText())
        )
        content_layout.addWidget(self._fb_edit)

        # Sub-goals (read-only display)
        if step.sub_goals:
            content_layout.addWidget(self._make_label("SUB-GOALS"))
            for sg in step.sub_goals:
                sg_label = QLabel(f"  ◆ {sg}")
                sg_label.setStyleSheet(
                    f"color: {Palette.TEXT_SECONDARY}; font-size: 11px; "
                    f"background: transparent; border: none; padding: 2px 0;"
                )
                sg_label.setWordWrap(True)
                content_layout.addWidget(sg_label)

        # Dependencies (read-only)
        if step.depends_on:
            content_layout.addWidget(self._make_label("DEPENDS ON"))
            dep_label = QLabel(", ".join(step.depends_on))
            dep_label.setStyleSheet(
                f"color: {Palette.TEXT_TERTIARY}; font-size: 11px; "
                f"font-family: 'JetBrains Mono', monospace; "
                f"background: transparent; border: none; padding: 2px 0;"
            )
            dep_label.setWordWrap(True)
            content_layout.addWidget(dep_label)

        # Cost estimate
        content_layout.addWidget(self._make_label("COST ESTIMATE"))
        self._cost_edit = QLineEdit(step.cost_estimate)
        self._cost_edit.setStyleSheet(self._input_style())
        self._cost_edit.textChanged.connect(
            lambda t: self.stepFieldChanged.emit(step.id, "cost_estimate", t)
        )
        content_layout.addWidget(self._cost_edit)

        content_layout.addStretch()
        layout.addWidget(content, stretch=1)

        # Animate in
        self.setWindowOpacity(0.0)
        self._opacity_anim = QPropertyAnimation(self, b"windowOpacity")
        self._opacity_anim.setDuration(200)
        self._opacity_anim.setStartValue(0.0)
        self._opacity_anim.setEndValue(1.0)
        self._opacity_anim.setEasingCurve(QEasingCurve.OutCubic)
        QTimer.singleShot(50, self._opacity_anim.start)

    def _make_label(self, text: str) -> QLabel:
        lbl = QLabel(text)
        lbl.setStyleSheet(
            f"color: {Palette.TEXT_TERTIARY}; font-size: 9px; "
            f"font-weight: bold; letter-spacing: 1.5px; "
            f"background: transparent; border: none; padding-top: 4px;"
        )
        return lbl

    def _input_style(self) -> str:
        return f"""
            QLineEdit, QTextEdit, QSpinBox, QDoubleSpinBox, QComboBox {{
                background-color: {Palette.BG_DEEPEST};
                color: {Palette.TEXT_PRIMARY};
                border: 1px solid {Palette.BORDER_NORMAL};
                border-radius: 3px;
                padding: 6px 10px;
                font-size: 11px;
            }}
            QLineEdit:focus, QTextEdit:focus, QSpinBox:focus,
            QDoubleSpinBox:focus, QComboBox:focus {{
                border: 1px solid {Palette.GOLD_BRIGHT};
            }}
        """

    def _on_close(self) -> None:
        # Fade out then close
        self._close_anim = QPropertyAnimation(self, b"windowOpacity")
        self._close_anim.setDuration(150)
        self._close_anim.setStartValue(1.0)
        self._close_anim.setEndValue(0.0)
        self._close_anim.finished.connect(self.close)
        self._close_anim.finished.connect(self.closed.emit)
        self._close_anim.start()

    # ---- Dragging ----
    def mousePressEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.LeftButton:
            # Only start drag from the header area
            if event.position().y() <= 36:
                self._dragging = True
                self._drag_offset = event.globalPosition().toPoint() - self.frameGeometry().topLeft()
                event.accept()
                return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        if self._dragging:
            self.move(event.globalPosition().toPoint() - self._drag_offset)
            event.accept()
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        self._dragging = False
        super().mouseReleaseEvent(event)

    def closeEvent(self, event) -> None:
        self.closed.emit()
        super().closeEvent(event)
