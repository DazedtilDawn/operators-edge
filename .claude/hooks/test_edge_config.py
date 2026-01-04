#!/usr/bin/env python3
"""
Tests for edge_config.py

Coverage:
- SessionContext class attributes
- RESEARCH_INDICATORS configuration
- SCAN_PATTERNS configuration
- COMPLEXITY_THRESHOLDS configuration
- MEMORY_SETTINGS configuration
- ARCHIVE_SETTINGS configuration
- ENTROPY_THRESHOLDS configuration
"""

import unittest

from edge_config import (
    SessionContext,
    RESEARCH_INDICATORS,
    SCAN_PATTERNS,
    COMPLEXITY_THRESHOLDS,
    MEMORY_SETTINGS,
    ARCHIVE_SETTINGS,
    ENTROPY_THRESHOLDS,
)


class TestSessionContext(unittest.TestCase):
    """Tests for SessionContext class."""

    def test_needs_plan_defined(self):
        """NEEDS_PLAN should be defined."""
        self.assertEqual(SessionContext.NEEDS_PLAN, "needs_plan")

    def test_needs_research_defined(self):
        """NEEDS_RESEARCH should be defined."""
        self.assertEqual(SessionContext.NEEDS_RESEARCH, "needs_research")

    def test_awaiting_research_defined(self):
        """AWAITING_RESEARCH should be defined."""
        self.assertEqual(SessionContext.AWAITING_RESEARCH, "awaiting_research")

    def test_ready_for_step_defined(self):
        """READY_FOR_STEP should be defined."""
        self.assertEqual(SessionContext.READY_FOR_STEP, "ready_for_step")

    def test_step_in_progress_defined(self):
        """STEP_IN_PROGRESS should be defined."""
        self.assertEqual(SessionContext.STEP_IN_PROGRESS, "step_in_progress")

    def test_potential_mismatch_defined(self):
        """POTENTIAL_MISMATCH should be defined."""
        self.assertEqual(SessionContext.POTENTIAL_MISMATCH, "potential_mismatch")

    def test_unresolved_mismatch_defined(self):
        """UNRESOLVED_MISMATCH should be defined."""
        self.assertEqual(SessionContext.UNRESOLVED_MISMATCH, "unresolved_mismatch")

    def test_needs_adaptation_defined(self):
        """NEEDS_ADAPTATION should be defined."""
        self.assertEqual(SessionContext.NEEDS_ADAPTATION, "needs_adaptation")

    def test_all_complete_defined(self):
        """ALL_COMPLETE should be defined."""
        self.assertEqual(SessionContext.ALL_COMPLETE, "all_complete")

    def test_needs_pruning_defined(self):
        """NEEDS_PRUNING should be defined."""
        self.assertEqual(SessionContext.NEEDS_PRUNING, "needs_pruning")

    def test_needs_scoring_defined(self):
        """NEEDS_SCORING should be defined."""
        self.assertEqual(SessionContext.NEEDS_SCORING, "needs_scoring")

    def test_all_contexts_are_strings(self):
        """All context values should be strings."""
        contexts = [
            SessionContext.NEEDS_PLAN,
            SessionContext.NEEDS_RESEARCH,
            SessionContext.AWAITING_RESEARCH,
            SessionContext.READY_FOR_STEP,
            SessionContext.STEP_IN_PROGRESS,
            SessionContext.POTENTIAL_MISMATCH,
            SessionContext.UNRESOLVED_MISMATCH,
            SessionContext.NEEDS_ADAPTATION,
            SessionContext.ALL_COMPLETE,
            SessionContext.NEEDS_PRUNING,
            SessionContext.NEEDS_SCORING,
        ]
        for ctx in contexts:
            self.assertIsInstance(ctx, str)

    def test_all_contexts_unique(self):
        """All context values should be unique."""
        contexts = [
            SessionContext.NEEDS_PLAN,
            SessionContext.NEEDS_RESEARCH,
            SessionContext.AWAITING_RESEARCH,
            SessionContext.READY_FOR_STEP,
            SessionContext.STEP_IN_PROGRESS,
            SessionContext.POTENTIAL_MISMATCH,
            SessionContext.UNRESOLVED_MISMATCH,
            SessionContext.NEEDS_ADAPTATION,
            SessionContext.ALL_COMPLETE,
            SessionContext.NEEDS_PRUNING,
            SessionContext.NEEDS_SCORING,
        ]
        self.assertEqual(len(contexts), len(set(contexts)))


