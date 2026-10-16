import tkinter as tk
from tkinter import ttk
from typing import Protocol

from autoclick import macos, units
from autoclick.actions import (
    DEFAULT_HOLD_MS,
    FAST_MODE_BELOW_MS,
    MIN_INTERVAL_MS,
    Action,
    Click,
    KeyTap,
    effective_hold_ms,
)
from autoclick.backend.base import InputBackend, MouseButton, Point
from autoclick.backend.quartz import QuartzBackend
from autoclick.engine import Engine, EngineConfig, Snapshot, StopReason
from autoclick.hotkey import HotkeyListener
from autoclick.keys import FUNCTION_KEYCODES, KEYCODES

WINDOW_TITLE = "Auto Click"

DEFAULT_KEY = "space"
DEFAULT_INTERVAL_MS = 300_000
DEFAULT_HOTKEY = "F6"
DEFAULT_AUTO_STOP_MIN = "30"
PRESETS_MS = (50, 100, 1_000, 300_000)
# Time to switch to the game after pressing Start.
START_DELAY_MS = 3_000
PICK_COUNTDOWN_S = 3
POLL_MS = 100

_COMMON_KEYS = ("space", "w", "a", "s", "d")
KEY_CHOICES = _COMMON_KEYS + tuple(sorted(set(KEYCODES) - set(_COMMON_KEYS)))

_ERROR_COLOR = "#d0342c"
_HINT_COLOR = "gray50"
_WRAP = 340

_STOP_TEXT = {
    StopReason.USER: "Stopped.",
    StopReason.AUTO_STOP: "Stopped: auto-stop time reached.",
    StopReason.PERMISSION: "Stopped: the Accessibility permission was removed.",
    StopReason.ERROR: "Stopped after an error",
}
_ACCESSIBILITY_TEXT = (
    "Accessibility: needed to send clicks and key presses. Start is off without it."
)
_INPUT_MONITORING_TEXT = (
    f"Input Monitoring: needed for the start/stop hotkey, and so for intervals under "
    f"{FAST_MODE_BELOW_MS} ms."
)
_GRANT_TEXT = (
    "Switch on Auto Click in the list, or your terminal app if you started it from a terminal. "
    "Then press Check again. If nothing changes, quit and reopen the app."
)


class Hotkey(Protocol):
    """What the window needs from `hotkey.HotkeyListener`."""

    keycode: int
    on_press: object

    @property
    def running(self) -> bool: ...

    def start(self) -> bool: ...

    def stop(self) -> None: ...


def _enable(widget: ttk.Widget, enabled: bool) -> None:
    widget.state(["!disabled"] if enabled else ["disabled"])


