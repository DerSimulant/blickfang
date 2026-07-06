/** WebSocket-Protokoll-Typen zwischen Backend und Frontend. */

export type ScanPhase =
  | 'idle'
  | 'row_scan'
  | 'col_scan'
  | 'confirm'
  | 'selected'
  | 'cancelled'
  | 'no_answer';

export type CommMode =
  | 'idle'
  | 'main_menu'
  | 'phrases'
  | 'keyboard'
  | 'yesno';

export interface ScanItem {
  label: string;
  value: string;
  speak: string;
  action: string;
  icon: string;
}

export interface ScanRow {
  label: string;
  items: ScanItem[];
}

export interface ScanLayout {
  name: string;
  scan_speed_s: number;
  rows: ScanRow[];
}

export interface FatigueMetrics {
  level: 'normal' | 'mild' | 'moderate' | 'high';
  session_min: number;
  signals_total: number;
  mean_latency_s: number;
}

export interface EngineState {
  mode: CommMode;
  phase: ScanPhase;
  current_row: number;
  current_col: number;
  confirm_progress: number;
  text_buffer: string;
  predictions: string[];
  layout: ScanLayout | null;
  fatigue: FatigueMetrics;
}

export interface WSMessage {
  type: string;
  data: any;
  ts: number;
}

export interface StatusResponse {
  running: boolean;
  mode: string;
  camera_active: boolean;
  person: string;
  scan_speed_s: number;
  uptime_s: number;
}
