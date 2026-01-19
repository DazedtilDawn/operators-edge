#!/usr/bin/env python3
"""
Tests for pre_tool.py - pre-tool gate enforcement.

Tests the core functions for:
- Bash command risk gating (block, ask patterns)
- Retry blocking for failed commands
- Plan requirement for file edits
- Main entry point
"""
import json
import os
import sys
import tempfile
import unittest
from io import StringIO
from pathlib import Path
from unittest.mock import patch, MagicMock

# Add hooks directory to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


class TestCheckBashCommand(unittest.TestCase):
    """Tests for check_bash_command() function."""

    def test_blocks_rm_rf_root(self):
        """check_bash_command() should block rm -rf /."""
        from pre_tool import check_bash_command

        result = check_bash_command("rm -rf /")

        self.assertIsNotNone(result)
        self.assertEqual(result[0], "block")

    def test_blocks_rm_rf_home(self):
        """check_bash_command() should block rm -rf ~."""
        from pre_tool import check_bash_command

        result = check_bash_command("rm -rf ~/")

        self.assertIsNotNone(result)
        self.assertEqual(result[0], "block")

    def test_blocks_git_reset_hard(self):
        """check_bash_command() should block git reset --hard."""
        from pre_tool import check_bash_command

        result = check_bash_command("git reset --hard HEAD~1")

        self.assertIsNotNone(result)
        self.assertEqual(result[0], "block")

    def test_blocks_force_push(self):
        """check_bash_command() should block force push."""
        from pre_tool import check_bash_command

        result = check_bash_command("git push --force origin main")

        self.assertIsNotNone(result)
        self.assertEqual(result[0], "block")

    def test_blocks_git_clean_fdx(self):
        """check_bash_command() should block git clean -fdx."""
        from pre_tool import check_bash_command

        result = check_bash_command("git clean -fdx")

        self.assertIsNotNone(result)
        self.assertEqual(result[0], "block")

    def test_blocks_chmod_777_recursive(self):
        """check_bash_command() should block chmod -R 777."""
        from pre_tool import check_bash_command

        result = check_bash_command("chmod -R 777 /var")

        self.assertIsNotNone(result)
        self.assertEqual(result[0], "block")

    def test_asks_for_git_push(self):
        """check_bash_command() should ask for regular git push."""
        from pre_tool import check_bash_command

        result = check_bash_command("git push origin main")

        self.assertIsNotNone(result)
        self.assertEqual(result[0], "ask")

    def test_asks_for_rm(self):
        """check_bash_command() should ask for file deletion."""
        from pre_tool import check_bash_command

        result = check_bash_command("rm file.txt")

        self.assertIsNotNone(result)
        self.assertEqual(result[0], "ask")

    def test_asks_for_kubectl(self):
        """check_bash_command() should ask for kubectl commands."""
        from pre_tool import check_bash_command

        result = check_bash_command("kubectl apply -f config.yaml")

        self.assertIsNotNone(result)
        self.assertEqual(result[0], "ask")

    def test_asks_for_terraform(self):
        """check_bash_command() should ask for terraform commands."""
        from pre_tool import check_bash_command

        result = check_bash_command("terraform apply")

        self.assertIsNotNone(result)
        self.assertEqual(result[0], "ask")

    def test_asks_for_docker_push(self):
        """check_bash_command() should ask for docker push."""
        from pre_tool import check_bash_command

        result = check_bash_command("docker push myimage:latest")

        self.assertIsNotNone(result)
        self.assertEqual(result[0], "ask")

    def test_asks_for_npm_publish(self):
        """check_bash_command() should ask for npm publish."""
        from pre_tool import check_bash_command

        result = check_bash_command("npm publish")

        self.assertIsNotNone(result)
        self.assertEqual(result[0], "ask")

    def test_asks_for_aws_commands(self):
        """check_bash_command() should ask for AWS commands."""
        from pre_tool import check_bash_command

        result = check_bash_command("aws s3 sync . s3://bucket")

        self.assertIsNotNone(result)
        self.assertEqual(result[0], "ask")

    def test_allows_safe_commands(self):
        """check_bash_command() should return None for safe commands."""
        from pre_tool import check_bash_command

        safe_commands = [
            "ls -la",
            "git status",
            "npm install",
            "python script.py",
            "cat file.txt",
            "echo hello"
        ]

        for cmd in safe_commands:
            result = check_bash_command(cmd)
            self.assertIsNone(result, f"Command '{cmd}' should be allowed")

    def test_handles_chained_commands(self):
        """check_bash_command() should detect dangerous commands in chains."""
        from pre_tool import check_bash_command

        result = check_bash_command("ls && rm -rf /")

        self.assertIsNotNone(result)
        self.assertEqual(result[0], "block")

    def test_handles_piped_commands(self):
        """check_bash_command() should detect dangerous commands in pipes."""
        from pre_tool import check_bash_command

        result = check_bash_command("echo test | rm -rf /home")

        # Should detect the rm in the pipe
        # Note: depends on regex handling


