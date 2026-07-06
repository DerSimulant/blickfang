"""Entrypoint: Ja/Nein/PASSE-Kommunikation.

Hauptanwendung für die Kommunikation. Lädt ein kalibriertes Profil
und startet den 3-Item-Scan mit Live-Monitor.
"""

from __future__ import annotations

import argparse
import logging
import sys
import time
import tkinter as tk
from pathlib import Path
from typing import Optional

from blickfang.calibration.profile import CalibrationProfile, list_profiles
from blickfang.capture.camera import CameraSource, CaptureThread, VideoFileSource
from blickfang.core.config import AppConfig, load_config
from blickfang.core.events import (
    ChannelFrame,
    DetectorState,
    QualityState,
    SwitchEvent,
    SystemStatus,
)
from blickfang.detection.quality import FPSSelfTest, LightJumpDetector, LivenessMonitor
from blickfang.features.channels import ChannelComputer
from blickfang.features.face_mesh import FaceMeshExtractor
from blickfang.io.replay import SessionLogger
from blickfang.output.scanning import ScanResult, ScanState, YesNoScanner
from blickfang.output.tts import TTSEngine
from blickfang.switch.key_switch import KeySwitch
from blickfang.switch.video_switch import VideoSwitch
from blickfang.temporal.patterns import PatternMatcher
from blickfang.ui.scan_ui import ScanUI

logger = logging.getLogger(__name__)


