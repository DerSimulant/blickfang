# blickfang

**Signaloffene Webcam-Kommunikation für Menschen mit schwerer motorischer Einschränkung**
(ALS, Locked-in-Syndrom, Chorea Huntington, hohe Querschnittslähmung u.ä.)

> **Status: Meilenstein M1 — Voll funktionsfähig.**
> Kalibrier- & Erkennungs-Kern implementiert inkl. Aufnahme-, Annotations-
> und Validierungs-Tools. Alle Anforderungen: [LASTENHEFT.md](LASTENHEFT.md).

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

# Selbsttest durchführen (prüft alles, lädt Modell automatisch herunter)
blickfang-selftest

# Konfiguration erstellen (optional — Standardwerte funktionieren)
cp config/settings.example.yaml config/settings.yaml
```

Das MediaPipe-Modell wird beim ersten Start **automatisch heruntergeladen** (~4 MB).

## Workflow

### Schnellstart (3 Schritte)

```bash
# 1. Selbsttest
blickfang-selftest

# 2. Kalibrierung (mit der Person)
blickfang-calibrate

# 3. Kommunikation starten
blickfang-run --person <Name>
```

### Vollständiger Workflow (mit Aufnahme & Validierung)

```
┌─────────────────┐     ┌──────────────────┐     ┌──────────────────┐
│  1. AUFNEHMEN   │────▶│  2. ANNOTIEREN   │────▶│  3. VALIDIEREN   │
│  blickfang-     │     │  blickfang-      │     │  blickfang-      │
│  record         │     │  annotate        │     │  validate        │
└─────────────────┘     └──────────────────┘     └──────────────────┘
        │                                                 │
        ▼                                                 ▼
┌─────────────────┐                              ┌──────────────────┐
│  4. KALIBRIEREN │                              │  Schwellwert     │
│  blickfang-     │◀─────────────────────────────│  optimieren      │
│  calibrate      │                              └──────────────────┘
└─────────────────┘
        │
        ▼
┌─────────────────┐
│  5. KOMMUNIZIEREN│
│  blickfang-run  │
└─────────────────┘
```

### Schritt 1: Videos aufnehmen (`blickfang-record`)

Nimmt Rohvideos und Feature-Streams auf. Jede Aufnahme bekommt ein **Label**
zur Kategorisierung:

```bash
# Signal-Aufnahme: Person erzeugt bewusst ihr Signal
blickfang-record --person Anna --label signal --duration 60

# Ruhe-Aufnahme: Person ruht (inkl. unwillkürlicher Bewegungen)
blickfang-record --person Anna --label ruhe --duration 180

# Unruhe-Aufnahme: Chorea/Tremor-Phase
blickfang-record --person Anna --label unruhe --duration 120

# Ohne Video (nur Feature-Stream, spart Speicher)
blickfang-record --person Anna --label signal --no-video
```

**Ausgabe:** Ein Verzeichnis pro Aufnahme mit:
- `features.jsonl` — Feature-Stream (für Replay & Validierung)
- `video.avi` — Rohvideo (optional, für visuelle Kontrolle)
- `meta.yaml` — Aufnahme-Metadaten
- `annotations.yaml` — Annotations-Datei (zunächst leer)

### Schritt 2: Annotieren (`blickfang-annotate`)

Markiert Zeitabschnitte in den Aufnahmen mit Labels:

```bash
blickfang-annotate recordings/Anna_20260706_120000_signal/
blickfang-annotate recordings/Anna_20260706_120000_signal/ --channel ear_left
```

**Tasten in der UI:**
| Taste | Funktion |
|-------|----------|
| S | Signal-Segment markieren (Start/Ende) |
| R | Ruhe-Segment markieren |
| U | Unruhe-Segment markieren |
| A | Artefakt markieren |
| Leertaste | Play/Pause |
| ← → | Vor/Zurück (1s) |
| Strg+Z | Rückgängig |
| Strg+S | Speichern |
| ESC | Beenden (speichert automatisch) |

### Schritt 3: Validieren (`blickfang-validate`)

Lässt den Detektor gegen annotierte Aufnahmen laufen:

```bash
# Standard-Validierung
blickfang-validate --profile config/profiles/Anna_v3.yaml --sessions recordings/

# Schwellwert-Sweep (findet optimalen Schwellwert)
blickfang-validate --profile config/profiles/Anna_v3.yaml --sessions recordings/ --sweep

