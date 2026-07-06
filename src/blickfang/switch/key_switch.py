"""Tastatur-/physischer Schalter (/LF510/) — Person B und Tests.

Implementiert dieselbe SwitchSource-Schnittstelle wie video_switch.
Physische Schalter werden über USB-Adapter als Tastatureingabe empfangen.
"""

from __future__ import annotations

import logging
import time
from typing import Optional

from blickfang.core.events import EventType, SwitchEvent
from blickfang.switch.base import SwitchSource

logger = logging.getLogger(__name__)


class KeySwitch(SwitchSource):
    """Tastatur-basierter Schalter.

    Empfängt Tastatureingaben (über Tkinter-Binding) und wandelt sie
    in SwitchEvents um. Physische Schalter über USB-Adapter erscheinen
    als Tastatureingabe.
    """

    def __init__(self, key_binding: str = "space"):
        """
        Args:
            key_binding: Taste, die als Schalter dient (z.B. "space", "Return").
        """
        super().__init__(source_id="key_switch")
        self._key_binding = key_binding
        self._last_press_time: float = 0.0
        self._debounce_s: float = 0.1  # 100ms Debouncing

    @property
    def key_binding(self) -> str:
        return self._key_binding

    def on_key_press(self, event=None) -> Optional[SwitchEvent]:
        """Callback für Tastendruck (wird von Tkinter aufgerufen).

        Args:
            event: Tkinter-Event (optional, für Kompatibilität).

        Returns:
            SwitchEvent wenn gültig (nach Debouncing).
        """
        if not self.enabled:
            return None

        now = time.perf_counter()

        # Debouncing
        if now - self._last_press_time < self._debounce_s:
            return None

        self._last_press_time = now

        switch_event = SwitchEvent(
            source_id=self.source_id,
            event_type=EventType.SINGLE,
            timestamp_capture=now,
            confidence=1.0,  # Physischer Schalter = volle Konfidenz
            channel_name="key_input",
        )

        self.emit(switch_event)
        logger.debug(f"KeySwitch: Event emittiert (Taste: {self._key_binding})")
        return switch_event

    def start(self) -> None:
        """Startet den Key-Schalter (Binding wird extern gesetzt)."""
        logger.info(f"KeySwitch gestartet (Taste: {self._key_binding})")

    def stop(self) -> None:
        """Stoppt den Key-Schalter."""
        logger.info("KeySwitch gestoppt")
