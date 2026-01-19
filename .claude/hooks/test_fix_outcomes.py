#!/usr/bin/env python3
"""
Tests for fix_outcomes.py - Fix Outcome Tracking (Phase 9)
"""
import json
import os
import sys
import tempfile
import unittest
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import patch, MagicMock

# Add hooks directory to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from fix_outcomes import (
    # Command matching
    normalize_command,
    get_base_command,
    get_command_target,
    command_matches_fix,
    # Data structures
    FixOutcome,
    FixEffectiveness,
    # Tracking
    track_fix_surfaced,
    track_command_after_fix,
    generate_outcome_id,
    # Storage
    load_outcomes,
    _get_outcomes_path,
    _save_outcome,
    _store_pending_outcome,
    _get_pending_outcome,
    _clear_pending_outcome,
    get_pending_fix_signature,
    # Analysis
    analyze_fix_outcomes,
)


class TestNormalizeCommand(unittest.TestCase):
    """Tests for command normalization."""

    def test_strips_whitespace(self):
        """Whitespace should be stripped."""
        self.assertEqual(normalize_command("  pip install requests  "), "pip install requests")

    def test_normalizes_pip3(self):
        """pip3 should normalize to pip."""
        self.assertEqual(normalize_command("pip3 install requests"), "pip install requests")

    def test_normalizes_python3(self):
        """python3 should normalize to python."""
        self.assertEqual(normalize_command("python3 script.py"), "python script.py")

    def test_removes_sudo(self):
        """sudo prefix should be removed."""
        self.assertEqual(normalize_command("sudo pip install requests"), "pip install requests")

    def test_normalizes_npm_alias(self):
        """npm i should normalize to npm install."""
        self.assertEqual(normalize_command("npm i express"), "npm install express")

    def test_lowercase(self):
        """Command should be lowercased."""
        self.assertEqual(normalize_command("PIP INSTALL Requests"), "pip install requests")

    def test_empty_string(self):
        """Empty string should return empty."""
        self.assertEqual(normalize_command(""), "")


class TestGetBaseCommand(unittest.TestCase):
    """Tests for base command extraction."""

    def test_pip_install(self):
        """Should extract 'pip install' as base."""
        self.assertEqual(get_base_command("pip install requests"), "pip install")

    def test_npm_install(self):
        """Should extract 'npm install' as base."""
        self.assertEqual(get_base_command("npm install express"), "npm install")

    def test_git_pull(self):
        """Should extract 'git pull' as base."""
        self.assertEqual(get_base_command("git pull origin main"), "git pull")

    def test_simple_command(self):
        """Simple command returns just the command."""
        self.assertEqual(get_base_command("ls -la"), "ls")

    def test_empty_string(self):
        """Empty string returns empty."""
        self.assertEqual(get_base_command(""), "")


class TestGetCommandTarget(unittest.TestCase):
    """Tests for command target extraction."""

    def test_pip_install_target(self):
        """Should extract package name."""
        self.assertEqual(get_command_target("pip install requests"), "requests")

    def test_version_stripped(self):
        """Version specifiers should be stripped."""
        self.assertEqual(get_command_target("pip install requests==2.28.0"), "requests")

    def test_version_gte(self):
        """Greater-than version should be stripped."""
        self.assertEqual(get_command_target("pip install requests>=2.0"), "requests")

    def test_extras_stripped(self):
        """Extras in brackets should be stripped."""
        self.assertEqual(get_command_target("pip install requests[security]"), "requests")

    def test_no_target(self):
        """Commands without target return empty."""
        self.assertEqual(get_command_target("git pull"), "")

    def test_lowercase(self):
        """Target should be lowercased."""
        self.assertEqual(get_command_target("pip install Requests"), "requests")


