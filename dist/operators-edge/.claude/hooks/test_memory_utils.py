#!/usr/bin/env python3
"""
Tests for memory_utils.py

Coverage:
- surface_relevant_memory: Finding memory by trigger match
- reinforce_memory: Increasing reinforcement counts
- add_memory_item: Adding new items with deduplication
- retrieve_from_archive: Archive search wrapper
- resurrect_archived_lesson: Bringing back archived lessons
- get_memory_summary: Memory statistics
"""

import unittest
from unittest.mock import patch, MagicMock
from datetime import datetime

import memory_utils


class TestSurfaceRelevantMemory(unittest.TestCase):
    """Tests for surface_relevant_memory function."""

    def test_returns_empty_when_no_state(self):
        """Should return empty list when state is None."""
        result = memory_utils.surface_relevant_memory(None, "test context")
        self.assertEqual(result, [])

    def test_returns_empty_when_no_context(self):
        """Should return empty list when context is empty."""
        result = memory_utils.surface_relevant_memory({}, "")
        self.assertEqual(result, [])

    @patch('state_utils.get_memory_items')
    def test_returns_empty_when_no_memory(self, mock_get):
        """Should return empty list when no memory items."""
        mock_get.return_value = []
        result = memory_utils.surface_relevant_memory({}, "test context")
        self.assertEqual(result, [])

    def test_finds_matching_trigger(self):
        """Should find memory items with matching trigger."""
        # Test directly with state that has memory
        state = {
            "memory": [
                {"trigger": "windows", "lesson": "Use pathlib", "reinforced": 2},
                {"trigger": "testing", "lesson": "Write tests", "reinforced": 1},
            ]
        }
        result = memory_utils.surface_relevant_memory(state, "handling windows issues")

        self.assertGreater(len(result), 0)
        self.assertEqual(result[0]["trigger"], "windows")

    def test_skips_non_dict_items(self):
        """Should skip non-dict memory items."""
        state = {
            "memory": [
                "old string format",
                {"trigger": "test", "lesson": "Lesson", "reinforced": 1}
            ]
        }
        result = memory_utils.surface_relevant_memory(state, "test context here")
        # Should only process the dict item
        self.assertTrue(all(isinstance(r, dict) for r in result))

    def test_skips_empty_triggers(self):
        """Should skip items with empty triggers."""
        state = {
            "memory": [
                {"trigger": "", "lesson": "No trigger", "reinforced": 1},
                {"trigger": "valid", "lesson": "Valid lesson", "reinforced": 1},
            ]
        }
        result = memory_utils.surface_relevant_memory(state, "valid context test")
        # Should only find the valid one
        if result:
            self.assertNotEqual(result[0]["trigger"], "")

    def test_skips_wildcard_triggers(self):
        """Should skip items with * wildcard triggers."""
        state = {
            "memory": [
                {"trigger": "*", "lesson": "Wildcard", "reinforced": 1},
            ]
        }
        result = memory_utils.surface_relevant_memory(state, "any context")
        self.assertEqual(result, [])

    def test_requires_majority_word_match(self):
        """Should require >50% of trigger words to match."""
        state = {
            "memory": [
                {"trigger": "windows mac linux", "lesson": "L1", "reinforced": 1},
            ]
        }
        # Only 1 of 3 words matches (33%, not >50%)
        result = memory_utils.surface_relevant_memory(state, "using windows only")
        self.assertEqual(len(result), 0)

        # 2 of 3 words match (66%, >50%)
        result = memory_utils.surface_relevant_memory(state, "windows and mac support")
        self.assertEqual(len(result), 1)

    def test_sorts_by_score_and_reinforcement(self):
        """Should sort by match score then reinforcement."""
        state = {
            "memory": [
                {"trigger": "test", "lesson": "Low reinforced", "reinforced": 1},
                {"trigger": "test", "lesson": "High reinforced", "reinforced": 10},
            ]
        }
        result = memory_utils.surface_relevant_memory(state, "test context here")

        # Higher reinforcement should come first when scores equal
        if len(result) >= 2:
            self.assertGreaterEqual(result[0]["reinforced"], result[1]["reinforced"])

    def test_limits_to_three_results(self):
        """Should return at most 3 results."""
        state = {
            "memory": [
                {"trigger": "test", "lesson": f"Lesson {i}", "reinforced": i}
                for i in range(10)
            ]
        }
        result = memory_utils.surface_relevant_memory(state, "test context many")
        self.assertLessEqual(len(result), 3)


