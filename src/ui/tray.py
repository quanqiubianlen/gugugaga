"""System tray icon with status indicators, expanded menu, and notifications."""

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QAction, QColor, QIcon, QPainter, QPixmap
from PyQt6.QtWidgets import QMenu, QSystemTrayIcon, QWidget


# ---------------------------------------------------------------------------
# Status-colour mapping (used for icon generation and tooltip prefix)
# ---------------------------------------------------------------------------
_STATUS_COLORS = {
    "idle":    QColor("#6C8EBF"),   # muted blue
    "working": QColor("#F0A030"),   # amber / orange
    "error":   QColor("#E74C3C"),   # red
}

_ICON_SIZE = 64


def _make_status_icon(status: str) -> QIcon:
    """Generate a solid-colour circle icon for the given status."""
    color = _STATUS_COLORS.get(status, _STATUS_COLORS["idle"])
    pix = QPixmap(_ICON_SIZE, _ICON_SIZE)
    pix.fill(Qt.GlobalColor.transparent)
    p = QPainter(pix)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    margin = 4
    p.setBrush(color)
    p.setPen(Qt.PenStyle.NoPen)
    p.drawEllipse(margin, margin, _ICON_SIZE - margin * 2, _ICON_SIZE - margin * 2)
    p.end()
    return QIcon(pix)


# ---------------------------------------------------------------------------
# TrayIcon
# ---------------------------------------------------------------------------

class TrayIcon(QSystemTrayIcon):
    """System tray icon with status-dependent appearance and rich menu.

    Signals
    -------
    show_hide_requested :
        Emitted when the user clicks Show/Hide in the menu.
    quick_question_requested :
        Emitted when the user clicks "Quick Question".
    settings_requested :
        Emitted when the user clicks "Settings".
    view_logs_requested :
        Emitted when the user clicks "View Logs".
    check_updates_requested :
        Emitted when the user clicks "Check for Updates".
    quit_requested :
        Emitted when the user clicks "Quit".
    autostart_toggled(bool) :
        Emitted when the "Start with Windows" checkbox changes.
    """

    show_hide_requested = pyqtSignal()
    quick_question_requested = pyqtSignal()
    settings_requested = pyqtSignal()
    view_logs_requested = pyqtSignal()
    check_updates_requested = pyqtSignal()
    quit_requested = pyqtSignal()
    autostart_toggled = pyqtSignal(bool)

    def __init__(
        self,
        autostart_enabled: bool = False,
        parent: QWidget | None = None,
    ) -> None:
        # Start with idle icon
        super().__init__(_make_status_icon("idle"), parent)
        self._status = "idle"
        self._window_visible = True
        self.setToolTip("Desktop Agent  - Idle")
        self._build_menu(autostart_enabled)
        self.activated.connect(self._on_activated)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def set_status(self, status: str) -> None:
        """Update the tray icon colour: 'idle', 'working', or 'error'."""
        if status not in _STATUS_COLORS:
            status = "idle"
        self._status = status
        self.setIcon(_make_status_icon(status))
        label = status.capitalize()
        self.setToolTip(f"Desktop Agent  - {label}")

    def set_window_visible(self, visible: bool) -> None:
        """Keep the Show / Hide action text in sync with actual visibility."""
        self._window_visible = visible
        self._show_hide_action.setText("Hide Window" if visible else "Show Window")

    def show_notification(self, title: str, message: str, duration_ms: int = 5000) -> None:
        """Pop a balloon notification near the system tray."""
        self.showMessage(title, message, QSystemTrayIcon.MessageIcon.Information, duration_ms)

    def show_error_notification(self, title: str, message: str) -> None:
        self.showMessage(title, message, QSystemTrayIcon.MessageIcon.Critical, 8000)

    # ------------------------------------------------------------------
    # Menu
    # ------------------------------------------------------------------

    def _build_menu(self, autostart_enabled: bool) -> None:
        menu = QMenu()

        self._show_hide_action = QAction("Hide Window")
        self._show_hide_action.triggered.connect(self._on_show_hide)
        menu.addAction(self._show_hide_action)

        menu.addSeparator()

        quick_action = QAction("Quick Question")
        quick_action.triggered.connect(self.quick_question_requested.emit)
        menu.addAction(quick_action)

        menu.addSeparator()

        settings_action = QAction("Settings")
        settings_action.triggered.connect(self.settings_requested.emit)
        menu.addAction(settings_action)

        logs_action = QAction("View Logs")
        logs_action.triggered.connect(self.view_logs_requested.emit)
        menu.addAction(logs_action)

        updates_action = QAction("Check for Updates")
        updates_action.triggered.connect(self.check_updates_requested.emit)
        menu.addAction(updates_action)

        menu.addSeparator()

        self._autostart_action = QAction("Start with Windows")
        self._autostart_action.setCheckable(True)
        self._autostart_action.setChecked(autostart_enabled)
        self._autostart_action.triggered.connect(self._on_autostart_toggled)
        menu.addAction(self._autostart_action)

        menu.addSeparator()

        quit_action = QAction("Quit")
        quit_action.triggered.connect(self.quit_requested.emit)
        menu.addAction(quit_action)

        self.setContextMenu(menu)

    def set_autostart_checked(self, enabled: bool) -> None:
        self._autostart_action.setChecked(enabled)

    # ------------------------------------------------------------------
    # Slots
    # ------------------------------------------------------------------

    def _on_show_hide(self) -> None:
        self.show_hide_requested.emit()

    def _on_autostart_toggled(self, checked: bool) -> None:
        self.autostart_toggled.emit(checked)

    def _on_activated(self, reason: QSystemTrayIcon.ActivationReason) -> None:
        if reason in (
            QSystemTrayIcon.ActivationReason.DoubleClick,
            QSystemTrayIcon.ActivationReason.Trigger,
        ):
            self.show_hide_requested.emit()
