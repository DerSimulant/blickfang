"""Zentrale Datentypen: ChannelFrame und SwitchEvent.

Referenz: /LF500/ — Schnittstelle in zwei Ebenen.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Dict, Optional


class EventType(Enum):
    """Typen von Switch-Events."""

    SINGLE = auto()       # Einzelnes Signal
    DOUBLE = auto()       # Doppel-Signal im Zeitfenster
    HOLD = auto()         # Gehaltenes Signal
    RELEASE = auto()      # Signal losgelassen (nach HOLD)


class DetectorState(Enum):
    """Zustände des Schmitt-Trigger-Automaten (/LF400/)."""

    IDLE = auto()
    RISING = auto()
    HELD = auto()
    CONFIRM = auto()
    EMIT = auto()
    REFRACTORY = auto()


class QualityState(Enum):
    """Qualitätszustände des Liveness-Monitors (/LF140/)."""

    OK = auto()
    DEGRADED = auto()       # Tracking-Qualität eingeschränkt
    LOST = auto()           # Gesicht verloren
    LIGHT_VETO = auto()     # Lichtsprung-Sperre aktiv


@dataclass(frozen=True, slots=True)
class ChannelFrame:
    """Kontinuierliche, normierte Kanalwerte mit Capture-Zeitstempel.

    Konsumiert von: Monitor, Logging, Replay, Detektion.
    Referenz: /LF220/, /LF500/.
    """

    timestamp: float                    # Capture-Zeitstempel (time.perf_counter)
    channels: Dict[str, float]          # Kanalname → normierter Wert
    quality: QualityState = QualityState.OK
    raw_fps: float = 0.0                # Aktuelle Verarbeitungs-FPS

    @property
    def is_valid(self) -> bool:
        """Frame darf nur bei OK-Qualität für Kommandos genutzt werden."""
        return self.quality == QualityState.OK


@dataclass(frozen=True, slots=True)
class SwitchEvent:
    """Diskretes Switch-Event — konsumiert von Mapping/Scanning.

    Referenz: /LF500/.
    """

    source_id: str                      # z.B. "video_switch", "key_switch"
    event_type: EventType
    timestamp_capture: float            # Capture-Zeitstempel des auslösenden Frames
    confidence: float = 1.0             # 0..1, bei key_switch immer 1.0
    channel_name: Optional[str] = None  # Welcher Kanal hat ausgelöst (bei video)


@dataclass
class SystemStatus:
    """Gesamtsystem-Status für UI-Anzeige."""

    detector_state: DetectorState = DetectorState.IDLE
    quality_state: QualityState = QualityState.OK
    current_channel: str = ""
    current_value: float = 0.0
    baseline_value: float = 0.0
    threshold_value: float = 0.0
    fps: float = 0.0
    veto_active: bool = False
    veto_remaining_s: float = 0.0
    expected_fp_per_min: float = 0.0    # /LF710/ Anti-FC-Anzeige
