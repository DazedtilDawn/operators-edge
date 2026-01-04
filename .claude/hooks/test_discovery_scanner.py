#!/usr/bin/env python3
"""
Tests for discovery_scanner.py - self-aware feature discovery.

Tests the discovery scanners:
- Archive pain mining
- Lesson reinforcement analysis
- Integration gap detection
"""

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from datetime import datetime, timedelta

# Add hooks directory to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from discovery_config import (
    DiscoveryFinding,
    DiscoveryEvidence,
    DiscoverySource,
    DiscoveryConfidence,
    DiscoveryValue,
    DiscoveryEffort,
    score_discovery,
    sort_discoveries,
    generate_discovery_id,
)


class TestDiscoveryFinding(unittest.TestCase):
    """Tests for DiscoveryFinding dataclass."""

    def test_create_finding(self):
        """Should create a DiscoveryFinding with all fields."""
        evidence = DiscoveryEvidence(
            source=DiscoverySource.ARCHIVE_PAIN,
            pattern="5 mismatches in 'git' category",
            frequency=5,
            data_points=["push failed", "commit rejected"],
        )

        finding = DiscoveryFinding(
            id="discovery-abc123",
            title="Add git preview",
            source=DiscoverySource.ARCHIVE_PAIN,
            confidence=DiscoveryConfidence.HIGH,
            value=DiscoveryValue.HIGH,
            effort=DiscoveryEffort.LOW,
            evidence=evidence,
            sketch="Preview diff before push",
        )

        self.assertEqual(finding.title, "Add git preview")
        self.assertEqual(finding.source, DiscoverySource.ARCHIVE_PAIN)
        self.assertEqual(finding.confidence, DiscoveryConfidence.HIGH)

    def test_to_dict_and_from_dict(self):
        """Should serialize and deserialize correctly."""
        evidence = DiscoveryEvidence(
            source=DiscoverySource.LESSON_REINFORCEMENT,
            pattern="Lesson used 5x",
            frequency=5,
        )

        original = DiscoveryFinding(
            id="discovery-test",
            title="Automate something",
            source=DiscoverySource.LESSON_REINFORCEMENT,
            confidence=DiscoveryConfidence.MEDIUM,
            value=DiscoveryValue.MEDIUM,
            effort=DiscoveryEffort.MEDIUM,
            evidence=evidence,
            sketch="Do the thing",
        )

        data = original.to_dict()
        restored = DiscoveryFinding.from_dict(data)

        self.assertEqual(restored.id, original.id)
        self.assertEqual(restored.title, original.title)
        self.assertEqual(restored.source, original.source)
        self.assertEqual(restored.evidence.frequency, 5)


class TestDiscoveryScoring(unittest.TestCase):
    """Tests for discovery scoring and sorting."""

    def test_high_value_scores_higher(self):
        """High value findings should score higher than low value."""
        evidence = DiscoveryEvidence(
            source=DiscoverySource.ARCHIVE_PAIN,
            pattern="test",
            frequency=1,
        )

        high = DiscoveryFinding(
            id="high",
            title="High value",
            source=DiscoverySource.ARCHIVE_PAIN,
            confidence=DiscoveryConfidence.MEDIUM,
            value=DiscoveryValue.HIGH,
            effort=DiscoveryEffort.MEDIUM,
            evidence=evidence,
            sketch="",
        )

        low = DiscoveryFinding(
            id="low",
            title="Low value",
            source=DiscoverySource.ARCHIVE_PAIN,
            confidence=DiscoveryConfidence.MEDIUM,
            value=DiscoveryValue.LOW,
            effort=DiscoveryEffort.MEDIUM,
            evidence=evidence,
            sketch="",
        )

        self.assertGreater(score_discovery(high), score_discovery(low))

    def test_low_effort_scores_higher(self):
        """Low effort findings should score higher than high effort."""
        evidence = DiscoveryEvidence(
            source=DiscoverySource.ARCHIVE_PAIN,
            pattern="test",
            frequency=1,
        )

        easy = DiscoveryFinding(
            id="easy",
            title="Easy",
            source=DiscoverySource.ARCHIVE_PAIN,
            confidence=DiscoveryConfidence.MEDIUM,
            value=DiscoveryValue.MEDIUM,
            effort=DiscoveryEffort.LOW,
            evidence=evidence,
            sketch="",
        )

        hard = DiscoveryFinding(
            id="hard",
            title="Hard",
            source=DiscoverySource.ARCHIVE_PAIN,
            confidence=DiscoveryConfidence.MEDIUM,
            value=DiscoveryValue.MEDIUM,
            effort=DiscoveryEffort.HIGH,
            evidence=evidence,
            sketch="",
        )

        self.assertGreater(score_discovery(easy), score_discovery(hard))

    def test_sort_discoveries(self):
        """Should sort by score descending."""
        evidence = DiscoveryEvidence(
            source=DiscoverySource.ARCHIVE_PAIN,
            pattern="test",
            frequency=1,
        )

        findings = [
            DiscoveryFinding(id="low", title="Low", source=DiscoverySource.ARCHIVE_PAIN,
                           confidence=DiscoveryConfidence.LOW, value=DiscoveryValue.LOW,
                           effort=DiscoveryEffort.HIGH, evidence=evidence, sketch=""),
            DiscoveryFinding(id="high", title="High", source=DiscoverySource.ARCHIVE_PAIN,
                           confidence=DiscoveryConfidence.HIGH, value=DiscoveryValue.HIGH,
                           effort=DiscoveryEffort.LOW, evidence=evidence, sketch=""),
        ]

        sorted_findings = sort_discoveries(findings)

        self.assertEqual(sorted_findings[0].id, "high")
        self.assertEqual(sorted_findings[1].id, "low")


