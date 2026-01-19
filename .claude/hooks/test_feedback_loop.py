#!/usr/bin/env python3
"""
Tests for Operator's Edge v7.1 - Feedback Loop (Phase 4)

Tests cover:
- Approach comparison and follow detection
- Confidence update formulas
- Pattern persistence
- Integration with archive
"""
import json
import os
import sys
import tempfile
import shutil
import unittest
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import patch, MagicMock

# Add hooks directory to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from feedback_loop import (
    FeedbackResult,
    compare_approach_to_suggestion,
    compute_confidence_update,
    get_suggestion_for_objective,
    process_completion_feedback,
    get_pattern_stats,
    get_pattern_confidence,
    update_pattern_confidence,
    _compute_sequence_similarity,
    _get_feedback_settings,
    _load_patterns,
    _save_patterns,
    _get_patterns_file
)


class TestCompareApproachToSuggestion(unittest.TestCase):
    """Tests for approach comparison logic."""

    def test_identical_approaches_followed(self):
        """Identical verb sequences should be marked as followed."""
        actual = ["scope", "test", "build", "test"]
        suggested = ["scope", "test", "build", "test"]

        followed, score = compare_approach_to_suggestion(actual, suggested)

        self.assertTrue(followed)
        self.assertAlmostEqual(score, 1.0, places=2)

    def test_similar_approaches_followed(self):
        """Similar approaches (70%+ overlap) should be marked as followed."""
        actual = ["scope", "test", "build", "integrate", "test"]
        suggested = ["scope", "test", "extract", "integrate", "test"]

        followed, score = compare_approach_to_suggestion(actual, suggested)

        # 4/6 overlap = 66%, but with sequence bonus should be >= 50%
        self.assertTrue(followed)
        self.assertGreater(score, 0.5)

    def test_different_approaches_not_followed(self):
        """Completely different approaches should not be marked as followed."""
        actual = ["fix", "clean", "deploy"]
        suggested = ["scope", "test", "build"]

        followed, score = compare_approach_to_suggestion(actual, suggested)

        self.assertFalse(followed)
        self.assertLess(score, 0.5)

    def test_partial_overlap_threshold(self):
        """Test the threshold for 'followed' detection."""
        # 50% overlap
        actual = ["scope", "build"]
        suggested = ["scope", "test", "build", "test"]

        followed, score = compare_approach_to_suggestion(actual, suggested)

        # 2/4 verbs overlap
        self.assertGreaterEqual(score, 0.3)

    def test_empty_actual_not_followed(self):
        """Empty actual approach should not be followed."""
        actual = []
        suggested = ["scope", "test", "build"]

        followed, score = compare_approach_to_suggestion(actual, suggested)

        self.assertFalse(followed)
        self.assertEqual(score, 0.0)

    def test_empty_suggested_not_followed(self):
        """Empty suggested approach should not be followed."""
        actual = ["scope", "test", "build"]
        suggested = []

        followed, score = compare_approach_to_suggestion(actual, suggested)

        self.assertFalse(followed)
        self.assertEqual(score, 0.0)

    def test_single_verb_match(self):
        """Single matching verb should have some score."""
        actual = ["test"]
        suggested = ["test"]

        followed, score = compare_approach_to_suggestion(actual, suggested)

        self.assertTrue(followed)
        self.assertEqual(score, 1.0)

    def test_superset_approach(self):
        """Actual approach being a superset should still follow."""
        actual = ["scope", "plan", "test", "build", "integrate", "test", "deploy"]
        suggested = ["scope", "test", "build", "test"]

        followed, score = compare_approach_to_suggestion(actual, suggested)

        # All suggested verbs are in actual
        self.assertTrue(followed)
        self.assertGreater(score, 0.5)


class TestSequenceSimilarity(unittest.TestCase):
    """Tests for sequence similarity computation."""

    def test_identical_sequences(self):
        """Identical sequences should have similarity 1.0."""
        seq1 = ["a", "b", "c"]
        seq2 = ["a", "b", "c"]

        score = _compute_sequence_similarity(seq1, seq2)

        self.assertEqual(score, 1.0)

    def test_reversed_sequences(self):
        """Reversed sequences should have low similarity."""
        seq1 = ["a", "b", "c"]
        seq2 = ["c", "b", "a"]

        score = _compute_sequence_similarity(seq1, seq2)

        # LCS is 1 ("b"), max_len is 3
        self.assertLess(score, 0.5)

    def test_partial_match(self):
        """Partially matching sequences."""
        seq1 = ["a", "b", "c", "d"]
        seq2 = ["a", "c", "d"]

        score = _compute_sequence_similarity(seq1, seq2)

        # LCS is 3 ("a", "c", "d"), max_len is 4
        self.assertEqual(score, 0.75)

    def test_empty_sequences(self):
        """Empty sequences should have similarity 0."""
        self.assertEqual(_compute_sequence_similarity([], []), 0.0)
        self.assertEqual(_compute_sequence_similarity(["a"], []), 0.0)
        self.assertEqual(_compute_sequence_similarity([], ["a"]), 0.0)


