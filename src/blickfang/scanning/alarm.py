"""Notruf-/Aufmerksamkeitsfunktion (/LF650/).

Konfigurierbares Muster (z.B. Signal 3× schnell hintereinander)
löst einen Alarmton aus — unabhängig vom aktuellen Modus.
"""

from __future__ import annotations

import logging
import time
import threading
from typing import Callable, List, Optional

logger = logging.getLogger(__name__)


class AlarmDetector:
    """Erkennt das Notruf-Muster und löst Alarm aus.

    Standard-Muster: 3 Signale innerhalb von 3 Sekunden.
    """

    def __init__(
        self,
        required_signals: int = 3,
        window_s: float = 3.0,
        cooldown_s: float = 10.0,
        on_alarm: Optional[Callable[[], None]] = None,
    ):
        self._required = required_signals
        self._window_s = window_s
        self._cooldown_s = cooldown_s
        self._on_alarm = on_alarm

        self._signal_times: List[float] = []
        self._last_alarm_time: float = 0.0
        self._enabled = True

    @property
    def enabled(self) -> bool:
        return self._enabled

    @enabled.setter
    def enabled(self, value: bool) -> None:
        self._enabled = value

    def signal(self) -> bool:
        """Registriert ein Signal und prüft auf Notruf-Muster.

        Returns:
            True wenn Alarm ausgelöst wurde.
        """
        if not self._enabled:
            return False

        now = time.perf_counter()

        # Cooldown prüfen
        if now - self._last_alarm_time < self._cooldown_s:
            return False

        # Signal registrieren
        self._signal_times.append(now)

        # Alte Signale entfernen (außerhalb Fenster)
        cutoff = now - self._window_s
        self._signal_times = [t for t in self._signal_times if t >= cutoff]

        # Muster prüfen
        if len(self._signal_times) >= self._required:
            self._trigger_alarm()
            self._signal_times.clear()
            self._last_alarm_time = now
            return True

        return False

    def _trigger_alarm(self) -> None:
        """Löst den Alarm aus."""
        logger.warning("NOTRUF ausgelöst!")
        if self._on_alarm:
            self._on_alarm()

    def reset(self) -> None:
        """Setzt den Detektor zurück."""
        self._signal_times.clear()


def play_alarm_sound() -> None:
    """Spielt einen Alarmton ab (plattformübergreifend).

    Verwendet System-Beep als Fallback, wenn kein Audio-Backend verfügbar.
    """
    def _play():
        try:
            # Versuche winsound (Windows)
            import winsound
            for _ in range(5):
                winsound.Beep(1000, 200)
                time.sleep(0.1)
                winsound.Beep(1500, 200)
                time.sleep(0.1)
        except (ImportError, RuntimeError):
            # Linux/Mac: Terminal-Bell
            for _ in range(5):
                print("\a", end="", flush=True)
                time.sleep(0.3)

    # In eigenem Thread damit UI nicht blockiert
    thread = threading.Thread(target=_play, daemon=True)
    thread.start()
