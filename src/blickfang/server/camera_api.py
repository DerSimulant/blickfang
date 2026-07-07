"""Kamera-API: Geräte-Auswahl, Vorschau-Stream, Gesichtserkennung-Status.

Endpoints:
  GET  /api/camera/devices     → Liste verfügbarer Kameras
  POST /api/camera/select      → Kamera auswählen
  GET  /api/camera/stream      → MJPEG-Stream (Vorschau mit Landmarks)
  GET  /api/camera/status      → Kamera-Status + Gesichtserkennung
"""

from __future__ import annotations

import logging
import platform
import threading
import time
from typing import Any, Dict, List, Optional

import cv2
import numpy as np
from fastapi import APIRouter
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/camera", tags=["camera"])

# ─── Globaler Kamera-Zustand ─────────────────────────────────────────────

_preview_state: Optional["CameraPreview"] = None


class CameraDevice(BaseModel):
    index: int
    name: str
    available: bool = True


class CameraSelectRequest(BaseModel):
    device_index: int


class CameraStatusResponse(BaseModel):
    active: bool = False
    device_index: int = 0
    face_detected: bool = False
    fps: float = 0.0
    resolution: str = ""


# ─── Kamera-Vorschau-Manager ─────────────────────────────────────────────


class CameraPreview:
    """Verwaltet die Kamera-Vorschau mit Gesichtserkennung-Overlay."""

    def __init__(self, device_index: int = 0):
        self.device_index = device_index
        self.face_detected = False
        self.fps = 0.0
        self.resolution = ""
        self._cap: Optional[cv2.VideoCapture] = None
        self._running = False
        self._frame: Optional[np.ndarray] = None
        self._lock = threading.Lock()
        self._extractor = None
        self._frame_count = 0
        self._fps_start = time.perf_counter()

    def start(self) -> bool:
        """Startet die Kamera-Vorschau."""
        self.stop()

        backend = cv2.CAP_DSHOW if platform.system() == "Windows" else cv2.CAP_ANY
        self._cap = cv2.VideoCapture(self.device_index, backend)

        if not self._cap.isOpened():
            logger.error(f"Kamera {self.device_index} konnte nicht geöffnet werden")
            return False

        self._cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
        self._cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
        self._cap.set(cv2.CAP_PROP_FPS, 30)

        w = int(self._cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        h = int(self._cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        self.resolution = f"{w}x{h}"

        # Face-Extractor initialisieren
        try:
            from blickfang.features.face_mesh import FaceMeshExtractor
            self._extractor = FaceMeshExtractor()
        except Exception as e:
            logger.warning(f"Face-Extractor nicht verfügbar: {e}")

        self._running = True
        threading.Thread(target=self._capture_loop, daemon=True).start()
        logger.info(f"Kamera-Vorschau gestartet (Device: {self.device_index}, {self.resolution})")
        return True

    def stop(self) -> None:
        """Stoppt die Kamera-Vorschau."""
        self._running = False
        time.sleep(0.1)
        if self._cap:
            self._cap.release()
            self._cap = None
        self._frame = None

    @property
    def active(self) -> bool:
        return self._running and self._cap is not None

    def get_jpeg(self) -> Optional[bytes]:
        """Gibt den aktuellen Frame als JPEG zurück."""
        with self._lock:
            if self._frame is None:
                return None
            _, buf = cv2.imencode('.jpg', self._frame, [cv2.IMWRITE_JPEG_QUALITY, 70])
            return buf.tobytes()

    def _capture_loop(self) -> None:
        """Capture + Gesichtserkennung + Overlay."""
        while self._running and self._cap and self._cap.isOpened():
            ret, frame = self._cap.read()
            if not ret or frame is None:
                time.sleep(0.01)
                continue

            # Gesichtserkennung
            display_frame = frame.copy()
            self.face_detected = False

            if self._extractor:
                try:
                    result = self._extractor.process(frame)
                    if result is not None:
                        self.face_detected = True
                        # Grüner Rahmen wenn Gesicht erkannt
                        h, w = display_frame.shape[:2]
                        cv2.rectangle(display_frame, (10, 10), (w - 10, h - 10),
                                     (0, 255, 0), 3)
                        cv2.putText(display_frame, "Gesicht erkannt",
                                   (20, 40), cv2.FONT_HERSHEY_SIMPLEX, 1.0,
                                   (0, 255, 0), 2)
                    else:
                        # Roter Rahmen wenn kein Gesicht
                        h, w = display_frame.shape[:2]
                        cv2.rectangle(display_frame, (10, 10), (w - 10, h - 10),
                                     (0, 0, 255), 3)
                        cv2.putText(display_frame, "Kein Gesicht erkannt",
                                   (20, 40), cv2.FONT_HERSHEY_SIMPLEX, 1.0,
                                   (0, 0, 255), 2)
                except Exception:
                    pass

            with self._lock:
                self._frame = display_frame

            # FPS berechnen
            self._frame_count += 1
            elapsed = time.perf_counter() - self._fps_start
            if elapsed >= 1.0:
                self.fps = self._frame_count / elapsed
                self._frame_count = 0
                self._fps_start = time.perf_counter()

            time.sleep(0.03)  # ~30 FPS


# ─── Hilfsfunktionen ─────────────────────────────────────────────────────


def _enumerate_cameras(max_check: int = 5) -> List[CameraDevice]:
    """Prüft welche Kamera-Indizes verfügbar sind."""
    devices = []
    backend = cv2.CAP_DSHOW if platform.system() == "Windows" else cv2.CAP_ANY

    for i in range(max_check):
        cap = cv2.VideoCapture(i, backend)
        if cap.isOpened():
            w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
            h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
            name = f"Kamera {i} ({w}x{h})"
            devices.append(CameraDevice(index=i, name=name, available=True))
            cap.release()
        else:
            # Nicht verfügbar — nicht in Liste aufnehmen
            pass

    if not devices:
        devices.append(CameraDevice(index=0, name="Keine Kamera gefunden", available=False))

    return devices


# ─── REST-Endpoints ──────────────────────────────────────────────────────


@router.get("/devices")
async def list_cameras() -> List[Dict[str, Any]]:
    """Listet alle verfügbaren Kameras."""
    devices = _enumerate_cameras()
    return [d.dict() for d in devices]


@router.post("/select")
async def select_camera(req: CameraSelectRequest) -> Dict[str, Any]:
    """Wählt eine Kamera aus und startet die Vorschau."""
    global _preview_state

    if _preview_state:
        _preview_state.stop()

    _preview_state = CameraPreview(device_index=req.device_index)
    success = _preview_state.start()

    if success:
        return {"status": "ok", "device_index": req.device_index}
    return {"error": f"Kamera {req.device_index} konnte nicht geöffnet werden"}


@router.get("/stream")
async def camera_stream():
    """MJPEG-Stream für die Kamera-Vorschau."""
    if not _preview_state or not _preview_state.active:
        # Automatisch starten mit Default-Kamera
        global _preview_state
        _preview_state = CameraPreview(device_index=0)
        _preview_state.start()
        time.sleep(0.5)  # Kurz warten bis erste Frames da sind

    def generate():
        while _preview_state and _preview_state.active:
            jpeg = _preview_state.get_jpeg()
            if jpeg:
                yield (
                    b'--frame\r\n'
                    b'Content-Type: image/jpeg\r\n\r\n'
                    + jpeg + b'\r\n'
                )
            time.sleep(0.05)  # ~20 FPS für Stream

    return StreamingResponse(
        generate(),
        media_type='multipart/x-mixed-replace; boundary=frame',
    )


@router.get("/status")
async def camera_status() -> Dict[str, Any]:
    """Gibt den aktuellen Kamera-Status zurück."""
    if _preview_state and _preview_state.active:
        return {
            "active": True,
            "device_index": _preview_state.device_index,
            "face_detected": _preview_state.face_detected,
            "fps": round(_preview_state.fps, 1),
            "resolution": _preview_state.resolution,
        }
    return {"active": False, "device_index": 0, "face_detected": False, "fps": 0, "resolution": ""}


@router.post("/stop")
async def stop_camera() -> Dict[str, Any]:
    """Stoppt die Kamera-Vorschau."""
    global _preview_state
    if _preview_state:
        _preview_state.stop()
        _preview_state = None
    return {"status": "ok"}
