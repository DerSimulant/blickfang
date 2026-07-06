"""Ermüdungs-Monitoring (/LF740/).

Online-Beobachtung von Trennschärfe und TP-Latenz.
Bei Degradation wird ein Pausen-Hinweis gegeben.
"""

from __future__ import annotations

import logging
import time
from collections import deque
from dataclasses import dataclass, field
from typing import Callable, List, Optional

logger = logging.getLogger(__name__)


@dataclass
class FatigueMetrics:
    """Aktuelle Ermüdungs-Metriken."""
    session_duration_s: float = 0.0
    signals_total: int = 0
    signals_last_5min: int = 0
    mean_latency_s: float = 0.0
    latency_trend: float = 0.0          # Positiv = wird langsamer
    fp_rate_last_5min: float = 0.0
    fatigue_level: str = "normal"       # normal | leicht | deutlich | kritisch
    pause_recommended: bool = False


class FatigueMonitor:
    """Überwacht Ermüdungsanzeichen während der Kommunikation.

    Indikatoren für Ermüdung:
    - Steigende Latenz (Signal wird langsamer erzeugt)
    - Sinkende Signal-Rate (weniger Kommunikation)
    - Steigende FP-Rate (Signal wird unschärfer)
    """

    def __init__(
        self,
        pause_threshold_min: float = 30.0,
        latency_increase_threshold: float = 0.5,
        on_pause_hint: Optional[Callable[[], None]] = None,
    ):
        self._start_time = time.perf_counter()
        self._pause_threshold_s = pause_threshold_min * 60
        self._latency_threshold = latency_increase_threshold
        self._on_pause_hint = on_pause_hint

        # Zeitstempel der Signale (für Rate-Berechnung)
        self._signal_times: deque = deque(maxlen=100)
        # Latenzen (Zeit von Scan-Start bis Signal)
        self._latencies: deque = deque(maxlen=50)
        # FP-Zeitstempel
        self._fp_times: deque = deque(maxlen=50)

        self._pause_given = False
        self._last_check_time = 0.0

    def record_signal(self, latency_s: float = 0.0) -> None:
        """Registriert ein erfolgreiches Signal.

        Args:
            latency_s: Zeit vom Scan-Highlight bis zum Signal.
        """
        now = time.perf_counter()
        self._signal_times.append(now)
        if latency_s > 0:
            self._latencies.append((now, latency_s))

    def record_false_positive(self) -> None:
        """Registriert eine Fehlauslösung."""
        self._fp_times.append(time.perf_counter())

    def get_metrics(self) -> FatigueMetrics:
        """Berechnet aktuelle Ermüdungs-Metriken."""
        now = time.perf_counter()
        metrics = FatigueMetrics()

        metrics.session_duration_s = now - self._start_time
        metrics.signals_total = len(self._signal_times)

        # Signale in den letzten 5 Minuten
        cutoff_5min = now - 300
        metrics.signals_last_5min = sum(
            1 for t in self._signal_times if t >= cutoff_5min
        )

        # Mittlere Latenz (letzte 10 Signale)
        recent_latencies = [l for t, l in self._latencies if t >= cutoff_5min]
        if recent_latencies:
            metrics.mean_latency_s = sum(recent_latencies) / len(recent_latencies)

        # Latenz-Trend (Vergleich erste vs. letzte Hälfte)
        if len(self._latencies) >= 10:
            all_lats = [l for _, l in self._latencies]
            mid = len(all_lats) // 2
            first_half = sum(all_lats[:mid]) / mid
            second_half = sum(all_lats[mid:]) / (len(all_lats) - mid)
            metrics.latency_trend = second_half - first_half

        # FP-Rate in letzten 5 Minuten
        recent_fps = sum(1 for t in self._fp_times if t >= cutoff_5min)
        metrics.fp_rate_last_5min = recent_fps / 5.0  # pro Minute

        # Ermüdungslevel bestimmen
        metrics.fatigue_level = self._assess_fatigue(metrics)
        metrics.pause_recommended = metrics.fatigue_level in ("deutlich", "kritisch")

        return metrics

    def check(self) -> Optional[str]:
        """Prüft ob ein Pausen-Hinweis nötig ist.

        Returns:
            Hinweis-Text oder None.
        """
        now = time.perf_counter()

        # Nicht öfter als alle 60s prüfen
        if now - self._last_check_time < 60:
            return None
        self._last_check_time = now

        metrics = self.get_metrics()

        if metrics.pause_recommended and not self._pause_given:
            self._pause_given = True
            hint = self._get_pause_hint(metrics)
            if self._on_pause_hint:
                self._on_pause_hint()
            logger.info(f"Ermüdungs-Hinweis: {hint}")
            return hint

        # Nach Pause den Hinweis zurücksetzen
        if not metrics.pause_recommended:
            self._pause_given = False

        return None

    def _assess_fatigue(self, metrics: FatigueMetrics) -> str:
        """Bewertet das Ermüdungslevel."""
        score = 0

        # Sitzungsdauer
        if metrics.session_duration_s > self._pause_threshold_s:
            score += 1
        if metrics.session_duration_s > self._pause_threshold_s * 2:
            score += 1

        # Latenz-Anstieg
        if metrics.latency_trend > self._latency_threshold:
            score += 1
        if metrics.latency_trend > self._latency_threshold * 2:
            score += 1

        # FP-Rate
        if metrics.fp_rate_last_5min > 1.0:
            score += 1
        if metrics.fp_rate_last_5min > 2.0:
            score += 1

        if score >= 4:
            return "kritisch"
        elif score >= 3:
            return "deutlich"
        elif score >= 1:
            return "leicht"
        return "normal"

    def _get_pause_hint(self, metrics: FatigueMetrics) -> str:
        """Generiert einen passenden Pausen-Hinweis."""
        duration_min = metrics.session_duration_s / 60

        if metrics.fatigue_level == "kritisch":
            return (
                f"Sitzung läuft seit {duration_min:.0f} Minuten. "
                f"Deutliche Ermüdungszeichen erkannt. "
                f"Bitte eine Pause einlegen."
            )
        else:
            return (
                f"Sitzung läuft seit {duration_min:.0f} Minuten. "
                f"Eine kurze Pause könnte helfen."
            )

    def reset(self) -> None:
        """Setzt den Monitor zurück (z.B. nach Pause)."""
        self._start_time = time.perf_counter()
        self._signal_times.clear()
        self._latencies.clear()
        self._fp_times.clear()
        self._pause_given = False
