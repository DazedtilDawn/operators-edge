#!/usr/bin/env python3
"""
Tests for orchestration_utils.py - session context and memory management.

Tests the core functions for:
- Session context detection
- Memory surfacing and management
- Lesson similarity and consolidation
- Score pattern analysis
"""
import os
import sys
import unittest
from unittest.mock import patch, MagicMock

# Add hooks directory to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from edge_config import SessionContext


class TestDetectSessionContext(unittest.TestCase):
    """Tests for detect_session_context() function."""

    @patch('context_utils.get_blocking_research')
    @patch('context_utils.get_unresolved_mismatches')
    @patch('context_utils.check_state_entropy')
    @patch('context_utils.get_step_by_status')
    def test_no_state_needs_plan(self, mock_steps, mock_entropy, mock_mismatch, mock_research):
        """No state should return NEEDS_PLAN."""
        from orchestration_utils import detect_session_context

        context, details = detect_session_context(None)
        self.assertEqual(context, SessionContext.NEEDS_PLAN)

    @patch('context_utils.get_blocking_research')
    @patch('context_utils.get_unresolved_mismatches')
    @patch('context_utils.check_state_entropy')
    @patch('context_utils.get_step_by_status')
    def test_empty_plan_needs_plan(self, mock_steps, mock_entropy, mock_mismatch, mock_research):
        """Empty plan should return NEEDS_PLAN."""
        from orchestration_utils import detect_session_context

        state = {"objective": "Test", "plan": []}
        context, details = detect_session_context(state)
        self.assertEqual(context, SessionContext.NEEDS_PLAN)

    @patch('context_utils.get_blocking_research')
    @patch('context_utils.get_unresolved_mismatches')
    @patch('context_utils.check_state_entropy')
    @patch('context_utils.get_step_by_status')
    def test_blocking_research_detected(self, mock_steps, mock_entropy, mock_mismatch, mock_research):
        """Blocking research should return NEEDS_RESEARCH."""
        from orchestration_utils import detect_session_context

        mock_research.return_value = [{"status": "pending", "priority": "critical"}]
        mock_mismatch.return_value = []
        mock_entropy.return_value = (False, [])

        state = {"objective": "Test", "plan": [{"status": "pending"}]}
        context, details = detect_session_context(state)
        self.assertEqual(context, SessionContext.NEEDS_RESEARCH)

    @patch('context_utils.get_blocking_research')
    @patch('context_utils.get_unresolved_mismatches')
    @patch('context_utils.check_state_entropy')
    @patch('context_utils.get_step_by_status')
    def test_unresolved_mismatch_needs_adaptation(self, mock_steps, mock_entropy, mock_mismatch, mock_research):
        """Unresolved mismatch should return NEEDS_ADAPTATION."""
        from orchestration_utils import detect_session_context

        mock_research.return_value = []
        mock_mismatch.return_value = [{"id": "m1"}]
        mock_entropy.return_value = (False, [])

        state = {"objective": "Test", "plan": [{"status": "pending"}]}
        context, details = detect_session_context(state)
        self.assertEqual(context, SessionContext.NEEDS_ADAPTATION)


class TestGetOrchestratorSuggestion(unittest.TestCase):
    """Tests for get_orchestrator_suggestion() function."""

    def test_needs_plan_suggestion(self):
        """NEEDS_PLAN should suggest /edge-plan."""
        from orchestration_utils import get_orchestrator_suggestion

        suggestion = get_orchestrator_suggestion(SessionContext.NEEDS_PLAN, {})
        self.assertEqual(suggestion["command"], "/edge-plan")

    def test_ready_for_step_suggestion(self):
        """READY_FOR_STEP should suggest /edge-step."""
        from orchestration_utils import get_orchestrator_suggestion

        suggestion = get_orchestrator_suggestion(SessionContext.READY_FOR_STEP, {"next_step": {}})
        self.assertEqual(suggestion["command"], "/edge-step")


