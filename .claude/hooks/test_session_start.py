#!/usr/bin/env python3
"""
Tests for session_start.py - session initialization hook.

Tests the core functions for:
- Session ID generation
- State clearing
- Dispatch status output
- Context output
- Main initialization flow
"""
import json
import os
import sys
import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from unittest.mock import patch, MagicMock, call
from io import StringIO

# Add hooks directory to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


class TestGenerateSessionId(unittest.TestCase):
    """Tests for generate_session_id() function."""

    def test_generates_id(self):
        """generate_session_id() should return a string."""
        from session_start import generate_session_id

        session_id = generate_session_id()

        self.assertIsInstance(session_id, str)

    def test_id_format(self):
        """generate_session_id() should have expected format."""
        from session_start import generate_session_id

        session_id = generate_session_id()

        # Should be YYYYMMDD-HHMMSS format
        self.assertEqual(len(session_id), 15)
        self.assertEqual(session_id[8], "-")

    @patch('session_start.datetime')
    def test_uses_current_time(self, mock_datetime):
        """generate_session_id() should use current datetime."""
        from session_start import generate_session_id

        mock_now = MagicMock()
        mock_now.strftime.return_value = "20250101-120000"
        mock_datetime.now.return_value = mock_now

        session_id = generate_session_id()

        self.assertEqual(session_id, "20250101-120000")


class TestClearOldState(unittest.TestCase):
    """Tests for clear_old_state() function."""

    @patch('session_start.get_state_dir')
    def test_clears_failure_log(self, mock_state_dir):
        """clear_old_state() should delete failure_log.jsonl."""
        from session_start import clear_old_state

        with tempfile.TemporaryDirectory() as tmpdir:
            mock_state_dir.return_value = Path(tmpdir)

            # Create a failure log
            failure_log = Path(tmpdir) / "failure_log.jsonl"
            failure_log.write_text('{"error": "test"}')

            clear_old_state()

            self.assertFalse(failure_log.exists())

    @patch('session_start.get_state_dir')
    def test_handles_missing_log(self, mock_state_dir):
        """clear_old_state() should not error if log missing."""
        from session_start import clear_old_state

        with tempfile.TemporaryDirectory() as tmpdir:
            mock_state_dir.return_value = Path(tmpdir)

            # No failure log exists
            clear_old_state()  # Should not raise




