#!/usr/bin/env python3
"""
Operator's Edge - Intent Engine (v6.0)
The brain of the unified /edge command.

Intent detection determines WHAT should happen, while gear detection
determines WHERE we are in the cycle. Together they enable:

1. Single command entry (/edge does the right thing)
2. Pattern surfacing (intent.context enables matching)
3. Override support (--plan, --verify, --auto)

The Intent carries enough context that pattern surfacing becomes trivial:
    patterns = surface_patterns(intent.context, memory)

This is the foundation for the Generative Layer.
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, Any, Optional, List, Tuple
import re

from gear_config import Gear, GearState, detect_current_gear


# =============================================================================
# INTENT TYPES
# =============================================================================

class IntentAction(Enum):
    """What the system should do next."""

    # Cross-cutting actions (from user input)
    NEW_OBJECTIVE = "new_objective"           # User provided new objective text
    JUNCTION_APPROVE = "junction_approve"     # User approved pending junction
    JUNCTION_SKIP = "junction_skip"           # User skipped pending junction
    JUNCTION_DISMISS = "junction_dismiss"     # User dismissed pending junction
    SHOW_STATUS = "show_status"               # Just show status, don't act
    STOP = "stop"                             # Stop autonomous mode

    # Override actions (from flags)
    FORCE_PLAN = "force_plan"                 # --plan flag
    FORCE_VERIFY = "force_verify"             # --verify flag
    FORCE_AUTO = "force_auto"                 # --auto flag

    # ACTIVE gear actions
    NEEDS_OBJECTIVE = "needs_objective"       # No objective set
    NEEDS_PLAN = "needs_plan"                 # Objective but no plan
    NEEDS_RISKS = "needs_risks"               # Plan but no risks identified
    READY_TO_EXECUTE = "ready_to_execute"     # Execute current step
    AT_JUNCTION = "at_junction"               # Blocked at junction
    BLOCKED_STEP = "blocked_step"             # Step is blocked, needs adaptation
    READY_TO_COMPLETE = "ready_to_complete"   # All steps done, run quality gate

    # PATROL gear actions
    RUN_SCAN = "run_scan"                     # Run patrol scan
    HAS_FINDINGS = "has_findings"             # Findings ready to present
    SELECT_FINDING = "select_finding"         # User should select a finding

    # DREAM gear actions
    REFLECT = "reflect"                       # Run reflection/consolidation
    HAS_PROPOSAL = "has_proposal"             # Proposal ready to present

    # Error states
    INVALID_STATE = "invalid_state"           # Something is wrong


# =============================================================================
# INTENT DATACLASS
# =============================================================================

@dataclass
class Intent:
    """
    What the system should do next.

    The intent carries enough context for pattern surfacing:
    - action: what to do
    - gear: which mode we're in
    - context: data for pattern matching (files, step description, etc.)
    - override: if user forced a mode
    - reason: human-readable explanation
    """
    action: IntentAction
    gear: Gear
    context: Dict[str, Any] = field(default_factory=dict)
    override: Optional[str] = None  # "--plan", "--verify", "--auto"
    reason: str = ""

    def to_dict(self) -> dict:
        return {
            "action": self.action.value,
            "gear": self.gear.value,
            "context": self.context,
            "override": self.override,
            "reason": self.reason,
        }

    @property
    def is_override(self) -> bool:
        """Check if this intent came from an explicit override."""
        return self.override is not None

    @property
    def requires_user_action(self) -> bool:
        """Check if this intent requires user input before continuing."""
        return self.action in (
            IntentAction.AT_JUNCTION,
            IntentAction.SELECT_FINDING,
            IntentAction.HAS_PROPOSAL,
            IntentAction.NEEDS_OBJECTIVE,
            IntentAction.BLOCKED_STEP,
        )


# =============================================================================
# ARGUMENT PARSING
# =============================================================================

def parse_edge_args(args: str) -> Dict[str, Any]:
    """
    Parse /edge command arguments.

    Supported formats:
        /edge                    → no args
        /edge status             → show_status
        /edge off | stop         → stop
        /edge approve            → approve junction
        /edge approve 1,2        → approve specific checks
        /edge skip               → skip junction
        /edge dismiss            → dismiss junction
        /edge --plan             → force plan mode
        /edge --verify           → force verify mode
        /edge --auto             → force auto/dispatch mode
        /edge "objective text"   → new objective

    Returns dict with:
        - command: str or None (status, approve, skip, dismiss, off/stop)
        - override: str or None (--plan, --verify, --auto)
        - objective: str or None (new objective text)
        - check_ids: list or None (for approve 1,2)
    """
    if not args:
        return {"command": None, "override": None, "objective": None, "check_ids": None}

    args = args.strip()

    # Check for override flags first
    if args.startswith("--"):
        flag = args.split()[0].lower()
        if flag in ("--plan", "--verify", "--auto"):
            return {"command": None, "override": flag, "objective": None, "check_ids": None}

    # Check for command keywords
    args_lower = args.lower()

    if args_lower in ("status", "state"):
        return {"command": "status", "override": None, "objective": None, "check_ids": None}

    if args_lower in ("off", "stop"):
        return {"command": "stop", "override": None, "objective": None, "check_ids": None}

    if args_lower == "skip":
        return {"command": "skip", "override": None, "objective": None, "check_ids": None}

    if args_lower == "dismiss":
        return {"command": "dismiss", "override": None, "objective": None, "check_ids": None}

    if args_lower.startswith("approve"):
        # Check for check IDs (approve 1,2,3)
        check_ids = None
        if len(args_lower) > 7:  # "approve" + something
            rest = args[7:].strip()
            if rest:
                # Parse comma-separated numbers
                try:
                    check_ids = [int(x.strip()) for x in rest.split(",")]
                except ValueError:
                    pass  # Not numbers, ignore
        return {"command": "approve", "override": None, "objective": None, "check_ids": check_ids}

    # Check for quoted objective text
    # Matches: "objective text" or 'objective text'
    quote_match = re.match(r'^["\'](.+)["\']$', args)
    if quote_match:
        return {"command": None, "override": None, "objective": quote_match.group(1), "check_ids": None}

    # Unquoted text that isn't a command - treat as objective
    if not args_lower.startswith("-") and args_lower not in ("on",):
        return {"command": None, "override": None, "objective": args, "check_ids": None}

    return {"command": None, "override": None, "objective": None, "check_ids": None}


# =============================================================================
# INTENT DETECTION - ACTIVE GEAR
# =============================================================================

def _detect_active_intent(state: Dict[str, Any]) -> Intent:
    """
    Detect intent when in ACTIVE gear.

    ACTIVE gear progression:
        needs_objective → needs_plan → needs_risks → ready_to_execute → ready_to_complete

    With potential diversions:
        → at_junction (dangerous step)
        → blocked_step (step failed)
    """
    objective = state.get("objective", "")
    plan = state.get("plan", [])
    risks = state.get("risks", [])
    current_step_num = state.get("current_step", 1)

    # No objective?
    if not objective or not objective.strip():
        return Intent(
            action=IntentAction.NEEDS_OBJECTIVE,
            gear=Gear.ACTIVE,
            context={},
            reason="No objective set - need to define what we're working on"
        )

    # No plan?
    if not plan:
        return Intent(
            action=IntentAction.NEEDS_PLAN,
            gear=Gear.ACTIVE,
            context={"objective": objective},
            reason="Objective set but no plan - need to break it into steps"
        )

    # No risks identified? (v3.5 requirement)
    if not risks:
        return Intent(
            action=IntentAction.NEEDS_RISKS,
            gear=Gear.ACTIVE,
            context={"objective": objective, "plan_steps": len(plan)},
            reason="Plan exists but no risks identified - what could go wrong?"
        )

    # Analyze plan state
    pending = []
    in_progress = []
    blocked = []
    completed = []

    for i, step in enumerate(plan):
        if not isinstance(step, dict):
            continue
        status = step.get("status", "pending")
        step_info = {"index": i, "step": step}

        if status == "pending":
            pending.append(step_info)
        elif status == "in_progress":
            in_progress.append(step_info)
        elif status == "blocked":
            blocked.append(step_info)
        elif status == "completed":
            completed.append(step_info)

    # Blocked steps need adaptation
    if blocked:
        blocker = blocked[0]
        return Intent(
            action=IntentAction.BLOCKED_STEP,
            gear=Gear.ACTIVE,
            context={
                "blocked_step": blocker["step"],
                "blocked_index": blocker["index"],
                "objective": objective,
            },
            reason=f"Step {blocker['index'] + 1} is blocked - needs adaptation"
        )

    # All complete? Quality gate time
    if len(completed) == len(plan) and not pending and not in_progress:
        return Intent(
            action=IntentAction.READY_TO_COMPLETE,
            gear=Gear.ACTIVE,
            context={
                "objective": objective,
                "steps_completed": len(completed),
                "plan": plan,
            },
            reason="All steps complete - running quality gate"
        )

    # Find current step (prefer in_progress, then first pending)
    current = None
    if in_progress:
        current = in_progress[0]
    elif pending:
        current = pending[0]

    if not current:
        # Edge case: no actionable steps but not all complete
        return Intent(
            action=IntentAction.INVALID_STATE,
            gear=Gear.ACTIVE,
            context={"objective": objective, "plan": plan},
            reason="Invalid state: no actionable steps but objective not complete"
        )

    step = current["step"]
    step_index = current["index"]

    # Check for junction-worthy operations
    junction_check = _should_junction_for_step(step)
    if junction_check:
        junction_type, junction_reason = junction_check
        return Intent(
            action=IntentAction.AT_JUNCTION,
            gear=Gear.ACTIVE,
            context={
                "step": step,
                "step_index": step_index,
                "junction_type": junction_type,
                "junction_reason": junction_reason,
                "objective": objective,
            },
            reason=f"Junction: {junction_reason}"
        )

    # Ready to execute!
    return Intent(
        action=IntentAction.READY_TO_EXECUTE,
        gear=Gear.ACTIVE,
        context={
            "step": step,
            "step_index": step_index,
            "step_description": step.get("description", ""),
            "objective": objective,
            "progress": f"{len(completed)}/{len(plan)}",
        },
        reason=f"Execute step {step_index + 1}: {step.get('description', '')[:50]}"
    )


def _should_junction_for_step(step: Dict[str, Any]) -> Optional[Tuple[str, str]]:
    """
    Check if a step should trigger a junction.

    Returns (junction_type, reason) or None.
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
            return ("dangerous", f"Step involves '{keyword}' operation")

    # Complex operations
    complex_keywords = [
        "refactor", "redesign", "rewrite", "restructure",
        "architecture", "schema change", "breaking change",
    ]
    for keyword in complex_keywords:
        if keyword in description:
            return ("complexity", f"Step involves '{keyword}' - needs review")

    return None


