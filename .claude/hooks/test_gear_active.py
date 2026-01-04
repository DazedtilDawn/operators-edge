#!/usr/bin/env python3
"""
Tests for gear_active.py - Active Gear execution module.
"""

import pytest
from unittest.mock import MagicMock, patch
from gear_active import (
    ActiveGearResult,
    get_current_step,
    get_step_progress,
    is_objective_complete,
    has_blocked_steps,
    should_junction_for_step,
    check_active_gear_preconditions,
    run_active_gear,
    should_transition_from_active,
    format_active_status,
)
from gear_config import Gear, GearState, GearTransition, get_default_gear_state


def make_gear_state() -> GearState:
    """Create a default GearState for testing."""
    return get_default_gear_state()


# =============================================================================
# ActiveGearResult Tests
# =============================================================================

class TestActiveGearResult:
    """Tests for ActiveGearResult dataclass."""

    def test_basic_creation(self):
        result = ActiveGearResult(
            steps_executed=2,
            steps_completed=1,
            hit_junction=False,
            junction_type=None,
            junction_reason=None,
            objective_completed=False,
            error=None,
        )
        assert result.steps_executed == 2
        assert result.steps_completed == 1
        assert result.hit_junction is False
        assert result.objective_completed is False

    def test_with_junction(self):
        result = ActiveGearResult(
            steps_executed=1,
            steps_completed=0,
            hit_junction=True,
            junction_type="dangerous",
            junction_reason="Step involves 'delete' operation",
            objective_completed=False,
            error=None,
        )
        assert result.hit_junction is True
        assert result.junction_type == "dangerous"
        assert "delete" in result.junction_reason

    def test_with_error(self):
        result = ActiveGearResult(
            steps_executed=0,
            steps_completed=0,
            hit_junction=False,
            junction_type=None,
            junction_reason=None,
            objective_completed=False,
            error="No objective set",
        )
        assert result.error == "No objective set"

    def test_to_dict(self):
        result = ActiveGearResult(
            steps_executed=3,
            steps_completed=2,
            hit_junction=True,
            junction_type="complexity",
            junction_reason="needs review",
            objective_completed=False,
            error=None,
        )
        d = result.to_dict()
        assert d["steps_executed"] == 3
        assert d["steps_completed"] == 2
        assert d["hit_junction"] is True
        assert d["junction_type"] == "complexity"
        assert d["junction_reason"] == "needs review"
        assert d["objective_completed"] is False
        assert d["error"] is None

    def test_to_dict_with_none_values(self):
        result = ActiveGearResult(
            steps_executed=0,
            steps_completed=0,
            hit_junction=False,
            junction_type=None,
            junction_reason=None,
            objective_completed=False,
            error=None,
        )
        d = result.to_dict()
        assert d["junction_type"] is None
        assert d["junction_reason"] is None
        assert d["error"] is None

    def test_completed_objective_result(self):
        result = ActiveGearResult(
            steps_executed=5,
            steps_completed=5,
            hit_junction=False,
            junction_type=None,
            junction_reason=None,
            objective_completed=True,
            error=None,
        )
        assert result.objective_completed is True
        assert result.steps_executed == 5


# =============================================================================
# get_current_step Tests
# =============================================================================

