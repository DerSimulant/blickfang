"""Session-Logging und Replay (/LF730/, /LF800/).

Log-Format = Replay-Format (ab Tag 1): Der Feature-Stream jeder Sitzung
kann deterministisch wiederabgespielt werden.

Format: JSONL (append-only), eine Zeile pro ChannelFrame oder Event.
Logging ist opt-in (Datenschutz, /LN31/).
"""

from __future__ import annotations

import json
import logging
import time
from datetime import datetime
from pathlib import Path
from typing import Generator, List, Optional

from blickfang.core.config import LoggingConfig
from blickfang.core.events import (
    ChannelFrame,
    DetectorState,
    EventType,
    QualityState,
    SwitchEvent,
)

logger = logging.getLogger(__name__)


class SessionLogger:
    """Append-only Session-Logger (/LF730/).

    Zeichnet ChannelFrames und SwitchEvents im JSONL-Format auf.
    Opt-in gemäß /LN31/ (Datenschutz).
    """

    def __init__(self, config: LoggingConfig):
        self._config = config
        self._file = None
        self._filepath: Optional[Path] = None
        self._frame_count = 0
        self._event_count = 0

    @property
    def is_active(self) -> bool:
        return self._file is not None

    @property
    def filepath(self) -> Optional[Path]:
        return self._filepath

    def start(self) -> Optional[Path]:
        """Startet eine neue Logging-Session.

        Returns:
            Pfad zur Log-Datei oder None wenn Logging deaktiviert.
        """
        if not self._config.enabled:
            logger.info("Session-Logging deaktiviert (opt-in, /LN31/)")
            return None

        output_dir = Path(self._config.output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        self._filepath = output_dir / f"session_{timestamp}.jsonl"

        self._file = open(self._filepath, "a", encoding="utf-8")

        # Header-Zeile
        header = {
            "type": "session_start",
            "timestamp": time.perf_counter(),
            "datetime": datetime.now().isoformat(),
            "version": "1.0",
        }
        self._write_line(header)

        logger.info(f"Session-Logging gestartet: {self._filepath}")
        return self._filepath

    def stop(self) -> None:
        """Beendet die Logging-Session."""
        if self._file is not None:
            footer = {
                "type": "session_end",
                "timestamp": time.perf_counter(),
                "frames_logged": self._frame_count,
                "events_logged": self._event_count,
            }
            self._write_line(footer)
            self._file.close()
            self._file = None
            logger.info(
                f"Session-Logging beendet: {self._frame_count} Frames, "
                f"{self._event_count} Events"
            )

    def log_frame(self, frame: ChannelFrame) -> None:
        """Loggt einen ChannelFrame."""
        if self._file is None:
            return

        data = {
            "type": "channel_frame",
            "timestamp": frame.timestamp,
            "channels": frame.channels,
            "quality": frame.quality.name,
            "fps": frame.raw_fps,
        }
        self._write_line(data)
        self._frame_count += 1

    def log_event(self, event: SwitchEvent) -> None:
        """Loggt ein SwitchEvent."""
        if self._file is None:
            return

        data = {
            "type": "switch_event",
            "source_id": event.source_id,
            "event_type": event.event_type.name,
            "timestamp_capture": event.timestamp_capture,
            "confidence": event.confidence,
            "channel_name": event.channel_name,
        }
        self._write_line(data)
        self._event_count += 1

    def log_state_change(
        self, old_state: DetectorState, new_state: DetectorState, timestamp: float
    ) -> None:
        """Loggt einen Zustandswechsel des Detektors."""
        if self._file is None:
            return

        data = {
            "type": "state_change",
            "timestamp": timestamp,
            "old_state": old_state.name,
            "new_state": new_state.name,
        }
        self._write_line(data)

    def log_veto(self, veto_type: str, timestamp: float, duration_s: float) -> None:
        """Loggt ein Veto-Ereignis."""
        if self._file is None:
            return

        data = {
            "type": "veto",
            "veto_type": veto_type,
            "timestamp": timestamp,
            "duration_s": duration_s,
        }
        self._write_line(data)

    def _write_line(self, data: dict) -> None:
        """Schreibt eine JSON-Zeile in die Log-Datei."""
        if self._file is not None:
            self._file.write(json.dumps(data, ensure_ascii=False) + "\n")
            self._file.flush()


class SessionReplay:
    """Replay von aufgezeichneten Sessions (/LF800/).

    Spielt Feature-Streams deterministisch ab — für Offline-Tests
    und Detektor-Entwicklung ohne echte Nutzer:innen.
    """

    def __init__(self, filepath: Path):
        """
        Args:
            filepath: Pfad zur JSONL-Session-Datei.
        """
        self._filepath = filepath
        self._lines: List[dict] = []
        self._load()

    def _load(self) -> None:
        """Lädt die Session-Datei."""
        with open(self._filepath, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    try:
                        self._lines.append(json.loads(line))
                    except json.JSONDecodeError:
                        continue

    @property
    def frame_count(self) -> int:
        """Anzahl der ChannelFrames in der Session."""
        return sum(1 for l in self._lines if l.get("type") == "channel_frame")

    @property
    def duration_s(self) -> float:
        """Dauer der Session in Sekunden."""
        frames = [l for l in self._lines if l.get("type") == "channel_frame"]
        if len(frames) < 2:
            return 0.0
        return frames[-1]["timestamp"] - frames[0]["timestamp"]

    def iter_frames(self) -> Generator[ChannelFrame, None, None]:
        """Iteriert über alle ChannelFrames der Session.

        Yields:
            ChannelFrame-Objekte in chronologischer Reihenfolge.
        """
        for line in self._lines:
            if line.get("type") == "channel_frame":
                quality = QualityState[line.get("quality", "OK")]
                yield ChannelFrame(
                    timestamp=line["timestamp"],
                    channels=line["channels"],
                    quality=quality,
                    raw_fps=line.get("fps", 0.0),
                )

    def iter_events(self) -> Generator[SwitchEvent, None, None]:
        """Iteriert über alle SwitchEvents der Session.

        Yields:
            SwitchEvent-Objekte in chronologischer Reihenfolge.
        """
        for line in self._lines:
            if line.get("type") == "switch_event":
                yield SwitchEvent(
                    source_id=line["source_id"],
                    event_type=EventType[line["event_type"]],
                    timestamp_capture=line["timestamp_capture"],
                    confidence=line.get("confidence", 1.0),
                    channel_name=line.get("channel_name"),
                )

    def get_fp_per_min(self) -> float:
        """Berechnet Fehlaktivierungen pro Minute aus der Session."""
        events = list(self.iter_events())
        if not events:
            return 0.0
        duration_min = self.duration_s / 60.0
        if duration_min < 0.1:
            return 0.0
        return len(events) / duration_min
