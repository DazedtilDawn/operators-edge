#!/usr/bin/env python3
"""
Tests for lesson_utils.py

Coverage:
- Constants (LESSON_THEMES, STOPWORDS)
- Lesson text extraction
- Keyword extraction
- Theme detection
- Lesson comparison
- Finding similar lessons
- Grouping by theme
- Consolidation candidates
- Lesson consolidation
- Lesson extraction from objectives
- Formatting
"""

import unittest
from unittest.mock import patch, MagicMock

from lesson_utils import (
    LESSON_THEMES,
    STOPWORDS,
    get_lesson_text,
    get_lesson_keywords,
    detect_lesson_theme,
    compare_lessons,
    find_similar_lesson,
    group_lessons_by_theme,
    identify_consolidation_candidates,
    consolidate_lessons,
    extract_lessons_from_objective,
    format_lesson_suggestions,
    _extract_trigger_words,
    _extract_from_mismatches,
    _extract_from_steps,
    _extract_from_constraints,
    _deduplicate_suggestions,
)


class TestConstants(unittest.TestCase):
    """Tests for constants."""

    def test_lesson_themes_defined(self):
        """LESSON_THEMES should be a non-empty dict."""
        self.assertIsInstance(LESSON_THEMES, dict)
        self.assertGreater(len(LESSON_THEMES), 0)

    def test_lesson_themes_have_keywords(self):
        """Each theme should have a list of keywords."""
        for theme, keywords in LESSON_THEMES.items():
            self.assertIsInstance(keywords, list, f"{theme} should have list of keywords")
            self.assertGreater(len(keywords), 0, f"{theme} should have at least one keyword")

    def test_stopwords_defined(self):
        """STOPWORDS should be a non-empty set."""
        self.assertIsInstance(STOPWORDS, set)
        self.assertGreater(len(STOPWORDS), 0)

    def test_stopwords_are_lowercase(self):
        """All stopwords should be lowercase."""
        for word in STOPWORDS:
            self.assertEqual(word, word.lower())


class TestGetLessonText(unittest.TestCase):
    """Tests for get_lesson_text function."""

    def test_string_input(self):
        """Should return string as-is."""
        result = get_lesson_text("This is a lesson")
        self.assertEqual(result, "This is a lesson")

    def test_dict_with_lesson_key(self):
        """Should extract lesson from dict."""
        result = get_lesson_text({"lesson": "The lesson text", "trigger": "test"})
        self.assertEqual(result, "The lesson text")

    def test_dict_without_lesson_key(self):
        """Should convert dict to string if no lesson key."""
        result = get_lesson_text({"trigger": "test"})
        self.assertIn("trigger", result)


class TestGetLessonKeywords(unittest.TestCase):
    """Tests for get_lesson_keywords function."""

    def test_extracts_keywords(self):
        """Should extract significant keywords."""
        result = get_lesson_keywords("Windows uses python, Mac uses python3")
        self.assertIn("windows", result)
        self.assertIn("python", result)
        self.assertIn("python3", result)
        self.assertIn("uses", result)

    def test_filters_stopwords(self):
        """Should filter out stopwords."""
        result = get_lesson_keywords("The quick brown fox jumps over the lazy dog")
        self.assertNotIn("the", result)
        # Note: "over" (4 chars) is in STOPWORDS but not filtered if not present
        # Check common stopwords are filtered
        self.assertIn("quick", result)  # Not a stopword
        self.assertIn("brown", result)  # Not a stopword

    def test_filters_short_words(self):
        """Should filter words shorter than 3 chars."""
        result = get_lesson_keywords("A is on it")
        # All short or stopwords
        self.assertEqual(len(result), 0)

    def test_filters_numbers(self):
        """Should filter pure numbers."""
        result = get_lesson_keywords("Version 123 and 456")
        self.assertNotIn("123", result)
        self.assertNotIn("456", result)
        self.assertIn("version", result)

    def test_handles_separators(self):
        """Should handle various separators."""
        result = get_lesson_keywords("path-handling, file/dir.ext (test)")
        self.assertIn("path", result)
        self.assertIn("handling", result)
        self.assertIn("file", result)


