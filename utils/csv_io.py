"""CSV içe/dışa aktarım — düz metin uyarısı UI katmanında verilir."""
from __future__ import annotations

import csv
from pathlib import Path
from core.vault import Vault

CSV_HEADERS = ["app_name", "username", "password", "category", "notes", "favorite"]


def export_csv(vault: Vault, path: str | Path) -> int:
    """Tüm kayıtları düz metin CSV'ye yazar, yazılan satır sayısını döner."""
    if vault.is_locked:
        raise RuntimeError("Vault kilitli")

    categories = {c.id: c.name for c in vault.list_categories()}
    entries = vault.list_entries()

    count = 0
    with open(path, "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=CSV_HEADERS)
        writer.writeheader()
        for entry in entries:
            writer.writerow({
                "app_name": entry.app_name,
                "username": entry.username,
                "password": vault.reveal_password(entry.id),
                "category": categories.get(entry.category_id, ""),
                "notes":    entry.notes or "",
                "favorite": "1" if entry.favorite else "0",
            })
            count += 1
    return count


def import_csv(vault: Vault, path: str | Path) -> int:
    """CSV'den kayıt yükler (Keyora ya da desteklenen başka bir biçim).

    Ayrıntılı akış ve önizleme için utils/importers.py kullanılır; bu fonksiyon
    geriye dönük uyumluluk için doğrudan içe aktarır ve eklenen sayıyı döner.
    """
    from utils import importers

    return importers.apply(vault, importers.preview(vault, path))
