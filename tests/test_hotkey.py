import os

import pytest
import Quartz

from autoclick.hotkey import HotkeyListener

F6, SPACE = 97, 49
# Real key presses come from the keyboard driver, which reports pid 0.
KEYBOARD_PID = 0


def key_event(keycode, down=True, pid=KEYBOARD_PID, autorepeat=False):
    event = Quartz.CGEventCreateKeyboardEvent(None, keycode, down)
    Quartz.CGEventSetIntegerValueField(event, Quartz.kCGEventSourceUnixProcessID, pid)
    Quartz.CGEventSetIntegerValueField(event, Quartz.kCGKeyboardEventAutorepeat, int(autorepeat))
    return event


@pytest.fixture
def presses():
    return []


@pytest.fixture
def listener(presses):
    return HotkeyListener(F6, lambda: presses.append("press"))


def deliver(listener, event, event_type=Quartz.kCGEventKeyDown):
    return listener._handle(None, event_type, event, None)


def test_hotkey_down_calls_on_press_and_passes_the_event_on(listener, presses):
    event = key_event(F6)

    assert deliver(listener, event) is event
    assert presses == ["press"]


def test_other_keys_are_ignored(listener, presses):
    deliver(listener, key_event(SPACE))

    assert presses == []


def test_holding_the_hotkey_counts_once(listener, presses):
    deliver(listener, key_event(F6))
    deliver(listener, key_event(F6, autorepeat=True))
    deliver(listener, key_event(F6, autorepeat=True))

    assert presses == ["press"]


def test_keys_sent_by_this_app_are_ignored(listener, presses):
    deliver(listener, key_event(F6, pid=os.getpid()))

    assert presses == []


def test_keycode_can_be_changed_while_listening(listener, presses):
    listener.keycode = SPACE

    deliver(listener, key_event(F6))
    deliver(listener, key_event(SPACE))

    assert presses == ["press"]


def test_error_in_on_press_does_not_escape_into_the_event_tap(listener):
    def broken():
        raise RuntimeError("boom")

    listener.on_press = broken
    event = key_event(F6)

    assert deliver(listener, event) is event


def test_tap_switched_off_by_macos_is_handled_without_a_press(listener, presses):
    deliver(listener, None, Quartz.kCGEventTapDisabledByTimeout)

    assert presses == []


def test_start_and_stop_follow_what_macos_allows(listener):
    # Listens only; nothing is posted. Without Input Monitoring the tap is
    # refused and start reports False.
    started = listener.start()

    assert listener.running is started
    listener.stop()
    assert not listener.running
