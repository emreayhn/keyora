"""Master password giriş ekranı."""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,
    QPushButton, QCheckBox,
)

from core.vault import Vault, InvalidMasterPassword

MAX_ATTEMPTS = 5


class LoginDialog(QDialog):
    """Var olan vault için master password ister."""

    def __init__(self, vault: Vault, parent=None) -> None:
        super().__init__(parent)
        self.vault = vault
        self.attempts = 0
        self.setWindowTitle("Keyora — Giriş")
        self.setMinimumWidth(380)
        self._build_ui()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(12)

        title = QLabel("Keyora")
        title.setProperty("role", "title")
        subtitle = QLabel("Master password ile vault'u aç")
        subtitle.setProperty("role", "muted")

        self.pw_edit = QLineEdit()
        self.pw_edit.setEchoMode(QLineEdit.Password)
        self.pw_edit.setPlaceholderText("Master password")
        self.pw_edit.returnPressed.connect(self._on_unlock)

        self.show_pw = QCheckBox("Şifreyi göster")
        self.show_pw.toggled.connect(self._toggle_echo)

        self.error_label = QLabel(" ")
        self.error_label.setStyleSheet("color: #F44336;")

        self.unlock_btn = QPushButton("Kilidi Aç")
        self.unlock_btn.setProperty("role", "primary")
        self.unlock_btn.setDefault(True)
        self.unlock_btn.clicked.connect(self._on_unlock)

        self.cancel_btn = QPushButton("Çıkış")
        self.cancel_btn.clicked.connect(self.reject)

        btns = QHBoxLayout()
        btns.addStretch()
        btns.addWidget(self.cancel_btn)
        btns.addWidget(self.unlock_btn)

        layout.addWidget(title)
        layout.addWidget(subtitle)
        layout.addSpacing(8)
        layout.addWidget(self.pw_edit)
        layout.addWidget(self.show_pw)
        layout.addWidget(self.error_label)
        layout.addLayout(btns)

    def _toggle_echo(self, checked: bool) -> None:
        self.pw_edit.setEchoMode(QLineEdit.Normal if checked else QLineEdit.Password)

    def _on_unlock(self) -> None:
        pw = self.pw_edit.text()
        if not pw:
            self.error_label.setText("Şifre boş olamaz.")
            return

        try:
            self.vault.unlock(pw)
        except InvalidMasterPassword:
            self.attempts += 1
            remaining = MAX_ATTEMPTS - self.attempts
            self.pw_edit.clear()
            if remaining <= 0:
                self.error_label.setText("Çok fazla hatalı deneme. Çıkılıyor.")
                self.reject()
                return
            self.error_label.setText(f"Hatalı şifre. Kalan deneme: {remaining}")
            return
        except Exception as exc:
            self.error_label.setText(f"Hata: {exc}")
            return

        self.pw_edit.clear()
        self.accept()
