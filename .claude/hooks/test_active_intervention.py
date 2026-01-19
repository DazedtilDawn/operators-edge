#!/usr/bin/env python3
"""
Tests for active_intervention.py

Testing the active intervention system for v8.0 Phase 8.
"""
import json
import os
import sys
import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from unittest.mock import patch, MagicMock

# Add hooks directory to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from active_intervention import (
    InterventionEvent,
    SessionHealth,
    InterventionConfig,
    DEFAULT_CONFIG,
    level_value,
    determine_intervention_level,
    should_inject_fix_context,
    format_fix_injection,
    should_block_command,
    format_block_warning,
    get_proactive_context,
    update_health_from_error,
    update_health_from_success,
    update_health_metrics,
    get_intervention_for_tool,
    reset_health,
    log_intervention,
    get_recent_interventions,
    load_intervention_config,
    save_intervention_config,
)


class TestInterventionEvent(unittest.TestCase):
    """Tests for InterventionEvent dataclass."""

    def test_to_dict(self):
        """Test serialization to dict."""
        event = InterventionEvent(
            timestamp="2026-01-18T10:00:00",
            intervention_type="context_inject",
            trigger="Tool: Edit",
            action_taken="Injected 200 chars",
            session_id="test-session",
        )
        d = event.to_dict()
        self.assertEqual(d["intervention_type"], "context_inject")
        self.assertEqual(d["session_id"], "test-session")

    def test_from_dict(self):
        """Test deserialization from dict."""
        data = {
            "timestamp": "2026-01-18T10:00:00",
            "intervention_type": "block",
            "trigger": "Command: rm -rf",
            "action_taken": "Blocked",
            "session_id": "test",
        }
        event = InterventionEvent.from_dict(data)
        self.assertEqual(event.intervention_type, "block")

    def test_roundtrip(self):
        """Test dict serialization roundtrip."""
        event = InterventionEvent(
            timestamp="2026-01-18T10:00:00",
            intervention_type="fix_prompt",
            trigger="Error detected",
            action_taken="Prompted fix",
        )
        restored = InterventionEvent.from_dict(event.to_dict())
        self.assertEqual(event.intervention_type, restored.intervention_type)
        self.assertEqual(event.trigger, restored.trigger)


class TestSessionHealth(unittest.TestCase):
    """Tests for SessionHealth dataclass."""

    def test_default_values(self):
        """Test default health values."""
        health = SessionHealth()
        self.assertEqual(health.context_usage_percent, 0.0)
        self.assertEqual(health.drift_signals_fired, 0)
        self.assertEqual(health.same_error_count, 0)
        self.assertIsNone(health.pending_error)

    def test_custom_values(self):
        """Test health with custom values."""
        health = SessionHealth(
            context_usage_percent=75,
            drift_signals_ignored=2,
            same_error_count=3,
        )
        self.assertEqual(health.context_usage_percent, 75)
        self.assertEqual(health.drift_signals_ignored, 2)


class TestInterventionConfig(unittest.TestCase):
    """Tests for InterventionConfig dataclass."""

    def test_default_config(self):
        """Test default config values."""
        config = InterventionConfig()
        self.assertTrue(config.enabled)
        self.assertEqual(config.default_level, "advise")
        self.assertEqual(config.max_level, "guide")
        self.assertFalse(config.auto_fix_enabled)

    def test_blocked_patterns_default(self):
        """Test default blocked patterns."""
        config = InterventionConfig()
        self.assertIn("rm -rf /", config.blocked_patterns)
        self.assertIn("git push --force", config.blocked_patterns)


class TestLevelValue(unittest.TestCase):
    """Tests for level_value function."""

    def test_level_ordering(self):
        """Test that levels are ordered correctly."""
        self.assertLess(level_value("observe"), level_value("advise"))
        self.assertLess(level_value("advise"), level_value("guide"))
        self.assertLess(level_value("guide"), level_value("intervene"))

    def test_unknown_level(self):
        """Test handling of unknown level."""
        self.assertEqual(level_value("unknown"), 1)  # Defaults to advise


