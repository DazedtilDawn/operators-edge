#!/usr/bin/env python3
"""
Tests for state_utils.py - core state management utilities.

Tests the core functions for:
- Path utilities
- YAML parsing
- Hashing and state tracking
- Failure and proof logging
- State helpers
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


class TestPathUtilities(unittest.TestCase):
    """Tests for path utility functions."""

    @patch.dict(os.environ, {"CLAUDE_PROJECT_DIR": "/test/project"})
    def test_get_project_dir_from_env(self):
        """get_project_dir() should use CLAUDE_PROJECT_DIR env var."""
        from state_utils import get_project_dir
        self.assertEqual(get_project_dir(), Path("/test/project"))

    @patch.dict(os.environ, {}, clear=True)
    def test_get_project_dir_fallback(self):
        """get_project_dir() should fall back to cwd."""
        from state_utils import get_project_dir
        # Remove CLAUDE_PROJECT_DIR if present
        os.environ.pop("CLAUDE_PROJECT_DIR", None)
        self.assertEqual(get_project_dir(), Path(os.getcwd()))

    @patch('state_utils.get_project_dir')
    def test_get_state_dir(self, mock_project):
        """get_state_dir() should return .claude/state path."""
        from state_utils import get_state_dir
        mock_project.return_value = Path("/project")
        self.assertEqual(get_state_dir(), Path("/project/.claude/state"))

    @patch('state_utils.get_project_dir')
    def test_get_proof_dir(self, mock_project):
        """get_proof_dir() should return .proof path."""
        from state_utils import get_proof_dir
        mock_project.return_value = Path("/project")
        self.assertEqual(get_proof_dir(), Path("/project/.proof"))


class TestYamlParsing(unittest.TestCase):
    """Tests for YAML parsing functions."""

    def test_parse_yaml_value_null(self):
        """parse_yaml_value() should handle null."""
        from state_utils import parse_yaml_value
        self.assertIsNone(parse_yaml_value("null"))
        self.assertIsNone(parse_yaml_value(""))

    def test_parse_yaml_value_bool(self):
        """parse_yaml_value() should handle booleans."""
        from state_utils import parse_yaml_value
        self.assertTrue(parse_yaml_value("true"))
        self.assertFalse(parse_yaml_value("false"))

    def test_parse_yaml_value_numbers(self):
        """parse_yaml_value() should handle numbers."""
        from state_utils import parse_yaml_value
        self.assertEqual(parse_yaml_value("42"), 42)
        self.assertEqual(parse_yaml_value("3.14"), 3.14)

    def test_parse_yaml_value_strings(self):
        """parse_yaml_value() should handle quoted strings."""
        from state_utils import parse_yaml_value
        self.assertEqual(parse_yaml_value('"hello"'), "hello")
        self.assertEqual(parse_yaml_value("'world'"), "world")

    def test_parse_simple_yaml_basic(self):
        """parse_simple_yaml() should parse basic structure."""
        from state_utils import parse_simple_yaml

        yaml = """
objective: "Test objective"
current_step: 1
"""
        result = parse_simple_yaml(yaml)
        self.assertEqual(result["objective"], "Test objective")
        self.assertEqual(result["current_step"], 1)

    def test_parse_simple_yaml_list(self):
        """parse_simple_yaml() should parse lists."""
        from state_utils import parse_simple_yaml

        yaml = """
lessons:
  - "Lesson one"
  - "Lesson two"
"""
        result = parse_simple_yaml(yaml)
        self.assertEqual(len(result["lessons"]), 2)

    def test_parse_simple_yaml_nested_dict(self):
        """parse_simple_yaml() should parse nested dicts in lists."""
        from state_utils import parse_simple_yaml

        yaml = """
plan:
  - description: "Step 1"
    status: pending
