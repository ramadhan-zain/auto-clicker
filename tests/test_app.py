import tkinter as tk

import pytest

from autoclick.actions import Click, KeyTap
from autoclick.app import START_DELAY_MS, App
from autoclick.backend.base import MouseButton
from autoclick.backend.fake import FakeBackend
from autoclick.engine import Snapshot, StopReason
from autoclick.macos import ROBLOX_BUNDLE_ID, RunningApp

F6, F8 = 97, 100
FINDER = "com.apple.finder"


class StubEngine:
    """Stands in for the engine so no worker thread runs in UI tests."""

    def __init__(self) -> None:
        self.state = Snapshot()
        self.started_with = None
        self.stop_calls = 0

    @property
    def running(self) -> bool:
        return self.state.running

    def snapshot(self) -> Snapshot:
        return self.state

    def start(self, config) -> None:
        self.started_with = config
        self.state = Snapshot(running=True, next_in_s=3.0)

    def stop(self) -> None:
        self.stop_calls += 1
        self.state = Snapshot(sent=self.state.sent, stop_reason=StopReason.USER)

    def join(self, timeout=None) -> None:
        pass


class StubHotkey:
    """Hotkey listener that starts only when `allowed`, as macOS would decide."""

    def __init__(self) -> None:
        self.allowed = True
        self.running = False
        self.keycode = None
        self.on_press = None
        self.start_calls = 0

    def start(self) -> bool:
        self.start_calls += 1
        self.running = self.allowed
        return self.running

    def stop(self) -> None:
        self.running = False


class FakeSystem:
    """Stands in for the `macos` module."""

    def __init__(self) -> None:
        self.accessibility = True
        self.input_monitoring = True
        self.apps = [RunningApp("Finder", FINDER), RunningApp("Roblox", ROBLOX_BUNDLE_ID)]
        self.calls: list[str] = []

    def accessibility_granted(self) -> bool:
        return self.accessibility

    def input_monitoring_granted(self) -> bool:
        return self.input_monitoring

    def windowed_apps(self) -> list[RunningApp]:
        return list(self.apps)

    def request_accessibility(self) -> None:
        self.calls.append("request_accessibility")

    def open_accessibility_settings(self) -> None:
        self.calls.append("open_accessibility_settings")

    def request_input_monitoring(self) -> None:
        self.calls.append("request_input_monitoring")

    def open_input_monitoring_settings(self) -> None:
        self.calls.append("open_input_monitoring_settings")


@pytest.fixture(scope="module")
def root():
    try:
        root = tk.Tk()
    except tk.TclError as exc:
        pytest.skip(f"No display for Tk: {exc}")
    root.withdraw()
    yield root
    root.destroy()


@pytest.fixture
def engine():
    return StubEngine()


@pytest.fixture
def backend():
    return FakeBackend(cursor=(512.0, 300.0))


@pytest.fixture
def hotkey():
    return StubHotkey()


@pytest.fixture
def system():
    return FakeSystem()


@pytest.fixture
def make_app(root, engine, backend, hotkey, system):
    """Builds the window; tests that need a missing permission set it up first."""
    apps = []

    def make() -> App:
        apps.append(App(root, engine, backend, hotkey, system=system))
        return apps[-1]

    yield make
    for app in apps:
        app.shutdown()
        app.frame.destroy()


@pytest.fixture
def app(make_app):
    return make_app()


def enabled(widget) -> bool:
    return not widget.instate(["disabled"])


def shown(widget) -> bool:
    return bool(widget.winfo_manager())


# Form


def test_defaults_are_a_space_tap_every_five_minutes_for_roblox(app):
    config = app.build_config()

    assert config.actions == (KeyTap("space", hold_ms=80),)
    assert config.interval_ms == 300_000
    assert config.target_bundle_id == ROBLOX_BUNDLE_ID
    assert config.auto_stop_after_s is None
    assert config.start_delay_ms == START_DELAY_MS
    assert app.interval_note.cget("text") == "5 min = 12 key presses per hour"
    assert enabled(app.start_button)


def test_interval_number_and_unit_are_converted_to_milliseconds(app):
    app.interval_value.set("1.5")
    app.interval_unit.set("s")

    assert app.build_config().interval_ms == 1500
    assert app.interval_note.cget("text") == "1500 ms = 40 key presses per minute"


