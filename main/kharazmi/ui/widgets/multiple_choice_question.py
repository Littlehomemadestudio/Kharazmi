"""
MultipleChoiceQuestionWidget — shows a question with 4 option buttons
plus an "Other..." input for custom answers.
"""
from __future__ import annotations

from typing import Optional

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QLineEdit,
    QFrame, QSizePolicy,
)

from ...ai import MultipleChoiceQuestion
from ..theme import Palette


class MultipleChoiceQuestionWidget(QFrame):
    """A single multiple-choice question with 4 options + custom input."""

    answered = Signal(str)  # the chosen answer (option text or custom)

    def __init__(self, question: MultipleChoiceQuestion, index: int,
                 parent: QWidget = None) -> None:
        super().__init__(parent)
        self.question = question
        self._index = index
        self._custom_mode = False

        self.setStyleSheet(f"""
            QFrame {{
                background-color: {Palette.BG_TERTIARY};
                border: 1px solid {Palette.BORDER_NORMAL};
                border-left: 3px solid {Palette.GOLD_PRIMARY};
                border-radius: 6px;
            }}
        """)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 10, 12, 10)
        layout.setSpacing(6)

        # Question header
        q_label = QLabel(f"<b>Q{index + 1}.</b>  {question.question}")
        q_label.setStyleSheet(
            f"color: {Palette.TEXT_PRIMARY}; font-size: 12px; background: transparent; border: none;"
        )
        q_label.setWordWrap(True)
        q_label.setTextFormat(Qt.RichText)
        layout.addWidget(q_label)

        # Hint
        if question.hint:
            hint_label = QLabel(question.hint)
            hint_label.setStyleSheet(
                f"color: {Palette.TEXT_TERTIARY}; font-size: 10px; "
                f"font-style: italic; background: transparent; border: none;"
            )
            hint_label.setWordWrap(True)
            layout.addWidget(hint_label)

        # Options row
        options_row = QHBoxLayout()
        options_row.setSpacing(4)
        for i, opt in enumerate(question.options[:4]):
            btn = QPushButton(f"{i + 1}.  {opt}")
            btn.setStyleSheet(f"""
                QPushButton {{
                    background-color: {Palette.BG_ELEVATED};
                    color: {Palette.TEXT_PRIMARY};
                    border: 1px solid {Palette.BORDER_NORMAL};
                    border-radius: 4px;
                    padding: 8px 12px;
                    font-size: 11px;
                    text-align: left;
                }}
                QPushButton:hover {{
                    background-color: {Palette.BG_SELECTED};
                    border: 1px solid {Palette.GOLD_PRIMARY};
                    color: {Palette.GOLD_BRIGHT};
                }}
            """)
            btn.clicked.connect(lambda _=False, o=opt: self.answered.emit(o))
            options_row.addWidget(btn, stretch=1)
        layout.addLayout(options_row)

        # Custom input row
        custom_row = QHBoxLayout()
        custom_row.setSpacing(4)
        self._custom_input = QLineEdit()
        self._custom_input.setPlaceholderText("Other…  (type your answer and press Enter)")
        self._custom_input.setStyleSheet(f"""
            QLineEdit {{
                background-color: {Palette.BG_ELEVATED};
                color: {Palette.TEXT_PRIMARY};
                border: 1px solid {Palette.BORDER_NORMAL};
                border-radius: 4px;
                padding: 6px 10px;
                font-size: 11px;
            }}
            QLineEdit:focus {{
                border: 1px solid {Palette.GOLD_PRIMARY};
            }}
        """)
        self._custom_input.returnPressed.connect(self._on_custom_submitted)
        custom_row.addWidget(self._custom_input, stretch=1)

        submit_btn = QPushButton("Submit")
        submit_btn.setProperty("variant", "primary")
        submit_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: {Palette.GOLD_PRIMARY};
                color: {Palette.TEXT_ON_GOLD};
                border: none;
                border-radius: 4px;
                padding: 6px 14px;
                font-size: 11px;
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
