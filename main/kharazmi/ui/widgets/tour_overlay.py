"""
Guided Tour — an overlay that walks the user through the application.

Renders a semi-transparent overlay over the entire window with a
spotlight cutout around the target widget, plus a tooltip-style
popup with the current step's description and Next/Prev/Skip buttons.

Steps are defined as data — each step targets a widget by an
object-name (or callable that returns a widget) and provides a title
and body.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Callable, Optional, Any

from PySide6.QtCore import Qt, QRectF, QPointF, QSize, QTimer, QPropertyAnimation, Property, QEasingCurve, QEvent
from PySide6.QtGui import (
    QPainter, QPen, QBrush, QColor, QFont, QPainterPath, QRadialGradient,
    QPolygonF, QRegion,
)
from PySide6.QtWidgets import (
    QWidget, QLabel, QPushButton, QHBoxLayout, QVBoxLayout, QDialog,
    QFrame, QGraphicsOpacityEffect, QApplication, QSizePolicy,
    QTabWidget, QTabBar,
)

from ..theme import Palette


@dataclass
class TourStep:
    """A single step in a guided tour."""
    title: str
    body: str
    # One of these must return a QWidget that exists in the main window:
    target_finder: Optional[Callable[["TourOverlay"], Optional[QWidget]]] = None
    # Alternative: target by object name
    target_name: Optional[str] = None
    # Where to place the popup relative to the target
    # "auto" | "top" | "bottom" | "left" | "right"
    placement: str = "auto"
    # Optional: action to perform on the target before showing (e.g. switch a tab)
    # Called BEFORE the visibility check so it can make the target visible.
    pre_show: Optional[Callable[["TourOverlay", QWidget], None]] = None


@dataclass
class Tour:
    """A sequence of TourSteps."""
    name: str
    title: str
    steps: list[TourStep] = field(default_factory=list)


# ---- Helpers for building tour steps that switch tabs ----

def _win(overlay: "TourOverlay"):
    """Return the overlay's parent window."""
    return overlay.parent()


def _switch_tab(overlay: "TourOverlay", tab_index: int) -> None:
    """Switch the main tab widget to the given index and process events."""
    win = _win(overlay)
    if win is not None and hasattr(win, "_tabs"):
        win._tabs.setCurrentIndex(tab_index)
        QApplication.processEvents()


def _find_tab_bar(overlay: "TourOverlay") -> Optional[QWidget]:
    """Find the tab bar of the main window."""
    win = _win(overlay)
    if win is not None and hasattr(win, "_tabs"):
        return win._tabs.tabBar()
    return None


def _find_dashboard(overlay: "TourOverlay") -> Optional[QWidget]:
    win = _win(overlay)
    if win is not None and hasattr(win, "dashboard_view"):
        _switch_tab(overlay, 0)
        return win.dashboard_view
    return None


def _find_calendar(overlay: "TourOverlay") -> Optional[QWidget]:
    win = _win(overlay)
    if win is not None and hasattr(win, "calendar_view"):
        _switch_tab(overlay, 1)
        return win.calendar_view
    return None


def _find_calendar_toolbar(overlay: "TourOverlay") -> Optional[QWidget]:
    """Find the calendar toolbar (which contains the AI Schedule button)."""
    win = _win(overlay)
    if win is not None and hasattr(win, "calendar_view"):
        _switch_tab(overlay, 1)
        cv = win.calendar_view
        if hasattr(cv, "_toolbar"):
            return cv._toolbar
    return None


def _find_ai_schedule_btn(overlay: "TourOverlay") -> Optional[QWidget]:
    """Find the 'AI Schedule' button inside the calendar toolbar."""
    win = _win(overlay)
    if win is not None and hasattr(win, "calendar_view"):
        _switch_tab(overlay, 1)
        cv = win.calendar_view
        if hasattr(cv, "_toolbar"):
            # Find the AI Schedule button by searching QPushButton children
            for btn in cv._toolbar.findChildren(QPushButton):
                if "AI Schedule" in btn.text():
                    return btn
    return None


