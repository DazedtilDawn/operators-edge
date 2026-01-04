#!/usr/bin/env python3
"""
Tests for context_utils.py

Coverage:
- Individual context check helpers
- Main detect_session_context function
- Orchestrator suggestion mapping
- Priority ordering of checks
"""

import unittest
from unittest.mock import patch, MagicMock

import context_utils
from edge_config import SessionContext


class TestCheckPlanExists(unittest.TestCase):
    """Tests for _check_plan_exists helper."""

    def test_returns_needs_plan_when_no_plan(self):
        """Should return NEEDS_PLAN when plan is empty."""
        state = {"plan": []}
        result = context_utils._check_plan_exists(state)
        self.assertEqual(result[0], SessionContext.NEEDS_PLAN)
        self.assertIn("No plan", result[1]["reason"])

    def test_returns_needs_plan_when_plan_missing(self):
        """Should return NEEDS_PLAN when plan key missing."""
        state = {}
        result = context_utils._check_plan_exists(state)
        self.assertEqual(result[0], SessionContext.NEEDS_PLAN)

    def test_returns_needs_plan_when_no_objective(self):
        """Should return NEEDS_PLAN when objective is empty."""
        state = {"plan": [{"description": "Step 1"}], "objective": ""}
        result = context_utils._check_plan_exists(state)
        self.assertEqual(result[0], SessionContext.NEEDS_PLAN)
        self.assertIn("No objective", result[1]["reason"])

    def test_returns_needs_plan_when_objective_is_placeholder(self):
        """Should return NEEDS_PLAN when objective is placeholder text."""
        state = {"plan": [{"description": "Step 1"}], "objective": "Set your objective here"}
        result = context_utils._check_plan_exists(state)
        self.assertEqual(result[0], SessionContext.NEEDS_PLAN)

    def test_returns_needs_plan_when_objective_is_null(self):
        """Should return NEEDS_PLAN when objective is 'null'."""
        state = {"plan": [{"description": "Step 1"}], "objective": "null"}
        result = context_utils._check_plan_exists(state)
        self.assertEqual(result[0], SessionContext.NEEDS_PLAN)

    def test_returns_none_when_plan_and_objective_exist(self):
        """Should return None when both plan and objective exist."""
        state = {"plan": [{"description": "Step 1"}], "objective": "Real objective"}
        result = context_utils._check_plan_exists(state)
        self.assertIsNone(result)


class TestCheckResearchStatus(unittest.TestCase):
    """Tests for _check_research_status helper."""

    @patch.object(context_utils, 'get_blocking_research')
    def test_returns_none_when_no_blocking_research(self, mock_get):
        """Should return None when no blocking research."""
        mock_get.return_value = []
        result = context_utils._check_research_status({})
        self.assertIsNone(result)

    @patch.object(context_utils, 'get_blocking_research')
    def test_returns_awaiting_when_in_progress(self, mock_get):
        """Should return AWAITING_RESEARCH when research in progress."""
        mock_get.return_value = [{"topic": "Test", "status": "in_progress"}]
        result = context_utils._check_research_status({})
        self.assertEqual(result[0], SessionContext.AWAITING_RESEARCH)
        self.assertIn("awaiting results", result[1]["reason"])

    @patch.object(context_utils, 'get_blocking_research')
    def test_returns_needs_when_pending(self, mock_get):
        """Should return NEEDS_RESEARCH when research pending."""
        mock_get.return_value = [{"topic": "Test", "status": "pending"}]
        result = context_utils._check_research_status({})
        self.assertEqual(result[0], SessionContext.NEEDS_RESEARCH)
        self.assertIn("pending", result[1]["reason"])

    @patch.object(context_utils, 'get_blocking_research')
    def test_in_progress_takes_priority_over_pending(self, mock_get):
        """In-progress research should take priority over pending."""
        mock_get.return_value = [
            {"topic": "A", "status": "in_progress"},
            {"topic": "B", "status": "pending"}
        ]
        result = context_utils._check_research_status({})
        self.assertEqual(result[0], SessionContext.AWAITING_RESEARCH)


