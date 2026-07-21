"""
AnimationManager — Smooth transitions for the RASK! calendar.

Provides reusable animation building blocks:
  - Fade in/out
  - Slide (horizontal/vertical)
  - Scale (zoom)
  - Ripple (material-design-style)
  - Page transitions (for month navigation)

Uses QVariantAnimation for frame-rate-independent smooth motion.
All animations run at the display's native refresh rate via Qt's
compositor (no fixed 60fps cap).
"""
from __future__ import annotations

from typing import Callable, Optional

from PySide6.QtCore import (
    Qt, QAbstractAnimation, QEasingCurve,
    QVariantAnimation, QPoint, QPointF, QSize, QRectF, QTimer,
)
from PySide6.QtGui import QPainter, QColor, QPen, QBrush, QLinearGradient
from PySide6.QtWidgets import QWidget

from .theme import Metrics


# ──────────────────────────────── Easings ─────────────────────────────────

EASE_OUT      = QEasingCurve(QEasingCurve.OutCubic)
EASE_IN_OUT   = QEasingCurve(QEasingCurve.InOutCubic)
EASE_OUT_BACK = QEasingCurve(QEasingCurve.OutBack)
EASE_OUT_QUAD = QEasingCurve(QEasingCurve.OutQuad)
EASE_SPRING   = QEasingCurve(QEasingCurve.OutElastic)


# ──────────────────────────────── Fade ────────────────────────────────────

def fade_widget(
    widget: QWidget,
    from_opacity: float = 0.0,
    to_opacity: float = 1.0,
    duration_ms: int = Metrics.ANIM_DURATION_MS,
    on_finished: Optional[Callable] = None,
) -> QVariantAnimation:
    """Animate a widget's window opacity (requires WA_TranslucentBackground)."""
    anim = QVariantAnimation(widget)
    anim.setStartValue(from_opacity)
    anim.setEndValue(to_opacity)
    anim.setDuration(duration_ms)
    anim.setEasingCurve(EASE_OUT)
    anim.valueChanged.connect(lambda v: widget.setWindowOpacity(v) if widget.window() else None)
    if on_finished:
        anim.finished.connect(on_finished)
    anim.start(QAbstractAnimation.DeleteWhenStopped)
    return anim


# ──────────────────────────────── Slide ───────────────────────────────────

class SlideAnimation(QVariantAnimation):
    """Slide a widget from one position to another."""

    def __init__(
        self,
        widget: QWidget,
        start_pos: QPoint,
        end_pos: QPoint,
        duration_ms: int = Metrics.ANIM_DURATION_MS,
        easing: QEasingCurve = EASE_OUT,
        on_finished: Optional[Callable] = None,
    ) -> None:
        super().__init__(widget)
        self._widget = widget
        self.setStartValue(start_pos)
        self.setEndValue(end_pos)
        self.setDuration(duration_ms)
        self.setEasingCurve(easing)
        self.valueChanged.connect(self._on_value)
        if on_finished:
            self.finished.connect(on_finished)

    def _on_value(self, pos: QPoint) -> None:
        self._widget.move(pos)


def slide_in(
    widget: QWidget,
    direction: str = "left",
    duration_ms: int = Metrics.ANIM_DURATION_MS,
    on_finished: Optional[Callable] = None,
) -> SlideAnimation:
    """Slide a widget into view from the given direction."""
    parent_rect = widget.parent().rect() if widget.parent() else widget.rect()
    target = widget.pos()
    if direction == "left":
        start = QPoint(parent_rect.width(), target.y())
    elif direction == "right":
        start = QPoint(-widget.width(), target.y())
    elif direction == "top":
        start = QPoint(target.x(), -widget.height())
    else:
        start = QPoint(target.x(), parent_rect.height())

    widget.move(start)
    anim = SlideAnimation(widget, start, target, duration_ms, EASE_OUT_BACK, on_finished)
    anim.start(QAbstractAnimation.DeleteWhenStopped)
    return anim


# ──────────────────────────────── Scale ───────────────────────────────────

class ScaleAnimation(QVariantAnimation):
    """Animate a scale factor (caller applies in paintEvent)."""

    def __init__(
        self,
        target: object,
        prop_name: str = "scale",
        from_val: float = 0.8,
        to_val: float = 1.0,
        duration_ms: int = Metrics.ANIM_FAST_MS,
        easing: QEasingCurve = EASE_OUT_BACK,
        on_finished: Optional[Callable] = None,
    ) -> None:
        super().__init__(target)
        self._target = target
        self._prop = prop_name
        self.setStartValue(from_val)
        self.setEndValue(to_val)
        self.setDuration(duration_ms)
        self.setEasingCurve(easing)
        self.valueChanged.connect(self._on_value)
        if on_finished:
            self.finished.connect(on_finished)

    def _on_value(self, val: float) -> None:
        if hasattr(self._target, self._prop):
            setattr(self._target, self._prop, val)
        if hasattr(self._target, "update"):
            self._target.update()


