import { useCallback, useEffect } from 'react';
import { useWebSocket } from './hooks/useWebSocket';
import { ModeBar } from './components/ModeBar';
import { ScanGrid } from './components/ScanGrid';
import { TextDisplay } from './components/TextDisplay';
import { StatusFooter } from './components/StatusFooter';
import { StartScreen } from './components/StartScreen';

function App() {
  const { state, connected, sendSignal, switchMode } = useWebSocket();

  // Tastatur-Handler: Leertaste/Enter = Signal
  const handleKeyDown = useCallback(
    (e: KeyboardEvent) => {
      if (e.code === 'Space' || e.code === 'Enter') {
        e.preventDefault();
        sendSignal();
      }
      // F11 für Vollbild
      if (e.code === 'F11') {
        e.preventDefault();
        if (document.fullscreenElement) {
          document.exitFullscreen();
        } else {
          document.documentElement.requestFullscreen();
        }
      }
    },
    [sendSignal]
  );

  useEffect(() => {
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [handleKeyDown]);

  const isIdle = state.mode === 'idle';
  const showTextDisplay = state.mode === 'keyboard';

  return (
    <div className="flex flex-col h-screen w-screen overflow-hidden">
      {/* Modus-Leiste (oben) — immer sichtbar wenn verbunden */}
      {connected && !isIdle && (
        <ModeBar
          mode={state.mode}
          fatigue={state.fatigue}
          connected={connected}
          onSwitchMode={switchMode}
        />
      )}

      {/* Hauptinhalt */}
      {connected && isIdle && (
        <StartScreen onStart={switchMode} />
      )}

      {connected && !isIdle && (
        <>
          {/* Text-Anzeige (nur im Keyboard-Modus) */}
          {showTextDisplay && (
            <TextDisplay text={state.text_buffer} predictions={state.predictions} />
          )}

          {/* Scanning-Grid (Hauptbereich) */}
          <div className="flex-1 min-h-0">
            <ScanGrid state={state} />
          </div>

          {/* Status-Leiste (unten) */}
          <StatusFooter phase={state.phase} confirmProgress={state.confirm_progress} />
        </>
      )}

      {/* Nicht verbunden — Overlay */}
      {!connected && (
        <div className="fixed inset-0 bg-black/80 flex items-center justify-center z-50">
          <div className="text-center animate-fade-in">
            <div className="text-6xl mb-4">🔌</div>
            <h2 className="text-2xl font-bold mb-2">Verbindung zum Server wird hergestellt...</h2>
            <p className="text-[var(--text-secondary)]">
              Stelle sicher, dass der blickfang-Server läuft.
            </p>
            <p className="text-sm text-white/30 mt-4">
              Starte mit: <code className="bg-white/10 px-2 py-1 rounded">blickfang-server</code>
            </p>
          </div>
        </div>
      )}
    </div>
  );
}

export default App;
