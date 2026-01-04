#!/usr/bin/env python3
"""
Tests for brainstorm_utils.py - project scanning for improvement opportunities.

Tests the core functions for:
- Code marker scanning (TODO, FIXME, etc.)
- Large file detection
- Archive pattern analysis
- State pattern analysis
- Challenge generation
- Full scan runner
- Result formatting
"""
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch, MagicMock

# Add hooks directory to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


class TestScanCodeMarkers(unittest.TestCase):
    """Tests for scan_code_markers() function."""

    @patch('brainstorm_utils.SCAN_PATTERNS', {
        'code_extensions': ['.py'],
        'skip_dirs': ['node_modules', '__pycache__'],
        'code_markers': ['TODO', 'FIXME']
    })
    @patch('brainstorm_utils.COMPLEXITY_THRESHOLDS', {'max_files_to_scan': 100})
    def test_finds_todo_markers(self):
        """scan_code_markers() should find TODO markers."""
        from brainstorm_utils import scan_code_markers

        with tempfile.TemporaryDirectory() as tmpdir:
            test_file = Path(tmpdir) / "test.py"
            test_file.write_text("# TODO: Fix this bug\ndef foo(): pass")

            findings = scan_code_markers(Path(tmpdir))

            self.assertEqual(len(findings), 1)
            self.assertEqual(findings[0]["marker"], "TODO")
            self.assertIn("Fix this bug", findings[0]["text"])

    @patch('brainstorm_utils.SCAN_PATTERNS', {
        'code_extensions': ['.py'],
        'skip_dirs': ['node_modules', '__pycache__'],
        'code_markers': ['TODO', 'FIXME']
    })
    @patch('brainstorm_utils.COMPLEXITY_THRESHOLDS', {'max_files_to_scan': 100})
    def test_fixme_has_high_priority(self):
        """scan_code_markers() should mark FIXME as high priority."""
        from brainstorm_utils import scan_code_markers

        with tempfile.TemporaryDirectory() as tmpdir:
            test_file = Path(tmpdir) / "test.py"
            test_file.write_text("# FIXME: Critical issue")

            findings = scan_code_markers(Path(tmpdir))

            self.assertEqual(len(findings), 1)
            self.assertEqual(findings[0]["priority"], "high")

    @patch('brainstorm_utils.SCAN_PATTERNS', {
        'code_extensions': ['.py'],
        'skip_dirs': ['skip_me'],
        'code_markers': ['TODO']
    })
    @patch('brainstorm_utils.COMPLEXITY_THRESHOLDS', {'max_files_to_scan': 100})
    def test_skips_excluded_dirs(self):
        """scan_code_markers() should skip excluded directories."""
        from brainstorm_utils import scan_code_markers

        with tempfile.TemporaryDirectory() as tmpdir:
            # Create file in excluded directory
            skip_dir = Path(tmpdir) / "skip_me"
            skip_dir.mkdir()
            skip_file = skip_dir / "test.py"
            skip_file.write_text("# TODO: Should not find this")

            findings = scan_code_markers(Path(tmpdir))

            self.assertEqual(len(findings), 0)

    @patch('brainstorm_utils.SCAN_PATTERNS', {
        'code_extensions': ['.py'],
        'skip_dirs': [],
        'code_markers': ['TODO']
    })
    @patch('brainstorm_utils.COMPLEXITY_THRESHOLDS', {'max_files_to_scan': 100})
    def test_truncates_long_text(self):
        """scan_code_markers() should truncate long lines."""
        from brainstorm_utils import scan_code_markers

        with tempfile.TemporaryDirectory() as tmpdir:
            test_file = Path(tmpdir) / "test.py"
            long_line = "# TODO: " + "x" * 200
            test_file.write_text(long_line)

            findings = scan_code_markers(Path(tmpdir))

            self.assertEqual(len(findings), 1)
            self.assertTrue(findings[0]["text"].endswith("..."))
            self.assertLessEqual(len(findings[0]["text"]), 103)  # 100 + "..."

    @patch('brainstorm_utils.SCAN_PATTERNS', {
        'code_extensions': ['.py'],
        'skip_dirs': [],
        'code_markers': ['TODO']
    })
    @patch('brainstorm_utils.COMPLEXITY_THRESHOLDS', {'max_files_to_scan': 1})
    def test_respects_max_files_limit(self):
        """scan_code_markers() should stop at max_files_to_scan."""
        from brainstorm_utils import scan_code_markers

        with tempfile.TemporaryDirectory() as tmpdir:
            # Create multiple files
            for i in range(5):
                test_file = Path(tmpdir) / f"test{i}.py"
                test_file.write_text(f"# TODO: Item {i}")

            findings = scan_code_markers(Path(tmpdir))

            # Should only scan 1 file due to limit
            self.assertLessEqual(len(findings), 1)