def _find_planner(overlay: "TourOverlay") -> Optional[QWidget]:
    win = _win(overlay)
    if win is not None and hasattr(win, "ai_planner_view"):
        _switch_tab(overlay, 2)
        return win.ai_planner_view
    return None


def _find_goal_input(overlay: "TourOverlay") -> Optional[QWidget]:
    win = _win(overlay)
    if win is not None and hasattr(win, "ai_planner_view"):
        _switch_tab(overlay, 2)
        pv = win.ai_planner_view
        if hasattr(pv, "_goal_input"):
            return pv._goal_input
    return None


def _find_plan_btn(overlay: "TourOverlay") -> Optional[QWidget]:
    win = _win(overlay)
    if win is not None and hasattr(win, "ai_planner_view"):
        _switch_tab(overlay, 2)
        pv = win.ai_planner_view
        if hasattr(pv, "_plan_btn"):
            return pv._plan_btn
    return None


def _find_schedule_btn(overlay: "TourOverlay") -> Optional[QWidget]:
    win = _win(overlay)
    if win is not None and hasattr(win, "ai_planner_view"):
        _switch_tab(overlay, 2)
        pv = win.ai_planner_view
        if hasattr(pv, "_schedule_btn"):
            return pv._schedule_btn
    return None


def _find_export_btn(overlay: "TourOverlay") -> Optional[QWidget]:
    win = _win(overlay)
    if win is not None and hasattr(win, "ai_planner_view"):
        _switch_tab(overlay, 2)
        pv = win.ai_planner_view
        # Try the header export button first, then the graph header one
        if hasattr(pv, "_export_btn"):
            return pv._export_btn
        if hasattr(pv, "_gh_export_btn"):
            return pv._gh_export_btn
    return None


def _find_graphs(overlay: "TourOverlay") -> Optional[QWidget]:
    win = _win(overlay)
    if win is not None and hasattr(win, "graphs_view"):
        _switch_tab(overlay, 3)
        return win.graphs_view
    return None


def _find_simulation(overlay: "TourOverlay") -> Optional[QWidget]:
    win = _win(overlay)
    if win is not None and hasattr(win, "simulation_view"):
        _switch_tab(overlay, 4)
        return win.simulation_view
    return None


def _find_journal(overlay: "TourOverlay") -> Optional[QWidget]:
    win = _win(overlay)
    if win is not None and hasattr(win, "journal_view"):
        _switch_tab(overlay, 5)
        return win.journal_view
    return None


def _find_statusbar(overlay: "TourOverlay") -> Optional[QWidget]:
    win = _win(overlay)
    if win is not None and hasattr(win, "statusbar"):
        return win.statusbar
    return None


def _find_central(overlay: "TourOverlay") -> Optional[QWidget]:
    """Fallback: return the central widget of the window."""
    win = _win(overlay)
    if win is not None:
        cw = win.centralWidget()
        if cw is not None:
            return cw
    return None


# ---- Predefined tours ----

