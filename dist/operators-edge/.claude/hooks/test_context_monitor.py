#!/usr/bin/env python3
"""
Tests for Operator's Edge v8.0 - Context Monitor

Tests cover:
- Session entry loading
- Token estimation
- Context usage calculation
- Compression recommendations
- Checkpoint generation
- Intervention formatting
"""
import json
import os
import shutil
import sys
import tempfile
import unittest
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import patch, MagicMock

# Add hooks directory to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from context_monitor import (
    ContextEstimate,
    CompressionRecommendation,
    load_session_entries,
    estimate_entry_tokens,
    estimate_context_usage,
    should_compress,
    generate_checkpoint,
    format_context_intervention,
    check_context_and_recommend,
    WARN_THRESHOLD,
    COMPRESS_THRESHOLD,
    CRITICAL_THRESHOLD,
    LONG_SESSION_WARNING,
    VERY_LONG_SESSION,
)


class TestLoadSessionEntries(unittest.TestCase):
    """Tests for session entry loading."""

    def setUp(self):
        """Create temp directory for test session logs."""
        self.temp_dir = tempfile.mkdtemp()
        self.session_log = Path(self.temp_dir) / "test_session.jsonl"

    def tearDown(self):
        """Clean up temp directory."""
        shutil.rmtree(self.temp_dir)

    def test_loads_valid_entries(self):
        """Should load valid JSON entries from log."""
        entries = [
            {"tool": "Edit", "timestamp": "2026-01-17T10:00:00"},
            {"tool": "Bash", "timestamp": "2026-01-17T10:01:00"},
        ]
        with open(self.session_log, 'w') as f:
            for entry in entries:
                f.write(json.dumps(entry) + "\n")

        loaded = load_session_entries(self.session_log)
        self.assertEqual(len(loaded), 2)
        self.assertEqual(loaded[0]["tool"], "Edit")

    def test_handles_missing_file(self):
        """Should return empty list for missing file."""
        missing = Path(self.temp_dir) / "nonexistent.jsonl"
        loaded = load_session_entries(missing)
        self.assertEqual(loaded, [])

    def test_skips_invalid_json(self):
        """Should skip lines with invalid JSON."""
        with open(self.session_log, 'w') as f:
            f.write('{"tool": "Edit"}\n')
            f.write('not valid json\n')
            f.write('{"tool": "Bash"}\n')

        loaded = load_session_entries(self.session_log)
        self.assertEqual(len(loaded), 2)

    def test_handles_empty_lines(self):
        """Should skip empty lines."""
        with open(self.session_log, 'w') as f:
            f.write('{"tool": "Edit"}\n')
            f.write('\n')
            f.write('   \n')
            f.write('{"tool": "Bash"}\n')

        loaded = load_session_entries(self.session_log)
        self.assertEqual(len(loaded), 2)


class TestEstimateEntryTokens(unittest.TestCase):
    """Tests for individual entry token estimation."""

    def test_estimates_dict_input(self):
        """Should estimate tokens from dict input."""
        entry = {
            "input_preview": {"file_path": "/app/test.py", "content": "x" * 100},
            "output_preview": "y" * 200
        }
        tokens = estimate_entry_tokens(entry)
        # Should be > 0 based on character count
        self.assertGreater(tokens, 0)

    def test_estimates_string_input(self):
        """Should estimate tokens from string input."""
        entry = {
            "input_preview": "a" * 400,
            "output_preview": "b" * 400
        }
        tokens = estimate_entry_tokens(entry)
        # 800 chars / 4 chars per token = 200 tokens
        self.assertEqual(tokens, 200)

    def test_handles_missing_fields(self):
        """Should handle entries without input/output."""
        entry = {}
        tokens = estimate_entry_tokens(entry)
        self.assertEqual(tokens, 0)

    def test_handles_none_output(self):
        """Should handle None output preview."""
        entry = {
            "input_preview": "test",
            "output_preview": None
        }
        tokens = estimate_entry_tokens(entry)
        self.assertGreaterEqual(tokens, 0)