class TestCheckMismatches(unittest.TestCase):
    """Tests for _check_mismatches helper."""

    @patch.object(context_utils, 'get_unresolved_mismatches')
    def test_returns_none_when_no_mismatches(self, mock_get):
        """Should return None when no unresolved mismatches."""
        mock_get.return_value = []
        result = context_utils._check_mismatches({})
        self.assertIsNone(result)

    @patch.object(context_utils, 'get_unresolved_mismatches')
    def test_returns_needs_adaptation_when_mismatches(self, mock_get):
        """Should return NEEDS_ADAPTATION when mismatches exist."""
        mock_get.return_value = [{"what": "Test mismatch"}]
        result = context_utils._check_mismatches({})
        self.assertEqual(result[0], SessionContext.NEEDS_ADAPTATION)
        self.assertIn("1 unresolved", result[1]["reason"])


class TestCheckEntropy(unittest.TestCase):
    """Tests for _check_entropy helper."""

    @patch.object(context_utils, 'check_state_entropy')
    def test_returns_none_when_no_pruning_needed(self, mock_check):
        """Should return None when entropy is low."""
        mock_check.return_value = (False, [])
        result = context_utils._check_entropy({})
        self.assertIsNone(result)

    @patch.object(context_utils, 'check_state_entropy')
    def test_returns_needs_pruning_when_entropy_high(self, mock_check):
        """Should return NEEDS_PRUNING when entropy is high."""
        mock_check.return_value = (True, ["Too many completed steps"])
        result = context_utils._check_entropy({})
        self.assertEqual(result[0], SessionContext.NEEDS_PRUNING)
        self.assertIn("pruning", result[1]["reason"])


class TestCheckPlanProgress(unittest.TestCase):
    """Tests for _check_plan_progress helper."""

    @patch.object(context_utils, 'get_step_by_status')
    def test_returns_needs_scoring_when_all_done_no_score(self, mock_get):
        """Should return NEEDS_SCORING when all steps done but no score."""
        mock_get.side_effect = lambda s, status: []  # No steps in any status
        state = {}  # No self_score
        result = context_utils._check_plan_progress(state)
        self.assertEqual(result[0], SessionContext.NEEDS_SCORING)

    @patch.object(context_utils, 'get_step_by_status')
    def test_returns_all_complete_when_scored(self, mock_get):
        """Should return ALL_COMPLETE when all steps done and scored."""
        mock_get.side_effect = lambda s, status: []
        state = {"self_score": {"total": 5}}
        result = context_utils._check_plan_progress(state)
        self.assertEqual(result[0], SessionContext.ALL_COMPLETE)

    @patch.object(context_utils, 'get_step_by_status')
    def test_returns_needs_adaptation_when_blocked(self, mock_get):
        """Should return NEEDS_ADAPTATION when steps are blocked."""
        def mock_status(s, status):
            if status == 'blocked':
                return [{"description": "Blocked step"}]
            return []
        mock_get.side_effect = mock_status
        result = context_utils._check_plan_progress({})
        self.assertEqual(result[0], SessionContext.NEEDS_ADAPTATION)
        self.assertIn("blocked", result[1]["reason"])

    @patch.object(context_utils, 'get_step_by_status')
    def test_returns_step_in_progress_when_active(self, mock_get):
        """Should return STEP_IN_PROGRESS when step is active."""
        def mock_status(s, status):
            if status == 'in_progress':
                return [{"description": "Active step"}]
            if status == 'pending':
                return [{"description": "Next step"}]
            return []
        mock_get.side_effect = mock_status
        result = context_utils._check_plan_progress({})
        self.assertEqual(result[0], SessionContext.STEP_IN_PROGRESS)

    @patch.object(context_utils, 'get_step_by_status')
    def test_returns_ready_for_step_when_pending(self, mock_get):
        """Should return READY_FOR_STEP when steps are pending."""
        def mock_status(s, status):
            if status == 'pending':
                return [{"description": "Next step"}]
            return []
        mock_get.side_effect = mock_status
        result = context_utils._check_plan_progress({"current_step": 2})
        self.assertEqual(result[0], SessionContext.READY_FOR_STEP)
        self.assertIn("step 2", result[1]["reason"])


