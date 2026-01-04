#!/usr/bin/env python3
"""
Tests for prune_skill_hook.py - the mechanical prune execution hook.
"""
import pytest
import json
import os
import sys
from pathlib import Path
from unittest.mock import patch, MagicMock
from datetime import datetime

# Add hooks directory to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from prune_skill_hook import (
    format_prune_report,
    execute_prune,
    format_prune_results,
    handle_prune,
)


# =============================================================================
# FIXTURES
# =============================================================================

@pytest.fixture
def empty_state():
    """State with no prunable items."""
    return {
        "objective": "Test objective",
        "plan": [],
        "mismatches": [],
        "memory": [],
    }


@pytest.fixture
def state_with_completed_steps():
    """State with completed steps to prune."""
    return {
        "objective": "Test objective",
        "plan": [
            {"description": "Step 1", "status": "completed", "proof": "done"},
            {"description": "Step 2", "status": "completed", "proof": "done"},
            {"description": "Step 3", "status": "completed", "proof": "done"},
            {"description": "Step 4", "status": "in_progress"},
        ],
        "mismatches": [],
        "memory": [],
    }


@pytest.fixture
def state_with_resolved_mismatches():
    """State with resolved mismatches to archive."""
    return {
        "objective": "Test objective",
        "plan": [],
        "mismatches": [
            {
                "id": "mismatch-001",
                "expectation": "API returns 200",
                "observation": "API returns 403",
                "resolved": True,
                "resolution": "Added auth token",
                "trigger": "API + auth + 403",
            },
        ],
        "memory": [],
    }


@pytest.fixture
def state_with_stale_memory():
    """State with stale memory items to decay."""
    return {
        "objective": "Test objective",
        "plan": [],
        "mismatches": [],
        "memory": [
            {
                "trigger": "old thing",
                "lesson": "Some old lesson",
                "reinforced": 0,
                "last_used": "2024-01-01",
            },
        ],
    }


@pytest.fixture
def empty_prune_plan():
    """Prune plan with nothing to prune."""
    return {
        "steps": [],
        "mismatches": [],
        "memory": [],
    }


@pytest.fixture
def full_prune_plan():
    """Prune plan with items to prune."""
    return {
        "steps": [
            {"index": 0, "step": {"description": "Step 1", "status": "completed"}},
            {"index": 1, "step": {"description": "Step 2", "status": "completed"}},
        ],
        "mismatches": [
            {
                "id": "mismatch-001",
                "resolved": True,
                "resolution": "Fixed it",
                "trigger": "test trigger",
            },
        ],
        "memory": [
            {"trigger": "stale", "lesson": "Old lesson", "decay_reason": "stale"},
        ],
    }


# =============================================================================
# FORMAT PRUNE REPORT TESTS
# =============================================================================

class TestFormatPruneReport:
    """Tests for format_prune_report function."""

    def test_report_contains_header(self, empty_state, empty_prune_plan):
        """Report should include header."""
        result = format_prune_report(empty_state, empty_prune_plan)
        assert "OPERATOR'S EDGE" in result
        assert "PRUNE ANALYSIS" in result

    def test_report_shows_objective(self, empty_state, empty_prune_plan):
        """Report should show current objective."""
        result = format_prune_report(empty_state, empty_prune_plan)
        assert "Test objective" in result

    def test_report_shows_entropy_status(self, empty_state, empty_prune_plan):
        """Report should show entropy status."""
        result = format_prune_report(empty_state, empty_prune_plan)
        assert "Entropy Status:" in result

    def test_report_shows_prune_breakdown(self, empty_state, full_prune_plan):
        """Report should show breakdown of prunable items."""
        result = format_prune_report(empty_state, full_prune_plan)
        assert "Steps to archive:" in result
        assert "Mismatches to archive:" in result
        assert "Lessons to decay:" in result

    def test_report_shows_estimate(self, empty_state, full_prune_plan):
        """Report should show estimate of savings."""
        result = format_prune_report(empty_state, full_prune_plan)
        assert "Total items to prune:" in result
        assert "Estimated lines saved:" in result

    def test_empty_prune_shows_no_action(self, empty_state, empty_prune_plan):
        """Report should indicate no pruning needed when empty."""
        result = format_prune_report(empty_state, empty_prune_plan)
        assert "No pruning needed" in result or "Total items to prune: 0" in result

    def test_report_truncates_long_descriptions(self, empty_state, full_prune_plan):
        """Report should handle long descriptions gracefully."""
        long_step = {
            "index": 0,
            "step": {"description": "A" * 100, "status": "completed"}
        }
        full_prune_plan["steps"] = [long_step]
        result = format_prune_report(empty_state, full_prune_plan)
        # Should truncate and add ellipsis
        assert "..." in result


