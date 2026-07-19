"""
RouteGraphView — unified workspace for BOTH AI route nodes AND Tasks nodes.

This is now THE workspace — no separate Tasks window. AI-generated
route steps and user-created Tasks coexist on the same canvas.

Features:
  - TRUE streaming: nodes appear one-by-one as AI generates them
  - Complex interconnected graph: branches, parallel paths, alternative
    edges (dashed), fallback edges (dotted), merge edges (thick)
  - Generous spacing — unlimited canvas space
  - Pan / zoom / drag / customize
  - Inline node editing (double-click)
  - Floating StepDetailsPopup (closeable, draggable)
  - Insight bubbles float as overlay boxes
  - Heavily enhanced node animations
  - Tasks nodes and Route nodes share the same canvas
"""
from __future__ import annotations

import math
import uuid
from collections import defaultdict, deque
from typing import Optional

from PySide6.QtCore import Qt, QRectF, QPointF, Signal, QTimer, QSizeF
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
_EDGE_STYLES = {
    "primary":     {"color": "#D4AF37", "width": 2.0, "style": Qt.SolidLine},
    "alternative": {"color": "#5A7FA8", "width": 1.8, "style": Qt.DashLine},
    "fallback":    {"color": "#A85A5A", "width": 1.5, "style": Qt.DotLine},
    "merge":       {"color": "#F5C842", "width": 2.5, "style": Qt.SolidLine},
}

# Generous spacing
X_SPACING = 380
Y_SPACING = 220


class UnifiedEdgeItem(QGraphicsPathItem):
    """An edge between two nodes (route or task)."""

    def __init__(self, edge: RouteEdge, source, target,
                 is_critical: bool = False) -> None:
        super().__init__()
        self.edge = edge
        self.source = source
        self.target = target
        self._is_critical = is_critical
        self.setZValue(5)
        self._arrow_poly: Optional[QPolygonF] = None
        self._arrow_color = QColor(Palette.TEXT_TERTIARY)
        self._label_item: Optional[QGraphicsTextItem] = None
        self._update_path()
        try:
            source.xChanged.connect(self._update_path)
            source.yChanged.connect(self._update_path)
            target.xChanged.connect(self._update_path)
            target.yChanged.connect(self._update_path)
        except Exception:
            pass

    def _update_path(self) -> None:
        src_pos = self.source.pos()
        tgt_pos = self.target.pos()
        dx = tgt_pos.x() - src_pos.x()
        dy = tgt_pos.y() - src_pos.y()

        if abs(dx) > abs(dy):
            if dx > 0:
                start = self.source.anchor_out
                end = self.target.anchor_in
            else:
                start = self.source.anchor_in
                end = self.target.anchor_out
        else:
            if dy > 0:
                start = self.source.anchor_bottom
                end = QPointF(self.target.mapToScene(QPointF(self.target._width / 2, 0)))
            else:
                start = self.source.anchor_top
                end = QPointF(self.target.mapToScene(QPointF(self.target._width / 2, self.target._height)))

        start_local = self.mapFromScene(start)
        end_local = self.mapFromScene(end)

        path = QPainterPath(start_local)
        dx_l = end_local.x() - start_local.x()
        dy_l = end_local.y() - start_local.y()
        length = (dx_l ** 2 + dy_l ** 2) ** 0.5
        if length < 1:
            self.setPath(path)
            return
        offset = min(100, length * 0.4)
        if abs(dx_l) > abs(dy_l):
            cx1 = start_local.x() + (offset if dx_l > 0 else -offset)
            cy1 = start_local.y()
            cx2 = end_local.x() - (offset if dx_l > 0 else -offset)
            cy2 = end_local.y()
        else:
            cx1 = start_local.x()
            cy1 = start_local.y() + (offset if dy_l > 0 else -offset)
            cx2 = end_local.x()
            cy2 = end_local.y() - (offset if dy_l > 0 else -offset)
        path.cubicTo(QPointF(cx1, cy1), QPointF(cx2, cy2), end_local)
        self.setPath(path)

        kind = self.edge.kind if self.edge.kind in _EDGE_STYLES else "primary"
        style = _EDGE_STYLES[kind]
        color = QColor(style["color"])
        if self._is_critical:
            color = QColor(Palette.GOLD_BRIGHT)
        pen = QPen(color, style["width"], style["style"])
        pen.setCapStyle(Qt.RoundCap)
        self.setPen(pen)
        self._arrow_color = color

        path_obj = self.path()
        if path_obj.isEmpty():
            self._arrow_poly = None
            return
        length_p = path_obj.length()
        if length_p < 1:
            self._arrow_poly = None
            return
        back = path_obj.pointAtPercent(max(0.0, 1.0 - 12 / length_p))
        direction = end_local - back
        mag = (direction.x() ** 2 + direction.y() ** 2) ** 0.5
        if mag < 1e-3:
            self._arrow_poly = None
            return
        ux, uy = direction.x() / mag, direction.y() / mag
        px, py = -uy, ux
        size = 10
        p1 = end_local
        p2 = QPointF(end_local.x() - ux * size + px * size * 0.5,
                     end_local.y() - uy * size + py * size * 0.5)
        p3 = QPointF(end_local.x() - ux * size - px * size * 0.5,
                     end_local.y() - uy * size - py * size * 0.5)
        self._arrow_poly = QPolygonF([p1, p2, p3])

        if self.edge.label:
            mid = path_obj.pointAtPercent(0.5)
            if self._label_item is None:
                self._label_item = QGraphicsTextItem(self.edge.label)
                self._label_item.setDefaultTextColor(QColor(color))
                self._label_item.setFont(QFont("JetBrains Mono", 8))
                self._label_item.setParentItem(self)
            self._label_item.setPlainText(self.edge.label)
            self._label_item.setPos(mid.x() - self._label_item.boundingRect().width() / 2,
                                     mid.y() - self._label_item.boundingRect().height() / 2)
        elif self._label_item is not None:
            self._label_item.setParentItem(None)
            self._label_item = None

    def paint(self, painter: QPainter, option, widget=None) -> None:
        super().paint(painter, option, widget)
        if self._arrow_poly is not None:
            painter.setBrush(QBrush(self._arrow_color))
            painter.setPen(Qt.NoPen)
            painter.drawPolygon(self._arrow_poly)


