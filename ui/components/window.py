"""Bağımsız üst düzey pencere ayarları."""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QWidget


def as_minimizable_window(widget: QWidget) -> None:
    """Diyaloğu küçültülebilir, görev çubuğunda görünen bir pencere yapar.

    Qt, Windows'ta diyaloglara varsayılan olarak yalnızca başlık ve kapat
    düğmesi verir. Giriş/kurulum gibi uygulamanın kendisi olan pencereler
    küçültülebilmeli ve görev çubuğundan geri açılabilmelidir. Büyütme
    düğmesi bilerek yok: bu boyutta bir formu büyütmek anlamsız.
    """
    widget.setWindowFlags(
        Qt.Window
        | Qt.WindowTitleHint
        | Qt.WindowSystemMenuHint
        | Qt.WindowMinimizeButtonHint
        | Qt.WindowCloseButtonHint
    )
