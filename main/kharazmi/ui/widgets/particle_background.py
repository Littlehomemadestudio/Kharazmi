"""
GoldParticleBackground — Animated ambient gold particle system.

A custom QWidget that renders floating gold particles using QPainter.
Particles drift slowly, fade in/out, and create a luxurious ambient
effect. Used as a background layer behind key views.

Performance: Uses a fixed particle count with QPropertyAnimation-free
approach — a simple QTimer drives the simulation at 30 FPS.
"""
from __future__ import annotations

import math
import random
from typing import Optional

from PySide6.QtCore import Qt, QTimer, QRectF, QPointF
from PySide6.QtGui import (
    QPainter, QColor, QPen, QBrush, QPainterPath, QRadialGradient,
)
from PySide6.QtWidgets import QWidget

from .theme import Palette


class Particle:
    """A single gold particle with position, velocity, size, and opacity."""
    __slots__ = ('x', 'y', 'vx', 'vy', 'size', 'opacity', 'target_opacity',
                 'fade_speed', 'life', 'max_life', 'glow')

    def __init__(self, x: float, y: float) -> None:
        self.x = x
        self.y = y
        self.vx = random.uniform(-0.3, 0.3)
        self.vy = random.uniform(-0.5, -0.05)
        self.size = random.uniform(1.5, 4.5)
        self.opacity = 0.0
        self.target_opacity = random.uniform(0.15, 0.55)
        self.fade_speed = random.uniform(0.005, 0.02)
        self.life = 0
        self.max_life = random.randint(200, 600)
        self.glow = random.random() > 0.7  # 30% have extra glow


class GoldParticleBackground(QWidget):
    """
    Ambient gold particle system — floating dust motes that give the
    app a luxurious, living feel.

    Usage:
        bg = GoldParticleBackground(parent)
        bg.raise_()  # keep on top of other children
        # OR as a bottom layer:
        layout.addWidget(bg)

    The widget is transparent except for the particles themselves.
    """

    def __init__(self, parent: Optional[QWidget] = None,
                 particle_count: int = 60) -> None:
        super().__init__(parent)
        self._particles: list[Particle] = []
        self._max_particles = particle_count
        self._paused = False

        # Timer at ~30 FPS
        self._timer = QTimer(self)
        self._timer.setInterval(33)
        self._timer.timeout.connect(self._tick)
        self._timer.start()

        self.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.setStyleSheet("background: transparent;")

    def pause(self) -> None:
        self._paused = True

    def resume(self) -> None:
        self._paused = False

    def set_particle_count(self, count: int) -> None:
        self._max_particles = count

    # ── Simulation ──

    def _tick(self) -> None:
        if self._paused:
            return

        w = self.width()
        h = self.height()
        if w < 10 or h < 10:
            return

        # Spawn new particles
        while len(self._particles) < self._max_particles:
            self._particles.append(self._spawn(w, h))

        # Update particles
        alive = []
        for p in self._particles:
            p.life += 1
            p.x += p.vx
            p.y += p.vy

            # Fade in
            if p.life < 60:
                p.opacity = min(p.opacity + p.fade_speed, p.target_opacity)
            # Fade out near end of life
            elif p.life > p.max_life - 60:
                p.opacity = max(p.opacity - p.fade_speed * 1.5, 0.0)
            # Subtle drift variation
            p.vx += random.uniform(-0.02, 0.02)
            p.vy += random.uniform(-0.01, 0.01)
            p.vx = max(-0.5, min(0.5, p.vx))
            p.vy = max(-0.6, min(0.2, p.vy))

            # Keep alive if still visible and in bounds
            if p.opacity > 0.001 and -20 < p.x < w + 20 and -20 < p.y < h + 20:
                alive.append(p)

        self._particles = alive
        self.update()

    def _spawn(self, w: int, h: int) -> Particle:
        """Spawn a particle at a random position."""
        # Spawn from edges and bottom mostly
        side = random.random()
        if side < 0.4:
            # Bottom
            x = random.uniform(0, w)
            y = h + random.uniform(0, 20)
        elif side < 0.7:
            # Left edge
            x = -random.uniform(0, 10)
            y = random.uniform(h * 0.3, h)
        elif side < 0.9:
            # Right edge
            x = w + random.uniform(0, 10)
            y = random.uniform(h * 0.3, h)
        else:
            # Random
            x = random.uniform(0, w)
            y = random.uniform(h * 0.5, h)
        return Particle(x, y)

    # ── Painting ──

    def paintEvent(self, event) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing, True)

        for pt in self._particles:
            if pt.opacity < 0.01:
                continue

            alpha = int(pt.opacity * 255)
            if pt.glow:
                # Draw glow ring
                glow_r = pt.size * 3
                grad = QRadialGradient(QPointF(pt.x, pt.y), glow_r)
                gold_glow = QColor(212, 175, 55, int(alpha * 0.25))
                grad.setColorAt(0, gold_glow)
                grad.setColorAt(1, QColor(212, 175, 55, 0))
                p.setPen(Qt.NoPen)
                p.setBrush(QBrush(grad))
                p.drawEllipse(QPointF(pt.x, pt.y), glow_r, glow_r)

            # Draw particle dot
            gold = QColor(245, 200, 66, alpha)
            p.setPen(Qt.NoPen)
            p.setBrush(QBrush(gold))
            p.drawEllipse(QPointF(pt.x, pt.y), pt.size, pt.size)

        p.end()
