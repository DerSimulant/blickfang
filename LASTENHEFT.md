# Lastenheft — Projekt „blickfang"

**Signaloffene Webcam-Kommunikation für Menschen mit schwerer motorischer Einschränkung**

| | |
|---|---|
| Dokument | Lastenheft (Anforderungen + gewähltes Umsetzungskonzept) |
| Version | 1.0 — 2026-07-06 |
| Status | Entwurf zur Abnahme |
| Lizenz des Projekts | Apache-2.0 |
| Arbeitsname | blickfang (Ordner- und Paketname, später umbenennbar) |

---

## 1. Zielbestimmung

### 1.1 Problem

Menschen mit schwerer motorischer Einschränkung (ALS, Locked-in-Syndrom, Chorea Huntington,
hohe Querschnittslähmung u.ä.) verlieren Sprache und die meisten Muskelbewegungen — nicht aber
ihr Bewusstsein und ihren Kommunikationswillen. Kommerzielle AAC-Systeme (Augmentative and
Alternative Communication) setzen häufig teure Spezial-Eyetracker voraus; freie Lösungen sind
oft auf ein festes Signal (z.B. Blinzeln) verdrahtet, das nicht jede Person erzeugen kann.

### 1.2 Ziel

Eine **Open-Source-Software**, die auf **handelsüblicher Hardware (normale Webcam, normaler
Laptop)** läuft und über eine **Kalibrierungsphase pro Person lernt**, welches individuelle,
**willentlich erzeugbare Signal** (Blinzeln, Augenbraue, Mundwinkel, Kopfdrehung, …) zuverlässig
erkennbar ist. Dieses Signal wird zu einem robusten „virtuellen Schalter", der Kommunikation
(Ja/Nein, Buchstaben-Scanning, Sprachausgabe) und perspektivisch Computersteuerung ermöglicht.

**Oberstes Schutzziel:** Unwillkürliche Bewegungen (Chorea, Spastik, Tremor) dürfen nicht als
Kommando fehlinterpretiert werden. Ein falsch gesprochenes „Ja" ist gefährlicher als ein
verpasstes Signal.

### 1.3 Leitpersonen (Personas)

**Person A — Chorea Huntington.**
Kann willentliche Bewegungen erzeugen, aber unwillkürliche choreatische Bewegungen ähneln
einem beabsichtigten Signal. Konsequenz: Die Erkennung ist **Anomalieerkennung gegen eine
individuell gelernte Baseline der Bewegungsunruhe** (Amplitude, Frequenz, Dauer), keine reine
Gestenklassifikation. Einstellbare Bestätigungslogik (z.B. Signal 2× im Zeitfenster) mit
transparentem Trade-off Robustheit ↔ Geschwindigkeit.

**Person B — Hohe Querschnittslähmung.**
Nutzt heute Ein-Schalter-Linear-Scanning (Balldruck, Buchstaben laufen lassen) — funktioniert,
ist aber sehr langsam. Der zuverlässige Schalter existiert bereits; der Hebel liegt in der
**Encodierungs-/Output-Schicht**: Zeilen-Spalten-Scanning, häufigkeitsoptimiertes deutsches
Layout, Wortvorhersage, optional ein zweiter (schwächerer) Videosignalkanal für ein schnelleres
2D-Raster.

**Architektur-Konsequenz:** Beide Personen werden vom **selben Grundsystem** bedient — Person A
über den Video-Signalweg, Person B über einen physischen Schalter als alternative Quelle
derselben „virtuellen Schalter"-Schnittstelle, mit unterschiedlicher Kalibrierung/Konfiguration.

### 1.4 Abgrenzung (Nicht-Ziele)

- **Kein Medizinprodukt.** blickfang ist ein Kommunikationshilfsmittel, keine Grundlage für
  medizinisch kritische Entscheidungen (Therapieabbruch, Einwilligungen o.ä.). Ein entsprechender
  Disclaimer ist Teil der Dokumentation und der Software. Die MDR-Einordnung ist ein offener
  Punkt (Kap. 9).
- **Kein Eyetracker-Ersatz.** Keine präzise Blickpunktbestimmung; Iris-Merkmale werden nur als
  ein Signalkanal unter vielen genutzt.
- **Keine Cloud.** Verarbeitung ausschließlich lokal (siehe /LN30/).
- **Kein Brain-Computer-Interface.** Es wird ausschließlich sichtbare Körperbewegung ausgewertet.

---

## 2. Produkteinsatz

### 2.1 Anwendungsbereich und Nutzergruppen