class TestOutputContext(unittest.TestCase):
    """Tests for output_context() function."""

    @patch('session_start.get_project_dir')
    @patch('session_start.load_yaml_state')
    @patch('session_start.get_schema_version')
    @patch('session_start.get_memory_items')
    @patch('session_start.get_unresolved_mismatches')
    @patch('session_start.check_state_entropy')
    @patch('session_start.load_archive')
    @patch('session_start.generate_reflection_summary')
    @patch('session_start.get_dispatch_status')
    @patch('session_start.detect_session_context')
    @patch('session_start.get_orchestrator_suggestion')
    def test_outputs_objective(self, mock_suggest, mock_detect, mock_dispatch,
                               mock_reflect, mock_archive, mock_entropy,
                               mock_mismatch, mock_memory, mock_schema,
                               mock_load, mock_project):
        """output_context() should print objective."""
        from session_start import output_context

        mock_project.return_value = Path("/test")
        mock_load.return_value = {"objective": "Test objective", "plan": []}
        mock_schema.return_value = 2
        mock_memory.return_value = []
        mock_mismatch.return_value = []
        mock_entropy.return_value = (False, [])
        mock_archive.return_value = []
        mock_reflect.return_value = None
        mock_dispatch.return_value = {"enabled": False}
        mock_detect.return_value = ("READY", {})
        mock_suggest.return_value = {}

        with patch('sys.stdout', new_callable=StringIO) as mock_stdout:
            output_context()
            output = mock_stdout.getvalue()

        self.assertIn("Test objective", output)

    @patch('session_start.get_project_dir')
    @patch('session_start.load_yaml_state')
    @patch('session_start.get_schema_version')
    @patch('session_start.get_memory_items')
    @patch('session_start.get_unresolved_mismatches')
    @patch('session_start.check_state_entropy')
    @patch('session_start.load_archive')
    @patch('session_start.generate_reflection_summary')
    @patch('session_start.get_dispatch_status')
    @patch('session_start.detect_session_context')
    @patch('session_start.get_orchestrator_suggestion')
    def test_outputs_plan_steps(self, mock_suggest, mock_detect, mock_dispatch,
                                 mock_reflect, mock_archive, mock_entropy,
                                 mock_mismatch, mock_memory, mock_schema,
                                 mock_load, mock_project):
        """output_context() should print plan steps."""
        from session_start import output_context

        mock_project.return_value = Path("/test")
        mock_load.return_value = {
            "objective": "Test",
            "current_step": 1,
            "plan": [
                {"description": "Step 1", "status": "in_progress"},
                {"description": "Step 2", "status": "pending"}
            ]
        }
        mock_schema.return_value = 2
        mock_memory.return_value = []
        mock_mismatch.return_value = []
        mock_entropy.return_value = (False, [])
        mock_archive.return_value = []
        mock_reflect.return_value = None
        mock_dispatch.return_value = {"enabled": False}
        mock_detect.return_value = ("READY", {})
        mock_suggest.return_value = {}

        with patch('sys.stdout', new_callable=StringIO) as mock_stdout:
            output_context()
            output = mock_stdout.getvalue()

        self.assertIn("Step 1", output)
        self.assertIn("Step 2", output)
        self.assertIn("[in_progress]", output)

    @patch('session_start.get_project_dir')
    @patch('session_start.load_yaml_state')
    @patch('session_start.get_schema_version')
    @patch('session_start.get_memory_items')
    @patch('session_start.get_unresolved_mismatches')
    @patch('session_start.check_state_entropy')
    @patch('session_start.load_archive')
    @patch('session_start.generate_reflection_summary')
    @patch('session_start.get_dispatch_status')
    @patch('session_start.detect_session_context')
    @patch('session_start.get_orchestrator_suggestion')
    def test_outputs_memory(self, mock_suggest, mock_detect, mock_dispatch,
                            mock_reflect, mock_archive, mock_entropy,
                            mock_mismatch, mock_memory, mock_schema,
                            mock_load, mock_project):
        """output_context() should print memory items."""
        from session_start import output_context

        mock_project.return_value = Path("/test")
        mock_load.return_value = {"objective": "Test", "plan": []}
        mock_schema.return_value = 2
        mock_memory.return_value = [
            {"trigger": "test", "lesson": "Test lesson", "reinforced": 2}
        ]
        mock_mismatch.return_value = []
        mock_entropy.return_value = (False, [])
        mock_archive.return_value = []
        mock_reflect.return_value = None
        mock_dispatch.return_value = {"enabled": False}
        mock_detect.return_value = ("READY", {})
        mock_suggest.return_value = {}

        with patch('sys.stdout', new_callable=StringIO) as mock_stdout:
            output_context()
            output = mock_stdout.getvalue()

        self.assertIn("Test lesson", output)

    @patch('session_start.get_project_dir')
    @patch('session_start.load_yaml_state')
    @patch('session_start.get_schema_version')
    @patch('session_start.get_memory_items')
    @patch('session_start.get_unresolved_mismatches')
    @patch('session_start.check_state_entropy')
    @patch('session_start.load_archive')
    @patch('session_start.generate_reflection_summary')
    @patch('session_start.get_dispatch_status')
    @patch('session_start.detect_session_context')
    @patch('session_start.get_orchestrator_suggestion')
    def test_warns_about_mismatches(self, mock_suggest, mock_detect, mock_dispatch,
                                     mock_reflect, mock_archive, mock_entropy,
                                     mock_mismatch, mock_memory, mock_schema,
                                     mock_load, mock_project):
        """output_context() should warn about unresolved mismatches."""
        from session_start import output_context

        mock_project.return_value = Path("/test")
        mock_load.return_value = {"objective": "Test", "plan": []}
        mock_schema.return_value = 2
        mock_memory.return_value = []
        mock_mismatch.return_value = [
            {"expectation": "A", "observation": "B"}
        ]
        mock_entropy.return_value = (False, [])
        mock_archive.return_value = []
        mock_reflect.return_value = None
        mock_dispatch.return_value = {"enabled": False}
        mock_detect.return_value = ("READY", {})
        mock_suggest.return_value = {}

        with patch('sys.stdout', new_callable=StringIO) as mock_stdout:
            output_context()
            output = mock_stdout.getvalue()

        self.assertIn("UNRESOLVED MISMATCHES", output)
        self.assertIn("/edge-adapt", output)

    @patch('session_start.get_project_dir')
    @patch('session_start.load_yaml_state')
    @patch('session_start.get_schema_version')
    @patch('session_start.get_memory_items')
    @patch('session_start.get_unresolved_mismatches')
    @patch('session_start.check_state_entropy')
    @patch('session_start.load_archive')
    @patch('session_start.generate_reflection_summary')
    @patch('session_start.get_dispatch_status')
    @patch('session_start.detect_session_context')
    @patch('session_start.get_orchestrator_suggestion')
    def test_warns_about_entropy(self, mock_suggest, mock_detect, mock_dispatch,
                                  mock_reflect, mock_archive, mock_entropy,
                                  mock_mismatch, mock_memory, mock_schema,
                                  mock_load, mock_project):
        """output_context() should warn about high entropy."""
        from session_start import output_context

        mock_project.return_value = Path("/test")
        mock_load.return_value = {"objective": "Test", "plan": []}
        mock_schema.return_value = 2
        mock_memory.return_value = []
        mock_mismatch.return_value = []
        mock_entropy.return_value = (True, ["Too many completed steps"])
        mock_archive.return_value = []
        mock_reflect.return_value = None
        mock_dispatch.return_value = {"enabled": False}
        mock_detect.return_value = ("READY", {})
        mock_suggest.return_value = {}

        with patch('sys.stdout', new_callable=StringIO) as mock_stdout:
            output_context()
            output = mock_stdout.getvalue()

        self.assertIn("ENTROPY HIGH", output)
        self.assertIn("/edge-prune", output)

    @patch('session_start.get_project_dir')
    @patch('session_start.load_yaml_state')
    @patch('session_start.get_schema_version')
    @patch('session_start.get_memory_items')
    @patch('session_start.get_unresolved_mismatches')
    @patch('session_start.check_state_entropy')
    @patch('session_start.load_archive')
    @patch('session_start.generate_reflection_summary')
    @patch('session_start.get_dispatch_status')
    @patch('session_start.detect_session_context')
    @patch('session_start.get_orchestrator_suggestion')
    def test_shows_dispatch_enabled(self, mock_suggest, mock_detect, mock_dispatch,
                                 mock_reflect, mock_archive, mock_entropy,
                                 mock_mismatch, mock_memory, mock_schema,
                                 mock_load, mock_project):
        """output_context() should show Dispatch Mode when enabled."""
        from session_start import output_context

        mock_project.return_value = Path("/test")
        mock_load.return_value = {"objective": "Test", "plan": []}
        mock_schema.return_value = 2
        mock_memory.return_value = []
        mock_mismatch.return_value = []
        mock_entropy.return_value = (False, [])
        mock_archive.return_value = []
        mock_reflect.return_value = None
        mock_dispatch.return_value = {
            "enabled": True,
            "state": "running",
            "iteration": 10,
            "junction": None,
            "stats": {"junctions_hit": 2},
            "stuck_count": 0
        }
        mock_detect.return_value = ("READY", {})
        mock_suggest.return_value = {}

        with patch('sys.stdout', new_callable=StringIO) as mock_stdout:
            output_context()
            output = mock_stdout.getvalue()

        self.assertIn("DISPATCH MODE: RUNNING", output)
        self.assertIn("Iterations: 10", output)
        self.assertIn("Junctions: 2", output)

    @patch('session_start.get_project_dir')
    @patch('session_start.load_yaml_state')
    def test_handles_missing_state(self, mock_load, mock_project):
        """output_context() should handle missing state."""
        from session_start import output_context

        mock_project.return_value = Path("/test")
        mock_load.return_value = None

        with patch('sys.stdout', new_callable=StringIO) as mock_stdout:
            output_context()
            output = mock_stdout.getvalue()

        self.assertIn("WARNING", output)
        self.assertIn("active_context.yaml missing", output)

    @patch('session_start.get_project_dir')
    @patch('session_start.load_yaml_state')
    @patch('session_start.get_schema_version')
    @patch('session_start.get_memory_items')
    @patch('session_start.get_unresolved_mismatches')
    @patch('session_start.check_state_entropy')
    @patch('session_start.load_archive')
    @patch('session_start.generate_reflection_summary')
    @patch('session_start.get_dispatch_status')
    @patch('session_start.detect_session_context')
    @patch('session_start.get_orchestrator_suggestion')
    def test_shows_reflection(self, mock_suggest, mock_detect, mock_dispatch,
                               mock_reflect, mock_archive, mock_entropy,
                               mock_mismatch, mock_memory, mock_schema,
                               mock_load, mock_project):
        """output_context() should show reflection summary."""
        from session_start import output_context

        mock_project.return_value = Path("/test")
        mock_load.return_value = {"objective": "Test", "plan": []}
        mock_schema.return_value = 2
        mock_memory.return_value = []
        mock_mismatch.return_value = []
        mock_entropy.return_value = (False, [])
        mock_archive.return_value = [{"type": "completed_objective"}]
        mock_reflect.return_value = "Sessions scored: 5\nAverage: 4.5/6"
        mock_dispatch.return_value = {"enabled": False}
        mock_detect.return_value = ("READY", {})
        mock_suggest.return_value = {}

        with patch('sys.stdout', new_callable=StringIO) as mock_stdout:
            output_context()
            output = mock_stdout.getvalue()

        self.assertIn("REFLECTION", output)
        self.assertIn("Sessions scored", output)


