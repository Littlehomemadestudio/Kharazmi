"""
RouteGraphView — unified workspace for BOTH AI route nodes AND Tasks nodes.

This is now THE workspace — no separate Tasks window. AI-generated
route steps and user-created Tasks coexist on the same canvas.

Features:
  - TRUE streaming: nodes appear one-by-one as AI generates them
  - Complex interconnected graph: branches, parallel paths, alternative
    edges (dashed), fallback edges (dotted), merge edges (thick)
  - GENEROUS auto-layout — nodes spread out so you never need to drag apart
  - Pan / zoom / drag / customize
  - Double-click opens a proper modal NodeEditDialog with Save/Cancel
  - Floating StepDetailsPopup (closeable, draggable) on single-click
  - Insight bubbles float as overlay boxes
  - Heavily enhanced node animations
  - Tasks nodes and Route nodes share the same canvas
  - Auto-layout after AI generation with smooth animation
"""
from __future__ import annotations

import math
import random
import logging
import uuid
from collections import defaultdict, deque
from typing import Optional

from PySide6.QtCore import Qt, QRectF, QPointF, Signal, QTimer, QSizeF, QPropertyAnimation, QEasingCurve
from PySide6.QtGui import (
    QPainter, QPen, QBrush, QColor, QFont, QPainterPath, QPolygonF,
    QMouseEvent, QWheelEvent, QKeyEvent,
)
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QGraphicsView, QGraphicsScene,
    QGraphicsItem, QGraphicsRectItem, QGraphicsPathItem,
    QFrame, QPushButton, QToolButton, QSizePolicy, QApplication, QMenu,
    QComboBox,
)

from ...ai import Route, RouteStep, RouteEdge, Insight
from ...core import Project, Task, TaskId
from ..theme import Palette
from ..widgets.route_node_item import RouteNodeItem
from ..widgets.insight_bubble import InsightBubble
from ..widgets.step_details_popup import StepDetailsPopup

logger = logging.getLogger(__name__)


# Edge style by kind
EDGE_STYLES = {
    "primary":     {"color": "#D4AF37", "width": 2.2, "style": Qt.SolidLine},
    "alternative": {"color": "#5A7FA8", "width": 1.8, "style": Qt.DashLine},
    "fallback":    {"color": "#A85A5A", "width": 1.5, "style": Qt.DotLine},
    "merge":       {"color": "#F5C842", "width": 2.5, "style": Qt.SolidLine},
}

# Generous spacing — large enough so nodes NEVER overlap
# Nodes can be up to 580px wide and ~400px tall, so spacing must exceed that
X_SPACING = 620
Y_SPACING = 420


class UnifiedEdgeItem(QGraphicsPathItem):
    """A beautiful edge between two nodes with gradient, glow, arrowhead, and label."""

    def __init__(self, edge: RouteEdge, source: RouteNodeItem,
                 target: RouteNodeItem, is_critical: bool = False,
                 parent: QGraphicsItem = None) -> None:
        super().__init__(parent)
        self.edge = edge
        self._source = source
        self._target = target
        self._is_critical = is_critical

        style = EDGE_STYLES.get(edge.kind, EDGE_STYLES["primary"])
        self._style = style
        self._base_color = QColor("#F5C842") if is_critical else QColor(style["color"])
        self._glow_color = QColor(self._base_color)
        self._glow_color.setAlpha(60)

        pen = QPen(self._base_color, style["width"] + (0.8 if is_critical else 0), style["style"])
        pen.setCapStyle(Qt.RoundCap)
        pen.setJoinStyle(Qt.RoundJoin)
        self.setPen(pen)
        self.setZValue(0)
        self.setAcceptHoverEvents(True)

        # Arrow head color
        self._arrow_color = QColor(self._base_color)

        # Label text
        self._label = edge.label or ""

        self._update_path()

    def _update_path(self) -> None:
        """Compute a smooth bezier curve from source anchor to target anchor.

        Picks the best anchor points depending on relative positions:
          - source → right side (anchor_out) or bottom (anchor_bottom)
          - target → left side (anchor_in) or top (anchor_top)
        Then creates a smooth S-curve or horizontal bezier.
        """
        src_pos = self._source.pos()
        tgt_pos = self._target.pos()
        src_size = self._source.size
        tgt_size = self._target.size

        dx = tgt_pos.x() - src_pos.x()
        dy = tgt_pos.y() - src_pos.y()

        # Choose best anchor points based on relative position
        if dx >= 0:
            # Target is to the right — use right→left anchors
            src_anchor = self._source.anchor_out
            tgt_anchor = self._target.anchor_in
        else:
            # Target is to the left — use left→right anchors
            src_anchor = QPointF(self._source.mapToScene(QPointF(0, src_size.height() / 2)))
            tgt_anchor = QPointF(self._target.mapToScene(QPointF(tgt_size.width(), tgt_size.height() / 2)))

        # If mostly vertical, use top/bottom anchors instead
        if abs(dy) > abs(dx) * 2.5:
            if dy >= 0:
                src_anchor = self._source.anchor_bottom
                tgt_anchor = self._target.anchor_top
            else:
                src_anchor = QPointF(self._source.mapToScene(QPointF(src_size.width() / 2, 0)))
                tgt_anchor = QPointF(self._target.mapToScene(QPointF(tgt_size.width() / 2, tgt_size.height())))

        path = QPainterPath()
        path.moveTo(src_anchor)

        adx = tgt_anchor.x() - src_anchor.x()
        ady = tgt_anchor.y() - src_anchor.y()

        # Control point offsets — make curves generous and smooth
        if abs(adx) > 20:
            # Horizontal-ish connection
            cp_offset = max(abs(adx) * 0.4, 60)
            if dx >= 0:
                cp1 = QPointF(src_anchor.x() + cp_offset, src_anchor.y())
                cp2 = QPointF(tgt_anchor.x() - cp_offset, tgt_anchor.y())
            else:
                cp1 = QPointF(src_anchor.x() - cp_offset, src_anchor.y())
                cp2 = QPointF(tgt_anchor.x() + cp_offset, tgt_anchor.y())
            path.cubicTo(cp1, cp2, tgt_anchor)
        else:
            # Vertical connection
            cp_offset = max(abs(ady) * 0.4, 60)
            if dy >= 0:
                cp1 = QPointF(src_anchor.x(), src_anchor.y() + cp_offset)
                cp2 = QPointF(tgt_anchor.x(), tgt_anchor.y() - cp_offset)
            else:
                cp1 = QPointF(src_anchor.x(), src_anchor.y() - cp_offset)
                cp2 = QPointF(tgt_anchor.x(), tgt_anchor.y() + cp_offset)
            path.cubicTo(cp1, cp2, tgt_anchor)

        self.setPath(path)

    def paint(self, painter: QPainter, option, widget=None) -> None:
        painter.setRenderHint(QPainter.Antialiasing, True)

        path = self.path()
        if path.elementCount() < 2:
            return

        # 1. Draw glow/shadow for critical edges
        if self._is_critical:
            glow_pen = QPen(QColor(245, 200, 66, 40), self._style["width"] + 6, Qt.SolidLine)
            glow_pen.setCapStyle(Qt.RoundCap)
            painter.setPen(glow_pen)
            painter.drawPath(path)
            # Inner glow
            glow_pen2 = QPen(QColor(245, 200, 66, 25), self._style["width"] + 12, Qt.SolidLine)
            glow_pen2.setCapStyle(Qt.RoundCap)
            painter.setPen(glow_pen2)
            painter.drawPath(path)

        # 2. Draw the main edge line
        painter.setPen(self.pen())
        painter.drawPath(path)

        # 3. Draw arrowhead — larger and more elegant
        tgt_anchor = self._target.anchor_in
        # Recalculate target anchor based on same logic as _update_path
        src_pos = self._source.pos()
        tgt_pos = self._target.pos()
        tgt_size = self._target.size
        dx = tgt_pos.x() - src_pos.x()
        dy = tgt_pos.y() - src_pos.y()

        if abs(dy) > abs(dx) * 2.5:
            if dy >= 0:
                tgt_anchor = self._target.anchor_top
            else:
                tgt_anchor = QPointF(self._target.mapToScene(QPointF(tgt_size.width() / 2, tgt_size.height())))
        elif dx < 0:
            tgt_anchor = QPointF(self._target.mapToScene(QPointF(tgt_size.width(), tgt_size.height() / 2)))

        pt_before = path.pointAtPercent(max(0, 1.0 - 0.04))
        angle = math.atan2(tgt_anchor.y() - pt_before.y(), tgt_anchor.x() - pt_before.x())

        arrow_size = 13
        p1 = QPointF(
            tgt_anchor.x() - arrow_size * math.cos(angle - math.pi / 7),
            tgt_anchor.y() - arrow_size * math.sin(angle - math.pi / 7),
        )
        p2 = QPointF(
            tgt_anchor.x() - arrow_size * math.cos(angle + math.pi / 7),
            tgt_anchor.y() - arrow_size * math.sin(angle + math.pi / 7),
        )

        # Draw arrow with slight gradient
        arrow = QPolygonF([tgt_anchor, p1, p2])
        painter.setBrush(QBrush(self._arrow_color))
        painter.setPen(Qt.NoPen)
        painter.drawPolygon(arrow)

        # 4. Draw edge label if present
        if self._label:
            mid = path.pointAtPercent(0.5)
            label_font = QFont("Inter", 8)
            painter.setFont(label_font)
            # Background pill
            fm = painter.fontMetrics()
            label_w = fm.horizontalAdvance(self._label) + 12
            label_h = fm.height() + 6
            label_rect = QRectF(mid.x() - label_w / 2, mid.y() - label_h / 2 - 2, label_w, label_h)
            painter.setBrush(QBrush(QColor(Palette.BG_ELEVATED)))
            painter.setPen(QPen(QColor(self._base_color.red(), self._base_color.green(),
                                       self._base_color.blue(), 120), 1))
            painter.drawRoundedRect(label_rect, 6, 6)
            # Label text
            painter.setPen(QPen(self._base_color))
            painter.drawText(label_rect, Qt.AlignCenter, self._label)

    def hoverEnterEvent(self, event) -> None:
        # Brighten on hover
        bright = QColor(self._base_color)
        bright = bright.lighter(140)
        pen = QPen(bright, self._style["width"] + 1.0, self._style["style"])
        pen.setCapStyle(Qt.RoundCap)
        pen.setJoinStyle(Qt.RoundJoin)
        self.setPen(pen)
        self.setZValue(5)
        super().hoverEnterEvent(event)

    def hoverLeaveEvent(self, event) -> None:
        pen = QPen(self._base_color, self._style["width"] + (0.8 if self._is_critical else 0), self._style["style"])
        pen.setCapStyle(Qt.RoundCap)
        pen.setJoinStyle(Qt.RoundJoin)
        self.setPen(pen)
        self.setZValue(0)
        super().hoverLeaveEvent(event)

    def itemChange(self, change, value):
        if change == QGraphicsItem.ItemSceneHasChanged:
            self._update_path()
        return super().itemChange(change, value)


