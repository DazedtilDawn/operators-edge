#!/usr/bin/env python3
"""
Tests for scout_config.py

Coverage:
- FindingType: Enum for finding types
- FindingPriority: Enum for priority levels
- ScoutFinding: Dataclass for findings
- TODO_PATTERNS: Regex patterns for TODOs
- SCANNABLE_EXTENSIONS: File extensions to scan
- SKIP_DIRECTORIES: Directories to skip
- SCOUT_THRESHOLDS: Threshold settings
- score_finding: Finding prioritization
- sort_findings: Sorting findings by score
- get_default_scout_state: Default state structure
- finding_to_objective: Convert finding to objective
- TaskComplexity: Task complexity classification
- classify_task_complexity: Complexity classification logic
- get_complexity_label: Human-readable complexity labels
- should_auto_plan: Auto-plan decision
- should_auto_select: Auto-select decision
- get_auto_plan_steps: Generate plan steps
- format_finding_for_display: Terminal display formatting
"""

import unittest

import scout_config
from scout_config import (
    FindingType, FindingPriority, ScoutFinding, TaskComplexity,
    TODO_PATTERNS, SCANNABLE_EXTENSIONS, SKIP_DIRECTORIES,
    SCOUT_THRESHOLDS, PRIORITY_WEIGHTS, TYPE_PRIORITY_BOOST,
    SIMPLE_TASK_KEYWORDS, COMPLEX_TASK_KEYWORDS,
    SIMPLE_FINDING_TYPES, COMPLEX_FINDING_TYPES,
    score_finding, sort_findings, get_default_scout_state,
    finding_to_objective, classify_task_complexity, get_complexity_label,
    should_auto_plan, should_auto_select, get_auto_plan_steps,
    format_finding_for_display
)


class TestFindingTypeEnum(unittest.TestCase):
    """Tests for FindingType enum."""

    def test_has_todo(self):
        """FindingType should have TODO."""
        self.assertEqual(FindingType.TODO.value, "todo")

    def test_has_large_file(self):
        """FindingType should have LARGE_FILE."""
        self.assertEqual(FindingType.LARGE_FILE.value, "large_file")

    def test_has_missing_test(self):
        """FindingType should have MISSING_TEST."""
        self.assertEqual(FindingType.MISSING_TEST.value, "missing_test")

    def test_has_dead_code(self):
        """FindingType should have DEAD_CODE."""
        self.assertEqual(FindingType.DEAD_CODE.value, "dead_code")

    def test_has_security(self):
        """FindingType should have SECURITY."""
        self.assertEqual(FindingType.SECURITY.value, "security")

    def test_has_complexity(self):
        """FindingType should have COMPLEXITY."""
        self.assertEqual(FindingType.COMPLEXITY.value, "complexity")

    def test_has_duplication(self):
        """FindingType should have DUPLICATION."""
        self.assertEqual(FindingType.DUPLICATION.value, "duplication")

    def test_has_outdated_dep(self):
        """FindingType should have OUTDATED_DEP."""
        self.assertEqual(FindingType.OUTDATED_DEP.value, "outdated_dep")


class TestFindingPriorityEnum(unittest.TestCase):
    """Tests for FindingPriority enum."""

    def test_has_high(self):
        """FindingPriority should have HIGH."""
        self.assertEqual(FindingPriority.HIGH.value, "high")

    def test_has_medium(self):
        """FindingPriority should have MEDIUM."""
        self.assertEqual(FindingPriority.MEDIUM.value, "medium")

    def test_has_low(self):
        """FindingPriority should have LOW."""
        self.assertEqual(FindingPriority.LOW.value, "low")


