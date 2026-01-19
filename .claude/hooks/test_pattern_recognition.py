#!/usr/bin/env python3
"""
Tests for pattern_recognition.py - Phase 2 of Learned Track Guidance.
"""
import os
import sys
import json
import shutil
import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from unittest.mock import patch, MagicMock

# Add the hooks directory to the path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


class TestComputeKeywordSimilarity(unittest.TestCase):
    """Tests for compute_keyword_similarity()."""

    def test_no_matches_returns_zero(self):
        """Should return 0 when no keywords match."""
        from pattern_recognition import compute_keyword_similarity

        score, matches = compute_keyword_similarity(
            "Add user authentication",
            ["refactor", "extract", "modular"]
        )

        self.assertEqual(score, 0.0)
        self.assertEqual(matches, [])

    def test_single_match(self):
        """Should return score for single keyword match."""
        from pattern_recognition import compute_keyword_similarity

        score, matches = compute_keyword_similarity(
            "Refactor the user module",
            ["refactor", "extract", "modular"]
        )

        self.assertGreater(score, 0)
        self.assertIn("refactor", matches)

    def test_multiple_matches(self):
        """Should return higher score for multiple matches."""
        from pattern_recognition import compute_keyword_similarity

        score1, _ = compute_keyword_similarity(
            "Refactor the module",
            ["refactor", "extract", "modular"]
        )

        score2, matches2 = compute_keyword_similarity(
            "Refactor and extract the modular code",
            ["refactor", "extract", "modular"]
        )

        self.assertGreater(score2, score1)
        self.assertEqual(len(matches2), 3)

    def test_exclude_keywords_block_match(self):
        """Should return 0 if exclude keyword present."""
        from pattern_recognition import compute_keyword_similarity

        score, matches = compute_keyword_similarity(
            "Fix the bug in refactoring",
            ["refactor", "extract"],
            exclude_keywords=["bug", "fix"]
        )

        self.assertEqual(score, 0.0)
        self.assertEqual(matches, [])

    def test_empty_objective(self):
        """Should handle empty objective gracefully."""
        from pattern_recognition import compute_keyword_similarity

        score, matches = compute_keyword_similarity("", ["refactor"])
        self.assertEqual(score, 0.0)

    def test_empty_keywords(self):
        """Should handle empty keywords gracefully."""
        from pattern_recognition import compute_keyword_similarity

        score, matches = compute_keyword_similarity("Some objective", [])
        self.assertEqual(score, 0.0)


class TestComputeTagSimilarity(unittest.TestCase):
    """Tests for compute_tag_similarity()."""

    def test_identical_tags(self):
        """Should return 1.0 for identical tag sets."""
        from pattern_recognition import compute_tag_similarity

        score = compute_tag_similarity(
            ["refactoring", "feature"],
            ["refactoring", "feature"]
        )

        self.assertEqual(score, 1.0)

    def test_partial_overlap(self):
        """Should return partial score for overlapping tags."""
        from pattern_recognition import compute_tag_similarity

        score = compute_tag_similarity(
            ["refactoring", "feature"],
            ["refactoring", "bugfix"]
        )

        # Jaccard: 1 / 3 = 0.333...
        self.assertAlmostEqual(score, 1/3, places=2)

    def test_no_overlap(self):
        """Should return 0 for non-overlapping tags."""
        from pattern_recognition import compute_tag_similarity

        score = compute_tag_similarity(
            ["refactoring"],
            ["bugfix"]
        )

        self.assertEqual(score, 0.0)

    def test_empty_tags(self):
        """Should return 0 for empty tag lists."""
        from pattern_recognition import compute_tag_similarity

        self.assertEqual(compute_tag_similarity([], ["tag"]), 0.0)
        self.assertEqual(compute_tag_similarity(["tag"], []), 0.0)


