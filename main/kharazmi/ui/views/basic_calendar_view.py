"""
BasicCalendarView — Google-Calendar-style month planner.

This is the ONLY view shown in the Basic plan. The user can:
  - See a month grid (Saturday..Friday, Persian Shamsi)
  - Click a day to add a task for that day
  - Drag tasks between days to reschedule
  - Switch between month / week / day layouts
  - Search / filter
  - Color-code by status

No graph, no Gantt, no Kanban, no statistics, no console — just a
clean calendar planner.
"""
from __future__ import annotations

from datetime import datetime, timedelta
from typing import Optional

from PySide6.QtCore import (
    Qt, QRectF, QPointF, QSize, Signal, QMimeData, QPoint,
)
from PySide6.QtGui import (
    QPainter, QPen, QBrush, QColor, QFont, QPainterPath, QLinearGradient,
    QAction, QMouseEvent, QDragEnterEvent, QDropEvent, QFontMetrics,
    QKeySequence, QShortcut,
)
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, QPushButton,
    QFrame, QScrollArea, QGridLayout, QSizePolicy, QToolButton,
    QComboBox, QMenu, QInputDialog, QMessageBox, QSpacerItem,
    QGraphicsDropShadowEffect, QApplication,
)

from ...core import (
    Project, Task, TaskId, TaskStatus, Priority,
    Duration, DurationUnit, ShamsiDate, format_shamsi,
    SHAMSI_MONTHS_FA, SHAMSI_MONTHS_EN,
    SHAMSI_WEEKDAYS_FA, SHAMSI_WEEKDAYS_SHORT_EN,
    shamsi_month_grid, iterate_week, days_in_month,
)
from ...services import TaskService
from ..theme import Palette, status_color
from ..icons import get_icon


# ---- Task chips in calendar cells ----

class CalendarTaskChip(QFrame):
    """A small task chip displayed inside a calendar cell."""
    chipClicked = Signal(str)
    chipDoubleClicked = Signal(str)
    DRAG_MIME = "application/x-kharazmi-task-id"

    def __init__(self, task: Task, parent: QWidget = None) -> None:
        super().__init__(parent)
        self.task = task
        self.setFixedHeight(22)
        self.setCursor(Qt.PointingHandCursor)
        self.setObjectName("chip")
        bg = status_color(task.status.value)
        text_color = Palette.TEXT_ON_GOLD if task.is_critical else Palette.TEXT_PRIMARY
        self.setStyleSheet(f"""
            QFrame#chip {{
                background-color: {bg};
                border-left: 2px solid {Palette.GOLD_BRIGHT if task.is_critical else 'transparent'};
                border-radius: 3px;
                margin: 1px 2px;
            }}
        """)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(6, 0, 6, 0)
        layout.setSpacing(4)

        title = QLabel(task.title)
        title.setStyleSheet(
            f"color: {text_color}; font-size: 11px; "
            f"font-weight: {'bold' if task.is_critical else 'normal'};"
        )
        title.setWordWrap(False)
        layout.addWidget(title)
        layout.addStretch()

        # Time hint
        if task.early_start:
            time_lbl = QLabel(task.early_start.strftime("%H:%M"))
            time_lbl.setStyleSheet(
                f"color: {Palette.TEXT_TERTIARY}; font-size: 10px; "
                f"font-family: 'JetBrains Mono', monospace;"
            )
            layout.addWidget(time_lbl)

    def mousePressEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.LeftButton:
            self.chipClicked.emit(str(self.task.id))
            self._drag_start = event.position().toPoint()
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        if event.buttons() & Qt.LeftButton and hasattr(self, "_drag_start"):
            delta = event.position().toPoint() - self._drag_start
            if delta.manhattanLength() > 5:
                from PySide6.QtCore import QDrag
                drag = QDrag(self)
                mime = QMimeData()
                mime.setText(self.DRAG_MIME)
                mime.setData(self.DRAG_MIME, str(self.task.id).encode())
                drag.setMimeData(mime)
                pm = QPixmap(self.size())
                self.render(pm)
                drag.setPixmap(pm)
                drag.setHotSpot(self._drag_start)
                drag.exec_(Qt.MoveAction)
        super().mouseMoveEvent(event)

    def mouseDoubleClickEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.LeftButton:
            self.chipDoubleClicked.emit(str(self.task.id))
        super().mouseDoubleClickEvent(event)


# ---- Calendar cells ----

