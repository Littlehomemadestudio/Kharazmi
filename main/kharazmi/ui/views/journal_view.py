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
from PySide6.QtGui import QFont, QColor, QPainter, QPen, QBrush, QPaintEvent
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QFrame, QScrollArea,
    QListWidget, QListWidgetItem, QPushButton, QLineEdit,
    QMessageBox, QInputDialog, QSizePolicy,
)

from ...ai import JournalStore, JournalEntry, Route
from ...core.shamsi import ShamsiDate, format_shamsi
from ..theme import Palette


class _JournalIcon(QWidget):
    """A simple hand-drawn journal/notebook icon rendered with QPainter."""

    def __init__(self, parent: QWidget = None) -> None:
        super().__init__(parent)
        self.setFixedSize(120, 140)
        self.setStyleSheet("background: transparent;")

    def paintEvent(self, event: QPaintEvent) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing, True)
        try:
            # Notebook body
            body_rect = self.rect().adjusted(20, 10, -10, -10)
            p.setPen(QPen(QColor(Palette.BORDER_GOLD), 2))
            p.setBrush(QColor(Palette.BG_TERTIARY))
            p.drawRoundedRect(body_rect, 8, 8)

            # Spine
            spine_rect = body_rect.adjusted(0, 0, -body_rect.width() + 14, 0)
            p.setPen(Qt.NoPen)
            p.setBrush(QColor(Palette.GOLD_DEEP))
            p.drawRoundedRect(spine_rect, 4, 4)

            # Gold accent line on spine
            p.setPen(QPen(QColor(Palette.GOLD_PRIMARY), 2))
            spine_center_x = spine_rect.x() + spine_rect.width() // 2
            p.drawLine(spine_center_x, body_rect.y() + 16, spine_center_x, body_rect.bottom() - 16)

            # Page lines
            p.setPen(QPen(QColor(Palette.BORDER_NORMAL), 1))
            for i in range(5):
                y = body_rect.y() + 28 + i * 18
                if y < body_rect.bottom() - 12:
                    p.drawLine(body_rect.x() + 24, y, body_rect.right() - 8, y)

            # Small gold star in the corner
            p.setPen(Qt.NoPen)
            p.setBrush(QColor(Palette.GOLD_BRIGHT))
            star_cx = body_rect.right() - 18
            star_cy = body_rect.y() + 20
            from PySide6.QtGui import QPolygonF
            from PySide6.QtCore import QPointF
            star = QPolygonF()
            import math
            for i in range(10):
                angle = math.pi / 2 + i * math.pi / 5
                r = 7 if i % 2 == 0 else 3
                star.append(QPointF(star_cx + r * math.cos(angle), star_cy - r * math.sin(angle)))
            p.drawPolygon(star)
        finally:
            p.end()


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
            f"color: {Palette.TEXT_SECONDARY}; font-size: 10px; "
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
                f"color: {Palette.TEXT_SECONDARY}; font-size: 11px; font-style: italic;"
            )
            notes_label.setWordWrap(True)
            layout.addWidget(notes_label)

        # Action row
        actions = QHBoxLayout()
        actions.addStretch()
        edit_btn = QPushButton("Edit notes")
        edit_btn.setStyleSheet(
            f"background: transparent; color: {Palette.TEXT_SECONDARY}; "
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
    goToPlannerRequested = Signal()  # Navigate to AI Planner tab

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

        self._subtitle = QLabel(
            "هر هدفی که با رَسک برنامه‌ریزی کنید اینجا ذخیره می‌شود — تاریخچه کامل مسیرهای ساخته‌شده با هوش مصنوعی."
        )
        self._subtitle.setStyleSheet(f"color: {Palette.TEXT_SECONDARY}; font-size: 12px;")
        self._subtitle.setWordWrap(True)
        layout.addWidget(self._subtitle)

        # Search
        self._search = QLineEdit()
        self._search.setPlaceholderText("🔍  جستجوی یادداشت‌ها...")
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
        self._scroll = QScrollArea()
        self._scroll.setWidgetResizable(True)
        self._scroll.setFrameShape(QFrame.NoFrame)
        self._scroll.setStyleSheet("QScrollArea { background: transparent; border: none; }")

        self._container = QWidget()
        self._container.setStyleSheet("background: transparent;")
        self._list_layout = QVBoxLayout(self._container)
        self._list_layout.setContentsMargins(0, 0, 0, 0)
        self._list_layout.setSpacing(8)
        self._list_layout.addStretch()
        self._scroll.setWidget(self._container)
        layout.addWidget(self._scroll, stretch=1)

        self.refresh()

    def refresh(self) -> None:
        # Clear (preserve stretch)
        while self._list_layout.count() > 1:
            item = self._list_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        query = self._search.text().strip()
        entries = self.journal.search(query) if query else self.journal.all()
        has_entries = len(self.journal) > 0

        # Show/hide search bar based on whether there are any entries at all
        self._search.setVisible(has_entries)

        if not entries:
            # Build a centered empty state widget
            empty_widget = QWidget()
            empty_widget.setStyleSheet("background: transparent;")
            empty_layout = QVBoxLayout(empty_widget)
            empty_layout.setContentsMargins(0, 0, 0, 0)
            empty_layout.setSpacing(16)
            empty_layout.setAlignment(Qt.AlignCenter)

            if not has_entries and not query:
                # ---- Completely empty journal (no entries at all) ----
                # Journal icon
                icon = _JournalIcon()
                icon_layout = QHBoxLayout()
                icon_layout.addStretch()
                icon_layout.addWidget(icon)
                icon_layout.addStretch()
                empty_layout.addLayout(icon_layout)

                # Main empty text
                empty_title = QLabel("هنوز یادداشتی ندارید")
                empty_title.setAlignment(Qt.AlignCenter)
                empty_title.setStyleSheet(f"""
                    color: {Palette.TEXT_PRIMARY};
                    font-size: 18px;
                    font-weight: bold;
                """)
                empty_title_layout = QHBoxLayout()
                empty_title_layout.addStretch()
                empty_title_layout.addWidget(empty_title)
                empty_title_layout.addStretch()
                empty_layout.addLayout(empty_title_layout)

                # Description
                empty_desc = QLabel("هدفتان را در برنامه‌ریز هوش مصنوعی شرح دهید تا اولین مسیر شما ساخته شود")
                empty_desc.setAlignment(Qt.AlignCenter)
                empty_desc.setWordWrap(True)
                empty_desc.setMaximumWidth(400)
                empty_desc.setStyleSheet(f"""
                    color: {Palette.TEXT_SECONDARY};
                    font-size: 13px;
                """)
                desc_layout = QHBoxLayout()
                desc_layout.addStretch()
                desc_layout.addWidget(empty_desc)
                desc_layout.addStretch()
                empty_layout.addLayout(desc_layout)

                empty_layout.addSpacing(8)

                # CTA button
                cta_btn = QPushButton("شروع برنامه‌ریزی با هوش مصنوعی")
                cta_btn.setCursor(Qt.PointingHandCursor)
                cta_btn.setProperty("variant", "primary")
                cta_btn.setStyleSheet(f"""
                    QPushButton {{
                        background-color: {Palette.GOLD_PRIMARY};
                        color: {Palette.TEXT_ON_GOLD};
                        border: 1px solid {Palette.GOLD_DEEP};
                        border-radius: 8px;
                        padding: 12px 28px;
                        font-size: 14px;
                        font-weight: bold;
                    }}
                    QPushButton:hover {{
                        background-color: {Palette.GOLD_BRIGHT};
                        border: 1px solid {Palette.GOLD_PRIMARY};
                    }}
                    QPushButton:pressed {{
                        background-color: {Palette.GOLD_DEEP};
                    }}
                """)
                cta_btn.clicked.connect(self.goToPlannerRequested.emit)
                cta_layout = QHBoxLayout()
                cta_layout.addStretch()
                cta_layout.addWidget(cta_btn)
                cta_layout.addStretch()
                empty_layout.addLayout(cta_layout)
            else:
                # ---- Search returned no results ----
                empty_label = QLabel("نتیجه‌ای یافت نشد")
                empty_label.setAlignment(Qt.AlignCenter)
                empty_label.setStyleSheet(f"""
                    color: {Palette.TEXT_SECONDARY};
                    font-size: 14px;
                    padding: 40px;
                """)
                label_layout = QHBoxLayout()
                label_layout.addStretch()
                label_layout.addWidget(empty_label)
                label_layout.addStretch()
                empty_layout.addLayout(label_layout)

            # Wrap in a layout that vertically centers the content
            wrapper = QVBoxLayout()
            wrapper.addStretch()
            wrapper.addWidget(empty_widget)
            wrapper.addStretch()

            # We need a container widget for the wrapper layout
            centered = QWidget()
            centered.setStyleSheet("background: transparent;")
            centered_layout = QVBoxLayout(centered)
            centered_layout.setContentsMargins(0, 0, 0, 0)
            centered_layout.setSpacing(0)
            centered_layout.addStretch()
            centered_layout.addWidget(empty_widget)
            centered_layout.addStretch()

            self._list_layout.insertWidget(0, centered)
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
