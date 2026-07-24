"""Chat window with message bubbles, Markdown, code highlighting, suggestions, error handling, and conversation sidebar."""

from datetime import datetime
from pathlib import Path

from PyQt6.QtCore import (
    QEasingCurve, QElapsedTimer, QPropertyAnimation, Qt, QThread, QTimer, pyqtSignal,
)
from PyQt6.QtGui import QAction, QCloseEvent, QFont, QFontMetrics, QKeyEvent, QPainter, QPainterPath, QPixmap, QResizeEvent
from src.agent.api_client import VisionClient
from src.utils.tools import TOOLS
from PyQt6.QtWidgets import (
    QFileDialog,
    QGraphicsOpacityEffect,
    QMenu,
    QApplication,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QSplitter,
    QToolBar,
    QVBoxLayout,
    QWidget,
)

# ---------------------------------------------------------------------------
# Code-highlighting CSS
# ---------------------------------------------------------------------------
_CODE_CSS = ""

def _build_code_css() -> str:
    global _CODE_CSS
    if _CODE_CSS:
        return _CODE_CSS
    try:
        from pygments.formatters import HtmlFormatter
        _CODE_CSS = HtmlFormatter(style="monokai").get_style_defs(".codehilite")
        _CODE_CSS = _CODE_CSS.replace(".codehilite", ".bubble-content .codehilite")
        _CODE_CSS += """
            .bubble-content .codehilite {
                background: rgba(0, 0, 0, 0.25) !important;
                border-radius: 8px;
                padding: 10px 14px;
            }
        """
    except Exception:
        _CODE_CSS = ""
    return _CODE_CSS


# ---------------------------------------------------------------------------
# Markdown -> HTML
# ---------------------------------------------------------------------------

def _m2t(content):
    if isinstance(content, str): return content
    if isinstance(content, list):
        p=[]
        for x in content:
            if isinstance(x,dict) and x.get('type')=='text': p.append(x.get('text',''))
            elif isinstance(x,dict) and x.get('type')=='image_url': p.append('[Image]')
        return ' '.join(p) or '[Attachment]'
    return str(content)

def _render_markdown(text: str) -> str:
    text = _m2t(text)
    if not text:
        return ""
    css = _build_code_css()
    try:
        import markdown
        html = markdown.markdown(
            text,
            extensions=["fenced_code", "codehilite", "tables", "nl2br"],
            extension_configs={"codehilite": {"css_class": "codehilite", "guess_lang": False}},
        )
    except Exception:
        html = text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
        css = ""
    style_block = f"<style>{css}</style>" if css else ""
    return f"<div class='bubble-content'>{style_block}{html}</div>"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _relative_time(dt: datetime) -> str:
    now = datetime.now()
    delta = now - dt
    seconds = int(delta.total_seconds())
    if seconds < 10:   return "just now"
    if seconds < 60:   return f"{seconds}s ago"
    minutes = seconds // 60
    if minutes < 60:   return f"{minutes}m ago"
    hours = minutes // 60
    if hours < 24:     return f"{hours}h ago"
    days = hours // 24
    if days < 7:       return f"{days}d ago"
    return dt.strftime("%Y-%m-%d %H:%M")


# ---------------------------------------------------------------------------
# Message bubble
# ---------------------------------------------------------------------------

