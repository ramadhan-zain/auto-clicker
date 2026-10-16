"""Worker that sends the configured actions on a timer."""

import threading
import time
from collections.abc import Callable
from dataclasses import dataclass, replace
from enum import Enum
from typing import Protocol

from autoclick.actions import Action, Click, effective_hold_ms, validate_interval_ms
from autoclick.backend.base import InputBackend

# A single long sleep overshoots by up to 20 ms on macOS, so the last stretch
# before a deadline is waited in 1 ms steps. Further out, coarser steps keep
# the idle cost low while still noticing Stop well within 100 ms.
_FINE_WINDOW_S = 0.025
_FINE_STEP_S = 0.001
_COARSE_STEP_S = 0.05

# Asking the window server costs about 1.4 ms, too much for every fast click.
_FOCUS_CACHE_S = 0.25


class Clock(Protocol):
    def now(self) -> float:
        """Monotonic time in seconds."""
        ...

    def sleep(self, seconds: float) -> None: ...


class SystemClock:
    def now(self) -> float:
        return time.perf_counter()

    def sleep(self, seconds: float) -> None:
        time.sleep(seconds)


class StopReason(Enum):
    USER = "user"
    AUTO_STOP = "auto_stop"
    PERMISSION = "permission"
    ERROR = "error"


@dataclass(frozen=True)
class EngineConfig:
    actions: tuple[Action, ...]
    interval_ms: int
    # Input is only sent while this app is frontmost. None sends to any app.
    target_bundle_id: str | None = None
    auto_stop_after_s: float | None = None
    # Time before the first tick, so the user can switch to the target app.
    start_delay_ms: int = 0

    def __post_init__(self) -> None:
        object.__setattr__(self, "actions", tuple(self.actions))
        if not self.actions:
            raise ValueError("At least one action is required.")
        validate_interval_ms(self.interval_ms)
        if self.auto_stop_after_s is not None and self.auto_stop_after_s <= 0:
            raise ValueError(f"Auto-stop must be positive, got {self.auto_stop_after_s!r}.")
        if self.start_delay_ms < 0:
            raise ValueError(f"Start delay cannot be negative, got {self.start_delay_ms!r}.")


@dataclass(frozen=True)
class Snapshot:
    """Engine state at one moment, safe to read from the UI thread."""

    running: bool = False
    sent: int = 0
    # Ticks not sent because the target app was not frontmost.
    skipped: int = 0
    # Ticks dropped because the engine fell behind schedule.
    missed: int = 0
    next_in_s: float | None = None
    # Time left before auto-stop, when one is set.
    stops_in_s: float | None = None
    stop_reason: StopReason | None = None
    error: str | None = None


