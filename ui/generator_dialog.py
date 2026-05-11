"""Bağımsız şifre üreteci — herhangi bir kayda bağlı değil."""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QGridLayout, QLabel, QLineEdit,
    QPushButton, QCheckBox, QSpinBox, QFrame, QMessageBox,
)

from utils.clipboard import copy_to_clipboard
from utils.password_gen import (
    PasswordPolicy, generate_password, estimate_strength,
    DEFAULT_LENGTH, MIN_LENGTH,
)


class GeneratorDialog(QDialog):
    """Hızlı şifre üretme + panoya kopyalama aracı."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Şifre Üreteci")
        self.setMinimumWidth(440)
        self._build_ui()
        self._regenerate()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 18, 18, 18)
        layout.setSpacing(12)

        self.output = QLineEdit()
        self.output.setReadOnly(True)
        self.output.setStyleSheet("font-family: 'Consolas', monospace; font-size: 15px;")

        self.strength = QLabel(" ")
        self.strength.setProperty("role", "muted")

        copy_btn = QPushButton("Kopyala")
        copy_btn.setProperty("role", "primary")
        copy_btn.clicked.connect(self._on_copy)

        new_btn = QPushButton("Yeniden Üret")
        new_btn.clicked.connect(self._regenerate)

        top_row = QHBoxLayout()
        top_row.addWidget(self.output, 1)
        top_row.addWidget(new_btn)
        top_row.addWidget(copy_btn)

        # Seçenekler paneli
        panel = QFrame()
        panel.setObjectName("Panel")
        grid = QGridLayout(panel)
        grid.setContentsMargins(12, 12, 12, 12)

        self.length_spin = QSpinBox()
        self.length_spin.setRange(MIN_LENGTH, 64)
        self.length_spin.setValue(DEFAULT_LENGTH)
        self.length_spin.valueChanged.connect(self._regenerate)

        self.upper_chk = QCheckBox("A-Z"); self.upper_chk.setChecked(True)
        self.lower_chk = QCheckBox("a-z"); self.lower_chk.setChecked(True)
        self.digits_chk = QCheckBox("0-9"); self.digits_chk.setChecked(True)
        self.special_chk = QCheckBox("!@#$"); self.special_chk.setChecked(True)

        for chk in (self.upper_chk, self.lower_chk, self.digits_chk, self.special_chk):
            chk.toggled.connect(self._regenerate)

        grid.addWidget(QLabel("Uzunluk"), 0, 0)
        grid.addWidget(self.length_spin, 0, 1)
        grid.addWidget(self.upper_chk, 0, 2)
        grid.addWidget(self.lower_chk, 0, 3)
        grid.addWidget(self.digits_chk, 1, 2)
        grid.addWidget(self.special_chk, 1, 3)

        close_btn = QPushButton("Kapat")
        close_btn.clicked.connect(self.accept)
        bottom = QHBoxLayout()
        bottom.addStretch()
        bottom.addWidget(close_btn)

        layout.addLayout(top_row)
        layout.addWidget(self.strength)
        layout.addWidget(panel)
        layout.addLayout(bottom)

    def _policy(self) -> PasswordPolicy:
        return PasswordPolicy(
            length=self.length_spin.value(),
            use_upper=self.upper_chk.isChecked(),
            use_lower=self.lower_chk.isChecked(),
            use_digits=self.digits_chk.isChecked(),
            use_special=self.special_chk.isChecked(),
        )

    def _regenerate(self) -> None:
        try:
            pw = generate_password(self._policy())
        except ValueError as exc:
            self.output.setText("")
            self.strength.setText(str(exc))
            return
        self.output.setText(pw)
        self.strength.setText(f"Güç: {estimate_strength(pw)}")

    def _on_copy(self) -> None:
        text = self.output.text()
        if not text:
            return
        copy_to_clipboard(text)
        QMessageBox.information(
            self, "Kopyalandı",
            "Şifre 20 saniyeliğine panoya kopyalandı."
        )
