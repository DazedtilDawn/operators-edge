#!/usr/bin/env python3
"""
Tests for smart_read.py - Phase 10.2 Smart Read Suggestions

Tests cover:
- Line count detection
- Severity determination
- File-type specific suggestions
- Formatting at different intervention levels
"""
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch, MagicMock

# Add hooks directory to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from smart_read import (
    get_file_line_count,
    get_file_extension,
    get_suggestions_for_file,
    determine_severity,
    should_suggest_smart_read,
    generate_smart_read_suggestion,
    format_smart_read_suggestion,
    format_compact_suggestion,
    check_read_and_suggest,
    SmartReadSuggestion,
    LINE_THRESHOLD_SUGGEST,
    LINE_THRESHOLD_WARN,
    LINE_THRESHOLD_CRITICAL,
)


class TestGetFileLineCount(unittest.TestCase):
    """Tests for get_file_line_count()."""

    def test_counts_lines_correctly(self):
        """Should count lines in a file."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False) as f:
            f.write("line1\nline2\nline3\n")
            f.flush()
            try:
                count = get_file_line_count(f.name)
                self.assertEqual(count, 3)
            finally:
                os.unlink(f.name)

    def test_handles_empty_file(self):
        """Should return 0 for empty file."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False) as f:
            f.flush()
            try:
                count = get_file_line_count(f.name)
                self.assertEqual(count, 0)
            finally:
                os.unlink(f.name)

    def test_handles_nonexistent_file(self):
        """Should return None for nonexistent file."""
        count = get_file_line_count("/nonexistent/path/file.txt")
        self.assertIsNone(count)

    def test_handles_directory(self):
        """Should return None for directory."""
        count = get_file_line_count("/tmp")
        self.assertIsNone(count)


class TestGetFileExtension(unittest.TestCase):
    """Tests for get_file_extension()."""

    def test_extracts_python_extension(self):
        """Should extract .py extension."""
        ext = get_file_extension("/path/to/file.py")
        self.assertEqual(ext, ".py")

    def test_lowercase_extension(self):
        """Should return lowercase extension."""
        ext = get_file_extension("/path/to/FILE.PY")
        self.assertEqual(ext, ".py")

    def test_handles_multiple_dots(self):
        """Should handle files with multiple dots."""
        ext = get_file_extension("/path/to/file.test.py")
        self.assertEqual(ext, ".py")

    def test_handles_no_extension(self):
        """Should return empty for no extension."""
        ext = get_file_extension("/path/to/Makefile")
        self.assertEqual(ext, "")


class TestGetSuggestionsForFile(unittest.TestCase):
    """Tests for get_suggestions_for_file()."""

    def test_python_file_suggestions(self):
        """Should return Python-specific suggestions for .py files."""
        suggestions = get_suggestions_for_file("/path/to/module.py")
        self.assertTrue(len(suggestions) > 0)
        # Should include grep for functions/classes
        self.assertTrue(any("def" in s or "class" in s for s in suggestions))

    def test_json_file_suggestions(self):
        """Should return JSON-specific suggestions for .json files."""
        suggestions = get_suggestions_for_file("/path/to/config.json")
        self.assertTrue(len(suggestions) > 0)
        # Should include head or keys inspection
        self.assertTrue(any("head" in s or "keys" in s for s in suggestions))

    def test_log_file_suggestions(self):
        """Should return log-specific suggestions for .log files."""
        suggestions = get_suggestions_for_file("/path/to/app.log")
        self.assertTrue(len(suggestions) > 0)
        # Should include tail for recent entries
        self.assertTrue(any("tail" in s for s in suggestions))

    def test_unknown_extension_gets_generic(self):
        """Should return generic suggestions for unknown extensions."""
        suggestions = get_suggestions_for_file("/path/to/file.xyz")
        self.assertTrue(len(suggestions) > 0)
        # Should include head/tail
        self.assertTrue(any("head" in s or "tail" in s for s in suggestions))

    def test_suggestions_include_file_path(self):
        """Suggestions should include the file path."""
        suggestions = get_suggestions_for_file("/path/to/test.py")
        self.assertTrue(any("/path/to/test.py" in s for s in suggestions))


