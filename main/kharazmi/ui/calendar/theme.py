# پوسته — رنگ‌ها، قلم‌ها و متریک‌های بصری تقویم
# هماهنگ با پالت حرفه‌ای مینیمال RASK
from __future__ import annotations

from PySide6.QtGui import QColor, QFont
from PySide6.QtCore import Qt


# ──────────────────────────────── Surfaces ────────────────────────────────

_LIGHT_SURFACE = {
    "CANVAS":      "#FFFFFF",
    "PANEL":       "#F7F7F8",
    "CARD":        "#F4F4F5",
    "CARD_HOVER":  "#EBEBED",
    "CARD_ACTIVE": "#E2E2E5",
    "ELEVATED":    "#E2E2E5",
    "TOOLTIP":     "#2A2A30",
    "OVERLAY":     "rgba(0, 0, 0, 0.25)",
}

_DARK_SURFACE = {
    "CANVAS":      "#111113",
    "PANEL":       "#18181B",
    "CARD":        "#1F1F23",
    "CARD_HOVER":  "#27272B",
    "CARD_ACTIVE": "#2E2E33",
    "ELEVATED":    "#27272B",
    "TOOLTIP":     "#1F1F23",
    "OVERLAY":     "rgba(0, 0, 0, 0.50)",
}

class Surface:
    """Background layers — darker = deeper."""
    pass

# Initialize with light mode (matches app default)
for _k, _v in _LIGHT_SURFACE.items():
    setattr(Surface, _k, _v)


# ──────────────────────────────── Gold Accent ─────────────────────────────

_LIGHT_GOLD = {
    "BRIGHT":        "#D4A017",
    "PRIMARY":       "#B8860B",
    "DEEP":          "#8B6914",
    "MUTED":         "#6B5509",
    "GLOW":          QColor(184, 134, 11, 25),
    "GLOW_STRONG":   QColor(184, 134, 11, 60),
    "GRADIENT_START": "#D4A017",
    "GRADIENT_END":   "#B8860B",
}

_DARK_GOLD = {
    "BRIGHT":        "#F5C842",
    "PRIMARY":       "#D4AF37",
    "DEEP":          "#A88B2A",
    "MUTED":         "#5C4A0E",
    "GLOW":          QColor(212, 175, 55, 40),
    "GLOW_STRONG":   QColor(212, 175, 55, 80),
    "GRADIENT_START": "#F5C842",
    "GRADIENT_END":   "#D4AF37",
}

class Gold:
    pass

# Initialize with light mode
for _k, _v in _LIGHT_GOLD.items():
    setattr(Gold, _k, _v)


# ──────────────────────────────── Text ────────────────────────────────────

_LIGHT_TEXT = {
    "PRIMARY":     "#1C1C1E",
    "SECONDARY":   "#6E6E73",
    "TERTIARY":    "#AEAEB2",
    "ON_GOLD":     "#FFFFFF",
    "MUTED_WHITE": "#6E6E73",
    "WEEKEND":     "#B8860B",
}

_DARK_TEXT = {
    "PRIMARY":     "#F0EDE4",
    "SECONDARY":   "#9E9A8F",
    "TERTIARY":    "#5C5950",
    "ON_GOLD":     "#1A1505",
    "MUTED_WHITE": "#9E9A8F",
    "WEEKEND":     "#D4AF37",
}

class Text:
    pass

for _k, _v in _LIGHT_TEXT.items():
    setattr(Text, _k, _v)


# ──────────────────────────────── Borders ─────────────────────────────────

_LIGHT_BORDER = {
    "SUBTLE":  "#E5E5EA",
    "NORMAL":  "#D1D1D6",
    "STRONG":  "#C7C7CC",
    "GOLD":    "#B8860B",
    "FOCUS":   "#B8860B",
}

_DARK_BORDER = {
    "SUBTLE":  "#222226",
    "NORMAL":  "#2C2C32",
    "STRONG":  "#3A3A42",
    "GOLD":    "#D4AF37",
    "FOCUS":   "#D4AF37",
}

