"""Persönliches Wörterbuch: Häufig genutzte Wörter priorisieren, Import/Export.

Jede Person hat ein eigenes Wörterbuch das:
- Automatisch aus der Nutzung lernt (häufig gewählte Wörter steigen auf)
- Manuell erweitert werden kann (Betreuer fügt Wörter hinzu)
- Exportiert/importiert werden kann (Backup, Therapeuten-Austausch)
- Kategorien unterstützt (Personen, Orte, Aktivitäten, Medizin)
"""

from __future__ import annotations

import json
import logging
from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Set

logger = logging.getLogger(__name__)


@dataclass
class DictionaryEntry:
    """Ein Eintrag im persönlichen Wörterbuch."""
    word: str
    category: str = "allgemein"
    usage_count: int = 0
    added_at: str = ""
    last_used: str = ""
    is_favorite: bool = False
    notes: str = ""  # z.B. "Name der Schwester"

    def __post_init__(self):
        if not self.added_at:
            self.added_at = datetime.now().isoformat()

    def to_dict(self) -> Dict[str, Any]:
        return {
            "word": self.word,
            "category": self.category,
            "usage_count": self.usage_count,
            "added_at": self.added_at,
            "last_used": self.last_used,
            "is_favorite": self.is_favorite,
            "notes": self.notes,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "DictionaryEntry":
        return cls(
            word=data.get("word", ""),
            category=data.get("category", "allgemein"),
            usage_count=data.get("usage_count", 0),
            added_at=data.get("added_at", ""),
            last_used=data.get("last_used", ""),
            is_favorite=data.get("is_favorite", False),
            notes=data.get("notes", ""),
        )


class PersonalDictionary:
    """Persönliches Wörterbuch pro Person."""

    # Standard-Kategorien
    CATEGORIES = [
        "allgemein",
        "personen",
        "orte",
        "aktivitaeten",
        "medizin",
        "essen_trinken",
        "gefuehle",
        "koerper",
        "gegenstaende",
    ]

    CATEGORY_LABELS = {
        "allgemein": "Allgemein",
        "personen": "Personen",
        "orte": "Orte",
        "aktivitaeten": "Aktivitäten",
        "medizin": "Medizin",
        "essen_trinken": "Essen & Trinken",
        "gefuehle": "Gefühle",
        "koerper": "Körper",
        "gegenstaende": "Gegenstände",
    }

    def __init__(self, person: str = "default", data_dir: Optional[Path] = None):
        self._person = person
        self._data_dir = data_dir or Path("data/dictionaries")
        self._data_dir.mkdir(parents=True, exist_ok=True)
        self._entries: Dict[str, DictionaryEntry] = {}

        self._load()

    @property
    def person(self) -> str:
        return self._person

    @property
    def size(self) -> int:
        return len(self._entries)

    def add_word(self, word: str, category: str = "allgemein",
                 notes: str = "", is_favorite: bool = False) -> DictionaryEntry:
        """Fügt ein Wort zum Wörterbuch hinzu."""
        key = word.lower()
        if key in self._entries:
            # Existiert bereits — aktualisieren
            entry = self._entries[key]
            if category != "allgemein":
                entry.category = category
            if notes:
                entry.notes = notes
            if is_favorite:
                entry.is_favorite = True
        else:
            entry = DictionaryEntry(
                word=word,
                category=category,
                notes=notes,
                is_favorite=is_favorite,
            )
            self._entries[key] = entry

        return entry

    def remove_word(self, word: str) -> bool:
        """Entfernt ein Wort aus dem Wörterbuch."""
        key = word.lower()
        if key in self._entries:
            del self._entries[key]
            return True
        return False

    def record_usage(self, word: str) -> None:
        """Zeichnet die Nutzung eines Wortes auf."""
        key = word.lower()
        if key in self._entries:
            self._entries[key].usage_count += 1
            self._entries[key].last_used = datetime.now().isoformat()
        else:
            # Automatisch hinzufügen
            entry = DictionaryEntry(word=word, usage_count=1)
            entry.last_used = datetime.now().isoformat()
            self._entries[key] = entry

    def get_words(self, category: Optional[str] = None,
                  favorites_only: bool = False,
                  min_usage: int = 0) -> List[DictionaryEntry]:
        """Gibt Wörterbuch-Einträge zurück, gefiltert und sortiert."""
        entries = list(self._entries.values())

        if category:
            entries = [e for e in entries if e.category == category]
        if favorites_only:
            entries = [e for e in entries if e.is_favorite]
        if min_usage > 0:
            entries = [e for e in entries if e.usage_count >= min_usage]

        # Sortierung: Favoriten zuerst, dann nach Nutzungshäufigkeit
        entries.sort(key=lambda e: (-int(e.is_favorite), -e.usage_count))
        return entries

    def get_top_words(self, count: int = 20, category: Optional[str] = None) -> List[str]:
        """Gibt die meistgenutzten Wörter zurück."""
        entries = self.get_words(category=category)
        return [e.word for e in entries[:count]]

    def search(self, prefix: str, max_count: int = 10) -> List[DictionaryEntry]:
        """Sucht Wörter die mit dem Präfix beginnen."""
        prefix_lower = prefix.lower()
        matches = [e for e in self._entries.values()
                   if e.word.lower().startswith(prefix_lower)]
        matches.sort(key=lambda e: (-int(e.is_favorite), -e.usage_count))
        return matches[:max_count]

    def get_categories_with_counts(self) -> Dict[str, int]:
        """Gibt Kategorien mit Anzahl der Einträge zurück."""
        counts: Dict[str, int] = {}
        for entry in self._entries.values():
            counts[entry.category] = counts.get(entry.category, 0) + 1
        return counts

    def save(self) -> None:
        """Speichert das Wörterbuch persistent."""
        data = {
            "person": self._person,
            "saved_at": datetime.now().isoformat(),
            "version": 1,
            "entries": [e.to_dict() for e in self._entries.values()],
        }
        path = self._data_dir / f"{self._person}_dictionary.json"
        path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        logger.info(f"Wörterbuch gespeichert: {path} ({self.size} Einträge)")

    def _load(self) -> None:
        """Lädt das gespeicherte Wörterbuch."""
        path = self._data_dir / f"{self._person}_dictionary.json"
        if not path.exists():
            self._load_defaults()
            return

        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            for entry_data in data.get("entries", []):
                entry = DictionaryEntry.from_dict(entry_data)
                self._entries[entry.word.lower()] = entry
            logger.info(f"Wörterbuch geladen: {self.size} Einträge")
        except Exception as e:
            logger.error(f"Fehler beim Laden des Wörterbuchs: {e}")
            self._load_defaults()

    def _load_defaults(self) -> None:
        """Lädt Standard-Wörter für ein neues Wörterbuch."""
        defaults = {
            "personen": [
                "Mama", "Papa", "Schwester", "Bruder", "Oma", "Opa",
                "Pfleger", "Pflegerin", "Arzt", "Ärztin", "Therapeut",
            ],
            "medizin": [
                "Schmerzmittel", "Tablette", "Tropfen", "Spritze",
                "Pflaster", "Salbe", "Medikament",
            ],
            "essen_trinken": [
                "Wasser", "Tee", "Kaffee", "Saft", "Milch",
                "Brot", "Suppe", "Obst", "Joghurt",
            ],
            "gefuehle": [
                "müde", "wach", "traurig", "froh", "ängstlich",
                "gelangweilt", "einsam", "zufrieden", "frustriert",
            ],
            "koerper": [
                "Kopf", "Rücken", "Bauch", "Bein", "Arm",
                "Hand", "Fuß", "Schulter", "Nacken", "Brust",
            ],
            "gegenstaende": [
                "Brille", "Fernseher", "Telefon", "Buch", "Decke",
                "Kissen", "Rollstuhl", "Hörgerät",
            ],
            "orte": [
                "Bett", "Badezimmer", "Küche", "Garten", "Balkon",
                "Wohnzimmer", "draußen",
            ],
            "aktivitaeten": [
                "schlafen", "essen", "trinken", "lesen", "fernsehen",
                "Musik hören", "spazieren", "reden",
            ],
        }

        for category, words in defaults.items():
            for word in words:
                self._entries[word.lower()] = DictionaryEntry(
                    word=word,
                    category=category,
                    usage_count=1,
                )

    def export_to_file(self, path: Path) -> None:
        """Exportiert das Wörterbuch als lesbare Textdatei."""
        lines = []
        lines.append(f"Persönliches Wörterbuch: {self._person}")
        lines.append(f"Exportiert: {datetime.now().strftime('%Y-%m-%d %H:%M')}")
        lines.append(f"Einträge: {self.size}")
        lines.append("=" * 50)
        lines.append("")

        for category in self.CATEGORIES:
            entries = self.get_words(category=category)
            if not entries:
                continue

            label = self.CATEGORY_LABELS.get(category, category)
            lines.append(f"--- {label} ---")
            for entry in entries:
                fav = "★" if entry.is_favorite else " "
                notes = f" ({entry.notes})" if entry.notes else ""
                lines.append(f"  {fav} {entry.word} [{entry.usage_count}x]{notes}")
            lines.append("")

        path.write_text("\n".join(lines), encoding="utf-8")

    def import_from_file(self, path: Path) -> int:
        """Importiert Wörter aus einer Textdatei (ein Wort pro Zeile oder JSON)."""
        text = path.read_text(encoding="utf-8")
        count = 0

        # Versuche JSON
        try:
            data = json.loads(text)
            for entry_data in data.get("entries", []):
                entry = DictionaryEntry.from_dict(entry_data)
                self._entries[entry.word.lower()] = entry
                count += 1
            return count
        except (json.JSONDecodeError, AttributeError):
            pass

        # Einfache Textdatei (ein Wort pro Zeile)
        for line in text.strip().split("\n"):
            line = line.strip()
            if not line or line.startswith("#") or line.startswith("=") or line.startswith("-"):
                continue
            # Bereinigen (★ und Nutzungszähler entfernen)
            word = line.lstrip("★ ").split("[")[0].strip()
            if word and len(word) > 1:
                self.add_word(word)
                count += 1

        return count
