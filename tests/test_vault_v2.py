"""v1.1 vault özellikleri: meta veri şifreleme, arama, kategoriler,
saklanan KDF parametreleri ve yanlış giriş beklemesi."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest

from core import crypto
from core.database import Database
from core.vault import (
    BASE_DELAY_S, FREE_ATTEMPTS, MAX_DELAY_S,
    InvalidMasterPassword, LoginThrottled, Vault, VaultCorrupted, VaultEntry,
)

MASTER = "master-pass-1234"


class FakeClock:
    """Testte zamanı elle ilerletmek için."""

    def __init__(self) -> None:
        self.now = 1_000_000.0

    def __call__(self) -> float:
        return self.now


@pytest.fixture
def vault(tmp_path):
    db = Database(tmp_path / "v.db")
    v = Vault(db)
    v.initialize(MASTER)
    yield v
    db.close()


def _add(vault: Vault, app: str, user: str = "u", fav: bool = False,
         notes: str | None = None, cat: int | None = None) -> int:
    return vault.add_entry(VaultEntry(
        id=None, app_name=app, username=user, password="pw-" + app,
        notes=notes, category_id=cat, favorite=fav,
    ))


# ---------- meta veri şifreleme ----------

def test_metadata_is_encrypted_at_rest(vault: Vault):
    cat = vault.add_category("Bankacılık")
    entry_id = _add(vault, "ZiraatMobil", "musteri42", notes="PIN kartta", cat=cat)

    row = vault.db.get_entry(entry_id)
    for col in ("app_name", "username", "notes"):
        assert isinstance(row[col], bytes)
        assert b"Ziraat" not in row[col] and b"musteri42" not in row[col]
    assert vault.db.list_categories()[0]["name"] != "Bankacılık"

    raw = Path(vault.db.path).read_bytes()
    for needle in ("ZiraatMobil", "musteri42", "PIN kartta", "Bankacılık"):
        assert needle.encode("utf-8") not in raw


def test_get_entry_and_summary_roundtrip(vault: Vault):
    entry_id = _add(vault, "Slack", "ada", notes="iş")
    full = vault.get_entry(entry_id)
    assert (full.app_name, full.username, full.password, full.notes) == \
        ("Slack", "ada", "pw-Slack", "iş")
    summary = vault.get_summary(entry_id)
    assert summary.app_name == "Slack" and not hasattr(summary, "password")
    assert vault.reveal_username(entry_id) == "ada"


def test_update_entry_reencrypts_metadata(vault: Vault):
    entry_id = _add(vault, "Eski")
    entry = vault.get_entry(entry_id)
    entry.app_name = "Yeni"
    entry.notes = "not"
    vault.update_entry(entry)
    assert vault.get_summary(entry_id).app_name == "Yeni"
    assert vault.get_summary(entry_id).notes == "not"
    assert vault.reveal_history(entry_id) == []  # şifre değişmedi → history yok


def test_list_requires_unlocked(vault: Vault):
    _add(vault, "X")
    vault.lock()
    with pytest.raises(Exception):
        vault.list_entries()


# ---------- arama / sıralama ----------

def test_search_is_case_insensitive_and_unicode(vault: Vault):
    _add(vault, "İnstagram", "ayşe")
    _add(vault, "GitHub", "ADA")
    _add(vault, "Gmail", "bob")
    assert [e.app_name for e in vault.list_entries(search="git")] == ["GitHub"]
    assert [e.app_name for e in vault.list_entries(search="ada")] == ["GitHub"]
    assert [e.app_name for e in vault.list_entries(search="AYŞE")] == ["İnstagram"]


def test_sort_favorites_first_then_name(vault: Vault):
    _add(vault, "beta")
    _add(vault, "Alpha")
    _add(vault, "zeta", fav=True)
    assert [e.app_name for e in vault.list_entries()] == ["zeta", "Alpha", "beta"]
    assert [e.app_name for e in vault.list_entries(favorites_only=True)] == ["zeta"]


def test_filter_by_category(vault: Vault):
    cat = vault.add_category("İş")
    _add(vault, "Jira", cat=cat)
    _add(vault, "Netflix")
    assert [e.app_name for e in vault.list_entries(category_id=cat)] == ["Jira"]


# ---------- kategoriler ----------

def test_category_names_must_be_unique_case_insensitive(vault: Vault):
    vault.add_category("Work")
    with pytest.raises(ValueError):
        vault.add_category("  work ")
    with pytest.raises(ValueError):
        vault.add_category("   ")


def test_rename_category(vault: Vault):
    a = vault.add_category("A")
    vault.add_category("B")
    vault.rename_category(a, "a")  # kendi adının harf farkı serbest
    with pytest.raises(ValueError):
        vault.rename_category(a, "B")
    assert [c.name for c in vault.list_categories()] == ["a", "B"]


# ---------- master password değişimi ----------

def test_change_master_password_reencrypts_everything(tmp_path):
    db = Database(tmp_path / "rekey.db")
    v = Vault(db)
    v.initialize("old-pass-1234")
    cat = v.add_category("Gizli")
    e = _add(v, "Banka", "ben", notes="not", cat=cat)
    old_row = dict(db.get_entry(e))
    old_cat = db.list_categories()[0]["name"]

    v.change_master_password("old-pass-1234", "new-pass-5678")
    new_row = db.get_entry(e)
    for col in ("app_name", "username", "notes", "encrypted_password"):
        assert new_row[col] != old_row[col]
    assert db.list_categories()[0]["name"] != old_cat

    v.lock()
    v.unlock("new-pass-5678")
    assert v.get_entry(e).notes == "not"
    assert v.list_categories()[0].name == "Gizli"
    db.close()


# ---------- KDF parametreleri ----------

def test_kdf_params_are_stored(vault: Vault):
    assert vault.db.get_setting("kdf_time_cost") == str(crypto.ARGON2_TIME_COST)
    assert vault.db.get_setting("kdf_memory_cost") == str(crypto.ARGON2_MEMORY_COST)
    assert vault.db.get_setting("kdf_parallelism") == str(crypto.ARGON2_PARALLELISM)
    assert vault.db.get_setting("schema_version") == "2"


def test_tampered_kdf_params_are_detected(vault: Vault):
    vault.lock()
    vault.db.set_setting("kdf_time_cost", "4")  # geçerli aralıkta ama yanlış
    with pytest.raises(VaultCorrupted):
        vault.unlock(MASTER)
    assert vault.is_locked


def test_downgraded_kdf_params_are_refused(vault: Vault):
    vault.lock()
    vault.db.set_setting("kdf_memory_cost", "1024")
    with pytest.raises(VaultCorrupted):
        vault.unlock(MASTER)


def test_kdf_params_validate_bounds():
    with pytest.raises(ValueError):
        crypto.KdfParams(time_cost=1).validate()
    with pytest.raises(ValueError):
        crypto.KdfParams(memory_cost=crypto.ARGON2_MAX_MEMORY_COST + 1).validate()
    crypto.DEFAULT_KDF.validate()


def test_verify_password_rejects_weak_embedded_params():
    from argon2 import PasswordHasher
    weak = PasswordHasher(time_cost=1, memory_cost=8, parallelism=1).hash("pw")
    assert crypto.verify_password("pw", weak) is False


# ---------- yanlış giriş beklemesi ----------

def test_login_throttle_grows_and_resets(tmp_path):
    clock = FakeClock()
    db = Database(tmp_path / "t.db")
    v = Vault(db, clock=clock)
    v.initialize(MASTER)
    v.lock()

    for _ in range(FREE_ATTEMPTS):
        assert v.lockout_remaining() == 0
        with pytest.raises(InvalidMasterPassword):
            v.unlock("yanlış")
    assert v.lockout_remaining() == BASE_DELAY_S

    # Bekleme dolmadan doğru parola bile denenemez
    with pytest.raises(LoginThrottled):
        v.unlock(MASTER)

    clock.now += BASE_DELAY_S
    with pytest.raises(InvalidMasterPassword):
        v.unlock("yanlış")
    assert v.lockout_remaining() == BASE_DELAY_S * 2

    clock.now += BASE_DELAY_S * 2
    v.unlock(MASTER)
    assert v.lockout_remaining() == 0
    assert db.get_setting("failed_attempts") == "0"
    db.close()


def test_login_throttle_is_capped_and_survives_restart(tmp_path):
    clock = FakeClock()
    path = tmp_path / "t.db"
    db = Database(path)
    db_vault = Vault(db, clock=clock)
    db_vault.initialize(MASTER)
    db.set_settings_bulk({"failed_attempts": "50", "last_failed_at": str(clock.now)})
    db.close()

    db2 = Database(path)
    v2 = Vault(db2, clock=clock)
    assert v2.lockout_remaining() == MAX_DELAY_S
    db2.close()


def test_clock_moved_back_applies_at_most_one_full_delay(tmp_path):
    """İleri ayarlı saat düzeltilince kullanıcı süresiz kilitli kalmamalı."""
    clock = FakeClock()
    db = Database(tmp_path / "t.db")
    v = Vault(db, clock=clock)
    v.initialize(MASTER)
    v.lock()
    clock.now += 3 * 3600  # saat 3 saat ileride
    for _ in range(FREE_ATTEMPTS):
        with pytest.raises(InvalidMasterPassword):
            v.unlock("yanlış")

    clock.now -= 3 * 3600  # NTP saati düzeltti
    assert v.lockout_remaining() == BASE_DELAY_S  # kısalmaz…
    clock.now += BASE_DELAY_S
    assert v.lockout_remaining() == 0  # …ama bir bekleme sonra açılır
    v.unlock(MASTER)
    db.close()


def test_v1_vault_without_kdf_settings_uses_fixed_v1_params(vault: Vault, monkeypatch):
    from core import vault as vault_module
    for key in ("kdf_time_cost", "kdf_memory_cost", "kdf_parallelism"):
        vault.db.delete_setting(key)
    # Varsayılan ileride yükseltilse bile v1 kasa v1 parametreleriyle açılır
    monkeypatch.setattr(crypto, "DEFAULT_KDF", crypto.KdfParams(time_cost=4))
    assert vault._kdf_params() == vault_module.V1_KDF
