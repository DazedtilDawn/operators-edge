#!/usr/bin/env python3
"""
Unit tests for smart_suggestions.py (Phase 6)
"""
import json
import os
import sys
import tempfile
import unittest
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import patch, MagicMock
from dataclasses import dataclass

# Add hooks directory to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from smart_suggestions import (
    # Data structures
    Suggestion,
    SuggestionContext,
    # Suggestion tracking
    _can_show_suggestion,
    _mark_suggestion_shown,
    reset_suggestion_history,
    # Suggestion generators
    suggest_auto_fix,
    suggest_related_files,
    suggest_checkpoint,
    suggest_drift_prevention,
    suggest_pattern_nudge,
    # Main interface
    generate_suggestions,
    format_suggestions,
    build_suggestion_context,
    get_suggestions_for_tool,
    # Constants
    FILE_CHURN_THRESHOLD,
    CONTEXT_CHECKPOINT_THRESHOLD,
    SUGGESTION_COOLDOWN,
)


# =============================================================================
# MOCK OBJECTS
# =============================================================================

@dataclass
class MockKnownFix:
    """Mock KnownFix for testing."""
    error_signature: str = "ImportError: module not found"
    error_type: str = "import_error"
    fix_description: str = "Add __init__.py to the directory"
    fix_commands: list = None
    fix_files: list = None
    confidence: float = 0.8
    times_used: int = 3

    def __post_init__(self):
        if self.fix_commands is None:
            self.fix_commands = ["touch utils/__init__.py"]
        if self.fix_files is None:
            self.fix_files = ["utils/__init__.py"]


@dataclass
class MockRelatedFile:
    """Mock RelatedFile for testing."""
    file_path: str
    relation_type: str = "cochange"
    strength: float = 0.6
    reason: str = "Changed together in session"


@dataclass
class MockDriftSignal:
    """Mock DriftSignal for testing."""
    signal_type: str
    severity: str
    message: str
    evidence: dict = None
    suggestion: str = "Consider a different approach"

    def __post_init__(self):
        if self.evidence is None:
            self.evidence = {}


# =============================================================================
# TEST CLASSES
# =============================================================================

class TestSuggestionDataStructures(unittest.TestCase):
    """Tests for Suggestion dataclass."""

    def test_suggestion_creation(self):
        """Test creating a suggestion."""
        suggestion = Suggestion(
            suggestion_type="auto_fix",
            severity="action",
            title="Test Title",
            message="Test message",
            action_prompt="Apply fix?",
            metadata={"key": "value"}
        )
        self.assertEqual(suggestion.suggestion_type, "auto_fix")
        self.assertEqual(suggestion.severity, "action")
        self.assertEqual(suggestion.title, "Test Title")

    def test_suggestion_to_dict(self):
        """Test serialization to dict."""
        suggestion = Suggestion(
            suggestion_type="checkpoint",
            severity="warning",
            title="Context High",
            message="Context at 80%",
            metadata={"usage": 80}
        )
        d = suggestion.to_dict()
        self.assertEqual(d["suggestion_type"], "checkpoint")
        self.assertEqual(d["severity"], "warning")
        self.assertEqual(d["metadata"]["usage"], 80)


class TestSuggestionTracking(unittest.TestCase):
    """Tests for suggestion history tracking."""

    def setUp(self):
        reset_suggestion_history()

    def test_can_show_suggestion_first_time(self):
        """Test that suggestions can be shown the first time."""
        self.assertTrue(_can_show_suggestion("test_type"))
        self.assertTrue(_can_show_suggestion("test_type", "key"))

    def test_cannot_show_suggestion_after_marking(self):
        """Test that suggestions are blocked after being shown."""
        _mark_suggestion_shown("test_type", "key")
        self.assertFalse(_can_show_suggestion("test_type", "key"))

    def test_can_show_after_cooldown(self):
        """Test that suggestions can be shown after cooldown."""
        import smart_suggestions
        _mark_suggestion_shown("test_type", "key")

        # Manually adjust the history to simulate time passing
        full_key = "test_type:key"
        smart_suggestions._suggestion_history[full_key] = (
            datetime.now() - timedelta(seconds=SUGGESTION_COOLDOWN + 10)
        )

        self.assertTrue(_can_show_suggestion("test_type", "key"))

    def test_reset_history(self):
        """Test resetting suggestion history."""
        _mark_suggestion_shown("test_type")
        self.assertFalse(_can_show_suggestion("test_type"))

        reset_suggestion_history()
        self.assertTrue(_can_show_suggestion("test_type"))


