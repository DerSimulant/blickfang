"""MediaPipe Face Landmarker Wrapper (/LF200/).

Extrahiert 478 Landmarken, 52 Blendshape-Scores und Transformationsmatrix
im VIDEO-Modus.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import numpy as np

try:
    import mediapipe as mp
    from mediapipe.tasks import python as mp_python
    from mediapipe.tasks.python import vision as mp_vision
    from mediapipe.framework.formats import landmark_pb2
    HAS_MEDIAPIPE = True
except ImportError:
    HAS_MEDIAPIPE = False

from blickfang.core.config import FeaturesConfig
from blickfang.core.model_manager import get_model_path

logger = logging.getLogger(__name__)


@dataclass
class FaceResult:
    """Ergebnis der Feature-Extraktion für einen Frame."""

    landmarks: Optional[np.ndarray] = None          # (478, 3) normierte Koordinaten
    blendshapes: Dict[str, float] = field(default_factory=dict)  # 52 Blendshape-Scores
    transform_matrix: Optional[np.ndarray] = None   # 4x4 Transformationsmatrix
    face_detected: bool = False
    detection_confidence: float = 0.0


class FaceMeshExtractor:
    """MediaPipe Face Landmarker im VIDEO-Modus.

    Referenz: /LF200/ — Feature-Extraktion.
    """

    def __init__(self, config: FeaturesConfig):
        if not HAS_MEDIAPIPE:
            raise RuntimeError(
                "MediaPipe ist nicht installiert. "
                "Bitte installieren: pip install mediapipe"
            )

        self._config = config
        self._landmarker: Optional[mp_vision.FaceLandmarker] = None
        self._frame_timestamp_ms: int = 0
        self._latest_result: Optional[FaceResult] = None

        self._init_landmarker()

    def _init_landmarker(self) -> None:
        """Initialisiert den Face Landmarker."""
        # Model-Asset-Pfad bestimmen
        model_path = self._find_model_asset()

        base_options = mp_python.BaseOptions(
            model_asset_path=str(model_path)
        )

        options = mp_vision.FaceLandmarkerOptions(
            base_options=base_options,
            running_mode=mp_vision.RunningMode.VIDEO,
            num_faces=1,
            min_face_detection_confidence=self._config.min_detection_confidence,
            min_face_presence_confidence=self._config.min_tracking_confidence,
            min_tracking_confidence=self._config.min_tracking_confidence,
            output_face_blendshapes=True,
            output_facial_transformation_matrixes=True,
        )

        self._landmarker = mp_vision.FaceLandmarker.create_from_options(options)

    def _find_model_asset(self) -> Path:
        """Sucht das MediaPipe-Modell. Lädt es automatisch herunter wenn nötig."""
        return get_model_path(self._config.model_asset)

    def process_frame(
        self, frame: np.ndarray, timestamp_ms: int
    ) -> FaceResult:
        """Verarbeitet einen Frame und extrahiert Gesichtsmerkmale.

        Args:
            frame: BGR-Frame von OpenCV.
            timestamp_ms: Monoton steigender Zeitstempel in Millisekunden.

        Returns:
            FaceResult mit Landmarken, Blendshapes und Transformationsmatrix.
        """
        result = FaceResult()

        if self._landmarker is None:
            return result

        # Sicherstellen, dass Zeitstempel monoton steigt
        if timestamp_ms <= self._frame_timestamp_ms:
            timestamp_ms = self._frame_timestamp_ms + 1
        self._frame_timestamp_ms = timestamp_ms

        # BGR → RGB für MediaPipe
        rgb_frame = frame[:, :, ::-1].copy()
        mp_image = mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb_frame)

        try:
            detection_result = self._landmarker.detect_for_video(
                mp_image, timestamp_ms
            )
        except Exception as e:
            logger.debug(f"MediaPipe-Fehler: {e}")
            return result

        if not detection_result.face_landmarks:
            return result

        # Landmarken extrahieren (erstes Gesicht)
        face_landmarks = detection_result.face_landmarks[0]
        landmarks_array = np.array(
            [[lm.x, lm.y, lm.z] for lm in face_landmarks],
            dtype=np.float32,
        )
        result.landmarks = landmarks_array
        result.face_detected = True

        # Blendshapes extrahieren
        if detection_result.face_blendshapes:
            blendshapes = detection_result.face_blendshapes[0]
            result.blendshapes = {
                bs.category_name: bs.score for bs in blendshapes
            }

        # Transformationsmatrix
        if detection_result.facial_transformation_matrixes:
            matrix = detection_result.facial_transformation_matrixes[0]
            result.transform_matrix = np.array(matrix, dtype=np.float32).reshape(4, 4)

        # Konfidenz aus dem ersten Landmark (Proxy)
        if face_landmarks:
            result.detection_confidence = getattr(
                face_landmarks[0], "presence", 1.0
            ) if hasattr(face_landmarks[0], "presence") else 1.0

        self._latest_result = result
        return result

    def close(self) -> None:
        """Gibt Ressourcen frei."""
        if self._landmarker is not None:
            self._landmarker.close()
            self._landmarker = None
