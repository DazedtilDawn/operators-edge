#!/usr/bin/env python3
"""
Tests for Operator's Edge v8.0 - Drift Detector

Tests cover:
- File churn detection
- Command repeat detection
- Step stall detection
- Intervention formatting
"""
import json
import os
import sys
import tempfile
import unittest
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import patch, MagicMock

# Add hooks directory to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from drift_detector import (
    DriftSignal,
    extract_file_edits,
    extract_bash_commands,
    detect_file_churn,
    detect_command_repeat,
    detect_step_stall,
    detect_drift,
    format_drift_intervention,
    load_recent_session_entries,
)


class TestExtractFileEdits(unittest.TestCase):
    """Tests for file edit extraction from session entries."""

    def test_extracts_edit_with_file_key(self):
        """Should extract file path from Edit entries using 'file' key."""
        entries = [
            {
                "tool": "Edit",
                "input_preview": {"file": "/app/utils.py"},
                "timestamp": "2026-01-17T10:00:00"
            }
        ]
        edits = extract_file_edits(entries)
        self.assertEqual(len(edits), 1)
        self.assertEqual(edits[0][0], "/app/utils.py")

    def test_extracts_edit_with_file_path_key(self):
        """Should extract file path from Edit entries using 'file_path' key."""
        entries = [
            {
                "tool": "Edit",
                "input_preview": {"file_path": "/app/models.py"},
                "timestamp": "2026-01-17T10:00:00"
            }
        ]
        edits = extract_file_edits(entries)
        self.assertEqual(len(edits), 1)
        self.assertEqual(edits[0][0], "/app/models.py")

    def test_extracts_write_entries(self):
        """Should extract Write tool entries."""
        entries = [
            {
                "tool": "Write",
                "input_preview": {"file_path": "/app/new_file.py"},
                "timestamp": "2026-01-17T10:00:00"
            }
        ]
        edits = extract_file_edits(entries)
        self.assertEqual(len(edits), 1)

    def test_ignores_non_edit_tools(self):
        """Should ignore Read, Bash, etc."""
        entries = [
            {
                "tool": "Read",
                "input_preview": {"file_path": "/app/utils.py"},
                "timestamp": "2026-01-17T10:00:00"
            },
            {
                "tool": "Bash",
                "input_preview": {"command": "ls"},
                "timestamp": "2026-01-17T10:00:00"
            }
        ]
        edits = extract_file_edits(entries)
        self.assertEqual(len(edits), 0)

    def test_handles_missing_file_path(self):
        """Should skip entries without file path."""
        entries = [
            {
                "tool": "Edit",
                "input_preview": {"old_string": "foo", "new_string": "bar"},
                "timestamp": "2026-01-17T10:00:00"
            }
        ]
        edits = extract_file_edits(entries)
        self.assertEqual(len(edits), 0)


class TestExtractBashCommands(unittest.TestCase):
    """Tests for bash command extraction."""

    def test_extracts_command_from_dict(self):
        """Should extract command from dict input_preview."""
        entries = [
            {
                "tool": "Bash",
                "input_preview": {"command": "npm test"},
                "success": False,
                "timestamp": "2026-01-17T10:00:00"
            }
        ]
        commands = extract_bash_commands(entries)
        self.assertEqual(len(commands), 1)
        self.assertEqual(commands[0][0], "npm test")
        self.assertEqual(commands[0][1], False)  # success

    def test_ignores_non_bash_tools(self):
        """Should ignore non-Bash tools."""
        entries = [
            {
                "tool": "Edit",
                "input_preview": {"file": "/app/x.py"},
                "timestamp": "2026-01-17T10:00:00"
            }
        ]
        commands = extract_bash_commands(entries)
        self.assertEqual(len(commands), 0)


