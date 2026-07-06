"""Deutsche Sprachausgabe (TTS) (/LF630/).

pyttsx3 als Zero-Config-Basis; Piper als Qualitätsoption (M2+).
TTS läuft in einem eigenen Thread und darf das Scanning nie blockieren.
"""

from __future__ import annotations

import logging
import queue
import threading
from typing import Optional

from blickfang.core.config import TTSConfig

logger = logging.getLogger(__name__)


class TTSEngine:
    """Text-to-Speech Engine mit eigenem Thread.

    Referenz: Kap. 6.2 Threading-Modell — TTS-Thread isoliert blockierendes
    runAndWait.
    """

    def __init__(self, config: TTSConfig):
        self._config = config
        self._queue: queue.Queue = queue.Queue()
        self._thread: Optional[threading.Thread] = None
        self._running = False
        self._cancel_flag = threading.Event()
        self._speaking = threading.Event()
        self._engine = None

    def start(self) -> None:
        """Startet den TTS-Thread."""
        self._running = True
        self._thread = threading.Thread(target=self._tts_loop, daemon=True)
        self._thread.start()
        logger.info(f"TTS-Engine gestartet (Engine: {self._config.engine})")

    def stop(self) -> None:
        """Stoppt den TTS-Thread."""
        self._running = False
        self._cancel_flag.set()
        self._queue.put(None)  # Sentinel
        if self._thread is not None:
            self._thread.join(timeout=3.0)
        logger.info("TTS-Engine gestoppt")

    def speak(self, text: str) -> None:
        """Spricht Text aus (non-blocking).

        Der Text wird in die Queue gelegt und vom TTS-Thread verarbeitet.
        """
        if not self._running:
            logger.warning("TTS-Engine nicht gestartet")
            return
        self._cancel_flag.clear()
        self._queue.put(text)

    def cancel(self) -> None:
        """Bricht die aktuelle Sprachausgabe ab (/LF620/)."""
        self._cancel_flag.set()
        # Queue leeren
        while not self._queue.empty():
            try:
                self._queue.get_nowait()
            except queue.Empty:
                break
        logger.debug("TTS: Ausgabe abgebrochen")

    @property
    def is_speaking(self) -> bool:
        """True wenn gerade gesprochen wird."""
        return self._speaking.is_set()

    def _tts_loop(self) -> None:
        """Hauptschleife des TTS-Threads."""
        # Engine im Thread initialisieren (pyttsx3 erfordert das)
        self._init_engine()

        while self._running:
            try:
                text = self._queue.get(timeout=0.5)
            except queue.Empty:
                continue

            if text is None:
                break

            if self._cancel_flag.is_set():
                continue

            self._speaking.set()
            try:
                self._speak_text(text)
            except Exception as e:
                logger.error(f"TTS-Fehler: {e}")
            finally:
                self._speaking.clear()

    def _init_engine(self) -> None:
        """Initialisiert die TTS-Engine im Thread."""
        if self._config.engine == "pyttsx3":
            self._init_pyttsx3()
        elif self._config.engine == "piper":
            self._init_piper()
        else:
            logger.warning(f"Unbekannte TTS-Engine: {self._config.engine}")
            self._init_pyttsx3()

    def _init_pyttsx3(self) -> None:
        """Initialisiert pyttsx3."""
        try:
            import pyttsx3
            self._engine = pyttsx3.init()
            self._engine.setProperty("rate", self._config.rate)

            # Deutsche Stimme suchen
            voices = self._engine.getProperty("voices")
            for voice in voices:
                if "german" in voice.name.lower() or "de" in voice.id.lower():
                    self._engine.setProperty("voice", voice.id)
                    break

            logger.info("pyttsx3 initialisiert")
        except Exception as e:
            logger.error(f"pyttsx3 konnte nicht initialisiert werden: {e}")
            self._engine = None

    def _init_piper(self) -> None:
        """Initialisiert Piper TTS (M2+)."""
        # Piper-Integration für spätere Meilensteine
        logger.info("Piper-TTS: Noch nicht implementiert, Fallback auf pyttsx3")
        self._init_pyttsx3()

    def _speak_text(self, text: str) -> None:
        """Spricht einen Text aus."""
        if self._cancel_flag.is_set():
            return

        if self._engine is None:
            logger.warning(f"TTS nicht verfügbar, Text: {text}")
            return

        try:
            self._engine.say(text)
            self._engine.runAndWait()
        except Exception as e:
            logger.error(f"TTS Sprachausgabe fehlgeschlagen: {e}")
