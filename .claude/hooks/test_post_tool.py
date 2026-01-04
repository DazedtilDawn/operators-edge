#!/usr/bin/env python3
"""
Tests for post_tool.py - post-tool proof capture hook.

Tests the main() function that processes tool execution results
and logs proof artifacts for different tool types.
"""
import json
import io
import os
import sys
import unittest
from unittest.mock import patch, MagicMock

# Add hooks directory to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


class TestPostToolMain(unittest.TestCase):
    """Tests for the main() function in post_tool.py."""

    @patch('post_tool.log_proof')
    @patch('post_tool.log_failure')
    def test_bash_success_logs_proof(self, mock_log_failure, mock_log_proof):
        """Successful Bash command should log proof with success=True."""
        from post_tool import main

        data = {
            "tool_name": "Bash",
            "tool_input": {"command": "ls -la"},
            "tool_result": {
                "exit_code": 0,
                "stdout": "file1.txt\nfile2.txt",
                "stderr": ""
            }
        }

        with patch('sys.stdin', io.StringIO(json.dumps(data))):
            main()

        mock_log_proof.assert_called_once()
        call_args = mock_log_proof.call_args
        self.assertEqual(call_args[0][0], "Bash")
        self.assertTrue(call_args[0][3])  # success=True
        mock_log_failure.assert_not_called()

    @patch('post_tool.log_proof')
    @patch('post_tool.log_failure')
    def test_bash_failure_logs_failure(self, mock_log_failure, mock_log_proof):
        """Failed Bash command should log both proof and failure."""
        from post_tool import main

        data = {
            "tool_name": "Bash",
            "tool_input": {"command": "invalid_command"},
            "tool_result": {
                "exit_code": 1,
                "stdout": "",
                "stderr": "command not found"
            }
        }

        with patch('sys.stdin', io.StringIO(json.dumps(data))):
            main()

        # Should log proof with success=False
        mock_log_proof.assert_called_once()
        self.assertFalse(mock_log_proof.call_args[0][3])  # success=False

        # Should also log failure for retry blocking
        mock_log_failure.assert_called_once()
        self.assertIn("invalid_command", mock_log_failure.call_args[0][0])

    @patch('post_tool.log_proof')
    def test_edit_logs_file_change(self, mock_log_proof):
        """Edit tool should log file modification."""
        from post_tool import main

        data = {
            "tool_name": "Edit",
            "tool_input": {"file_path": "/path/to/file.py"},
            "tool_result": {"success": True}
        }

        with patch('sys.stdin', io.StringIO(json.dumps(data))):
            main()

        mock_log_proof.assert_called_once()
        call_args = mock_log_proof.call_args
        self.assertEqual(call_args[0][0], "Edit")
        self.assertIn("file.py", call_args[0][2])

    @patch('post_tool.log_proof')
    def test_write_logs_file_change(self, mock_log_proof):
        """Write tool should log file modification."""
        from post_tool import main

        data = {
            "tool_name": "Write",
            "tool_input": {"file_path": "/path/to/new_file.py"},
            "tool_result": {"success": True}
        }

        with patch('sys.stdin', io.StringIO(json.dumps(data))):
            main()

        mock_log_proof.assert_called_once()
        self.assertEqual(mock_log_proof.call_args[0][0], "Write")

    @patch('post_tool.log_proof')
    def test_notebook_edit_logs_file_change(self, mock_log_proof):
        """NotebookEdit tool should log file modification."""
        from post_tool import main

        data = {
            "tool_name": "NotebookEdit",
            "tool_input": {"file_path": "/path/to/notebook.ipynb"},
            "tool_result": {"success": True}
        }

        with patch('sys.stdin', io.StringIO(json.dumps(data))):
            main()

        mock_log_proof.assert_called_once()
        self.assertEqual(mock_log_proof.call_args[0][0], "NotebookEdit")

    @patch('post_tool.log_proof')
    def test_read_logs_lightweight(self, mock_log_proof):
        """Read tool should log lightweight proof."""
        from post_tool import main

        data = {
            "tool_name": "Read",
            "tool_input": {"file_path": "/path/to/file.py"},
            "tool_result": {"content": "file contents here"}
        }

        with patch('sys.stdin', io.StringIO(json.dumps(data))):
            main()

        mock_log_proof.assert_called_once()
        call_args = mock_log_proof.call_args
        self.assertEqual(call_args[0][0], "Read")
        self.assertEqual(call_args[0][2], "Read file")
        self.assertTrue(call_args[0][3])  # success=True

    @patch('post_tool.log_proof')
    def test_generic_tool_logs(self, mock_log_proof):
        """Unknown tools should get generic logging."""
        from post_tool import main

        data = {
            "tool_name": "SomeNewTool",
            "tool_input": {"param": "value"},
            "tool_result": {"output": "result"}
        }

        with patch('sys.stdin', io.StringIO(json.dumps(data))):
            main()

        mock_log_proof.assert_called_once()
        self.assertEqual(mock_log_proof.call_args[0][0], "SomeNewTool")

    @patch('post_tool.log_proof')
    def test_handles_json_decode_error(self, mock_log_proof):
        """Invalid JSON should not crash, just return."""
        from post_tool import main

        with patch('sys.stdin', io.StringIO("not valid json")):
            main()  # Should not raise

        mock_log_proof.assert_not_called()

    @patch('post_tool.log_proof')
    def test_handles_missing_tool_input(self, mock_log_proof):
        """Missing tool_input should not crash."""
        from post_tool import main

        data = {
            "tool_name": "Bash",
            "tool_result": {"exit_code": 0, "stdout": "ok"}
        }

        with patch('sys.stdin', io.StringIO(json.dumps(data))):
            main()  # Should not raise

        mock_log_proof.assert_called_once()

    @patch('post_tool.log_proof')
    def test_handles_missing_tool_result(self, mock_log_proof):
        """Missing tool_result should not crash."""
        from post_tool import main

        data = {
            "tool_name": "Read",
            "tool_input": {"file_path": "/some/path"}
        }

        with patch('sys.stdin', io.StringIO(json.dumps(data))):
            main()  # Should not raise

        mock_log_proof.assert_called_once()

    @patch('post_tool.log_proof')
    @patch('post_tool.log_failure')
    def test_bash_stderr_used_for_error_msg(self, mock_log_failure, mock_log_proof):
        """Bash failure should use stderr for error message."""
        from post_tool import main

        data = {
            "tool_name": "Bash",
            "tool_input": {"command": "bad_cmd"},
            "tool_result": {
                "exit_code": 127,
                "stdout": "",
                "stderr": "bash: bad_cmd: command not found"
            }
        }

        with patch('sys.stdin', io.StringIO(json.dumps(data))):
            main()

        mock_log_failure.assert_called_once()
        error_msg = mock_log_failure.call_args[0][1]
        self.assertIn("command not found", error_msg)

    @patch('post_tool.log_proof')
    def test_long_output_truncated(self, mock_log_proof):
        """Long stdout should be truncated to 500 chars."""
        from post_tool import main

        long_output = "x" * 1000
        data = {
            "tool_name": "Bash",
            "tool_input": {"command": "echo"},
            "tool_result": {
                "exit_code": 0,
                "stdout": long_output,
                "stderr": ""
            }
        }

        with patch('sys.stdin', io.StringIO(json.dumps(data))):
            main()

        call_args = mock_log_proof.call_args
        result_preview = call_args[0][2]
        self.assertEqual(len(result_preview), 500)


