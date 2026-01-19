#!/usr/bin/env python3
"""
Operator's Edge - Gear Engine (v3.7)
Manages gear transitions and orchestrates the three modes.

The Gear Engine is the central controller that:
- Detects the appropriate gear based on state
- Manages transitions between gears
- Executes the appropriate gear logic
- Tracks gear state across iterations
"""

from typing import Dict, Any, Optional, Tuple
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
import json
import hashlib

from gear_config import (
    Gear, GearTransition, GearState, QualityGateOverride,
    detect_current_gear, get_default_gear_state,
    get_gear_behavior, get_valid_transitions,
    format_gear_status, GEAR_EMOJI, GEAR_LABELS,
)
from gear_active import (
    run_active_gear, ActiveGearResult,
    should_transition_from_active, format_active_status,
)
from gear_patrol import (
    run_patrol_scan, PatrolGearResult,
    should_transition_from_patrol, format_patrol_status,
)
from gear_dream import (
    run_dream_gear, DreamGearResult,
    should_transition_from_dream, format_dream_status,
)
from quality_gate import (
    run_quality_gate, QualityGateResult, QualityCheck,
    format_quality_gate_result, format_quality_junction,
)
from state_utils import (
    write_json_atomic, load_yaml_state,
    get_runtime_section, update_runtime_section,
)
from proof_utils import get_current_session_id

# Feature flag: set to True to use YAML runtime section (v5 schema)
USE_YAML_RUNTIME = True


# =============================================================================
# ENGINE RESULT
# =============================================================================

@dataclass
class GearEngineResult:
    """Result of running the gear engine."""
    gear_executed: Gear
    transitioned: bool
    new_gear: Optional[Gear]
    transition_type: Optional[GearTransition]
    gear_result: Dict[str, Any]  # Result from the executed gear
    junction_hit: bool
    junction_type: Optional[str]
    junction_reason: Optional[str]
    continue_loop: bool  # Should the orchestrator continue?
    display_message: str

    def to_dict(self) -> dict:
        return {
            "gear_executed": self.gear_executed.value,
            "transitioned": self.transitioned,
            "new_gear": self.new_gear.value if self.new_gear else None,
            "transition_type": self.transition_type.value if self.transition_type else None,
            "gear_result": self.gear_result,
            "junction_hit": self.junction_hit,
            "junction_type": self.junction_type,
            "junction_reason": self.junction_reason,
            "continue_loop": self.continue_loop,
        }


# =============================================================================
# GEAR STATE PERSISTENCE
# =============================================================================

GEAR_STATE_FILE = Path(".claude/state/gear_state.json")


def _load_from_yaml_runtime() -> Optional[GearState]:
    """Load gear state from YAML runtime section (v5 schema)."""
    if not USE_YAML_RUNTIME:
        return None

    yaml_state = load_yaml_state()
    if not yaml_state:
        return None

    gear = get_runtime_section(yaml_state, "gear")
    if not gear:
        return None

    # Convert YAML format to GearState
    return GearState(
        current_gear=Gear(gear.get("current", "active")),
        entered_at=gear.get("entered_at"),
        last_run_at=gear.get("last_run_at"),
        last_transition=gear.get("last_transition"),
        iterations=gear.get("iterations", 0),
        patrol_findings_count=gear.get("patrol_findings_count", 0),
        dream_proposals_count=gear.get("dream_proposals_count", 0),
        completion_epoch=gear.get("completion_epoch"),
    )


def _load_from_json_file() -> Optional[GearState]:
    """Load gear state from legacy JSON file."""
    try:
        if GEAR_STATE_FILE.exists():
            data = json.loads(GEAR_STATE_FILE.read_text())
            return GearState.from_dict(data)
    except (json.JSONDecodeError, IOError):
        pass
    return None


