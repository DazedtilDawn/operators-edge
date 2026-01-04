#!/usr/bin/env python3
"""
Tests for discovery_config.py

Coverage:
- Enum values and definitions
- DiscoveryEvidence dataclass
- DiscoveryFinding dataclass with to_dict/from_dict
- Scoring functions
- Sorting discoveries
- Formatting functions
- State helpers
- ID generation
"""

import unittest
from datetime import datetime

from discovery_config import (
    DiscoverySource,
    DiscoveryConfidence,
    DiscoveryValue,
    DiscoveryEffort,
    DiscoveryEvidence,
    DiscoveryFinding,
    VALUE_SCORES,
    EFFORT_PENALTIES,
    CONFIDENCE_BOOSTS,
    score_discovery,
    sort_discoveries,
    format_discovery_for_display,
    discovery_to_objective,
    get_default_discovery_state,
    generate_discovery_id,
    DISCOVERY_THRESHOLDS,
    ARCHIVE_ENTRY_TYPES,
    MISMATCH_CATEGORIES,
)


class TestEnums(unittest.TestCase):
    """Tests for enum definitions."""

    def test_discovery_source_values(self):
        """DiscoverySource should have expected values."""
        self.assertEqual(DiscoverySource.ARCHIVE_PAIN.value, "archive_pain")
        self.assertEqual(DiscoverySource.LESSON_REINFORCEMENT.value, "lesson_reinforcement")
        self.assertEqual(DiscoverySource.WORKFLOW_FRICTION.value, "workflow_friction")
        self.assertEqual(DiscoverySource.INTEGRATION_GAP.value, "integration_gap")

    def test_discovery_confidence_values(self):
        """DiscoveryConfidence should have expected values."""
        self.assertEqual(DiscoveryConfidence.HIGH.value, "high")
        self.assertEqual(DiscoveryConfidence.MEDIUM.value, "medium")
        self.assertEqual(DiscoveryConfidence.LOW.value, "low")

    def test_discovery_value_values(self):
        """DiscoveryValue should have expected values."""
        self.assertEqual(DiscoveryValue.HIGH.value, "high")
        self.assertEqual(DiscoveryValue.MEDIUM.value, "medium")
        self.assertEqual(DiscoveryValue.LOW.value, "low")

    def test_discovery_effort_values(self):
        """DiscoveryEffort should have expected values."""
        self.assertEqual(DiscoveryEffort.LOW.value, "low")
        self.assertEqual(DiscoveryEffort.MEDIUM.value, "medium")
        self.assertEqual(DiscoveryEffort.HIGH.value, "high")


class TestDiscoveryEvidence(unittest.TestCase):
    """Tests for DiscoveryEvidence dataclass."""

    def test_create_evidence_with_defaults(self):
        """Should create evidence with default values."""
        evidence = DiscoveryEvidence(
            source=DiscoverySource.ARCHIVE_PAIN,
            pattern="test pattern",
            frequency=5,
        )
        self.assertEqual(evidence.source, DiscoverySource.ARCHIVE_PAIN)
        self.assertEqual(evidence.pattern, "test pattern")
        self.assertEqual(evidence.frequency, 5)
        self.assertEqual(evidence.data_points, [])  # default
        self.assertEqual(evidence.time_range_days, 30)  # default

    def test_create_evidence_with_data_points(self):
        """Should create evidence with custom data points."""
        evidence = DiscoveryEvidence(
            source=DiscoverySource.LESSON_REINFORCEMENT,
            pattern="repeated lesson",
            frequency=10,
            data_points=["point1", "point2"],
            time_range_days=60,
        )
        self.assertEqual(len(evidence.data_points), 2)
        self.assertEqual(evidence.time_range_days, 60)


