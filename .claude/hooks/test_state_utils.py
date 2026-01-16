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
from datetime import datetime
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


class TestFileLocking(unittest.TestCase):
    """Tests for file locking behavior."""

    def test_lock_contention_times_out_cleanly(self):
        """file_lock() should raise TimeoutError (not AttributeError) on contention."""
        from state_utils import file_lock, _lock_path_for

        with tempfile.TemporaryDirectory() as tmpdir:
            target = Path(tmpdir) / "state.json"
            lock_path = _lock_path_for(target)
            lock_path.write_text(json.dumps({
                "pid": os.getpid(),
                "created_at": datetime.now().isoformat(),
                "host": "test",
            }))
            try:
                with self.assertRaises(TimeoutError):
                    with file_lock(target, timeout_seconds=0.05, poll_interval=0.01):
                        pass
            finally:
                if lock_path.exists():
                    lock_path.unlink()


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

    @patch('proof_utils.log_proof_entry')
    def test_log_proof(self, mock_log_entry):
        """log_proof() should delegate to proof_utils.log_proof_entry()."""
        from state_utils import log_proof

        mock_log_entry.return_value = {"tool": "TestTool", "success": True}

        log_proof("TestTool", {"key": "value"}, "result", True)

        # Verify delegation happened
        mock_log_entry.assert_called_once_with("TestTool", {"key": "value"}, "result", True)


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


class TestComputeNormalizedCurrentStep(unittest.TestCase):
    """Tests for compute_normalized_current_step() normalization logic."""

    def test_none_state_returns_none(self):
        """compute_normalized_current_step() returns None for None state."""
        from state_utils import compute_normalized_current_step
        self.assertIsNone(compute_normalized_current_step(None))

    def test_non_dict_state_returns_none(self):
        """compute_normalized_current_step() returns None for non-dict state."""
        from state_utils import compute_normalized_current_step
        self.assertIsNone(compute_normalized_current_step("not a dict"))
        self.assertIsNone(compute_normalized_current_step([1, 2, 3]))

    def test_missing_plan_returns_none(self):
        """compute_normalized_current_step() returns None if plan missing."""
        from state_utils import compute_normalized_current_step
        self.assertIsNone(compute_normalized_current_step({}))
        self.assertIsNone(compute_normalized_current_step({"objective": "test"}))

    def test_non_list_plan_returns_none(self):
        """compute_normalized_current_step() returns None for non-list plan."""
        from state_utils import compute_normalized_current_step
        self.assertIsNone(compute_normalized_current_step({"plan": "not a list"}))
        self.assertIsNone(compute_normalized_current_step({"plan": {"key": "value"}}))

    def test_empty_plan_returns_zero(self):
        """compute_normalized_current_step() returns 0 for empty plan."""
        from state_utils import compute_normalized_current_step
        self.assertEqual(compute_normalized_current_step({"plan": []}), 0)

    def test_all_completed_returns_len_plus_one(self):
        """compute_normalized_current_step() returns len(plan)+1 when all completed."""
        from state_utils import compute_normalized_current_step

        # 3 steps all completed -> should return 4
        state = {
            "plan": [
                {"description": "Step 1", "status": "completed"},
                {"description": "Step 2", "status": "completed"},
                {"description": "Step 3", "status": "completed"}
            ]
        }
        self.assertEqual(compute_normalized_current_step(state), 4)

        # 1 step completed -> should return 2
        state_single = {
            "plan": [{"description": "Step 1", "status": "completed"}]
        }
        self.assertEqual(compute_normalized_current_step(state_single), 2)

    def test_pending_step_returns_none(self):
        """compute_normalized_current_step() returns None if any step pending."""
        from state_utils import compute_normalized_current_step

        state = {
            "plan": [
                {"description": "Step 1", "status": "completed"},
                {"description": "Step 2", "status": "pending"},
                {"description": "Step 3", "status": "completed"}
            ]
        }
        self.assertIsNone(compute_normalized_current_step(state))

    def test_in_progress_step_returns_none(self):
        """compute_normalized_current_step() returns None if any step in_progress."""
        from state_utils import compute_normalized_current_step

        state = {
            "plan": [
                {"description": "Step 1", "status": "completed"},
                {"description": "Step 2", "status": "in_progress"}
            ]
        }
        self.assertIsNone(compute_normalized_current_step(state))

    def test_blocked_step_returns_none(self):
        """compute_normalized_current_step() returns None if any step blocked."""
        from state_utils import compute_normalized_current_step

        state = {
            "plan": [
                {"description": "Step 1", "status": "completed"},
                {"description": "Step 2", "status": "blocked"}
            ]
        }
        self.assertIsNone(compute_normalized_current_step(state))

    def test_non_dict_step_returns_none(self):
        """compute_normalized_current_step() returns None if step is not a dict."""
        from state_utils import compute_normalized_current_step

        state = {
            "plan": [
                {"description": "Step 1", "status": "completed"},
                "not a dict"
            ]
        }
        self.assertIsNone(compute_normalized_current_step(state))


