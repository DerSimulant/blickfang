import type { EngineState } from '../types/protocol';

interface ScanGridProps {
  state: EngineState;
}

export function ScanGrid({ state }: ScanGridProps) {
  const { layout, phase, current_row, current_col } = state;

  if (!layout || !layout.rows || layout.rows.length === 0) {
    return (
      <div className="flex items-center justify-center h-full">
        <p className="text-2xl text-[var(--text-secondary)]">Warte auf Layout...</p>
      </div>
    );
  }

  return (
    <div
      className="grid gap-2 p-4 h-full w-full"
      style={{ gridTemplateRows: `repeat(${layout.rows.length}, 1fr)` }}
    >
      {layout.rows.map((row, rIdx) => (
        <div
          key={rIdx}
          className="grid gap-2"
          style={{ gridTemplateColumns: `repeat(${row.items.length}, 1fr)` }}
        >
          {row.items.map((item, cIdx) => (
            <ScanCell
              key={`${rIdx}-${cIdx}`}
              label={item.label}
              icon={item.icon}
              isRowHighlight={phase === 'row_scan' && rIdx === current_row}
              isColHighlight={phase === 'col_scan' && rIdx === current_row && cIdx === current_col}
              isConfirm={phase === 'confirm' && rIdx === current_row && cIdx === current_col}
              isSelected={phase === 'selected' && rIdx === current_row && cIdx === current_col}
            />
          ))}
        </div>
      ))}
    </div>
  );
}

interface ScanCellProps {
  label: string;
  icon: string;
  isRowHighlight: boolean;
  isColHighlight: boolean;
  isConfirm: boolean;
  isSelected: boolean;
}

function ScanCell({ label, icon, isRowHighlight, isColHighlight, isConfirm, isSelected }: ScanCellProps) {
  let bgClass = 'bg-[var(--bg-card)]';
  let textClass = 'text-white';
  let extraClass = '';
  let borderClass = 'border-2 border-transparent';

  if (isSelected) {
    bgClass = 'bg-[var(--accent-selected)]';
    textClass = 'text-black';
    borderClass = 'border-2 border-[var(--accent-selected)]';
    extraClass = 'animate-fade-in';
  } else if (isConfirm) {
    bgClass = 'bg-[var(--accent-confirm)]';
    textClass = 'text-black';
    borderClass = 'border-2 border-[var(--accent-confirm)]';
    extraClass = 'animate-pulse-highlight';
  } else if (isColHighlight) {
    bgClass = 'bg-[var(--accent-highlight)]';
    textClass = 'text-black';
    borderClass = 'border-2 border-[var(--accent-highlight)]';
    extraClass = 'animate-pulse-highlight';
  } else if (isRowHighlight) {
    bgClass = 'bg-[var(--bg-secondary)]';
    borderClass = 'border-2 border-[var(--accent-highlight)]/50';
  }

  // Schriftgröße basierend auf Label-Länge
  let fontSize = 'text-3xl';
  if (label.length > 10) fontSize = 'text-lg';
  else if (label.length > 5) fontSize = 'text-xl';
  else if (label.length > 2) fontSize = 'text-2xl';

  return (
    <div
      className={`
        flex items-center justify-center rounded-xl
        transition-all duration-200 ease-out
        select-none cursor-default
        min-h-[60px]
        ${bgClass} ${textClass} ${borderClass} ${extraClass}
      `}
    >
      <span className={`font-bold ${fontSize} text-center px-2 leading-tight`}>
        {icon && <span className="mr-1">{icon}</span>}
        {label}
      </span>
    </div>
  );
}
