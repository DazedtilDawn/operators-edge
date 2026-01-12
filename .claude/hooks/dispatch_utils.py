#!/usr/bin/env python3
"""
Operator's Edge - Dispatch Mode Utilities
Orchestration helpers for autopilot execution.

Dispatch Mode runs /edge commands in a loop until the objective is complete,
stopping only at "junctions" (decision points requiring human input).
"""

import json
import os
import sys
from pathlib import Path
from datetime import datetime
from typing import Optional, Tuple, Dict, Any

# Add hooks directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from edge_utils import load_yaml_state, get_state_dir
from state_utils import write_json_atomic
from dispatch_config import (
    DispatchState,
    JunctionType,
    DISPATCH_STATE_FILE,
    DISPATCH_DEFAULTS,
    get_default_dispatch_state,
    classify_edge_command,
    is_junction,
)
from scout_config import (
    ScoutFinding,
    get_default_scout_state,
    sort_findings,
    SCOUT_THRESHOLDS,
)
from junction_utils import (
    set_pending_junction,
    clear_pending_junction,
    get_pending_junction,
)


# =============================================================================
# STATE MANAGEMENT
# =============================================================================

def load_dispatch_state() -> dict:
    """Load dispatch state from file."""
    state_dir = get_state_dir()
    dispatch_file = state_dir / "dispatch_state.json"
    if dispatch_file.exists():
        try:
            with open(dispatch_file, 'r') as f:
                state = json.load(f)
                # Ensure scout state exists
                if "scout" not in state:
                    state["scout"] = get_default_scout_state()
                return state
        except (json.JSONDecodeError, IOError):
            pass
    state = get_default_dispatch_state()
    state["scout"] = get_default_scout_state()
    return state


def save_dispatch_state(state: dict) -> None:
    """Save dispatch state to file."""
    state_dir = get_state_dir()
    state_dir.mkdir(parents=True, exist_ok=True)
    dispatch_file = state_dir / "dispatch_state.json"
    try:
        write_json_atomic(dispatch_file, state, indent=2)
    except TimeoutError:
        # Let callers decide how to surface contention
        raise


def update_dispatch_stats(state: dict, key: str) -> None:
    """Increment a stats counter."""
    if "stats" not in state:
        state["stats"] = {"auto_executed": 0, "junctions_hit": 0, "total_iterations": 0}
    state["stats"][key] = state["stats"].get(key, 0) + 1


# =============================================================================
# ORCHESTRATION LOGIC
# =============================================================================

def determine_next_action(yaml_state: dict) -> Tuple[str, str, JunctionType]:
    """
    Determine the next /edge command to run based on current state.

    Args:
        yaml_state: The loaded active_context.yaml state

    Returns:
        Tuple of (command, reason, junction_type)
        - command: The /edge command to run (e.g., "edge-plan", "edge-step")
        - reason: Why this command was chosen
        - junction_type: Whether this is a junction
    """
    objective = yaml_state.get("objective")
    plan = yaml_state.get("plan", [])
    current_step = yaml_state.get("current_step", 1)

    # No objective - need to set one
    if not objective:
        return ("edge-plan", "No objective set - need to create a plan", JunctionType.AMBIGUOUS)

    # No plan - need to create one
    if not plan:
        return ("edge-plan", "Objective set but no plan - need to create steps", JunctionType.AMBIGUOUS)

    # Check plan status
    in_progress = [s for s in plan if s.get("status") == "in_progress"]
    pending = [s for s in plan if s.get("status") == "pending"]
    blocked = [s for s in plan if s.get("status") == "blocked"]
    completed = [s for s in plan if s.get("status") == "completed"]

    # All steps completed
    if len(completed) == len(plan):
        return ("complete", "All steps completed - objective achieved!", JunctionType.NONE)

    # Has blocked steps - need adaptation
    if blocked:
        return ("edge-adapt", f"Step blocked: {blocked[0].get('description', 'unknown')}", JunctionType.AMBIGUOUS)

    # Has in-progress step - continue it
    if in_progress:
        return ("edge-step", f"Continue: {in_progress[0].get('description', 'step')}", JunctionType.NONE)

    # Has pending steps - start next one
    if pending:
        return ("edge-step", f"Start: {pending[0].get('description', 'next step')}", JunctionType.NONE)

    # Unclear state - ask for guidance
    return ("edge", "Unclear state - running smart orchestrator", JunctionType.NONE)


