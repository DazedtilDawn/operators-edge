#!/usr/bin/env python3
"""
Tests for verification_utils.py - subagent verification utilities.

Tests the Understanding-First v1.0 verification system:
- Policy detection
- Subagent decision logic
- Prompt building
- Result parsing
"""
import os
import sys
import unittest
from datetime import datetime

# Add hooks directory to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


class TestVerificationPolicy(unittest.TestCase):
    """Tests for verification policy functions."""

    def test_get_verification_policy_defaults(self):
        """get_verification_policy should return defaults when not set."""
        from verification_utils import get_verification_policy

        state = {"plan": []}
        policy = get_verification_policy(state)

        self.assertEqual(policy.mode, "subagent")
        self.assertFalse(policy.require_subagent)
        self.assertTrue(policy.auto_suggest)

    def test_get_verification_policy_from_state(self):
        """get_verification_policy should read from state."""
        from verification_utils import get_verification_policy

        state = {
            "verification_policy": {
                "mode": "inline",
                "require_subagent": True,
                "auto_suggest": False,
            }
        }
        policy = get_verification_policy(state)

        self.assertEqual(policy.mode, "inline")
        self.assertTrue(policy.require_subagent)
        self.assertFalse(policy.auto_suggest)


class TestShouldUseSubagent(unittest.TestCase):
    """Tests for should_use_subagent_verification function."""

    def test_returns_false_for_non_verification_step(self):
        """should_use_subagent_verification returns False for regular steps."""
        from verification_utils import should_use_subagent_verification

        step = {"description": "Regular step", "status": "pending"}
        state = {}

        self.assertFalse(should_use_subagent_verification(step, state))

    def test_returns_true_for_verification_step_subagent_mode(self):
        """should_use_subagent_verification returns True in subagent mode."""
        from verification_utils import should_use_subagent_verification

        step = {"description": "Verify", "is_verification": True}
        state = {"verification_policy": {"mode": "subagent"}}

        self.assertTrue(should_use_subagent_verification(step, state))

    def test_returns_false_for_verification_step_inline_mode(self):
        """should_use_subagent_verification returns False in inline mode."""
        from verification_utils import should_use_subagent_verification

        step = {"description": "Verify", "is_verification": True}
        state = {"verification_policy": {"mode": "inline"}}

        self.assertFalse(should_use_subagent_verification(step, state))

    def test_hybrid_mode_with_auto_suggest(self):
        """should_use_subagent_verification in hybrid mode with auto_suggest."""
        from verification_utils import should_use_subagent_verification

        step = {"description": "Verify", "is_verification": True}
        state = {
            "verification_policy": {
                "mode": "hybrid",
                "auto_suggest": True,
            }
        }

        self.assertTrue(should_use_subagent_verification(step, state))

    def test_hybrid_mode_without_auto_suggest(self):
        """should_use_subagent_verification in hybrid mode without auto_suggest."""
        from verification_utils import should_use_subagent_verification

        step = {"description": "Verify", "is_verification": True}
        state = {
            "verification_policy": {
                "mode": "hybrid",
                "auto_suggest": False,
            }
        }

        self.assertFalse(should_use_subagent_verification(step, state))


class TestBuildVerificationPrompt(unittest.TestCase):
    """Tests for build_verification_prompt function."""

    def test_includes_objective(self):
        """build_verification_prompt includes objective."""
        from verification_utils import build_verification_prompt

        state = {
            "objective": "Add user authentication",
            "intent": {"user_wants": "Auth system"},
            "plan": []
        }
        prompt = build_verification_prompt(state)

        self.assertIn("Add user authentication", prompt)

    def test_includes_intent(self):
        """build_verification_prompt includes user_wants and success_looks_like."""
        from verification_utils import build_verification_prompt

        state = {
            "objective": "Test",
            "intent": {
                "user_wants": "Add login feature",
                "success_looks_like": "Users can log in",
            },
            "plan": []
        }
        prompt = build_verification_prompt(state)

        self.assertIn("Add login feature", prompt)
        self.assertIn("Users can log in", prompt)

    def test_includes_completed_step_proofs(self):
        """build_verification_prompt includes proof from completed steps."""
        from verification_utils import build_verification_prompt

        state = {
            "objective": "Test",
            "intent": {"user_wants": "Test"},
            "plan": [
                {"description": "Step 1", "status": "completed", "proof": "Done step 1"},
                {"description": "Step 2", "status": "completed", "proof": "Done step 2"},
                {"description": "Verify", "status": "pending", "is_verification": True},
            ]
        }
        prompt = build_verification_prompt(state)

        self.assertIn("Step 1", prompt)
        self.assertIn("Done step 1", prompt)
        self.assertIn("Step 2", prompt)
        self.assertIn("Done step 2", prompt)

    def test_excludes_verification_steps_from_proof(self):
        """build_verification_prompt excludes verification steps from proof summary."""
        from verification_utils import build_verification_prompt

        state = {
            "objective": "Test",
            "intent": {"user_wants": "Test"},
            "plan": [
                {"description": "Implement", "status": "completed", "proof": "Implemented"},
                {"description": "Verify step", "status": "completed", "proof": "Verified", "is_verification": True},
            ]
        }
        prompt = build_verification_prompt(state)

        # Implementation proof should be there
        self.assertIn("Implement", prompt)
        self.assertIn("Implemented", prompt)

        # The verification step proof should NOT be in the "Work completed" section
        # (it's a meta-task about verification, not about work)
        lines = prompt.split("\n")
        work_section = False
        verification_step_in_work = False
        for line in lines:
            if "Work completed" in line:
                work_section = True
            if work_section and "Verify step" in line:
                verification_step_in_work = True
                break
            if work_section and "---" in line:
                break

        self.assertFalse(verification_step_in_work)

    def test_includes_verification_instructions(self):
        """build_verification_prompt includes instructions for verifier."""
        from verification_utils import build_verification_prompt

        state = {
            "objective": "Test",
            "intent": {"user_wants": "Test"},
            "plan": []
        }
        prompt = build_verification_prompt(state)

        self.assertIn("Do NOT trust the proof summaries", prompt)
        self.assertIn("PASS", prompt)
        self.assertIn("FAIL", prompt)
        self.assertIn("independently verify", prompt.lower())


