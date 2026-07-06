interface StartScreenProps {
  onStart: (mode: string) => void;
}

export function StartScreen({ onStart }: StartScreenProps) {
  return (
    <div className="flex flex-col items-center justify-center h-full gap-8 animate-fade-in p-8">
      <div className="text-center">
        <h1 className="text-5xl font-bold mb-4 tracking-tight">blickfang</h1>
        <p className="text-xl text-[var(--text-secondary)]">
          Kommunikation durch Mimik-Erkennung
        </p>
      </div>

      <div className="grid grid-cols-2 gap-4 w-full max-w-lg">
        <button
          onClick={() => onStart('phrases')}
          className="flex flex-col items-center gap-3 p-8 bg-[var(--bg-card)] rounded-2xl border-2 border-transparent hover:border-[var(--accent-highlight)] transition-all duration-200"
        >
          <span className="text-4xl">💬</span>
          <span className="text-lg font-bold">Schnell-Phrasen</span>
          <span className="text-sm text-[var(--text-secondary)]">Vorgefertigte Sätze</span>
        </button>

        <button
          onClick={() => onStart('keyboard')}
          className="flex flex-col items-center gap-3 p-8 bg-[var(--bg-card)] rounded-2xl border-2 border-transparent hover:border-[var(--accent-highlight)] transition-all duration-200"
        >
          <span className="text-4xl">⌨</span>
          <span className="text-lg font-bold">Buchstabieren</span>
          <span className="text-sm text-[var(--text-secondary)]">Freier Text</span>
        </button>

        <button
          onClick={() => onStart('yesno')}
          className="flex flex-col items-center gap-3 p-8 bg-[var(--bg-card)] rounded-2xl border-2 border-transparent hover:border-[var(--accent-highlight)] transition-all duration-200"
        >
          <span className="text-4xl">✓✗</span>
          <span className="text-lg font-bold">Ja / Nein</span>
          <span className="text-sm text-[var(--text-secondary)]">Einfache Antworten</span>
        </button>

        <button
          onClick={() => onStart('main_menu')}
          className="flex flex-col items-center gap-3 p-8 bg-[var(--bg-card)] rounded-2xl border-2 border-transparent hover:border-[var(--accent-highlight)] transition-all duration-200"
        >
          <span className="text-4xl">🏠</span>
          <span className="text-lg font-bold">Hauptmenü</span>
          <span className="text-sm text-[var(--text-secondary)]">Alle Modi per Scan</span>
        </button>
      </div>

      <div className="text-center text-sm text-white/30 mt-4">
        <p>Leertaste oder Enter = Signal geben</p>
        <p>F11 = Vollbild | ESC = Beenden</p>
      </div>
    </div>
  );
}