class TestComputeConfidenceUpdate(unittest.TestCase):
    """Tests for confidence update formulas."""

    def test_followed_success_boosts(self):
        """Following + success should boost confidence."""
        current = 0.5
        new_conf, delta = compute_confidence_update(current, followed=True, success=True)

        self.assertGreater(new_conf, current)
        self.assertGreater(delta, 0)

    def test_followed_failure_penalizes(self):
        """Following + failure should reduce confidence."""
        current = 0.7
        new_conf, delta = compute_confidence_update(current, followed=True, success=False)

        self.assertLess(new_conf, current)
        self.assertLess(delta, 0)

    def test_ignored_success_slight_penalty(self):
        """Ignoring + success should slightly reduce confidence."""
        current = 0.6
        new_conf, delta = compute_confidence_update(current, followed=False, success=True)

        self.assertLess(new_conf, current)
        self.assertLess(delta, 0)
        # But not as much as followed+failure
        failure_conf, _ = compute_confidence_update(current, followed=True, success=False)
        self.assertGreater(new_conf, failure_conf)

    def test_ignored_failure_no_change(self):
        """Ignoring + failure should not change confidence."""
        current = 0.5
        new_conf, delta = compute_confidence_update(current, followed=False, success=False)

        self.assertAlmostEqual(new_conf, current, places=2)
        self.assertAlmostEqual(delta, 0.0, places=2)

    def test_confidence_clamped_high(self):
        """Confidence should not exceed 0.95."""
        current = 0.9
        new_conf, _ = compute_confidence_update(current, followed=True, success=True)

        self.assertLessEqual(new_conf, 0.95)

    def test_confidence_clamped_low(self):
        """Confidence should not go below 0.1."""
        current = 0.15
        new_conf, _ = compute_confidence_update(current, followed=True, success=False)

        self.assertGreaterEqual(new_conf, 0.1)

    def test_asymptotic_boost(self):
        """Boost should be asymptotic (diminishing returns at high confidence)."""
        low_boost = compute_confidence_update(0.3, followed=True, success=True)[1]
        high_boost = compute_confidence_update(0.8, followed=True, success=True)[1]

        # Low confidence should get bigger boost
        self.assertGreater(low_boost, high_boost)

    def test_custom_settings(self):
        """Custom settings should be applied."""
        settings = {
            "followed_success_boost": 0.5,  # Big boost
            "followed_failure_penalty": 0.5,  # Big penalty
            "ignored_success_penalty": 0.5,
            "ignored_failure_change": 1.0
        }

        current = 0.5
        new_conf, _ = compute_confidence_update(current, True, True, settings)

        # With 0.5 boost: 0.5 + (1 - 0.5) * 0.5 = 0.75
        self.assertAlmostEqual(new_conf, 0.75, places=2)