# =============================================================================
# INTENT DETECTION - PATROL GEAR
# =============================================================================

def _detect_patrol_intent(state: Dict[str, Any], gear_state: Optional[GearState] = None) -> Intent:
    """
    Detect intent when in PATROL gear.

    PATROL scans for issues after objective completion.
    """
    # Check for existing findings in runtime state
    runtime = state.get("runtime", {})
    dispatch = runtime.get("dispatch", {})
    scout = dispatch.get("scout", {})
    findings = scout.get("findings", [])

    if findings:
        return Intent(
            action=IntentAction.HAS_FINDINGS,
            gear=Gear.PATROL,
            context={
                "findings_count": len(findings),
                "findings": findings[:5],  # Top 5 for context
            },
            reason=f"Found {len(findings)} actionable items"
        )

    # No findings - need to run scan
    return Intent(
        action=IntentAction.RUN_SCAN,
        gear=Gear.PATROL,
        context={},
        reason="Scanning codebase for issues..."
    )


# =============================================================================
# INTENT DETECTION - DREAM GEAR
# =============================================================================

def _detect_dream_intent(state: Dict[str, Any], gear_state: Optional[GearState] = None) -> Intent:
    """
    Detect intent when in DREAM gear.

    DREAM reflects, consolidates lessons, and proposes improvements.
    """
    # Check for existing proposal
    runtime = state.get("runtime", {})
    dream = runtime.get("dream", {})
    proposal = dream.get("pending_proposal")

    if proposal:
        return Intent(
            action=IntentAction.HAS_PROPOSAL,
            gear=Gear.DREAM,
            context={"proposal": proposal},
            reason=f"Proposal ready: {proposal.get('title', 'Untitled')}"
        )

    # Check if we can generate a proposal (rate limit)
    if gear_state and gear_state.dream_proposals_count >= 1:
        # Already made a proposal this session, just reflect
        return Intent(
            action=IntentAction.REFLECT,
            gear=Gear.DREAM,
            context={"proposals_made": gear_state.dream_proposals_count},
            reason="Reflecting on session (proposal limit reached)"
        )

    # Ready to reflect and potentially propose
    memory = state.get("memory", [])
    return Intent(
        action=IntentAction.REFLECT,
        gear=Gear.DREAM,
        context={
            "memory_count": len(memory),
            "can_propose": True,
        },
        reason="Entering reflection mode..."
    )