class YesNoApp:
    """Ja/Nein/PASSE-Kommunikationsanwendung."""

    def __init__(self, config: AppConfig, profile: CalibrationProfile):
        self._config = config
        self._profile = profile
        self._running = False

        # Pipeline-Komponenten
        self._capture: Optional[CaptureThread] = None
        self._extractor: Optional[FaceMeshExtractor] = None
        self._channel_computer: Optional[ChannelComputer] = None
        self._video_switch: Optional[VideoSwitch] = None
        self._key_switch: Optional[KeySwitch] = None
        self._pattern_matcher: Optional[PatternMatcher] = None
        self._scanner: Optional[YesNoScanner] = None
        self._tts: Optional[TTSEngine] = None
        self._session_logger: Optional[SessionLogger] = None

        # Qualitätsüberwachung
        self._fps_test = FPSSelfTest()
        self._liveness = LivenessMonitor()
        self._light_detector = LightJumpDetector(config.detection)

        # UI
        self._ui: Optional[ScanUI] = None

        # Status
        self._system_status = SystemStatus()

    def run(self) -> None:
        """Startet die Anwendung."""
        logger.info(f"Starte Ja/Nein/PASSE mit Profil: {self._profile.person_name}")
        logger.info(f"Kanal: {self._profile.channel_name}")

        try:
            self._init_components()
            self._init_ui()
            self._start_processing()
        except Exception as e:
            logger.error(f"Fehler beim Start: {e}")
            raise

    def _init_components(self) -> None:
        """Initialisiert alle Pipeline-Komponenten."""
        # Kamera
        source = CameraSource(self._config.capture)
        self._capture = CaptureThread(source)

        # Feature-Extraktion
        self._extractor = FaceMeshExtractor(self._config.features)

        # Kanalberechnung
        blocked = set(self._profile.blocked_regions)
        self._channel_computer = ChannelComputer(blocked_regions=blocked)

        # Video-Schalter (Person A)
        self._video_switch = VideoSwitch(self._profile)

        # Key-Schalter (Person B / Test)
        self._key_switch = KeySwitch(self._config.switch.key_binding)

        # Pattern-Matcher
        self._pattern_matcher = PatternMatcher(self._config.patterns)
        self._pattern_matcher.set_callback(self._on_confirmed_event)

        # TTS
        self._tts = TTSEngine(self._config.tts)
        self._tts.start()

        # Scanner
        self._scanner = YesNoScanner(self._config.output, self._tts)
        self._scanner.set_callbacks(
            on_highlight=self._on_highlight,
            on_result=self._on_scan_result,
            on_state_change=self._on_scan_state_change,
            on_countdown_tick=self._on_countdown_tick,
        )

        # Session-Logging
        self._session_logger = SessionLogger(self._config.logging)
        self._session_logger.start()

        # Switch-Callbacks
        self._video_switch.set_callback(self._on_raw_switch_event)
        self._key_switch.set_callback(self._on_raw_switch_event)

    def _init_ui(self) -> None:
        """Initialisiert die UI."""
        self._ui = ScanUI(
            fullscreen=self._config.ui.fullscreen,
            font_size=self._config.ui.font_size,
        )

        # Key-Binding
        key = self._config.switch.key_binding
        if key == "space":
            bind_key = "<space>"
        elif key == "Return":
            bind_key = "<Return>"
        else:
            bind_key = f"<{key}>"

        self._ui.root.bind(bind_key, self._key_switch.on_key_press)
        self._ui.root.bind("<Escape>", lambda e: self._stop())
        self._ui.root.bind("<F5>", lambda e: self._restart_scan())

        self._ui.set_status(
            f"Profil: {self._profile.person_name} | "
            f"Kanal: {self._profile.channel_name} | "
            f"Taste: {key} | ESC=Beenden | F5=Neustart"
        )

    def _start_processing(self) -> None:
        """Startet die Verarbeitungspipeline."""
        self._running = True
        self._capture.start()
        self._video_switch.start()
        self._key_switch.start()

        # Scan starten
        self._scanner.start()

        # Verarbeitungsschleife (in Tkinter-Mainloop integriert)
        self._ui.root.after(10, self._process_loop)
        self._ui.mainloop()

    def _process_loop(self) -> None:
        """Hauptverarbeitungsschleife (wird von Tkinter periodisch aufgerufen)."""
        if not self._running:
            return

        # Frame holen
        frame, ts = self._capture.get_frame()

        if frame is not None:
            # Lichtsprung-Veto (/LF130/)
            veto = self._light_detector.update(frame)

            # Feature-Extraktion
            ts_ms = int(ts * 1000) % (2**31)  # Monoton, aber bounded
            face_result = self._extractor.process_frame(frame, ts_ms)

            # Liveness-Monitor (/LF140/)
            quality = self._liveness.update(
                face_result.face_detected,
                face_result.landmarks,
            )

            # Kanalberechnung
            channel_frame = self._channel_computer.compute(face_result, ts)

            # Qualität und Veto berücksichtigen
            if veto:
                channel_frame = ChannelFrame(
                    timestamp=channel_frame.timestamp,
                    channels=channel_frame.channels,
                    quality=QualityState.LIGHT_VETO,
                    raw_fps=self._fps_test.fps,
                )

            # FPS
            self._fps_test.tick()
            channel_frame = ChannelFrame(
                timestamp=channel_frame.timestamp,
                channels=channel_frame.channels,
                quality=channel_frame.quality,
                raw_fps=self._fps_test.fps,
            )

            # Detektion (nur bei Video-Quelle)
            if self._config.switch.source == "video":
                event = self._video_switch.process_frame(channel_frame)

            # Logging
            if self._session_logger:
                self._session_logger.log_frame(channel_frame)

            # Status aktualisieren
            self._update_status(channel_frame)

        # Scanner-Tick
        self._scanner.tick()

        # UI aktualisieren
        if self._ui and self._config.ui.monitor_visible:
            self._ui.update_monitor(self._system_status)

        # Nächster Tick
        self._ui.root.after(30, self._process_loop)  # ~33 FPS UI-Update

    def _update_status(self, frame: ChannelFrame) -> None:
        """Aktualisiert den Systemstatus für die UI."""
        channel = self._profile.channel_name
        value = frame.channels.get(channel, 0.0)

        detector = self._video_switch.detector if self._video_switch else None

        self._system_status = SystemStatus(
            detector_state=detector.state if detector else DetectorState.IDLE,
            quality_state=frame.quality,
            current_channel=channel,
            current_value=value,
            baseline_value=detector.baseline.median if detector else 0.0,
            threshold_value=detector.threshold_on if detector else 0.0,
            fps=frame.raw_fps,
            veto_active=self._light_detector.is_vetoed,
            veto_remaining_s=self._light_detector.remaining_s,
            expected_fp_per_min=detector.expected_fp_per_min if detector else 0.0,
        )

    def _on_raw_switch_event(self, event: SwitchEvent) -> None:
        """Callback für rohe Switch-Events (vor Pattern-Matching)."""
        # Pattern-Matching
        self._pattern_matcher.process_event(event)

        # Logging
        if self._session_logger:
            self._session_logger.log_event(event)

    def _on_confirmed_event(self, event: SwitchEvent) -> None:
        """Callback für bestätigte (Pattern-gematchte) Events."""
        # An Scanner weiterleiten
        if self._scanner:
            self._scanner.on_switch_event(event)

    def _on_highlight(self, index: int, item: str) -> None:
        """UI-Callback: Item hervorgehoben."""
        if self._ui:
            self._ui.highlight_item(index, item)

    def _on_scan_result(self, result: ScanResult) -> None:
        """UI-Callback: Scan-Ergebnis."""
        if self._ui:
            if result.no_answer:
                self._ui.show_result("KEINE ANTWORT", "#ff9800")
            elif result.cancelled:
                self._ui.show_result(f"ABGEBROCHEN ({result.item})", "#9c27b0")
            else:
                self._ui.show_result(f"→ {result.item}", "#4caf50")

            # Nach 3s neuen Scan starten
            self._ui.root.after(3000, self._restart_scan)

    def _on_scan_state_change(self, state: ScanState) -> None:
        """UI-Callback: Scan-Zustand geändert."""
        pass

    def _on_countdown_tick(self, remaining: float) -> None:
        """UI-Callback: Countdown-Update."""
        if self._ui:
            self._ui.show_countdown(remaining)

    def _restart_scan(self) -> None:
        """Startet einen neuen Scan-Durchlauf."""
        if self._ui:
            self._ui.reset_scan()
        if self._scanner:
            self._scanner.start()

    def _stop(self) -> None:
        """Beendet die Anwendung."""
        self._running = False
        if self._capture:
            self._capture.stop()
        if self._extractor:
            self._extractor.close()
        if self._tts:
            self._tts.stop()
        if self._session_logger:
            self._session_logger.stop()
        if self._ui:
            self._ui.destroy()


