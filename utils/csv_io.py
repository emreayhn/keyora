"""CSV içe/dışa aktarım — düz metin uyarısı UI katmanında verilir."""
from __future__ import annotations

import csv
from pathlib import Path
from typing import Iterable

from core.vault import Vault, VaultEntry

CSV_HEADERS = ["app_name", "username", "password", "category", "notes", "favorite"]


def export_csv(vault: Vault, path: str | Path) -> int:
    """Tüm kayıtları düz metin CSV'ye yazar, yazılan satır sayısını döner."""
    if vault.is_locked:
        raise RuntimeError("Vault kilitli")

    categories = {c["id"]: c["name"] for c in vault.db.list_categories()}
    rows = vault.db.list_entries()

    count = 0
    with open(path, "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=CSV_HEADERS)
        writer.writeheader()
        for row in rows:
            password = vault.decrypt(row["encrypted_password"])
            writer.writerow({
                "app_name": row["app_name"],
                "username": row["username"],
                "password": password,
                "category": categories.get(row["category_id"], ""),
                "notes":    row["notes"] or "",
                "favorite": "1" if row["favorite"] else "0",
            })
            count += 1
    return count


def import_csv(vault: Vault, path: str | Path) -> int:
    """CSV'den kayıt yükler. Kategoriler gerektiğinde oluşturulur."""
    if vault.is_locked:
        raise RuntimeError("Vault kilitli")

    existing_categories = {c["name"]: c["id"] for c in vault.db.list_categories()}
    count = 0

    with open(path, "r", encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        missing = [h for h in ("app_name", "username", "password") if h not in (reader.fieldnames or [])]
        if missing:
            raise ValueError(f"CSV başlıkları eksik: {', '.join(missing)}")

        for raw in reader:
            app_name = (raw.get("app_name") or "").strip()
            username = (raw.get("username") or "").strip()
            password = raw.get("password") or ""
            if not app_name or not username or not password:
                continue

            cat_name = (raw.get("category") or "").strip()
            category_id: int | None = None
            if cat_name:
                if cat_name not in existing_categories:
                    existing_categories[cat_name] = vault.db.add_category(cat_name)
                category_id = existing_categories[cat_name]

            entry = VaultEntry(
                id=None,
                app_name=app_name,
                username=username,
                password=password,
                notes=(raw.get("notes") or "").strip() or None,
                category_id=category_id,
                favorite=(raw.get("favorite") or "").strip() in {"1", "true", "True"},
            )
            vault.add_entry(entry)
            count += 1

    return count
