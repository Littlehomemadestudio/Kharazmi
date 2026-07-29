# سیستم تم RASK — پشتیبانی از حالت روشن و تیره
from __future__ import annotations

from PySide6.QtGui import QColor, QFont, QFontDatabase, QPalette
from PySide6.QtCore import Qt


# ──────────────────────────────────────────────────────────────
#  Light Palette (default)
# ──────────────────────────────────────────────────────────────

_LIGHT = {
    # Surfaces (light progression: white → gray)
    "BG_DEEPEST":   "#F5F5F7",
    "BG_PRIMARY":   "#FFFFFF",
    "BG_SECONDARY": "#F0F0F2",
    "BG_TERTIARY":  "#E6E6E8",
    "BG_ELEVATED":  "#DCDCDE",
    "BG_HOVER":     "#D4D4D8",
    "BG_SELECTED":  "#FFF4CC",    # gold-tinted light

    # Gold family (deeper tints for contrast on white)
    "GOLD_BRIGHT":  "#E8B730",
    "GOLD_PRIMARY": "#C9A027",
    "GOLD_DEEP":    "#8C7012",
    "GOLD_MUTED":   "#6B5509",
    "GOLD_GLOW":    "rgba(201, 160, 39, 0.12)",

    # Text (dark progression for light backgrounds)
    "TEXT_PRIMARY":   "#1A1A2E",
    "TEXT_SECONDARY": "#6B6B80",
    "TEXT_TERTIARY":  "#A0A0B4",
    "TEXT_ON_GOLD":   "#FFFFFF",

    # Borders (light gray progression)
    "BORDER_SUBTLE": "#E4E4E8",
    "BORDER_NORMAL": "#CCCCCC",
    "BORDER_STRONG": "#A8A8B4",
    "BORDER_GOLD":   "#8C7012",

    # Status (more saturated for visibility on white)
    "STATUS_DONE":      "#2E7D32",
    "STATUS_ACTIVE":    "#1565C0",
    "STATUS_BLOCKED":   "#C62828",
    "STATUS_DRAFT":     "#9E9E9E",
    "STATUS_READY":     "#827717",
    "STATUS_DEFERRED":  "#757575",
    "STATUS_CANCELLED": "#BDBDBD",

    # Critical path glow
    "CRITICAL_GLOW": "rgba(201, 160, 39, 0.25)",

    # Risk (lighter backgrounds for heatmap on white)
    "RISK_NEGLIGIBLE": "#C8E6C9",
    "RISK_LOW":        "#A5D6A7",
    "RISK_MEDIUM":     "#FFF59D",
    "RISK_HIGH":       "#FFCC80",
    "RISK_SEVERE":     "#EF9A9A",
}


# ──────────────────────────────────────────────────────────────
#  Dark Palette
# ──────────────────────────────────────────────────────────────

_DARK = {
    # Surfaces (dark progression: near-black → dark gray)
    "BG_DEEPEST":   "#08080A",
    "BG_PRIMARY":   "#0A0A0B",
    "BG_SECONDARY": "#111114",
    "BG_TERTIARY":  "#16161A",
    "BG_ELEVATED":  "#1C1C22",
    "BG_HOVER":     "#22222A",
    "BG_SELECTED":  "#2A2410",

    # Gold family (bright tints for contrast on dark)
    "GOLD_BRIGHT":  "#F5C842",
    "GOLD_PRIMARY": "#D4AF37",
    "GOLD_DEEP":    "#8C7012",
    "GOLD_MUTED":   "#5C4A0E",
    "GOLD_GLOW":    "rgba(212, 175, 55, 0.18)",

    # Text (warm light progression)
    "TEXT_PRIMARY":   "#F5F0DC",
    "TEXT_SECONDARY": "#A8A294",
    "TEXT_TERTIARY":  "#5C5749",
    "TEXT_ON_GOLD":   "#1A1505",

    # Borders (dark progression)
    "BORDER_SUBTLE": "#1F1F25",
    "BORDER_NORMAL": "#2A2A33",
    "BORDER_STRONG": "#3A3A45",
    "BORDER_GOLD":   "#8C7012",

    # Status (muted, never as primary accent)
    "STATUS_DONE":      "#5A8A5A",
    "STATUS_ACTIVE":    "#5A7FA8",
    "STATUS_BLOCKED":   "#A85A5A",
    "STATUS_DRAFT":     "#5C5749",
    "STATUS_READY":     "#7A7A4A",
    "STATUS_DEFERRED":  "#4A4A52",
    "STATUS_CANCELLED": "#3A2A2A",

    # Critical path
    "CRITICAL_GLOW": "rgba(245, 200, 66, 0.35)",

    # Risk (dark muted)
    "RISK_NEGLIGIBLE": "#3A4A3A",
    "RISK_LOW":        "#5A6A4A",
    "RISK_MEDIUM":     "#8A8A4A",
    "RISK_HIGH":       "#A87A4A",
    "RISK_SEVERE":     "#A85A5A",
}


