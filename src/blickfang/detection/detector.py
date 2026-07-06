"""Schmitt-Trigger-Zustandsautomat (/LF400/).

Zustände: IDLE → RISING → HELD → CONFIRM → EMIT → REFRACTORY

Alle Zeitparameter in Sekunden, nie in Frames (FPS variieren je Rechner).
Hysterese: getrennte Ein-/Aus-Schwellen.
"""

from __future__ import annotations

import logging
import time
from typing import Optional

from blickfang.calibration.profile import CalibrationProfile
from blickfang.core.events import (
    ChannelFrame,
    DetectorState,
    EventType,
    QualityState,
    SwitchEvent,
)
from blickfang.detection.baseline import DualTimescaleBaseline

logger = logging.getLogger(__name__)


class SchmittTriggerDetector:
    """Schmitt-Trigger-Zustandsautomat für Signaldetektion.

    Referenz: /LF400/ — IDLE → RISING → HELD → CONFIRM → EMIT → REFRACTORY.
    """

    def __init__(self, profile: CalibrationProfile):
        """
        Args:
            profile: Kalibrierungsprofil mit Kanal und Schwellwerten.
        """
        self._profile = profile
        self._channel = profile.channel_name
        self._direction = profile.channel_direction

        # Zeitparameter (Sekunden!)
        self._hold_time_s = profile.hold_time_s
        self._refractory_s = profile.refractory_s
        self._hysteresis_factor = profile.hysteresis_factor

        # Schwellwert-Delta (relativ zur Baseline, /LF430/)
        self._threshold_delta = profile.threshold_delta

        # Baseline
        self._baseline = DualTimescaleBaseline(
            slow_window_s=120.0,
            fast_window_s=5.0,
            mad_floor=profile.mad_floor,
        )
        self._baseline.set_initial(profile.baseline_median, profile.baseline_mad)

        # Zustand
        self._state = DetectorState.IDLE
        self._state_enter_time: float = 0.0
        self._rising_start_time: float = 0.0

        # Statistik für /LF710/
        self._total_time_s: float = 0.0
        self._emission_count: int = 0
        self._start_time: float = 0.0

    @property
    def state(self) -> DetectorState:
        return self._state

    @property
    def baseline(self) -> DualTimescaleBaseline:
        return self._baseline

    @property
    def threshold_on(self) -> float:
        """Ein-Schwelle (Baseline + Delta)."""
        if self._direction == 1:
            return self._baseline.median + self._threshold_delta
        else:
            return self._baseline.median - self._threshold_delta

    @property
    def threshold_off(self) -> float:
        """Aus-Schwelle (mit Hysterese)."""
        hysteresis = self._threshold_delta * self._hysteresis_factor
        if self._direction == 1:
            return self._baseline.median + self._threshold_delta - hysteresis
        else:
            return self._baseline.median - self._threshold_delta + hysteresis

    @property
    def expected_fp_per_min(self) -> float:
        """Erwartete Zufalls-Auslösungsrate (/LF710/).

        Berechnet aus der aktuellen Baseline-Statistik und dem Schwellwert.
        """
        if not self._baseline.is_initialized or self._baseline.mad < 1e-6:
            return 0.0

        # Z-Score des Schwellwerts relativ zur Baseline
        z = self._threshold_delta / self._baseline.mad

        # Vereinfachte Schätzung: Annahme Gauss für Anzeigezweck
        # P(X > threshold) ≈ erfc(z/sqrt(2))/2
        import math
        p_exceed = 0.5 * math.erfc(z / math.sqrt(2))

        # Annahme: ~15 unabhängige Samples pro Sekunde
        samples_per_min = 15 * 60
        expected_exceedances = p_exceed * samples_per_min

        # Berücksichtige Haltezeit (reduziert effektive FP)
        if self._hold_time_s > 0:
            # Nur Cluster, die lang genug sind, zählen
            expected_exceedances *= max(0.1, 1.0 - self._hold_time_s * 2)

        return expected_exceedances

    def process(self, frame: ChannelFrame) -> Optional[SwitchEvent]:
        """Verarbeitet einen ChannelFrame und gibt ggf. ein SwitchEvent aus.

        Args:
            frame: Aktueller ChannelFrame.

        Returns:
            SwitchEvent wenn ein Signal emittiert wird, sonst None.
        """
        # Initialisierung
        if self._start_time == 0.0:
            self._start_time = frame.timestamp

        # Qualitätsprüfung: bei nicht-OK keine Emission
        if not frame.is_valid:
            # Baseline trotzdem nicht updaten bei schlechter Qualität
            return None

        # Kanalwert holen
        if self._channel not in frame.channels:
            return None

        value = frame.channels[self._channel]
        now = frame.timestamp

        # Baseline updaten (mit Gating)
        self._baseline.update(now, value, self._state)

        # Schwellwert-Vergleich (richtungsabhängig)
        is_above_on = self._is_above_threshold(value, self.threshold_on)
        is_above_off = self._is_above_threshold(value, self.threshold_off)

        # Zustandsautomat
        event = self._update_state(now, value, is_above_on, is_above_off)

        # Gesamtzeit für FP-Statistik
        self._total_time_s = now - self._start_time

        return event

    def _is_above_threshold(self, value: float, threshold: float) -> bool:
        """Prüft ob der Wert über dem Schwellwert liegt (richtungsabhängig)."""
        if self._direction == 1:
            return value > threshold
        else:
            return value < threshold

    def _update_state(
        self,
        now: float,
        value: float,
        is_above_on: bool,
        is_above_off: bool,
    ) -> Optional[SwitchEvent]:
        """Zustandsübergänge des Schmitt-Trigger-Automaten."""
        event = None

        if self._state == DetectorState.IDLE:
            if is_above_on:
                self._transition(DetectorState.RISING, now)

        elif self._state == DetectorState.RISING:
            if not is_above_off:
                # Signal zu kurz — zurück zu IDLE
                self._transition(DetectorState.IDLE, now)
            elif now - self._state_enter_time >= self._hold_time_s:
                # Haltezeit erreicht → HELD
                self._transition(DetectorState.HELD, now)

        elif self._state == DetectorState.HELD:
            if not is_above_off:
                # Signal beendet → CONFIRM
                self._transition(DetectorState.CONFIRM, now)
            # Bleibt in HELD solange Signal gehalten wird

        elif self._state == DetectorState.CONFIRM:
            # Sofortige Emission (Bestätigungslogik in temporal/patterns.py)
            event = SwitchEvent(
                source_id="video_switch",
                event_type=EventType.SINGLE,
                timestamp_capture=self._rising_start_time,
                confidence=self._compute_confidence(value),
                channel_name=self._channel,
            )
            self._emission_count += 1
            self._transition(DetectorState.EMIT, now)

        elif self._state == DetectorState.EMIT:
            # Sofort in Refraktärphase
            self._transition(DetectorState.REFRACTORY, now)

        elif self._state == DetectorState.REFRACTORY:
            if now - self._state_enter_time >= self._refractory_s:
                self._transition(DetectorState.IDLE, now)

        return event

    def _transition(self, new_state: DetectorState, now: float) -> None:
        """Zustandsübergang."""
        old_state = self._state
        self._state = new_state
        self._state_enter_time = now

        if new_state == DetectorState.RISING:
            self._rising_start_time = now

        logger.debug(f"Detektor: {old_state.name} → {new_state.name}")

    def _compute_confidence(self, value: float) -> float:
        """Berechnet Konfidenz basierend auf Signal-Stärke."""
        if self._baseline.mad < 1e-6:
            return 1.0

        # Z-Score als Konfidenz-Proxy
        z = abs(value - self._baseline.median) / self._baseline.mad
        # Sigmoid-artige Normierung auf [0, 1]
        confidence = min(1.0, z / 5.0)
        return confidence

    def reset(self) -> None:
        """Setzt den Detektor zurück."""
        self._state = DetectorState.IDLE
        self._state_enter_time = 0.0
