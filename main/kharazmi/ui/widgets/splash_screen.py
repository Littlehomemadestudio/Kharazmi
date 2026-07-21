"""
RaskSplashScreen — Animated branded splash screen with gold particles.

Shows when the app launches:
  - Dark background with animated gold particle field
  - RASK! logo text with gold gradient
  - "Kharazmi" subtitle with fade-in
  - Loading progress bar with gold shimmer
  - Status text ("Loading calendar...", "Initializing AI...", etc.)
  - Smooth fade-out transition when loading completes

This creates a powerful first impression — referees see a premium
loading experience, not a blank window.
"""
from __future__ import annotations

import math
import random
from typing import Optional

from PySide6.QtCore import Qt, QTimer, QPropertyAnimation, QEasingCurve, QRectF, QPointF
from PySide6.QtGui import (
    QPainter, QColor, QPen, QBrush, QFont, QPixmap,
    QPainterPath, QLinearGradient, QRadialGradient, QFontMetrics,
)
from PySide6.QtWidgets import QWidget, QApplication

from .theme import Palette


class _SplashParticle:
    """A gold particle for the splash background."""
    __slots__ = ('x', 'y', 'vx', 'vy', 'size', 'opacity', 'phase', 'speed')

    def __init__(self, x: float, y: float) -> None:
        self.x = x
        self.y = y
        angle = random.uniform(0, 2 * math.pi)
        speed = random.uniform(0.2, 1.0)
        self.vx = math.cos(angle) * speed
        self.vy = math.sin(angle) * speed
        self.size = random.uniform(1.0, 3.5)
        self.opacity = random.uniform(0.1, 0.5)
        self.phase = random.uniform(0, math.pi * 2)
        self.speed = random.uniform(0.02, 0.06)