class TestSuggestAutoFix(unittest.TestCase):
    """Tests for auto-fix suggestions."""

    def setUp(self):
        reset_suggestion_history()

    def test_no_suggestion_for_non_bash(self):
        """Test no suggestion for non-Bash tools."""
        ctx = SuggestionContext(
            tool_name="Edit",
            tool_input={},
            session_state={},
            known_fix=MockKnownFix()
        )
        self.assertIsNone(suggest_auto_fix(ctx))

    def test_no_suggestion_without_known_fix(self):
        """Test no suggestion without a known fix."""
        ctx = SuggestionContext(
            tool_name="Bash",
            tool_input={"command": "pytest"},
            session_state={},
            known_fix=None
        )
        self.assertIsNone(suggest_auto_fix(ctx))

    def test_no_suggestion_for_low_confidence(self):
        """Test no suggestion for low confidence fixes."""
        ctx = SuggestionContext(
            tool_name="Bash",
            tool_input={"command": "pytest"},
            session_state={},
            known_fix=MockKnownFix(confidence=0.4)
        )
        self.assertIsNone(suggest_auto_fix(ctx))

    def test_suggestion_for_high_confidence_fix(self):
        """Test suggestion generated for high confidence fix."""
        ctx = SuggestionContext(
            tool_name="Bash",
            tool_input={"command": "pytest"},
            session_state={},
            known_fix=MockKnownFix(confidence=0.8)
        )
        suggestion = suggest_auto_fix(ctx)
        self.assertIsNotNone(suggestion)
        self.assertEqual(suggestion.suggestion_type, "auto_fix")
        self.assertEqual(suggestion.severity, "action")
        self.assertIn("Known Fix", suggestion.title)
        self.assertIn("__init__.py", suggestion.message)

    def test_cooldown_prevents_repeat_suggestion(self):
        """Test that cooldown prevents repeat suggestions."""
        ctx = SuggestionContext(
            tool_name="Bash",
            tool_input={"command": "pytest"},
            session_state={},
            known_fix=MockKnownFix()
        )
        # First suggestion
        suggestion1 = suggest_auto_fix(ctx)
        self.assertIsNotNone(suggestion1)

        # Second suggestion (same error) should be blocked
        suggestion2 = suggest_auto_fix(ctx)
        self.assertIsNone(suggestion2)


class TestSuggestRelatedFiles(unittest.TestCase):
    """Tests for related files suggestions."""

    def setUp(self):
        reset_suggestion_history()

    def test_no_suggestion_for_non_edit_tools(self):
        """Test no suggestion for non-edit tools."""
        ctx = SuggestionContext(
            tool_name="Bash",
            tool_input={"command": "pytest"},
            session_state={},
            related_files=[MockRelatedFile(file_path="/app/billing.py")]
        )
        self.assertIsNone(suggest_related_files(ctx))

    def test_no_suggestion_without_related_files(self):
        """Test no suggestion without related files."""
        ctx = SuggestionContext(
            tool_name="Edit",
            tool_input={"file_path": "/app/auth.py"},
            session_state={},
            related_files=[]
        )
        self.assertIsNone(suggest_related_files(ctx))

    def test_no_suggestion_for_weak_relations(self):
        """Test no suggestion for weak relations."""
        ctx = SuggestionContext(
            tool_name="Edit",
            tool_input={"file_path": "/app/auth.py"},
            session_state={},
            related_files=[MockRelatedFile(file_path="/app/billing.py", strength=0.3)]
        )
        self.assertIsNone(suggest_related_files(ctx))

    def test_suggestion_for_strong_relations(self):
        """Test suggestion generated for strong relations."""
        ctx = SuggestionContext(
            tool_name="Edit",
            tool_input={"file_path": "/app/auth.py"},
            session_state={},
            related_files=[
                MockRelatedFile(file_path="/app/billing.py", strength=0.7),
                MockRelatedFile(file_path="/app/user.py", strength=0.6),
            ]
        )
        suggestion = suggest_related_files(ctx)
        self.assertIsNotNone(suggestion)
        self.assertEqual(suggestion.suggestion_type, "related_file")
        self.assertEqual(suggestion.severity, "info")
        self.assertIn("billing.py", suggestion.message)
        self.assertIn("70%", suggestion.message)


