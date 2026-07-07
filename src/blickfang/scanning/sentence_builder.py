"""Satz-Builder: Grammatik-Engine für Subjekt → Verb → Objekt Konstruktion.

Ermöglicht es dem Nutzer, Sätze aus vordefinierten Bausteinen zusammenzusetzen,
statt jeden Buchstaben einzeln zu scannen. Deutlich schneller für Alltagskommunikation.

Architektur:
  - Slot-basiert: Jeder Satz hat Slots (Subjekt, Verb, Objekt, Ergänzung)
  - Kategorien pro Slot: z.B. Subjekt → "Ich", "Du", "Er/Sie", "Wir"
  - Kontext-sensitiv: Verfügbare Verben/Objekte hängen vom gewählten Subjekt ab
  - Erweiterbar: Neue Wörter/Kategorien per YAML-Konfiguration
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import yaml

logger = logging.getLogger(__name__)


class SlotType(str, Enum):
    """Satz-Slot-Typen."""
    SUBJECT = "subjekt"
    VERB = "verb"
    OBJECT = "objekt"
    COMPLEMENT = "ergaenzung"
    TIME = "zeit"
    PLACE = "ort"


@dataclass
class Word:
    """Ein Wort/Phrase im Satz-Builder."""
    text: str
    display: str = ""  # Anzeige-Text (kann kürzer sein)
    icon: str = ""
    category: str = ""
    conjugations: Dict[str, str] = field(default_factory=dict)  # z.B. {"ich": "möchte", "du": "möchtest"}

    def __post_init__(self):
        if not self.display:
            self.display = self.text


@dataclass
class Slot:
    """Ein Slot im Satz-Template."""
    slot_type: SlotType
    label: str
    words: List[Word] = field(default_factory=list)
    optional: bool = False
    selected: Optional[Word] = None


@dataclass
class SentenceTemplate:
    """Ein Satz-Template mit Slots."""
    name: str
    slots: List[Slot] = field(default_factory=list)
    description: str = ""


class SentenceBuilder:
    """Hauptklasse für den Satz-Builder.

    Verwaltet Templates, aktuelle Auswahl und generiert den fertigen Satz.
    """

    def __init__(self, vocabulary_path: Optional[Path] = None):
        self._templates: List[SentenceTemplate] = []
        self._active_template: Optional[SentenceTemplate] = None
        self._current_slot_idx: int = 0
        self._built_sentence: str = ""

        # Standard-Vokabular laden
        if vocabulary_path and vocabulary_path.exists():
            self._load_vocabulary(vocabulary_path)
        else:
            self._load_default_vocabulary()

    def _load_vocabulary(self, path: Path) -> None:
        """Lädt Vokabular aus YAML-Datei."""
        try:
            data = yaml.safe_load(path.read_text(encoding="utf-8"))
            self._parse_vocabulary(data)
        except Exception as e:
            logger.error(f"Fehler beim Laden des Vokabulars: {e}")
            self._load_default_vocabulary()

    def _parse_vocabulary(self, data: Dict[str, Any]) -> None:
        """Parst Vokabular-Daten aus YAML."""
        for template_data in data.get("templates", []):
            template = SentenceTemplate(
                name=template_data.get("name", ""),
                description=template_data.get("description", ""),
            )
            for slot_data in template_data.get("slots", []):
                slot = Slot(
                    slot_type=SlotType(slot_data.get("type", "subjekt")),
                    label=slot_data.get("label", ""),
                    optional=slot_data.get("optional", False),
                )
                for word_data in slot_data.get("words", []):
                    if isinstance(word_data, str):
                        slot.words.append(Word(text=word_data))
                    else:
                        slot.words.append(Word(
                            text=word_data.get("text", ""),
                            display=word_data.get("display", ""),
                            icon=word_data.get("icon", ""),
                            category=word_data.get("category", ""),
                            conjugations=word_data.get("conjugations", {}),
                        ))
                template.slots.append(slot)
            self._templates.append(template)

    def _load_default_vocabulary(self) -> None:
        """Lädt das Standard-Vokabular für deutsche Alltagskommunikation."""

        # Template 1: Bedürfnis-Satz (Ich möchte/brauche...)
        beduerfnis = SentenceTemplate(
            name="Bedürfnis",
            description="Ich möchte/brauche etwas",
        )
        beduerfnis.slots = [
            Slot(
                slot_type=SlotType.SUBJECT,
                label="Wer",
                words=[
                    Word(text="Ich", icon="👤"),
                    Word(text="Wir", icon="👥"),
                ],
            ),
            Slot(
                slot_type=SlotType.VERB,
                label="Was tun",
                words=[
                    Word(text="möchte", icon="💭", conjugations={"Ich": "möchte", "Wir": "möchten"}),
                    Word(text="brauche", icon="❗", conjugations={"Ich": "brauche", "Wir": "brauchen"}),
                    Word(text="hätte gerne", icon="🙏", conjugations={"Ich": "hätte gerne", "Wir": "hätten gerne"}),
                    Word(text="will", icon="💪", conjugations={"Ich": "will", "Wir": "wollen"}),
                ],
            ),
            Slot(
                slot_type=SlotType.OBJECT,
                label="Was",
                words=[
                    Word(text="Wasser", icon="💧", category="Trinken"),
                    Word(text="Tee", icon="🍵", category="Trinken"),
                    Word(text="Kaffee", icon="☕", category="Trinken"),
                    Word(text="etwas zu essen", icon="🍽", category="Essen"),
                    Word(text="Hilfe", icon="🆘", category="Hilfe"),
                    Word(text="Ruhe", icon="🤫", category="Zustand"),
                    Word(text="Gesellschaft", icon="👋", category="Sozial"),
                    Word(text="frische Luft", icon="🌬", category="Zustand"),
                    Word(text="eine Decke", icon="🛏", category="Komfort"),
                    Word(text="Schmerzmittel", icon="💊", category="Medizin"),
                    Word(text="auf die Toilette", icon="🚽", category="Körper"),
                    Word(text="mich hinlegen", icon="🛌", category="Körper"),
                    Word(text="aufstehen", icon="🧍", category="Körper"),
                    Word(text="Musik hören", icon="🎵", category="Unterhaltung"),
                    Word(text="fernsehen", icon="📺", category="Unterhaltung"),
                ],
            ),
        ]

        # Template 2: Befinden (Mir geht es...)
        befinden = SentenceTemplate(
            name="Befinden",
            description="Wie es mir geht",
        )
        befinden.slots = [
            Slot(
                slot_type=SlotType.SUBJECT,
                label="Wer",
                words=[
                    Word(text="Mir", icon="👤"),
                    Word(text="Uns", icon="👥"),
                ],
            ),
            Slot(
                slot_type=SlotType.VERB,
                label="Zustand",
                words=[
                    Word(text="geht es", icon="📊"),
                    Word(text="ist", icon="📊"),
                    Word(text="tut etwas", icon="😣"),
                ],
            ),
            Slot(
                slot_type=SlotType.COMPLEMENT,
                label="Wie",
                words=[
                    Word(text="gut", icon="😊", category="Positiv"),
                    Word(text="besser", icon="📈", category="Positiv"),
                    Word(text="nicht gut", icon="😔", category="Negativ"),
                    Word(text="schlecht", icon="😢", category="Negativ"),
                    Word(text="kalt", icon="🥶", category="Temperatur"),
                    Word(text="warm", icon="🥵", category="Temperatur"),
                    Word(text="langweilig", icon="😐", category="Gefühl"),
                    Word(text="einsam", icon="😞", category="Gefühl"),
                    Word(text="müde", icon="😴", category="Gefühl"),
                    Word(text="weh", icon="😣", category="Schmerz"),
                ],
            ),
            Slot(
                slot_type=SlotType.PLACE,
                label="Wo (Schmerz)",
                optional=True,
                words=[
                    Word(text="am Kopf", icon="🤕", category="Kopf"),
                    Word(text="im Rücken", icon="🔙", category="Rücken"),
                    Word(text="im Bauch", icon="🤢", category="Bauch"),
                    Word(text="in den Beinen", icon="🦵", category="Beine"),
                    Word(text="in der Brust", icon="💔", category="Brust"),
                    Word(text="überall", icon="😰", category="Allgemein"),
                ],
            ),
        ]

        # Template 3: Frage/Bitte
        frage = SentenceTemplate(
            name="Frage/Bitte",
            description="Kann jemand etwas tun?",
        )
        frage.slots = [
            Slot(
                slot_type=SlotType.SUBJECT,
                label="An wen",
                words=[
                    Word(text="Kannst du", icon="👤"),
                    Word(text="Können Sie", icon="👔"),
                    Word(text="Bitte", icon="🙏"),
                ],
            ),
            Slot(
                slot_type=SlotType.VERB,
                label="Was tun",
                words=[
                    Word(text="das Fenster öffnen", icon="🪟"),
                    Word(text="das Licht anmachen", icon="💡"),
                    Word(text="das Licht ausmachen", icon="🌙"),
                    Word(text="die Tür schließen", icon="🚪"),
                    Word(text="leiser sein", icon="🤫"),
                    Word(text="lauter sprechen", icon="🔊"),
                    Word(text="nochmal sagen", icon="🔁"),
                    Word(text="mir helfen", icon="🤝"),
                    Word(text="jemanden rufen", icon="📞"),
                    Word(text="den Arzt rufen", icon="👨‍⚕️"),
                    Word(text="mich zudecken", icon="🛏"),
                    Word(text="mich umlagern", icon="🔄"),
                    Word(text="den Fernseher anmachen", icon="📺"),
                    Word(text="den Fernseher ausmachen", icon="📺"),
                ],
            ),
        ]

        # Template 4: Soziales
        soziales = SentenceTemplate(
            name="Soziales",
            description="Soziale Kommunikation",
        )
        soziales.slots = [
            Slot(
                slot_type=SlotType.SUBJECT,
                label="Aussage",
                words=[
                    Word(text="Danke", icon="🙏"),
                    Word(text="Bitte", icon="😊"),
                    Word(text="Entschuldigung", icon="😅"),
                    Word(text="Ja, gerne", icon="👍"),
                    Word(text="Nein, danke", icon="👎"),
                    Word(text="Ich liebe dich", icon="❤️"),
                    Word(text="Guten Morgen", icon="🌅"),
                    Word(text="Gute Nacht", icon="🌙"),
                    Word(text="Wie geht es dir?", icon="💬"),
                    Word(text="Das ist schön", icon="😊"),
                    Word(text="Das gefällt mir nicht", icon="😕"),
                    Word(text="Ich bin froh", icon="😃"),
                    Word(text="Ich bin traurig", icon="😢"),
                    Word(text="Ich habe Angst", icon="😨"),
                    Word(text="Alles gut", icon="👌"),
                ],
            ),
        ]

        # Template 5: Zeit-Angaben
        zeit = SentenceTemplate(
            name="Wann",
            description="Zeitliche Angaben",
        )
        zeit.slots = [
            Slot(
                slot_type=SlotType.TIME,
                label="Wann",
                words=[
                    Word(text="Jetzt", icon="⏰"),
                    Word(text="Gleich", icon="🔜"),
                    Word(text="Später", icon="⏳"),
                    Word(text="Morgen", icon="📅"),
                    Word(text="Heute Abend", icon="🌆"),
                    Word(text="Nicht jetzt", icon="🚫"),
                ],
            ),
        ]

        self._templates = [beduerfnis, befinden, frage, soziales, zeit]

    @property
    def templates(self) -> List[SentenceTemplate]:
        """Alle verfügbaren Satz-Templates."""
        return self._templates

    @property
    def active_template(self) -> Optional[SentenceTemplate]:
        """Das aktuell aktive Template."""
        return self._active_template

    @property
    def current_slot(self) -> Optional[Slot]:
        """Der aktuelle Slot."""
        if self._active_template and self._current_slot_idx < len(self._active_template.slots):
            return self._active_template.slots[self._current_slot_idx]
        return None

    @property
    def current_slot_index(self) -> int:
        """Index des aktuellen Slots."""
        return self._current_slot_idx

    @property
    def total_slots(self) -> int:
        """Gesamtzahl der Slots im aktiven Template."""
        if self._active_template:
            return len(self._active_template.slots)
        return 0

    @property
    def is_complete(self) -> bool:
        """Ob alle Pflicht-Slots ausgefüllt sind."""
        if not self._active_template:
            return False
        for slot in self._active_template.slots:
            if not slot.optional and slot.selected is None:
                return False
        return True

    def select_template(self, index: int) -> Optional[SentenceTemplate]:
        """Wählt ein Template aus."""
        if 0 <= index < len(self._templates):
            self._active_template = self._templates[index]
            self._current_slot_idx = 0
            # Alle Slots zurücksetzen
            for slot in self._active_template.slots:
                slot.selected = None
            return self._active_template
        return None

    def select_word(self, word_index: int) -> Optional[Word]:
        """Wählt ein Wort für den aktuellen Slot."""
        slot = self.current_slot
        if slot and 0 <= word_index < len(slot.words):
            slot.selected = slot.words[word_index]
            return slot.selected
        return None

    def advance_slot(self) -> bool:
        """Geht zum nächsten Slot. Gibt True zurück wenn erfolgreich."""
        if self._active_template:
            if self._current_slot_idx < len(self._active_template.slots) - 1:
                self._current_slot_idx += 1
                return True
        return False

    def skip_slot(self) -> bool:
        """Überspringt den aktuellen Slot (nur wenn optional)."""
        slot = self.current_slot
        if slot and slot.optional:
            return self.advance_slot()
        return False

    def previous_slot(self) -> bool:
        """Geht zum vorherigen Slot zurück."""
        if self._current_slot_idx > 0:
            self._current_slot_idx -= 1
            return True
        return False

    def build_sentence(self) -> str:
        """Baut den Satz aus den gewählten Wörtern zusammen."""
        if not self._active_template:
            return ""

        parts = []
        subject_text = ""

        for slot in self._active_template.slots:
            if slot.selected is None:
                continue

            word = slot.selected

            # Konjugation anwenden wenn verfügbar
            if word.conjugations and subject_text:
                conjugated = word.conjugations.get(subject_text, word.text)
                parts.append(conjugated)
            else:
                parts.append(word.text)

            # Subjekt merken für Konjugation
            if slot.slot_type == SlotType.SUBJECT:
                subject_text = word.text

        self._built_sentence = " ".join(parts)

        # Satzzeichen hinzufügen
        if self._built_sentence and not self._built_sentence[-1] in ".!?":
            # Fragen erkennen
            if any(w in self._built_sentence.lower() for w in ["kannst", "können", "wie"]):
                self._built_sentence += "?"
            else:
                self._built_sentence += "."

        return self._built_sentence

    def reset(self) -> None:
        """Setzt den Builder komplett zurück."""
        self._active_template = None
        self._current_slot_idx = 0
        self._built_sentence = ""

    def get_layout_for_scanning(self) -> Dict[str, Any]:
        """Generiert ein Scanning-Layout für den aktuellen Zustand.

        Gibt ein Layout zurück das vom Scanning-Framework dargestellt werden kann.
        """
        # Template-Auswahl
        if not self._active_template:
            rows = []
            for i, template in enumerate(self._templates):
                rows.append({
                    "items": [{"label": template.name, "icon": "", "action": f"template:{i}"}]
                })
            return {
                "title": "Satz-Builder: Kategorie wählen",
                "rows": rows,
            }

        # Slot-Auswahl
        slot = self.current_slot
        if not slot:
            # Alle Slots ausgefüllt → Vorschau
            sentence = self.build_sentence()
            return {
                "title": f"Satz: {sentence}",
                "rows": [
                    {"items": [
                        {"label": "Sprechen", "icon": "🔊", "action": "speak"},
                        {"label": "Ändern", "icon": "✏️", "action": "edit"},
                        {"label": "Abbrechen", "icon": "❌", "action": "cancel"},
                    ]}
                ],
            }

        # Wörter für aktuellen Slot anzeigen
        # In Zeilen à 4 aufteilen
        items_per_row = 4
        rows = []
        current_row_items = []

        for i, word in enumerate(slot.words):
            current_row_items.append({
                "label": word.display or word.text,
                "icon": word.icon,
                "action": f"word:{i}",
            })
            if len(current_row_items) >= items_per_row:
                rows.append({"items": current_row_items})
                current_row_items = []

        if current_row_items:
            rows.append({"items": current_row_items})

        # Optionaler Slot: Überspringen-Option
        if slot.optional:
            rows.append({"items": [
                {"label": "Überspringen", "icon": "⏭", "action": "skip"},
            ]})

        # Fortschritts-Anzeige
        progress_parts = []
        for s in self._active_template.slots:
            if s.selected:
                progress_parts.append(s.selected.display or s.selected.text)
            elif s == slot:
                progress_parts.append(f"[{s.label}?]")
            else:
                progress_parts.append(f"({s.label})")

        title = " ".join(progress_parts)

        return {
            "title": title,
            "rows": rows,
            "slot_index": self._current_slot_idx,
            "total_slots": len(self._active_template.slots),
        }
