"""
AIPlannerView — the unified AI Planner + Tasks workspace.

Layout:
  ┌─────────────────────────────────────────────────────────────────────┐
  │ Top: Goal input + stats                                            │
  ├──────────────────────────────────────────────┬─────────────────────┤
  │ Route Workspace (large)                     │ Professional Chat   │
  │  ┌─────────┐   ┌─────────┐                  │  ✦ Rask             │
  │  │  Node   │──▶│  Node   │                  │  Building route…    │
  │  │         │   │         │                  │  (status box)       │
  │  └─────────┘   └─────────┘                  │                     │
  │       │                                     │  ✦ Rask             │
  │       ▼                                     │  Route generated!   │
  │  ┌─────────┐                                │                     │
  │  │  Node   │  [Insight bubbles]             │  ○ You              │
  │  │         │                                │  How to speed up?   │
  │  └─────────┘                                │                     │
  │                                             │  ✦ Rask             │
  │  Pan / zoom / drag                          │  streaming reply…  │
  ├─────────────────────────────────────────────┴─────────────────────┤
  │ Collapsible Step Details (expands on node click)                  │
  │ [Schedule in Calendar] button                                      │
  └────────────────────────────────────────────────────────────────────┘
"""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta
from typing import Optional

from PySide6.QtCore import Qt, Signal, QTimer
from PySide6.QtGui import QFont, QColor
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, QPushButton,
    QFrame, QSplitter, QScrollArea, QPlainTextEdit, QTextEdit,
    QSizePolicy, QMessageBox, QApplication, QToolButton,
)

from ...ai import (
    AIService, Route, RouteStep, RouteEdge, JournalStore, Insight,
    MultipleChoiceQuestion,
)
from ...calendar import CalendarStore, Event as CalendarEvent, EventType, Availability
from ...core.shamsi import ShamsiDate
from ..theme import Palette
from ..views.route_graph_view import RouteGraphView
from ..widgets.ai_chat_panel import AIChatPanel
from ..widgets.multiple_choice_question import MultipleChoiceQuestionWidget
from ..widgets.step_details_panel import StepDetailsPanel


