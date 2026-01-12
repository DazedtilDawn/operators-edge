#!/usr/bin/env python3
"""
Operator's Edge - Gear Configuration (v3.7)
Three Gears Mode: Automatic mode switching based on system state.

Gears represent the system's operational mode:
- ACTIVE: Has objective, executing steps
- PATROL: Just completed, scanning for issues
- DREAM: Truly idle, reflecting and proposing

Transitions happen automatically based on state conditions.
"""

from enum import Enum
from dataclasses import dataclass
from typing import Optional, List, Dict, Any
from datetime import datetime


# =============================================================================
# GEAR STATES
# =============================================================================

class Gear(Enum):
    """The three operational modes of Operator's Edge."""
    ACTIVE = "active"   # Executing objectives
    PATROL = "patrol"   # Scanning for issues after completion
    DREAM = "dream"     # Reflecting and proposing when idle


class GearTransition(Enum):
    """Valid transitions between gears."""
    ACTIVE_TO_PATROL = "active_to_patrol"     # Objective completed
    ACTIVE_TO_DREAM = "active_to_dream"       # Idle/no objective
    PATROL_TO_ACTIVE = "patrol_to_active"     # Finding selected
    PATROL_TO_DREAM = "patrol_to_dream"       # Nothing actionable found
    DREAM_TO_ACTIVE = "dream_to_active"       # Proposal approved or user input
    DREAM_TO_PATROL = "dream_to_patrol"       # Periodic re-scan


# =============================================================================
# GEAR STATE DETECTION
# =============================================================================

def detect_current_gear(state: Dict[str, Any]) -> Gear:
    """
    Determine the appropriate gear based on current state.

    Args:
        state: The active_context state dict

    Returns:
        The gear the system should be in
    """
    objective = state.get("objective", "")
    plan = state.get("plan", [])

    # Has an active objective with work to do?
    if objective and objective.strip():
        # Check if there's actual work (pending/in_progress steps)
        has_work = any(
            step.get("status") in ("pending", "in_progress")
            for step in plan
            if isinstance(step, dict)
        )
        if has_work:
            return Gear.ACTIVE

    # No objective or all complete - check if we just finished something
    # (Patrol scans for issues after completion)
    if _recently_completed_objective(state):
        return Gear.PATROL

    # Nothing active, nothing recently completed - Dream mode
    return Gear.DREAM


def _recently_completed_objective(state: Dict[str, Any]) -> bool:
    """Check if we recently completed an objective (within last transition)."""
    # Check if all steps are completed but objective still set
    plan = state.get("plan", [])
    if not plan:
        return False

    all_complete = all(
        step.get("status") == "completed"
        for step in plan
        if isinstance(step, dict)
    )

    # If all steps complete and objective exists, we just finished
    objective = state.get("objective", "")
    return all_complete and bool(objective and objective.strip())


# =============================================================================
# GEAR BEHAVIORS
# =============================================================================

@dataclass
class GearBehavior:
    """Configuration for each gear's behavior."""
    gear: Gear
    description: str
    actions: List[str]
    max_iterations: int
    requires_user_approval: bool

    def to_dict(self) -> dict:
        return {
            "gear": self.gear.value,
            "description": self.description,
            "actions": self.actions,
            "max_iterations": self.max_iterations,
            "requires_user_approval": self.requires_user_approval,
        }


# Behavior definitions for each gear
GEAR_BEHAVIORS = {
    Gear.ACTIVE: GearBehavior(
        gear=Gear.ACTIVE,
        description="Executing objective steps",
        actions=["execute_step", "check_progress", "handle_errors"],
        max_iterations=100,  # Can run many steps
        requires_user_approval=False,  # Auto-executes (except junctions)
    ),
    Gear.PATROL: GearBehavior(
        gear=Gear.PATROL,
        description="Scanning for issues and violations",
        actions=["scout_scan", "lesson_audit", "drift_detection"],
        max_iterations=1,  # Single scan cycle
        requires_user_approval=False,  # Auto-scans, but findings go to junction
    ),
    Gear.DREAM: GearBehavior(
        gear=Gear.DREAM,
        description="Reflecting, consolidating, proposing",
        actions=["consolidate_lessons", "analyze_patterns", "generate_proposals"],
        max_iterations=1,  # Single reflection cycle
        requires_user_approval=True,  # Proposals need approval
    ),
}


def get_gear_behavior(gear: Gear) -> GearBehavior:
    """Get the behavior configuration for a gear."""
    return GEAR_BEHAVIORS.get(gear, GEAR_BEHAVIORS[Gear.ACTIVE])


# =============================================================================
# TRANSITION RULES
# =============================================================================

@dataclass
class TransitionRule:
    """A rule for when gear transitions should occur."""
    from_gear: Gear
    to_gear: Gear
    condition: str  # Human-readable condition description
    priority: int   # Higher = checked first