# =============================================================================
# MAIN INTENT DETECTION
# =============================================================================

def detect_intent(
    state: Dict[str, Any],
    args: str = "",
    gear_state: Optional[GearState] = None,
) -> Intent:
    """
    The brain of /edge - determines what should happen next.

    This is the single entry point for intent detection. It:
    1. Parses arguments for overrides/commands
    2. Checks for pending junctions
    3. Detects current gear
    4. Delegates to gear-specific detection

    The returned Intent carries enough context for:
    - Executing the appropriate action
    - Surfacing relevant patterns (Phase 2)
    - Displaying meaningful status

    Args:
        state: The active_context.yaml state
        args: Arguments passed to /edge command
        gear_state: Optional gear state (loaded if not provided)

    Returns:
        Intent with action, gear, context, and reason
    """
    # Parse arguments
    parsed = parse_edge_args(args)

    # Handle explicit commands first
    if parsed["command"] == "status":
        gear = detect_current_gear(state)
        return Intent(
            action=IntentAction.SHOW_STATUS,
            gear=gear,
            context={"show_only": True},
            reason="Showing current status"
        )

    if parsed["command"] == "stop":
        gear = detect_current_gear(state)
        return Intent(
            action=IntentAction.STOP,
            gear=gear,
            context={},
            reason="Stopping autonomous mode"
        )

    if parsed["command"] == "approve":
        gear = detect_current_gear(state)
        return Intent(
            action=IntentAction.JUNCTION_APPROVE,
            gear=gear,
            context={"check_ids": parsed.get("check_ids")},
            reason="Approving pending junction"
        )

    if parsed["command"] == "skip":
        gear = detect_current_gear(state)
        return Intent(
            action=IntentAction.JUNCTION_SKIP,
            gear=gear,
            context={},
            reason="Skipping pending junction"
        )

    if parsed["command"] == "dismiss":
        gear = detect_current_gear(state)
        return Intent(
            action=IntentAction.JUNCTION_DISMISS,
            gear=gear,
            context={},
            reason="Dismissing pending junction"
        )

    # Handle override flags
    if parsed["override"] == "--plan":
        return Intent(
            action=IntentAction.FORCE_PLAN,
            gear=Gear.ACTIVE,  # Planning is always in ACTIVE context
            context={"objective": state.get("objective", "")},
            override="--plan",
            reason="Forced into planning mode"
        )

    if parsed["override"] == "--verify":
        return Intent(
            action=IntentAction.FORCE_VERIFY,
            gear=Gear.ACTIVE,
            context={"plan": state.get("plan", [])},
            override="--verify",
            reason="Forced into verification mode"
        )

    if parsed["override"] == "--auto":
        return Intent(
            action=IntentAction.FORCE_AUTO,
            gear=detect_current_gear(state),
            context={},
            override="--auto",
            reason="Forced into autonomous mode"
        )

    # Handle new objective
    if parsed["objective"]:
        return Intent(
            action=IntentAction.NEW_OBJECTIVE,
            gear=Gear.ACTIVE,
            context={
                "new_objective": parsed["objective"],
                "previous_objective": state.get("objective"),
            },
            reason=f"New objective: {parsed['objective'][:50]}..."
        )

    # Check for pending junction (must address before continuing)
    runtime = state.get("runtime", {})
    junction = runtime.get("junction", {})
    pending = junction.get("pending")

    if pending:
        gear = detect_current_gear(state)
        return Intent(
            action=IntentAction.AT_JUNCTION,
            gear=gear,
            context={
                "junction": pending,
                "junction_type": pending.get("type"),
                "junction_reason": pending.get("payload", {}).get("reason"),
            },
            reason=f"Pending junction: {pending.get('type', 'unknown')}"
        )

    # Detect current gear and delegate
    gear = detect_current_gear(state)

    if gear == Gear.ACTIVE:
        return _detect_active_intent(state)
    elif gear == Gear.PATROL:
        return _detect_patrol_intent(state, gear_state)
    elif gear == Gear.DREAM:
        return _detect_dream_intent(state, gear_state)

    # Fallback
    return Intent(
        action=IntentAction.INVALID_STATE,
        gear=gear,
        context={},
        reason="Unable to determine intent"
    )


# =============================================================================
# INTENT FORMATTING
# =============================================================================

def format_intent_status(intent: Intent) -> str:
    """Format intent for display."""
    gear_emoji = {
        Gear.ACTIVE: "⚙️",
        Gear.PATROL: "🔍",
        Gear.DREAM: "💭",
    }

    emoji = gear_emoji.get(intent.gear, "❓")
    action = intent.action.value.replace("_", " ").title()

    lines = [
        f"{emoji} [{intent.gear.value.upper()}] {action}",
        f"   {intent.reason}",
    ]

    if intent.override:
        lines.append(f"   (override: {intent.override})")

    return "\n".join(lines)
