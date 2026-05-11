"""İlk kurulum — master password belirleme ekranı."""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,
    QPushButton, QMessageBox, QCheckBox,
)

from core.vault import Vault

MIN_MASTER_LENGTH = 8


class SetupDialog(QDialog):
    """Vault hiç kurulmamışken açılır."""

    def __init__(self, vault: Vault, parent=None) -> None:
        super().__init__(parent)
        self.vault = vault
        self.setWindowTitle("Keyora — İlk Kurulum")
        self.setMinimumWidth(420)
        self._build_ui()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(12)

        title = QLabel("Keyora'ya Hoş Geldin")
        title.setProperty("role", "title")
        subtitle = QLabel(
            "Master password vault'unun tek anahtarıdır. Unutursan veriler "
            "kurtarılamaz — güvenli bir yerde sakla."
        )
        subtitle.setProperty("role", "muted")
        subtitle.setWordWrap(True)

        self.pw_edit = QLineEdit()
        self.pw_edit.setEchoMode(QLineEdit.Password)
        self.pw_edit.setPlaceholderText("Master password")

        self.pw_confirm = QLineEdit()
        self.pw_confirm.setEchoMode(QLineEdit.Password)
        self.pw_confirm.setPlaceholderText("Tekrar gir")

        self.show_pw = QCheckBox("Şifreleri göster")
        self.show_pw.toggled.connect(self._toggle_echo)

        self.create_btn = QPushButton("Vault'u oluştur")
        self.create_btn.setProperty("role", "primary")
        self.create_btn.setDefault(True)
        self.create_btn.clicked.connect(self._on_create)

        self.cancel_btn = QPushButton("İptal")
        self.cancel_btn.clicked.connect(self.reject)

        btn_row = QHBoxLayout()
        btn_row.addStretch()
        btn_row.addWidget(self.cancel_btn)
        btn_row.addWidget(self.create_btn)

        layout.addWidget(title)
        layout.addWidget(subtitle)
        layout.addSpacing(8)
        layout.addWidget(QLabel("Master password"))
        layout.addWidget(self.pw_edit)
        layout.addWidget(QLabel("Tekrar"))
        layout.addWidget(self.pw_confirm)
        layout.addWidget(self.show_pw)
        layout.addSpacing(8)
        layout.addLayout(btn_row)

    def _toggle_echo(self, checked: bool) -> None:
        mode = QLineEdit.Normal if checked else QLineEdit.Password
        self.pw_edit.setEchoMode(mode)
        self.pw_confirm.setEchoMode(mode)

    def _on_create(self) -> None:
        pw = self.pw_edit.text()
        confirm = self.pw_confirm.text()

        if len(pw) < MIN_MASTER_LENGTH:
            QMessageBox.warning(self, "Geçersiz", f"En az {MIN_MASTER_LENGTH} karakter olmalı.")
            return
        if pw != confirm:
            QMessageBox.warning(self, "Eşleşmiyor", "Şifreler aynı değil.")
            return

        try:
            self.vault.initialize(pw)
        except Exception as exc:
            QMessageBox.critical(self, "Hata", f"Kurulum başarısız: {exc}")
            return

        # Hassas girişleri hemen temizle
        self.pw_edit.clear()
        self.pw_confirm.clear()
        self.accept()
