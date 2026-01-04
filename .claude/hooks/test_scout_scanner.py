#!/usr/bin/env python3
"""
Tests for scout_scanner.py - autonomous codebase exploration scanner.

Tests the core scanning functions for:
- File discovery with filtering
- TODO/FIXME comment detection
- Large file identification
- Missing test detection
"""
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch, MagicMock

# Add hooks directory to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


class TestDiscoverFiles(unittest.TestCase):
    """Tests for discover_files() function."""

    @patch('scout_scanner.SCOUT_THRESHOLDS', {"max_files_to_scan": 100})
    @patch('scout_scanner.SCANNABLE_EXTENSIONS', {'.py', '.js'})
    @patch('scout_scanner.SKIP_DIRECTORIES', {'node_modules', '__pycache__'})
    def test_discovers_matching_files(self):
        """discover_files() should find files with matching extensions."""
        from scout_scanner import discover_files

        with tempfile.TemporaryDirectory() as tmpdir:
            # Create test files
            (Path(tmpdir) / "app.py").write_text("# Python file")
            (Path(tmpdir) / "index.js").write_text("// JS file")
            (Path(tmpdir) / "readme.md").write_text("# Readme")

            files = discover_files(Path(tmpdir))

            self.assertEqual(len(files), 2)
            extensions = {f.suffix for f in files}
            self.assertEqual(extensions, {'.py', '.js'})

    @patch('scout_scanner.SCOUT_THRESHOLDS', {"max_files_to_scan": 100})
    @patch('scout_scanner.SCANNABLE_EXTENSIONS', {'.py'})
    @patch('scout_scanner.SKIP_DIRECTORIES', {'node_modules', '__pycache__'})
    def test_skips_excluded_directories(self):
        """discover_files() should skip directories in SKIP_DIRECTORIES."""
        from scout_scanner import discover_files

        with tempfile.TemporaryDirectory() as tmpdir:
            # Create files in skip directory
            skip_dir = Path(tmpdir) / "node_modules"
            skip_dir.mkdir()
            (skip_dir / "module.py").write_text("# Skipped")

            # Create file in normal directory
            (Path(tmpdir) / "app.py").write_text("# Found")

            files = discover_files(Path(tmpdir))

            self.assertEqual(len(files), 1)
            self.assertTrue(files[0].name == "app.py")

    @patch('scout_scanner.SCANNABLE_EXTENSIONS', {'.py'})
    @patch('scout_scanner.SKIP_DIRECTORIES', set())
    def test_respects_max_files(self):
        """discover_files() should respect max_files limit."""
        from scout_scanner import discover_files

        with tempfile.TemporaryDirectory() as tmpdir:
            # Create more files than limit
            for i in range(10):
                (Path(tmpdir) / f"file{i}.py").write_text(f"# File {i}")

            files = discover_files(Path(tmpdir), max_files=3)

            self.assertEqual(len(files), 3)


class TestScanTodos(unittest.TestCase):
    """Tests for scan_todos() function."""

    def test_finds_todo_comments(self):
        """scan_todos() should find TODO comments."""
        from scout_scanner import scan_todos

        with tempfile.TemporaryDirectory() as tmpdir:
            filepath = Path(tmpdir) / "test.py"
            filepath.write_text("""
# TODO: Implement this feature
def foo():
    pass
# TODO Add validation
""")

            findings = scan_todos(filepath)

            self.assertEqual(len(findings), 2)
            self.assertTrue(all(f.type.value == "todo" for f in findings))

    def test_finds_fixme_with_high_priority(self):
        """scan_todos() should mark FIXME as high priority."""
        from scout_scanner import scan_todos
        from scout_config import FindingPriority

        with tempfile.TemporaryDirectory() as tmpdir:
            filepath = Path(tmpdir) / "test.py"
            filepath.write_text("# FIXME: Critical bug here")

            findings = scan_todos(filepath)

            self.assertEqual(len(findings), 1)
            self.assertEqual(findings[0].priority, FindingPriority.HIGH)

    def test_handles_unreadable_file(self):
        """scan_todos() should handle files that can't be read."""
        from scout_scanner import scan_todos

        # Non-existent file
        findings = scan_todos(Path("/nonexistent/file.py"))

        self.assertEqual(len(findings), 0)

    def test_extracts_todo_message(self):
        """scan_todos() should extract the TODO message."""
        from scout_scanner import scan_todos

        with tempfile.TemporaryDirectory() as tmpdir:
            filepath = Path(tmpdir) / "test.py"
            filepath.write_text("# TODO: This is the message")

            findings = scan_todos(filepath)

            self.assertIn("This is the message", findings[0].title)


