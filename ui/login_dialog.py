"""Master password giriş ekranı."""
from __future__ import annotations

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,
    QPushButton, QCheckBox,
)

from core.vault import (
    Vault, InvalidMasterPassword, LoginThrottled,
    UnsupportedVaultVersion, VaultCorrupted,
)


class LoginDialog(QDialog):
    """Var olan vault için master password ister."""

    def __init__(self, vault: Vault, parent=None) -> None:
        super().__init__(parent)
        self.vault = vault
        self.setWindowTitle("Keyora — Giriş")
        self.setMinimumWidth(380)
        self._build_ui()

        # Yanlış denemeler sonrası bekleme geri sayımı (süre core'da hesaplanır)
        self._throttle_timer = QTimer(self)
        self._throttle_timer.setInterval(1000)
        self._throttle_timer.timeout.connect(self._update_throttle)
        self._update_throttle()

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
        self.error_label.setWordWrap(True)
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

    def _update_throttle(self) -> None:
        """Bekleme süresi varsa girişi kilitler ve geri sayımı gösterir."""
        remaining = self.vault.lockout_remaining()
        locked = remaining > 0
        self.unlock_btn.setEnabled(not locked)
        self.pw_edit.setEnabled(not locked)
        if locked:
            self.error_label.setText(
                f"Çok fazla hatalı deneme. {remaining} sn sonra tekrar deneyin."
            )
            if not self._throttle_timer.isActive():
                self._throttle_timer.start()
        elif self._throttle_timer.isActive():
            self._throttle_timer.stop()
            self.error_label.setText(" ")
            self.pw_edit.setFocus()

    def _on_unlock(self) -> None:
        if not self.unlock_btn.isEnabled():
            return
        pw = self.pw_edit.text()
        if not pw:
            self.error_label.setText("Şifre boş olamaz.")
            return

        try:
            self.vault.unlock(pw)
        except InvalidMasterPassword:
            self.pw_edit.clear()
            self.error_label.setText("Hatalı şifre.")
            self._update_throttle()
            return
        except LoginThrottled:
            self.pw_edit.clear()
            self._update_throttle()
            return
        except (UnsupportedVaultVersion, VaultCorrupted) as exc:
            self.pw_edit.clear()
            self.error_label.setText(str(exc))
            return
        except Exception as exc:
            self.pw_edit.clear()
            self.error_label.setText(f"Hata: {exc}")
            return

        self.pw_edit.clear()
        self.accept()