# ──────────────────────────────────────────────────────────────
#  Dynamic Palette class
# ──────────────────────────────────────────────────────────────

class Palette:
    """Dynamically-switchable color palette.

    Class attributes are updated in-place when ``set_theme()`` is called.
    All code that reads ``Palette.TEXT_PRIMARY`` gets the current value.
    """
    pass


# Apply default (light) values to Palette class
for _k, _v in _LIGHT.items():
    setattr(Palette, _k, _v)


# بازگرداندن رنگ متناسب با وضعیت وظیفه

def status_color(status_value: str) -> str:
    return {
        "draft":     Palette.STATUS_DRAFT,
        "ready":     Palette.STATUS_READY,
        "active":    Palette.STATUS_ACTIVE,
        "blocked":   Palette.STATUS_BLOCKED,
        "done":      Palette.STATUS_DONE,
        "deferred":  Palette.STATUS_DEFERRED,
        "cancelled": Palette.STATUS_CANCELLED,
    }.get(status_value, Palette.STATUS_DRAFT)


# بازگرداندن رنگ متناسب با سطح ریسک

def risk_color(risk_value: str) -> str:
    return {
        "negligible": Palette.RISK_NEGLIGIBLE,
        "low":        Palette.RISK_LOW,
        "medium":     Palette.RISK_MEDIUM,
        "high":       Palette.RISK_HIGH,
        "severe":     Palette.RISK_SEVERE,
    }.get(risk_value, Palette.RISK_LOW)


# تبدیل اولویت عددی به وزن بصری (۱ تا ۵)

def priority_weight(p: int) -> int:
    """Visual weight 1..5 for a Priority int (0..4)."""
    return p + 1


# ──────────────────────────────────────────────────────────────
#  Theme switching
# ──────────────────────────────────────────────────────────────

_current_mode: str = "light"


# بازگرداندن حالت فعلی تم ('light' یا 'dark')

def current_mode() -> str:
    """Return the current theme mode ('light' or 'dark')."""
    return _current_mode


# تغییر تم سراسری به حالت روشن یا تیره و ذخیره ترجیح

def set_theme(mode: str) -> None:
    """Switch the global palette to 'light' or 'dark'.

    Updates ``Palette`` class attributes in-place and regenerates ``QSS``.
    After calling this, you must also:
      1. ``app.setStyleSheet(QSS)``
      2. ``app.setPalette(build_qpalette())``
      3. ``window._reapply_theme()``  (rebuilds inline styles)
    """
    global _current_mode, QSS
    _current_mode = mode
    values = _DARK if mode == "dark" else _LIGHT
    for key, val in values.items():
        setattr(Palette, key, val)
    QSS = _build_qss()

    # Also update calendar sub-theme
    from .calendar.theme import set_calendar_theme
    set_calendar_theme(mode)

    # Save preference
    try:
        import json
        from pathlib import Path
        cfg = Path.home() / ".rask" / "theme.json"
        cfg.parent.mkdir(parents=True, exist_ok=True)
        cfg.write_text(json.dumps({"mode": mode}), encoding="utf-8")
    except Exception:
        pass


# بارگذاری ترجیح ذخیره‌شده تم از فایل پیکربندی

def load_theme_preference() -> str:
    """Load saved theme preference from ~/.rask/theme.json."""
    try:
        import json
        from pathlib import Path
        cfg = Path.home() / ".rask" / "theme.json"
        if cfg.exists():
            data = json.loads(cfg.read_text(encoding="utf-8"))
            return data.get("mode", "light")
    except Exception:
        pass
    return "light"


