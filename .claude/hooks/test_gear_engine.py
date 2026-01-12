#!/usr/bin/env python3
"""
Tests for gear_engine.py - Gear transition management (v3.7)
"""

import unittest
from unittest.mock import patch, MagicMock
from pathlib import Path


class TestGearStatePersistence(unittest.TestCase):
    """Tests for gear state file operations."""

    @patch('gear_engine.GEAR_STATE_FILE')
    def test_load_gear_state_returns_default_when_missing(self, mock_file):
        """Should return default state when file doesn't exist."""
        from gear_engine import load_gear_state
        from gear_config import Gear

        mock_file.exists.return_value = False

        state = load_gear_state()
        self.assertEqual(state.current_gear, Gear.ACTIVE)

    def test_reset_gear_state(self):
        """reset_gear_state should return default state."""
        from gear_engine import reset_gear_state
        from gear_config import Gear

        with patch('gear_engine.save_gear_state'):
            state = reset_gear_state()
            self.assertEqual(state.current_gear, Gear.ACTIVE)
            self.assertEqual(state.iterations, 0)


class TestExecuteTransition(unittest.TestCase):
    """Tests for execute_transition()."""

    def test_active_to_patrol_transition(self):
        """Should transition from ACTIVE to PATROL."""
        from gear_engine import execute_transition
        from gear_config import Gear, GearTransition, get_default_gear_state

        initial = get_default_gear_state()
        initial.current_gear = Gear.ACTIVE

        result = execute_transition(initial, GearTransition.ACTIVE_TO_PATROL)

        self.assertEqual(result.current_gear, Gear.PATROL)
        self.assertEqual(result.iterations, 0)  # Reset on transition

    def test_patrol_to_active_transition(self):
        """Should transition from PATROL to ACTIVE."""
        from gear_engine import execute_transition
        from gear_config import Gear, GearTransition, GearState

        initial = GearState(
            current_gear=Gear.PATROL,
            entered_at="2025-01-01",
            iterations=5,
            last_transition=None,
            patrol_findings_count=3,
            dream_proposals_count=0,
        )

        result = execute_transition(initial, GearTransition.PATROL_TO_ACTIVE)

        self.assertEqual(result.current_gear, Gear.ACTIVE)
        self.assertEqual(result.patrol_findings_count, 3)  # Preserved

    def test_patrol_to_dream_transition(self):
        """Should transition from PATROL to DREAM."""
        from gear_engine import execute_transition
        from gear_config import Gear, GearTransition, GearState

        initial = GearState(
            current_gear=Gear.PATROL,
            entered_at="2025-01-01",
            iterations=1,
            last_transition=None,
            patrol_findings_count=0,
            dream_proposals_count=0,
        )

        result = execute_transition(initial, GearTransition.PATROL_TO_DREAM)

        self.assertEqual(result.current_gear, Gear.DREAM)

    def test_active_to_dream_transition(self):
        """Should transition from ACTIVE to DREAM."""
        from gear_engine import execute_transition
        from gear_config import Gear, GearTransition, GearState

        initial = GearState(
            current_gear=Gear.ACTIVE,
            entered_at="2025-01-01",
            iterations=2,
            last_transition=None,
            patrol_findings_count=0,
            dream_proposals_count=0,
        )

        result = execute_transition(initial, GearTransition.ACTIVE_TO_DREAM)

        self.assertEqual(result.current_gear, Gear.DREAM)

    def test_dream_to_active_transition(self):
        """Should transition from DREAM to ACTIVE."""
        from gear_engine import execute_transition
        from gear_config import Gear, GearTransition, GearState

        initial = GearState(
            current_gear=Gear.DREAM,
            entered_at="2025-01-01",
            iterations=1,
            last_transition=None,
            patrol_findings_count=0,
            dream_proposals_count=1,
        )

        result = execute_transition(initial, GearTransition.DREAM_TO_ACTIVE)

        self.assertEqual(result.current_gear, Gear.ACTIVE)
        self.assertEqual(result.dream_proposals_count, 1)  # Preserved


