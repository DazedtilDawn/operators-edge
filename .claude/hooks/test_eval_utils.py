#!/usr/bin/env python3
"""
Tests for eval_utils.py - eval core utilities.
"""
import os
import sys
import unittest

# Add hooks directory to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


class TestEvalUtilsDiff(unittest.TestCase):
    def test_compute_state_diff_counts(self):
        from eval_utils import compute_state_diff

        before = {
            "objective": "A",
            "plan": [{"description": "x"}],
            "current_step": 1,
            "extra": {"x": 1},
        }
        after = {
            "objective": "B",
            "plan": [{"description": "x"}, {"description": "y"}],
            "current_step": 1,
        }

        diff = compute_state_diff(before, after, max_changes=50)
        self.assertEqual(diff["summary"]["removed"], 1)
        self.assertEqual(diff["summary"]["added"], 1)
        self.assertGreaterEqual(diff["summary"]["changed"], 1)


class TestEvalUtilsInvariants(unittest.TestCase):
    def test_schema_validation_fails_when_missing_keys(self):
        from eval_utils import run_invariant_checks

        invariants = [{"id": "INV-01"}]
        before = {"objective": "A", "plan": [], "current_step": 1}
        after = {"objective": "A", "plan": []}
        diff = {"changes": [], "summary": {}, "truncated": False}
        results = run_invariant_checks(invariants, before, after, diff, {})
        self.assertEqual(len(results["failed"]), 1)
        self.assertEqual(results["failed"][0]["id"], "INV-01")

    def test_no_silent_deletions(self):
        from eval_utils import compute_state_diff, run_invariant_checks

        before = {"objective": "A", "plan": [], "current_step": 1, "extra": 1}
        after = {"objective": "A", "plan": [], "current_step": 1}
        diff = compute_state_diff(before, after, max_changes=50)

        invariants = [{"id": "INV-02"}]
        results = run_invariant_checks(invariants, before, after, diff, {})
        self.assertEqual(len(results["failed"]), 1)

        allow_config = {"allow_deletions": ["extra"]}
        results_allowed = run_invariant_checks(invariants, before, after, diff, allow_config)
        self.assertEqual(len(results_allowed["failed"]), 0)
        self.assertEqual(len(results_allowed["passed"]), 1)

    def test_expected_changes_only(self):
        from eval_utils import compute_state_diff, run_invariant_checks

        before = {"objective": "A", "plan": [], "current_step": 1}
        after = {"objective": "B", "plan": [], "current_step": 1}
        diff = compute_state_diff(before, after, max_changes=50)

        invariants = [{"id": "INV-05"}]
        fail_results = run_invariant_checks(invariants, before, after, diff, {"expected_changes": []})
        self.assertEqual(len(fail_results["skipped"]), 1)

        pass_results = run_invariant_checks(invariants, before, after, diff, {"expected_changes": ["objective"]})
        self.assertEqual(len(pass_results["failed"]), 0)
        self.assertEqual(len(pass_results["passed"]), 1)


import tempfile
import shutil
from pathlib import Path


