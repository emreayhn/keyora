"""Giriş ekranı: Enter tuşu kilidi bir kez açmayı dener, doğru mesaj görünür."""
from __future__ import annotations

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtCore import Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QDialog

from core.database import Database
from core.vault import Vault

MASTER = "master-pass-1234"


@pytest.fixture(scope="module")
def qapp():
    return QApplication.instance() or QApplication([])


@pytest.fixture
def dialog(qapp, tmp_path):
    from ui.login_dialog import LoginDialog

    db = Database(tmp_path / "v.db")
    vault = Vault(db)
    vault.initialize(MASTER)
    vault.lock(backup_changes=False)
    calls: list[int] = []
    real_unlock = vault.unlock

    def counting_unlock(pw: str) -> None:
        calls.append(1)
        real_unlock(pw)

    vault.unlock = counting_unlock
    d = LoginDialog(vault)
    d.show()
    qapp.processEvents()
    yield d, vault, calls
    d.close()
    db.close()


def test_enter_with_wrong_password_shows_wrong_password(dialog, qapp):
    d, _vault, calls = dialog
    QTest.keyClicks(d.pw_edit, "yanlis-sifre")
    QTest.keyClick(d.pw_edit, Qt.Key_Return)
    qapp.processEvents()
    assert calls == [1]
    assert d.error_label.text() == "Hatalı şifre."


def test_enter_with_empty_password_does_not_try_unlock(dialog, qapp):
    d, _vault, calls = dialog
    QTest.keyClick(d.pw_edit, Qt.Key_Return)
    qapp.processEvents()
    assert calls == []
    assert d.error_label.text() == "Şifre boş olamaz."


def test_enter_with_right_password_unlocks_once(dialog, qapp):
    d, vault, calls = dialog
    QTest.keyClicks(d.pw_edit, MASTER)
    QTest.keyClick(d.pw_edit, Qt.Key_Return)
    qapp.processEvents()
    assert calls == [1]
    assert d.result() == QDialog.Accepted
    assert not vault.is_locked


def test_enter_during_throttle_does_not_try_unlock(dialog, qapp):
    d, vault, calls = dialog
    vault.lockout_remaining = lambda: 30
    d._update_throttle()
    QTest.keyClick(d.pw_edit, Qt.Key_Return)
    QTest.keyClick(d, Qt.Key_Return)
    qapp.processEvents()
    assert calls == []
    assert d.error_label.text().startswith("Çok fazla hatalı deneme.")
    d._throttle_timer.stop()
