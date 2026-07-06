"""Entrypoint: blickfang-annotate — Annotations-Tool.

Ermöglicht das Taggen von Zeitabschnitten in aufgezeichneten Sessions:
- Signal-Zeitpunkte markieren ("hier war ein willentliches Signal")
- Ruhephasen markieren ("hier war Ruhe")
- Unruhe-Phasen markieren ("hier war Tremor/Chorea")

Zwei Modi:
1. Video-Modus: Video abspielen und per Tastendruck annotieren
2. Kurven-Modus: Feature-Kurven anzeigen und Bereiche markieren

Ausgabe: annotations.yaml im Session-Verzeichnis.

Workflow:
    blickfang-annotate recordings/Anna_20260706_signal/
    blickfang-annotate recordings/Anna_20260706_signal/ --channel ear_left
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
import time
import tkinter as tk
from pathlib import Path
from tkinter import messagebox, ttk
from typing import Dict, List, Optional, Tuple

import yaml

logger = logging.getLogger(__name__)


class Segment:
    """Ein annotiertes Zeitsegment."""

    def __init__(
        self,
        start_s: float,
        end_s: float,
        label: str,
        channel: Optional[str] = None,
        confidence: float = 1.0,
        note: str = "",
    ):
        self.start_s = start_s
        self.end_s = end_s
        self.label = label  # "signal", "ruhe", "unruhe", "artefakt"
        self.channel = channel
        self.confidence = confidence
        self.note = note

    def to_dict(self) -> dict:
        return {
            "start_s": round(self.start_s, 3),
            "end_s": round(self.end_s, 3),
            "label": self.label,
            "channel": self.channel,
            "confidence": self.confidence,
            "note": self.note,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "Segment":
        return cls(
            start_s=d["start_s"],
            end_s=d["end_s"],
            label=d["label"],
            channel=d.get("channel"),
            confidence=d.get("confidence", 1.0),
            note=d.get("note", ""),
        )


class AnnotationStore:
    """Verwaltet Annotationen für eine Session."""

    def __init__(self, session_dir: Path):
        self._session_dir = session_dir
        self._annotations_path = session_dir / "annotations.yaml"
        self._segments: List[Segment] = []
        self._person: str = ""
        self._session_name: str = session_dir.name
        self._load()

    def _load(self) -> None:
        """Lädt bestehende Annotationen."""
        if self._annotations_path.exists():
            with open(self._annotations_path, "r", encoding="utf-8") as f:
                data = yaml.safe_load(f) or {}
            self._person = data.get("person", "")
            self._session_name = data.get("session", self._session_name)
            for seg_dict in data.get("segments", []):
                self._segments.append(Segment.from_dict(seg_dict))
            logger.info(f"Geladene Annotationen: {len(self._segments)} Segmente")

    def save(self) -> None:
        """Speichert Annotationen."""
        data = {
            "person": self._person,
            "session": self._session_name,
            "annotated_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
            "segments": [s.to_dict() for s in sorted(self._segments, key=lambda x: x.start_s)],
            "summary": self._compute_summary(),
        }
        with open(self._annotations_path, "w", encoding="utf-8") as f:
            yaml.dump(data, f, default_flow_style=False, allow_unicode=True)
        logger.info(f"Annotationen gespeichert: {self._annotations_path}")

    def add_segment(self, segment: Segment) -> None:
        """Fügt ein Segment hinzu."""
        self._segments.append(segment)

    def remove_last(self) -> Optional[Segment]:
        """Entfernt das letzte Segment."""
        if self._segments:
            return self._segments.pop()
        return None

    @property
    def segments(self) -> List[Segment]:
        return self._segments

    def _compute_summary(self) -> dict:
        """Berechnet eine Zusammenfassung."""
        labels = {}
        for seg in self._segments:
            if seg.label not in labels:
                labels[seg.label] = {"count": 0, "total_duration_s": 0.0}
            labels[seg.label]["count"] += 1
            labels[seg.label]["total_duration_s"] += seg.end_s - seg.start_s

        return {
            "total_segments": len(self._segments),
            "by_label": labels,
        }


class FeatureTimeline:
    """Lädt und verwaltet den Feature-Stream einer Session."""

    def __init__(self, session_dir: Path):
        self._session_dir = session_dir
        self._frames: List[dict] = []
        self._channels: List[str] = []
        self._duration_s: float = 0.0
        self._load()

    def _load(self) -> None:
        """Lädt den Feature-Stream."""
        jsonl_path = self._session_dir / "features.jsonl"
        if not jsonl_path.exists():
            raise FileNotFoundError(f"Feature-Datei nicht gefunden: {jsonl_path}")

        with open(jsonl_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    data = json.loads(line)
                    if data.get("type") == "channel_frame":
                        self._frames.append(data)
                except json.JSONDecodeError:
                    continue

        if self._frames:
            self._channels = list(self._frames[0].get("channels", {}).keys())
            first_t = self._frames[0].get("relative_time_s", 0)
            last_t = self._frames[-1].get("relative_time_s", 0)
            self._duration_s = last_t - first_t

        logger.info(
            f"Feature-Stream geladen: {len(self._frames)} Frames, "
            f"{self._duration_s:.1f}s, {len(self._channels)} Kanäle"
        )

    @property
    def frames(self) -> List[dict]:
        return self._frames

    @property
    def channels(self) -> List[str]:
        return self._channels

    @property
    def duration_s(self) -> float:
        return self._duration_s

    def get_channel_values(self, channel: str) -> Tuple[List[float], List[float]]:
        """Gibt Zeitstempel und Werte eines Kanals zurück."""
        times = []
        values = []
        for frame in self._frames:
            t = frame.get("relative_time_s", frame.get("timestamp", 0))
            v = frame.get("channels", {}).get(channel, 0.0)
            times.append(t)
            values.append(v)
        return times, values


class AnnotateApp:
    """Annotations-Anwendung mit Tkinter-UI.

    Zeigt eine Zeitleiste und ermöglicht das Markieren von Segmenten
    per Tastendruck oder Mausklick.
    """

    def __init__(self, session_dir: Path, channel: Optional[str] = None):
        self._session_dir = session_dir
        self._preferred_channel = channel

        # Daten laden
        self._timeline = FeatureTimeline(session_dir)
        self._store = AnnotationStore(session_dir)

        # Zustand
        self._current_time: float = 0.0
        self._marking_start: Optional[float] = None
        self._current_label: str = "signal"
        self._playback_speed: float = 1.0
        self._is_playing: bool = False
        self._selected_channel: str = ""

        # UI
        self._root: Optional[tk.Tk] = None
        self._canvas: Optional[tk.Canvas] = None
        self._time_label: Optional[tk.Label] = None
        self._segments_list: Optional[tk.Listbox] = None

    def run(self) -> None:
        """Startet die Annotations-UI."""
        if not self._timeline.channels:
            print("FEHLER: Keine Kanäle im Feature-Stream gefunden.")
            return

        # Kanal auswählen
        if self._preferred_channel and self._preferred_channel in self._timeline.channels:
            self._selected_channel = self._preferred_channel
        else:
            self._selected_channel = self._timeline.channels[0]

        self._root = tk.Tk()
        self._root.title(f"blickfang-annotate — {self._session_dir.name}")
        self._root.geometry("1200x700")
        self._root.configure(bg="#1a1a2e")

        self._build_ui()
        self._draw_timeline()
        self._update_segments_list()

        print(f"=== blickfang-annotate ===")
        print(f"  Session: {self._session_dir.name}")
        print(f"  Dauer: {self._timeline.duration_s:.1f}s")
        print(f"  Kanäle: {len(self._timeline.channels)}")
        print(f"  Kanal: {self._selected_channel}")
        print(f"  Bestehende Annotationen: {len(self._store.segments)}")
        print()
        print("  Tasten:")
        print("    S = Signal-Start/Ende markieren")
        print("    R = Ruhe-Start/Ende markieren")
        print("    U = Unruhe-Start/Ende markieren")
        print("    A = Artefakt-Start/Ende markieren")
        print("    Leertaste = Play/Pause")
        print("    ← → = Vor/Zurück (1s)")
        print("    Strg+Z = Letzte Annotation rückgängig")
        print("    Strg+S = Speichern")
        print("    ESC = Beenden (speichert automatisch)")
        print()

        self._root.mainloop()

    def _build_ui(self) -> None:
        """Baut die UI auf."""
        # Toolbar
        toolbar = tk.Frame(self._root, bg="#0f3460", height=40)
        toolbar.pack(fill="x", padx=5, pady=5)

        # Kanal-Auswahl
        tk.Label(toolbar, text="Kanal:", bg="#0f3460", fg="white").pack(side="left", padx=5)
        self._channel_var = tk.StringVar(value=self._selected_channel)
        channel_menu = ttk.Combobox(
            toolbar, textvariable=self._channel_var,
            values=self._timeline.channels, width=20
        )
        channel_menu.pack(side="left", padx=5)
        channel_menu.bind("<<ComboboxSelected>>", self._on_channel_change)

        # Label-Auswahl
        tk.Label(toolbar, text="Label:", bg="#0f3460", fg="white").pack(side="left", padx=15)
        self._label_var = tk.StringVar(value="signal")
        for label, color in [("signal", "#4caf50"), ("ruhe", "#2196f3"),
                             ("unruhe", "#ff9800"), ("artefakt", "#9c27b0")]:
            rb = tk.Radiobutton(
                toolbar, text=label.upper(), variable=self._label_var,
                value=label, bg="#0f3460", fg=color, selectcolor="#0f3460",
                activebackground="#0f3460", activeforeground=color,
                font=("Arial", 10, "bold")
            )
            rb.pack(side="left", padx=3)

        # Zeitanzeige
        self._time_label = tk.Label(
            toolbar, text="0:00.0 / 0:00.0", font=("Courier", 12),
            bg="#0f3460", fg="white"
        )
        self._time_label.pack(side="right", padx=10)

        # Canvas für Zeitleiste
        self._canvas = tk.Canvas(
            self._root, bg="#1a1a2e", height=300, highlightthickness=0
        )
        self._canvas.pack(fill="both", expand=True, padx=5, pady=5)
        self._canvas.bind("<Button-1>", self._on_canvas_click)
        self._canvas.bind("<Configure>", lambda e: self._draw_timeline())

        # Segmente-Liste
        list_frame = tk.Frame(self._root, bg="#1a1a2e")
        list_frame.pack(fill="x", padx=5, pady=5)

        tk.Label(list_frame, text="Annotationen:", bg="#1a1a2e", fg="white",
                 font=("Arial", 10, "bold")).pack(anchor="w")

        self._segments_list = tk.Listbox(
            list_frame, height=6, bg="#0f3460", fg="white",
            font=("Courier", 10), selectbackground="#e94560"
        )
        self._segments_list.pack(fill="x")

        # Status-Leiste
        self._status_label = tk.Label(
            self._root, text="Bereit — Klicke auf die Zeitleiste oder nutze Tasten",
            bg="#1a1a2e", fg="#607d8b", anchor="w"
        )
        self._status_label.pack(fill="x", padx=5, pady=2)

        # Key-Bindings
        self._root.bind("<space>", self._toggle_playback)
        self._root.bind("<Left>", lambda e: self._seek(-1.0))
        self._root.bind("<Right>", lambda e: self._seek(1.0))
        self._root.bind("<s>", lambda e: self._toggle_mark("signal"))
        self._root.bind("<r>", lambda e: self._toggle_mark("ruhe"))
        self._root.bind("<u>", lambda e: self._toggle_mark("unruhe"))
        self._root.bind("<a>", lambda e: self._toggle_mark("artefakt"))
        self._root.bind("<Control-z>", self._undo)
        self._root.bind("<Control-s>", self._save)
        self._root.bind("<Escape>", self._quit)
        self._root.protocol("WM_DELETE_WINDOW", lambda: self._quit(None))

    def _draw_timeline(self) -> None:
        """Zeichnet die Zeitleiste mit Kanalwerten und Annotationen."""
        if not self._canvas:
            return

        self._canvas.delete("all")
        width = self._canvas.winfo_width()
        height = self._canvas.winfo_height()

        if width < 50 or height < 50:
            return

        duration = max(self._timeline.duration_s, 1.0)
        margin_left = 60
        margin_right = 20
        margin_top = 30
        margin_bottom = 40
        plot_width = width - margin_left - margin_right
        plot_height = height - margin_top - margin_bottom

        # Hintergrund-Raster
        for i in range(0, int(duration) + 1, max(1, int(duration // 10))):
            x = margin_left + (i / duration) * plot_width
            self._canvas.create_line(x, margin_top, x, height - margin_bottom,
                                     fill="#2a2a4e", dash=(2, 4))
            self._canvas.create_text(x, height - margin_bottom + 15,
                                     text=f"{i}s", fill="#607d8b", font=("Arial", 8))

        # Annotierte Segmente als farbige Bereiche
        label_colors = {
            "signal": "#4caf5040",
            "ruhe": "#2196f340",
            "unruhe": "#ff980040",
            "artefakt": "#9c27b040",
        }
        label_colors_solid = {
            "signal": "#4caf50",
            "ruhe": "#2196f3",
            "unruhe": "#ff9800",
            "artefakt": "#9c27b0",
        }

        for seg in self._store.segments:
            x1 = margin_left + (seg.start_s / duration) * plot_width
            x2 = margin_left + (seg.end_s / duration) * plot_width
            color = label_colors_solid.get(seg.label, "#607d8b")
            self._canvas.create_rectangle(
                x1, margin_top, x2, height - margin_bottom,
                fill="", outline=color, width=2
            )
            # Label-Text oben
            mid_x = (x1 + x2) / 2
            self._canvas.create_text(
                mid_x, margin_top - 10, text=seg.label.upper(),
                fill=color, font=("Arial", 8, "bold")
            )

        # Kanalwerte zeichnen
        times, values = self._timeline.get_channel_values(self._selected_channel)
        if times and values:
            # Normierung
            v_min = min(values) if values else 0
            v_max = max(values) if values else 1
            v_range = max(v_max - v_min, 0.001)

            # Punkte berechnen
            points = []
            step = max(1, len(times) // plot_width)  # Downsampling
            for i in range(0, len(times), step):
                x = margin_left + (times[i] / duration) * plot_width
                y = margin_top + plot_height - ((values[i] - v_min) / v_range) * plot_height
                points.append((x, y))

            # Linie zeichnen
            if len(points) > 1:
                flat_points = [coord for p in points for coord in p]
                self._canvas.create_line(
                    *flat_points, fill="#00bcd4", width=1, smooth=True
                )

            # Y-Achse
            self._canvas.create_text(
                margin_left - 30, margin_top, text=f"{v_max:.2f}",
                fill="#607d8b", font=("Arial", 8), anchor="e"
            )
            self._canvas.create_text(
                margin_left - 30, height - margin_bottom, text=f"{v_min:.2f}",
                fill="#607d8b", font=("Arial", 8), anchor="e"
            )

        # Aktuelle Position (Cursor)
        cursor_x = margin_left + (self._current_time / duration) * plot_width
        self._canvas.create_line(
            cursor_x, margin_top, cursor_x, height - margin_bottom,
            fill="#e94560", width=2
        )

        # Markierungs-Start (wenn aktiv)
        if self._marking_start is not None:
            mark_x = margin_left + (self._marking_start / duration) * plot_width
            self._canvas.create_line(
                mark_x, margin_top, mark_x, height - margin_bottom,
                fill="#ffeb3b", width=2, dash=(4, 2)
            )

        # Kanal-Name
        self._canvas.create_text(
            margin_left + 5, margin_top + 10,
            text=self._selected_channel, fill="#00bcd4",
            font=("Arial", 10, "bold"), anchor="w"
        )

    def _on_canvas_click(self, event) -> None:
        """Klick auf die Zeitleiste → Position setzen."""
        width = self._canvas.winfo_width()
        margin_left = 60
        margin_right = 20
        plot_width = width - margin_left - margin_right

        if event.x < margin_left or event.x > width - margin_right:
            return

        ratio = (event.x - margin_left) / plot_width
        self._current_time = ratio * self._timeline.duration_s
        self._update_time_display()
        self._draw_timeline()

    def _on_channel_change(self, event=None) -> None:
        """Kanalwechsel."""
        self._selected_channel = self._channel_var.get()
        self._draw_timeline()

    def _toggle_mark(self, label: str) -> None:
        """Startet oder beendet eine Markierung."""
        self._label_var.set(label)

        if self._marking_start is None:
            # Start markieren
            self._marking_start = self._current_time
            self._status_label.configure(
                text=f"▶ Markierung gestartet bei {self._marking_start:.1f}s "
                     f"({label.upper()}) — nochmal drücken zum Beenden",
                fg="#ffeb3b"
            )
        else:
            # Ende markieren → Segment erstellen
            start = min(self._marking_start, self._current_time)
            end = max(self._marking_start, self._current_time)

            if end - start < 0.05:
                # Zu kurz → als Punkt-Event (100ms Fenster)
                start = max(0, self._current_time - 0.05)
                end = self._current_time + 0.05

            segment = Segment(
                start_s=start,
                end_s=end,
                label=label,
                channel=self._selected_channel,
            )
            self._store.add_segment(segment)
            self._marking_start = None

            self._status_label.configure(
                text=f"✓ Segment hinzugefügt: {label.upper()} "
                     f"[{start:.1f}s – {end:.1f}s]",
                fg="#4caf50"
            )
            self._update_segments_list()
            self._draw_timeline()

    def _toggle_playback(self, event=None) -> None:
        """Play/Pause."""
        self._is_playing = not self._is_playing
        if self._is_playing:
            self._status_label.configure(text="▶ Wiedergabe...", fg="#4caf50")
            self._playback_loop()
        else:
            self._status_label.configure(text="⏸ Pausiert", fg="#ff9800")

    def _playback_loop(self) -> None:
        """Wiedergabe-Schleife."""
        if not self._is_playing:
            return

        self._current_time += 0.05 * self._playback_speed
        if self._current_time >= self._timeline.duration_s:
            self._current_time = 0
            self._is_playing = False
            self._status_label.configure(text="⏹ Ende erreicht", fg="#607d8b")
            return

        self._update_time_display()
        self._draw_timeline()
        self._root.after(50, self._playback_loop)

    def _seek(self, delta_s: float) -> None:
        """Springt um delta_s Sekunden."""
        self._current_time = max(0, min(
            self._timeline.duration_s, self._current_time + delta_s
        ))
        self._update_time_display()
        self._draw_timeline()

    def _undo(self, event=None) -> None:
        """Letzte Annotation rückgängig."""
        removed = self._store.remove_last()
        if removed:
            self._status_label.configure(
                text=f"↩ Rückgängig: {removed.label.upper()} "
                     f"[{removed.start_s:.1f}s – {removed.end_s:.1f}s]",
                fg="#ff9800"
            )
            self._update_segments_list()
            self._draw_timeline()

    def _save(self, event=None) -> None:
        """Speichert Annotationen."""
        self._store.save()
        self._status_label.configure(
            text=f"💾 Gespeichert ({len(self._store.segments)} Segmente)",
            fg="#4caf50"
        )

    def _quit(self, event=None) -> None:
        """Beendet und speichert."""
        self._store.save()
        print(f"\n✓ Annotationen gespeichert: {len(self._store.segments)} Segmente")
        if self._root:
            self._root.destroy()

    def _update_time_display(self) -> None:
        """Aktualisiert die Zeitanzeige."""
        if self._time_label:
            t = self._current_time
            d = self._timeline.duration_s
            self._time_label.configure(
                text=f"{int(t//60)}:{t%60:04.1f} / {int(d//60)}:{d%60:04.1f}"
            )

    def _update_segments_list(self) -> None:
        """Aktualisiert die Segmente-Liste."""
        if self._segments_list is None:
            return
        self._segments_list.delete(0, tk.END)
        for seg in sorted(self._store.segments, key=lambda s: s.start_s):
            text = (
                f"[{seg.start_s:6.1f}s – {seg.end_s:6.1f}s] "
                f"{seg.label.upper():10s} "
                f"({seg.channel or 'alle'})"
            )
            self._segments_list.insert(tk.END, text)


def main():
    """Haupteinstiegspunkt für blickfang-annotate."""
    parser = argparse.ArgumentParser(
        description="blickfang-annotate — Annotieren von aufgezeichneten Sessions"
    )
    parser.add_argument(
        "session_dir", type=Path,
        help="Pfad zum Session-Verzeichnis (enthält features.jsonl)"
    )
    parser.add_argument(
        "--channel", "-c", type=str, default=None,
        help="Bevorzugter Kanal zur Anzeige"
    )
    parser.add_argument(
        "--verbose", "-v", action="store_true",
        help="Ausführliche Ausgabe"
    )
    args = parser.parse_args()

    level = logging.DEBUG if args.verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
    )

    if not args.session_dir.exists():
        print(f"FEHLER: Session-Verzeichnis nicht gefunden: {args.session_dir}")
        sys.exit(1)

    app = AnnotateApp(session_dir=args.session_dir, channel=args.channel)
    app.run()


if __name__ == "__main__":
    main()
