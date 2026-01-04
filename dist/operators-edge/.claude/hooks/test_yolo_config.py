#!/usr/bin/env python3
"""
Tests for yolo_config.py

Coverage:
- TrustLevel: Enum for trust levels
- AUTO_TOOLS: Read-only tools set
- SUPERVISED_TOOLS: State-modifying tools set
- COMMAND_CLASSIFIED_TOOLS: Tools needing command-level classification
- AUTO_BASH_PATTERNS: Read-only bash patterns
- SUPERVISED_BASH_PATTERNS: State-modifying bash patterns
- BLOCKED_BASH_PATTERNS: Always-blocked patterns
- CONFIRM_BASH_PATTERNS: External-effect patterns
- BATCH_DEFAULTS: Batch settings
- YOLO_STATE_FILE: State file path
- YOLO_CONFIG_FILE: Config file path
- classify_bash_command: Bash command classification
- classify_action: Full action classification
- is_hard_blocked: Hard block detection
- get_default_yolo_state: Default state structure
- get_default_yolo_config: Default config structure
"""

import unittest

import yolo_config
from yolo_config import (
    TrustLevel,
    AUTO_TOOLS, SUPERVISED_TOOLS, COMMAND_CLASSIFIED_TOOLS,
    AUTO_BASH_PATTERNS, SUPERVISED_BASH_PATTERNS,
    BLOCKED_BASH_PATTERNS, CONFIRM_BASH_PATTERNS,
    BATCH_DEFAULTS, YOLO_STATE_FILE, YOLO_CONFIG_FILE,
    classify_bash_command, classify_action, is_hard_blocked,
    get_default_yolo_state, get_default_yolo_config
)


class TestTrustLevelEnum(unittest.TestCase):
    """Tests for TrustLevel enum."""

    def test_has_auto(self):
        """TrustLevel should have AUTO."""
        self.assertEqual(TrustLevel.AUTO.value, "auto")

    def test_has_supervised(self):
        """TrustLevel should have SUPERVISED."""
        self.assertEqual(TrustLevel.SUPERVISED.value, "supervised")

    def test_has_blocked(self):
        """TrustLevel should have BLOCKED."""
        self.assertEqual(TrustLevel.BLOCKED.value, "blocked")


class TestToolSets(unittest.TestCase):
    """Tests for tool categorization sets."""

    def test_auto_tools_is_frozenset(self):
        """AUTO_TOOLS should be a frozenset."""
        self.assertIsInstance(AUTO_TOOLS, frozenset)

    def test_auto_tools_has_read(self):
        """AUTO_TOOLS should include Read."""
        self.assertIn("Read", AUTO_TOOLS)

    def test_auto_tools_has_glob(self):
        """AUTO_TOOLS should include Glob."""
        self.assertIn("Glob", AUTO_TOOLS)

    def test_auto_tools_has_grep(self):
        """AUTO_TOOLS should include Grep."""
        self.assertIn("Grep", AUTO_TOOLS)

    def test_auto_tools_has_webfetch(self):
        """AUTO_TOOLS should include WebFetch."""
        self.assertIn("WebFetch", AUTO_TOOLS)

    def test_auto_tools_has_websearch(self):
        """AUTO_TOOLS should include WebSearch."""
        self.assertIn("WebSearch", AUTO_TOOLS)

    def test_auto_tools_has_task(self):
        """AUTO_TOOLS should include Task."""
        self.assertIn("Task", AUTO_TOOLS)

    def test_supervised_tools_is_frozenset(self):
        """SUPERVISED_TOOLS should be a frozenset."""
        self.assertIsInstance(SUPERVISED_TOOLS, frozenset)

    def test_supervised_tools_has_edit(self):
        """SUPERVISED_TOOLS should include Edit."""
        self.assertIn("Edit", SUPERVISED_TOOLS)

    def test_supervised_tools_has_write(self):
        """SUPERVISED_TOOLS should include Write."""
        self.assertIn("Write", SUPERVISED_TOOLS)

    def test_supervised_tools_has_notebookedit(self):
        """SUPERVISED_TOOLS should include NotebookEdit."""
        self.assertIn("NotebookEdit", SUPERVISED_TOOLS)

    def test_command_classified_has_bash(self):
        """COMMAND_CLASSIFIED_TOOLS should include Bash."""
        self.assertIn("Bash", COMMAND_CLASSIFIED_TOOLS)

    def test_no_overlap_auto_supervised(self):
        """AUTO_TOOLS and SUPERVISED_TOOLS should not overlap."""
        overlap = AUTO_TOOLS & SUPERVISED_TOOLS
        self.assertEqual(overlap, frozenset())