def load_gear_state() -> GearState:
    """Load gear state from YAML runtime (preferred) or JSON file (fallback)."""
    # v5: Try YAML runtime section first
    state = _load_from_yaml_runtime()
    if state:
        return state

    # Fallback: Load from JSON file
    state = _load_from_json_file()
    if state:
        # Migrate to YAML on first load
        if USE_YAML_RUNTIME:
            _save_to_yaml_runtime(state)
        return state

    return get_default_gear_state()


def _save_to_yaml_runtime(gear_state: GearState) -> bool:
    """Save gear state to YAML runtime section (v5 schema)."""
    if not USE_YAML_RUNTIME:
        return False

    # Check if YAML state exists with runtime section before attempting write
    yaml_state = load_yaml_state()
    if not yaml_state or "runtime" not in yaml_state:
        return False  # No YAML runtime section, fall back to JSON

    # Convert GearState to YAML format
    yaml_data = {
        "current": gear_state.current_gear.value,
        "entered_at": gear_state.entered_at,
        "last_run_at": gear_state.last_run_at,
        "last_transition": gear_state.last_transition,
        "iterations": gear_state.iterations,
        "patrol_findings_count": gear_state.patrol_findings_count,
        "dream_proposals_count": gear_state.dream_proposals_count,
        "completion_epoch": gear_state.completion_epoch,
    }

    return update_runtime_section("gear", yaml_data)


def _save_to_json_file(gear_state: GearState) -> Tuple[bool, Optional[str]]:
    """Save gear state to legacy JSON file (fallback)."""
    try:
        write_json_atomic(GEAR_STATE_FILE, gear_state.to_dict(), indent=2)
        return (True, None)
    except TimeoutError as e:
        return (False, f"State lock busy: {e}")
    except (IOError, OSError) as e:
        return (False, f"Failed to save gear state: {e}")


def save_gear_state(gear_state: GearState) -> Tuple[bool, Optional[str]]:
    """
    Save gear state to YAML runtime section (preferred) or JSON file (fallback).

    Returns:
        (success, error_message) - True and None on success,
        False and error message on failure.
    """
    # v5: Try YAML runtime section first
    if USE_YAML_RUNTIME and _save_to_yaml_runtime(gear_state):
        return (True, None)

    # Fall back to JSON
    return _save_to_json_file(gear_state)


def reset_gear_state() -> Tuple[GearState, Optional[str]]:
    """
    Reset gear state to default.

    Returns:
        (state, error_message) - state is always returned,
        error_message is None on success, or contains the error on failure.
    """
    state = get_default_gear_state()
    success, error = save_gear_state(state)
    return (state, error)


# =============================================================================
# TRANSITION MANAGEMENT
# =============================================================================

def _is_objective_complete(state: Dict[str, Any]) -> bool:
    """Check if all plan steps are completed."""
    plan = state.get("plan", [])
    if not plan:
        return False
    return all(
        step.get("status") == "completed"
        for step in plan
        if isinstance(step, dict)
    )