# Ergebnisse speichern
blickfang-validate --profile config/profiles/Anna_v3.yaml --sessions recordings/ --output results.yaml
```

**Ausgabe:**
```
  ✓ Anna_20260706_signal1  TP: 90% (9/10) FP: 0.33/min Latenz: 0.42s
  ✓ Anna_20260706_signal2  TP: 80% (8/10) FP: 0.50/min Latenz: 0.38s
  ─────────────────────────────────────────────────────────
  GESAMT:
    Signale: 17/20 erkannt (85%)
    Fehlauslösungen: 3 (0.41/min)
    Mittlere Latenz: 0.40s

  ★★☆ GUT — Profil ist brauchbar
```

### Schritt 4: Kalibrieren (`blickfang-calibrate`)

Interaktive Kalibrierung mit der Person:

```bash
blickfang-calibrate
blickfang-calibrate --config config/settings.yaml
```

### Schritt 5: Kommunizieren (`blickfang-run`)

```bash
# Mit kalibriertem Profil
blickfang-run --person Anna

# Nur mit Tastatur (zum Testen ohne Kamera)
blickfang-run --key-only

# Mit bestimmtem Profil
blickfang-run --profile config/profiles/Anna_20260706_v3.yaml
```

## Alle Befehle

| Befehl | Funktion |
|--------|----------|
| `blickfang-selftest` | Prüft Installation, Kamera, TTS, lädt Modell |
| `blickfang-record` | Nimmt Videos + Feature-Streams auf |
| `blickfang-annotate` | Annotiert Aufnahmen (Signal/Ruhe/Unruhe) |
| `blickfang-validate` | Testet Detektor gegen annotierte Aufnahmen |
| `blickfang-calibrate` | Interaktive Kalibrierung mit Person |
| `blickfang-run` | Startet Ja/Nein/PASSE-Kommunikation |

## Architektur

```
blickfang/
  LASTENHEFT.md · LICENSE (Apache-2.0) · README.md · pyproject.toml
  config/
    settings.example.yaml     # Fragen/Ansagen, Muster, Zeiten
    profiles/                 # versionierte Personen-Profile (YAML)
  recordings/                 # Aufnahmen (von blickfang-record)
  src/blickfang/
    core/
      events.py               # ChannelFrame + SwitchEvent
      config.py               # YAML-Konfigurationsmanagement
      model_manager.py        # Automatischer Modell-Download
    capture/camera.py         # OpenCV, Backend-Wahl, Frame-Slot
    features/
      face_mesh.py            # MediaPipe-Wrapper (VIDEO-Modus)
      channels.py             # Blendshapes + Geometrie → Kanäle
    calibration/
      session.py              # selbst getaktete Aufnahme, Peaks
      selector.py             # FP@TP-Ranking, Degenerations-Check
      profile.py              # versionierte Profile, Schnell-Trim
    detection/
      baseline.py             # gated Dual-Timescale Median/MAD
      detector.py             # Schmitt-Trigger-Automat (+ HOLD)
      quality.py              # Liveness, Lichtsprung-Veto, FPS-Test
    switch/
      base.py                 # Switch-Schnittstelle
      video_switch.py         # Detektor-gestützt (Person A)
      key_switch.py           # Tastatur/physischer Schalter (B)
    temporal/patterns.py      # 1×/2×/halten, Debouncing
    io/replay.py              # Log=Replay-Format, deterministisch
    output/
      tts.py                  # pyttsx3, eigener Thread
      scanning.py             # 3-Item-Scan, Cancel, KEINE ANTWORT
    ui/scan_ui.py             # Tkinter: Scan-UI + Live-Monitor
    app/
      selftest.py             # Installations-Check
      record.py               # Aufnahme-Tool
      annotate.py             # Annotations-Tool
      validate.py             # Batch-Validierung
      calibrate.py            # Kalibrierung
      run_yesno.py            # Ja/Nein/PASSE-Kommunikation
  tests/                      # 35 Tests (synthetisch + Tools)
```

## Tests

```bash
pytest tests/ -v
```

**35 Tests** abdeckend:
- Schmitt-Trigger-Detektor (Tremor, Signal, Doppelpuls, HOLD)
- Dual-Timescale-Baseline (Gating, MAD-Floor)
- Kalibrierung (Peak-Picking, Kanal-Ranking, Profil-IO)
- Scanning (3-Item, Timeout, Cancel-Countdown)
- Replay (Log + Wiedergabe)
- Tools (Annotation, Validierung, Batch-Runner)

## Technik

Python · OpenCV · MediaPipe Face Landmarker (52 Blendshapes + 478 Landmarken) · Tkinter ·
pyttsx3 (deutsche TTS) — Details, Architektur und alle Anforderungen: [LASTENHEFT.md](LASTENHEFT.md).

## Lizenz

[Apache-2.0](LICENSE). Es werden ausschließlich lizenzkompatible Abhängigkeiten verwendet;
GPL-Projekte (OptiKey, Dasher, eViacam) dienen nur als Konzept-Referenz, ohne Code-Übernahme.
