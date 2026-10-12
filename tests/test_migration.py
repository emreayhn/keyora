"""v1.0.0 kasasının v2 şemasına (meta veri şifreli) taşınması testleri.

v1 kasa, v1.0.0'daki şema ve settings düzeniyle birebir elle oluşturulur;
böylece gerçek kullanıcı kasasının yükseltme yolu test edilir.
"""
from __future__ import annotations

import base64
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest

from core import backup, crypto
from core.database import Database, SCHEMA_VERSION
from core.vault import (
    InvalidMasterPassword, UnsupportedVaultVersion, Vault, VaultCorrupted,
)

MASTER = "v1-master-pass-1234"

# v1.0.0 (commit 2d7cc42) core/database.py SCHEMA_SQL — değiştirmeyin
V1_SCHEMA = """
CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS categories (
    id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL UNIQUE);
CREATE TABLE IF NOT EXISTS vault_entries (
    id                 INTEGER PRIMARY KEY AUTOINCREMENT,
    app_name           TEXT NOT NULL,
    username           TEXT NOT NULL,
    encrypted_password BLOB NOT NULL,
    notes              TEXT,
    category_id        INTEGER REFERENCES categories(id) ON DELETE SET NULL,
    created_at         DATETIME DEFAULT (datetime('now')),
    updated_at         DATETIME DEFAULT (datetime('now')),
    favorite           INTEGER NOT NULL DEFAULT 0);
CREATE TABLE IF NOT EXISTS password_history (
    id                 INTEGER PRIMARY KEY AUTOINCREMENT,
    entry_id           INTEGER NOT NULL REFERENCES vault_entries(id) ON DELETE CASCADE,
    encrypted_password BLOB NOT NULL,
    changed_at         DATETIME DEFAULT (datetime('now')));
CREATE INDEX IF NOT EXISTS idx_entries_app      ON vault_entries(app_name);
CREATE INDEX IF NOT EXISTS idx_entries_category ON vault_entries(category_id);
CREATE INDEX IF NOT EXISTS idx_entries_favorite ON vault_entries(favorite);
CREATE INDEX IF NOT EXISTS idx_history_entry    ON password_history(entry_id);
"""


def make_v1_vault(path: Path, *, corrupt_second: bool = False) -> None:
    """v1.0.0'ın yazacağı biçimde bir kasa dosyası oluşturur."""
    material = crypto.setup_new_vault(MASTER)
    fernet = crypto.derive_encryption_key(MASTER, material.salt_key)
    conn = sqlite3.connect(str(path))
    conn.executescript(V1_SCHEMA)
    conn.executemany("INSERT INTO settings VALUES (?, ?)", [
        ("password_hash", material.password_hash),
        ("salt_verify", base64.b64encode(material.salt_verify).decode()),
        ("salt_key", base64.b64encode(material.salt_key).decode()),
        ("auto_lock_minutes", "5"),
        ("theme", "dark"),
    ])
    conn.execute("INSERT INTO categories(name) VALUES ('İş')")
    conn.execute(
        "INSERT INTO vault_entries(app_name, username, encrypted_password, notes, "
        "category_id, favorite) VALUES (?, ?, ?, ?, ?, ?)",
        ("GitHub", "ada@ornek.com", crypto.encrypt(fernet, "gh-secret"), "iş hesabı", 1, 1),
    )
    second_pw = b"bozuk-token" if corrupt_second else crypto.encrypt(fernet, "mail-secret")
    conn.execute(
        "INSERT INTO vault_entries(app_name, username, encrypted_password, notes) "
        "VALUES (?, ?, ?, ?)",
        ("Gmail", "ada", second_pw, None),
    )
    conn.execute(
        "INSERT INTO password_history(entry_id, encrypted_password) VALUES (1, ?)",
        (crypto.encrypt(fernet, "gh-old"),),
    )
    conn.commit()
    conn.close()


@pytest.fixture
def v1_path(tmp_path) -> Path:
    path = tmp_path / "keyora.db"
    make_v1_vault(path)
    return path


def test_v1_vault_detected_as_version_1(v1_path):
    db = Database(v1_path)
    assert db.get_schema_version() == 1
    db.close()


