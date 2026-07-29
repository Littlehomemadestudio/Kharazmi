"""
AIScheduleDialog — AI-powered interactive scheduling dialog.

When the user clicks "AI Schedule" in the calendar toolbar, this dialog
opens. The AI asks questions, the user answers, and when the AI has enough
information, it creates events directly in the calendar.

Flow:
  1. Dialog opens with an initial prompt input
  2. User describes what they want scheduled
  3. AI may ask clarifying questions
  4. User answers (multi-turn conversation)
  5. When AI is ready, it creates events in the calendar
  6. Dialog shows a summary of created events
"""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta
from typing import Optional, Any

from PySide6.QtCore import Qt, Signal, QTimer, QSize
from PySide6.QtGui import (
    QFont, QColor, QTextCursor, QTextOption, QKeyEvent,
)
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QFrame, QScrollArea, QPlainTextEdit, QTextEdit, QSizePolicy,
    QToolButton, QApplication,
)

from ...ai import AIService
from ...calendar.store import CalendarStore
from ...calendar.event import Event
from ...calendar.enums import EventType, EventStatus
from ...core.shamsi import ShamsiDate, format_shamsi
from ..theme import Palette


# ---- RTL detection ----

def _is_rtl(text: str) -> bool:
    rtl_count = sum(
        1 for ch in text
        if '\u0600' <= ch <= '\u06FF'
        or '\uFB50' <= ch <= '\uFDFF'
        or '\uFE70' <= ch <= '\uFEFF'
    )
    return rtl_count > len(text) * 0.3


# ---- Message bubble ----

class _ScheduleBubble(QFrame):
    """A chat message bubble for the scheduling conversation."""

    def __init__(self, role: str = "assistant", parent=None) -> None:
        super().__init__(parent)
        self.role = role

        if role == "assistant":
            bg = Palette.BG_TERTIARY
            border_left = Palette.GOLD_PRIMARY
            icon = "✦"
            name = "Rask AI"
            icon_color = Palette.GOLD_BRIGHT
        elif role == "system":
            bg = "#1A2A1A"
            border_left = "#5A8A5A"
            icon = "✓"
            name = "Schedule"
            icon_color = "#5A8A5A"
        else:
            bg = Palette.BG_SELECTED
            border_left = Palette.GOLD_BRIGHT
            icon = "○"
            name = "You"
            icon_color = Palette.TEXT_SECONDARY

        self.setStyleSheet(f"""
            QFrame {{
                background-color: {bg};
                border: 1px solid {Palette.BORDER_SUBTLE};
                border-left: 3px solid {border_left};
                border-radius: 5px;
                margin: 1px 0;
            }}
        """)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 5, 8, 5)
        layout.setSpacing(2)

        # Header row
        header = QHBoxLayout()
        header.setSpacing(4)
        icon_lbl = QLabel(icon)
        icon_lbl.setStyleSheet(
            f"color: {icon_color}; font-size: 11px; font-weight: bold; "
            f"background: transparent; border: none;"
        )
        header.addWidget(icon_lbl)
        name_lbl = QLabel(name)
        name_lbl.setStyleSheet(
            f"color: {icon_color}; font-size: 10px; font-weight: bold; "
            f"letter-spacing: 0.5px; background: transparent; border: none;"
        )
        header.addWidget(name_lbl)
        header.addStretch()
        ts = QLabel(datetime.now().strftime("%H:%M"))
        ts.setStyleSheet(
            f"color: {Palette.TEXT_TERTIARY}; font-size: 8px; "
            f"font-family: 'JetBrains Mono', monospace; "
            f"background: transparent; border: none;"
        )
        header.addWidget(ts)
        layout.addLayout(header)

        # Body
        self._body = QTextEdit()
        self._body.setReadOnly(True)
        self._body.setStyleSheet(f"""
            QTextEdit {{
                background: transparent;
                color: {Palette.TEXT_PRIMARY};
                border: none;
                font-size: 12px;
            }}
        """)
        self._body.setWordWrapMode(QTextOption.WordWrap)
        self._body.setMinimumHeight(16)
        self._body.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Minimum)
        self._body.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self._body.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        layout.addWidget(self._body)

        self._body.document().contentsChanged.connect(self._adjust_height)

    def _adjust_height(self) -> None:
        doc_height = self._body.document().size().height()
        self._body.setFixedHeight(int(doc_height) + 6)

    def append_text(self, text: str) -> None:
        cursor = self._body.textCursor()
        cursor.movePosition(QTextCursor.End)
        cursor.insertText(text)
        self._body.setTextCursor(cursor)

    def set_text(self, text: str) -> None:
        self._body.setPlainText(text)
        if _is_rtl(text):
            self._body.setLayoutDirection(Qt.RightToLeft)
        else:
            self._body.setLayoutDirection(Qt.LeftToRight)

    def get_text(self) -> str:
        return self._body.toPlainText()


