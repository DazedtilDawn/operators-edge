#!/usr/bin/env python3
"""
Tests for rules_engine.py - graduated lessons become enforcement.
"""
import unittest
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from rules_engine import (
    Rule, RuleViolation,
    check_rules, format_violations, get_blocking_violation,
    check_policy_has_enforcement, check_python_shebang, check_resolved_archived,
    should_graduate_lesson, get_graduation_candidates,
    GRADUATION_THRESHOLD,
)


class TestRuleDataclasses(unittest.TestCase):
    """Test Rule and RuleViolation dataclasses."""

    def test_rule_to_dict(self):
        rule = Rule(
            id="test-rule",
            trigger_pattern=r"\.py$",
            check_fn="test_check",
            message="Test message",
            action="warn"
        )
        d = rule.to_dict()
        self.assertEqual(d["id"], "test-rule")
        self.assertEqual(d["action"], "warn")
        self.assertTrue(d["enabled"])

    def test_violation_to_response_warn(self):
        v = RuleViolation(
            rule_id="test",
            rule_message="Test warning",
            action="warn",
            context="Some context"
        )
        action, msg = v.to_response()
        self.assertEqual(action, "warn")
        self.assertIn("Test warning", msg)

    def test_violation_to_response_block(self):
        v = RuleViolation(
            rule_id="test",
            rule_message="Test block",
            action="block",
            context="Some context"
        )
        action, msg = v.to_response()
        self.assertEqual(action, "ask")
        self.assertIn("Rule violation", msg)
        self.assertIn("Test block", msg)


class TestPolicyEnforcementRule(unittest.TestCase):
    """Test the policy-has-enforcement rule."""

    def test_triggers_on_policy_file_with_should(self):
        tool_input = {
            "file_path": "/project/CLAUDE.md",
            "content": "Users should always verify their input."
        }
        violation = check_policy_has_enforcement(tool_input)
        self.assertIsNotNone(violation)
        self.assertEqual(violation.rule_id, "policy-enforcement")

    def test_triggers_on_policy_file_with_must(self):
        tool_input = {
            "file_path": "/project/AGENTS.md",
            "new_string": "Agents must validate all inputs."
        }
        violation = check_policy_has_enforcement(tool_input)
        self.assertIsNotNone(violation)

    def test_no_trigger_when_hooks_mentioned(self):
        tool_input = {
            "file_path": "/project/CLAUDE.md",
            "content": "Users should verify input. This is enforced by the pre_tool hook."
        }
        violation = check_policy_has_enforcement(tool_input)
        self.assertIsNone(violation)

    def test_no_trigger_on_non_policy_file(self):
        tool_input = {
            "file_path": "/project/src/main.py",
            "content": "Users should always verify their input."
        }
        violation = check_policy_has_enforcement(tool_input)
        self.assertIsNone(violation)

    def test_no_trigger_on_empty_content(self):
        tool_input = {
            "file_path": "/project/CLAUDE.md",
            "content": ""
        }
        violation = check_policy_has_enforcement(tool_input)
        self.assertIsNone(violation)


class TestPythonShebangRule(unittest.TestCase):
    """Test the python-shebang rule."""

    def test_triggers_on_bad_shebang(self):
        tool_input = {
            "file_path": "/project/script.py",
            "content": "#!/usr/bin/env python\nprint('hello')"
        }
        violation = check_python_shebang(tool_input)
        self.assertIsNotNone(violation)
        self.assertEqual(violation.rule_id, "python-shebang")

    def test_triggers_on_direct_python_path(self):
        tool_input = {
            "file_path": "/project/script.py",
            "new_string": "#!/usr/bin/python\nprint('hello')"
        }
        violation = check_python_shebang(tool_input)
        self.assertIsNotNone(violation)

    def test_no_trigger_on_python3_shebang(self):
        tool_input = {
            "file_path": "/project/script.py",
            "content": "#!/usr/bin/env python3\nprint('hello')"
        }
        violation = check_python_shebang(tool_input)
        self.assertIsNone(violation)

    def test_no_trigger_without_shebang(self):
        tool_input = {
            "file_path": "/project/script.py",
            "content": "print('hello')"
        }
        violation = check_python_shebang(tool_input)
        self.assertIsNone(violation)

    def test_no_trigger_on_non_python_file(self):
        tool_input = {
            "file_path": "/project/script.js",
            "content": "#!/usr/bin/env python\nconsole.log('hello')"
        }
        violation = check_python_shebang(tool_input)
        self.assertIsNone(violation)