class TestDiscoveryFinding(unittest.TestCase):
    """Tests for DiscoveryFinding dataclass."""

    def setUp(self):
        """Create a sample finding for tests."""
        self.evidence = DiscoveryEvidence(
            source=DiscoverySource.ARCHIVE_PAIN,
            pattern="git failures",
            frequency=5,
            data_points=["fail1", "fail2"],
        )
        self.finding = DiscoveryFinding(
            id="test-123",
            title="Add git retry logic",
            source=DiscoverySource.ARCHIVE_PAIN,
            confidence=DiscoveryConfidence.HIGH,
            value=DiscoveryValue.HIGH,
            effort=DiscoveryEffort.LOW,
            evidence=self.evidence,
            sketch="Add retry wrapper around git commands",
            affected_files=["git_utils.py"],
        )

    def test_create_finding(self):
        """Should create finding with all fields."""
        self.assertEqual(self.finding.id, "test-123")
        self.assertEqual(self.finding.title, "Add git retry logic")
        self.assertEqual(self.finding.source, DiscoverySource.ARCHIVE_PAIN)
        self.assertEqual(self.finding.confidence, DiscoveryConfidence.HIGH)

    def test_to_dict(self):
        """to_dict() should return JSON-serializable dict."""
        result = self.finding.to_dict()

        self.assertEqual(result["id"], "test-123")
        self.assertEqual(result["title"], "Add git retry logic")
        self.assertEqual(result["source"], "archive_pain")
        self.assertEqual(result["confidence"], "high")
        self.assertEqual(result["value"], "high")
        self.assertEqual(result["effort"], "low")
        self.assertEqual(result["evidence"]["frequency"], 5)
        self.assertEqual(result["sketch"], "Add retry wrapper around git commands")
        self.assertIn("git_utils.py", result["affected_files"])

    def test_to_dict_limits_data_points(self):
        """to_dict() should limit data_points to 5."""
        many_points = [f"point{i}" for i in range(10)]
        evidence = DiscoveryEvidence(
            source=DiscoverySource.ARCHIVE_PAIN,
            pattern="test",
            frequency=10,
            data_points=many_points,
        )
        finding = DiscoveryFinding(
            id="test",
            title="Test",
            source=DiscoverySource.ARCHIVE_PAIN,
            confidence=DiscoveryConfidence.MEDIUM,
            value=DiscoveryValue.MEDIUM,
            effort=DiscoveryEffort.MEDIUM,
            evidence=evidence,
            sketch="",
        )

        result = finding.to_dict()
        self.assertEqual(len(result["evidence"]["data_points"]), 5)

    def test_from_dict(self):
        """from_dict() should reconstruct finding from dict."""
        data = {
            "id": "restored-456",
            "title": "Restored finding",
            "source": "lesson_reinforcement",
            "confidence": "medium",
            "value": "low",
            "effort": "high",
            "evidence": {
                "source": "lesson_reinforcement",
                "pattern": "repeated lesson",
                "frequency": 8,
                "data_points": ["p1"],
                "time_range_days": 45,
            },
            "sketch": "Implementation notes",
            "affected_files": ["file1.py", "file2.py"],
        }

        result = DiscoveryFinding.from_dict(data)

        self.assertEqual(result.id, "restored-456")
        self.assertEqual(result.source, DiscoverySource.LESSON_REINFORCEMENT)
        self.assertEqual(result.confidence, DiscoveryConfidence.MEDIUM)
        self.assertEqual(result.evidence.frequency, 8)
        self.assertEqual(len(result.affected_files), 2)

    def test_from_dict_with_defaults(self):
        """from_dict() should handle missing optional fields."""
        data = {
            "id": "minimal",
            "title": "Minimal finding",
            "source": "archive_pain",
            # Missing: confidence, value, effort, sketch, affected_files
            "evidence": {
                "source": "archive_pain",
                "pattern": "test",
                "frequency": 1,
            },
        }

        result = DiscoveryFinding.from_dict(data)

        # Should use defaults
        self.assertEqual(result.confidence, DiscoveryConfidence.MEDIUM)
        self.assertEqual(result.value, DiscoveryValue.MEDIUM)
        self.assertEqual(result.effort, DiscoveryEffort.MEDIUM)
        self.assertEqual(result.sketch, "")
        self.assertEqual(result.affected_files, [])

    def test_roundtrip_to_dict_from_dict(self):
        """to_dict/from_dict should be reversible."""
        original = self.finding
        data = original.to_dict()
        restored = DiscoveryFinding.from_dict(data)

        self.assertEqual(restored.id, original.id)
        self.assertEqual(restored.title, original.title)
        self.assertEqual(restored.source, original.source)
        self.assertEqual(restored.confidence, original.confidence)


