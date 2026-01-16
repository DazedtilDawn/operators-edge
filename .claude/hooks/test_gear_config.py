#!/usr/bin/env python3
"""
Tests for gear_config.py - Gear state and transition definitions (v3.7)
"""

import unittest
from datetime import datetime


class TestGearEnum(unittest.TestCase):
    """Tests for Gear enum."""

    def test_has_active_gear(self):
        """Should have ACTIVE gear."""
        from gear_config import Gear
        self.assertEqual(Gear.ACTIVE.value, "active")

    def test_has_patrol_gear(self):
        """Should have PATROL gear."""
        from gear_config import Gear
        self.assertEqual(Gear.PATROL.value, "patrol")

    def test_has_dream_gear(self):
        """Should have DREAM gear."""
        from gear_config import Gear
        self.assertEqual(Gear.DREAM.value, "dream")

    def test_exactly_three_gears(self):
        """Should have exactly three gears."""
        from gear_config import Gear
        self.assertEqual(len(Gear), 3)


class TestGearTransitionEnum(unittest.TestCase):
    """Tests for GearTransition enum."""

    def test_active_to_patrol(self):
        """Should have ACTIVE_TO_PATROL transition."""
        from gear_config import GearTransition
        self.assertIsNotNone(GearTransition.ACTIVE_TO_PATROL)

    def test_active_to_dream(self):
        """Should have ACTIVE_TO_DREAM transition."""
        from gear_config import GearTransition
        self.assertIsNotNone(GearTransition.ACTIVE_TO_DREAM)

    def test_patrol_to_active(self):
        """Should have PATROL_TO_ACTIVE transition."""
        from gear_config import GearTransition
        self.assertIsNotNone(GearTransition.PATROL_TO_ACTIVE)

    def test_patrol_to_dream(self):
        """Should have PATROL_TO_DREAM transition."""
        from gear_config import GearTransition
        self.assertIsNotNone(GearTransition.PATROL_TO_DREAM)

    def test_dream_to_active(self):
        """Should have DREAM_TO_ACTIVE transition."""
        from gear_config import GearTransition
        self.assertIsNotNone(GearTransition.DREAM_TO_ACTIVE)

    def test_dream_to_patrol(self):
        """Should have DREAM_TO_PATROL transition."""
        from gear_config import GearTransition
        self.assertIsNotNone(GearTransition.DREAM_TO_PATROL)


class TestDetectCurrentGear(unittest.TestCase):
    """Tests for detect_current_gear()."""

    def test_active_when_objective_with_pending_steps(self):
        """Should detect ACTIVE when objective has pending work."""
        from gear_config import detect_current_gear, Gear

        state = {
            "objective": "Test objective",
            "plan": [
                {"description": "Step 1", "status": "completed"},
                {"description": "Step 2", "status": "pending"},
            ]
        }

        result = detect_current_gear(state)
        self.assertEqual(result, Gear.ACTIVE)

    def test_active_when_objective_with_in_progress_steps(self):
        """Should detect ACTIVE when objective has in_progress work."""
        from gear_config import detect_current_gear, Gear

        state = {
            "objective": "Test objective",
            "plan": [
                {"description": "Step 1", "status": "in_progress"},
            ]
        }

        result = detect_current_gear(state)
        self.assertEqual(result, Gear.ACTIVE)

    def test_patrol_when_all_complete(self):
        """Should detect PATROL when all steps completed but objective set."""
        from gear_config import detect_current_gear, Gear

        state = {
            "objective": "Test objective",
            "plan": [
                {"description": "Step 1", "status": "completed"},
                {"description": "Step 2", "status": "completed"},
            ]
        }

        result = detect_current_gear(state)
        self.assertEqual(result, Gear.PATROL)

    def test_dream_when_no_objective(self):
        """Should detect DREAM when no objective."""
        from gear_config import detect_current_gear, Gear

        state = {
            "objective": "",
            "plan": []
        }

        result = detect_current_gear(state)
        self.assertEqual(result, Gear.DREAM)

    def test_dream_when_objective_empty_string(self):
        """Should detect DREAM when objective is empty string."""
        from gear_config import detect_current_gear, Gear

        state = {
            "objective": "   ",
            "plan": []
        }

        result = detect_current_gear(state)
        self.assertEqual(result, Gear.DREAM)


