"""Synthetische Tests für den Schmitt-Trigger-Detektor (/LF820/).

Testfälle:
- Tremor-Rauschen + 1 gehaltenes Signal ⇒ genau 1 Emission
- Reiner Tremor ⇒ 0 Emissionen
- Doppelpuls im Fenster ⇒ 2 Emissionen (raw), Pattern-Matcher → `double`
"""

import numpy as np
import pytest

from blickfang.calibration.profile import CalibrationProfile
from blickfang.core.events import ChannelFrame, DetectorState, EventType, QualityState
from blickfang.detection.baseline import DualTimescaleBaseline, RollingMedianMAD
from blickfang.detection.detector import SchmittTriggerDetector
from blickfang.temporal.patterns import PatternMatcher
from blickfang.core.config import PatternsConfig


def _make_profile(
    channel: str = "test_channel",
    baseline_median: float = 0.5,
    baseline_mad: float = 0.05,
    threshold_delta: float = 0.2,
    hold_time_s: float = 0.3,
    refractory_s: float = 0.5,
) -> CalibrationProfile:
    """Erstellt ein Test-Profil."""
    return CalibrationProfile(
        person_name="test",
        channel_name=channel,
        channel_direction=1,
        baseline_median=baseline_median,
        baseline_mad=baseline_mad,
        mad_floor=0.01,
        threshold_delta=threshold_delta,
        hold_time_s=hold_time_s,
        refractory_s=refractory_s,
    )


def _generate_tremor(
    duration_s: float = 10.0,
    fps: float = 30.0,
    baseline: float = 0.5,
    amplitude: float = 0.08,
    frequency_hz: float = 5.0,
    noise_std: float = 0.02,
    seed: int = 42,
) -> list:
    """Generiert synthetisches Tremor-Rauschen.

    Simuliert choreatische Bewegungsunruhe: schnelle, unregelmäßige
    Schwankungen um die Baseline.
    """
    rng = np.random.default_rng(seed)
    n_frames = int(duration_s * fps)
    timestamps = np.linspace(0, duration_s, n_frames)

    # Tremor: Sinusoide + Rauschen + gelegentliche Spikes
    tremor = (
        amplitude * np.sin(2 * np.pi * frequency_hz * timestamps)
        + noise_std * rng.standard_normal(n_frames)
        + amplitude * 0.5 * np.sin(2 * np.pi * frequency_hz * 1.7 * timestamps)
    )

    # Gelegentliche kurze Spikes (ballistisch, < 100ms)
    for _ in range(int(duration_s * 2)):  # ~2 Spikes/s
        spike_pos = rng.integers(0, n_frames)
        spike_width = rng.integers(1, 3)  # 1-3 Frames = 33-100ms
        spike_amp = rng.uniform(0.05, 0.12)
        end = min(spike_pos + spike_width, n_frames)
        tremor[spike_pos:end] += spike_amp

    values = baseline + tremor
    return [(timestamps[i], float(values[i])) for i in range(n_frames)]


def _generate_signal(
    start_s: float,
    duration_s: float = 0.8,
    fps: float = 30.0,
    baseline: float = 0.5,
    amplitude: float = 0.35,
) -> list:
    """Generiert ein willentliches, gehaltenes Signal.

    Langsamer Anstieg, Plateau, langsamer Abfall — typisch für
    willentliche Bewegung (vs. ballistischer Tremor).
    """
    n_frames = int(duration_s * fps)
    timestamps = np.linspace(start_s, start_s + duration_s, n_frames)

    # Glockenkurve (gehaltenes Signal)
    t_norm = np.linspace(0, 1, n_frames)
    signal = amplitude * np.sin(np.pi * t_norm)  # Halbe Sinuswelle

    values = baseline + signal
    return [(timestamps[i], float(values[i])) for i in range(n_frames)]


def _make_frames(data: list, channel: str = "test_channel") -> list:
    """Konvertiert (timestamp, value) Liste in ChannelFrames."""
    return [
        ChannelFrame(
            timestamp=ts,
            channels={channel: val},
            quality=QualityState.OK,
        )
        for ts, val in data
    ]