class TestBashPatterns(unittest.TestCase):
    """Tests for bash pattern lists."""

    def test_auto_patterns_is_list(self):
        """AUTO_BASH_PATTERNS should be a list."""
        self.assertIsInstance(AUTO_BASH_PATTERNS, list)

    def test_auto_patterns_has_git_status(self):
        """Should include git status pattern."""
        self.assertTrue(any("git" in p and "status" in p for p in AUTO_BASH_PATTERNS))

    def test_auto_patterns_has_ls(self):
        """Should include ls command."""
        self.assertTrue(any("ls" in p for p in AUTO_BASH_PATTERNS))

    def test_supervised_patterns_is_list(self):
        """SUPERVISED_BASH_PATTERNS should be a list."""
        self.assertIsInstance(SUPERVISED_BASH_PATTERNS, list)

    def test_supervised_patterns_has_git_add(self):
        """Should include git add pattern."""
        self.assertTrue(any("git" in p and "add" in p for p in SUPERVISED_BASH_PATTERNS))

    def test_supervised_patterns_has_mkdir(self):
        """Should include mkdir command."""
        self.assertTrue(any("mkdir" in p for p in SUPERVISED_BASH_PATTERNS))

    def test_blocked_patterns_is_list(self):
        """BLOCKED_BASH_PATTERNS should be a list."""
        self.assertIsInstance(BLOCKED_BASH_PATTERNS, list)

    def test_blocked_patterns_has_rm_rf(self):
        """Should include rm -rf pattern."""
        self.assertTrue(any("rm" in p and "-rf" in p for p in BLOCKED_BASH_PATTERNS))

    def test_blocked_patterns_has_git_reset_hard(self):
        """Should include git reset --hard pattern."""
        self.assertTrue(any("reset" in p and "hard" in p for p in BLOCKED_BASH_PATTERNS))

    def test_blocked_patterns_has_force_push(self):
        """Should include git push --force pattern."""
        self.assertTrue(any("push" in p and "force" in p for p in BLOCKED_BASH_PATTERNS))

    def test_confirm_patterns_is_list(self):
        """CONFIRM_BASH_PATTERNS should be a list."""
        self.assertIsInstance(CONFIRM_BASH_PATTERNS, list)

    def test_confirm_patterns_has_git_push(self):
        """Should include git push pattern."""
        self.assertTrue(any("git" in p and "push" in p for p in CONFIRM_BASH_PATTERNS))

    def test_confirm_patterns_has_kubectl(self):
        """Should include kubectl pattern."""
        self.assertTrue(any("kubectl" in p for p in CONFIRM_BASH_PATTERNS))

    def test_confirm_patterns_has_rm(self):
        """Should include rm pattern."""
        self.assertTrue(any(r"^rm\s" in p or "rm " in p for p in CONFIRM_BASH_PATTERNS))


class TestBatchDefaults(unittest.TestCase):
    """Tests for BATCH_DEFAULTS."""

    def test_is_dict(self):
        """BATCH_DEFAULTS should be a dict."""
        self.assertIsInstance(BATCH_DEFAULTS, dict)

    def test_has_max_staged(self):
        """Should have max_staged setting."""
        self.assertIn("max_staged", BATCH_DEFAULTS)
        self.assertIsInstance(BATCH_DEFAULTS["max_staged"], int)

    def test_has_timeout_minutes(self):
        """Should have timeout_minutes setting."""
        self.assertIn("timeout_minutes", BATCH_DEFAULTS)
        self.assertIsInstance(BATCH_DEFAULTS["timeout_minutes"], int)