class TestPatternPersistence(unittest.TestCase):
    """Tests for pattern persistence (patterns.yaml)."""

    def setUp(self):
        """Create temporary directory for test patterns."""
        self.temp_dir = tempfile.mkdtemp()
        self.original_patterns_file = _get_patterns_file()

    def tearDown(self):
        """Clean up temporary directory."""
        shutil.rmtree(self.temp_dir)

    def test_load_empty_patterns(self):
        """Loading non-existent patterns file should return empty structure."""
        with patch('feedback_loop._get_patterns_file') as mock_file:
            mock_file.return_value = Path(self.temp_dir) / "nonexistent.yaml"
            patterns = _load_patterns()

        self.assertEqual(patterns, {"seed_overrides": {}, "learned": {}})

    def test_save_and_load_patterns(self):
        """Patterns should be saveable and loadable."""
        patterns_file = Path(self.temp_dir) / "patterns.yaml"

        with patch('feedback_loop._get_patterns_file') as mock_file:
            mock_file.return_value = patterns_file

            # Save patterns
            test_patterns = {
                "seed_overrides": {
                    "seed-test": {"confidence": 0.8, "updated_at": "2026-01-17"}
                },
                "learned": {}
            }
            result = _save_patterns(test_patterns)
            self.assertTrue(result)

            # Load patterns
            loaded = _load_patterns()

        self.assertEqual(loaded["seed_overrides"]["seed-test"]["confidence"], 0.8)

    def test_update_seed_pattern_confidence(self):
        """Updating seed pattern confidence should store override."""
        patterns_file = Path(self.temp_dir) / "patterns.yaml"

        with patch('feedback_loop._get_patterns_file') as mock_file:
            mock_file.return_value = patterns_file

            result = update_pattern_confidence("seed-refactor", "seed", 0.75)
            self.assertTrue(result)

            patterns = _load_patterns()

        self.assertIn("seed-refactor", patterns["seed_overrides"])
        self.assertEqual(patterns["seed_overrides"]["seed-refactor"]["confidence"], 0.75)

    def test_update_learned_pattern_confidence(self):
        """Updating learned pattern confidence should update directly."""
        patterns_file = Path(self.temp_dir) / "patterns.yaml"

        with patch('feedback_loop._get_patterns_file') as mock_file:
            mock_file.return_value = patterns_file

            result = update_pattern_confidence("learned-refactoring", "learned", 0.85)
            self.assertTrue(result)

            patterns = _load_patterns()

        self.assertIn("learned-refactoring", patterns["learned"])
        self.assertEqual(patterns["learned"]["learned-refactoring"]["confidence"], 0.85)

    def test_get_pattern_confidence_with_override(self):
        """Getting confidence should check for overrides."""
        patterns_file = Path(self.temp_dir) / "patterns.yaml"

        with patch('feedback_loop._get_patterns_file') as mock_file:
            mock_file.return_value = patterns_file

            # Set an override
            update_pattern_confidence("seed-test", "seed", 0.9)

            # Get should return override
            conf = get_pattern_confidence("seed-test", "seed", default=0.5)

        self.assertEqual(conf, 0.9)

    def test_get_pattern_confidence_default(self):
        """Getting confidence without override should return default."""
        patterns_file = Path(self.temp_dir) / "patterns.yaml"

        with patch('feedback_loop._get_patterns_file') as mock_file:
            mock_file.return_value = patterns_file

            conf = get_pattern_confidence("nonexistent", "seed", default=0.5)

        self.assertEqual(conf, 0.5)


class TestSuggestionLookup(unittest.TestCase):
    """Tests for finding suggestions in archive."""

    def test_find_exact_match(self):
        """Should find suggestion with exact objective match."""
        mock_entries = [
            {"type": "completed_step", "timestamp": "2026-01-17T10:00:00"},
            {
                "type": "suggestion_shown",
                "timestamp": "2026-01-17T10:01:00",
                "objective": "Refactor authentication module",
                "pattern_id": "seed-refactor",
                "confidence": 0.6
            }
        ]

        with patch('archive_utils.load_archive') as mock_load:
            mock_load.return_value = mock_entries
            suggestion = get_suggestion_for_objective("Refactor authentication module")

        self.assertIsNotNone(suggestion)
        self.assertEqual(suggestion["pattern_id"], "seed-refactor")

    def test_find_truncated_match(self):
        """Should find suggestion with truncated objective."""
        mock_entries = [
            {
                "type": "suggestion_shown",
                "timestamp": "2026-01-17T10:01:00",
                "objective": "Refactor auth",  # Truncated
                "pattern_id": "seed-refactor",
                "confidence": 0.6
            }
        ]

        with patch('archive_utils.load_archive') as mock_load:
            mock_load.return_value = mock_entries
            suggestion = get_suggestion_for_objective("Refactor authentication module")

        self.assertIsNotNone(suggestion)

    def test_no_suggestion_found(self):
        """Should return None when no matching suggestion."""
        mock_entries = [
            {"type": "completed_step", "timestamp": "2026-01-17T10:00:00"},
            {
                "type": "suggestion_shown",
                "timestamp": "2026-01-17T10:01:00",
                "objective": "Fix bug in login",
                "pattern_id": "seed-bugfix"
            }
        ]

        with patch('archive_utils.load_archive') as mock_load:
            mock_load.return_value = mock_entries
            suggestion = get_suggestion_for_objective("Build new feature")

        self.assertIsNone(suggestion)

    def test_finds_most_recent(self):
        """Should find the most recent matching suggestion."""
        mock_entries = [
            {
                "type": "suggestion_shown",
                "timestamp": "2026-01-17T10:00:00",
                "objective": "Refactor auth",
                "pattern_id": "old-pattern",
                "confidence": 0.5
            },
            {
                "type": "suggestion_shown",
                "timestamp": "2026-01-17T11:00:00",
                "objective": "Refactor auth",
                "pattern_id": "new-pattern",
                "confidence": 0.7
            }
        ]

        with patch('archive_utils.load_archive') as mock_load:
            mock_load.return_value = mock_entries
            suggestion = get_suggestion_for_objective("Refactor auth")

        self.assertEqual(suggestion["pattern_id"], "new-pattern")


