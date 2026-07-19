"""
InspectorPanel — properties editor for the currently-selected task.

Shown on the right side of the main window. Reflects and edits the
task that the user has selected in any view.
"""
from __future__ import annotations

from datetime import datetime
from typing import Optional

from PySide6.QtCore import Qt, Signal, QDate, QDateTime
from PySide6.QtGui import (
    QFont, QColor, QIntValidator, QDoubleValidator,
)
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QFormLayout, QLabel, QLineEdit,
    QTextEdit, QComboBox, QSpinBox, QDoubleSpinBox, QPushButton, QFrame,
    QScrollArea, QGroupBox, QSlider, QCheckBox, QDateTimeEdit, QSizePolicy,
    QSpacerItem, QToolButton,
)

from ...core import (
    Project, Task, TaskId, TaskStatus, Priority, RiskLevel, DurationUnit,
    Duration, Tag, Resource, ResourceAllocation, PertEstimate,
    LEGAL_TRANSITIONS,
)
from ...services import TaskService
from ..theme import Palette, status_color, risk_color
from ..icons import get_icon


class InspectorPanel(QScrollArea):
    """Right-side properties panel."""

    taskChanged = Signal(object)  # emits the Task being edited (or None)

    def __init__(self, project: Project, task_service: TaskService,
                 parent: QWidget = None) -> None:
        super().__init__(parent)
        self.project = project
        self.task_service = task_service
        self._current_task: Optional[Task] = None
        self._suppress_updates = False

        self.setWidgetResizable(True)
        self.setFrameShape(QFrame.NoFrame)
        self.setFixedWidth(320)
        self.setStyleSheet(f"QScrollArea {{ background-color: {Palette.BG_SECONDARY}; border: none; }}")

        container = QWidget()
        container.setStyleSheet(f"background-color: {Palette.BG_SECONDARY};")
        self._layout = QVBoxLayout(container)
        self._layout.setContentsMargins(14, 14, 14, 14)
        self._layout.setSpacing(12)

        self._build_header()
        self._build_basic_group()
        self._build_schedule_group()
        self._build_status_group()
        self._build_pert_group()
        self._build_actions_group()

        self._layout.addStretch()
        self.setWidget(container)

        self._set_enabled(False)

    def _build_header(self) -> None:
        title = QLabel("INSPECTOR")
        title.setStyleSheet(
            f"color: {Palette.GOLD_PRIMARY}; font-size: 11px; font-weight: bold; "
            f"letter-spacing: 1.8px; padding: 4px 0;"
        )
        self._layout.addWidget(title)

        self._task_title_label = QLabel("No task selected")
        self._task_title_label.setWordWrap(True)
        self._task_title_label.setStyleSheet(
            f"color: {Palette.TEXT_PRIMARY}; font-size: 14px; font-weight: bold; "
            f"padding: 4px 0 8px 0; border-bottom: 1px solid {Palette.BORDER_SUBTLE};"
        )
        self._layout.addWidget(self._task_title_label)

    def _build_basic_group(self) -> None:
        group = QGroupBox("Basic")
        layout = QFormLayout(group)
        layout.setSpacing(6)
        layout.setLabelAlignment(Qt.AlignLeft)

        self._title_edit = QLineEdit()
        self._title_edit.textChanged.connect(self._on_title_changed)
        layout.addRow("Title", self._title_edit)

        self._desc_edit = QTextEdit()
        self._desc_edit.setFixedHeight(60)
        self._desc_edit.textChanged.connect(self._on_desc_changed)
        layout.addRow("Description", self._desc_edit)

        # Duration
        dur_row = QHBoxLayout()
        self._dur_value = QDoubleSpinBox()
        self._dur_value.setRange(0.01, 9999.0)
        self._dur_value.setSingleStep(0.5)
        self._dur_value.setDecimals(2)
        self._dur_unit = QComboBox()
        for u in DurationUnit:
            self._dur_unit.addItem(u.value)
        self._dur_value.valueChanged.connect(self._on_duration_changed)
        self._dur_unit.currentTextChanged.connect(self._on_duration_changed)
        dur_row.addWidget(self._dur_value)
        dur_row.addWidget(self._dur_unit)
        layout.addRow("Duration", dur_row)

        # Priority
        self._priority_combo = QComboBox()
        for p in Priority:
            self._priority_combo.addItem(p.name, p)
        self._priority_combo.currentIndexChanged.connect(self._on_priority_changed)
        layout.addRow("Priority", self._priority_combo)

        # Risk
        self._risk_combo = QComboBox()
        for r in RiskLevel:
            self._risk_combo.addItem(r.name, r)
        self._risk_combo.currentIndexChanged.connect(self._on_risk_changed)
        layout.addRow("Risk", self._risk_combo)

        # Tags
        self._tags_edit = QLineEdit()
        self._tags_edit.setPlaceholderText("comma-separated")
        self._tags_edit.editingFinished.connect(self._on_tags_changed)
        layout.addRow("Tags", self._tags_edit)

        self._layout.addWidget(group)

    def _build_schedule_group(self) -> None:
        group = QGroupBox("Schedule (computed)")
        layout = QFormLayout(group)
        layout.setSpacing(4)

        self._lbl_es = QLabel("—")
        self._lbl_ef = QLabel("—")
        self._lbl_ls = QLabel("—")
        self._lbl_lf = QLabel("—")
        self._lbl_slack = QLabel("—")
        self._lbl_critical = QLabel("—")

        for lbl in [self._lbl_es, self._lbl_ef, self._lbl_ls, self._lbl_lf,
                    self._lbl_slack, self._lbl_critical]:
            lbl.setStyleSheet(
                f"color: {Palette.TEXT_PRIMARY}; font-family: 'JetBrains Mono', monospace; font-size: 11px;"
            )

        layout.addRow("Early start", self._lbl_es)
        layout.addRow("Early finish", self._lbl_ef)
        layout.addRow("Late start", self._lbl_ls)
        layout.addRow("Late finish", self._lbl_lf)
        layout.addRow("Total slack", self._lbl_slack)
        layout.addRow("Status", self._lbl_critical)

        # Earliest-start / latest-finish constraints
        self._es_constraint = QDateTimeEdit()
        self._es_constraint.setCalendarPopup(True)
        self._es_constraint.setDisplayFormat("yyyy-MM-dd HH:mm")
        self._es_constraint.setSpecialValueText("(none)")
        self._es_constraint.dateTimeChanged.connect(self._on_es_constraint_changed)
        layout.addRow("Earliest start", self._es_constraint)

        self._lf_constraint = QDateTimeEdit()
        self._lf_constraint.setCalendarPopup(True)
        self._lf_constraint.setDisplayFormat("yyyy-MM-dd HH:mm")
        self._lf_constraint.setSpecialValueText("(none)")
        self._lf_constraint.dateTimeChanged.connect(self._on_lf_constraint_changed)
        layout.addRow("Latest finish", self._lf_constraint)

        self._layout.addWidget(group)

    def _build_status_group(self) -> None:
        group = QGroupBox("Status & Progress")
        layout = QVBoxLayout(group)

        self._status_combo = QComboBox()
        for s in TaskStatus:
            self._status_combo.addItem(s.value, s)
        self._status_combo.currentIndexChanged.connect(self._on_status_changed)
        layout.addWidget(self._status_combo)

        # Progress slider
        prog_row = QHBoxLayout()
        self._progress_slider = QSlider(Qt.Horizontal)
        self._progress_slider.setRange(0, 100)
        self._progress_slider.setSingleStep(5)
        self._progress_slider.valueChanged.connect(self._on_progress_changed)
        prog_row.addWidget(self._progress_slider)
        self._progress_label = QLabel("0%")
        self._progress_label.setFixedWidth(36)
        self._progress_label.setStyleSheet(
            f"color: {Palette.GOLD_BRIGHT}; font-weight: bold; "
            f"font-family: 'JetBrains Mono', monospace;"
        )
        prog_row.addWidget(self._progress_label)
        layout.addLayout(prog_row)

        # Legal transitions hint
        self._transitions_label = QLabel("")
        self._transitions_label.setWordWrap(True)
        self._transitions_label.setStyleSheet(
            f"color: {Palette.TEXT_TERTIARY}; font-size: 10px; padding-top: 4px;"
        )
        layout.addWidget(self._transitions_label)

        self._layout.addWidget(group)

    def _build_pert_group(self) -> None:
        group = QGroupBox("PERT 3-Point Estimate")
        layout = QFormLayout(group)

        self._pert_o = QDoubleSpinBox()
        self._pert_m = QDoubleSpinBox()
        self._pert_p = QDoubleSpinBox()
        for sb in [self._pert_o, self._pert_m, self._pert_p]:
            sb.setRange(0.01, 9999.0)
            sb.setSingleStep(0.5)
            sb.setDecimals(2)
        self._pert_unit = QComboBox()
        for u in DurationUnit:
            self._pert_unit.addItem(u.value)

        self._pert_o.valueChanged.connect(self._on_pert_changed)
        self._pert_m.valueChanged.connect(self._on_pert_changed)
        self._pert_p.valueChanged.connect(self._on_pert_changed)

        layout.addRow("Optimistic", self._pert_o)
        layout.addRow("Most likely", self._pert_m)
        layout.addRow("Pessimistic", self._pert_p)
        layout.addRow("Unit", self._pert_unit)

        self._pert_expected = QLabel("—")
        self._pert_expected.setStyleSheet(
            f"color: {Palette.GOLD_BRIGHT}; font-family: 'JetBrains Mono', monospace;"
        )
        layout.addRow("Expected", self._pert_expected)

        self._clear_pert_btn = QPushButton("Clear PERT")
        self._clear_pert_btn.clicked.connect(self._on_clear_pert)
        layout.addRow(self._clear_pert_btn)

        self._layout.addWidget(group)

    def _build_actions_group(self) -> None:
        group = QGroupBox("Quick Actions")
        layout = QVBoxLayout(group)

        # Status quick-change buttons
        for status in [TaskStatus.READY, TaskStatus.ACTIVE,
                       TaskStatus.BLOCKED, TaskStatus.DONE, TaskStatus.CANCELLED]:
            btn = QPushButton(f"→ {status.value.upper()}")
            btn.clicked.connect(lambda _=False, s=status: self._quick_change_status(s))
            layout.addWidget(btn)

        self._layout.addWidget(group)

    # ---- Loading ----
    def load_task(self, task: Optional[Task]) -> None:
        self._current_task = task
        self._suppress_updates = True
        try:
            if task is None:
                self._task_title_label.setText("No task selected")
                self._task_title_label.setStyleSheet(
                    f"color: {Palette.TEXT_TERTIARY}; font-size: 14px; "
                    f"font-weight: bold; padding: 4px 0 8px 0; "
                    f"border-bottom: 1px solid {Palette.BORDER_SUBTLE};"
                )
                self._set_enabled(False)
                return

            self._task_title_label.setText(task.title)
            self._task_title_label.setStyleSheet(
                f"color: {Palette.GOLD_BRIGHT if task.is_critical else Palette.TEXT_PRIMARY}; "
                f"font-size: 14px; font-weight: bold; padding: 4px 0 8px 0; "
                f"border-bottom: 1px solid {Palette.BORDER_SUBTLE};"
            )

            # Basic
            self._title_edit.setText(task.title)
            self._desc_edit.setPlainText(task.description)
            self._dur_value.setValue(task.duration.to_unit(DurationUnit.DAY))
            self._dur_unit.setCurrentText(DurationUnit.DAY.value)
            self._priority_combo.setCurrentIndex(int(task.priority))
            self._risk_combo.setCurrentText(task.risk.name)
            self._tags_edit.setText(", ".join(sorted(str(t) for t in task.tags)))

            # Schedule
            from ...core.shamsi import format_shamsi
            self._lbl_es.setText(format_shamsi(task.early_start, include_time=True) if task.early_start else "—")
            self._lbl_ef.setText(format_shamsi(task.early_finish, include_time=True) if task.early_finish else "—")
            self._lbl_ls.setText(format_shamsi(task.late_start, include_time=True) if task.late_start else "—")
            self._lbl_lf.setText(format_shamsi(task.late_finish, include_time=True) if task.late_finish else "—")
            if task.slack:
                self._lbl_slack.setText(task.slack.total_slack.humanize())
                self._lbl_critical.setText("CRITICAL" if task.is_critical else "non-critical")
                self._lbl_critical.setStyleSheet(
                    f"color: {Palette.GOLD_BRIGHT if task.is_critical else Palette.TEXT_SECONDARY}; "
                    f"font-weight: bold; font-family: 'JetBrains Mono', monospace;"
                )
            else:
                self._lbl_slack.setText("—")
                self._lbl_critical.setText("—")

            # Constraints
            if task.earliest_start:
                self._es_constraint.setDateTime(QDateTime(task.earliest_start))
            else:
                self._es_constraint.setSpecialValueText("(none)")
                self._es_constraint.setDateTime(QDateTime.currentDateTime())
            if task.latest_finish:
                self._lf_constraint.setDateTime(QDateTime(task.latest_finish))
            else:
                self._lf_constraint.setSpecialValueText("(none)")
                self._lf_constraint.setDateTime(QDateTime.currentDateTime())

            # Status
            self._status_combo.setCurrentIndex(list(TaskStatus).index(task.status))
            self._progress_slider.setValue(task.progress.percent)
            self._progress_label.setText(f"{task.progress.percent}%")
            legal = LEGAL_TRANSITIONS.get(task.status, frozenset())
            self._transitions_label.setText(
                f"Allowed transitions: {', '.join(s.value for s in legal) or '(terminal)'}"
            )

            # PERT
            if task.pert is not None:
                self._pert_o.setValue(task.pert.optimistic.to_unit(DurationUnit.DAY))
                self._pert_m.setValue(task.pert.most_likely.to_unit(DurationUnit.DAY))
                self._pert_p.setValue(task.pert.pessimistic.to_unit(DurationUnit.DAY))
                self._pert_expected.setText(task.pert.expected.humanize())
            else:
                self._pert_o.setValue(0)
                self._pert_m.setValue(0)
                self._pert_p.setValue(0)
                self._pert_expected.setText("—")

            self._set_enabled(True)
        finally:
            self._suppress_updates = False

    def _set_enabled(self, enabled: bool) -> None:
        for w in self.findChildren(QWidget):
            w.setEnabled(enabled)

    # ---- Edit handlers ----
    def _on_title_changed(self, text: str) -> None:
        if self._suppress_updates or self._current_task is None:
            return
        self.task_service.update_task(self._current_task.id, title=text, recalc=False)

    def _on_desc_changed(self) -> None:
        if self._suppress_updates or self._current_task is None:
            return
        self.task_service.update_task(self._current_task.id,
                                      description=self._desc_edit.toPlainText(),
                                      recalc=False)

    def _on_duration_changed(self) -> None:
        if self._suppress_updates or self._current_task is None:
            return
        amount = self._dur_value.value()
        unit = DurationUnit(self._dur_unit.currentText())
        self.task_service.update_task(self._current_task.id,
                                      duration=Duration.of(amount, unit))

    def _on_priority_changed(self, idx: int) -> None:
        if self._suppress_updates or self._current_task is None:
            return
        p = self._priority_combo.itemData(idx)
        if p is not None:
            self.task_service.update_task(self._current_task.id, priority=p, recalc=False)

    def _on_risk_changed(self, idx: int) -> None:
        if self._suppress_updates or self._current_task is None:
            return
        r = self._risk_combo.itemData(idx)
        if r is not None:
            self.task_service.update_task(self._current_task.id, risk=r, recalc=False)

    def _on_tags_changed(self) -> None:
        if self._suppress_updates or self._current_task is None:
            return
        text = self._tags_edit.text()
        parts = [p.strip() for p in text.split(",") if p.strip()]
        new_tags = set()
        for p in parts:
            try:
                new_tags.add(Tag(p))
            except ValueError:
                pass
        # Diff
        to_remove = self._current_task.tags - new_tags
        to_add = new_tags - self._current_task.tags
        for t in to_remove:
            self._current_task.remove_tag(t)
        for t in to_add:
            self._current_task.add_tag(t)
        if to_add or to_remove:
            # Trigger update event by touching the task
            self._current_task.touch()

    def _on_status_changed(self, idx: int) -> None:
        if self._suppress_updates or self._current_task is None:
            return
        new_status = self._status_combo.itemData(idx)
        if new_status is None or new_status == self._current_task.status:
            return
        try:
            self.task_service.change_status(self._current_task.id, new_status)
        except ValueError:
            # Revert
            self._suppress_updates = True
            self._status_combo.setCurrentIndex(list(TaskStatus).index(self._current_task.status))
            self._suppress_updates = False

    def _on_progress_changed(self, val: int) -> None:
        if self._suppress_updates or self._current_task is None:
            return
        self._progress_label.setText(f"{val}%")
        self.task_service.update_task(self._current_task.id, progress=val, recalc=False)

    def _on_es_constraint_changed(self, dt) -> None:
        if self._suppress_updates or self._current_task is None:
            return
        self._current_task.earliest_start = dt.toPython() if hasattr(dt, 'toPython') else dt
        self._current_task.touch()
        self.task_service.scheduling.recalculate()

    def _on_lf_constraint_changed(self, dt) -> None:
        if self._suppress_updates or self._current_task is None:
            return
        self._current_task.latest_finish = dt.toPython() if hasattr(dt, 'toPython') else dt
        self._current_task.touch()
        self.task_service.scheduling.recalculate()

    def _on_pert_changed(self) -> None:
        if self._suppress_updates or self._current_task is None:
            return
        if self._pert_o.value() == 0 and self._pert_m.value() == 0 and self._pert_p.value() == 0:
            return
        unit = DurationUnit(self._pert_unit.currentText())
        try:
            opt = Duration.of(self._pert_o.value(), unit)
            ml = Duration.of(self._pert_m.value(), unit)
            pess = Duration.of(self._pert_p.value(), unit)
            if not (opt.minutes <= ml.minutes <= pess.minutes):
                self._pert_expected.setText("invalid: O≤M≤P required")
                return
            self._current_task.pert = PertEstimate(opt, ml, pess)
            self._current_task.touch()
            self._pert_expected.setText(self._current_task.pert.expected.humanize())
            self.task_service.scheduling.recalculate()
        except ValueError as e:
            self._pert_expected.setText(f"error: {e}")

    def _on_clear_pert(self) -> None:
        if self._current_task is None:
            return
        self._current_task.pert = None
        self._current_task.touch()
        self._pert_o.setValue(0)
        self._pert_m.setValue(0)
        self._pert_p.setValue(0)
        self._pert_expected.setText("—")
        self.task_service.scheduling.recalculate()

    def _quick_change_status(self, new_status: TaskStatus) -> None:
        if self._current_task is None:
            return
        try:
            self.task_service.change_status(self._current_task.id, new_status)
        except ValueError as e:
            from PySide6.QtWidgets import QMessageBox
            QMessageBox.warning(self, "Illegal Transition", str(e))
