"""
AIChatPanel — a professional Cursor IDE-style chat panel.

Features:
  - Streaming responses with REAL text (not JSON)
  - For structured operations (route generation), shows meaningful
    status boxes like 'Building fallback branches…' instead of raw JSON
  - Role icons (✦ for AI, ○ for user)
  - Multi-line input with auto-resize
  - Stop button while streaming
  - Suggested follow-up prompts
  - Clean, professional styling
"""
from __future__ import annotations

from datetime import datetime
from typing import Optional, Callable

from PySide6.QtCore import Qt, Signal, QTimer, QSize
from PySide6.QtGui import (
    QFont, QColor, QTextCursor, QTextCharFormat, QKeyEvent,
    QTextOption, QKeyEvent,
)
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, QPushButton,
    QFrame, QScrollArea, QPlainTextEdit, QTextEdit, QSizePolicy,
    QToolButton, QSpacerItem, QApplication,
)

from ...ai import AIService
from ..theme import Palette


def _is_rtl(text: str) -> bool:
    """Detect if text is primarily RTL (Persian/Arabic)."""
    rtl_count = sum(1 for ch in text if '\u0600' <= ch <= '\u06FF' or '\uFB50' <= ch <= '\uFDFF' or '\uFE70' <= ch <= '\uFEFF')
    return rtl_count > len(text) * 0.3


class StatusBox(QFrame):
    """A small status box shown during structured operations.
    Displays messages like 'Building fallback branches…' instead of raw JSON."""

    def __init__(self, text: str = "", parent: QWidget = None) -> None:
        super().__init__(parent)
        self.setStyleSheet(f"""
            QFrame {{
                background-color: {Palette.BG_TERTIARY};
                border: 1px solid {Palette.BORDER_GOLD};
                border-left: 3px solid {Palette.GOLD_BRIGHT};
                border-radius: 4px;
                margin: 2px 0;
            }}
        """)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(10, 6, 10, 6)
        layout.setSpacing(8)

        # Spinner icon (animated)
        self._spinner = QLabel("◐")
        self._spinner.setStyleSheet(
            f"color: {Palette.GOLD_BRIGHT}; font-size: 14px; "
            f"background: transparent; border: none;"
        )
        layout.addWidget(self._spinner)

        self._label = QLabel(text)
        self._label.setStyleSheet(
            f"color: {Palette.TEXT_PRIMARY}; font-size: 12px; "
            f"background: transparent; border: none;"
        )
        self._label.setWordWrap(True)
        layout.addWidget(self._label, stretch=1)

        # Animate the spinner
        self._spinner_chars = ["◐", "◓", "◑", "◒"]
        self._spinner_idx = 0
        self._spinner_timer = QTimer(self)
        self._spinner_timer.setInterval(150)
        self._spinner_timer.timeout.connect(self._tick_spinner)
        self._spinner_timer.start()

    def _tick_spinner(self) -> None:
        self._spinner_idx = (self._spinner_idx + 1) % len(self._spinner_chars)
        self._spinner.setText(self._spinner_chars[self._spinner_idx])

    def set_text(self, text: str) -> None:
        self._label.setText(text)

    def stop_spinner(self) -> None:
        self._spinner_timer.stop()
        self._spinner.setText("✓")
        self._spinner.setStyleSheet(
            f"color: {Palette.GOLD_BRIGHT}; font-size: 14px; "
            f"background: transparent; border: none;"
        )


