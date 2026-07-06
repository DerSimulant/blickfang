"""Bridge: Verbindet Scanning-Engine mit WebSocket-Server.

Läuft in einem eigenen Thread und sendet State-Updates an alle
verbundenen WebSocket-Clients.
"""

from __future__ import annotations

import asyncio
import json
import logging
import threading
import time
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

_bridge_instance: Optional["EngineBridge"] = None


def get_bridge() -> Optional["EngineBridge"]:
    """Gibt die aktive Bridge-Instanz zurück."""
    return _bridge_instance


def create_bridge(**kwargs) -> "EngineBridge":
    """Erstellt eine neue Bridge-Instanz."""
    global _bridge_instance
    _bridge_instance = EngineBridge(**kwargs)
    return _bridge_instance


class EngineBridge:
    """Verbindet die Scanning-Engine mit dem WebSocket-Server.

    Übersetzt Engine-Events in JSON-Nachrichten für das Frontend.
    """

    def __init__(
        self,
        scan_speed_s: float = 1.5,
        cancel_countdown_s: float = 2.5,
        tts_enabled: bool = True,
    ):
        self._scan_speed_s = scan_speed_s
        self._cancel_countdown_s = cancel_countdown_s
        self._tts_enabled = tts_enabled

        self._running = False
        self._mode = "idle"
        self._person = ""
        self._key_only = True
        self._camera_active = False
        self._start_time = 0.0

        self._controller = None
        self._tick_thread: Optional[threading.Thread] = None
        self._camera_thread: Optional[threading.Thread] = None
        self._loop: Optional[asyncio.AbstractEventLoop] = None

    @property
    def running(self) -> bool:
        return self._running

    @property
    def mode(self) -> str:
        return self._mode

    @property
    def camera_active(self) -> bool:
        return self._camera_active

    @property
    def person(self) -> str:
        return self._person

    @property
    def scan_speed_s(self) -> float:
        return self._scan_speed_s

    @property
    def uptime_s(self) -> float:
        if self._start_time:
            return time.perf_counter() - self._start_time
        return 0.0

    def start(self, person: str = "", key_only: bool = True) -> None:
        """Startet die Kommunikation."""
        if self._running:
            self.stop()

        self._person = person
        self._key_only = key_only
        self._start_time = time.perf_counter()

        # TTS initialisieren
        tts_speak = self._init_tts() if self._tts_enabled else self._print_speak

        # Controller erstellen
        from blickfang.scanning.controller import CommMode, CommunicationController
        from blickfang.scanning.alarm import play_alarm_sound

        self._controller = CommunicationController(
            on_speak=tts_speak,
            on_mode_change=self._on_mode_change,
            on_alarm=play_alarm_sound,
            scan_speed_s=self._scan_speed_s,
            cancel_countdown_s=self._cancel_countdown_s,
        )

        # Engine-Callbacks für UI-Updates
        self._controller.engine.on("highlight", self._on_highlight)
        self._controller.engine.on("select", self._on_select)
        self._controller.engine.on("confirm", self._on_confirm)
        self._controller.engine.on("cancel", self._on_cancel)
        self._controller.engine.on("no_answer", self._on_no_answer)

        self._running = True
        self._controller.start(CommMode.MAIN_MENU)

        # Tick-Thread starten
        self._tick_thread = threading.Thread(target=self._tick_loop, daemon=True)
        self._tick_thread.start()

        # Kamera-Thread (wenn nicht key-only)
        if not key_only and person:
            self._camera_thread = threading.Thread(
                target=self._camera_loop, daemon=True
            )
            self._camera_thread.start()

        logger.info(f"Bridge gestartet (Person: {person or 'keine'}, Key-Only: {key_only})")
        self._broadcast_state()

    def stop(self) -> None:
        """Stoppt die Kommunikation."""
        self._running = False
        if self._controller:
            self._controller.stop()
        self._mode = "idle"
        self._broadcast_event("stopped", {})
        logger.info("Bridge gestoppt")

    def signal(self) -> None:
        """Verarbeitet ein Switch-Signal."""
        if self._controller and self._running:
            self._controller.signal()

    def switch_mode(self, mode: str) -> None:
        """Wechselt den Kommunikations-Modus."""
        if not self._controller:
            return

        from blickfang.scanning.controller import CommMode

        mode_map = {
            "main_menu": CommMode.MAIN_MENU,
            "phrases": CommMode.PHRASES,
            "keyboard": CommMode.KEYBOARD,
            "yesno": CommMode.YESNO,
        }

        if mode in mode_map:
            self._controller.start(mode_map[mode])

    def update_config(self, config: Dict[str, Any]) -> None:
        """Aktualisiert die Laufzeit-Konfiguration."""
        if "scan_speed_s" in config:
            self._scan_speed_s = config["scan_speed_s"]
            if self._controller:
                self._controller.engine.layout.scan_speed_s = self._scan_speed_s

        if "cancel_countdown_s" in config:
            self._cancel_countdown_s = config["cancel_countdown_s"]
            if self._controller:
                self._controller.engine.layout.cancel_countdown_s = self._cancel_countdown_s

        self._broadcast_event("config_updated", config)

    # ─── Private Methoden ──────────────────────────────────────────────

    def _tick_loop(self) -> None:
        """Tick-Loop in eigenem Thread."""
        while self._running:
            if self._controller:
                self._controller.tick()
                self._broadcast_state()
            time.sleep(0.05)  # 20 Hz Update-Rate

    def _camera_loop(self) -> None:
        """Kamera-Erkennungs-Loop."""
        try:
            from blickfang.calibration.profile import load_latest_profile
            from blickfang.capture.camera import CameraSource
            from blickfang.features.face_mesh import FaceMeshExtractor
            from blickfang.features.channels import ChannelComputer
            from blickfang.detection.baseline import GatedBaseline
            from blickfang.detection.detector import SchmittDetector

            profile = load_latest_profile(self._person)
            if not profile:
                logger.warning(f"Kein Profil für '{self._person}'")
                return

            camera = CameraSource()
            extractor = FaceMeshExtractor()
            channels = ChannelComputer()

            detector = SchmittDetector(
                channel=profile.get("channel", "eyeBlinkLeft"),
                threshold_delta=profile.get("threshold_delta", 0.15),
                hysteresis=profile.get("hysteresis", 0.5),
                hold_time_s=profile.get("hold_time_s", 0.12),
                refractory_s=profile.get("refractory_s", 0.8),
            )

            baseline = GatedBaseline(
                fast_alpha=profile.get("fast_alpha", 0.02),
                slow_alpha=profile.get("slow_alpha", 0.002),
                mad_floor=profile.get("mad_floor", 0.01),
            )

            camera.start()
            self._camera_active = True
            logger.info("Kamera-Erkennung aktiv")

            while self._running:
                frame = camera.get_frame()
                if frame is None:
                    time.sleep(0.01)
                    continue

                result = extractor.process(frame)
                if result is None:
                    continue

                channel_values = channels.compute(result)
                channel_name = profile.get("channel", "eyeBlinkLeft")
                value = channel_values.get(channel_name, 0.0)

                baseline.update(value)
                event = detector.update(value, baseline.median, baseline.mad)
                if event:
                    self.signal()

                time.sleep(0.01)

        except Exception as e:
            logger.error(f"Kamera-Fehler: {e}")
        finally:
            self._camera_active = False
            try:
                camera.stop()
            except:
                pass

    def _on_mode_change(self, mode) -> None:
        """Callback: Modus gewechselt."""
        self._mode = mode.name.lower()
        self._broadcast_event("mode_change", {
            "mode": self._mode,
            "layout": self._serialize_layout(),
        })

    def _on_highlight(self, row: int, col: int, phase) -> None:
        """Callback: Item hervorgehoben."""
        self._broadcast_event("highlight", {
            "row": row,
            "col": col,
            "phase": phase.name.lower(),
        })

    def _on_select(self, item) -> None:
        """Callback: Item ausgewählt."""
        self._broadcast_event("select", {
            "label": item.label if item else "",
            "value": item.value if item else "",
            "speak": item.speak if item else "",
            "action": item.action if item else "",
        })

    def _on_confirm(self, item) -> None:
        """Callback: Bestätigung läuft."""
        self._broadcast_event("confirm", {
            "label": item.label if item else "",
            "speak": item.speak if item else "",
        })

    def _on_cancel(self) -> None:
        """Callback: Auswahl abgebrochen."""
        self._broadcast_event("cancel", {})

    def _on_no_answer(self) -> None:
        """Callback: Timeout."""
        self._broadcast_event("no_answer", {})

    def _broadcast_state(self) -> None:
        """Sendet den vollständigen Zustand an alle Clients."""
        if not self._controller:
            return

        state = self._controller.engine.state
        from blickfang.scanning.engine import ScanPhase

        data = {
            "mode": self._mode,
            "phase": state.phase.name.lower() if state.phase else "idle",
            "current_row": state.current_row,
            "current_col": state.current_col,
            "confirm_progress": self._controller.engine.confirm_progress,
            "text_buffer": self._controller.text_buffer.text,
            "predictions": self._controller.get_predictions(),
            "layout": self._serialize_layout(),
            "fatigue": self._serialize_fatigue(),
        }

        self._broadcast_event("state", data)

    def _broadcast_event(self, event_type: str, data: Dict[str, Any]) -> None:
        """Sendet ein Event an alle WebSocket-Clients (thread-safe)."""
        from blickfang.server.api import _connections

        if not _connections:
            return

        message = json.dumps({"type": event_type, "data": data, "ts": time.time()})

        # Thread-safe broadcast
        for ws in list(_connections):
            try:
                asyncio.run_coroutine_threadsafe(
                    ws.send_text(message),
                    self._get_loop(),
                )
            except Exception:
                pass

    def _get_loop(self) -> asyncio.AbstractEventLoop:
        """Holt den asyncio Event-Loop."""
        if self._loop is None:
            try:
                self._loop = asyncio.get_event_loop()
            except RuntimeError:
                self._loop = asyncio.new_event_loop()
        return self._loop

    def set_loop(self, loop: asyncio.AbstractEventLoop) -> None:
        """Setzt den Event-Loop (wird vom Server gesetzt)."""
        self._loop = loop

    def _serialize_layout(self) -> Optional[Dict]:
        """Serialisiert das aktuelle Layout für das Frontend."""
        if not self._controller:
            return None

        layout = self._controller.current_layout
        return {
            "name": layout.name,
            "scan_speed_s": layout.scan_speed_s,
            "rows": [
                {
                    "label": row.label,
                    "items": [
                        {
                            "label": item.label,
                            "value": item.value,
                            "speak": item.speak,
                            "action": item.action,
                            "icon": item.icon,
                        }
                        for item in row.items
                    ],
                }
                for row in layout.rows
            ],
        }

    def _serialize_fatigue(self) -> Dict:
        """Serialisiert Ermüdungs-Metriken."""
        if not self._controller:
            return {"level": "normal", "session_min": 0}

        metrics = self._controller.fatigue.get_metrics()
        return {
            "level": metrics.fatigue_level,
            "session_min": int(metrics.session_duration_s / 60),
            "signals_total": metrics.signals_total,
            "mean_latency_s": round(metrics.mean_latency_s, 2),
        }

    def _init_tts(self):
        """Initialisiert TTS."""
        try:
            from blickfang.output.tts import TTSEngine
            engine = TTSEngine()
            return engine.speak
        except Exception as e:
            logger.warning(f"TTS nicht verfügbar: {e}")
            return self._print_speak

    @staticmethod
    def _print_speak(text: str) -> None:
        """Fallback: Text ausgeben."""
        print(f"  🔊 {text}")