RASK_TOUR = Tour(
    name="rask",
    title="Welcome to RASK",
    steps=[
        TourStep(
            title="Welcome to RASK!",
            body=(
                "RASK is your unified planning workspace — combining a Persian "
                "calendar, an AI-powered route planner, a journal for saved "
                "routes, and a full project management system.\n\n"
                "This quick tour will walk you through each section. "
                "Press Next to continue, or Skip to close."
            ),
            target_finder=_find_tab_bar,
            placement="bottom",
        ),
        TourStep(
            title="🏠 Home Dashboard",
            body=(
                "The Home tab is your landing page. It shows today's Shamsi "
                "date, a greeting in Persian, key stats at a glance, and quick "
                "action buttons to jump into creating events or planning routes."
            ),
            target_finder=_find_dashboard,
            placement="right",
        ),
        TourStep(
            title="📅 Calendar",
            body=(
                "The Calendar is a full Google-Calendar-style planner using the "
                "Persian Shamsi calendar. The grid runs Saturday through Friday "
                "(Iranian week), with month names like فروردین and تیر. "
                "Today's date is highlighted in gold.\n\n"
                "Switch between Day, Week, Month, and Year views. Drag events "
                "to reschedule them. Double-click any day to create an event."
            ),
            target_finder=_find_calendar,
            placement="right",
        ),
        TourStep(
            title="✦ AI Schedule",
            body=(
                "The AI Schedule button opens an interactive dialog where you "
                "describe what you need in natural language — and the AI builds "
                "a schedule for you. It asks clarifying questions and creates "
                "calendar events automatically.\n\n"
                "Configure your AI key in File → AI Settings first."
            ),
            target_finder=_find_ai_schedule_btn,
            placement="bottom",
        ),
        TourStep(
            title="✦ Planner & Tasks",
            body=(
                "The Planner & Tasks tab is your AI-powered route workspace. "
                "Type a goal in plain language — like 'I want to be home by "
                "9 o'clock, my car is broken' — and the AI generates a "
                "walkable route of interconnected steps with success "
                "probabilities, fallbacks, and time estimates.\n\n"
                "You can also create and manage Tasks directly on the same "
                "canvas."
            ),
            target_finder=_find_planner,
            placement="right",
        ),
        TourStep(
            title="Goal Input",
            body=(
                "Type your goal here in plain language. The AI will ask "
                "clarifying questions and then generate a step-by-step route "
                "on the workspace canvas.\n\n"
                "Press Enter or click 'Plan with AI' to start."
            ),
            target_finder=_find_goal_input,
            placement="bottom",
        ),
        TourStep(
            title="📅 Schedule in Calendar",
            body=(
                "Once the AI generates a route, this button becomes active. "
                "Click it to schedule the route's steps as calendar events — "
                "the AI will pick the best times based on your existing "
                "calendar and preferences."
            ),
            target_finder=_find_schedule_btn,
            placement="bottom",
        ),
        TourStep(
            title="📤 Export",
            body=(
                "Export your route as CSV, Excel, or HTML for sharing or "
                "further analysis. The export button becomes available once "
                "a route has been generated."
            ),
            target_finder=_find_export_btn,
            placement="bottom",
        ),
        TourStep(
            title="📊 Graphs",
            body=(
                "The Graphs tab visualizes your AI-generated routes with "
                "interactive charts. Select a route from the Journal to see "
                "its analytics here — success probability over time, critical "
                "path analysis, and more."
            ),
            target_finder=_find_graphs,
            placement="right",
        ),
        TourStep(
            title="🧪 Simulation",
            body=(
                "The Simulation tab lets you run Monte Carlo simulations on "
                "your routes. See how likely different outcomes are, explore "
                "risk factors, and make data-driven decisions about your plans."
            ),
            target_finder=_find_simulation,
            placement="right",
        ),
        TourStep(
            title="📖 Journal",
            body=(
                "Every AI-generated route is automatically saved to the "
                "Journal. Browse your past routes, review their success "
                "probabilities, add notes, and reload any route into the "
                "Planner for further editing.\n\n"
                "Click any entry to load it back into the AI Planner."
            ),
            target_finder=_find_journal,
            placement="right",
        ),
        TourStep(
            title="Status Bar",
            body=(
                "The status bar at the bottom shows event and task counts, "
                "the number of journal entries, and whether your AI service "
                "is configured and ready."
            ),
            target_finder=_find_statusbar,
            placement="top",
        ),
        TourStep(
            title="Keyboard Shortcuts",
            body=(
                "Useful shortcuts:\n\n"
                "  Ctrl+0  — Home tab\n"
                "  Ctrl+1  — Calendar tab\n"
                "  Ctrl+2  — AI Planner tab\n"
                "  Ctrl+3  — Graphs tab\n"
                "  Ctrl+4  — Simulation tab\n"
                "  Ctrl+5  — Journal tab\n"
                "  Ctrl+E  — New event\n"
                "  Ctrl+T  — New task\n"
                "  Ctrl+S  — Save\n"
                "  Ctrl+R  — Recalculate CPM\n"
                "  F1      — Show this tour\n"
                "  F11     — Fullscreen"
            ),
            target_finder=_find_tab_bar,
            placement="bottom",
        ),
        TourStep(
            title="You're Ready!",
            body=(
                "That's the tour! RASK combines a Persian calendar, "
                "AI route planning, Monte Carlo simulation, and project "
                "management into one workspace. The more you use it, the "
                "more powerful it becomes.\n\n"
                "Press Finish to start exploring. You can restart this tour "
                "anytime from Help → Take the Tour (or press F1)."
            ),
            target_finder=_find_tab_bar,
            placement="bottom",
        ),
    ],
)


