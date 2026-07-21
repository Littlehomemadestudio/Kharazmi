"""UI layer exports."""
from .theme import Palette, QSS, build_qpalette, default_font, mono_font
from .icons import get_icon
from .calendar import CalendarView
from .widgets import (
    TaskNodeItem, EdgeItem, InspectorPanel,
    CommandPaletteDialog, PaletteItem, MainToolbar, StatusBar, MinimapOverlay,
    TourOverlay, TourStep, Tour,
    ENTERPRISE_TOUR, BASIC_TOUR, start_tour,
    # AI widgets
    RouteNodeItem, InsightBubble,
    AIChatPanel, ChatMessage, ChatInput,
    MultipleChoiceQuestionWidget, StepDetailsPopup,
)
from .views import (
    NodeGraphView, GanttView, KanbanView, TimelineView, StatisticsView,
    # AI views
    RouteGraphView, UnifiedGraphView, AIPlannerView, JournalView,
    # Analytics
    GraphsView, SimulationView,
)
from .dialogs import (
    TaskEditorDialog, ProjectSettingsDialog, AdvisorDialog,
    PlanSelectionDialog, PlanCard, load_saved_plan, save_plan,
    # Calendar dialogs
    EventEditorDialog, CalendarSettingsDialog,
    # AI dialogs
    AISettingsDialog,
)
from .basic_window import BasicMainWindow
from .rask_window import RaskMainWindow

__all__ = [
    "Palette", "QSS", "build_qpalette", "default_font", "mono_font",
    "get_icon",
    "CalendarView",
    "TaskNodeItem", "EdgeItem", "InspectorPanel",
    "CommandPaletteDialog", "PaletteItem", "MainToolbar", "StatusBar", "MinimapOverlay",
    "TourOverlay", "TourStep", "Tour",
    "ENTERPRISE_TOUR", "BASIC_TOUR", "start_tour",
    "RouteNodeItem", "InsightBubble",
    "AIChatPanel", "ChatMessage", "ChatInput",
    "MultipleChoiceQuestionWidget", "StepDetailsPopup",
    "NodeGraphView", "GanttView", "KanbanView", "TimelineView", "StatisticsView",
    "RouteGraphView", "UnifiedGraphView", "AIPlannerView", "JournalView",
    "GraphsView", "SimulationView",
    "TaskEditorDialog", "ProjectSettingsDialog", "AdvisorDialog",
    "PlanSelectionDialog", "PlanCard", "load_saved_plan", "save_plan",
    "EventEditorDialog", "CalendarSettingsDialog",
    "AISettingsDialog",
    "BasicMainWindow", "RaskMainWindow",
]
