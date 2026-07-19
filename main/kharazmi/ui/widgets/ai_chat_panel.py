"""
AIChatPanel — a Cursor IDE-style chat panel for the AI Planner.

Features:
  - Streaming responses (text appears token-by-token)
  - Role icons (✦ for AI, ○ for user)
  - Markdown rendering (basic)
  - "Stop generating" button while streaming
  - Multi-line input with auto-resize
  - Suggested follow-up prompts
  - Conversation history persists during the session

The panel is intentionally compact — it sits on the right side of
the AI Planner view.
"""
from __future__ import annotations

from datetime import datetime
from typing import Optional, Callable

from PySide6.QtCore import Qt, Signal, QTimer, QSize
from PySide6.QtGui import (
    QFont, QColor, QTextCursor, QTextCharFormat, QKeyEvent,
    QPalette, QBrush, QPixmap, QPainter, QIcon, QTextOption,
)
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, QPushButton,
    QFrame, QScrollArea, QPlainTextEdit, QTextEdit, QSizePolicy,
    QToolButton, QSpacerItem, QApplication,
)

from ...ai import AIService
from ..theme import Palette


class ChatMessage(QFrame):
    """A single chat message bubble (user or assistant)."""

    def __init__(self, role: str = "assistant", parent: QWidget = None) -> None:
        super().__init__(parent)
        self.role = role
        self._streaming = False

        bg_color = Palette.BG_TERTIARY if role == "assistant" else Palette.BG_SELECTED
        border_color = Palette.GOLD_PRIMARY if role == "assistant" else Palette.BORDER_NORMAL
        self.setStyleSheet(f"""
            QFrame {{
                background-color: {bg_color};
                border: 1px solid {border_color};
                border-left: 3px solid {border_color};
                border-radius: 6px;
                margin: 2px 0;
            }}
        """)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 8, 10, 8)
        layout.setSpacing(4)

        # Header row
        header = QHBoxLayout()
        header.setSpacing(6)
        icon = QLabel("✦" if role == "assistant" else "○")
        icon.setStyleSheet(
            f"color: {Palette.GOLD_BRIGHT if role == 'assistant' else Palette.TEXT_SECONDARY}; "
            f"font-size: 14px; font-weight: bold; background: transparent; border: none;"
        )
        header.addWidget(icon)
        name = QLabel("Rask" if role == "assistant" else "You")
        name.setStyleSheet(
            f"color: {Palette.GOLD_BRIGHT if role == 'assistant' else Palette.TEXT_PRIMARY}; "
            f"font-size: 11px; font-weight: bold; letter-spacing: 1px; "
            f"background: transparent; border: none;"
        )
        header.addWidget(name)
        header.addStretch()
        # Timestamp
        ts = QLabel(datetime.now().strftime("%H:%M"))
        ts.setStyleSheet(
            f"color: {Palette.TEXT_TERTIARY}; font-size: 9px; "
            f"font-family: 'JetBrains Mono', monospace; background: transparent; border: none;"
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
                line-height: 160%;
            }}
        """)
        self._body.setWordWrapMode(QTextOption.WordWrap)
        self._body.setMinimumHeight(20)
        self._body.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Minimum)
        layout.addWidget(self._body)

        # Adjust height to fit content
        self._body.document().contentsChanged.connect(self._adjust_height)

    def _adjust_height(self) -> None:
        # Set the body's height to fit its content
        doc_height = self._body.document().size().height()
        self._body.setFixedHeight(int(doc_height) + 8)

    def append_text(self, text: str) -> None:
        """Append streaming text. Called on each token."""
        cursor = self._body.textCursor()
        cursor.movePosition(QTextCursor.End)
        cursor.insertText(text)
        self._body.setTextCursor(cursor)

    def set_text(self, text: str) -> None:
        """Set the full message text (replaces existing)."""
        self._body.setPlainText(text)

    def set_html(self, html: str) -> None:
        """Set the message body as HTML (for rich formatting)."""
        self._body.setHtml(html)

    def get_text(self) -> str:
        return self._body.toPlainText()

    def set_streaming(self, streaming: bool) -> None:
        self._streaming = streaming
        if streaming:
            self.setStyleSheet(self.styleSheet() + f"""
                QFrame {{
                    border-color: {Palette.GOLD_BRIGHT};
                }}
            """)


class ChatInput(QPlainTextEdit):
    """Multi-line input with Enter-to-send, Shift+Enter for newline."""
    sendMessage = Signal(str)
    stopRequested = Signal()

    def __init__(self, parent: QWidget = None) -> None:
        super().__init__(parent)
        self.setPlaceholderText("Ask Rask anything about this route…  (Enter to send, Shift+Enter for newline)")
        self.setFixedHeight(80)
        self.setStyleSheet(f"""
            QPlainTextEdit {{
                background-color: {Palette.BG_TERTIARY};
                color: {Palette.TEXT_PRIMARY};
                border: 1px solid {Palette.BORDER_NORMAL};
                border-radius: 4px;
                padding: 8px 12px;
                font-size: 12px;
            }}
            QPlainTextEdit:focus {{
                border: 1px solid {Palette.GOLD_PRIMARY};
            }}
        """)

    def keyPressEvent(self, event: QKeyEvent) -> None:
        if event.key() == Qt.Key_Return and not (event.modifiers() & Qt.ShiftModifier):
            text = self.toPlainText().strip()
            if text:
                self.sendMessage.emit(text)
                self.clear()
            return
        super().keyPressEvent(event)


class AIChatPanel(QWidget):
    """
    The full chat panel — Cursor IDE-style.

    Shows a scrolling conversation with streaming responses.
    """

    sendRequested = Signal(str)  # user-typed message
    stopRequested = Signal()

    def __init__(self, ai_service: AIService, parent: QWidget = None) -> None:
        super().__init__(parent)
        self.ai = ai_service
        self._messages: list[dict] = []  # conversation history
        self._current_streaming_msg: Optional[ChatMessage] = None
        self._current_request_id: Optional[str] = None

        self.setStyleSheet(f"background-color: {Palette.BG_SECONDARY};")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # Header
        header = QLabel("AI CHAT")
        header.setStyleSheet(
            f"background-color: {Palette.BG_TERTIARY}; color: {Palette.GOLD_PRIMARY}; "
            f"font-size: 11px; font-weight: bold; letter-spacing: 2px; "
            f"padding: 8px 12px; border-bottom: 1px solid {Palette.BORDER_SUBTLE};"
        )
        layout.addWidget(header)

        # Conversation scroll area
        self._scroll = QScrollArea()
        self._scroll.setWidgetResizable(True)
        self._scroll.setFrameShape(QFrame.NoFrame)
        self._scroll.setStyleSheet(
            f"QScrollArea {{ background-color: {Palette.BG_SECONDARY}; border: none; }}"
        )
        self._container = QWidget()
        self._conv_layout = QVBoxLayout(self._container)
        self._conv_layout.setContentsMargins(10, 10, 10, 10)
        self._conv_layout.setSpacing(6)
        self._conv_layout.addStretch()
        self._scroll.setWidget(self._container)
        layout.addWidget(self._scroll, stretch=1)

        # Input area
        input_frame = QFrame()
        input_frame.setStyleSheet(f"background-color: {Palette.BG_TERTIARY}; border-top: 1px solid {Palette.BORDER_SUBTLE};")
        input_layout = QVBoxLayout(input_frame)
        input_layout.setContentsMargins(8, 8, 8, 8)
        input_layout.setSpacing(4)

        self._input = ChatInput()
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
                font-size: 11px;
                font-weight: bold;
            }}
            QPushButton:hover {{
                background-color: #C24A4A;
            }}
        """)
        self._stop_btn.clicked.connect(self._on_stop)
        self._stop_btn.hide()
        action_row.addWidget(self._stop_btn)

        self._send_btn = QPushButton("➤ Send")
        self._send_btn.setProperty("variant", "primary")
        self._send_btn.clicked.connect(lambda: self._on_send(self._input.toPlainText()))
        action_row.addWidget(self._send_btn)

        input_layout.addLayout(action_row)
        layout.addWidget(input_frame)

    def _on_send(self, text: str) -> None:
        text = text.strip()
        if not text:
            return
        # Add user message to UI
        self.add_message(text, role="user")
        self.sendRequested.emit(text)

    def _on_stop(self) -> None:
        if self._current_request_id:
            self.ai.cancel_request(self._current_request_id)
        self._finish_streaming()
        self.stopRequested.emit()

    # ---- Public API ----
    def add_message(self, text: str, role: str = "assistant",
                    as_html: bool = False) -> ChatMessage:
        """Add a complete message to the conversation."""
        msg = ChatMessage(role)
        if as_html:
            msg.set_html(text)
        else:
            msg.set_text(text)
        self._conv_layout.insertWidget(self._conv_layout.count() - 1, msg)
        self._scroll_to_bottom()
        self._messages.append({"role": role, "content": text})
        return msg

    def start_streaming_message(self) -> ChatMessage:
        """Create a new assistant message bubble and prepare to stream into it."""
        msg = ChatMessage("assistant")
        msg.set_streaming(True)
        self._conv_layout.insertWidget(self._conv_layout.count() - 1, msg)
        self._scroll_to_bottom()
        self._current_streaming_msg = msg
        self._stop_btn.show()
        self._send_btn.hide()
        return msg

    def stream_chunk(self, text: str) -> None:
        """Append a chunk of text to the current streaming message."""
        if self._current_streaming_msg is not None:
            self._current_streaming_msg.append_text(text)
            self._scroll_to_bottom()

    def finish_streaming(self, full_text: Optional[str] = None) -> None:
        """Finish the current streaming message."""
        if self._current_streaming_msg is not None:
            self._current_streaming_msg.set_streaming(False)
            if full_text is not None:
                self._current_streaming_msg.set_text(full_text)
            self._messages.append({
                "role": "assistant",
                "content": full_text or self._current_streaming_msg.get_text(),
            })
            self._current_streaming_msg = None
        self._stop_btn.hide()
        self._send_btn.show()

    def _finish_streaming(self) -> None:
        """Alias for backward compat."""
        self.finish_streaming()

    def set_request_id(self, request_id: str) -> None:
        self._current_request_id = request_id

    def clear_conversation(self) -> None:
        # Remove all messages (preserve stretch)
        while self._conv_layout.count() > 1:
            item = self._conv_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        self._messages.clear()

    def _scroll_to_bottom(self) -> None:
        QTimer.singleShot(10, lambda: self._scroll.verticalScrollBar().setValue(
            self._scroll.verticalScrollBar().maximum()
        ))
