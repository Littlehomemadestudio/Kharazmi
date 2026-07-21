"""
TimelineWidget — 24-hour vertical time ruler for the RASK! calendar.

Renders hour labels (00:00–23:00) with Shamsi/Persian digit formatting,
15-minute sub-tick marks, hour separator lines, and a current-time red
indicator line with dot.  Designed to sit inside a scroll area alongside
DayView and WeekView.
"""
from __future__ import annotations

from datetime import datetime

from PySide6.QtCore import Qt, QRectF, QTimer
from PySide6.QtGui import QPainter, QColor, QPen, QFont
from PySide6.QtWidgets import QWidget

from ...core.shamsi import to_persian_digits
from .theme import Text, Border, NowLine, Metrics, font_time_label


# ── Layout constants (derived from theme) ──────────────────────────────────

_HOUR_HEIGHT: int   = Metrics.HOUR_HEIGHT            # 60 px
_RULER_WIDTH: int   = Metrics.TIME_RULER_WIDTH       # 52 px
_NOW_LINE_PX: int   = Metrics.NOW_LINE_WIDTH         # 2 px

_SUB_TICKS_PER_HOUR: int = 4                         # 15-min intervals
_SUB_TICK_HEIGHT: float  = _HOUR_HEIGHT / _SUB_TICKS_PER_HOUR

# Tick mark lengths (extend leftward from the right edge)
_HOUR_TICK_LEN: int      = 10
_HALF_HOUR_TICK_LEN: int = 6
_QUARTER_TICK_LEN: int   = 3

# Right-margin: distance between label right-edge and widget right-edge
_LABEL_RIGHT_MARGIN: int = 8

# Current-time dot radius
_NOW_DOT_RADIUS: float = 4.0

# Per-minute refresh
_TIMER_INTERVAL_MS: int = 60_000


# ── Widget ─────────────────────────────────────────────────────────────────

