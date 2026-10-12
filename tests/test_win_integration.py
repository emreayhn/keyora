"""Windows oturum kilidi / uyku mesajı ayrıştırma testleri."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from utils import win_integration as wi


def test_session_lock_messages_trigger_lock():
    assert wi.is_lock_message(wi.WM_WTSSESSION_CHANGE, wi.WTS_SESSION_LOCK)
    assert wi.is_lock_message(wi.WM_WTSSESSION_CHANGE, wi.WTS_CONSOLE_DISCONNECT)
    assert wi.is_lock_message(wi.WM_WTSSESSION_CHANGE, wi.WTS_REMOTE_DISCONNECT)
    assert wi.is_lock_message(wi.WM_POWERBROADCAST, wi.PBT_APMSUSPEND)


def test_other_messages_do_not_trigger_lock():
    WTS_SESSION_UNLOCK = 0x8
    PBT_APMRESUMEAUTOMATIC = 0x12
    assert not wi.is_lock_message(wi.WM_WTSSESSION_CHANGE, WTS_SESSION_UNLOCK)
    assert not wi.is_lock_message(wi.WM_POWERBROADCAST, PBT_APMRESUMEAUTOMATIC)
    assert not wi.is_lock_message(0x0010, wi.WTS_SESSION_LOCK)  # WM_CLOSE
