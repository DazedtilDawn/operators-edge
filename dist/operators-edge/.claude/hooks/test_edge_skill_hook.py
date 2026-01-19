#!/usr/bin/env python3
"""
Tests for edge_skill_hook.py - the mechanical gear execution hook.
"""
import pytest
import json
import os
import sys
from pathlib import Path
from unittest.mock import patch, MagicMock
from datetime import datetime

# Add hooks directory to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from edge_skill_hook import (
    parse_edge_args,
    handle_status,
    handle_stop,
    handle_approve,
    handle_skip,
    handle_dismiss,
    handle_run,
)
from gear_config import Gear, GearState, get_default_gear_state


# =============================================================================
# ARGUMENT PARSING TESTS
# =============================================================================

class TestParseEdgeArgs:
    """Tests for parse_edge_args function."""

    def test_bare_edge_command(self):
        """Bare /edge should return run command."""
        result = parse_edge_args("/edge")
        assert result["command"] == "run"
        assert result["args"] == ""

    def test_edge_with_status(self):
        """/edge status should return status command."""
        result = parse_edge_args("/edge status")
        assert result["command"] == "status"

    def test_edge_with_on(self):
        """/edge on should return on command."""
        result = parse_edge_args("/edge on")
        assert result["command"] == "on"

    def test_edge_with_off(self):
        """/edge off should return off command."""
        result = parse_edge_args("/edge off")
        assert result["command"] == "off"

    def test_edge_with_stop(self):
        """/edge stop should return stop command."""
        result = parse_edge_args("/edge stop")
        assert result["command"] == "stop"

    def test_edge_with_approve(self):
        """/edge approve should return approve command."""
        result = parse_edge_args("/edge approve")
        assert result["command"] == "approve"

    def test_edge_with_skip(self):
        """/edge skip should return skip command."""
        result = parse_edge_args("/edge skip")
        assert result["command"] == "skip"

    def test_edge_with_dismiss(self):
        """/edge dismiss should return dismiss command."""
        result = parse_edge_args("/edge dismiss 1")
        assert result["command"] == "dismiss"
        assert result["args"] == "1"

    def test_edge_subcommand(self):
        """/edge-plan should return subcommand."""
        result = parse_edge_args("/edge-plan")
        assert result["command"] == "subcommand"

    def test_edge_with_extra_text(self):
        """Extra text after /edge should be args."""
        result = parse_edge_args("/edge do something specific")
        assert result["command"] == "run"
        assert result["args"] == "do something specific"

    def test_edge_case_insensitive(self):
        """Commands should be case insensitive."""
        result = parse_edge_args("/edge STATUS")
        assert result["command"] == "status"

    def test_edge_in_longer_message(self):
        """Should find /edge in longer messages."""
        result = parse_edge_args("Please run /edge status for me")
        assert result["command"] == "status"

    def test_no_edge_in_message(self):
        """Should return run if no /edge found."""
        result = parse_edge_args("Hello world")
        assert result["command"] == "run"


# =============================================================================
# HANDLER TESTS - STATUS
# =============================================================================

