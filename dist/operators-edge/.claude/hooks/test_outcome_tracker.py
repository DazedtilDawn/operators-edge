#!/usr/bin/env python3
"""
Tests for outcome_tracker.py - connecting rules to outcomes.
"""
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from outcome_tracker import (
    generate_correlation_id,
    log_surface_event,
    log_outcome_event,
    get_pending_correlation,
    get_rule_effectiveness,
    get_all_rule_stats,
    get_ineffective_rules,
    get_highly_effective_rules,
    analyze_rule_impact,
    load_outcome_log,
    _pending_correlations,
)


class TestCorrelationIdGeneration(unittest.TestCase):
    """Test correlation ID generation."""

    def test_generates_unique_ids(self):
        """Each call should generate a unique ID."""
        # Generate 10 IDs (fewer to avoid timing collisions in tests)
        ids = [generate_correlation_id() for _ in range(10)]
        self.assertEqual(len(ids), len(set(ids)))

    def test_format_includes_timestamp(self):
        """ID should include timestamp prefix."""
        corr_id = generate_correlation_id()
        self.assertTrue(corr_id.startswith("corr_"))
        # Should have format corr_YYYYMMDD_HHMMSS_xxxx
        parts = corr_id.split("_")
        self.assertEqual(len(parts), 4)


class TestSurfaceEventLogging(unittest.TestCase):
    """Test surface event logging."""

    def setUp(self):
        """Clear pending correlations before each test."""
        _pending_correlations.clear()

    def test_logs_surface_event(self):
        """Surface events should be stored in memory."""
        corr_id = "test_corr_123"
        log_surface_event(
            correlation_id=corr_id,
            file_path="/test/file.py",
            rules_fired=["python-shebang"],
            context_shown=["cochange:test.py"],
            tool_name="Write"
        )

        self.assertIn(corr_id, _pending_correlations)
        event = _pending_correlations[corr_id]
        self.assertEqual(event["file_path"], "/test/file.py")
        self.assertEqual(event["rules_fired"], ["python-shebang"])
        self.assertEqual(event["context_shown"], ["cochange:test.py"])

    def test_multiple_events_tracked(self):
        """Multiple surface events should all be tracked."""
        log_surface_event("corr1", "/file1.py", ["rule1"], [], "Write")
        log_surface_event("corr2", "/file2.py", ["rule2"], [], "Edit")

        self.assertIn("corr1", _pending_correlations)
        self.assertIn("corr2", _pending_correlations)


class TestOutcomeEventLogging(unittest.TestCase):
    """Test outcome event logging."""

    def setUp(self):
        """Clear pending correlations before each test."""
        _pending_correlations.clear()

    def test_outcome_clears_pending(self):
        """Logging an outcome should clear the pending correlation."""
        corr_id = "test_outcome_123"
        log_surface_event(corr_id, "/test/file.py", ["rule1"], [], "Write")
        self.assertIn(corr_id, _pending_correlations)

        log_outcome_event(corr_id, success=True)
        self.assertNotIn(corr_id, _pending_correlations)

    def test_unknown_correlation_handled(self):
        """Logging outcome for unknown correlation should not fail."""
        # Should not raise
        log_outcome_event("unknown_corr", success=False, error_message="Test error")


class TestGetPendingCorrelation(unittest.TestCase):
    """Test pending correlation lookup."""

    def setUp(self):
        """Clear pending correlations before each test."""
        _pending_correlations.clear()

    def test_finds_correlation_by_file(self):
        """Should find correlation ID for a given file path."""
        corr_id = "find_test_123"
        log_surface_event(corr_id, "/test/specific.py", ["rule1"], [], "Write")

        found = get_pending_correlation("/test/specific.py")
        self.assertEqual(found, corr_id)

    def test_returns_none_for_unknown_file(self):
        """Should return None for unknown files."""
        found = get_pending_correlation("/unknown/file.py")
        self.assertIsNone(found)


