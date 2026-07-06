# blickfang

# blickfang

**Signaloffene Webcam-Kommunikation für Menschen mit schwerer motorischer Einschränkung**
(ALS, Locked-in-Syndrom, Chorea Huntington, hohe Querschnittslähmung u.ä.)

> **Status: Lastenheft-Phase.** Es existiert noch kein Code — die Anforderungen und das
> Umsetzungskonzept sind in [LASTENHEFT.md](LASTENHEFT.md) definiert. Die Implementierung von
> Meilenstein M1 (Kalibrier- & Erkennungs-Kern) ist der nächste Schritt.

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

## Technik (geplant)

Python · OpenCV · MediaPipe Face Landmarker (52 Blendshapes + 478 Landmarken) · Tkinter ·
pyttsx3/Piper (deutsche TTS) — Details, Architektur und alle Anforderungen: [LASTENHEFT.md](LASTENHEFT.md).

## Lizenz

[Apache-2.0](LICENSE). Es werden ausschließlich lizenzkompatible Abhängigkeiten verwendet;
GPL-Projekte (OptiKey, Dasher, eViacam) dienen nur als Konzept-Referenz, ohne Code-Übernahme.