# ──────────────────────────────────────────────────────────────
#  QSS stylesheet generator
# ──────────────────────────────────────────────────────────────

# ساخت شیوه‌نامه کامل QSS از پالت فعلی

def _build_qss() -> str:
    """Build the complete QSS stylesheet from the current Palette."""
    pal = Palette
    return f"""
/* ===== Global ===== */
QWidget {{
    background-color: {pal.BG_PRIMARY};
    color: {pal.TEXT_PRIMARY};
    font-family: "Inter", "SF Pro Display", "Segoe UI", "DejaVu Sans", sans-serif;
    font-size: 16px;
}}

QWidget:disabled {{
    color: {pal.TEXT_TERTIARY};
}}

/* ===== Tooltips ===== */
QToolTip {{
    background-color: {pal.BG_ELEVATED};
    color: {pal.TEXT_PRIMARY};
    border: 1px solid {pal.BORDER_GOLD};
    border-radius: 4px;
    padding: 6px 10px;
    font-size: 14px;
}}

/* ===== Main window background ===== */
QMainWindow, QDialog {{
    background-color: {pal.BG_DEEPEST};
}}

/* ===== Menus ===== */
QMenuBar {{
    background-color: {pal.BG_SECONDARY};
    color: {pal.TEXT_PRIMARY};
    border-bottom: 1px solid {pal.BORDER_SUBTLE};
    padding: 2px 4px;
    font-size: 15px;
}}
QMenuBar::item {{
    background: transparent;
    padding: 6px 12px;
    border-radius: 3px;
}}
QMenuBar::item:selected {{
    background-color: {pal.BG_HOVER};
    color: {pal.GOLD_BRIGHT};
}}
QMenu {{
    background-color: {pal.BG_TERTIARY};
    border: 1px solid {pal.BORDER_NORMAL};
    border-radius: 4px;
    padding: 4px;
}}
QMenu::item {{
    padding: 6px 28px 6px 18px;
    border-radius: 3px;
}}
QMenu::item:selected {{
    background-color: {pal.BG_HOVER};
    color: {pal.GOLD_BRIGHT};
}}
QMenu::separator {{
    height: 1px;
    background: {pal.BORDER_SUBTLE};
    margin: 4px 8px;
}}

/* ===== Status bar ===== */
QStatusBar {{
    background-color: {pal.BG_SECONDARY};
    color: {pal.TEXT_SECONDARY};
    border-top: 1px solid {pal.BORDER_SUBTLE};
    font-size: 14px;
    padding: 2px 8px;
}}
QStatusBar::item {{ border: none; }}

/* ===== Toolbars ===== */
QToolBar {{
    background-color: {pal.BG_SECONDARY};
    border: none;
    border-bottom: 1px solid {pal.BORDER_SUBTLE};
    padding: 4px 6px;
    spacing: 4px;
}}
QToolBar::separator {{
    background: {pal.BORDER_SUBTLE};
    width: 1px;
    margin: 6px 4px;
}}
QToolButton {{
    background: transparent;
    color: {pal.TEXT_SECONDARY};
    border: 1px solid transparent;
    border-radius: 4px;
    padding: 6px 10px;
    font-size: 15px;
}}
QToolButton:hover {{
    background-color: {pal.BG_HOVER};
    color: {pal.TEXT_PRIMARY};
    border: 1px solid {pal.BORDER_NORMAL};
}}
QToolButton:checked {{
    background-color: {pal.BG_SELECTED};
    color: {pal.GOLD_BRIGHT};
    border: 1px solid {pal.BORDER_GOLD};
}}

/* ===== Buttons ===== */
QPushButton {{
    background-color: {pal.BG_TERTIARY};
    color: {pal.TEXT_PRIMARY};
    border: 1px solid {pal.BORDER_NORMAL};
    border-radius: 4px;
    padding: 7px 16px;
    font-size: 15px;
}}
QPushButton:hover {{
    background-color: {pal.BG_ELEVATED};
    border: 1px solid {pal.BORDER_GOLD};
    color: {pal.GOLD_BRIGHT};
}}
QPushButton:pressed {{
    background-color: {pal.BG_HOVER};
}}
QPushButton:disabled {{
    color: {pal.TEXT_TERTIARY};
    background-color: {pal.BG_SECONDARY};
    border: 1px solid {pal.BORDER_SUBTLE};
}}

/* Primary action button — gold */
QPushButton[variant="primary"] {{
    background-color: {pal.GOLD_PRIMARY};
    color: {pal.TEXT_ON_GOLD};
    border: 1px solid {pal.GOLD_DEEP};
    font-weight: 600;
}}
QPushButton[variant="primary"]:hover {{
    background-color: {pal.GOLD_BRIGHT};
    border: 1px solid {pal.GOLD_PRIMARY};
}}
QPushButton[variant="primary"]:pressed {{
    background-color: {pal.GOLD_DEEP};
}}

/* Danger button */
QPushButton[variant="danger"] {{
    background-color: transparent;
    color: {pal.STATUS_BLOCKED};
    border: 1px solid {pal.STATUS_BLOCKED};
}}
QPushButton[variant="danger"]:hover {{
    background-color: {pal.STATUS_BLOCKED};
    color: {pal.TEXT_PRIMARY};
}}

/* ===== Inputs ===== */
QLineEdit, QTextEdit, QPlainTextEdit, QSpinBox, QDoubleSpinBox, QComboBox, QDateEdit {{
    background-color: {pal.BG_TERTIARY};
    color: {pal.TEXT_PRIMARY};
    border: 1px solid {pal.BORDER_NORMAL};
    border-radius: 4px;
    padding: 6px 10px;
    selection-background-color: {pal.GOLD_MUTED};
    selection-color: {pal.TEXT_PRIMARY};
}}
QLineEdit:focus, QTextEdit:focus, QPlainTextEdit:focus,
QSpinBox:focus, QDoubleSpinBox:focus, QComboBox:focus, QDateEdit:focus {{
    border: 1px solid {pal.GOLD_PRIMARY};
    background-color: {pal.BG_ELEVATED};
}}
QLineEdit:disabled, QTextEdit:disabled {{
    color: {pal.TEXT_TERTIARY};
    background-color: {pal.BG_SECONDARY};
}}

QComboBox::drop-down {{
    border: none;
    width: 22px;
}}
QComboBox::down-arrow {{
    image: none;
    border-left: 4px solid transparent;
    border-right: 4px solid transparent;
    border-top: 5px solid {pal.TEXT_SECONDARY};
    margin-right: 8px;
}}
QComboBox QAbstractItemView {{
    background-color: {pal.BG_TERTIARY};
    border: 1px solid {pal.BORDER_NORMAL};
    border-radius: 4px;
    padding: 4px;
    selection-background-color: {pal.BG_HOVER};
    selection-color: {pal.GOLD_BRIGHT};
}}

/* ===== Lists ===== */
QListWidget, QTreeWidget, QTableWidget {{
    background-color: {pal.BG_SECONDARY};
    alternate-background-color: {pal.BG_TERTIARY};
    color: {pal.TEXT_PRIMARY};
    border: 1px solid {pal.BORDER_SUBTLE};
    border-radius: 4px;
    outline: 0;
}}
QListWidget::item, QTreeWidget::item {{
    padding: 4px 6px;
    border-bottom: 1px solid {pal.BORDER_SUBTLE};
}}
QListWidget::item:selected, QTreeWidget::item:selected {{
    background-color: {pal.BG_SELECTED};
    color: {pal.GOLD_BRIGHT};
}}
QListWidget::item:hover, QTreeWidget::item:hover {{
    background-color: {pal.BG_HOVER};
}}
QHeaderView::section {{
    background-color: {pal.BG_TERTIARY};
    color: {pal.TEXT_SECONDARY};
    padding: 6px 10px;
    border: none;
    border-right: 1px solid {pal.BORDER_SUBTLE};
    border-bottom: 1px solid {pal.BORDER_NORMAL};
    font-weight: 600;
    font-size: 14px;
    text-transform: uppercase;
    letter-spacing: 0.5px;
}}

/* ===== Scrollbars ===== */
QScrollBar:vertical {{
    background: transparent;
    width: 12px;
    margin: 0;
}}
QScrollBar::handle:vertical {{
    background: {pal.BG_ELEVATED};
    border-radius: 4px;
    min-height: 24px;
    margin: 2px;
}}
QScrollBar::handle:vertical:hover {{
    background: {pal.BORDER_GOLD};
}}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
    height: 0;
}}
QScrollBar:horizontal {{
    background: transparent;
    height: 12px;
    margin: 0;
}}
QScrollBar::handle:horizontal {{
    background: {pal.BG_ELEVATED};
    border-radius: 4px;
    min-width: 24px;
    margin: 2px;
}}
QScrollBar::handle:horizontal:hover {{
    background: {pal.BORDER_GOLD};
}}
QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {{
    width: 0;
}}

/* ===== Splitter ===== */
QSplitter::handle {{
    background: {pal.BG_DEEPEST};
    border: none;
}}
QSplitter::handle:hover {{
    background: {pal.GOLD_MUTED};
}}
QSplitter::handle:horizontal {{ width: 2px; }}
QSplitter::handle:vertical {{ height: 2px; }}

/* ===== Group boxes ===== */
QGroupBox {{
    background-color: {pal.BG_SECONDARY};
    border: 1px solid {pal.BORDER_SUBTLE};
    border-radius: 6px;
    margin-top: 14px;
    padding-top: 10px;
    font-size: 14px;
    font-weight: 600;
    color: {pal.TEXT_SECONDARY};
    text-transform: uppercase;
    letter-spacing: 0.8px;
}}
QGroupBox::title {{
    subcontrol-origin: margin;
    subcontrol-position: top left;
    padding: 0 8px;
    left: 10px;
    background-color: {pal.BG_PRIMARY};
    color: {pal.GOLD_PRIMARY};
}}

/* ===== Tabs ===== */
QTabWidget::pane {{
    border: 1px solid {pal.BORDER_SUBTLE};
    border-radius: 4px;
    top: -1px;
    background: {pal.BG_PRIMARY};
}}
QTabBar {{
    background: transparent;
}}
QTabBar::tab {{
    background: {pal.BG_SECONDARY};
    color: {pal.TEXT_SECONDARY};
    padding: 8px 18px;
    border: 1px solid {pal.BORDER_SUBTLE};
    border-bottom: none;
    border-top-left-radius: 4px;
    border-top-right-radius: 4px;
    margin-right: 2px;
    font-size: 14px;
    font-weight: 600;
    text-transform: uppercase;
    letter-spacing: 0.5px;
}}
QTabBar::tab:selected {{
    background: {pal.BG_PRIMARY};
    color: {pal.GOLD_BRIGHT};
    border-color: {pal.BORDER_GOLD};
    border-bottom: 2px solid {pal.GOLD_PRIMARY};
}}
QTabBar::tab:hover:!selected {{
    background: {pal.BG_TERTIARY};
    color: {pal.TEXT_PRIMARY};
}}

/* ===== Progress bar ===== */
QProgressBar {{
    background-color: {pal.BG_TERTIARY};
    border: 1px solid {pal.BORDER_NORMAL};
    border-radius: 3px;
    text-align: center;
    color: {pal.TEXT_PRIMARY};
    font-size: 13px;
    height: 14px;
}}
QProgressBar::chunk {{
    background-color: {pal.GOLD_PRIMARY};
    border-radius: 2px;
}}

/* ===== Checkboxes & Radio ===== */
QCheckBox, QRadioButton {{
    color: {pal.TEXT_PRIMARY};
    spacing: 8px;
    padding: 4px 0;
}}
QCheckBox::indicator, QRadioButton::indicator {{
    width: 14px;
    height: 14px;
    border: 1px solid {pal.BORDER_STRONG};
    background: {pal.BG_TERTIARY};
    border-radius: 2px;
}}
QRadioButton::indicator {{ border-radius: 7px; }}
QCheckBox::indicator:checked, QRadioButton::indicator:checked {{
    background: {pal.GOLD_PRIMARY};
    border: 1px solid {pal.GOLD_DEEP};
}}
QCheckBox::indicator:hover, QRadioButton::indicator:hover {{
    border: 1px solid {pal.GOLD_PRIMARY};
}}

/* ===== Labels ===== */
QLabel {{ background: transparent; }}
QLabel[variant="title"] {{
    font-size: 24px;
    font-weight: 700;
    color: {pal.GOLD_BRIGHT};
    letter-spacing: 0.5px;
}}
QLabel[variant="subtitle"] {{
    font-size: 13px;
    color: {pal.TEXT_TERTIARY};
    text-transform: uppercase;
    letter-spacing: 1px;
}}
QLabel[variant="section"] {{
    font-size: 15px;
    font-weight: 600;
    color: {pal.GOLD_PRIMARY};
    text-transform: uppercase;
    letter-spacing: 0.8px;
    padding-top: 8px;
}}
QLabel[variant="mono"] {{
    font-family: "JetBrains Mono", "Menlo", "Consolas", "DejaVu Sans Mono", monospace;
    color: {pal.TEXT_SECONDARY};
}}

/* ===== Dock widgets ===== */
QDockWidget {{
    color: {pal.TEXT_PRIMARY};
    titlebar-close-icon: none;
    titlebar-normal-icon: none;
}}
QDockWidget::title {{
    background: {pal.BG_SECONDARY};
    padding: 6px 12px;
    border-bottom: 1px solid {pal.BORDER_GOLD};
    color: {pal.GOLD_PRIMARY};
    font-weight: 600;
    text-transform: uppercase;
    letter-spacing: 0.8px;
    font-size: 13px;
}}

/* ===== Graphics view (node graph) ===== */
QGraphicsView {{
    background-color: {pal.BG_DEEPEST};
    border: none;
    outline: 0;
}}
"""


