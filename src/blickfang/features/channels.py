"""Kanalberechnung aus Landmarken und Blendshapes (/LF210/–/LF230/).

Alle Kanäle sind benannt und bilden zusammen einen ChannelFrame mit
Capture-Zeitstempel. Normierung auf Interokularabstand.
"""

from __future__ import annotations

import math
from typing import Dict, List, Optional, Set

import numpy as np

from blickfang.core.events import ChannelFrame, QualityState
from blickfang.features.face_mesh import FaceResult


# MediaPipe Landmark-Indizes (Auswahl)
# Referenz: https://github.com/google/mediapipe/blob/master/mediapipe/modules/face_geometry/data/canonical_face_model_uv_visualization.png
_LEFT_EYE_TOP = 159
_LEFT_EYE_BOTTOM = 145
_LEFT_EYE_INNER = 133
_LEFT_EYE_OUTER = 33

_RIGHT_EYE_TOP = 386
_RIGHT_EYE_BOTTOM = 374
_RIGHT_EYE_INNER = 362
_RIGHT_EYE_OUTER = 263

_LEFT_BROW_INNER = 107
_LEFT_BROW_OUTER = 70
_RIGHT_BROW_INNER = 336
_RIGHT_BROW_OUTER = 300

_MOUTH_LEFT = 61
_MOUTH_RIGHT = 291
_MOUTH_TOP = 13
_MOUTH_BOTTOM = 14

_NOSE_TIP = 1
_CHIN = 152
_FOREHEAD = 10

# Interokularabstand: Mitte linkes Auge ↔ Mitte rechtes Auge
_LEFT_EYE_CENTER = 468   # MediaPipe iris center left
_RIGHT_EYE_CENTER = 473  # MediaPipe iris center right


def _distance(landmarks: np.ndarray, i: int, j: int) -> float:
    """Euklidischer Abstand zwischen zwei Landmarken (2D: x, y)."""
    diff = landmarks[i, :2] - landmarks[j, :2]
    return float(np.linalg.norm(diff))


def _eye_aspect_ratio(landmarks: np.ndarray, top: int, bottom: int,
                      inner: int, outer: int) -> float:
    """Eye Aspect Ratio (EAR) nach Soukupová & Čech.

    EAR = vertical_dist / horizontal_dist
    """
    vertical = _distance(landmarks, top, bottom)
    horizontal = _distance(landmarks, inner, outer)
    if horizontal < 1e-6:
        return 0.0
    return vertical / horizontal


def _interocular_distance(landmarks: np.ndarray) -> float:
    """Interokularabstand für Normierung."""
    # Verwende Augeninnenkanten als robustere Alternative
    return _distance(landmarks, _LEFT_EYE_INNER, _RIGHT_EYE_INNER)


def _head_pose_from_landmarks(landmarks: np.ndarray) -> Dict[str, float]:
    """Grobe Kopfpose aus Landmarken (Yaw, Pitch, Roll).

    Vereinfachte Berechnung basierend auf Nasenspitze und Gesichtskonturen.
    """
    # Vereinfachte Pose-Schätzung über Landmark-Geometrie
    nose = landmarks[_NOSE_TIP, :3]
    chin = landmarks[_CHIN, :3]
    forehead = landmarks[_FOREHEAD, :3]
    left_eye = landmarks[_LEFT_EYE_OUTER, :3]
    right_eye = landmarks[_RIGHT_EYE_OUTER, :3]

    # Yaw: Asymmetrie Nase zu Augen
    eye_center = (left_eye + right_eye) / 2.0
    nose_offset_x = nose[0] - eye_center[0]
    eye_width = abs(right_eye[0] - left_eye[0])
    yaw = nose_offset_x / max(eye_width, 1e-6) * 90.0

    # Pitch: Nase relativ zu Stirn-Kinn-Achse
    face_height = abs(forehead[1] - chin[1])
    nose_relative_y = (nose[1] - forehead[1]) / max(face_height, 1e-6)
    pitch = (nose_relative_y - 0.4) * 90.0  # 0.4 ist Normalposition

    # Roll: Augenachse
    dy = right_eye[1] - left_eye[1]
    dx = right_eye[0] - left_eye[0]
    roll = math.degrees(math.atan2(dy, max(abs(dx), 1e-6)))

    return {"head_yaw": yaw, "head_pitch": pitch, "head_roll": roll}