class TestResolvedArchivedRule(unittest.TestCase):
    """Test the resolved-archived rule."""

    def test_triggers_on_resolved_mismatch(self):
        tool_input = {
            "file_path": "/project/.claude/active_context.yaml",
            "content": 'mismatches:\n  - status: "resolved"\n    description: "test"'
        }
        violation = check_resolved_archived(tool_input)
        self.assertIsNotNone(violation)
        self.assertEqual(violation.rule_id, "resolved-archived")

    def test_no_trigger_on_active_mismatch(self):
        tool_input = {
            "file_path": "/project/.claude/active_context.yaml",
            "content": 'mismatches:\n  - status: "active"\n    description: "test"'
        }
        violation = check_resolved_archived(tool_input)
        self.assertIsNone(violation)

    def test_no_trigger_on_other_files(self):
        tool_input = {
            "file_path": "/project/config.yaml",
            "content": 'mismatches:\n  - status: "resolved"'
        }
        violation = check_resolved_archived(tool_input)
        self.assertIsNone(violation)


class TestCheckRules(unittest.TestCase):
    """Test the main check_rules function."""

    def test_returns_violations_for_matching_rules(self):
        tool_input = {
            "file_path": "/project/script.py",
            "content": "#!/usr/bin/env python\nprint('hello')"
        }
        violations = check_rules("Write", tool_input)
        self.assertGreater(len(violations), 0)
        self.assertEqual(violations[0].rule_id, "python-shebang")

    def test_returns_empty_for_non_file_tools(self):
        violations = check_rules("Bash", {"command": "ls"})
        self.assertEqual(len(violations), 0)

    def test_returns_empty_for_clean_input(self):
        tool_input = {
            "file_path": "/project/script.py",
            "content": "#!/usr/bin/env python3\nprint('hello')"
        }
        violations = check_rules("Write", tool_input)
        self.assertEqual(len(violations), 0)


class TestFormatViolations(unittest.TestCase):
    """Test violation formatting."""

    def test_formats_violations(self):
        violations = [
            RuleViolation("r1", "Message 1", "warn", "ctx"),
            RuleViolation("r2", "Message 2", "block", "ctx"),
        ]
        formatted = format_violations(violations)
        self.assertIn("Rule checks", formatted)
        self.assertIn("Message 1", formatted)
        self.assertIn("Message 2", formatted)

    def test_empty_for_no_violations(self):
        formatted = format_violations([])
        self.assertEqual(formatted, "")


class TestGetBlockingViolation(unittest.TestCase):
    """Test blocking violation detection."""

    def test_returns_blocking(self):
        violations = [
            RuleViolation("r1", "Warn", "warn", "ctx"),
            RuleViolation("r2", "Block", "block", "ctx"),
        ]
        blocking = get_blocking_violation(violations)
        self.assertIsNotNone(blocking)
        self.assertEqual(blocking.rule_id, "r2")

    def test_returns_none_for_no_blocking(self):
        violations = [
            RuleViolation("r1", "Warn 1", "warn", "ctx"),
            RuleViolation("r2", "Warn 2", "warn", "ctx"),
        ]
        blocking = get_blocking_violation(violations)
        self.assertIsNone(blocking)


class TestLessonGraduation(unittest.TestCase):
    """Test lesson graduation logic."""

    def test_should_graduate_high_reinforcement(self):
        lesson = {"trigger": "test", "reinforced": 15}
        self.assertTrue(should_graduate_lesson(lesson))

    def test_should_not_graduate_low_reinforcement(self):
        lesson = {"trigger": "test", "reinforced": 5}
        self.assertFalse(should_graduate_lesson(lesson))

    def test_evergreen_does_not_graduate(self):
        """Evergreen lessons stay as lessons, don't become rules."""
        lesson = {"trigger": "test", "reinforced": 50, "evergreen": True}
        self.assertFalse(should_graduate_lesson(lesson))

    def test_threshold_boundary(self):
        # Just below threshold
        lesson_below = {"trigger": "test", "reinforced": GRADUATION_THRESHOLD - 1}
        self.assertFalse(should_graduate_lesson(lesson_below))

        # At threshold
        lesson_at = {"trigger": "test", "reinforced": GRADUATION_THRESHOLD}
        self.assertTrue(should_graduate_lesson(lesson_at))

    def test_get_graduation_candidates(self):
        state = {
            "memory": [
                {"trigger": "low", "reinforced": 3},
                {"trigger": "high", "reinforced": 15},
                {"trigger": "evergreen", "reinforced": 50, "evergreen": True},
            ]
        }
        candidates = get_graduation_candidates(state)
        self.assertEqual(len(candidates), 1)
        self.assertEqual(candidates[0]["trigger"], "high")


