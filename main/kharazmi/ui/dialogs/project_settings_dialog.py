# دیالوگ تنظیمات پروژه — پیکربندی پروژه
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QFormLayout, QLabel, QLineEdit,
    QTextEdit, QPushButton, QDialogButtonBox, QGroupBox, QFrame,
)

from ...core import Project
from ..theme import Palette


class ProjectSettingsDialog(QDialog):
    # سازنده — مقداردهی اولیه شیء
    def __init__(self, project: Project, parent=None) -> None:
        super().__init__(parent)
        self.project = project
        self.setWindowTitle("تنظیمات پروژه")
        self.setMinimumWidth(480)
        self.setStyleSheet(f"background-color: {Palette.BG_PRIMARY};")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(12)

        title = QLabel("تنظیمات پروژه")
        title.setStyleSheet(
            f"color: {Palette.GOLD_PRIMARY}; font-size: 11px; font-weight: bold; "
            f"letter-spacing: 2px;"
        )
        layout.addWidget(title)

        form = QFormLayout()
        self._name = QLineEdit(project.name)
        form.addRow("نام", self._name)

        self._desc = QTextEdit()
        self._desc.setPlainText(project.description)
        self._desc.setFixedHeight(80)
        form.addRow("توضیحات", self._desc)

        layout.addLayout(form)

        # Info group
        info_group = QGroupBox("اطلاعات پروژه")
        info_layout = QFormLayout(info_group)
        info_layout.addRow("وظایف", QLabel(str(project.task_count)))
        info_layout.addRow("وابستگی‌ها", QLabel(str(project.dependency_count)))
        info_layout.addRow("ایجاد شده", QLabel(project.created_at.strftime("%Y-%m-%d %H:%M")))
        layout.addWidget(info_group)

        buttons = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        buttons.button(QDialogButtonBox.Save).setProperty("variant", "primary")
        buttons.accepted.connect(self._on_save)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    # پاسخ به ذخیره
    def _on_save(self) -> None:
        name = self._name.text().strip()
        if not name:
            from PySide6.QtWidgets import QMessageBox
            QMessageBox.warning(self, "الزامی", "نام پروژه الزامی است.")
            return
        self.project.name = name
        self.project.description = self._desc.toPlainText()
        self.accept()
