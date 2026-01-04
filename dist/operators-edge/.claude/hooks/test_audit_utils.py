#!/usr/bin/env python3
"""
Tests for audit_utils.py - Lesson audit functionality (v3.6)
"""

import unittest
from unittest.mock import patch, MagicMock
from pathlib import Path
from datetime import datetime


class TestInferAuditPattern(unittest.TestCase):
    """Tests for infer_audit_pattern() function."""

    def test_returns_none_for_non_code_lesson(self):
        """Non-code related lessons should not get audit patterns."""
        from audit_utils import infer_audit_pattern

        result = infer_audit_pattern(
            "Memory is taste, not storage",
            "memory"
        )
        self.assertIsNone(result)

    def test_detects_os_path_anti_pattern(self):
        """Should detect os.path usage anti-pattern."""
        from audit_utils import infer_audit_pattern

        result = infer_audit_pattern(
            "pathlib.Path handles cross-platform paths correctly, use instead of os.path",
            "paths"
        )
        self.assertIsNotNone(result)
        self.assertIn("os", result.lower())

    def test_detects_relative_import_anti_pattern(self):
        """Should detect relative import anti-pattern."""
        from audit_utils import infer_audit_pattern

        result = infer_audit_pattern(
            "Absolute imports work better, avoid relative import",
            "imports"
        )
        self.assertIsNotNone(result)

    def test_extracts_instead_of_pattern(self):
        """Should extract pattern from 'instead of X' phrase."""
        from audit_utils import infer_audit_pattern

        result = infer_audit_pattern(
            "Use requests instead of urllib",
            "python"
        )
        self.assertIsNotNone(result)
        self.assertIn("urllib", result)

    def test_extracts_dont_use_pattern(self):
        """Should extract pattern from \"don't use X\" phrase."""
        from audit_utils import infer_audit_pattern

        result = infer_audit_pattern(
            "Don't use eval() in production code",
            "security python"
        )
        self.assertIsNotNone(result)

    def test_returns_none_for_meta_lessons(self):
        """Meta-lessons about process should not get audit patterns."""
        from audit_utils import infer_audit_pattern

        result = infer_audit_pattern(
            "Capture lessons at resolution moment, not at scoring",
            "lesson capture"
        )
        self.assertIsNone(result)

    def test_known_anti_patterns_detected(self):
        """Known anti-patterns should be detected."""
        from audit_utils import infer_audit_pattern

        # bare except
        result = infer_audit_pattern(
            "Never use bare except clauses",
            "python"
        )
        self.assertIsNotNone(result)

    def test_quoted_pattern_extraction(self):
        """Should extract patterns from quoted code references."""
        from audit_utils import infer_audit_pattern

        result = infer_audit_pattern(
            "Avoid using 'os.path.join' directly",
            "paths python"
        )
        self.assertIsNotNone(result)


class TestInferAuditScope(unittest.TestCase):
    """Tests for infer_audit_scope() function."""

    def test_python_keywords_return_py_scope(self):
        """Python-related keywords should return *.py scope."""
        from audit_utils import infer_audit_scope

        result = infer_audit_scope(
            "Use pathlib instead of os.path",
            "python paths"
        )
        self.assertIn("*.py", result)

    def test_javascript_keywords_return_js_scope(self):
        """JavaScript-related keywords should return JS scopes."""
        from audit_utils import infer_audit_scope

        result = infer_audit_scope(
            "Use const instead of var in JavaScript",
            "javascript"
        )
        self.assertTrue(any(ext in result for ext in ["*.js", "*.ts"]))

    def test_bash_keywords_return_sh_scope(self):
        """Bash-related keywords should return *.sh scope."""
        from audit_utils import infer_audit_scope

        result = infer_audit_scope(
            "Always quote variables in bash scripts",
            "bash shell"
        )
        self.assertIn("*.sh", result)

    def test_yaml_keywords_return_yaml_scope(self):
        """YAML-related keywords should return yaml scopes."""
        from audit_utils import infer_audit_scope

        result = infer_audit_scope(
            "Use consistent indentation in yaml files",
            "config yaml"
        )
        self.assertTrue(any(ext in result for ext in ["*.yaml", "*.yml"]))

    def test_defaults_to_python_for_code_lessons(self):
        """Code-related lessons without specific language default to Python."""
        from audit_utils import infer_audit_scope

        result = infer_audit_scope(
            "Use meaningful variable names",
            "naming convention"
        )
        # Should default to Python since it's code-related
        self.assertEqual(result, ["*.py"])

    def test_returns_empty_for_non_code_lessons(self):
        """Non-code lessons should return empty scope."""
        from audit_utils import infer_audit_scope

        result = infer_audit_scope(
            "Always document decisions",
            "process documentation"
        )
        # Not code-related, so empty
        self.assertEqual(result, [])