class TestNormalizeCurrentStepFile(unittest.TestCase):
    """Tests for normalize_current_step_file() file operations."""

    @patch('state_utils.load_yaml_state')
    def test_missing_state_returns_false(self, mock_load):
        """normalize_current_step_file() returns False for missing state."""
        from state_utils import normalize_current_step_file

        mock_load.return_value = None
        updated, msg = normalize_current_step_file()
        self.assertFalse(updated)
        self.assertIn("missing", msg.lower())

    @patch('state_utils.load_yaml_state')
    @patch('state_utils.compute_normalized_current_step')
    def test_no_normalization_needed_returns_false(self, mock_compute, mock_load):
        """normalize_current_step_file() returns False when no normalization needed."""
        from state_utils import normalize_current_step_file

        mock_load.return_value = {"plan": [{"status": "pending"}]}
        mock_compute.return_value = None

        updated, msg = normalize_current_step_file()
        self.assertFalse(updated)
        self.assertIn("no normalization", msg.lower())

    @patch('state_utils.load_yaml_state')
    @patch('state_utils.compute_normalized_current_step')
    def test_already_normalized_returns_false(self, mock_compute, mock_load):
        """normalize_current_step_file() returns False if already at target value."""
        from state_utils import normalize_current_step_file

        mock_load.return_value = {"current_step": 4}
        mock_compute.return_value = 4

        updated, msg = normalize_current_step_file()
        self.assertFalse(updated)
        self.assertIn("already normalized", msg.lower())

    @patch('state_utils.get_project_dir')
    def test_successful_normalization(self, mock_project_dir):
        """normalize_current_step_file() updates file when normalization needed."""
        from state_utils import normalize_current_step_file

        with tempfile.TemporaryDirectory() as tmpdir:
            mock_project_dir.return_value = Path(tmpdir)

            # Create a test YAML file with completed plan but wrong current_step
            yaml_content = """objective: "Test"
current_step: 2
plan:
  - description: "Step 1"
    status: completed
  - description: "Step 2"
    status: completed
  - description: "Step 3"
    status: completed
"""
            yaml_file = Path(tmpdir) / "active_context.yaml"
            yaml_file.write_text(yaml_content)

            updated, msg = normalize_current_step_file()

            self.assertTrue(updated)
            self.assertIn("4", msg)  # Should normalize to 4 (len=3 + 1)

            # Verify file was updated
            new_content = yaml_file.read_text()
            self.assertIn("current_step: 4", new_content)

    @patch('state_utils.get_project_dir')
    def test_preserves_yaml_structure(self, mock_project_dir):
        """normalize_current_step_file() preserves other YAML content."""
        from state_utils import normalize_current_step_file

        with tempfile.TemporaryDirectory() as tmpdir:
            mock_project_dir.return_value = Path(tmpdir)

            yaml_content = """# Comment at top
objective: "Test objective"
current_step: 1
plan:
  - description: "Step 1"
    status: completed
constraints:
  - "Keep it simple"
memory:
  - trigger: "test"
    lesson: "Test lesson"
"""
            yaml_file = Path(tmpdir) / "active_context.yaml"
            yaml_file.write_text(yaml_content)

            updated, msg = normalize_current_step_file()
            self.assertTrue(updated)

            new_content = yaml_file.read_text()

            # Verify structure preserved
            self.assertIn("# Comment at top", new_content)
            self.assertIn('objective: "Test objective"', new_content)
            self.assertIn("current_step: 2", new_content)  # Updated
            self.assertIn("constraints:", new_content)
            self.assertIn('- "Keep it simple"', new_content)
            self.assertIn("memory:", new_content)

    @patch('state_utils.get_project_dir')
    def test_handles_indented_current_step(self, mock_project_dir):
        """normalize_current_step_file() handles current_step with indentation."""
        from state_utils import normalize_current_step_file

        with tempfile.TemporaryDirectory() as tmpdir:
            mock_project_dir.return_value = Path(tmpdir)

            # Some YAML might have current_step indented (though not typical)
            yaml_content = """objective: "Test"
  current_step: 1
plan:
  - description: "Step 1"
    status: completed
"""
            yaml_file = Path(tmpdir) / "active_context.yaml"
            yaml_file.write_text(yaml_content)

            # This should fail because our parser might not match indented current_step
            # at root level - testing edge case behavior
            updated, msg = normalize_current_step_file()
            # Either it updates or gracefully fails
            if updated:
                new_content = yaml_file.read_text()
                self.assertIn("current_step: 2", new_content)