class TestScanLargeFiles(unittest.TestCase):
    """Tests for scan_large_files() function."""

    @patch('brainstorm_utils.SCAN_PATTERNS', {
        'code_extensions': ['.py'],
        'skip_dirs': []
    })
    @patch('brainstorm_utils.COMPLEXITY_THRESHOLDS', {
        'max_files_to_scan': 100,
        'large_file_lines': 10,
        'very_large_file_lines': 20
    })
    def test_finds_large_files(self):
        """scan_large_files() should find files exceeding threshold."""
        from brainstorm_utils import scan_large_files

        with tempfile.TemporaryDirectory() as tmpdir:
            # Create a file with 15 lines (above large, below very large)
            test_file = Path(tmpdir) / "test.py"
            test_file.write_text("\n".join(["line"] * 15))

            findings = scan_large_files(Path(tmpdir))

            self.assertEqual(len(findings), 1)
            self.assertEqual(findings[0]["priority"], "medium")
            self.assertEqual(findings[0]["lines"], 15)

    @patch('brainstorm_utils.SCAN_PATTERNS', {
        'code_extensions': ['.py'],
        'skip_dirs': []
    })
    @patch('brainstorm_utils.COMPLEXITY_THRESHOLDS', {
        'max_files_to_scan': 100,
        'large_file_lines': 10,
        'very_large_file_lines': 20
    })
    def test_very_large_has_high_priority(self):
        """scan_large_files() should mark very large files as high priority."""
        from brainstorm_utils import scan_large_files

        with tempfile.TemporaryDirectory() as tmpdir:
            test_file = Path(tmpdir) / "test.py"
            test_file.write_text("\n".join(["line"] * 25))

            findings = scan_large_files(Path(tmpdir))

            self.assertEqual(len(findings), 1)
            self.assertEqual(findings[0]["priority"], "high")

    @patch('brainstorm_utils.SCAN_PATTERNS', {
        'code_extensions': ['.py'],
        'skip_dirs': []
    })
    @patch('brainstorm_utils.COMPLEXITY_THRESHOLDS', {
        'max_files_to_scan': 100,
        'large_file_lines': 100,
        'very_large_file_lines': 200
    })
    def test_ignores_small_files(self):
        """scan_large_files() should not report small files."""
        from brainstorm_utils import scan_large_files

        with tempfile.TemporaryDirectory() as tmpdir:
            test_file = Path(tmpdir) / "test.py"
            test_file.write_text("# Small file\n")

            findings = scan_large_files(Path(tmpdir))

            self.assertEqual(len(findings), 0)

    @patch('brainstorm_utils.SCAN_PATTERNS', {
        'code_extensions': ['.py'],
        'skip_dirs': []
    })
    @patch('brainstorm_utils.COMPLEXITY_THRESHOLDS', {
        'max_files_to_scan': 100,
        'large_file_lines': 5,
        'very_large_file_lines': 10
    })
    def test_sorts_by_size_descending(self):
        """scan_large_files() should sort results by line count descending."""
        from brainstorm_utils import scan_large_files

        with tempfile.TemporaryDirectory() as tmpdir:
            # Create files of different sizes
            (Path(tmpdir) / "small.py").write_text("\n".join(["x"] * 7))
            (Path(tmpdir) / "large.py").write_text("\n".join(["x"] * 15))
            (Path(tmpdir) / "medium.py").write_text("\n".join(["x"] * 10))

            findings = scan_large_files(Path(tmpdir))

            self.assertGreaterEqual(len(findings), 2)
            self.assertGreater(findings[0]["lines"], findings[1]["lines"])