| Rolle | Beschreibung |
|---|---|
| **Nutzer:in** | Person mit motorischer Einschränkung; erzeugt Signale, trifft Auswahl. |
| **Caregiver** | Angehörige/Pflegekraft; richtet ein, kalibriert mit, überwacht Signalqualität, definiert Fragen/Ansagen. Kein IT-Fachwissen vorausgesetzt. |
| **Entwickler:in** | Open-Source-Community; erweitert Kanäle, Layouts, Ausgabe-Adapter. |

### 2.2 Betriebsbedingungen

- Häusliche Pflege- oder Kliniksituation; wechselnde Beleuchtung (Fenster, Deckenlicht, TV).
- Gesicht ggf. teilverdeckt (Beatmungsmaske, Nasensonde, Brille, Bart) und nicht immer frontal.
- Rechner: handelsüblicher (auch älterer) Laptop mit integrierter oder USB-Webcam.

### 2.3 Hardware-Mindestanforderungen

- x86-64-CPU **mit AVX-Unterstützung** (MediaPipe-Wheels setzen AVX voraus; ohne AVX startet die
  Inferenz nicht — wird beim Start geprüft, siehe /LF150/).
- Webcam mit ≥ 640×480 @ 30 fps nominell; effektiv müssen ≥ ~12 FPS Verarbeitung erreicht werden
  (Selbsttest, /LF150/).
- Betriebssysteme: Windows 10/11, Linux (x86-64), macOS (siehe /LN50/).

---

## 3. Funktionale Anforderungen

Nummerierung: `/LFxxx/`. Jede Anforderung ist einzeln prüfbar. „Muss" = M1-relevant bzw.
verbindlich; „Soll" = geplant, Meilenstein in Klammern (vgl. Kap. 7).

### LF10x — Capture & Signalqualität