@pytest.mark.parametrize(
    ("text", "unit", "message"),
    [
        ("abc", "s", "must be a number"),
        ("61", "min", "between 10 ms and 1 hour"),
        ("5", "ms", "between 10 ms and 1 hour"),
    ],
)
def test_invalid_interval_shows_an_inline_error_and_blocks_start(app, text, unit, message):
    app.interval_value.set(text)
    app.interval_unit.set(unit)

    assert message in app.interval_note.cget("text")
    assert not enabled(app.start_button)
    with pytest.raises(ValueError):
        app.build_config()


def test_fixing_the_interval_enables_start_again(app):
    app.interval_value.set("")
    assert not enabled(app.start_button)

    app.interval_value.set("30")
    app.interval_unit.set("s")

    assert enabled(app.start_button)


def test_presets_fill_the_interval(app):
    assert [button.cget("text") for button in app.preset_buttons.values()] == [
        "50 ms",
        "100 ms",
        "1 s",
        "5 min",
    ]

    app.preset_buttons[1000].invoke()

    assert (app.interval_value.get(), app.interval_unit.get()) == ("1", "s")
    assert app.build_config().interval_ms == 1000


def test_invalid_hold_shows_an_inline_error_and_blocks_start(app):
    app.hold.set("0")

    assert "Hold must be between" in app.hold_note.cget("text")
    assert not enabled(app.start_button)


def test_hold_longer_than_half_the_interval_shows_the_effective_value(app):
    app.interval_value.set("500")
    app.interval_unit.set("ms")
    app.hold.set("400")

    assert app.hold_note.cget("text") == "Shortened to 250 ms to fit the interval."
    assert enabled(app.start_button)


def test_key_and_position_controls_follow_the_action(app):
    assert enabled(app.key_box)
    assert not enabled(app.pick_button)

    app.action.set("left")

    assert not enabled(app.key_box)
    assert enabled(app.pick_button)
    assert app.interval_note.cget("text") == "5 min = 12 clicks per hour"


def test_click_at_current_cursor(app):
    app.action.set("right")

    assert app.build_config().actions == (Click(MouseButton.RIGHT, None, 80),)


def test_fixed_position_needs_a_pick_first(app):
    app.action.set("left")
    app.position_mode.set("fixed")

    assert app.position_text.get() == "Pick a position first."
    assert not enabled(app.start_button)


def test_pick_position_counts_down_then_saves_the_cursor(app):
    app.action.set("left")

    app.pick_button.invoke()

    assert app.position_text.get() == "Move the cursor to the spot... 3"
    assert not enabled(app.start_button)
    # Jump to the end of the countdown instead of waiting three seconds.
    app.root.after_cancel(app._pick_job)
    app._pick_tick(0)

    assert app.position_text.get() == "x 512, y 300"
    assert app.position_mode.get() == "fixed"
    assert enabled(app.start_button)
    assert app.build_config().actions == (Click(MouseButton.LEFT, (512.0, 300.0), 80),)


# Frontmost guard and auto-stop


def test_guard_toggle_sends_to_any_app_when_off(app):
    app.guard_on.set(False)

    assert app.build_config().target_bundle_id is None
    assert app.guard_note.cget("text") == ""


def test_guard_off_in_fast_mode_warns_but_does_not_block(app):
    app.apply_preset(50)
    assert app.guard_note.cget("text") == ""

    app.guard_on.set(False)

    assert "whatever is in front" in app.guard_note.cget("text")
    assert enabled(app.start_button)


def test_target_list_offers_the_apps_with_a_window_open(app):
    assert app.target_box.cget("values") == ("Finder", "Roblox")
    assert app.target.get() == "Roblox"

    app.target.set("Finder")

    assert app.build_config().target_bundle_id == FINDER


def test_target_list_is_read_again_when_opened_and_keeps_the_choice(app, system):
    app.target.set("Finder")
    system.apps = [RunningApp("Notes", "com.apple.Notes"), RunningApp("Finder", FINDER)]

    app.refresh_targets()

    assert app.target_box.cget("values") == ("Notes", "Finder")
    assert app.target.get() == "Finder"
    assert app.build_config().target_bundle_id == FINDER


def test_roblox_stays_listed_while_it_is_not_open(make_app, system):
    system.apps = [RunningApp("Finder", FINDER)]

    app = make_app()

    assert app.target_box.cget("values") == ("Finder", "Roblox")
    assert app.build_config().target_bundle_id == ROBLOX_BUNDLE_ID


