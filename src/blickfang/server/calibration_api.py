"""Kalibrierungs-API für Browser-basierte Kalibrierung.

Steuert den gesamten Kalibrierungsablauf über REST-Endpoints:
1. Session starten (Kamera aktivieren)
2. Signal-Phase: Frames sammeln, Peaks finden
3. Caregiver bestätigt/lehnt Events ab
4. Neutral-Phase: Ruhephase aufzeichnen
5. Ranking: Besten Kanal bestimmen
6. Profil speichern

Der Zustand wird über WebSocket an das Frontend gestreamt.
"""

from __future__ import annotations

import asyncio
import json
import logging
import threading
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import APIRouter
from pydantic import BaseModel

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/calibration", tags=["calibration"])

# ─── Globaler Kalibrierungs-Zustand ──────────────────────────────────────

_calibration_state: Optional["CalibrationManager"] = None


def get_calibration_manager() -> Optional["CalibrationManager"]:
    return _calibration_state


# ─── Pydantic-Modelle ────────────────────────────────────────────────────


class CalibStartRequest(BaseModel):
    person_name: str
    signal_count: int = 10
    neutral_duration_s: float = 60.0


class EventConfirmation(BaseModel):
    event_index: int
    confirmed: bool


class CalibStatusResponse(BaseModel):
    active: bool = False
    phase: str = "idle"
    person_name: str = ""
    frames_collected: int = 0
    elapsed_s: float = 0.0
    signal_events: List[Dict[str, Any]] = []
    confirmed_count: int = 0
    ranking: List[Dict[str, Any]] = []
    best_channel: str = ""
    error: str = ""
    live_channels: Dict[str, float] = {}


# ─── Kalibrierungs-Manager ───────────────────────────────────────────────


