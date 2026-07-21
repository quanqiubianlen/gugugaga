"""Desktop Pet -- a cute animated character that lives on your desktop.

Click to chat, drag to move, idle animations with personality.
"""

import math
import random
from pathlib import Path

from PyQt6.QtCore import QPoint, QRect, Qt, QTimer, pyqtSignal
from PyQt6.QtGui import (
    QBrush,
    QColor,
    QFont,
    QMouseEvent,
    QPainter,
    QPen,
    QPixmap,
)
from PyQt6.QtWidgets import QApplication, QMenu, QWidget


# ---------------------------------------------------------------------------
# Colour palette
# ---------------------------------------------------------------------------
BODY_TOP = QColor("#6C9FFF")
BODY_BOT = QColor("#4A7FE0")
BODY_HOVER_TOP = QColor("#8CB8FF")
BODY_HOVER_BOT = QColor("#6C9FFF")
EYE_WHITE = QColor("#FFFFFF")
EYE_PUPIL = QColor("#1A1A2E")
MOUTH_COLOR = QColor("#3A5FB0")
CHEEK_COLOR = QColor(255, 150, 150, 80)
BORDER_COLOR = QColor(255, 255, 255, 50)
BADGE_BG = QColor("#E74C3C")
BADGE_TEXT = QColor("#FFFFFF")
SHADOW_COLOR = QColor(0, 0, 0, 40)


# ---------------------------------------------------------------------------
# Pet image assets
# ---------------------------------------------------------------------------
_ASSETS_DIR = Path(__file__).resolve().parent.parent / "assets" / "pet"

def _load_pixmap(filename: str) -> QPixmap:
    path = _ASSETS_DIR / filename
    if path.exists():
        return QPixmap(str(path))
    return QPixmap()