class TestEstimateContextUsage(unittest.TestCase):
    """Tests for full context usage estimation."""

    def setUp(self):
        """Create temp directory for test session logs."""
        self.temp_dir = tempfile.mkdtemp()
        self.session_log = Path(self.temp_dir) / "test_session.jsonl"

    def tearDown(self):
        """Clean up temp directory."""
        shutil.rmtree(self.temp_dir)

    def test_empty_log_returns_empty_estimate(self):
        """Should return zero estimate for empty log."""
        estimate = estimate_context_usage(self.session_log)
        self.assertEqual(estimate.tool_calls, 0)
        self.assertEqual(estimate.estimated_tokens, 0)

    def test_counts_tool_calls(self):
        """Should count total tool calls."""
        base_time = datetime.now()
        entries = [
            {"tool": "Edit", "timestamp": base_time.isoformat()},
            {"tool": "Bash", "timestamp": (base_time + timedelta(minutes=1)).isoformat()},
            {"tool": "Read", "timestamp": (base_time + timedelta(minutes=2)).isoformat()},
        ]
        with open(self.session_log, 'w') as f:
            for entry in entries:
                f.write(json.dumps(entry) + "\n")

        estimate = estimate_context_usage(self.session_log)
        self.assertEqual(estimate.tool_calls, 3)

    def test_tracks_files_read(self):
        """Should count Read operations."""
        base_time = datetime.now()
        entries = [
            {"tool": "Read", "timestamp": base_time.isoformat()},
            {"tool": "Read", "timestamp": (base_time + timedelta(minutes=1)).isoformat()},
            {"tool": "Edit", "timestamp": (base_time + timedelta(minutes=2)).isoformat()},
        ]
        with open(self.session_log, 'w') as f:
            for entry in entries:
                f.write(json.dumps(entry) + "\n")

        estimate = estimate_context_usage(self.session_log)
        self.assertEqual(estimate.files_read, 2)
        self.assertEqual(estimate.files_written, 1)

    def test_calculates_session_duration(self):
        """Should calculate session duration from timestamps."""
        base_time = datetime.now()
        entries = [
            {"tool": "Edit", "timestamp": base_time.isoformat()},
            {"tool": "Edit", "timestamp": (base_time + timedelta(minutes=30)).isoformat()},
        ]
        with open(self.session_log, 'w') as f:
            for entry in entries:
                f.write(json.dumps(entry) + "\n")

        estimate = estimate_context_usage(self.session_log)
        self.assertAlmostEqual(estimate.session_duration_minutes, 30, delta=0.1)

    def test_computes_usage_percentage(self):
        """Should compute usage as percentage of estimated window."""
        base_time = datetime.now()
        # Create entries with substantial content
        entries = []
        for i in range(50):
            entries.append({
                "tool": "Read",
                "timestamp": (base_time + timedelta(minutes=i)).isoformat(),
                "input_preview": "x" * 1000,
                "output_preview": "y" * 1000
            })

        with open(self.session_log, 'w') as f:
            for entry in entries:
                f.write(json.dumps(entry) + "\n")

        estimate = estimate_context_usage(self.session_log)
        # Should have some percentage usage
        self.assertGreater(estimate.usage_percentage, 0)
        self.assertLessEqual(estimate.usage_percentage, 1.0)

    def test_tracks_tool_breakdown(self):
        """Should track per-tool call counts."""
        base_time = datetime.now()
        entries = [
            {"tool": "Edit", "timestamp": base_time.isoformat()},
            {"tool": "Edit", "timestamp": (base_time + timedelta(minutes=1)).isoformat()},
            {"tool": "Bash", "timestamp": (base_time + timedelta(minutes=2)).isoformat()},
        ]
        with open(self.session_log, 'w') as f:
            for entry in entries:
                f.write(json.dumps(entry) + "\n")

        estimate = estimate_context_usage(self.session_log)
        self.assertEqual(estimate.tool_breakdown.get("Edit", 0), 2)
        self.assertEqual(estimate.tool_breakdown.get("Bash", 0), 1)


