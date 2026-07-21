"""
EventEditorDialog — full editor for a calendar event.

Mirrors Google Calendar's event editor with:
  - Title, description, location
  - Start/end date+time (or all-day)
  - Calendar selector
  - Color override
  - Event type (normal, meeting, focus time, out of office, etc.)
  - Availability (busy/free/tentative)
  - Recurrence (with presets + custom)
  - Attendees (add/remove, RSVP status)
  - Reminders (multiple, with method)
  - Meeting link
  - Attachments (file paths)
"""
from __future__ import annotations

from datetime import datetime, timedelta
from typing import Optional

from PySide6.QtCore import Qt, QDateTime, QDate, QTime, Signal
from PySide6.QtGui import QFont, QColor
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QFormLayout, QLabel, QLineEdit,
    QTextEdit, QComboBox, QSpinBox, QDoubleSpinBox, QPushButton, QFrame,
    QDialogButtonBox, QGroupBox, QCheckBox, QDateTimeEdit, QDateEdit,
    QTimeEdit, QRadioButton, QButtonGroup, QScrollArea, QWidget, QSizePolicy,
    QListWidget, QListWidgetItem, QInputDialog, QMessageBox, QColorDialog,
    QFileDialog, QSpacerItem,
)

from ...calendar import (
    CalendarStore, Event as CalEvent, Calendar, EventType, Availability, EventStatus,
    RecurrenceRule, RecurrenceFrequency, ByDay, Weekday,
    Reminder, ReminderMethod, Attendee, AttendeeStatus,
    PRESET_RULES, CALENDAR_COLORS,
)
from ..theme import Palette