class RaskSplashScreen(QWidget):
    """
    Full-screen animated splash screen.

    Usage:
        splash = RaskSplashScreen()
        splash.show()
        splash.set_progress(30, "Loading calendar...")
        # ... later ...
        splash.set_progress(100, "Ready!")
        splash.finish()  # fades out and closes
    """

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setWindowFlags(
            Qt.FramelessWindowHint |
            Qt.WindowStaysOnTopHint |
            Qt.SplashScreen
        )
        self.setAttribute(Qt.WA_TranslucentBackground, False)
        self.setFixedSize(680, 420)

        self._progress = 0
        self._status_text = "Initializing..."
        self._particles: list[_SplashParticle] = []
        self._tick = 0
        self._fade_opacity = 1.0
        self._finishing = False

        # Spawn initial particles
        for _ in range(80):
            self._particles.append(_SplashParticle(
                random.uniform(0, self.width()),
                random.uniform(0, self.height()),
            ))

        # Animation timer
        self._timer = QTimer(self)
        self._timer.setInterval(25)  # ~40 FPS
        self._timer.timeout.connect(self._on_tick)
        self._timer.start()

    def set_progress(self, value: int, status: str = "") -> None:
        """Update the progress bar (0-100) and optional status text."""
        self._progress = max(0, min(100, value))
        if status:
            self._status_text = status
        self.update()

    def finish(self) -> None:
        """Start the fade-out animation and close when done."""
        self._finishing = True
        self._fade_anim = QPropertyAnimation(self, b"windowOpacity")
        self._fade_anim.setDuration(600)
        self._fade_anim.setStartValue(1.0)
        self._fade_anim.setEndValue(0.0)
        self._fade_anim.setEasingCurve(QEasingCurve.OutCubic)
        self._fade_anim.finished.connect(self.close)
        self._fade_anim.start()

    def _on_tick(self) -> None:
        self._tick += 1
        w, h = self.width(), self.height()

        for p in self._particles:
            p.x += p.vx
            p.y += p.vy
            p.phase += p.speed
            # Subtle pulsing
            p.opacity = 0.15 + 0.25 * (0.5 + 0.5 * math.sin(p.phase))
            # Wrap around
            if p.x < -10: p.x = w + 10
            if p.x > w + 10: p.x = -10
            if p.y < -10: p.y = h + 10
            if p.y > h + 10: p.y = -10

        self.update()

    # ── Paint ──

    def paintEvent(self, event) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing, True)

        w, h = self.width(), self.height()

        # ── Background ──
        bg_grad = QLinearGradient(0, 0, 0, h)
        bg_grad.setColorAt(0, QColor(10, 10, 12))
        bg_grad.setColorAt(0.5, QColor(14, 14, 18))
        bg_grad.setColorAt(1, QColor(8, 8, 10))
        p.fillRect(self.rect(), QBrush(bg_grad))

        # ── Subtle radial glow behind logo ──
        center_glow = QRadialGradient(QPointF(w / 2, h / 2 - 20), 200)
        center_glow.setColorAt(0, QColor(212, 175, 55, 25))
        center_glow.setColorAt(1, QColor(212, 175, 55, 0))
        p.setPen(Qt.NoPen)
        p.setBrush(QBrush(center_glow))
        p.drawRect(self.rect())

        # ── Particles ──
        for pt in self._particles:
            alpha = int(pt.opacity * 255)
            gold = QColor(245, 200, 66, alpha)
            p.setPen(Qt.NoPen)
            p.setBrush(QBrush(gold))
            p.drawEllipse(QPointF(pt.x, pt.y), pt.size, pt.size)

            # Glow for larger particles
            if pt.size > 2.5:
                glow = QRadialGradient(QPointF(pt.x, pt.y), pt.size * 4)
                glow.setColorAt(0, QColor(212, 175, 55, int(alpha * 0.2)))
                glow.setColorAt(1, QColor(212, 175, 55, 0))
                p.setBrush(QBrush(glow))
                p.drawEllipse(QPointF(pt.x, pt.y), pt.size * 4, pt.size * 4)

        # ── Top gold accent line ──
        accent = QLinearGradient(0, 0, w, 0)
        accent.setColorAt(0.0, QColor(212, 175, 55, 0))
        accent.setColorAt(0.3, QColor(212, 175, 55, 200))
        accent.setColorAt(0.5, QColor(245, 200, 66, 255))
        accent.setColorAt(0.7, QColor(212, 175, 55, 200))
        accent.setColorAt(1.0, QColor(212, 175, 55, 0))
        p.fillRect(0, 0, w, 2, QBrush(accent))

        # ── RASK! logo ──
        logo_font = QFont("Segoe UI", 56, QFont.Bold)
        p.setFont(logo_font)

        # Gold gradient on text
        text_grad = QLinearGradient(0, h / 2 - 80, 0, h / 2 - 10)
        text_grad.setColorAt(0, QColor(245, 200, 66))
        text_grad.setColorAt(0.5, QColor(212, 175, 55))
        text_grad.setColorAt(1, QColor(140, 112, 18))
        p.setPen(QPen(QBrush(text_grad), 1))
        p.setBrush(Qt.NoBrush)

        logo_rect = QRectF(0, h / 2 - 80, w, 80)
        p.drawText(logo_rect, Qt.AlignCenter, "RASK!")

        # ── Subtitle: KHARAZMI ──
        sub_font = QFont("Segoe UI", 14)
        sub_font.setLetterSpacing(QFont.AbsoluteSpacing, 8)
        p.setFont(sub_font)
        # Fade-in based on tick
        sub_alpha = min(255, int(self._tick * 3))
        p.setPen(QPen(QColor(168, 162, 148, sub_alpha)))
        sub_rect = QRectF(0, h / 2 + 5, w, 30)
        p.drawText(sub_rect, Qt.AlignCenter, "K H A R A Z M I")

        # ── Progress bar ──
        bar_y = h - 70
        bar_h = 6
        bar_left = 80
        bar_right = w - 80
        bar_w = bar_right - bar_left

        # Track background
        p.setPen(Qt.NoPen)
        p.setBrush(QBrush(QColor(26, 26, 30)))
        track_path = QPainterPath()
        track_path.addRoundedRect(QRectF(bar_left, bar_y, bar_w, bar_h), 3, 3)
        p.drawPath(track_path)

        # Fill
        if self._progress > 0:
            fill_w = bar_w * (self._progress / 100.0)
            fill_grad = QLinearGradient(bar_left, bar_y, bar_left + fill_w, bar_y)
            fill_grad.setColorAt(0, QColor(140, 112, 18))
            fill_grad.setColorAt(0.5, QColor(212, 175, 55))
            fill_grad.setColorAt(1, QColor(245, 200, 66))
            p.setBrush(QBrush(fill_grad))
            fill_path = QPainterPath()
            fill_path.addRoundedRect(QRectF(bar_left, bar_y, fill_w, bar_h), 3, 3)
            p.drawPath(fill_path)

            # Shimmer effect — a bright line that moves across the fill
            if self._progress < 100:
                shimmer_x = bar_left + fill_w - 30 + 15 * math.sin(self._tick * 0.1)
                shimmer_grad = QRadialGradient(QPointF(shimmer_x, bar_y + bar_h / 2), 25)
                shimmer_grad.setColorAt(0, QColor(255, 255, 200, 100))
                shimmer_grad.setColorAt(1, QColor(255, 255, 200, 0))
                p.setBrush(QBrush(shimmer_grad))
                p.setClipPath(fill_path)
                p.drawRect(self.rect())
                p.setClipping(False)

        # ── Status text ──
        status_font = QFont("Inter", 10)
        p.setFont(status_font)
        p.setPen(QPen(QColor(168, 162, 148, 180)))
        p.drawText(QRectF(bar_left, bar_y + 16, bar_w, 20),
                    Qt.AlignCenter, self._status_text)

        # ── Version ──
        ver_font = QFont("Inter", 9)
        p.setFont(ver_font)
        p.setPen(QPen(QColor(92, 87, 73, 120)))
        p.drawText(QRectF(0, h - 28, w, 20), Qt.AlignCenter, "v3.0 — Persian Calendar + AI Planning")

        p.end()
