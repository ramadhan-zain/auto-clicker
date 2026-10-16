import time

import pytest

from autoclick.actions import Click, KeyTap
from autoclick.backend.base import MouseButton
from autoclick.backend.fake import FakeBackend
from autoclick.engine import Engine, EngineConfig, StopReason

SPACE = 49
ROBLOX = "com.roblox.RobloxPlayer"


class Recorder:
    """Fake backend that also notes the clock time of every call."""

    def __init__(self, clock, **backend_options):
        self.clock = clock
        self.times: list[tuple[str, float]] = []
        self.backend = FakeBackend(on_call=self._note, **backend_options)

    def _note(self, call):
        self.times.append((call[0], self.clock.now()))

    def times_of(self, name):
        return [when for call, when in self.times if call == name]


@pytest.fixture
def recorder(clock):
    return Recorder(clock)


def config(interval_ms=1000, action=None, **options):
    return EngineConfig(actions=(action or KeyTap("space"),), interval_ms=interval_ms, **options)


def test_ticks_fire_one_interval_apart(clock, recorder):
    engine = Engine(recorder.backend, clock)
    clock.at(3.5, engine.stop)

    reason = engine.run(config(interval_ms=1000))

    assert reason is StopReason.USER
    assert recorder.times_of("key_down") == pytest.approx([0.0, 1.0, 2.0, 3.0])
    assert engine.snapshot().sent == 4


def test_key_tap_is_down_then_up_after_the_hold(clock, recorder):
    engine = Engine(recorder.backend, clock)
    clock.at(0.5, engine.stop)

    engine.run(config(action=KeyTap("space", hold_ms=80)))

    assert recorder.backend.calls == [("key_down", SPACE), ("key_up", SPACE)]
    assert recorder.times == [("key_down", 0.0), ("key_up", pytest.approx(0.08))]


def test_click_at_cursor_nudges_then_presses_where_the_cursor_is(clock):
    backend = FakeBackend(cursor=(200.0, 300.0))
    engine = Engine(backend, clock)
    clock.at(0.5, engine.stop)

    engine.run(config(action=Click(MouseButton.RIGHT)))

    assert backend.calls == [
        ("mouse_move", (201.0, 300.0)),
        ("mouse_move", (200.0, 300.0)),
        ("mouse_down", MouseButton.RIGHT, (200.0, 300.0)),
        ("mouse_up", MouseButton.RIGHT, (200.0, 300.0)),
    ]


def test_click_at_cursor_releases_where_the_cursor_moved_to(clock):
    backend = FakeBackend(cursor=(200.0, 300.0))
    engine = Engine(backend, clock)
    clock.at(0.04, lambda: setattr(backend, "cursor", (250.0, 320.0)))
    clock.at(0.5, engine.stop)

    engine.run(config(action=Click(hold_ms=80, nudge=False)))

    assert backend.calls == [
        ("mouse_down", MouseButton.LEFT, (200.0, 300.0)),
        ("mouse_up", MouseButton.LEFT, (250.0, 320.0)),
    ]


def test_click_at_saved_position_ignores_the_cursor(clock):
    backend = FakeBackend(cursor=(1.0, 1.0))
    engine = Engine(backend, clock)
    clock.at(0.5, engine.stop)

    engine.run(config(action=Click(position=(640.0, 480.0), nudge=False)))

    assert backend.calls == [
        ("mouse_down", MouseButton.LEFT, (640.0, 480.0)),
        ("mouse_up", MouseButton.LEFT, (640.0, 480.0)),
    ]


def test_start_delay_postpones_the_first_tick(clock, recorder):
    engine = Engine(recorder.backend, clock)
    clock.at(4.5, engine.stop)

    engine.run(config(interval_ms=1000, start_delay_ms=3000))

    assert recorder.times_of("key_down") == pytest.approx([3.0, 4.0])


def test_stop_during_a_long_wait_is_honoured_within_100_ms(clock, recorder):
    engine = Engine(recorder.backend, clock)
    clock.at(10.0, engine.stop)

    engine.run(config(interval_ms=300_000))

    assert clock.now() - 10.0 <= 0.1
    assert engine.snapshot().sent == 1
    assert not engine.running


def test_stop_in_the_middle_of_a_hold_releases_the_key(clock, recorder):
    engine = Engine(recorder.backend, clock)
    clock.at(0.3, engine.stop)

    engine.run(config(interval_ms=5000, action=KeyTap("space", hold_ms=2000)))

    assert recorder.backend.calls == [("key_down", SPACE), ("key_up", SPACE)]
    assert recorder.times_of("key_up")[0] - 0.3 <= 0.1


def test_stop_in_the_middle_of_a_hold_releases_the_mouse_button(clock, recorder):
    engine = Engine(recorder.backend, clock)
    clock.at(0.3, engine.stop)

    engine.run(config(interval_ms=5000, action=Click(hold_ms=2000, nudge=False)))

    assert [call[0] for call in recorder.backend.calls] == ["mouse_down", "mouse_up"]
    assert recorder.times_of("mouse_up")[0] - 0.3 <= 0.1


