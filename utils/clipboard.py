"""QClipboard sarmalayıcı — sabit 20 sn otomatik temizleme.

Windows'ta kopyalanan değer ayrıca pano geçmişinden (Win+V), bulut panosu
eşitlemesinden ve pano izleyicilerinden hariç tutulur: Keyora panoyu
temizlese bile geçmişte bir kopyası kalmasın.
"""
from __future__ import annotations

import struct
import sys
from typing import Optional

from PySide6.QtCore import QMimeData, QTimer
from PySide6.QtWidgets import QApplication

CLEAR_AFTER_MS = 20_000

# Windows'un tanıdığı kayıtlı pano biçimleri — Qt bunları bu adla kaydeder.
_WIN_MIME = 'application/x-qt-windows-mime;value="{}"'
_DWORD_ZERO = struct.pack("<I", 0)
WINDOWS_PRIVACY_FORMATS: dict[str, bytes] = {
    "ExcludeClipboardContentFromMonitorProcessing": b"\x00",
    "CanIncludeInClipboardHistory": _DWORD_ZERO,
    "CanUploadToCloudClipboard": _DWORD_ZERO,
}

# Son kopyalanan gizli değer — kilit/çıkışta hâlâ panodaysa temizlemek için
_last_copied: Optional[str] = None


def _build_mime(text: str) -> QMimeData:
    """Metni, Windows'ta geçmiş/bulut dışı bırakma işaretleriyle paketler."""
    mime = QMimeData()
    mime.setText(text)
    if sys.platform == "win32":
        for name, value in WINDOWS_PRIVACY_FORMATS.items():
            mime.setData(_WIN_MIME.format(name), value)
    return mime


def copy_to_clipboard(text: str, clear_after_ms: int = CLEAR_AFTER_MS) -> None:
    """Metni panoya yazar, süre dolunca yalnızca aynı içerik duruyorsa temizler."""
    global _last_copied
    clipboard = QApplication.clipboard()
    clipboard.setMimeData(_build_mime(text))
    _last_copied = text

    def _clear_if_unchanged() -> None:
        global _last_copied
        if clipboard.text() == text:
            clipboard.clear()
        if _last_copied == text:
            _last_copied = None

    QTimer.singleShot(clear_after_ms, _clear_if_unchanged)


def clear_pending_secret() -> None:
    """Kilitlenirken/çıkarken: Keyora'nın kopyaladığı değer hâlâ panodaysa siler.

    Kullanıcı arada başka bir şey kopyaladıysa ona dokunmaz.
    """
    global _last_copied
    if _last_copied is None:
        return
    clipboard = QApplication.clipboard()
    if clipboard.text() == _last_copied:
        clipboard.clear()
    _last_copied = None