class TestScoutFindingDataclass(unittest.TestCase):
    """Tests for ScoutFinding dataclass."""

    def test_create_minimal(self):
        """Should create finding with required fields only."""
        finding = ScoutFinding(
            type=FindingType.TODO,
            priority=FindingPriority.MEDIUM,
            title="Fix this bug",
            description="A bug needs fixing",
            location="src/main.py:42"
        )
        self.assertEqual(finding.type, FindingType.TODO)
        self.assertEqual(finding.priority, FindingPriority.MEDIUM)

    def test_optional_fields_default_none(self):
        """Optional fields should default to None."""
        finding = ScoutFinding(
            type=FindingType.TODO,
            priority=FindingPriority.LOW,
            title="Title",
            description="Desc",
            location="file.py:1"
        )
        self.assertIsNone(finding.context)
        self.assertIsNone(finding.suggested_action)

    def test_create_with_optional_fields(self):
        """Should accept optional fields."""
        finding = ScoutFinding(
            type=FindingType.MISSING_TEST,
            priority=FindingPriority.HIGH,
            title="Add tests",
            description="No tests exist",
            location="utils.py:1",
            context="def untested_func():",
            suggested_action="Write unit tests"
        )
        self.assertEqual(finding.context, "def untested_func():")
        self.assertEqual(finding.suggested_action, "Write unit tests")

    def test_to_dict(self):
        """to_dict should return serializable dict."""
        finding = ScoutFinding(
            type=FindingType.SECURITY,
            priority=FindingPriority.HIGH,
            title="SQL injection risk",
            description="Raw SQL used",
            location="db.py:100",
            context="query = f'SELECT * FROM {table}'",
            suggested_action="Use parameterized queries"
        )
        result = finding.to_dict()

        self.assertEqual(result["type"], "security")
        self.assertEqual(result["priority"], "high")
        self.assertEqual(result["title"], "SQL injection risk")
        self.assertEqual(result["location"], "db.py:100")
        self.assertIn("context", result)
        self.assertIn("suggested_action", result)

    def test_from_dict(self):
        """from_dict should create finding from dict."""
        data = {
            "type": "todo",
            "priority": "medium",
            "title": "Implement feature",
            "description": "Needs work",
            "location": "app.py:50"
        }
        finding = ScoutFinding.from_dict(data)

        self.assertEqual(finding.type, FindingType.TODO)
        self.assertEqual(finding.priority, FindingPriority.MEDIUM)
        self.assertEqual(finding.title, "Implement feature")

    def test_from_dict_with_optional(self):
        """from_dict should handle optional fields."""
        data = {
            "type": "large_file",
            "priority": "low",
            "title": "Large file",
            "description": "File is too long",
            "location": "big.py:1",
            "context": "# Very long file",
            "suggested_action": "Split into modules"
        }
        finding = ScoutFinding.from_dict(data)

        self.assertEqual(finding.context, "# Very long file")
        self.assertEqual(finding.suggested_action, "Split into modules")

    def test_roundtrip(self):
        """to_dict then from_dict should preserve data."""
        original = ScoutFinding(
            type=FindingType.DEAD_CODE,
            priority=FindingPriority.LOW,
            title="Unused function",
            description="Function never called",
            location="utils.py:20",
            context="def unused():",
            suggested_action="Remove or document"
        )
        restored = ScoutFinding.from_dict(original.to_dict())

        self.assertEqual(restored.type, original.type)
        self.assertEqual(restored.priority, original.priority)
        self.assertEqual(restored.title, original.title)
        self.assertEqual(restored.description, original.description)
        self.assertEqual(restored.location, original.location)
        self.assertEqual(restored.context, original.context)
        self.assertEqual(restored.suggested_action, original.suggested_action)