class TestScanLargeFiles(unittest.TestCase):
    """Tests for scan_large_files() function."""

    @patch('scout_scanner.SCOUT_THRESHOLDS', {"large_file_lines": 10})
    def test_finds_large_files(self):
        """scan_large_files() should find files exceeding threshold."""
        from scout_scanner import scan_large_files

        with tempfile.TemporaryDirectory() as tmpdir:
            # Create small file
            small = Path(tmpdir) / "small.py"
            small.write_text("line\n" * 5)

            # Create large file
            large = Path(tmpdir) / "large.py"
            large.write_text("line\n" * 20)

            files = [small, large]
            findings = scan_large_files(files)

            self.assertEqual(len(findings), 1)
            self.assertIn("large.py", findings[0].title)

    @patch('scout_scanner.SCOUT_THRESHOLDS', {"large_file_lines": 100})
    def test_no_findings_for_small_files(self):
        """scan_large_files() should not flag small files."""
        from scout_scanner import scan_large_files

        with tempfile.TemporaryDirectory() as tmpdir:
            small = Path(tmpdir) / "small.py"
            small.write_text("line\n" * 10)

            findings = scan_large_files([small])

            self.assertEqual(len(findings), 0)


class TestScanMissingTests(unittest.TestCase):
    """Tests for scan_missing_tests() function."""

    def test_finds_files_without_tests(self):
        """scan_missing_tests() should find source files without tests."""
        from scout_scanner import scan_missing_tests

        with tempfile.TemporaryDirectory() as tmpdir:
            # Source file without test (needs > 20 lines)
            source = Path(tmpdir) / "module.py"
            source.write_text("# code\n" * 25)

            files = [source]
            findings = scan_missing_tests(files, Path(tmpdir))

            self.assertEqual(len(findings), 1)
            self.assertIn("module.py", findings[0].title)

    def test_ignores_files_with_tests(self):
        """scan_missing_tests() should ignore files that have tests."""
        from scout_scanner import scan_missing_tests

        with tempfile.TemporaryDirectory() as tmpdir:
            # Source file
            source = Path(tmpdir) / "utils.py"
            source.write_text("# code\n" * 25)

            # Corresponding test file
            test = Path(tmpdir) / "test_utils.py"
            test.write_text("# tests\n")

            files = [source, test]
            findings = scan_missing_tests(files, Path(tmpdir))

            self.assertEqual(len(findings), 0)

    def test_ignores_small_files(self):
        """scan_missing_tests() should ignore files under 20 lines."""
        from scout_scanner import scan_missing_tests

        with tempfile.TemporaryDirectory() as tmpdir:
            small = Path(tmpdir) / "tiny.py"
            small.write_text("# small\n" * 10)

            findings = scan_missing_tests([small], Path(tmpdir))

            self.assertEqual(len(findings), 0)

    def test_ignores_test_files(self):
        """scan_missing_tests() should not flag test files themselves."""
        from scout_scanner import scan_missing_tests

        with tempfile.TemporaryDirectory() as tmpdir:
            test_file = Path(tmpdir) / "test_module.py"
            test_file.write_text("# test code\n" * 25)

            findings = scan_missing_tests([test_file], Path(tmpdir))

            self.assertEqual(len(findings), 0)


