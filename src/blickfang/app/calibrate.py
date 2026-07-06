"""Entrypoint: Kalibrierung.

Führt den vollständigen Kalibrierungsablauf durch:
1. Kamera-Setup und Selbsttest (/LF150/)
2. Signal-Aufnahme (selbst getaktet, /LF310/)
3. Caregiver-Bestätigung der Events (/LF311/)
4. Neutral-Aufnahme (/LF320/)
5. Kanal-Ranking (/LF330/)
6. Validierungsrunde (/LF360/)
7. Profil speichern (/LF370/)
"""

from __future__ import annotations

import argparse
import logging
import sys
import time
import tkinter as tk
from pathlib import Path
from tkinter import messagebox, simpledialog
from typing import Optional

from blickfang.calibration.profile import CalibrationProfile, ValidationResult
from blickfang.calibration.selector import ChannelSelector
from blickfang.calibration.session import CalibrationSession, SignalEvent
from blickfang.capture.camera import CameraSource, CaptureThread
from blickfang.core.config import AppConfig, load_config
from blickfang.core.events import ChannelFrame, QualityState
from blickfang.detection.quality import FPSSelfTest, LivenessMonitor, check_avx_support
from blickfang.features.channels import ChannelComputer
from blickfang.features.face_mesh import FaceMeshExtractor
from blickfang.io.replay import SessionLogger

logger = logging.getLogger(__name__)