def _compute_completion_epoch(state: Dict[str, Any]) -> Optional[str]:
    """Compute a completion epoch hash for the current objective state."""
    if not _is_objective_complete(state):
        return None

    plan = state.get("plan", [])
    statuses = []
    for step in plan:
        if isinstance(step, dict):
            statuses.append(step.get("status"))
        else:
            statuses.append(str(step))

    payload = {
        "objective": state.get("objective", ""),
        "statuses": statuses,
    }
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _check_quality_gate_override(
    gear_state: GearState,
    state: Dict[str, Any],
    failed_checks: Optional[list] = None
) -> Tuple[bool, list]:
    """
    Check if a valid quality gate override exists (v5.2).

    Returns:
        (skip_gate, remaining_failures)
        - Full mode: skip_gate=True, remaining=[]
        - Check-specific mode: skip_gate=True only if ALL failed checks are approved
        - No override/invalid: skip_gate=False, remaining=failed_checks

    Invalidates stale overrides automatically.
    Valid override = same session + same objective hash
    """
    override = gear_state.quality_gate_override
    if not override:
        return (False, failed_checks or [])

    # Handle both dict (v5.1) and QualityGateOverride (v5.2)
    if isinstance(override, dict):
        # Legacy v5.1 dict format - treat as full override
        session_id = override.get("session_id")
        objective_hash = override.get("objective_hash")
        mode = "full"
        approved_checks = []
    else:
        # v5.2 QualityGateOverride dataclass
        session_id = override.session_id
        objective_hash = override.objective_hash
        mode = override.mode
        approved_checks = override.approved_checks or []

    # Check session match
    current_session = get_current_session_id()
    if session_id != current_session:
        # Different session - invalidate override
        gear_state.quality_gate_override = None
        save_gear_state(gear_state)
        return (False, failed_checks or [])

    # Check objective match
    objective = state.get("objective", "") if state else ""
    if objective_hash != hash(objective):
        # Different objective - invalidate override
        gear_state.quality_gate_override = None
        save_gear_state(gear_state)
        return (False, failed_checks or [])

    # Valid override - check mode
    if mode == "full":
        # Full override - skip entire gate
        return (True, [])

    # Check-specific mode - filter failures
    if mode == "check_specific" and failed_checks:
        # Filter out approved checks
        remaining = [
            c for c in failed_checks
            if (c.name if hasattr(c, 'name') else c.get("name", "")) not in approved_checks
        ]
        # Skip gate only if ALL failures are approved
        skip = len(remaining) == 0
        return (skip, remaining)

    # Unknown mode or no failures provided - don't skip
    return (False, failed_checks or [])


def execute_transition(
    gear_state: GearState,
    transition: GearTransition,
) -> GearState:
    """
    Execute a gear transition.

    Updates gear state tracking and returns new state.
    """
    # Determine new gear from transition
    new_gear = {
        GearTransition.ACTIVE_TO_PATROL: Gear.PATROL,
        GearTransition.ACTIVE_TO_DREAM: Gear.DREAM,
        GearTransition.PATROL_TO_ACTIVE: Gear.ACTIVE,
        GearTransition.PATROL_TO_DREAM: Gear.DREAM,
        GearTransition.DREAM_TO_ACTIVE: Gear.ACTIVE,
        GearTransition.DREAM_TO_PATROL: Gear.PATROL,
    }.get(transition, Gear.ACTIVE)

    # Create new gear state
    return GearState(
        current_gear=new_gear,
        entered_at=datetime.now().isoformat(),
        iterations=0,
        last_transition=transition.value,
        patrol_findings_count=gear_state.patrol_findings_count,
        dream_proposals_count=gear_state.dream_proposals_count,
        last_run_at=gear_state.last_run_at,
        completion_epoch=gear_state.completion_epoch,
    )


# =============================================================================
# GEAR EXECUTION
# =============================================================================