class TestScanForViolations(unittest.TestCase):
    """Tests for scan_for_violations() function."""

    @patch('audit_utils.get_project_dir')
    def test_finds_pattern_matches(self, mock_get_project):
        """Should find files matching the pattern."""
        from audit_utils import scan_for_violations

        # Create a temp directory structure
        with patch('audit_utils._get_files_to_scan') as mock_files:
            mock_file = MagicMock()
            mock_file.read_text.return_value = "import os\nos.path.join('a', 'b')\n"
            mock_file.relative_to.return_value = Path("test.py")
            mock_files.return_value = [mock_file]

            violations = scan_for_violations(
                r"os\.path",
                scope=["*.py"],
                project_dir=Path("/fake")
            )

            self.assertGreater(len(violations), 0)

    @patch('audit_utils.get_project_dir')
    def test_returns_empty_for_invalid_pattern(self, mock_get_project):
        """Invalid regex patterns should return empty list."""
        from audit_utils import scan_for_violations

        mock_get_project.return_value = Path("/fake")

        violations = scan_for_violations(
            r"[invalid regex",  # Unclosed bracket
            scope=["*.py"],
            project_dir=Path("/fake")
        )

        self.assertEqual(violations, [])

    @patch('audit_utils.get_project_dir')
    def test_respects_max_results(self, mock_get_project):
        """Should limit results to max_results."""
        from audit_utils import scan_for_violations

        with patch('audit_utils._get_files_to_scan') as mock_files:
            mock_file = MagicMock()
            # Create content with many matches
            mock_file.read_text.return_value = "\n".join(["os.path"] * 20)
            mock_file.relative_to.return_value = Path("test.py")
            mock_files.return_value = [mock_file]

            violations = scan_for_violations(
                r"os\.path",
                scope=["*.py"],
                project_dir=Path("/fake"),
                max_results=5
            )

            self.assertLessEqual(len(violations), 5)


class TestAuditLesson(unittest.TestCase):
    """Tests for audit_lesson() function."""

    def test_returns_not_audited_when_no_pattern(self):
        """Lessons without audit_pattern should return not audited."""
        from audit_utils import audit_lesson

        lesson = {
            "trigger": "memory",
            "lesson": "Memory is taste, not storage",
            "reinforced": 2
        }

        result = audit_lesson(lesson)

        self.assertFalse(result["audited"])
        self.assertEqual(result["reason"], "no_pattern")

    @patch('audit_utils.scan_for_violations')
    def test_returns_violations_when_pattern_exists(self, mock_scan):
        """Lessons with audit_pattern should be scanned."""
        from audit_utils import audit_lesson

        mock_scan.return_value = [
            {"location": "test.py:10", "line": "os.path.join()", "match": "os.path"}
        ]

        lesson = {
            "trigger": "paths",
            "lesson": "Use pathlib instead of os.path",
            "audit_pattern": r"os\.path",
            "audit_scope": ["*.py"],
            "reinforced": 3
        }

        result = audit_lesson(lesson)

        self.assertTrue(result["audited"])
        self.assertEqual(result["violation_count"], 1)
        self.assertEqual(len(result["violations"]), 1)

    @patch('audit_utils.scan_for_violations')
    def test_includes_timestamp(self, mock_scan):
        """Audit result should include timestamp."""
        from audit_utils import audit_lesson

        mock_scan.return_value = []

        lesson = {
            "trigger": "paths",
            "lesson": "Use pathlib",
            "audit_pattern": r"os\.path",
            "reinforced": 1
        }

        result = audit_lesson(lesson)

        self.assertIn("timestamp", result)