class TestHandleStatus:
    """Tests for handle_status function."""

    @patch('edge_skill_hook.load_gear_state')
    @patch('edge_skill_hook.load_yaml_state')
    @patch('edge_skill_hook.detect_current_gear')
    def test_status_output_contains_header(self, mock_detect, mock_state, mock_gear):
        """Status should include header."""
        mock_gear.return_value = get_default_gear_state()
        mock_state.return_value = {"objective": "Test", "plan": []}
        mock_detect.return_value = Gear.DREAM

        result = handle_status()
        assert "OPERATOR'S EDGE" in result
        assert "GEAR STATUS" in result

    @patch('edge_skill_hook.load_gear_state')
    @patch('edge_skill_hook.load_yaml_state')
    @patch('edge_skill_hook.detect_current_gear')
    def test_status_shows_detected_gear(self, mock_detect, mock_state, mock_gear):
        """Status should show detected gear."""
        mock_gear.return_value = get_default_gear_state()
        mock_state.return_value = {}
        mock_detect.return_value = Gear.DREAM

        result = handle_status()
        assert "DREAM" in result

    @patch('edge_skill_hook.load_gear_state')
    @patch('edge_skill_hook.load_yaml_state')
    @patch('edge_skill_hook.detect_current_gear')
    def test_status_shows_objective(self, mock_detect, mock_state, mock_gear):
        """Status should show current objective."""
        mock_gear.return_value = get_default_gear_state()
        mock_state.return_value = {"objective": "Build feature X"}
        mock_detect.return_value = Gear.ACTIVE

        result = handle_status()
        assert "Build feature X" in result

    @patch('edge_skill_hook.load_gear_state')
    @patch('edge_skill_hook.load_yaml_state')
    @patch('edge_skill_hook.detect_current_gear')
    def test_status_shows_plan_stats(self, mock_detect, mock_state, mock_gear):
        """Status should show plan statistics."""
        mock_gear.return_value = get_default_gear_state()
        mock_state.return_value = {
            "objective": "Test",
            "plan": [
                {"status": "completed", "description": "Step 1"},
                {"status": "pending", "description": "Step 2"},
            ]
        }
        mock_detect.return_value = Gear.ACTIVE

        result = handle_status()
        assert "2 steps" in result
        assert "1 completed" in result
        assert "1 pending" in result

    @patch('edge_skill_hook.get_pending_junction')
    @patch('edge_skill_hook.load_gear_state')
    @patch('edge_skill_hook.load_yaml_state')
    @patch('edge_skill_hook.detect_current_gear')
    def test_status_with_pending_steps_and_junction(self, mock_detect, mock_state, mock_gear, mock_pending):
        """Status should include pending steps and junction without crashing."""
        mock_gear.return_value = get_default_gear_state()
        mock_state.return_value = {
            "objective": "Test",
            "plan": [
                {"status": "completed", "description": "Step 1"},
                {"status": "pending", "description": "Step 2"},
            ]
        }
        mock_detect.return_value = Gear.ACTIVE
        mock_pending.return_value = {"type": "proposal", "payload": {"reason": "Review proposal"}}

        result = handle_status()
        assert "2 steps" in result
        assert "1 pending" in result
        assert "Pending junction" in result
        assert "proposal" in result


# =============================================================================
# HANDLER TESTS - STOP
# =============================================================================

class TestHandleStop:
    """Tests for handle_stop function."""

    @patch('edge_skill_hook.load_gear_state')
    @patch('edge_skill_hook.reset_gear_state')
    def test_stop_shows_stats(self, mock_reset, mock_gear):
        """Stop should show session stats."""
        gear_state = get_default_gear_state()
        gear_state.patrol_findings_count = 5
        gear_state.dream_proposals_count = 2
        gear_state.iterations = 10
        mock_gear.return_value = gear_state
        mock_reset.return_value = (get_default_gear_state(), None)  # (state, error) tuple

        result = handle_stop()
        assert "DISPATCH STOPPED" in result
        assert "5" in result  # findings
        assert "2" in result  # proposals
        assert "10" in result  # iterations


# =============================================================================
# HANDLER TESTS - APPROVE/SKIP/DISMISS
# =============================================================================

class TestHandleJunctionActions:
    """Tests for junction action handlers."""

    @patch('edge_skill_hook.clear_pending_junction')
    def test_handle_approve_timeout(self, mock_clear):
        """Approve should surface lock timeout without crashing."""
        mock_clear.side_effect = TimeoutError("Timeout acquiring lock for junction_state.json")
        message, should_run = handle_approve()
        assert "State lock busy" in message
        assert should_run is False

    @patch('edge_skill_hook.load_gear_state')
    @patch('edge_skill_hook.reset_gear_state')
    def test_stop_resets_state(self, mock_reset, mock_gear):
        """Stop should reset gear state."""
        mock_gear.return_value = get_default_gear_state()
        mock_reset.return_value = (get_default_gear_state(), None)  # (state, error) tuple

        handle_stop()
        mock_reset.assert_called_once()


