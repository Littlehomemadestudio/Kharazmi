"""
NewNodeDialog — modal dialog for manually creating new nodes on the canvas.

Provides a node-type card selector at the top (action, decision, milestone,
wait, checkpoint) and a complete form for all RouteStep fields below.
Returns a new RouteStep via get_step() after accepted().
"""
from __future__ import annotations

import uuid

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QFormLayout, QLabel, QLineEdit,
    QTextEdit, QComboBox, QSpinBox, QDoubleSpinBox, QPushButton, QFrame,
    QSizePolicy,
)

from ...ai import RouteStep
from ..theme import Palette

# ---------------------------------------------------------------------------
# Node-type definitions
# ---------------------------------------------------------------------------
_NODE_TYPES: list[dict] = [
    {
        "kind": "action",
        "icon": "\U0001F3AF",  # 🎯
        "label": "Action",
        "tip": "A regular step",
        "bg": "#1A2418",       # muted green-dark
        "bg_hover": "#223020",
        "border": "#3A5A30",
    },
    {
        "kind": "decision",
        "icon": "\U0001F500",  # 🔀
        "label": "Decision",
        "tip": "A branching point",
        "bg": "#1A1824",       # muted purple-dark
        "bg_hover": "#222030",
        "border": "#3A305A",
    },
    {
        "kind": "milestone",
        "icon": "\U0001F3C1",  # 🏁
        "label": "Milestone",
        "tip": "A checkpoint",
        "bg": "#24201A",       # muted gold-dark
        "bg_hover": "#302A20",
        "border": "#5A4A20",
    },
    {
        "kind": "wait",
        "icon": "\u23F3",      # ⏳
        "label": "Wait",
        "tip": "A waiting step",
        "bg": "#1A2024",       # muted blue-dark
        "bg_hover": "#202A30",
        "border": "#304A5A",
    },
    {
        "kind": "checkpoint",
        "icon": "\u2705",      # ✅
        "label": "Checkpoint",
        "tip": "A verification step",
        "bg": "#241A1A",       # muted red-dark
        "bg_hover": "#302020",
        "border": "#5A3030",
    },
]


class _TypeCard(QFrame):
    """A single clickable card in the node-type selector row."""

    def __init__(self, info: dict, parent=None) -> None:
        super().__init__(parent)
        self.info = info
        self.selected = False
        self.setFixedSize(96, 80)
        self.setCursor(Qt.PointingHandCursor)
        self.setToolTip(info["tip"])

        layout = QVBoxLayout(self)
        layout.setContentsMargins(6, 8, 6, 6)
        layout.setSpacing(2)
        layout.setAlignment(Qt.AlignCenter)

        icon_lbl = QLabel(info["icon"])
        icon_lbl.setAlignment(Qt.AlignCenter)
        icon_lbl.setStyleSheet("font-size: 22px; background: transparent; border: none;")
        layout.addWidget(icon_lbl)

        name_lbl = QLabel(info["label"])
        name_lbl.setAlignment(Qt.AlignCenter)
        name_lbl.setStyleSheet(
            f"color: {Palette.TEXT_SECONDARY}; font-size: 10px; "
            f"font-weight: bold; letter-spacing: 0.5px; "
            f"background: transparent; border: none;"
        )
        layout.addWidget(name_lbl)

        self._apply_style()

    def set_selected(self, selected: bool) -> None:
        self.selected = selected
        self._apply_style()

    def _apply_style(self) -> None:
        info = self.info
        if self.selected:
            border_color = Palette.GOLD_BRIGHT
            border_width = "2px"
            bg = info["bg_hover"]
        else:
            border_color = info["border"]
            border_width = "1px"
            bg = info["bg"]
        self.setStyleSheet(
            f"QFrame {{ "
            f"  background-color: {bg}; "
            f"  border: {border_width} solid {border_color}; "
            f"  border-radius: 8px; "
            f"}}"
        )

    def mousePressEvent(self, event) -> None:  # noqa: N802
        # Emit custom selection via parent dialog; handled below
        super().mousePressEvent(event)


