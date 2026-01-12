#!/usr/bin/env python3
"""
Tests for quality_gate.py - objective completion quality checks.

Tests the quality gate that runs before ACTIVE→PATROL transition:
- Steps have proof check
- No dangling in_progress check
- Verifications tested check
- No unresolved mismatches check
"""
import os
import sys
import tempfile
import unittest
from pathlib import Path

# Add hooks directory to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


# =============================================================================
# TEST: check_steps_have_proof
# =============================================================================

class TestCheckStepsHaveProof(unittest.TestCase):
    """Tests for check_steps_have_proof() function."""

    def test_passes_with_empty_plan(self):
        """Should pass when plan is empty."""
        from quality_gate import check_steps_have_proof
        result = check_steps_have_proof({"plan": []})
        self.assertTrue(result.passed)

    def test_passes_with_no_plan(self):
        """Should pass when plan key is missing."""
        from quality_gate import check_steps_have_proof
        result = check_steps_have_proof({})
        self.assertTrue(result.passed)

    def test_passes_when_all_completed_have_proof(self):
        """Should pass when all completed steps have proof."""
        from quality_gate import check_steps_have_proof
        state = {
            "plan": [
                {"description": "Step 1", "status": "completed", "proof": "Done"},
                {"description": "Step 2", "status": "completed", "proof": "Verified"},
                {"description": "Step 3", "status": "pending", "proof": None},
            ]
        }
        result = check_steps_have_proof(state)
        self.assertTrue(result.passed)
        self.assertIn("2 completed steps have proof", result.message)

    def test_fails_when_completed_missing_proof(self):
        """Should fail when completed step has no proof."""
        from quality_gate import check_steps_have_proof
        state = {
            "plan": [
                {"description": "Step 1", "status": "completed", "proof": "Done"},
                {"description": "Step 2", "status": "completed", "proof": None},
            ]
        }
        result = check_steps_have_proof(state)
        self.assertFalse(result.passed)
        self.assertEqual(result.severity, "error")
        self.assertIn("1 completed step(s) missing proof", result.message)

    def test_fails_when_proof_is_empty_string(self):
        """Should fail when proof is empty string."""
        from quality_gate import check_steps_have_proof
        state = {
            "plan": [
                {"description": "Step 1", "status": "completed", "proof": ""},
            ]
        }
        result = check_steps_have_proof(state)
        self.assertFalse(result.passed)

    def test_fails_when_proof_is_null_string(self):
        """Should fail when proof is literal 'null' string."""
        from quality_gate import check_steps_have_proof
        state = {
            "plan": [
                {"description": "Step 1", "status": "completed", "proof": "null"},
            ]
        }
        result = check_steps_have_proof(state)
        self.assertFalse(result.passed)

    def test_ignores_pending_steps(self):
        """Should not check proof for pending steps."""
        from quality_gate import check_steps_have_proof
        state = {
            "plan": [
                {"description": "Step 1", "status": "pending", "proof": None},
            ]
        }
        result = check_steps_have_proof(state)
        self.assertTrue(result.passed)

    def test_details_list_missing_steps(self):
        """Should list steps missing proof in details."""
        from quality_gate import check_steps_have_proof
        state = {
            "plan": [
                {"description": "First step here", "status": "completed", "proof": None},
                {"description": "Second step", "status": "completed", "proof": "Done"},
                {"description": "Third step missing", "status": "completed", "proof": ""},
            ]
        }
        result = check_steps_have_proof(state)
        self.assertFalse(result.passed)
        self.assertEqual(len(result.details), 2)
        self.assertIn("Step 1", result.details[0])
        self.assertIn("Step 3", result.details[1])


# =============================================================================
# TEST: check_no_dangling_in_progress
# =============================================================================