class TestPatternConstants(unittest.TestCase):
    """Tests for pattern constants."""

    def test_todo_patterns_is_list(self):
        """TODO_PATTERNS should be a list."""
        self.assertIsInstance(TODO_PATTERNS, list)

    def test_todo_patterns_not_empty(self):
        """TODO_PATTERNS should have entries."""
        self.assertGreater(len(TODO_PATTERNS), 0)

    def test_todo_patterns_has_python_todo(self):
        """Should include Python-style TODO pattern."""
        self.assertTrue(any("TODO" in p for p in TODO_PATTERNS))

    def test_todo_patterns_has_fixme(self):
        """Should include FIXME pattern."""
        self.assertTrue(any("FIXME" in p for p in TODO_PATTERNS))

    def test_scannable_extensions_is_list(self):
        """SCANNABLE_EXTENSIONS should be a list."""
        self.assertIsInstance(SCANNABLE_EXTENSIONS, list)

    def test_scannable_extensions_has_py(self):
        """Should include .py extension."""
        self.assertIn(".py", SCANNABLE_EXTENSIONS)

    def test_scannable_extensions_has_js(self):
        """Should include .js extension."""
        self.assertIn(".js", SCANNABLE_EXTENSIONS)

    def test_scannable_extensions_has_ts(self):
        """Should include .ts extension."""
        self.assertIn(".ts", SCANNABLE_EXTENSIONS)

    def test_skip_directories_is_list(self):
        """SKIP_DIRECTORIES should be a list."""
        self.assertIsInstance(SKIP_DIRECTORIES, list)

    def test_skip_directories_has_node_modules(self):
        """Should skip node_modules."""
        self.assertIn("node_modules", SKIP_DIRECTORIES)

    def test_skip_directories_has_git(self):
        """Should skip .git."""
        self.assertIn(".git", SKIP_DIRECTORIES)

    def test_skip_directories_has_pycache(self):
        """Should skip __pycache__."""
        self.assertIn("__pycache__", SKIP_DIRECTORIES)


class TestScoutThresholds(unittest.TestCase):
    """Tests for SCOUT_THRESHOLDS."""

    def test_is_dict(self):
        """SCOUT_THRESHOLDS should be a dict."""
        self.assertIsInstance(SCOUT_THRESHOLDS, dict)

    def test_has_large_file_lines(self):
        """Should have large_file_lines threshold."""
        self.assertIn("large_file_lines", SCOUT_THRESHOLDS)
        self.assertIsInstance(SCOUT_THRESHOLDS["large_file_lines"], int)

    def test_has_max_findings(self):
        """Should have max_findings threshold."""
        self.assertIn("max_findings", SCOUT_THRESHOLDS)

    def test_has_display_findings(self):
        """Should have display_findings threshold."""
        self.assertIn("display_findings", SCOUT_THRESHOLDS)

    def test_has_scan_timeout(self):
        """Should have scan_timeout_seconds."""
        self.assertIn("scan_timeout_seconds", SCOUT_THRESHOLDS)

    def test_has_max_files(self):
        """Should have max_files_to_scan."""
        self.assertIn("max_files_to_scan", SCOUT_THRESHOLDS)


class TestPriorityWeights(unittest.TestCase):
    """Tests for PRIORITY_WEIGHTS."""

    def test_has_all_priorities(self):
        """Should have weights for all priority levels."""
        self.assertIn(FindingPriority.HIGH, PRIORITY_WEIGHTS)
        self.assertIn(FindingPriority.MEDIUM, PRIORITY_WEIGHTS)
        self.assertIn(FindingPriority.LOW, PRIORITY_WEIGHTS)

    def test_high_greater_than_medium(self):
        """HIGH should have greater weight than MEDIUM."""
        self.assertGreater(
            PRIORITY_WEIGHTS[FindingPriority.HIGH],
            PRIORITY_WEIGHTS[FindingPriority.MEDIUM]
        )

    def test_medium_greater_than_low(self):
        """MEDIUM should have greater weight than LOW."""
        self.assertGreater(
            PRIORITY_WEIGHTS[FindingPriority.MEDIUM],
            PRIORITY_WEIGHTS[FindingPriority.LOW]
        )


class TestTypePriorityBoost(unittest.TestCase):
    """Tests for TYPE_PRIORITY_BOOST."""

    def test_security_is_high(self):
        """Security findings should be HIGH priority."""
        self.assertEqual(TYPE_PRIORITY_BOOST[FindingType.SECURITY], FindingPriority.HIGH)

    def test_missing_test_is_medium(self):
        """Missing test findings should be MEDIUM priority."""
        self.assertEqual(TYPE_PRIORITY_BOOST[FindingType.MISSING_TEST], FindingPriority.MEDIUM)

    def test_large_file_is_low(self):
        """Large file findings should be LOW priority."""
        self.assertEqual(TYPE_PRIORITY_BOOST[FindingType.LARGE_FILE], FindingPriority.LOW)