def test_apps_sharing_a_name_are_told_apart_by_bundle_id(make_app, system):
    system.apps = [RunningApp("Game", "com.a.game"), RunningApp("Game", "com.b.game")]
    app = make_app()

    app.target.set("Game (com.b.game)")

    assert app.build_config().target_bundle_id == "com.b.game"


def test_target_list_is_locked_while_the_guard_is_off(app):
    assert enabled(app.target_box)

    app.guard_on.set(False)

    assert not enabled(app.target_box)


def test_auto_stop_is_off_by_default_and_its_field_is_locked(app):
    assert not enabled(app.auto_stop_entry)

    app.auto_stop_on.set(True)

    assert enabled(app.auto_stop_entry)
    assert app.build_config().auto_stop_after_s == 30 * 60


def test_auto_stop_minutes_are_converted_to_seconds(app):
    app.auto_stop_on.set(True)
    app.auto_stop_minutes.set("1.5")

    assert app.build_config().auto_stop_after_s == 90


@pytest.mark.parametrize("text", ["", "abc", "0", "-5", "1441"])
def test_invalid_auto_stop_blocks_start_only_while_switched_on(app, text):
    app.auto_stop_minutes.set(text)
    assert enabled(app.start_button)

    app.auto_stop_on.set(True)

    assert "Auto-stop must be" in app.auto_stop_note.cget("text")
    assert not enabled(app.start_button)


# Start, stop and status


def test_start_hands_the_form_to_the_engine_and_locks_it(app, engine):
    app.start_button.invoke()

    assert engine.started_with == app.build_config()
    assert app.start_button.cget("text") == "Stop (F6)"
    for widget in (
        app.interval_entry,
        app.key_box,
        app.guard_box,
        app.target_box,
        app.hotkey_box,
    ):
        assert not enabled(widget)
    assert app.status.get() == "Running. Next action in 3.0 s."
    assert app.counts.get() == "Sent 0 · skipped 0"


def test_stop_button_stops_the_engine_and_unlocks_the_form(app, engine):
    app.start_button.invoke()
    engine.state = Snapshot(running=True, sent=4, skipped=2, next_in_s=1.0)

    app.start_button.invoke()
    app._render(engine.snapshot())

    assert engine.stop_calls == 1
    assert app.start_button.cget("text") == "Start (F6)"
    assert enabled(app.interval_entry)
    assert app.status.get() == "Stopped."
    assert app.counts.get() == "Sent 4 · skipped 0"


def test_status_shows_progress_and_time_to_auto_stop(app, engine):
    app.start_button.invoke()
    engine.state = Snapshot(
        running=True, sent=1200, skipped=3, missed=2, next_in_s=252.9, stops_in_s=725.0
    )

    app._render(engine.snapshot())

    assert app.status.get() == "Running. Next action in 4 min 12 s. Stops in 12 min 5 s."
    assert app.counts.get() == "Sent 1,200 · skipped 3 · missed 2"


def test_engine_stopping_by_itself_is_explained(app, engine):
    app.start_button.invoke()
    engine.state = Snapshot(sent=1, stop_reason=StopReason.ERROR, error="OSError: boom")

    app._render(engine.snapshot())

    assert app.status.get() == "Stopped after an error: OSError: boom"
    assert app.start_button.cget("text") == "Start (F6)"


def test_shutdown_stops_the_engine_and_the_hotkey(app, engine, hotkey):
    app.start_button.invoke()

    app.shutdown()

    assert engine.stop_calls == 1
    assert not hotkey.running


# Hotkey


def test_hotkey_is_f6_by_default_and_can_be_changed(app, hotkey):
    assert hotkey.keycode == F6
    assert hotkey.on_press is not None

    app.hotkey_name.set("F8")

    assert hotkey.keycode == F8
    assert app.start_button.cget("text") == "Start (F8)"


def test_hotkey_press_starts_on_the_next_poll_not_on_the_hotkey_thread(app, engine):
    hotkey_press = app.hotkey.on_press

    hotkey_press()
    assert engine.started_with is None

    app._poll()

    assert engine.started_with == app.build_config()
    assert app.start_button.cget("text") == "Stop (F6)"


