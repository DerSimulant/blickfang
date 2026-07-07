import { useEffect, useState } from 'react';

interface Profile {
  name: string;
  channel: string;
  created: string;
}

interface StartScreenProps {
  onStart: (mode: string, person?: string) => void;
  onCalibrate?: () => void;
  onSettings?: () => void;
  onDashboard?: () => void;
  onSentenceBuilder?: () => void;
  onDictionary?: () => void;
}

export function StartScreen({ onStart, onCalibrate, onSettings, onDashboard, onSentenceBuilder, onDictionary }: StartScreenProps) {
  const [profiles, setProfiles] = useState<Profile[]>([]);
  const [selectedProfile, setSelectedProfile] = useState('');
  const [useCamera, setUseCamera] = useState(false);
  const [cameraStatus, setCameraStatus] = useState<{ active: boolean; face_detected: boolean }>({
    active: false,
    face_detected: false,
  });

  // Profile laden
  useEffect(() => {
    fetch('/api/profiles')
      .then((r) => r.json())
      .then((data) => {
        setProfiles(data);
        if (data.length > 0) setSelectedProfile(data[0].name);
      })
      .catch(console.error);
  }, []);

  // Kamera-Status polling wenn aktiv
  useEffect(() => {
    if (!useCamera) return;
    const interval = setInterval(async () => {
      try {
        const res = await fetch('/api/camera/status');
        setCameraStatus(await res.json());
      } catch (e) {
        console.error(e);
      }
    }, 1000);
    return () => clearInterval(interval);
  }, [useCamera]);

  const toggleCamera = async () => {
    if (useCamera) {
      await fetch('/api/camera/stop', { method: 'POST' });
      setUseCamera(false);
      setCameraStatus({ active: false, face_detected: false });
    } else {
      await fetch('/api/camera/select', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ device_index: 0 }),
      });
      setUseCamera(true);
    }
  };

  const handleStart = (mode: string) => {
    const person = useCamera && selectedProfile ? selectedProfile : undefined;
    onStart(mode, person);
  };

  return (
    <div className="flex flex-col items-center justify-center h-full gap-6 animate-fade-in p-6 overflow-auto">
      <div className="text-center">
        <h1 className="text-5xl font-bold mb-2 tracking-tight">blickfang</h1>
        <p className="text-lg text-[var(--text-secondary)]">
          Kommunikation durch Mimik-Erkennung
        </p>
      </div>

      {/* Profil + Kamera Auswahl */}
      <div className="w-full max-w-lg bg-[var(--bg-card)] rounded-xl p-4 border border-white/10">
        <div className="flex items-center justify-between mb-3">
          <h3 className="text-sm font-medium text-white/60">Eingabe-Modus</h3>
          <button
            onClick={toggleCamera}
            className={`px-3 py-1 rounded-lg text-sm font-medium transition-colors ${
              useCamera
                ? 'bg-green-600 text-white'
                : 'bg-white/10 text-white/60 hover:bg-white/20'
            }`}
          >
            {useCamera ? '📷 Kamera aktiv' : '⌨️ Nur Tastatur'}
          </button>
        </div>

        {useCamera && (
          <div className="space-y-3">
            {/* Profil-Auswahl */}
            <div>
              <label className="block text-xs text-white/40 mb-1">Profil</label>
              {profiles.length > 0 ? (
                <select
                  value={selectedProfile}
                  onChange={(e) => setSelectedProfile(e.target.value)}
                  className="w-full px-3 py-2 bg-[var(--bg-primary)] rounded-lg border border-white/10 text-white focus:border-[var(--accent-highlight)] focus:outline-none"
                >
                  {profiles.map((p) => (
                    <option key={p.name} value={p.name}>
                      {p.name} {p.channel ? `(${p.channel})` : ''} {p.created ? `— ${p.created.slice(0, 10)}` : ''}
                    </option>
                  ))}
                </select>
              ) : (
                <p className="text-sm text-orange-400">
                  Kein Profil vorhanden — bitte zuerst kalibrieren.
                </p>
              )}
            </div>

            {/* Kamera-Vorschau */}
            <div className="relative rounded-lg overflow-hidden bg-black aspect-video">
              {cameraStatus.active ? (
                <>
                  <img
                    src="/api/camera/stream"
                    alt="Kamera-Vorschau"
                    className="w-full h-full object-cover"
                  />
                  <div className={`absolute top-2 right-2 px-2 py-1 rounded text-xs font-bold ${
                    cameraStatus.face_detected
                      ? 'bg-green-600 text-white'
                      : 'bg-red-600 text-white'
                  }`}>
                    {cameraStatus.face_detected ? 'Gesicht erkannt' : 'Kein Gesicht'}
                  </div>
                </>
              ) : (
                <div className="flex items-center justify-center h-full text-white/30">
                  Kamera wird gestartet...
                </div>
              )}
            </div>
          </div>
        )}

        {!useCamera && (
          <p className="text-sm text-white/40">
            Signal per Leertaste/Enter — ideal zum Testen und Demonstrieren.
          </p>
        )}
      </div>

      {/* Kommunikations-Modi */}
      <div className="grid grid-cols-2 gap-3 w-full max-w-lg">
        <button
          onClick={() => handleStart('phrases')}
          className="flex flex-col items-center gap-2 p-6 bg-[var(--bg-card)] rounded-2xl border-2 border-transparent hover:border-[var(--accent-highlight)] transition-all duration-200"
        >
          <span className="text-3xl">💬</span>
          <span className="text-base font-bold">Schnell-Phrasen</span>
          <span className="text-xs text-[var(--text-secondary)]">Vorgefertigte Sätze</span>
        </button>

        <button
          onClick={() => handleStart('keyboard')}
          className="flex flex-col items-center gap-2 p-6 bg-[var(--bg-card)] rounded-2xl border-2 border-transparent hover:border-[var(--accent-highlight)] transition-all duration-200"
        >
          <span className="text-3xl">⌨</span>
          <span className="text-base font-bold">Buchstabieren</span>
          <span className="text-xs text-[var(--text-secondary)]">Freier Text</span>
        </button>

        <button
          onClick={() => handleStart('yesno')}
          className="flex flex-col items-center gap-2 p-6 bg-[var(--bg-card)] rounded-2xl border-2 border-transparent hover:border-[var(--accent-highlight)] transition-all duration-200"
        >
          <span className="text-3xl">✓✗</span>
          <span className="text-base font-bold">Ja / Nein</span>
          <span className="text-xs text-[var(--text-secondary)]">Einfache Antworten</span>
        </button>

        <button
          onClick={() => handleStart('main_menu')}
          className="flex flex-col items-center gap-2 p-6 bg-[var(--bg-card)] rounded-2xl border-2 border-transparent hover:border-[var(--accent-highlight)] transition-all duration-200"
        >
          <span className="text-3xl">🏠</span>
          <span className="text-base font-bold">Hauptmenü</span>
          <span className="text-xs text-[var(--text-secondary)]">Alle Modi per Scan</span>
        </button>

        {onSentenceBuilder && (
          <button
            onClick={onSentenceBuilder}
            className="flex flex-col items-center gap-2 p-6 bg-[var(--bg-card)] rounded-2xl border-2 border-transparent hover:border-[var(--accent-highlight)] transition-all duration-200"
          >
            <span className="text-3xl">📝</span>
            <span className="text-base font-bold">Satz-Builder</span>
            <span className="text-xs text-[var(--text-secondary)]">Sätze zusammensetzen</span>
          </button>
        )}
      </div>

      {/* Betreuer-Werkzeuge */}
      <div className="flex gap-3">
        {onCalibrate && (
          <button
            onClick={onCalibrate}
            className="flex items-center gap-2 px-4 py-2 bg-[var(--bg-card)] rounded-lg border border-white/10 hover:border-[var(--accent-highlight)] transition-colors text-sm"
          >
            <span>🎯</span>
            <span>Kalibrierung</span>
          </button>
        )}
        {onDashboard && (
          <button
            onClick={onDashboard}
            className="flex items-center gap-2 px-4 py-2 bg-[var(--bg-card)] rounded-lg border border-white/10 hover:border-[var(--accent-highlight)] transition-colors text-sm"
          >
            <span>📊</span>
            <span>Dashboard</span>
          </button>
        )}
        {onSettings && (
          <button
            onClick={onSettings}
            className="flex items-center gap-2 px-4 py-2 bg-[var(--bg-card)] rounded-lg border border-white/10 hover:border-[var(--accent-highlight)] transition-colors text-sm"
          >
            <span>⚙️</span>
            <span>Einstellungen</span>
          </button>
        )}
        {onDictionary && (
          <button
            onClick={onDictionary}
            className="flex items-center gap-2 px-4 py-2 bg-[var(--bg-card)] rounded-lg border border-white/10 hover:border-[var(--accent-highlight)] transition-colors text-sm"
          >
            <span>📖</span>
            <span>Wörterbuch</span>
          </button>
        )}
      </div>

      <div className="text-center text-xs text-white/30">
        <p>Leertaste/Enter = Signal | F11 = Vollbild</p>
      </div>
    </div>
  );
}