- **/LF100/** Das System muss Videobilder einer angeschlossenen Webcam über OpenCV erfassen.
  Windows: `CAP_DSHOW` als Default-Backend (MSMF öffnet langsam, Property-Steuerung unzuverlässig);
  Linux: v4l2; Backend konfigurierbar.
- **/LF110/** Die Frame-Quelle muss abstrahiert sein, sodass sie durch eine Videodatei oder einen
  aufgezeichneten Feature-Stream (Replay, /LF800/) ersetzt werden kann.
- **/LF120/** Der Kalibrierungsablauf muss einen **Kamera-Setup-Schritt** enthalten: Autofokus
  deaktivieren und Belichtung fixieren, sofern die Kamera dies zulässt; andernfalls Hinweis an den
  Caregiver und Verlass auf /LF130/.
- **/LF130/** **Lichtsprung-Veto:** Ein globaler Helligkeits-/Ganzgesichts-Sprungdetektor muss bei
  abrupten Beleuchtungsänderungen eine Kommandosperre von 1–2 s über alle Kanäle erzwingen. Der
  Sperrzustand muss sichtbar angezeigt werden.
- **/LF140/** **Liveness-/Qualitätsmonitor:** Bei verlorenem Gesicht, starker Verdeckung oder
  degradierter Trackingqualität (Landmark-Jitter als Proxy) darf das System **keine Kommandos
  emittieren** und muss den Zustand sichtbar anzeigen. Grundsatz: kein Signal senden ist immer
  sicherer als ein falsches.
- **/LF150/** **Selbsttest beim Start:** AVX-Verfügbarkeit und effektive Verarbeitungs-FPS werden
  gemessen und angezeigt; unter 12 FPS erscheint eine deutliche Warnung.

### LF20x — Feature-Extraktion

- **/LF200/** Das System muss pro Frame Gesichtsmerkmale über MediaPipe Face Landmarker
  (VIDEO-Modus) extrahieren: 478 Landmarken, 52 Blendshape-Scores, Transformationsmatrix.
- **/LF210/** Aus Landmarken müssen abgeleitete geometrische Kanäle berechnet werden (mindestens:
  Eye-Aspect-Ratio je Auge, Brauen-Augen-Abstand, Mundwinkel-Auslenkung, Kopf-Yaw/-Pitch/-Roll),
  normiert auf den Interokularabstand.
- **/LF220/** Alle Kanäle sind **benannt** und bilden zusammen einen `ChannelFrame` mit
  **Capture-Zeitstempel** (nicht Verarbeitungszeit). Sämtliche nachgelagerten Zeitmessungen
  (Latenz, Kalibrierungs-Alignment) beziehen sich auf Capture-Zeitstempel.
- **/LF230/** Die Kanalmenge muss erweiterbar sein (später Hand-/Pose-Landmarken für andere
  Körperregionen), ohne dass Kalibrierung/Detektion geändert werden müssen (M5+).

### LF30x — Kalibrierung

- **/LF300/** **Signaloffenheit:** Die Kalibrierung muss aus allen verfügbaren Kanälen den/die
  trennschärfsten für die jeweilige Person auswählen. Kein Kanal ist fest verdrahtet.
- **/LF310/** **Selbst getaktete Signalaufnahme:** Die Person erzeugt ihr Signal N-mal (Ziel: 10),
  wann sie will („Mach dein Signal, wann du bereit bist") — keine festen Ansage-Zeitfenster
  (Reaktionslatenz von Sekunden darf keine Fehl-Labels erzeugen). Ereignisse werden per
  Peak-Picking in großzügigen Fenstern gefunden.
- **/LF311/** Jedes gefundene Signal-Ereignis muss dem Caregiver als Kurvenausschnitt zur
  Bestätigung angezeigt werden („War das eins?") — Absicherung gegen Label-Rauschen.
- **/LF320/** **Neutral-Aufnahme:** Zusätzlich wird eine Ruhe-/Neutralphase aufgezeichnet. Bei
  Personen mit Bewegungsunruhe (Person A) muss diese lang genug sein, um die Ausreißer-Statistik
  zu erfassen (Richtwert 3–5 min). Die unwillkürlichen Bewegungen werden **nicht herausgefiltert** —
  sie **sind** die Referenzverteilung, gegen die diskriminiert wird.
- **/LF330/** **Kanal-Ranking:** Primäre Metrik ist die **empirische False-Positive-Rate bei
  vorgegebener True-Positive-Rate** (quantilbasiert aus den Rohverteilungen); AUC als Zweitmaß.
  d′ wird nicht als Entscheidungsmaß verwendet (Normalverteilungsannahme versagt bei heavy-tailed
  Unruhe-Verteilungen).
- **/LF331/** Kanäle mit degenerierten Verteilungen (quasi-konstant, MAD ≈ 0) müssen erkannt und
  disqualifiziert werden. Die minimale beobachtete Streuung je Kanal wird als MAD-Floor im Profil
  gespeichert (→ /LF420/).
- **/LF340/** Es müssen **kurze und gehaltene** Signalvarianten getestet werden — für Person A ist
  ein gehaltenes Signal oft besser von kurzen ballistischen Unwillkür-Bewegungen trennbar.
- **/LF350/** **Kalibrierung unter Realbedingungen:** Der Ablauf muss den Caregiver anweisen, die
  Kalibrierung im Alltagszustand durchzuführen (Maske an, Brille auf). Verdeckte/halluzinierte
  Kanäle werden so vom Ranking selbst aussortiert. Zusätzlich müssen Gesichtsregionen im Profil
  manuell sperrbar sein (z.B. „alle Mund-Kanäle aus").
- **/LF360/** **Validierungsrunde als Pflichtabschluss:** Nach der Kalibrierung werden 10
  aufgeforderte Signale + 2 min Ruhe gemessen; TP-Rate und FP/min werden **angezeigt**, bevor das
  Profil zur Kommunikation freigegeben wird.
- **/LF370/** **Profil-Versionierung:** Profile werden als YAML gespeichert mit Datum, gewähltem
  Kanal, Baseline-Statistik, Schwellwert-Delta, Haltezeit, MAD-Floor und den Messwerten der
  Validierungsrunde. Mehrere Profilversionen pro Person bleiben erhalten (Tagesform).
- **/LF380/** **Schnell-Trim:** Getrennt von der Erst-Kalibrierung (realistisch 5–10 min) muss ein
  Trim-Modus (< 2 min) existieren, der nur Schwellwert/Baseline eines bestehenden Profils nachzieht.

### LF40x — Detektion

- **/LF400/** Die Erkennung ist als **Schmitt-Trigger-Zustandsautomat** implementiert:
  `IDLE → RISING → HELD → CONFIRM → EMIT → REFRACTORY`, mit Hysterese (getrennte Ein-/Aus-Schwellen),
  Mindest-Haltezeit und Refraktärzeit. Alle Zeitparameter in **Sekunden, nie in Frames**
  (FPS variieren je Rechner).
- **/LF410/** **Gated Dual-Timescale-Baseline:** Die Rolling-Baseline (Median/MAD) wird auf zwei
  Zeitskalen geführt (langsam: Minuten, für Drift/Ermüdung; schnell: Sekunden, für Licht); die
  Detektion nutzt die langsame. Samples aus den Zuständen RISING/HELD/CONFIRM/EMIT/REFRACTORY
  fließen **niemals** in die Baseline ein (sonst kontaminiert das Signal bei aktiver Nutzung die
  eigene Referenz und der Schwellwert wandert weg).
- **/LF420/** **MAD-Floor:** Die Streuungsschätzung darf nie unter den kalibrierten Floor (/LF331/)
  fallen — verhindert Schwellwert-Kollaps und Dauerfeuern bei quasi-konstanten Kanälen.
- **/LF430/** **Relative Schwellen:** Der Auslöse-Schwellwert ist als laufende Baseline + gelerntes
  Delta definiert, nicht absolut — fängt langsame Drift (Ermüdung, absinkende Augenöffnung) ab.
- **/LF440/** *(Soll, M2)* **Spezifitäts-Check als Chorea-Diskriminator:** CONFIRM nur, wenn der
  Zielkanal deutlich erhöht ist UND die übrigen Top-Kanäle nahe Baseline bleiben (Chorea aktiviert
  viele Kanäle gleichzeitig, ein willentliches isoliertes Signal nicht). Entwicklung gegen
  Replay-Daten von Person A.
- **/LF450/** *(Soll, M2)* **Posennormalisierung:** Geometrie über die facial transformation matrix
  in einen kanonischen Face-Frame rechnen; bei extremer Pose/hoher Kopf-Winkelgeschwindigkeit
  sinkt die Frame-Konfidenz (Gewichtung, **kein Hard-Veto** — sonst wird Person A permanent
  ausgesperrt).

### LF50x — Virtueller Schalter & zeitliche Muster

- **/LF500/** Zentrale Schnittstelle in zwei Ebenen:
  **`ChannelFrame`** (kontinuierliche, normierte Kanalwerte + Capture-Zeitstempel — konsumiert von
  Monitor, Logging, Replay, später proportionaler Steuerung) und
  **`SwitchEvent`** mit `source_id`, `event_type`, `timestamp_capture`, `confidence` (diskret —
  konsumiert von Mapping/Scanning). `source_id` macht Mehrkanal-Betrieb (2D-Raster, M5) von Anfang
  an möglich.
- **/LF510/** Schalterquellen sind austauschbar: `video_switch` (Detektor-gestützt, Person A) und
  `key_switch` (Tastatur/physischer Schalter über USB-Adapter, Person B und Tests) implementieren
  dieselbe Schnittstelle.
- **/LF520/** **Zeitliche Muster** müssen konfigurierbar sein: 1×, 2× innerhalb eines Zeitfensters,
  halten für X Sekunden — inkl. Debouncing. Die Muster-Semantik liegt in der Konfiguration, nicht
  im Event-Typ-Kern.
- **/LF530/** Die Bestätigungslogik (z.B. „2× im Fenster nötig") muss pro Profil einstellbar sein;
  der Trade-off Robustheit ↔ Geschwindigkeit wird dem Caregiver angezeigt (→ /LF720/).

### LF60x — Output

- **/LF600/** **Ja/Nein-Modus mit 3 Items: JA / NEIN / PASSE** („will/kann gerade nicht
  antworten"). Ein 2-Item-Scan ist ethisch unterspezifiziert.
- **/LF610/** **Timeout ist nie eine Antwort:** Endet der Scan nach N Zyklen ohne Auswahl, geht das
  System in den Zustand „KEINE ANTWORT" (angezeigt und geloggt, **niemals** als Ja/Nein gesprochen).
- **/LF620/** **Cancel-Countdown:** Vor jeder Sprachausgabe läuft ein sichtbarer Countdown
  (2–3 s, konfigurierbar); jedes Signal während des Countdowns bricht die Ausgabe ab.
- **/LF630/** Deutsche **Sprachausgabe (TTS)**: pyttsx3 (SAPI5/NSSpeech/espeak-ng als
  System-Abhängigkeit) als Zero-Config-Basis; Piper (MIT, neuronale deutsche Stimmen, offline) als
  Qualitätsoption (M2+). TTS läuft in einem eigenen Thread und darf das Scanning nie blockieren.
- **/LF640/** *(Soll, M2)* **Scanning-Engine:** Zeilen-Spalten-Scanning mit häufigkeitsoptimiertem
  deutschem Buchstaben-Layout (konfigurierbare Layout-Dateien); Scan-Geschwindigkeit einstellbar.
- **/LF650/** *(Soll, M2)* **Notruf-/Aufmerksamkeitsfunktion:** konfigurierbares Muster
  (z.B. Signal 3×) löst einen Alarmton aus — unabhängig vom aktuellen Modus.
- **/LF660/** *(Soll, M3)* **Wortvorhersage** für Deutsch (n-gram, später optional kompaktes
  Sprachmodell, stets offline) — größter Geschwindigkeitshebel für Person B.
- **/LF670/** *(Soll, M6)* OS-Steuerung über Accessibility-APIs (Maus/Tastatur-Emulation).

### LF70x — Betreuer-Funktionen

- **/LF700/** **Live-Monitor (bereits im MVP):** Anzeige von aktuellem Kanalwert, Baseline,
  Schwellwert und Automaten-Zustand als Balken/Ampel — ohne diese Sicht ist Kalibrieren und
  Fehlersuche vor Ort unmöglich.
- **/LF710/** **Anti-Facilitated-Communication-Anzeige:** Beim Einstellen des Schwellwerts zeigt
  das System live die **erwartete Zufalls-Auslösungsrate** („bei dieser Einstellung: ~X Auslösungen
  pro Minute ohne Absicht"). Schutz davor, dass Rauschen als Wille interpretiert wird.
- **/LF711/** *(Soll, M4)* **Verifikationsmodus:** Serie verblindeter Kontrollfragen mit bekannter
  richtiger Antwort (nur für die Person wahrnehmbar); Konsistenz-Score wird protokolliert.
- **/LF720/** Konfiguration im MVP **datei-getrieben** (YAML: Fragen/Ansagen, Muster, Zeiten);
  grafische Caregiver-GUI erst M4.
- **/LF730/** **Session-Logging:** Kanalwerte und Events werden als JSONL protokolliert
  (append-only), inkl. Fehlaktivierungen/min und TP-Latenzen — Grundlage für Tuning, Validierung
  und Ermüdungs-Trendauswertung (M2+). Logging ist **opt-in** (→ /LN31/).
- **/LF740/** *(Soll, M2)* **Ermüdungs-Monitoring:** Online-Beobachtung von Trennschärfe und
  TP-Latenz; bei Degradation Pausen-Hinweis. Die dafür nötigen Logdaten werden ab M1 erfasst.

### LF80x — Replay & Test

- **/LF800/** **Log-Format = Replay-Format (ab Tag 1):** Der Feature-Stream (ChannelFrames mit
  Capture-Zeitstempeln) jeder Sitzung kann so aufgezeichnet werden, dass Kalibrierung und Detektion
  **offline deterministisch** wiederabgespielt werden können. Begründung: Nutzerzeit ist das
  knappste Gut — jede Detektor-Änderung wird gegen aufgezeichnete Sessions getestet, nicht an
  erschöpfbaren Menschen.
- **/LF810/** Akzeptanztests für Unruhe-Robustheit laufen gegen **echte** aufgezeichnete
  Unruhe-Daten via Replay — von Gesunden „simulierte" Unruhe hat eine andere Statistik und ist als
  Nachweis unzulässig.
- **/LF820/** Detektor und Kanal-Ranking müssen zusätzlich mit synthetischen Traces (pytest)
  getestet sein: Tremor-Rauschen + 1 gehaltenes Signal ⇒ genau 1 Emission; reiner Tremor ⇒ 0;
  Doppelpuls im Fenster ⇒ `double`.

---

## 4. Nicht-funktionale Anforderungen

- **/LN10/ Robustheit:** Fehlaktivierungsrate < 0,5/min über je 10 min Ruhe **und** echte
  Replay-Unruhe (Messverfahren siehe Kap. 5). „Null Fehler" wird nicht behauptet — Restrisiko wird
  über Bestätigungslogik (/LF530/) und Cancel-Countdown (/LF620/) abgefangen.