class UnifiedGraphView(QGraphicsView):
    """
    The unified workspace view — holds BOTH AI route nodes AND Tasks nodes.

    This replaces both the old RouteGraphView and the old NodeGraphView.
    """
    stepSelected = Signal(object)  # RouteStep or Task or None
    stepDoubleClicked = Signal(object)
    insightSelected = Signal(object)
    stepFieldChanged = Signal(str, str, object)  # step_id, field, value
    taskCreated = Signal(str, float, float)  # title, x, y — request to create a task
    stepBreakdownRequested = Signal(str)  # step_id — request AI breakdown

    def __init__(self, parent: QWidget = None) -> None:
        super().__init__(parent)
        self._route: Optional[Route] = None
        self._project: Optional[Project] = None
        self._node_items: dict[str, RouteNodeItem] = {}  # unified: both route steps and tasks
        self._edge_items: list[UnifiedEdgeItem] = []
        self._bubble_items: dict[str, InsightBubble] = {}
        self._details_popup: Optional[StepDetailsPopup] = None

        self._scene = QGraphicsScene(self)
        self.setScene(self._scene)
        self._scene.setBackgroundBrush(QBrush(QColor(Palette.BG_DEEPEST)))
        self._scene.setSceneRect(-10000, -10000, 20000, 20000)

        self.setRenderHint(QPainter.Antialiasing, True)
        self.setRenderHint(QPainter.SmoothPixmapTransform, True)
        self.setRenderHint(QPainter.TextAntialiasing, True)
        self.setViewportUpdateMode(QGraphicsView.FullViewportUpdate)
        self.setDragMode(QGraphicsView.RubberBandDrag)
        self.setAcceptDrops(True)
        self.setMouseTracking(True)

        self._panning = False
        self._pan_last: Optional[QPointF] = None

        self._build_controls()

    def _build_controls(self) -> None:
        self._controls = QFrame(self)
        self._controls.setStyleSheet(f"""
            QFrame {{
                background-color: {Palette.BG_TERTIARY};
                border: 1px solid {Palette.BORDER_NORMAL};
                border-radius: 6px;
            }}
        """)
        layout = QHBoxLayout(self._controls)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(2)

        for label, tip, handler in [
            ("＋", "Zoom in", lambda: self.scale(1.2, 1.2)),
            ("－", "Zoom out", lambda: self.scale(1/1.2, 1/1.2)),
            ("⤢", "Fit to view", self.fit_all),
            ("⇆", "Auto-layout", self.auto_layout),
            ("＋◆", "Add task", self._on_add_task),
        ]:
            btn = QToolButton()
            btn.setText(label)
            btn.setFixedSize(32, 28)
            btn.setToolTip(tip)
            btn.setStyleSheet(f"""
                QToolButton {{
                    background-color: transparent;
                    color: {Palette.GOLD_BRIGHT};
                    border: none;
                    font-size: 13px;
                    font-weight: bold;
                    border-radius: 4px;
                }}
                QToolButton:hover {{
                    background-color: {Palette.BG_HOVER};
                }}
            """)
            btn.clicked.connect(handler)
            layout.addWidget(btn)

        self._reposition_controls()

    def _on_add_task(self) -> None:
        """Add a new task node at the center of the current view."""
        center = self.mapToScene(self.viewport().rect().center())
        self.taskCreated.emit("New Task", center.x(), center.y())

    def _reposition_controls(self) -> None:
        if hasattr(self, "_controls"):
            self._controls.move(self.width() - self._controls.width() - 16,
                                self.height() - self._controls.height() - 16)
            self._controls.raise_()

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self._reposition_controls()

    # ---- Project / Task integration ----
    def set_project(self, project: Project) -> None:
        """Attach a Project (for Tasks). Existing tasks are loaded as nodes."""
        self._project = project
        self._sync_tasks_to_canvas()

    def _sync_tasks_to_canvas(self) -> None:
        """Add Task nodes from the project to the canvas (without removing route nodes)."""
        if self._project is None:
            return
        for task in self._project.tasks():
            if str(task.id) in self._node_items:
                continue
            # Convert Task to a RouteStep-like for unified rendering
            step = RouteStep(
                id=str(task.id),
                title=task.title,
                duration_minutes=task.duration.minutes,
                success_probability=0.5,
                location="",
                description=task.description,
                fallback="",
                depends_on=[str(d.predecessor_id) for d in self._project.dependencies_of(task.id)],
                sub_goals=[],
                cost_estimate="",
                risk_level="low",
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
                           animate=True, delay_ms=i * 100)

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

        QTimer.singleShot(100, self.fit_all)

    def _add_node(self, step: RouteStep, x: float = 0, y: float = 0,
                  animate: bool = False, delay_ms: int = 0) -> RouteNodeItem:
        """Add a single node to the canvas."""
        item = RouteNodeItem(step)
        item.setPos(x, y)
        item.nodeClicked.connect(self._on_node_clicked)
        item.nodeDoubleClicked.connect(self._on_node_double_clicked)
        item.nodeMoved.connect(self._on_node_moved)
        item.nodeEdited.connect(self._on_node_edited)
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

    # Keep alias for backward compat
    def add_insights(self, insights: list[Insight]) -> None:
        self.add_steps_and_edges([], [], insights)

    def _compute_bubble_position(self, insight: Insight, bubble) -> QPointF:
        if insight.anchor_step_id and insight.anchor_step_id in self._node_items:
            node = self._node_items[insight.anchor_step_id]
            node_pos = node.pos()
            node_w = node._width
            return QPointF(node_pos.x() + node_w + 40, node_pos.y() + 20)
        items_rect = self._scene.itemsBoundingRect()
        if items_rect.isNull():
            return QPointF(insight.x_hint * 800 - 400, insight.y_hint * 600 - 300)
        x = items_rect.left() + insight.x_hint * items_rect.width()
        y = items_rect.top() - 100 - insight.y_hint * 80
        return QPointF(x, y)

    # ---- Layout & analysis ----
    def _compute_layout(self, route: Route) -> dict[str, tuple[float, float]]:
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
            total_h = (n - 1) * Y_SPACING
            start_y = -total_h / 2
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
        # Inline editing is handled by the node itself
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
        while item is not None:
            if isinstance(item, RouteNodeItem):
                step_id = item.step.id
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

                # Edit action
                edit_action = menu.addAction(f"✏️ Edit: {step.title}")
                edit_action.triggered.connect(lambda: item and item.start_editing() if isinstance(item, RouteNodeItem) else None)

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
        if self._route is None:
            return
        layout = self._compute_layout(self._route)
        for step_id, (x, y) in layout.items():
            node = self._node_items.get(step_id)
            if node is not None:
                node.setPos(x, y)
        for bubble_id, bubble in self._bubble_items.items():
            pos = self._compute_bubble_position(bubble.insight, bubble)
            bubble.setPos(pos)
        self.fit_all()