class TestDetermineSeverity(unittest.TestCase):
    """Tests for determine_severity()."""

    def test_below_threshold_is_none(self):
        """Lines below threshold should return 'none'."""
        severity = determine_severity(100)
        self.assertEqual(severity, "none")

    def test_suggest_threshold(self):
        """Lines at suggest threshold should return 'info'."""
        severity = determine_severity(LINE_THRESHOLD_SUGGEST)
        self.assertEqual(severity, "info")

    def test_warn_threshold(self):
        """Lines at warn threshold should return 'warning'."""
        severity = determine_severity(LINE_THRESHOLD_WARN)
        self.assertEqual(severity, "warning")

    def test_critical_threshold(self):
        """Lines at critical threshold should return 'critical'."""
        severity = determine_severity(LINE_THRESHOLD_CRITICAL)
        self.assertEqual(severity, "critical")

    def test_above_critical(self):
        """Lines above critical should still return 'critical'."""
        severity = determine_severity(LINE_THRESHOLD_CRITICAL + 10000)
        self.assertEqual(severity, "critical")


class TestShouldSuggestSmartRead(unittest.TestCase):
    """Tests for should_suggest_smart_read()."""

    def test_small_file_no_suggestion(self):
        """Small file should not trigger suggestion."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False) as f:
            f.write("small file\n")
            f.flush()
            try:
                should, count = should_suggest_smart_read(f.name)
                self.assertFalse(should)
                self.assertEqual(count, 1)
            finally:
                os.unlink(f.name)

    def test_large_file_triggers_suggestion(self):
        """Large file should trigger suggestion."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False) as f:
            # Write enough lines to exceed threshold
            for i in range(LINE_THRESHOLD_SUGGEST + 10):
                f.write(f"line {i}\n")
            f.flush()
            try:
                should, count = should_suggest_smart_read(f.name)
                self.assertTrue(should)
                self.assertGreater(count, LINE_THRESHOLD_SUGGEST)
            finally:
                os.unlink(f.name)

    def test_nonexistent_file_no_suggestion(self):
        """Nonexistent file should not trigger suggestion."""
        should, count = should_suggest_smart_read("/nonexistent/file.txt")
        self.assertFalse(should)
        self.assertIsNone(count)


