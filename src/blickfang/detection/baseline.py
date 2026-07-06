"""Gated Dual-Timescale-Baseline (/LF410/–/LF430/).

Zwei Zeitskalen:
- Langsam (Minuten): für Drift/Ermüdung — wird von der Detektion genutzt.
- Schnell (Sekunden): für Licht-Anpassung.

Gating: Samples aus RISING/HELD/CONFIRM/EMIT/REFRACTORY fließen NIEMALS
in die Baseline ein (sonst kontaminiert das Signal die eigene Referenz).
"""

from __future__ import annotations

from collections import deque
from typing import Optional

import numpy as np

from blickfang.core.events import DetectorState


class RollingMedianMAD:
    """Rolling Median und MAD über ein Zeitfenster.

    Effiziente Implementierung mit sortiertem Ringpuffer.
    """

    def __init__(self, window_s: float, mad_floor: float = 0.0):
        """
        Args:
            window_s: Fensterbreite in Sekunden.
            mad_floor: Minimaler MAD-Wert (/LF420/).
        """
        self._window_s = window_s
        self._mad_floor = mad_floor
        self._buffer: deque = deque()  # (timestamp, value)
        self._median: float = 0.0
        self._mad: float = 0.0
        self._initialized = False

    def update(self, timestamp: float, value: float) -> None:
        """Fügt einen neuen Wert hinzu und aktualisiert Statistik."""
        self._buffer.append((timestamp, value))

        # Alte Werte entfernen (außerhalb des Zeitfensters)
        cutoff = timestamp - self._window_s
        while self._buffer and self._buffer[0][0] < cutoff:
            self._buffer.popleft()

        # Statistik neu berechnen
        if len(self._buffer) >= 5:
            values = np.array([v for _, v in self._buffer])
            self._median = float(np.median(values))
            raw_mad = float(np.median(np.abs(values - self._median))) * 1.4826
            self._mad = max(raw_mad, self._mad_floor)
            self._initialized = True

    @property
    def median(self) -> float:
        return self._median

    @property
    def mad(self) -> float:
        return self._mad

    @property
    def is_initialized(self) -> bool:
        return self._initialized

    def set_initial(self, median: float, mad: float) -> None:
        """Setzt initiale Werte aus dem Kalibrierungsprofil."""
        self._median = median
        self._mad = max(mad, self._mad_floor)
        self._initialized = True

    @property
    def sample_count(self) -> int:
        return len(self._buffer)


class DualTimescaleBaseline:
    """Gated Dual-Timescale-Baseline (/LF410/).

    Die Detektion nutzt die langsame Baseline.
    Gating verhindert Kontamination durch aktive Signale.
    """

    # Zustände, in denen KEINE Baseline-Updates stattfinden
    _GATED_STATES = frozenset({
        DetectorState.RISING,
        DetectorState.HELD,
        DetectorState.CONFIRM,
        DetectorState.EMIT,
        DetectorState.REFRACTORY,
    })

    def __init__(
        self,
        slow_window_s: float = 120.0,
        fast_window_s: float = 5.0,
        mad_floor: float = 0.0,
    ):
        """
        Args:
            slow_window_s: Langsame Baseline-Fensterbreite (Minuten).
            fast_window_s: Schnelle Baseline-Fensterbreite (Sekunden).
            mad_floor: Minimaler MAD (/LF420/).
        """
        self._slow = RollingMedianMAD(slow_window_s, mad_floor)
        self._fast = RollingMedianMAD(fast_window_s, mad_floor)
        self._mad_floor = mad_floor
        self._current_state = DetectorState.IDLE

    def update(
        self,
        timestamp: float,
        value: float,
        detector_state: DetectorState,
    ) -> None:
        """Aktualisiert die Baseline (mit Gating).

        Args:
            timestamp: Capture-Zeitstempel.
            value: Aktueller Kanalwert.
            detector_state: Aktueller Zustand des Detektors.
        """
        self._current_state = detector_state

        # Gating: Kein Update während aktiver Signale
        if detector_state in self._GATED_STATES:
            return

        self._slow.update(timestamp, value)
        self._fast.update(timestamp, value)

    def set_initial(self, median: float, mad: float) -> None:
        """Setzt initiale Werte aus dem Kalibrierungsprofil."""
        self._slow.set_initial(median, mad)
        self._fast.set_initial(median, mad)

    @property
    def median(self) -> float:
        """Langsame Baseline (für Detektion)."""
        return self._slow.median

    @property
    def mad(self) -> float:
        """MAD der langsamen Baseline."""
        return self._slow.mad

    @property
    def fast_median(self) -> float:
        """Schnelle Baseline (für Licht-Anpassung)."""
        return self._fast.median

    @property
    def is_initialized(self) -> bool:
        return self._slow.is_initialized

    @property
    def threshold_up(self) -> float:
        """Oberer Schwellwert (Baseline + Delta). Wird vom Detektor genutzt."""
        # Delta wird extern gesetzt — hier nur Baseline bereitstellen
        return self._slow.median

    @property
    def threshold_down(self) -> float:
        """Unterer Schwellwert. Wird vom Detektor genutzt."""
        return self._slow.median