class Border:
    pass

for _k, _v in _LIGHT_BORDER.items():
    setattr(Border, _k, _v)


# ──────────────────────────────── Event Palette ───────────────────────────

class EventColors:
    """Named colors for event cards — professional, muted palette."""
    DEFAULT    = "#B8860B"
    BLUE       = "#5B9BD5"
    TEAL       = "#4A9A8A"
    CORAL      = "#C07060"
    PURPLE     = "#8A6AAA"
    GREEN      = "#5A9A6A"
    ORANGE     = "#C08A4A"
    PINK       = "#B06080"
    SLATE      = "#6A7A8A"
    LAVENDER   = "#7A6AB0"

    # همه
    @classmethod
    def all(cls) -> list[str]:
        return [
            cls.DEFAULT, cls.BLUE, cls.TEAL, cls.CORAL,
            cls.PURPLE, cls.GREEN, cls.ORANGE, cls.PINK,
            cls.SLATE, cls.LAVENDER,
        ]


# ──────────────────────────────── Status ──────────────────────────────────

_LIGHT_STATUS = {
    "DONE":      "#34A853",
    "ACTIVE":    "#5B9BD5",
    "BLOCKED":   "#D93025",
    "DRAFT":     "#9E9E9E",
    "CANCELLED": "#BDBDBD",
}

_DARK_STATUS = {
    "DONE":      "#5A9A6A",
    "ACTIVE":    "#6A8FB8",
    "BLOCKED":   "#C05A5A",
    "DRAFT":     "#5C5950",
    "CANCELLED": "#3A3232",
}

class Status:
    pass

for _k, _v in _LIGHT_STATUS.items():
    setattr(Status, _k, _v)


# ──────────────────────────────── Current Time ────────────────────────────

class NowLine:
    COLOR = QColor(212, 175, 55)
    DOT   = QColor(212, 175, 55)
    WIDTH = 2


# ──────────────────────────────── Priority Colors ─────────────────────────

_LIGHT_PRIORITY = {
    0: "#9E9E9E",   # trivial
    1: "#8B6914",   # low
    2: "#C08A4A",   # medium
    3: "#C07060",   # high
    4: "#D93025",   # critical
}

_DARK_PRIORITY = {
    0: "#5C5950",   # trivial
    1: "#8A8A4A",   # low
    2: "#C08A4A",   # medium
    3: "#C07060",   # high
    4: "#C05A5A",   # critical
}

PRIORITY_COLORS = dict(_LIGHT_PRIORITY)


# ──────────────────────────────── Event Type Icons ───────────────────────

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

# قلم عنوان
def font_title() -> QFont:
    f = QFont("Segoe UI", 28, QFont.Bold)
    f.setStyleStrategy(QFont.PreferAntialias)
    return f

# قلم ماه عنوان
def font_month_title() -> QFont:
    f = QFont("Segoe UI", 24, QFont.Bold)
    f.setStyleStrategy(QFont.PreferAntialias)
    return f

# قلم سربرگ
def font_header() -> QFont:
    f = QFont("Segoe UI", 16, QFont.Bold)
    f.setStyleStrategy(QFont.PreferAntialias)
    return f

# قلم بدنه
def font_body() -> QFont:
    f = QFont("Inter", 15, QFont.Medium)
    f.setStyleStrategy(QFont.PreferAntialias)
    return f

# قلم small
def font_small() -> QFont:
    f = QFont("Inter", 14)
    f.setStyleStrategy(QFont.PreferAntialias)
    return f

# قلم زمان برچسب
def font_time_label() -> QFont:
    f = QFont("Inter", 14)
    f.setStyleStrategy(QFont.PreferAntialias)
    return f

# قلم mini روز
def font_mini_day() -> QFont:
    f = QFont("Inter", 13, QFont.Medium)
    f.setStyleStrategy(QFont.PreferAntialias)
    return f


# ──────────────────────────────── Spacing ─────────────────────────────────

class Spacing:
    XS  = 3
    SM  = 6
    MD  = 10
    LG  = 14
    XL  = 20
    XXL = 28
    XXXL = 36