class TestSurfaceRelevantMemory(unittest.TestCase):
    """Tests for surface_relevant_memory() function."""

    def test_finds_matching_memory(self):
        """surface_relevant_memory() should find memories with matching triggers."""
        from orchestration_utils import surface_relevant_memory

        state = {
            "memory": [
                {"trigger": "windows", "lesson": "Use pathlib", "reinforced": 2},
                {"trigger": "api calls", "lesson": "Handle errors", "reinforced": 1}
            ]
        }

        # Context must contain >50% of trigger words for a match
        # Single word trigger "windows" in context "windows problem" should match
        result = surface_relevant_memory(state, "windows problem")

        self.assertEqual(len(result), 1)
        self.assertIn("pathlib", result[0]["lesson"])

    @patch('memory_utils.get_memory_items')
    def test_returns_empty_for_no_match(self, mock_memory):
        """surface_relevant_memory() should return empty for no matches."""
        from orchestration_utils import surface_relevant_memory

        mock_memory.return_value = [
            {"trigger": "database migration", "lesson": "Backup first", "reinforced": 1}
        ]

        result = surface_relevant_memory({}, "Fix CSS styling")
        self.assertEqual(len(result), 0)


class TestReinforceMemory(unittest.TestCase):
    """Tests for reinforce_memory() function."""

    def test_reinforces_matching_memory(self):
        """reinforce_memory() should increment reinforced count."""
        from orchestration_utils import reinforce_memory

        state = {
            "memory": [
                {"trigger": "test trigger", "lesson": "test", "reinforced": 1}
            ]
        }

        result = reinforce_memory(state, "test trigger")

        self.assertTrue(result)
        self.assertEqual(state["memory"][0]["reinforced"], 2)

    def test_returns_false_for_no_match(self):
        """reinforce_memory() should return False if not found."""
        from orchestration_utils import reinforce_memory

        state = {"memory": [{"trigger": "other", "reinforced": 1}]}
        result = reinforce_memory(state, "nonexistent")
        self.assertFalse(result)


class TestAddMemoryItem(unittest.TestCase):
    """Tests for add_memory_item() function."""

    def test_adds_new_memory(self):
        """add_memory_item() should add new item."""
        from orchestration_utils import add_memory_item

        state = {"session": {"id": "test-session"}}
        item = add_memory_item(state, "new trigger", "new lesson", dedup=False)

        self.assertEqual(item["trigger"], "new trigger")
        self.assertEqual(item["lesson"], "new lesson")
        self.assertIn("memory", state)

    @patch('lesson_utils.find_similar_lesson')
    def test_deduplicates_similar(self, mock_find):
        """add_memory_item() should deduplicate similar lessons."""
        from orchestration_utils import add_memory_item

        mock_find.return_value = (0, {"is_similar": True, "keyword_similarity": 0.5})

        state = {
            "memory": [{"trigger": "existing", "lesson": "existing lesson", "reinforced": 1}]
        }

        item = add_memory_item(state, "new trigger", "similar lesson", dedup=True)

        self.assertTrue(item.get("deduplicated"))
        self.assertEqual(state["memory"][0]["reinforced"], 2)


class TestGetMemorySummary(unittest.TestCase):
    """Tests for get_memory_summary() function."""

    @patch('memory_utils.get_memory_items')
    def test_summarizes_memory(self, mock_memory):
        """get_memory_summary() should return correct counts."""
        from orchestration_utils import get_memory_summary

        mock_memory.return_value = [
            {"trigger": "a", "reinforced": 3},  # high value
            {"trigger": "b", "reinforced": 0},  # at risk
            {"trigger": "c", "reinforced": 1}
        ]

        summary = get_memory_summary({})

        self.assertEqual(summary["count"], 3)
        self.assertEqual(summary["high_value"], 1)
        self.assertEqual(summary["at_risk"], 1)


class TestLessonSimilarity(unittest.TestCase):
    """Tests for lesson similarity functions."""

    def test_get_lesson_keywords(self):
        """get_lesson_keywords() should extract significant words."""
        from orchestration_utils import get_lesson_keywords

        keywords = get_lesson_keywords("Windows uses python, Mac uses python3")

        self.assertIn("windows", keywords)
        self.assertIn("python", keywords)
        self.assertIn("python3", keywords)
        self.assertNotIn("the", keywords)  # stopword

    def test_detect_lesson_theme(self):
        """detect_lesson_theme() should identify themes."""
        from orchestration_utils import detect_lesson_theme

        themes = detect_lesson_theme("Windows and Mac have different paths")

        self.assertIn("cross_platform", themes)

    def test_compare_lessons_exact(self):
        """compare_lessons() should detect exact matches."""
        from orchestration_utils import compare_lessons

        result = compare_lessons(
            "Use pathlib for paths",
            "Use pathlib for paths"
        )

        self.assertTrue(result["is_exact"])
        self.assertTrue(result["is_similar"])

    def test_compare_lessons_similar(self):
        """compare_lessons() should detect similar lessons."""
        from orchestration_utils import compare_lessons

        result = compare_lessons(
            "Windows uses python, Mac uses python3",
            "Mac uses python3, Windows uses python command"
        )

        self.assertTrue(result["is_similar"])
        self.assertGreater(result["keyword_similarity"], 0.3)

    def test_compare_lessons_different(self):
        """compare_lessons() should detect different lessons."""
        from orchestration_utils import compare_lessons

        result = compare_lessons(
            "Use pathlib for paths",
            "Always handle API errors gracefully"
        )

        self.assertFalse(result["is_similar"])


