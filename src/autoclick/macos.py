import os
import subprocess
from typing import NamedTuple

import objc
import Quartz
from AppKit import NSApplicationActivationPolicyRegular, NSRunningApplication
from ApplicationServices import (
    AXIsProcessTrusted,
    AXIsProcessTrustedWithOptions,
    kAXTrustedCheckOptionPrompt,
)

ROBLOX_BUNDLE_ID = "com.roblox.RobloxPlayer"
ROBLOX_NAME = "Roblox"


class RunningApp(NamedTuple):
    name: str
    bundle_id: str


_ACCESSIBILITY_SETTINGS_URL = (
    "x-apple.systempreferences:com.apple.preference.security?Privacy_Accessibility"
)
_INPUT_MONITORING_SETTINGS_URL = (
    "x-apple.systempreferences:com.apple.preference.security?Privacy_ListenEvent"
)


def accessibility_granted() -> bool:
    """True when this process may post input events.

    In development the permission belongs to the app that launched Python
    (the terminal), not to the script.
    """
    return bool(AXIsProcessTrusted())


def request_accessibility() -> bool:
    """Show the system prompt that offers to open the Accessibility settings."""
    return bool(AXIsProcessTrustedWithOptions({kAXTrustedCheckOptionPrompt: True}))


def open_accessibility_settings() -> None:
    subprocess.run(["open", _ACCESSIBILITY_SETTINGS_URL], check=False)


def input_monitoring_granted() -> bool:
    """True when this process may listen for key presses in other apps.

    macOS only applies a new grant after the app is quit and reopened.
    """
    return bool(Quartz.CGPreflightListenEventAccess())


def request_input_monitoring() -> bool:
    """Show the system prompt and add this app to the Input Monitoring list."""
    return bool(Quartz.CGRequestListenEventAccess())


def open_input_monitoring_settings() -> None:
    subprocess.run(["open", _INPUT_MONITORING_SETTINGS_URL], check=False)


def frontmost_bundle_id() -> str | None:
    """Bundle id of the app that owns the frontmost normal window.

    Asks the window server on every call. `NSWorkspace.frontmostApplication`
    is not used because it only updates while the main run loop is running,
    which is not the case on a worker thread or in a plain script.
    """
    # Worker threads have no autorelease pool of their own, so without this
    # every call would leak until the thread ends.
    with objc.autorelease_pool():
        windows = Quartz.CGWindowListCopyWindowInfo(
            Quartz.kCGWindowListOptionOnScreenOnly | Quartz.kCGWindowListExcludeDesktopElements,
            Quartz.kCGNullWindowID,
        )
        for window in windows or ():
            if window.get(Quartz.kCGWindowLayer) != 0:
                continue
            app = NSRunningApplication.runningApplicationWithProcessIdentifier_(
                window[Quartz.kCGWindowOwnerPID]
            )
            if app is not None and app.bundleIdentifier():
                return str(app.bundleIdentifier())
        return None


def windowed_apps() -> list[RunningApp]:
    """Apps that have a normal window open, sorted by name.

    Covers windows in other Spaces, in full screen and minimised, so a game
    can be picked before switching to it. This process is left out. Window
    titles are not read: that would need the Screen Recording permission.
    """
    own_pid = os.getpid()
    with objc.autorelease_pool():
        windows = Quartz.CGWindowListCopyWindowInfo(
            Quartz.kCGWindowListOptionAll | Quartz.kCGWindowListExcludeDesktopElements,
            Quartz.kCGNullWindowID,
        )
        seen = {own_pid}
        names: dict[str, str] = {}
        for window in windows or ():
            pid = window[Quartz.kCGWindowOwnerPID]
            if window.get(Quartz.kCGWindowLayer) != 0 or pid in seen:
                continue
            seen.add(pid)
            app = NSRunningApplication.runningApplicationWithProcessIdentifier_(pid)
            # Regular apps are the ones in the Dock; the rest are helpers and agents.
            if (
                app is None
                or not app.bundleIdentifier()
                or app.activationPolicy() != NSApplicationActivationPolicyRegular
            ):
                continue
            bundle_id = str(app.bundleIdentifier())
            # Some names carry invisible marks (WhatsApp starts with U+200E).
            name = "".join(ch for ch in str(app.localizedName() or "") if ch.isprintable())
            names[bundle_id] = name.strip() or bundle_id
        return sorted(
            (RunningApp(name, bundle_id) for bundle_id, name in names.items()),
            key=lambda app: app.name.lower(),
        )