- **/LN20/ Latenz:** Verarbeitung < Frameintervall (Pipeline hält die Kamera-FPS); End-to-End
  Signal → sichtbares Feedback < 500 ms (gemessen über Capture-Zeitstempel). Die
  **Entscheidungslatenz** (Haltezeit + Bestätigungsfenster) liegt konstruktionsbedingt bei
  Sekunden und wird getrennt ausgewiesen — sie ist konfigurierter Trade-off, kein Mangel.
- **/LN30/ Datenschutz:** Verarbeitung ausschließlich lokal, keine Netzwerkübertragung von Video-
  oder Gesichtsdaten. Videoframes werden **niemals per Default gespeichert**.
- **/LN31/** Feature-Logs sind Gesundheitsdaten: Aufzeichnung nur opt-in, Speicherort transparent,
  Löschung durch Caregiver jederzeit möglich.
- **/LN40/ Lizenz:** Projekt unter **Apache-2.0**. Nur lizenzkompatible Abhängigkeiten
  (OpenCV: Apache-2.0, MediaPipe: Apache-2.0, NumPy: BSD, PyYAML: MIT, Piper: MIT; espeak-ng
  (GPLv3) nur als externe Systemabhängigkeit, nicht gebündelt). **Keine Code-Übernahme aus
  GPL-Projekten** (OptiKey, Dasher, eViacam) — nur Konzept-/UX-Referenz.