class TestIsGitCommitCommand(unittest.TestCase):
    """Tests for is_git_commit_command()."""

    def test_detects_simple_commit(self):
        """Should detect 'git commit -m'."""
        from post_tool import is_git_commit_command
        self.assertTrue(is_git_commit_command("git commit -m 'test'"))

    def test_detects_commit_with_flags(self):
        """Should detect git commit with various flags."""
        from post_tool import is_git_commit_command
        self.assertTrue(is_git_commit_command("git commit --all -m 'test'"))
        self.assertTrue(is_git_commit_command("git commit -a -m 'test'"))

    def test_detects_commit_in_chain(self):
        """Should detect git commit in command chain."""
        from post_tool import is_git_commit_command
        self.assertTrue(is_git_commit_command("git add . && git commit -m 'test'"))

    def test_ignores_non_commit(self):
        """Should not match non-commit git commands."""
        from post_tool import is_git_commit_command
        self.assertFalse(is_git_commit_command("git status"))
        self.assertFalse(is_git_commit_command("git push"))
        self.assertFalse(is_git_commit_command("git log --oneline"))

    def test_ignores_empty(self):
        """Should handle empty/None input."""
        from post_tool import is_git_commit_command
        self.assertFalse(is_git_commit_command(""))
        self.assertFalse(is_git_commit_command(None))


