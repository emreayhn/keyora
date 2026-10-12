"""Ayarlar — tema, auto-lock, gizlilik, yedekleme, master password."""
from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt, Signal, QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QGridLayout, QLabel, QLineEdit,
    QPushButton, QSpinBox, QFrame, QMessageBox, QCheckBox, QComboBox,
    QFileDialog, QScrollArea, QWidget,
)

from core import backup
from core.vault import Vault, InvalidMasterPassword
from ui import theme

MIN_MASTER_LENGTH = 8


class SettingsDialog(QDialog):
    """Ayarlar paneli — değişiklik olduysa `settings_changed` yayar."""

    settings_changed = Signal()
    theme_changed = Signal(str)  # yeni tema adı (dark / light)
    capture_setting_changed = Signal(bool)  # ekran yakalamadan gizleme açık mı
    vault_restored = Signal()  # yedek geri yüklendi — kasa kilitlendi

    def __init__(self, vault: Vault, parent=None) -> None:
        super().__init__(parent)
        self.vault = vault
        self.setWindowTitle("Ayarlar")
        self.setMinimumWidth(520)
        self.resize(560, 720)
        self._build_ui()

    def _build_ui(self) -> None:
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 12)

        content = QWidget()
        layout = QVBoxLayout(content)
        layout.setContentsMargins(20, 20, 20, 8)
        layout.setSpacing(14)

        layout.addWidget(self._build_theme_panel())
        layout.addWidget(self._build_auto_lock_panel())
        layout.addWidget(self._build_privacy_panel())
        layout.addWidget(self._build_backup_panel())
        layout.addWidget(self._build_master_password_panel())
        layout.addStretch()

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setWidget(content)
        outer.addWidget(scroll, 1)

        close_btn = QPushButton("Kapat")
        close_btn.clicked.connect(self.accept)
        row = QHBoxLayout()
        row.setContentsMargins(20, 0, 20, 0)
        row.addStretch()
        row.addWidget(close_btn)
        outer.addLayout(row)

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

    # ---------- privacy ----------

    def _build_privacy_panel(self) -> QFrame:
        panel = QFrame()
        panel.setObjectName("Panel")
        grid = QGridLayout(panel)
        grid.setContentsMargins(14, 14, 14, 14)

        title = QLabel("Gizlilik")
        title.setProperty("role", "title")
        sub = QLabel(
            "Windows kilitlendiğinde, oturum kapandığında veya bilgisayar uyku "
            "moduna geçtiğinde kasa her zaman anında kilitlenir."
        )
        sub.setProperty("role", "muted")
        sub.setWordWrap(True)

        self.capture_chk = QCheckBox(
            "Pencereleri ekran görüntüsü ve ekran paylaşımından gizle"
        )
        self.capture_chk.setToolTip(
            "Teams/Zoom ile ekran paylaşırken Keyora pencereleri karşı tarafa "
            "boş görünür. Ekran görüntüsü almanız gerekiyorsa geçici olarak kapatın."
        )
        self.capture_chk.setChecked(self.vault.get_hide_from_capture())
        self.capture_chk.toggled.connect(self._on_capture_toggled)

        grid.addWidget(title, 0, 0)
        grid.addWidget(sub, 1, 0)
        grid.addWidget(self.capture_chk, 2, 0)
        return panel

    def _on_capture_toggled(self, checked: bool) -> None:
        self.vault.set_hide_from_capture(checked)
        self.capture_setting_changed.emit(checked)

    # ---------- backup ----------

    def _build_backup_panel(self) -> QFrame:
        panel = QFrame()
        panel.setObjectName("Panel")
        grid = QGridLayout(panel)
        grid.setContentsMargins(14, 14, 14, 14)

        title = QLabel("Yedekleme")
        title.setProperty("role", "title")
        sub = QLabel(
            "Kasa günde bir kez açılışta ve değişiklik yapılan her oturumun "
            "sonunda otomatik yedeklenir. Otomatik yedekler şifrelidir; açmak için "
            "yedeğin alındığı andaki master password gerekir. Disk arızasına karşı "
            "klasörü harici bir diske veya senkronize bir klasöre almanız önerilir."
        )
        sub.setProperty("role", "muted")
        sub.setWordWrap(True)

        self.backup_dir_edit = QLineEdit(str(self.vault.get_backup_dir()))
        self.backup_dir_edit.setReadOnly(True)
        change_dir_btn = QPushButton("Değiştir…")
        change_dir_btn.clicked.connect(self._on_change_backup_dir)
        reset_dir_btn = QPushButton("Varsayılan")
        reset_dir_btn.clicked.connect(self._on_reset_backup_dir)
        dir_row = QHBoxLayout()
        dir_row.addWidget(self.backup_dir_edit, 1)
        dir_row.addWidget(change_dir_btn)
        dir_row.addWidget(reset_dir_btn)

        self.keep_spin = QSpinBox()
        self.keep_spin.setRange(backup.MIN_KEEP, backup.MAX_KEEP)
        self.keep_spin.setValue(self.vault.get_backup_keep())
        self.keep_spin.setSuffix(" kopya")
        keep_save = QPushButton("Kaydet")
        keep_save.clicked.connect(self._on_save_keep)
        keep_row = QHBoxLayout()
        keep_row.addWidget(self.keep_spin)
        keep_row.addWidget(keep_save)
        keep_row.addStretch()

        self.last_backup_label = QLabel()
        self.last_backup_label.setProperty("role", "muted")
        self.last_backup_label.setWordWrap(True)
        self._refresh_last_backup()

        now_btn = QPushButton("Şimdi Yedekle")
        now_btn.setProperty("role", "primary")
        now_btn.clicked.connect(self._on_backup_now)
        open_btn = QPushButton("Klasörü Aç")
        open_btn.clicked.connect(self._on_open_backup_dir)
        restore_btn = QPushButton("Yedekten Geri Yükle…")
        restore_btn.setProperty("role", "danger")
        restore_btn.clicked.connect(self._on_restore)
        btn_row = QHBoxLayout()
        btn_row.addWidget(restore_btn)
        btn_row.addStretch()
        btn_row.addWidget(open_btn)
        btn_row.addWidget(now_btn)

        grid.addWidget(title, 0, 0, 1, 2)
        grid.addWidget(sub, 1, 0, 1, 2)
        grid.setColumnMinimumWidth(0, 56)
        grid.setColumnStretch(1, 1)
        grid.addWidget(QLabel("Klasör"), 2, 0)
        grid.addLayout(dir_row, 2, 1)
        grid.addWidget(QLabel("Sakla"), 3, 0)
        grid.addLayout(keep_row, 3, 1)
        grid.addWidget(self.last_backup_label, 4, 0, 1, 2)
        grid.addLayout(btn_row, 5, 0, 1, 2)

        # v1→v2 geçiş öncesi yedek varsa: düz metin meta veri içerdiğini söyle
        self.plain_row = QWidget()
        plain_layout = QHBoxLayout(self.plain_row)
        plain_layout.setContentsMargins(0, 6, 0, 0)
        plain_label = QLabel(
            "⚠ Keyora 1.0.0'a dönüş için saklanan geçiş öncesi yedek var. "
            "İçindeki uygulama adları, kullanıcı adları ve notlar düz metindir."
        )
        plain_label.setWordWrap(True)
        plain_btn = QPushButton("Eski Yedeği Sil")
        plain_btn.setProperty("role", "danger")
        plain_btn.clicked.connect(self._on_delete_plaintext)
        plain_layout.addWidget(plain_label, 1)
        plain_layout.addWidget(plain_btn)
        self.plain_row.setVisible(bool(self.vault.list_plaintext_backups()))
        grid.addWidget(self.plain_row, 6, 0, 1, 2)
        return panel

    def _on_delete_plaintext(self) -> None:
        confirm = QMessageBox.question(
            self, "Eski yedeği sil",
            "Geçiş öncesi yedek silinsin mi? Bundan sonra Keyora 1.0.0'a "
            "dönmek için bu yedeği kullanamazsınız.",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No,
        )
        if confirm != QMessageBox.Yes:
            return
        self.vault.delete_plaintext_backups()
        self.plain_row.setVisible(False)

    def _refresh_last_backup(self) -> None:
        backups = self.vault.list_backups()
        if backups:
            latest = backups[0]
            text = (f"Son yedek: {latest.created:%d.%m.%Y %H:%M} "
                    f"({len(backups)} yedek klasörde)")
        else:
            text = "Bu klasörde henüz yedek yok."
        if self.vault.last_backup_error:
            text += f"\n⚠ {self.vault.last_backup_error}"
        self.last_backup_label.setText(text)

    def _on_change_backup_dir(self) -> None:
        chosen = QFileDialog.getExistingDirectory(
            self, "Yedek klasörü seç", str(self.vault.get_backup_dir())
        )
        if not chosen:
            return
        try:
            self.vault.set_backup_dir(Path(chosen))
        except OSError as exc:
            QMessageBox.warning(self, "Hata", f"Klasör kullanılamıyor: {exc}")
            return
        self.backup_dir_edit.setText(str(self.vault.get_backup_dir()))
        self._refresh_last_backup()

    def _on_reset_backup_dir(self) -> None:
        self.vault.set_backup_dir(None)
        self.backup_dir_edit.setText(str(self.vault.get_backup_dir()))
        self._refresh_last_backup()

    def _on_save_keep(self) -> None:
        try:
            self.vault.set_backup_keep(self.keep_spin.value())
        except ValueError as exc:
            QMessageBox.warning(self, "Geçersiz", str(exc))
            return
        QMessageBox.information(self, "Kaydedildi", "Yedek sayısı güncellendi.")

    def _on_backup_now(self) -> None:
        try:
            path = self.vault.backup_now()
        except Exception as exc:
            QMessageBox.critical(self, "Hata", f"Yedek alınamadı: {exc}")
            return
        self._refresh_last_backup()
        QMessageBox.information(self, "Tamam", f"Yedek alındı:\n{path}")

    def _on_open_backup_dir(self) -> None:
        directory = self.vault.get_backup_dir()
        try:
            directory.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            QMessageBox.warning(self, "Hata", f"Klasör açılamadı: {exc}")
            return
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(directory)))

    def _on_restore(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, "Geri yüklenecek yedeği seç", str(self.vault.get_backup_dir()),
            "Keyora yedeği (*.db)",
        )
        if not path:
            return
        confirm = QMessageBox.warning(
            self, "Yedekten geri yükle",
            "Mevcut kasa seçilen yedekle DEĞİŞTİRİLECEK. Mevcut hâli önce "
            "'pre-restore' yedeği olarak saklanır.\n\n"
            "Geri yüklemeden sonra kasa kilitlenir; yedeğin alındığı andaki "
            "master password ile giriş yapmanız gerekir. Devam edilsin mi?",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No,
        )
        if confirm != QMessageBox.Yes:
            return
        try:
            self.vault.restore_backup(Path(path))
        except Exception as exc:
            QMessageBox.critical(self, "Geri yükleme başarısız", str(exc))
            return
        self.vault_restored.emit()
        self.accept()

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
