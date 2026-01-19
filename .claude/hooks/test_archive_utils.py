#!/usr/bin/env python3
"""
Tests for archive_utils.py - archive system, pruning, and entropy management.

Tests the core functions for:
- Writing entries to archive
- Loading and searching archive
- Checking state entropy
- Identifying prunable items
"""
import json
import os
import shutil
import sys
import tempfile
import unittest
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import patch, MagicMock

# Add hooks directory to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


class TestLogToArchive(unittest.TestCase):
    """Tests for log_to_archive() function."""

    @patch('archive_utils.get_archive_file')
    def test_creates_archive_entry(self, mock_get_archive):
        """log_to_archive() should append JSON entry to archive file."""
        from archive_utils import log_to_archive

        with tempfile.TemporaryDirectory() as tmpdir:
            archive_file = Path(tmpdir) / "archive.jsonl"
            mock_get_archive.return_value = archive_file

            log_to_archive("test_type", {"key": "value"})

            content = archive_file.read_text().strip()
            entry = json.loads(content)

            self.assertEqual(entry["type"], "test_type")
            self.assertEqual(entry["key"], "value")
            self.assertIn("timestamp", entry)

    @patch('archive_utils.get_archive_file')
    def test_appends_multiple_entries(self, mock_get_archive):
        """log_to_archive() should append, not overwrite."""
        from archive_utils import log_to_archive

        with tempfile.TemporaryDirectory() as tmpdir:
            archive_file = Path(tmpdir) / "archive.jsonl"
            mock_get_archive.return_value = archive_file

            log_to_archive("type1", {"a": 1})
            log_to_archive("type2", {"b": 2})

            lines = archive_file.read_text().strip().split('\n')
            self.assertEqual(len(lines), 2)


class TestArchiveCompletedStep(unittest.TestCase):
    """Tests for archive_completed_step() function."""

    @patch('archive_utils.log_to_archive')
    def test_archives_step_data(self, mock_log):
        """archive_completed_step() should log step with all fields."""
        from archive_utils import archive_completed_step

        step = {
            'description': 'Test step',
            'proof': 'test proof',
            'expected': 'expected result',
            'actual': 'actual result'
        }

        archive_completed_step(step, 1, "Test objective", "session-123")

        mock_log.assert_called_once()
        call_args = mock_log.call_args
        self.assertEqual(call_args[0][0], "completed_step")
        self.assertEqual(call_args[0][1]["objective"], "Test objective")
        self.assertEqual(call_args[0][1]["step_number"], 1)
        self.assertEqual(call_args[0][1]["description"], "Test step")


class TestLoadArchive(unittest.TestCase):
    """Tests for load_archive() function."""

    @patch('archive_utils.get_archive_file')
    @patch('archive_utils.ARCHIVE_SETTINGS', {"max_archive_entries_to_load": 100})
    def test_loads_all_entries(self, mock_get_archive):
        """load_archive() should return all entries when under limit."""
        from archive_utils import load_archive

        with tempfile.TemporaryDirectory() as tmpdir:
            archive_file = Path(tmpdir) / "archive.jsonl"
            entries = [
                {"type": "step", "n": 1},
                {"type": "step", "n": 2},
                {"type": "step", "n": 3}
            ]
            archive_file.write_text('\n'.join(json.dumps(e) for e in entries))
            mock_get_archive.return_value = archive_file

            result = load_archive()

            self.assertEqual(len(result), 3)
            self.assertEqual(result[0]["n"], 1)

    @patch('archive_utils.get_archive_file')
    def test_returns_empty_for_missing_file(self, mock_get_archive):
        """load_archive() should return empty list if file doesn't exist."""
        from archive_utils import load_archive

        with tempfile.TemporaryDirectory() as tmpdir:
            mock_get_archive.return_value = Path(tmpdir) / "nonexistent.jsonl"

            result = load_archive()

            self.assertEqual(result, [])

    @patch('archive_utils.get_archive_file')
    @patch('archive_utils.ARCHIVE_SETTINGS', {"max_archive_entries_to_load": 2})
    def test_respects_limit(self, mock_get_archive):
        """load_archive() should return only most recent entries up to limit."""
        from archive_utils import load_archive

        with tempfile.TemporaryDirectory() as tmpdir:
            archive_file = Path(tmpdir) / "archive.jsonl"
            entries = [{"n": i} for i in range(5)]
            archive_file.write_text('\n'.join(json.dumps(e) for e in entries))
            mock_get_archive.return_value = archive_file

            result = load_archive(limit=2)

            self.assertEqual(len(result), 2)
            self.assertEqual(result[0]["n"], 3)  # Most recent 2
            self.assertEqual(result[1]["n"], 4)


