"""
ScheduleQuestionsWidget — wizard-style scheduling preferences collector.

Shown when the user clicks "Schedule in Calendar". Asks clarifying questions
one at a time (wizard flow) about their scheduling preferences, then emits
a preferences dict for the AI to create the schedule.

Visual style: dark+gold RASK theme, matching MultipleChoiceQuestionWidget
option cards with gold borders, hover glow, and a prominent pulsing final
"Schedule with AI" button.
"""
from __future__ import annotations

import re
from typing import Optional

from PySide6.QtCore import (
    Qt, Signal, QPropertyAnimation, QEasingCurve, QSize, QTimer,
)
from PySide6.QtGui import QFont, QColor, QCursor
from PySide6.QtWidgets import (
    QFrame, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QLineEdit,
    QScrollArea, QSizePolicy, QWidget, QStackedWidget,
)

from ..theme import Palette
from ...core.shamsi import ShamsiDate, parse_shamsi, to_ascii_digits


# ───────────────────── RTL Detection ──────────────────────────────────

_PERSIAN_RE = re.compile(r'[\u0600-\u06FF]')


def _is_rtl(text: str) -> bool:
    """Return True if text contains Persian/Arabic characters."""
    return bool(_PERSIAN_RE.search(text))


# ───────────────────── Option Button ──────────────────────────────────

class _ScheduleOptionButton(QFrame):
    """
    Clickable option card for schedule question choices.

    Mimics _OptionCard / _CompactOptionButton from multiple_choice_question
    but with a slightly different layout supporting an optional description
    line underneath the main label.
    """
    clicked = Signal(str)  # emits the value key

    def __init__(
        self,
        label: str,
        value: str,
        description: str = "",
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._value = value
        self._hovered = False
        self._pressed = False
        self._selected = False

        self.setCursor(Qt.PointingHandCursor)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Minimum)
        self.setObjectName("schedOptBtn")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 10, 12, 10)
        layout.setSpacing(2)

        # Main label
        self._label_widget = QLabel(label)
        self._label_widget.setWordWrap(True)
        self._label_widget.setTextFormat(Qt.PlainText)
        self._label_widget.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Minimum)
        self._label_widget.setStyleSheet(
            f"color: {Palette.TEXT_PRIMARY}; font-size: 13px; "
            f"background: transparent; border: none;"
        )
        layout.addWidget(self._label_widget)

        # Optional description
        if description:
            desc = QLabel(description)
            desc.setWordWrap(True)
            desc.setTextFormat(Qt.PlainText)
            desc.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Minimum)
            desc.setStyleSheet(
                f"color: {Palette.TEXT_TERTIARY}; font-size: 11px; "
                f"font-style: italic; background: transparent; border: none;"
            )
            layout.addWidget(desc)

        self._apply_style()

    # ── Selection state ──
    @property
    def selected(self) -> bool:
        return self._selected

    @selected.setter
    def selected(self, val: bool) -> None:
        self._selected = val
        self._apply_style()

    # ── Styling ──
    def _apply_style(self) -> None:
        if self._selected:
            bg = Palette.BG_SELECTED
            border = Palette.GOLD_BRIGHT
        elif self._pressed:
            bg = Palette.GOLD_MUTED
            border = Palette.GOLD_PRIMARY
        elif self._hovered:
            bg = Palette.BG_HOVER
            border = Palette.GOLD_PRIMARY
        else:
            bg = Palette.BG_ELEVATED
            border = Palette.BORDER_NORMAL

        self.setStyleSheet(f"""
            QFrame#schedOptBtn {{
                background-color: {bg};
                border: 1px solid {border};
                border-left: 3px solid {Palette.GOLD_DEEP};
                border-radius: 6px;
            }}
        """)
        if self._selected:
            self._label_widget.setStyleSheet(
                f"color: {Palette.GOLD_BRIGHT}; font-size: 13px; "
                f"font-weight: 600; background: transparent; border: none;"
            )

    # ── Mouse events ──
    def enterEvent(self, event) -> None:
        self._hovered = True
        self._apply_style()
        super().enterEvent(event)

    def leaveEvent(self, event) -> None:
        self._hovered = False
        self._apply_style()
        super().leaveEvent(event)

    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.LeftButton:
            self._pressed = True
            self._apply_style()

    def mouseReleaseEvent(self, event) -> None:
        if event.button() == Qt.LeftButton and self._pressed:
            self._pressed = False
            self._hovered = False
            self._apply_style()
            self.clicked.emit(self._value)
        else:
            self._pressed = False
            self._apply_style()

    def sizeHint(self) -> QSize:
        return QSize(200, 40)

    def minimumSizeHint(self) -> QSize:
        return QSize(120, 34)


