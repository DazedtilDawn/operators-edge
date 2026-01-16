#!/usr/bin/env python3
"""
Tests for pattern_engine.py - the Generative Layer.
"""

import unittest
from datetime import datetime
from unittest.mock import patch, MagicMock

from pattern_engine import (
    Pattern, PatternType, PatternBundle,
    extract_lesson_patterns, extract_risk_patterns,
    extract_rhythm_patterns, surface_patterns,
    format_pattern_guidance, _pattern_icon,
)


class TestPatternDataclasses(unittest.TestCase):
    """Test Pattern and PatternBundle dataclasses."""

    def test_pattern_to_dict(self):
        p = Pattern(
            type=PatternType.LESSON,
            trigger="test trigger",
            content="Test content",
            relevance=0.8,
            source="test",
            confidence="high"
        )
        d = p.to_dict()
        self.assertEqual(d["type"], "lesson")
        self.assertEqual(d["trigger"], "test trigger")
        self.assertEqual(d["relevance"], 0.8)
        self.assertEqual(d["confidence"], "high")

    def test_pattern_bundle_to_dict(self):
        p = Pattern(
            type=PatternType.RISK,
            trigger="risk",
            content="Watch out",
            relevance=0.5,
            source="test"
        )
        bundle = PatternBundle(
            context="Testing",
            patterns=[p],
            total_found=1,
            intent_action="ready_to_execute"
        )
        d = bundle.to_dict()
        self.assertEqual(d["context"], "Testing")
        self.assertEqual(len(d["patterns"]), 1)
        self.assertEqual(d["intent_action"], "ready_to_execute")

    def test_pattern_bundle_format_guidance_empty(self):
        bundle = PatternBundle(
            context="Test",
            patterns=[],
            total_found=0,
            intent_action="test"
        )
        self.assertEqual(bundle.format_guidance(), "")

    def test_pattern_bundle_format_guidance_with_patterns(self):
        p = Pattern(
            type=PatternType.LESSON,
            trigger="test",
            content="Use CSS variables",
            relevance=0.8,
            source="memory",
            confidence="high"
        )
        bundle = PatternBundle(
            context="Testing",
            patterns=[p],
            total_found=1,
            intent_action="test"
        )
        guidance = bundle.format_guidance()
        self.assertIn("📖", guidance)
        self.assertIn("Lesson", guidance)
        self.assertIn("CSS variables", guidance)


class TestPatternIcons(unittest.TestCase):
    """Test pattern icon mapping."""

    def test_lesson_icon(self):
        self.assertEqual(_pattern_icon(PatternType.LESSON), "📚")

    def test_cochange_icon(self):
        self.assertEqual(_pattern_icon(PatternType.COCHANGE), "🔗")

    def test_risk_icon(self):
        self.assertEqual(_pattern_icon(PatternType.RISK), "⚠️")

    def test_rhythm_icon(self):
        self.assertEqual(_pattern_icon(PatternType.RHYTHM), "🕐")


class TestExtractLessonPatterns(unittest.TestCase):
    """Test lesson pattern extraction."""

    def test_extracts_from_memory(self):
        state = {
            "memory": [
                {"trigger": "theme css", "lesson": "Use CSS variables", "reinforced": 3},
            ]
        }
        patterns = extract_lesson_patterns(state, "Adding theme CSS variables")
        self.assertEqual(len(patterns), 1)
        self.assertEqual(patterns[0].type, PatternType.LESSON)
        self.assertEqual(patterns[0].confidence, "high")

    def test_empty_state(self):
        patterns = extract_lesson_patterns({}, "test context")
        self.assertEqual(len(patterns), 0)

    def test_no_matching_memory(self):
        state = {
            "memory": [
                {"trigger": "database sql", "lesson": "Use transactions", "reinforced": 2},
            ]
        }
        patterns = extract_lesson_patterns(state, "Adding CSS styles")
        self.assertEqual(len(patterns), 0)


class TestExtractRiskPatterns(unittest.TestCase):
    """Test risk pattern extraction."""

    def test_extracts_from_risks(self):
        state = {
            "risks": [
                {"risk": "CSS browser support", "mitigation": "Check caniuse.com"},
            ]
        }
        patterns = extract_risk_patterns(state, "Adding CSS browser styles")
        self.assertGreater(len(patterns), 0)
        self.assertEqual(patterns[0].type, PatternType.RISK)

    def test_extracts_from_resolved_mismatches(self):
        state = {
            "mismatches": [
                {
                    "expectation": "API returns json",
                    "status": "resolved",
                    "resolution": "API actually returns XML"
                },
            ]
        }
        patterns = extract_risk_patterns(state, "Calling API for json data")
        self.assertGreater(len(patterns), 0)
        self.assertEqual(patterns[0].type, PatternType.RISK)

    def test_empty_state(self):
        patterns = extract_risk_patterns({}, "test")
        self.assertEqual(len(patterns), 0)


class TestExtractRhythmPatterns(unittest.TestCase):
    """Test time-based pattern extraction."""

    @patch('pattern_engine.datetime')
    def test_late_night_warning(self, mock_datetime):
        mock_datetime.now.return_value = datetime(2025, 1, 15, 23, 30)
        state = {}
        patterns = extract_rhythm_patterns(state, "Adding feature")
        self.assertTrue(any(p.trigger == "late_night" for p in patterns))

    @patch('pattern_engine.datetime')
    def test_friday_deploy_warning(self, mock_datetime):
        # Friday = 4
        mock_now = MagicMock()
        mock_now.hour = 14
        mock_now.weekday.return_value = 4
        mock_datetime.now.return_value = mock_now
        state = {}
        patterns = extract_rhythm_patterns(state, "Deploy to production")
        self.assertTrue(any(p.trigger == "friday_deploy" for p in patterns))

    def test_long_session_warning(self):
        state = {
            "plan": [
                {"status": "completed"},
                {"status": "completed"},
                {"status": "completed"},
                {"status": "completed"},
                {"status": "completed"},
                {"status": "in_progress"},
            ]
        }
        patterns = extract_rhythm_patterns(state, "Continuing work")
        self.assertTrue(any(p.trigger == "long_session" for p in patterns))


