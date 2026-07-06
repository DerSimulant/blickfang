"""Tests für die neuen Tools: record, annotate, validate."""

import json
import sys
import tempfile
from pathlib import Path
from unittest.mock import MagicMock

import numpy as np
import pytest
import yaml

# Mock tkinter before importing modules that use it
sys.modules.setdefault("tkinter", MagicMock())
sys.modules.setdefault("tkinter.ttk", MagicMock())
sys.modules.setdefault("tkinter.font", MagicMock())
sys.modules.setdefault("tkinter.messagebox", MagicMock())
sys.modules.setdefault("tkinter.simpledialog", MagicMock())

from blickfang.app.annotate import AnnotationStore, FeatureTimeline, Segment
from blickfang.app.validate import BatchValidator, SessionValidator, ValidationMetrics
from blickfang.calibration.profile import CalibrationProfile
from blickfang.core.events import ChannelFrame, QualityState


def _create_test_session(tmpdir: Path, person: str = "test",
                         label: str = "signal") -> Path:
    """Erstellt eine Test-Session mit Feature-Stream und Annotationen."""
    session_dir = tmpdir / f"{person}_20260706_120000_{label}"
    session_dir.mkdir(parents=True)

    # Feature-Stream erstellen
    features_path = session_dir / "features.jsonl"
    rng = np.random.default_rng(42)

    with open(features_path, "w") as f:
        # Header
        f.write(json.dumps({"type": "recording_start", "person": person}) + "\n")

        # 10 Sekunden Frames @ 30 FPS
        for i in range(300):
            t = i / 30.0
            # Baseline-Wert mit Rauschen
            base_val = 0.3 + rng.normal(0, 0.02)

            # Signal bei t=3-4s und t=7-8s
            if 3.0 <= t <= 4.0 or 7.0 <= t <= 8.0:
                base_val += 0.3  # Deutliches Signal

            frame_data = {
                "type": "channel_frame",
                "timestamp": t + 1000.0,  # Absolute time
                "relative_time_s": t,
                "channels": {"ear_left": base_val, "brow_left": 0.15 + rng.normal(0, 0.01)},
                "quality": "OK",
                "fps": 30.0,
                "face_detected": True,
            }
            f.write(json.dumps(frame_data) + "\n")

        # Footer
        f.write(json.dumps({"type": "recording_end", "frames": 300, "duration_s": 10.0}) + "\n")

    # Annotationen erstellen
    annotations = {
        "person": person,
        "session": session_dir.name,
        "segments": [
            {"start_s": 3.0, "end_s": 4.0, "label": "signal", "channel": "ear_left", "confidence": 1.0, "note": ""},
            {"start_s": 7.0, "end_s": 8.0, "label": "signal", "channel": "ear_left", "confidence": 1.0, "note": ""},
            {"start_s": 0.0, "end_s": 3.0, "label": "ruhe", "channel": None, "confidence": 1.0, "note": ""},
            {"start_s": 4.0, "end_s": 7.0, "label": "ruhe", "channel": None, "confidence": 1.0, "note": ""},
        ],
    }
    with open(session_dir / "annotations.yaml", "w") as f:
        yaml.dump(annotations, f)

    # Meta
    meta = {"person": person, "label": label, "duration_s": 10.0, "frames": 300}
    with open(session_dir / "meta.yaml", "w") as f:
        yaml.dump(meta, f)

    return session_dir


class TestAnnotationStore:
    """Tests für das Annotations-Modul."""

    def test_add_and_save_segments(self):
        """Segmente hinzufügen und speichern."""
        with tempfile.TemporaryDirectory() as tmpdir:
            session_dir = _create_test_session(Path(tmpdir))
            store = AnnotationStore(session_dir)

            # Bestehende Segmente geladen
            assert len(store.segments) == 4

            # Neues Segment hinzufügen
            store.add_segment(Segment(
                start_s=9.0, end_s=10.0, label="unruhe", channel="ear_left"
            ))
            assert len(store.segments) == 5

            # Speichern
            store.save()

            # Neu laden und prüfen
            store2 = AnnotationStore(session_dir)
            assert len(store2.segments) == 5

    def test_undo(self):
        """Letzte Annotation rückgängig machen."""
        with tempfile.TemporaryDirectory() as tmpdir:
            session_dir = _create_test_session(Path(tmpdir))
            store = AnnotationStore(session_dir)

            initial_count = len(store.segments)
            removed = store.remove_last()
            assert removed is not None
            assert len(store.segments) == initial_count - 1


class TestFeatureTimeline:
    """Tests für das Feature-Timeline-Modul."""

    def test_load_features(self):
        """Feature-Stream laden."""
        with tempfile.TemporaryDirectory() as tmpdir:
            session_dir = _create_test_session(Path(tmpdir))
            timeline = FeatureTimeline(session_dir)

            assert len(timeline.frames) == 300
            assert "ear_left" in timeline.channels
            assert timeline.duration_s > 9.0

    def test_get_channel_values(self):
        """Kanalwerte abrufen."""
        with tempfile.TemporaryDirectory() as tmpdir:
            session_dir = _create_test_session(Path(tmpdir))
            timeline = FeatureTimeline(session_dir)

            times, values = timeline.get_channel_values("ear_left")
            assert len(times) == 300
            assert len(values) == 300

            # Signal-Bereich sollte höhere Werte haben
            signal_values = [v for t, v in zip(times, values) if 3.0 <= t <= 4.0]
            rest_values = [v for t, v in zip(times, values) if 0.0 <= t <= 2.0]
            assert np.mean(signal_values) > np.mean(rest_values) + 0.1