class CalibrationManager:
    """Verwaltet eine laufende Kalibrierungssitzung."""

    def __init__(self, person_name: str, signal_count: int = 10, neutral_duration_s: float = 60.0):
        self.person_name = person_name
        self.signal_count = signal_count
        self.neutral_duration_s = neutral_duration_s

        self.phase = "idle"
        self.error = ""
        self.frames_collected = 0
        self.start_time = 0.0
        self.signal_events: List[Dict[str, Any]] = []
        self.confirmed_count = 0
        self.ranking: List[Dict[str, Any]] = []
        self.best_channel = ""
        self.profile_path = ""
        self.live_channels: Dict[str, float] = {}

        self._session = None
        self._selector = None
        self._camera = None
        self._extractor = None
        self._channel_computer = None
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._loop: Optional[asyncio.AbstractEventLoop] = None

    def set_loop(self, loop: asyncio.AbstractEventLoop):
        self._loop = loop

    @property
    def elapsed_s(self) -> float:
        if self.start_time:
            return time.perf_counter() - self.start_time
        return 0.0

    def start_signal_phase(self) -> None:
        """Startet die Signal-Aufnahme mit Kamera."""
        self.phase = "signal"
        self.start_time = time.perf_counter()
        self._running = True

        self._thread = threading.Thread(target=self._capture_loop, daemon=True)
        self._thread.start()
        logger.info(f"Kalibrierung gestartet für '{self.person_name}' (Signal-Phase)")

    def stop_signal_phase(self) -> List[Dict[str, Any]]:
        """Stoppt die Signal-Phase und findet Peaks."""
        self._running = False
        if self._thread:
            self._thread.join(timeout=3.0)

        if self._session:
            events = self._session.finalize_signal_phase()
            self.signal_events = [
                {
                    "index": i,
                    "channel": e.channel_name,
                    "timestamp": round(e.timestamp, 2),
                    "peak_value": round(e.peak_value, 4),
                    "confirmed": e.confirmed,
                }
                for i, e in enumerate(events)
            ]
            self.phase = "confirm"
            logger.info(f"Signal-Phase beendet: {len(events)} Events gefunden")
            return self.signal_events
        return []

    def confirm_event(self, index: int, confirmed: bool) -> None:
        """Bestätigt oder lehnt ein Event ab."""
        if self._session and index < len(self._session.recording.signal_events):
            event = self._session.recording.signal_events[index]
            if confirmed:
                self._session.confirm_event(event)
            else:
                self._session.reject_event(event)

            # Update local state
            if index < len(self.signal_events):
                self.signal_events[index]["confirmed"] = confirmed

            self.confirmed_count = len(self._session.confirmed_events)

    def start_neutral_phase(self) -> None:
        """Startet die Neutral-/Ruhephase."""
        self.phase = "neutral"
        self.start_time = time.perf_counter()
        self._running = True

        if self._session:
            self._session.start_neutral_phase()

        self._thread = threading.Thread(target=self._capture_loop, daemon=True)
        self._thread.start()
        logger.info(f"Neutral-Phase gestartet ({self.neutral_duration_s}s)")

    def stop_neutral_phase(self) -> None:
        """Stoppt die Neutral-Phase."""
        self._running = False
        if self._thread:
            self._thread.join(timeout=3.0)
        logger.info("Neutral-Phase beendet")

    def compute_ranking(self) -> List[Dict[str, Any]]:
        """Berechnet das Kanal-Ranking."""
        if not self._session or not self._selector:
            self.error = "Keine Session oder Selector verfügbar"
            return []

        self.phase = "ranking"
        ranking = self._selector.rank_channels(
            self._session.recording,
            self._session.confirmed_events,
        )

        self.ranking = [
            {
                "channel": s.channel_name,
                "fp_at_90tp": round(s.fp_rate_at_90tp, 4),
                "auc": round(s.auc, 3),
                "direction": s.direction,
                "threshold_delta": round(s.threshold_delta, 4),
            }
            for s in ranking.ranked[:10]
        ]

        if ranking.best_channel:
            self.best_channel = ranking.best_channel
            logger.info(f"Bester Kanal: {ranking.best_channel} "
                       f"(FP@90TP: {ranking.best_score.fp_rate_at_90tp:.4f})")
        else:
            self.error = "Kein geeigneter Kanal gefunden"

        return self.ranking

    def save_profile(self) -> str:
        """Speichert das Profil."""
        if not self._session or not self._selector:
            self.error = "Keine Session verfügbar"
            return ""

        self.phase = "saving"

        ranking = self._selector.rank_channels(
            self._session.recording,
            self._session.confirmed_events,
        )

        if not ranking.best_score:
            self.error = "Kein Kanal zum Speichern"
            return ""

        from blickfang.calibration.profile import CalibrationProfile

        profile = CalibrationProfile.from_channel_score(
            ranking.best_score, self.person_name
        )
        profile.ranking_top5 = [
            {"channel": s.channel_name, "fp_at_90tp": s.fp_rate_at_90tp, "auc": s.auc}
            for s in ranking.ranked[:5]
        ]

        filepath = profile.save()
        self.profile_path = str(filepath)
        self.phase = "done"
        logger.info(f"Profil gespeichert: {filepath}")
        return str(filepath)

    def cancel(self) -> None:
        """Bricht die Kalibrierung ab."""
        self._running = False
        if self._thread:
            self._thread.join(timeout=3.0)
        self.phase = "cancelled"
        self._cleanup()

    def _capture_loop(self) -> None:
        """Frame-Capture-Loop in eigenem Thread."""
        try:
            if not self._camera:
                self._init_capture()

            while self._running:
                frame = self._camera.get_frame()
                if frame is None:
                    time.sleep(0.01)
                    continue

                result = self._extractor.process(frame)
                if result is None:
                    time.sleep(0.01)
                    continue

                channel_values = self._channel_computer.compute(result)
                self.live_channels = {
                    k: round(v, 4) for k, v in list(channel_values.items())[:10]
                }

                # ChannelFrame erstellen
                from blickfang.core.events import ChannelFrame
                channel_frame = ChannelFrame(
                    timestamp=time.perf_counter() - self.start_time,
                    channels=channel_values,
                )

                if self._session:
                    self._session.add_frame(channel_frame)
                    self.frames_collected = len(self._session.recording.frames)

                # Auto-Stop bei Neutral-Phase nach Dauer
                if (self.phase == "neutral" and
                    self.elapsed_s >= self.neutral_duration_s):
                    self._running = False
                    break

                time.sleep(0.01)

        except Exception as e:
            logger.error(f"Capture-Fehler: {e}")
            self.error = str(e)
        finally:
            pass

    def _init_capture(self) -> None:
        """Initialisiert Kamera und Feature-Extraktion."""
        from blickfang.capture.camera import CameraSource
        from blickfang.features.face_mesh import FaceMeshExtractor
        from blickfang.features.channels import ChannelComputer
        from blickfang.calibration.session import CalibrationSession
        from blickfang.calibration.selector import ChannelSelector
        from blickfang.core.config import CalibrationConfig

        config = CalibrationConfig(
            signal_count=self.signal_count,
            neutral_duration_s=self.neutral_duration_s,
        )

        self._camera = CameraSource()
        self._camera.start()
        self._extractor = FaceMeshExtractor()
        self._channel_computer = ChannelComputer()
        self._session = CalibrationSession(config)
        self._selector = ChannelSelector()

        # Signal-Phase starten
        if self.phase == "signal":
            self._session.start_signal_phase()

    def _cleanup(self) -> None:
        """Räumt Ressourcen auf."""
        if self._camera:
            try:
                self._camera.stop()
            except Exception:
                pass
            self._camera = None

    def get_status(self) -> Dict[str, Any]:
        """Gibt den aktuellen Status zurück."""
        return {
            "active": self.phase not in ("idle", "done", "cancelled"),
            "phase": self.phase,
            "person_name": self.person_name,
            "frames_collected": self.frames_collected,
            "elapsed_s": round(self.elapsed_s, 1),
            "signal_events": self.signal_events,
            "confirmed_count": self.confirmed_count,
            "ranking": self.ranking,
            "best_channel": self.best_channel,
            "error": self.error,
            "live_channels": self.live_channels,
            "profile_path": self.profile_path,
        }