# Legacy aliases — kept so existing imports don't break, but they now
# point to the unified RASK_TOUR.
ENTERPRISE_TOUR = RASK_TOUR
BASIC_TOUR = RASK_TOUR


# ---- The overlay widget ----

class TourOverlay(QWidget):
    """Full-window overlay that highlights one widget at a time."""

    def __init__(self, tour: Tour, parent: QWidget) -> None:
        super().__init__(parent)
        self.tour = tour
        self._step_index = 0
        self._target_rect: Optional[QRectF] = None

        # ── Critical: enable true translucency so the dark overlay is
        #    semi-transparent and the spotlight hole shows the parent window ──
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WA_TransparentForMouseEvents, False)
        self.setAttribute(Qt.WA_StyledBackground, False)
        self.setFocusPolicy(Qt.StrongFocus)

        # Build the popup
        self._popup = QFrame(self)
        self._popup.setObjectName("tourPopup")
        self._popup.setStyleSheet(f"""
            QFrame#tourPopup {{
                background-color: {Palette.BG_TERTIARY};
                border: 2px solid {Palette.GOLD_PRIMARY};
                border-radius: 10px;
            }}
        """)

        popup_layout = QVBoxLayout(self._popup)
        popup_layout.setContentsMargins(24, 20, 24, 20)
        popup_layout.setSpacing(10)

        # Step counter
        self._counter_label = QLabel("")
        self._counter_label.setStyleSheet(
            f"color: {Palette.TEXT_TERTIARY}; font-size: 10px; "
            f"font-weight: bold; letter-spacing: 1.5px;"
        )
        popup_layout.addWidget(self._counter_label)

        # Title
        self._title_label = QLabel("")
        self._title_label.setStyleSheet(
            f"color: {Palette.GOLD_BRIGHT}; font-size: 18px; "
            f"font-weight: bold; letter-spacing: 0.5px;"
        )
        self._title_label.setWordWrap(True)
        popup_layout.addWidget(self._title_label)

        # Body
        self._body_label = QLabel("")
        self._body_label.setStyleSheet(
            f"color: {Palette.TEXT_PRIMARY}; font-size: 13px; "
            f"line-height: 160%;"
        )
        self._body_label.setWordWrap(True)
        self._body_label.setMinimumWidth(320)
        self._body_label.setMaximumWidth(400)
        popup_layout.addWidget(self._body_label)

        # Buttons
        btn_row = QHBoxLayout()
        btn_row.setSpacing(8)

        self._skip_btn = QPushButton("Skip tour")
        self._skip_btn.setStyleSheet(
            f"background: transparent; color: {Palette.TEXT_TERTIARY}; "
            f"border: none; padding: 6px 12px; font-size: 12px;"
        )
        self._skip_btn.setCursor(Qt.PointingHandCursor)
        self._skip_btn.clicked.connect(self._skip)
        btn_row.addWidget(self._skip_btn)

        btn_row.addStretch()

        self._prev_btn = QPushButton("‹ Back")
        self._prev_btn.setStyleSheet(
            f"background-color: {Palette.BG_ELEVATED}; color: {Palette.TEXT_PRIMARY}; "
            f"border: 1px solid {Palette.BORDER_NORMAL}; border-radius: 4px; "
            f"padding: 6px 14px; font-size: 12px;"
        )
        self._prev_btn.setCursor(Qt.PointingHandCursor)
        self._prev_btn.clicked.connect(self._prev)
        btn_row.addWidget(self._prev_btn)

        self._next_btn = QPushButton("Next ›")
        self._next_btn.setStyleSheet(
            f"background-color: {Palette.GOLD_PRIMARY}; color: #000000; "
            f"border: none; border-radius: 4px; "
            f"padding: 8px 18px; font-size: 13px; font-weight: bold;"
        )
        self._next_btn.setCursor(Qt.PointingHandCursor)
        self._next_btn.clicked.connect(self._next)
        btn_row.addWidget(self._next_btn)

        popup_layout.addLayout(btn_row)

        self._popup.adjustSize()
        self._popup.hide()

        # Install event filter on parent to track resizes
        parent.installEventFilter(self)

    # ---- Event filter for parent resize ----
    def eventFilter(self, obj, event):
        """Track parent resize events to keep the overlay covering the window."""
        if obj is self.parent() and event.type() == QEvent.Type.Resize:
            self.setGeometry(0, 0, obj.width(), obj.height())
            if self.isVisible():
                self._reposition_for_current_step()
        return super().eventFilter(obj, event)

    def _reposition_for_current_step(self) -> None:
        """Recompute spotlight rect and popup position after a resize."""
        if 0 <= self._step_index < len(self.tour.steps):
            step = self.tour.steps[self._step_index]
            target = self._find_target(step)
            if target is not None and target.isVisible():
                try:
                    top_left = target.mapTo(self.parent(), target.rect().topLeft())
                    self._target_rect = QRectF(
                        top_left.x(), top_left.y(),
                        target.width(), target.height()
                    )
                except RuntimeError:
                    self._target_rect = None
            else:
                self._target_rect = None
            self._popup.adjustSize()
            self._position_popup(step.placement)
            self.update()

    # ---- Show / hide ----
    def start(self) -> None:
        parent = self.parent()
        if parent is None:
            return
        self.setGeometry(0, 0, parent.width(), parent.height())
        self.raise_()
        self.show()
        self.setFocus()
        self._show_step()

    def _skip(self) -> None:
        # Remove event filter before closing
        parent = self.parent()
        if parent is not None:
            parent.removeEventFilter(self)
        self.close()
        self.deleteLater()

    def _next(self) -> None:
        if self._step_index < len(self.tour.steps) - 1:
            self._step_index += 1
            self._show_step()
        else:
            self._skip()

    def _prev(self) -> None:
        if self._step_index > 0:
            self._step_index -= 1
            self._show_step()

    def _show_step(self) -> None:
        step = self.tour.steps[self._step_index]
        self._counter_label.setText(
            f"STEP {self._step_index + 1} / {len(self.tour.steps)}  •  {self.tour.title.upper()}"
        )
        self._title_label.setText(step.title)
        self._body_label.setText(step.body)
        self._prev_btn.setEnabled(self._step_index > 0)
        self._next_btn.setText(
            "Finish ✓" if self._step_index == len(self.tour.steps) - 1 else "Next ›"
        )

        # Find the target widget
        target = self._find_target(step)

        if target is not None:
            # Run pre-show action BEFORE the visibility check so it can
            # e.g. switch tabs to make the target widget visible.
            if step.pre_show is not None:
                try:
                    step.pre_show(self, target)
                except Exception:
                    pass
            # Process events so layout updates (from tab switches etc.) take effect
            QApplication.processEvents()

        if target is not None and target.isVisible():
            # Map target's rect to our coordinate system
            try:
                top_left = target.mapTo(self.parent(), target.rect().topLeft())
                if top_left is not None:
                    self._target_rect = QRectF(
                        top_left.x(), top_left.y(),
                        target.width(), target.height()
                    )
                else:
                    self._target_rect = None
            except RuntimeError:
                # Widget may have been deleted
                self._target_rect = None
        else:
            # Target not found or not visible — fallback to no spotlight
            self._target_rect = None

        self._popup.adjustSize()
        self._position_popup(step.placement)
        self._popup.show()
        self._popup.raise_()
        self.update()

    def _find_target(self, step: TourStep) -> Optional[QWidget]:
        parent = self.parent()
        if parent is None:
            return None
        if step.target_finder is not None:
            try:
                return step.target_finder(self)
            except Exception:
                return None
        if step.target_name is not None:
            return parent.findChild(QWidget, step.target_name)
        return None

    def _position_popup(self, placement: str) -> None:
        if self.parent() is None:
            return
        parent_rect = self.parent().rect()
        popup_size = self._popup.size()
        target = self._target_rect

        # Default position: center of screen
        x = (parent_rect.width() - popup_size.width()) // 2
        y = (parent_rect.height() - popup_size.height()) // 2

        if target is not None:
            margin = 20
            if placement == "auto":
                # Pick the side with the most space
                space_right = parent_rect.width() - target.right()
                space_left = target.left()
                space_top = target.top()
                space_bottom = parent_rect.height() - target.bottom()
                max_space = max(space_right, space_left, space_top, space_bottom)
                if max_space == space_right and space_right > popup_size.width() + margin * 2:
                    placement = "right"
                elif max_space == space_left and space_left > popup_size.width() + margin * 2:
                    placement = "left"
                elif max_space == space_bottom and space_bottom > popup_size.height() + margin * 2:
                    placement = "bottom"
                elif max_space == space_top and space_top > popup_size.height() + margin * 2:
                    placement = "top"
                else:
                    placement = "bottom_right"

            if placement == "right":
                x = target.right() + margin
                y = max(20, min(int(target.center().y() - popup_size.height() / 2),
                                parent_rect.height() - popup_size.height() - 20))
            elif placement == "left":
                x = target.left() - popup_size.width() - margin
                y = max(20, min(int(target.center().y() - popup_size.height() / 2),
                                parent_rect.height() - popup_size.height() - 20))
            elif placement == "top":
                x = max(20, min(int(target.center().x() - popup_size.width() / 2),
                                parent_rect.width() - popup_size.width() - 20))
                y = target.top() - popup_size.height() - margin
            elif placement == "bottom":
                x = max(20, min(int(target.center().x() - popup_size.width() / 2),
                                parent_rect.width() - popup_size.width() - 20))
                y = target.bottom() + margin
            elif placement == "bottom_right":
                x = parent_rect.width() - popup_size.width() - 30
                y = parent_rect.height() - popup_size.height() - 30

        # Clamp to be within parent bounds
        x = max(10, min(x, parent_rect.width() - popup_size.width() - 10))
        y = max(10, min(y, parent_rect.height() - popup_size.height() - 10))

        self._popup.move(int(x), int(y))

    # ---- Painting the overlay ----
    def paintEvent(self, event) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing, True)
        try:
            if self._target_rect is not None:
                # Create a path with the dark overlay and a hole for the spotlight
                # using OddEvenFill rule: overlapping areas are NOT filled
                margin = 8
                glow_rect = self._target_rect.adjusted(-margin, -margin, margin, margin)

                path = QPainterPath()
                # Outer rectangle (full widget area)
                path.addRect(QRectF(self.rect()))
                # Inner rectangle (spotlight hole) — overlaps with outer
                path.addRoundedRect(glow_rect, 6, 6)
                # OddEvenFill: areas covered by an odd number of subpaths are filled
                # The overlap (spotlight) is covered by 2 subpaths → not filled (hole!)
                # The dark area is covered by 1 subpath → filled
                path.setFillRule(Qt.OddEvenFill)

                p.fillPath(path, QColor(0, 0, 0, 190))

                # Draw a gold border around the spotlight
                pen = QPen(QColor(Palette.GOLD_BRIGHT), 2)
                p.setPen(pen)
                p.setBrush(Qt.NoBrush)
                p.drawRoundedRect(glow_rect, 6, 6)

                # Soft glow inside the spotlight
                gradient = QRadialGradient(glow_rect.center(), max(glow_rect.width(), glow_rect.height()) / 2)
                gradient.setColorAt(0.0, QColor(Palette.GOLD_BRIGHT, 20))
                gradient.setColorAt(1.0, QColor(Palette.GOLD_BRIGHT, 0))
                p.setPen(Qt.NoPen)
                p.setBrush(QBrush(gradient))
                p.drawRoundedRect(glow_rect, 6, 6)

                # Arrow from spotlight to popup
                try:
                    popup_pos = self._popup.pos()
                    popup_rect = QRectF(popup_pos.x(), popup_pos.y(),
                                        self._popup.width(), self._popup.height())
                    arrow = self._compute_arrow(glow_rect, popup_rect)
                    if arrow is not None:
                        p.setBrush(QBrush(QColor(Palette.GOLD_BRIGHT)))
                        p.setPen(Qt.NoPen)
                        p.drawPolygon(arrow)
                except RuntimeError:
                    pass
            else:
                # No target — fill entire overlay with semi-transparent dark
                p.fillRect(self.rect(), QColor(0, 0, 0, 190))
        finally:
            p.end()

    def _compute_arrow(self, src: QRectF, dst: QRectF) -> Optional[QPolygonF]:
        """Compute a small arrow polygon from src to dst."""
        # Find the closest edges
        src_center = src.center()
        dst_center = dst.center()

        # Choose source point: closest point on src rect to dst center
        sx = max(src.left(), min(dst_center.x(), src.right()))
        sy = max(src.top(), min(dst_center.y(), src.bottom()))

        # Choose dst point: closest point on dst rect to src center
        dx = max(dst.left(), min(src_center.x(), dst.right()))
        dy = max(dst.top(), min(src_center.y(), dst.bottom()))

        # Midpoint for the arrow base
        mid_x = (sx + dx) / 2
        mid_y = (sy + dy) / 2

        # Direction
        vx, vy = dx - sx, dy - sy
        mag = math.hypot(vx, vy)
        if mag < 30:
            return None  # too close, skip arrow
        ux, uy = vx / mag, vy / mag
        # Perpendicular
        px, py = -uy, ux

        size = 8
        tip = QPointF(dx, dy)
        base1 = QPointF(dx - ux * size * 2 + px * size,
                        dy - uy * size * 2 + py * size)
        base2 = QPointF(dx - ux * size * 2 - px * size,
                        dy - uy * size * 2 - py * size)
        return QPolygonF([tip, base1, base2])

    # ---- Keyboard ----
    def keyPressEvent(self, event) -> None:
        key = event.key()
        if key == Qt.Key_Escape:
            self._skip()
        elif key in (Qt.Key_Return, Qt.Key_Enter, Qt.Key_Right, Qt.Key_Space):
            self._next()
        elif key == Qt.Key_Left:
            self._prev()
        elif key == Qt.Key_Tab:
            self._next()
        else:
            super().keyPressEvent(event)


# ---- Convenience entry points ----

def start_tour(parent: QWidget, plan: str = "rask") -> TourOverlay:
    """Start the appropriate tour for the given plan.

    The 'plan' parameter is accepted for backward compatibility but
    all plans now use the unified RASK_TOUR.
    """
    overlay = TourOverlay(RASK_TOUR, parent)
    overlay.start()
    return overlay