class TestAuditAllLessons(unittest.TestCase):
    """Tests for audit_all_lessons() function."""

    @patch('audit_utils.audit_lesson')
    def test_filters_to_auditable_lessons(self, mock_audit):
        """Should only audit lessons with patterns."""
        from audit_utils import audit_all_lessons

        mock_audit.return_value = {"audited": True, "violations": []}

        lessons = [
            {"trigger": "a", "lesson": "A", "audit_pattern": "pattern_a"},
            {"trigger": "b", "lesson": "B"},  # No pattern
            {"trigger": "c", "lesson": "C", "audit_pattern": "pattern_c"},
        ]

        audit_all_lessons(lessons)

        # Should only call audit_lesson for lessons with patterns
        self.assertEqual(mock_audit.call_count, 2)

    @patch('audit_utils.audit_lesson')
    def test_prioritizes_high_reinforced_lessons(self, mock_audit):
        """Should audit high-reinforced lessons first."""
        from audit_utils import audit_all_lessons

        call_order = []

        def track_calls(lesson, project_dir=None):
            call_order.append(lesson["trigger"])
            return {"audited": True, "violations": []}

        mock_audit.side_effect = track_calls

        lessons = [
            {"trigger": "low", "lesson": "Low", "audit_pattern": "x", "reinforced": 1},
            {"trigger": "high", "lesson": "High", "audit_pattern": "y", "reinforced": 5},
            {"trigger": "mid", "lesson": "Mid", "audit_pattern": "z", "reinforced": 3},
        ]

        audit_all_lessons(lessons)

        # Should be called in order: high (5), mid (3), low (1)
        self.assertEqual(call_order, ["high", "mid", "low"])

    @patch('audit_utils.audit_lesson')
    def test_limits_violations_per_lesson(self, mock_audit):
        """Should cap violations per lesson."""
        from audit_utils import audit_all_lessons

        mock_audit.return_value = {
            "audited": True,
            "violations": [{"location": f"file{i}.py:1"} for i in range(10)],
            "trigger": "test"
        }

        lessons = [
            {"trigger": "test", "lesson": "Test", "audit_pattern": "x", "reinforced": 1}
        ]

        findings = audit_all_lessons(lessons, max_per_lesson=3)

        self.assertLessEqual(len(findings), 3)


class TestUpdateLessonAuditStats(unittest.TestCase):
    """Tests for update_lesson_audit_stats() function."""

    def test_updates_last_audit(self):
        """Should update last_audit timestamp."""
        from audit_utils import update_lesson_audit_stats

        lesson = {"trigger": "test", "lesson": "Test"}
        audit_result = {
            "audited": True,
            "timestamp": "2025-01-01T12:00:00",
            "violation_count": 2
        }

        update_lesson_audit_stats(lesson, audit_result)

        self.assertEqual(lesson["last_audit"], "2025-01-01T12:00:00")
        self.assertEqual(lesson["violations_found"], 2)

    def test_no_update_when_not_audited(self):
        """Should not update when not audited."""
        from audit_utils import update_lesson_audit_stats

        lesson = {"trigger": "test", "lesson": "Test"}
        audit_result = {"audited": False, "reason": "no_pattern"}

        update_lesson_audit_stats(lesson, audit_result)

        self.assertNotIn("last_audit", lesson)
        self.assertNotIn("violations_found", lesson)


class TestGetAuditableLessons(unittest.TestCase):
    """Tests for get_auditable_lessons() function."""

    def test_filters_lessons_with_patterns(self):
        """Should return only lessons with audit_pattern."""
        from audit_utils import get_auditable_lessons

        lessons = [
            {"trigger": "a", "lesson": "A", "audit_pattern": "x"},
            {"trigger": "b", "lesson": "B"},
            {"trigger": "c", "lesson": "C", "audit_pattern": "y"},
        ]

        result = get_auditable_lessons(lessons)

        self.assertEqual(len(result), 2)
        self.assertTrue(all(l.get("audit_pattern") for l in result))