TRANSITION_RULES = [
    # From ACTIVE
    TransitionRule(
        from_gear=Gear.ACTIVE,
        to_gear=Gear.PATROL,
        condition="objective_completed",
        priority=100,
    ),
    TransitionRule(
        from_gear=Gear.ACTIVE,
        to_gear=Gear.DREAM,
        condition="no_objective_or_no_work",
        priority=50,
    ),

    # From PATROL
    TransitionRule(
        from_gear=Gear.PATROL,
        to_gear=Gear.ACTIVE,
        condition="finding_selected",
        priority=100,
    ),
    TransitionRule(
        from_gear=Gear.PATROL,
        to_gear=Gear.DREAM,
        condition="no_actionable_findings",
        priority=50,
    ),

    # From DREAM
    TransitionRule(
        from_gear=Gear.DREAM,
        to_gear=Gear.ACTIVE,
        condition="proposal_approved_or_user_input",
        priority=100,
    ),
    TransitionRule(
        from_gear=Gear.DREAM,
        to_gear=Gear.PATROL,
        condition="periodic_rescan_due",
        priority=50,
    ),
]


def get_valid_transitions(from_gear: Gear) -> List[TransitionRule]:
    """Get all valid transitions from a gear, sorted by priority."""
    rules = [r for r in TRANSITION_RULES if r.from_gear == from_gear]
    return sorted(rules, key=lambda r: r.priority, reverse=True)


# =============================================================================
# GEAR STATE TRACKING
# =============================================================================

@dataclass
class GearState:
    """Current gear state with metadata."""
    current_gear: Gear
    entered_at: str  # ISO timestamp
    iterations: int
    last_transition: Optional[str]  # Transition that got us here
    patrol_findings_count: int
    dream_proposals_count: int
    last_run_at: Optional[str] = None  # ISO timestamp
    completion_epoch: Optional[str] = None

    def to_dict(self) -> dict:
        return {
            "current_gear": self.current_gear.value,
            "entered_at": self.entered_at,
            "last_run_at": self.last_run_at,
            "iterations": self.iterations,
            "last_transition": self.last_transition,
            "patrol_findings_count": self.patrol_findings_count,
            "dream_proposals_count": self.dream_proposals_count,
            "completion_epoch": self.completion_epoch,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "GearState":
        return cls(
            current_gear=Gear(data.get("current_gear", "active")),
            entered_at=data.get("entered_at", datetime.now().isoformat()),
            last_run_at=data.get("last_run_at"),
            iterations=data.get("iterations", 0),
            last_transition=data.get("last_transition"),
            patrol_findings_count=data.get("patrol_findings_count", 0),
            dream_proposals_count=data.get("dream_proposals_count", 0),
            completion_epoch=data.get("completion_epoch"),
        )


def get_default_gear_state() -> GearState:
    """Create default gear state (starts in ACTIVE)."""
    return GearState(
        current_gear=Gear.ACTIVE,
        entered_at=datetime.now().isoformat(),
        last_run_at=None,
        iterations=0,
        last_transition=None,
        patrol_findings_count=0,
        dream_proposals_count=0,
        completion_epoch=None,
    )


# =============================================================================
# RATE LIMITING
# =============================================================================

# Dream gear rate limits
DREAM_LIMITS = {
    "max_proposals_per_session": 1,     # Don't spam proposals
    "min_idle_seconds": 60,             # Must be idle for 1 min before Dream
    "max_dream_iterations": 3,          # Max Dream cycles before forcing Patrol
}

# Patrol gear rate limits
PATROL_LIMITS = {
    "max_findings_to_surface": 5,       # Don't overwhelm with findings
    "sample_violations_per_lesson": 2,  # Quick sample, not full audit
    "scan_timeout_seconds": 30,         # Fast scan
}


def should_enter_dream(gear_state: GearState, idle_seconds: float) -> bool:
    """
    Check if conditions are met to enter Dream gear.

    Args:
        gear_state: Current gear state
        idle_seconds: How long the system has been idle

    Returns:
        True if Dream gear is appropriate
    """
    # Must be idle long enough
    if idle_seconds < DREAM_LIMITS["min_idle_seconds"]:
        return False

    # Haven't hit proposal limit
    if gear_state.dream_proposals_count >= DREAM_LIMITS["max_proposals_per_session"]:
        return False

    return True


def can_generate_proposal(gear_state: GearState) -> bool:
    """Check if Dream gear can generate another proposal."""
    return gear_state.dream_proposals_count < DREAM_LIMITS["max_proposals_per_session"]


# =============================================================================
# DISPLAY HELPERS
# =============================================================================

GEAR_EMOJI = {
    Gear.ACTIVE: "⚙️",
    Gear.PATROL: "🔍",
    Gear.DREAM: "💭",
}

GEAR_LABELS = {
    Gear.ACTIVE: "Active (Executing)",
    Gear.PATROL: "Patrol (Scanning)",
    Gear.DREAM: "Dream (Reflecting)",
}


def format_gear_status(gear_state: GearState) -> str:
    """Format gear state for display."""
    gear = gear_state.current_gear
    emoji = GEAR_EMOJI.get(gear, "?")
    label = GEAR_LABELS.get(gear, "Unknown")

    lines = [
        f"{emoji} Gear: {label}",
        f"   Iterations: {gear_state.iterations}",
    ]

    if gear == Gear.PATROL:
        lines.append(f"   Findings surfaced: {gear_state.patrol_findings_count}")
    elif gear == Gear.DREAM:
        lines.append(f"   Proposals made: {gear_state.dream_proposals_count}")

    return "\n".join(lines)