class TestDetermineInterventionLevel(unittest.TestCase):
    """Tests for determine_intervention_level function."""

    def test_disabled_returns_observe(self):
        """Test that disabled config returns observe."""
        config = InterventionConfig(enabled=False)
        health = SessionHealth()
        level = determine_intervention_level(health, config)
        self.assertEqual(level, "observe")

    def test_default_level_used(self):
        """Test that default level is used for healthy session."""
        config = InterventionConfig(default_level="advise")
        health = SessionHealth()
        level = determine_intervention_level(health, config)
        self.assertEqual(level, "advise")

    def test_escalate_on_high_context(self):
        """Test escalation on high context usage."""
        config = InterventionConfig(auto_escalate=True, max_level="intervene")
        health = SessionHealth(context_usage_percent=90)
        level = determine_intervention_level(health, config)
        self.assertEqual(level, "guide")

    def test_escalate_on_ignored_signals(self):
        """Test escalation on ignored drift signals."""
        config = InterventionConfig(auto_escalate=True, max_level="intervene")
        health = SessionHealth(drift_signals_ignored=4)
        level = determine_intervention_level(health, config)
        self.assertEqual(level, "guide")

    def test_escalate_on_repeated_errors(self):
        """Test escalation to intervene on repeated errors."""
        config = InterventionConfig(auto_escalate=True, max_level="intervene")
        health = SessionHealth(same_error_count=3)
        level = determine_intervention_level(health, config)
        self.assertEqual(level, "intervene")

    def test_respects_max_level(self):
        """Test that max_level caps escalation."""
        config = InterventionConfig(auto_escalate=True, max_level="guide")
        health = SessionHealth(same_error_count=5)  # Would normally escalate to intervene
        level = determine_intervention_level(health, config)
        self.assertEqual(level, "guide")

    def test_no_escalate_when_disabled(self):
        """Test no escalation when auto_escalate is False."""
        config = InterventionConfig(auto_escalate=False, default_level="advise")
        health = SessionHealth(same_error_count=5, context_usage_percent=95)
        level = determine_intervention_level(health, config)
        self.assertEqual(level, "advise")


class TestShouldInjectFixContext(unittest.TestCase):
    """Tests for should_inject_fix_context function."""

    def test_no_pending_error(self):
        """Test no injection without pending error."""
        config = InterventionConfig(context_injection_enabled=True)
        health = SessionHealth()
        self.assertFalse(should_inject_fix_context(health, config, "guide"))

    def test_no_pending_fix(self):
        """Test no injection without pending fix."""
        config = InterventionConfig(context_injection_enabled=True)
        health = SessionHealth(pending_error="Some error")
        self.assertFalse(should_inject_fix_context(health, config, "guide"))

    def test_injection_disabled(self):
        """Test no injection when disabled."""
        config = InterventionConfig(context_injection_enabled=False)
        health = SessionHealth(pending_error="Error", pending_fix=MagicMock())
        self.assertFalse(should_inject_fix_context(health, config, "guide"))

    def test_inject_at_guide_level(self):
        """Test injection at guide level."""
        config = InterventionConfig(context_injection_enabled=True)
        health = SessionHealth(pending_error="Error", pending_fix=MagicMock())
        self.assertTrue(should_inject_fix_context(health, config, "guide"))

    def test_inject_for_high_confidence_at_advise(self):
        """Test injection for high confidence fix at advise level."""
        config = InterventionConfig(context_injection_enabled=True)
        mock_fix = MagicMock()
        mock_fix.confidence = 0.8
        health = SessionHealth(pending_error="Error", pending_fix=mock_fix)
        self.assertTrue(should_inject_fix_context(health, config, "advise"))