- **/LN50/ Plattformen:** Windows 10/11, Linux, macOS. OS-neutraler Kern; plattformspezifisches
  (Kamera-Backend, TTS, spätere OS-Steuerung) in gekapselten Adaptern.
- **/LN60/ Sprache:** Deutsch zuerst (UI-Texte, TTS, Layouts, Wortvorhersage); alle Texte und
  Sprachressourcen als austauschbare Ressourcen für spätere Lokalisierung.
- **/LN70/ Bedienbarkeit:** Kalibrierung und Alltagsbetrieb müssen durch Caregiver ohne
  IT-Kenntnisse durchführbar sein (geführte Abläufe, verständliche Zustandsanzeigen, keine
  Kommandozeilen-Pflicht ab M4).
- **/LN80/ Erweiterbarkeit:** Neue Signalkanäle, Schalterquellen, Layouts und Ausgabemodi müssen
  ohne Änderung des Kerns ergänzbar sein (Schnittstellen /LF500/, /LF510/).

---

## 5. Abnahmekriterien Meilenstein M1

M1 gilt als abgenommen, wenn — dokumentiert per Session-Log/Replay:

| Nr. | Kriterium | Messverfahren |
|---|---|---|
| A1 | < 0,5 Fehlaktivierungen/min bei Ruhe | 10 min Ruheaufnahme, Log-Auswertung |
| A2 | < 0,5 Fehlaktivierungen/min bei echter Unruhe | 10 min echte Unruhe-Aufnahme via Replay (/LF810/) |
| A3 | TP-Rate ≥ 90 % | ≥ 20 aufgeforderte Signale in der Validierungsrunde |
| A4 | Signal → Feedback < 500 ms | Capture-Zeitstempel-Differenz im Log |
| A5 | Lichtsprung-Test: 0 Emissionen | Lampe an/aus während Ruhephase; Veto + Sperranzeige greifen |
| A6 | Kalibrierung unter Realbedingungen abgeschlossen, Profil versioniert gespeichert | Profil-YAML mit Validierungs-Messwerten vorhanden |
| A7 | Zufalls-FP-Anzeige (/LF710/) aktiv und plausibel | Sichtprüfung beim Schwellwert-Einstellen |
| A8 | FPS-Selbsttest vorhanden | Start auf Referenz-Hardware, Warnung unter 12 FPS |
| A9 | Ja/Nein/PASSE-Ablauf inkl. Cancel-Countdown und „KEINE ANTWORT" | Durchspielen aller vier Ausgänge |
| A10 | Synthetik-Tests grün | `pytest` (/LF820/) |

