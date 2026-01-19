#!/usr/bin/env python3
"""
Tests for auto_checkpoint.py - Phase 10.4 Auto-Checkpoint

Tests cover:
- Breakpoint detection (time, tool calls, context, git commits)
- Checkpoint generation and storage
- Compaction offer formatting
- Integration with session state
"""
import json
import os
import sys
import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from unittest.mock import patch, MagicMock

# Add hooks directory to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from auto_checkpoint import (
    Checkpoint,
    BreakpointDetection,
    detect_time_breakpoint,
    detect_tool_calls_breakpoint,
    detect_context_breakpoint,
    detect_step_completion,
    detect_error_resolved,
    detect_git_commit,
    detect_breakpoint,
    generate_checkpoint,
    format_checkpoint_summary,
    offer_compaction,
    save_checkpoint,
    load_checkpoint,
    load_latest_checkpoint,
    reset_checkpoint_cooldown,
    _can_offer_checkpoint,
    _mark_checkpoint_offered,
    _extract_commit_message,
    _load_checkpoint_config,
    DEFAULT_TIME_THRESHOLD_MINUTES as TIME_THRESHOLD_MINUTES,
    DEFAULT_TOOL_CALLS_THRESHOLD as TOOL_CALLS_THRESHOLD,
    DEFAULT_CONTEXT_THRESHOLD_PERCENT as CONTEXT_THRESHOLD_PERCENT,
    DEFAULT_ERROR_RESOLVED_THRESHOLD as ERROR_RESOLVED_THRESHOLD,
)


class TestTimeBreakpoint(unittest.TestCase):
    """Tests for detect_time_breakpoint()."""

    def test_no_breakpoint_below_threshold(self):
        """Duration below threshold should not trigger breakpoint."""
        result = detect_time_breakpoint(15)
        self.assertIsNone(result)

    def test_breakpoint_at_threshold(self):
        """Duration at threshold should trigger breakpoint."""
        result = detect_time_breakpoint(TIME_THRESHOLD_MINUTES)
        self.assertIsNotNone(result)
        self.assertIn(str(TIME_THRESHOLD_MINUTES), result)

    def test_breakpoint_above_threshold(self):
        """Duration above threshold should trigger breakpoint."""
        result = detect_time_breakpoint(TIME_THRESHOLD_MINUTES + 15)
        self.assertIsNotNone(result)

    def test_message_includes_duration(self):
        """Message should include the duration."""
        result = detect_time_breakpoint(45)
        self.assertIn("45", result)
        self.assertIn("minutes", result.lower())


class TestToolCallsBreakpoint(unittest.TestCase):
    """Tests for detect_tool_calls_breakpoint()."""

    def test_no_breakpoint_below_threshold(self):
        """Tool calls below threshold should not trigger breakpoint."""
        result = detect_tool_calls_breakpoint(25)
        self.assertIsNone(result)

    def test_breakpoint_at_threshold(self):
        """Tool calls at threshold should trigger breakpoint."""
        result = detect_tool_calls_breakpoint(TOOL_CALLS_THRESHOLD)
        self.assertIsNotNone(result)
        self.assertIn(str(TOOL_CALLS_THRESHOLD), result)

    def test_breakpoint_above_threshold(self):
        """Tool calls above threshold should trigger breakpoint."""
        result = detect_tool_calls_breakpoint(TOOL_CALLS_THRESHOLD + 20)
        self.assertIsNotNone(result)


class TestContextBreakpoint(unittest.TestCase):
    """Tests for detect_context_breakpoint()."""

    def test_no_breakpoint_below_threshold(self):
        """Context below threshold should not trigger breakpoint."""
        result = detect_context_breakpoint(40)
        self.assertIsNone(result)

    def test_breakpoint_at_threshold(self):
        """Context at threshold should trigger breakpoint."""
        result = detect_context_breakpoint(CONTEXT_THRESHOLD_PERCENT)
        self.assertIsNotNone(result)
        self.assertIn(str(int(CONTEXT_THRESHOLD_PERCENT)), result)

    def test_breakpoint_high_context(self):
        """High context should trigger breakpoint."""
        result = detect_context_breakpoint(85)
        self.assertIsNotNone(result)
        self.assertIn("85", result)