def run_gear_engine(
    state: Dict[str, Any],
    project_dir: Optional[Path] = None,
) -> GearEngineResult:
    """
    Run the gear engine - the main entry point.

    This:
    1. Loads gear state
    2. Detects appropriate gear
    3. Executes gear logic
    4. Handles transitions
    5. Returns result

    Args:
        state: The active_context state
        project_dir: Project root for scanning

    Returns:
        GearEngineResult with execution summary
    """
    # Load current gear state
    gear_state = load_gear_state()
    persistence_warnings = []

    # Clear completion epoch if objective is no longer complete
    if not _is_objective_complete(state) and gear_state.completion_epoch is not None:
        gear_state.completion_epoch = None

    # Detect appropriate gear based on state
    detected_gear = detect_current_gear(state)

    # If detected gear differs from current, transition
    if detected_gear != gear_state.current_gear:
        # Find appropriate transition
        transition = _find_transition(gear_state.current_gear, detected_gear)
        if transition:
            gear_state = execute_transition(gear_state, transition)
            success, error = save_gear_state(gear_state)
            if not success:
                persistence_warnings.append(f"Transition not persisted: {error}")

    # Execute the current gear
    gear_state.iterations += 1
    gear_state.last_run_at = datetime.now().isoformat()
    success, error = save_gear_state(gear_state)
    if not success:
        persistence_warnings.append(f"Iteration not persisted: {error}")

    if gear_state.current_gear == Gear.ACTIVE:
        result = _run_active(state, gear_state, project_dir)
    elif gear_state.current_gear == Gear.PATROL:
        result = _run_patrol(state, gear_state, project_dir)
    elif gear_state.current_gear == Gear.DREAM:
        result = _run_dream(state, gear_state)
    else:
        # Fallback
        result = GearEngineResult(
            gear_executed=Gear.ACTIVE,
            transitioned=False,
            new_gear=None,
            transition_type=None,
            gear_result={},
            junction_hit=False,
            junction_type=None,
            junction_reason=None,
            continue_loop=False,
            display_message="Unknown gear state",
        )

    # Append any persistence warnings to the display message
    if persistence_warnings:
        warnings_text = "\n".join(f"[WARNING] {w}" for w in persistence_warnings)
        result.display_message = f"{result.display_message}\n\n{warnings_text}"

    return result


def _find_transition(from_gear: Gear, to_gear: Gear) -> Optional[GearTransition]:
    """Find the transition type between two gears."""
    mapping = {
        (Gear.ACTIVE, Gear.PATROL): GearTransition.ACTIVE_TO_PATROL,
        (Gear.ACTIVE, Gear.DREAM): GearTransition.ACTIVE_TO_DREAM,
        (Gear.PATROL, Gear.ACTIVE): GearTransition.PATROL_TO_ACTIVE,
        (Gear.PATROL, Gear.DREAM): GearTransition.PATROL_TO_DREAM,
        (Gear.DREAM, Gear.ACTIVE): GearTransition.DREAM_TO_ACTIVE,
        (Gear.DREAM, Gear.PATROL): GearTransition.DREAM_TO_PATROL,
    }
    return mapping.get((from_gear, to_gear))


