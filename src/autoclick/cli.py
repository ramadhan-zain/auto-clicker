"""Command line entry point.

python -m autoclick                  open the window
python -m autoclick run --help       run the engine from the terminal
"""

import argparse
import sys
import time

from autoclick import macos
from autoclick.actions import DEFAULT_HOLD_MS, Click, KeyTap
from autoclick.backend.base import MouseButton
from autoclick.backend.quartz import QuartzBackend
from autoclick.engine import Engine, EngineConfig, Snapshot

_PRINT_EVERY_S = 1.0


def _parse_args(argv: list[str] | None) -> tuple[argparse.ArgumentParser, argparse.Namespace]:
    parser = argparse.ArgumentParser(
        prog="autoclick", description="Timed mouse clicks and key presses for macOS."
    )
    commands = parser.add_subparsers(dest="command")
    run = commands.add_parser(
        "run", help="send an action on a timer without the window; Ctrl+C stops"
    )
    run.add_argument("--action", choices=("key", "left", "right"), default="key")
    run.add_argument("--key", default="space", help="key to tap when --action is key")
    run.add_argument("--interval-ms", type=int, default=1000)
    run.add_argument("--hold-ms", type=int, default=DEFAULT_HOLD_MS)
    run.add_argument("--minutes", type=float, help="stop by itself after this long")
    run.add_argument("--delay-s", type=float, default=3, help="wait before the first action")
    run.add_argument(
        "--target", default=macos.ROBLOX_BUNDLE_ID, help="bundle id that must be frontmost"
    )
    run.add_argument("--any-app", action="store_true", help="send to whatever app is frontmost")
    run.add_argument("--dry-run", action="store_true", help="build events but do not post them")
    return parser, parser.parse_args(argv)


def _status(snapshot: Snapshot) -> str:
    text = f"sent {snapshot.sent}, skipped {snapshot.skipped}, missed {snapshot.missed}"
    if snapshot.next_in_s is not None:
        text += f", next in {snapshot.next_in_s:.1f} s"
    return text


def _run(parser: argparse.ArgumentParser, args: argparse.Namespace) -> None:
    try:
        if args.action == "key":
            action = KeyTap(args.key, args.hold_ms)
        else:
            action = Click(MouseButton(args.action), hold_ms=args.hold_ms)
        config = EngineConfig(
            actions=(action,),
            interval_ms=args.interval_ms,
            target_bundle_id=None if args.any_app else args.target,
            auto_stop_after_s=None if args.minutes is None else args.minutes * 60,
            start_delay_ms=round(args.delay_s * 1000),
        )
    except ValueError as exc:
        parser.error(str(exc))

    if args.dry_run:
        print("DRY RUN: events are built but not posted.")
        engine = Engine(QuartzBackend(post=lambda event: None), frontmost=macos.frontmost_bundle_id)
    elif not macos.accessibility_granted():
        macos.request_accessibility()
        sys.exit(
            "Accessibility permission is missing, so macOS would drop every event.\n"
            "Grant it to the app you launched this from (your terminal) in\n"
            "System Settings > Privacy & Security > Accessibility, then quit and\n"
            "reopen that app and run this again."
        )
    else:
        engine = Engine(
            QuartzBackend(),
            frontmost=macos.frontmost_bundle_id,
            permission_granted=macos.accessibility_granted,
        )

    where = "any app" if config.target_bundle_id is None else config.target_bundle_id
    print(f"{args.action} every {config.interval_ms} ms to {where}. Ctrl+C stops.")
    engine.start(config)
    last_counts = None
    try:
        while engine.running:
            time.sleep(_PRINT_EVERY_S)
            snapshot = engine.snapshot()
            counts = (snapshot.sent, snapshot.skipped, snapshot.missed)
            if snapshot.running and counts != last_counts:
                last_counts = counts
                print(f"  {_status(snapshot)}", flush=True)
    except KeyboardInterrupt:
        print()
    finally:
        engine.stop()
        engine.join()
    snapshot = engine.snapshot()
    print(f"Stopped ({snapshot.stop_reason.value}): {_status(snapshot)}")
    if snapshot.error:
        sys.exit(snapshot.error)


def main(argv: list[str] | None = None) -> None:
    parser, args = _parse_args(argv)
    if args.command == "run":
        _run(parser, args)
        return
    # Imported here so a terminal run does not load Tk.
    from autoclick.app import run

    run()