class TestScanArchivePatterns(unittest.TestCase):
    """Tests for scan_archive_patterns() function."""

    def test_returns_empty_for_missing_archive(self):
        """scan_archive_patterns() should return empty if no archive."""
        from brainstorm_utils import scan_archive_patterns

        with tempfile.TemporaryDirectory() as tmpdir:
            findings = scan_archive_patterns(Path(tmpdir))
            self.assertEqual(findings, [])

    def test_finds_recurring_mismatches(self):
        """scan_archive_patterns() should find recurring mismatch causes."""
        from brainstorm_utils import scan_archive_patterns

        with tempfile.TemporaryDirectory() as tmpdir:
            proof_dir = Path(tmpdir) / ".proof"
            proof_dir.mkdir()

            archive = proof_dir / "archive.jsonl"
            entries = [
                {"type": "resolved_mismatch", "delta": "API timeout"},
                {"type": "resolved_mismatch", "delta": "API timeout"},
                {"type": "resolved_mismatch", "delta": "Parse error"}
            ]
            archive.write_text("\n".join(json.dumps(e) for e in entries))

            findings = scan_archive_patterns(Path(tmpdir))

            # Should find "API timeout" as recurring (2+ times)
            self.assertEqual(len(findings), 1)
            self.assertEqual(findings[0]["cause"], "API timeout")
            self.assertEqual(findings[0]["count"], 2)

    def test_high_priority_for_frequent_patterns(self):
        """scan_archive_patterns() should mark frequent patterns as high priority."""
        from brainstorm_utils import scan_archive_patterns

        with tempfile.TemporaryDirectory() as tmpdir:
            proof_dir = Path(tmpdir) / ".proof"
            proof_dir.mkdir()

            archive = proof_dir / "archive.jsonl"
            entries = [{"type": "resolved_mismatch", "delta": "Same issue"}] * 4
            archive.write_text("\n".join(json.dumps(e) for e in entries))

            findings = scan_archive_patterns(Path(tmpdir))

            self.assertEqual(len(findings), 1)
            self.assertEqual(findings[0]["priority"], "high")

    def test_handles_invalid_json(self):
        """scan_archive_patterns() should handle invalid JSON lines."""
        from brainstorm_utils import scan_archive_patterns

        with tempfile.TemporaryDirectory() as tmpdir:
            proof_dir = Path(tmpdir) / ".proof"
            proof_dir.mkdir()

            archive = proof_dir / "archive.jsonl"
            archive.write_text("invalid json\n{\"type\": \"test\"}")

            # Should not raise
            findings = scan_archive_patterns(Path(tmpdir))
            self.assertIsInstance(findings, list)


class TestScanStatePatterns(unittest.TestCase):
    """Tests for scan_state_patterns() function."""

    def test_returns_empty_for_no_state(self):
        """scan_state_patterns() should return empty for None state."""
        from brainstorm_utils import scan_state_patterns

        findings = scan_state_patterns(None)
        self.assertEqual(findings, [])

    def test_detects_multiple_unresolved_mismatches(self):
        """scan_state_patterns() should detect multiple unresolved mismatches."""
        from brainstorm_utils import scan_state_patterns

        state = {
            "mismatches": [
                {"id": 1, "resolved": False},
                {"id": 2, "resolved": False},
                {"id": 3, "resolved": True}
            ]
        }

        findings = scan_state_patterns(state)

        self.assertTrue(any(f["pattern"] == "multiple_unresolved_mismatches" for f in findings))

    def test_detects_blocked_steps(self):
        """scan_state_patterns() should detect blocked steps."""
        from brainstorm_utils import scan_state_patterns

        state = {
            "plan": [
                {"status": "completed"},
                {"status": "blocked"},
                {"status": "pending"}
            ]
        }

        findings = scan_state_patterns(state)

        blocked_finding = next((f for f in findings if f["pattern"] == "blocked_steps"), None)
        self.assertIsNotNone(blocked_finding)
        self.assertEqual(blocked_finding["priority"], "high")

    def test_detects_pending_research(self):
        """scan_state_patterns() should detect pending research."""
        from brainstorm_utils import scan_state_patterns

        state = {
            "research": [
                {"status": "pending"},
                {"status": "pending"},
                {"status": "completed"}
            ]
        }

        findings = scan_state_patterns(state)

        self.assertTrue(any(f["pattern"] == "pending_research" for f in findings))

    def test_detects_unreinforced_lessons(self):
        """scan_state_patterns() should detect unreinforced lessons."""
        from brainstorm_utils import scan_state_patterns

        state = {
            "memory": [
                {"lesson": "a", "reinforced": 0},
                {"lesson": "b", "reinforced": 0},
                {"lesson": "c", "reinforced": 0},
                {"lesson": "d", "reinforced": 2}
            ]
        }

        findings = scan_state_patterns(state)

        self.assertTrue(any(f["pattern"] == "unreinforced_lessons" for f in findings))


