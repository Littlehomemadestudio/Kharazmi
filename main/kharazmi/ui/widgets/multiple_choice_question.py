"""
MultipleChoiceQuestionWidget — fully responsive question panel for the AI planner.

Shows a question with option buttons that fully adapt to text length:
  - Short options: horizontal row of compact buttons
  - Long options: vertical stack of full-width clickable cards with word wrap
  - Mixed: smart layout that adapts per-option
  - Never breaks, never clips, always readable

Also supports 4-6 options + custom "Other..." input.

NO custom QPainter — uses QLabel for word-wrap which works perfectly natively.
"""
from __future__ import annotations

from typing import Optional

from PySide6.QtCore import Qt, Signal, QSize
from PySide6.QtGui import QFont, QFontMetrics, QCursor
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QLineEdit,
    QFrame, QSizePolicy, QScrollArea, QApplication,
)

from ...ai import MultipleChoiceQuestion
from ..theme import Palette


# ──────────────────────────── Helper ──────────────────────────────────

def _estimate_text_width(text: str, font: QFont) -> int:
    """Estimate the pixel width needed to render text without wrapping."""
    fm = QFontMetrics(font)
    return fm.horizontalAdvance(text)


def _is_long_option(text: str, font: QFont, threshold: int = 80) -> bool:
    """Return True if the option text is long enough to need its own row."""
    return _estimate_text_width(text, font) > threshold


# ──────────────────────────── Option Card ─────────────────────────────

class _OptionCard(QFrame):
    """
    A clickable card for an option that natively supports word wrap.

    Uses a QFrame + QLabel layout instead of QPushButton, so text
    wrapping works perfectly without any custom QPainter code.
    Emits clicked(option_text) when clicked.
    """
    clicked = Signal(str)

    def __init__(self, label: str, text: str, parent=None) -> None:
        super().__init__(parent)
        self._label = label
        self._option_text = text
        self._is_long = len(text) > 30 or '\n' in text
        self._hovered = False
        self._pressed = False

        self.setCursor(Qt.PointingHandCursor)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Minimum)
        self.setObjectName("optionCard")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 8, 10, 8)
        layout.setSpacing(0)

        # Build the display text
        display_text = f"<b style='color:{Palette.GOLD_BRIGHT}'>{label}.</b>  {text}"

        self._text_label = QLabel(display_text)
        self._text_label.setWordWrap(True)
        self._text_label.setTextFormat(Qt.RichText)
        self._text_label.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Minimum)
        self._text_label.setTextInteractionFlags(Qt.NoTextInteraction)

        if self._is_long:
            self._text_label.setStyleSheet(f"""
                color: {Palette.TEXT_PRIMARY};
                font-size: 12px;
                background: transparent;
                border: none;
                line-height: 1.4;
            """)
        else:
            self._text_label.setStyleSheet(f"""
                color: {Palette.TEXT_PRIMARY};
                font-size: 12px;
                background: transparent;
                border: none;
            """)

        layout.addWidget(self._text_label)
        self._apply_style()

    def _apply_style(self) -> None:
        if self._is_long:
            if self._pressed:
                bg = Palette.GOLD_MUTED
                border_left = Palette.GOLD_PRIMARY
            elif self._hovered:
                bg = Palette.BG_SELECTED
                border_left = Palette.GOLD_PRIMARY
            else:
                bg = Palette.BG_ELEVATED
                border_left = Palette.GOLD_DEEP

            self.setStyleSheet(f"""
                QFrame#optionCard {{
                    background-color: {bg};
                    border: 1px solid {Palette.BORDER_NORMAL};
                    border-left: 3px solid {border_left};
                    border-radius: 4px;
                }}
            """)
        else:
            if self._pressed:
                bg = Palette.GOLD_MUTED
                border = Palette.GOLD_PRIMARY
            elif self._hovered:
                bg = Palette.BG_SELECTED
                border = Palette.GOLD_PRIMARY
            else:
                bg = Palette.BG_ELEVATED
                border = Palette.BORDER_NORMAL

            self.setStyleSheet(f"""
                QFrame#optionCard {{
                    background-color: {bg};
                    border: 1px solid {border};
                    border-radius: 4px;
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

    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.LeftButton:
            self._pressed = True
            self._apply_style()

    def mouseReleaseEvent(self, event) -> None:
        if event.button() == Qt.LeftButton and self._pressed:
            self._pressed = False
            self._hovered = False
            self._apply_style()
            self.clicked.emit(self._option_text)
        else:
            self._pressed = False
            self._apply_style()

    def sizeHint(self) -> QSize:
        fm = QFontMetrics(QFont("Inter", 12))
        if self._is_long:
            # Estimate height for wrapped text at ~300px width
            display = f"{self._label}.  {self._option_text}"
            rect = fm.boundingRect(0, 0, 300, 0, Qt.TextWordWrap, display)
            return QSize(max(200, rect.width()), rect.height() + 24)
        return QSize(160, 36)

    def minimumSizeHint(self) -> QSize:
        if self._is_long:
            return QSize(120, 36)
        return QSize(80, 30)


# ──────────────────────────── Compact Option Button ───────────────────

class _CompactOptionButton(QPushButton):
    """
    A QPushButton for short option text — no custom painting needed.
    Text is set directly and QPushButton handles it natively.
    """

    def __init__(self, label: str, text: str, parent=None) -> None:
        super().__init__(parent)
        self._label = label
        self._option_text = text

        self.setCursor(Qt.PointingHandCursor)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Minimum)

        self.setText(f"{label}.  {text}")
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


# ──────────────────────────── Question Widget ─────────────────────────

class MultipleChoiceQuestionWidget(QFrame):
    """
    A single multiple-choice question with adaptive layout.

    - Questions of any length are fully displayed with word wrap
    - Hints wrap naturally
    - Options adapt: short → compact buttons, long → full-width cards with word wrap
    - Mixed short/long → vertical stack for consistency
    - Custom input always wraps to full width
    - Never breaks, never clips, always readable
    - NO custom QPainter — uses native QLabel word wrap
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

        if has_long or len(opts) > 4:
            # ── Vertical stack: one option per row, full width ──
            for i, opt in enumerate(opts):
                is_this_long = _is_long_option(opt, font, 80) or len(opt) > 30
                if is_this_long:
                    card = _OptionCard(str(i + 1), opt)
                    card.clicked.connect(lambda o=opt: self.answered.emit(o))
                    layout.addWidget(card)
                else:
                    btn = _CompactOptionButton(str(i + 1), opt)
                    btn.clicked.connect(lambda _=False, o=opt: self.answered.emit(o))
                    layout.addWidget(btn)
        else:
            # ── Horizontal rows: 2 per row for short options ──
            row = None
            for i, opt in enumerate(opts):
                if i % 2 == 0:
                    row = QHBoxLayout()
                    row.setSpacing(6)
                btn = _CompactOptionButton(str(i + 1), opt)
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
