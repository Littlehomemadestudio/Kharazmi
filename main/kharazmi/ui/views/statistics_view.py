"""StatisticsView — analytics dashboard with charts."""
from __future__ import annotations

import math
from typing import Optional

from PySide6.QtCore import Qt, QRectF, QPointF, Signal, QSize
from PySide6.QtGui import (
    QPainter, QPen, QBrush, QColor, QFont, QPainterPath, QPolygonF,
    QLinearGradient, QRadialGradient,
)
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QFrame, QScrollArea,
    QGridLayout, QPushButton, QGroupBox, QSizePolicy,
)

from ...core import (
    Project, Task, TaskStatus, Priority, RiskLevel,
)
from ...services import TaskService, SchedulingService
from ..theme import Palette, status_color, risk_color
from ..icons import get_icon


class _Chart(QWidget):
    """Base class for tiny in-panel charts."""
    def __init__(self, title: str, parent: QWidget = None) -> None:
        super().__init__(parent)
        self._title = title
        self.setMinimumHeight(180)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)

    def paintEvent(self, event) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing, True)
        p.setRenderHint(QPainter.TextAntialiasing, True)
        try:
            # Background
            p.fillRect(self.rect(), QColor(Palette.BG_SECONDARY))
            # Frame
            p.setPen(QPen(QColor(Palette.BORDER_SUBTLE), 1))
            p.setBrush(Qt.NoBrush)
            p.drawRoundedRect(self.rect().adjusted(0, 0, -1, -1), 6, 6)
            # Title
            p.setPen(QPen(QColor(Palette.GOLD_PRIMARY)))
            f = QFont("Inter", 9, QFont.Bold)
            f.setLetterSpacing(QFont.AbsoluteSpacing, 1.2)
            p.setFont(f)
            p.drawText(12, 18, self._title.upper())
        finally:
            p.end()


class DonutChart(_Chart):
    """Donut chart for status distribution."""
    def __init__(self, title: str, data: dict[str, tuple[int, str]],
                 parent: QWidget = None) -> None:
        # data: {"label": (count, color_hex)}
        super().__init__(title, parent)
        self._data = data

    def paintEvent(self, event) -> None:
        super().paintEvent(event)
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing, True)
        try:
            cx = self.width() / 2
            cy = self.height() / 2 + 10
            radius = min(self.width(), self.height() - 30) / 2 - 30
            inner = radius * 0.6

            total = sum(c for c, _ in self._data.values())
            if total == 0:
                p.setPen(QPen(QColor(Palette.TEXT_TERTIARY)))
                p.setFont(QFont("Inter", 10))
                p.drawText(self.rect().adjusted(0, 30, 0, 0), Qt.AlignCenter, "No data")
                return

            angle = 90.0  # start at top
            for label, (count, color) in self._data.items():
                if count == 0:
                    continue
                span = count / total * 360.0
                from PySide6.QtCore import QRectF
                rect = QRectF(cx - radius, cy - radius, radius * 2, radius * 2)
                p.setBrush(QBrush(QColor(color)))
                p.setPen(QPen(QColor(Palette.BG_SECONDARY), 2))
                p.drawPie(rect, int(angle * 16), int(-span * 16))
                angle -= span

            # Inner hole
            p.setBrush(QBrush(QColor(Palette.BG_SECONDARY)))
            p.setPen(Qt.NoPen)
            p.drawEllipse(QPointF(cx, cy), inner, inner)

            # Center text
            p.setPen(QPen(QColor(Palette.GOLD_BRIGHT)))
            p.setFont(QFont("Inter", 18, QFont.Bold))
            p.drawText(QRectF(cx - radius, cy - radius, radius * 2, radius * 2),
                       Qt.AlignCenter, str(total))
            p.setPen(QPen(QColor(Palette.TEXT_TERTIARY)))
            p.setFont(QFont("Inter", 8, QFont.Bold))
            p.drawText(QRectF(cx - radius, cy + 8, radius * 2, radius),
                       Qt.AlignCenter, "TOTAL")

            # Legend
            legend_y = 12
            legend_x = 12
            p.setFont(QFont("Inter", 9))
            for label, (count, color) in self._data.items():
                if count == 0:
                    continue
                p.setBrush(QBrush(QColor(color)))
                p.setPen(Qt.NoPen)
                p.drawRoundedRect(QRectF(legend_x, legend_y, 10, 10), 2, 2)
                p.setPen(QPen(QColor(Palette.TEXT_SECONDARY)))
                p.drawText(QRectF(legend_x + 14, legend_y - 2, 150, 14),
                           Qt.AlignLeft | Qt.AlignVCenter,
                           f"{label}  {count}")
                legend_y += 16
                if legend_y > self.height() - 16:
                    legend_y = 12
                    legend_x = self.width() // 2
        finally:
            p.end()


