"""Keyora yedekleme — otomatik, döner (son N kopya), şifreli yedekler.

Yedek, kasa dosyasının SQLite backup API ile alınmış tutarlı bir kopyasıdır.
Kasa zaten şifreli olduğundan (v2: meta veri dahil) yedek de şifrelidir ve
açmak için o anki master password gerekir.

Dosya adı: keyora-YYYYMMDD-HHMMSS[-N]-<tür>.db
  auto          — oturum açılışında (24 saatte bir) ve değişiklik sonrası kilitte
  manual        — kullanıcı "Şimdi yedekle" dediğinde
  pre-migration — şema geçişinden hemen önce (döndürülmez, eski sürüme dönüş için)
  pre-restore   — geri yüklemeden hemen önce mevcut kasa (döndürülmez)
Yalnızca `auto` yedekler döndürülür; diğerleri kullanıcı silene kadar kalır.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

from core.database import Database, DatabaseError, SCHEMA_VERSION

BACKUP_DIRNAME = "backups"
DEFAULT_KEEP = 10
MIN_KEEP = 1
MAX_KEEP = 100
AUTO_INTERVAL = timedelta(hours=24)

KINDS = ("auto", "manual", "pre-migration", "pre-restore")
ROTATED_KINDS = ("auto",)

_NAME_RE = re.compile(
    r"^keyora-(?P<stamp>\d{8}-\d{6})(?:-(?P<seq>\d+))?-(?P<kind>"
    + "|".join(re.escape(k) for k in KINDS)
    + r")\.db$"
)


@dataclass(frozen=True)
class BackupInfo:
    """Yedek klasöründeki tek bir yedek dosyası."""
    path: Path
    kind: str
    created: datetime


def local_backup_dir(db: Database) -> Path:
    """Kasanın yanındaki varsayılan yedek klasörü."""
    return db.path.parent / BACKUP_DIRNAME


def backup_dir(db: Database) -> Path:
    """Otomatik yedeklerin yazıldığı klasör (ayar yoksa kasanın yanı)."""
    custom = db.get_setting("backup_dir")
    return Path(custom) if custom else local_backup_dir(db)


def get_keep(db: Database) -> int:
    """Saklanacak otomatik yedek sayısı."""
    raw = db.get_setting("backup_keep")
    try:
        value = int(raw) if raw else DEFAULT_KEEP
    except ValueError:
        return DEFAULT_KEEP
    return min(MAX_KEEP, max(MIN_KEEP, value))


def list_backups(directory: Path) -> list[BackupInfo]:
    """Klasördeki Keyora yedekleri, en yeniden en eskiye."""
    if not directory.is_dir():
        return []
    found: list[BackupInfo] = []
    for path in directory.iterdir():
        match = _NAME_RE.match(path.name)
        if not match or not path.is_file():
            continue
        created = datetime.strptime(match["stamp"], "%Y%m%d-%H%M%S")
        found.append(BackupInfo(path=path, kind=match["kind"], created=created))
    found.sort(key=lambda b: (b.created, b.path.name), reverse=True)
    return found


def _next_name(directory: Path, kind: str, now: datetime) -> Path:
    stamp = now.strftime("%Y%m%d-%H%M%S")
    candidate = directory / f"keyora-{stamp}-{kind}.db"
    seq = 1
    while candidate.exists():
        seq += 1
        candidate = directory / f"keyora-{stamp}-{seq}-{kind}.db"
    return candidate


def create_backup(
    db: Database,
    kind: str = "auto",
    directory: Optional[Path] = None,
    now: Optional[datetime] = None,
) -> Path:
    """Yedek alır, gerekirse eski otomatik yedekleri döndürür, yolu döner.

    Disk/klasör hatasında OSError yükselir; çağıran karar verir.
    """
    if kind not in KINDS:
        raise ValueError(f"Bilinmeyen yedek türü: {kind}")
    directory = Path(directory) if directory else backup_dir(db)
    directory.mkdir(parents=True, exist_ok=True)
    dest = _next_name(directory, kind, now or datetime.now())
    db.backup_to(dest)
    if kind in ROTATED_KINDS:
        rotate(directory, get_keep(db))
    return dest


def rotate(directory: Path, keep: int) -> list[Path]:
    """En yeni `keep` otomatik yedek dışındakileri siler, silinenleri döner."""
    autos = [b for b in list_backups(directory) if b.kind in ROTATED_KINDS]
    removed: list[Path] = []
    for info in autos[keep:]:
        info.path.unlink(missing_ok=True)
        removed.append(info.path)
    return removed


def auto_backup_due(db: Database, now: Optional[datetime] = None) -> bool:
    """Son otomatik yedek AUTO_INTERVAL'dan eskiyse (ya da hiç yoksa) True."""
    autos = [b for b in list_backups(backup_dir(db)) if b.kind == "auto"]
    if not autos:
        return True
    return (now or datetime.now()) - autos[0].created >= AUTO_INTERVAL


def restore_backup(db: Database, src: Path) -> int:
    """Yedeği geri yükler; önce mevcut kasanın `pre-restore` yedeğini alır.

    Dönen değer yedeğin şema sürümüdür. Eski (v1) bir yedekse sonraki
    unlock sırasında otomatik olarak taşınır.
    """
    src = Path(src)
    if src.resolve() == db.path.resolve():
        raise DatabaseError("Açık olan kasa kendi üzerine geri yüklenemez")
    version = Database.inspect_backup(src)
    if version > SCHEMA_VERSION:
        raise DatabaseError(
            "Bu yedek Keyora'nın daha yeni bir sürümüyle alınmış; "
            "önce uygulamayı güncelleyin."
        )
    create_backup(db, kind="pre-restore", directory=local_backup_dir(db))
    db.restore_from(src)
    return version


__all__ = [
    "BackupInfo",
    "DEFAULT_KEEP",
    "MIN_KEEP",
    "MAX_KEEP",
    "local_backup_dir",
    "backup_dir",
    "get_keep",
    "list_backups",
    "create_backup",
    "rotate",
    "auto_backup_due",
    "restore_backup",
]