class TestFilePaths(unittest.TestCase):
    """Tests for file path constants."""

    def test_state_file_path(self):
        """YOLO_STATE_FILE should be defined."""
        self.assertIsInstance(YOLO_STATE_FILE, str)
        self.assertIn("yolo_state.json", YOLO_STATE_FILE)

    def test_config_file_path(self):
        """YOLO_CONFIG_FILE should be defined."""
        self.assertIsInstance(YOLO_CONFIG_FILE, str)
        self.assertIn("yolo_config.yaml", YOLO_CONFIG_FILE)


class TestClassifyBashCommand(unittest.TestCase):
    """Tests for classify_bash_command function."""

    # AUTO tests
    def test_git_status_is_auto(self):
        """git status should be AUTO."""
        result = classify_bash_command("git status")
        self.assertEqual(result, TrustLevel.AUTO)

    def test_git_diff_is_auto(self):
        """git diff should be AUTO."""
        result = classify_bash_command("git diff HEAD~1")
        self.assertEqual(result, TrustLevel.AUTO)

    def test_git_log_is_auto(self):
        """git log should be AUTO."""
        result = classify_bash_command("git log --oneline -10")
        self.assertEqual(result, TrustLevel.AUTO)

    def test_ls_is_auto(self):
        """ls should be AUTO."""
        result = classify_bash_command("ls -la")
        self.assertEqual(result, TrustLevel.AUTO)

    def test_pwd_is_supervised(self):
        """pwd defaults to SUPERVISED (no space-based pattern match)."""
        # Note: pwd alone doesn't match the pattern "pwd\s" (which requires a space after)
        # This is expected behavior - bare pwd is supervised by default
        result = classify_bash_command("pwd")
        self.assertEqual(result, TrustLevel.SUPERVISED)

    def test_cat_is_auto(self):
        """cat should be AUTO."""
        result = classify_bash_command("cat file.txt")
        self.assertEqual(result, TrustLevel.AUTO)

    def test_pytest_is_auto(self):
        """pytest should be AUTO."""
        result = classify_bash_command("pytest tests/")
        self.assertEqual(result, TrustLevel.AUTO)

    def test_npm_test_is_auto(self):
        """npm test should be AUTO."""
        result = classify_bash_command("npm test")
        self.assertEqual(result, TrustLevel.AUTO)

    def test_npm_run_lint_is_auto(self):
        """npm run lint should be AUTO."""
        result = classify_bash_command("npm run lint")
        self.assertEqual(result, TrustLevel.AUTO)

    # SUPERVISED tests
    def test_git_add_is_supervised(self):
        """git add should be SUPERVISED."""
        result = classify_bash_command("git add .")
        self.assertEqual(result, TrustLevel.SUPERVISED)

    def test_git_commit_is_supervised(self):
        """git commit should be SUPERVISED."""
        result = classify_bash_command('git commit -m "message"')
        self.assertEqual(result, TrustLevel.SUPERVISED)

    def test_mkdir_is_supervised(self):
        """mkdir should be SUPERVISED."""
        result = classify_bash_command("mkdir new_dir")
        self.assertEqual(result, TrustLevel.SUPERVISED)

    def test_touch_is_supervised(self):
        """touch should be SUPERVISED."""
        result = classify_bash_command("touch newfile.txt")
        self.assertEqual(result, TrustLevel.SUPERVISED)

    def test_cp_is_supervised(self):
        """cp should be SUPERVISED."""
        result = classify_bash_command("cp file1 file2")
        self.assertEqual(result, TrustLevel.SUPERVISED)

    def test_mv_is_supervised(self):
        """mv should be SUPERVISED."""
        result = classify_bash_command("mv old new")
        self.assertEqual(result, TrustLevel.SUPERVISED)

    def test_npm_install_is_supervised(self):
        """npm install should be SUPERVISED."""
        result = classify_bash_command("npm install lodash")
        self.assertEqual(result, TrustLevel.SUPERVISED)

    def test_pip_install_is_supervised(self):
        """pip install should be SUPERVISED."""
        result = classify_bash_command("pip install requests")
        self.assertEqual(result, TrustLevel.SUPERVISED)

    def test_python_script_is_supervised(self):
        """python script should be SUPERVISED."""
        result = classify_bash_command("python3 script.py")
        self.assertEqual(result, TrustLevel.SUPERVISED)

    # BLOCKED tests
    def test_rm_rf_root_is_blocked(self):
        """rm -rf / should be BLOCKED."""
        result = classify_bash_command("rm -rf /")
        self.assertEqual(result, TrustLevel.BLOCKED)

    def test_rm_rf_home_is_blocked(self):
        """rm -rf ~ should be BLOCKED."""
        result = classify_bash_command("rm -rf ~")
        self.assertEqual(result, TrustLevel.BLOCKED)

    def test_git_reset_hard_is_blocked(self):
        """git reset --hard should be BLOCKED."""
        result = classify_bash_command("git reset --hard HEAD~5")
        self.assertEqual(result, TrustLevel.BLOCKED)

    def test_git_clean_fdx_is_blocked(self):
        """git clean -fdx should be BLOCKED."""
        result = classify_bash_command("git clean -fdx")
        self.assertEqual(result, TrustLevel.BLOCKED)

    def test_git_force_push_is_blocked(self):
        """git push --force should be BLOCKED."""
        result = classify_bash_command("git push origin main --force")
        self.assertEqual(result, TrustLevel.BLOCKED)

    def test_chmod_777_recursive_is_blocked(self):
        """chmod -R 777 should be BLOCKED."""
        result = classify_bash_command("chmod -R 777 /var/www")
        self.assertEqual(result, TrustLevel.BLOCKED)

    # CONFIRM (treated as BLOCKED) tests
    def test_git_push_is_blocked(self):
        """git push should be BLOCKED (needs confirmation)."""
        result = classify_bash_command("git push origin main")
        self.assertEqual(result, TrustLevel.BLOCKED)

    def test_rm_files_is_blocked(self):
        """rm files should be BLOCKED (needs confirmation)."""
        result = classify_bash_command("rm file.txt")
        self.assertEqual(result, TrustLevel.BLOCKED)

    def test_kubectl_is_blocked(self):
        """kubectl should be BLOCKED (needs confirmation)."""
        result = classify_bash_command("kubectl apply -f deployment.yaml")
        self.assertEqual(result, TrustLevel.BLOCKED)

    def test_terraform_is_blocked(self):
        """terraform should be BLOCKED (needs confirmation)."""
        result = classify_bash_command("terraform destroy")
        self.assertEqual(result, TrustLevel.BLOCKED)

    def test_docker_push_is_blocked(self):
        """docker push should be BLOCKED (needs confirmation)."""
        result = classify_bash_command("docker push myimage:latest")
        self.assertEqual(result, TrustLevel.BLOCKED)

    def test_aws_is_blocked(self):
        """aws commands should be BLOCKED (needs confirmation)."""
        result = classify_bash_command("aws s3 cp file.txt s3://bucket/")
        self.assertEqual(result, TrustLevel.BLOCKED)

    def test_gcloud_is_blocked(self):
        """gcloud commands should be BLOCKED (needs confirmation)."""
        result = classify_bash_command("gcloud compute instances create vm1")
        self.assertEqual(result, TrustLevel.BLOCKED)

    # Default test
    def test_unknown_command_is_supervised(self):
        """Unknown commands should default to SUPERVISED."""
        result = classify_bash_command("some-unknown-command --flag value")
        self.assertEqual(result, TrustLevel.SUPERVISED)

    # Edge cases
    def test_whitespace_handling(self):
        """Should handle leading/trailing whitespace."""
        result = classify_bash_command("  git status  ")
        self.assertEqual(result, TrustLevel.AUTO)

    def test_case_insensitivity(self):
        """Should match patterns case-insensitively."""
        result = classify_bash_command("GIT STATUS")
        self.assertEqual(result, TrustLevel.AUTO)


