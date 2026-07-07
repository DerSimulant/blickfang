"""Tages-Protokoll-Export: Vollständiger Tagesverlauf als Textdatei.

Speichert automatisch alle Kommunikations-Events eines Tages und
ermöglicht den Export als formatierte Textdatei für Therapeuten und Dokumentation.
"""

from __future__ import annotations

import json
import logging
import time
from datetime import datetime, date
from pathlib import Path
from typing import Any, Dict, List

from fastapi import APIRouter
from fastapi.responses import Response

logger = logging.getLogger(__name__)

router = APIRouter()

# ─── Protokoll-Speicher ──────────────────────────────────────────────────

_protocols_dir = Path(__file__).resolve().parents[3] / "data" / "protocols"
_protocols_dir.mkdir(parents=True, exist_ok=True)


def _get_today_file() -> Path:
    """Gibt den Pfad zur heutigen Protokoll-Datei zurück."""
    return _protocols_dir / f"{date.today().isoformat()}.jsonl"


def log_event(event_type: str, data: Dict[str, Any], person: str = "default") -> None:
    """Protokolliert ein Event im Tages-Protokoll.

    Args:
        event_type: Art des Events (communication, signal, mode_change, calibration, error)
        data: Event-Daten
        person: Name der Person
    """
    entry = {
        "timestamp": datetime.now().isoformat(),
        "type": event_type,
        "person": person,
        "data": data,
    }

    try:
        with open(_get_today_file(), "a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    except Exception as e:
        logger.error(f"Protokoll-Fehler: {e}")


def get_today_events() -> List[Dict[str, Any]]:
    """Gibt alle Events des heutigen Tages zurück."""
    path = _get_today_file()
    if not path.exists():
        return []

    events = []
    for line in path.read_text(encoding="utf-8").strip().split("\n"):
        if line:
            try:
                events.append(json.loads(line))
            except json.JSONDecodeError:
                pass
    return events


# ─── API-Endpunkte ───────────────────────────────────────────────────────


@router.get("/api/protocol/today")
async def get_today_protocol():
    """Gibt das heutige Protokoll zurück."""
    events = get_today_events()
    return {
        "date": date.today().isoformat(),
        "events": events,
        "count": len(events),
    }


@router.get("/api/protocol/dates")
async def get_available_dates():
    """Gibt alle verfügbaren Protokoll-Tage zurück."""
    dates = []
    for path in sorted(_protocols_dir.glob("*.jsonl"), reverse=True):
        dates.append(path.stem)
    return {"dates": dates}


@router.get("/api/protocol/export/{target_date}")
async def export_protocol(target_date: str):
    """Exportiert ein Tages-Protokoll als formatierte Textdatei."""
    path = _protocols_dir / f"{target_date}.jsonl"
    if not path.exists():
        return {"error": "Kein Protokoll für dieses Datum"}

    events = []
    for line in path.read_text(encoding="utf-8").strip().split("\n"):
        if line:
            try:
                events.append(json.loads(line))
            except json.JSONDecodeError:
                pass

    # Formatierte Ausgabe
    lines = []
    lines.append("╔══════════════════════════════════════════════════╗")
    lines.append("║       blickfang — Tages-Protokoll               ║")
    lines.append("╚══════════════════════════════════════════════════╝")
    lines.append("")
    lines.append(f"  Datum:     {target_date}")
    lines.append(f"  Einträge:  {len(events)}")

    # Statistiken berechnen
    comm_events = [e for e in events if e.get("type") == "communication"]
    signal_events = [e for e in events if e.get("type") == "signal"]
    persons = set(e.get("person", "?") for e in events)

    lines.append(f"  Personen:  {', '.join(persons)}")
    lines.append(f"  Aussagen:  {len(comm_events)}")
    lines.append(f"  Signale:   {len(signal_events)}")
    lines.append("")
    lines.append("─" * 50)
    lines.append("")

    # Zeitverlauf
    lines.append("KOMMUNIKATIONS-VERLAUF")
    lines.append("")

    current_hour = ""
    for event in events:
        ts = event.get("timestamp", "")
        event_type = event.get("type", "")
        data = event.get("data", {})

        # Stunden-Trenner
        hour = ts[11:13] if len(ts) > 13 else ""
        if hour and hour != current_hour:
            current_hour = hour
            lines.append(f"  --- {hour}:00 Uhr ---")
            lines.append("")

        time_str = ts[11:19] if len(ts) > 19 else ts

        if event_type == "communication":
            text = data.get("text", "")
            mode = data.get("mode", "")
            lines.append(f"  [{time_str}] 💬 {text}")
            lines.append(f"             (Modus: {mode})")
            lines.append("")
        elif event_type == "mode_change":
            old_mode = data.get("from", "")
            new_mode = data.get("to", "")
            lines.append(f"  [{time_str}] 🔄 Modus: {old_mode} → {new_mode}")
        elif event_type == "error":
            msg = data.get("message", "")
            lines.append(f"  [{time_str}] ⚠️  {msg}")
        elif event_type == "session_start":
            lines.append(f"  [{time_str}] ▶️  Session gestartet")
        elif event_type == "session_end":
            lines.append(f"  [{time_str}] ⏹️  Session beendet")

    lines.append("")
    lines.append("─" * 50)
    lines.append("")

    # Zusammenfassung
    if comm_events:
        lines.append("ZUSAMMENFASSUNG DER AUSSAGEN")
        lines.append("")
        for i, event in enumerate(comm_events, 1):
            text = event.get("data", {}).get("text", "")
            ts = event.get("timestamp", "")[11:16]
            lines.append(f"  {i:3d}. [{ts}] {text}")
        lines.append("")

    lines.append("─" * 50)
    lines.append(f"  Erstellt: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    lines.append("  Software: blickfang v0.3.0")
    lines.append("")

    content = "\n".join(lines)
    filename = f"blickfang_protokoll_{target_date}.txt"

    return Response(
        content=content,
        media_type="text/plain; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/api/protocol/export-today")
async def export_today():
    """Shortcut: Exportiert das heutige Protokoll."""
    return await export_protocol(date.today().isoformat())