class TestStepCompletion(unittest.TestCase):
    """Tests for detect_step_completion()."""

    def test_detects_step_complete_event(self):
        """Should detect 'step complete' in event."""
        result = detect_step_completion("step complete", {})
        self.assertIsNotNone(result)

    def test_detects_phase_complete_event(self):
        """Should detect 'phase complete' in event."""
        result = detect_step_completion("phase complete", {})
        self.assertIsNotNone(result)

    def test_detects_tests_passing_event(self):
        """Should detect 'tests passing' in event."""
        result = detect_step_completion("tests passing", {})
        self.assertIsNotNone(result)

    def test_no_detection_for_regular_event(self):
        """Should not detect for regular events."""
        result = detect_step_completion("edited file.py", {})
        self.assertIsNone(result)

    def test_detects_completed_step_in_state(self):
        """Should detect completed step in state."""
        state = {
            "plan": [
                {"description": "First step", "status": "completed"},
                {"description": "Second step", "status": "pending"},
            ]
        }
        result = detect_step_completion("", state)
        self.assertIsNotNone(result)
        self.assertIn("First step", result)


class TestErrorResolved(unittest.TestCase):
    """Tests for detect_error_resolved()."""

    def test_no_detection_below_threshold(self):
        """Should not trigger below threshold."""
        result = detect_error_resolved(5, 2)
        self.assertIsNone(result)

    def test_detection_at_threshold(self):
        """Should trigger at threshold."""
        result = detect_error_resolved(5, ERROR_RESOLVED_THRESHOLD)
        self.assertIsNotNone(result)
        self.assertIn(str(ERROR_RESOLVED_THRESHOLD), result)

    def test_detection_above_threshold(self):
        """Should trigger above threshold."""
        result = detect_error_resolved(10, 5)
        self.assertIsNotNone(result)


class TestGitCommitDetection(unittest.TestCase):
    """Tests for detect_git_commit()."""

    def test_detects_git_commit(self):
        """Should detect git commit command."""
        result = detect_git_commit("git commit -m 'Add feature'")
        self.assertIsNotNone(result)
        self.assertIn("Git commit", result)

    def test_no_detection_for_other_git(self):
        """Should not detect other git commands."""
        result = detect_git_commit("git status")
        self.assertIsNone(result)

    def test_no_detection_for_other_commands(self):
        """Should not detect non-git commands."""
        result = detect_git_commit("npm test")
        self.assertIsNone(result)


class TestDetectBreakpoint(unittest.TestCase):
    """Tests for detect_breakpoint()."""

    def test_no_breakpoint_low_values(self):
        """Should not detect breakpoint with low values."""
        metrics = {
            "session_duration_minutes": 5,
            "tool_calls": 10,
            "context_usage_percent": 20,
            "errors_encountered": 0,
            "errors_resolved": 0,
        }
        result = detect_breakpoint("edited file", {}, metrics)
        self.assertIsNone(result)

    def test_breakpoint_on_git_commit(self):
        """Should detect breakpoint on git commit."""
        metrics = {
            "session_duration_minutes": 10,
            "tool_calls": 20,
            "context_usage_percent": 30,
            "errors_encountered": 0,
            "errors_resolved": 0,
        }
        result = detect_breakpoint("git commit -m 'test'", {}, metrics)
        self.assertIsNotNone(result)
        self.assertTrue(result.is_breakpoint)
        self.assertEqual(result.urgency, "recommendation")

    def test_breakpoint_high_context(self):
        """Should detect urgent breakpoint on high context."""
        metrics = {
            "session_duration_minutes": 10,
            "tool_calls": 20,
            "context_usage_percent": 85,
            "errors_encountered": 0,
            "errors_resolved": 0,
        }
        result = detect_breakpoint("edited file", {}, metrics)
        self.assertIsNotNone(result)
        self.assertTrue(result.is_breakpoint)
        self.assertEqual(result.urgency, "urgent")

    def test_breakpoint_multiple_reasons(self):
        """Should include multiple reasons when applicable."""
        metrics = {
            "session_duration_minutes": 60,
            "tool_calls": 100,
            "context_usage_percent": 75,
            "errors_encountered": 5,
            "errors_resolved": 5,
        }
        result = detect_breakpoint("git commit -m 'test'", {}, metrics)
        self.assertIsNotNone(result)
        # Should have multiple reasons
        self.assertIn(";", result.reason)