# ─── REST-Endpoints ──────────────────────────────────────────────────────


@router.get("/status")
async def calibration_status() -> Dict[str, Any]:
    """Gibt den aktuellen Kalibrierungs-Status zurück."""
    mgr = get_calibration_manager()
    if mgr:
        return mgr.get_status()
    return {"active": False, "phase": "idle"}


@router.post("/start")
async def start_calibration(req: CalibStartRequest) -> Dict[str, Any]:
    """Startet eine neue Kalibrierungssitzung."""
    global _calibration_state

    # Alte Session abbrechen
    if _calibration_state:
        _calibration_state.cancel()

    _calibration_state = CalibrationManager(
        person_name=req.person_name,
        signal_count=req.signal_count,
        neutral_duration_s=req.neutral_duration_s,
    )

    try:
        loop = asyncio.get_event_loop()
        _calibration_state.set_loop(loop)
    except RuntimeError:
        pass

    _calibration_state.start_signal_phase()
    return {"status": "ok", "phase": "signal"}


@router.post("/stop-signal")
async def stop_signal_phase() -> Dict[str, Any]:
    """Stoppt die Signal-Phase und gibt gefundene Events zurück."""
    mgr = get_calibration_manager()
    if not mgr:
        return {"error": "Keine aktive Kalibrierung"}

    events = mgr.stop_signal_phase()
    return {"status": "ok", "events": events, "count": len(events)}


@router.post("/confirm-event")
async def confirm_event(req: EventConfirmation) -> Dict[str, Any]:
    """Bestätigt oder lehnt ein Signal-Event ab."""
    mgr = get_calibration_manager()
    if not mgr:
        return {"error": "Keine aktive Kalibrierung"}

    mgr.confirm_event(req.event_index, req.confirmed)
    return {"status": "ok", "confirmed_count": mgr.confirmed_count}


@router.post("/confirm-all")
async def confirm_all_events() -> Dict[str, Any]:
    """Bestätigt alle Events auf einmal."""
    mgr = get_calibration_manager()
    if not mgr:
        return {"error": "Keine aktive Kalibrierung"}

    for i in range(len(mgr.signal_events)):
        mgr.confirm_event(i, True)

    return {"status": "ok", "confirmed_count": mgr.confirmed_count}


@router.post("/start-neutral")
async def start_neutral_phase() -> Dict[str, Any]:
    """Startet die Neutral-/Ruhephase."""
    mgr = get_calibration_manager()
    if not mgr:
        return {"error": "Keine aktive Kalibrierung"}

    if mgr.confirmed_count < 3:
        return {"error": f"Mindestens 3 bestätigte Events nötig (aktuell: {mgr.confirmed_count})"}

    mgr.start_neutral_phase()
    return {"status": "ok", "phase": "neutral", "duration_s": mgr.neutral_duration_s}


@router.post("/stop-neutral")
async def stop_neutral_phase() -> Dict[str, Any]:
    """Stoppt die Neutral-Phase und berechnet das Ranking."""
    mgr = get_calibration_manager()
    if not mgr:
        return {"error": "Keine aktive Kalibrierung"}

    mgr.stop_neutral_phase()
    ranking = mgr.compute_ranking()
    return {"status": "ok", "ranking": ranking, "best_channel": mgr.best_channel}


@router.post("/save-profile")
async def save_profile() -> Dict[str, Any]:
    """Speichert das Kalibrierungsprofil."""
    mgr = get_calibration_manager()
    if not mgr:
        return {"error": "Keine aktive Kalibrierung"}

    path = mgr.save_profile()
    if path:
        return {"status": "ok", "path": path}
    return {"error": mgr.error or "Profil konnte nicht gespeichert werden"}


@router.post("/cancel")
async def cancel_calibration() -> Dict[str, Any]:
    """Bricht die Kalibrierung ab."""
    global _calibration_state
    if _calibration_state:
        _calibration_state.cancel()
        _calibration_state = None
    return {"status": "ok"}
