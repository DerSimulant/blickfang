"""Konfigurationsmanagement — YAML-basiert (/LF720/).

Lädt settings.yaml und stellt typisierte Zugriffe bereit.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

import yaml


_DEFAULT_CONFIG_PATH = Path(__file__).resolve().parents[3] / "config" / "settings.yaml"
_EXAMPLE_CONFIG_PATH = Path(__file__).resolve().parents[3] / "config" / "settings.example.yaml"


@dataclass
class CaptureConfig:
    backend: str = "auto"
    device_index: int = 0
    resolution: List[int] = field(default_factory=lambda: [640, 480])
    fps: int = 30
    disable_autofocus: bool = True
    fix_exposure: bool = True


@dataclass
class FeaturesConfig:
    model_asset: str = "face_landmarker_v2_with_blendshapes.task"
    min_detection_confidence: float = 0.5
    min_tracking_confidence: float = 0.5


@dataclass
class CalibrationConfig:
    signal_count: int = 10
    neutral_duration_s: float = 180.0
    peak_window_s: float = 3.0
    validation_signals: int = 10
    validation_rest_s: float = 120.0


@dataclass
class DetectionConfig:
    hysteresis_factor: float = 0.3
    hold_time_s: float = 0.4
    refractory_s: float = 1.0
    baseline_slow_window_s: float = 120.0
    baseline_fast_window_s: float = 5.0
    light_jump_threshold: float = 0.15
    light_veto_duration_s: float = 2.0


@dataclass
class SwitchConfig:
    source: str = "video"
    key_binding: str = "space"


@dataclass
class PatternsConfig:
    confirmation: str = "single"
    double_window_s: float = 1.5
    hold_duration_s: float = 1.0


@dataclass
class OutputConfig:
    mode: str = "yesno"
    items: List[str] = field(default_factory=lambda: ["JA", "NEIN", "PASSE"])
    scan_speed_s: float = 2.0
    max_cycles: int = 3
    cancel_countdown_s: float = 2.5


@dataclass
class TTSConfig:
    engine: str = "pyttsx3"
    language: str = "de"
    rate: int = 150
    piper_model: str = ""


@dataclass
class LoggingConfig:
    enabled: bool = False
    output_dir: str = "./sessions"
    format: str = "jsonl"


@dataclass
class UIConfig:
    monitor_visible: bool = True
    fullscreen: bool = False
    font_size: int = 24


@dataclass
class AppConfig:
    """Gesamtkonfiguration der Anwendung."""

    capture: CaptureConfig = field(default_factory=CaptureConfig)
    features: FeaturesConfig = field(default_factory=FeaturesConfig)
    calibration: CalibrationConfig = field(default_factory=CalibrationConfig)
    detection: DetectionConfig = field(default_factory=DetectionConfig)
    switch: SwitchConfig = field(default_factory=SwitchConfig)
    patterns: PatternsConfig = field(default_factory=PatternsConfig)
    output: OutputConfig = field(default_factory=OutputConfig)
    tts: TTSConfig = field(default_factory=TTSConfig)
    logging: LoggingConfig = field(default_factory=LoggingConfig)
    ui: UIConfig = field(default_factory=UIConfig)


def _merge_dict(target: Any, source: Dict[str, Any]) -> None:
    """Rekursives Mergen von Dict-Werten in Dataclass-Felder."""
    if not isinstance(source, dict):
        return
    for key, value in source.items():
        if hasattr(target, key):
            current = getattr(target, key)
            if hasattr(current, "__dataclass_fields__") and isinstance(value, dict):
                _merge_dict(current, value)
            else:
                setattr(target, key, value)


def load_config(path: Optional[Path] = None) -> AppConfig:
    """Lädt die Konfiguration aus YAML. Fallback auf Beispiel-Datei."""
    config = AppConfig()

    if path is None:
        path = _DEFAULT_CONFIG_PATH

    if not path.exists():
        # Fallback auf Beispiel-Konfiguration
        path = _EXAMPLE_CONFIG_PATH

    if path.exists():
        with open(path, "r", encoding="utf-8") as f:
            raw = yaml.safe_load(f) or {}
        _merge_dict(config, raw)

    return config
