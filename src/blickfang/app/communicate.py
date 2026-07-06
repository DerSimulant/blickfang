"""Haupteinstiegspunkt für die Kommunikation (M2).

Startet die vollständige Kommunikations-Oberfläche mit:
- Scanning-Engine
- Phrasen / Buchstabieren / Ja-Nein
- Kamera-basierter oder Tastatur-basierter Steuerung
- TTS-Sprachausgabe
- Notruf-Funktion
- Ermüdungs-Monitoring
"""

from __future__ import annotations

import argparse
import logging
import sys
import threading
import time
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="blickfang — Kommunikation starten",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Modi:
  Hauptmenü → Schnell-Phrasen / Buchstabieren / Ja-Nein / Hilfe

Steuerung:
  --key-only    Nur Tastatur (Leertaste = Signal)
  --person NAME Kamera + Profil der Person verwenden

Tastatur-Shortcuts (im UI):
  Leertaste/Enter = Signal geben
  F1 = Hauptmenü
  F2 = Phrasen
  F3 = Buchstabieren
  F4 = Ja/Nein
  ESC = Beenden
""",
    )
    parser.add_argument(
        "--person", "-p",
        help="Name der Person (lädt zugehöriges Profil)",
    )
    parser.add_argument(
        "--key-only",
        action="store_true",
        help="Nur Tastatur-Steuerung (ohne Kamera)",
    )
    parser.add_argument(
        "--speed",
        type=float,
        default=1.5,
        help="Scan-Geschwindigkeit in Sekunden (Standard: 1.5)",
    )
    parser.add_argument(
        "--cancel-time",
        type=float,
        default=2.5,
        help="Cancel-Countdown in Sekunden (Standard: 2.5)",
    )
    parser.add_argument(
        "--windowed",
        action="store_true",
        help="Im Fenster statt Vollbild starten",
    )
    parser.add_argument(
        "--no-tts",
        action="store_true",
        help="Sprachausgabe deaktivieren",
    )
    parser.add_argument(
        "--log-level",
        default="INFO",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        help="Log-Level (Standard: INFO)",
    )

    args = parser.parse_args()

    # Logging einrichten
    logging.basicConfig(
        level=getattr(logging, args.log_level),
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    # TTS initialisieren
    tts_speak = None
    if not args.no_tts:
        tts_speak = _init_tts()

    # Controller erstellen
    from blickfang.scanning.controller import CommMode, CommunicationController
    from blickfang.scanning.alarm import play_alarm_sound

    controller = CommunicationController(
        on_speak=tts_speak,
        on_alarm=play_alarm_sound,
        scan_speed_s=args.speed,
        cancel_countdown_s=args.cancel_time,
    )

    # Kamera-Thread starten (wenn nicht key-only)
    camera_thread = None
    if not args.key_only and args.person:
        camera_thread = _start_camera_detection(args.person, controller)

    # UI starten
    from blickfang.ui.comm_ui import CommunicationUI

    ui = CommunicationUI(
        controller=controller,
        fullscreen=not args.windowed,
        key_switch=args.key_only or True,  # Tastatur immer als Fallback
    )

    print("\n" + "=" * 60)
    print("  blickfang — Kommunikation")
    print("=" * 60)
    if args.key_only:
        print("  Modus: Nur Tastatur (Leertaste = Signal)")
    else:
        print(f"  Modus: Kamera + Tastatur (Person: {args.person or 'Standard'})")
    print(f"  Scan-Geschwindigkeit: {args.speed}s")
    print(f"  Cancel-Countdown: {args.cancel_time}s")
    print("  ESC = Beenden")
    print("=" * 60 + "\n")

    try:
        ui.run()
    except KeyboardInterrupt:
        pass
    finally:
        controller.stop()
        print("\n[Beendet]")


def _init_tts():
    """Initialisiert TTS und gibt die speak-Funktion zurück."""
    try:
        from blickfang.output.tts import TTSEngine
        engine = TTSEngine()
        logger.info("TTS initialisiert")
        return engine.speak
    except Exception as e:
        logger.warning(f"TTS nicht verfügbar: {e}")
        # Fallback: nur Print
        def _print_speak(text: str) -> None:
            print(f"  🔊 {text}")
        return _print_speak


def _start_camera_detection(person: str, controller) -> Optional[threading.Thread]:
    """Startet Kamera-Erkennung in eigenem Thread.

    Returns:
        Thread-Objekt oder None bei Fehler.
    """
    try:
        from blickfang.calibration.profile import load_latest_profile
        from blickfang.capture.camera import CameraSource
        from blickfang.features.face_mesh import FaceMeshExtractor
        from blickfang.features.channels import ChannelComputer
        from blickfang.detection.baseline import GatedBaseline
        from blickfang.detection.detector import SchmittDetector

        # Profil laden
        profile = load_latest_profile(person)
        if not profile:
            logger.warning(f"Kein Profil für '{person}' — nur Tastatur-Modus")
            return None

        def _detection_loop():
            """Kamera → Features → Detektor → Controller.signal()"""
            try:
                camera = CameraSource()
                extractor = FaceMeshExtractor()
                channels = ChannelComputer()

                # Detektor aus Profil konfigurieren
                detector = SchmittDetector(
                    channel=profile.get("channel", "eyeBlinkLeft"),
                    threshold_delta=profile.get("threshold_delta", 0.15),
                    hysteresis=profile.get("hysteresis", 0.5),
                    hold_time_s=profile.get("hold_time_s", 0.12),
                    refractory_s=profile.get("refractory_s", 0.8),
                )

                baseline = GatedBaseline(
                    fast_alpha=profile.get("fast_alpha", 0.02),
                    slow_alpha=profile.get("slow_alpha", 0.002),
                    mad_floor=profile.get("mad_floor", 0.01),
                )

                camera.start()
                logger.info("Kamera-Erkennung gestartet")

                while controller.mode != CommMode.IDLE:
                    frame = camera.get_frame()
                    if frame is None:
                        time.sleep(0.01)
                        continue

                    # Features extrahieren
                    result = extractor.process(frame)
                    if result is None:
                        continue

                    channel_values = channels.compute(result)
                    channel_name = profile.get("channel", "eyeBlinkLeft")
                    value = channel_values.get(channel_name, 0.0)

                    # Baseline aktualisieren
                    baseline.update(value)

                    # Detektor füttern
                    event = detector.update(value, baseline.median, baseline.mad)
                    if event:
                        controller.signal()

                    time.sleep(0.01)

            except Exception as e:
                logger.error(f"Kamera-Fehler: {e}")
            finally:
                try:
                    camera.stop()
                except:
                    pass

        thread = threading.Thread(target=_detection_loop, daemon=True)
        thread.start()
        return thread

    except Exception as e:
        logger.warning(f"Kamera-Erkennung nicht möglich: {e}")
        return None


if __name__ == "__main__":
    main()
