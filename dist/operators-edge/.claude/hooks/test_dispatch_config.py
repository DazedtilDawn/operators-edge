#!/usr/bin/env python3
"""
Tests for dispatch_config.py

Coverage:
- Enum values
- Pattern lists
- Classification functions
- Default state
"""

import unittest

from dispatch_config import (
    DispatchState,
    JunctionType,
    IRREVERSIBLE_BASH,
    EXTERNAL_BASH,
    AMBIGUOUS_SIGNALS,
    BLOCKED_SIGNALS,
    AUTO_EDGE_COMMANDS,
    JUNCTION_EDGE_COMMANDS,
    DISPATCH_DEFAULTS,
    DISPATCH_STATE_FILE,
    classify_bash_junction,
    classify_edge_command,
    detect_output_junction,
    is_junction,
    get_default_dispatch_state,
)


class TestEnums(unittest.TestCase):
    """Tests for enum definitions."""

    def test_dispatch_state_values(self):
        """DispatchState should have expected values."""
        self.assertEqual(DispatchState.IDLE.value, "idle")
        self.assertEqual(DispatchState.RUNNING.value, "running")
        self.assertEqual(DispatchState.JUNCTION.value, "junction")
        self.assertEqual(DispatchState.COMPLETE.value, "complete")
        self.assertEqual(DispatchState.STUCK.value, "stuck")

    def test_junction_type_values(self):
        """JunctionType should have expected values."""
        self.assertEqual(JunctionType.IRREVERSIBLE.value, "irreversible")
        self.assertEqual(JunctionType.EXTERNAL.value, "external")
        self.assertEqual(JunctionType.AMBIGUOUS.value, "ambiguous")
        self.assertEqual(JunctionType.BLOCKED.value, "blocked")
        self.assertEqual(JunctionType.NONE.value, "none")


class TestPatternLists(unittest.TestCase):
    """Tests for pattern list definitions."""

    def test_irreversible_bash_not_empty(self):
        """IRREVERSIBLE_BASH should have patterns."""
        self.assertGreater(len(IRREVERSIBLE_BASH), 0)

    def test_irreversible_bash_patterns_valid(self):
        """IRREVERSIBLE_BASH patterns should be valid regex."""
        import re
        for pattern in IRREVERSIBLE_BASH:
            try:
                re.compile(pattern)
            except re.error:
                self.fail(f"Invalid regex pattern: {pattern}")

    def test_external_bash_not_empty(self):
        """EXTERNAL_BASH should have patterns."""
        self.assertGreater(len(EXTERNAL_BASH), 0)

    def test_external_bash_patterns_valid(self):
        """EXTERNAL_BASH patterns should be valid regex."""
        import re
        for pattern in EXTERNAL_BASH:
            try:
                re.compile(pattern)
            except re.error:
                self.fail(f"Invalid regex pattern: {pattern}")

    def test_ambiguous_signals_not_empty(self):
        """AMBIGUOUS_SIGNALS should have patterns."""
        self.assertGreater(len(AMBIGUOUS_SIGNALS), 0)

    def test_blocked_signals_not_empty(self):
        """BLOCKED_SIGNALS should have patterns."""
        self.assertGreater(len(BLOCKED_SIGNALS), 0)

    def test_auto_edge_commands_includes_key_commands(self):
        """AUTO_EDGE_COMMANDS should include main commands."""
        self.assertIn("edge", AUTO_EDGE_COMMANDS)
        self.assertIn("edge-step", AUTO_EDGE_COMMANDS)
        self.assertIn("edge-prune", AUTO_EDGE_COMMANDS)

    def test_junction_edge_commands_includes_decision_commands(self):
        """JUNCTION_EDGE_COMMANDS should include decision commands."""
        self.assertIn("edge-plan", JUNCTION_EDGE_COMMANDS)
        self.assertIn("edge-adapt", JUNCTION_EDGE_COMMANDS)


class TestDispatchDefaults(unittest.TestCase):
    """Tests for dispatch defaults."""

    def test_defaults_has_required_keys(self):
        """DISPATCH_DEFAULTS should have required keys."""
        self.assertIn("max_iterations", DISPATCH_DEFAULTS)
        self.assertIn("stuck_threshold", DISPATCH_DEFAULTS)
        self.assertIn("auto_prune", DISPATCH_DEFAULTS)
        self.assertIn("verbose", DISPATCH_DEFAULTS)

    def test_max_iterations_reasonable(self):
        """max_iterations should be a reasonable value."""
        self.assertGreater(DISPATCH_DEFAULTS["max_iterations"], 0)
        self.assertLessEqual(DISPATCH_DEFAULTS["max_iterations"], 1000)

    def test_state_file_path(self):
        """DISPATCH_STATE_FILE should be a valid path."""
        self.assertIn(".claude", DISPATCH_STATE_FILE)
        self.assertTrue(DISPATCH_STATE_FILE.endswith(".json"))