class TestGenerateSuggestedChallenges(unittest.TestCase):
    """Tests for generate_suggested_challenges() function."""

    def test_generates_challenge_for_code_markers(self):
        """generate_suggested_challenges() should generate challenge for many markers."""
        from brainstorm_utils import generate_suggested_challenges

        findings = {
            "code_markers": [
                {"file": "a.py"},
                {"file": "b.py"},
                {"file": "c.py"}
            ],
            "large_files": [],
            "archive_patterns": [],
            "state_patterns": []
        }

        challenges = generate_suggested_challenges(findings)

        self.assertTrue(any("technical debt" in c.lower() for c in challenges))

    def test_generates_challenge_for_large_files(self):
        """generate_suggested_challenges() should generate challenge for large files."""
        from brainstorm_utils import generate_suggested_challenges

        findings = {
            "code_markers": [],
            "large_files": [{"file": "huge.py", "lines": 1000}],
            "archive_patterns": [],
            "state_patterns": []
        }

        challenges = generate_suggested_challenges(findings)

        self.assertTrue(any("organization" in c.lower() or "huge.py" in c for c in challenges))

    def test_generates_challenge_for_recurring_mismatches(self):
        """generate_suggested_challenges() should generate challenge for mismatches."""
        from brainstorm_utils import generate_suggested_challenges

        findings = {
            "code_markers": [],
            "large_files": [],
            "archive_patterns": [
                {"pattern": "recurring_mismatch", "cause": "timeout errors"}
            ],
            "state_patterns": []
        }

        challenges = generate_suggested_challenges(findings)

        self.assertTrue(any("timeout errors" in c for c in challenges))

    def test_adds_generic_challenges_if_needed(self):
        """generate_suggested_challenges() should add generic challenges if few specific ones."""
        from brainstorm_utils import generate_suggested_challenges

        findings = {
            "code_markers": [],
            "large_files": [],
            "archive_patterns": [],
            "state_patterns": []
        }

        challenges = generate_suggested_challenges(findings)

        self.assertGreaterEqual(len(challenges), 3)

    def test_limits_to_five_challenges(self):
        """generate_suggested_challenges() should return at most 5 challenges."""
        from brainstorm_utils import generate_suggested_challenges

        findings = {
            "code_markers": [{"file": f"{i}.py"} for i in range(10)],
            "large_files": [{"file": "big.py", "lines": 500}],
            "archive_patterns": [
                {"pattern": "recurring_mismatch", "cause": f"error{i}"}
                for i in range(5)
            ],
            "state_patterns": [
                {"pattern": "multiple_unresolved_mismatches"},
                {"pattern": "blocked_steps"},
                {"pattern": "pending_research"}
            ]
        }

        challenges = generate_suggested_challenges(findings)

        self.assertLessEqual(len(challenges), 5)


class TestRunBrainstormScan(unittest.TestCase):
    """Tests for run_brainstorm_scan() function."""

    @patch('brainstorm_utils.scan_code_markers')
    @patch('brainstorm_utils.scan_large_files')
    @patch('brainstorm_utils.scan_archive_patterns')
    @patch('brainstorm_utils.scan_state_patterns')
    @patch('brainstorm_utils.generate_suggested_challenges')
    @patch('brainstorm_utils.load_yaml_state')
    def test_runs_all_scans(self, mock_state, mock_challenges, mock_state_pat,
                            mock_archive, mock_large, mock_markers):
        """run_brainstorm_scan() should run all scan functions."""
        from brainstorm_utils import run_brainstorm_scan

        mock_state.return_value = {}
        mock_markers.return_value = []
        mock_large.return_value = []
        mock_archive.return_value = []
        mock_state_pat.return_value = []
        mock_challenges.return_value = []

        with tempfile.TemporaryDirectory() as tmpdir:
            findings = run_brainstorm_scan(Path(tmpdir))

        mock_markers.assert_called_once()
        mock_large.assert_called_once()
        mock_archive.assert_called_once()
        mock_state_pat.assert_called_once()

    @patch('brainstorm_utils.scan_code_markers')
    @patch('brainstorm_utils.scan_large_files')
    @patch('brainstorm_utils.scan_archive_patterns')
    @patch('brainstorm_utils.scan_state_patterns')
    @patch('brainstorm_utils.generate_suggested_challenges')
    @patch('brainstorm_utils.load_yaml_state')
    def test_includes_summary(self, mock_state, mock_challenges, mock_state_pat,
                               mock_archive, mock_large, mock_markers):
        """run_brainstorm_scan() should include summary stats."""
        from brainstorm_utils import run_brainstorm_scan

        mock_state.return_value = {}
        mock_markers.return_value = [{"marker": "TODO"}]
        mock_large.return_value = []
        mock_archive.return_value = []
        mock_state_pat.return_value = []
        mock_challenges.return_value = ["Challenge 1"]

        with tempfile.TemporaryDirectory() as tmpdir:
            findings = run_brainstorm_scan(Path(tmpdir))

        self.assertIn("summary", findings)
        self.assertEqual(findings["summary"]["code_markers_found"], 1)
        self.assertEqual(findings["summary"]["challenges_generated"], 1)

    @patch('brainstorm_utils.scan_code_markers')
    @patch('brainstorm_utils.scan_large_files')
    @patch('brainstorm_utils.scan_archive_patterns')
    @patch('brainstorm_utils.scan_state_patterns')
    @patch('brainstorm_utils.generate_suggested_challenges')
    @patch('brainstorm_utils.load_yaml_state')
    def test_includes_timestamp(self, mock_state, mock_challenges, mock_state_pat,
                                 mock_archive, mock_large, mock_markers):
        """run_brainstorm_scan() should include timestamp."""
        from brainstorm_utils import run_brainstorm_scan

        mock_state.return_value = {}
        mock_markers.return_value = []
        mock_large.return_value = []
        mock_archive.return_value = []
        mock_state_pat.return_value = []
        mock_challenges.return_value = []

        with tempfile.TemporaryDirectory() as tmpdir:
            findings = run_brainstorm_scan(Path(tmpdir))

        self.assertIn("timestamp", findings)


