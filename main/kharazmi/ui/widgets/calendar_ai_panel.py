"""
CalendarAIPanel — a compact, collapsible AI chat panel for the Calendar view.

Features:
  - Floating/dockable panel that sits on the right side of the calendar
  - Collapsible: toggle button with ✦ icon
  - When collapsed: just a small ✦ button in the bottom-right corner
  - When expanded: a chat panel ~320px wide, full height
  - Context-aware: auto-includes Shamsi date, current view, events
  - Pre-built quick question chips (bilingual)
  - Streaming responses via AIService.calendar_chat_streaming()
  - Compact message bubbles (QLabel-based)
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Optional, Any

from PySide6.QtCore import Qt, Signal, QTimer, QSize
from PySide6.QtGui import (
    QFont, QColor, QTextCursor, QTextOption, QKeyEvent,
)
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QFrame, QScrollArea, QPlainTextEdit, QTextEdit, QSizePolicy,
    QToolButton, QApplication,
)

from ...ai import AIService
from ...core.shamsi import ShamsiDate, format_shamsi
from ..theme import Palette


# ---- RTL detection ----

def _is_rtl(text: str) -> bool:
    """Detect if text is primarily RTL (Persian/Arabic)."""
    rtl_count = sum(
        1 for ch in text
        if '\u0600' <= ch <= '\u06FF'
        or '\uFB50' <= ch <= '\uFDFF'
        or '\uFE70' <= ch <= '\uFEFF'
    )
    return rtl_count > len(text) * 0.3


# ---- Compact message bubble ----

class _MessageBubble(QFrame):
    """A compact chat message bubble using QTextEdit for rich text."""

    def __init__(self, role: str = "assistant", parent: QWidget = None) -> None:
        super().__init__(parent)
        self.role = role

        if role == "assistant":
            bg = Palette.BG_TERTIARY
            border_left = Palette.GOLD_PRIMARY
            icon = "✦"
            name = "Rask"
            icon_color = Palette.GOLD_BRIGHT
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

        # Header row: icon + name + timestamp
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
                font-size: 11px;
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


# ---- Quick question chip ----

class _QuickChip(QPushButton):
    """A compact clickable chip for quick questions."""

    clicked_with_text = Signal(str)

    def __init__(self, text: str, parent: QWidget = None) -> None:
        super().__init__(text, parent)
        self._text = text
        self.setStyleSheet(f"""
            QPushButton {{
                background-color: {Palette.BG_ELEVATED};
                color: {Palette.GOLD_PRIMARY};
                border: 1px solid {Palette.BORDER_GOLD};
                border-radius: 10px;
                padding: 3px 10px;
                font-size: 10px;
            }}
            QPushButton:hover {{
                background-color: {Palette.BG_HOVER};
                color: {Palette.GOLD_BRIGHT};
                border: 1px solid {Palette.GOLD_PRIMARY};
            }}
            QPushButton:pressed {{
                background-color: {Palette.GOLD_MUTED};
            }}
        """)
        self.setCursor(Qt.PointingHandCursor)
        self.clicked.connect(lambda: self.clicked_with_text.emit(self._text))


# ---- Compact chat input ----

class _ChatInput(QPlainTextEdit):
    """Multi-line input. Enter sends, Shift+Enter for newline."""

    sendMessage = Signal(str)

    def __init__(self, parent: QWidget = None) -> None:
        super().__init__(parent)
        self.setPlaceholderText(
            "Ask about your calendar…  (Enter to send)"
        )
        self.setStyleSheet(f"""
            QPlainTextEdit {{
                background-color: {Palette.BG_TERTIARY};
                color: {Palette.TEXT_PRIMARY};
                border: 1px solid {Palette.BORDER_NORMAL};
                border-radius: 4px;
                padding: 6px 10px;
                font-size: 11px;
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


# ---- Main panel ----

class CalendarAIPanel(QWidget):
    """Floating AI chat panel for the Calendar view.

    Collapsible panel with context-aware calendar chat.
    When collapsed, shows a small ✦ toggle button.
    When expanded, shows a ~320px wide chat panel.
    """

    # Quick questions (bilingual)
    QUICK_QUESTIONS = [
        ("What's my schedule today?", "برنامه امروز چیست؟"),
        ("When am I free this week?", "کی هفته آزادم؟"),
        ("Am I overbooked?", "آیا خیلی سرم شلوغه؟"),
        ("Suggest a study plan", "یک برنامه پیشنهاد بده"),
    ]

    def __init__(
        self,
        calendar_store: Any,
        ai_service: AIService,
        parent: QWidget = None,
    ) -> None:
        super().__init__(parent)
        self._store = calendar_store
        self._ai = ai_service
        self._expanded = False
        self._streaming_msg: Optional[_MessageBubble] = None
        self._request_id: Optional[str] = None
        self._conversation_history: list[dict] = []

        # Calendar context
        self._current_date: str = ""
        self._current_view: str = "month"
        self._visible_events: list[dict] = []
        self._today_events: list[dict] = []
        self._upcoming_events: list[dict] = []

        self._setup_ui()

    # ---- UI Setup ----

    def _setup_ui(self) -> None:
        self.setStyleSheet(f"background-color: transparent;")

        # Root layout — we stack the toggle button and panel
        self._root_layout = QVBoxLayout(self)
        self._root_layout.setContentsMargins(0, 0, 0, 0)
        self._root_layout.setSpacing(0)
        self._root_layout.addStretch()

        # Toggle button (always visible)
        self._toggle_btn = QToolButton()
        self._toggle_btn.setText("✦")
        self._toggle_btn.setFixedSize(40, 40)
        self._toggle_btn.setCursor(Qt.PointingHandCursor)
        self._toggle_btn.setToolTip("Toggle Calendar AI Assistant")
        self._toggle_btn.setStyleSheet(f"""
            QToolButton {{
                background-color: {Palette.BG_TERTIARY};
                color: {Palette.GOLD_BRIGHT};
                border: 1px solid {Palette.BORDER_GOLD};
                border-radius: 20px;
                font-size: 18px;
                font-weight: bold;
            }}
            QToolButton:hover {{
                background-color: {Palette.BG_HOVER};
                border: 1px solid {Palette.GOLD_PRIMARY};
            }}
            QToolButton:pressed {{
                background-color: {Palette.GOLD_MUTED};
            }}
        """)
        self._toggle_btn.clicked.connect(self.toggle_visibility)
        self._root_layout.addWidget(self._toggle_btn, alignment=Qt.AlignRight | Qt.AlignBottom)

        # Panel widget (initially hidden)
        self._panel = QFrame()
        self._panel.setFixedWidth(320)
        self._panel.setStyleSheet(f"""
            QFrame {{
                background-color: {Palette.BG_SECONDARY};
                border: 1px solid {Palette.BORDER_SUBTLE};
                border-radius: 8px;
            }}
        """)
        self._panel.hide()

        panel_layout = QVBoxLayout(self._panel)
        panel_layout.setContentsMargins(0, 0, 0, 0)
        panel_layout.setSpacing(0)

        # -- Header --
        header = QFrame()
        header.setStyleSheet(
            f"background-color: {Palette.BG_TERTIARY}; "
            f"border-bottom: 1px solid {Palette.BORDER_SUBTLE}; "
            f"border-top-left-radius: 8px; "
            f"border-top-right-radius: 8px;"
        )
        header.setFixedHeight(34)
        header_layout = QHBoxLayout(header)
        header_layout.setContentsMargins(10, 4, 10, 4)
        header_layout.setSpacing(6)

        icon_lbl = QLabel("✦")
        icon_lbl.setStyleSheet(
            f"color: {Palette.GOLD_BRIGHT}; font-size: 13px; "
            f"font-weight: bold; background: transparent; border: none;"
        )
        header_layout.addWidget(icon_lbl)
        title_lbl = QLabel("Rask Calendar Assistant")
        title_lbl.setStyleSheet(
            f"color: {Palette.GOLD_PRIMARY}; font-size: 10px; "
            f"font-weight: bold; letter-spacing: 1px; "
            f"background: transparent; border: none;"
        )
        header_layout.addWidget(title_lbl)
        header_layout.addStretch()

        # Clear button
        clear_btn = QToolButton()
        clear_btn.setText("Clear")
        clear_btn.setStyleSheet(f"""
            QToolButton {{
                background: transparent;
                color: {Palette.TEXT_TERTIARY};
                border: none;
                font-size: 9px;
                padding: 2px 4px;
            }}
            QToolButton:hover {{
                color: {Palette.GOLD_BRIGHT};
            }}
        """)
        clear_btn.clicked.connect(self._clear_conversation)
        header_layout.addWidget(clear_btn)

        # Close/collapse button
        close_btn = QToolButton()
        close_btn.setText("✕")
        close_btn.setStyleSheet(f"""
            QToolButton {{
                background: transparent;
                color: {Palette.TEXT_TERTIARY};
                border: none;
                font-size: 12px;
                padding: 2px 4px;
            }}
            QToolButton:hover {{
                color: {Palette.GOLD_BRIGHT};
            }}
        """)
        close_btn.clicked.connect(self.toggle_visibility)
        header_layout.addWidget(close_btn)

        panel_layout.addWidget(header)

        # -- Quick questions area --
        chips_frame = QFrame()
        chips_frame.setStyleSheet(
            f"background-color: {Palette.BG_SECONDARY}; "
            f"border-bottom: 1px solid {Palette.BORDER_SUBTLE};"
        )
        chips_layout = QVBoxLayout(chips_frame)
        chips_layout.setContentsMargins(8, 6, 8, 6)
        chips_layout.setSpacing(3)

        chips_label = QLabel("Quick questions:")
        chips_label.setStyleSheet(
            f"color: {Palette.TEXT_TERTIARY}; font-size: 9px; "
            f"font-weight: bold; letter-spacing: 0.5px; "
            f"background: transparent; border: none;"
        )
        chips_layout.addWidget(chips_label)

        chips_row = QHBoxLayout()
        chips_row.setSpacing(4)
        chips_row.setContentsMargins(0, 0, 0, 0)

        for en_text, fa_text in self.QUICK_QUESTIONS:
            chip = _QuickChip(en_text)
            chip.setToolTip(fa_text)
            chip.clicked_with_text.connect(self._on_quick_question)
            chips_row.addWidget(chip)

        chips_row.addStretch()
        chips_layout.addLayout(chips_row)
        panel_layout.addWidget(chips_frame)

        # -- Conversation scroll area --
        self._scroll = QScrollArea()
        self._scroll.setWidgetResizable(True)
        self._scroll.setFrameShape(QFrame.NoFrame)
        self._scroll.setStyleSheet(
            f"QScrollArea {{ background-color: {Palette.BG_SECONDARY}; border: none; }}"
        )
        self._container = QWidget()
        self._conv_layout = QVBoxLayout(self._container)
        self._conv_layout.setContentsMargins(8, 8, 8, 8)
        self._conv_layout.setSpacing(4)
        self._conv_layout.addStretch()
        self._scroll.setWidget(self._container)
        panel_layout.addWidget(self._scroll, stretch=1)

        # -- Input area --
        input_frame = QFrame()
        input_frame.setStyleSheet(
            f"background-color: {Palette.BG_TERTIARY}; "
            f"border-top: 1px solid {Palette.BORDER_SUBTLE}; "
            f"border-bottom-left-radius: 8px; "
            f"border-bottom-right-radius: 8px;"
        )
        input_layout = QVBoxLayout(input_frame)
        input_layout.setContentsMargins(6, 6, 6, 6)
        input_layout.setSpacing(4)

        self._input = _ChatInput()
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
                padding: 3px 10px;
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

        self._send_btn = QPushButton("➤")
        self._send_btn.setProperty("variant", "primary")
        self._send_btn.setFixedSize(28, 24)
        self._send_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: {Palette.GOLD_PRIMARY};
                color: {Palette.TEXT_ON_GOLD};
                border: 1px solid {Palette.GOLD_DEEP};
                border-radius: 3px;
                font-size: 12px;
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
        panel_layout.addWidget(input_frame)

        # Add panel to root (below stretch, above toggle)
        self._root_layout.insertWidget(0, self._panel, alignment=Qt.AlignRight)

    # ---- Public API ----

    def set_context(
        self,
        current_date: str,
        current_view: str,
        visible_events: list,
        today_events: list,
        upcoming_events: list,
    ) -> None:
        """Update the AI context with current calendar state.

        Args:
            current_date: Shamsi-formatted date string.
            current_view: One of 'month', 'week', 'day', 'year'.
            visible_events: List of event dicts visible in the current view.
            today_events: List of event dicts for today.
            upcoming_events: List of event dicts for the next 7 days.
        """
        self._current_date = current_date
        self._current_view = current_view
        self._visible_events = self._serialize_events(visible_events)
        self._today_events = self._serialize_events(today_events)
        self._upcoming_events = self._serialize_events(upcoming_events)

    def toggle_visibility(self) -> None:
        """Toggle between collapsed (just button) and expanded (full panel)."""
        self._expanded = not self._expanded
        if self._expanded:
            self._panel.show()
            self._toggle_btn.hide()
            # Auto-update context when expanding
            self._auto_update_context()
        else:
            self._panel.hide()
            self._toggle_btn.show()

    def is_expanded(self) -> bool:
        """Return whether the panel is currently expanded."""
        return self._expanded

    def update_context_from_store(self) -> None:
        """Manually trigger a context refresh from the calendar store."""
        self._auto_update_context()

    # ---- Internal helpers ----

    def _auto_update_context(self) -> None:
        """Automatically populate context from the calendar store."""
        if self._store is None:
            return

        now = datetime.utcnow()
        today_shamsi = ShamsiDate.from_gregorian(now.date())
        self._current_date = today_shamsi.format("yyyy/mm/dd EEEE")

        try:
            today_evts = self._store.events_on_day(now.date())
        except Exception:
            today_evts = []

        try:
            upcoming_evts = self._store.upcoming_events(days=7)
        except Exception:
            upcoming_evts = []

        self._today_events = self._serialize_events(today_evts)
        self._upcoming_events = self._serialize_events(upcoming_evts)
        # visible_events are set externally via set_context since they
        # depend on the active view mode

    def _serialize_events(self, events: list) -> list[dict]:
        """Convert a list of Event objects (or dicts) to serializable dicts."""
        result = []
        for ev in events:
            if isinstance(ev, dict):
                result.append(ev)
            else:
                # Event object — extract key fields
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
                        "location": getattr(ev, "location", ""),
                    })
                except Exception:
                    continue
        return result

    def _build_context(self) -> dict:
        """Build the context dict for the AI service."""
        return {
            "current_date": self._current_date,
            "current_view": self._current_view,
            "visible_events": self._visible_events,
            "today_events": self._today_events,
            "upcoming_events": self._upcoming_events,
        }

    # ---- Chat logic ----

    def _on_send(self, text: str) -> None:
        text = text.strip()
        if not text:
            return

        # Add user message bubble
        user_msg = _MessageBubble("user")
        user_msg.set_text(text)
        self._conv_layout.insertWidget(self._conv_layout.count() - 1, user_msg)
        self._scroll_to_bottom()
        self._conversation_history.append({"role": "user", "content": text})

        # Start streaming AI response
        self._start_streaming(text)

    def _on_quick_question(self, text: str) -> None:
        """Handle a quick question chip click."""
        self._input.setPlainText(text)
        self._on_send(text)

    def _start_streaming(self, user_message: str) -> None:
        """Start a streaming AI response."""
        self._request_id = f"cal-ai-{uuid.uuid4().hex[:8]}"
        self._streaming_msg = _MessageBubble("assistant")
        self._conv_layout.insertWidget(
            self._conv_layout.count() - 1, self._streaming_msg
        )
        self._scroll_to_bottom()

        # Show stop button, hide send
        self._stop_btn.show()
        self._send_btn.hide()
        self._input.setEnabled(False)

        context = self._build_context()

        def on_chunk(chunk: str) -> None:
            # Must update UI on the main thread
            QTimer.singleShot(0, lambda: self._handle_chunk(chunk))

        def on_status(status: str) -> None:
            pass  # Could show status in the streaming bubble

        def callback(success: bool, result: Any) -> None:
            QTimer.singleShot(0, lambda: self._handle_stream_done(success, result))

        self._ai.calendar_chat_streaming(
            user_message=user_message,
            context=context,
            on_chunk=on_chunk,
            on_status=on_status,
            callback=callback,
            request_id=self._request_id,
        )

    def _handle_chunk(self, chunk: str) -> None:
        """Handle a streaming chunk (called on main thread via QTimer)."""
        if self._streaming_msg is not None:
            self._streaming_msg.append_text(chunk)
            self._scroll_to_bottom()

    def _handle_stream_done(self, success: bool, result: Any) -> None:
        """Handle completion of streaming (called on main thread via QTimer)."""
        if self._streaming_msg is not None:
            text = self._streaming_msg.get_text()
            self._conversation_history.append({
                "role": "assistant",
                "content": text,
            })
            self._streaming_msg = None

        self._stop_btn.hide()
        self._send_btn.show()
        self._input.setEnabled(True)
        self._input.setFocus()
        self._request_id = None

    def _on_stop(self) -> None:
        """Stop the current streaming request."""
        if self._request_id:
            self._ai.cancel_request(self._request_id)
        self._handle_stream_done(True, None)

    def _clear_conversation(self) -> None:
        """Clear all messages from the conversation."""
        while self._conv_layout.count() > 1:
            item = self._conv_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        self._conversation_history.clear()
        self._streaming_msg = None

    def _scroll_to_bottom(self) -> None:
        """Scroll the conversation area to the bottom."""
        QTimer.singleShot(
            10,
            lambda: self._scroll.verticalScrollBar().setValue(
                self._scroll.verticalScrollBar().maximum()
            ),
        )

    # ---- Size hints ----

    def sizeHint(self) -> QSize:
        if self._expanded:
            return QSize(320, 400)
        return QSize(40, 40)

    def minimumSizeHint(self) -> QSize:
        if self._expanded:
            return QSize(320, 200)
        return QSize(40, 40)