class AIPlannerView(QWidget):
    """
    The unified AI Planner workspace.
    """

    viewActivated = Signal()
    # Internal signals for thread-safe UI updates
    _clarifyingReady = Signal(bool, object)
    _routeReady = Signal(bool, object)
    _continueReady = Signal(bool, object)
    _chatChunk = Signal(str)
    _chatDone = Signal(bool, object)
    _statusUpdate = Signal(str)
    _scheduleReady = Signal(bool, object)

    def __init__(self, ai_service: Optional[AIService] = None,
                 journal: Optional[JournalStore] = None,
                 calendar_store: Optional[CalendarStore] = None,
                 parent: QWidget = None) -> None:
        super().__init__(parent)
        self.ai = ai_service or AIService()
        self.journal = journal or JournalStore()
        self.calendar_store = calendar_store
        self._current_route: Optional[Route] = None
        self._pending_goal: str = ""
        self._clarifying_qa: list[tuple[str, str]] = []
        self._awaiting_questions: list[MultipleChoiceQuestion] = []
        self._current_request_id: Optional[str] = None

        self.setStyleSheet(f"background-color: {Palette.BG_PRIMARY};")

        # Connect internal signals
        self._statusUpdate.connect(self._on_status_update)
        self._clarifyingReady.connect(self._on_clarifying_received)
        self._routeReady.connect(self._on_route_received)
        self._continueReady.connect(self._on_continue_received)
        self._chatChunk.connect(self._on_chat_chunk)
        self._chatDone.connect(self._on_chat_done)
        self._scheduleReady.connect(self._on_schedule_received)

        self._build_ui()

    def set_calendar_store(self, store: CalendarStore) -> None:
        self.calendar_store = store

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # Top: goal input + stats
        layout.addWidget(self._build_goal_bar())

        # Middle: graph + chat
        splitter = QSplitter(Qt.Horizontal, self)
        splitter.setHandleWidth(2)
        splitter.setStyleSheet(
            f"QSplitter::handle {{ background: {Palette.BG_DEEPEST}; }}"
        )

        # Left: route graph + collapsible step details
        left_container = QWidget()
        left_layout = QVBoxLayout(left_container)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.setSpacing(0)

        # Graph header with action buttons
        graph_header = QFrame()
        graph_header.setFixedHeight(36)
        graph_header.setStyleSheet(
            f"background-color: {Palette.BG_SECONDARY}; "
            f"border-bottom: 1px solid {Palette.BORDER_SUBTLE};"
        )
        gh_layout = QHBoxLayout(graph_header)
        gh_layout.setContentsMargins(12, 4, 12, 4)
        gh_layout.setSpacing(8)
        gh_label = QLabel("ROUTE WORKSPACE")
        gh_label.setStyleSheet(
            f"color: {Palette.GOLD_PRIMARY}; font-size: 11px; "
            f"font-weight: bold; letter-spacing: 2px;"
        )
        gh_layout.addWidget(gh_label)
        gh_layout.addStretch()

        # Schedule in calendar button
        self._schedule_btn = QToolButton()
        self._schedule_btn.setText("📅  Schedule in Calendar")
        self._schedule_btn.setStyleSheet(f"""
            QToolButton {{
                background-color: {Palette.GOLD_PRIMARY};
                color: {Palette.TEXT_ON_GOLD};
                border: none;
                border-radius: 3px;
                padding: 4px 12px;
                font-size: 11px;
                font-weight: bold;
            }}
            QToolButton:hover {{
                background-color: {Palette.GOLD_BRIGHT};
            }}
            QToolButton:disabled {{
                background-color: {Palette.BG_TERTIARY};
                color: {Palette.TEXT_TERTIARY};
            }}
        """)
        self._schedule_btn.setEnabled(False)
        self._schedule_btn.clicked.connect(self._on_schedule_in_calendar)
        gh_layout.addWidget(self._schedule_btn)

        left_layout.addWidget(graph_header)

        # Route graph view
        self.graph_view = RouteGraphView()
        self.graph_view.stepSelected.connect(self._on_step_selected)
        self.graph_view.insightSelected.connect(self._on_insight_selected)
        left_layout.addWidget(self.graph_view, stretch=1)

        # Multiple-choice questions container
        self._questions_container = QFrame()
        self._questions_container.setStyleSheet(f"""
            QFrame {{
                background-color: {Palette.BG_TERTIARY};
                border-top: 2px solid {Palette.GOLD_PRIMARY};
            }}
        """)
        self._questions_layout = QVBoxLayout(self._questions_container)
        self._questions_layout.setContentsMargins(12, 8, 12, 8)
        self._questions_layout.setSpacing(6)
        q_header = QLabel("RASK NEEDS CLARIFICATION — answer the questions below")
        q_header.setStyleSheet(
            f"color: {Palette.GOLD_BRIGHT}; font-size: 11px; "
            f"font-weight: bold; letter-spacing: 1.5px;"
        )
        self._questions_layout.addWidget(q_header)
        self._questions_list = QVBoxLayout()
        self._questions_list.setSpacing(6)
        self._questions_layout.addLayout(self._questions_list)
        self._questions_container.hide()
        left_layout.addWidget(self._questions_container)

        # Collapsible step details panel
        self.step_details = StepDetailsPanel()
        left_layout.addWidget(self.step_details)

        splitter.addWidget(left_container)

        # Right: Professional AI chat
        self.chat_panel = AIChatPanel(self.ai)
        self.chat_panel.setMinimumWidth(360)
        self.chat_panel.setMaximumWidth(520)
        self.chat_panel.sendRequested.connect(self._on_chat_send)
        self.chat_panel.stopRequested.connect(self._on_chat_stop)
        splitter.addWidget(self.chat_panel)

        splitter.setStretchFactor(0, 3)
        splitter.setStretchFactor(1, 1)
        splitter.setSizes([1100, 460])

        layout.addWidget(splitter, stretch=1)

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

        header_row = QHBoxLayout()
        label = QLabel("DESCRIBE YOUR GOAL — RASK WILL BUILD A WALKABLE ROUTE")
        label.setStyleSheet(
            f"color: {Palette.TEXT_TERTIARY}; font-size: 10px; "
            f"font-weight: bold; letter-spacing: 2px;"
        )
        header_row.addWidget(label)
        header_row.addStretch()

        self._stat_steps = QLabel("○ steps: 0")
        self._stat_steps.setStyleSheet(
            f"color: {Palette.TEXT_TERTIARY}; font-size: 11px; "
            f"font-family: 'JetBrains Mono', monospace;"
        )
        header_row.addWidget(self._stat_steps)
        self._stat_duration = QLabel("⏱ —")
        self._stat_duration.setStyleSheet(
            f"color: {Palette.TEXT_TERTIARY}; font-size: 11px; "
            f"font-family: 'JetBrains Mono', monospace;"
        )
        header_row.addWidget(self._stat_duration)
        self._stat_success = QLabel("✓ —")
        self._stat_success.setStyleSheet(
            f"color: {Palette.TEXT_TERTIARY}; font-size: 11px; "
            f"font-family: 'JetBrains Mono', monospace; padding-left: 12px;"
        )
        header_row.addWidget(self._stat_success)
        self._stat_status = QLabel("")
        self._stat_status.setStyleSheet(
            f"color: {Palette.GOLD_PRIMARY}; font-size: 11px; "
            f"font-family: 'JetBrains Mono', monospace; padding-left: 12px;"
        )
        header_row.addWidget(self._stat_status)
        layout.addLayout(header_row)

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

    # ---- Helpers ----
    def _set_status(self, text: str) -> None:
        self._stat_status.setText(text)

    def _update_stats(self, route: Route) -> None:
        self._stat_steps.setText(f"○ steps: {len(route.steps)}")
        hours = route.total_duration_minutes // 60
        mins = route.total_duration_minutes % 60
        if hours > 0:
            self._stat_duration.setText(f"⏱ {hours}h {mins}m")
        else:
            self._stat_duration.setText(f"⏱ {mins}m")
        pct = route.overall_success_probability
        color = Palette.GOLD_BRIGHT if pct > 0.7 else (Palette.GOLD_PRIMARY if pct > 0.4 else Palette.STATUS_BLOCKED)
        self._stat_success.setText(f"✓ {pct:.0%}")
        self._stat_success.setStyleSheet(
            f"color: {color}; font-size: 11px; "
            f"font-family: 'JetBrains Mono', monospace; padding-left: 12px;"
        )

    # ---- Status update from worker thread ----
    def _on_status_update(self, text: str) -> None:
        """Receive a status update from the worker thread (via signal)."""
        self.chat_panel.update_status(text)

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
        self._awaiting_questions = []
        self._goal_input.clear()

        # Add user message to chat
        self.chat_panel.add_message(f"<b>Goal:</b> {goal}", role="user", as_html=True)

        # Start status box (NOT streaming JSON — just meaningful status)
        self.chat_panel.start_status_box("Analysing your goal…")
        self._set_status("⏳ Asking AI to analyse your goal…")
        self._plan_btn.setEnabled(False)

        self._current_request_id = f"clar-{uuid.uuid4().hex[:8]}"
        self.chat_panel.set_request_id(self._current_request_id)

        self.ai.generate_clarifying_questions_streaming(
            goal,
            on_status=lambda s: self._statusUpdate.emit(s),
            callback=lambda success, result: self._clarifyingReady.emit(success, result),
            request_id=self._current_request_id,
        )

    def _on_clarifying_received(self, success, result) -> None:
        self._plan_btn.setEnabled(True)
        # Finish the status box
        self.chat_panel.finish_status_box("Analysis complete")

        if not success:
            self._set_status("✗ Error")
            self.chat_panel.add_message(f"<b>Error:</b> {result}", role="assistant", as_html=True)
            return

        is_clear = result.get("is_clear", False)
        questions = result.get("questions", [])
        acknowledgment = result.get("acknowledgment", "")

        if acknowledgment:
            self.chat_panel.add_message(acknowledgment, role="assistant")

        if is_clear or not questions:
            self._set_status("⏳ Goal is clear — generating route…")
            self._generate_route()
        else:
            self._awaiting_questions = questions
            self._show_multiple_choice_questions(questions)
            self._set_status(f"⏳ Waiting for {len(questions)} answers…")
            self.chat_panel.add_message(
                f"I need to ask <b>{len(questions)} clarifying question(s)</b> "
                f"to build a good route. Answer them in the panel below the graph.",
                role="assistant", as_html=True,
            )

    def _show_multiple_choice_questions(self, questions: list[MultipleChoiceQuestion]) -> None:
        while self._questions_list.count():
            item = self._questions_list.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        for i, q in enumerate(questions):
            qw = MultipleChoiceQuestionWidget(q, i)
            qw.answered.connect(lambda answer, question=q: self._on_question_answered(question, answer))
            self._questions_list.addWidget(qw)
        self._questions_container.show()

    def _on_question_answered(self, question: MultipleChoiceQuestion, answer: str) -> None:
        self._clarifying_qa.append((question.question, answer))
        self.chat_panel.add_message(
            f"<b>Q:</b> {question.question}<br><b>A:</b> {answer}",
            role="user", as_html=True,
        )
        # Remove the answered question widget
        for i in range(self._questions_list.count()):
            item = self._questions_list.itemAt(i)
            widget = item.widget() if item else None
            if widget is not None and isinstance(widget, MultipleChoiceQuestionWidget):
                if widget.question is question:
                    self._questions_list.removeWidget(widget)
                    widget.deleteLater()
                    break
        if question in self._awaiting_questions:
            self._awaiting_questions.remove(question)
        if not self._awaiting_questions:
            self._questions_container.hide()
            self._set_status("⏳ Generating route…")
            self._generate_route()
        else:
            self._set_status(f"⏳ Waiting for {len(self._awaiting_questions)} more answer(s)…")

    def _generate_route(self) -> None:
        # Start status box (NO raw JSON — just meaningful status)
        self.chat_panel.start_status_box("Building the route graph…")
        self._set_status("⏳ AI is building the route…")

        self._current_request_id = f"route-{uuid.uuid4().hex[:8]}"
        self.chat_panel.set_request_id(self._current_request_id)

        self.ai.generate_route_streaming(
            self._pending_goal, self._clarifying_qa,
            on_status=lambda s: self._statusUpdate.emit(s),
            callback=lambda success, result: self._routeReady.emit(success, result),
            request_id=self._current_request_id,
        )

    def _on_route_received(self, success, result) -> None:
        # Finish the status box
        self.chat_panel.finish_status_box("Route generated")

        if not success:
            self._set_status("✗ Error generating route")
            self.chat_panel.add_message(f"<b>Error:</b> {result}", role="assistant", as_html=True)
            return

        self._current_route = result
        self.graph_view.set_route(result)
        self._update_stats(result)
        self._schedule_btn.setEnabled(True)

        # Clean summary message (no JSON)
        msg = (
            f"<b>Route generated!</b><br><br>"
            f"{result.summary}<br><br>"
            f"<b>Steps:</b> {len(result.steps)}<br>"
            f"<b>Edges:</b> {len(result.edges)}<br>"
            f"<b>Insights:</b> {len(result.insights)}<br>"
            f"<b>Overall success:</b> {result.overall_success_probability:.0%}<br>"
            f"<b>Total duration:</b> {result.total_duration_minutes} min"
        )
        self.chat_panel.add_message(msg, role="assistant", as_html=True)

        # Save to journal
        self.journal.add(
            goal=self._pending_goal,
            clarifying_qa=self._clarifying_qa,
            route=result,
        )
        self._set_status("✓ Route saved — AI is continuing to work…")

        # Auto-continue
        QTimer.singleShot(500, self._continue_working)

    # ---- Auto-continue after route generation ----
    def _continue_working(self) -> None:
        if self._current_route is None:
            return

        self.chat_panel.start_status_box("Continuing to work — adding alternatives, breakthroughs, more questions…")
        self._set_status("⏳ AI is continuing to work…")

        self._current_request_id = f"cont-{uuid.uuid4().hex[:8]}"
        self.chat_panel.set_request_id(self._current_request_id)

        self.ai.continue_working_streaming(
            self._current_route,
            on_status=lambda s: self._statusUpdate.emit(s),
            callback=lambda success, result: self._continueReady.emit(success, result),
            request_id=self._current_request_id,
        )

    def _on_continue_received(self, success, result) -> None:
        self.chat_panel.finish_status_box("Done")
        if not success:
            self._set_status("✗ Continue-working failed")
            return

        reflection = result.get("reflection", "")
        new_steps = result.get("new_steps", [])
        new_edges = result.get("new_edges", [])
        new_insights = result.get("new_insights", [])

        if reflection:
            self.chat_panel.add_message(
                f"<b>Continuing my analysis…</b><br>{reflection}",
                role="assistant", as_html=True,
            )

        # Add new steps/edges/insights to the graph
        if new_steps or new_edges or new_insights:
            self.graph_view.add_steps_and_edges(new_steps, new_edges, new_insights)
            self._update_stats(self._current_route)
            parts = []
            if new_steps:
                parts.append(f"<b>{len(new_steps)} new steps</b>")
            if new_edges:
                parts.append(f"<b>{len(new_edges)} new edges</b>")
            if new_insights:
                parts.append(f"<b>{len(new_insights)} new insights</b>")
            self.chat_panel.add_message(
                f"Added {' , '.join(parts)} to the route graph. "
                f"Drag nodes around to reorganize.",
                role="assistant", as_html=True,
            )

        self._set_status(f"✓ Done · {len(self._current_route.steps)} steps · {len(self._current_route.insights)} insights")

    # ---- Free-form chat (streaming REAL text) ----
    def _on_chat_send(self, text: str) -> None:
        if self._current_route is None:
            self.chat_panel.add_message(
                "Generate a route first — describe your goal in the top input.",
                role="assistant", as_html=True,
            )
            return

        route = self._current_route
        context = (
            f"You are discussing this route with the user.\n\n"
            f"Goal: {route.goal}\n"
            f"Summary: {route.summary}\n"
            f"Steps ({len(route.steps)}):\n"
        )
        for s in route.steps:
            context += f"  [{s.id}] {s.title} — {s.duration_minutes}m, {s.success_probability:.0%} success\n"
        context += f"\nOverall success: {route.overall_success_probability:.0%}\n"
        context += f"Total duration: {route.total_duration_minutes} min\n"

        messages = [
            {"role": "assistant", "content": context},
            {"role": "user", "content": text},
        ]

        # For chat, we stream REAL text (not JSON)
        streaming_msg = self.chat_panel.start_streaming_message()
        self._current_request_id = f"chat-{uuid.uuid4().hex[:8]}"
        self.chat_panel.set_request_id(self._current_request_id)
        self._set_status("⏳ AI is responding…")

        self.ai.chat_streaming(
            messages,
            on_status=lambda chunk: self._chatChunk.emit(chunk),
            callback=lambda success, result: self._chatDone.emit(success, result),
            request_id=self._current_request_id,
        )

    def _on_chat_chunk(self, chunk: str) -> None:
        """Receive a chunk of REAL text from the chat (not JSON)."""
        self.chat_panel.stream_chunk(chunk)

    def _on_chat_done(self, success, result) -> None:
        self.chat_panel.finish_streaming()
        if not success:
            self.chat_panel.add_message(f"<b>Error:</b> {result}", role="assistant", as_html=True)
            self._set_status("✗ Chat error")
        else:
            self._set_status("✓ Ready")

    def _on_chat_stop(self) -> None:
        if self._current_request_id:
            self.ai.cancel_request(self._current_request_id)
        self.chat_panel.finish_streaming()
        self.chat_panel.finish_status_box()
        self._set_status("■ Stopped")

    # ---- Schedule in calendar ----
    def _on_schedule_in_calendar(self) -> None:
        if self._current_route is None or self.calendar_store is None:
            return

        # Start with route's start time = now rounded up to next 15 min
        now = datetime.now().replace(second=0, microsecond=0)
        now = now + timedelta(minutes=15 - now.minute % 15)

        self.chat_panel.start_status_box("Scheduling route into your calendar…")
        self._set_status("⏳ Scheduling…")

        self._current_request_id = f"sched-{uuid.uuid4().hex[:8]}"
        self.chat_panel.set_request_id(self._current_request_id)

        self.ai.schedule_in_calendar_streaming(
            self._current_route,
            now.isoformat(),
            on_status=lambda s: self._statusUpdate.emit(s),
            callback=lambda success, result: self._scheduleReady.emit(success, result),
            request_id=self._current_request_id,
        )

    def _on_schedule_received(self, success, result) -> None:
        self.chat_panel.finish_status_box("Scheduled")
        if not success:
            self._set_status("✗ Scheduling failed")
            self.chat_panel.add_message(f"<b>Error:</b> {result}", role="assistant", as_html=True)
            return

        events_data = result.get("events", [])
        summary = result.get("summary", "")

        # Create calendar events
        count = 0
        for ev_data in events_data:
            try:
                title = ev_data.get("title", "Untitled")
                start_str = ev_data.get("start", "")
                end_str = ev_data.get("end", "")
                start = datetime.fromisoformat(start_str) if start_str else datetime.now()
                end = datetime.fromisoformat(end_str) if end_str else start + timedelta(hours=1)
                location = ev_data.get("location", "")
                description = ev_data.get("description", "")
                calendar_name = ev_data.get("calendar_name", "Personal")

                # Find or use a calendar
                cal_id = None
                for cal in self.calendar_store.calendars():
                    if cal.name == calendar_name and not cal.is_readonly:
                        cal_id = cal.id
                        break
                if cal_id is None:
                    # Use first writable calendar
                    for cal in self.calendar_store.calendars():
                        if not cal.is_readonly:
                            cal_id = cal.id
                            break
                if cal_id is None:
                    continue

                evt = CalendarEvent.create(
                    calendar_id=cal_id,
                    title=title,
                    start=start,
                    end=end,
                    description=description,
                    location=location,
                    event_type=EventType.TASK,
                    availability=Availability.BUSY,
                )
                self.calendar_store.add_event(evt)
                count += 1
            except Exception:
                continue

        self.chat_panel.add_message(
            f"<b>Scheduled!</b> Created {count} calendar events from the route. "
            f"Switch to the Calendar tab to see them. {summary}",
            role="assistant", as_html=True,
        )
        self._set_status(f"✓ Scheduled {count} events")

    # ---- Selection handlers ----
    def _on_step_selected(self, step: Optional[RouteStep]) -> None:
        if step is None:
            self.step_details.collapse()
        else:
            self.step_details.show_step(step)

    def _on_insight_selected(self, insight: Optional[Insight]) -> None:
        pass

    # ---- Public API ----
    def set_route(self, route: Route) -> None:
        """Load a route from the journal."""
        self._current_route = route
        self._pending_goal = route.goal
        self._clarifying_qa = []
        self.graph_view.set_route(route)
        self._update_stats(route)
        self._schedule_btn.setEnabled(True)
        self.chat_panel.add_message(
            f"<b>Loaded route from journal:</b><br>{route.goal}",
            role="user", as_html=True,
        )
        self.chat_panel.add_message(
            f"<b>Route summary:</b><br>{route.summary}",
            role="assistant", as_html=True,
        )
        self._set_status("✓ Loaded from journal")
