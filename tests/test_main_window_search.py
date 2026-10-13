"""Ana pencerede arama: kartlar yeniden oluşturulmaz, yalnızca gizlenir/gösterilir."""
from __future__ import annotations

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtCore import QEvent, QObject
from PySide6.QtWidgets import QApplication, QWidget

from core.database import Database
from core.vault import EntrySummary, Vault, VaultEntry, matches_search

MASTER = "master-pass-1234"


@pytest.fixture(scope="module")
def qapp():
    return QApplication.instance() or QApplication([])


@pytest.fixture
def window(qapp, tmp_path):
    from ui.main_window import MainWindow

    db = Database(tmp_path / "v.db")
    vault = Vault(db)
    vault.initialize(MASTER)
    for name, user in (("GitHub", "ada"), ("Gmail", "ada@example.com"),
                       ("İş Bankası", "12345"), ("Netflix", "hopper")):
        vault.add_entry(VaultEntry(None, name, user, "x" * 14, None, None))
    w = MainWindow(vault)
    w._tick_timer.stop()
    w.show()
    qapp.processEvents()
    yield w
    w._clear_cards()
    w.hide()
    QApplication.instance().removeEventFilter(w)
    db.close()


def _visible_names(w) -> list[str]:
    return [c.app_label.text() for c in w._cards.values() if not c.isHidden()]


def _summary(app_name: str, username: str) -> EntrySummary:
    return EntrySummary(1, app_name, username, None, None, False, "", "")


def test_matches_search_folds_turkish_and_checks_both_fields():
    assert matches_search(_summary("İş Bankası", "ada"), "iş")
    assert matches_search(_summary("GitHub", "Ada.Lovelace"), "lovelace")
    assert matches_search(_summary("GitHub", "ada"), "   ")
    assert not matches_search(_summary("GitHub", "ada"), "netflix")


def test_search_hides_cards_without_rebuilding(window, qapp):
    cards_before = dict(window._cards)
    window.search_edit.setText("g")
    window._apply_search()  # debounce beklenmeden
    assert sorted(_visible_names(window)) == ["GitHub", "Gmail"]
    assert window._cards == cards_before  # aynı kart nesneleri
    assert window.status.currentMessage() == "2 kayıt"

    window.search_edit.setText("")
    window._apply_search()
    assert len(_visible_names(window)) == 4


def test_search_is_debounced(window, qapp):
    window.search_edit.setText("git")
    assert window._search_timer.isActive()
    assert len(_visible_names(window)) == 4  # henüz filtrelenmedi
    window._search_timer.timeout.emit()
    assert _visible_names(window) == ["GitHub"]


def test_no_match_shows_empty_state(window, qapp):
    window.search_edit.setText("yokboylebirsey")
    window._apply_search()
    assert window.list_stack.currentIndex() == 1
    assert "yokboylebirsey" in window.empty_subtitle.text()


def test_search_survives_reload(window, qapp):
    window.search_edit.setText("net")
    window._apply_search()
    window._reload_entries()  # örn. kayıt düzenlendikten sonra
    assert _visible_names(window) == ["Netflix"]


def test_search_opens_no_top_level_windows(window, qapp):
    class Spy(QObject):
        seen: list[str] = []

        def eventFilter(self, obj, event):
            if (event.type() == QEvent.Show and isinstance(obj, QWidget)
                    and obj.isWindow() and obj is not window):
                self.seen.append(type(obj).__name__)
            return False

    spy = Spy()
    qapp.installEventFilter(spy)
    try:
        for text in ("g", "gi", "", "n", ""):
            window.search_edit.setText(text)
            window._apply_search()
            window._reload_entries()
            qapp.processEvents()
    finally:
        qapp.removeEventFilter(spy)
    assert spy.seen == []


def test_about_has_releases_link_without_network(qapp):
    from ui.about_dialog import AboutDialog, RELEASES_URL

    dlg = AboutDialog()
    label = dlg.findChild(QWidget, "updatesLink")
    assert label is not None
    assert RELEASES_URL.startswith("https://github.com/")
    assert RELEASES_URL in label.text()
    assert label.openExternalLinks()


def test_search_kept_when_category_or_favorites_change(window, qapp):
    window.vault.toggle_favorite(next(r.id for r in window._rows if r.app_name == "Gmail"))
    window.search_edit.setText("g")
    window._apply_search()
    window._set_filter(None, favorites_only=True)
    assert _visible_names(window) == ["Gmail"]
    window._set_filter(None, favorites_only=False)
    assert sorted(_visible_names(window)) == ["GitHub", "Gmail"]
    assert window.search_edit.text() == "g"


def test_cards_and_rows_stay_in_sync_after_delete(window, qapp):
    gid = next(r.id for r in window._rows if r.app_name == "GitHub")
    window.vault.delete_entry(gid)
    window._reload_entries()
    assert set(window._cards) == {r.id for r in window._rows}
    assert gid not in window._cards


def test_clear_cards_drops_decrypted_rows(window, qapp):
    window._search_timer.start()
    window._clear_cards()
    assert window._rows == [] and window._cards == {}


def test_hidden_card_is_masked(window, qapp):
    from ui.components.entry_card import MASK_STRING

    card = next(c for c in window._cards.values() if c.app_label.text() == "Netflix")
    card.show_password("gizli-sifre-123")
    window.search_edit.setText("git")
    window._apply_search()
    assert card.isHidden()
    assert card.pw_field.text() == MASK_STRING


def test_matches_search_includes_category_name():
    e = _summary("GitHub", "ada")
    assert matches_search(e, "iş", "İş")
    assert not matches_search(e, "iş", None)
    assert not matches_search(e, "finans", "İş")


def test_vault_list_entries_searches_category_names(tmp_path):
    db = Database(tmp_path / "c.db")
    vault = Vault(db)
    vault.initialize(MASTER)
    is_cat = vault.add_category("İş")
    vault.add_entry(VaultEntry(None, "Jira", "ada", "x" * 14, None, is_cat))
    vault.add_entry(VaultEntry(None, "Netflix", "ada", "x" * 14, None, None))
    assert [e.app_name for e in vault.list_entries(search="İŞ")] == ["Jira"]
    db.close()


def test_window_search_by_category_and_rename(window, qapp):
    vault = window.vault
    cat = vault.add_category("Eğlence")
    netflix = next(r for r in window._rows if r.app_name == "Netflix")
    entry = vault.get_entry(netflix.id)
    entry.category_id = cat
    vault.update_entry(entry)
    window._reload_categories()
    window._reload_entries()

    window.search_edit.setText("eğlen")
    window._apply_search()
    assert _visible_names(window) == ["Netflix"]

    vault.rename_category(cat, "Dizi")
    window._reload_categories()  # yeniden adlandırma yalnızca kategorileri yeniler
    assert _visible_names(window) == []
    window.search_edit.setText("dizi")
    window._apply_search()
    assert _visible_names(window) == ["Netflix"]


def test_lock_clears_category_names(window, qapp):
    window.vault.add_category("İş")
    window._reload_categories()
    assert window._category_names
    window.lock_now()
    assert window._category_names == {} and window._rows == []
