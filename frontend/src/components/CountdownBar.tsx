interface CountdownBarProps {
  progress: number; // 0.0 - 1.0
  phase: string;
}

export function CountdownBar({ progress, phase }: CountdownBarProps) {
  const isActive = phase === 'confirm' && progress > 0;

  return (
    <div className="w-full h-8 bg-[var(--bg-secondary)] rounded-full overflow-hidden border border-white/10">
      <div
        className={`h-full transition-all duration-100 ease-linear rounded-full ${
          isActive ? 'bg-[var(--accent-confirm)]' : 'bg-transparent'
        }`}
        style={{ width: `${progress * 100}%` }}
      />
      {isActive && (
        <div className="absolute inset-0 flex items-center justify-center">
          <span className="text-xs font-bold text-white/70 uppercase tracking-wider">
            Bestätigung... (Signal = Abbruch)
          </span>
        </div>
      )}
    </div>
  );
}