class TestClassifyAction(unittest.TestCase):
    """Tests for classify_action function."""

    def test_read_tool_is_auto(self):
        """Read tool should be AUTO."""
        result = classify_action("Read", {"file_path": "/path/to/file"})
        self.assertEqual(result, TrustLevel.AUTO)

    def test_glob_tool_is_auto(self):
        """Glob tool should be AUTO."""
        result = classify_action("Glob", {"pattern": "*.py"})
        self.assertEqual(result, TrustLevel.AUTO)

    def test_grep_tool_is_auto(self):
        """Grep tool should be AUTO."""
        result = classify_action("Grep", {"pattern": "TODO"})
        self.assertEqual(result, TrustLevel.AUTO)

    def test_edit_tool_is_supervised(self):
        """Edit tool should be SUPERVISED."""
        result = classify_action("Edit", {"file_path": "test.py", "old_string": "a", "new_string": "b"})
        self.assertEqual(result, TrustLevel.SUPERVISED)

    def test_write_tool_is_supervised(self):
        """Write tool should be SUPERVISED."""
        result = classify_action("Write", {"file_path": "new.py", "content": "# code"})
        self.assertEqual(result, TrustLevel.SUPERVISED)

    def test_bash_auto_command(self):
        """Bash with auto command should be AUTO."""
        result = classify_action("Bash", {"command": "git status"})
        self.assertEqual(result, TrustLevel.AUTO)

    def test_bash_supervised_command(self):
        """Bash with supervised command should be SUPERVISED."""
        result = classify_action("Bash", {"command": "mkdir newdir"})
        self.assertEqual(result, TrustLevel.SUPERVISED)

    def test_bash_blocked_command(self):
        """Bash with blocked command should be BLOCKED."""
        result = classify_action("Bash", {"command": "rm -rf /"})
        self.assertEqual(result, TrustLevel.BLOCKED)

    def test_unknown_tool_is_supervised(self):
        """Unknown tools should default to SUPERVISED."""
        result = classify_action("UnknownTool", {"some": "param"})
        self.assertEqual(result, TrustLevel.SUPERVISED)

    # User override tests
    def test_user_override_tool(self):
        """User can override tool trust level."""
        overrides = {"Read": "blocked"}
        result = classify_action("Read", {}, user_overrides=overrides)
        self.assertEqual(result, TrustLevel.BLOCKED)

    def test_user_override_bash_pattern(self):
        """User can override bash patterns."""
        overrides = {"bash:pytest": "blocked"}
        result = classify_action("Bash", {"command": "pytest tests/"}, user_overrides=overrides)
        self.assertEqual(result, TrustLevel.BLOCKED)

    def test_tool_override_takes_precedence(self):
        """Tool override should take precedence over default."""
        overrides = {"Edit": "auto"}
        result = classify_action("Edit", {"file_path": "test.py"}, user_overrides=overrides)
        self.assertEqual(result, TrustLevel.AUTO)