class TestSuggestCheckpoint(unittest.TestCase):
    """Tests for checkpoint suggestions."""

    def setUp(self):
        reset_suggestion_history()

    def test_no_suggestion_for_low_usage(self):
        """Test no suggestion for low context usage."""
        ctx = SuggestionContext(
            tool_name="Bash",
            tool_input={},
            session_state={},
            context_usage_percent=50.0
        )
        self.assertIsNone(suggest_checkpoint(ctx))

    def test_suggestion_at_threshold(self):
        """Test suggestion at checkpoint threshold."""
        ctx = SuggestionContext(
            tool_name="Bash",
            tool_input={},
            session_state={},
            context_usage_percent=76.0
        )
        suggestion = suggest_checkpoint(ctx)
        self.assertIsNotNone(suggestion)
        self.assertEqual(suggestion.suggestion_type, "checkpoint")
        self.assertEqual(suggestion.severity, "info")
        self.assertIn("76%", suggestion.message)

    def test_critical_suggestion_at_high_usage(self):
        """Test critical suggestion at high usage."""
        ctx = SuggestionContext(
            tool_name="Bash",
            tool_input={},
            session_state={},
            context_usage_percent=92.0
        )
        suggestion = suggest_checkpoint(ctx)
        self.assertIsNotNone(suggestion)
        self.assertEqual(suggestion.severity, "warning")
        self.assertIn("Critical", suggestion.title)


class TestSuggestDriftPrevention(unittest.TestCase):
    """Tests for drift prevention suggestions."""

    def setUp(self):
        reset_suggestion_history()

    def test_file_churn_warning(self):
        """Test warning for file churn."""
        ctx = SuggestionContext(
            tool_name="Edit",
            tool_input={"file_path": "/app/utils.py"},
            session_state={},
            file_edit_counts={"/app/utils.py": 4}
        )
        suggestion = suggest_drift_prevention(ctx)
        self.assertIsNotNone(suggestion)
        self.assertEqual(suggestion.suggestion_type, "drift_warning")
        self.assertIn("4 times", suggestion.message)

    def test_no_warning_below_threshold(self):
        """Test no warning below churn threshold."""
        ctx = SuggestionContext(
            tool_name="Edit",
            tool_input={"file_path": "/app/utils.py"},
            session_state={},
            file_edit_counts={"/app/utils.py": 2}
        )
        self.assertIsNone(suggest_drift_prevention(ctx))

    def test_critical_drift_signal_warning(self):
        """Test warning for critical drift signals."""
        ctx = SuggestionContext(
            tool_name="Bash",
            tool_input={},
            session_state={},
            drift_signals=[
                MockDriftSignal(
                    signal_type="COMMAND_REPEAT",
                    severity="critical",
                    message="Command failed 3 times"
                )
            ]
        )
        suggestion = suggest_drift_prevention(ctx)
        self.assertIsNotNone(suggestion)
        self.assertIn("COMMAND_REPEAT", suggestion.title)


class TestSuggestPatternNudge(unittest.TestCase):
    """Tests for pattern nudge suggestions."""

    def setUp(self):
        reset_suggestion_history()

    def test_test_file_nudge(self):
        """Test nudge for test files."""
        ctx = SuggestionContext(
            tool_name="Edit",
            tool_input={"file_path": "/app/test_utils.py"},
            session_state={},
        )
        suggestion = suggest_pattern_nudge(ctx)
        self.assertIsNotNone(suggestion)
        self.assertEqual(suggestion.suggestion_type, "pattern")
        self.assertIn("run tests", suggestion.message)

    def test_package_json_nudge(self):
        """Test nudge for package.json."""
        ctx = SuggestionContext(
            tool_name="Edit",
            tool_input={"file_path": "/app/package.json"},
            session_state={},
        )
        suggestion = suggest_pattern_nudge(ctx)
        self.assertIsNotNone(suggestion)
        self.assertIn("npm install", suggestion.message)

    def test_requirements_txt_nudge(self):
        """Test nudge for requirements.txt."""
        ctx = SuggestionContext(
            tool_name="Edit",
            tool_input={"file_path": "/app/requirements.txt"},
            session_state={},
        )
        suggestion = suggest_pattern_nudge(ctx)
        self.assertIsNotNone(suggestion)
        self.assertIn("pip install", suggestion.message)

    def test_no_nudge_for_regular_file(self):
        """Test no nudge for regular files."""
        ctx = SuggestionContext(
            tool_name="Edit",
            tool_input={"file_path": "/app/utils.py"},
            session_state={},
        )
        self.assertIsNone(suggest_pattern_nudge(ctx))


