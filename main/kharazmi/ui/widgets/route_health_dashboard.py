"""
RouteHealthDashboard — A visually stunning health dashboard for Kharazmi AI Planner routes.

Shows overall health gauge, score breakdown, bottleneck alerts, recommendations,
Monte Carlo simulation results, and action buttons.

Uses the gold-on-dark theme from Palette and custom QPainter gauges.
"""
from __future__ import annotations

import math
from typing import Optional

from PySide6.QtCore import Qt, QRectF, Signal, QSize, QMarginsF, QTimer, QPropertyAnimation, QEasingCurve
from PySide6.QtGui import (
    QPainter, QPainterPath, QColor, QPen, QBrush, QFont, QLinearGradient,
    QRadialGradient, QConicalGradient, QFontMetrics, QPixmap, QPaintEvent,
)
from PySide6.QtWidgets import (
    QFrame, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QProgressBar,
    QScrollArea, QWidget, QSizePolicy, QGridLayout, QSpacerItem,
    QSizePolicy as SP,
)

from ...ai import RouteHealthReport, SimulationResult, Route
from ..theme import Palette


# ──────────────────────────────────────────────────────────────────────
#  Circular Gauge Widget (QPainter-based)
# ──────────────────────────────────────────────────────────────────────

class _CircularGauge(QWidget):
    """
    A large circular gauge showing a score from 0-100 with a color gradient
    arc that sweeps from red → yellow → green.  The score number and grade
    text are drawn in the centre.
    """

    MIN_SIZE = 220

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._score: float = 0.0
        self._grade: str = "F"
        self._anim_score: float = 0.0
        self.setFixedSize(self.MIN_SIZE, self.MIN_SIZE)

    # ── public ──
    def set_score(self, score: float, grade: str) -> None:
        self._score = max(0.0, min(100.0, score))
        self._grade = grade
        # Animate from current position
        self._anim_score = self._score
        self.update()

    # ── painting ──
    def paintEvent(self, event: QPaintEvent) -> None:  # noqa: N802
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing, True)
        p.setRenderHint(QPainter.TextAntialiasing, True)

        w, h = self.width(), self.height()
        cx, cy = w / 2, h / 2

        # Ring geometry
        pen_width = 16
        radius = min(w, h) / 2 - pen_width - 8
        rect = QRectF(cx - radius, cy - radius, radius * 2, radius * 2)

        # ── background ring ──
        bg_pen = QPen(QColor(Palette.BG_TERTIARY), pen_width, Qt.SolidLine, Qt.RoundCap)
        p.setPen(bg_pen)
        p.setBrush(Qt.NoBrush)
        p.drawArc(rect, 0, 360 * 16)

        # ── value arc with gradient ──
        if self._anim_score > 0:
            # The arc spans from the top (270°) clockwise
            start_angle = 270 * 16
            span = int(self._anim_score / 100.0 * 360 * 16)

            # Build a conical gradient centred on the widget
            grad = QConicalGradient(cx, cy, 270)  # 0° = right, 270 = top
            # Red → Yellow → Green mapped over 0..1
            grad.setColorAt(0.0, QColor("#C0392B"))      # deep red
            grad.setColorAt(0.35, QColor("#E67E22"))      # orange
            grad.setColorAt(0.55, QColor("#F1C40F"))      # yellow
            grad.setColorAt(0.75, QColor("#27AE60"))      # green
            grad.setColorAt(1.0, QColor("#1E8449"))       # dark green

            arc_pen = QPen(QBrush(grad), pen_width, Qt.SolidLine, Qt.RoundCap)
            p.setPen(arc_pen)
            p.drawArc(rect, start_angle, -span)

            # Glow effect — wider translucent arc behind
            glow_pen = QPen(QBrush(grad), pen_width + 10, Qt.SolidLine, Qt.RoundCap)
            glow_color = QColor(255, 255, 255, 25)
            p.setPen(glow_pen)
            p.drawArc(rect, start_angle, -span)

        # ── centre score number ──
        score_font = QFont("Inter", 48, QFont.Bold)
        p.setFont(score_font)
        p.setPen(QPen(QColor(Palette.TEXT_PRIMARY)))

        score_text = f"{int(round(self._anim_score))}"
        fm = QFontMetrics(score_font)
        sw = fm.horizontalAdvance(score_text)
        p.drawText(QRectF(cx - sw / 2 - 4, cy - 34, sw + 8, 60), Qt.AlignCenter, score_text)

        # ── grade label ──
        grade_font = QFont("Inter", 18, QFont.DemiBold)
        p.setFont(grade_font)
        grade_color = self._grade_color()
        p.setPen(QPen(grade_color))
        grade_text = self._grade
        fm_g = QFontMetrics(grade_font)
        gw = fm_g.horizontalAdvance(grade_text)
        p.drawText(QRectF(cx - gw / 2 - 4, cy + 22, gw + 8, 30), Qt.AlignCenter, grade_text)

        # ── "HEALTH SCORE" subtitle ──
        sub_font = QFont("Inter", 8, QFont.Bold)
        p.setFont(sub_font)
        p.setPen(QPen(QColor(Palette.TEXT_TERTIARY)))
        sub_text = "HEALTH SCORE"
        fm_s = QFontMetrics(sub_font)
        subw = fm_s.horizontalAdvance(sub_text)
        p.drawText(QRectF(cx - subw / 2 - 4, cy + 48, subw + 8, 16), Qt.AlignCenter, sub_text)

        p.end()

    def _grade_color(self) -> QColor:
        m = {
            "A+": "#27AE60", "A": "#2ECC71",
            "B": "#F1C40F", "C": "#E67E22",
            "D": "#E74C3C", "F": "#C0392B",
        }
        return QColor(m.get(self._grade, Palette.TEXT_TERTIARY))