class TestIsHardBlocked(unittest.TestCase):
    """Tests for is_hard_blocked function."""

    def test_non_bash_not_blocked(self):
        """Non-Bash tools should never be hard blocked."""
        self.assertFalse(is_hard_blocked("Edit", {"file_path": "test.py"}))

    def test_safe_bash_not_blocked(self):
        """Safe bash commands should not be hard blocked."""
        self.assertFalse(is_hard_blocked("Bash", {"command": "git status"}))

    def test_rm_rf_root_is_blocked(self):
        """rm -rf / should be hard blocked."""
        self.assertTrue(is_hard_blocked("Bash", {"command": "rm -rf /"}))

    def test_rm_rf_home_is_blocked(self):
        """rm -rf ~ should be hard blocked."""
        self.assertTrue(is_hard_blocked("Bash", {"command": "rm -rf ~"}))

    def test_git_reset_hard_is_blocked(self):
        """git reset --hard should be hard blocked."""
        self.assertTrue(is_hard_blocked("Bash", {"command": "git reset --hard"}))

    def test_git_clean_fdx_is_blocked(self):
        """git clean -fdx should be hard blocked."""
        self.assertTrue(is_hard_blocked("Bash", {"command": "git clean -fdx"}))

    def test_force_push_is_blocked(self):
        """git push --force should be hard blocked."""
        self.assertTrue(is_hard_blocked("Bash", {"command": "git push --force origin main"}))

    def test_chmod_777_recursive_is_blocked(self):
        """chmod -R 777 should be hard blocked."""
        self.assertTrue(is_hard_blocked("Bash", {"command": "chmod -R 777 /var"}))

    def test_confirm_commands_not_hard_blocked(self):
        """Confirm-required commands should not be hard blocked."""
        # Regular push needs confirmation but isn't hard blocked
        self.assertFalse(is_hard_blocked("Bash", {"command": "git push origin main"}))

    def test_whitespace_handling(self):
        """Should handle whitespace in commands."""
        self.assertTrue(is_hard_blocked("Bash", {"command": "  rm -rf /  "}))