class TestScoreFinding(unittest.TestCase):
    """Tests for score_finding function."""

    def test_high_priority_higher_score(self):
        """HIGH priority should score higher than MEDIUM."""
        high = ScoutFinding(
            type=FindingType.TODO,
            priority=FindingPriority.HIGH,
            title="High priority task",
            description="",
            location="file.py:1"
        )
        medium = ScoutFinding(
            type=FindingType.TODO,
            priority=FindingPriority.MEDIUM,
            title="Medium priority task",
            description="",
            location="file.py:1"
        )

        self.assertGreater(score_finding(high), score_finding(medium))

    def test_security_keyword_boost(self):
        """'security' in title should boost score."""
        with_security = ScoutFinding(
            type=FindingType.TODO,
            priority=FindingPriority.MEDIUM,
            title="security issue found",
            description="",
            location="file.py:1"
        )
        without = ScoutFinding(
            type=FindingType.TODO,
            priority=FindingPriority.MEDIUM,
            title="regular issue found",
            description="",
            location="file.py:1"
        )

        self.assertGreater(score_finding(with_security), score_finding(without))

    def test_vulnerability_keyword_boost(self):
        """'vulnerability' in title should boost score."""
        with_vuln = ScoutFinding(
            type=FindingType.TODO,
            priority=FindingPriority.LOW,
            title="potential vulnerability",
            description="",
            location="file.py:1"
        )
        without = ScoutFinding(
            type=FindingType.TODO,
            priority=FindingPriority.LOW,
            title="potential issue",
            description="",
            location="file.py:1"
        )

        self.assertGreater(score_finding(with_vuln), score_finding(without))

    def test_fixme_keyword_boost(self):
        """'fixme' in title should boost score."""
        with_fixme = ScoutFinding(
            type=FindingType.TODO,
            priority=FindingPriority.LOW,
            title="FIXME: broken function",
            description="",
            location="file.py:1"
        )
        without = ScoutFinding(
            type=FindingType.TODO,
            priority=FindingPriority.LOW,
            title="function needs work",
            description="",
            location="file.py:1"
        )

        self.assertGreater(score_finding(with_fixme), score_finding(without))

    def test_todo_keyword_boost(self):
        """'todo' in title should boost score."""
        with_todo = ScoutFinding(
            type=FindingType.TODO,
            priority=FindingPriority.LOW,
            title="TODO: implement feature",
            description="",
            location="file.py:1"
        )
        without = ScoutFinding(
            type=FindingType.TODO,
            priority=FindingPriority.LOW,
            title="implement feature",
            description="",
            location="file.py:1"
        )

        self.assertGreater(score_finding(with_todo), score_finding(without))


class TestSortFindings(unittest.TestCase):
    """Tests for sort_findings function."""

    def test_returns_list(self):
        """Should return a list."""
        result = sort_findings([])
        self.assertIsInstance(result, list)

    def test_empty_input(self):
        """Should handle empty list."""
        result = sort_findings([])
        self.assertEqual(result, [])

    def test_sorts_by_score_descending(self):
        """Should sort by score, highest first."""
        low = ScoutFinding(
            type=FindingType.TODO,
            priority=FindingPriority.LOW,
            title="low",
            description="",
            location="a.py:1"
        )
        high = ScoutFinding(
            type=FindingType.TODO,
            priority=FindingPriority.HIGH,
            title="high",
            description="",
            location="b.py:1"
        )
        medium = ScoutFinding(
            type=FindingType.TODO,
            priority=FindingPriority.MEDIUM,
            title="medium",
            description="",
            location="c.py:1"
        )

        result = sort_findings([low, high, medium])

        self.assertEqual(result[0].title, "high")
        self.assertEqual(result[1].title, "medium")
        self.assertEqual(result[2].title, "low")


