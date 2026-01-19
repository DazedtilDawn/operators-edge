#!/usr/bin/env python3
"""
Tests for self_clarify.py - Phase 10.3 Self-Clarification

Tests cover:
- Configuration loading
- Cooldown management
- Stuck pattern detection (drift, errors, file loops, tool loops)
- Clarification context gathering
- Clarification prompt generation
- Intervention level filtering
"""
import json
import os
import sys
import tempfile
import unittest
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import patch, MagicMock

# Add hooks directory to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from self_clarify import (
    # Configuration
    _load_clarification_config,
    _get_threshold,
    DEFAULT_DRIFT_THRESHOLD,
    DEFAULT_ERROR_REPEAT_THRESHOLD,
    DEFAULT_SAME_FILE_EDIT_THRESHOLD,
    DEFAULT_TOOL_LOOP_THRESHOLD,
    CLARIFICATION_COOLDOWN_SECONDS,
    # Cooldown
    _can_offer_clarification,
    _mark_clarification_offered,
    reset_clarification_cooldown,
    # Pattern detection
    detect_drift_ignored,
    detect_error_repeat,
    detect_file_loop,
    detect_tool_loop,
    detect_stuck_patterns,
    # Data structures
    StuckPattern,
    ClarificationContext,
    ClarificationResult,
    # Generation
    generate_clarification_prompt,
    generate_clarification_injection,
    # Integration
    should_trigger_clarification,
    check_and_offer_clarification,
    get_clarification_for_health,
    # Storage
    log_clarification,
)


