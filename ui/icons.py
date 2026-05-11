"""Kodla çizilen vektör ikonlar — tema duyarlı, lru_cache temizlenebilir."""
from __future__ import annotations

import math
from functools import lru_cache
from typing import Optional

from PySide6.QtCore import QPointF, Qt
from PySide6.QtGui import (
    QBrush, QColor, QIcon, QPainter, QPainterPath, QPen, QPixmap,
)

from ui import theme

ICON_SIZE = 18


def _c(token: str) -> str:
    return theme.palette()[token]


def _resolve(color: Optional[str], default_token: str) -> str:
    """Renk açıkça verilmemişse aktif paletten oku."""
    return color if color else theme.palette()[default_token]


def _new_pixmap(size: int) -> QPixmap:
    pm = QPixmap(size, size)
    pm.fill(Qt.transparent)
    return pm


def _painter(pm: QPixmap) -> QPainter:
    p = QPainter(pm)
    p.setRenderHint(QPainter.Antialiasing, True)
    p.setRenderHint(QPainter.TextAntialiasing, True)
    return p


def _stroke(color: str, size: int, ratio: float = 0.10) -> QPen:
    pen = QPen(QColor(color), max(1.0, size * ratio))
    pen.setCapStyle(Qt.RoundCap)
    pen.setJoinStyle(Qt.RoundJoin)
    return pen


def clear_cache() -> None:
    """Tema değişince ikonların palet-bağımlı cache'lerini boşaltır."""
    for fn in (copy_icon, eye_icon, eye_off_icon, clipboard_history_icon,
               pencil_icon, trash_icon, star_icon, plus_icon, lock_icon):
        fn.cache_clear()


# ---------- ikonlar ----------

@lru_cache(maxsize=64)
def copy_icon(size: int = ICON_SIZE, color: Optional[str] = None) -> QIcon:
    color = _resolve(color, "text_muted")
    pm = _new_pixmap(size)
    p = _painter(pm)
    p.setPen(_stroke(color, size, 0.10))
    p.setBrush(Qt.NoBrush)
    s = size
    back = s * 0.50
    radius = s * 0.10
    p.drawRoundedRect(s * 0.18, s * 0.18, back, back, radius, radius)
    p.drawRoundedRect(s * 0.32, s * 0.32, back, back, radius, radius)
    p.end()
    return QIcon(pm)


@lru_cache(maxsize=64)
def eye_icon(size: int = ICON_SIZE, color: Optional[str] = None) -> QIcon:
    color = _resolve(color, "text_muted")
    pm = _new_pixmap(size)
    p = _painter(pm)
    p.setPen(_stroke(color, size, 0.10))
    p.setBrush(Qt.NoBrush)
    s = size
    path = QPainterPath()
    path.moveTo(s * 0.10, s * 0.50)
    path.quadTo(s * 0.50, s * 0.16, s * 0.90, s * 0.50)
    path.quadTo(s * 0.50, s * 0.84, s * 0.10, s * 0.50)
    p.drawPath(path)
    p.setPen(Qt.NoPen)
    p.setBrush(QBrush(QColor(color)))
    p.drawEllipse(QPointF(s * 0.50, s * 0.50), s * 0.14, s * 0.14)
    p.end()
    return QIcon(pm)


@lru_cache(maxsize=64)
def eye_off_icon(size: int = ICON_SIZE, color: Optional[str] = None) -> QIcon:
    color = _resolve(color, "accent")
    pm = _new_pixmap(size)
    p = _painter(pm)
    p.setPen(_stroke(color, size, 0.10))
    p.setBrush(Qt.NoBrush)
    s = size
    path = QPainterPath()
    path.moveTo(s * 0.10, s * 0.50)
    path.quadTo(s * 0.50, s * 0.16, s * 0.90, s * 0.50)
    path.quadTo(s * 0.50, s * 0.84, s * 0.10, s * 0.50)
    p.drawPath(path)
    p.setPen(Qt.NoPen)
    p.setBrush(QBrush(QColor(color)))
    p.drawEllipse(QPointF(s * 0.50, s * 0.50), s * 0.14, s * 0.14)
    p.setPen(_stroke(color, size, 0.12))
    p.drawLine(QPointF(s * 0.15, s * 0.15), QPointF(s * 0.85, s * 0.85))
    p.end()
    return QIcon(pm)


@lru_cache(maxsize=64)
def clipboard_history_icon(size: int = ICON_SIZE, color: Optional[str] = None) -> QIcon:
    color = _resolve(color, "text_muted")
    pm = _new_pixmap(size)
    p = _painter(pm)
    s = size
    p.setPen(_stroke(color, size, 0.09))
    p.setBrush(Qt.NoBrush)
    p.drawRoundedRect(s * 0.22, s * 0.20, s * 0.56, s * 0.70, s * 0.07, s * 0.07)
    p.setBrush(QBrush(QColor(color)))
    p.drawRoundedRect(s * 0.36, s * 0.10, s * 0.28, s * 0.16, s * 0.04, s * 0.04)
    p.setBrush(Qt.NoBrush)
    p.setPen(_stroke(color, size, 0.08))
    for y in (0.42, 0.56, 0.70):
        p.drawLine(QPointF(s * 0.32, s * y), QPointF(s * 0.68, s * y))
    p.end()
    return QIcon(pm)