class TestDetectSessionContext(unittest.TestCase):
    """Tests for main detect_session_context function."""

    def test_returns_needs_plan_when_no_state(self):
        """Should return NEEDS_PLAN when state is None."""
        result = context_utils.detect_session_context(None)
        self.assertEqual(result[0], SessionContext.NEEDS_PLAN)
        self.assertIn("No state", result[1]["reason"])

    def test_returns_needs_plan_when_state_empty(self):
        """Should return NEEDS_PLAN when state is empty dict."""
        result = context_utils.detect_session_context({})
        self.assertEqual(result[0], SessionContext.NEEDS_PLAN)

    @patch.object(context_utils, '_check_plan_progress')
    @patch.object(context_utils, '_check_entropy')
    @patch.object(context_utils, '_check_mismatches')
    @patch.object(context_utils, '_check_research_status')
    @patch.object(context_utils, '_check_plan_exists')
    def test_checks_in_priority_order(self, mock_plan, mock_research, mock_mismatch, mock_entropy, mock_progress):
        """Should check conditions in correct priority order."""
        # All return None except progress
        mock_plan.return_value = None
        mock_research.return_value = None
        mock_mismatch.return_value = None
        mock_entropy.return_value = None
        mock_progress.return_value = (SessionContext.READY_FOR_STEP, {})

        state = {"plan": [{"d": "s"}], "objective": "Test"}
        context_utils.detect_session_context(state)

        # All should be called
        mock_plan.assert_called_once()
        mock_research.assert_called_once()
        mock_mismatch.assert_called_once()
        mock_entropy.assert_called_once()
        mock_progress.assert_called_once()

    @patch.object(context_utils, '_check_plan_exists')
    def test_stops_at_first_match(self, mock_plan):
        """Should return first matching context."""
        mock_plan.return_value = (SessionContext.NEEDS_PLAN, {"reason": "test"})

        state = {"plan": [{"d": "s"}], "objective": "Test"}
        result = context_utils.detect_session_context(state)

        self.assertEqual(result[0], SessionContext.NEEDS_PLAN)

    @patch.object(context_utils, '_check_plan_progress')
    @patch.object(context_utils, '_check_entropy')
    @patch.object(context_utils, '_check_mismatches')
    @patch.object(context_utils, '_check_research_status')
    @patch.object(context_utils, '_check_plan_exists')
    def test_returns_potential_mismatch_on_error(self, mock_plan, mock_research, mock_mismatch, mock_entropy, mock_progress):
        """Should return POTENTIAL_MISMATCH when recent_error provided."""
        mock_plan.return_value = None
        mock_research.return_value = None
        mock_mismatch.return_value = None
        mock_entropy.return_value = None

        state = {"plan": [{"d": "s"}], "objective": "Test"}
        result = context_utils.detect_session_context(state, recent_error="Command failed")

        self.assertEqual(result[0], SessionContext.POTENTIAL_MISMATCH)
        self.assertIn("error detected", result[1]["reason"])
        mock_progress.assert_not_called()  # Should stop before progress check