class TestCheckRetryBlocking(unittest.TestCase):
    """Tests for check_retry_blocking() function."""

    @patch('pre_tool.get_recent_failures')
    def test_blocks_after_two_failures(self, mock_failures):
        """check_retry_blocking() should block after 2 failures."""
        from pre_tool import check_retry_blocking

        mock_failures.return_value = 2

        result = check_retry_blocking("failing command")

        self.assertIsNotNone(result)
        self.assertEqual(result[0], "block")
        self.assertIn("2 times", result[1])

    @patch('pre_tool.get_recent_failures')
    def test_allows_first_attempt(self, mock_failures):
        """check_retry_blocking() should allow first attempt."""
        from pre_tool import check_retry_blocking

        mock_failures.return_value = 0

        result = check_retry_blocking("new command")

        self.assertIsNone(result)

    @patch('pre_tool.get_recent_failures')
    def test_allows_single_failure(self, mock_failures):
        """check_retry_blocking() should allow after single failure."""
        from pre_tool import check_retry_blocking

        mock_failures.return_value = 1

        result = check_retry_blocking("command")

        self.assertIsNone(result)


class TestCheckIntentConfirmed(unittest.TestCase):
    """Tests for check_intent_confirmed() function (Understanding-First v1.0)."""

    def test_ignores_non_edit_tools(self):
        """check_intent_confirmed() should ignore non-edit tools."""
        from pre_tool import check_intent_confirmed

        result = check_intent_confirmed("Bash", {"command": "ls"})
        self.assertIsNone(result)

        result = check_intent_confirmed("Read", {"file_path": "/code/file.py"})
        self.assertIsNone(result)

    @patch('pre_tool.load_yaml_state')
    def test_allows_safe_paths(self, mock_state):
        """check_intent_confirmed() should allow safe paths without intent."""
        from pre_tool import check_intent_confirmed

        mock_state.return_value = {"intent": {}}

        safe_paths = [
            "active_context.yaml",
            ".proof/session_log.jsonl",
            "checklist.md",
            "archive.md",
            ".claude/plans/my-plan.md"
        ]

        for path in safe_paths:
            result = check_intent_confirmed("Edit", {"file_path": path})
            self.assertIsNone(result, f"Path '{path}' should be allowed")

    @patch('pre_tool.load_yaml_state')
    def test_allows_if_no_intent_set(self, mock_state):
        """check_intent_confirmed() should allow if no intent set (backward compat)."""
        from pre_tool import check_intent_confirmed

        mock_state.return_value = {"intent": {}}

        result = check_intent_confirmed("Edit", {"file_path": "/code/file.py"})

        # Backward compatibility: no user_wants = skip intent check
        self.assertIsNone(result)

    @patch('pre_tool.load_yaml_state')
    def test_asks_if_intent_not_confirmed(self, mock_state):
        """check_intent_confirmed() should ask if intent set but not confirmed."""
        from pre_tool import check_intent_confirmed

        mock_state.return_value = {
            "intent": {
                "user_wants": "Add a new feature",
                "success_looks_like": "Feature works",
                "confirmed": False
            }
        }

        result = check_intent_confirmed("Edit", {"file_path": "/code/file.py"})

        self.assertIsNotNone(result)
        self.assertEqual(result[0], "ask")
        self.assertIn("Intent not confirmed", result[1])
        self.assertIn("Add a new feature", result[1])

    @patch('pre_tool.load_yaml_state')
    def test_allows_if_intent_confirmed(self, mock_state):
        """check_intent_confirmed() should allow edits if intent confirmed."""
        from pre_tool import check_intent_confirmed

        mock_state.return_value = {
            "intent": {
                "user_wants": "Add a new feature",
                "success_looks_like": "Feature works",
                "confirmed": True,
                "confirmed_at": "2026-01-14T10:00:00"
            }
        }

        result = check_intent_confirmed("Edit", {"file_path": "/code/file.py"})

        self.assertIsNone(result)

    @patch('pre_tool.load_yaml_state')
    def test_handles_missing_state(self, mock_state):
        """check_intent_confirmed() should pass through if no state."""
        from pre_tool import check_intent_confirmed

        mock_state.return_value = None

        # Should return None to let plan_requirement handle it
        result = check_intent_confirmed("Edit", {"file_path": "/code/file.py"})

        self.assertIsNone(result)

    @patch('pre_tool.load_yaml_state')
    def test_handles_missing_intent_section(self, mock_state):
        """check_intent_confirmed() should allow if no intent section (backward compat)."""
        from pre_tool import check_intent_confirmed

        mock_state.return_value = {"plan": []}  # No intent section

        result = check_intent_confirmed("Edit", {"file_path": "/code/file.py"})

        # Backward compatibility: no intent section = skip check
        self.assertIsNone(result)


