"""Şifre sağlığı raporu testleri."""
from __future__ import annotations

import dataclasses
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest

from core import health
from core.database import Database
from core.vault import Vault, VaultEntry

STRONG_A = "Xk9#mPq2$vL7nR4!wZ"
STRONG_B = "Tz6&hJ3@cN8*bQ1^yE"
NOW = datetime(2026, 10, 12, 12, 0, 0)


@pytest.fixture
def vault(tmp_path):
    db = Database(tmp_path / "h.db")
    v = Vault(db)
    v.initialize("master-pass-1234")
    yield v
    db.close()


def _add(vault: Vault, app: str, password: str, created: str = "2026-10-01 00:00:00") -> int:
    entry_id = vault.add_entry(VaultEntry(
        id=None, app_name=app, username="u", password=password,
        notes=None, category_id=None,
    ))
    vault.db._conn.execute(
        "UPDATE vault_entries SET created_at = ? WHERE id = ?", (created, entry_id)
    )
    vault.db._conn.commit()
    return entry_id


def test_empty_vault_scores_100(vault: Vault):
    report = health.analyze(vault, now=NOW)
    assert report.total == 0 and report.score == 100


def test_detects_weak_passwords_with_reason(vault: Vault):
    _add(vault, "Kısa", "abc123")
    _add(vault, "TekTür", "aaaaaaaaaaaaaaaa")
    _add(vault, "Güçlü", STRONG_A)
    report = health.analyze(vault, now=NOW)
    weak = {i.entry.app_name: i.detail for i in report.weak}
    assert set(weak) == {"Kısa", "TekTür"}
    assert "6 karakter" in weak["Kısa"]
    assert "çeşidi" in weak["TekTür"]


def test_detects_reused_passwords_as_groups(vault: Vault):
    _add(vault, "Gmail", STRONG_A)
    _add(vault, "Banka", STRONG_A)
    _add(vault, "Netflix", STRONG_A)
    _add(vault, "GitHub", STRONG_B)
    report = health.analyze(vault, now=NOW)
    assert len(report.reused) == 1
    assert {e.app_name for e in report.reused[0]} == {"Gmail", "Banka", "Netflix"}
    assert report.score == 25  # 4 kayıttan yalnızca GitHub sorunsuz


def test_old_uses_last_password_change_not_creation(vault: Vault):
    old_id = _add(vault, "Eski", STRONG_A, created="2024-01-01 00:00:00")
    renewed = _add(vault, "Yenilenmiş", STRONG_B, created="2024-01-01 00:00:00")
    entry = vault.get_entry(renewed)
    entry.password = "Rw5!pK8#sD2@fG7$hL"
    vault.update_entry(entry)  # history'e bugün tarihli satır düşer
    vault.db._conn.execute(
        "UPDATE password_history SET changed_at = '2026-09-01 00:00:00' WHERE entry_id = ?",
        (renewed,),
    )
    vault.db._conn.commit()

    report = health.analyze(vault, now=NOW)
    assert [i.entry.id for i in report.old] == [old_id]
    assert "1015 gündür" in report.old[0].detail  # 2024-01-01 → 2026-10-12


def test_old_sorted_oldest_first_numerically(vault: Vault):
    _add(vault, "400gün", STRONG_A, created="2025-09-07 12:00:00")
    _add(vault, "1000gün", STRONG_B, created="2024-01-16 12:00:00")
    report = health.analyze(vault, now=NOW, old_after_days=365)
    assert [i.entry.app_name for i in report.old] == ["1000gün", "400gün"]


def test_entry_with_several_problems_counted_once(vault: Vault):
    _add(vault, "A", "abc", created="2020-01-01 00:00:00")
    _add(vault, "B", "abc", created="2020-01-01 00:00:00")
    report = health.analyze(vault, now=NOW)
    assert len(report.weak) == 2 and len(report.old) == 2 and len(report.reused) == 1
    assert report.healthy == 0 and report.score == 0


def test_report_never_contains_passwords(vault: Vault):
    _add(vault, "A", "gizli-zayif")
    _add(vault, "B", "gizli-zayif")
    report = health.analyze(vault, now=NOW)
    dumped = repr(dataclasses.asdict(report))
    assert "gizli-zayif" not in dumped


def test_requires_unlocked_vault(vault: Vault):
    from core.vault import VaultLocked
    vault.lock()
    with pytest.raises(VaultLocked):
        health.analyze(vault, now=NOW)


def test_corrupt_entry_is_listed_not_fatal(vault: Vault):
    good = _add(vault, "Sağlam", STRONG_A)
    bad = _add(vault, "Bozuk", STRONG_B)
    vault.db._conn.execute(
        "UPDATE vault_entries SET encrypted_password = ? WHERE id = ?", (b"garbage", bad)
    )
    vault.db._conn.commit()

    report = health.analyze(vault, now=NOW)
    assert [i.entry.id for i in report.unreadable] == [bad]
    assert good not in report.problem_ids
    assert report.healthy == 1 and report.score == 50


def test_default_now_is_utc_so_new_entry_is_not_old(vault: Vault):
    """Varsayılan `now` UTC olmalı. Kayıt 22 saat önce (UTC) oluşmuş gibi
    ayarlanır: UTC'de yaşı 0 gün; analyze yanlışlıkla yerel saati (ör. UTC+3)
    kullansaydı 1 gün çıkar ve kayıt "eski" listesine düşerdi."""
    from datetime import timedelta, timezone
    created = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(hours=22)
    _add(vault, "Yeni", STRONG_A, created=created.strftime("%Y-%m-%d %H:%M:%S"))
    report = health.analyze(vault, old_after_days=1)
    assert report.old == []
    assert report.score == 100


def test_parse_ts_accepts_iso_formats():
    assert health._parse_ts("2026-01-02 03:04:05") == datetime(2026, 1, 2, 3, 4, 5)
    assert health._parse_ts("2026-01-02T03:04:05") == datetime(2026, 1, 2, 3, 4, 5)
    assert health._parse_ts("2026-01-02T06:04:05+03:00") == datetime(2026, 1, 2, 3, 4, 5)
    assert health._parse_ts("2026-01-02 06:04:05+03:00") == datetime(2026, 1, 2, 3, 4, 5)
    assert health._parse_ts("2026-01-02T03:04:05Z") == datetime(2026, 1, 2, 3, 4, 5)
    assert health._parse_ts("bozuk") is None
    assert health._parse_ts(None) is None