# ──────────────────────────────────────────────────────────────────────
#  Mini Histogram Widget (QPainter-based)
# ──────────────────────────────────────────────────────────────────────

class _MiniHistogram(QWidget):
    """Small histogram showing Monte Carlo completion-time distribution."""

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._bins: list[dict] = []
        self._max_count: int = 1
        self.setFixedHeight(90)
        self.setMinimumWidth(200)
        self.setSizePolicy(SP.Expanding, SP.Fixed)

    def set_distribution(self, bins: list[dict]) -> None:
        self._bins = bins or []
        self._max_count = max((b.get("count", 0) for b in self._bins), default=1) or 1
        self.update()

    def paintEvent(self, event: QPaintEvent) -> None:  # noqa: N802
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing, True)
        p.setRenderHint(QPainter.TextAntialiasing, True)

        w, h = self.width(), self.height()
        margin_bottom = 18
        margin_top = 6
        margin_lr = 4
        bar_area_h = h - margin_bottom - margin_top
        bar_area_w = w - margin_lr * 2

        if not self._bins:
            p.setPen(QPen(QColor(Palette.TEXT_TERTIARY)))
            p.setFont(QFont("Inter", 9))
            p.drawText(QRectF(0, 0, w, h), Qt.AlignCenter, "No simulation data")
            p.end()
            return

        n = len(self._bins)
        gap = 2
        bar_w = max(4, (bar_area_w - gap * (n - 1)) / n)

        # Gradient for bars
        for i, bin_data in enumerate(self._bins):
            count = bin_data.get("count", 0)
            frac = count / self._max_count if self._max_count else 0
            bar_h = max(2, frac * bar_area_h)
            x = margin_lr + i * (bar_w + gap)
            y = margin_top + bar_area_h - bar_h

            # Color: green → yellow → red based on position (earlier = greener)
            t = i / max(n - 1, 1)
            if t < 0.5:
                r = int(46 + t * 2 * (241 - 46))
                g = int(204 - t * 2 * (204 - 196))
                b = int(113 - t * 2 * (113 - 15))
            else:
                t2 = (t - 0.5) * 2
                r = int(241 + t2 * (231 - 241))
                g = int(196 - t2 * (196 - 76))
                b = int(15 + t2 * (60 - 15))

            bar_color = QColor(r, g, b, 200)
            p.setBrush(QBrush(bar_color))
            p.setPen(Qt.NoPen)
            p.drawRoundedRect(QRectF(x, y, bar_w, bar_h), 2, 2)

        # X-axis labels (first, mid, last)
        label_font = QFont("Inter", 7)
        p.setFont(label_font)
        p.setPen(QPen(QColor(Palette.TEXT_TERTIARY)))

        if n >= 1:
            first_label = str(self._bins[0].get("start", ""))
            p.drawText(QRectF(margin_lr, h - margin_bottom, bar_w + 10, margin_bottom),
                       Qt.AlignLeft | Qt.AlignTop, first_label)
        if n >= 2:
            mid = n // 2
            mid_label = str(self._bins[mid].get("start", ""))
            mid_x = margin_lr + mid * (bar_w + gap)
            p.drawText(QRectF(mid_x - 10, h - margin_bottom, bar_w + 20, margin_bottom),
                       Qt.AlignCenter | Qt.AlignTop, mid_label)
        if n >= 3:
            last_label = str(self._bins[-1].get("end", ""))
            last_x = margin_lr + (n - 1) * (bar_w + gap)
            p.drawText(QRectF(last_x - 10, h - margin_bottom, bar_w + 20, margin_bottom),
                       Qt.AlignRight | Qt.AlignTop, last_label)

        p.end()