class CalendarCell(QFrame):
    """A single day cell in the month grid."""
    cellClicked = Signal(object)  # ShamsiDate
    cellDoubleClicked = Signal(object)
    taskDropped = Signal(str, object)  # task_id, ShamsiDate

    def __init__(self, date: Optional[ShamsiDate], is_today: bool = False,
                 in_month: bool = True, parent: QWidget = None) -> None:
        super().__init__(parent)
        self.date = date
        self.is_today = is_today
        self.in_month = in_month
        self.setAcceptDrops(True)
        self.setMinimumHeight(100)
        self.setObjectName("cell")
        self._apply_style()

        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(2)

        # Day number
        if date is not None:
            day_lbl = QLabel(str(date.day))
            day_lbl.setStyleSheet(
                f"color: {Palette.GOLD_BRIGHT if is_today else (Palette.TEXT_PRIMARY if in_month else Palette.TEXT_TERTIARY)}; "
                f"font-size: 13px; font-weight: {'bold' if is_today else 'normal'}; "
                f"font-family: 'JetBrains Mono', monospace; padding: 2px 6px;"
            )
            if is_today:
                # Circle highlight
                day_lbl.setStyleSheet(day_lbl.styleSheet() +
                    f"background-color: {Palette.GOLD_PRIMARY}; border-radius: 10px; "
                    f"color: {Palette.TEXT_ON_GOLD}; min-width: 16px; min-height: 16px; "
                    f"max-width: 20px; alignment: center;")
            layout.addWidget(day_lbl, alignment=Qt.AlignRight | Qt.AlignTop)

        # Container for chips
        self._chips_container = QWidget()
        chips_layout = QVBoxLayout(self._chips_container)
        chips_layout.setContentsMargins(0, 0, 0, 0)
        chips_layout.setSpacing(1)
        self._chips_layout = chips_layout
        layout.addWidget(self._chips_container, stretch=1)

        # Overflow indicator
        self._overflow = QLabel("")
        self._overflow.setStyleSheet(
            f"color: {Palette.TEXT_TERTIARY}; font-size: 10px; padding: 0 4px;"
        )
        layout.addWidget(self._overflow)

    def _apply_style(self) -> None:
        bg = Palette.BG_SECONDARY if self.in_month else Palette.BG_DEEPEST
        border = Palette.GOLD_PRIMARY if self.is_today else Palette.BORDER_SUBTLE
        border_w = "2px" if self.is_today else "1px"
        self.setStyleSheet(f"""
            QFrame#cell {{
                background-color: {bg};
                border: {border_w} solid {border};
                border-radius: 2px;
            }}
            QFrame#cell:hover {{
                background-color: {Palette.BG_TERTIARY};
                border: 1px solid {Palette.BORDER_GOLD};
            }}
        """)

    def set_tasks(self, tasks: list[Task], max_visible: int = 4) -> None:
        # Clear old
        while self._chips_layout.count():
            item = self._chips_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        # Sort by start time
        sorted_tasks = sorted(tasks, key=lambda t: (t.early_start or datetime.max))
        for t in sorted_tasks[:max_visible]:
            chip = CalendarTaskChip(t)
            self._chips_layout.addWidget(chip)
        if len(sorted_tasks) > max_visible:
            self._overflow.setText(f"+ {len(sorted_tasks) - max_visible} more")
        else:
            self._overflow.setText("")

    def dragEnterEvent(self, event: QDragEnterEvent) -> None:
        if self.date is not None and event.mimeData().hasFormat(CalendarTaskChip.DRAG_MIME):
            event.acceptProposedAction()
            self.setStyleSheet(f"""
                QFrame#cell {{
                    background-color: {Palette.BG_SELECTED};
                    border: 2px dashed {Palette.GOLD_BRIGHT};
                    border-radius: 2px;
                }}
            """)
        else:
            event.ignore()

    def dragLeaveEvent(self, event) -> None:
        self._apply_style()
        super().dragLeaveEvent(event)

    def dropEvent(self, event: QDropEvent) -> None:
        if self.date is not None and event.mimeData().hasFormat(CalendarTaskChip.DRAG_MIME):
            task_id = bytes(event.mimeData().data(CalendarTaskChip.DRAG_MIME)).decode()
            self.taskDropped.emit(task_id, self.date)
            event.acceptProposedAction()
        self._apply_style()

    def mousePressEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.LeftButton and self.date is not None:
            self.cellClicked.emit(self.date)
        super().mousePressEvent(event)

    def mouseDoubleClickEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.LeftButton and self.date is not None:
            self.cellDoubleClicked.emit(self.date)
        super().mouseDoubleClickEvent(event)