class TestGetDefaultScoutState(unittest.TestCase):
    """Tests for get_default_scout_state function."""

    def test_returns_dict(self):
        """Should return a dictionary."""
        result = get_default_scout_state()
        self.assertIsInstance(result, dict)

    def test_has_last_scan(self):
        """Should have last_scan key."""
        result = get_default_scout_state()
        self.assertIn("last_scan", result)
        self.assertIsNone(result["last_scan"])

    def test_has_findings(self):
        """Should have empty findings list."""
        result = get_default_scout_state()
        self.assertIn("findings", result)
        self.assertEqual(result["findings"], [])

    def test_has_dismissed(self):
        """Should have empty dismissed list."""
        result = get_default_scout_state()
        self.assertIn("dismissed", result)
        self.assertEqual(result["dismissed"], [])

    def test_has_explored_paths(self):
        """Should have empty explored_paths list."""
        result = get_default_scout_state()
        self.assertIn("explored_paths", result)
        self.assertEqual(result["explored_paths"], [])

    def test_has_files_scanned(self):
        """Should have files_scanned initialized to 0."""
        result = get_default_scout_state()
        self.assertIn("files_scanned", result)
        self.assertEqual(result["files_scanned"], 0)


class TestFindingToObjective(unittest.TestCase):
    """Tests for finding_to_objective function."""

    def test_returns_title(self):
        """Should return the finding's title."""
        finding = ScoutFinding(
            type=FindingType.TODO,
            priority=FindingPriority.MEDIUM,
            title="Implement user authentication",
            description="Users need to log in",
            location="auth.py:1"
        )
        result = finding_to_objective(finding)

        self.assertEqual(result, "Implement user authentication")


class TestTaskComplexityEnum(unittest.TestCase):
    """Tests for TaskComplexity enum."""

    def test_has_simple(self):
        """TaskComplexity should have SIMPLE."""
        self.assertEqual(TaskComplexity.SIMPLE.value, "simple")

    def test_has_medium(self):
        """TaskComplexity should have MEDIUM."""
        self.assertEqual(TaskComplexity.MEDIUM.value, "medium")

    def test_has_complex(self):
        """TaskComplexity should have COMPLEX."""
        self.assertEqual(TaskComplexity.COMPLEX.value, "complex")


class TestComplexityKeywords(unittest.TestCase):
    """Tests for complexity keyword constants."""

    def test_simple_keywords_is_list(self):
        """SIMPLE_TASK_KEYWORDS should be a list."""
        self.assertIsInstance(SIMPLE_TASK_KEYWORDS, list)

    def test_simple_keywords_includes_add_test(self):
        """Should include 'add test' as simple."""
        self.assertIn("add test", SIMPLE_TASK_KEYWORDS)

    def test_simple_keywords_includes_fix_typo(self):
        """Should include 'fix typo' as simple."""
        self.assertIn("fix typo", SIMPLE_TASK_KEYWORDS)

    def test_complex_keywords_is_list(self):
        """COMPLEX_TASK_KEYWORDS should be a list."""
        self.assertIsInstance(COMPLEX_TASK_KEYWORDS, list)

    def test_complex_keywords_includes_refactor(self):
        """Should include 'refactor' as complex."""
        self.assertIn("refactor", COMPLEX_TASK_KEYWORDS)

    def test_complex_keywords_includes_security(self):
        """Should include 'security' as complex."""
        self.assertIn("security", COMPLEX_TASK_KEYWORDS)


class TestComplexityFindingTypes(unittest.TestCase):
    """Tests for complexity finding type constants."""

    def test_simple_finding_types_is_set(self):
        """SIMPLE_FINDING_TYPES should be a set."""
        self.assertIsInstance(SIMPLE_FINDING_TYPES, set)

    def test_missing_test_is_simple(self):
        """MISSING_TEST should be a simple finding type."""
        self.assertIn(FindingType.MISSING_TEST, SIMPLE_FINDING_TYPES)

    def test_complex_finding_types_is_set(self):
        """COMPLEX_FINDING_TYPES should be a set."""
        self.assertIsInstance(COMPLEX_FINDING_TYPES, set)

    def test_large_file_is_complex(self):
        """LARGE_FILE should be a complex finding type."""
        self.assertIn(FindingType.LARGE_FILE, COMPLEX_FINDING_TYPES)

    def test_security_is_complex(self):
        """SECURITY should be a complex finding type."""
        self.assertIn(FindingType.SECURITY, COMPLEX_FINDING_TYPES)