class TestResearchIndicators(unittest.TestCase):
    """Tests for RESEARCH_INDICATORS configuration."""

    def test_is_dict(self):
        """RESEARCH_INDICATORS should be a dict."""
        self.assertIsInstance(RESEARCH_INDICATORS, dict)

    def test_has_technologies(self):
        """Should have technologies key."""
        self.assertIn("technologies", RESEARCH_INDICATORS)
        self.assertIsInstance(RESEARCH_INDICATORS["technologies"], list)

    def test_technologies_not_empty(self):
        """Technologies list should not be empty."""
        self.assertGreater(len(RESEARCH_INDICATORS["technologies"]), 0)

    def test_technologies_are_strings(self):
        """All technologies should be strings."""
        for tech in RESEARCH_INDICATORS["technologies"]:
            self.assertIsInstance(tech, str)

    def test_includes_common_technologies(self):
        """Should include common complex technologies."""
        techs = RESEARCH_INDICATORS["technologies"]
        self.assertIn("kubernetes", techs)
        self.assertIn("docker", techs)
        self.assertIn("aws", techs)

    def test_has_ambiguity_signals(self):
        """Should have ambiguity_signals key."""
        self.assertIn("ambiguity_signals", RESEARCH_INDICATORS)
        self.assertIsInstance(RESEARCH_INDICATORS["ambiguity_signals"], list)

    def test_ambiguity_signals_not_empty(self):
        """Ambiguity signals list should not be empty."""
        self.assertGreater(len(RESEARCH_INDICATORS["ambiguity_signals"]), 0)

    def test_includes_common_ambiguity_signals(self):
        """Should include common ambiguity phrases."""
        signals = RESEARCH_INDICATORS["ambiguity_signals"]
        self.assertIn("best way", signals)
        self.assertIn("should i", signals)

    def test_has_research_verbs(self):
        """Should have research_verbs key."""
        self.assertIn("research_verbs", RESEARCH_INDICATORS)
        self.assertIsInstance(RESEARCH_INDICATORS["research_verbs"], list)

    def test_research_verbs_not_empty(self):
        """Research verbs list should not be empty."""
        self.assertGreater(len(RESEARCH_INDICATORS["research_verbs"]), 0)


class TestScanPatterns(unittest.TestCase):
    """Tests for SCAN_PATTERNS configuration."""

    def test_is_dict(self):
        """SCAN_PATTERNS should be a dict."""
        self.assertIsInstance(SCAN_PATTERNS, dict)

    def test_has_code_markers(self):
        """Should have code_markers key."""
        self.assertIn("code_markers", SCAN_PATTERNS)
        self.assertIsInstance(SCAN_PATTERNS["code_markers"], list)

    def test_code_markers_includes_todo_fixme(self):
        """Should include TODO and FIXME markers."""
        markers = SCAN_PATTERNS["code_markers"]
        self.assertIn("TODO", markers)
        self.assertIn("FIXME", markers)

    def test_has_skip_dirs(self):
        """Should have skip_dirs key."""
        self.assertIn("skip_dirs", SCAN_PATTERNS)
        self.assertIsInstance(SCAN_PATTERNS["skip_dirs"], list)

    def test_skip_dirs_includes_git_node_modules(self):
        """Should skip .git and node_modules."""
        skip = SCAN_PATTERNS["skip_dirs"]
        self.assertIn(".git", skip)
        self.assertIn("node_modules", skip)

    def test_has_code_extensions(self):
        """Should have code_extensions key."""
        self.assertIn("code_extensions", SCAN_PATTERNS)
        self.assertIsInstance(SCAN_PATTERNS["code_extensions"], list)

    def test_code_extensions_includes_common_langs(self):
        """Should include common language extensions."""
        exts = SCAN_PATTERNS["code_extensions"]
        self.assertIn(".py", exts)
        self.assertIn(".js", exts)
        self.assertIn(".ts", exts)

    def test_code_extensions_start_with_dot(self):
        """All extensions should start with dot."""
        for ext in SCAN_PATTERNS["code_extensions"]:
            self.assertTrue(ext.startswith("."), f"Extension {ext} should start with .")


class TestComplexityThresholds(unittest.TestCase):
    """Tests for COMPLEXITY_THRESHOLDS configuration."""

    def test_is_dict(self):
        """COMPLEXITY_THRESHOLDS should be a dict."""
        self.assertIsInstance(COMPLEXITY_THRESHOLDS, dict)

    def test_has_large_file_lines(self):
        """Should have large_file_lines key."""
        self.assertIn("large_file_lines", COMPLEXITY_THRESHOLDS)
        self.assertIsInstance(COMPLEXITY_THRESHOLDS["large_file_lines"], int)

    def test_large_file_lines_reasonable(self):
        """large_file_lines should be reasonable."""
        self.assertGreater(COMPLEXITY_THRESHOLDS["large_file_lines"], 100)
        self.assertLess(COMPLEXITY_THRESHOLDS["large_file_lines"], 10000)

    def test_has_very_large_file_lines(self):
        """Should have very_large_file_lines key."""
        self.assertIn("very_large_file_lines", COMPLEXITY_THRESHOLDS)
        self.assertIsInstance(COMPLEXITY_THRESHOLDS["very_large_file_lines"], int)

    def test_very_large_greater_than_large(self):
        """very_large_file_lines should be greater than large_file_lines."""
        self.assertGreater(
            COMPLEXITY_THRESHOLDS["very_large_file_lines"],
            COMPLEXITY_THRESHOLDS["large_file_lines"]
        )

    def test_has_max_files_to_scan(self):
        """Should have max_files_to_scan key."""
        self.assertIn("max_files_to_scan", COMPLEXITY_THRESHOLDS)
        self.assertIsInstance(COMPLEXITY_THRESHOLDS["max_files_to_scan"], int)

    def test_max_files_to_scan_reasonable(self):
        """max_files_to_scan should be reasonable."""
        self.assertGreater(COMPLEXITY_THRESHOLDS["max_files_to_scan"], 10)
        self.assertLess(COMPLEXITY_THRESHOLDS["max_files_to_scan"], 10000)


