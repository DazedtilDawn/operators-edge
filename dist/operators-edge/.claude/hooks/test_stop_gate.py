#!/usr/bin/env python3
"""
Tests for stop_gate.py - the session end enforcement hook.

Tests the core validation functions that determine whether a session
can end (state modified, proof exists) and warning checks (in_progress
steps, mismatches, entropy).
"""
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch, MagicMock

# Add hooks directory to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


class TestCheckStateModified(unittest.TestCase):
    """Tests for check_state_modified() function."""

    @patch('stop_gate.get_start_hash')
    @patch('stop_gate.get_project_dir')
    @patch('stop_gate.file_hash')
    def test_state_modified_returns_true(self, mock_file_hash, mock_project_dir, mock_start_hash):
        """When state file hash differs from start, return True."""
        from stop_gate import check_state_modified

        mock_start_hash.return_value = "hash_at_start"
        mock_project_dir.return_value = Path(tempfile.gettempdir())
        mock_file_hash.return_value = "different_hash"

        # Create temp file so exists() check passes
        temp_yaml = Path(tempfile.gettempdir()) / "active_context.yaml"
        temp_yaml.write_text("test: data")

        try:
            passed, msg = check_state_modified()
            self.assertTrue(passed)
            self.assertIn("modified", msg.lower())
        finally:
            temp_yaml.unlink()

    @patch('stop_gate.get_start_hash')
    @patch('stop_gate.get_project_dir')
    @patch('stop_gate.file_hash')
    def test_state_not_modified_returns_false(self, mock_file_hash, mock_project_dir, mock_start_hash):
        """When state file hash matches start hash, return False (blocking)."""
        from stop_gate import check_state_modified

        mock_start_hash.return_value = "same_hash"
        mock_project_dir.return_value = Path(tempfile.gettempdir())
        mock_file_hash.return_value = "same_hash"

        temp_yaml = Path(tempfile.gettempdir()) / "active_context.yaml"
        temp_yaml.write_text("test: data")

        try:
            passed, msg = check_state_modified()
            self.assertFalse(passed)
            self.assertIn("NOT modified", msg)
        finally:
            temp_yaml.unlink()

    @patch('stop_gate.get_start_hash')
    def test_no_start_hash_allows_with_warning(self, mock_start_hash):
        """When no start hash exists, allow with warning."""
        from stop_gate import check_state_modified

        mock_start_hash.return_value = None

        passed, msg = check_state_modified()
        self.assertTrue(passed)
        self.assertIn("No session start hash", msg)


class TestCheckProofExists(unittest.TestCase):
    """Tests for check_proof_exists() function."""

    @patch('stop_gate.check_proof_for_session')
    def test_proof_exists_with_entries(self, mock_check):
        """When proof log has entries, return True."""
        from stop_gate import check_proof_exists

        mock_check.return_value = (True, "Proof log has 5 entries", 5)

        passed, msg = check_proof_exists()
        self.assertTrue(passed)
        self.assertIn("5 entries", msg)

    @patch('stop_gate.graceful_fallback')
    @patch('stop_gate.recover_proof_from_state')
    @patch('stop_gate.check_proof_for_session')
    def test_no_proof_file_with_recovery(self, mock_check, mock_recover, mock_fallback):
        """When proof log missing but state changed, recovery creates proof."""
        from stop_gate import check_proof_exists

        mock_check.return_value = (False, "No proof log", 0)
        mock_recover.return_value = (True, "Proof recovered from state modification")

        passed, msg = check_proof_exists()
        self.assertTrue(passed)
        self.assertIn("recovered", msg.lower())

    @patch('stop_gate.graceful_fallback')
    @patch('stop_gate.recover_proof_from_state')
    @patch('stop_gate.check_proof_for_session')
    def test_no_proof_graceful_fallback(self, mock_check, mock_recover, mock_fallback):
        """When proof missing and recovery fails, graceful fallback allows exit."""
        from stop_gate import check_proof_exists

        mock_check.return_value = (False, "No proof log", 0)
        mock_recover.return_value = (False, "No state change")
        mock_fallback.return_value = (True, "WARNING: No session tracking")

        passed, msg = check_proof_exists()
        self.assertTrue(passed)  # Graceful fallback allows exit
        self.assertIn("WARNING", msg)

    @patch('stop_gate.graceful_fallback')
    @patch('stop_gate.recover_proof_from_state')
    @patch('stop_gate.check_proof_for_session')
    def test_truly_empty_session_blocks(self, mock_check, mock_recover, mock_fallback):
        """When truly nothing happened, block exit."""
        from stop_gate import check_proof_exists

        mock_check.return_value = (False, "No proof log", 0)
        mock_recover.return_value = (False, "No state change")
        mock_fallback.return_value = (False, "No evidence of work")

        passed, msg = check_proof_exists()
        self.assertFalse(passed)  # Block when truly empty


