import os
import subprocess
import re
import time
from dataclasses import dataclass

from fabric.core.service import Property, Service, Signal
from fabric.utils import exec_shell_command_async, monitor_file
from gi.repository import GLib
from loguru import logger

import utils.functions as helpers
from utils.colors import Colors


@dataclass
class Display:
    """One controllable display — either a backlight panel (brightnessctl)
    or a DDC/CI monitor (ddcutil). Everything the service needs to track
    and apply brightness for that single target lives here."""

    id: str  # stable key, e.g. "brightnessctl:intel_backlight" or "ddcutil:7"
    backend: str  # "brightnessctl" | "ddcutil"
    identifier: str  # device name for brightnessctl, bus number (as str) for ddcutil
    max_raw: int = 100  # brightnessctl: device-specific units; ddcutil: VCP10 max (usually 100)
    last_raw: int = -1
    last_percent: int = -1
    last_update_time: float = 0.0


class Brightness(Service):
    """Service for controlling screen brightness across ALL connected displays,
    using ddcutil (external DDC/CI monitors) and brightnessctl (internal
    backlight panels) simultaneously — not one-or-the-other.

    Public API is percentage-based for multi-display operations
    (set_all_brightness_percent), plus a backward-compatible single-value
    `screen_brightness` RAW property that reads/writes the PRIMARY display
    (the first one detected) exactly as before, except the setter now also
    broadcasts the equivalent percentage to every other detected display.
    """

    instance = None
    DDCUTIL_PARAMS = "--disable-dynamic-sleep --sleep-multiplier=0.05"
    MIN_CHANGE_THRESHOLD = 2  # Minimum brightness change to apply (percent)
    CACHE_INTERVAL = 3  # Cache duration in seconds (ddcutil lazy refresh)
    POLL_INTERVAL = 500  # File polling interval in ms (brightnessctl displays)

    @staticmethod
    def get_initial():
        """Singleton to get Brightness service instance."""
        if Brightness.instance is None:
            Brightness.instance = Brightness()
        return Brightness.instance

    @Signal
    def screen(self, value: int) -> None:
        """Emitted when the PRIMARY display's brightness changes (percent 0-100).
        Kept for backward compatibility with existing single-slider UI code."""
        pass

    @Signal
    def screen_for(self, display_id: str, value: int) -> None:
        """Emitted per-display whenever any individual display's brightness
        changes (percent 0-100). Use this for a UI that wants one slider
        per monitor instead of a single global one."""
        pass

    def __init__(self, backend=None, **kwargs):
        """Initialize service with automatic multi-display detection.

        `backend`, if given ("brightnessctl" or "ddcutil"), restricts
        detection to that backend only — matching the old force-backend
        behavior — but still finds ALL devices under that backend rather
        than just the first.
        """
        super().__init__(**kwargs)
        self._pending_percent = None
        self._timer_id = None
        self._poll_timer_id = None
        self._lock = GLib.Mutex()
        self._force_backend = backend

        self.displays: list[Display] = []
        self._detect_displays()

        if not self.displays:
            logger.warning(
                "No available backend for brightness control - no backlight devices or DDC/CI monitors found"
            )
            self.primary = None
            self.backend = None
            self.ddcutil_bus = None
            self.max_screen = 100
            return

        names = ", ".join(f"{d.backend}:{d.identifier}" for d in self.displays)
        logger.info(f"Detected {len(self.displays)} controllable display(s): {names}")

        # Primary display drives the legacy single-value API (max_screen,
        # screen_brightness raw value, "screen" signal, slider position).
        self.primary = self.displays[0]
        self.max_screen = self.primary.max_raw
        # Backward-compat plain attributes some callers may read directly.
        self.backend = self.primary.backend
        self.ddcutil_bus = (
            int(self.primary.identifier) if self.primary.backend == "ddcutil" else None
        )

        for d in self.displays:
            self._refresh_display_cache(d)

        # Poll brightnessctl-backed displays for external changes (hotkeys, etc).
        if any(d.backend == "brightnessctl" for d in self.displays):
            self._poll_timer_id = GLib.timeout_add(
                self.POLL_INTERVAL, self._check_brightness_files
            )

        # One-shot warm-up of ddcutil cache shortly after startup.
        if any(d.backend == "ddcutil" for d in self.displays):
            GLib.timeout_add(100, lambda: self._update_ddcutil_cache())

    # ---------------------------------------------------------------------
    # Detection — finds EVERY backlight device and EVERY DDC/CI monitor,
    # instead of the old behavior of grabbing index [0] / the first regex
    # match and stopping there.
    # ---------------------------------------------------------------------

    def _detect_displays(self):
        self.displays = []

        want_brightnessctl = self._force_backend in (None, "brightnessctl")
        want_ddcutil = self._force_backend in (None, "ddcutil")

        if want_brightnessctl and helpers.executable_exists("brightnessctl"):
            for device in self._list_backlight_devices():
                max_raw = self._read_backlight_max(device)
                if max_raw:
                    self.displays.append(
                        Display(
                            id=f"brightnessctl:{device}",
                            backend="brightnessctl",
                            identifier=device,
                            max_raw=max_raw,
                        )
                    )
                else:
                    logger.debug(
                        f"Skipping backlight device {device} - couldn't read max_brightness"
                    )

        if want_ddcutil and helpers.executable_exists("ddcutil"):
            for bus in self._detect_ddcutil_buses():
                max_raw = self._read_ddcutil_max(bus)
                if max_raw:
                    self.displays.append(
                        Display(
                            id=f"ddcutil:{bus}",
                            backend="ddcutil",
                            identifier=str(bus),
                            max_raw=max_raw,
                        )
                    )
                else:
                    logger.debug(
                        f"Skipping ddcutil bus {bus} - couldn't read VCP10 max value"
                    )

    def _list_backlight_devices(self) -> list[str]:
        """Return every backlight device, not just the first."""
        try:
            return sorted(os.listdir("/sys/class/backlight"))
        except Exception:
            return []

    def _read_backlight_max(self, device: str):
        try:
            with open(f"/sys/class/backlight/{device}/max_brightness") as f:
                return int(f.readline().strip())
        except Exception:
            return None

    def _detect_ddcutil_buses(self) -> list[int]:
        """Return the I2C bus number for EVERY DDC/CI-capable monitor ddcutil
        finds — `ddcutil detect` can list several, the old code only ever
        captured the first via re.search."""
        try:
            process = subprocess.run(
                ["ddcutil", "detect"], text=True, capture_output=True, timeout=5
            )
            if process.returncode != 0:
                return []
            return [
                int(m) for m in re.findall(r"I2C bus:\s*/dev/i2c-(\d+)", process.stdout)
            ]
        except Exception as e:
            logger.error(f"Error running ddcutil detect: {e}")
            return []

    def _read_ddcutil_max(self, bus: int):
        try:
            process = subprocess.run(
                ["ddcutil", "--bus", str(bus), *self.DDCUTIL_PARAMS.split(), "getvcp", "10"],
                text=True,
                capture_output=True,
                timeout=2,
            )
            if process.returncode == 0:
                match = re.search(
                    r"current value\s*=\s*(\d+)\s*,\s*max value\s*=\s*(\d+)",
                    process.stdout,
                )
                if match:
                    return int(match.group(2))
        except Exception as e:
            logger.error(f"Error executing ddcutil on bus {bus}: {e}")
        return None

    # ---------------------------------------------------------------------
    # Per-display read/cache helpers
    # ---------------------------------------------------------------------

    def _read_backlight_raw(self, device: str):
        try:
            with open(f"/sys/class/backlight/{device}/brightness") as f:
                return int(f.readline().strip())
        except Exception:
            return None

    def _read_ddcutil_raw(self, bus: str):
        try:
            process = subprocess.run(
                ["ddcutil", "--bus", str(bus), *self.DDCUTIL_PARAMS.split(), "getvcp", "10"],
                text=True,
                capture_output=True,
                timeout=2,
            )
            if process.returncode == 0:
                match = re.search(r"current value\s*=\s*(\d+)", process.stdout)
                if match:
                    return int(match.group(1))
        except Exception as e:
            logger.error(f"Error executing ddcutil on bus {bus}: {e}")
        return None

    def _refresh_display_cache(self, d: Display):
        raw = None
        if d.backend == "brightnessctl":
            raw = self._read_backlight_raw(d.identifier)
        elif d.backend == "ddcutil":
            raw = self._read_ddcutil_raw(d.identifier)

        if raw is not None:
            d.last_raw = raw
            d.last_percent = int((raw / d.max_raw) * 100) if d.max_raw else 0
            d.last_update_time = time.time()

    def _check_brightness_files(self):
        """Poll every brightnessctl-backed display for changes made outside
        this service (hardware keys, another app, etc)."""
        for d in self.displays:
            if d.backend != "brightnessctl":
                continue
            try:
                file_path = f"/sys/class/backlight/{d.identifier}/brightness"
                if not os.path.exists(file_path):
                    continue
                mtime = os.path.getmtime(file_path)
                if mtime <= d.last_update_time:
                    continue

                raw = self._read_backlight_raw(d.identifier)
                if raw is None or raw == d.last_raw:
                    d.last_update_time = mtime
                    continue

                percent = int((raw / d.max_raw) * 100) if d.max_raw else 0
                d.last_raw = raw
                d.last_update_time = mtime

                if abs(percent - d.last_percent) >= self.MIN_CHANGE_THRESHOLD:
                    d.last_percent = percent
                    self.emit("screen_for", d.id, percent)
                    if d is self.primary:
                        self.emit("screen", percent)
            except Exception as e:
                logger.error(f"Error checking brightness file for {d.id}: {e}")
        return True

    def _update_ddcutil_cache(self):
        for d in self.displays:
            if d.backend == "ddcutil":
                self._refresh_display_cache(d)
        return False

    # ---------------------------------------------------------------------
    # Public API
    # ---------------------------------------------------------------------

    @Property(int, "read-write")
    def screen_brightness(self):
        """RAW value (0 to max_screen) of the PRIMARY display. Preserved for
        backward compatibility with existing single-slider UI bindings."""
        if not self.displays:
            return -1
        if (
            self.primary.backend == "ddcutil"
            and time.time() - self.primary.last_update_time >= self.CACHE_INTERVAL
        ):
            self._refresh_display_cache(self.primary)
        return self.primary.last_raw

    @screen_brightness.setter
    def screen_brightness(self, value: int):
        """Setting the primary display's raw brightness now applies the
        equivalent PERCENTAGE to every detected display, not just the one
        it used to talk to."""
        if not self.displays:
            return

        self._lock.lock()
        try:
            value = max(0, min(value, self.primary.max_raw))
            percent = (
                int((value / self.primary.max_raw) * 100) if self.primary.max_raw else 0
            )

            current_percent = self.primary.last_percent
            if current_percent != -1 and abs(percent - current_percent) < self.MIN_CHANGE_THRESHOLD:
                return

            self._pending_percent = percent
            if self._timer_id:
                GLib.source_remove(self._timer_id)
            self._timer_id = GLib.timeout_add(50, self._apply_percent_to_all)
        finally:
            self._lock.unlock()

    def set_all_brightness_percent(self, percent: int):
        """Explicit multi-monitor entry point: set every detected display to
        the given percentage (0-100) directly, without going through the
        primary display's raw-value scale."""
        if not self.displays:
            return

        self._lock.lock()
        try:
            self._pending_percent = max(0, min(percent, 100))
            if self._timer_id:
                GLib.source_remove(self._timer_id)
            self._timer_id = GLib.timeout_add(50, self._apply_percent_to_all)
        finally:
            self._lock.unlock()

    def _apply_percent_to_all(self):
        """Apply the pending percentage to every display, each converted to
        its own raw range. Debounced the same way the old single-display
        setter was."""
        self._lock.lock()
        try:
            if self._pending_percent is None:
                self._timer_id = None
                return False
            percent = self._pending_percent
            self._pending_percent = None
            self._timer_id = None
        finally:
            self._lock.unlock()

        for d in self.displays:
            try:
                raw = int(round((percent / 100) * d.max_raw))
                d.last_raw = raw
                d.last_percent = percent
                d.last_update_time = time.time()

                if d.backend == "brightnessctl":
                    exec_shell_command_async(
                        f"brightnessctl --device '{d.identifier}' set {raw}"
                    )
                elif d.backend == "ddcutil":
                    exec_shell_command_async(
                        f"ddcutil --bus {d.identifier} {self.DDCUTIL_PARAMS} --terse setvcp 10 {raw}",
                        lambda exit_code, stdout, stderr, dname=d.id: (
                            logger.error(f"ddcutil error on {dname} (code {exit_code}): {stderr}")
                            if exit_code != 0
                            else None
                        ),
                    )

                self.emit("screen_for", d.id, percent)
            except Exception as e:
                logger.error(f"Error setting brightness for {d.id}: {e}")

        self.emit("screen", percent)
        return False

    def cleanup(self):
        """Clean up resources when service is stopped."""
        if self._timer_id:
            GLib.source_remove(self._timer_id)
            self._timer_id = None

        if self._poll_timer_id:
            GLib.source_remove(self._poll_timer_id)
            self._poll_timer_id = None