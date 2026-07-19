"""
RouteGraphView — the visual walkable graph of an AI-generated Route.

Each RouteStep is a RouteNodeItem; dependencies become edges with
arrows. The view shows:

  - The success probability as a colored ring on each node
  - The critical path (longest dependency chain) highlighted in gold
  - The total duration and overall success at the top
  - Fallback edges shown as dashed arrows
  - Step ordering via topological layout

The user can pan, zoom, drag nodes, and click a node to see its
full details in the side panel.
"""
from __future__ import annotations

from collections import defaultdict, deque
from typing import Optional

from PySide6.QtCore import Qt, QRectF, QPointF, Signal, QTimer
from PySide6.QtGui import (
    QPainter, QPen, QBrush, QColor, QFont, QPainterPath, QPolygonF,
    QMouseEvent, QWheelEvent, QKeyEvent,
)
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QGraphicsView, QGraphicsScene,
    QGraphicsItem, QGraphicsRectItem, QGraphicsPathItem, QGraphicsTextItem,
    QFrame, QPushButton, QSizePolicy,
)

from ...ai import Route, RouteStep
from ...core.shamsi import ShamsiDate
from ..theme import Palette
from ..widgets.route_node_item import RouteNodeItem, NODE_WIDTH, NODE_HEIGHT


class RouteEdgeItem(QGraphicsPathItem):
    """An edge between two route-step nodes (a dependency arrow)."""

    def __init__(self, source: RouteNodeItem, target: RouteNodeItem,
                 is_critical: bool = False) -> None:
        super().__init__()
        self.source = source
        self.target = target
        self._is_critical = is_critical
        self.setZValue(5)
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
        start = self.source.anchor_out
        end = self.target.anchor_in
        # Map to local coordinates of this item
        start_local = self.mapFromScene(start)
        end_local = self.mapFromScene(end)

        path = QPainterPath(start_local)
        dx = end_local.x() - start_local.x()
        cx1 = start_local.x() + dx * 0.5
        cx2 = end_local.x() - dx * 0.5
        path.cubicTo(QPointF(cx1, start_local.y()),
                     QPointF(cx2, end_local.y()),
                     end_local)
        self.setPath(path)

        # Style
        if self._is_critical:
            pen = QPen(QColor(Palette.GOLD_BRIGHT), 2.5)
        else:
            pen = QPen(QColor(Palette.TEXT_TERTIARY), 1.5)
        pen.setCapStyle(Qt.RoundCap)
        self.setPen(pen)

        # Arrow head
        self._arrow = self._make_arrow(end_local)

    def _make_arrow(self, tip: QPointF) -> Optional[QGraphicsPolygonItem]:
        """Add an arrow head at the tip."""
        # Compute direction from the path's tangent at the end
        path = self.path()
        if path.isEmpty():
            return None
        length = path.length()
        if length < 1:
            return None
        back = path.pointAtPercent(max(0.0, 1.0 - 8 / length))
        direction = tip - back
        mag = (direction.x() ** 2 + direction.y() ** 2) ** 0.5
        if mag < 1e-3:
            return None
        ux, uy = direction.x() / mag, direction.y() / mag
        px, py = -uy, ux
        size = 8
        p1 = tip
        p2 = QPointF(tip.x() - ux * size + px * size * 0.5,
                     tip.y() - uy * size + py * size * 0.5)
        p3 = QPointF(tip.x() - ux * size - px * size * 0.5,
                     tip.y() - uy * size - py * size * 0.5)
        poly = QPolygonF([p1, p2, p3])
        color = QColor(Palette.GOLD_BRIGHT) if self._is_critical else QColor(Palette.TEXT_TERTIARY)
        # We can't add child items easily to a path item; instead, paint arrow in paint()
        self._arrow_poly = poly
        self._arrow_color = color
        return None

    def paint(self, painter: QPainter, option, widget=None) -> None:
        super().paint(painter, option, widget)
        # Draw arrow head
        if hasattr(self, "_arrow_poly") and self._arrow_poly is not None:
            painter.setBrush(QBrush(self._arrow_color))
            painter.setPen(Qt.NoPen)
            painter.drawPolygon(self._arrow_poly)