# =============================================================================
# v5 Schema: Runtime State Tests
# =============================================================================

class TestRuntimeState(unittest.TestCase):
    """Tests for runtime state functions (v5 schema)."""

    def test_get_runtime_section_with_state(self):
        """get_runtime_section should extract runtime from provided state."""
        from state_utils import get_runtime_section

        state = {
            "runtime": {
                "junction": {"pending": None},
                "gear": {"current": "active"},
                "dispatch": {"enabled": True},
            }
        }

        # Get entire runtime
        runtime = get_runtime_section(state)
        self.assertEqual(runtime["gear"]["current"], "active")

        # Get specific section
        junction = get_runtime_section(state, "junction")
        self.assertIsNone(junction["pending"])

        gear = get_runtime_section(state, "gear")
        self.assertEqual(gear["current"], "active")

    def test_get_runtime_section_missing(self):
        """get_runtime_section should return empty dict if missing."""
        from state_utils import get_runtime_section

        state = {"objective": "test"}
        runtime = get_runtime_section(state)
        self.assertEqual(runtime, {})

        junction = get_runtime_section(state, "junction")
        self.assertEqual(junction, {})

    def test_serialize_runtime_value_primitives(self):
        """_serialize_runtime_value should handle primitives."""
        from state_utils import _serialize_runtime_value

        self.assertEqual(_serialize_runtime_value(None), "null")
        self.assertEqual(_serialize_runtime_value(True), "true")
        self.assertEqual(_serialize_runtime_value(False), "false")
        self.assertEqual(_serialize_runtime_value(42), "42")
        self.assertEqual(_serialize_runtime_value(3.14), "3.14")

    def test_serialize_runtime_value_strings(self):
        """_serialize_runtime_value should quote strings appropriately."""
        from state_utils import _serialize_runtime_value

        # Regular strings get quoted
        self.assertEqual(_serialize_runtime_value("hello"), '"hello"')
        # Strings that look like other types get quoted
        self.assertEqual(_serialize_runtime_value("true"), '"true"')
        self.assertEqual(_serialize_runtime_value("123"), '"123"')

    def test_serialize_runtime_value_empty_collections(self):
        """_serialize_runtime_value should handle empty collections."""
        from state_utils import _serialize_runtime_value

        self.assertEqual(_serialize_runtime_value([]), "[]")
        self.assertEqual(_serialize_runtime_value({}), "{}")

    def test_migrate_json_runtime_state(self):
        """migrate_json_runtime_state should read from JSON files."""
        from state_utils import migrate_json_runtime_state, get_state_dir
        import tempfile

        with tempfile.TemporaryDirectory() as tmpdir:
            with patch('state_utils.get_state_dir', return_value=Path(tmpdir)):
                # Create test JSON files
                state_dir = Path(tmpdir)

                # Junction state
                junction_data = {
                    "pending": {"id": "test-123", "type": "test"},
                    "suppression": [{"fingerprint": "abc", "expires_at": "2026-01-01"}],
                    "history_tail": [{"id": "h1", "type": "t", "decision": "approve"}]
                }
                (state_dir / "junction_state.json").write_text(json.dumps(junction_data))

                # Gear state
                gear_data = {
                    "current_gear": "patrol",
                    "entered_at": "2026-01-01",
                    "iterations": 5
                }
                (state_dir / "gear_state.json").write_text(json.dumps(gear_data))

                # Dispatch state
                dispatch_data = {
                    "enabled": True,
                    "state": "running",
                    "iteration": 10
                }
                (state_dir / "dispatch_state.json").write_text(json.dumps(dispatch_data))

                # Migrate
                result = migrate_json_runtime_state()

                # Verify junction
                self.assertEqual(result["junction"]["pending"]["id"], "test-123")
                self.assertEqual(len(result["junction"]["suppressions"]), 1)

                # Verify gear
                self.assertEqual(result["gear"]["current"], "patrol")
                self.assertEqual(result["gear"]["iterations"], 5)

                # Verify dispatch
                self.assertTrue(result["dispatch"]["enabled"])
                self.assertEqual(result["dispatch"]["state"], "running")

    def test_migrate_json_runtime_state_missing_files(self):
        """migrate_json_runtime_state should handle missing files gracefully."""
        from state_utils import migrate_json_runtime_state
        import tempfile

        with tempfile.TemporaryDirectory() as tmpdir:
            with patch('state_utils.get_state_dir', return_value=Path(tmpdir)):
                result = migrate_json_runtime_state()

                # Should return empty sections, not crash
                self.assertEqual(result["junction"], {})
                self.assertEqual(result["gear"], {})
                self.assertEqual(result["dispatch"], {})


# =============================================================================
# Intent Verification Tests (Understanding-First v1.0)
# =============================================================================

