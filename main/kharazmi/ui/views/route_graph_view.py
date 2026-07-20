"""
RouteGraphView — a true workspace view of an AI-generated Route.

Features:
  - COMPLEX interconnected graph: branches, parallel paths, alternative
    edges (dashed), fallback edges (dotted), merge edges (thick)
  - Generous spacing — uses unlimited canvas space, no cramped nodes
  - Pan (middle-mouse or space+drag)
  - Zoom (Ctrl+wheel) — zooms around mouse position
  - Drag nodes anywhere
  - Auto-layout (L key) — DAG layout with branches spread vertically
  - Fit-in-view (F key)
  - Insight bubbles float as overlay boxes
  - Node entrance animations (fade-in + scale-up, staggered)
  - Critical path highlighted
"""
from __future__ import annotations

import math
import uuid
from collections import defaultdict, deque
from typing import Optional

from PySide6.QtCore import Qt, QRectF, QPointF, Signal, QTimer, QSizeF
from PySide6.QtGui import (
    QPainter, QPen, QBrush, QColor, QFont, QPainterPath, QPolygonF,
    QMouseEvent, QWheelEvent, QKeyEvent, QPainterPathStroker,
)
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QGraphicsView, QGraphicsScene,
    QGraphicsItem, QGraphicsRectItem, QGraphicsPathItem, QGraphicsTextItem,
    QFrame, QPushButton, QToolButton, QSizePolicy,
)

from ...ai import Route, RouteStep, RouteEdge, Insight
from ..theme import Palette
from ..widgets.route_node_item import RouteNodeItem
from ..widgets.insight_bubble import InsightBubble


# Edge style by kind
_EDGE_STYLES = {
    "primary":     {"color": "#D4AF37", "width": 2.0, "style": Qt.SolidLine},
    "alternative": {"color": "#5A7FA8", "width": 1.8, "style": Qt.DashLine},
    "fallback":    {"color": "#A85A5A", "width": 1.5, "style": Qt.DotLine},
    "merge":       {"color": "#F5C842", "width": 2.5, "style": Qt.SolidLine},
}

# Generous spacing — use unlimited canvas space
X_SPACING = 380   # horizontal gap between columns
Y_SPACING = 220   # vertical gap between rows in same column


