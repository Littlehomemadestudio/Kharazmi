"""
Vector icons drawn in code — no external image files needed.

Each function returns a QIcon built from a QPolygonF / QPainterPath.
This keeps the application self-contained.
"""
from __future__ import annotations

from PySide6.QtCore import QPointF, QRectF, Qt, QSize
from PySide6.QtGui import (
    QIcon, QPainter, QPainterPath, QPolygonF, QPixmap, QColor,
    QPen, QBrush, QLinearGradient,
)
from .theme import Palette


def _new_pixmap(size: int = 24) -> tuple[QPixmap, QPainter]:
    pm = QPixmap(size, size)
    pm.fill(Qt.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.Antialiasing, True)
    p.setRenderHint(QPainter.SmoothPixmapTransform, True)
    return pm, p


def _to_icon(pm: QPixmap) -> QIcon:
    return QIcon(pm)


def icon_plus() -> QIcon:
    pm, p = _new_pixmap()
    pen = QPen(QColor(Palette.GOLD_BRIGHT), 2.5)
    pen.setCapStyle(Qt.RoundCap)
    p.setPen(pen)
    p.drawLine(12, 5, 12, 19)
    p.drawLine(5, 12, 19, 12)
    p.end()
    return _to_icon(pm)


def icon_minus() -> QIcon:
    pm, p = _new_pixmap()
    pen = QPen(QColor(Palette.TEXT_SECONDARY), 2.5)
    pen.setCapStyle(Qt.RoundCap)
    p.setPen(pen)
    p.drawLine(5, 12, 19, 12)
    p.end()
    return _to_icon(pm)


def icon_trash() -> QIcon:
    pm, p = _new_pixmap()
    p.setPen(QPen(QColor(Palette.STATUS_BLOCKED), 2))
    p.setBrush(QBrush(QColor(Palette.STATUS_BLOCKED)))
    # Lid
    p.drawLine(5, 7, 19, 7)
    p.drawLine(9, 5, 15, 5)
    p.drawLine(12, 5, 12, 7)
    # Body
    p.setBrush(Qt.NoBrush)
    p.drawRoundedRect(7, 7, 10, 12, 2, 2)
    p.drawLine(10, 10, 10, 17)
    p.drawLine(14, 10, 14, 17)
    p.end()
    return _to_icon(pm)


def icon_play() -> QIcon:
    pm, p = _new_pixmap()
    path = QPainterPath()
    path.moveTo(7, 5)
    path.lineTo(19, 12)
    path.lineTo(7, 19)
    path.closeSubpath()
    p.fillPath(path, QColor(Palette.GOLD_BRIGHT))
    p.end()
    return _to_icon(pm)


def icon_pause() -> QIcon:
    pm, p = _new_pixmap()
    p.fillRect(6, 5, 4, 14, QColor(Palette.GOLD_PRIMARY))
    p.fillRect(14, 5, 4, 14, QColor(Palette.GOLD_PRIMARY))
    p.end()
    return _to_icon(pm)


def icon_check() -> QIcon:
    pm, p = _new_pixmap()
    pen = QPen(QColor(Palette.STATUS_DONE), 2.5)
    pen.setCapStyle(Qt.RoundCap)
    pen.setJoinStyle(Qt.RoundJoin)
    p.setPen(pen)
    p.drawLine(5, 12, 10, 17)
    p.drawLine(10, 17, 19, 7)
    p.end()
    return _to_icon(pm)


def icon_block() -> QIcon:
    pm, p = _new_pixmap()
    p.setPen(QPen(QColor(Palette.STATUS_BLOCKED), 2))
    p.setBrush(Qt.NoBrush)
    p.drawEllipse(QPointF(12, 12), 8, 8)
    p.drawLine(6, 12, 18, 12)
    p.end()
    return _to_icon(pm)


def icon_link() -> QIcon:
    pm, p = _new_pixmap()
    pen = QPen(QColor(Palette.GOLD_PRIMARY), 2)
    p.setPen(pen)
    p.setBrush(Qt.NoBrush)
    # Two interlocking U-shapes
    p.drawArc(4, 7, 10, 10, 0, 180 * 16)
    p.drawArc(10, 7, 10, 10, 180 * 16, 180 * 16)
    p.end()
    return _to_icon(pm)


def icon_unlink() -> QIcon:
    pm, p = _new_pixmap()
    pen = QPen(QColor(Palette.STATUS_BLOCKED), 2)
    p.setPen(pen)
    p.setBrush(Qt.NoBrush)
    p.drawArc(4, 7, 8, 10, 0, 180 * 16)
    p.drawArc(12, 7, 8, 10, 180 * 16, 180 * 16)
    p.drawLine(4, 4, 20, 20)
    p.end()
    return _to_icon(pm)