class MessageBubble(QFrame):
    """A single chat message with bubble styling, timestamp, and copy."""

    def __init__(self, role: str, content: str, timestamp: datetime | None = None, parent=None) -> None:
        super().__init__(parent)
        self._role = role
        self._content = content
        self._timestamp = timestamp or datetime.now()

        self.setObjectName("messageBubble")
        self.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Minimum)
        self.setContextMenuPolicy(Qt.ContextMenuPolicy.ActionsContextMenu)

        copy_action = QAction("Copy", self)
        copy_action.triggered.connect(self._copy_content)
        self.addAction(copy_action)

        is_user = role == "user"

        # --- Avatar with circular background ---
        avatar_bg = "#4a3068" if is_user else "#1a3c5e"
        self._avatar = QLabel()
        self._avatar.setFixedSize(32, 32)
        self._avatar.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._avatar.setStyleSheet(
            f"background: {avatar_bg}; border-radius: 16px;"
        )
        pet_dir = Path(__file__).resolve().parent.parent / "assets" / "pet"
        if role != "user":
            # Load pet image as AI avatar (find by glob to avoid encoding issues)
            candidates = list(pet_dir.glob("*.png"))
            # Pick the main pet image (largest file, usually the main character)
            pet_img = max(candidates, key=lambda p: p.stat().st_size) if candidates else None
            if pet_img and pet_img.exists():
                pix = QPixmap(str(pet_img)).scaled(
                    30, 30, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation
                )
                self._avatar.setPixmap(pix)
            else:
                self._avatar.setText(chr(0x1F427))
        else:
            # Load user avatar from pet folder
            user_img = pet_dir / "本人.jpg"
            if user_img.exists():
                pix = QPixmap(str(user_img)).scaled(
                    30, 30, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation
                )
                circular = QPixmap(30, 30)
                circular.fill(Qt.GlobalColor.transparent)
                p = QPainter(circular)
                p.setRenderHint(QPainter.RenderHint.Antialiasing)
                clip = QPainterPath()
                clip.addEllipse(0, 0, 30, 30)
                p.setClipPath(clip)
                p.drawPixmap(0, 0, pix)
                p.end()
                self._avatar.setPixmap(circular)
            else:
                self._avatar.setText(chr(0x1F464))
                self._avatar.setStyleSheet(
                    f"background: {avatar_bg}; border-radius: 16px; font-size: 17px;"
                )

        # --- Inner bubble frame: richer colours + chat-tail shape ---
        self._bubble_frame = QFrame(self)
        self._bubble_frame.setObjectName("bubble")
        self._bubble_frame.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Minimum)
        bubble_color = "#5b3a78" if is_user else "#142c4a"
        border_color = "#7a55a0" if is_user else "#2a62a0"
        # AI: small bottom-left corner  (16 16 16 4)
        # User: small bottom-right corner (16 16 4 16)
        corners = "16px 16px 4px 16px" if is_user else "16px 16px 16px 4px"
        self._bubble_frame.setStyleSheet(
            f"#bubble {{"
            f"  border-radius: {corners};"
            f"  background: {bubble_color};"
            f"  border: 1px solid {border_color};"
            f"}}"
        )

        bubble_layout = QVBoxLayout(self._bubble_frame)
        bubble_layout.setContentsMargins(15, 10, 15, 10)
        bubble_layout.setSpacing(6)

        self._content_label = QLabel(_render_markdown(content))
        self._content_label.setObjectName("bubbleLabel")
        self._content_label.setWordWrap(True)
        self._content_label.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Preferred)
        # Natural min-width from content (no forced zero)
        self._content_label.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self._content_label.setTextFormat(Qt.TextFormat.RichText)
        self._content_label.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse | Qt.TextInteractionFlag.LinksAccessibleByMouse
        )
        self._content_label.setOpenExternalLinks(True)
        bubble_layout.addWidget(self._content_label)

        self._time_label = QLabel(_relative_time(self._timestamp))
        self._time_label.setObjectName("bubbleTime")
        self._time_label.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Preferred)
        # Natural min-width from content
        self._time_label.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self._time_label.setToolTip(self._timestamp.strftime("%Y-%m-%d %H:%M:%S"))
        bubble_layout.addWidget(self._time_label, alignment=Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignBottom)

        # --- Outer layout: avatar + bubble, flush to screen edge ---
        outer = QHBoxLayout(self)
        outer.setContentsMargins(0, 4, 0, 4)
        outer.setSpacing(6)

        if is_user:
            # User: bubble then avatar, no stretch (alignment from parent)
            outer.addWidget(self._bubble_frame)
            outer.addWidget(self._avatar)
        else:
            # AI: avatar then bubble, no stretch (alignment from parent)
            outer.addWidget(self._avatar)
            outer.addWidget(self._bubble_frame)

        # --- Fade-in animation (applied to bubble frame only, not parent) ---
        self._fade_effect = QGraphicsOpacityEffect(self._bubble_frame)
        self._fade_effect.setOpacity(0.0)
        self._bubble_frame.setGraphicsEffect(self._fade_effect)
        self._fade_anim = QPropertyAnimation(self._fade_effect, b"opacity", self)
        self._fade_anim.setDuration(280)
        self._fade_anim.setStartValue(0.0)
        self._fade_anim.setEndValue(1.0)
        self._fade_anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        self._fade_anim.finished.connect(self._on_fade_done)

    def _copy_content(self) -> None:
        QApplication.clipboard().setText(self._content)

    @staticmethod
    def bubble_stylesheet() -> str:
        """Shared stylesheet (role-specific colours are set inline per bubble)."""
        return """
            #bubbleLabel {
                font-size: 13px; line-height: 1.55; color: #e2e2f0; background: transparent;
            }
            #bubbleTime { font-size: 10px; color: #889; margin-top: 2px; }
        """

    def set_bubble_max_width(self, max_width: int) -> None:
        """Cap max width (used by streaming); for final sizing use fit_bubble_to_content."""
        if self._bubble_frame:
            self._bubble_frame.setMaximumWidth(max_width)

    def fit_bubble_to_content(self, max_width: int) -> None:
        """Measure plain-text width and lock bubble to min(ideal, max_width)."""
        if not self._bubble_frame:
            return
        fm = QFontMetrics(self._content_label.font())
        lines = (self._content or "").split(chr(10))
        widest = max((fm.horizontalAdvance(line) for line in lines), default=0)
        ideal_w = int(widest) + 50
        final_w = max(60, min(ideal_w, max_width))
        self._bubble_frame.setFixedWidth(final_w)


    def start_fade_in(self) -> None:
        """Trigger the entrance fade-in animation."""
        if hasattr(self, "_fade_anim") and self._fade_anim:
            self._fade_anim.start()

    def _on_fade_done(self) -> None:
        """Remove the graphics effect after fade-in so layout shifts render in real-time."""
        if self._bubble_frame:
            self._bubble_frame.setGraphicsEffect(None)


# ---------------------------------------------------------------------------
# Error bubble  (extends MessageBubble with retry)
# ---------------------------------------------------------------------------

class ErrorBubble(MessageBubble):
    """Error message bubble with a Retry button."""

    retry_requested = pyqtSignal()

    def __init__(self, error_msg: str, category: str = "unknown") -> None:
        icons = {"network": "[NET]", "timeout": "[TIM]", "auth": "[AUTH]"}
        icon = icons.get(category, "[!]")
        super().__init__("agent", f"**{icon}  {error_msg}**")

        # Add retry button directly to the bubble frame
        retry_btn = QPushButton("Retry")
        retry_btn.setStyleSheet("""
            QPushButton {
                background: #E74C3C; color: white; border: none;
                border-radius: 4px; padding: 4px 16px; font-size: 11px;
            }
            QPushButton:hover { background: #C0392B; }
        """)
        retry_btn.clicked.connect(self.retry_requested.emit)
        self._bubble_frame.layout().addWidget(retry_btn)


# ---------------------------------------------------------------------------
# Suggestion chips
# ---------------------------------------------------------------------------

class SuggestionChips(QWidget):
    """Horizontal row of clickable suggestion buttons."""

    clicked = pyqtSignal(str)

    def __init__(self, suggestions: list[str], parent=None) -> None:
        super().__init__(parent)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(8, 0, 8, 4)
        layout.setSpacing(6)
        layout.addStretch()

        for text in suggestions:
            chip = QPushButton(text)
            chip.setStyleSheet("""
                QPushButton {
                    background: #313244; color: #89b4fa; border: 1px solid #45475a;
                    border-radius: 14px; padding: 4px 14px; font-size: 11px;
                }
                QPushButton:hover { background: #45475a; }
            """)
            chip.clicked.connect(lambda checked, t=text: self.clicked.emit(t))
            layout.addWidget(chip)
        layout.addStretch()


# ---------------------------------------------------------------------------
# Typing indicator
# ---------------------------------------------------------------------------

