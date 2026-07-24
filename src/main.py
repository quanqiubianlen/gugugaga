"""Desktop Agent -- main entry point."""


import os
import sys
from pathlib import Path

# Ensure the project root is on sys.path so 'src.*' imports work
# regardless of how the script is invoked.
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from PyQt6.QtCore import Qt, QTimer, pyqtSignal
from PyQt6.QtGui import QFont, QIcon
from PyQt6.QtWidgets import (
    QApplication,
    QInputDialog,
    QLineEdit,
    QMessageBox,
    QVBoxLayout,
    QWidget,
)

from src.agent.agent_handler import ConversationManager
from src.agent.api_client import APIClient, VisionClient
from src.agent.memory import MemoryStore
from src.agent.monitor import ObservationJournal, SystemMonitor
from src.agent.scheduler import BackgroundScheduler
from src.ui.pet import DesktopPet
from src.ui.settings import SettingsDialog
from src.ui.tray import TrayIcon
from src.ui.window import MainWindow
from src.utils.autostart import disable as autostart_disable
from src.utils.autostart import enable as autostart_enable
from src.utils.config import Config
from src.utils.hotkey import HotkeyManager, platform_modifier
from src.utils.logger import setup_logger
from src.utils.speech import SpeechToText, TextToSpeech
from src.utils.tools import set_memory_store


# ---------------------------------------------------------------------------
# Quick-input dialog
# ---------------------------------------------------------------------------

