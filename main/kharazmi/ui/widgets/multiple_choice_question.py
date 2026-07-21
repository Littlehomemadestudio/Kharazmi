"""
MultipleChoiceQuestionWidget — responsive question panel for the AI planner.

Shows a question with option buttons that fully adapt to text length:
  - Short options: horizontal row of compact buttons
  - Long options: vertical stack of full-width buttons with word wrap
  - Mixed: smart layout that adapts per-option
  - Never breaks, never clips, always readable

Also supports 4-6 options + custom "Other..." input.
"""
from __future__ import annotations

from typing import Optional

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QFont, QFontMetrics
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QLineEdit,
    QFrame, QSizePolicy, QScrollArea,
)

from ...ai import MultipleChoiceQuestion
from ..theme import Palette


# ──────────────────────────── Helper ──────────────────────────────────

def _estimate_text_width(text: str, font: QFont) -> int:
    """Estimate the pixel width needed to render text without wrapping."""
    fm = QFontMetrics(font)
    return fm.horizontalAdvance(text)


def _is_long_option(text: str, font: QFont, threshold: int = 60) -> bool:
    """Return True if the option text is long enough to need its own row."""
    return _estimate_text_width(text, font) > threshold


# ──────────────────────────── Option Button ───────────────────────────

class _OptionButton(QPushButton):
    """
    A QPushButton that wraps long text.

    QPushButton doesn't natively support word wrap, so we override
    the size hint and paint the text ourselves using QLabel-style
    eliding for short-mode and word-wrapping for long-mode.
    """

    def __init__(self, label: str, text: str, parent=None) -> None:
        super().__init__(parent)
        self._label = label
        self._option_text = text
        self._is_long = len(text) > 30 or '\n' in text

        self.setCursor(Qt.PointingHandCursor)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Minimum)

        if self._is_long:
            # Long options: full width, allow word wrap via minimum height
            self.setStyleSheet(f"""
                QPushButton {{
                    background-color: {Palette.BG_ELEVATED};
                    color: {Palette.TEXT_PRIMARY};
                    border: 1px solid {Palette.BORDER_NORMAL};
                    border-left: 3px solid {Palette.GOLD_DEEP};
                    border-radius: 4px;
                    padding: 10px 14px;
                    font-size: 12px;
                    text-align: left;
                    min-height: 36px;
                }}
                QPushButton:hover {{
                    background-color: {Palette.BG_SELECTED};
                    border-left: 3px solid {Palette.GOLD_PRIMARY};
                    border-color: {Palette.GOLD_PRIMARY} {Palette.BORDER_NORMAL} {Palette.BORDER_NORMAL} {Palette.GOLD_PRIMARY};
                    color: {Palette.GOLD_BRIGHT};
                }}
                QPushButton:pressed {{
                    background-color: {Palette.GOLD_MUTED};
                }}
            """)
        else:
            # Short options: compact button
            self.setStyleSheet(f"""
                QPushButton {{
                    background-color: {Palette.BG_ELEVATED};
                    color: {Palette.TEXT_PRIMARY};
                    border: 1px solid {Palette.BORDER_NORMAL};
                    border-radius: 4px;
                    padding: 8px 12px;
                    font-size: 12px;
                    text-align: left;
                }}
                QPushButton:hover {{
                    background-color: {Palette.BG_SELECTED};
                    border: 1px solid {Palette.GOLD_PRIMARY};
                    color: {Palette.GOLD_BRIGHT};
                }}
                QPushButton:pressed {{
                    background-color: {Palette.GOLD_MUTED};
                }}
            """)

        self.setText(f"{label}.  {text}")

    def sizeHint(self):
        """Return a size that fits the text without clipping."""
        from PySide6.QtCore import QSize
        fm = QFontMetrics(self.font())
        if self._is_long:
            # Estimate height for wrapped text at ~300px width
            rect = fm.boundingRect(0, 0, 300, 0, Qt.TextWordWrap, self.text())
            return QSize(max(super().sizeHint().width(), 200), rect.height() + 24)
        return super().sizeHint()

    def minimumSizeHint(self):
        from PySide6.QtCore import QSize
        if self._is_long:
            return QSize(160, 36)
        return super().minimumSizeHint()

    def paintEvent(self, event):
        """Override paint to handle word-wrap for long options."""
        if self._is_long:
            from PySide6.QtGui import QPainter, QPen, QStyleOptionButton
            from PySide6.QtWidgets import QStyle

            opt = QStyleOptionButton()
            self.initStyleOption(opt)
            self.style().drawControl(QStyle.CE_PushButtonBevel, opt, self, self)

            # Draw text with word wrap
            painter = QPainter(self)
            painter.setRenderHint(QPainter.TextAntialiasing)
            color = self.palette().color(self.foregroundRole())
            if self.isDown():
                color = self.palette().color(self.foregroundRole())
            painter.setPen(QPen(color))
            painter.setFont(self.font())

            text_rect = self.rect().adjusted(14, 8, -8, -8)
            painter.drawText(text_rect, Qt.AlignLeft | Qt.AlignTop | Qt.TextWordWrap, self.text())
            painter.end()
        else:
            super().paintEvent(event)


# ──────────────────────────── Question Widget ─────────────────────────

