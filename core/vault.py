"""Keyora vault session — login, kilit, migration ve şifreleme aracıları."""
from __future__ import annotations

import base64
import unicodedata
import sqlite3
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Optional

from cryptography.fernet import Fernet, InvalidToken

from core import backup, crypto
from core.database import Database, EntryCipherRow, SCHEMA_VERSION

# Yanlış giriş denemelerinde artan bekleme: ilk FREE_ATTEMPTS ücretsiz,
# sonra BASE_DELAY_S * 2^(n - FREE_ATTEMPTS), en fazla MAX_DELAY_S saniye.
FREE_ATTEMPTS = 3
BASE_DELAY_S = 5
MAX_DELAY_S = 300

KEY_CHECK_PLAINTEXT = "keyora-key-check"

# v1.0.0'ın sabit Argon2 parametreleri. kdf_* ayarı olmayan (taşınmamış) kasa
# her zaman bunlarla açılır — crypto.DEFAULT_KDF ileride değişse bile.
V1_KDF = crypto.KdfParams(time_cost=3, memory_cost=65536, parallelism=1)


class VaultLocked(RuntimeError):
    """Vault kilitliyken kripto işlemi denenirse yükselir."""


class InvalidMasterPassword(RuntimeError):
    """Master password doğrulanamazsa yükselir."""


class LoginThrottled(RuntimeError):
    """Çok fazla hatalı denemeden sonra bekleme süresi dolmadıysa yükselir."""

    def __init__(self, seconds: int) -> None:
        super().__init__(f"Çok fazla hatalı deneme. {seconds} sn bekleyin.")
        self.seconds = seconds


class UnsupportedVaultVersion(RuntimeError):
    """Kasa, bu uygulamadan daha yeni bir Keyora sürümüyle oluşturulmuş."""


class VaultCorrupted(RuntimeError):
    """Parola doğru ama kasa verisi çözülemiyor (bozuk veya değiştirilmiş)."""


def fold(text: str) -> str:
    """Türkçe uyumlu büyük/küçük harf duyarsız karşılaştırma anahtarı.

    str.casefold() 'İ' harfini 'i' yerine 'i̇' (i + nokta) yapar; bu yüzden
    'İş' ile 'iş' eşleşmez. Burada İ, I ve ı hepsi 'i' sayılır — arama ve
    tekillik için biraz daha hoşgörülü ama Türkçe ve İngilizce adlarda doğru.
    """
    text = unicodedata.normalize("NFC", text)
    return text.replace("İ", "i").replace("I", "i").replace("ı", "i").casefold()


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


@dataclass(frozen=True)
class EntrySummary:
    """Listeleme için çözülmüş kayıt — şifre alanı içermez."""
    id: int
    app_name: str
    username: str
    notes: Optional[str]
    category_id: Optional[int]
    favorite: bool
    created_at: str
    updated_at: str


def matches_search(
    entry: EntrySummary, search: str, category_name: Optional[str] = None
) -> bool:
    """Kayıt, arama metnini uygulama adında, kullanıcı adında veya kategori
    adında içeriyor mu?

    Boş arama her kayıtla eşleşir. Karşılaştırma `fold` ile yapılır.
    """
    needle = fold(search.strip())
    if not needle:
        return True
    return (
        needle in fold(entry.app_name)
        or needle in fold(entry.username)
        or (category_name is not None and needle in fold(category_name))
    )


@dataclass(frozen=True)
class Category:
    """Çözülmüş kategori."""
    id: int
    name: str