class TestSearchArchive(unittest.TestCase):
    """Tests for search_archive() function."""

    @patch('archive_utils.load_archive')
    def test_filters_by_type(self, mock_load):
        """search_archive() should filter by entry type."""
        from archive_utils import search_archive

        mock_load.return_value = [
            {"type": "step", "desc": "step1"},
            {"type": "mismatch", "desc": "mismatch1"},
            {"type": "step", "desc": "step2"}
        ]

        result = search_archive(entry_type="step")

        self.assertEqual(len(result), 2)
        self.assertTrue(all(e["type"] == "step" for e in result))

    @patch('archive_utils.load_archive')
    def test_filters_by_keyword(self, mock_load):
        """search_archive() should filter by keyword in string values."""
        from archive_utils import search_archive

        mock_load.return_value = [
            {"type": "step", "desc": "Add dark mode"},
            {"type": "step", "desc": "Fix bug"},
            {"type": "step", "desc": "Dark theme update"}
        ]

        result = search_archive(keyword="dark")

        self.assertEqual(len(result), 2)


class TestGetArchiveStats(unittest.TestCase):
    """Tests for get_archive_stats() function."""

    @patch('archive_utils.load_archive')
    def test_returns_stats(self, mock_load):
        """get_archive_stats() should return counts by type."""
        from archive_utils import get_archive_stats

        mock_load.return_value = [
            {"type": "step", "timestamp": "2025-01-01"},
            {"type": "step", "timestamp": "2025-01-02"},
            {"type": "mismatch", "timestamp": "2025-01-03"}
        ]

        stats = get_archive_stats()

        self.assertEqual(stats["total"], 3)
        self.assertEqual(stats["by_type"]["step"], 2)
        self.assertEqual(stats["by_type"]["mismatch"], 1)

    @patch('archive_utils.load_archive')
    def test_empty_archive(self, mock_load):
        """get_archive_stats() should handle empty archive."""
        from archive_utils import get_archive_stats

        mock_load.return_value = []

        stats = get_archive_stats()

        self.assertEqual(stats["total"], 0)


class TestCheckStateEntropy(unittest.TestCase):
    """Tests for check_state_entropy() function."""

    @patch('archive_utils.count_completed_steps')
    @patch('archive_utils.get_memory_items')
    @patch('archive_utils.ENTROPY_THRESHOLDS', {"max_completed_steps": 3, "max_resolved_mismatches": 2})
    def test_detects_high_entropy_from_steps(self, mock_memory, mock_count):
        """check_state_entropy() should flag too many completed steps."""
        from archive_utils import check_state_entropy

        mock_count.return_value = 5
        mock_memory.return_value = []

        needs_pruning, reasons = check_state_entropy({"plan": []})

        self.assertTrue(needs_pruning)
        self.assertTrue(any("completed steps" in r for r in reasons))

    @patch('archive_utils.count_completed_steps')
    @patch('archive_utils.get_memory_items')
    @patch('archive_utils.ENTROPY_THRESHOLDS', {"max_completed_steps": 10, "max_resolved_mismatches": 10})
    def test_low_entropy_ok(self, mock_memory, mock_count):
        """check_state_entropy() should return False when entropy is low."""
        from archive_utils import check_state_entropy

        mock_count.return_value = 1
        mock_memory.return_value = []

        needs_pruning, reasons = check_state_entropy({"plan": [], "mismatches": []})

        self.assertFalse(needs_pruning)
        self.assertEqual(len(reasons), 0)

    def test_handles_none_state(self):
        """check_state_entropy() should handle None state."""
        from archive_utils import check_state_entropy

        needs_pruning, reasons = check_state_entropy(None)

        self.assertFalse(needs_pruning)


class TestIdentifyPrunableSteps(unittest.TestCase):
    """Tests for identify_prunable_steps() function."""

    @patch('archive_utils.ARCHIVE_SETTINGS', {"max_completed_steps_in_state": 1})
    def test_identifies_old_completed_steps(self):
        """identify_prunable_steps() should return all but most recent completed."""
        from archive_utils import identify_prunable_steps

        state = {
            "plan": [
                {"status": "completed", "desc": "step1"},
                {"status": "completed", "desc": "step2"},
                {"status": "completed", "desc": "step3"},
                {"status": "pending", "desc": "step4"}
            ]
        }

        prunable = identify_prunable_steps(state)

        # Should return first 2 completed steps (keep last 1)
        self.assertEqual(len(prunable), 2)
        self.assertEqual(prunable[0][1]["desc"], "step1")
        self.assertEqual(prunable[1][1]["desc"], "step2")

    @patch('archive_utils.ARCHIVE_SETTINGS', {"max_completed_steps_in_state": 1})
    def test_keeps_recent_completed(self):
        """identify_prunable_steps() should keep most recent completed step."""
        from archive_utils import identify_prunable_steps

        state = {
            "plan": [
                {"status": "completed", "desc": "only_one"}
            ]
        }

        prunable = identify_prunable_steps(state)

        self.assertEqual(len(prunable), 0)


