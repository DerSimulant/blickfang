"""Entrypoint: blickfang-validate — Batch-Validierung.

Lässt den Detektor gegen annotierte Aufnahmen laufen und berechnet:
- True-Positive-Rate (TP): Wie viele annotierte Signale wurden erkannt?
- False-Positive-Rate (FP/min): Wie viele Fehlauslösungen pro Minute?
- Latenz: Wie schnell nach Signal-Beginn wird erkannt?
- Vergleich verschiedener Schwellwert-Einstellungen

Workflow:
    blickfang-validate --profile config/profiles/Anna_v3.yaml --sessions recordings/
    blickfang-validate --profile config/profiles/Anna_v3.yaml --sessions recordings/ --sweep
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import numpy as np
import yaml

from blickfang.calibration.profile import CalibrationProfile
from blickfang.core.config import AppConfig, load_config
from blickfang.core.events import ChannelFrame, DetectorState, EventType, QualityState, SwitchEvent
from blickfang.detection.baseline import DualTimescaleBaseline
from blickfang.detection.detector import SchmittTriggerDetector

logger = logging.getLogger(__name__)


@dataclass
class ValidationMetrics:
    """Metriken einer Validierung."""

    session_name: str = ""
    total_signals: int = 0
    detected_signals: int = 0
    missed_signals: int = 0
    false_positives: int = 0
    duration_s: float = 0.0
    ruhe_duration_s: float = 0.0

    # Raten
    tp_rate: float = 0.0
    fp_per_min: float = 0.0
    fp_per_min_ruhe: float = 0.0  # FP nur in Ruhephasen

    # Latenz
    latencies_s: List[float] = field(default_factory=list)
    mean_latency_s: float = 0.0
    max_latency_s: float = 0.0

    # Konfiguration
    threshold_delta: float = 0.0
    hold_time_s: float = 0.0

    def compute_rates(self) -> None:
        """Berechnet abgeleitete Metriken."""
        if self.total_signals > 0:
            self.tp_rate = self.detected_signals / self.total_signals
        if self.duration_s > 0:
            self.fp_per_min = self.false_positives / (self.duration_s / 60.0)
        if self.ruhe_duration_s > 0:
            self.fp_per_min_ruhe = self.false_positives / (self.ruhe_duration_s / 60.0)
        if self.latencies_s:
            self.mean_latency_s = np.mean(self.latencies_s)
            self.max_latency_s = np.max(self.latencies_s)


@dataclass
class SweepResult:
    """Ergebnis eines Schwellwert-Sweeps."""

    threshold_deltas: List[float] = field(default_factory=list)
    tp_rates: List[float] = field(default_factory=list)
    fp_per_mins: List[float] = field(default_factory=list)
    best_threshold: float = 0.0
    best_tp: float = 0.0
    best_fp: float = 0.0


class SessionValidator:
    """Validiert den Detektor gegen eine annotierte Session."""

    def __init__(self, profile: CalibrationProfile, config: Optional[AppConfig] = None):
        self._profile = profile
        self._config = config or AppConfig()

    def validate_session(self, session_dir: Path) -> ValidationMetrics:
        """Validiert eine einzelne Session.

        Args:
            session_dir: Pfad zum Session-Verzeichnis.

        Returns:
            ValidationMetrics mit TP/FP/Latenz.
        """
        metrics = ValidationMetrics(session_name=session_dir.name)

        # Annotationen laden
        annotations_path = session_dir / "annotations.yaml"
        if not annotations_path.exists():
            logger.warning(f"Keine Annotationen: {session_dir}")
            return metrics

        with open(annotations_path, "r", encoding="utf-8") as f:
            annotations = yaml.safe_load(f) or {}

        segments = annotations.get("segments", [])
        if not segments:
            logger.warning(f"Keine Segmente in Annotationen: {session_dir}")
            return metrics

        # Feature-Stream laden
        features_path = session_dir / "features.jsonl"
        if not features_path.exists():
            logger.warning(f"Kein Feature-Stream: {session_dir}")
            return metrics

        frames = self._load_frames(features_path)
        if not frames:
            return metrics

        # Signal- und Ruhe-Segmente extrahieren
        signal_segments = [s for s in segments if s["label"] == "signal"]
        ruhe_segments = [s for s in segments if s["label"] == "ruhe"]

        metrics.total_signals = len(signal_segments)
        metrics.duration_s = frames[-1].timestamp - frames[0].timestamp if frames else 0
        metrics.ruhe_duration_s = sum(
            s["end_s"] - s["start_s"] for s in ruhe_segments
        )
        metrics.threshold_delta = self._profile.threshold_delta
        metrics.hold_time_s = self._profile.hold_time_s

        # Detektor erstellen und laufen lassen
        detector = SchmittTriggerDetector(self._profile)
        emissions: List[SwitchEvent] = []

        for frame in frames:
            event = detector.process(frame)
            if event is not None:
                emissions.append(event)

        # Emissionen mit Annotationen abgleichen
        matched_signals = set()
        false_positives = []

        for emission in emissions:
            emission_time = emission.timestamp_capture - frames[0].timestamp
            matched = False

            for i, seg in enumerate(signal_segments):
                if i in matched_signals:
                    continue
                # Emission innerhalb oder kurz nach Signal-Segment?
                # Toleranz: bis 1s nach Signal-Ende (Latenz)
                if seg["start_s"] - 0.5 <= emission_time <= seg["end_s"] + 1.0:
                    matched_signals.add(i)
                    latency = max(0, emission_time - seg["start_s"])
                    metrics.latencies_s.append(latency)
                    matched = True
                    break

            if not matched:
                false_positives.append(emission_time)

        metrics.detected_signals = len(matched_signals)
        metrics.missed_signals = metrics.total_signals - metrics.detected_signals
        metrics.false_positives = len(false_positives)
        metrics.compute_rates()

        return metrics

    def sweep_thresholds(
        self,
        session_dir: Path,
        deltas: Optional[List[float]] = None,
    ) -> SweepResult:
        """Führt einen Schwellwert-Sweep durch.

        Testet verschiedene threshold_delta-Werte und findet den
        optimalen Kompromiss zwischen TP und FP.
        """
        if deltas is None:
            # Standard-Sweep: 0.05 bis 0.5 in 0.025-Schritten
            deltas = [round(0.05 + i * 0.025, 3) for i in range(19)]

        result = SweepResult()

        for delta in deltas:
            # Profil mit neuem Schwellwert
            test_profile = CalibrationProfile(
                person_name=self._profile.person_name,
                channel_name=self._profile.channel_name,
                channel_direction=self._profile.channel_direction,
                baseline_median=self._profile.baseline_median,
                baseline_mad=self._profile.baseline_mad,
                mad_floor=self._profile.mad_floor,
                threshold_delta=delta,
                hold_time_s=self._profile.hold_time_s,
                refractory_s=self._profile.refractory_s,
            )

            validator = SessionValidator(test_profile, self._config)
            metrics = validator.validate_session(session_dir)

            result.threshold_deltas.append(delta)
            result.tp_rates.append(metrics.tp_rate)
            result.fp_per_mins.append(metrics.fp_per_min)

        # Besten Punkt finden (TP >= 0.8 mit niedrigstem FP)
        best_idx = None
        for i, (tp, fp) in enumerate(zip(result.tp_rates, result.fp_per_mins)):
            if tp >= 0.8:
                if best_idx is None or fp < result.fp_per_mins[best_idx]:
                    best_idx = i

        if best_idx is None:
            # Kein Punkt mit TP >= 0.8 → nimm höchsten TP
            best_idx = int(np.argmax(result.tp_rates))

        result.best_threshold = result.threshold_deltas[best_idx]
        result.best_tp = result.tp_rates[best_idx]
        result.best_fp = result.fp_per_mins[best_idx]

        return result

    def _load_frames(self, path: Path) -> List[ChannelFrame]:
        """Lädt Frames aus einer JSONL-Datei."""
        frames = []
        with open(path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    data = json.loads(line)
                    if data.get("type") == "channel_frame":
                        quality = QualityState[data.get("quality", "OK")]
                        frame = ChannelFrame(
                            timestamp=data["timestamp"],
                            channels=data["channels"],
                            quality=quality,
                            raw_fps=data.get("fps", 30.0),
                        )
                        frames.append(frame)
                except (json.JSONDecodeError, KeyError):
                    continue
        return frames


class BatchValidator:
    """Validiert über mehrere Sessions hinweg."""

    def __init__(self, profile: CalibrationProfile, config: Optional[AppConfig] = None):
        self._profile = profile
        self._config = config
        self._validator = SessionValidator(profile, config)

    def validate_all(self, sessions_dir: Path) -> List[ValidationMetrics]:
        """Validiert alle Sessions in einem Verzeichnis.

        Args:
            sessions_dir: Verzeichnis mit Session-Unterordnern.

        Returns:
            Liste von ValidationMetrics pro Session.
        """
        results = []

        # Finde alle Session-Verzeichnisse (mit features.jsonl)
        session_dirs = sorted([
            d for d in sessions_dir.iterdir()
            if d.is_dir() and (d / "features.jsonl").exists()
        ])

        if not session_dirs:
            logger.warning(f"Keine Sessions gefunden in: {sessions_dir}")
            return results

        print(f"\nValidiere {len(session_dirs)} Sessions...")
        print(f"Profil: {self._profile.person_name} | Kanal: {self._profile.channel_name}")
        print(f"Schwellwert-Delta: {self._profile.threshold_delta}")
        print(f"Haltezeit: {self._profile.hold_time_s}s")
        print("-" * 70)

        for session_dir in session_dirs:
            metrics = self._validator.validate_session(session_dir)
            results.append(metrics)

            # Ausgabe pro Session
            status = "✓" if metrics.tp_rate >= 0.8 and metrics.fp_per_min < 1.0 else "✗"
            print(
                f"  {status} {metrics.session_name:40s} "
                f"TP: {metrics.tp_rate:.0%} ({metrics.detected_signals}/{metrics.total_signals}) "
                f"FP: {metrics.fp_per_min:.2f}/min "
                f"Latenz: {metrics.mean_latency_s:.2f}s"
            )

        # Zusammenfassung
        print("-" * 70)
        self._print_summary(results)

        return results

    def _print_summary(self, results: List[ValidationMetrics]) -> None:
        """Gibt eine Zusammenfassung aus."""
        if not results:
            return

        total_signals = sum(r.total_signals for r in results)
        total_detected = sum(r.detected_signals for r in results)
        total_fp = sum(r.false_positives for r in results)
        total_duration = sum(r.duration_s for r in results)
        all_latencies = [l for r in results for l in r.latencies_s]

        overall_tp = total_detected / max(total_signals, 1)
        overall_fp_min = total_fp / max(total_duration / 60, 0.01)
        mean_latency = np.mean(all_latencies) if all_latencies else 0

        print(f"\n  GESAMT:")
        print(f"    Sessions: {len(results)}")
        print(f"    Signale: {total_detected}/{total_signals} erkannt ({overall_tp:.0%})")
        print(f"    Fehlauslösungen: {total_fp} ({overall_fp_min:.2f}/min)")
        print(f"    Mittlere Latenz: {mean_latency:.2f}s")
        print(f"    Gesamtdauer: {total_duration:.0f}s ({total_duration/60:.1f} min)")

        # Bewertung
        print()
        if overall_tp >= 0.9 and overall_fp_min < 0.5:
            print("  ★★★ EXZELLENT — Profil ist sehr gut eingestellt")
        elif overall_tp >= 0.8 and overall_fp_min < 1.0:
            print("  ★★☆ GUT — Profil ist brauchbar")
        elif overall_tp >= 0.6:
            print("  ★☆☆ MÄSSIG — Schwellwert-Anpassung empfohlen")
        else:
            print("  ☆☆☆ SCHLECHT — Neukalibrierung empfohlen")


def main():
    """Haupteinstiegspunkt für blickfang-validate."""
    parser = argparse.ArgumentParser(
        description="blickfang-validate — Batch-Validierung des Detektors"
    )
    parser.add_argument(
        "--profile", "-p", type=Path, required=True,
        help="Pfad zum Kalibrierungsprofil (YAML)"
    )
    parser.add_argument(
        "--sessions", "-s", type=Path, required=True,
        help="Verzeichnis mit aufgezeichneten Sessions"
    )
    parser.add_argument(
        "--sweep", action="store_true",
        help="Schwellwert-Sweep durchführen"
    )
    parser.add_argument(
        "--output", "-o", type=Path, default=None,
        help="Ergebnis-Datei (YAML)"
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

    # Profil laden
    profile = CalibrationProfile.load(args.profile)
    config = load_config(args.config)

    if args.sweep:
        # Schwellwert-Sweep
        print("=== blickfang-validate — Schwellwert-Sweep ===")
        validator = SessionValidator(profile, config)

        # Finde erste Session mit Annotationen
        session_dirs = [
            d for d in args.sessions.iterdir()
            if d.is_dir() and (d / "annotations.yaml").exists()
        ]

        if not session_dirs:
            print("FEHLER: Keine annotierten Sessions gefunden.")
            sys.exit(1)

        print(f"\nSweep über {len(session_dirs)} Sessions...")
        print(f"{'Delta':>8} {'TP-Rate':>10} {'FP/min':>10}")
        print("-" * 30)

        # Aggregierter Sweep über alle Sessions
        deltas = [round(0.05 + i * 0.025, 3) for i in range(19)]
        best_delta = 0.0
        best_score = -1.0

        for delta in deltas:
            test_profile = CalibrationProfile(
                person_name=profile.person_name,
                channel_name=profile.channel_name,
                channel_direction=profile.channel_direction,
                baseline_median=profile.baseline_median,
                baseline_mad=profile.baseline_mad,
                mad_floor=profile.mad_floor,
                threshold_delta=delta,
                hold_time_s=profile.hold_time_s,
                refractory_s=profile.refractory_s,
            )
            test_validator = SessionValidator(test_profile, config)

            total_tp = 0
            total_signals = 0
            total_fp = 0
            total_duration = 0.0

            for sd in session_dirs:
                m = test_validator.validate_session(sd)
                total_tp += m.detected_signals
                total_signals += m.total_signals
                total_fp += m.false_positives
                total_duration += m.duration_s

            tp_rate = total_tp / max(total_signals, 1)
            fp_min = total_fp / max(total_duration / 60, 0.01)

            # Score: TP - 2*FP (Sicherheit vor Geschwindigkeit)
            score = tp_rate - 2.0 * min(fp_min, 1.0)
            if score > best_score:
                best_score = score
                best_delta = delta

            marker = " ←" if delta == best_delta else ""
            print(f"  {delta:6.3f}   {tp_rate:7.0%}   {fp_min:7.2f}{marker}")

        print(f"\n  Empfohlener Schwellwert: {best_delta:.3f}")

    else:
        # Standard-Validierung
        print("=== blickfang-validate ===")
        batch = BatchValidator(profile, config)
        results = batch.validate_all(args.sessions)

        # Ergebnis speichern
        if args.output:
            output_data = {
                "profile": str(args.profile),
                "sessions_dir": str(args.sessions),
                "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S"),
                "results": [
                    {
                        "session": r.session_name,
                        "tp_rate": round(r.tp_rate, 3),
                        "fp_per_min": round(r.fp_per_min, 3),
                        "mean_latency_s": round(r.mean_latency_s, 3),
                        "signals": r.total_signals,
                        "detected": r.detected_signals,
                        "false_positives": r.false_positives,
                    }
                    for r in results
                ],
            }
            with open(args.output, "w", encoding="utf-8") as f:
                yaml.dump(output_data, f, default_flow_style=False)
            print(f"\n  Ergebnisse gespeichert: {args.output}")


if __name__ == "__main__":
    main()