def test_backend_error_releases_the_key_and_is_reported(clock):
    class BrokenClock:
        """Fails on the first sleep after the key goes down."""

        def __init__(self):
            self.armed = False

        def now(self):
            return clock.now()

        def sleep(self, seconds):
            if self.armed:
                raise OSError("boom")
            clock.sleep(seconds)

    broken = BrokenClock()
    backend = FakeBackend(on_call=lambda call: setattr(broken, "armed", True))
    engine = Engine(backend, broken)

    reason = engine.run(config())

    assert reason is StopReason.ERROR
    assert backend.calls == [("key_down", SPACE), ("key_up", SPACE)]
    snapshot = engine.snapshot()
    assert not snapshot.running
    assert snapshot.error == "OSError: boom"


def test_ticks_are_skipped_and_counted_while_target_is_not_frontmost(clock, recorder):
    front = {"app": "com.apple.finder"}
    engine = Engine(recorder.backend, clock, frontmost=lambda: front["app"])
    clock.at(2.5, lambda: front.update(app=ROBLOX))
    clock.at(4.5, lambda: front.update(app="com.apple.finder"))
    clock.at(6.5, engine.stop)

    engine.run(config(interval_ms=1000, target_bundle_id=ROBLOX))

    assert recorder.times_of("key_down") == pytest.approx([3.0, 4.0])
    snapshot = engine.snapshot()
    assert (snapshot.sent, snapshot.skipped) == (2, 5)


def test_skipped_ticks_are_not_sent_later_as_a_burst(clock, recorder):
    front = {"app": None}
    engine = Engine(recorder.backend, clock, frontmost=lambda: front["app"])
    clock.at(9.5, lambda: front.update(app=ROBLOX))
    clock.at(10.5, engine.stop)

    engine.run(config(interval_ms=1000, target_bundle_id=ROBLOX))

    assert recorder.times_of("key_down") == pytest.approx([10.0])


def test_focus_is_checked_at_most_every_250_ms_in_fast_mode(clock, recorder):
    checks = []

    def frontmost():
        checks.append(clock.now())
        return ROBLOX

    engine = Engine(recorder.backend, clock, frontmost=frontmost)
    clock.at(1.005, engine.stop)

    engine.run(config(interval_ms=10, target_bundle_id=ROBLOX))

    assert engine.snapshot().sent == 101
    assert checks == pytest.approx([0.0, 0.25, 0.5, 0.75, 1.0])


def test_no_guard_sends_to_any_app(clock, recorder):
    engine = Engine(recorder.backend, clock, frontmost=lambda: "com.apple.finder")
    clock.at(0.5, engine.stop)

    engine.run(config(target_bundle_id=None))

    assert engine.snapshot().sent == 1


def test_auto_stop_ends_the_run(clock, recorder):
    engine = Engine(recorder.backend, clock)

    reason = engine.run(config(interval_ms=1000, auto_stop_after_s=10))

    assert reason is StopReason.AUTO_STOP
    assert clock.now() == pytest.approx(10.0)
    snapshot = engine.snapshot()
    assert snapshot.sent == 10
    assert snapshot.stop_reason is StopReason.AUTO_STOP
    assert not snapshot.running


def test_missing_permission_stops_before_sending(clock, recorder):
    engine = Engine(recorder.backend, clock, permission_granted=lambda: False)

    reason = engine.run(config())

    assert reason is StopReason.PERMISSION
    assert recorder.backend.calls == []


def test_permission_removed_mid_run_stops_the_engine(clock, recorder):
    granted = {"value": True}
    engine = Engine(recorder.backend, clock, permission_granted=lambda: granted["value"])
    clock.at(2.5, lambda: granted.update(value=False))

    reason = engine.run(config(interval_ms=1000))

    assert reason is StopReason.PERMISSION
    assert engine.snapshot().sent == 3


@pytest.mark.parametrize("interval_ms", [9, 3_600_001, 0])
def test_config_rejects_interval_outside_range(interval_ms):
    with pytest.raises(ValueError, match="between 10 ms and 1 hour"):
        config(interval_ms=interval_ms)


def test_config_rejects_empty_actions_and_bad_auto_stop():
    with pytest.raises(ValueError, match="At least one action"):
        EngineConfig(actions=(), interval_ms=1000)
    with pytest.raises(ValueError, match="Auto-stop"):
        config(auto_stop_after_s=0)


def test_no_drift_over_1000_ticks_even_when_sending_takes_time(clock):
    # Every backend call costs 0.4 ms, which must not add up across ticks.
    recorder = Recorder(clock)
    backend = FakeBackend(on_call=lambda call: (recorder._note(call), clock.advance(0.0004)))
    engine = Engine(backend, clock)
    clock.at(49.955, engine.stop)

    engine.run(config(interval_ms=50, action=KeyTap("space", hold_ms=10)))

    downs = recorder.times_of("key_down")
    assert len(downs) == 1000
    assert downs[-1] == pytest.approx(999 * 0.05, abs=1e-6)
    assert max(abs(when - i * 0.05) for i, when in enumerate(downs)) < 1e-6
    assert engine.snapshot().missed == 0


