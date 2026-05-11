"""CSV içe/dışa aktarım testleri."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest

from core.database import Database
from core.vault import Vault, VaultEntry
from utils import csv_io


@pytest.fixture
def vault(tmp_path):
    db = Database(tmp_path / "csv.db")
    v = Vault(db)
    v.initialize("master-pass-1234")
    yield v
    db.close()


def test_export_then_import_roundtrip(vault: Vault, tmp_path):
    cat_id = vault.db.add_category("Work")
    vault.add_entry(VaultEntry(
        id=None, app_name="GitHub", username="ada",
        password="hunter2!@", notes="iş hesabı",
        category_id=cat_id, favorite=True,
    ))
    vault.add_entry(VaultEntry(
        id=None, app_name="Mail", username="ada@x",
        password="başka-şifre", notes=None, category_id=None,
    ))

    csv_path = tmp_path / "export.csv"
    written = csv_io.export_csv(vault, csv_path)
    assert written == 2
    assert csv_path.exists()

    # Yeni vault'a import et
    db2 = Database(tmp_path / "imp.db")
    v2 = Vault(db2)
    v2.initialize("yeni-master-9999")
    imported = csv_io.import_csv(v2, csv_path)
    assert imported == 2

    apps = sorted(r["app_name"] for r in v2.db.list_entries())
    assert apps == ["GitHub", "Mail"]

    # Kategori de yaratılmış olmalı
    cats = [c["name"] for c in v2.db.list_categories()]
    assert "Work" in cats

    # Şifre roundtrip
    github = next(r for r in v2.db.list_entries() if r["app_name"] == "GitHub")
    assert v2.decrypt(github["encrypted_password"]) == "hunter2!@"
    assert github["favorite"] == 1

    db2.close()


def test_import_skips_rows_with_missing_fields(vault: Vault, tmp_path):
    csv_path = tmp_path / "partial.csv"
    csv_path.write_text(
        "app_name,username,password,category,notes,favorite\n"
        "A,u,p,,n,0\n"
        ",noapp,p,,,\n"          # app_name eksik → atlanmalı
        "B,,p,,,\n"               # username eksik → atlanmalı
        "C,u,,,,\n",              # password eksik → atlanmalı
        encoding="utf-8",
    )
    count = csv_io.import_csv(vault, csv_path)
    assert count == 1


def test_import_rejects_missing_required_headers(vault: Vault, tmp_path):
    csv_path = tmp_path / "bad.csv"
    csv_path.write_text("foo,bar\n1,2\n", encoding="utf-8")
    with pytest.raises(ValueError):
        csv_io.import_csv(vault, csv_path)
