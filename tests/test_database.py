"""core/database.py için testler — geçici dosya kullanır."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest

from core.database import Database, HISTORY_LIMIT


@pytest.fixture
def db(tmp_path):
    path = tmp_path / "test.db"
    instance = Database(path)
    yield instance
    instance.close()


def test_schema_created(db: Database):
    assert db.is_initialized() is False


def test_settings_roundtrip(db: Database):
    db.set_setting("theme", "dark")
    assert db.get_setting("theme") == "dark"
    db.set_setting("theme", "light")  # upsert
    assert db.get_setting("theme") == "light"


def test_add_and_list_entry(db: Database):
    entry_id = db.add_entry(
        app_name="GitHub", username="ada",
        encrypted_password=b"x1", notes=None, category_id=None,
    )
    assert entry_id > 0
    entries = db.list_entries()
    assert len(entries) == 1
    assert entries[0]["app_name"] == "GitHub"


def test_password_history_rotation(db: Database):
    entry_id = db.add_entry(
        app_name="App", username="u",
        encrypted_password=b"v0", notes=None, category_id=None,
    )
    # 7 güncelleme: history sadece en son 5'i tutmalı (HISTORY_LIMIT)
    for i in range(1, 8):
        db.update_entry(
            entry_id,
            app_name="App", username="u",
            encrypted_password=f"v{i}".encode(),
            notes=None, category_id=None, favorite=False,
            password_changed=True,
        )
    history = db.list_history(entry_id)
    assert len(history) == HISTORY_LIMIT


def test_category_delete_sets_entry_null(db: Database):
    cat_id = db.add_category("Work")
    entry_id = db.add_entry(
        app_name="Slack", username="me",
        encrypted_password=b"e", notes=None, category_id=cat_id,
    )
    db.delete_category(cat_id)
    row = db.get_entry(entry_id)
    assert row["category_id"] is None
