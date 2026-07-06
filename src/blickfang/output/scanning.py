"""3-Item-Scan: JA / NEIN / PASSE (/LF600/–/LF620/).

- Timeout ist nie eine Antwort (/LF610/).
- Cancel-Countdown vor jeder Sprachausgabe (/LF620/).
- Jedes Signal während des Countdowns bricht die Ausgabe ab.
"""

from __future__ import annotations

import logging
import time
from enum import Enum, auto
from typing import Callable, List, Optional

from blickfang.core.config import OutputConfig
from blickfang.core.events import SwitchEvent
from blickfang.output.tts import TTSEngine

logger = logging.getLogger(__name__)


class ScanState(Enum):
    """Zustände des Scanning-Ablaufs."""

    IDLE = auto()           # Warte auf Start
    SCANNING = auto()       # Item wird hervorgehoben
    SELECTED = auto()       # Item wurde ausgewählt
    COUNTDOWN = auto()      # Cancel-Countdown läuft
    SPEAKING = auto()       # Sprachausgabe aktiv
    NO_ANSWER = auto()      # Timeout: KEINE ANTWORT
    CANCELLED = auto()      # Ausgabe abgebrochen


class ScanResult:
    """Ergebnis eines Scan-Durchlaufs."""

    def __init__(self, item: Optional[str] = None, cancelled: bool = False,
                 no_answer: bool = False):
        self.item = item
        self.cancelled = cancelled
        self.no_answer = no_answer
        self.timestamp = time.perf_counter()


class YesNoScanner:
    """3-Item-Scanning-Engine für Ja/Nein/Passe (/LF600/).

    Scan-Ablauf:
    1. Items werden nacheinander hervorgehoben (Verweildauer konfigurierbar)
    2. Signal während Hervorhebung → Auswahl
    3. Cancel-Countdown vor Sprachausgabe
    4. Signal während Countdown → Abbruch
    5. Nach max_cycles ohne Auswahl → KEINE ANTWORT
    """

    def __init__(self, config: OutputConfig, tts: TTSEngine):
        self._config = config
        self._tts = tts
        self._items = config.items  # ["JA", "NEIN", "PASSE"]
        self._scan_speed_s = config.scan_speed_s
        self._max_cycles = config.max_cycles
        self._cancel_countdown_s = config.cancel_countdown_s

        # Zustand
        self._state = ScanState.IDLE
        self._current_index = 0
        self._cycle_count = 0
        self._item_start_time: float = 0.0
        self._countdown_start_time: float = 0.0
        self._selected_item: Optional[str] = None

        # Callbacks
        self._on_highlight: Optional[Callable[[int, str], None]] = None
        self._on_result: Optional[Callable[[ScanResult], None]] = None
        self._on_state_change: Optional[Callable[[ScanState], None]] = None
        self._on_countdown_tick: Optional[Callable[[float], None]] = None

    @property
    def state(self) -> ScanState:
        return self._state

    @property
    def current_item(self) -> Optional[str]:
        if 0 <= self._current_index < len(self._items):
            return self._items[self._current_index]
        return None

    @property
    def current_index(self) -> int:
        return self._current_index

    @property
    def countdown_remaining(self) -> float:
        """Verbleibende Cancel-Countdown-Zeit."""
        if self._state != ScanState.COUNTDOWN:
            return 0.0
        elapsed = time.perf_counter() - self._countdown_start_time
        return max(0.0, self._cancel_countdown_s - elapsed)

    def set_callbacks(
        self,
        on_highlight: Optional[Callable[[int, str], None]] = None,
        on_result: Optional[Callable[[ScanResult], None]] = None,
        on_state_change: Optional[Callable[[ScanState], None]] = None,
        on_countdown_tick: Optional[Callable[[float], None]] = None,
    ) -> None:
        """Setzt UI-Callbacks."""
        self._on_highlight = on_highlight
        self._on_result = on_result
        self._on_state_change = on_state_change
        self._on_countdown_tick = on_countdown_tick

    def start(self) -> None:
        """Startet einen neuen Scan-Durchlauf."""
        self._current_index = 0
        self._cycle_count = 0
        self._selected_item = None
        self._set_state(ScanState.SCANNING)
        self._item_start_time = time.perf_counter()
        self._highlight_current()

    def stop(self) -> None:
        """Stoppt den Scan."""
        self._set_state(ScanState.IDLE)

    def on_switch_event(self, event: SwitchEvent) -> None:
        """Verarbeitet ein SwitchEvent während des Scannens.

        Args:
            event: Bestätigtes SwitchEvent.
        """
        if self._state == ScanState.SCANNING:
            # Item ausgewählt!
            self._selected_item = self._items[self._current_index]
            logger.info(f"Scan: '{self._selected_item}' ausgewählt")
            self._set_state(ScanState.SELECTED)
            self._start_countdown()

        elif self._state == ScanState.COUNTDOWN:
            # Signal während Countdown → Abbruch! (/LF620/)
            logger.info("Scan: Ausgabe abgebrochen (Signal während Countdown)")
            self._tts.cancel()
            self._set_state(ScanState.CANCELLED)
            result = ScanResult(item=self._selected_item, cancelled=True)
            self._emit_result(result)

    def tick(self) -> None:
        """Wird regelmäßig aufgerufen (z.B. alle 50ms) für Zeitsteuerung."""
        now = time.perf_counter()

        if self._state == ScanState.SCANNING:
            # Prüfe ob Verweildauer abgelaufen
            elapsed = now - self._item_start_time
            if elapsed >= self._scan_speed_s:
                self._advance_item()

        elif self._state == ScanState.COUNTDOWN:
            # Prüfe ob Countdown abgelaufen
            elapsed = now - self._countdown_start_time
            remaining = self._cancel_countdown_s - elapsed

            if self._on_countdown_tick:
                self._on_countdown_tick(max(0.0, remaining))

            if remaining <= 0:
                # Countdown abgelaufen → Sprachausgabe
                self._speak_selection()

    def _advance_item(self) -> None:
        """Geht zum nächsten Item."""
        self._current_index += 1

        if self._current_index >= len(self._items):
            self._current_index = 0
            self._cycle_count += 1

            # Max-Zyklen erreicht? → KEINE ANTWORT (/LF610/)
            if self._cycle_count >= self._max_cycles:
                logger.info("Scan: KEINE ANTWORT (Timeout)")
                self._set_state(ScanState.NO_ANSWER)
                result = ScanResult(no_answer=True)
                self._emit_result(result)
                return

        self._item_start_time = time.perf_counter()
        self._highlight_current()

    def _start_countdown(self) -> None:
        """Startet den Cancel-Countdown (/LF620/)."""
        self._countdown_start_time = time.perf_counter()
        self._set_state(ScanState.COUNTDOWN)

    def _speak_selection(self) -> None:
        """Gibt die Auswahl per TTS aus."""
        if self._selected_item:
            self._set_state(ScanState.SPEAKING)
            self._tts.speak(self._selected_item)
            result = ScanResult(item=self._selected_item)
            self._emit_result(result)

    def _highlight_current(self) -> None:
        """Hebt das aktuelle Item hervor (UI-Callback)."""
        if self._on_highlight and 0 <= self._current_index < len(self._items):
            self._on_highlight(self._current_index, self._items[self._current_index])

    def _set_state(self, new_state: ScanState) -> None:
        """Setzt den Zustand und benachrichtigt UI."""
        self._state = new_state
        if self._on_state_change:
            self._on_state_change(new_state)

    def _emit_result(self, result: ScanResult) -> None:
        """Gibt das Ergebnis an den Callback weiter."""
        if self._on_result:
            self._on_result(result)