class TestRuleEffectivenessTracking(unittest.TestCase):
    """Test rule effectiveness statistics."""

    def setUp(self):
        """Use a temporary directory for stats."""
        self.temp_dir = tempfile.mkdtemp()
        self.stats_patcher = patch(
            'outcome_tracker.get_proof_dir',
            return_value=Path(self.temp_dir)
        )
        self.stats_patcher.start()
        _pending_correlations.clear()

    def tearDown(self):
        """Clean up."""
        self.stats_patcher.stop()
        import shutil
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_tracks_rule_fires(self):
        """Should track when rules fire."""
        corr_id = "track_test_1"
        log_surface_event(corr_id, "/test.py", ["python-shebang"], [], "Write")
        log_outcome_event(corr_id, success=True)

        stats = get_rule_effectiveness("python-shebang")
        self.assertIsNotNone(stats)
        self.assertEqual(stats["times_fired"], 1)
        self.assertEqual(stats["times_success"], 1)

    def test_tracks_failures(self):
        """Should track rule outcomes including failures."""
        # Fire and succeed
        corr1 = "success_test"
        log_surface_event(corr1, "/test1.py", ["rule1"], [], "Write")
        log_outcome_event(corr1, success=True)

        # Fire and fail
        corr2 = "fail_test"
        log_surface_event(corr2, "/test2.py", ["rule1"], [], "Write")
        log_outcome_event(corr2, success=False)

        stats = get_rule_effectiveness("rule1")
        self.assertEqual(stats["times_fired"], 2)
        self.assertEqual(stats["times_success"], 1)

    def test_tracks_overrides(self):
        """Should track when users override rules."""
        corr_id = "override_test"
        log_surface_event(corr_id, "/test.py", ["rule1"], [], "Write")
        log_outcome_event(corr_id, success=True, override=True)

        stats = get_rule_effectiveness("rule1")
        self.assertEqual(stats["times_override"], 1)
        self.assertEqual(stats["times_override_success"], 1)

    def test_effectiveness_calculation(self):
        """Should calculate effectiveness based on outcomes."""
        # Scenario: Rule fires 10 times
        # - 6 times followed, succeeded (effective - good advice followed)
        # - 2 times overridden, succeeded (ineffective - unnecessary warning)
        # - 2 times overridden, failed (effective - warning was correct)
        #
        # Formula: (successes - override_successes + override_failures) / fired
        # = (8 - 2 + 2) / 10 = 8/10 = 0.8

        for i in range(6):
            corr = f"follow_{i}"
            log_surface_event(corr, f"/file{i}.py", ["test-rule"], [], "Write")
            log_outcome_event(corr, success=True, override=False)

        for i in range(2):
            corr = f"override_success_{i}"
            log_surface_event(corr, f"/override_s{i}.py", ["test-rule"], [], "Write")
            log_outcome_event(corr, success=True, override=True)

        for i in range(2):
            corr = f"override_fail_{i}"
            log_surface_event(corr, f"/override_f{i}.py", ["test-rule"], [], "Write")
            log_outcome_event(corr, success=False, override=True)

        stats = get_rule_effectiveness("test-rule")
        # Total successes: 8 (6 followed + 2 overridden)
        # Override successes: 2 (these are "false positives" - rule was wrong)
        # Override failures: 2 (rule was right, user ignored it)
        # Effective = 8 - 2 + 2 = 8
        # Effectiveness = 8/10 = 0.8
        self.assertEqual(stats["times_fired"], 10)
        self.assertEqual(stats["times_success"], 8)
        self.assertAlmostEqual(stats["effectiveness"], 0.8, places=2)


class TestRuleAnalysis(unittest.TestCase):
    """Test rule analysis functions."""

    def setUp(self):
        """Use a temporary directory for stats."""
        self.temp_dir = tempfile.mkdtemp()
        self.stats_patcher = patch(
            'outcome_tracker.get_proof_dir',
            return_value=Path(self.temp_dir)
        )
        self.stats_patcher.start()
        _pending_correlations.clear()

    def tearDown(self):
        """Clean up."""
        self.stats_patcher.stop()
        import shutil
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_get_ineffective_rules_requires_samples(self):
        """Should only report ineffective rules with enough samples."""
        # Add a rule with few samples
        for i in range(3):
            corr = f"few_{i}"
            log_surface_event(corr, f"/file{i}.py", ["few-samples"], [], "Write")
            log_outcome_event(corr, success=True, override=True)  # All overridden = 0% effective

        # Should not be reported (< 5 samples)
        ineffective = get_ineffective_rules()
        self.assertEqual(len([r for r in ineffective if r[0] == "few-samples"]), 0)

    def test_get_highly_effective_rules(self):
        """Should identify rules with high effectiveness."""
        # Add a highly effective rule
        for i in range(10):
            corr = f"effective_{i}"
            log_surface_event(corr, f"/file{i}.py", ["good-rule"], [], "Write")
            log_outcome_event(corr, success=True, override=False)

        effective = get_highly_effective_rules(threshold=0.8)
        rule_ids = [r[0] for r in effective]
        self.assertIn("good-rule", rule_ids)

    def test_analyze_rule_impact(self):
        """Should provide overall impact analysis."""
        # Add some data
        for i in range(5):
            corr = f"impact_{i}"
            log_surface_event(corr, f"/file{i}.py", ["impact-rule"], [], "Write")
            log_outcome_event(corr, success=i < 4)  # 4 success, 1 failure

        impact = analyze_rule_impact()
        self.assertEqual(impact["total_rule_fires"], 5)
        self.assertEqual(impact["total_successes"], 4)
        self.assertEqual(impact["rules_tracked"], 1)


class TestOutcomeLog(unittest.TestCase):
    """Test outcome log file operations."""

    def setUp(self):
        """Use a temporary directory for logs."""
        self.temp_dir = tempfile.mkdtemp()
        self.log_patcher = patch(
            'outcome_tracker.get_proof_dir',
            return_value=Path(self.temp_dir)
        )
        self.log_patcher.start()
        _pending_correlations.clear()

    def tearDown(self):
        """Clean up."""
        self.log_patcher.stop()
        import shutil
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_logs_persisted_to_file(self):
        """Events should be persisted to the log file."""
        corr_id = "persist_test"
        log_surface_event(corr_id, "/test.py", ["rule1"], [], "Write")
        log_outcome_event(corr_id, success=True)

        events = load_outcome_log()
        self.assertEqual(len(events), 2)  # surface + outcome
        self.assertEqual(events[0]["type"], "surface")
        self.assertEqual(events[1]["type"], "outcome")

    def test_load_respects_limit(self):
        """Should respect the limit parameter."""
        for i in range(20):
            corr = f"limit_{i}"
            log_surface_event(corr, f"/file{i}.py", ["rule"], [], "Write")

        events = load_outcome_log(limit=5)
        self.assertEqual(len(events), 5)


if __name__ == "__main__":
    unittest.main()