class TestGetOrchestratorSuggestion(unittest.TestCase):
    """Tests for get_orchestrator_suggestion function."""

    def test_needs_plan_suggestion(self):
        """Should return correct suggestion for NEEDS_PLAN."""
        result = context_utils.get_orchestrator_suggestion(SessionContext.NEEDS_PLAN, {})
        self.assertEqual(result["command"], "/edge-plan")
        self.assertIn("plan", result["message"].lower())

    def test_needs_research_suggestion(self):
        """Should return correct suggestion for NEEDS_RESEARCH."""
        result = context_utils.get_orchestrator_suggestion(SessionContext.NEEDS_RESEARCH, {})
        self.assertEqual(result["command"], "/edge-research")

    def test_awaiting_research_suggestion(self):
        """Should return correct suggestion for AWAITING_RESEARCH."""
        result = context_utils.get_orchestrator_suggestion(SessionContext.AWAITING_RESEARCH, {})
        self.assertEqual(result["command"], "/edge-research-results")

    def test_ready_for_step_suggestion(self):
        """Should return correct suggestion for READY_FOR_STEP."""
        details = {"next_step": {"description": "Test step"}}
        result = context_utils.get_orchestrator_suggestion(SessionContext.READY_FOR_STEP, details)
        self.assertEqual(result["command"], "/edge-step")
        self.assertIn("Test step", result["message"])

    def test_step_in_progress_suggestion(self):
        """Should return correct suggestion for STEP_IN_PROGRESS."""
        details = {"step": {"description": "Current work"}}
        result = context_utils.get_orchestrator_suggestion(SessionContext.STEP_IN_PROGRESS, details)
        self.assertIsNone(result["command"])  # No command, just continue
        self.assertIn("Current work", result["message"])

    def test_potential_mismatch_suggestion(self):
        """Should return correct suggestion for POTENTIAL_MISMATCH."""
        result = context_utils.get_orchestrator_suggestion(SessionContext.POTENTIAL_MISMATCH, {})
        self.assertEqual(result["command"], "/edge-mismatch")

    def test_needs_adaptation_suggestion(self):
        """Should return correct suggestion for NEEDS_ADAPTATION."""
        result = context_utils.get_orchestrator_suggestion(SessionContext.NEEDS_ADAPTATION, {})
        self.assertEqual(result["command"], "/edge-adapt")

    def test_needs_pruning_suggestion(self):
        """Should return correct suggestion for NEEDS_PRUNING."""
        result = context_utils.get_orchestrator_suggestion(SessionContext.NEEDS_PRUNING, {})
        self.assertEqual(result["command"], "/edge-prune")

    def test_needs_scoring_suggestion(self):
        """Should return correct suggestion for NEEDS_SCORING."""
        result = context_utils.get_orchestrator_suggestion(SessionContext.NEEDS_SCORING, {})
        self.assertEqual(result["command"], "/edge-score")

    def test_all_complete_suggestion(self):
        """Should return correct suggestion for ALL_COMPLETE."""
        result = context_utils.get_orchestrator_suggestion(SessionContext.ALL_COMPLETE, {})
        self.assertIsNone(result["command"])  # No command needed
        self.assertIn("complete", result["message"].lower())

    def test_unknown_context_fallback(self):
        """Should return fallback for unknown context type."""
        result = context_utils.get_orchestrator_suggestion("unknown_type", {})
        self.assertEqual(result["command"], "/edge-plan")
        self.assertIn("unclear", result["message"].lower())


class TestEdgeCases(unittest.TestCase):
    """Tests for edge cases."""

    @patch.object(context_utils, 'get_step_by_status')
    def test_ready_for_step_with_empty_pending(self, mock_get):
        """Should handle edge case of empty pending list gracefully."""
        def mock_status(s, status):
            if status == 'pending':
                return []  # Empty but we still get here somehow
            return []
        mock_get.side_effect = mock_status
        # This tests the final fallback
        result = context_utils._check_plan_progress({})
        # With no steps at all and no score, should be NEEDS_SCORING
        self.assertEqual(result[0], SessionContext.NEEDS_SCORING)

    def test_suggestion_handles_missing_step_info(self):
        """Suggestion should handle missing step description."""
        details = {}  # No next_step or step key
        result = context_utils.get_orchestrator_suggestion(SessionContext.READY_FOR_STEP, details)
        self.assertIn("next step", result["message"])  # Fallback text


if __name__ == "__main__":
    unittest.main()