class TestCheckNoDanglingInProgress(unittest.TestCase):
    """Tests for check_no_dangling_in_progress() function."""

    def test_passes_with_empty_plan(self):
        """Should pass when plan is empty."""
        from quality_gate import check_no_dangling_in_progress
        result = check_no_dangling_in_progress({"plan": []})
        self.assertTrue(result.passed)

    def test_passes_when_no_in_progress(self):
        """Should pass when no steps are in_progress."""
        from quality_gate import check_no_dangling_in_progress
        state = {
            "plan": [
                {"description": "Step 1", "status": "completed"},
                {"description": "Step 2", "status": "pending"},
            ]
        }
        result = check_no_dangling_in_progress(state)
        self.assertTrue(result.passed)

    def test_fails_when_step_in_progress(self):
        """Should fail when a step is still in_progress."""
        from quality_gate import check_no_dangling_in_progress
        state = {
            "plan": [
                {"description": "Step 1", "status": "completed"},
                {"description": "Step 2", "status": "in_progress"},
            ]
        }
        result = check_no_dangling_in_progress(state)
        self.assertFalse(result.passed)
        self.assertEqual(result.severity, "error")
        self.assertIn("1 step(s) still in_progress", result.message)

    def test_details_list_in_progress_steps(self):
        """Should list in_progress steps in details."""
        from quality_gate import check_no_dangling_in_progress
        state = {
            "plan": [
                {"description": "First in progress", "status": "in_progress"},
                {"description": "Completed", "status": "completed"},
                {"description": "Second in progress", "status": "in_progress"},
            ]
        }
        result = check_no_dangling_in_progress(state)
        self.assertFalse(result.passed)
        self.assertEqual(len(result.details), 2)


# =============================================================================
# TEST: check_verifications_tested
# =============================================================================

class TestCheckVerificationsTested(unittest.TestCase):
    """Tests for check_verifications_tested() function."""

    def test_passes_with_empty_plan(self):
        """Should pass when plan is empty."""
        from quality_gate import check_verifications_tested
        result = check_verifications_tested({"plan": []})
        self.assertTrue(result.passed)

    def test_passes_when_no_verifications(self):
        """Should pass when no steps have verification field."""
        from quality_gate import check_verifications_tested
        state = {
            "plan": [
                {"description": "Step 1", "status": "completed", "proof": "Done"},
            ]
        }
        result = check_verifications_tested(state)
        self.assertTrue(result.passed)
        self.assertIn("No steps with verification", result.message)

    def test_fails_when_verification_not_in_tests(self):
        """Should fail when verification keywords not found in tests."""
        from quality_gate import check_verifications_tested
        state = {
            "plan": [
                {
                    "description": "Add auth",
                    "status": "completed",
                    "verification": "POST /login returns token with valid credentials"
                }
            ]
        }
        # No test files provided
        with tempfile.TemporaryDirectory() as tmpdir:
            result = check_verifications_tested(state, Path(tmpdir))
            self.assertFalse(result.passed)
            self.assertEqual(result.severity, "warning")

    def test_passes_when_verification_found_in_tests(self):
        """Should pass when verification keywords found in test files."""
        from quality_gate import check_verifications_tested

        with tempfile.TemporaryDirectory() as tmpdir:
            # Create a test file with matching content
            test_file = Path(tmpdir) / "test_auth.py"
            test_file.write_text("""
def test_login_returns_token():
    response = client.post('/login', json={'credentials': 'valid'})
    assert 'token' in response.json()
""")
            state = {
                "plan": [
                    {
                        "description": "Add auth",
                        "status": "completed",
                        "verification": "POST /login returns token with valid credentials"
                    }
                ]
            }
            result = check_verifications_tested(state, Path(tmpdir))
            self.assertTrue(result.passed)

    def test_is_warning_not_error(self):
        """Verification check should be warning severity, not error."""
        from quality_gate import check_verifications_tested
        state = {
            "plan": [
                {
                    "description": "Add feature",
                    "status": "completed",
                    "verification": "Something unique happens"
                }
            ]
        }
        with tempfile.TemporaryDirectory() as tmpdir:
            result = check_verifications_tested(state, Path(tmpdir))
            self.assertEqual(result.severity, "warning")


# =============================================================================
# TEST: check_no_unresolved_mismatches
# =============================================================================

class TestCheckNoUnresolvedMismatches(unittest.TestCase):
    """Tests for check_no_unresolved_mismatches() function."""

    def test_passes_with_no_mismatches(self):
        """Should pass when mismatches array is empty."""
        from quality_gate import check_no_unresolved_mismatches
        result = check_no_unresolved_mismatches({"mismatches": []})
        self.assertTrue(result.passed)

    def test_passes_with_missing_mismatches_key(self):
        """Should pass when mismatches key is missing."""
        from quality_gate import check_no_unresolved_mismatches
        result = check_no_unresolved_mismatches({})
        self.assertTrue(result.passed)

    def test_passes_when_all_resolved(self):
        """Should pass when all mismatches are resolved."""
        from quality_gate import check_no_unresolved_mismatches
        state = {
            "mismatches": [
                {"expected": "X", "actual": "Y", "status": "resolved"},
                {"expected": "A", "actual": "B", "status": "resolved"},
            ]
        }
        result = check_no_unresolved_mismatches(state)
        self.assertTrue(result.passed)
        self.assertIn("2 mismatches resolved", result.message)

    def test_fails_when_unresolved(self):
        """Should fail when mismatch is not resolved."""
        from quality_gate import check_no_unresolved_mismatches
        state = {
            "mismatches": [
                {"expected": "Tests pass", "actual": "Tests fail", "status": "unresolved"},
            ]
        }
        result = check_no_unresolved_mismatches(state)
        self.assertFalse(result.passed)
        self.assertEqual(result.severity, "error")

    def test_fails_when_status_missing(self):
        """Should fail when mismatch has no status (assumed unresolved)."""
        from quality_gate import check_no_unresolved_mismatches
        state = {
            "mismatches": [
                {"expected": "X", "actual": "Y"},  # No status
            ]
        }
        result = check_no_unresolved_mismatches(state)
        self.assertFalse(result.passed)