class ChannelComputer:
    """Berechnet benannte Kanäle aus FaceResult (/LF210/).

    Kanäle werden auf den Interokularabstand normiert.
    Erweiterbar für zusätzliche Körperregionen (/LF230/).
    """

    def __init__(self, blocked_regions: Optional[Set[str]] = None):
        """
        Args:
            blocked_regions: Manuell gesperrte Kanalgruppen (/LF350/).
                             z.B. {"mouth", "left_eye"}
        """
        self._blocked_regions = blocked_regions or set()

    def compute(self, face_result: FaceResult, timestamp: float) -> ChannelFrame:
        """Berechnet alle Kanäle aus einem FaceResult.

        Returns:
            ChannelFrame mit allen verfügbaren Kanälen.
        """
        if not face_result.face_detected or face_result.landmarks is None:
            return ChannelFrame(
                timestamp=timestamp,
                channels={},
                quality=QualityState.LOST,
            )

        landmarks = face_result.landmarks
        channels: Dict[str, float] = {}

        # Interokularabstand für Normierung
        iod = _interocular_distance(landmarks)
        if iod < 1e-6:
            return ChannelFrame(
                timestamp=timestamp,
                channels={},
                quality=QualityState.DEGRADED,
            )

        # --- Geometrische Kanäle (/LF210/) ---

        # Eye Aspect Ratio (EAR)
        if "left_eye" not in self._blocked_regions:
            channels["ear_left"] = _eye_aspect_ratio(
                landmarks, _LEFT_EYE_TOP, _LEFT_EYE_BOTTOM,
                _LEFT_EYE_INNER, _LEFT_EYE_OUTER
            )

        if "right_eye" not in self._blocked_regions:
            channels["ear_right"] = _eye_aspect_ratio(
                landmarks, _RIGHT_EYE_TOP, _RIGHT_EYE_BOTTOM,
                _RIGHT_EYE_INNER, _RIGHT_EYE_OUTER
            )

        # Brauen-Augen-Abstand (normiert auf IOD)
        if "left_brow" not in self._blocked_regions:
            brow_eye_left = _distance(landmarks, _LEFT_BROW_INNER, _LEFT_EYE_TOP)
            channels["brow_left"] = brow_eye_left / iod

        if "right_brow" not in self._blocked_regions:
            brow_eye_right = _distance(landmarks, _RIGHT_BROW_INNER, _RIGHT_EYE_TOP)
            channels["brow_right"] = brow_eye_right / iod

        # Mundwinkel-Auslenkung (normiert auf IOD)
        if "mouth" not in self._blocked_regions:
            mouth_width = _distance(landmarks, _MOUTH_LEFT, _MOUTH_RIGHT)
            channels["mouth_width"] = mouth_width / iod

            mouth_height = _distance(landmarks, _MOUTH_TOP, _MOUTH_BOTTOM)
            channels["mouth_open"] = mouth_height / iod

        # Kopfpose
        if "head" not in self._blocked_regions:
            pose = _head_pose_from_landmarks(landmarks)
            channels.update(pose)

        # --- Blendshape-Kanäle (direkt von MediaPipe) ---
        if face_result.blendshapes:
            for name, score in face_result.blendshapes.items():
                region = self._blendshape_region(name)
                if region not in self._blocked_regions:
                    channels[f"bs_{name}"] = score

        return ChannelFrame(
            timestamp=timestamp,
            channels=channels,
            quality=QualityState.OK,
        )

    @staticmethod
    def _blendshape_region(name: str) -> str:
        """Ordnet einen Blendshape einer Region zu (für Blocking)."""
        name_lower = name.lower()
        if "eye" in name_lower or "blink" in name_lower:
            if "left" in name_lower:
                return "left_eye"
            elif "right" in name_lower:
                return "right_eye"
            return "eyes"
        elif "brow" in name_lower:
            return "brow"
        elif "mouth" in name_lower or "jaw" in name_lower or "lip" in name_lower:
            return "mouth"
        elif "cheek" in name_lower or "nose" in name_lower:
            return "face"
        return "other"

    @property
    def channel_names(self) -> List[str]:
        """Liste aller möglichen Kanalnamen (ohne Blocking)."""
        geometric = [
            "ear_left", "ear_right",
            "brow_left", "brow_right",
            "mouth_width", "mouth_open",
            "head_yaw", "head_pitch", "head_roll",
        ]
        # Blendshape-Namen sind dynamisch; hier die bekannten 52
        return geometric  # Vollständige Liste erst zur Laufzeit