class TestIdentifyPrunableMismatches(unittest.TestCase):
    """Tests for identify_prunable_mismatches() function."""

    def test_identifies_resolved_mismatches(self):
        """identify_prunable_mismatches() should return resolved mismatches with validation."""
        from archive_utils import identify_prunable_mismatches

        state = {
            "mismatches": [
                {"id": 1, "resolved": True, "trigger": "test", "resolution": "fixed"},
                {"id": 2, "resolved": False},
                {"id": 3, "resolved": True, "trigger": "other", "resolution": "also fixed"}
            ]
        }

        prunable = identify_prunable_mismatches(state)

        # Should find 2 resolved mismatches
        self.assertEqual(len(prunable), 2)
        # Both should be valid (have trigger and resolution)
        self.assertTrue(all(p["valid"] for p in prunable))
        # All should be resolved
        self.assertTrue(all(p["mismatch"]["resolved"] for p in prunable))

    def test_flags_missing_trigger(self):
        """identify_prunable_mismatches() should flag resolved without trigger."""
        from archive_utils import identify_prunable_mismatches

        state = {
            "mismatches": [
                {"id": 1, "resolved": True, "resolution": "fixed"}  # No trigger!
            ]
        }

        prunable = identify_prunable_mismatches(state)

        self.assertEqual(len(prunable), 1)
        self.assertFalse(prunable[0]["valid"])
        self.assertIn("trigger", prunable[0]["error"])


class TestIdentifyDecayedMemory(unittest.TestCase):
    """Tests for identify_decayed_memory() function."""

    @patch('archive_utils.get_memory_items')
    @patch('archive_utils.MEMORY_SETTINGS', {"decay_threshold_days": 14, "reinforcement_threshold": 2})
    def test_decays_old_unreinforced(self, mock_memory):
        """identify_decayed_memory() should decay old unreinforced items."""
        from archive_utils import identify_decayed_memory

        old_date = (datetime.now() - timedelta(days=20)).strftime('%Y-%m-%d')
        mock_memory.return_value = [
            {"trigger": "old_lesson", "reinforced": 0, "last_used": old_date}
        ]

        decayed = identify_decayed_memory({"memory": []})

        self.assertEqual(len(decayed), 1)
        self.assertEqual(decayed[0][0]["trigger"], "old_lesson")

    @patch('archive_utils.get_memory_items')
    @patch('archive_utils.MEMORY_SETTINGS', {"decay_threshold_days": 14, "reinforcement_threshold": 2})
    def test_keeps_reinforced(self, mock_memory):
        """identify_decayed_memory() should keep highly reinforced items."""
        from archive_utils import identify_decayed_memory

        old_date = (datetime.now() - timedelta(days=100)).strftime('%Y-%m-%d')
        mock_memory.return_value = [
            {"trigger": "valuable_lesson", "reinforced": 3, "last_used": old_date}
        ]

        decayed = identify_decayed_memory({"memory": []})

        self.assertEqual(len(decayed), 0)


class TestProofGroundedDecay(unittest.TestCase):
    """Tests for proof-grounded memory decay (v3.10.1)."""

    @patch('archive_utils.get_memory_items')
    @patch('archive_utils.MEMORY_SETTINGS', {
        "decay_threshold_days": 14,
        "reinforcement_threshold": 2,
        "vitality_threshold": 1,
        "vitality_lookback_days": 14
    })
    def test_vitality_protects_from_decay(self, mock_memory):
        """Lessons with proof vitality should be protected from decay."""
        from archive_utils import identify_decayed_memory

        old_date = (datetime.now() - timedelta(days=20)).strftime('%Y-%m-%d')
        mock_memory.return_value = [
            {"trigger": "vital_lesson", "reinforced": 0, "last_used": old_date}
        ]

        # Mock check_lesson_vitality at the import location (proof_utils)
        with patch('proof_utils.check_lesson_vitality') as mock_vitality:
            mock_vitality.return_value = (True, "Proof shows 2 matches")

            decayed = identify_decayed_memory({"memory": []})

            # Lesson should NOT be decayed because proof shows vitality
            self.assertEqual(len(decayed), 0)
            mock_vitality.assert_called_once()

    @patch('archive_utils.get_memory_items')
    @patch('archive_utils.MEMORY_SETTINGS', {
        "decay_threshold_days": 14,
        "reinforcement_threshold": 2,
        "vitality_threshold": 1,
        "vitality_lookback_days": 14
    })
    def test_no_vitality_allows_decay(self, mock_memory):
        """Lessons without proof vitality should still decay normally."""
        from archive_utils import identify_decayed_memory

        old_date = (datetime.now() - timedelta(days=20)).strftime('%Y-%m-%d')
        mock_memory.return_value = [
            {"trigger": "stale_lesson", "reinforced": 0, "last_used": old_date}
        ]

        # Mock check_lesson_vitality at the import location (proof_utils)
        with patch('proof_utils.check_lesson_vitality') as mock_vitality:
            mock_vitality.return_value = (False, "No proof vitality")

            decayed = identify_decayed_memory({"memory": []})

            # Lesson should be decayed
            self.assertEqual(len(decayed), 1)
            self.assertEqual(decayed[0][0]["trigger"], "stale_lesson")

    @patch('archive_utils.get_memory_items')
    @patch('archive_utils.MEMORY_SETTINGS', {
        "decay_threshold_days": 14,
        "reinforcement_threshold": 2,
        "vitality_threshold": 1,
        "vitality_lookback_days": 14
    })
    def test_vitality_check_graceful_on_import_error(self, mock_memory):
        """identify_decayed_memory() should work even if proof_utils import fails."""
        from archive_utils import identify_decayed_memory

        old_date = (datetime.now() - timedelta(days=20)).strftime('%Y-%m-%d')
        mock_memory.return_value = [
            {"trigger": "some_lesson", "reinforced": 0, "last_used": old_date}
        ]

        # Simulate ImportError by making check_lesson_vitality unavailable
        with patch.dict('sys.modules', {'proof_utils': None}):
            # This should not crash, just fall back to normal decay behavior
            decayed = identify_decayed_memory({"memory": []})

            # Should decay normally when vitality check unavailable
            self.assertEqual(len(decayed), 1)


