"""Layout-Loader: Lädt Scanning-Layouts aus YAML-Dateien.

Referenz: /LF640/ — konfigurierbare Layout-Dateien.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Dict, List, Optional

import yaml

from blickfang.scanning.engine import ScanItem, ScanLayout, ScanRow

logger = logging.getLogger(__name__)

_LAYOUTS_DIR = Path(__file__).resolve().parents[3] / "config" / "layouts"


def load_layout(path: Path) -> ScanLayout:
    """Lädt ein Layout aus einer YAML-Datei.

    Args:
        path: Pfad zur Layout-Datei.

    Returns:
        ScanLayout-Objekt.
    """
    with open(path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f)

    layout = ScanLayout(
        name=data.get("name", path.stem),
        scan_speed_s=data.get("scan_speed_s", 1.5),
        max_cycles=data.get("max_cycles", 3),
        cancel_countdown_s=data.get("cancel_countdown_s", 2.5),
        speak_on_highlight=data.get("speak_on_highlight", True),
    )

    for row_data in data.get("rows", []):
        row = ScanRow(label=row_data.get("label", ""))
        for item_data in row_data.get("items", []):
            if isinstance(item_data, str):
                # Einfaches String-Item
                item = ScanItem(label=item_data, value=item_data.lower())
            else:
                item = ScanItem(
                    label=item_data.get("label", ""),
                    value=item_data.get("value", item_data.get("label", "")),
                    speak=item_data.get("speak", ""),
                    action=item_data.get("action", ""),
                    icon=item_data.get("icon", ""),
                    group=item_data.get("group", ""),
                )
            row.items.append(item)
        layout.rows.append(row)

    logger.info(f"Layout geladen: {layout.name} ({layout.row_count} Zeilen, {layout.total_items} Items)")
    return layout


def load_layout_by_name(name: str) -> Optional[ScanLayout]:
    """Lädt ein Layout nach Name.

    Args:
        name: Name der Layout-Datei (ohne .yaml).

    Returns:
        ScanLayout oder None wenn nicht gefunden.
    """
    path = _LAYOUTS_DIR / f"{name}.yaml"
    if path.exists():
        return load_layout(path)

    # Suche case-insensitive
    for p in _LAYOUTS_DIR.glob("*.yaml"):
        if p.stem.lower() == name.lower():
            return load_layout(p)

    logger.warning(f"Layout nicht gefunden: {name}")
    return None


def list_layouts() -> List[Dict[str, str]]:
    """Listet alle verfügbaren Layouts.

    Returns:
        Liste von Dicts mit 'name', 'path', 'description'.
    """
    layouts = []
    if not _LAYOUTS_DIR.exists():
        return layouts

    for path in sorted(_LAYOUTS_DIR.glob("*.yaml")):
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = yaml.safe_load(f)
            layouts.append({
                "name": data.get("name", path.stem),
                "path": str(path),
                "description": data.get("description", ""),
                "filename": path.stem,
            })
        except Exception as e:
            logger.warning(f"Layout-Fehler ({path}): {e}")

    return layouts


def get_keyboard_layout() -> ScanLayout:
    """Gibt das Standard-Tastatur-Layout zurück."""
    layout = load_layout_by_name("deutsch_frequenz")
    if layout:
        return layout

    # Fallback: einfaches ABC-Layout
    logger.warning("Kein Frequenz-Layout gefunden — verwende ABC-Fallback")
    return _create_abc_fallback()


def get_phrases_layout() -> ScanLayout:
    """Gibt das Phrasen-Layout zurück."""
    layout = load_layout_by_name("phrasen")
    if layout:
        return layout

    # Fallback: minimales Phrasen-Layout
    logger.warning("Kein Phrasen-Layout gefunden — verwende Minimal-Fallback")
    return _create_phrases_fallback()


def get_yesno_layout() -> ScanLayout:
    """Gibt ein einfaches Ja/Nein/Passe-Layout zurück."""
    layout = ScanLayout(
        name="Ja/Nein/Passe",
        scan_speed_s=2.0,
        max_cycles=3,
        cancel_countdown_s=2.5,
        speak_on_highlight=True,
    )
    row = ScanRow(label="Antwort")
    row.items = [
        ScanItem(label="JA", value="ja", speak="Ja"),
        ScanItem(label="NEIN", value="nein", speak="Nein"),
        ScanItem(label="PASSE", value="passe", speak="Passe"),
    ]
    layout.rows.append(row)
    return layout


def _create_abc_fallback() -> ScanLayout:
    """Erstellt ein einfaches ABC-Layout als Fallback."""
    layout = ScanLayout(name="ABC", scan_speed_s=1.5, max_cycles=3)

    alphabet = "ABCDEFGHIJKLMNOPQRSTUVWXYZÄÖÜ"
    row_size = 6

    for i in range(0, len(alphabet), row_size):
        chunk = alphabet[i:i + row_size]
        row = ScanRow(label=f"{chunk[0]}–{chunk[-1]}")
        for char in chunk:
            row.items.append(ScanItem(label=char, value=char.lower()))
        layout.rows.append(row)

    # Aktions-Zeile
    actions_row = ScanRow(label="Aktionen")
    actions_row.items = [
        ScanItem(label="␣", value=" ", speak="Leerzeichen", action="space"),
        ScanItem(label="⌫", value="", speak="Löschen", action="backspace"),
        ScanItem(label="🔊", value="", speak="Vorlesen", action="speak"),
        ScanItem(label="⌧", value="", speak="Alles löschen", action="clear"),
        ScanItem(label="🏠", value="", speak="Hauptmenü", action="home"),
    ]
    layout.rows.append(actions_row)

    return layout


def _create_phrases_fallback() -> ScanLayout:
    """Erstellt ein minimales Phrasen-Layout als Fallback."""
    layout = ScanLayout(name="Phrasen", scan_speed_s=2.0, max_cycles=3)

    row1 = ScanRow(label="Grundbedürfnisse")
    row1.items = [
        ScanItem(label="Durst", speak="Ich habe Durst"),
        ScanItem(label="Hunger", speak="Ich habe Hunger"),
        ScanItem(label="Toilette", speak="Ich muss auf die Toilette"),
        ScanItem(label="Schmerzen", speak="Ich habe Schmerzen"),
    ]
    layout.rows.append(row1)

    row2 = ScanRow(label="Soziales")
    row2.items = [
        ScanItem(label="Ja", speak="Ja"),
        ScanItem(label="Nein", speak="Nein"),
        ScanItem(label="Danke", speak="Danke"),
        ScanItem(label="Hilfe", speak="Ich brauche Hilfe", action="alarm"),
    ]
    layout.rows.append(row2)

    row3 = ScanRow(label="Navigation")
    row3.items = [
        ScanItem(label="Buchstabieren", speak="Buchstabieren", action="keyboard"),
        ScanItem(label="Hauptmenü", speak="Hauptmenü", action="home"),
    ]
    layout.rows.append(row3)

    return layout
