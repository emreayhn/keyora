"""Bir vault entry'sinin geçmiş şifre versiyonları — ikon temalı satırlar."""
from __future__ import annotations

from typing import Optional

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QAction
from PySide6.QtWidgets import (
    QDialog, QFrame, QHBoxLayout, QLabel, QLineEdit, QPushButton, QScrollArea,
    QSizePolicy, QToolButton, QVBoxLayout, QWidget, QMessageBox,
)

from core.vault import Vault
from ui import icons, theme
from utils.clipboard import copy_to_clipboard

REVEAL_TIMEOUT_MS = 10_000
MASK_STRING = "•" * 10


class _HistoryRow(QFrame):
    """Tek bir geçmiş satırı — tarih + maskeli şifre kutusu (göz + kopya)."""

    def __init__(self, changed_at: str, password: str, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._password = password
        self._revealed = False
        self.setObjectName("HistoryRow")
        self.setAttribute(Qt.WA_StyledBackground, True)
        c = theme.palette()
        self.setStyleSheet(f"""
            QFrame#HistoryRow {{
                background-color: {c['bg_secondary']};
                border: 1px solid {c['border']};
                border-radius: 8px;
            }}
            QFrame#HistoryRow QLineEdit {{
                background-color: {c['field_bg']};
                color: {c['text_primary']};
                border: 1px solid {c['border']};
                border-radius: 6px;
                padding: 6px 8px;
                font-family: 'Consolas', monospace;
            }}
            QFrame#HistoryRow QLabel#Date {{
                color: {c['text_muted']};
                font-size: 12px;
            }}
        """)

        self._mask_timer = QTimer(self)
        self._mask_timer.setSingleShot(True)
        self._mask_timer.timeout.connect(self._mask)

        row = QHBoxLayout(self)
        row.setContentsMargins(12, 8, 12, 8)
        row.setSpacing(10)

        date_lbl = QLabel(changed_at)
        date_lbl.setObjectName("Date")
        date_lbl.setMinimumWidth(150)

        self.field = QLineEdit(MASK_STRING)
        self.field.setReadOnly(True)
        self.field.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        self.field.setMinimumHeight(32)

        self.eye_action = QAction(
            icons.eye_icon(16), "Göster (10 sn)", self
        )
        self.eye_action.triggered.connect(self._toggle_reveal)
        self.field.addAction(self.eye_action, QLineEdit.TrailingPosition)

        copy_action = QAction(
            icons.copy_icon(16), "Panoya kopyala", self
        )
        copy_action.triggered.connect(self._on_copy)
        self.field.addAction(copy_action, QLineEdit.TrailingPosition)

        row.addWidget(date_lbl)
        row.addWidget(self.field, 1)

    def _toggle_reveal(self) -> None:
        if self._revealed:
            self._mask()
            return
        c = theme.palette()
        self.field.setText(self._password)
        self.field.setCursorPosition(0)
        self.field.setStyleSheet(f"QLineEdit {{ color: {c['accent_strong']}; }}")
        self.eye_action.setIcon(icons.eye_off_icon(16))
        self.eye_action.setText("Gizle")
        self._revealed = True
        self._mask_timer.start(REVEAL_TIMEOUT_MS)

    def _mask(self) -> None:
        self.field.setText(MASK_STRING)
        self.field.setCursorPosition(0)
        self.field.setStyleSheet("")
        self.eye_action.setIcon(icons.eye_icon(16))
        self.eye_action.setText("Göster (10 sn)")
        self._revealed = False
        self._mask_timer.stop()

    def _on_copy(self) -> None:
        copy_to_clipboard(self._password)
        QMessageBox.information(
            self, "Kopyalandı",
            "Geçmiş şifre 20 saniyeliğine panoya kopyalandı."
        )


class HistoryDialog(QDialog):
    """Bir entry için son N (maks. 5) şifre versiyonunu listeler."""

    def __init__(self, vault: Vault, entry_id: int, app_name: str, parent=None) -> None:
        super().__init__(parent)
        self.vault = vault
        self.entry_id = entry_id
        self.setWindowTitle(f"Şifre Geçmişi — {app_name}")
        self.setMinimumWidth(560)
        self.setMinimumHeight(380)
        self._build_ui()
        self._load()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(10)

        info = QLabel(
            "En fazla son 5 versiyon saklanır. "
            "Göz simgesiyle gör, kopya simgesiyle panoya al."
        )
        info.setProperty("role", "muted")
        info.setWordWrap(True)

        # Satırların gideceği scroll alanı
        self._container = QWidget()
        self._rows_layout = QVBoxLayout(self._container)
        self._rows_layout.setContentsMargins(0, 0, 0, 0)
        self._rows_layout.setSpacing(6)
        self._rows_layout.addStretch(1)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(self._container)
        scroll.setFrameShape(QFrame.NoFrame)

        close_btn = QPushButton("Kapat")
        close_btn.clicked.connect(self.accept)
        row = QHBoxLayout()
        row.addStretch()
        row.addWidget(close_btn)

        layout.addWidget(info)
        layout.addWidget(scroll, 1)
        layout.addLayout(row)

    def _load(self) -> None:
        try:
            history = self.vault.reveal_history(self.entry_id)
        except Exception as exc:
            QMessageBox.critical(self, "Hata", f"Geçmiş okunamadı: {exc}")
            return

        if not history:
            placeholder = QLabel("Bu kayıt için geçmiş yok.")
            placeholder.setAlignment(Qt.AlignCenter)
            placeholder.setProperty("role", "muted")
            self._rows_layout.insertWidget(0, placeholder)
            return

        for entry in history:
            row = _HistoryRow(entry["changed_at"], entry["password"])
            self._rows_layout.insertWidget(self._rows_layout.count() - 1, row)
