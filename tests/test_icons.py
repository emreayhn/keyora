"""Kayıt kartı testleri (ekransız Qt)."""
from __future__ import annotations

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtWidgets import QApplication


@pytest.fixture(scope="module")
def qapp():
    return QApplication.instance() or QApplication([])


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


def test_card_shows_plain_bold_name_without_badge(qapp):
    from ui.components.entry_card import EntryCard

    card = EntryCard(entry_id=1, app_name="İş Bankası", username="ada", favorite=False)
    assert card.app_label.text() == "İş Bankası"
    assert not hasattr(card, "badge")


def test_long_category_is_elided_but_text_and_tooltip_stay_full(qapp):
    from ui.components.entry_card import EntryCard

    long_name = "Sosyal Medya Hesapları ve Diğerleri"
    card = EntryCard(entry_id=1, app_name="Instagram", username="ada",
                     favorite=False, category=long_name)
    card.resize(500, 50)
    card.show()
    qapp.processEvents()
    assert card.category_label.text() == long_name
    assert card.category_label.toolTip() == long_name
    card.grab()  # paintEvent kısaltarak çizerken hata vermemeli
    card.set_category(None)
    assert card.category_label.text() == "—"
    card.close()