def _run_active(
    state: Dict[str, Any],
    gear_state: GearState,
    project_dir: Optional[Path]
) -> GearEngineResult:
    """Execute Active Gear."""
    result = run_active_gear(state, gear_state)

    # Handle errors - do not continue loop on failure
    if result.error:
        return GearEngineResult(
            gear_executed=Gear.ACTIVE,
            transitioned=False,
            new_gear=None,
            transition_type=None,
            gear_result=result.to_dict(),
            junction_hit=False,
            junction_type=None,
            junction_reason=None,
            continue_loop=False,
            display_message=f"{format_active_status(state)}\n   Error: {result.error}",
        )

    # Check for transition
    should_transition, transition = should_transition_from_active(state)

    # Handle junction
    if result.hit_junction:
        return GearEngineResult(
            gear_executed=Gear.ACTIVE,
            transitioned=False,
            new_gear=None,
            transition_type=None,
            gear_result=result.to_dict(),
            junction_hit=True,
            junction_type=result.junction_type,
            junction_reason=result.junction_reason,
            continue_loop=False,  # Wait for user approval
            display_message=format_active_status(state),
        )

    # Handle completion - run quality gate first (v3.9.3)
    if result.objective_completed or should_transition:
        if transition:
            completion_epoch = _compute_completion_epoch(state)

            # If we've already passed the gate for this completion epoch, skip gating
            if completion_epoch and gear_state.completion_epoch == completion_epoch:
                new_state = execute_transition(gear_state, transition)
                new_state.completion_epoch = completion_epoch
                success, error = save_gear_state(new_state)
                if not success:
                    # Don't report transition if save failed
                    return GearEngineResult(
                        gear_executed=Gear.ACTIVE,
                        transitioned=False,
                        new_gear=None,
                        transition_type=None,
                        gear_result=result.to_dict(),
                        junction_hit=False,
                        junction_type=None,
                        junction_reason=None,
                        continue_loop=False,
                        display_message=f"Quality gate already passed but transition failed to persist: {error}",
                    )
                return GearEngineResult(
                    gear_executed=Gear.ACTIVE,
                    transitioned=True,
                    new_gear=Gear.PATROL,
                    transition_type=transition,
                    gear_result=result.to_dict(),
                    junction_hit=False,
                    junction_type=None,
                    junction_reason=None,
                    continue_loop=True,
                    display_message="Quality gate already passed → Patrol",
                )

            # v5.2: Check for FULL quality gate override (skip gate entirely)
            skip_full, _ = _check_quality_gate_override(gear_state, state, failed_checks=None)
            if skip_full:
                new_state = execute_transition(gear_state, transition)
                if completion_epoch:
                    new_state.completion_epoch = completion_epoch
                success, error = save_gear_state(new_state)
                if not success:
                    return GearEngineResult(
                        gear_executed=Gear.ACTIVE,
                        transitioned=False,
                        new_gear=None,
                        transition_type=None,
                        gear_result=result.to_dict(),
                        junction_hit=False,
                        junction_type=None,
                        junction_reason=None,
                        continue_loop=False,
                        display_message=f"Quality gate override active but transition failed: {error}",
                    )
                return GearEngineResult(
                    gear_executed=Gear.ACTIVE,
                    transitioned=True,
                    new_gear=Gear.PATROL,
                    transition_type=transition,
                    gear_result=result.to_dict(),
                    junction_hit=False,
                    junction_type=None,
                    junction_reason=None,
                    continue_loop=True,
                    display_message="Quality gate bypassed (full override) → Patrol",
                )

            # Run quality gate before allowing transition
            quality_result = run_quality_gate(state, project_dir)

            if not quality_result.passed:
                # v5.2: Check for check-specific override on failed checks
                skip_specific, remaining_failures = _check_quality_gate_override(
                    gear_state, state, failed_checks=quality_result.failed_checks
                )

                if skip_specific:
                    # All failed checks were approved - proceed with transition
                    new_state = execute_transition(gear_state, transition)
                    if completion_epoch:
                        new_state.completion_epoch = completion_epoch
                    success, error = save_gear_state(new_state)
                    if not success:
                        return GearEngineResult(
                            gear_executed=Gear.ACTIVE,
                            transitioned=False,
                            new_gear=None,
                            transition_type=None,
                            gear_result=result.to_dict(),
                            junction_hit=False,
                            junction_type=None,
                            junction_reason=None,
                            continue_loop=False,
                            display_message=f"Quality gate check-specific override active but transition failed: {error}",
                        )
                    approved_count = len(quality_result.failed_checks) - len(remaining_failures)
                    return GearEngineResult(
                        gear_executed=Gear.ACTIVE,
                        transitioned=True,
                        new_gear=Gear.PATROL,
                        transition_type=transition,
                        gear_result=result.to_dict(),
                        junction_hit=False,
                        junction_type=None,
                        junction_reason=None,
                        continue_loop=True,
                        display_message=f"Quality gate bypassed ({approved_count} check(s) approved) → Patrol",
                    )

                # Some checks still failing - create junction with remaining failures
                # Create modified quality result with only remaining failures
                remaining_result = QualityGateResult(
                    passed=False,
                    checks=quality_result.checks,
                    failed_checks=remaining_failures,
                    warning_checks=quality_result.warning_checks,
                    summary=f"{len(remaining_failures)} check(s) still failing",
                )
                return GearEngineResult(
                    gear_executed=Gear.ACTIVE,
                    transitioned=False,
                    new_gear=None,
                    transition_type=None,
                    gear_result={
                        **result.to_dict(),
                        "quality_gate": remaining_result.to_dict(),
                    },
                    junction_hit=True,
                    junction_type="quality_gate",
                    junction_reason=remaining_result.summary,
                    continue_loop=False,  # Wait for fixes
                    display_message=format_quality_junction(remaining_result),
                )

            # Quality gate passed - proceed with transition
            new_state = execute_transition(gear_state, transition)
            if completion_epoch:
                new_state.completion_epoch = completion_epoch
            success, error = save_gear_state(new_state)
            if not success:
                # Don't report transition if save failed
                return GearEngineResult(
                    gear_executed=Gear.ACTIVE,
                    transitioned=False,
                    new_gear=None,
                    transition_type=None,
                    gear_result={
                        **result.to_dict(),
                        "quality_gate": quality_result.to_dict(),
                    },
                    junction_hit=False,
                    junction_type=None,
                    junction_reason=None,
                    continue_loop=False,
                    display_message=f"Quality gate passed but transition failed to persist: {error}\n{format_quality_gate_result(quality_result)}",
                )
            return GearEngineResult(
                gear_executed=Gear.ACTIVE,
                transitioned=True,
                new_gear=Gear.PATROL,
                transition_type=transition,
                gear_result={
                    **result.to_dict(),
                    "quality_gate": quality_result.to_dict(),
                },
                junction_hit=False,
                junction_type=None,
                junction_reason=None,
                continue_loop=True,  # Continue to Patrol
                display_message=f"Quality gate passed → Patrol\n{format_quality_gate_result(quality_result)}",
            )

    # Continue in Active
    return GearEngineResult(
        gear_executed=Gear.ACTIVE,
        transitioned=False,
        new_gear=None,
        transition_type=None,
        gear_result=result.to_dict(),
        junction_hit=False,
        junction_type=None,
        junction_reason=None,
        continue_loop=True,
        display_message=format_active_status(state),
    )


