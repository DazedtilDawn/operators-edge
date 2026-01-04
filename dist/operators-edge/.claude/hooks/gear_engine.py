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

from gear_config import (
    Gear, GearTransition, GearState,
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
    run_quality_gate, QualityGateResult,
    format_quality_gate_result, format_quality_junction,
)


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


def load_gear_state() -> GearState:
    """Load gear state from file or create default."""
    try:
        if GEAR_STATE_FILE.exists():
            data = json.loads(GEAR_STATE_FILE.read_text())
            return GearState.from_dict(data)
    except (json.JSONDecodeError, IOError):
        pass
    return get_default_gear_state()


def save_gear_state(gear_state: GearState) -> None:
    """Save gear state to file."""
    try:
        GEAR_STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
        GEAR_STATE_FILE.write_text(json.dumps(gear_state.to_dict(), indent=2))
    except IOError:
        pass  # Non-critical


def reset_gear_state() -> GearState:
    """Reset gear state to default."""
    state = get_default_gear_state()
    save_gear_state(state)
    return state


# =============================================================================
# TRANSITION MANAGEMENT
# =============================================================================

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

    # Detect appropriate gear based on state
    detected_gear = detect_current_gear(state)

    # If detected gear differs from current, transition
    if detected_gear != gear_state.current_gear:
        # Find appropriate transition
        transition = _find_transition(gear_state.current_gear, detected_gear)
        if transition:
            gear_state = execute_transition(gear_state, transition)
            save_gear_state(gear_state)

    # Execute the current gear
    gear_state.iterations += 1

    if gear_state.current_gear == Gear.ACTIVE:
        return _run_active(state, gear_state, project_dir)
    elif gear_state.current_gear == Gear.PATROL:
        return _run_patrol(state, gear_state, project_dir)
    elif gear_state.current_gear == Gear.DREAM:
        return _run_dream(state, gear_state)

    # Fallback
    return GearEngineResult(
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


def _find_transition(from_gear: Gear, to_gear: Gear) -> Optional[GearTransition]:
    """Find the transition type between two gears."""
    mapping = {
        (Gear.ACTIVE, Gear.PATROL): GearTransition.ACTIVE_TO_PATROL,
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
            # Run quality gate before allowing transition
            quality_result = run_quality_gate(state, project_dir)

            if not quality_result.passed:
                # Quality gate failed - junction instead of transition
                return GearEngineResult(
                    gear_executed=Gear.ACTIVE,
                    transitioned=False,
                    new_gear=None,
                    transition_type=None,
                    gear_result={
                        **result.to_dict(),
                        "quality_gate": quality_result.to_dict(),
                    },
                    junction_hit=True,
                    junction_type="quality_gate",
                    junction_reason=quality_result.summary,
                    continue_loop=False,  # Wait for fixes
                    display_message=format_quality_junction(quality_result),
                )

            # Quality gate passed - proceed with transition
            new_state = execute_transition(gear_state, transition)
            save_gear_state(new_state)
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

    # Update findings count
    gear_state.patrol_findings_count += result.findings_count
    save_gear_state(gear_state)

    # Check for transition
    should_transition, transition = should_transition_from_patrol(result, gear_state)

    if should_transition and transition:
        new_state = execute_transition(gear_state, transition)
        save_gear_state(new_state)

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
                display_message="No findings → Dream",
            )

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
        display_message=format_patrol_status(result),
    )


def _run_dream(
    state: Dict[str, Any],
    gear_state: GearState,
) -> GearEngineResult:
    """Execute Dream Gear."""
    result = run_dream_gear(state, gear_state)

    # Update proposal count
    if result.proposal:
        gear_state.dream_proposals_count += 1
        save_gear_state(gear_state)

    # Check for transition
    should_transition, transition = should_transition_from_dream(result, gear_state)

    # If proposal generated, junction for approval
    if result.proposal:
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
            display_message=format_dream_status(result),
        )

    # Transition back to Patrol
    if should_transition and transition:
        new_state = execute_transition(gear_state, transition)
        save_gear_state(new_state)
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
