"""Tests für das Scanning- und Output-Modul."""

import time
from unittest.mock import MagicMock, patch

import pytest

from blickfang.core.config import OutputConfig, PatternsConfig
from blickfang.core.events import EventType, SwitchEvent
from blickfang.output.scanning import ScanResult, ScanState, YesNoScanner
from blickfang.output.tts import TTSEngine
from blickfang.core.config import TTSConfig


class TestYesNoScanner:
    """Tests für den Ja/Nein/PASSE-Scanner."""

    def _make_scanner(self) -> YesNoScanner:
        """Erstellt einen Scanner mit Mock-TTS."""
        config = OutputConfig(
            items=["JA", "NEIN", "PASSE"],
            scan_speed_s=0.1,  # Schnell für Tests
            max_cycles=2,
            cancel_countdown_s=0.2,
        )
        tts = MagicMock(spec=TTSEngine)
        return YesNoScanner(config, tts)

    def test_initial_state_idle(self):
        """Scanner startet im IDLE-Zustand."""
        scanner = self._make_scanner()
        assert scanner.state == ScanState.IDLE

    def test_start_begins_scanning(self):
        """Start wechselt in SCANNING-Zustand."""
        scanner = self._make_scanner()
        scanner.start()
        assert scanner.state == ScanState.SCANNING
        assert scanner.current_index == 0

    def test_signal_selects_item(self):
        """Signal während Scanning wählt Item aus."""
        scanner = self._make_scanner()
        results = []
        scanner.set_callbacks(on_result=lambda r: results.append(r))
        scanner.start()

        # Signal senden
        event = SwitchEvent(
            source_id="test",
            event_type=EventType.SINGLE,
            timestamp_capture=time.perf_counter(),
            confidence=1.0,
        )
        scanner.on_switch_event(event)

        # Sollte in COUNTDOWN sein
        assert scanner.state in (ScanState.SELECTED, ScanState.COUNTDOWN)

    def test_three_items_present(self):
        """Scanner hat genau 3 Items: JA, NEIN, PASSE (/LF600/)."""
        scanner = self._make_scanner()
        scanner.start()

        items_seen = set()
        # Simuliere Durchlauf
        for _ in range(3):
            items_seen.add(scanner.current_item)
            scanner._advance_item()

        assert "JA" in items_seen
        assert "NEIN" in items_seen
        assert "PASSE" in items_seen

    def test_timeout_no_answer(self):
        """Timeout erzeugt KEINE ANTWORT, nie eine Auswahl (/LF610/)."""
        config = OutputConfig(
            items=["JA", "NEIN", "PASSE"],
            scan_speed_s=0.01,
            max_cycles=2,
            cancel_countdown_s=0.1,
        )
        tts = MagicMock(spec=TTSEngine)
        scanner = YesNoScanner(config, tts)

        results = []
        scanner.set_callbacks(on_result=lambda r: results.append(r))
        scanner.start()

        # Viele Ticks ohne Signal → Timeout
        for _ in range(100):
            scanner.tick()
            time.sleep(0.01)

        # Sollte NO_ANSWER sein
        assert any(r.no_answer for r in results), (
            "Timeout sollte KEINE ANTWORT erzeugen"
        )

    def test_cancel_during_countdown(self):
        """Signal während Countdown bricht Ausgabe ab (/LF620/)."""
        scanner = self._make_scanner()
        results = []
        scanner.set_callbacks(on_result=lambda r: results.append(r))
        scanner.start()

        # Erstes Signal: Auswahl
        event1 = SwitchEvent(
            source_id="test", event_type=EventType.SINGLE,
            timestamp_capture=time.perf_counter(), confidence=1.0,
        )
        scanner.on_switch_event(event1)

        # Sollte jetzt im Countdown sein
        assert scanner.state == ScanState.COUNTDOWN

        # Zweites Signal während Countdown: Abbruch
        event2 = SwitchEvent(
            source_id="test", event_type=EventType.SINGLE,
            timestamp_capture=time.perf_counter(), confidence=1.0,
        )
        scanner.on_switch_event(event2)

        assert scanner.state == ScanState.CANCELLED
        assert any(r.cancelled for r in results)


class TestReplay:
    """Tests für Session-Logging und Replay."""

    def test_log_and_replay(self):
        """Session kann geloggt und wiedergegeben werden."""
        import tempfile
        from pathlib import Path

        from blickfang.core.config import LoggingConfig
        from blickfang.core.events import ChannelFrame, QualityState
        from blickfang.io.replay import SessionLogger, SessionReplay

        with tempfile.TemporaryDirectory() as tmpdir:
            config = LoggingConfig(enabled=True, output_dir=tmpdir)
            logger = SessionLogger(config)
            filepath = logger.start()

            assert filepath is not None

            # Frames loggen
            for i in range(100):
                frame = ChannelFrame(
                    timestamp=i * 0.033,
                    channels={"ear_left": 0.3 + i * 0.001},
                    quality=QualityState.OK,
                    raw_fps=30.0,
                )
                logger.log_frame(frame)

            # Event loggen
            event = SwitchEvent(
                source_id="video_switch",
                event_type=EventType.SINGLE,
                timestamp_capture=1.5,
                confidence=0.9,
                channel_name="ear_left",
            )
            logger.log_event(event)

            logger.stop()

            # Replay
            replay = SessionReplay(filepath)
            assert replay.frame_count == 100
            assert replay.duration_s > 0

            frames = list(replay.iter_frames())
            assert len(frames) == 100
            assert frames[0].channels["ear_left"] == pytest.approx(0.3, abs=0.01)

            events = list(replay.iter_events())
            assert len(events) == 1
            assert events[0].source_id == "video_switch"