def icon_undo() -> QIcon:
    pm, p = _new_pixmap()
    pen = QPen(QColor(Palette.TEXT_PRIMARY), 2)
    pen.setCapStyle(Qt.RoundCap)
    p.setPen(pen)
    path = QPainterPath()
    path.moveTo(17, 7)
    path.cubicTo(17, 7, 7, 7, 7, 13)
    path.lineTo(11, 13)
    p.drawPath(path)
    # arrow head
    poly = QPolygonF([QPointF(5, 11), QPointF(9, 15), QPointF(9, 7)])
    p.setBrush(QBrush(QColor(Palette.TEXT_PRIMARY)))
    p.drawPolygon(poly)
    p.end()
    return _to_icon(pm)


def icon_redo() -> QIcon:
    pm, p = _new_pixmap()
    pen = QPen(QColor(Palette.TEXT_PRIMARY), 2)
    pen.setCapStyle(Qt.RoundCap)
    p.setPen(pen)
    path = QPainterPath()
    path.moveTo(7, 7)
    path.cubicTo(7, 7, 17, 7, 17, 13)
    path.lineTo(13, 13)
    p.drawPath(path)
    poly = QPolygonF([QPointF(19, 11), QPointF(15, 15), QPointF(15, 7)])
    p.setBrush(QBrush(QColor(Palette.TEXT_PRIMARY)))
    p.drawPolygon(poly)
    p.end()
    return _to_icon(pm)


def icon_graph() -> QIcon:
    pm, p = _new_pixmap()
    p.setPen(QPen(QColor(Palette.GOLD_BRIGHT), 1.5))
    p.setBrush(QBrush(QColor(Palette.GOLD_BRIGHT)))
    # 3 nodes + 2 edges
    p.drawEllipse(QPointF(5, 6), 2.5, 2.5)
    p.drawEllipse(QPointF(5, 18), 2.5, 2.5)
    p.drawEllipse(QPointF(18, 12), 2.5, 2.5)
    p.setPen(QPen(QColor(Palette.GOLD_PRIMARY), 1.5))
    p.drawLine(7, 7, 16, 11)
    p.drawLine(7, 17, 16, 13)
    p.end()
    return _to_icon(pm)


def icon_gantt() -> QIcon:
    pm, p = _new_pixmap()
    p.setPen(Qt.NoPen)
    p.setBrush(QBrush(QColor(Palette.GOLD_PRIMARY)))
    p.drawRect(2, 5, 12, 3)
    p.setBrush(QBrush(QColor(Palette.GOLD_BRIGHT)))
    p.drawRect(6, 10, 14, 3)
    p.setBrush(QBrush(QColor(Palette.GOLD_DEEP)))
    p.drawRect(4, 15, 9, 3)
    p.end()
    return _to_icon(pm)


def icon_kanban() -> QIcon:
    pm, p = _new_pixmap()
    p.setPen(QPen(QColor(Palette.BORDER_NORMAL), 1))
    p.setBrush(QBrush(QColor(Palette.BG_TERTIARY)))
    p.drawRoundedRect(3, 4, 5, 16, 1, 1)
    p.drawRoundedRect(10, 4, 5, 16, 1, 1)
    p.drawRoundedRect(17, 4, 5, 16, 1, 1)
    p.setBrush(QBrush(QColor(Palette.GOLD_PRIMARY)))
    p.setPen(Qt.NoPen)
    p.drawRect(4, 6, 3, 2)
    p.setBrush(QBrush(QColor(Palette.GOLD_BRIGHT)))
    p.drawRect(11, 6, 3, 2)
    p.end()
    return _to_icon(pm)


def icon_stats() -> QIcon:
    pm, p = _new_pixmap()
    p.setPen(QPen(QColor(Palette.TEXT_TERTIARY), 1))
    p.drawLine(4, 4, 4, 20)
    p.drawLine(4, 20, 20, 20)
    p.setPen(Qt.NoPen)
    p.setBrush(QBrush(QColor(Palette.GOLD_PRIMARY)))
    p.drawRect(6, 14, 3, 5)
    p.setBrush(QBrush(QColor(Palette.GOLD_BRIGHT)))
    p.drawRect(11, 9, 3, 10)
    p.setBrush(QBrush(QColor(Palette.GOLD_DEEP)))
    p.drawRect(16, 11, 3, 8)
    p.end()
    return _to_icon(pm)


def icon_timeline() -> QIcon:
    pm, p = _new_pixmap()
    pen = QPen(QColor(Palette.TEXT_TERTIARY), 1.5)
    p.setPen(pen)
    p.drawLine(4, 12, 20, 12)
    for x, color in [(7, Palette.GOLD_BRIGHT), (12, Palette.GOLD_PRIMARY), (17, Palette.GOLD_DEEP)]:
        p.setBrush(QBrush(QColor(color)))
        p.setPen(Qt.NoPen)
        p.drawEllipse(QPointF(x, 12), 2.5, 2.5)
        p.setPen(pen)
    p.end()
    return _to_icon(pm)


