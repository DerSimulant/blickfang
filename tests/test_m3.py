"""Tests für Meilenstein M3: Satz-Builder, Vorhersagen, Wörterbuch."""

import json
import tempfile
from pathlib import Path

import pytest


class TestSentenceBuilder:
    """Tests für den Satz-Builder."""

    def test_default_templates_loaded(self):
        from blickfang.scanning.sentence_builder import SentenceBuilder
        sb = SentenceBuilder()
        assert len(sb.templates) >= 4  # Bedürfnis, Befinden, Frage, Soziales

    def test_select_template(self):
        from blickfang.scanning.sentence_builder import SentenceBuilder
        sb = SentenceBuilder()
        template = sb.select_template(0)
        assert template is not None
        assert template.name == "Bedürfnis"
        assert sb.current_slot is not None

    def test_select_word(self):
        from blickfang.scanning.sentence_builder import SentenceBuilder
        sb = SentenceBuilder()
        sb.select_template(0)  # Bedürfnis
        word = sb.select_word(0)  # "Ich"
        assert word is not None
        assert word.text == "Ich"

    def test_build_sentence(self):
        from blickfang.scanning.sentence_builder import SentenceBuilder
        sb = SentenceBuilder()
        sb.select_template(0)  # Bedürfnis

        # Subjekt: "Ich"
        sb.select_word(0)
        sb.advance_slot()

        # Verb: "möchte"
        sb.select_word(0)
        sb.advance_slot()

        # Objekt: "Wasser"
        sb.select_word(0)

        sentence = sb.build_sentence()
        assert "Ich" in sentence
        assert "möchte" in sentence
        assert "Wasser" in sentence

    def test_conjugation(self):
        from blickfang.scanning.sentence_builder import SentenceBuilder
        sb = SentenceBuilder()
        sb.select_template(0)  # Bedürfnis

        # Subjekt: "Wir"
        sb.select_word(1)
        sb.advance_slot()

        # Verb: "möchte" → sollte zu "möchten" konjugiert werden
        sb.select_word(0)
        sb.advance_slot()

        # Objekt
        sb.select_word(0)

        sentence = sb.build_sentence()
        assert "möchten" in sentence

    def test_optional_slot_skip(self):
        from blickfang.scanning.sentence_builder import SentenceBuilder
        sb = SentenceBuilder()
        sb.select_template(1)  # Befinden (hat optionalen Ort-Slot)

        # Alle Pflicht-Slots ausfüllen
        sb.select_word(0)  # Mir
        sb.advance_slot()
        sb.select_word(0)  # geht es
        sb.advance_slot()
        sb.select_word(0)  # gut
        sb.advance_slot()

        # Optionaler Slot: überspringen
        assert sb.current_slot is not None
        assert sb.current_slot.optional is True
        assert sb.skip_slot() is False  # Letzter Slot, kann nicht weiter

    def test_reset(self):
        from blickfang.scanning.sentence_builder import SentenceBuilder
        sb = SentenceBuilder()
        sb.select_template(0)
        sb.select_word(0)
        sb.reset()
        assert sb.active_template is None
        assert sb.current_slot is None

    def test_get_layout_for_scanning_templates(self):
        from blickfang.scanning.sentence_builder import SentenceBuilder
        sb = SentenceBuilder()
        layout = sb.get_layout_for_scanning()
        assert "rows" in layout
        assert len(layout["rows"]) >= 4

    def test_get_layout_for_scanning_words(self):
        from blickfang.scanning.sentence_builder import SentenceBuilder
        sb = SentenceBuilder()
        sb.select_template(0)
        layout = sb.get_layout_for_scanning()
        assert "rows" in layout
        assert len(layout["rows"]) > 0


class TestContextPredictor:
    """Tests für den kontextabhängigen Prediktor."""

    def test_learn_and_predict(self):
        from blickfang.scanning.predictor import ContextPredictor
        with tempfile.TemporaryDirectory() as tmpdir:
            p = ContextPredictor(person="test", data_dir=Path(tmpdir))

            # Lernen
            p.learn_word("wasser", context="ich möchte")
            p.learn_word("wasser", context="ich möchte")
            p.learn_word("tee", context="ich möchte")

            # Vorhersagen
            predictions = p.predict(context="ich möchte", max_count=5)
            assert "wasser" in predictions
            # Wasser sollte vor Tee kommen (häufiger)
            if "tee" in predictions:
                assert predictions.index("wasser") < predictions.index("tee")

    def test_prefix_filter(self):
        from blickfang.scanning.predictor import ContextPredictor
        with tempfile.TemporaryDirectory() as tmpdir:
            p = ContextPredictor(person="test", data_dir=Path(tmpdir))
            p.learn_word("wasser", context="")
            p.learn_word("wand", context="")
            p.learn_word("tee", context="")

            predictions = p.predict(context="", prefix="wa", max_count=5)
            assert all(w.startswith("wa") for w in predictions)
            assert "tee" not in predictions

    def test_save_and_load(self):
        from blickfang.scanning.predictor import ContextPredictor
        with tempfile.TemporaryDirectory() as tmpdir:
            p1 = ContextPredictor(person="test", data_dir=Path(tmpdir))
            p1.learn_word("wasser", context="ich möchte")
            p1.learn_word("wasser", context="ich möchte")
            p1.save()

            # Neu laden
            p2 = ContextPredictor(person="test", data_dir=Path(tmpdir))
            assert p2.get_stats()["unique_words"] >= 1

    def test_learn_sentence(self):
        from blickfang.scanning.predictor import ContextPredictor
        with tempfile.TemporaryDirectory() as tmpdir:
            p = ContextPredictor(person="test", data_dir=Path(tmpdir))
            p.learn_sentence("ich möchte bitte wasser")
            stats = p.get_stats()
            assert stats["unique_words"] == 4


