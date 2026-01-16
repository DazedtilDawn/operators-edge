#!/usr/bin/env python3
"""
Tests for learning_loop.py - Phase 3 feedback cycle.
"""

import unittest
from datetime import datetime, timedelta
from unittest.mock import patch, MagicMock

from learning_loop import (
    PatternOutcome,
    track_surfaced_patterns, get_tracked_patterns, clear_tracked_patterns,
    make_step_key,
    evaluate_step_outcome, infer_pattern_helpfulness,
    reinforce_lesson_pattern, apply_pattern_reinforcement,
    decay_stale_patterns,
    process_step_completion, run_periodic_decay,
    get_pattern_stats, format_pattern_stats, _calculate_pattern_health,
)
from pattern_engine import Pattern, PatternType, PatternBundle


class TestPatternOutcome(unittest.TestCase):
    """Test PatternOutcome dataclass."""

    def test_to_dict(self):
        outcome = PatternOutcome(
            pattern_type="lesson",
            pattern_trigger="test trigger",
            pattern_content="Test content",
            surfaced_at="2025-01-15T10:00:00",
            intent_action="ready_to_execute",
            step_description="Test step",
            outcome="success",
            reinforcement_applied=1
        )
        d = outcome.to_dict()
        self.assertEqual(d["pattern_type"], "lesson")
        self.assertEqual(d["outcome"], "success")
        self.assertEqual(d["reinforcement_applied"], 1)


class TestPatternTracking(unittest.TestCase):
    """Test pattern tracking for learning loop."""

    def setUp(self):
        # Clear any existing tracked patterns
        clear_tracked_patterns("test:step0")

    def test_track_and_get(self):
        p = Pattern(
            type=PatternType.LESSON,
            trigger="test",
            content="Test lesson",
            relevance=0.8,
            source="test"
        )
        bundle = PatternBundle(
            context="Test",
            patterns=[p],
            total_found=1,
            intent_action="test"
        )

        track_surfaced_patterns(bundle, "test:step0")
        retrieved = get_tracked_patterns("test:step0")

        self.assertIsNotNone(retrieved)
        self.assertEqual(len(retrieved.patterns), 1)

    def test_clear_tracked(self):
        p = Pattern(
            type=PatternType.LESSON,
            trigger="test",
            content="Test",
            relevance=0.5,
            source="test"
        )
        bundle = PatternBundle(
            context="Test",
            patterns=[p],
            total_found=1,
            intent_action="test"
        )

        track_surfaced_patterns(bundle, "test:step1")
        clear_tracked_patterns("test:step1")
        retrieved = get_tracked_patterns("test:step1")

        self.assertIsNone(retrieved)

    def test_make_step_key(self):
        key = make_step_key("Add dark mode", 2)
        self.assertEqual(key, "Add dark mode:step2")

    def test_make_step_key_truncates_long_objective(self):
        long_obj = "A" * 100
        key = make_step_key(long_obj, 0)
        self.assertLessEqual(len(key.split(":")[0]), 50)


class TestOutcomeEvaluation(unittest.TestCase):
    """Test outcome evaluation logic."""

    def test_success_outcome(self):
        outcome = evaluate_step_outcome({}, 0, "in_progress", "completed")
        self.assertEqual(outcome, "success")

    def test_success_from_pending(self):
        outcome = evaluate_step_outcome({}, 0, "pending", "completed")
        self.assertEqual(outcome, "success")

    def test_blocked_outcome(self):
        outcome = evaluate_step_outcome({}, 0, "in_progress", "blocked")
        self.assertEqual(outcome, "blocked")

    def test_failure_outcome(self):
        outcome = evaluate_step_outcome({}, 0, "in_progress", "failed")
        self.assertEqual(outcome, "failure")

    def test_skipped_outcome(self):
        outcome = evaluate_step_outcome({}, 0, "pending", "skipped")
        self.assertEqual(outcome, "skipped")

    def test_in_progress_outcome(self):
        outcome = evaluate_step_outcome({}, 0, "pending", "in_progress")
        self.assertEqual(outcome, "in_progress")


class TestHelpfulnessInference(unittest.TestCase):
    """Test helpfulness inference from outcomes."""

    def test_success_is_helpful(self):
        self.assertEqual(infer_pattern_helpfulness("success"), 1)

    def test_failure_is_neutral(self):
        self.assertEqual(infer_pattern_helpfulness("failure"), 0)

    def test_blocked_is_neutral(self):
        self.assertEqual(infer_pattern_helpfulness("blocked"), 0)

    def test_skipped_is_negative(self):
        self.assertEqual(infer_pattern_helpfulness("skipped"), -1)

    def test_in_progress_is_neutral(self):
        self.assertEqual(infer_pattern_helpfulness("in_progress"), 0)


class TestReinforceLessonPattern(unittest.TestCase):
    """Test lesson pattern reinforcement."""

    def test_reinforce_existing(self):
        state = {
            "memory": [
                {"trigger": "test", "lesson": "Test lesson", "reinforced": 2}
            ]
        }
        result = reinforce_lesson_pattern(state, "test", 1)
        self.assertTrue(result)
        self.assertEqual(state["memory"][0]["reinforced"], 3)

    def test_reinforce_nonexistent(self):
        state = {"memory": []}
        result = reinforce_lesson_pattern(state, "nonexistent", 1)
        self.assertFalse(result)

    def test_reinforce_updates_last_used(self):
        state = {
            "memory": [
                {"trigger": "test", "lesson": "Test", "reinforced": 1, "last_used": "2020-01-01"}
            ]
        }
        reinforce_lesson_pattern(state, "test", 1)
        self.assertNotEqual(state["memory"][0]["last_used"], "2020-01-01")

    def test_reinforce_never_goes_negative(self):
        state = {
            "memory": [
                {"trigger": "test", "lesson": "Test", "reinforced": 0}
            ]
        }
        reinforce_lesson_pattern(state, "test", -5)
        self.assertEqual(state["memory"][0]["reinforced"], 0)