class TestGenerateSuggestions(unittest.TestCase):
    """Tests for the main generate_suggestions function."""

    def setUp(self):
        reset_suggestion_history()

    def test_empty_context_no_suggestions(self):
        """Test that empty context generates no suggestions."""
        ctx = SuggestionContext(
            tool_name="Read",
            tool_input={},
            session_state={}
        )
        suggestions = generate_suggestions(ctx)
        self.assertEqual(len(suggestions), 0)

    def test_multiple_suggestions_generated(self):
        """Test that multiple suggestions can be generated."""
        ctx = SuggestionContext(
            tool_name="Edit",
            tool_input={"file_path": "/app/test_utils.py"},
            session_state={},
            file_edit_counts={"/app/test_utils.py": 5},
            context_usage_percent=80.0
        )
        suggestions = generate_suggestions(ctx)
        self.assertGreater(len(suggestions), 1)

    def test_suggestions_sorted_by_severity(self):
        """Test that suggestions are sorted by severity."""
        ctx = SuggestionContext(
            tool_name="Edit",
            tool_input={"file_path": "/app/test_utils.py"},
            session_state={},
            file_edit_counts={"/app/test_utils.py": 5},
            context_usage_percent=95.0  # Critical
        )
        suggestions = generate_suggestions(ctx)

        if len(suggestions) >= 2:
            # Warning should come before info
            severities = [s.severity for s in suggestions]
            warning_idx = severities.index("warning") if "warning" in severities else len(severities)
            info_idx = severities.index("info") if "info" in severities else len(severities)
            self.assertLessEqual(warning_idx, info_idx)


class TestFormatSuggestions(unittest.TestCase):
    """Tests for suggestion formatting."""

    def test_empty_suggestions_returns_empty_string(self):
        """Test empty suggestions return empty string."""
        result = format_suggestions([])
        self.assertEqual(result, "")

    def test_single_suggestion_formatted(self):
        """Test single suggestion is formatted correctly."""
        suggestions = [
            Suggestion(
                suggestion_type="checkpoint",
                severity="warning",
                title="Context High",
                message="Context at 80%"
            )
        ]
        result = format_suggestions(suggestions)
        self.assertIn("SMART SUGGESTIONS", result)
        self.assertIn("Context High", result)
        self.assertIn("80%", result)

    def test_action_prompt_included(self):
        """Test action prompt is included."""
        suggestions = [
            Suggestion(
                suggestion_type="auto_fix",
                severity="action",
                title="Known Fix",
                message="Fix available",
                action_prompt="Apply this fix?"
            )
        ]
        result = format_suggestions(suggestions)
        self.assertIn("Apply this fix?", result)

    def test_max_display_limit(self):
        """Test that max_display limit is respected."""
        suggestions = [
            Suggestion(suggestion_type=f"type_{i}", severity="info", title=f"Title {i}", message=f"Message {i}")
            for i in range(5)
        ]
        result = format_suggestions(suggestions, max_display=2)
        self.assertIn("Title 0", result)
        self.assertIn("Title 1", result)
        self.assertNotIn("Title 2", result)
        self.assertIn("3 more suggestions", result)


class TestBuildSuggestionContext(unittest.TestCase):
    """Tests for building suggestion context."""

    def test_basic_context_building(self):
        """Test basic context building."""
        ctx = build_suggestion_context(
            tool_name="Edit",
            tool_input={"file_path": "/app/test.py"},
            state={"objective": "Test objective"}
        )
        self.assertEqual(ctx.tool_name, "Edit")
        self.assertEqual(ctx.tool_input["file_path"], "/app/test.py")
        self.assertEqual(ctx.session_state["objective"], "Test objective")


class TestGetSuggestionsForTool(unittest.TestCase):
    """Tests for the main get_suggestions_for_tool entry point."""

    def setUp(self):
        reset_suggestion_history()

    def test_returns_empty_string_for_no_suggestions(self):
        """Test returns empty string when no suggestions."""
        result = get_suggestions_for_tool(
            tool_name="Read",
            tool_input={"file_path": "/app/test.py"},
            state={}
        )
        self.assertEqual(result, "")

    def test_returns_formatted_suggestions(self):
        """Test returns formatted suggestions when applicable."""
        result = get_suggestions_for_tool(
            tool_name="Edit",
            tool_input={"file_path": "/app/test_utils.py"},
            state={},
            known_fix=MockKnownFix()
        )
        # May or may not have suggestions depending on context
        # Just verify it doesn't crash and returns a string
        self.assertIsInstance(result, str)


if __name__ == '__main__':
    unittest.main()
