"""Global start/stop hotkey.

A listen-only Quartz event tap on its own thread, so it works while another
app (Roblox in full screen) has the keyboard. Creating the tap needs the Input
Monitoring permission; without it `start` returns False.
"""

import os
import threading
from collections.abc import Callable

import objc
import Quartz

_START_TIMEOUT_S = 2.0
# How long the listener thread may take to notice `stop` if the wake-up is lost.
_LOOP_SLICE_S = 0.25
_TAP_DISABLED = (Quartz.kCGEventTapDisabledByTimeout, Quartz.kCGEventTapDisabledByUserInput)


class HotkeyListener:
    """Calls `on_press` when the hotkey goes down, whichever app is frontmost.

    `on_press` runs on the listener thread, so it must not touch Tk.
    """

    def __init__(self, keycode: int, on_press: Callable[[], None] = lambda: None) -> None:
        self.keycode = keycode
        self.on_press = on_press
        self._own_pid = os.getpid()
        self._thread: threading.Thread | None = None
        self._ready = threading.Event()
        self._stopping = False
        self._tap = None
        self._loop = None

    @property
    def running(self) -> bool:
        return self._tap is not None

    def start(self) -> bool:
        """Start listening. False means macOS refused the tap (no permission)."""
        if self.running:
            return True
        self._stopping = False
        self._ready.clear()
        self._thread = threading.Thread(target=self._run, name="autoclick-hotkey", daemon=True)
        self._thread.start()
        self._ready.wait(_START_TIMEOUT_S)
        return self.running

    def stop(self) -> None:
        self._stopping = True
        if self._loop is not None:
            Quartz.CFRunLoopStop(self._loop)
        if self._thread is not None:
            self._thread.join(timeout=1.0)

    def _run(self) -> None:
        tap = Quartz.CGEventTapCreate(
            Quartz.kCGSessionEventTap,
            Quartz.kCGHeadInsertEventTap,
            Quartz.kCGEventTapOptionListenOnly,
            Quartz.CGEventMaskBit(Quartz.kCGEventKeyDown),
            self._handle,
            None,
        )
        if tap is None:
            self._ready.set()
            return
        source = Quartz.CFMachPortCreateRunLoopSource(None, tap, 0)
        self._loop = Quartz.CFRunLoopGetCurrent()
        Quartz.CFRunLoopAddSource(self._loop, source, Quartz.kCFRunLoopCommonModes)
        Quartz.CGEventTapEnable(tap, True)
        self._tap = tap
        self._ready.set()
        try:
            # Run in slices rather than CFRunLoopRun, so a `stop` that arrives
            # before the loop is running is still noticed.
            while not self._stopping:
                with objc.autorelease_pool():
                    Quartz.CFRunLoopRunInMode(Quartz.kCFRunLoopDefaultMode, _LOOP_SLICE_S, False)
        finally:
            self._tap = None
            self._loop = None
            Quartz.CGEventTapEnable(tap, False)
            Quartz.CFMachPortInvalidate(tap)

    def _handle(self, proxy, event_type, event, refcon):
        if event_type in _TAP_DISABLED:
            # macOS switches a tap off when its callback is slow; turn it back on.
            if self._tap is not None:
                Quartz.CGEventTapEnable(self._tap, True)
        elif event_type == Quartz.kCGEventKeyDown and self._is_hotkey(event):
            try:
                self.on_press()
            except Exception:
                # An error must not escape into the event tap.
                pass
        return event

    def _is_hotkey(self, event) -> bool:
        field = Quartz.CGEventGetIntegerValueField
        return (
            field(event, Quartz.kCGKeyboardEventKeycode) == self.keycode
            and not field(event, Quartz.kCGKeyboardEventAutorepeat)
            # The engine's own key taps pass through this tap as well.
            and field(event, Quartz.kCGEventSourceUnixProcessID) != self._own_pid
        )