class TimelineWidget(QWidget):
    """Vertical 24-hour time ruler rendered entirely with QPainter.

    * Fixed width  = ``Metrics.TIME_RULER_WIDTH``
    * Min height   = 24 × ``Metrics.HOUR_HEIGHT``
    * Auto-updates the now-line every minute via :class:`QTimer`.
    * Emits no signals — pure rendering widget.
    """

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)

        # ── Geometry ────────────────────────────────────────────────────────
        self.setFixedWidth(_RULER_WIDTH)
        self.setMinimumHeight(24 * _HOUR_HEIGHT)

        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setAutoFillBackground(False)

        # ── Fonts ───────────────────────────────────────────────────────────
        self._font_hour: QFont = font_time_label()
        self._font_half: QFont = font_time_label()
        self._font_half.setPointSize(self._font_half.pointSize() - 1)

        # ── Pens (created once, reused every paint) ─────────────────────────
        self._pen_hour = QPen(QColor(Border.SUBTLE), 1.0)
        self._pen_hour.setCosmetic(True)

        _half_c = QColor(Border.SUBTLE)
        _half_c.setAlpha(140)
        self._pen_half = QPen(_half_c, 1.0)
        self._pen_half.setCosmetic(True)

        _quarter_c = QColor(Border.SUBTLE)
        _quarter_c.setAlpha(70)
        self._pen_quarter = QPen(_quarter_c, 1.0)
        self._pen_quarter.setCosmetic(True)

        self._pen_now = QPen(NowLine.COLOR, _NOW_LINE_PX)
        self._pen_now.setCosmetic(True)

        # ── Label colours ───────────────────────────────────────────────────
        self._color_hour: QColor = QColor(Text.TERTIARY)
        self._color_half: QColor = QColor(Text.TERTIARY)
        self._color_half.setAlpha(160)

        # ── Per-minute timer ────────────────────────────────────────────────
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._on_tick)
        self._timer.start(_TIMER_INTERVAL_MS)

    # ── Timer ───────────────────────────────────────────────────────────────

    def _on_tick(self) -> None:
        """Repaint to advance the current-time indicator."""
        self.update()

    # ── Helpers ─────────────────────────────────────────────────────────────

    @staticmethod
    def _now_y() -> float:
        """Y-pixel offset for the current wall-clock time."""
        now = datetime.now()
        minutes = now.hour * 60 + now.minute
        return minutes * (_HOUR_HEIGHT / 60.0)

    @staticmethod
    def _fmt_hour(hour: int) -> str:
        """``HH:۰۰`` with Persian digits in the hour part."""
        return to_persian_digits(f"{hour:02d}:۰۰")

    @staticmethod
    def _fmt_half(hour: int) -> str:
        """``HH:۳۰`` with Persian digits in the hour part."""
        return to_persian_digits(f"{hour:02d}:۳۰")

    # ── Painting ────────────────────────────────────────────────────────────

    def paintEvent(self, event) -> None:  # noqa: N802
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, True)
        painter.setRenderHint(QPainter.TextAntialiasing, True)

        w: int = self.width()
        h_total: int = self.height()

        # Label drawing area: full widget width minus the right margin
        label_w: float = float(w - _LABEL_RIGHT_MARGIN)

        # ── 24-hour loop ───────────────────────────────────────────────────
        for hour in range(24):
            y0: float = hour * _HOUR_HEIGHT

            # ── Full-hour separator (spans entire widget width) ─────────────
            painter.setPen(self._pen_hour)
            painter.drawLine(0, int(y0), w, int(y0))

            # ── Hour label, right-aligned, vertically centred just above line
            painter.setFont(self._font_hour)
            painter.setPen(self._color_hour)
            fm = painter.fontMetrics()
            label_h: float = float(fm.height())
            # Place text so its vertical centre sits ~5 px above the hour line
            label_rect = QRectF(
                0.0,
                y0 - label_h - 2.0,
                label_w,
                label_h,
            )
            painter.drawText(label_rect, Qt.AlignRight | Qt.AlignVCenter, self._fmt_hour(hour))

            # ── Full-hour tick mark (right edge) ────────────────────────────
            painter.setPen(self._pen_hour)
            painter.drawLine(w - _HOUR_TICK_LEN, int(y0), w, int(y0))

            # ── 15-minute sub-ticks ─────────────────────────────────────────
            for sub in range(1, _SUB_TICKS_PER_HOUR):
                y_sub: float = y0 + sub * _SUB_TICK_HEIGHT

                if sub == 2:
                    # ── Half-hour ───────────────────────────────────────────
                    painter.setPen(self._pen_half)
                    # Separator across widget
                    painter.drawLine(0, int(y_sub), w, int(y_sub))
                    # Tick on right edge
                    painter.drawLine(
                        w - _HALF_HOUR_TICK_LEN, int(y_sub), w, int(y_sub)
                    )
                    # Label (smaller, dimmer)
                    painter.setFont(self._font_half)
                    painter.setPen(self._color_half)
                    fm_half = painter.fontMetrics()
                    half_h: float = float(fm_half.height())
                    half_rect = QRectF(
                        0.0,
                        y_sub - half_h - 2.0,
                        label_w,
                        half_h,
                    )
                    painter.drawText(
                        half_rect,
                        Qt.AlignRight | Qt.AlignVCenter,
                        self._fmt_half(hour),
                    )
                    painter.setFont(self._font_hour)
                else:
                    # ── Quarter-hour (:15 / :45) — short tick only ─────────
                    painter.setPen(self._pen_quarter)
                    painter.drawLine(
                        w - _QUARTER_TICK_LEN, int(y_sub), w, int(y_sub)
                    )

        # ── Closing line at 24:00 ──────────────────────────────────────────
        y_24: int = 24 * _HOUR_HEIGHT
        painter.setPen(self._pen_hour)
        painter.drawLine(0, y_24, w, y_24)

        # ── Current-time indicator ─────────────────────────────────────────
        now_y: float = self._now_y()
        if 0.0 <= now_y <= float(h_total):
            # Red horizontal line spanning the widget
            painter.setPen(self._pen_now)
            painter.drawLine(0, int(now_y), w, int(now_y))

            # Red dot centred on the left edge of the widget
            painter.setPen(Qt.NoPen)
            painter.setBrush(NowLine.DOT)
            painter.drawEllipse(
                QRectF(
                    0.0,                             # left edge of dot = x=0
                    now_y - _NOW_DOT_RADIUS,
                    _NOW_DOT_RADIUS * 2.0,
                    _NOW_DOT_RADIUS * 2.0,
                )
            )

        painter.end()