# ───────────────────── Step Page (one question) ───────────────────────

class _StepPage(QFrame):
    """A single wizard step page containing one question and its options."""

    selectionChanged = Signal(str)  # emits the value key when user picks

    def __init__(
        self,
        question_text: str,
        options: list[dict],
        allow_custom: bool = True,
        custom_placeholder: str = "",
        rtl: bool = False,
        parent: QWidget | None = None,
    ) -> None:
        """
        options: list of {"label": str, "value": str, "description": str=""}
        """
        super().__init__(parent)
        self._options = options
        self._selected_value: Optional[str] = None
        self._option_buttons: list[_ScheduleOptionButton] = []

        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Minimum)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(10)

        # Question text
        q_label = QLabel(question_text)
        q_label.setWordWrap(True)
        q_label.setTextFormat(Qt.PlainText)
        q_label.setAlignment(Qt.AlignRight if rtl else Qt.AlignLeft)
        q_label.setStyleSheet(
            f"color: {Palette.TEXT_PRIMARY}; font-size: 15px; "
            f"font-weight: 500; background: transparent; border: none;"
        )
        layout.addWidget(q_label)

        # Options
        for opt in options:
            btn = _ScheduleOptionButton(
                label=opt["label"],
                value=opt["value"],
                description=opt.get("description", ""),
            )
            if rtl:
                btn.setLayoutDirection(Qt.RightToLeft)
            btn.clicked.connect(self._on_option_clicked)
            self._option_buttons.append(btn)
            layout.addWidget(btn)

        # Custom input
        if allow_custom:
            custom_row = QHBoxLayout()
            custom_row.setSpacing(6)

            icon_label = QLabel("✏️")
            icon_label.setStyleSheet(
                f"color: {Palette.TEXT_TERTIARY}; background: transparent; "
                f"border: none; font-size: 13px;"
            )
            icon_label.setFixedWidth(24)
            custom_row.addWidget(icon_label)

            self._custom_input = QLineEdit()
            self._custom_input.setPlaceholderText(
                custom_placeholder or "Type your own answer…"
            )
            self._custom_input.setStyleSheet(f"""
                QLineEdit {{
                    background-color: {Palette.BG_ELEVATED};
                    color: {Palette.TEXT_PRIMARY};
                    border: 1px solid {Palette.BORDER_NORMAL};
                    border-radius: 4px;
                    padding: 8px 12px;
                    font-size: 12px;
                }}
                QLineEdit:focus {{
                    border: 1px solid {Palette.GOLD_PRIMARY};
                    background-color: {Palette.BG_ELEVATED};
                }}
            """)
            self._custom_input.returnPressed.connect(self._on_custom_submitted)
            custom_row.addWidget(self._custom_input, stretch=1)

            submit_btn = QPushButton("→")
            submit_btn.setToolTip("Submit custom answer")
            submit_btn.setFixedSize(32, 32)
            submit_btn.setStyleSheet(f"""
                QPushButton {{
                    background-color: {Palette.GOLD_PRIMARY};
                    color: {Palette.TEXT_ON_GOLD};
                    border: none;
                    border-radius: 4px;
                    font-size: 14px;
                    font-weight: bold;
                }}
                QPushButton:hover {{
                    background-color: {Palette.GOLD_BRIGHT};
                }}
            """)
            submit_btn.clicked.connect(self._on_custom_submitted)
            custom_row.addWidget(submit_btn)

            layout.addLayout(custom_row)
        else:
            self._custom_input = None

    def _on_option_clicked(self, value: str) -> None:
        # Deselect all, select this one
        self._selected_value = value
        for btn in self._option_buttons:
            btn.selected = (btn._value == value)
        self.selectionChanged.emit(value)

    def _on_custom_submitted(self) -> None:
        if self._custom_input is None:
            return
        text = self._custom_input.text().strip()
        if text:
            # Deselect all option buttons
            for btn in self._option_buttons:
                btn.selected = False
            self._selected_value = text
            self.selectionChanged.emit(text)

    @property
    def selected_value(self) -> Optional[str]:
        return self._selected_value

    def reset_selection(self) -> None:
        self._selected_value = None
        for btn in self._option_buttons:
            btn.selected = False
        if self._custom_input is not None:
            self._custom_input.clear()


# ───────────────────── Date Step Page ─────────────────────────────────

