"""Otomatik/döner yedekleme ve geri yükleme testleri."""
from __future__ import annotations

import sys
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest

from core import backup
from core.database import Database, DatabaseError
from core.vault import Vault, VaultEntry

MASTER = "master-pass-1234"


@pytest.fixture
def vault(tmp_path):
    db = Database(tmp_path / "keyora.db")
    v = Vault(db)
    v.initialize(MASTER)
    yield v
    db.close()


def _add(vault: Vault, app: str) -> int:
    return vault.add_entry(VaultEntry(
        id=None, app_name=app, username="u", password="pw",
        notes=None, category_id=None,
    ))


def test_backup_is_a_working_encrypted_copy(vault: Vault, tmp_path):
    _add(vault, "GitHub")
    path = vault.backup_now()
    assert path.parent == tmp_path / "backups"
    assert b"GitHub" not in path.read_bytes()
    assert not list(path.parent.glob("*.partial"))

    copy_db = Database(path)
    copy = Vault(copy_db)
    copy.unlock(MASTER)
    assert [e.app_name for e in copy.list_entries()] == ["GitHub"]
    copy_db.close()


def test_rotation_keeps_only_newest_auto_backups(vault: Vault, tmp_path):
    vault.set_backup_keep(3)
    base = datetime(2026, 1, 1, 12, 0, 0)
    for i in range(6):
        backup.create_backup(vault.db, kind="auto", now=base + timedelta(hours=i))
    backup.create_backup(vault.db, kind="manual", now=base)
    backup.create_backup(vault.db, kind="pre-migration", now=base)

    items = vault.list_backups()
    autos = [b for b in items if b.kind == "auto"]
    assert len(autos) == 3
    assert autos[0].created == base + timedelta(hours=5)
    assert {b.kind for b in items} == {"auto", "manual", "pre-migration"}


def test_same_second_backups_do_not_overwrite(vault: Vault):
    now = datetime(2026, 5, 5, 10, 0, 0)
    a = backup.create_backup(vault.db, kind="manual", now=now)
    b = backup.create_backup(vault.db, kind="manual", now=now)
    assert a != b and a.exists() and b.exists()
    assert len(vault.list_backups()) == 2


def test_auto_backup_due_after_interval(vault: Vault):
    now = datetime(2026, 3, 1, 9, 0, 0)
    assert backup.auto_backup_due(vault.db, now=now)
    backup.create_backup(vault.db, kind="auto", now=now)
    assert not backup.auto_backup_due(vault.db, now=now + timedelta(hours=23))
    assert backup.auto_backup_due(vault.db, now=now + timedelta(hours=24))


def test_unlock_takes_daily_backup(vault: Vault):
    vault.lock()
    before = len(vault.list_backups())
    vault.unlock(MASTER)
    assert len(vault.list_backups()) >= before
    assert any(b.kind == "auto" for b in vault.list_backups())


def test_lock_backs_up_only_when_changed(vault: Vault):
    vault.lock()
    vault.unlock(MASTER)
    count = len(vault.list_backups())
    vault.lock()  # değişiklik yok
    assert len(vault.list_backups()) == count

    vault.unlock(MASTER)
    _add(vault, "Yeni")
    vault.lock()
    assert len(vault.list_backups()) == count + 1


def test_backup_failure_does_not_break_lock(vault: Vault, tmp_path):
    blocker = tmp_path / "not-a-dir"
    blocker.write_text("x")
    vault.db.set_setting("backup_dir", str(blocker))  # klasör yerine dosya
    _add(vault, "A")
    vault.lock()
    assert vault.is_locked
    assert vault.last_backup_error is not None


def test_disk_full_during_backup_never_blocks_lock_or_unlock(vault: Vault, monkeypatch):
    import sqlite3

    def disk_full(dest):
        raise sqlite3.OperationalError("database or disk is full")

    monkeypatch.setattr(vault.db, "backup_to", disk_full)
    _add(vault, "A")
    vault.lock()  # değişiklik var → yedek denenir, başarısız olur
    assert vault.is_locked
    assert "disk is full" in vault.last_backup_error

    vault.unlock(MASTER)  # hiç auto yedek yok → yine denenir, unlock yine başarılı
    assert not vault.is_locked


def test_failed_backup_leaves_no_partial_file(vault: Vault, tmp_path, monkeypatch):
    import sqlite3
    real_connect = sqlite3.connect

    class Exploding:
        def __init__(self, conn): self._c = conn
        def close(self): self._c.close()

    def fake_connect(path, *a, **kw):
        conn = real_connect(path, *a, **kw)
        return Exploding(conn) if str(path).endswith(".partial") else conn

    monkeypatch.setattr(sqlite3, "connect", fake_connect)
    with pytest.raises(TypeError):  # backup() Exploding'i hedef olarak kabul etmez
        vault.db.backup_to(tmp_path / "out" / "x.db")
    assert not list((tmp_path / "out").glob("*"))


def test_export_onto_live_vault_is_refused(vault: Vault):
    with pytest.raises(DatabaseError):
        vault.export_backup(vault.db.path)


def test_custom_backup_dir(vault: Vault, tmp_path):
    target = tmp_path / "usb" / "keyora"
    vault.set_backup_dir(target)
    assert vault.backup_now().parent == target
    vault.set_backup_dir(None)
    assert vault.get_backup_dir() == tmp_path / "backups"


def test_restore_replaces_content_and_locks(vault: Vault):
    keep_id = _add(vault, "Korunacak")
    snapshot = vault.backup_now()
    vault.delete_entry(keep_id)
    _add(vault, "SonradanEklenen")

    vault.restore_backup(snapshot)
    assert vault.is_locked
    vault.unlock(MASTER)
    assert [e.app_name for e in vault.list_entries()] == ["Korunacak"]
    pre = [b for b in backup.list_backups(backup.local_backup_dir(vault.db))
           if b.kind == "pre-restore"]
    assert len(pre) == 1


def test_restore_rejects_bad_files(vault: Vault, tmp_path):
    junk = tmp_path / "junk.db"
    junk.write_bytes(b"bu bir sqlite dosyasi degil" * 100)
    with pytest.raises(DatabaseError):
        vault.restore_backup(junk)

    empty = Database(tmp_path / "empty.db")  # kurulmamış kasa
    empty.close()
    with pytest.raises(DatabaseError):
        vault.restore_backup(tmp_path / "empty.db")

    with pytest.raises(DatabaseError):
        vault.restore_backup(vault.db.path)  # kendi üzerine

    assert not vault.is_locked  # başarısız geri yükleme kasayı değiştirmez


def test_export_backup_to_chosen_path(vault: Vault, tmp_path):
    _add(vault, "X")
    dest = tmp_path / "dışa" / "yedek.db"
    vault.export_backup(dest)
    assert Database.inspect_backup(dest) == 2


def test_corrupt_database_raises_database_error(tmp_path):
    bad = tmp_path / "bozuk.db"
    bad.write_bytes(b"\x00garbage" * 512)
    with pytest.raises(DatabaseError):
        Database(bad)