def test_unlock_migrates_v1_and_keeps_all_data(v1_path):
    db = Database(v1_path)
    vault = Vault(db)
    vault.unlock(MASTER)

    assert db.get_schema_version() == SCHEMA_VERSION
    entries = vault.list_entries()
    assert [e.app_name for e in entries] == ["GitHub", "Gmail"]  # favori önce
    gh = entries[0]
    assert gh.username == "ada@ornek.com"
    assert gh.notes == "iş hesabı"
    assert gh.favorite is True
    assert vault.reveal_password(gh.id) == "gh-secret"
    assert vault.reveal_password(entries[1].id) == "mail-secret"
    assert vault.reveal_history(gh.id)[0]["password"] == "gh-old"
    assert [c.name for c in vault.list_categories()] == ["İş"]
    assert gh.category_id == vault.list_categories()[0].id
    db.close()


def test_migrated_file_contains_no_plaintext_metadata(v1_path):
    db = Database(v1_path)
    Vault(db).unlock(MASTER)
    db.close()

    raw = v1_path.read_bytes()
    for needle in ("GitHub", "ada@ornek.com", "Gmail", "iş hesabı", "İş"):
        assert needle.encode("utf-8") not in raw, needle

    conn = sqlite3.connect(str(v1_path))
    indexes = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='index'")}
    types = conn.execute("SELECT DISTINCT typeof(app_name) FROM vault_entries").fetchall()
    conn.close()
    assert "idx_entries_app" not in indexes
    assert types == [("blob",)]


def test_migration_takes_v1_backup_first(v1_path):
    db = Database(v1_path)
    Vault(db).unlock(MASTER)
    backups = backup.list_backups(backup.local_backup_dir(db))
    pre = [b for b in backups if b.kind == "pre-migration"]
    assert len(pre) == 1
    assert Database.inspect_backup(pre[0].path) == 1  # eski sürüme dönüş için v1 hâli
    db.close()


def test_plaintext_pre_migration_backup_is_reported_and_deletable(v1_path):
    db = Database(v1_path)
    vault = Vault(db)
    vault.unlock(MASTER)
    assert vault.just_migrated is True

    olds = vault.list_plaintext_backups()
    assert len(olds) == 1
    assert b"GitHub" in olds[0].path.read_bytes()  # gerçekten düz metin içerir

    assert vault.delete_plaintext_backups() == 1
    assert vault.list_plaintext_backups() == []
    assert not olds[0].path.exists()
    db.close()


def test_migration_is_idempotent(v1_path):
    db = Database(v1_path)
    vault = Vault(db)
    vault.unlock(MASTER)
    vault.lock()
    vault.unlock(MASTER)  # ikinci açılış tekrar migrate etmemeli
    assert [e.app_name for e in vault.list_entries()] == ["GitHub", "Gmail"]
    pre = [b for b in backup.list_backups(backup.local_backup_dir(db))
           if b.kind == "pre-migration"]
    assert len(pre) == 1
    db.close()


def test_wrong_password_leaves_v1_untouched(v1_path):
    db = Database(v1_path)
    with pytest.raises(InvalidMasterPassword):
        Vault(db).unlock("yanlış-parola")
    assert db.get_schema_version() == 1
    assert db.get_entry(1)["app_name"] == "GitHub"
    assert backup.list_backups(backup.local_backup_dir(db)) == []
    db.close()


def test_failed_migration_is_rolled_back(tmp_path):
    path = tmp_path / "keyora.db"
    make_v1_vault(path, corrupt_second=True)
    db = Database(path)
    vault = Vault(db)
    with pytest.raises(VaultCorrupted):
        vault.unlock(MASTER)
    assert vault.is_locked
    assert db.get_schema_version() == 1
    assert db.get_entry(1)["app_name"] == "GitHub"  # ilk kayıt da şifrelenmemiş kaldı
    assert db.get_setting("key_check") is None
    db.close()


def test_newer_schema_is_refused(tmp_path):
    db = Database(tmp_path / "future.db")
    vault = Vault(db)
    vault.initialize("master-pass-1234")
    vault.lock()
    db.set_setting("schema_version", str(SCHEMA_VERSION + 1))
    with pytest.raises(UnsupportedVaultVersion):
        vault.unlock("master-pass-1234")
    db.close()
