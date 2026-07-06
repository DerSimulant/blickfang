import { useCallback, useEffect, useState } from 'react';

interface Settings {
  scan_speed_s: number;
  cancel_countdown_s: number;
  speak_on_highlight: boolean;
}

interface Profile {
  name: string;
  channel: string;
  created: string;
  path: string;
}

interface SettingsPanelProps {
  onClose: () => void;
}

export function SettingsPanel({ onClose }: SettingsPanelProps) {
  const [settings, setSettings] = useState<Settings>({
    scan_speed_s: 1.5,
    cancel_countdown_s: 2.5,
    speak_on_highlight: true,
  });
  const [profiles, setProfiles] = useState<Profile[]>([]);
  const [saved, setSaved] = useState(false);

  useEffect(() => {
    // Profile laden
    fetch('/api/profiles')
      .then((r) => r.json())
      .then(setProfiles)
      .catch(console.error);

    // Status laden für aktuelle Settings
    fetch('/api/status')
      .then((r) => r.json())
      .then((data) => {
        setSettings((s) => ({
          ...s,
          scan_speed_s: data.scan_speed_s || s.scan_speed_s,
        }));
      })
      .catch(console.error);
  }, []);

  const updateSetting = useCallback(
    async (key: keyof Settings, value: number | boolean) => {
      const newSettings = { ...settings, [key]: value };
      setSettings(newSettings);

      await fetch('/api/config', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ [key]: value }),
      });

      setSaved(true);
      setTimeout(() => setSaved(false), 1500);
    },
    [settings]
  );

  const deleteProfile = useCallback(async (path: string, name: string) => {
    if (!confirm(`Profil "${name}" wirklich löschen?`)) return;
    // Delete via API (we'll add this endpoint)
    await fetch('/api/profiles/' + encodeURIComponent(name), { method: 'DELETE' });
    setProfiles((p) => p.filter((pr) => pr.path !== path));
  }, []);

  return (
    <div className="flex flex-col h-full p-6 overflow-auto animate-fade-in">
      <div className="flex justify-between items-center mb-6">
        <h2 className="text-2xl font-bold">Einstellungen</h2>
        <button
          onClick={onClose}
          className="px-4 py-2 bg-white/10 rounded-lg hover:bg-white/20 text-sm"
        >
          Schließen
        </button>
      </div>

      {saved && (
        <div className="mb-4 px-4 py-2 bg-green-900/40 border border-green-500/50 rounded-lg text-sm text-green-300 text-center">
          Einstellung gespeichert
        </div>
      )}

      {/* Scanning-Einstellungen */}
      <section className="mb-8">
        <h3 className="text-lg font-semibold mb-4 text-[var(--accent-highlight)]">
          Scanning
        </h3>
        <div className="space-y-6 max-w-lg">
          {/* Scan-Geschwindigkeit */}
          <div>
            <div className="flex justify-between mb-2">
              <label className="text-sm font-medium">Scan-Geschwindigkeit</label>
              <span className="font-mono text-sm text-[var(--accent-selected)]">
                {settings.scan_speed_s.toFixed(1)}s
              </span>
            </div>
            <input
              type="range"
              min={0.5}
              max={4.0}
              step={0.1}
              value={settings.scan_speed_s}
              onChange={(e) => updateSetting('scan_speed_s', parseFloat(e.target.value))}
              className="w-full h-2 bg-white/10 rounded-lg appearance-none cursor-pointer accent-[var(--accent-highlight)]"
            />
            <div className="flex justify-between text-xs text-white/40 mt-1">
              <span>Schnell (0.5s)</span>
              <span>Langsam (4.0s)</span>
            </div>
            <p className="text-xs text-white/40 mt-1">
              Wie lange jede Option hervorgehoben wird. Langsamer = einfacher, aber dauert länger.
            </p>
          </div>

          {/* Cancel-Countdown */}
          <div>
            <div className="flex justify-between mb-2">
              <label className="text-sm font-medium">Cancel-Countdown</label>
              <span className="font-mono text-sm text-[var(--accent-selected)]">
                {settings.cancel_countdown_s.toFixed(1)}s
              </span>
            </div>
            <input
              type="range"
              min={1.0}
              max={5.0}
              step={0.5}
              value={settings.cancel_countdown_s}
              onChange={(e) =>
                updateSetting('cancel_countdown_s', parseFloat(e.target.value))
              }
              className="w-full h-2 bg-white/10 rounded-lg appearance-none cursor-pointer accent-[var(--accent-highlight)]"
            />
            <div className="flex justify-between text-xs text-white/40 mt-1">
              <span>Kurz (1.0s)</span>
              <span>Lang (5.0s)</span>
            </div>
            <p className="text-xs text-white/40 mt-1">
              Zeit zum Abbrechen einer Auswahl. Länger = sicherer gegen Fehler.
            </p>
          </div>

          {/* Sprachausgabe beim Scannen */}
          <div className="flex items-center justify-between">
            <div>
              <label className="text-sm font-medium">Optionen vorlesen</label>
              <p className="text-xs text-white/40">
                Jede Option wird beim Hervorheben vorgelesen.
              </p>
            </div>
            <button
              onClick={() => updateSetting('speak_on_highlight', !settings.speak_on_highlight)}
              className={`w-14 h-7 rounded-full transition-colors ${
                settings.speak_on_highlight ? 'bg-[var(--accent-selected)]' : 'bg-white/20'
              }`}
            >
              <div
                className={`w-5 h-5 bg-white rounded-full transition-transform mx-1 ${
                  settings.speak_on_highlight ? 'translate-x-7' : 'translate-x-0'
                }`}
              />
            </button>
          </div>
        </div>
      </section>

      {/* Profile */}
      <section className="mb-8">
        <h3 className="text-lg font-semibold mb-4 text-[var(--accent-highlight)]">
          Profile
        </h3>
        {profiles.length === 0 ? (
          <p className="text-white/40 text-sm">
            Noch keine Profile vorhanden. Starten Sie eine Kalibrierung.
          </p>
        ) : (
          <div className="space-y-2 max-w-lg">
            {profiles.map((p) => (
              <div
                key={p.path}
                className="flex items-center justify-between p-3 bg-[var(--bg-card)] rounded-lg border border-white/10"
              >
                <div>
                  <span className="font-medium">{p.name}</span>
                  {p.channel && (
                    <span className="text-xs text-white/40 ml-2">({p.channel})</span>
                  )}
                  {p.created && (
                    <span className="text-xs text-white/30 ml-2">{p.created.slice(0, 10)}</span>
                  )}
                </div>
                <button
                  onClick={() => deleteProfile(p.path, p.name)}
                  className="text-xs text-red-400 hover:text-red-300 px-2 py-1"
                >
                  Löschen
                </button>
              </div>
            ))}
          </div>
        )}
      </section>

      {/* Info */}
      <section>
        <h3 className="text-lg font-semibold mb-4 text-[var(--accent-highlight)]">
          Tastenkürzel
        </h3>
        <div className="space-y-2 max-w-lg text-sm">
          <div className="flex justify-between p-2 bg-[var(--bg-card)] rounded">
            <span>Signal geben</span>
            <kbd className="px-2 py-0.5 bg-white/10 rounded text-xs font-mono">Leertaste</kbd>
          </div>
          <div className="flex justify-between p-2 bg-[var(--bg-card)] rounded">
            <span>Vollbild</span>
            <kbd className="px-2 py-0.5 bg-white/10 rounded text-xs font-mono">F11</kbd>
          </div>
          <div className="flex justify-between p-2 bg-[var(--bg-card)] rounded">
            <span>Notruf (3× schnell)</span>
            <kbd className="px-2 py-0.5 bg-white/10 rounded text-xs font-mono">Leertaste ×3</kbd>
          </div>
        </div>
      </section>
    </div>
  );
}
