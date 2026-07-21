"""
CalendarTheme — Centralized visual constants for the RASK! calendar.

Luxury dark theme with gold accents. Every color, font, spacing, and
metric used by the calendar is defined here so there is a single source
of truth. Views should NEVER hardcode visual values.

v2 — Bigger, rounder, better space management.
"""
from __future__ import annotations

from PySide6.QtGui import QColor, QFont
from PySide6.QtCore import Qt


# ──────────────────────────────── Surfaces ────────────────────────────────

class Surface:
    """Background layers — darker = deeper."""
    CANVAS       = "#0A0A0A"
    PANEL        = "#111113"
    CARD         = "#1A1A1E"
    CARD_HOVER   = "#222228"
    CARD_ACTIVE  = "#2A2A32"
    ELEVATED     = "#1E1E24"
    TOOLTIP      = "#1C1C22"
    OVERLAY      = "rgba(0, 0, 0, 0.55)"


# ──────────────────────────────── Gold Accent ─────────────────────────────

class Gold:
    BRIGHT   = "#F5C842"
    PRIMARY  = "#D4AF37"
    DEEP     = "#8C7012"
    MUTED    = "#5C4A0E"
    GLOW     = QColor(212, 175, 55, 46)        # 18 % opacity
    GLOW_STRONG = QColor(212, 175, 55, 90)     # 35 % opacity
    GRADIENT_START = "#F5C842"
    GRADIENT_END   = "#D4AF37"


# ──────────────────────────────── Text ────────────────────────────────────

class Text:
    PRIMARY     = "#F5F0DC"
    SECONDARY   = "#A8A294"
    TERTIARY    = "#5C5749"
    ON_GOLD     = "#1A1505"
    MUTED_WHITE = "#C8C4B8"
    WEEKEND     = "#C9A96E"          # slightly warmer for Fri/Sat headers


# ──────────────────────────────── Borders ─────────────────────────────────

class Border:
    SUBTLE   = "#1C1C22"
    NORMAL   = "#2A2A33"
    STRONG   = "#3A3A45"
    GOLD     = "#8C7012"
    FOCUS    = "#D4AF37"


# ──────────────────────────────── Event Palette ───────────────────────────

class EventColors:
    """Named colors for event cards — each calendar gets one."""
    DEFAULT    = "#D4AF37"
    BLUE       = "#5A7FA8"
    TEAL       = "#4A9A8A"
    CORAL      = "#C07060"
    PURPLE     = "#8A6AAA"
    GREEN      = "#5A9A5A"
    ORANGE     = "#C08A4A"
    PINK       = "#B06080"
    SLATE      = "#6A7A8A"
    LAVENDER   = "#7A6AB0"

    @classmethod
    def all(cls) -> list[str]:
        return [
            cls.DEFAULT, cls.BLUE, cls.TEAL, cls.CORAL,
            cls.PURPLE, cls.GREEN, cls.ORANGE, cls.PINK,
            cls.SLATE, cls.LAVENDER,
        ]


# ──────────────────────────────── Status ──────────────────────────────────

class Status:
    DONE      = "#5A8A5A"
    ACTIVE    = "#5A7FA8"
    BLOCKED   = "#A85A5A"
    DRAFT     = "#5C5749"
    CANCELLED = "#3A2A2A"


# ──────────────────────────────── Current Time ────────────────────────────

class NowLine:
    COLOR = QColor(220, 60, 60)
    DOT   = QColor(220, 60, 60)
    WIDTH = 2


# ──────────────────────────────── Priority Colors ─────────────────────────

PRIORITY_COLORS = {
    0: "#5C5749",   # trivial
    1: "#7A7A4A",   # low
    2: "#C08A4A",   # medium
    3: "#C07060",   # high
    4: "#C04040",   # critical
}


# ──────────────────────────────── Event Type Icons ────────────────────────

EVENT_TYPE_ICONS = {
    "normal":      "○",
    "meeting":     "👥",
    "appointment": "📍",
    "birthday":    "🎂",
    "holiday":     "🎆",
    "focus_time":  "🎯",
    "out_of_office": "🏖",
    "task":        "☑",
    "reminder":    "🔔",
}


# ──────────────────────────────── Fonts ───────────────────────────────────

def font_title() -> QFont:
    f = QFont("Segoe UI", 22, QFont.Bold)
    f.setStyleStrategy(QFont.PreferAntialias)
    return f

def font_month_title() -> QFont:
    f = QFont("Segoe UI", 18, QFont.Bold)
    f.setStyleStrategy(QFont.PreferAntialias)
    return f

def font_header() -> QFont:
    """Used for section headers, weekday names, mini month headers."""
    f = QFont("Segoe UI", 12, QFont.Bold)
    f.setStyleStrategy(QFont.PreferAntialias)
    return f

