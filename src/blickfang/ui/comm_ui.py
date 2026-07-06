"""Kommunikations-Oberfläche (Tkinter).

Vollbild-UI für die Kommunikation mit:
- Großes Scanning-Raster (gut sichtbar)
- Text-Anzeige (beim Buchstabieren)
- Wortvorschläge
- Modus-Anzeige
- Cancel-Countdown-Balken
- Ermüdungs-Status
"""

from __future__ import annotations

import logging
import threading
import time
import tkinter as tk
from tkinter import font as tkfont
from typing import Optional

from blickfang.scanning.controller import CommMode, CommunicationController
from blickfang.scanning.engine import ScanPhase

logger = logging.getLogger(__name__)

# Farben (hoher Kontrast, gut sichtbar)
COLORS = {
    "bg": "#1a1a2e",            # Dunkler Hintergrund
    "fg": "#ffffff",            # Weißer Text
    "highlight": "#ffcc00",     # Gelb = aktuell gescannt
    "selected": "#00cc66",      # Grün = ausgewählt
    "confirm": "#ff6600",       # Orange = Bestätigung läuft
    "row_highlight": "#2a2a4e", # Zeile hervorgehoben
    "item_normal": "#3a3a5e",   # Normales Item
    "item_highlight": "#ffcc00",# Hervorgehobenes Item
    "text_area": "#0d0d1a",     # Text-Bereich
    "cancel_bar": "#ff3333",    # Cancel-Countdown
    "mode_bar": "#2a4a6e",      # Modus-Leiste
    "prediction": "#4a6a8e",    # Wortvorschlag
}