class TestCommandMatchesFix(unittest.TestCase):
    """Tests for command matching logic."""

    def test_exact_match(self):
        """Exact match should return True."""
        self.assertTrue(command_matches_fix(
            "pip install requests",
            ["pip install requests"]
        ))

    def test_pip3_matches_pip(self):
        """pip3 should match pip."""
        self.assertTrue(command_matches_fix(
            "pip3 install requests",
            ["pip install requests"]
        ))

    def test_version_variation(self):
        """Version variations should match."""
        self.assertTrue(command_matches_fix(
            "pip install requests==2.28.0",
            ["pip install requests"]
        ))

    def test_npm_alias(self):
        """npm i should match npm install."""
        self.assertTrue(command_matches_fix(
            "npm i express",
            ["npm install express"]
        ))

    def test_git_with_args(self):
        """git pull with args should match git pull."""
        self.assertTrue(command_matches_fix(
            "git pull origin main",
            ["git pull"]
        ))

    def test_different_package_no_match(self):
        """Different packages should not match."""
        self.assertFalse(command_matches_fix(
            "pip install flask",
            ["pip install requests"]
        ))

    def test_different_command_no_match(self):
        """Different commands should not match."""
        self.assertFalse(command_matches_fix(
            "ls -la",
            ["pip install requests"]
        ))

    def test_empty_suggested_no_match(self):
        """Empty suggestions should not match."""
        self.assertFalse(command_matches_fix(
            "pip install requests",
            []
        ))

    def test_empty_actual_no_match(self):
        """Empty actual should not match."""
        self.assertFalse(command_matches_fix(
            "",
            ["pip install requests"]
        ))


class TestFixOutcome(unittest.TestCase):
    """Tests for FixOutcome dataclass."""

    def test_to_dict(self):
        """Should serialize to dict correctly."""
        outcome = FixOutcome(
            outcome_id="abc123",
            fix_signature="def456",
            error_signature="test error",
            surfaced_at="2026-01-18T10:00:00",
            surfaced_commands=["pip install requests"],
            followed=True,
            success=True,
        )
        d = outcome.to_dict()
        self.assertEqual(d["outcome_id"], "abc123")
        self.assertEqual(d["followed"], True)
        self.assertEqual(d["success"], True)

    def test_from_dict(self):
        """Should deserialize from dict correctly."""
        d = {
            "outcome_id": "abc123",
            "fix_signature": "def456",
            "error_signature": "test error",
            "surfaced_at": "2026-01-18T10:00:00",
            "surfaced_commands": ["pip install requests"],
            "followed": True,
            "success": True,
        }
        outcome = FixOutcome.from_dict(d)
        self.assertEqual(outcome.outcome_id, "abc123")
        self.assertEqual(outcome.followed, True)
        self.assertEqual(outcome.success, True)

    def test_roundtrip(self):
        """to_dict and from_dict should roundtrip."""
        original = FixOutcome(
            outcome_id="abc123",
            fix_signature="def456",
            error_signature="test error",
            surfaced_at="2026-01-18T10:00:00",
            surfaced_commands=["pip install requests"],
            followed=True,
            success=True,
            followed_command="pip install requests",
            resolution="followed_success"
        )
        restored = FixOutcome.from_dict(original.to_dict())
        self.assertEqual(restored.outcome_id, original.outcome_id)
        self.assertEqual(restored.followed_command, original.followed_command)
        self.assertEqual(restored.resolution, original.resolution)


class TestFixEffectiveness(unittest.TestCase):
    """Tests for FixEffectiveness metrics."""

    def test_follow_rate(self):
        """Follow rate calculation."""
        eff = FixEffectiveness(total_surfaced=10, followed=5)
        self.assertEqual(eff.follow_rate, 0.5)

    def test_success_rate(self):
        """Success rate calculation."""
        eff = FixEffectiveness(followed=10, followed_success=8)
        self.assertEqual(eff.success_rate, 0.8)

    def test_overall_effectiveness(self):
        """Overall effectiveness calculation."""
        eff = FixEffectiveness(total_surfaced=20, followed_success=4)
        self.assertEqual(eff.overall_effectiveness, 0.2)

    def test_zero_division(self):
        """Zero division should return 0."""
        eff = FixEffectiveness()
        self.assertEqual(eff.follow_rate, 0.0)
        self.assertEqual(eff.success_rate, 0.0)
        self.assertEqual(eff.overall_effectiveness, 0.0)

    def test_to_dict(self):
        """to_dict should include rates."""
        eff = FixEffectiveness(total_surfaced=10, followed=5, followed_success=4)
        d = eff.to_dict()
        self.assertEqual(d["follow_rate"], 50.0)
        self.assertEqual(d["success_rate"], 80.0)


