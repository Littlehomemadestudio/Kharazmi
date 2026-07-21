"""
The Rask Gold-on-Dark theme.

A single, opinionated visual language: deep near-black surfaces with
warm gold accents. No theme switching — the look IS the product.

Color philosophy:
  - Backgrounds descend from #0A0A0B (almost black) through a series
    of subtle elevations (#111114, #16161A, #1C1C22).
  - Gold is the SOLE accent family. We use three tints:
      gold_bright   #F5C842 — primary actions, critical highlights
      gold_primary  #D4AF37 — default accent
      gold_deep     #8C7012 — borders, quiet emphasis
  - Status colors are muted and used ONLY for status, never as primary
    accents (so the gold remains the visual signature).
"""
from __future__ import annotations

from PySide6.QtGui import QColor, QFont, QFontDatabase, QPalette
from PySide6.QtCore import Qt


# ---- Color palette ----
class Palette:
    # Surfaces (dark)
    BG_DEEPEST   = "#08080A"
    BG_PRIMARY   = "#0A0A0B"
    BG_SECONDARY = "#111114"
    BG_TERTIARY  = "#16161A"
    BG_ELEVATED  = "#1C1C22"
    BG_HOVER     = "#22222A"
    BG_SELECTED  = "#2A2410"   # subtle gold-tinted dark

    # Gold family (the only accent)
    GOLD_BRIGHT  = "#F5C842"
    GOLD_PRIMARY = "#D4AF37"
    GOLD_DEEP    = "#8C7012"
    GOLD_MUTED   = "#5C4A0E"
    GOLD_GLOW    = "rgba(212, 175, 55, 0.18)"

    # Text
    TEXT_PRIMARY   = "#F5F0DC"   # warm off-white
    TEXT_SECONDARY = "#A8A294"
    TEXT_TERTIARY  = "#5C5749"
    TEXT_ON_GOLD   = "#1A1505"   # dark text on gold buttons

    # Borders
    BORDER_SUBTLE = "#1F1F25"
    BORDER_NORMAL = "#2A2A33"
    BORDER_STRONG = "#3A3A45"
    BORDER_GOLD   = "#8C7012"

    # Status (used sparingly — never as primary accent)
    STATUS_DONE     = "#5A8A5A"
    STATUS_ACTIVE   = "#5A7FA8"
    STATUS_BLOCKED  = "#A85A5A"
    STATUS_DRAFT    = "#5C5749"
    STATUS_READY    = "#7A7A4A"
    STATUS_DEFERRED = "#4A4A52"
    STATUS_CANCELLED = "#3A2A2A"

    # Critical path
    CRITICAL_GLOW = "rgba(245, 200, 66, 0.35)"

    # Risk
    RISK_NEGLIGIBLE = "#3A4A3A"
    RISK_LOW        = "#5A6A4A"
    RISK_MEDIUM     = "#8A8A4A"
    RISK_HIGH       = "#A87A4A"
    RISK_SEVERE     = "#A85A5A"


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


def risk_color(risk_value: str) -> str:
    return {
        "negligible": Palette.RISK_NEGLIGIBLE,
        "low":        Palette.RISK_LOW,
        "medium":     Palette.RISK_MEDIUM,
        "high":       Palette.RISK_HIGH,
        "severe":     Palette.RISK_SEVERE,
    }.get(risk_value, Palette.RISK_LOW)


def priority_weight(p: int) -> int:
    """Visual weight 1..5 for a Priority int (0..4)."""
    return p + 1