class CommunicationUI:
    """Tkinter-basierte Kommunikations-Oberfläche.

    Zeigt das Scanning-Raster, Text-Buffer und Status an.
    Verarbeitet Tastatur-Eingaben als Switch-Signal.
    """

    def __init__(
        self,
        controller: CommunicationController,
        fullscreen: bool = True,
        key_switch: bool = False,
    ):
        self._controller = controller
        self._fullscreen = fullscreen
        self._key_switch = key_switch
        self._running = False

        # Tkinter Setup
        self._root: Optional[tk.Tk] = None
        self._canvas: Optional[tk.Canvas] = None

        # UI-Elemente (Canvas-IDs)
        self._item_rects: dict = {}     # (row, col) → rect_id
        self._item_texts: dict = {}     # (row, col) → text_id
        self._text_display_id = None
        self._mode_label_id = None
        self._countdown_bar_id = None
        self._prediction_ids: list = []

        # Layout-Cache
        self._last_layout_name = ""

    def run(self) -> None:
        """Startet die UI (blockiert bis geschlossen)."""
        self._root = tk.Tk()
        self._root.title("blickfang — Kommunikation")
        self._root.configure(bg=COLORS["bg"])

        if self._fullscreen:
            self._root.attributes("-fullscreen", True)
            self._root.bind("<Escape>", lambda e: self._quit())
        else:
            self._root.geometry("1200x800")

        # Canvas für alles
        self._canvas = tk.Canvas(
            self._root,
            bg=COLORS["bg"],
            highlightthickness=0,
        )
        self._canvas.pack(fill=tk.BOTH, expand=True)

        # Tastatur-Bindings
        if self._key_switch:
            self._root.bind("<space>", lambda e: self._on_signal())
            self._root.bind("<Return>", lambda e: self._on_signal())

        self._root.bind("<F1>", lambda e: self._controller.go_home())
        self._root.bind("<F2>", lambda e: self._controller.go_phrases())
        self._root.bind("<F3>", lambda e: self._controller.go_keyboard())
        self._root.bind("<F4>", lambda e: self._controller.go_yesno())
        self._root.bind("<q>", lambda e: self._quit())

        # Initiales Zeichnen nach kurzer Verzögerung (damit Fenster-Größe bekannt)
        self._root.after(100, self._initial_draw)

        # Tick-Loop starten
        self._running = True
        self._tick_loop()

        # Controller starten
        self._controller.start(CommMode.MAIN_MENU)

        self._root.mainloop()

    def _initial_draw(self) -> None:
        """Zeichnet die initiale UI."""
        self._draw_layout()

    def _tick_loop(self) -> None:
        """Regelmäßiger Tick für Scanning und UI-Update."""
        if not self._running:
            return

        # Controller tick
        self._controller.tick()

        # UI aktualisieren
        self._update_display()

        # Nächster Tick in 50ms
        self._root.after(50, self._tick_loop)

    def _on_signal(self) -> None:
        """Verarbeitet ein Switch-Signal (Tastatur)."""
        self._controller.signal()

    def _draw_layout(self) -> None:
        """Zeichnet das aktuelle Layout neu."""
        if not self._canvas:
            return

        layout = self._controller.current_layout

        # Nur neu zeichnen wenn Layout sich geändert hat
        if layout.name == self._last_layout_name:
            return
        self._last_layout_name = layout.name

        self._canvas.delete("all")
        self._item_rects.clear()
        self._item_texts.clear()
        self._prediction_ids.clear()

        w = self._canvas.winfo_width()
        h = self._canvas.winfo_height()

        if w < 100 or h < 100:
            # Fenster noch nicht bereit
            self._root.after(100, self._draw_layout)
            return

        # Layout-Bereiche berechnen
        mode_bar_h = 50
        text_area_h = 80 if self._controller.mode == CommMode.KEYBOARD else 0
        prediction_h = 50 if self._controller.mode == CommMode.KEYBOARD else 0
        countdown_h = 30
        grid_top = mode_bar_h + text_area_h + prediction_h + 10
        grid_bottom = h - countdown_h - 20
        grid_h = grid_bottom - grid_top

        # Modus-Leiste
        self._canvas.create_rectangle(
            0, 0, w, mode_bar_h,
            fill=COLORS["mode_bar"], outline=""
        )
        mode_text = self._get_mode_text()
        self._mode_label_id = self._canvas.create_text(
            w // 2, mode_bar_h // 2,
            text=mode_text,
            fill=COLORS["fg"],
            font=("Arial", 18, "bold"),
        )

        # Hilfe-Text
        self._canvas.create_text(
            w - 10, mode_bar_h // 2,
            text="ESC=Beenden  F1=Menü  Leertaste=Signal",
            fill="#888888",
            font=("Arial", 10),
            anchor="e",
        )

        # Text-Anzeige (nur im Keyboard-Modus)
        if self._controller.mode == CommMode.KEYBOARD:
            self._canvas.create_rectangle(
                20, mode_bar_h + 5, w - 20, mode_bar_h + text_area_h,
                fill=COLORS["text_area"], outline=COLORS["fg"], width=2
            )
            self._text_display_id = self._canvas.create_text(
                30, mode_bar_h + text_area_h // 2 + 5,
                text=self._controller.text_buffer.display_text,
                fill=COLORS["fg"],
                font=("Courier", 24, "bold"),
                anchor="w",
            )

            # Wortvorschläge
            predictions = self._controller.get_predictions()
            pred_y = mode_bar_h + text_area_h + prediction_h // 2 + 5
            pred_w = (w - 40) // max(len(predictions), 1)
            for i, pred in enumerate(predictions[:4]):
                x = 20 + i * pred_w + pred_w // 2
                pid = self._canvas.create_text(
                    x, pred_y,
                    text=f"[{pred}]",
                    fill=COLORS["prediction"],
                    font=("Arial", 14),
                )
                self._prediction_ids.append(pid)

        # Scanning-Raster zeichnen
        if layout.row_count == 0:
            return

        row_h = min(grid_h // layout.row_count, 120)
        max_cols = max(row.size for row in layout.rows)
        col_w = (w - 40) // max(max_cols, 1)

        padding = 4

        for r_idx, row in enumerate(layout.rows):
            y = grid_top + r_idx * row_h
            for c_idx, item in enumerate(row.items):
                x = 20 + c_idx * col_w

                # Rechteck
                rect_id = self._canvas.create_rectangle(
                    x + padding, y + padding,
                    x + col_w - padding, y + row_h - padding,
                    fill=COLORS["item_normal"],
                    outline=COLORS["fg"],
                    width=2,
                )
                self._item_rects[(r_idx, c_idx)] = rect_id

                # Text
                label = item.label
                font_size = 20 if len(label) <= 3 else 14 if len(label) <= 10 else 11
                text_id = self._canvas.create_text(
                    x + col_w // 2, y + row_h // 2,
                    text=label,
                    fill=COLORS["fg"],
                    font=("Arial", font_size, "bold"),
                )
                self._item_texts[(r_idx, c_idx)] = text_id

        # Cancel-Countdown-Balken
        bar_y = h - countdown_h - 10
        self._canvas.create_rectangle(
            20, bar_y, w - 20, bar_y + countdown_h,
            fill=COLORS["bg"], outline=COLORS["fg"], width=1
        )
        self._countdown_bar_id = self._canvas.create_rectangle(
            20, bar_y, 20, bar_y + countdown_h,
            fill=COLORS["cancel_bar"], outline=""
        )

    def _update_display(self) -> None:
        """Aktualisiert die UI basierend auf dem aktuellen Zustand."""
        if not self._canvas:
            return

        layout = self._controller.current_layout
        state = self._controller.engine.state

        # Layout-Wechsel erkennen
        if layout.name != self._last_layout_name:
            self._draw_layout()
            return

        # Alle Items zurücksetzen
        for key, rect_id in self._item_rects.items():
            self._canvas.itemconfig(rect_id, fill=COLORS["item_normal"])

        # Hervorhebung basierend auf Phase
        if state.phase == ScanPhase.ROW_SCAN:
            # Ganze Zeile hervorheben
            row = layout.rows[state.current_row] if state.current_row < layout.row_count else None
            if row:
                for c_idx in range(row.size):
                    key = (state.current_row, c_idx)
                    if key in self._item_rects:
                        self._canvas.itemconfig(
                            self._item_rects[key],
                            fill=COLORS["row_highlight"]
                        )

        elif state.phase == ScanPhase.COL_SCAN:
            # Einzelnes Item hervorheben
            key = (state.current_row, state.current_col)
            if key in self._item_rects:
                self._canvas.itemconfig(
                    self._item_rects[key],
                    fill=COLORS["item_highlight"]
                )
                # Text schwarz für Kontrast
                if key in self._item_texts:
                    self._canvas.itemconfig(self._item_texts[key], fill="#000000")

        elif state.phase == ScanPhase.CONFIRM:
            # Bestätigung — Item orange
            key = (state.current_row, state.current_col)
            if key in self._item_rects:
                self._canvas.itemconfig(
                    self._item_rects[key],
                    fill=COLORS["confirm"]
                )

        elif state.phase == ScanPhase.SELECTED:
            # Ausgewählt — Item grün
            key = (state.current_row, state.current_col)
            if key in self._item_rects:
                self._canvas.itemconfig(
                    self._item_rects[key],
                    fill=COLORS["selected"]
                )

        # Text-Farben zurücksetzen (außer hervorgehobene)
        for key, text_id in self._item_texts.items():
            if state.phase == ScanPhase.COL_SCAN and key == (state.current_row, state.current_col):
                self._canvas.itemconfig(text_id, fill="#000000")
            else:
                self._canvas.itemconfig(text_id, fill=COLORS["fg"])

        # Cancel-Countdown-Balken aktualisieren
        if self._countdown_bar_id:
            progress = self._controller.engine.confirm_progress
            w = self._canvas.winfo_width()
            bar_width = int((w - 40) * progress)
            h = self._canvas.winfo_height()
            bar_y = h - 40
            self._canvas.coords(
                self._countdown_bar_id,
                20, bar_y, 20 + bar_width, bar_y + 30
            )

        # Text-Display aktualisieren (Keyboard-Modus)
        if self._text_display_id and self._controller.mode == CommMode.KEYBOARD:
            self._canvas.itemconfig(
                self._text_display_id,
                text=self._controller.text_buffer.display_text
            )

        # Modus-Label aktualisieren
        if self._mode_label_id:
            self._canvas.itemconfig(
                self._mode_label_id,
                text=self._get_mode_text()
            )

    def _get_mode_text(self) -> str:
        """Gibt den Modus-Text für die Anzeige zurück."""
        mode = self._controller.mode
        if mode == CommMode.MAIN_MENU:
            return "🏠 HAUPTMENÜ"
        elif mode == CommMode.PHRASES:
            return "💬 SCHNELL-PHRASEN"
        elif mode == CommMode.KEYBOARD:
            return "⌨ BUCHSTABIEREN"
        elif mode == CommMode.YESNO:
            return "✓✗ JA / NEIN / PASSE"
        return "blickfang"

    def _quit(self) -> None:
        """Beendet die UI."""
        self._running = False
        self._controller.stop()
        if self._root:
            self._root.destroy()
