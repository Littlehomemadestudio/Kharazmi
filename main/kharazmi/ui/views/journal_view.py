"""
JournalView — list of all AI-generated routes saved by the user.

Shows each journal entry with:
  - Goal
  - Timestamp (Shamsi)
  - Success probability
  - Number of steps
  - Notes

Click an entry to load its route into the AI planner view.
"""
from __future__ import annotations

from typing import Optional

from PySide6.QtCore import Qt, Signal, QTimer
from PySide6.QtGui import QFont, QColor
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QFrame, QScrollArea,
    QListWidget, QListWidget, QListWidgetItem, QPushButton, QLineEdit,
    QMessageBox, QInputDialog, QSizePolicy,
)

from ...ai import JournalStore, JournalEntry, Route
from ...core.shamsi import ShamsiDate, format_shamsi
from ..theme import Palette


class JournalEntryCard(QFrame):
    """A card representing a single journal entry."""
    clicked = Signal(str)  # entry_id
    deleteRequested = Signal(str)  # entry_id
    editNotesRequested = Signal(str)  # entry_id

    def __init__(self, entry: JournalEntry, parent: QWidget = None) -> None:
        super().__init__(parent)
        self.entry = entry
        self.setCursor(Qt.PointingHandCursor)
        self.setObjectName("journalCard")
        self.setStyleSheet(f"""
            QFrame#journalCard {{
                background-color: {Palette.BG_TERTIARY};
                border: 1px solid {Palette.BORDER_NORMAL};
                border-left: 3px solid {Palette.GOLD_PRIMARY};
                border-radius: 4px;
            }}
            QFrame#journalCard:hover {{
                background-color: {Palette.BG_ELEVATED};
                border: 1px solid {Palette.GOLD_PRIMARY};
                border-left: 3px solid {Palette.GOLD_BRIGHT};
            }}
        """)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 10, 12, 10)
        layout.setSpacing(4)

        # Header row: timestamp + success %
        header = QHBoxLayout()
        ts_label = QLabel(format_shamsi(
            _parse_iso(entry.timestamp), include_time=True
        ) if entry.timestamp else "—")
        ts_label.setStyleSheet(
            f"color: {Palette.TEXT_TERTIARY}; font-size: 10px; "
            f"font-family: 'JetBrains Mono', monospace;"
        )
        header.addWidget(ts_label)
        header.addStretch()

        if entry.route:
            pct = entry.route.overall_success_probability
            pct_color = Palette.GOLD_BRIGHT if pct > 0.7 else (Palette.GOLD_PRIMARY if pct > 0.4 else Palette.STATUS_BLOCKED)
            pct_label = QLabel(f"{pct:.0%} success")
            pct_label.setStyleSheet(
                f"color: {pct_color}; font-size: 11px; font-weight: bold; "
                f"font-family: 'JetBrains Mono', monospace; "
                f"background-color: {Palette.BG_DEEPEST}; padding: 2px 8px; "
                f"border-radius: 8px;"
            )
            header.addWidget(pct_label)
        layout.addLayout(header)

        # Goal
        goal_label = QLabel(entry.user_goal)
        goal_label.setStyleSheet(
            f"color: {Palette.TEXT_PRIMARY}; font-size: 13px; font-weight: bold;"
        )
        goal_label.setWordWrap(True)
        layout.addWidget(goal_label)

        # Step count
        if entry.route:
            steps_label = QLabel(
                f"{len(entry.route.steps)} steps · {entry.route.total_duration_minutes} min total"
            )
            steps_label.setStyleSheet(
                f"color: {Palette.TEXT_SECONDARY}; font-size: 11px;"
            )
            layout.addWidget(steps_label)

        # Notes
        if entry.notes:
            notes_label = QLabel(f"📝 {entry.notes}")
            notes_label.setStyleSheet(
                f"color: {Palette.TEXT_TERTIARY}; font-size: 11px; font-style: italic;"
            )
            notes_label.setWordWrap(True)
            layout.addWidget(notes_label)

        # Action row
        actions = QHBoxLayout()
        actions.addStretch()
        edit_btn = QPushButton("Edit notes")
        edit_btn.setStyleSheet(
            f"background: transparent; color: {Palette.TEXT_TERTIARY}; "
            f"border: none; padding: 2px 8px; font-size: 10px;"
        )
        edit_btn.setCursor(Qt.PointingHandCursor)
        edit_btn.clicked.connect(lambda: self.editNotesRequested.emit(entry.id))
        actions.addWidget(edit_btn)
        del_btn = QPushButton("Delete")
        del_btn.setStyleSheet(
            f"background: transparent; color: {Palette.STATUS_BLOCKED}; "
            f"border: none; padding: 2px 8px; font-size: 10px;"
        )
        del_btn.setCursor(Qt.PointingHandCursor)
        del_btn.clicked.connect(lambda: self.deleteRequested.emit(entry.id))
        actions.addWidget(del_btn)
        layout.addLayout(actions)

    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.LeftButton:
            self.clicked.emit(self.entry.id)
        super().mousePressEvent(event)


