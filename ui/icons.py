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
    for fn in (copy_icon, eye_icon, eye_off_icon, history_icon, more_icon,
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
def history_icon(size: int = ICON_SIZE, color: Optional[str] = None) -> QIcon:
    """Geriye dönen oklu saat — 'şifre geçmişi'."""
    color = _resolve(color, "text_muted")
    pm = _new_pixmap(size)
    p = _painter(pm)
    s = size
    p.setPen(_stroke(color, size, 0.09))
    p.setBrush(Qt.NoBrush)
    # Saat kadranı: sol üstte ok için boşluk bırakan yay
    p.drawArc(int(s * 0.16), int(s * 0.16), int(s * 0.68), int(s * 0.68), 140 * 16, -300 * 16)
    # Yayın ucundaki ok başı (saat yönünün tersine)
    arrow = QPainterPath()
    arrow.moveTo(s * 0.10, s * 0.22)
    arrow.lineTo(s * 0.21, s * 0.36)
    arrow.lineTo(s * 0.36, s * 0.27)
    p.drawPath(arrow)
    # Akrep ve yelkovan
    p.drawLine(QPointF(s * 0.50, s * 0.50), QPointF(s * 0.50, s * 0.32))
    p.drawLine(QPointF(s * 0.50, s * 0.50), QPointF(s * 0.63, s * 0.60))
    p.end()
    return QIcon(pm)


@lru_cache(maxsize=64)
def pencil_icon(size: int = ICON_SIZE, color: Optional[str] = None) -> QIcon:
    """Gövdesi, ucu ve silgisi olan eğik kalem — 'düzenle'."""
    color = _resolve(color, "text_muted")
    pm = _new_pixmap(size)
    p = _painter(pm)
    s = size
    p.translate(s * 0.5, s * 0.5)
    p.rotate(45)
    pen = _stroke(color, size, 0.08)
    p.setPen(pen)
    p.setBrush(Qt.NoBrush)
    w, half = s * 0.22, s * 0.11
    # Gövde (dikdörtgen) ve silgi ayrımı
    p.drawRect(-half, -s * 0.40, w, s * 0.58)
    p.drawLine(QPointF(-half, -s * 0.27), QPointF(half, -s * 0.27))
    # Uç (üçgen) ve grafit ucu
    tip = QPainterPath()
    tip.moveTo(-half, s * 0.18)
    tip.lineTo(0, s * 0.40)
    tip.lineTo(half, s * 0.18)
    p.drawPath(tip)
    p.setPen(Qt.NoPen)
    p.setBrush(QBrush(QColor(color)))
    lead = QPainterPath()
    lead.moveTo(-s * 0.04, s * 0.31)
    lead.lineTo(0, s * 0.40)
    lead.lineTo(s * 0.04, s * 0.31)
    lead.closeSubpath()
    p.drawPath(lead)
    p.end()
    return QIcon(pm)


@lru_cache(maxsize=64)
def more_icon(size: int = ICON_SIZE, color: Optional[str] = None) -> QIcon:
    """Yatay üç nokta — 'diğer işlemler' menüsü."""
    color = _resolve(color, "text_muted")
    pm = _new_pixmap(size)
    p = _painter(pm)
    s = size
    p.setPen(Qt.NoPen)
    p.setBrush(QBrush(QColor(color)))
    r = s * 0.085
    for x in (0.24, 0.50, 0.76):
        p.drawEllipse(QPointF(s * x, s * 0.50), r, r)
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
