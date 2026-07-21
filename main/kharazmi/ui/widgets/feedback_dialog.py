"""
FeedbackDialog — a simple dialog for collecting user feedback.

Displays a text area and "Submit" button. On submit, the feedback
is stored locally at ~/.rask/feedback.json and a thank-you message
is shown. Styled consistent with the app's gold-on-dark theme.
"""
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel,
    QTextEdit, QPushButton, QMessageBox,
)

from ..theme import Palette


FEEDBACK_PATH = Path.home() / ".rask" / "feedback.json"


def _load_feedback() -> list[dict]:
    """Read existing feedback entries from disk."""
    try:
        if FEEDBACK_PATH.exists():
            return json.loads(FEEDBACK_PATH.read_text(encoding="utf-8"))
    except Exception:
        pass
    return []


def _save_feedback(entries: list[dict]) -> None:
    """Persist feedback entries to disk."""
    try:
        FEEDBACK_PATH.parent.mkdir(parents=True, exist_ok=True)
        FEEDBACK_PATH.write_text(
            json.dumps(entries, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
    except Exception:
        pass


class FeedbackDialog(QDialog):
    """Gold-on-dark feedback dialog with text area and submit button."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("💡 Feedback")
        self.setMinimumWidth(420)
        self.setMinimumHeight(320)
        self.setStyleSheet(
            f"background-color: {Palette.BG_SECONDARY}; "
            f"color: {Palette.TEXT_PRIMARY};"
        )

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 16, 20, 16)
        layout.setSpacing(12)

        # Title
        title = QLabel("We'd love to hear from you!")
        title.setStyleSheet(
            f"color: {Palette.GOLD_BRIGHT}; font-size: 16px; "
            f"font-weight: bold; border: none;"
        )
        layout.addWidget(title)

        # Subtitle
        subtitle = QLabel(
            "Share your thoughts, suggestions, or bug reports. "
            "Your feedback helps us improve Rask."
        )
        subtitle.setWordWrap(True)
        subtitle.setStyleSheet(
            f"color: {Palette.TEXT_SECONDARY}; font-size: 12px; border: none;"
        )
        layout.addWidget(subtitle)

        # Text area
        self._text_area = QTextEdit()
        self._text_area.setPlaceholderText("Type your feedback here…")
        self._text_area.setStyleSheet(f"""
            QTextEdit {{
                background-color: {Palette.BG_TERTIARY};
                color: {Palette.TEXT_PRIMARY};
                border: 1px solid {Palette.BORDER_GOLD};
                border-radius: 4px;
                padding: 10px;
                font-size: 13px;
            }}
            QTextEdit:focus {{
                border: 1px solid {Palette.GOLD_BRIGHT};
            }}
        """)
        layout.addWidget(self._text_area, stretch=1)

        # Button row
        btn_row = QHBoxLayout()
        btn_row.addStretch()

        cancel_btn = QPushButton("Cancel")
        cancel_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: {Palette.BG_TERTIARY};
                color: {Palette.TEXT_SECONDARY};
                border: 1px solid {Palette.BORDER_NORMAL};
                border-radius: 4px;
                padding: 8px 20px;
                font-size: 13px;
            }}
            QPushButton:hover {{
                background-color: {Palette.BG_ELEVATED};
                color: {Palette.TEXT_PRIMARY};
            }}
        """)
        cancel_btn.clicked.connect(self.reject)
        btn_row.addWidget(cancel_btn)

        submit_btn = QPushButton("Submit")
        submit_btn.setProperty("variant", "primary")
        submit_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: {Palette.GOLD_PRIMARY};
                color: {Palette.TEXT_ON_GOLD};
                border: 1px solid {Palette.GOLD_DEEP};
                border-radius: 4px;
                padding: 8px 24px;
                font-size: 13px;
                font-weight: bold;
            }}
            QPushButton:hover {{
                background-color: {Palette.GOLD_BRIGHT};
            }}
        """)
        submit_btn.clicked.connect(self._on_submit)
        btn_row.addWidget(submit_btn)

        layout.addLayout(btn_row)

    def _on_submit(self) -> None:
        text = self._text_area.toPlainText().strip()
        if not text:
            return

        # Save to local JSON
        entries = _load_feedback()
        entries.append({
            "timestamp": datetime.now().isoformat(),
            "feedback": text,
        })
        _save_feedback(entries)

        self.accept()

        # Show thank you message
        QMessageBox.information(
            None,
            "Thank you! 🙏",
            "Your feedback has been saved. Thank you for helping us improve Rask!",
        )
