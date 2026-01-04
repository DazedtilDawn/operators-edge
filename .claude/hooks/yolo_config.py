#!/usr/bin/env python3
"""
Operator's Edge - YOLO Mode Configuration
Trust levels, action categories, and default settings for autonomous execution.
"""

import re
from enum import Enum
from typing import Optional

# =============================================================================
# TRUST LEVELS
# =============================================================================

class TrustLevel(Enum):
    """Trust levels for action classification."""
    AUTO = "auto"           # Execute immediately, no confirmation
    SUPERVISED = "supervised"  # Stage for batch approval
    BLOCKED = "blocked"     # Always require explicit confirmation


# =============================================================================
# DEFAULT TOOL TRUST LEVELS
# =============================================================================

# Tools that are always safe (read-only, no state changes)
AUTO_TOOLS = frozenset([
    "Read", "Glob", "Grep", "LSP", "WebFetch", "WebSearch",
    "AskUserQuestion", "TodoWrite", "Task", "TaskOutput"
])

# Tools that modify state but are common development operations
SUPERVISED_TOOLS = frozenset([
    "Edit", "Write", "NotebookEdit"
])

# Tools that need command-level classification
COMMAND_CLASSIFIED_TOOLS = frozenset([
    "Bash"
])


# =============================================================================
# BASH COMMAND PATTERNS
# =============================================================================

# Commands that are read-only (auto in YOLO mode)
AUTO_BASH_PATTERNS = [
    r"^git\s+(status|diff|log|branch|show|blame|stash\s+list)",
    r"^(ls|pwd|cat|head|tail|wc|file|which|where|type)\s",
    r"^(echo|printf)\s",
    r"^(npm|yarn|pnpm)\s+(test|run\s+(test|lint|check|typecheck))",
    r"^pytest\b",
    r"^(tsc|eslint|prettier)\s+.*--.*check",
    r"^python3?\s+-c\s+",  # Python one-liners (usually checks)
    r"^grep\s",
    r"^find\s",
    r"^curl\s+.*-I",  # HEAD requests
]

# Commands that modify state (supervised in YOLO mode)
SUPERVISED_BASH_PATTERNS = [
    r"^git\s+(add|commit|stash\s+(push|pop|drop))",
    r"^(mkdir|touch|cp|mv)\s",
    r"^(npm|yarn|pnpm)\s+install",
    r"^pip\s+install",
    r"^python3?\s+",  # Python scripts (could modify)
    r"^chmod\s+(?!.*777)",  # chmod except 777
]

# Commands that are always blocked (hard block, never auto)
BLOCKED_BASH_PATTERNS = [
    r"rm\s+-rf\s+/",
    r"rm\s+-rf\s+~",
    r"rm\s+-rf\s+\.\.",
    r"git\s+reset\s+--hard",
    r"git\s+clean\s+-fdx",
    r"git\s+push\s+.*--force",
    r"chmod\s+-R\s+777",
    r":\(\)\s*{\s*:|:&\s*};:",  # Fork bomb
    r"mkfs\.",
    r"dd\s+if=.*/dev/",
]

# Commands that have external effects (always confirm, but not hard blocked)
CONFIRM_BASH_PATTERNS = [
    r"^git\s+push(\s|$)",
    r"^rm\s+(-r\s+)?[^|&;]+",  # Any rm command
    r"^kubectl\s+",
    r"^terraform\s+",
    r"^docker\s+push",
    r"^(npm|yarn)\s+publish",
    r"^aws\s+",
    r"^gcloud\s+",
]


# =============================================================================
# BATCH SETTINGS
# =============================================================================

BATCH_DEFAULTS = {
    "max_staged": 10,       # Prompt approval after N staged actions
    "timeout_minutes": 5,   # Prompt approval after N minutes of activity
}


# =============================================================================
# YOLO STATE FILE
# =============================================================================

YOLO_STATE_FILE = ".claude/state/yolo_state.json"
YOLO_CONFIG_FILE = ".claude/state/yolo_config.yaml"


# =============================================================================
# CLASSIFICATION FUNCTIONS
# =============================================================================

def classify_bash_command(cmd: str) -> TrustLevel:
    """
    Classify a bash command by trust level.

    Order matters:
    1. Check BLOCKED patterns first (hard blocks)
    2. Check CONFIRM patterns (external effects)
    3. Check AUTO patterns (read-only)
    4. Check SUPERVISED patterns (local modifications)
    5. Default to SUPERVISED
    """
    cmd_stripped = cmd.strip()

    # Hard blocked - never allow
    for pattern in BLOCKED_BASH_PATTERNS:
        if re.search(pattern, cmd_stripped, re.IGNORECASE):
            return TrustLevel.BLOCKED

    # Confirm required - external effects
    for pattern in CONFIRM_BASH_PATTERNS:
        if re.search(pattern, cmd_stripped, re.IGNORECASE):
            return TrustLevel.BLOCKED

    # Auto - read-only operations
    for pattern in AUTO_BASH_PATTERNS:
        if re.search(pattern, cmd_stripped, re.IGNORECASE):
            return TrustLevel.AUTO

    # Supervised - local modifications
    for pattern in SUPERVISED_BASH_PATTERNS:
        if re.search(pattern, cmd_stripped, re.IGNORECASE):
            return TrustLevel.SUPERVISED

    # Default to supervised for unknown commands
    return TrustLevel.SUPERVISED


def classify_action(tool_name: str, tool_input: dict, user_overrides: dict = None) -> TrustLevel:
    """
    Classify an action by trust level.

    Args:
        tool_name: Name of the tool being invoked
        tool_input: Input parameters for the tool
        user_overrides: Optional dict of user trust level overrides

    Returns:
        TrustLevel indicating how to handle this action in YOLO mode
    """
    # Check user overrides first
    if user_overrides:
        # Check tool-level override
        if tool_name in user_overrides:
            return TrustLevel(user_overrides[tool_name])

        # Check command-specific override for Bash
        if tool_name == "Bash":
            cmd = tool_input.get("command", "")
            for pattern, level in user_overrides.items():
                if pattern.startswith("bash:") and re.search(pattern[5:], cmd, re.IGNORECASE):
                    return TrustLevel(level)

    # Auto tools (read-only)
    if tool_name in AUTO_TOOLS:
        return TrustLevel.AUTO

    # Supervised tools (state modification)
    if tool_name in SUPERVISED_TOOLS:
        return TrustLevel.SUPERVISED

    # Command-classified tools (Bash)
    if tool_name in COMMAND_CLASSIFIED_TOOLS:
        cmd = tool_input.get("command", "")
        return classify_bash_command(cmd)

    # Default to supervised for unknown tools
    return TrustLevel.SUPERVISED


def is_hard_blocked(tool_name: str, tool_input: dict) -> bool:
    """
    Check if an action is hard-blocked (never auto, even with overrides).
    """
    if tool_name != "Bash":
        return False

    cmd = tool_input.get("command", "").strip()
    for pattern in BLOCKED_BASH_PATTERNS:
        if re.search(pattern, cmd, re.IGNORECASE):
            return True

    return False


# =============================================================================
# YOLO STATE MANAGEMENT
# =============================================================================

def get_default_yolo_state() -> dict:
    """Return default YOLO state structure."""
    return {
        "enabled": False,
        "staged_actions": [],
        "batch_start_time": None,
        "stats": {
            "auto_executed": 0,
            "staged": 0,
            "blocked": 0
        }
    }


def get_default_yolo_config() -> dict:
    """Return default YOLO configuration."""
    return {
        "enabled": False,
        "trust_overrides": {},
        "batch": BATCH_DEFAULTS.copy()
    }