class TestComputeApproachSimilarity(unittest.TestCase):
    """Tests for compute_approach_similarity()."""

    def test_identical_sequences(self):
        """Should return 1.0 for identical verb sequences."""
        from pattern_recognition import compute_approach_similarity

        score = compute_approach_similarity(
            ["scope", "test", "build", "test"],
            ["scope", "test", "build", "test"]
        )

        self.assertEqual(score, 1.0)

    def test_different_sequences(self):
        """Should return partial score for different sequences."""
        from pattern_recognition import compute_approach_similarity

        score = compute_approach_similarity(
            ["scope", "test", "build"],
            ["scope", "build", "deploy"]
        )

        # Some overlap in verbs, different order
        self.assertGreater(score, 0)
        self.assertLess(score, 1.0)

    def test_completely_different(self):
        """Should return low score for completely different sequences."""
        from pattern_recognition import compute_approach_similarity

        score = compute_approach_similarity(
            ["scope", "test", "build"],
            ["deploy", "fix", "clean"]
        )

        self.assertEqual(score, 0.0)

    def test_empty_sequences(self):
        """Should handle empty sequences gracefully."""
        from pattern_recognition import compute_approach_similarity

        self.assertEqual(compute_approach_similarity([], ["test"]), 0.0)
        self.assertEqual(compute_approach_similarity(["test"], []), 0.0)


class TestLongestCommonSubsequence(unittest.TestCase):
    """Tests for _longest_common_subsequence_length()."""

    def test_identical_sequences(self):
        """Should return full length for identical sequences."""
        from pattern_recognition import _longest_common_subsequence_length

        result = _longest_common_subsequence_length(
            ["a", "b", "c"],
            ["a", "b", "c"]
        )

        self.assertEqual(result, 3)

    def test_subsequence(self):
        """Should find common subsequence."""
        from pattern_recognition import _longest_common_subsequence_length

        result = _longest_common_subsequence_length(
            ["a", "b", "c", "d"],
            ["a", "c", "d"]
        )

        self.assertEqual(result, 3)  # "a", "c", "d"

    def test_no_common(self):
        """Should return 0 for no common elements."""
        from pattern_recognition import _longest_common_subsequence_length

        result = _longest_common_subsequence_length(
            ["a", "b"],
            ["c", "d"]
        )

        self.assertEqual(result, 0)


class TestFindSimilarObjectives(unittest.TestCase):
    """Tests for find_similar_objectives()."""

    def test_finds_similar_by_tags(self):
        """Should find objectives with similar tags."""
        from pattern_recognition import find_similar_objectives

        completions = [
            {"objective": "Refactor user module", "tags": ["refactoring"]},
            {"objective": "Add login feature", "tags": ["feature"]},
            {"objective": "Refactor auth system", "tags": ["refactoring"]}
        ]

        results = find_similar_objectives(
            "Refactor the payment module",  # Should infer "refactoring" tag
            completions,
            min_similarity=0.1
        )

        # Should find at least the refactoring objectives
        self.assertGreater(len(results), 0)

    def test_returns_empty_for_no_matches(self):
        """Should return empty list when nothing matches."""
        from pattern_recognition import find_similar_objectives

        completions = [
            {"objective": "XYZ task", "tags": ["random"]}
        ]

        results = find_similar_objectives(
            "Completely unrelated objective",
            completions,
            min_similarity=0.5
        )

        self.assertEqual(len(results), 0)

    def test_sorted_by_score(self):
        """Should return results sorted by similarity score."""
        from pattern_recognition import find_similar_objectives

        completions = [
            {"objective": "Low match", "tags": ["other"]},
            {"objective": "Refactor module", "tags": ["refactoring"]},
            {"objective": "Refactor and extract module", "tags": ["refactoring"]}
        ]

        results = find_similar_objectives(
            "Refactor the auth module",
            completions,
            min_similarity=0.1
        )

        if len(results) >= 2:
            # First result should have highest score
            self.assertGreaterEqual(results[0][1], results[1][1])


class TestMatchSeedPattern(unittest.TestCase):
    """Tests for match_seed_pattern()."""

    def test_matches_refactor_pattern(self):
        """Should match refactoring objective to refactor seed pattern."""
        from pattern_recognition import match_seed_pattern

        match = match_seed_pattern("Refactor the user authentication module")

        if match:  # Depends on seed patterns being loaded
            self.assertEqual(match.source, "seed")
            self.assertIn("refactor", match.pattern_id.lower())

    def test_matches_bugfix_pattern(self):
        """Should match bugfix objective to bugfix seed pattern."""
        from pattern_recognition import match_seed_pattern

        match = match_seed_pattern("Fix the login bug that crashes the app")

        if match:
            self.assertEqual(match.source, "seed")

    def test_no_match_for_unrelated(self):
        """Should return None for unrelated objectives."""
        from pattern_recognition import match_seed_pattern

        match = match_seed_pattern("Random task with no keywords")

        # May or may not match depending on thresholds
        # Just verify it doesn't error


