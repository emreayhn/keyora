"""Vault kaydını gösteren kart — kolonlu yerleşim + alan içi ikonlar, tema duyarlı."""
from __future__ import annotations

from typing import Optional

from PySide6.QtCore import Qt, Signal, QTimer
from PySide6.QtGui import QAction
from PySide6.QtWidgets import (
    QFrame, QHBoxLayout, QLabel, QLineEdit, QSizePolicy, QToolButton, QWidget,
)

from ui import icons, theme

REVEAL_TIMEOUT_MS = 10_000
MASK_STRING = "•" * 10

# Header satırıyla aynı genişlik şablonu — değişirse oraya da yansıt.
COL_FAV_W      = 36
COL_APP_STR    = 3
COL_USER_STR   = 4
COL_PW_STR     = 4
COL_ACTION_W   = 36


class EntryCard(QFrame):
    """Tek satırlık kayıt kartı — favori, app, kullanıcı, şifre, geçmiş, düzenle, sil."""

    reveal_requested        = Signal(int)
    copy_username_requested = Signal(int)
    copy_password_requested = Signal(int)
    history_requested       = Signal(int)
    edit_requested          = Signal(int)
    favorite_requested      = Signal(int)
    delete_requested        = Signal(int)

    def __init__(
        self,
        entry_id: int,
        app_name: str,
        username: str,
        favorite: bool,
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self.entry_id = entry_id
        self._revealed = False
        self.setObjectName("EntryCard")
        self.setAttribute(Qt.WA_StyledBackground, True)

        self._mask_timer = QTimer(self)
        self._mask_timer.setSingleShot(True)
        self._mask_timer.timeout.connect(self._mask_password)

        self._apply_style()
        self._build_ui(app_name, username, favorite)

    # ---------- style ----------

    def _apply_style(self) -> None:
        c = theme.palette()
        self.setStyleSheet(f"""
            QFrame#EntryCard {{
                background-color: {c['bg_secondary']};
                border: 1px solid {c['border']};
                border-radius: 10px;
            }}
            QFrame#EntryCard:hover {{
                border: 1px solid {c['border_hover']};
            }}
            QFrame#EntryCard QLineEdit {{
                background-color: {c['field_bg']};
                color: {c['text_primary']};
                border: 1px solid {c['border']};
                border-radius: 6px;
                padding: 6px 8px;
                selection-background-color: {c['accent']};
                selection-color: {c['text_on_accent']};
            }}
            QFrame#EntryCard QLineEdit:focus {{
                border: 1px solid {c['border_hover']};
            }}
            QFrame#EntryCard QToolButton {{
                background: transparent;
                border: none;
                padding: 4px;
                border-radius: 6px;
            }}
            QFrame#EntryCard QToolButton:hover {{
                background-color: {c['bg_card']};
            }}
        """)

    # ---------- build ----------

    def _build_ui(self, app_name: str, username: str, favorite: bool) -> None:
        c = theme.palette()
        outer = QHBoxLayout(self)
        outer.setContentsMargins(12, 10, 12, 10)
        outer.setSpacing(10)

        # 1) Favori
        self.fav_btn = QToolButton()
        self.fav_btn.setIcon(icons.star_icon(20, filled=favorite))
        self.fav_btn.setFixedSize(COL_FAV_W, 32)
        self.fav_btn.setToolTip("Favorilere ekle / çıkar")
        self.fav_btn.setCursor(Qt.PointingHandCursor)
        self.fav_btn.clicked.connect(lambda: self.favorite_requested.emit(self.entry_id))
        outer.addWidget(self.fav_btn)

        # 2) Uygulama adı
        self.app_label = QLabel(app_name)
        self.app_label.setStyleSheet(
            f"color: {c['text_primary']}; font-size: 14px; font-weight: 600; padding-left: 4px;"
        )
        self.app_label.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        outer.addWidget(self.app_label, COL_APP_STR)

        # 3) Kullanıcı adı — read-only QLineEdit + sağ kenarda kopya ikonu
        self.user_field = QLineEdit(username)
        self.user_field.setReadOnly(True)
        self.user_field.setCursorPosition(0)
        self.user_field.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        self.user_field.setMinimumHeight(32)

        self.copy_user_action = QAction(
            icons.copy_icon(16), "Kullanıcı adını kopyala", self
        )
        self.copy_user_action.triggered.connect(
            lambda: self.copy_username_requested.emit(self.entry_id)
        )
        self.user_field.addAction(self.copy_user_action, QLineEdit.TrailingPosition)
        outer.addWidget(self.user_field, COL_USER_STR)

        # 4) Şifre — maskeli QLineEdit + içinde göz + kopya ikonu
        self.pw_field = QLineEdit(MASK_STRING)
        self.pw_field.setReadOnly(True)
        self.pw_field.setCursorPosition(0)
        self.pw_field.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        self.pw_field.setMinimumHeight(32)
        self.pw_field.setStyleSheet(
            "QLineEdit { font-family: 'Consolas', monospace; }"
        )

        self.eye_action = QAction(
            icons.eye_icon(16), "Şifreyi göster (10 sn)", self
        )
        self.eye_action.triggered.connect(self._on_eye_click)
        self.pw_field.addAction(self.eye_action, QLineEdit.TrailingPosition)

        self.copy_pw_action = QAction(
            icons.copy_icon(16), "Şifreyi panoya kopyala", self
        )
        self.copy_pw_action.triggered.connect(
            lambda: self.copy_password_requested.emit(self.entry_id)
        )
        self.pw_field.addAction(self.copy_pw_action, QLineEdit.TrailingPosition)
        outer.addWidget(self.pw_field, COL_PW_STR)

        # 5-6-7) Geçmiş / Düzenle / Sil — sadece ikon
        self.history_btn = self._icon_button(
            icons.clipboard_history_icon(20), "Şifre geçmişi (son 5)",
            lambda: self.history_requested.emit(self.entry_id),
        )
        self.edit_btn = self._icon_button(
            icons.pencil_icon(20), "Düzenle",
            lambda: self.edit_requested.emit(self.entry_id),
        )
        self.delete_btn = self._icon_button(
            icons.trash_icon(20), "Sil",
            lambda: self.delete_requested.emit(self.entry_id),
        )

        outer.addWidget(self.history_btn)
        outer.addWidget(self.edit_btn)
        outer.addWidget(self.delete_btn)

    def _icon_button(self, icon, tooltip: str, on_click) -> QToolButton:
        btn = QToolButton()
        btn.setIcon(icon)
        btn.setToolTip(tooltip)
        btn.setFixedSize(COL_ACTION_W, 32)
        btn.setCursor(Qt.PointingHandCursor)
        btn.clicked.connect(on_click)
        return btn

    # ---------- reveal ----------

    def _on_eye_click(self) -> None:
        if self._revealed:
            self._mask_password()
            return
        self.reveal_requested.emit(self.entry_id)

    def show_password(self, plaintext: str) -> None:
        """Parent decrypt sonrası — şifreyi göster, sonra otomatik maskele."""
        c = theme.palette()
        self.pw_field.setText(plaintext)
        self.pw_field.setCursorPosition(0)
        self.pw_field.setStyleSheet(
            f"QLineEdit {{ font-family: 'Consolas', monospace; color: {c['accent_strong']}; }}"
        )
        self.eye_action.setIcon(icons.eye_off_icon(16))
        self.eye_action.setText("Şifreyi gizle")
        self._revealed = True
        self._mask_timer.start(REVEAL_TIMEOUT_MS)

    def _mask_password(self) -> None:
        self.pw_field.setText(MASK_STRING)
        self.pw_field.setCursorPosition(0)
        self.pw_field.setStyleSheet(
            "QLineEdit { font-family: 'Consolas', monospace; }"
        )
        self.eye_action.setIcon(icons.eye_icon(16))
        self.eye_action.setText("Şifreyi göster (10 sn)")
        self._revealed = False
        self._mask_timer.stop()