class TestComputePrunePlan(unittest.TestCase):
    """Tests for compute_prune_plan() function."""

    @patch('archive_utils.identify_prunable_steps')
    @patch('archive_utils.identify_prunable_mismatches')
    @patch('archive_utils.identify_decayed_memory')
    def test_computes_full_plan(self, mock_memory, mock_mismatches, mock_steps):
        """compute_prune_plan() should aggregate all prunable items."""
        from archive_utils import compute_prune_plan

        mock_steps.return_value = [(0, {"desc": "step"})]
        mock_mismatches.return_value = [{"id": 1}]
        mock_memory.return_value = [({"trigger": "x"}, "reason")]

        plan = compute_prune_plan({})

        self.assertEqual(len(plan["steps"]), 1)
        self.assertEqual(len(plan["mismatches"]), 1)
        self.assertEqual(len(plan["memory"]), 1)


class TestEstimateEntropyReduction(unittest.TestCase):
    """Tests for estimate_entropy_reduction() function."""

    def test_estimates_lines_saved(self):
        """estimate_entropy_reduction() should calculate savings."""
        from archive_utils import estimate_entropy_reduction

        plan = {
            "steps": [(0, {}), (1, {})],  # 2 steps
            "mismatches": [{}],            # 1 mismatch
            "memory": []                    # 0 memory
        }

        estimate = estimate_entropy_reduction(plan)

        self.assertEqual(estimate["items_to_prune"], 3)
        self.assertEqual(estimate["breakdown"]["steps"], 2)
        self.assertEqual(estimate["breakdown"]["mismatches"], 1)
        self.assertEqual(estimate["breakdown"]["memory"], 0)
        self.assertGreater(estimate["estimated_lines_saved"], 0)


class TestValidateMismatchForArchive(unittest.TestCase):
    """Tests for validate_mismatch_for_archive() - v3.4 lesson extraction."""

    def test_valid_mismatch_passes(self):
        """validate_mismatch_for_archive() should accept mismatch with trigger and resolution."""
        from archive_utils import validate_mismatch_for_archive

        mismatch = {
            "id": "m-123",
            "resolved": True,
            "trigger": "sync + data missing",
            "resolution": "Changed sync to use same DB"
        }

        is_valid, error = validate_mismatch_for_archive(mismatch)

        self.assertTrue(is_valid)
        self.assertIsNone(error)

    def test_rejects_unresolved(self):
        """validate_mismatch_for_archive() should reject unresolved mismatch."""
        from archive_utils import validate_mismatch_for_archive

        mismatch = {"id": "m-123", "resolved": False}

        is_valid, error = validate_mismatch_for_archive(mismatch)

        self.assertFalse(is_valid)
        self.assertIn("resolved", error)

    def test_rejects_missing_trigger(self):
        """validate_mismatch_for_archive() should reject missing trigger."""
        from archive_utils import validate_mismatch_for_archive

        mismatch = {
            "id": "m-123",
            "resolved": True,
            "resolution": "Fixed it"
            # No trigger!
        }

        is_valid, error = validate_mismatch_for_archive(mismatch)

        self.assertFalse(is_valid)
        self.assertIn("trigger", error)

    def test_rejects_missing_resolution(self):
        """validate_mismatch_for_archive() should reject missing resolution."""
        from archive_utils import validate_mismatch_for_archive

        mismatch = {
            "id": "m-123",
            "resolved": True,
            "trigger": "test trigger"
            # No resolution!
        }

        is_valid, error = validate_mismatch_for_archive(mismatch)

        self.assertFalse(is_valid)
        self.assertIn("resolution", error)


