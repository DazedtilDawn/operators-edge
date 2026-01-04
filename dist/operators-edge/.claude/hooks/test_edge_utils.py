#!/usr/bin/env python3
"""
Tests for edge_utils.py

Coverage:
- Verifies the facade module correctly re-exports all utilities
- Tests that imports from edge_utils work as expected
- Validates __all__ contains expected exports
- Confirms __version__ is defined
"""

import unittest


class TestFacadeImports(unittest.TestCase):
    """Tests for facade module re-exports."""

    def test_import_edge_utils_succeeds(self):
        """Should be able to import edge_utils."""
        import edge_utils
        self.assertIsNotNone(edge_utils)

    def test_version_defined(self):
        """Should have __version__ defined."""
        import edge_utils
        self.assertTrue(hasattr(edge_utils, '__version__'))
        self.assertIsInstance(edge_utils.__version__, str)

    def test_all_defined(self):
        """Should have __all__ defined."""
        import edge_utils
        self.assertTrue(hasattr(edge_utils, '__all__'))
        self.assertIsInstance(edge_utils.__all__, list)
        self.assertGreater(len(edge_utils.__all__), 0)


class TestConfigReExports(unittest.TestCase):
    """Tests for edge_config.py re-exports."""

    def test_session_context_exported(self):
        """SessionContext should be importable from edge_utils."""
        from edge_utils import SessionContext
        self.assertTrue(hasattr(SessionContext, 'NEEDS_PLAN'))

    def test_research_indicators_exported(self):
        """RESEARCH_INDICATORS should be importable."""
        from edge_utils import RESEARCH_INDICATORS
        self.assertIsInstance(RESEARCH_INDICATORS, dict)

    def test_scan_patterns_exported(self):
        """SCAN_PATTERNS should be importable."""
        from edge_utils import SCAN_PATTERNS
        self.assertIsInstance(SCAN_PATTERNS, dict)

    def test_complexity_thresholds_exported(self):
        """COMPLEXITY_THRESHOLDS should be importable."""
        from edge_utils import COMPLEXITY_THRESHOLDS
        self.assertIsInstance(COMPLEXITY_THRESHOLDS, dict)

    def test_memory_settings_exported(self):
        """MEMORY_SETTINGS should be importable."""
        from edge_utils import MEMORY_SETTINGS
        self.assertIsInstance(MEMORY_SETTINGS, dict)

    def test_archive_settings_exported(self):
        """ARCHIVE_SETTINGS should be importable."""
        from edge_utils import ARCHIVE_SETTINGS
        self.assertIsInstance(ARCHIVE_SETTINGS, dict)

    def test_entropy_thresholds_exported(self):
        """ENTROPY_THRESHOLDS should be importable."""
        from edge_utils import ENTROPY_THRESHOLDS
        self.assertIsInstance(ENTROPY_THRESHOLDS, dict)


class TestStateUtilsReExports(unittest.TestCase):
    """Tests for state_utils.py re-exports."""

    def test_get_project_dir_exported(self):
        """get_project_dir should be importable."""
        from edge_utils import get_project_dir
        self.assertTrue(callable(get_project_dir))

    def test_get_state_dir_exported(self):
        """get_state_dir should be importable."""
        from edge_utils import get_state_dir
        self.assertTrue(callable(get_state_dir))

    def test_get_proof_dir_exported(self):
        """get_proof_dir should be importable."""
        from edge_utils import get_proof_dir
        self.assertTrue(callable(get_proof_dir))

    def test_parse_yaml_value_exported(self):
        """parse_yaml_value should be importable."""
        from edge_utils import parse_yaml_value
        self.assertTrue(callable(parse_yaml_value))

    def test_load_yaml_state_exported(self):
        """load_yaml_state should be importable."""
        from edge_utils import load_yaml_state
        self.assertTrue(callable(load_yaml_state))

    def test_file_hash_exported(self):
        """file_hash should be importable."""
        from edge_utils import file_hash
        self.assertTrue(callable(file_hash))

    def test_log_failure_exported(self):
        """log_failure should be importable."""
        from edge_utils import log_failure
        self.assertTrue(callable(log_failure))

    def test_log_proof_exported(self):
        """log_proof should be importable."""
        from edge_utils import log_proof
        self.assertTrue(callable(log_proof))

    def test_respond_exported(self):
        """respond should be importable."""
        from edge_utils import respond
        self.assertTrue(callable(respond))

    def test_get_current_step_exported(self):
        """get_current_step should be importable."""
        from edge_utils import get_current_step
        self.assertTrue(callable(get_current_step))

    def test_get_step_by_status_exported(self):
        """get_step_by_status should be importable."""
        from edge_utils import get_step_by_status
        self.assertTrue(callable(get_step_by_status))