class TestGetCurrentStep:
    """Tests for get_current_step function."""

    def test_empty_plan(self):
        state = {"plan": []}
        assert get_current_step(state) is None

    def test_no_plan_key(self):
        state = {}
        assert get_current_step(state) is None

    def test_first_pending_step(self):
        state = {
            "plan": [
                {"description": "Step 1", "status": "pending"},
                {"description": "Step 2", "status": "pending"},
            ]
        }
        result = get_current_step(state)
        assert result["index"] == 0
        assert result["step"]["description"] == "Step 1"

    def test_in_progress_step_prioritized(self):
        state = {
            "plan": [
                {"description": "Step 1", "status": "completed"},
                {"description": "Step 2", "status": "in_progress"},
                {"description": "Step 3", "status": "pending"},
            ]
        }
        result = get_current_step(state)
        assert result["index"] == 1
        assert result["step"]["status"] == "in_progress"

    def test_skip_completed_steps(self):
        state = {
            "plan": [
                {"description": "Step 1", "status": "completed"},
                {"description": "Step 2", "status": "completed"},
                {"description": "Step 3", "status": "pending"},
            ]
        }
        result = get_current_step(state)
        assert result["index"] == 2
        assert result["step"]["description"] == "Step 3"

    def test_all_steps_completed(self):
        state = {
            "plan": [
                {"description": "Step 1", "status": "completed"},
                {"description": "Step 2", "status": "completed"},
            ]
        }
        assert get_current_step(state) is None

    def test_non_dict_steps_skipped(self):
        state = {
            "plan": [
                "invalid step",
                {"description": "Valid step", "status": "pending"},
            ]
        }
        result = get_current_step(state)
        assert result["index"] == 1
        assert result["step"]["description"] == "Valid step"

    def test_step_without_status_treated_as_pending(self):
        state = {
            "plan": [
                {"description": "Step 1"},  # No status
            ]
        }
        result = get_current_step(state)
        assert result["index"] == 0

    def test_blocked_steps_not_returned(self):
        state = {
            "plan": [
                {"description": "Step 1", "status": "blocked"},
                {"description": "Step 2", "status": "pending"},
            ]
        }
        result = get_current_step(state)
        assert result["index"] == 1  # Skip blocked, get pending


# =============================================================================
# get_step_progress Tests
# =============================================================================

class TestGetStepProgress:
    """Tests for get_step_progress function."""

    def test_empty_plan(self):
        state = {"plan": []}
        completed, total = get_step_progress(state)
        assert completed == 0
        assert total == 0

    def test_no_completed_steps(self):
        state = {
            "plan": [
                {"description": "Step 1", "status": "pending"},
                {"description": "Step 2", "status": "pending"},
            ]
        }
        completed, total = get_step_progress(state)
        assert completed == 0
        assert total == 2

    def test_some_completed(self):
        state = {
            "plan": [
                {"description": "Step 1", "status": "completed"},
                {"description": "Step 2", "status": "in_progress"},
                {"description": "Step 3", "status": "pending"},
            ]
        }
        completed, total = get_step_progress(state)
        assert completed == 1
        assert total == 3

    def test_all_completed(self):
        state = {
            "plan": [
                {"description": "Step 1", "status": "completed"},
                {"description": "Step 2", "status": "completed"},
            ]
        }
        completed, total = get_step_progress(state)
        assert completed == 2
        assert total == 2

    def test_non_dict_steps_counted_in_total(self):
        state = {
            "plan": [
                "invalid",
                {"description": "Step 1", "status": "completed"},
            ]
        }
        completed, total = get_step_progress(state)
        assert completed == 1
        assert total == 2

    def test_no_plan_key(self):
        state = {}
        completed, total = get_step_progress(state)
        assert completed == 0
        assert total == 0


# =============================================================================
# is_objective_complete Tests
# =============================================================================

class TestIsObjectiveComplete:
    """Tests for is_objective_complete function."""

    def test_empty_plan_not_complete(self):
        state = {"plan": []}
        assert is_objective_complete(state) is False

    def test_all_completed(self):
        state = {
            "plan": [
                {"description": "Step 1", "status": "completed"},
                {"description": "Step 2", "status": "completed"},
            ]
        }
        assert is_objective_complete(state) is True

    def test_some_pending(self):
        state = {
            "plan": [
                {"description": "Step 1", "status": "completed"},
                {"description": "Step 2", "status": "pending"},
            ]
        }
        assert is_objective_complete(state) is False

    def test_some_in_progress(self):
        state = {
            "plan": [
                {"description": "Step 1", "status": "completed"},
                {"description": "Step 2", "status": "in_progress"},
            ]
        }
        assert is_objective_complete(state) is False

    def test_non_dict_steps_skipped(self):
        state = {
            "plan": [
                {"description": "Step 1", "status": "completed"},
                "invalid step",
            ]
        }
        # Only dict steps count, so all dict steps are completed
        assert is_objective_complete(state) is True

    def test_no_plan_key(self):
        state = {}
        assert is_objective_complete(state) is False


# =============================================================================
# has_blocked_steps Tests
# =============================================================================