def _run_patrol(
    state: Dict[str, Any],
    gear_state: GearState,
    project_dir: Optional[Path]
) -> GearEngineResult:
    """Execute Patrol Gear."""
    result = run_patrol_scan(state, project_dir)
    persistence_warning = None

    # Update findings count
    gear_state.patrol_findings_count += result.findings_count
    success, error = save_gear_state(gear_state)
    if not success:
        persistence_warning = f"Findings count not persisted: {error}"

    # Check for transition
    should_transition, transition = should_transition_from_patrol(result, gear_state)

    if should_transition and transition:
        new_state = execute_transition(gear_state, transition)
        success, error = save_gear_state(new_state)

        if not success:
            # Don't report transition if save failed
            display_msg = f"{format_patrol_status(result)}\n\n[WARNING] Transition failed to persist: {error}"
            return GearEngineResult(
                gear_executed=Gear.PATROL,
                transitioned=False,
                new_gear=None,
                transition_type=None,
                gear_result=result.to_dict(),
                junction_hit=False,
                junction_type=None,
                junction_reason=None,
                continue_loop=False,
                display_message=display_msg,
            )

        if transition == GearTransition.PATROL_TO_ACTIVE:
            return GearEngineResult(
                gear_executed=Gear.PATROL,
                transitioned=True,
                new_gear=Gear.ACTIVE,
                transition_type=transition,
                gear_result=result.to_dict(),
                junction_hit=True,  # Junction to select finding
                junction_type="finding_selection",
                junction_reason="Select a finding to work on",
                continue_loop=False,  # Wait for selection
                display_message=format_patrol_status(result),
            )
        elif transition == GearTransition.PATROL_TO_DREAM:
            display_msg = "No findings → Dream"
            if persistence_warning:
                display_msg = f"{display_msg}\n\n[WARNING] {persistence_warning}"
            return GearEngineResult(
                gear_executed=Gear.PATROL,
                transitioned=True,
                new_gear=Gear.DREAM,
                transition_type=transition,
                gear_result=result.to_dict(),
                junction_hit=False,
                junction_type=None,
                junction_reason=None,
                continue_loop=True,  # Continue to Dream
                display_message=display_msg,
            )

    display_msg = format_patrol_status(result)
    if persistence_warning:
        display_msg = f"{display_msg}\n\n[WARNING] {persistence_warning}"
    return GearEngineResult(
        gear_executed=Gear.PATROL,
        transitioned=False,
        new_gear=None,
        transition_type=None,
        gear_result=result.to_dict(),
        junction_hit=False,
        junction_type=None,
        junction_reason=None,
        continue_loop=False,
        display_message=display_msg,
    )


