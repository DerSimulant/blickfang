"""Kanal-Ranking und -Auswahl (/LF300/, /LF330/–/LF350/).

Signaloffenheit: Die Kalibrierung wählt aus allen verfügbaren Kanälen
den/die trennschärfsten für die jeweilige Person aus.
Primäre Metrik: empirische False-Positive-Rate bei vorgegebener TP-Rate.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

import numpy as np

from blickfang.calibration.session import CalibrationRecording, SignalEvent

logger = logging.getLogger(__name__)


@dataclass
class ChannelScore:
    """Bewertung eines Kanals für die Signaltrennung."""

    channel_name: str
    fp_rate_at_90tp: float = 1.0       # FP-Rate bei 90% TP (primär, /LF330/)
    auc: float = 0.0                    # Area Under Curve (sekundär)
    signal_median: float = 0.0          # Median der Signal-Werte
    neutral_median: float = 0.0         # Median der Neutral-Werte
    neutral_mad: float = 0.0            # MAD der Neutral-Verteilung
    mad_floor: float = 0.0             # Minimale beobachtete Streuung (/LF331/)
    threshold_delta: float = 0.0        # Optimaler Schwellwert-Delta
    is_degenerate: bool = False         # Quasi-konstant (/LF331/)
    direction: int = 1                  # +1 = Signal über Baseline, -1 = darunter
    hold_variant_better: bool = False   # Gehaltenes Signal besser trennbar (/LF340/)


@dataclass
class ChannelRanking:
    """Ergebnis des Kanal-Rankings."""

    scores: List[ChannelScore] = field(default_factory=list)
    best_channel: Optional[str] = None
    best_score: Optional[ChannelScore] = None

    @property
    def ranked(self) -> List[ChannelScore]:
        """Kanäle sortiert nach FP-Rate (aufsteigend = besser)."""
        return sorted(self.scores, key=lambda s: s.fp_rate_at_90tp)


class ChannelSelector:
    """Wählt den besten Signalkanal aus (/LF300/).

    Methodik:
    - Für jeden Kanal: Verteilung der Signal-Werte vs. Neutral-Werte
    - Empirische FP-Rate bei vorgegebener TP-Rate (quantilbasiert)
    - Keine Normalverteilungsannahme (heavy-tailed Unruhe-Verteilungen)
    """

    def __init__(self, target_tp_rate: float = 0.9, mad_floor_factor: float = 0.01):
        """
        Args:
            target_tp_rate: Ziel-TP-Rate für FP-Berechnung.
            mad_floor_factor: Minimaler MAD als Anteil des Medians (/LF331/).
        """
        self._target_tp_rate = target_tp_rate
        self._mad_floor_factor = mad_floor_factor

    def rank_channels(
        self,
        recording: CalibrationRecording,
        confirmed_events: List[SignalEvent],
    ) -> ChannelRanking:
        """Bewertet und rankt alle Kanäle.

        Args:
            recording: Die Kalibrierungsaufzeichnung.
            confirmed_events: Vom Caregiver bestätigte Signal-Ereignisse.

        Returns:
            ChannelRanking mit bewerteten Kanälen.
        """
        if not confirmed_events or not recording.neutral_frames:
            logger.warning("Nicht genug Daten für Kanal-Ranking")
            return ChannelRanking()

        # Alle verfügbaren Kanäle sammeln
        channel_names = set()
        for frame in recording.neutral_frames:
            channel_names.update(frame.channels.keys())

        ranking = ChannelRanking()

        for channel in channel_names:
            score = self._evaluate_channel(
                channel, recording, confirmed_events
            )
            if score is not None:
                ranking.scores.append(score)

        # Besten Kanal bestimmen
        if ranking.scores:
            valid_scores = [s for s in ranking.scores if not s.is_degenerate]
            if valid_scores:
                ranking.scores = valid_scores
                best = min(valid_scores, key=lambda s: s.fp_rate_at_90tp)
                ranking.best_channel = best.channel_name
                ranking.best_score = best

        return ranking

    def _evaluate_channel(
        self,
        channel_name: str,
        recording: CalibrationRecording,
        confirmed_events: List[SignalEvent],
    ) -> Optional[ChannelScore]:
        """Bewertet einen einzelnen Kanal."""
        # Neutral-Verteilung sammeln
        neutral_values = []
        for frame in recording.neutral_frames:
            if channel_name in frame.channels:
                neutral_values.append(frame.channels[channel_name])

        if len(neutral_values) < 30:
            return None

        neutral_arr = np.array(neutral_values)
        neutral_median = float(np.median(neutral_arr))
        neutral_mad = float(np.median(np.abs(neutral_arr - neutral_median))) * 1.4826

        # Degenerationscheck (/LF331/)
        mad_floor = max(abs(neutral_median) * self._mad_floor_factor, 1e-6)
        if neutral_mad < mad_floor:
            score = ChannelScore(
                channel_name=channel_name,
                is_degenerate=True,
                neutral_median=neutral_median,
                neutral_mad=neutral_mad,
                mad_floor=mad_floor,
            )
            return score

        # Signal-Werte aus bestätigten Events extrahieren
        signal_values = self._extract_signal_values(
            channel_name, recording, confirmed_events
        )

        if len(signal_values) < 3:
            return None

        signal_arr = np.array(signal_values)
        signal_median = float(np.median(signal_arr))

        # Richtung bestimmen (Signal über oder unter Baseline?)
        direction = 1 if signal_median > neutral_median else -1

        # Empirische FP-Rate bei Ziel-TP-Rate (quantilbasiert, /LF330/)
        fp_rate, threshold_delta = self._compute_fp_at_tp(
            signal_arr, neutral_arr, neutral_median, direction
        )

        # AUC berechnen (Zweitmaß)
        auc = self._compute_auc(signal_arr, neutral_arr, direction)

        return ChannelScore(
            channel_name=channel_name,
            fp_rate_at_90tp=fp_rate,
            auc=auc,
            signal_median=signal_median,
            neutral_median=neutral_median,
            neutral_mad=neutral_mad,
            mad_floor=mad_floor,
            threshold_delta=threshold_delta,
            direction=direction,
        )

    def _extract_signal_values(
        self,
        channel_name: str,
        recording: CalibrationRecording,
        confirmed_events: List[SignalEvent],
    ) -> List[float]:
        """Extrahiert Kanalwerte an den Zeitpunkten bestätigter Events."""
        values = []
        for event in confirmed_events:
            if event.channel_name == channel_name:
                values.append(event.peak_value)
            else:
                # Suche den nächsten Frame zum Event-Zeitpunkt
                closest_value = self._find_closest_value(
                    channel_name, event.timestamp, recording.frames
                )
                if closest_value is not None:
                    values.append(closest_value)
        return values

    @staticmethod
    def _find_closest_value(
        channel_name: str, timestamp: float, frames
    ) -> Optional[float]:
        """Findet den Kanalwert am nächsten zum Zeitstempel."""
        best_diff = float("inf")
        best_value = None
        for frame in frames:
            if channel_name in frame.channels:
                diff = abs(frame.timestamp - timestamp)
                if diff < best_diff:
                    best_diff = diff
                    best_value = frame.channels[channel_name]
        return best_value

    def _compute_fp_at_tp(
        self,
        signal_values: np.ndarray,
        neutral_values: np.ndarray,
        neutral_median: float,
        direction: int,
    ) -> Tuple[float, float]:
        """Berechnet empirische FP-Rate bei Ziel-TP-Rate.

        Quantilbasiert — keine Normalverteilungsannahme (/LF330/).

        Returns:
            (fp_rate, threshold_delta)
        """
        # Schwellwert so wählen, dass target_tp_rate der Signale erkannt werden
        if direction == 1:
            # Signal über Baseline: Schwelle = Quantil der Signal-Verteilung
            threshold_quantile = 1.0 - self._target_tp_rate
            threshold = float(np.quantile(signal_values, threshold_quantile))
            # FP-Rate: Anteil der Neutral-Werte über diesem Schwellwert
            fp_rate = float(np.mean(neutral_values > threshold))
        else:
            # Signal unter Baseline
            threshold_quantile = self._target_tp_rate
            threshold = float(np.quantile(signal_values, threshold_quantile))
            fp_rate = float(np.mean(neutral_values < threshold))

        threshold_delta = abs(threshold - neutral_median)
        return fp_rate, threshold_delta

    @staticmethod
    def _compute_auc(
        signal_values: np.ndarray,
        neutral_values: np.ndarray,
        direction: int,
    ) -> float:
        """Berechnet AUC (Mann-Whitney U Statistik).

        AUC = P(signal > neutral) für direction=1.
        """
        if direction == -1:
            signal_values = -signal_values
            neutral_values = -neutral_values

        # Effiziente AUC-Berechnung
        n_signal = len(signal_values)
        n_neutral = len(neutral_values)

        if n_signal == 0 or n_neutral == 0:
            return 0.5

        count = 0
        for s in signal_values:
            count += np.sum(neutral_values < s)
            count += 0.5 * np.sum(neutral_values == s)

        auc = count / (n_signal * n_neutral)
        return float(auc)
