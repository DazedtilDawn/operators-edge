#!/usr/bin/env python3
"""
Tests for course_correction.py

Testing the feedback loop of v8.0 metrics.
"""
import json
import os
import sys
import tempfile
import unittest
from datetime import datetime, timedelta
from pathlib import Path

# Add hooks directory to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from course_correction import (
    DriftSignalEvent,
    CorrectionAnalysis,
    load_session_entries,
    parse_timestamp,
    infer_drift_signals,
    get_entries_around_time,
    extract_files_from_entries,
    extract_commands_from_entries,
    detect_file_churn_correction,
    detect_command_repeat_correction,
    detect_correction,
    analyze_session_corrections,
    calculate_correction_rate,
)


class TestDriftSignalEvent(unittest.TestCase):
    """Tests for DriftSignalEvent dataclass."""

    def test_problem_file_extraction(self):
        """Test extracting problem file from evidence."""
        signal = DriftSignalEvent(
            signal_type="FILE_CHURN",
            timestamp=datetime.now(),
            severity="warning",
            evidence={"file": "/app/utils.py", "edit_count": 3}
        )
        self.assertEqual(signal.problem_file, "/app/utils.py")

    def test_problem_command_extraction(self):
        """Test extracting problem command from evidence."""
        signal = DriftSignalEvent(
            signal_type="COMMAND_REPEAT",
            timestamp=datetime.now(),
            severity="warning",
            evidence={"command_pattern": "pytest", "fail_count": 3}
        )
        self.assertEqual(signal.problem_command, "pytest")


class TestTimestampParsing(unittest.TestCase):
    """Tests for timestamp parsing."""

    def test_valid_timestamp(self):
        """Test parsing valid ISO timestamp."""
        ts = parse_timestamp("2026-01-18T10:30:00")
        self.assertIsNotNone(ts)
        self.assertEqual(ts.hour, 10)
        self.assertEqual(ts.minute, 30)

    def test_invalid_timestamp(self):
        """Test parsing invalid timestamp."""
        ts = parse_timestamp("not-a-timestamp")
        self.assertIsNone(ts)

    def test_empty_timestamp(self):
        """Test parsing empty timestamp."""
        ts = parse_timestamp("")
        self.assertIsNone(ts)


class TestDriftSignalInference(unittest.TestCase):
    """Tests for drift signal inference from session logs."""

    def test_no_signals_from_normal_activity(self):
        """Test that normal activity doesn't trigger signals."""
        entries = [
            {"timestamp": "2026-01-18T10:00:00", "tool": "Read", "input_preview": {"file": "/app/a.py"}},
            {"timestamp": "2026-01-18T10:01:00", "tool": "Edit", "input_preview": {"file_path": "/app/b.py"}, "success": True},
            {"timestamp": "2026-01-18T10:02:00", "tool": "Bash", "input_preview": {"command": "pytest"}, "success": True},
        ]
        signals = infer_drift_signals(entries)
        self.assertEqual(len(signals), 0)

    def test_file_churn_signal(self):
        """Test FILE_CHURN signal inference."""
        entries = [
            {"timestamp": "2026-01-18T10:00:00", "tool": "Edit", "input_preview": {"file_path": "/app/utils.py"}, "success": True},
            {"timestamp": "2026-01-18T10:01:00", "tool": "Edit", "input_preview": {"file_path": "/app/utils.py"}, "success": True},
            {"timestamp": "2026-01-18T10:02:00", "tool": "Edit", "input_preview": {"file_path": "/app/utils.py"}, "success": True},
        ]
        signals = infer_drift_signals(entries)
        self.assertEqual(len(signals), 1)
        self.assertEqual(signals[0].signal_type, "FILE_CHURN")
        self.assertEqual(signals[0].problem_file, "/app/utils.py")

    def test_command_repeat_signal(self):
        """Test COMMAND_REPEAT signal inference."""
        entries = [
            {"timestamp": "2026-01-18T10:00:00", "tool": "Bash", "input_preview": {"command": "pytest tests/"}, "success": False},
            {"timestamp": "2026-01-18T10:01:00", "tool": "Bash", "input_preview": {"command": "pytest tests/"}, "success": False},
            {"timestamp": "2026-01-18T10:02:00", "tool": "Bash", "input_preview": {"command": "pytest tests/"}, "success": False},
        ]
        signals = infer_drift_signals(entries)
        self.assertEqual(len(signals), 1)
        self.assertEqual(signals[0].signal_type, "COMMAND_REPEAT")
        self.assertEqual(signals[0].problem_command, "pytest")

    def test_no_signal_for_different_files(self):
        """Test that editing different files doesn't trigger signal."""
        entries = [
            {"timestamp": "2026-01-18T10:00:00", "tool": "Edit", "input_preview": {"file_path": "/app/a.py"}, "success": True},
            {"timestamp": "2026-01-18T10:01:00", "tool": "Edit", "input_preview": {"file_path": "/app/b.py"}, "success": True},
            {"timestamp": "2026-01-18T10:02:00", "tool": "Edit", "input_preview": {"file_path": "/app/c.py"}, "success": True},
        ]
        signals = infer_drift_signals(entries)
        self.assertEqual(len(signals), 0)


