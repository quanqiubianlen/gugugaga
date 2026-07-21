"""Floating desktop overlay with icon, badge, drag, opacity, and context menu."""

from pathlib import Path

from PyQt6.QtCore import QPoint, QRect, Qt, pyqtSignal
from PyQt6.QtGui import (
    QBrush,
    QColor,
    QFont,
    QLinearGradient,
    QMouseEvent,
    QPainter,
    QPen,
    QPixmap,
)
from PyQt6.QtWidgets import QApplication, QMenu, QWidget


# ---------------------------------------------------------------------------
# Colour palette
# ---------------------------------------------------------------------------
BG_GRADIENT_TOP = QColor("#5B8DEF")
BG_GRADIENT_BOT = QColor("#3A6FD8")
BG_HOVER_TOP = QColor("#7BA8FF")
BG_HOVER_BOT = QColor("#5B8DEF")
BORDER_COLOR = QColor(255, 255, 255, 60)
BADGE_BG = QColor("#E74C3C")
BADGE_TEXT = QColor("#FFFFFF")
ICON_COLOR = QColor(255, 255, 255, 230)


class FloatingButton(QWidget):
    """A frameless, always-on-top, semi-transparent overlay.

    Signals
    -------
    left_clicked :
        Emitted on a clean left-click (no drag registered).
    settings_requested :
        Emitted when the user picks "Settings" from the right-click menu.
    quit_requested :
        Emitted when the user picks "Quit" from the right-click menu.
    """

    left_clicked = pyqtSignal()
    settings_requested = pyqtSignal()
    quit_requested = pyqtSignal()

    def __init__(
        self,
        size: int = 56,
        opacity: float = 0.85,
        position: str = "top-right",
        icon_path: Path | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._size = size
        self._opacity = opacity
        self._position = position
        self._icon_path = icon_path
        self._cached_icon: QPixmap | None = None

        # Drag state
        self._drag_pos: QPoint | None = None
        self._dragging = False
        self._press_pos: QPoint | None = None

        # Hover state
        self._hovered = False
        self.setMouseTracking(True)

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

        self._apply_position(position)

        self._load_icon()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def set_opacity(self, value: float) -> None:
        """Set window opacity (0.0 -- 1.0)."""
        self._opacity = max(0.1, min(1.0, value))
        self.setWindowOpacity(self._opacity)

    def opacity(self) -> float:
        return self._opacity

    def set_badge_count(self, count: int) -> None:
        """Show or hide the unread badge.  0 hides it."""
        self._badge_count = max(0, count)
        self.update()

    def set_icon(self, path: Path) -> None:
        """Load a custom icon from a file path."""
        self._icon_path = path
        self._cached_icon = None
        self._load_icon()
        self.update()

    # ------------------------------------------------------------------
    # Paint
    # ------------------------------------------------------------------

    def paintEvent(self, event) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)

        center = self.rect().center()
        radius = self._size / 2 - 2

        # --- background circle with gradient ---
        grad = QLinearGradient(0, 0, 0, self._size)
        if self._hovered:
            grad.setColorAt(0.0, BG_HOVER_TOP)
            grad.setColorAt(1.0, BG_HOVER_BOT)
        else:
            grad.setColorAt(0.0, BG_GRADIENT_TOP)
            grad.setColorAt(1.0, BG_GRADIENT_BOT)

        p.setBrush(QBrush(grad))
        p.setPen(QPen(BORDER_COLOR, 2))
        p.drawEllipse(center, int(radius), int(radius))

        # --- icon ---
        if self._cached_icon and not self._cached_icon.isNull():
            icon_size = int(self._size * 0.48)
            src = self._cached_icon.scaled(
                icon_size, icon_size,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
            x = (self._size - src.width()) // 2
            y = (self._size - src.height()) // 2
            p.drawPixmap(x, y, src)
        else:
            self._draw_default_icon(p, center, radius)

        # --- badge ---
        if self._badge_count > 0:
            self._draw_badge(p)

        p.end()

    def _draw_default_icon(self, p: QPainter, center: QPoint, radius: float) -> None:
        """Draw a simple sparkle / AI glyph when no custom icon is loaded."""
        s = radius * 0.65
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QBrush(ICON_COLOR))

        from PyQt6.QtGui import QPainterPath
        pp = QPainterPath()
        # Reconstruct path step by step
        pp.moveTo(center.x(), center.y() - s)
        pp.lineTo(center.x() + s * 0.35, center.y() - s * 0.3)
        pp.lineTo(center.x() + s, center.y())
        pp.lineTo(center.x() + s * 0.35, center.y() + s * 0.3)
        pp.lineTo(center.x(), center.y() + s)
        pp.lineTo(center.x() - s * 0.35, center.y() + s * 0.3)
        pp.lineTo(center.x() - s, center.y())
        pp.lineTo(center.x() - s * 0.35, center.y() - s * 0.3)
        pp.closeSubpath()
        p.drawPath(pp)

    def _draw_badge(self, p: QPainter) -> None:
        """Red circle with white count number, positioned at top-right."""
        badge_r = 10
        margin = 2
        cx = self._size - badge_r - margin
        cy = badge_r + margin

        p.setBrush(QBrush(BADGE_BG))
        p.setPen(QPen(Qt.GlobalColor.white, 1))
        p.drawEllipse(QPoint(cx, cy), badge_r, badge_r)

        p.setFont(QFont("Segoe UI", 8, QFont.Weight.Bold))
        p.setPen(QPen(BADGE_TEXT))
        text = str(self._badge_count) if self._badge_count < 100 else "99+"
        p.drawText(QRect(cx - badge_r, cy - badge_r, badge_r * 2, badge_r * 2),
                   Qt.AlignmentFlag.AlignCenter, text)

    # ------------------------------------------------------------------
    # Mouse events
    # ------------------------------------------------------------------

    def mousePressEvent(self, event: QMouseEvent | None) -> None:
        if event is None:
            return
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
            if delta.manhattanLength() > 4:
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

    def contextMenuEvent(self, event) -> None:
        menu = QMenu(self)
        menu.setStyleSheet("""
            QMenu {
                background: #2b2b2b;
                color: #eee;
                border: 1px solid #555;
                padding: 4px;
            }
            QMenu::item {
                padding: 6px 28px 6px 12px;
            }
            QMenu::item:selected {
                background: #4A90D9;
                border-radius: 4px;
            }
            QMenu::separator {
                height: 1px;
                background: #555;
                margin: 4px 8px;
            }
        """)

        settings_action = menu.addAction("Settings")
        menu.addSeparator()
        quit_action = menu.addAction("Quit")

        action = menu.exec(event.globalPos())
        if action == settings_action:
            self.settings_requested.emit()
        elif action == quit_action:
            self.quit_requested.emit()

    def enterEvent(self, event) -> None:
        self._hovered = True
        self.update()
        super().enterEvent(event)

    def leaveEvent(self, event) -> None:
        self._hovered = False
        self.update()
        super().leaveEvent(event)

    # ------------------------------------------------------------------
    # Private
    # ------------------------------------------------------------------

    def set_position(self, position: str) -> None:
        """Move the floating icon to a preset or custom position."""
        self._position = position
        self._apply_position(position)

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
        x, y = positions.get(position, positions["top-right"])
        self.move(x, y)

    def _load_icon(self) -> None:
        if self._icon_path and self._icon_path.exists():
            self._cached_icon = QPixmap(str(self._icon_path))
        else:
            self._cached_icon = None
