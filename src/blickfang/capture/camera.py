"""Webcam-Capture mit Latest-Frame-Slot (/LF100/–/LF120/).

Threading-Modell: Capture-Thread schreibt in einen 1-Slot-Buffer.
Kein Backlog — Latenz wächst sonst unsichtbar auf Sekunden.
"""

from __future__ import annotations

import platform
import threading
import time
from typing import Optional, Tuple

import cv2
import numpy as np

from blickfang.core.config import CaptureConfig


def _select_backend(config: CaptureConfig) -> int:
    """Wählt das passende OpenCV-Backend (/LF100/)."""
    if config.backend == "dshow":
        return cv2.CAP_DSHOW
    elif config.backend == "v4l2":
        return cv2.CAP_V4L2
    elif config.backend == "avfoundation":
        return cv2.CAP_AVFOUNDATION
    elif config.backend == "auto":
        system = platform.system()
        if system == "Windows":
            return cv2.CAP_DSHOW  # MSMF öffnet langsam, Property-Steuerung unzuverlässig
        elif system == "Linux":
            return cv2.CAP_V4L2
        elif system == "Darwin":
            return cv2.CAP_AVFOUNDATION
    return cv2.CAP_ANY


class FrameSource:
    """Abstrakte Frame-Quelle (/LF110/) — Basisklasse."""

    def read(self) -> Tuple[bool, Optional[np.ndarray], float]:
        """Liest einen Frame. Gibt (success, frame, capture_timestamp) zurück."""
        raise NotImplementedError

    def release(self) -> None:
        """Gibt Ressourcen frei."""
        pass

    @property
    def is_open(self) -> bool:
        return False


class CameraSource(FrameSource):
    """Live-Webcam als Frame-Quelle."""

    def __init__(self, config: CaptureConfig):
        self._config = config
        backend = _select_backend(config)
        self._cap = cv2.VideoCapture(config.device_index, backend)

        if not self._cap.isOpened():
            raise RuntimeError(
                f"Kamera {config.device_index} konnte nicht geöffnet werden "
                f"(Backend: {backend})"
            )

        # Auflösung setzen
        self._cap.set(cv2.CAP_PROP_FRAME_WIDTH, config.resolution[0])
        self._cap.set(cv2.CAP_PROP_FRAME_HEIGHT, config.resolution[1])
        self._cap.set(cv2.CAP_PROP_FPS, config.fps)

        # Kamera-Setup (/LF120/)
        self._setup_camera()

    def _setup_camera(self) -> None:
        """Autofokus deaktivieren, Belichtung fixieren (/LF120/)."""
        if self._config.disable_autofocus:
            self._cap.set(cv2.CAP_PROP_AUTOFOCUS, 0)

        if self._config.fix_exposure:
            self._cap.set(cv2.CAP_PROP_AUTO_EXPOSURE, 0.25)  # Manual mode

    def read(self) -> Tuple[bool, Optional[np.ndarray], float]:
        ts = time.perf_counter()
        ret, frame = self._cap.read()
        return ret, frame if ret else None, ts

    def release(self) -> None:
        if self._cap is not None:
            self._cap.release()

    @property
    def is_open(self) -> bool:
        return self._cap is not None and self._cap.isOpened()


class VideoFileSource(FrameSource):
    """Videodatei als Frame-Quelle (/LF110/ — Replay/Test)."""

    def __init__(self, path: str, loop: bool = False):
        self._cap = cv2.VideoCapture(path)
        if not self._cap.isOpened():
            raise RuntimeError(f"Videodatei konnte nicht geöffnet werden: {path}")
        self._loop = loop
        self._path = path
        self._fps = self._cap.get(cv2.CAP_PROP_FPS) or 30.0
        self._frame_interval = 1.0 / self._fps
        self._start_time = time.perf_counter()
        self._frame_count = 0

    def read(self) -> Tuple[bool, Optional[np.ndarray], float]:
        ret, frame = self._cap.read()
        if not ret and self._loop:
            self._cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
            ret, frame = self._cap.read()

        ts = self._start_time + self._frame_count * self._frame_interval
        self._frame_count += 1
        return ret, frame if ret else None, ts

    def release(self) -> None:
        if self._cap is not None:
            self._cap.release()

    @property
    def is_open(self) -> bool:
        return self._cap is not None and self._cap.isOpened()


class CaptureThread:
    """Capture-Thread mit Latest-Frame-Slot (1 Slot, kein Backlog).

    Referenz: Kap. 6.2 Threading-Modell.
    """

    def __init__(self, source: FrameSource):
        self._source = source
        self._lock = threading.Lock()
        self._frame: Optional[np.ndarray] = None
        self._timestamp: float = 0.0
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._frame_count = 0
        self._fps_start = time.perf_counter()
        self._current_fps = 0.0

    def start(self) -> None:
        """Startet den Capture-Thread."""
        self._running = True
        self._thread = threading.Thread(target=self._capture_loop, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        """Stoppt den Capture-Thread."""
        self._running = False
        if self._thread is not None:
            self._thread.join(timeout=2.0)
        self._source.release()

    def get_frame(self) -> Tuple[Optional[np.ndarray], float]:
        """Holt den neuesten Frame (Latest-Frame-Slot)."""
        with self._lock:
            return self._frame, self._timestamp

    @property
    def fps(self) -> float:
        """Aktuelle Capture-FPS."""
        return self._current_fps

    def _capture_loop(self) -> None:
        """Hauptschleife des Capture-Threads."""
        while self._running:
            ret, frame, ts = self._source.read()
            if ret and frame is not None:
                with self._lock:
                    self._frame = frame
                    self._timestamp = ts

                # FPS berechnen
                self._frame_count += 1
                elapsed = time.perf_counter() - self._fps_start
                if elapsed >= 1.0:
                    self._current_fps = self._frame_count / elapsed
                    self._frame_count = 0
                    self._fps_start = time.perf_counter()
            else:
                time.sleep(0.001)