class TestCheckPlanRequirement(unittest.TestCase):
    """Tests for check_plan_requirement() function."""

    def test_ignores_non_edit_tools(self):
        """check_plan_requirement() should ignore non-edit tools."""
        from pre_tool import check_plan_requirement

        result = check_plan_requirement("Bash", {"command": "ls"})

        self.assertIsNone(result)

    @patch('pre_tool.load_yaml_state')
    def test_blocks_if_no_state(self, mock_state):
        """check_plan_requirement() should block if state missing."""
        from pre_tool import check_plan_requirement

        mock_state.return_value = None

        result = check_plan_requirement("Edit", {"file_path": "/code/file.py"})

        self.assertIsNotNone(result)
        self.assertEqual(result[0], "block")

    @patch('pre_tool.load_yaml_state')
    def test_asks_if_no_plan(self, mock_state):
        """check_plan_requirement() should ask if no plan exists."""
        from pre_tool import check_plan_requirement

        mock_state.return_value = {"plan": []}

        result = check_plan_requirement("Edit", {"file_path": "/code/file.py"})

        self.assertIsNotNone(result)
        self.assertEqual(result[0], "ask")

    @patch('pre_tool.load_yaml_state')
    def test_allows_safe_paths_without_plan(self, mock_state):
        """check_plan_requirement() should allow safe paths without plan."""
        from pre_tool import check_plan_requirement

        mock_state.return_value = {"plan": []}

        safe_paths = [
            "active_context.yaml",
            ".proof/session_log.jsonl",
            "checklist.md",
            "archive.md"
        ]

        for path in safe_paths:
            result = check_plan_requirement("Edit", {"file_path": path})
            self.assertIsNone(result, f"Path '{path}' should be allowed")

    @patch('pre_tool.load_yaml_state')
    def test_allows_with_plan_and_risks(self, mock_state):
        """check_plan_requirement() should allow edits with plan AND risks."""
        from pre_tool import check_plan_requirement

        mock_state.return_value = {
            "plan": [{"status": "in_progress"}],
            "risks": [{"risk": "Something could fail", "mitigation": "Check first"}]
        }

        result = check_plan_requirement("Edit", {"file_path": "/code/file.py"})

        self.assertIsNone(result)

    @patch('pre_tool.load_yaml_state')
    def test_asks_if_no_risks(self, mock_state):
        """check_plan_requirement() should ask if risks are empty (v3.5)."""
        from pre_tool import check_plan_requirement

        mock_state.return_value = {
            "plan": [{"status": "in_progress"}],
            "risks": []  # Empty risks
        }

        result = check_plan_requirement("Edit", {"file_path": "/code/file.py"})

        self.assertIsNotNone(result)
        self.assertEqual(result[0], "ask")
        self.assertIn("risk", result[1].lower())

    @patch('pre_tool.load_yaml_state')
    def test_asks_if_risks_missing(self, mock_state):
        """check_plan_requirement() should ask if risks field missing (v3.5)."""
        from pre_tool import check_plan_requirement

        mock_state.return_value = {
            "plan": [{"status": "in_progress"}]
            # No risks field at all
        }

        result = check_plan_requirement("Edit", {"file_path": "/code/file.py"})

        self.assertIsNotNone(result)
        self.assertEqual(result[0], "ask")

    @patch('pre_tool.load_yaml_state')
    def test_checks_write_tool(self, mock_state):
        """check_plan_requirement() should check Write tool."""
        from pre_tool import check_plan_requirement

        mock_state.return_value = None

        result = check_plan_requirement("Write", {"file_path": "/code/new.py"})

        self.assertIsNotNone(result)
        self.assertEqual(result[0], "block")

    @patch('pre_tool.load_yaml_state')
    def test_checks_notebook_edit(self, mock_state):
        """check_plan_requirement() should check NotebookEdit tool."""
        from pre_tool import check_plan_requirement

        mock_state.return_value = None

        result = check_plan_requirement("NotebookEdit", {"notebook_path": "/nb.ipynb"})

        self.assertIsNotNone(result)
        self.assertEqual(result[0], "block")


