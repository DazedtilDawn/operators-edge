#!/usr/bin/env python3
"""
Tests for junction_utils.py - junction state management with readonly mode.
"""
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

# Add hooks directory to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from junction_utils import (
    is_readonly,
    load_junction_state,
    save_junction_state,
    set_pending_junction,
    clear_pending_junction,
    get_pending_junction,
    _default_state,
)


class TestIsReadonly(unittest.TestCase):
    """Tests for is_readonly detection."""

    def test_readonly_not_set(self):
        """No env var means not readonly."""
        with patch.dict(os.environ, {}, clear=True):
            self.assertFalse(is_readonly())

    def test_readonly_set_to_1(self):
        """EDGE_READONLY=1 enables readonly mode."""
        with patch.dict(os.environ, {"EDGE_READONLY": "1"}):
            self.assertTrue(is_readonly())

    def test_readonly_set_to_true(self):
        """EDGE_READONLY=true enables readonly mode."""
        with patch.dict(os.environ, {"EDGE_READONLY": "true"}):
            self.assertTrue(is_readonly())

    def test_readonly_set_to_yes(self):
        """EDGE_READONLY=yes enables readonly mode."""
        with patch.dict(os.environ, {"EDGE_READONLY": "yes"}):
            self.assertTrue(is_readonly())

    def test_readonly_set_to_0(self):
        """EDGE_READONLY=0 does not enable readonly mode."""
        with patch.dict(os.environ, {"EDGE_READONLY": "0"}):
            self.assertFalse(is_readonly())

    def test_readonly_case_insensitive(self):
        """EDGE_READONLY is case insensitive."""
        with patch.dict(os.environ, {"EDGE_READONLY": "TRUE"}):
            self.assertTrue(is_readonly())


class TestLoadJunctionStateReadonly(unittest.TestCase):
    """Tests for load_junction_state with readonly parameter."""

    def setUp(self):
        """Create a temp directory for state files."""
        self.temp_dir = tempfile.mkdtemp()
        self.state_dir = Path(self.temp_dir) / ".claude" / "state"
        self.state_dir.mkdir(parents=True)
        self.state_file = self.state_dir / "junction_state.json"
        self.legacy_file = self.state_dir / "dispatch_state.json"

    def tearDown(self):
        """Clean up temp directory."""
        import shutil
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    @patch("junction_utils.get_state_dir")
    def test_load_returns_tuple(self, mock_get_state_dir):
        """load_junction_state returns (state, warning) tuple."""
        mock_get_state_dir.return_value = self.state_dir
        state, warning = load_junction_state(readonly=True)
        self.assertIsInstance(state, dict)
        self.assertIn("pending", state)
        self.assertIsNone(warning)

    @patch("junction_utils.load_yaml_state")
    @patch("junction_utils.get_state_dir")
    def test_load_readonly_skips_legacy_migration(self, mock_get_state_dir, mock_load_yaml):
        """Readonly mode skips legacy migration."""
        mock_get_state_dir.return_value = self.state_dir
        mock_load_yaml.return_value = None  # Force JSON fallback path

        # Create legacy pending junction
        self.legacy_file.write_text(json.dumps({
            "pending_junction": True,
            "junction_type": "test_type",
            "junction_reason": "test reason"
        }))

        state, warning = load_junction_state(readonly=True)

        # Should detect legacy but not migrate (warning returned)
        self.assertIn("pending", state)
        self.assertIsNotNone(warning)
        self.assertIn("Read-only mode", warning)
        self.assertIn("legacy", warning.lower())

    @patch("junction_utils.load_yaml_state")
    @patch("junction_utils.get_state_dir")
    def test_load_not_readonly_does_migrate(self, mock_get_state_dir, mock_load_yaml):
        """Non-readonly mode does migrate legacy state (JSON fallback)."""
        mock_get_state_dir.return_value = self.state_dir
        mock_load_yaml.return_value = None  # Force JSON fallback

        # Create legacy pending junction
        self.legacy_file.write_text(json.dumps({
            "pending_junction": True,
            "junction_type": "test_type",
            "junction_reason": "test reason"
        }))

        state, warning = load_junction_state(readonly=False)

        # Should migrate (no warning)
        self.assertIsNone(warning)
        # State file should exist after migration
        self.assertTrue(self.state_file.exists())