class TestProcessCompletionFeedback(unittest.TestCase):
    """Tests for the main feedback processing function."""

    def setUp(self):
        """Set up test fixtures."""
        self.temp_dir = tempfile.mkdtemp()

    def tearDown(self):
        """Clean up."""
        shutil.rmtree(self.temp_dir)

    def test_no_suggestion_returns_no_feedback(self):
        """When no suggestion was shown, feedback should indicate this."""
        with patch('feedback_loop.get_suggestion_for_objective') as mock_get:
            mock_get.return_value = None

            result = process_completion_feedback(
                objective="Build new feature",
                approach_verbs=["scope", "build", "test"],
                success=True
            )

        self.assertFalse(result.suggestion_found)
        self.assertIsNone(result.pattern_id)
        self.assertIsNone(result.suggestion_followed)

    def test_followed_success_updates_confidence(self):
        """Following + success should update pattern confidence."""
        mock_suggestion = {
            "objective": "Refactor module",
            "pattern_id": "seed-refactor",
            "pattern_source": "seed",
            "approach_verbs": ["scope", "test", "extract", "test"],
            "confidence": 0.6
        }

        patterns_file = Path(self.temp_dir) / "patterns.yaml"

        with patch('feedback_loop.get_suggestion_for_objective') as mock_get, \
             patch('feedback_loop._get_patterns_file') as mock_file, \
             patch('feedback_loop._log_feedback_to_archive'):
            mock_get.return_value = mock_suggestion
            mock_file.return_value = patterns_file

            result = process_completion_feedback(
                objective="Refactor module",
                approach_verbs=["scope", "test", "extract", "test"],  # Same as suggestion
                success=True
            )

        self.assertTrue(result.suggestion_found)
        self.assertEqual(result.pattern_id, "seed-refactor")
        self.assertTrue(result.suggestion_followed)
        self.assertGreater(result.confidence_delta, 0)  # Confidence increased
        self.assertGreater(result.new_confidence, 0.6)

    def test_ignored_success_slight_penalty(self):
        """Ignoring + success should slightly reduce confidence."""
        mock_suggestion = {
            "objective": "Refactor module",
            "pattern_id": "seed-refactor",
            "pattern_source": "seed",
            "approach_verbs": ["scope", "test", "extract", "test"],
            "confidence": 0.6
        }

        patterns_file = Path(self.temp_dir) / "patterns.yaml"

        with patch('feedback_loop.get_suggestion_for_objective') as mock_get, \
             patch('feedback_loop._get_patterns_file') as mock_file, \
             patch('feedback_loop._log_feedback_to_archive'):
            mock_get.return_value = mock_suggestion
            mock_file.return_value = patterns_file

            result = process_completion_feedback(
                objective="Refactor module",
                approach_verbs=["fix", "clean", "deploy"],  # Different from suggestion
                success=True
            )

        self.assertTrue(result.suggestion_found)
        self.assertFalse(result.suggestion_followed)
        self.assertLess(result.confidence_delta, 0)  # Confidence decreased slightly

    def test_followed_failure_penalizes(self):
        """Following + failure should reduce confidence."""
        mock_suggestion = {
            "objective": "Build feature",
            "pattern_id": "seed-feature",
            "pattern_source": "seed",
            "approach_verbs": ["scope", "plan", "build", "test"],
            "confidence": 0.7
        }

        patterns_file = Path(self.temp_dir) / "patterns.yaml"

        with patch('feedback_loop.get_suggestion_for_objective') as mock_get, \
             patch('feedback_loop._get_patterns_file') as mock_file, \
             patch('feedback_loop._log_feedback_to_archive'):
            mock_get.return_value = mock_suggestion
            mock_file.return_value = patterns_file

            result = process_completion_feedback(
                objective="Build feature",
                approach_verbs=["scope", "plan", "build", "test"],  # Same
                success=False  # But failed
            )

        self.assertTrue(result.suggestion_followed)
        self.assertLess(result.confidence_delta, 0)
        self.assertLess(result.new_confidence, 0.7)


