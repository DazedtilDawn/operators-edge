#!/usr/bin/env python3
"""
Tests for dispatch_hook.py - mechanical dispatch mode control.

Tests the core functions for:
- Command parsing
- Dispatch enable/disable
- Junction approval/skip/dismiss
- Status display
"""
import json
import os
import sys
import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from unittest.mock import patch, MagicMock
from io import StringIO

# Add hooks directory to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


class TestParseYoloArgs(unittest.TestCase):
    """Tests for parse_yolo_args() function."""

    def test_parses_on_command(self):
        """parse_yolo_args() should parse 'on' command."""
        from dispatch_hook import parse_yolo_args

        result = parse_yolo_args("/edge-yolo on")

        self.assertEqual(result["command"], "on")

    def test_parses_off_command(self):
        """parse_yolo_args() should parse 'off' command."""
        from dispatch_hook import parse_yolo_args

        result = parse_yolo_args("/edge-yolo off")

        self.assertEqual(result["command"], "off")

    def test_parses_stop_command(self):
        """parse_yolo_args() should parse 'stop' command."""
        from dispatch_hook import parse_yolo_args

        result = parse_yolo_args("/edge-yolo stop")

        self.assertEqual(result["command"], "stop")

    def test_parses_approve_command(self):
        """parse_yolo_args() should parse 'approve' command."""
        from dispatch_hook import parse_yolo_args

        result = parse_yolo_args("/edge-yolo approve")

        self.assertEqual(result["command"], "approve")

    def test_parses_skip_command(self):
        """parse_yolo_args() should parse 'skip' command."""
        from dispatch_hook import parse_yolo_args

        result = parse_yolo_args("/edge-yolo skip")

        self.assertEqual(result["command"], "skip")

    def test_parses_dismiss_with_ttl(self):
        """parse_yolo_args() should parse 'dismiss' with TTL."""
        from dispatch_hook import parse_yolo_args

        result = parse_yolo_args("/edge-yolo dismiss 120")

        self.assertEqual(result["command"], "dismiss")
        self.assertEqual(result["args"], "120")

    def test_defaults_to_status(self):
        """parse_yolo_args() should default to status when no args."""
        from dispatch_hook import parse_yolo_args

        result = parse_yolo_args("/edge-yolo")

        self.assertEqual(result["command"], "status")

    def test_handles_mixed_case(self):
        """parse_yolo_args() should handle mixed case."""
        from dispatch_hook import parse_yolo_args

        result = parse_yolo_args("/Edge-YOLO ON")

        self.assertEqual(result["command"], "on")


class TestHandleOn(unittest.TestCase):
    """Tests for handle_on() function."""

    @patch('dispatch_hook.load_yaml_state')
    @patch('dispatch_hook.start_dispatch')
    def test_starts_dispatch_with_objective(self, mock_start, mock_yaml):
        """handle_on() should start dispatch when objective exists."""
        from dispatch_hook import handle_on

        mock_yaml.return_value = {"objective": "Test objective"}
        mock_start.return_value = {"enabled": True, "state": "running"}

        result = handle_on()

        self.assertIn("DISPATCH MODE: ENABLED", result)
        self.assertIn("Autopilot engaged", result)
        mock_start.assert_called_once()

    @patch('dispatch_hook.load_yaml_state')
    def test_rejects_without_objective(self, mock_yaml):
        """handle_on() should reject start when no objective."""
        from dispatch_hook import handle_on

        mock_yaml.return_value = {}

        result = handle_on()

        self.assertIn("CANNOT START", result)
        self.assertIn("No objective set", result)


class TestHandleOff(unittest.TestCase):
    """Tests for handle_off() function."""

    @patch('dispatch_hook.load_dispatch_state')
    @patch('dispatch_hook.stop_dispatch')
    def test_stops_dispatch(self, mock_stop, mock_load):
        """handle_off() should stop dispatch mode."""
        from dispatch_hook import handle_off

        mock_load.return_value = {
            "iteration": 10,
            "stats": {"junctions_hit": 2, "objectives_completed": 1}
        }
        mock_stop.return_value = {"enabled": False}

        result = handle_off()

        self.assertIn("DISPATCH MODE: DISABLED", result)
        self.assertIn("Iterations: 10", result)
        self.assertIn("Junctions hit: 2", result)
        mock_stop.assert_called_once()


class TestHandleApprove(unittest.TestCase):
    """Tests for handle_approve() function."""

    @patch('dispatch_hook.get_pending_junction')
    @patch('dispatch_hook.clear_pending_junction')
    @patch('dispatch_hook.load_dispatch_state')
    @patch('dispatch_hook.save_dispatch_state')
    def test_approves_junction(self, mock_save, mock_load, mock_clear, mock_get):
        """handle_approve() should clear junction and continue."""
        from dispatch_hook import handle_approve

        mock_get.return_value = {"type": "irreversible", "id": "test-id"}
        mock_clear.return_value = ({"type": "irreversible"}, None)
        mock_load.return_value = {"state": "junction"}

        message, should_continue = handle_approve()

        self.assertIn("JUNCTION APPROVED", message)
        self.assertTrue(should_continue)

    @patch('dispatch_hook.get_pending_junction')
    def test_handles_no_junction(self, mock_get):
        """handle_approve() should handle missing junction."""
        from dispatch_hook import handle_approve

        mock_get.return_value = None

        message, should_continue = handle_approve()

        self.assertIn("No pending junction", message)
        self.assertTrue(should_continue)