class Engine:
    """Runs one configuration at a time on a worker thread.

    `run` is the blocking loop; `start` runs it on a thread. Whatever ends the
    loop, any key or button that is down is released first.
    """

    def __init__(
        self,
        backend: InputBackend,
        clock: Clock | None = None,
        frontmost: Callable[[], str | None] = lambda: None,
        permission_granted: Callable[[], bool] = lambda: True,
    ) -> None:
        self._backend = backend
        self._clock = clock or SystemClock()
        self._frontmost = frontmost
        self._permission_granted = permission_granted
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._lock = threading.Lock()
        self._snapshot = Snapshot()
        self._next_tick_at: float | None = None
        self._auto_stop_at: float | None = None
        self._focus_checked_at: float | None = None
        self._focus_ok = False

    @property
    def running(self) -> bool:
        return self.snapshot().running

    def snapshot(self) -> Snapshot:
        with self._lock:
            snapshot, next_tick_at = self._snapshot, self._next_tick_at
            auto_stop_at = self._auto_stop_at
        if not snapshot.running or next_tick_at is None:
            return snapshot
        now = self._clock.now()
        return replace(
            snapshot,
            next_in_s=max(0.0, next_tick_at - now),
            stops_in_s=None if auto_stop_at is None else max(0.0, auto_stop_at - now),
        )

    def start(self, config: EngineConfig) -> None:
        if self.running:
            raise RuntimeError("Engine is already running.")
        self._stop.clear()
        # Published here as well, so `running` is true as soon as start returns.
        self._publish(Snapshot(running=True), None)
        self._thread = threading.Thread(
            target=self._loop, args=(config,), name="autoclick-engine", daemon=True
        )
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()

    def join(self, timeout: float | None = None) -> None:
        if self._thread is not None:
            self._thread.join(timeout)

    def run(self, config: EngineConfig) -> StopReason:
        """Run on the calling thread until stopped."""
        self._stop.clear()
        return self._loop(config)

    def _loop(self, config: EngineConfig) -> StopReason:
        clock = self._clock
        interval_s = config.interval_ms / 1000
        actions = [
            (action, effective_hold_ms(action.hold_ms, config.interval_ms, len(config.actions)))
            for action in config.actions
        ]
        started_at = clock.now()
        first_tick_at = started_at + config.start_delay_ms / 1000
        auto_stop_at = (
            None if config.auto_stop_after_s is None else started_at + config.auto_stop_after_s
        )
        self._focus_checked_at = None
        self._auto_stop_at = auto_stop_at
        # Ticks sit on a fixed grid (first + n * interval), so neither the time
        # spent sending nor rounding accumulates as drift.
        tick = 0
        next_tick_at = first_tick_at
        sent = skipped = missed = 0
        reason = StopReason.USER
        error = None
        self._publish(Snapshot(running=True), next_tick_at)
        try:
            while True:
                if auto_stop_at is not None and auto_stop_at <= next_tick_at:
                    if self._wait_until(auto_stop_at):
                        reason = StopReason.AUTO_STOP
                    break
                if not self._wait_until(next_tick_at):
                    break
                if not self._permission_granted():
                    reason = StopReason.PERMISSION
                    break
                if self._target_is_front(config.target_bundle_id):
                    sent += 1
                    if not self._perform_all(actions):
                        break
                else:
                    skipped += 1
                tick += 1
                behind_s = clock.now() - (first_tick_at + tick * interval_s)
                if behind_s > interval_s:
                    # More than one interval late: drop every tick already in
                    # the past instead of firing a catch-up burst. A tick that
                    # is late by less fires at once, which keeps the average
                    # rate exact when a fast click runs a few ms over.
                    lost = int(behind_s // interval_s) + 1
                    missed += lost
                    tick += lost
                next_tick_at = first_tick_at + tick * interval_s
                self._publish(
                    Snapshot(running=True, sent=sent, skipped=skipped, missed=missed),
                    next_tick_at,
                )
        except Exception as exc:
            reason = StopReason.ERROR
            error = f"{type(exc).__name__}: {exc}"
        finally:
            self._publish(
                Snapshot(
                    sent=sent, skipped=skipped, missed=missed, stop_reason=reason, error=error
                ),
                None,
            )
        return reason

    def _publish(self, snapshot: Snapshot, next_tick_at: float | None) -> None:
        with self._lock:
            self._snapshot = snapshot
            self._next_tick_at = next_tick_at

    def _wait_until(self, deadline: float) -> bool:
        """Wait for a clock deadline. False means Stop was requested first."""
        while not self._stop.is_set():
            remaining = deadline - self._clock.now()
            if remaining <= 0:
                return True
            # A coarse step is only taken when it ends outside the fine window.
            # Shrinking it to fit instead could ask for a sleep too small to
            # move the clock at all.
            coarse = remaining > _FINE_WINDOW_S + _COARSE_STEP_S
            self._clock.sleep(_COARSE_STEP_S if coarse else min(remaining, _FINE_STEP_S))
        return False

    def _target_is_front(self, target_bundle_id: str | None) -> bool:
        if target_bundle_id is None:
            return True
        now = self._clock.now()
        if self._focus_checked_at is None or now - self._focus_checked_at >= _FOCUS_CACHE_S:
            self._focus_ok = self._frontmost() == target_bundle_id
            self._focus_checked_at = now
        return self._focus_ok

    def _perform_all(self, actions: list[tuple[Action, float]]) -> bool:
        """Send each action in turn. False means Stop interrupted them."""
        for action, hold_ms in actions:
            if not self._perform(action, hold_ms / 1000):
                return False
        return True

    def _perform(self, action: Action, hold_s: float) -> bool:
        backend = self._backend
        if isinstance(action, Click):
            pos = action.position if action.position is not None else backend.cursor_position()
            if action.nudge:
                backend.mouse_move((pos[0] + 1, pos[1]))
                backend.mouse_move(pos)
            backend.mouse_down(action.button, pos)
            try:
                return self._wait_until(self._clock.now() + hold_s)
            finally:
                # Posting at the press point would drag a cursor that moved
                # during the hold back to it.
                if action.position is None:
                    pos = backend.cursor_position()
                backend.mouse_up(action.button, pos)
        code = action.keycode
        backend.key_down(code)
        try:
            return self._wait_until(self._clock.now() + hold_s)
        finally:
            backend.key_up(code)