class TestSaveJunctionStateReadonly(unittest.TestCase):
    """Tests for save_junction_state with readonly parameter."""

    def setUp(self):
        """Create a temp directory for state files."""
        self.temp_dir = tempfile.mkdtemp()
        self.state_dir = Path(self.temp_dir) / ".claude" / "state"
        self.state_dir.mkdir(parents=True)
        self.state_file = self.state_dir / "junction_state.json"

    def tearDown(self):
        """Clean up temp directory."""
        import shutil
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    @patch("junction_utils.get_state_dir")
    def test_save_readonly_returns_warning(self, mock_get_state_dir):
        """Readonly mode returns warning without saving."""
        mock_get_state_dir.return_value = self.state_dir
        state = _default_state()
        warning = save_junction_state(state, readonly=True)
        self.assertIsNotNone(warning)
        self.assertIn("Read-only mode", warning)
        self.assertFalse(self.state_file.exists())

    @patch("junction_utils.load_yaml_state")
    @patch("junction_utils.get_state_dir")
    def test_save_not_readonly_saves(self, mock_get_state_dir, mock_load_yaml):
        """Non-readonly mode saves state (JSON fallback when no YAML runtime)."""
        mock_get_state_dir.return_value = self.state_dir
        mock_load_yaml.return_value = None  # Force JSON fallback
        state = _default_state()
        warning = save_junction_state(state, readonly=False)
        self.assertIsNone(warning)
        self.assertTrue(self.state_file.exists())


class TestSetPendingJunctionReadonly(unittest.TestCase):
    """Tests for set_pending_junction with readonly parameter."""

    def setUp(self):
        """Create a temp directory for state files."""
        self.temp_dir = tempfile.mkdtemp()
        self.state_dir = Path(self.temp_dir) / ".claude" / "state"
        self.state_dir.mkdir(parents=True)
        self.state_file = self.state_dir / "junction_state.json"

    def tearDown(self):
        """Clean up temp directory."""
        import shutil
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    @patch("junction_utils.get_state_dir")
    def test_set_readonly_returns_warning(self, mock_get_state_dir):
        """Readonly mode returns warning without persisting."""
        mock_get_state_dir.return_value = self.state_dir
        pending, warning = set_pending_junction("test_type", {"key": "value"}, readonly=True)
        self.assertIsNotNone(pending)
        self.assertEqual(pending["type"], "test_type")
        self.assertIsNotNone(warning)
        self.assertIn("Read-only mode", warning)
        self.assertFalse(self.state_file.exists())

    @patch("junction_utils.load_yaml_state")
    @patch("junction_utils.get_state_dir")
    def test_set_not_readonly_persists(self, mock_get_state_dir, mock_load_yaml):
        """Non-readonly mode persists junction (JSON fallback when no YAML runtime)."""
        mock_get_state_dir.return_value = self.state_dir
        mock_load_yaml.return_value = None  # Force JSON fallback
        pending, warning = set_pending_junction("test_type", {"key": "value"}, readonly=False)
        self.assertIsNotNone(pending)
        self.assertIsNone(warning)
        self.assertTrue(self.state_file.exists())

        # Verify persisted
        data = json.loads(self.state_file.read_text())
        self.assertEqual(data["pending"]["type"], "test_type")


