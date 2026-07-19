"""
CalendarSettingsDialog — create/edit/delete calendars.

Lists all calendars; lets the user create new ones, rename, recolor,
or delete (non-default, non-readonly).
"""
from __future__ import annotations

from typing import Optional

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QFont, QColor
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, QPushButton,
    QFrame, QListWidget, QListWidgetItem, QComboBox, QInputDialog,
    QMessageBox, QColorDialog, QScrollArea, QWidget, QSizePolicy,
)

from ...calendar import CalendarStore, Calendar, CALENDAR_COLORS
from ..theme import Palette


class CalendarSettingsDialog(QDialog):
    """Manage calendars."""

    def __init__(self, store: CalendarStore, parent=None) -> None:
        super().__init__(parent)
        self.store = store
        self.setWindowTitle("Manage Calendars")
        self.setMinimumSize(560, 460)
        self.setStyleSheet(f"background-color: {Palette.BG_PRIMARY};")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(12)

        title = QLabel("CALENDAR MANAGEMENT")
        title.setStyleSheet(
            f"color: {Palette.GOLD_PRIMARY}; font-size: 11px; "
            f"font-weight: bold; letter-spacing: 2px;"
        )
        layout.addWidget(title)

        # List
        self._list = QListWidget()
        self._list.setStyleSheet(f"""
            QListWidget {{
                background-color: {Palette.BG_TERTIARY};
                border: 1px solid {Palette.BORDER_NORMAL};
                border-radius: 4px;
            }}
            QListWidget::item {{ padding: 8px; }}
            QListWidget::item:selected {{
                background-color: {Palette.BG_SELECTED};
                color: {Palette.GOLD_BRIGHT};
            }}
        """)
        self._list.currentRowChanged.connect(self._on_selection)
        layout.addWidget(self._list, stretch=1)

        # Edit panel
        edit_panel = QFrame()
        edit_panel.setStyleSheet(f"background-color: {Palette.BG_TERTIARY}; border: 1px solid {Palette.BORDER_SUBTLE}; border-radius: 4px;")
        edit_layout = QVBoxLayout(edit_panel)
        edit_layout.setContentsMargins(12, 12, 12, 12)
        edit_layout.setSpacing(8)

        # Name
        name_row = QHBoxLayout()
        name_row.addWidget(QLabel("Name:"))
        self._name_edit = QLineEdit()
        name_row.addWidget(self._name_edit, stretch=1)
        edit_layout.addLayout(name_row)

        # Description
        desc_row = QHBoxLayout()
        desc_row.addWidget(QLabel("Description:"))
        self._desc_edit = QLineEdit()
        desc_row.addWidget(self._desc_edit, stretch=1)
        edit_layout.addLayout(desc_row)

        # Color
        color_row = QHBoxLayout()
        color_row.addWidget(QLabel("Color:"))
        for hex_color in CALENDAR_COLORS:
            btn = QPushButton()
            btn.setFixedSize(24, 24)
            btn.setStyleSheet(
                f"background-color: {hex_color}; border: 1px solid {Palette.BORDER_NORMAL}; border-radius: 4px;"
            )
            btn.clicked.connect(lambda _=False, c=hex_color: self._set_color(c))
            color_row.addWidget(btn)
        color_row.addStretch()
        self._custom_color_btn = QPushButton("Custom...")
        self._custom_color_btn.clicked.connect(self._pick_custom_color)
        color_row.addWidget(self._custom_color_btn)
        edit_layout.addLayout(color_row)

        # Action buttons
        btn_row = QHBoxLayout()
        self._apply_btn = QPushButton("Apply Changes")
        self._apply_btn.setProperty("variant", "primary")
        self._apply_btn.clicked.connect(self._apply_changes)
        btn_row.addWidget(self._apply_btn)
        self._delete_btn = QPushButton("Delete Calendar")
        self._delete_btn.setProperty("variant", "danger")
        self._delete_btn.clicked.connect(self._delete_calendar)
        btn_row.addWidget(self._delete_btn)
        btn_row.addStretch()
        edit_layout.addLayout(btn_row)

        layout.addWidget(edit_panel)

        # Create new calendar button
        new_btn = QPushButton("+ Create New Calendar")
        new_btn.setProperty("variant", "primary")
        new_btn.clicked.connect(self._create_new)
        layout.addWidget(new_btn)

        # Close
        close_btn = QPushButton("Close")
        close_btn.clicked.connect(self.accept)
        layout.addWidget(close_btn)

        self._current_color = CALENDAR_COLORS[0]
        self._selected_cal_id: Optional[str] = None
        self._refresh_list()

    def _refresh_list(self) -> None:
        self._list.clear()
        for cal in sorted(self.store.calendars(),
                           key=lambda c: (not c.is_default, c.name.lower())):
            suffix = ""
            if cal.is_default:
                suffix = "  (default)"
            elif cal.is_readonly:
                suffix = "  (read-only)"
            item = QListWidgetItem(f"{cal.name}{suffix}")
            item.setData(Qt.UserRole, cal.id)
            self._list.addItem(item)
        if self._list.count() > 0:
            self._list.setCurrentRow(0)

    def _on_selection(self, row: int) -> None:
        if row < 0 or row >= self._list.count():
            return
        cal_id = self._list.item(row).data(Qt.UserRole)
        cal = self.store.get_calendar(cal_id)
        if cal is None:
            return
        self._selected_cal_id = cal_id
        self._name_edit.setText(cal.name)
        self._desc_edit.setText(cal.description)
        self._current_color = cal.color
        # Disable delete for default or readonly
        self._delete_btn.setEnabled(not cal.is_default and not cal.is_readonly)
        self._name_edit.setEnabled(not cal.is_readonly)
        self._desc_edit.setEnabled(not cal.is_readonly)

    def _set_color(self, color: str) -> None:
        self._current_color = color

    def _pick_custom_color(self) -> None:
        color = QColorDialog.getColor(QColor(self._current_color), self)
        if color.isValid():
            self._current_color = color.name()

    def _apply_changes(self) -> None:
        if self._selected_cal_id is None:
            return
        cal = self.store.get_calendar(self._selected_cal_id)
        if cal is None or cal.is_readonly:
            return
        self.store.update_calendar(
            self._selected_cal_id,
            name=self._name_edit.text().strip() or cal.name,
            description=self._desc_edit.text(),
            color=self._current_color,
        )
        self._refresh_list()

    def _delete_calendar(self) -> None:
        if self._selected_cal_id is None:
            return
        cal = self.store.get_calendar(self._selected_cal_id)
        if cal is None or cal.is_default or cal.is_readonly:
            return
        ret = QMessageBox.question(
            self, "Delete Calendar",
            f"Delete calendar '{cal.name}'?\nAll events on it will be deleted.\nThis cannot be undone.",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No,
        )
        if ret == QMessageBox.Yes:
            self.store.delete_calendar(self._selected_cal_id)
            self._selected_cal_id = None
            self._refresh_list()

    def _create_new(self) -> None:
        name, ok = QInputDialog.getText(self, "New Calendar", "Calendar name:")
        if not ok or not name.strip():
            return
        # Pick a color not yet used
        used = {c.color for c in self.store.calendars()}
        color = next((c for c in CALENDAR_COLORS if c not in used), CALENDAR_COLORS[0])
        self.store.create_calendar(name=name.strip(), color=color)
        self._refresh_list()