class TestReinforceMemory(unittest.TestCase):
    """Tests for reinforce_memory function."""

    def test_reinforces_matching_trigger(self):
        """Should increment reinforcement for matching trigger."""
        state = {
            "memory": [
                {"trigger": "test", "lesson": "Test lesson", "reinforced": 2}
            ]
        }
        result = memory_utils.reinforce_memory(state, "test")

        self.assertTrue(result)
        self.assertEqual(state["memory"][0]["reinforced"], 3)

    def test_updates_last_used(self):
        """Should update last_used date."""
        state = {
            "memory": [
                {"trigger": "test", "lesson": "Test lesson", "reinforced": 1, "last_used": "2020-01-01"}
            ]
        }
        memory_utils.reinforce_memory(state, "test")

        today = datetime.now().strftime('%Y-%m-%d')
        self.assertEqual(state["memory"][0]["last_used"], today)

    def test_case_insensitive_match(self):
        """Should match triggers case-insensitively."""
        state = {
            "memory": [
                {"trigger": "Test Trigger", "lesson": "L", "reinforced": 1}
            ]
        }
        result = memory_utils.reinforce_memory(state, "test trigger")
        self.assertTrue(result)

    def test_returns_false_when_no_match(self):
        """Should return False when trigger not found."""
        state = {
            "memory": [
                {"trigger": "other", "lesson": "L", "reinforced": 1}
            ]
        }
        result = memory_utils.reinforce_memory(state, "test")
        self.assertFalse(result)

    def test_handles_empty_memory(self):
        """Should handle empty memory list."""
        state = {"memory": []}
        result = memory_utils.reinforce_memory(state, "test")
        self.assertFalse(result)

    def test_handles_missing_memory_key(self):
        """Should handle missing memory key."""
        state = {}
        result = memory_utils.reinforce_memory(state, "test")
        self.assertFalse(result)

    def test_initializes_reinforced_if_missing(self):
        """Should initialize reinforced count if missing."""
        state = {
            "memory": [
                {"trigger": "test", "lesson": "L"}  # No reinforced key
            ]
        }
        memory_utils.reinforce_memory(state, "test")
        self.assertEqual(state["memory"][0]["reinforced"], 1)


class TestAddMemoryItem(unittest.TestCase):
    """Tests for add_memory_item function."""

    def test_creates_memory_list_if_missing(self):
        """Should create memory list if not present."""
        state = {}
        memory_utils.add_memory_item(state, "trigger", "lesson", dedup=False)
        self.assertIn("memory", state)
        self.assertEqual(len(state["memory"]), 1)

    def test_adds_new_item(self):
        """Should add new item with all fields."""
        state = {"memory": []}
        result = memory_utils.add_memory_item(
            state,
            trigger="test trigger",
            lesson="test lesson",
            dedup=False
        )

        self.assertEqual(result["trigger"], "test trigger")
        self.assertEqual(result["lesson"], "test lesson")
        self.assertEqual(result["reinforced"], 1)
        self.assertIn("last_used", result)

    def test_applies_to_defaults_to_empty_list(self):
        """applies_to should default to empty list."""
        state = {"memory": []}
        result = memory_utils.add_memory_item(state, "t", "l", dedup=False)
        self.assertEqual(result["applies_to"], [])

    def test_applies_to_custom_value(self):
        """applies_to should accept custom value."""
        state = {"memory": []}
        result = memory_utils.add_memory_item(
            state, "t", "l",
            applies_to=["context1", "context2"],
            dedup=False
        )
        self.assertEqual(result["applies_to"], ["context1", "context2"])

    def test_source_from_session_id(self):
        """source should default to session id."""
        state = {
            "memory": [],
            "session": {"id": "test-session-123"}
        }
        result = memory_utils.add_memory_item(state, "t", "l", dedup=False)
        self.assertEqual(result["source"], "test-session-123")

    def test_source_custom_value(self):
        """source should accept custom value."""
        state = {"memory": []}
        result = memory_utils.add_memory_item(
            state, "t", "l",
            source="custom-source",
            dedup=False
        )
        self.assertEqual(result["source"], "custom-source")

    @patch('lesson_utils.find_similar_lesson')
    def test_dedup_finds_similar(self, mock_find):
        """Should deduplicate when similar lesson found."""
        mock_find.return_value = (0, {
            "is_similar": True,
            "keyword_similarity": 0.6
        })
        state = {
            "memory": [
                {"trigger": "existing", "lesson": "Existing lesson", "reinforced": 2}
            ]
        }

        result = memory_utils.add_memory_item(state, "new", "New similar lesson")

        self.assertTrue(result.get("deduplicated"))
        self.assertEqual(state["memory"][0]["reinforced"], 3)

    @patch('lesson_utils.find_similar_lesson')
    def test_dedup_converts_string_format(self, mock_find):
        """Should convert old string format during dedup."""
        mock_find.return_value = (0, {"is_similar": True, "keyword_similarity": 0.5})
        state = {
            "memory": ["Old string lesson"]  # Old format
        }

        result = memory_utils.add_memory_item(state, "trigger", "Similar new lesson")

        self.assertTrue(result.get("deduplicated"))
        self.assertIsInstance(state["memory"][0], dict)

    def test_no_dedup_when_disabled(self):
        """Should not deduplicate when dedup=False."""
        state = {
            "memory": [
                {"trigger": "test", "lesson": "Existing", "reinforced": 1}
            ]
        }

        result = memory_utils.add_memory_item(
            state, "test", "New lesson",
            dedup=False
        )

        self.assertNotIn("deduplicated", result)
        self.assertEqual(len(state["memory"]), 2)