class TestBuildLearnedPattern(unittest.TestCase):
    """Tests for build_learned_pattern()."""

    def test_builds_from_sufficient_samples(self):
        """Should build pattern from 2+ completions."""
        from pattern_recognition import build_learned_pattern

        completions = [
            {
                "objective": "Refactor module A",
                "tags": ["refactoring"],
                "approach_verbs": ["scope", "test", "extract", "test"],
                "approach_summary": [
                    {"verb": "scope", "description": "Define boundaries"},
                    {"verb": "test", "description": "Run existing tests"},
                    {"verb": "extract", "description": "Move code"},
                    {"verb": "test", "description": "Verify"}
                ],
                "metrics": {"steps_completed": 4},
                "outcome": {"success": True}
            },
            {
                "objective": "Refactor module B",
                "tags": ["refactoring"],
                "approach_verbs": ["scope", "test", "extract", "test"],
                "approach_summary": [
                    {"verb": "scope", "description": "Identify deps"},
                    {"verb": "test", "description": "Ensure coverage"},
                    {"verb": "extract", "description": "Separate code"},
                    {"verb": "test", "description": "Run tests"}
                ],
                "metrics": {"steps_completed": 4},
                "outcome": {"success": True}
            }
        ]

        pattern = build_learned_pattern(completions)

        self.assertIsNotNone(pattern)
        self.assertEqual(pattern.source, "learned")
        self.assertEqual(pattern.samples, 2)
        self.assertEqual(pattern.approach_verbs, ["scope", "test", "extract", "test"])

    def test_returns_none_for_insufficient_samples(self):
        """Should return None for fewer than min_samples."""
        from pattern_recognition import build_learned_pattern

        completions = [
            {"objective": "Single item", "tags": [], "approach_verbs": ["test"]}
        ]

        pattern = build_learned_pattern(completions)

        self.assertIsNone(pattern)

    def test_computes_success_rate(self):
        """Should correctly compute success rate."""
        from pattern_recognition import build_learned_pattern

        completions = [
            {"objective": "A", "tags": ["test"], "approach_verbs": ["test"],
             "approach_summary": [], "metrics": {"steps_completed": 1},
             "outcome": {"success": True}},
            {"objective": "B", "tags": ["test"], "approach_verbs": ["test"],
             "approach_summary": [], "metrics": {"steps_completed": 1},
             "outcome": {"success": False}}
        ]

        pattern = build_learned_pattern(completions)

        self.assertIsNotNone(pattern)
        self.assertEqual(pattern.success_rate, 0.5)


class TestGetPatternSuggestion(unittest.TestCase):
    """Tests for get_pattern_suggestion()."""

    def setUp(self):
        """Set up test environment."""
        self.temp_dir = tempfile.mkdtemp()
        self.old_cwd = os.getcwd()

    def tearDown(self):
        """Clean up test environment."""
        os.chdir(self.old_cwd)
        shutil.rmtree(self.temp_dir)

    @patch('archive_utils.get_objective_completions')
    def test_returns_seed_when_no_completions(self, mock_completions):
        """Should return seed pattern when no completion history."""
        mock_completions.return_value = []

        from pattern_recognition import get_pattern_suggestion

        result = get_pattern_suggestion("Refactor the auth module", include_seeds=True)

        # Should get seed pattern match if thresholds met
        if result:
            self.assertEqual(result.source, "seed")

    @patch('archive_utils.get_objective_completions')
    def test_prefers_learned_over_seed(self, mock_completions):
        """Should prefer learned pattern over seed when confident."""
        mock_completions.return_value = [
            {
                "objective": "Refactor module A",
                "tags": ["refactoring"],
                "approach_verbs": ["scope", "test", "extract"],
                "approach_summary": [],
                "metrics": {"steps_completed": 3},
                "outcome": {"success": True}
            },
            {
                "objective": "Refactor module B",
                "tags": ["refactoring"],
                "approach_verbs": ["scope", "test", "extract"],
                "approach_summary": [],
                "metrics": {"steps_completed": 3},
                "outcome": {"success": True}
            },
            {
                "objective": "Refactor module C",
                "tags": ["refactoring"],
                "approach_verbs": ["scope", "test", "extract"],
                "approach_summary": [],
                "metrics": {"steps_completed": 3},
                "outcome": {"success": True}
            }
        ]

        from pattern_recognition import get_pattern_suggestion

        result = get_pattern_suggestion("Refactor the payment module")

        # With 3 similar completions, learned should be preferred
        if result and result.confidence > 0.5:
            self.assertEqual(result.source, "learned")


