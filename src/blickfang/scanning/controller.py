"""Kommunikations-Controller: Verbindet Scanning, Layouts und Navigation.

Der Controller verwaltet den Gesamtzustand der Kommunikation:
- Welcher Modus ist aktiv (Hauptmenü, Phrasen, Buchstabieren, Ja/Nein)
- Navigation zwischen Modi
- Text-Buffer für Buchstabieren
- Notruf-Erkennung
"""

from __future__ import annotations

import logging
import time
from enum import Enum, auto
from typing import Callable, Dict, List, Optional

from blickfang.scanning.alarm import AlarmDetector, play_alarm_sound
from blickfang.scanning.engine import ScanItem, ScanLayout, ScanPhase, ScanningEngine
from blickfang.scanning.fatigue import FatigueMonitor
from blickfang.scanning.layouts import (
    get_keyboard_layout,
    get_phrases_layout,
    get_yesno_layout,
)
from blickfang.scanning.text_buffer import TextBuffer

logger = logging.getLogger(__name__)


class CommMode(Enum):
    """Kommunikations-Modi."""
    MAIN_MENU = auto()      # Hauptmenü (Phrasen / Buchstabieren / Ja-Nein)
    PHRASES = auto()        # Schnell-Phrasen nach Kategorien
    KEYBOARD = auto()       # Buchstaben-Scanning
    YESNO = auto()          # Ja/Nein/Passe
    IDLE = auto()           # Inaktiv