class TestRetrieveFromArchive(unittest.TestCase):
    """Tests for retrieve_from_archive function."""

    @patch.object(memory_utils, 'search_archive')
    def test_calls_search_archive(self, mock_search):
        """Should call search_archive with correct parameters."""
        mock_search.return_value = []

        memory_utils.retrieve_from_archive("test keyword")

        mock_search.assert_called_once_with(
            entry_type="resolved_mismatch",
            keyword="test keyword",
            limit=5
        )

    @patch.object(memory_utils, 'search_archive')
    def test_custom_entry_type(self, mock_search):
        """Should accept custom entry_type."""
        mock_search.return_value = []

        memory_utils.retrieve_from_archive("test", entry_type="completed_step")

        mock_search.assert_called_once_with(
            entry_type="completed_step",
            keyword="test",
            limit=5
        )

    @patch.object(memory_utils, 'search_archive')
    def test_custom_limit(self, mock_search):
        """Should accept custom limit."""
        mock_search.return_value = []

        memory_utils.retrieve_from_archive("test", limit=10)

        mock_search.assert_called_once_with(
            entry_type="resolved_mismatch",
            keyword="test",
            limit=10
        )


class TestResurrectArchivedLesson(unittest.TestCase):
    """Tests for resurrect_archived_lesson function."""

    def test_returns_none_when_no_lesson_data(self):
        """Should return None when archived item has no lesson_extracted."""
        result = memory_utils.resurrect_archived_lesson({}, {})
        self.assertIsNone(result)

    @patch.object(memory_utils, 'add_memory_item')
    def test_calls_add_memory_item(self, mock_add):
        """Should call add_memory_item with correct data."""
        mock_add.return_value = {"trigger": "test", "lesson": "lesson"}

        archived = {
            "lesson_extracted": {
                "trigger": "archived trigger",
                "lesson": "archived lesson"
            },
            "timestamp": "2024-01-01"
        }

        memory_utils.resurrect_archived_lesson(archived, {})

        mock_add.assert_called_once()
        call_kwargs = mock_add.call_args[1]
        self.assertEqual(call_kwargs["trigger"], "archived trigger")
        self.assertEqual(call_kwargs["lesson"], "archived lesson")
        self.assertIn("resurrected", call_kwargs["source"])

    @patch.object(memory_utils, 'add_memory_item')
    def test_handles_missing_trigger(self, mock_add):
        """Should use 'unknown' for missing trigger."""
        mock_add.return_value = {}

        archived = {
            "lesson_extracted": {"lesson": "some lesson"}
        }

        memory_utils.resurrect_archived_lesson(archived, {})

        call_kwargs = mock_add.call_args[1]
        self.assertEqual(call_kwargs["trigger"], "unknown")


class TestGetMemorySummary(unittest.TestCase):
    """Tests for get_memory_summary function."""

    def test_empty_memory(self):
        """Should handle empty memory."""
        state = {"memory": []}
        result = memory_utils.get_memory_summary(state)

        self.assertEqual(result["count"], 0)
        self.assertEqual(result["high_value"], 0)
        self.assertEqual(result["at_risk"], 0)

    def test_counts_high_value(self):
        """Should count high value items (reinforced >= 2)."""
        state = {
            "memory": [
                {"trigger": "t1", "reinforced": 5},  # High value
                {"trigger": "t2", "reinforced": 2},  # High value
                {"trigger": "t3", "reinforced": 1},  # Not high value
            ]
        }
        result = memory_utils.get_memory_summary(state)

        self.assertEqual(result["high_value"], 2)

    def test_counts_at_risk(self):
        """Should count at risk items (reinforced == 0)."""
        state = {
            "memory": [
                {"trigger": "t1", "reinforced": 0},  # At risk
                {"trigger": "t2", "reinforced": 1},  # Not at risk
            ]
        }
        result = memory_utils.get_memory_summary(state)

        self.assertEqual(result["at_risk"], 1)

    def test_includes_items_list(self):
        """Should include items list with trigger and reinforced."""
        state = {
            "memory": [
                {"trigger": "test1", "lesson": "L1", "reinforced": 3},
                {"trigger": "test2", "lesson": "L2", "reinforced": 1},
            ]
        }
        result = memory_utils.get_memory_summary(state)

        self.assertEqual(len(result["items"]), 2)
        self.assertEqual(result["items"][0]["trigger"], "test1")
        self.assertEqual(result["items"][0]["reinforced"], 3)

    def test_skips_non_dict_items_in_list(self):
        """Should skip non-dict items in summary list."""
        state = {
            "memory": [
                "old string format",
                {"trigger": "valid", "reinforced": 1}
            ]
        }
        result = memory_utils.get_memory_summary(state)

        # Count includes all, but items list only includes dicts
        self.assertEqual(result["count"], 2)
        self.assertEqual(len(result["items"]), 1)


if __name__ == "__main__":
    unittest.main()