class TestShouldCompress(unittest.TestCase):
    """Tests for compression recommendation logic."""

    def test_no_compression_low_usage(self):
        """Should not recommend compression for low usage."""
        estimate = ContextEstimate(
            usage_percentage=0.30,
            session_duration_minutes=20
        )
        rec = should_compress(estimate)
        self.assertFalse(rec.should_compress)
        self.assertEqual(rec.severity, "none")

    def test_info_at_warn_threshold(self):
        """Should return info severity at warn threshold."""
        estimate = ContextEstimate(
            usage_percentage=WARN_THRESHOLD + 0.01,
            session_duration_minutes=20
        )
        rec = should_compress(estimate)
        self.assertEqual(rec.severity, "info")

    def test_warning_at_compress_threshold(self):
        """Should recommend compression at compress threshold."""
        estimate = ContextEstimate(
            usage_percentage=COMPRESS_THRESHOLD + 0.01,
            session_duration_minutes=20
        )
        rec = should_compress(estimate)
        self.assertTrue(rec.should_compress)
        self.assertEqual(rec.severity, "warning")

    def test_critical_at_critical_threshold(self):
        """Should return critical at critical threshold."""
        estimate = ContextEstimate(
            usage_percentage=CRITICAL_THRESHOLD + 0.01,
            session_duration_minutes=20
        )
        rec = should_compress(estimate)
        self.assertTrue(rec.should_compress)
        self.assertEqual(rec.severity, "critical")

    def test_warning_for_very_long_session(self):
        """Should warn for very long sessions even with low token usage."""
        estimate = ContextEstimate(
            usage_percentage=0.20,
            session_duration_minutes=VERY_LONG_SESSION + 5
        )
        rec = should_compress(estimate)
        self.assertTrue(rec.should_compress)
        self.assertEqual(rec.severity, "warning")
        self.assertIn("minutes", rec.reason)

    def test_info_for_long_session(self):
        """Should info for long (but not very long) sessions."""
        estimate = ContextEstimate(
            usage_percentage=0.20,
            session_duration_minutes=LONG_SESSION_WARNING + 5
        )
        rec = should_compress(estimate)
        self.assertEqual(rec.severity, "info")


class TestGenerateCheckpoint(unittest.TestCase):
    """Tests for checkpoint generation."""

    def setUp(self):
        """Create temp directory for test session logs."""
        self.temp_dir = tempfile.mkdtemp()
        self.session_log = Path(self.temp_dir) / "test_session.jsonl"

    def tearDown(self):
        """Clean up temp directory."""
        shutil.rmtree(self.temp_dir)

    def test_includes_objective(self):
        """Should include objective in checkpoint."""
        state = {"objective": "Test objective here"}

        # Create minimal log
        with open(self.session_log, 'w') as f:
            f.write('{"tool": "Edit", "timestamp": "2026-01-17T10:00:00"}\n')

        checkpoint = generate_checkpoint(state, self.session_log)
        self.assertIn("Test objective here", checkpoint)

    def test_includes_progress(self):
        """Should include step progress."""
        state = {
            "objective": "Test",
            "plan": [
                {"description": "Step 1", "status": "completed"},
                {"description": "Step 2", "status": "in_progress"},
                {"description": "Step 3", "status": "pending"},
            ]
        }

        with open(self.session_log, 'w') as f:
            f.write('{"tool": "Edit", "timestamp": "2026-01-17T10:00:00"}\n')

        checkpoint = generate_checkpoint(state, self.session_log)
        self.assertIn("1/3", checkpoint)  # 1 completed of 3 total
        self.assertIn("Step 1", checkpoint)
        self.assertIn("Step 2", checkpoint)

    def test_includes_recent_failures(self):
        """Should include recent failures."""
        state = {"objective": "Test"}
        base_time = datetime.now()

        entries = [
            {
                "tool": "Bash",
                "success": False,
                "output_preview": "Error: command not found",
                "timestamp": base_time.isoformat()
            }
        ]

        with open(self.session_log, 'w') as f:
            for entry in entries:
                f.write(json.dumps(entry) + "\n")

        checkpoint = generate_checkpoint(state, self.session_log)
        self.assertIn("Recent Issues", checkpoint)

    def test_includes_churned_files(self):
        """Should include files with high edit counts."""
        state = {"objective": "Test"}
        base_time = datetime.now()

        entries = []
        for i in range(5):
            entries.append({
                "tool": "Edit",
                "input_preview": {"file_path": "/app/utils.py"},
                "timestamp": (base_time + timedelta(minutes=i)).isoformat(),
                "success": True
            })

        with open(self.session_log, 'w') as f:
            for entry in entries:
                f.write(json.dumps(entry) + "\n")

        checkpoint = generate_checkpoint(state, self.session_log)
        self.assertIn("High Edit Count", checkpoint)
        self.assertIn("utils.py", checkpoint)

    def test_includes_session_stats(self):
        """Should include session statistics."""
        state = {"objective": "Test"}
        base_time = datetime.now()

        entries = [
            {"tool": "Read", "timestamp": base_time.isoformat(), "success": True},
            {"tool": "Edit", "timestamp": (base_time + timedelta(minutes=30)).isoformat(), "success": True},
        ]

        with open(self.session_log, 'w') as f:
            for entry in entries:
                f.write(json.dumps(entry) + "\n")

        checkpoint = generate_checkpoint(state, self.session_log)
        self.assertIn("Session Statistics", checkpoint)
        self.assertIn("Tool calls:", checkpoint)