# ---- Main calendar view ----

class BasicCalendarView(QWidget):
    """
    Google-Calendar-style planner. This is the entire Basic plan UI.
    """

    taskDoubleClicked = Signal(str)
    taskEditRequested = Signal(str)

    def __init__(self, project: Project, task_service: TaskService,
                 parent: QWidget = None) -> None:
        super().__init__(parent)
        self.project = project
        self.task_service = task_service

        # Current view mode
        self._view_mode = "month"  # "month" | "week" | "day"
        self._current: ShamsiDate = ShamsiDate.today()
        self._selected_date: Optional[ShamsiDate] = None

        self.setStyleSheet(f"background-color: {Palette.BG_PRIMARY};")

        # Top toolbar
        self._build_toolbar()

        # Content area
        self._content = QWidget()
        content_layout = QVBoxLayout(self._content)
        content_layout.setContentsMargins(0, 0, 0, 0)
        content_layout.setSpacing(0)

        # Weekday header
        self._weekday_header = self._build_weekday_header()
        content_layout.addWidget(self._weekday_header)

        # Grid container
        self._grid_container = QWidget()
        self._grid_layout = QGridLayout(self._grid_container)
        self._grid_layout.setContentsMargins(0, 0, 0, 0)
        self._grid_layout.setSpacing(1)
        content_layout.addWidget(self._grid_container, stretch=1)

        # Add to main layout
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)
        main_layout.addWidget(self._toolbar)
        main_layout.addWidget(self._content, stretch=1)

        self.refresh()

    # ---- UI building ----
    def _build_toolbar(self) -> None:
        self._toolbar = QFrame()
        self._toolbar.setStyleSheet(f"""
            QFrame {{
                background-color: {Palette.BG_SECONDARY};
                border-bottom: 1px solid {Palette.BORDER_SUBTLE};
            }}
        """)
        layout = QHBoxLayout(self._toolbar)
        layout.setContentsMargins(16, 10, 16, 10)
        layout.setSpacing(12)

        # Today button
        today_btn = QPushButton("Today")
        today_btn.setProperty("variant", "primary")
        today_btn.clicked.connect(self._go_today)
        layout.addWidget(today_btn)

        # Prev / Next
        prev_btn = QToolButton()
        prev_btn.setText("‹")
        prev_btn.setStyleSheet(self._nav_button_style())
        prev_btn.setFixedSize(32, 32)
        prev_btn.clicked.connect(lambda: self._navigate(-1))
        layout.addWidget(prev_btn)

        next_btn = QToolButton()
        next_btn.setText("›")
        next_btn.setStyleSheet(self._nav_button_style())
        next_btn.setFixedSize(32, 32)
        next_btn.clicked.connect(lambda: self._navigate(1))
        layout.addWidget(next_btn)

        # Title
        self._title_label = QLabel("")
        self._title_label.setStyleSheet(
            f"color: {Palette.GOLD_BRIGHT}; font-size: 18px; font-weight: bold; "
            f"letter-spacing: 0.5px; padding: 0 12px;"
        )
        layout.addWidget(self._title_label)

        layout.addStretch()

        # Search
        self._search = QLineEdit()
        self._search.setPlaceholderText("🔍  Search tasks...")
        self._search.setFixedWidth(240)
        self._search.setStyleSheet(f"""
            QLineEdit {{
                background-color: {Palette.BG_TERTIARY};
                color: {Palette.TEXT_PRIMARY};
                border: 1px solid {Palette.BORDER_NORMAL};
                border-radius: 4px;
                padding: 6px 12px;
                font-size: 12px;
            }}
            QLineEdit:focus {{
                border: 1px solid {Palette.GOLD_PRIMARY};
            }}
        """)
        self._search.textChanged.connect(lambda _: self.refresh())
        layout.addWidget(self._search)

        # View mode combo
        self._view_combo = QComboBox()
        self._view_combo.addItem("Month", "month")
        self._view_combo.addItem("Week", "week")
        self._view_combo.addItem("Day", "day")
        self._view_combo.currentIndexChanged.connect(
            lambda _: self._set_view_mode(self._view_combo.currentData())
        )
        self._view_combo.setStyleSheet(f"""
            QComboBox {{
                background-color: {Palette.BG_TERTIARY};
                color: {Palette.TEXT_PRIMARY};
                border: 1px solid {Palette.BORDER_NORMAL};
                border-radius: 4px;
                padding: 6px 12px;
                font-size: 12px;
                min-width: 90px;
            }}
        """)
        layout.addWidget(self._view_combo)

        # New task button
        new_btn = QPushButton("+ New Task")
        new_btn.setProperty("variant", "primary")
        new_btn.clicked.connect(self._on_new_task)
        layout.addWidget(new_btn)

    def _nav_button_style(self) -> str:
        return f"""
            QToolButton {{
                background-color: {Palette.BG_TERTIARY};
                color: {Palette.GOLD_BRIGHT};
                border: 1px solid {Palette.BORDER_NORMAL};
                border-radius: 4px;
                font-size: 18px;
                font-weight: bold;
            }}
            QToolButton:hover {{
                background-color: {Palette.BG_ELEVATED};
                border: 1px solid {Palette.GOLD_PRIMARY};
            }}
        """

    def _build_weekday_header(self) -> QWidget:
        header = QWidget()
        header.setStyleSheet(f"background-color: {Palette.BG_SECONDARY};")
        layout = QHBoxLayout(header)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(1)
        for i, wd in enumerate(SHAMSI_WEEKDAYS_SHORT_EN):
            cell = QLabel(wd.upper())
            cell.setAlignment(Qt.AlignCenter)
            cell.setStyleSheet(
                f"color: {Palette.TEXT_TERTIARY}; font-size: 10px; "
                f"font-weight: bold; letter-spacing: 2px; padding: 8px 0; "
                f"background-color: {Palette.BG_SECONDARY};"
            )
            layout.addWidget(cell, stretch=1)
        return header

    # ---- Navigation ----
    def _go_today(self) -> None:
        self._current = ShamsiDate.today()
        self.refresh()

    def _navigate(self, delta: int) -> None:
        if self._view_mode == "month":
            self._current = self._current.add_months(delta)
        elif self._view_mode == "week":
            self._current = self._current.add_days(7 * delta)
        else:
            self._current = self._current.add_days(delta)
        self.refresh()

    def _set_view_mode(self, mode: str) -> None:
        self._view_mode = mode
        self.refresh()

    # ---- Rendering ----
    def refresh(self) -> None:
        # Clear grid
        while self._grid_layout.count():
            item = self._grid_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        if self._view_mode == "month":
            self._render_month()
        elif self._view_mode == "week":
            self._render_week()
        else:
            self._render_day()

        self._update_title()

    def _update_title(self) -> None:
        if self._view_mode == "month":
            self._title_label.setText(
                f"{SHAMSI_MONTHS_FA[self._current.month - 1]}  {self._current.year}"
            )
        elif self._view_mode == "week":
            days = iterate_week(self._current)
            first, last = days[0], days[-1]
            self._title_label.setText(
                f"{first.day} {first.month_name_fa} – {last.day} {last.month_name_fa}  {last.year}"
            )
        else:
            self._title_label.setText(
                f"{self._current.day}  {self._current.month_name_fa}  {self._current.year}"
            )

    def _render_month(self) -> None:
        grid = shamsi_month_grid(self._current.year, self._current.month)
        today = ShamsiDate.today()
        # Also include tail of previous month + head of next for overflow
        # (the grid already has None cells; we'll show prev/next month dates there too)
        prev_month = self._current.add_months(-1)
        next_month = self._current.add_months(1)
        prev_last_day = days_in_month(prev_month.year, prev_month.month)

        for row, week in enumerate(grid):
            for col, sd in enumerate(week):
                if sd is None:
                    # Compute the overflow date
                    # If row 0: prev month days filling the start
                    if row == 0:
                        # Find first non-None day in this week
                        first_real = next((d for d in week if d is not None), None)
                        if first_real is not None:
                            offset = (first_real.day - 1) - col
                            if offset >= 0:
                                sd = ShamsiDate(prev_month.year, prev_month.month,
                                                prev_last_day - offset)
                                in_month = False
                            else:
                                continue
                        else:
                            continue
                    else:
                        # Last row: next month days
                        last_real_idx = max((i for i, d in enumerate(week) if d is not None),
                                             default=-1)
                        if col > last_real_idx and last_real_idx >= 0:
                            last_real = week[last_real_idx]
                            offset = col - last_real_idx
                            sd = ShamsiDate(next_month.year, next_month.month, offset)
                            in_month = False
                        else:
                            continue
                else:
                    in_month = True

                is_today = (sd == today)
                cell = CalendarCell(sd, is_today=is_today, in_month=in_month)
                cell.cellDoubleClicked.connect(self._on_day_double_clicked)
                cell.taskDropped.connect(self._on_task_dropped)
                # Find tasks scheduled on this date
                tasks = self._tasks_on(sd)
                cell.set_tasks(tasks)
                self._grid_layout.addWidget(cell, row, col)
        # Make columns equal-width
        for c in range(7):
            self._grid_layout.setColumnStretch(c, 1)
        for r in range(6):
            self._grid_layout.setRowStretch(r, 1)

    def _render_week(self) -> None:
        days = iterate_week(self._current)
        today = ShamsiDate.today()
        # 1 row x 7 cols, taller cells
        for col, sd in enumerate(days):
            is_today = (sd == today)
            cell = CalendarCell(sd, is_today=is_today, in_month=True)
            cell.setMinimumHeight(400)
            cell.cellDoubleClicked.connect(self._on_day_double_clicked)
            cell.taskDropped.connect(self._on_task_dropped)
            tasks = self._tasks_on(sd)
            cell.set_tasks(tasks, max_visible=20)
            self._grid_layout.addWidget(cell, 0, col)
        for c in range(7):
            self._grid_layout.setColumnStretch(c, 1)
        self._grid_layout.setRowStretch(0, 1)

    def _render_day(self) -> None:
        today = ShamsiDate.today()
        is_today = (self._current == today)
        cell = CalendarCell(self._current, is_today=is_today, in_month=True)
        cell.setMinimumHeight(600)
        cell.cellDoubleClicked.connect(self._on_day_double_clicked)
        cell.taskDropped.connect(self._on_task_dropped)
        tasks = self._tasks_on(self._current)
        cell.set_tasks(tasks, max_visible=50)
        self._grid_layout.addWidget(cell, 0, 0)
        self._grid_layout.setColumnStretch(0, 1)
        self._grid_layout.setRowStretch(0, 1)

    # ---- Task queries ----
    def _tasks_on(self, sd: ShamsiDate) -> list[Task]:
        """Return all tasks whose early_start falls on the given Shamsi date."""
        target_greg = sd.to_gregorian()
        results = []
        q = self._search.text().lower().strip()
        for t in self.project.tasks():
            if t.early_start is None:
                continue
            if t.early_start.date() != target_greg:
                continue
            if q and q not in t.title.lower() and q not in t.description.lower():
                continue
            results.append(t)
        return results

    # ---- Event handlers ----
    def _on_day_double_clicked(self, sd: ShamsiDate) -> None:
        """Create a new task for this day."""
        title, ok = QInputDialog.getText(
            self, "New Task",
            f"Create task for {sd.format('d MMMM yyyy')} ({sd.weekday_fa}):"
        )
        if not ok or not title.strip():
            return
        # Create the task starting at 9am on the chosen date
        start_dt = sd.to_datetime(9, 0)
        tid = self.task_service.create_task(
            title=title.strip(),
            duration_minutes=60,
        )
        if tid is not None:
            task = self.project.get_task(tid)
            if task is not None:
                task.earliest_start = start_dt
                task.x = 0
                task.y = 0
                task.touch()
                self.task_service.scheduling.recalculate()
            self.refresh()

    def _on_task_dropped(self, task_id_str: str, target_date: ShamsiDate) -> None:
        """Move a task to a new day."""
        task = self.project.get_task(TaskId(task_id_str))
        if task is None:
            return
        # Preserve the original time-of-day if possible
        hour = task.early_start.hour if task.early_start else 9
        minute = task.early_start.minute if task.early_start else 0
        task.earliest_start = target_date.to_datetime(hour, minute)
        task.touch()
        self.task_service.scheduling.recalculate()
        self.refresh()

    def _on_new_task(self) -> None:
        """Open the full task editor."""
        from ..dialogs.task_editor_dialog import TaskEditorDialog
        dlg = TaskEditorDialog(None, self.task_service, self)
        if dlg.exec():
            # Set the new task's earliest_start to the selected day if any
            if dlg.task is not None and self._selected_date is not None:
                dlg.task.earliest_start = self._selected_date.to_datetime(9, 0)
                dlg.task.touch()
                self.task_service.scheduling.recalculate()
            self.refresh()