class TestFormatScanResults(unittest.TestCase):
    """Tests for format_scan_results() function."""

    def test_formats_header(self):
        """format_scan_results() should include header."""
        from brainstorm_utils import format_scan_results

        findings = {
            "timestamp": "2025-01-01T12:00:00",
            "code_markers": [],
            "large_files": [],
            "archive_patterns": [],
            "state_patterns": [],
            "suggested_challenges": []
        }

        result = format_scan_results(findings)

        self.assertIn("PROJECT IMPROVEMENT SCAN", result)
        self.assertIn("2025-01-01", result)

    def test_formats_code_markers(self):
        """format_scan_results() should format code markers."""
        from brainstorm_utils import format_scan_results

        findings = {
            "timestamp": "2025-01-01T12:00:00",
            "code_markers": [
                {"marker": "TODO", "file": "test.py", "line": 10, "text": "Fix bug"}
            ],
            "large_files": [],
            "archive_patterns": [],
            "state_patterns": [],
            "suggested_challenges": []
        }

        result = format_scan_results(findings)

        self.assertIn("[TODO]", result)
        self.assertIn("test.py:10", result)

    def test_formats_large_files(self):
        """format_scan_results() should format large files."""
        from brainstorm_utils import format_scan_results

        findings = {
            "timestamp": "2025-01-01T12:00:00",
            "code_markers": [],
            "large_files": [
                {"file": "big.py", "lines": 500, "priority": "high"}
            ],
            "archive_patterns": [],
            "state_patterns": [],
            "suggested_challenges": []
        }

        result = format_scan_results(findings)

        self.assertIn("big.py", result)
        self.assertIn("500 lines", result)

    def test_formats_challenges(self):
        """format_scan_results() should format challenges."""
        from brainstorm_utils import format_scan_results

        findings = {
            "timestamp": "2025-01-01T12:00:00",
            "code_markers": [],
            "large_files": [],
            "archive_patterns": [],
            "state_patterns": [],
            "suggested_challenges": [
                "How might we improve testing?"
            ]
        }

        result = format_scan_results(findings)

        self.assertIn("SUGGESTED CHALLENGES", result)
        self.assertIn("How might we improve testing?", result)

    def test_limits_marker_display(self):
        """format_scan_results() should limit markers displayed."""
        from brainstorm_utils import format_scan_results

        findings = {
            "timestamp": "2025-01-01T12:00:00",
            "code_markers": [
                {"marker": "TODO", "file": f"file{i}.py", "line": i, "text": f"Task {i}"}
                for i in range(15)
            ],
            "large_files": [],
            "archive_patterns": [],
            "state_patterns": [],
            "suggested_challenges": []
        }

        result = format_scan_results(findings)

        self.assertIn("... and 5 more", result)


if __name__ == '__main__':
    unittest.main()