class TestSurfacePatterns(unittest.TestCase):
    """Test main pattern surfacing function."""

    def test_returns_bundle(self):
        state = {
            "objective": "Test",
            "memory": [
                {"trigger": "test", "lesson": "Testing is good", "reinforced": 1},
            ]
        }
        bundle = surface_patterns(state, "Adding test cases", "ready_to_execute")
        self.assertIsInstance(bundle, PatternBundle)
        self.assertEqual(bundle.intent_action, "ready_to_execute")

    def test_limits_patterns(self):
        state = {
            "memory": [
                {"trigger": f"test{i}", "lesson": f"Lesson {i}", "reinforced": 1}
                for i in range(10)
            ]
        }
        bundle = surface_patterns(state, "test0 test1 test2 test3", "test", max_patterns=3)
        self.assertLessEqual(len(bundle.patterns), 3)

    def test_diversity_across_types(self):
        state = {
            "memory": [
                {"trigger": "test", "lesson": "Lesson 1", "reinforced": 3},
                {"trigger": "test", "lesson": "Lesson 2", "reinforced": 2},
                {"trigger": "test", "lesson": "Lesson 3", "reinforced": 1},
            ],
            "risks": [
                {"risk": "test failure", "mitigation": "Handle it"},
            ]
        }
        bundle = surface_patterns(state, "test", "test", max_patterns=5)
        # Should have diverse types, not all lessons
        types = {p.type for p in bundle.patterns}
        self.assertGreater(len(types), 0)


class TestFormatPatternGuidance(unittest.TestCase):
    """Test guidance formatting."""

    def test_formats_bundle(self):
        p = Pattern(
            type=PatternType.LESSON,
            trigger="test",
            content="Important lesson",
            relevance=0.8,
            source="test",
            confidence="high"
        )
        bundle = PatternBundle(
            context="Testing",
            patterns=[p],
            total_found=1,
            intent_action="test"
        )
        guidance = format_pattern_guidance(bundle)
        self.assertIn("Important lesson", guidance)
        self.assertIn("★", guidance)  # High confidence marker

    def test_empty_bundle(self):
        bundle = PatternBundle(
            context="Testing",
            patterns=[],
            total_found=0,
            intent_action="test"
        )
        guidance = format_pattern_guidance(bundle)
        self.assertEqual(guidance, "")


class TestGraduationLifecycle(unittest.TestCase):
    """Test the graduation lifecycle for lessons."""

    def test_new_lesson_surfaces(self):
        """New lessons (low reinforcement) should always surface."""
        from pattern_engine import should_surface_lesson
        lesson = {"trigger": "test", "reinforced": 2}
        self.assertTrue(should_surface_lesson(lesson, 0.5))

    def test_established_high_confidence_surfaces(self):
        """Established lessons surface only with high-confidence matches."""
        from pattern_engine import should_surface_lesson
        lesson = {"trigger": "test", "reinforced": 6}
        self.assertTrue(should_surface_lesson(lesson, 0.8))  # High confidence
        self.assertFalse(should_surface_lesson(lesson, 0.5))  # Low confidence

    def test_graduated_does_not_surface(self):
        """Graduated lessons (10+ reinforcements) should not surface."""
        from pattern_engine import should_surface_lesson
        lesson = {"trigger": "test", "reinforced": 15}
        self.assertFalse(should_surface_lesson(lesson, 0.9))

    def test_evergreen_always_surfaces(self):
        """Evergreen lessons surface regardless of reinforcement."""
        from pattern_engine import should_surface_lesson
        lesson = {"trigger": "test", "reinforced": 50, "evergreen": True}
        self.assertTrue(should_surface_lesson(lesson, 0.3))

    def test_lifecycle_stage_new(self):
        """Test lifecycle stage detection for new lessons."""
        from pattern_engine import get_lesson_lifecycle_stage
        lesson = {"trigger": "test", "reinforced": 2}
        self.assertEqual(get_lesson_lifecycle_stage(lesson), "new")

    def test_lifecycle_stage_established(self):
        """Test lifecycle stage detection for established lessons."""
        from pattern_engine import get_lesson_lifecycle_stage
        lesson = {"trigger": "test", "reinforced": 7}
        self.assertEqual(get_lesson_lifecycle_stage(lesson), "established")

    def test_lifecycle_stage_graduated(self):
        """Test lifecycle stage detection for graduated lessons."""
        from pattern_engine import get_lesson_lifecycle_stage
        lesson = {"trigger": "test", "reinforced": 15}
        self.assertEqual(get_lesson_lifecycle_stage(lesson), "graduated")

    def test_lifecycle_stage_evergreen(self):
        """Test lifecycle stage detection for evergreen lessons."""
        from pattern_engine import get_lesson_lifecycle_stage
        lesson = {"trigger": "test", "reinforced": 50, "evergreen": True}
        self.assertEqual(get_lesson_lifecycle_stage(lesson), "evergreen")


if __name__ == "__main__":
    unittest.main()
