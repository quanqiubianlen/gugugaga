"""Autonomous system monitor -- lets the agent perceive the system.

Monitors CPU, memory, disk, active window title, clipboard, and filesystem
changes. Writes a daily observation journal and can trigger proactive alerts.
"""

import ctypes
import os
import time
from ctypes import wintypes
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from PyQt6.QtCore import QObject, QTimer, pyqtSignal

try:
    import psutil
    HAS_PSUTIL = True
except ImportError:
    HAS_PSUTIL = False


# ---------------------------------------------------------------------------
# Win32 API bindings via ctypes (no subprocess, no console window)
# ---------------------------------------------------------------------------

_user32 = ctypes.windll.user32
_kernel32 = ctypes.windll.kernel32

_user32.GetForegroundWindow.restype = wintypes.HWND
_user32.GetWindowTextW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
_user32.GetWindowTextW.restype = ctypes.c_int
_user32.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
_user32.GetWindowThreadProcessId.restype = wintypes.DWORD


def _get_active_window_info():
    """Return (window_title, process_name) using pure ctypes. No console window."""
    hwnd = _user32.GetForegroundWindow()
    if not hwnd:
        return ("", "")

    buf = ctypes.create_unicode_buffer(256)
    _user32.GetWindowTextW(hwnd, buf, 256)
    title = buf.value or ""

    pid = wintypes.DWORD()
    _user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))

    proc_name = ""
    if pid.value:
        try:
            handle = _kernel32.OpenProcess(0x0400 | 0x0010, False, pid.value)
            if handle:
                exe_buf = ctypes.create_unicode_buffer(260)
                size = wintypes.DWORD(260)
                if _kernel32.QueryFullProcessImageNameW(handle, 0, exe_buf, ctypes.byref(size)):
                    proc_name = Path(exe_buf.value).stem
                _kernel32.CloseHandle(handle)
        except Exception:
            pass

    return (title, proc_name)


# ---------------------------------------------------------------------------
# Journal (daily markdown log)
# ---------------------------------------------------------------------------

class ObservationJournal:
    """Append observations to a daily markdown file."""

    def __init__(self, journal_dir=None):
        if journal_dir is None:
            journal_dir = Path("journal")
        self._dir = journal_dir
        self._dir.mkdir(parents=True, exist_ok=True)

    def log(self, observation, category="system"):
        now = datetime.now()
        filename = now.strftime("%Y-%m-%d") + ".md"
        path = self._dir / filename
        timestamp = now.strftime("%H:%M:%S")
        line = f"- **[{timestamp}]** ({category}) {observation}\n"
        with open(path, "a", encoding="utf-8") as f:
            f.write(line)


# ---------------------------------------------------------------------------
# System Monitor
# ---------------------------------------------------------------------------

