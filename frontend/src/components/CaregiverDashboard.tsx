import { useEffect, useState } from 'react';

interface DashboardData {
  running: boolean;
  mode: string;
  camera_active: boolean;
  person: string;
  scan_speed_s: number;
  uptime_s: number;
}

interface FatigueData {
  level: string;
  session_min: number;
  signals_total: number;
  mean_latency_s: number;
}

interface CaregiverDashboardProps {
  wsState: {
    mode?: string;
    fatigue?: FatigueData;
    text_buffer?: string;
    confirm_progress?: number;
  } | null;
  onClose: () => void;
}

export function CaregiverDashboard({ wsState, onClose }: CaregiverDashboardProps) {
  const [status, setStatus] = useState<DashboardData | null>(null);
  const [history, setHistory] = useState<string[]>([]);

  // Status-Polling
  useEffect(() => {
    const fetchStatus = async () => {
      try {
        const res = await fetch('/api/status');
        setStatus(await res.json());
      } catch (e) {
        console.error(e);
      }
    };
    fetchStatus();
    const interval = setInterval(fetchStatus, 2000);
    return () => clearInterval(interval);
  }, []);

  // Kommunikations-Verlauf tracken
  useEffect(() => {
    if (wsState?.text_buffer && wsState.text_buffer !== history[history.length - 1]) {
      setHistory((h) => [...h.slice(-20), wsState.text_buffer!]);
    }
  }, [wsState?.text_buffer]);

  const fatigue = wsState?.fatigue || { level: 'normal', session_min: 0, signals_total: 0, mean_latency_s: 0 };

  const fatigueColor = {
    normal: 'text-green-400',
    leicht: 'text-yellow-400',
    deutlich: 'text-orange-400',
    kritisch: 'text-red-400',
  }[fatigue.level] || 'text-white';

  const fatigueLabel = {
    normal: 'Normal',
    leicht: 'Leichte Ermüdung',
    deutlich: 'Deutliche Ermüdung',
    kritisch: 'Kritisch — Pause empfohlen!',
  }[fatigue.level] || fatigue.level;

  const formatUptime = (s: number) => {
    const min = Math.floor(s / 60);
    const sec = Math.floor(s % 60);
    return `${min}:${sec.toString().padStart(2, '0')}`;
  };

  return (
    <div className="flex flex-col h-full p-6 overflow-auto animate-fade-in">
      <div className="flex justify-between items-center mb-6">
        <h2 className="text-2xl font-bold">Betreuer-Dashboard</h2>
        <button
          onClick={onClose}
          className="px-4 py-2 bg-white/10 rounded-lg hover:bg-white/20 text-sm"
        >
          Schließen
        </button>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4 mb-6">
        {/* Status-Karte */}
        <div className="bg-[var(--bg-card)] rounded-xl p-4 border border-white/10">
          <h3 className="text-sm text-white/40 mb-2">System-Status</h3>
          <div className="space-y-2">
            <div className="flex justify-between">
              <span className="text-sm">Status</span>
              <span className={`text-sm font-medium ${status?.running ? 'text-green-400' : 'text-red-400'}`}>
                {status?.running ? 'Aktiv' : 'Gestoppt'}
              </span>
            </div>
            <div className="flex justify-between">
              <span className="text-sm">Modus</span>
              <span className="text-sm font-mono">{wsState?.mode || status?.mode || '—'}</span>
            </div>
            <div className="flex justify-between">
              <span className="text-sm">Kamera</span>
              <span className={`text-sm ${status?.camera_active ? 'text-green-400' : 'text-white/40'}`}>
                {status?.camera_active ? 'Aktiv' : 'Aus'}
              </span>
            </div>
            <div className="flex justify-between">
              <span className="text-sm">Person</span>
              <span className="text-sm">{status?.person || '—'}</span>
            </div>
            <div className="flex justify-between">
              <span className="text-sm">Laufzeit</span>
              <span className="text-sm font-mono">{formatUptime(status?.uptime_s || 0)}</span>
            </div>
          </div>
        </div>

        {/* Ermüdungs-Karte */}
        <div className="bg-[var(--bg-card)] rounded-xl p-4 border border-white/10">
          <h3 className="text-sm text-white/40 mb-2">Ermüdung</h3>
          <div className={`text-2xl font-bold mb-2 ${fatigueColor}`}>
            {fatigueLabel}
          </div>
          <div className="space-y-2">
            <div className="flex justify-between">
              <span className="text-sm">Session-Dauer</span>
              <span className="text-sm font-mono">{fatigue.session_min} min</span>
            </div>
            <div className="flex justify-between">
              <span className="text-sm">Signale gesamt</span>
              <span className="text-sm font-mono">{fatigue.signals_total}</span>
            </div>
            <div className="flex justify-between">
              <span className="text-sm">Ø Latenz</span>
              <span className="text-sm font-mono">{fatigue.mean_latency_s}s</span>
            </div>
          </div>
          {fatigue.level === 'kritisch' && (
            <div className="mt-3 p-2 bg-red-900/40 border border-red-500/50 rounded text-xs text-red-300 text-center">
              Pause empfohlen! Die Person zeigt Zeichen von Ermüdung.
            </div>
          )}
        </div>

        {/* Scan-Einstellungen Karte */}
        <div className="bg-[var(--bg-card)] rounded-xl p-4 border border-white/10">
          <h3 className="text-sm text-white/40 mb-2">Scan-Parameter</h3>
          <div className="space-y-2">
            <div className="flex justify-between">
              <span className="text-sm">Geschwindigkeit</span>
              <span className="text-sm font-mono">{status?.scan_speed_s || 1.5}s</span>
            </div>
            <div className="flex justify-between">
              <span className="text-sm">Bestätigungs-Fortschritt</span>
              <span className="text-sm font-mono">
                {((wsState?.confirm_progress || 0) * 100).toFixed(0)}%
              </span>
            </div>
          </div>
          {/* Schnell-Aktionen */}
          <div className="mt-4 space-y-2">
            <button
              onClick={() => fetch('/api/config', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ scan_speed_s: (status?.scan_speed_s || 1.5) + 0.5 }),
              })}
              className="w-full py-2 bg-white/10 rounded text-sm hover:bg-white/20"
            >
              ↓ Langsamer
            </button>
            <button
              onClick={() => fetch('/api/config', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ scan_speed_s: Math.max(0.5, (status?.scan_speed_s || 1.5) - 0.5) }),
              })}
              className="w-full py-2 bg-white/10 rounded text-sm hover:bg-white/20"
            >
              ↑ Schneller
            </button>
          </div>
        </div>
      </div>

      {/* Kommunikations-Verlauf */}
      <div className="bg-[var(--bg-card)] rounded-xl p-4 border border-white/10 flex-1 min-h-[200px]">
        <div className="flex justify-between items-center mb-3">
          <h3 className="text-sm text-white/40">Kommunikations-Verlauf</h3>
          <div className="flex gap-2">
            <a
              href="/api/session/export"
              download
              className="px-2 py-1 bg-white/10 rounded text-xs hover:bg-white/20"
            >
              Exportieren
            </a>
            <button
              onClick={() => { fetch('/api/session/history', { method: 'DELETE' }); }}
              className="px-2 py-1 bg-white/10 rounded text-xs hover:bg-white/20 text-red-300"
            >
              Löschen
            </button>
          </div>
        </div>
        {wsState?.text_buffer ? (
          <div className="mb-3 p-3 bg-[var(--accent-highlight)]/10 border border-[var(--accent-highlight)]/30 rounded-lg">
            <span className="text-xs text-white/40">Aktueller Text:</span>
            <p className="text-lg font-medium mt-1">{wsState.text_buffer}</p>
          </div>
        ) : null}
        <div className="space-y-1 overflow-auto max-h-[300px]">
          {history.length === 0 ? (
            <p className="text-white/30 text-sm">Noch keine Kommunikation.</p>
          ) : (
            history.map((text, i) => (
              <div key={i} className="text-sm py-1 border-b border-white/5">
                <span className="text-white/30 mr-2">#{i + 1}</span>
                {text}
              </div>
            ))
          )}
        </div>
      </div>
    </div>
  );
}
