import pytest

from autoclick.actions import (
    Click,
    KeyTap,
    effective_hold_ms,
    validate_hold_ms,
    validate_interval_ms,
)
from autoclick.backend.base import MouseButton


@pytest.mark.parametrize("interval_ms", [10, 500, 3_600_000])
def test_interval_inside_range_is_accepted(interval_ms):
    assert validate_interval_ms(interval_ms) == interval_ms


@pytest.mark.parametrize("interval_ms", [9, 0, -100, 3_600_001])
def test_interval_outside_range_is_rejected_not_clamped(interval_ms):
    with pytest.raises(ValueError, match="between 10 ms and 1 hour"):
        validate_interval_ms(interval_ms)


@pytest.mark.parametrize("interval_ms", [100.0, "100", True, None])
def test_interval_must_be_whole_milliseconds(interval_ms):
    with pytest.raises(ValueError, match="whole number"):
        validate_interval_ms(interval_ms)


@pytest.mark.parametrize("hold_ms", [0, -1, 10_001])
def test_hold_outside_range_is_rejected(hold_ms):
    with pytest.raises(ValueError, match="Hold must be between"):
        validate_hold_ms(hold_ms)


def test_hold_is_kept_when_it_fits_in_half_the_interval():
    assert effective_hold_ms(80, 1000) == 80
    assert effective_hold_ms(50, 100) == 50


def test_hold_is_cut_to_half_of_a_short_interval():
    assert effective_hold_ms(80, 100) == 50
    assert effective_hold_ms(80, 10) == 5


def test_hold_budget_is_shared_between_actions():
    assert effective_hold_ms(80, 100, action_count=2) == 25


def test_click_defaults_to_left_button_at_the_cursor():
    click = Click()

    assert click.button is MouseButton.LEFT
    assert click.position is None


def test_click_rejects_bad_hold_and_position():
    with pytest.raises(ValueError, match="Hold"):
        Click(hold_ms=0)
    with pytest.raises(ValueError, match="Position"):
        Click(position=(1, 2, 3))


def test_key_tap_resolves_its_keycode():
    assert KeyTap("Space").keycode == 49


def test_key_tap_rejects_unknown_key():
    with pytest.raises(ValueError, match="Unknown key"):
        KeyTap("hyper")
