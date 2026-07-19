"""
AIPlannerView — the main "Enterprise analysis screen".

Layout:
  ┌──────────────────────────────────────────────────────────────────┐
  │ Top bar: Goal input box + "Plan with AI" button                  │
  ├──────────────────────────────────┬───────────────────────────────┤
  │ Route Graph (left, large)        │ Side Panel (right)            │
  │                                  │ ┌─────────────────────────┐  │
  │  [node]──[node]──[node]          │ │ Conversation            │  │
  │                                  │ │ (clarifying Q&A +       │  │
  │  with success %, time, risk      │ │  AI responses)          │  │
  │                                  │ └─────────────────────────┘  │
  │                                  │ ┌─────────────────────────┐  │
  │                                  │ │ Selected Step Details   │  │
  │                                  │ │ (description, fallback, │  │
  │                                  │ │  sub-goals, etc.)       │  │
  │                                  │ └─────────────────────────┘  │
  │                                  │ ┌─────────────────────────┐  │
  │                                  │ │ Improvements &          │  │
  │                                  │ │ Follow-up Questions     │  │
  │                                  │ └─────────────────────────┘  │
  ├──────────────────────────────────┴───────────────────────────────┤
  │ Bottom: Stats (overall success %, total duration, step count)    │
  └──────────────────────────────────────────────────────────────────┘

Flow:
  1. User types a goal in the top input
  2. Clicks "Plan with AI"
  3. AI either:
     - Asks clarifying questions → user answers → AI generates route
     - Generates route directly (if goal is clear)
  4. Route appears in the graph view
  5. Conversation and details appear in the side panel
  6. Entry is saved to the journal
"""
from __future__ import annotations

from datetime import datetime
from typing import Optional

from PySide6.QtCore import Qt, Signal, QTimer
from PySide6.QtGui import (
    QFont, QColor, QKeyEvent, QTextCursor, QTextCharFormat,
)
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, QPushButton,
    QFrame, QSplitter, QScrollArea, QPlainTextEdit, QTextEdit,
    QSizePolicy, QMessageBox, QApplication,
)

from ...ai import (
    AIService, Route, RouteStep, JournalStore,
)
from ...core.shamsi import ShamsiDate, format_shamsi
from ..theme import Palette
from ..views.route_graph_view import RouteGraphView


class MessageBubble(QFrame):
    """A chat-style message bubble."""
    def __init__(self, text: str, role: str = "assistant") -> None:
        super().__init__()
        self.role = role
        bg = Palette.BG_TERTIARY if role == "assistant" else Palette.BG_SELECTED
        fg = Palette.GOLD_BRIGHT if role == "assistant" else Palette.TEXT_PRIMARY
        prefix = "✦ Rask" if role == "assistant" else "You"
        self.setStyleSheet(f"""
            QFrame {{
                background-color: {bg};
                border: 1px solid {Palette.BORDER_NORMAL};
                border-radius: 6px;
                padding: 8px 12px;
                margin: 2px 0;
            }}
        """)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 6, 10, 6)
        layout.setSpacing(2)
        label = QLabel(prefix)
        label.setStyleSheet(
            f"color: {fg}; font-size: 9px; font-weight: bold; "
            f"letter-spacing: 1.5px; background: transparent; border: none;"
        )
        layout.addWidget(label)
        body = QLabel(text)
        body.setWordWrap(True)
        body.setStyleSheet(
            f"color: {Palette.TEXT_PRIMARY}; font-size: 12px; "
            f"background: transparent; border: none;"
        )
        body.setTextFormat(Qt.RichText)
        layout.addWidget(body)


