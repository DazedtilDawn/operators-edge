#!/usr/bin/env python3
"""
Operator's Edge - Active Gear (v3.7)
Executes objective steps - the "doing" mode.

Active Gear is engaged when there's an objective with pending/in-progress steps.
It runs the execution loop until completion or junction.
"""

from typing import Dict, Any, Optional, Tuple
from dataclasses import dataclass
from datetime import datetime

from gear_config import Gear, GearState, GearTransition


# =============================================================================
# ACTIVE GEAR STATE
# =============================================================================

@dataclass
class ActiveGearResult:
    """Result of running Active Gear."""
    steps_executed: int
    steps_completed: int
    hit_junction: bool
    junction_type: Optional[str]  # "complexity", "dangerous", "blocked"
    junction_reason: Optional[str]
    objective_completed: bool
    error: Optional[str]

    def to_dict(self) -> dict:
        return {
            "steps_executed": self.steps_executed,
            "steps_completed": self.steps_completed,
            "hit_junction": self.hit_junction,
            "junction_type": self.junction_type,
            "junction_reason": self.junction_reason,
            "objective_completed": self.objective_completed,
            "error": self.error,
        }


# =============================================================================
# STEP ANALYSIS
# =============================================================================

def get_current_step(state: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Get the current step to execute."""
    plan = state.get("plan", [])
    current_step_num = state.get("current_step", 1)

    # Find first in_progress or pending step
    for i, step in enumerate(plan):
        if not isinstance(step, dict):
            continue
        status = step.get("status", "pending")
        if status == "in_progress":
            return {"index": i, "step": step}
        if status == "pending":
            return {"index": i, "step": step}

    return None


def get_step_progress(state: Dict[str, Any]) -> Tuple[int, int]:
    """Get (completed_count, total_count) of steps."""
    plan = state.get("plan", [])
    total = len(plan)
    completed = sum(
        1 for step in plan
        if isinstance(step, dict) and step.get("status") == "completed"
    )
    return completed, total


def is_objective_complete(state: Dict[str, Any]) -> bool:
    """Check if all steps are completed."""
    plan = state.get("plan", [])
    if not plan:
        return False

    return all(
        step.get("status") == "completed"
        for step in plan
        if isinstance(step, dict)
    )


def has_blocked_steps(state: Dict[str, Any]) -> bool:
    """Check if any steps are blocked."""
    plan = state.get("plan", [])
    return any(
        step.get("status") == "blocked"
        for step in plan
        if isinstance(step, dict)
    )


# =============================================================================
# JUNCTION DETECTION
# =============================================================================

def should_junction_for_step(step: Dict[str, Any]) -> Tuple[bool, Optional[str], Optional[str]]:
    """
    Check if a step requires a junction (user approval).

    Returns:
        (should_junction, junction_type, reason)
    """
    description = step.get("description", "").lower()

    # Dangerous operations
    dangerous_keywords = [
        "delete", "remove", "drop", "truncate",
        "push", "deploy", "publish", "release",
        "migrate", "rollback", "reset",
    ]
    for keyword in dangerous_keywords:
        if keyword in description:
            return True, "dangerous", f"Step involves '{keyword}' operation"

    # Complex operations that need review
    complex_keywords = [
        "refactor", "redesign", "rewrite", "restructure",
        "architecture", "schema change", "breaking change",
    ]
    for keyword in complex_keywords:
        if keyword in description:
            return True, "complexity", f"Step involves '{keyword}' - needs review"

    return False, None, None


# =============================================================================
# ACTIVE GEAR EXECUTION
# =============================================================================

def check_active_gear_preconditions(state: Dict[str, Any]) -> Tuple[bool, Optional[str]]:
    """
    Check if Active Gear can run.

    Returns:
        (can_run, error_message)
    """
    # Must have an objective
    objective = state.get("objective", "")
    if not objective or not objective.strip():
        return False, "No objective set"

    # Must have a plan
    plan = state.get("plan", [])
    if not plan:
        return False, "No plan defined"

    # Must have work to do
    if is_objective_complete(state):
        return False, "Objective already complete"

    # Check for blocked steps
    if has_blocked_steps(state):
        return False, "Has blocked steps - needs adaptation"

    return True, None


def run_active_gear(
    state: Dict[str, Any],
    gear_state: GearState,
    max_steps: int = 10
) -> ActiveGearResult:
    """
    Run Active Gear - execute steps until completion or junction.

    This is the core execution loop. It:
    1. Gets the current step
    2. Checks for junctions
    3. Executes if safe
    4. Updates state
    5. Repeats until done or junction

    Args:
        state: The active_context state
        gear_state: Current gear state tracking
        max_steps: Maximum steps to execute in one run

    Returns:
        ActiveGearResult with execution summary
    """
    # Check preconditions
    can_run, error = check_active_gear_preconditions(state)
    if not can_run:
        return ActiveGearResult(
            steps_executed=0,
            steps_completed=0,
            hit_junction=False,
            junction_type=None,
            junction_reason=None,
            objective_completed=False,
            error=error,
        )

    steps_executed = 0
    steps_completed = 0

    for _ in range(max_steps):
        # Get current step
        current = get_current_step(state)
        if not current:
            # No more steps - objective complete
            return ActiveGearResult(
                steps_executed=steps_executed,
                steps_completed=steps_completed,
                hit_junction=False,
                junction_type=None,
                junction_reason=None,
                objective_completed=True,
                error=None,
            )

        step = current["step"]

        # Check for junction
        needs_junction, junction_type, reason = should_junction_for_step(step)
        if needs_junction:
            return ActiveGearResult(
                steps_executed=steps_executed,
                steps_completed=steps_completed,
                hit_junction=True,
                junction_type=junction_type,
                junction_reason=reason,
                objective_completed=False,
                error=None,
            )

        # Step would be executed here by the orchestrator
        # This module just analyzes and prepares - actual execution
        # is done by the skill/command that invokes this
        steps_executed += 1

        # For now, we return after analyzing one step
        # The orchestrator will call us again after executing
        return ActiveGearResult(
            steps_executed=steps_executed,
            steps_completed=steps_completed,
            hit_junction=False,
            junction_type=None,
            junction_reason=None,
            objective_completed=False,
            error=None,
        )

    # Hit max steps
    return ActiveGearResult(
        steps_executed=steps_executed,
        steps_completed=steps_completed,
        hit_junction=False,
        junction_type=None,
        junction_reason=None,
        objective_completed=False,
        error=None,
    )


# =============================================================================
# TRANSITION DETECTION
# =============================================================================

def should_transition_from_active(state: Dict[str, Any]) -> Tuple[bool, Optional[GearTransition]]:
    """
    Check if Active Gear should transition to another gear.

    Returns:
        (should_transition, transition_type)
    """
    if is_objective_complete(state):
        return True, GearTransition.ACTIVE_TO_PATROL

    return False, None


# =============================================================================
# LESSON SURFACING (v3.10)
# =============================================================================

def get_lessons_for_current_step(state: Dict[str, Any]) -> list:
    """
    Surface lessons relevant to the current step.
    Returns list of relevant lessons (for display or guidance).
    """
    current = get_current_step(state)
    if not current:
        return []

    try:
        from memory_utils import surface_relevant_memory

        step = current["step"]
        context = step.get("description", "")
        return surface_relevant_memory(state, context)
    except (ImportError, Exception):
        return []


# =============================================================================
# DISPLAY HELPERS
# =============================================================================

def format_active_status(state: Dict[str, Any]) -> str:
    """Format Active Gear status for display."""
    objective = state.get("objective", "No objective")
    completed, total = get_step_progress(state)

    current = get_current_step(state)
    current_desc = current["step"].get("description", "Unknown") if current else "None"

    lines = [
        f"⚙️ ACTIVE GEAR",
        f"   Objective: {objective[:50]}{'...' if len(objective) > 50 else ''}",
        f"   Progress: {completed}/{total} steps",
        f"   Current: {current_desc[:40]}{'...' if len(current_desc) > 40 else ''}",
    ]

    # v3.10: Surface relevant lessons for current step
    relevant = get_lessons_for_current_step(state)
    if relevant:
        lines.append("   📚 Relevant lessons:")
        for lesson in relevant[:3]:
            trigger = lesson.get("trigger", "?")
            text = lesson.get("lesson", "")[:50]
            lines.append(f"      [{trigger}]: {text}...")

    return "\n".join(lines)