class TestEntriesAroundTime(unittest.TestCase):
    """Tests for getting entries around a timestamp."""

    def test_entries_before_and_after(self):
        """Test getting entries before and after a timestamp."""
        entries = [
            {"timestamp": "2026-01-18T10:00:00", "tool": "A"},
            {"timestamp": "2026-01-18T10:02:00", "tool": "B"},
            {"timestamp": "2026-01-18T10:05:00", "tool": "C"},  # Target
            {"timestamp": "2026-01-18T10:07:00", "tool": "D"},
            {"timestamp": "2026-01-18T10:10:00", "tool": "E"},
        ]
        target = datetime.fromisoformat("2026-01-18T10:05:00")

        before, after = get_entries_around_time(entries, target, window_before_seconds=300, window_after_seconds=300)

        self.assertEqual(len(before), 2)  # A and B
        self.assertEqual(len(after), 2)   # D and E


class TestFileExtraction(unittest.TestCase):
    """Tests for file extraction from entries."""

    def test_extract_files(self):
        """Test extracting files from entries."""
        entries = [
            {"tool": "Edit", "input_preview": {"file_path": "/app/a.py"}},
            {"tool": "Read", "input_preview": {"file": "/app/b.py"}},
            {"tool": "Bash", "input_preview": {"command": "ls"}},
            {"tool": "Write", "input_preview": {"file_path": "/app/c.py"}},
        ]
        files = extract_files_from_entries(entries)
        self.assertEqual(files, {"/app/a.py", "/app/b.py", "/app/c.py"})

    def test_extract_commands(self):
        """Test extracting commands from entries."""
        entries = [
            {"tool": "Bash", "input_preview": {"command": "pytest tests/"}},
            {"tool": "Bash", "input_preview": {"command": "npm install"}},
            {"tool": "Edit", "input_preview": {"file_path": "/app/a.py"}},
        ]
        commands = extract_commands_from_entries(entries)
        self.assertEqual(commands, ["pytest", "npm"])


class TestFileChurnCorrectionDetection(unittest.TestCase):
    """Tests for FILE_CHURN correction detection."""

    def test_correction_when_file_not_edited_after(self):
        """Test that stopping file edits counts as correction."""
        signal = DriftSignalEvent(
            signal_type="FILE_CHURN",
            timestamp=datetime.fromisoformat("2026-01-18T10:05:00"),
            severity="warning",
            evidence={"file": "/app/utils.py", "edit_count": 3}
        )

        entries_before = [
            {"tool": "Edit", "input_preview": {"file_path": "/app/utils.py"}},
            {"tool": "Edit", "input_preview": {"file_path": "/app/utils.py"}},
        ]

        entries_after = [
            {"tool": "Edit", "input_preview": {"file_path": "/app/models.py"}},
            {"tool": "Read", "input_preview": {"file": "/app/config.py"}},
        ]

        analysis = detect_file_churn_correction(signal, entries_before, entries_after)

        self.assertTrue(analysis.correction_detected)
        self.assertGreater(analysis.confidence, 0.5)

    def test_no_correction_when_file_still_edited(self):
        """Test that continued editing counts as no correction."""
        signal = DriftSignalEvent(
            signal_type="FILE_CHURN",
            timestamp=datetime.fromisoformat("2026-01-18T10:05:00"),
            severity="warning",
            evidence={"file": "/app/utils.py", "edit_count": 3}
        )

        entries_before = [
            {"tool": "Edit", "input_preview": {"file_path": "/app/utils.py"}},
        ]

        entries_after = [
            {"tool": "Edit", "input_preview": {"file_path": "/app/utils.py"}},
            {"tool": "Edit", "input_preview": {"file_path": "/app/utils.py"}},
        ]

        analysis = detect_file_churn_correction(signal, entries_before, entries_after)

        self.assertFalse(analysis.correction_detected)


