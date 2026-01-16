#!/usr/bin/env python3
"""
Tests for intent_engine.py - the brain of unified /edge command.
"""

import unittest
from unittest.mock import patch

from intent_engine import (
    Intent, IntentAction, Gear,
    parse_edge_args, detect_intent,
    _detect_active_intent, _should_junction_for_step,
    format_intent_status,
)


class TestParseEdgeArgs(unittest.TestCase):
    """Test argument parsing for /edge command."""

    def test_no_args(self):
        result = parse_edge_args("")
        self.assertIsNone(result["command"])
        self.assertIsNone(result["override"])
        self.assertIsNone(result["objective"])

    def test_status_command(self):
        result = parse_edge_args("status")
        self.assertEqual(result["command"], "status")

        result = parse_edge_args("state")
        self.assertEqual(result["command"], "status")

    def test_stop_command(self):
        result = parse_edge_args("stop")
        self.assertEqual(result["command"], "stop")

        result = parse_edge_args("off")
        self.assertEqual(result["command"], "stop")

    def test_approve_command(self):
        result = parse_edge_args("approve")
        self.assertEqual(result["command"], "approve")
        self.assertIsNone(result["check_ids"])

    def test_approve_with_check_ids(self):
        result = parse_edge_args("approve 1,2,3")
        self.assertEqual(result["command"], "approve")
        self.assertEqual(result["check_ids"], [1, 2, 3])

    def test_skip_command(self):
        result = parse_edge_args("skip")
        self.assertEqual(result["command"], "skip")

    def test_dismiss_command(self):
        result = parse_edge_args("dismiss")
        self.assertEqual(result["command"], "dismiss")

    def test_plan_override(self):
        result = parse_edge_args("--plan")
        self.assertEqual(result["override"], "--plan")
        self.assertIsNone(result["command"])

    def test_verify_override(self):
        result = parse_edge_args("--verify")
        self.assertEqual(result["override"], "--verify")

    def test_auto_override(self):
        result = parse_edge_args("--auto")
        self.assertEqual(result["override"], "--auto")

    def test_quoted_objective(self):
        result = parse_edge_args('"Add dark mode toggle"')
        self.assertEqual(result["objective"], "Add dark mode toggle")
        self.assertIsNone(result["command"])

    def test_single_quoted_objective(self):
        result = parse_edge_args("'Fix the login bug'")
        self.assertEqual(result["objective"], "Fix the login bug")

    def test_unquoted_objective(self):
        result = parse_edge_args("Add new feature")
        self.assertEqual(result["objective"], "Add new feature")

    def test_case_insensitive_commands(self):
        result = parse_edge_args("STATUS")
        self.assertEqual(result["command"], "status")

        result = parse_edge_args("APPROVE")
        self.assertEqual(result["command"], "approve")