class TestGetDefaultYoloState(unittest.TestCase):
    """Tests for get_default_yolo_state function."""

    def test_returns_dict(self):
        """Should return a dictionary."""
        result = get_default_yolo_state()
        self.assertIsInstance(result, dict)

    def test_disabled_by_default(self):
        """Should be disabled by default."""
        result = get_default_yolo_state()
        self.assertFalse(result["enabled"])

    def test_empty_staged_actions(self):
        """Should have empty staged_actions list."""
        result = get_default_yolo_state()
        self.assertEqual(result["staged_actions"], [])

    def test_null_batch_start_time(self):
        """Should have null batch_start_time."""
        result = get_default_yolo_state()
        self.assertIsNone(result["batch_start_time"])

    def test_has_stats(self):
        """Should have stats dict."""
        result = get_default_yolo_state()
        self.assertIn("stats", result)
        self.assertIsInstance(result["stats"], dict)

    def test_stats_zero_counters(self):
        """Stats should have zero counters."""
        result = get_default_yolo_state()
        self.assertEqual(result["stats"]["auto_executed"], 0)
        self.assertEqual(result["stats"]["staged"], 0)
        self.assertEqual(result["stats"]["blocked"], 0)


class TestGetDefaultYoloConfig(unittest.TestCase):
    """Tests for get_default_yolo_config function."""

    def test_returns_dict(self):
        """Should return a dictionary."""
        result = get_default_yolo_config()
        self.assertIsInstance(result, dict)

    def test_disabled_by_default(self):
        """Should be disabled by default."""
        result = get_default_yolo_config()
        self.assertFalse(result["enabled"])

    def test_empty_trust_overrides(self):
        """Should have empty trust_overrides."""
        result = get_default_yolo_config()
        self.assertEqual(result["trust_overrides"], {})

    def test_has_batch_settings(self):
        """Should have batch settings."""
        result = get_default_yolo_config()
        self.assertIn("batch", result)
        self.assertIsInstance(result["batch"], dict)

    def test_batch_copies_defaults(self):
        """Batch should copy BATCH_DEFAULTS values."""
        result = get_default_yolo_config()
        self.assertEqual(result["batch"]["max_staged"], BATCH_DEFAULTS["max_staged"])
        self.assertEqual(result["batch"]["timeout_minutes"], BATCH_DEFAULTS["timeout_minutes"])

    def test_batch_is_new_dict(self):
        """Batch should be a new dict, not reference to BATCH_DEFAULTS."""
        result = get_default_yolo_config()
        result["batch"]["max_staged"] = 999
        # Should not affect the module constant
        self.assertNotEqual(BATCH_DEFAULTS["max_staged"], 999)


if __name__ == "__main__":
    unittest.main()