# =============================================================================
# TEST: run_quality_gate
# =============================================================================

class TestRunQualityGate(unittest.TestCase):
    """Tests for run_quality_gate() main function."""

    def test_passes_with_clean_state(self):
        """Should pass with a well-formed completed objective."""
        from quality_gate import run_quality_gate

        state = {
            "plan": [
                {"description": "Step 1", "status": "completed", "proof": "Done"},
                {"description": "Step 2", "status": "completed", "proof": "Verified"},
            ],
            "mismatches": [],
        }
        result = run_quality_gate(state)
        self.assertTrue(result.passed)
        self.assertIn("PASSED", result.summary)

    def test_fails_with_missing_proof(self):
        """Should fail when completed steps lack proof."""
        from quality_gate import run_quality_gate

        state = {
            "plan": [
                {"description": "Step 1", "status": "completed", "proof": None},
            ]
        }
        result = run_quality_gate(state)
        self.assertFalse(result.passed)
        self.assertEqual(len(result.failed_checks), 1)
        self.assertEqual(result.failed_checks[0].name, "steps_have_proof")

    def test_fails_with_dangling_in_progress(self):
        """Should fail when steps are stuck in_progress."""
        from quality_gate import run_quality_gate

        state = {
            "plan": [
                {"description": "Step 1", "status": "in_progress"},
            ]
        }
        result = run_quality_gate(state)
        self.assertFalse(result.passed)

    def test_warnings_dont_block(self):
        """Warnings should not cause gate to fail."""
        from quality_gate import run_quality_gate

        with tempfile.TemporaryDirectory() as tmpdir:
            state = {
                "plan": [
                    {
                        "description": "Step 1",
                        "status": "completed",
                        "proof": "Done",
                        "verification": "Something unique untested"
                    }
                ]
            }
            result = run_quality_gate(state, Path(tmpdir))
            # Should pass (warnings don't block)
            self.assertTrue(result.passed)
            self.assertEqual(len(result.warning_checks), 1)

    def test_multiple_failures(self):
        """Should report all failures, not just first."""
        from quality_gate import run_quality_gate

        state = {
            "plan": [
                {"description": "Step 1", "status": "completed", "proof": None},
                {"description": "Step 2", "status": "in_progress"},
            ],
            "mismatches": [
                {"expected": "X", "actual": "Y", "status": "unresolved"},
            ]
        }
        result = run_quality_gate(state)
        self.assertFalse(result.passed)
        # Should have at least 3 failed checks (eval gate may add warning)
        self.assertGreaterEqual(len(result.failed_checks), 3)


# =============================================================================
# TEST: Display Helpers
# =============================================================================

class TestDisplayHelpers(unittest.TestCase):
    """Tests for display formatting functions."""

    def test_format_quality_gate_result_shows_all_checks(self):
        """Should include all checks in output."""
        from quality_gate import run_quality_gate, format_quality_gate_result

        state = {
            "plan": [
                {"description": "Step 1", "status": "completed", "proof": "Done"},
            ]
        }
        result = run_quality_gate(state)
        output = format_quality_gate_result(result)

        self.assertIn("steps_have_proof", output)
        self.assertIn("no_dangling_in_progress", output)
        self.assertIn("QUALITY GATE", output)

    def test_format_quality_junction_shows_failures(self):
        """Should show failed checks in junction message."""
        from quality_gate import run_quality_gate, format_quality_junction

        state = {
            "plan": [
                {"description": "Missing proof step", "status": "completed", "proof": None},
            ]
        }
        result = run_quality_gate(state)
        output = format_quality_junction(result)

        self.assertIn("JUNCTION", output)
        self.assertIn("quality_gate", output)
        self.assertIn("steps_have_proof", output)
        self.assertIn("Options", output)


if __name__ == '__main__':
    unittest.main()