# ──────────────────────────────── Ripple ──────────────────────────────────

class RippleOverlay(QWidget):
    """Material Design ripple effect overlay."""

    def __init__(self, parent: QWidget) -> None:
        super().__init__(parent)
        self.setAttribute(Qt.WA_TransparentForMouseEvents)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self._ripples: list[_Ripple] = []

    def start(self, pos: QPointF, color: QColor = QColor(212, 175, 55, 80)) -> None:
        r = _Ripple(pos, color, self)
        self._ripples.append(r)
        r.finished.connect(lambda: self._ripples.remove(r) if r in self._ripples else None)
        r.start()

    def paintEvent(self, event) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        for r in self._ripples:
            r.paint(p)
        p.end()


class _Ripple:
    def __init__(self, origin: QPointF, color: QColor, overlay: RippleOverlay) -> None:
        self._origin = origin
        self._color = color
        self._overlay = overlay
        self._progress = 0.0
        self._max_radius = 120
        self.finished = None

        self._anim = QVariantAnimation(overlay)
        self._anim.setStartValue(0.0)
        self._anim.setEndValue(1.0)
        self._anim.setDuration(500)
        self._anim.setEasingCurve(EASE_OUT_QUAD)
        self._anim.valueChanged.connect(self._tick)
        self._anim.finished.connect(self._done)

    def start(self) -> None:
        self._anim.start(QAbstractAnimation.DeleteWhenStopped)

    def _tick(self, val: float) -> None:
        self._progress = val
        self._overlay.update()

    def _done(self) -> None:
        if self.finished:
            self.finished()

    def paint(self, painter: QPainter) -> None:
        radius = self._progress * self._max_radius
        alpha = int(80 * (1.0 - self._progress))
        c = QColor(self._color)
        c.setAlpha(alpha)
        painter.setPen(Qt.NoPen)
        painter.setBrush(QBrush(c))
        painter.drawEllipse(self._origin, radius, radius)


# ──────────────────────────────── Page Transition ─────────────────────────

class PageTransition:
    """
    Manages animated transitions between calendar pages (e.g. month → month).

    Supports slide-left, slide-right, and fade transitions.
    """

    def __init__(self, container: QWidget) -> None:
        self._container = container
        self._anim: Optional[QVariantAnimation] = None

    def transition(
        self,
        old_widget: Optional[QWidget],
        new_widget: QWidget,
        direction: str = "left",
    ) -> None:
        """Animate from old_widget to new_widget."""
        if self._anim and self._anim.state() == QAbstractAnimation.Running:
            self._anim.stop()

        if old_widget is None:
            new_widget.show()
            return

        # Simple fade transition
        new_widget.show()
        new_widget.setWindowOpacity(0.0)

        self._anim = QVariantAnimation(self._container)
        self._anim.setStartValue(0.0)
        self._anim.setEndValue(1.0)
        self._anim.setDuration(Metrics.ANIM_DURATION_MS)
        self._anim.setEasingCurve(EASE_OUT)

        def _tick(v: float) -> None:
            old_widget.setWindowOpacity(1.0 - v)
            new_widget.setWindowOpacity(v)

        def _done() -> None:
            old_widget.hide()
            old_widget.setWindowOpacity(1.0)
            new_widget.setWindowOpacity(1.0)

        self._anim.valueChanged.connect(_tick)
        self._anim.finished.connect(_done)
        self._anim.start(QAbstractAnimation.DeleteWhenStopped)


# ──────────────────────────────── Hover Glow ──────────────────────────────

class HoverGlow:
    """Tracks hover state and provides a smooth glow factor 0..1."""

    def __init__(self, widget: QWidget, duration_ms: int = Metrics.ANIM_FAST_MS) -> None:
        self._widget = widget
        self._value = 0.0
        self._anim: Optional[QVariantAnimation] = None
        self._duration = duration_ms

    @property
    def value(self) -> float:
        return self._value

    def enter(self) -> None:
        self._animate_to(1.0)

    def leave(self) -> None:
        self._animate_to(0.0)

    def _animate_to(self, target: float) -> None:
        if self._anim and self._anim.state() == QAbstractAnimation.Running:
            self._anim.stop()
        self._anim = QVariantAnimation(self._widget)
        self._anim.setStartValue(self._value)
        self._anim.setEndValue(target)
        self._anim.setDuration(self._duration)
        self._anim.setEasingCurve(EASE_OUT)
        self._anim.valueChanged.connect(self._tick)
        self._anim.start(QAbstractAnimation.DeleteWhenStopped)

    def _tick(self, v: float) -> None:
        self._value = v
        self._widget.update()
