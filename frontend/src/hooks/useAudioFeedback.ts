/**
 * Akustisches Feedback für Scanning-Events.
 *
 * Verwendet Web Audio API für latenzfreie Klick-Töne:
 * - tick: Leiser Klick bei jedem Scan-Schritt (Highlight wechselt)
 * - select: Höherer Ton bei Auswahl
 * - confirm: Aufsteigender Doppelton bei Bestätigung
 * - cancel: Absteigender Ton bei Abbruch
 * - alarm: Wiederholter hoher Ton bei Notruf
 */

import { useCallback, useEffect, useRef } from 'react';

type SoundType = 'tick' | 'select' | 'confirm' | 'cancel' | 'alarm';

export function useAudioFeedback(enabled: boolean = true) {
  const ctxRef = useRef<AudioContext | null>(null);

  useEffect(() => {
    // AudioContext erst bei User-Interaktion erstellen (Browser-Policy)
    const initAudio = () => {
      if (!ctxRef.current) {
        ctxRef.current = new AudioContext();
      }
    };
    window.addEventListener('click', initAudio, { once: true });
    window.addEventListener('keydown', initAudio, { once: true });
    return () => {
      window.removeEventListener('click', initAudio);
      window.removeEventListener('keydown', initAudio);
    };
  }, []);

  const playTone = useCallback(
    (frequency: number, duration: number, volume: number = 0.3, type: OscillatorType = 'sine') => {
      if (!enabled || !ctxRef.current) return;
      const ctx = ctxRef.current;
      if (ctx.state === 'suspended') ctx.resume();

      const osc = ctx.createOscillator();
      const gain = ctx.createGain();

      osc.type = type;
      osc.frequency.value = frequency;
      gain.gain.value = volume;
      gain.gain.exponentialRampToValueAtTime(0.001, ctx.currentTime + duration);

      osc.connect(gain);
      gain.connect(ctx.destination);
      osc.start();
      osc.stop(ctx.currentTime + duration);
    },
    [enabled]
  );

  const play = useCallback(
    (sound: SoundType) => {
      if (!enabled) return;

      switch (sound) {
        case 'tick':
          // Leiser, kurzer Klick
          playTone(800, 0.05, 0.1, 'square');
          break;

        case 'select':
          // Mittlerer Ton bei Auswahl
          playTone(1200, 0.1, 0.25, 'sine');
          break;

        case 'confirm':
          // Aufsteigender Doppelton
          playTone(600, 0.1, 0.3, 'sine');
          setTimeout(() => playTone(900, 0.15, 0.3, 'sine'), 120);
          break;

        case 'cancel':
          // Absteigender Ton
          playTone(500, 0.1, 0.2, 'sawtooth');
          setTimeout(() => playTone(300, 0.15, 0.2, 'sawtooth'), 100);
          break;

        case 'alarm':
          // Wiederholter hoher Ton
          for (let i = 0; i < 5; i++) {
            setTimeout(() => playTone(1500, 0.1, 0.4, 'square'), i * 200);
          }
          break;
      }
    },
    [enabled, playTone]
  );

  return { play };
}
