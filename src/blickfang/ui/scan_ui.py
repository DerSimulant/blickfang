"""Tkinter-UI: Scan-Anzeige und Live-Monitor (/LF700/–/LF710/).

Zeigt:
- Aktuellen Kanalwert, Baseline, Schwellwert als Balken/Ampel
- Automaten-Zustand
- 3-Item-Scan (JA/NEIN/PASSE) mit Hervorhebung
- Cancel-Countdown
- Erwartete Zufalls-Auslösungsrate (/LF710/)
- Qualitäts-/Veto-Status
"""

from __future__ import annotations

import logging
import tkinter as tk
from tkinter import font as tkfont
from typing import Optional

from blickfang.core.events import DetectorState, QualityState, SystemStatus
from blickfang.output.scanning import ScanState

logger = logging.getLogger(__name__)


# Farben
_COLOR_BG = "#1a1a2e"
_COLOR_FG = "#eaeaea"
_COLOR_ACCENT = "#0f3460"
_COLOR_HIGHLIGHT = "#e94560"
_COLOR_OK = "#4caf50"
_COLOR_WARNING = "#ff9800"
_COLOR_DANGER = "#f44336"
_COLOR_IDLE = "#607d8b"
_COLOR_ACTIVE = "#2196f3"
_COLOR_VETO = "#9c27b0"


