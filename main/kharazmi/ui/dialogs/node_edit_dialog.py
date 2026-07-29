# دیالوگ ویرایش گره — ویرایش جزئیات گره
from __future__ import annotations

from typing import Optional

from PySide6.QtCore import Qt
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QFormLayout, QLabel, QLineEdit,
    QTextEdit, QComboBox, QSpinBox, QDoubleSpinBox, QPushButton, QFrame,
    QSizePolicy,
)

from ...ai import RouteStep
from ..theme import Palette


class NodeEditDialog(QDialog):
    """
    Full modal node editor with Save/Cancel buttons.

    Works for both RouteStep nodes and Task-backed nodes.
    Returns the edited values via get_changes() after accepted().
    """

    # سازنده — مقداردهی اولیه شیء
    def __init__(self, step: RouteStep, parent=None) -> None:
        super().__init__(parent)
        self.step = step
        self._changes: dict = {}
        self.setWindowTitle(f"ویرایش: {step.title}")
        self.setMinimumWidth(560)
        self.setMinimumHeight(520)
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

        icon_label = QLabel("✏️")
        icon_label.setStyleSheet("font-size: 20px; background: transparent; border: none;")
        header_layout.addWidget(icon_label)

        title_label = QLabel(f"ویرایش گره — {step.id.upper()}")
        title_label.setStyleSheet(
            f"color: {Palette.GOLD_PRIMARY}; font-size: 12px; font-weight: bold; "
            f"letter-spacing: 2px; background: transparent; border: none;"
        )
        header_layout.addWidget(title_label)
        header_layout.addStretch()

        kind_label = QLabel(step.kind.upper())
        kind_label.setStyleSheet(
            f"color: {Palette.TEXT_TERTIARY}; font-size: 10px; font-weight: bold; "
            f"letter-spacing: 1px; background: transparent; border: none; "
            f"padding: 2px 8px; border: 1px solid {Palette.BORDER_NORMAL}; border-radius: 3px;"
        )
        header_layout.addWidget(kind_label)

        layout.addWidget(header)

        # ---- Form ----
        form = QFormLayout()
        form.setSpacing(10)
        form.setLabelAlignment(Qt.AlignRight)

        # Title
        self._title = QLineEdit(step.title or "")
        self._title.setStyleSheet(self._input_style(large=True))
        self._title.setPlaceholderText("عنوان مرحله…")
        self._title.selectAll()
        form.addRow(self._label("عنوان"), self._title)

        # Description
        self._desc = QTextEdit()
        self._desc.setPlainText(step.description or "")
        self._desc.setFixedHeight(100)
        self._desc.setStyleSheet(self._input_style())
        self._desc.setPlaceholderText("توضیحات…")
        self._desc.setAcceptRichText(False)
        form.addRow(self._label("توضیحات"), self._desc)

        # Duration + Success probability
        row1 = QHBoxLayout()
        self._dur_spin = QSpinBox()
        self._dur_spin.setRange(1, 99999)
        self._dur_spin.setValue(step.duration_minutes)
        self._dur_spin.setSuffix("  دقیقه")
        self._dur_spin.setStyleSheet(self._input_style())
        row1.addWidget(self._dur_spin)

        row1.addSpacing(16)

        self._prob_spin = QDoubleSpinBox()
        self._prob_spin.setRange(0.0, 1.0)
        self._prob_spin.setSingleStep(0.05)
        self._prob_spin.setDecimals(2)
        self._prob_spin.setValue(step.success_probability)
        self._prob_spin.setStyleSheet(self._input_style())
        row1.addWidget(QLabel("احتمال موفقیت"))
        row1.addWidget(self._prob_spin)
        form.addRow(self._label("مدت"), row1)

        # Risk + Kind
        row2 = QHBoxLayout()
        self._risk_combo = QComboBox()
        for r in ["پایین", "متوسط", "بالا", "شدید"]:
            self._risk_combo.addItem(r)
        self._risk_combo.setCurrentText(step.risk_level)
        self._risk_combo.setStyleSheet(self._input_style())
        row2.addWidget(self._risk_combo)

        row2.addSpacing(16)

        self._kind_combo = QComboBox()
        for k in ["عمل", "تصمیم", "نقطه عطف", "انتظار", "بازرسی"]:
            self._kind_combo.addItem(k)
        self._kind_combo.setCurrentText(step.kind)
        self._kind_combo.setStyleSheet(self._input_style())
        row2.addWidget(QLabel("نوع"))
        row2.addWidget(self._kind_combo)
        form.addRow(self._label("ریسک"), row2)

        # Branch
        self._branch = QLineEdit(step.branch or "")
        self._branch.setStyleSheet(self._input_style())
        self._branch.setPlaceholderText("مثلاً: اصلی، alt-a، fallback-1")
        form.addRow(self._label("شاخه"), self._branch)

        # Location
        self._location = QLineEdit(step.location or "")
        self._location.setStyleSheet(self._input_style())
        self._location.setPlaceholderText("مثلاً: دفتر، راه دور، تهران")
        form.addRow(self._label("مکان"), self._location)

        # Cost estimate
        self._cost = QLineEdit(step.cost_estimate or "")
        self._cost.setStyleSheet(self._input_style())
        self._cost.setPlaceholderText("مثلاً: ۵۰۰ دلار، ۲ ساعت")
        form.addRow(self._label("هزینه"), self._cost)

        # Fallback
        self._fallback = QTextEdit()
        self._fallback.setPlainText(step.fallback or "")
        self._fallback.setFixedHeight(60)
        self._fallback.setStyleSheet(self._input_style())
        self._fallback.setPlaceholderText("اگر این مرحله شکست خورد چه کار کنید…")
        self._fallback.setAcceptRichText(False)
        form.addRow(self._label("جایگزین"), self._fallback)

        # Depends on (display only)
        if step.depends_on:
            dep_text = ", ".join(step.depends_on)
            dep_label = QLabel(dep_text)
            dep_label.setStyleSheet(
                f"color: {Palette.TEXT_TERTIARY}; font-size: 11px; "
                f"font-family: 'JetBrains Mono', monospace; "
                f"background: transparent; border: none; padding: 4px;"
            )
            dep_label.setWordWrap(True)
            form.addRow(self._label("وابسته به"), dep_label)

        # Sub-goals (display only)
        if step.sub_goals:
            sg_text = "\n".join(f"◆ {sg}" for sg in step.sub_goals)
            sg_label = QLabel(sg_text)
            sg_label.setStyleSheet(
                f"color: {Palette.TEXT_SECONDARY}; font-size: 11px; "
                f"background: transparent; border: none; padding: 4px;"
            )
            sg_label.setWordWrap(True)
            form.addRow(self._label("زیراهداف"), sg_label)

        layout.addLayout(form)

        layout.addSpacing(8)

        # ---- Buttons ----
        btn_row = QHBoxLayout()
        btn_row.addStretch()

        cancel_btn = QPushButton("  لغو  ")
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

        save_btn = QPushButton("  💾  ذخیره تغییرات  ")
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
        save_btn.clicked.connect(self._on_save)
        btn_row.addWidget(save_btn)

        layout.addLayout(btn_row)

        # Focus title on open
        self._title.setFocus()

    # برچسب
    def _label(self, text: str) -> QLabel:
        lbl = QLabel(text)
        lbl.setStyleSheet(
            f"color: {Palette.TEXT_TERTIARY}; font-size: 10px; "
            f"font-weight: bold; letter-spacing: 1.2px; "
            f"background: transparent; border: none; padding-top: 4px;"
        )
        return lbl

    # input سبک
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

    # پاسخ به ذخیره
    def _on_save(self) -> None:
        title = self._title.text().strip()
        if not title:
            from PySide6.QtWidgets import QMessageBox
            QMessageBox.warning(self, "الزامی", "عنوان الزامی است.")
            return

        # Collect changes
        self._changes = {
            "title": title,
            "description": self._desc.toPlainText().strip(),
            "duration_minutes": self._dur_spin.value(),
            "success_probability": self._prob_spin.value(),
            "risk_level": self._risk_combo.currentText(),
            "kind": self._kind_combo.currentText(),
            "branch": self._branch.text().strip(),
            "location": self._location.text().strip(),
            "cost_estimate": self._cost.text().strip(),
            "fallback": self._fallback.toPlainText().strip(),
        }
        self.accept()

    # دریافت changes
    def get_changes(self) -> dict:
        """Return the dict of changed fields after dialog is accepted."""
        return self._changes