class TestSchmittTriggerDetector:
    """Tests für den Schmitt-Trigger-Detektor."""

    def test_pure_tremor_no_emission(self):
        """Reiner Tremor ⇒ 0 Emissionen (/LF820/)."""
        profile = _make_profile(threshold_delta=0.2, hold_time_s=0.3)
        detector = SchmittTriggerDetector(profile)

        # 10 Sekunden reines Tremor-Rauschen
        tremor_data = _generate_tremor(duration_s=10.0, amplitude=0.08)
        frames = _make_frames(tremor_data)

        emissions = []
        for frame in frames:
            event = detector.process(frame)
            if event is not None:
                emissions.append(event)

        assert len(emissions) == 0, (
            f"Reiner Tremor sollte 0 Emissionen erzeugen, "
            f"aber {len(emissions)} wurden emittiert"
        )

    def test_tremor_plus_one_signal_one_emission(self):
        """Tremor + 1 gehaltenes Signal ⇒ genau 1 Emission (/LF820/)."""
        profile = _make_profile(threshold_delta=0.2, hold_time_s=0.3)
        detector = SchmittTriggerDetector(profile)

        # Tremor vor dem Signal (5s)
        tremor_before = _generate_tremor(duration_s=5.0, amplitude=0.08, seed=42)

        # Gehaltenes Signal bei t=5s
        signal = _generate_signal(start_s=5.0, duration_s=0.8, amplitude=0.35)

        # Tremor nach dem Signal (5s)
        tremor_after = _generate_tremor(duration_s=5.0, amplitude=0.08, seed=99)
        # Zeitstempel anpassen
        tremor_after = [(ts + 5.8, val) for ts, val in tremor_after]

        all_data = tremor_before + signal + tremor_after
        all_data.sort(key=lambda x: x[0])
        frames = _make_frames(all_data)

        emissions = []
        for frame in frames:
            event = detector.process(frame)
            if event is not None:
                emissions.append(event)

        assert len(emissions) == 1, (
            f"Tremor + 1 Signal sollte genau 1 Emission erzeugen, "
            f"aber {len(emissions)} wurden emittiert"
        )

    def test_double_pulse_two_emissions(self):
        """Doppelpuls ⇒ 2 rohe Emissionen (/LF820/)."""
        profile = _make_profile(
            threshold_delta=0.2, hold_time_s=0.2, refractory_s=0.3
        )
        detector = SchmittTriggerDetector(profile)

        # Ruhephase (2s)
        rest1 = [(t / 30.0, 0.5) for t in range(60)]

        # Erster Puls bei t=2s
        signal1 = _generate_signal(start_s=2.0, duration_s=0.5, amplitude=0.35)

        # Kurze Pause (0.5s)
        pause = [(2.5 + t / 30.0, 0.5) for t in range(15)]

        # Zweiter Puls bei t=3.0s
        signal2 = _generate_signal(start_s=3.0, duration_s=0.5, amplitude=0.35)

        # Ruhephase (2s)
        rest2 = [(3.5 + t / 30.0, 0.5) for t in range(60)]

        all_data = rest1 + signal1 + pause + signal2 + rest2
        all_data.sort(key=lambda x: x[0])
        frames = _make_frames(all_data)

        emissions = []
        for frame in frames:
            event = detector.process(frame)
            if event is not None:
                emissions.append(event)

        assert len(emissions) == 2, (
            f"Doppelpuls sollte 2 Emissionen erzeugen, "
            f"aber {len(emissions)} wurden emittiert"
        )

    def test_double_pattern_matcher(self):
        """Doppelpuls + Pattern-Matcher ⇒ 1 DOUBLE-Event."""
        config = PatternsConfig(
            confirmation="double",
            double_window_s=2.0,
        )
        matcher = PatternMatcher(config)

        confirmed_events = []
        matcher.set_callback(lambda e: confirmed_events.append(e))

        # Zwei rohe Events im Zeitfenster simulieren
        from blickfang.core.events import SwitchEvent

        event1 = SwitchEvent(
            source_id="video_switch",
            event_type=EventType.SINGLE,
            timestamp_capture=1.0,
            confidence=0.8,
        )
        event2 = SwitchEvent(
            source_id="video_switch",
            event_type=EventType.SINGLE,
            timestamp_capture=1.8,  # Innerhalb von 2s
            confidence=0.9,
        )

        matcher.process_event(event1)
        result = matcher.process_event(event2)

        assert result is not None
        assert result.event_type == EventType.DOUBLE
        assert len(confirmed_events) == 1

    def test_quality_blocks_emission(self):
        """Bei schlechter Qualität keine Emission."""
        profile = _make_profile(threshold_delta=0.2, hold_time_s=0.2)
        detector = SchmittTriggerDetector(profile)

        # Signal über Schwellwert, aber Qualität LOST
        frames = [
            ChannelFrame(
                timestamp=t / 30.0,
                channels={"test_channel": 0.9},  # Weit über Schwelle
                quality=QualityState.LOST,
            )
            for t in range(30)
        ]

        emissions = []
        for frame in frames:
            event = detector.process(frame)
            if event is not None:
                emissions.append(event)

        assert len(emissions) == 0

    def test_refractory_prevents_rapid_fire(self):
        """Refraktärzeit verhindert Schnellfeuer."""
        profile = _make_profile(
            threshold_delta=0.15, hold_time_s=0.1, refractory_s=1.0
        )
        detector = SchmittTriggerDetector(profile)

        # Schnelle Signalfolge (alle 200ms)
        data = []
        for i in range(50):
            t = i * 0.2
            if i % 5 in (1, 2):  # Signal alle 1s für 400ms
                data.append((t, 0.9))
            else:
                data.append((t, 0.5))

        frames = _make_frames(data)
        emissions = []
        for frame in frames:
            event = detector.process(frame)
            if event is not None:
                emissions.append(event)

        # Bei 1s Refraktärzeit und 10s Gesamtdauer: max ~10 Emissionen
        # Aber wegen Haltezeit und Muster deutlich weniger
        assert len(emissions) <= 10