class TestHasBlockedSteps:
    """Tests for has_blocked_steps function."""

    def test_no_blocked_steps(self):
        state = {
            "plan": [
                {"description": "Step 1", "status": "completed"},
                {"description": "Step 2", "status": "pending"},
            ]
        }
        assert has_blocked_steps(state) is False

    def test_has_blocked_step(self):
        state = {
            "plan": [
                {"description": "Step 1", "status": "completed"},
                {"description": "Step 2", "status": "blocked"},
            ]
        }
        assert has_blocked_steps(state) is True

    def test_empty_plan(self):
        state = {"plan": []}
        assert has_blocked_steps(state) is False

    def test_non_dict_steps_skipped(self):
        state = {
            "plan": [
                "invalid",
                {"description": "Step 1", "status": "pending"},
            ]
        }
        assert has_blocked_steps(state) is False


# =============================================================================
# should_junction_for_step Tests
# =============================================================================

class TestShouldJunctionForStep:
    """Tests for should_junction_for_step function."""

    def test_normal_step_no_junction(self):
        step = {"description": "Add a new function to utils.py"}
        should, jtype, reason = should_junction_for_step(step)
        assert should is False
        assert jtype is None
        assert reason is None

    def test_delete_operation(self):
        step = {"description": "Delete the old config file"}
        should, jtype, reason = should_junction_for_step(step)
        assert should is True
        assert jtype == "dangerous"
        assert "delete" in reason

    def test_remove_operation(self):
        step = {"description": "Remove deprecated endpoints"}
        should, jtype, reason = should_junction_for_step(step)
        assert should is True
        assert jtype == "dangerous"

    def test_push_operation(self):
        step = {"description": "Push changes to main branch"}
        should, jtype, reason = should_junction_for_step(step)
        assert should is True
        assert jtype == "dangerous"
        assert "push" in reason

    def test_deploy_operation(self):
        step = {"description": "Deploy to production"}
        should, jtype, reason = should_junction_for_step(step)
        assert should is True
        assert jtype == "dangerous"

    def test_refactor_operation(self):
        step = {"description": "Refactor the authentication module"}
        should, jtype, reason = should_junction_for_step(step)
        assert should is True
        assert jtype == "complexity"
        assert "refactor" in reason

    def test_rewrite_operation(self):
        step = {"description": "Rewrite the parser"}
        should, jtype, reason = should_junction_for_step(step)
        assert should is True
        assert jtype == "complexity"

    def test_architecture_change(self):
        step = {"description": "Update the architecture to microservices"}
        should, jtype, reason = should_junction_for_step(step)
        assert should is True
        assert jtype == "complexity"

    def test_case_insensitive(self):
        step = {"description": "DELETE the old file"}
        should, jtype, reason = should_junction_for_step(step)
        assert should is True
        assert jtype == "dangerous"

    def test_dangerous_prioritized_over_complex(self):
        # If both keywords present, dangerous should be caught first
        step = {"description": "Delete and refactor the module"}
        should, jtype, reason = should_junction_for_step(step)
        assert should is True
        assert jtype == "dangerous"  # "delete" checked before "refactor"

    def test_migrate_operation(self):
        step = {"description": "Migrate database schema"}
        should, jtype, reason = should_junction_for_step(step)
        assert should is True
        assert jtype == "dangerous"

    def test_publish_operation(self):
        step = {"description": "Publish package to npm"}
        should, jtype, reason = should_junction_for_step(step)
        assert should is True
        assert jtype == "dangerous"

    def test_empty_description(self):
        step = {"description": ""}
        should, jtype, reason = should_junction_for_step(step)
        assert should is False

    def test_no_description_key(self):
        step = {}
        should, jtype, reason = should_junction_for_step(step)
        assert should is False


# =============================================================================
# check_active_gear_preconditions Tests
# =============================================================================

