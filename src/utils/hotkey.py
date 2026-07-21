"""Global hotkey manager with multi-action support and conflict detection.

Cross-platform: normalises key names for Windows, macOS, and Linux.
"""

import platform
from typing import Callable

import keyboard


# ---------------------------------------------------------------------------
# Platform helpers
# ---------------------------------------------------------------------------

_current_os = platform.system()


def platform_modifier() -> str:
    """Return the primary modifier name for the current OS."""
    if _current_os == "Darwin":
        return "cmd"
    return "ctrl"


def normalise_hotkey(hotkey: str) -> str:
    """Convert a user-facing hotkey string to one ``keyboard`` understands.

    On macOS, ``ctrl`` is automatically remapped to ``cmd`` unless the
    user explicitly writes ``ctrl`` (not ``cmd``).  On Windows / Linux
    the string is passed through as-is after lowercasing.
    """
    hotkey = hotkey.strip().lower()
    if _current_os == "Darwin":
        # Detect: if user wrote "cmd+..." keep it; otherwise replace "ctrl" ? "cmd"
        if "cmd" not in hotkey:
            hotkey = hotkey.replace("ctrl", "cmd")
    return hotkey


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------

# All known key names recognised by the ``keyboard`` library (partial but
# sufficient for typical hotkey strings).
_VALID_KEYS = {
    "ctrl", "shift", "alt", "cmd", "windows", "left windows", "right windows",
    "a", "b", "c", "d", "e", "f", "g", "h", "i", "j", "k", "l", "m",
    "n", "o", "p", "q", "r", "s", "t", "u", "v", "w", "x", "y", "z",
    "0", "1", "2", "3", "4", "5", "6", "7", "8", "9",
    "f1", "f2", "f3", "f4", "f5", "f6", "f7", "f8", "f9", "f10", "f11", "f12",
    "space", "enter", "tab", "esc", "escape", "backspace",
    "up", "down", "left", "right",
    "home", "end", "page up", "page down",
    "insert", "delete", "print screen", "scroll lock", "pause",
}


def validate_hotkey(hotkey: str) -> tuple[bool, str]:
    """Return (is_valid, error_message) for a hotkey string.

    A valid hotkey is a ``+``-separated list of known key names, with at
    least one non-modifier key and at least one modifier (ctrl/shift/alt/cmd).
    """
    hotkey = hotkey.strip().lower()
    if not hotkey:
        return False, "Hotkey must not be empty."

    parts = [p.strip() for p in hotkey.split("+") if p.strip()]
    if len(parts) < 2:
        return False, "Hotkey must include at least one modifier (ctrl/shift/alt) and one key."

    modifiers = {"ctrl", "shift", "alt", "cmd", "windows"}
    has_modifier = any(p in modifiers for p in parts)
    if not has_modifier:
        return False, "Hotkey must include at least one modifier (ctrl/shift/alt)."

    for part in parts:
        if part not in _VALID_KEYS:
            return False, f"Unknown key: '{part}'"

    return True, ""


# ---------------------------------------------------------------------------
# Hotkey manager
# ---------------------------------------------------------------------------

class HotkeyManager:
    """Register and manage multiple global hotkeys with conflict detection."""

    def __init__(self) -> None:
        self._actions: dict[str, str] = {}       # action_name ? hotkey_string
        self._callbacks: dict[str, Callable] = {} # action_name ? callback

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def register(self, action: str, hotkey: str, callback: Callable[[], None]) -> tuple[bool, str]:
        """Register (or re-register) a hotkey for *action*.

        Returns (success, message).  On failure the previous binding for
        *action* (if any) is left intact.
        """
        valid, err = validate_hotkey(hotkey)
        if not valid:
            return False, err

        conflict = self._find_conflict(hotkey, exclude=action)
        if conflict is not None:
            return False, f"Hotkey '{hotkey}' is already used by '{conflict}'."

        normalised = normalise_hotkey(hotkey)

        # Remove old binding for this action
        if action in self._actions:
            old = normalise_hotkey(self._actions[action])
            try:
                keyboard.remove_hotkey(old)
            except Exception:
                pass

        try:
            keyboard.add_hotkey(normalised, callback)
        except Exception as exc:
            return False, str(exc)

        self._actions[action] = hotkey
        self._callbacks[action] = callback
        return True, f"Registered '{hotkey}' for '{action}'."

    def unregister(self, action: str) -> None:
        """Remove a single hotkey binding."""
        if action not in self._actions:
            return
        normalised = normalise_hotkey(self._actions[action])
        try:
            keyboard.remove_hotkey(normalised)
        except Exception:
            pass
        self._actions.pop(action, None)
        self._callbacks.pop(action, None)

    def unregister_all(self) -> None:
        """Remove every registered hotkey."""
        keyboard.unhook_all()
        self._actions.clear()
        self._callbacks.clear()

    def get_hotkey(self, action: str) -> str | None:
        """Return the hotkey string bound to *action*, or None."""
        return self._actions.get(action)

    def list_actions(self) -> dict[str, str]:
        """Return a copy of {action: hotkey_string}."""
        return dict(self._actions)

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _find_conflict(self, hotkey: str, exclude: str) -> str | None:
        """Return the action name that already uses *hotkey*, or None."""
        normalised = normalise_hotkey(hotkey)
        for action, existing in self._actions.items():
            if action == exclude:
                continue
            if normalise_hotkey(existing) == normalised:
                return action
        return None
