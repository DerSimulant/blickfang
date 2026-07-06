import type { CommMode, FatigueMetrics } from '../types/protocol';

interface ModeBarProps {
  mode: CommMode;
  fatigue: FatigueMetrics;
  connected: boolean;
  onSwitchMode: (mode: string) => void;
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
  mild: 'text-yellow-400',
  moderate: 'text-orange-400',
  high: 'text-red-400',
};

export function ModeBar({ mode, fatigue, connected, onSwitchMode }: ModeBarProps) {
  const modeInfo = MODE_LABELS[mode] || MODE_LABELS.idle;

  return (
    <div className="flex items-center justify-between px-6 py-3 bg-[var(--bg-secondary)] border-b border-white/10">
      {/* Linke Seite: Modus */}
      <div className="flex items-center gap-3">
        <span className="text-2xl">{modeInfo.icon}</span>
        <h1 className="text-xl font-bold tracking-wide">{modeInfo.label}</h1>
      </div>

      {/* Mitte: Modus-Buttons (für Caregiver) */}
      <div className="flex gap-2">
        {(['main_menu', 'phrases', 'keyboard', 'yesno'] as const).map((m) => (
          <button
            key={m}
            onClick={() => onSwitchMode(m)}
            className={`px-3 py-1 rounded-lg text-sm font-medium transition-colors ${
              mode === m
                ? 'bg-[var(--accent-highlight)] text-black'
                : 'bg-white/5 text-white/60 hover:bg-white/10 hover:text-white'
            }`}
          >
            {MODE_LABELS[m].icon} {MODE_LABELS[m].label}
          </button>
        ))}
      </div>

      {/* Rechte Seite: Status */}
      <div className="flex items-center gap-4 text-sm">
        {/* Ermüdung */}
        <div className={`flex items-center gap-1 ${FATIGUE_COLORS[fatigue.level]}`}>
          <span>{fatigue.session_min}min</span>
          <span className="text-xs opacity-60">|</span>
          <span>{fatigue.signals_total} Signale</span>
        </div>

        {/* Verbindungsstatus */}
        <div className={`flex items-center gap-1 ${connected ? 'text-green-400' : 'text-red-400'}`}>
          <div className={`w-2 h-2 rounded-full ${connected ? 'bg-green-400' : 'bg-red-400'}`} />
          <span className="text-xs">{connected ? 'Verbunden' : 'Getrennt'}</span>
        </div>
      </div>
    </div>
  );
}
