"""Kontextabhängige Wortvorschläge mit Lern-Fähigkeit.

Verbessert die Wortvorhersage durch:
- Bigram-Modell: Welches Wort folgt typischerweise auf welches?
- Nutzungs-Lernen: Häufig gewählte Wörter werden priorisiert
- Tageszeit-Kontext: Morgens andere Vorschläge als abends
- Recency-Bonus: Kürzlich genutzte Wörter erscheinen weiter oben
- Persistenz: Gelerntes wird in JSON gespeichert
"""

from __future__ import annotations

import json
import logging
import time
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)


class ContextPredictor:
    """Kontextabhängiger Wort-Prediktor mit Lern-Fähigkeit."""

    def __init__(self, person: str = "default", data_dir: Optional[Path] = None):
        self._person = person
        self._data_dir = data_dir or Path("data/predictions")
        self._data_dir.mkdir(parents=True, exist_ok=True)

        # Frequenz-Daten
        self._unigrams: Counter = Counter()       # Einzelwort-Häufigkeit
        self._bigrams: Dict[str, Counter] = defaultdict(Counter)  # Wort → Folgewort
        self._trigrams: Dict[str, Counter] = defaultdict(Counter)  # "w1 w2" → Folgewort
        self._time_context: Dict[str, Counter] = defaultdict(Counter)  # Tageszeit → Wort
        self._recent_words: List[str] = []        # Letzte 50 Wörter (Recency)

        # Lade gespeicherte Daten
        self._load()

    def predict(self, context: str, prefix: str = "", max_count: int = 6) -> List[str]:
        """Gibt kontextabhängige Wortvorschläge zurück.

        Args:
            context: Die letzten 1-2 Wörter als Kontext.
            prefix: Aktuell getippter Buchstaben-Anfang.
            max_count: Maximale Anzahl Vorschläge.

        Returns:
            Sortierte Liste von Wortvorschlägen.
        """
        candidates: Dict[str, float] = {}

        # 1. Trigram-Vorschläge (höchste Priorität)
        context_words = context.strip().lower().split()
        if len(context_words) >= 2:
            trigram_key = f"{context_words[-2]} {context_words[-1]}"
            for word, count in self._trigrams.get(trigram_key, {}).items():
                candidates[word] = candidates.get(word, 0) + count * 4.0

        # 2. Bigram-Vorschläge
        if context_words:
            last_word = context_words[-1]
            for word, count in self._bigrams.get(last_word, {}).items():
                candidates[word] = candidates.get(word, 0) + count * 2.0

        # 3. Unigram-Häufigkeit
        for word, count in self._unigrams.most_common(100):
            candidates[word] = candidates.get(word, 0) + count * 0.5

        # 4. Tageszeit-Kontext
        hour = datetime.now().hour
        if hour < 10:
            time_key = "morgen"
        elif hour < 14:
            time_key = "mittag"
        elif hour < 18:
            time_key = "nachmittag"
        else:
            time_key = "abend"

        for word, count in self._time_context.get(time_key, {}).items():
            candidates[word] = candidates.get(word, 0) + count * 1.0

        # 5. Recency-Bonus
        for i, word in enumerate(reversed(self._recent_words[-20:])):
            candidates[word] = candidates.get(word, 0) + (20 - i) * 0.3

        # Prefix-Filter
        if prefix:
            prefix_lower = prefix.lower()
            candidates = {w: s for w, s in candidates.items()
                         if w.startswith(prefix_lower) and w != prefix_lower}

        # Sortieren und zurückgeben
        sorted_candidates = sorted(candidates.items(), key=lambda x: -x[1])
        return [word for word, _ in sorted_candidates[:max_count]]

    def learn_word(self, word: str, context: str = "") -> None:
        """Lernt ein neues Wort aus der Nutzung.

        Args:
            word: Das gewählte Wort.
            context: Die vorherigen Wörter als Kontext.
        """
        word_lower = word.lower()

        # Unigram
        self._unigrams[word_lower] += 1

        # Bigram
        context_words = context.strip().lower().split()
        if context_words:
            self._bigrams[context_words[-1]][word_lower] += 1

        # Trigram
        if len(context_words) >= 2:
            trigram_key = f"{context_words[-2]} {context_words[-1]}"
            self._trigrams[trigram_key][word_lower] += 1

        # Tageszeit
        hour = datetime.now().hour
        if hour < 10:
            time_key = "morgen"
        elif hour < 14:
            time_key = "mittag"
        elif hour < 18:
            time_key = "nachmittag"
        else:
            time_key = "abend"
        self._time_context[time_key][word_lower] += 1

        # Recency
        self._recent_words.append(word_lower)
        if len(self._recent_words) > 50:
            self._recent_words = self._recent_words[-50:]

    def learn_sentence(self, sentence: str) -> None:
        """Lernt aus einem vollständigen Satz (alle Wort-Übergänge)."""
        words = sentence.strip().lower().split()
        for i, word in enumerate(words):
            context = " ".join(words[:i])
            self.learn_word(word, context)

    def save(self) -> None:
        """Speichert die gelernten Daten persistent."""
        data = {
            "person": self._person,
            "saved_at": datetime.now().isoformat(),
            "unigrams": dict(self._unigrams.most_common(500)),
            "bigrams": {k: dict(v.most_common(20)) for k, v in self._bigrams.items()},
            "trigrams": {k: dict(v.most_common(10)) for k, v in self._trigrams.items()},
            "time_context": {k: dict(v.most_common(30)) for k, v in self._time_context.items()},
            "recent_words": self._recent_words[-50:],
        }

        path = self._data_dir / f"{self._person}_predictions.json"
        path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        logger.info(f"Vorhersage-Daten gespeichert: {path}")

    def _load(self) -> None:
        """Lädt gespeicherte Vorhersage-Daten."""
        path = self._data_dir / f"{self._person}_predictions.json"
        if not path.exists():
            return

        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            self._unigrams = Counter(data.get("unigrams", {}))
            self._bigrams = defaultdict(Counter, {
                k: Counter(v) for k, v in data.get("bigrams", {}).items()
            })
            self._trigrams = defaultdict(Counter, {
                k: Counter(v) for k, v in data.get("trigrams", {}).items()
            })
            self._time_context = defaultdict(Counter, {
                k: Counter(v) for k, v in data.get("time_context", {}).items()
            })
            self._recent_words = data.get("recent_words", [])
            logger.info(f"Vorhersage-Daten geladen: {len(self._unigrams)} Wörter")
        except Exception as e:
            logger.error(f"Fehler beim Laden der Vorhersage-Daten: {e}")

    def get_stats(self) -> Dict[str, int]:
        """Gibt Statistiken über die gelernten Daten zurück."""
        return {
            "unique_words": len(self._unigrams),
            "total_words": sum(self._unigrams.values()),
            "bigram_pairs": sum(len(v) for v in self._bigrams.values()),
            "trigram_pairs": sum(len(v) for v in self._trigrams.values()),
        }