# =============================================================================
# HANDLER TESTS - APPROVE
# =============================================================================

class TestHandleApprove:
    """Tests for handle_approve function."""

    @patch.dict(os.environ, {"CLAUDE_PROJECT_DIR": "/tmp/test_approve_project"})
    def test_approve_no_junction(self, tmp_path):
        """Approve with no junction should indicate no junction."""
        # Ensure clean state - no dispatch file exists
        state_dir = Path("/tmp/test_approve_project/.claude/state")
        if state_dir.exists():
            dispatch_file = state_dir / "dispatch_state.json"
            if dispatch_file.exists():
                dispatch_file.unlink()

        result, should_run = handle_approve()
        assert "No pending junction" in result
        assert should_run is True

    @patch.dict(os.environ, {"CLAUDE_PROJECT_DIR": "/tmp/test_project"})
    def test_approve_clears_junction(self, tmp_path):
        """Approve should clear pending junction."""
        # Create state directory and dispatch file
        state_dir = Path("/tmp/test_project/.claude/state")
        state_dir.mkdir(parents=True, exist_ok=True)

        junction_file = state_dir / "junction_state.json"
        junction_file.write_text(json.dumps({
            "schema_version": 1,
            "pending": {
                "id": "test",
                "type": "complexity",
                "payload": {"reason": "needs review"},
                "created_at": "2025-01-01T00:00:00",
                "source": "edge"
            },
            "history_tail": [],
            "suppression": []
        }))

        result, should_run = handle_approve()
        assert "APPROVED" in result or "Junction cleared" in result
        assert should_run is True

        # Cleanup
        if junction_file.exists():
            junction_file.unlink()


# =============================================================================
# HANDLER TESTS - SKIP
# =============================================================================

class TestHandleSkip:
    """Tests for handle_skip function."""

    @patch.dict(os.environ, {"CLAUDE_PROJECT_DIR": "/tmp/test_project"})
    def test_skip_no_junction(self):
        """Skip with no junction should indicate nothing to skip."""
        result, should_run = handle_skip()
        assert "Nothing to skip" in result
        assert should_run is True

    @patch.dict(os.environ, {"CLAUDE_PROJECT_DIR": "/tmp/test_project"})
    def test_skip_clears_junction(self):
        """Skip should clear pending junction and mark skipped."""
        # Create state directory and dispatch file
        state_dir = Path("/tmp/test_project/.claude/state")
        state_dir.mkdir(parents=True, exist_ok=True)

        junction_file = state_dir / "junction_state.json"
        junction_file.write_text(json.dumps({
            "schema_version": 1,
            "pending": {
                "id": "test",
                "type": "dangerous",
                "payload": {"reason": "dangerous op"},
                "created_at": "2025-01-01T00:00:00",
                "source": "edge"
            },
            "history_tail": [],
            "suppression": []
        }))

        result, should_run = handle_skip()
        assert "SKIPPED" in result or "skipped" in result.lower()
        assert should_run is True

        # Cleanup
        if junction_file.exists():
            junction_file.unlink()


# =============================================================================
# HANDLER TESTS - DISMISS
# =============================================================================

class TestHandleDismiss:
    """Tests for handle_dismiss function."""

    @patch.dict(os.environ, {"CLAUDE_PROJECT_DIR": "/tmp/test_project"})
    def test_dismiss_clears_junction(self):
        """Dismiss should clear pending junction."""
        state_dir = Path("/tmp/test_project/.claude/state")
        state_dir.mkdir(parents=True, exist_ok=True)

        junction_file = state_dir / "junction_state.json"
        junction_file.write_text(json.dumps({
            "schema_version": 1,
            "pending": {
                "id": "test",
                "type": "proposal",
                "payload": {"reason": "review proposal"},
                "created_at": "2025-01-01T00:00:00",
                "source": "edge"
            },
            "history_tail": [],
            "suppression": []
        }))

        result, should_run = handle_dismiss()
        assert "DISMISSED" in result or "dismissed" in result.lower()
        assert should_run is True

        if junction_file.exists():
            junction_file.unlink()