class DesktopPet(QWidget):
    """A frameless, always-on-top animated desktop companion.

    Signals
    -------
    left_clicked :
        Clean left-click (no drag).  Use to open the chat popup.
    settings_requested :
        "Settings" picked from the right-click menu.
    quit_requested :
        "Quit" picked from the right-click menu.
    """

    left_clicked = pyqtSignal()
    settings_requested = pyqtSignal()
    quit_requested = pyqtSignal()

    # Animation phases
    IDLE = "idle"
    SLEEPING = "sleeping"
    EXCITED = "excited"
    RESPONDING = "responding"
    THINKING = "thinking"

    def __init__(
        self,
        size: int = 80,
        opacity: float = 0.92,
        position: str = "bottom-right",
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._size = size
        self._opacity = opacity
        self._position = position

        # Animation state
        self._state = self.IDLE
        self._breath_phase = 0.0
        self._eye_open = 1.0       # 1.0 = open, 0.0 = closed (blink)
        self._blink_timer_val = 0
        self._bob_offset = 0.0
        self._idle_move_timer = 0

        # Drag state
        self._drag_pos: QPoint | None = None
        self._dragging = False
        self._press_pos: QPoint | None = None

        # Hover
        self._hovered = False
        self.setMouseTracking(True)

        # Pet images
        self._img_idle = _load_pixmap("眨眼.png")
        self._img_thinking = _load_pixmap("思考.png")
        self._img_responding = _load_pixmap("回答.png")
        self._img_sleeping = _load_pixmap("睡觉.png")

        # Badge
        self._badge_count = 0

        # Window setup
        self.setFixedSize(size, size)
        self.setWindowFlags(
            Qt.WindowType.Tool
            | Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setWindowOpacity(self._opacity)

        # Initial position
        self._apply_position(position)

        # --- Animation timers ---
        # Breathing (60 fps smooth)
        self._breath_timer = QTimer(self)
        self._breath_timer.timeout.connect(self._tick_breath)
        self._breath_timer.start(16)  # ~60 fps

        # Blinking (random intervals)
        self._blink_timer = QTimer(self)
        self._blink_timer.timeout.connect(self._tick_blink)
        self._schedule_next_blink()

        # Idle wandering (every few seconds)
        self._wander_timer = QTimer(self)
        self._wander_timer.timeout.connect(self._tick_wander)
        self._wander_timer.start(3000)

        # Sleeping timer (enter sleep after 2 min idle)
        self._sleep_timer = QTimer(self)
        self._sleep_timer.setSingleShot(True)
        self._sleep_timer.timeout.connect(self._go_to_sleep)
        self._sleep_timer.start(120_000)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def set_state(self, state: str) -> None:
        """Switch animation state: 'idle', 'sleeping', 'excited', 'responding'."""
        self._state = state
        if state == self.SLEEPING:
            self._breath_timer.start(50)  # slower breathing
        else:
            self._breath_timer.start(16)
            self._sleep_timer.start(120_000)

    def set_badge_count(self, count: int) -> None:
        self._badge_count = max(0, count)
        self.update()

    def set_opacity(self, value: float) -> None:
        self._opacity = max(0.1, min(1.0, value))
        self.setWindowOpacity(self._opacity)

    def set_position(self, position: str) -> None:
        self._position = position
        self._apply_position(position)

    def wake_up(self) -> None:
        """Exit sleeping state."""
        if self._state == self.SLEEPING:
            self.set_state(self.IDLE)

    # ------------------------------------------------------------------
    # Paint
    # ------------------------------------------------------------------

    def paintEvent(self, event) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)

        s = self._size

        # Bob offset (gentle vertical sway)
        bob_y = int(self._bob_offset)

        # --- Select image by state ---
        state_images = {
            self.IDLE: self._img_idle,
            self.EXCITED: self._img_idle,
            self.THINKING: self._img_thinking,
            self.RESPONDING: self._img_responding,
            self.SLEEPING: self._img_sleeping,
        }
        pixmap = state_images.get(self._state, self._img_idle)

        if pixmap and not pixmap.isNull():
            # Draw image with bob offset and slight breathing scale
            breath_scale = 1.0 + math.sin(self._breath_phase) * 0.02
            draw_size = int(s * breath_scale)
            offset = (s - draw_size) // 2
            target = QRect(offset, offset + bob_y, draw_size, draw_size)
            p.drawPixmap(target, pixmap)

            # Hover highlight overlay
            if self._hovered:
                p.setPen(Qt.PenStyle.NoPen)
                p.setBrush(QBrush(QColor(255, 255, 255, 40)))
                p.drawRect(self.rect())

        # --- Badge ---
        if self._badge_count > 0:
            badge_r = 12
            bx = self._size - badge_r - 2
            by = badge_r + 2
            p.setBrush(QBrush(BADGE_BG))
            p.setPen(QPen(Qt.GlobalColor.white, 1.5))
            p.drawEllipse(QPoint(bx, by), badge_r, badge_r)
            p.setFont(QFont("Segoe UI", 8, QFont.Weight.Bold))
            p.setPen(QPen(BADGE_TEXT))
            text = str(self._badge_count) if self._badge_count < 100 else "99+"
            p.drawText(QRect(bx - badge_r, by - badge_r, badge_r * 2, badge_r * 2),
                       Qt.AlignmentFlag.AlignCenter, text)

        # --- Zzz for sleeping ---
        if self._state == self.SLEEPING:
            p.setFont(QFont("Segoe UI", 9, QFont.Weight.Bold))
            p.setPen(QPen(QColor(180, 200, 255, 180)))
            zx = int(s * 0.75)
            zy = int(s * 0.2)
            p.drawText(zx, zy, "zZz")

        p.end()

    # ------------------------------------------------------------------
    # Animation ticks
    # ------------------------------------------------------------------

    def _tick_breath(self) -> None:
        if self._state == self.SLEEPING:
            speed = 0.02
        elif self._state == self.EXCITED:
            speed = 0.08
        else:
            speed = 0.04

        self._breath_phase += speed
        self._bob_offset = math.sin(self._breath_phase * 2) * 2.0
        self.update()

    def _tick_blink(self) -> None:
        self._blink_timer_val += 1
        if self._blink_timer_val <= 3:
            self._eye_open = max(0.0, 1.0 - self._blink_timer_val * 0.35)
        elif self._blink_timer_val <= 6:
            self._eye_open = min(1.0, (self._blink_timer_val - 3) * 0.35)
        else:
            self._eye_open = 1.0
            self._blink_timer.stop()
            self._schedule_next_blink()
        self.update()

    def _schedule_next_blink(self) -> None:
        self._blink_timer_val = 0
        # Random interval: 2-6 seconds
        interval = random.randint(2000, 6000)
        self._blink_timer.start(50)

    def _tick_wander(self) -> None:
        if self._state != self.IDLE:
            return
        # Gentle random drift
        dx = random.randint(-15, 15)
        dy = random.randint(-8, 8)
        nx = self.x() + dx
        ny = self.y() + dy

        screen = QApplication.primaryScreen()
        if screen:
            geo = screen.availableGeometry()
            nx = max(geo.left(), min(geo.right() - self._size, nx))
            ny = max(geo.top(), min(geo.bottom() - self._size, ny))

        self.move(nx, ny)

    def _go_to_sleep(self) -> None:
        if self._state == self.IDLE:
            self.set_state(self.SLEEPING)

    # ------------------------------------------------------------------
    # Mouse events
    # ------------------------------------------------------------------

    def mousePressEvent(self, event: QMouseEvent | None) -> None:
        if event is None:
            return
        self.wake_up()
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag_pos = event.globalPosition().toPoint() - self.frameGeometry().topLeft()
            self._press_pos = event.globalPosition().toPoint()
            self._dragging = False
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event: QMouseEvent | None) -> None:
        if event is None:
            return
        if self._drag_pos is not None:
            delta = event.globalPosition().toPoint() - self._press_pos
            if delta.manhattanLength() > 5:
                self._dragging = True
            self.move(event.globalPosition().toPoint() - self._drag_pos)
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event: QMouseEvent | None) -> None:
        if event and event.button() == Qt.MouseButton.LeftButton and not self._dragging:
            self.left_clicked.emit()
        self._drag_pos = None
        self._press_pos = None
        self._dragging = False
        super().mouseReleaseEvent(event)

    def enterEvent(self, event) -> None:
        self._hovered = True
        self.wake_up()
        self.update()
        super().enterEvent(event)

    def leaveEvent(self, event) -> None:
        self._hovered = False
        self.update()
        super().leaveEvent(event)

    def contextMenuEvent(self, event) -> None:
        menu = QMenu(self)
        menu.setStyleSheet("""
            QMenu { background: #2b2b2b; color: #eee; border: 1px solid #555; padding: 4px; }
            QMenu::item { padding: 6px 28px 6px 12px; }
            QMenu::item:selected { background: #4A90D9; border-radius: 4px; }
            QMenu::separator { height: 1px; background: #555; margin: 4px 8px; }
        """)
        settings_action = menu.addAction("Settings")
        menu.addSeparator()
        quit_action = menu.addAction("Quit")

        action = menu.exec(event.globalPos())
        if action == settings_action:
            self.settings_requested.emit()
        elif action == quit_action:
            self.quit_requested.emit()

    # ------------------------------------------------------------------
    # Position helper
    # ------------------------------------------------------------------

    def _apply_position(self, position: str) -> None:
        screen = QApplication.primaryScreen()
        if not screen:
            return
        geo = screen.availableGeometry()
        size = self._size
        pad_x, pad_y = 20, 40

        parts = position.split(",")
        if len(parts) == 2:
            try:
                self.move(int(parts[0].strip()), int(parts[1].strip()))
                return
            except ValueError:
                pass

        positions = {
            "top-right":     (geo.right() - size - pad_x, geo.top() + pad_y),
            "top-left":      (geo.left() + pad_x, geo.top() + pad_y),
            "bottom-right":  (geo.right() - size - pad_x, geo.bottom() - size - pad_y),
            "bottom-left":   (geo.left() + pad_x, geo.bottom() - size - pad_y),
        }
        x, y = positions.get(position, positions["bottom-right"])
        self.move(x, y)