def font_body() -> QFont:
    """Primary body text — event titles, buttons, labels."""
    f = QFont("Inter", 12)
    f.setStyleStrategy(QFont.PreferAntialias)
    return f

def font_small() -> QFont:
    """Secondary text — times, hints, chips."""
    f = QFont("Inter", 11)
    f.setStyleStrategy(QFont.PreferAntialias)
    return f

def font_time_label() -> QFont:
    """Time ruler labels."""
    f = QFont("Inter", 11)
    f.setStyleStrategy(QFont.PreferAntialias)
    return f

def font_mini_day() -> QFont:
    """Small day numbers in mini-month and year view."""
    f = QFont("Inter", 10)
    f.setStyleStrategy(QFont.PreferAntialias)
    return f


# ──────────────────────────────── Spacing ─────────────────────────────────

class Spacing:
    XS  = 2
    SM  = 4
    MD  = 8
    LG  = 12
    XL  = 16
    XXL = 24
    XXXL = 32


# ──────────────────────────────── Metrics ─────────────────────────────────

class Metrics:
    # Month view
    MONTH_ROW_HEIGHT       = 38       # weekday header row (was 32)
    MONTH_CELL_MIN_HEIGHT  = 120      # minimum cell height (was 90)
    MONTH_CELL_PAD         = 6        # cell internal padding (was 4)
    MONTH_DAY_NUMBER_H     = 26       # day number area height (was 22)
    MONTH_EVENT_CHIP_H     = 24       # event chip height (was 20)
    MONTH_EVENT_GAP        = 3        # gap between chips (was 2)
    MONTH_OVERFLOW_H       = 22       # "+N more" row height (was 18)
    MONTH_CORNER_RADIUS    = 10       # cell corner radius (was 6)

    # Time views (Day / Week)
    TIME_RULER_WIDTH       = 60       # time label column width (was 52)
    HOUR_HEIGHT            = 72       # pixels per hour (was 60)
    SNAP_MINUTES           = 15
    MIN_EVENT_HEIGHT       = 28       # min event card height (was 22)
    EVENT_CORNER_RADIUS    = 8        # event card corner radius (was 5)
    EVENT_LEFT_BORDER      = 4        # colored left bar width (was 3)
    EVENT_PAD              = 6        # event internal padding (was 4)
    ALL_DAY_ROW_HEIGHT     = 34       # all-day row height (was 28)
    ALL_DAY_MAX_ROWS       = 3

    # Year view
    YEAR_CELL_SIZE         = 24       # day cell in year view (was 18)
    YEAR_MONTH_PAD         = 16       # padding around mini-months (was 12)
    YEAR_HEADER_H          = 32       # year header height (was 24)

    # Sidebar
    SIDEBAR_WIDTH          = 260      # wider sidebar (was 220)
    SIDEBAR_MINI_MONTH_H   = 240      # taller mini month (was 200)

    # Toolbar
    TOOLBAR_HEIGHT         = 56       # taller toolbar (was 48)

    # Animation
    ANIM_DURATION_MS       = 250
    ANIM_FAST_MS           = 150
    ANIM_SLOW_MS           = 400

    # Drag
    DRAG_THRESHOLD         = 5
    DRAG_OPACITY           = 0.7
    RESIZE_HANDLE_H        = 6

    # Current time line
    NOW_LINE_WIDTH         = 2

    # Scroll
    SCROLL_STEP            = 30       # pixels per scroll step


# ──────────────────────────────── Helpers ─────────────────────────────────

def qcolor(hex_str: str) -> QColor:
    """Parse a hex color string to QColor. Handles #RGB, #RRGGBB, #AARRGGBB."""
    h = hex_str.lstrip("#")
    if len(h) == 3:
        h = h[0]*2 + h[1]*2 + h[2]*2
    if len(h) == 6:
        return QColor(int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16))
    if len(h) == 8:
        return QColor(int(h[2:4], 16), int(h[4:6], 16), int(h[6:8], 16), int(h[0:2], 16))
    return QColor(hex_str)


def lighten(hex_str: str, factor: float = 0.15) -> QColor:
    c = qcolor(hex_str)
    h, s, v, a = c.getHsvF()
    v = min(1.0, v + factor)
    result = QColor()
    result.setHsvF(h, s, v, a)
    return result


def darken(hex_str: str, factor: float = 0.15) -> QColor:
    c = qcolor(hex_str)
    h, s, v, a = c.getHsvF()
    v = max(0.0, v - factor)
    result = QColor()
    result.setHsvF(h, s, v, a)
    return result


def with_alpha(hex_str: str, alpha: int) -> QColor:
    c = qcolor(hex_str)
    c.setAlpha(alpha)
    return c