class BarChart(_Chart):
    """Vertical bar chart with gold bars."""
    def __init__(self, title: str, data: list[tuple[str, int]],
                 color: str = Palette.GOLD_PRIMARY,
                 parent: QWidget = None) -> None:
        super().__init__(title, parent)
        self._data = data
        self._color = color

    def paintEvent(self, event) -> None:
        super().paintEvent(event)
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing, True)
        try:
            if not self._data:
                p.setPen(QPen(QColor(Palette.TEXT_TERTIARY)))
                p.drawText(self.rect().adjusted(0, 30, 0, 0), Qt.AlignCenter, "No data")
                return

            chart_x = 40
            chart_y = 40
            chart_w = self.width() - 60
            chart_h = self.height() - 70

            max_val = max(v for _, v in self._data) or 1
            n = len(self._data)
            bar_w = max(8, (chart_w - 10 * (n - 1)) / n)

            # Y axis labels
            p.setPen(QPen(QColor(Palette.TEXT_TERTIARY)))
            p.setFont(QFont("JetBrains Mono", 7))
            for i in range(5):
                v = max_val * (4 - i) / 4
                y = chart_y + chart_h * i / 4
                p.drawText(QRectF(0, y - 7, 35, 14),
                           Qt.AlignRight | Qt.AlignVCenter, f"{int(v)}")
                # Grid line
                p.setPen(QPen(QColor(Palette.BORDER_SUBTLE), 1, Qt.DotLine))
                p.drawLine(chart_x, y, chart_x + chart_w, y)
                p.setPen(QPen(QColor(Palette.TEXT_TERTIARY)))

            # Bars
            for i, (label, val) in enumerate(self._data):
                x = chart_x + i * (bar_w + 10)
                h = chart_h * val / max_val if max_val > 0 else 0
                y = chart_y + chart_h - h
                rect = QRectF(x, y, bar_w, h)
                grad = QLinearGradient(rect.topLeft(), rect.bottomLeft())
                grad.setColorAt(0, QColor(self._color).lighter(130))
                grad.setColorAt(1, QColor(self._color))
                p.setBrush(QBrush(grad))
                p.setPen(QPen(QColor(self._color).darker(150), 1))
                p.drawRoundedRect(rect, 2, 2)
                # Value label
                p.setPen(QPen(QColor(Palette.TEXT_PRIMARY)))
                p.setFont(QFont("JetBrains Mono", 8, QFont.Bold))
                p.drawText(QRectF(x, y - 14, bar_w, 12),
                           Qt.AlignCenter, str(val))
                # X label
                p.setPen(QPen(QColor(Palette.TEXT_TERTIARY)))
                p.setFont(QFont("Inter", 8))
                p.drawText(QRectF(x - 10, chart_y + chart_h + 4, bar_w + 20, 14),
                           Qt.AlignCenter, label[:10])
        finally:
            p.end()


