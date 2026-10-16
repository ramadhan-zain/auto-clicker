"""M1 spike: prove that Roblox registers synthetic input.

Throwaway script. The real scheduler is built in M2.

    uv run python scripts/spike_input.py check
    uv run python scripts/spike_input.py basic
    uv run python scripts/spike_input.py timing
    caffeinate -d uv run python scripts/spike_input.py soak

Input is only sent while the target app (Roblox by default) is frontmost.
Press Ctrl+C in the terminal to stop.
"""

import argparse
import statistics
import sys
import time

from autoclick import macos
from autoclick.backend.base import MouseButton
from autoclick.backend.quartz import QuartzBackend
from autoclick.keys import keycode

FOCUS_CHECK_EVERY_S = 0.25


def sleep_until(deadline: float) -> None:
    """Wait for a perf_counter deadline.

    A single time.sleep() overshoots by up to ~20 ms on macOS, so wait in 1 ms
    steps and spin through the last half millisecond.
    """
    while True:
        remaining = deadline - time.perf_counter()
        if remaining <= 0:
            return
        if remaining > 0.003:
            time.sleep(0.001)
        elif remaining > 0.0005:
            time.sleep(0)


def hold(seconds: float) -> None:
    sleep_until(time.perf_counter() + seconds)


def click(backend: QuartzBackend, hold_s: float, nudge: bool) -> None:
    x, y = backend.cursor_position()
    if nudge:
        # Roblox may ignore a click that is not preceded by mouse movement.
        backend.mouse_move((x + 1, y))
        backend.mouse_move((x, y))
    backend.mouse_down(MouseButton.LEFT, (x, y))
    try:
        hold(hold_s)
    finally:
        backend.mouse_up(MouseButton.LEFT, (x, y))


def key_tap(backend: QuartzBackend, code: int, hold_s: float) -> None:
    backend.key_down(code)
    try:
        hold(hold_s)
    finally:
        backend.key_up(code)


class Session:
    def __init__(self, args: argparse.Namespace) -> None:
        self.dry_run: bool = args.dry_run
        self.target: str | None = None if (args.any_app or args.dry_run) else args.target
        self.countdown: int = args.countdown
        self.hold_s: float = args.hold_ms / 1000
        self.nudge: bool = not args.no_nudge
        self.backend = QuartzBackend(post=lambda event: None) if self.dry_run else QuartzBackend()

    def require_permission(self) -> None:
        if self.dry_run:
            print("DRY RUN: events are built but not posted.")
            return
        if macos.accessibility_granted():
            return
        macos.request_accessibility()
        sys.exit(
            "Accessibility permission is missing, so macOS would drop every event.\n"
            "Grant it to the app you launched this from (your terminal) in\n"
            "System Settings > Privacy & Security > Accessibility, then quit and\n"
            "reopen that app and run this again."
        )

    def target_is_front(self) -> bool:
        return self.target is None or macos.frontmost_bundle_id() == self.target

    def wait_for_target(self) -> None:
        """Count down so the user can switch to the target app, then verify it."""
        what = self.target or "the window you want to test"
        for remaining in range(self.countdown, 0, -1):
            print(f"  switch to {what} ... {remaining}", flush=True)
            time.sleep(1)
        if not self.target_is_front():
            sys.exit(
                f"Frontmost app is {macos.frontmost_bundle_id()}, not {self.target}. Nothing sent."
            )


def cmd_check(session: Session, args: argparse.Namespace) -> None:
    granted = macos.accessibility_granted()
    x, y = session.backend.cursor_position()
    print(f"Accessibility granted : {granted}")
    print(f"Frontmost app         : {macos.frontmost_bundle_id()}")
    print(f"Target app            : {args.target}")
    print(f"Cursor position       : {x:.0f}, {y:.0f}")
    if not granted:
        print("\nNo input can be sent until Accessibility is granted to your terminal app.")


def cmd_basic(session: Session, args: argparse.Namespace) -> None:
    session.require_permission()
    session.wait_for_target()
    print("left click at cursor")
    click(session.backend, session.hold_s, session.nudge)
    time.sleep(1)
    print(f"{args.key} tap")
    key_tap(session.backend, keycode(args.key), session.hold_s)
    print("Done. Did the click register and the key act in game?")