class App:
    """The main window.

    Engine state is read by polling `engine.snapshot()`. The one thing that
    arrives from another thread is a hotkey press; see `_on_hotkey`.
    """

    def __init__(
        self,
        root: tk.Tk,
        engine: Engine,
        backend: InputBackend,
        hotkey: Hotkey,
        *,
        system=macos,
        target_bundle_id: str = macos.ROBLOX_BUNDLE_ID,
    ) -> None:
        self.root = root
        self.engine = engine
        self.backend = backend
        self.hotkey = hotkey
        # Permission checks and System Settings links; `macos` outside tests.
        self._system = system
        self._target_bundle_id = target_bundle_id
        # What the target list shows, mapped to bundle ids.
        self._targets: dict[str, str] = {}

        self._fixed_position: Point | None = None
        self._picking = False
        self._running = False
        self._form_ok = False
        self._accessibility_ok = False
        # Set from the hotkey thread, acted on by `_poll`.
        self._start_requested = False
        self._poll_job: str | None = None
        self._pick_job: str | None = None

        interval_text, interval_unit = units.split_interval(DEFAULT_INTERVAL_MS)
        self.action = tk.StringVar(root, "key")
        self.key = tk.StringVar(root, DEFAULT_KEY)
        self.hold = tk.StringVar(root, str(DEFAULT_HOLD_MS))
        self.interval_value = tk.StringVar(root, interval_text)
        self.interval_unit = tk.StringVar(root, interval_unit)
        self.position_mode = tk.StringVar(root, "cursor")
        self.position_text = tk.StringVar(root)
        self.guard_on = tk.BooleanVar(root, True)
        self.target = tk.StringVar(root)
        self.auto_stop_on = tk.BooleanVar(root, False)
        self.auto_stop_minutes = tk.StringVar(root, DEFAULT_AUTO_STOP_MIN)
        self.hotkey_name = tk.StringVar(root, DEFAULT_HOTKEY)
        self.status = tk.StringVar(root)
        self.counts = tk.StringVar(root)

        root.title(WINDOW_TITLE)
        root.resizable(False, False)
        root.protocol("WM_DELETE_WINDOW", self._on_close)
        self._build()
        self.refresh_targets()

        self.hotkey.keycode = FUNCTION_KEYCODES[self.hotkey_name.get()]
        self.hotkey.on_press = self._on_hotkey
        for var in (
            self.action,
            self.key,
            self.hold,
            self.interval_value,
            self.interval_unit,
            self.position_mode,
            self.guard_on,
            self.target,
            self.auto_stop_on,
            self.auto_stop_minutes,
            self.hotkey_name,
        ):
            var.trace_add("write", lambda *_: self._refresh())
        # Coming back from System Settings: pick up a permission granted there.
        self._focus_binding: str | None = root.bind("<FocusIn>", self._on_focus, add="+")
        self.check_permissions()
        self._poll()

    # Layout

    def _build(self) -> None:
        frame = self.frame = ttk.Frame(self.root, padding=16)
        frame.grid(sticky="nsew")
        frame.columnconfigure(1, weight=1)
        rows = iter(range(100))

        def row_label(row: int, text: str) -> None:
            ttk.Label(frame, text=text).grid(row=row, column=0, sticky="w", padx=(0, 12), pady=4)

        def field(text: str) -> ttk.Frame:
            row = next(rows)
            row_label(row, text)
            holder = ttk.Frame(frame)
            holder.grid(row=row, column=1, sticky="w")
            return holder

        def note() -> ttk.Label:
            label = ttk.Label(frame, wraplength=_WRAP, foreground=_HINT_COLOR)
            label.grid(row=next(rows), column=1, sticky="w")
            return label

        self._build_permission_panel(frame, next(rows))

        actions = field("Action")
        self.action_buttons = [
            ttk.Radiobutton(actions, text=text, value=value, variable=self.action)
            for text, value in (
                ("Key press", "key"),
                ("Left click", "left"),
                ("Right click", "right"),
            )
        ]
        for button in self.action_buttons:
            button.pack(side="left", padx=(0, 8))

        self.key_box = ttk.Combobox(
            field("Key"), textvariable=self.key, values=KEY_CHOICES, state="readonly", width=10
        )
        self.key_box.pack(side="left")

        hold = field("Hold")
        self.hold_entry = ttk.Entry(hold, textvariable=self.hold, width=8)
        self.hold_entry.pack(side="left")
        ttk.Label(hold, text="ms").pack(side="left", padx=(6, 0))
        self.hold_note = note()

        interval = field("Interval")
        self.interval_entry = ttk.Entry(interval, textvariable=self.interval_value, width=8)
        self.interval_entry.pack(side="left")
        self.unit_box = ttk.Combobox(
            interval,
            textvariable=self.interval_unit,
            values=tuple(units.UNITS),
            state="readonly",
            width=5,
        )
        self.unit_box.pack(side="left", padx=(6, 0))
        self.interval_note = note()

        presets = field("Presets")
        self.preset_buttons: dict[int, ttk.Button] = {}
        for interval_ms in PRESETS_MS:
            button = ttk.Button(
                presets,
                text=units.format_interval(interval_ms),
                width=6,
                command=lambda ms=interval_ms: self.apply_preset(ms),
            )
            button.pack(side="left", padx=(0, 4))
            self.preset_buttons[interval_ms] = button

        position = field("Click at")
        self.position_buttons = [
            ttk.Radiobutton(position, text=text, value=value, variable=self.position_mode)
            for text, value in (("Current cursor", "cursor"), ("Fixed position", "fixed"))
        ]
        for button in self.position_buttons:
            button.pack(side="left", padx=(0, 8))
        pick = ttk.Frame(frame)
        pick.grid(row=next(rows), column=1, sticky="w", pady=(2, 0))
        self.pick_button = ttk.Button(pick, text="Pick position", command=self.pick_position)
        self.pick_button.pack(side="left")
        self.position_note = ttk.Label(pick, textvariable=self.position_text)
        self.position_note.pack(side="left", padx=(8, 0))

        guard = field("Send")
        self.guard_box = ttk.Checkbutton(guard, text="Only while", variable=self.guard_on)
        self.guard_box.pack(side="left")
        # The list is read again each time it is opened.
        self.target_box = ttk.Combobox(
            guard,
            textvariable=self.target,
            state="readonly",
            width=16,
            postcommand=self.refresh_targets,
        )
        self.target_box.pack(side="left", padx=(4, 6))
        ttk.Label(guard, text="is in front").pack(side="left")
        self.guard_note = note()

        auto_stop = field("Auto-stop")
        self.auto_stop_box = ttk.Checkbutton(
            auto_stop, text="Stop after", variable=self.auto_stop_on
        )
        self.auto_stop_box.pack(side="left")
        self.auto_stop_entry = ttk.Entry(auto_stop, textvariable=self.auto_stop_minutes, width=6)
        self.auto_stop_entry.pack(side="left", padx=(6, 0))
        ttk.Label(auto_stop, text="min").pack(side="left", padx=(6, 0))
        self.auto_stop_note = note()

        self.hotkey_box = ttk.Combobox(
            field("Hotkey"),
            textvariable=self.hotkey_name,
            values=tuple(FUNCTION_KEYCODES),
            state="readonly",
            width=5,
        )
        self.hotkey_box.pack(side="left")
        self.hotkey_note = note()

        ttk.Separator(frame).grid(row=next(rows), column=0, columnspan=2, sticky="ew", pady=12)

        self.start_button = ttk.Button(frame, command=self.toggle, default="active")
        self.start_button.grid(row=next(rows), column=0, columnspan=2, sticky="ew")
        ttk.Label(frame, textvariable=self.status, wraplength=_WRAP + 60).grid(
            row=next(rows), column=0, columnspan=2, sticky="w", pady=(10, 0)
        )
        ttk.Label(frame, textvariable=self.counts).grid(
            row=next(rows), column=0, columnspan=2, sticky="w"
        )
        ttk.Label(
            frame,
            text=f"The first action comes {START_DELAY_MS // 1000} s after Start.",
            foreground=_HINT_COLOR,
        ).grid(row=next(rows), column=0, columnspan=2, sticky="w", pady=(6, 0))

    def _build_permission_panel(self, frame: ttk.Frame, row: int) -> None:
        """Shown only while a permission is missing."""
        panel = self.permission_panel = ttk.LabelFrame(frame, text="Permissions needed", padding=10)
        panel.grid(row=row, column=0, columnspan=2, sticky="ew", pady=(0, 12))

        def permission_row(text: str, button_text: str, command) -> tuple[ttk.Frame, ttk.Button]:
            holder = ttk.Frame(panel)
            ttk.Label(holder, text=text, wraplength=_WRAP + 60).pack(anchor="w")
            button = ttk.Button(holder, text=button_text, command=command)
            button.pack(anchor="w", pady=(4, 8))
            return holder, button

        self.accessibility_row, self.accessibility_button = permission_row(
            _ACCESSIBILITY_TEXT, "Open Accessibility settings", self.open_accessibility
        )
        self.input_monitoring_row, self.input_monitoring_button = permission_row(
            _INPUT_MONITORING_TEXT, "Open Input Monitoring settings", self.open_input_monitoring
        )
        self._permission_footer = ttk.Frame(panel)
        ttk.Label(
            self._permission_footer,
            text=_GRANT_TEXT,
            wraplength=_WRAP + 60,
            foreground=_HINT_COLOR,
        ).pack(anchor="w")
        self.recheck_button = ttk.Button(
            self._permission_footer,
            text="Check again",
            command=lambda: self.check_permissions(retry_hotkey=True),
        )
        self.recheck_button.pack(anchor="w", pady=(4, 0))

    # Permissions

    def check_permissions(self, retry_hotkey: bool = False) -> None:
        """Re-read both permissions and show or hide the panel to match.

        Trying to listen without Input Monitoring makes macOS show its prompt,
        so that is only done when macOS already reports the permission, or
        when the user asks with Check again.
        """
        self._accessibility_ok = bool(self._system.accessibility_granted())
        if not self.hotkey.running and (retry_hotkey or self._system.input_monitoring_granted()):
            self.hotkey.start()

        for holder, missing in (
            (self.accessibility_row, not self._accessibility_ok),
            (self.input_monitoring_row, not self.hotkey.running),
        ):
            holder.pack_forget()
            if missing:
                holder.pack(anchor="w", fill="x")
        self._permission_footer.pack_forget()
        if self._accessibility_ok and self.hotkey.running:
            self.permission_panel.grid_remove()
        else:
            self._permission_footer.pack(anchor="w", fill="x")
            self.permission_panel.grid()
        self._refresh()

    def open_accessibility(self) -> None:
        # The request adds this app to the list, so there is a switch to flip.
        self._system.request_accessibility()
        self._system.open_accessibility_settings()

    def open_input_monitoring(self) -> None:
        self._system.request_input_monitoring()
        self._system.open_input_monitoring_settings()

    def _on_focus(self, event: tk.Event) -> None:
        if event.widget is self.root and not self.permission_ok:
            self.check_permissions()

    @property
    def permission_ok(self) -> bool:
        return self._accessibility_ok and self.hotkey.running

    # Form

    def _min_interval_ms(self) -> int:
        """Fast mode is only offered while the hotkey can stop it."""
        return MIN_INTERVAL_MS if self.hotkey.running else FAST_MODE_BELOW_MS

    def _interval_ms(self) -> int:
        interval_ms = units.parse_interval(self.interval_value.get(), self.interval_unit.get())
        if interval_ms < self._min_interval_ms():
            raise ValueError(
                f"Intervals under {FAST_MODE_BELOW_MS} ms need the stop hotkey, "
                "which needs Input Monitoring."
            )
        return interval_ms

    def _action(self) -> Action:
        hold_ms = units.parse_hold(self.hold.get())
        if self.action.get() == "key":
            return KeyTap(self.key.get(), hold_ms)
        if self.position_mode.get() == "cursor":
            position = None
        elif self._fixed_position is None:
            raise ValueError("Pick a position first.")
        else:
            position = self._fixed_position
        return Click(MouseButton(self.action.get()), position, hold_ms)

    def _auto_stop_s(self) -> float | None:
        if not self.auto_stop_on.get():
            return None
        return units.parse_auto_stop(self.auto_stop_minutes.get())

    def build_config(self) -> EngineConfig:
        """Engine settings for what the form shows, or ValueError."""
        return EngineConfig(
            actions=(self._action(),),
            interval_ms=self._interval_ms(),
            target_bundle_id=self.target_bundle_id if self.guard_on.get() else None,
            auto_stop_after_s=self._auto_stop_s(),
            start_delay_ms=START_DELAY_MS,
        )

    @property
    def target_bundle_id(self) -> str:
        return self._targets.get(self.target.get(), self._target_bundle_id)

    def refresh_targets(self) -> None:
        """Fill the target list with the apps that have a window open."""
        selected = self.target_bundle_id
        names = {app.bundle_id: app.name for app in self._system.windowed_apps()}
        if selected not in names:
            # Not open yet: keep it listed so it can be chosen before the game starts.
            is_roblox = selected == macos.ROBLOX_BUNDLE_ID
            names[selected] = macos.ROBLOX_NAME if is_roblox else selected
        taken = list(names.values())
        self._targets = {
            (name if taken.count(name) == 1 else f"{name} ({bundle_id})"): bundle_id
            for bundle_id, name in names.items()
        }
        self._target_bundle_id = selected
        self.target_box.configure(values=tuple(self._targets))
        self.target.set(next(label for label, value in self._targets.items() if value == selected))

    def apply_preset(self, interval_ms: int) -> None:
        text, unit = units.split_interval(interval_ms)
        self.interval_unit.set(unit)
        self.interval_value.set(text)

    def _refresh(self) -> None:
        """Re-validate the form and update every hint, error and enabled state."""
        is_click = self.action.get() != "key"
        self._form_ok = True
        self.hotkey.keycode = FUNCTION_KEYCODES[self.hotkey_name.get()]

        try:
            interval_ms = self._interval_ms()
            self._show(
                self.interval_note,
                units.describe_rate(interval_ms, "click" if is_click else "key press"),
            )
        except ValueError as exc:
            interval_ms = None
            self._error(self.interval_note, str(exc))

        try:
            hold_ms = units.parse_hold(self.hold.get())
            hint = ""
            if interval_ms is not None:
                effective = effective_hold_ms(hold_ms, interval_ms)
                if effective < hold_ms:
                    hint = f"Shortened to {effective:g} ms to fit the interval."
            self._show(self.hold_note, hint)
        except ValueError as exc:
            self._error(self.hold_note, str(exc))

        if not self._picking:
            if self._fixed_position is not None:
                x, y = self._fixed_position
                self._show(self.position_note, f"x {x:.0f}, y {y:.0f}", var=self.position_text)
            elif is_click and self.position_mode.get() == "fixed":
                self._error(self.position_note, "Pick a position first.", var=self.position_text)
            else:
                self._show(self.position_note, "No position picked", var=self.position_text)

        fast = interval_ms is not None and interval_ms < FAST_MODE_BELOW_MS
        if fast and not self.guard_on.get():
            # A warning, not an error: the hotkey and auto-stop still apply.
            self._show(
                self.guard_note,
                "Fast input will land on whatever is in front, in any app.",
                color=_ERROR_COLOR,
            )
        else:
            self._show(self.guard_note, "")

        try:
            self._auto_stop_s()
            self._show(self.auto_stop_note, "")
        except ValueError as exc:
            self._error(self.auto_stop_note, str(exc))

        if self.hotkey.running:
            self._show(
                self.hotkey_note,
                "Starts and stops from any app. On a laptop keyboard, hold fn as well.",
            )
        else:
            self._show(self.hotkey_note, "Not working: needs Input Monitoring.", color=_ERROR_COLOR)
        self._sync_enabled()

    def _show(
        self,
        label: ttk.Label,
        text: str,
        color: str = _HINT_COLOR,
        var: tk.StringVar | None = None,
    ) -> None:
        label.configure(foreground=color)
        if var is not None:
            var.set(text)
        else:
            label.configure(text=text)

    def _error(self, label: ttk.Label, text: str, var: tk.StringVar | None = None) -> None:
        """Show a message that also blocks Start."""
        self._form_ok = False
        self._show(label, text, _ERROR_COLOR, var)

    def _can_start(self) -> bool:
        return self._form_ok and not self._picking and self._accessibility_ok

    def _sync_enabled(self) -> None:
        editable = not self._running and not self._picking
        is_click = self.action.get() != "key"
        for widget in (
            *self.action_buttons,
            self.hold_entry,
            self.interval_entry,
            self.unit_box,
            self.guard_box,
            self.auto_stop_box,
            self.hotkey_box,
        ):
            _enable(widget, editable)
        _enable(self.key_box, editable and not is_click)
        _enable(self.target_box, editable and self.guard_on.get())
        _enable(self.auto_stop_entry, editable and self.auto_stop_on.get())
        for interval_ms, button in self.preset_buttons.items():
            _enable(button, editable and interval_ms >= self._min_interval_ms())
        for widget in (*self.position_buttons, self.pick_button):
            _enable(widget, editable and is_click)
        _enable(self.start_button, self._running or self._can_start())
        text = "Stop" if self._running else "Start"
        if self.hotkey.running:
            text += f" ({self.hotkey_name.get()})"
        self.start_button.configure(text=text)

    # Position capture

    def pick_position(self) -> None:
        """Count down, then save wherever the cursor is."""
        self._picking = True
        self._sync_enabled()
        self._pick_tick(PICK_COUNTDOWN_S)

    def _pick_tick(self, remaining_s: int) -> None:
        if remaining_s > 0:
            self._show(
                self.position_note,
                f"Move the cursor to the spot... {remaining_s}",
                var=self.position_text,
            )
            self._pick_job = self.root.after(1000, self._pick_tick, remaining_s - 1)
            return
        self._pick_job = None
        self._fixed_position = self.backend.cursor_position()
        self._picking = False
        self.position_mode.set("fixed")
        self._refresh()

    # Start, stop and status

    def toggle(self) -> None:
        if self.engine.running:
            self.engine.stop()
            return
        # Permissions can be removed while the app is open, so look again.
        self.check_permissions()
        if not self._can_start():
            return
        self.engine.start(self.build_config())
        self._render(self.engine.snapshot())

    def _on_hotkey(self) -> None:
        """Runs on the hotkey thread, so it must not touch Tk.

        Stopping is done right here: it cannot wait for a UI that may be busy
        while the mouse clicks many times per second. Starting reads the form,
        so it is left to `_poll` on the main thread.
        """
        if self.engine.running:
            self.engine.stop()
        else:
            self._start_requested = True

    def _poll(self) -> None:
        if self._start_requested:
            self._start_requested = False
            if not self.engine.running:
                self.toggle()
        self._render(self.engine.snapshot())
        self._poll_job = self.root.after(POLL_MS, self._poll)

    def _render(self, snapshot: Snapshot) -> None:
        if snapshot.running != self._running:
            self._running = snapshot.running
            if snapshot.running:
                self._sync_enabled()
            else:
                # Also shows the panel if the run ended on a lost permission.
                self.check_permissions()
        self.status.set(self._status_text(snapshot))
        self.counts.set(self._counts_text(snapshot))

    def _status_text(self, snapshot: Snapshot) -> str:
        if snapshot.running:
            if snapshot.next_in_s is None:
                return "Running."
            text = f"Running. Next action in {units.format_countdown(snapshot.next_in_s)}."
            if snapshot.stops_in_s is not None:
                text += f" Stops in {units.format_countdown(snapshot.stops_in_s)}."
            return text
        if snapshot.stop_reason is None:
            return "Ready."
        text = _STOP_TEXT[snapshot.stop_reason]
        return f"{text}: {snapshot.error}" if snapshot.error else text

    def _counts_text(self, snapshot: Snapshot) -> str:
        if not snapshot.running and snapshot.stop_reason is None:
            return ""
        text = f"Sent {snapshot.sent:,} · skipped {snapshot.skipped:,}"
        if snapshot.missed:
            text += f" · missed {snapshot.missed:,}"
        return text

    def shutdown(self) -> None:
        """Stop the engine, the hotkey and the timers. Waits so no key is left held."""
        for job in (self._poll_job, self._pick_job):
            if job is not None:
                self.root.after_cancel(job)
        self._poll_job = self._pick_job = None
        if self._focus_binding is not None:
            self.root.unbind("<FocusIn>", self._focus_binding)
            self._focus_binding = None
        self.engine.stop()
        self.engine.join(timeout=1.0)
        self.hotkey.stop()

    def _on_close(self) -> None:
        self.shutdown()
        self.root.destroy()


def run() -> None:
    root = tk.Tk()
    backend = QuartzBackend()
    engine = Engine(
        backend,
        frontmost=macos.frontmost_bundle_id,
        permission_granted=macos.accessibility_granted,
    )
    App(root, engine, backend, HotkeyListener(FUNCTION_KEYCODES[DEFAULT_HOTKEY]))
    root.mainloop()