class TestCheckpoint(unittest.TestCase):
    """Tests for Checkpoint dataclass."""

    def test_checkpoint_creation(self):
        """Should create checkpoint with all fields."""
        checkpoint = Checkpoint(
            checkpoint_id="test-001",
            timestamp=datetime.now().isoformat(),
            accomplished=["Task 1", "Task 2"],
            decisions=["Decision 1"],
            files_modified=["file1.py", "file2.py"],
            pending=["Task 3"],
            current_focus="Current work",
            context_usage_percent=50.0,
            tool_calls=25,
            session_duration_minutes=20.0,
        )
        self.assertEqual(checkpoint.checkpoint_id, "test-001")
        self.assertEqual(len(checkpoint.accomplished), 2)
        self.assertEqual(len(checkpoint.files_modified), 2)

    def test_checkpoint_to_dict(self):
        """Should convert checkpoint to dict."""
        checkpoint = Checkpoint(
            checkpoint_id="test-002",
            timestamp="2026-01-19T10:00:00",
            accomplished=["Done"],
            current_focus="Focus",
        )
        data = checkpoint.to_dict()
        self.assertEqual(data["checkpoint_id"], "test-002")
        self.assertEqual(data["accomplished"], ["Done"])

    def test_checkpoint_from_dict(self):
        """Should create checkpoint from dict."""
        data = {
            "checkpoint_id": "test-003",
            "timestamp": "2026-01-19T10:00:00",
            "accomplished": ["Task"],
            "decisions": [],
            "files_modified": ["file.py"],
            "pending": [],
            "current_focus": "Focus",
            "context_usage_percent": 30.0,
            "tool_calls": 15,
            "session_duration_minutes": 10.0,
            "errors_encountered": 1,
            "errors_resolved": 1,
        }
        checkpoint = Checkpoint.from_dict(data)
        self.assertEqual(checkpoint.checkpoint_id, "test-003")
        self.assertEqual(checkpoint.files_modified, ["file.py"])


class TestCheckpointStorage(unittest.TestCase):
    """Tests for checkpoint storage functions."""

    def setUp(self):
        """Create temp directory for checkpoints."""
        self.temp_dir = tempfile.mkdtemp()
        # Patch the checkpoints directory
        self.patcher = patch(
            'auto_checkpoint._get_checkpoints_dir',
            return_value=Path(self.temp_dir)
        )
        self.patcher.start()

    def tearDown(self):
        """Cleanup temp directory."""
        self.patcher.stop()
        import shutil
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_save_checkpoint(self):
        """Should save checkpoint to disk."""
        checkpoint = Checkpoint(
            checkpoint_id="ckpt-test-save",
            timestamp=datetime.now().isoformat(),
            accomplished=["Saved"],
        )
        filepath = save_checkpoint(checkpoint)
        self.assertTrue(filepath.exists())

    def test_load_checkpoint(self):
        """Should load saved checkpoint."""
        checkpoint = Checkpoint(
            checkpoint_id="ckpt-test-load",
            timestamp=datetime.now().isoformat(),
            accomplished=["Loaded"],
        )
        save_checkpoint(checkpoint)

        loaded = load_checkpoint("ckpt-test-load")
        self.assertIsNotNone(loaded)
        self.assertEqual(loaded.accomplished, ["Loaded"])

    def test_load_nonexistent_checkpoint(self):
        """Should return None for nonexistent checkpoint."""
        loaded = load_checkpoint("ckpt-nonexistent")
        self.assertIsNone(loaded)

    def test_load_latest_checkpoint(self):
        """Should load most recent checkpoint."""
        # Save multiple checkpoints
        for i in range(3):
            checkpoint = Checkpoint(
                checkpoint_id=f"ckpt-2026011{i}-{i:06d}",
                timestamp=datetime.now().isoformat(),
                accomplished=[f"Checkpoint {i}"],
            )
            save_checkpoint(checkpoint)

        latest = load_latest_checkpoint()
        self.assertIsNotNone(latest)
        # Should be the last one (highest ID when sorted)
        self.assertIn("Checkpoint", latest.accomplished[0])


class TestFormatCheckpointSummary(unittest.TestCase):
    """Tests for format_checkpoint_summary()."""

    def test_includes_checkpoint_id(self):
        """Summary should include checkpoint ID."""
        checkpoint = Checkpoint(
            checkpoint_id="ckpt-test-format",
            timestamp=datetime.now().isoformat(),
        )
        summary = format_checkpoint_summary(checkpoint)
        self.assertIn("ckpt-test-format", summary)

    def test_includes_accomplished(self):
        """Summary should include accomplished items."""
        checkpoint = Checkpoint(
            checkpoint_id="ckpt-test",
            timestamp=datetime.now().isoformat(),
            accomplished=["Built feature", "Fixed bug"],
        )
        summary = format_checkpoint_summary(checkpoint)
        self.assertIn("Built feature", summary)
        self.assertIn("Accomplished", summary)

    def test_includes_files(self):
        """Summary should include files modified."""
        checkpoint = Checkpoint(
            checkpoint_id="ckpt-test",
            timestamp=datetime.now().isoformat(),
            files_modified=["app.py", "test.py"],
        )
        summary = format_checkpoint_summary(checkpoint)
        self.assertIn("app.py", summary)
        self.assertIn("Files", summary)

    def test_includes_pending(self):
        """Summary should include pending items."""
        checkpoint = Checkpoint(
            checkpoint_id="ckpt-test",
            timestamp=datetime.now().isoformat(),
            pending=["Add tests", "Deploy"],
        )
        summary = format_checkpoint_summary(checkpoint)
        self.assertIn("Add tests", summary)
        self.assertIn("Pending", summary)

    def test_includes_metrics(self):
        """Summary should include session metrics."""
        checkpoint = Checkpoint(
            checkpoint_id="ckpt-test",
            timestamp=datetime.now().isoformat(),
            context_usage_percent=65.0,
            tool_calls=45,
            session_duration_minutes=30.0,
        )
        summary = format_checkpoint_summary(checkpoint)
        self.assertIn("65", summary)
        self.assertIn("45", summary)
        self.assertIn("30", summary)


