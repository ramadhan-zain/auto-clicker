from collections.abc import Callable

import Quartz

from autoclick.backend.base import MouseButton, Point

_BUTTON_EVENTS = {
    MouseButton.LEFT: (
        Quartz.kCGEventLeftMouseDown,
        Quartz.kCGEventLeftMouseUp,
        Quartz.kCGMouseButtonLeft,
    ),
    MouseButton.RIGHT: (
        Quartz.kCGEventRightMouseDown,
        Quartz.kCGEventRightMouseUp,
        Quartz.kCGMouseButtonRight,
    ),
}


def _post_to_hid(event) -> None:
    Quartz.CGEventPost(Quartz.kCGHIDEventTap, event)


class QuartzBackend:
    """Sends input as Quartz events at the HID level.

    Posting needs the Accessibility permission. Without it macOS drops the
    events silently, so check `macos.accessibility_granted()` before use.
    """

    def __init__(self, post: Callable[[object], None] = _post_to_hid) -> None:
        self._post = post
        self._source = Quartz.CGEventSourceCreate(Quartz.kCGEventSourceStateHIDSystemState)

    def cursor_position(self) -> Point:
        location = Quartz.CGEventGetLocation(Quartz.CGEventCreate(None))
        return (location.x, location.y)

    def mouse_move(self, pos: Point) -> None:
        self._post_mouse(Quartz.kCGEventMouseMoved, pos, Quartz.kCGMouseButtonLeft)

    def mouse_down(self, button: MouseButton, pos: Point) -> None:
        down, _, cg_button = _BUTTON_EVENTS[button]
        self._post_mouse(down, pos, cg_button, click_state=1)

    def mouse_up(self, button: MouseButton, pos: Point) -> None:
        _, up, cg_button = _BUTTON_EVENTS[button]
        self._post_mouse(up, pos, cg_button, click_state=1)

    def key_down(self, keycode: int) -> None:
        self._post_key(keycode, True)

    def key_up(self, keycode: int) -> None:
        self._post_key(keycode, False)

    def _post_mouse(
        self, event_type: int, pos: Point, cg_button: int, click_state: int = 0
    ) -> None:
        event = Quartz.CGEventCreateMouseEvent(self._source, event_type, pos, cg_button)
        if click_state:
            Quartz.CGEventSetIntegerValueField(event, Quartz.kCGMouseEventClickState, click_state)
        self._post(event)

    def _post_key(self, keycode: int, is_down: bool) -> None:
        event = Quartz.CGEventCreateKeyboardEvent(self._source, keycode, is_down)
        # Drop modifiers the user happens to be holding, so a Space tap cannot
        # turn into Cmd+Space.
        Quartz.CGEventSetFlags(event, 0)
        self._post(event)
