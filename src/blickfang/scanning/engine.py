"""Scanning-Engine: Zeilen-Spalten-Scanning und hierarchisches Scanning.

Referenz: /LF640/ — Zeilen-Spalten-Scanning mit konfigurierbarem Layout.

Das Scanning funktioniert so:
1. Zeilen werden nacheinander hervorgehoben (Zeilen-Scan)
2. Bei Signal: gewählte Zeile wird fixiert
3. Spalten der Zeile werden nacheinander hervorgehoben (Spalten-Scan)
4. Bei Signal: Buchstabe/Item wird ausgewählt
5. Cancel-Countdown vor Bestätigung

Hierarchisches Scanning:
- Gruppen → Items innerhalb der Gruppe
- Kategorien → Phrasen innerhalb der Kategorie
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Any, Callable, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)


class ScanPhase(Enum):
    """Phasen des Scanning-Prozesses."""
    IDLE = auto()
    ROW_SCAN = auto()       # Zeilen werden gescannt
    COL_SCAN = auto()       # Spalten der gewählten Zeile werden gescannt
    GROUP_SCAN = auto()     # Gruppen werden gescannt (hierarchisch)
    ITEM_SCAN = auto()      # Items in gewählter Gruppe
    CONFIRM = auto()        # Cancel-Countdown läuft
    SELECTED = auto()       # Item wurde bestätigt
    NO_ANSWER = auto()      # Timeout ohne Auswahl


class ScanDirection(Enum):
    """Scan-Richtung."""
    FORWARD = auto()
    BACKWARD = auto()


@dataclass
class ScanItem:
    """Ein scanbares Element."""
    label: str                          # Anzeige-Text
    value: str = ""                     # Ausgabe-Wert (kann vom Label abweichen)
    speak: str = ""                     # TTS-Text (falls anders als label)
    action: str = ""                    # Sonderaktion: "backspace", "speak", "clear", "space", "home"
    icon: str = ""                      # Optional: Icon/Emoji für UI
    group: str = ""                     # Gruppenzugehörigkeit

    def __post_init__(self):
        if not self.value:
            self.value = self.label
        if not self.speak:
            self.speak = self.label


@dataclass
class ScanRow:
    """Eine Zeile im Scanning-Raster."""
    items: List[ScanItem] = field(default_factory=list)
    label: str = ""                     # Zeilen-Label (für Gruppen-Scan)

    @property
    def size(self) -> int:
        return len(self.items)


@dataclass
class ScanLayout:
    """Ein vollständiges Scanning-Layout (Raster aus Zeilen)."""
    name: str = ""
    rows: List[ScanRow] = field(default_factory=list)
    scan_speed_s: float = 1.5           # Sekunden pro Schritt
    max_cycles: int = 3                 # Max. Durchläufe bevor NO_ANSWER
    cancel_countdown_s: float = 2.5     # Cancel-Countdown in Sekunden
    speak_on_highlight: bool = True     # Aktuelles Item vorlesen beim Scannen

    @property
    def row_count(self) -> int:
        return len(self.rows)

    @property
    def total_items(self) -> int:
        return sum(row.size for row in self.rows)

    def get_item(self, row: int, col: int) -> Optional[ScanItem]:
        """Gibt Item an Position zurück."""
        if 0 <= row < len(self.rows) and 0 <= col < self.rows[row].size:
            return self.rows[row].items[col]
        return None


@dataclass
class ScanState:
    """Aktueller Zustand der Scanning-Engine."""
    phase: ScanPhase = ScanPhase.IDLE
    current_row: int = 0
    current_col: int = 0
    cycle_count: int = 0                # Wie oft wurde komplett durchgescannt
    confirm_start_time: float = 0.0     # Wann Cancel-Countdown begann
    selected_item: Optional[ScanItem] = None
    last_advance_time: float = 0.0      # Wann zuletzt weitergerückt


class ScanningEngine:
    """Zeilen-Spalten-Scanning-Engine.

    Verarbeitet Switch-Events und steuert die Scan-Position.
    Die UI fragt den aktuellen Zustand ab und rendert entsprechend.
    """

    def __init__(self, layout: ScanLayout):
        self._layout = layout
        self._state = ScanState()
        self._callbacks: Dict[str, List[Callable]] = {
            "highlight": [],    # (row, col, phase) — UI soll hervorheben
            "select": [],       # (item) — Item wurde ausgewählt
            "confirm": [],      # (item) — Bestätigung läuft
            "cancel": [],       # () — Auswahl abgebrochen
            "no_answer": [],    # () — Timeout
            "speak": [],        # (text) — TTS-Anforderung
        }

    @property
    def state(self) -> ScanState:
        return self._state

    @property
    def layout(self) -> ScanLayout:
        return self._layout

    @layout.setter
    def layout(self, new_layout: ScanLayout) -> None:
        """Layout wechseln (z.B. von Kategorien zu Buchstaben)."""
        self._layout = new_layout
        self.reset()

    def on(self, event: str, callback: Callable) -> None:
        """Registriert einen Callback."""
        if event in self._callbacks:
            self._callbacks[event].append(callback)

    def _emit(self, event: str, *args) -> None:
        """Löst Callbacks aus."""
        for cb in self._callbacks.get(event, []):
            try:
                cb(*args)
            except Exception as e:
                logger.error(f"Callback-Fehler ({event}): {e}")

    def start(self) -> None:
        """Startet den Scan-Vorgang."""
        if self._layout.row_count == 0:
            logger.warning("Leeres Layout — kann nicht scannen")
            return

        self._state = ScanState()
        self._state.phase = ScanPhase.ROW_SCAN
        self._state.current_row = 0
        self._state.current_col = 0
        self._state.last_advance_time = time.perf_counter()

        self._emit("highlight", 0, -1, ScanPhase.ROW_SCAN)
        logger.info("Scanning gestartet (Zeilen-Scan)")

    def reset(self) -> None:
        """Setzt den Scanner zurück."""
        self._state = ScanState()

    def stop(self) -> None:
        """Stoppt den Scanner."""
        self._state.phase = ScanPhase.IDLE

    def tick(self) -> None:
        """Zeitbasierter Tick — rückt den Scanner weiter.

        Muss regelmäßig aufgerufen werden (z.B. alle 50ms).
        """
        now = time.perf_counter()

        if self._state.phase == ScanPhase.IDLE:
            return

        if self._state.phase == ScanPhase.CONFIRM:
            # Cancel-Countdown prüfen
            elapsed = now - self._state.confirm_start_time
            if elapsed >= self._layout.cancel_countdown_s:
                # Bestätigt!
                item = self._state.selected_item
                self._state.phase = ScanPhase.SELECTED
                self._emit("select", item)
                if item:
                    self._emit("speak", item.speak)
                return
            return

        if self._state.phase in (ScanPhase.SELECTED, ScanPhase.NO_ANSWER):
            return

        # Auto-Advance basierend auf Scan-Geschwindigkeit
        elapsed = now - self._state.last_advance_time
        if elapsed >= self._layout.scan_speed_s:
            self._advance()
            self._state.last_advance_time = now

    def signal(self) -> None:
        """Verarbeitet ein Switch-Signal (Auswahl/Bestätigung).

        Wird aufgerufen wenn die Person ihr Signal gibt.
        """
        if self._state.phase == ScanPhase.IDLE:
            return

        if self._state.phase == ScanPhase.CONFIRM:
            # Signal während Countdown = CANCEL
            self._state.phase = ScanPhase.ROW_SCAN
            self._state.selected_item = None
            self._state.current_row = 0
            self._state.current_col = 0
            self._state.last_advance_time = time.perf_counter()
            self._emit("cancel")
            self._emit("highlight", 0, -1, ScanPhase.ROW_SCAN)
            logger.info("Auswahl abgebrochen (Cancel)")
            return

        if self._state.phase == ScanPhase.ROW_SCAN:
            # Zeile gewählt → Spalten-Scan starten
            row_idx = self._state.current_row
            row = self._layout.rows[row_idx]

            if row.size == 1:
                # Nur ein Item in der Zeile → direkt auswählen
                self._start_confirm(row.items[0])
            else:
                # Spalten-Scan starten
                self._state.phase = ScanPhase.COL_SCAN
                self._state.current_col = 0
                self._state.last_advance_time = time.perf_counter()
                self._emit("highlight", row_idx, 0, ScanPhase.COL_SCAN)
                if self._layout.speak_on_highlight:
                    self._emit("speak", row.items[0].speak)
            return

        if self._state.phase == ScanPhase.COL_SCAN:
            # Spalte gewählt → Item auswählen
            row_idx = self._state.current_row
            col_idx = self._state.current_col
            item = self._layout.get_item(row_idx, col_idx)
            if item:
                self._start_confirm(item)
            return

        if self._state.phase == ScanPhase.GROUP_SCAN:
            # Gruppe gewählt → Item-Scan starten
            self._state.phase = ScanPhase.ITEM_SCAN
            self._state.current_col = 0
            self._state.last_advance_time = time.perf_counter()
            row = self._layout.rows[self._state.current_row]
            self._emit("highlight", self._state.current_row, 0, ScanPhase.ITEM_SCAN)
            if row.items and self._layout.speak_on_highlight:
                self._emit("speak", row.items[0].speak)
            return

        if self._state.phase == ScanPhase.ITEM_SCAN:
            # Item gewählt
            row_idx = self._state.current_row
            col_idx = self._state.current_col
            item = self._layout.get_item(row_idx, col_idx)
            if item:
                self._start_confirm(item)
            return

    def _start_confirm(self, item: ScanItem) -> None:
        """Startet den Cancel-Countdown für ein Item."""
        self._state.phase = ScanPhase.CONFIRM
        self._state.selected_item = item
        self._state.confirm_start_time = time.perf_counter()
        self._emit("confirm", item)
        logger.info(f"Bestätigung: '{item.label}' (Cancel in {self._layout.cancel_countdown_s}s)")

    def _advance(self) -> None:
        """Rückt den Scanner einen Schritt weiter."""
        if self._state.phase == ScanPhase.ROW_SCAN:
            self._state.current_row += 1
            if self._state.current_row >= self._layout.row_count:
                self._state.current_row = 0
                self._state.cycle_count += 1
                if self._state.cycle_count >= self._layout.max_cycles:
                    self._state.phase = ScanPhase.NO_ANSWER
                    self._emit("no_answer")
                    logger.info("Timeout — KEINE ANTWORT")
                    return

            self._emit("highlight", self._state.current_row, -1, ScanPhase.ROW_SCAN)

            # Zeilen-Label vorlesen (optional)
            row = self._layout.rows[self._state.current_row]
            if row.label and self._layout.speak_on_highlight:
                self._emit("speak", row.label)

        elif self._state.phase == ScanPhase.COL_SCAN:
            row = self._layout.rows[self._state.current_row]
            self._state.current_col += 1
            if self._state.current_col >= row.size:
                self._state.current_col = 0
                self._state.cycle_count += 1
                if self._state.cycle_count >= self._layout.max_cycles:
                    # Zurück zum Zeilen-Scan
                    self._state.phase = ScanPhase.ROW_SCAN
                    self._state.current_row = 0
                    self._state.cycle_count = 0
                    self._state.last_advance_time = time.perf_counter()
                    self._emit("highlight", 0, -1, ScanPhase.ROW_SCAN)
                    return

            self._emit("highlight", self._state.current_row,
                       self._state.current_col, ScanPhase.COL_SCAN)

            item = row.items[self._state.current_col]
            if self._layout.speak_on_highlight:
                self._emit("speak", item.speak)

        elif self._state.phase == ScanPhase.ITEM_SCAN:
            row = self._layout.rows[self._state.current_row]
            self._state.current_col += 1
            if self._state.current_col >= row.size:
                self._state.current_col = 0
                self._state.cycle_count += 1
                if self._state.cycle_count >= self._layout.max_cycles:
                    # Zurück zum Gruppen-Scan
                    self._state.phase = ScanPhase.GROUP_SCAN
                    self._state.current_row = 0
                    self._state.cycle_count = 0
                    self._emit("highlight", 0, -1, ScanPhase.GROUP_SCAN)
                    return

            self._emit("highlight", self._state.current_row,
                       self._state.current_col, ScanPhase.ITEM_SCAN)

            item = row.items[self._state.current_col]
            if self._layout.speak_on_highlight:
                self._emit("speak", item.speak)

    @property
    def confirm_progress(self) -> float:
        """Fortschritt des Cancel-Countdowns (0.0 bis 1.0)."""
        if self._state.phase != ScanPhase.CONFIRM:
            return 0.0
        elapsed = time.perf_counter() - self._state.confirm_start_time
        return min(1.0, elapsed / self._layout.cancel_countdown_s)

    @property
    def is_active(self) -> bool:
        """Ob der Scanner aktiv scannt."""
        return self._state.phase not in (ScanPhase.IDLE, ScanPhase.SELECTED, ScanPhase.NO_ANSWER)
