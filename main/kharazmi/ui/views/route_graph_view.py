"""
RouteGraphView — a true workspace view of an AI-generated Route.

Features:
  - Pan (middle-mouse or space+drag)
  - Zoom (Ctrl+wheel) — fully scalable
  - Multi-select (rubber-band or Shift+click)
  - Drag nodes/bubbles anywhere
  - Auto-layout (L key)
  - Fit-in-view (F key)
  - Insight bubbles float as overlay boxes around the route
  - Critical path highlighted in gold
  - Background dot grid
"""
from __future__ import annotations

import math
import uuid
from collections import defaultdict, deque
from typing import Optional

from PySide6.QtCore import Qt, QRectF, QPointF, Signal, QTimer, QSizeF
from PySide6.QtGui import (
    QPainter, QPen, QBrush, QColor, QFont, QPainterPath, QPolygonF,
    QMouseEvent, QWheelEvent, QKeyEvent,
)
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QGraphicsView, QGraphicsScene,
    QGraphicsItem, QGraphicsRectItem, QGraphicsPathItem, QGraphicsTextItem,
    QFrame, QPushButton, QToolButton, QSizePolicy,
)

from ...ai import Route, RouteStep, Insight
from ..theme import Palette
from ..widgets.route_node_item import RouteNodeItem
from ..widgets.insight_bubble import InsightBubble


class RouteEdgeItem(QGraphicsPathItem):
    """An edge between two route-step nodes (a dependency arrow)."""

    def __init__(self, source: RouteNodeItem, target: RouteNodeItem,
                 is_critical: bool = False) -> None:
        super().__init__()
        self.source = source
        self.target = target
        self._is_critical = is_critical
        self.setZValue(5)
        self._arrow_poly: Optional[QPolygonF] = None
        self._arrow_color = QColor(Palette.TEXT_TERTIARY)
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
        start_local = self.mapFromScene(start)
        end_local = self.mapFromScene(end)

        path = QPainterPath(start_local)
        dx = end_local.x() - start_local.x()
        # Use cubic bezier with horizontal control points
        cx1 = start_local.x() + max(40, dx * 0.5)
        cx2 = end_local.x() - max(40, dx * 0.5)
        path.cubicTo(QPointF(cx1, start_local.y()),
                     QPointF(cx2, end_local.y()),
                     end_local)
        self.setPath(path)

        if self._is_critical:
            pen = QPen(QColor(Palette.GOLD_BRIGHT), 2.5)
        else:
            pen = QPen(QColor(Palette.TEXT_TERTIARY), 1.5)
        pen.setCapStyle(Qt.RoundCap)
        self.setPen(pen)

        # Compute arrow head polygon
        path_obj = self.path()
        if path_obj.isEmpty():
            self._arrow_poly = None
            return
        length = path_obj.length()
        if length < 1:
            self._arrow_poly = None
            return
        back = path_obj.pointAtPercent(max(0.0, 1.0 - 10 / length))
        direction = end_local - back
        mag = (direction.x() ** 2 + direction.y() ** 2) ** 0.5
        if mag < 1e-3:
            self._arrow_poly = None
            return
        ux, uy = direction.x() / mag, direction.y() / mag
        px, py = -uy, ux
        size = 9
        p1 = end_local
        p2 = QPointF(end_local.x() - ux * size + px * size * 0.5,
                     end_local.y() - uy * size + py * size * 0.5)
        p3 = QPointF(end_local.x() - ux * size - px * size * 0.5,
                     end_local.y() - uy * size - py * size * 0.5)
        self._arrow_poly = QPolygonF([p1, p2, p3])
        self._arrow_color = QColor(Palette.GOLD_BRIGHT) if self._is_critical else QColor(Palette.TEXT_TERTIARY)

    def paint(self, painter: QPainter, option, widget=None) -> None:
        super().paint(painter, option, widget)
        if self._arrow_poly is not None:
            painter.setBrush(QBrush(self._arrow_color))
            painter.setPen(Qt.NoPen)
            painter.drawPolygon(self._arrow_poly)