class TestClassifyBashJunction(unittest.TestCase):
    """Tests for classify_bash_junction function."""

    def test_git_push_is_irreversible(self):
        """git push should be classified as irreversible."""
        result = classify_bash_junction("git push origin main")
        self.assertEqual(result, JunctionType.IRREVERSIBLE)

    def test_git_push_force_is_irreversible(self):
        """git push --force should be classified as irreversible."""
        result = classify_bash_junction("git push --force")
        self.assertEqual(result, JunctionType.IRREVERSIBLE)

    def test_git_reset_hard_is_irreversible(self):
        """git reset --hard should be classified as irreversible."""
        result = classify_bash_junction("git reset --hard HEAD~1")
        self.assertEqual(result, JunctionType.IRREVERSIBLE)

    def test_rm_is_irreversible(self):
        """rm command should be classified as irreversible."""
        result = classify_bash_junction("rm -rf /tmp/test")
        self.assertEqual(result, JunctionType.IRREVERSIBLE)

    def test_rm_single_file_is_irreversible(self):
        """rm single file should be classified as irreversible."""
        result = classify_bash_junction("rm file.txt")
        self.assertEqual(result, JunctionType.IRREVERSIBLE)

    def test_kubectl_apply_is_external(self):
        """kubectl apply should be classified as external."""
        result = classify_bash_junction("kubectl apply -f deployment.yaml")
        self.assertEqual(result, JunctionType.EXTERNAL)

    def test_gcloud_is_external(self):
        """gcloud commands should be classified as external."""
        result = classify_bash_junction("gcloud compute instances list")
        self.assertEqual(result, JunctionType.EXTERNAL)

    def test_docker_push_is_external(self):
        """docker push should be classified as external."""
        result = classify_bash_junction("docker push myimage:latest")
        self.assertEqual(result, JunctionType.EXTERNAL)

    def test_npm_publish_is_external(self):
        """npm publish should be classified as external."""
        result = classify_bash_junction("npm publish")
        self.assertEqual(result, JunctionType.EXTERNAL)

    def test_aws_command_is_external(self):
        """aws commands should be classified as external."""
        result = classify_bash_junction("aws s3 cp file.txt s3://bucket/")
        self.assertEqual(result, JunctionType.EXTERNAL)

    def test_curl_post_is_external(self):
        """curl POST should be classified as external."""
        result = classify_bash_junction('curl -X POST http://api.example.com')
        self.assertEqual(result, JunctionType.EXTERNAL)

    def test_gh_pr_create_is_external(self):
        """gh pr create should be classified as external."""
        result = classify_bash_junction("gh pr create --title 'Test'")
        self.assertEqual(result, JunctionType.EXTERNAL)

    def test_git_status_is_not_junction(self):
        """git status should not be a junction."""
        result = classify_bash_junction("git status")
        self.assertEqual(result, JunctionType.NONE)

    def test_ls_is_not_junction(self):
        """ls should not be a junction."""
        result = classify_bash_junction("ls -la")
        self.assertEqual(result, JunctionType.NONE)

    def test_python_test_is_not_junction(self):
        """python test command should not be a junction."""
        result = classify_bash_junction("python -m pytest test.py")
        self.assertEqual(result, JunctionType.NONE)

    def test_echo_is_not_junction(self):
        """echo should not be a junction."""
        result = classify_bash_junction("echo 'hello world'")
        self.assertEqual(result, JunctionType.NONE)

    def test_handles_whitespace(self):
        """Should handle commands with leading/trailing whitespace."""
        result = classify_bash_junction("  git push  ")
        self.assertEqual(result, JunctionType.IRREVERSIBLE)

    def test_case_insensitive(self):
        """Should be case insensitive."""
        result = classify_bash_junction("GIT PUSH origin main")
        self.assertEqual(result, JunctionType.IRREVERSIBLE)


class TestClassifyEdgeCommand(unittest.TestCase):
    """Tests for classify_edge_command function."""

    def test_edge_is_auto(self):
        """edge command should be auto."""
        result = classify_edge_command("edge")
        self.assertEqual(result, JunctionType.NONE)

    def test_edgestep_is_auto(self):
        """edgestep (no dash) should be auto per the function's logic."""
        # The function removes dashes from the list but not input
        # So input without dash matches
        result = classify_edge_command("edgestep")
        self.assertEqual(result, JunctionType.NONE)

    def test_edgeprune_is_auto(self):
        """edgeprune (no dash) should be auto."""
        result = classify_edge_command("edgeprune")
        self.assertEqual(result, JunctionType.NONE)

    def test_edgeplan_is_junction(self):
        """edgeplan should be a junction."""
        result = classify_edge_command("edgeplan")
        self.assertEqual(result, JunctionType.AMBIGUOUS)

    def test_edgeadapt_is_junction(self):
        """edgeadapt should be a junction."""
        result = classify_edge_command("edgeadapt")
        self.assertEqual(result, JunctionType.AMBIGUOUS)

    def test_edgeresearch_is_junction(self):
        """edgeresearch should be a junction."""
        result = classify_edge_command("edgeresearch")
        self.assertEqual(result, JunctionType.AMBIGUOUS)

    def test_handles_slash_prefix(self):
        """Should handle /edge prefix."""
        result = classify_edge_command("/edgestep")
        self.assertEqual(result, JunctionType.NONE)

    def test_handles_mixed_case(self):
        """Should handle mixed case."""
        result = classify_edge_command("EDGESTEP")
        self.assertEqual(result, JunctionType.NONE)

    def test_unknown_command_is_junction(self):
        """Unknown commands should be junctions for safety."""
        result = classify_edge_command("edge-unknown")
        self.assertEqual(result, JunctionType.AMBIGUOUS)