class TestBuildVerificationContext(unittest.TestCase):
    """Tests for build_verification_context function."""

    def test_includes_objective(self):
        """build_verification_context includes objective."""
        from verification_utils import build_verification_context

        state = {"objective": "My objective", "intent": {}, "plan": []}
        context = build_verification_context(state)

        self.assertEqual(context["objective"], "My objective")

    def test_includes_intent(self):
        """build_verification_context includes intent fields."""
        from verification_utils import build_verification_context

        state = {
            "objective": "Test",
            "intent": {
                "user_wants": "Add feature",
                "success_looks_like": "Feature works",
            },
            "plan": []
        }
        context = build_verification_context(state)

        self.assertEqual(context["intent"]["user_wants"], "Add feature")
        self.assertEqual(context["intent"]["success_looks_like"], "Feature works")

    def test_includes_completed_steps(self):
        """build_verification_context includes completed steps."""
        from verification_utils import build_verification_context

        state = {
            "objective": "Test",
            "intent": {},
            "plan": [
                {"description": "Step 1", "status": "completed", "proof": "Done"},
                {"description": "Step 2", "status": "pending"},
            ]
        }
        context = build_verification_context(state)

        self.assertEqual(len(context["completed_steps"]), 1)
        self.assertEqual(context["completed_steps"][0]["description"], "Step 1")


class TestParseVerificationResult(unittest.TestCase):
    """Tests for parse_verification_result function."""

    def test_detects_pass(self):
        """parse_verification_result detects PASS result."""
        from verification_utils import parse_verification_result

        output = """
## Verification Result: PASS

### Criteria Checked
1. Tests pass: PASS - All 10 tests green
2. Feature works: PASS - Verified manually
"""
        result = parse_verification_result(output)

        self.assertTrue(result["passed"])

    def test_detects_fail(self):
        """parse_verification_result detects FAIL result."""
        from verification_utils import parse_verification_result

        output = """
## Verification Result: FAIL

### Criteria Checked
1. Tests pass: FAIL - 2 tests failing

### Issues Found
- Test test_auth fails with assertion error
- Missing validation in login form
"""
        result = parse_verification_result(output)

        self.assertFalse(result["passed"])

    def test_extracts_issues(self):
        """parse_verification_result extracts issues list."""
        from verification_utils import parse_verification_result

        output = """
## Verification Result: FAIL

### Issues Found
- First issue here
- Second issue here
- Third issue
"""
        result = parse_verification_result(output)

        self.assertEqual(len(result["issues"]), 3)
        self.assertIn("First issue here", result["issues"])

    def test_preserves_raw_output(self):
        """parse_verification_result preserves raw output."""
        from verification_utils import parse_verification_result

        output = "Some verification output"
        result = parse_verification_result(output)

        self.assertEqual(result["raw_output"], output)

    def test_handles_ambiguous_result(self):
        """parse_verification_result handles ambiguous output."""
        from verification_utils import parse_verification_result

        output = "All checks completed successfully."
        result = parse_verification_result(output)

        # Ambiguous - no explicit PASS/FAIL, no : PASS/: FAIL markers
        self.assertFalse(result["passed"])  # Conservative default


