# Auto Click — Development Plan

A small macOS desktop app (Tkinter) that sends mouse clicks and key presses on a timer, mainly to keep a Roblox session from being kicked for inactivity.

## 1. Goal and scope

Roblox disconnects a player after 20 minutes without input. The app sends a harmless input (a click or a key tap) at a chosen interval, well under that limit, while Roblox is the active window.

**In scope for v1**

- Start/stop a repeating sequence of actions: left/right click, key tap (e.g. Space, W/A/S/D).
- Configurable repeat interval with millisecond precision, from 10 ms (fast clicking) up to minutes (anti-AFK), and hold duration per action.
- Click at the current cursor position or at a saved screen position.
- Only send input while the target app is frontmost (on by default). The target is Roblox unless another app is picked from the list of apps with a window open.
- Global hotkey to start/stop, plus an optional auto-stop after N minutes.
- Settings saved between launches.
- Clear guidance when macOS permissions are missing.

**Out of scope for v1**

- Recording and replaying macros.
- Sending input to Roblox while it is in the background.
- Image/pixel detection, multiple profiles, Windows/Linux support.

**Note on game rules:** some Roblox experiences forbid AFK farming and may kick or ban for it. The app is for personal use; check the rules of the experience you use it in.

## Status (2026-10-11)

| Milestone | State |
|---|---|
| M0 Project setup | Done |
| M1 Input backend spike | Code written and unit tested. The three Roblox tests below still have to be run by hand; no real input has been sent yet. |
| M2 Engine | Code written and unit tested. Command-line run checked with `--dry-run` only (events built, not posted); a run that posts real input is still to do. |
| M3 User interface | Code written and unit tested. Start/stop flow checked in the real window with a fake backend. Not yet looked at on screen, and not yet tried against Roblox. |
| M4 Safety and permissions | Code written and unit tested. The hotkey listener starts, runs next to Tk and stops cleanly, but no real key press has reached it yet: pressing F6, with Roblox in full screen, is still to do. |
| M5 to M6 | Not started |

**To finish M1**

1. Grant Accessibility to the terminal app (System Settings → Privacy & Security → Accessibility), then quit and reopen the terminal. It is currently not granted, so nothing can be sent.
2. `uv run python scripts/spike_input.py check` should print `Accessibility granted : True`.
3. Open Roblox, join an experience, then run `uv run python scripts/spike_input.py basic`. Expect one click and one jump.
4. `uv run python scripts/spike_input.py timing` with the cursor on something that counts clicks. Fill the last column of the printed table.
5. `caffeinate -d uv run python scripts/spike_input.py soak` and leave Roblox alone for 25 minutes. Expect no idle kick.

**To finish M2 and M3** (after the M1 steps above)

1. `uv run python -m autoclick run --interval-ms 1000 --minutes 1` with Roblox frontmost. Expect a jump every second and `sent` counting up.
2. `make run`, press Start, switch to Roblox within 3 seconds. Expect a jump every 5 minutes (or pick the 1 s preset to see it sooner), and `skipped` counting up while another app is in front.
3. Check the window layout by eye, and try a left click with a picked position.

**To finish M4**

1. `make run`. If a "Permissions needed" box shows, follow it (the terminal app needs Input Monitoring as well as Accessibility), then quit and reopen.
2. The button should read `Start (F6)`. Press F6 (fn+F6 on a laptop keyboard) while another app is in front: the window should switch to Running, and F6 again should stop it.
3. Pick the 50 ms preset with Left click, start with F6 over Roblox in full screen, stop with F6.
4. Revoke both permissions in System Settings, reopen the app and check that the box leads back to a working setup.

### M4 findings

- **Hotkey: Quartz listen-only event tap on its own thread; `pynput` not needed.** The tap thread ran next to the Tk main loop, stopped and restarted without a crash. The listener only reads the key code, the auto-repeat flag and the sender's process id, and never calls the keyboard-layout functions that crash `pynput` off the main thread.
- **What the spike could not show:** a real key press arriving at the tap. Events posted to this process only (`CGEventPostToPid`) do not pass a session tap, and posting to the session would have typed into whatever app was in front. The handler is covered by unit tests with constructed events instead.
- **`CGEventTapCreateForPid` is unusable from pyobjc**: it does not keep the callback alive, and the first event crashes the process. `CGEventTapCreate` does not have this problem.
- **The engine's own key taps pass through the tap too**, so events whose sender is this process are ignored. Hotkey choices are F1 to F12 and are kept out of the list of keys that can be sent.
- **Stop from the hotkey happens on the tap thread** (`engine.stop()` only sets a flag); the engine was stopped within 10 ms in the window test. Start from the hotkey is handed to the main thread, because it reads the form.
- **Trying to create the tap without Input Monitoring makes macOS show its prompt.** At launch the app therefore only tries when macOS already reports the permission; the Check again button always tries.
- **Not done:** the measured click rate in the status line (Risks table). No milestone lists it.