def main():
    """Haupteinstiegspunkt für Ja/Nein/PASSE-Kommunikation."""
    parser = argparse.ArgumentParser(
        description="blickfang — Ja/Nein/PASSE-Kommunikation"
    )
    parser.add_argument(
        "--config", type=Path, default=None,
        help="Pfad zur Konfigurationsdatei (YAML)"
    )
    parser.add_argument(
        "--profile", type=Path, default=None,
        help="Pfad zum Kalibrierungsprofil (YAML)"
    )
    parser.add_argument(
        "--person", type=str, default=None,
        help="Name der Person (lädt neuestes Profil)"
    )
    parser.add_argument(
        "--key-only", action="store_true",
        help="Nur Tastatur-Schalter (kein Video)"
    )
    parser.add_argument(
        "--verbose", "-v", action="store_true",
        help="Ausführliche Ausgabe"
    )
    args = parser.parse_args()

    # Logging
    level = logging.DEBUG if args.verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
    )

    # Konfiguration laden
    config = load_config(args.config)

    # Key-Only-Modus
    if args.key_only:
        config.switch.source = "key"

    # Profil laden
    profile = None
    if args.profile:
        profile = CalibrationProfile.load(args.profile)
    elif args.person:
        profiles = list_profiles(args.person)
        if profiles:
            profile = CalibrationProfile.load(profiles[0])
            logger.info(f"Neuestes Profil geladen: {profiles[0]}")
        else:
            logger.error(f"Kein Profil für '{args.person}' gefunden")
            sys.exit(1)
    else:
        # Versuche irgendeines zu laden
        profiles = list_profiles()
        if profiles:
            profile = CalibrationProfile.load(profiles[0])
            logger.info(f"Profil geladen: {profiles[0]}")
        else:
            # Erstelle ein Dummy-Profil für Key-Only-Modus
            if config.switch.source == "key":
                profile = CalibrationProfile(
                    person_name="key_user",
                    channel_name="key_input",
                )
                logger.info("Key-Only-Modus: Dummy-Profil erstellt")
            else:
                logger.error(
                    "Kein Profil gefunden. Bitte zuerst kalibrieren: "
                    "blickfang-calibrate"
                )
                sys.exit(1)

    # App starten
    app = YesNoApp(config, profile)
    app.run()


if __name__ == "__main__":
    main()
