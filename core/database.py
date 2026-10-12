"""Keyora SQLite katmanı — şema, CRUD, password_history rotation, yedek.

Şema sürümleri (settings.schema_version):
  1 — v1.0.0: app_name / username / notes / kategori adı düz metin.
  2 — v1.1.0: bu alanlar da Fernet ile şifreli (BLOB); Argon2 parametreleri
      settings'te (kdf_*). Geçiş anahtar gerektirdiği için Vault.unlock içinde
      yapılır, bkz. core/vault.py.
"""
from __future__ import annotations

import os
import sqlite3
import sys
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator, Optional

DB_FILENAME = "keyora.db"
HISTORY_LIMIT = 5
SCHEMA_VERSION = 2

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS settings (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS categories (
    id   INTEGER PRIMARY KEY AUTOINCREMENT,
    name BLOB NOT NULL               -- şifreli (v2+)
);

CREATE TABLE IF NOT EXISTS vault_entries (
    id                 INTEGER PRIMARY KEY AUTOINCREMENT,
    app_name           BLOB NOT NULL,  -- şifreli (v2+)
    username           BLOB NOT NULL,  -- şifreli (v2+)
    encrypted_password BLOB NOT NULL,
    notes              BLOB,           -- şifreli (v2+)
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


class DatabaseError(RuntimeError):
    """Kasa dosyası açılamadı, bozuk ya da Keyora kasası değil."""


EntryCipherRow = tuple[int, bytes, bytes, bytes, Optional[bytes]]
"""(id, app_name, username, encrypted_password, notes) — hepsi şifreli."""

BulkEntry = tuple[bytes, bytes, bytes, Optional[bytes], Optional[int], Optional[int], bool]
"""(app_name, username, encrypted_password, notes, category_id,
new_category_index, favorite) — metin alanları şifreli."""


def _open_readonly(path: Path) -> sqlite3.Connection:
    """Dosyayı salt okunur açar — yedeği incelerken yanlışlıkla değiştirmemek için."""
    return sqlite3.connect(f"{Path(path).resolve().as_uri()}?mode=ro", uri=True)


class Database:
    """Keyora veritabanı için ince bir sarmalayıcı. Tüm SQL raw çalıştırılır.

    v2 şemasında app_name, username, notes ve kategori adı alanları şifreli
    BLOB'dur; bu katman içeriği görmez, yalnızca bayt taşır. Arama ve
    sıralama şifre çözüldükten sonra Vault katmanında yapılır.
    """

    def __init__(self, path: Optional[Path] = None) -> None:
        self.path = Path(path) if path else default_db_path()
        try:
            self._conn = sqlite3.connect(str(self.path))
            self._conn.row_factory = sqlite3.Row
            self._conn.execute("PRAGMA foreign_keys = ON")
            # Silinen/üzerine yazılan içerik boş sayfalarda okunabilir kalmasın
            self._conn.execute("PRAGMA secure_delete = ON")
            self._init_schema()
        except sqlite3.DatabaseError as exc:
            raise DatabaseError(f"Kasa dosyası açılamadı: {exc}") from exc

    def _init_schema(self) -> None:
        with self._conn:
            self._conn.executescript(SCHEMA_SQL)

    def close(self) -> None:
        """Bağlantıyı kapatır."""
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

    def quick_check(self) -> bool:
        """SQLite bütünlük kontrolü — dosya bozuksa False."""
        try:
            row = self._conn.execute("PRAGMA quick_check").fetchone()
        except sqlite3.DatabaseError:
            return False
        return row is not None and row[0] == "ok"

    @property
    def total_changes(self) -> int:
        """Bağlantı açıldığından beri değişen satır sayısı (yedek tetikleme için)."""
        return self._conn.total_changes

    # ---------- settings ----------

    def is_initialized(self) -> bool:
        """Master password kurulmuş mu?"""
        row = self._conn.execute(
            "SELECT 1 FROM settings WHERE key = 'password_hash'"
        ).fetchone()
        return row is not None

    def get_setting(self, key: str) -> Optional[str]:
        """Ayar değerini döner, yoksa None."""
        row = self._conn.execute(
            "SELECT value FROM settings WHERE key = ?", (key,)
        ).fetchone()
        return row["value"] if row else None

    def set_setting(self, key: str, value: str) -> None:
        """Tek ayarı yazar (upsert)."""
        with self.transaction() as conn:
            conn.execute(
                "INSERT INTO settings(key, value) VALUES (?, ?) "
                "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
                (key, value),
            )

    def set_settings_bulk(self, items: dict[str, str]) -> None:
        """Birden çok ayarı tek transaction'da yazar."""
        with self.transaction() as conn:
            conn.executemany(
                "INSERT INTO settings(key, value) VALUES (?, ?) "
                "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
                list(items.items()),
            )

    def delete_setting(self, key: str) -> None:
        """Ayarı siler (yoksa bir şey yapmaz)."""
        with self.transaction() as conn:
            conn.execute("DELETE FROM settings WHERE key = ?", (key,))

    def get_schema_version(self) -> int:
        """Kasanın şema sürümü. Kurulmuş ama sürüm yazılmamış kasa v1'dir."""
        raw = self.get_setting("schema_version")
        if raw is None:
            return 1 if self.is_initialized() else SCHEMA_VERSION
        try:
            return int(raw)
        except ValueError as exc:
            raise DatabaseError(f"Geçersiz schema_version: {raw!r}") from exc

    # ---------- categories ----------

    def list_categories(self) -> list[sqlite3.Row]:
        """Tüm kategoriler (id, şifreli name). Sıralama Vault'ta yapılır."""
        return list(self._conn.execute("SELECT id, name FROM categories"))

    def add_category(self, name: bytes) -> int:
        """Şifreli adla kategori ekler, yeni id döner."""
        with self.transaction() as conn:
            cur = conn.execute(
                "INSERT INTO categories(name) VALUES (?)", (name,)
            )
            return cur.lastrowid

    def rename_category(self, category_id: int, new_name: bytes) -> None:
        """Kategorinin şifreli adını değiştirir."""
        with self.transaction() as conn:
            conn.execute(
                "UPDATE categories SET name = ? WHERE id = ?",
                (new_name, category_id),
            )

    def delete_category(self, category_id: int) -> None:
        """Kategoriyi siler; bağlı kayıtlar kategorisiz kalır."""
        with self.transaction() as conn:
            conn.execute("DELETE FROM categories WHERE id = ?", (category_id,))

    # ---------- vault entries ----------

    def list_entries(
        self,
        *,
        category_id: Optional[int] = None,
        favorites_only: bool = False,
    ) -> list[sqlite3.Row]:
        """Filtrelenmiş kayıt listesi (şifreli alanlarla). Arama Vault'ta yapılır."""
        clauses: list[str] = []
        params: list = []

        if category_id is not None:
            clauses.append("category_id = ?")
            params.append(category_id)
        if favorites_only:
            clauses.append("favorite = 1")

        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        sql = (
            "SELECT id, app_name, username, encrypted_password, notes, "
            "       category_id, created_at, updated_at, favorite "
            f"FROM vault_entries {where}"
        )
        return list(self._conn.execute(sql, params))

    def add_bulk(
        self,
        *,
        new_categories: list[bytes],
        entries: list[BulkEntry],
    ) -> int:
        """Yeni kategorileri ve kayıtları TEK transaction'da ekler (içe aktarma).

        Kayıt, mevcut bir kategoriye `category_id` ile ya da bu çağrıda
        oluşturulan bir kategoriye `new_category_index` ile bağlanır. Herhangi
        bir satırda hata olursa hiçbir şey yazılmaz. Eklenen kayıt sayısını döner.
        """
        with self.transaction() as conn:
            created_ids = [
                conn.execute("INSERT INTO categories(name) VALUES (?)", (name,)).lastrowid
                for name in new_categories
            ]
            conn.executemany(
                "INSERT INTO vault_entries(app_name, username, encrypted_password, "
                "                          notes, category_id, favorite) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                [
                    (
                        app, user, pw, notes,
                        created_ids[new_idx] if new_idx is not None else cat_id,
                        1 if favorite else 0,
                    )
                    for app, user, pw, notes, cat_id, new_idx, favorite in entries
                ],
            )
        return len(entries)

    def get_entry(self, entry_id: int) -> Optional[sqlite3.Row]:
        """Tek kayıt (şifreli alanlarla), yoksa None."""
        return self._conn.execute(
            "SELECT id, app_name, username, encrypted_password, notes, "
            "       category_id, created_at, updated_at, favorite "
            "FROM vault_entries WHERE id = ?",
            (entry_id,),
        ).fetchone()

    def add_entry(
        self,
        *,
        app_name: bytes,
        username: bytes,
        encrypted_password: bytes,
        notes: Optional[bytes],
        category_id: Optional[int],
        favorite: bool = False,
    ) -> int:
        """Şifreli alanlarla kayıt ekler, yeni id döner."""
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
        app_name: bytes,
        username: bytes,
        encrypted_password: bytes,
        notes: Optional[bytes],
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
        """Favori bayrağını tersine çevirir."""
        with self.transaction() as conn:
            conn.execute(
                "UPDATE vault_entries SET favorite = 1 - favorite WHERE id = ?",
                (entry_id,),
            )

    def delete_entry(self, entry_id: int) -> None:
        """Kaydı ve (cascade ile) geçmişini siler."""
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
        """Bir kaydın geçmiş şifre blobları, en yeniden eskiye."""
        return list(self._conn.execute(
            "SELECT id, encrypted_password, changed_at "
            "FROM password_history WHERE entry_id = ? "
            "ORDER BY changed_at DESC, id DESC",
            (entry_id,),
        ))

    def last_password_changes(self) -> dict[int, str]:
        """Her kayıt için şifrenin en son değiştiği an (history'deki en yeni satır).

        Hiç değişmemiş kayıtlar sözlükte yer almaz; onlar için created_at geçerlidir.
        """
        return {
            row["entry_id"]: row["last_change"]
            for row in self._conn.execute(
                "SELECT entry_id, MAX(changed_at) AS last_change "
                "FROM password_history GROUP BY entry_id"
            )
        }

    # ---------- toplu yeniden yazım (rekey / migration) ----------

    def iter_all_entries_raw(self) -> list[sqlite3.Row]:
        """Tüm kayıtların ham alanları (v2'de şifreli, v1'de meta veri düz)."""
        return list(self._conn.execute(
            "SELECT id, app_name, username, encrypted_password, notes FROM vault_entries"
        ))

    def iter_all_history_blobs(self) -> list[sqlite3.Row]:
        """Tüm history kayıtlarının id + encrypted_password çiftleri."""
        return list(self._conn.execute(
            "SELECT id, encrypted_password FROM password_history"
        ))

    def rewrite_all(
        self,
        *,
        entries: list[EntryCipherRow],
        history: list[tuple[int, bytes]],
        categories: list[tuple[int, bytes]],
        new_settings: dict[str, str],
    ) -> None:
        """Tüm şifreli alanları ve settings'i TEK transaction'da değiştirir.

        Master password değişimi ve v1→v2 migration'ı bunu kullanır: herhangi
        bir adımda hata olursa hiçbir şey yazılmaz, kasa eski hâlinde kalır.
        """
        with self.transaction() as conn:
            conn.executemany(
                "UPDATE vault_entries SET app_name = ?, username = ?, "
                "  encrypted_password = ?, notes = ? WHERE id = ?",
                [(app, user, pw, notes, entry_id)
                 for entry_id, app, user, pw, notes in entries],
            )
            conn.executemany(
                "UPDATE password_history SET encrypted_password = ? WHERE id = ?",
                [(blob, hist_id) for hist_id, blob in history],
            )
            conn.executemany(
                "UPDATE categories SET name = ? WHERE id = ?",
                [(name, cat_id) for cat_id, name in categories],
            )
            conn.executemany(
                "INSERT INTO settings(key, value) VALUES (?, ?) "
                "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
                list(new_settings.items()),
            )
            # v1'deki düz metin app_name indeksi artık işe yaramaz
            conn.execute("DROP INDEX IF EXISTS idx_entries_app")

    def vacuum(self) -> None:
        """Dosyayı yeniden yazar; eski sürümden kalan serbest sayfaları temizler."""
        self._conn.execute("VACUUM")

    # ---------- yedek / geri yükleme ----------

    def backup_to(self, dest: Path) -> None:
        """Kasanın tutarlı bir kopyasını dest'e yazar (SQLite online backup API).

        Kopya önce geçici dosyaya yazılıp sonra yerine taşınır; yarım kalan
        bir yedek hiçbir zaman geçerli dosya adıyla görünmez.
        """
        dest = Path(dest)
        if dest.resolve() == self.path.resolve():
            raise DatabaseError("Yedek, açık kasa dosyasının üzerine yazılamaz")
        dest.parent.mkdir(parents=True, exist_ok=True)
        tmp = dest.with_name(dest.name + ".partial")
        if tmp.exists():
            tmp.unlink()
        try:
            target = sqlite3.connect(str(tmp))
            try:
                self._conn.backup(target)
            finally:
                target.close()
            os.replace(tmp, dest)
        except BaseException:
            tmp.unlink(missing_ok=True)  # yarım dosya kalmasın (ör. disk dolu)
            raise

    @staticmethod
    def inspect_backup(src: Path) -> int:
        """Yedek dosyasını doğrular ve şema sürümünü döner.

        Bozuk, Keyora kasası olmayan ya da kurulmamış dosyada DatabaseError.
        """
        src = Path(src)
        if not src.is_file():
            raise DatabaseError(f"Yedek bulunamadı: {src}")
        try:
            conn = _open_readonly(src)
        except sqlite3.DatabaseError as exc:
            raise DatabaseError(f"Yedek açılamadı: {exc}") from exc
        try:
            if conn.execute("PRAGMA quick_check").fetchone()[0] != "ok":
                raise DatabaseError("Yedek dosyası bozuk")
            rows = dict(conn.execute(
                "SELECT key, value FROM settings "
                "WHERE key IN ('password_hash', 'schema_version')"
            ).fetchall())
        except sqlite3.DatabaseError as exc:
            raise DatabaseError(f"Keyora yedeği değil: {exc}") from exc
        finally:
            conn.close()
        if "password_hash" not in rows:
            raise DatabaseError("Yedekte kurulu bir kasa yok")
        try:
            return int(rows.get("schema_version") or 1)
        except ValueError as exc:
            raise DatabaseError("Yedeğin şema sürümü okunamadı") from exc

    def restore_from(self, src: Path) -> None:
        """Kasa içeriğini src yedeğiyle değiştirir (bağlantı açık kalır).

        Çağıran önce inspect_backup ile doğrulamalı ve mevcut kasanın
        yedeğini almalıdır — bkz. core/backup.py: restore_backup.
        """
        source = _open_readonly(src)
        try:
            source.backup(self._conn)
        finally:
            source.close()
        self._init_schema()
