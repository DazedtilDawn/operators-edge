#!/usr/bin/env python3
"""
Tests for research_utils.py - research detection and prompt generation.

Tests the core functions for:
- Scanning for research needs in TODOs and alternatives
- Research state management
- Prompt generation for external tools
"""
import os
import sys
import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from unittest.mock import patch, MagicMock

# Add hooks directory to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


class TestGenerateResearchId(unittest.TestCase):
    """Tests for generate_research_id() function."""

    def test_generates_unique_id(self):
        """generate_research_id() should create unique IDs."""
        from research_utils import generate_research_id

        id1 = generate_research_id()
        id2 = generate_research_id()

        self.assertTrue(id1.startswith("R"))
        self.assertIsInstance(id1, str)

    def test_id_format(self):
        """generate_research_id() should have expected format."""
        from research_utils import generate_research_id

        research_id = generate_research_id()

        # Should start with R followed by datetime
        self.assertTrue(research_id.startswith("R"))
        self.assertEqual(len(research_id), 15)  # R + 14 digit timestamp


class TestGetResearchItems(unittest.TestCase):
    """Tests for get_research_items() function."""

    def test_returns_research_list(self):
        """get_research_items() should return research array."""
        from research_utils import get_research_items

        state = {"research": [{"topic": "test"}]}
        result = get_research_items(state)

        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["topic"], "test")

    def test_returns_empty_for_no_state(self):
        """get_research_items() should return empty list for None state."""
        from research_utils import get_research_items

        result = get_research_items(None)
        self.assertEqual(result, [])

    def test_returns_empty_for_missing_key(self):
        """get_research_items() should return empty list if key missing."""
        from research_utils import get_research_items

        result = get_research_items({"plan": []})
        self.assertEqual(result, [])


class TestGetPendingResearch(unittest.TestCase):
    """Tests for get_pending_research() function."""

    def test_filters_pending(self):
        """get_pending_research() should return pending/in_progress items."""
        from research_utils import get_pending_research

        state = {
            "research": [
                {"topic": "a", "status": "pending"},
                {"topic": "b", "status": "completed"},
                {"topic": "c", "status": "in_progress"}
            ]
        }

        result = get_pending_research(state)

        self.assertEqual(len(result), 2)
        topics = {r["topic"] for r in result}
        self.assertEqual(topics, {"a", "c"})


class TestGetBlockingResearch(unittest.TestCase):
    """Tests for get_blocking_research() function."""

    def test_filters_critical_pending(self):
        """get_blocking_research() should return critical pending items."""
        from research_utils import get_blocking_research

        state = {
            "research": [
                {"topic": "a", "priority": "critical", "status": "pending"},
                {"topic": "b", "priority": "optional", "status": "pending"},
                {"topic": "c", "priority": "critical", "status": "completed"}
            ]
        }

        result = get_blocking_research(state)

        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["topic"], "a")


class TestScanForResearchNeeds(unittest.TestCase):
    """Tests for scan_for_research_needs() function."""

    @patch('research_utils.RESEARCH_INDICATORS', {
        'technologies': ['kubernetes', 'docker'],
        'ambiguity_signals': ['somehow', 'maybe'],
        'research_verbs': ['research', 'investigate']
    })
    def test_detects_technology_in_objective(self):
        """scan_for_research_needs() should detect tech keywords in objective."""
        from research_utils import scan_for_research_needs

        state = {"objective": "Deploy to Kubernetes cluster"}

        needs = scan_for_research_needs(state)

        self.assertTrue(any("kubernetes" in n["topic"].lower() for n in needs))

    @patch('research_utils.RESEARCH_INDICATORS', {
        'technologies': [],
        'ambiguity_signals': ['somehow', 'maybe'],
        'research_verbs': []
    })
    def test_detects_ambiguity(self):
        """scan_for_research_needs() should detect ambiguity signals."""
        from research_utils import scan_for_research_needs

        state = {"objective": "Somehow improve performance"}

        needs = scan_for_research_needs(state)

        self.assertTrue(any(n["priority"] == "critical" for n in needs))

    def test_handles_empty_state(self):
        """scan_for_research_needs() should handle empty state."""
        from research_utils import scan_for_research_needs

        result = scan_for_research_needs(None)
        self.assertEqual(result, [])

    @patch('research_utils.RESEARCH_INDICATORS', {
        'technologies': [],
        'ambiguity_signals': [],
        'research_verbs': []
    })
    def test_includes_open_questions(self):
        """scan_for_research_needs() should include open_questions."""
        from research_utils import scan_for_research_needs

        state = {
            "objective": "Test",
            "open_questions": [
                {"question": "What auth method?", "blocking": True}
            ]
        }

        needs = scan_for_research_needs(state)

        self.assertTrue(any("auth method" in n["topic"].lower() for n in needs))