# =============================================================================
# EXECUTE PRUNE TESTS
# =============================================================================

class TestExecutePrune:
    """Tests for execute_prune function."""

    @patch('prune_skill_hook.archive_completed_step')
    def test_archives_steps(self, mock_archive, empty_state, full_prune_plan):
        """Should archive completed steps."""
        empty_state["session"] = {"id": "test-session"}

        result = execute_prune(empty_state, full_prune_plan)

        assert result["steps_archived"] == 2
        assert mock_archive.call_count == 2

    @patch('prune_skill_hook.archive_resolved_mismatch')
    @patch('prune_skill_hook.validate_mismatch_for_archive')
    def test_archives_mismatches(self, mock_validate, mock_archive, empty_state, full_prune_plan):
        """Should archive resolved mismatches."""
        empty_state["session"] = {"id": "test-session"}
        mock_validate.return_value = (True, None)

        result = execute_prune(empty_state, full_prune_plan)

        assert result["mismatches_archived"] == 1
        assert result["lessons_extracted"] == 1

    @patch('prune_skill_hook.archive_decayed_lesson')
    def test_decays_memory(self, mock_decay, empty_state, full_prune_plan):
        """Should decay stale memory items."""
        empty_state["session"] = {"id": "test-session"}

        result = execute_prune(empty_state, full_prune_plan)

        assert result["lessons_decayed"] == 1
        mock_decay.assert_called_once()

    @patch('prune_skill_hook.archive_completed_step')
    def test_handles_archive_errors(self, mock_archive, empty_state, full_prune_plan):
        """Should capture errors without crashing."""
        empty_state["session"] = {"id": "test-session"}
        mock_archive.side_effect = Exception("Archive failed")

        result = execute_prune(empty_state, full_prune_plan)

        assert len(result["errors"]) > 0
        assert "Archive failed" in result["errors"][0]

    def test_empty_prune_plan(self, empty_state, empty_prune_plan):
        """Should handle empty prune plan."""
        empty_state["session"] = {"id": "test-session"}

        result = execute_prune(empty_state, empty_prune_plan)

        assert result["steps_archived"] == 0
        assert result["mismatches_archived"] == 0
        assert result["lessons_decayed"] == 0
        assert len(result["errors"]) == 0


# =============================================================================
# FORMAT PRUNE RESULTS TESTS
# =============================================================================

class TestFormatPruneResults:
    """Tests for format_prune_results function."""

    def test_shows_counts(self):
        """Results should show all counts."""
        results = {
            "steps_archived": 3,
            "mismatches_archived": 1,
            "lessons_extracted": 1,
            "lessons_decayed": 2,
            "errors": [],
        }

        output = format_prune_results(results)

        assert "Steps archived: 3" in output
        assert "Mismatches archived: 1" in output
        assert "Lessons extracted: 1" in output
        assert "Lessons decayed: 2" in output

    def test_shows_errors(self):
        """Results should show errors if any."""
        results = {
            "steps_archived": 0,
            "mismatches_archived": 0,
            "lessons_extracted": 0,
            "lessons_decayed": 0,
            "errors": ["Error 1", "Error 2"],
        }

        output = format_prune_results(results)

        assert "Errors (2)" in output
        assert "Error 1" in output
        assert "Error 2" in output

    def test_shows_completion_note(self):
        """Results should include note about updating state."""
        results = {
            "steps_archived": 1,
            "mismatches_archived": 0,
            "lessons_extracted": 0,
            "lessons_decayed": 0,
            "errors": [],
        }

        output = format_prune_results(results)

        assert "update active_context.yaml" in output.lower() or "NOTE" in output


# =============================================================================
# HANDLE PRUNE TESTS
# =============================================================================

