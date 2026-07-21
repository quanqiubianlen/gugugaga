"""Settings dialog with tabbed interface for all configuration sections."""

from PyQt6.QtCore import Qt, QTimer, pyqtSignal
from src.utils.hotkey import validate_hotkey
from PyQt6.QtGui import QFont
from PyQt6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QSlider,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)


class SettingsDialog(QDialog):
    """Modal settings window.  Reads from a Config object, writes back on Accept."""

    settings_applied = pyqtSignal()

    # Position presets
    POSITIONS = ["top-right", "top-left", "bottom-right", "bottom-left"]

    def __init__(self, config, parent=None) -> None:
        super().__init__(parent)
        self._config = config
        self.setWindowTitle("Settings")
        self.setMinimumWidth(480)

        tabs = QTabWidget()

        tabs.addTab(self._build_general_tab(), "General")
        tabs.addTab(self._build_api_tab(), "API")
        tabs.addTab(self._build_features_tab(), "Features")

        # Dialog buttons
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self._on_accept)
        buttons.rejected.connect(self.reject)

        layout = QVBoxLayout(self)
        layout.addWidget(tabs)
        layout.addWidget(buttons)

        self.setStyleSheet("""
            QDialog { background: #2b2b2b; color: #eee; }
            QTabWidget::pane { border: 1px solid #555; background: #2b2b2b; }
            QTabBar::tab {
                background: #363636; color: #aaa; padding: 8px 16px;
                border: 1px solid #555; border-bottom: none;
                border-top-left-radius: 4px; border-top-right-radius: 4px;
            }
            QTabBar::tab:selected { background: #2b2b2b; color: #fff; }
            QLabel { color: #ddd; }
            QLineEdit {
                background: #1e1e2e; color: #cdd6f4; border: 1px solid #45475a;
                border-radius: 4px; padding: 6px 10px;
            }
            QComboBox {
                background: #1e1e2e; color: #cdd6f4; border: 1px solid #45475a;
                border-radius: 4px; padding: 4px 8px;
            }
            QComboBox::drop-down { border: none; }
            QComboBox QAbstractItemView {
                background: #1e1e2e; color: #cdd6f4; selection-background-color: #4A90D9;
            }
            QCheckBox { color: #ddd; spacing: 8px; }
            QCheckBox::indicator { width: 16px; height: 16px; }
            QSlider::groove:horizontal {
                height: 6px; background: #45475a; border-radius: 3px;
            }
            QSlider::handle:horizontal {
                width: 16px; height: 16px; background: #4A90D9;
                border-radius: 8px; margin: -5px 0;
            }
            QGroupBox {
                color: #ccc; border: 1px solid #555; border-radius: 6px;
                margin-top: 12px; padding-top: 16px; font-weight: bold;
            }
            QGroupBox::title {
                subcontrol-origin: margin; left: 12px; padding: 0 6px;
            }
            QPushButton {
                background: #4A90D9; color: white; border: none;
                border-radius: 4px; padding: 6px 16px;
            }
            QPushButton:hover { background: #5BA0E9; }
        """)

    # ------------------------------------------------------------------
    # Tab builders
    # ------------------------------------------------------------------

    def _build_general_tab(self) -> QWidget:
        w = QWidget()
        layout = QVBoxLayout(w)
        layout.setSpacing(16)

        # Appearance group
        group = QGroupBox("Appearance")
        form = QFormLayout(group)
        form.setSpacing(10)

        self._theme_combo = QComboBox()
        self._theme_combo.addItems(["dark", "light", "system"])
        self._theme_combo.setCurrentText(self._config.get("ui", "theme", default="dark"))
        form.addRow("Theme:", self._theme_combo)

        self._opacity_slider = QSlider(Qt.Orientation.Horizontal)
        self._opacity_slider.setRange(50, 100)
        self._opacity_slider.setValue(int(self._config.get("ui", "window", "opacity", default=1.0) * 100))
        self._opacity_label = QLabel(f"{self._opacity_slider.value()}%")
        row = QHBoxLayout()
        row.addWidget(self._opacity_slider)
        row.addWidget(self._opacity_label)
        self._opacity_slider.valueChanged.connect(
            lambda v: self._opacity_label.setText(f"{v}%")
        )
        form.addRow("Window opacity:", row)

        # Font size
        font_group = QGroupBox("Display")
        font_form = QFormLayout(font_group)
        font_form.setSpacing(10)

        self._font_slider = QSlider(Qt.Orientation.Horizontal)
        self._font_slider.setRange(10, 24)
        self._font_slider.setValue(self._config.get("ui", "font_size", default=13))
        self._font_label = QLabel(f"{self._font_slider.value()}px")
        self._font_slider.valueChanged.connect(lambda v: self._font_label.setText(f"{v}px"))
        row_f = QHBoxLayout()
        row_f.addWidget(self._font_slider)
        row_f.addWidget(self._font_label)
        font_form.addRow("Font size:", row_f)
        layout.addWidget(font_group)

        # TTS
        self._tts_check = QCheckBox()
        self._tts_check.setChecked(self._config.get("features", "tts_enabled", default=False))
        font_form.addRow("Text-to-speech:", self._tts_check)

        # Hotkeys group
        hk_group = QGroupBox("Hotkeys")
        hk_form = QFormLayout(hk_group)
        hk_form.setSpacing(10)

        self._hk_toggle_edit = QLineEdit()
        self._hk_toggle_edit.setText(self._config.get("features", "hotkeys", "toggle_window", default="ctrl+shift+a"))
        self._hk_toggle_edit.setPlaceholderText("e.g. ctrl+shift+a")
        hk_form.addRow("Toggle window:", self._hk_toggle_edit)

        self._hk_quick_edit = QLineEdit()
        self._hk_quick_edit.setText(self._config.get("features", "hotkeys", "quick_input", default="ctrl+shift+q"))
        self._hk_quick_edit.setPlaceholderText("e.g. ctrl+shift+q")
        hk_form.addRow("Quick input:", self._hk_quick_edit)

        self._hk_voice_edit = QLineEdit()
        self._hk_voice_edit.setText(self._config.get("features", "hotkeys", "voice_input", default="ctrl+shift+v"))
        self._hk_voice_edit.setPlaceholderText("e.g. ctrl+shift+v")
        hk_form.addRow("Voice input:", self._hk_voice_edit)

        layout.addWidget(hk_group)

        self._hk_fields = {
            "toggle_window": self._hk_toggle_edit,
            "quick_input": self._hk_quick_edit,
            "voice_input": self._hk_voice_edit,
        }
        # Live validation feedback
        for edit in self._hk_fields.values():
            edit.textChanged.connect(self._validate_hotkeys)

        layout.addWidget(group)
        layout.addStretch()
        return w

    def _build_api_tab(self) -> QWidget:
        w = QWidget()
        layout = QVBoxLayout(w)
        layout.setSpacing(16)

        group = QGroupBox("API Connection")
        form = QFormLayout(group)
        form.setSpacing(10)

        self._api_url_edit = QLineEdit()
        self._api_url_edit.setText(self._config.get("api", "base_url", default=""))
        self._api_url_edit.setPlaceholderText("https://api.example.com/v1")
        form.addRow("API URL:", self._api_url_edit)

        self._api_key_edit = QLineEdit()
        self._api_key_edit.setText(self._config.get("api", "api_key", default=""))
        self._api_key_edit.setEchoMode(QLineEdit.EchoMode.Password)
        self._api_key_edit.setPlaceholderText("sk-...")
        form.addRow("API Key:", self._api_key_edit)

        toggle_btn = QPushButton("Show")
        toggle_btn.setCheckable(True)
        toggle_btn.toggled.connect(
            lambda checked: self._api_key_edit.setEchoMode(
                QLineEdit.EchoMode.Normal if checked else QLineEdit.EchoMode.Password
            )
        )
        form.addRow("", toggle_btn)

        layout.addWidget(group)
        layout.addStretch()
        return w

    def _build_features_tab(self) -> QWidget:
        w = QWidget()
        layout = QVBoxLayout(w)
        layout.setSpacing(16)

        group = QGroupBox("Features")
        form = QFormLayout(group)
        form.setSpacing(10)

        self._autostart_check = QCheckBox()
        self._autostart_check.setChecked(self._config.get("features", "autostart", default=False))
        form.addRow("Start with Windows:", self._autostart_check)

        self._history_check = QCheckBox()
        self._history_check.setChecked(self._config.get("features", "conversation_history", default=True))
        form.addRow("Save conversation history:", self._history_check)

        layout.addWidget(group)

        # Floating icon group
        float_group = QGroupBox("Floating Icon")
        fform = QFormLayout(float_group)
        fform.setSpacing(10)

        self._float_enabled_check = QCheckBox()
        self._float_enabled_check.setChecked(self._config.get("ui", "floating", "enabled", default=True))
        fform.addRow("Enabled:", self._float_enabled_check)

        self._float_opacity_slider = QSlider(Qt.Orientation.Horizontal)
        self._float_opacity_slider.setRange(20, 100)
        self._float_opacity_slider.setValue(int(self._config.get("ui", "floating", "opacity", default=0.85) * 100))
        self._float_opacity_label = QLabel(f"{self._float_opacity_slider.value()}%")
        self._float_opacity_slider.valueChanged.connect(
            lambda v: self._float_opacity_label.setText(f"{v}%")
        )
        row2 = QHBoxLayout()
        row2.addWidget(self._float_opacity_slider)
        row2.addWidget(self._float_opacity_label)
        fform.addRow("Opacity:", row2)

        self._float_pos_combo = QComboBox()
        self._float_pos_combo.addItems(self.POSITIONS)
        current_pos = self._config.get("ui", "floating", "position", default="top-right")
        if current_pos in self.POSITIONS:
            self._float_pos_combo.setCurrentText(current_pos)
        fform.addRow("Position:", self._float_pos_combo)

        layout.addWidget(float_group)
        layout.addStretch()
        return w

    # ------------------------------------------------------------------
    # Accept
    # ------------------------------------------------------------------

    def _validate_hotkeys(self) -> None:
        """Highlight hotkey fields with invalid or conflicting values."""
        values: dict[str, str] = {}
        for action, edit in self._hk_fields.items():
            val = edit.text().strip().lower()
            values[action] = val
            valid, err = validate_hotkey(val)
            if val and not valid:
                edit.setStyleSheet("QLineEdit { background: #3e1a1a; border: 1px solid #E74C3C; }")
                edit.setToolTip(err)
            else:
                edit.setStyleSheet("")
                edit.setToolTip("")

        # Conflict detection (only among non-empty fields)
        seen: dict[str, str] = {}
        for action, val in values.items():
            if not val:
                continue
            if val in seen:
                conflict_label = seen[val]
                for a, e in self._hk_fields.items():
                    if a in (action, conflict_label):
                        e.setStyleSheet("QLineEdit { background: #3e1a1a; border: 1px solid #F0A030; }")
                        e.setToolTip(f"Conflict: same hotkey as '{conflict_label if a == action else action}'")
            else:
                seen[val] = action

    def _on_accept(self) -> None:
        self._config.set("ui", "theme", value=self._theme_combo.currentText())
        self._config.set("ui", "window", "opacity", value=self._opacity_slider.value() / 100.0)
        self._config.set("ui", "font_size", value=self._font_slider.value())
        self._config.set("features", "tts_enabled", value=self._tts_check.isChecked())

        for action, edit in self._hk_fields.items():
            self._config.set("features", "hotkeys", action, value=edit.text().strip())
        self._config.set("api", "base_url", value=self._api_url_edit.text().strip())
        self._config.set("api", "api_key", value=self._api_key_edit.text().strip())
        self._config.set("features", "autostart", value=self._autostart_check.isChecked())
        self._config.set("features", "conversation_history", value=self._history_check.isChecked())
        self._config.set("ui", "floating", "enabled", value=self._float_enabled_check.isChecked())
        self._config.set("ui", "floating", "opacity", value=self._float_opacity_slider.value() / 100.0)
        self._config.set("ui", "floating", "position", value=self._float_pos_combo.currentText())

        self.settings_applied.emit()
        self.accept()