class TestScoringConstants(unittest.TestCase):
    """Tests for scoring constants."""

    def test_value_scores_defined(self):
        """VALUE_SCORES should have all values."""
        self.assertIn(DiscoveryValue.HIGH, VALUE_SCORES)
        self.assertIn(DiscoveryValue.MEDIUM, VALUE_SCORES)
        self.assertIn(DiscoveryValue.LOW, VALUE_SCORES)
        # Higher value = higher score
        self.assertGreater(VALUE_SCORES[DiscoveryValue.HIGH], VALUE_SCORES[DiscoveryValue.LOW])

    def test_effort_penalties_defined(self):
        """EFFORT_PENALTIES should have all values."""
        self.assertIn(DiscoveryEffort.HIGH, EFFORT_PENALTIES)
        self.assertIn(DiscoveryEffort.MEDIUM, EFFORT_PENALTIES)
        self.assertIn(DiscoveryEffort.LOW, EFFORT_PENALTIES)
        # Higher effort = more negative
        self.assertLess(EFFORT_PENALTIES[DiscoveryEffort.HIGH], EFFORT_PENALTIES[DiscoveryEffort.LOW])

    def test_confidence_boosts_defined(self):
        """CONFIDENCE_BOOSTS should have all values."""
        self.assertIn(DiscoveryConfidence.HIGH, CONFIDENCE_BOOSTS)
        self.assertIn(DiscoveryConfidence.MEDIUM, CONFIDENCE_BOOSTS)
        self.assertIn(DiscoveryConfidence.LOW, CONFIDENCE_BOOSTS)
        # Higher confidence = higher boost
        self.assertGreater(CONFIDENCE_BOOSTS[DiscoveryConfidence.HIGH], CONFIDENCE_BOOSTS[DiscoveryConfidence.LOW])


class TestScoreDiscovery(unittest.TestCase):
    """Tests for score_discovery function."""

    def _make_finding(self, value, effort, confidence, frequency=5):
        """Helper to create a finding with specific attributes."""
        evidence = DiscoveryEvidence(
            source=DiscoverySource.ARCHIVE_PAIN,
            pattern="test",
            frequency=frequency,
        )
        return DiscoveryFinding(
            id="test",
            title="Test",
            source=DiscoverySource.ARCHIVE_PAIN,
            confidence=confidence,
            value=value,
            effort=effort,
            evidence=evidence,
            sketch="",
        )

    def test_high_value_high_confidence_low_effort_scores_highest(self):
        """Best attributes should produce highest score."""
        best = self._make_finding(
            DiscoveryValue.HIGH,
            DiscoveryEffort.LOW,
            DiscoveryConfidence.HIGH,
            frequency=10,
        )
        worst = self._make_finding(
            DiscoveryValue.LOW,
            DiscoveryEffort.HIGH,
            DiscoveryConfidence.LOW,
            frequency=1,
        )

        self.assertGreater(score_discovery(best), score_discovery(worst))

    def test_frequency_bonus_capped(self):
        """Frequency bonus should be capped at 20."""
        low_freq = self._make_finding(
            DiscoveryValue.MEDIUM,
            DiscoveryEffort.MEDIUM,
            DiscoveryConfidence.MEDIUM,
            frequency=1,
        )
        high_freq = self._make_finding(
            DiscoveryValue.MEDIUM,
            DiscoveryEffort.MEDIUM,
            DiscoveryConfidence.MEDIUM,
            frequency=100,  # Very high
        )

        score_diff = score_discovery(high_freq) - score_discovery(low_freq)
        # Should be capped at 20 - 2 = 18 difference
        self.assertLessEqual(score_diff, 20)

    def test_value_affects_score(self):
        """Higher value should increase score."""
        high_value = self._make_finding(
            DiscoveryValue.HIGH,
            DiscoveryEffort.MEDIUM,
            DiscoveryConfidence.MEDIUM,
        )
        low_value = self._make_finding(
            DiscoveryValue.LOW,
            DiscoveryEffort.MEDIUM,
            DiscoveryConfidence.MEDIUM,
        )

        self.assertGreater(score_discovery(high_value), score_discovery(low_value))


