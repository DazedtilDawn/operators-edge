#!/usr/bin/env python3
"""
Tests for dispatch_utils.py - dispatch mode orchestration utilities.

Tests the core functions for:
- State management (load, save, update)
- Orchestration logic (next action, stuck detection)
- Dispatch flow control
- Scout mode utilities
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

from dispatch_config import DispatchState, JunctionType


class TestLoadDispatchState(unittest.TestCase):
    """Tests for load_dispatch_state() function."""

    @patch('dispatch_utils.load_yaml_state')
    @patch('dispatch_utils.get_state_dir')
    @patch('dispatch_utils.get_default_dispatch_state')
    @patch('dispatch_utils.get_default_scout_state')
    def test_loads_existing_state(self, mock_scout, mock_default, mock_state_dir, mock_load_yaml):
        """load_dispatch_state() should load from JSON file if exists (fallback)."""
        from dispatch_utils import load_dispatch_state

        mock_load_yaml.return_value = None  # Force JSON fallback

        with tempfile.TemporaryDirectory() as tmpdir:
            mock_state_dir.return_value = Path(tmpdir)

            state_file = Path(tmpdir) / "dispatch_state.json"
            state_file.write_text('{"enabled": true, "iteration": 5}')

            result = load_dispatch_state()

            self.assertTrue(result["enabled"])
            self.assertEqual(result["iteration"], 5)

    @patch('dispatch_utils.load_yaml_state')
    @patch('dispatch_utils.get_state_dir')
    @patch('dispatch_utils.get_default_dispatch_state')
    @patch('dispatch_utils.get_default_scout_state')
    def test_returns_default_if_missing(self, mock_scout, mock_default, mock_state_dir, mock_load_yaml):
        """load_dispatch_state() should return default if file missing."""
        from dispatch_utils import load_dispatch_state

        mock_load_yaml.return_value = None  # Force JSON fallback

        with tempfile.TemporaryDirectory() as tmpdir:
            mock_state_dir.return_value = Path(tmpdir)
            mock_default.return_value = {"enabled": False}
            mock_scout.return_value = {}

            result = load_dispatch_state()

            self.assertEqual(result["enabled"], False)

    @patch('dispatch_utils.load_yaml_state')
    @patch('dispatch_utils.get_state_dir')
    @patch('dispatch_utils.get_default_dispatch_state')
    @patch('dispatch_utils.get_default_scout_state')
    def test_adds_scout_state_if_missing(self, mock_scout, mock_default, mock_state_dir, mock_load_yaml):
        """load_dispatch_state() should add scout state if missing."""
        from dispatch_utils import load_dispatch_state

        mock_load_yaml.return_value = None  # Force JSON fallback

        with tempfile.TemporaryDirectory() as tmpdir:
            mock_state_dir.return_value = Path(tmpdir)
            mock_scout.return_value = {"findings": []}

            state_file = Path(tmpdir) / "dispatch_state.json"
            state_file.write_text('{"enabled": true}')

            result = load_dispatch_state()

            self.assertIn("scout", result)


class TestSaveDispatchState(unittest.TestCase):
    """Tests for save_dispatch_state() function."""

    @patch('dispatch_utils.load_yaml_state')
    @patch('dispatch_utils.get_state_dir')
    def test_saves_state_to_file(self, mock_state_dir, mock_load_yaml):
        """save_dispatch_state() should write state to file (JSON fallback)."""
        from dispatch_utils import save_dispatch_state

        mock_load_yaml.return_value = None  # Force JSON fallback

        with tempfile.TemporaryDirectory() as tmpdir:
            mock_state_dir.return_value = Path(tmpdir)

            save_dispatch_state({"enabled": True, "iteration": 10})

            state_file = Path(tmpdir) / "dispatch_state.json"
            self.assertTrue(state_file.exists())

            content = json.loads(state_file.read_text())
            self.assertTrue(content["enabled"])
            self.assertEqual(content["iteration"], 10)

    @patch('dispatch_utils.load_yaml_state')
    @patch('dispatch_utils.get_state_dir')
    def test_creates_directory_if_missing(self, mock_state_dir, mock_load_yaml):
        """save_dispatch_state() should create directory if needed."""
        from dispatch_utils import save_dispatch_state

        mock_load_yaml.return_value = None  # Force JSON fallback

        with tempfile.TemporaryDirectory() as tmpdir:
            state_dir = Path(tmpdir) / "subdir"
            mock_state_dir.return_value = state_dir

            save_dispatch_state({"enabled": True})

            self.assertTrue(state_dir.exists())


class TestUpdateDispatchStats(unittest.TestCase):
    """Tests for update_dispatch_stats() function."""

    def test_increments_stat(self):
        """update_dispatch_stats() should increment counter."""
        from dispatch_utils import update_dispatch_stats

        state = {"stats": {"auto_executed": 5}}
        update_dispatch_stats(state, "auto_executed")

        self.assertEqual(state["stats"]["auto_executed"], 6)

    def test_creates_stats_if_missing(self):
        """update_dispatch_stats() should create stats if missing."""
        from dispatch_utils import update_dispatch_stats

        state = {}
        update_dispatch_stats(state, "junctions_hit")

        self.assertIn("stats", state)
        self.assertEqual(state["stats"]["junctions_hit"], 1)


class TestDetermineNextAction(unittest.TestCase):
    """Tests for determine_next_action() function."""

    def test_no_objective_needs_plan(self):
        """determine_next_action() should suggest plan if no objective."""
        from dispatch_utils import determine_next_action

        yaml_state = {"objective": None, "plan": []}
        cmd, reason, junction = determine_next_action(yaml_state)

        self.assertEqual(cmd, "edge-plan")
        self.assertEqual(junction, JunctionType.AMBIGUOUS)

    def test_no_plan_needs_plan(self):
        """determine_next_action() should suggest plan if no steps."""
        from dispatch_utils import determine_next_action

        yaml_state = {"objective": "Test", "plan": []}
        cmd, reason, junction = determine_next_action(yaml_state)

        self.assertEqual(cmd, "edge-plan")

    def test_all_completed_returns_complete(self):
        """determine_next_action() should return complete if all done."""
        from dispatch_utils import determine_next_action

        yaml_state = {
            "objective": "Test",
            "plan": [
                {"status": "completed"},
                {"status": "completed"}
            ]
        }
        cmd, reason, junction = determine_next_action(yaml_state)

        self.assertEqual(cmd, "complete")
        self.assertEqual(junction, JunctionType.NONE)

    def test_blocked_needs_adaptation(self):
        """determine_next_action() should suggest adapt if blocked."""
        from dispatch_utils import determine_next_action

        yaml_state = {
            "objective": "Test",
            "plan": [
                {"status": "blocked", "description": "Blocked step"}
            ]
        }
        cmd, reason, junction = determine_next_action(yaml_state)

        self.assertEqual(cmd, "edge-adapt")
        self.assertEqual(junction, JunctionType.AMBIGUOUS)

    def test_in_progress_continues_step(self):
        """determine_next_action() should continue in_progress step."""
        from dispatch_utils import determine_next_action

        yaml_state = {
            "objective": "Test",
            "plan": [
                {"status": "in_progress", "description": "Current step"}
            ]
        }
        cmd, reason, junction = determine_next_action(yaml_state)

        self.assertEqual(cmd, "edge-step")
        self.assertEqual(junction, JunctionType.NONE)

    def test_pending_starts_next_step(self):
        """determine_next_action() should start pending step."""
        from dispatch_utils import determine_next_action

        yaml_state = {
            "objective": "Test",
            "plan": [
                {"status": "completed"},
                {"status": "pending", "description": "Next step"}
            ]
        }
        cmd, reason, junction = determine_next_action(yaml_state)

        self.assertEqual(cmd, "edge-step")


class TestCheckStuck(unittest.TestCase):
    """Tests for check_stuck() function."""

    def test_not_stuck_when_below_threshold(self):
        """check_stuck() should return False when below threshold."""
        from dispatch_utils import check_stuck

        state = {"stuck_count": 1}
        is_stuck, reason = check_stuck(state, max_retries=3)

        self.assertFalse(is_stuck)

    def test_stuck_when_at_threshold(self):
        """check_stuck() should return True when at threshold."""
        from dispatch_utils import check_stuck

        state = {"stuck_count": 3}
        is_stuck, reason = check_stuck(state, max_retries=3)

        self.assertTrue(is_stuck)
        self.assertIn("3 times", reason)


class TestCheckIterationLimit(unittest.TestCase):
    """Tests for check_iteration_limit() function."""

    def test_not_limited_when_below(self):
        """check_iteration_limit() should return False when below limit."""
        from dispatch_utils import check_iteration_limit

        state = {"iteration": 5}
        limited, reason = check_iteration_limit(state, max_iterations=10)

        self.assertFalse(limited)

    def test_limited_when_at_max(self):
        """check_iteration_limit() should return True at limit."""
        from dispatch_utils import check_iteration_limit

        state = {"iteration": 10}
        limited, reason = check_iteration_limit(state, max_iterations=10)

        self.assertTrue(limited)


class TestRecordAction(unittest.TestCase):
    """Tests for record_action() function."""

    def test_appends_action(self):
        """record_action() should append to history."""
        from dispatch_utils import record_action

        state = {"history": []}
        record_action(state, "test", "result")

        self.assertEqual(len(state["history"]), 1)
        self.assertEqual(state["history"][0]["action"], "test")

    def test_creates_history_if_missing(self):
        """record_action() should create history if missing."""
        from dispatch_utils import record_action

        state = {}
        record_action(state, "test", "result")

        self.assertIn("history", state)

    def test_limits_history_size(self):
        """record_action() should keep only last 10 actions."""
        from dispatch_utils import record_action

        state = {"history": [{"action": f"old{i}"} for i in range(12)]}
        record_action(state, "new", "result")

        self.assertEqual(len(state["history"]), 10)
        self.assertEqual(state["history"][-1]["action"], "new")


class TestIncrementIteration(unittest.TestCase):
    """Tests for increment_iteration() function."""

    def test_increments_counter(self):
        """increment_iteration() should increment and return value."""
        from dispatch_utils import increment_iteration

        state = {"iteration": 5, "stats": {}}
        result = increment_iteration(state)

        self.assertEqual(result, 6)
        self.assertEqual(state["iteration"], 6)


class TestStuckCounterFunctions(unittest.TestCase):
    """Tests for stuck counter functions."""

    def test_reset_stuck_counter(self):
        """reset_stuck_counter() should set count to 0."""
        from dispatch_utils import reset_stuck_counter

        state = {"stuck_count": 5}
        reset_stuck_counter(state)

        self.assertEqual(state["stuck_count"], 0)

    def test_increment_stuck_counter(self):
        """increment_stuck_counter() should increment and return."""
        from dispatch_utils import increment_stuck_counter

        state = {"stuck_count": 2}
        result = increment_stuck_counter(state)

        self.assertEqual(result, 3)
        self.assertEqual(state["stuck_count"], 3)


class TestDispatchFlowFunctions(unittest.TestCase):
    """Tests for dispatch flow control functions."""

    @patch('dispatch_utils.save_dispatch_state')
    @patch('dispatch_utils.load_dispatch_state')
    def test_start_dispatch(self, mock_load, mock_save):
        """start_dispatch() should enable and reset state."""
        from dispatch_utils import start_dispatch

        mock_load.return_value = {"enabled": False}

        result = start_dispatch()

        self.assertTrue(result["enabled"])
        self.assertEqual(result["state"], DispatchState.RUNNING.value)
        self.assertEqual(result["iteration"], 0)
        mock_save.assert_called()

    @patch('dispatch_utils.save_dispatch_state')
    @patch('dispatch_utils.load_dispatch_state')
    def test_stop_dispatch(self, mock_load, mock_save):
        """stop_dispatch() should disable dispatch."""
        from dispatch_utils import stop_dispatch

        mock_load.return_value = {"enabled": True, "history": []}

        result = stop_dispatch("Test stop")

        self.assertFalse(result["enabled"])
        self.assertEqual(result["state"], DispatchState.IDLE.value)
        mock_save.assert_called()

    @patch('dispatch_utils.set_pending_junction')
    @patch('dispatch_utils.save_dispatch_state')
    def test_pause_at_junction(self, mock_save, mock_set_pending):
        """pause_at_junction() should set junction state."""
        from dispatch_utils import pause_at_junction

        state = {"stats": {}}
        # Return tuple (pending, warning) - new signature
        mock_set_pending.return_value = ({"id": "test-junction"}, None)
        pause_at_junction(state, JunctionType.IRREVERSIBLE, "Push detected")

        self.assertEqual(state["state"], DispatchState.JUNCTION.value)
        self.assertIsNotNone(state["junction"])
        self.assertEqual(state["junction"]["type"], JunctionType.IRREVERSIBLE.value)

    @patch('dispatch_utils.clear_pending_junction')
    @patch('dispatch_utils.save_dispatch_state')
    def test_resume_from_junction(self, mock_save, mock_clear):
        """resume_from_junction() should clear junction."""
        from dispatch_utils import resume_from_junction

        state = {"junction": {"type": "test"}}
        # Return tuple (cleared, warning) - new signature
        mock_clear.return_value = ({"type": "test"}, None)
        resume_from_junction(state)

        self.assertEqual(state["state"], DispatchState.RUNNING.value)
        self.assertIsNone(state["junction"])

    @patch('dispatch_utils.save_dispatch_state')
    def test_mark_complete(self, mock_save):
        """mark_complete() should set complete state."""
        from dispatch_utils import mark_complete

        state = {"history": []}
        mark_complete(state)

        self.assertFalse(state["enabled"])
        self.assertEqual(state["state"], DispatchState.COMPLETE.value)

    @patch('dispatch_utils.save_dispatch_state')
    def test_mark_stuck(self, mock_save):
        """mark_stuck() should set stuck state."""
        from dispatch_utils import mark_stuck

        state = {"history": []}
        mark_stuck(state, "Test stuck")

        self.assertEqual(state["state"], DispatchState.STUCK.value)


class TestGetDispatchStatus(unittest.TestCase):
    """Tests for get_dispatch_status() function."""

    @patch('dispatch_utils.load_yaml_state')
    @patch('dispatch_utils.load_dispatch_state')
    @patch('dispatch_utils.get_pending_junction')
    def test_returns_status_dict(self, mock_pending, mock_dispatch, mock_yaml):
        """get_dispatch_status() should return complete status."""
        from dispatch_utils import get_dispatch_status

        mock_pending.return_value = None
        mock_dispatch.return_value = {
            "enabled": True,
            "state": "running",
            "iteration": 5,
            "stuck_count": 0,
            "junction": None,
            "stats": {"auto_executed": 10},
            "scout": {}
        }
        mock_yaml.return_value = {
            "objective": "Test",
            "plan": [
                {"status": "completed"},
                {"status": "pending"}
            ]
        }

        status = get_dispatch_status()

        self.assertTrue(status["enabled"])
        self.assertEqual(status["iteration"], 5)
        self.assertEqual(status["objective"], "Test")
        self.assertEqual(status["plan_steps"], 2)
        self.assertEqual(status["completed_steps"], 1)


class TestScoutFindingsManagement(unittest.TestCase):
    """Tests for scout findings management functions."""

    @patch('dispatch_utils.save_dispatch_state')
    @patch('dispatch_utils.load_dispatch_state')
    def test_save_scout_findings(self, mock_load, mock_save):
        """save_scout_findings() should store findings."""
        from dispatch_utils import save_scout_findings

        mock_load.return_value = {"scout": {}}

        findings = [{"type": "todo", "title": "Test"}]
        metadata = {"last_scan": "2025-01-01", "files_scanned": 10}

        save_scout_findings(findings, metadata)

        call_args = mock_save.call_args[0][0]
        self.assertEqual(len(call_args["scout"]["findings"]), 1)
        self.assertEqual(call_args["scout"]["files_scanned"], 10)

    @patch('dispatch_utils.load_dispatch_state')
    def test_get_scout_findings(self, mock_load):
        """get_scout_findings() should return findings list."""
        from dispatch_utils import get_scout_findings

        mock_load.return_value = {
            "scout": {
                "findings": [
                    {"type": "todo", "priority": "medium", "title": "Test",
                     "description": "Desc", "location": "/path"}
                ]
            }
        }

        findings = get_scout_findings()

        self.assertEqual(len(findings), 1)

    @patch('dispatch_utils.save_dispatch_state')
    @patch('dispatch_utils.load_dispatch_state')
    def test_dismiss_finding(self, mock_load, mock_save):
        """dismiss_finding() should add to dismissed list."""
        from dispatch_utils import dismiss_finding

        mock_load.return_value = {
            "scout": {
                "findings": [{"title": "Test TODO"}],
                "dismissed": []
            }
        }

        dismiss_finding("Test TODO")

        call_args = mock_save.call_args[0][0]
        self.assertIn("Test TODO", call_args["scout"]["dismissed"])
        self.assertEqual(len(call_args["scout"]["findings"]), 0)

    @patch('dispatch_utils.save_dispatch_state')
    @patch('dispatch_utils.load_dispatch_state')
    def test_clear_scout_findings(self, mock_load, mock_save):
        """clear_scout_findings() should empty findings list."""
        from dispatch_utils import clear_scout_findings

        mock_load.return_value = {
            "scout": {"findings": [{"title": "Test"}]}
        }

        clear_scout_findings()

        call_args = mock_save.call_args[0][0]
        self.assertEqual(len(call_args["scout"]["findings"]), 0)

    @patch('dispatch_utils.get_top_findings')
    def test_has_scout_findings(self, mock_top):
        """has_scout_findings() should check if findings exist."""
        from dispatch_utils import has_scout_findings

        mock_top.return_value = [{"title": "Test"}]
        self.assertTrue(has_scout_findings())

        mock_top.return_value = []
        self.assertFalse(has_scout_findings())

    def test_needs_scout_scan_no_objective(self):
        """needs_scout_scan() should return True if no objective."""
        from dispatch_utils import needs_scout_scan

        self.assertTrue(needs_scout_scan({"objective": None}))
        self.assertTrue(needs_scout_scan({"objective": "null"}))
        self.assertFalse(needs_scout_scan({"objective": "Real objective"}))


if __name__ == '__main__':
    unittest.main()
