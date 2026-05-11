"""Ayarlar — auto-lock süresi + master password değiştirme."""
from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QGridLayout, QLabel, QLineEdit,
    QPushButton, QSpinBox, QFrame, QMessageBox, QCheckBox, QComboBox,
)

from core.vault import Vault, InvalidMasterPassword
from ui import theme

MIN_MASTER_LENGTH = 8


class SettingsDialog(QDialog):
    """Ayarlar paneli — değişiklik olduysa `settings_changed` yayar."""

    settings_changed = Signal()
    theme_changed = Signal(str)  # yeni tema adı (dark / light)

    def __init__(self, vault: Vault, parent=None) -> None:
        super().__init__(parent)
        self.vault = vault
        self.setWindowTitle("Ayarlar")
        self.setMinimumWidth(480)
        self._build_ui()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(14)

        layout.addWidget(self._build_theme_panel())
        layout.addWidget(self._build_auto_lock_panel())
        layout.addWidget(self._build_master_password_panel())

        close_btn = QPushButton("Kapat")
        close_btn.clicked.connect(self.accept)
        row = QHBoxLayout()
        row.addStretch()
        row.addWidget(close_btn)
        layout.addLayout(row)

    # ---------- theme ----------

    def _build_theme_panel(self) -> QFrame:
        panel = QFrame()
        panel.setObjectName("Panel")
        grid = QGridLayout(panel)
        grid.setContentsMargins(14, 14, 14, 14)

        title = QLabel("Tema")
        title.setProperty("role", "title")
        sub = QLabel("Arayüzün renk tonu — pastel koyu veya pastel açık.")
        sub.setProperty("role", "muted")
        sub.setWordWrap(True)

        self.theme_combo = QComboBox()
        current = self.vault.get_theme()
        for name, label in theme.available_themes():
            self.theme_combo.addItem(label, name)
            if name == current:
                self.theme_combo.setCurrentIndex(self.theme_combo.count() - 1)
        self.theme_combo.currentIndexChanged.connect(self._on_theme_picked)

        grid.addWidget(title, 0, 0, 1, 2)
        grid.addWidget(sub, 1, 0, 1, 2)
        grid.addWidget(QLabel("Görünüm"), 2, 0)
        grid.addWidget(self.theme_combo, 2, 1)
        return panel

    def _on_theme_picked(self, _idx: int) -> None:
        name = self.theme_combo.currentData()
        if not name:
            return
        self.vault.set_theme(name)
        self.theme_changed.emit(name)

    # ---------- auto-lock ----------

    def _build_auto_lock_panel(self) -> QFrame:
        panel = QFrame()
        panel.setObjectName("Panel")
        grid = QGridLayout(panel)
        grid.setContentsMargins(14, 14, 14, 14)

        title = QLabel("Otomatik Kilit")
        title.setProperty("role", "title")
        sub = QLabel("Kullanıcı boştayken vault şu kadar dakika sonra kilitlenir.")
        sub.setProperty("role", "muted")
        sub.setWordWrap(True)

        self.lock_spin = QSpinBox()
        self.lock_spin.setRange(1, 120)
        self.lock_spin.setSuffix(" dk")
        self.lock_spin.setValue(self.vault.get_auto_lock_minutes())

        save_btn = QPushButton("Kaydet")
        save_btn.setProperty("role", "primary")
        save_btn.clicked.connect(self._on_save_auto_lock)

        grid.addWidget(title, 0, 0, 1, 2)
        grid.addWidget(sub, 1, 0, 1, 2)
        grid.addWidget(QLabel("Süre"), 2, 0)
        grid.addWidget(self.lock_spin, 2, 1)
        grid.addWidget(save_btn, 3, 1, alignment=Qt.AlignRight)
        return panel

    def _on_save_auto_lock(self) -> None:
        try:
            self.vault.set_auto_lock_minutes(self.lock_spin.value())
        except ValueError as exc:
            QMessageBox.warning(self, "Geçersiz", str(exc))
            return
        self.settings_changed.emit()
        QMessageBox.information(self, "Kaydedildi", "Otomatik kilit güncellendi.")

    # ---------- master password ----------

    def _build_master_password_panel(self) -> QFrame:
        panel = QFrame()
        panel.setObjectName("Panel")
        grid = QGridLayout(panel)
        grid.setContentsMargins(14, 14, 14, 14)

        title = QLabel("Master Password")
        title.setProperty("role", "title")
        sub = QLabel(
            "Tüm kayıtlar yeni şifreyle yeniden şifrelenir. İşlem atomiktir; "
            "hata olursa eski şifre geçerli kalır."
        )
        sub.setProperty("role", "muted")
        sub.setWordWrap(True)

        self.old_pw = QLineEdit()
        self.old_pw.setEchoMode(QLineEdit.Password)
        self.new_pw = QLineEdit()
        self.new_pw.setEchoMode(QLineEdit.Password)
        self.new_pw_confirm = QLineEdit()
        self.new_pw_confirm.setEchoMode(QLineEdit.Password)

        self.show_chk = QCheckBox("Şifreleri göster")
        self.show_chk.toggled.connect(self._toggle_echo)

        change_btn = QPushButton("Şifreyi Değiştir")
        change_btn.setProperty("role", "primary")
        change_btn.clicked.connect(self._on_change_password)

        grid.addWidget(title, 0, 0, 1, 2)
        grid.addWidget(sub, 1, 0, 1, 2)
        grid.addWidget(QLabel("Eski şifre"), 2, 0)
        grid.addWidget(self.old_pw, 2, 1)
        grid.addWidget(QLabel("Yeni şifre"), 3, 0)
        grid.addWidget(self.new_pw, 3, 1)
        grid.addWidget(QLabel("Tekrar"), 4, 0)
        grid.addWidget(self.new_pw_confirm, 4, 1)
        grid.addWidget(self.show_chk, 5, 1)
        grid.addWidget(change_btn, 6, 1, alignment=Qt.AlignRight)
        return panel

    def _toggle_echo(self, checked: bool) -> None:
        mode = QLineEdit.Normal if checked else QLineEdit.Password
        for w in (self.old_pw, self.new_pw, self.new_pw_confirm):
            w.setEchoMode(mode)

    def _on_change_password(self) -> None:
        old = self.old_pw.text()
        new = self.new_pw.text()
        confirm = self.new_pw_confirm.text()

        if len(new) < MIN_MASTER_LENGTH:
            QMessageBox.warning(self, "Geçersiz", f"Yeni şifre en az {MIN_MASTER_LENGTH} karakter olmalı.")
            return
        if new != confirm:
            QMessageBox.warning(self, "Eşleşmiyor", "Yeni şifreler aynı değil.")
            return
        if new == old:
            QMessageBox.warning(self, "Geçersiz", "Yeni şifre eski şifreyle aynı olamaz.")
            return

        try:
            self.vault.change_master_password(old, new)
        except InvalidMasterPassword:
            QMessageBox.warning(self, "Hatalı", "Eski master password yanlış.")
            return
        except Exception as exc:
            QMessageBox.critical(self, "Hata", f"Değişiklik başarısız: {exc}")
            return

        self.old_pw.clear()
        self.new_pw.clear()
        self.new_pw_confirm.clear()
        QMessageBox.information(self, "Tamam", "Master password güncellendi.")