class TestDeriveLessonFromMismatch(unittest.TestCase):
    """Tests for derive_lesson_from_mismatch() - v3.4 lesson extraction."""

    def test_derives_lesson_from_resolution(self):
        """derive_lesson_from_mismatch() should use resolution as lesson text."""
        from archive_utils import derive_lesson_from_mismatch

        mismatch = {
            "id": "m-123",
            "trigger": "sync + data",
            "resolution": "Use same database type",
            "expectation": "Data syncs correctly",
            "observation": "Data not appearing"
        }

        lesson = derive_lesson_from_mismatch(mismatch)

        self.assertEqual(lesson["trigger"], "sync + data")
        self.assertEqual(lesson["lesson"], "Use same database type")
        self.assertIn("m-123", lesson["source"])

    def test_falls_back_to_expectation_observation(self):
        """derive_lesson_from_mismatch() should use expectation/observation if no resolution."""
        from archive_utils import derive_lesson_from_mismatch

        mismatch = {
            "id": "m-456",
            "trigger": "test trigger",
            "resolution": "",
            "expectation": "X happens",
            "observation": "Y happens"
        }

        lesson = derive_lesson_from_mismatch(mismatch)

        self.assertIn("Expected: X happens", lesson["lesson"])
        self.assertIn("Reality: Y happens", lesson["lesson"])


class TestArchiveResolvedMismatchWithLesson(unittest.TestCase):
    """Tests for archive_resolved_mismatch() - v3.4 with lesson extraction."""

    @patch('archive_utils.log_to_archive')
    def test_rejects_invalid_mismatch(self, mock_log):
        """archive_resolved_mismatch() should reject mismatch without trigger."""
        from archive_utils import archive_resolved_mismatch

        mismatch = {
            "id": "m-123",
            "resolved": True,
            "resolution": "Fixed"
            # No trigger!
        }

        success, result = archive_resolved_mismatch(mismatch)

        self.assertFalse(success)
        self.assertIn("trigger", result)
        mock_log.assert_not_called()

    @patch('archive_utils.log_to_archive')
    def test_archives_valid_mismatch(self, mock_log):
        """archive_resolved_mismatch() should archive valid mismatch with lesson."""
        from archive_utils import archive_resolved_mismatch

        mismatch = {
            "id": "m-123",
            "resolved": True,
            "trigger": "sync + data",
            "resolution": "Use same DB",
            "expectation": "Data syncs",
            "observation": "Data missing"
        }

        success, lesson = archive_resolved_mismatch(mismatch)

        self.assertTrue(success)
        self.assertEqual(lesson["trigger"], "sync + data")
        self.assertEqual(lesson["lesson"], "Use same DB")
        mock_log.assert_called_once()

    @patch('archive_utils.log_to_archive')
    def test_adds_lesson_to_memory(self, mock_log):
        """archive_resolved_mismatch() should add lesson to memory when state provided."""
        from archive_utils import archive_resolved_mismatch

        mismatch = {
            "id": "m-123",
            "resolved": True,
            "trigger": "test trigger",
            "resolution": "Test lesson"
        }
        state = {"memory": []}

        # Patch memory_utils.add_memory_item inside archive_utils
        with patch('memory_utils.add_memory_item') as mock_add:
            success, lesson = archive_resolved_mismatch(mismatch, state=state)
            # Verify add_memory_item was called with correct args
            mock_add.assert_called_once()
            call_args = mock_add.call_args
            self.assertEqual(call_args[0][0], state)  # First arg is state
            self.assertEqual(call_args[1]["trigger"], "test trigger")

        self.assertTrue(success)


class TestEvergreenLessons(unittest.TestCase):
    """Tests for v3.10 Evergreen Lessons - lessons that never decay."""

    @patch('archive_utils.get_memory_items')
    @patch('archive_utils.MEMORY_SETTINGS', {"decay_threshold_days": 14, "reinforcement_threshold": 2})
    def test_evergreen_never_decays(self, mock_memory):
        """identify_decayed_memory() should never decay evergreen lessons."""
        from archive_utils import identify_decayed_memory

        old_date = (datetime.now() - timedelta(days=100)).strftime('%Y-%m-%d')
        mock_memory.return_value = [
            # Old unreinforced evergreen - should NOT decay
            {"trigger": "evergreen_lesson", "reinforced": 0, "last_used": old_date, "evergreen": True},
            # Old unreinforced non-evergreen - SHOULD decay
            {"trigger": "normal_lesson", "reinforced": 0, "last_used": old_date}
        ]

        decayed = identify_decayed_memory({"memory": []})

        # Only the non-evergreen lesson should be decayed
        self.assertEqual(len(decayed), 1)
        self.assertEqual(decayed[0][0]["trigger"], "normal_lesson")

    @patch('archive_utils.get_memory_items')
    @patch('archive_utils.MEMORY_SETTINGS', {"decay_threshold_days": 14, "reinforcement_threshold": 2})
    def test_evergreen_survives_single_reinforcement(self, mock_memory):
        """Evergreen lessons with single reinforcement should also survive."""
        from archive_utils import identify_decayed_memory

        old_date = (datetime.now() - timedelta(days=30)).strftime('%Y-%m-%d')
        mock_memory.return_value = [
            # Evergreen with 1 reinforcement (would normally decay at >7 days)
            {"trigger": "core_principle", "reinforced": 1, "last_used": old_date, "evergreen": True}
        ]

        decayed = identify_decayed_memory({"memory": []})

        # Evergreen should survive regardless of reinforcement
        self.assertEqual(len(decayed), 0)