class TestFindTransition(unittest.TestCase):
    """Tests for _find_transition()."""

    def test_finds_active_to_patrol(self):
        """Should find ACTIVE_TO_PATROL transition."""
        from gear_engine import _find_transition
        from gear_config import Gear, GearTransition

        result = _find_transition(Gear.ACTIVE, Gear.PATROL)
        self.assertEqual(result, GearTransition.ACTIVE_TO_PATROL)

    def test_finds_patrol_to_active(self):
        """Should find PATROL_TO_ACTIVE transition."""
        from gear_engine import _find_transition
        from gear_config import Gear, GearTransition

        result = _find_transition(Gear.PATROL, Gear.ACTIVE)
        self.assertEqual(result, GearTransition.PATROL_TO_ACTIVE)

    def test_returns_none_for_invalid(self):
        """Should return None for invalid transition."""
        from gear_engine import _find_transition
        from gear_config import Gear

        # PATROL to PATROL is not a direct transition
        result = _find_transition(Gear.PATROL, Gear.PATROL)
        self.assertIsNone(result)


class TestRunGearEngine(unittest.TestCase):
    """Tests for run_gear_engine()."""

    @patch('gear_engine.load_gear_state')
    @patch('gear_engine.save_gear_state')
    @patch('gear_engine._run_active')
    def test_runs_active_gear_when_objective_exists(self, mock_run, mock_save, mock_load):
        """Should run Active gear when objective with pending work."""
        from gear_engine import run_gear_engine, GearEngineResult
        from gear_config import Gear, get_default_gear_state

        mock_load.return_value = get_default_gear_state()
        mock_run.return_value = GearEngineResult(
            gear_executed=Gear.ACTIVE,
            transitioned=False,
            new_gear=None,
            transition_type=None,
            gear_result={},
            junction_hit=False,
            junction_type=None,
            junction_reason=None,
            continue_loop=True,
            display_message="Active",
        )

        state = {
            "objective": "Test",
            "plan": [{"description": "Step", "status": "pending"}]
        }

        result = run_gear_engine(state)

        self.assertEqual(result.gear_executed, Gear.ACTIVE)

    @patch('gear_engine.load_gear_state')
    @patch('gear_engine.save_gear_state')
    @patch('gear_engine._run_patrol')
    def test_runs_patrol_when_all_complete(self, mock_run, mock_save, mock_load):
        """Should run Patrol gear after objective completion."""
        from gear_engine import run_gear_engine, GearEngineResult
        from gear_config import Gear, GearState

        mock_load.return_value = GearState(
            current_gear=Gear.PATROL,
            entered_at="2025-01-01",
            iterations=0,
            last_transition=None,
            patrol_findings_count=0,
            dream_proposals_count=0,
        )
        mock_run.return_value = GearEngineResult(
            gear_executed=Gear.PATROL,
            transitioned=False,
            new_gear=None,
            transition_type=None,
            gear_result={},
            junction_hit=False,
            junction_type=None,
            junction_reason=None,
            continue_loop=False,
            display_message="Patrol",
        )

        state = {
            "objective": "Test",
            "plan": [{"description": "Step", "status": "completed"}]
        }

        result = run_gear_engine(state)

        mock_run.assert_called_once()


class TestGearEngineResult(unittest.TestCase):
    """Tests for GearEngineResult dataclass."""

    def test_to_dict(self):
        """Should serialize to dict."""
        from gear_engine import GearEngineResult
        from gear_config import Gear, GearTransition

        result = GearEngineResult(
            gear_executed=Gear.ACTIVE,
            transitioned=True,
            new_gear=Gear.PATROL,
            transition_type=GearTransition.ACTIVE_TO_PATROL,
            gear_result={"test": "data"},
            junction_hit=False,
            junction_type=None,
            junction_reason=None,
            continue_loop=True,
            display_message="Test",
        )

        d = result.to_dict()
        self.assertEqual(d["gear_executed"], "active")
        self.assertEqual(d["new_gear"], "patrol")
        self.assertTrue(d["transitioned"])


class TestDisplayHelpers(unittest.TestCase):
    """Tests for display helper functions."""

    def test_format_engine_status(self):
        """format_engine_status should return string."""
        from gear_engine import format_engine_status
        from gear_config import get_default_gear_state

        state = get_default_gear_state()
        result = format_engine_status(state)

        self.assertIsInstance(result, str)
        self.assertIn("GEAR ENGINE", result)

    def test_format_transition(self):
        """format_transition should return readable string."""
        from gear_engine import format_transition
        from gear_config import Gear

        result = format_transition(Gear.ACTIVE, Gear.PATROL)

        self.assertIn("Active", result)
        self.assertIn("Patrol", result)
        self.assertIn("→", result)


if __name__ == "__main__":
    unittest.main()