class UnifiedGraphView(QGraphicsView):
    """
    Unified canvas for both AI route nodes AND Tasks nodes.

    Single-click: show StepDetailsPopup for quick viewing.
    Double-click: open NodeEditDialog modal with Save/Cancel.
    Right-click: context menu with edit/delete/breakdown.
    Ctrl+L or Auto Layout button: spread nodes nicely.
    """

    stepSelected = Signal(object)      # RouteStep | None
    stepDoubleClicked = Signal(object)  # RouteStep
    insightSelected = Signal(object)    # Insight | None
    taskCreated = Signal(str, float, float)  # title, x, y
    stepBreakdownRequested = Signal(str)  # step_id
    stepFieldChanged = Signal(str, str, object)  # step_id, field, value

    def __init__(self, parent: QWidget = None) -> None:
        super().__init__(parent)
        self._route: Optional[Route] = None
        self._project: Optional[Project] = None
        self._node_items: dict[str, RouteNodeItem] = {}  # unified: both route steps and tasks
        self._edge_items: list[UnifiedEdgeItem] = []
        self._edges_by_node: dict[str, list[UnifiedEdgeItem]] = {}  # step_id -> list of edges for O(1) lookup
        self._bubble_items: dict[str, InsightBubble] = {}
        self._details_popup: Optional[StepDetailsPopup] = None
        self._layout_anims: list[QPropertyAnimation] = []  # track layout animations for cleanup
        self._pending_edges: list[RouteEdge] = []  # edges waiting for both nodes to exist

        self._scene = QGraphicsScene(self)
        self._scene.setSceneRect(-5000, -5000, 10000, 10000)
        self._scene.selectionChanged.connect(self._update_selection_ui)
        self.setScene(self._scene)
        self.setRenderHint(QPainter.Antialiasing, True)
        self.setRenderHint(QPainter.TextAntialiasing, True)
        self.setViewportUpdateMode(QGraphicsView.FullViewportUpdate)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.setTransformationAnchor(QGraphicsView.AnchorUnderMouse)
        self.setResizeAnchor(QGraphicsView.AnchorUnderMouse)
        self.setDragMode(QGraphicsView.NoDrag)
        self.setContextMenuPolicy(Qt.DefaultContextMenu)

        self._panning = False
        self._pan_last = None
        self._click_timer = QTimer()
        self._click_timer.setSingleShot(True)
        self._click_timer.setInterval(200)  # wait to distinguish single from double click
        self._pending_click_step_id = None

        # Rubber band selection state
        self._rubber_band_active = False
        self._rubber_band_start = None  # scene coords
        self._rubber_band_rect: Optional[QGraphicsRectItem] = None
        self._rubber_band_color = QColor(Palette.GOLD_PRIMARY)
        self._rubber_band_color.setAlpha(30)
        self._rubber_band_border = QColor(Palette.GOLD_BRIGHT)
        self._rubber_band_border.setAlpha(160)

        # Toolbar for auto-layout
        self._build_toolbar()

    def _build_toolbar(self) -> None:
        """Build a floating toolbar with layout style selector, zoom controls."""
        toolbar = QFrame(self)
        toolbar.setStyleSheet(f"""
            QFrame {{
                background-color: {Palette.BG_ELEVATED};
                border: 1px solid {Palette.BORDER_NORMAL};
                border-radius: 6px;
            }}
        """)
        toolbar_layout = QHBoxLayout(toolbar)
        toolbar_layout.setContentsMargins(6, 4, 6, 4)
        toolbar_layout.setSpacing(4)

        # Layout style selector
        layout_label = QLabel("Layout:")
        layout_label.setStyleSheet(f"""
            color: {Palette.TEXT_TERTIARY};
            font-size: 10px;
            font-weight: bold;
            background: transparent;
            border: none;
        """)
        toolbar_layout.addWidget(layout_label)

        self._layout_combo = QComboBox()
        self._layout_combo.addItem("🌊 Organic Flow", "organic")
        self._layout_combo.addItem("🌀 Radial Burst", "radial")
        self._layout_combo.addItem("🔀 Mind Map", "mindmap")
        self._layout_combo.addItem("⚡ Layered DAG", "layered")
        self._layout_combo.addItem("💫 Force Field", "force")
        self._layout_combo.setStyleSheet(f"""
            QComboBox {{
                background-color: {Palette.BG_TERTIARY};
                color: {Palette.TEXT_PRIMARY};
                border: 1px solid {Palette.BORDER_NORMAL};
                border-radius: 4px;
                padding: 4px 8px;
                font-size: 11px;
                min-width: 130px;
            }}
            QComboBox:hover {{
                border: 1px solid {Palette.GOLD_PRIMARY};
            }}
            QComboBox::drop-down {{
                border: none;
                width: 20px;
            }}
            QComboBox QAbstractItemView {{
                background-color: {Palette.BG_DEEPEST};
                color: {Palette.TEXT_PRIMARY};
                border: 1px solid {Palette.BORDER_NORMAL};
                selection-background-color: {Palette.BG_HOVER};
                selection-color: {Palette.GOLD_BRIGHT};
                padding: 4px;
            }}
        """)
        toolbar_layout.addWidget(self._layout_combo)

        auto_layout_btn = QPushButton("⊞ Layout")
        auto_layout_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: {Palette.GOLD_PRIMARY};
                color: {Palette.TEXT_ON_GOLD};
                border: none;
                border-radius: 4px;
                padding: 6px 14px;
                font-size: 11px;
                font-weight: bold;
            }}
            QPushButton:hover {{
                background-color: {Palette.GOLD_BRIGHT};
            }}
        """)
        auto_layout_btn.clicked.connect(self.auto_layout)
        toolbar_layout.addWidget(auto_layout_btn)

        fit_btn = QPushButton("⊡ Fit")
        fit_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: {Palette.BG_TERTIARY};
                color: {Palette.TEXT_SECONDARY};
                border: 1px solid {Palette.BORDER_NORMAL};
                border-radius: 4px;
                padding: 6px 10px;
                font-size: 11px;
            }}
            QPushButton:hover {{
                background-color: {Palette.BG_HOVER};
            }}
        """)
        fit_btn.clicked.connect(self.fit_all)
        toolbar_layout.addWidget(fit_btn)

        zoom_in_btn = QPushButton("+")
        zoom_in_btn.setFixedSize(28, 28)
        zoom_in_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: {Palette.BG_TERTIARY};
                color: {Palette.TEXT_PRIMARY};
                border: 1px solid {Palette.BORDER_NORMAL};
                border-radius: 4px;
                font-size: 16px;
                font-weight: bold;
            }}
            QPushButton:hover {{
                background-color: {Palette.BG_HOVER};
            }}
        """)
        zoom_in_btn.clicked.connect(lambda: self.scale(1.2, 1.2))
        toolbar_layout.addWidget(zoom_in_btn)

        zoom_out_btn = QPushButton("−")
        zoom_out_btn.setFixedSize(28, 28)
        zoom_out_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: {Palette.BG_TERTIARY};
                color: {Palette.TEXT_PRIMARY};
                border: 1px solid {Palette.BORDER_NORMAL};
                border-radius: 4px;
                font-size: 16px;
                font-weight: bold;
            }}
            QPushButton:hover {{
                background-color: {Palette.BG_HOVER};
            }}
        """)
        zoom_out_btn.clicked.connect(lambda: self.scale(1/1.2, 1/1.2))
        toolbar_layout.addWidget(zoom_out_btn)

        # Separator
        sep = QFrame()
        sep.setFixedWidth(1)
        sep.setFixedHeight(20)
        sep.setStyleSheet(f"background-color: {Palette.BORDER_NORMAL}; border: none;")
        toolbar_layout.addWidget(sep)

        # Delete Selected button
        self._delete_sel_btn = QPushButton("🗑 Delete")
        self._delete_sel_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: {Palette.STATUS_BLOCKED};
                color: {Palette.TEXT_PRIMARY};
                border: none;
                border-radius: 4px;
                padding: 6px 10px;
                font-size: 11px;
                font-weight: bold;
            }}
            QPushButton:hover {{
                background-color: #C04040;
            }}
        """)
        self._delete_sel_btn.clicked.connect(self._delete_selected_nodes)
        self._delete_sel_btn.setVisible(False)  # Only visible when nodes are selected
        toolbar_layout.addWidget(self._delete_sel_btn)

        # Selection count label
        self._sel_count_label = QLabel("")
        self._sel_count_label.setStyleSheet(f"""
            color: {Palette.TEXT_TERTIARY};
            font-size: 10px;
            background: transparent;
            border: none;
        """)
        self._sel_count_label.setVisible(False)
        toolbar_layout.addWidget(self._sel_count_label)

        self._toolbar = toolbar

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        # Position toolbar at top-right
        tb = self._toolbar
        tb.move(self.width() - tb.width() - 12, 12)

    # ---- Project sync ----
    def set_project(self, project: Project) -> None:
        self._project = project
        self._sync_tasks_to_canvas()

    def _sync_tasks_to_canvas(self) -> None:
        """Sync project tasks to the canvas as route-step-like nodes."""
        if self._project is None:
            return
        # Remove task nodes that no longer exist
        task_ids = {str(t.id) for t in self._project.tasks()}
        for nid in list(self._node_items.keys()):
            item = self._node_items[nid]
            if item.step.branch == "tasks" and nid not in task_ids:
                self._scene.removeItem(item)
                del self._node_items[nid]

        for task in self._project.tasks():
            tid = str(task.id)
            if tid in self._node_items:
                # Update existing
                item = self._node_items[tid]
                item.step.title = task.title
                item.step.description = task.description
                item.step.duration_minutes = task.duration.minutes
                item._compute_size()
                item.prepareGeometryChange()
                item.update()
                continue
            # Create new node for this task
            x, y = task.x, task.y
            if x == 0 and y == 0:
                x = random.randint(-200, 200)
                y = random.randint(-200, 200)
            step = self._task_to_step(task)
            self._add_node(step, x=task.x, y=task.y, animate=True)

    @staticmethod
    def _task_to_step(task) -> RouteStep:
        """Convert a Task to a RouteStep for display on the canvas."""
        return RouteStep(
            id=str(task.id),
            title=task.title,
            duration_minutes=task.duration.minutes,
            success_probability=0.5,
            location="",
            description=task.description,
            fallback="",
            branch="tasks",
            kind="action",
        )

    # ---- Loading ----
    def set_route(self, route: Optional[Route]) -> None:
        self._route = route
        if route is None:
            return
        # Don't clear existing tasks — just add route nodes
        # Clear existing route nodes first (those with branch != "tasks")
        route_node_ids = [s.id for s in route.steps]
        to_remove = [nid for nid, item in self._node_items.items()
                     if nid in route_node_ids]
        for nid in to_remove:
            item = self._node_items.pop(nid)
            # Stop animations/timers
            if hasattr(item, '_pulse_timer') and item._pulse_timer.isActive():
                item._pulse_timer.stop()
            self._scene.removeItem(item)
            item.deleteLater()
        # Clear route edges
        for edge in list(self._edge_items):
            self._scene.removeItem(edge)
        self._edge_items.clear()
        self._edges_by_node.clear()
        # Clear insight bubbles
        for bubble in list(self._bubble_items.values()):
            self._scene.removeItem(bubble)
        self._bubble_items.clear()

        # Add route nodes (will be added incrementally via add_step)
        layout = self._compute_layout(route)
        critical_path = self._compute_critical_path(route)

        for i, step in enumerate(route.steps):
            self._add_node(step, *layout.get(step.id, (0, 0)),
                           animate=True, delay_ms=i * 80)

        # Add edges — with fuzzy ID matching
        seen_edges: set[tuple[str, str, str]] = set()
        for edge in route.edges:
            src = self._fuzzy_match_step_id(edge.source_id) or edge.source_id
            tgt = self._fuzzy_match_step_id(edge.target_id) or edge.target_id
            if src != edge.source_id or tgt != edge.target_id:
                edge = RouteEdge(source_id=src, target_id=tgt,
                                 kind=edge.kind, label=edge.label)
            key = (edge.source_id, edge.target_id, edge.kind)
            if key in seen_edges:
                continue
            seen_edges.add(key)
            self._add_edge(edge, is_crit=edge.source_id in critical_path and edge.target_id in critical_path)
        for step in route.steps:
            for dep_id in step.depends_on:
                resolved_dep = self._fuzzy_match_step_id(dep_id) or dep_id
                key = (resolved_dep, step.id, "primary")
                if key in seen_edges:
                    continue
                seen_edges.add(key)
                edge = RouteEdge(source_id=resolved_dep, target_id=step.id, kind="primary")
                self._add_edge(edge, is_crit=resolved_dep in critical_path and step.id in critical_path)

        # FALLBACK: If no edges were created, connect steps sequentially
        if not self._edge_items and len(route.steps) > 1:
            for i in range(len(route.steps) - 1):
                src = route.steps[i]
                tgt = route.steps[i + 1]
                key = (src.id, tgt.id, "primary")
                if key not in seen_edges:
                    seen_edges.add(key)
                    edge = RouteEdge(source_id=src.id, target_id=tgt.id, kind="primary")
                    self._add_edge(edge, is_crit=src.id in critical_path and tgt.id in critical_path)

        # Add insight bubbles
        for insight in route.insights:
            self._add_insight(insight)

        # Auto-layout after a short delay so animations finish first
        QTimer.singleShot(len(route.steps) * 80 + 300, self.auto_layout)

    def _add_node(self, step: RouteStep, x: float = 0, y: float = 0,
                  animate: bool = False, delay_ms: int = 0) -> RouteNodeItem:
        """Add a single node to the canvas."""
        item = RouteNodeItem(step)
        item.setPos(x, y)
        item.nodeClicked.connect(self._on_node_clicked)
        item.nodeDoubleClicked.connect(self._on_node_double_clicked)
        item.nodeMoved.connect(self._on_node_moved)
        item.nodeEdited.connect(self._on_node_edited)
        item.nodeEditRequested.connect(self._on_node_edit_requested)
        item.nodePositionChanged.connect(self._on_node_position_changed)
        self._scene.addItem(item)
        self._node_items[step.id] = item
        if animate:
            item.animate_entrance(delay_ms=delay_ms)
        return item

    def _add_edge(self, edge: RouteEdge, is_crit: bool = False) -> None:
        source = self._node_items.get(edge.source_id)
        target = self._node_items.get(edge.target_id)
        if source is None or target is None:
            logger.debug(
                "Edge dropped: source=%s (%s), target=%s (%s) — node missing",
                edge.source_id, "exists" if edge.source_id in self._node_items else "MISSING",
                edge.target_id, "exists" if edge.target_id in self._node_items else "MISSING",
            )
            return
        edge_item = UnifiedEdgeItem(edge, source, target, is_critical=is_crit)
        self._scene.addItem(edge_item)
        self._edge_items.append(edge_item)
        # Maintain edge lookup index for O(1) access during drag
        self._edges_by_node.setdefault(edge.source_id, []).append(edge_item)
        self._edges_by_node.setdefault(edge.target_id, []).append(edge_item)

    def _add_insight(self, insight: Insight) -> None:
        bubble_id = f"ib-{uuid.uuid4().hex[:8]}"
        bubble = InsightBubble(insight, bubble_id)
        pos = self._compute_bubble_position(insight, bubble)
        bubble.setPos(pos)
        bubble.bubbleClicked.connect(self._on_bubble_clicked)
        self._scene.addItem(bubble)
        self._bubble_items[bubble_id] = bubble

    # ---- Incremental addition (for streaming) ----
    def _fuzzy_match_step_id(self, ref_id: str) -> Optional[str]:
        """Try to find a step ID on the canvas that matches *ref_id* even if
        the exact string differs.  Handles cases like the AI using 'step_1'
        in the edges array but '1' in the steps array (or vice versa).
        Returns the matched step_id or None.
        """
        if ref_id in self._node_items:
            return ref_id
        # Try common prefixes/suffixes
        for candidate in (f"step_{ref_id}", ref_id.replace("step_", ""),
                          ref_id.replace("step-", ""), f"step-{ref_id}",
                          ref_id.lstrip("0"), f"0{ref_id}"):
            if candidate in self._node_items:
                return candidate
        # Try numeric match — extract the trailing number
        import re as _re
        m = _re.search(r'(\d+)', ref_id)
        if m:
            num = m.group(1)
            for nid in self._node_items:
                m2 = _re.search(r'(\d+)', nid)
                if m2 and m2.group(1) == num:
                    return nid
        return None

    def add_step(self, step: RouteStep) -> None:
        """Add a single step to the canvas (for TRUE streaming — one at a time)."""
        if step.id in self._node_items:
            return
        # Find a position — use rank-based layout
        if self._route is None:
            self._route = Route(goal="", steps=[], edges=[])
        self._route.steps.append(step)
        # Recompute layout for all steps, but only position the new one
        layout = self._compute_layout(self._route)
        x, y = layout.get(step.id, (0, 0))
        self._add_node(step, x, y, animate=True, delay_ms=0)
        # Process any pending edges that were waiting for this node
        self._process_pending_edges()

    def add_edge(self, edge: RouteEdge) -> None:
        """Add a single edge (for streaming).

        If both nodes don't exist yet, queues the edge in _pending_edges.
        It will be retried in finalize_route() or when the missing node arrives.
        Uses fuzzy ID matching to handle AI ID format inconsistencies.
        """
        # Try fuzzy matching for source/target IDs
        resolved_src = self._fuzzy_match_step_id(edge.source_id)
        resolved_tgt = self._fuzzy_match_step_id(edge.target_id)

        if resolved_src and resolved_src != edge.source_id:
            logger.debug("Fuzzy matched edge source: %s -> %s", edge.source_id, resolved_src)
            edge = RouteEdge(source_id=resolved_src, target_id=edge.target_id,
                             kind=edge.kind, label=edge.label)
        if resolved_tgt and resolved_tgt != edge.target_id:
            logger.debug("Fuzzy matched edge target: %s -> %s", edge.target_id, resolved_tgt)
            edge = RouteEdge(source_id=edge.source_id, target_id=resolved_tgt,
                             kind=edge.kind, label=edge.label)

        if edge.source_id not in self._node_items or edge.target_id not in self._node_items:
            # Queue for later — don't lose it
            self._pending_edges.append(edge)
            return
        # Check if already exists
        for existing in self._edge_items:
            if (existing.edge.source_id == edge.source_id and
                existing.edge.target_id == edge.target_id and
                existing.edge.kind == edge.kind):
                return
        if self._route is not None:
            self._route.edges.append(edge)
        self._add_edge(edge)

    def _process_pending_edges(self) -> None:
        """Try to add all pending edges whose nodes now exist."""
        still_pending: list[RouteEdge] = []
        for edge in self._pending_edges:
            # Try fuzzy matching again
            resolved_src = self._fuzzy_match_step_id(edge.source_id)
            resolved_tgt = self._fuzzy_match_step_id(edge.target_id)
            if resolved_src and resolved_src != edge.source_id:
                edge = RouteEdge(source_id=resolved_src, target_id=edge.target_id,
                                 kind=edge.kind, label=edge.label)
            if resolved_tgt and resolved_tgt != edge.target_id:
                edge = RouteEdge(source_id=edge.source_id, target_id=resolved_tgt,
                                 kind=edge.kind, label=edge.label)

            if edge.source_id in self._node_items and edge.target_id in self._node_items:
                # Check duplicate
                exists = any(
                    existing.edge.source_id == edge.source_id and
                    existing.edge.target_id == edge.target_id and
                    existing.edge.kind == edge.kind
                    for existing in self._edge_items
                )
                if not exists:
                    self._add_edge(edge)
            else:
                still_pending.append(edge)
        self._pending_edges = still_pending

    def add_insight(self, insight: Insight) -> None:
        """Add a single insight bubble (for streaming)."""
        if self._route is not None:
            self._route.insights.append(insight)
        self._add_insight(insight)

    def finalize_route(self, route: Route) -> None:
        """After streaming adds all steps, ensure ALL edges exist.

        This creates edges from both route.edges AND step.depends_on,
        similar to set_route() but without removing/re-adding existing nodes.
        Also processes any pending edges that were queued during streaming.
        Also recomputes the critical path and updates edge critical styling.
        Uses fuzzy ID matching for robustness against AI ID format inconsistencies.
        Adds fallback sequential edges when no explicit edges exist.
        """
        # Replace the partial route with the complete one
        self._route = route

        # Process any pending edges from streaming
        self._process_pending_edges()

        # Compute critical path for edge styling
        critical_path = self._compute_critical_path(route)
        critical_set = set(critical_path)

        seen_edges: set[tuple[str, str, str]] = set()

        # Track existing edges
        for existing in self._edge_items:
            key = (existing.edge.source_id, existing.edge.target_id, existing.edge.kind)
            seen_edges.add(key)

        # Add edges from route.edges (explicit edges) — with fuzzy ID matching
        for edge in route.edges:
            src = self._fuzzy_match_step_id(edge.source_id) or edge.source_id
            tgt = self._fuzzy_match_step_id(edge.target_id) or edge.target_id
            if src != edge.source_id or tgt != edge.target_id:
                logger.debug("finalize_route fuzzy: %s->%s, %s->%s",
                             edge.source_id, src, edge.target_id, tgt)
                edge = RouteEdge(source_id=src, target_id=tgt,
                                 kind=edge.kind, label=edge.label)
            key = (edge.source_id, edge.target_id, edge.kind)
            if key in seen_edges:
                continue
            seen_edges.add(key)
            is_crit = edge.source_id in critical_set and edge.target_id in critical_set
            self._add_edge(edge, is_crit=is_crit)

        # Add implicit edges from step.depends_on — with fuzzy matching
        for step in route.steps:
            for dep_id in step.depends_on:
                resolved_dep = self._fuzzy_match_step_id(dep_id) or dep_id
                key = (resolved_dep, step.id, "primary")
                if key in seen_edges:
                    continue
                seen_edges.add(key)
                # Only add if both nodes exist
                if resolved_dep in self._node_items and step.id in self._node_items:
                    edge = RouteEdge(source_id=resolved_dep, target_id=step.id, kind="primary")
                    is_crit = resolved_dep in critical_set and step.id in critical_set
                    self._add_edge(edge, is_crit=is_crit)

        # FALLBACK: If no edges were created at all, connect steps sequentially
        # This handles the case where the AI generates no edges and no depends_on
        if not self._edge_items and len(route.steps) > 1:
            logger.warning("No edges found — creating sequential fallback edges")
            for i in range(len(route.steps) - 1):
                src = route.steps[i]
                tgt = route.steps[i + 1]
                if src.id in self._node_items and tgt.id in self._node_items:
                    key = (src.id, tgt.id, "primary")
                    if key not in seen_edges:
                        seen_edges.add(key)
                        edge = RouteEdge(source_id=src.id, target_id=tgt.id, kind="primary")
                        is_crit = src.id in critical_set and tgt.id in critical_set
                        self._add_edge(edge, is_crit=is_crit)

        # Update existing edges' critical path styling
        for edge_item in list(self._edge_items):
            try:
                src_id = edge_item.edge.source_id
                tgt_id = edge_item.edge.target_id
                is_crit = src_id in critical_set and tgt_id in critical_set
                style = EDGE_STYLES.get(edge_item.edge.kind, EDGE_STYLES["primary"])
                color = QColor("#F5C842") if is_crit else QColor(style["color"])
                pen = QPen(color, style["width"] + (0.5 if is_crit else 0), style["style"])
                pen.setCapStyle(Qt.RoundCap)
                edge_item.setPen(pen)
                edge_item._arrow_color = color
                edge_item._is_critical = is_crit
            except RuntimeError:
                pass  # edge item already deleted

    def add_steps_and_edges(self, steps: list[RouteStep], edges: list[RouteEdge],
                             insights: list[Insight] = None) -> None:
        """Add multiple steps/edges/insights (for 'continue working')."""
        for i, step in enumerate(steps):
            self.add_step(step)
        for edge in edges:
            self.add_edge(edge)
        if insights:
            for insight in insights:
                self.add_insight(insight)
        # Auto-layout after adding
        QTimer.singleShot(500, self.auto_layout)

    # Keep alias for backward compat
    def add_insights(self, insights: list[Insight]) -> None:
        self.add_steps_and_edges([], [], insights)

    def _compute_bubble_position(self, insight: Insight, bubble) -> QPointF:
        if insight.anchor_step_id and insight.anchor_step_id in self._node_items:
            node = self._node_items[insight.anchor_step_id]
            node_pos = node.pos()
            node_w = node._width
            return QPointF(node_pos.x() + node_w + 60, node_pos.y() + 20)
        items_rect = self._scene.itemsBoundingRect()
        if items_rect.isNull():
            return QPointF(insight.x_hint * 800 - 400, insight.y_hint * 600 - 300)
        x = items_rect.left() + insight.x_hint * items_rect.width()
        y = items_rect.top() - 120 - insight.y_hint * 100
        return QPointF(x, y)

    # ---- Layout & analysis ----
    def _get_layout_style(self) -> str:
        """Get the currently selected layout style from the combo box."""
        if hasattr(self, '_layout_combo') and self._layout_combo is not None:
            return self._layout_combo.currentData() or "organic"
        return "organic"

    def _compute_layout(self, route: Route) -> dict[str, tuple[float, float]]:
        """Dispatch to the selected layout algorithm."""
        style = self._get_layout_style()
        if style == "radial":
            return self._layout_radial(route)
        elif style == "mindmap":
            return self._layout_mindmap(route)
        elif style == "layered":
            return self._layout_layered(route)
        elif style == "force":
            return self._layout_force(route)
        else:
            return self._layout_organic(route)

    # ---- Shared helpers for layouts ----
    def _build_topology(self, route: Route):
        """Build topological data structures shared by all layouts.
        Returns (steps_by_id, ranks, edge_pairs, succ, pred, branch_lanes, node_sizes).
        """
        rng = random.Random(42)

        steps_by_id = {s.id: s for s in route.steps}
        ranks: dict[str, int] = {}
        in_degree: dict[str, int] = {s.id: 0 for s in route.steps}
        succ: dict[str, list[str]] = {s.id: [] for s in route.steps}
        pred: dict[str, list[str]] = {s.id: [] for s in route.steps}

        edge_pairs: set[tuple[str, str]] = set()
        for s in route.steps:
            for dep_id in s.depends_on:
                if dep_id in in_degree:
                    edge_pairs.add((dep_id, s.id))
        for e in route.edges:
            if e.source_id in in_degree and e.target_id in in_degree:
                edge_pairs.add((e.source_id, e.target_id))

        for src, tgt in edge_pairs:
            in_degree[tgt] += 1
            if tgt not in succ[src]:
                succ[src].append(tgt)
            if src not in pred[tgt]:
                pred[tgt].append(src)

        queue = deque([sid for sid, d in in_degree.items() if d == 0])
        for sid in queue:
            ranks[sid] = 0
        while queue:
            cur = queue.popleft()
            for nxt in succ[cur]:
                in_degree[nxt] -= 1
                ranks[nxt] = max(ranks.get(nxt, 0), ranks[cur] + 1)
                if in_degree[nxt] == 0:
                    queue.append(nxt)
        for s in route.steps:
            if s.id not in ranks:
                ranks[s.id] = 0

        # Branch lanes
        branches_seen: list[str] = []
        for s in route.steps:
            b = s.branch or "main"
            if b not in branches_seen:
                branches_seen.append(b)

        def branch_priority(b: str) -> int:
            if b == "main": return 0
            elif b.startswith("alt"): return 1
            elif b.startswith("fallback"): return 2
            elif b == "tasks": return 3
            return 4

        branches_seen.sort(key=branch_priority)

        branch_lanes: dict[str, float] = {}
        lane = 0
        for i, b in enumerate(branches_seen):
            if i == 0:
                branch_lanes[b] = 0.0
            else:
                if i % 2 == 1:
                    lane += 1
                    branch_lanes[b] = float(lane)
                else:
                    branch_lanes[b] = float(-lane)

        # Node sizes
        node_sizes: dict[str, tuple[float, float]] = {}
        for sid in steps_by_id:
            item = self._node_items.get(sid)
            if item is not None:
                node_sizes[sid] = (item._width, item._height)
            else:
                node_sizes[sid] = (280, 160)

        return steps_by_id, ranks, edge_pairs, succ, pred, branch_lanes, node_sizes

    # ---- 1. Organic Flow (default) ----
    def _layout_organic(self, route: Route) -> dict[str, tuple[float, float]]:
        """Organic flow: branches spread wide with heavy jitter, RTL direction."""
        rng = random.Random(42)

        if not route.steps:
            return {}

        steps_by_id, ranks, edge_pairs, succ, pred, branch_lanes, node_sizes = \
            self._build_topology(route)
        max_rank = max(ranks.values()) if ranks else 0

        LANE_SPACING = 480
        RANK_SPACING = 620
        positions: dict[str, tuple[float, float]] = {}

        by_rank: dict[int, list[str]] = defaultdict(list)
        for sid, r in ranks.items():
            by_rank[r].append(sid)
        for rank in by_rank:
            by_rank[rank].sort(key=lambda sid: branch_lanes.get(steps_by_id[sid].branch or "main", 0))

        lane_rank_count: dict[tuple[float, int], int] = defaultdict(int)
        lane_rank_index: dict[tuple[float, int, str], int] = {}
        for rank in by_rank:
            for sid in by_rank[rank]:
                b = steps_by_id[sid].branch or "main"
                lane = branch_lanes.get(b, 0)
                key = (lane, rank)
                lane_rank_index[(lane, rank, sid)] = lane_rank_count[key]
                lane_rank_count[key] += 1

        for rank in sorted(by_rank.keys()):
            for sid in by_rank[rank]:
                step = steps_by_id[sid]
                b = step.branch or "main"
                lane = branch_lanes.get(b, 0)

                x = (max_rank - rank) * RANK_SPACING - (max_rank * RANK_SPACING) / 2
                y = lane * LANE_SPACING

                key = (lane, rank)
                count = lane_rank_count[key]
                idx = lane_rank_index.get((lane, rank, sid), 0)
                if count > 1:
                    y += (idx - (count - 1) / 2) * 220

                # Heavy organic jitter
                x += rng.uniform(-80, 80)
                y += rng.uniform(-60, 60)

                positions[sid] = (x, y)

        # Pull connected nodes closer
        for _ in range(3):
            for src, tgt in edge_pairs:
                if src in positions and tgt in positions:
                    sx, sy = positions[src]
                    tx, ty = positions[tgt]
                    nudge = (sy - ty) * 0.1
                    positions[tgt] = (positions[tgt][0], positions[tgt][1] + nudge)

        positions = self._eliminate_overlaps(positions, node_sizes)
        return positions

    # ---- 2. Radial Burst ----
    def _layout_radial(self, route: Route) -> dict[str, tuple[float, float]]:
        """Radial: start nodes at center, branches radiate outward like a starburst.
        RTL: start center-right, end outer-left.
        """
        rng = random.Random(42)

        if not route.steps:
            return {}

        steps_by_id, ranks, edge_pairs, succ, pred, branch_lanes, node_sizes = \
            self._build_topology(route)
        max_rank = max(ranks.values()) if ranks else 0

        RADIUS_PER_RANK = 350
        positions: dict[str, tuple[float, float]] = {}

        by_rank: dict[int, list[str]] = defaultdict(list)
        for sid, r in ranks.items():
            by_rank[r].append(sid)

        # Find start nodes (rank 0)
        start_nodes = by_rank.get(0, [])

        # Assign angular sectors per branch
        branches = set(steps_by_id[sid].branch or "main" for sid in route.steps)
        branch_list = sorted(branches, key=lambda b: 0 if b == "main" else (1 if b.startswith("alt") else 2))
        num_branches = max(len(branch_list), 1)

        # Spread branches across angles (centered on right side = 0 degrees, going RTL)
        branch_angles: dict[str, float] = {}
        if num_branches == 1:
            branch_angles[branch_list[0]] = 0.0
        else:
            angle_span = math.pi * 1.4  # ~250 degrees of spread
            angle_start = -angle_span / 2
            for i, b in enumerate(branch_list):
                branch_angles[b] = angle_start + (i / (num_branches - 1)) * angle_span

        for rank in sorted(by_rank.keys()):
            sids_in_rank = by_rank[rank]
            radius = (rank + 1) * RADIUS_PER_RANK

            # Group by branch within this rank
            by_branch: dict[str, list[str]] = defaultdict(list)
            for sid in sids_in_rank:
                b = steps_by_id[sid].branch or "main"
                by_branch[b].append(sid)

            for b, sids in by_branch.items():
                base_angle = branch_angles.get(b, 0)
                # Slight angle progression per rank (spiral effect)
                base_angle += rank * 0.15

                for i, sid in enumerate(sids):
                    # Fan out if multiple nodes in same branch+rank
                    if len(sids) > 1:
                        sub_angle = base_angle + (i - (len(sids) - 1) / 2) * 0.2
                    else:
                        sub_angle = base_angle

                    # Add jitter to angle and radius
                    sub_angle += rng.uniform(-0.12, 0.12)
                    radius_jittered = radius + rng.uniform(-60, 60)

                    # RTL: flip so start (rank 0) is on the right
                    x = -radius_jittered * math.cos(sub_angle)
                    y = radius_jittered * math.sin(sub_angle)

                    positions[sid] = (x, y)

        # Pull connected nodes closer
        for _ in range(4):
            for src, tgt in edge_pairs:
                if src in positions and tgt in positions:
                    sx, sy = positions[src]
                    tx, ty = positions[tgt]
                    nudge_x = (sx - tx) * 0.06
                    nudge_y = (sy - ty) * 0.06
                    positions[tgt] = (positions[tgt][0] + nudge_x,
                                      positions[tgt][1] + nudge_y)

        positions = self._eliminate_overlaps(positions, node_sizes)
        return positions

    # ---- 3. Mind Map ----
    def _layout_mindmap(self, route: Route) -> dict[str, tuple[float, float]]:
        """Mind map: start node(s) in center, branches go in different directions.
        Each branch gets its own angular sector radiating from center.
        """
        rng = random.Random(42)

        if not route.steps:
            return {}

        steps_by_id, ranks, edge_pairs, succ, pred, branch_lanes, node_sizes = \
            self._build_topology(route)

        positions: dict[str, tuple[float, float]] = {}

        # Find start nodes
        by_rank: dict[int, list[str]] = defaultdict(list)
        for sid, r in ranks.items():
            by_rank[r].append(sid)
        start_nodes = by_rank.get(0, [])
        max_rank = max(ranks.values()) if ranks else 0

        # Place start node(s) at center
        for i, sid in enumerate(start_nodes):
            positions[sid] = (rng.uniform(-30, 30), (i - (len(start_nodes) - 1) / 2) * 200)

        # Group all non-start nodes by branch
        branches: dict[str, list[str]] = defaultdict(list)
        for sid in route.steps:
            if sid not in {s for s in start_nodes}:
                b = steps_by_id[sid].branch or "main"
                branches[b].append(sid)

        # Assign each branch an angular direction from center
        branch_list = list(branches.keys())
        branch_list.sort(key=lambda b: 0 if b == "main" else (1 if b.startswith("alt") else 2))

        num_branches = max(len(branch_list), 1)
        # Spread branches: main goes right, others fan around
        branch_direction: dict[str, float] = {}
        if num_branches == 1:
            branch_direction[branch_list[0]] = 0.0  # right
        else:
            # Main at 0 (right), others spread evenly
            for i, b in enumerate(branch_list):
                if b == "main":
                    branch_direction[b] = 0.0
                else:
                    # Alternate above and below
                    idx = i  # 0-based among all branches
                    angle = (idx / num_branches) * 2 * math.pi
                    branch_direction[b] = angle

        SPACING = 320
        for b, sids in branches.items():
            direction = branch_direction.get(b, 0)
            # Sort sids by rank within this branch
            sids.sort(key=lambda sid: ranks.get(sid, 0))

            for i, sid in enumerate(sids):
                distance = (i + 1) * SPACING
                # Slight spiral: each step rotates a tiny bit
                angle = direction + i * 0.18 + rng.uniform(-0.15, 0.15)
                distance += rng.uniform(-50, 50)

                x = distance * math.cos(angle)
                y = distance * math.sin(angle)

                # If multiple nodes at same distance, fan them
                positions[sid] = (x, y)

        # Pull connected nodes closer
        for _ in range(5):
            for src, tgt in edge_pairs:
                if src in positions and tgt in positions:
                    sx, sy = positions[src]
                    tx, ty = positions[tgt]
                    nudge_x = (sx - tx) * 0.05
                    nudge_y = (sy - ty) * 0.05
                    positions[tgt] = (positions[tgt][0] + nudge_x,
                                      positions[tgt][1] + nudge_y)

        positions = self._eliminate_overlaps(positions, node_sizes)
        return positions

    # ---- 4. Layered DAG ----
    def _layout_layered(self, route: Route) -> dict[str, tuple[float, float]]:
        """Classic Sugiyama-style layered DAG layout with proper layering.
        RTL: start on right, end on left. Each layer is a vertical column.
        Nodes within a layer are spread with barycenter ordering.
        """
        rng = random.Random(42)

        if not route.steps:
            return {}

        steps_by_id, ranks, edge_pairs, succ, pred, branch_lanes, node_sizes = \
            self._build_topology(route)
        max_rank = max(ranks.values()) if ranks else 0

        RANK_SPACING = 550
        positions: dict[str, tuple[float, float]] = {}

        by_rank: dict[int, list[str]] = defaultdict(list)
        for sid, r in ranks.items():
            by_rank[r].append(sid)

        # Barycenter heuristic: order nodes within each rank to minimize crossings
        # Initialize with branch-based ordering
        for rank in by_rank:
            by_rank[rank].sort(key=lambda sid: branch_lanes.get(steps_by_id[sid].branch or "main", 0))

        # 3 passes of barycenter refinement
        for _ in range(3):
            for rank in sorted(by_rank.keys()):
                if rank == 0:
                    continue
                prev_rank = rank - 1
                prev_sids = by_rank[prev_rank]
                prev_pos = {sid: i for i, sid in enumerate(prev_sids)}

                # For each node in this rank, compute barycenter of predecessors
                def barycenter(sid: str) -> float:
                    preds = pred.get(sid, [])
                    if not preds:
                        return float('inf')
                    positions_sum = sum(prev_pos.get(p, 0) for p in preds if p in prev_pos)
                    return positions_sum / max(len(preds), 1)

                by_rank[rank].sort(key=barycenter)

        # Assign positions with generous vertical spread
        for rank in sorted(by_rank.keys()):
            sids = by_rank[rank]
            n = len(sids)
            x = (max_rank - rank) * RANK_SPACING - (max_rank * RANK_SPACING) / 2

            # Spread vertically with generous spacing
            total_height = (n - 1) * 420
            start_y = -total_height / 2

            for i, sid in enumerate(sids):
                y = start_y + i * 420
                # Slight jitter
                y += rng.uniform(-35, 35)
                x_jittered = x + rng.uniform(-25, 25)
                positions[sid] = (x_jittered, y)

        positions = self._eliminate_overlaps(positions, node_sizes)
        return positions

    # ---- 5. Force Field (physics simulation) ----
    def _layout_force(self, route: Route) -> dict[str, tuple[float, float]]:
        """Force-directed layout: nodes repel each other, edges act as springs.
        Starts with topological positions, then runs a physics simulation.
        Produces very organic, complex-looking layouts.
        """
        rng = random.Random(42)

        if not route.steps:
            return {}

        steps_by_id, ranks, edge_pairs, succ, pred, branch_lanes, node_sizes = \
            self._build_topology(route)
        max_rank = max(ranks.values()) if ranks else 0

        # Start from organic positions as initial state
        positions = self._layout_organic(route)

        # Convert to mutable
        pos = {k: list(v) for k, v in positions.items()}
        ids = list(pos.keys())
        n = len(ids)

        # Physics parameters
        REPULSION = 800000  # how strongly nodes push apart
        SPRING_LENGTH = 400  # ideal edge length
        SPRING_K = 0.04  # spring stiffness
        DAMPING = 0.85  # velocity damping
        ITERATIONS = 120  # simulation steps

        # Initialize velocities
        vel = {sid: [0.0, 0.0] for sid in ids}

        for iteration in range(ITERATIONS):
            forces = {sid: [0.0, 0.0] for sid in ids}

            # Repulsion: every pair of nodes pushes apart
            for i in range(n):
                for j in range(i + 1, n):
                    a, b = ids[i], ids[j]
                    dx = pos[a][0] - pos[b][0]
                    dy = pos[a][1] - pos[b][1]
                    dist_sq = dx * dx + dy * dy
                    dist = math.sqrt(dist_sq) if dist_sq > 0 else 1.0
                    # Coulomb's law
                    force = REPULSION / max(dist_sq, 100)
                    fx = force * dx / dist
                    fy = force * dy / dist
                    forces[a][0] += fx
                    forces[a][1] += fy
                    forces[b][0] -= fx
                    forces[b][1] -= fy

            # Spring: connected nodes attract
            for src, tgt in edge_pairs:
                if src not in pos or tgt not in pos:
                    continue
                dx = pos[tgt][0] - pos[src][0]
                dy = pos[tgt][1] - pos[src][1]
                dist = math.sqrt(dx * dx + dy * dy) if (dx * dx + dy * dy) > 0 else 1.0
                displacement = dist - SPRING_LENGTH
                force = SPRING_K * displacement
                fx = force * dx / dist
                fy = force * dy / dist
                forces[src][0] += fx
                forces[src][1] += fy
                forces[tgt][0] -= fx
                forces[tgt][1] -= fy

            # Gentle gravity toward center (prevent drift)
            for sid in ids:
                forces[sid][0] -= pos[sid][0] * 0.001
                forces[sid][1] -= pos[sid][1] * 0.001

            # RTL bias: gently push start nodes right, end nodes left
            for sid in ids:
                rank = ranks.get(sid, 0)
                bias = (max_rank / 2 - rank) * 0.5
                forces[sid][0] += bias

            # Apply forces with damping
            for sid in ids:
                vel[sid][0] = (vel[sid][0] + forces[sid][0]) * DAMPING
                vel[sid][1] = (vel[sid][1] + forces[sid][1]) * DAMPING
                # Limit max velocity
                max_v = 50
                speed = math.sqrt(vel[sid][0]**2 + vel[sid][1]**2)
                if speed > max_v:
                    vel[sid][0] *= max_v / speed
                    vel[sid][1] *= max_v / speed
                pos[sid][0] += vel[sid][0]
                pos[sid][1] += vel[sid][1]

        # Add final jitter for organic feel
        for sid in ids:
            pos[sid][0] += rng.uniform(-20, 20)
            pos[sid][1] += rng.uniform(-20, 20)

        result = {k: (v[0], v[1]) for k, v in pos.items()}
        result = self._eliminate_overlaps(result, node_sizes)
        return result

    def _eliminate_overlaps(self, positions: dict[str, tuple[float, float]],
                            node_sizes: dict[str, tuple[float, float]]) -> dict[str, tuple[float, float]]:
        """Push overlapping nodes apart until no two nodes overlap.

        Uses a simple iterative repulsion approach: for each pair of
        overlapping nodes, push them apart by the minimum amount needed.
        """
        pos = {k: list(v) for k, v in positions.items()}  # mutable
        ids = list(pos.keys())
        padding = 40  # minimum gap between nodes

        for _iteration in range(20):  # max 20 passes
            any_overlap = False
            for i in range(len(ids)):
                for j in range(i + 1, len(ids)):
                    a, b = ids[i], ids[j]
                    ax, ay = pos[a]
                    bx, by = pos[b]
                    aw, ah = node_sizes.get(a, (280, 160))
                    bw, bh = node_sizes.get(b, (280, 160))

                    # Check bounding rect overlap
                    overlap_x = (ax + aw + padding) - bx if ax < bx else (bx + bw + padding) - ax
                    overlap_y = (ay + ah + padding) - by if ay < by else (by + bh + padding) - ay

                    if overlap_x > 0 and overlap_y > 0:
                        any_overlap = True
                        # Push apart in the direction of minimum overlap
                        if overlap_x < overlap_y:
                            # Push horizontally
                            push = overlap_x / 2 + 10
                            if ax < bx:
                                pos[a][0] -= push
                                pos[b][0] += push
                            else:
                                pos[a][0] += push
                                pos[b][0] -= push
                        else:
                            # Push vertically
                            push = overlap_y / 2 + 10
                            if ay < by:
                                pos[a][1] -= push
                                pos[b][1] += push
                            else:
                                pos[a][1] += push
                                pos[b][1] -= push

            if not any_overlap:
                break

        return {k: (v[0], v[1]) for k, v in pos.items()}

    def _compute_critical_path(self, route: Route) -> list[str]:
        if not route.steps:
            return []
        steps_by_id = {s.id: s for s in route.steps}
        memo: dict[str, tuple[int, list[str]]] = {}
        visiting: set[str] = set()  # cycle detection

        def longest_path_ending_at(sid: str) -> tuple[int, list[str]]:
            if sid in memo:
                return memo[sid]
            # Cycle detection — if we're already visiting this node, skip it
            if sid in visiting:
                return (0, [])
            visiting.add(sid)
            step = steps_by_id[sid]
            preds = list(step.depends_on)
            for e in route.edges:
                if e.target_id == sid and e.source_id in steps_by_id:
                    if e.source_id not in preds:
                        preds.append(e.source_id)
            if not preds:
                result = (step.duration_minutes, [sid])
            else:
                best = (0, [])
                for dep_id in preds:
                    if dep_id in steps_by_id:
                        dep_len, dep_path = longest_path_ending_at(dep_id)
                        if dep_len > best[0]:
                            best = (dep_len, dep_path)
                result = (best[0] + step.duration_minutes, best[1] + [sid])
            visiting.discard(sid)
            memo[sid] = result
            return result

        best_overall: tuple[int, list[str]] = (0, [])
        for s in route.steps:
            length, path = longest_path_ending_at(s.id)
            if length > best_overall[0]:
                best_overall = (length, path)
        return best_overall[1]

    # ---- Step lookup helper ----
    def _find_step(self, step_id: str):
        """Find a RouteStep by ID — checks route steps first, then tasks.
        Returns (step, is_task). Returns (None, False) if not found.
        """
        if self._route is not None:
            step = next((s for s in self._route.steps if s.id == step_id), None)
            if step is not None:
                return step, False
        if self._project is not None:
            try:
                task = self._project.get_task(TaskId(step_id))
                if task is not None:
                    return self._task_to_step(task), True
            except Exception:
                logger.debug("Failed to look up task for step %s", step_id, exc_info=True)
        return None, False

    # ---- Interaction ----
    def _on_node_clicked(self, step_id: str) -> None:
        # Update selection UI whenever a node is clicked
        self._update_selection_ui()
        # No popup on single-click — double-click opens the edit dialog instead

    def _deferred_show_popup(self) -> None:
        """Show the details popup after the click timer expires (no double-click came)."""
        self._click_timer.timeout.disconnect(self._deferred_show_popup)
        step_id = self._pending_click_step_id
        self._pending_click_step_id = None
        if step_id is None:
            return
        step, _ = self._find_step(step_id)
        if step is not None:
            self.stepSelected.emit(step)
            self._show_details_popup(step)

    def _on_node_double_clicked(self, step_id: str) -> None:
        # Cancel the pending popup from the first click
        self._click_timer.stop()
        try:
            self._click_timer.timeout.disconnect(self._deferred_show_popup)
        except RuntimeError:
            pass
        self._pending_click_step_id = None

        step, _ = self._find_step(step_id)
        if step is not None:
            self.stepDoubleClicked.emit(step)

    def _on_node_edit_requested(self, step_id: str) -> None:
        """Open the modal NodeEditDialog for the given step."""
        step, is_task = self._find_step(step_id)
        if step is None:
            return

        # Import here to avoid circular imports
        from ..dialogs.node_edit_dialog import NodeEditDialog

        # Close any open details popup first
        if self._details_popup is not None:
            self._details_popup.close()
            self._details_popup = None

        dialog = NodeEditDialog(step, self)
        if dialog.exec():
            changes = dialog.get_changes()
            # Apply changes to the RouteStep
            for key, value in changes.items():
                if hasattr(step, key):
                    setattr(step, key, value)
            # Also update the underlying Task if it's a task
            if self._project is not None:
                try:
                    task = self._project.get_task(TaskId(step_id))
                    if task is not None:
                        if "title" in changes:
                            task.title = changes["title"]
                        if "description" in changes:
                            task.description = changes["description"]
                        if "duration_minutes" in changes:
                            from ...core import Duration
                            task.duration = Duration(int(changes["duration_minutes"]))
                        task.touch()
                except Exception:
                    pass
            # Update the node item visually
            item = self._node_items.get(step_id)
            if item is not None:
                item._compute_size()
                item.prepareGeometryChange()
                item.update()
                item.nodeEdited.emit(step_id, step.title, step.description or "")
            # Emit signal for any listeners
            for key, value in changes.items():
                self.stepFieldChanged.emit(step_id, key, value)

    def _on_node_moved(self, step_id: str, x: float, y: float) -> None:
        # Update connected edges' paths using O(1) index lookup
        for edge_item in self._edges_by_node.get(step_id, []):
            edge_item._update_path()
        # Update the underlying Task position if it's a task
        if self._project is not None:
            try:
                task = self._project.get_task(TaskId(step_id))
                if task is not None:
                    task.x = x
                    task.y = y
                    task.touch()
            except Exception:
                logger.debug("Failed to update task position for %s", step_id, exc_info=True)

    def _on_node_position_changed(self, step_id: str) -> None:
        """Live edge update during drag — called on every position change."""
        for edge_item in self._edges_by_node.get(step_id, []):
            edge_item._update_path()

    def _on_node_edited(self, step_id: str, new_title: str, new_desc: str) -> None:
        # Update the underlying Task if it's a task
        if self._project is not None:
            try:
                task = self._project.get_task(TaskId(step_id))
                if task is not None:
                    task.title = new_title
                    task.description = new_desc
                    task.touch()
            except Exception:
                logger.debug("Failed to look up task for step %s", step_id, exc_info=True)
        # Update route step if it's a route step
        if self._route is not None:
            for step in self._route.steps:
                if step.id == step_id:
                    step.title = new_title
                    step.description = new_desc
                    break

    def _on_bubble_clicked(self, bubble_id: str) -> None:
        bubble = self._bubble_items.get(bubble_id)
        if bubble is not None:
            self.insightSelected.emit(bubble.insight)

    # ---- Details popup ----
    def _show_details_popup(self, step: RouteStep) -> None:
        """Show the floating details popup for a step."""
        # Close any existing popup
        if self._details_popup is not None:
            self._details_popup.close()
            self._details_popup = None
        # Create new popup
        self._details_popup = StepDetailsPopup(step, self)
        # Position near the center of the viewport in global coords
        center = self.mapToGlobal(self.viewport().rect().center())
        # Offset to the right of center
        self._details_popup.move(center.x() + 100, center.y() - 200)
        self._details_popup.show()
        self._details_popup.raise_()
        # Connect field-changed signal
        self._details_popup.stepFieldChanged.connect(self._on_step_field_changed)
        self._details_popup.fullEditRequested.connect(self._on_node_edit_requested)
        self._details_popup.closed.connect(lambda: setattr(self, "_details_popup", None))

    def _on_step_field_changed(self, step_id: str, field: str, value) -> None:
        """Handle field changes from the details popup."""
        # Update the RouteStep
        if self._route is not None:
            for step in self._route.steps:
                if step.id == step_id:
                    if hasattr(step, field):
                        current = getattr(step, field)
                        converted = value
                        if isinstance(current, int) and not isinstance(value, int):
                            try:
                                converted = int(value)
                            except (ValueError, TypeError):
                                logger.warning("Cannot convert %r to int for field %s", value, field)
                                continue
                        elif isinstance(current, float) and not isinstance(value, float):
                            try:
                                converted = float(value)
                            except (ValueError, TypeError):
                                logger.warning("Cannot convert %r to float for field %s", value, field)
                                continue
                        setattr(step, field, converted)
                    break
        # Update the underlying Task if it's a task
        if self._project is not None:
            try:
                task = self._project.get_task(TaskId(step_id))
                if task is not None:
                    if field == "title":
                        task.title = str(value)
                    elif field == "description":
                        task.description = str(value)
                    elif field == "duration_minutes":
                        from ...core import Duration
                        task.duration = Duration(int(value))
                    task.touch()
            except Exception:
                logger.debug("Failed to update task field for %s", step_id, exc_info=True)
        # Update the node item
        item = self._node_items.get(step_id)
        if item is not None:
            item._compute_size()
            item.prepareGeometryChange()
            item.update()
        # Emit signal
        self.stepFieldChanged.emit(step_id, field, value)

    # ---- Pan & zoom ----
    def wheelEvent(self, event: QWheelEvent) -> None:
        angle = event.angleDelta().y()
        factor = 1.15 if angle > 0 else 1 / 1.15
        mouse_scene = self.mapToScene(event.position().toPoint())
        self.scale(factor, factor)
        new_mouse = self.mapFromScene(mouse_scene)
        delta = new_mouse - event.position().toPoint()
        self.horizontalScrollBar().setValue(self.horizontalScrollBar().value() + delta.x())
        self.verticalScrollBar().setValue(self.verticalScrollBar().value() + delta.y())

    def mousePressEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.MiddleButton or \
           (event.button() == Qt.LeftButton and (event.modifiers() & Qt.KeyboardModifier.ShiftModifier)):
            self._panning = True
            self._pan_last = event.position().toPoint()
            self.setCursor(Qt.ClosedHandCursor)
            event.accept()
            return
        if event.button() == Qt.LeftButton:
            item = self.itemAt(event.position().toPoint())
            if item is None:
                # Clicking on empty canvas — start rubber band selection
                self.stepSelected.emit(None)
                self.insightSelected.emit(None)
                # Close popup if clicking outside
                if self._details_popup is not None:
                    self._details_popup.close()
                    self._details_popup = None
                # If not holding Ctrl, clear previous selection
                if not (event.modifiers() & Qt.KeyboardModifier.ControlModifier):
                    self._scene.clearSelection()
                # Start rubber band
                self._rubber_band_active = True
                self._rubber_band_start = self.mapToScene(event.position().toPoint())
                self._start_rubber_band(self._rubber_band_start)
                event.accept()
                return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        if self._panning and self._pan_last is not None:
            delta = event.position().toPoint() - self._pan_last
            self._pan_last = event.position().toPoint()
            self.horizontalScrollBar().setValue(
                self.horizontalScrollBar().value() - delta.x()
            )
            self.verticalScrollBar().setValue(
                self.verticalScrollBar().value() - delta.y()
            )
            event.accept()
            return
        if self._rubber_band_active and self._rubber_band_start is not None:
            current = self.mapToScene(event.position().toPoint())
            self._update_rubber_band(self._rubber_band_start, current)
            event.accept()
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        if self._panning:
            self._panning = False
            self._pan_last = None
            self.setCursor(Qt.ArrowCursor)
            event.accept()
            return
        if self._rubber_band_active and event.button() == Qt.LeftButton:
            self._finish_rubber_band()
            event.accept()
            return
        super().mouseReleaseEvent(event)

    # ---- Rubber band selection ----
    def _start_rubber_band(self, start: QPointF) -> None:
        """Create the rubber band rectangle at the start position."""
        if self._rubber_band_rect is not None:
            self._scene.removeItem(self._rubber_band_rect)
        rect = QRectF(start, start)
        self._rubber_band_rect = self._scene.addRect(
            rect,
            QPen(self._rubber_band_border, 1.5, Qt.DashLine),
            QBrush(self._rubber_band_color),
        )
        self._rubber_band_rect.setZValue(1000)
        self._rubber_band_rect.setOpacity(0.0)  # Start invisible, show on move

    def _update_rubber_band(self, start: QPointF, current: QPointF) -> None:
        """Update the rubber band rectangle as the mouse moves."""
        if self._rubber_band_rect is None:
            return
        rect = QRectF(
            min(start.x(), current.x()),
            min(start.y(), current.y()),
            abs(current.x() - start.x()),
            abs(current.y() - start.y()),
        )
        self._rubber_band_rect.setRect(rect)
        self._rubber_band_rect.setOpacity(1.0)

        # Live preview: highlight nodes that would be selected
        sel_rect = rect.adjusted(-5, -5, 5, 5)  # slight padding
        for nid, item in self._node_items.items():
            node_rect = item.sceneBoundingRect()
            would_select = sel_rect.intersects(node_rect)
            if would_select and not item.isSelected():
                item.setSelected(True)
            elif not would_select and item.isSelected() and not (QApplication.keyboardModifiers() & Qt.KeyboardModifier.ControlModifier):
                # Only deselect if Ctrl isn't held (Ctrl = additive selection)
                item.setSelected(False)

    def _finish_rubber_band(self) -> None:
        """Finish rubber band selection — select all nodes within the rect."""
        self._rubber_band_active = False

        if self._rubber_band_rect is not None:
            rect = self._rubber_band_rect.rect()
            self._scene.removeItem(self._rubber_band_rect)
            self._rubber_band_rect = None

            if rect.width() > 5 or rect.height() > 5:
                # Select all RouteNodeItems whose bounding rect intersects
                sel_rect = rect.adjusted(-5, -5, 5, 5)
                for nid, item in self._node_items.items():
                    if sel_rect.intersects(item.sceneBoundingRect()):
                        item.setSelected(True)

        self._update_selection_ui()

    def _update_selection_ui(self) -> None:
        """Update the Delete button and selection count in toolbar."""
        if not hasattr(self, '_delete_sel_btn') or self._delete_sel_btn is None:
            return
        selected = [item for item in self._node_items.values() if item.isSelected()]
        count = len(selected)
        self._delete_sel_btn.setVisible(count > 0)
        self._sel_count_label.setVisible(count > 0)
        if count > 0:
            self._sel_count_label.setText(f"{count} selected")

    # ---- Delete selected nodes ----
    def _delete_selected_nodes(self) -> None:
        """Delete all currently selected nodes and their connected edges."""
        selected_ids = [
            item.step.id for item in self._node_items.values()
            if item.isSelected()
        ]
        if not selected_ids:
            return
        # Remove each selected node
        for step_id in selected_ids:
            self._remove_step(step_id)
        self._update_selection_ui()

    def contextMenuEvent(self, event) -> None:
        """Right-click context menu on nodes."""
        item = self.itemAt(event.pos())
        # Find the RouteNodeItem under cursor
        step_id = None
        route_node_item = None
        while item is not None:
            if isinstance(item, RouteNodeItem):
                step_id = item.step.id
                route_node_item = item
                break
            item = item.parentItem()

        # Count currently selected nodes
        selected_count = sum(1 for it in self._node_items.values() if it.isSelected())

        menu = QMenu(self)
        menu.setStyleSheet(f"""
            QMenu {{
                background-color: {Palette.BG_TERTIARY};
                color: {Palette.TEXT_PRIMARY};
                border: 1px solid {Palette.BORDER_NORMAL};
                border-radius: 4px;
                padding: 4px;
            }}
            QMenu::item {{
                padding: 6px 20px;
                border-radius: 3px;
            }}
            QMenu::item:selected {{
                background-color: {Palette.BG_HOVER};
                color: {Palette.GOLD_BRIGHT};
            }}
        """)

        if step_id and self._route is not None:
            step = next((s for s in self._route.steps if s.id == step_id), None)
            if step:
                breakdown_action = menu.addAction(f"✦ AI Break Down: {step.title}")
                breakdown_action.triggered.connect(lambda: self.stepBreakdownRequested.emit(step_id))

                # Add separator
                menu.addSeparator()

                # Edit action — opens the modal dialog
                edit_action = menu.addAction(f"✏️ Edit: {step.title}")
                edit_action.triggered.connect(lambda: self._on_node_edit_requested(step_id))

                # Delete action
                delete_action = menu.addAction(f"🗑 Remove: {step.title}")
                delete_action.triggered.connect(lambda: self._remove_step(step_id))

                # If multiple nodes are selected, offer bulk delete
                if selected_count > 1:
                    menu.addSeparator()
                    bulk_delete_action = menu.addAction(f"🗑 Delete {selected_count} Selected Nodes")
                    bulk_delete_action.triggered.connect(self._delete_selected_nodes)
            else:
                menu.addAction("No actions available")
        else:
            add_task_action = menu.addAction("＋ Add Task Here")
            scene_pos = self.mapToScene(event.pos())
            add_task_action.triggered.connect(
                lambda: self.taskCreated.emit("New Task", scene_pos.x(), scene_pos.y())
            )
            # If nodes are selected, offer bulk delete even on empty canvas
            if selected_count > 0:
                menu.addSeparator()
                bulk_delete_action = menu.addAction(f"🗑 Delete {selected_count} Selected Nodes")
                bulk_delete_action.triggered.connect(self._delete_selected_nodes)

        menu.exec(event.globalPos())

    def _remove_step(self, step_id: str) -> None:
        """Remove a step from the route and the canvas, cleaning up ALL references.

        This is a thorough cleanup that stops animations, disconnects signals,
        removes edges, and ensures no ghost items remain.
        """
        # 1. Remove from route data model
        if self._route is not None:
            self._route.steps = [s for s in self._route.steps if s.id != step_id]
            self._route.edges = [e for e in self._route.edges
                                  if e.source_id != step_id and e.target_id != step_id]
            # Clean up depends_on references in remaining steps
            for s in self._route.steps:
                if step_id in s.depends_on:
                    s.depends_on = [d for d in s.depends_on if d != step_id]

        # 2. Cancel any running layout animations targeting this node
        for anim in list(self._layout_anims):
            if anim.state() == QPropertyAnimation.Running:
                try:
                    target = anim.targetObject()
                    if target is not None and (
                        (isinstance(target, RouteNodeItem) and target.step.id == step_id) or
                        target is self._node_items.get(step_id)
                    ):
                        anim.stop()
                except RuntimeError:
                    pass  # target already deleted

        # 3. Remove connected edges FIRST (before removing node, so edge _update_path won't crash)
        to_remove = [e for e in self._edge_items
                     if e.edge.source_id == step_id or e.edge.target_id == step_id]
        for edge in to_remove:
            self._scene.removeItem(edge)
            if edge in self._edge_items:
                self._edge_items.remove(edge)
            # Clean up edge index
            src = edge.edge.source_id
            tgt = edge.edge.target_id
            if src in self._edges_by_node:
                self._edges_by_node[src] = [e for e in self._edges_by_node[src] if e is not edge]
                if not self._edges_by_node[src]:
                    del self._edges_by_node[src]
            if tgt in self._edges_by_node:
                self._edges_by_node[tgt] = [e for e in self._edges_by_node[tgt] if e is not edge]
                if not self._edges_by_node[tgt]:
                    del self._edges_by_node[tgt]

        # 4. Remove the node item with full cleanup
        item = self._node_items.pop(step_id, None)
        if item is not None:
            # Stop pulse timer
            if hasattr(item, '_pulse_timer') and item._pulse_timer.isActive():
                item._pulse_timer.stop()
            # Stop all property animations on the item
            for attr_name in ('_opacity_anim', '_scale_anim', '_pos_anim'):
                anim = getattr(item, attr_name, None)
                if anim is not None and hasattr(anim, 'state'):
                    try:
                        if anim.state() == QPropertyAnimation.Running:
                            anim.stop()
                    except RuntimeError:
                        pass
            # Disconnect all signals to prevent callbacks on dead item
            try:
                item.nodeClicked.disconnect()
                item.nodeDoubleClicked.disconnect()
                item.nodeMoved.disconnect()
                item.nodeEdited.disconnect()
                item.nodeEditRequested.disconnect()
                item.nodePositionChanged.disconnect()
            except (RuntimeError, TypeError):
                pass
            # Deselect
            item.setSelected(False)
            # Remove from scene
            self._scene.removeItem(item)
            # Schedule deletion to free memory
            item.deleteLater()

        # 5. Clean up pending edges for this node
        self._pending_edges = [e for e in self._pending_edges
                               if e.source_id != step_id and e.target_id != step_id]

        # 6. Close details popup if it references this step
        if self._details_popup is not None:
            try:
                if hasattr(self._details_popup, '_step') and self._details_popup._step.id == step_id:
                    self._details_popup.close()
                    self._details_popup = None
            except RuntimeError:
                self._details_popup = None

        # 7. Force scene update to clear any ghost rendering
        self._scene.update()

    def keyPressEvent(self, event: QKeyEvent) -> None:
        key = event.key()
        if key == Qt.Key_F:
            self.fit_all()
        elif key == Qt.Key_L and event.modifiers() & Qt.ControlModifier:
            self.auto_layout()
        elif key == Qt.Key_Plus or key == Qt.Key_Equal:
            self.scale(1.2, 1.2)
        elif key == Qt.Key_Minus:
            self.scale(1/1.2, 1/1.2)
        elif key == Qt.Key_Escape:
            self._scene.clearSelection()
            if self._details_popup is not None:
                self._details_popup.close()
                self._details_popup = None
            self._update_selection_ui()
        elif key in (Qt.Key_Delete, Qt.Key_Backspace):
            # Delete selected nodes
            self._delete_selected_nodes()
        elif key == Qt.Key_A and event.modifiers() & Qt.ControlModifier:
            # Ctrl+A — select all nodes
            for item in self._node_items.values():
                item.setSelected(True)
            self._update_selection_ui()
        else:
            super().keyPressEvent(event)

    # ---- Background grid ----
    def drawBackground(self, painter: QPainter, rect: QRectF) -> None:
        painter.fillRect(rect, QColor(Palette.BG_DEEPEST))
        painter.setPen(QPen(QColor(Palette.BORDER_SUBTLE), 1, Qt.DotLine))
        left = int(rect.left()) - (int(rect.left()) % 20)
        top = int(rect.top()) - (int(rect.top()) % 20)
        x = left
        while x < rect.right():
            painter.drawLine(x, int(rect.top()), x, int(rect.bottom()))
            x += 20
        y = top
        while y < rect.bottom():
            painter.drawLine(int(rect.left()), y, int(rect.right()), y)
            y += 20
        painter.setPen(QPen(QColor(Palette.BORDER_NORMAL), 1, Qt.DotLine))
        left = int(rect.left()) - (int(rect.left()) % 100)
        top = int(rect.top()) - (int(rect.top()) % 100)
        x = left
        while x < rect.right():
            painter.drawLine(x, int(rect.top()), x, int(rect.bottom()))
            x += 100
        y = top
        while y < rect.bottom():
            painter.drawLine(int(rect.left()), y, int(rect.right()), y)
            y += 100

    # ---- Public actions ----
    def fit_all(self) -> None:
        items_rect = self._scene.itemsBoundingRect()
        if items_rect.isNull() or items_rect.width() < 10:
            items_rect = QRectF(-400, -300, 800, 600)
        self.fitInView(items_rect.adjusted(-80, -80, 80, 80), Qt.KeepAspectRatio)

    def _build_canvas_route(self) -> Route:
        """Build a synthetic Route that includes ALL nodes currently on the canvas.

        This ensures the layout algorithms work on every visible node, not just
        the ones in self._route.steps.  Orphan nodes (e.g. tasks not in the
        route, or nodes whose steps were removed) are included with stub edges
        inferred from their depends_on fields.
        """
        # Start from the real route if we have one
        if self._route is not None:
            steps = list(self._route.steps)
            edges = list(self._route.edges)
            step_ids_in_route = {s.id for s in steps}
        else:
            steps = []
            edges = []
            step_ids_in_route = set()

        # Add any canvas nodes that are NOT in the route yet
        for nid, item in self._node_items.items():
            if nid not in step_ids_in_route:
                steps.append(item.step)
                step_ids_in_route.add(nid)
                # Create implicit edges from the step's depends_on
                for dep_id in item.step.depends_on:
                    if dep_id in step_ids_in_route:
                        edges.append(RouteEdge(source_id=dep_id, target_id=nid, kind="primary"))

        return Route(
            goal=self._route.goal if self._route else "",
            steps=steps,
            edges=edges,
        )

    def auto_layout(self) -> None:
        """Auto-layout ALL nodes on the canvas with generous spacing and smooth animation.

        Uses the selected layout style.  Works even when nodes have been deleted
        or when task-only nodes exist without a full route.
        """
        if not self._node_items:
            return

        # Build a comprehensive route that includes ALL canvas nodes
        canvas_route = self._build_canvas_route()

        if not canvas_route.steps:
            return

        # Sync the route reference so _compute_layout can access it
        old_route = self._route
        self._route = canvas_route

        layout = self._compute_layout(canvas_route)

        # Restore the real route
        self._route = old_route

        # Animate nodes to new positions
        for step_id, (x, y) in layout.items():
            node = self._node_items.get(step_id)
            if node is not None:
                self._animate_node_to(node, x, y)

        # Reposition insight bubbles
        for bubble_id, bubble in self._bubble_items.items():
            pos = self._compute_bubble_position(bubble.insight, bubble)
            self._animate_node_to(bubble, pos.x(), pos.y())

        # Fit all after animation, and update edges
        QTimer.singleShot(600, self._post_layout_update)

    def _post_layout_update(self) -> None:
        """Called after layout animation finishes — update edges and fit view."""
        for edge_item in list(self._edge_items):
            try:
                edge_item._update_path()
            except RuntimeError:
                pass  # edge already deleted
        self.fit_all()

    def _auto_layout_all_nodes(self) -> None:
        """Layout all nodes on the canvas using the selected layout style."""
        # Delegate to auto_layout which now handles all nodes
        self.auto_layout()

    def _animate_node_to(self, item, x: float, y: float) -> None:
        """Smoothly animate a QGraphicsItem to a new position."""
        anim = QPropertyAnimation(item, b"pos")
        anim.setDuration(400)
        anim.setStartValue(item.pos())
        anim.setEndValue(QPointF(x, y))
        anim.setEasingCurve(QEasingCurve.OutCubic)
        # Auto-cleanup when animation finishes
        anim.finished.connect(anim.deleteLater)
        anim.start()
        self._layout_anims.append(anim)
        # Clean up completed animations from the list
        self._layout_anims = [a for a in self._layout_anims if a.state() == QPropertyAnimation.Running]