# ──────────────────────────────── Metrics ─────────────────────────────────

class Metrics:
    # Month view
    MONTH_ROW_HEIGHT       = 48
    MONTH_CELL_MIN_HEIGHT  = 140
    MONTH_CELL_PAD         = 12
    MONTH_DAY_NUMBER_H     = 32
    MONTH_EVENT_CHIP_H     = 30
    MONTH_EVENT_GAP        = 4
    MONTH_OVERFLOW_H       = 26
    MONTH_CORNER_RADIUS    = 10

    # Time views (Day / Week)
    TIME_RULER_WIDTH       = 72
    HOUR_HEIGHT            = 80
    SNAP_MINUTES           = 15
    MIN_EVENT_HEIGHT       = 34
    EVENT_CORNER_RADIUS    = 8
    EVENT_LEFT_BORDER      = 5
    EVENT_PAD              = 8
    ALL_DAY_ROW_HEIGHT     = 40
    ALL_DAY_MAX_ROWS       = 3

    # Year view
    YEAR_CELL_SIZE         = 28
    YEAR_MONTH_PAD         = 20
    YEAR_HEADER_H          = 38

    # Sidebar
    SIDEBAR_WIDTH          = 280
    SIDEBAR_MINI_MONTH_H   = 280

    # Toolbar
    TOOLBAR_HEIGHT         = 64

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
    SCROLL_STEP            = 30


# ──────────────────────────────── Theme switching ────────────────────────

# مجموعه تقویم پوسته
def set_calendar_theme(mode: str) -> None:
    """Switch the calendar sub-theme to 'light' or 'dark'."""
    if mode == "dark":
        for k, v in _DARK_SURFACE.items():
            setattr(Surface, k, v)
        for k, v in _DARK_TEXT.items():
            setattr(Text, k, v)
        for k, v in _DARK_BORDER.items():
            setattr(Border, k, v)
        for k, v in _DARK_STATUS.items():
            setattr(Status, k, v)
        for k, v in _DARK_GOLD.items():
            setattr(Gold, k, v)
        PRIORITY_COLORS.update(_DARK_PRIORITY)
    else:
        for k, v in _LIGHT_SURFACE.items():
            setattr(Surface, k, v)
        for k, v in _LIGHT_TEXT.items():
            setattr(Text, k, v)
        for k, v in _LIGHT_BORDER.items():
            setattr(Border, k, v)
        for k, v in _LIGHT_STATUS.items():
            setattr(Status, k, v)
        for k, v in _LIGHT_GOLD.items():
            setattr(Gold, k, v)
        PRIORITY_COLORS.update(_LIGHT_PRIORITY)


# ──────────────────────────────── Helpers ─────────────────────────────────

# تبدیل رشته رنگ به QColor
def qcolor(hex_str: str) -> QColor:
    """Parse a hex color string to QColor."""
    h = hex_str.lstrip("#")
    if len(h) == 3:
        h = h[0]*2 + h[1]*2 + h[2]*2
    if len(h) == 6:
        return QColor(int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16))
    if len(h) == 8:
        return QColor(int(h[2:4], 16), int(h[4:6], 16), int(h[6:8], 16), int(h[0:2], 16))
    return QColor(hex_str)


# روشن‌تر کردن رنگ
def lighten(hex_str: str, factor: float = 0.15) -> QColor:
    c = qcolor(hex_str)
    h, s, v, a = c.getHsvF()
    v = min(1.0, v + factor)
    result = QColor()
    result.setHsvF(h, s, v, a)
    return result


# تیره‌تر کردن رنگ
def darken(hex_str: str, factor: float = 0.15) -> QColor:
    c = qcolor(hex_str)
    h, s, v, a = c.getHsvF()
    v = max(0.0, v - factor)
    result = QColor()
    result.setHsvF(h, s, v, a)
    return result


# همراه با alpha
def with_alpha(hex_str: str, alpha: int) -> QColor:
    c = qcolor(hex_str)
    c.setAlpha(alpha)
    return c