class TestDetectFileChurn(unittest.TestCase):
    """Tests for file churn detection."""

    def test_detects_churn_above_threshold(self):
        """Should detect when same file edited 3+ times."""
        base_time = datetime.now()
        entries = []
        for i in range(5):
            entries.append({
                "tool": "Edit",
                "input_preview": {"file": "/app/utils.py"},
                "timestamp": (base_time - timedelta(minutes=i)).isoformat()
            })

        signal = detect_file_churn(entries, threshold=3)

        self.assertIsNotNone(signal)
        self.assertEqual(signal.signal_type, "FILE_CHURN")
        self.assertIn("5 times", signal.message)

    def test_no_detection_below_threshold(self):
        """Should not detect when edits below threshold."""
        base_time = datetime.now()
        entries = [
            {
                "tool": "Edit",
                "input_preview": {"file": "/app/utils.py"},
                "timestamp": base_time.isoformat()
            },
            {
                "tool": "Edit",
                "input_preview": {"file": "/app/utils.py"},
                "timestamp": (base_time - timedelta(minutes=1)).isoformat()
            }
        ]

        signal = detect_file_churn(entries, threshold=3)

        self.assertIsNone(signal)

    def test_severity_critical_above_5(self):
        """Should be critical severity when 5+ edits."""
        base_time = datetime.now()
        entries = []
        for i in range(6):
            entries.append({
                "tool": "Edit",
                "input_preview": {"file": "/app/utils.py"},
                "timestamp": (base_time - timedelta(minutes=i)).isoformat()
            })

        signal = detect_file_churn(entries, threshold=3)

        self.assertEqual(signal.severity, "critical")

    def test_severity_warning_below_5(self):
        """Should be warning severity when 3-4 edits."""
        base_time = datetime.now()
        entries = []
        for i in range(4):
            entries.append({
                "tool": "Edit",
                "input_preview": {"file": "/app/utils.py"},
                "timestamp": (base_time - timedelta(minutes=i)).isoformat()
            })

        signal = detect_file_churn(entries, threshold=3)

        self.assertEqual(signal.severity, "warning")


class TestDetectCommandRepeat(unittest.TestCase):
    """Tests for command repeat detection."""

    def test_detects_repeated_failures(self):
        """Should detect when same command fails multiple times."""
        base_time = datetime.now()
        entries = []
        for i in range(3):
            entries.append({
                "tool": "Bash",
                "input_preview": {"command": "npm test"},
                "success": False,
                "timestamp": (base_time - timedelta(minutes=i)).isoformat()
            })

        signal = detect_command_repeat(entries, threshold=2)

        self.assertIsNotNone(signal)
        self.assertEqual(signal.signal_type, "COMMAND_REPEAT")
        self.assertIn("3/3", signal.message)

    def test_no_detection_with_successes(self):
        """Should not detect if command mostly succeeds."""
        base_time = datetime.now()
        entries = [
            {
                "tool": "Bash",
                "input_preview": {"command": "npm test"},
                "success": True,
                "timestamp": base_time.isoformat()
            },
            {
                "tool": "Bash",
                "input_preview": {"command": "npm test"},
                "success": False,
                "timestamp": (base_time - timedelta(minutes=1)).isoformat()
            },
            {
                "tool": "Bash",
                "input_preview": {"command": "npm test"},
                "success": True,
                "timestamp": (base_time - timedelta(minutes=2)).isoformat()
            }
        ]

        signal = detect_command_repeat(entries, threshold=2)

        self.assertIsNone(signal)

    def test_severity_critical_above_3(self):
        """Should be critical when 3+ failures."""
        base_time = datetime.now()
        entries = []
        for i in range(4):
            entries.append({
                "tool": "Bash",
                "input_preview": {"command": "npm test"},
                "success": False,
                "timestamp": (base_time - timedelta(minutes=i)).isoformat()
            })

        signal = detect_command_repeat(entries, threshold=2)

        self.assertEqual(signal.severity, "critical")


class TestDetectStepStall(unittest.TestCase):
    """Tests for step stall detection."""

    def test_detects_stall_with_many_operations(self):
        """Should detect when current step has many operations."""
        state = {
            "current_step": 3,
            "plan": [
                {"description": "Step 1", "status": "completed"},
                {"description": "Step 2", "status": "completed"},
                {"description": "Step 3", "status": "in_progress"}
            ]
        }

        # 20 operations for current step when avg is ~10
        base_time = datetime.now()
        entries = []
        for i in range(20):
            entries.append({
                "tool": "Edit",
                "input_preview": {"file": f"/app/file{i}.py"},
                "timestamp": (base_time - timedelta(minutes=i)).isoformat()
            })

        signal = detect_step_stall(state, entries, stall_multiplier=1.5)

        # Should detect since 20 ops is well above average
        self.assertIsNotNone(signal)
        self.assertEqual(signal.signal_type, "STEP_STALL")

    def test_no_stall_with_few_operations(self):
        """Should not detect stall with normal operation count."""
        state = {
            "current_step": 3,
            "plan": [
                {"description": "Step 1", "status": "completed"},
                {"description": "Step 2", "status": "completed"},
                {"description": "Step 3", "status": "in_progress"}
            ]
        }

        entries = [
            {"tool": "Edit", "input_preview": {"file": "/app/x.py"}, "timestamp": datetime.now().isoformat()}
        ]

        signal = detect_step_stall(state, entries, stall_multiplier=3.0)

        self.assertIsNone(signal)