### M2 findings

- **Engine timing with the real clock and a fake backend** (200 clicks per set, hold is half the interval):

  | Requested ms | Achieved mean ms | p95 ms | Max ms | Missed ticks |
  |---|---|---|---|---|
  | 100 | 100.00 | 100.75 | 104.78 | 0 |
  | 50 | 50.00 | 54.69 | 64.65 | 0 |
  | 20 | 20.00 | 26.07 | 29.27 | 0 |
  | 10 | 10.10 | 17.79 | 29.79 | 2 |

  Stop took under 3 ms in every set.
- **A tick that is late by less than one interval fires at once**; only a tick more than one interval late is dropped. Dropping every late tick lost 16 of 200 clicks at 10 ms, because a 5 ms hold that starts a few milliseconds late already runs past the next tick.
- **The UI polls an engine snapshot** every 100 ms instead of draining a queue of tick events. A queue grows without limit at 100 ticks per second when nothing drains it (the command-line run), and the UI only needs the latest counts.
- **The first action comes 3 seconds after Start** (`start_delay_ms`). Without the delay the first tick fires while the Auto Click window is still in front: with the guard on it is counted as skipped, and with the guard off a click at the cursor lands on the Stop button.

### M1 findings so far

- **`NSWorkspace.frontmostApplication()` goes stale** when the main run loop is not running. In a test that switched to Finder and back it kept reporting the terminal, while the window-server query reported Finder correctly. `macos.frontmost_bundle_id()` therefore uses `CGWindowListCopyWindowInfo`. It costs about 1.4 ms per call, so the engine checks focus at most every 250 ms in fast mode, not on every click. Known gap: an app that is frontmost but has no window on screen is not detected.
- **A single `time.sleep()` is too coarse for fast mode.** Measured overshoot was up to 14 ms on a 10 ms sleep and 19 ms on a 50 ms sleep. Waiting in 1 ms steps against a monotonic deadline fixes the average. Raising thread priority made no useful difference.
- **Scheduler accuracy without posting events** (200 clicks per set, other apps running):

  | Requested ms | Hold ms | Achieved mean ms | p95 ms | Max ms |
  |---|---|---|---|---|
  | 100 | 50 | 100.01 | 108.00 | 152.81 |
  | 50 | 25 | 50.00 | 57.87 | 68.92 |
  | 20 | 10 | 20.06 | 25.77 | 34.75 |
  | 10 | 5 | 10.01 | 17.15 | 27.64 |

  The average rate is exact down to 10 ms. Individual clicks can be late by several milliseconds, with rare spikes of 20 ms or more. Whether Roblox registers clicks at these rates is still unmeasured.
- Building the events for one click takes about 0.01 ms, so event construction is not a limit.

## 2. Current environment (checked 2026-10-11)

