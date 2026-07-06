"""Tests für das Scanning-Framework (M2).

Testet:
- ScanningEngine (Zeilen-Spalten-Scanning)
- TextBuffer (Buchstabieren + Wortvorhersage)
- AlarmDetector (Notruf)
- FatigueMonitor (Ermüdung)
- Layout-Loader
"""

import time
from unittest.mock import MagicMock, patch

import pytest

from blickfang.scanning.engine import (
    ScanItem,
    ScanLayout,
    ScanPhase,
    ScanRow,
    ScanningEngine,
)
from blickfang.scanning.text_buffer import TextBuffer
from blickfang.scanning.alarm import AlarmDetector
from blickfang.scanning.fatigue import FatigueMonitor


# ─── ScanningEngine Tests ───────────────────────────────────────────────


def _make_simple_layout() -> ScanLayout:
    """Erstellt ein einfaches 2x3 Test-Layout."""
    layout = ScanLayout(name="Test", scan_speed_s=0.1, max_cycles=2, cancel_countdown_s=0.1)
    row1 = ScanRow(label="Zeile 1")
    row1.items = [
        ScanItem(label="A", value="a"),
        ScanItem(label="B", value="b"),
        ScanItem(label="C", value="c"),
    ]
    row2 = ScanRow(label="Zeile 2")
    row2.items = [
        ScanItem(label="D", value="d"),
        ScanItem(label="E", value="e"),
        ScanItem(label="F", value="f"),
    ]
    layout.rows = [row1, row2]
    return layout


class TestScanningEngine:
    def test_start_begins_row_scan(self):
        layout = _make_simple_layout()
        engine = ScanningEngine(layout)
        engine.start()
        assert engine.state.phase == ScanPhase.ROW_SCAN
        assert engine.state.current_row == 0

    def test_signal_in_row_scan_starts_col_scan(self):
        layout = _make_simple_layout()
        engine = ScanningEngine(layout)
        engine.start()
        engine.signal()  # Zeile 0 wählen
        assert engine.state.phase == ScanPhase.COL_SCAN
        assert engine.state.current_col == 0

    def test_signal_in_col_scan_starts_confirm(self):
        layout = _make_simple_layout()
        engine = ScanningEngine(layout)
        engine.start()
        engine.signal()  # Zeile 0
        engine.signal()  # Spalte 0 (Item "A")
        assert engine.state.phase == ScanPhase.CONFIRM
        assert engine.state.selected_item.label == "A"

    def test_confirm_completes_after_countdown(self):
        layout = _make_simple_layout()
        engine = ScanningEngine(layout)
        engine.start()
        engine.signal()  # Zeile 0
        engine.signal()  # Spalte 0

        # Warte auf Countdown
        time.sleep(0.15)
        engine.tick()

        assert engine.state.phase == ScanPhase.SELECTED

    def test_signal_during_confirm_cancels(self):
        layout = _make_simple_layout()
        engine = ScanningEngine(layout)
        engine.start()
        engine.signal()  # Zeile 0
        engine.signal()  # Spalte 0 → CONFIRM

        # Sofort nochmal Signal → Cancel
        engine.signal()
        assert engine.state.phase == ScanPhase.ROW_SCAN

    def test_advance_moves_to_next_row(self):
        layout = _make_simple_layout()
        engine = ScanningEngine(layout)
        engine.start()

        # Warte auf Auto-Advance
        time.sleep(0.15)
        engine.tick()

        assert engine.state.current_row == 1

    def test_timeout_triggers_no_answer(self):
        layout = _make_simple_layout()
        layout.max_cycles = 1
        engine = ScanningEngine(layout)
        engine.start()

        # 2 Zeilen + 1 Cycle = nach 3 Advances → NO_ANSWER
        for _ in range(3):
            time.sleep(0.15)
            engine.tick()

        assert engine.state.phase == ScanPhase.NO_ANSWER

    def test_select_callback_fired(self):
        layout = _make_simple_layout()
        engine = ScanningEngine(layout)
        selected = []
        engine.on("select", lambda item: selected.append(item))

        engine.start()
        engine.signal()  # Zeile 0
        engine.signal()  # Spalte 0

        time.sleep(0.15)
        engine.tick()

        assert len(selected) == 1
        assert selected[0].label == "A"

    def test_single_item_row_selects_directly(self):
        layout = ScanLayout(name="Single", scan_speed_s=0.1, cancel_countdown_s=0.1)
        row = ScanRow(label="Einzel")
        row.items = [ScanItem(label="X", value="x")]
        layout.rows = [row]

        engine = ScanningEngine(layout)
        engine.start()
        engine.signal()  # Zeile mit nur 1 Item → direkt CONFIRM

        assert engine.state.phase == ScanPhase.CONFIRM
        assert engine.state.selected_item.label == "X"

    def test_col_scan_advances_columns(self):
        layout = _make_simple_layout()
        layout.scan_speed_s = 0.05
        engine = ScanningEngine(layout)
        engine.start()
        engine.signal()  # Zeile 0 → Col-Scan

        # Warte auf Advance
        time.sleep(0.08)
        engine.tick()

        assert engine.state.current_col == 1


# ─── TextBuffer Tests ───────────────────────────────────────────────────


