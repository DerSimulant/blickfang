"""Text-Buffer und Wortvorhersage für Buchstaben-Scanning.

Der TextBuffer verwaltet den eingegebenen Text und bietet:
- Buchstabe hinzufügen/löschen
- Wort-Vorschläge basierend auf n-gram-Häufigkeiten
- Gesamttext für TTS-Ausgabe
"""

from __future__ import annotations

import logging
from collections import Counter
from pathlib import Path
from typing import Callable, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

# Die 500 häufigsten deutschen Wörter (Grundwortschatz)
_COMMON_WORDS = [
    "ich", "du", "er", "sie", "es", "wir", "ihr", "sie",
    "bin", "bist", "ist", "sind", "seid", "war", "habe", "hat", "haben",
    "will", "kann", "muss", "soll", "darf", "möchte", "werde",
    "ja", "nein", "nicht", "kein", "keine",
    "und", "oder", "aber", "weil", "wenn", "dass", "als", "wie",
    "der", "die", "das", "ein", "eine", "den", "dem", "des",
    "in", "an", "auf", "mit", "von", "zu", "für", "aus", "bei", "nach",
    "hier", "da", "dort", "jetzt", "heute", "morgen", "gestern",
    "gut", "schlecht", "schön", "groß", "klein", "viel", "wenig",
    "bitte", "danke", "hallo", "tschüss",
    "Wasser", "Essen", "Bett", "Schmerzen", "Hilfe", "Arzt", "Pflege",
    "Kopf", "Bauch", "Rücken", "Arm", "Bein", "Hand", "Fuß",
    "kalt", "warm", "müde", "Angst", "Durst", "Hunger",
    "mehr", "weniger", "noch", "schon", "wieder", "immer", "nie",
    "links", "rechts", "oben", "unten", "vorne", "hinten",
    "Mama", "Papa", "Familie", "Freund", "Freundin",
    "Fernseher", "Musik", "Buch", "Licht", "Fenster", "Tür",
    "Tag", "Nacht", "Morgen", "Abend", "Uhr", "Zeit",
    "liebe", "lieben", "mag", "mögen", "brauche", "brauchen",
    "gehen", "kommen", "machen", "sagen", "sehen", "hören",
    "wissen", "denken", "glauben", "fühlen", "verstehen",
    "etwas", "nichts", "alles", "jemand", "niemand",
    "wo", "wann", "warum", "was", "wer", "welche",
    "neue", "alte", "andere", "gleiche", "erste", "letzte",
    "Minute", "Stunde", "Woche", "Monat", "Jahr",
    "Nummer", "Name", "Telefon", "Adresse",
    "bald", "später", "früher", "langsam", "schnell",
    "leise", "laut", "hell", "dunkel", "nass", "trocken",
    "Medikament", "Tablette", "Tropfen", "Salbe", "Spritze",
    "Stuhl", "Rollstuhl", "Bett", "Tisch", "Lampe",
    "anziehen", "ausziehen", "waschen", "essen", "trinken", "schlafen",
    "umdrehen", "aufsetzen", "hinlegen", "aufstehen",
    "Brille", "Hörgerät", "Zahnprothese",
    "draußen", "drinnen", "Garten", "Balkon", "Zimmer",
    "Besuch", "Termin", "Ausflug",
    "fertig", "bereit", "okay", "genug", "stop",
]


class TextBuffer:
    """Verwaltet den eingegebenen Text beim Buchstabieren."""

    def __init__(self, on_change: Optional[Callable[[str], None]] = None):
        self._text: str = ""
        self._on_change = on_change
        self._word_frequencies: Counter = Counter()
        self._history: List[str] = []  # Für Undo

        # Wortfrequenzen initialisieren
        self._init_word_frequencies()

    @property
    def text(self) -> str:
        return self._text

    @property
    def current_word(self) -> str:
        """Das aktuell begonnene Wort (nach dem letzten Leerzeichen)."""
        if not self._text:
            return ""
        parts = self._text.split(" ")
        return parts[-1] if parts else ""

    @property
    def display_text(self) -> str:
        """Text für die Anzeige (mit Cursor)."""
        return self._text + "▌"

    def add_char(self, char: str) -> None:
        """Fügt einen Buchstaben hinzu."""
        self._history.append(self._text)
        self._text += char
        self._notify()

    def add_space(self) -> None:
        """Fügt ein Leerzeichen hinzu und lernt das Wort."""
        word = self.current_word
        if word:
            self._word_frequencies[word.lower()] += 1
        self._history.append(self._text)
        self._text += " "
        self._notify()

    def backspace(self) -> None:
        """Löscht den letzten Buchstaben."""
        if self._text:
            self._history.append(self._text)
            self._text = self._text[:-1]
            self._notify()

    def clear(self) -> None:
        """Löscht den gesamten Text."""
        if self._text:
            self._history.append(self._text)
            self._text = ""
            self._notify()

    def complete_word(self, word: str) -> None:
        """Vervollständigt das aktuelle Wort."""
        current = self.current_word
        if current and word.lower().startswith(current.lower()):
            # Rest des Wortes einfügen
            rest = word[len(current):]
            self._history.append(self._text)
            self._text += rest + " "
            self._word_frequencies[word.lower()] += 1
            self._notify()
        else:
            # Ganzes Wort einfügen
            self._history.append(self._text)
            self._text += word + " "
            self._word_frequencies[word.lower()] += 1
            self._notify()

    def undo(self) -> None:
        """Macht die letzte Aktion rückgängig."""
        if self._history:
            self._text = self._history.pop()
            self._notify()

    def get_predictions(self, max_count: int = 5) -> List[str]:
        """Gibt Wortvorschläge basierend auf dem aktuellen Präfix.

        Args:
            max_count: Maximale Anzahl Vorschläge.

        Returns:
            Liste von Wortvorschlägen.
        """
        prefix = self.current_word.lower()
        if not prefix:
            # Ohne Präfix: häufigste Wörter
            return [w for w, _ in self._word_frequencies.most_common(max_count)]

        # Wörter die mit dem Präfix beginnen, sortiert nach Häufigkeit
        matches = []
        for word, count in self._word_frequencies.items():
            if word.startswith(prefix) and word != prefix:
                matches.append((word, count))

        # Nach Häufigkeit sortieren
        matches.sort(key=lambda x: -x[1])

        return [w for w, _ in matches[:max_count]]

    def _init_word_frequencies(self) -> None:
        """Initialisiert Wortfrequenzen mit Grundwortschatz."""
        for i, word in enumerate(_COMMON_WORDS):
            # Häufigere Wörter bekommen höheren Startwert
            self._word_frequencies[word.lower()] = max(1, len(_COMMON_WORDS) - i)

    def _notify(self) -> None:
        """Benachrichtigt über Textänderung."""
        if self._on_change:
            self._on_change(self._text)

    def get_full_text_for_speech(self) -> str:
        """Gibt den vollständigen Text für TTS-Ausgabe zurück."""
        return self._text.strip()
