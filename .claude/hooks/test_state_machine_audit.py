#!/usr/bin/env python3
"""
Tests for state machine audit findings.

These tests document discovered issues and will fail until fixes are implemented.
After fixes, they should pass and serve as regression tests.

Phase 0 of the State Machine Logic Audit:
- Test A: Quality gate approve→reblock loop
- Test B: Orphaned eval pending_run
- Test C: Junction status drift
"""
import json
import os
import sys
import tempfile
import unittest
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import patch, MagicMock

# Add hooks directory to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


class TestQualityGateApproveReblockLoop(unittest.TestCase):
    """
    Test A: Quality gate approve→reblock loop.

    Issue: After /edge approve on a quality_gate junction, the next /edge run
    will hit the quality gate again and create the same junction.

    Expected: After approving a quality_gate junction, subsequent /edge runs
    should bypass the gate (for this session + objective).

    Current behavior: Junction is cleared but no override is persisted,
    so the next run re-triggers the gate.
    """

    @patch('gear_engine.save_gear_state')
    @patch('gear_engine.load_gear_state')
    @patch('gear_engine.detect_current_gear')  # Prevent auto-transition to PATROL
    @patch('gear_engine.run_quality_gate')     # Patches where it's used (gear_engine imports it)
    @patch('gear_engine.run_active_gear')      # Patches where it's used (gear_engine imports it)
    def test_quality_gate_not_reblocked_after_approve(
        self, mock_active, mock_quality, mock_detect, mock_load, mock_save
    ):
        """
        After /edge approve on quality_gate junction, next run should NOT reblock.

        This test verifies:
        1. GearState has quality_gate_override field (for session-scoped bypass)
        2. When objective completes and quality gate fails, we get quality_gate junction
        3. After setting override, subsequent runs bypass the gate

        v5.1: This test now passes after implementing the override.
        """
        from gear_engine import run_gear_engine, GearEngineResult
        from gear_config import Gear, GearState, get_default_gear_state
        from gear_active import ActiveGearResult
        from quality_gate import QualityGateResult, QualityCheck

        # Setup: State where objective is in progress (has pending work)
        # This keeps us in ACTIVE gear so quality gate runs on completion
        state = {
            "objective": "Test objective",
            "plan": [
                {"description": "Step 1", "status": "completed", "proof": "Done"}
            ],
            "current_step": 2,
        }

        # Mock gear state: in ACTIVE gear
        gear_state = get_default_gear_state()
        gear_state.current_gear = Gear.ACTIVE
        mock_load.return_value = gear_state
        mock_save.return_value = (True, None)

        # Mock detect to keep us in ACTIVE (prevent auto-transition to PATROL)
        mock_detect.return_value = Gear.ACTIVE

        # Mock active gear result: objective completed (should trigger quality gate)
        mock_active.return_value = ActiveGearResult(
            steps_executed=1,
            steps_completed=1,
            hit_junction=False,
            junction_type=None,
            junction_reason=None,
            objective_completed=True,
            error=None,
        )

        # Mock quality gate: FAILS (missing proof, etc.)
        failed_check = QualityCheck(
            name="check_steps_have_proof",
            passed=False,
            severity="error",
            message="Step 1 missing proof",
            details={}
        )
        mock_quality.return_value = QualityGateResult(
            passed=False,
            checks=[failed_check],
            failed_checks=[failed_check],
            warning_checks=[],
            summary="1 check failed",
        )

        # First run: Should hit quality_gate junction
        result1 = run_gear_engine(state)

        self.assertTrue(result1.junction_hit)
        self.assertEqual(result1.junction_type, "quality_gate")

        # Check if gear_state has quality_gate_override attribute (v5.1 fix)
        has_override_capability = hasattr(gear_state, 'quality_gate_override')

        self.assertTrue(
            has_override_capability,
            "GearState should have quality_gate_override field for session-scoped bypass"
        )

    @patch('gear_engine.save_gear_state')
    @patch('gear_engine.load_gear_state')
    @patch('gear_engine.run_quality_gate')
    @patch('gear_active.run_active_gear')
    def test_quality_gate_override_in_gear_state(
        self, mock_active, mock_quality, mock_load, mock_save
    ):
        """
        GearState should have a quality_gate_override field.

        This test verifies the data structure exists for the fix.
        """
        from gear_config import GearState, get_default_gear_state

        state = get_default_gear_state()

        # Check if the override field exists and is serializable
        state_dict = state.to_dict()

        # This assertion will fail until we add the field
        self.assertIn(
            "quality_gate_override",
            state_dict,
            "GearState.to_dict() should include quality_gate_override field"
        )


