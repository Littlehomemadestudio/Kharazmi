"""
NaturalLanguageInput — a top-bar input that parses natural-language
event descriptions.

Type something like:
  "Lunch with Sarah tomorrow at 1 PM"
  "Meeting every Monday at 10am"
  "Doctor appointment next Friday 3pm"

Press Enter → the parser extracts title/time/recurrence/attendees
and opens the EventEditorDialog pre-filled with the parsed values.
"""
from __future__ import annotations

from datetime import datetime
from typing import Optional

from PySide6.QtCore import Qt, Signal, QTimer
from PySide6.QtGui import QFont, QColor, QKeyEvent
from PySide6.QtWidgets import (
    QWidget, QHBoxLayout, QLabel, QLineEdit, QPushButton, QFrame,
    QCompleter,
)

from ...calendar import parse, ParsedEvent
from ...core.shamsi import ShamsiDate
from ..theme import Palette


# Suggestion examples shown in the completer
NL_EXAMPLES = [
    "Lunch with Sarah tomorrow at 1 PM",
    "Meeting every Monday at 10am",
    "Doctor appointment next Friday 3pm",
    "Call mom today at 6pm",
    "Standup daily at 9am",
    "Birthday party on 1403/05/14",
    "Coffee with John and Jane tomorrow afternoon",
    "Vacation for 2 weeks",
    "Focus time tomorrow morning for 3 hours",
    "Dentist appointment next Wednesday 2pm",
    "Team review every Friday at 4pm",
    "Lunch at noon",
    "Pick up kids at 3pm",
]


class NaturalLanguageInput(QFrame):
    """Natural-language event creation bar."""

    eventParsed = Signal(ParsedEvent)

    def __init__(self, parent: QWidget = None) -> None:
        super().__init__(parent)
        self.setObjectName("nlInput")
        self.setStyleSheet(f"""
            QFrame#nlInput {{
                background-color: {Palette.BG_TERTIARY};
                border: 1px solid {Palette.BORDER_GOLD};
                border-radius: 6px;
            }}
        """)
        self.setFixedHeight(44)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(12, 6, 12, 6)
        layout.setSpacing(8)

        # Sparkle icon
        icon = QLabel("✦")
        icon.setStyleSheet(
            f"color: {Palette.GOLD_BRIGHT}; font-size: 16px; font-weight: bold;"
        )
        layout.addWidget(icon)

        # Input
        self._input = QLineEdit()
        self._input.setPlaceholderText(
            "Describe your event...  e.g. \"Lunch with Sarah tomorrow at 1 PM\""
        )
        self._input.setStyleSheet(f"""
            QLineEdit {{
                background: transparent;
                color: {Palette.GOLD_BRIGHT};
                border: none;
                font-size: 13px;
                font-family: 'Inter', sans-serif;
            }}
        """)
        self._input.returnPressed.connect(self._on_submit)
        layout.addWidget(self._input, stretch=1)

        # Submit button
        self._submit_btn = QPushButton("Create")
        self._submit_btn.setProperty("variant", "primary")
        self._submit_btn.clicked.connect(self._on_submit)
        layout.addWidget(self._submit_btn)

        # Suggestion completer
        self._completer = QCompleter(NL_EXAMPLES)
        self._completer.setCaseSensitivity(Qt.CaseInsensitive)
        self._completer.setFilterMode(Qt.MatchContains)
        self._input.setCompleter(self._completer)

    def _on_submit(self) -> None:
        text = self._input.text().strip()
        if not text:
            return
        parsed = parse(text, now=datetime.now())
        if parsed.title and parsed.start:
            self.eventParsed.emit(parsed)
            self._input.clear()
        else:
            # Show placeholder feedback
            self._input.setPlaceholderText("Couldn't parse — try \"Lunch tomorrow at 1pm\"")
            QTimer.singleShot(3000, lambda: self._input.setPlaceholderText(
                "Describe your event...  e.g. \"Lunch with Sarah tomorrow at 1 PM\""
            ))

    def focus_input(self) -> None:
        self._input.setFocus()