class TestClassifyTaskComplexity(unittest.TestCase):
    """Tests for classify_task_complexity function."""

    def test_refactor_is_complex(self):
        """Finding with 'refactor' should be COMPLEX."""
        finding = ScoutFinding(
            type=FindingType.TODO,
            priority=FindingPriority.MEDIUM,
            title="Refactor the auth module",
            description="Needs cleanup",
            location="auth.py:1"
        )
        result = classify_task_complexity(finding)

        self.assertEqual(result, TaskComplexity.COMPLEX)

    def test_security_type_is_complex(self):
        """SECURITY finding type should be COMPLEX."""
        finding = ScoutFinding(
            type=FindingType.SECURITY,
            priority=FindingPriority.HIGH,
            title="Fix XSS issue",
            description="User input not escaped",
            location="web.py:50"
        )
        result = classify_task_complexity(finding)

        self.assertEqual(result, TaskComplexity.COMPLEX)

    def test_missing_test_is_simple(self):
        """MISSING_TEST finding should be SIMPLE."""
        finding = ScoutFinding(
            type=FindingType.MISSING_TEST,
            priority=FindingPriority.MEDIUM,
            title="No tests for utils.py",
            description="Utils lacks tests",
            location="utils.py:1"
        )
        result = classify_task_complexity(finding)

        self.assertEqual(result, TaskComplexity.SIMPLE)

    def test_large_missing_test_is_complex(self):
        """MISSING_TEST with 'large' in description is COMPLEX."""
        finding = ScoutFinding(
            type=FindingType.MISSING_TEST,
            priority=FindingPriority.MEDIUM,
            title="No tests for large file",
            description="This is a large file",
            location="big.py:1"
        )
        result = classify_task_complexity(finding)

        self.assertEqual(result, TaskComplexity.COMPLEX)

    def test_add_test_keyword_is_simple(self):
        """'add test' keyword should be SIMPLE."""
        finding = ScoutFinding(
            type=FindingType.TODO,
            priority=FindingPriority.MEDIUM,
            title="Add test for validator",
            description="",
            location="validator.py:1"
        )
        result = classify_task_complexity(finding)

        self.assertEqual(result, TaskComplexity.SIMPLE)

    def test_fixme_todo_is_medium(self):
        """FIXME in TODO finding should be MEDIUM."""
        finding = ScoutFinding(
            type=FindingType.TODO,
            priority=FindingPriority.HIGH,
            title="FIXME: Critical bug here",
            description="",
            location="app.py:100"
        )
        result = classify_task_complexity(finding)

        self.assertEqual(result, TaskComplexity.MEDIUM)

    def test_short_todo_with_action_is_simple(self):
        """Short TODO with suggested_action should be SIMPLE."""
        finding = ScoutFinding(
            type=FindingType.TODO,
            priority=FindingPriority.LOW,
            title="Add logging",
            description="",
            location="app.py:10",
            suggested_action="Add log statement"
        )
        result = classify_task_complexity(finding)

        self.assertEqual(result, TaskComplexity.SIMPLE)

    def test_long_todo_without_action_is_medium(self):
        """Long TODO without action should be MEDIUM."""
        finding = ScoutFinding(
            type=FindingType.TODO,
            priority=FindingPriority.LOW,
            title="This is a really long TODO title that describes something complicated that needs significant work",
            description="",
            location="app.py:10"
        )
        result = classify_task_complexity(finding)

        self.assertEqual(result, TaskComplexity.MEDIUM)

    def test_unknown_type_defaults_to_medium(self):
        """Unknown finding type should default to MEDIUM."""
        finding = ScoutFinding(
            type=FindingType.OUTDATED_DEP,
            priority=FindingPriority.MEDIUM,
            title="Update package",
            description="Outdated version",
            location="package.json:5"
        )
        result = classify_task_complexity(finding)

        self.assertEqual(result, TaskComplexity.MEDIUM)


