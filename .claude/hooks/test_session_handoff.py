#!/usr/bin/env python3
"""
Tests for Operator's Edge v8.0 - Session Handoff

Tests cover:
- Handoff generation from state and session log
- Approach extraction from session history
- Handoff storage and retrieval
- Handoff formatting for injection
- Integration with other v8.0 modules
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

from session_handoff import (
    ApproachTried,
    HandoffSummary,
    generate_handoff_summary,
    format_handoff_for_injection,
    save_handoff,
    load_latest_handoff,
    load_handoff_by_session,
    get_handoff_for_new_session,
    _extract_approaches_from_log,
    _get_handoffs_dir,
    _cleanup_old_handoffs,
)


class TestApproachTriedDataclass(unittest.TestCase):
    """Tests for ApproachTried dataclass."""

    def test_to_dict(self):
        """Should serialize to dict."""
        approach = ApproachTried(
            description="Test approach",
            outcome="success",
            reason="It worked",
            commands_run=["pytest"],
            files_modified=["test.py"]
        )

        d = approach.to_dict()

        self.assertEqual(d["description"], "Test approach")
        self.assertEqual(d["outcome"], "success")
        self.assertEqual(d["commands_run"], ["pytest"])

    def test_from_dict(self):
        """Should deserialize from dict."""
        data = {
            "description": "Test",
            "outcome": "failed",
            "reason": "Error occurred",
            "commands_run": ["cmd"],
            "files_modified": ["file.py"]
        }

        approach = ApproachTried.from_dict(data)

        self.assertEqual(approach.description, "Test")
        self.assertEqual(approach.outcome, "failed")


class TestHandoffSummaryDataclass(unittest.TestCase):
    """Tests for HandoffSummary dataclass."""

    def test_to_dict(self):
        """Should serialize to dict."""
        handoff = HandoffSummary(
            objective="Test objective",
            progress="1/3 steps",
            active_problem="Testing",
            next_action="Continue",
            context_usage_percent=50.0,
            session_id="test-123"
        )

        d = handoff.to_dict()

        self.assertEqual(d["objective"], "Test objective")
        self.assertEqual(d["progress"], "1/3 steps")
        self.assertEqual(d["context_usage_percent"], 50.0)

    def test_from_dict(self):
        """Should deserialize from dict."""
        data = {
            "objective": "Test",
            "progress": "2/4",
            "active_problem": "Problem",
            "next_action": "Next",
            "approaches_tried": [
                {"description": "Try 1", "outcome": "failed", "reason": "Error"}
            ],
            "drift_warnings": ["FILE_CHURN: test.py"],
            "session_id": "sess-1"
        }

        handoff = HandoffSummary.from_dict(data)

        self.assertEqual(handoff.objective, "Test")
        self.assertEqual(len(handoff.approaches_tried), 1)
        self.assertEqual(handoff.approaches_tried[0].outcome, "failed")


class TestHandoffStorage(unittest.TestCase):
    """Tests for handoff storage operations."""

    def setUp(self):
        """Create temp directory for handoffs."""
        self.temp_dir = tempfile.mkdtemp()

    def tearDown(self):
        """Clean up temp directory."""
        shutil.rmtree(self.temp_dir)

    @patch('session_handoff._get_handoffs_dir')
    def test_save_and_load_handoff(self, mock_dir):
        """Should save and load handoff."""
        mock_dir.return_value = Path(self.temp_dir)

        handoff = HandoffSummary(
            objective="Test save",
            progress="1/1",
            active_problem="Testing save",
            next_action="Verify load",
            session_id="test-save"
        )

        # Save
        path = save_handoff(handoff)
        self.assertTrue(path.exists())

        # Load
        loaded = load_latest_handoff()
        self.assertIsNotNone(loaded)
        self.assertEqual(loaded.objective, "Test save")
        self.assertEqual(loaded.session_id, "test-save")

    @patch('session_handoff._get_handoffs_dir')
    def test_load_handoff_by_session(self, mock_dir):
        """Should load handoff by session ID."""
        mock_dir.return_value = Path(self.temp_dir)

        # Save multiple handoffs with unique timestamps
        import time
        for i in range(3):
            handoff = HandoffSummary(
                objective=f"Objective {i}",
                progress="1/1",
                active_problem="Test",
                next_action="Next",
                session_id=f"session-{i}"
            )
            # Write directly to avoid timestamp collision
            filepath = Path(self.temp_dir) / f"handoff-2026010{i}-12000{i}.json"
            with open(filepath, 'w') as f:
                json.dump(handoff.to_dict(), f)

        # Load specific session
        loaded = load_handoff_by_session("session-1")
        self.assertIsNotNone(loaded)
        self.assertEqual(loaded.session_id, "session-1")
        self.assertEqual(loaded.objective, "Objective 1")

    @patch('session_handoff._get_handoffs_dir')
    def test_returns_none_for_missing_handoff(self, mock_dir):
        """Should return None for missing handoff."""
        mock_dir.return_value = Path(self.temp_dir)

        loaded = load_latest_handoff()
        self.assertIsNone(loaded)

    @patch('session_handoff._get_handoffs_dir')
    def test_cleanup_old_handoffs(self, mock_dir):
        """Should cleanup old handoffs beyond retention limit."""
        mock_dir.return_value = Path(self.temp_dir)

        # Create 15 handoffs (limit is 10)
        for i in range(15):
            handoff = HandoffSummary(
                objective=f"Obj {i}",
                progress="1/1",
                active_problem="Test",
                next_action="Next",
                session_id=f"sess-{i:02d}"
            )
            save_handoff(handoff)

        # Check that only MAX_HANDOFFS remain
        handoff_files = list(Path(self.temp_dir).glob("handoff-*.json"))
        self.assertLessEqual(len(handoff_files), 10)


class TestHandoffGeneration(unittest.TestCase):
    """Tests for handoff generation from state and session log."""

    def setUp(self):
        """Create temp directory for session logs."""
        self.temp_dir = tempfile.mkdtemp()
        self.session_log = Path(self.temp_dir) / "session.jsonl"

    def tearDown(self):
        """Clean up temp directory."""
        shutil.rmtree(self.temp_dir)

    def test_generates_from_state(self):
        """Should generate handoff from state."""
        state = {
            "objective": "Test objective",
            "plan": [
                {"description": "Step 1", "status": "completed"},
                {"description": "Step 2", "status": "in_progress"},
                {"description": "Step 3", "status": "pending"},
            ],
            "risks": ["Risk 1"],
        }

        # Create minimal log
        with open(self.session_log, 'w') as f:
            f.write('{"tool": "Edit", "timestamp": "2026-01-18T10:00:00"}\n')

        handoff = generate_handoff_summary(state, self.session_log, "test-session")

        self.assertEqual(handoff.objective, "Test objective")
        self.assertEqual(handoff.progress, "1/3 steps complete")
        self.assertIn("Step 2", handoff.active_problem)
        self.assertIn("Step 3", handoff.next_action)

    def test_handles_empty_plan(self):
        """Should handle state with no plan."""
        state = {
            "objective": "No plan objective",
            "plan": []
        }

        with open(self.session_log, 'w') as f:
            f.write('{"tool": "Read", "timestamp": "2026-01-18T10:00:00"}\n')

        handoff = generate_handoff_summary(state, self.session_log)

        self.assertEqual(handoff.progress, "0/0 steps complete")
        self.assertIn("No plan defined", handoff.active_problem)

    def test_handles_all_completed(self):
        """Should handle state with all steps completed."""
        state = {
            "objective": "Completed objective",
            "plan": [
                {"description": "Step 1", "status": "completed"},
                {"description": "Step 2", "status": "completed"},
            ]
        }

        with open(self.session_log, 'w') as f:
            f.write('{"tool": "Edit", "timestamp": "2026-01-18T10:00:00"}\n')

        handoff = generate_handoff_summary(state, self.session_log)

        self.assertEqual(handoff.progress, "2/2 steps complete")
        self.assertIn("complete", handoff.active_problem.lower())

    def test_includes_key_insights(self):
        """Should include risks and constraints as insights."""
        state = {
            "objective": "Test",
            "plan": [],
            "risks": ["Risk A", "Risk B"],
            "constraints": ["Constraint X"],
        }

        with open(self.session_log, 'w') as f:
            f.write('{"tool": "Read", "timestamp": "2026-01-18T10:00:00"}\n')

        handoff = generate_handoff_summary(state, self.session_log)

        self.assertGreater(len(handoff.key_insights), 0)
        self.assertTrue(any("Risk A" in i for i in handoff.key_insights))


class TestApproachExtraction(unittest.TestCase):
    """Tests for extracting approaches from session log."""

    def setUp(self):
        """Create temp directory for session logs."""
        self.temp_dir = tempfile.mkdtemp()
        self.session_log = Path(self.temp_dir) / "session.jsonl"

    def tearDown(self):
        """Clean up temp directory."""
        shutil.rmtree(self.temp_dir)

    def test_extracts_failed_then_success(self):
        """Should extract approach when command fails then succeeds."""
        entries = [
            {"tool": "Bash", "input_preview": {"command": "pytest"}, "success": False, "output_preview": "FAILED", "timestamp": "2026-01-18T10:00:00"},
            {"tool": "Bash", "input_preview": {"command": "pytest"}, "success": True, "output_preview": "PASSED", "timestamp": "2026-01-18T10:01:00"},
        ]

        with open(self.session_log, 'w') as f:
            for entry in entries:
                f.write(json.dumps(entry) + "\n")

        approaches = _extract_approaches_from_log(self.session_log)

        self.assertGreater(len(approaches), 0)
        success_approaches = [a for a in approaches if a.outcome == "success"]
        self.assertGreater(len(success_approaches), 0)

    def test_extracts_high_churn_files(self):
        """Should extract approach for files with many edits."""
        base_time = datetime.now()
        entries = []
        for i in range(5):
            entries.append({
                "tool": "Edit",
                "input_preview": {"file_path": "/app/churned.py"},
                "success": True,
                "timestamp": (base_time + timedelta(minutes=i)).isoformat()
            })

        with open(self.session_log, 'w') as f:
            for entry in entries:
                f.write(json.dumps(entry) + "\n")

        approaches = _extract_approaches_from_log(self.session_log)

        churn_approaches = [a for a in approaches if "churned.py" in str(a.files_modified)]
        self.assertGreater(len(churn_approaches), 0)

    def test_handles_empty_log(self):
        """Should handle empty session log."""
        with open(self.session_log, 'w') as f:
            pass

        approaches = _extract_approaches_from_log(self.session_log)

        self.assertEqual(approaches, [])


class TestHandoffFormatting(unittest.TestCase):
    """Tests for handoff formatting for injection."""

    def test_formats_basic_handoff(self):
        """Should format handoff with basic info."""
        handoff = HandoffSummary(
            objective="Test formatting",
            progress="2/5 steps",
            active_problem="Working on step 3",
            next_action="Continue testing",
            session_id="test-format"
        )

        formatted = format_handoff_for_injection(handoff)

        self.assertIn("PREVIOUS SESSION HANDOFF", formatted)
        self.assertIn("Test formatting", formatted)
        self.assertIn("2/5 steps", formatted)
        self.assertIn("Working on step 3", formatted)

    def test_formats_approaches_tried(self):
        """Should format approaches with icons."""
        handoff = HandoffSummary(
            objective="Test",
            progress="1/1",
            active_problem="Test",
            next_action="Next",
            approaches_tried=[
                ApproachTried("Successful approach", "success", "Worked"),
                ApproachTried("Failed approach", "failed", "Did not work"),
            ]
        )

        formatted = format_handoff_for_injection(handoff)

        self.assertIn("Approaches Tried", formatted)
        self.assertIn("✓", formatted)  # Success icon
        self.assertIn("✗", formatted)  # Failure icon

    def test_formats_drift_warnings(self):
        """Should prominently show drift warnings."""
        handoff = HandoffSummary(
            objective="Test",
            progress="1/1",
            active_problem="Test",
            next_action="Next",
            drift_warnings=["FILE_CHURN: test.py edited 5 times"]
        )

        formatted = format_handoff_for_injection(handoff)

        self.assertIn("Drift Warnings", formatted)
        self.assertIn("FILE_CHURN", formatted)
        self.assertIn("⚠️", formatted)

    def test_formats_churned_files(self):
        """Should show churned files."""
        handoff = HandoffSummary(
            objective="Test",
            progress="1/1",
            active_problem="Test",
            next_action="Next",
            churned_files=[("/app/utils.py", 4), ("/app/main.py", 3)]
        )

        formatted = format_handoff_for_injection(handoff)

        self.assertIn("Multiple Edits", formatted)
        self.assertIn("utils.py", formatted)
        self.assertIn("4 edits", formatted)

    def test_formats_session_stats(self):
        """Should include session statistics."""
        handoff = HandoffSummary(
            objective="Test",
            progress="1/1",
            active_problem="Test",
            next_action="Next",
            context_usage_percent=75.5,
            session_duration_minutes=45.0,
            tool_calls=50
        )

        formatted = format_handoff_for_injection(handoff)

        self.assertIn("45", formatted)  # Duration
        self.assertIn("50", formatted)  # Tool calls
        # Context usage could be 75 or 76 due to rounding
        self.assertTrue("75" in formatted or "76" in formatted)  # Context usage


class TestGetHandoffForNewSession(unittest.TestCase):
    """Tests for getting handoff at session start."""

    def setUp(self):
        """Create temp directory for handoffs."""
        self.temp_dir = tempfile.mkdtemp()

    def tearDown(self):
        """Clean up temp directory."""
        shutil.rmtree(self.temp_dir)

    @patch('session_handoff._get_handoffs_dir')
    def test_returns_none_when_no_handoff(self, mock_dir):
        """Should return None when no handoff exists."""
        mock_dir.return_value = Path(self.temp_dir)

        result = get_handoff_for_new_session()

        self.assertIsNone(result)

    @patch('session_handoff._get_handoffs_dir')
    def test_returns_formatted_recent_handoff(self, mock_dir):
        """Should return formatted handoff if recent."""
        mock_dir.return_value = Path(self.temp_dir)

        handoff = HandoffSummary(
            objective="Recent objective",
            progress="1/2",
            active_problem="Working",
            next_action="Continue",
            created_at=datetime.now().isoformat()
        )
        save_handoff(handoff)

        result = get_handoff_for_new_session()

        self.assertIsNotNone(result)
        self.assertIn("Recent objective", result)

    @patch('session_handoff._get_handoffs_dir')
    def test_returns_none_for_old_handoff(self, mock_dir):
        """Should return None for handoff older than 24 hours."""
        mock_dir.return_value = Path(self.temp_dir)

        old_time = datetime.now() - timedelta(hours=30)
        handoff = HandoffSummary(
            objective="Old objective",
            progress="1/1",
            active_problem="Done",
            next_action="Nothing",
            created_at=old_time.isoformat()
        )
        save_handoff(handoff)

        result = get_handoff_for_new_session()

        self.assertIsNone(result)


if __name__ == "__main__":
    unittest.main()
