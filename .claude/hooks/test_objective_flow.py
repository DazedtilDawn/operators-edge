#!/usr/bin/env python3
"""
Tests for /edge "objective" flow (v6.0).

Tests the new objective management functions that enable:
  /edge "Deploy authentication system"
to just work.
"""
import os
import sys
import tempfile
import shutil
from pathlib import Path
from unittest import TestCase, main

# Add hooks directory to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from state_utils import (
    is_objective_text,
    extract_objective_text,
    set_new_objective,
    load_yaml_state,
    get_project_dir,
)


class TestIsObjectiveText(TestCase):
    """Tests for is_objective_text()."""

    def test_quoted_string_is_objective(self):
        self.assertTrue(is_objective_text('"Deploy authentication"'))
        self.assertTrue(is_objective_text("'Add dark mode'"))

    def test_commands_are_not_objectives(self):
        commands = ['status', 'approve', 'skip', 'dismiss', 'on', 'off', 'stop',
                    'plan', 'active', 'review', 'done']
        for cmd in commands:
            self.assertFalse(is_objective_text(cmd), f"{cmd} should not be objective")

    def test_flags_are_not_objectives(self):
        self.assertFalse(is_objective_text('--plan'))
        self.assertFalse(is_objective_text('--verify'))
        self.assertFalse(is_objective_text('--auto'))

    def test_multi_word_is_objective(self):
        self.assertTrue(is_objective_text('Add dark mode toggle'))
        self.assertTrue(is_objective_text('Refactor the login flow'))
        self.assertTrue(is_objective_text('Deploy new authentication system'))

    def test_empty_is_not_objective(self):
        self.assertFalse(is_objective_text(''))
        self.assertFalse(is_objective_text('   '))
        self.assertFalse(is_objective_text(None))


class TestExtractObjectiveText(TestCase):
    """Tests for extract_objective_text()."""

    def test_removes_double_quotes(self):
        self.assertEqual(
            extract_objective_text('"Deploy auth system"'),
            'Deploy auth system'
        )

    def test_removes_single_quotes(self):
        self.assertEqual(
            extract_objective_text("'Add dark mode'"),
            'Add dark mode'
        )

    def test_strips_whitespace(self):
        self.assertEqual(
            extract_objective_text('  Add feature  '),
            'Add feature'
        )

    def test_unquoted_passes_through(self):
        self.assertEqual(
            extract_objective_text('Add dark mode toggle'),
            'Add dark mode toggle'
        )


class TestSetNewObjective(TestCase):
    """Tests for set_new_objective()."""

    def setUp(self):
        """Create a temp directory with a valid active_context.yaml."""
        self.temp_dir = tempfile.mkdtemp()
        self.yaml_content = '''# Operator's Edge - Active Context
session:
  id: "test-session"
  started_at: "2026-01-17T00:00:00"
mode: "active"

intent:
  user_wants: "Old objective"
  success_looks_like: "Old criteria"
  confirmed: true
  confirmed_at: "2026-01-17T00:00:00"

objective: "Old objective"

current_step: 5

plan:
  - description: "Step 1"
    status: "completed"
    proof: "Done"
  - description: "Step 2"
    status: "in_progress"
    proof: ""

constraints:
  - "No breaking changes"

memory:
  - trigger: "test"
    lesson: "Test lesson"
'''
        yaml_path = Path(self.temp_dir) / 'active_context.yaml'
        yaml_path.write_text(self.yaml_content)

        # Monkey-patch get_project_dir
        import state_utils
        self._original_get_project_dir = state_utils.get_project_dir
        state_utils.get_project_dir = lambda: Path(self.temp_dir)

    def tearDown(self):
        """Clean up temp directory and restore get_project_dir."""
        import state_utils
        state_utils.get_project_dir = self._original_get_project_dir
        shutil.rmtree(self.temp_dir)

    def test_sets_objective(self):
        success, msg = set_new_objective("New objective")
        self.assertTrue(success)

        state = load_yaml_state()
        self.assertEqual(state['objective'], 'New objective')

    def test_clears_plan(self):
        success, msg = set_new_objective("New objective", clear_plan=True)
        self.assertTrue(success)

        state = load_yaml_state()
        self.assertEqual(state['plan'], [])

    def test_resets_current_step(self):
        success, msg = set_new_objective("New objective")
        self.assertTrue(success)

        state = load_yaml_state()
        self.assertEqual(state['current_step'], 0)

    def test_sets_mode_to_plan(self):
        success, msg = set_new_objective("New objective")
        self.assertTrue(success)

        state = load_yaml_state()
        self.assertEqual(state['mode'], 'plan')

    def test_updates_intent_user_wants(self):
        success, msg = set_new_objective("New objective")
        self.assertTrue(success)

        state = load_yaml_state()
        self.assertEqual(state['intent']['user_wants'], 'New objective')

    def test_resets_intent_confirmed(self):
        success, msg = set_new_objective("New objective")
        self.assertTrue(success)

        state = load_yaml_state()
        self.assertFalse(state['intent']['confirmed'])

    def test_preserves_other_sections(self):
        success, msg = set_new_objective("New objective")
        self.assertTrue(success)

        state = load_yaml_state()
        # Memory and constraints should be preserved
        self.assertIn('memory', state)
        self.assertIn('constraints', state)

    def test_returns_error_for_missing_file(self):
        # Remove the file
        (Path(self.temp_dir) / 'active_context.yaml').unlink()

        success, msg = set_new_objective("New objective")
        self.assertFalse(success)
        self.assertIn('not found', msg.lower())


class TestParseEdgeArgs(TestCase):
    """Tests for parse_edge_args in edge_skill_hook."""

    def test_objective_routed_to_run(self):
        from edge_skill_hook import parse_edge_args

        result = parse_edge_args('/edge "Deploy auth"')
        self.assertEqual(result['command'], 'run')
        self.assertEqual(result['args'], '"Deploy auth"')

    def test_unquoted_objective_routed_to_run(self):
        from edge_skill_hook import parse_edge_args

        result = parse_edge_args('/edge Add dark mode toggle')
        self.assertEqual(result['command'], 'run')
        self.assertEqual(result['args'], 'Add dark mode toggle')


if __name__ == '__main__':
    main()
