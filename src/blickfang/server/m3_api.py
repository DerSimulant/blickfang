"""M3 API-Endpunkte: Satz-Builder, Wörterbuch, Vorhersagen.

Stellt REST-Endpunkte für die M3-Module bereit:
- /api/sentence-builder/* — Satz-Builder Steuerung
- /api/dictionary/* — Persönliches Wörterbuch
- /api/predictions/* — Kontextabhängige Vorschläge
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, Dict, Optional

from fastapi import APIRouter, UploadFile, File
from fastapi.responses import Response
from pydantic import BaseModel

logger = logging.getLogger(__name__)

router = APIRouter()

# ─── Globale Instanzen (lazy init) ──────────────────────────────────────

_sentence_builder = None
_dictionary = None
_predictor = None
_current_person = "default"


def _get_sentence_builder():
    global _sentence_builder
    if _sentence_builder is None:
        from blickfang.scanning.sentence_builder import SentenceBuilder
        vocab_path = Path(__file__).resolve().parents[3] / "config" / "layouts" / "vocabulary.yaml"
        _sentence_builder = SentenceBuilder(vocabulary_path=vocab_path if vocab_path.exists() else None)
    return _sentence_builder


def _get_dictionary(person: str = None):
    global _dictionary, _current_person
    person = person or _current_person
    if _dictionary is None or _current_person != person:
        from blickfang.scanning.dictionary import PersonalDictionary
        data_dir = Path(__file__).resolve().parents[3] / "data" / "dictionaries"
        _dictionary = PersonalDictionary(person=person, data_dir=data_dir)
        _current_person = person
    return _dictionary


def _get_predictor(person: str = None):
    global _predictor, _current_person
    person = person or _current_person
    if _predictor is None or _current_person != person:
        from blickfang.scanning.predictor import ContextPredictor
        data_dir = Path(__file__).resolve().parents[3] / "data" / "predictions"
        _predictor = ContextPredictor(person=person, data_dir=data_dir)
        _current_person = person
    return _predictor


# ─── Satz-Builder Endpunkte ──────────────────────────────────────────────


@router.get("/api/sentence-builder/templates")
async def get_templates():
    """Gibt alle verfügbaren Satz-Templates zurück."""
    sb = _get_sentence_builder()
    templates = []
    for t in sb.templates:
        slots = []
        for s in t.slots:
            words = [{"text": w.text, "display": w.display, "icon": w.icon, "category": w.category}
                     for w in s.words]
            slots.append({
                "label": s.label,
                "slot_type": s.slot_type.value,
                "words": words,
                "optional": s.optional,
                "selected": None,
            })
        templates.append({
            "name": t.name,
            "description": t.description,
            "slots": slots,
        })
    return {"templates": templates}


class TemplateSelectRequest(BaseModel):
    index: int


@router.post("/api/sentence-builder/select-template")
async def select_template(req: TemplateSelectRequest):
    """Wählt ein Satz-Template aus."""
    sb = _get_sentence_builder()
    template = sb.select_template(req.index)
    if template:
        slot = sb.current_slot
        return {
            "status": "ok",
            "template": {
                "name": template.name,
                "slots": [{"label": s.label, "slot_type": s.slot_type.value,
                           "words": [{"text": w.text, "display": w.display, "icon": w.icon}
                                     for w in s.words],
                           "optional": s.optional, "selected": None}
                          for s in template.slots],
            },
            "current_slot": slot.label if slot else None,
        }
    return {"error": "Ungültiger Template-Index"}


class WordSelectRequest(BaseModel):
    word_index: int


@router.post("/api/sentence-builder/select-word")
async def select_word(req: WordSelectRequest):
    """Wählt ein Wort für den aktuellen Slot."""
    sb = _get_sentence_builder()
    word = sb.select_word(req.word_index)
    if word:
        # Zum nächsten Slot
        has_next = sb.advance_slot()
        if not has_next or sb.is_complete:
            sentence = sb.build_sentence()
            # Lernen
            predictor = _get_predictor()
            predictor.learn_sentence(sentence)
            predictor.save()
            return {"status": "ok", "word": word.text, "complete": True, "sentence": sentence}
        return {"status": "ok", "word": word.text, "complete": False}
    return {"error": "Ungültiger Wort-Index"}


@router.post("/api/sentence-builder/skip")
async def skip_slot():
    """Überspringt den aktuellen optionalen Slot."""
    sb = _get_sentence_builder()
    if sb.skip_slot():
        if sb.is_complete:
            sentence = sb.build_sentence()
            return {"status": "ok", "complete": True, "sentence": sentence}
        return {"status": "ok", "complete": False}
    return {"error": "Slot kann nicht übersprungen werden"}


@router.get("/api/sentence-builder/build")
async def build_sentence():
    """Baut den Satz aus den gewählten Wörtern."""
    sb = _get_sentence_builder()
    sentence = sb.build_sentence()
    return {"sentence": sentence}


@router.post("/api/sentence-builder/speak")
async def speak_sentence():
    """Spricht den gebauten Satz per TTS."""
    sb = _get_sentence_builder()
    sentence = sb.build_sentence()
    if sentence:
        try:
            from blickfang.output.tts import speak
            speak(sentence)
        except Exception as e:
            logger.error(f"TTS-Fehler: {e}")

        # Kommunikation protokollieren
        from blickfang.server.api import log_communication
        log_communication(sentence, "satz-builder")

    return {"status": "ok", "sentence": sentence}


@router.post("/api/sentence-builder/reset")
async def reset_builder():
    """Setzt den Satz-Builder zurück."""
    sb = _get_sentence_builder()
    sb.reset()
    return {"status": "ok"}


# ─── Wörterbuch Endpunkte ────────────────────────────────────────────────


@router.get("/api/dictionary/words")
async def get_dictionary_words(category: str = "", favorites_only: bool = False):
    """Gibt Wörterbuch-Einträge zurück."""
    d = _get_dictionary()
    entries = d.get_words(
        category=category if category else None,
        favorites_only=favorites_only,
    )
    return {
        "entries": [e.to_dict() for e in entries],
    }


@router.get("/api/dictionary/stats")
async def get_dictionary_stats():
    """Gibt Wörterbuch-Statistiken zurück."""
    d = _get_dictionary()
    return {
        "total": d.size,
        "categories": d.get_categories_with_counts(),
    }


class AddWordRequest(BaseModel):
    word: str
    category: str = "allgemein"
    notes: str = ""


@router.post("/api/dictionary/add")
async def add_word(req: AddWordRequest):
    """Fügt ein Wort zum Wörterbuch hinzu."""
    d = _get_dictionary()
    entry = d.add_word(req.word, category=req.category, notes=req.notes)
    d.save()
    return {"status": "ok", "entry": entry.to_dict()}


class RemoveWordRequest(BaseModel):
    word: str


@router.post("/api/dictionary/remove")
async def remove_word(req: RemoveWordRequest):
    """Entfernt ein Wort aus dem Wörterbuch."""
    d = _get_dictionary()
    success = d.remove_word(req.word)
    if success:
        d.save()
    return {"status": "ok" if success else "not_found"}


class FavoriteRequest(BaseModel):
    word: str


@router.post("/api/dictionary/favorite")
async def toggle_favorite(req: FavoriteRequest):
    """Markiert/entfernt ein Wort als Favorit."""
    d = _get_dictionary()
    entries = d.get_words()
    for entry in entries:
        if entry.word.lower() == req.word.lower():
            entry.is_favorite = not entry.is_favorite
            d.save()
            return {"status": "ok", "is_favorite": entry.is_favorite}
    return {"error": "Wort nicht gefunden"}


@router.get("/api/dictionary/export")
async def export_dictionary():
    """Exportiert das Wörterbuch als JSON-Datei."""
    d = _get_dictionary()
    entries = d.get_words()
    data = {
        "person": d.person,
        "entries": [e.to_dict() for e in entries],
    }
    content = json.dumps(data, ensure_ascii=False, indent=2)
    return Response(
        content=content,
        media_type="application/json",
        headers={"Content-Disposition": f'attachment; filename="{d.person}_woerterbuch.json"'},
    )


# ─── Vorhersage Endpunkte ────────────────────────────────────────────────


class PredictRequest(BaseModel):
    context: str = ""
    prefix: str = ""
    max_count: int = 6


@router.post("/api/predictions/predict")
async def predict_words(req: PredictRequest):
    """Gibt kontextabhängige Wortvorschläge zurück."""
    p = _get_predictor()
    predictions = p.predict(context=req.context, prefix=req.prefix, max_count=req.max_count)
    return {"predictions": predictions}


@router.get("/api/predictions/stats")
async def prediction_stats():
    """Gibt Statistiken über die Vorhersage-Daten zurück."""
    p = _get_predictor()
    return p.get_stats()