def check_stuck(dispatch_state: dict, max_retries: int = None) -> Tuple[bool, str]:
    """
    Check if dispatch is stuck (same action failing repeatedly).

    Returns:
        Tuple of (is_stuck, reason)
    """
    if max_retries is None:
        max_retries = DISPATCH_DEFAULTS["stuck_threshold"]

    stuck_count = dispatch_state.get("stuck_count", 0)
    if stuck_count >= max_retries:
        return (True, f"Same action failed {stuck_count} times - need new approach")

    return (False, "")


def check_iteration_limit(dispatch_state: dict, max_iterations: int = None) -> Tuple[bool, str]:
    """
    Check if we've hit the iteration safety limit.

    Returns:
        Tuple of (limit_reached, reason)
    """
    if max_iterations is None:
        max_iterations = DISPATCH_DEFAULTS["max_iterations"]

    iteration = dispatch_state.get("iteration", 0)
    if iteration >= max_iterations:
        return (True, f"Safety limit reached ({max_iterations} iterations)")

    return (False, "")


def record_action(dispatch_state: dict, action: str, result: str) -> None:
    """Record an action in the dispatch history."""
    if "history" not in dispatch_state:
        dispatch_state["history"] = []

    dispatch_state["history"].append({
        "action": action,
        "result": result,
        "timestamp": datetime.now().isoformat()
    })

    # Keep only last 10 actions
    if len(dispatch_state["history"]) > 10:
        dispatch_state["history"] = dispatch_state["history"][-10:]


def increment_iteration(dispatch_state: dict) -> int:
    """Increment and return the iteration counter."""
    dispatch_state["iteration"] = dispatch_state.get("iteration", 0) + 1
    update_dispatch_stats(dispatch_state, "total_iterations")
    return dispatch_state["iteration"]


def reset_stuck_counter(dispatch_state: dict) -> None:
    """Reset the stuck counter (called when making progress)."""
    dispatch_state["stuck_count"] = 0


def increment_stuck_counter(dispatch_state: dict) -> int:
    """Increment stuck counter (called when action fails/repeats)."""
    dispatch_state["stuck_count"] = dispatch_state.get("stuck_count", 0) + 1
    return dispatch_state["stuck_count"]


# =============================================================================
# DISPATCH FLOW
# =============================================================================

def start_dispatch() -> dict:
    """Start dispatch mode, return initial state."""
    state = load_dispatch_state()
    state["enabled"] = True
    state["state"] = DispatchState.RUNNING.value
    state["iteration"] = 0
    state["stuck_count"] = 0
    state["history"] = []
    save_dispatch_state(state)
    return state


def stop_dispatch(reason: str = "User stopped") -> dict:
    """Stop dispatch mode, return final state."""
    state = load_dispatch_state()
    state["enabled"] = False
    state["state"] = DispatchState.IDLE.value
    record_action(state, "stop", reason)
    save_dispatch_state(state)
    return state


def pause_at_junction(dispatch_state: dict, junction_type: JunctionType, reason: str) -> None:
    """Pause dispatch at a junction."""
    pending = set_pending_junction(junction_type.value, {"reason": reason}, source="dispatch")
    dispatch_state["state"] = DispatchState.JUNCTION.value
    dispatch_state["junction"] = {
        "type": junction_type.value,
        "reason": reason,
        "timestamp": datetime.now().isoformat(),
        "id": pending.get("id") if pending else None,
    }
    update_dispatch_stats(dispatch_state, "junctions_hit")
    save_dispatch_state(dispatch_state)


def resume_from_junction(dispatch_state: dict) -> None:
    """Resume dispatch after junction approval."""
    clear_pending_junction("approve")
    dispatch_state["state"] = DispatchState.RUNNING.value
    dispatch_state["junction"] = None
    save_dispatch_state(dispatch_state)