class TestFindSimilarLesson(unittest.TestCase):
    """Tests for find_similar_lesson() function."""

    def test_finds_exact_match(self):
        """find_similar_lesson() should find exact matches."""
        from orchestration_utils import find_similar_lesson

        existing = [
            "Use pathlib for paths",
            "Handle errors gracefully"
        ]

        idx, result = find_similar_lesson("Use pathlib for paths", existing)

        self.assertEqual(idx, 0)
        self.assertTrue(result["is_exact"])

    def test_finds_similar_match(self):
        """find_similar_lesson() should find similar matches."""
        from orchestration_utils import find_similar_lesson

        existing = [
            {"lesson": "Windows uses python, Mac uses python3"}
        ]

        idx, result = find_similar_lesson(
            "Mac uses python3, Windows uses python command",
            existing
        )

        self.assertEqual(idx, 0)
        self.assertTrue(result["is_similar"])


class TestAnalyzeScorePatterns(unittest.TestCase):
    """Tests for analyze_score_patterns() function."""

    def test_analyzes_objectives(self):
        """analyze_score_patterns() should calculate stats."""
        from orchestration_utils import analyze_score_patterns

        entries = [
            {"type": "completed_objective", "score": {"total": 4, "level": "promising_fragile"}},
            {"type": "completed_objective", "score": {"total": 5, "level": "real_agent"}},
            {"type": "completed_objective", "score": {"total": 6, "level": "real_agent"}}
        ]

        analysis = analyze_score_patterns(entries)

        self.assertEqual(analysis["total_objectives"], 3)
        self.assertEqual(analysis["avg_score"], 5.0)
        self.assertEqual(analysis["level_distribution"]["real_agent"], 2)

    def test_handles_empty(self):
        """analyze_score_patterns() should handle empty entries."""
        from orchestration_utils import analyze_score_patterns

        analysis = analyze_score_patterns([])

        self.assertEqual(analysis["total_objectives"], 0)
        self.assertEqual(analysis["avg_score"], 0)

    def test_handles_self_score_key(self):
        """analyze_score_patterns() should support self_score key."""
        from orchestration_utils import analyze_score_patterns

        entries = [
            {"type": "completed_objective", "self_score": {"total": 5, "level": "real_agent"}},
            {"type": "completed_objective", "score": {"total": 6, "level": "real_agent"}}
        ]

        analysis = analyze_score_patterns(entries)

        self.assertEqual(analysis["avg_score"], 5.5)
        self.assertEqual(analysis["level_distribution"]["real_agent"], 2)

    def test_excludes_entries_without_score(self):
        """analyze_score_patterns() should not count entries without score in average."""
        from orchestration_utils import analyze_score_patterns

        entries = [
            {"type": "completed_objective", "score": {"total": 6, "level": "real_agent"}},
            {"type": "completed_objective"},  # No score
            {"type": "completed_objective", "version": "v2.7"}  # No score
        ]

        analysis = analyze_score_patterns(entries)

        # Only 1 entry should be in average
        self.assertEqual(analysis["avg_score"], 6.0)
        # But all 3 should be counted in total
        self.assertEqual(analysis["total_objectives"], 3)
        # Unknown should have 2 entries
        self.assertEqual(analysis["level_distribution"].get("unknown", 0), 2)


class TestGetRecurringFailures(unittest.TestCase):
    """Tests for get_recurring_failures() function."""

    @patch('reflection_utils.analyze_score_patterns')
    def test_finds_recurring_failures(self, mock_analyze):
        """get_recurring_failures() should find checks failing multiple times."""
        from orchestration_utils import get_recurring_failures

        mock_analyze.return_value = {
            "check_failures": {
                "mismatch_detection": 3,
                "plan_revision": 1,
                "tool_switching": 2
            }
        }

        recurring = get_recurring_failures([])

        self.assertEqual(len(recurring), 2)
        self.assertEqual(recurring[0]["check"], "mismatch_detection")


if __name__ == '__main__':
    unittest.main()