class TestRunScoutScan(unittest.TestCase):
    """Tests for run_scout_scan() function."""

    @patch('scout_scanner.discover_files')
    @patch('scout_scanner.scan_todos')
    @patch('scout_scanner.scan_large_files')
    @patch('scout_scanner.scan_missing_tests')
    @patch('scout_scanner.sort_findings')
    @patch('scout_scanner.SCOUT_THRESHOLDS', {"max_findings": 10})
    def test_runs_all_scanners(self, mock_sort, mock_missing, mock_large, mock_todos, mock_discover):
        """run_scout_scan() should run all scanner types."""
        from scout_scanner import run_scout_scan

        mock_discover.return_value = [Path("/fake/file.py")]
        mock_todos.return_value = []
        mock_large.return_value = []
        mock_missing.return_value = []
        mock_sort.return_value = []

        findings, meta = run_scout_scan(Path("/fake"))

        mock_discover.assert_called_once()
        mock_todos.assert_called()
        mock_large.assert_called_once()
        mock_missing.assert_called_once()

    @patch('scout_scanner.discover_files')
    @patch('scout_scanner.scan_todos')
    @patch('scout_scanner.scan_large_files')
    @patch('scout_scanner.scan_missing_tests')
    @patch('scout_scanner.sort_findings')
    @patch('scout_scanner.SCOUT_THRESHOLDS', {"max_findings": 10})
    def test_returns_metadata(self, mock_sort, mock_missing, mock_large, mock_todos, mock_discover):
        """run_scout_scan() should return scan metadata."""
        from scout_scanner import run_scout_scan

        mock_discover.return_value = [Path("/a.py"), Path("/b.py")]
        mock_todos.return_value = []
        mock_large.return_value = []
        mock_missing.return_value = []
        mock_sort.return_value = []

        findings, meta = run_scout_scan(Path("/fake"))

        self.assertIn("files_scanned", meta)
        self.assertIn("scan_duration_seconds", meta)
        self.assertIn("last_scan", meta)
        self.assertEqual(meta["files_scanned"], 2)

    @patch('scout_scanner.discover_files')
    @patch('scout_scanner.scan_todos')
    @patch('scout_scanner.scan_large_files')
    @patch('scout_scanner.scan_missing_tests')
    @patch('scout_scanner.sort_findings')
    @patch('scout_scanner.SCOUT_THRESHOLDS', {"max_findings": 2})
    def test_limits_findings(self, mock_sort, mock_missing, mock_large, mock_todos, mock_discover):
        """run_scout_scan() should limit findings to max_findings."""
        from scout_scanner import run_scout_scan
        from scout_config import ScoutFinding, FindingType, FindingPriority

        mock_discover.return_value = []
        mock_todos.return_value = []
        mock_large.return_value = []
        mock_missing.return_value = []

        # Return more findings than limit
        findings_list = [
            ScoutFinding(FindingType.TODO, FindingPriority.MEDIUM, f"Finding {i}", "", "")
            for i in range(5)
        ]
        mock_sort.return_value = findings_list

        findings, meta = run_scout_scan(Path("/fake"))

        self.assertEqual(len(findings), 2)


class TestCalculateComplexity(unittest.TestCase):
    """Tests for calculate_complexity() function."""

    def test_simple_function_low_complexity(self):
        """Simple function should have low complexity."""
        from scout_scanner import calculate_complexity

        code = """
def simple():
    return 42
"""
        complexity = calculate_complexity(code)
        self.assertLessEqual(complexity, 5)

    def test_branches_increase_complexity(self):
        """Branches should increase complexity."""
        from scout_scanner import calculate_complexity

        code_simple = "return 1"
        code_branches = """
if x:
    return 1
elif y:
    return 2
else:
    return 3
for i in range(10):
    if i > 5:
        print(i)
"""
        simple_complexity = calculate_complexity(code_simple)
        branch_complexity = calculate_complexity(code_branches)

        self.assertGreater(branch_complexity, simple_complexity)


class TestExtractPythonFunctions(unittest.TestCase):
    """Tests for extract_python_functions()."""

    def test_extracts_function(self):
        """Should extract simple function definitions."""
        from scout_scanner import extract_python_functions

        code = """
def hello():
    print("hello")

def world():
    print("world")
"""
        functions = extract_python_functions(code)
        self.assertEqual(len(functions), 2)
        self.assertEqual(functions[0][0], "hello")
        self.assertEqual(functions[1][0], "world")