class TestMemorySettings(unittest.TestCase):
    """Tests for MEMORY_SETTINGS configuration."""

    def test_is_dict(self):
        """MEMORY_SETTINGS should be a dict."""
        self.assertIsInstance(MEMORY_SETTINGS, dict)

    def test_has_decay_threshold_days(self):
        """Should have decay_threshold_days key."""
        self.assertIn("decay_threshold_days", MEMORY_SETTINGS)
        self.assertIsInstance(MEMORY_SETTINGS["decay_threshold_days"], int)

    def test_decay_threshold_reasonable(self):
        """decay_threshold_days should be reasonable."""
        self.assertGreater(MEMORY_SETTINGS["decay_threshold_days"], 0)
        self.assertLessEqual(MEMORY_SETTINGS["decay_threshold_days"], 365)

    def test_has_reinforcement_threshold(self):
        """Should have reinforcement_threshold key."""
        self.assertIn("reinforcement_threshold", MEMORY_SETTINGS)
        self.assertIsInstance(MEMORY_SETTINGS["reinforcement_threshold"], int)

    def test_has_max_memory_items(self):
        """Should have max_memory_items key."""
        self.assertIn("max_memory_items", MEMORY_SETTINGS)
        self.assertIsInstance(MEMORY_SETTINGS["max_memory_items"], int)

    def test_max_memory_items_reasonable(self):
        """max_memory_items should be reasonable."""
        self.assertGreater(MEMORY_SETTINGS["max_memory_items"], 0)
        self.assertLessEqual(MEMORY_SETTINGS["max_memory_items"], 1000)


class TestArchiveSettings(unittest.TestCase):
    """Tests for ARCHIVE_SETTINGS configuration."""

    def test_is_dict(self):
        """ARCHIVE_SETTINGS should be a dict."""
        self.assertIsInstance(ARCHIVE_SETTINGS, dict)

    def test_has_max_completed_steps_in_state(self):
        """Should have max_completed_steps_in_state key."""
        self.assertIn("max_completed_steps_in_state", ARCHIVE_SETTINGS)
        self.assertIsInstance(ARCHIVE_SETTINGS["max_completed_steps_in_state"], int)

    def test_has_max_archive_entries_to_load(self):
        """Should have max_archive_entries_to_load key."""
        self.assertIn("max_archive_entries_to_load", ARCHIVE_SETTINGS)
        self.assertIsInstance(ARCHIVE_SETTINGS["max_archive_entries_to_load"], int)

    def test_has_max_search_entries(self):
        """Should have max_search_entries key."""
        self.assertIn("max_search_entries", ARCHIVE_SETTINGS)
        self.assertIsInstance(ARCHIVE_SETTINGS["max_search_entries"], int)


class TestEntropyThresholds(unittest.TestCase):
    """Tests for ENTROPY_THRESHOLDS configuration."""

    def test_is_dict(self):
        """ENTROPY_THRESHOLDS should be a dict."""
        self.assertIsInstance(ENTROPY_THRESHOLDS, dict)

    def test_has_max_completed_steps(self):
        """Should have max_completed_steps key."""
        self.assertIn("max_completed_steps", ENTROPY_THRESHOLDS)
        self.assertIsInstance(ENTROPY_THRESHOLDS["max_completed_steps"], int)

    def test_has_max_resolved_mismatches(self):
        """Should have max_resolved_mismatches key."""
        self.assertIn("max_resolved_mismatches", ENTROPY_THRESHOLDS)
        self.assertIsInstance(ENTROPY_THRESHOLDS["max_resolved_mismatches"], int)

    def test_max_completed_steps_reasonable(self):
        """max_completed_steps should be reasonable."""
        self.assertGreaterEqual(ENTROPY_THRESHOLDS["max_completed_steps"], 0)
        self.assertLessEqual(ENTROPY_THRESHOLDS["max_completed_steps"], 100)


if __name__ == "__main__":
    unittest.main()