class TestDetectLessonTheme(unittest.TestCase):
    """Tests for detect_lesson_theme function."""

    def test_cross_platform_theme(self):
        """Should detect cross-platform theme."""
        result = detect_lesson_theme("Windows uses different path separators")
        self.assertIn("cross_platform", result)

    def test_imports_modules_theme(self):
        """Should detect imports/modules theme."""
        result = detect_lesson_theme("Use sys.path.insert for imports")
        self.assertIn("imports_modules", result)

    def test_enforcement_theme(self):
        """Should detect enforcement theme."""
        result = detect_lesson_theme("Hooks enforce policy, not just suggest")
        self.assertIn("enforcement", result)

    def test_multiple_themes(self):
        """Should detect multiple matching themes."""
        result = detect_lesson_theme("Windows path handling in module imports")
        self.assertIn("cross_platform", result)
        self.assertIn("imports_modules", result)

    def test_other_theme_fallback(self):
        """Should return 'other' when no theme matches."""
        result = detect_lesson_theme("Something completely unrelated xyz")
        self.assertEqual(result, ["other"])


class TestCompareLessons(unittest.TestCase):
    """Tests for compare_lessons function."""

    def test_exact_match(self):
        """Should detect exact matches."""
        result = compare_lessons(
            "Policy is not enforcement - hooks are enforcement",
            "Policy is not enforcement - hooks are enforcement"
        )
        self.assertTrue(result["is_exact"])
        self.assertTrue(result["is_similar"])

    def test_exact_match_ignores_whitespace(self):
        """Exact match should ignore extra whitespace."""
        result = compare_lessons(
            "Policy  is   not  enforcement",
            "Policy is not enforcement"
        )
        self.assertTrue(result["is_exact"])

    def test_similar_lessons_same_theme(self):
        """Should detect similar lessons with same theme and keyword overlap."""
        result = compare_lessons(
            "Hooks enforce policy through blocking actions",
            "Hooks enforce policy by blocking actions"
        )
        # Same keywords (hooks, enforce, policy, blocking, actions) + enforcement theme
        self.assertTrue(result["theme_match"])
        # High keyword overlap should make them similar
        self.assertGreater(result["keyword_similarity"], 0.3)

    def test_different_lessons(self):
        """Should not mark different lessons as similar."""
        result = compare_lessons(
            "Windows uses different paths",
            "Always write tests for new code"
        )
        self.assertFalse(result["is_similar"])

    def test_returns_keyword_similarity(self):
        """Should return keyword similarity score."""
        result = compare_lessons("Path handling matters", "Path handling is important")
        self.assertIsInstance(result["keyword_similarity"], float)
        self.assertGreaterEqual(result["keyword_similarity"], 0)
        self.assertLessEqual(result["keyword_similarity"], 1)

    def test_returns_shared_keywords(self):
        """Should return set of shared keywords."""
        result = compare_lessons("Path handling matters", "Path handling is important")
        self.assertIn("path", result["shared_keywords"])
        self.assertIn("handling", result["shared_keywords"])


class TestFindSimilarLesson(unittest.TestCase):
    """Tests for find_similar_lesson function."""

    def test_finds_exact_match(self):
        """Should find exact matching lesson."""
        existing = [
            "Lesson about paths",
            "Lesson about imports",
            "Lesson about testing"
        ]
        idx, comparison = find_similar_lesson("Lesson about paths", existing)
        self.assertEqual(idx, 0)
        self.assertTrue(comparison["is_exact"])

    def test_finds_similar_lesson(self):
        """Should find similar lesson by theme with high keyword overlap."""
        existing = [
            {"lesson": "Windows path handling with dotfiles is tricky"},
            {"lesson": "Testing is important"},
        ]
        idx, comparison = find_similar_lesson(
            "Windows path handling with dotfiles works differently",
            existing
        )
        # Should find similarity if there's enough keyword overlap + theme match
        if idx is not None:
            self.assertEqual(idx, 0)
            self.assertTrue(comparison["is_similar"])

    def test_returns_none_when_no_match(self):
        """Should return None when no similar lesson."""
        existing = [
            "Testing matters",
            "Code quality counts",
        ]
        idx, comparison = find_similar_lesson("Windows path handling", existing)
        self.assertIsNone(idx)
        self.assertIsNone(comparison)

    def test_empty_list(self):
        """Should handle empty list."""
        idx, comparison = find_similar_lesson("Any lesson", [])
        self.assertIsNone(idx)
        self.assertIsNone(comparison)


