"""Windows auto-start registry utility."""

import sys
import winreg
from pathlib import Path


REG_PATH = r"Software\Microsoft\Windows\CurrentVersion\Run"
APP_NAME = "DesktopAgent"


def _resolve_target() -> str:
    """Build the command line that starts the agent."""
    exe = sys.executable
    main = str(Path(__file__).resolve().parents[1] / "main.py")
    return f'"{exe}" "{main}"'


def is_enabled() -> bool:
    """Return True if the app is registered for auto-start."""
    try:
        key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, REG_PATH)
        value, _ = winreg.QueryValueEx(key, APP_NAME)
        winreg.CloseKey(key)
        return bool(value)
    except FileNotFoundError:
        return False


def enable() -> None:
    """Register the app to start with Windows."""
    target = _resolve_target()
    key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, REG_PATH, 0, winreg.KEY_SET_VALUE)
    winreg.SetValueEx(key, APP_NAME, 0, winreg.REG_SZ, target)
    winreg.CloseKey(key)


def disable() -> None:
    """Remove the app from Windows auto-start."""
    try:
        key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, REG_PATH, 0, winreg.KEY_SET_VALUE)
        winreg.DeleteValue(key, APP_NAME)
        winreg.CloseKey(key)
    except FileNotFoundError:
        pass


def toggle() -> bool:
    """Toggle auto-start and return the new state."""
    if is_enabled():
        disable()
        return False
    else:
        enable()
        return True