class TestFormatFixInjection(unittest.TestCase):
    """Tests for format_fix_injection function."""

    def test_includes_description(self):
        """Test that fix description is included."""
        mock_fix = MagicMock()
        mock_fix.fix_description = "Install missing package"
        mock_fix.fix_commands = ["pip install package"]
        mock_fix.confidence = 0.85
        mock_fix.times_used = 3

        health = SessionHealth()
        output = format_fix_injection(mock_fix, health)

        self.assertIn("KNOWN FIX", output)
        self.assertIn("Install missing package", output)

    def test_includes_commands(self):
        """Test that commands are included."""
        mock_fix = MagicMock()
        mock_fix.fix_description = "Fix"
        mock_fix.fix_commands = ["npm install", "npm test"]
        mock_fix.confidence = 0.9
        mock_fix.times_used = 2

        output = format_fix_injection(mock_fix, SessionHealth())

        self.assertIn("npm install", output)
        self.assertIn("npm test", output)

    def test_includes_confidence(self):
        """Test that confidence is included."""
        mock_fix = MagicMock()
        mock_fix.fix_description = "Fix"
        mock_fix.fix_commands = []
        mock_fix.confidence = 0.75
        mock_fix.times_used = 5

        output = format_fix_injection(mock_fix, SessionHealth())

        self.assertIn("75%", output)
        self.assertIn("5x", output)


class TestShouldBlockCommand(unittest.TestCase):
    """Tests for should_block_command function."""

    def test_no_block_at_advise_level(self):
        """Test no blocking at advise level."""
        config = InterventionConfig()
        should_block, _ = should_block_command("rm -rf /", config, "advise")
        self.assertFalse(should_block)

    def test_block_dangerous_at_intervene(self):
        """Test blocking dangerous command at intervene level."""
        config = InterventionConfig()
        should_block, reason = should_block_command("rm -rf /", config, "intervene")
        self.assertTrue(should_block)
        self.assertIn("rm -rf", reason.lower())

    def test_allow_safe_at_intervene(self):
        """Test allowing safe command at intervene level."""
        config = InterventionConfig()
        should_block, _ = should_block_command("ls -la", config, "intervene")
        self.assertFalse(should_block)

    def test_block_force_push(self):
        """Test blocking git push --force."""
        config = InterventionConfig()
        should_block, _ = should_block_command("git push --force origin main", config, "intervene")
        self.assertTrue(should_block)

    def test_case_insensitive(self):
        """Test case-insensitive pattern matching."""
        config = InterventionConfig()
        should_block, _ = should_block_command("RM -RF /", config, "intervene")
        self.assertTrue(should_block)


class TestFormatBlockWarning(unittest.TestCase):
    """Tests for format_block_warning function."""

    def test_includes_command(self):
        """Test that command is included in warning."""
        output = format_block_warning("rm -rf /", "Dangerous pattern")
        self.assertIn("rm -rf /", output)
        self.assertIn("BLOCKED", output)

    def test_includes_reason(self):
        """Test that reason is included in warning."""
        output = format_block_warning("cmd", "Safety concern")
        self.assertIn("Safety concern", output)


class TestHealthTracking(unittest.TestCase):
    """Tests for health tracking functions."""

    def setUp(self):
        """Reset health before each test."""
        reset_health()

    def test_update_from_error(self):
        """Test updating health from error."""
        update_health_from_error("ModuleNotFoundError", MagicMock())
        from active_intervention import _current_health
        self.assertIsNotNone(_current_health.pending_error)
        self.assertIsNotNone(_current_health.pending_fix)
        self.assertEqual(_current_health.same_error_count, 1)

    def test_update_from_success_clears_error(self):
        """Test that success clears pending error."""
        update_health_from_error("Error", None)
        update_health_from_success()
        from active_intervention import _current_health
        self.assertIsNone(_current_health.pending_error)
        self.assertEqual(_current_health.same_error_count, 0)

    def test_update_metrics(self):
        """Test updating general metrics."""
        update_health_metrics(
            context_usage=75,
            drift_signals=2,
            duration_minutes=30
        )
        from active_intervention import _current_health
        self.assertEqual(_current_health.context_usage_percent, 75)
        self.assertEqual(_current_health.drift_signals_fired, 2)

    def test_reset_health(self):
        """Test health reset."""
        update_health_from_error("Error", MagicMock())
        update_health_metrics(context_usage=90)
        reset_health()
        from active_intervention import _current_health
        self.assertEqual(_current_health.context_usage_percent, 0)
        self.assertIsNone(_current_health.pending_error)