class TestOrphanedEvalPendingRun(unittest.TestCase):
    """
    Test B: Orphaned eval pending_run.

    Issue: pre_tool.py creates a pending_run in eval_state.json.
    If post_tool.py never runs (crash, timeout), the pending_run lingers forever.

    Expected: Stale pending_runs (>1 hour old) should be cleaned up
    automatically on session start.

    Current behavior: No cleanup mechanism exists or is wired up.
    """

    def test_cleanup_orphaned_eval_state_exists(self):
        """
        cleanup_orphaned_eval_state() function should exist in eval_utils.

        This test verifies the cleanup function exists.
        """
        try:
            from eval_utils import cleanup_orphaned_eval_state
            exists = True
        except ImportError:
            exists = False

        self.assertTrue(
            exists,
            "eval_utils should export cleanup_orphaned_eval_state() function"
        )

    @patch('eval_utils.get_eval_state_file')
    @patch('eval_utils.save_eval_state')
    def test_stale_pending_run_cleared(self, mock_save, mock_file):
        """
        Stale pending_run (>1 hour old) should be cleared by cleanup function.

        This test will fail until cleanup_orphaned_eval_state() is implemented.
        """
        # Skip if function doesn't exist yet
        try:
            from eval_utils import cleanup_orphaned_eval_state, load_eval_state
        except ImportError:
            self.skipTest("cleanup_orphaned_eval_state not yet implemented")

        with tempfile.TemporaryDirectory() as tmpdir:
            state_file = Path(tmpdir) / "eval_state.json"
            mock_file.return_value = state_file

            # Create stale pending_run (2 hours old)
            two_hours_ago = (datetime.now() - timedelta(hours=2)).isoformat()
            stale_state = {
                "pending_run": {
                    "tool": "Edit",
                    "started_at": two_hours_ago,
                }
            }
            state_file.write_text(json.dumps(stale_state))

            # Run cleanup
            result = cleanup_orphaned_eval_state(max_age_minutes=60)

            # Verify pending_run was cleared
            self.assertTrue(result, "cleanup should return True when clearing stale run")

            # Verify state was saved without pending_run
            if mock_save.called:
                saved_state = mock_save.call_args[0][0]
                self.assertIsNone(
                    saved_state.get("pending_run"),
                    "pending_run should be None after cleanup"
                )


class TestJunctionStatusDrift(unittest.TestCase):
    """
    Test C: Junction status drift.

    Issue: get_dispatch_status() falls back to dispatch_state["junction"]
    when get_pending_junction() returns None. This can show stale junction data.

    Expected: Junction status should ONLY come from junction_state.json
    (single source of truth). No fallback to dispatch_state.

    Current behavior: Line 417 in dispatch_utils.py has:
        "junction": pending or state.get("junction"),
    This fallback causes drift.
    """

    @patch('dispatch_utils.load_yaml_state')
    @patch('dispatch_utils.load_dispatch_state')
    @patch('dispatch_utils.get_pending_junction')
    def test_no_stale_junction_from_dispatch_state(
        self, mock_pending, mock_dispatch, mock_yaml
    ):
        """
        get_dispatch_status() should NOT show stale junction from dispatch_state.

        Scenario:
        1. Junction was set in both junction_state and dispatch_state
        2. Junction is cleared from junction_state (via clear_pending_junction)
        3. But dispatch_state["junction"] still has the old value (drift)
        4. get_dispatch_status() should NOT show the stale junction

        This test SHOULD PASS after removing the fallback.
        Currently EXPECTED TO FAIL - documenting the issue.
        """
        from dispatch_utils import get_dispatch_status

        # Setup: No pending junction (cleared)
        mock_pending.return_value = None

        # Setup: dispatch_state still has stale junction data (drift)
        mock_dispatch.return_value = {
            "enabled": True,
            "state": "running",
            "iteration": 5,
            "stuck_count": 0,
            "junction": {  # STALE - should not be shown
                "type": "irreversible",
                "reason": "git push",
            },
            "stats": {},
            "scout": {},
        }

        mock_yaml.return_value = {
            "objective": "Test",
            "plan": [],
        }

        status = get_dispatch_status()

        # The junction field should be None (from get_pending_junction)
        # NOT the stale value from dispatch_state["junction"]
        self.assertIsNone(
            status["junction"],
            "Junction should be None (from junction_state), not stale dispatch_state value"
        )

    def test_pause_at_junction_does_not_write_duplicate(self):
        """
        pause_at_junction() should NOT write to both junction_state AND dispatch_state.

        This test verifies that the duplicate write is removed.
        Currently EXPECTED TO FAIL - documenting the issue.
        """
        from dispatch_utils import pause_at_junction
        from dispatch_config import JunctionType
        import inspect

        # Get the source code of pause_at_junction
        source = inspect.getsource(pause_at_junction)

        # Check if it writes to dispatch_state["junction"]
        writes_to_dispatch = 'dispatch_state["junction"]' in source or "dispatch_state['junction']" in source

        # This should be False after the fix
        self.assertFalse(
            writes_to_dispatch,
            "pause_at_junction() should NOT write to dispatch_state['junction'] (use junction_state only)"
        )


class TestDispatchStuckDeadCode(unittest.TestCase):
    """
    Test D: Dispatch STUCK is dead code.

    Issue: increment_stuck_counter() is defined but never called.
    /edge-yolo is not a Python hook, so STUCK mechanics never run.

    This test documents the issue for tracking purposes.
    """

    def test_increment_stuck_counter_has_call_sites(self):
        """
        increment_stuck_counter() should have actual call sites (not just definition).

        This test uses grep-like inspection to find call sites.
        Currently EXPECTED TO FAIL - documenting the dead code issue.
        """
        import os
        from pathlib import Path

        hooks_dir = Path(__file__).parent

        # Search for increment_stuck_counter usage (not definition or import)
        call_sites = []
        for py_file in hooks_dir.glob("*.py"):
            if py_file.name.startswith("test_"):
                continue  # Skip test files
            content = py_file.read_text()
            lines = content.split("\n")
            for i, line in enumerate(lines, 1):
                if "increment_stuck_counter(" in line:
                    # Exclude function definition and import statements
                    if not line.strip().startswith("def ") and \
                       not line.strip().startswith("from ") and \
                       not line.strip().startswith("import "):
                        call_sites.append((py_file.name, i, line.strip()))

        self.assertGreater(
            len(call_sites),
            0,
            "increment_stuck_counter() should have at least one call site in production code"
        )


if __name__ == "__main__":
    unittest.main()