class CalibrationApp:
    """Kalibrierungs-Anwendung mit Tkinter-UI."""

    def __init__(self, config: AppConfig):
        self._config = config
        self._running = False

        # Komponenten
        self._capture: Optional[CaptureThread] = None
        self._extractor: Optional[FaceMeshExtractor] = None
        self._channel_computer: Optional[ChannelComputer] = None
        self._session: Optional[CalibrationSession] = None
        self._selector = ChannelSelector()
        self._fps_test = FPSSelfTest()
        self._liveness = LivenessMonitor()
        self._logger: Optional[SessionLogger] = None

        # UI
        self._root: Optional[tk.Tk] = None

    def run(self) -> None:
        """Startet die Kalibrierung."""
        # Selbsttest (/LF150/)
        if not self._self_test():
            return

        # Initialisierung
        try:
            self._init_components()
        except Exception as e:
            logger.error(f"Initialisierung fehlgeschlagen: {e}")
            print(f"FEHLER: {e}")
            return

        # UI starten
        self._root = tk.Tk()
        self._root.title("blickfang — Kalibrierung")
        self._root.geometry("800x600")

        # Person-Name abfragen
        person_name = simpledialog.askstring(
            "Kalibrierung",
            "Name der Person:",
            parent=self._root,
        )
        if not person_name:
            person_name = "person"

        self._session = CalibrationSession(self._config.calibration)
        self._running = True

        # Kalibrierungsablauf
        self._run_calibration(person_name)

    def _self_test(self) -> bool:
        """Führt den Selbsttest durch (/LF150/)."""
        print("=== blickfang Selbsttest ===")

        # AVX-Prüfung
        if not check_avx_support():
            print("FEHLER: CPU unterstützt kein AVX. MediaPipe benötigt AVX.")
            print("Bitte verwenden Sie einen Computer mit AVX-Unterstützung.")
            return False
        print("✓ AVX-Unterstützung vorhanden")

        # Kamera-Test
        try:
            source = CameraSource(self._config.capture)
            ret, frame, ts = source.read()
            if not ret:
                print("FEHLER: Kamera liefert keine Frames.")
                source.release()
                return False
            source.release()
            print("✓ Kamera verfügbar")
        except Exception as e:
            print(f"FEHLER: Kamera nicht verfügbar: {e}")
            return False

        print("✓ Selbsttest bestanden")
        return True

    def _init_components(self) -> None:
        """Initialisiert alle Komponenten."""
        # Kamera
        source = CameraSource(self._config.capture)
        self._capture = CaptureThread(source)
        self._capture.start()

        # Feature-Extraktion
        self._extractor = FaceMeshExtractor(self._config.features)

        # Kanalberechnung
        self._channel_computer = ChannelComputer()

        # Logging (opt-in)
        self._logger = SessionLogger(self._config.logging)
        self._logger.start()

    def _run_calibration(self, person_name: str) -> None:
        """Führt den Kalibrierungsablauf durch."""
        # Phase 1: Signal-Aufnahme
        messagebox.showinfo(
            "Signal-Aufnahme",
            f"Bitte erzeugen Sie Ihr Signal {self._config.calibration.signal_count}× "
            f"— wann Sie bereit sind.\n\n"
            f"Drücken Sie OK um zu beginnen.",
            parent=self._root,
        )

        self._session.start_signal_phase()
        self._collect_frames(
            duration_s=60.0,  # Max 60s für Signal-Phase
            label="Signal-Aufnahme"
        )

        # Peaks finden
        events = self._session.finalize_signal_phase()
        logger.info(f"Gefundene Signal-Ereignisse: {len(events)}")

        # Phase 1b: Caregiver-Bestätigung (/LF311/)
        confirmed_count = self._confirm_events(events)
        logger.info(f"Bestätigte Events: {confirmed_count}")

        if confirmed_count < 3:
            messagebox.showwarning(
                "Zu wenige Signale",
                f"Nur {confirmed_count} Signale bestätigt. "
                f"Mindestens 3 werden benötigt.",
                parent=self._root,
            )
            self._cleanup()
            return

        # Phase 2: Neutral-Aufnahme (/LF320/)
        neutral_duration = self._config.calibration.neutral_duration_s
        messagebox.showinfo(
            "Ruhephase",
            f"Bitte bleiben Sie {neutral_duration:.0f} Sekunden ruhig.\n"
            f"Unwillkürliche Bewegungen sind OK — sie werden als Referenz genutzt.\n\n"
            f"Drücken Sie OK um zu beginnen.",
            parent=self._root,
        )

        self._session.start_neutral_phase()
        self._collect_frames(
            duration_s=neutral_duration,
            label="Ruhephase"
        )

        # Phase 3: Kanal-Ranking (/LF330/)
        ranking = self._selector.rank_channels(
            self._session.recording,
            self._session.confirmed_events,
        )

        if not ranking.best_channel:
            messagebox.showerror(
                "Kalibrierung fehlgeschlagen",
                "Kein geeigneter Signalkanal gefunden.",
                parent=self._root,
            )
            self._cleanup()
            return

        # Ergebnis anzeigen
        result_text = f"Bester Kanal: {ranking.best_channel}\n"
        result_text += f"FP-Rate bei 90% TP: {ranking.best_score.fp_rate_at_90tp:.3f}\n"
        result_text += f"AUC: {ranking.best_score.auc:.3f}\n\n"
        result_text += "Top 5 Kanäle:\n"
        for i, score in enumerate(ranking.ranked[:5]):
            result_text += f"  {i+1}. {score.channel_name} (FP@90TP: {score.fp_rate_at_90tp:.3f})\n"

        messagebox.showinfo("Kanal-Ranking", result_text, parent=self._root)

        # Profil erstellen
        profile = CalibrationProfile.from_channel_score(
            ranking.best_score, person_name
        )

        # Top-5 für Referenz speichern
        profile.ranking_top5 = [
            {"channel": s.channel_name, "fp_at_90tp": s.fp_rate_at_90tp, "auc": s.auc}
            for s in ranking.ranked[:5]
        ]

        # Phase 4: Validierungsrunde (/LF360/)
        messagebox.showinfo(
            "Validierung",
            f"Validierungsrunde: Bitte erzeugen Sie "
            f"{self._config.calibration.validation_signals} Signale, "
            f"dann {self._config.calibration.validation_rest_s:.0f}s Ruhe.\n\n"
            f"Drücken Sie OK um zu beginnen.",
            parent=self._root,
        )

        # TODO: Vollständige Validierung mit Detektor
        # Für M1: Vereinfachte Validierung
        profile.validation = ValidationResult(
            tp_rate=0.0,
            fp_per_min=0.0,
            signals_tested=self._config.calibration.validation_signals,
        )

        # Profil speichern (/LF370/)
        filepath = profile.save()
        messagebox.showinfo(
            "Profil gespeichert",
            f"Kalibrierungsprofil gespeichert:\n{filepath}",
            parent=self._root,
        )

        self._cleanup()

    def _collect_frames(self, duration_s: float, label: str) -> None:
        """Sammelt Frames für eine bestimmte Dauer."""
        start = time.perf_counter()

        while time.perf_counter() - start < duration_s and self._running:
            frame, ts = self._capture.get_frame()
            if frame is None:
                time.sleep(0.01)
                continue

            # Feature-Extraktion
            ts_ms = int((ts - start) * 1000)
            face_result = self._extractor.process_frame(frame, ts_ms)

            # Kanalberechnung
            channel_frame = self._channel_computer.compute(face_result, ts)

            # FPS-Test
            self._fps_test.tick()

            # An Session übergeben
            if self._session:
                self._session.add_frame(channel_frame)

            # Logging
            if self._logger:
                self._logger.log_frame(channel_frame)

            # Kurze Pause um CPU zu schonen
            time.sleep(0.01)

    def _confirm_events(self, events: list) -> int:
        """Zeigt Events zur Bestätigung durch den Caregiver (/LF311/)."""
        confirmed = 0
        for i, event in enumerate(events[:20]):  # Max 20 Events anzeigen
            result = messagebox.askyesno(
                f"Signal {i+1}/{min(len(events), 20)}",
                f"Kanal: {event.channel_name}\n"
                f"Zeitpunkt: {event.timestamp:.2f}s\n"
                f"Wert: {event.peak_value:.4f}\n\n"
                f"War das ein beabsichtigtes Signal?",
                parent=self._root,
            )
            if result:
                self._session.confirm_event(event)
                confirmed += 1
            else:
                self._session.reject_event(event)

        return confirmed

    def _cleanup(self) -> None:
        """Räumt auf."""
        if self._capture:
            self._capture.stop()
        if self._extractor:
            self._extractor.close()
        if self._logger:
            self._logger.stop()
        if self._root:
            self._root.destroy()


def main():
    """Haupteinstiegspunkt für die Kalibrierung."""
    parser = argparse.ArgumentParser(
        description="blickfang — Kalibrierung"
    )
    parser.add_argument(
        "--config", type=Path, default=None,
        help="Pfad zur Konfigurationsdatei (YAML)"
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

    # App starten
    app = CalibrationApp(config)
    app.run()


if __name__ == "__main__":
    main()
