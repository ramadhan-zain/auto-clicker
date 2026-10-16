"""macOS virtual key codes.

These identify physical key positions on an ANSI keyboard, not characters, so
"w" is the key in the W position regardless of the active keyboard layout.
"""

KEYCODES: dict[str, int] = {
    "a": 0, "s": 1, "d": 2, "f": 3, "h": 4, "g": 5, "z": 6, "x": 7, "c": 8, "v": 9,
    "b": 11, "q": 12, "w": 13, "e": 14, "r": 15, "y": 16, "t": 17,
    "1": 18, "2": 19, "3": 20, "4": 21, "6": 22, "5": 23, "9": 25, "7": 26, "8": 28, "0": 29,
    "o": 31, "u": 32, "i": 34, "p": 35, "l": 37, "j": 38, "k": 40, "n": 45, "m": 46,
    "return": 36, "tab": 48, "space": 49, "escape": 53,
    "left": 123, "right": 124, "down": 125, "up": 126,
}  # fmt: skip

# Kept apart from KEYCODES: these are offered for the stop hotkey, not as keys
# to send.
FUNCTION_KEYCODES: dict[str, int] = {
    "F1": 122, "F2": 120, "F3": 99, "F4": 118, "F5": 96, "F6": 97,
    "F7": 98, "F8": 100, "F9": 101, "F10": 109, "F11": 103, "F12": 111,
}  # fmt: skip


def keycode(name: str) -> int:
    """Return the virtual key code for a key name such as "space" or "w"."""
    try:
        return KEYCODES[name.strip().lower()]
    except KeyError:
        raise ValueError(
            f"Unknown key {name!r}. Known keys: {', '.join(sorted(KEYCODES))}"
        ) from None
