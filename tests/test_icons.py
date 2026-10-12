"""Rozet yardımcıları ve kayıt kartı menüsü testleri (ekransız Qt)."""
from __future__ import annotations

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtWidgets import QApplication

from ui import icons


@pytest.fixture(scope="module")
def qapp():
    return QApplication.instance() or QApplication([])


# ---------- saf fonksiyonlar ----------

@pytest.mark.parametrize("name, letter", [
    ("istanbul Kart", "İ"),   # Türkçe: i → İ (I değil)
    ("ışık", "I"),            # Türkçe: ı → I
    ("GitHub", "G"),
    ("  netflix", "N"),
    ("@kurumsal", "K"),       # baştaki sembol atlanır
    ("123 Banka", "1"),
    ("!!!", "#"),
    ("", "#"),
])
def test_badge_letter(name, letter):
    assert icons.badge_letter(name) == letter


def test_badge_color_is_deterministic_and_from_palette():
    assert icons.badge_color("GitHub") == icons.badge_color("GitHub")
    assert icons.badge_color("GitHub") == icons.badge_color("  github ")
    assert icons.badge_color("GitHub") in icons.BADGE_COLORS
    colors = {icons.badge_color(n) for n in ("GitHub", "Gmail", "Netflix", "Banka", "Jira", "Slack")}
    assert len(colors) > 1  # hepsi aynı renge düşmüyor


def test_badge_cache_never_holds_app_names(qapp):
    """Kasada şifreli olan ad, kilitten sonra önbellek anahtarı olarak kalmamalı."""
    assert not hasattr(icons.initial_badge, "cache_info")  # adla önbelleklenmiyor

    # Aynı harf + renge düşen iki FARKLI ad tek önbellek kaydını paylaşmalı:
    # anahtar addan bağımsızsa ikinci çağrı isabet (hit) olur.
    first = "GizliBanka"
    second = next(
        n for n in (f"G{i}" for i in range(1000))
        if icons.badge_color(n) == icons.badge_color(first)
    )
    icons._badge_pixmap.cache_clear()
    icons.initial_badge(first, 28)
    icons.initial_badge(second, 28)
    info = icons._badge_pixmap.cache_info()
    assert info.currsize == 1 and info.hits == 1


# ---------- kart menüsü ----------

def test_card_menu_has_history_then_delete_and_emits(qapp):
    from ui.components.entry_card import EntryCard

    card = EntryCard(entry_id=7, app_name="GitHub", username="ada", favorite=False)
    menu = card.more_btn.menu()
    actions = menu.actions()
    labels = [a.text() for a in actions]
    assert labels[0].startswith("Şifre geçmişi")
    assert actions[1].isSeparator()
    assert labels[-1].startswith("Sil")
    assert not hasattr(card, "delete_btn")  # satırda doğrudan sil düğmesi yok

    got: list[tuple[str, int]] = []
    card.history_requested.connect(lambda i: got.append(("h", i)))
    card.delete_requested.connect(lambda i: got.append(("d", i)))
    actions[0].trigger()
    actions[-1].trigger()
    assert got == [("h", 7), ("d", 7)]
