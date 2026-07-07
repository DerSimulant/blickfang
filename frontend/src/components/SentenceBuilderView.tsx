/**
 * SentenceBuilderView: React-Komponente für den Satz-Builder.
 *
 * Zeigt Templates, Slots und Wörter als Scanning-Grid an.
 * Integriert sich nahtlos in das bestehende Scanning-Framework.
 */

import { useState, useEffect, useCallback } from 'react';

interface Word {
  text: string;
  display: string;
  icon: string;
  category: string;
}

interface Slot {
  label: string;
  slot_type: string;
  words: Word[];
  optional: boolean;
  selected: Word | null;
}

interface Template {
  name: string;
  description: string;
  slots: Slot[];
}

interface SentenceBuilderState {
  templates: Template[];
  active_template: Template | null;
  current_slot_idx: number;
  built_sentence: string;
  phase: 'template_select' | 'slot_fill' | 'preview';
}

interface SentenceBuilderViewProps {
  onSendSignal: () => void;
}

export function SentenceBuilderView({ onSendSignal: _onSendSignal }: SentenceBuilderViewProps) {
  void _onSendSignal; // reserved for WebSocket signal forwarding
  const [state, setState] = useState<SentenceBuilderState>({
    templates: [],
    active_template: null,
    current_slot_idx: 0,
    built_sentence: '',
    phase: 'template_select',
  });
  const [highlightIdx, setHighlightIdx] = useState(0);
  const [scanPhase, setScanPhase] = useState<'row' | 'col' | 'confirm'>('row');
  const [confirmCountdown, setConfirmCountdown] = useState(0);
  const [scanSpeed] = useState(1.5);

  // Lade Templates vom Backend
  useEffect(() => {
    fetch('/api/sentence-builder/templates')
      .then(r => r.json())
      .then(data => {
        setState(prev => ({ ...prev, templates: data.templates || [] }));
      })
      .catch(() => {});
  }, []);

  // Scanning-Timer
  useEffect(() => {
    if (scanPhase === 'confirm') return;

    const items = getCurrentItems();
    if (items.length === 0) return;

    const interval = setInterval(() => {
      setHighlightIdx(prev => (prev + 1) % items.length);
    }, scanSpeed * 1000);

    return () => clearInterval(interval);
  }, [scanPhase, state.phase, state.current_slot_idx, scanSpeed]);

  // Confirm-Countdown
  useEffect(() => {
    if (scanPhase !== 'confirm') return;

    const timer = setInterval(() => {
      setConfirmCountdown(prev => {
        if (prev <= 0) {
          // Bestätigt!
          handleConfirm();
          return 0;
        }
        return prev - 100;
      });
    }, 100);

    return () => clearInterval(timer);
  }, [scanPhase, highlightIdx]);

  const getCurrentItems = useCallback((): { label: string; icon: string }[] => {
    if (state.phase === 'template_select') {
      return state.templates.map(t => ({ label: t.name, icon: '' }));
    }
    if (state.phase === 'slot_fill' && state.active_template) {
      const slot = state.active_template.slots[state.current_slot_idx];
      if (slot) {
        const items = slot.words.map(w => ({ label: w.display || w.text, icon: w.icon }));
        if (slot.optional) {
          items.push({ label: 'Überspringen', icon: '⏭' });
        }
        return items;
      }
    }
    if (state.phase === 'preview') {
      return [
        { label: 'Sprechen', icon: '🔊' },
        { label: 'Nochmal', icon: '🔄' },
        { label: 'Abbrechen', icon: '❌' },
      ];
    }
    return [];
  }, [state]);

  const handleSignal = useCallback(() => {
    if (scanPhase === 'confirm') {
      // Abbruch während Countdown
      setScanPhase('row');
      setConfirmCountdown(0);
      return;
    }

    // Auswahl treffen
    setScanPhase('confirm');
    setConfirmCountdown(2500);
  }, [scanPhase, highlightIdx]);

  const handleConfirm = useCallback(() => {
    setScanPhase('row');
    const items = getCurrentItems();
    const idx = highlightIdx % items.length;

    if (state.phase === 'template_select') {
      // Template auswählen
      fetch('/api/sentence-builder/select-template', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ index: idx }),
      })
        .then(r => r.json())
        .then(data => {
          setState(prev => ({
            ...prev,
            active_template: data.template,
            current_slot_idx: 0,
            phase: 'slot_fill',
          }));
          setHighlightIdx(0);
        });
    } else if (state.phase === 'slot_fill') {
      const slot = state.active_template?.slots[state.current_slot_idx];
      if (slot?.optional && idx === slot.words.length) {
        // Überspringen
        advanceSlot();
      } else {
        // Wort auswählen
        fetch('/api/sentence-builder/select-word', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ word_index: idx }),
        })
          .then(r => r.json())
          .then(data => {
            if (data.complete) {
              setState(prev => ({
                ...prev,
                built_sentence: data.sentence,
                phase: 'preview',
              }));
            } else {
              advanceSlot();
            }
            setHighlightIdx(0);
          });
      }
    } else if (state.phase === 'preview') {
      if (idx === 0) {
        // Sprechen
        fetch('/api/sentence-builder/speak', { method: 'POST' });
        resetBuilder();
      } else if (idx === 1) {
        // Nochmal (zurück zum ersten Slot)
        setState(prev => ({ ...prev, current_slot_idx: 0, phase: 'slot_fill' }));
        setHighlightIdx(0);
      } else {
        // Abbrechen
        resetBuilder();
      }
    }
  }, [state, highlightIdx]);

  const advanceSlot = () => {
    setState(prev => {
      const nextIdx = prev.current_slot_idx + 1;
      if (prev.active_template && nextIdx >= prev.active_template.slots.length) {
        // Alle Slots ausgefüllt
        fetch('/api/sentence-builder/build')
          .then(r => r.json())
          .then(data => {
            setState(p => ({ ...p, built_sentence: data.sentence, phase: 'preview' }));
          });
        return prev;
      }
      return { ...prev, current_slot_idx: nextIdx };
    });
    setHighlightIdx(0);
  };

  const resetBuilder = () => {
    fetch('/api/sentence-builder/reset', { method: 'POST' });
    setState(prev => ({
      ...prev,
      active_template: null,
      current_slot_idx: 0,
      built_sentence: '',
      phase: 'template_select',
    }));
    setHighlightIdx(0);
  };

  // Tastatur-Listener
  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if (e.code === 'Space' || e.key === ' ') {
        e.preventDefault();
        handleSignal();
      }
      if (e.key === 'Escape') {
        resetBuilder();
      }
    };
    window.addEventListener('keydown', handler);
    return () => window.removeEventListener('keydown', handler);
  }, [handleSignal]);

  const items = getCurrentItems();
  const currentSlot = state.active_template?.slots[state.current_slot_idx];

  // Fortschritts-Anzeige
  const progressParts = state.active_template?.slots.map((slot, i) => {
    if (slot.selected) return slot.selected.display || slot.selected.text;
    if (i === state.current_slot_idx) return `[${slot.label}?]`;
    return `(${slot.label})`;
  }) || [];

  return (
    <div className="flex flex-col h-full p-4">
      {/* Header mit Fortschritt */}
      <div className="mb-4">
        <div className="flex items-center justify-between mb-2">
          <h2 className="text-xl font-bold text-[var(--accent-highlight)]">
            {state.phase === 'template_select' && 'Satz-Builder: Kategorie wählen'}
            {state.phase === 'slot_fill' && currentSlot && `${currentSlot.label} wählen`}
            {state.phase === 'preview' && 'Satz fertig'}
          </h2>
          <button
            onClick={resetBuilder}
            className="px-3 py-1 bg-white/10 rounded text-sm hover:bg-white/20"
          >
            Zurück
          </button>
        </div>

        {/* Fortschritts-Balken */}
        {state.active_template && (
          <div className="flex gap-1 mb-2">
            {state.active_template.slots.map((_, i) => (
              <div
                key={i}
                className={`h-1 flex-1 rounded ${
                  i < state.current_slot_idx
                    ? 'bg-[var(--accent-selected)]'
                    : i === state.current_slot_idx
                    ? 'bg-[var(--accent-highlight)]'
                    : 'bg-white/20'
                }`}
              />
            ))}
          </div>
        )}

        {/* Satz-Vorschau */}
        {progressParts.length > 0 && (
          <div className="text-lg text-white/70 font-mono">
            {progressParts.join(' ')}
          </div>
        )}

        {/* Fertiger Satz */}
        {state.built_sentence && (
          <div className="mt-2 p-3 bg-[var(--accent-highlight)]/20 border border-[var(--accent-highlight)]/40 rounded-lg">
            <p className="text-2xl font-bold text-center">{state.built_sentence}</p>
          </div>
        )}
      </div>

      {/* Confirm-Countdown */}
      {scanPhase === 'confirm' && (
        <div className="mb-2">
          <div className="h-2 bg-white/10 rounded-full overflow-hidden">
            <div
              className="h-full bg-[var(--accent-confirm)] transition-all duration-100"
              style={{ width: `${(confirmCountdown / 2500) * 100}%` }}
            />
          </div>
          <p className="text-center text-sm text-[var(--accent-confirm)] mt-1">
            Signal zum Abbrechen — {(confirmCountdown / 1000).toFixed(1)}s
          </p>
        </div>
      )}

      {/* Scanning-Grid */}
      <div className="flex-1 grid gap-3" style={{ gridTemplateRows: `repeat(${Math.min(items.length, 6)}, 1fr)` }}>
        {items.map((item, idx) => {
          const isHighlighted = scanPhase !== 'confirm' && idx === highlightIdx % items.length;
          const isConfirming = scanPhase === 'confirm' && idx === highlightIdx % items.length;

          return (
            <div
              key={idx}
              className={`
                flex items-center justify-center rounded-xl
                transition-all duration-200 ease-out
                border-2 select-none
                ${isConfirming
                  ? 'bg-[var(--accent-confirm)] text-black border-[var(--accent-confirm)] animate-pulse-highlight'
                  : isHighlighted
                  ? 'bg-[var(--accent-highlight)] text-black border-[var(--accent-highlight)]'
                  : 'bg-[var(--bg-card)] text-white border-transparent'
                }
              `}
            >
              <span className="text-2xl font-bold text-center px-4">
                {item.icon && <span className="mr-2">{item.icon}</span>}
                {item.label}
              </span>
            </div>
          );
        })}
      </div>

      {/* Hinweis */}
      <div className="mt-4 text-center text-sm text-white/30">
        Leertaste = Signal | Escape = Zurück
      </div>
    </div>
  );
}
