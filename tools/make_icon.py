"""Keyora ikon üretici — resources/keyora.ico oluşturur.

Kullanım:
    venv\\Scripts\\python.exe tools\\make_icon.py
"""
from __future__ import annotations

import struct
import sys
from io import BytesIO
from pathlib import Path

from PySide6.QtCore import Qt, QRect
from PySide6.QtGui import QColor, QFont, QImage, QPainter, QPen, QBrush
from PySide6.QtWidgets import QApplication

ROOT = Path(__file__).resolve().parent.parent
OUT_DIR = ROOT / "resources"
OUT_ICO = OUT_DIR / "keyora.ico"
OUT_PNG = OUT_DIR / "keyora.png"

ICON_SIZES = [16, 24, 32, 48, 64, 128, 256]
BG = QColor("#1A1A2E")
RING = QColor("#0F3460")
ACCENT = QColor("#E94560")
TEXT = QColor("#EAEAEA")


def _render(size: int) -> QImage:
    """Yuvarlatılmış dark mode 'K' ikonu çizer."""
    img = QImage(size, size, QImage.Format_ARGB32)
    img.fill(Qt.transparent)

    painter = QPainter(img)
    painter.setRenderHint(QPainter.Antialiasing)
    painter.setRenderHint(QPainter.TextAntialiasing)

    # Yuvarlak köşeli dolu arka plan
    radius = size * 0.22
    painter.setPen(Qt.NoPen)
    painter.setBrush(QBrush(BG))
    painter.drawRoundedRect(0, 0, size, size, radius, radius)

    # Aksan ince kenarlık
    pen_w = max(1.0, size * 0.04)
    painter.setBrush(Qt.NoBrush)
    painter.setPen(QPen(ACCENT, pen_w))
    inset = pen_w / 2
    painter.drawRoundedRect(
        inset, inset, size - 2 * inset, size - 2 * inset,
        radius - inset, radius - inset,
    )

    # 'K' harfi
    font = QFont("Segoe UI", -1)
    font.setBold(True)
    font.setPixelSize(int(size * 0.62))
    painter.setFont(font)
    painter.setPen(QPen(TEXT))
    painter.drawText(QRect(0, 0, size, size), Qt.AlignCenter, "K")

    painter.end()
    return img


def _png_bytes(img: QImage) -> bytes:
    from PySide6.QtCore import QBuffer, QByteArray
    ba = QByteArray()
    buf = QBuffer(ba)
    buf.open(QBuffer.WriteOnly)
    img.save(buf, "PNG")
    buf.close()
    return bytes(ba)


def _build_ico(images: list[QImage]) -> bytes:
    """Çoklu çözünürlüklü .ico dosyasını elle birleştirir (PNG payload).

    Windows ICO formatı: ICONDIR + ICONDIRENTRY[n] + image payloads (PNG
    256+ için zorunlu, küçükler için de modern Windows tarafından destekleniyor).
    """
    count = len(images)
    header = struct.pack("<HHH", 0, 1, count)
    entries = bytearray()
    payloads = bytearray()
    offset = 6 + count * 16  # header + entries

    for img in images:
        png = _png_bytes(img)
        w = img.width() if img.width() < 256 else 0
        h = img.height() if img.height() < 256 else 0
        entry = struct.pack(
            "<BBBBHHII",
            w, h,    # width, height (0 == 256)
            0,       # color palette
            0,       # reserved
            1,       # color planes
            32,      # bits per pixel
            len(png),
            offset,
        )
        entries += entry
        payloads += png
        offset += len(png)

    return bytes(header) + bytes(entries) + bytes(payloads)


def main() -> int:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    app = QApplication.instance() or QApplication(sys.argv)

    images = [_render(s) for s in ICON_SIZES]

    OUT_ICO.write_bytes(_build_ico(images))
    images[-1].save(str(OUT_PNG), "PNG")

    print(f"OK: {OUT_ICO} ({OUT_ICO.stat().st_size:,} byte)")
    print(f"OK: {OUT_PNG} ({OUT_PNG.stat().st_size:,} byte)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
