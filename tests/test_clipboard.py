"""Pano testleri — gerçek panoya dokunmaz, sahte pano kullanır."""
from __future__ import annotations

import struct
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest

from utils import clipboard as cb


class FakeClipboard:
    """QClipboard'un kullanılan kısmının sahtesi."""

    def __init__(self) -> None:
        self.value = ""

    def text(self) -> str:
        return self.value

    def setMimeData(self, mime) -> None:  # noqa: N802 (Qt API)
        self.value = mime.text()

    def clear(self) -> None:
        self.value = ""


@pytest.fixture
def timers(monkeypatch) -> list:
    """singleShot ile kurulan zamanlayıcıları toplar; test elle tetikler."""
    pending: list = []
    monkeypatch.setattr(cb.QTimer, "singleShot",
                        staticmethod(lambda ms, fn: pending.append((ms, fn))))
    return pending


@pytest.fixture
def fake(monkeypatch, timers):
    board = FakeClipboard()
    monkeypatch.setattr(cb.QApplication, "clipboard", staticmethod(lambda: board))
    monkeypatch.setattr(cb, "_last_copied", None)
    return board


def test_timer_clears_after_20_seconds(fake, timers):
    cb.copy_to_clipboard("şifre-123")
    assert timers[0][0] == 20_000
    timers[0][1]()  # 20 sn doldu
    assert fake.value == ""
    assert cb._last_copied is None


def test_consecutive_copies_old_timer_keeps_newer_value(fake, timers):
    cb.copy_to_clipboard("A")
    cb.copy_to_clipboard("B")
    timers[0][1]()  # A'nın süresi doldu
    assert fake.value == "B"
    cb.clear_pending_secret()  # B hâlâ izleniyor → kilitte silinir
    assert fake.value == ""


def test_lock_now_clears_clipboard(monkeypatch):
    """lock_now panoyu temizlemeyi unutursa bu test kırılır."""
    from ui import main_window

    calls: list[str] = []
    monkeypatch.setattr(main_window, "clear_pending_secret", lambda: calls.append("clear"))

    class FakeWindow:
        _locking = False
        _tick_timer = type("T", (), {"stop": lambda self: None})()
        vault = type("V", (), {"lock": lambda self: calls.append("lock")})()
        def _clear_cards(self): pass
        def close(self): calls.append("close")

    monkeypatch.setattr(main_window.QApplication, "topLevelWidgets", staticmethod(lambda: []))
    main_window.MainWindow.lock_now(FakeWindow())
    assert calls == ["clear", "lock", "close"]


@pytest.mark.skipif(sys.platform != "win32", reason="Windows'a özgü pano biçimleri")
def test_mime_excludes_from_history_cloud_and_monitors():
    mime = cb._build_mime("gizli")
    assert mime.text() == "gizli"
    zero = struct.pack("<I", 0)
    assert bytes(mime.data(cb._WIN_MIME.format("CanIncludeInClipboardHistory"))) == zero
    assert bytes(mime.data(cb._WIN_MIME.format("CanUploadToCloudClipboard"))) == zero
    assert mime.hasFormat(cb._WIN_MIME.format("ExcludeClipboardContentFromMonitorProcessing"))


def test_clear_pending_secret_removes_our_copy(fake):
    cb.copy_to_clipboard("şifre-123")
    assert fake.value == "şifre-123"
    cb.clear_pending_secret()  # kilit / çıkış
    assert fake.value == ""


def test_clear_pending_secret_keeps_users_own_copy(fake):
    cb.copy_to_clipboard("şifre-123")
    fake.value = "kullanıcının kopyaladığı metin"
    cb.clear_pending_secret()
    assert fake.value == "kullanıcının kopyaladığı metin"


def test_clear_pending_secret_without_copy_is_noop(fake):
    fake.value = "başka bir şey"
    cb.clear_pending_secret()
    assert fake.value == "başka bir şey"
