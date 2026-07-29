# نوارابزار — دکمه‌ها و ابزارهای اصلی بالای صفحه
from __future__ import annotations

from PySide6.QtCore import Qt, Signal, QSize
from PySide6.QtGui import QAction, QFont, QIcon
from PySide6.QtWidgets import (
    QToolBar, QWidget, QLabel, QToolButton, QSpacerItem, QSizePolicy,
    QPushButton, QHBoxLayout,
)

from ...core import ViewKind
from ..theme import Palette
from ..icons import get_icon


class MainToolbar(QToolBar):
    """The top toolbar."""

    newTaskRequested = Signal()
    deleteRequested = Signal()
    undoRequested = Signal()
    redoRequested = Signal()
    layoutRequested = Signal()
    scheduleRequested = Signal()
    monteCarloRequested = Signal()
    saveRequested = Signal()
    openRequested = Signal()
    exportRequested = Signal()
    viewChanged = Signal(str)
    commandPaletteRequested = Signal()
    advisorRequested = Signal()

    # سازنده — مقداردهی اولیه شیء
    def __init__(self, parent: QWidget = None) -> None:
        super().__init__("Main", parent)
        self.setMovable(False)
        self.setIconSize(QSize(18, 18))
        self.setToolButtonStyle(Qt.ToolButtonTextBesideIcon)

        # --- File ops ---
        self._add_action("open", "باز کردن", self.openRequested, "باز کردن پروژه")
        self._add_action("save", "ذخیره", self.saveRequested, "ذخیره پروژه")
        self._add_action("export", "صادر کردن", self.exportRequested, "صادر کردن به فایل")
        self.addSeparator()

        # --- Task ops ---
        self._add_action("plus", "وظیفه جدید", self.newTaskRequested, "ایجاد وظیفه جدید (N)")
        self._add_action("trash", "حذف", self.deleteRequested, "حذف وظیفه انتخاب‌شده (Del)")
        self.addSeparator()

        # --- Undo / Redo ---
        self._undo_action = self._add_action("undo", "برگشت", self.undoRequested, "برگشت (Ctrl+Z)")
        self._redo_action = self._add_action("redo", "دوباره", self.redoRequested, "دوباره (Ctrl+Y)")
        self.addSeparator()

        # --- Schedule ops ---
        self._add_action("play", "محاسبه", self.scheduleRequested, "محاسبه مجدد زمان‌بندی")
        self._add_action("graph", "چیدمان", self.layoutRequested, "چیدمان خودکار گراف (Ctrl+L)")
        self._add_action("stats", "مونت‌کارلو", self.monteCarloRequested, "اجرای شبیه‌سازی مونت‌کارلو")
        self._add_action("warning", "مشاور", self.advisorRequested, "اجرای مشاور")
        self.addSeparator()

        # --- Command palette ---
        self._add_action("command", "دستورات", self.commandPaletteRequested,
                         "پالت دستورات (Ctrl+P)")

        # Spacer
        spacer = QWidget()
        spacer.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        self.addWidget(spacer)

        # --- View switcher (right side) ---
        view_label = QLabel("نما")
        view_label.setStyleSheet(
            f"color: {Palette.TEXT_TERTIARY}; font-size: 10px; "
            f"font-weight: bold; letter-spacing: 1.5px; padding: 0 6px 0 12px;"
        )
        self.addWidget(view_label)

        from PySide6.QtWidgets import QButtonGroup, QToolButton
        self._view_group = QButtonGroup(self)
        self._view_group.setExclusive(True)
        for kind in ViewKind:
            btn = QToolButton()
            btn.setText(kind.value.upper())
            btn.setIcon(get_icon(kind.value))
            btn.setToolButtonStyle(Qt.ToolButtonTextBesideIcon)
            btn.setCheckable(True)
            btn.setProperty("view_kind", kind.value)
            btn.clicked.connect(lambda _=False, k=kind: self.viewChanged.emit(k.value))
            self._view_group.addButton(btn)
            self.addWidget(btn)
        # Default to graph view
        for btn in self._view_group.buttons():
            if btn.property("view_kind") == "graph":
                btn.setChecked(True)
                break

    # افزودن عملکرد
    def _add_action(self, icon_name: str, label: str,
                    signal: Signal, tooltip: str) -> QAction:
        action = QAction(get_icon(icon_name), label, self)
        action.setToolTip(tooltip)
        action.triggered.connect(signal.emit)
        self.addAction(action)
        return action

    # بروزرسانی undo redo
    def update_undo_redo(self, can_undo: bool, can_redo: bool,
                         undo_name: str = "", redo_name: str = "") -> None:
        self._undo_action.setEnabled(can_undo)
        self._redo_action.setEnabled(can_redo)
        if can_undo and undo_name:
            self._undo_action.setToolTip(f"برگشت {undo_name} (Ctrl+Z)")
        else:
            self._undo_action.setToolTip("چیزی برای برگشت نیست")
        if can_redo and redo_name:
            self._redo_action.setToolTip(f"دوباره {redo_name} (Ctrl+Y)")
        else:
            self._redo_action.setToolTip("چیزی برای دوباره نیست")

    # مجموعه فعال نما
    def set_active_view(self, view_kind: str) -> None:
        for btn in self._view_group.buttons():
            if btn.property("view_kind") == view_kind:
                btn.setChecked(True)
                break
