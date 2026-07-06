"""Selbst getaktete Kalibrierungssitzung (/LF310/–/LF320/).

Die Person erzeugt ihr Signal N-mal, wann sie will. Ereignisse werden per
Peak-Picking in großzügigen Fenstern gefunden. Keine festen Ansage-Zeitfenster.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Callable, Dict, List, Optional, Tuple

import numpy as np

from blickfang.core.config import CalibrationConfig
from blickfang.core.events import ChannelFrame

logger = logging.getLogger(__name__)


@dataclass
class SignalEvent:
    """Ein erkanntes Signal-Ereignis während der Kalibrierung."""

    timestamp: float
    channel_name: str
    peak_value: float
    window_start: float
    window_end: float
    confirmed: bool = False  # Vom Caregiver bestätigt (/LF311/)


@dataclass
class CalibrationRecording:
    """Aufzeichnung einer Kalibrierungssitzung."""

    # Alle ChannelFrames der Sitzung
    frames: List[ChannelFrame] = field(default_factory=list)

    # Signal-Phase: erkannte Peaks
    signal_events: List[SignalEvent] = field(default_factory=list)

    # Neutral-Phase: Frames der Ruhephase
    neutral_frames: List[ChannelFrame] = field(default_factory=list)

    # Metadaten
    start_time: float = 0.0
    end_time: float = 0.0
    phase: str = "idle"  # idle | signal | neutral | validation


class PeakPicker:
    """Peak-Picking in großzügigen Fenstern (/LF310/).

    Findet Signal-Ereignisse ohne feste Zeitfenster — die Person bestimmt
    das Tempo selbst.
    """

    def __init__(self, config: CalibrationConfig):
        self._window_s = config.peak_window_s
        self._min_prominence = 0.0  # Wird dynamisch bestimmt

    def find_peaks(
        self,
        timestamps: np.ndarray,
        values: np.ndarray,
        baseline_median: float,
        baseline_mad: float,
    ) -> List[Tuple[int, float]]:
        """Findet Peaks in einer Zeitreihe.

        Args:
            timestamps: Zeitstempel-Array.
            values: Kanalwert-Array.
            baseline_median: Median der Baseline.
            baseline_mad: MAD der Baseline.

        Returns:
            Liste von (Index, Peak-Wert) Tupeln.
        """
        if len(values) < 3:
            return []

        # Minimale Prominenz: 3 * MAD über Baseline
        min_prominence = max(baseline_mad * 3.0, 0.01)

        peaks = []
        i = 1
        while i < len(values) - 1:
            # Einfaches Peak-Kriterium: lokales Maximum über Schwelle
            if (values[i] > values[i - 1] and
                values[i] >= values[i + 1] and
                values[i] - baseline_median > min_prominence):

                # Prüfe ob Peak im Zeitfenster isoliert ist
                peak_time = timestamps[i]
                is_isolated = True
                for prev_idx, _ in peaks:
                    if abs(timestamps[prev_idx] - peak_time) < self._window_s:
                        # Behalte den höheren Peak
                        if values[i] > values[prev_idx]:
                            peaks = [(idx, v) for idx, v in peaks
                                     if abs(timestamps[idx] - peak_time) >= self._window_s]
                            peaks.append((i, float(values[i])))
                        is_isolated = False
                        break

                if is_isolated:
                    peaks.append((i, float(values[i])))

            i += 1

        return peaks


class CalibrationSession:
    """Steuert den Ablauf einer Kalibrierungssitzung.

    Phasen:
    1. Signal-Aufnahme: Person erzeugt Signal N-mal (selbst getaktet)
    2. Neutral-Aufnahme: Ruhephase (bei Unruhe: 3–5 min)
    3. Validierung: 10 Signale + 2 min Ruhe (/LF360/)
    """

    def __init__(self, config: CalibrationConfig):
        self._config = config
        self._recording = CalibrationRecording()
        self._peak_picker = PeakPicker(config)
        self._phase = "idle"
        self._signal_count_target = config.signal_count
        self._on_event_callback: Optional[Callable[[SignalEvent], None]] = None

    @property
    def recording(self) -> CalibrationRecording:
        return self._recording

    @property
    def phase(self) -> str:
        return self._phase

    def set_event_callback(self, callback: Callable[[SignalEvent], None]) -> None:
        """Setzt Callback für erkannte Signal-Ereignisse (/LF311/)."""
        self._on_event_callback = callback

    def start_signal_phase(self) -> None:
        """Startet die Signal-Aufnahmephase."""
        self._phase = "signal"
        self._recording.phase = "signal"
        self._recording.start_time = 0.0  # Wird beim ersten Frame gesetzt
        logger.info("Kalibrierung: Signal-Phase gestartet")

    def start_neutral_phase(self) -> None:
        """Startet die Neutral-/Ruhephase (/LF320/)."""
        self._phase = "neutral"
        self._recording.phase = "neutral"
        logger.info(
            f"Kalibrierung: Neutral-Phase gestartet "
            f"(Dauer: {self._config.neutral_duration_s}s)"
        )

    def start_validation_phase(self) -> None:
        """Startet die Validierungsrunde (/LF360/)."""
        self._phase = "validation"
        self._recording.phase = "validation"
        logger.info("Kalibrierung: Validierungs-Phase gestartet")

    def add_frame(self, frame: ChannelFrame) -> None:
        """Fügt einen Frame zur Aufzeichnung hinzu."""
        if self._recording.start_time == 0.0:
            self._recording.start_time = frame.timestamp

        self._recording.frames.append(frame)

        if self._phase == "neutral":
            self._recording.neutral_frames.append(frame)

    def finalize_signal_phase(self) -> List[SignalEvent]:
        """Finalisiert die Signal-Phase und findet Peaks.

        Returns:
            Liste der erkannten Signal-Ereignisse.
        """
        if not self._recording.frames:
            return []

        # Für jeden Kanal Peaks finden
        all_events: List[SignalEvent] = []
        channel_names = set()
        for frame in self._recording.frames:
            channel_names.update(frame.channels.keys())

        for channel in channel_names:
            timestamps = []
            values = []
            for frame in self._recording.frames:
                if channel in frame.channels:
                    timestamps.append(frame.timestamp)
                    values.append(frame.channels[channel])

            if len(values) < 10:
                continue

            ts_arr = np.array(timestamps)
            val_arr = np.array(values)

            # Baseline aus den Daten schätzen (Median/MAD)
            median = float(np.median(val_arr))
            mad = float(np.median(np.abs(val_arr - median))) * 1.4826

            if mad < 1e-6:
                continue

            peaks = self._peak_picker.find_peaks(ts_arr, val_arr, median, mad)

            for idx, peak_val in peaks:
                event = SignalEvent(
                    timestamp=timestamps[idx],
                    channel_name=channel,
                    peak_value=peak_val,
                    window_start=max(timestamps[0], timestamps[idx] - self._config.peak_window_s / 2),
                    window_end=min(timestamps[-1], timestamps[idx] + self._config.peak_window_s / 2),
                )
                all_events.append(event)

                if self._on_event_callback:
                    self._on_event_callback(event)

        self._recording.signal_events = all_events
        return all_events

    def confirm_event(self, event: SignalEvent) -> None:
        """Caregiver bestätigt ein Signal-Ereignis (/LF311/)."""
        event.confirmed = True

    def reject_event(self, event: SignalEvent) -> None:
        """Caregiver lehnt ein Signal-Ereignis ab."""
        event.confirmed = False

    @property
    def confirmed_events(self) -> List[SignalEvent]:
        """Alle bestätigten Signal-Ereignisse."""
        return [e for e in self._recording.signal_events if e.confirmed]

    @property
    def neutral_duration_reached(self) -> bool:
        """Prüft ob die Neutral-Phase lang genug war."""
        if not self._recording.neutral_frames:
            return False
        duration = (
            self._recording.neutral_frames[-1].timestamp -
            self._recording.neutral_frames[0].timestamp
        )
        return duration >= self._config.neutral_duration_s

    def get_channel_timeseries(
        self, channel_name: str, phase: str = "signal"
    ) -> Tuple[np.ndarray, np.ndarray]:
        """Gibt Zeitreihe eines Kanals für eine Phase zurück.

        Returns:
            (timestamps, values) Arrays.
        """
        frames = (
            self._recording.neutral_frames if phase == "neutral"
            else self._recording.frames
        )

        timestamps = []
        values = []
        for frame in frames:
            if channel_name in frame.channels:
                timestamps.append(frame.timestamp)
                values.append(frame.channels[channel_name])

        return np.array(timestamps), np.array(values)
