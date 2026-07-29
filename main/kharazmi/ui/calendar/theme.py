# پوسته — رنگ‌ها، قلم‌ها و متریک‌های بصری تقویم
from __future__ import annotations

from PySide6.QtGui import QColor, QFont
from PySide6.QtCore import Qt


# ──────────────────────────────── Surfaces ────────────────────────────────

_LIGHT_SURFACE = {
    "CANVAS":      "#FFFFFF",
    "PANEL":       "#F5F5F7",
    "CARD":        "#EEEEF0",
    "CARD_HOVER":  "#E4E4E6",
    "CARD_ACTIVE": "#DCDCDE",
    "ELEVATED":    "#E8E8EA",
    "TOOLTIP":     "#2A2A30",     # dark tooltip for contrast
    "OVERLAY":     "rgba(0, 0, 0, 0.30)",
}

_DARK_SURFACE = {
    "CANVAS":      "#0A0A0A",
    "PANEL":       "#111113",
    "CARD":        "#1A1A1E",
    "CARD_HOVER":  "#222228",
    "CARD_ACTIVE": "#2A2A32",
    "ELEVATED":    "#1E1E24",
    "TOOLTIP":     "#1C1C22",
    "OVERLAY":     "rgba(0, 0, 0, 0.55)",
}

class Surface:
    """Background layers — darker = deeper (dark mode default)."""
    pass

# Initialize with light mode (matches app default)
for _k, _v in _LIGHT_SURFACE.items():
    setattr(Surface, _k, _v)


# ──────────────────────────────── Gold Accent ─────────────────────────────

_LIGHT_GOLD = {
    "BRIGHT":        "#E8B730",
    "PRIMARY":       "#C9A027",
    "DEEP":          "#8C7012",
    "MUTED":         "#6B5509",
    "GLOW":          QColor(201, 160, 39, 30),
    "GLOW_STRONG":   QColor(201, 160, 39, 70),
    "GRADIENT_START": "#E8B730",
    "GRADIENT_END":   "#C9A027",
}

_DARK_GOLD = {
    "BRIGHT":        "#F5C842",
    "PRIMARY":       "#D4AF37",
    "DEEP":          "#8C7012",
    "MUTED":         "#5C4A0E",
    "GLOW":          QColor(212, 175, 55, 46),
    "GLOW_STRONG":   QColor(212, 175, 55, 90),
    "GRADIENT_START": "#F5C842",
    "GRADIENT_END":   "#D4AF37",
}

class Gold:
    pass

# Initialize with light mode (matches app default)
for _k, _v in _LIGHT_GOLD.items():
    setattr(Gold, _k, _v)


# ──────────────────────────────── Text ────────────────────────────────────

_LIGHT_TEXT = {
    "PRIMARY":     "#1A1A2E",
    "SECONDARY":   "#6B6B80",
    "TERTIARY":    "#A0A0B4",
    "ON_GOLD":     "#FFFFFF",
    "MUTED_WHITE": "#5A5A6E",
    "WEEKEND":     "#C9A96E",
}

_DARK_TEXT = {
    "PRIMARY":     "#F5F0DC",
    "SECONDARY":   "#A8A294",
    "TERTIARY":    "#5C5749",
    "ON_GOLD":     "#1A1505",
    "MUTED_WHITE": "#C8C4B8",
    "WEEKEND":     "#C9A96E",
}

class Text:
    pass

for _k, _v in _LIGHT_TEXT.items():
    setattr(Text, _k, _v)


# ──────────────────────────────── Borders ─────────────────────────────────

_LIGHT_BORDER = {
    "SUBTLE":  "#E4E4E8",
    "NORMAL":  "#CCCCCC",
    "STRONG":  "#A8A8B4",
    "GOLD":    "#8C7012",
    "FOCUS":   "#C9A027",
}

_DARK_BORDER = {
    "SUBTLE":  "#1C1C22",
    "NORMAL":  "#2A2A33",
    "STRONG":  "#3A3A45",
    "GOLD":    "#8C7012",
    "FOCUS":   "#D4AF37",
}

class Border:
    pass