class TestArchivePainMiner(unittest.TestCase):
    """Tests for archive pain mining."""

    def test_load_archive_entries(self):
        """Should load entries from archive.jsonl."""
        from discovery_scanner import load_archive_entries

        with tempfile.TemporaryDirectory() as tmpdir:
            proof_dir = Path(tmpdir) / ".proof"
            proof_dir.mkdir()

            # Create test archive
            archive = proof_dir / "archive.jsonl"
            entries = [
                {"type": "mismatch", "timestamp": datetime.now().isoformat(),
                 "expectation": "git push works", "observation": "push rejected"},
                {"type": "completed_objective", "timestamp": datetime.now().isoformat(),
                 "objective": "Test objective"},
            ]
            archive.write_text('\n'.join(json.dumps(e) for e in entries))

            loaded = load_archive_entries(max_days=7, project_root=Path(tmpdir))

            self.assertEqual(len(loaded), 2)

    def test_categorize_mismatch(self):
        """Should categorize mismatches by keywords."""
        from discovery_scanner import categorize_mismatch

        self.assertEqual(categorize_mismatch("git push failed"), "git")
        self.assertEqual(categorize_mismatch("test assertion error"), "test")
        self.assertEqual(categorize_mismatch("import module failed"), "import")
        self.assertIsNone(categorize_mismatch("random error"))

    def test_mine_mismatch_patterns(self):
        """Should find mismatch patterns meeting threshold."""
        from discovery_scanner import mine_mismatch_patterns

        entries = [
            {"type": "mismatch", "expectation": "git push works", "observation": "rejected"},
            {"type": "mismatch", "expectation": "git commit works", "observation": "failed"},
            {"type": "mismatch", "expectation": "git reset worked", "observation": "no"},
            {"type": "mismatch", "expectation": "something else", "observation": "error"},
        ]

        patterns = mine_mismatch_patterns(entries)

        # Should find "git" category with 3 occurrences
        git_pattern = next((p for p in patterns if p[0] == "git"), None)
        self.assertIsNotNone(git_pattern)
        self.assertEqual(git_pattern[1], 3)


class TestLessonReinforcementAnalyzer(unittest.TestCase):
    """Tests for lesson reinforcement analysis."""

    def test_finds_actionable_reinforced_lessons(self):
        """Should find actionable lessons with high reinforcement."""
        from discovery_scanner import scan_lesson_reinforcement

        state = {
            "memory": [
                # Actionable lesson (specific tool/platform)
                {"trigger": "git", "lesson": "Always check status before push", "reinforced": 5},
                {"trigger": "other", "lesson": "Something else", "reinforced": 1},
            ]
        }

        findings = scan_lesson_reinforcement(state)

        # Should find the actionable highly-reinforced lesson
        self.assertEqual(len(findings), 1)
        self.assertIn("git", findings[0].title.lower())

    def test_filters_meta_lessons(self):
        """Should filter out meta-lessons (design principles)."""
        from discovery_scanner import scan_lesson_reinforcement

        state = {
            "memory": [
                # Meta-lesson (system internal, design principle)
                {"trigger": "hooks", "lesson": "Policy is not enforcement", "reinforced": 5},
                {"trigger": "memory", "lesson": "Memory beats storage", "reinforced": 5},
                {"trigger": "archive", "lesson": "Resolved enables pruning", "reinforced": 5},
            ]
        }

        findings = scan_lesson_reinforcement(state)

        # Should filter out all meta-lessons
        self.assertEqual(len(findings), 0)

    def test_no_findings_for_low_reinforcement(self):
        """Should not surface lessons below threshold."""
        from discovery_scanner import scan_lesson_reinforcement

        state = {
            "memory": [
                {"trigger": "git", "lesson": "Low reinforcement actionable", "reinforced": 1},
            ]
        }

        findings = scan_lesson_reinforcement(state)

        self.assertEqual(len(findings), 0)