class TestGearBehavior(unittest.TestCase):
    """Tests for GearBehavior and GEAR_BEHAVIORS."""

    def test_active_behavior_exists(self):
        """Should have behavior for ACTIVE gear."""
        from gear_config import GEAR_BEHAVIORS, Gear

        self.assertIn(Gear.ACTIVE, GEAR_BEHAVIORS)

    def test_patrol_behavior_exists(self):
        """Should have behavior for PATROL gear."""
        from gear_config import GEAR_BEHAVIORS, Gear

        self.assertIn(Gear.PATROL, GEAR_BEHAVIORS)

    def test_dream_behavior_exists(self):
        """Should have behavior for DREAM gear."""
        from gear_config import GEAR_BEHAVIORS, Gear

        self.assertIn(Gear.DREAM, GEAR_BEHAVIORS)

    def test_get_gear_behavior(self):
        """get_gear_behavior should return correct behavior."""
        from gear_config import get_gear_behavior, Gear

        behavior = get_gear_behavior(Gear.ACTIVE)
        self.assertEqual(behavior.gear, Gear.ACTIVE)
        self.assertIn("execute_step", behavior.actions)


class TestTransitionRules(unittest.TestCase):
    """Tests for TRANSITION_RULES."""

    def test_transition_rules_exist(self):
        """Should have transition rules defined."""
        from gear_config import TRANSITION_RULES

        self.assertGreater(len(TRANSITION_RULES), 0)

    def test_get_valid_transitions_from_active(self):
        """Should get valid transitions from ACTIVE."""
        from gear_config import get_valid_transitions, Gear

        transitions = get_valid_transitions(Gear.ACTIVE)
        self.assertGreater(len(transitions), 0)

    def test_get_valid_transitions_from_patrol(self):
        """Should get valid transitions from PATROL."""
        from gear_config import get_valid_transitions, Gear

        transitions = get_valid_transitions(Gear.PATROL)
        self.assertGreater(len(transitions), 0)

    def test_get_valid_transitions_from_dream(self):
        """Should get valid transitions from DREAM."""
        from gear_config import get_valid_transitions, Gear

        transitions = get_valid_transitions(Gear.DREAM)
        self.assertGreater(len(transitions), 0)


class TestGearState(unittest.TestCase):
    """Tests for GearState dataclass."""

    def test_to_dict(self):
        """GearState should serialize to dict."""
        from gear_config import GearState, Gear

        state = GearState(
            current_gear=Gear.ACTIVE,
            entered_at="2025-01-01T00:00:00",
            iterations=5,
            last_transition=None,
            patrol_findings_count=3,
            dream_proposals_count=1,
        )

        d = state.to_dict()
        self.assertEqual(d["current_gear"], "active")
        self.assertEqual(d["iterations"], 5)

    def test_from_dict(self):
        """GearState should deserialize from dict."""
        from gear_config import GearState, Gear

        d = {
            "current_gear": "patrol",
            "entered_at": "2025-01-01T00:00:00",
            "iterations": 10,
            "last_transition": "active_to_patrol",
            "patrol_findings_count": 5,
            "dream_proposals_count": 0,
        }

        state = GearState.from_dict(d)
        self.assertEqual(state.current_gear, Gear.PATROL)
        self.assertEqual(state.iterations, 10)


