"""
Toolbar — the main toolbar above the workspace.

Provides quick access to: New Task, Delete, Undo, Redo, Layout, Run
Schedule, Run Monte Carlo, View switcher.
"""
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

    def __init__(self, parent: QWidget = None) -> None:
        super().__init__("Main", parent)
        self.setMovable(False)
        self.setIconSize(QSize(18, 18))
        self.setToolButtonStyle(Qt.ToolButtonTextBesideIcon)

        # --- File ops ---
        self._add_action("open", "Open", self.openRequested, "Open project snapshot")
        self._add_action("save", "Save", self.saveRequested, "Save project snapshot")
        self._add_action("export", "Export", self.exportRequested, "Export to file")
        self.addSeparator()

        # --- Task ops ---
        self._add_action("plus", "New Task", self.newTaskRequested, "Create a new task (N)")
        self._add_action("trash", "Delete", self.deleteRequested, "Delete selected task (Del)")
        self.addSeparator()

        # --- Undo / Redo ---
        self._undo_action = self._add_action("undo", "Undo", self.undoRequested, "Undo (Ctrl+Z)")
        self._redo_action = self._add_action("redo", "Redo", self.redoRequested, "Redo (Ctrl+Y)")
        self.addSeparator()

        # --- Schedule ops ---
        self._add_action("play", "Recalc", self.scheduleRequested, "Recalculate schedule")
        self._add_action("graph", "Layout", self.layoutRequested, "Auto-layout graph (Ctrl+L)")
        self._add_action("stats", "Monte Carlo", self.monteCarloRequested, "Run Monte Carlo")
        self._add_action("warning", "Advisor", self.advisorRequested, "Run advisor")
        self.addSeparator()

        # --- Command palette ---
        self._add_action("command", "Commands", self.commandPaletteRequested,
                         "Command palette (Ctrl+P)")

        # Spacer
        spacer = QWidget()
        spacer.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        self.addWidget(spacer)

        # --- View switcher (right side) ---
        view_label = QLabel("VIEW")
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

    def _add_action(self, icon_name: str, label: str,
                    signal: Signal, tooltip: str) -> QAction:
        action = QAction(get_icon(icon_name), label, self)
        action.setToolTip(tooltip)
        action.triggered.connect(signal.emit)
        self.addAction(action)
        return action

    def update_undo_redo(self, can_undo: bool, can_redo: bool,
                         undo_name: str = "", redo_name: str = "") -> None:
        self._undo_action.setEnabled(can_undo)
        self._redo_action.setEnabled(can_redo)
        if can_undo and undo_name:
            self._undo_action.setToolTip(f"Undo {undo_name} (Ctrl+Z)")
        else:
            self._undo_action.setToolTip("Nothing to undo")
        if can_redo and redo_name:
            self._redo_action.setToolTip(f"Redo {redo_name} (Ctrl+Y)")
        else:
            self._redo_action.setToolTip("Nothing to redo")

    def set_active_view(self, view_kind: str) -> None:
        for btn in self._view_group.buttons():
            if btn.property("view_kind") == view_kind:
                btn.setChecked(True)
                break
