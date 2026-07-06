import { useCallback, useEffect, useRef, useState } from 'react';
import type { EngineState, WSMessage } from '../types/protocol';

const INITIAL_STATE: EngineState = {
  mode: 'idle',
  phase: 'idle',
  current_row: 0,
  current_col: -1,
  confirm_progress: 0,
  text_buffer: '',
  predictions: [],
  layout: null,
  fatigue: { level: 'normal', session_min: 0, signals_total: 0, mean_latency_s: 0 },
};

export function useWebSocket() {
  const [state, setState] = useState<EngineState>(INITIAL_STATE);
  const [connected, setConnected] = useState(false);
  const wsRef = useRef<WebSocket | null>(null);
  const reconnectTimer = useRef<number | null>(null);

  const connect = useCallback(() => {
    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    const wsUrl = `${protocol}//${window.location.host}/ws`;

    const ws = new WebSocket(wsUrl);
    wsRef.current = ws;

    ws.onopen = () => {
      setConnected(true);
      console.log('[WS] Verbunden');
    };

    ws.onmessage = (event) => {
      try {
        const msg: WSMessage = JSON.parse(event.data);
        if (msg.type === 'state') {
          setState(msg.data as EngineState);
        }
      } catch (e) {
        console.error('[WS] Parse-Fehler:', e);
      }
    };

    ws.onclose = () => {
      setConnected(false);
      console.log('[WS] Getrennt — Reconnect in 2s');
      reconnectTimer.current = window.setTimeout(connect, 2000);
    };

    ws.onerror = () => {
      ws.close();
    };
  }, []);

  useEffect(() => {
    connect();
    return () => {
      if (reconnectTimer.current) clearTimeout(reconnectTimer.current);
      wsRef.current?.close();
    };
  }, [connect]);

  const sendSignal = useCallback(() => {
    wsRef.current?.send(JSON.stringify({ type: 'signal' }));
  }, []);

  const switchMode = useCallback((mode: string) => {
    wsRef.current?.send(JSON.stringify({ type: 'mode', data: mode }));
  }, []);

  const updateConfig = useCallback((config: Record<string, any>) => {
    wsRef.current?.send(JSON.stringify({ type: 'config', data: config }));
  }, []);

  return { state, connected, sendSignal, switchMode, updateConfig };
}