for _k, _v in _LIGHT_BORDER.items():
    setattr(Border, _k, _v)


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
    "DONE":      "#2E7D32",
    "ACTIVE":    "#1565C0",
    "BLOCKED":   "#C62828",
    "DRAFT":     "#9E9E9E",
    "CANCELLED": "#BDBDBD",
}

_DARK_STATUS = {
    "DONE":      "#5A8A5A",
    "ACTIVE":    "#5A7FA8",
    "BLOCKED":   "#A85A5A",
    "DRAFT":     "#5C5749",
    "CANCELLED": "#3A2A2A",
}

class Status:
    pass

for _k, _v in _LIGHT_STATUS.items():
    setattr(Status, _k, _v)


# ──────────────────────────────── Current Time ────────────────────────────

class NowLine:
    COLOR = QColor(220, 60, 60)
    DOT   = QColor(220, 60, 60)
    WIDTH = 2


# ──────────────────────────────── Priority Colors ─────────────────────────

_LIGHT_PRIORITY = {
    0: "#9E9E9E",   # trivial
    1: "#827717",   # low
    2: "#C08A4A",   # medium
    3: "#C07060",   # high
    4: "#C62828",   # critical
}

_DARK_PRIORITY = {
    0: "#5C5749",   # trivial
    1: "#7A7A4A",   # low
    2: "#C08A4A",   # medium
    3: "#C07060",   # high
    4: "#C04040",   # critical
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
    """Used for section headers, weekday names, mini month headers."""
    f = QFont("Segoe UI", 16, QFont.Bold)
    f.setStyleStrategy(QFont.PreferAntialias)
    return f

# قلم بدنه
def font_body() -> QFont:
    """Primary body text — event titles, buttons, labels, day numbers."""
    f = QFont("Inter", 15, QFont.Medium)
    f.setStyleStrategy(QFont.PreferAntialias)
    return f

# قلم small
def font_small() -> QFont:
    """Secondary text — times, hints, chips."""
    f = QFont("Inter", 14)
    f.setStyleStrategy(QFont.PreferAntialias)
    return f

# قلم زمان برچسب
def font_time_label() -> QFont:
    """Time ruler labels."""
    f = QFont("Inter", 14)
    f.setStyleStrategy(QFont.PreferAntialias)
    return f

# قلم mini روز
def font_mini_day() -> QFont:
    """Small day numbers in mini-month and year view."""
    f = QFont("Inter", 13, QFont.Medium)
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
    MONTH_ROW_HEIGHT       = 38
    MONTH_CELL_MIN_HEIGHT  = 120
    MONTH_CELL_PAD         = 10
    MONTH_DAY_NUMBER_H     = 26
    MONTH_EVENT_CHIP_H     = 24
    MONTH_EVENT_GAP        = 3
    MONTH_OVERFLOW_H       = 22
    MONTH_CORNER_RADIUS    = 10

    # Time views (Day / Week)
    TIME_RULER_WIDTH       = 60
    HOUR_HEIGHT            = 72
    SNAP_MINUTES           = 15
    MIN_EVENT_HEIGHT       = 28
    EVENT_CORNER_RADIUS    = 8
    EVENT_LEFT_BORDER      = 4
    EVENT_PAD              = 6
    ALL_DAY_ROW_HEIGHT     = 34
    ALL_DAY_MAX_ROWS       = 3

    # Year view
    YEAR_CELL_SIZE         = 24
    YEAR_MONTH_PAD         = 16
    YEAR_HEADER_H          = 32

    # Sidebar
    SIDEBAR_WIDTH          = 260
    SIDEBAR_MINI_MONTH_H   = 240

    # Toolbar
    TOOLBAR_HEIGHT         = 56

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
    """Switch the calendar sub-theme to 'light' or 'dark'.

    Updates Surface, Text, Border, Status, PRIORITY_COLORS
    class attributes in-place so all calendar views pick up
    the new values dynamically.
    """
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

# qcolor
# تبدیل رشته رنگ به QColor
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


# lighten
# روشن‌تر کردن رنگ
def lighten(hex_str: str, factor: float = 0.15) -> QColor:
    c = qcolor(hex_str)
    h, s, v, a = c.getHsvF()
    v = min(1.0, v + factor)
    result = QColor()
    result.setHsvF(h, s, v, a)
    return result


# darken
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