class NewNodeDialog(QDialog):
    """
    Modal dialog for creating a new RouteStep node.

    After dialog is accepted, call get_step() to retrieve the new RouteStep.
    """

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._selected_kind: str = "action"
        self._step: RouteStep | None = None

        self.setWindowTitle("Add New Node")
        self.setMinimumWidth(580)
        self.setMinimumHeight(620)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.setStyleSheet(f"background-color: {Palette.BG_PRIMARY};")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 20, 24, 20)
        layout.setSpacing(12)

        # ---- Header ----
        header = QFrame()
        header.setStyleSheet(
            f"background: transparent; border-bottom: 1px solid {Palette.BORDER_SUBTLE};"
        )
        header_layout = QHBoxLayout(header)
        header_layout.setContentsMargins(0, 0, 0, 8)

        icon_label = QLabel("\u2795")  # ➕
        icon_label.setStyleSheet("font-size: 20px; background: transparent; border: none;")
        header_layout.addWidget(icon_label)

        title_label = QLabel("ADD NEW NODE")
        title_label.setStyleSheet(
            f"color: {Palette.GOLD_PRIMARY}; font-size: 12px; font-weight: bold; "
            f"letter-spacing: 2px; background: transparent; border: none;"
        )
        header_layout.addWidget(title_label)
        header_layout.addStretch()

        layout.addWidget(header)

        # ---- Node-type card selector ----
        type_row = QHBoxLayout()
        type_row.setSpacing(8)
        type_row.addStretch()

        self._type_cards: list[_TypeCard] = []
        for info in _NODE_TYPES:
            card = _TypeCard(info, self)
            if info["kind"] == self._selected_kind:
                card.set_selected(True)
            card.mousePressEvent = (  # type: ignore[assignment]
                lambda event, c=card: self._select_type(c)
            )
            self._type_cards.append(card)
            type_row.addWidget(card)

        type_row.addStretch()
        layout.addLayout(type_row)

        # ---- Separator ----
        sep = QFrame()
        sep.setFixedHeight(1)
        sep.setStyleSheet(f"background-color: {Palette.BORDER_SUBTLE}; border: none;")
        layout.addWidget(sep)

        layout.addSpacing(4)

        # ---- Form ----
        form = QFormLayout()
        form.setSpacing(10)
        form.setLabelAlignment(Qt.AlignRight)

        # Title (large, required)
        self._title = QLineEdit()
        self._title.setStyleSheet(self._input_style(large=True))
        self._title.setPlaceholderText("Step title\u2026")
        form.addRow(self._label("Title *"), self._title)

        # Description
        self._desc = QTextEdit()
        self._desc.setFixedHeight(80)
        self._desc.setStyleSheet(self._input_style())
        self._desc.setPlaceholderText("Description\u2026")
        self._desc.setAcceptRichText(False)
        form.addRow(self._label("Description"), self._desc)

        # Duration + Success probability (side by side)
        row1 = QHBoxLayout()
        self._dur_spin = QSpinBox()
        self._dur_spin.setRange(1, 99999)
        self._dur_spin.setValue(30)
        self._dur_spin.setSuffix("  min")
        self._dur_spin.setStyleSheet(self._input_style())
        row1.addWidget(self._dur_spin)

        row1.addSpacing(16)

        prob_label = QLabel("Success %")
        prob_label.setStyleSheet(
            f"color: {Palette.TEXT_TERTIARY}; font-size: 10px; "
            f"font-weight: bold; letter-spacing: 1px; "
            f"background: transparent; border: none; padding-top: 4px;"
        )
        row1.addWidget(prob_label)

        self._prob_spin = QDoubleSpinBox()
        self._prob_spin.setRange(0.0, 1.0)
        self._prob_spin.setSingleStep(0.05)
        self._prob_spin.setDecimals(2)
        self._prob_spin.setValue(0.8)
        self._prob_spin.setStyleSheet(self._input_style())
        row1.addWidget(self._prob_spin)
        form.addRow(self._label("Duration"), row1)

        # Risk Level + Branch (side by side)
        row2 = QHBoxLayout()
        self._risk_combo = QComboBox()
        for r in ["low", "medium", "high", "severe"]:
            self._risk_combo.addItem(r)
        self._risk_combo.setCurrentText("low")
        self._risk_combo.setStyleSheet(self._input_style())
        row2.addWidget(self._risk_combo)

        row2.addSpacing(16)

        branch_label = QLabel("Branch")
        branch_label.setStyleSheet(
            f"color: {Palette.TEXT_TERTIARY}; font-size: 10px; "
            f"font-weight: bold; letter-spacing: 1px; "
            f"background: transparent; border: none; padding-top: 4px;"
        )
        row2.addWidget(branch_label)

        self._branch = QLineEdit("main")
        self._branch.setStyleSheet(self._input_style())
        self._branch.setPlaceholderText("e.g. main, alt-a, fallback-1")
        row2.addWidget(self._branch)
        form.addRow(self._label("Risk"), row2)

        # Location
        self._location = QLineEdit()
        self._location.setStyleSheet(self._input_style())
        self._location.setPlaceholderText("e.g. Office, Remote, Tehran")
        form.addRow(self._label("Location"), self._location)

        # Cost estimate
        self._cost = QLineEdit()
        self._cost.setStyleSheet(self._input_style())
        self._cost.setPlaceholderText("e.g. $500, 2 hours")
        form.addRow(self._label("Cost"), self._cost)

        # Fallback
        self._fallback = QTextEdit()
        self._fallback.setFixedHeight(60)
        self._fallback.setStyleSheet(self._input_style())
        self._fallback.setPlaceholderText("What to do if this step fails\u2026")
        self._fallback.setAcceptRichText(False)
        form.addRow(self._label("Fallback"), self._fallback)

        layout.addLayout(form)

        layout.addSpacing(8)

        # ---- Buttons ----
        btn_row = QHBoxLayout()
        btn_row.addStretch()

        cancel_btn = QPushButton("  Cancel  ")
        cancel_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: {Palette.BG_TERTIARY};
                color: {Palette.TEXT_SECONDARY};
                border: 1px solid {Palette.BORDER_NORMAL};
                border-radius: 6px;
                padding: 10px 28px;
                font-size: 13px;
                font-weight: bold;
            }}
            QPushButton:hover {{
                background-color: {Palette.BG_HOVER};
                border: 1px solid {Palette.BORDER_GOLD};
            }}
        """)
        cancel_btn.clicked.connect(self.reject)
        btn_row.addWidget(cancel_btn)

        save_btn = QPushButton("  \u2795  Create Node  ")
        save_btn.setDefault(True)
        save_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: {Palette.GOLD_PRIMARY};
                color: {Palette.TEXT_ON_GOLD};
                border: none;
                border-radius: 6px;
                padding: 10px 28px;
                font-size: 13px;
                font-weight: bold;
            }}
            QPushButton:hover {{
                background-color: {Palette.GOLD_BRIGHT};
            }}
        """)
        save_btn.clicked.connect(self._on_create)
        btn_row.addWidget(save_btn)

        layout.addLayout(btn_row)

        # Focus title on open
        self._title.setFocus()

    # ------------------------------------------------------------------
    # Helpers (same pattern as NodeEditDialog)
    # ------------------------------------------------------------------

    def _label(self, text: str) -> QLabel:
        lbl = QLabel(text)
        lbl.setStyleSheet(
            f"color: {Palette.TEXT_TERTIARY}; font-size: 10px; "
            f"font-weight: bold; letter-spacing: 1.2px; "
            f"background: transparent; border: none; padding-top: 4px;"
        )
        return lbl

    def _input_style(self, large: bool = False) -> str:
        font_size = "13px" if large else "11px"
        font_weight = "bold" if large else "normal"
        return f"""
            QLineEdit, QTextEdit, QSpinBox, QDoubleSpinBox, QComboBox {{
                background-color: {Palette.BG_DEEPEST};
                color: {Palette.TEXT_PRIMARY};
                border: 1px solid {Palette.BORDER_NORMAL};
                border-radius: 4px;
                padding: 8px 12px;
                font-size: {font_size};
                font-weight: {font_weight};
            }}
            QLineEdit:focus, QTextEdit:focus, QSpinBox:focus,
            QDoubleSpinBox:focus, QComboBox:focus {{
                border: 2px solid {Palette.GOLD_BRIGHT};
                background-color: {Palette.BG_ELEVATED};
            }}
        """

    # ------------------------------------------------------------------
    # Type-card selection
    # ------------------------------------------------------------------

    def _select_type(self, card: _TypeCard) -> None:
        self._selected_kind = card.info["kind"]
        for c in self._type_cards:
            c.set_selected(c is card)

    # ------------------------------------------------------------------
    # Create action
    # ------------------------------------------------------------------

    def _on_create(self) -> None:
        title = self._title.text().strip()
        if not title:
            from PySide6.QtWidgets import QMessageBox
            QMessageBox.warning(self, "Required", "Title is required.")
            return

        step_id = f"manual-{uuid.uuid4().hex[:8]}"
        self._step = RouteStep(
            id=step_id,
            title=title,
            description=self._desc.toPlainText().strip(),
            duration_minutes=self._dur_spin.value(),
            success_probability=self._prob_spin.value(),
            risk_level=self._risk_combo.currentText(),
            kind=self._selected_kind,
            branch=self._branch.text().strip() or "main",
            location=self._location.text().strip(),
            cost_estimate=self._cost.text().strip(),
            fallback=self._fallback.toPlainText().strip(),
        )
        self.accept()

    def get_step(self) -> RouteStep | None:
        """Return the newly created RouteStep after dialog is accepted, or None."""
        return self._step