class ChatMessage(QFrame):
    """A chat message bubble (user or assistant). Auto-sizes to content."""

    def __init__(self, role: str = "assistant", parent: QWidget = None) -> None:
        super().__init__(parent)
        self.role = role

        if role == "assistant":
            bg_color = Palette.BG_TERTIARY
            border_color = Palette.GOLD_PRIMARY
            icon = "✦"
            name = "Rask"
            icon_color = Palette.GOLD_BRIGHT
        else:
            bg_color = Palette.BG_SELECTED
            border_color = Palette.BORDER_NORMAL
            icon = "○"
            name = "You"
            icon_color = Palette.TEXT_SECONDARY

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
        layout.setContentsMargins(12, 8, 12, 8)
        layout.setSpacing(4)

        # Header row
        header = QHBoxLayout()
        header.setSpacing(6)
        icon_label = QLabel(icon)
        icon_label.setStyleSheet(
            f"color: {icon_color}; font-size: 14px; font-weight: bold; "
            f"background: transparent; border: none;"
        )
        header.addWidget(icon_label)
        name_label = QLabel(name)
        name_label.setStyleSheet(
            f"color: {icon_color}; font-size: 11px; font-weight: bold; "
            f"letter-spacing: 1px; background: transparent; border: none;"
        )
        header.addWidget(name_label)
        header.addStretch()
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
            }}
        """)
        self._body.setWordWrapMode(QTextOption.WordWrap)
        self._body.setMinimumHeight(20)
        self._body.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Minimum)
        layout.addWidget(self._body)

        self._body.document().contentsChanged.connect(self._adjust_height)

    def _adjust_height(self) -> None:
        doc_height = self._body.document().size().height()
        self._body.setFixedHeight(int(doc_height) + 8)

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

    def set_html(self, html: str) -> None:
        self._body.setHtml(html)
        plain = self._body.toPlainText()
        if _is_rtl(plain):
            self._body.setLayoutDirection(Qt.RightToLeft)
        else:
            self._body.setLayoutDirection(Qt.LeftToRight)

    def get_text(self) -> str:
        return self._body.toPlainText()


class ChatInput(QPlainTextEdit):
    """Multi-line input. Enter sends, Shift+Enter for newline."""
    sendMessage = Signal(str)

    def __init__(self, parent: QWidget = None) -> None:
        super().__init__(parent)
        self.setPlaceholderText("Ask Rask about this route…  (Enter to send, Shift+Enter for newline)")
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
        self.setMaximumHeight(120)
        self.setMinimumHeight(40)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)

    def keyPressEvent(self, event: QKeyEvent) -> None:
        if event.key() == Qt.Key_Return and not (event.modifiers() & Qt.ShiftModifier):
            text = self.toPlainText().strip()
            if text:
                self.sendMessage.emit(text)
                self.clear()
            return
        super().keyPressEvent(event)


class AIChatPanel(QWidget):
    """Professional Cursor IDE-style chat panel."""

    sendRequested = Signal(str)
    stopRequested = Signal()

    def __init__(self, ai_service: AIService, parent: QWidget = None) -> None:
        super().__init__(parent)
        self.ai = ai_service
        self._messages: list[dict] = []
        self._current_streaming_msg: Optional[ChatMessage] = None
        self._current_status_box: Optional[StatusBox] = None
        self._current_request_id: Optional[str] = None

        self.setStyleSheet(f"background-color: {Palette.BG_SECONDARY};")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # Header
        header = QFrame()
        header.setStyleSheet(
            f"background-color: {Palette.BG_TERTIARY}; "
            f"border-bottom: 1px solid {Palette.BORDER_SUBTLE};"
        )
        header.setFixedHeight(36)
        header_layout = QHBoxLayout(header)
        header_layout.setContentsMargins(12, 4, 12, 4)
        header_layout.setSpacing(8)

        icon = QLabel("✦")
        icon.setStyleSheet(
            f"color: {Palette.GOLD_BRIGHT}; font-size: 14px; "
            f"font-weight: bold; background: transparent; border: none;"
        )
        header_layout.addWidget(icon)
        title = QLabel("RASK ASSISTANT")
        title.setStyleSheet(
            f"color: {Palette.GOLD_PRIMARY}; font-size: 11px; "
            f"font-weight: bold; letter-spacing: 2px; "
            f"background: transparent; border: none;"
        )
        header_layout.addWidget(title)
        header_layout.addStretch()

        # Clear button
        clear_btn = QToolButton()
        clear_btn.setText("Clear")
        clear_btn.setStyleSheet(f"""
            QToolButton {{
                background: transparent;
                color: {Palette.TEXT_TERTIARY};
                border: none;
                font-size: 10px;
                padding: 2px 6px;
            }}
            QToolButton:hover {{
                color: {Palette.GOLD_BRIGHT};
            }}
        """)
        clear_btn.clicked.connect(self.clear_conversation)
        header_layout.addWidget(clear_btn)

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
        input_frame.setStyleSheet(
            f"background-color: {Palette.BG_TERTIARY}; "
            f"border-top: 1px solid {Palette.BORDER_SUBTLE};"
        )
        input_layout = QVBoxLayout(input_frame)
        input_layout.setContentsMargins(8, 8, 8, 8)
        input_layout.setSpacing(4)

        self._input = ChatInput()
        self._input.sendMessage.connect(self._on_send)
        input_layout.addWidget(self._input)

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

    def start_status_box(self, initial_text: str = "Working…") -> StatusBox:
        """Show a status box (used during structured operations like route generation).
        Shows meaningful status text instead of raw JSON."""
        box = StatusBox(initial_text)
        self._conv_layout.insertWidget(self._conv_layout.count() - 1, box)
        self._scroll_to_bottom()
        self._current_status_box = box
        self._stop_btn.show()
        self._send_btn.hide()
        return box

    def update_status(self, text: str) -> None:
        """Update the current status box's text."""
        if self._current_status_box is not None:
            self._current_status_box.set_text(text)

    def finish_status_box(self, final_text: Optional[str] = None) -> None:
        """Mark the status box as done (changes spinner to checkmark)."""
        if self._current_status_box is not None:
            self._current_status_box.stop_spinner()
            if final_text:
                self._current_status_box.set_text(final_text)
            self._current_status_box = None
        self._stop_btn.hide()
        self._send_btn.show()

    def start_streaming_message(self) -> ChatMessage:
        """Start a streaming assistant message (for free-form chat, not structured ops)."""
        msg = ChatMessage("assistant")
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
        if self._current_streaming_msg is not None:
            if full_text is not None:
                self._current_streaming_msg.set_text(full_text)
            self._messages.append({
                "role": "assistant",
                "content": full_text or self._current_streaming_msg.get_text(),
            })
            self._current_streaming_msg = None
        self._stop_btn.hide()
        self._send_btn.show()

    def set_request_id(self, request_id: str) -> None:
        self._current_request_id = request_id

    def clear_conversation(self) -> None:
        while self._conv_layout.count() > 1:
            item = self._conv_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        self._messages.clear()
        self._current_streaming_msg = None
        self._current_status_box = None

    def _scroll_to_bottom(self) -> None:
        QTimer.singleShot(10, lambda: self._scroll.verticalScrollBar().setValue(
            self._scroll.verticalScrollBar().maximum()
        ))