class TestHandlePrune:
    """Tests for handle_prune function."""

    @patch('prune_skill_hook.load_yaml_state')
    @patch('prune_skill_hook.compute_prune_plan')
    def test_returns_report(self, mock_compute, mock_load):
        """Should return a formatted report."""
        mock_load.return_value = {"objective": "Test", "plan": []}
        mock_compute.return_value = {"steps": [], "mismatches": [], "memory": []}

        result = handle_prune()

        assert "PRUNE ANALYSIS" in result
        assert "OPERATOR'S EDGE" in result

    @patch('prune_skill_hook.load_yaml_state')
    @patch('prune_skill_hook.compute_prune_plan')
    @patch('prune_skill_hook.execute_prune')
    def test_executes_when_items_to_prune(self, mock_exec, mock_compute, mock_load):
        """Should execute prune when there are items."""
        mock_load.return_value = {"objective": "Test", "plan": []}
        mock_compute.return_value = {
            "steps": [{"index": 0, "step": {"description": "Test"}}],
            "mismatches": [],
            "memory": [],
        }
        mock_exec.return_value = {
            "steps_archived": 1,
            "mismatches_archived": 0,
            "lessons_extracted": 0,
            "lessons_decayed": 0,
            "errors": [],
        }

        result = handle_prune()

        mock_exec.assert_called_once()
        assert "PRUNE COMPLETE" in result

    @patch('prune_skill_hook.load_yaml_state')
    @patch('prune_skill_hook.compute_prune_plan')
    def test_skips_execution_when_nothing_to_prune(self, mock_compute, mock_load):
        """Should skip execution when nothing to prune."""
        mock_load.return_value = {"objective": "Test", "plan": []}
        mock_compute.return_value = {"steps": [], "mismatches": [], "memory": []}

        result = handle_prune()

        # Should not contain completion message (no execution)
        assert "PRUNE COMPLETE" not in result

    @patch('prune_skill_hook.load_yaml_state')
    def test_handles_none_state(self, mock_load):
        """Should handle None state gracefully."""
        mock_load.return_value = None

        # Should not raise
        result = handle_prune()
        assert "PRUNE ANALYSIS" in result


# =============================================================================
# INTEGRATION TESTS
# =============================================================================

class TestIntegration:
    """Integration tests for the prune hook."""

    @patch('prune_skill_hook.load_yaml_state')
    @patch('prune_skill_hook.compute_prune_plan')
    @patch('prune_skill_hook.archive_completed_step')
    def test_full_prune_flow(self, mock_archive, mock_compute, mock_load):
        """Test complete prune flow from state to output."""
        mock_load.return_value = {
            "objective": "Integration test",
            "session": {"id": "test-session"},
            "plan": [
                {"description": "Done", "status": "completed"},
                {"description": "Current", "status": "in_progress"},
            ],
        }
        mock_compute.return_value = {
            "steps": [{"index": 0, "step": {"description": "Done", "status": "completed"}}],
            "mismatches": [],
            "memory": [],
        }

        result = handle_prune()

        # Should have full report
        assert "PRUNE ANALYSIS" in result
        assert "Integration test" in result
        assert "PRUNE COMPLETE" in result
        assert "Steps archived: 1" in result


# =============================================================================
# EDGE CASES
# =============================================================================

class TestEdgeCases:
    """Edge case tests."""

    def test_format_empty_state(self, empty_prune_plan):
        """Should handle completely empty state."""
        empty_state = {}
        result = format_prune_report(empty_state, empty_prune_plan)
        assert "PRUNE ANALYSIS" in result

    def test_format_none_objective(self, empty_prune_plan):
        """Should handle None objective."""
        state = {"objective": None, "plan": []}
        result = format_prune_report(state, empty_prune_plan)
        assert "PRUNE ANALYSIS" in result

    def test_execute_with_missing_step_fields(self, empty_state):
        """Should handle steps with missing fields."""
        empty_state["session"] = {"id": "test"}
        prune_plan = {
            "steps": [{"index": 0}],  # Missing 'step' key
            "mismatches": [],
            "memory": [],
        }

        # Should not crash
        result = execute_prune(empty_state, prune_plan)
        # May have errors but shouldn't crash
        assert isinstance(result, dict)

    @patch('prune_skill_hook.validate_mismatch_for_archive')
    def test_execute_with_invalid_mismatch(self, mock_validate, empty_state):
        """Should handle invalid mismatches gracefully."""
        empty_state["session"] = {"id": "test"}
        mock_validate.return_value = (False, "Missing trigger")

        prune_plan = {
            "steps": [],
            "mismatches": [{"id": "bad", "resolved": True}],
            "memory": [],
        }

        result = execute_prune(empty_state, prune_plan)

        # Should record the validation error
        assert result["mismatches_archived"] == 0
        assert len(result["errors"]) > 0
