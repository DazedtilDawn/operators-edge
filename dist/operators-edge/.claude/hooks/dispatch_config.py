#!/usr/bin/env python3
"""
Operator's Edge - Dispatch Mode Configuration
Junction classification and autopilot settings for autonomous execution.

Dispatch Mode runs /edge commands automatically, stopping only at "junctions":
- Irreversible actions (git push, delete, deploy)
- External effects (API calls, external services)
- Ambiguous decisions (multiple valid approaches)
- Blocked steps (failures requiring adaptation)
"""

import re
from enum import Enum
from typing import Optional, Tuple

# =============================================================================
# DISPATCH STATES
# =============================================================================

class DispatchState(Enum):
    """States for the dispatch loop."""
    IDLE = "idle"              # Not running
    RUNNING = "running"        # Executing automatically
    JUNCTION = "junction"      # Paused at decision point
    COMPLETE = "complete"      # Objective achieved
    STUCK = "stuck"            # Can't proceed, need help


# =============================================================================
# JUNCTION TYPES
# =============================================================================

class JunctionType(Enum):
    """Types of junctions that pause autopilot."""
    IRREVERSIBLE = "irreversible"  # Can't undo (git push, delete)
    EXTERNAL = "external"          # Affects outside world (deploy, API)
    AMBIGUOUS = "ambiguous"        # Multiple valid paths, need human choice
    BLOCKED = "blocked"            # Step failed, needs adaptation
    NONE = "none"                  # Not a junction, proceed automatically


# =============================================================================
# JUNCTION DETECTION PATTERNS
# =============================================================================

# Bash commands that are irreversible
IRREVERSIBLE_BASH = [
    r"git\s+push",
    r"git\s+reset\s+--hard",
    r"git\s+clean\s+-fd",
    r"rm\s+(-rf?\s+)?[^|&;]+",  # Any rm command
    r"drop\s+table",
    r"truncate\s+",
]

# Bash commands with external effects
EXTERNAL_BASH = [
    r"kubectl\s+(apply|delete|scale)",
    r"terraform\s+(apply|destroy)",
    r"docker\s+push",
    r"(npm|yarn)\s+publish",
    r"aws\s+",
    r"gcloud\s+",
    r"curl\s+.*-X\s*(POST|PUT|DELETE|PATCH)",
    r"gh\s+pr\s+create",
    r"gh\s+release\s+create",
]

# Edge command outputs that indicate ambiguity
AMBIGUOUS_SIGNALS = [
    r"multiple\s+(valid\s+)?approach",
    r"could\s+(also|either)",
    r"which\s+(option|approach|method)",
    r"choose\s+between",
    r"alternatives?:",
    r"option\s+[a-d1-4]:",
]

# Edge command outputs that indicate blocked state
BLOCKED_SIGNALS = [
    r"blocked",
    r"failed",
    r"error:",
    r"cannot\s+proceed",
    r"stuck",
    r"mismatch",
    r"unexpected",
]

# Edge commands that are always safe to auto-execute
AUTO_EDGE_COMMANDS = [
    "edge",           # Smart orchestrator (determines next action)
    "edge-step",      # Execute current step (if step itself isn't junction)
    "edge-prune",     # Cleanup completed work
    "edge-score",     # Self-assessment
]

# Edge commands that are junctions (need approval)
JUNCTION_EDGE_COMMANDS = [
    "edge-plan",      # Creating/modifying plan is a decision point
    "edge-adapt",     # Adaptation is a decision point
    "edge-research",  # External research is a decision point
    "edge-brainstorm", # Ideation is a decision point
]


# =============================================================================
# DISPATCH SETTINGS
# =============================================================================

DISPATCH_DEFAULTS = {
    "max_iterations": 50,        # Safety limit on loop iterations
    "stuck_threshold": 3,        # Retries before declaring stuck
    "auto_prune": True,          # Auto-prune after completing objective
    "verbose": True,             # Show what's being executed
}


# =============================================================================
# STATE FILE
# =============================================================================

DISPATCH_STATE_FILE = ".claude/state/dispatch_state.json"


# =============================================================================
# CLASSIFICATION FUNCTIONS
# =============================================================================

def classify_bash_junction(cmd: str) -> JunctionType:
    """
    Classify a bash command by junction type.

    Returns:
        JunctionType indicating whether this is a junction and why
    """
    cmd_stripped = cmd.strip()

    # Check irreversible patterns
    for pattern in IRREVERSIBLE_BASH:
        if re.search(pattern, cmd_stripped, re.IGNORECASE):
            return JunctionType.IRREVERSIBLE

    # Check external effect patterns
    for pattern in EXTERNAL_BASH:
        if re.search(pattern, cmd_stripped, re.IGNORECASE):
            return JunctionType.EXTERNAL

    # Not a junction
    return JunctionType.NONE


def classify_edge_command(cmd: str) -> JunctionType:
    """
    Classify an /edge command by junction type.

    Args:
        cmd: The edge command name (without /)

    Returns:
        JunctionType indicating whether this is a junction
    """
    cmd_clean = cmd.strip().lower().replace("/", "")

    if cmd_clean in [c.replace("-", "") for c in JUNCTION_EDGE_COMMANDS]:
        return JunctionType.AMBIGUOUS

    if cmd_clean in [c.replace("-", "") for c in AUTO_EDGE_COMMANDS]:
        return JunctionType.NONE

    # Unknown commands are junctions by default (safety)
    return JunctionType.AMBIGUOUS


def detect_output_junction(output: str) -> Tuple[JunctionType, Optional[str]]:
    """
    Analyze command output for junction signals.

    Args:
        output: The output text from a command

    Returns:
        Tuple of (JunctionType, reason if junction)
    """
    output_lower = output.lower()

    # Check for blocked signals
    for pattern in BLOCKED_SIGNALS:
        if re.search(pattern, output_lower):
            return (JunctionType.BLOCKED, f"Detected: {pattern}")

    # Check for ambiguity signals
    for pattern in AMBIGUOUS_SIGNALS:
        if re.search(pattern, output_lower):
            return (JunctionType.AMBIGUOUS, f"Detected: {pattern}")

    return (JunctionType.NONE, None)


def is_junction(junction_type: JunctionType) -> bool:
    """Check if a junction type requires pausing."""
    return junction_type != JunctionType.NONE


# =============================================================================
# DEFAULT STATE
# =============================================================================

def get_default_dispatch_state() -> dict:
    """Return default dispatch state structure."""
    return {
        "enabled": False,
        "state": DispatchState.IDLE.value,
        "current_action": None,
        "junction": None,
        "iteration": 0,
        "stuck_count": 0,
        "history": [],  # Recent actions for context
        "stats": {
            "auto_executed": 0,
            "junctions_hit": 0,
            "total_iterations": 0
        }
    }