class TestScanComplexity(unittest.TestCase):
    """Tests for scan_complexity()."""

    def test_skips_non_python(self):
        """Should skip non-Python files."""
        from scout_scanner import scan_complexity

        findings = scan_complexity(Path("/fake/file.js"))
        self.assertEqual(findings, [])

    def test_finds_complex_function(self):
        """Should find functions over complexity threshold."""
        import tempfile
        import os
        from scout_scanner import scan_complexity

        # Create code with high complexity (>15 branches)
        complex_code = """
def complex_function():
    if a and b and c:
        if d or e or f:
            if g:
                for i in range(10):
                    if h:
                        while j:
                            try:
                                if k and l or m:
                                    if n:
                                        if o:
                                            pass
                            except:
                                pass
    return None
"""
        with tempfile.NamedTemporaryFile(suffix='.py', mode='w', delete=False) as f:
            f.write(complex_code)
            f.flush()
            findings = scan_complexity(Path(f.name))
            os.unlink(f.name)

        # Should have at least one finding for high complexity
        self.assertGreater(len(findings), 0)


class TestScanDeadCode(unittest.TestCase):
    """Tests for scan_dead_code()."""

    def test_skips_non_python(self):
        """Should skip non-Python files."""
        from scout_scanner import scan_dead_code

        findings = scan_dead_code(Path("/fake/file.js"))
        self.assertEqual(findings, [])

    def test_finds_unused_import(self):
        """Should find imports that are never used."""
        import tempfile
        import os
        from scout_scanner import scan_dead_code

        code = """
import unused_module
import used_module

used_module.do_something()
"""
        with tempfile.NamedTemporaryFile(suffix='.py', mode='w', delete=False) as f:
            f.write(code)
            f.flush()
            findings = scan_dead_code(Path(f.name))
            os.unlink(f.name)

        # Should find the unused import
        unused_findings = [f for f in findings if 'unused_module' in f.title]
        self.assertEqual(len(unused_findings), 1)


# =============================================================================
# UNVERIFIED COMPLETION SCANNER TESTS (v3.9.2)
# =============================================================================