def icon_console() -> QIcon:
    pm, p = _new_pixmap()
    p.setPen(QPen(QColor(Palette.GOLD_PRIMARY), 2))
    p.drawLine(4, 6, 9, 11)
    p.drawLine(9, 11, 4, 16)
    p.drawLine(11, 16, 18, 16)
    p.end()
    return _to_icon(pm)


def icon_search() -> QIcon:
    pm, p = _new_pixmap()
    p.setPen(QPen(QColor(Palette.TEXT_SECONDARY), 2))
    p.setBrush(Qt.NoBrush)
    p.drawEllipse(QPointF(10, 10), 5, 5)
    p.drawLine(14, 14, 19, 19)
    p.end()
    return _to_icon(pm)


def icon_save() -> QIcon:
    pm, p = _new_pixmap()
    p.setPen(QPen(QColor(Palette.TEXT_PRIMARY), 1.5))
    p.setBrush(QBrush(QColor(Palette.BG_TERTIARY)))
    p.drawRect(4, 4, 16, 16)
    p.setBrush(QBrush(QColor(Palette.GOLD_PRIMARY)))
    p.drawRect(4, 4, 16, 5)
    p.setBrush(QBrush(QColor(Palette.BG_DEEPEST)))
    p.drawRect(7, 12, 10, 8)
    p.setBrush(QBrush(QColor(Palette.GOLD_PRIMARY)))
    p.drawRect(13, 12, 2, 5)
    p.end()
    return _to_icon(pm)


def icon_open() -> QIcon:
    pm, p = _new_pixmap()
    p.setPen(QPen(QColor(Palette.TEXT_PRIMARY), 1.5))
    p.setBrush(QBrush(QColor(Palette.BG_TERTIARY)))
    path = QPainterPath()
    path.moveTo(4, 7)
    path.lineTo(10, 7)
    path.lineTo(12, 9)
    path.lineTo(20, 9)
    path.lineTo(20, 18)
    path.lineTo(4, 18)
    path.closeSubpath()
    p.drawPath(path)
    p.end()
    return _to_icon(pm)


def icon_settings() -> QIcon:
    pm, p = _new_pixmap()
    p.setPen(QPen(QColor(Palette.TEXT_SECONDARY), 1.5))
    p.setBrush(Qt.NoBrush)
    p.drawEllipse(QPointF(12, 12), 4, 4)
    for ang in range(0, 360, 45):
        import math
        x1 = 12 + 6 * math.cos(math.radians(ang))
        y1 = 12 + 6 * math.sin(math.radians(ang))
        x2 = 12 + 8 * math.cos(math.radians(ang))
        y2 = 12 + 8 * math.sin(math.radians(ang))
        p.drawLine(x1, y1, x2, y2)
    p.end()
    return _to_icon(pm)


def icon_warning() -> QIcon:
    pm, p = _new_pixmap()
    path = QPainterPath()
    path.moveTo(12, 3)
    path.lineTo(22, 20)
    path.lineTo(2, 20)
    path.closeSubpath()
    p.setPen(QPen(QColor(Palette.GOLD_BRIGHT), 1.5))
    p.setBrush(QBrush(QColor(Palette.GOLD_MUTED)))
    p.drawPath(path)
    p.setPen(QPen(QColor(Palette.GOLD_BRIGHT), 2))
    p.drawLine(12, 9, 12, 14)
    p.setBrush(QBrush(QColor(Palette.GOLD_BRIGHT)))
    p.setPen(Qt.NoPen)
    p.drawEllipse(QPointF(12, 17), 1, 1)
    p.end()
    return _to_icon(pm)


def icon_command_palette() -> QIcon:
    pm, p = _new_pixmap()
    p.setPen(QPen(QColor(Palette.GOLD_BRIGHT), 2))
    p.drawRect(3, 5, 18, 14)
    p.drawLine(3, 9, 21, 9)
    p.setPen(QPen(QColor(Palette.GOLD_PRIMARY), 2))
    p.drawLine(6, 7, 8, 7)
    p.end()
    return _to_icon(pm)


# Lookup table
ICONS = {
    "plus": icon_plus,
    "minus": icon_minus,
    "trash": icon_trash,
    "play": icon_play,
    "pause": icon_pause,
    "check": icon_check,
    "block": icon_block,
    "link": icon_link,
    "unlink": icon_unlink,
    "undo": icon_undo,
    "redo": icon_redo,
    "graph": icon_graph,
    "gantt": icon_gantt,
    "kanban": icon_kanban,
    "stats": icon_stats,
    "timeline": icon_timeline,
    "console": icon_console,
    "search": icon_search,
    "save": icon_save,
    "open": icon_open,
    "settings": icon_settings,
    "warning": icon_warning,
    "command": icon_command_palette,
}


def get_icon(name: str) -> QIcon:
    factory = ICONS.get(name)
    if factory is None:
        return QIcon()
    return factory()
