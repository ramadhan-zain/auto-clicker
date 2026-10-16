from enum import Enum
from typing import Protocol

Point = tuple[float, float]


class MouseButton(Enum):
    LEFT = "left"
    RIGHT = "right"


class InputBackend(Protocol):
    """Low-level input primitives.

    Down and up are separate so the caller controls the hold duration and can
    release early when asked to stop.
    """

    def cursor_position(self) -> Point: ...

    def mouse_move(self, pos: Point) -> None: ...

    def mouse_down(self, button: MouseButton, pos: Point) -> None: ...

    def mouse_up(self, button: MouseButton, pos: Point) -> None: ...

    def key_down(self, keycode: int) -> None: ...

    def key_up(self, keycode: int) -> None: ...