class EventEditorDialog(QDialog):
    """Full event editor."""

    def __init__(self, event: Optional[Event], store: CalendarStore,
                 parent=None) -> None:
        super().__init__(parent)
        self.evt = event
        self.store = store
        self.setWindowTitle("Edit Event" if event else "New Event")
        self.setMinimumSize(620, 720)
        self.setStyleSheet(f"background-color: {Palette.BG_PRIMARY};")

        # Scrollable layout (the dialog has a lot of fields)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setStyleSheet("QScrollArea { background: transparent; border: none; }")

        container = QWidget()
        container.setStyleSheet(f"background-color: {Palette.BG_PRIMARY};")
        self._layout = QVBoxLayout(container)
        self._layout.setContentsMargins(20, 20, 20, 20)
        self._layout.setSpacing(12)

        scroll.setWidget(container)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(scroll)

        # Build sections
        self._build_header()
        self._build_basic_group()
        self._build_time_group()
        self._build_classification_group()
        self._build_recurrence_group()
        self._build_attendees_group()
        self._build_reminders_group()
        self._build_extras_group()

        self._layout.addStretch()

        # Buttons
        button_row = QHBoxLayout()
        if event is not None:
            delete_btn = QPushButton("Delete")
            delete_btn.setProperty("variant", "danger")
            delete_btn.clicked.connect(self._on_delete)
            button_row.addWidget(delete_btn)
        button_row.addStretch()
        cancel_btn = QPushButton("Cancel")
        cancel_btn.clicked.connect(self.reject)
        button_row.addWidget(cancel_btn)
        save_btn = QPushButton("Save")
        save_btn.setProperty("variant", "primary")
        save_btn.clicked.connect(self._on_save)
        button_row.addWidget(save_btn)
        outer.addLayout(button_row)

        # Load existing event data
        if event is not None:
            self._load_from_event(event)
        else:
            # Default: today at 9am for 1 hour
            now = datetime.now().replace(minute=0, second=0, microsecond=0)
            if now.hour < 9:
                now = now.replace(hour=9)
            self._start_dt.setDateTime(QDateTime(now))
            self._end_dt.setDateTime(QDateTime(now + timedelta(hours=1)))
            # Default calendar = first visible
            for cal in store.calendars():
                if cal.visible and not cal.is_readonly:
                    self._calendar_combo.setCurrentText(cal.name)
                    break

    def _build_header(self) -> None:
        title = QLabel("EVENT EDITOR")
        title.setStyleSheet(
            f"color: {Palette.GOLD_PRIMARY}; font-size: 11px; "
            f"font-weight: bold; letter-spacing: 2px;"
        )
        self._layout.addWidget(title)

    def _build_basic_group(self) -> None:
        group = QGroupBox("Basic")
        form = QFormLayout(group)
        form.setSpacing(6)

        self._title_edit = QLineEdit()
        self._title_edit.setPlaceholderText("Add title")
        form.addRow("Title", self._title_edit)

        self._location_edit = QLineEdit()
        self._location_edit.setPlaceholderText("Add location")
        form.addRow("Location", self._location_edit)

        self._desc_edit = QTextEdit()
        self._desc_edit.setFixedHeight(80)
        self._desc_edit.setPlaceholderText("Add description")
        form.addRow("Description", self._desc_edit)

        # Calendar selector
        self._calendar_combo = QComboBox()
        self._original_calendar_id: Optional[str] = None  # track to prevent drift
        for cal in self.store.calendars():
            if not cal.is_readonly:
                self._calendar_combo.addItem(cal.name, cal.id)
        # If editing an event on a readonly calendar, add it to the combo
        # so the calendar_id doesn't drift to a different calendar on save
        if self.evt is not None and self.evt.calendar_id:
            self._original_calendar_id = self.evt.calendar_id
            found = False
            for i in range(self._calendar_combo.count()):
                if self._calendar_combo.itemData(i) == self.evt.calendar_id:
                    found = True
                    break
            if not found:
                cal = self.store.get_calendar(self.evt.calendar_id)
                if cal:
                    self._calendar_combo.addItem(cal.name + " (read-only)", cal.id)
        form.addRow("Calendar", self._calendar_combo)

        # Color override
        color_row = QHBoxLayout()
        self._color_checkbox = QCheckBox("Custom color:")
        self._color_checkbox.toggled.connect(self._on_color_toggle)
        color_row.addWidget(self._color_checkbox)
        self._color_btn = QPushButton()
        self._color_btn.setFixedSize(60, 24)
        self._color_btn.setEnabled(False)
        self._color_btn.clicked.connect(self._pick_color)
        self._color_btn.setStyleSheet(
            f"background-color: {Palette.GOLD_PRIMARY}; border: 1px solid {Palette.BORDER_NORMAL};"
        )
        self._custom_color = Palette.GOLD_PRIMARY
        color_row.addWidget(self._color_btn)
        color_row.addStretch()
        form.addRow("", color_row)

        self._layout.addWidget(group)

    def _build_time_group(self) -> None:
        group = QGroupBox("Time")
        form = QFormLayout(group)
        form.setSpacing(6)

        # All-day checkbox
        self._all_day = QCheckBox("All day")
        self._all_day.toggled.connect(self._on_all_day_toggle)
        form.addRow("", self._all_day)

        # Start
        self._start_dt = QDateTimeEdit()
        self._start_dt.setCalendarPopup(True)
        self._start_dt.setDisplayFormat("yyyy-MM-dd HH:mm")
        form.addRow("Starts", self._start_dt)

        # End
        self._end_dt = QDateTimeEdit()
        self._end_dt.setCalendarPopup(True)
        self._end_dt.setDisplayFormat("yyyy-MM-dd HH:mm")
        form.addRow("Ends", self._end_dt)

        # Timezone label (informational)
        tz = QLabel("Time zone: local")
        tz.setStyleSheet(f"color: {Palette.TEXT_TERTIARY}; font-size: 11px;")
        form.addRow("", tz)

        self._layout.addWidget(group)

    def _build_classification_group(self) -> None:
        group = QGroupBox("Classification")
        form = QFormLayout(group)

        # Event type
        self._type_combo = QComboBox()
        for t in EventType:
            self._type_combo.addItem(t.value.replace("_", " ").title(), t)
        form.addRow("Type", self._type_combo)

        # Completed checkbox (for tasks)
        self._completed_check = QCheckBox("Completed")
        self._completed_check.setStyleSheet(f"""
            QCheckBox {{ color: {Palette.TEXT_PRIMARY}; spacing: 8px; }}
            QCheckBox::indicator {{ width: 18px; height: 18px; border: 2px solid {Palette.BORDER_STRONG}; border-radius: 4px; background: {Palette.BG_TERTIARY}; }}
            QCheckBox::indicator:checked {{ background: #5A8A5A; border: 2px solid #5A8A5A; }}
        """)
        form.addRow("Done", self._completed_check)

        # Availability
        self._avail_combo = QComboBox()
        for a in Availability:
            self._avail_combo.addItem(a.value.replace("_", " ").title(), a)
        form.addRow("Availability", self._avail_combo)

        # Status
        self._status_combo = QComboBox()
        for s in EventStatus:
            self._status_combo.addItem(s.value.title(), s)
        form.addRow("Status", self._status_combo)

        self._layout.addWidget(group)

    def _build_recurrence_group(self) -> None:
        group = QGroupBox("Recurrence")
        layout = QVBoxLayout(group)

        # Preset radio buttons
        self._recur_none = QRadioButton("One-time (no repeat)")
        self._recur_preset = QRadioButton("Preset:")
        self._recur_custom = QRadioButton("Custom")
        self._recur_group = QButtonGroup(self)
        self._recur_group.addButton(self._recur_none)
        self._recur_group.addButton(self._recur_preset)
        self._recur_group.addButton(self._recur_custom)
        self._recur_none.setChecked(True)

        layout.addWidget(self._recur_none)

        preset_row = QHBoxLayout()
        preset_row.addWidget(self._recur_preset)
        self._preset_combo = QComboBox()
        for name in PRESET_RULES.keys():
            self._preset_combo.addItem(name)
        preset_row.addWidget(self._preset_combo, stretch=1)
        layout.addLayout(preset_row)

        # Custom controls
        layout.addWidget(self._recur_custom)
        custom_row = QFormLayout()
        self._custom_freq = QComboBox()
        for f in RecurrenceFrequency:
            self._custom_freq.addItem(f.value.title(), f)
        custom_row.addRow("Frequency", self._custom_freq)
        self._custom_interval = QSpinBox()
        self._custom_interval.setRange(1, 99)
        self._custom_interval.setValue(1)
        custom_row.addRow("Every", self._custom_interval)
        self._custom_count = QSpinBox()
        self._custom_count.setRange(0, 999)
        self._custom_count.setSpecialValueText("(no limit)")
        custom_row.addRow("Count (0 = forever)", self._custom_count)
        layout.addLayout(custom_row)

        self._layout.addWidget(group)

    def _build_attendees_group(self) -> None:
        group = QGroupBox("Attendees")
        layout = QVBoxLayout(group)

        self._attendees_list = QListWidget()
        self._attendees_list.setStyleSheet(f"QListWidget {{ background-color: {Palette.BG_TERTIARY}; border: 1px solid {Palette.BORDER_NORMAL}; border-radius: 4px; }}")
        layout.addWidget(self._attendees_list)

        add_row = QHBoxLayout()
        self._att_name_edit = QLineEdit()
        self._att_name_edit.setPlaceholderText("Name")
        add_row.addWidget(self._att_name_edit)
        self._att_email_edit = QLineEdit()
        self._att_email_edit.setPlaceholderText("Email (optional)")
        add_row.addWidget(self._att_email_edit)
        add_btn = QPushButton("+ Add")
        add_btn.clicked.connect(self._add_attendee)
        add_row.addWidget(add_btn)
        remove_btn = QPushButton("Remove")
        remove_btn.clicked.connect(self._remove_attendee)
        add_row.addWidget(remove_btn)
        layout.addLayout(add_row)

        self._layout.addWidget(group)

    def _build_reminders_group(self) -> None:
        group = QGroupBox("Reminders")
        layout = QVBoxLayout(group)

        self._reminders_list = QListWidget()
        self._reminders_list.setStyleSheet(f"QListWidget {{ background-color: {Palette.BG_TERTIARY}; border: 1px solid {Palette.BORDER_NORMAL}; border-radius: 4px; }}")
        layout.addWidget(self._reminders_list)

        add_row = QHBoxLayout()
        self._reminder_minutes = QSpinBox()
        self._reminder_minutes.setRange(0, 40320)  # up to 4 weeks
        self._reminder_minutes.setValue(30)
        add_row.addWidget(QLabel("Minutes before:"))
        add_row.addWidget(self._reminder_minutes)
        self._reminder_method = QComboBox()
        self._reminder_method.addItem("Popup", ReminderMethod.POPUP)
        self._reminder_method.addItem("Email", ReminderMethod.EMAIL)
        add_row.addWidget(self._reminder_method)
        add_btn = QPushButton("+ Add")
        add_btn.clicked.connect(self._add_reminder)
        add_row.addWidget(add_btn)
        remove_btn = QPushButton("Remove")
        remove_btn.clicked.connect(self._remove_reminder)
        add_row.addWidget(remove_btn)
        layout.addLayout(add_row)

        self._layout.addWidget(group)

    def _build_extras_group(self) -> None:
        group = QGroupBox("Meeting & Attachments")
        form = QFormLayout(group)

        self._meeting_link = QLineEdit()
        self._meeting_link.setPlaceholderText("https://meet.google.com/...")
        form.addRow("Meeting link", self._meeting_link)

        self._attachments_list = QListWidget()
        self._attachments_list.setStyleSheet(f"QListWidget {{ background-color: {Palette.BG_TERTIARY}; border: 1px solid {Palette.BORDER_NORMAL}; border-radius: 4px; }}")
        form.addRow("Attachments", self._attachments_list)

        att_row = QHBoxLayout()
        add_att = QPushButton("+ Add file...")
        add_att.clicked.connect(self._add_attachment)
        att_row.addWidget(add_att)
        rm_att = QPushButton("Remove")
        rm_att.clicked.connect(self._remove_attachment)
        att_row.addWidget(rm_att)
        att_row.addStretch()
        form.addRow("", att_row)

        self._layout.addWidget(group)

    # ---- Load existing event ----
    def _load_from_event(self, event: Event) -> None:
        self._title_edit.setText(event.title)
        self._location_edit.setText(event.location)
        self._desc_edit.setPlainText(event.description)
        # Calendar
        for i in range(self._calendar_combo.count()):
            if self._calendar_combo.itemData(i) == event.calendar_id:
                self._calendar_combo.setCurrentIndex(i)
                break
        # Color
        if event.color:
            self._color_checkbox.setChecked(True)
            self._custom_color = event.color
            self._color_btn.setStyleSheet(
                f"background-color: {event.color}; border: 1px solid {Palette.BORDER_NORMAL};"
            )
        # Time
        self._all_day.setChecked(event.all_day)
        self._start_dt.setDateTime(QDateTime(event.start))
        self._end_dt.setDateTime(QDateTime(event.end))
        # Classification
        for i in range(self._type_combo.count()):
            if self._type_combo.itemData(i) == event.event_type:
                self._type_combo.setCurrentIndex(i)
                break
        for i in range(self._avail_combo.count()):
            if self._avail_combo.itemData(i) == event.availability:
                self._avail_combo.setCurrentIndex(i)
                break
        for i in range(self._status_combo.count()):
            if self._status_combo.itemData(i) == event.status:
                self._status_combo.setCurrentIndex(i)
                break
        # Completed state
        self._completed_check.setChecked(event.completed)
        # Recurrence
        if event.recurrence is None:
            self._recur_none.setChecked(True)
        else:
            # Check presets first
            matched_preset = None
            for name, rule in PRESET_RULES.items():
                if rule.to_rrule_str() == event.recurrence.to_rrule_str():
                    matched_preset = name
                    break
            if matched_preset:
                self._recur_preset.setChecked(True)
                self._preset_combo.setCurrentText(matched_preset)
            else:
                self._recur_custom.setChecked(True)
                self._custom_freq.setCurrentText(event.recurrence.freq.value.title())
                self._custom_interval.setValue(event.recurrence.interval)
                self._custom_count.setValue(event.recurrence.count or 0)
        # Attendees
        for att in event.attendees:
            item = QListWidgetItem(f"{att.name} <{att.email}>  [{att.status.value}]")
            item.setData(Qt.UserRole, att)
            self._attendees_list.addItem(item)
        # Reminders
        for rem in event.reminders:
            item = QListWidgetItem(f"{rem.minutes_before} min before ({rem.method.value})")
            item.setData(Qt.UserRole, rem)
            self._reminders_list.addItem(item)
        # Meeting link
        self._meeting_link.setText(event.meeting_link)
        # Attachments
        for att in event.attachments:
            self._attachments_list.addItem(att)

    # ---- Interaction handlers ----
    def _on_color_toggle(self, checked: bool) -> None:
        self._color_btn.setEnabled(checked)

    def _pick_color(self) -> None:
        color = QColorDialog.getColor(QColor(self._custom_color), self)
        if color.isValid():
            self._custom_color = color.name()
            self._color_btn.setStyleSheet(
                f"background-color: {self._custom_color}; "
                f"border: 1px solid {Palette.BORDER_NORMAL};"
            )

    def _on_all_day_toggle(self, checked: bool) -> None:
        if checked:
            self._start_dt.setDisplayFormat("yyyy-MM-dd")
            self._end_dt.setDisplayFormat("yyyy-MM-dd")
        else:
            self._start_dt.setDisplayFormat("yyyy-MM-dd HH:mm")
            self._end_dt.setDisplayFormat("yyyy-MM-dd HH:mm")

    def _add_attendee(self) -> None:
        name = self._att_name_edit.text().strip()
        email = self._att_email_edit.text().strip()
        if not name:
            return
        att = Attendee(name=name, email=email)
        item = QListWidgetItem(f"{name} <{email}>  [{att.status.value}]")
        item.setData(Qt.UserRole, att)
        self._attendees_list.addItem(item)
        self._att_name_edit.clear()
        self._att_email_edit.clear()

    def _remove_attendee(self) -> None:
        for item in self._attendees_list.selectedItems():
            self._attendees_list.takeItem(self._attendees_list.row(item))

    def _add_reminder(self) -> None:
        minutes = self._reminder_minutes.value()
        method = self._reminder_method.currentData()
        rem = Reminder(minutes_before=minutes, method=method)
        item = QListWidgetItem(f"{minutes} min before ({method.value})")
        item.setData(Qt.UserRole, rem)
        self._reminders_list.addItem(item)

    def _remove_reminder(self) -> None:
        for item in self._reminders_list.selectedItems():
            self._reminders_list.takeItem(self._reminders_list.row(item))

    def _add_attachment(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "Add Attachment")
        if path:
            self._attachments_list.addItem(path)

    def _remove_attachment(self) -> None:
        for item in self._attachments_list.selectedItems():
            self._attachments_list.takeItem(self._attachments_list.row(item))

    # ---- Save ----
    def _on_save(self) -> None:
        title = self._title_edit.text().strip()
        if not title:
            QMessageBox.warning(self, "Required", "Title is required.")
            return

        cal_id = self._calendar_combo.currentData()
        if cal_id is None:
            QMessageBox.warning(self, "Required", "Calendar is required.")
            return

        # Prevent calendar_id drift if the original calendar isn't in the combo
        if self._original_calendar_id and cal_id != self._original_calendar_id:
            # Check if the original calendar still exists
            if self.store.get_calendar(self._original_calendar_id):
                cal_id = self._original_calendar_id

        start = self._start_dt.dateTime().toPython()
        end = self._end_dt.dateTime().toPython()
        if end < start:
            QMessageBox.warning(self, "Time", "End must be after start.")
            return

        # Build recurrence rule
        recurrence = None
        if self._recur_preset.isChecked():
            name = self._preset_combo.currentText()
            recurrence = PRESET_RULES.get(name)
        elif self._recur_custom.isChecked():
            count = self._custom_count.value() or None
            recurrence = RecurrenceRule(
                freq=self._custom_freq.currentData(),
                interval=self._custom_interval.value(),
                count=count,
            )

        # Build attendees / reminders
        attendees = []
        for i in range(self._attendees_list.count()):
            item = self._attendees_list.item(i)
            attendees.append(item.data(Qt.UserRole))
        reminders = []
        for i in range(self._reminders_list.count()):
            item = self._reminders_list.item(i)
            reminders.append(item.data(Qt.UserRole))
        attachments = []
        for i in range(self._attachments_list.count()):
            attachments.append(self._attachments_list.item(i).text())

        color = self._custom_color if self._color_checkbox.isChecked() else None

        completed = self._completed_check.isChecked()

        if self.evt is None:
            # Create new
            evt = CalEvent.create(
                calendar_id=cal_id,
                title=title,
                start=start,
                end=end,
                description=self._desc_edit.toPlainText(),
                location=self._location_edit.text(),
                all_day=self._all_day.isChecked(),
                event_type=self._type_combo.currentData(),
                availability=self._avail_combo.currentData(),
                status=self._status_combo.currentData(),
                color=color,
                recurrence=recurrence,
                attendees=attendees,
                reminders=reminders,
                attachments=attachments,
                meeting_link=self._meeting_link.text(),
                completed=completed,
            )
            self.store.add_event(evt)
        else:
            # Update existing
            self.store.update_event(
                self.evt.id,
                calendar_id=cal_id,
                title=title,
                description=self._desc_edit.toPlainText(),
                location=self._location_edit.text(),
                start=start,
                end=end,
                all_day=self._all_day.isChecked(),
                event_type=self._type_combo.currentData(),
                availability=self._avail_combo.currentData(),
                status=self._status_combo.currentData(),
                color=color,
                recurrence=recurrence,
                attendees=attendees,
                reminders=reminders,
                attachments=attachments,
                meeting_link=self._meeting_link.text(),
                completed=completed,
            )
        self.accept()

    def _on_delete(self) -> None:
        if self.evt is None:
            return
        ret = QMessageBox.question(
            self, "Delete Event",
            f"Delete '{self.evt.title}'?\nThis cannot be undone.",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No,
        )
        if ret == QMessageBox.Yes:
            self.store.delete_event(self.evt.id)
            self.accept()
