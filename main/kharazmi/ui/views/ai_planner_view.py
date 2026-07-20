"""
AIPlannerView — the UNIFIED workspace (AI Planner + Tasks merged).

No more separate Tasks window. Everything lives on one canvas:
  - AI-generated route nodes
  - User-created Tasks
  - Insight bubbles
  - Edges (primary, alternative, fallback, merge)

Layout:
  ┌─────────────────────────────────────────────────────────────────────┐
  │ Top: Goal input + stats                                            │
  ├──────────────────────────────────────────────┬─────────────────────┤
  │ Unified Workspace (large)                    │ Professional Chat   │
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
  │  Pan / zoom / drag / edit                   │  streaming reply…  │
  │                                             │                     │
  │  [Floating Step Details popup on click]     │                     │
  └─────────────────────────────────────────────┴─────────────────────┘

TRUE STREAMING: nodes appear one-by-one as the AI generates them.
"""
from __future__ import annotations

import logging
import uuid
from datetime import datetime, timedelta
from typing import Optional

from PySide6.QtCore import Qt, Signal, QTimer, QPropertyAnimation, QEasingCurve
from PySide6.QtGui import QFont, QColor
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, QPushButton,
    QFrame, QSplitter, QScrollArea, QPlainTextEdit, QTextEdit,
    QSizePolicy, QMessageBox, QApplication, QToolButton, QInputDialog,
    QTabWidget, QGraphicsOpacityEffect, QStackedWidget,
)

from ...ai import (
    AIService, Route, RouteStep, RouteEdge, JournalStore, Insight,
    MultipleChoiceQuestion,
    MonteCarloSimulator, SimulationResult,
    RouteHealthEngine, RouteHealthReport,
)
from ...calendar import CalendarStore, Event as CalendarEvent, EventType, Availability
from ...core import Project, Task, TaskId, Duration, DurationUnit, Priority, TaskStatus
from ...core.shamsi import ShamsiDate
from ..theme import Palette

logger = logging.getLogger(__name__)
from ..views.unified_graph_view import UnifiedGraphView
from ..widgets.ai_chat_panel import AIChatPanel
from ..widgets.multiple_choice_question import MultipleChoiceQuestionWidget
from ..widgets.route_health_dashboard import RouteHealthDashboard
from ..widgets.credits_panel import CreditsPanel
from ..widgets.feedback_dialog import FeedbackDialog
from ..widgets.planner_landing import PlannerLanding


