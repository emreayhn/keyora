"""Kayıt ekleme/düzenleme dialog'u — generator entegrasyonlu."""
from __future__ import annotations

from typing import Optional

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QGridLayout, QLabel, QLineEdit,
    QTextEdit, QComboBox, QPushButton, QCheckBox, QSpinBox, QFrame,
    QMessageBox,
)

from core.vault import Vault, VaultEntry
from utils.password_gen import (
    PasswordPolicy, generate_password, estimate_strength,
    DEFAULT_LENGTH, MIN_LENGTH,
)


class EntryDialog(QDialog):
    """app_name / username / password / notes / kategori girer/düzenler."""

    def __init__(
        self,
        vault: Vault,
        *,
        entry: Optional[VaultEntry] = None,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self.vault = vault
        self.entry = entry
        self.setWindowTitle("Kayıt Düzenle" if entry else "Yeni Kayıt")
        self.setMinimumWidth(520)
        self._build_ui()
        if entry:
            self._load_entry(entry)

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(10)

        grid = QGridLayout()
        grid.setColumnStretch(1, 1)
        grid.setVerticalSpacing(10)

        self.app_edit = QLineEdit()
        self.app_edit.setPlaceholderText("ör. GitHub")

        self.user_edit = QLineEdit()
        self.user_edit.setPlaceholderText("kullanıcı adı veya e-posta")

        self.pw_edit = QLineEdit()
        self.pw_edit.setEchoMode(QLineEdit.Password)

        self.toggle_btn = QPushButton("Göster")
        self.toggle_btn.setProperty("role", "ghost")
        self.toggle_btn.setCheckable(True)
        self.toggle_btn.toggled.connect(self._toggle_pw)

        self.gen_btn = QPushButton("Üret")
        self.gen_btn.setProperty("role", "primary")
        self.gen_btn.clicked.connect(self._on_generate)

        pw_row = QHBoxLayout()
        pw_row.addWidget(self.pw_edit, 1)
        pw_row.addWidget(self.toggle_btn)
        pw_row.addWidget(self.gen_btn)

        self.strength_label = QLabel(" ")
        self.strength_label.setProperty("role", "muted")
        self.pw_edit.textChanged.connect(self._update_strength)

        self.category_combo = QComboBox()
        self.category_combo.addItem("— Yok —", None)
        for cat in self.vault.db.list_categories():
            self.category_combo.addItem(cat["name"], cat["id"])

        self.notes_edit = QTextEdit()
        self.notes_edit.setFixedHeight(80)

        self.favorite_chk = QCheckBox("Favori")

        grid.addWidget(QLabel("Uygulama"), 0, 0)
        grid.addWidget(self.app_edit, 0, 1)
        grid.addWidget(QLabel("Kullanıcı adı"), 1, 0)
        grid.addWidget(self.user_edit, 1, 1)
        grid.addWidget(QLabel("Şifre"), 2, 0)
        grid.addLayout(pw_row, 2, 1)
        grid.addWidget(self.strength_label, 3, 1)
        grid.addWidget(QLabel("Kategori"), 4, 0)
        grid.addWidget(self.category_combo, 4, 1)
        grid.addWidget(QLabel("Notlar"), 5, 0)
        grid.addWidget(self.notes_edit, 5, 1)
        grid.addWidget(self.favorite_chk, 6, 1)

        layout.addLayout(grid)

        # Generator paneli
        panel = QFrame()
        panel.setObjectName("Panel")
        gen_layout = QGridLayout(panel)
        gen_layout.setContentsMargins(12, 12, 12, 12)

        self.length_spin = QSpinBox()
        self.length_spin.setRange(MIN_LENGTH, 64)
        self.length_spin.setValue(DEFAULT_LENGTH)

        self.upper_chk = QCheckBox("A-Z")
        self.upper_chk.setChecked(True)
        self.lower_chk = QCheckBox("a-z")
        self.lower_chk.setChecked(True)
        self.digits_chk = QCheckBox("0-9")
        self.digits_chk.setChecked(True)
        self.special_chk = QCheckBox("!@#$")
        self.special_chk.setChecked(True)

        gen_layout.addWidget(QLabel("Generator"), 0, 0, 1, 4)
        gen_layout.addWidget(QLabel("Uzunluk"), 1, 0)
        gen_layout.addWidget(self.length_spin, 1, 1)
        gen_layout.addWidget(self.upper_chk, 1, 2)
        gen_layout.addWidget(self.lower_chk, 1, 3)
        gen_layout.addWidget(self.digits_chk, 2, 2)
        gen_layout.addWidget(self.special_chk, 2, 3)

        layout.addWidget(panel)

        # Buton satırı
        self.save_btn = QPushButton("Kaydet")
        self.save_btn.setProperty("role", "primary")
        self.save_btn.setDefault(True)
        self.save_btn.clicked.connect(self._on_save)
        self.cancel_btn = QPushButton("İptal")
        self.cancel_btn.clicked.connect(self.reject)

        btns = QHBoxLayout()
        btns.addStretch()
        btns.addWidget(self.cancel_btn)
        btns.addWidget(self.save_btn)
        layout.addLayout(btns)

    def _toggle_pw(self, checked: bool) -> None:
        self.pw_edit.setEchoMode(QLineEdit.Normal if checked else QLineEdit.Password)
        self.toggle_btn.setText("Gizle" if checked else "Göster")

    def _update_strength(self, text: str) -> None:
        if not text:
            self.strength_label.setText(" ")
            return
        self.strength_label.setText(f"Güç: {estimate_strength(text)}")

    def _on_generate(self) -> None:
        policy = PasswordPolicy(
            length=self.length_spin.value(),
            use_upper=self.upper_chk.isChecked(),
            use_lower=self.lower_chk.isChecked(),
            use_digits=self.digits_chk.isChecked(),
            use_special=self.special_chk.isChecked(),
        )
        try:
            self.pw_edit.setText(generate_password(policy))
        except ValueError as exc:
            QMessageBox.warning(self, "Geçersiz", str(exc))

    def _load_entry(self, entry: VaultEntry) -> None:
        self.app_edit.setText(entry.app_name)
        self.user_edit.setText(entry.username)
        self.pw_edit.setText(entry.password)
        self.notes_edit.setPlainText(entry.notes or "")
        self.favorite_chk.setChecked(entry.favorite)
        if entry.category_id is not None:
            idx = self.category_combo.findData(entry.category_id)
            if idx >= 0:
                self.category_combo.setCurrentIndex(idx)

    def get_entry(self) -> VaultEntry:
        return VaultEntry(
            id=self.entry.id if self.entry else None,
            app_name=self.app_edit.text().strip(),
            username=self.user_edit.text().strip(),
            password=self.pw_edit.text(),
            notes=self.notes_edit.toPlainText().strip() or None,
            category_id=self.category_combo.currentData(),
            favorite=self.favorite_chk.isChecked(),
        )

    def _on_save(self) -> None:
        if not self.app_edit.text().strip():
            QMessageBox.warning(self, "Eksik", "Uygulama adı zorunlu.")
            return
        if not self.user_edit.text().strip():
            QMessageBox.warning(self, "Eksik", "Kullanıcı adı zorunlu.")
            return
        if not self.pw_edit.text():
            QMessageBox.warning(self, "Eksik", "Şifre boş olamaz.")
            return
        self.accept()