| Item | Found | Consequence |
|---|---|---|
| macOS | 15.7.9, Apple Silicon (arm64) | Target platform; no Intel build needed |
| Python | Only `/usr/bin/python3` 3.9.6 | Too old; do not use |
| Tk | 8.5 (Apple's deprecated build) | Rendering and dark-mode bugs; do not use |
| `uv` | Installed at `/opt/homebrew/bin/uv` | Use it to manage Python and dependencies |
| pyobjc / pynput | Not installed | Added as project dependencies |
| Project folder | Empty, not a git repo | Start from scratch, `git init` in M0 |

## 3. Technical decisions

| Area | Choice | Why |
|---|---|---|
| Python | 3.12 managed by `uv` | Ships with a current Tk (9.0.4 on this machine); isolated from system Python |
| UI | Tkinter + `ttk` | Requested; no extra dependency |
| Input sending | Quartz `CGEvent` via `pyobjc-framework-Quartz` | Lowest-level reliable path on macOS; games often ignore higher-level synthetic input |
| Permission and frontmost-app checks | `pyobjc-framework-ApplicationServices`, `pyobjc-framework-Cocoa` | `AXIsProcessTrusted()`; frontmost app read from the window server with `CGWindowListCopyWindowInfo` (see M1 findings) |
| Global hotkey | Quartz event tap, `hotkey.py` | Decided: Quartz listen-only event tap on its own thread (see M4 findings). `pynput` listeners are known to crash alongside Tk on recent macOS |
| Settings | JSON in `~/Library/Application Support/AutoClick/config.json` | Standard location, human-readable |
| Packaging | PyInstaller `--windowed`, ad-hoc code signed | Gives a `.app` that can hold its own Accessibility permission |
| Tests | `pytest` with a fake input backend and fake clock | Engine logic is testable without touching the real mouse |

### macOS behaviour that shapes the design

- **Accessibility permission is mandatory.** Without it, `CGEventPost` fails silently: no error, no input. The app must check `AXIsProcessTrusted()` at startup and before starting, and show how to grant it (System Settings → Privacy & Security → Accessibility).
- **In development the permission belongs to the launcher** (Terminal, iTerm, VS Code), not to the script. In the packaged app it belongs to the `.app`.
- **Unsigned rebuilds lose the permission.** Each new build looks like a new app to macOS, so a stable ad-hoc signature and bundle id are needed.
- **A global hotkey listener needs Input Monitoring** permission as well.
- **Tk must own the main thread.** All input sending and timing runs on a worker thread; UI updates go back through `root.after()`.

### Roblox behaviour to verify early

- Zero-length clicks and key taps are often ignored. Send down, wait 50–150 ms, then up.
- Roblox reads input once per frame (about 16.7 ms at 60 fps). Clicks sent faster than that, or held for less than a frame, may be dropped by the game even though macOS delivered them. M1 measures the fastest interval Roblox actually registers.
- A click may only register after a mouse-move event, so post a small move to the same point before the click.
- Key codes are physical key positions (Space = 49, W = 13, A = 0, S = 1, D = 2), not characters.
- Roblox bundle id is `com.roblox.RobloxPlayer` (confirmed from `/Applications/Roblox.app`, version 0.742).

## 4. Architecture

```
auto-click/
├── pyproject.toml
├── DEVELOPMENT_PLAN.md
├── src/autoclick/
│   ├── __main__.py        # entry point
│   ├── cli.py             # argument parsing: window by default, `run` for the terminal
│   ├── app.py             # Tk window, widgets, status display
│   ├── engine.py          # worker thread: schedule, run actions, stop conditions
│   ├── actions.py         # Action dataclasses (Click, KeyTap) and validation
│   ├── units.py           # interval and hold text parsing, rate and countdown text
│   ├── config.py          # load/save settings, defaults
│   ├── keys.py            # key name to macOS virtual key code
│   ├── macos.py           # permission checks, frontmost app, open System Settings
│   ├── hotkey.py          # global start/stop hotkey
│   └── backend/
│       ├── base.py        # InputBackend protocol
│       ├── quartz.py      # real CGEvent implementation
│       └── fake.py        # records calls, used by tests
└── tests/
    ├── conftest.py        # fake clock
    ├── test_engine.py
    ├── test_actions.py
    ├── test_units.py
    ├── test_app.py        # window logic with a stub engine
    ├── test_hotkey.py
    └── test_config.py
scripts/
└── spike_input.py         # M1 throwaway: check / basic / timing / soak
```

**Flow:** the UI builds a list of actions and an interval and hands them to the engine. The engine thread waits on a `threading.Event` (so Stop is immediate), checks the guards (permission, frontmost app, auto-stop time), then calls the backend. It publishes its state (running, counts, time to the next tick) as a snapshot under a lock, which the UI reads every 100 ms with `root.after()`.

**Engine rules**

- Stop is always honoured within 100 ms, including in the middle of a key hold; any key or button that is down is released on stop.
- If Roblox is not frontmost, the tick is skipped and counted, not queued.
- The interval is stored as whole milliseconds (`interval_ms`). Allowed range is 10 ms to 3,600,000 ms (1 hour); values outside it are rejected, not clamped silently.
- Ticks are scheduled against a monotonic clock as `next = previous + interval`, not `sleep(interval)`, so the time spent sending an action does not accumulate as drift. If the engine falls behind by more than one interval, it skips the missed ticks instead of firing a burst; a tick that is late by less fires at once. Waits are done in steps of 1 ms or less (checking the stop flag each step), because one long sleep overshoots by up to 20 ms on macOS.
- The first tick comes after a start delay (3 s in the UI), so the user can switch to the game.
- The hold duration must fit inside the interval. When the configured hold is longer than half the interval, the engine uses half the interval and the UI shows the effective value.
- Intervals under 500 ms count as fast mode and need a working global hotkey before Start is allowed (see M4), because the Stop button cannot be relied on while the mouse is clicking many times per second.

## 5. Milestones

Each milestone ends with something that can be run and checked.

### M0 — Project setup (done 2026-10-11)
- `git init`, `uv init`, Python 3.12, dependencies, `.gitignore`, `ruff` and `pytest` configured.
- **Done when:** `uv run python -m autoclick` opens an empty Tk window on the uv-managed Python. Verified: window opens and closes cleanly on Tk 9.0.4.

### M1 — Input backend spike (highest risk, do first) (code done, Roblox tests pending)
- Implement `backend/quartz.py`: click at point, key tap with hold duration.
- Implement the Accessibility permission check.
- Throwaway script: wait 5 s, then send a click and a Space tap.
- Timing test: send 200 clicks at 100, 50, 20 and 10 ms intervals; record the achieved interval and how many clicks Roblox registers.
- **Done when:** with Roblox frontmost, the character jumps on Space and a click registers in game, and a 25-minute run does not get kicked. If Roblox ignores the input, resolve it here before building anything else. The timing test results are written into this plan and set the final minimum interval.

### M2 — Engine (code done, real-input run pending)
- `actions.py`, `engine.py`, fake backend, fake clock.
- Unit tests: interval timing, immediate stop, release-on-stop, frontmost guard skips, auto-stop, interval range validation, no drift over 1,000 ticks, missed ticks skipped not burst, hold shortened to fit a short interval.
- **Done when:** tests pass and a command-line run drives the real backend on a timer.

### M3 — User interface (code done, Roblox run pending)
- Action picker (left click / right click / key), key selector, hold field with validation.
- Interval input: a number field plus a unit selector (ms / s / min), converted to whole milliseconds. Shows the resulting rate next to it (e.g. "50 ms = 20 clicks per second") and an inline error for values outside 10 ms to 1 hour.
- Presets for common values: 50 ms, 100 ms, 1 s, 5 min.
- Click position: current cursor, or "pick position" with a 3-second countdown capture.
- Start/Stop button, status line (running, next action in N s, actions sent, ticks skipped).
- **Done when:** the whole anti-AFK flow works from the window with no terminal.

### M4 — Safety and permissions (code done, real hotkey press pending)
- Hotkey spike: try a Quartz listen-only event tap on its own thread; fall back to `pynput` if stable; choose one.
- Global start/stop hotkey (default F6), configurable.
- Fast mode gate: Start is blocked for intervals under 500 ms until the hotkey is registered and Input Monitoring is granted. Until M4 lands, the UI limits the interval to 500 ms or more.
- "Only while the target app is in front" toggle with a list of open apps to pick the target from (Roblox by default), auto-stop timer.
- Missing-permission screen with a button that opens the right System Settings pane, and a re-check button.
- **Done when:** the hotkey stops the app while Roblox is fullscreen, and a fresh machine state (permissions revoked) leads the user to a working setup without reading docs.

### M5 — Persistence and polish
- Save and restore all settings and window position.
- Always-on-top toggle, sensible defaults (Space tap every 5 minutes), log of the last few actions.
- **Done when:** quitting and relaunching restores the previous setup, and a corrupt config file falls back to defaults instead of crashing.

### M6 — Packaging
- PyInstaller build script, app icon, fixed bundle id, ad-hoc signing.
- README: install, grant permissions, usage, troubleshooting.
- **Done when:** `AutoClick.app` launched from Finder passes the M1 25-minute test, and a rebuild keeps its Accessibility permission.

## 6. Risks

| Risk | Impact | Mitigation |
|---|---|---|
| Roblox ignores synthetic input | App is useless | M1 proves it before any UI work; try move-before-click, longer holds, `kCGHIDEventTap` vs session tap |
| Global hotkey library crashes with Tk | No way to stop during fast clicking | Spike in M4; fast mode (under 500 ms) stays disabled until a hotkey works; frontmost guard stops clicks as soon as another app is activated |
| Fast clicking with the frontmost guard turned off | Clicks land on whatever is under the cursor, including other apps | Guard is on by default; turning it off in fast mode shows a warning; hotkey and auto-stop still apply |
| Short intervals are not met exactly | Achieved rate is lower than the number shown | Monotonic scheduling; status line shows the measured rate; M1 timing test sets a realistic minimum |
| Roblox drops clicks faster than its frame rate | User sets 10 ms but sees about 60 clicks per second or fewer | Documented in the UI hint and README; not something the app can fix |
| Permission silently missing | User thinks app is broken | Check before every start, block Start with an explanation |
| Permission reset on rebuild | Annoying during development and after updates | Stable bundle id and signature; document `tccutil reset Accessibility <bundle id>` |
| Keys left held down after a crash | Stuck input in game | Release all in a `finally` block and on app exit |
| Roblox changes its idle rule or bundle id | Kicks resume or guard never matches | Interval and target bundle id are configurable |

## 7. Testing

- **Automated:** engine, actions and config with the fake backend; no real input is sent in the test suite.
- **Manual checklist per release:** permission missing → guided fix; start/stop by button and hotkey; frontmost guard skips when another app is active; 25-minute Roblox soak test; quit while running leaves no key held.

## 8. Decisions taken by default

Change any of these before M3 if they are wrong:

1. Default action is a Space tap every 5 minutes (300,000 ms; a visible jump, safely under the 20-minute limit).
2. Interval is settable in milliseconds, minimum 10 ms (100 per second), subject to the M1 timing test. Intervals under 500 ms require the global hotkey.
3. Input is only sent while Roblox is frontmost; background sending is left for a later version.
4. Default hotkey is F6.
5. Distribution is a local unsigned-by-Apple `.app` for personal use; no notarization.