class TestRunTestsAfterCommit(unittest.TestCase):
    """Tests for run_tests_after_commit()."""

    @patch('post_tool.subprocess.run')
    def test_returns_success_on_passing_tests(self, mock_run):
        """Should return success when tests pass."""
        from post_tool import run_tests_after_commit

        mock_run.return_value = MagicMock(
            returncode=0,
            stderr="Ran 50 tests in 0.5s\n\nOK",
            stdout=""
        )

        success, summary = run_tests_after_commit()
        self.assertTrue(success)
        self.assertIn("50", summary)
        self.assertIn("passed", summary)

    @patch('post_tool.subprocess.run')
    def test_returns_failure_on_test_failure(self, mock_run):
        """Should return failure when tests fail."""
        from post_tool import run_tests_after_commit

        mock_run.return_value = MagicMock(
            returncode=1,
            stderr="FAIL: test_something\nRan 10 tests in 0.3s\n\nFAILED",
            stdout=""
        )

        success, summary = run_tests_after_commit()
        self.assertFalse(success)
        self.assertIn("failed", summary)

    @patch('post_tool.subprocess.run')
    def test_handles_timeout(self, mock_run):
        """Should handle test timeout gracefully."""
        import subprocess
        from post_tool import run_tests_after_commit

        mock_run.side_effect = subprocess.TimeoutExpired("cmd", 120)

        success, summary = run_tests_after_commit()
        self.assertFalse(success)
        self.assertIn("timed out", summary)

    @patch('post_tool.subprocess.run')
    def test_handles_exception(self, mock_run):
        """Should handle unexpected exceptions."""
        from post_tool import run_tests_after_commit

        mock_run.side_effect = Exception("Something went wrong")

        success, summary = run_tests_after_commit()
        self.assertFalse(success)
        self.assertIn("Could not run tests", summary)


class TestPostCommitIntegration(unittest.TestCase):
    """Integration tests for post-commit test runner."""

    @patch('post_tool.run_tests_after_commit')
    @patch('post_tool.log_proof')
    def test_runs_tests_after_git_commit(self, mock_log_proof, mock_run_tests):
        """Should run tests after successful git commit."""
        from post_tool import main

        mock_run_tests.return_value = (True, "50 tests passed")

        data = {
            "tool_name": "Bash",
            "tool_input": {"command": "git commit -m 'test'"},
            "tool_result": {
                "exit_code": 0,
                "stdout": "[main abc123] test\n 1 file changed",
                "stderr": ""
            }
        }

        with patch('sys.stdin', io.StringIO(json.dumps(data))):
            main()

        mock_run_tests.assert_called_once()

    @patch('post_tool.run_tests_after_commit')
    @patch('post_tool.log_proof')
    def test_skips_tests_for_non_commit(self, mock_log_proof, mock_run_tests):
        """Should not run tests for non-commit commands."""
        from post_tool import main

        data = {
            "tool_name": "Bash",
            "tool_input": {"command": "git status"},
            "tool_result": {
                "exit_code": 0,
                "stdout": "nothing to commit",
                "stderr": ""
            }
        }

        with patch('sys.stdin', io.StringIO(json.dumps(data))):
            main()

        mock_run_tests.assert_not_called()


if __name__ == '__main__':
    unittest.main()
