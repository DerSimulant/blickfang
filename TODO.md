# blickfang — TODO-Liste

## Status-Legende

- [ ] Offen
- [x] Erledigt

---

## Meilenstein M1 — Kalibrier- & Erkennungs-Kern

- [x] Kamera-Capture mit OpenCV (Latest-Frame-Slot)
- [x] Feature-Extraktion via MediaPipe Face Landmarker
- [x] Selbst getaktete Kalibrierung mit Validierungsrunde
- [x] Schmitt-Trigger-Detektor mit gated Dual-Timescale-Baseline
- [x] Virtueller Schalter (Video + Tastatur)
- [x] Ja/Nein/PASSE-Modus mit Cancel-Countdown
- [x] Deutsche TTS-Sprachausgabe
- [x] Live-Monitor für Caregiver
- [x] Replay-Logging (JSONL)
- [x] Automatischer MediaPipe-Modell-Download
- [x] HOLD-Event-Emission

## Meilenstein M2 — Kommunikations-Oberfläche

- [x] Erweitertes Scanning-Framework (Zeile/Spalte, Gruppen, Hierarchie)
- [x] Frequenz-optimiertes deutsches Tastatur-Layout
- [x] Schnell-Phrasen (36 Sätze in 6 Kategorien)
- [x] Buchstaben-Scanning mit Wortvorschlägen
- [x] Notruf-Alarm (3× Signal)
- [x] Ermüdungs-Monitoring
- [x] React + Vite + TailwindCSS Frontend
- [x] FastAPI + WebSocket Backend
- [x] Kamera-Auswahl + Vorschau im Browser
- [x] Profil-Auswahl im Startscreen (Dropdown)
- [x] Fehler-Meldungen im UI
- [x] Akustisches Scan-Feedback (Web Audio API)
- [x] Session-Export (Kommunikations-Verlauf als Textdatei)
- [x] Kalibrierung im Browser
- [x] Settings-Panel (Scan-Speed, Countdown, TTS)
- [x] Caregiver-Dashboard

## Meilenstein M3 — Erweitertes Vokabular & Satz-Builder

- [x] Satz-Builder (Subjekt → Verb → Objekt) mit Verb-Konjugation
- [x] Kontextabhängige Wortvorschläge (lernt aus Nutzung, Bigram-Modell)
- [x] Persönliches Wörterbuch (Kategorien, Favoriten, Import/Export)
- [x] Textdatei-Export (gesamter Tagesverlauf, formatiert für Therapeuten)
- [ ] Mehrsprachige Unterstützung (Englisch, weitere Sprachen)
- [ ] Emoji-Unterstützung für emotionale Kommunikation

## Meilenstein M4 — Umgebungssteuerung

- [ ] Smart-Home-Integration (Licht, TV, Jalousien)
- [ ] IR-Sender-Anbindung (Fernbedienung)
- [ ] Notruf-Weiterleitung (SMS/Anruf an Betreuer)
- [ ] Musik/Radio-Steuerung
- [ ] Temperatur-Steuerung (Heizung/Klima)
- [ ] Türöffner-Integration

## Meilenstein M5 — Adaptive Schwellwerte & Lernen

- [ ] Adaptive Schwellwerte (lernt über Tage/Wochen)
- [ ] Automatische Profil-Aktualisierung bei Drift
- [ ] Tageszeit-abhängige Anpassung (morgens vs. abends)
- [ ] Ermüdungs-kompensierte Schwellwerte
- [ ] A/B-Testing verschiedener Detektor-Konfigurationen
- [ ] Langzeit-Statistiken (Signalqualität über Wochen)

## Meilenstein M6 — Multi-User & Cloud

- [ ] Cloud-Sync für Profile (zwischen Geräten)
- [ ] Therapeuten-Portal (Remote-Zugriff auf Statistiken)
- [ ] Multi-User-Verwaltung (Pflegeheim-Szenario)
- [ ] Backup & Restore von Profilen
- [ ] Remote-Konfiguration durch Therapeuten
- [ ] Datenexport für Forschung (anonymisiert)

---

## Technische Verbesserungen

### Robustheit

- [ ] Kamera-Reconnect bei Ausfall (automatisch)
- [ ] Graceful Degradation wenn MediaPipe nicht verfügbar
- [ ] Watchdog für Server-Prozess (Neustart bei Crash)
- [ ] Heartbeat-Monitoring (Server → Frontend)
- [ ] Fehler-Logging in Datei (für Support)

### Performance

- [ ] GPU-Beschleunigung für MediaPipe (ONNX/TensorRT)
- [ ] Frame-Skipping bei hoher CPU-Last
- [ ] Lazy-Loading für Frontend-Komponenten
- [ ] Service Worker für Offline-Fähigkeit

### UX/UI

- [ ] Themes (Hochkontrast, Dunkel, Hell, benutzerdefiniert)
- [ ] Schriftgrößen-Anpassung pro Person
- [ ] Touch-Modus für Tablet-Betreuer
- [ ] Onboarding-Wizard für Ersteinrichtung
- [ ] Animations-Geschwindigkeit anpassbar
- [ ] Sound-Pack-Auswahl (verschiedene Klick-Töne)

### Testing & Qualität

- [ ] End-to-End-Test mit echter Kamera
- [ ] Integrationstests (Server + Frontend)
- [ ] Performance-Benchmarks (Latenz-Messung)
- [ ] Accessibility-Audit (WCAG 2.1)
- [ ] Cross-Browser-Tests (Chrome, Firefox, Edge)

### Deployment

- [ ] Windows-Installer (MSI/EXE)
- [ ] Auto-Update-Mechanismus
- [ ] Portable Version (USB-Stick)
- [ ] Raspberry Pi Support (für günstige Kiosk-Lösung)
- [ ] Docker-Container für einfache Installation

---

## Bekannte Einschränkungen

- TTS (pyttsx3) kann auf manchen Windows-Systemen Probleme machen
- Kamera-Auswahl bei mehreren USB-Kameras nicht immer zuverlässig
- MediaPipe benötigt mindestens 640x480 Auflösung
- Validierungsrunde in Kalibrierung noch nicht vollständig implementiert
- Wortvorschläge basieren auf Bigram-Modell (lernt mit Nutzung)
