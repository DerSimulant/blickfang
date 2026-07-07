import { useEffect, useState } from 'react';

interface ErrorInfo {
  type: 'camera' | 'face' | 'connection' | 'tts' | 'general';
  message: string;
  hint: string;
  severity: 'warning' | 'error';
  timestamp: number;
}

interface ErrorOverlayProps {
  connected: boolean;
  cameraActive: boolean;
  faceDetected: boolean;
}

const ERROR_CONFIGS: Record<string, Omit<ErrorInfo, 'timestamp'>> = {
  no_camera: {
    type: 'camera',
    message: 'Keine Kamera gefunden',
    hint: 'Bitte Kamera anschließen und Seite neu laden.',
    severity: 'error',
  },
  no_face: {
    type: 'face',
    message: 'Kein Gesicht erkannt',
    hint: 'Bitte Position anpassen — Gesicht muss sichtbar sein.',
    severity: 'warning',
  },
  connection_lost: {
    type: 'connection',
    message: 'Verbindung zum Server verloren',
    hint: 'Prüfe ob der blickfang-Server noch läuft.',
    severity: 'error',
  },
};

export function ErrorOverlay({ connected, cameraActive, faceDetected }: ErrorOverlayProps) {
  const [errors, setErrors] = useState<ErrorInfo[]>([]);
  const [dismissed, setDismissed] = useState<Set<string>>(new Set());

  useEffect(() => {
    const newErrors: ErrorInfo[] = [];

    if (!connected) {
      newErrors.push({ ...ERROR_CONFIGS.connection_lost, timestamp: Date.now() });
    }

    // Nur Kamera/Gesicht-Fehler zeigen wenn Kamera-Modus aktiv
    if (cameraActive && !faceDetected) {
      newErrors.push({ ...ERROR_CONFIGS.no_face, timestamp: Date.now() });
    }

    setErrors(newErrors.filter((e) => !dismissed.has(e.type)));
  }, [connected, cameraActive, faceDetected, dismissed]);

  const dismiss = (type: string) => {
    setDismissed((d) => new Set([...d, type]));
  };

  if (errors.length === 0) return null;

  return (
    <div className="fixed top-16 right-4 z-40 space-y-2 max-w-sm">
      {errors.map((error) => (
        <div
          key={error.type}
          className={`flex items-start gap-3 p-3 rounded-lg border animate-fade-in ${
            error.severity === 'error'
              ? 'bg-red-900/80 border-red-500/50'
              : 'bg-yellow-900/80 border-yellow-500/50'
          }`}
        >
          <span className="text-xl flex-shrink-0">
            {error.severity === 'error' ? '🔴' : '🟡'}
          </span>
          <div className="flex-1 min-w-0">
            <p className="font-medium text-sm">{error.message}</p>
            <p className="text-xs text-white/60 mt-0.5">{error.hint}</p>
          </div>
          <button
            onClick={() => dismiss(error.type)}
            className="text-white/40 hover:text-white text-xs flex-shrink-0"
          >
            ✕
          </button>
        </div>
      ))}
    </div>
  );
}