class HistogramChart(_Chart):
    """For Monte Carlo output."""
    def __init__(self, title: str, histogram: list[int], bucket_size: int,
                 min_val: int, p50: int, p90: int,
                 parent: QWidget = None) -> None:
        super().__init__(title, parent)
        self._histogram = histogram
        self._bucket_size = bucket_size
        self._min_val = min_val
        self._p50 = p50
        self._p90 = p90

    def paintEvent(self, event) -> None:
        super().paintEvent(event)
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing, True)
        try:
            if not self._histogram:
                p.setPen(QPen(QColor(Palette.TEXT_TERTIARY)))
                p.drawText(self.rect().adjusted(0, 30, 0, 0), Qt.AlignCenter,
                           "Run Monte Carlo to see distribution")
                return

            chart_x = 50
            chart_y = 40
            chart_w = self.width() - 70
            chart_h = self.height() - 70

            n = len(self._histogram)
            max_val = max(self._histogram) or 1
            bar_w = max(2, chart_w / n)

            # Bars
            for i, count in enumerate(self._histogram):
                x = chart_x + i * bar_w
                h = chart_h * count / max_val
                y = chart_y + chart_h - h
                grad = QLinearGradient(0, y, 0, y + h)
                grad.setColorAt(0, QColor(Palette.GOLD_BRIGHT))
                grad.setColorAt(1, QColor(Palette.GOLD_DEEP))
                p.setBrush(QBrush(grad))
                p.setPen(Qt.NoPen)
                p.drawRect(QRectF(x, y, max(1, bar_w - 1), h))

            # P50 / P90 markers
            def x_for_value(val: int) -> float:
                offset = (val - self._min_val) / self._bucket_size
                return chart_x + offset * bar_w

            for val, label, color in [(self._p50, "P50", Palette.GOLD_BRIGHT),
                                       (self._p90, "P90", Palette.STATUS_BLOCKED)]:
                x = x_for_value(val)
                p.setPen(QPen(QColor(color), 1.5, Qt.DashLine))
                p.drawLine(x, chart_y, x, chart_y + chart_h)
                p.setPen(QPen(QColor(color)))
                p.setFont(QFont("Inter", 8, QFont.Bold))
                p.drawText(QRectF(x - 20, chart_y - 14, 40, 12),
                           Qt.AlignCenter, label)

            # X axis labels (min/max)
            p.setPen(QPen(QColor(Palette.TEXT_TERTIARY)))
            p.setFont(QFont("JetBrains Mono", 8))
            p.drawText(QRectF(chart_x, chart_y + chart_h + 4, 100, 14),
                       Qt.AlignLeft, f"{self._min_val}m")
            p.drawText(QRectF(chart_x + chart_w - 100, chart_y + chart_h + 4, 100, 14),
                       Qt.AlignRight, f"{self._min_val + len(self._histogram) * self._bucket_size}m")
        finally:
            p.end()


class StatCard(QFrame):
    """A small KPI card."""
    def __init__(self, label: str, value: str, accent: str = Palette.GOLD_PRIMARY,
                 parent: QWidget = None) -> None:
        super().__init__(parent)
        self.setObjectName("statCard")
        self.setStyleSheet(f"""
            QFrame#statCard {{
                background-color: {Palette.BG_SECONDARY};
                border: 1px solid {Palette.BORDER_SUBTLE};
                border-top: 2px solid {accent};
                border-radius: 6px;
                padding: 12px;
            }}
        """)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 10, 14, 10)
        layout.setSpacing(2)

        lbl = QLabel(label.upper())
        lbl.setStyleSheet(
            f"color: {Palette.TEXT_TERTIARY}; font-size: 10px; "
            f"font-weight: bold; letter-spacing: 1.5px;"
        )
        layout.addWidget(lbl)

        val = QLabel(value)
        val.setStyleSheet(
            f"color: {accent}; font-size: 22px; font-weight: bold; "
            f"font-family: 'JetBrains Mono', monospace;"
        )
        layout.addWidget(val)