class TestFormatContextIntervention(unittest.TestCase):
    """Tests for intervention message formatting."""

    def test_empty_for_none_severity(self):
        """Should return empty string for 'none' severity."""
        rec = CompressionRecommendation(
            should_compress=False,
            severity="none",
            reason="All good",
            suggestion=""
        )
        estimate = ContextEstimate()
        output = format_context_intervention(rec, estimate)
        self.assertEqual(output, "")

    def test_includes_severity_indicator(self):
        """Should include severity indicator icon."""
        rec = CompressionRecommendation(
            should_compress=True,
            severity="critical",
            reason="Context at 95%",
            suggestion="Compress now"
        )
        estimate = ContextEstimate(estimated_tokens=190000)
        output = format_context_intervention(rec, estimate)
        self.assertIn("🔴", output)
        self.assertIn("CRITICAL", output)

    def test_includes_metrics(self):
        """Should include context metrics."""
        rec = CompressionRecommendation(
            should_compress=True,
            severity="warning",
            reason="Context at 80%",
            suggestion="Consider compressing"
        )
        estimate = ContextEstimate(
            estimated_tokens=160000,
            session_duration_minutes=45,
            tool_calls=50,
            files_read=10
        )
        output = format_context_intervention(rec, estimate)
        self.assertIn("160,000", output)  # tokens with comma
        self.assertIn("45", output)  # duration
        self.assertIn("50", output)  # tool calls

    def test_includes_suggestion(self):
        """Should include recommendation suggestion."""
        rec = CompressionRecommendation(
            should_compress=True,
            severity="warning",
            reason="Test reason",
            suggestion="Test suggestion here"
        )
        estimate = ContextEstimate()
        output = format_context_intervention(rec, estimate)
        self.assertIn("Test suggestion here", output)


class TestCheckContextAndRecommend(unittest.TestCase):
    """Integration tests for main interface."""

    def setUp(self):
        """Create temp directory for test session logs."""
        self.temp_dir = tempfile.mkdtemp()
        self.session_log = Path(self.temp_dir) / "test_session.jsonl"

    def tearDown(self):
        """Clean up temp directory."""
        shutil.rmtree(self.temp_dir)

    def test_returns_estimate_and_recommendation(self):
        """Should return both estimate and recommendation."""
        state = {"objective": "Test"}

        with open(self.session_log, 'w') as f:
            f.write('{"tool": "Edit", "timestamp": "2026-01-17T10:00:00"}\n')

        estimate, rec = check_context_and_recommend(self.session_log, state)

        self.assertIsInstance(estimate, ContextEstimate)
        self.assertIsInstance(rec, CompressionRecommendation)

    def test_generates_checkpoint_when_compressing(self):
        """Should generate checkpoint when compression recommended."""
        state = {"objective": "Test objective"}
        base_time = datetime.now()

        # Create many entries to trigger compression
        entries = []
        for i in range(100):
            entries.append({
                "tool": "Read",
                "timestamp": (base_time + timedelta(minutes=i)).isoformat(),
                "input_preview": "x" * 2000,
                "output_preview": "y" * 2000,
                "success": True
            })

        with open(self.session_log, 'w') as f:
            for entry in entries:
                f.write(json.dumps(entry) + "\n")

        estimate, rec = check_context_and_recommend(self.session_log, state)

        # If compression is recommended, checkpoint should be generated
        if rec.should_compress:
            self.assertIsNotNone(rec.checkpoint_summary)
            self.assertIn("Test objective", rec.checkpoint_summary)


class TestContextEstimateDataclass(unittest.TestCase):
    """Tests for ContextEstimate dataclass."""

    def test_to_dict(self):
        """Should convert to dictionary."""
        estimate = ContextEstimate(
            tool_calls=10,
            estimated_tokens=5000,
            usage_percentage=0.025,
            session_duration_minutes=15.5
        )
        d = estimate.to_dict()

        self.assertEqual(d["tool_calls"], 10)
        self.assertEqual(d["estimated_tokens"], 5000)
        self.assertEqual(d["usage_percentage"], 2.5)  # Converted to percentage
        self.assertEqual(d["session_duration_minutes"], 15.5)

    def test_default_values(self):
        """Should have sensible defaults."""
        estimate = ContextEstimate()

        self.assertEqual(estimate.tool_calls, 0)
        self.assertEqual(estimate.estimated_tokens, 0)
        self.assertEqual(estimate.usage_percentage, 0.0)
        self.assertEqual(estimate.tool_breakdown, {})


if __name__ == "__main__":
    unittest.main()
