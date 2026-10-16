from collections.abc import Callable

from autoclick.backend.base import MouseButton, Point


class FakeBackend:
    """Records every call instead of sending input. Used by tests."""

    def __init__(
        self,
        cursor: Point = (0.0, 0.0),
        on_call: Callable[[tuple], None] | None = None,
    ) -> None:
        self.cursor = cursor
        self.calls: list[tuple] = []
        self._on_call = on_call

    def cursor_position(self) -> Point:
        return self.cursor

    def mouse_move(self, pos: Point) -> None:
        self._record("mouse_move", pos)

    def mouse_down(self, button: MouseButton, pos: Point) -> None:
        self._record("mouse_down", button, pos)

    def mouse_up(self, button: MouseButton, pos: Point) -> None:
        self._record("mouse_up", button, pos)

    def key_down(self, keycode: int) -> None:
        self._record("key_down", keycode)

    def key_up(self, keycode: int) -> None:
        self._record("key_up", keycode)

    def _record(self, *call) -> None:
        self.calls.append(call)
        if self._on_call is not None:
            self._on_call(call)