class TestGenerateResearchPrompt(unittest.TestCase):
    """Tests for generate_research_prompt() function."""

    @patch('research_utils.get_memory_items')
    def test_generates_prompt(self, mock_memory):
        """generate_research_prompt() should create formatted prompt."""
        from research_utils import generate_research_prompt

        mock_memory.return_value = []
        state = {
            "objective": "Build API",
            "constraints": ["Must be fast"]
        }
        need = {
            "topic": "Best practices for REST API",
            "reason": "Need API design guidance",
            "priority": "optional"
        }

        prompt = generate_research_prompt(need, state)

        self.assertIn("Research Request", prompt)
        self.assertIn("REST API", prompt)
        self.assertIn("Build API", prompt)

    @patch('research_utils.get_memory_items')
    def test_includes_blocking_step(self, mock_memory):
        """generate_research_prompt() should mention blocking step."""
        from research_utils import generate_research_prompt

        mock_memory.return_value = []
        state = {"objective": "Test"}
        need = {
            "topic": "Test topic",
            "reason": "Test reason",
            "blocking_step": 3
        }

        prompt = generate_research_prompt(need, state)

        self.assertIn("Step 3", prompt)


class TestCreateResearchItem(unittest.TestCase):
    """Tests for create_research_item() function."""

    @patch('research_utils.generate_research_prompt')
    @patch('research_utils.generate_research_id')
    def test_creates_full_item(self, mock_id, mock_prompt):
        """create_research_item() should create complete research item."""
        from research_utils import create_research_item

        mock_id.return_value = "R20250101000000"
        mock_prompt.return_value = "Test prompt"

        state = {"objective": "Test"}
        need = {
            "topic": "Test topic",
            "priority": "critical",
            "blocking_step": 1
        }

        item = create_research_item(need, state)

        self.assertEqual(item["id"], "R20250101000000")
        self.assertEqual(item["topic"], "Test topic")
        self.assertEqual(item["priority"], "critical")
        self.assertEqual(item["status"], "pending")
        self.assertEqual(item["prompt"], "Test prompt")


class TestAddResearchToState(unittest.TestCase):
    """Tests for add_research_to_state() function."""

    def test_adds_to_empty_state(self):
        """add_research_to_state() should create research array if missing."""
        from research_utils import add_research_to_state

        state = {}
        item = {"id": "R1", "topic": "Test"}

        add_research_to_state(state, item)

        self.assertIn("research", state)
        self.assertEqual(len(state["research"]), 1)

    def test_appends_to_existing(self):
        """add_research_to_state() should append to existing array."""
        from research_utils import add_research_to_state

        state = {"research": [{"id": "R1"}]}
        item = {"id": "R2", "topic": "Test"}

        add_research_to_state(state, item)

        self.assertEqual(len(state["research"]), 2)


class TestUpdateResearchStatus(unittest.TestCase):
    """Tests for update_research_status() function."""

    def test_updates_status(self):
        """update_research_status() should update matching item."""
        from research_utils import update_research_status

        state = {
            "research": [
                {"id": "R1", "status": "pending"},
                {"id": "R2", "status": "pending"}
            ]
        }

        result = update_research_status(state, "R1", "in_progress")

        self.assertTrue(result)
        self.assertEqual(state["research"][0]["status"], "in_progress")

    def test_returns_false_for_missing(self):
        """update_research_status() should return False if not found."""
        from research_utils import update_research_status

        state = {"research": [{"id": "R1", "status": "pending"}]}

        result = update_research_status(state, "R999", "completed")

        self.assertFalse(result)


class TestAddResearchResults(unittest.TestCase):
    """Tests for add_research_results() function."""

    def test_adds_results(self):
        """add_research_results() should add results and complete."""
        from research_utils import add_research_results

        state = {
            "research": [{"id": "R1", "status": "pending"}]
        }

        result = add_research_results(state, "R1", "Test results", ["Action 1"])

        self.assertTrue(result)
        self.assertEqual(state["research"][0]["results"], "Test results")
        self.assertEqual(state["research"][0]["action_items"], ["Action 1"])
        self.assertEqual(state["research"][0]["status"], "completed")


class TestGetResearchSummary(unittest.TestCase):
    """Tests for get_research_summary() function."""

    def test_summarizes_research(self):
        """get_research_summary() should return stats."""
        from research_utils import get_research_summary

        state = {
            "research": [
                {"status": "pending", "priority": "optional"},
                {"status": "in_progress", "priority": "critical"},
                {"status": "completed", "priority": "optional"}
            ]
        }

        summary = get_research_summary(state)

        self.assertEqual(summary["total"], 3)
        self.assertEqual(summary["pending"], 1)
        self.assertEqual(summary["in_progress"], 1)
        self.assertEqual(summary["completed"], 1)

    def test_empty_research(self):
        """get_research_summary() should handle empty research."""
        from research_utils import get_research_summary

        summary = get_research_summary({"research": []})

        self.assertEqual(summary["total"], 0)


if __name__ == '__main__':
    unittest.main()
