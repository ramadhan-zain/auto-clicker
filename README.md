# Auto Click

macOS auto clicker and key presser (Tkinter), mainly to avoid the Roblox idle kick.
See [DEVELOPMENT_PLAN.md](DEVELOPMENT_PLAN.md) for scope, design and progress.

## Development

Requires [uv](https://docs.astral.sh/uv/). Python 3.12 and dependencies are installed on first run.

```sh
make            # list all commands
make run        # open the app window
make check      # lint and tests (no real input is sent)
make format     # fix lint issues and reformat
```

## Usage

`make run` opens the window: choose a key press or a click, set the interval, press Start,
then switch to the game. The first action comes 3 seconds after Start, and by default input is
only sent while the chosen app is the front window. That app is Roblox unless you pick another
one from the list, which shows every app that has a window open.

F6 starts and stops from any app (fn+F6 on a laptop keyboard); the key can be changed in the
window. The hotkey needs the Input Monitoring permission, and intervals under 500 ms are only
offered while it works. If a permission is missing, the window shows which one and opens the
right System Settings pane.

The same engine runs from the terminal, without the window:

```sh
uv run python -m autoclick run --key space --interval-ms 1000 --minutes 5
uv run python -m autoclick run --help    # --action left, --any-app, --dry-run, ...
```

Ctrl+C stops it.

Both permissions belong to the app that launches Python (your terminal): System Settings →
Privacy & Security → Accessibility, and → Input Monitoring. Quit and reopen the terminal
after granting them.

## Building and releasing

`make build` writes `dist/AutoClick.app` (ad-hoc signed, Apple Silicon) and
`dist/AutoClick-macos-arm64.zip`.

To publish a release, bump `version` in `pyproject.toml` and `src/autoclick/__init__.py`,
commit, then push a matching tag:

```sh
git tag v0.1.0
git push origin v0.1.0
```

The Release workflow checks the tag matches the version, runs `make check`, builds the app
and attaches the zip to a GitHub release. Running the workflow by hand from the Actions tab
builds the zip as a workflow artifact without releasing.

The app is not notarized, so macOS blocks it after download. Clear the quarantine flag once:

```sh
xattr -dr com.apple.quarantine /Applications/AutoClick.app
```

Each build has a new ad-hoc signature, so after updating, remove AutoClick from
Accessibility and Input Monitoring in System Settings and add it again.

## Input spike (M1)

```sh
make spike-check    # permission and focus state
make spike-basic    # one click and one Space tap
make spike-timing   # click bursts at 100/50/20/10 ms
make spike-soak     # 25 minute anti-AFK run
```

Input is only sent while Roblox is frontmost. Ctrl+C stops. For options such as
`--dry-run` or `--any-app`, run `uv run python scripts/spike_input.py <command> --help`.
# auto-clicker