"""
        result = parse_simple_yaml(yaml)
        self.assertEqual(len(result["plan"]), 1)
        self.assertEqual(result["plan"][0]["description"], "Step 1")
        self.assertEqual(result["plan"][0]["status"], "pending")


class TestFileHash(unittest.TestCase):
    """Tests for file_hash() function."""

    def test_hash_existing_file(self):
        """file_hash() should return hash for existing file."""
        from state_utils import file_hash

        with tempfile.NamedTemporaryFile(mode='w', delete=False) as f:
            f.write("test content")
            f.flush()
            try:
                h = file_hash(f.name)
                self.assertIsNotNone(h)
                self.assertEqual(len(h), 64)  # SHA256 hex length
            finally:
                os.unlink(f.name)

    def test_hash_nonexistent_file(self):
        """file_hash() should return None for missing file."""
        from state_utils import file_hash
        self.assertIsNone(file_hash("/nonexistent/file.txt"))


class TestFailureLogging(unittest.TestCase):
    """Tests for failure logging functions."""

    @patch('state_utils.get_state_dir')
    def test_log_failure(self, mock_state_dir):
        """log_failure() should append to failure log."""
        from state_utils import log_failure

        with tempfile.TemporaryDirectory() as tmpdir:
            mock_state_dir.return_value = Path(tmpdir)

            log_failure("test command", "test error")

            log_file = Path(tmpdir) / "failure_log.jsonl"
            self.assertTrue(log_file.exists())

            content = log_file.read_text()
            entry = json.loads(content.strip())
            self.assertIn("test command", entry["command"])

    @patch('state_utils.get_state_dir')
    def test_get_recent_failures_empty(self, mock_state_dir):
        """get_recent_failures() should return 0 for no log."""
        from state_utils import get_recent_failures

        with tempfile.TemporaryDirectory() as tmpdir:
            mock_state_dir.return_value = Path(tmpdir)
            count = get_recent_failures("some command")
            self.assertEqual(count, 0)


class TestProofLogging(unittest.TestCase):
    """Tests for log_proof() function."""

    @patch('state_utils.get_proof_dir')
    def test_log_proof(self, mock_proof_dir):
        """log_proof() should append to session log."""
        from state_utils import log_proof

        with tempfile.TemporaryDirectory() as tmpdir:
            mock_proof_dir.return_value = Path(tmpdir)

            log_proof("TestTool", {"key": "value"}, "result", True)

            log_file = Path(tmpdir) / "session_log.jsonl"
            self.assertTrue(log_file.exists())

            content = log_file.read_text()
            entry = json.loads(content.strip())
            self.assertEqual(entry["tool"], "TestTool")
            self.assertTrue(entry["success"])


class TestStateHelpers(unittest.TestCase):
    """Tests for state helper functions."""

    def test_get_current_step(self):
        """get_current_step() should return correct step."""
        from state_utils import get_current_step

        state = {
            "current_step": 2,
            "plan": [
                {"description": "Step 1"},
                {"description": "Step 2"},
                {"description": "Step 3"}
            ]
        }

        step = get_current_step(state)
        self.assertEqual(step["description"], "Step 2")

    def test_get_current_step_none(self):
        """get_current_step() should return None for empty state."""
        from state_utils import get_current_step
        self.assertIsNone(get_current_step(None))

    def test_get_step_by_status(self):
        """get_step_by_status() should filter by status."""
        from state_utils import get_step_by_status

        state = {
            "plan": [
                {"status": "completed"},
                {"status": "pending"},
                {"status": "completed"}
            ]
        }

        completed = get_step_by_status(state, "completed")
        self.assertEqual(len(completed), 2)

    def test_count_completed_steps(self):
        """count_completed_steps() should count correctly."""
        from state_utils import count_completed_steps

        state = {
            "plan": [
                {"status": "completed"},
                {"status": "pending"},
                {"status": "completed"}
            ]
        }

        self.assertEqual(count_completed_steps(state), 2)

    def test_get_unresolved_mismatches(self):
        """get_unresolved_mismatches() should filter unresolved."""
        from state_utils import get_unresolved_mismatches

        state = {
            "mismatches": [
                {"id": 1, "resolved": True},
                {"id": 2, "resolved": False},
                {"id": 3}  # No resolved key = unresolved
            ]
        }

        unresolved = get_unresolved_mismatches(state)
        self.assertEqual(len(unresolved), 2)

    def test_get_memory_items_v2(self):
        """get_memory_items() should return memory from v2 state."""
        from state_utils import get_memory_items

        state = {
            "memory": [
                {"trigger": "test", "lesson": "lesson1"}
            ]
        }

        items = get_memory_items(state)
        self.assertEqual(len(items), 1)

    def test_get_memory_items_v1_fallback(self):
        """get_memory_items() should fall back to lessons for v1."""
        from state_utils import get_memory_items

        state = {
            "lessons": ["Simple lesson"]
        }

        items = get_memory_items(state)
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]["lesson"], "Simple lesson")

    def test_get_schema_version_v1(self):
        """get_schema_version() should detect v1 schema."""
        from state_utils import get_schema_version

        state = {
            "objective": "Test",
            "plan": [],
            "lessons": []
        }

        self.assertEqual(get_schema_version(state), 1)

    def test_get_schema_version_v2(self):
        """get_schema_version() should detect v2 schema."""
        from state_utils import get_schema_version

        state = {
            "objective": "Test",
            "mismatches": [],
            "self_score": {}
        }

        self.assertEqual(get_schema_version(state), 2)

    def test_generate_mismatch_id(self):
        """generate_mismatch_id() should create unique ID."""
        from state_utils import generate_mismatch_id

        id1 = generate_mismatch_id()
        self.assertTrue(id1.startswith("mismatch-"))


if __name__ == '__main__':
    unittest.main()