class QuickInputDialog(QWidget):
    submitted = pyqtSignal(str)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Quick Input")
        self.setFixedSize(420, 64)
        self.setWindowFlags(Qt.WindowType.Tool | Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        self._input = QLineEdit()
        self._input.setPlaceholderText("Ask the Agent...  (Esc to close)")
        self._input.setFont(QFont("Segoe UI", 13))
        self._input.setStyleSheet("QLineEdit { background: #313244; color: #cdd6f4; border: 2px solid #4A90D9; border-radius: 10px; padding: 12px 18px; }")
        self._input.returnPressed.connect(self._on_submit)
        layout.addWidget(self._input)
        self._input.installEventFilter(self)

    def eventFilter(self, obj, event) -> bool:
        if obj is self._input and event.type() == event.Type.KeyPress and event.key() == Qt.Key.Key_Escape:
            self.hide()
            return True
        return super().eventFilter(obj, event)

    def _on_submit(self) -> None:
        text = self._input.text().strip()
        if text:
            self.submitted.emit(text)
        self._input.clear()
        self.hide()

    def popup(self) -> None:
        screen = QApplication.primaryScreen()
        if screen:
            geo = screen.availableGeometry()
            self.move(geo.center().x() - self.width() // 2, geo.center().y() - self.height() // 2 - 80)
        self._input.clear()
        self._input.setFocus()
        self.show()
        self.raise_()
        self.activateWindow()


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def find_icon() -> Path:
    # Prefer pet image, fall back to generic icon
    g = chr(0x5495)+chr(0x5495)+chr(0x560E)+chr(0x560E)
    pet_img = Path(__file__).parent / "assets" / "pet" / (g + ".png")
    candidates = [
        pet_img,
        Path(__file__).parent / "assets" / "icon.png",
        Path("src/assets/icon.png"),
        Path("assets/icon.png"),
    ]
    for c in candidates:
        if c.exists():
            return c
    return candidates[0]


def main() -> None:
    app = QApplication(sys.argv)
    app.setApplicationName("Desktop Agent")
    app.setQuitOnLastWindowClosed(False)

    config = Config()
    logger = setup_logger(
        level=config.get("logging", "level", default="INFO"),
        log_file=config.get("logging", "file", default="agent.log"),
    )
    mod = platform_modifier()
    logger.info(f"Starting Desktop Agent...  (platform modifier: {mod})")

    icon_path = find_icon()
    icon = QIcon(str(icon_path)) if icon_path.exists() else QIcon()
    app.setWindowIcon(icon)

    # --- API client & conversation manager ---
    api_client = APIClient(
        base_url=config.get("api", "base_url", default="https://api.openai.com/v1"),
        api_key=config.get("api", "api_key", default=""),
        model=config.get("api", "model", default="deepseek-chat"),
    )
    memory_store = MemoryStore()
    set_memory_store(memory_store)
    vc=config.get("vision",default={})
    vision_client=VisionClient(vc.get("base_url",""),vc.get("api_key",""),vc.get("model","gpt-4o")) if vc.get("enabled",False) else None
    conv_mgr = ConversationManager(api_client, memory_store=memory_store)

    # --- Background systems: monitor & scheduler ---
    journal = ObservationJournal()
    monitor = SystemMonitor(journal=journal)
    scheduler = BackgroundScheduler()

    def on_agent_checkin(message: str) -> None:
        show_window()
        window.add_agent_message(message)

    scheduler.check_in.connect(on_agent_checkin)

    def on_system_alert(message: str, category: str) -> None:
        logger.warning(f"System alert [{category}]: {message}")
        if pet:
            pet.set_badge_count(pet._badge_count + 1)

    monitor.alert.connect(on_system_alert)

    # --- Main window ---
    window = MainWindow(
        conv_manager=conv_mgr,
        vision_client=vision_client,
        title=config.get("ui", "window", "title", default="Desktop Agent"),
        width=config.get("ui", "window", "width", default=900),
        height=config.get("ui", "window", "height", default=600),
        theme=config.get("ui", "theme", default="dark"),
        window_opacity=config.get("ui", "window", "opacity", default=1.0),
    )
    window.setWindowIcon(icon)

    # Track user interactions for idle detection
    window.input_widget.textChanged.connect(lambda: scheduler.user_interacted())

    # Initial font size from config
    font_size = config.get("ui", "font_size", default=13)
    window.set_font_size(font_size)

    # --- Speech ---
    stt = SpeechToText()
    tts = TextToSpeech()
    tts.enabled = config.get("features", "tts_enabled", default=False)
    window.set_tts_checked(tts.enabled)

    # --- Quick-input ---
    quick_dlg = QuickInputDialog()

    def on_quick_submit(text: str) -> None:
        show_window()
        window.input_widget.setText(text)
        window._on_send()

    quick_dlg.submitted.connect(on_quick_submit)

    # --- System tray ---
    autostart_on = config.get("features", "autostart", default=False)
    tray = TrayIcon(autostart_enabled=autostart_on, parent=window)
    tray.show()

    def show_window() -> None:
        window.show()
        window.raise_()
        window.activateWindow()
        tray.set_window_visible(True)

    def hide_window() -> None:
        window.hide()
        tray.set_window_visible(False)

    def toggle_window() -> None:
        if window.isVisible():
            hide_window()
        else:
            show_window()

    tray.show_hide_requested.connect(toggle_window)

    def quick_question() -> None:
        show_window()
        text, ok = QInputDialog.getText(window, "Quick Question", "Ask the Agent:")
        if ok and text.strip():
            window.input_widget.setText(text.strip())
            window._on_send()

    tray.quick_question_requested.connect(quick_question)

    def view_logs() -> None:
        log_path = Path(config.get("logging", "file", default="agent.log")).resolve()
        if log_path.exists():
            os.startfile(str(log_path))
        else:
            QMessageBox.information(window, "Logs", f"Log file not found:\n{log_path}")

    tray.view_logs_requested.connect(view_logs)

    def check_updates() -> None:
        ver = config.get("app", "version", default="0.1.0")
        QMessageBox.information(window, "Check for Updates", f"Desktop Agent v{ver}\n\nYou are running the latest version.")

    tray.check_updates_requested.connect(check_updates)
    tray.quit_requested.connect(app.quit)

    def on_autostart_toggle(checked: bool) -> None:
        if checked:
            autostart_enable()
        else:
            autostart_disable()
        config.set("features", "autostart", value=checked)
        logger.info(f"Autostart {'enabled' if checked else 'disabled'}")

    tray.autostart_toggled.connect(on_autostart_toggle)

    def on_api_started() -> None:
        tray.set_status("working")

    def on_api_finished(reply: str) -> None:
        tray.set_status("idle")
        if pet:
            pet.set_state(DesktopPet.IDLE)
        preview = reply[:120] + "..." if len(reply) > 120 else reply
# Notifications disabled

    def on_api_error(error_msg: str) -> None:
        tray.set_status("error")
        if pet:
            pet.set_state(DesktopPet.IDLE)
# Error notifications disabled
        def _reset_error_state():
            tray.set_status("idle")
            if pet:
                pet.set_state(DesktopPet.IDLE)
        QTimer.singleShot(5000, _reset_error_state)

    window.api_call_started.connect(on_api_started)

    def on_thinking() -> None:
        if pet:
            pet.set_state(DesktopPet.THINKING)

    window.thinking_started.connect(on_thinking)

    def on_streaming_started() -> None:
        if pet:
            pet.set_state(DesktopPet.RESPONDING)

    window.streaming_started.connect(on_streaming_started)

    window.api_call_finished.connect(on_api_finished)
    window.api_call_error.connect(on_api_error)

    # --- Window: voice input ---
    def on_voice_input() -> None:
        window._mic_btn.setChecked(True)
        def on_result(text: str) -> None:
            window._mic_btn.setChecked(False)
            window.input_widget.setText(text)
            window._on_send()
        def on_err(msg: str) -> None:
            window._mic_btn.setChecked(False)
    # Voice error notifications disabled
        stt.listen(on_result, on_err)

    window.voice_input_requested.connect(on_voice_input)

    # --- Window: TTS toggle ---
    def on_tts_toggle(checked: bool) -> None:
        tts.enabled = checked
        config.set("features", "tts_enabled", value=checked)

    window.tts_toggled.connect(on_tts_toggle)

    # Speak agent replies
    def on_api_finished_tts(reply: str) -> None:
        if tts.enabled:
            tts.speak_async(reply)

    window.api_call_finished.connect(on_api_finished_tts)

    # --- Window: screenshot ---
    def on_screenshot() -> None:
        screen = app.primaryScreen()
        if screen:
            pix = screen.grabWindow(0)
            import tempfile, os
            fd, tmp = tempfile.mkstemp(suffix=".png")
            os.close(fd)
            pix.save(tmp, "PNG")
            show_window()
            import base64
            with open(tmp, "rb") as fb:
                b64 = base64.b64encode(fb.read()).decode("ascii")
            try: os.unlink(tmp)
            except: pass
            window.add_screenshot(b64)
            window.input_widget.setFocus()

    window.screenshot_requested.connect(on_screenshot)

    # --- Window: file attach ---
    def on_file_attach(filepath: str) -> None:
        name = __import__("pathlib").Path(filepath).name
        show_window()
        window.input_widget.setText(f"[File: {name}] ")
        window.input_widget.setFocus()
        # TODO: send file content to API when supported

    window.file_attached.connect(on_file_attach)

    # --- Window: font size changed ---
    def on_font_size_changed(size: int) -> None:
        config.set("ui", "font_size", value=size)

    window.font_size_changed.connect(on_font_size_changed)

    def open_settings() -> None:
        dlg = SettingsDialog(config, parent=window)
        dlg.settings_applied.connect(lambda: _apply_all_settings(config, window, pet))
        dlg.exec()

    tray.settings_requested.connect(open_settings)

    # --- Floating button ---
    pet = None
    if config.get("ui", "floating", "enabled", default=True):
        float_size = config.get("ui", "floating", "size", default=56)
        float_opacity = config.get("ui", "floating", "opacity", default=0.85)
        float_pos = config.get("ui", "floating", "position", default="top-right")
        pet = DesktopPet(
            size=float_size,
            opacity=float_opacity,
            position=float_pos,
        )
        window.set_popup_mode(True)

        def toggle_chat_popup() -> None:
            pet.wake_up()
            if window.isVisible():
                window.hide()
            else:
                pet.set_state(DesktopPet.EXCITED)
                window.show_near(pet.x() + pet.width() // 2, pet.y())
                QTimer.singleShot(2000, lambda: pet.set_state(DesktopPet.IDLE))

        pet.left_clicked.connect(toggle_chat_popup)
        pet.settings_requested.connect(open_settings)
        pet.quit_requested.connect(app.quit)
        pet.show()

    # --- Hotkeys ---
    hk = HotkeyManager()

    def register_all_hotkeys() -> None:
        hk.unregister_all()
        callbacks = {
            "toggle_window": toggle_window,
            "quick_input": quick_dlg.popup,
            "voice_input": lambda: logger.info("Voice input not yet implemented"),
        }
        for action in ("toggle_window", "quick_input", "voice_input"):
            hotkey = config.get("features", "hotkeys", action, default="")
            if not hotkey:
                continue
            ok, msg = hk.register(action, hotkey, callbacks.get(action, lambda: None))
            if ok:
                logger.info(f"Hotkey [{action}] -> {hotkey}")
            else:
                logger.warning(f"Hotkey [{action}] failed: {msg}")

    register_all_hotkeys()

    def _apply_all_settings(cfg, win, pt):
        win.apply_theme(cfg.get("ui", "theme", default="dark"))
        win.set_window_opacity(cfg.get("ui", "window", "opacity", default=1.0))
        win.set_font_size(cfg.get("ui", "font_size", default=13))
        if pt:
            pt.set_opacity(cfg.get("ui", "floating", "opacity", default=0.85))
            pt.set_position(cfg.get("ui", "floating", "position", default="top-right"))
            pt.set_size(cfg.get("ui", "floating", "size", default=80))
        register_all_hotkeys()

    def on_config_changed() -> None:
        logger.info("Config file changed, applying...")
        _apply_all_settings(config, window, pet)

    config.config_changed.connect(on_config_changed)

    # History auto-cleanup
    retention = config.get("features", "history_retention_days", default=15)
    removed = conv_mgr.cleanup_old(max_age_days=retention)
    if removed:
        logger.info(f"Cleaned up {removed} old conversation(s)")

    window.show()
    tray.set_window_visible(True)
    logger.info("Desktop Agent ready.")
    # Daily reset at startup
    scheduler.reset_daily()
    logger.info("Autonomous agent systems active: memory + monitor + scheduler + web tools.")
    app.aboutToQuit.connect(hk.unregister_all)
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