class TestArchiveUtilsReExports(unittest.TestCase):
    """Tests for archive_utils.py re-exports."""

    def test_log_to_archive_exported(self):
        """log_to_archive should be importable."""
        from edge_utils import log_to_archive
        self.assertTrue(callable(log_to_archive))

    def test_archive_completed_step_exported(self):
        """archive_completed_step should be importable."""
        from edge_utils import archive_completed_step
        self.assertTrue(callable(archive_completed_step))

    def test_load_archive_exported(self):
        """load_archive should be importable."""
        from edge_utils import load_archive
        self.assertTrue(callable(load_archive))

    def test_search_archive_exported(self):
        """search_archive should be importable."""
        from edge_utils import search_archive
        self.assertTrue(callable(search_archive))

    def test_check_state_entropy_exported(self):
        """check_state_entropy should be importable."""
        from edge_utils import check_state_entropy
        self.assertTrue(callable(check_state_entropy))

    def test_compute_prune_plan_exported(self):
        """compute_prune_plan should be importable."""
        from edge_utils import compute_prune_plan
        self.assertTrue(callable(compute_prune_plan))


class TestResearchUtilsReExports(unittest.TestCase):
    """Tests for research_utils.py re-exports."""

    def test_generate_research_id_exported(self):
        """generate_research_id should be importable."""
        from edge_utils import generate_research_id
        self.assertTrue(callable(generate_research_id))

    def test_get_research_items_exported(self):
        """get_research_items should be importable."""
        from edge_utils import get_research_items
        self.assertTrue(callable(get_research_items))

    def test_get_pending_research_exported(self):
        """get_pending_research should be importable."""
        from edge_utils import get_pending_research
        self.assertTrue(callable(get_pending_research))

    def test_generate_research_prompt_exported(self):
        """generate_research_prompt should be importable."""
        from edge_utils import generate_research_prompt
        self.assertTrue(callable(generate_research_prompt))


class TestBrainstormUtilsReExports(unittest.TestCase):
    """Tests for brainstorm_utils.py re-exports."""

    def test_scan_code_markers_exported(self):
        """scan_code_markers should be importable."""
        from edge_utils import scan_code_markers
        self.assertTrue(callable(scan_code_markers))

    def test_run_brainstorm_scan_exported(self):
        """run_brainstorm_scan should be importable."""
        from edge_utils import run_brainstorm_scan
        self.assertTrue(callable(run_brainstorm_scan))

    def test_format_scan_results_exported(self):
        """format_scan_results should be importable."""
        from edge_utils import format_scan_results
        self.assertTrue(callable(format_scan_results))


class TestYoloConfigReExports(unittest.TestCase):
    """Tests for yolo_config.py re-exports."""

    def test_trust_level_exported(self):
        """TrustLevel should be importable."""
        from edge_utils import TrustLevel
        self.assertTrue(hasattr(TrustLevel, 'BLOCKED'))

    def test_auto_tools_exported(self):
        """AUTO_TOOLS should be importable."""
        from edge_utils import AUTO_TOOLS
        self.assertIsInstance(AUTO_TOOLS, (list, set, frozenset))

    def test_blocked_bash_patterns_exported(self):
        """BLOCKED_BASH_PATTERNS should be importable."""
        from edge_utils import BLOCKED_BASH_PATTERNS
        self.assertIsInstance(BLOCKED_BASH_PATTERNS, list)

    def test_classify_bash_command_exported(self):
        """classify_bash_command should be importable."""
        from edge_utils import classify_bash_command
        self.assertTrue(callable(classify_bash_command))

    def test_classify_action_exported(self):
        """classify_action should be importable."""
        from edge_utils import classify_action
        self.assertTrue(callable(classify_action))

    def test_is_hard_blocked_exported(self):
        """is_hard_blocked should be importable."""
        from edge_utils import is_hard_blocked
        self.assertTrue(callable(is_hard_blocked))