# ---- The complete QSS stylesheet ----
QSS = f"""
/* ===== Global ===== */
QWidget {{
    background-color: {Palette.BG_PRIMARY};
    color: {Palette.TEXT_PRIMARY};
    font-family: "Inter", "SF Pro Display", "Segoe UI", "DejaVu Sans", sans-serif;
    font-size: 13px;
}}

QWidget:disabled {{
    color: {Palette.TEXT_TERTIARY};
}}

/* ===== Tooltips ===== */
QToolTip {{
    background-color: {Palette.BG_ELEVATED};
    color: {Palette.TEXT_PRIMARY};
    border: 1px solid {Palette.BORDER_GOLD};
    border-radius: 4px;
    padding: 6px 10px;
    font-size: 12px;
}}

/* ===== Main window background ===== */
QMainWindow, QDialog {{
    background-color: {Palette.BG_DEEPEST};
}}

/* ===== Menus ===== */
QMenuBar {{
    background-color: {Palette.BG_SECONDARY};
    color: {Palette.TEXT_PRIMARY};
    border-bottom: 1px solid {Palette.BORDER_SUBTLE};
    padding: 2px 4px;
    font-size: 13px;
}}
QMenuBar::item {{
    background: transparent;
    padding: 6px 12px;
    border-radius: 3px;
}}
QMenuBar::item:selected {{
    background-color: {Palette.BG_HOVER};
    color: {Palette.GOLD_BRIGHT};
}}
QMenu {{
    background-color: {Palette.BG_TERTIARY};
    border: 1px solid {Palette.BORDER_NORMAL};
    border-radius: 4px;
    padding: 4px;
}}
QMenu::item {{
    padding: 6px 28px 6px 18px;
    border-radius: 3px;
}}
QMenu::item:selected {{
    background-color: {Palette.BG_HOVER};
    color: {Palette.GOLD_BRIGHT};
}}
QMenu::separator {{
    height: 1px;
    background: {Palette.BORDER_SUBTLE};
    margin: 4px 8px;
}}

/* ===== Status bar ===== */
QStatusBar {{
    background-color: {Palette.BG_SECONDARY};
    color: {Palette.TEXT_SECONDARY};
    border-top: 1px solid {Palette.BORDER_SUBTLE};
    font-size: 12px;
    padding: 2px 8px;
}}
QStatusBar::item {{ border: none; }}

/* ===== Toolbars ===== */
QToolBar {{
    background-color: {Palette.BG_SECONDARY};
    border: none;
    border-bottom: 1px solid {Palette.BORDER_SUBTLE};
    padding: 4px 6px;
    spacing: 4px;
}}
QToolBar::separator {{
    background: {Palette.BORDER_SUBTLE};
    width: 1px;
    margin: 6px 4px;
}}
QToolButton {{
    background: transparent;
    color: {Palette.TEXT_SECONDARY};
    border: 1px solid transparent;
    border-radius: 4px;
    padding: 6px 10px;
    font-size: 13px;
}}
QToolButton:hover {{
    background-color: {Palette.BG_HOVER};
    color: {Palette.TEXT_PRIMARY};
    border: 1px solid {Palette.BORDER_NORMAL};
}}
QToolButton:checked {{
    background-color: {Palette.BG_SELECTED};
    color: {Palette.GOLD_BRIGHT};
    border: 1px solid {Palette.BORDER_GOLD};
}}

/* ===== Buttons ===== */
QPushButton {{
    background-color: {Palette.BG_TERTIARY};
    color: {Palette.TEXT_PRIMARY};
    border: 1px solid {Palette.BORDER_NORMAL};
    border-radius: 4px;
    padding: 7px 16px;
    font-size: 13px;
}}
QPushButton:hover {{
    background-color: {Palette.BG_ELEVATED};
    border: 1px solid {Palette.BORDER_GOLD};
    color: {Palette.GOLD_BRIGHT};
}}
QPushButton:pressed {{
    background-color: {Palette.BG_HOVER};
}}
QPushButton:disabled {{
    color: {Palette.TEXT_TERTIARY};
    background-color: {Palette.BG_SECONDARY};
    border: 1px solid {Palette.BORDER_SUBTLE};
}}

/* Primary action button — gold */
QPushButton[variant="primary"] {{
    background-color: {Palette.GOLD_PRIMARY};
    color: {Palette.TEXT_ON_GOLD};
    border: 1px solid {Palette.GOLD_DEEP};
    font-weight: 600;
}}
QPushButton[variant="primary"]:hover {{
    background-color: {Palette.GOLD_BRIGHT};
    border: 1px solid {Palette.GOLD_PRIMARY};
}}
QPushButton[variant="primary"]:pressed {{
    background-color: {Palette.GOLD_DEEP};
}}

/* Danger button */
QPushButton[variant="danger"] {{
    background-color: transparent;
    color: {Palette.STATUS_BLOCKED};
    border: 1px solid {Palette.STATUS_BLOCKED};
}}
QPushButton[variant="danger"]:hover {{
    background-color: {Palette.STATUS_BLOCKED};
    color: {Palette.TEXT_PRIMARY};
}}

/* ===== Inputs ===== */
QLineEdit, QTextEdit, QPlainTextEdit, QSpinBox, QDoubleSpinBox, QComboBox, QDateEdit {{
    background-color: {Palette.BG_TERTIARY};
    color: {Palette.TEXT_PRIMARY};
    border: 1px solid {Palette.BORDER_NORMAL};
    border-radius: 4px;
    padding: 6px 10px;
    selection-background-color: {Palette.GOLD_MUTED};
    selection-color: {Palette.TEXT_PRIMARY};
}}
QLineEdit:focus, QTextEdit:focus, QPlainTextEdit:focus,
QSpinBox:focus, QDoubleSpinBox:focus, QComboBox:focus, QDateEdit:focus {{
    border: 1px solid {Palette.GOLD_PRIMARY};
    background-color: {Palette.BG_ELEVATED};
}}
QLineEdit:disabled, QTextEdit:disabled {{
    color: {Palette.TEXT_TERTIARY};
    background-color: {Palette.BG_SECONDARY};
}}

QComboBox::drop-down {{
    border: none;
    width: 22px;
}}
QComboBox::down-arrow {{
    image: none;
    border-left: 4px solid transparent;
    border-right: 4px solid transparent;
    border-top: 5px solid {Palette.TEXT_SECONDARY};
    margin-right: 8px;
}}
QComboBox QAbstractItemView {{
    background-color: {Palette.BG_TERTIARY};
    border: 1px solid {Palette.BORDER_NORMAL};
    border-radius: 4px;
    padding: 4px;
    selection-background-color: {Palette.BG_HOVER};
    selection-color: {Palette.GOLD_BRIGHT};
}}

/* ===== Lists ===== */
QListWidget, QTreeWidget, QTableWidget {{
    background-color: {Palette.BG_SECONDARY};
    alternate-background-color: {Palette.BG_TERTIARY};
    color: {Palette.TEXT_PRIMARY};
    border: 1px solid {Palette.BORDER_SUBTLE};
    border-radius: 4px;
    outline: 0;
}}
QListWidget::item, QTreeWidget::item {{
    padding: 4px 6px;
    border-bottom: 1px solid {Palette.BORDER_SUBTLE};
}}
QListWidget::item:selected, QTreeWidget::item:selected {{
    background-color: {Palette.BG_SELECTED};
    color: {Palette.GOLD_BRIGHT};
}}
QListWidget::item:hover, QTreeWidget::item:hover {{
    background-color: {Palette.BG_HOVER};
}}
QHeaderView::section {{
    background-color: {Palette.BG_TERTIARY};
    color: {Palette.TEXT_SECONDARY};
    padding: 6px 10px;
    border: none;
    border-right: 1px solid {Palette.BORDER_SUBTLE};
    border-bottom: 1px solid {Palette.BORDER_NORMAL};
    font-weight: 600;
    font-size: 12px;
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
    background: {Palette.BG_ELEVATED};
    border-radius: 4px;
    min-height: 24px;
    margin: 2px;
}}
QScrollBar::handle:vertical:hover {{
    background: {Palette.BORDER_GOLD};
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
    background: {Palette.BG_ELEVATED};
    border-radius: 4px;
    min-width: 24px;
    margin: 2px;
}}
QScrollBar::handle:horizontal:hover {{
    background: {Palette.BORDER_GOLD};
}}
QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {{
    width: 0;
}}

/* ===== Splitter ===== */
QSplitter::handle {{
    background: {Palette.BG_DEEPEST};
    border: none;
}}
QSplitter::handle:hover {{
    background: {Palette.GOLD_MUTED};
}}
QSplitter::handle:horizontal {{ width: 2px; }}
QSplitter::handle:vertical {{ height: 2px; }}

/* ===== Group boxes ===== */
QGroupBox {{
    background-color: {Palette.BG_SECONDARY};
    border: 1px solid {Palette.BORDER_SUBTLE};
    border-radius: 6px;
    margin-top: 14px;
    padding-top: 10px;
    font-size: 12px;
    font-weight: 600;
    color: {Palette.TEXT_SECONDARY};
    text-transform: uppercase;
    letter-spacing: 0.8px;
}}
QGroupBox::title {{
    subcontrol-origin: margin;
    subcontrol-position: top left;
    padding: 0 8px;
    left: 10px;
    background-color: {Palette.BG_PRIMARY};
    color: {Palette.GOLD_PRIMARY};
}}

/* ===== Tabs ===== */
QTabWidget::pane {{
    border: 1px solid {Palette.BORDER_SUBTLE};
    border-radius: 4px;
    top: -1px;
    background: {Palette.BG_PRIMARY};
}}
QTabBar {{
    background: transparent;
}}
QTabBar::tab {{
    background: {Palette.BG_SECONDARY};
    color: {Palette.TEXT_SECONDARY};
    padding: 8px 18px;
    border: 1px solid {Palette.BORDER_SUBTLE};
    border-bottom: none;
    border-top-left-radius: 4px;
    border-top-right-radius: 4px;
    margin-right: 2px;
    font-size: 12px;
    font-weight: 600;
    text-transform: uppercase;
    letter-spacing: 0.5px;
}}
QTabBar::tab:selected {{
    background: {Palette.BG_PRIMARY};
    color: {Palette.GOLD_BRIGHT};
    border-color: {Palette.BORDER_GOLD};
    border-bottom: 2px solid {Palette.GOLD_PRIMARY};
}}
QTabBar::tab:hover:!selected {{
    background: {Palette.BG_TERTIARY};
    color: {Palette.TEXT_PRIMARY};
}}

/* ===== Progress bar ===== */
QProgressBar {{
    background-color: {Palette.BG_TERTIARY};
    border: 1px solid {Palette.BORDER_NORMAL};
    border-radius: 3px;
    text-align: center;
    color: {Palette.TEXT_PRIMARY};
    font-size: 11px;
    height: 14px;
}}
QProgressBar::chunk {{
    background-color: {Palette.GOLD_PRIMARY};
    border-radius: 2px;
}}

/* ===== Checkboxes & Radio ===== */
QCheckBox, QRadioButton {{
    color: {Palette.TEXT_PRIMARY};
    spacing: 8px;
    padding: 4px 0;
}}
QCheckBox::indicator, QRadioButton::indicator {{
    width: 14px;
    height: 14px;
    border: 1px solid {Palette.BORDER_STRONG};
    background: {Palette.BG_TERTIARY};
    border-radius: 2px;
}}
QRadioButton::indicator {{ border-radius: 7px; }}
QCheckBox::indicator:checked, QRadioButton::indicator:checked {{
    background: {Palette.GOLD_PRIMARY};
    border: 1px solid {Palette.GOLD_DEEP};
}}
QCheckBox::indicator:hover, QRadioButton::indicator:hover {{
    border: 1px solid {Palette.GOLD_PRIMARY};
}}

/* ===== Labels ===== */
QLabel {{ background: transparent; }}
QLabel[variant="title"] {{
    font-size: 18px;
    font-weight: 700;
    color: {Palette.GOLD_BRIGHT};
    letter-spacing: 0.5px;
}}
QLabel[variant="subtitle"] {{
    font-size: 11px;
    color: {Palette.TEXT_TERTIARY};
    text-transform: uppercase;
    letter-spacing: 1px;
}}
QLabel[variant="section"] {{
    font-size: 12px;
    font-weight: 600;
    color: {Palette.GOLD_PRIMARY};
    text-transform: uppercase;
    letter-spacing: 0.8px;
    padding-top: 8px;
}}
QLabel[variant="mono"] {{
    font-family: "JetBrains Mono", "Menlo", "Consolas", "DejaVu Sans Mono", monospace;
    color: {Palette.TEXT_SECONDARY};
}}

/* ===== Dock widgets ===== */
QDockWidget {{
    color: {Palette.TEXT_PRIMARY};
    titlebar-close-icon: none;
    titlebar-normal-icon: none;
}}
QDockWidget::title {{
    background: {Palette.BG_SECONDARY};
    padding: 6px 12px;
    border-bottom: 1px solid {Palette.BORDER_GOLD};
    color: {Palette.GOLD_PRIMARY};
    font-weight: 600;
    text-transform: uppercase;
    letter-spacing: 0.8px;
    font-size: 11px;
}}

/* ===== Graphics view (node graph) ===== */
QGraphicsView {{
    background-color: {Palette.BG_DEEPEST};
    border: none;
    outline: 0;
}}
"""