class RouteGraphView(QGraphicsView):
    """
    A workspace view showing a Route graph + floating insight bubbles.

    Full pan/zoom/drag/customize support.
    """
    stepSelected = Signal(object)  # RouteStep or None
    stepDoubleClicked = Signal(object)  # RouteStep
    insightSelected = Signal(object)  # Insight or None

    def __init__(self, parent: QWidget = None) -> None:
        super().__init__(parent)
        self._route: Optional[Route] = None
        self._node_items: dict[str, RouteNodeItem] = {}
        self._edge_items: list[RouteEdgeItem] = []
        self._bubble_items: dict[str, InsightBubble] = {}
        # Track insight positions (persist across route updates)
        self._bubble_positions: dict[str, QPointF] = {}

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

        # Build floating control toolbar (bottom-right)
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

        # Position the controls at bottom-right; reposition on resize
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
        self._rebuild_scene()

    def add_insights(self, insights: list[Insight]) -> None:
        """Add additional insights to the canvas without rebuilding everything."""
        if self._route is None:
            return
        for insight in insights:
            bubble_id = f"ib-{uuid.uuid4().hex[:8]}"
            bubble = InsightBubble(insight, bubble_id)
            # Position
            pos = self._compute_bubble_position(insight, bubble)
            bubble.setPos(pos)
            bubble.bubbleClicked.connect(self._on_bubble_clicked)
            self._scene.addItem(bubble)
            self._bubble_items[bubble_id] = bubble
            # Track position
            self._bubble_positions[bubble_id] = pos
        self.update()

    def _compute_bubble_position(self, insight: Insight,
                                  bubble: InsightBubble) -> QPointF:
        """Compute a position for a bubble on the canvas."""
        # If anchored to a step, float near that node
        if insight.anchor_step_id and insight.anchor_step_id in self._node_items:
            node = self._node_items[insight.anchor_step_id]
            node_pos = node.pos()
            node_w = node._width
            node_h = node._height
            # Place bubble to the right of the node (or below if no room)
            x = node_pos.x() + node_w + 20
            y = node_pos.y() - 10
            return QPointF(x, y)
        # Otherwise use x_hint/y_hint relative to scene bounding rect
        items_rect = self._scene.itemsBoundingRect()
        if items_rect.isNull():
            return QPointF(insight.x_hint * 800 - 400, insight.y_hint * 600 - 300)
        # Position relative to the bounding rect, offset to the perimeter
        x = items_rect.left() + insight.x_hint * items_rect.width()
        y = items_rect.top() - 80 - insight.y_hint * 60  # above the route
        # Spread horizontally
        return QPointF(x, y)

    def _rebuild_scene(self) -> None:
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

        # Add insight bubbles from the route
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
        """Hierarchical left-to-right layout (Sugiyama-style, simplified)."""
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
        for s in route.steps:
            if s.id not in ranks:
                ranks[s.id] = 0

        by_rank: dict[int, list[str]] = defaultdict(list)
        for sid, r in ranks.items():
            by_rank[r].append(sid)

        x_spacing = 320  # wider since nodes auto-size
        y_spacing = 170
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
        """Identify the longest dependency chain (by total duration)."""
        if not route.steps:
            return []
        steps_by_id = {s.id: s for s in route.steps}
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

    # ---- Pan & zoom (workspace behavior) ----
    def wheelEvent(self, event: QWheelEvent) -> None:
        # Zoom around mouse position
        angle = event.angleDelta().y()
        factor = 1.15 if angle > 0 else 1 / 1.15
        # Save mouse position in scene coords
        mouse_scene = self.mapToScene(event.position().toPoint())
        self.scale(factor, factor)
        # Adjust to keep mouse position stable
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
        # Click on empty area → deselect
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
        self.fitInView(items_rect.adjusted(-60, -60, 60, 60), Qt.KeepAspectRatio)

    def auto_layout(self) -> None:
        """Re-run the auto-layout algorithm and reposition nodes."""
        if self._route is None:
            return
        layout = self._compute_layout(self._route)
        for step_id, (x, y) in layout.items():
            node = self._node_items.get(step_id)
            if node is not None:
                node.setPos(x, y)
        # Re-position bubbles
        for bubble_id, bubble in self._bubble_items.items():
            pos = self._compute_bubble_position(bubble.insight, bubble)
            bubble.setPos(pos)
        self.fit_all()
