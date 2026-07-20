"""
Plan selection dialog — shown at app startup.

Asks the user to pick between:
  - BASIC    (free):  A Google-Calendar-style month planner.
                      Only that view is shown; the graph, gantt, kanban,
                      stats, console, inspector, command palette are all
                      hidden.
  - ENTERPRISE (paid): Full node-graph task operating system with
                      CPM / PERT / Monte Carlo / resource leveling /
                      undo-redo / multi-view / etc.

Once chosen, the selection is persisted in app settings so the user
isn't asked again — but they can switch later via the menu.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Optional

from PySide6.QtCore import Qt, QRectF, QPointF, QSize, QTimer, Signal
from PySide6.QtGui import (
    QPainter, QPen, QBrush, QColor, QFont, QPainterPath, QLinearGradient,
    QRadialGradient, QPolygonF, QPixmap, QFontMetrics,
)
from PySide6.QtWidgets import (
    QDialog, QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QFrame, QSizePolicy, QApplication, QGraphicsDropShadowEffect,
)

from ...core.shamsi import ShamsiDate, SHAMSI_MONTHS_FA
from ..theme import Palette


# ---- Persistent plan preference ----

SETTINGS_PATH = Path.home() / ".rask" / "plan.json"


def load_saved_plan() -> Optional[str]:
    """Return 'basic' or 'enterprise' if previously chosen, else None."""
    try:
        if SETTINGS_PATH.exists():
            data = json.loads(SETTINGS_PATH.read_text(encoding="utf-8"))
            return data.get("plan")
    except Exception:
        pass
    return None


def save_plan(plan: str) -> None:
    """Persist the chosen plan."""
    try:
        SETTINGS_PATH.parent.mkdir(parents=True, exist_ok=True)
        SETTINGS_PATH.write_text(
            json.dumps({"plan": plan, "chosen_at": ShamsiDate.today().format()}, indent=2),
            encoding="utf-8",
        )
    except Exception:
        pass


# ---- The dialog ----

class PlanCard(QFrame):
    """A clickable plan card."""

    def __init__(self, plan: str, title: str, price: str,
                 features: list[str], accent: str,
                 featured: bool = False,
                 parent: QWidget = None) -> None:
        super().__init__(parent)
        self.plan = plan
        self._featured = featured
        self._accent = accent
        self._hovered = False

        self.setFixedSize(360, 460)
        self.setCursor(Qt.PointingHandCursor)
        self.setAcceptDrops(False)

        self.setObjectName("planCard")
        self._apply_style()

        layout = QVBoxLayout(self)
        layout.setContentsMargins(28, 28, 28, 28)
        layout.setSpacing(10)

        # Featured ribbon
        if featured:
            ribbon = QLabel("★ RECOMMENDED")
            ribbon.setStyleSheet(
                f"background-color: {Palette.GOLD_PRIMARY}; "
                f"color: {Palette.TEXT_ON_GOLD}; "
                f"font-size: 10px; font-weight: bold; letter-spacing: 1.5px; "
                f"padding: 3px 10px; border-radius: 3px;"
            )
            ribbon.setMaximumWidth(140)
            ribbon.setAlignment(Qt.AlignCenter)
            layout.addWidget(ribbon, alignment=Qt.AlignLeft)
        else:
            layout.addSpacing(20)

        # Title
        title_lbl = QLabel(title)
        title_lbl.setStyleSheet(
            f"color: {accent}; font-size: 26px; font-weight: bold; "
            f"letter-spacing: 1px;"
        )
        layout.addWidget(title_lbl)

        # Price
        price_lbl = QLabel(price)
        price_lbl.setStyleSheet(
            f"color: {Palette.TEXT_SECONDARY}; font-size: 14px; "
            f"font-family: 'JetBrains Mono', monospace;"
        )
        price_lbl.setWordWrap(True)
        layout.addWidget(price_lbl)

        # Divider
        divider = QFrame()
        divider.setFixedHeight(1)
        divider.setStyleSheet(f"background-color: {Palette.BORDER_SUBTLE};")
        layout.addWidget(divider)

        # Features
        for feat in features:
            row = QHBoxLayout()
            dot = QLabel("◆")
            dot.setStyleSheet(f"color: {accent}; font-size: 10px;")
            dot.setFixedWidth(14)
            row.addWidget(dot)
            text = QLabel(feat)
            text.setStyleSheet(f"color: {Palette.TEXT_PRIMARY}; font-size: 12px;")
            text.setWordWrap(True)
            row.addWidget(text, stretch=1)
            row_container = QWidget()
            row_container.setLayout(row)
            layout.addWidget(row_container)

        layout.addStretch()

        # CTA button
        self._cta = QPushButton(f"Choose {title}")
        self._cta.setProperty("variant", "primary" if featured else "default")
        self._cta.setFixedHeight(40)
        layout.addWidget(self._cta)

    def _apply_style(self) -> None:
        border_color = self._accent if self._featured else Palette.BORDER_NORMAL
        border_width = "2px" if self._featured else "1px"
        self.setStyleSheet(f"""
            QFrame#planCard {{
                background-color: {Palette.BG_TERTIARY};
                border: {border_width} solid {border_color};
                border-radius: 12px;
            }}
        """)

    def enterEvent(self, event) -> None:
        self._hovered = True
        if not self._featured:
            self.setStyleSheet(f"""
                QFrame#planCard {{
                    background-color: {Palette.BG_ELEVATED};
                    border: 2px solid {self._accent};
                    border-radius: 12px;
                }}
            """)
        super().enterEvent(event)

    def leaveEvent(self, event) -> None:
        self._hovered = False
        self._apply_style()
        super().leaveEvent(event)

    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.LeftButton:
            self._cta.click()
        super().mousePressEvent(event)


class PlanSelectionDialog(QDialog):
    """Modal dialog that asks the user to pick a plan."""

    def __init__(self, parent: QWidget = None) -> None:
        super().__init__(parent)
        self.chosen_plan: Optional[str] = None
        self.setWindowTitle("Welcome to Rask")
        self.setModal(True)
        self.setMinimumSize(900, 620)
        self.setStyleSheet(f"background-color: {Palette.BG_DEEPEST};")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(40, 32, 40, 32)
        layout.setSpacing(20)

        # Header
        header = QVBoxLayout()
        header.setSpacing(4)

        title = QLabel("KHARAZMI")
        title.setStyleSheet(
            f"color: {Palette.GOLD_BRIGHT}; font-size: 32px; font-weight: bold; "
            f"letter-spacing: 4px;"
        )
        title.setAlignment(Qt.AlignCenter)
        header.addWidget(title)

        subtitle = QLabel("TASK OPERATING SYSTEM")
        subtitle.setStyleSheet(
            f"color: {Palette.TEXT_TERTIARY}; font-size: 11px; "
            f"font-weight: bold; letter-spacing: 3px;"
        )
        subtitle.setAlignment(Qt.AlignCenter)
        header.addWidget(subtitle)

        today = ShamsiDate.today()
        date_lbl = QLabel(f"Today: {today.format('d MMMM yyyy')}  •  {today.weekday_fa}")
        date_lbl.setStyleSheet(
            f"color: {Palette.GOLD_PRIMARY}; font-size: 12px; "
            f"font-family: 'JetBrains Mono', monospace; padding-top: 4px;"
        )
        date_lbl.setAlignment(Qt.AlignCenter)
        header.addWidget(date_lbl)

        layout.addLayout(header)

        # Choose-your-experience prompt
        prompt = QLabel("Choose your experience")
        prompt.setStyleSheet(
            f"color: {Palette.TEXT_SECONDARY}; font-size: 14px; padding-top: 12px;"
        )
        prompt.setAlignment(Qt.AlignCenter)
        layout.addWidget(prompt)

        # Cards row
        cards_row = QHBoxLayout()
        cards_row.setSpacing(24)
        cards_row.addStretch()

        self._basic_card = PlanCard(
            plan="basic",
            title="Basic",
            price="Free",
            accent=Palette.TEXT_SECONDARY,
            features=[
                "Google-Calendar-style planner",
                "Day / Week / Month / Year / Schedule views",
                "Persian Shamsi calendar (Iranian week)",
                "Multiple calendars with colors",
                "Recurring events (RRULE-based)",
                "Drag-and-drop to reschedule",
                "Natural-language event creation",
                "Built-in Persian holidays",
                "Reminders, attendees, locations",
                "Local SQLite persistence",
            ],
            featured=False,
        )
        self._basic_card._cta.clicked.connect(lambda: self._choose("basic"))
        cards_row.addWidget(self._basic_card)

        self._enterprise_card = PlanCard(
            plan="enterprise",
            title="Enterprise",
            price="Paid  •  Pro features",
            accent=Palette.GOLD_BRIGHT,
            features=[
                "Node-based task graph (main view)",
                "Critical Path Method (CPM)",
                "PERT 3-point estimates",
                "Monte Carlo risk simulation",
                "Resource leveling",
                "Gantt / Kanban / Timeline / Stats",
                "Undo / Redo with command stack",
                "Command palette & integrated console",
                "Mermaid / JSON / CSV export",
                "Local rule-based advisor",
            ],
            featured=True,
        )
        self._enterprise_card._cta.clicked.connect(lambda: self._choose("enterprise"))
        cards_row.addWidget(self._enterprise_card)

        cards_row.addStretch()
        layout.addLayout(cards_row, stretch=1)

        # Footer hint
        hint = QLabel(
            "You can switch plans later from the menu: File → Switch Plan"
        )
        hint.setStyleSheet(
            f"color: {Palette.TEXT_TERTIARY}; font-size: 11px; "
            f"font-style: italic;"
        )
        hint.setAlignment(Qt.AlignCenter)
        layout.addWidget(hint)

    def _choose(self, plan: str) -> None:
        self.chosen_plan = plan
        save_plan(plan)
        self.accept()

    @classmethod
    def ask(cls, parent: QWidget = None) -> Optional[str]:
        """Show the dialog and return the chosen plan (or None if cancelled)."""
        dlg = cls(parent)
        if dlg.exec() == QDialog.Accepted:
            return dlg.chosen_plan
        return None