class RouteEdgeItem(QGraphicsPathItem):
    """An edge between two route-step nodes."""

    def __init__(self, edge: RouteEdge, source: RouteNodeItem, target: RouteNodeItem,
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

        # Track node movement
        try:
            source.xChanged.connect(self._update_path)
            source.yChanged.connect(self._update_path)
            target.xChanged.connect(self._update_path)
            target.yChanged.connect(self._update_path)
        except Exception:
            pass

    def _update_path(self) -> None:
        # Choose anchors based on relative position
        src_pos = self.source.pos()
        tgt_pos = self.target.pos()
        src_w = self.source._width
        src_h = self.source._height
        tgt_w = self.target._width
        tgt_h = self.target._height

        # If target is to the right of source → out → in
        # If target is below source → bottom → top
        # If target is to the left → in → out (reverse)
        dx = tgt_pos.x() - src_pos.x()
        dy = tgt_pos.y() - src_pos.y()

        if abs(dx) > abs(dy):
            # Horizontal flow
            if dx > 0:
                start = self.source.anchor_out
                end = self.target.anchor_in
            else:
                start = self.source.anchor_in
                end = self.target.anchor_out
        else:
            # Vertical flow
            if dy > 0:
                start = self.source.anchor_bottom
                end = QPointF(self.target.mapToScene(QPointF(self.target._width / 2, 0)))
            else:
                start = self.source.anchor_top
                end = QPointF(self.target.mapToScene(QPointF(self.target._width / 2, self.target._height)))

        start_local = self.mapFromScene(start)
        end_local = self.mapFromScene(end)

        path = QPainterPath(start_local)
        # Cubic bezier with control points offset perpendicular to the line
        dx_l = end_local.x() - start_local.x()
        dy_l = end_local.y() - start_local.y()
        length = (dx_l ** 2 + dy_l ** 2) ** 0.5
        if length < 1:
            self.setPath(path)
            return
        # Control points
        offset = min(100, length * 0.4)
        if abs(dx_l) > abs(dy_l):
            # Horizontal — control points push horizontally
            cx1 = start_local.x() + (offset if dx_l > 0 else -offset)
            cy1 = start_local.y()
            cx2 = end_local.x() - (offset if dx_l > 0 else -offset)
            cy2 = end_local.y()
        else:
            # Vertical — control points push vertically
            cx1 = start_local.x()
            cy1 = start_local.y() + (offset if dy_l > 0 else -offset)
            cx2 = end_local.x()
            cy2 = end_local.y() - (offset if dy_l > 0 else -offset)
        path.cubicTo(QPointF(cx1, cy1), QPointF(cx2, cy2), end_local)
        self.setPath(path)

        # Style based on edge kind
        kind = self.edge.kind if self.edge.kind in _EDGE_STYLES else "primary"
        style = _EDGE_STYLES[kind]
        color = QColor(style["color"])
        if self._is_critical:
            color = QColor(Palette.GOLD_BRIGHT)
        pen = QPen(color, style["width"], style["style"])
        pen.setCapStyle(Qt.RoundCap)
        self.setPen(pen)
        self._arrow_color = color

        # Compute arrow head
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

        # Update or create label
        if self.edge.label:
            mid = path_obj.pointAtPercent(0.5)
            if self._label_item is None:
                self._label_item = QGraphicsTextItem(self.edge.label)
                self._label_item.setDefaultTextColor(QColor(color))
                label_font = QFont("JetBrains Mono", 8)
                self._label_item.setFont(label_font)
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


class RouteGraphView(QGraphicsView):
    """
    A workspace view showing a Route graph + floating insight bubbles.

    Full pan/zoom/drag support. Nodes auto-size to fit content.
    Edges support primary/alternative/fallback/merge styles.
    """
    stepSelected = Signal(object)
    stepDoubleClicked = Signal(object)
    insightSelected = Signal(object)

    def __init__(self, parent: QWidget = None) -> None:
        super().__init__(parent)
        self._route: Optional[Route] = None
        self._node_items: dict[str, RouteNodeItem] = {}
        self._edge_items: list[RouteEdgeItem] = []
        self._bubble_items: dict[str, InsightBubble] = {}

        self._scene = QGraphicsScene(self)
        self.setScene(self._scene)
        self._scene.setBackgroundBrush(QBrush(QColor(Palette.BG_DEEPEST)))
        # Set a huge scene rect so the user can pan freely
        self._scene.setSceneRect(-5000, -5000, 10000, 10000)

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
        """Floating zoom/layout controls at the bottom-right."""
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
        ]:
            btn = QToolButton()
            btn.setText(label)
            btn.setFixedSize(28, 28)
            btn.setToolTip(tip)
            btn.setStyleSheet(f"""
                QToolButton {{
                    background-color: transparent;
                    color: {Palette.GOLD_BRIGHT};
                    border: none;
                    font-size: 14px;
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

    def _reposition_controls(self) -> None:
        if hasattr(self, "_controls"):
            self._controls.move(self.width() - self._controls.width() - 16,
                                self.height() - self._controls.height() - 16)
            self._controls.raise_()

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self._reposition_controls()

    # ---- Loading ----
    def set_route(self, route: Optional[Route]) -> None:
        self._route = route
        self._rebuild_scene(animate=True)

    def add_steps_and_edges(self, steps: list[RouteStep], edges: list[RouteEdge],
                             insights: list[Insight] = None) -> None:
        """Add new steps/edges to the existing route graph (for 'continue working')."""
        if self._route is None:
            return
        # Add to route
        self._route.steps.extend(steps)
        self._route.edges.extend(edges)
        if insights:
            self._route.insights.extend(insights)

        # Compute layout for ALL nodes (re-layout to make room)
        layout = self._compute_layout(self._route)

        # Add new node items (don't touch existing ones' positions if user moved them)
        for step in steps:
            if step.id in self._node_items:
                continue
            item = RouteNodeItem(step)
            x, y = layout.get(step.id, (0, 0))
            item.setPos(x, y)
            item.nodeClicked.connect(self._on_node_clicked)
            item.nodeDoubleClicked.connect(self._on_node_double_clicked)
            self._scene.addItem(item)
            self._node_items[step.id] = item
            # Animate entrance
            delay = list(self._node_items.values()).index(item) * 80
            item.animate_entrance(delay_ms=delay)

        # Add new edges
        for edge in edges:
            source = self._node_items.get(edge.source_id)
            target = self._node_items.get(edge.target_id)
            if source is None or target is None:
                continue
            # Check if edge already exists
            existing = next((e for e in self._edge_items
                             if e.edge.source_id == edge.source_id
                             and e.edge.target_id == edge.target_id
                             and e.edge.kind == edge.kind), None)
            if existing is not None:
                continue
            is_crit = False  # could compute critical path again
            edge_item = RouteEdgeItem(edge, source, target, is_critical=is_crit)
            self._scene.addItem(edge_item)
            self._edge_items.append(edge_item)

        # Add new insight bubbles
        if insights:
            for insight in insights:
                bubble_id = f"ib-{uuid.uuid4().hex[:8]}"
                bubble = InsightBubble(insight, bubble_id)
                pos = self._compute_bubble_position(insight, bubble)
                bubble.setPos(pos)
                bubble.bubbleClicked.connect(self._on_bubble_clicked)
                self._scene.addItem(bubble)
                self._bubble_items[bubble_id] = bubble

        self.update()

    def add_insights(self, insights: list[Insight]) -> None:
        """Add additional insights to the canvas."""
        self.add_steps_and_edges([], [], insights)

    def _compute_bubble_position(self, insight: Insight,
                                  bubble: InsightBubble) -> QPointF:
        """Compute a position for a bubble on the canvas."""
        if insight.anchor_step_id and insight.anchor_step_id in self._node_items:
            node = self._node_items[insight.anchor_step_id]
            node_pos = node.pos()
            node_w = node._width
            # Place bubble to the right of the node, offset down a bit
            x = node_pos.x() + node_w + 40
            y = node_pos.y() + 20
            return QPointF(x, y)
        # Use x_hint/y_hint relative to bounding rect, place ABOVE the route
        items_rect = self._scene.itemsBoundingRect()
        if items_rect.isNull():
            return QPointF(insight.x_hint * 800 - 400, insight.y_hint * 600 - 300)
        x = items_rect.left() + insight.x_hint * items_rect.width()
        y = items_rect.top() - 100 - insight.y_hint * 80
        return QPointF(x, y)

    def _rebuild_scene(self, animate: bool = False) -> None:
        self._scene.clear()
        self._node_items.clear()
        self._edge_items.clear()
        self._bubble_items.clear()

        if self._route is None:
            msg = QGraphicsTextItem("No route yet — describe a goal above to generate one.")
            msg.setDefaultTextColor(QColor(Palette.TEXT_TERTIARY))
            msg.setFont(QFont("Inter", 12))
            msg.setPos(0, 0)
            self._scene.addItem(msg)
            return

        layout = self._compute_layout(self._route)
        critical_path = self._compute_critical_path(self._route)

        # Add nodes with staggered animation
        for i, step in enumerate(self._route.steps):
            item = RouteNodeItem(step)
            x, y = layout.get(step.id, (0, 0))
            item.setPos(x, y)
            item.nodeClicked.connect(self._on_node_clicked)
            item.nodeDoubleClicked.connect(self._on_node_double_clicked)
            self._scene.addItem(item)
            self._node_items[step.id] = item
            if animate:
                item.animate_entrance(delay_ms=i * 80)

        # Build a lookup of edges by (source, target, kind) for dedup
        seen_edges = set()
        # Add edges from explicit edges list
        for edge in self._route.edges:
            key = (edge.source_id, edge.target_id, edge.kind)
            if key in seen_edges:
                continue
            seen_edges.add(key)
            source = self._node_items.get(edge.source_id)
            target = self._node_items.get(edge.target_id)
            if source is None or target is None:
                continue
            is_crit = edge.source_id in critical_path and edge.target_id in critical_path and edge.kind in ("primary", "merge")
            edge_item = RouteEdgeItem(edge, source, target, is_critical=is_crit)
            self._scene.addItem(edge_item)
            self._edge_items.append(edge_item)
        # Also add edges implied by depends_on (if not already in explicit list)
        for step in self._route.steps:
            for dep_id in step.depends_on:
                key = (dep_id, step.id, "primary")
                if key in seen_edges:
                    continue
                seen_edges.add(key)
                source = self._node_items.get(dep_id)
                target = self._node_items.get(step.id)
                if source is None or target is None:
                    continue
                edge = RouteEdge(source_id=dep_id, target_id=step.id, kind="primary")
                is_crit = dep_id in critical_path and step.id in critical_path
                edge_item = RouteEdgeItem(edge, source, target, is_critical=is_crit)
                self._scene.addItem(edge_item)
                self._edge_items.append(edge_item)

        # Add insight bubbles
        for insight in self._route.insights:
            bubble_id = f"ib-{uuid.uuid4().hex[:8]}"
            bubble = InsightBubble(insight, bubble_id)
            pos = self._compute_bubble_position(insight, bubble)
            bubble.setPos(pos)
            bubble.bubbleClicked.connect(self._on_bubble_clicked)
            self._scene.addItem(bubble)
            self._bubble_items[bubble_id] = bubble

        # Fit to view
        QTimer.singleShot(50, self.fit_all)

    # ---- Layout & analysis ----
    def _compute_layout(self, route: Route) -> dict[str, tuple[float, float]]:
        """
        Hierarchical DAG layout with branches spread vertically.

        Uses generous spacing (X_SPACING=380, Y_SPACING=220) so nodes
        have plenty of room.
        """
        if not route.steps:
            return {}
        # Compute ranks (longest path from any root)
        steps_by_id = {s.id: s for s in route.steps}
        ranks: dict[str, int] = {}
        in_degree: dict[str, int] = {s.id: 0 for s in route.steps}
        succ: dict[str, list[str]] = {s.id: [] for s in route.steps}

        # Build edges from depends_on AND explicit edges
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

        # Group by rank
        by_rank: dict[int, list[str]] = defaultdict(list)
        for sid, r in ranks.items():
            by_rank[r].append(sid)

        # Within each rank, group by branch
        # Sort: main branch first, then alt-N, then fallback-N
        def branch_sort_key(sid: str) -> tuple:
            step = steps_by_id.get(sid)
            if step is None:
                return (99, "")
            b = step.branch
            if b == "main":
                return (0, "")
            elif b.startswith("alt-"):
                try:
                    return (1, b)
                except Exception:
                    return (1, b)
            elif b.startswith("fallback-"):
                return (2, b)
            return (3, b)

        # Position nodes
        positions: dict[str, tuple[float, float]] = {}
        max_rank = max(by_rank.keys()) if by_rank else 0

        # For each rank, sort by branch and stack vertically with big spacing
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
        """Identify the longest dependency chain (by total duration)."""
        if not route.steps:
            return []
        steps_by_id = {s.id: s for s in route.steps}
        memo: dict[str, tuple[int, list[str]]] = {}

        def longest_path_ending_at(sid: str) -> tuple[int, list[str]]:
            if sid in memo:
                return memo[sid]
            step = steps_by_id[sid]
            # Collect predecessors from depends_on AND explicit edges
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
        step = next((s for s in self._route.steps if s.id == step_id), None) if self._route else None
        if step is not None:
            self.stepSelected.emit(step)

    def _on_node_double_clicked(self, step_id: str) -> None:
        step = next((s for s in self._route.steps if s.id == step_id), None) if self._route else None
        if step is not None:
            self.stepDoubleClicked.emit(step)

    def _on_bubble_clicked(self, bubble_id: str) -> None:
        bubble = self._bubble_items.get(bubble_id)
        if bubble is not None:
            self.insightSelected.emit(bubble.insight)

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
        else:
            super().keyPressEvent(event)

    # ---- Background grid ----
    def drawBackground(self, painter: QPainter, rect: QRectF) -> None:
        painter.fillRect(rect, QColor(Palette.BG_DEEPEST))
        # Subtle dot grid
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
        # Major grid every 100px
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
