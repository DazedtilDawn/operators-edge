#!/usr/bin/env python3
"""
Tests for outcome_tracker.py - v7.0 outcome tracking system.
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

import outcome_tracker


class TestCorrelationId(unittest.TestCase):
    """Tests for correlation ID generation."""
    
    def test_generate_correlation_id_format(self):
        """Correlation ID has expected format."""
        cid = outcome_tracker.generate_correlation_id()
        self.assertTrue(cid.startswith("corr_"))
        # Format: corr_YYYYMMDD_HHMMSS_hex
        self.assertRegex(cid, r'^corr_\d{8}_\d{6}_[0-9a-f]{4}$')
    
    def test_generate_correlation_id_unique(self):
        """Consecutive correlation IDs are unique."""
        # Use a set to track IDs - allow for very rare collision due to same-second generation
        ids = set()
        for _ in range(100):
            cid = outcome_tracker.generate_correlation_id()
            ids.add(cid)
        # Allow 1-2 collisions due to same-second + rare hex collision
        self.assertGreaterEqual(len(ids), 98)
    
    def test_store_and_get_pending_correlation(self):
        """Can store and retrieve pending correlations."""
        outcome_tracker.reset_for_testing()
        cid = "test_corr_123"
        data = {"rules_fired": ["rule1"], "file_path": "test.py"}
        
        outcome_tracker.store_pending_correlation(cid, data)
        retrieved = outcome_tracker.get_pending_correlation(cid)
        
        self.assertIsNotNone(retrieved)
        self.assertEqual(retrieved["rules_fired"], ["rule1"])
        self.assertEqual(retrieved["file_path"], "test.py")
        self.assertIn("stored_at", retrieved)
    
    def test_get_pending_correlation_removes(self):
        """Getting a correlation removes it from pending."""
        outcome_tracker.reset_for_testing()
        cid = "test_corr_456"
        outcome_tracker.store_pending_correlation(cid, {"test": True})
        
        # First get should succeed
        self.assertIsNotNone(outcome_tracker.get_pending_correlation(cid))
        # Second get should return None
        self.assertIsNone(outcome_tracker.get_pending_correlation(cid))
    
    def test_get_latest_pending_correlation(self):
        """Can get most recent pending correlation."""
        outcome_tracker.reset_for_testing()
        
        outcome_tracker.store_pending_correlation("old", {"order": 1})
        outcome_tracker.store_pending_correlation("new", {"order": 2})
        
        result = outcome_tracker.get_latest_pending_correlation()
        self.assertIsNotNone(result)
        cid, data = result
        self.assertEqual(cid, "new")
        self.assertEqual(data["order"], 2)
    
    def test_clear_stale_correlations(self):
        """Stale correlations are cleared."""
        outcome_tracker.reset_for_testing()
        
        # Add a correlation with old timestamp
        old_time = (datetime.now() - timedelta(seconds=600)).isoformat()
        outcome_tracker._pending_correlations["stale"] = {
            "stored_at": old_time,
            "data": "old"
        }
        outcome_tracker._pending_correlations["fresh"] = {
            "stored_at": datetime.now().isoformat(),
            "data": "new"
        }
        
        cleared = outcome_tracker.clear_stale_correlations(max_age_seconds=300)
        
        self.assertEqual(cleared, 1)
        self.assertNotIn("stale", outcome_tracker._pending_correlations)
        self.assertIn("fresh", outcome_tracker._pending_correlations)


class TestSurfaceEventLogging(unittest.TestCase):
    """Tests for surface event logging."""
    
    def setUp(self):
        outcome_tracker.reset_for_testing()
        self.temp_dir = tempfile.mkdtemp()
        self.original_get_proof_dir = outcome_tracker.get_proof_dir
        outcome_tracker.get_proof_dir = lambda: Path(self.temp_dir)
    
    def tearDown(self):
        outcome_tracker.get_proof_dir = self.original_get_proof_dir
        import shutil
        shutil.rmtree(self.temp_dir, ignore_errors=True)
    
    def test_log_surface_event_stores_correlation(self):
        """Surface event stores data for correlation."""
        cid = "surf_123"
        outcome_tracker.log_surface_event(
            correlation_id=cid,
            file_path="app.py",
            rules_fired=["python-shebang"],
            context_shown=["Use python3"],
            tool_name="Write"
        )
        
        # Should be stored for correlation
        data = outcome_tracker.get_pending_correlation(cid)
        self.assertIsNotNone(data)
        self.assertEqual(data["rules_fired"], ["python-shebang"])
    
    def test_log_surface_event_writes_to_log(self):
        """Surface event is written to log file."""
        outcome_tracker.log_surface_event(
            correlation_id="log_test",
            file_path="test.py",
            rules_fired=["rule1"],
            context_shown=[],
            tool_name="Edit"
        )
        
        log_path = outcome_tracker.get_outcome_log_path()
        self.assertTrue(log_path.exists())
        
        content = log_path.read_text()
        event = json.loads(content.strip())
        self.assertEqual(event["type"], "surface")
        self.assertEqual(event["correlation_id"], "log_test")


class TestOutcomeEventLogging(unittest.TestCase):
    """Tests for outcome event logging."""
    
    def setUp(self):
        outcome_tracker.reset_for_testing()
        self.temp_dir = tempfile.mkdtemp()
        self.original_get_proof_dir = outcome_tracker.get_proof_dir
        outcome_tracker.get_proof_dir = lambda: Path(self.temp_dir)
    
    def tearDown(self):
        outcome_tracker.get_proof_dir = self.original_get_proof_dir
        import shutil
        shutil.rmtree(self.temp_dir, ignore_errors=True)
    
    def test_log_outcome_event_correlates_with_surface(self):
        """Outcome event includes data from correlated surface event."""
        cid = "corr_test"
        
        # First log surface
        outcome_tracker.log_surface_event(
            correlation_id=cid,
            file_path="module.py",
            rules_fired=["policy-enforcement"],
            context_shown=["Context A"],
            tool_name="Write"
        )
        
        # Then log outcome
        outcome_tracker.log_outcome_event(
            correlation_id=cid,
            success=True,
            tool_name="Write",
            was_overridden=False
        )
        
        # Check the log
        log_path = outcome_tracker.get_outcome_log_path()
        lines = log_path.read_text().strip().split("\n")
        self.assertEqual(len(lines), 2)
        
        outcome = json.loads(lines[1])
        self.assertEqual(outcome["type"], "outcome")
        self.assertEqual(outcome["rules_fired"], ["policy-enforcement"])
        self.assertEqual(outcome["file_path"], "module.py")
    
    def test_log_outcome_event_updates_rule_stats(self):
        """Outcome event updates rule statistics."""
        cid = "stats_test"
        
        outcome_tracker.log_surface_event(
            correlation_id=cid,
            file_path="test.py",
            rules_fired=["test-rule"],
            context_shown=[],
            tool_name="Write"
        )
        
        outcome_tracker.log_outcome_event(
            correlation_id=cid,
            success=True,
            tool_name="Write"
        )
        
        stats = outcome_tracker.get_rule_stats("test-rule")
        self.assertIsNotNone(stats)
        self.assertEqual(stats["fired"], 1)
        self.assertEqual(stats["successes"], 1)


class TestRuleStatistics(unittest.TestCase):
    """Tests for rule statistics tracking."""
    
    def setUp(self):
        outcome_tracker.reset_for_testing()
        self.temp_dir = tempfile.mkdtemp()
        self.original_get_proof_dir = outcome_tracker.get_proof_dir
        outcome_tracker.get_proof_dir = lambda: Path(self.temp_dir)
    
    def tearDown(self):
        outcome_tracker.get_proof_dir = self.original_get_proof_dir
        import shutil
        shutil.rmtree(self.temp_dir, ignore_errors=True)
    
    def test_rule_stats_track_successes_and_failures(self):
        """Rule stats correctly track successes and failures."""
        # Simulate multiple outcomes
        for i in range(3):
            cid = f"success_{i}"
            outcome_tracker.log_surface_event(cid, "f.py", ["my-rule"], [], "Write")
            outcome_tracker.log_outcome_event(cid, success=True, tool_name="Write")
        
        for i in range(2):
            cid = f"failure_{i}"
            outcome_tracker.log_surface_event(cid, "f.py", ["my-rule"], [], "Write")
            outcome_tracker.log_outcome_event(cid, success=False, tool_name="Write")
        
        stats = outcome_tracker.get_rule_stats("my-rule")
        self.assertEqual(stats["fired"], 5)
        self.assertEqual(stats["successes"], 3)
        self.assertEqual(stats["failures"], 2)
    
    def test_rule_stats_track_overrides(self):
        """Rule stats track when rules are overridden."""
        cid = "override_test"
        outcome_tracker.log_surface_event(cid, "f.py", ["strict-rule"], [], "Write")
        outcome_tracker.log_outcome_event(
            cid, 
            success=True, 
            tool_name="Write",
            was_overridden=True
        )
        
        stats = outcome_tracker.get_rule_stats("strict-rule")
        self.assertEqual(stats["overrides"], 1)
        self.assertEqual(stats["override_successes"], 1)


class TestEffectivenessAnalysis(unittest.TestCase):
    """Tests for effectiveness calculation."""
    
    def setUp(self):
        outcome_tracker.reset_for_testing()
        self.temp_dir = tempfile.mkdtemp()
        self.original_get_proof_dir = outcome_tracker.get_proof_dir
        outcome_tracker.get_proof_dir = lambda: Path(self.temp_dir)
    
    def tearDown(self):
        outcome_tracker.get_proof_dir = self.original_get_proof_dir
        import shutil
        shutil.rmtree(self.temp_dir, ignore_errors=True)
    
    def test_compute_effectiveness_no_data(self):
        """Effectiveness is None when no data."""
        result = outcome_tracker.compute_rule_effectiveness("nonexistent")
        self.assertIsNone(result)
    
    def test_compute_effectiveness_all_success(self):
        """Effectiveness is 1.0 when all successes, no overrides."""
        for i in range(5):
            cid = f"eff_{i}"
            outcome_tracker.log_surface_event(cid, "f.py", ["perfect-rule"], [], "W")
            outcome_tracker.log_outcome_event(cid, success=True, tool_name="W")
        
        eff = outcome_tracker.compute_rule_effectiveness("perfect-rule")
        self.assertEqual(eff, 1.0)
    
    def test_compute_effectiveness_penalizes_override_success(self):
        """Effectiveness drops when overrides succeed (false positives)."""
        # 5 normal successes
        for i in range(5):
            cid = f"norm_{i}"
            outcome_tracker.log_surface_event(cid, "f.py", ["flakey-rule"], [], "W")
            outcome_tracker.log_outcome_event(cid, success=True, tool_name="W")
        
        # 5 overridden successes (rule was wrong)
        for i in range(5):
            cid = f"over_{i}"
            outcome_tracker.log_surface_event(cid, "f.py", ["flakey-rule"], [], "W")
            outcome_tracker.log_outcome_event(cid, success=True, tool_name="W", was_overridden=True)
        
        eff = outcome_tracker.compute_rule_effectiveness("flakey-rule")
        # (5 successes - 5 override_successes + 0 override_failures) / 10 = 0.0
        self.assertEqual(eff, 0.0)
    
    def test_get_ineffective_rules(self):
        """Can identify ineffective rules."""
        # Create an ineffective rule (all overridden with success)
        for i in range(6):
            cid = f"ineff_{i}"
            outcome_tracker.log_surface_event(cid, "f.py", ["bad-rule"], [], "W")
            outcome_tracker.log_outcome_event(cid, success=True, tool_name="W", was_overridden=True)
        
        ineffective = outcome_tracker.get_ineffective_rules(threshold=0.3, min_fires=5)
        self.assertEqual(len(ineffective), 1)
        self.assertEqual(ineffective[0]["rule_id"], "bad-rule")
    
    def test_get_highly_effective_rules(self):
        """Can identify highly effective rules."""
        # Create an effective rule
        for i in range(6):
            cid = f"good_{i}"
            outcome_tracker.log_surface_event(cid, "f.py", ["good-rule"], [], "W")
            outcome_tracker.log_outcome_event(cid, success=True, tool_name="W")
        
        effective = outcome_tracker.get_highly_effective_rules(threshold=0.8, min_fires=5)
        self.assertEqual(len(effective), 1)
        self.assertEqual(effective[0]["rule_id"], "good-rule")
    
    def test_analyze_rule_impact(self):
        """Impact analysis provides summary and recommendations."""
        # Add some data
        for i in range(3):
            cid = f"imp_{i}"
            outcome_tracker.log_surface_event(cid, "f.py", ["test-rule"], [], "W")
            outcome_tracker.log_outcome_event(cid, success=True, tool_name="W")
        
        impact = outcome_tracker.analyze_rule_impact()
        
        self.assertEqual(impact["total_rules"], 1)
        self.assertEqual(impact["total_fires"], 3)
        self.assertIn("recommendations", impact)


if __name__ == "__main__":
    unittest.main()