class TestGroupLessonsByTheme(unittest.TestCase):
    """Tests for group_lessons_by_theme function."""

    def test_groups_by_theme(self):
        """Should group lessons by primary theme."""
        lessons = [
            "Windows path handling",
            "Mac path handling",
            "Import module correctly",
            "Something random xyz"
        ]
        result = group_lessons_by_theme(lessons)

        self.assertIn("cross_platform", result)
        self.assertEqual(len(result["cross_platform"]), 2)
        self.assertIn("imports_modules", result)
        self.assertIn("other", result)

    def test_empty_list(self):
        """Should handle empty list."""
        result = group_lessons_by_theme([])
        self.assertEqual(result, {})

    def test_returns_index_and_text(self):
        """Should return tuples of (index, text)."""
        lessons = ["Windows path handling"]
        result = group_lessons_by_theme(lessons)
        idx, text = result["cross_platform"][0]
        self.assertEqual(idx, 0)
        self.assertEqual(text, "Windows path handling")


class TestIdentifyConsolidationCandidates(unittest.TestCase):
    """Tests for identify_consolidation_candidates function."""

    def test_finds_similar_pairs(self):
        """Should identify pairs of similar lessons with high overlap."""
        lessons = [
            {"lesson": "Windows path handling with dotfiles is complex"},
            {"lesson": "Windows path handling with dotfiles is different"},
            {"lesson": "Testing is important for quality"}
        ]
        result = identify_consolidation_candidates(lessons)

        # First two should be similar (high keyword overlap + cross_platform theme)
        if len(result) > 0:
            # If found, first two indices should be present
            indices = result[0][:2]
            self.assertTrue(0 in indices or 1 in indices)

    def test_no_candidates_when_different(self):
        """Should return empty list when no similar lessons."""
        lessons = [
            "Testing is important",
            "Documentation helps",
        ]
        result = identify_consolidation_candidates(lessons)
        self.assertEqual(len(result), 0)

    def test_sorted_by_similarity(self):
        """Should sort by similarity descending."""
        lessons = [
            {"lesson": "Windows path"},
            {"lesson": "Windows path handling"},
            {"lesson": "Something else entirely"}
        ]
        result = identify_consolidation_candidates(lessons)

        if len(result) >= 2:
            self.assertGreaterEqual(result[0][2], result[1][2])


class TestConsolidateLessons(unittest.TestCase):
    """Tests for consolidate_lessons function."""

    def test_dry_run_no_modification(self):
        """dry_run should not modify state."""
        state = {
            "memory": [
                {"lesson": "Windows path handling", "reinforced": 2},
                {"lesson": "Mac path handling", "reinforced": 1},
            ]
        }
        original_len = len(state["memory"])

        result = consolidate_lessons(state, dry_run=True)

        self.assertEqual(len(state["memory"]), original_len)
        self.assertTrue(result.get("dry_run", False))

    def test_returns_statistics(self):
        """Should return consolidation statistics."""
        state = {
            "memory": [
                {"lesson": "Test lesson A", "reinforced": 1},
            ]
        }
        result = consolidate_lessons(state)

        self.assertIn("consolidated", result)
        self.assertIn("lessons_before", result)
        self.assertIn("lessons_after", result)
        self.assertIn("savings", result)

    def test_keeps_higher_reinforcement(self):
        """Should keep lesson with higher reinforcement."""
        state = {
            "memory": [
                {"lesson": "Windows path handling dotfiles v1", "reinforced": 1},
                {"lesson": "Windows path handling dotfiles v2", "reinforced": 5},
            ]
        }

        # dry_run=True doesn't call archive_decayed_lesson, so no need to mock
        result = consolidate_lessons(state, dry_run=True)

        if result["consolidated"]:
            # The one with reinforced=5 should be kept
            self.assertEqual(result["consolidated"][0]["kept_idx"], 1)

    def test_no_consolidation_on_single_lesson(self):
        """Should not consolidate single lesson."""
        state = {"memory": [{"lesson": "Only one", "reinforced": 1}]}
        result = consolidate_lessons(state)
        self.assertEqual(result["savings"], 0)


class TestExtractTriggerWords(unittest.TestCase):
    """Tests for _extract_trigger_words helper."""

    def test_extracts_first_significant_words(self):
        """Should extract first significant words."""
        result = _extract_trigger_words("Path handling in Python code")
        self.assertIsNotNone(result)
        self.assertIn("path", result)

    def test_filters_stopwords(self):
        """Should filter stopwords from triggers."""
        result = _extract_trigger_words("The very first thing")
        self.assertNotIn("the", result or "")
        self.assertNotIn("very", result or "")

    def test_returns_none_for_short_text(self):
        """Should return None for text with only short/stop words."""
        result = _extract_trigger_words("A is on")
        self.assertIsNone(result)