class TestCheckActiveGearPreconditions:
    """Tests for check_active_gear_preconditions function."""

    def test_valid_state(self):
        state = {
            "objective": "Add feature X",
            "plan": [
                {"description": "Step 1", "status": "pending"},
            ]
        }
        can_run, error = check_active_gear_preconditions(state)
        assert can_run is True
        assert error is None

    def test_no_objective(self):
        state = {
            "objective": "",
            "plan": [
                {"description": "Step 1", "status": "pending"},
            ]
        }
        can_run, error = check_active_gear_preconditions(state)
        assert can_run is False
        assert "No objective" in error

    def test_whitespace_only_objective(self):
        state = {
            "objective": "   ",
            "plan": [
                {"description": "Step 1", "status": "pending"},
            ]
        }
        can_run, error = check_active_gear_preconditions(state)
        assert can_run is False
        assert "No objective" in error

    def test_no_plan(self):
        state = {
            "objective": "Add feature X",
            "plan": []
        }
        can_run, error = check_active_gear_preconditions(state)
        assert can_run is False
        assert "No plan" in error

    def test_missing_plan_key(self):
        state = {
            "objective": "Add feature X",
        }
        can_run, error = check_active_gear_preconditions(state)
        assert can_run is False
        assert "No plan" in error

    def test_objective_complete(self):
        state = {
            "objective": "Add feature X",
            "plan": [
                {"description": "Step 1", "status": "completed"},
            ]
        }
        can_run, error = check_active_gear_preconditions(state)
        assert can_run is False
        assert "already complete" in error

    def test_blocked_steps(self):
        state = {
            "objective": "Add feature X",
            "plan": [
                {"description": "Step 1", "status": "blocked"},
                {"description": "Step 2", "status": "pending"},
            ]
        }
        can_run, error = check_active_gear_preconditions(state)
        assert can_run is False
        assert "blocked" in error


# =============================================================================
# run_active_gear Tests
# =============================================================================

class TestRunActiveGear:
    """Tests for run_active_gear function."""

    def test_no_objective_returns_error(self):
        state = {"objective": "", "plan": []}
        gear_state = make_gear_state()
        result = run_active_gear(state, gear_state)
        assert result.error == "No objective set"
        assert result.steps_executed == 0

    def test_no_plan_returns_error(self):
        state = {"objective": "Test", "plan": []}
        gear_state = make_gear_state()
        result = run_active_gear(state, gear_state)
        assert result.error == "No plan defined"

    def test_executes_pending_step(self):
        state = {
            "objective": "Test",
            "plan": [
                {"description": "Add tests", "status": "pending"},
            ]
        }
        gear_state = make_gear_state()
        result = run_active_gear(state, gear_state)
        assert result.steps_executed == 1
        assert result.hit_junction is False
        assert result.error is None

    def test_hits_dangerous_junction(self):
        state = {
            "objective": "Test",
            "plan": [
                {"description": "Delete all files", "status": "pending"},
            ]
        }
        gear_state = make_gear_state()
        result = run_active_gear(state, gear_state)
        assert result.hit_junction is True
        assert result.junction_type == "dangerous"
        assert result.steps_executed == 0

    def test_hits_complexity_junction(self):
        state = {
            "objective": "Test",
            "plan": [
                {"description": "Refactor the entire codebase", "status": "pending"},
            ]
        }
        gear_state = make_gear_state()
        result = run_active_gear(state, gear_state)
        assert result.hit_junction is True
        assert result.junction_type == "complexity"

    def test_objective_complete_when_no_steps(self):
        state = {
            "objective": "Test",
            "plan": [
                {"description": "Step 1", "status": "completed"},
            ]
        }
        gear_state = make_gear_state()
        result = run_active_gear(state, gear_state)
        assert result.error == "Objective already complete"

    def test_blocked_steps_error(self):
        state = {
            "objective": "Test",
            "plan": [
                {"description": "Step 1", "status": "blocked"},
            ]
        }
        gear_state = make_gear_state()
        result = run_active_gear(state, gear_state)
        assert "blocked" in result.error

    def test_max_steps_respected(self):
        state = {
            "objective": "Test",
            "plan": [
                {"description": f"Step {i}", "status": "pending"}
                for i in range(20)
            ]
        }
        gear_state = make_gear_state()
        result = run_active_gear(state, gear_state, max_steps=1)
        # Should only analyze one step before returning
        assert result.steps_executed == 1


# =============================================================================
# should_transition_from_active Tests
# =============================================================================