class TestGetLessonsNeedingAudit(unittest.TestCase):
    """Tests for get_lessons_needing_audit() function."""

    def test_returns_lessons_without_last_audit(self):
        """Lessons without last_audit need auditing."""
        from audit_utils import get_lessons_needing_audit

        # Use a very recent date that won't be past threshold
        recent_date = datetime.now().isoformat()
        lessons = [
            {"trigger": "a", "lesson": "A", "audit_pattern": "x"},
            {"trigger": "b", "lesson": "B", "audit_pattern": "y", "last_audit": recent_date}
        ]

        result = get_lessons_needing_audit(lessons)

        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["trigger"], "a")

    def test_returns_lessons_past_threshold(self):
        """Lessons past the threshold need auditing."""
        from audit_utils import get_lessons_needing_audit

        old_date = "2020-01-01T00:00:00"  # Very old
        lessons = [
            {"trigger": "old", "lesson": "Old", "audit_pattern": "x", "last_audit": old_date}
        ]

        result = get_lessons_needing_audit(lessons, days_threshold=7)

        self.assertEqual(len(result), 1)

    def test_excludes_recently_audited(self):
        """Recently audited lessons should not be returned."""
        from audit_utils import get_lessons_needing_audit

        recent_date = datetime.now().isoformat()
        lessons = [
            {"trigger": "recent", "lesson": "Recent", "audit_pattern": "x", "last_audit": recent_date}
        ]

        result = get_lessons_needing_audit(lessons, days_threshold=7)

        self.assertEqual(len(result), 0)


class TestGetFilesToScan(unittest.TestCase):
    """Tests for _get_files_to_scan() helper."""

    @patch('os.walk')
    def test_filters_by_scope(self, mock_walk):
        """Should filter files by scope patterns."""
        from audit_utils import _get_files_to_scan

        mock_walk.return_value = [
            ("/fake", [], ["test.py", "test.js", "readme.md"])
        ]

        files = _get_files_to_scan(Path("/fake"), scope=["*.py"])

        # Should only include .py files
        py_files = [f for f in files if f.suffix == ".py"]
        self.assertEqual(len(py_files), len(files))

    @patch('os.walk')
    def test_skips_excluded_directories(self, mock_walk):
        """Should skip directories in SKIP_DIRECTORIES."""
        from audit_utils import _get_files_to_scan

        # The walk will be modified in-place to exclude dirs
        mock_walk.return_value = [
            ("/fake", ["node_modules", "src"], ["test.py"]),
            ("/fake/src", [], ["app.py"])
        ]

        files = _get_files_to_scan(Path("/fake"))

        # node_modules should be filtered out
        self.assertFalse(any("node_modules" in str(f) for f in files))


class TestScanFile(unittest.TestCase):
    """Tests for _scan_file() helper."""

    def test_finds_matches_with_line_numbers(self):
        """Should return matches with correct line numbers."""
        from audit_utils import _scan_file
        import re

        mock_file = MagicMock()
        mock_file.read_text.return_value = "line1\nos.path.join\nline3\nos.path.exists\n"
        mock_file.relative_to.return_value = Path("test.py")

        regex = re.compile(r"os\.path")

        violations = _scan_file(mock_file, regex, Path("/fake"))

        self.assertEqual(len(violations), 2)
        self.assertIn(":2", violations[0]["location"])
        self.assertIn(":4", violations[1]["location"])

    def test_handles_unreadable_files(self):
        """Should handle files that can't be read."""
        from audit_utils import _scan_file
        import re

        mock_file = MagicMock()
        mock_file.read_text.side_effect = IOError("Permission denied")

        regex = re.compile(r"test")

        violations = _scan_file(mock_file, regex, Path("/fake"))

        self.assertEqual(violations, [])


if __name__ == "__main__":
    unittest.main()
