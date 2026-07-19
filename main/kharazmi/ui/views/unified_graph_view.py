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
import uuid
from collections import defaultdict, deque
from typing import Optional

from PySide6.QtCore import Qt, QRectF, QPointF, Signal, QTimer, QSizeF, QPropertyAnimation, QEasingCurve
from PySide6.QtGui import (
    QPainter, QPen, QBrush, QColor, QFont, QPainterPath, QPolygonF,
    QMouseEvent, QWheelEvent, QKeyEvent, QPainterPathStroker, QAction,
)
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QGraphicsView, QGraphicsScene,
    QGraphicsItem, QGraphicsRectItem, QGraphicsPathItem, QGraphicsTextItem,
    QFrame, QPushButton, QToolButton, QSizePolicy, QApplication, QMenu,
)

from ...ai import Route, RouteStep, RouteEdge, Insight
from ...core import Project, Task, TaskId, DependencyType
from ..theme import Palette
from ..widgets.route_node_item import RouteNodeItem
from ..widgets.insight_bubble import InsightBubble
from ..widgets.step_details_popup import StepDetailsPopup


# Edge style by kind
EDGE_STYLES = {
    "primary":     {"color": "#D4AF37", "width": 2.2, "style": Qt.SolidLine},
    "alternative": {"color": "#5A7FA8", "width": 1.8, "style": Qt.DashLine},
    "fallback":    {"color": "#A85A5A", "width": 1.5, "style": Qt.DotLine},
    "merge":       {"color": "#F5C842", "width": 2.5, "style": Qt.SolidLine},
}

# Generous spacing — large enough so nodes NEVER overlap
X_SPACING = 520
Y_SPACING = 320