class TestGenerateOutcomeId(unittest.TestCase):
    """Tests for outcome ID generation."""

    def test_generates_string(self):
        """Should generate a string ID."""
        oid = generate_outcome_id()
        self.assertIsInstance(oid, str)

    def test_unique_ids(self):
        """Should generate unique IDs."""
        ids = [generate_outcome_id() for _ in range(100)]
        self.assertEqual(len(ids), len(set(ids)))

    def test_length(self):
        """ID should be 12 characters."""
        oid = generate_outcome_id()
        self.assertEqual(len(oid), 12)


class TestPendingOutcome(unittest.TestCase):
    """Tests for pending outcome tracking."""

    def setUp(self):
        """Clear pending before each test."""
        _clear_pending_outcome()

    def test_store_and_get(self):
        """Should store and retrieve pending outcome."""
        outcome = FixOutcome(
            outcome_id="test123",
            fix_signature="sig456",
            error_signature="error",
            surfaced_at=datetime.now().isoformat(),
            surfaced_commands=["pip install requests"]
        )
        _store_pending_outcome(outcome)
        pending = _get_pending_outcome()
        self.assertIsNotNone(pending)
        self.assertEqual(pending.outcome_id, "test123")

    def test_clear(self):
        """Should clear pending outcome."""
        outcome = FixOutcome(
            outcome_id="test123",
            fix_signature="sig456",
            error_signature="error",
            surfaced_at=datetime.now().isoformat(),
            surfaced_commands=["pip install requests"]
        )
        _store_pending_outcome(outcome)
        _clear_pending_outcome()
        self.assertIsNone(_get_pending_outcome())

    def test_get_pending_signature(self):
        """Should return fix signature if pending."""
        outcome = FixOutcome(
            outcome_id="test123",
            fix_signature="sig456",
            error_signature="error",
            surfaced_at=datetime.now().isoformat(),
            surfaced_commands=["pip install requests"]
        )
        _store_pending_outcome(outcome)
        self.assertEqual(get_pending_fix_signature(), "sig456")

    def test_no_pending_signature(self):
        """Should return None if no pending."""
        _clear_pending_outcome()
        self.assertIsNone(get_pending_fix_signature())


class TestTrackFixSurfaced(unittest.TestCase):
    """Tests for fix surfacing tracking."""

    def setUp(self):
        _clear_pending_outcome()

    def test_returns_outcome_id(self):
        """Should return a valid outcome ID."""
        oid = track_fix_surfaced(
            fix_signature="abc123",
            error_signature="test error",
            fix_commands=["pip install requests"]
        )
        self.assertIsInstance(oid, str)
        self.assertEqual(len(oid), 12)

    def test_creates_pending(self):
        """Should create a pending outcome."""
        track_fix_surfaced(
            fix_signature="abc123",
            error_signature="test error",
            fix_commands=["pip install requests"]
        )
        pending = _get_pending_outcome()
        self.assertIsNotNone(pending)
        self.assertEqual(pending.fix_signature, "abc123")