class TestMetaLessonDetection(unittest.TestCase):
    """Tests for meta-lesson detection."""

    def test_detects_meta_triggers(self):
        """Should detect meta-lessons by trigger."""
        from discovery_scanner import is_meta_lesson

        # System-internal triggers are meta
        self.assertTrue(is_meta_lesson("hooks", "Any lesson text"))
        self.assertTrue(is_meta_lesson("memory", "Any lesson text"))
        self.assertTrue(is_meta_lesson("enforcement", "Any lesson text"))

    def test_detects_meta_language(self):
        """Should detect meta-lessons by language patterns."""
        from discovery_scanner import is_meta_lesson

        # Abstract verbs indicate meta-lessons
        self.assertTrue(is_meta_lesson("random", "X is not Y"))
        self.assertTrue(is_meta_lesson("random", "A beats B"))
        self.assertTrue(is_meta_lesson("random", "This enables that"))

    def test_detects_actionable_triggers(self):
        """Should recognize actionable triggers."""
        from discovery_scanner import is_meta_lesson

        # Tool/platform triggers are actionable
        self.assertFalse(is_meta_lesson("git", "Any lesson"))
        self.assertFalse(is_meta_lesson("python", "Any lesson"))
        self.assertFalse(is_meta_lesson("windows", "Any lesson"))

    def test_detects_actionable_verbs(self):
        """Should recognize actionable imperative verbs."""
        from discovery_scanner import is_meta_lesson

        # Imperative verbs indicate actionable lessons
        self.assertFalse(is_meta_lesson("random", "Always use X"))
        self.assertFalse(is_meta_lesson("random", "Never run Y"))
        self.assertFalse(is_meta_lesson("random", "Copy this to clipboard"))


class TestIntegrationGapFinder(unittest.TestCase):
    """Tests for integration gap detection."""

    def test_finds_clickup_gap(self):
        """Should find ClickUp integration opportunity."""
        from discovery_scanner import scan_integration_gaps

        findings = scan_integration_gaps()

        # Should have at least the ClickUp finding
        self.assertGreaterEqual(len(findings), 1)
        clickup = next((f for f in findings if "clickup" in f.title.lower()), None)
        self.assertIsNotNone(clickup)


class TestFullDiscoveryScan(unittest.TestCase):
    """Tests for the complete discovery scan."""

    def test_run_discovery_scan(self):
        """Should run all scanners and return findings."""
        from discovery_scanner import run_discovery_scan

        state = {
            "memory": [
                {"trigger": "test", "lesson": "Test lesson", "reinforced": 5},
            ]
        }

        findings, metadata = run_discovery_scan(state)

        # Should return findings and metadata
        self.assertIsInstance(findings, list)
        self.assertIn("last_scan", metadata)
        self.assertIn("sources_scanned", metadata)

    def test_deduplicates_findings(self):
        """Should deduplicate findings by ID."""
        from discovery_scanner import run_discovery_scan

        # Run twice - should get same findings (deduped)
        state = {"memory": []}
        findings1, _ = run_discovery_scan(state)
        findings2, _ = run_discovery_scan(state)

        self.assertEqual(len(findings1), len(findings2))


class TestDiscoveryIdGeneration(unittest.TestCase):
    """Tests for discovery ID generation."""

    def test_generates_stable_id(self):
        """Same inputs should generate same ID."""
        id1 = generate_discovery_id(DiscoverySource.ARCHIVE_PAIN, "Test title")
        id2 = generate_discovery_id(DiscoverySource.ARCHIVE_PAIN, "Test title")

        self.assertEqual(id1, id2)

    def test_different_inputs_different_id(self):
        """Different inputs should generate different IDs."""
        id1 = generate_discovery_id(DiscoverySource.ARCHIVE_PAIN, "Title A")
        id2 = generate_discovery_id(DiscoverySource.ARCHIVE_PAIN, "Title B")

        self.assertNotEqual(id1, id2)


if __name__ == '__main__':
    unittest.main()
