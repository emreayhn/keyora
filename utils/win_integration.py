"""Windows entegrasyonu — oturum kilidi/uyku algılama ve ekran yakalamadan gizleme.

Windows dışındaki platformlarda tüm fonksiyonlar sessizce hiçbir şey yapmaz.
"""
from __future__ import annotations

import ctypes
import sys
from typing import Callable

from PySide6.QtCore import QAbstractNativeEventFilter, QEvent, QObject
from PySide6.QtWidgets import QWidget

IS_WINDOWS = sys.platform == "win32"

WM_WTSSESSION_CHANGE = 0x02B1
WM_POWERBROADCAST = 0x0218
WTS_CONSOLE_DISCONNECT = 0x2
WTS_REMOTE_DISCONNECT = 0x4
WTS_SESSION_LOCK = 0x7
PBT_APMSUSPEND = 0x4
NOTIFY_FOR_THIS_SESSION = 0

WDA_NONE = 0x0
WDA_MONITOR = 0x1
WDA_EXCLUDEFROMCAPTURE = 0x11  # Windows 10 2004+

LOCK_SESSION_EVENTS = (WTS_SESSION_LOCK, WTS_CONSOLE_DISCONNECT, WTS_REMOTE_DISCONNECT)

if IS_WINDOWS:
    from ctypes import wintypes

    _user32 = ctypes.WinDLL("user32", use_last_error=True)
    _user32.SetWindowDisplayAffinity.argtypes = [wintypes.HWND, wintypes.DWORD]
    _user32.SetWindowDisplayAffinity.restype = wintypes.BOOL

    _wtsapi32 = ctypes.WinDLL("wtsapi32", use_last_error=True)
    _wtsapi32.WTSRegisterSessionNotification.argtypes = [wintypes.HWND, wintypes.DWORD]
    _wtsapi32.WTSRegisterSessionNotification.restype = wintypes.BOOL
    _wtsapi32.WTSUnRegisterSessionNotification.argtypes = [wintypes.HWND]
    _wtsapi32.WTSUnRegisterSessionNotification.restype = wintypes.BOOL


def set_capture_excluded(widget: QWidget, excluded: bool) -> bool:
    """Pencereyi ekran görüntüsü / ekran paylaşımından gizler veya gösterir.

    Eski Windows sürümlerinde WDA_EXCLUDEFROMCAPTURE yoksa WDA_MONITOR'a
    (pencere siyah görünür) düşer. Başarılıysa True.
    """
    if not IS_WINDOWS:
        return False
    hwnd = int(widget.winId())
    if not excluded:
        return bool(_user32.SetWindowDisplayAffinity(hwnd, WDA_NONE))
    if _user32.SetWindowDisplayAffinity(hwnd, WDA_EXCLUDEFROMCAPTURE):
        return True
    return bool(_user32.SetWindowDisplayAffinity(hwnd, WDA_MONITOR))


class CaptureGuard(QObject):
    """Uygulamadaki her üst düzey pencereyi gösterildiği anda yakalamadan gizler.

    QApplication'a event filter olarak takılır; diyaloglar dahil tüm pencereleri
    kapsar. `enabled` False iken pencerelere dokunmaz.
    """

    def __init__(self, enabled: bool = True, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self.enabled = enabled

    def eventFilter(self, obj: QObject, event: QEvent) -> bool:
        """Show olayında üst düzey pencereye ekran yakalama korumasını uygular."""
        if (
            self.enabled
            and event.type() == QEvent.Show
            and isinstance(obj, QWidget)
            and obj.isWindow()
        ):
            set_capture_excluded(obj, True)
        return False

    def apply_to(self, widgets: list[QWidget]) -> None:
        """Ayar değiştiğinde açık pencerelere yeni durumu uygular."""
        for w in widgets:
            if w.isWindow() and w.isVisible():
                set_capture_excluded(w, self.enabled)


class SessionLockFilter(QAbstractNativeEventFilter):
    """Windows oturumu kilitlendiğinde / bağlantı kesildiğinde / uykuya geçerken
    `on_lock` geri çağrısını tetikler.

    Oturum bildirimlerini almak için `register(widget)` ile bir pencerenin
    HWND'si WTS'ye kaydedilmelidir; uyku bildirimi tüm üst düzey pencerelere
    zaten gelir.
    """

    def __init__(self, on_lock: Callable[[], None]) -> None:
        super().__init__()
        self._on_lock = on_lock
        self._registered: set[int] = set()

    def register(self, widget: QWidget) -> bool:
        """Pencereyi oturum değişikliği bildirimlerine kaydeder."""
        if not IS_WINDOWS:
            return False
        hwnd = int(widget.winId())
        if hwnd in self._registered:
            return True
        if _wtsapi32.WTSRegisterSessionNotification(hwnd, NOTIFY_FOR_THIS_SESSION):
            self._registered.add(hwnd)
            return True
        return False

    def unregister(self, widget: QWidget) -> None:
        """Kaydı kaldırır (pencere kapanırken çağrılmalı)."""
        if not IS_WINDOWS:
            return
        hwnd = int(widget.winId())
        if hwnd in self._registered:
            _wtsapi32.WTSUnRegisterSessionNotification(hwnd)
            self._registered.discard(hwnd)

    def nativeEventFilter(self, eventType, message):  # noqa: N802 (Qt API)
        """Windows mesajlarını süzer; olayı asla yutmaz."""
        if IS_WINDOWS and bytes(eventType) == b"windows_generic_MSG":
            msg = wintypes.MSG.from_address(int(message))
            if is_lock_message(msg.message, msg.wParam):
                self._on_lock()
        return False, 0


def is_lock_message(message: int, wparam: int) -> bool:
    """Bu Windows mesajı kasanın kilitlenmesini gerektiriyor mu?"""
    if message == WM_WTSSESSION_CHANGE:
        return wparam in LOCK_SESSION_EVENTS
    if message == WM_POWERBROADCAST:
        return wparam == PBT_APMSUSPEND
    return False