# ──────────────────────────────────────────────────────────────────────
#  Helper: styled sub-card
# ──────────────────────────────────────────────────────────────────────

class _SubCard(QFrame):
    """A small card with background and border consistent with the theme."""

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setStyleSheet(f"""
            _SubCard, QFrame {{
                background-color: {Palette.BG_TERTIARY};
                border: 1px solid {Palette.BORDER_SUBTLE};
                border-radius: 8px;
            }}
        """)
        self.setFrameShape(QFrame.StyledPanel)


# ──────────────────────────────────────────────────────────────────────
#  Score Breakdown Row
# ──────────────────────────────────────────────────────────────────────

class _ScoreBar(QWidget):
    """A single metric bar: label | progress-bar | score/max."""

    def __init__(self, label: str, max_val: float,
                 parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._label = label
        self._max_val = max_val
        self._value: float = 0.0

        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 2, 0, 2)
        lay.setSpacing(8)

        self._name_lbl = QLabel(label)
        self._name_lbl.setFixedWidth(150)
        self._name_lbl.setStyleSheet(
            f"color: {Palette.TEXT_SECONDARY}; font-size: 11px; font-weight: 500; background: transparent;"
        )
        lay.addWidget(self._name_lbl)

        self._bar = QProgressBar()
        self._bar.setRange(0, int(max_val * 10))
        self._bar.setValue(0)
        self._bar.setTextVisible(False)
        self._bar.setFixedHeight(10)
        self._bar.setStyleSheet(f"""
            QProgressBar {{
                background-color: {Palette.BG_ELEVATED};
                border: 1px solid {Palette.BORDER_SUBTLE};
                border-radius: 5px;
            }}
            QProgressBar::chunk {{
                background-color: {Palette.GOLD_PRIMARY};
                border-radius: 4px;
            }}
        """)
        lay.addWidget(self._bar, 1)

        self._score_lbl = QLabel(f"0/{int(max_val)}")
        self._score_lbl.setFixedWidth(50)
        self._score_lbl.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        self._score_lbl.setStyleSheet(
            f"color: {Palette.TEXT_PRIMARY}; font-size: 11px; font-weight: 600; "
            f"font-family: 'JetBrains Mono', 'Menlo', monospace; background: transparent;"
        )
        lay.addWidget(self._score_lbl)

    def set_value(self, value: float) -> None:
        self._value = max(0.0, min(self._max_val, value))
        self._bar.setValue(int(self._value * 10))
        self._score_lbl.setText(f"{self._value:.0f}/{int(self._max_val)}")

        # Color the chunk based on percentage
        pct = self._value / self._max_val if self._max_val else 0
        if pct >= 0.7:
            color = "#27AE60"  # green
        elif pct >= 0.4:
            color = Palette.GOLD_PRIMARY  # gold
        elif pct >= 0.2:
            color = "#E67E22"  # orange
        else:
            color = Palette.STATUS_BLOCKED  # red

        self._bar.setStyleSheet(f"""
            QProgressBar {{
                background-color: {Palette.BG_ELEVATED};
                border: 1px solid {Palette.BORDER_SUBTLE};
                border-radius: 5px;
            }}
            QProgressBar::chunk {{
                background-color: {color};
                border-radius: 4px;
            }}
        """)


# ──────────────────────────────────────────────────────────────────────
#  Bottleneck Alert Card
# ──────────────────────────────────────────────────────────────────────

