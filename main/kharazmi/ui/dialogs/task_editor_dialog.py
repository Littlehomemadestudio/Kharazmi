"""Task editor dialog — full modal editor for a task."""
from __future__ import annotations

from typing import Optional

from PySide6.QtCore import Qt, QDate, QDateTime
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QFormLayout, QLabel, QLineEdit,
    QTextEdit, QComboBox, QSpinBox, QDoubleSpinBox, QPushButton, QFrame,
    QDialogButtonBox, QGroupBox, QSlider, QDateTimeEdit, QCheckBox,
)

from ...core import (
    Task, TaskId, TaskStatus, Priority, RiskLevel, DurationUnit,
    Duration, Tag, PertEstimate,
)
from ...services import TaskService
from ..theme import Palette


class TaskEditorDialog(QDialog):
    """Full modal task editor."""

    def __init__(self, task: Optional[Task], task_service: TaskService,
                 parent=None) -> None:
        super().__init__(parent)
        self.task = task
        self.task_service = task_service
        self.setWindowTitle("Edit Task" if task else "New Task")
        self.setMinimumWidth(520)
        self.setStyleSheet(f"background-color: {Palette.BG_PRIMARY};")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(12)

        title_label = QLabel("TASK EDITOR")
        title_label.setStyleSheet(
            f"color: {Palette.GOLD_PRIMARY}; font-size: 11px; font-weight: bold; "
            f"letter-spacing: 2px;"
        )
        layout.addWidget(title_label)

        form = QFormLayout()
        form.setSpacing(8)

        self._title = QLineEdit(task.title if task else "")
        form.addRow("Title", self._title)

        self._desc = QTextEdit()
        self._desc.setFixedHeight(80)
        self._desc.setPlainText(task.description if task else "")
        form.addRow("Description", self._desc)

        # Duration
        dur_row = QHBoxLayout()
        self._dur = QDoubleSpinBox()
        self._dur.setRange(0.01, 9999)
        self._dur.setValue(task.duration.to_unit(DurationUnit.DAY) if task else 1.0)
        self._dur_unit = QComboBox()
        for u in DurationUnit:
            self._dur_unit.addItem(u.value)
        self._dur_unit.setCurrentText(DurationUnit.DAY.value)
        dur_row.addWidget(self._dur)
        dur_row.addWidget(self._dur_unit)
        form.addRow("Duration", dur_row)

        # Priority
        self._priority = QComboBox()
        for p in Priority:
            self._priority.addItem(p.name, p)
        if task:
            self._priority.setCurrentIndex(int(task.priority))
        form.addRow("Priority", self._priority)

        # Risk
        self._risk = QComboBox()
        for r in RiskLevel:
            self._risk.addItem(r.name, r)
        if task:
            self._risk.setCurrentText(task.risk.name)
        form.addRow("Risk", self._risk)

        # Status
        self._status = QComboBox()
        for s in TaskStatus:
            self._status.addItem(s.value, s)
        if task:
            self._status.setCurrentIndex(list(TaskStatus).index(task.status))
        form.addRow("Status", self._status)

        # Progress
        prog_row = QHBoxLayout()
        self._progress = QSlider(Qt.Horizontal)
        self._progress.setRange(0, 100)
        self._progress.setValue(task.progress.percent if task else 0)
        self._progress_lbl = QLabel(f"{self._progress.value()}%")
        self._progress_lbl.setStyleSheet(
            f"color: {Palette.GOLD_BRIGHT}; font-weight: bold; "
            f"font-family: 'JetBrains Mono', monospace;"
        )
        self._progress.valueChanged.connect(
            lambda v: self._progress_lbl.setText(f"{v}%")
        )
        prog_row.addWidget(self._progress)
        prog_row.addWidget(self._progress_lbl)
        form.addRow("Progress", prog_row)

        # Tags
        self._tags = QLineEdit()
        if task:
            self._tags.setText(", ".join(sorted(str(t) for t in task.tags)))
        self._tags.setPlaceholderText("comma-separated, e.g. backend, urgent")
        form.addRow("Tags", self._tags)

        layout.addLayout(form)

        # PERT group
        pert_group = QGroupBox("PERT 3-Point Estimate (optional)")
        pert_layout = QFormLayout(pert_group)
        self._pert_o = QDoubleSpinBox()
        self._pert_m = QDoubleSpinBox()
        self._pert_p = QDoubleSpinBox()
        for sb in [self._pert_o, self._pert_m, self._pert_p]:
            sb.setRange(0, 9999)
            sb.setDecimals(2)
        if task and task.pert:
            self._pert_o.setValue(task.pert.optimistic.to_unit(DurationUnit.DAY))
            self._pert_m.setValue(task.pert.most_likely.to_unit(DurationUnit.DAY))
            self._pert_p.setValue(task.pert.pessimistic.to_unit(DurationUnit.DAY))
        pert_layout.addRow("Optimistic", self._pert_o)
        pert_layout.addRow("Most likely", self._pert_m)
        pert_layout.addRow("Pessimistic", self._pert_p)
        layout.addWidget(pert_group)

        # Buttons
        buttons = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        buttons.button(QDialogButtonBox.Save).setProperty("variant", "primary")
        buttons.button(QDialogButtonBox.Save).setText("Save Task")
        buttons.accepted.connect(self._on_save)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _on_save(self) -> None:
        title = self._title.text().strip()
        if not title:
            from PySide6.QtWidgets import QMessageBox
            QMessageBox.warning(self, "Required", "Title is required.")
            return
        # Build / update task
        if self.task is None:
            tid = self.task_service.create_task(
                title=title,
                duration_minutes=Duration.of(self._dur.value(),
                                              DurationUnit(self._dur_unit.currentText())).minutes,
                priority=self._priority.currentData(),
            )
            if tid is None:
                self.reject()
                return
            self.task = self.task_service.project.get_task(tid)
        else:
            self.task_service.update_task(
                self.task.id,
                title=title,
                description=self._desc.toPlainText(),
                duration=Duration.of(self._dur.value(),
                                      DurationUnit(self._dur_unit.currentText())),
                priority=self._priority.currentData(),
                risk=self._risk.currentData(),
                progress=self._progress.value(),
            )
            # Status change — may be illegal; ignore if so
            try:
                self.task_service.change_status(self.task.id, self._status.currentData())
            except ValueError:
                pass

        # Tags
        new_tags = set()
        for part in self._tags.text().split(","):
            part = part.strip()
            if not part:
                continue
            try:
                new_tags.add(Tag(part))
            except ValueError:
                pass
        self.task.tags = new_tags

        # PERT
        if self._pert_o.value() > 0 or self._pert_m.value() > 0 or self._pert_p.value() > 0:
            try:
                unit = DurationUnit.DAY
                opt = Duration.of(self._pert_o.value(), unit)
                ml = Duration.of(self._pert_m.value(), unit)
                pess = Duration.of(self._pert_p.value(), unit)
                if opt.minutes <= ml.minutes <= pess.minutes:
                    self.task.pert = PertEstimate(opt, ml, pess)
            except ValueError:
                pass

        self.task.touch()
        self.task_service.scheduling.recalculate()
        self.accept()
