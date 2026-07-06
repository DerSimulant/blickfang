interface StatusFooterProps {
  phase: string;
  confirmProgress: number;
}

export function StatusFooter({ phase, confirmProgress }: StatusFooterProps) {
  const getPhaseText = () => {
    switch (phase) {
      case 'row_scan': return 'Zeilen-Scan — Signal = Zeile wählen';
      case 'col_scan': return 'Spalten-Scan — Signal = Item wählen';
      case 'confirm': return 'Bestätigung läuft — Signal = ABBRUCH';
      case 'selected': return 'Ausgewählt!';
      case 'cancelled': return 'Abgebrochen — Scan startet neu';
      case 'no_answer': return 'Keine Antwort — Timeout';
      default: return 'Bereit — Leertaste = Signal';
    }
  };

  const isConfirm = phase === 'confirm';

  return (
    <div className="px-6 py-2 bg-[var(--bg-secondary)] border-t border-white/10">
      {/* Countdown-Balken */}
      <div className="w-full h-6 bg-black/30 rounded-full overflow-hidden mb-2 relative">
        <div
          className={`h-full rounded-full transition-all duration-100 ease-linear ${
            isConfirm ? 'bg-[var(--accent-confirm)]' : 'bg-transparent'
          }`}
          style={{ width: `${confirmProgress * 100}%` }}
        />
        {isConfirm && (
          <div className="absolute inset-0 flex items-center justify-center">
            <span className="text-xs font-bold text-white uppercase tracking-wider drop-shadow">
              Signal zum Abbrechen!
            </span>
          </div>
        )}
      </div>

      {/* Status-Text */}
      <div className="flex items-center justify-between">
        <span className="text-sm text-[var(--text-secondary)]">{getPhaseText()}</span>
        <span className="text-xs text-white/30">
          Leertaste/Enter = Signal | ESC = Vollbild | F11 = Vollbild
        </span>
      </div>
    </div>
  );
}
