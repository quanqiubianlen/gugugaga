"""Speech-to-text and text-to-speech utilities."""

import threading
from typing import Callable


# ---------------------------------------------------------------------------
# Speech-to-text
# ---------------------------------------------------------------------------

class SpeechToText:
    """Capture microphone input and convert to text via speech_recognition."""

    def __init__(self) -> None:
        self._listening = False

    def listen(self, callback: Callable[[str], None], error_callback: Callable[[str], None] | None = None) -> None:
        """Start listening in a background thread.  Calls ``callback(text)`` on success,
        or ``error_callback(msg)`` on failure."""
        if self._listening:
            return
        self._listening = True

        def _run() -> None:
            try:
                import speech_recognition as sr
                r = sr.Recognizer()
                with sr.Microphone() as source:
                    r.adjust_for_ambient_noise(source, duration=0.5)
                    audio = r.listen(source, timeout=5, phrase_time_limit=10)
                text = r.recognize_google(audio, language="zh-CN")
                callback(text)
            except ImportError:
                msg = "speech_recognition not installed. Run: pip install speechrecognition"
                if error_callback:
                    error_callback(msg)
            except Exception as exc:
                msg = f"Speech recognition failed: {exc}"
                if error_callback:
                    error_callback(msg)
            finally:
                self._listening = False

        threading.Thread(target=_run, daemon=True).start()


# ---------------------------------------------------------------------------
# Text-to-speech
# ---------------------------------------------------------------------------

class TextToSpeech:
    """Speak text aloud using pyttsx3 (offline, cross-platform)."""

    def __init__(self) -> None:
        self._engine = None
        self._enabled = False

    @property
    def enabled(self) -> bool:
        return self._enabled

    @enabled.setter
    def enabled(self, value: bool) -> None:
        self._enabled = value
        if value and self._engine is None:
            self._init_engine()

    def speak(self, text: str) -> None:
        """Queue text for speaking.  No-op if TTS is disabled."""
        if not self._enabled or self._engine is None:
            return
        # Strip markdown for cleaner speech
        clean = self._strip_markdown(text)
        self._engine.say(clean)
        self._engine.runAndWait()

    def speak_async(self, text: str) -> None:
        """Same as speak() but in a daemon thread so it doesn't block the UI."""
        if not self._enabled:
            return
        threading.Thread(target=self.speak, args=(text,), daemon=True).start()

    def stop(self) -> None:
        if self._engine:
            try:
                self._engine.stop()
            except Exception:
                pass

    def _init_engine(self) -> None:
        try:
            import pyttsx3
            self._engine = pyttsx3.init()
            self._engine.setProperty("rate", 180)
        except Exception:
            self._engine = None

    @staticmethod
    def _strip_markdown(text: str) -> str:
        import re
        # Remove code blocks, links, images, bold/italic markers
        text = re.sub(r"```.*?```", "", text, flags=re.DOTALL)
        text = re.sub(r"!\[.*?\]\(.*?\)", "", text)
        text = re.sub(r"\[([^\]]*)\]\(.*?\)", r"\1", text)
        text = re.sub(r"[*_~`#>|]", "", text)
        return text.strip()
