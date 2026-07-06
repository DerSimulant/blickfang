"""Tests für das Kalibrierungsmodul."""

import tempfile
from pathlib import Path

import numpy as np
import pytest

from blickfang.calibration.profile import (
    CalibrationProfile,
    QuickTrim,
    ValidationResult,
    list_profiles,
)
from blickfang.calibration.selector import ChannelSelector
from blickfang.calibration.session import CalibrationSession, PeakPicker
from blickfang.core.config import CalibrationConfig
from blickfang.core.events import ChannelFrame, QualityState


class TestPeakPicker:
    """Tests für Peak-Picking."""

    def test_finds_clear_peaks(self):
        """Findet eindeutige Peaks."""
        config = CalibrationConfig(peak_window_s=2.0)
        picker = PeakPicker(config)

        # Zeitreihe mit 3 klaren Peaks
        n = 300
        timestamps = np.linspace(0, 10, n)
        values = np.ones(n) * 0.5

        # Peaks bei t=2, t=5, t=8
        for peak_t in [2.0, 5.0, 8.0]:
            idx = int(peak_t / 10.0 * n)
            values[idx - 2:idx + 3] += 0.5  # Breiter Peak

        baseline_median = 0.5
        baseline_mad = 0.05

        peaks = picker.find_peaks(timestamps, values, baseline_median, baseline_mad)

        assert len(peaks) >= 2, f"Erwartet >= 2 Peaks, gefunden: {len(peaks)}"

    def test_ignores_noise(self):
        """Ignoriert Rauschen unter Prominenz-Schwelle."""
        config = CalibrationConfig(peak_window_s=2.0)
        picker = PeakPicker(config)

        n = 300
        timestamps = np.linspace(0, 10, n)
        rng = np.random.default_rng(42)
        values = 0.5 + rng.normal(0, 0.02, n)  # Nur Rauschen

        peaks = picker.find_peaks(timestamps, values, 0.5, 0.03)

        assert len(peaks) == 0, f"Rauschen sollte keine Peaks erzeugen: {len(peaks)}"


class TestChannelSelector:
    """Tests für Kanal-Ranking."""

    def test_selects_best_channel(self):
        """Wählt den Kanal mit bester Trennung."""
        from blickfang.calibration.session import CalibrationRecording, SignalEvent

        selector = ChannelSelector()

        # Simuliere Aufzeichnung mit 2 Kanälen
        recording = CalibrationRecording()

        # Neutral-Frames: Kanal A ruhig, Kanal B unruhig
        rng = np.random.default_rng(42)
        for i in range(200):
            t = i * 0.033
            frame = ChannelFrame(
                timestamp=t,
                channels={
                    "channel_a": 0.5 + rng.normal(0, 0.02),  # Ruhig
                    "channel_b": 0.5 + rng.normal(0, 0.15),  # Unruhig
                },
                quality=QualityState.OK,
            )
            recording.neutral_frames.append(frame)
            recording.frames.append(frame)

        # Signal-Events: beide Kanäle reagieren, aber A deutlicher
        events = []
        for i in range(10):
            event = SignalEvent(
                timestamp=7.0 + i * 0.5,
                channel_name="channel_a",
                peak_value=0.9,  # Deutlich über Baseline
                window_start=6.5 + i * 0.5,
                window_end=7.5 + i * 0.5,
                confirmed=True,
            )
            events.append(event)

        ranking = selector.rank_channels(recording, events)

        assert ranking.best_channel is not None
        # Kanal A sollte besser sein (weniger Rauschen → niedrigere FP-Rate)
        assert ranking.best_channel == "channel_a", (
            f"Erwartet channel_a als bester Kanal, aber: {ranking.best_channel}"
        )

    def test_degenerate_channel_disqualified(self):
        """Quasi-konstante Kanäle werden disqualifiziert (/LF331/)."""
        from blickfang.calibration.session import CalibrationRecording, SignalEvent

        selector = ChannelSelector()

        recording = CalibrationRecording()

        # Kanal mit quasi-konstanten Werten
        for i in range(200):
            frame = ChannelFrame(
                timestamp=i * 0.033,
                channels={"constant_channel": 0.5},  # Exakt konstant
                quality=QualityState.OK,
            )
            recording.neutral_frames.append(frame)
            recording.frames.append(frame)

        events = [
            SignalEvent(
                timestamp=7.0, channel_name="constant_channel",
                peak_value=0.5, window_start=6.5, window_end=7.5,
                confirmed=True,
            )
        ]

        ranking = selector.rank_channels(recording, events)

        # Konstanter Kanal sollte als degeneriert markiert sein
        # (wird aus dem Ranking entfernt)
        assert ranking.best_channel is None or ranking.best_channel != "constant_channel"


class TestCalibrationProfile:
    """Tests für Profil-Verwaltung."""

    def test_save_and_load(self):
        """Profil speichern und laden."""
        with tempfile.TemporaryDirectory() as tmpdir:
            profile = CalibrationProfile(
                person_name="test_person",
                channel_name="ear_left",
                channel_direction=1,
                baseline_median=0.3,
                baseline_mad=0.05,
                mad_floor=0.01,
                threshold_delta=0.15,
                hold_time_s=0.4,
                refractory_s=1.0,
                confirmation_pattern="single",
                blocked_regions=["mouth"],
                validation=ValidationResult(
                    tp_rate=0.95,
                    fp_per_min=0.3,
                    signals_tested=10,
                    signals_detected=9,
                ),
            )

            filepath = profile.save(Path(tmpdir))
            assert filepath.exists()

            # Laden
            loaded = CalibrationProfile.load(filepath)
            assert loaded.person_name == "test_person"
            assert loaded.channel_name == "ear_left"
            assert loaded.baseline_median == 0.3
            assert loaded.threshold_delta == 0.15
            assert loaded.blocked_regions == ["mouth"]
            assert loaded.validation.tp_rate == 0.95

    def test_version_increment(self):
        """Profil-Versionierung (/LF370/)."""
        with tempfile.TemporaryDirectory() as tmpdir:
            profile = CalibrationProfile(
                person_name="test", channel_name="ear_left"
            )

            path1 = profile.save(Path(tmpdir))
            path2 = profile.save(Path(tmpdir))

            assert path1 != path2
            assert "v1" in path1.stem or "v2" in path2.stem


class TestQuickTrim:
    """Tests für Schnell-Trim (/LF380/)."""

    def test_trim_updates_baseline(self):
        """Trim aktualisiert Baseline-Statistik."""
        profile = CalibrationProfile(
            person_name="test",
            channel_name="ear_left",
            baseline_median=0.3,
            baseline_mad=0.05,
            mad_floor=0.01,
        )

        trim = QuickTrim(profile)

        # Neue Neutral-Werte (leicht verschoben)
        rng = np.random.default_rng(42)
        for _ in range(100):
            trim.add_neutral_sample(0.35 + rng.normal(0, 0.04))

        updated = trim.apply()

        assert abs(updated.baseline_median - 0.35) < 0.05
        assert updated.version == 2

    def test_trim_respects_mad_floor(self):
        """Trim respektiert MAD-Floor (/LF420/)."""
        profile = CalibrationProfile(
            person_name="test",
            channel_name="ear_left",
            baseline_median=0.3,
            baseline_mad=0.05,
            mad_floor=0.03,
        )

        trim = QuickTrim(profile)

        # Quasi-konstante Werte (MAD wäre ~0)
        for _ in range(100):
            trim.add_neutral_sample(0.3)

        updated = trim.apply()

        assert updated.baseline_mad >= 0.03, (
            f"MAD {updated.baseline_mad} unter Floor 0.03"
        )