# =============================================================================
# HANDLER TESTS - RUN
# =============================================================================

class TestHandleRun:
    """Tests for handle_run function."""

    @patch('edge_skill_hook.run_gear_engine')
    @patch('edge_skill_hook.load_yaml_state')
    @patch.dict(os.environ, {"CLAUDE_PROJECT_DIR": "/tmp/test_project"})
    def test_run_shows_gear_header(self, mock_state, mock_engine):
        """Run should show gear header."""
        mock_state.return_value = {}

        # Create a mock result
        from gear_engine import GearEngineResult
        mock_engine.return_value = GearEngineResult(
            gear_executed=Gear.DREAM,
            transitioned=False,
            new_gear=None,
            transition_type=None,
            gear_result={},
            junction_hit=False,
            junction_type=None,
            junction_reason=None,
            continue_loop=False,
            display_message="DREAM gear active",
        )

        result = handle_run()
        assert "OPERATOR'S EDGE" in result
        assert "DREAM" in result

    @patch('edge_skill_hook.run_gear_engine')
    @patch('edge_skill_hook.load_yaml_state')
    @patch.dict(os.environ, {"CLAUDE_PROJECT_DIR": "/tmp/test_project"})
    def test_run_shows_junction(self, mock_state, mock_engine):
        """Run should show junction when hit."""
        mock_state.return_value = {}

        from gear_engine import GearEngineResult
        mock_engine.return_value = GearEngineResult(
            gear_executed=Gear.ACTIVE,
            transitioned=False,
            new_gear=None,
            transition_type=None,
            gear_result={},
            junction_hit=True,
            junction_type="complexity",
            junction_reason="Step involves refactoring",
            continue_loop=False,
            display_message="Active gear paused",
        )

        result = handle_run()
        assert "JUNCTION" in result
        assert "complexity" in result
        assert "/edge approve" in result

    @patch.dict(os.environ, {"CLAUDE_PROJECT_DIR": "/tmp/test_project"})
    def test_run_blocks_on_pending_junction(self):
        """Run should block when pending junction exists."""
        state_dir = Path("/tmp/test_project/.claude/state")
        state_dir.mkdir(parents=True, exist_ok=True)

        junction_file = state_dir / "junction_state.json"
        junction_file.write_text(json.dumps({
            "schema_version": 1,
            "pending": {
                "id": "test",
                "type": "quality_gate",
                "payload": {"reason": "quality gate failed"},
                "created_at": "2025-01-01T00:00:00",
                "source": "edge"
            },
            "history_tail": [],
            "suppression": []
        }))

        result = handle_run()
        assert "JUNCTION PENDING" in result
        assert "quality_gate" in result

        if junction_file.exists():
            junction_file.unlink()

    @patch('edge_skill_hook.run_gear_engine')
    @patch('edge_skill_hook.load_yaml_state')
    @patch.dict(os.environ, {"CLAUDE_PROJECT_DIR": "/tmp/test_project"})
    def test_run_shows_transition(self, mock_state, mock_engine):
        """Run should show transition when occurred."""
        mock_state.return_value = {}

        from gear_engine import GearEngineResult
        mock_engine.return_value = GearEngineResult(
            gear_executed=Gear.ACTIVE,
            transitioned=True,
            new_gear=Gear.PATROL,
            transition_type=None,
            gear_result={},
            junction_hit=False,
            junction_type=None,
            junction_reason=None,
            continue_loop=True,
            display_message="Objective complete",
        )

        result = handle_run()
        assert "TRANSITION" in result
        assert "PATROL" in result