class TestGetDefaultGearState(unittest.TestCase):
    """Tests for get_default_gear_state()."""

    def test_starts_in_active(self):
        """Default gear state should start in ACTIVE."""
        from gear_config import get_default_gear_state, Gear

        state = get_default_gear_state()
        self.assertEqual(state.current_gear, Gear.ACTIVE)

    def test_zero_iterations(self):
        """Default gear state should have zero iterations."""
        from gear_config import get_default_gear_state

        state = get_default_gear_state()
        self.assertEqual(state.iterations, 0)

    def test_zero_findings(self):
        """Default gear state should have zero findings."""
        from gear_config import get_default_gear_state

        state = get_default_gear_state()
        self.assertEqual(state.patrol_findings_count, 0)


class TestDreamLimits(unittest.TestCase):
    """Tests for DREAM_LIMITS."""

    def test_has_max_proposals(self):
        """Should have max_proposals_per_session."""
        from gear_config import DREAM_LIMITS

        self.assertIn("max_proposals_per_session", DREAM_LIMITS)

    def test_has_min_idle_seconds(self):
        """Should have min_idle_seconds."""
        from gear_config import DREAM_LIMITS

        self.assertIn("min_idle_seconds", DREAM_LIMITS)

    def test_should_enter_dream_respects_idle_time(self):
        """should_enter_dream should respect idle time."""
        from gear_config import should_enter_dream, get_default_gear_state, DREAM_LIMITS

        gear_state = get_default_gear_state()

        # Not enough idle time
        result = should_enter_dream(gear_state, idle_seconds=10)
        self.assertFalse(result)

        # Enough idle time
        result = should_enter_dream(gear_state, idle_seconds=120)
        self.assertTrue(result)

    def test_can_generate_proposal(self):
        """can_generate_proposal should check limit."""
        from gear_config import can_generate_proposal, GearState, Gear

        # Under limit
        state = GearState(
            current_gear=Gear.DREAM,
            entered_at="2025-01-01",
            iterations=1,
            last_transition=None,
            patrol_findings_count=0,
            dream_proposals_count=0,
        )
        self.assertTrue(can_generate_proposal(state))

        # At limit
        state.dream_proposals_count = 1
        self.assertFalse(can_generate_proposal(state))


class TestPatrolLimits(unittest.TestCase):
    """Tests for PATROL_LIMITS."""

    def test_has_max_findings(self):
        """Should have max_findings_to_surface."""
        from gear_config import PATROL_LIMITS

        self.assertIn("max_findings_to_surface", PATROL_LIMITS)

    def test_has_sample_violations(self):
        """Should have sample_violations_per_lesson."""
        from gear_config import PATROL_LIMITS

        self.assertIn("sample_violations_per_lesson", PATROL_LIMITS)


class TestDisplayHelpers(unittest.TestCase):
    """Tests for display helper functions."""

    def test_gear_emoji_exists(self):
        """Should have emoji for each gear."""
        from gear_config import GEAR_EMOJI, Gear

        for gear in Gear:
            self.assertIn(gear, GEAR_EMOJI)

    def test_gear_labels_exists(self):
        """Should have labels for each gear."""
        from gear_config import GEAR_LABELS, Gear

        for gear in Gear:
            self.assertIn(gear, GEAR_LABELS)

    def test_format_gear_status(self):
        """format_gear_status should return string."""
        from gear_config import format_gear_status, get_default_gear_state

        state = get_default_gear_state()
        result = format_gear_status(state)
        self.assertIsInstance(result, str)
        self.assertIn("Active", result)


