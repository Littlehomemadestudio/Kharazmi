"""
CommandPalette — Ctrl+P quick-action launcher.

A modal popup at the top of the window that lets the user fuzzy-find
tasks or execute any registered command by name.
"""
from __future__ import annotations

from typing import Callable, Optional
from dataclasses import dataclass

from PySide6.QtCore import Qt, Signal, QSize, QRectF
from PySide6.QtGui import (
    QFont, QColor, QKeyEvent, QPainter, QBrush, QPen,
)
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, QFrame,
    QListWidget, QListWidgetItem, QDialog, QStyledItemDelegate,
    QStyleOptionViewItem, QStyle, QApplication,
)

from ...core import Project, Task
from ..theme import Palette
from ..icons import get_icon


@dataclass
class PaletteItem:
    title: str
    subtitle: str = ""
    kind: str = "action"   # "action" | "task"
    payload: object = None  # callable or task id


class CommandPaletteDialog(QDialog):
    """The actual palette popup."""

    itemActivated = Signal(object)  # the PaletteItem's payload

    def __init__(self, parent: QWidget, project: Project,
                 commands: list[PaletteItem]) -> None:
        super().__init__(parent)
        self.project = project
        self._all_items = list(commands)
        self.setWindowFlags(Qt.Popup | Qt.FramelessWindowHint)
        self.setAttribute(Qt.WA_StyledBackground)
        self.setStyleSheet(f"""
            QDialog {{
                background-color: {Palette.BG_TERTIARY};
                border: 1px solid {Palette.BORDER_GOLD};
                border-radius: 8px;
            }}
        """)
        self.setModal(True)
        self.setMinimumWidth(560)
        self.setMaximumHeight(420)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self._input = QLineEdit()
        self._input.setPlaceholderText("type a command or search tasks...")
        self._input.setStyleSheet(f"""
            QLineEdit {{
                background-color: transparent;
                color: {Palette.GOLD_BRIGHT};
                border: none;
                border-bottom: 1px solid {Palette.BORDER_SUBTLE};
                padding: 14px 18px;
                font-size: 15px;
                font-family: 'JetBrains Mono', monospace;
            }}
        """)
        self._input.textChanged.connect(self._refilter)
        self._input.returnPressed.connect(self._activate_current)
        layout.addWidget(self._input)

        self._list = QListWidget()
        self._list.setStyleSheet(f"""
            QListWidget {{
                background-color: transparent;
                border: none;
                outline: 0;
            }}
            QListWidget::item {{
                padding: 8px 18px;
                border-bottom: 1px solid {Palette.BORDER_SUBTLE};
            }}
            QListWidget::item:selected {{
                background-color: {Palette.BG_SELECTED};
                color: {Palette.GOLD_BRIGHT};
            }}
        """)
        self._list.setItemDelegate(PaletteItemDelegate(self._list))
        self._list.itemActivated.connect(self._on_item_activated)
        layout.addWidget(self._list)

        self._populate(self._all_items)
        self._input.setFocus()

    def _populate(self, items: list[PaletteItem]) -> None:
        self._list.clear()
        for item in items:
            li = QListWidgetItem()
            li.setData(Qt.UserRole, item)
            li.setSizeHint(QSize(0, 44))
            self._list.addItem(li)
        if self._list.count() > 0:
            self._list.setCurrentRow(0)

    def _refilter(self, text: str) -> None:
        q = text.lower().strip()
        if not q:
            self._populate(self._all_items)
            return
        # Tasks + commands fuzzy-filtered
        matches: list[tuple[int, PaletteItem]] = []
        for item in self._all_items:
            score = self._match_score(q, item)
            if score >= 0:
                matches.append((score, item))
        matches.sort(key=lambda x: -x[0])
        self._populate([m[1] for m in matches[:50]])

    def _match_score(self, query: str, item: PaletteItem) -> int:
        title = item.title.lower()
        sub = item.subtitle.lower()
        if query in title:
            return 100 - title.index(query)
        if query in sub:
            return 50 - sub.index(query)
        # Initials match
        initials = "".join(w[0] for w in title.split() if w)
        if query in initials:
            return 30
        return -1

    def _activate_current(self) -> None:
        item = self._list.currentItem()
        if item is not None:
            self._on_item_activated(item)

    def _on_item_activated(self, list_item: QListWidgetItem) -> None:
        pal_item: PaletteItem = list_item.data(Qt.UserRole)
        self.itemActivated.emit(pal_item)
        self.accept()

    def keyPressEvent(self, event: QKeyEvent) -> None:
        key = event.key()
        if key == Qt.Key_Escape:
            self.reject()
            return
        if key in (Qt.Key_Up, Qt.Key_Down):
            self._list.keyPressEvent(event)
            return
        if key == Qt.Key_Return:
            self._activate_current()
            return
        super().keyPressEvent(event)


class PaletteItemDelegate(QStyledItemDelegate):
    """Renders palette items with title + subtitle."""

    def paint(self, painter: QPainter, option: QStyleOptionViewItem,
              index) -> None:
        painter.setRenderHint(QPainter.Antialiasing, True)
        # Background
        if option.state & QStyle.State_Selected:
            painter.fillRect(option.rect, QColor(Palette.BG_SELECTED))
        else:
            painter.fillRect(option.rect, QColor(Palette.BG_TERTIARY))

        item: PaletteItem = index.data(Qt.UserRole)
        if item is None:
            return

        # Kind indicator (left color bar)
        bar_color = {
            "action": Palette.GOLD_PRIMARY,
            "task":    Palette.GOLD_BRIGHT,
        }.get(item.kind, Palette.TEXT_TERTIARY)
        painter.fillRect(option.rect.left(), option.rect.top(),
                         3, option.rect.height(), QColor(bar_color))

        # Title
        painter.setPen(QPen(QColor(Palette.TEXT_PRIMARY) if not (option.state & QStyle.State_Selected)
                            else QColor(Palette.GOLD_BRIGHT)))
        title_font = QFont("Inter", 11, QFont.DemiBold)
        painter.setFont(title_font)
        painter.drawText(
            option.rect.adjusted(14, 4, -10, -16),
            Qt.AlignLeft | Qt.AlignVCenter,
            item.title
        )

        # Subtitle
        if item.subtitle:
            painter.setPen(QPen(QColor(Palette.TEXT_TERTIARY)))
            painter.setFont(QFont("JetBrains Mono", 9))
            painter.drawText(
                option.rect.adjusted(14, 18, -10, -2),
                Qt.AlignLeft | Qt.AlignVCenter,
                item.subtitle
            )

    def sizeHint(self, option, index) -> QSize:
        return QSize(0, 44)
