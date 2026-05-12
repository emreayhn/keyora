"""Hakkında — versiyon, lisans ve kısa güvenlik notu."""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
)

from core.database import default_db_path

APP_VERSION = "1.0.0"


class AboutDialog(QDialog):
    """Kısa uygulama bilgisi."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Keyora Hakkında")
        self.setMinimumWidth(420)
        self._build_ui()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(8)

        title = QLabel("Keyora")
        title.setProperty("role", "title")

        version = QLabel(f"Sürüm {APP_VERSION}")
        version.setProperty("role", "muted")

        desc = QLabel(
            "Yerel, çevrimdışı çalışan masaüstü parola yöneticisi. "
            "Şifreler Argon2id ile türetilmiş anahtar kullanılarak Fernet "
            "(AES-128-CBC + HMAC-SHA256) ile şifrelenir ve yalnızca senin "
            "cihazında saklanır."
        )
        desc.setWordWrap(True)

        tech = QLabel(
            "<b>Teknoloji:</b> Python · PySide6 · SQLite · cryptography · argon2-cffi"
        )
        tech.setTextFormat(Qt.RichText)
        tech.setWordWrap(True)

        location = QLabel(
            f"<b>Vault konumu:</b><br><span style='font-family: Consolas, monospace;'>"
            f"{default_db_path()}</span>"
        )
        location.setTextFormat(Qt.RichText)
        location.setWordWrap(True)
        location.setTextInteractionFlags(Qt.TextSelectableByMouse)

        warn = QLabel(
            "<b>Önemli:</b> Master password unutulursa hiçbir veri kurtarılamaz. "
            "Veri internet üzerinden hiçbir yere gönderilmez."
        )
        warn.setTextFormat(Qt.RichText)
        warn.setWordWrap(True)
        warn.setStyleSheet("color: #FF9800;")

        close_btn = QPushButton("Kapat")
        close_btn.setProperty("role", "primary")
        close_btn.clicked.connect(self.accept)
        row = QHBoxLayout()
        row.addStretch()
        row.addWidget(close_btn)

        layout.addWidget(title)
        layout.addWidget(version)
        layout.addSpacing(8)
        layout.addWidget(desc)
        layout.addSpacing(4)
        layout.addWidget(tech)
        layout.addSpacing(4)
        layout.addWidget(location)
        layout.addSpacing(8)
        layout.addWidget(warn)
        layout.addStretch()
        layout.addLayout(row)