class TestCheckNoInProgressSteps(unittest.TestCase):
    """Tests for check_no_in_progress_steps() function."""

    @patch('stop_gate.load_yaml_state')
    def test_no_in_progress_returns_ok(self, mock_load):
        """When no steps are in_progress, return ok message."""
        from stop_gate import check_no_in_progress_steps

        mock_load.return_value = {
            'plan': [
                {'description': 'Step 1', 'status': 'completed'},
                {'description': 'Step 2', 'status': 'pending'}
            ]
        }

        passed, msg = check_no_in_progress_steps()
        self.assertTrue(passed)
        self.assertIn("No steps left in_progress", msg)

    @patch('stop_gate.load_yaml_state')
    def test_in_progress_steps_returns_warning(self, mock_load):
        """When steps are in_progress, return warning (but still True)."""
        from stop_gate import check_no_in_progress_steps

        mock_load.return_value = {
            'plan': [
                {'description': 'Step 1', 'status': 'completed'},
                {'description': 'Step 2', 'status': 'in_progress'},
                {'description': 'Step 3', 'status': 'in_progress'}
            ]
        }

        passed, msg = check_no_in_progress_steps()
        self.assertTrue(passed)  # Warning, not blocking
        self.assertIn("in_progress", msg)
        self.assertIn("[2, 3]", msg)


class TestCheckUnresolvedMismatches(unittest.TestCase):
    """Tests for check_unresolved_mismatches() function."""

    @patch('stop_gate.load_yaml_state')
    @patch('stop_gate.get_unresolved_mismatches')
    def test_no_mismatches_returns_ok(self, mock_get_unresolved, mock_load):
        """When no unresolved mismatches, return ok."""
        from stop_gate import check_unresolved_mismatches

        mock_load.return_value = {'mismatches': []}
        mock_get_unresolved.return_value = []

        passed, msg = check_unresolved_mismatches()
        self.assertTrue(passed)
        self.assertIn("No unresolved", msg)

    @patch('stop_gate.load_yaml_state')
    @patch('stop_gate.get_unresolved_mismatches')
    def test_unresolved_mismatches_returns_warning(self, mock_get_unresolved, mock_load):
        """When unresolved mismatches exist, return warning."""
        from stop_gate import check_unresolved_mismatches

        mock_load.return_value = {'mismatches': [{'status': 'unresolved'}]}
        mock_get_unresolved.return_value = [{'status': 'unresolved'}]

        passed, msg = check_unresolved_mismatches()
        self.assertTrue(passed)  # Warning, not blocking
        self.assertIn("1 unresolved", msg)


class TestCheckEntropy(unittest.TestCase):
    """Tests for check_entropy() function."""

    @patch('stop_gate.load_yaml_state')
    @patch('stop_gate.check_state_entropy')
    def test_low_entropy_returns_ok(self, mock_check_entropy, mock_load):
        """When entropy is low, return ok."""
        from stop_gate import check_entropy

        mock_load.return_value = {'plan': []}
        mock_check_entropy.return_value = (False, [])

        passed, msg = check_entropy()
        self.assertTrue(passed)
        self.assertIn("OK", msg)

    @patch('stop_gate.load_yaml_state')
    @patch('stop_gate.check_state_entropy')
    def test_high_entropy_returns_warning(self, mock_check_entropy, mock_load):
        """When entropy is high, return warning."""
        from stop_gate import check_entropy

        mock_load.return_value = {'plan': [{'status': 'completed'}] * 10}
        mock_check_entropy.return_value = (True, ["10 completed steps"])

        passed, msg = check_entropy()
        self.assertTrue(passed)  # Warning, not blocking
        self.assertIn("entropy", msg.lower())


class TestRespond(unittest.TestCase):
    """Tests for respond() helper function."""

    def test_respond_outputs_json(self):
        """respond() should output valid JSON with decision and reason."""
        from stop_gate import respond
        import io
        from contextlib import redirect_stdout

        f = io.StringIO()
        with redirect_stdout(f):
            respond("approve", "All checks passed")

        output = f.getvalue().strip()
        result = json.loads(output)

        self.assertEqual(result['decision'], 'approve')
        self.assertEqual(result['reason'], 'All checks passed')

    def test_respond_block_decision(self):
        """respond() should output block decision correctly."""
        from stop_gate import respond
        import io
        from contextlib import redirect_stdout

        f = io.StringIO()
        with redirect_stdout(f):
            respond("block", "State not modified")

        output = f.getvalue().strip()
        result = json.loads(output)

        self.assertEqual(result['decision'], 'block')


if __name__ == '__main__':
    unittest.main()