class TestIntentVerification(unittest.TestCase):
    """Tests for intent verification functions (Understanding-First v1.0)."""

    def test_get_intent_with_state(self):
        """get_intent should return intent section from state."""
        from state_utils import get_intent

        state = {
            "intent": {
                "user_wants": "Add a feature",
                "success_looks_like": "Feature works",
                "confirmed": True
            }
        }

        intent = get_intent(state)
        self.assertEqual(intent["user_wants"], "Add a feature")
        self.assertTrue(intent["confirmed"])

    def test_get_intent_missing_section(self):
        """get_intent should return empty dict if no intent section."""
        from state_utils import get_intent

        state = {"objective": "test"}
        intent = get_intent(state)
        self.assertEqual(intent, {})

    def test_get_intent_empty_state(self):
        """get_intent should handle empty/None state."""
        from state_utils import get_intent

        self.assertEqual(get_intent({}), {})
        # With None, it will try to load from file
        with patch('state_utils.load_yaml_state', return_value=None):
            self.assertEqual(get_intent(None), {})

    def test_is_intent_confirmed_true(self):
        """is_intent_confirmed should return True when confirmed."""
        from state_utils import is_intent_confirmed

        state = {
            "intent": {
                "user_wants": "Add a feature",
                "confirmed": True
            }
        }

        self.assertTrue(is_intent_confirmed(state))

    def test_is_intent_confirmed_false(self):
        """is_intent_confirmed should return False when not confirmed."""
        from state_utils import is_intent_confirmed

        state = {
            "intent": {
                "user_wants": "Add a feature",
                "confirmed": False
            }
        }

        self.assertFalse(is_intent_confirmed(state))

    def test_is_intent_confirmed_missing(self):
        """is_intent_confirmed should return False when intent missing."""
        from state_utils import is_intent_confirmed

        self.assertFalse(is_intent_confirmed({"objective": "test"}))
        self.assertFalse(is_intent_confirmed({}))

    def test_is_intent_confirmed_no_confirmed_field(self):
        """is_intent_confirmed should return False when confirmed field missing."""
        from state_utils import is_intent_confirmed

        state = {
            "intent": {
                "user_wants": "Add a feature"
                # No 'confirmed' field
            }
        }

        self.assertFalse(is_intent_confirmed(state))

    def test_get_intent_summary_confirmed(self):
        """get_intent_summary should report confirmed intent."""
        from state_utils import get_intent_summary

        state = {
            "intent": {
                "user_wants": "Add a feature",
                "confirmed": True
            }
        }

        summary = get_intent_summary(state)
        self.assertIn("confirmed", summary.lower())
        self.assertNotIn("NOT", summary)

    def test_get_intent_summary_not_confirmed(self):
        """get_intent_summary should report unconfirmed intent."""
        from state_utils import get_intent_summary

        state = {
            "intent": {
                "user_wants": "Add a very important feature",
                "confirmed": False
            }
        }

        summary = get_intent_summary(state)
        self.assertIn("NOT confirmed", summary)
        self.assertIn("Add a very", summary)

    def test_get_intent_summary_not_set(self):
        """get_intent_summary should report when intent not set."""
        from state_utils import get_intent_summary

        summary = get_intent_summary({"objective": "test"})
        self.assertIn("not set", summary.lower())

    @patch('state_utils.get_project_dir')
    def test_set_intent_confirmed_success(self, mock_project_dir):
        """set_intent_confirmed should update YAML file."""
        from state_utils import set_intent_confirmed

        with tempfile.TemporaryDirectory() as tmpdir:
            mock_project_dir.return_value = Path(tmpdir)

            yaml_content = """objective: "Test"
intent:
  user_wants: "Add feature"
  success_looks_like: "Works"
  confirmed: false
  confirmed_at: null
plan:
  - description: "Step 1"
    status: pending
"""
            yaml_file = Path(tmpdir) / "active_context.yaml"
            yaml_file.write_text(yaml_content)

            # Set confirmed
            result = set_intent_confirmed(True, {"intent": {"user_wants": "Add feature"}})

            self.assertTrue(result)

            # Verify file was updated
            new_content = yaml_file.read_text()
            self.assertIn("confirmed: true", new_content)

    @patch('state_utils.get_project_dir')
    def test_set_intent_confirmed_fails_without_user_wants(self, mock_project_dir):
        """set_intent_confirmed should fail if user_wants not set."""
        from state_utils import set_intent_confirmed

        with tempfile.TemporaryDirectory() as tmpdir:
            mock_project_dir.return_value = Path(tmpdir)

            yaml_file = Path(tmpdir) / "active_context.yaml"
            yaml_file.write_text("objective: test")

            # Should fail because no user_wants
            result = set_intent_confirmed(True, {"intent": {}})

            self.assertFalse(result)


if __name__ == '__main__':
    unittest.main()