# ---- Qt palette for things QSS can't reach (e.g. some default dialogs) ----
def build_qpalette() -> QPalette:
    p = QPalette()
    p.setColor(QPalette.Window, QColor(Palette.BG_PRIMARY))
    p.setColor(QPalette.WindowText, QColor(Palette.TEXT_PRIMARY))
    p.setColor(QPalette.Base, QColor(Palette.BG_TERTIARY))
    p.setColor(QPalette.AlternateBase, QColor(Palette.BG_SECONDARY))
    p.setColor(QPalette.Text, QColor(Palette.TEXT_PRIMARY))
    p.setColor(QPalette.Button, QColor(Palette.BG_TERTIARY))
    p.setColor(QPalette.ButtonText, QColor(Palette.TEXT_PRIMARY))
    p.setColor(QPalette.Highlight, QColor(Palette.GOLD_MUTED))
    p.setColor(QPalette.HighlightedText, QColor(Palette.GOLD_BRIGHT))
    p.setColor(QPalette.ToolTipBase, QColor(Palette.BG_ELEVATED))
    p.setColor(QPalette.ToolTipText, QColor(Palette.TEXT_PRIMARY))
    p.setColor(QPalette.PlaceholderText, QColor(Palette.TEXT_TERTIARY))
    p.setColor(QPalette.Accent, QColor(Palette.GOLD_PRIMARY))
    return p


# ---- Fonts ----
def with_alpha(hex_str: str, alpha: int) -> QColor:
    """Create a QColor from a hex string with the given alpha (0-255)."""
    c = QColor(hex_str)
    c.setAlpha(alpha)
    return c


def default_font() -> QFont:
    f = QFont("Inter", 10)
    f.setStyleStrategy(QFont.PreferAntialias)
    return f


def mono_font() -> QFont:
    f = QFont("JetBrains Mono", 10)
    if not f.exactMatch():
        f = QFont("Menlo", 10)
        if not f.exactMatch():
            f = QFont("Consolas", 10)
            if not f.exactMatch():
                f = QFont("DejaVu Sans Mono", 10)
    f.setStyleStrategy(QFont.PreferAntialias)
    return f