class _BottleneckCard(QFrame):
    """Card showing a single bottleneck step."""

    def __init__(self, step_id: str, title: str, reason: str,
                 parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setStyleSheet(f"""
            QFrame {{
                background-color: {Palette.BG_TERTIARY};
                border: 1px solid {Palette.STATUS_BLOCKED};
                border-left: 3px solid {Palette.STATUS_BLOCKED};
                border-radius: 6px;
            }}
        """)
        self.setFrameShape(QFrame.StyledPanel)

        lay = QVBoxLayout(self)
        lay.setContentsMargins(10, 8, 10, 8)
        lay.setSpacing(4)

        # Top row: icon + step ID
        top = QHBoxLayout()
        top.setSpacing(6)
        icon_lbl = QLabel("\U0001F534")  # red circle
        icon_lbl.setStyleSheet("background: transparent; font-size: 12px;")
        icon_lbl.setFixedSize(18, 18)
        top.addWidget(icon_lbl)

        id_lbl = QLabel(step_id)
        id_lbl.setStyleSheet(
            f"color: {Palette.STATUS_BLOCKED}; font-size: 10px; font-weight: 600; "
            f"font-family: 'JetBrains Mono', monospace; background: transparent;"
        )
        top.addWidget(id_lbl)
        top.addStretch()
        lay.addLayout(top)

        # Title
        title_lbl = QLabel(title)
        title_lbl.setWordWrap(True)
        title_lbl.setStyleSheet(
            f"color: {Palette.TEXT_PRIMARY}; font-size: 12px; font-weight: 600; background: transparent;"
        )
        lay.addWidget(title_lbl)

        # Reason
        reason_lbl = QLabel(reason)
        reason_lbl.setWordWrap(True)
        reason_lbl.setStyleSheet(
            f"color: {Palette.TEXT_SECONDARY}; font-size: 11px; background: transparent;"
        )
        lay.addWidget(reason_lbl)


# ──────────────────────────────────────────────────────────────────────
#  Main Dashboard Widget
# ──────────────────────────────────────────────────────────────────────

class RouteHealthDashboard(QFrame):
    """
    Route Health Dashboard — visual summary of a route's health.

    Sections:
      1. Circular gauge with overall score & grade
      2. Score breakdown (6 component bars)
      3. Bottleneck alert cards
      4. Recommendations list
      5. Monte Carlo simulation summary + histogram
      6. Action buttons
    """

    # ── Signals ──
    optimizeRequested = Signal()
    riskAnalysisRequested = Signal()
    simulationRequested = Signal()
    replanRequested = Signal()

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._health: Optional[RouteHealthReport] = None
        self._simulation: Optional[SimulationResult] = None
        self._route: Optional[Route] = None

        self.setFrameShape(QFrame.StyledPanel)
        self.setStyleSheet(f"""
            RouteHealthDashboard {{
                background-color: {Palette.BG_SECONDARY};
                border: 1px solid {Palette.BORDER_SUBTLE};
                border-radius: 10px;
            }}
        """)

        # ── Outer layout with scroll ──
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        self._scroll = QScrollArea()
        self._scroll.setWidgetResizable(True)
        self._scroll.setStyleSheet(f"""
            QScrollArea {{
                background-color: {Palette.BG_SECONDARY};
                border: none;
            }}
            QScrollBar:vertical {{
                background: transparent;
                width: 10px;
                margin: 0;
            }}
            QScrollBar::handle:vertical {{
                background: {Palette.BG_ELEVATED};
                border-radius: 4px;
                min-height: 20px;
                margin: 1px;
            }}
            QScrollBar::handle:vertical:hover {{
                background: {Palette.BORDER_GOLD};
            }}
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
                height: 0;
            }}
        """)

        self._container = QWidget()
        self._container.setStyleSheet(f"background-color: {Palette.BG_SECONDARY};")

        self._main_layout = QVBoxLayout(self._container)
        self._main_layout.setContentsMargins(20, 18, 20, 20)
        self._main_layout.setSpacing(16)

        self._build_header()
        self._build_gauge_section()
        self._build_breakdown_section()
        self._build_bottleneck_section()
        self._build_recommendations_section()
        self._build_simulation_section()
        self._build_action_buttons()

        self._main_layout.addStretch(1)

        self._scroll.setWidget(self._container)
        outer.addWidget(self._scroll)

    # ──────────── Section builders ────────────

    def _section_title(self, text: str, icon: str = "") -> QLabel:
        lbl = QLabel(f"{icon}  {text}" if icon else text)
        lbl.setStyleSheet(
            f"color: {Palette.GOLD_PRIMARY}; font-size: 12px; font-weight: 700; "
            f"text-transform: uppercase; letter-spacing: 1.2px; background: transparent; "
            f"padding-bottom: 4px; border-bottom: 1px solid {Palette.BORDER_SUBTLE};"
        )
        return lbl

    def _build_header(self) -> None:
        hdr = QHBoxLayout()
        hdr.setSpacing(8)

        title = QLabel("Route Health Dashboard")
        title.setStyleSheet(
            f"color: {Palette.GOLD_BRIGHT}; font-size: 18px; font-weight: 700; "
            f"letter-spacing: 0.5px; background: transparent;"
        )
        hdr.addWidget(title)
        hdr.addStretch()

        self._route_goal_lbl = QLabel("")
        self._route_goal_lbl.setWordWrap(True)
        self._route_goal_lbl.setStyleSheet(
            f"color: {Palette.TEXT_TERTIARY}; font-size: 11px; "
            f"font-style: italic; background: transparent; max-width: 300px;"
        )
        self._route_goal_lbl.setMaximumWidth(300)
        hdr.addWidget(self._route_goal_lbl)

        self._main_layout.addLayout(hdr)

    def _build_gauge_section(self) -> None:
        row = QHBoxLayout()
        row.setSpacing(24)

        # Gauge
        self._gauge = _CircularGauge()
        row.addWidget(self._gauge, 0, Qt.AlignCenter)

        # Summary text to the right of gauge
        summary_col = QVBoxLayout()
        summary_col.setSpacing(6)

        self._score_summary_lbl = QLabel("No health data")
        self._score_summary_lbl.setWordWrap(True)
        self._score_summary_lbl.setStyleSheet(
            f"color: {Palette.TEXT_SECONDARY}; font-size: 12px; background: transparent;"
        )
        summary_col.addWidget(self._score_summary_lbl)

        self._steps_count_lbl = QLabel("")
        self._steps_count_lbl.setStyleSheet(
            f"color: {Palette.TEXT_TERTIARY}; font-size: 11px; background: transparent;"
        )
        summary_col.addWidget(self._steps_count_lbl)

        self._prob_avg_lbl = QLabel("")
        self._prob_avg_lbl.setStyleSheet(
            f"color: {Palette.TEXT_TERTIARY}; font-size: 11px; background: transparent;"
        )
        summary_col.addWidget(self._prob_avg_lbl)

        summary_col.addStretch()
        row.addLayout(summary_col, 1)

        self._main_layout.addWidget(self._section_title("Overall Health", "\U0001F3AF"))
        self._main_layout.addLayout(row)

    def _build_breakdown_section(self) -> None:
        self._main_layout.addWidget(self._section_title("Score Breakdown", "\U0001F4CA"))

        breakdown_card = QFrame()
        breakdown_card.setStyleSheet(f"""
            QFrame {{
                background-color: {Palette.BG_TERTIARY};
                border: 1px solid {Palette.BORDER_SUBTLE};
                border-radius: 8px;
            }}
        """)
        breakdown_card.setFrameShape(QFrame.StyledPanel)
        blay = QVBoxLayout(breakdown_card)
        blay.setContentsMargins(14, 12, 14, 12)
        blay.setSpacing(6)

        self._prob_bar = _ScoreBar("Probability Score", 40)
        self._fallback_bar = _ScoreBar("Fallback Coverage", 15)
        self._risk_bar = _ScoreBar("Risk Score", 15)
        self._branch_bar = _ScoreBar("Branch Complexity", 12)
        self._kind_bar = _ScoreBar("Step Kind Variety", 10)
        self._dep_bar = _ScoreBar("Dependency Health", 10)

        blay.addWidget(self._prob_bar)
        blay.addWidget(self._fallback_bar)
        blay.addWidget(self._risk_bar)
        blay.addWidget(self._branch_bar)
        blay.addWidget(self._kind_bar)
        blay.addWidget(self._dep_bar)

        self._main_layout.addWidget(breakdown_card)

    def _build_bottleneck_section(self) -> None:
        self._bottleneck_title = self._section_title("Bottleneck Alerts", "\U0001F6A8")
        self._main_layout.addWidget(self._bottleneck_title)

        self._bottleneck_container = QVBoxLayout()
        self._bottleneck_container.setSpacing(8)

        self._no_bottleneck_lbl = QLabel("No bottlenecks detected \u2705")
        self._no_bottleneck_lbl.setStyleSheet(
            f"color: {Palette.STATUS_DONE}; font-size: 12px; padding: 8px; background: transparent;"
        )
        self._bottleneck_container.addWidget(self._no_bottleneck_lbl)

        self._main_layout.addLayout(self._bottleneck_container)

    def _build_recommendations_section(self) -> None:
        self._main_layout.addWidget(self._section_title("Recommendations", "\U0001F4A1"))

        self._rec_card = QFrame()
        self._rec_card.setStyleSheet(f"""
            QFrame {{
                background-color: {Palette.BG_TERTIARY};
                border: 1px solid {Palette.BORDER_SUBTLE};
                border-radius: 8px;
            }}
        """)
        self._rec_card.setFrameShape(QFrame.StyledPanel)
        self._rec_lay = QVBoxLayout(self._rec_card)
        self._rec_lay.setContentsMargins(14, 12, 14, 12)
        self._rec_lay.setSpacing(6)

        self._no_rec_lbl = QLabel("Run a health check to see recommendations.")
        self._no_rec_lbl.setStyleSheet(
            f"color: {Palette.TEXT_TERTIARY}; font-size: 11px; background: transparent;"
        )
        self._rec_lay.addWidget(self._no_rec_lbl)

        self._main_layout.addWidget(self._rec_card)

    def _build_simulation_section(self) -> None:
        self._main_layout.addWidget(self._section_title("Monte Carlo Simulation", "\U0001F3B2"))

        sim_card = QFrame()
        sim_card.setStyleSheet(f"""
            QFrame {{
                background-color: {Palette.BG_TERTIARY};
                border: 1px solid {Palette.BORDER_SUBTLE};
                border-radius: 8px;
            }}
        """)
        sim_card.setFrameShape(QFrame.StyledPanel)
        slay = QVBoxLayout(sim_card)
        slay.setContentsMargins(14, 12, 14, 12)
        slay.setSpacing(10)

        # Percentile grid
        pct_grid = QGridLayout()
        pct_grid.setSpacing(8)

        self._p50_lbl = self._make_stat_label("P50", "--")
        self._p75_lbl = self._make_stat_label("P75", "--")
        self._p90_lbl = self._make_stat_label("P90", "--")
        self._p99_lbl = self._make_stat_label("P99", "--")
        self._fail_lbl = self._make_stat_label("Fail %", "--")

        pct_grid.addWidget(self._p50_lbl[0], 0, 0)
        pct_grid.addWidget(self._p50_lbl[1], 1, 0)
        pct_grid.addWidget(self._p75_lbl[0], 0, 1)
        pct_grid.addWidget(self._p75_lbl[1], 1, 1)
        pct_grid.addWidget(self._p90_lbl[0], 0, 2)
        pct_grid.addWidget(self._p90_lbl[1], 1, 2)
        pct_grid.addWidget(self._p99_lbl[0], 0, 3)
        pct_grid.addWidget(self._p99_lbl[1], 1, 3)
        pct_grid.addWidget(self._fail_lbl[0], 0, 4)
        pct_grid.addWidget(self._fail_lbl[1], 1, 4)

        slay.addLayout(pct_grid)

        # Histogram
        self._histogram = _MiniHistogram()
        slay.addWidget(self._histogram)

        # Sim runs info
        self._sim_info_lbl = QLabel("No simulation has been run yet.")
        self._sim_info_lbl.setStyleSheet(
            f"color: {Palette.TEXT_TERTIARY}; font-size: 10px; background: transparent;"
        )
        slay.addWidget(self._sim_info_lbl)

        self._main_layout.addWidget(sim_card)

    def _make_stat_label(self, title: str, value: str) -> tuple[QLabel, QLabel]:
        """Return (title_label, value_label) for a stat box."""
        t = QLabel(title)
        t.setAlignment(Qt.AlignCenter)
        t.setStyleSheet(
            f"color: {Palette.TEXT_TERTIARY}; font-size: 9px; font-weight: 700; "
            f"letter-spacing: 0.8px; background: transparent;"
        )
        v = QLabel(value)
        v.setAlignment(Qt.AlignCenter)
        v.setStyleSheet(
            f"color: {Palette.GOLD_BRIGHT}; font-size: 16px; font-weight: 700; "
            f"font-family: 'JetBrains Mono', monospace; background: transparent;"
        )
        return t, v

    def _build_action_buttons(self) -> None:
        self._main_layout.addWidget(self._section_title("Actions", "\u2699\uFE0F"))

        btn_row = QHBoxLayout()
        btn_row.setSpacing(10)

        self._sim_btn = self._make_action_button(
            "\U0001F3B2  Run Monte Carlo Simulation", primary=True
        )
        self._sim_btn.setToolTip("Run 5,000 Monte Carlo simulations to estimate completion time and failure rate")
        self._sim_btn.clicked.connect(self.simulationRequested.emit)
        btn_row.addWidget(self._sim_btn)

        self._opt_btn = self._make_action_button(
            "\u2728  AI Optimize Route", primary=False
        )
        self._opt_btn.setToolTip("Ask AI to optimize the route for better health and resilience")
        self._opt_btn.clicked.connect(self.optimizeRequested.emit)
        btn_row.addWidget(self._opt_btn)

        self._risk_btn = self._make_action_button(
            "\U0001F6A8  AI Risk Analysis", primary=False
        )
        self._risk_btn.setToolTip("Ask AI to analyze and mitigate risks in the route")
        self._risk_btn.clicked.connect(self.riskAnalysisRequested.emit)
        btn_row.addWidget(self._risk_btn)

        self._replan_btn = self._make_action_button(
            "\U0001F504  AI Smart Re-plan", primary=False
        )
        self._replan_btn.setToolTip("Ask AI to re-plan the route with improved structure")
        self._replan_btn.clicked.connect(self.replanRequested.emit)
        btn_row.addWidget(self._replan_btn)

        self._main_layout.addLayout(btn_row)

    def _make_action_button(self, text: str, primary: bool = False) -> QPushButton:
        btn = QPushButton(text)
        btn.setFixedHeight(38)
        btn.setSizePolicy(SP.Expanding, SP.Fixed)
        if primary:
            btn.setProperty("variant", "primary")
        btn.setStyleSheet(
            f"""
            QPushButton {{
                background-color: {Palette.GOLD_PRIMARY if primary else Palette.BG_ELEVATED};
                color: {Palette.TEXT_ON_GOLD if primary else Palette.TEXT_PRIMARY};
                border: 1px solid {Palette.GOLD_DEEP if primary else Palette.BORDER_NORMAL};
                border-radius: 6px;
                padding: 8px 14px;
                font-size: 12px;
                font-weight: 600;
            }}
            QPushButton:hover {{
                background-color: {Palette.GOLD_BRIGHT if primary else Palette.BG_HOVER};
                border: 1px solid {Palette.GOLD_PRIMARY if primary else Palette.BORDER_GOLD};
                color: {Palette.TEXT_ON_GOLD if primary else Palette.GOLD_BRIGHT};
            }}
            QPushButton:pressed {{
                background-color: {Palette.GOLD_DEEP if primary else Palette.BG_TERTIARY};
            }}
            """
        )
        return btn

    # ──────────── Public API ────────────

    def set_route(self, route: Route) -> None:
        """Set the current route for context."""
        self._route = route
        if route:
            goal = route.goal or ""
            elided = goal[:60] + ("..." if len(goal) > 60 else "")
            self._route_goal_lbl.setText(elided)
            self._route_goal_lbl.setToolTip(goal)
        else:
            self._route_goal_lbl.setText("")

    def update_health(self, health: RouteHealthReport) -> None:
        """Refresh the entire dashboard from a health report."""
        self._health = health
        if health is None:
            return

        # ── Gauge ──
        self._gauge.set_score(health.overall_score, health.grade)

        # ── Summary text ──
        score_desc = self._describe_score(health.overall_score)
        self._score_summary_lbl.setText(
            f"Overall Score: <b>{health.overall_score:.0f}</b>/100 — {score_desc}"
        )

        m = health.metrics
        n_steps = len(self._route.steps) if self._route else 0
        self._steps_count_lbl.setText(
            f"Steps: {n_steps}  |  Branches: {m.get('n_branches', 0)}  |  "
            f"Kinds: {m.get('n_kinds', 0)}"
        )
        self._prob_avg_lbl.setText(
            f"Avg Probability: {m.get('avg_success_probability', 0):.0%}  |  "
            f"Fallback Coverage: {m.get('fallback_coverage_pct', 0):.0%}"
        )

        # ── Breakdown bars ──
        self._prob_bar.set_value(m.get("prob_score", 0))
        self._fallback_bar.set_value(m.get("fallback_score", 0))
        self._risk_bar.set_value(m.get("risk_score", 0))
        self._branch_bar.set_value(m.get("branch_score", 0))
        self._kind_bar.set_value(m.get("kind_score", 0))
        self._dep_bar.set_value(m.get("dep_score", 0))

        # ── Bottleneck cards ──
        self._rebuild_bottlenecks(health)

        # ── Recommendations ──
        self._rebuild_recommendations(health.recommendations)

    def update_simulation(self, result: SimulationResult) -> None:
        """Show Monte Carlo simulation results."""
        self._simulation = result
        if result is None:
            return

        # Percentile labels
        self._p50_lbl[1].setText(f"{result.p50_minutes}m")
        self._p75_lbl[1].setText(f"{result.p75_minutes}m")
        self._p90_lbl[1].setText(f"{result.p90_minutes}m")
        self._p99_lbl[1].setText(f"{result.p99_minutes}m")

        # Failure rate — color-coded
        fail_pct = result.failure_rate * 100
        fail_text = f"{fail_pct:.1f}%"
        self._fail_lbl[1].setText(fail_text)
        if fail_pct > 20:
            self._fail_lbl[1].setStyleSheet(
                f"color: {Palette.STATUS_BLOCKED}; font-size: 16px; font-weight: 700; "
                f"font-family: 'JetBrains Mono', monospace; background: transparent;"
            )
        elif fail_pct > 5:
            self._fail_lbl[1].setStyleSheet(
                f"color: #E67E22; font-size: 16px; font-weight: 700; "
                f"font-family: 'JetBrains Mono', monospace; background: transparent;"
            )
        else:
            self._fail_lbl[1].setStyleSheet(
                f"color: #27AE60; font-size: 16px; font-weight: 700; "
                f"font-family: 'JetBrains Mono', monospace; background: transparent;"
            )

        # Histogram
        self._histogram.set_distribution(result.completion_time_distribution)

        # Info
        self._sim_info_lbl.setText(
            f"Based on {result.n_simulations:,} simulations  |  "
            f"Mean: {result.mean_minutes:.0f}m  |  "
            f"Range: {result.min_minutes}m – {result.max_minutes}m"
        )

    # ──────────── Internals ────────────

    def _describe_score(self, score: float) -> str:
        if score >= 90:
            return "Excellent — route is robust and well-structured"
        elif score >= 80:
            return "Good — minor issues to address"
        elif score >= 70:
            return "Fair — some risks present"
        elif score >= 60:
            return "Moderate — improvements recommended"
        elif score >= 50:
            return "Poor — significant issues found"
        else:
            return "Critical — route is likely to fail"

    def _rebuild_bottlenecks(self, health: RouteHealthReport) -> None:
        # Remove old bottleneck widgets
        while self._bottleneck_container.count():
            item = self._bottleneck_container.takeAt(0)
            w = item.widget()
            if w:
                w.deleteLater()

        bottlenecks = health.bottlenecks
        if not bottlenecks:
            lbl = QLabel("No bottlenecks detected \u2705")
            lbl.setStyleSheet(
                f"color: {Palette.STATUS_DONE}; font-size: 12px; padding: 8px; background: transparent;"
            )
            self._bottleneck_container.addWidget(lbl)
            return

        # Build a step lookup from the route
        step_map: dict[str, 'RouteStep'] = {}
        if self._route:
            step_map = {s.id: s for s in self._route.steps}

        # Count dependents for each step
        dependents_count: dict[str, int] = {}
        if self._route:
            for edge in self._route.edges:
                dependents_count[edge.source_id] = dependents_count.get(edge.source_id, 0) + 1

        for bn_id in bottlenecks:
            step = step_map.get(bn_id)
            title = step.title if step else bn_id
            reasons = []
            if step:
                if step.success_probability < 0.4:
                    reasons.append(f"Very low success probability ({step.success_probability:.0%})")
                elif step.success_probability < 0.6:
                    reasons.append(f"Low success probability ({step.success_probability:.0%})")
                n_deps = dependents_count.get(bn_id, 0)
                if n_deps >= 2:
                    reasons.append(f"{n_deps} other steps depend on this step")
                if step.risk_level in ("high", "severe"):
                    reasons.append(f"High risk level ({step.risk_level})")
                if not step.fallback:
                    reasons.append("No fallback plan defined")

            reason_text = "; ".join(reasons) if reasons else "Bottleneck detected"
            card = _BottleneckCard(bn_id, title, reason_text)
            self._bottleneck_container.addWidget(card)

    def _rebuild_recommendations(self, recommendations: list[str]) -> None:
        # Remove old rec widgets
        while self._rec_lay.count():
            item = self._rec_lay.takeAt(0)
            w = item.widget()
            if w:
                w.deleteLater()

        if not recommendations:
            lbl = QLabel("No recommendations yet.")
            lbl.setStyleSheet(
                f"color: {Palette.TEXT_TERTIARY}; font-size: 11px; background: transparent;"
            )
            self._rec_lay.addWidget(lbl)
            return

        for rec in recommendations:
            # Use bullet point
            bullet = QLabel(f"\u2022  {rec}")
            bullet.setWordWrap(True)
            bullet.setStyleSheet(
                f"color: {Palette.TEXT_SECONDARY}; font-size: 12px; "
                f"padding: 3px 0; background: transparent; line-height: 1.4;"
            )
            self._rec_lay.addWidget(bullet)

    def sizeHint(self) -> QSize:  # noqa: N802
        return QSize(520, 900)

    def minimumSizeHint(self) -> QSize:  # noqa: N802
        return QSize(400, 600)