class TestApplyPatternReinforcement(unittest.TestCase):
    """Test applying reinforcement to different pattern types."""

    def test_lesson_pattern(self):
        state = {
            "memory": [
                {"trigger": "test", "lesson": "Test", "reinforced": 1}
            ]
        }
        p = Pattern(
            type=PatternType.LESSON,
            trigger="test",
            content="Test",
            relevance=0.5,
            source="test"
        )
        result = apply_pattern_reinforcement(state, p, 1)
        self.assertTrue(result)
        self.assertEqual(state["memory"][0]["reinforced"], 2)

    def test_zero_delta_no_change(self):
        state = {
            "memory": [
                {"trigger": "test", "lesson": "Test", "reinforced": 1}
            ]
        }
        p = Pattern(
            type=PatternType.LESSON,
            trigger="test",
            content="Test",
            relevance=0.5,
            source="test"
        )
        result = apply_pattern_reinforcement(state, p, 0)
        self.assertFalse(result)


class TestDecayStalePatterns(unittest.TestCase):
    """Test decay of stale patterns."""

    def test_decay_old_weak_pattern(self):
        old_date = (datetime.now() - timedelta(days=20)).strftime("%Y-%m-%d")
        state = {
            "memory": [
                {"trigger": "stale", "lesson": "Old", "reinforced": 1, "last_used": old_date}
            ]
        }
        decayed = decay_stale_patterns(state, days_threshold=14)
        self.assertEqual(len(decayed), 1)
        self.assertEqual(state["memory"][0]["reinforced"], 0)

    def test_no_decay_recent_pattern(self):
        recent_date = datetime.now().strftime("%Y-%m-%d")
        state = {
            "memory": [
                {"trigger": "fresh", "lesson": "New", "reinforced": 1, "last_used": recent_date}
            ]
        }
        decayed = decay_stale_patterns(state, days_threshold=14)
        self.assertEqual(len(decayed), 0)
        self.assertEqual(state["memory"][0]["reinforced"], 1)

    def test_no_decay_strong_pattern(self):
        old_date = (datetime.now() - timedelta(days=20)).strftime("%Y-%m-%d")
        state = {
            "memory": [
                {"trigger": "strong", "lesson": "Important", "reinforced": 5, "last_used": old_date}
            ]
        }
        decayed = decay_stale_patterns(state, days_threshold=14)
        self.assertEqual(len(decayed), 0)


class TestProcessStepCompletion(unittest.TestCase):
    """Test the main learning loop function."""

    def test_returns_result(self):
        state = {
            "objective": "Test",
            "plan": [{"description": "Step 1", "status": "completed"}],
            "memory": []
        }
        result = process_step_completion(
            state, "Test", 0, "in_progress", "completed"
        )
        self.assertIn("outcome", result)
        self.assertEqual(result["outcome"], "success")

    def test_no_patterns_tracked(self):
        state = {
            "objective": "Test",
            "plan": [{"description": "Step 1", "status": "completed"}],
            "memory": []
        }
        result = process_step_completion(
            state, "Test", 0, "in_progress", "completed"
        )
        self.assertEqual(result["patterns_evaluated"], 0)


class TestPatternStats(unittest.TestCase):
    """Test pattern statistics."""

    def test_empty_stats(self):
        state = {"memory": [], "risks": []}
        stats = get_pattern_stats(state)
        self.assertEqual(stats["lessons"]["total"], 0)
        self.assertEqual(stats["health"], "empty")

    def test_healthy_stats(self):
        state = {
            "memory": [
                {"trigger": "a", "reinforced": 5},
                {"trigger": "b", "reinforced": 3},
                {"trigger": "c", "reinforced": 1},
            ],
            "risks": [{"risk": "test", "times_helped": 1}]
        }
        stats = get_pattern_stats(state)
        self.assertEqual(stats["lessons"]["total"], 3)
        self.assertEqual(stats["lessons"]["high_value"], 2)
        self.assertEqual(stats["risks"]["helpful"], 1)

    def test_health_calculation_healthy(self):
        stats = {"total": 10, "high_value": 4, "medium_value": 4, "at_risk": 2}
        health = _calculate_pattern_health(stats)
        self.assertEqual(health, "healthy")

    def test_health_calculation_stale(self):
        stats = {"total": 10, "high_value": 1, "medium_value": 2, "at_risk": 7}
        health = _calculate_pattern_health(stats)
        self.assertEqual(health, "stale")


class TestFormatPatternStats(unittest.TestCase):
    """Test pattern stats formatting."""

    def test_formats_stats(self):
        stats = {
            "lessons": {"total": 5, "high_value": 2, "medium_value": 2, "at_risk": 1},
            "risks": {"total": 3, "helpful": 1},
            "health": "healthy"
        }
        output = format_pattern_stats(stats)
        self.assertIn("Pattern Health", output)
        self.assertIn("🟢", output)
        self.assertIn("5 total", output)


if __name__ == "__main__":
    unittest.main()
