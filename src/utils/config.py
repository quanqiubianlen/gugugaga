"""Configuration management with YAML support and hot-reload."""

import time
from pathlib import Path
from typing import Any

import yaml
from PyQt6.QtCore import QFileSystemWatcher, QObject, pyqtSignal


class Config(QObject):
    """YAML-backed configuration with file-watch hot-reload.

    Emits ``config_changed`` whenever the YAML file is modified on disk
    and the in-memory state is refreshed.
    """

    config_changed = pyqtSignal()

    # ------------------------------------------------------------------
    # Built-in defaults used when a key is absent from the YAML file.
    # ------------------------------------------------------------------
    _DEFAULTS: dict[str, Any] = {
        "api": {
            "base_url": "https://api.openai.com/v1",
            "api_key": "",
        },
        "ui": {
            "theme": "dark",
            "font_size": 13,
            "window": {"width": 800, "height": 600, "title": "Desktop Agent", "opacity": 1.0},
            "floating": {"enabled": True, "size": 80, "opacity": 0.85, "position": "top-right"},
        },
        "features": {
            "hotkeys": {
                "toggle_window": "ctrl+shift+a",
                "quick_input": "ctrl+shift+q",
                "voice_input": "ctrl+shift+v",
            },
            "autostart": False,
            "conversation_history": True,
            "history_retention_days": 15,
            "tts_enabled": False,
        },
        "logging": {"level": "INFO", "file": "agent.log"},
    }

    def __init__(self, config_path: str | Path = "config.yaml", parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._path = Path(config_path).resolve()
        self._data: dict[str, Any] = dict(self._DEFAULTS)
        self._load_file()

        # Start watching for external changes (debounced by 1 s)
        self._watcher = QFileSystemWatcher(self)
        self._watcher.addPath(str(self._path))
        self._watcher.fileChanged.connect(self._on_file_changed)
        self._last_load = time.time()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def get(self, *keys: str, default: Any = None) -> Any:
        """Retrieve a nested config value by dotted or chained keys.

        Falls back to the built-in defaults table when the key path is
        not present in the YAML file.
        """
        # Try live data first
        node = self._data
        for key in keys:
            if isinstance(node, dict):
                node = node.get(key)
            else:
                node = None
                break
            if node is None:
                break

        if node is not None:
            return node

        # Fall back to defaults
        node = self._DEFAULTS
        for key in keys:
            if isinstance(node, dict):
                node = node.get(key)
            else:
                return default
            if node is None:
                return default
        return node

    def set(self, *keys: str, value: Any) -> None:
        """Set a nested config value and immediately persist to disk."""
        node = self._data
        for key in keys[:-1]:
            if key not in node or not isinstance(node[key], dict):
                node[key] = {}
            node = node[key]
        node[keys[-1]] = value
        self._save_file()

    def reload(self) -> None:
        """Force re-read the YAML file and emit config_changed."""
        self._load_file()
        self.config_changed.emit()

    @property
    def data(self) -> dict[str, Any]:
        """Return a shallow copy of the live config dict."""
        return dict(self._data)

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _load_file(self) -> None:
        if not self._path.exists():
            return
        try:
            with open(self._path, "r", encoding="utf-8") as f:
                loaded = yaml.safe_load(f) or {}
            # Deep-merge loaded values over defaults so new keys appear
            self._data = self._deep_merge(dict(self._DEFAULTS), loaded)
        except Exception:
            pass  # keep existing data on parse errors

    def _save_file(self) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        with open(self._path, "w", encoding="utf-8") as f:
            yaml.safe_dump(self._data, f, allow_unicode=True, default_flow_style=False)

    def _on_file_changed(self, path: str) -> None:
        # Debounce: editors may write multiple times in quick succession
        now = time.time()
        if now - self._last_load < 1.0:
            return
        self._last_load = now
        self.reload()
        # Re-add the path because some editors replace the file
        if str(self._path) not in self._watcher.files():
            self._watcher.addPath(str(self._path))

    @staticmethod
    def _deep_merge(base: dict, override: dict) -> dict:
        """Recursively merge override into base, returning a new dict."""
        result = dict(base)
        for key, value in override.items():
            if key in result and isinstance(result[key], dict) and isinstance(value, dict):
                result[key] = Config._deep_merge(result[key], value)
            else:
                result[key] = value
        return result
