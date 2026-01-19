#!/usr/bin/env python3
"""
Tests for scorecard_utils.py - outcome scorecard and autonomy governor.

Tests the core functions for:
- Scorecard computation
- Governor recommendation
- Autonomy level determination
- Formatting
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


class TestComputeObjectiveScorecard(unittest.TestCase):
    """Tests for compute_objective_scorecard() function."""

    def test_computes_success_when_all_complete(self):
        """compute_objective_scorecard() should mark success when all steps complete."""
        from scorecard_utils import compute_objective_scorecard

        dispatch_state = {
            "iteration": 10,
            "stuck_count": 0,
            "stats": {"junctions_hit": 2}
        }
        yaml_state = {
            "plan": [
                {"status": "completed"},
                {"status": "completed"},
                {"status": "completed"}
            ],
            "memory": []
        }

        scorecard = compute_objective_scorecard(
            objective="Test objective",
            dispatch_state=dispatch_state,
            yaml_state=yaml_state
        )

        self.assertTrue(scorecard["success"])
        self.assertEqual(scorecard["metrics"]["steps_completed"], 3)
        self.assertEqual(scorecard["metrics"]["steps_total"], 3)

    def test_computes_failure_when_incomplete(self):
        """compute_objective_scorecard() should mark failure when steps pending."""
        from scorecard_utils import compute_objective_scorecard

        dispatch_state = {
            "iteration": 5,
            "stuck_count": 1,
            "stats": {"junctions_hit": 1}
        }
        yaml_state = {
            "plan": [
                {"status": "completed"},
                {"status": "pending"}
            ],
            "memory": []
        }

        scorecard = compute_objective_scorecard(
            objective="Test objective",
            dispatch_state=dispatch_state,
            yaml_state=yaml_state
        )

        self.assertFalse(scorecard["success"])
        self.assertEqual(scorecard["metrics"]["steps_completed"], 1)

    def test_computes_efficiency(self):
        """compute_objective_scorecard() should compute efficiency correctly."""
        from scorecard_utils import compute_objective_scorecard

        dispatch_state = {
            "iteration": 20,  # 20 iterations
            "stuck_count": 0,
            "stats": {"junctions_hit": 0}
        }
        yaml_state = {
            "plan": [
                {"status": "completed"},
                {"status": "completed"},
                {"status": "completed"},
                {"status": "completed"}
            ],  # 4 steps
            "memory": []
        }

        scorecard = compute_objective_scorecard(
            objective="Test",
            dispatch_state=dispatch_state,
            yaml_state=yaml_state
        )

        # 20 iterations / 4 steps = 5.0 efficiency
        self.assertEqual(scorecard["metrics"]["efficiency"], 5.0)

    def test_computes_junction_rate(self):
        """compute_objective_scorecard() should compute junction rate correctly."""
        from scorecard_utils import compute_objective_scorecard

        dispatch_state = {
            "iteration": 10,
            "stuck_count": 0,
            "stats": {"junctions_hit": 2}  # 2 junctions in 10 iterations
        }
        yaml_state = {
            "plan": [{"status": "completed"}],
            "memory": []
        }

        scorecard = compute_objective_scorecard(
            objective="Test",
            dispatch_state=dispatch_state,
            yaml_state=yaml_state
        )

        # 2/10 = 0.2
        self.assertEqual(scorecard["metrics"]["junction_rate"], 0.2)

    def test_includes_quality_gate(self):
        """compute_objective_scorecard() should include quality gate result."""
        from scorecard_utils import compute_objective_scorecard

        dispatch_state = {"iteration": 5, "stats": {}}
        yaml_state = {"plan": [{"status": "completed"}], "memory": []}

        scorecard = compute_objective_scorecard(
            objective="Test",
            dispatch_state=dispatch_state,
            yaml_state=yaml_state,
            quality_gate_passed=False,
            quality_gate_reason="Tests failed"
        )

        self.assertFalse(scorecard["quality"]["passed"])
        self.assertEqual(scorecard["quality"]["reason"], "Tests failed")


class TestGovernorRecommendation(unittest.TestCase):
    """Tests for compute_governor_recommendation() function."""

    def test_maintains_with_insufficient_data(self):
        """compute_governor_recommendation() should maintain with < 2 scorecards."""
        from scorecard_utils import compute_governor_recommendation

        result = compute_governor_recommendation([])
        self.assertEqual(result["direction"], "maintain")

        result = compute_governor_recommendation([{"success": True}])
        self.assertEqual(result["direction"], "maintain")

    def test_decreases_when_quality_low(self):
        """compute_governor_recommendation() should decrease when quality fails."""
        from scorecard_utils import compute_governor_recommendation

        scorecards = [
            {"success": True, "quality": {"passed": False}, "metrics": {"efficiency": 5, "junction_rate": 0.2, "stuck_count": 0}},
            {"success": True, "quality": {"passed": False}, "metrics": {"efficiency": 5, "junction_rate": 0.2, "stuck_count": 0}},
            {"success": True, "quality": {"passed": False}, "metrics": {"efficiency": 5, "junction_rate": 0.2, "stuck_count": 0}},
        ]

        result = compute_governor_recommendation(scorecards)

        self.assertEqual(result["direction"], "decrease")
        self.assertIn("Quality pass rate", result["reason"])

    def test_decreases_when_stuck_rising(self):
        """compute_governor_recommendation() should decrease when stuck events rise."""
        from scorecard_utils import compute_governor_recommendation

        scorecards = [
            {"success": True, "quality": {"passed": True}, "metrics": {"efficiency": 5, "junction_rate": 0.2, "stuck_count": 0}},
            {"success": True, "quality": {"passed": True}, "metrics": {"efficiency": 5, "junction_rate": 0.2, "stuck_count": 0}},
            {"success": True, "quality": {"passed": True}, "metrics": {"efficiency": 5, "junction_rate": 0.2, "stuck_count": 3}},
            {"success": True, "quality": {"passed": True}, "metrics": {"efficiency": 5, "junction_rate": 0.2, "stuck_count": 4}},
        ]

        result = compute_governor_recommendation(scorecards)

        self.assertEqual(result["direction"], "decrease")
        self.assertIn("rising", result["reason"])

    def test_increases_when_successful_and_efficient(self):
        """compute_governor_recommendation() should increase when doing well."""
        from scorecard_utils import compute_governor_recommendation

        scorecards = [
            {"success": True, "quality": {"passed": True}, "metrics": {"efficiency": 10, "junction_rate": 0.2, "stuck_count": 0}},
            {"success": True, "quality": {"passed": True}, "metrics": {"efficiency": 9, "junction_rate": 0.1, "stuck_count": 0}},
            {"success": True, "quality": {"passed": True}, "metrics": {"efficiency": 7, "junction_rate": 0.1, "stuck_count": 0}},
            {"success": True, "quality": {"passed": True}, "metrics": {"efficiency": 5, "junction_rate": 0.1, "stuck_count": 0}},
        ]

        result = compute_governor_recommendation(scorecards)

        self.assertEqual(result["direction"], "increase")


class TestAutonomyLevel(unittest.TestCase):
    """Tests for get_autonomy_level() function."""

    def test_returns_medium_with_no_data(self):
        """get_autonomy_level() should return medium with no scorecards."""
        from scorecard_utils import get_autonomy_level

        result = get_autonomy_level([])

        self.assertEqual(result["level"], "medium")
        self.assertIn("irreversible", result["junction_types"])
        self.assertEqual(result["stuck_threshold"], 3)

    def test_returns_high_when_increasing(self):
        """get_autonomy_level() should return high when governor recommends increase."""
        from scorecard_utils import get_autonomy_level

        scorecards = [
            {"success": True, "quality": {"passed": True}, "metrics": {"efficiency": 10, "junction_rate": 0.2, "stuck_count": 0}},
            {"success": True, "quality": {"passed": True}, "metrics": {"efficiency": 8, "junction_rate": 0.1, "stuck_count": 0}},
            {"success": True, "quality": {"passed": True}, "metrics": {"efficiency": 6, "junction_rate": 0.1, "stuck_count": 0}},
            {"success": True, "quality": {"passed": True}, "metrics": {"efficiency": 4, "junction_rate": 0.1, "stuck_count": 0}},
        ]

        result = get_autonomy_level(scorecards)

        self.assertEqual(result["level"], "high")
        self.assertEqual(result["stuck_threshold"], 5)
        self.assertIn("ambiguous", result["auto_approve_types"])

    def test_returns_low_when_decreasing(self):
        """get_autonomy_level() should return low when governor recommends decrease."""
        from scorecard_utils import get_autonomy_level

        scorecards = [
            {"success": True, "quality": {"passed": False}, "metrics": {"efficiency": 5, "junction_rate": 0.2, "stuck_count": 0}},
            {"success": True, "quality": {"passed": False}, "metrics": {"efficiency": 5, "junction_rate": 0.2, "stuck_count": 0}},
            {"success": True, "quality": {"passed": False}, "metrics": {"efficiency": 5, "junction_rate": 0.2, "stuck_count": 0}},
        ]

        result = get_autonomy_level(scorecards)

        self.assertEqual(result["level"], "low")
        self.assertEqual(result["stuck_threshold"], 2)
        self.assertIn("step_failure", result["junction_types"])


class TestFormatScorecard(unittest.TestCase):
    """Tests for format_scorecard() function."""

    def test_formats_success(self):
        """format_scorecard() should show success correctly."""
        from scorecard_utils import format_scorecard

        scorecard = {
            "objective": "Test objective",
            "success": True,
            "metrics": {
                "steps_completed": 5,
                "steps_total": 5,
                "iterations": 15,
                "efficiency": 3.0,
                "junctions_hit": 2,
                "junction_rate": 0.133,
                "stuck_count": 0
            },
            "quality": {"passed": True},
            "learning": {"lessons_used_today": 3, "total_reinforcements": 10}
        }

        result = format_scorecard(scorecard)

        self.assertIn("SUCCESS", result)
        self.assertIn("Steps: 5/5", result)
        self.assertIn("Efficiency: 3.00", result)

    def test_formats_failure(self):
        """format_scorecard() should show failure correctly."""
        from scorecard_utils import format_scorecard

        scorecard = {
            "objective": "Test objective",
            "success": False,
            "metrics": {
                "steps_completed": 2,
                "steps_total": 5,
                "iterations": 10,
                "efficiency": 5.0,
                "junctions_hit": 3,
                "junction_rate": 0.3,
                "stuck_count": 2
            },
            "quality": {"passed": False, "reason": "Tests failed"},
            "learning": {"lessons_used_today": 1, "total_reinforcements": 5}
        }

        result = format_scorecard(scorecard)

        self.assertIn("INCOMPLETE", result)
        self.assertIn("Steps: 2/5", result)
        self.assertIn("Tests failed", result)


class TestOnObjectiveComplete(unittest.TestCase):
    """Tests for on_objective_complete() function."""

    @patch('scorecard_utils.load_yaml_state')
    @patch('scorecard_utils.persist_scorecard')
    def test_computes_and_persists(self, mock_persist, mock_yaml):
        """on_objective_complete() should compute and persist scorecard."""
        from scorecard_utils import on_objective_complete

        mock_yaml.return_value = {
            "objective": "Test objective",
            "plan": [{"status": "completed"}, {"status": "completed"}],
            "memory": []
        }
        mock_persist.return_value = True

        dispatch_state = {
            "iteration": 5,
            "stuck_count": 0,
            "stats": {"junctions_hit": 1, "objectives_completed": 0}
        }

        scorecard = on_objective_complete(dispatch_state)

        self.assertTrue(scorecard["success"])
        mock_persist.assert_called_once()
        self.assertEqual(dispatch_state["stats"]["objectives_completed"], 1)


if __name__ == '__main__':
    unittest.main()