def test_missed_ticks_are_skipped_not_fired_as_a_burst(clock):
    recorder = Recorder(clock)
    stalled = []

    def on_call(call):
        recorder._note(call)
        # The third key press stalls for 350 ms, longer than three intervals.
        if call[0] == "key_down" and len(recorder.times_of("key_down")) == 3 and not stalled:
            stalled.append(True)
            clock.advance(0.35)

    engine = Engine(FakeBackend(on_call=on_call), clock)
    clock.at(0.95, engine.stop)

    engine.run(config(interval_ms=100, action=KeyTap("space", hold_ms=10)))

    downs = recorder.times_of("key_down")
    # Ticks at 0.3, 0.4 and 0.5 fall inside the stall and are dropped; the
    # engine resumes on the original grid.
    assert downs == pytest.approx([0.0, 0.1, 0.2, 0.6, 0.7, 0.8, 0.9])
    snapshot = engine.snapshot()
    assert (snapshot.sent, snapshot.missed) == (7, 3)


def test_tick_late_by_less_than_an_interval_fires_at_once_and_keeps_the_grid(clock):
    recorder = Recorder(clock)
    stalled = []

    def on_call(call):
        recorder._note(call)
        # The second key press stalls for 150 ms, past the next tick at 0.2.
        if call[0] == "key_down" and len(recorder.times_of("key_down")) == 2 and not stalled:
            stalled.append(True)
            clock.advance(0.15)

    engine = Engine(FakeBackend(on_call=on_call), clock)
    clock.at(0.45, engine.stop)

    engine.run(config(interval_ms=100, action=KeyTap("space", hold_ms=10)))

    assert recorder.times_of("key_down") == pytest.approx([0.0, 0.1, 0.26, 0.3, 0.4])
    assert engine.snapshot().missed == 0


def test_hold_is_shortened_to_half_of_a_short_interval(clock, recorder):
    engine = Engine(recorder.backend, clock)
    clock.at(0.095, engine.stop)

    engine.run(config(interval_ms=100, action=KeyTap("space", hold_ms=80)))

    assert recorder.times == [("key_down", 0.0), ("key_up", pytest.approx(0.05))]


def test_several_actions_run_in_order_and_share_the_hold_budget(clock, recorder):
    engine = Engine(recorder.backend, clock)
    clock.at(0.095, engine.stop)

    engine.run(
        EngineConfig(
            actions=[KeyTap("space", hold_ms=80), KeyTap("w", hold_ms=10)], interval_ms=100
        )
    )

    assert recorder.backend.calls == [
        ("key_down", SPACE),
        ("key_up", SPACE),
        ("key_down", 13),
        ("key_up", 13),
    ]
    assert [when for _, when in recorder.times] == pytest.approx([0.0, 0.025, 0.025, 0.035])


def test_snapshot_reports_time_to_the_next_tick(clock, recorder):
    engine = Engine(recorder.backend, clock)
    seen = []
    clock.at(0.4, lambda: seen.append(engine.snapshot()))
    clock.at(0.5, engine.stop)

    engine.run(config(interval_ms=1000))

    assert seen[0].running
    assert seen[0].sent == 1
    assert seen[0].next_in_s == pytest.approx(0.6)
    assert seen[0].stops_in_s is None
    assert engine.snapshot().next_in_s is None


def test_snapshot_reports_time_to_auto_stop(clock, recorder):
    engine = Engine(recorder.backend, clock)
    seen = []
    clock.at(2.5, lambda: seen.append(engine.snapshot()))

    engine.run(config(interval_ms=1000, auto_stop_after_s=10))

    assert seen[0].stops_in_s == pytest.approx(7.5)
    assert engine.snapshot().stops_in_s is None


def test_engine_can_run_again_after_a_stop(clock, recorder):
    engine = Engine(recorder.backend, clock)
    clock.at(0.5, engine.stop)
    engine.run(config())
    clock.at(clock.now() + 0.5, engine.stop)

    engine.run(config())

    assert len(recorder.times_of("key_down")) == 2
    assert engine.snapshot().sent == 1


def test_start_runs_on_a_thread_and_stop_ends_it_quickly():
    backend = FakeBackend()
    engine = Engine(backend)

    engine.start(config(interval_ms=20, action=KeyTap("space", hold_ms=5)))
    assert engine.running
    with pytest.raises(RuntimeError, match="already running"):
        engine.start(config())
    time.sleep(0.15)
    stop_requested = time.perf_counter()
    engine.stop()
    engine.join(timeout=1.0)

    assert time.perf_counter() - stop_requested < 0.1
    assert not engine.running
    assert engine.snapshot().stop_reason is StopReason.USER
    assert engine.snapshot().sent >= 3
    assert backend.calls.count(("key_down", SPACE)) == backend.calls.count(("key_up", SPACE))
