"""
RASK! Calendar Module — Production-Quality Calendar Rebuild.

Architecture (MVC + Specialist Managers):

  CalendarModel        → data queries, filtering, date-range calculations
  CalendarController   → navigation, CRUD, drag-drop, commands
  CalendarView         → main container (toolbar + sidebar + sub-views)

  MonthView            → infinite-scroll month grid
  WeekView             → 7-day time grid with 24h timeline
  DayView              → single-day detailed timeline
  YearView             → 12-month overview

  TimelineWidget       → 24h time ruler with current-time indicator
  EventWidget          → interactive event card (drag, resize, hover)
  EventRenderer        → QPainter-based event rendering

  CalendarTheme        → visual constants (colors, fonts, metrics)
  AnimationManager     → fade, slide, scale, ripple transitions
  SelectionManager     → keyboard navigation, multi-select, focus

All dates are Persian/Jalali (Shamsi) internally.
"""
from .calendar_view import CalendarView

__all__ = ["CalendarView"]