class TestAutoMismatch(unittest.TestCase):
    """Tests for auto-mismatch on eval failure (v3.9.8)."""

    def test_create_mismatch_from_eval_with_failures(self):
        """Should create a mismatch dict from eval entry with failures."""
        from eval_utils import create_mismatch_from_eval

        eval_entry = {
            "invariants_failed": ["INV-02"],
            "tool": "Edit",
            "snapshots": {"diff": ".proof/evals/run-01/diff.json"},
            "diff_summary": {"added": 1, "removed": 2, "changed": 0},
            "timestamp": "2026-01-10T12:00:00"
        }
        mismatch = create_mismatch_from_eval(eval_entry)

        self.assertIsNotNone(mismatch)
        self.assertIn("INV-02", mismatch["actual"])
        self.assertEqual(mismatch["status"], "unresolved")
        self.assertEqual(mismatch["source"], "eval_auto")
        self.assertIn("Edit", mismatch["expected"])

    def test_create_mismatch_from_eval_no_failures(self):
        """Should return None when no invariants failed."""
        from eval_utils import create_mismatch_from_eval

        eval_entry = {"invariants_failed": [], "tool": "Edit"}
        result = create_mismatch_from_eval(eval_entry)
        self.assertIsNone(result)

    def test_create_mismatch_from_eval_multiple_failures(self):
        """Should include all failed invariants in mismatch."""
        from eval_utils import create_mismatch_from_eval

        eval_entry = {
            "invariants_failed": ["INV-01", "INV-02", "INV-05"],
            "tool": "Write",
            "snapshots": {},
            "diff_summary": {},
        }
        mismatch = create_mismatch_from_eval(eval_entry)

        self.assertIn("INV-01", mismatch["actual"])
        self.assertIn("INV-02", mismatch["actual"])
        self.assertIn("INV-05", mismatch["actual"])

    def test_mismatch_includes_diff_summary(self):
        """Should include diff summary in context."""
        from eval_utils import create_mismatch_from_eval

        eval_entry = {
            "invariants_failed": ["INV-02"],
            "tool": "Edit",
            "snapshots": {},
            "diff_summary": {"added": 5, "removed": 3, "changed": 2},
        }
        mismatch = create_mismatch_from_eval(eval_entry)

        self.assertIn("+5", mismatch["context"])
        self.assertIn("-3", mismatch["context"])
        self.assertIn("~2", mismatch["context"])

    def test_mismatch_dedup_check(self):
        """Should detect duplicate mismatches in content."""
        from eval_utils import _mismatch_exists

        content = 'mismatches:\n  - actual: "Invariant(s) failed: INV-02"\n'
        mismatch = {"actual": "Invariant(s) failed: INV-02"}

        self.assertTrue(_mismatch_exists(content, mismatch))

    def test_mismatch_dedup_no_match(self):
        """Should not detect false duplicate."""
        from eval_utils import _mismatch_exists

        content = 'mismatches:\n  - actual: "Invariant(s) failed: INV-01"\n'
        mismatch = {"actual": "Invariant(s) failed: INV-02"}

        self.assertFalse(_mismatch_exists(content, mismatch))


class TestSnapshotRetention(unittest.TestCase):
    """Tests for snapshot retention functions (v3.9.8)."""

    def test_get_snapshot_stats_empty(self):
        """Should return empty stats when no evals directory."""
        from eval_utils import get_snapshot_stats
        from unittest.mock import patch

        with patch('eval_utils.get_eval_base_dir') as mock_dir:
            mock_dir.return_value = Path("/nonexistent/path")
            stats = get_snapshot_stats()
            self.assertEqual(stats["total_runs"], 0)
            self.assertEqual(stats["total_size_bytes"], 0)
            self.assertIsNone(stats["oldest_date"])

    def test_cleanup_old_snapshots_empty(self):
        """Should handle empty evals directory gracefully."""
        from eval_utils import cleanup_old_snapshots
        from unittest.mock import patch

        with patch('eval_utils.get_eval_base_dir') as mock_dir:
            mock_dir.return_value = Path("/nonexistent/path")
            result = cleanup_old_snapshots(dry_run=True)
            self.assertEqual(result["deleted"], 0)
            self.assertEqual(result["kept"], 0)

    def test_get_run_age_days(self):
        """Should calculate run age from directory name."""
        from eval_utils import _get_run_age_days
        from datetime import datetime, timedelta

        # Create a fake run dir with today's date
        today = datetime.now().strftime("%Y-%m-%d")
        fake_run = Path(f"/fake/{today}/run-01")
        age = _get_run_age_days(fake_run)
        self.assertEqual(age, 0)

        # Yesterday
        yesterday = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")
        fake_run_old = Path(f"/fake/{yesterday}/run-01")
        age_old = _get_run_age_days(fake_run_old)
        self.assertEqual(age_old, 1)

    def test_default_retention_values(self):
        """Should have sensible default retention values."""
        from eval_utils import DEFAULT_RETENTION_DAYS, FAILURE_RETENTION_DAYS

        self.assertEqual(DEFAULT_RETENTION_DAYS, 7)
        self.assertEqual(FAILURE_RETENTION_DAYS, 30)


if __name__ == "__main__":
    unittest.main()