class TestOfferCompaction(unittest.TestCase):
    """Tests for offer_compaction()."""

    def setUp(self):
        """Create mock checkpoint for testing."""
        self.checkpoint = Checkpoint(
            checkpoint_id="ckpt-test-offer",
            timestamp=datetime.now().isoformat(),
            accomplished=["Completed task"],
            files_modified=["file.py"],
            pending=["Next task"],
            context_usage_percent=70.0,
            tool_calls=50,
            session_duration_minutes=25.0,
        )

    def test_suggestion_format(self):
        """Suggestion urgency should use TIP header."""
        offer = offer_compaction(self.checkpoint, "suggestion")
        self.assertIn("SUGGESTION", offer)

    def test_recommendation_format(self):
        """Recommendation urgency should use AVAILABLE header."""
        offer = offer_compaction(self.checkpoint, "recommendation")
        self.assertIn("AVAILABLE", offer)

    def test_urgent_format(self):
        """Urgent urgency should use RECOMMENDED header."""
        offer = offer_compaction(self.checkpoint, "urgent")
        self.assertIn("RECOMMENDED", offer)
        self.assertIn("URGENT", offer)

    def test_includes_checkpoint_info(self):
        """Offer should include checkpoint summary."""
        offer = offer_compaction(self.checkpoint, "suggestion")
        self.assertIn("Completed task", offer)
        self.assertIn("file.py", offer)

    def test_includes_compaction_advice(self):
        """Offer should include compaction advice."""
        offer = offer_compaction(self.checkpoint, "suggestion")
        self.assertIn("compact", offer.lower())


class TestGenerateCheckpoint(unittest.TestCase):
    """Tests for generate_checkpoint()."""

    def test_generates_with_minimal_data(self):
        """Should generate checkpoint with minimal data."""
        with tempfile.TemporaryDirectory() as tmpdir:
            session_log = Path(tmpdir) / "session.jsonl"
            session_log.touch()

            state = {}
            metrics = {
                "context_usage_percent": 50,
                "tool_calls": 30,
                "session_duration_minutes": 20,
            }

            with patch('auto_checkpoint.extract_accomplished_from_log', return_value=[]):
                with patch('auto_checkpoint.extract_files_modified_from_log', return_value=[]):
                    checkpoint = generate_checkpoint(session_log, state, metrics)

            self.assertIsNotNone(checkpoint)
            self.assertTrue(checkpoint.checkpoint_id.startswith("ckpt-"))
            self.assertEqual(checkpoint.context_usage_percent, 50)

    def test_includes_state_data(self):
        """Should include data from state."""
        with tempfile.TemporaryDirectory() as tmpdir:
            session_log = Path(tmpdir) / "session.jsonl"
            session_log.touch()

            state = {
                "objective": "Build feature",
                "plan": [
                    {"description": "Step 1", "status": "completed"},
                    {"description": "Step 2", "status": "in_progress"},
                    {"description": "Step 3", "status": "pending"},
                ],
                "risks": ["Risk 1"],
            }
            metrics = {"context_usage_percent": 40, "tool_calls": 20, "session_duration_minutes": 15}

            with patch('auto_checkpoint.extract_accomplished_from_log', return_value=[]):
                with patch('auto_checkpoint.extract_files_modified_from_log', return_value=[]):
                    checkpoint = generate_checkpoint(session_log, state, metrics)

            self.assertEqual(checkpoint.current_focus, "Step 2")
            self.assertIn("Step 2", checkpoint.pending)
            self.assertIn("Step 3", checkpoint.pending)


