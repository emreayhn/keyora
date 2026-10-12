"""Keyora ana giriş noktası — kurulum/login/main window akışı."""
from __future__ import annotations

import sys
from pathlib import Path
from typing import Optional

from PySide6.QtCore import QTimer
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QApplication, QDialog, QMessageBox

from core import backup
from core.database import Database, DatabaseError, default_db_path
from core.vault import Vault
from ui import theme
from ui.login_dialog import LoginDialog
from ui.setup_dialog import SetupDialog
from ui.main_window import MainWindow
from utils.win_integration import CaptureGuard, SessionLockFilter


def _resource_path(relative: str) -> Path:
    """PyInstaller --onefile altında MEIPASS, geliştirmede proje kökü."""
    base = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent))
    return base / relative


def run_setup_or_login(vault: Vault) -> bool:
    """Vault durumuna göre setup veya login akışını çalıştırır."""
    if vault.is_initialized:
        dialog: QDialog = LoginDialog(vault)
    else:
        dialog = SetupDialog(vault)
    return dialog.exec() == QDialog.Accepted


def open_database() -> Optional[Database]:
    """Kasayı açar; açılamıyor veya bozuksa kullanıcıyı yedeklere yönlendirir."""
    db_path = default_db_path()
    backups_hint = db_path.parent / backup.BACKUP_DIRNAME
    try:
        db = Database(db_path)
    except DatabaseError as exc:
        QMessageBox.critical(
            None, "Keyora — Kasa açılamadı",
            f"{exc}\n\nKasa dosyası: {db_path}\n"
            f"Otomatik yedekler: {backups_hint}\n\n"
            "Bozuk dosyayı başka bir yere taşıyıp en yeni yedeği "
            f"'{db_path.name}' adıyla yerine kopyalayarak kasanızı kurtarabilirsiniz.",
        )
        return None
    if not db.quick_check():
        QMessageBox.warning(
            None, "Keyora — Bütünlük uyarısı",
            "Kasa dosyasında bütünlük hatası bulundu. Verileriniz etkilenmiş olabilir.\n\n"
            f"Otomatik yedekler: {backups_hint}\n"
            "Giriş yaptıktan sonra Ayarlar → Yedekleme → 'Yedekten Geri Yükle' ile "
            "son sağlam yedeğe dönebilirsiniz.",
        )
    return db


def main() -> int:
    """Uygulamayı başlatır ve kilit döngüsünü yönetir."""
    app = QApplication(sys.argv)
    app.setApplicationName("Keyora")
    app.setApplicationVersion("1.0.0")

    icon_path = _resource_path("resources/keyora.png")
    if icon_path.exists():
        app.setWindowIcon(QIcon(str(icon_path)))

    db = open_database()
    if db is None:
        return 1
    vault = Vault(db)

    # Kayıtlı tema — vault başlatılmamışsa varsayılan (dark) kalır
    stored_theme = db.get_setting("theme") if vault.is_initialized else None
    theme.set_active(stored_theme or theme.DEFAULT)
    app.setStyleSheet(theme.stylesheet())

    # Tüm pencereleri (login dahil) ekran yakalamadan gizle — ayar kasada
    capture_guard = CaptureGuard(enabled=vault.get_hide_from_capture(), parent=app)
    app.installEventFilter(capture_guard)

    # Windows kilitlenince / uykuya geçince açık kasayı kilitle
    current: dict[str, Optional[MainWindow]] = {"window": None}

    def lock_on_session_event() -> None:
        window = current["window"]
        if window is None or vault.is_locked:
            return
        # Anahtarı HEMEN düşür: sistem olay döngüsü dönmeden uykuya/hazırda
        # bekletmeye geçerse anahtar bellekte kalmasın. Uyku sırasında diske
        # yazmamak için yedek, pencere kapanırken (uyanınca) alınır.
        vault.lock(backup_changes=False)
        # Pencereyi kapatma işi native olay işleyicisinin dışında yapılır
        QTimer.singleShot(0, window.lock_now)

    session_filter = SessionLockFilter(lock_on_session_event)
    app.installNativeEventFilter(session_filter)

    # Kilit döngüsü: auto-lock kapattıktan sonra tekrar login isteyebilmek için
    while True:
        if not run_setup_or_login(vault):
            db.close()
            return 0

        # Setup sonrası tema DB'de oluştu — okuyup tekrar uygula
        theme.set_active(vault.get_theme())
        app.setStyleSheet(theme.stylesheet())
        capture_guard.enabled = vault.get_hide_from_capture()

        window = MainWindow(vault, capture_guard=capture_guard)
        window.show()
        session_filter.register(window)
        current["window"] = window
        app.exec()
        current["window"] = None
        session_filter.unregister(window)
        window.deleteLater()  # kilitli pencerenin widget'ları bellekte kalmasın
        del window

        if vault.is_locked:
            continue
        vault.lock()  # çıkışta da anahtarı düşür; değişiklik varsa yedekle
        db.close()
        return 0


if __name__ == "__main__":
    sys.exit(main())
