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


if __name__ == "__main__":
    unittest.main()