class TestCleanupArchive(unittest.TestCase):
    """Tests for v3.10 cleanup_archive() - type-based retention policy."""

    def test_dry_run_returns_analysis(self):
        """cleanup_archive(dry_run=True) should return analysis without modifying."""
        from archive_utils import cleanup_archive

        with tempfile.NamedTemporaryFile(mode='w', suffix='.jsonl', delete=False) as f:
            # Write some test entries
            old_date = (datetime.now() - timedelta(days=60)).isoformat()
            new_date = datetime.now().isoformat()
            f.write(json.dumps({"type": "completed_step", "timestamp": old_date}) + "\n")  # Should expire (>30 days)
            f.write(json.dumps({"type": "completed_objective", "timestamp": new_date}) + "\n")  # Should keep (365 days)
            f.flush()
            temp_path = f.name

        try:
            with patch('archive_utils.get_archive_file', return_value=Path(temp_path)):
                result = cleanup_archive(dry_run=True)

            self.assertIn("by_type", result)
            self.assertEqual(result["removed"], 1)  # Old step expired
            self.assertEqual(result["kept"], 1)     # New objective kept
        finally:
            os.unlink(temp_path)

    def test_removes_expired_entries(self):
        """cleanup_archive() should remove entries beyond retention period."""
        from archive_utils import cleanup_archive

        with tempfile.NamedTemporaryFile(mode='w', suffix='.jsonl', delete=False) as f:
            # Write entries of different ages
            very_old = (datetime.now() - timedelta(days=400)).isoformat()  # > 365 days
            recent = datetime.now().isoformat()
            f.write(json.dumps({"type": "completed_objective", "timestamp": very_old}) + "\n")
            f.write(json.dumps({"type": "completed_objective", "timestamp": recent}) + "\n")
            f.flush()
            temp_path = f.name

        try:
            with patch('archive_utils.get_archive_file', return_value=Path(temp_path)):
                removed, kept = cleanup_archive(dry_run=False)

            self.assertEqual(removed, 1)  # Very old objective expired
            self.assertEqual(kept, 1)     # Recent objective kept

            # Verify file was updated
            with open(temp_path, 'r') as f:
                lines = f.readlines()
            self.assertEqual(len(lines), 1)  # Only one entry left
        finally:
            os.unlink(temp_path)


# =============================================================================
# v7.1 - LEARNED GUIDANCE CAPTURE TESTS
# =============================================================================

class TestLoadVerbTaxonomy(unittest.TestCase):
    """Tests for _load_verb_taxonomy()."""

    def test_loads_taxonomy_from_config(self):
        """_load_verb_taxonomy() should load verb definitions from YAML."""
        from archive_utils import _load_verb_taxonomy

        taxonomy = _load_verb_taxonomy()

        self.assertIsInstance(taxonomy, dict)
        # Should have canonical verbs from guidance_config.yaml
        self.assertIn("scope", taxonomy)
        self.assertIn("test", taxonomy)
        self.assertIn("build", taxonomy)

    def test_scope_has_synonyms(self):
        """scope verb should have synonyms list."""
        from archive_utils import _load_verb_taxonomy

        taxonomy = _load_verb_taxonomy()

        scope = taxonomy.get("scope", {})
        synonyms = scope.get("synonyms", [])
        self.assertIn("define", synonyms)
        self.assertIn("identify", synonyms)

    def test_fallback_when_yaml_unavailable(self):
        """_load_verb_taxonomy() should use defaults when yaml import fails."""
        from archive_utils import _get_default_taxonomy

        # The default taxonomy should have all 10 canonical verbs
        defaults = _get_default_taxonomy()

        self.assertEqual(len(defaults), 10)
        for verb in ["scope", "plan", "test", "build", "extract",
                     "integrate", "fix", "clean", "document", "deploy"]:
            self.assertIn(verb, defaults)
            self.assertIn("synonyms", defaults[verb])


