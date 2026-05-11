"""Keyora vault session — login, kilit ve şifreleme aracıları."""
from __future__ import annotations

import base64
from dataclasses import dataclass
from typing import Optional

from cryptography.fernet import Fernet, InvalidToken

from core import crypto
from core.database import Database


class VaultLocked(RuntimeError):
    """Vault kilitliyken kripto işlemi denenirse yükselir."""


class InvalidMasterPassword(RuntimeError):
    """Master password doğrulanamazsa yükselir."""


@dataclass
class VaultEntry:
    """UI ve servis katmanı arasında taşınan ham (çözülmüş) kayıt."""
    id: Optional[int]
    app_name: str
    username: str
    password: str
    notes: Optional[str]
    category_id: Optional[int]
    favorite: bool = False


class Vault:
    """Vault session — Fernet anahtarı yalnızca burada (bellekte) yaşar."""

    def __init__(self, db: Database) -> None:
        self.db = db
        self._fernet: Optional[Fernet] = None

    # ---------- session ----------

    @property
    def is_locked(self) -> bool:
        return self._fernet is None

    @property
    def is_initialized(self) -> bool:
        return self.db.is_initialized()

    def initialize(
        self,
        master_password: str,
        *,
        auto_lock_minutes: int = 5,
        theme: str = "dark",
    ) -> None:
        """İlk kurulum — master password belirler ve vault'u açar."""
        if self.is_initialized:
            raise RuntimeError("Vault zaten kurulmuş")

        material = crypto.setup_new_vault(master_password)
        self.db.set_settings_bulk({
            "password_hash":     material.password_hash,
            "salt_verify":       base64.b64encode(material.salt_verify).decode(),
            "salt_key":          base64.b64encode(material.salt_key).decode(),
            "auto_lock_minutes": str(auto_lock_minutes),
            "theme":             theme,
        })
        self._fernet = crypto.derive_encryption_key(master_password, material.salt_key)

    def unlock(self, master_password: str) -> None:
        """Doğru parola ile session'ı açar."""
        stored_hash = self.db.get_setting("password_hash")
        salt_key_b64 = self.db.get_setting("salt_key")
        if not stored_hash or not salt_key_b64:
            raise RuntimeError("Vault başlatılmamış")

        if not crypto.verify_password(master_password, stored_hash):
            raise InvalidMasterPassword("Master password hatalı")

        salt_key = base64.b64decode(salt_key_b64)
        self._fernet = crypto.derive_encryption_key(master_password, salt_key)

    def lock(self) -> None:
        """Session'ı kilitler ve Fernet referansını düşürür."""
        self._fernet = None

    # ---------- crypto helpers ----------

    def _require_fernet(self) -> Fernet:
        if self._fernet is None:
            raise VaultLocked("Vault kilitli")
        return self._fernet

    def encrypt(self, plaintext: str) -> bytes:
        return crypto.encrypt(self._require_fernet(), plaintext)

    def decrypt(self, ciphertext: bytes) -> str:
        return crypto.decrypt(self._require_fernet(), ciphertext)

    # ---------- entry operations ----------

    def add_entry(self, entry: VaultEntry) -> int:
        """Plaintext kaydı şifreleyip DB'ye yazar, yeni id döner."""
        encrypted = self.encrypt(entry.password)
        return self.db.add_entry(
            app_name=entry.app_name,
            username=entry.username,
            encrypted_password=encrypted,
            notes=entry.notes,
            category_id=entry.category_id,
            favorite=entry.favorite,
        )

    def update_entry(self, entry: VaultEntry) -> None:
        """Kaydı günceller. Şifre değiştiyse history rotation tetiklenir."""
        if entry.id is None:
            raise ValueError("Güncellenecek kaydın id'si yok")

        existing = self.db.get_entry(entry.id)
        if existing is None:
            raise ValueError(f"Kayıt bulunamadı: id={entry.id}")

        try:
            old_password = self.decrypt(existing["encrypted_password"])
        except InvalidToken:
            old_password = None

        password_changed = old_password != entry.password
        encrypted = self.encrypt(entry.password)

        self.db.update_entry(
            entry.id,
            app_name=entry.app_name,
            username=entry.username,
            encrypted_password=encrypted,
            notes=entry.notes,
            category_id=entry.category_id,
            favorite=entry.favorite,
            password_changed=password_changed,
        )

    def reveal_password(self, entry_id: int) -> str:
        """Tek kaydın şifresini çözer (kopyala/göster butonları için)."""
        row = self.db.get_entry(entry_id)
        if row is None:
            raise ValueError(f"Kayıt bulunamadı: id={entry_id}")
        return self.decrypt(row["encrypted_password"])

    def reveal_history(self, entry_id: int) -> list[dict]:
        """Bir kaydın geçmiş şifre versiyonlarını çözer."""
        rows = self.db.list_history(entry_id)
        result = []
        for r in rows:
            try:
                pw = self.decrypt(r["encrypted_password"])
            except InvalidToken:
                pw = "<çözülemedi>"
            result.append({"id": r["id"], "password": pw, "changed_at": r["changed_at"]})
        return result

    # ---------- master password change ----------

    def change_master_password(self, old_password: str, new_password: str) -> None:
        """Master password'ü değiştirir. Tüm bloblar yeni anahtarla yeniden şifrelenir.

        İşlem atomiktir: rekey transaction'ı başarısız olursa eski anahtar geçerli kalır.
        """
        if self.is_locked:
            raise VaultLocked("Vault kilitli")

        stored_hash = self.db.get_setting("password_hash")
        if not stored_hash or not crypto.verify_password(old_password, stored_hash):
            raise InvalidMasterPassword("Eski master password hatalı")

        old_fernet = self._require_fernet()
        new_material = crypto.setup_new_vault(new_password)
        new_fernet = crypto.derive_encryption_key(new_password, new_material.salt_key)

        entry_updates: list[tuple[int, bytes]] = []
        for row in self.db.iter_all_entry_blobs():
            plain = crypto.decrypt(old_fernet, row["encrypted_password"])
            entry_updates.append((row["id"], crypto.encrypt(new_fernet, plain)))

        history_updates: list[tuple[int, bytes]] = []
        for row in self.db.iter_all_history_blobs():
            plain = crypto.decrypt(old_fernet, row["encrypted_password"])
            history_updates.append((row["id"], crypto.encrypt(new_fernet, plain)))

        self.db.rekey(
            entry_updates=entry_updates,
            history_updates=history_updates,
            new_settings={
                "password_hash": new_material.password_hash,
                "salt_verify":   base64.b64encode(new_material.salt_verify).decode(),
                "salt_key":      base64.b64encode(new_material.salt_key).decode(),
            },
        )

        self._fernet = new_fernet

    # ---------- settings ----------

    def verify_current_password(self, password: str) -> bool:
        """Açık vault için master password doğrulama (hassas işlemler öncesi)."""
        stored_hash = self.db.get_setting("password_hash")
        if not stored_hash:
            return False
        return crypto.verify_password(password, stored_hash)

    def get_auto_lock_minutes(self) -> int:
        raw = self.db.get_setting("auto_lock_minutes")
        try:
            return max(1, int(raw)) if raw else 5
        except ValueError:
            return 5

    def set_auto_lock_minutes(self, minutes: int) -> None:
        if minutes < 1:
            raise ValueError("Auto-lock en az 1 dakika olmalı")
        self.db.set_setting("auto_lock_minutes", str(minutes))

    def get_theme(self) -> str:
        return self.db.get_setting("theme") or "dark"

    def set_theme(self, name: str) -> None:
        self.db.set_setting("theme", name)