class TestFormatDriftIntervention(unittest.TestCase):
    """Tests for intervention message formatting."""

    def test_formats_single_signal(self):
        """Should format a single drift signal."""
        signals = [
            DriftSignal(
                signal_type="FILE_CHURN",
                severity="warning",
                message="You've edited utils.py 4 times.",
                evidence={"file": "utils.py", "count": 4},
                suggestion="Consider stepping back."
            )
        ]

        output = format_drift_intervention(signals)

        self.assertIn("DRIFT DETECTED", output)
        self.assertIn("FILE_CHURN", output)
        self.assertIn("4 times", output)
        self.assertIn("stepping back", output)

    def test_formats_multiple_signals(self):
        """Should format multiple drift signals."""
        signals = [
            DriftSignal(
                signal_type="FILE_CHURN",
                severity="warning",
                message="File churn detected.",
                evidence={},
                suggestion="Step back."
            ),
            DriftSignal(
                signal_type="COMMAND_REPEAT",
                severity="critical",
                message="Command failing.",
                evidence={},
                suggestion="Try different approach."
            )
        ]

        output = format_drift_intervention(signals)

        self.assertIn("FILE_CHURN", output)
        self.assertIn("COMMAND_REPEAT", output)

    def test_sorts_by_severity(self):
        """Should show critical signals first."""
        signals = [
            DriftSignal(
                signal_type="FILE_CHURN",
                severity="info",
                message="Info level.",
                evidence={},
                suggestion=""
            ),
            DriftSignal(
                signal_type="COMMAND_REPEAT",
                severity="critical",
                message="Critical level.",
                evidence={},
                suggestion=""
            )
        ]

        output = format_drift_intervention(signals)

        # Critical should appear before info
        critical_pos = output.find("COMMAND_REPEAT")
        info_pos = output.find("FILE_CHURN")
        self.assertLess(critical_pos, info_pos)

    def test_empty_signals_returns_empty(self):
        """Should return empty string for no signals."""
        output = format_drift_intervention([])
        self.assertEqual(output, "")


class TestDetectDrift(unittest.TestCase):
    """Integration tests for the main detect_drift function."""

    def setUp(self):
        """Create temp directory for test session log."""
        self.temp_dir = tempfile.mkdtemp()
        self.session_log = Path(self.temp_dir) / "session.jsonl"

    def tearDown(self):
        """Clean up temp directory."""
        import shutil
        shutil.rmtree(self.temp_dir)

    def test_detect_drift_with_real_log(self):
        """Should detect drift from session log file."""
        # Create a session log with file churn
        base_time = datetime.now()
        entries = []
        for i in range(5):
            entries.append({
                "tool": "Edit",
                "input_preview": {"file": "/app/utils.py"},
                "timestamp": (base_time - timedelta(minutes=i)).isoformat(),
                "success": True
            })

        with open(self.session_log, 'w') as f:
            for entry in entries:
                f.write(json.dumps(entry) + "\n")

        signals = detect_drift(self.session_log, {}, lookback_minutes=60)

        self.assertTrue(len(signals) > 0)
        self.assertEqual(signals[0].signal_type, "FILE_CHURN")

    def test_detect_drift_empty_log(self):
        """Should return empty list for empty/missing log."""
        signals = detect_drift(self.session_log, {})
        self.assertEqual(signals, [])


class TestLoadRecentSessionEntries(unittest.TestCase):
    """Tests for session entry loading."""

    def setUp(self):
        """Create temp directory for test session log."""
        self.temp_dir = tempfile.mkdtemp()
        self.session_log = Path(self.temp_dir) / "session.jsonl"

    def tearDown(self):
        """Clean up temp directory."""
        import shutil
        shutil.rmtree(self.temp_dir)

    def test_loads_recent_entries(self):
        """Should load entries within lookback window."""
        now = datetime.now()
        entries = [
            {"tool": "Edit", "timestamp": now.isoformat()},
            {"tool": "Bash", "timestamp": (now - timedelta(minutes=5)).isoformat()},
            {"tool": "Read", "timestamp": (now - timedelta(hours=2)).isoformat()}  # Old
        ]

        with open(self.session_log, 'w') as f:
            for entry in entries:
                f.write(json.dumps(entry) + "\n")

        loaded = load_recent_session_entries(self.session_log, lookback_minutes=30)

        # Should only get the 2 recent entries
        self.assertEqual(len(loaded), 2)

    def test_handles_missing_file(self):
        """Should return empty list for missing file."""
        missing_path = Path(self.temp_dir) / "nonexistent.jsonl"
        loaded = load_recent_session_entries(missing_path)
        self.assertEqual(loaded, [])


if __name__ == "__main__":
    unittest.main()