# =============================================================================
# v7.1 GRADUATION PIPELINE TESTS
# =============================================================================

class TestRuleShadowMode(unittest.TestCase):
    """Test shadow mode tracking for graduated rules."""

    def test_new_rule_starts_in_shadow_mode(self):
        """New rules should start with shadow_mode=True."""
        rule = Rule(
            id="test",
            trigger_pattern=r"\.py$",
            check_fn="check",
            message="Test"
        )
        self.assertTrue(rule.shadow_mode)
        self.assertEqual(rule.fire_count, 0)

    def test_rule_from_dict_preserves_shadow_mode(self):
        """Rule.from_dict should preserve shadow mode fields."""
        data = {
            "id": "test",
            "trigger_pattern": r"\.py$",
            "check_fn": "check",
            "message": "Test",
            "shadow_mode": False,
            "fire_count": 15,
            "promoted_at": "2026-01-01T00:00:00",
        }
        rule = Rule.from_dict(data)
        self.assertFalse(rule.shadow_mode)
        self.assertEqual(rule.fire_count, 15)
        self.assertEqual(rule.promoted_at, "2026-01-01T00:00:00")

    def test_is_ready_for_promotion_requires_min_fires(self):
        """Rule needs minimum fires before promotion check."""
        from rules_engine import SHADOW_MODE_MIN_FIRES
        rule = Rule(
            id="test",
            trigger_pattern=r"\.py$",
            check_fn="check",
            message="Test",
            shadow_mode=True,
            fire_count=SHADOW_MODE_MIN_FIRES - 1,
            promoted_at="2020-01-01T00:00:00",  # Old enough
        )
        self.assertFalse(rule.is_ready_for_promotion())

        rule.fire_count = SHADOW_MODE_MIN_FIRES
        self.assertTrue(rule.is_ready_for_promotion())

    def test_promoted_rule_not_ready_for_promotion(self):
        """Already promoted rules return False for is_ready_for_promotion."""
        rule = Rule(
            id="test",
            trigger_pattern=r"\.py$",
            check_fn="check",
            message="Test",
            shadow_mode=False,  # Already promoted
            fire_count=100,
        )
        self.assertFalse(rule.is_ready_for_promotion())


class TestRulesFilePersistence(unittest.TestCase):
    """Test rules.json file operations."""

    def setUp(self):
        import tempfile
        self.temp_dir = tempfile.mkdtemp()

    def tearDown(self):
        import shutil
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_save_and_load_rules(self):
        """Can save and load rules from JSON."""
        from rules_engine import save_rules_to_file, load_rules_from_file
        from pathlib import Path

        rules = [
            Rule(
                id="test-rule-1",
                trigger_pattern=r"\.py$",
                check_fn="check_python_shebang",
                message="Test rule 1",
            ),
            Rule(
                id="test-rule-2",
                trigger_pattern=r"\.md$",
                check_fn="check_policy",
                message="Test rule 2",
                shadow_mode=False,
            ),
        ]

        project_dir = Path(self.temp_dir)
        self.assertTrue(save_rules_to_file(rules, project_dir))

        loaded = load_rules_from_file(project_dir)
        self.assertEqual(len(loaded), 2)
        self.assertEqual(loaded[0].id, "test-rule-1")
        self.assertTrue(loaded[0].shadow_mode)
        self.assertEqual(loaded[1].id, "test-rule-2")
        self.assertFalse(loaded[1].shadow_mode)

    def test_add_rule_to_file(self):
        """Can add a single rule to JSON."""
        from rules_engine import add_rule_to_file, load_rules_from_file
        from pathlib import Path

        project_dir = Path(self.temp_dir)

        rule = Rule(
            id="new-rule",
            trigger_pattern=r"\.js$",
            check_fn="check_js",
            message="JS rule",
        )

        self.assertTrue(add_rule_to_file(rule, project_dir))

        loaded = load_rules_from_file(project_dir)
        self.assertEqual(len(loaded), 1)
        self.assertEqual(loaded[0].id, "new-rule")

    def test_add_duplicate_rule_fails(self):
        """Adding duplicate rule ID fails."""
        from rules_engine import add_rule_to_file
        from pathlib import Path

        project_dir = Path(self.temp_dir)

        rule = Rule(id="dup", trigger_pattern=".*", check_fn="c", message="m")

        self.assertTrue(add_rule_to_file(rule, project_dir))
        self.assertFalse(add_rule_to_file(rule, project_dir))  # Duplicate

    def test_remove_rule_from_file(self):
        """Can remove a rule from JSON."""
        from rules_engine import save_rules_to_file, remove_rule_from_file, load_rules_from_file
        from pathlib import Path

        project_dir = Path(self.temp_dir)

        rules = [
            Rule(id="keep", trigger_pattern=".*", check_fn="c", message="keep"),
            Rule(id="remove", trigger_pattern=".*", check_fn="c", message="remove"),
        ]
        save_rules_to_file(rules, project_dir)

        self.assertTrue(remove_rule_from_file("remove", project_dir))

        loaded = load_rules_from_file(project_dir)
        self.assertEqual(len(loaded), 1)
        self.assertEqual(loaded[0].id, "keep")


