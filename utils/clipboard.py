"""QClipboard sarmalayıcı — sabit 20 sn otomatik temizleme."""
from __future__ import annotations

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication

CLEAR_AFTER_MS = 20_000


def copy_to_clipboard(text: str, clear_after_ms: int = CLEAR_AFTER_MS) -> None:
    """Metni panoya yazar, süre dolunca yalnızca aynı içerik duruyorsa temizler."""
    clipboard = QApplication.clipboard()
    clipboard.setText(text)

    def _clear_if_unchanged() -> None:
        if clipboard.text() == text:
            clipboard.clear()

    QTimer.singleShot(clear_after_ms, _clear_if_unchanged)