def mark_complete(dispatch_state: dict) -> None:
    """Mark dispatch as complete (objective achieved)."""
    dispatch_state["enabled"] = False
    dispatch_state["state"] = DispatchState.COMPLETE.value
    record_action(dispatch_state, "complete", "Objective achieved")
    save_dispatch_state(dispatch_state)


def mark_stuck(dispatch_state: dict, reason: str) -> None:
    """Mark dispatch as stuck (can't proceed)."""
    dispatch_state["state"] = DispatchState.STUCK.value
    record_action(dispatch_state, "stuck", reason)
    save_dispatch_state(dispatch_state)


# =============================================================================
# STATUS REPORTING
# =============================================================================

def get_dispatch_status() -> Dict[str, Any]:
    """Get current dispatch status for display."""
    state = load_dispatch_state()
    yaml_state = load_yaml_state() or {}
    pending = get_pending_junction()

    return {
        "enabled": state.get("enabled", False),
        "state": state.get("state", DispatchState.IDLE.value),
        "iteration": state.get("iteration", 0),
        "stuck_count": state.get("stuck_count", 0),
        "junction": pending or state.get("junction"),
        "stats": state.get("stats", {}),
        "objective": yaml_state.get("objective"),
        "plan_steps": len(yaml_state.get("plan", [])),
        "completed_steps": len([s for s in yaml_state.get("plan", []) if s.get("status") == "completed"]),
        "scout": state.get("scout", {}),
    }


# =============================================================================
# SCOUT MODE UTILITIES
# =============================================================================

def save_scout_findings(findings: list, metadata: dict) -> None:
    """Save scout findings to dispatch state."""
    state = load_dispatch_state()
    if "scout" not in state:
        state["scout"] = get_default_scout_state()

    # Convert findings to dicts if they're ScoutFinding objects
    findings_dicts = []
    for f in findings:
        if hasattr(f, 'to_dict'):
            findings_dicts.append(f.to_dict())
        else:
            findings_dicts.append(f)

    state["scout"]["findings"] = findings_dicts
    state["scout"]["last_scan"] = metadata.get("last_scan")
    state["scout"]["scan_duration_seconds"] = metadata.get("scan_duration_seconds")
    state["scout"]["files_scanned"] = metadata.get("files_scanned", 0)

    save_dispatch_state(state)


def get_scout_findings() -> list:
    """Get current scout findings from state."""
    state = load_dispatch_state()
    scout = state.get("scout", {})
    findings_dicts = scout.get("findings", [])

    # Convert back to ScoutFinding objects
    findings = []
    for fd in findings_dicts:
        try:
            findings.append(ScoutFinding.from_dict(fd))
        except Exception:
            pass  # Skip malformed findings

    return findings


def dismiss_finding(title: str) -> None:
    """Mark a finding as dismissed (user doesn't want to see it again)."""
    state = load_dispatch_state()
    if "scout" not in state:
        state["scout"] = get_default_scout_state()

    if "dismissed" not in state["scout"]:
        state["scout"]["dismissed"] = []

    if title not in state["scout"]["dismissed"]:
        state["scout"]["dismissed"].append(title)

    # Remove from current findings
    state["scout"]["findings"] = [
        f for f in state["scout"].get("findings", [])
        if f.get("title") != title
    ]

    save_dispatch_state(state)


def get_top_findings(count: int = None) -> list:
    """Get top N findings, excluding dismissed ones."""
    if count is None:
        count = SCOUT_THRESHOLDS["display_findings"]

    state = load_dispatch_state()
    scout = state.get("scout", {})
    dismissed = set(scout.get("dismissed", []))

    findings = get_scout_findings()
    filtered = [f for f in findings if f.title not in dismissed]
    sorted_findings = sort_findings(filtered)

    return sorted_findings[:count]


def clear_scout_findings() -> None:
    """Clear all scout findings (after converting one to objective)."""
    state = load_dispatch_state()
    if "scout" in state:
        state["scout"]["findings"] = []
    save_dispatch_state(state)


def has_scout_findings() -> bool:
    """Check if there are any scout findings to show."""
    findings = get_top_findings()
    return len(findings) > 0


def needs_scout_scan(yaml_state: dict) -> bool:
    """Check if we should run a scout scan (no objective set)."""
    objective = yaml_state.get("objective")
    return not objective or objective == "null"
