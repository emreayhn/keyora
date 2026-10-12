"""Şifre sağlığı raporu — zayıf, tekrar kullanılan ve eskimiş şifreler.

Tamamen çevrimdışı: yalnızca açık kasadaki veriye bakar, hiçbir şey dışarı
gönderilmez. Rapor şifrelerin kendisini içermez; yalnızca hangi kaydın neden
listelendiğini taşır.
"""
from __future__ import annotations

import hashlib
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional

from cryptography.fernet import InvalidToken

from core.vault import EntrySummary, Vault
from utils.password_gen import MIN_LENGTH, estimate_strength

OLD_AFTER_DAYS = 365
_SQLITE_TS = "%Y-%m-%d %H:%M:%S"


@dataclass(frozen=True)
class HealthIssue:
    """Rapordaki tek bir satır: kayıt + neden listelendiği."""
    entry: EntrySummary
    detail: str


@dataclass(frozen=True)
class HealthReport:
    """Kasanın şifre sağlığı özeti."""
    total: int
    weak: list[HealthIssue] = field(default_factory=list)
    reused: list[list[EntrySummary]] = field(default_factory=list)
    old: list[HealthIssue] = field(default_factory=list)
    unreadable: list[HealthIssue] = field(default_factory=list)

    @property
    def problem_ids(self) -> set[int]:
        """En az bir sorunu olan kayıtların id'leri."""
        ids = {i.entry.id for i in self.weak} | {i.entry.id for i in self.old}
        ids.update(i.entry.id for i in self.unreadable)
        for group in self.reused:
            ids.update(e.id for e in group)
        return ids

    @property
    def healthy(self) -> int:
        """Hiçbir sorunu olmayan kayıt sayısı."""
        return self.total - len(self.problem_ids)

    @property
    def score(self) -> int:
        """0-100 arası puan: sorunsuz kayıtların yüzdesi (boş kasa = 100)."""
        if self.total == 0:
            return 100
        return round(100 * self.healthy / self.total)


def _parse_ts(value: Optional[str]) -> Optional[datetime]:
    """SQLite zaman damgası (UTC, 'YYYY-MM-DD HH:MM:SS'); ISO 'T' biçimi de kabul."""
    if not value:
        return None
    try:
        # 3.11+ fromisoformat boşluk ayırıcıyı ve ofseti de anlar
        parsed = datetime.fromisoformat(value)
    except ValueError:
        try:
            return datetime.strptime(value[:19], _SQLITE_TS)
        except ValueError:
            return None
    if parsed.tzinfo is not None:
        parsed = parsed.astimezone(timezone.utc).replace(tzinfo=None)
    return parsed


def _weak_reason(password: str) -> Optional[str]:
    """Şifre zayıfsa kullanıcıya gösterilecek neden, değilse None."""
    if estimate_strength(password) != "zayıf":
        return None
    if len(password) < MIN_LENGTH:
        return f"{len(password)} karakter — en az {MIN_LENGTH} önerilir"
    return "Çok az karakter çeşidi — büyük/küçük harf, rakam ve sembol karıştırın"


def analyze(
    vault: Vault,
    *,
    now: Optional[datetime] = None,
    old_after_days: int = OLD_AFTER_DAYS,
) -> HealthReport:
    """Açık kasayı tarar ve sağlık raporu üretir.

    `now` ve tarihler UTC, saat dilimi bilgisi olmadan karşılaştırılır
    (SQLite datetime('now') UTC yazar).
    """
    now = now or datetime.now(timezone.utc).replace(tzinfo=None)
    entries = vault.list_entries()
    last_changes = vault.db.last_password_changes()

    weak: list[HealthIssue] = []
    unreadable: list[HealthIssue] = []
    old_by_age: list[tuple[int, HealthIssue]] = []
    # Tekrar tespiti için şifrenin kendisi değil özeti anahtar olarak tutulur
    groups: dict[bytes, list[EntrySummary]] = defaultdict(list)

    for entry in entries:
        try:
            password = vault.reveal_password(entry.id)
        except InvalidToken:
            # Tek bozuk kayıt tüm raporu düşürmesin; ayrıca listelenir
            unreadable.append(HealthIssue(
                entry,
                "Şifre çözülemedi — kayıt bozulmuş olabilir. Ana pencereden silip "
                "yeniden ekleyin ya da Ayarlar → Yedekleme'den yedeğe dönün.",
            ))
            password = None
        if password is not None:
            groups[hashlib.sha256(password.encode("utf-8")).digest()].append(entry)
            reason = _weak_reason(password)
            if reason:
                weak.append(HealthIssue(entry, reason))
            del password

        changed = _parse_ts(last_changes.get(entry.id)) or _parse_ts(entry.created_at)
        if changed is not None:
            age = (now - changed).days
            if age >= old_after_days:
                old_by_age.append((age, HealthIssue(entry, f"{age} gündür değişmedi")))

    reused = [g for g in groups.values() if len(g) > 1]
    reused.sort(key=lambda g: (-len(g), g[0].app_name.casefold()))
    old_by_age.sort(key=lambda pair: pair[0], reverse=True)  # en eski önce
    old = [issue for _, issue in old_by_age]

    return HealthReport(
        total=len(entries), weak=weak, reused=reused, old=old, unreadable=unreadable
    )