class TestSortDiscoveries(unittest.TestCase):
    """Tests for sort_discoveries function."""

    def test_sorts_by_score_descending(self):
        """Should sort findings by score, highest first."""
        evidence = DiscoveryEvidence(
            source=DiscoverySource.ARCHIVE_PAIN,
            pattern="test",
            frequency=5,
        )

        low_score = DiscoveryFinding(
            id="low",
            title="Low",
            source=DiscoverySource.ARCHIVE_PAIN,
            confidence=DiscoveryConfidence.LOW,
            value=DiscoveryValue.LOW,
            effort=DiscoveryEffort.HIGH,
            evidence=evidence,
            sketch="",
        )

        high_score = DiscoveryFinding(
            id="high",
            title="High",
            source=DiscoverySource.ARCHIVE_PAIN,
            confidence=DiscoveryConfidence.HIGH,
            value=DiscoveryValue.HIGH,
            effort=DiscoveryEffort.LOW,
            evidence=evidence,
            sketch="",
        )

        findings = [low_score, high_score]
        sorted_findings = sort_discoveries(findings)

        self.assertEqual(sorted_findings[0].id, "high")
        self.assertEqual(sorted_findings[1].id, "low")

    def test_empty_list(self):
        """Should handle empty list."""
        result = sort_discoveries([])
        self.assertEqual(result, [])


class TestFormatDiscoveryForDisplay(unittest.TestCase):
    """Tests for format_discovery_for_display function."""

    def setUp(self):
        """Create sample finding."""
        evidence = DiscoveryEvidence(
            source=DiscoverySource.ARCHIVE_PAIN,
            pattern="git failures",
            frequency=5,
        )
        self.finding = DiscoveryFinding(
            id="test-123",
            title="Add git retry logic",
            source=DiscoverySource.ARCHIVE_PAIN,
            confidence=DiscoveryConfidence.HIGH,
            value=DiscoveryValue.HIGH,
            effort=DiscoveryEffort.LOW,
            evidence=evidence,
            sketch="First line of sketch\nSecond line",
        )

    def test_includes_index(self):
        """Should include 1-based index."""
        result = format_discovery_for_display(self.finding, 0)
        self.assertIn("[1]", result)

    def test_includes_title(self):
        """Should include finding title."""
        result = format_discovery_for_display(self.finding, 0)
        self.assertIn("Add git retry logic", result)

    def test_includes_confidence_emoji(self):
        """Should include confidence emoji."""
        result = format_discovery_for_display(self.finding, 0)
        # HIGH confidence = star
        self.assertIn("★", result)

    def test_includes_source(self):
        """Should include source."""
        result = format_discovery_for_display(self.finding, 0)
        self.assertIn("archive pain", result)

    def test_includes_evidence_pattern(self):
        """Should include evidence pattern and frequency."""
        result = format_discovery_for_display(self.finding, 0)
        self.assertIn("git failures", result)
        self.assertIn("5x", result)

    def test_includes_value_and_effort(self):
        """Should include value and effort labels."""
        result = format_discovery_for_display(self.finding, 0)
        self.assertIn("High", result)  # Value
        self.assertIn("Low", result)   # Effort

    def test_includes_sketch_preview(self):
        """Should include first line of sketch."""
        result = format_discovery_for_display(self.finding, 0)
        self.assertIn("First line of sketch", result)
        self.assertNotIn("Second line", result)

    def test_no_sketch_preview_when_empty(self):
        """Should not include sketch line when empty."""
        self.finding.sketch = ""
        result = format_discovery_for_display(self.finding, 0)
        self.assertNotIn("Sketch:", result)


class TestDiscoveryToObjective(unittest.TestCase):
    """Tests for discovery_to_objective function."""

    def test_returns_title(self):
        """Should return the finding title."""
        evidence = DiscoveryEvidence(
            source=DiscoverySource.ARCHIVE_PAIN,
            pattern="test",
            frequency=1,
        )
        finding = DiscoveryFinding(
            id="test",
            title="Implement new feature",
            source=DiscoverySource.ARCHIVE_PAIN,
            confidence=DiscoveryConfidence.MEDIUM,
            value=DiscoveryValue.MEDIUM,
            effort=DiscoveryEffort.MEDIUM,
            evidence=evidence,
            sketch="",
        )

        result = discovery_to_objective(finding)
        self.assertEqual(result, "Implement new feature")