class TestCooldown(unittest.TestCase):
    """Tests for checkpoint cooldown functionality."""

    def setUp(self):
        """Reset cooldown before each test."""
        reset_checkpoint_cooldown()

    def tearDown(self):
        """Reset cooldown after each test."""
        reset_checkpoint_cooldown()

    def test_can_offer_when_never_offered(self):
        """Should allow offer when never offered before."""
        self.assertTrue(_can_offer_checkpoint())

    def test_cannot_offer_immediately_after(self):
        """Should not allow offer immediately after previous offer."""
        _mark_checkpoint_offered()
        self.assertFalse(_can_offer_checkpoint())

    def test_can_offer_after_cooldown(self):
        """Should allow offer after cooldown period."""
        from datetime import timedelta
        import auto_checkpoint

        _mark_checkpoint_offered()
        # Simulate time passing by setting last offer to past
        auto_checkpoint._last_checkpoint_offer = datetime.now() - timedelta(minutes=15)
        self.assertTrue(_can_offer_checkpoint())

    def test_reset_allows_offer(self):
        """Reset should allow immediate offer."""
        _mark_checkpoint_offered()
        self.assertFalse(_can_offer_checkpoint())
        reset_checkpoint_cooldown()
        self.assertTrue(_can_offer_checkpoint())


class TestConfigLoading(unittest.TestCase):
    """Tests for config loading functionality."""

    def test_returns_defaults_when_no_config(self):
        """Should return defaults when config file doesn't exist."""
        with tempfile.TemporaryDirectory() as tmpdir:
            with patch('auto_checkpoint._get_config_path', return_value=Path(tmpdir) / "nonexistent.json"):
                config = _load_checkpoint_config()

        self.assertEqual(config["time_threshold_minutes"], TIME_THRESHOLD_MINUTES)
        self.assertEqual(config["tool_calls_threshold"], TOOL_CALLS_THRESHOLD)

    def test_loads_custom_config(self):
        """Should load custom config when file exists."""
        with tempfile.TemporaryDirectory() as tmpdir:
            config_path = Path(tmpdir) / "v8_config.json"
            config_data = {
                "checkpoint": {
                    "time_threshold_minutes": 45,
                    "cooldown_seconds": 300,
                }
            }
            with open(config_path, "w") as f:
                json.dump(config_data, f)

            with patch('auto_checkpoint._get_config_path', return_value=config_path):
                config = _load_checkpoint_config()

        self.assertEqual(config["time_threshold_minutes"], 45)
        self.assertEqual(config["cooldown_seconds"], 300)
        # Other values should be defaults
        self.assertEqual(config["tool_calls_threshold"], TOOL_CALLS_THRESHOLD)

    def test_handles_invalid_json(self):
        """Should return defaults for invalid JSON."""
        with tempfile.TemporaryDirectory() as tmpdir:
            config_path = Path(tmpdir) / "v8_config.json"
            with open(config_path, "w") as f:
                f.write("not valid json")

            with patch('auto_checkpoint._get_config_path', return_value=config_path):
                config = _load_checkpoint_config()

        self.assertEqual(config["time_threshold_minutes"], TIME_THRESHOLD_MINUTES)


class TestCommitMessageExtraction(unittest.TestCase):
    """Tests for _extract_commit_message()."""

    def test_extracts_standard_format(self):
        """Should extract message from standard git output."""
        output = "[main abc123] Add new feature"
        msg = _extract_commit_message(output)
        self.assertEqual(msg, "Add new feature")

    def test_extracts_with_branch_name(self):
        """Should extract message regardless of branch name."""
        output = "[feature/auth abc123] Implement login"
        msg = _extract_commit_message(output)
        self.assertEqual(msg, "Implement login")

    def test_handles_multiline_output(self):
        """Should take only first line after bracket."""
        output = "[main abc123] Fix bug\n 1 file changed, 5 insertions(+)"
        msg = _extract_commit_message(output)
        self.assertEqual(msg, "Fix bug")

    def test_truncates_long_messages(self):
        """Should truncate long messages to 50 chars."""
        long_msg = "A" * 100
        output = f"[main abc123] {long_msg}"
        msg = _extract_commit_message(output)
        self.assertEqual(len(msg), 50)

    def test_fallback_for_unknown_format(self):
        """Should return 'commit made' for unknown formats."""
        output = "Some other output format without brackets"
        msg = _extract_commit_message(output)
        self.assertEqual(msg, "commit made")

    def test_returns_none_for_empty(self):
        """Should return None for empty output."""
        self.assertIsNone(_extract_commit_message(""))
        self.assertIsNone(_extract_commit_message(None))


if __name__ == "__main__":
    unittest.main()