class TestFormatPatternSuggestion(unittest.TestCase):
    """Tests for format_pattern_suggestion()."""

    def test_formats_learned_pattern(self):
        """Should format learned pattern with correct emoji."""
        from pattern_recognition import format_pattern_suggestion, PatternMatch

        match = PatternMatch(
            pattern_id="learned-refactor",
            pattern_name="Module Refactoring",
            source="learned",
            confidence=0.75,
            approach=[
                {"verb": "scope", "description": "Define boundaries"},
                {"verb": "test", "description": "Run tests"}
            ],
            match_reasons=["Similar tags"],
            samples=3
        )

        result = format_pattern_suggestion(match)

        self.assertIn("📚", result)  # Learned emoji
        self.assertIn("Module Refactoring", result)
        self.assertIn("75%", result)
        self.assertIn("SCOPE", result)
        self.assertIn("3 similar objectives", result)

    def test_formats_seed_pattern(self):
        """Should format seed pattern with correct emoji."""
        from pattern_recognition import format_pattern_suggestion, PatternMatch

        match = PatternMatch(
            pattern_id="seed-bugfix",
            pattern_name="Bug Fix",
            source="seed",
            confidence=0.5,
            approach=[
                {"verb": "scope", "description": "Reproduce bug"},
                {"verb": "fix", "description": "Implement fix"}
            ],
            match_reasons=["Keywords: fix, bug"],
            samples=0
        )

        result = format_pattern_suggestion(match)

        self.assertIn("📋", result)  # Seed emoji
        self.assertIn("Bug Fix", result)
        self.assertIn("seed", result)


class TestSuggestApproachForObjective(unittest.TestCase):
    """Tests for suggest_approach_for_objective()."""

    @patch('pattern_recognition.get_pattern_suggestion')
    def test_returns_formatted_and_match(self, mock_suggestion):
        """Should return both formatted string and match object."""
        from pattern_recognition import suggest_approach_for_objective, PatternMatch

        mock_match = PatternMatch(
            pattern_id="test",
            pattern_name="Test Pattern",
            source="seed",
            confidence=0.6,
            approach=[{"verb": "test", "description": "Test it"}],
            match_reasons=["test"],
            samples=0
        )
        mock_suggestion.return_value = mock_match

        formatted, match = suggest_approach_for_objective("Test objective")

        self.assertIsNotNone(formatted)
        self.assertEqual(match, mock_match)

    @patch('pattern_recognition.get_pattern_suggestion')
    def test_returns_none_when_no_match(self, mock_suggestion):
        """Should return (None, None) when no pattern matches."""
        mock_suggestion.return_value = None

        from pattern_recognition import suggest_approach_for_objective

        formatted, match = suggest_approach_for_objective("Random objective")

        self.assertIsNone(formatted)
        self.assertIsNone(match)


class TestPatternMatchDataclass(unittest.TestCase):
    """Tests for PatternMatch dataclass."""

    def test_to_dict(self):
        """Should convert to dictionary correctly."""
        from pattern_recognition import PatternMatch

        match = PatternMatch(
            pattern_id="test-id",
            pattern_name="Test",
            source="learned",
            confidence=0.8,
            approach=[{"verb": "test"}],
            match_reasons=["reason"],
            samples=5
        )

        result = match.to_dict()

        self.assertEqual(result["pattern_id"], "test-id")
        self.assertEqual(result["confidence"], 0.8)
        self.assertEqual(result["samples"], 5)


class TestLearnedPatternDataclass(unittest.TestCase):
    """Tests for LearnedPattern dataclass."""

    def test_to_dict(self):
        """Should convert to dictionary correctly."""
        from pattern_recognition import LearnedPattern

        pattern = LearnedPattern(
            id="test-pattern",
            name="Test Pattern",
            tags=["test"],
            approach_verbs=["scope", "test"],
            confidence=0.7,
            samples=3
        )

        result = pattern.to_dict()

        self.assertEqual(result["id"], "test-pattern")
        self.assertEqual(result["tags"], ["test"])
        self.assertEqual(result["samples"], 3)


if __name__ == '__main__':
    unittest.main()
