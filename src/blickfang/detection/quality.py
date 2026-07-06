"""Qualitätsüberwachung: Liveness-Monitor und Lichtsprung-Veto.

Referenz: /LF130/ (Lichtsprung-Veto), /LF140/ (Liveness-Monitor), /LF150/ (Selbsttest).
"""

from __future__ import annotations

import platform
import time
from collections import deque
from typing import Optional

import numpy as np

from blickfang.core.config import DetectionConfig
from blickfang.core.events import QualityState


def check_avx_support() -> bool:
    """Prüft AVX-Unterstützung (/LF150/).

    MediaPipe-Wheels setzen AVX voraus; ohne AVX startet die Inferenz nicht.
    """
    try:
        # Auf Linux: /proc/cpuinfo prüfen
        if platform.system() == "Linux":
            with open("/proc/cpuinfo", "r") as f:
                cpuinfo = f.read()
            return "avx" in cpuinfo.lower()
        elif platform.system() == "Windows":
            # Auf Windows: Versuch über cpuid oder einfach MediaPipe laden
            try:
                import mediapipe  # noqa: F401
                return True
            except Exception:
                return False
        elif platform.system() == "Darwin":
            # macOS: sysctl
            import subprocess
            result = subprocess.run(
                ["sysctl", "-n", "machdep.cpu.features"],
                capture_output=True, text=True
            )
            return "AVX" in result.stdout.upper()
    except Exception:
        pass
    # Fallback: Annahme OK
    return True


class FPSSelfTest:
    """FPS-Selbsttest beim Start (/LF150/).

    Misst effektive Verarbeitungs-FPS und warnt unter 12 FPS.
    """

    MIN_FPS = 12.0

    def __init__(self):
        self._timestamps: deque = deque(maxlen=60)
        self._current_fps: float = 0.0

    def tick(self) -> None:
        """Registriert einen verarbeiteten Frame."""
        self._timestamps.append(time.perf_counter())

    @property
    def fps(self) -> float:
        """Aktuelle FPS (gleitender Durchschnitt)."""
        if len(self._timestamps) < 2:
            return 0.0
        elapsed = self._timestamps[-1] - self._timestamps[0]
        if elapsed < 0.01:
            return 0.0
        self._current_fps = (len(self._timestamps) - 1) / elapsed
        return self._current_fps

    @property
    def is_sufficient(self) -> bool:
        """True wenn FPS über Minimum."""
        return self.fps >= self.MIN_FPS


class LightJumpDetector:
    """Lichtsprung-Veto (/LF130/).

    Erkennt abrupte Beleuchtungsänderungen und erzwingt eine Kommandosperre.
    """

    def __init__(self, config: DetectionConfig):
        self._threshold = config.light_jump_threshold
        self._veto_duration = config.light_veto_duration_s
        self._prev_brightness: Optional[float] = None
        self._veto_until: float = 0.0

    def update(self, frame: np.ndarray) -> bool:
        """Prüft Frame auf Lichtsprung.

        Args:
            frame: BGR-Frame von OpenCV.

        Returns:
            True wenn Veto aktiv (Lichtsprung erkannt oder noch gesperrt).
        """
        # Mittlere Helligkeit berechnen (schnell über Grauwert-Mittel)
        gray = np.mean(frame)  # Vereinfacht: Mittel über alle Kanäle
        brightness = gray / 255.0

        now = time.perf_counter()

        if self._prev_brightness is not None:
            change = abs(brightness - self._prev_brightness)
            if change > self._threshold:
                self._veto_until = now + self._veto_duration

        self._prev_brightness = brightness

        return now < self._veto_until

    @property
    def is_vetoed(self) -> bool:
        """True wenn Veto aktuell aktiv."""
        return time.perf_counter() < self._veto_until

    @property
    def remaining_s(self) -> float:
        """Verbleibende Veto-Zeit in Sekunden."""
        remaining = self._veto_until - time.perf_counter()
        return max(0.0, remaining)


class LivenessMonitor:
    """Liveness-/Qualitätsmonitor (/LF140/).

    Bei verlorenem Gesicht, starker Verdeckung oder degradierter
    Trackingqualität darf das System keine Kommandos emittieren.
    """

    def __init__(self, jitter_threshold: float = 0.02, window_size: int = 10):
        """
        Args:
            jitter_threshold: Maximaler Landmark-Jitter (normiert) für OK-Status.
            window_size: Anzahl Frames für Jitter-Berechnung.
        """
        self._jitter_threshold = jitter_threshold
        self._window_size = window_size
        self._landmark_history: deque = deque(maxlen=window_size)
        self._state = QualityState.OK
        self._face_lost_count = 0

    def update(
        self,
        face_detected: bool,
        landmarks: Optional[np.ndarray] = None,
    ) -> QualityState:
        """Aktualisiert den Qualitätszustand.

        Args:
            face_detected: Ob ein Gesicht erkannt wurde.
            landmarks: Landmarken-Array (478, 3) falls erkannt.

        Returns:
            Aktueller QualityState.
        """
        if not face_detected:
            self._face_lost_count += 1
            if self._face_lost_count >= 3:  # 3 Frames ohne Gesicht → LOST
                self._state = QualityState.LOST
            return self._state

        self._face_lost_count = 0

        # Jitter-Berechnung als Proxy für Tracking-Qualität
        if landmarks is not None:
            self._landmark_history.append(landmarks.copy())

            if len(self._landmark_history) >= 3:
                jitter = self._compute_jitter()
                if jitter > self._jitter_threshold:
                    self._state = QualityState.DEGRADED
                else:
                    self._state = QualityState.OK
            else:
                self._state = QualityState.OK
        else:
            self._state = QualityState.OK

        return self._state

    def _compute_jitter(self) -> float:
        """Berechnet Landmark-Jitter als mittlere Frame-zu-Frame-Differenz."""
        if len(self._landmark_history) < 2:
            return 0.0

        diffs = []
        for i in range(1, len(self._landmark_history)):
            diff = np.mean(
                np.abs(self._landmark_history[i] - self._landmark_history[i - 1])
            )
            diffs.append(diff)

        return float(np.mean(diffs))

    @property
    def state(self) -> QualityState:
        return self._state