class ScanUI:
    """Hauptfenster der blickfang-Anwendung.

    Enthält:
    - Scan-Bereich (JA/NEIN/PASSE)
    - Live-Monitor (Balken, Zustand, FP-Rate)
    - Status-Leiste
    """

    def __init__(self, fullscreen: bool = False, font_size: int = 24):
        self._root = tk.Tk()
        self._root.title("blickfang — Kommunikation")
        self._root.configure(bg=_COLOR_BG)

        if fullscreen:
            self._root.attributes("-fullscreen", True)
        else:
            self._root.geometry("1024x768")

        self._font_size = font_size
        self._large_font = tkfont.Font(family="Arial", size=font_size * 2, weight="bold")
        self._medium_font = tkfont.Font(family="Arial", size=font_size, weight="bold")
        self._small_font = tkfont.Font(family="Arial", size=font_size // 2)
        self._mono_font = tkfont.Font(family="Courier", size=font_size // 2)

        # UI-Elemente
        self._scan_labels: list = []
        self._monitor_canvas: Optional[tk.Canvas] = None
        self._status_label: Optional[tk.Label] = None
        self._countdown_label: Optional[tk.Label] = None
        self._fp_label: Optional[tk.Label] = None
        self._state_label: Optional[tk.Label] = None
        self._quality_label: Optional[tk.Label] = None

        self._build_ui()

    def _build_ui(self) -> None:
        """Baut die UI-Elemente auf."""
        # Hauptlayout: oben Scan, unten Monitor
        self._root.grid_rowconfigure(0, weight=3)
        self._root.grid_rowconfigure(1, weight=2)
        self._root.grid_columnconfigure(0, weight=1)

        # --- Scan-Bereich ---
        scan_frame = tk.Frame(self._root, bg=_COLOR_BG)
        scan_frame.grid(row=0, column=0, sticky="nsew", padx=20, pady=20)

        # Titel
        title_label = tk.Label(
            scan_frame, text="Auswahl:", font=self._medium_font,
            bg=_COLOR_BG, fg=_COLOR_FG
        )
        title_label.pack(pady=(10, 20))

        # Scan-Items
        items_frame = tk.Frame(scan_frame, bg=_COLOR_BG)
        items_frame.pack(expand=True, fill="both")

        for i, item in enumerate(["JA", "NEIN", "PASSE"]):
            label = tk.Label(
                items_frame, text=item, font=self._large_font,
                bg=_COLOR_ACCENT, fg=_COLOR_FG,
                padx=40, pady=30, relief="raised", borderwidth=3
            )
            label.pack(side="left", expand=True, fill="both", padx=10)
            self._scan_labels.append(label)

        # Countdown-Anzeige
        self._countdown_label = tk.Label(
            scan_frame, text="", font=self._medium_font,
            bg=_COLOR_BG, fg=_COLOR_WARNING
        )
        self._countdown_label.pack(pady=10)

        # --- Monitor-Bereich ---
        monitor_frame = tk.Frame(self._root, bg=_COLOR_ACCENT)
        monitor_frame.grid(row=1, column=0, sticky="nsew", padx=20, pady=(0, 20))

        # Monitor-Titel
        monitor_title = tk.Label(
            monitor_frame, text="Live-Monitor", font=self._small_font,
            bg=_COLOR_ACCENT, fg=_COLOR_FG
        )
        monitor_title.pack(anchor="w", padx=10, pady=5)

        # Canvas für Balkenanzeige
        self._monitor_canvas = tk.Canvas(
            monitor_frame, height=60, bg=_COLOR_BG, highlightthickness=0
        )
        self._monitor_canvas.pack(fill="x", padx=10, pady=5)

        # Info-Zeile
        info_frame = tk.Frame(monitor_frame, bg=_COLOR_ACCENT)
        info_frame.pack(fill="x", padx=10, pady=5)

        self._state_label = tk.Label(
            info_frame, text="Zustand: IDLE", font=self._small_font,
            bg=_COLOR_ACCENT, fg=_COLOR_FG
        )
        self._state_label.pack(side="left", padx=10)

        self._quality_label = tk.Label(
            info_frame, text="Qualität: OK", font=self._small_font,
            bg=_COLOR_ACCENT, fg=_COLOR_OK
        )
        self._quality_label.pack(side="left", padx=10)

        self._fp_label = tk.Label(
            info_frame, text="Erw. FP/min: 0.0", font=self._small_font,
            bg=_COLOR_ACCENT, fg=_COLOR_FG
        )
        self._fp_label.pack(side="left", padx=10)

        # FPS-Anzeige
        self._fps_label = tk.Label(
            info_frame, text="FPS: --", font=self._small_font,
            bg=_COLOR_ACCENT, fg=_COLOR_FG
        )
        self._fps_label.pack(side="right", padx=10)

        # Status-Leiste
        self._status_label = tk.Label(
            self._root, text="Bereit", font=self._small_font,
            bg=_COLOR_BG, fg=_COLOR_IDLE, anchor="w"
        )
        self._status_label.grid(row=2, column=0, sticky="ew", padx=20)

    def highlight_item(self, index: int, item: str) -> None:
        """Hebt ein Scan-Item hervor."""
        for i, label in enumerate(self._scan_labels):
            if i == index:
                label.configure(bg=_COLOR_HIGHLIGHT, relief="sunken")
            else:
                label.configure(bg=_COLOR_ACCENT, relief="raised")

    def show_countdown(self, remaining_s: float) -> None:
        """Zeigt den Cancel-Countdown an."""
        if self._countdown_label:
            if remaining_s > 0:
                self._countdown_label.configure(
                    text=f"Abbrechen möglich: {remaining_s:.1f}s"
                )
            else:
                self._countdown_label.configure(text="")

    def show_result(self, text: str, color: str = _COLOR_OK) -> None:
        """Zeigt das Ergebnis an."""
        if self._status_label:
            self._status_label.configure(text=text, fg=color)

    def update_monitor(self, status: SystemStatus) -> None:
        """Aktualisiert den Live-Monitor (/LF700/)."""
        if self._monitor_canvas is None:
            return

        canvas = self._monitor_canvas
        canvas.delete("all")

        width = canvas.winfo_width()
        height = canvas.winfo_height()

        if width < 10:
            return

        # Balkenanzeige: Baseline, Schwellwert, aktueller Wert
        # Normierung auf Anzeige
        value_range = max(abs(status.threshold_value - status.baseline_value) * 3, 0.01)
        center_x = width / 2

        # Baseline-Linie (grün)
        baseline_x = center_x
        canvas.create_line(
            baseline_x, 5, baseline_x, height - 5,
            fill=_COLOR_OK, width=2, dash=(4, 2)
        )

        # Schwellwert-Linie (orange)
        if value_range > 0:
            threshold_offset = (status.threshold_value - status.baseline_value) / value_range * (width / 2)
            threshold_x = center_x + threshold_offset
            canvas.create_line(
                threshold_x, 5, threshold_x, height - 5,
                fill=_COLOR_WARNING, width=2
            )

            # Aktueller Wert (Balken)
            value_offset = (status.current_value - status.baseline_value) / value_range * (width / 2)
            value_x = center_x + value_offset

            # Balkenfarbe je nach Zustand
            bar_color = _COLOR_IDLE
            if status.detector_state in (DetectorState.RISING, DetectorState.HELD):
                bar_color = _COLOR_ACTIVE
            elif status.detector_state == DetectorState.EMIT:
                bar_color = _COLOR_HIGHLIGHT
            elif status.veto_active:
                bar_color = _COLOR_VETO

            bar_width = max(4, height // 3)
            canvas.create_rectangle(
                center_x, height // 2 - bar_width // 2,
                value_x, height // 2 + bar_width // 2,
                fill=bar_color, outline=""
            )

        # Beschriftungen
        canvas.create_text(
            10, height - 5, text=f"Wert: {status.current_value:.3f}",
            anchor="sw", fill=_COLOR_FG, font=self._mono_font
        )
        canvas.create_text(
            width - 10, height - 5,
            text=f"Baseline: {status.baseline_value:.3f} | Schwelle: {status.threshold_value:.3f}",
            anchor="se", fill=_COLOR_FG, font=self._mono_font
        )

        # Zustandsanzeige
        if self._state_label:
            state_name = status.detector_state.name
            self._state_label.configure(text=f"Zustand: {state_name}")

        # Qualitätsanzeige
        if self._quality_label:
            q = status.quality_state
            color = _COLOR_OK if q == QualityState.OK else (
                _COLOR_WARNING if q == QualityState.DEGRADED else _COLOR_DANGER
            )
            text = f"Qualität: {q.name}"
            if status.veto_active:
                text += f" | VETO ({status.veto_remaining_s:.1f}s)"
                color = _COLOR_VETO
            self._quality_label.configure(text=text, fg=color)

        # FP-Rate (/LF710/)
        if self._fp_label:
            fp = status.expected_fp_per_min
            color = _COLOR_OK if fp < 0.5 else (
                _COLOR_WARNING if fp < 2.0 else _COLOR_DANGER
            )
            self._fp_label.configure(
                text=f"Erw. FP/min: {fp:.2f}", fg=color
            )

        # FPS
        if self._fps_label:
            fps = status.fps
            color = _COLOR_OK if fps >= 12 else _COLOR_DANGER
            self._fps_label.configure(text=f"FPS: {fps:.0f}", fg=color)

    def set_status(self, text: str, color: str = _COLOR_FG) -> None:
        """Setzt die Status-Leiste."""
        if self._status_label:
            self._status_label.configure(text=text, fg=color)

    def reset_scan(self) -> None:
        """Setzt die Scan-Anzeige zurück."""
        for label in self._scan_labels:
            label.configure(bg=_COLOR_ACCENT, relief="raised")
        if self._countdown_label:
            self._countdown_label.configure(text="")

    @property
    def root(self) -> tk.Tk:
        return self._root

    def mainloop(self) -> None:
        """Startet die Tkinter-Mainloop."""
        self._root.mainloop()

    def destroy(self) -> None:
        """Schließt das Fenster."""
        self._root.destroy()