class Vault:
    """Vault session — Fernet anahtarı yalnızca burada (bellekte) yaşar."""

    def __init__(
        self,
        db: Database,
        clock: Callable[[], float] = time.time,
    ) -> None:
        self.db = db
        self._fernet: Optional[Fernet] = None
        self._clock = clock
        self._changes_at_last_backup = db.total_changes
        self.last_backup_error: Optional[str] = None
        # Bu oturumda v1→v2 geçişi yapıldıysa True (UI kullanıcıyı bilgilendirir)
        self.just_migrated = False

    # ---------- session ----------

    @property
    def is_locked(self) -> bool:
        """Anahtar bellekte değilse True."""
        return self._fernet is None

    @property
    def is_initialized(self) -> bool:
        """Master password kurulmuş mu?"""
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
        fernet = crypto.derive_encryption_key(
            master_password, material.salt_key, material.params
        )
        settings = self._key_settings(material, fernet)
        settings.update({
            "schema_version":    str(SCHEMA_VERSION),
            "auto_lock_minutes": str(auto_lock_minutes),
            "theme":             theme,
        })
        self.db.set_settings_bulk(settings)
        self._fernet = fernet
        self._changes_at_last_backup = self.db.total_changes

    def unlock(self, master_password: str) -> None:
        """Doğru parola ile session'ı açar; gerekiyorsa kasayı yeni şemaya taşır.

        Sıra: bekleme kontrolü → sürüm kontrolü → parola doğrulama →
        anahtar türetme ve kontrol → (v1 ise) yedek + migration → günlük yedek.
        """
        remaining = self.lockout_remaining()
        if remaining > 0:
            raise LoginThrottled(remaining)

        stored_hash = self.db.get_setting("password_hash")
        salt_key_b64 = self.db.get_setting("salt_key")
        if not stored_hash or not salt_key_b64:
            raise RuntimeError("Vault başlatılmamış")

        version = self.db.get_schema_version()
        if version > SCHEMA_VERSION:
            raise UnsupportedVaultVersion(
                "Bu kasa Keyora'nın daha yeni bir sürümüyle oluşturulmuş. "
                "Uygulamayı güncelleyin."
            )

        if not crypto.verify_password(master_password, stored_hash):
            self._register_failure()
            raise InvalidMasterPassword("Master password hatalı")
        self._reset_failures()

        try:
            params = self._kdf_params()
        except ValueError as exc:
            raise VaultCorrupted(f"Kasa ayarları geçersiz: {exc}") from exc
        fernet = crypto.derive_encryption_key(
            master_password, base64.b64decode(salt_key_b64), params
        )
        self._check_key(fernet)

        if version < 2:
            # Migration öncesi yedek ZORUNLU: alınamazsa kasa açılmaz,
            # veri v1 hâliyle olduğu gibi kalır.
            backup.create_backup(
                self.db, kind="pre-migration", directory=backup.local_backup_dir(self.db)
            )
            self._migrate_v1_to_v2(fernet, params)
            self.just_migrated = True
            # Düz metin meta verinin eski kopyaları dosyada kalmasın. VACUUM
            # başarısız olursa (ör. disk dolu) geçiş yine geçerlidir; secure_delete
            # açık olduğu için eski hücreler zaten büyük ölçüde sıfırlanmıştır.
            try:
                self.db.vacuum()
            except sqlite3.Error as exc:
                self.last_backup_error = f"Kasa sıkıştırılamadı (VACUUM): {exc}"

        self._fernet = fernet
        self._changes_at_last_backup = self.db.total_changes
        if backup.auto_backup_due(self.db):
            self._safe_backup("auto")

    def lock(self, *, backup_changes: bool = True) -> None:
        """Session'ı kilitler, Fernet referansını düşürür; değişiklik varsa yedekler.

        Yedek hatası kilitlemeyi asla engellemez. backup_changes=False iken
        (ör. uyku moduna geçerken) diske yazılmaz; yedek bir sonraki kilitte alınır.
        """
        self._fernet = None
        if backup_changes and self.db.total_changes != self._changes_at_last_backup:
            self._safe_backup("auto")

    # ---------- login throttling ----------

    def _failed_attempts(self) -> int:
        try:
            return max(0, int(self.db.get_setting("failed_attempts") or 0))
        except ValueError:
            return 0

    def lockout_remaining(self) -> int:
        """Yeni giriş denemesine kadar beklenecek saniye (0 = hemen denenebilir)."""
        failures = self._failed_attempts()
        if failures < FREE_ATTEMPTS:
            return 0
        delay = min(MAX_DELAY_S, BASE_DELAY_S * 2 ** (failures - FREE_ATTEMPTS))
        try:
            last = float(self.db.get_setting("last_failed_at") or 0)
        except ValueError:
            last = 0.0
        now = self._clock()
        elapsed = now - last
        if elapsed < 0:
            # Saat geri alınmış (ör. ileri ayarlı saat düzeltildi): sayacı şimdiye
            # çek — en fazla bir tam bekleme uygulanır, kullanıcı kilitli kalmaz.
            try:
                self.db.set_setting("last_failed_at", str(now))
            except sqlite3.Error:
                pass  # salt okunur dosya: bu çağrıda yine tam bekleme uygulanır
            elapsed = 0
        return max(0, int(delay - elapsed + 0.999))

    def _register_failure(self) -> None:
        self.db.set_settings_bulk({
            "failed_attempts": str(self._failed_attempts() + 1),
            "last_failed_at":  str(self._clock()),
        })

    def _reset_failures(self) -> None:
        if self._failed_attempts():
            self.db.set_settings_bulk({"failed_attempts": "0", "last_failed_at": "0"})

    # ---------- key material ----------

    def _kdf_params(self) -> crypto.KdfParams:
        """DB'deki Argon2 parametreleri; v1 kasada yoksa v1.0.0'ın sabitleri."""
        raw = {
            "time_cost":   self.db.get_setting("kdf_time_cost"),
            "memory_cost": self.db.get_setting("kdf_memory_cost"),
            "parallelism": self.db.get_setting("kdf_parallelism"),
        }
        if all(v is None for v in raw.values()):
            return V1_KDF
        if any(v is None for v in raw.values()):
            raise ValueError("kdf_* ayarları eksik")
        params = crypto.KdfParams(**{k: int(v) for k, v in raw.items()})
        params.validate()
        return params

    def _key_settings(
        self, material: crypto.KeyMaterial, fernet: Fernet
    ) -> dict[str, str]:
        """Yeni anahtar materyali için settings satırları."""
        return {
            "password_hash":   material.password_hash,
            "salt_verify":     base64.b64encode(material.salt_verify).decode(),
            "salt_key":        base64.b64encode(material.salt_key).decode(),
            "kdf_time_cost":   str(material.params.time_cost),
            "kdf_memory_cost": str(material.params.memory_cost),
            "kdf_parallelism": str(material.params.parallelism),
            "key_check":       crypto.encrypt(fernet, KEY_CHECK_PLAINTEXT).decode("ascii"),
        }

    def _check_key(self, fernet: Fernet) -> None:
        """Türetilen anahtarın bu kasaya ait olduğunu doğrular."""
        token = self.db.get_setting("key_check")
        if token is None:
            return  # v1 kasa — migration her kaydı çözerek doğrular
        try:
            ok = crypto.decrypt(fernet, token.encode("ascii")) == KEY_CHECK_PLAINTEXT
        except InvalidToken:
            ok = False
        if not ok:
            raise VaultCorrupted("Kasa anahtarı doğrulanamadı (ayarlar bozuk olabilir)")

    # ---------- migration ----------

    def _migrate_v1_to_v2(self, fernet: Fernet, params: crypto.KdfParams) -> None:
        """v1 → v2: meta veriyi şifreler, kdf parametrelerini yazar. Tek transaction."""
        entries: list[EntryCipherRow] = []
        for row in self.db.iter_all_entries_raw():
            try:
                crypto.decrypt(fernet, row["encrypted_password"])
            except InvalidToken as exc:
                raise VaultCorrupted(
                    f"Kayıt #{row['id']} çözülemediği için yeni formata geçiş iptal "
                    "edildi. Kasanız DEĞİŞTİRİLMEDİ: Keyora 1.0.0 ile açmaya devam "
                    "edebilirsiniz; geçiş öncesi kopyası 'backups' klasöründe."
                ) from exc
            entries.append((
                row["id"],
                crypto.encrypt(fernet, _as_text(row["app_name"])),
                crypto.encrypt(fernet, _as_text(row["username"])),
                row["encrypted_password"],
                None if row["notes"] is None
                else crypto.encrypt(fernet, _as_text(row["notes"])),
            ))
        categories = [
            (c["id"], crypto.encrypt(fernet, _as_text(c["name"])))
            for c in self.db.list_categories()
        ]
        self.db.rewrite_all(
            entries=entries,
            history=[],
            categories=categories,
            new_settings={
                "schema_version":  "2",
                "kdf_time_cost":   str(params.time_cost),
                "kdf_memory_cost": str(params.memory_cost),
                "kdf_parallelism": str(params.parallelism),
                "key_check": crypto.encrypt(fernet, KEY_CHECK_PLAINTEXT).decode("ascii"),
            },
        )

    # ---------- crypto helpers ----------

    def _require_fernet(self) -> Fernet:
        if self._fernet is None:
            raise VaultLocked("Vault kilitli")
        return self._fernet

    def encrypt(self, plaintext: str) -> bytes:
        """Açık oturumun anahtarıyla şifreler."""
        return crypto.encrypt(self._require_fernet(), plaintext)

    def decrypt(self, ciphertext: bytes) -> str:
        """Açık oturumun anahtarıyla çözer."""
        return crypto.decrypt(self._require_fernet(), ciphertext)

    def _encrypt_opt(self, value: Optional[str]) -> Optional[bytes]:
        return None if value is None else self.encrypt(value)

    def _decrypt_opt(self, value: Optional[bytes]) -> Optional[str]:
        return None if value is None else self.decrypt(value)

    def _summary(self, row) -> EntrySummary:
        return EntrySummary(
            id=row["id"],
            app_name=self.decrypt(row["app_name"]),
            username=self.decrypt(row["username"]),
            notes=self._decrypt_opt(row["notes"]),
            category_id=row["category_id"],
            favorite=bool(row["favorite"]),
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )

    # ---------- entry operations ----------

    def list_entries(
        self,
        *,
        category_id: Optional[int] = None,
        favorites_only: bool = False,
        search: Optional[str] = None,
    ) -> list[EntrySummary]:
        """Çözülmüş, filtrelenmiş ve sıralanmış kayıt listesi.

        Meta veri şifreli olduğundan arama ve sıralama bellekte yapılır.
        """
        self._require_fernet()
        rows = self.db.list_entries(category_id=category_id, favorites_only=favorites_only)
        items = [self._summary(r) for r in rows]
        if search:
            names = {c.id: c.name for c in self.list_categories()}
            items = [
                e for e in items
                if matches_search(e, search, names.get(e.category_id))
            ]
        items.sort(key=lambda e: (not e.favorite, fold(e.app_name), e.id))
        return items

    def get_summary(self, entry_id: int) -> Optional[EntrySummary]:
        """Tek kaydın çözülmüş özeti (şifresiz), yoksa None."""
        row = self.db.get_entry(entry_id)
        return self._summary(row) if row else None

    def get_entry(self, entry_id: int) -> Optional[VaultEntry]:
        """Tek kaydın şifresi dahil çözülmüş hâli (düzenleme için), yoksa None."""
        row = self.db.get_entry(entry_id)
        if row is None:
            return None
        summary = self._summary(row)
        return VaultEntry(
            id=summary.id,
            app_name=summary.app_name,
            username=summary.username,
            password=self.decrypt(row["encrypted_password"]),
            notes=summary.notes,
            category_id=summary.category_id,
            favorite=summary.favorite,
        )

    def add_entry(self, entry: VaultEntry) -> int:
        """Plaintext kaydı şifreleyip DB'ye yazar, yeni id döner."""
        return self.db.add_entry(
            app_name=self.encrypt(entry.app_name),
            username=self.encrypt(entry.username),
            encrypted_password=self.encrypt(entry.password),
            notes=self._encrypt_opt(entry.notes),
            category_id=entry.category_id,
            favorite=entry.favorite,
        )

    def import_entries(self, items: list[tuple[VaultEntry, Optional[str]]]) -> int:
        """Çok sayıda kaydı tek transaction'da ekler (içe aktarma).

        Her öğe (kayıt, kategori adı) çiftidir; kategori adı mevcut bir
        kategoriyle büyük/küçük harf duyarsız eşleşirse ona bağlanır, yoksa
        oluşturulur. Hata olursa hiçbir kayıt ya da kategori eklenmez.
        """
        existing = {fold(c.name): c.id for c in self.list_categories()}
        new_names: list[str] = []
        new_index: dict[str, int] = {}
        rows = []
        for entry, category_name in items:
            category_id, new_idx = entry.category_id, None
            name = (category_name or "").strip()
            if name:
                key = fold(name)
                if key in existing:
                    category_id = existing[key]
                else:
                    if key not in new_index:
                        new_index[key] = len(new_names)
                        new_names.append(name)
                    category_id, new_idx = None, new_index[key]
            rows.append((
                self.encrypt(entry.app_name),
                self.encrypt(entry.username),
                self.encrypt(entry.password),
                self._encrypt_opt(entry.notes),
                category_id,
                new_idx,
                entry.favorite,
            ))
        return self.db.add_bulk(
            new_categories=[self.encrypt(n) for n in new_names], entries=rows
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

        self.db.update_entry(
            entry.id,
            app_name=self.encrypt(entry.app_name),
            username=self.encrypt(entry.username),
            encrypted_password=self.encrypt(entry.password),
            notes=self._encrypt_opt(entry.notes),
            category_id=entry.category_id,
            favorite=entry.favorite,
            password_changed=old_password != entry.password,
        )

    def toggle_favorite(self, entry_id: int) -> None:
        """Kaydın favori durumunu değiştirir."""
        self._require_fernet()
        self.db.toggle_favorite(entry_id)

    def delete_entry(self, entry_id: int) -> None:
        """Kaydı ve geçmişini siler."""
        self._require_fernet()
        self.db.delete_entry(entry_id)

    def reveal_password(self, entry_id: int) -> str:
        """Tek kaydın şifresini çözer (kopyala/göster butonları için)."""
        row = self.db.get_entry(entry_id)
        if row is None:
            raise ValueError(f"Kayıt bulunamadı: id={entry_id}")
        return self.decrypt(row["encrypted_password"])

    def reveal_username(self, entry_id: int) -> str:
        """Tek kaydın kullanıcı adını çözer."""
        row = self.db.get_entry(entry_id)
        if row is None:
            raise ValueError(f"Kayıt bulunamadı: id={entry_id}")
        return self.decrypt(row["username"])

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

    # ---------- categories ----------

    def list_categories(self) -> list[Category]:
        """Çözülmüş kategoriler, ada göre sıralı."""
        cats = [Category(id=c["id"], name=self.decrypt(c["name"]))
                for c in self.db.list_categories()]
        cats.sort(key=lambda c: (fold(c.name), c.id))
        return cats

    def _validate_category_name(self, name: str, exclude_id: Optional[int] = None) -> str:
        name = name.strip()
        if not name:
            raise ValueError("Kategori adı boş olamaz")
        for cat in self.list_categories():
            if cat.id != exclude_id and fold(cat.name) == fold(name):
                raise ValueError(f"'{name}' adında bir kategori zaten var")
        return name

    def add_category(self, name: str) -> int:
        """Kategori ekler (aynı ad tekrar eklenemez), yeni id döner."""
        name = self._validate_category_name(name)
        return self.db.add_category(self.encrypt(name))

    def rename_category(self, category_id: int, new_name: str) -> None:
        """Kategoriyi yeniden adlandırır."""
        new_name = self._validate_category_name(new_name, exclude_id=category_id)
        self.db.rename_category(category_id, self.encrypt(new_name))

    def delete_category(self, category_id: int) -> None:
        """Kategoriyi siler; kayıtlar kategorisiz kalır."""
        self._require_fernet()
        self.db.delete_category(category_id)

    # ---------- master password change ----------

    def change_master_password(self, old_password: str, new_password: str) -> None:
        """Master password'ü değiştirir. Tüm şifreli alanlar yeni anahtarla yazılır.

        İşlem atomiktir: rewrite transaction'ı başarısız olursa eski anahtar geçerli kalır.
        """
        if self.is_locked:
            raise VaultLocked("Vault kilitli")

        stored_hash = self.db.get_setting("password_hash")
        if not stored_hash or not crypto.verify_password(old_password, stored_hash):
            raise InvalidMasterPassword("Eski master password hatalı")

        old_fernet = self._require_fernet()
        new_material = crypto.setup_new_vault(new_password)
        new_fernet = crypto.derive_encryption_key(
            new_password, new_material.salt_key, new_material.params
        )

        def rekey(blob: bytes) -> bytes:
            return crypto.encrypt(new_fernet, crypto.decrypt(old_fernet, blob))

        entries: list[EntryCipherRow] = [
            (
                row["id"],
                rekey(row["app_name"]),
                rekey(row["username"]),
                rekey(row["encrypted_password"]),
                None if row["notes"] is None else rekey(row["notes"]),
            )
            for row in self.db.iter_all_entries_raw()
        ]
        history = [(r["id"], rekey(r["encrypted_password"]))
                   for r in self.db.iter_all_history_blobs()]
        categories = [(c["id"], rekey(c["name"])) for c in self.db.list_categories()]

        self.db.rewrite_all(
            entries=entries,
            history=history,
            categories=categories,
            new_settings=self._key_settings(new_material, new_fernet),
        )
        self._fernet = new_fernet

    # ---------- backup ----------

    def _safe_backup(self, kind: str) -> Optional[Path]:
        """Yedek alır; hata uygulamayı durdurmaz, last_backup_error'a yazılır."""
        try:
            path = backup.create_backup(self.db, kind=kind)
        except (OSError, sqlite3.Error) as exc:  # disk dolu → sqlite3.OperationalError
            self.last_backup_error = f"Yedek alınamadı: {exc}"
            return None
        self.last_backup_error = None
        self._changes_at_last_backup = self.db.total_changes
        return path

    def backup_now(self) -> Path:
        """Kullanıcının istediği anlık yedek. Hata yükseltir."""
        self._require_fernet()
        path = backup.create_backup(self.db, kind="manual")
        self._changes_at_last_backup = self.db.total_changes
        return path

    def export_backup(self, dest: Path) -> None:
        """Şifreli kasa kopyasını kullanıcının seçtiği yola yazar."""
        self._require_fernet()
        self.db.backup_to(Path(dest))

    def restore_backup(self, src: Path) -> int:
        """Yedeği geri yükler ve kasayı kilitler (yedeğin parolası farklı olabilir)."""
        self._require_fernet()
        version = backup.restore_backup(self.db, Path(src))
        self._fernet = None
        self._changes_at_last_backup = self.db.total_changes
        return version

    def list_backups(self) -> list[backup.BackupInfo]:
        """Yedek klasöründeki yedekler (en yeni önce)."""
        return backup.list_backups(backup.backup_dir(self.db))

    def list_plaintext_backups(self) -> list[backup.BackupInfo]:
        """v1 biçimindeki geçiş öncesi yedekler.

        Bunlarda şifreler şifreli ama uygulama adı, kullanıcı adı, notlar ve
        kategori adları DÜZ METİNDİR. Yalnızca Keyora 1.0.0'a dönüş için gerekir.
        """
        return [b for b in backup.list_backups(backup.local_backup_dir(self.db))
                if b.kind == "pre-migration"]

    def delete_plaintext_backups(self) -> int:
        """Geçiş öncesi (düz metin meta verili) yedekleri siler, silinen sayısını döner."""
        self._require_fernet()
        removed = 0
        for info in self.list_plaintext_backups():
            info.path.unlink(missing_ok=True)
            removed += 1
        return removed

    def get_backup_dir(self) -> Path:
        """Otomatik yedek klasörü."""
        return backup.backup_dir(self.db)

    def set_backup_dir(self, directory: Optional[Path]) -> None:
        """Yedek klasörünü ayarlar; None varsayılana döner."""
        if directory is None:
            self.db.delete_setting("backup_dir")
            return
        directory = Path(directory)
        directory.mkdir(parents=True, exist_ok=True)
        self.db.set_setting("backup_dir", str(directory))

    def get_backup_keep(self) -> int:
        """Saklanacak otomatik yedek sayısı."""
        return backup.get_keep(self.db)

    def set_backup_keep(self, count: int) -> None:
        """Saklanacak otomatik yedek sayısını ayarlar."""
        if not backup.MIN_KEEP <= count <= backup.MAX_KEEP:
            raise ValueError(
                f"Yedek sayısı {backup.MIN_KEEP}-{backup.MAX_KEEP} arasında olmalı"
            )
        self.db.set_setting("backup_keep", str(count))

    # ---------- settings ----------

    def verify_current_password(self, password: str) -> bool:
        """Açık vault için master password doğrulama (hassas işlemler öncesi)."""
        stored_hash = self.db.get_setting("password_hash")
        if not stored_hash:
            return False
        return crypto.verify_password(password, stored_hash)

    def get_auto_lock_minutes(self) -> int:
        """Boşta kalınca kilitlenme süresi (dk)."""
        raw = self.db.get_setting("auto_lock_minutes")
        try:
            return max(1, int(raw)) if raw else 5
        except ValueError:
            return 5

    def set_auto_lock_minutes(self, minutes: int) -> None:
        """Boşta kalınca kilitlenme süresini ayarlar."""
        if minutes < 1:
            raise ValueError("Auto-lock en az 1 dakika olmalı")
        self.db.set_setting("auto_lock_minutes", str(minutes))

    def get_theme(self) -> str:
        """Kayıtlı tema adı."""
        return self.db.get_setting("theme") or "dark"

    def set_theme(self, name: str) -> None:
        """Temayı kaydeder."""
        self.db.set_setting("theme", name)

    def get_hide_from_capture(self) -> bool:
        """Pencereler ekran görüntüsü/paylaşımından gizlensin mi (varsayılan: evet)."""
        return self.db.get_setting("hide_from_capture") != "0"

    def set_hide_from_capture(self, enabled: bool) -> None:
        """Ekran görüntüsünden gizleme ayarını kaydeder."""
        self.db.set_setting("hide_from_capture", "1" if enabled else "0")


def _as_text(value: object) -> str:
    """v1 düz metin alanını str'ye çevirir; zaten bayt ise migration'ı durdurur."""
    if isinstance(value, str):
        return value
    raise VaultCorrupted("v1 kasada beklenmeyen şifreli alan bulundu; migration iptal")
