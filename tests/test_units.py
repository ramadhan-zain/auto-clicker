import pytest

from autoclick import units


@pytest.mark.parametrize(
    ("text", "unit", "expected"),
    [
        ("50", "ms", 50),
        ("1", "s", 1000),
        ("0.1", "s", 100),
        ("1.5", "s", 1500),
        ("5", "min", 300_000),
        ("0.5", "min", 30_000),
        (" 60 ", "min", 3_600_000),
    ],
)
def test_parse_interval_converts_to_whole_milliseconds(text, unit, expected):
    assert units.parse_interval(text, unit) == expected


@pytest.mark.parametrize("text", ["", "abc", "1,5", "nan", "inf"])
def test_parse_interval_rejects_text_that_is_not_a_number(text):
    with pytest.raises(ValueError, match="must be a number"):
        units.parse_interval(text, "s")


@pytest.mark.parametrize(("text", "unit"), [("10.5", "ms"), ("0.0015", "s")])
def test_parse_interval_rejects_fractions_of_a_millisecond(text, unit):
    with pytest.raises(ValueError, match="whole number of milliseconds"):
        units.parse_interval(text, unit)


@pytest.mark.parametrize(("text", "unit"), [("9", "ms"), ("0", "s"), ("-1", "s"), ("61", "min")])
def test_parse_interval_rejects_values_outside_10_ms_to_1_hour(text, unit):
    with pytest.raises(ValueError, match="between 10 ms and 1 hour"):
        units.parse_interval(text, unit)


@pytest.mark.parametrize(("text", "seconds"), [("30", 1800), (" 1.5 ", 90), ("1440", 86_400)])
def test_parse_auto_stop_converts_minutes_to_seconds(text, seconds):
    assert units.parse_auto_stop(text) == seconds


@pytest.mark.parametrize("text", ["", "abc", "nan", "0", "-1", "1441"])
def test_parse_auto_stop_rejects_bad_values(text):
    with pytest.raises(ValueError, match="Auto-stop must be"):
        units.parse_auto_stop(text)


def test_parse_hold_accepts_whole_milliseconds_only():
    assert units.parse_hold(" 80 ") == 80
    with pytest.raises(ValueError, match="whole number"):
        units.parse_hold("80.5")
    with pytest.raises(ValueError, match="between 1 and 10,000"):
        units.parse_hold("0")


@pytest.mark.parametrize(
    ("interval_ms", "expected"),
    [(50, "50 ms"), (1000, "1 s"), (1500, "1500 ms"), (90_000, "90 s"), (300_000, "5 min")],
)
def test_format_interval_uses_the_largest_exact_unit(interval_ms, expected):
    assert units.format_interval(interval_ms) == expected


@pytest.mark.parametrize(
    ("interval_ms", "noun", "expected"),
    [
        (50, "click", "50 ms = 20 clicks per second"),
        (1000, "click", "1 s = 1 click per second"),
        (300, "click", "300 ms = 3.33 clicks per second"),
        (5000, "key press", "5 s = 12 key presses per minute"),
        (300_000, "key press", "5 min = 12 key presses per hour"),
        (3_600_000, "key press", "60 min = 1 key press per hour"),
    ],
)
def test_describe_rate(interval_ms, noun, expected):
    assert units.describe_rate(interval_ms, noun) == expected


@pytest.mark.parametrize(
    ("seconds", "expected"),
    [(0.44, "0.4 s"), (9.96, "10.0 s"), (12.7, "12 s"), (60, "1 min 0 s"), (252.9, "4 min 12 s")],
)
def test_format_countdown(seconds, expected):
    assert units.format_countdown(seconds) == expected