class TestGenerateSmartReadSuggestion(unittest.TestCase):
    """Tests for generate_smart_read_suggestion()."""

    def test_small_file_returns_none(self):
        """Small file should return None."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False) as f:
            f.write("# small\n")
            f.flush()
            try:
                suggestion = generate_smart_read_suggestion(f.name)
                self.assertIsNone(suggestion)
            finally:
                os.unlink(f.name)

    def test_large_file_returns_suggestion(self):
        """Large file should return SmartReadSuggestion."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False) as f:
            for i in range(LINE_THRESHOLD_SUGGEST + 100):
                f.write(f"# line {i}\n")
            f.flush()
            try:
                suggestion = generate_smart_read_suggestion(f.name)
                self.assertIsNotNone(suggestion)
                self.assertIsInstance(suggestion, SmartReadSuggestion)
                self.assertEqual(suggestion.file_path, f.name)
                self.assertGreater(suggestion.line_count, LINE_THRESHOLD_SUGGEST)
            finally:
                os.unlink(f.name)

    def test_suggestion_has_correct_severity(self):
        """Suggestion should have severity based on line count."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False) as f:
            for i in range(LINE_THRESHOLD_CRITICAL + 100):
                f.write(f"# line {i}\n")
            f.flush()
            try:
                suggestion = generate_smart_read_suggestion(f.name)
                self.assertEqual(suggestion.severity, "critical")
            finally:
                os.unlink(f.name)


class TestFormatSmartReadSuggestion(unittest.TestCase):
    """Tests for format_smart_read_suggestion()."""

    def setUp(self):
        """Create a mock suggestion for testing."""
        self.mock_suggestion = SmartReadSuggestion(
            file_path="/project/src/large.py",
            line_count=3000,
            severity="warning",
            suggestions=[
                'grep -n "def " "/project/src/large.py"',
                'head -100 "/project/src/large.py"',
            ],
            message="📄 large.py has 3,000 lines"
        )

    def test_observe_returns_empty(self):
        """Observe level should return empty string."""
        result = format_smart_read_suggestion(self.mock_suggestion, "observe")
        self.assertEqual(result, "")

    def test_advise_includes_suggestion(self):
        """Advise level should include SUGGESTION header for warning severity."""
        result = format_smart_read_suggestion(self.mock_suggestion, "advise")
        # Warning severity at advise level shows SUGGESTION
        self.assertIn("SUGGESTION", result)

    def test_guide_includes_suggestion(self):
        """Guide level should include SUGGESTION header."""
        result = format_smart_read_suggestion(self.mock_suggestion, "guide")
        self.assertIn("SUGGESTION", result)

    def test_intervene_includes_recommended(self):
        """Intervene level should include RECOMMENDED header."""
        result = format_smart_read_suggestion(self.mock_suggestion, "intervene")
        self.assertIn("RECOMMENDED", result)

    def test_critical_severity_escalates(self):
        """Critical severity should show RECOMMENDED even at advise level."""
        critical = SmartReadSuggestion(
            file_path="/project/huge.py",
            line_count=10000,
            severity="critical",
            suggestions=["head -100"],
            message="LARGE FILE"
        )
        result = format_smart_read_suggestion(critical, "advise")
        self.assertIn("RECOMMENDED", result)

    def test_includes_suggestions(self):
        """Output should include the suggestions."""
        result = format_smart_read_suggestion(self.mock_suggestion, "guide")
        self.assertIn("grep", result)
        self.assertIn("head", result)

    def test_includes_context_estimate(self):
        """Output should include context estimate."""
        result = format_smart_read_suggestion(self.mock_suggestion, "guide")
        self.assertIn("context", result.lower())


class TestFormatCompactSuggestion(unittest.TestCase):
    """Tests for format_compact_suggestion()."""

    def test_compact_format(self):
        """Compact format should be one line with key info."""
        suggestion = SmartReadSuggestion(
            file_path="/project/src/module.py",
            line_count=2500,
            severity="warning",
            suggestions=[],
            message=""
        )
        result = format_compact_suggestion(suggestion)
        self.assertIn("module.py", result)
        self.assertIn("2,500", result)
        self.assertIn("head", result)


class TestCheckReadAndSuggest(unittest.TestCase):
    """Tests for check_read_and_suggest() integration function."""

    def test_small_file_returns_none(self):
        """Small file should return None."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False) as f:
            f.write("# small\n")
            f.flush()
            try:
                result = check_read_and_suggest(f.name)
                self.assertIsNone(result)
            finally:
                os.unlink(f.name)

    def test_large_file_returns_suggestion(self):
        """Large file should return formatted suggestion."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False) as f:
            for i in range(LINE_THRESHOLD_SUGGEST + 100):
                f.write(f"# line {i}\n")
            f.flush()
            try:
                result = check_read_and_suggest(f.name, "guide")
                self.assertIsNotNone(result)
                self.assertIn("SUGGESTION", result)
            finally:
                os.unlink(f.name)

    def test_respects_intervention_level(self):
        """Should respect intervention level parameter."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False) as f:
            for i in range(LINE_THRESHOLD_SUGGEST + 100):
                f.write(f"# line {i}\n")
            f.flush()
            try:
                result = check_read_and_suggest(f.name, "observe")
                self.assertEqual(result, "")
            finally:
                os.unlink(f.name)


class TestFileTypeSpecificSuggestions(unittest.TestCase):
    """Tests for file-type specific suggestions."""

    def test_typescript_suggestions(self):
        """TypeScript files should get TS-specific suggestions."""
        suggestions = get_suggestions_for_file("/app/component.tsx")
        combined = " ".join(suggestions)
        self.assertTrue("interface" in combined or "function" in combined)

    def test_go_suggestions(self):
        """Go files should get Go-specific suggestions."""
        suggestions = get_suggestions_for_file("/app/main.go")
        combined = " ".join(suggestions)
        self.assertTrue("func" in combined or "type" in combined)

    def test_sql_suggestions(self):
        """SQL files should get SQL-specific suggestions."""
        suggestions = get_suggestions_for_file("/db/schema.sql")
        combined = " ".join(suggestions)
        self.assertTrue("CREATE" in combined or "TABLE" in combined)

    def test_shell_suggestions(self):
        """Shell scripts should get shell-specific suggestions."""
        suggestions = get_suggestions_for_file("/scripts/deploy.sh")
        combined = " ".join(suggestions)
        self.assertTrue("function" in combined or "head" in combined)


if __name__ == "__main__":
    unittest.main()
