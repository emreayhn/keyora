"""Vault session + master password değişimi testleri."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest

from core.database import Database
from core.vault import (
    Vault, VaultEntry, VaultLocked, InvalidMasterPassword,
)


@pytest.fixture
def vault(tmp_path):
    db = Database(tmp_path / "v.db")
    v = Vault(db)
    v.initialize("master-pass-1234")
    yield v
    db.close()


def test_locked_blocks_crypto(tmp_path):
    db = Database(tmp_path / "v2.db")
    v = Vault(db)
    v.initialize("pw-1234-strong")
    v.lock()
    with pytest.raises(VaultLocked):
        v.encrypt("x")
    db.close()


def test_unlock_with_wrong_password(tmp_path):
    db = Database(tmp_path / "v3.db")
    v = Vault(db)
    v.initialize("pw-1234-strong")
    v.lock()
    with pytest.raises(InvalidMasterPassword):
        v.unlock("yanlış")
    db.close()


def test_change_master_password_preserves_data(vault: Vault):
    e_id = vault.add_entry(VaultEntry(
        id=None, app_name="App", username="me",
        password="secret-pw", notes=None, category_id=None,
    ))
    # Bir güncelleme — history'e bir kayıt düşsün
    vault.update_entry(VaultEntry(
        id=e_id, app_name="App", username="me",
        password="secret-pw-2", notes=None, category_id=None,
    ))

    vault.change_master_password("master-pass-1234", "new-master-9999")

    # Aktif anahtarla şifre hâlâ okunabiliyor
    assert vault.reveal_password(e_id) == "secret-pw-2"
    # Geçmiş de okunabiliyor
    history = vault.reveal_history(e_id)
    assert len(history) == 1
    assert history[0]["password"] == "secret-pw"


def test_change_master_password_wrong_old(vault: Vault):
    vault.add_entry(VaultEntry(
        id=None, app_name="X", username="u",
        password="p", notes=None, category_id=None,
    ))
    with pytest.raises(InvalidMasterPassword):
        vault.change_master_password("wrong", "new-master-9999")


def test_relock_then_unlock_with_new_password(tmp_path):
    db = Database(tmp_path / "v4.db")
    v = Vault(db)
    v.initialize("old-pass-1234")
    e_id = v.add_entry(VaultEntry(
        id=None, app_name="A", username="u",
        password="data", notes=None, category_id=None,
    ))
    v.change_master_password("old-pass-1234", "new-pass-5678")
    v.lock()

    with pytest.raises(InvalidMasterPassword):
        v.unlock("old-pass-1234")
    v.unlock("new-pass-5678")
    assert v.reveal_password(e_id) == "data"
    db.close()


def test_auto_lock_setting(vault: Vault):
    assert vault.get_auto_lock_minutes() == 5
    vault.set_auto_lock_minutes(15)
    assert vault.get_auto_lock_minutes() == 15
    with pytest.raises(ValueError):
        vault.set_auto_lock_minutes(0)
