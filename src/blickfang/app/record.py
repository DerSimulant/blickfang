"""Entrypoint: blickfang-record — Aufnahme-Tool.

Nimmt Rohvideos und/oder Feature-Streams auf für spätere Annotation
und Validierung. Speichert:
- Rohvideo (.avi/.mp4) — optional, für visuelle Kontrolle
- Feature-Stream (.jsonl) — für Replay und Detektor-Tests
- Metadaten (.yaml) — Aufnahme-Infos, Kamera-Settings

Workflow:
1. blickfang-record --person Anna --label ruhe --duration 180
2. blickfang-record --person Anna --label signal
3. blickfang-annotate sessions/Anna_20260706_*.jsonl
4. blickfang-validate --profile profiles/Anna.yaml --sessions sessions/
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
import time
import tkinter as tk
from datetime import datetime
from pathlib import Path
from typing import Optional

import cv2
import numpy as np
import yaml

from blickfang.capture.camera import CameraSource, CaptureThread
from blickfang.core.config import AppConfig, load_config
from blickfang.core.events import ChannelFrame, QualityState
from blickfang.detection.quality import FPSSelfTest, LightJumpDetector, LivenessMonitor
from blickfang.features.channels import ChannelComputer
from blickfang.features.face_mesh import FaceMeshExtractor

logger = logging.getLogger(__name__)


class RecordingSession:
    """Eine Aufnahmesitzung mit Video und Feature-Stream."""

    def __init__(
        self,
        output_dir: Path,
        person_name: str,
        label: str = "unlabeled",
        save_video: bool = True,
        config: Optional[AppConfig] = None,
    ):
        self._output_dir = output_dir
        self._person_name = person_name
        self._label = label
        self._save_video = save_video
        self._config = config or AppConfig()

        # Dateipfade
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        self._base_name = f"{person_name}_{timestamp}_{label}"
        self._session_dir = output_dir / self._base_name
        self._session_dir.mkdir(parents=True, exist_ok=True)

        self._jsonl_path = self._session_dir / "features.jsonl"
        self._video_path = self._session_dir / "video.avi"
        self._meta_path = self._session_dir / "meta.yaml"
        self._annotations_path = self._session_dir / "annotations.yaml"

        # Komponenten
        self._capture: Optional[CaptureThread] = None
        self._extractor: Optional[FaceMeshExtractor] = None
        self._channel_computer: Optional[ChannelComputer] = None
        self._video_writer: Optional[cv2.VideoWriter] = None
        self._jsonl_file = None
        self._fps_test = FPSSelfTest()
        self._liveness = LivenessMonitor()
        self._light_detector = LightJumpDetector(self._config.detection)

        # Statistik
        self._frame_count = 0
        self._start_time: float = 0.0
        self._running = False

    @property
    def session_dir(self) -> Path:
        return self._session_dir

    def start(self) -> None:
        """Startet die Aufnahme."""
        # Kamera
        source = CameraSource(self._config.capture)
        self._capture = CaptureThread(source)
        self._capture.start()

        # Feature-Extraktion
        self._extractor = FaceMeshExtractor(self._config.features)
        self._channel_computer = ChannelComputer()

        # Video-Writer
        if self._save_video:
            w, h = self._config.capture.resolution
            fourcc = cv2.VideoWriter_fourcc(*"XVID")
            self._video_writer = cv2.VideoWriter(
                str(self._video_path), fourcc,
                self._config.capture.fps, (w, h)
            )

        # JSONL-Datei
        self._jsonl_file = open(self._jsonl_path, "w", encoding="utf-8")

        # Header
        header = {
            "type": "recording_start",
            "person": self._person_name,
            "label": self._label,
            "datetime": datetime.now().isoformat(),
            "config": {
                "resolution": self._config.capture.resolution,
                "fps": self._config.capture.fps,
                "backend": self._config.capture.backend,
            },
        }
        self._write_jsonl(header)

        self._start_time = time.perf_counter()
        self._running = True
        logger.info(f"Aufnahme gestartet: {self._session_dir}")

    def process_frame(self) -> Optional[ChannelFrame]:
        """Verarbeitet den nächsten Frame.

        Returns:
            ChannelFrame oder None wenn kein Frame verfügbar.
        """
        if not self._running or self._capture is None:
            return None

        frame, ts = self._capture.get_frame()
        if frame is None:
            return None

        # Video speichern
        if self._video_writer is not None:
            self._video_writer.write(frame)

        # Lichtsprung-Veto
        veto = self._light_detector.update(frame)

        # Feature-Extraktion
        ts_ms = int((ts - self._start_time) * 1000)
        face_result = self._extractor.process_frame(frame, max(1, ts_ms))

        # Liveness
        quality = self._liveness.update(
            face_result.face_detected, face_result.landmarks
        )

        # Kanalberechnung
        channel_frame = self._channel_computer.compute(face_result, ts)

        # Qualität anpassen
        if veto:
            channel_frame = ChannelFrame(
                timestamp=channel_frame.timestamp,
                channels=channel_frame.channels,
                quality=QualityState.LIGHT_VETO,
                raw_fps=self._fps_test.fps,
            )

        # FPS
        self._fps_test.tick()

        # JSONL schreiben
        data = {
            "type": "channel_frame",
            "timestamp": channel_frame.timestamp,
            "relative_time_s": ts - self._start_time,
            "channels": channel_frame.channels,
            "quality": channel_frame.quality.name,
            "fps": self._fps_test.fps,
            "face_detected": face_result.face_detected,
        }
        self._write_jsonl(data)

        self._frame_count += 1
        return channel_frame

    def stop(self) -> dict:
        """Beendet die Aufnahme und speichert Metadaten.

        Returns:
            Metadaten-Dict der Aufnahme.
        """
        self._running = False
        duration = time.perf_counter() - self._start_time

        # Footer
        footer = {
            "type": "recording_end",
            "frames": self._frame_count,
            "duration_s": duration,
            "avg_fps": self._frame_count / max(duration, 0.01),
        }
        self._write_jsonl(footer)

        # Dateien schließen
        if self._jsonl_file:
            self._jsonl_file.close()
        if self._video_writer:
            self._video_writer.release()
        if self._capture:
            self._capture.stop()
        if self._extractor:
            self._extractor.close()

        # Metadaten speichern
        meta = {
            "person": self._person_name,
            "label": self._label,
            "datetime": datetime.now().isoformat(),
            "duration_s": round(duration, 1),
            "frames": self._frame_count,
            "avg_fps": round(self._frame_count / max(duration, 0.01), 1),
            "has_video": self._save_video,
            "files": {
                "features": str(self._jsonl_path.name),
                "video": str(self._video_path.name) if self._save_video else None,
                "annotations": str(self._annotations_path.name),
            },
        }

        with open(self._meta_path, "w", encoding="utf-8") as f:
            yaml.dump(meta, f, default_flow_style=False, allow_unicode=True)

        # Leere Annotations-Datei erstellen
        annotations = {
            "person": self._person_name,
            "session": self._base_name,
            "segments": [],  # Wird von blickfang-annotate gefüllt
        }
        with open(self._annotations_path, "w", encoding="utf-8") as f:
            yaml.dump(annotations, f, default_flow_style=False, allow_unicode=True)

        logger.info(
            f"Aufnahme beendet: {self._frame_count} Frames, "
            f"{duration:.1f}s, {meta['avg_fps']} FPS"
        )
        print(f"\n✓ Aufnahme gespeichert: {self._session_dir}")
        print(f"  Dauer: {duration:.1f}s | Frames: {self._frame_count} | FPS: {meta['avg_fps']}")
        print(f"  Features: {self._jsonl_path}")
        if self._save_video:
            print(f"  Video: {self._video_path}")
        print(f"  Annotationen: {self._annotations_path}")
        print(f"\n  Nächster Schritt: blickfang-annotate {self._session_dir}")

        return meta

    def _write_jsonl(self, data: dict) -> None:
        """Schreibt eine Zeile in die JSONL-Datei."""
        if self._jsonl_file:
            self._jsonl_file.write(json.dumps(data, ensure_ascii=False) + "\n")


class RecordApp:
    """Aufnahme-Anwendung mit einfacher Tkinter-UI."""

    def __init__(self, config: AppConfig, person: str, label: str,
                 duration: Optional[float], output_dir: Path,
                 save_video: bool = True):
        self._config = config
        self._person = person
        self._label = label
        self._duration = duration
        self._output_dir = output_dir
        self._save_video = save_video
        self._session: Optional[RecordingSession] = None
        self._root: Optional[tk.Tk] = None

    def run(self) -> None:
        """Startet die Aufnahme."""
        self._session = RecordingSession(
            output_dir=self._output_dir,
            person_name=self._person,
            label=self._label,
            save_video=self._save_video,
            config=self._config,
        )

        print(f"=== blickfang-record ===")
        print(f"  Person: {self._person}")
        print(f"  Label: {self._label}")
        print(f"  Dauer: {self._duration}s" if self._duration else "  Dauer: unbegrenzt (Strg+C zum Stoppen)")
        print(f"  Video: {'Ja' if self._save_video else 'Nein'}")
        print(f"  Ausgabe: {self._output_dir}")
        print()

        self._session.start()

        # Einfache Tkinter-UI für Feedback
        self._root = tk.Tk()
        self._root.title(f"blickfang-record — {self._person} ({self._label})")
        self._root.geometry("400x200")
        self._root.configure(bg="#1a1a2e")

        self._status_label = tk.Label(
            self._root, text="● AUFNAHME LÄUFT",
            font=("Arial", 18, "bold"), bg="#1a1a2e", fg="#e94560"
        )
        self._status_label.pack(pady=20)

        self._info_label = tk.Label(
            self._root, text=f"Person: {self._person} | Label: {self._label}",
            font=("Arial", 12), bg="#1a1a2e", fg="#eaeaea"
        )
        self._info_label.pack()

        self._time_label = tk.Label(
            self._root, text="0:00",
            font=("Courier", 24), bg="#1a1a2e", fg="#4caf50"
        )
        self._time_label.pack(pady=10)

        self._fps_label = tk.Label(
            self._root, text="FPS: --",
            font=("Arial", 10), bg="#1a1a2e", fg="#607d8b"
        )
        self._fps_label.pack()

        # Stopp-Button
        stop_btn = tk.Button(
            self._root, text="⏹ STOPP (oder ESC)",
            font=("Arial", 12), command=self._stop,
            bg="#e94560", fg="white"
        )
        stop_btn.pack(pady=10)

        self._root.bind("<Escape>", lambda e: self._stop())
        self._root.protocol("WM_DELETE_WINDOW", self._stop)

        # Verarbeitungsschleife
        self._start_time = time.perf_counter()
        self._root.after(10, self._process_loop)
        self._root.mainloop()

    def _process_loop(self) -> None:
        """Hauptschleife."""
        if self._session is None:
            return

        # Frame verarbeiten
        frame = self._session.process_frame()

        # Zeit-Anzeige
        elapsed = time.perf_counter() - self._start_time
        minutes = int(elapsed // 60)
        seconds = int(elapsed % 60)
        self._time_label.configure(text=f"{minutes}:{seconds:02d}")

        # FPS
        if frame:
            self._fps_label.configure(text=f"FPS: {frame.raw_fps:.0f}")

        # Dauer-Check
        if self._duration and elapsed >= self._duration:
            self._stop()
            return

        self._root.after(10, self._process_loop)

    def _stop(self) -> None:
        """Beendet die Aufnahme."""
        if self._session:
            self._session.stop()
            self._session = None
        if self._root:
            self._root.destroy()
            self._root = None


def main():
    """Haupteinstiegspunkt für blickfang-record."""
    parser = argparse.ArgumentParser(
        description="blickfang-record — Aufnahme von Videos und Feature-Streams"
    )
    parser.add_argument(
        "--person", "-p", type=str, required=True,
        help="Name der Person"
    )
    parser.add_argument(
        "--label", "-l", type=str, default="unlabeled",
        help="Label/Kategorie der Aufnahme (z.B. 'ruhe', 'signal', 'unruhe', 'blinzeln')"
    )
    parser.add_argument(
        "--duration", "-d", type=float, default=None,
        help="Aufnahmedauer in Sekunden (ohne: unbegrenzt)"
    )
    parser.add_argument(
        "--output", "-o", type=Path, default=Path("./recordings"),
        help="Ausgabeverzeichnis (Standard: ./recordings)"
    )
    parser.add_argument(
        "--no-video", action="store_true",
        help="Kein Rohvideo speichern (nur Feature-Stream)"
    )
    parser.add_argument(
        "--config", type=Path, default=None,
        help="Pfad zur Konfigurationsdatei"
    )
    parser.add_argument(
        "--verbose", "-v", action="store_true",
        help="Ausführliche Ausgabe"
    )
    args = parser.parse_args()

    level = logging.DEBUG if args.verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
    )

    config = load_config(args.config)

    app = RecordApp(
        config=config,
        person=args.person,
        label=args.label,
        duration=args.duration,
        output_dir=args.output,
        save_video=not args.no_video,
    )
    app.run()


if __name__ == "__main__":
    main()
