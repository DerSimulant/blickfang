"""Profil-Verwaltung: versionierte YAML-Profile (/LF370/–/LF380/).

Profile speichern: Kanal, Baseline-Statistik, Schwellwert-Delta, Haltezeit,
MAD-Floor, Validierungs-Messwerte. Mehrere Versionen pro Person (Tagesform).
"""

from __future__ import annotations

import logging
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Set

import numpy as np
import yaml

from blickfang.calibration.selector import ChannelScore

logger = logging.getLogger(__name__)

_PROFILES_DIR = Path(__file__).resolve().parents[3] / "config" / "profiles"


@dataclass
class ValidationResult:
    """Ergebnis der Validierungsrunde (/LF360/)."""

    tp_rate: float = 0.0                # True-Positive-Rate
    fp_per_min: float = 0.0             # False-Positives pro Minute
    signals_tested: int = 0
    signals_detected: int = 0
    rest_duration_s: float = 0.0
    false_positives: int = 0


@dataclass
class CalibrationProfile:
    """Kalibrierungsprofil einer Person (/LF370/).

    Wird als YAML gespeichert mit allen relevanten Parametern.
    """

    # Identifikation
    person_name: str = ""
    version: int = 1
    created: str = ""
    notes: str = ""

    # Gewählter Kanal
    channel_name: str = ""
    channel_direction: int = 1          # +1 oder -1

    # Baseline-Statistik
    baseline_median: float = 0.0
    baseline_mad: float = 0.0
    mad_floor: float = 0.0             # /LF331/, /LF420/

    # Schwellwert-Parameter
    threshold_delta: float = 0.0        # Relative Schwelle (/LF430/)
    hysteresis_factor: float = 0.3

    # Zeitparameter (in Sekunden, nie Frames!)
    hold_time_s: float = 0.4
    refractory_s: float = 1.0

    # Bestätigungsmuster (/LF530/)
    confirmation_pattern: str = "single"  # single | double | hold
    double_window_s: float = 1.5
    hold_duration_s: float = 1.0

    # Gesperrte Regionen (/LF350/)
    blocked_regions: List[str] = field(default_factory=list)

    # Validierungs-Messwerte (/LF360/)
    validation: Optional[ValidationResult] = None

    # Kanal-Ranking (Top 5 für Referenz)
    ranking_top5: List[Dict] = field(default_factory=list)

    def save(self, directory: Optional[Path] = None) -> Path:
        """Speichert das Profil als YAML.

        Returns:
            Pfad zur gespeicherten Datei.
        """
        if directory is None:
            directory = _PROFILES_DIR

        directory.mkdir(parents=True, exist_ok=True)

        if not self.created:
            self.created = datetime.now().isoformat()

        # Dateiname: person_datum_version.yaml
        date_str = datetime.now().strftime("%Y%m%d")
        filename = f"{self.person_name}_{date_str}_v{self.version}.yaml"
        filepath = directory / filename

        # Sicherstellen, dass kein Überschreiben
        while filepath.exists():
            self.version += 1
            filename = f"{self.person_name}_{date_str}_v{self.version}.yaml"
            filepath = directory / filename

        data = self._to_dict()

        with open(filepath, "w", encoding="utf-8") as f:
            yaml.dump(data, f, default_flow_style=False, allow_unicode=True,
                      sort_keys=False)

        logger.info(f"Profil gespeichert: {filepath}")
        return filepath

    def _to_dict(self) -> Dict:
        """Konvertiert Profil in ein serialisierbares Dict."""
        data = {
            "person_name": self.person_name,
            "version": self.version,
            "created": self.created,
            "notes": self.notes,
            "channel": {
                "name": self.channel_name,
                "direction": self.channel_direction,
            },
            "baseline": {
                "median": self.baseline_median,
                "mad": self.baseline_mad,
                "mad_floor": self.mad_floor,
            },
            "threshold": {
                "delta": self.threshold_delta,
                "hysteresis_factor": self.hysteresis_factor,
            },
            "timing": {
                "hold_time_s": self.hold_time_s,
                "refractory_s": self.refractory_s,
            },
            "confirmation": {
                "pattern": self.confirmation_pattern,
                "double_window_s": self.double_window_s,
                "hold_duration_s": self.hold_duration_s,
            },
            "blocked_regions": self.blocked_regions,
        }

        if self.validation:
            data["validation"] = {
                "tp_rate": self.validation.tp_rate,
                "fp_per_min": self.validation.fp_per_min,
                "signals_tested": self.validation.signals_tested,
                "signals_detected": self.validation.signals_detected,
                "rest_duration_s": self.validation.rest_duration_s,
                "false_positives": self.validation.false_positives,
            }

        if self.ranking_top5:
            data["ranking_top5"] = self.ranking_top5

        return data

    @classmethod
    def load(cls, filepath: Path) -> CalibrationProfile:
        """Lädt ein Profil aus einer YAML-Datei."""
        with open(filepath, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f)

        profile = cls()
        profile.person_name = data.get("person_name", "")
        profile.version = data.get("version", 1)
        profile.created = data.get("created", "")
        profile.notes = data.get("notes", "")

        channel = data.get("channel", {})
        profile.channel_name = channel.get("name", "")
        profile.channel_direction = channel.get("direction", 1)

        baseline = data.get("baseline", {})
        profile.baseline_median = baseline.get("median", 0.0)
        profile.baseline_mad = baseline.get("mad", 0.0)
        profile.mad_floor = baseline.get("mad_floor", 0.0)

        threshold = data.get("threshold", {})
        profile.threshold_delta = threshold.get("delta", 0.0)
        profile.hysteresis_factor = threshold.get("hysteresis_factor", 0.3)

        timing = data.get("timing", {})
        profile.hold_time_s = timing.get("hold_time_s", 0.4)
        profile.refractory_s = timing.get("refractory_s", 1.0)

        confirmation = data.get("confirmation", {})
        profile.confirmation_pattern = confirmation.get("pattern", "single")
        profile.double_window_s = confirmation.get("double_window_s", 1.5)
        profile.hold_duration_s = confirmation.get("hold_duration_s", 1.0)

        profile.blocked_regions = data.get("blocked_regions", [])

        validation_data = data.get("validation")
        if validation_data:
            profile.validation = ValidationResult(
                tp_rate=validation_data.get("tp_rate", 0.0),
                fp_per_min=validation_data.get("fp_per_min", 0.0),
                signals_tested=validation_data.get("signals_tested", 0),
                signals_detected=validation_data.get("signals_detected", 0),
                rest_duration_s=validation_data.get("rest_duration_s", 0.0),
                false_positives=validation_data.get("false_positives", 0),
            )

        profile.ranking_top5 = data.get("ranking_top5", [])
        return profile

    @classmethod
    def from_channel_score(
        cls,
        score: ChannelScore,
        person_name: str,
        blocked_regions: Optional[Set[str]] = None,
    ) -> CalibrationProfile:
        """Erstellt ein Profil aus einem ChannelScore."""
        profile = cls()
        profile.person_name = person_name
        profile.channel_name = score.channel_name
        profile.channel_direction = score.direction
        profile.baseline_median = score.neutral_median
        profile.baseline_mad = score.neutral_mad
        profile.mad_floor = score.mad_floor
        profile.threshold_delta = score.threshold_delta
        profile.blocked_regions = list(blocked_regions) if blocked_regions else []
        profile.created = datetime.now().isoformat()
        return profile


