"""Keyora ana giriş noktası — kurulum/login/main window akışı."""
from __future__ import annotations

import sys
from pathlib import Path

from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QApplication, QDialog

from core.database import Database
from core.vault import Vault
from ui import theme
from ui.login_dialog import LoginDialog
from ui.setup_dialog import SetupDialog
from ui.main_window import MainWindow


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


def main() -> int:
    app = QApplication(sys.argv)
    app.setApplicationName("Keyora")
    app.setApplicationVersion("1.0.0")

    icon_path = _resource_path("resources/keyora.png")
    if icon_path.exists():
        app.setWindowIcon(QIcon(str(icon_path)))

    db = Database()
    vault = Vault(db)

    # Kayıtlı tema — vault başlatılmamışsa varsayılan (dark) kalır
    stored_theme = db.get_setting("theme") if vault.is_initialized else None
    theme.set_active(stored_theme or theme.DEFAULT)
    app.setStyleSheet(theme.stylesheet())

    # Kilit döngüsü: auto-lock kapattıktan sonra tekrar login isteyebilmek için
    while True:
        if not run_setup_or_login(vault):
            db.close()
            return 0

        # Setup sonrası tema DB'de oluştu — okuyup tekrar uygula
        theme.set_active(vault.get_theme())
        app.setStyleSheet(theme.stylesheet())

        window = MainWindow(vault)
        window.show()
        app.exec()

        if vault.is_locked:
            continue
        db.close()
        return 0


if __name__ == "__main__":
    sys.exit(main())
