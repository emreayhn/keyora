"""Keyora SQLite katmanı — şema, CRUD, password_history rotation."""
from __future__ import annotations

import os
import sqlite3
import sys
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator, Optional

DB_FILENAME = "keyora.db"
HISTORY_LIMIT = 5

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS settings (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS categories (
    id   INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL UNIQUE
);

CREATE TABLE IF NOT EXISTS vault_entries (
    id                 INTEGER PRIMARY KEY AUTOINCREMENT,
    app_name           TEXT NOT NULL,
    username           TEXT NOT NULL,
    encrypted_password BLOB NOT NULL,
    notes              TEXT,
    category_id        INTEGER REFERENCES categories(id) ON DELETE SET NULL,
    created_at         DATETIME DEFAULT (datetime('now')),
    updated_at         DATETIME DEFAULT (datetime('now')),
    favorite           INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS password_history (
    id                 INTEGER PRIMARY KEY AUTOINCREMENT,
    entry_id           INTEGER NOT NULL REFERENCES vault_entries(id) ON DELETE CASCADE,
    encrypted_password BLOB NOT NULL,
    changed_at         DATETIME DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_entries_app      ON vault_entries(app_name);
CREATE INDEX IF NOT EXISTS idx_entries_category ON vault_entries(category_id);
CREATE INDEX IF NOT EXISTS idx_entries_favorite ON vault_entries(favorite);
CREATE INDEX IF NOT EXISTS idx_history_entry    ON password_history(entry_id);
"""


def user_data_dir() -> Path:
    """Vault DB'sinin tutulduğu kullanıcı veri dizini.

    Platform-aware:
      - Windows: %LOCALAPPDATA%\\Keyora
      - macOS:   ~/Library/Application Support/Keyora
      - Linux:   $XDG_DATA_HOME/Keyora (ya da ~/.local/share/Keyora)
    """
    if sys.platform == "win32":
        base = os.environ.get("LOCALAPPDATA") or str(Path.home() / "AppData" / "Local")
        return Path(base) / "Keyora"
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / "Keyora"
    base = os.environ.get("XDG_DATA_HOME") or str(Path.home() / ".local" / "share")
    return Path(base) / "Keyora"


def default_db_path() -> Path:
    """Vault DB için varsayılan yol.

    Üretimde her zaman kullanıcı veri dizinine yazılır — böylece PyInstaller
    onefile build'inde geçici dizinde kaybolmaz.
    KEYORA_DB_PATH ortam değişkeniyle ad-hoc dev kullanımı için ezilebilir.
    """
    override = os.environ.get("KEYORA_DB_PATH")
    if override:
        return Path(override)
    data_dir = user_data_dir()
    data_dir.mkdir(parents=True, exist_ok=True)
    return data_dir / DB_FILENAME


class Database:
    """Keyora veritabanı için ince bir sarmalayıcı. Tüm SQL raw çalıştırılır."""

    def __init__(self, path: Optional[Path] = None) -> None:
        self.path = Path(path) if path else default_db_path()
        self._conn = sqlite3.connect(str(self.path))
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA foreign_keys = ON")
        self._init_schema()

    def _init_schema(self) -> None:
        with self._conn:
            self._conn.executescript(SCHEMA_SQL)

    def close(self) -> None:
        self._conn.close()

    @contextmanager
    def transaction(self) -> Iterator[sqlite3.Connection]:
        """Atomik işlemler için kısa sözleşme."""
        try:
            yield self._conn
            self._conn.commit()
        except Exception:
            self._conn.rollback()
            raise

    # ---------- settings ----------

    def is_initialized(self) -> bool:
        """Master password kurulmuş mu?"""
        row = self._conn.execute(
            "SELECT 1 FROM settings WHERE key = 'password_hash'"
        ).fetchone()
        return row is not None

    def get_setting(self, key: str) -> Optional[str]:
        row = self._conn.execute(
            "SELECT value FROM settings WHERE key = ?", (key,)
        ).fetchone()
        return row["value"] if row else None

    def set_setting(self, key: str, value: str) -> None:
        with self.transaction() as conn:
            conn.execute(
                "INSERT INTO settings(key, value) VALUES (?, ?) "
                "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
                (key, value),
            )

    def set_settings_bulk(self, items: dict[str, str]) -> None:
        with self.transaction() as conn:
            conn.executemany(
                "INSERT INTO settings(key, value) VALUES (?, ?) "
                "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
                list(items.items()),
            )

    # ---------- categories ----------

    def list_categories(self) -> list[sqlite3.Row]:
        return list(self._conn.execute(
            "SELECT id, name FROM categories ORDER BY name COLLATE NOCASE"
        ))

    def add_category(self, name: str) -> int:
        with self.transaction() as conn:
            cur = conn.execute(
                "INSERT INTO categories(name) VALUES (?)", (name,)
            )
            return cur.lastrowid

    def rename_category(self, category_id: int, new_name: str) -> None:
        with self.transaction() as conn:
            conn.execute(
                "UPDATE categories SET name = ? WHERE id = ?",
                (new_name, category_id),
            )

    def delete_category(self, category_id: int) -> None:
        with self.transaction() as conn:
            conn.execute("DELETE FROM categories WHERE id = ?", (category_id,))

    # ---------- vault entries ----------

    def list_entries(
        self,
        *,
        category_id: Optional[int] = None,
        favorites_only: bool = False,
        search: Optional[str] = None,
    ) -> list[sqlite3.Row]:
        """Filtrelenmiş kayıt listesi. Şifre BLOB'u dahil edilir."""
        clauses: list[str] = []
        params: list = []

        if category_id is not None:
            clauses.append("category_id = ?")
            params.append(category_id)
        if favorites_only:
            clauses.append("favorite = 1")
        if search:
            clauses.append("(app_name LIKE ? OR username LIKE ?)")
            wildcard = f"%{search}%"
            params.extend([wildcard, wildcard])

        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        sql = (
            "SELECT id, app_name, username, encrypted_password, notes, "
            "       category_id, created_at, updated_at, favorite "
            f"FROM vault_entries {where} "
            "ORDER BY favorite DESC, app_name COLLATE NOCASE"
        )
        return list(self._conn.execute(sql, params))

    def get_entry(self, entry_id: int) -> Optional[sqlite3.Row]:
        return self._conn.execute(
            "SELECT id, app_name, username, encrypted_password, notes, "
            "       category_id, created_at, updated_at, favorite "
            "FROM vault_entries WHERE id = ?",
            (entry_id,),
        ).fetchone()

    def add_entry(
        self,
        *,
        app_name: str,
        username: str,
        encrypted_password: bytes,
        notes: Optional[str],
        category_id: Optional[int],
        favorite: bool = False,
    ) -> int:
        with self.transaction() as conn:
            cur = conn.execute(
                "INSERT INTO vault_entries(app_name, username, encrypted_password, "
                "                          notes, category_id, favorite) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (
                    app_name,
                    username,
                    encrypted_password,
                    notes,
                    category_id,
                    1 if favorite else 0,
                ),
            )
            return cur.lastrowid

    def update_entry(
        self,
        entry_id: int,
        *,
        app_name: str,
        username: str,
        encrypted_password: bytes,
        notes: Optional[str],
        category_id: Optional[int],
        favorite: bool,
        password_changed: bool,
    ) -> None:
        """Kayıt günceller. Şifre değiştiyse eski versiyon history'e yazılır."""
        with self.transaction() as conn:
            if password_changed:
                old = conn.execute(
                    "SELECT encrypted_password FROM vault_entries WHERE id = ?",
                    (entry_id,),
                ).fetchone()
                if old is not None:
                    self._push_history(conn, entry_id, old["encrypted_password"])

            conn.execute(
                "UPDATE vault_entries SET "
                "  app_name = ?, username = ?, encrypted_password = ?, "
                "  notes = ?, category_id = ?, favorite = ?, "
                "  updated_at = datetime('now') "
                "WHERE id = ?",
                (
                    app_name,
                    username,
                    encrypted_password,
                    notes,
                    category_id,
                    1 if favorite else 0,
                    entry_id,
                ),
            )

    def toggle_favorite(self, entry_id: int) -> None:
        with self.transaction() as conn:
            conn.execute(
                "UPDATE vault_entries SET favorite = 1 - favorite WHERE id = ?",
                (entry_id,),
            )

    def delete_entry(self, entry_id: int) -> None:
        with self.transaction() as conn:
            conn.execute("DELETE FROM vault_entries WHERE id = ?", (entry_id,))

    # ---------- password_history ----------

    def _push_history(
        self,
        conn: sqlite3.Connection,
        entry_id: int,
        old_encrypted: bytes,
    ) -> None:
        """Eski şifreyi history'e yaz, 5'i aşan en eski kayıtları sil."""
        conn.execute(
            "INSERT INTO password_history(entry_id, encrypted_password) VALUES (?, ?)",
            (entry_id, old_encrypted),
        )
        conn.execute(
            "DELETE FROM password_history "
            "WHERE id IN ("
            "  SELECT id FROM password_history "
            "  WHERE entry_id = ? "
            "  ORDER BY changed_at ASC, id ASC "
            "  LIMIT MAX(0, ("
            "    SELECT COUNT(*) FROM password_history WHERE entry_id = ?"
            "  ) - ?)"
            ")",
            (entry_id, entry_id, HISTORY_LIMIT),
        )

    def list_history(self, entry_id: int) -> list[sqlite3.Row]:
        return list(self._conn.execute(
            "SELECT id, encrypted_password, changed_at "
            "FROM password_history WHERE entry_id = ? "
            "ORDER BY changed_at DESC, id DESC",
            (entry_id,),
        ))

    # ---------- rekey ----------

    def iter_all_entry_blobs(self) -> list[sqlite3.Row]:
        """Tüm kayıtların id + encrypted_password çiftleri (rekey için)."""
        return list(self._conn.execute(
            "SELECT id, encrypted_password FROM vault_entries"
        ))

    def iter_all_history_blobs(self) -> list[sqlite3.Row]:
        """Tüm history kayıtlarının id + encrypted_password çiftleri."""
        return list(self._conn.execute(
            "SELECT id, encrypted_password FROM password_history"
        ))

    def rekey(
        self,
        entry_updates: list[tuple[int, bytes]],
        history_updates: list[tuple[int, bytes]],
        new_settings: dict[str, str],
    ) -> None:
        """Tek bir transaction içinde tüm blobları ve settings'i değiştirir.

        Master password değişiminde kullanılır — kısmi yazıma karşı atomik.
        """
        with self.transaction() as conn:
            conn.executemany(
                "UPDATE vault_entries SET encrypted_password = ? WHERE id = ?",
                [(blob, entry_id) for entry_id, blob in entry_updates],
            )
            conn.executemany(
                "UPDATE password_history SET encrypted_password = ? WHERE id = ?",
                [(blob, hist_id) for hist_id, blob in history_updates],
            )
            conn.executemany(
                "INSERT INTO settings(key, value) VALUES (?, ?) "
                "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
                list(new_settings.items()),
            )