class MultipleChoiceQuestionWidget(QFrame):
    """
    A single multiple-choice question with adaptive layout.

    - Questions of any length are fully displayed with word wrap
    - Hints wrap naturally
    - Options adapt: short → horizontal row, long → vertical stack
    - Mixed short/long → vertical stack for consistency
    - Custom input always wraps to full width
    - Never breaks, never clips, always readable
    """

    answered = Signal(str)  # the chosen answer (option text or custom)

    def __init__(self, question: MultipleChoiceQuestion, index: int,
                 parent: QWidget = None) -> None:
        super().__init__(parent)
        self.question = question
        self._index = index
        self._custom_mode = False

        self.setStyleSheet(f"""
            QFrame#questionCard {{
                background-color: {Palette.BG_TERTIARY};
                border: 1px solid {Palette.BORDER_NORMAL};
                border-left: 3px solid {Palette.GOLD_PRIMARY};
                border-radius: 6px;
            }}
        """)
        self.setObjectName("questionCard")
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Minimum)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 12, 14, 12)
        layout.setSpacing(8)

        # ── Question header ──
        q_label = QLabel(f"<b style='color:{Palette.GOLD_BRIGHT}'>Q{index + 1}.</b>  {question.question}")
        q_label.setStyleSheet(
            f"color: {Palette.TEXT_PRIMARY}; font-size: 13px; "
            f"background: transparent; border: none;"
        )
        q_label.setWordWrap(True)
        q_label.setTextFormat(Qt.RichText)
        q_label.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Minimum)
        layout.addWidget(q_label)

        # ── Hint ──
        if question.hint:
            hint_label = QLabel(f"💡 {question.hint}")
            hint_label.setStyleSheet(
                f"color: {Palette.TEXT_TERTIARY}; font-size: 11px; "
                f"font-style: italic; background: transparent; border: none;"
            )
            hint_label.setWordWrap(True)
            hint_label.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Minimum)
            layout.addWidget(hint_label)

        # ── Options ──
        opts = question.options[:6]  # Allow up to 6 options

        # Decide layout: if any option is long, use vertical stack for all
        font = QFont("Inter", 12)
        has_long = any(_is_long_option(opt, font, 80) for opt in opts)
        long_count = sum(1 for opt in opts if _is_long_option(opt, font, 80))

        if has_long or len(opts) > 4:
            # ── Vertical stack: one option per row, full width ──
            for i, opt in enumerate(opts):
                btn = _OptionButton(str(i + 1), opt)
                btn.clicked.connect(lambda _=False, o=opt: self.answered.emit(o))
                layout.addWidget(btn)
        else:
            # ── Horizontal rows: 2 per row for short options ──
            row = None
            for i, opt in enumerate(opts):
                if i % 2 == 0:
                    row = QHBoxLayout()
                    row.setSpacing(6)
                btn = _OptionButton(str(i + 1), opt)
                btn.clicked.connect(lambda _=False, o=opt: self.answered.emit(o))
                row.addWidget(btn, stretch=1)
                if i % 2 == 1 or i == len(opts) - 1:
                    layout.addLayout(row)

        # ── Separator ──
        sep = QFrame()
        sep.setFrameShape(QFrame.HLine)
        sep.setStyleSheet(f"color: {Palette.BORDER_SUBTLE};")
        sep.setFixedHeight(1)
        layout.addWidget(sep)

        # ── Custom input row ──
        custom_row = QHBoxLayout()
        custom_row.setSpacing(6)

        custom_label = QLabel("✏️")
        custom_label.setStyleSheet(f"color: {Palette.TEXT_TERTIARY}; background: transparent; border: none; font-size: 13px;")
        custom_label.setFixedWidth(20)
        custom_row.addWidget(custom_label)

        self._custom_input = QLineEdit()
        self._custom_input.setPlaceholderText("Type your own answer and press Enter…")
        self._custom_input.setStyleSheet(f"""
            QLineEdit {{
                background-color: {Palette.BG_ELEVATED};
                color: {Palette.TEXT_PRIMARY};
                border: 1px solid {Palette.BORDER_NORMAL};
                border-radius: 4px;
                padding: 8px 12px;
                font-size: 12px;
            }}
            QLineEdit:focus {{
                border: 1px solid {Palette.GOLD_PRIMARY};
            }}
        """)
        self._custom_input.returnPressed.connect(self._on_custom_submitted)
        custom_row.addWidget(self._custom_input, stretch=1)

        submit_btn = QPushButton("→")
        submit_btn.setToolTip("Submit custom answer")
        submit_btn.setFixedSize(32, 32)
        submit_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: {Palette.GOLD_PRIMARY};
                color: {Palette.TEXT_ON_GOLD};
                border: none;
                border-radius: 4px;
                font-size: 14px;
                font-weight: bold;
            }}
            QPushButton:hover {{
                background-color: {Palette.GOLD_BRIGHT};
            }}
        """)
        submit_btn.clicked.connect(self._on_custom_submitted)
        custom_row.addWidget(submit_btn)

        layout.addLayout(custom_row)

    def _on_custom_submitted(self) -> None:
        text = self._custom_input.text().strip()
        if text:
            self.answered.emit(text)

    def focus_input(self) -> None:
        self._custom_input.setFocus()