class CommunicationController:
    """Zentraler Controller für die gesamte Kommunikation.

    Verwaltet:
    - Aktiven Modus und Layout-Wechsel
    - Scanning-Engine
    - Text-Buffer (Buchstabieren)
    - Notruf-Erkennung
    - Ermüdungs-Monitoring
    """

    def __init__(
        self,
        on_speak: Optional[Callable[[str], None]] = None,
        on_mode_change: Optional[Callable[[CommMode], None]] = None,
        on_alarm: Optional[Callable[[], None]] = None,
        scan_speed_s: float = 1.5,
        cancel_countdown_s: float = 2.5,
    ):
        self._mode = CommMode.IDLE
        self._on_speak = on_speak
        self._on_mode_change = on_mode_change
        self._scan_speed_s = scan_speed_s
        self._cancel_countdown_s = cancel_countdown_s

        # Layouts laden
        self._keyboard_layout = get_keyboard_layout()
        self._phrases_layout = get_phrases_layout()
        self._yesno_layout = get_yesno_layout()
        self._main_menu_layout = self._create_main_menu()

        # Scan-Geschwindigkeit übernehmen
        for layout in [self._keyboard_layout, self._phrases_layout,
                       self._yesno_layout, self._main_menu_layout]:
            layout.scan_speed_s = scan_speed_s
            layout.cancel_countdown_s = cancel_countdown_s

        # Scanning-Engine
        self._engine = ScanningEngine(self._main_menu_layout)
        self._engine.on("select", self._on_item_selected)
        self._engine.on("no_answer", self._on_no_answer)

        # Text-Buffer
        self._text_buffer = TextBuffer()

        # Notruf
        self._alarm = AlarmDetector(
            required_signals=3,
            window_s=3.0,
            on_alarm=on_alarm or play_alarm_sound,
        )

        # Ermüdungs-Monitoring
        self._fatigue = FatigueMonitor()

        # Statistik
        self._selections_count = 0
        self._session_start = time.perf_counter()

    @property
    def mode(self) -> CommMode:
        return self._mode

    @property
    def engine(self) -> ScanningEngine:
        return self._engine

    @property
    def text_buffer(self) -> TextBuffer:
        return self._text_buffer

    @property
    def fatigue(self) -> FatigueMonitor:
        return self._fatigue

    @property
    def alarm(self) -> AlarmDetector:
        return self._alarm

    @property
    def current_layout(self) -> ScanLayout:
        return self._engine.layout

    def start(self, mode: CommMode = CommMode.MAIN_MENU) -> None:
        """Startet die Kommunikation im gewählten Modus."""
        self._switch_mode(mode)

    def stop(self) -> None:
        """Stoppt die Kommunikation."""
        self._engine.stop()
        self._mode = CommMode.IDLE
        if self._on_mode_change:
            self._on_mode_change(CommMode.IDLE)

    def signal(self) -> None:
        """Verarbeitet ein Switch-Signal.

        Wird aufgerufen wenn die Person ihr Signal gibt.
        Leitet an Scanning-Engine und Notruf-Detektor weiter.
        """
        # Notruf prüfen (immer, unabhängig vom Modus)
        self._alarm.signal()

        # An Scanning-Engine weiterleiten
        self._engine.signal()

        # Ermüdung tracken
        self._fatigue.record_signal()

    def tick(self) -> None:
        """Zeitbasierter Tick — muss regelmäßig aufgerufen werden."""
        self._engine.tick()

        # Ermüdungs-Check
        hint = self._fatigue.check()
        if hint and self._on_speak:
            self._on_speak(hint)

    def go_home(self) -> None:
        """Zurück zum Hauptmenü."""
        self._switch_mode(CommMode.MAIN_MENU)

    def go_keyboard(self) -> None:
        """Wechselt zum Buchstaben-Modus."""
        self._switch_mode(CommMode.KEYBOARD)

    def go_phrases(self) -> None:
        """Wechselt zum Phrasen-Modus."""
        self._switch_mode(CommMode.PHRASES)

    def go_yesno(self) -> None:
        """Wechselt zum Ja/Nein-Modus."""
        self._switch_mode(CommMode.YESNO)

    def get_predictions(self) -> List[str]:
        """Gibt aktuelle Wortvorschläge zurück (nur im Keyboard-Modus)."""
        if self._mode == CommMode.KEYBOARD:
            return self._text_buffer.get_predictions(max_count=4)
        return []

    def _switch_mode(self, mode: CommMode) -> None:
        """Wechselt den Kommunikations-Modus."""
        self._mode = mode

        if mode == CommMode.MAIN_MENU:
            self._engine.layout = self._main_menu_layout
        elif mode == CommMode.PHRASES:
            self._engine.layout = self._phrases_layout
        elif mode == CommMode.KEYBOARD:
            self._engine.layout = self._keyboard_layout
        elif mode == CommMode.YESNO:
            self._engine.layout = self._yesno_layout

        self._engine.start()

        if self._on_mode_change:
            self._on_mode_change(mode)

        logger.info(f"Modus gewechselt: {mode.name}")

    def _on_item_selected(self, item: ScanItem) -> None:
        """Callback wenn ein Item ausgewählt wurde."""
        if item is None:
            return

        self._selections_count += 1
        logger.info(f"Ausgewählt: '{item.label}' (Aktion: {item.action or 'text'})")

        # Sonderaktionen verarbeiten
        if item.action == "home":
            self._switch_mode(CommMode.MAIN_MENU)
            return

        if item.action == "keyboard":
            self._switch_mode(CommMode.KEYBOARD)
            return

        if item.action == "phrases":
            self._switch_mode(CommMode.PHRASES)
            return

        if item.action == "yesno":
            self._switch_mode(CommMode.YESNO)
            return

        if item.action == "alarm":
            play_alarm_sound()
            if self._on_speak:
                self._on_speak(item.speak)
            # Scan neu starten
            self._engine.start()
            return

        if item.action == "backspace":
            self._text_buffer.backspace()
            self._engine.start()  # Weiter scannen
            return

        if item.action == "space":
            self._text_buffer.add_space()
            self._engine.start()
            return

        if item.action == "clear":
            self._text_buffer.clear()
            self._engine.start()
            return

        if item.action == "speak":
            # Gesamten Text vorlesen
            text = self._text_buffer.get_full_text_for_speech()
            if text and self._on_speak:
                self._on_speak(text)
            self._engine.start()
            return

        if item.action == "done":
            # Text vorlesen und zum Hauptmenü
            text = self._text_buffer.get_full_text_for_speech()
            if text and self._on_speak:
                self._on_speak(text)
            self._text_buffer.clear()
            self._switch_mode(CommMode.MAIN_MENU)
            return

        # Standard: Text/Buchstabe verarbeiten
        if self._mode == CommMode.KEYBOARD:
            # Buchstabe zum Buffer hinzufügen
            self._text_buffer.add_char(item.value)
            # Weiter scannen
            self._engine.start()
        elif self._mode in (CommMode.PHRASES, CommMode.YESNO):
            # Phrase vorlesen
            if self._on_speak:
                self._on_speak(item.speak)
            # Scan neu starten
            time.sleep(0.5)  # Kurze Pause nach Sprachausgabe
            self._engine.start()
        elif self._mode == CommMode.MAIN_MENU:
            # Menüpunkt-Aktion ausführen
            if item.action:
                self._handle_menu_action(item.action)
            elif self._on_speak:
                self._on_speak(item.speak)
                self._engine.start()

    def _on_no_answer(self) -> None:
        """Callback bei Timeout (KEINE ANTWORT)."""
        logger.info("KEINE ANTWORT — Timeout")
        # Scan nach kurzer Pause neu starten
        self._engine.start()

    def _handle_menu_action(self, action: str) -> None:
        """Verarbeitet eine Hauptmenü-Aktion."""
        if action == "phrases":
            self._switch_mode(CommMode.PHRASES)
        elif action == "keyboard":
            self._switch_mode(CommMode.KEYBOARD)
        elif action == "yesno":
            self._switch_mode(CommMode.YESNO)
        elif action == "alarm":
            play_alarm_sound()

    def _create_main_menu(self) -> ScanLayout:
        """Erstellt das Hauptmenü-Layout."""
        from blickfang.scanning.engine import ScanRow

        layout = ScanLayout(
            name="Hauptmenü",
            scan_speed_s=self._scan_speed_s,
            max_cycles=3,
            cancel_countdown_s=self._cancel_countdown_s,
            speak_on_highlight=True,
        )

        row = ScanRow(label="Hauptmenü")
        row.items = [
            ScanItem(
                label="Schnell-Phrasen",
                speak="Schnell-Phrasen",
                action="phrases",
                icon="💬",
            ),
            ScanItem(
                label="Buchstabieren",
                speak="Buchstabieren",
                action="keyboard",
                icon="⌨",
            ),
            ScanItem(
                label="Ja / Nein",
                speak="Ja oder Nein",
                action="yesno",
                icon="✓✗",
            ),
            ScanItem(
                label="HILFE!",
                speak="Hilfe! Ich brauche Hilfe!",
                action="alarm",
                icon="🚨",
            ),
        ]
        layout.rows.append(row)

        return layout
