"""Automatischer Modell-Download und -Verwaltung.

Lädt das MediaPipe Face Landmarker Modell automatisch herunter,
wenn es nicht vorhanden ist. Speichert es im Benutzerverzeichnis.
"""

from __future__ import annotations

import hashlib
import logging
import os
import shutil
import urllib.request
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

# MediaPipe Face Landmarker Modell
_MODEL_URL = (
    "https://storage.googleapis.com/mediapipe-models/"
    "face_landmarker/face_landmarker/float16/latest/face_landmarker.task"
)
_MODEL_FILENAME = "face_landmarker_v2_with_blendshapes.task"

# Speicherort: ~/.blickfang/models/
_MODEL_DIR = Path.home() / ".blickfang" / "models"


def get_model_path(filename: Optional[str] = None) -> Path:
    """Gibt den Pfad zum Modell zurück.

    Sucht in folgender Reihenfolge:
    1. Aktuelles Arbeitsverzeichnis
    2. ~/.blickfang/models/
    3. Projektverzeichnis

    Falls nicht gefunden, wird das Modell automatisch heruntergeladen.
    """
    if filename is None:
        filename = _MODEL_FILENAME

    # Suchpfade
    candidates = [
        Path.cwd() / filename,
        _MODEL_DIR / filename,
        Path(__file__).resolve().parents[3] / filename,
    ]

    for path in candidates:
        if path.exists():
            logger.info(f"Modell gefunden: {path}")
            return path

    # Nicht gefunden → herunterladen
    logger.info(f"Modell nicht gefunden. Lade herunter...")
    return download_model(filename)


def download_model(filename: Optional[str] = None, url: Optional[str] = None) -> Path:
    """Lädt das MediaPipe-Modell herunter.

    Args:
        filename: Zieldateiname.
        url: Download-URL.

    Returns:
        Pfad zur heruntergeladenen Datei.
    """
    if filename is None:
        filename = _MODEL_FILENAME
    if url is None:
        url = _MODEL_URL

    _MODEL_DIR.mkdir(parents=True, exist_ok=True)
    target_path = _MODEL_DIR / filename

    if target_path.exists():
        logger.info(f"Modell bereits vorhanden: {target_path}")
        return target_path

    print(f"Lade MediaPipe-Modell herunter...")
    print(f"  URL: {url}")
    print(f"  Ziel: {target_path}")

    try:
        # Download mit Fortschrittsanzeige
        tmp_path = target_path.with_suffix(".tmp")

        def _progress_hook(block_num, block_size, total_size):
            if total_size > 0:
                downloaded = block_num * block_size
                percent = min(100, downloaded * 100 // total_size)
                mb_downloaded = downloaded / (1024 * 1024)
                mb_total = total_size / (1024 * 1024)
                print(
                    f"\r  Fortschritt: {percent}% ({mb_downloaded:.1f}/{mb_total:.1f} MB)",
                    end="", flush=True,
                )

        urllib.request.urlretrieve(url, tmp_path, reporthook=_progress_hook)
        print()  # Neue Zeile nach Fortschrittsanzeige

        # Verschieben
        shutil.move(str(tmp_path), str(target_path))
        logger.info(f"Modell heruntergeladen: {target_path}")
        print(f"  ✓ Download abgeschlossen: {target_path}")

    except Exception as e:
        logger.error(f"Download fehlgeschlagen: {e}")
        print(f"  ✗ Download fehlgeschlagen: {e}")
        print(f"  Bitte manuell herunterladen:")
        print(f"    wget -O {target_path} {url}")
        raise RuntimeError(
            f"MediaPipe-Modell konnte nicht heruntergeladen werden: {e}"
        ) from e

    return target_path


def ensure_model_available(filename: Optional[str] = None) -> Path:
    """Stellt sicher, dass das Modell verfügbar ist.

    Kombiniert Suche und Download. Gibt den Pfad zurück oder
    wirft einen Fehler.
    """
    return get_model_path(filename)


def model_info() -> dict:
    """Gibt Informationen über das installierte Modell zurück."""
    path = None
    for candidate in [
        Path.cwd() / _MODEL_FILENAME,
        _MODEL_DIR / _MODEL_FILENAME,
    ]:
        if candidate.exists():
            path = candidate
            break

    if path is None:
        return {"installed": False, "path": None, "size_mb": 0}

    size_mb = path.stat().st_size / (1024 * 1024)
    return {
        "installed": True,
        "path": str(path),
        "size_mb": round(size_mb, 1),
    }