class TestDetectActiveIntent(unittest.TestCase):
    """Test intent detection in ACTIVE gear."""

    def test_needs_objective(self):
        state = {"objective": "", "plan": []}
        intent = _detect_active_intent(state)
        self.assertEqual(intent.action, IntentAction.NEEDS_OBJECTIVE)
        self.assertEqual(intent.gear, Gear.ACTIVE)

    def test_needs_objective_whitespace(self):
        state = {"objective": "   ", "plan": []}
        intent = _detect_active_intent(state)
        self.assertEqual(intent.action, IntentAction.NEEDS_OBJECTIVE)

    def test_needs_plan(self):
        state = {"objective": "Add feature", "plan": []}
        intent = _detect_active_intent(state)
        self.assertEqual(intent.action, IntentAction.NEEDS_PLAN)
        self.assertEqual(intent.context["objective"], "Add feature")

    def test_needs_risks(self):
        state = {
            "objective": "Add feature",
            "plan": [{"description": "Step 1", "status": "pending"}],
            "risks": []
        }
        intent = _detect_active_intent(state)
        self.assertEqual(intent.action, IntentAction.NEEDS_RISKS)

    def test_ready_to_execute(self):
        state = {
            "objective": "Add feature",
            "plan": [{"description": "Step 1", "status": "pending"}],
            "risks": [{"risk": "Could fail", "mitigation": "Test it"}]
        }
        intent = _detect_active_intent(state)
        self.assertEqual(intent.action, IntentAction.READY_TO_EXECUTE)
        self.assertEqual(intent.context["step_index"], 0)
        self.assertEqual(intent.context["step_description"], "Step 1")

    def test_ready_to_execute_in_progress(self):
        state = {
            "objective": "Add feature",
            "plan": [
                {"description": "Step 1", "status": "completed"},
                {"description": "Step 2", "status": "in_progress"},
            ],
            "risks": [{"risk": "X", "mitigation": "Y"}]
        }
        intent = _detect_active_intent(state)
        self.assertEqual(intent.action, IntentAction.READY_TO_EXECUTE)
        self.assertEqual(intent.context["step_index"], 1)

    def test_blocked_step(self):
        state = {
            "objective": "Add feature",
            "plan": [
                {"description": "Step 1", "status": "completed"},
                {"description": "Step 2", "status": "blocked"},
            ],
            "risks": [{"risk": "X", "mitigation": "Y"}]
        }
        intent = _detect_active_intent(state)
        self.assertEqual(intent.action, IntentAction.BLOCKED_STEP)
        self.assertEqual(intent.context["blocked_index"], 1)

    def test_ready_to_complete(self):
        state = {
            "objective": "Add feature",
            "plan": [
                {"description": "Step 1", "status": "completed"},
                {"description": "Step 2", "status": "completed"},
            ],
            "risks": [{"risk": "X", "mitigation": "Y"}]
        }
        intent = _detect_active_intent(state)
        self.assertEqual(intent.action, IntentAction.READY_TO_COMPLETE)
        self.assertEqual(intent.context["steps_completed"], 2)


class TestJunctionDetection(unittest.TestCase):
    """Test junction detection for steps."""

    def test_dangerous_delete(self):
        step = {"description": "Delete old files"}
        result = _should_junction_for_step(step)
        self.assertIsNotNone(result)
        self.assertEqual(result[0], "dangerous")

    def test_dangerous_deploy(self):
        step = {"description": "Deploy to production"}
        result = _should_junction_for_step(step)
        self.assertIsNotNone(result)
        self.assertEqual(result[0], "dangerous")

    def test_complex_refactor(self):
        step = {"description": "Refactor the auth module"}
        result = _should_junction_for_step(step)
        self.assertIsNotNone(result)
        self.assertEqual(result[0], "complexity")

    def test_safe_step(self):
        step = {"description": "Add unit tests"}
        result = _should_junction_for_step(step)
        self.assertIsNone(result)

    def test_safe_step_add(self):
        step = {"description": "Add validation logic"}
        result = _should_junction_for_step(step)
        self.assertIsNone(result)