class TypingIndicator(QWidget):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._dot_count = 0
        self.setFixedHeight(40)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(8, 0, 8, 0)
        layout.addStretch()
        self._label = QLabel("Agent is typing")
        self._label.setStyleSheet("color: #888; font-size: 12px;")
        layout.addWidget(self._label)
        layout.addStretch()
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._tick)
        self._timer.start(500)

    def _tick(self) -> None:
        self._dot_count = (self._dot_count + 1) % 4
        self._label.setText(f"Agent is typing{'.' * self._dot_count}")

    def stop(self) -> None:
        self._timer.stop()


# ---------------------------------------------------------------------------
# API worker
# ---------------------------------------------------------------------------

class ApiWorker(QThread):
    result_ready = pyqtSignal(object)
    error_occurred = pyqtSignal(str, str)  # message, category

    def __init__(self, handler, message: str, context=None, parent=None) -> None:
        super().__init__(parent)
        self.handler = handler
        self.message = message
        self.context = context

    def run(self) -> None:
        try:
            data = self.handler.send(self.message, self.context)
            self.result_ready.emit(data)
        except Exception as exc:
            category = getattr(exc, "category", "unknown")
            self.error_occurred.emit(str(exc), category)


# ---------------------------------------------------------------------------



# ---------------------------------------------------------------------------
# Streaming API worker  (SSE token-by-token)
# ---------------------------------------------------------------------------

class StreamingApiWorker(QThread):
    token_received = pyqtSignal(object)
    stream_finished = pyqtSignal()
    stream_error = pyqtSignal(str, str)

    def __init__(self, handler, message: str, context=None, tools=None, parent=None) -> None:
        super().__init__(parent)
        self.handler = handler
        self.message = message
        self.context = context
        self.tools = tools
        self._cancelled = False

    def cancel(self) -> None:
        self._cancelled = True

    def run(self) -> None:
        try:
            for event in self.handler.send_stream(self.message, self.context, tools=self.tools):
                if self._cancelled:
                    break
                self.token_received.emit(event)
            if not self._cancelled:
                self.stream_finished.emit()
        except Exception as exc:
            category = getattr(exc, 'category', 'unknown')
            self.stream_error.emit(str(exc), category)

# Main chat window
# ---------------------------------------------------------------------------