---

## 6. Gewähltes Umsetzungskonzept (Architektur)

### 6.1 Schichtenmodell

```
┌────────────────────────────────────────────────────────────────────┐
│  Capture (OpenCV, CAP_DSHOW/v4l2, Latest-Frame-Slot)               │
│  + Kamera-Setup, Lichtsprung-Veto, Liveness-Monitor  [LF10x]       │
└──────────────┬─────────────────────────────────────────────────────┘
               ▼
┌────────────────────────────────────────────────────────────────────┐
│  Feature-Extraktion (MediaPipe Face Landmarker, VIDEO-Modus)       │
│  Blendshapes + Geometrie → benannte Kanäle → ChannelFrame [LF20x]  │
└──────┬───────────────────────────────┬─────────────────────────────┘
       ▼                               ▼
┌─────────────────────┐   ┌────────────────────────────────────────┐
│ Kalibrierung        │   │ Detektion                              │
│ selbst getaktet,    │──▶│ Schmitt-Trigger-Automat,               │
│ FP@TP-Ranking,      │   │ gated Dual-Timescale-Baseline,         │
│ Validierungsrunde,  │   │ MAD-Floor, relative Schwellen [LF40x]  │
│ Profil-YAML [LF30x] │   └──────────────┬─────────────────────────┘
└─────────────────────┘                  ▼
              ┌──────────────────────────────────────────────┐
              │  Virtueller Schalter [LF50x]                 │
              │  SwitchEvent(source_id, type, ts, conf)      │
              │  Quellen: video_switch │ key_switch          │
              │  + Temporal Patterns (1×/2×/halten)          │
              └──────────────┬───────────────────────────────┘
                             ▼
┌────────────────────────────────────────────────────────────────────┐
│  Mapping (YAML-Konfiguration) → Output [LF60x]                     │
│  3-Item-Scan (JA/NEIN/PASSE) · Cancel-Countdown · dt. TTS          │
│  ab M2: Zeilen-Spalten-Scanning, Notruf; M3: Wortvorhersage        │
└────────────────────────────────────────────────────────────────────┘
   Querschnitt: Live-Monitor [LF700] · Session-Log = Replay [LF80x]
```

### 6.2 Threading-Modell

```
Capture-Thread ──▶ Latest-Frame-Slot (1 Slot, kein Backlog — Latenz
                   wächst sonst unsichtbar auf Sekunden)
                        │
Inferenz-Thread ◀───────┘  (MediaPipe gibt den GIL bei Inferenz frei)
      │
      ▼ Event-Queue
UI-Mainthread (Tkinter)          TTS-Thread (blockierendes
                                  runAndWait isoliert)
```