class TestDetectIntent(unittest.TestCase):
    """Test main intent detection function."""

    def test_status_command(self):
        state = {"objective": "Test", "plan": [], "runtime": {}}
        intent = detect_intent(state, "status")
        self.assertEqual(intent.action, IntentAction.SHOW_STATUS)

    def test_stop_command(self):
        state = {"objective": "Test", "plan": [], "runtime": {}}
        intent = detect_intent(state, "stop")
        self.assertEqual(intent.action, IntentAction.STOP)

    def test_approve_command(self):
        state = {"objective": "Test", "plan": [], "runtime": {}}
        intent = detect_intent(state, "approve")
        self.assertEqual(intent.action, IntentAction.JUNCTION_APPROVE)

    def test_approve_with_ids(self):
        state = {"objective": "Test", "plan": [], "runtime": {}}
        intent = detect_intent(state, "approve 1,2")
        self.assertEqual(intent.action, IntentAction.JUNCTION_APPROVE)
        self.assertEqual(intent.context["check_ids"], [1, 2])

    def test_plan_override(self):
        state = {"objective": "Test", "plan": [], "runtime": {}}
        intent = detect_intent(state, "--plan")
        self.assertEqual(intent.action, IntentAction.FORCE_PLAN)
        self.assertEqual(intent.override, "--plan")

    def test_verify_override(self):
        state = {"objective": "Test", "plan": [], "runtime": {}}
        intent = detect_intent(state, "--verify")
        self.assertEqual(intent.action, IntentAction.FORCE_VERIFY)
        self.assertEqual(intent.override, "--verify")

    def test_new_objective(self):
        state = {"objective": "", "plan": [], "runtime": {}}
        intent = detect_intent(state, '"Add dark mode"')
        self.assertEqual(intent.action, IntentAction.NEW_OBJECTIVE)
        self.assertEqual(intent.context["new_objective"], "Add dark mode")

    def test_pending_junction(self):
        state = {
            "objective": "Test",
            "plan": [{"description": "Step", "status": "pending"}],
            "risks": [{"risk": "X", "mitigation": "Y"}],
            "runtime": {
                "junction": {
                    "pending": {
                        "type": "dangerous",
                        "payload": {"reason": "git push detected"}
                    }
                }
            }
        }
        intent = detect_intent(state, "")
        self.assertEqual(intent.action, IntentAction.AT_JUNCTION)
        self.assertEqual(intent.context["junction_type"], "dangerous")

    def test_no_args_active_gear(self):
        state = {
            "objective": "Add feature",
            "plan": [{"description": "Step 1", "status": "pending"}],
            "risks": [{"risk": "X", "mitigation": "Y"}],
            "runtime": {}
        }
        intent = detect_intent(state, "")
        self.assertEqual(intent.action, IntentAction.READY_TO_EXECUTE)
        self.assertEqual(intent.gear, Gear.ACTIVE)


class TestIntentProperties(unittest.TestCase):
    """Test Intent dataclass properties."""

    def test_is_override_true(self):
        intent = Intent(
            action=IntentAction.FORCE_PLAN,
            gear=Gear.ACTIVE,
            override="--plan"
        )
        self.assertTrue(intent.is_override)

    def test_is_override_false(self):
        intent = Intent(
            action=IntentAction.READY_TO_EXECUTE,
            gear=Gear.ACTIVE,
        )
        self.assertFalse(intent.is_override)

    def test_requires_user_action_true(self):
        intent = Intent(
            action=IntentAction.AT_JUNCTION,
            gear=Gear.ACTIVE,
        )
        self.assertTrue(intent.requires_user_action)

    def test_requires_user_action_false(self):
        intent = Intent(
            action=IntentAction.READY_TO_EXECUTE,
            gear=Gear.ACTIVE,
        )
        self.assertFalse(intent.requires_user_action)

    def test_to_dict(self):
        intent = Intent(
            action=IntentAction.READY_TO_EXECUTE,
            gear=Gear.ACTIVE,
            context={"step": "Test"},
            reason="Testing"
        )
        d = intent.to_dict()
        self.assertEqual(d["action"], "ready_to_execute")
        self.assertEqual(d["gear"], "active")
        self.assertEqual(d["context"]["step"], "Test")


class TestFormatIntent(unittest.TestCase):
    """Test intent formatting."""

    def test_format_active_intent(self):
        intent = Intent(
            action=IntentAction.READY_TO_EXECUTE,
            gear=Gear.ACTIVE,
            reason="Execute step 1: Add tests"
        )
        output = format_intent_status(intent)
        self.assertIn("⚙️", output)
        self.assertIn("ACTIVE", output)
        self.assertIn("Ready To Execute", output)

    def test_format_patrol_intent(self):
        intent = Intent(
            action=IntentAction.RUN_SCAN,
            gear=Gear.PATROL,
            reason="Scanning codebase"
        )
        output = format_intent_status(intent)
        self.assertIn("🔍", output)
        self.assertIn("PATROL", output)

    def test_format_with_override(self):
        intent = Intent(
            action=IntentAction.FORCE_PLAN,
            gear=Gear.ACTIVE,
            override="--plan",
            reason="Forced planning"
        )
        output = format_intent_status(intent)
        self.assertIn("--plan", output)


if __name__ == "__main__":
    unittest.main()