class MainWindow(QMainWindow):
    """Chat-style Agent window with message bubbles, suggestions, error handling, and conversation management."""

    thinking_started = pyqtSignal()
    streaming_started = pyqtSignal()
    api_call_started = pyqtSignal()
    api_call_finished = pyqtSignal(str)
    api_call_error = pyqtSignal(str)
    voice_input_requested = pyqtSignal()
    tts_toggled = pyqtSignal(bool)
    screenshot_requested = pyqtSignal()
    file_attached = pyqtSignal(str)
    font_size_changed = pyqtSignal(int)

    def __init__(self, conv_manager, vision_client: VisionClient | None = None, title="Desktop Agent", width=900, height=600,
                 theme="dark", window_opacity=1.0) -> None:
        super().__init__()
        self._vision = vision_client
        self._popup_mode = False
        self._show_ts = 0
        self._conv = conv_manager
        self._theme = theme
        self._font_size = 13  # default, updated from config
        self.setWindowTitle(title)
        self.resize(width, height)
        self.setMinimumSize(500, 400)
        self.setWindowOpacity(window_opacity)

        # ---- Toolbar ----
        toolbar = QToolBar("Chat")
        toolbar.setMovable(False)
        toolbar.setStyleSheet("QToolBar { background: #1e1e2e; border-bottom: 1px solid #45475a; padding: 2px 8px; spacing: 6px; }")

        new_btn = QPushButton("New Chat")
        new_btn.setStyleSheet("""
            QPushButton { background: #4A90D9; color: white; border: none; border-radius: 4px; padding: 4px 12px; font-size: 12px; }
            QPushButton:hover { background: #5BA0E9; }
        """)
        new_btn.clicked.connect(self._new_conversation)
        toolbar.addWidget(new_btn)

        clear_btn = QPushButton("Clear")
        clear_btn.setStyleSheet("QPushButton { background: transparent; color: #cdd6f4; border: 1px solid #45475a; border-radius: 4px; padding: 4px 12px; font-size: 12px; } QPushButton:hover { background: #313244; }")
        clear_btn.clicked.connect(self._clear_current)
        toolbar.addWidget(clear_btn)

        export_btn = QPushButton("Export")
        export_btn.setStyleSheet("QPushButton { background: transparent; color: #cdd6f4; border: 1px solid #45475a; border-radius: 4px; padding: 4px 12px; font-size: 12px; } QPushButton:hover { background: #313244; }")
        export_btn.clicked.connect(self._export_current)
        toolbar.addWidget(export_btn)

        toolbar.addSeparator()

        self._pin_btn = QPushButton("Pin")
        self._pin_btn.setCheckable(True)
        self._pin_btn.setStyleSheet("QPushButton { background: transparent; color: #cdd6f4; border: 1px solid #45475a; border-radius: 4px; padding: 4px 12px; font-size: 12px; } QPushButton:checked { background: #4A90D9; color: white; border-color: #4A90D9; } QPushButton:hover:!checked { background: #313244; }")
        self._pin_btn.toggled.connect(self._toggle_pin)
        toolbar.addWidget(self._pin_btn)

        toolbar.addSeparator()

        # Font size
        font_minus = QPushButton("A-")
        font_minus.setStyleSheet("QPushButton { background: transparent; color: #cdd6f4; border: 1px solid #45475a; border-radius: 4px; padding: 2px 8px; font-size: 10px; } QPushButton:hover { background: #313244; }")
        font_minus.clicked.connect(self._font_smaller)
        toolbar.addWidget(font_minus)

        font_plus = QPushButton("A+")
        font_plus.setStyleSheet("QPushButton { background: transparent; color: #cdd6f4; border: 1px solid #45475a; border-radius: 4px; padding: 2px 8px; font-size: 12px; } QPushButton:hover { background: #313244; }")
        font_plus.clicked.connect(self._font_larger)
        toolbar.addWidget(font_plus)

        toolbar.addSeparator()

        # Templates dropdown
        self._templates_btn = QPushButton("Templates")
        self._templates_btn.setStyleSheet("QPushButton { background: transparent; color: #cdd6f4; border: 1px solid #45475a; border-radius: 4px; padding: 2px 10px; font-size: 11px; } QPushButton:hover { background: #313244; }")
        self._templates_btn.clicked.connect(self._show_templates_menu)
        toolbar.addWidget(self._templates_btn)

        # Voice input
        self._mic_btn = QPushButton("Mic")
        self._mic_btn.setStyleSheet("QPushButton { background: transparent; color: #cdd6f4; border: 1px solid #45475a; border-radius: 4px; padding: 2px 10px; font-size: 11px; } QPushButton:hover { background: #313244; } QPushButton:checked { background: #E74C3C; color: white; }")
        self._mic_btn.setCheckable(True)
        self._mic_btn.clicked.connect(self._toggle_voice_input)
        toolbar.addWidget(self._mic_btn)

        # TTS toggle
        self._tts_btn = QPushButton("TTS")
        self._tts_btn.setCheckable(True)
        self._tts_btn.setStyleSheet("QPushButton { background: transparent; color: #cdd6f4; border: 1px solid #45475a; border-radius: 4px; padding: 2px 10px; font-size: 11px; } QPushButton:hover { background: #313244; } QPushButton:checked { background: #4A90D9; color: white; border-color: #4A90D9; }")
        self._tts_btn.clicked.connect(self._toggle_tts)
        toolbar.addWidget(self._tts_btn)

        # Screenshot
        scr_btn = QPushButton("Shot")
        scr_btn.setStyleSheet("QPushButton { background: transparent; color: #cdd6f4; border: 1px solid #45475a; border-radius: 4px; padding: 2px 10px; font-size: 11px; } QPushButton:hover { background: #313244; }")
        scr_btn.clicked.connect(self._capture_screenshot)
        toolbar.addWidget(scr_btn)

        # File attach
        file_btn = QPushButton("File")
        file_btn.setStyleSheet("QPushButton { background: transparent; color: #cdd6f4; border: 1px solid #45475a; border-radius: 4px; padding: 2px 10px; font-size: 11px; } QPushButton:hover { background: #313244; }")
        file_btn.clicked.connect(self._attach_file)
        toolbar.addWidget(file_btn)

        self.addToolBar(toolbar)

        # ---- Central: splitter (sidebar + chat) ----
        splitter = QSplitter(Qt.Orientation.Horizontal)
        self.setCentralWidget(splitter)

        # Sidebar
        sidebar = QWidget()
        sidebar.setFixedWidth(200)
        sidebar.setStyleSheet("background: #1e1e2e; border-right: 1px solid #45475a;")
        side_layout = QVBoxLayout(sidebar)
        side_layout.setContentsMargins(8, 8, 8, 8)
        side_layout.setSpacing(6)

        side_label = QLabel("Conversations")
        side_label.setStyleSheet("color: #aaa; font-size: 11px; font-weight: bold;")
        side_layout.addWidget(side_label)

        self._conv_list = QListWidget()
        self._conv_list.setStyleSheet("QListWidget { background: #181825; color: #cdd6f4; border: none; font-size: 12px; } QListWidget::item { padding: 8px 10px; border-radius: 4px; margin: 1px 0; } QListWidget::item:selected { background: #4A90D9; color: white; } QListWidget::item:hover { background: #252536; }")
        self._conv_list.itemClicked.connect(self._on_conv_selected)
        side_layout.addWidget(self._conv_list)

        del_btn = QPushButton("Delete")
        del_btn.setStyleSheet("QPushButton { background: transparent; color: #E74C3C; border: 1px solid #E74C3C; border-radius: 4px; padding: 4px; font-size: 11px; } QPushButton:hover { background: #3e1a1a; }")
        del_btn.clicked.connect(self._delete_conversation)
        side_layout.addWidget(del_btn)

        splitter.addWidget(sidebar)

        # Chat area (right side)
        chat_widget = QWidget()
        chat_layout = QVBoxLayout(chat_widget)
        chat_layout.setContentsMargins(0, 0, 0, 0)
        chat_layout.setSpacing(0)

        self._scroll = QScrollArea()
        self._scroll.setWidgetResizable(True)
        self._scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._scroll.setStyleSheet("QScrollArea { background: #181825; border: none; margin: 0; padding: 0; }")
        self._scroll.viewport().setStyleSheet("background: #181825; margin: 0; padding: 0;")

        self._msg_container = QWidget()
        self._msg_container.setStyleSheet("background: #181825; margin: 0; padding: 0;")
        self._msg_layout = QVBoxLayout(self._msg_container)
        self._msg_layout.setContentsMargins(0, 8, 0, 8)
        self._msg_layout.setSpacing(4)
        self._msg_layout.insertStretch(0, 1)
        self._scroll.setWidget(self._msg_container)
        self._scroll.verticalScrollBar().rangeChanged.connect(self._on_range_changed)
        self._scroll.verticalScrollBar().valueChanged.connect(self._on_scroll_value)

        # Input bar
        input_panel = QWidget()
        input_panel.setFixedHeight(56)
        input_panel.setStyleSheet("background: #1e1e2e; border-top: 1px solid #45475a;")
        input_layout = QHBoxLayout(input_panel)
        input_layout.setContentsMargins(12, 8, 12, 8)
        input_layout.setSpacing(8)

        self._input = QLineEdit()
        self._input.setPlaceholderText("Type a message... (Enter to send)")
        self._input.setFont(QFont("Segoe UI", 11))
        self._input.setStyleSheet("QLineEdit { background: #313244; color: #cdd6f4; border: 1px solid #45475a; border-radius: 8px; padding: 8px 14px; }")
        self._input.returnPressed.connect(self._on_send)
        input_layout.addWidget(self._input)

        send_btn = QPushButton("Send")
        send_btn.setStyleSheet("QPushButton { background-color: #4A90D9; color: white; border: none; border-radius: 8px; padding: 8px 20px; font-size: 12px; font-weight: bold; } QPushButton:hover { background-color: #5BA0E9; } QPushButton:pressed { background-color: #3A80C9; }")
        send_btn.clicked.connect(self._on_send)
        input_layout.addWidget(send_btn)

        # Attachment indicator
        self._att_label = QPushButton("")
        self._att_label.setStyleSheet("QPushButton { background: #313244; color: #f9e2af; border: 1px solid #f9e2af; border-radius: 6px; padding: 4px 10px; font-size: 11px; text-align: left; } QPushButton:hover { background: #45475a; }")
        self._att_label.setVisible(False)
        self._att_label.clicked.connect(self._clear_attachments)
        chat_layout.addWidget(self._att_label)

        chat_layout.addWidget(self._scroll)
        chat_layout.addWidget(input_panel)
        splitter.addWidget(chat_widget)
        splitter.setSizes([200, 700])

        # ---- Internal state ----
        self._streaming_worker: StreamingApiWorker | None = None
        self._streaming_bubble = None
        self._cursor_timer: QTimer | None = None
        self._stream_timer = QElapsedTimer()
        self._stream_started_at: str = ''
        
        self._typing: TypingIndicator | None = None
        self._worker: ApiWorker | None = None
        self._attachments: list = []
        self._last_message: str = ""  # for retry
        self._stream_first_token = False
        self._at_bottom = True

        self.setStyleSheet(MessageBubble.bubble_stylesheet())

        # Load conversations and activate the latest
        self._refresh_sidebar()
        cid = self._conv.ensure_active()
        self._load_conversation_messages(cid)

    # ------------------------------------------------------------------
    # Public
    # ------------------------------------------------------------------

    @property
    def input_widget(self) -> QLineEdit:
        return self._input

    def add_user_message(self, text: str) -> None:
        self._add_bubble("user", text)

    def add_agent_message(self, text: str) -> None:
        self._add_bubble("agent", text)

    def show_typing(self) -> None:
        if self._typing is not None:
            return
        self._remove_stretch()
        self._typing = TypingIndicator()
        self._msg_layout.addWidget(self._typing)
        self._add_stretch()
        self._scroll_to_bottom()

    def hide_typing(self) -> None:
        if self._typing is None:
            return
        self._msg_layout.removeWidget(self._typing)
        self._typing.stop()
        self._typing.deleteLater()
        self._typing = None

    # ------------------------------------------------------------------
    # Slots
    # ------------------------------------------------------------------

    def _on_send(self, retry_text: str | None = None) -> None:
        text = retry_text or self._input.text().strip()
        if not text and not self._attachments:
            return
        self._input.clear()
        self._last_message = text
        display = text or ""
        if self._attachments:
            parts = []
            for a in self._attachments:
                if a["type"] == "image": parts.append("[Screenshot]")
                elif a["type"] == "file": parts.append("[File: " + a.get("name", "?") + "]")
            display = " ".join(parts) + " " + (text or "")
        self.add_user_message(display)
        self.thinking_started.emit()
        self.api_call_started.emit()

        handler = self._conv.active_handler
        if handler is None:
            cid = self._conv.create()
            self._refresh_sidebar()
            handler = self._conv.active_handler
            if handler is None:
                self.hide_typing()
                self._show_error("Failed to create conversation.", "unknown")
                return

        self._start_streaming(text)

    def add_screenshot(self, base64_data: str) -> None:
        self._attachments.append({"type": "image", "data": base64_data})
        self._att_label.setText("Attached: Screenshot")
        self._att_label.setVisible(True)

    def add_file(self, filepath: str, content: str) -> None:
        import os
        name = os.path.basename(filepath)
        self._attachments.append({"type": "file", "name": name, "data": content})
        self._att_label.setText("Attached: " + name)
        self._att_label.setVisible(True)

    def _clear_attachments(self) -> None:
        self._attachments.clear()
        self._att_label.setVisible(False)

    def _on_api_result(self, data: dict) -> None:
        self.hide_typing()
        reply = data.get("response", "")
        self.api_call_finished.emit(reply)
        self.add_agent_message(reply)

        # Suggestions
        suggestions = data.get("suggestions", [])
        if suggestions:
            self._remove_stretch()
            chips = SuggestionChips(suggestions)
            chips.clicked.connect(self._on_suggestion_clicked)
            self._msg_layout.addWidget(chips)
            self._add_stretch()
            self._scroll_to_bottom()

        self._conv.save_active()
        self._refresh_sidebar()

    def _on_api_error(self, error_msg: str, category: str) -> None:
        self.api_call_error.emit(error_msg)
        self.hide_typing()

        error_bubble = ErrorBubble(error_msg, category)
        error_bubble.retry_requested.connect(lambda: self._retry_last())
        self._add_error_bubble(error_bubble)

    def _on_suggestion_clicked(self, text: str) -> None:
        self._input.setText(text)
        self._on_send()

    def _retry_last(self) -> None:
        if self._last_message:
            self._on_send(retry_text=self._last_message)

    # ------------------------------------------------------------------
    # Conversation management
    # ------------------------------------------------------------------

    def _new_conversation(self) -> None:
        cid = self._conv.create()
        self._clear_message_area()
        self._refresh_sidebar()
        self._select_in_list(cid)
                # Update window title
        for conv in self._conv.list_conversations():
            if conv["id"] == cid:
                self.setWindowTitle(f"Desktop Agent  - {conv.get('title', 'Chat')}")
                break

    # ------------------------------------------------------------------
    # Streaming
    # ------------------------------------------------------------------

    def _start_streaming(self, text: str) -> None:
        handler = self._conv.active_handler
        if handler is None:
            self._show_error("No active conversation.", "unknown")
            return
        self.hide_typing()
        content = text
        if self._attachments:
            parts = []
            has_img = any(a["type"] == "image" for a in self._attachments)
            # Try vision model for screenshots
            desc = None
            if has_img and self._vision and self._vision.enabled:
                for a in self._attachments:
                    if a["type"] == "image":
                        desc = self._vision.describe(a["data"], prompt=text or "Describe this screenshot in detail.")
                        break
            if desc:
                parts.append({"type": "text", "text": (text or "") + "\n\n[Screenshot description: " + desc + "]"})
            else:
                if text:
                    parts.append({"type": "text", "text": text})
            for a in self._attachments:
                if a["type"] == "file":
                    parts.append({"type": "text", "text": "[File: " + a.get("name", "?") + "]\n\n```\n" + a["data"] + "\n```"})
                elif a["type"] == "image" and not desc:
                    parts.append({"type": "text", "text": "[Screenshot captured]"})
            if parts:
                content = parts
            self._clear_attachments()
        self._streaming_worker = StreamingApiWorker(handler, content, tools=TOOLS)
        self._streaming_worker.token_received.connect(self._on_stream_token)
        self._streaming_worker.stream_finished.connect(self._on_stream_finished)
        self._streaming_worker.stream_error.connect(self._on_stream_error)
        self._remove_stretch()
        self._streaming_bubble = MessageBubble("agent", "")
        cw2 = self._scroll.width()
        if cw2 > 100:
            w90 = int(cw2 * 0.90)
            self._streaming_bubble.set_bubble_max_width(w90)
        self._msg_layout.addWidget(self._streaming_bubble, 0, Qt.AlignmentFlag.AlignLeft)
        self._streaming_bubble.start_fade_in()
        self._add_stretch()
        self._scroll_to_bottom()
        self._cursor_timer = QTimer(self)
        self._cursor_timer.timeout.connect(self._blink_cursor)
        self._cursor_timer.start(530)
        self._stream_timer.start()
        from datetime import datetime
        self._stream_started_at = datetime.now().strftime("%H:%M:%S")
        self._set_streaming_ui(True)
        self._stream_first_token = True
        self._streaming_worker.start()

    def _on_stream_token(self, event) -> None:
        try:
            self._handle_stream_event(event)
        except Exception:
            pass

    def _handle_stream_event(self, event) -> None:
        if self._streaming_bubble is None:
            return

        # Handle dict events (new tool-call format)
        if isinstance(event, dict):
            etype = event.get("type", "")
            if etype == "text":
                token = event.get("content", "")
                if self._stream_first_token:
                    self._stream_first_token = False
                    self.streaming_started.emit()
                self._streaming_bubble._content += token
                self._streaming_bubble._content_label.setText(
                    _render_markdown(self._streaming_bubble._content + " ▌")
                )
            elif etype == "tool_start":
                name = event.get("name", "?")
                self._streaming_bubble._content += "\n\n> Running: `" + name + "`...\n"
                self._streaming_bubble._content_label.setText(
                    _render_markdown(self._streaming_bubble._content + " ▌")
                )
            elif etype == "tool_result":
                name = event.get("name", "?")
                result = event.get("result", "")
                result_short = result[:500] + ("..." if len(result) > 500 else "")
                self._streaming_bubble._content += (
                    "\n> Result from `" + name + "`:\n>\n> " + result_short.strip().replace("\n", "\n> ") + "\n"
                )
                self._streaming_bubble._content_label.setText(
                    _render_markdown(self._streaming_bubble._content + " ▌")
                )
        elif isinstance(event, str):
            # Backward compat: plain string tokens
            if self._stream_first_token:
                self._stream_first_token = False
                self.streaming_started.emit()
            self._streaming_bubble._content += event
            self._streaming_bubble._content_label.setText(
                _render_markdown(self._streaming_bubble._content + " ▌")
            )
            self._scroll_to_bottom()
    def _on_stream_finished(self) -> None:
        self._stop_cursor()
        elapsed = self._stream_timer.elapsed() / 1000.0
        if self._streaming_bubble:
            self._streaming_bubble._content_label.setText(
                _render_markdown(self._streaming_bubble._content)
            )
            # Lock final width after streaming finishes
            cw4 = self._scroll.width()
            if cw4 > 100:
                self._streaming_bubble.fit_bubble_to_content(int(cw4 * 0.90))
            self._streaming_bubble._time_label.setText(
                _relative_time(self._streaming_bubble._timestamp) + f"  ({elapsed:.1f}s)"
            )
        reply = self._streaming_bubble._content if self._streaming_bubble else ""
        self._reset_streaming_ui()
        self._conv.save_active()
        self._refresh_sidebar()
        self.api_call_finished.emit(reply)
        self._scroll_to_bottom()

    def _on_stream_error(self, error_msg: str, category: str) -> None:
        self._stop_cursor()
        if self._streaming_bubble:
            self._streaming_bubble._content_label.setText(
                _render_markdown(
                    self._streaming_bubble._content
                    + "\n\n*[" + category.upper() + "]* " + error_msg
                )
            )
        self._reset_streaming_ui()
        self.api_call_error.emit(error_msg)

    def _cancel_streaming(self) -> None:
        if self._streaming_worker:
            self._streaming_worker.cancel()
            self._streaming_worker.quit()
            self._streaming_worker.wait(2000)
        self._stop_cursor()
        self._reset_streaming_ui()

    def _stop_cursor(self) -> None:
        if self._cursor_timer:
            self._cursor_timer.stop()
            self._cursor_timer = None

    def _set_streaming_ui(self, streaming: bool) -> None:
        self._input.setEnabled(not streaming)
        self._input.setPlaceholderText(
            "Agent is responding..." if streaming else "Type a message... (Enter to send)"
        )
        input_parent = self._input.parent()
        if input_parent is None:
            return
        for i in range(input_parent.layout().count()):
            w = input_parent.layout().itemAt(i).widget()
            if isinstance(w, QPushButton) and w.text() in ("Send", "Cancel"):
                if streaming:
                    w.setText("Cancel")
                    w.setStyleSheet("QPushButton { background-color: #E74C3C; color: white; border: none; border-radius: 8px; padding: 8px 20px; font-size: 12px; font-weight: bold; } QPushButton:hover { background-color: #C0392B; }")
                    try:
                        w.clicked.disconnect()
                    except Exception:
                        pass
                    w.clicked.connect(self._cancel_streaming)
                else:
                    w.setText("Send")
                    w.setStyleSheet("QPushButton { background-color: #4A90D9; color: white; border: none; border-radius: 8px; padding: 8px 20px; font-size: 12px; font-weight: bold; } QPushButton:hover { background-color: #5BA0E9; } QPushButton:pressed { background-color: #3A80C9; }")
                    try:
                        w.clicked.disconnect()
                    except Exception:
                        pass
                    w.clicked.connect(self._on_send)
                break

    def _reset_streaming_ui(self) -> None:
        self._set_streaming_ui(False)
        self._streaming_worker = None
        self._streaming_bubble = None

    def _blink_cursor(self) -> None:
        if self._streaming_bubble is None:
            return
        text = self._streaming_bubble._content_label.text()
        if " \u258C</" in text:
            self._streaming_bubble._content_label.setText(
                _render_markdown(self._streaming_bubble._content)
            )
        else:
            self._streaming_bubble._content_label.setText(
                _render_markdown(self._streaming_bubble._content + " \u258C")
            )


    # ------------------------------------------------------------------
    # Advanced features
    # ------------------------------------------------------------------

    def _font_smaller(self) -> None:
        self._font_size = max(10, self._font_size - 1)
        self._apply_font_size()
        self.font_size_changed.emit(self._font_size)

    def _font_larger(self) -> None:
        self._font_size = min(24, self._font_size + 1)
        self._apply_font_size()
        self.font_size_changed.emit(self._font_size)

    def set_font_size(self, size: int) -> None:
        self._font_size = max(10, min(24, size))
        self._apply_font_size()

    def _apply_font_size(self) -> None:
        fs = self._font_size
        self._input.setFont(QFont("Segoe UI", fs))
        for i in range(self._msg_layout.count()):
            w = self._msg_layout.itemAt(i).widget()
            if isinstance(w, MessageBubble) and w._content_label:
                w._content_label.setStyleSheet(f"font-size: {fs}px; line-height: 1.5;")

    def _show_templates_menu(self) -> None:
        from src.utils.templates import TEMPLATES
        menu = QMenu(self)
        menu.setStyleSheet("QMenu { background: #2b2b2b; color: #eee; border: 1px solid #555; } QMenu::item:selected { background: #4A90D9; }")
        for t in TEMPLATES:
            action = menu.addAction(t["title"])
            action.setData(t["prompt"])
        action = menu.exec(self._templates_btn.mapToGlobal(self._templates_btn.rect().bottomLeft()))
        if action:
            self._input.setText(action.data())
            self._input.setFocus()

    def _toggle_voice_input(self) -> None:
        self.voice_input_requested.emit()

    def _toggle_tts(self) -> None:
        self.tts_toggled.emit(self._tts_btn.isChecked())

    def set_tts_checked(self, checked: bool) -> None:
        self._tts_btn.setChecked(checked)

    def _capture_screenshot(self) -> None:
        self.screenshot_requested.emit()

    def _attach_file(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "Select File")
        if path:
            self.file_attached.emit(path)

    def _clear_current(self) -> None:
        handler = self._conv.active_handler
        if handler:
            handler.reset()
        self._clear_message_area()

    def _delete_conversation(self) -> None:
        item = self._conv_list.currentItem()
        if item is None:
            return
        cid = item.data(Qt.ItemDataRole.UserRole)
        if cid is None:
            return
        reply = QMessageBox.question(self, "Delete", "Delete this conversation?", QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
        if reply != QMessageBox.StandardButton.Yes:
            return
        was_active = (cid == self._conv.active_id)
        self._conv.delete(cid)
        if was_active:
            self._clear_message_area()
            new_id = self._conv.ensure_active()
            if new_id:
                self._load_conversation_messages(new_id)
        self._refresh_sidebar()

    def _export_current(self) -> None:
        cid = self._conv.active_id
        if cid is None:
            return
        from PyQt6.QtWidgets import QFileDialog
        path, _ = QFileDialog.getSaveFileName(self, "Export Conversation", "chat_export.json", "JSON (*.json);;Markdown (*.md);;PDF (*.pdf)")
        if not path:
            return
        if path.endswith(".pdf"):
            fmt = "pdf"
        elif path.endswith(".md"):
            fmt = "markdown"
        else:
            fmt = "json"
        content = self._conv.export_conversation(cid, fmt)
        if content:
            if fmt == "pdf":
                with open(path, "wb") as f:
                    f.write(content)
            else:
                with open(path, "w", encoding="utf-8") as f:
                    f.write(content)
            QMessageBox.information(self, "Export", f"Saved to {Path(path).name}")

    def _on_conv_selected(self, item: QListWidgetItem) -> None:
        cid = item.data(Qt.ItemDataRole.UserRole)
        if cid:
            self._conv.switch(cid)
            self._clear_message_area()
            self._load_conversation_messages(cid)
            # Update window title
            for conv in self._conv.list_conversations():
                if conv["id"] == cid:
                    self.setWindowTitle(f"Desktop Agent  - {conv.get('title', 'Chat')}")
                    break

    def _refresh_sidebar(self) -> None:
        self._conv_list.clear()
        active_id = self._conv.active_id
        for conv in self._conv.list_conversations():
            title = conv.get("title", "New Chat")[:30]
            count = conv.get("message_count", 0)
            # Show message count in the title
            label = f"{title}  ({count})"
            item = QListWidgetItem(label)
            item.setData(Qt.ItemDataRole.UserRole, conv["id"])
            updated = conv.get("updated_at", "")[:16].replace("T", " ")
            item.setToolTip(f"Messages: {count}  |  Updated: {updated}")
            self._conv_list.addItem(item)
            # Highlight the active conversation
            if conv["id"] == active_id:
                self._conv_list.setCurrentItem(item)

    def _select_in_list(self, cid: str) -> None:
        for i in range(self._conv_list.count()):
            item = self._conv_list.item(i)
            if item and item.data(Qt.ItemDataRole.UserRole) == cid:
                self._conv_list.setCurrentItem(item)
                break

    def _load_conversation_messages(self, cid: str) -> None:
        handler = self._conv.load_conversation(cid)
        if handler is None:
            return
        for msg in handler.history:
            # Skip tool-call messages with no displayable content
            role = msg.get("role", "")
            content = _m2t(msg.get("content", ""))
            if role == "tool":
                continue
            if role == "assistant" and not content and msg.get("tool_calls"):
                continue
            self._add_bubble(role, content or "")
        self._conv.switch(cid)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _add_bubble(self, role: str, content: str) -> None:
        self._remove_stretch()
        bubble = MessageBubble(role, content)
        # Cap at 90% -- bubble shrinks to content via Maximum policy
        cw = self._scroll.width()
        if cw > 100:
            bubble.fit_bubble_to_content(int(cw * 0.90))
        align = Qt.AlignmentFlag.AlignRight if role == "user" else Qt.AlignmentFlag.AlignLeft
        self._msg_layout.addWidget(bubble, 0, align)
        self._add_stretch()
        bubble.start_fade_in()
        self._scroll_to_bottom()

    def _add_error_bubble(self, bubble: ErrorBubble) -> None:
        self._remove_stretch()
        cw = self._scroll.width()
        if cw > 100:
            bubble.fit_bubble_to_content(int(cw * 0.90))
        self._msg_layout.addWidget(bubble, 0, Qt.AlignmentFlag.AlignLeft)
        bubble.start_fade_in()
        self._add_stretch()
        self._scroll_to_bottom()

    def _show_error(self, msg: str, category: str) -> None:
        bubble = ErrorBubble(msg, category)
        self._add_error_bubble(bubble)

    def _clear_message_area(self) -> None:
        while self._msg_layout.count() > 0:
            item = self._msg_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        self._msg_layout.insertStretch(0, 1)

    def _remove_stretch(self) -> None:
        if self._msg_layout.count() > 0:
            item = self._msg_layout.itemAt(0)
            if item and item.spacerItem():
                self._msg_layout.removeItem(item)

    def _add_stretch(self) -> None:
        self._msg_layout.insertStretch(0, 1)

    def _scroll_to_bottom(self) -> None:
        self._at_bottom = True
        sb = self._scroll.verticalScrollBar()
        sb.setValue(sb.maximum())

    def _on_range_changed(self, _min: int, _max: int) -> None:
        if self._at_bottom:
            self._scroll.verticalScrollBar().setValue(_max)

    def _on_scroll_value(self, val: int) -> None:
        sb = self._scroll.verticalScrollBar()
        self._at_bottom = val >= sb.maximum() - 20

    def _toggle_pin(self, checked: bool) -> None:
        if checked:
            self.setWindowFlags(self.windowFlags() | Qt.WindowType.WindowStaysOnTopHint)
        else:
            self.setWindowFlags(self.windowFlags() & ~Qt.WindowType.WindowStaysOnTopHint)
        import time; self._show_ts = time.time()
        self.show()

    # ------------------------------------------------------------------
    # Theme
    # ------------------------------------------------------------------

    def set_popup_mode(self, enabled: bool) -> None:
        self._popup_mode = enabled

    def show_near(self, x: int, y: int) -> None:
        screen = QApplication.primaryScreen()
        if screen:
            geo = screen.availableGeometry()
            w, h = self.width(), self.height()
            px = max(geo.left(), min(geo.right() - w, x - w // 2))
            py = max(geo.top(), min(geo.bottom() - h, y - h - 20))
            self.move(px, py)
        self.show()
        self.raise_()
        self.activateWindow()
        # Force foreground on Windows
        try:
            import ctypes
            hwnd = int(self.winId())
            user32 = ctypes.windll.user32
            user32.ShowWindow(hwnd, 9)  # SW_RESTORE
            user32.SetForegroundWindow(hwnd)
            user32.BringWindowToTop(hwnd)
            user32.SetFocus(hwnd)
        except Exception:
            pass

    def apply_theme(self, theme: str) -> None:
        self._theme = theme
        actual = theme
        if theme == "system":
            actual = self._detect_system_theme()
        if actual == "light":
            self._apply_light_theme()
        else:
            self._apply_dark_theme()

    def set_window_opacity(self, value: float) -> None:
        self.setWindowOpacity(max(0.3, min(1.0, value)))

    @staticmethod
    def _detect_system_theme() -> str:
        try:
            import winreg
            key = winreg.OpenKey(winreg.HKEY_CURRENT_USER,
                                 r"Software\\Microsoft\\Windows\\CurrentVersion\\Themes\\Personalize")
            value, _ = winreg.QueryValueEx(key, "AppsUseLightTheme")
            winreg.CloseKey(key)
            return "light" if value == 1 else "dark"
        except Exception:
            return "dark"

    def _apply_dark_theme(self) -> None:
        self.setStyleSheet("""
            QMainWindow { background: #181825; }
            QToolBar { background: #1e1e2e; border-bottom: 1px solid #45475a; }
            QScrollArea { background: #181825; border: none; }
        """ + MessageBubble.bubble_stylesheet())

    def _apply_light_theme(self) -> None:
        self.setStyleSheet("QMainWindow { background: #f5f5f5; } QToolBar { background: #ffffff; border-bottom: 1px solid #ddd; } QScrollArea { background: #f5f5f5; border: none; }")
        self._msg_container.setStyleSheet("background: #f5f5f5;")
        self._input.setStyleSheet("QLineEdit { background: #ffffff; color: #333; border: 1px solid #ccc; border-radius: 8px; padding: 8px 14px; }")

    def changeEvent(self, event) -> None:
        super().changeEvent(event)

    def closeEvent(self, event: QCloseEvent | None) -> None:
        if event:
            event.ignore()
        self._conv.save_active()
        self.hide()

    def resizeEvent(self, event: QResizeEvent | None) -> None:
        super().resizeEvent(event)
        # Update max width of all existing messages
        cw = self._scroll.width()
        if cw > 100:
            max_w = int(cw * 0.90)
            for i in range(self._msg_layout.count()):
                widget = self._msg_layout.itemAt(i).widget()
                if isinstance(widget, MessageBubble):
                    widget.fit_bubble_to_content(max_w)