class AIPlannerView(QWidget):
    """
    The UNIFIED workspace — AI Planner + Tasks in one place.
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
    _stepAdded = Signal(object)  # RouteStep
    _edgeAdded = Signal(object)  # RouteEdge
    _insightAdded = Signal(object)  # Insight
    _taskCreated = Signal(str, float, float)  # title, x, y
    _optimizeReady = Signal(bool, object)
    _riskAnalysisReady = Signal(bool, object)
    _replanReady = Signal(bool, object)
    _simulationComplete = Signal(object)
    _critiqueReady = Signal(bool, object)

    def __init__(self, ai_service: Optional[AIService] = None,
                 journal: Optional[JournalStore] = None,
                 calendar_store: Optional[CalendarStore] = None,
                 project: Optional[Project] = None,
                 parent: QWidget = None) -> None:
        super().__init__(parent)
        self.ai = ai_service or AIService()
        self.journal = journal or JournalStore()
        self.calendar_store = calendar_store
        self.project = project
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
        self._stepAdded.connect(self._on_step_added)
        self._edgeAdded.connect(self._on_edge_added)
        self._insightAdded.connect(self._on_insight_added)
        self._taskCreated.connect(self._on_task_created)
        self._optimizeReady.connect(self._on_optimize_received)
        self._riskAnalysisReady.connect(self._on_risk_analysis_received)
        self._replanReady.connect(self._on_replan_received)
        self._simulationComplete.connect(self._on_simulation_complete)
        self._critiqueReady.connect(self._on_critique_received)

        self._build_ui()

    def set_calendar_store(self, store: CalendarStore) -> None:
        self.calendar_store = store

    def set_project(self, project: Project) -> None:
        self.project = project
        if self.graph_view is not None:
            self.graph_view.set_project(project)

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # Stacked widget: page 0 = landing, page 1 = workspace
        self._stack = QStackedWidget()

        # ---- Page 0: Landing page ----
        self._landing = PlannerLanding()
        self._landing.goalSubmitted.connect(self._on_landing_goal)
        self._stack.addWidget(self._landing)

        # ---- Page 1: Workspace ----
        workspace = QWidget()
        ws_layout = QVBoxLayout(workspace)
        ws_layout.setContentsMargins(0, 0, 0, 0)
        ws_layout.setSpacing(0)

        # Top: goal input + stats
        ws_layout.addWidget(self._build_goal_bar())

        # Middle: graph + chat
        splitter = QSplitter(Qt.Horizontal, workspace)
        splitter.setHandleWidth(2)
        splitter.setStyleSheet(
            f"QSplitter::handle {{ background: {Palette.BG_DEEPEST}; }}"
        )

        # Left: unified graph
        left_container = QWidget()
        left_layout = QVBoxLayout(left_container)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.setSpacing(0)

        # Graph header
        graph_header = QFrame()
        graph_header.setFixedHeight(36)
        graph_header.setStyleSheet(
            f"background-color: {Palette.BG_SECONDARY}; "
            f"border-bottom: 1px solid {Palette.BORDER_SUBTLE};"
        )
        gh_layout = QHBoxLayout(graph_header)
        gh_layout.setContentsMargins(12, 4, 12, 4)
        gh_layout.setSpacing(8)
        gh_label = QLabel("WORKSPACE — AI ROUTES + TASKS")
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

        self._critique_btn = QToolButton()
        self._critique_btn.setText("🔍  Critique & Improve")
        self._critique_btn.setStyleSheet(f"""
            QToolButton {{
                background-color: #5A4A8A;
                color: #E0D8FF;
                border: none;
                border-radius: 3px;
                padding: 4px 12px;
                font-size: 11px;
                font-weight: bold;
            }}
            QToolButton:hover {{
                background-color: #7A6AAA;
            }}
            QToolButton:disabled {{
                background-color: {Palette.BG_TERTIARY};
                color: {Palette.TEXT_TERTIARY};
            }}
        """)
        self._critique_btn.setEnabled(False)
        self._critique_btn.clicked.connect(self._on_critique_clicked)
        gh_layout.addWidget(self._critique_btn)

        left_layout.addWidget(graph_header)

        # Unified graph view
        self.graph_view = UnifiedGraphView()
        if self.project is not None:
            self.graph_view.set_project(self.project)
        self.graph_view.taskCreated.connect(self._taskCreated.emit)
        self.graph_view.stepBreakdownRequested.connect(self._on_step_breakdown_requested)
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

        splitter.addWidget(left_container)

        # Right: Tabbed panel (Chat + Health)
        self.chat_panel = AIChatPanel(self.ai)

        self.chat_panel.sendRequested.connect(self._on_chat_send)
        self.chat_panel.stopRequested.connect(self._on_chat_stop)

        # Health dashboard
        self._health_dashboard = RouteHealthDashboard()
        self._health_dashboard.optimizeRequested.connect(self._on_optimize_clicked)
        self._health_dashboard.riskAnalysisRequested.connect(self._on_risk_analysis_clicked)
        self._health_dashboard.simulationRequested.connect(self._on_simulation_clicked)
        self._health_dashboard.replanRequested.connect(self._on_replan_clicked)

        # Tab widget
        self._right_tabs = QTabWidget()
        self._right_tabs.setTabPosition(QTabWidget.TabPosition.North)
        # Opacity effect for tab-switch animation
        self._tab_opacity = QGraphicsOpacityEffect(self._right_tabs)
        self._tab_opacity.setOpacity(1.0)
        self._right_tabs.setGraphicsEffect(self._tab_opacity)
        self._right_tabs.currentChanged.connect(self._on_tab_changed)
        self._right_tabs.setStyleSheet(f"""
            QTabWidget::pane {{
                border: none;
                background-color: {Palette.BG_PRIMARY};
            }}
            QTabBar::tab {{
                background-color: {Palette.BG_TERTIARY};
                color: {Palette.TEXT_TERTIARY};
                padding: 8px 16px;
                margin: 0px;
                border: none;
                border-bottom: 2px solid transparent;
                font-weight: bold;
                font-size: 11px;
                letter-spacing: 1px;
            }}
            QTabBar::tab:selected {{
                color: {Palette.GOLD_BRIGHT};
                border-bottom: 2px solid {Palette.GOLD_PRIMARY};
                background-color: {Palette.BG_SECONDARY};
            }}
            QTabBar::tab:hover {{
                color: {Palette.GOLD_PRIMARY};
            }}
        """)
        self._right_tabs.addTab(self.chat_panel, "Chat")
        self._right_tabs.addTab(self._health_dashboard, "Health")
        self._right_tabs.setMinimumWidth(280)

        splitter.addWidget(self._right_tabs)

        splitter.setStretchFactor(0, 7)
        splitter.setStretchFactor(1, 3)
        splitter.setSizes([1100, 460])

        ws_layout.addWidget(splitter, stretch=1)

        self._stack.addWidget(workspace)

        # Start on the landing page
        self._stack.setCurrentIndex(0)
        layout.addWidget(self._stack, stretch=1)

    def _on_landing_goal(self, goal: str) -> None:
        """User submitted a goal from the landing page — switch to workspace and start planning."""
        # Animate landing out
        self._landing.animate_out()
        # Switch to workspace after a short delay for the animation
        QTimer.singleShot(300, lambda: self._switch_to_workspace(goal))

    def _switch_to_workspace(self, goal: str) -> None:
        """Switch from landing page to workspace and trigger plan."""
        self._stack.setCurrentIndex(1)
        # Put the goal into the goal input and trigger planning
        self._goal_input.setText(goal)
        self._on_plan_clicked()

    def show_landing(self) -> None:
        """Switch back to the landing page (e.g. when user wants to start a new plan)."""
        self._stack.setCurrentIndex(0)
        self._landing.animate_in()
        self._landing.focus_input()

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

        # New Plan button — go back to landing
        new_plan_btn = QPushButton("✦ New Plan")
        new_plan_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: transparent;
                color: {Palette.TEXT_TERTIARY};
                border: 1px solid {Palette.BORDER_NORMAL};
                border-radius: 3px;
                padding: 2px 10px;
                font-size: 10px;
                font-weight: bold;
            }}
            QPushButton:hover {{
                color: {Palette.GOLD_BRIGHT};
                border: 1px solid {Palette.BORDER_GOLD};
                background-color: {Palette.BG_TERTIARY};
            }}
        """)
        new_plan_btn.setFixedHeight(22)
        new_plan_btn.clicked.connect(self.show_landing)
        header_row.addWidget(new_plan_btn)

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

        # Feedback button
        self._feedback_btn = QPushButton("💡 Feedback")
        self._feedback_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: transparent;
                color: {Palette.TEXT_TERTIARY};
                border: 1px solid {Palette.BORDER_NORMAL};
                border-radius: 3px;
                padding: 2px 10px;
                font-size: 10px;
                font-weight: bold;
            }}
            QPushButton:hover {{
                color: {Palette.GOLD_BRIGHT};
                border: 1px solid {Palette.BORDER_GOLD};
                background-color: {Palette.BG_TERTIARY};
            }}
        """)
        self._feedback_btn.setFixedHeight(22)
        self._feedback_btn.clicked.connect(self._on_feedback_clicked)
        header_row.addWidget(self._feedback_btn)

        # Credits panel
        self._credits_panel = CreditsPanel()
        header_row.addWidget(self._credits_panel)

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

    # ---- Tab switch animation ----
    def _on_tab_changed(self, index: int) -> None:
        """Fade animation when switching between Chat and Health tabs."""
        anim = QPropertyAnimation(self._tab_opacity, b"opacity")
        anim.setDuration(250)
        anim.setStartValue(0.0)
        anim.setEndValue(1.0)
        anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        anim.start()
        # Keep a reference so it doesn't get GC'd mid-animation
        self._tab_anim = anim

    # ---- Feedback button ----
    def _on_feedback_clicked(self) -> None:
        dlg = FeedbackDialog(self)
        dlg.exec()

    def _build_existing_context(self) -> str:
        """Build a context string describing the user's existing Tasks."""
        if self.project is None:
            return ""
        tasks = list(self.project.tasks())
        if not tasks:
            return ""
        lines = [f"Existing tasks ({len(tasks)}):"]
        for t in tasks:
            lines.append(f"  - id={t.id} title='{t.title}' duration={t.duration.minutes}min")
            deps = self.project.dependencies_of(t.id)
            if deps:
                lines.append(f"    depends_on: {[str(d.predecessor_id) for d in deps]}")
        return "\n".join(lines)

    # ---- Status update ----
    def _on_status_update(self, text: str) -> None:
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

        self.chat_panel.add_message(f"<b>Goal:</b> {goal}", role="user", as_html=True)
        self.chat_panel.start_status_box("Analysing your goal…")
        self._set_status("⏳ Asking AI to analyse your goal…")
        self._plan_btn.setEnabled(False)

        self._current_request_id = f"clar-{uuid.uuid4().hex[:8]}"
        self.chat_panel.set_request_id(self._current_request_id)

        self._credits_panel.increment()
        self.ai.generate_clarifying_questions_streaming(
            goal,
            on_status=lambda s: self._statusUpdate.emit(s),
            callback=lambda success, result: self._clarifyingReady.emit(success, result),
            request_id=self._current_request_id,
        )

    def _on_clarifying_received(self, success, result) -> None:
        self._plan_btn.setEnabled(True)
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
        self.chat_panel.start_status_box("Building the route graph…")
        self._set_status("⏳ AI is building the route…")

        self._current_request_id = f"route-{uuid.uuid4().hex[:8]}"
        self.chat_panel.set_request_id(self._current_request_id)

        # Build existing context (existing tasks)
        existing_context = self._build_existing_context()

        # TRUE STREAMING: pass on_step, on_edge, on_insight callbacks
        # so nodes appear one-by-one as the AI generates them
        self._credits_panel.increment()
        self.ai.generate_route_streaming(
            self._pending_goal, self._clarifying_qa,
            on_status=lambda s: self._statusUpdate.emit(s),
            callback=lambda success, result: self._routeReady.emit(success, result),
            request_id=self._current_request_id,
            on_step=lambda step: self._stepAdded.emit(step),
            on_edge=lambda edge: self._edgeAdded.emit(edge),
            on_insight=lambda insight: self._insightAdded.emit(insight),
            existing_context=existing_context,
        )

    def _on_step_added(self, step: RouteStep) -> None:
        """TRUE STREAMING: a step was parsed from the AI's response.
        Add it to the canvas immediately — don't wait for the full route."""
        self.graph_view.add_step(step)
        self.chat_panel.update_status(f"Added step: {step.title[:50]}…")

    def _on_edge_added(self, edge: RouteEdge) -> None:
        """An edge was parsed — add it immediately."""
        self.graph_view.add_edge(edge)

    def _on_insight_added(self, insight: Insight) -> None:
        """An insight was parsed — add it immediately."""
        self.graph_view.add_insight(insight)

    def _on_route_received(self, success, result) -> None:
        self.chat_panel.finish_status_box("Route generated")

        if not success:
            self._set_status("✗ Error generating route")
            self.chat_panel.add_message(f"<b>Error:</b> {result}", role="assistant", as_html=True)
            return

        self._current_route = result

        # Log edge diagnostics
        step_ids = {s.id for s in result.steps}
        edge_src_ids = {e.source_id for e in result.edges}
        edge_tgt_ids = {e.target_id for e in result.edges}
        all_edge_ids = edge_src_ids | edge_tgt_ids
        unmatched = all_edge_ids - step_ids
        dep_ids = set()
        for s in result.steps:
            dep_ids.update(s.depends_on)
        unmatched_deps = dep_ids - step_ids

        logger.info(
            "Route received: %d steps, %d explicit edges, %d steps with depends_on",
            len(result.steps), len(result.edges),
            sum(1 for s in result.steps if s.depends_on),
        )
        if unmatched:
            logger.warning("Edge IDs not matching any step: %s (step IDs: %s)", unmatched, step_ids)
        if unmatched_deps:
            logger.warning("depends_on IDs not matching any step: %s", unmatched_deps)

        # The graph view has already been adding nodes incrementally
        # via _on_step_added. Now finalize the route to ensure ALL
        # edges are created (from both route.edges AND step.depends_on),
        # and compute the critical path for edge styling.
        self.graph_view.finalize_route(result)
        self._update_stats(result)
        self._schedule_btn.setEnabled(True)
        self._critique_btn.setEnabled(True)

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

        self.journal.add(
            goal=self._pending_goal,
            clarifying_qa=self._clarifying_qa,
            route=result,
        )
        self._set_status("✓ Route saved — AI is continuing to work…")

        # Auto-compute health score
        if self._current_route:
            health = RouteHealthEngine.compute(self._current_route)
            self._health_dashboard.update_health(health)
            self._health_dashboard.set_route(self._current_route)

        QTimer.singleShot(500, self._continue_working)

    # ---- Auto-continue ----
    def _continue_working(self) -> None:
        if self._current_route is None:
            return

        self.chat_panel.start_status_box("Continuing to work — adding alternatives, breakthroughs, more questions…")
        self._set_status("⏳ AI is continuing to work…")

        self._current_request_id = f"cont-{uuid.uuid4().hex[:8]}"
        self.chat_panel.set_request_id(self._current_request_id)

        self._credits_panel.increment()
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

        if new_steps or new_edges or new_insights:
            self.graph_view.add_steps_and_edges(new_steps, new_edges, new_insights)
            if self._current_route is not None:
                self._current_route.steps.extend(new_steps)
                self._current_route.edges.extend(new_edges)
                self._current_route.insights.extend(new_insights)
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
                f"Drag nodes around to reorganize. Double-click a node to open the edit dialog (with Save button).",
                role="assistant", as_html=True,
            )

        self._set_status(f"✓ Done · {len(self._current_route.steps) if self._current_route else 0} steps")

    # ---- Free-form chat ----
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

        streaming_msg = self.chat_panel.start_streaming_message()
        self._current_request_id = f"chat-{uuid.uuid4().hex[:8]}"
        self.chat_panel.set_request_id(self._current_request_id)
        self._set_status("⏳ AI is responding…")

        self._credits_panel.increment()
        self.ai.chat_streaming(
            messages,
            on_status=lambda chunk: self._chatChunk.emit(chunk),
            callback=lambda success, result: self._chatDone.emit(success, result),
            request_id=self._current_request_id,
        )

    def _on_chat_chunk(self, chunk: str) -> None:
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

        now = datetime.now().replace(second=0, microsecond=0)
        now = now + timedelta(minutes=15 - now.minute % 15)

        self.chat_panel.start_status_box("Scheduling route into your calendar…")
        self._set_status("⏳ Scheduling…")

        self._current_request_id = f"sched-{uuid.uuid4().hex[:8]}"
        self.chat_panel.set_request_id(self._current_request_id)

        self._credits_panel.increment()
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

                cal_id = None
                for cal in self.calendar_store.calendars():
                    if cal.name == calendar_name and not cal.is_readonly:
                        cal_id = cal.id
                        break
                if cal_id is None:
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

    # ---- Task creation ----
    def _on_task_created(self, title: str, x: float, y: float) -> None:
        """Handle the 'add task' button — create a new Task in the project."""
        if self.project is None:
            return
        # Prompt for title
        new_title, ok = QInputDialog.getText(self, "New Task", "Task title:", text=title)
        if not ok or not new_title.strip():
            return
        task = self.project.create_task(
            title=new_title.strip(),
            duration=Duration.of(1, DurationUnit.HOUR),
            priority=Priority.MEDIUM,
            x=x, y=y,
        )
        # Add to canvas
        from ...ai import RouteStep as RS
        step = RS(
            id=str(task.id),
            title=task.title,
            duration_minutes=task.duration.minutes,
            success_probability=0.5,
            location="",
            description=task.description,
            fallback="",
            branch="tasks",
            kind="action",
        )
        self.graph_view._add_node(step, x, y, animate=True)
        self.chat_panel.add_message(
            f"Created task <b>{new_title}</b>. Double-click to edit (with Save button), drag to move.",
            role="assistant", as_html=True,
        )

    # ---- AI Step Breakdown ----
    def _on_step_breakdown_requested(self, step_id: str) -> None:
        """Handle the right-click 'AI Break Down' action on a step."""
        if self._current_route is None:
            return
        step = next((s for s in self._current_route.steps if s.id == step_id), None)
        if step is None:
            return
        self.chat_panel.start_status_box(f"Breaking down step: {step.title}…")
        self._set_status(f"⏳ AI breaking down step: {step.title}…")

        self._current_request_id = f"bd-{uuid.uuid4().hex[:8]}"
        self.chat_panel.set_request_id(self._current_request_id)

        def _on_breakdown_done(success, result):
            self.chat_panel.finish_status_box("Breakdown complete")
            if not success:
                self._set_status("✗ Step breakdown failed")
                self.chat_panel.add_message(f"<b>Error:</b> {result}", role="assistant", as_html=True)
                return

            analysis = result.get("analysis", "")
            new_steps = result.get("new_steps", [])
            new_edges = result.get("new_edges", [])
            edges_to_parents = result.get("edges_to_parents", [])

            if analysis:
                self.chat_panel.add_message(f"<b>Step Breakdown:</b> {analysis}", role="assistant", as_html=True)

            if new_steps:
                # Remove the original step from the route and canvas
                self._current_route.steps = [s for s in self._current_route.steps if s.id != step_id]
                self._current_route.edges = [e for e in self._current_route.edges
                                              if e.source_id != step_id and e.target_id != step_id]
                item = self.graph_view._node_items.pop(step_id, None)
                if item is not None:
                    self.graph_view._scene.removeItem(item)

                # Add new sub-steps
                self.graph_view.add_steps_and_edges(new_steps, new_edges + edges_to_parents)
                self._current_route.steps.extend(new_steps)
                self._current_route.edges.extend(new_edges)
                self._current_route.edges.extend(edges_to_parents)

                self.chat_panel.add_message(
                    f"Replaced <b>{step.title}</b> with <b>{len(new_steps)} sub-steps</b>. "
                    f"Drag them around to reorganize.",
                    role="assistant", as_html=True,
                )

            self._set_status("✓ Step broken down")
            # Update health
            if self._current_route:
                health = RouteHealthEngine.compute(self._current_route)
                self._health_dashboard.update_health(health)

        self.ai.breakdown_step_streaming(
            step, self._current_route,
            on_status=lambda s: self._statusUpdate.emit(s),
            callback=_on_breakdown_done,
            request_id=self._current_request_id,
        )

    # ---- Public API ----
    def set_route(self, route: Route) -> None:
        """Load a route from the journal."""
        self._current_route = route
        self._pending_goal = route.goal
        self._clarifying_qa = []
        self.graph_view.set_route(route)
        self._update_stats(route)
        self._schedule_btn.setEnabled(True)
        self._critique_btn.setEnabled(True)
        self._health_dashboard.set_route(route)
        if route and route.steps:
            health = RouteHealthEngine.compute(route)
            self._health_dashboard.update_health(health)
        self.chat_panel.add_message(
            f"<b>Loaded route from journal:</b><br>{route.goal}",
            role="user", as_html=True,
        )
        self.chat_panel.add_message(
            f"<b>Route summary:</b><br>{route.summary}",
            role="assistant", as_html=True,
        )
        self._set_status("✓ Loaded from journal")

    # ---- Monte Carlo Simulation ----
    def _on_simulation_clicked(self) -> None:
        if self._current_route is None or not self._current_route.steps:
            self.chat_panel.add_message("Generate a route first before running simulation.", role="assistant", as_html=True)
            return
        self._set_status("⏳ Running Monte Carlo simulation (5,000 runs)…")
        self.chat_panel.add_message("<b>Running Monte Carlo simulation…</b> Simulating the route 5,000 times to compute realistic time estimates.", role="assistant", as_html=True)

        def _run():
            sim = MonteCarloSimulator(self._current_route, n_simulations=5000)
            result = sim.run()
            return result

        def _on_done(success, result):
            if success:
                self._simulationComplete.emit(result)
            else:
                self._set_status("✗ Simulation failed")

        import threading
        t = threading.Thread(target=lambda: _on_done(True, _run()), daemon=True)
        t.start()

    def _on_simulation_complete(self, result: SimulationResult) -> None:
        self._health_dashboard.update_simulation(result)
        self.chat_panel.add_message(
            f"<b>Simulation complete!</b><br>"
            f"P50: {result.p50_minutes}min · P75: {result.p75_minutes}min · "
            f"P90: {result.p90_minutes}min · P99: {result.p99_minutes}min<br>"
            f"Failure rate: {result.failure_rate:.1%}<br>"
            f"Switch to the <b>Health</b> tab for full details.",
            role="assistant", as_html=True,
        )
        self._set_status(f"✓ Simulation done · P50={result.p50_minutes}m")

        # Also compute and update health
        health = RouteHealthEngine.compute(self._current_route)
        self._health_dashboard.update_health(health)

    # ---- AI Route Optimization ----
    def _on_optimize_clicked(self) -> None:
        if self._current_route is None:
            return
        self.chat_panel.start_status_box("AI is optimizing your route…")
        self._set_status("⏳ AI optimizing route…")

        self._current_request_id = f"opt-{uuid.uuid4().hex[:8]}"
        self.chat_panel.set_request_id(self._current_request_id)

        self._credits_panel.increment()
        self.ai.optimize_route_streaming(
            self._current_route,
            on_status=lambda s: self._statusUpdate.emit(s),
            callback=lambda success, result: self._optimizeReady.emit(success, result),
            request_id=self._current_request_id,
        )

    def _on_optimize_received(self, success, result) -> None:
        self.chat_panel.finish_status_box("Optimization complete")
        if not success:
            self._set_status("✗ Optimization failed")
            self.chat_panel.add_message(f"<b>Error:</b> {result}", role="assistant", as_html=True)
            return

        analysis = result.get("analysis", "")
        optimizations = result.get("optimizations", [])
        new_steps = result.get("new_steps", [])
        new_edges = result.get("new_edges", [])
        new_insights = result.get("new_insights", [])

        if analysis:
            self.chat_panel.add_message(f"<b>Route Optimization Analysis:</b><br>{analysis}", role="assistant", as_html=True)

        if optimizations:
            parts = []
            for opt in optimizations:
                impact = opt.get("impact", "medium")
                icon = "🔴" if impact == "high" else ("🟡" if impact == "medium" else "🟢")
                parts.append(f"{icon} <b>{opt.get('title', '')}</b> ({impact} impact)<br>{opt.get('description', '')}")
            self.chat_panel.add_message("<br><br>".join(parts), role="assistant", as_html=True)

        if new_steps or new_edges or new_insights:
            self.graph_view.add_steps_and_edges(new_steps, new_edges, new_insights)
            if self._current_route is not None:
                self._current_route.steps.extend(new_steps)
                self._current_route.edges.extend(new_edges)
                self._current_route.insights.extend(new_insights)
            self.chat_panel.add_message(f"Added {len(new_steps)} new steps, {len(new_edges)} new edges, {len(new_insights)} new insights to the route.", role="assistant", as_html=True)

        self._set_status("✓ Optimization applied")
        # Update health dashboard
        if self._current_route:
            health = RouteHealthEngine.compute(self._current_route)
            self._health_dashboard.update_health(health)

    # ---- AI Risk Analysis ----
    def _on_risk_analysis_clicked(self) -> None:
        if self._current_route is None:
            return
        self.chat_panel.start_status_box("AI is analyzing risks…")
        self._set_status("⏳ AI analyzing risks…")

        self._current_request_id = f"risk-{uuid.uuid4().hex[:8]}"
        self.chat_panel.set_request_id(self._current_request_id)

        self._credits_panel.increment()
        self.ai.analyze_risks_streaming(
            self._current_route,
            on_status=lambda s: self._statusUpdate.emit(s),
            callback=lambda success, result: self._riskAnalysisReady.emit(success, result),
            request_id=self._current_request_id,
        )

    def _on_risk_analysis_received(self, success, result) -> None:
        self.chat_panel.finish_status_box("Risk analysis complete")
        if not success:
            self._set_status("✗ Risk analysis failed")
            self.chat_panel.add_message(f"<b>Error:</b> {result}", role="assistant", as_html=True)
            return

        overall = result.get("overall_risk_level", "unknown")
        risk_score = result.get("risk_score", 0)
        analysis = result.get("analysis", "")
        risks = result.get("risks", [])
        actions = result.get("recommended_actions", [])

        icon = {"low": "🟢", "medium": "🟡", "high": "🔴", "critical": "⛔"}.get(overall, "⚪")
        msg = f"<b>{icon} Risk Level: {overall.upper()}</b> (score: {risk_score:.2f})<br>{analysis}<br><br>"

        if risks:
            msg += "<b>Identified Risks:</b><br>"
            for risk in risks:
                sev = risk.get("severity", "medium")
                sev_icon = "🔴" if sev in ("critical", "high") else ("🟡" if sev == "medium" else "🟢")
                msg += f"{sev_icon} <b>{risk.get('title', '')}</b> ({sev})<br>{risk.get('description', '')}<br><i>Mitigation: {risk.get('mitigation', '')}</i><br><br>"

        if actions:
            msg += "<b>Recommended Actions:</b><br>"
            for i, action in enumerate(actions, 1):
                msg += f"{i}. {action}<br>"

        self.chat_panel.add_message(msg, role="assistant", as_html=True)
        self._set_status(f"✓ Risk analysis · {overall}")

    # ---- AI Self-Critique & Improve ----
    def _on_critique_clicked(self) -> None:
        if self._current_route is None:
            return
        self.chat_panel.start_status_box("AI is critically reviewing its own plan…")
        self._set_status("⏳ AI critiquing route…")

        self._current_request_id = f"crit-{uuid.uuid4().hex[:8]}"
        self.chat_panel.set_request_id(self._current_request_id)

        self._credits_panel.increment()
        self.ai.critique_and_improve_streaming(
            self._current_route,
            on_status=lambda s: self._statusUpdate.emit(s),
            callback=lambda success, result: self._critiqueReady.emit(success, result),
            request_id=self._current_request_id,
        )

    def _on_critique_received(self, success, result) -> None:
        self.chat_panel.finish_status_box("Critique complete")
        if not success:
            self._set_status("✗ Critique failed")
            self.chat_panel.add_message(f"<b>Error:</b> {result}", role="assistant", as_html=True)
            return

        quality = result.get("quality_score", 0)
        critique = result.get("critique", "")
        weaknesses = result.get("weaknesses", [])
        new_steps = result.get("new_steps", [])
        new_edges = result.get("new_edges", [])
        new_insights = result.get("new_insights", [])

        # Quality score color
        if quality >= 0.8:
            q_icon, q_color = "🟢", "#5A8A5A"
        elif quality >= 0.6:
            q_icon, q_color = "🟡", "#D4AF37"
        elif quality >= 0.4:
            q_icon, q_color = "🟠", "#A87A4A"
        else:
            q_icon, q_color = "🔴", "#A85A5A"

        msg = f"<b>{q_icon} Plan Quality Score: {quality:.0%}</b><br>{critique}<br><br>"

        if weaknesses:
            msg += "<b>Identified Weaknesses:</b><br>"
            for w in weaknesses:
                sev = w.get("severity", "medium")
                sev_icon = "🔴" if sev in ("critical", "high") else ("🟡" if sev == "medium" else "🟢")
                msg += f"{sev_icon} <b>{w.get('kind', '').replace('_', ' ').title()}</b> ({sev})<br>"
                msg += f"{w.get('description', '')}<br>"
                msg += f"<i>💡 {w.get('suggestion', '')}</i><br><br>"

        self.chat_panel.add_message(msg, role="assistant", as_html=True)

        if new_steps or new_edges or new_insights:
            self.graph_view.add_steps_and_edges(new_steps, new_edges, new_insights)
            if self._current_route is not None:
                self._current_route.steps.extend(new_steps)
                self._current_route.edges.extend(new_edges)
                self._current_route.insights.extend(new_insights)
                self._update_stats(self._current_route)
            parts = []
            if new_steps:
                parts.append(f"<b>{len(new_steps)} improvement steps</b>")
            if new_edges:
                parts.append(f"<b>{len(new_edges)} new edges</b>")
            if new_insights:
                parts.append(f"<b>{len(new_insights)} new insights</b>")
            self.chat_panel.add_message(
                f"Applied improvements: {' , '.join(parts)} to address the weaknesses.",
                role="assistant", as_html=True,
            )

        self._set_status(f"✓ Critique done · Quality {quality:.0%}")
        # Update health
        if self._current_route:
            health = RouteHealthEngine.compute(self._current_route)
            self._health_dashboard.update_health(health)

    # ---- Smart Re-plan ----
    def _on_replan_clicked(self) -> None:
        if self._current_route is None:
            return
        # Ask user what changed
        change_desc, ok = QInputDialog.getText(self, "Smart Re-plan", "What did you change? Describe the modification:")
        if not ok or not change_desc.strip():
            return

        self.chat_panel.start_status_box("AI is adjusting the route…")
        self._set_status("⏳ AI re-planning…")

        self._current_request_id = f"replan-{uuid.uuid4().hex[:8]}"
        self.chat_panel.set_request_id(self._current_request_id)

        self._credits_panel.increment()
        self.ai.smart_replan_streaming(
            self._current_route, "", change_desc.strip(),
            on_status=lambda s: self._statusUpdate.emit(s),
            callback=lambda success, result: self._replanReady.emit(success, result),
            request_id=self._current_request_id,
        )

    def _on_replan_received(self, success, result) -> None:
        self.chat_panel.finish_status_box("Re-plan complete")
        if not success:
            self._set_status("✗ Re-plan failed")
            self.chat_panel.add_message(f"<b>Error:</b> {result}", role="assistant", as_html=True)
            return

        analysis = result.get("analysis", "")
        adjustments = result.get("step_adjustments", [])
        new_steps = result.get("new_steps", [])
        new_edges = result.get("new_edges", [])
        new_insights = result.get("new_insights", [])

        if analysis:
            self.chat_panel.add_message(f"<b>Re-plan Analysis:</b><br>{analysis}", role="assistant", as_html=True)

        if adjustments:
            msg = "<b>Suggested Adjustments:</b><br>"
            for adj in adjustments:
                msg += f"• Step <b>{adj.get('step_id', '')}</b>: change <b>{adj.get('field', '')}</b> → {adj.get('new_value', '')}<br><i>{adj.get('reason', '')}</i><br>"
            self.chat_panel.add_message(msg, role="assistant", as_html=True)

        if new_steps or new_edges or new_insights:
            self.graph_view.add_steps_and_edges(new_steps, new_edges, new_insights)
            if self._current_route is not None:
                self._current_route.steps.extend(new_steps)
                self._current_route.edges.extend(new_edges)
                self._current_route.insights.extend(new_insights)
            self.chat_panel.add_message(f"Added {len(new_steps)} new steps and {len(new_edges)} new edges.", role="assistant", as_html=True)

        self._set_status("✓ Re-plan applied")