class RouteGraphView(QGraphicsView):
    """
    The graph view showing a single Route.

    Renders all steps as nodes, dependencies as edges, and highlights
    the critical path. Provides pan/zoom/fit-all.
    """
    stepSelected = Signal(object)  # RouteStep
    stepDoubleClicked = Signal(object)  # RouteStep

    def __init__(self, parent: QWidget = None) -> None:
        super().__init__(parent)
        self._route: Optional[Route] = None
        self._node_items: dict[str, RouteNodeItem] = {}
        self._edge_items: list[RouteEdgeItem] = []

        self._scene = QGraphicsScene(self)
        self.setScene(self._scene)
        self._scene.setBackgroundBrush(QBrush(QColor(Palette.BG_DEEPEST)))

        self.setRenderHint(QPainter.Antialiasing, True)
        self.setRenderHint(QPainter.SmoothPixmapTransform, True)
        self.setRenderHint(QPainter.TextAntialiasing, True)
        self.setViewportUpdateMode(QGraphicsView.FullViewportUpdate)
        self.setDragMode(QGraphicsView.RubberBandDrag)
        self.setAcceptDrops(True)
        self.setMouseTracking(True)

        self._panning = False
        self._pan_last: Optional[QPointF] = None

    # ---- Loading ----
    def set_route(self, route: Optional[Route]) -> None:
        self._route = route
        self._rebuild_scene()

    def _rebuild_scene(self) -> None:
        self._scene.clear()
        self._node_items.clear()
        self._edge_items.clear()

        if self._route is None or not self._route.steps:
            # Show empty-state message
            msg = QGraphicsTextItem("No route yet — describe a goal above to generate one.")
            msg.setDefaultTextColor(QColor(Palette.TEXT_TERTIARY))
            msg.setFont(QFont("Inter", 12))
            msg.setPos(0, 0)
            self._scene.addItem(msg)
            return

        # Compute layout
        layout = self._compute_layout(self._route)
        critical_path = self._compute_critical_path(self._route)

        # Add nodes
        for step in self._route.steps:
            item = RouteNodeItem(step)
            x, y = layout.get(step.id, (0, 0))
            item.setPos(x, y)
            item.nodeClicked.connect(self._on_node_clicked)
            item.nodeDoubleClicked.connect(self._on_node_double_clicked)
            self._scene.addItem(item)
            self._node_items[step.id] = item

        # Add edges
        for step in self._route.steps:
            for dep_id in step.depends_on:
                source = self._node_items.get(dep_id)
                target = self._node_items.get(step.id)
                if source is None or target is None:
                    continue
                is_crit = dep_id in critical_path and step.id in critical_path
                edge = RouteEdgeItem(source, target, is_critical=is_crit)
                self._scene.addItem(edge)
                self._edge_items.append(edge)

        # Fit to view
        QTimer.singleShot(50, self.fit_all)

    # ---- Layout & analysis ----
    def _compute_layout(self, route: Route) -> dict[str, tuple[float, float]]:
        """
        Hierarchical left-to-right layout (Sugiyama-style, simplified).

        Each step is assigned a rank = longest path from any root.
        Within each rank, steps are stacked vertically.
        """
        # Compute ranks
        ranks: dict[str, int] = {}
        in_degree: dict[str, int] = {s.id: 0 for s in route.steps}
        succ: dict[str, list[str]] = {s.id: [] for s in route.steps}
        for s in route.steps:
            for dep_id in s.depends_on:
                if dep_id in in_degree:
                    in_degree[s.id] += 1
                    if s.id not in succ[dep_id]:
                        succ[dep_id].append(s.id)

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
        # Unranked (cycles) → rank 0
        for s in route.steps:
            if s.id not in ranks:
                ranks[s.id] = 0

        # Group by rank
        by_rank: dict[int, list[str]] = defaultdict(list)
        for sid, r in ranks.items():
            by_rank[r].append(sid)

        # Position
        x_spacing = NODE_WIDTH + 100
        y_spacing = NODE_HEIGHT + 40
        positions: dict[str, tuple[float, float]] = {}
        max_rank = max(by_rank.keys()) if by_rank else 0
        for rank, sids in sorted(by_rank.items()):
            sids.sort()
            n = len(sids)
            total_h = n * y_spacing
            start_y = -total_h / 2
            x = rank * x_spacing - (max_rank * x_spacing) / 2
            for i, sid in enumerate(sids):
                positions[sid] = (x, start_y + i * y_spacing)
        return positions

    def _compute_critical_path(self, route: Route) -> list[str]:
        """
        Identify the longest dependency chain (by total duration).

        Returns the list of step ids on the critical path.
        """
        if not route.steps:
            return []
        # Build step lookup
        steps_by_id = {s.id: s for s in route.steps}
        # Memoized longest path ending at each step
        memo: dict[str, tuple[int, list[str]]] = {}

        def longest_path_ending_at(sid: str) -> tuple[int, list[str]]:
            if sid in memo:
                return memo[sid]
            step = steps_by_id[sid]
            if not step.depends_on:
                result = (step.duration_minutes, [sid])
            else:
                best = (0, [])
                for dep_id in step.depends_on:
                    if dep_id in steps_by_id:
                        dep_len, dep_path = longest_path_ending_at(dep_id)
                        if dep_len > best[0]:
                            best = (dep_len, dep_path)
                result = (best[0] + step.duration_minutes, best[1] + [sid])
            memo[sid] = result
            return result

        # Find the step with the longest total path
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

    # ---- Pan & zoom ----
    def wheelEvent(self, event: QWheelEvent) -> None:
        if event.modifiers() & Qt.ControlModifier:
            angle = event.angleDelta().y()
            factor = 1.15 if angle > 0 else 1 / 1.15
            self.scale(factor, factor)
        else:
            super().wheelEvent(event)

    def mousePressEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.MiddleButton or \
           (event.button() == Qt.LeftButton and (event.modifiers() & Qt.SpaceModifier)):
            self._panning = True
            self._pan_last = event.position().toPoint()
            self.setCursor(Qt.ClosedHandCursor)
            event.accept()
            return
        # Click on empty area → deselect
        item = self.itemAt(event.position().toPoint())
        if item is None:
            self.stepSelected.emit(None)
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
        if event.key() == Qt.Key_F:
            self.fit_all()
        elif event.key() == Qt.Key_Escape:
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
        self.fitInView(items_rect.adjusted(-60, -60, 60, 60), Qt.KeepAspectRatio)
