import { useCallback, useEffect, useState } from 'react';

interface CalibEvent {
  index: number;
  channel: string;
  timestamp: number;
  peak_value: number;
  confirmed: boolean;
}

interface CalibStatus {
  active: boolean;
  phase: string;
  person_name: string;
  frames_collected: number;
  elapsed_s: number;
  signal_events: CalibEvent[];
  confirmed_count: number;
  ranking: { channel: string; fp_at_90tp: number; auc: number; direction: number; threshold_delta: number }[];
  best_channel: string;
  error: string;
  live_channels: Record<string, number>;
  profile_path?: string;
}

interface CalibrationViewProps {
  onDone: () => void;
}

export function CalibrationView({ onDone }: CalibrationViewProps) {
  const [status, setStatus] = useState<CalibStatus | null>(null);
  const [personName, setPersonName] = useState('');
  const [signalCount, setSignalCount] = useState(10);
  const [neutralDuration, setNeutralDuration] = useState(60);
  const [polling, setPolling] = useState(false);

  // Polling für Status-Updates
  useEffect(() => {
    if (!polling) return;
    const interval = setInterval(async () => {
      try {
        const res = await fetch('/api/calibration/status');
        const data = await res.json();
        setStatus(data);
      } catch (e) {
        console.error('Status-Fehler:', e);
      }
    }, 500);
    return () => clearInterval(interval);
  }, [polling]);

  const startCalibration = useCallback(async () => {
    if (!personName.trim()) return;
    const res = await fetch('/api/calibration/start', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        person_name: personName.trim(),
        signal_count: signalCount,
        neutral_duration_s: neutralDuration,
      }),
    });
    await res.json();
    setPolling(true);
  }, [personName, signalCount, neutralDuration]);

  const stopSignal = useCallback(async () => {
    await fetch('/api/calibration/stop-signal', { method: 'POST' });
  }, []);

  const confirmAll = useCallback(async () => {
    await fetch('/api/calibration/confirm-all', { method: 'POST' });
  }, []);

  const confirmEvent = useCallback(async (index: number, confirmed: boolean) => {
    await fetch('/api/calibration/confirm-event', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ event_index: index, confirmed }),
    });
  }, []);

  const startNeutral = useCallback(async () => {
    await fetch('/api/calibration/start-neutral', { method: 'POST' });
  }, []);

  const stopNeutral = useCallback(async () => {
    await fetch('/api/calibration/stop-neutral', { method: 'POST' });
  }, []);

  const saveProfile = useCallback(async () => {
    await fetch('/api/calibration/save-profile', { method: 'POST' });
  }, []);

  const cancel = useCallback(async () => {
    await fetch('/api/calibration/cancel', { method: 'POST' });
    setPolling(false);
    setStatus(null);
  }, []);

  // Phase-Anzeige
  const phase = status?.phase || 'idle';

  // Start-Formular
  if (!status || phase === 'idle' || phase === 'cancelled') {
    return (
      <div className="flex flex-col items-center justify-center h-full gap-6 p-8 animate-fade-in">
        <h1 className="text-3xl font-bold">Kalibrierung</h1>
        <p className="text-[var(--text-secondary)] text-center max-w-lg">
          Die Kalibrierung findet das beste Signal der Person und erstellt ein Profil
          für die Kommunikation.
        </p>

        <div className="w-full max-w-md space-y-4">
          <div>
            <label className="block text-sm font-medium mb-1">Name der Person</label>
            <input
              type="text"
              value={personName}
              onChange={(e) => setPersonName(e.target.value)}
              className="w-full px-4 py-3 bg-[var(--bg-card)] rounded-lg border border-white/10 text-white text-lg focus:border-[var(--accent-highlight)] focus:outline-none"
              placeholder="z.B. Anna"
            />
          </div>

          <div className="grid grid-cols-2 gap-4">
            <div>
              <label className="block text-sm font-medium mb-1">Signale (Anzahl)</label>
              <input
                type="number"
                value={signalCount}
                onChange={(e) => setSignalCount(Number(e.target.value))}
                className="w-full px-4 py-3 bg-[var(--bg-card)] rounded-lg border border-white/10 text-white focus:border-[var(--accent-highlight)] focus:outline-none"
                min={3}
                max={30}
              />
            </div>
            <div>
              <label className="block text-sm font-medium mb-1">Ruhephase (Sek.)</label>
              <input
                type="number"
                value={neutralDuration}
                onChange={(e) => setNeutralDuration(Number(e.target.value))}
                className="w-full px-4 py-3 bg-[var(--bg-card)] rounded-lg border border-white/10 text-white focus:border-[var(--accent-highlight)] focus:outline-none"
                min={30}
                max={300}
              />
            </div>
          </div>

          <button
            onClick={startCalibration}
            disabled={!personName.trim()}
            className="w-full py-4 bg-[var(--accent-highlight)] text-black font-bold text-lg rounded-lg hover:opacity-90 transition-opacity disabled:opacity-30"
          >
            Kalibrierung starten
          </button>
        </div>

        <button onClick={onDone} className="text-sm text-white/40 hover:text-white/70 mt-4">
          Zurück
        </button>
      </div>
    );
  }

  // Signal-Phase
  if (phase === 'signal') {
    return (
      <div className="flex flex-col items-center justify-center h-full gap-6 p-8">
        <div className="text-center">
          <h2 className="text-2xl font-bold mb-2">Signal-Aufnahme</h2>
          <p className="text-[var(--text-secondary)]">
            Bitte erzeugen Sie Ihr Signal {signalCount}× — in Ihrem eigenen Tempo.
          </p>
        </div>

        {/* Live-Anzeige */}
        <div className="bg-[var(--bg-card)] rounded-xl p-6 w-full max-w-lg">
          <div className="flex justify-between mb-2">
            <span className="text-sm text-white/60">Frames gesammelt</span>
            <span className="font-mono">{status.frames_collected}</span>
          </div>
          <div className="flex justify-between mb-2">
            <span className="text-sm text-white/60">Zeit</span>
            <span className="font-mono">{status.elapsed_s.toFixed(1)}s</span>
          </div>
          {/* Live-Kanäle */}
          <div className="mt-4 space-y-1">
            <span className="text-xs text-white/40">Live-Kanäle (Top 5):</span>
            {Object.entries(status.live_channels || {}).slice(0, 5).map(([ch, val]) => (
              <div key={ch} className="flex justify-between text-xs">
                <span className="text-white/60 truncate max-w-[200px]">{ch}</span>
                <span className="font-mono">{val.toFixed(3)}</span>
              </div>
            ))}
          </div>
        </div>

        <div className="flex gap-4">
          <button
            onClick={stopSignal}
            className="px-6 py-3 bg-[var(--accent-selected)] text-black font-bold rounded-lg hover:opacity-90"
          >
            Signal-Phase beenden
          </button>
          <button
            onClick={cancel}
            className="px-6 py-3 bg-[var(--accent-cancel)] text-white font-bold rounded-lg hover:opacity-90"
          >
            Abbrechen
          </button>
        </div>
      </div>
    );
  }

  // Bestätigungs-Phase
  if (phase === 'confirm') {
    return (
      <div className="flex flex-col h-full p-6 overflow-auto">
        <div className="text-center mb-4">
          <h2 className="text-2xl font-bold">Signal-Events bestätigen</h2>
          <p className="text-[var(--text-secondary)]">
            {status.signal_events.length} Events gefunden — bitte bestätigen Sie die echten Signale.
          </p>
          <p className="text-sm text-white/40 mt-1">
            Bestätigt: {status.confirmed_count} / {status.signal_events.length}
          </p>
        </div>

        {/* Event-Liste */}
        <div className="flex-1 overflow-auto space-y-2 max-w-2xl mx-auto w-full">
          {status.signal_events.map((ev) => (
            <div
              key={ev.index}
              className={`flex items-center justify-between p-3 rounded-lg border ${
                ev.confirmed
                  ? 'bg-green-900/30 border-green-500/50'
                  : 'bg-[var(--bg-card)] border-white/10'
              }`}
            >
              <div>
                <span className="font-mono text-sm">{ev.channel}</span>
                <span className="text-xs text-white/40 ml-3">
                  t={ev.timestamp}s | Wert={ev.peak_value}
                </span>
              </div>
              <div className="flex gap-2">
                <button
                  onClick={() => confirmEvent(ev.index, true)}
                  className="px-3 py-1 bg-green-600 text-white text-sm rounded hover:bg-green-500"
                >
                  ✓ Ja
                </button>
                <button
                  onClick={() => confirmEvent(ev.index, false)}
                  className="px-3 py-1 bg-red-600 text-white text-sm rounded hover:bg-red-500"
                >
                  ✗ Nein
                </button>
              </div>
            </div>
          ))}
        </div>

        <div className="flex gap-4 justify-center mt-4">
          <button
            onClick={confirmAll}
            className="px-6 py-3 bg-green-600 text-white font-bold rounded-lg hover:opacity-90"
          >
            Alle bestätigen
          </button>
          <button
            onClick={startNeutral}
            disabled={status.confirmed_count < 3}
            className="px-6 py-3 bg-[var(--accent-highlight)] text-black font-bold rounded-lg hover:opacity-90 disabled:opacity-30"
          >
            Weiter → Ruhephase
          </button>
          <button
            onClick={cancel}
            className="px-6 py-3 bg-white/10 text-white rounded-lg hover:bg-white/20"
          >
            Abbrechen
          </button>
        </div>
      </div>
    );
  }

  // Neutral-Phase
  if (phase === 'neutral') {
    const progress = Math.min(status.elapsed_s / neutralDuration, 1.0);
    return (
      <div className="flex flex-col items-center justify-center h-full gap-6 p-8">
        <div className="text-center">
          <h2 className="text-2xl font-bold mb-2">Ruhephase</h2>
          <p className="text-[var(--text-secondary)]">
            Bitte bleiben Sie ruhig. Unwillkürliche Bewegungen sind OK.
          </p>
        </div>

        {/* Fortschrittsbalken */}
        <div className="w-full max-w-lg">
          <div className="w-full h-8 bg-[var(--bg-card)] rounded-full overflow-hidden">
            <div
              className="h-full bg-[var(--accent-selected)] rounded-full transition-all duration-500"
              style={{ width: `${progress * 100}%` }}
            />
          </div>
          <div className="flex justify-between mt-2 text-sm text-white/60">
            <span>{status.elapsed_s.toFixed(0)}s</span>
            <span>{neutralDuration}s</span>
          </div>
          <p className="text-center text-sm text-white/40 mt-2">
            {status.frames_collected} Frames | {Object.keys(status.live_channels || {}).length} Kanäle
          </p>
        </div>

        <button
          onClick={stopNeutral}
          className="px-6 py-3 bg-[var(--accent-highlight)] text-black font-bold rounded-lg hover:opacity-90"
        >
          Ruhephase beenden
        </button>
      </div>
    );
  }

  // Ranking-Ergebnis
  if (phase === 'ranking' || phase === 'saving' || phase === 'done') {
    return (
      <div className="flex flex-col items-center justify-center h-full gap-6 p-8">
        <div className="text-center">
          <h2 className="text-2xl font-bold mb-2">
            {phase === 'done' ? 'Kalibrierung abgeschlossen!' : 'Kanal-Ranking'}
          </h2>
          {status.best_channel && (
            <p className="text-lg text-[var(--accent-selected)]">
              Bester Kanal: <strong>{status.best_channel}</strong>
            </p>
          )}
        </div>

        {/* Ranking-Tabelle */}
        <div className="w-full max-w-lg bg-[var(--bg-card)] rounded-xl p-4">
          <table className="w-full text-sm">
            <thead>
              <tr className="text-white/40 border-b border-white/10">
                <th className="text-left py-2">#</th>
                <th className="text-left py-2">Kanal</th>
                <th className="text-right py-2">FP@90TP</th>
                <th className="text-right py-2">AUC</th>
              </tr>
            </thead>
            <tbody>
              {status.ranking.map((r, i) => (
                <tr
                  key={r.channel}
                  className={`border-b border-white/5 ${
                    r.channel === status.best_channel ? 'text-[var(--accent-selected)]' : ''
                  }`}
                >
                  <td className="py-2">{i + 1}</td>
                  <td className="py-2 font-mono text-xs">{r.channel}</td>
                  <td className="py-2 text-right">{r.fp_at_90tp.toFixed(4)}</td>
                  <td className="py-2 text-right">{r.auc.toFixed(3)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>

        {phase === 'done' && status.profile_path && (
          <p className="text-sm text-white/40">
            Profil gespeichert: {status.profile_path}
          </p>
        )}

        <div className="flex gap-4">
          {phase !== 'done' && (
            <button
              onClick={saveProfile}
              className="px-6 py-3 bg-[var(--accent-highlight)] text-black font-bold rounded-lg hover:opacity-90"
            >
              Profil speichern
            </button>
          )}
          <button
            onClick={() => { setPolling(false); setStatus(null); onDone(); }}
            className="px-6 py-3 bg-white/10 text-white rounded-lg hover:bg-white/20"
          >
            {phase === 'done' ? 'Fertig — zurück zur Kommunikation' : 'Abbrechen'}
          </button>
        </div>
      </div>
    );
  }

  // Fehler-Anzeige
  if (status.error) {
    return (
      <div className="flex flex-col items-center justify-center h-full gap-4 p-8">
        <div className="text-4xl">⚠️</div>
        <h2 className="text-xl font-bold text-[var(--accent-cancel)]">Fehler</h2>
        <p className="text-[var(--text-secondary)]">{status.error}</p>
        <button
          onClick={() => { setPolling(false); setStatus(null); }}
          className="px-6 py-3 bg-white/10 text-white rounded-lg hover:bg-white/20"
        >
          Zurück
        </button>
      </div>
    );
  }

  return null;
}
