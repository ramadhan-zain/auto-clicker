"""What the engine can send, and the limits on how often."""

from dataclasses import dataclass

from autoclick.backend.base import MouseButton, Point
from autoclick.keys import keycode

MIN_INTERVAL_MS = 10
MAX_INTERVAL_MS = 3_600_000
# Below this the mouse clicks too often for the Stop button to be reliable.
FAST_MODE_BELOW_MS = 500

MIN_HOLD_MS = 1
MAX_HOLD_MS = 10_000
DEFAULT_HOLD_MS = 80


def _is_whole_number(value: object) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def validate_interval_ms(interval_ms: int) -> int:
    """Return the interval unchanged, or raise ValueError. Never clamps."""
    if not _is_whole_number(interval_ms):
        raise ValueError(f"Interval must be a whole number of milliseconds, got {interval_ms!r}.")
    if not MIN_INTERVAL_MS <= interval_ms <= MAX_INTERVAL_MS:
        raise ValueError(
            f"Interval must be between {MIN_INTERVAL_MS} ms and 1 hour, got {interval_ms:,} ms."
        )
    return interval_ms


def validate_hold_ms(hold_ms: int) -> int:
    if not _is_whole_number(hold_ms):
        raise ValueError(f"Hold must be a whole number of milliseconds, got {hold_ms!r}.")
    if not MIN_HOLD_MS <= hold_ms <= MAX_HOLD_MS:
        raise ValueError(
            f"Hold must be between {MIN_HOLD_MS} and {MAX_HOLD_MS:,} ms, got {hold_ms:,} ms."
        )
    return hold_ms


def effective_hold_ms(hold_ms: int, interval_ms: int, action_count: int = 1) -> float:
    """Hold the engine really uses: all holds together take at most half the interval."""
    return min(hold_ms, interval_ms / (2 * action_count))


@dataclass(frozen=True)
class Click:
    button: MouseButton = MouseButton.LEFT
    # None presses wherever the cursor is when the tick fires, and releases
    # wherever it is by then.
    position: Point | None = None
    hold_ms: int = DEFAULT_HOLD_MS
    # Roblox may ignore a click that is not preceded by mouse movement.
    nudge: bool = True

    def __post_init__(self) -> None:
        validate_hold_ms(self.hold_ms)
        if self.position is not None and len(self.position) != 2:
            raise ValueError(f"Position must be an (x, y) pair, got {self.position!r}.")


@dataclass(frozen=True)
class KeyTap:
    key: str
    hold_ms: int = DEFAULT_HOLD_MS

    def __post_init__(self) -> None:
        keycode(self.key)
        validate_hold_ms(self.hold_ms)

    @property
    def keycode(self) -> int:
        return keycode(self.key)


Action = Click | KeyTap