class TestHandleSkip(unittest.TestCase):
    """Tests for handle_skip() function."""

    @patch('dispatch_hook.get_pending_junction')
    @patch('dispatch_hook.clear_pending_junction')
    @patch('dispatch_hook.load_dispatch_state')
    @patch('dispatch_hook.save_dispatch_state')
    def test_skips_junction(self, mock_save, mock_load, mock_clear, mock_get):
        """handle_skip() should skip junction."""
        from dispatch_hook import handle_skip

        mock_get.return_value = {"type": "ambiguous"}
        mock_clear.return_value = ({"type": "ambiguous"}, None)
        mock_load.return_value = {"state": "junction"}

        message, should_continue = handle_skip()

        self.assertIn("ACTION SKIPPED", message)
        self.assertTrue(should_continue)


class TestHandleDismiss(unittest.TestCase):
    """Tests for handle_dismiss() function."""

    @patch('dispatch_hook.get_pending_junction')
    @patch('dispatch_hook.clear_pending_junction')
    @patch('dispatch_hook.load_dispatch_state')
    @patch('dispatch_hook.save_dispatch_state')
    def test_dismisses_with_default_ttl(self, mock_save, mock_load, mock_clear, mock_get):
        """handle_dismiss() should dismiss with default TTL."""
        from dispatch_hook import handle_dismiss

        mock_get.return_value = {"type": "external"}
        mock_clear.return_value = ({"type": "external"}, None)
        mock_load.return_value = {"state": "junction"}

        message, should_continue = handle_dismiss()

        self.assertIn("JUNCTION DISMISSED", message)
        self.assertIn("60 minutes", message)
        self.assertTrue(should_continue)

    @patch('dispatch_hook.get_pending_junction')
    @patch('dispatch_hook.clear_pending_junction')
    @patch('dispatch_hook.load_dispatch_state')
    @patch('dispatch_hook.save_dispatch_state')
    def test_dismisses_with_custom_ttl(self, mock_save, mock_load, mock_clear, mock_get):
        """handle_dismiss() should dismiss with custom TTL."""
        from dispatch_hook import handle_dismiss

        mock_get.return_value = {"type": "external"}
        mock_clear.return_value = ({"type": "external"}, None)
        mock_load.return_value = {"state": "junction"}

        message, should_continue = handle_dismiss("120")

        self.assertIn("120 minutes", message)

    def test_rejects_invalid_ttl(self):
        """handle_dismiss() should reject invalid TTL."""
        from dispatch_hook import handle_dismiss

        message, should_continue = handle_dismiss("not-a-number")

        self.assertIn("Invalid TTL", message)
        self.assertFalse(should_continue)

    def test_rejects_negative_ttl(self):
        """handle_dismiss() should reject negative TTL."""
        from dispatch_hook import handle_dismiss

        message, should_continue = handle_dismiss("-5")

        self.assertIn("TTL must be positive", message)
        self.assertFalse(should_continue)


class TestFormatDispatchStatus(unittest.TestCase):
    """Tests for format_dispatch_status() function."""

    @patch('dispatch_hook.get_dispatch_status')
    def test_shows_disabled_status(self, mock_status):
        """format_dispatch_status() should show disabled state."""
        from dispatch_hook import format_dispatch_status

        mock_status.return_value = {
            "enabled": False,
            "state": "idle",
            "iteration": 0,
            "stats": {"junctions_hit": 0},
        }

        result = format_dispatch_status()

        self.assertIn("Mode: DISABLED", result)

    @patch('dispatch_hook.get_dispatch_status')
    def test_shows_enabled_status(self, mock_status):
        """format_dispatch_status() should show enabled state."""
        from dispatch_hook import format_dispatch_status

        mock_status.return_value = {
            "enabled": True,
            "state": "running",
            "objective": "Test objective",
            "plan_steps": 5,
            "completed_steps": 2,
            "iteration": 10,
            "stats": {"junctions_hit": 3},
        }

        result = format_dispatch_status()

        self.assertIn("Mode: ENABLED", result)
        self.assertIn("State: RUNNING", result)
        self.assertIn("Iterations: 10", result)

    @patch('dispatch_hook.get_dispatch_status')
    def test_shows_junction_info(self, mock_status):
        """format_dispatch_status() should show junction details."""
        from dispatch_hook import format_dispatch_status

        mock_status.return_value = {
            "enabled": True,
            "state": "junction",
            "junction": {
                "type": "irreversible",
                "reason": "git push detected",
            },
            "iteration": 5,
            "stats": {"junctions_hit": 1},
        }

        result = format_dispatch_status()

        self.assertIn("JUNCTION: irreversible", result)
        self.assertIn("/edge-yolo approve", result)


if __name__ == '__main__':
    unittest.main()
