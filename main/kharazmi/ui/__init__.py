"""UI layer exports."""
from .theme import Palette, QSS, build_qpalette, default_font, mono_font
from .icons import get_icon
from .widgets import (
    TaskNodeItem, EdgeItem, InspectorPanel, ConsolePanel,
    CommandPaletteDialog, PaletteItem, MainToolbar, StatusBar, MinimapOverlay,
    TourOverlay, TourStep, Tour,
    ENTERPRISE_TOUR, BASIC_TOUR, start_tour,
    # Calendar widgets
    MiniMonthWidget, CalendarListWidget, EventBlock,
    NaturalLanguageInput,
    # AI widgets
    RouteNodeItem,
)
from .views import (
    NodeGraphView, GanttView, KanbanView, TimelineView, StatisticsView,
    BasicCalendarView,
    # Google-Calendar-style views
    TimeGridView, DayView, WeekView, CustomView,
    MonthView, YearView, ScheduleView,
    GoogleCalendarView,
    # AI views
    RouteGraphView, AIPlannerView, JournalView,
)
from .dialogs import (
    TaskEditorDialog, ProjectSettingsDialog, AdvisorDialog,
    PlanSelectionDialog, PlanCard, load_saved_plan, save_plan,
    # Calendar dialogs
    EventEditorDialog, CalendarSettingsDialog,
    # AI dialogs
    AISettingsDialog,
)
from .main_window import MainWindow
from .basic_window import BasicMainWindow
from .rask_window import RaskMainWindow

__all__ = [
    "Palette", "QSS", "build_qpalette", "default_font", "mono_font",
    "get_icon",
    "TaskNodeItem", "EdgeItem", "InspectorPanel", "ConsolePanel",
    "CommandPaletteDialog", "PaletteItem", "MainToolbar", "StatusBar", "MinimapOverlay",
    "TourOverlay", "TourStep", "Tour",
    "ENTERPRISE_TOUR", "BASIC_TOUR", "start_tour",
    "MiniMonthWidget", "CalendarListWidget", "EventBlock", "NaturalLanguageInput",
    "RouteNodeItem",
    "NodeGraphView", "GanttView", "KanbanView", "TimelineView", "StatisticsView",
    "BasicCalendarView",
    "TimeGridView", "DayView", "WeekView", "CustomView",
    "MonthView", "YearView", "ScheduleView",
    "GoogleCalendarView",
    "RouteGraphView", "AIPlannerView", "JournalView",
    "TaskEditorDialog", "ProjectSettingsDialog", "AdvisorDialog",
    "PlanSelectionDialog", "PlanCard", "load_saved_plan", "save_plan",
    "EventEditorDialog", "CalendarSettingsDialog",
    "AISettingsDialog",
    "MainWindow", "BasicMainWindow", "RaskMainWindow",
]