class TestNormalizeStepToVerb(unittest.TestCase):
    """Tests for _normalize_step_to_verb()."""

    def test_normalizes_scope_synonyms(self):
        """Should map 'define' and 'identify' to 'scope'."""
        from archive_utils import _normalize_step_to_verb, _load_verb_taxonomy

        taxonomy = _load_verb_taxonomy()

        self.assertEqual(_normalize_step_to_verb("Define the boundaries", taxonomy), "scope")
        self.assertEqual(_normalize_step_to_verb("Identify files to change", taxonomy), "scope")

    def test_normalizes_test_synonyms(self):
        """Should map 'verify' and 'validate' to 'test'."""
        from archive_utils import _normalize_step_to_verb, _load_verb_taxonomy

        taxonomy = _load_verb_taxonomy()

        self.assertEqual(_normalize_step_to_verb("Verify tests pass", taxonomy), "test")
        self.assertEqual(_normalize_step_to_verb("Validate implementation", taxonomy), "test")

    def test_returns_other_for_unknown(self):
        """Should return 'other' for unmatched steps."""
        from archive_utils import _normalize_step_to_verb, _load_verb_taxonomy

        taxonomy = _load_verb_taxonomy()

        self.assertEqual(_normalize_step_to_verb("Ponder the meaning of life", taxonomy), "other")


class TestExtractApproachSummary(unittest.TestCase):
    """Tests for _extract_approach_summary()."""

    def test_extracts_completed_steps(self):
        """Should extract normalized verbs from completed steps."""
        from archive_utils import _extract_approach_summary, _load_verb_taxonomy

        taxonomy = _load_verb_taxonomy()
        plan = [
            {"description": "Define requirements", "status": "completed", "proof": "Done"},
            {"description": "Write tests", "status": "completed", "proof": "Tests pass"},
            {"description": "Pending work", "status": "pending"},
        ]

        result = _extract_approach_summary(plan, taxonomy)

        self.assertEqual(len(result), 2)  # Only completed steps
        self.assertEqual(result[0]["verb"], "scope")  # 'Define' → 'scope'
        self.assertEqual(result[1]["verb"], "test")   # 'Write tests' → 'test'

    def test_preserves_proof(self):
        """Should preserve proof from completed steps."""
        from archive_utils import _extract_approach_summary, _load_verb_taxonomy

        taxonomy = _load_verb_taxonomy()
        plan = [
            {"description": "Test the system", "status": "completed", "proof": "All 50 tests pass"},
        ]

        result = _extract_approach_summary(plan, taxonomy)

        self.assertEqual(result[0]["proof"], "All 50 tests pass")


class TestComputeObjectiveMetrics(unittest.TestCase):
    """Tests for _compute_objective_metrics()."""

    def test_counts_steps(self):
        """Should count planned, completed, and abandoned steps."""
        from archive_utils import _compute_objective_metrics

        state = {
            "plan": [
                {"status": "completed"},
                {"status": "completed"},
                {"status": "pending"},
                {"status": "in_progress"},
            ]
        }

        metrics = _compute_objective_metrics(state)

        self.assertEqual(metrics["steps_planned"], 4)
        self.assertEqual(metrics["steps_completed"], 2)
        self.assertEqual(metrics["steps_abandoned"], 2)  # pending + in_progress


class TestInferTagsFromObjective(unittest.TestCase):
    """Tests for _infer_tags_from_objective()."""

    def test_infers_refactoring(self):
        """Should infer 'refactoring' from keywords."""
        from archive_utils import _infer_tags_from_objective

        tags = _infer_tags_from_objective("Refactor the authentication module")
        self.assertIn("refactoring", tags)

    def test_infers_feature(self):
        """Should infer 'feature' from keywords."""
        from archive_utils import _infer_tags_from_objective

        tags = _infer_tags_from_objective("Add new login feature")
        self.assertIn("feature", tags)

    def test_infers_testing(self):
        """Should infer 'testing' from keywords."""
        from archive_utils import _infer_tags_from_objective

        tags = _infer_tags_from_objective("Write unit tests for API")
        self.assertIn("testing", tags)