class TestShouldTransitionFromActive:
    """Tests for should_transition_from_active function."""

    def test_complete_triggers_transition(self):
        state = {
            "plan": [
                {"description": "Step 1", "status": "completed"},
            ]
        }
        should, transition = should_transition_from_active(state)
        assert should is True
        assert transition == GearTransition.ACTIVE_TO_PATROL

    def test_pending_no_transition(self):
        state = {
            "plan": [
                {"description": "Step 1", "status": "pending"},
            ]
        }
        should, transition = should_transition_from_active(state)
        assert should is False
        assert transition is None

    def test_in_progress_no_transition(self):
        state = {
            "plan": [
                {"description": "Step 1", "status": "in_progress"},
            ]
        }
        should, transition = should_transition_from_active(state)
        assert should is False
        assert transition is None

    def test_empty_plan_no_transition(self):
        state = {"plan": []}
        should, transition = should_transition_from_active(state)
        assert should is False


# =============================================================================
# format_active_status Tests
# =============================================================================

class TestFormatActiveStatus:
    """Tests for format_active_status function."""

    def test_basic_format(self):
        state = {
            "objective": "Add feature X",
            "plan": [
                {"description": "Step 1", "status": "completed"},
                {"description": "Step 2", "status": "in_progress"},
            ]
        }
        output = format_active_status(state)
        assert "ACTIVE GEAR" in output
        assert "Add feature X" in output
        assert "1/2" in output
        assert "Step 2" in output

    def test_truncates_long_objective(self):
        state = {
            "objective": "A" * 100,
            "plan": [
                {"description": "Step 1", "status": "pending"},
            ]
        }
        output = format_active_status(state)
        assert "..." in output

    def test_truncates_long_step_description(self):
        state = {
            "objective": "Test",
            "plan": [
                {"description": "B" * 100, "status": "pending"},
            ]
        }
        output = format_active_status(state)
        assert "..." in output

    def test_no_current_step(self):
        state = {
            "objective": "Test",
            "plan": [
                {"description": "Step 1", "status": "completed"},
            ]
        }
        output = format_active_status(state)
        assert "None" in output or "Current" in output

    def test_no_objective(self):
        state = {
            "plan": []
        }
        output = format_active_status(state)
        assert "No objective" in output

    def test_progress_display(self):
        state = {
            "objective": "Test",
            "plan": [
                {"description": "S1", "status": "completed"},
                {"description": "S2", "status": "completed"},
                {"description": "S3", "status": "pending"},
            ]
        }
        output = format_active_status(state)
        assert "2/3" in output


# =============================================================================
# Edge Cases and Integration Tests
# =============================================================================

class TestEdgeCases:
    """Edge case tests for gear_active module."""

    def test_mixed_invalid_steps(self):
        state = {
            "objective": "Test",
            "plan": [
                None,
                "string step",
                123,
                {"description": "Valid", "status": "pending"},
            ]
        }
        gear_state = make_gear_state()
        result = run_active_gear(state, gear_state)
        assert result.steps_executed == 1
        assert result.error is None

    def test_step_missing_status_field(self):
        state = {
            "objective": "Test",
            "plan": [
                {"description": "No status"},  # Missing status
            ]
        }
        # Should treat as pending
        current = get_current_step(state)
        assert current is not None
        assert current["index"] == 0

    def test_empty_state(self):
        state = {}
        gear_state = make_gear_state()
        result = run_active_gear(state, gear_state)
        assert result.error is not None

    def test_multiple_in_progress_steps(self):
        # Edge case: multiple in_progress (shouldn't happen, but handle it)
        state = {
            "plan": [
                {"description": "Step 1", "status": "in_progress"},
                {"description": "Step 2", "status": "in_progress"},
            ]
        }
        current = get_current_step(state)
        # Should return first one
        assert current["index"] == 0

    def test_junction_keywords_partial_match(self):
        # "published" contains "publish" - should still trigger
        step = {"description": "Check published packages"}
        should, jtype, reason = should_junction_for_step(step)
        assert should is True
        assert jtype == "dangerous"

    def test_keyword_in_middle_of_word(self):
        # "removed" contains "remove"
        step = {"description": "Handle removed items"}
        should, jtype, reason = should_junction_for_step(step)
        assert should is True