class AIPlannerView(QWidget):
    """
    The full AI planner screen.

    Owns an AIService instance, a RouteGraphView, a conversation panel,
    and a step-details panel. Saves completed routes to a JournalStore.
    """

    viewActivated = Signal()
    # Internal signals used to marshal AI callbacks from worker thread to UI thread
    _clarifyingReady = Signal(bool, object)
    _routeReady = Signal(bool, object)

    def __init__(self, ai_service: Optional[AIService] = None,
                 journal: Optional[JournalStore] = None,
                 parent: QWidget = None) -> None:
        super().__init__(parent)
        self.ai = ai_service or AIService()
        self.journal = journal or JournalStore()
        self._current_route: Optional[Route] = None
        self._pending_goal: str = ""
        self._clarifying_qa: list[tuple[str, str]] = []
        self._awaiting_clarifying_answers: list[str] = []

        self.setStyleSheet(f"background-color: {Palette.BG_PRIMARY};")

        # Connect internal signals to UI-thread handlers
        self._clarifyingReady.connect(self._on_clarifying_received)
        self._routeReady.connect(self._on_route_received)

        self._build_ui()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # Top: goal input
        layout.addWidget(self._build_goal_bar())

        # Middle: graph + side panel
        splitter = QSplitter(Qt.Horizontal, self)
        splitter.setHandleWidth(2)
        splitter.setStyleSheet(
            f"QSplitter::handle {{ background: {Palette.BG_DEEPEST}; }}"
        )

        # Left: route graph
        self.graph_view = RouteGraphView()
        self.graph_view.stepSelected.connect(self._on_step_selected)
        graph_container = QFrame()
        graph_container.setStyleSheet(f"background-color: {Palette.BG_PRIMARY};")
        graph_layout = QVBoxLayout(graph_container)
        graph_layout.setContentsMargins(0, 0, 0, 0)
        graph_layout.setSpacing(0)
        # Graph header
        header = QLabel("ROUTE GRAPH")
        header.setStyleSheet(
            f"background-color: {Palette.BG_SECONDARY}; color: {Palette.GOLD_PRIMARY}; "
            f"font-size: 11px; font-weight: bold; letter-spacing: 2px; "
            f"padding: 8px 16px; border-bottom: 1px solid {Palette.BORDER_SUBTLE};"
        )
        graph_layout.addWidget(header)
        graph_layout.addWidget(self.graph_view, stretch=1)
        splitter.addWidget(graph_container)

        # Right: side panel
        splitter.addWidget(self._build_side_panel())
        splitter.setStretchFactor(0, 3)
        splitter.setStretchFactor(1, 1)
        splitter.setSizes([1000, 380])

        layout.addWidget(splitter, stretch=1)

        # Bottom: stats bar
        layout.addWidget(self._build_stats_bar())

    def _build_goal_bar(self) -> QWidget:
        bar = QFrame()
        bar.setFixedHeight(80)
        bar.setStyleSheet(
            f"background-color: {Palette.BG_SECONDARY}; "
            f"border-bottom: 1px solid {Palette.BORDER_SUBTLE};"
        )
        layout = QVBoxLayout(bar)
        layout.setContentsMargins(16, 10, 16, 10)
        layout.setSpacing(4)

        # Label
        label = QLabel("DESCRIBE YOUR GOAL — RASK WILL BUILD A WALKABLE ROUTE")
        label.setStyleSheet(
            f"color: {Palette.TEXT_TERTIARY}; font-size: 10px; "
            f"font-weight: bold; letter-spacing: 2px;"
        )
        layout.addWidget(label)

        # Input row
        row = QHBoxLayout()
        row.setSpacing(8)

        self._goal_input = QLineEdit()
        self._goal_input.setPlaceholderText(
            "e.g. 'I want to be home by 9 o'clock, my car is broken'"
        )
        self._goal_input.setStyleSheet(f"""
            QLineEdit {{
                background-color: {Palette.BG_TERTIARY};
                color: {Palette.GOLD_BRIGHT};
                border: 1px solid {Palette.BORDER_GOLD};
                border-radius: 4px;
                padding: 8px 14px;
                font-size: 13px;
            }}
            QLineEdit:focus {{
                border: 1px solid {Palette.GOLD_BRIGHT};
            }}
        """)
        self._goal_input.returnPressed.connect(self._on_plan_clicked)
        row.addWidget(self._goal_input, stretch=1)

        self._plan_btn = QPushButton("✦ Plan with AI")
        self._plan_btn.setProperty("variant", "primary")
        self._plan_btn.setFixedHeight(38)
        self._plan_btn.clicked.connect(self._on_plan_clicked)
        row.addWidget(self._plan_btn)

        layout.addLayout(row)
        return bar

    def _build_side_panel(self) -> QWidget:
        panel = QFrame()
        panel.setMinimumWidth(340)
        panel.setMaximumWidth(500)
        panel.setStyleSheet(f"background-color: {Palette.BG_SECONDARY};")
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # Conversation
        conv_header = QLabel("CONVERSATION")
        conv_header.setStyleSheet(
            f"background-color: {Palette.BG_TERTIARY}; color: {Palette.GOLD_PRIMARY}; "
            f"font-size: 10px; font-weight: bold; letter-spacing: 2px; "
            f"padding: 8px 12px; border-bottom: 1px solid {Palette.BORDER_SUBTLE};"
        )
        layout.addWidget(conv_header)

        self._conversation = QScrollArea()
        self._conversation.setWidgetResizable(True)
        self._conversation.setFrameShape(QFrame.NoFrame)
        self._conversation.setStyleSheet(
            f"QScrollArea {{ background-color: {Palette.BG_SECONDARY}; border: none; }}"
        )
        conv_container = QWidget()
        self._conv_layout = QVBoxLayout(conv_container)
        self._conv_layout.setContentsMargins(10, 10, 10, 10)
        self._conv_layout.setSpacing(6)
        self._conv_layout.addStretch()
        self._conversation.setWidget(conv_container)
        layout.addWidget(self._conversation, stretch=1)

        # Answer input (for clarifying questions)
        self._answer_input = QLineEdit()
        self._answer_input.setPlaceholderText("Type your answer and press Enter…")
        self._answer_input.setStyleSheet(f"""
            QLineEdit {{
                background-color: {Palette.BG_TERTIARY};
                color: {Palette.TEXT_PRIMARY};
                border: 1px solid {Palette.BORDER_NORMAL};
                border-top: 1px solid {Palette.BORDER_SUBTLE};
                border-radius: 0;
                padding: 10px 14px;
                font-size: 12px;
            }}
            QLineEdit:focus {{
                border: 1px solid {Palette.GOLD_PRIMARY};
                border-top: 1px solid {Palette.GOLD_PRIMARY};
            }}
        """)
        self._answer_input.returnPressed.connect(self._on_answer_submitted)
        self._answer_input.hide()
        layout.addWidget(self._answer_input)

        # Step details
        details_header = QLabel("STEP DETAILS")
        details_header.setStyleSheet(
            f"background-color: {Palette.BG_TERTIARY}; color: {Palette.GOLD_PRIMARY}; "
            f"font-size: 10px; font-weight: bold; letter-spacing: 2px; "
            f"padding: 8px 12px; border-top: 1px solid {Palette.BORDER_SUBTLE}; "
            f"border-bottom: 1px solid {Palette.BORDER_SUBTLE};"
        )
        layout.addWidget(details_header)

        self._details = QLabel("Click a step in the graph to see its details.")
        self._details.setWordWrap(True)
        self._details.setAlignment(Qt.AlignTop | Qt.AlignLeft)
        self._details.setStyleSheet(
            f"color: {Palette.TEXT_SECONDARY}; font-size: 12px; padding: 10px 12px; "
            f"background-color: {Palette.BG_SECONDARY};"
        )
        details_scroll = QScrollArea()
        details_scroll.setWidgetResizable(True)
        details_scroll.setFrameShape(QFrame.NoFrame)
        details_scroll.setStyleSheet("QScrollArea { background: transparent; border: none; }")
        details_scroll.setWidget(self._details)
        details_scroll.setFixedHeight(180)
        layout.addWidget(details_scroll)

        # Improvements + follow-up questions
        insights_header = QLabel("INSIGHTS")
        insights_header.setStyleSheet(
            f"background-color: {Palette.BG_TERTIARY}; color: {Palette.GOLD_PRIMARY}; "
            f"font-size: 10px; font-weight: bold; letter-spacing: 2px; "
            f"padding: 8px 12px; border-top: 1px solid {Palette.BORDER_SUBTLE}; "
            f"border-bottom: 1px solid {Palette.BORDER_SUBTLE};"
        )
        layout.addWidget(insights_header)

        self._insights = QLabel("Insights will appear here once a route is generated.")
        self._insights.setWordWrap(True)
        self._insights.setAlignment(Qt.AlignTop | Qt.AlignLeft)
        self._insights.setStyleSheet(
            f"color: {Palette.TEXT_SECONDARY}; font-size: 12px; padding: 10px 12px; "
            f"background-color: {Palette.BG_SECONDARY};"
        )
        insights_scroll = QScrollArea()
        insights_scroll.setWidgetResizable(True)
        insights_scroll.setFrameShape(QFrame.NoFrame)
        insights_scroll.setStyleSheet("QScrollArea { background: transparent; border: none; }")
        insights_scroll.setWidget(self._insights)
        insights_scroll.setFixedHeight(180)
        layout.addWidget(insights_scroll)

        return panel

    def _build_stats_bar(self) -> QWidget:
        bar = QFrame()
        bar.setFixedHeight(48)
        bar.setStyleSheet(
            f"background-color: {Palette.BG_SECONDARY}; "
            f"border-top: 1px solid {Palette.BORDER_SUBTLE};"
        )
        layout = QHBoxLayout(bar)
        layout.setContentsMargins(16, 6, 16, 6)
        layout.setSpacing(20)

        self._stat_goal = self._make_stat("GOAL", "—")
        layout.addWidget(self._stat_goal)
        self._stat_steps = self._make_stat("STEPS", "0")
        layout.addWidget(self._stat_steps)
        self._stat_duration = self._make_stat("TOTAL DURATION", "—")
        layout.addWidget(self._stat_duration)
        self._stat_success = self._make_stat("SUCCESS PROBABILITY", "—")
        layout.addWidget(self._stat_success)
        self._stat_critical = self._make_stat("CRITICAL PATH", "—")
        layout.addWidget(self._stat_critical)

        layout.addStretch()

        self._stat_status = QLabel("")
        self._stat_status.setStyleSheet(
            f"color: {Palette.TEXT_TERTIARY}; font-size: 11px; "
            f"font-family: 'JetBrains Mono', monospace;"
        )
        layout.addWidget(self._stat_status)

        return bar

    def _make_stat(self, label: str, value: str) -> QWidget:
        w = QFrame()
        w.setStyleSheet("QFrame { background: transparent; border: none; }")
        l = QVBoxLayout(w)
        l.setContentsMargins(0, 0, 0, 0)
        l.setSpacing(0)
        lbl = QLabel(label)
        lbl.setStyleSheet(
            f"color: {Palette.TEXT_TERTIARY}; font-size: 9px; "
            f"font-weight: bold; letter-spacing: 1.5px;"
        )
        l.addWidget(lbl)
        val = QLabel(value)
        val.setStyleSheet(
            f"color: {Palette.GOLD_BRIGHT}; font-size: 14px; "
            f"font-weight: bold; font-family: 'JetBrains Mono', monospace;"
        )
        l.addWidget(val)
        w._value_label = val  # type: ignore[attr-defined]
        return w

    def _set_stat(self, widget: QWidget, value: str) -> None:
        if hasattr(widget, "_value_label"):
            widget._value_label.setText(value)  # type: ignore[attr-defined]

    # ---- Conversation helpers ----
    def _add_message(self, text: str, role: str = "assistant") -> None:
        bubble = MessageBubble(text, role)
        # Insert before the stretch
        self._conv_layout.insertWidget(self._conv_layout.count() - 1, bubble)
        # Scroll to bottom
        QTimer.singleShot(50, lambda: self._conversation.verticalScrollBar().setValue(
            self._conversation.verticalScrollBar().maximum()
        ))

    def _set_status(self, text: str) -> None:
        self._stat_status.setText(text)

    # ---- Plan flow ----
    def _on_plan_clicked(self) -> None:
        goal = self._goal_input.text().strip()
        if not goal:
            return
        if not self.ai.is_configured:
            QMessageBox.warning(self, "AI Not Configured",
                                "Please set your z.ai API key in Settings.")
            return

        self._pending_goal = goal
        self._clarifying_qa = []
        self._awaiting_clarifying_answers = []
        self._goal_input.clear()

        self._add_message(f"<b>Your goal:</b> {goal}", role="user")
        self._set_status("⏳ Asking AI to analyse your goal...")
        self._plan_btn.setEnabled(False)

        # The AI callback runs on a worker thread — emit a signal to
        # marshal back to the UI thread (Qt signals are thread-safe).
        self.ai.generate_clarifying_questions(
            goal, lambda success, result: self._clarifyingReady.emit(success, result)
        )

    def _on_clarifying_received(self, success, result) -> None:
        self._plan_btn.setEnabled(True)
        if not success:
            self._set_status("✗ Error")
            self._add_message(f"<b>Error:</b> {result}", role="assistant")
            return

        # result is a dict with is_clear, clarifying_questions, acknowledgment
        is_clear = result.get("is_clear", False)
        questions = result.get("clarifying_questions", [])
        acknowledgment = result.get("acknowledgment", "")

        if acknowledgment:
            self._add_message(acknowledgment)

        if is_clear or not questions:
            self._set_status("⏳ Goal is clear — generating route...")
            self._generate_route()
        else:
            self._awaiting_clarifying_answers = questions
            self._add_message(
                f"I need to ask <b>{len(questions)} clarifying question(s)</b> "
                f"to build a good route:<br><br>"
                + "<br>".join(f"<b>Q{ i+1 }.</b> {q}" for i, q in enumerate(questions))
                + "<br><br>Type your answer below (one per line, or all in one message)."
            )
            self._answer_input.show()
            self._answer_input.setFocus()
            self._answer_input.setPlaceholderText(
                f"Answer Q1 (of {len(questions)})…"
            )
            self._set_status("⏳ Waiting for your answers…")

    def _on_answer_submitted(self) -> None:
        if not self._awaiting_clarifying_answers:
            return
        answer = self._answer_input.text().strip()
        if not answer:
            return
        question = self._awaiting_clarifying_answers.pop(0)
        self._clarifying_qa.append((question, answer))
        self._add_message(f"<b>Q:</b> {question}<br><b>A:</b> {answer}", role="user")
        self._answer_input.clear()

        if self._awaiting_clarifying_answers:
            self._answer_input.setPlaceholderText(
                f"Answer Q{len(self._clarifying_qa) + 1} (of {len(self._clarifying_qa) + len(self._awaiting_clarifying_answers)})…"
            )
        else:
            self._answer_input.hide()
            self._set_status("⏳ Generating route...")
            self._generate_route()

    def _generate_route(self) -> None:
        self.ai.generate_route(
            self._pending_goal, self._clarifying_qa,
            lambda success, result: self._routeReady.emit(success, result)
        )

    def _on_route_received(self, success, result) -> None:
        if not success:
            self._set_status("✗ Error generating route")
            self._add_message(f"<b>Error:</b> {result}", role="assistant")
            return

        self._current_route = result
        self.graph_view.set_route(result)
        self._update_stats(result)
        self._update_insights(result)

        # Add summary message
        msg = (
            f"<b>Route generated!</b><br><br>"
            f"{result.summary}<br><br>"
            f"<b>Overall success probability:</b> {result.overall_success_probability:.0%}<br>"
            f"<b>Total duration:</b> {result.total_duration_minutes} minutes<br>"
            f"<b>Steps:</b> {len(result.steps)}"
        )
        self._add_message(msg)

        # Save to journal
        self.journal.add(
            goal=self._pending_goal,
            clarifying_qa=self._clarifying_qa,
            route=result,
        )
        self._set_status(f"✓ Route saved to journal · {ShamsiDate.today().format('yyyy/mm/dd')}")

    # ---- Public API for loading from journal ----
    def set_route(self, route: Route) -> None:
        """Load a route (e.g. from the journal) into the planner view."""
        self._current_route = route
        self._pending_goal = route.goal
        self._clarifying_qa = []
        self.graph_view.set_route(route)
        self._update_stats(route)
        self._update_insights(route)
        self._add_message(
            f"<b>Loaded route from journal:</b><br>{route.goal}", role="user"
        )
        self._add_message(
            f"<b>Route summary:</b><br>{route.summary}", role="assistant"
        )
        self._set_status("✓ Loaded from journal")

    # ---- Update UI ----
    def _update_stats(self, route: Route) -> None:
        self._set_stat(self._stat_goal, route.goal[:40] + ("…" if len(route.goal) > 40 else ""))
        self._set_stat(self._stat_steps, str(len(route.steps)))
        hours = route.total_duration_minutes // 60
        mins = route.total_duration_minutes % 60
        if hours > 0:
            self._set_stat(self._stat_duration, f"{hours}h {mins}m")
        else:
            self._set_stat(self._stat_duration, f"{mins}m")
        pct = route.overall_success_probability
        color = Palette.GOLD_BRIGHT if pct > 0.7 else (Palette.GOLD_PRIMARY if pct > 0.4 else Palette.STATUS_BLOCKED)
        # Update label color
        self._stat_success._value_label.setStyleSheet(  # type: ignore[attr-defined]
            f"color: {color}; font-size: 14px; font-weight: bold; "
            f"font-family: 'JetBrains Mono', monospace;"
        )
        self._set_stat(self._stat_success, f"{pct:.0%}")

        # Critical path
        critical_path = self.graph_view._compute_critical_path(route)
        if critical_path:
            self._set_stat(self._stat_critical, f"{len(critical_path)} steps")
        else:
            self._set_stat(self._stat_critical, "—")

    def _update_insights(self, route: Route) -> None:
        parts = []
        if route.improvements:
            parts.append("<b>How to improve your chances:</b>")
            for imp in route.improvements:
                parts.append(f"  • {imp}")
        if route.follow_up_questions:
            parts.append("")
            parts.append("<b>Follow-up questions to consider:</b>")
            for q in route.follow_up_questions:
                parts.append(f"  ? {q}")
        if not parts:
            parts.append("No insights generated.")
        self._insights.setText("<br>".join(parts))

    def _on_step_selected(self, step: Optional[RouteStep]) -> None:
        if step is None:
            self._details.setText("Click a step in the graph to see its details.")
            return
        parts = [f"<b>{step.title}</b>"]
        parts.append(f"<b>ID:</b> {step.id}")
        parts.append(f"<b>Duration:</b> {step.duration_minutes} minutes")
        parts.append(f"<b>Success probability:</b> {step.success_probability:.0%}")
        parts.append(f"<b>Risk level:</b> {step.risk_level}")
        if step.location:
            parts.append(f"<b>Location:</b> 📍 {step.location}")
        if step.cost_estimate:
            parts.append(f"<b>Cost:</b> {step.cost_estimate}")
        if step.description:
            parts.append(f"<br><b>What to do:</b><br>{step.description}")
        if step.fallback:
            parts.append(f"<br><b>If this fails:</b><br>{step.fallback}")
        if step.sub_goals:
            parts.append("<br><b>Sub-goals:</b>")
            for sg in step.sub_goals:
                parts.append(f"  • {sg}")
        if step.depends_on:
            parts.append(f"<br><b>Depends on:</b> {', '.join(step.depends_on)}")
        self._details.setText("<br>".join(parts))