def run_timing_set(session: Session, interval_s: float, count: int) -> dict:
    hold_s = min(session.hold_s, interval_s / 2)
    check_every = max(1, round(FOCUS_CHECK_EVERY_S / interval_s))
    stamps: list[float] = []
    start = time.perf_counter()
    for i in range(count):
        if i % check_every == 0 and not session.target_is_front():
            print("  target lost focus, set aborted")
            break
        sleep_until(start + i * interval_s)
        stamps.append(time.perf_counter())
        click(session.backend, hold_s, session.nudge)
    gaps_ms = [(b - a) * 1000 for a, b in zip(stamps, stamps[1:], strict=False)]
    return {
        "interval_ms": interval_s * 1000,
        "hold_ms": hold_s * 1000,
        "sent": len(stamps),
        "mean_ms": statistics.fmean(gaps_ms) if gaps_ms else 0.0,
        "p95_ms": statistics.quantiles(gaps_ms, n=20)[-1] if len(gaps_ms) >= 20 else 0.0,
        "max_ms": max(gaps_ms, default=0.0),
    }


def cmd_timing(session: Session, args: argparse.Namespace) -> None:
    session.require_permission()
    intervals_ms = [float(value) for value in args.intervals.split(",")]
    print(
        f"{len(intervals_ms)} sets of {args.count} clicks. Put the cursor on something that\n"
        "counts clicks in game and note the counter before and after each set."
    )
    results = []
    for interval_ms in intervals_ms:
        print(f"\nSet: {args.count} clicks every {interval_ms:g} ms")
        session.wait_for_target()
        results.append(run_timing_set(session, interval_ms / 1000, args.count))
        print(f"  sent {results[-1]['sent']} clicks")
        time.sleep(args.pause)
    print(
        "\n| Requested ms | Hold ms | Sent | Achieved mean ms | p95 ms | Max ms "
        "| Registered in Roblox |"
    )
    print("|---|---|---|---|---|---|---|")
    for r in results:
        print(
            f"| {r['interval_ms']:g} | {r['hold_ms']:g} | {r['sent']} | {r['mean_ms']:.2f} "
            f"| {r['p95_ms']:.2f} | {r['max_ms']:.2f} | ? |"
        )


def cmd_soak(session: Session, args: argparse.Namespace) -> None:
    session.require_permission()
    code = keycode(args.key)
    interval_s = args.interval_s
    print(
        f"{args.key} tap every {interval_s:g} s for {args.minutes:g} min. "
        "Do not touch the keyboard or mouse in the game."
    )
    session.wait_for_target()
    start = time.monotonic()
    end = start + args.minutes * 60
    next_tap = start
    sent = skipped = 0
    while time.monotonic() < end:
        if time.monotonic() >= next_tap:
            elapsed_min = (time.monotonic() - start) / 60
            if session.target_is_front():
                key_tap(session.backend, code, session.hold_s)
                sent += 1
                print(f"  {elapsed_min:5.1f} min  sent {args.key}", flush=True)
            else:
                skipped += 1
                print(f"  {elapsed_min:5.1f} min  skipped, target not frontmost", flush=True)
            next_tap += interval_s
        time.sleep(0.5)
    print(f"Finished: {sent} sent, {skipped} skipped. Still connected in Roblox?")


def parse_args() -> argparse.Namespace:
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument(
        "--target", default=macos.ROBLOX_BUNDLE_ID, help="bundle id that must be frontmost"
    )
    common.add_argument("--any-app", action="store_true", help="send to whatever app is frontmost")
    common.add_argument("--dry-run", action="store_true", help="build events but do not post them")
    common.add_argument(
        "--countdown", type=int, default=5, help="seconds to switch to the target app"
    )
    common.add_argument("--hold-ms", type=float, default=80, help="time between down and up")
    common.add_argument(
        "--no-nudge", action="store_true", help="do not move the mouse before a click"
    )

    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    commands = parser.add_subparsers(dest="command", required=True)

    commands.add_parser(
        "check", parents=[common], help="show permission and focus state"
    ).set_defaults(run=cmd_check)

    basic = commands.add_parser("basic", parents=[common], help="one click, then one key tap")
    basic.add_argument("--key", default="space")
    basic.set_defaults(run=cmd_basic)

    timing = commands.add_parser(
        "timing", parents=[common], help="click bursts at several intervals"
    )
    timing.add_argument("--intervals", default="100,50,20,10", help="comma-separated milliseconds")
    timing.add_argument("--count", type=int, default=200)
    timing.add_argument("--pause", type=float, default=3, help="seconds to rest after each set")
    timing.set_defaults(run=cmd_timing)

    soak = commands.add_parser("soak", parents=[common], help="long anti-AFK run")
    soak.add_argument("--key", default="space")
    soak.add_argument("--minutes", type=float, default=25)
    soak.add_argument("--interval-s", type=float, default=300)
    soak.set_defaults(run=cmd_soak)

    return parser.parse_args()


def main() -> None:
    args = parse_args()
    session = Session(args)
    try:
        args.run(session, args)
    except KeyboardInterrupt:
        print("\nStopped.")


if __name__ == "__main__":
    main()