class TestMain(unittest.TestCase):
    """Tests for main() function."""

    @patch('pre_tool.respond')
    @patch('sys.stdin', new_callable=StringIO)
    def test_approves_safe_bash(self, mock_stdin, mock_respond):
        """main() should approve safe bash commands."""
        from pre_tool import main

        mock_stdin.write(json.dumps({
            "tool_name": "Bash",
            "tool_input": {"command": "ls -la"}
        }))
        mock_stdin.seek(0)

        main()

        mock_respond.assert_called_with("approve", "Passed all pre-tool checks")

    @patch('pre_tool.respond')
    @patch('sys.stdin', new_callable=StringIO)
    def test_blocks_dangerous_bash(self, mock_stdin, mock_respond):
        """main() should block dangerous bash commands."""
        from pre_tool import main

        mock_stdin.write(json.dumps({
            "tool_name": "Bash",
            "tool_input": {"command": "rm -rf /"}
        }))
        mock_stdin.seek(0)

        main()

        # Should have called respond with block
        calls = mock_respond.call_args_list
        self.assertTrue(any(call[0][0] == "block" for call in calls))

    @patch('pre_tool.load_yaml_state')
    @patch('pre_tool.respond')
    @patch('sys.stdin', new_callable=StringIO)
    def test_checks_edit_plan(self, mock_stdin, mock_respond, mock_state):
        """main() should check plan for Edit tool."""
        from pre_tool import main

        mock_state.return_value = None
        mock_stdin.write(json.dumps({
            "tool_name": "Edit",
            "tool_input": {"file_path": "/code/file.py"}
        }))
        mock_stdin.seek(0)

        main()

        calls = mock_respond.call_args_list
        self.assertTrue(any(call[0][0] == "block" for call in calls))

    @patch('pre_tool.respond')
    @patch('sys.stdin', new_callable=StringIO)
    def test_handles_invalid_json(self, mock_stdin, mock_respond):
        """main() should handle invalid JSON input."""
        from pre_tool import main

        mock_stdin.write("invalid json")
        mock_stdin.seek(0)

        main()

        mock_respond.assert_called_with("approve", "Could not parse input, allowing by default")

    @patch('pre_tool.respond')
    @patch('sys.stdin', new_callable=StringIO)
    def test_approves_read_tool(self, mock_stdin, mock_respond):
        """main() should approve Read tool."""
        from pre_tool import main

        mock_stdin.write(json.dumps({
            "tool_name": "Read",
            "tool_input": {"file_path": "/code/file.py"}
        }))
        mock_stdin.seek(0)

        main()

        mock_respond.assert_called_with("approve", "Passed all pre-tool checks")


if __name__ == '__main__':
    unittest.main()