class TestGetComplexityLabel(unittest.TestCase):
    """Tests for get_complexity_label function."""

    def test_simple_label(self):
        """SIMPLE should have green emoji and auto-plan."""
        result = get_complexity_label(TaskComplexity.SIMPLE)
        self.assertIn("Simple", result)
        self.assertIn("auto-plan", result)

    def test_medium_label(self):
        """MEDIUM should have yellow emoji and plan review."""
        result = get_complexity_label(TaskComplexity.MEDIUM)
        self.assertIn("Medium", result)
        self.assertIn("plan review", result)

    def test_complex_label(self):
        """COMPLEX should have red emoji and full review."""
        result = get_complexity_label(TaskComplexity.COMPLEX)
        self.assertIn("Complex", result)
        self.assertIn("full review", result)


class TestShouldAutoPlan(unittest.TestCase):
    """Tests for should_auto_plan function."""

    def test_simple_returns_true(self):
        """SIMPLE complexity finding should auto-plan."""
        finding = ScoutFinding(
            type=FindingType.MISSING_TEST,
            priority=FindingPriority.MEDIUM,
            title="No tests for helper.py",
            description="",
            location="helper.py:1"
        )
        self.assertTrue(should_auto_plan(finding))

    def test_complex_returns_false(self):
        """COMPLEX complexity finding should not auto-plan."""
        finding = ScoutFinding(
            type=FindingType.SECURITY,
            priority=FindingPriority.HIGH,
            title="Fix SQL injection",
            description="",
            location="db.py:50"
        )
        self.assertFalse(should_auto_plan(finding))

    def test_medium_returns_false(self):
        """MEDIUM complexity finding should not auto-plan."""
        finding = ScoutFinding(
            type=FindingType.TODO,
            priority=FindingPriority.MEDIUM,
            title="FIXME: Handle edge case",
            description="",
            location="logic.py:100"
        )
        self.assertFalse(should_auto_plan(finding))


class TestShouldAutoSelect(unittest.TestCase):
    """Tests for should_auto_select function."""

    def test_empty_returns_false(self):
        """Empty findings list should not auto-select."""
        self.assertFalse(should_auto_select([]))

    def test_with_findings_returns_true(self):
        """Non-empty findings should auto-select."""
        findings = [
            ScoutFinding(
                type=FindingType.TODO,
                priority=FindingPriority.MEDIUM,
                title="Task 1",
                description="",
                location="a.py:1"
            )
        ]
        self.assertTrue(should_auto_select(findings))


class TestGetAutoPlanSteps(unittest.TestCase):
    """Tests for get_auto_plan_steps function."""

    def test_missing_test_generates_two_steps(self):
        """MISSING_TEST finding should generate 2 steps."""
        finding = ScoutFinding(
            type=FindingType.MISSING_TEST,
            priority=FindingPriority.MEDIUM,
            title="No tests for parser.py",
            description="",
            location="src/parser.py"
        )
        steps = get_auto_plan_steps(finding)

        self.assertEqual(len(steps), 2)
        self.assertIn("test file", steps[0]["description"].lower())
        self.assertIn("run tests", steps[1]["description"].lower())

    def test_todo_generates_one_step(self):
        """Simple TODO finding should generate 1 step."""
        finding = ScoutFinding(
            type=FindingType.TODO,
            priority=FindingPriority.LOW,
            title="Add logging",
            description="",
            location="app.py:10",
            suggested_action="Add log statement"
        )
        steps = get_auto_plan_steps(finding)

        self.assertEqual(len(steps), 1)

    def test_complex_returns_empty(self):
        """COMPLEX finding should return empty list."""
        finding = ScoutFinding(
            type=FindingType.SECURITY,
            priority=FindingPriority.HIGH,
            title="Security vulnerability",
            description="",
            location="auth.py:1"
        )
        steps = get_auto_plan_steps(finding)

        self.assertEqual(steps, [])

    def test_steps_have_correct_structure(self):
        """Generated steps should have description, status, proof."""
        finding = ScoutFinding(
            type=FindingType.MISSING_TEST,
            priority=FindingPriority.MEDIUM,
            title="No tests",
            description="",
            location="util.py"
        )
        steps = get_auto_plan_steps(finding)

        for step in steps:
            self.assertIn("description", step)
            self.assertIn("status", step)
            self.assertEqual(step["status"], "pending")
            self.assertIn("proof", step)