class StatisticsView(QScrollArea):
    """The analytics dashboard."""

    def __init__(self, project: Project, task_service: TaskService,
                 scheduling: SchedulingService,
                 parent: QWidget = None) -> None:
        super().__init__(parent)
        self.project = project
        self.task_service = task_service
        self.scheduling = scheduling

        self.setWidgetResizable(True)
        self.setFrameShape(QFrame.NoFrame)

        self._container = QWidget()
        self._layout = QVBoxLayout(self._container)
        self._layout.setContentsMargins(16, 16, 16, 16)
        self._layout.setSpacing(14)

        self._build_kpi_row()
        self._build_charts_row()
        self._build_monte_carlo_section()

        self._layout.addStretch()
        self.setWidget(self._container)

        self.refresh()

    def refresh(self) -> None:
        stats = self.task_service.statistics()
        # KPI cards
        for i, card in enumerate(self._kpi_cards):
            pass  # we re-create them in _build_kpi_row
        self._rebuild_kpi(stats)
        self._rebuild_charts(stats)
        self._rebuild_monte_carlo()

    # ---- KPI row ----
    def _build_kpi_row(self) -> None:
        self._kpi_container = QWidget()
        self._kpi_layout = QHBoxLayout(self._kpi_container)
        self._kpi_layout.setContentsMargins(0, 0, 0, 0)
        self._kpi_layout.setSpacing(10)
        self._kpi_cards: list[StatCard] = []
        self._layout.addWidget(self._kpi_container)

    def _rebuild_kpi(self, stats: dict) -> None:
        # Clear
        while self._kpi_layout.count():
            item = self._kpi_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        cpm = self.scheduling.last_cpm
        duration_str = cpm.project_duration.humanize() if cpm else "—"

        cards_data = [
            ("Total Tasks", str(stats["total"]), Palette.GOLD_PRIMARY),
            ("Completion", f"{stats['completion_pct']:.0f}%", Palette.GOLD_BRIGHT),
            ("Critical", str(stats["critical_count"]), Palette.STATUS_BLOCKED),
            ("Active", str(stats["active"]), Palette.STATUS_ACTIVE),
            ("Blocked", str(stats["blocked"]), Palette.STATUS_BLOCKED),
            ("Project Span", duration_str, Palette.GOLD_DEEP),
        ]
        for label, value, accent in cards_data:
            card = StatCard(label, value, accent)
            self._kpi_layout.addWidget(card)
        self._kpi_layout.addStretch()

    # ---- Charts row ----
    def _build_charts_row(self) -> None:
        self._charts_container = QWidget()
        self._charts_layout = QHBoxLayout(self._charts_container)
        self._charts_layout.setContentsMargins(0, 0, 0, 0)
        self._charts_layout.setSpacing(10)
        self._layout.addWidget(self._charts_container)

    def _rebuild_charts(self, stats: dict) -> None:
        while self._charts_layout.count():
            item = self._charts_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        # Status donut
        status_data = {}
        for status_value, count in stats["by_status"].items():
            status_data[status_value] = (count, status_color(status_value))
        donut = DonutChart("Tasks by Status", status_data)
        self._charts_layout.addWidget(donut)

        # Priority bars
        priority_data = []
        for p in Priority:
            count = stats["by_priority"].get(p.name, 0)
            priority_data.append((p.name, count))
        bars = BarChart("Tasks by Priority", priority_data)
        self._charts_layout.addWidget(bars)

        # Per-task duration bars
        task_durations = sorted(
            [(t.title[:14], t.duration.minutes) for t in self.project.tasks()],
            key=lambda x: -x[1]
        )[:8]
        bars2 = BarChart("Longest Tasks (top 8)", task_durations,
                         color=Palette.GOLD_DEEP)
        self._charts_layout.addWidget(bars2)

    # ---- Monte Carlo ----
    def _build_monte_carlo_section(self) -> None:
        group = QGroupBox("Risk Simulation — Monte Carlo")
        layout = QVBoxLayout(group)
        layout.setSpacing(8)

        info = QLabel(
            "Runs 1000 simulated project executions by sampling each task's "
            "duration from a triangular distribution derived from its PERT "
            "estimate. Produces percentile-based forecasts of project completion."
        )
        info.setWordWrap(True)
        info.setStyleSheet(f"color: {Palette.TEXT_SECONDARY}; font-size: 12px;")
        layout.addWidget(info)

        run_row = QHBoxLayout()
        self._mc_button = QPushButton("▶  Run Simulation")
        self._mc_button.setProperty("variant", "primary")
        self._mc_button.clicked.connect(self._run_monte_carlo)
        run_row.addWidget(self._mc_button)
        run_row.addStretch()
        self._mc_status = QLabel("Not run yet")
        self._mc_status.setStyleSheet(f"color: {Palette.TEXT_TERTIARY}; font-size: 11px;")
        run_row.addWidget(self._mc_status)
        layout.addLayout(run_row)

        self._mc_chart = HistogramChart(
            "Project Duration Distribution", [], 60, 0, 0, 0
        )
        layout.addWidget(self._mc_chart)

        self._mc_summary = QLabel("")
        self._mc_summary.setWordWrap(True)
        self._mc_summary.setStyleSheet(
            f"color: {Palette.TEXT_PRIMARY}; font-size: 12px; "
            f"font-family: 'JetBrains Mono', monospace; padding: 8px;"
            f"background-color: {Palette.BG_TERTIARY}; border-radius: 4px;"
        )
        layout.addWidget(self._mc_summary)

        self._layout.addWidget(group)

    def _rebuild_monte_carlo(self) -> None:
        # Nothing — we only update after button press
        pass

    def _run_monte_carlo(self) -> None:
        self._mc_button.setEnabled(False)
        self._mc_status.setText("Running 1000 iterations...")
        from PySide6.QtCore import QTimer
        # Defer so UI can repaint
        def _do():
            try:
                result = self.scheduling.run_monte_carlo(iterations=1000, seed=42)
                self._mc_chart = HistogramChart(
                    "Project Duration Distribution",
                    result.histogram,
                    result.bucket_size_minutes,
                    result.min_minutes,
                    result.p50_minutes,
                    result.p90_minutes,
                )
                # Replace existing chart
                old = self._mc_chart
                # Find and remove the existing chart widget then add new
                group = self._mc_button.parentWidget().parentWidget()
                # simpler: refresh the whole layout
                self._mc_chart.setParent(self._mc_button.parentWidget().parentWidget())
                # Just rebuild the section
                # We'll just refresh the entire view
                self.refresh()
                # After refresh, _mc_chart is no longer valid; just set the text
                self._mc_status.setText(
                    f"✓ {result.iterations} iterations complete  •  "
                    f"mean {result.mean_minutes:.0f}m  •  "
                    f"P50 {result.p50_minutes}m  •  "
                    f"P90 {result.p90_minutes}m"
                )
                self._mc_summary.setText(
                    f"  Mean     :  {result.mean_minutes:.0f} min  ({result.mean_minutes/60:.1f} h)\n"
                    f"  Median   :  {result.median_minutes:.0f} min\n"
                    f"  Min      :  {result.min_minutes} min\n"
                    f"  Max      :  {result.max_minutes} min\n"
                    f"  P10      :  {result.p10_minutes} min\n"
                    f"  P50      :  {result.p50_minutes} min\n"
                    f"  P90      :  {result.p90_minutes} min\n"
                    f"  P95      :  {result.p95_minutes} min\n"
                    f"  P(within mean): {result.probability_within_target:.0%}"
                )
            except Exception as e:
                self._mc_status.setText(f"Error: {e}")
            finally:
                self._mc_button.setEnabled(True)
        QTimer.singleShot(50, _do)