def _run_dream(
    state: Dict[str, Any],
    gear_state: GearState,
) -> GearEngineResult:
    """Execute Dream Gear."""
    result = run_dream_gear(state, gear_state)
    persistence_warning = None

    # Update proposal count
    if result.proposal:
        gear_state.dream_proposals_count += 1
        success, error = save_gear_state(gear_state)
        if not success:
            persistence_warning = f"Proposal count not persisted: {error}"

    # Check for transition
    should_transition, transition = should_transition_from_dream(result, gear_state)

    # If proposal generated, junction for approval
    if result.proposal:
        display_msg = format_dream_status(result)
        if persistence_warning:
            display_msg = f"{display_msg}\n\n[WARNING] {persistence_warning}"
        return GearEngineResult(
            gear_executed=Gear.DREAM,
            transitioned=False,
            new_gear=None,
            transition_type=None,
            gear_result=result.to_dict(),
            junction_hit=True,
            junction_type="proposal",
            junction_reason="Review proposal",
            continue_loop=False,  # Wait for user
            display_message=display_msg,
        )

    # Transition back to Patrol
    if should_transition and transition:
        new_state = execute_transition(gear_state, transition)
        success, error = save_gear_state(new_state)
        if not success:
            # Don't report transition if save failed
            return GearEngineResult(
                gear_executed=Gear.DREAM,
                transitioned=False,
                new_gear=None,
                transition_type=None,
                gear_result=result.to_dict(),
                junction_hit=False,
                junction_type=None,
                junction_reason=None,
                continue_loop=False,
                display_message=f"Reflection complete but transition failed to persist: {error}",
            )
        return GearEngineResult(
            gear_executed=Gear.DREAM,
            transitioned=True,
            new_gear=Gear.PATROL,
            transition_type=transition,
            gear_result=result.to_dict(),
            junction_hit=False,
            junction_type=None,
            junction_reason=None,
            continue_loop=True,  # Back to Patrol
            display_message="Reflection complete → Patrol",
        )

    return GearEngineResult(
        gear_executed=Gear.DREAM,
        transitioned=False,
        new_gear=None,
        transition_type=None,
        gear_result=result.to_dict(),
        junction_hit=False,
        junction_type=None,
        junction_reason=None,
        continue_loop=False,
        display_message=format_dream_status(result),
    )


# =============================================================================
# DISPLAY HELPERS
# =============================================================================

def format_engine_status(gear_state: GearState) -> str:
    """Format current engine status."""
    gear = gear_state.current_gear
    emoji = GEAR_EMOJI.get(gear, "?")
    label = GEAR_LABELS.get(gear, "Unknown")

    lines = [
        "─" * 50,
        f"GEAR ENGINE STATUS",
        "─" * 50,
        format_gear_status(gear_state),
        "",
        f"Last transition: {gear_state.last_transition or 'None'}",
        f"Session stats:",
        f"  Patrol findings: {gear_state.patrol_findings_count}",
        f"  Dream proposals: {gear_state.dream_proposals_count}",
        "─" * 50,
    ]

    return "\n".join(lines)


def format_transition(from_gear: Gear, to_gear: Gear) -> str:
    """Format a gear transition for display."""
    from_emoji = GEAR_EMOJI.get(from_gear, "?")
    to_emoji = GEAR_EMOJI.get(to_gear, "?")
    from_label = from_gear.value.title()
    to_label = to_gear.value.title()

    return f"{from_emoji} {from_label} → {to_emoji} {to_label}"