class TestOrchestrationUtilsReExports(unittest.TestCase):
    """Tests for orchestration_utils.py re-exports."""

    def test_detect_session_context_exported(self):
        """detect_session_context should be importable."""
        from edge_utils import detect_session_context
        self.assertTrue(callable(detect_session_context))

    def test_get_orchestrator_suggestion_exported(self):
        """get_orchestrator_suggestion should be importable."""
        from edge_utils import get_orchestrator_suggestion
        self.assertTrue(callable(get_orchestrator_suggestion))

    def test_surface_relevant_memory_exported(self):
        """surface_relevant_memory should be importable."""
        from edge_utils import surface_relevant_memory
        self.assertTrue(callable(surface_relevant_memory))

    def test_reinforce_memory_exported(self):
        """reinforce_memory should be importable."""
        from edge_utils import reinforce_memory
        self.assertTrue(callable(reinforce_memory))

    def test_lesson_themes_exported(self):
        """LESSON_THEMES should be importable."""
        from edge_utils import LESSON_THEMES
        self.assertIsInstance(LESSON_THEMES, dict)

    def test_compare_lessons_exported(self):
        """compare_lessons should be importable."""
        from edge_utils import compare_lessons
        self.assertTrue(callable(compare_lessons))

    def test_adaptation_checks_exported(self):
        """ADAPTATION_CHECKS should be importable."""
        from edge_utils import ADAPTATION_CHECKS
        self.assertIsInstance(ADAPTATION_CHECKS, list)


class TestAllListCompleteness(unittest.TestCase):
    """Tests that __all__ contains all expected exports."""

    def test_all_contains_session_context(self):
        """__all__ should include SessionContext."""
        from edge_utils import __all__
        self.assertIn("SessionContext", __all__)

    def test_all_contains_respond(self):
        """__all__ should include respond."""
        from edge_utils import __all__
        self.assertIn("respond", __all__)

    def test_all_contains_log_to_archive(self):
        """__all__ should include log_to_archive."""
        from edge_utils import __all__
        self.assertIn("log_to_archive", __all__)

    def test_all_contains_classify_action(self):
        """__all__ should include classify_action."""
        from edge_utils import __all__
        self.assertIn("classify_action", __all__)

    def test_all_items_are_importable(self):
        """All items in __all__ should be importable."""
        import edge_utils
        for name in edge_utils.__all__:
            self.assertTrue(
                hasattr(edge_utils, name),
                f"{name} in __all__ but not importable"
            )


class TestBackwardCompatibility(unittest.TestCase):
    """Tests for backward compatibility with older import patterns."""

    def test_common_import_pattern_1(self):
        """Test: from edge_utils import respond, load_yaml_state."""
        from edge_utils import respond, load_yaml_state
        self.assertTrue(callable(respond))
        self.assertTrue(callable(load_yaml_state))

    def test_common_import_pattern_2(self):
        """Test: from edge_utils import SessionContext."""
        from edge_utils import SessionContext
        self.assertEqual(SessionContext.NEEDS_PLAN, "needs_plan")

    def test_common_import_pattern_3(self):
        """Test: from edge_utils import classify_bash_command, TrustLevel."""
        from edge_utils import classify_bash_command, TrustLevel
        self.assertTrue(callable(classify_bash_command))
        self.assertIsNotNone(TrustLevel)


if __name__ == "__main__":
    unittest.main()
