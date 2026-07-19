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
)
from .views import (
    NodeGraphView, GanttView, KanbanView, TimelineView, StatisticsView,
    BasicCalendarView,
    # Google-Calendar-style views
    TimeGridView, DayView, WeekView, CustomView,
    MonthView, YearView, ScheduleView,
    GoogleCalendarView,
)
from .dialogs import (
    TaskEditorDialog, ProjectSettingsDialog, AdvisorDialog,
    PlanSelectionDialog, PlanCard, load_saved_plan, save_plan,
    # Calendar dialogs
    EventEditorDialog, CalendarSettingsDialog,
)
from .main_window import MainWindow
from .basic_window import BasicMainWindow

__all__ = [
    "Palette", "QSS", "build_qpalette", "default_font", "mono_font",
    "get_icon",
    "TaskNodeItem", "EdgeItem", "InspectorPanel", "ConsolePanel",
    "CommandPaletteDialog", "PaletteItem", "MainToolbar", "StatusBar", "MinimapOverlay",
    "TourOverlay", "TourStep", "Tour",
    "ENTERPRISE_TOUR", "BASIC_TOUR", "start_tour",
    "MiniMonthWidget", "CalendarListWidget", "EventBlock", "NaturalLanguageInput",
    "NodeGraphView", "GanttView", "KanbanView", "TimelineView", "StatisticsView",
    "BasicCalendarView",
    "TimeGridView", "DayView", "WeekView", "CustomView",
    "MonthView", "YearView", "ScheduleView",
    "GoogleCalendarView",
    "TaskEditorDialog", "ProjectSettingsDialog", "AdvisorDialog",
    "PlanSelectionDialog", "PlanCard", "load_saved_plan", "save_plan",
    "EventEditorDialog", "CalendarSettingsDialog",
    "MainWindow", "BasicMainWindow",
]
