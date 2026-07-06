"""Entrypoint: blickfang-selftest — Schneller Installations-Check.

Prüft alle Voraussetzungen und gibt einen klaren Status:
- Python-Version
- Abhängigkeiten (OpenCV, MediaPipe, pyttsx3)
- AVX-Unterstützung
- MediaPipe-Modell (lädt automatisch herunter)
- Kamera-Verfügbarkeit
- TTS-Engine
"""

from __future__ import annotations

import sys
import platform


def main():
    """Führt den Selbsttest durch."""
    print("=" * 50)
    print("  blickfang — Selbsttest")
    print("=" * 50)
    print()

    errors = []
    warnings = []

    # 1. Python-Version
    py_version = sys.version_info
    if py_version >= (3, 10):
        print(f"  ✓ Python {py_version.major}.{py_version.minor}.{py_version.micro}")
    else:
        msg = f"Python {py_version.major}.{py_version.minor} — mindestens 3.10 erforderlich"
        print(f"  ✗ {msg}")
        errors.append(msg)

    # 2. OpenCV
    try:
        import cv2
        print(f"  ✓ OpenCV {cv2.__version__}")
    except ImportError:
        msg = "OpenCV nicht installiert (pip install opencv-python)"
        print(f"  ✗ {msg}")
        errors.append(msg)

    # 3. NumPy
    try:
        import numpy as np
        print(f"  ✓ NumPy {np.__version__}")
    except ImportError:
        msg = "NumPy nicht installiert"
        print(f"  ✗ {msg}")
        errors.append(msg)

    # 4. MediaPipe
    try:
        import mediapipe as mp
        print(f"  ✓ MediaPipe {mp.__version__}")
    except ImportError:
        msg = "MediaPipe nicht installiert (pip install mediapipe)"
        print(f"  ✗ {msg}")
        errors.append(msg)

    # 5. PyYAML
    try:
        import yaml
        print(f"  ✓ PyYAML verfügbar")
    except ImportError:
        msg = "PyYAML nicht installiert"
        print(f"  ✗ {msg}")
        errors.append(msg)

    # 6. pyttsx3
    try:
        import pyttsx3
        print(f"  ✓ pyttsx3 verfügbar")
    except ImportError:
        msg = "pyttsx3 nicht installiert (pip install pyttsx3)"
        print(f"  ⚠ {msg}")
        warnings.append(msg)

    # 7. AVX-Unterstützung
    print()
    try:
        from blickfang.detection.quality import check_avx_support
        if check_avx_support():
            print(f"  ✓ AVX-Unterstützung vorhanden")
        else:
            msg = "Keine AVX-Unterstützung — MediaPipe benötigt AVX"
            print(f"  ✗ {msg}")
            errors.append(msg)
    except Exception as e:
        print(f"  ⚠ AVX-Check fehlgeschlagen: {e}")
        warnings.append(f"AVX-Check: {e}")

    # 8. MediaPipe-Modell
    try:
        from blickfang.core.model_manager import get_model_path, model_info
        info = model_info()
        if info["installed"]:
            print(f"  ✓ MediaPipe-Modell vorhanden ({info['size_mb']} MB)")
        else:
            print(f"  ⚠ MediaPipe-Modell nicht gefunden — wird beim ersten Start heruntergeladen")
            warnings.append("Modell wird beim ersten Start heruntergeladen (~4 MB)")
    except Exception as e:
        print(f"  ⚠ Modell-Check: {e}")

    # 9. Kamera
    print()
    try:
        import cv2
        cap = cv2.VideoCapture(0)
        if cap.isOpened():
            ret, frame = cap.read()
            if ret and frame is not None:
                h, w = frame.shape[:2]
                print(f"  ✓ Kamera verfügbar ({w}×{h})")
            else:
                print(f"  ⚠ Kamera geöffnet, aber liefert keine Frames")
                warnings.append("Kamera liefert keine Frames")
            cap.release()
        else:
            print(f"  ⚠ Keine Kamera gefunden (Index 0)")
            warnings.append("Keine Kamera — für Video-Modus erforderlich")
    except Exception as e:
        print(f"  ⚠ Kamera-Test: {e}")
        warnings.append(f"Kamera: {e}")

    # 10. TTS-Test
    try:
        import pyttsx3
        engine = pyttsx3.init()
        voices = engine.getProperty("voices")
        german_voices = [v for v in voices if "german" in v.name.lower() or "de" in v.id.lower()]
        if german_voices:
            print(f"  ✓ Deutsche TTS-Stimme verfügbar ({german_voices[0].name})")
        else:
            print(f"  ⚠ Keine deutsche TTS-Stimme — englische wird verwendet")
            warnings.append("Keine deutsche TTS-Stimme")
        engine.stop()
    except Exception as e:
        print(f"  ⚠ TTS-Test: {e}")
        warnings.append(f"TTS: {e}")

    # 11. Tkinter
    try:
        import tkinter as tk
        root = tk.Tk()
        root.withdraw()
        root.destroy()
        print(f"  ✓ Tkinter verfügbar")
    except Exception as e:
        msg = f"Tkinter nicht verfügbar: {e}"
        print(f"  ✗ {msg}")
        errors.append(msg)

    # Zusammenfassung
    print()
    print("-" * 50)
    if not errors:
        print(f"  ✓ SELBSTTEST BESTANDEN")
        if warnings:
            print(f"    ({len(warnings)} Warnungen — siehe oben)")
        print()
        print("  Nächste Schritte:")
        print("    1. blickfang-record --person <Name> --label signal")
        print("    2. blickfang-calibrate")
        print("    3. blickfang-run --person <Name>")
    else:
        print(f"  ✗ SELBSTTEST FEHLGESCHLAGEN ({len(errors)} Fehler)")
        for err in errors:
            print(f"    • {err}")

    print()
    return 0 if not errors else 1


if __name__ == "__main__":
    sys.exit(main())