class TestFeedbackResult(unittest.TestCase):
    """Tests for FeedbackResult dataclass."""

    def test_to_dict(self):
        """FeedbackResult should convert to dict properly."""
        result = FeedbackResult(
            suggestion_found=True,
            pattern_id="test-pattern",
            pattern_source="seed",
            suggestion_followed=True,
            follow_score=0.85,
            outcome_success=True,
            confidence_delta=0.1,
            new_confidence=0.7
        )

        d = result.to_dict()

        self.assertEqual(d["pattern_id"], "test-pattern")
        self.assertEqual(d["follow_score"], 0.85)
        self.assertTrue(d["suggestion_followed"])


class TestPatternStats(unittest.TestCase):
    """Tests for pattern statistics functions."""

    def test_get_stats_no_data(self):
        """Stats with no feedback data should return zeros."""
        with patch('archive_utils.load_archive') as mock_load:
            mock_load.return_value = []

            stats = get_pattern_stats("test-pattern")

        self.assertEqual(stats["times_used"], 0)
        self.assertEqual(stats["follow_rate"], 0.0)

    def test_get_stats_with_data(self):
        """Stats should aggregate feedback entries correctly."""
        mock_entries = [
            {
                "type": "pattern_feedback",
                "pattern_id": "test-pattern",
                "suggestion_followed": True,
                "outcome_success": True
            },
            {
                "type": "pattern_feedback",
                "pattern_id": "test-pattern",
                "suggestion_followed": False,
                "outcome_success": True
            },
            {
                "type": "pattern_feedback",
                "pattern_id": "test-pattern",
                "suggestion_followed": True,
                "outcome_success": False
            }
        ]

        with patch('archive_utils.load_archive') as mock_load:
            mock_load.return_value = mock_entries

            stats = get_pattern_stats("test-pattern")

        self.assertEqual(stats["times_used"], 3)
        self.assertEqual(stats["times_followed"], 2)
        self.assertAlmostEqual(stats["follow_rate"], 2/3, places=2)
        self.assertAlmostEqual(stats["success_rate"], 2/3, places=2)


class TestFeedbackSettings(unittest.TestCase):
    """Tests for feedback settings loading."""

    def test_default_settings(self):
        """Should return default settings when config unavailable."""
        with patch('feedback_loop.Path') as mock_path:
            mock_path.return_value.parent.__truediv__ = MagicMock(
                return_value=MagicMock(exists=MagicMock(return_value=False))
            )

            settings = _get_feedback_settings()

        self.assertIn("followed_success_boost", settings)
        self.assertIn("followed_failure_penalty", settings)


# =============================================================================
# INTEGRATION TESTS
# =============================================================================

class TestFeedbackIntegration(unittest.TestCase):
    """Integration tests for the full feedback loop."""

    def setUp(self):
        """Set up test fixtures."""
        self.temp_dir = tempfile.mkdtemp()
        self.archive_file = Path(self.temp_dir) / "archive.jsonl"

    def tearDown(self):
        """Clean up."""
        shutil.rmtree(self.temp_dir)

    def test_full_feedback_cycle(self):
        """Test complete cycle: suggestion shown → completion → confidence update."""
        patterns_file = Path(self.temp_dir) / "patterns.yaml"

        # Simulate suggestion being shown
        suggestion_entry = {
            "type": "suggestion_shown",
            "timestamp": "2026-01-17T10:00:00",
            "objective": "Refactor the auth module",
            "pattern_id": "seed-refactor-module",
            "pattern_source": "seed",
            "confidence": 0.6,
            "approach_verbs": ["scope", "test", "extract", "integrate", "test"]
        }

        mock_entries = [suggestion_entry]

        with patch('feedback_loop.get_suggestion_for_objective') as mock_get, \
             patch('feedback_loop._get_patterns_file') as mock_file, \
             patch('feedback_loop._log_feedback_to_archive'):

            mock_get.return_value = suggestion_entry
            mock_file.return_value = patterns_file

            # Process completion that followed the suggestion
            result = process_completion_feedback(
                objective="Refactor the auth module",
                approach_verbs=["scope", "test", "extract", "integrate", "test"],
                success=True,
                session_id="test-session"
            )

        # Verify feedback result
        self.assertTrue(result.suggestion_found)
        self.assertTrue(result.suggestion_followed)
        self.assertTrue(result.outcome_success)
        self.assertGreater(result.confidence_delta, 0)

        # Verify pattern was updated
        with patch('feedback_loop._get_patterns_file') as mock_file:
            mock_file.return_value = patterns_file
            new_conf = get_pattern_confidence("seed-refactor-module", "seed", default=0.5)

        self.assertGreater(new_conf, 0.6)  # Should have increased


if __name__ == "__main__":
    unittest.main()