class TestGetVerificationStep(unittest.TestCase):
    """Tests for get_verification_step function."""

    def test_returns_verification_step(self):
        """get_verification_step returns the verification step."""
        from verification_utils import get_verification_step

        state = {
            "plan": [
                {"description": "Step 1", "status": "completed"},
                {"description": "Verify", "status": "pending", "is_verification": True},
            ]
        }

        step = get_verification_step(state)
        self.assertIsNotNone(step)
        self.assertEqual(step["description"], "Verify")

    def test_returns_none_when_no_verification_step(self):
        """get_verification_step returns None when no verification step."""
        from verification_utils import get_verification_step

        state = {
            "plan": [
                {"description": "Step 1", "status": "completed"},
                {"description": "Step 2", "status": "pending"},
            ]
        }

        step = get_verification_step(state)
        self.assertIsNone(step)

    def test_returns_first_verification_step(self):
        """get_verification_step returns first verification step if multiple."""
        from verification_utils import get_verification_step

        state = {
            "plan": [
                {"description": "Verify A", "is_verification": True},
                {"description": "Verify B", "is_verification": True},
            ]
        }

        step = get_verification_step(state)
        self.assertEqual(step["description"], "Verify A")


class TestSuggestVerificationApproach(unittest.TestCase):
    """Tests for suggest_verification_approach function."""

    def test_suggests_adding_step_when_missing(self):
        """suggest_verification_approach suggests adding step when missing."""
        from verification_utils import suggest_verification_approach

        state = {"plan": [{"description": "Step 1"}]}
        suggestion = suggest_verification_approach(state)

        self.assertIn("No verification step", suggestion)
        self.assertIn("is_verification: true", suggestion)

    def test_reports_completed_when_done(self):
        """suggest_verification_approach reports when already completed."""
        from verification_utils import suggest_verification_approach

        state = {
            "plan": [
                {"description": "Verify", "status": "completed", "is_verification": True},
            ]
        }
        suggestion = suggest_verification_approach(state)

        self.assertIn("already completed", suggestion)

    def test_suggests_subagent_in_subagent_mode(self):
        """suggest_verification_approach suggests subagent in subagent mode."""
        from verification_utils import suggest_verification_approach

        state = {
            "plan": [
                {"description": "Verify", "status": "pending", "is_verification": True},
            ],
            "verification_policy": {"mode": "subagent"}
        }
        suggestion = suggest_verification_approach(state)

        self.assertIn("Task tool", suggestion)
        self.assertIn("edge-reviewer", suggestion)


# =============================================================================
# TESTS FOR V1.1 FEATURES
# =============================================================================

class TestVerificationObservations(unittest.TestCase):
    """Tests for v1.1 verification observation logging."""

    def setUp(self):
        """Clear observations before each test."""
        from verification_utils import clear_verification_observations
        clear_verification_observations()

    def tearDown(self):
        """Clear observations after each test."""
        from verification_utils import clear_verification_observations
        clear_verification_observations()

    def test_log_verification_observation(self):
        """log_verification_observation creates observation record."""
        from verification_utils import log_verification_observation, load_verification_observations

        obs = log_verification_observation("edge-reviewer", {"prompt": "test prompt"})

        self.assertEqual(obs["subagent_type"], "edge-reviewer")
        self.assertTrue(obs["is_verification_subagent"])
        self.assertFalse(obs["is_delegated"])

        loaded = load_verification_observations()
        self.assertEqual(len(loaded), 1)

    def test_verification_method_subagent(self):
        """get_verification_method returns 'subagent' for edge-reviewer."""
        from verification_utils import (
            log_verification_observation,
            get_verification_method,
        )

        log_verification_observation("edge-reviewer", {})
        method = get_verification_method()

        self.assertEqual(method, "subagent")

    def test_verification_method_inline(self):
        """get_verification_method returns 'inline' for non-verification subagent."""
        from verification_utils import (
            log_verification_observation,
            get_verification_method,
        )

        log_verification_observation("Explore", {})
        method = get_verification_method()

        self.assertEqual(method, "inline")

    def test_verification_method_self(self):
        """get_verification_method returns 'self' when no observations."""
        from verification_utils import get_verification_method

        method = get_verification_method()
        self.assertEqual(method, "self")


