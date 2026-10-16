from collections.abc import Callable

import pytest


class FakeClock:
    """Clock that only moves when something sleeps on it.

    Callbacks registered with `at` run from inside `sleep` when their time is
    reached, which is how tests press Stop or switch apps mid-run.
    """

    def __init__(self) -> None:
        self._now = 0.0
        self._timers: list[tuple[float, Callable[[], None]]] = []

    def now(self) -> float:
        return self._now

    def sleep(self, seconds: float) -> None:
        target = self._now + seconds
        while self._timers and self._timers[0][0] <= target:
            when, callback = self._timers.pop(0)
            self._now = max(self._now, when)
            callback()
        self._now = max(self._now, target)

    def advance(self, seconds: float) -> None:
        """Jump ahead without running timers, like a stalled thread."""
        self._now += seconds

    def at(self, when: float, callback: Callable[[], None]) -> None:
        self._timers.append((when, callback))
        self._timers.sort(key=lambda timer: timer[0])


@pytest.fixture
def clock() -> FakeClock:
    return FakeClock()