class UnifiedEdgeItem(QGraphicsPathItem):
    """An edge between two nodes (route or task)."""

    def __init__(self, edge: RouteEdge, source: RouteNodeItem,
                 target: RouteNodeItem, is_critical: bool = False,
                 parent: QGraphicsItem = None) -> None:
        super().__init__(parent)
        self.edge = edge
        self._source = source
        self._target = target
        self._is_critical = is_critical

        style = EDGE_STYLES.get(edge.kind, EDGE_STYLES["primary"])
        color = QColor(style["color"])
        if is_critical:
            color = QColor("#F5C842")

        pen = QPen(color, style["width"] + (0.5 if is_critical else 0), style["style"])
        pen.setCapStyle(Qt.RoundCap)
        self.setPen(pen)
        self.setZValue(0)

        # Arrow head
        self._arrow_color = color

        self._update_path()

    def _update_path(self) -> None:
        src = self._source.anchor_out
        tgt = self._target.anchor_in

        path = QPainterPath()
        path.moveTo(src)

        dx = tgt.x() - src.x()
        dy = tgt.y() - src.y()

        if abs(dx) > abs(dy) * 0.3:
            # Horizontal-ish: use cubic bezier
            mid_x = src.x() + dx * 0.5
            path.cubicTo(
                QPointF(mid_x, src.y()),
                QPointF(mid_x, tgt.y()),
                tgt,
            )
        else:
            # Vertical: use a simple S-curve
            mid_y = src.y() + dy * 0.5
            path.cubicTo(
                QPointF(src.x(), mid_y),
                QPointF(tgt.x(), mid_y),
                tgt,
            )

        self.setPath(path)

    def paint(self, painter: QPainter, option, widget=None) -> None:
        painter.setRenderHint(QPainter.Antialiasing, True)
        super().paint(painter, option, widget)

        # Draw arrowhead
        path = self.path()
        if path.elementCount() < 2:
            return

        # Get angle at end
        tgt = self._target.anchor_in
        pt_before = path.pointAtPercent(max(0, 1.0 - 0.05))
        angle = math.atan2(tgt.y() - pt_before.y(), tgt.x() - pt_before.x())

        arrow_size = 10
        p1 = QPointF(
            tgt.x() - arrow_size * math.cos(angle - math.pi / 6),
            tgt.y() - arrow_size * math.sin(angle - math.pi / 6),
        )
        p2 = QPointF(
            tgt.x() - arrow_size * math.cos(angle + math.pi / 6),
            tgt.y() - arrow_size * math.sin(angle + math.pi / 6),
        )

        arrow = QPolygonF([tgt, p1, p2])
        painter.setBrush(QBrush(self._arrow_color))
        painter.setPen(Qt.NoPen)
        painter.drawPolygon(arrow)

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
        self._bubble_items: dict[str, InsightBubble] = {}
        self._details_popup: Optional[StepDetailsPopup] = None

        self._scene = QGraphicsScene(self)
        self._scene.setSceneRect(-5000, -5000, 10000, 10000)
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

        # Toolbar for auto-layout
        self._build_toolbar()

    def _build_toolbar(self) -> None:
        """Build a floating toolbar with auto-layout and zoom controls."""
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

        auto_layout_btn = QPushButton("⊞ Auto Layout")
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

        fit_btn = QPushButton("⊡ Fit All")
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
                # Place at a good default position
                import random
                x = random.randint(-200, 200)
                y = random.randint(-200, 200)
            step = RouteStep(
                id=str(task.id),
                title=task.title,
                duration_minutes=task.duration.minutes,
                success_probability=0.5,
                description=task.description,
                branch="tasks",
                kind="action",
            )
            self._add_node(step, x=task.x, y=task.y, animate=True)

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
            self._scene.removeItem(item)
        # Clear route edges
        for edge in list(self._edge_items):
            self._scene.removeItem(edge)
        self._edge_items.clear()
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

        # Add edges
        seen_edges = set()
        for edge in route.edges:
            key = (edge.source_id, edge.target_id, edge.kind)
            if key in seen_edges:
                continue
            seen_edges.add(key)
            self._add_edge(edge, is_crit=edge.source_id in critical_path and edge.target_id in critical_path)
        for step in route.steps:
            for dep_id in step.depends_on:
                key = (dep_id, step.id, "primary")
                if key in seen_edges:
                    continue
                seen_edges.add(key)
                edge = RouteEdge(source_id=dep_id, target_id=step.id, kind="primary")
                self._add_edge(edge, is_crit=dep_id in critical_path and step.id in critical_path)

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
        self._scene.addItem(item)
        self._node_items[step.id] = item
        if animate:
            item.animate_entrance(delay_ms=delay_ms)
        return item

    def _add_edge(self, edge: RouteEdge, is_crit: bool = False) -> None:
        source = self._node_items.get(edge.source_id)
        target = self._node_items.get(edge.target_id)
        if source is None or target is None:
            return
        edge_item = UnifiedEdgeItem(edge, source, target, is_critical=is_crit)
        self._scene.addItem(edge_item)
        self._edge_items.append(edge_item)

    def _add_insight(self, insight: Insight) -> None:
        bubble_id = f"ib-{uuid.uuid4().hex[:8]}"
        bubble = InsightBubble(insight, bubble_id)
        pos = self._compute_bubble_position(insight, bubble)
        bubble.setPos(pos)
        bubble.bubbleClicked.connect(self._on_bubble_clicked)
        self._scene.addItem(bubble)
        self._bubble_items[bubble_id] = bubble

    # ---- Incremental addition (for streaming) ----
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

    def add_edge(self, edge: RouteEdge) -> None:
        """Add a single edge (for streaming)."""
        if edge.source_id not in self._node_items or edge.target_id not in self._node_items:
            # Defer — wait for both nodes to exist
            QTimer.singleShot(200, lambda: self._try_add_deferred_edge(edge))
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

    def _try_add_deferred_edge(self, edge: RouteEdge) -> None:
        if edge.source_id in self._node_items and edge.target_id in self._node_items:
            self.add_edge(edge)

    def add_insight(self, insight: Insight) -> None:
        """Add a single insight bubble (for streaming)."""
        if self._route is not None:
            self._route.insights.append(insight)
        self._add_insight(insight)

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
    def _compute_layout(self, route: Route) -> dict[str, tuple[float, float]]:
        """Compute generous layout positions for all steps in a route.

        Uses a topological ranking with generous X/Y spacing to prevent
        any overlap, even for routes with many parallel branches.
        """
        if not route.steps:
            return {}
        steps_by_id = {s.id: s for s in route.steps}
        ranks: dict[str, int] = {}
        in_degree: dict[str, int] = {s.id: 0 for s in route.steps}
        succ: dict[str, list[str]] = {s.id: [] for s in route.steps}

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

        by_rank: dict[int, list[str]] = defaultdict(list)
        for sid, r in ranks.items():
            by_rank[r].append(sid)

        def branch_sort_key(sid: str) -> tuple:
            step = steps_by_id.get(sid)
            if step is None:
                return (99, "")
            b = step.branch
            if b == "main":
                return (0, "")
            elif b.startswith("alt"):
                return (1, b)
            elif b.startswith("fallback"):
                return (2, b)
            elif b == "tasks":
                return (3, "")
            return (4, b)

        positions: dict[str, tuple[float, float]] = {}
        max_rank = max(by_rank.keys()) if by_rank else 0
        for rank in sorted(by_rank.keys()):
            sids = by_rank[rank]
            sids.sort(key=branch_sort_key)
            n = len(sids)
            # Center vertically with generous Y spacing
            total_h = (n - 1) * Y_SPACING
            start_y = -total_h / 2
            # X position based on rank
            x = rank * X_SPACING - (max_rank * X_SPACING) / 2
            for i, sid in enumerate(sids):
                positions[sid] = (x, start_y + i * Y_SPACING)
        return positions

    def _compute_critical_path(self, route: Route) -> list[str]:
        if not route.steps:
            return []
        steps_by_id = {s.id: s for s in route.steps}
        memo: dict[str, tuple[int, list[str]]] = {}

        def longest_path_ending_at(sid: str) -> tuple[int, list[str]]:
            if sid in memo:
                return memo[sid]
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
            memo[sid] = result
            return result

        best_overall: tuple[int, list[str]] = (0, [])
        for s in route.steps:
            length, path = longest_path_ending_at(s.id)
            if length > best_overall[0]:
                best_overall = (length, path)
        return best_overall[1]

    # ---- Interaction ----
    def _on_node_clicked(self, step_id: str) -> None:
        step = None
        if self._route is not None:
            step = next((s for s in self._route.steps if s.id == step_id), None)
        if step is None and self._project is not None:
            # It's a Task — convert to RouteStep for display
            try:
                task = self._project.get_task(TaskId(step_id))
                if task is not None:
                    step = RouteStep(
                        id=str(task.id), title=task.title,
                        duration_minutes=task.duration.minutes,
                        success_probability=0.5,
                        description=task.description,
                        depends_on=[str(d.predecessor_id) for d in self._project.dependencies_of(task.id)],
                        branch="tasks", kind="action",
                    )
            except Exception:
                pass
        if step is not None:
            self.stepSelected.emit(step)
            self._show_details_popup(step)

    def _on_node_double_clicked(self, step_id: str) -> None:
        # Double-click just emits the signal; actual dialog is opened
        # by _on_node_edit_requested
        step = None
        if self._route is not None:
            step = next((s for s in self._route.steps if s.id == step_id), None)
        if step is None and self._project is not None:
            try:
                task = self._project.get_task(TaskId(step_id))
                if task is not None:
                    step = RouteStep(
                        id=str(task.id), title=task.title,
                        duration_minutes=task.duration.minutes,
                        success_probability=0.5,
                        description=task.description,
                        branch="tasks", kind="action",
                    )
            except Exception:
                pass
        if step is not None:
            self.stepDoubleClicked.emit(step)

    def _on_node_edit_requested(self, step_id: str) -> None:
        """Open the modal NodeEditDialog for the given step."""
        step = None
        if self._route is not None:
            step = next((s for s in self._route.steps if s.id == step_id), None)
        if step is None and self._project is not None:
            try:
                task = self._project.get_task(TaskId(step_id))
                if task is not None:
                    step = RouteStep(
                        id=str(task.id), title=task.title,
                        duration_minutes=task.duration.minutes,
                        success_probability=0.5,
                        description=task.description,
                        branch="tasks", kind="action",
                    )
            except Exception:
                pass
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
        # Update the underlying Task position if it's a task
        if self._project is not None:
            try:
                task = self._project.get_task(TaskId(step_id))
                if task is not None:
                    task.x = x
                    task.y = y
                    task.touch()
            except Exception:
                pass

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
                pass
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
                        # Convert value to the right type
                        current = getattr(step, field)
                        if isinstance(current, int) and not isinstance(value, int):
                            try:
                                value = int(value)
                            except Exception:
                                pass
                        elif isinstance(current, float) and not isinstance(value, float):
                            try:
                                value = float(value)
                            except Exception:
                                pass
                        setattr(step, field, value)
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
                pass
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
           (event.button() == Qt.LeftButton and (event.modifiers() & Qt.SpaceModifier)):
            self._panning = True
            self._pan_last = event.position().toPoint()
            self.setCursor(Qt.ClosedHandCursor)
            event.accept()
            return
        item = self.itemAt(event.position().toPoint())
        if item is None:
            self.stepSelected.emit(None)
            self.insightSelected.emit(None)
            self._scene.clearSelection()
            # Close popup if clicking outside
            if self._details_popup is not None:
                self._details_popup.close()
                self._details_popup = None
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
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        if self._panning:
            self._panning = False
            self._pan_last = None
            self.setCursor(Qt.ArrowCursor)
            event.accept()
            return
        super().mouseReleaseEvent(event)

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
            else:
                menu.addAction("No actions available")
        else:
            add_task_action = menu.addAction("＋ Add Task Here")
            scene_pos = self.mapToScene(event.pos())
            add_task_action.triggered.connect(
                lambda: self.taskCreated.emit("New Task", scene_pos.x(), scene_pos.y())
            )

        menu.exec(event.globalPos())

    def _remove_step(self, step_id: str) -> None:
        """Remove a step from the route and the canvas."""
        if self._route is not None:
            self._route.steps = [s for s in self._route.steps if s.id != step_id]
            self._route.edges = [e for e in self._route.edges
                                  if e.source_id != step_id and e.target_id != step_id]
        # Remove from canvas
        item = self._node_items.pop(step_id, None)
        if item is not None:
            self._scene.removeItem(item)
        # Remove connected edges
        to_remove = [e for e in self._edge_items
                     if e.edge.source_id == step_id or e.edge.target_id == step_id]
        for edge in to_remove:
            self._scene.removeItem(edge)
            self._edge_items.remove(edge)

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

    def auto_layout(self) -> None:
        """Auto-layout all nodes with generous spacing and smooth animation."""
        if self._route is None or not self._route.steps:
            # Even if no route, layout any task nodes
            if self._node_items:
                self._auto_layout_all_nodes()
            return
        layout = self._compute_layout(self._route)

        # Animate nodes to new positions
        for step_id, (x, y) in layout.items():
            node = self._node_items.get(step_id)
            if node is not None:
                self._animate_node_to(node, x, y)

        # Reposition insight bubbles
        for bubble_id, bubble in self._bubble_items.items():
            pos = self._compute_bubble_position(bubble.insight, bubble)
            self._animate_node_to(bubble, pos.x(), pos.y())

        # Fit all after animation
        QTimer.singleShot(600, self.fit_all)

    def _auto_layout_all_nodes(self) -> None:
        """Layout all nodes on the canvas, even without a route."""
        if not self._node_items:
            return
        # Simple grid layout
        items = list(self._node_items.values())
        cols = max(1, int(math.ceil(math.sqrt(len(items)))))
        for i, item in enumerate(items):
            col = i % cols
            row = i // cols
            x = col * X_SPACING - (cols * X_SPACING) / 2
            y = row * Y_SPACING - ((len(items) // cols) * Y_SPACING) / 2
            self._animate_node_to(item, x, y)
        QTimer.singleShot(600, self.fit_all)

    def _animate_node_to(self, item, x: float, y: float) -> None:
        """Smoothly animate a QGraphicsItem to a new position."""
        # Use QPropertyAnimation for smooth movement
        anim = QPropertyAnimation(item, b"pos")
        anim.setDuration(400)
        anim.setStartValue(item.pos())
        anim.setEndValue(QPointF(x, y))
        anim.setEasingCurve(QEasingCurve.OutCubic)
        anim.start()
        # Keep reference to prevent garbage collection
        if not hasattr(self, '_layout_anims'):
            self._layout_anims = []
        self._layout_anims.append(anim)
        # Clean up old animations
        self._layout_anims = [a for a in self._layout_anims if a.state() == QPropertyAnimation.Running]