class TestDetectOutputJunction(unittest.TestCase):
    """Tests for detect_output_junction function."""

    def test_blocked_keyword_detected(self):
        """Should detect blocked keyword."""
        result = detect_output_junction("Step blocked due to error")
        self.assertEqual(result[0], JunctionType.BLOCKED)
        self.assertIsNotNone(result[1])

    def test_failed_keyword_detected(self):
        """Should detect failed keyword."""
        result = detect_output_junction("Command failed with exit code 1")
        self.assertEqual(result[0], JunctionType.BLOCKED)

    def test_error_keyword_detected(self):
        """Should detect error: keyword."""
        result = detect_output_junction("Error: file not found")
        self.assertEqual(result[0], JunctionType.BLOCKED)

    def test_mismatch_keyword_detected(self):
        """Should detect mismatch keyword."""
        result = detect_output_junction("Mismatch detected in output")
        self.assertEqual(result[0], JunctionType.BLOCKED)

    def test_multiple_approaches_detected(self):
        """Should detect ambiguity signals."""
        result = detect_output_junction("There are multiple valid approaches")
        self.assertEqual(result[0], JunctionType.AMBIGUOUS)

    def test_choose_between_detected(self):
        """Should detect choose between."""
        result = detect_output_junction("Choose between option A and B")
        self.assertEqual(result[0], JunctionType.AMBIGUOUS)

    def test_alternatives_detected(self):
        """Should detect alternatives."""
        result = detect_output_junction("Alternatives: 1) First 2) Second")
        self.assertEqual(result[0], JunctionType.AMBIGUOUS)

    def test_clean_output_is_none(self):
        """Clean output should return NONE."""
        result = detect_output_junction("Build succeeded. All tests passing.")
        self.assertEqual(result[0], JunctionType.NONE)
        self.assertIsNone(result[1])

    def test_case_insensitive(self):
        """Should be case insensitive."""
        result = detect_output_junction("BLOCKED by permission issue")
        self.assertEqual(result[0], JunctionType.BLOCKED)

    def test_blocked_takes_priority(self):
        """Blocked should take priority over ambiguous."""
        # Has both blocked and ambiguous signals
        result = detect_output_junction("Error: choose between failed options")
        self.assertEqual(result[0], JunctionType.BLOCKED)


class TestIsJunction(unittest.TestCase):
    """Tests for is_junction function."""

    def test_none_is_not_junction(self):
        """NONE should not be a junction."""
        self.assertFalse(is_junction(JunctionType.NONE))

    def test_irreversible_is_junction(self):
        """IRREVERSIBLE should be a junction."""
        self.assertTrue(is_junction(JunctionType.IRREVERSIBLE))

    def test_external_is_junction(self):
        """EXTERNAL should be a junction."""
        self.assertTrue(is_junction(JunctionType.EXTERNAL))

    def test_ambiguous_is_junction(self):
        """AMBIGUOUS should be a junction."""
        self.assertTrue(is_junction(JunctionType.AMBIGUOUS))

    def test_blocked_is_junction(self):
        """BLOCKED should be a junction."""
        self.assertTrue(is_junction(JunctionType.BLOCKED))


class TestGetDefaultDispatchState(unittest.TestCase):
    """Tests for get_default_dispatch_state function."""

    def test_returns_dict(self):
        """Should return a dict."""
        result = get_default_dispatch_state()
        self.assertIsInstance(result, dict)

    def test_has_required_keys(self):
        """Should have all required keys."""
        result = get_default_dispatch_state()
        self.assertIn("enabled", result)
        self.assertIn("state", result)
        self.assertIn("current_action", result)
        self.assertIn("junction", result)
        self.assertIn("iteration", result)
        self.assertIn("stuck_count", result)
        self.assertIn("history", result)
        self.assertIn("stats", result)

    def test_default_values(self):
        """Should have correct default values."""
        result = get_default_dispatch_state()
        self.assertFalse(result["enabled"])
        self.assertEqual(result["state"], "idle")
        self.assertIsNone(result["current_action"])
        self.assertIsNone(result["junction"])
        self.assertEqual(result["iteration"], 0)
        self.assertEqual(result["stuck_count"], 0)
        self.assertEqual(result["history"], [])

    def test_stats_has_counters(self):
        """Stats should have counter keys."""
        result = get_default_dispatch_state()
        stats = result["stats"]
        self.assertIn("auto_executed", stats)
        self.assertIn("junctions_hit", stats)
        self.assertIn("total_iterations", stats)
        self.assertEqual(stats["auto_executed"], 0)


if __name__ == "__main__":
    unittest.main()
