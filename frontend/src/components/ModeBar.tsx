import type { CommMode, FatigueMetrics } from '../types/protocol';

interface ModeBarProps {
  mode: CommMode;
  fatigue: FatigueMetrics;
  connected: boolean;
  onSwitchMode: (mode: string) => void;
  onOpenSettings?: () => void;
  onOpenDashboard?: () => void;
  onOpenCalibration?: () => void;
}

const MODE_LABELS: Record<string, { label: string; icon: string }> = {
  idle: { label: 'Bereit', icon: '⏸' },
  main_menu: { label: 'HAUPTMENÜ', icon: '🏠' },
  phrases: { label: 'SCHNELL-PHRASEN', icon: '💬' },
  keyboard: { label: 'BUCHSTABIEREN', icon: '⌨' },
  yesno: { label: 'JA / NEIN / PASSE', icon: '✓✗' },
};

const FATIGUE_COLORS: Record<string, string> = {
  normal: 'text-green-400',
  leicht: 'text-yellow-400',
  deutlich: 'text-orange-400',
  kritisch: 'text-red-400',
};

export function ModeBar({
  mode,
  fatigue,
  connected,
  onSwitchMode,
  onOpenSettings,
  onOpenDashboard,
  onOpenCalibration,
}: ModeBarProps) {
  const modeInfo = MODE_LABELS[mode] || MODE_LABELS.idle;

  return (
    <div className="flex items-center justify-between px-4 py-2 bg-[var(--bg-secondary)] border-b border-white/10">
      {/* Linke Seite: Modus */}
      <div className="flex items-center gap-2">
        <span className="text-xl">{modeInfo.icon}</span>
        <h1 className="text-lg font-bold tracking-wide">{modeInfo.label}</h1>
      </div>

      {/* Mitte: Modus-Buttons (für Caregiver) */}
      <div className="flex gap-1">
        {(['main_menu', 'phrases', 'keyboard', 'yesno'] as const).map((m) => (
          <button
            key={m}
            onClick={() => onSwitchMode(m)}
            className={`px-2 py-1 rounded text-xs font-medium transition-colors ${
              mode === m
                ? 'bg-[var(--accent-highlight)] text-black'
                : 'bg-white/5 text-white/60 hover:bg-white/10 hover:text-white'
            }`}
          >
            {MODE_LABELS[m].icon}
          </button>
        ))}
      </div>

      {/* Rechte Seite: Tools + Status */}
      <div className="flex items-center gap-3 text-sm">
        {/* Ermüdung */}
        <div className={`flex items-center gap-1 ${FATIGUE_COLORS[fatigue.level] || 'text-white/60'}`}>
          <span className="text-xs">{fatigue.session_min}min</span>
          <span className="text-xs opacity-40">|</span>
          <span className="text-xs">{fatigue.signals_total} Sig.</span>
        </div>

        {/* Tool-Buttons */}
        <div className="flex gap-1 border-l border-white/10 pl-3">
          {onOpenDashboard && (
            <button
              onClick={onOpenDashboard}
              className="px-2 py-1 bg-white/5 rounded text-xs hover:bg-white/10"
              title="Betreuer-Dashboard"
            >
              📊
            </button>
          )}
          {onOpenCalibration && (
            <button
              onClick={onOpenCalibration}
              className="px-2 py-1 bg-white/5 rounded text-xs hover:bg-white/10"
              title="Kalibrierung"
            >
              🎯
            </button>
          )}
          {onOpenSettings && (
            <button
              onClick={onOpenSettings}
              className="px-2 py-1 bg-white/5 rounded text-xs hover:bg-white/10"
              title="Einstellungen"
            >
              ⚙️
            </button>
          )}
        </div>

        {/* Verbindungsstatus */}
        <div className={`flex items-center gap-1 ${connected ? 'text-green-400' : 'text-red-400'}`}>
          <div className={`w-2 h-2 rounded-full ${connected ? 'bg-green-400' : 'bg-red-400'}`} />
        </div>
      </div>
    </div>
  );
}
