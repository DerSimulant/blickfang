interface TextDisplayProps {
  text: string;
  predictions: string[];
}

export function TextDisplay({ text, predictions }: TextDisplayProps) {
  return (
    <div className="flex flex-col gap-2 px-6 py-3">
      {/* Text-Anzeige */}
      <div className="bg-[var(--bg-secondary)] rounded-xl px-6 py-4 border border-white/10 min-h-[70px] flex items-center">
        <span className="text-2xl font-mono text-white tracking-wide">
          {text || <span className="text-white/30">Hier erscheint dein Text...</span>}
          <span className="animate-pulse text-[var(--accent-highlight)]">▌</span>
        </span>
      </div>

      {/* Wortvorschläge */}
      {predictions.length > 0 && (
        <div className="flex gap-2 px-2">
          {predictions.map((pred, i) => (
            <div
              key={i}
              className="px-4 py-2 bg-[var(--bg-card)] rounded-lg text-sm text-[var(--text-secondary)] border border-white/5"
            >
              <span className="text-xs text-white/30 mr-1">{i + 1}.</span>
              {pred}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