class TestCaptureObjectiveCompletion(unittest.TestCase):
    """Tests for capture_objective_completion()."""

    def setUp(self):
        """Create temp directory for archive."""
        self.temp_dir = tempfile.mkdtemp()
        self.archive_path = Path(self.temp_dir) / ".proof" / "archive.jsonl"
        self.archive_path.parent.mkdir(parents=True, exist_ok=True)

    def tearDown(self):
        """Clean up temp directory."""
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_captures_completion_data(self):
        """capture_objective_completion() should log rich completion record."""
        from archive_utils import capture_objective_completion, load_archive

        state = {
            "objective": "Implement feature X",
            "plan": [
                {"description": "Define scope", "status": "completed", "proof": "Scope doc"},
                {"description": "Write tests", "status": "completed", "proof": "Tests pass"},
                {"description": "Build feature", "status": "completed", "proof": "Feature works"},
            ],
        }

        with patch('archive_utils.get_archive_file', return_value=self.archive_path):
            result = capture_objective_completion(
                state=state,
                session_id="test-session",
                outcome_quality="clean",
                outcome_notes="All good"
            )

        self.assertEqual(result["type"], "objective_completion")
        self.assertEqual(result["objective"], "Implement feature X")
        self.assertEqual(len(result["approach_summary"]), 3)
        self.assertEqual(result["metrics"]["steps_completed"], 3)
        self.assertEqual(result["outcome"]["quality"], "clean")

        # Verify it was logged
        with patch('archive_utils.get_archive_file', return_value=self.archive_path):
            entries = load_archive()
        self.assertEqual(len(entries), 1)
        self.assertEqual(entries[0]["type"], "objective_completion")


class TestCaptureObjectivePartial(unittest.TestCase):
    """Tests for capture_objective_partial()."""

    def setUp(self):
        """Create temp directory for archive."""
        self.temp_dir = tempfile.mkdtemp()
        self.archive_path = Path(self.temp_dir) / ".proof" / "archive.jsonl"
        self.archive_path.parent.mkdir(parents=True, exist_ok=True)

    def tearDown(self):
        """Clean up temp directory."""
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_captures_partial_data(self):
        """capture_objective_partial() should log partial completion record."""
        from archive_utils import capture_objective_partial, load_archive

        state = {
            "objective": "Old objective",
            "plan": [
                {"description": "Step 1", "status": "completed", "proof": "Done"},
                {"description": "Step 2", "status": "in_progress"},
                {"description": "Step 3", "status": "pending"},
            ],
        }

        with patch('archive_utils.get_archive_file', return_value=self.archive_path):
            result = capture_objective_partial(
                state=state,
                session_id="test-session",
                reason="objective_changed",
                new_objective="New objective"
            )

        self.assertEqual(result["type"], "objective_partial")
        self.assertEqual(result["objective"], "Old objective")
        self.assertEqual(result["new_objective"], "New objective")
        self.assertEqual(result["metrics"]["steps_completed"], 1)
        self.assertEqual(result["metrics"]["steps_abandoned"], 2)
        self.assertEqual(result["reason"], "objective_changed")

        # Verify completed steps captured
        self.assertEqual(len(result["approach_summary"]), 1)


class TestGetObjectiveCompletions(unittest.TestCase):
    """Tests for get_objective_completions()."""

    def setUp(self):
        """Create temp directory for archive."""
        self.temp_dir = tempfile.mkdtemp()
        self.archive_path = Path(self.temp_dir) / ".proof" / "archive.jsonl"
        self.archive_path.parent.mkdir(parents=True, exist_ok=True)

    def tearDown(self):
        """Clean up temp directory."""
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_filters_completions_only(self):
        """get_objective_completions() should return only completion records."""
        from archive_utils import get_objective_completions

        # Write mixed archive entries
        with open(self.archive_path, 'w') as f:
            f.write(json.dumps({"type": "objective_completion", "objective": "A"}) + "\n")
            f.write(json.dumps({"type": "completed_step", "step": "X"}) + "\n")
            f.write(json.dumps({"type": "objective_completion", "objective": "B"}) + "\n")
            f.write(json.dumps({"type": "objective_partial", "objective": "C"}) + "\n")

        with patch('archive_utils.get_archive_file', return_value=self.archive_path):
            completions = get_objective_completions(limit=50)

        self.assertEqual(len(completions), 2)
        self.assertTrue(all(c["type"] == "objective_completion" for c in completions))


class TestGetObjectivePartials(unittest.TestCase):
    """Tests for get_objective_partials()."""

    def setUp(self):
        """Create temp directory for archive."""
        self.temp_dir = tempfile.mkdtemp()
        self.archive_path = Path(self.temp_dir) / ".proof" / "archive.jsonl"
        self.archive_path.parent.mkdir(parents=True, exist_ok=True)

    def tearDown(self):
        """Clean up temp directory."""
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_filters_partials_only(self):
        """get_objective_partials() should return only partial records."""
        from archive_utils import get_objective_partials

        # Write mixed archive entries
        with open(self.archive_path, 'w') as f:
            f.write(json.dumps({"type": "objective_partial", "objective": "A"}) + "\n")
            f.write(json.dumps({"type": "objective_completion", "objective": "B"}) + "\n")
            f.write(json.dumps({"type": "objective_partial", "objective": "C"}) + "\n")

        with patch('archive_utils.get_archive_file', return_value=self.archive_path):
            partials = get_objective_partials(limit=50)

        self.assertEqual(len(partials), 2)
        self.assertTrue(all(p["type"] == "objective_partial" for p in partials))


if __name__ == '__main__':
    unittest.main()