class TestGraduationFunctions(unittest.TestCase):
    """Test lesson graduation functions."""

    def test_generate_rule_id(self):
        """Rule ID generated from lesson trigger."""
        from rules_engine import generate_rule_id

        lesson = {"trigger": "react hooks", "lesson": "Use useCallback"}
        rule_id = generate_rule_id(lesson)
        self.assertEqual(rule_id, "graduated-react-hooks")

    def test_generate_rule_id_sanitizes(self):
        """Rule ID is sanitized for special characters."""
        from rules_engine import generate_rule_id

        lesson = {"trigger": "C++ templates & generics", "lesson": "Use templates"}
        rule_id = generate_rule_id(lesson)
        self.assertEqual(rule_id, "graduated-c-templates-generics")

    def test_generate_trigger_pattern_python(self):
        """Trigger pattern inferred for Python lessons."""
        from rules_engine import generate_trigger_pattern

        lesson = {"trigger": "python shebang", "lesson": "Use python3"}
        pattern = generate_trigger_pattern(lesson)
        self.assertEqual(pattern, r"\.py$")

    def test_generate_trigger_pattern_react(self):
        """Trigger pattern inferred for React lessons."""
        from rules_engine import generate_trigger_pattern

        lesson = {"trigger": "react components", "lesson": "Use hooks"}
        pattern = generate_trigger_pattern(lesson)
        self.assertEqual(pattern, r"\.(jsx|tsx)$")

    def test_generate_trigger_pattern_default(self):
        """Default pattern matches all files."""
        from rules_engine import generate_trigger_pattern

        lesson = {"trigger": "general advice", "lesson": "Be careful"}
        pattern = generate_trigger_pattern(lesson)
        self.assertEqual(pattern, r".*")

    def test_graduate_lesson_to_rule(self):
        """Can graduate a lesson to a shadow mode rule."""
        from rules_engine import graduate_lesson_to_rule, load_rules_from_file
        from pathlib import Path
        import tempfile
        import shutil

        temp_dir = tempfile.mkdtemp()
        try:
            project_dir = Path(temp_dir)

            lesson = {
                "trigger": "test trigger",
                "lesson": "Test lesson text",
                "reinforced": 15,
            }

            rule = graduate_lesson_to_rule(lesson, project_dir)

            self.assertIsNotNone(rule)
            self.assertEqual(rule.id, "graduated-test-trigger")
            self.assertEqual(rule.message, "Test lesson text")
            self.assertTrue(rule.shadow_mode)
            self.assertEqual(rule.fire_count, 0)

            # Verify persisted
            loaded = load_rules_from_file(project_dir)
            self.assertEqual(len(loaded), 1)
            self.assertEqual(loaded[0].id, "graduated-test-trigger")
        finally:
            shutil.rmtree(temp_dir, ignore_errors=True)

    def test_format_graduation_candidates(self):
        """Candidates are formatted for display."""
        from rules_engine import format_graduation_candidates

        candidates = [
            {"trigger": "hooks", "lesson": "Use hooks properly in React components for state", "reinforced": 12},
            {"trigger": "async", "lesson": "Always await async operations", "reinforced": 10},
        ]

        output = format_graduation_candidates(candidates)

        self.assertIn("Graduation Candidates", output)
        self.assertIn("[hooks]", output)
        self.assertIn("12 times", output)
        self.assertIn("[async]", output)

    def test_format_no_candidates(self):
        """Empty candidates list handled."""
        from rules_engine import format_graduation_candidates

        output = format_graduation_candidates([])
        self.assertIn("No lessons ready", output)


if __name__ == "__main__":
    unittest.main()