class _DateStepPage(QFrame):
    """Specialized step page for Shamsi date input."""

    selectionChanged = Signal(str)  # emits the date string

    def __init__(
        self,
        question_text: str,
        rtl: bool = False,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._selected_value: Optional[str] = None

        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Minimum)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(10)

        # Question text
        q_label = QLabel(question_text)
        q_label.setWordWrap(True)
        q_label.setTextFormat(Qt.PlainText)
        q_label.setAlignment(Qt.AlignRight if rtl else Qt.AlignLeft)
        q_label.setStyleSheet(
            f"color: {Palette.TEXT_PRIMARY}; font-size: 15px; "
            f"font-weight: 500; background: transparent; border: none;"
        )
        layout.addWidget(q_label)

        # Quick options: "Today" / "Tomorrow"
        today = ShamsiDate.today()
        tomorrow = today.add_days(1)

        quick_row = QHBoxLayout()
        quick_row.setSpacing(8)

        self._today_btn = QPushButton(
            f"امروز  {today.format('yyyy/mm/dd')}" if rtl
            else f"Today  {today.format('yyyy/mm/dd')}"
        )
        self._today_btn.setCursor(Qt.PointingHandCursor)
        self._today_btn.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Minimum)
        self._today_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: {Palette.BG_ELEVATED};
                color: {Palette.TEXT_PRIMARY};
                border: 1px solid {Palette.BORDER_NORMAL};
                border-radius: 6px;
                padding: 10px 14px;
                font-size: 12px;
            }}
            QPushButton:hover {{
                background-color: {Palette.BG_SELECTED};
                border: 1px solid {Palette.GOLD_PRIMARY};
                color: {Palette.GOLD_BRIGHT};
            }}
        """)
        self._today_btn.clicked.connect(lambda: self._pick_date(str(today)))
        quick_row.addWidget(self._today_btn)

        self._tomorrow_btn = QPushButton(
            f"فردا  {tomorrow.format('yyyy/mm/dd')}" if rtl
            else f"Tomorrow  {tomorrow.format('yyyy/mm/dd')}"
        )
        self._tomorrow_btn.setCursor(Qt.PointingHandCursor)
        self._tomorrow_btn.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Minimum)
        self._tomorrow_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: {Palette.BG_ELEVATED};
                color: {Palette.TEXT_PRIMARY};
                border: 1px solid {Palette.BORDER_NORMAL};
                border-radius: 6px;
                padding: 10px 14px;
                font-size: 12px;
            }}
            QPushButton:hover {{
                background-color: {Palette.BG_SELECTED};
                border: 1px solid {Palette.GOLD_PRIMARY};
                color: {Palette.GOLD_BRIGHT};
            }}
        """)
        self._tomorrow_btn.clicked.connect(lambda: self._pick_date(str(tomorrow)))
        quick_row.addWidget(self._tomorrow_btn)

        layout.addLayout(quick_row)

        # Custom date input
        custom_label = QLabel("✏️ Enter a date (Shamsi format: yyyy/mm/dd):")
        custom_label.setStyleSheet(
            f"color: {Palette.TEXT_TERTIARY}; font-size: 11px; "
            f"background: transparent; border: none;"
        )
        layout.addWidget(custom_label)

        input_row = QHBoxLayout()
        input_row.setSpacing(6)

        self._date_input = QLineEdit()
        self._date_input.setPlaceholderText("1403/01/15")
        self._date_input.setStyleSheet(f"""
            QLineEdit {{
                background-color: {Palette.BG_ELEVATED};
                color: {Palette.TEXT_PRIMARY};
                border: 1px solid {Palette.BORDER_NORMAL};
                border-radius: 4px;
                padding: 8px 12px;
                font-size: 13px;
            }}
            QLineEdit:focus {{
                border: 1px solid {Palette.GOLD_PRIMARY};
            }}
        """)
        self._date_input.returnPressed.connect(self._on_date_submitted)
        input_row.addWidget(self._date_input, stretch=1)

        submit_btn = QPushButton("→")
        submit_btn.setToolTip("Submit date")
        submit_btn.setFixedSize(32, 32)
        submit_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: {Palette.GOLD_PRIMARY};
                color: {Palette.TEXT_ON_GOLD};
                border: none;
                border-radius: 4px;
                font-size: 14px;
                font-weight: bold;
            }}
            QPushButton:hover {{
                background-color: {Palette.GOLD_BRIGHT};
            }}
        """)
        submit_btn.clicked.connect(self._on_date_submitted)
        input_row.addWidget(submit_btn)

        layout.addLayout(input_row)

        # Validation label
        self._validation_label = QLabel("")
        self._validation_label.setWordWrap(True)
        self._validation_label.setStyleSheet(
            f"color: {Palette.STATUS_BLOCKED}; font-size: 11px; "
            f"background: transparent; border: none;"
        )
        self._validation_label.hide()
        layout.addWidget(self._validation_label)

        # Default: select tomorrow
        self._selected_value = str(tomorrow)
        self._highlight_quick("tomorrow")

    def _pick_date(self, date_str: str) -> None:
        self._selected_value = date_str
        self._validation_label.hide()
        # Highlight the clicked quick button
        if date_str == str(ShamsiDate.today()):
            self._highlight_quick("today")
        else:
            self._highlight_quick("tomorrow")
        self.selectionChanged.emit(date_str)

    def _highlight_quick(self, which: str) -> None:
        gold_style = f"""
            QPushButton {{
                background-color: {Palette.BG_SELECTED};
                color: {Palette.GOLD_BRIGHT};
                border: 1px solid {Palette.GOLD_BRIGHT};
                border-radius: 6px;
                padding: 10px 14px;
                font-size: 12px;
                font-weight: 600;
            }}
            QPushButton:hover {{
                background-color: {Palette.BG_SELECTED};
            }}
        """
        normal_style = f"""
            QPushButton {{
                background-color: {Palette.BG_ELEVATED};
                color: {Palette.TEXT_PRIMARY};
                border: 1px solid {Palette.BORDER_NORMAL};
                border-radius: 6px;
                padding: 10px 14px;
                font-size: 12px;
            }}
            QPushButton:hover {{
                background-color: {Palette.BG_SELECTED};
                border: 1px solid {Palette.GOLD_PRIMARY};
                color: {Palette.GOLD_BRIGHT};
            }}
        """
        self._today_btn.setStyleSheet(gold_style if which == "today" else normal_style)
        self._tomorrow_btn.setStyleSheet(gold_style if which == "tomorrow" else normal_style)

    def _on_date_submitted(self) -> None:
        raw = self._date_input.text().strip()
        if not raw:
            return
        parsed = parse_shamsi(raw)
        if parsed is None:
            self._validation_label.setText(
                "Invalid date format. Use yyyy/mm/dd (e.g. 1403/01/15)"
            )
            self._validation_label.show()
            return
        # Validate it's not in the past
        today = ShamsiDate.today()
        if parsed < today:
            self._validation_label.setText(
                "Start date cannot be in the past."
            )
            self._validation_label.show()
            return

        self._validation_label.hide()
        self._selected_value = str(parsed)
        self._highlight_quick(None)  # deselect both quick buttons
        self.selectionChanged.emit(str(parsed))

    @property
    def selected_value(self) -> Optional[str]:
        return self._selected_value

    def reset_selection(self) -> None:
        tomorrow = ShamsiDate.today().add_days(1)
        self._selected_value = str(tomorrow)
        self._date_input.clear()
        self._validation_label.hide()
        self._highlight_quick("tomorrow")


# ───────────────────── Main Widget ────────────────────────────────────

class ScheduleQuestionsWidget(QFrame):
    """
    Wizard-style scheduling preferences collector.

    Shows 5 questions one at a time (step-by-step wizard), then emits
    a preferences dict via `schedulingRequested` when the user confirms.

    Signals:
        schedulingRequested(dict) — the collected preferences
        cancelled()               — user cancelled the flow
    """

    schedulingRequested = Signal(dict)
    cancelled = Signal()

    # Step definitions (built lazily in _build_steps)
    _STEPS: list[dict] = []

    def __init__(self, route_goal: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._route_goal = route_goal
        self._rtl = _is_rtl(route_goal)
        self._current_step = 0
        self._step_pages: list[QWidget] = []
        self._answers: list[Optional[str]] = []

        self.setObjectName("scheduleQuestions")
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.setStyleSheet(f"""
            QFrame#scheduleQuestions {{
                background-color: {Palette.BG_TERTIARY};
                border: 1px solid {Palette.BORDER_NORMAL};
                border-radius: 8px;
            }}
        """)

        self._build_ui()
        self._build_steps()
        self._update_step()

    # ──────────────── UI Construction ─────────────────────────────────

    def _build_ui(self) -> None:
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        # Scroll area for content
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        scroll.setStyleSheet(f"""
            QScrollArea {{
                background-color: {Palette.BG_TERTIARY};
                border: none;
            }}
            QScrollBar:vertical {{
                background: transparent;
                width: 8px;
            }}
            QScrollBar::handle:vertical {{
                background: {Palette.BG_ELEVATED};
                border-radius: 4px;
                min-height: 24px;
                margin: 1px;
            }}
            QScrollBar::handle:vertical:hover {{
                background: {Palette.BORDER_GOLD};
            }}
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
                height: 0;
            }}
        """)

        self._content = QWidget()
        self._content.setStyleSheet(f"background-color: {Palette.BG_TERTIARY};")

        self._main_layout = QVBoxLayout(self._content)
        self._main_layout.setContentsMargins(24, 20, 24, 20)
        self._main_layout.setSpacing(12)

        # ── Header ──
        self._build_header()

        # ── Step indicator ──
        self._step_indicator = QLabel("")
        self._step_indicator.setAlignment(Qt.AlignCenter)
        self._step_indicator.setStyleSheet(
            f"color: {Palette.GOLD_PRIMARY}; font-size: 11px; "
            f"font-weight: 600; letter-spacing: 1px; "
            f"background: transparent; border: none;"
        )
        self._main_layout.addWidget(self._step_indicator)

        # ── Progress bar ──
        self._progress_frame = QFrame()
        self._progress_frame.setFixedHeight(3)
        self._progress_frame.setStyleSheet(
            f"background-color: {Palette.BG_ELEVATED}; border: none; border-radius: 1px;"
        )
        self._main_layout.addWidget(self._progress_frame)

        # Gold fill for progress
        self._progress_fill = QFrame(self._progress_frame)
        self._progress_fill.setGeometry(0, 0, 0, 3)
        self._progress_fill.setStyleSheet(
            f"background-color: {Palette.GOLD_PRIMARY}; border: none; border-radius: 1px;"
        )

        # ── Stacked pages ──
        self._stack = QStackedWidget()
        self._stack.setStyleSheet("background: transparent;")
        self._main_layout.addWidget(self._stack, stretch=1)

        # ── Navigation ──
        self._build_navigation()

        scroll.setWidget(self._content)
        outer.addWidget(scroll)

    def _build_header(self) -> None:
        # Goal name with gold gradient style
        goal_label = QLabel(self._route_goal)
        goal_label.setWordWrap(True)
        goal_label.setAlignment(Qt.AlignCenter)
        goal_label.setStyleSheet(f"""
            color: {Palette.GOLD_BRIGHT};
            font-size: 16px;
            font-weight: 700;
            letter-spacing: 0.3px;
            background: transparent;
            border: none;
            padding: 4px 0;
        """)
        self._main_layout.addWidget(goal_label)

        # Subtitle
        subtitle_text = "تنظیمات زمان‌بندی" if self._rtl else "Scheduling Preferences"
        subtitle = QLabel(f"📅  {subtitle_text}")
        subtitle.setAlignment(Qt.AlignCenter)
        subtitle.setStyleSheet(
            f"color: {Palette.TEXT_SECONDARY}; font-size: 12px; "
            f"background: transparent; border: none;"
        )
        self._main_layout.addWidget(subtitle)

        # Divider
        divider = QFrame()
        divider.setFrameShape(QFrame.HLine)
        divider.setFixedHeight(1)
        divider.setStyleSheet(f"color: {Palette.BORDER_SUBTLE};")
        self._main_layout.addWidget(divider)

    def _build_navigation(self) -> None:
        nav_layout = QHBoxLayout()
        nav_layout.setSpacing(8)
        nav_layout.setContentsMargins(0, 8, 0, 0)

        # Cancel button
        self._cancel_btn = QPushButton(
            "انصراف" if self._rtl else "Cancel"
        )
        self._cancel_btn.setCursor(Qt.PointingHandCursor)
        self._cancel_btn.setSizePolicy(QSizePolicy.Minimum, QSizePolicy.Fixed)
        self._cancel_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: transparent;
                color: {Palette.TEXT_TERTIARY};
                border: 1px solid {Palette.BORDER_NORMAL};
                border-radius: 4px;
                padding: 8px 16px;
                font-size: 12px;
            }}
            QPushButton:hover {{
                color: {Palette.STATUS_BLOCKED};
                border: 1px solid {Palette.STATUS_BLOCKED};
            }}
        """)
        self._cancel_btn.clicked.connect(self.cancelled.emit)
        nav_layout.addWidget(self._cancel_btn)

        nav_layout.addStretch()

        # Back button
        self._back_btn = QPushButton(
            "→ قبلی" if self._rtl else "← Back"
        )
        self._back_btn.setCursor(Qt.PointingHandCursor)
        self._back_btn.setSizePolicy(QSizePolicy.Minimum, QSizePolicy.Fixed)
        self._back_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: {Palette.BG_ELEVATED};
                color: {Palette.TEXT_SECONDARY};
                border: 1px solid {Palette.BORDER_NORMAL};
                border-radius: 4px;
                padding: 8px 16px;
                font-size: 12px;
            }}
            QPushButton:hover {{
                background-color: {Palette.BG_HOVER};
                color: {Palette.TEXT_PRIMARY};
                border: 1px solid {Palette.BORDER_NORMAL};
            }}
            QPushButton:disabled {{
                color: {Palette.TEXT_TERTIARY};
                background-color: {Palette.BG_SECONDARY};
                border: 1px solid {Palette.BORDER_SUBTLE};
            }}
        """)
        self._back_btn.clicked.connect(self._go_back)
        nav_layout.addWidget(self._back_btn)

        # Next / Submit button
        self._next_btn = QPushButton(
            "بعدی ←" if self._rtl else "Next →"
        )
        self._next_btn.setCursor(Qt.PointingHandCursor)
        self._next_btn.setSizePolicy(QSizePolicy.Minimum, QSizePolicy.Fixed)
        self._next_btn.setMinimumHeight(36)
        self._next_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: {Palette.GOLD_PRIMARY};
                color: {Palette.TEXT_ON_GOLD};
                border: 1px solid {Palette.GOLD_DEEP};
                border-radius: 4px;
                padding: 8px 20px;
                font-size: 13px;
                font-weight: 600;
            }}
            QPushButton:hover {{
                background-color: {Palette.GOLD_BRIGHT};
                border: 1px solid {Palette.GOLD_PRIMARY};
            }}
            QPushButton:pressed {{
                background-color: {Palette.GOLD_DEEP};
            }}
            QPushButton:disabled {{
                color: {Palette.TEXT_TERTIARY};
                background-color: {Palette.BG_SECONDARY};
                border: 1px solid {Palette.BORDER_SUBTLE};
            }}
        """)
        self._next_btn.clicked.connect(self._go_next)
        nav_layout.addWidget(self._next_btn)

        self._main_layout.addLayout(nav_layout)

        # ── Final "Schedule with AI" button (hidden until last step) ──
        self._final_btn = QPushButton("✦  Schedule with AI")
        self._final_btn.setCursor(Qt.PointingHandCursor)
        self._final_btn.setFixedHeight(52)
        self._final_btn.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self._final_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: {Palette.GOLD_PRIMARY};
                color: {Palette.TEXT_ON_GOLD};
                border: none;
                border-radius: 8px;
                font-size: 15px;
                font-weight: 700;
                letter-spacing: 0.5px;
            }}
            QPushButton:hover {{
                background-color: {Palette.GOLD_BRIGHT};
            }}
            QPushButton:pressed {{
                background-color: {Palette.GOLD_DEEP};
            }}
        """)
        self._final_btn.clicked.connect(self._on_final_submit)
        self._final_btn.hide()
        self._main_layout.addWidget(self._final_btn)

        # Pulse animation for final button
        self._pulse_anim = QPropertyAnimation(self._final_btn, b"windowOpacity")
        self._pulse_anim.setDuration(1800)
        self._pulse_anim.setStartValue(1.0)
        self._pulse_anim.setKeyValueAt(0.5, 0.75)
        self._pulse_anim.setEndValue(1.0)
        self._pulse_anim.setEasingCurve(QEasingCurve.InOutSine)
        self._pulse_anim.setLoopCount(-1)

        # Alternate pulse: animate a custom property for background glow
        self._glow_phase = 0
        self._glow_timer = QTimer(self)
        self._glow_timer.setInterval(900)
        self._glow_timer.timeout.connect(self._toggle_glow)

    def _toggle_glow(self) -> None:
        """Toggle the final button between bright and normal gold."""
        self._glow_phase = 1 - self._glow_phase
        if self._glow_phase:
            self._final_btn.setStyleSheet(f"""
                QPushButton {{
                    background-color: {Palette.GOLD_BRIGHT};
                    color: {Palette.TEXT_ON_GOLD};
                    border: none;
                    border-radius: 8px;
                    font-size: 15px;
                    font-weight: 700;
                    letter-spacing: 0.5px;
                }}
                QPushButton:hover {{
                    background-color: {Palette.GOLD_BRIGHT};
                }}
                QPushButton:pressed {{
                    background-color: {Palette.GOLD_DEEP};
                }}
            """)
        else:
            self._final_btn.setStyleSheet(f"""
                QPushButton {{
                    background-color: {Palette.GOLD_PRIMARY};
                    color: {Palette.TEXT_ON_GOLD};
                    border: none;
                    border-radius: 8px;
                    font-size: 15px;
                    font-weight: 700;
                    letter-spacing: 0.5px;
                }}
                QPushButton:hover {{
                    background-color: {Palette.GOLD_BRIGHT};
                }}
                QPushButton:pressed {{
                    background-color: {Palette.GOLD_DEEP};
                }}
            """)

    # ──────────────── Step Definitions ────────────────────────────────

    def _build_steps(self) -> None:
        """Create the 5 wizard step pages."""
        rtl = self._rtl

        # Question 1: Daily hours
        q1_text = "روزانه چند ساعت می‌توانید وقت بگذارید؟" if rtl else \
                  "How many hours per day can you dedicate to this goal?"
        step1 = _StepPage(
            question_text=q1_text,
            options=[
                {"label": "۱-۲ ساعت" if rtl else "1-2 hours", "value": "1-2"},
                {"label": "۲-۳ ساعت" if rtl else "2-3 hours", "value": "2-3"},
                {"label": "۳-۴ ساعت" if rtl else "3-4 hours", "value": "3-4"},
                {"label": "۴-۶ ساعت" if rtl else "4-6 hours", "value": "4-6"},
                {"label": "۶-۸ ساعت" if rtl else "6-8 hours", "value": "6-8"},
            ],
            allow_custom=True,
            custom_placeholder="e.g. 5 hours" if not rtl else "مثلاً ۵ ساعت",
            rtl=rtl,
        )
        step1.selectionChanged.connect(lambda v: self._set_answer(0, v))
        self._step_pages.append(step1)
        self._stack.addWidget(step1)

        # Question 2: Preferred time of day
        q2_text = "چه زمانی از روز ترجیح می‌دهید؟" if rtl else \
                  "When do you prefer to work on this?"
        step2 = _StepPage(
            question_text=q2_text,
            options=[
                {
                    "label": "صبح (۷-۱۲)" if rtl else "Morning (7-12)",
                    "value": "morning",
                },
                {
                    "label": "بعدازظهر (۱۳-۱۷)" if rtl else "Afternoon (13-17)",
                    "value": "afternoon",
                },
                {
                    "label": "عصر (۱۸-۲۲)" if rtl else "Evening (18-22)",
                    "value": "evening",
                },
                {
                    "label": "انعطاف‌پذیر (هر زمان)" if rtl else "Flexible (any time)",
                    "value": "flexible",
                },
            ],
            allow_custom=True,
            custom_placeholder="e.g. late nights" if not rtl else "مثلاً آخر شب",
            rtl=rtl,
        )
        step2.selectionChanged.connect(lambda v: self._set_answer(1, v))
        self._step_pages.append(step2)
        self._stack.addWidget(step2)

        # Question 3: Intensity level
        q3_text = "سطح شدت کار چقدر باشد؟" if rtl else \
                  "What intensity level works for you?"
        step3 = _StepPage(
            question_text=q3_text,
            options=[
                {
                    "label": "Relaxed 🌿",
                    "value": "relaxed",
                    "description": "Steady pace, no rush" if not rtl else "سرعت ثابت، بدون عجله",
                },
                {
                    "label": "Balanced ⚖️",
                    "value": "balanced",
                    "description": "Moderate pace" if not rtl else "سرعت متعادل",
                },
                {
                    "label": "Intensive 🔥",
                    "value": "intensive",
                    "description": "Maximum effort" if not rtl else "حداکثر تلاش",
                },
            ],
            allow_custom=False,
            rtl=rtl,
        )
        step3.selectionChanged.connect(lambda v: self._set_answer(2, v))
        self._step_pages.append(step3)
        self._stack.addWidget(step3)

        # Question 4: Days to avoid
        q4_text = "کدام روزها را نمی‌خواهید؟" if rtl else \
                  "Which days do you want to avoid?"
        step4 = _StepPage(
            question_text=q4_text,
            options=[
                {"label": "None", "value": "none"},
                {"label": "Fridays (جمعه)", "value": "friday"},
                {"label": "Weekends (Fridays + Saturdays)", "value": "weekends"},
                {"label": "Custom…", "value": "custom"},
            ],
            allow_custom=True,
            custom_placeholder="e.g. Wednesdays" if not rtl else "مثلاً چهارشنبه‌ها",
            rtl=rtl,
        )
        step4.selectionChanged.connect(lambda v: self._set_answer(3, v))
        self._step_pages.append(step4)
        self._stack.addWidget(step4)

        # Question 5: Start date
        q5_text = "چه زمانی می‌خواهید شروع کنید؟" if rtl else \
                  "When do you want to start?"
        step5 = _DateStepPage(
            question_text=q5_text,
            rtl=rtl,
        )
        step5.selectionChanged.connect(lambda v: self._set_answer(4, v))
        self._step_pages.append(step5)
        self._stack.addWidget(step5)

        # Initialize answers
        self._answers = [None] * 5

        # Set default for step 5 (tomorrow is default in _DateStepPage)
        self._answers[4] = step5.selected_value

    # ──────────────── Navigation ──────────────────────────────────────

    def _set_answer(self, step: int, value: str) -> None:
        self._answers[step] = value
        # Update Next button enabled state — it depends on whether the
        # current step has an answer.  Without this the button stayed
        # disabled even after the user picked an option.
        if step == self._current_step:
            self._next_btn.setEnabled(value is not None)

    def _go_next(self) -> None:
        if self._current_step < len(self._step_pages) - 1:
            self._current_step += 1
            self._update_step()

    def _go_back(self) -> None:
        if self._current_step > 0:
            self._current_step -= 1
            self._update_step()

    def _update_step(self) -> None:
        total = len(self._step_pages)

        # Switch stacked widget
        self._stack.setCurrentIndex(self._current_step)

        # Step indicator text
        self._step_indicator.setText(
            f"Step {self._current_step + 1} of {total}"
        )

        # Progress bar fill
        progress_pct = (self._current_step + 1) / total
        fill_width = int(self._progress_frame.width() * progress_pct)
        self._progress_fill.setGeometry(0, 0, fill_width, 3)

        # Back button state
        self._back_btn.setEnabled(self._current_step > 0)

        # Next/Final button visibility
        is_last = self._current_step == total - 1
        if is_last:
            self._next_btn.hide()
            self._final_btn.show()
            self._glow_timer.start()
        else:
            self._next_btn.show()
            self._final_btn.hide()
            self._glow_timer.stop()
            self._glow_phase = 0

        # Next button enabled state — require selection on current step
        current_value = self._answers[self._current_step]
        self._next_btn.setEnabled(current_value is not None)

    def _on_final_submit(self) -> None:
        """Collect all answers and emit the schedulingRequested signal."""
        prefs = self._build_preferences()
        self._glow_timer.stop()
        self.schedulingRequested.emit(prefs)

    def _build_preferences(self) -> dict:
        """Build the preferences dict from collected answers."""
        # Daily hours
        daily_hours = self._answers[0] or "2-3"

        # Preferred time
        preferred_time = self._answers[1] or "flexible"

        # Intensity
        intensity = self._answers[2] or "balanced"

        # Avoid days — convert to list
        avoid_raw = self._answers[3] or "none"
        if avoid_raw == "none":
            avoid_days: list[str] = []
        elif avoid_raw == "friday":
            avoid_days = ["friday"]
        elif avoid_raw == "weekends":
            avoid_days = ["friday", "saturday"]
        elif avoid_raw == "custom":
            # Use custom input if available
            custom_text = ""
            step4 = self._step_pages[3]
            if hasattr(step4, '_custom_input') and step4._custom_input is not None:
                custom_text = step4._custom_input.text().strip()
            if custom_text:
                # Split by comma and strip
                avoid_days = [d.strip().lower() for d in custom_text.split(",") if d.strip()]
            else:
                avoid_days = []
        else:
            # Custom value entered directly
            avoid_days = [d.strip().lower() for d in avoid_raw.split(",") if d.strip()]

        # Start date
        start_date = self._answers[4] or str(ShamsiDate.today().add_days(1))

        return {
            "daily_hours": daily_hours,
            "preferred_time": preferred_time,
            "intensity": intensity,
            "avoid_days": avoid_days,
            "start_date": start_date,
        }

    # ──────────────── Public API ──────────────────────────────────────

    def reset(self) -> None:
        """Reset the wizard to the first step."""
        self._current_step = 0
        self._answers = [None] * 5
        # Reset date step default
        if len(self._step_pages) >= 5:
            self._answers[4] = self._step_pages[4].selected_value
        for page in self._step_pages:
            if hasattr(page, 'reset_selection'):
                page.reset_selection()
        self._update_step()

    # ──────────────── Resize ──────────────────────────────────────────

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        # Update progress fill width
        total = len(self._step_pages)
        if total > 0:
            progress_pct = (self._current_step + 1) / total
            fill_width = int(self._progress_frame.width() * progress_pct)
            self._progress_fill.setGeometry(0, 0, fill_width, 3)