class TestMain(unittest.TestCase):
    """Tests for main() function."""

    @patch('session_start.get_state_dir')
    @patch('session_start.get_proof_dir')
    @patch('session_start.generate_session_id')
    @patch('session_start.save_state_hash')
    @patch('session_start.clear_old_state')
    @patch('session_start.output_context')
    def test_creates_directories(self, mock_output, mock_clear, mock_hash,
                                  mock_session, mock_proof, mock_state):
        """main() should create state and proof directories."""
        from session_start import main

        with tempfile.TemporaryDirectory() as tmpdir:
            state_dir = Path(tmpdir) / "state"
            proof_dir = Path(tmpdir) / "proof"
            mock_state.return_value = state_dir
            mock_proof.return_value = proof_dir
            mock_session.return_value = "20250101-120000"
            mock_hash.return_value = "abc123"

            main()

            self.assertTrue(state_dir.exists())
            self.assertTrue(proof_dir.exists())

    @patch('session_start.get_state_dir')
    @patch('session_start.get_proof_dir')
    @patch('session_start.generate_session_id')
    @patch('session_start.save_state_hash')
    @patch('session_start.clear_old_state')
    @patch('session_start.output_context')
    def test_saves_session_id(self, mock_output, mock_clear, mock_hash,
                               mock_session, mock_proof, mock_state):
        """main() should save session ID to file."""
        from session_start import main

        with tempfile.TemporaryDirectory() as tmpdir:
            state_dir = Path(tmpdir) / "state"
            proof_dir = Path(tmpdir) / "proof"
            mock_state.return_value = state_dir
            mock_proof.return_value = proof_dir
            mock_session.return_value = "20250101-120000"
            mock_hash.return_value = "abc123"

            main()

            session_file = state_dir / "session_id"
            self.assertTrue(session_file.exists())
            self.assertEqual(session_file.read_text(), "20250101-120000")

    @patch('session_start.get_state_dir')
    @patch('session_start.get_proof_dir')
    @patch('session_start.generate_session_id')
    @patch('session_start.save_state_hash')
    @patch('session_start.clear_old_state')
    @patch('session_start.output_context')
    def test_calls_save_state_hash(self, mock_output, mock_clear, mock_hash,
                                    mock_session, mock_proof, mock_state):
        """main() should call save_state_hash()."""
        from session_start import main

        with tempfile.TemporaryDirectory() as tmpdir:
            state_dir = Path(tmpdir) / "state"
            proof_dir = Path(tmpdir) / "proof"
            mock_state.return_value = state_dir
            mock_proof.return_value = proof_dir
            mock_session.return_value = "test-session"
            mock_hash.return_value = "abc123"

            main()

            mock_hash.assert_called_once()

    @patch('session_start.get_state_dir')
    @patch('session_start.get_proof_dir')
    @patch('session_start.generate_session_id')
    @patch('session_start.save_state_hash')
    @patch('session_start.clear_old_state')
    @patch('session_start.output_context')
    def test_calls_clear_old_state(self, mock_output, mock_clear, mock_hash,
                                    mock_session, mock_proof, mock_state):
        """main() should call clear_old_state()."""
        from session_start import main

        with tempfile.TemporaryDirectory() as tmpdir:
            state_dir = Path(tmpdir) / "state"
            proof_dir = Path(tmpdir) / "proof"
            mock_state.return_value = state_dir
            mock_proof.return_value = proof_dir
            mock_session.return_value = "test-session"
            mock_hash.return_value = "abc123"

            main()

            mock_clear.assert_called_once()

    @patch('session_start.get_state_dir')
    @patch('session_start.get_proof_dir')
    @patch('session_start.generate_session_id')
    @patch('session_start.save_state_hash')
    @patch('session_start.clear_old_state')
    @patch('session_start.output_context')
    def test_calls_output_context(self, mock_output, mock_clear, mock_hash,
                                   mock_session, mock_proof, mock_state):
        """main() should call output_context()."""
        from session_start import main

        with tempfile.TemporaryDirectory() as tmpdir:
            state_dir = Path(tmpdir) / "state"
            proof_dir = Path(tmpdir) / "proof"
            mock_state.return_value = state_dir
            mock_proof.return_value = proof_dir
            mock_session.return_value = "test-session"
            mock_hash.return_value = "abc123"

            main()

            mock_output.assert_called_once()


if __name__ == '__main__':
    unittest.main()