class TestPersonalDictionary:
    """Tests für das persönliche Wörterbuch."""

    def test_add_and_get_word(self):
        from blickfang.scanning.dictionary import PersonalDictionary
        with tempfile.TemporaryDirectory() as tmpdir:
            d = PersonalDictionary(person="test", data_dir=Path(tmpdir))
            d.add_word("Schwester Maria", category="personen", notes="Pflegerin")

            entries = d.get_words(category="personen")
            words = [e.word for e in entries]
            assert "Schwester Maria" in words

    def test_remove_word(self):
        from blickfang.scanning.dictionary import PersonalDictionary
        with tempfile.TemporaryDirectory() as tmpdir:
            d = PersonalDictionary(person="test", data_dir=Path(tmpdir))
            d.add_word("TestWort")
            assert d.remove_word("TestWort") is True
            assert d.remove_word("NichtDa") is False

    def test_record_usage(self):
        from blickfang.scanning.dictionary import PersonalDictionary
        with tempfile.TemporaryDirectory() as tmpdir:
            d = PersonalDictionary(person="test", data_dir=Path(tmpdir))
            d.add_word("Wasser")
            d.record_usage("Wasser")
            d.record_usage("Wasser")

            entries = d.get_words()
            wasser = next(e for e in entries if e.word == "Wasser")
            assert wasser.usage_count >= 2

    def test_search(self):
        from blickfang.scanning.dictionary import PersonalDictionary
        with tempfile.TemporaryDirectory() as tmpdir:
            d = PersonalDictionary(person="test", data_dir=Path(tmpdir))
            d.add_word("Wasser")
            d.add_word("Wand")
            d.add_word("Tee")

            results = d.search("Wa")
            words = [e.word for e in results]
            assert "Wasser" in words
            assert "Wand" in words
            assert "Tee" not in words

    def test_save_and_load(self):
        from blickfang.scanning.dictionary import PersonalDictionary
        with tempfile.TemporaryDirectory() as tmpdir:
            d1 = PersonalDictionary(person="test", data_dir=Path(tmpdir))
            d1.add_word("Spezialwort", category="medizin")
            d1.save()

            d2 = PersonalDictionary(person="test", data_dir=Path(tmpdir))
            entries = d2.get_words(category="medizin")
            words = [e.word for e in entries]
            assert "Spezialwort" in words

    def test_export_import(self):
        from blickfang.scanning.dictionary import PersonalDictionary
        with tempfile.TemporaryDirectory() as tmpdir:
            d = PersonalDictionary(person="test", data_dir=Path(tmpdir))
            d.add_word("ExportTest", category="allgemein")

            export_path = Path(tmpdir) / "export.txt"
            d.export_to_file(export_path)
            assert export_path.exists()
            content = export_path.read_text()
            assert "ExportTest" in content

    def test_default_words_loaded(self):
        from blickfang.scanning.dictionary import PersonalDictionary
        with tempfile.TemporaryDirectory() as tmpdir:
            d = PersonalDictionary(person="new_person", data_dir=Path(tmpdir))
            # Sollte Standard-Wörter haben
            assert d.size > 0
            entries = d.get_words(category="essen_trinken")
            words = [e.word for e in entries]
            assert "Wasser" in words

    def test_favorites(self):
        from blickfang.scanning.dictionary import PersonalDictionary
        with tempfile.TemporaryDirectory() as tmpdir:
            d = PersonalDictionary(person="test", data_dir=Path(tmpdir))
            d.add_word("Favorit", is_favorite=True)
            d.add_word("Normal")

            favorites = d.get_words(favorites_only=True)
            words = [e.word for e in favorites]
            assert "Favorit" in words
            assert "Normal" not in words


class TestProtocolExport:
    """Tests für den Tages-Protokoll-Export."""

    def test_log_event(self):
        from blickfang.server.protocol_api import log_event, get_today_events
        log_event("communication", {"text": "Test", "mode": "test"}, person="test")
        events = get_today_events()
        assert len(events) > 0
        assert events[-1]["type"] == "communication"