class TestFormatFindingForDisplay(unittest.TestCase):
    """Tests for format_finding_for_display function."""

    def test_includes_index(self):
        """Should include 1-based index."""
        finding = ScoutFinding(
            type=FindingType.TODO,
            priority=FindingPriority.MEDIUM,
            title="Task title",
            description="",
            location="file.py:1"
        )
        result = format_finding_for_display(finding, 0)

        self.assertIn("[1]", result)

    def test_includes_title(self):
        """Should include finding title."""
        finding = ScoutFinding(
            type=FindingType.TODO,
            priority=FindingPriority.HIGH,
            title="Important task",
            description="",
            location="file.py:1"
        )
        result = format_finding_for_display(finding, 0)

        self.assertIn("Important task", result)

    def test_includes_priority_emoji(self):
        """Should include priority indicator."""
        finding = ScoutFinding(
            type=FindingType.TODO,
            priority=FindingPriority.HIGH,
            title="Task",
            description="",
            location="file.py:1"
        )
        result = format_finding_for_display(finding, 0)

        self.assertIn("!", result)  # HIGH priority uses !

    def test_includes_type_and_priority(self):
        """Should include type and priority values."""
        finding = ScoutFinding(
            type=FindingType.SECURITY,
            priority=FindingPriority.HIGH,
            title="Task",
            description="",
            location="file.py:1"
        )
        result = format_finding_for_display(finding, 0)

        self.assertIn("security", result)
        self.assertIn("high", result)

    def test_includes_location(self):
        """Should include file location."""
        finding = ScoutFinding(
            type=FindingType.TODO,
            priority=FindingPriority.MEDIUM,
            title="Task",
            description="",
            location="src/main.py:42"
        )
        result = format_finding_for_display(finding, 0)

        self.assertIn("src/main.py:42", result)

    def test_includes_complexity_by_default(self):
        """Should include complexity label by default."""
        finding = ScoutFinding(
            type=FindingType.MISSING_TEST,
            priority=FindingPriority.MEDIUM,
            title="No tests",
            description="",
            location="file.py:1"
        )
        result = format_finding_for_display(finding, 0)

        self.assertIn("Complexity:", result)

    def test_can_hide_complexity(self):
        """Should be able to hide complexity."""
        finding = ScoutFinding(
            type=FindingType.TODO,
            priority=FindingPriority.MEDIUM,
            title="Task",
            description="",
            location="file.py:1"
        )
        result = format_finding_for_display(finding, 0, show_complexity=False)

        self.assertNotIn("Complexity:", result)

    def test_includes_context_if_present(self):
        """Should include truncated context if present."""
        finding = ScoutFinding(
            type=FindingType.TODO,
            priority=FindingPriority.MEDIUM,
            title="Task",
            description="",
            location="file.py:1",
            context="def some_function():\n    # TODO: implement"
        )
        result = format_finding_for_display(finding, 0)

        self.assertIn("Context:", result)
        self.assertIn("def some_function():", result)

    def test_includes_action_if_present(self):
        """Should include suggested action if present."""
        finding = ScoutFinding(
            type=FindingType.TODO,
            priority=FindingPriority.MEDIUM,
            title="Task",
            description="",
            location="file.py:1",
            suggested_action="Write unit tests"
        )
        result = format_finding_for_display(finding, 0)

        self.assertIn("Action:", result)
        self.assertIn("Write unit tests", result)


if __name__ == "__main__":
    unittest.main()