@lru_cache(maxsize=64)
def pencil_icon(size: int = ICON_SIZE, color: Optional[str] = None) -> QIcon:
    color = _resolve(color, "text_muted")
    pm = _new_pixmap(size)
    p = _painter(pm)
    p.setPen(_stroke(color, size, 0.10))
    p.setBrush(Qt.NoBrush)
    s = size
    p.drawLine(QPointF(s * 0.22, s * 0.78), QPointF(s * 0.74, s * 0.26))
    p.drawLine(QPointF(s * 0.22, s * 0.78), QPointF(s * 0.14, s * 0.86))
    p.setPen(Qt.NoPen)
    p.setBrush(QBrush(QColor(color)))
    path = QPainterPath()
    path.moveTo(s * 0.66, s * 0.18)
    path.lineTo(s * 0.86, s * 0.14)
    path.lineTo(s * 0.82, s * 0.34)
    path.closeSubpath()
    p.drawPath(path)
    p.end()
    return QIcon(pm)


@lru_cache(maxsize=64)
def trash_icon(size: int = ICON_SIZE, color: Optional[str] = None) -> QIcon:
    color = _resolve(color, "danger")
    pm = _new_pixmap(size)
    p = _painter(pm)
    p.setPen(_stroke(color, size, 0.09))
    p.setBrush(Qt.NoBrush)
    s = size
    p.drawLine(QPointF(s * 0.40, s * 0.20), QPointF(s * 0.60, s * 0.20))
    p.drawLine(QPointF(s * 0.40, s * 0.20), QPointF(s * 0.40, s * 0.30))
    p.drawLine(QPointF(s * 0.60, s * 0.20), QPointF(s * 0.60, s * 0.30))
    p.drawLine(QPointF(s * 0.18, s * 0.30), QPointF(s * 0.82, s * 0.30))
    p.drawLine(QPointF(s * 0.26, s * 0.32), QPointF(s * 0.32, s * 0.86))
    p.drawLine(QPointF(s * 0.74, s * 0.32), QPointF(s * 0.68, s * 0.86))
    p.drawLine(QPointF(s * 0.32, s * 0.86), QPointF(s * 0.68, s * 0.86))
    p.drawLine(QPointF(s * 0.42, s * 0.40), QPointF(s * 0.42, s * 0.78))
    p.drawLine(QPointF(s * 0.58, s * 0.40), QPointF(s * 0.58, s * 0.78))
    p.end()
    return QIcon(pm)


@lru_cache(maxsize=64)
def star_icon(
    size: int = ICON_SIZE,
    filled: bool = False,
    color: Optional[str] = None,
) -> QIcon:
    color = _resolve(color, "accent")
    pm = _new_pixmap(size)
    p = _painter(pm)
    s = size
    cx, cy = s * 0.50, s * 0.52
    r_out = s * 0.42
    r_in = r_out * 0.42
    points: list[QPointF] = []
    for i in range(10):
        angle = -math.pi / 2 + i * math.pi / 5
        r = r_out if i % 2 == 0 else r_in
        points.append(QPointF(cx + r * math.cos(angle), cy + r * math.sin(angle)))
    path = QPainterPath()
    path.moveTo(points[0])
    for pt in points[1:]:
        path.lineTo(pt)
    path.closeSubpath()
    if filled:
        p.setPen(Qt.NoPen)
        p.setBrush(QBrush(QColor(color)))
    else:
        p.setPen(_stroke(color, size, 0.10))
        p.setBrush(Qt.NoBrush)
    p.drawPath(path)
    p.end()
    return QIcon(pm)


@lru_cache(maxsize=64)
def plus_icon(size: int = ICON_SIZE, color: Optional[str] = None) -> QIcon:
    color = _resolve(color, "text_on_accent")
    pm = _new_pixmap(size)
    p = _painter(pm)
    p.setPen(_stroke(color, size, 0.14))
    s = size
    p.drawLine(QPointF(s * 0.50, s * 0.20), QPointF(s * 0.50, s * 0.80))
    p.drawLine(QPointF(s * 0.20, s * 0.50), QPointF(s * 0.80, s * 0.50))
    p.end()
    return QIcon(pm)


@lru_cache(maxsize=64)
def lock_icon(size: int = ICON_SIZE, color: Optional[str] = None) -> QIcon:
    color = _resolve(color, "text_on_accent")
    pm = _new_pixmap(size)
    p = _painter(pm)
    p.setPen(_stroke(color, size, 0.10))
    p.setBrush(Qt.NoBrush)
    s = size
    path = QPainterPath()
    path.moveTo(s * 0.30, s * 0.50)
    path.lineTo(s * 0.30, s * 0.36)
    path.arcTo(s * 0.30, s * 0.22, s * 0.40, s * 0.28, 180, -180)
    path.lineTo(s * 0.70, s * 0.50)
    p.drawPath(path)
    p.setBrush(QBrush(QColor(color)))
    p.setPen(Qt.NoPen)
    p.drawRoundedRect(s * 0.22, s * 0.50, s * 0.56, s * 0.34, s * 0.05, s * 0.05)
    p.end()
    return QIcon(pm)