class TestClearPendingJunctionReadonly(unittest.TestCase):
    """Tests for clear_pending_junction with readonly parameter."""

    def setUp(self):
        """Create a temp directory for state files."""
        self.temp_dir = tempfile.mkdtemp()
        self.state_dir = Path(self.temp_dir) / ".claude" / "state"
        self.state_dir.mkdir(parents=True)
        self.state_file = self.state_dir / "junction_state.json"

    def tearDown(self):
        """Clean up temp directory."""
        import shutil
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    @patch("junction_utils.load_yaml_state")
    @patch("junction_utils.get_state_dir")
    def test_clear_readonly_returns_warning(self, mock_get_state_dir, mock_load_yaml):
        """Readonly mode returns warning without persisting."""
        mock_get_state_dir.return_value = self.state_dir
        mock_load_yaml.return_value = None  # Force JSON fallback

        # First create a pending junction in non-readonly mode
        set_pending_junction("test_type", {"key": "value"}, readonly=False)

        # Now try to clear in readonly mode
        cleared, warning = clear_pending_junction("approve", readonly=True)
        self.assertIsNotNone(cleared)
        self.assertEqual(cleared["type"], "test_type")
        self.assertIsNotNone(warning)
        self.assertIn("Read-only mode", warning)

        # Junction should still be pending in file
        data = json.loads(self.state_file.read_text())
        self.assertIsNotNone(data["pending"])

    @patch("junction_utils.load_yaml_state")
    @patch("junction_utils.get_state_dir")
    def test_clear_not_readonly_persists(self, mock_get_state_dir, mock_load_yaml):
        """Non-readonly mode persists clear (JSON fallback when no YAML runtime)."""
        mock_get_state_dir.return_value = self.state_dir
        mock_load_yaml.return_value = None  # Force JSON fallback

        # Create a pending junction
        set_pending_junction("test_type", {"key": "value"}, readonly=False)

        # Clear in non-readonly mode
        cleared, warning = clear_pending_junction("approve", readonly=False)
        self.assertIsNotNone(cleared)
        self.assertIsNone(warning)

        # Junction should be cleared in file
        data = json.loads(self.state_file.read_text())
        self.assertIsNone(data["pending"])


class TestGetPendingJunctionReadonly(unittest.TestCase):
    """Tests for get_pending_junction with readonly parameter."""

    def setUp(self):
        """Create a temp directory for state files."""
        self.temp_dir = tempfile.mkdtemp()
        self.state_dir = Path(self.temp_dir) / ".claude" / "state"
        self.state_dir.mkdir(parents=True)
        self.state_file = self.state_dir / "junction_state.json"

    def tearDown(self):
        """Clean up temp directory."""
        import shutil
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    @patch("junction_utils.load_yaml_state")
    @patch("junction_utils.get_state_dir")
    def test_get_defaults_to_readonly(self, mock_get_state_dir, mock_load_yaml):
        """get_pending_junction defaults to readonly mode."""
        mock_get_state_dir.return_value = self.state_dir
        mock_load_yaml.return_value = None  # Force JSON fallback path

        # Create legacy file that would trigger migration if not readonly
        legacy_file = self.state_dir / "dispatch_state.json"
        legacy_file.write_text(json.dumps({
            "pending_junction": True,
            "junction_type": "legacy_type",
            "junction_reason": "legacy reason"
        }))

        # Get should not create the state file (readonly by default)
        pending = get_pending_junction()
        self.assertIsNotNone(pending)
        self.assertEqual(pending["type"], "legacy_type")
        # State file should NOT exist because get is readonly
        self.assertFalse(self.state_file.exists())


class TestEnvVarIntegration(unittest.TestCase):
    """Integration tests for EDGE_READONLY env var."""

    def setUp(self):
        """Create a temp directory for state files."""
        self.temp_dir = tempfile.mkdtemp()
        self.state_dir = Path(self.temp_dir) / ".claude" / "state"
        self.state_dir.mkdir(parents=True)
        self.state_file = self.state_dir / "junction_state.json"

    def tearDown(self):
        """Clean up temp directory."""
        import shutil
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    @patch("junction_utils.load_yaml_state")
    @patch("junction_utils.get_state_dir")
    def test_env_var_blocks_writes(self, mock_get_state_dir, mock_load_yaml):
        """EDGE_READONLY=1 blocks all writes."""
        mock_get_state_dir.return_value = self.state_dir
        mock_load_yaml.return_value = None  # Force JSON fallback

        with patch.dict(os.environ, {"EDGE_READONLY": "1"}):
            # All these should return warnings and not write
            pending, warning = set_pending_junction("test", {"foo": "bar"})
            self.assertIn("Read-only mode", warning)
            self.assertFalse(self.state_file.exists())


if __name__ == "__main__":
    unittest.main()