class TestCommandRepeatCorrectionDetection(unittest.TestCase):
    """Tests for COMMAND_REPEAT correction detection."""

    def test_correction_when_different_command(self):
        """Test that trying different command counts as correction."""
        signal = DriftSignalEvent(
            signal_type="COMMAND_REPEAT",
            timestamp=datetime.fromisoformat("2026-01-18T10:05:00"),
            severity="warning",
            evidence={"command_pattern": "pytest", "fail_count": 3}
        )

        entries_before = [
            {"tool": "Bash", "input_preview": {"command": "pytest tests/"}},
            {"tool": "Bash", "input_preview": {"command": "pytest tests/"}},
        ]

        entries_after = [
            {"tool": "Bash", "input_preview": {"command": "pip install -r requirements.txt"}},
            {"tool": "Bash", "input_preview": {"command": "npm test"}},
        ]

        analysis = detect_command_repeat_correction(signal, entries_before, entries_after)

        self.assertTrue(analysis.correction_detected)

    def test_no_correction_when_same_command(self):
        """Test that repeating same command counts as no correction."""
        signal = DriftSignalEvent(
            signal_type="COMMAND_REPEAT",
            timestamp=datetime.fromisoformat("2026-01-18T10:05:00"),
            severity="warning",
            evidence={"command_pattern": "pytest", "fail_count": 3}
        )

        entries_before = [
            {"tool": "Bash", "input_preview": {"command": "pytest tests/"}},
        ]

        entries_after = [
            {"tool": "Bash", "input_preview": {"command": "pytest tests/ -v"}},
        ]

        analysis = detect_command_repeat_correction(signal, entries_before, entries_after)

        self.assertFalse(analysis.correction_detected)


class TestSessionCorrectionAnalysis(unittest.TestCase):
    """Tests for full session correction analysis."""

    def test_empty_session(self):
        """Test analysis of empty session."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.jsonl', delete=False) as f:
            temp_path = Path(f.name)

        try:
            analyses = analyze_session_corrections(temp_path)
            self.assertEqual(len(analyses), 0)
        finally:
            temp_path.unlink()

    def test_session_with_file_churn(self):
        """Test analysis of session with file churn."""
        entries = [
            {"timestamp": "2026-01-18T10:00:00", "tool": "Edit", "input_preview": {"file_path": "/app/utils.py"}, "success": True},
            {"timestamp": "2026-01-18T10:02:00", "tool": "Edit", "input_preview": {"file_path": "/app/utils.py"}, "success": True},
            {"timestamp": "2026-01-18T10:04:00", "tool": "Edit", "input_preview": {"file_path": "/app/utils.py"}, "success": True},
            {"timestamp": "2026-01-18T10:08:00", "tool": "Edit", "input_preview": {"file_path": "/app/models.py"}, "success": True},
        ]

        with tempfile.NamedTemporaryFile(mode='w', suffix='.jsonl', delete=False) as f:
            for entry in entries:
                f.write(json.dumps(entry) + '\n')
            temp_path = Path(f.name)

        try:
            analyses = analyze_session_corrections(temp_path)
            self.assertEqual(len(analyses), 1)
            self.assertEqual(analyses[0].signal.signal_type, "FILE_CHURN")
        finally:
            temp_path.unlink()


class TestCorrectionRateCalculation(unittest.TestCase):
    """Tests for correction rate calculation."""

    def test_empty_list(self):
        """Test with no analyses."""
        rate, conf = calculate_correction_rate([])
        self.assertEqual(rate, 0.0)
        self.assertEqual(conf, 0.0)

    def test_all_corrected(self):
        """Test with all corrections."""
        analyses = [
            CorrectionAnalysis(
                signal=DriftSignalEvent("FILE_CHURN", datetime.now(), "warning", {}),
                correction_detected=True,
                confidence=0.8,
                evidence="",
                analysis_window_seconds=300,
                entries_before=5,
                entries_after=5
            ),
            CorrectionAnalysis(
                signal=DriftSignalEvent("FILE_CHURN", datetime.now(), "warning", {}),
                correction_detected=True,
                confidence=0.7,
                evidence="",
                analysis_window_seconds=300,
                entries_before=5,
                entries_after=5
            ),
        ]
        rate, conf = calculate_correction_rate(analyses)
        self.assertEqual(rate, 1.0)
        self.assertEqual(conf, 0.75)

    def test_partial_correction(self):
        """Test with partial corrections."""
        analyses = [
            CorrectionAnalysis(
                signal=DriftSignalEvent("FILE_CHURN", datetime.now(), "warning", {}),
                correction_detected=True,
                confidence=0.8,
                evidence="",
                analysis_window_seconds=300,
                entries_before=5,
                entries_after=5
            ),
            CorrectionAnalysis(
                signal=DriftSignalEvent("FILE_CHURN", datetime.now(), "warning", {}),
                correction_detected=False,
                confidence=0.7,
                evidence="",
                analysis_window_seconds=300,
                entries_before=5,
                entries_after=5
            ),
        ]
        rate, conf = calculate_correction_rate(analyses)
        self.assertEqual(rate, 0.5)


if __name__ == "__main__":
    unittest.main()