class TestGetDefaultDiscoveryState(unittest.TestCase):
    """Tests for get_default_discovery_state function."""

    def test_returns_dict(self):
        """Should return a dict."""
        result = get_default_discovery_state()
        self.assertIsInstance(result, dict)

    def test_has_required_keys(self):
        """Should have all required keys."""
        result = get_default_discovery_state()
        self.assertIn("last_scan", result)
        self.assertIn("findings", result)
        self.assertIn("dismissed", result)
        self.assertIn("implemented", result)

    def test_default_values(self):
        """Should have correct default values."""
        result = get_default_discovery_state()
        self.assertIsNone(result["last_scan"])
        self.assertEqual(result["findings"], [])
        self.assertEqual(result["dismissed"], [])
        self.assertEqual(result["implemented"], [])


class TestGenerateDiscoveryId(unittest.TestCase):
    """Tests for generate_discovery_id function."""

    def test_returns_string(self):
        """Should return a string."""
        result = generate_discovery_id(DiscoverySource.ARCHIVE_PAIN, "Test title")
        self.assertIsInstance(result, str)

    def test_starts_with_discovery(self):
        """Should start with 'discovery-'."""
        result = generate_discovery_id(DiscoverySource.ARCHIVE_PAIN, "Test title")
        self.assertTrue(result.startswith("discovery-"))

    def test_deterministic(self):
        """Same inputs should produce same ID."""
        id1 = generate_discovery_id(DiscoverySource.ARCHIVE_PAIN, "Same title")
        id2 = generate_discovery_id(DiscoverySource.ARCHIVE_PAIN, "Same title")
        self.assertEqual(id1, id2)

    def test_different_source_different_id(self):
        """Different source should produce different ID."""
        id1 = generate_discovery_id(DiscoverySource.ARCHIVE_PAIN, "Test")
        id2 = generate_discovery_id(DiscoverySource.LESSON_REINFORCEMENT, "Test")
        self.assertNotEqual(id1, id2)

    def test_different_title_different_id(self):
        """Different title should produce different ID."""
        id1 = generate_discovery_id(DiscoverySource.ARCHIVE_PAIN, "Title A")
        id2 = generate_discovery_id(DiscoverySource.ARCHIVE_PAIN, "Title B")
        self.assertNotEqual(id1, id2)

    def test_long_title_handled(self):
        """Should handle very long titles."""
        long_title = "A" * 200
        result = generate_discovery_id(DiscoverySource.ARCHIVE_PAIN, long_title)
        self.assertIsInstance(result, str)


class TestThresholds(unittest.TestCase):
    """Tests for threshold constants."""

    def test_thresholds_defined(self):
        """Should have required thresholds."""
        self.assertIn("min_pain_frequency", DISCOVERY_THRESHOLDS)
        self.assertIn("min_lesson_reinforcement", DISCOVERY_THRESHOLDS)
        self.assertIn("archive_lookback_days", DISCOVERY_THRESHOLDS)
        self.assertIn("max_discoveries", DISCOVERY_THRESHOLDS)

    def test_thresholds_reasonable(self):
        """Thresholds should be reasonable values."""
        self.assertGreater(DISCOVERY_THRESHOLDS["min_pain_frequency"], 0)
        self.assertGreater(DISCOVERY_THRESHOLDS["archive_lookback_days"], 0)
        self.assertGreater(DISCOVERY_THRESHOLDS["max_discoveries"], 0)


class TestArchivePatterns(unittest.TestCase):
    """Tests for archive mining patterns."""

    def test_entry_types_defined(self):
        """Should have archive entry types."""
        self.assertIn("completed_objective", ARCHIVE_ENTRY_TYPES)
        self.assertIn("mismatch", ARCHIVE_ENTRY_TYPES)

    def test_mismatch_categories_defined(self):
        """Should have mismatch categories."""
        self.assertIn("git", MISMATCH_CATEGORIES)
        self.assertIn("test", MISMATCH_CATEGORIES)
        self.assertIn("path", MISMATCH_CATEGORIES)


if __name__ == "__main__":
    unittest.main()