class TestTrackCommandAfterFix(unittest.TestCase):
    """Tests for command tracking after fix surfacing."""

    def setUp(self):
        _clear_pending_outcome()

    def test_no_pending_returns_none(self):
        """Should return None if no pending outcome."""
        result = track_command_after_fix("pip install requests", True)
        self.assertIsNone(result)

    def test_unrelated_command_still_pending(self):
        """Unrelated command should not resolve outcome."""
        track_fix_surfaced(
            fix_signature="abc123",
            error_signature="test error",
            fix_commands=["pip install requests"]
        )
        result = track_command_after_fix("ls -la", True)
        self.assertIsNone(result)
        # Should still be pending
        self.assertIsNotNone(_get_pending_outcome())

    @patch('fix_outcomes._save_outcome')
    @patch('fix_outcomes._boost_fix_confidence')
    def test_matching_success(self, mock_boost, mock_save):
        """Matching successful command should resolve as followed_success."""
        mock_boost.return_value = True
        mock_save.return_value = True

        track_fix_surfaced(
            fix_signature="abc123",
            error_signature="test error",
            fix_commands=["pip install requests"]
        )
        result = track_command_after_fix("pip install requests", True)

        self.assertEqual(result, "followed_success")
        mock_boost.assert_called_once_with("abc123")
        self.assertIsNone(_get_pending_outcome())  # Should be cleared

    @patch('fix_outcomes._save_outcome')
    @patch('fix_outcomes._decay_fix_confidence')
    def test_matching_failure(self, mock_decay, mock_save):
        """Matching failed command should resolve as followed_failure."""
        mock_decay.return_value = True
        mock_save.return_value = True

        track_fix_surfaced(
            fix_signature="abc123",
            error_signature="test error",
            fix_commands=["pip install requests"]
        )
        result = track_command_after_fix("pip install requests", False)

        self.assertEqual(result, "followed_failure")
        mock_decay.assert_called_once_with("abc123")

    @patch('fix_outcomes._save_outcome')
    def test_ignore_after_threshold(self, mock_save):
        """Should mark as ignored after threshold commands."""
        mock_save.return_value = True

        track_fix_surfaced(
            fix_signature="abc123",
            error_signature="test error",
            fix_commands=["pip install requests"]
        )

        # Run 5 unrelated commands (IGNORE_THRESHOLD)
        for _ in range(4):
            result = track_command_after_fix("ls -la", True)
            self.assertIsNone(result)

        # 5th command should trigger ignore
        result = track_command_after_fix("cd /app", True)
        self.assertEqual(result, "ignored")
        self.assertIsNone(_get_pending_outcome())


class TestAnalyzeFixOutcomes(unittest.TestCase):
    """Tests for outcome analysis."""

    def setUp(self):
        """Set up temporary outcomes file."""
        self.temp_dir = tempfile.mkdtemp()
        self.patcher = patch('fix_outcomes._get_outcomes_path')
        self.mock_path = self.patcher.start()
        self.mock_path.return_value = Path(self.temp_dir) / "fix_outcomes.jsonl"

    def tearDown(self):
        self.patcher.stop()
        import shutil
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_empty_outcomes(self):
        """Should return empty effectiveness for no outcomes."""
        eff = analyze_fix_outcomes(days=7)
        self.assertEqual(eff.total_surfaced, 0)

    def test_counts_followed(self):
        """Should count followed outcomes."""
        # Write test outcomes
        path = Path(self.temp_dir) / "fix_outcomes.jsonl"
        outcomes = [
            FixOutcome(
                outcome_id=f"id{i}",
                fix_signature="sig",
                error_signature="error",
                surfaced_at=datetime.now().isoformat(),
                surfaced_commands=["pip install requests"],
                followed=True if i < 3 else False,
                success=True if i < 2 else False,
                resolution="followed_success" if i < 2 else ("followed_failure" if i < 3 else "ignored")
            )
            for i in range(5)
        ]

        with open(path, 'w') as f:
            for o in outcomes:
                f.write(json.dumps(o.to_dict()) + '\n')

        eff = analyze_fix_outcomes(days=7)
        self.assertEqual(eff.total_surfaced, 5)
        self.assertEqual(eff.followed, 3)
        self.assertEqual(eff.followed_success, 2)
        self.assertEqual(eff.ignored, 2)


if __name__ == "__main__":
    unittest.main()
