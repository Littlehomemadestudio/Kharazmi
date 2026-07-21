"""Widgets layer exports."""
from .task_node_item import TaskNodeItem, NODE_WIDTH, NODE_HEIGHT
from .edge_item import EdgeItem
from .inspector_panel import InspectorPanel
from .command_palette import CommandPaletteDialog, PaletteItem
from .toolbar import MainToolbar
from .status_bar import StatusBar
from .minimap import MinimapOverlay
from .tour_overlay import (
    TourOverlay, TourStep, Tour,
    RASK_TOUR, ENTERPRISE_TOUR, BASIC_TOUR, start_tour,
)
# AI widgets
from .route_node_item import RouteNodeItem
from .insight_bubble import InsightBubble
from .ai_chat_panel import AIChatPanel, ChatMessage, ChatInput
from .multiple_choice_question import MultipleChoiceQuestionWidget
from .step_details_popup import StepDetailsPopup
from .route_health_dashboard import RouteHealthDashboard
from .planner_landing import PlannerLanding
from .route_annotation import BreakthroughFlash, SkipWhirl, LoopCurl
from .particle_background import GoldParticleBackground
from .glass_title_bar import GlassTitleBar, FramelessWindowMixin
from .splash_screen import RaskSplashScreen
from .schedule_questions import ScheduleQuestionsWidget
from .calendar_ai_panel import CalendarAIPanel

__all__ = [
    "TaskNodeItem", "NODE_WIDTH", "NODE_HEIGHT", "EdgeItem",
    "InspectorPanel",
    "CommandPaletteDialog", "PaletteItem",
    "MainToolbar", "StatusBar", "MinimapOverlay",
    "TourOverlay", "TourStep", "Tour",
    "RASK_TOUR", "ENTERPRISE_TOUR", "BASIC_TOUR", "start_tour",
    # AI
    "RouteNodeItem",
    "InsightBubble",
    "AIChatPanel", "ChatMessage", "ChatInput",
    "MultipleChoiceQuestionWidget",
    "StepDetailsPopup",
    "RouteHealthDashboard",
    "PlannerLanding",
    "BreakthroughFlash", "SkipWhirl", "LoopCurl",
    # Premium UI
    "GoldParticleBackground",
    "GlassTitleBar", "FramelessWindowMixin",
    "RaskSplashScreen",
    "ScheduleQuestionsWidget",
    "CalendarAIPanel",
]