# =============================================================================
# INTEGRATION TESTS
# =============================================================================

class TestIntegration:
    """Integration tests for the hook."""

    @patch('edge_skill_hook.load_yaml_state')
    @patch('edge_skill_hook.load_gear_state')
    @patch('edge_skill_hook.detect_current_gear')
    def test_full_status_flow(self, mock_detect, mock_gear, mock_state):
        """Test complete status flow."""
        mock_gear.return_value = get_default_gear_state()
        mock_state.return_value = {
            "objective": "Test objective",
            "plan": [
                {"status": "completed", "description": "Done"},
                {"status": "pending", "description": "Todo"},
            ]
        }
        mock_detect.return_value = Gear.ACTIVE

        result = handle_status()

        # Should have all key elements
        assert "OPERATOR'S EDGE" in result
        assert "GEAR STATUS" in result
        assert "ACTIVE" in result
        assert "Test objective" in result
        assert "2 steps" in result


# =============================================================================
# EDGE CASES
# =============================================================================

class TestEdgeCases:
    """Edge case tests."""

    def test_parse_empty_input(self):
        """Empty input should return run."""
        result = parse_edge_args("")
        assert result["command"] == "run"

    def test_parse_only_whitespace(self):
        """Whitespace input should return run."""
        result = parse_edge_args("   ")
        assert result["command"] == "run"

    def test_parse_edge_multiple_times(self):
        """Multiple /edge in input should use first one."""
        result = parse_edge_args("/edge status /edge approve")
        assert result["command"] == "status"

    @patch('edge_skill_hook.load_gear_state')
    @patch('edge_skill_hook.load_yaml_state')
    @patch('edge_skill_hook.detect_current_gear')
    def test_status_with_empty_state(self, mock_detect, mock_state, mock_gear):
        """Status should handle empty state gracefully."""
        mock_gear.return_value = get_default_gear_state()
        mock_state.return_value = None
        mock_detect.return_value = Gear.DREAM

        # Should not raise
        result = handle_status()
        assert "OPERATOR'S EDGE" in result

    @patch('edge_skill_hook.run_gear_engine')
    @patch('edge_skill_hook.load_yaml_state')
    @patch.dict(os.environ, {"CLAUDE_PROJECT_DIR": "/tmp/test_project"})
    def test_run_with_none_state(self, mock_state, mock_engine):
        """Run should handle None state."""
        mock_state.return_value = None

        from gear_engine import GearEngineResult
        mock_engine.return_value = GearEngineResult(
            gear_executed=Gear.DREAM,
            transitioned=False,
            new_gear=None,
            transition_type=None,
            gear_result={},
            junction_hit=False,
            junction_type=None,
            junction_reason=None,
            continue_loop=False,
            display_message="No state",
        )

        # Should not raise
        result = handle_run()
        assert "OPERATOR'S EDGE" in result

    @patch('edge_skill_hook.set_pending_junction')
    @patch('edge_skill_hook.run_gear_engine')
    @patch('edge_skill_hook.load_yaml_state')
    @patch.dict(os.environ, {"CLAUDE_PROJECT_DIR": "/tmp/test_project"})
    def test_run_junction_save_timeout(self, mock_state, mock_engine, mock_set_pending):
        """Run should surface lock timeout when saving junction."""
        mock_state.return_value = {"objective": "Test", "plan": [{"status": "pending"}]}

        from gear_engine import GearEngineResult
        mock_engine.return_value = GearEngineResult(
            gear_executed=Gear.ACTIVE,
            transitioned=False,
            new_gear=None,
            transition_type=None,
            gear_result={},
            junction_hit=True,
            junction_type="proposal",
            junction_reason="Review proposal",
            continue_loop=False,
            display_message="Junction",
        )
        mock_set_pending.side_effect = TimeoutError("Timeout acquiring lock for junction_state.json")

        result = handle_run()
        assert "State lock busy" in result