class TestTextBuffer:
    def test_add_char(self):
        buf = TextBuffer()
        buf.add_char("h")
        buf.add_char("a")
        assert buf.text == "ha"

    def test_backspace(self):
        buf = TextBuffer()
        buf.add_char("a")
        buf.add_char("b")
        buf.backspace()
        assert buf.text == "a"

    def test_backspace_empty(self):
        buf = TextBuffer()
        buf.backspace()  # Sollte nicht crashen
        assert buf.text == ""

    def test_clear(self):
        buf = TextBuffer()
        buf.add_char("x")
        buf.add_char("y")
        buf.clear()
        assert buf.text == ""

    def test_add_space(self):
        buf = TextBuffer()
        buf.add_char("h")
        buf.add_char("i")
        buf.add_space()
        assert buf.text == "hi "

    def test_current_word(self):
        buf = TextBuffer()
        buf.add_char("h")
        buf.add_char("a")
        buf.add_char("l")
        assert buf.current_word == "hal"

        buf.add_space()
        assert buf.current_word == ""

    def test_predictions_with_prefix(self):
        buf = TextBuffer()
        buf.add_char("i")
        buf.add_char("c")
        preds = buf.get_predictions()
        assert len(preds) > 0
        assert all(p.startswith("ic") for p in preds)

    def test_complete_word(self):
        buf = TextBuffer()
        buf.add_char("i")
        buf.add_char("c")
        buf.complete_word("ich")
        assert buf.text == "ich "

    def test_undo(self):
        buf = TextBuffer()
        buf.add_char("a")
        buf.add_char("b")
        buf.undo()
        assert buf.text == "a"

    def test_display_text_has_cursor(self):
        buf = TextBuffer()
        buf.add_char("x")
        assert "▌" in buf.display_text

    def test_get_full_text_for_speech(self):
        buf = TextBuffer()
        buf.add_char("h")
        buf.add_char("i")
        buf.add_space()
        buf.add_char("d")
        buf.add_char("u")
        assert buf.get_full_text_for_speech() == "hi du"

    def test_on_change_callback(self):
        changes = []
        buf = TextBuffer(on_change=lambda t: changes.append(t))
        buf.add_char("a")
        buf.add_char("b")
        assert len(changes) == 2
        assert changes[-1] == "ab"


# ─── AlarmDetector Tests ────────────────────────────────────────────────


class TestAlarmDetector:
    def test_no_alarm_on_single_signal(self):
        alarm = AlarmDetector(required_signals=3, window_s=2.0)
        assert alarm.signal() is False

    def test_alarm_on_rapid_signals(self):
        triggered = []
        alarm = AlarmDetector(
            required_signals=3,
            window_s=2.0,
            on_alarm=lambda: triggered.append(True),
        )
        alarm.signal()
        alarm.signal()
        result = alarm.signal()
        assert result is True
        assert len(triggered) == 1

    def test_no_alarm_if_signals_too_spread(self):
        alarm = AlarmDetector(required_signals=3, window_s=0.1)
        alarm.signal()
        time.sleep(0.15)
        alarm.signal()
        time.sleep(0.15)
        result = alarm.signal()
        assert result is False

    def test_cooldown_prevents_repeated_alarm(self):
        alarm = AlarmDetector(required_signals=2, window_s=2.0, cooldown_s=1.0)
        alarm.signal()
        alarm.signal()  # Alarm 1

        # Sofort nochmal
        alarm.signal()
        result = alarm.signal()
        assert result is False  # Cooldown aktiv

    def test_disabled_alarm(self):
        alarm = AlarmDetector(required_signals=2, window_s=2.0)
        alarm.enabled = False
        alarm.signal()
        result = alarm.signal()
        assert result is False

    def test_reset_clears_signals(self):
        alarm = AlarmDetector(required_signals=3, window_s=2.0)
        alarm.signal()
        alarm.signal()
        alarm.reset()
        result = alarm.signal()  # Nur 1 Signal nach Reset
        assert result is False


# ─── FatigueMonitor Tests ───────────────────────────────────────────────


class TestFatigueMonitor:
    def test_initial_metrics_normal(self):
        monitor = FatigueMonitor()
        metrics = monitor.get_metrics()
        assert metrics.fatigue_level == "normal"
        assert metrics.pause_recommended is False

    def test_records_signals(self):
        monitor = FatigueMonitor()
        monitor.record_signal(latency_s=0.5)
        monitor.record_signal(latency_s=0.6)
        metrics = monitor.get_metrics()
        assert metrics.signals_total == 2

    def test_mean_latency(self):
        monitor = FatigueMonitor()
        monitor.record_signal(latency_s=1.0)
        monitor.record_signal(latency_s=2.0)
        metrics = monitor.get_metrics()
        assert metrics.mean_latency_s == pytest.approx(1.5, abs=0.1)

    def test_reset_clears_data(self):
        monitor = FatigueMonitor()
        monitor.record_signal()
        monitor.record_signal()
        monitor.reset()
        metrics = monitor.get_metrics()
        assert metrics.signals_total == 0

    def test_false_positive_tracking(self):
        monitor = FatigueMonitor()
        monitor.record_false_positive()
        monitor.record_false_positive()
        metrics = monitor.get_metrics()
        assert metrics.fp_rate_last_5min > 0


# ─── Layout-Loader Tests ───────────────────────────────────────────────


class TestLayoutLoader:
    def test_load_keyboard_layout(self):
        from blickfang.scanning.layouts import get_keyboard_layout
        layout = get_keyboard_layout()
        assert layout is not None
        assert layout.row_count > 0
        assert layout.total_items > 20  # Mindestens Alphabet

    def test_load_phrases_layout(self):
        from blickfang.scanning.layouts import get_phrases_layout
        layout = get_phrases_layout()
        assert layout is not None
        assert layout.row_count > 0

    def test_load_yesno_layout(self):
        from blickfang.scanning.layouts import get_yesno_layout
        layout = get_yesno_layout()
        assert layout is not None
        assert layout.total_items == 3

    def test_list_layouts(self):
        from blickfang.scanning.layouts import list_layouts
        layouts = list_layouts()
        assert len(layouts) >= 2  # deutsch_frequenz + phrasen