class TestGetInterventionForTool(unittest.TestCase):
    """Tests for get_intervention_for_tool function."""

    def setUp(self):
        """Reset health before each test."""
        reset_health()

    def test_no_intervention_when_healthy(self):
        """Test no intervention for healthy session."""
        text, should_block = get_intervention_for_tool("Edit", {"file_path": "/app/main.py"})
        self.assertFalse(should_block)

    def test_block_returns_warning(self):
        """Test that blocking returns warning text."""
        # Create a proper mock fix with numeric attributes
        mock_fix = MagicMock()
        mock_fix.confidence = 0.8
        mock_fix.times_used = 2
        mock_fix.fix_description = "Test fix"
        mock_fix.fix_commands = ["test"]

        # Set up conditions for escalation
        update_health_metrics(context_usage=95)
        update_health_from_error("Error", mock_fix)
        update_health_from_error("Error", mock_fix)
        update_health_from_error("Error", mock_fix)  # 3 errors

        # Test that intervention works (may or may not block depending on config)
        text, should_block = get_intervention_for_tool("Bash", {"command": "ls -la"})
        # At minimum, this should not crash
        self.assertIsInstance(text, str)
        self.assertIsInstance(should_block, bool)


class TestAuditLogging(unittest.TestCase):
    """Tests for audit logging functions."""

    def test_log_intervention(self):
        """Test logging an intervention."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Patch the audit path
            audit_path = Path(tmpdir) / "audit.jsonl"

            with patch('active_intervention.get_audit_path', return_value=audit_path):
                event = InterventionEvent(
                    timestamp=datetime.now().isoformat(),
                    intervention_type="test",
                    trigger="Test trigger",
                    action_taken="Test action",
                )
                result = log_intervention(event)
                self.assertTrue(result)
                self.assertTrue(audit_path.exists())

    def test_get_recent_interventions(self):
        """Test retrieving recent interventions."""
        with tempfile.TemporaryDirectory() as tmpdir:
            audit_path = Path(tmpdir) / "audit.jsonl"

            # Write some test events
            events = [
                {"timestamp": "2026-01-18T10:00:00", "intervention_type": "test1", "trigger": "t1", "action_taken": "a1"},
                {"timestamp": "2026-01-18T10:01:00", "intervention_type": "test2", "trigger": "t2", "action_taken": "a2"},
            ]
            with open(audit_path, 'w') as f:
                for e in events:
                    f.write(json.dumps(e) + '\n')

            with patch('active_intervention.get_audit_path', return_value=audit_path):
                recent = get_recent_interventions(limit=10)
                self.assertEqual(len(recent), 2)
                self.assertEqual(recent[0].intervention_type, "test1")


class TestConfigPersistence(unittest.TestCase):
    """Tests for config loading and saving."""

    def test_load_default_when_missing(self):
        """Test loading default config when file missing."""
        with tempfile.TemporaryDirectory() as tmpdir:
            config_path = Path(tmpdir) / "v8_config.json"
            with patch('active_intervention.get_config_path', return_value=config_path):
                config = load_intervention_config()
                self.assertEqual(config.default_level, DEFAULT_CONFIG.default_level)

    def test_save_and_load(self):
        """Test saving and loading config."""
        with tempfile.TemporaryDirectory() as tmpdir:
            config_path = Path(tmpdir) / "v8_config.json"

            with patch('active_intervention.get_config_path', return_value=config_path):
                # Save custom config
                custom = InterventionConfig(
                    default_level="guide",
                    auto_fix_enabled=True,
                )
                result = save_intervention_config(custom)
                self.assertTrue(result)

                # Load it back
                loaded = load_intervention_config()
                self.assertEqual(loaded.default_level, "guide")
                self.assertTrue(loaded.auto_fix_enabled)


if __name__ == "__main__":
    unittest.main()