class TestScanUnverifiedCompletions(unittest.TestCase):
    """Tests for scan_unverified_completions() function."""

    def test_returns_empty_for_no_state(self):
        """Should return empty list when state is None."""
        from scout_scanner import scan_unverified_completions
        findings = scan_unverified_completions(None, [])
        self.assertEqual(findings, [])

    def test_returns_empty_for_invalid_state(self):
        """Should return empty list when state is not a dict."""
        from scout_scanner import scan_unverified_completions
        findings = scan_unverified_completions("not a dict", [])
        self.assertEqual(findings, [])

    def test_returns_empty_for_no_plan(self):
        """Should return empty list when state has no plan."""
        from scout_scanner import scan_unverified_completions
        findings = scan_unverified_completions({"memory": []}, [])
        self.assertEqual(findings, [])

    def test_returns_empty_for_empty_plan(self):
        """Should return empty list when plan is empty."""
        from scout_scanner import scan_unverified_completions
        findings = scan_unverified_completions({"plan": []}, [])
        self.assertEqual(findings, [])

    def test_ignores_pending_steps(self):
        """Should not flag pending steps even with verification."""
        from scout_scanner import scan_unverified_completions
        state = {
            "plan": [
                {"description": "Do something", "status": "pending", "verification": "API returns 200"}
            ]
        }
        findings = scan_unverified_completions(state, [])
        self.assertEqual(findings, [])

    def test_ignores_completed_without_verification(self):
        """Should not flag completed steps without verification field."""
        from scout_scanner import scan_unverified_completions
        state = {
            "plan": [
                {"description": "Do something", "status": "completed", "proof": "done"}
            ]
        }
        findings = scan_unverified_completions(state, [])
        self.assertEqual(findings, [])

    def test_flags_completed_with_unverified_verification(self):
        """Should flag completed steps with verification but no matching test."""
        from scout_scanner import scan_unverified_completions
        state = {
            "plan": [
                {
                    "description": "Add auth endpoint",
                    "status": "completed",
                    "verification": "POST /auth returns 200 with valid credentials"
                }
            ]
        }
        # No test files provided
        findings = scan_unverified_completions(state, [])
        self.assertEqual(len(findings), 1)
        self.assertIn("auth endpoint", findings[0].title.lower())
        self.assertEqual(findings[0].context, "POST /auth returns 200 with valid credentials")

    def test_does_not_flag_when_test_matches(self):
        """Should not flag when test file contains verification keywords."""
        from scout_scanner import scan_unverified_completions
        import tempfile

        state = {
            "plan": [
                {
                    "description": "Add user login",
                    "status": "completed",
                    "verification": "POST /login returns token for valid user"
                }
            ]
        }

        # Create a test file with matching content
        with tempfile.TemporaryDirectory() as tmpdir:
            test_file = Path(tmpdir) / "test_auth.py"
            test_file.write_text("""
def test_login_returns_token():
    response = client.post('/login', json={'user': 'test'})
    assert response.status_code == 200
    assert 'token' in response.json()
""")
            findings = scan_unverified_completions(state, [test_file])
            # Should not flag because test contains 'login', 'token', 'user' keywords
            self.assertEqual(len(findings), 0)

    def test_finding_has_correct_type(self):
        """Should create finding with UNVERIFIED_COMPLETION type."""
        from scout_scanner import scan_unverified_completions
        from scout_config import FindingType

        state = {
            "plan": [
                {
                    "description": "Add feature X",
                    "status": "completed",
                    "verification": "Feature X works correctly"
                }
            ]
        }
        findings = scan_unverified_completions(state, [])
        self.assertEqual(len(findings), 1)
        self.assertEqual(findings[0].type, FindingType.UNVERIFIED_COMPLETION)

    def test_finding_location_includes_plan_index(self):
        """Should include plan index in finding location."""
        from scout_scanner import scan_unverified_completions

        state = {
            "plan": [
                {"description": "Step 1", "status": "completed", "proof": "done"},
                {"description": "Step 2", "status": "completed", "verification": "Something"},
            ]
        }
        findings = scan_unverified_completions(state, [])
        self.assertEqual(len(findings), 1)
        self.assertIn("plan[1]", findings[0].location)


class TestExtractVerificationKeywords(unittest.TestCase):
    """Tests for _extract_verification_keywords() helper."""

    def test_extracts_meaningful_words(self):
        """Should extract domain-specific keywords."""
        from scout_scanner import _extract_verification_keywords
        keywords = _extract_verification_keywords("post /auth returns 200 with valid credentials")
        self.assertIn("post", keywords)
        self.assertIn("auth", keywords)
        self.assertIn("200", keywords)
        self.assertIn("credentials", keywords)

    def test_filters_stop_words(self):
        """Should filter out common stop words."""
        from scout_scanner import _extract_verification_keywords
        keywords = _extract_verification_keywords("the user should be able to login")
        self.assertNotIn("the", keywords)
        self.assertNotIn("should", keywords)
        self.assertNotIn("be", keywords)
        self.assertIn("user", keywords)
        self.assertIn("able", keywords)
        self.assertIn("login", keywords)

    def test_filters_short_words(self):
        """Should filter words with 2 or fewer characters."""
        from scout_scanner import _extract_verification_keywords
        keywords = _extract_verification_keywords("if a is b then x")
        self.assertNotIn("if", keywords)
        self.assertNotIn("a", keywords)
        self.assertNotIn("is", keywords)
        self.assertNotIn("b", keywords)

    def test_handles_special_characters(self):
        """Should split on special characters and punctuation."""
        from scout_scanner import _extract_verification_keywords
        keywords = _extract_verification_keywords("user.login() returns {token: string}")
        self.assertIn("user", keywords)
        self.assertIn("login", keywords)
        self.assertIn("token", keywords)
        self.assertIn("string", keywords)


if __name__ == '__main__':
    unittest.main()