class SystemMonitor(QObject):
    """Monitors system resources and emits signals on significant changes."""

    alert = pyqtSignal(str, str)
    active_window_changed = pyqtSignal(str, str)
    clipboard_changed = pyqtSignal(str)

    def __init__(self, journal=None, parent=None):
        super().__init__(parent)
        self._journal = journal
        self._enabled = True
        self._last_window = ""
        self._last_clipboard = ""
        self._last_cpu_alert = 0.0
        self._last_mem_alert = 0.0
        self._last_disk_alert = 0.0

        # Fast poll: active window + clipboard (every 30s)
        self._poll_timer = QTimer(self)
        self._poll_timer.timeout.connect(self._poll)
        self._poll_timer.start(30_000)

        # Slow poll: resources + journal snapshot (every 2 min)
        self._slow_timer = QTimer(self)
        self._slow_timer.timeout.connect(self._poll_slow)
        self._slow_timer.start(120_000)

        # Defer initial poll so the app finishes starting up
        QTimer.singleShot(5000, self._poll)
        QTimer.singleShot(10000, self._poll_slow)

    @property
    def enabled(self):
        return self._enabled

    @enabled.setter
    def enabled(self, value):
        self._enabled = value

    def _poll(self):
        if not self._enabled:
            return
        self._check_active_window()
        self._check_clipboard()

    def _poll_slow(self):
        if not self._enabled:
            return
        self._check_resources()
        self._write_snapshot()

    def _check_active_window(self):
        """Pure ctypes Win32 API -- no PowerShell, no console window."""
        try:
            title, proc = _get_active_window_info()
            if title and title != self._last_window:
                self._last_window = title
                self.active_window_changed.emit(title, proc)
                if self._journal:
                    self._journal.log(
                        f"Active window: **{title}** ({proc})",
                        category="focus",
                    )
        except Exception:
            pass

    def _check_clipboard(self):
        try:
            from PyQt6.QtWidgets import QApplication
            app = QApplication.instance()
            if app is None:
                return
            clipboard = app.clipboard()
            if clipboard is None:
                return
            text = clipboard.text()
            if text and text != self._last_clipboard:
                self._last_clipboard = text
                preview = text[:200] + ("..." if len(text) > 200 else "")
                self.clipboard_changed.emit(preview)
        except Exception:
            pass

    def _check_resources(self):
        now = time.time()
        if HAS_PSUTIL:
            cpu = psutil.cpu_percent(interval=1)
            if cpu > 90 and (now - self._last_cpu_alert) > 300:
                self._last_cpu_alert = now
                self.alert.emit(f"CPU usage is very high: {cpu:.0f}%", "cpu_high")

        if HAS_PSUTIL:
            mem = psutil.virtual_memory()
            if mem.percent > 90 and (now - self._last_mem_alert) > 300:
                self._last_mem_alert = now
                self.alert.emit(
                    f"Memory usage is critical: {mem.percent:.0f}% "
                    f"({mem.available // (1024*1024)} MB free)",
                    "memory_high",
                )

        if HAS_PSUTIL:
            for part in psutil.disk_partitions():
                try:
                    usage = psutil.disk_usage(part.mountpoint)
                    if usage.percent > 90 and (now - self._last_disk_alert) > 3600:
                        self._last_disk_alert = now
                        self.alert.emit(
                            f"Disk {part.device} ({part.mountpoint}) is nearly full: "
                            f"{usage.percent:.0f}% ({usage.free // (1024*1024*1024)} GB free)",
                            "disk_low",
                        )
                except Exception:
                    pass

    def _write_snapshot(self):
        if not self._journal or not HAS_PSUTIL:
            return
        try:
            cpu = psutil.cpu_percent(interval=0.5)
            mem = psutil.virtual_memory()
            disk = psutil.disk_usage(os.getcwd())
            self._journal.log(
                f"CPU: {cpu:.0f}% | Mem: {mem.percent:.0f}% "
                f"({mem.available // (1024*1024)} MB free) | "
                f"Disk: {disk.percent:.0f}% "
                f"({disk.free // (1024*1024*1024)} GB free)",
                category="snapshot",
            )
        except Exception:
            pass

    def get_status(self):
        status = {"timestamp": datetime.now(timezone.utc).isoformat()}
        if HAS_PSUTIL:
            try:
                status["cpu_percent"] = psutil.cpu_percent(interval=0.5)
                mem = psutil.virtual_memory()
                status["memory_percent"] = mem.percent
                status["memory_available_mb"] = mem.available // (1024 * 1024)
                disk = psutil.disk_usage(os.getcwd())
                status["disk_percent"] = disk.percent
                status["disk_free_gb"] = disk.free // (1024 * 1024 * 1024)
                status["active_window"] = self._last_window
            except Exception:
                pass
        return status

    def get_journal_today(self):
        if not self._journal:
            return ""
        filename = datetime.now().strftime("%Y-%m-%d") + ".md"
        path = self._journal._dir / filename
        if path.exists():
            return path.read_text(encoding="utf-8")
        return ""


MONITOR_TOOLS: list[dict[str, Any]] = [
    {
        "type": "function",
        "function": {
            "name": "get_system_status",
            "description": (
                "Get current system status: CPU usage, memory usage, disk space, "
                "active window title. Use to check how the computer is doing."
            ),
            "parameters": {
                "type": "object",
                "properties": {},
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_daily_journal",
            "description": (
                "Read today's observation journal -- what the agent has noticed today "
                "about system activity, window switches, alerts, etc."
            ),
            "parameters": {
                "type": "object",
                "properties": {},
                "required": [],
            },
        },
    },
]