class TestQualityGateOverride(unittest.TestCase):
    """Tests for QualityGateOverride dataclass (v5.2)."""

    def test_to_dict_full_mode(self):
        """QualityGateOverride should serialize to dict in full mode."""
        from gear_config import QualityGateOverride

        override = QualityGateOverride(
            mode="full",
            approved_at="2024-01-01T00:00:00",
            session_id="test-session",
            objective_hash=12345,
            approved_checks=[],
            reason="user_approved",
        )
        result = override.to_dict()

        self.assertEqual(result["mode"], "full")
        self.assertEqual(result["session_id"], "test-session")
        self.assertEqual(result["objective_hash"], 12345)
        self.assertEqual(result["approved_checks"], [])

    def test_to_dict_check_specific_mode(self):
        """QualityGateOverride should serialize approved_checks in check_specific mode."""
        from gear_config import QualityGateOverride

        override = QualityGateOverride(
            mode="check_specific",
            approved_at="2024-01-01T00:00:00",
            session_id="test-session",
            objective_hash=12345,
            approved_checks=["steps_have_proof", "no_dangling_in_progress"],
            reason="user_approved",
        )
        result = override.to_dict()

        self.assertEqual(result["mode"], "check_specific")
        self.assertEqual(result["approved_checks"], ["steps_have_proof", "no_dangling_in_progress"])

    def test_from_dict_full_mode(self):
        """QualityGateOverride should deserialize from dict."""
        from gear_config import QualityGateOverride

        data = {
            "mode": "full",
            "approved_at": "2024-01-01T00:00:00",
            "session_id": "test-session",
            "objective_hash": 12345,
            "approved_checks": [],
            "reason": "user_approved",
        }
        override = QualityGateOverride.from_dict(data)

        self.assertEqual(override.mode, "full")
        self.assertEqual(override.session_id, "test-session")
        self.assertEqual(override.objective_hash, 12345)

    def test_from_dict_defaults_to_full_mode(self):
        """QualityGateOverride should default to full mode (v5.1 backward compat)."""
        from gear_config import QualityGateOverride

        # v5.1 format without mode field
        data = {
            "approved_at": "2024-01-01T00:00:00",
            "session_id": "test-session",
            "objective_hash": 12345,
        }
        override = QualityGateOverride.from_dict(data)

        self.assertEqual(override.mode, "full")  # Default

    def test_from_dict_returns_none_for_none(self):
        """QualityGateOverride.from_dict(None) should return None."""
        from gear_config import QualityGateOverride

        result = QualityGateOverride.from_dict(None)
        self.assertIsNone(result)

    def test_gear_state_serializes_override(self):
        """GearState.to_dict() should serialize QualityGateOverride."""
        from gear_config import GearState, Gear, QualityGateOverride

        override = QualityGateOverride(
            mode="check_specific",
            approved_at="2024-01-01T00:00:00",
            session_id="test",
            objective_hash=123,
            approved_checks=["check1"],
            reason="test",
        )
        state = GearState(
            current_gear=Gear.ACTIVE,
            entered_at="2024-01-01T00:00:00",
            iterations=0,
            last_transition=None,
            patrol_findings_count=0,
            dream_proposals_count=0,
            quality_gate_override=override,
        )
        result = state.to_dict()

        self.assertIsInstance(result["quality_gate_override"], dict)
        self.assertEqual(result["quality_gate_override"]["mode"], "check_specific")
        self.assertEqual(result["quality_gate_override"]["approved_checks"], ["check1"])

    def test_gear_state_deserializes_override(self):
        """GearState.from_dict() should deserialize QualityGateOverride."""
        from gear_config import GearState, QualityGateOverride

        data = {
            "current_gear": "active",
            "entered_at": "2024-01-01T00:00:00",
            "iterations": 0,
            "quality_gate_override": {
                "mode": "check_specific",
                "approved_at": "2024-01-01T00:00:00",
                "session_id": "test",
                "objective_hash": 123,
                "approved_checks": ["check1", "check2"],
                "reason": "test",
            },
        }
        state = GearState.from_dict(data)

        self.assertIsInstance(state.quality_gate_override, QualityGateOverride)
        self.assertEqual(state.quality_gate_override.mode, "check_specific")
        self.assertEqual(state.quality_gate_override.approved_checks, ["check1", "check2"])


if __name__ == "__main__":
    unittest.main()