class TestSessionValidator:
    """Tests für den Validierungs-Runner."""

    def test_validates_session(self):
        """Validiert eine Session mit bekannten Signalen."""
        with tempfile.TemporaryDirectory() as tmpdir:
            session_dir = _create_test_session(Path(tmpdir))

            profile = CalibrationProfile(
                person_name="test",
                channel_name="ear_left",
                channel_direction=1,
                baseline_median=0.3,
                baseline_mad=0.03,
                mad_floor=0.01,
                threshold_delta=0.15,
                hold_time_s=0.2,
                refractory_s=0.5,
            )

            validator = SessionValidator(profile)
            metrics = validator.validate_session(session_dir)

            # Sollte mindestens 1 Signal erkennen
            assert metrics.total_signals == 2
            assert metrics.detected_signals >= 1
            assert metrics.tp_rate >= 0.5

    def test_sweep_thresholds(self):
        """Schwellwert-Sweep durchführen."""
        with tempfile.TemporaryDirectory() as tmpdir:
            session_dir = _create_test_session(Path(tmpdir))

            profile = CalibrationProfile(
                person_name="test",
                channel_name="ear_left",
                channel_direction=1,
                baseline_median=0.3,
                baseline_mad=0.03,
                mad_floor=0.01,
                threshold_delta=0.15,
                hold_time_s=0.2,
                refractory_s=0.5,
            )

            validator = SessionValidator(profile)
            result = validator.sweep_thresholds(
                session_dir,
                deltas=[0.05, 0.10, 0.15, 0.20, 0.30]
            )

            assert len(result.threshold_deltas) == 5
            assert len(result.tp_rates) == 5
            assert result.best_threshold > 0

    def test_no_annotations_returns_empty(self):
        """Ohne Annotationen leere Metriken."""
        with tempfile.TemporaryDirectory() as tmpdir:
            session_dir = Path(tmpdir) / "empty_session"
            session_dir.mkdir()

            # Nur Feature-Stream, keine Annotationen
            with open(session_dir / "features.jsonl", "w") as f:
                f.write(json.dumps({"type": "recording_start"}) + "\n")

            profile = CalibrationProfile(
                person_name="test", channel_name="ear_left"
            )
            validator = SessionValidator(profile)
            metrics = validator.validate_session(session_dir)

            assert metrics.total_signals == 0


class TestBatchValidator:
    """Tests für den Batch-Validator."""

    def test_validates_multiple_sessions(self):
        """Validiert mehrere Sessions."""
        with tempfile.TemporaryDirectory() as tmpdir:
            recordings_dir = Path(tmpdir) / "recordings"
            recordings_dir.mkdir()

            # Zwei Sessions erstellen
            _create_test_session(recordings_dir, person="test", label="signal1")
            _create_test_session(recordings_dir, person="test", label="signal2")

            profile = CalibrationProfile(
                person_name="test",
                channel_name="ear_left",
                channel_direction=1,
                baseline_median=0.3,
                baseline_mad=0.03,
                mad_floor=0.01,
                threshold_delta=0.15,
                hold_time_s=0.2,
                refractory_s=0.5,
            )

            batch = BatchValidator(profile)
            results = batch.validate_all(recordings_dir)

            assert len(results) == 2


class TestModelManager:
    """Tests für den Modell-Manager."""

    def test_model_info(self):
        """model_info gibt korrekte Struktur zurück."""
        from blickfang.core.model_manager import model_info
        info = model_info()
        assert "installed" in info
        assert "path" in info
        assert "size_mb" in info


class TestHoldDetection:
    """Tests für HOLD-Event-Emission."""

    def test_long_hold_emits_hold_event(self):
        """Langes Halten emittiert HOLD-Event."""
        from blickfang.core.events import EventType
        from blickfang.detection.detector import SchmittTriggerDetector

        profile = CalibrationProfile(
            person_name="test",
            channel_name="test_channel",
            channel_direction=1,
            baseline_median=0.5,
            baseline_mad=0.05,
            mad_floor=0.01,
            threshold_delta=0.2,
            hold_time_s=0.2,
            refractory_s=0.5,
            hold_duration_s=0.8,
        )

        detector = SchmittTriggerDetector(profile)

        # Ruhephase (2s)
        events = []
        for i in range(60):
            frame = ChannelFrame(
                timestamp=i / 30.0,
                channels={"test_channel": 0.5},
                quality=QualityState.OK,
            )
            e = detector.process(frame)
            if e:
                events.append(e)

        # Langes Signal (2s über Schwelle)
        for i in range(60):
            frame = ChannelFrame(
                timestamp=2.0 + i / 30.0,
                channels={"test_channel": 0.9},
                quality=QualityState.OK,
            )
            e = detector.process(frame)
            if e:
                events.append(e)

        # Mindestens ein HOLD-Event
        hold_events = [e for e in events if e.event_type == EventType.HOLD]
        assert len(hold_events) >= 1, (
            f"Erwartet mindestens 1 HOLD-Event, aber {len(hold_events)} erhalten. "
            f"Alle Events: {[(e.event_type.name, e.timestamp_capture) for e in events]}"
        )