class QuickTrim:
    """Schnell-Trim: Nur Schwellwert/Baseline nachziehen (/LF380/).

    Dauer: < 2 min. Ändert nur Baseline-Statistik und Schwellwert-Delta
    eines bestehenden Profils.
    """

    def __init__(self, profile: CalibrationProfile):
        self._profile = profile
        self._neutral_values: List[float] = []

    def add_neutral_sample(self, value: float) -> None:
        """Fügt einen Neutral-Wert hinzu."""
        self._neutral_values.append(value)

    def apply(self) -> CalibrationProfile:
        """Wendet den Trim auf das Profil an.

        Returns:
            Aktualisiertes Profil (neue Version).
        """
        if len(self._neutral_values) < 30:
            logger.warning("Zu wenige Neutral-Samples für Trim")
            return self._profile

        values = np.array(self._neutral_values)
        new_median = float(np.median(values))
        new_mad = float(np.median(np.abs(values - new_median))) * 1.4826

        # MAD-Floor beachten (/LF420/)
        new_mad = max(new_mad, self._profile.mad_floor)

        # Profil aktualisieren
        self._profile.baseline_median = new_median
        self._profile.baseline_mad = new_mad
        self._profile.version += 1
        self._profile.created = datetime.now().isoformat()
        self._profile.notes += f" [Trim am {datetime.now().strftime('%Y-%m-%d %H:%M')}]"

        return self._profile


def list_profiles(
    person_name: Optional[str] = None,
    directory: Optional[Path] = None,
) -> List[Path]:
    """Listet alle verfügbaren Profile.

    Args:
        person_name: Optional Filter nach Person.
        directory: Profilverzeichnis.

    Returns:
        Liste der Profil-Dateipfade, neueste zuerst.
    """
    if directory is None:
        directory = _PROFILES_DIR

    if not directory.exists():
        return []

    profiles = sorted(directory.glob("*.yaml"), reverse=True)

    if person_name:
        profiles = [p for p in profiles if p.stem.startswith(person_name)]

    return profiles
