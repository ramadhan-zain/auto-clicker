import pytest
import Quartz

from autoclick.backend.base import MouseButton
from autoclick.backend.quartz import QuartzBackend


@pytest.fixture
def posted():
    return []


@pytest.fixture
def backend(posted):
    return QuartzBackend(post=posted.append)


def event_type(event) -> int:
    return Quartz.CGEventGetType(event)


def location(event) -> tuple[float, float]:
    point = Quartz.CGEventGetLocation(event)
    return (point.x, point.y)


def test_left_click_posts_down_then_up_at_position(backend, posted):
    backend.mouse_down(MouseButton.LEFT, (120, 340))
    backend.mouse_up(MouseButton.LEFT, (120, 340))

    assert [event_type(e) for e in posted] == [
        Quartz.kCGEventLeftMouseDown,
        Quartz.kCGEventLeftMouseUp,
    ]
    assert [location(e) for e in posted] == [(120, 340), (120, 340)]


def test_right_click_uses_right_button_events(backend, posted):
    backend.mouse_down(MouseButton.RIGHT, (10, 20))
    backend.mouse_up(MouseButton.RIGHT, (10, 20))

    assert [event_type(e) for e in posted] == [
        Quartz.kCGEventRightMouseDown,
        Quartz.kCGEventRightMouseUp,
    ]
    button = Quartz.CGEventGetIntegerValueField(posted[0], Quartz.kCGMouseEventButtonNumber)
    assert button == Quartz.kCGMouseButtonRight


def test_click_events_carry_single_click_state(backend, posted):
    backend.mouse_down(MouseButton.LEFT, (1, 1))

    state = Quartz.CGEventGetIntegerValueField(posted[0], Quartz.kCGMouseEventClickState)
    assert state == 1


def test_mouse_move_posts_moved_event(backend, posted):
    backend.mouse_move((55, 66))

    assert event_type(posted[0]) == Quartz.kCGEventMouseMoved
    assert location(posted[0]) == (55, 66)


def test_key_tap_posts_key_down_then_up_with_keycode(backend, posted):
    backend.key_down(49)
    backend.key_up(49)

    assert [event_type(e) for e in posted] == [Quartz.kCGEventKeyDown, Quartz.kCGEventKeyUp]
    codes = [Quartz.CGEventGetIntegerValueField(e, Quartz.kCGKeyboardEventKeycode) for e in posted]
    assert codes == [49, 49]


def test_key_events_carry_no_modifiers(backend, posted):
    backend.key_down(49)

    modifiers = (
        Quartz.kCGEventFlagMaskCommand
        | Quartz.kCGEventFlagMaskShift
        | Quartz.kCGEventFlagMaskControl
        | Quartz.kCGEventFlagMaskAlternate
    )
    assert Quartz.CGEventGetFlags(posted[0]) & modifiers == 0


def test_cursor_position_returns_two_numbers(backend):
    x, y = backend.cursor_position()

    assert isinstance(x, float)
    assert isinstance(y, float)