# ---- Chat input ----

class _ScheduleInput(QPlainTextEdit):
    """Multi-line input. Enter sends, Shift+Enter for newline."""

    sendMessage = Signal(str)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setPlaceholderText(
            "Describe what you want scheduled...  (Enter to send)"
        )
        self.setStyleSheet(f"""
            QPlainTextEdit {{
                background-color: {Palette.BG_TERTIARY};
                color: {Palette.TEXT_PRIMARY};
                border: 1px solid {Palette.BORDER_NORMAL};
                border-radius: 4px;
                padding: 6px 10px;
                font-size: 12px;
            }}
            QPlainTextEdit:focus {{
                border: 1px solid {Palette.GOLD_PRIMARY};
            }}
        """)
        self.setMaximumHeight(80)
        self.setMinimumHeight(32)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)

    def keyPressEvent(self, event: QKeyEvent) -> None:
        if event.key() == Qt.Key_Return and not (event.modifiers() & Qt.ShiftModifier):
            text = self.toPlainText().strip()
            if text:
                self.sendMessage.emit(text)
                self.clear()
            return
        super().keyPressEvent(event)


# ---- Main Dialog ----

class AIScheduleDialog(QDialog):
    """
    AI-powered scheduling dialog.

    Opens a conversation with the AI. The AI asks questions about
    what the user wants to schedule, then creates events in the
    calendar when ready.
    """

    # Quick scheduling prompts
    QUICK_PROMPTS = [
        "Study plan for my exams",
        "Schedule my work week",
        "Plan a daily routine",
        "Block focus time this week",
    ]

    def __init__(
        self,
        calendar_store: CalendarStore,
        ai_service: AIService,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self._store = calendar_store
        self._ai = ai_service
        self._streaming_msg: Optional[_ScheduleBubble] = None
        self._request_id: Optional[str] = None
        self._conversation_history: list[dict] = []
        self._created_events: list[Event] = []
        self._scheduling_done = False

        # Calendar context (built on show)
        self._context: dict = {}

        self._setup_ui()

    def _setup_ui(self) -> None:
        self.setWindowTitle("✦ AI Schedule")
        self.setMinimumSize(520, 600)
        self.resize(560, 680)
        self.setStyleSheet(f"background-color: {Palette.BG_PRIMARY};")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # ── Header ──
        header = QFrame()
        header.setStyleSheet(
            f"background-color: {Palette.BG_TERTIARY}; "
            f"border-bottom: 1px solid {Palette.BORDER_SUBTLE};"
        )
        header.setFixedHeight(50)
        header_layout = QHBoxLayout(header)
        header_layout.setContentsMargins(16, 8, 16, 8)
        header_layout.setSpacing(8)

        icon_lbl = QLabel("✦")
        icon_lbl.setStyleSheet(
            f"color: {Palette.GOLD_BRIGHT}; font-size: 18px; font-weight: bold; "
            f"background: transparent; border: none;"
        )
        header_layout.addWidget(icon_lbl)

        title_lbl = QLabel("AI Schedule")
        title_lbl.setStyleSheet(
            f"color: {Palette.GOLD_PRIMARY}; font-size: 14px; "
            f"font-weight: bold; letter-spacing: 1px; "
            f"background: transparent; border: none;"
        )
        header_layout.addWidget(title_lbl)

        subtitle = QLabel("Let AI plan your calendar")
        subtitle.setStyleSheet(
            f"color: {Palette.TEXT_TERTIARY}; font-size: 10px; "
            f"background: transparent; border: none;"
        )
        header_layout.addWidget(subtitle)
        header_layout.addStretch()

        # Close button
        close_btn = QToolButton()
        close_btn.setText("✕")
        close_btn.setStyleSheet(f"""
            QToolButton {{
                background: transparent;
                color: {Palette.TEXT_TERTIARY};
                border: none;
                font-size: 14px;
                padding: 4px;
            }}
            QToolButton:hover {{
                color: {Palette.GOLD_BRIGHT};
            }}
        """)
        close_btn.clicked.connect(self.reject)
        header_layout.addWidget(close_btn)

        layout.addWidget(header)

        # ── Quick prompt chips ──
        chips_frame = QFrame()
        chips_frame.setStyleSheet(
            f"background-color: {Palette.BG_SECONDARY}; "
            f"border-bottom: 1px solid {Palette.BORDER_SUBTLE};"
        )
        chips_layout = QHBoxLayout(chips_frame)
        chips_layout.setContentsMargins(12, 6, 12, 6)
        chips_layout.setSpacing(6)

        chips_label = QLabel("Try:")
        chips_label.setStyleSheet(
            f"color: {Palette.TEXT_TERTIARY}; font-size: 10px; "
            f"font-weight: bold; background: transparent; border: none;"
        )
        chips_layout.addWidget(chips_label)

        for prompt_text in self.QUICK_PROMPTS:
            chip = QPushButton(prompt_text)
            chip.setStyleSheet(f"""
                QPushButton {{
                    background-color: {Palette.BG_ELEVATED};
                    color: {Palette.GOLD_PRIMARY};
                    border: 1px solid {Palette.BORDER_GOLD};
                    border-radius: 12px;
                    padding: 4px 12px;
                    font-size: 10px;
                }}
                QPushButton:hover {{
                    background-color: {Palette.BG_HOVER};
                    color: {Palette.GOLD_BRIGHT};
                    border: 1px solid {Palette.GOLD_PRIMARY};
                }}
            """)
            chip.setCursor(Qt.PointingHandCursor)
            chip.clicked.connect(
                lambda checked, t=prompt_text: self._on_quick_prompt(t)
            )
            chips_layout.addWidget(chip)

        chips_layout.addStretch()
        layout.addWidget(chips_frame)

        # ── Conversation area ──
        self._scroll = QScrollArea()
        self._scroll.setWidgetResizable(True)
        self._scroll.setFrameShape(QFrame.NoFrame)
        self._scroll.setStyleSheet(
            f"QScrollArea {{ background-color: {Palette.BG_SECONDARY}; border: none; }}"
        )
        self._container = QWidget()
        self._conv_layout = QVBoxLayout(self._container)
        self._conv_layout.setContentsMargins(12, 12, 12, 12)
        self._conv_layout.setSpacing(6)
        self._conv_layout.addStretch()
        self._scroll.setWidget(self._container)
        layout.addWidget(self._scroll, 1)

        # ── Created events summary ──
        self._summary_frame = QFrame()
        self._summary_frame.setStyleSheet(
            f"background-color: {Palette.BG_TERTIARY}; "
            f"border-top: 1px solid {Palette.BORDER_SUBTLE};"
        )
        self._summary_frame.hide()
        summary_layout = QVBoxLayout(self._summary_frame)
        summary_layout.setContentsMargins(12, 8, 12, 8)
        summary_layout.setSpacing(4)

        self._summary_label = QLabel("")
        self._summary_label.setStyleSheet(
            f"color: {Palette.GOLD_BRIGHT}; font-size: 11px; "
            f"font-weight: bold; background: transparent; border: none;"
        )
        summary_layout.addWidget(self._summary_label)

        self._events_list_label = QLabel("")
        self._events_list_label.setWordWrap(True)
        self._events_list_label.setStyleSheet(
            f"color: {Palette.TEXT_SECONDARY}; font-size: 10px; "
            f"background: transparent; border: none;"
        )
        summary_layout.addWidget(self._events_list_label)

        layout.addWidget(self._summary_frame)

        # ── Input area ──
        input_frame = QFrame()
        input_frame.setStyleSheet(
            f"background-color: {Palette.BG_TERTIARY}; "
            f"border-top: 1px solid {Palette.BORDER_SUBTLE};"
        )
        input_layout = QVBoxLayout(input_frame)
        input_layout.setContentsMargins(8, 8, 8, 8)
        input_layout.setSpacing(4)

        self._input = _ScheduleInput()
        self._input.sendMessage.connect(self._on_send)
        input_layout.addWidget(self._input)

        # Action row
        action_row = QHBoxLayout()
        action_row.addStretch()

        self._stop_btn = QPushButton("■ Stop")
        self._stop_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: {Palette.STATUS_BLOCKED};
                color: {Palette.TEXT_PRIMARY};
                border: none;
                border-radius: 3px;
                padding: 4px 12px;
                font-size: 10px;
                font-weight: bold;
            }}
            QPushButton:hover {{
                background-color: #C24A4A;
            }}
        """)
        self._stop_btn.clicked.connect(self._on_stop)
        self._stop_btn.hide()
        action_row.addWidget(self._stop_btn)

        self._send_btn = QPushButton("➤ Schedule")
        self._send_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: {Palette.GOLD_PRIMARY};
                color: {Palette.TEXT_ON_GOLD};
                border: 1px solid {Palette.GOLD_DEEP};
                border-radius: 6px;
                padding: 6px 18px;
                font-size: 11px;
                font-weight: bold;
            }}
            QPushButton:hover {{
                background-color: {Palette.GOLD_BRIGHT};
            }}
            QPushButton:pressed {{
                background-color: {Palette.GOLD_DEEP};
            }}
        """)
        self._send_btn.setCursor(Qt.PointingHandCursor)
        self._send_btn.clicked.connect(
            lambda: self._on_send(self._input.toPlainText())
        )
        action_row.addWidget(self._send_btn)

        input_layout.addLayout(action_row)
        layout.addWidget(input_frame)

    # ---- Context ----

    def _build_context(self) -> dict:
        """Build calendar context for the AI."""
        now = datetime.now()
        today_shamsi = ShamsiDate.from_gregorian(now.date())
        current_date = today_shamsi.format("yyyy/mm/dd EEEE")

        # Today's events
        try:
            today_evts = self._store.events_on_day(now.date())
        except Exception:
            today_evts = []

        # Upcoming events (7 days)
        try:
            upcoming_evts = self._store.upcoming_events(days=7)
        except Exception:
            upcoming_evts = []

        # Available calendars
        calendars = []
        for cal in self._store.calendars():
            calendars.append({
                "id": cal.id,
                "name": cal.name,
                "color": cal.color,
            })

        def _serialize(events):
            result = []
            for ev in events:
                if isinstance(ev, dict):
                    result.append(ev)
                else:
                    try:
                        result.append({
                            "title": getattr(ev, "title", "?"),
                            "start": format_shamsi(getattr(ev, "start", None)),
                            "end": format_shamsi(getattr(ev, "end", None)),
                            "start_iso": getattr(ev, "start", None).isoformat()
                            if getattr(ev, "start", None) else "?",
                            "end_iso": getattr(ev, "end", None).isoformat()
                            if getattr(ev, "end", None) else "?",
                            "all_day": getattr(ev, "all_day", False),
                            "completed": getattr(ev, "completed", False),
                        })
                    except Exception:
                        continue
            return result

        return {
            "current_date": current_date,
            "today_events": _serialize(today_evts),
            "upcoming_events": _serialize(upcoming_evts),
            "working_hours": "08:00-22:00",
            "calendars": calendars,
        }

    # ---- Conversation ----

    def _on_quick_prompt(self, text: str) -> None:
        """Handle a quick prompt chip click."""
        self._input.setPlainText(text)
        self._on_send(text)

    def _on_send(self, text: str) -> None:
        text = text.strip()
        if not text:
            return

        # Add user message bubble
        user_msg = _ScheduleBubble("user")
        user_msg.set_text(text)
        self._conv_layout.insertWidget(self._conv_layout.count() - 1, user_msg)
        self._scroll_to_bottom()
        self._conversation_history.append({"role": "user", "content": text})

        # Start streaming AI response
        self._start_streaming(text)

    def _start_streaming(self, user_message: str) -> None:
        """Start a streaming AI scheduling request."""
        self._request_id = f"schedule-{uuid.uuid4().hex[:8]}"
        self._streaming_msg = _ScheduleBubble("assistant")
        self._conv_layout.insertWidget(
            self._conv_layout.count() - 1, self._streaming_msg
        )
        self._scroll_to_bottom()

        # Show stop button, disable input
        self._stop_btn.show()
        self._send_btn.hide()
        self._input.setEnabled(False)

        # Build context if not yet built
        if not self._context:
            self._context = self._build_context()

        def on_chunk(chunk: str) -> None:
            QTimer.singleShot(0, lambda: self._handle_chunk(chunk))

        def on_status(status: str) -> None:
            pass

        def callback(success: bool, result: Any) -> None:
            QTimer.singleShot(0, lambda: self._handle_stream_done(success, result))

        self._ai.ai_schedule_streaming(
            user_request=user_message,
            context=self._context,
            conversation_history=self._conversation_history,
            on_chunk=on_chunk,
            on_status=on_status,
            callback=callback,
            request_id=self._request_id,
        )

    def _handle_chunk(self, chunk: str) -> None:
        """Handle a streaming chunk."""
        if self._streaming_msg is not None:
            self._streaming_msg.append_text(chunk)
            self._scroll_to_bottom()

    def _handle_stream_done(self, success: bool, result: Any) -> None:
        """Handle completion of streaming."""
        if not success:
            # Show error
            if self._streaming_msg is not None:
                self._streaming_msg.set_text(
                    f"⚠ Error: {result}" if result else "⚠ An error occurred."
                )
            self._reset_input()
            return

        # Get the full text from the streaming message
        if self._streaming_msg is not None:
            full_text = self._streaming_msg.get_text()
            self._conversation_history.append({
                "role": "assistant",
                "content": full_text,
            })
            self._streaming_msg = None

        # Parse the AI response
        if isinstance(result, dict):
            mode = result.get("mode", "ask")
            message = result.get("message", "")

            if mode == "schedule":
                # AI wants to create events
                events_data = result.get("events", [])
                self._create_events(events_data)
                # Show the AI's summary message
                if message:
                    sys_msg = _ScheduleBubble("system")
                    sys_msg.set_text(message)
                    self._conv_layout.insertWidget(
                        self._conv_layout.count() - 1, sys_msg
                    )
                self._scheduling_done = True
            elif mode == "ask":
                # AI is asking a question - update the streaming bubble
                # with just the message (the streaming text was raw JSON)
                # We already have the full_text in the bubble, but we
                # should replace it with just the message part
                if message:
                    # Find the last assistant bubble and replace text
                    for i in range(self._conv_layout.count() - 1, -1, -1):
                        item = self._conv_layout.itemAt(i)
                        if item and item.widget() and isinstance(item.widget(), _ScheduleBubble):
                            if item.widget().role == "assistant":
                                item.widget().set_text(message)
                                break
            else:
                # Unknown mode, treat as ask
                pass

        self._reset_input()

    def _reset_input(self) -> None:
        """Reset the input area after streaming is done."""
        self._stop_btn.hide()
        self._send_btn.show()
        self._input.setEnabled(True)
        self._input.setFocus()
        self._request_id = None

    def _on_stop(self) -> None:
        """Stop the current streaming request."""
        if self._request_id:
            self._ai.cancel_request(self._request_id)
        self._handle_stream_done(True, {"mode": "ask", "message": "⏹ Stopped."})

    def _create_events(self, events_data: list[dict]) -> None:
        """Create events in the calendar store from AI-provided data."""
        created = []
        for ev_data in events_data:
            try:
                title = ev_data.get("title", "Untitled")
                start_iso = ev_data.get("start_iso", "")
                end_iso = ev_data.get("end_iso", "")
                calendar_id = ev_data.get("calendar_id", "cal-default")
                description = ev_data.get("description", "")
                all_day = ev_data.get("all_day", False)
                event_type_str = ev_data.get("event_type", "task")

                # Parse datetimes
                try:
                    start = datetime.fromisoformat(start_iso)
                except (ValueError, TypeError):
                    # If parsing fails, use tomorrow at 9am
                    start = datetime.now().replace(
                        hour=9, minute=0, second=0, microsecond=0
                    ) + timedelta(days=1)

                try:
                    end = datetime.fromisoformat(end_iso)
                except (ValueError, TypeError):
                    end = start + timedelta(hours=1)

                if end <= start:
                    end = start + timedelta(hours=1)

                # Validate calendar_id
                if not self._store.get_calendar(calendar_id):
                    calendar_id = "cal-default"

                # Parse event type
                try:
                    event_type = EventType(event_type_str)
                except ValueError:
                    event_type = EventType.TASK

                evt = Event.create(
                    calendar_id=calendar_id,
                    title=title,
                    start=start,
                    end=end,
                    description=description,
                    all_day=all_day,
                    event_type=event_type,
                )
                self._store.add_event(evt)
                created.append(evt)
            except Exception:
                continue

        self._created_events = created

        # Show summary
        if created:
            self._summary_label.setText(
                f"✓ {len(created)} event{'s' if len(created) != 1 else ''} created"
            )
            events_text = "\n".join(
                f"  • {ev.title}  "
                f"({format_shamsi(ev.start, include_time=True)})"
                for ev in created
            )
            self._events_list_label.setText(events_text)
            self._summary_frame.show()

            # Show system message in conversation
            sys_msg = _ScheduleBubble("system")
            sys_msg.set_text(
                f"✅ Created {len(created)} event{'s' if len(created) != 1 else ''} in your calendar!\n\n"
                + "\n".join(
                    f"• {ev.title} — {format_shamsi(ev.start, include_time=True)}"
                    for ev in created
                )
            )
            self._conv_layout.insertWidget(
                self._conv_layout.count() - 1, sys_msg
            )

            # Add "Schedule more" button
            more_btn = QPushButton("✦ Schedule More")
            more_btn.setStyleSheet(f"""
                QPushButton {{
                    background-color: {Palette.GOLD_MUTED};
                    color: {Palette.GOLD_BRIGHT};
                    border: 1px solid {Palette.BORDER_GOLD};
                    border-radius: 8px;
                    padding: 8px 20px;
                    font-size: 11px;
                    font-weight: bold;
                }}
                QPushButton:hover {{
                    background-color: {Palette.BG_HOVER};
                    border: 1px solid {Palette.GOLD_PRIMARY};
                }}
            """)
            more_btn.setCursor(Qt.PointingHandCursor)
            more_btn.clicked.connect(lambda: self._summary_frame.hide())
            self._conv_layout.insertWidget(
                self._conv_layout.count() - 1, more_btn
            )

    def _scroll_to_bottom(self) -> None:
        """Scroll the conversation area to the bottom."""
        QTimer.singleShot(
            10,
            lambda: self._scroll.verticalScrollBar().setValue(
                self._scroll.verticalScrollBar().maximum()
            ),
        )

    def showEvent(self, event) -> None:
        """When the dialog is shown, auto-start with a welcome message."""
        super().showEvent(event)
        if not self._conversation_history:
            welcome = _ScheduleBubble("assistant")
            welcome.set_text(
                "👋 Hi! I'm your AI scheduling assistant.\n\n"
                "Tell me what you'd like to schedule and I'll help you plan it. "
                "I can create study plans, work blocks, daily routines, or anything else.\n\n"
                "I'll ask questions if I need more details!"
            )
            self._conv_layout.insertWidget(
                self._conv_layout.count() - 1, welcome
            )