### 6.3 Technologie-Entscheidungen (mit Begründung)

| Entscheidung | Begründung |
|---|---|
| **MediaPipe Face Landmarker** statt eigenem Modell | 52 semantisch benannte Blendshapes + 478 Landmarken out-of-the-box; Apache-2.0; läuft CPU-only. Die Signaloffenheit entsteht in der Kalibrierung (Kanalauswahl), nicht durch eigenes ML. |
| **Kein SVM/MLP im MVP** | Schwellwert + robuste Statistik ist erklärbar, debugbar und pro Person mit Minuten an Daten kalibrierbar. ML erst, wenn ein Einzelkanal nachweislich nicht trennt (dann mit Replay-Daten). |
| **Anomalieerkennung statt Gestenklassifikation** | Kernanforderung Person A: Abweichung von individueller Unruhe-Baseline, nicht „Geste erkannt". |
| **Tkinter statt OpenCV-HighGUI** für UI | `cv2.putText` kann kein UTF-8 → deutsche Umlaute unmöglich; HighGUI-Eventloop fragil. Tkinter ist stdlib (keine neue Abhängigkeit) und plattformübergreifend. OpenCV nur für Capture. |
| **pyttsx3 zuerst, Piper als Option** | Zero-Config-Start auf allen Plattformen; Piper (MIT) liefert später deutlich bessere deutsche Stimmen, offline. |
| **YAML-Konfiguration statt GUI im MVP** | Caregiver-GUI (M4) erst bauen, wenn die Abläufe mit echten Nutzer:innen validiert sind. |
| **Zeiten in Sekunden, nie Frames** | Profile müssen auf Rechnern mit 12–30 FPS identisch funktionieren. |
| **Replay-First-Testing** | Nutzerzeit/Belastbarkeit ist die knappste Ressource des Projekts. |

### 6.4 Modulstruktur

```
blickfang/
  LASTENHEFT.md · LICENSE (Apache-2.0) · README.md · pyproject.toml
  config/
    settings.example.yaml     # Fragen/Ansagen, Muster, Zeiten
    profiles/                 # versionierte Personen-Profile (YAML)
    layouts/                  # Scanning-Layouts (dt. Frequenz-Layout ab M2)
  src/blickfang/
    core/events.py            # ChannelFrame + SwitchEvent            [LF500]
    capture/camera.py         # OpenCV, Backend-Wahl, Frame-Slot      [LF100-120]
    features/face_mesh.py     # MediaPipe-Wrapper (VIDEO-Modus)       [LF200]
    features/channels.py      # Blendshapes + Geometrie → Kanäle      [LF210-230]
    calibration/session.py    # selbst getaktete Aufnahme, Peaks      [LF310-320]
    calibration/selector.py   # FP@TP-Ranking, Degenerations-Check    [LF330-350]
    calibration/profile.py    # versionierte Profile, Schnell-Trim    [LF370-380]
    detection/baseline.py     # gated Dual-Timescale Median/MAD       [LF410-430]
    detection/detector.py     # Schmitt-Trigger-Automat               [LF400]
    detection/quality.py      # Liveness, Lichtsprung-Veto, Jitter    [LF130-150]
    switch/base.py            # Switch-Schnittstelle                  [LF500]
    switch/video_switch.py    # Detektor-gestützt (Person A)          [LF510]
    switch/key_switch.py      # Tastatur/physischer Schalter (B)      [LF510]
    temporal/patterns.py      # 1×/2×/halten, Debouncing              [LF520-530]
    io/replay.py              # Log=Replay-Format, deterministisch    [LF800]
    output/tts.py             # pyttsx3→Piper, eigener Thread         [LF630]
    output/scanning.py        # 3-Item-Scan, Cancel, KEINE ANTWORT    [LF600-620]
    ui/scan_ui.py             # Tkinter: Scan-UI + Live-Monitor       [LF700-710]
    app/calibrate.py          # Entrypoint Kalibrierung
    app/run_yesno.py          # Entrypoint Ja/Nein/PASSE-Demo
  tests/                      # synthetische Traces, Replay-Regression [LF820]
```

### 6.5 Datenformate

- **Profil (`profiles/<name>_<datum>.yaml`):** Kanalname, Baseline-Statistik (Median/MAD),
  Schwellwert-Delta, Hysterese, Haltezeit, Refraktärzeit, MAD-Floor, Bestätigungsmuster,
  gesperrte Regionen, Validierungs-Messwerte (TP-Rate, FP/min), Versions-/Datumsstempel.
