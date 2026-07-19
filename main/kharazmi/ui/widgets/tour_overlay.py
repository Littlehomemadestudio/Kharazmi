"""
Guided Tour — an overlay that walks the user through the application.

Renders a semi-transparent overlay over the entire window with a
spotlight cutout around the target widget, plus a tooltip-style
popup with the current step's description and Next/Prev/Skip buttons.

Steps are defined as data — each step targets a widget by an
object-name (or callable that returns a widget) and provides a title
and body. Different tours can be defined for the Basic and Enterprise
plans.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, Optional, Any

from PySide6.QtCore import Qt, QRectF, QPointF, QSize, QTimer, QPropertyAnimation, Property, QEasingCurve
from PySide6.QtGui import (
    QPainter, QPen, QBrush, QColor, QFont, QPainterPath, QRadialGradient,
    QPolygonF, QRegion,
)
from PySide6.QtWidgets import (
    QWidget, QLabel, QPushButton, QHBoxLayout, QVBoxLayout, QDialog,
    QFrame, QGraphicsOpacityEffect, QApplication, QSizePolicy,
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
    # Optional: action to perform on the target before showing (e.g. open a menu)
    pre_show: Optional[Callable[["TourOverlay", QWidget], None]] = None


@dataclass
class Tour:
    """A sequence of TourSteps."""
    name: str
    title: str
    steps: list[TourStep] = field(default_factory=list)


# ---- Predefined tours ----

ENTERPRISE_TOUR = Tour(
    name="enterprise",
    title="Welcome to Rask Enterprise",
    steps=[
        TourStep(
            title="The Node Graph",
            body=(
                "This is the main screen of Rask — your project as a "
                "neural network of tasks. Each box is a task; each arrow "
                "is a dependency between them. Tasks on the critical path "
                "glow in gold."
            ),
            target_name="centralWidget",
            placement="right",
        ),
        TourStep(
            title="Toolbar",
            body=(
                "Use the toolbar to create new tasks, delete them, undo/redo "
                "your last actions, recalculate the schedule, auto-layout "
                "the graph, run a Monte Carlo risk simulation, or open the "
                "advisor for recommendations."
            ),
            target_finder=lambda t: t.window().findChild(QWidget, "MainToolbar") or t.window().findChild(QWidget, None, Qt.FindDirectChildrenOnly) if hasattr(t.window(), "toolbar") else None,
            placement="bottom",
        ),
        TourStep(
            title="View Switcher",
            body=(
                "Click any of these buttons to switch between five views: "
                "Graph (node diagram), Gantt (time-scaled bars), Kanban "
                "(status board), Timeline (chronological list), and "
                "Statistics (analytics dashboard)."
            ),
            target_finder=lambda t: t.window().toolbar if hasattr(t.window(), "toolbar") else None,
            placement="bottom",
        ),
        TourStep(
            title="Outline Sidebar",
            body=(
                "The left sidebar lists every task grouped by status. "
                "Double-click any task to jump to it in the graph view."
            ),
            target_finder=lambda t: t.window().sidebar if hasattr(t.window(), "sidebar") else None,
            placement="right",
        ),
        TourStep(
            title="Inspector Panel",
            body=(
                "Select any task in the graph and the Inspector on the "
                "right shows its properties: title, duration, priority, "
                "risk, status, progress, PERT 3-point estimate, and the "
                "schedule computed by CPM (early/late start, slack, "
                "criticality)."
            ),
            target_finder=lambda t: t.window().inspector if hasattr(t.window(), "inspector") else None,
            placement="left",
        ),
        TourStep(
            title="Console",
            body=(
                "The bottom panel is a built-in command console. Type "
                "'help' to see all commands. You can create tasks, link "
                "dependencies, run schedules, run Monte Carlo, save and "
                "load projects, all from the keyboard."
            ),
            target_finder=lambda t: t.window().console if hasattr(t.window(), "console") else None,
            placement="top",
        ),
        TourStep(
            title="Status Bar",
            body=(
                "The bottom status bar shows your project name, task "
                "counts, and the schedule summary (project span and "
                "critical task count) computed by the Critical Path Method."
            ),
            target_finder=lambda t: t.window().statusbar if hasattr(t.window(), "statusbar") else None,
            placement="top",
        ),
        TourStep(
            title="Command Palette",
            body=(
                "Press Ctrl+P (or click 'Commands' in the toolbar) to "
                "open the command palette — a fuzzy-searchable launcher "
                "for every action and every task in your project."
            ),
            target_finder=lambda t: t.window().toolbar if hasattr(t.window(), "toolbar") else None,
            placement="bottom",
        ),
        TourStep(
            title="Keyboard Shortcuts",
            body=(
                "Useful shortcuts:\n"
                "  N         — new task\n"
                "  Del       — delete selected\n"
                "  Ctrl+Z    — undo\n"
                "  Ctrl+Y    — redo\n"
                "  Ctrl+R    — recalculate schedule\n"
                "  Ctrl+L    — auto-layout graph\n"
                "  Ctrl+P    — command palette\n"
                "  `         — toggle console\n"
                "  F         — fit graph to view\n"
                "  Esc       — clear selection"
            ),
            target_name="centralWidget",
            placement="right",
        ),
        TourStep(
            title="You're Ready",
            body=(
                "That's the tour. Rask treats your project as a "
                "directed graph governed by real scheduling math — "
                "Critical Path Method, PERT, Monte Carlo. The more you "
                "use it, the more useful the analytics become. Good luck."
            ),
            target_name="centralWidget",
            placement="right",
        ),
    ],
)


BASIC_TOUR = Tour(
    name="basic",
    title="Welcome to Rask Basic",
    steps=[
        TourStep(
            title="Your Calendar",
            body=(
                "This is your Google-Calendar-style planner using the "
                "Persian Shamsi calendar. The grid runs Saturday through "
                "Friday (Iranian week), with month names like فروردین "
                "and تیر. Today's date is highlighted in gold."
            ),
            target_name="centralWidget",
            placement="right",
        ),
        TourStep(
            title="Top Bar",
            body=(
                "Use 'Today' to jump back to today. Use ‹ and › to move "
                "between periods (days, weeks, months, or years depending "
                "on the view). The dropdown switches between Day, Week, "
                "Month, Year, and Schedule views. The search box filters "
                "events by title, location, or attendee."
            ),
            target_name="centralWidget",
            placement="bottom",
        ),
        TourStep(
            title="Natural-Language Input",
            body=(
                "The gold bar below the top bar accepts natural-language "
                "event descriptions. Try:\n\n"
                "  • 'Lunch with Sarah tomorrow at 1 PM'\n"
                "  • 'Meeting every Monday at 10am'\n"
                "  • 'Doctor appointment next Friday 3pm'\n"
                "  • 'Standup daily at 9am'\n\n"
                "Rask parses the text and creates the event "
                "automatically — title, time, recurrence, and attendees."
            ),
            target_name="centralWidget",
            placement="right",
        ),
        TourStep(
            title="Mini Month & Calendars",
            body=(
                "The left sidebar shows a mini month picker (click any "
                "day to jump there) and a list of your calendars. Each "
                "calendar has a color and a visibility checkbox — uncheck "
                "to hide its events. Click '+' next to 'My Calendars' to "
                "create a new one, or double-click an existing calendar "
                "to rename or recolor it."
            ),
            target_name="centralWidget",
            placement="right",
        ),
        TourStep(
            title="Persian Holidays",
            body=(
                "A read-only 'Persian Holidays' calendar is included by "
                "default. It contains Nowruz, Sizdah Bedar, Islamic "
                "Republic Day, and other official Iranian holidays, all "
                "recurring yearly. Hide it from the sidebar if you prefer."
            ),
            target_name="centralWidget",
            placement="right",
        ),
        TourStep(
            title="Create Events",
            body=(
                "Click '+ Event' in the top bar to open the full event "
                "editor — title, location, description, time, calendar, "
                "color, event type (Meeting, Focus Time, Out of Office, "
                "Birthday, Task), availability, recurrence, attendees, "
                "reminders, meeting link, and attachments.\n\n"
                "Or just double-click any day cell in the month view for "
                "a quick create."
            ),
            target_name="centralWidget",
            placement="right",
        ),
        TourStep(
            title="Drag and Drop",
            body=(
                "Drag any event to reschedule it — between days in the "
                "month view, or between time slots in the day/week views. "
                "Drag the bottom edge of an event in the day/week view "
                "to change its duration."
            ),
            target_name="centralWidget",
            placement="right",
        ),
        TourStep(
            title="Recurring Events",
            body=(
                "In the event editor, set up recurrence with presets "
                "(Every day, Every weekday, Every week, Every month, "
                "Every year) or custom rules (every N days/weeks/months/"
                "years, with optional count limit)."
            ),
            target_name="centralWidget",
            placement="right",
        ),
        TourStep(
            title="Keyboard Shortcuts",
            body=(
                "Google-Calendar-style shortcuts:\n\n"
                "  c or n  — create event\n"
                "  t       — today\n"
                "  d       — day view\n"
                "  w       — week view\n"
                "  m       — month view\n"
                "  y       — year view\n"
                "  a       — schedule (agenda) view\n"
                "  + / -   — next / previous period\n"
                "  /       — focus search\n"
                "  F1      — show this tour"
            ),
            target_name="centralWidget",
            placement="right",
        ),
        TourStep(
            title="Ready to Go Deeper?",
            body=(
                "When you're ready for the node-graph view, Critical "
                "Path Method, PERT estimates, Monte Carlo simulation, "
                "and the rest — choose File → Switch to Enterprise Plan.\n\n"
                "Your calendar events are preserved across the switch."
            ),
            target_name="centralWidget",
            placement="right",
        ),
    ],
)


# ---- The overlay widget ----

class TourOverlay(QWidget):
    """Full-window overlay that highlights one widget at a time."""

    def __init__(self, tour: Tour, parent: QWidget) -> None:
        super().__init__(parent)
        self.tour = tour
        self._step_index = 0
        self._target_rect: Optional[QRectF] = None

        # Make this widget cover the parent
        self.setAttribute(Qt.WA_TransparentForMouseEvents, False)
        self.setAttribute(Qt.WA_StyledBackground, False)
        self.setFocusPolicy(Qt.StrongFocus)

        # Build the popup
        self._popup = QFrame(self)
        self._popup.setObjectName("tourPopup")
        self._popup.setStyleSheet(f"""
            QFrame#tourPopup {{
                background-color: {Palette.BG_TERTIARY};
                border: 1px solid {Palette.GOLD_PRIMARY};
                border-radius: 8px;
            }}
        """)
        # Drop shadow
        effect = QGraphicsOpacityEffect(self._popup)
        effect.setOpacity(1.0)
        self._popup.setGraphicsEffect(effect)

        popup_layout = QVBoxLayout(self._popup)
        popup_layout.setContentsMargins(20, 18, 20, 18)
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
        self._body_label.setMaximumWidth(380)
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
        self._prev_btn.clicked.connect(self._prev)
        btn_row.addWidget(self._prev_btn)

        self._next_btn = QPushButton("Next ›")
        self._next_btn.setProperty("variant", "primary")
        self._next_btn.clicked.connect(self._next)
        btn_row.addWidget(self._next_btn)

        popup_layout.addLayout(btn_row)

        self._popup.adjustSize()
        self._popup.hide()

    # ---- Show / hide ----
    def start(self) -> None:
        parent = self.parent()
        if parent is None:
            return
        self.setGeometry(parent.rect())
        self.raise_()
        self.show()
        self.setFocus()
        self._show_step()

    def _skip(self) -> None:
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
        if target is not None and target.isVisible():
            # Run pre-show action
            if step.pre_show is not None:
                try:
                    step.pre_show(self, target)
                except Exception:
                    pass
            # Map target's rect to our coordinate system
            top_left = target.mapTo(self.parent(), target.rect().topLeft()) \
                if hasattr(target, "mapTo") else None
            if top_left is not None:
                self._target_rect = QRectF(
                    top_left.x(), top_left.y(),
                    target.width(), target.height()
                )
            else:
                self._target_rect = None
        else:
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

        # Default position: bottom-right
        x = parent_rect.width() - popup_size.width() - 30
        y = parent_rect.height() - popup_size.height() - 30

        if target is not None:
            margin = 16
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

        self._popup.move(int(x), int(y))

    # ---- Painting the overlay ----
    def paintEvent(self, event) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing, True)

        # Fill with semi-transparent dark
        p.fillRect(self.rect(), QColor(0, 0, 0, 180))

        # Cut out a spotlight around the target
        if self._target_rect is not None:
            # Soft glow around the target
            margin = 8
            glow_rect = self._target_rect.adjusted(-margin, -margin, margin, margin)

            # Clear a hole (use CompositionMode_Clear)
            p.setCompositionMode(QPainter.CompositionMode_Clear)
            p.setBrush(QBrush(QColor(0, 0, 0, 0)))
            p.setPen(Qt.NoPen)
            p.drawRoundedRect(glow_rect, 6, 6)
            p.setCompositionMode(QPainter.CompositionMode_SourceOver)

            # Draw a gold border around the spotlight
            pen = QPen(QColor(Palette.GOLD_BRIGHT), 2)
            p.setPen(pen)
            p.setBrush(Qt.NoBrush)
            p.drawRoundedRect(glow_rect, 6, 6)

            # Arrow from spotlight to popup
            popup_pos = self._popup.pos()
            popup_rect = QRectF(popup_pos.x(), popup_pos.y(),
                                self._popup.width(), self._popup.height())
            arrow = self._compute_arrow(glow_rect, popup_rect)
            if arrow is not None:
                p.setBrush(QBrush(QColor(Palette.GOLD_BRIGHT)))
                p.setPen(Qt.NoPen)
                p.drawPolygon(arrow)

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
        import math
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

def start_tour(parent: QWidget, plan: str = "enterprise") -> TourOverlay:
    """Start the appropriate tour for the given plan."""
    tour = ENTERPRISE_TOUR if plan == "enterprise" else BASIC_TOUR
    overlay = TourOverlay(tour, parent)
    overlay.start()
    return overlay