class TestStructuredCriteria(unittest.TestCase):
    """Tests for v1.1 structured success criteria evaluation."""

    def test_evaluate_file_exists_pass(self):
        """evaluate_criterion passes for existing file."""
        from verification_utils import evaluate_criterion

        criterion = {"type": "file_exists", "path": __file__}  # This test file exists
        result = evaluate_criterion(criterion)

        self.assertTrue(result.passed)
        self.assertIn("Found", result.output)

    def test_evaluate_file_exists_fail(self):
        """evaluate_criterion fails for non-existing file."""
        from verification_utils import evaluate_criterion

        criterion = {"type": "file_exists", "path": "/nonexistent/file.py"}
        result = evaluate_criterion(criterion)

        self.assertFalse(result.passed)
        self.assertIn("Not found", result.output)

    def test_evaluate_command_succeeds_pass(self):
        """evaluate_criterion passes for successful command."""
        from verification_utils import evaluate_criterion

        criterion = {"type": "command_succeeds", "command": "echo hello"}
        result = evaluate_criterion(criterion)

        self.assertTrue(result.passed)
        self.assertIn("hello", result.output)

    def test_evaluate_command_succeeds_fail(self):
        """evaluate_criterion fails for failing command."""
        from verification_utils import evaluate_criterion

        criterion = {"type": "command_succeeds", "command": "exit 1"}
        result = evaluate_criterion(criterion)

        self.assertFalse(result.passed)
        self.assertIsNotNone(result.error)

    def test_evaluate_manual_returns_none(self):
        """evaluate_criterion returns passed=None for manual criteria."""
        from verification_utils import evaluate_criterion

        criterion = {"type": "manual", "description": "Check UI looks good"}
        result = evaluate_criterion(criterion)

        self.assertIsNone(result.passed)
        self.assertIn("human verification", result.output)

    def test_evaluate_structured_criteria_integration(self):
        """evaluate_structured_criteria processes all criteria types."""
        from verification_utils import evaluate_structured_criteria

        state = {
            "intent": {
                "success_criteria": [
                    {"type": "file_exists", "path": __file__},
                    {"type": "command_succeeds", "command": "echo test"},
                    {"type": "manual", "description": "Looks good"},
                ]
            }
        }

        results = evaluate_structured_criteria(state)

        self.assertEqual(len(results), 3)
        self.assertTrue(results[0].passed)  # file exists
        self.assertTrue(results[1].passed)  # command succeeds
        self.assertIsNone(results[2].passed)  # manual

    def test_format_criteria_results(self):
        """format_criteria_results produces readable output."""
        from verification_utils import evaluate_structured_criteria, format_criteria_results

        state = {
            "intent": {
                "success_criteria": [
                    {"type": "file_exists", "path": __file__},
                    {"type": "manual", "description": "Check UI"},
                ]
            }
        }

        results = evaluate_structured_criteria(state)
        output = format_criteria_results(results)

        self.assertIn("PASS", output)
        self.assertIn("MANUAL", output)
        self.assertIn("Summary", output)


class TestVerificationMismatch(unittest.TestCase):
    """Tests for v1.1 verification mismatch creation."""

    def test_create_verification_mismatch(self):
        """create_verification_mismatch builds correct mismatch dict."""
        from verification_utils import create_verification_mismatch

        result = {"passed": False, "issues": ["Test failed: expected X, got Y"]}
        intent = {"success_looks_like": "All tests pass", "user_wants": "Add feature"}

        mismatch = create_verification_mismatch(result, intent)

        self.assertIn("id", mismatch)
        self.assertEqual(mismatch["source"], "verification_failure")
        self.assertTrue(mismatch["intent_link"])
        self.assertFalse(mismatch["resolved"])
        self.assertEqual(mismatch["expectation"], "All tests pass")
        self.assertIn("Test failed", mismatch["observation"])

    def test_should_create_verification_mismatch_true(self):
        """should_create_verification_mismatch returns True for failed verification."""
        from verification_utils import should_create_verification_mismatch

        result = {"passed": False}
        self.assertTrue(should_create_verification_mismatch(result))

    def test_should_create_verification_mismatch_false(self):
        """should_create_verification_mismatch returns False for passed verification."""
        from verification_utils import should_create_verification_mismatch

        result = {"passed": True}
        self.assertFalse(should_create_verification_mismatch(result))

    def test_handle_verification_result_pass(self):
        """handle_verification_result does not create mismatch on pass."""
        from verification_utils import handle_verification_result

        raw_output = "## Verification Result: PASS\n\nAll tests passed."
        state = {"intent": {"success_looks_like": "All tests pass"}}

        response = handle_verification_result(raw_output, state, auto_create_mismatch=False)

        self.assertTrue(response["result"]["passed"])
        self.assertIsNone(response["mismatch"])

    def test_handle_verification_result_fail_creates_mismatch(self):
        """handle_verification_result creates mismatch on failure."""
        from verification_utils import handle_verification_result

        raw_output = "## Verification Result: FAIL\n\n### Issues Found\n- Test failed"
        state = {"intent": {"success_looks_like": "All tests pass"}}

        # Use auto_create_mismatch=False to avoid file write in test
        response = handle_verification_result(raw_output, state, auto_create_mismatch=False)

        self.assertFalse(response["result"]["passed"])
        # Mismatch is None because auto_create_mismatch=False


if __name__ == '__main__':
    unittest.main()