def _parse_iso(s: str):
    """Parse an ISO timestamp string into a datetime."""
    from datetime import datetime
    try:
        return datetime.fromisoformat(s)
    except (ValueError, TypeError):
        return None


class JournalView(QWidget):
    """The journal screen — list of past AI-generated routes."""
    entrySelected = Signal(object)  # JournalEntry

    def __init__(self, journal: JournalStore, parent: QWidget = None) -> None:
        super().__init__(parent)
        self.journal = journal
        self.setStyleSheet(f"background-color: {Palette.BG_PRIMARY};")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(12)

        # Header
        title = QLabel("JOURNAL")
        title.setStyleSheet(
            f"color: {Palette.GOLD_BRIGHT}; font-size: 22px; "
            f"font-weight: bold; letter-spacing: 2px;"
        )
        layout.addWidget(title)

        subtitle = QLabel(
            "Every goal you plan with Rask is saved here — your complete history of AI-built routes."
        )
        subtitle.setStyleSheet(f"color: {Palette.TEXT_TERTIARY}; font-size: 12px;")
        subtitle.setWordWrap(True)
        layout.addWidget(subtitle)

        # Search
        self._search = QLineEdit()
        self._search.setPlaceholderText("🔍  Search journal entries…")
        self._search.setStyleSheet(f"""
            QLineEdit {{
                background-color: {Palette.BG_TERTIARY};
                color: {Palette.TEXT_PRIMARY};
                border: 1px solid {Palette.BORDER_NORMAL};
                border-radius: 4px;
                padding: 8px 14px;
                font-size: 12px;
            }}
            QLineEdit:focus {{
                border: 1px solid {Palette.GOLD_PRIMARY};
            }}
        """)
        self._search.textChanged.connect(lambda _: self.refresh())
        layout.addWidget(self._search)

        # List
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setStyleSheet("QScrollArea { background: transparent; border: none; }")

        container = QWidget()
        self._list_layout = QVBoxLayout(container)
        self._list_layout.setContentsMargins(0, 0, 0, 0)
        self._list_layout.setSpacing(8)
        self._list_layout.addStretch()
        scroll.setWidget(container)
        layout.addWidget(scroll, stretch=1)

        self.refresh()

    def refresh(self) -> None:
        # Clear (preserve stretch)
        while self._list_layout.count() > 1:
            item = self._list_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        query = self._search.text().strip()
        entries = self.journal.search(query) if query else self.journal.all()

        if not entries:
            empty = QLabel(
                "No journal entries yet.\n\nDescribe a goal in the AI Planner tab to create your first route."
                if not query else "No entries match your search."
            )
            empty.setStyleSheet(
                f"color: {Palette.TEXT_TERTIARY}; font-size: 13px; "
                f"padding: 40px; font-style: italic;"
            )
            empty.setAlignment(Qt.AlignCenter)
            self._list_layout.insertWidget(0, empty)
            return

        for entry in entries:
            card = JournalEntryCard(entry)
            card.clicked.connect(self._on_entry_clicked)
            card.deleteRequested.connect(self._on_delete)
            card.editNotesRequested.connect(self._on_edit_notes)
            self._list_layout.insertWidget(self._list_layout.count() - 1, card)

    def _on_entry_clicked(self, entry_id: str) -> None:
        entry = self.journal.get(entry_id)
        if entry is not None:
            self.entrySelected.emit(entry)

    def _on_delete(self, entry_id: str) -> None:
        reply = QMessageBox.question(
            self, "Delete Entry",
            "Delete this journal entry? This cannot be undone.",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No,
        )
        if reply == QMessageBox.Yes:
            self.journal.delete(entry_id)
            self.refresh()

    def _on_edit_notes(self, entry_id: str) -> None:
        entry = self.journal.get(entry_id)
        if entry is None:
            return
        text, ok = QInputDialog.getMultiLineText(
            self, "Edit Notes",
            "Notes for this journal entry:",
            entry.notes,
        )
        if ok:
            self.journal.update_notes(entry_id, text)
            self.refresh()
