"""Zeitliche Muster: 1×, 2×, halten (/LF520/–/LF530/).

Konfigurierbare Bestätigungslogik inkl. Debouncing.
Die Muster-Semantik liegt in der Konfiguration, nicht im Event-Typ-Kern.
"""

from __future__ import annotations

import logging
import time
from collections import deque
from typing import Callable, Optional

from blickfang.core.config import PatternsConfig
from blickfang.core.events import EventType, SwitchEvent

logger = logging.getLogger(__name__)


class PatternMatcher:
    """Erkennt zeitliche Muster in SwitchEvents (/LF520/).

    Unterstützte Muster:
    - single: Einzelnes Signal → sofortige Bestätigung
    - double: 2× im Zeitfenster → Bestätigung
    - hold: Signal gehalten für X Sekunden → Bestätigung
    """

    def __init__(self, config: PatternsConfig):
        self._config = config
        self._pattern = config.confirmation
        self._double_window_s = config.double_window_s
        self._hold_duration_s = config.hold_duration_s

        # Event-History für Doppel-Erkennung
        self._recent_events: deque = deque(maxlen=10)

        # Callback für bestätigte Events
        self._on_confirmed: Optional[Callable[[SwitchEvent], None]] = None

    def set_callback(self, callback: Callable[[SwitchEvent], None]) -> None:
        """Setzt Callback für bestätigte (Pattern-gematchte) Events."""
        self._on_confirmed = callback

    def process_event(self, event: SwitchEvent) -> Optional[SwitchEvent]:
        """Verarbeitet ein rohes SwitchEvent und prüft auf Muster.

        Args:
            event: Rohes SwitchEvent vom Detektor/Switch.

        Returns:
            Bestätigtes SwitchEvent wenn Muster erkannt, sonst None.
        """
        if self._pattern == "single":
            return self._handle_single(event)
        elif self._pattern == "double":
            return self._handle_double(event)
        elif self._pattern == "hold":
            return self._handle_hold(event)
        else:
            logger.warning(f"Unbekanntes Muster: {self._pattern}")
            return self._handle_single(event)

    def _handle_single(self, event: SwitchEvent) -> SwitchEvent:
        """Einzelsignal: sofortige Bestätigung."""
        confirmed = SwitchEvent(
            source_id=event.source_id,
            event_type=EventType.SINGLE,
            timestamp_capture=event.timestamp_capture,
            confidence=event.confidence,
            channel_name=event.channel_name,
        )
        self._emit_confirmed(confirmed)
        return confirmed

    def _handle_double(self, event: SwitchEvent) -> Optional[SwitchEvent]:
        """Doppelsignal: 2× im Zeitfenster nötig."""
        now = event.timestamp_capture
        self._recent_events.append(event)

        # Prüfe ob ein vorheriges Event im Zeitfenster liegt
        for prev_event in list(self._recent_events)[:-1]:
            time_diff = now - prev_event.timestamp_capture
            if 0 < time_diff <= self._double_window_s:
                # Doppel-Signal erkannt!
                confirmed = SwitchEvent(
                    source_id=event.source_id,
                    event_type=EventType.DOUBLE,
                    timestamp_capture=event.timestamp_capture,
                    confidence=min(event.confidence, prev_event.confidence),
                    channel_name=event.channel_name,
                )
                # History leeren um Dreifach-Trigger zu vermeiden
                self._recent_events.clear()
                self._emit_confirmed(confirmed)
                return confirmed

        return None

    def _handle_hold(self, event: SwitchEvent) -> Optional[SwitchEvent]:
        """Gehaltenes Signal: Event-Typ HOLD vom Detektor erwartet."""
        # HOLD-Events werden direkt vom Detektor erzeugt wenn das Signal
        # lange genug gehalten wird. Hier nur durchreichen.
        if event.event_type == EventType.HOLD:
            confirmed = SwitchEvent(
                source_id=event.source_id,
                event_type=EventType.HOLD,
                timestamp_capture=event.timestamp_capture,
                confidence=event.confidence,
                channel_name=event.channel_name,
            )
            self._emit_confirmed(confirmed)
            return confirmed

        # Für SINGLE-Events im Hold-Modus: ignorieren (zu kurz)
        return None

    def _emit_confirmed(self, event: SwitchEvent) -> None:
        """Gibt bestätigtes Event an Callback weiter."""
        if self._on_confirmed is not None:
            self._on_confirmed(event)

    @property
    def pattern_description(self) -> str:
        """Menschenlesbare Beschreibung des aktiven Musters."""
        if self._pattern == "single":
            return "Einzelsignal (1×)"
        elif self._pattern == "double":
            return f"Doppelsignal (2× in {self._double_window_s}s)"
        elif self._pattern == "hold":
            return f"Halten ({self._hold_duration_s}s)"
        return self._pattern