def test_hotkey_press_stops_at_once_without_waiting_for_a_poll(app, engine):
    app.start_button.invoke()

    app.hotkey.on_press()

    assert engine.stop_calls == 1
    app._poll()
    assert engine.started_with is not None
    assert not engine.running


def test_hotkey_press_cannot_start_an_invalid_form(app, engine):
    app.hold.set("0")

    app.hotkey.on_press()
    app._poll()

    assert engine.started_with is None


def test_fast_mode_is_allowed_while_the_hotkey_works(app):
    assert enabled(app.preset_buttons[50])

    app.preset_buttons[50].invoke()

    assert app.build_config().interval_ms == 50
    assert app.interval_note.cget("text") == "50 ms = 20 key presses per second"
    assert enabled(app.start_button)


# Permissions


def test_no_permission_panel_when_everything_is_granted(app, hotkey):
    assert not shown(app.permission_panel)
    assert hotkey.start_calls == 1
    assert "Starts and stops from any app" in app.hotkey_note.cget("text")


def test_missing_accessibility_shows_the_panel_and_blocks_start(make_app, system, engine):
    system.accessibility = False

    app = make_app()

    assert shown(app.permission_panel)
    assert shown(app.accessibility_row)
    assert not shown(app.input_monitoring_row)
    assert not enabled(app.start_button)
    app.hotkey.on_press()
    app._poll()
    assert engine.started_with is None


def test_accessibility_button_registers_the_app_and_opens_the_right_pane(make_app, system):
    system.accessibility = False
    app = make_app()

    app.accessibility_button.invoke()

    assert system.calls == ["request_accessibility", "open_accessibility_settings"]


def test_check_again_hides_the_panel_once_accessibility_is_granted(make_app, system):
    system.accessibility = False
    app = make_app()
    system.accessibility = True

    app.recheck_button.invoke()

    assert not shown(app.permission_panel)
    assert enabled(app.start_button)


def test_missing_input_monitoring_blocks_fast_mode_only(make_app, system, hotkey):
    system.input_monitoring = False
    hotkey.allowed = False

    app = make_app()

    # Not even tried at launch: trying is what makes macOS show its prompt.
    assert hotkey.start_calls == 0
    assert shown(app.permission_panel)
    assert shown(app.input_monitoring_row)
    assert not shown(app.accessibility_row)
    assert app.hotkey_note.cget("text") == "Not working: needs Input Monitoring."
    assert app.start_button.cget("text") == "Start"
    assert enabled(app.start_button)
    assert not enabled(app.preset_buttons[50])
    assert not enabled(app.preset_buttons[100])
    assert enabled(app.preset_buttons[1000])

    app.interval_value.set("100")
    app.interval_unit.set("ms")

    assert "need the stop hotkey" in app.interval_note.cget("text")
    assert not enabled(app.start_button)


def test_input_monitoring_button_registers_the_app_and_opens_the_right_pane(
    make_app, system, hotkey
):
    system.input_monitoring = False
    hotkey.allowed = False
    app = make_app()

    app.input_monitoring_button.invoke()

    assert system.calls == ["request_input_monitoring", "open_input_monitoring_settings"]


def test_check_again_starts_the_hotkey_and_unlocks_fast_mode(make_app, system, hotkey):
    system.input_monitoring = False
    hotkey.allowed = False
    app = make_app()
    app.interval_value.set("100")
    app.interval_unit.set("ms")
    # macOS keeps reporting the old answer until the app restarts, so the
    # button tries the listener itself.
    hotkey.allowed = True

    app.recheck_button.invoke()

    assert hotkey.running
    assert not shown(app.permission_panel)
    assert app.interval_note.cget("text") == "100 ms = 10 key presses per second"
    assert enabled(app.start_button)
    assert app.start_button.cget("text") == "Start (F6)"


def test_accessibility_removed_while_open_is_caught_when_start_is_pressed(app, system, engine):
    system.accessibility = False

    app.start_button.invoke()

    assert engine.started_with is None
    assert shown(app.permission_panel)
    assert not enabled(app.start_button)


def test_run_ended_by_a_lost_permission_brings_the_panel_back(app, system, engine):
    app.start_button.invoke()
    system.accessibility = False
    engine.state = Snapshot(sent=2, stop_reason=StopReason.PERMISSION)

    app._render(engine.snapshot())

    assert app.status.get() == "Stopped: the Accessibility permission was removed."
    assert shown(app.permission_panel)
    assert not enabled(app.start_button)