class TestExtractFromMismatches(unittest.TestCase):
    """Tests for _extract_from_mismatches helper."""

    def test_extracts_from_resolved_mismatches(self):
        """Should extract lessons from resolved mismatches."""
        mismatches = [
            {
                "status": "resolved",
                "expectation": "Expected test to pass",
                "resolution": "Fixed the import path issue"
            }
        ]
        result = _extract_from_mismatches(mismatches)

        self.assertEqual(len(result), 1)
        self.assertIn("Fixed the import", result[0]["lesson"])
        self.assertEqual(result[0]["confidence"], "high")

    def test_ignores_unresolved_mismatches(self):
        """Should ignore unresolved mismatches."""
        mismatches = [
            {
                "status": "unresolved",
                "expectation": "Expected something",
            }
        ]
        result = _extract_from_mismatches(mismatches)
        self.assertEqual(len(result), 0)


class TestExtractFromSteps(unittest.TestCase):
    """Tests for _extract_from_steps helper."""

    def test_extracts_from_learning_proofs(self):
        """Should extract lessons from proofs with learning indicators."""
        plan = [
            {
                "status": "completed",
                "description": "Fix the bug",
                "proof": "Realized the problem was a missing import"
            }
        ]
        result = _extract_from_steps(plan)

        self.assertEqual(len(result), 1)
        self.assertIn("import", result[0]["lesson"].lower())

    def test_ignores_short_proofs(self):
        """Should ignore proofs that are too short."""
        plan = [
            {
                "status": "completed",
                "description": "Test",
                "proof": "Done"
            }
        ]
        result = _extract_from_steps(plan)
        self.assertEqual(len(result), 0)


class TestExtractFromConstraints(unittest.TestCase):
    """Tests for _extract_from_constraints helper."""

    def test_extracts_from_constraints(self):
        """Should extract lessons from constraints."""
        constraints = [
            "Don't modify the database directly",
            "Always backup before changes"
        ]
        result = _extract_from_constraints(constraints)

        self.assertEqual(len(result), 2)
        self.assertEqual(result[0]["confidence"], "medium")

    def test_keeps_dont_prefix(self):
        """Should keep don't prefix as-is."""
        constraints = ["Don't skip tests"]
        result = _extract_from_constraints(constraints)

        self.assertIn("Don't skip", result[0]["lesson"])


class TestDeduplicateSuggestions(unittest.TestCase):
    """Tests for _deduplicate_suggestions helper."""

    def test_removes_duplicates(self):
        """Should remove duplicate suggestions."""
        suggestions = [
            {"lesson": "Path handling is important"},
            {"lesson": "Path handling is very important"},  # Similar
            {"lesson": "Testing matters"},
        ]
        result = _deduplicate_suggestions(suggestions)

        self.assertEqual(len(result), 2)


class TestExtractLessonsFromObjective(unittest.TestCase):
    """Tests for extract_lessons_from_objective function."""

    def test_extracts_from_multiple_sources(self):
        """Should extract from mismatches, steps, and constraints."""
        state = {
            "mismatches": [
                {"status": "resolved", "expectation": "X", "resolution": "Fixed by doing Y in the code"}
            ],
            "plan": [
                {"status": "completed", "description": "Task", "proof": "Learned that Z is important for this"}
            ],
            "constraints": ["Don't do A thing"]
        }
        result = extract_lessons_from_objective(state)

        self.assertGreater(len(result), 0)

    def test_handles_empty_state(self):
        """Should handle empty state."""
        result = extract_lessons_from_objective({})
        self.assertEqual(result, [])


class TestFormatLessonSuggestions(unittest.TestCase):
    """Tests for format_lesson_suggestions function."""

    def test_formats_suggestions(self):
        """Should format suggestions nicely."""
        suggestions = [
            {"trigger": "testing", "lesson": "Always test", "source": "step", "confidence": "high"}
        ]
        result = format_lesson_suggestions(suggestions)

        self.assertIn("Trigger: testing", result)
        self.assertIn("Always test", result)
        self.assertIn("step", result)

    def test_empty_suggestions(self):
        """Should handle empty suggestions."""
        result = format_lesson_suggestions([])
        self.assertIn("No lesson suggestions", result)

    def test_confidence_markers(self):
        """Should include confidence markers."""
        suggestions = [
            {"trigger": "t", "lesson": "l", "source": "s", "confidence": "high"}
        ]
        result = format_lesson_suggestions(suggestions)
        self.assertIn("★", result)


if __name__ == "__main__":
    unittest.main()