class TestDualTimescaleBaseline:
    """Tests für die Dual-Timescale-Baseline."""

    def test_gating_prevents_contamination(self):
        """Gating: Aktive Signale kontaminieren nicht die Baseline."""
        baseline = DualTimescaleBaseline(
            slow_window_s=10.0, fast_window_s=2.0, mad_floor=0.01
        )
        baseline.set_initial(0.5, 0.05)

        # Normale Werte einspeisen (IDLE)
        for i in range(100):
            baseline.update(i * 0.1, 0.5 + np.random.normal(0, 0.02),
                           DetectorState.IDLE)

        median_before = baseline.median

        # Hohe Werte während RISING/HELD (sollten ignoriert werden)
        for i in range(50):
            baseline.update(10.0 + i * 0.1, 2.0,  # Sehr hoher Wert
                           DetectorState.HELD)

        median_after = baseline.median

        # Baseline sollte sich kaum geändert haben
        assert abs(median_after - median_before) < 0.1, (
            f"Baseline wurde durch gated Samples kontaminiert: "
            f"{median_before:.3f} → {median_after:.3f}"
        )

    def test_mad_floor(self):
        """MAD-Floor verhindert Schwellwert-Kollaps (/LF420/)."""
        mad_floor = 0.05
        baseline = RollingMedianMAD(window_s=10.0, mad_floor=mad_floor)

        # Konstante Werte (MAD wäre 0)
        for i in range(100):
            baseline.update(i * 0.1, 0.5)

        assert baseline.mad >= mad_floor, (
            f"MAD {baseline.mad} ist unter Floor {mad_floor}"
        )


class TestRollingMedianMAD:
    """Tests für Rolling Median/MAD."""

    def test_basic_statistics(self):
        """Grundlegende Statistik-Berechnung."""
        rm = RollingMedianMAD(window_s=10.0, mad_floor=0.0)

        values = [1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0, 8.0, 9.0, 10.0]
        for i, v in enumerate(values):
            rm.update(float(i), v)

        assert rm.is_initialized
        assert abs(rm.median - 5.5) < 0.1

    def test_window_expiry(self):
        """Alte Werte fallen aus dem Fenster."""
        rm = RollingMedianMAD(window_s=5.0, mad_floor=0.0)

        # Erst niedrige Werte
        for i in range(50):
            rm.update(float(i) * 0.1, 1.0)

        # Dann hohe Werte (nach Fenster)
        for i in range(50):
            rm.update(5.0 + float(i) * 0.1, 10.0)

        # Median sollte bei ~10 liegen (alte Werte rausgefallen)
        assert rm.median > 5.0
