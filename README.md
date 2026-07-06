# blickfang

**Signaloffene Webcam-Kommunikation für Menschen mit schwerer motorischer Einschränkung**
(ALS, Locked-in-Syndrom, Chorea Huntington, hohe Querschnittslähmung u.ä.)

> **Status: Meilenstein M1 — Implementierung.**
> Der Kalibrier- & Erkennungs-Kern ist implementiert. Alle Anforderungen und das
> Umsetzungskonzept sind in [LASTENHEFT.md](LASTENHEFT.md) definiert.

## Idee in drei Sätzen

Eine normale Webcam filmt die Person; eine **Kalibrierungsphase lernt, welches individuelle,
willentlich erzeugbare Signal** (Blinzeln, Augenbraue, Mundwinkel, Kopfdrehung, …) die Person
zuverlässig erzeugen kann — nichts ist fest verdrahtet. Das erkannte Signal wird zu einem
robusten „virtuellen Schalter" für Ja/Nein-Kommunikation, Buchstaben-Scanning und Sprachausgabe.
Unwillkürliche Bewegungen (Chorea, Spastik, Tremor) werden über eine individuell gelernte
Baseline statistisch vom willentlichen Signal getrennt — ein falsches „Ja" ist gefährlicher als
ein verpasstes Signal.

## Grundsätze

- **Handelsübliche Hardware** — normale Webcam, normaler (auch älterer) Laptop, kein Eyetracker.
- **Nur lokal** — keine Cloud, keine Übertragung von Video- oder Gesichtsdaten.
- **Signaloffen** — die Kalibrierung wählt den besten Kanal pro Person, nicht umgekehrt.
- **Sicherheit vor Geschwindigkeit** — Timeout ist nie eine Antwort; jede Sprachausgabe ist
  abbrechbar; die Software zeigt ehrlich an, wie viele Zufalls-Auslösungen eine Einstellung erwarten lässt.
- **Kein Medizinprodukt** — Kommunikationshilfsmittel, keine Grundlage für medizinisch kritische
  Entscheidungen.

## Installation

### Voraussetzungen

- Python 3.10+
- Webcam (USB oder integriert, ≥ 640×480 @ 30 fps)
- CPU mit AVX-Unterstützung (für MediaPipe)
- Windows 10/11, Linux (x86-64) oder macOS

### Setup

```bash
# Repository klonen
git clone https://github.com/DerSimulant/blickfang.git
cd blickfang

# Abhängigkeiten installieren
pip install -e ".[dev]"

# MediaPipe-Modell herunterladen
wget -O face_landmarker_v2_with_blendshapes.task \
  https://storage.googleapis.com/mediapipe-models/face_landmarker/face_landmarker/float16/latest/face_landmarker.task

# Konfiguration erstellen
cp config/settings.example.yaml config/settings.yaml
```

### Verwendung

```bash
# Kalibrierung durchführen
blickfang-calibrate

# Ja/Nein/PASSE-Kommunikation starten
blickfang-run --person <name>

# Nur mit Tastatur-Schalter (ohne Kamera, zum Testen)
blickfang-run --key-only
```

### Tests

```bash
pytest tests/ -v
```

## Architektur (M1)

```
blickfang/
  LASTENHEFT.md · LICENSE (Apache-2.0) · README.md · pyproject.toml
  config/
    settings.example.yaml     # Fragen/Ansagen, Muster, Zeiten
    profiles/                 # versionierte Personen-Profile (YAML)
  src/blickfang/
    core/events.py            # ChannelFrame + SwitchEvent
    core/config.py            # YAML-Konfigurationsmanagement
    capture/camera.py         # OpenCV, Backend-Wahl, Frame-Slot
    features/face_mesh.py     # MediaPipe-Wrapper (VIDEO-Modus)
    features/channels.py      # Blendshapes + Geometrie → Kanäle
    calibration/session.py    # selbst getaktete Aufnahme, Peaks
    calibration/selector.py   # FP@TP-Ranking, Degenerations-Check
    calibration/profile.py    # versionierte Profile, Schnell-Trim
    detection/baseline.py     # gated Dual-Timescale Median/MAD
    detection/detector.py     # Schmitt-Trigger-Automat
    detection/quality.py      # Liveness, Lichtsprung-Veto, FPS-Test
    switch/base.py            # Switch-Schnittstelle
    switch/video_switch.py    # Detektor-gestützt (Person A)
    switch/key_switch.py      # Tastatur/physischer Schalter (B)
    temporal/patterns.py      # 1×/2×/halten, Debouncing
    io/replay.py              # Log=Replay-Format, deterministisch
    output/tts.py             # pyttsx3, eigener Thread
    output/scanning.py        # 3-Item-Scan, Cancel, KEINE ANTWORT
    ui/scan_ui.py             # Tkinter: Scan-UI + Live-Monitor
    app/calibrate.py          # Entrypoint Kalibrierung
    app/run_yesno.py          # Entrypoint Ja/Nein/PASSE
  tests/                      # synthetische Traces, Replay-Regression
```

## Implementierte Anforderungen (M1)

| Anforderung | Status | Modul |
|---|---|---|
| /LF100/–/LF120/ Capture & Kamera-Setup | ✓ | `capture/camera.py` |
| /LF130/ Lichtsprung-Veto | ✓ | `detection/quality.py` |
| /LF140/ Liveness-Monitor | ✓ | `detection/quality.py` |
| /LF150/ Selbsttest (AVX, FPS) | ✓ | `detection/quality.py` |
| /LF200/–/LF230/ Feature-Extraktion | ✓ | `features/face_mesh.py`, `features/channels.py` |
| /LF300/–/LF380/ Kalibrierung | ✓ | `calibration/` |
| /LF400/–/LF430/ Detektion | ✓ | `detection/baseline.py`, `detection/detector.py` |
| /LF500/–/LF530/ Virtueller Schalter | ✓ | `switch/`, `temporal/patterns.py` |
| /LF600/–/LF630/ Output (Ja/Nein/PASSE, TTS) | ✓ | `output/scanning.py`, `output/tts.py` |
| /LF700/–/LF710/ Live-Monitor & FP-Anzeige | ✓ | `ui/scan_ui.py` |
| /LF730/ Session-Logging | ✓ | `io/replay.py` |
| /LF800/ Replay-Format | ✓ | `io/replay.py` |
| /LF820/ Synthetik-Tests | ✓ | `tests/` |

## Technik

Python · OpenCV · MediaPipe Face Landmarker (52 Blendshapes + 478 Landmarken) · Tkinter ·
pyttsx3 (deutsche TTS) — Details, Architektur und alle Anforderungen: [LASTENHEFT.md](LASTENHEFT.md).

## Lizenz

[Apache-2.0](LICENSE). Es werden ausschließlich lizenzkompatible Abhängigkeiten verwendet;
GPL-Projekte (OptiKey, Dasher, eViacam) dienen nur als Konzept-Referenz, ohne Code-Übernahme.