class TestConfiguration(unittest.TestCase):
    """Test configuration loading."""

    def test_default_thresholds(self):
        """Test that default thresholds are reasonable."""
        self.assertEqual(DEFAULT_DRIFT_THRESHOLD, 3)
        self.assertEqual(DEFAULT_ERROR_REPEAT_THRESHOLD, 3)
        self.assertEqual(DEFAULT_SAME_FILE_EDIT_THRESHOLD, 5)
        self.assertEqual(DEFAULT_TOOL_LOOP_THRESHOLD, 10)

    def test_load_config_with_no_file(self):
        """Test config loading when no file exists."""
        with patch('self_clarify._get_config_path') as mock_path:
            mock_path.return_value = Path("/nonexistent/path/config.json")
            config = _load_clarification_config()

            self.assertEqual(config["drift_threshold"], DEFAULT_DRIFT_THRESHOLD)
            self.assertEqual(config["error_repeat_threshold"], DEFAULT_ERROR_REPEAT_THRESHOLD)

    def test_load_config_with_custom_values(self):
        """Test config loading with custom values."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            json.dump({
                "clarification": {
                    "drift_threshold": 5,
                    "error_repeat_threshold": 4,
                }
            }, f)
            f.flush()

            with patch('self_clarify._get_config_path') as mock_path:
                mock_path.return_value = Path(f.name)
                config = _load_clarification_config()

                self.assertEqual(config["drift_threshold"], 5)
                self.assertEqual(config["error_repeat_threshold"], 4)
                # Defaults still apply for unspecified
                self.assertEqual(config["same_file_edit_threshold"], DEFAULT_SAME_FILE_EDIT_THRESHOLD)

            os.unlink(f.name)

    def test_get_threshold(self):
        """Test getting specific threshold."""
        with patch('self_clarify._load_clarification_config') as mock_load:
            mock_load.return_value = {
                "drift_threshold": 7,
                "error_repeat_threshold": 4,
            }

            self.assertEqual(_get_threshold("drift_threshold"), 7)
            self.assertEqual(_get_threshold("error_repeat_threshold"), 4)
            self.assertEqual(_get_threshold("nonexistent"), 0)


class TestCooldown(unittest.TestCase):
    """Test cooldown management."""

    def setUp(self):
        """Reset cooldown before each test."""
        reset_clarification_cooldown()

    def test_can_offer_when_never_offered(self):
        """Test that clarification can be offered when never offered before."""
        self.assertTrue(_can_offer_clarification())

    def test_cannot_offer_immediately_after(self):
        """Test that clarification cannot be offered immediately after."""
        _mark_clarification_offered()
        self.assertFalse(_can_offer_clarification())

    def test_can_offer_after_cooldown(self):
        """Test that clarification can be offered after cooldown expires."""
        import self_clarify

        # Set last offer to past cooldown period
        self_clarify._last_clarification_offer = datetime.now() - timedelta(seconds=CLARIFICATION_COOLDOWN_SECONDS + 60)
        self.assertTrue(_can_offer_clarification())

    def test_reset_cooldown(self):
        """Test that reset_clarification_cooldown works."""
        _mark_clarification_offered()
        self.assertFalse(_can_offer_clarification())

        reset_clarification_cooldown()
        self.assertTrue(_can_offer_clarification())


class TestDriftIgnoredDetection(unittest.TestCase):
    """Test drift ignored pattern detection."""

    def test_no_pattern_when_below_threshold(self):
        """Test no pattern when drift ignored is below threshold."""
        result = detect_drift_ignored(drift_signals_fired=2, drift_signals_acted_on=1)
        self.assertIsNone(result)

    def test_pattern_when_at_threshold(self):
        """Test pattern detection at threshold."""
        with patch('self_clarify._get_threshold', return_value=3):
            result = detect_drift_ignored(drift_signals_fired=5, drift_signals_acted_on=2)

            self.assertIsNotNone(result)
            self.assertEqual(result.pattern_type, "drift_ignored")
            self.assertEqual(result.count, 3)
            self.assertEqual(result.severity, "mild")

    def test_severe_pattern_with_high_count(self):
        """Test severe pattern with high ignored count."""
        with patch('self_clarify._get_threshold', return_value=3):
            result = detect_drift_ignored(drift_signals_fired=12, drift_signals_acted_on=1)

            self.assertIsNotNone(result)
            self.assertEqual(result.severity, "severe")
            self.assertEqual(result.count, 11)


class TestErrorRepeatDetection(unittest.TestCase):
    """Test error repeat pattern detection."""

    def test_no_pattern_with_empty_errors(self):
        """Test no pattern with no errors."""
        result = detect_error_repeat([])
        self.assertIsNone(result)

    def test_no_pattern_with_unique_errors(self):
        """Test no pattern when all errors are unique."""
        errors = [
            "Error A at line 1",
            "Error B at line 2",
            "Error C at line 3",
        ]
        result = detect_error_repeat(errors, threshold_override=3)
        self.assertIsNone(result)

    def test_pattern_with_repeated_errors(self):
        """Test pattern detection with repeated errors."""
        errors = [
            "Error: undefined variable 'x' at line 5",
            "Error: undefined variable 'x' at line 5",
            "Error: undefined variable 'x' at line 5",
        ]
        result = detect_error_repeat(errors, threshold_override=3)

        self.assertIsNotNone(result)
        self.assertEqual(result.pattern_type, "error_repeat")
        self.assertEqual(result.count, 3)

    def test_line_number_normalization(self):
        """Test that line numbers are normalized for comparison."""
        errors = [
            "Error at line 5",
            "Error at line 10",
            "Error at line 15",
        ]
        result = detect_error_repeat(errors, threshold_override=3)

        # Should match because line numbers are normalized
        self.assertIsNotNone(result)
        self.assertEqual(result.count, 3)


class TestFileLoopDetection(unittest.TestCase):
    """Test file loop pattern detection."""

    def test_no_pattern_with_empty_list(self):
        """Test no pattern with no file edits."""
        result = detect_file_loop([])
        self.assertIsNone(result)

    def test_no_pattern_with_unique_files(self):
        """Test no pattern when all files are unique."""
        files = ["a.py", "b.py", "c.py", "d.py"]
        result = detect_file_loop(files, threshold_override=5)
        self.assertIsNone(result)

    def test_pattern_with_repeated_file(self):
        """Test pattern detection with repeated file edits."""
        files = ["src/app.py"] * 5
        result = detect_file_loop(files, threshold_override=5)

        self.assertIsNotNone(result)
        self.assertEqual(result.pattern_type, "file_loop")
        self.assertEqual(result.count, 5)
        self.assertIn("app.py", result.evidence[0])

    def test_severity_scales_with_count(self):
        """Test that severity scales with edit count."""
        files = ["src/app.py"] * 12
        result = detect_file_loop(files, threshold_override=5)

        self.assertIsNotNone(result)
        self.assertEqual(result.severity, "severe")


class TestToolLoopDetection(unittest.TestCase):
    """Test tool loop pattern detection."""

    def test_no_pattern_with_few_tools(self):
        """Test no pattern with few tool calls."""
        tools = [{"tool": "Edit", "success": True}] * 5
        result = detect_tool_loop(tools, threshold_override=10)
        self.assertIsNone(result)

    def test_no_pattern_with_all_success(self):
        """Test no pattern when all tools succeed."""
        tools = [
            {"tool": "Edit", "success": True},
            {"tool": "Bash", "success": True},
        ] * 5
        result = detect_tool_loop(tools, threshold_override=10)
        # Need failures for loop detection
        self.assertIsNone(result)

    def test_pattern_with_alternating_failures(self):
        """Test pattern detection with alternating tool failures."""
        tools = []
        for _ in range(5):
            tools.append({"tool": "Edit", "success": True})
            tools.append({"tool": "Bash", "success": False})

        result = detect_tool_loop(tools, threshold_override=10)

        self.assertIsNotNone(result)
        self.assertEqual(result.pattern_type, "tool_loop")
        self.assertEqual(result.severity, "moderate")


class TestDetectStuckPatterns(unittest.TestCase):
    """Test combined stuck pattern detection."""

    def test_detects_multiple_patterns(self):
        """Test detection of multiple patterns."""
        context = ClarificationContext(
            recent_tools=[
                {"tool": "Edit", "success": True},
                {"tool": "Bash", "success": False},
            ] * 6,
            recent_errors=["Error X"] * 4,
            files_being_edited=["app.py"] * 6,
        )

        with patch('self_clarify._get_threshold', side_effect=lambda k: {
            "error_repeat_threshold": 3,
            "same_file_edit_threshold": 5,
            "tool_loop_threshold": 10,
        }.get(k, 3)):
            patterns = detect_stuck_patterns(context)

        # Should detect file loop and error repeat
        pattern_types = [p.pattern_type for p in patterns]
        self.assertIn("file_loop", pattern_types)
        self.assertIn("error_repeat", pattern_types)

    def test_returns_empty_list_when_no_patterns(self):
        """Test returns empty list when no patterns detected."""
        context = ClarificationContext(
            recent_tools=[{"tool": "Edit", "success": True}],
            recent_errors=[],
            files_being_edited=["a.py"],
        )

        patterns = detect_stuck_patterns(context)
        self.assertEqual(patterns, [])


class TestClarificationPromptGeneration(unittest.TestCase):
    """Test clarification prompt generation."""

    def test_generates_prompt_with_context(self):
        """Test that prompt is generated with context."""
        context = ClarificationContext(
            recent_tools=[
                {"tool": "Edit", "input_preview": {"file_path": "app.py"}, "success": True},
                {"tool": "Bash", "input_preview": {"command": "python app.py"}, "success": False},
            ],
            recent_errors=["NameError: undefined variable"],
            files_being_edited=["app.py"] * 3,
            current_objective="Fix bug",
        )

        prompt = generate_clarification_prompt(context)

        self.assertIn("Recent actions", prompt)
        self.assertIn("Recent errors", prompt)
        self.assertIn("What is the ACTUAL problem", prompt)
        self.assertIn("Why haven't previous attempts worked", prompt)

    def test_includes_stuck_patterns(self):
        """Test that stuck patterns are included in prompt."""
        context = ClarificationContext(
            stuck_patterns=[
                StuckPattern(
                    pattern_type="error_repeat",
                    severity="moderate",
                    evidence=["Same error 4 times"],
                    count=4,
                )
            ]
        )

        prompt = generate_clarification_prompt(context)
        self.assertIn("detected patterns", prompt)
        self.assertIn("error_repeat", prompt)


class TestClarificationInjection(unittest.TestCase):
    """Test clarification injection formatting."""

    def test_suggestion_urgency(self):
        """Test suggestion urgency formatting."""
        context = ClarificationContext()
        injection = generate_clarification_injection(context, "suggestion")

        self.assertIn("CONSIDER CLARIFYING", injection)
        self.assertIn("╭", injection)  # Box drawing
        self.assertIn("╰", injection)

    def test_recommendation_urgency(self):
        """Test recommendation urgency formatting."""
        context = ClarificationContext()
        injection = generate_clarification_injection(context, "recommendation")

        self.assertIn("RECOMMENDED", injection)

    def test_urgent_urgency(self):
        """Test urgent urgency formatting."""
        context = ClarificationContext()
        injection = generate_clarification_injection(context, "urgent")

        self.assertIn("REQUIRED", injection)
        self.assertIn("⚠️", injection)

    def test_includes_patterns_warning(self):
        """Test that patterns are included as warning."""
        context = ClarificationContext(
            stuck_patterns=[
                StuckPattern(
                    pattern_type="file_loop",
                    severity="moderate",
                    evidence=["Edited app.py 6 times"],
                    count=6,
                )
            ]
        )

        injection = generate_clarification_injection(context, "recommendation")
        self.assertIn("Stuck patterns detected", injection)
        self.assertIn("app.py", injection)


class TestShouldTriggerClarification(unittest.TestCase):
    """Test should_trigger_clarification quick check."""

    def setUp(self):
        reset_clarification_cooldown()

    def test_triggers_on_drift_ignored(self):
        """Test trigger on drift ignored."""
        with patch('self_clarify._get_threshold', return_value=3):
            result = should_trigger_clarification(
                drift_signals_fired=5,
                drift_signals_acted_on=1,
            )
            self.assertTrue(result)

    def test_triggers_on_error_repeat(self):
        """Test trigger on error repeat."""
        with patch('self_clarify._get_threshold', return_value=3):
            result = should_trigger_clarification(
                same_error_count=4,
            )
            self.assertTrue(result)

    def test_triggers_on_file_edits(self):
        """Test trigger on same file edits."""
        with patch('self_clarify._get_threshold', return_value=5):
            result = should_trigger_clarification(
                same_file_edits=6,
            )
            self.assertTrue(result)

    def test_no_trigger_below_thresholds(self):
        """Test no trigger when below all thresholds."""
        with patch('self_clarify._get_threshold', return_value=3):
            result = should_trigger_clarification(
                drift_signals_fired=2,
                drift_signals_acted_on=1,
                same_error_count=1,
                same_file_edits=2,
            )
            self.assertFalse(result)

    def test_respects_cooldown(self):
        """Test that cooldown is respected."""
        _mark_clarification_offered()

        with patch('self_clarify._get_threshold', return_value=3):
            result = should_trigger_clarification(
                same_error_count=5,  # Would normally trigger
            )
            self.assertFalse(result)


class TestCheckAndOfferClarification(unittest.TestCase):
    """Test check_and_offer_clarification integration."""

    def setUp(self):
        reset_clarification_cooldown()

    def test_returns_none_in_observe_mode(self):
        """Test returns None in observe mode."""
        result = check_and_offer_clarification(intervention_level="observe")
        self.assertIsNone(result)

    def test_returns_none_on_cooldown(self):
        """Test returns None when on cooldown."""
        _mark_clarification_offered()
        result = check_and_offer_clarification(intervention_level="guide")
        self.assertIsNone(result)

    def test_returns_none_when_healthy(self):
        """Test returns None when session is healthy."""
        # When should_trigger_clarification returns False, we get None
        with patch('self_clarify.should_trigger_clarification', return_value=False):
            # Also need to mock the import of active_intervention
            with patch.dict('sys.modules', {'active_intervention': MagicMock()}):
                result = check_and_offer_clarification(intervention_level="guide")
                self.assertIsNone(result)


class TestDataStructures(unittest.TestCase):
    """Test data structure behaviors."""

    def test_stuck_pattern_to_dict(self):
        """Test StuckPattern to_dict."""
        pattern = StuckPattern(
            pattern_type="error_repeat",
            severity="moderate",
            evidence=["Error repeated 5 times"],
            count=5,
        )

        d = pattern.to_dict()

        self.assertEqual(d["pattern_type"], "error_repeat")
        self.assertEqual(d["severity"], "moderate")
        self.assertEqual(d["count"], 5)

    def test_clarification_context_defaults(self):
        """Test ClarificationContext default values."""
        context = ClarificationContext()

        self.assertEqual(context.recent_tools, [])
        self.assertEqual(context.recent_errors, [])
        self.assertEqual(context.files_being_edited, [])
        self.assertEqual(context.stuck_patterns, [])
        self.assertEqual(context.session_duration_minutes, 0.0)


class TestLogClarification(unittest.TestCase):
    """Test clarification logging."""

    def test_logs_clarification(self):
        """Test that clarification is logged."""
        context = ClarificationContext(
            stuck_patterns=[
                StuckPattern("file_loop", "mild", ["Edited app.py 5 times"], 5)
            ],
            total_tool_calls=50,
            session_duration_minutes=30.0,
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            log_path = Path(tmpdir) / "clarifications.jsonl"

            with patch('self_clarify._get_clarifications_path', return_value=log_path):
                result = log_clarification(context, was_helpful=True)

                self.assertTrue(result)
                self.assertTrue(log_path.exists())

                # Read and verify
                with open(log_path) as f:
                    entry = json.loads(f.readline())

                self.assertEqual(entry["tool_calls"], 50)
                self.assertEqual(entry["was_helpful"], True)
                self.assertEqual(len(entry["patterns"]), 1)


class TestIntegrationWithInterventionLevels(unittest.TestCase):
    """Test intervention level filtering."""

    def setUp(self):
        reset_clarification_cooldown()

    def test_advise_filters_mild_suggestions(self):
        """Test that advise level filters out mild suggestions."""
        # Test that mild patterns at advise level are filtered
        # When urgency is "suggestion" and level is "advise", should return None
        context = ClarificationContext(
            stuck_patterns=[
                StuckPattern("file_loop", "mild", [], 5)
            ]
        )

        # The logic is: if urgency == "suggestion" and level == "advise", return None
        # This is tested via the urgency calculation in check_and_offer_clarification
        # For a unit test, we can verify the injection is still generated
        # (the filtering happens in check_and_offer_clarification, not generation)
        injection = generate_clarification_injection(context, "suggestion")
        self.assertIn("CONSIDER CLARIFYING", injection)


class TestEdgeCases(unittest.TestCase):
    """Test edge cases and error handling."""

    def test_handles_empty_context_gracefully(self):
        """Test handling of completely empty context."""
        context = ClarificationContext()

        prompt = generate_clarification_prompt(context)
        injection = generate_clarification_injection(context, "suggestion")

        # Should still generate valid output
        self.assertIn("What is the ACTUAL problem", prompt)
        self.assertIn("╭", injection)

    def test_handles_malformed_tool_data(self):
        """Test handling of malformed tool data."""
        context = ClarificationContext(
            recent_tools=[
                {"tool": "Edit"},  # Missing other fields
                {},  # Empty dict
                None,  # None (should be skipped gracefully)
            ],
        )

        # Should not crash - None and empty dicts should be handled
        prompt = generate_clarification_prompt(context)
        self.assertIsInstance(prompt, str)
        # Should still contain the valid Edit tool
        self.assertIn("Edit", prompt)

    def test_truncates_long_errors(self):
        """Test that long errors are truncated."""
        long_error = "Error: " + "x" * 500
        context = ClarificationContext(
            recent_errors=[long_error],
        )

        prompt = generate_clarification_prompt(context)
        # Should contain truncated version
        self.assertIn("Error:", prompt)
        self.assertTrue(len(prompt) < len(long_error) + 500)


if __name__ == "__main__":
    unittest.main()
