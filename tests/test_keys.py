import pytest

from autoclick.keys import FUNCTION_KEYCODES, KEYCODES, keycode


@pytest.mark.parametrize(
    ("name", "expected"),
    [("space", 49), ("w", 13), ("a", 0), ("s", 1), ("d", 2), ("return", 36)],
)
def test_known_keys(name, expected):
    assert keycode(name) == expected


def test_lookup_ignores_case_and_surrounding_spaces():
    assert keycode("  Space ") == 49


def test_unknown_key_is_rejected():
    with pytest.raises(ValueError, match="Unknown key"):
        keycode("hyper")


def test_keycodes_are_unique():
    assert len(set(KEYCODES.values())) == len(KEYCODES)


def test_function_keys_are_separate_from_the_keys_that_can_be_sent():
    assert FUNCTION_KEYCODES["F6"] == 97
    assert len(set(FUNCTION_KEYCODES.values())) == 12
    assert not set(FUNCTION_KEYCODES.values()) & set(KEYCODES.values())
