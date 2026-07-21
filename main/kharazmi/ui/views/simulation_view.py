"""
SimulationView — dedicated simulation & health analysis page for RASK! routes.

Runs Monte Carlo simulations, shows:
  - Where the route succeeds/fails
  - Per-step failure analysis
  - Completion time distribution histogram
  - Recommendations for improvement
  - How to fix the weak points
"""
from __future__ import annotations

import math
from typing import Optional

from PySide6.QtCore import Qt, QRectF, Signal, QTimer
from PySide6.QtGui import (
    QPainter, QPainterPath, QColor, QPen, QBrush, QFont,
    QLinearGradient, QRadialGradient, QFontMetrics,
)
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QFrame,
    QScrollArea, QSizePolicy, QProgressBar, QGridLayout, QSplitter,
)

from ...ai import Route, MonteCarloSimulator, SimulationResult, RouteHealthEngine, RouteHealthReport
from ..theme import Palette


# ──────────────────────────────────────────────────────────────────────
#  Histogram Widget (custom QPainter)
# ──────────────────────────────────────────────────────────────────────

class _HistogramWidget(QWidget):
    """Custom-painted histogram showing completion time distribution."""

    def __init__(self, result: SimulationResult, parent=None):
        super().__init__(parent)
        self.result = result
        self.setFixedHeight(200)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing, True)
        p.setRenderHint(QPainter.TextAntialiasing, True)

        w, h = self.width(), self.height()
        hist = self.result.histogram
        if not hist:
            p.setPen(QColor(Palette.TEXT_TERTIARY))
            p.setFont(QFont("Inter", 11))
            p.drawText(self.rect(), Qt.AlignCenter, "No histogram data")
            p.end()
            return

        title_font = QFont("Inter", 10, QFont.Bold)
        p.setFont(title_font)
        p.setPen(QColor(Palette.GOLD_BRIGHT))
        p.drawText(10, 16, "Completion Time Distribution")

        max_count = max(hist.values()) if hist else 1
        bar_area_y = 36
        bar_area_h = h - 70
        bar_area_w = w - 60
        label_w = 50

        sorted_bins = sorted(hist.keys())
        if not sorted_bins:
            p.end()
            return

        n_bins = len(sorted_bins)
        bar_w = max(4, bar_area_w // n_bins - 2)
        x = label_w

        for bin_val in sorted_bins:
            count = hist[bin_val]
            bar_h = max(2, int(bar_area_h * count / max_count))

            # Color gradient based on position (earlier = green, later = red)
            pct = sorted_bins.index(bin_val) / max(1, n_bins - 1)
            if pct < 0.33:
                color = QColor("#5A8A5A")
            elif pct < 0.66:
                color = QColor("#D4AF37")
            else:
                color = QColor("#A87A4A")

            p.setPen(Qt.NoPen)
            p.setBrush(color)
            p.drawRoundedRect(QRectF(x, bar_area_y + bar_area_h - bar_h, bar_w, bar_h), 2, 2)

            # Bin label (every few bins)
            if n_bins <= 20 or sorted_bins.index(bin_val) % max(1, n_bins // 10) == 0:
                p.setFont(QFont("JetBrains Mono", 7))
                p.setPen(QColor(Palette.TEXT_TERTIARY))
                p.drawText(QRectF(x - 10, bar_area_y + bar_area_h + 4, bar_w + 20, 14),
                           Qt.AlignCenter, f"{bin_val}m")

            x += bar_w + 2

        # X-axis line
        p.setPen(QPen(QColor(Palette.BORDER_NORMAL), 1))
        p.drawLine(label_w, bar_area_y + bar_area_h, w - 10, bar_area_y + bar_area_h)

        p.end()


# ──────────────────────────────────────────────────────────────────────
#  Step Failure Analysis Widget
# ──────────────────────────────────────────────────────────────────────

class _StepFailureWidget(QWidget):
    """Shows per-step failure rates with visual bars."""

    def __init__(self, result: SimulationResult, route: Route, parent=None):
        super().__init__(parent)
        self.result = result
        self.route = route
        self.setMinimumHeight(max(200, len(route.steps) * 28 + 50))
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing, True)
        p.setRenderHint(QPainter.TextAntialiasing, True)

        w, h = self.width(), self.height()
        step_failures = self.result.step_failure_counts
        steps = self.route.steps
        if not steps:
            p.end()
            return

        title_font = QFont("Inter", 10, QFont.Bold)
        p.setFont(title_font)
        p.setPen(QColor(Palette.GOLD_BRIGHT))
        p.drawText(10, 16, "Step Failure Analysis")

        bar_h = min(22, max(14, (h - 50) // len(steps) - 4))
        label_w = 160
        bar_area = w - label_w - 80
        y = 30

        # Sort steps by failure count (highest first)
        sorted_steps = sorted(steps, key=lambda s: step_failures.get(s.id, 0), reverse=True)

        for step in sorted_steps:
            fail_count = step_failures.get(step.id, 0)
            fail_rate = fail_count / max(1, self.result.n_simulations)

            # Label
            p.setFont(QFont("Inter", 9))
            p.setPen(QColor(Palette.TEXT_SECONDARY))
            label = step.title[:20] + "…" if len(step.title) > 20 else step.title
            p.drawText(QRectF(4, y, label_w - 8, bar_h), Qt.AlignRight | Qt.AlignVCenter, label)

            # Background
            p.setPen(Qt.NoPen)
            p.setBrush(QColor(Palette.BG_TERTIARY))
            p.drawRoundedRect(QRectF(label_w, y + 2, bar_area, bar_h - 4), 3, 3)

            # Failure bar (red)
            bar_fill_w = bar_area * fail_rate
            if fail_rate > 0.3:
                color = QColor("#A85A5A")
            elif fail_rate > 0.15:
                color = QColor("#A87A4A")
            else:
                color = QColor("#5A8A5A")

            grad = QLinearGradient(label_w, 0, label_w + bar_fill_w, 0)
            grad.setColorAt(0, color)
            grad.setColorAt(1, color.lighter(120))
            p.setBrush(QBrush(grad))
            p.drawRoundedRect(QRectF(label_w, y + 2, bar_fill_w, bar_h - 4), 3, 3)

            # Value
            p.setFont(QFont("JetBrains Mono", 9, QFont.Bold))
            p.setPen(QColor(Palette.TEXT_PRIMARY))
            p.drawText(QRectF(label_w + bar_area + 4, y, 70, bar_h),
                       Qt.AlignLeft | Qt.AlignVCenter, f"{fail_rate:.1%} ({fail_count})")

            y += bar_h + 4

        p.end()


# ──────────────────────────────────────────────────────────────────────
#  Circular Score Gauge (reused from health dashboard)
# ──────────────────────────────────────────────────────────────────────

class _CircularGauge(QWidget):
    """Circular gauge showing a 0-100 score."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._score = 0.0
        self._label = ""
        self.setFixedSize(180, 180)

    def set_score(self, score: float, label: str = ""):
        self._score = max(0, min(100, score))
        self._label = label
        self.update()

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing, True)

        cx, cy, r = 90, 85, 70
        pen_w = 10

        # Background arc
        p.setPen(QPen(QColor(Palette.BG_TERTIARY), pen_w, Qt.SolidLine, Qt.RoundCap))
        arc_rect = QRectF(cx - r, cy - r, r * 2, r * 2)
        p.drawArc(arc_rect, 135 * 16, 270 * 16)

        # Foreground arc (score)
        score_pct = self._score / 100.0
        if score_pct > 0.7:
            arc_color = QColor("#5A8A5A")
        elif score_pct > 0.4:
            arc_color = QColor("#D4AF37")
        else:
            arc_color = QColor("#A85A5A")

        p.setPen(QPen(arc_color, pen_w, Qt.SolidLine, Qt.RoundCap))
        span = int(270 * 16 * score_pct)
        p.drawArc(arc_rect, 135 * 16, span)

        # Center text
        p.setFont(QFont("Inter", 28, QFont.Bold))
        p.setPen(QColor(Palette.TEXT_PRIMARY))
        p.drawText(QRectF(cx - 50, cy - 18, 100, 36), Qt.AlignCenter, f"{self._score:.0f}")

        p.setFont(QFont("Inter", 9))
        p.setPen(QColor(Palette.TEXT_TERTIARY))
        p.drawText(QRectF(cx - 60, cy + 20, 120, 18), Qt.AlignCenter, self._label)

        p.end()


# ──────────────────────────────────────────────────────────────────────
#  Main SimulationView
# ──────────────────────────────────────────────────────────────────────

class SimulationView(QWidget):
    """
    Full-page simulation & health analysis for RASK! routes.

    Runs Monte Carlo simulations, shows:
      - Overall health gauge
      - Where the route fails (per-step failure analysis)
      - Where it succeeds
      - Completion time distribution
      - Recommendations for improvement
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self._route: Optional[Route] = None
        self._sim_result: Optional[SimulationResult] = None
        self._health: Optional[RouteHealthReport] = None
        self._build_ui()

    def _build_ui(self):
        self.setStyleSheet(f"background-color: {Palette.BG_PRIMARY};")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # Top bar
        top = QFrame()
        top.setFixedHeight(50)
        top.setStyleSheet(f"background-color: {Palette.BG_SECONDARY}; border-bottom: 1px solid {Palette.BORDER_SUBTLE};")
        top_layout = QHBoxLayout(top)
        top_layout.setContentsMargins(16, 8, 16, 8)

        title = QLabel("🧪  SIMULATION & HEALTH")
        title.setStyleSheet(
            f"color: {Palette.GOLD_BRIGHT}; font-size: 14px; font-weight: bold; "
            f"letter-spacing: 2px; background: transparent;"
        )
        top_layout.addWidget(title)

        self._route_info = QLabel("No route loaded")
        self._route_info.setStyleSheet(
            f"color: {Palette.TEXT_TERTIARY}; font-size: 11px; background: transparent;"
        )
        top_layout.addWidget(self._route_info)
        top_layout.addStretch()

        self._run_btn = QPushButton("▶  Run Simulation (5,000 runs)")
        self._run_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: {Palette.GOLD_PRIMARY};
                color: {Palette.TEXT_ON_GOLD};
                border: none;
                border-radius: 4px;
                padding: 8px 18px;
                font-size: 12px;
                font-weight: bold;
            }}
            QPushButton:hover {{
                background-color: {Palette.GOLD_BRIGHT};
            }}
            QPushButton:disabled {{
                background-color: {Palette.BG_TERTIARY};
                color: {Palette.TEXT_TERTIARY};
            }}
        """)
        self._run_btn.clicked.connect(self._run_simulation)
        self._run_btn.setEnabled(False)
        top_layout.addWidget(self._run_btn)

        layout.addWidget(top)

        # Scroll area for content
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet(f"""
            QScrollArea {{ background: {Palette.BG_PRIMARY}; border: none; }}
            QScrollBar:vertical {{ background: {Palette.BG_TERTIARY}; width: 8px; }}
            QScrollBar::handle:vertical {{ background: {Palette.BORDER_NORMAL}; border-radius: 4px; }}
        """)

        self._content = QWidget()
        self._content_layout = QVBoxLayout(self._content)
        self._content_layout.setContentsMargins(20, 16, 20, 20)
        self._content_layout.setSpacing(16)

        # Placeholder
        self._placeholder = QLabel(
            "Run a simulation to see detailed analysis.\n\n"
            "The simulation will:\n"
            "  • Run your route 5,000 times\n"
            "  • Show where it fails and where it succeeds\n"
            "  • Calculate realistic time estimates\n"
            "  • Give you concrete recommendations\n\n"
            "Go to the Planner tab and generate a route first."
        )
        self._placeholder.setStyleSheet(
            f"color: {Palette.TEXT_TERTIARY}; font-size: 13px; background: transparent; padding: 40px;"
        )
        self._placeholder.setAlignment(Qt.AlignCenter)
        self._content_layout.addWidget(self._placeholder)

        scroll.setWidget(self._content)
        layout.addWidget(scroll, stretch=1)

    def set_route(self, route: Route):
        self._route = route
        self._route_info.setText(
            f"{len(route.steps)} steps · {route.total_duration_minutes}m · "
            f"{route.overall_success_probability:.0%} success"
        )
        self._run_btn.setEnabled(True)

        # Auto-compute health
        self._health = RouteHealthEngine.compute(route)
        self._show_results()

    def _run_simulation(self):
        if not self._route:
            return

        self._run_btn.setEnabled(False)
        self._run_btn.setText("⏳  Running simulation…")
        QApplication.processEvents()

        try:
            sim = MonteCarloSimulator(self._route, n_simulations=5000)
            self._sim_result = sim.run()
        except Exception as e:
            self._run_btn.setText("▶  Run Simulation (5,000 runs)")
            self._run_btn.setEnabled(True)
            return

        self._run_btn.setText("▶  Re-run Simulation (5,000 runs)")
        self._run_btn.setEnabled(True)
        self._show_results()

    def _show_results(self):
        # Clear placeholder / existing content
        while self._content_layout.count():
            item = self._content_layout.takeAt(0)
            w = item.widget()
            if w:
                w.deleteLater()

        if not self._route:
            return

        # ---- Row 1: Gauge + Percentiles ----
        row1 = QHBoxLayout()
        row1.setSpacing(16)

        # Health gauge
        gauge_card = self._card()
        gauge_layout = QHBoxLayout(gauge_card)
        gauge_layout.setContentsMargins(16, 16, 16, 16)

        self._gauge = _CircularGauge()
        health_score = self._health.overall_score * 100 if self._health else 50
        self._gauge.set_score(health_score, "Health Score")
        gauge_layout.addWidget(self._gauge)

        # Percentile stats
        stats_widget = QWidget()
        stats_layout = QVBoxLayout(stats_widget)
        stats_layout.setContentsMargins(16, 0, 0, 0)
        stats_layout.setSpacing(8)

        stats_layout.addWidget(QLabel("<b style='color: #D4AF37; font-size: 13px;'>Simulation Results</b>"))

        if self._sim_result:
            for label, value, color in [
                ("P50 (median)", f"{self._sim_result.p50_minutes}m", Palette.TEXT_PRIMARY),
                ("P75", f"{self._sim_result.p75_minutes}m", Palette.TEXT_PRIMARY),
                ("P90", f"{self._sim_result.p90_minutes}m", Palette.GOLD_PRIMARY),
                ("P99", f"{self._sim_result.p99_minutes}m", Palette.GOLD_BRIGHT),
                ("Failure Rate", f"{self._sim_result.failure_rate:.1%}",
                 "#A85A5A" if self._sim_result.failure_rate > 0.3 else "#5A8A5A"),
                ("Min / Max", f"{self._sim_result.min_minutes}m / {self._sim_result.max_minutes}m", Palette.TEXT_SECONDARY),
            ]:
                row = QHBoxLayout()
                l = QLabel(label)
                l.setStyleSheet(f"color: {Palette.TEXT_TERTIARY}; font-size: 11px; background: transparent;")
                row.addWidget(l)
                row.addStretch()
                v = QLabel(value)
                v.setStyleSheet(f"color: {color}; font-size: 13px; font-weight: bold; background: transparent;")
                row.addWidget(v)
                stats_layout.addLayout(row)
        else:
            stats_layout.addWidget(QLabel("Run simulation to see percentile estimates"))

        gauge_layout.addWidget(stats_widget, stretch=1)
        row1.addWidget(gauge_card)
        self._content_layout.addLayout(row1)

        # ---- Row 2: Success vs Failure Summary ----
        row2 = QHBoxLayout()
        row2.setSpacing(12)

        if self._sim_result:
            success_rate = 1.0 - self._sim_result.failure_rate
            fail_rate = self._sim_result.failure_rate

            # Success card
            success_card = self._status_card(
                "✅ Where It Succeeds",
                f"{success_rate:.0%} of simulations complete successfully",
                self._get_succeeding_steps(),
                "#5A8A5A",
            )
            row2.addWidget(success_card, stretch=1)

            # Failure card
            fail_card = self._status_card(
                "❌ Where It Fails",
                f"{fail_rate:.0%} of simulations hit a failure",
                self._get_failing_steps(),
                "#A85A5A",
            )
            row2.addWidget(fail_card, stretch=1)
        else:
            no_sim = QLabel("Run simulation to see success/failure analysis")
            no_sim.setStyleSheet(f"color: {Palette.TEXT_TERTIARY}; font-size: 12px; padding: 20px;")
            row2.addWidget(no_sim)

        self._content_layout.addLayout(row2)

        # ---- Row 3: Step Failure Analysis ----
        if self._sim_result:
            fail_card = self._card()
            fail_cl = QVBoxLayout(fail_card)
            fail_cl.setContentsMargins(0, 0, 0, 0)
            fail_cl.addWidget(_StepFailureWidget(self._sim_result, self._route))
            self._content_layout.addWidget(fail_card)

        # ---- Row 4: Histogram ----
        if self._sim_result:
            hist_card = self._card()
            hist_cl = QVBoxLayout(hist_card)
            hist_cl.setContentsMargins(0, 0, 0, 0)
            hist_cl.addWidget(_HistogramWidget(self._sim_result))
            self._content_layout.addWidget(hist_card)

        # ---- Row 5: Recommendations ----
        rec_card = self._card()
        rec_cl = QVBoxLayout(rec_card)
        rec_cl.setContentsMargins(16, 12, 16, 12)
        rec_cl.setSpacing(8)

        rec_title = QLabel("💡  How to Improve")
        rec_title.setStyleSheet(f"color: {Palette.GOLD_BRIGHT}; font-size: 13px; font-weight: bold; background: transparent;")
        rec_cl.addWidget(rec_title)

        for rec in self._get_recommendations():
            rl = QLabel(f"• {rec}")
            rl.setStyleSheet(f"color: {Palette.TEXT_SECONDARY}; font-size: 11px; background: transparent;")
            rl.setWordWrap(True)
            rec_cl.addWidget(rl)

        self._content_layout.addWidget(rec_card)

        self._content_layout.addStretch()

    def _card(self) -> QFrame:
        card = QFrame()
        card.setStyleSheet(f"""
            QFrame {{
                background-color: {Palette.BG_SECONDARY};
                border: 1px solid {Palette.BORDER_SUBTLE};
                border-radius: 10px;
            }}
        """)
        return card

    def _status_card(self, title: str, subtitle: str, items: list, accent: str) -> QFrame:
        card = self._card()
        card.setStyleSheet(f"""
            QFrame {{
                background-color: {Palette.BG_SECONDARY};
                border: 1px solid {Palette.BORDER_SUBTLE};
                border-left: 3px solid {accent};
                border-radius: 10px;
            }}
        """)
        cl = QVBoxLayout(card)
        cl.setContentsMargins(14, 10, 14, 10)
        cl.setSpacing(6)

        t = QLabel(title)
        t.setStyleSheet(f"color: {accent}; font-size: 12px; font-weight: bold; background: transparent;")
        cl.addWidget(t)

        s = QLabel(subtitle)
        s.setStyleSheet(f"color: {Palette.TEXT_TERTIARY}; font-size: 10px; background: transparent;")
        cl.addWidget(s)

        for item in items[:8]:
            il = QLabel(f"  • {item}")
            il.setStyleSheet(f"color: {Palette.TEXT_SECONDARY}; font-size: 10px; background: transparent;")
            il.setWordWrap(True)
            cl.addWidget(il)

        return card

    def _get_failing_steps(self) -> list[str]:
        if not self._sim_result or not self._route:
            return []
        step_failures = self._sim_result.step_failure_counts
        result = []
        for step in sorted(self._route.steps, key=lambda s: step_failures.get(s.id, 0), reverse=True):
            fail_count = step_failures.get(step.id, 0)
            fail_rate = fail_count / max(1, self._sim_result.n_simulations)
            if fail_rate > 0.05:
                result.append(f"{step.title} — fails {fail_rate:.0%} of the time (risk: {step.risk_level}, fallback: {'yes' if step.fallback else 'NONE'})")
        return result

    def _get_succeeding_steps(self) -> list[str]:
        if not self._sim_result or not self._route:
            return []
        step_failures = self._sim_result.step_failure_counts
        result = []
        for step in self._route.steps:
            fail_count = step_failures.get(step.id, 0)
            fail_rate = fail_count / max(1, self._sim_result.n_simulations)
            if fail_rate < 0.05:
                result.append(f"{step.title} — reliable ({step.success_probability:.0%} success)")
        return result

    def _get_recommendations(self) -> list[str]:
        recs = []
        if not self._route:
            return ["Generate a route first."]

        # Check for steps without fallbacks
        no_fallback = [s for s in self._route.steps if not s.fallback and s.risk_level in ("high", "severe")]
        if no_fallback:
            names = ", ".join(s.title[:25] for s in no_fallback[:4])
            recs.append(f"Add fallback plans for high-risk steps: {names}. Without fallbacks, failure cascades.")

        # Check for low-probability steps
        low_prob = [s for s in self._route.steps if s.success_probability < 0.5]
        if low_prob:
            names = ", ".join(s.title[:25] for s in low_prob[:4])
            recs.append(f"Improve success probability of: {names}. Consider breaking these into smaller, more reliable steps.")

        # Check for single points of failure
        if self._sim_result and self._sim_result.failure_rate > 0.3:
            recs.append(f"Overall failure rate is {self._sim_result.failure_rate:.0%} — add more alternative/fallback branches to reduce risk.")

        # Check for bottleneck steps
        if self._health:
            for bn in self._health.bottlenecks[:3]:
                recs.append(f"Bottleneck: {bn}. Consider parallelizing or adding alternatives.")

        # Check for missing edges
        if len(self._route.edges) < len(self._route.steps) - 1:
            recs.append("Some steps may be disconnected — verify all edges are properly connected.")

        # Check for imbalance in branches
        branches = {}
        for s in self._route.steps:
            branches[s.branch] = branches.get(s.branch, 0) + 1
        if len(branches) == 1:
            recs.append("Only one branch — add alternative paths and fallbacks for resilience.")

        if not recs:
            recs.append("Your route looks solid! Consider running a Critique & Improve pass for deeper analysis.")

        return recs


# Need QApplication.processEvents
from PySide6.QtWidgets import QApplication
