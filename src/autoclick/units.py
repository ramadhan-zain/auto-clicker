"""Turns what the user types into milliseconds, and milliseconds into text."""

from decimal import Decimal, InvalidOperation

from autoclick.actions import validate_hold_ms, validate_interval_ms

UNITS: dict[str, int] = {"ms": 1, "s": 1_000, "min": 60_000}
MAX_AUTO_STOP_MIN = 1_440


def parse_interval(text: str, unit: str) -> int:
    """Convert a number and a unit to whole milliseconds, or raise ValueError."""
    try:
        value = Decimal(text.strip())
    except InvalidOperation:
        raise ValueError("Interval must be a number.") from None
    if not value.is_finite():
        raise ValueError("Interval must be a number.")
    interval_ms = value * UNITS[unit]
    if interval_ms != interval_ms.to_integral_value():
        raise ValueError("Interval must be a whole number of milliseconds.")
    return validate_interval_ms(int(interval_ms))


def parse_hold(text: str) -> int:
    try:
        hold_ms = int(text.strip())
    except ValueError:
        raise ValueError("Hold must be a whole number of milliseconds.") from None
    return validate_hold_ms(hold_ms)


def parse_auto_stop(text: str) -> float:
    """Convert minutes typed by the user to seconds, or raise ValueError."""
    try:
        minutes = Decimal(text.strip())
    except InvalidOperation:
        raise ValueError("Auto-stop must be a number of minutes.") from None
    if not minutes.is_finite() or not 0 < minutes <= MAX_AUTO_STOP_MIN:
        raise ValueError(f"Auto-stop must be between 0 and {MAX_AUTO_STOP_MIN:,} minutes.")
    return float(minutes * 60)


def split_interval(interval_ms: int) -> tuple[str, str]:
    """Number and unit for the largest unit that divides the interval evenly."""
    for unit in ("min", "s"):
        if interval_ms % UNITS[unit] == 0:
            return str(interval_ms // UNITS[unit]), unit
    return str(interval_ms), "ms"


def format_interval(interval_ms: int) -> str:
    return " ".join(split_interval(interval_ms))


def describe_rate(interval_ms: int, noun: str) -> str:
    """Interval with its rate, such as "50 ms = 20 clicks per second"."""
    per_second = 1000 / interval_ms
    amount, period = per_second * 3600, "hour"
    if per_second >= 1:
        amount, period = per_second, "second"
    elif per_second * 60 >= 1:
        amount, period = per_second * 60, "minute"
    number = f"{amount:.3g}"
    if number != "1":
        noun += "es" if noun.endswith("s") else "s"
    return f"{format_interval(interval_ms)} = {number} {noun} per {period}"


def format_countdown(seconds: float) -> str:
    if seconds >= 60:
        minutes, rest = divmod(int(seconds), 60)
        return f"{minutes} min {rest} s"
    if seconds >= 10:
        return f"{int(seconds)} s"
    return f"{seconds:.1f} s"