- **Session-Log/Replay (`*.jsonl`, append-only):** eine Zeile pro ChannelFrame
  (Capture-Zeitstempel, Kanalwerte) und pro Event (SwitchEvent, Zustandswechsel, Vetos) —
  deterministisch wiederabspielbar (/LF800/).

---

## 7. Meilensteine & Roadmap

| MS | Inhalt | Leitperson |
|---|---|---|
| **M1** | Kalibrier- & Erkennungs-Kern: Kamera-Setup, Kanäle, selbst getaktete Kalibrierung + Validierungsrunde, Detektor (gated Baseline), virtueller Schalter, Ja/Nein/PASSE + Cancel-Countdown + dt. TTS, Live-Monitor, Replay-Logging. Abnahme nach Kap. 5. | A (Kern), B (Unterbau) |
| **M2** | Scanning-Kern: Zeilen-Spalten-Scanning, dt. Frequenz-Layout, `key_switch`-Betrieb, Notruf-Funktion, Spezifitäts-Check + Posennormalisierung (aus Replay-Daten von A), Ermüdungs-Monitoring, Piper-TTS. | B, A |
| **M3** | Wortvorhersage Deutsch (n-gram → optional kompaktes LM, offline). | B |
| **M4** | Caregiver-GUI: Fragen/Ansagen definieren, Profile verwalten, Messwerte einsehen; Verifikationsmodus. | beide |
| **M5** | Zweiter Videosignalkanal → 2D-Raster; Mehrkanal-Kalibrierung; erweiterte Körperregionen (Pose/Hand). | B |
| **M6** | OS-Steuerung über Accessibility-APIs. | beide |

---

## 8. Referenzprojekte & Lizenzhinweise

| Projekt | Lizenz | Nutzung |
|---|---|---|
| [OptiKey](https://github.com/OptiKey/OptiKey) | GPLv3, C#/.NET, Windows | **Nur UX-/Konzept-Referenz** (Scanning, Dwell, Keyboard-Layouts, TTS-Ablauf). Keine Code-Übernahme (GPL↔Apache). |
| Intel ACAT | prüfen | Referenz für Switch-Scanning, Wortvorhersage, Abkürzungs-Expansion (System hinter S. Hawkings Kommunikation). Lizenz vor jeder Übernahme prüfen. |
| Dasher | GPL | Referenz für informationseffiziente Texteingabe mit einem Schalter. Keine Code-Übernahme. |
| eViacam / Camera Mouse | GPL / — | Referenz Webcam-Kopfsteuerung. Keine Code-Übernahme. |
| Soukupová & Čech: „Real-Time Eye Blink Detection using Facial Landmarks" | Paper | Eye-Aspect-Ratio als geometrischer Fallback-Kanal. |
| [MediaPipe](https://ai.google.dev/edge/mediapipe/solutions/vision/face_landmarker) | Apache-2.0 | Direkte Abhängigkeit (Face Landmarker, Blendshapes). |

---

## 9. Risiken & offene Punkte

| Risiko | Einordnung / Gegenmaßnahme |
|---|---|
| MediaPipe-Wheel benötigt AVX; „Legacy Solutions" wurden bereits eingestellt — langfristige Verfügbarkeit der Tasks-API ungewiss | Feature-Extraktion hinter eigener Schnittstelle kapseln (/LF200/ austauschbar, z.B. OpenSeeFace als Fallback-Kandidat); AVX-Selbsttest (/LF150/) |
| Webcam-Belichtung/Fokus nicht auf allen Geräten steuerbar | Lichtsprung-Veto (/LF130/) als Pflicht-Fallback; Liste getesteter Webcams in der Doku |
| Facilitated-Communication-Risiko: Caregiver senkt Schwellwert, bis „Antworten" kommen | Zufalls-FP-Anzeige (/LF710/) ab M1; Verifikationsmodus (M4); append-only Logs |
| MDR-Grauzone (Software als Medizinprodukt) | Nicht-Ziel-Erklärung (Kap. 1.4) + Disclaimer; vor breiter Verbreitung juristisch prüfen lassen |
| Validierung nur mit echten Nutzer:innen möglich; deren Zeit/Belastbarkeit begrenzt | Replay-First-Ansatz (/LF800/–/LF810/): jede Änderung offline gegen aufgezeichnete Sessions |
| Tagesform-Schwankungen entwerten Profile | Profil-Versionierung (/LF370/) + Schnell-Trim (/LF380/) |
| OneDrive-Sync ↔ Git-Repository (Konflikte bei `.git`) | Vor Beginn der Implementierung klären, ob das Repo in ein lokales Dev-Verzeichnis umzieht (OneDrive-Ordner nur für Doku) |

---

*Ende des Lastenhefts. Änderungen an Anforderungen werden über die Versionsnummer im Kopf und
das Änderungsdatum nachgeführt.*