# Initialize QSS from current Palette
QSS = _build_qss()


# ──────────────────────────────────────────────────────────────
#  Qt palette builder
# ──────────────────────────────────────────────────────────────

# ساخت پالت رنگی Qt از مقادیر فعلی پالت

def build_qpalette() -> QPalette:
    """Build a QPalette from the current Palette values.

    This covers native Qt widgets that QSS can't fully style
    (e.g. some default dialog elements, message boxes).
    """
    pal = Palette
    p = QPalette()
    p.setColor(QPalette.Window, QColor(pal.BG_PRIMARY))
    p.setColor(QPalette.WindowText, QColor(pal.TEXT_PRIMARY))
    p.setColor(QPalette.Base, QColor(pal.BG_TERTIARY))
    p.setColor(QPalette.AlternateBase, QColor(pal.BG_SECONDARY))
    p.setColor(QPalette.Text, QColor(pal.TEXT_PRIMARY))
    p.setColor(QPalette.Button, QColor(pal.BG_TERTIARY))
    p.setColor(QPalette.ButtonText, QColor(pal.TEXT_PRIMARY))
    p.setColor(QPalette.Highlight, QColor(pal.GOLD_MUTED))
    p.setColor(QPalette.HighlightedText, QColor(pal.GOLD_BRIGHT))
    p.setColor(QPalette.ToolTipBase, QColor(pal.BG_ELEVATED))
    p.setColor(QPalette.ToolTipText, QColor(pal.TEXT_PRIMARY))
    p.setColor(QPalette.PlaceholderText, QColor(pal.TEXT_TERTIARY))
    p.setColor(QPalette.Accent, QColor(pal.GOLD_PRIMARY))
    return p


# ──────────────────────────────────────────────────────────────
#  Helpers
# ──────────────────────────────────────────────────────────────

# ساخت QColor از رشته هگز با شفافیت مشخص

def with_alpha(hex_str: str, alpha: int) -> QColor:
    """Create a QColor from a hex string with the given alpha (0-255)."""
    c = QColor(hex_str)
    c.setAlpha(alpha)
    return c


# بازگرداندن قلم پیش‌فرض برنامه

def default_font() -> QFont:
    f = QFont("Inter", 13)
    f.setStyleStrategy(QFont.PreferAntialias)
    return f


# بازگرداندن قلم هم‌عرض (monospace) پیش‌فرض

def mono_font() -> QFont:
    f = QFont("JetBrains Mono", 13)
    if not f.exactMatch():
        f = QFont("Menlo", 13)
        if not f.exactMatch():
            f = QFont("Consolas", 13)
            if not f.exactMatch():
                f = QFont("DejaVu Sans Mono", 13)
    f.setStyleStrategy(QFont.PreferAntialias)
    return f
