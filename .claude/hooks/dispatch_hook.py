#!/usr/bin/env python3
"""
Operator's Edge v3.0 - Dispatch Hook
Mechanical dispatch mode control (autopilot).

This hook intercepts /edge-yolo commands and manages dispatch state mechanically,
providing enforcement instead of behavioral compliance.

Triggered by: UserPromptSubmit (matcher: "/edge-yolo")
"""
import os
import sys
from pathlib import Path

# Add hooks directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from dispatch_utils import (
    load_dispatch_state,
    save_dispatch_state,
    start_dispatch,
    stop_dispatch,
    get_dispatch_status,
    resume_from_junction,
    check_stuck,
    check_iteration_limit,
    determine_next_action,
)
from dispatch_config import DispatchState, JunctionType, DISPATCH_DEFAULTS
from junction_utils import get_pending_junction, clear_pending_junction
from state_utils import load_yaml_state


def parse_yolo_args(user_input: str) -> dict:
    """
    Parse /edge-yolo command arguments.

    Returns:
        dict with 'command' and 'args' keys
    """
    # Find /edge-yolo in the input
    input_lower = user_input.lower()

    idx = input_lower.find("/edge-yolo")
    if idx == -1:
        return {"command": "status", "args": ""}

    after_yolo = user_input[idx + 10:].strip()

    # Parse first word as command
    parts = after_yolo.split(None, 1)
    if not parts:
        return {"command": "status", "args": ""}

    first_word = parts[0].lower()
    rest = parts[1] if len(parts) > 1 else ""

    # Known commands
    if first_word in ("on", "off", "stop", "approve", "skip", "dismiss", "status"):
        return {"command": first_word, "args": rest}
    else:
        return {"command": "status", "args": after_yolo}


def format_dispatch_status() -> str:
    """Format current dispatch status for display."""
    status = get_dispatch_status()
    state_name = status.get("state", "unknown").upper()
    enabled = status.get("enabled", False)

    lines = [
        "=" * 70,
        "DISPATCH MODE STATUS",
        "=" * 70,
        "",
        f"Mode: {'ENABLED' if enabled else 'DISABLED'}",
        f"State: {state_name}",
        "",
        f"Objective: {status.get('objective', 'None set') or 'None set'}",
    ]

    if status.get("plan_steps"):
        completed = status.get("completed_steps", 0)
        total = status.get("plan_steps", 0)
        lines.append(f"Progress: [{completed}/{total}] steps completed")

    lines.extend([
        "",
        f"Stats this session:",
        f"  - Iterations: {status.get('iteration', 0)}",
        f"  - Junctions hit: {status.get('stats', {}).get('junctions_hit', 0)}",
    ])

    # Show junction if pending
    junction = status.get("junction")
    if junction:
        reason = junction.get("reason", "No reason provided")
        if isinstance(junction.get("payload"), dict):
            reason = junction["payload"].get("reason", reason)
        lines.extend([
            "",
            "-" * 70,
            f"JUNCTION: {junction.get('type', 'unknown')}",
            "-" * 70,
            f"Reason: {reason}",
            "",
            "Options:",
            "  /edge-yolo approve  - Approve and continue",
            "  /edge-yolo skip     - Skip this action, continue",
            "  /edge-yolo dismiss  - Dismiss for 60 minutes",
            "  /edge-yolo off      - Stop dispatch mode",
        ])

    lines.extend(["", "=" * 70])
    return "\n".join(lines)


def handle_on() -> str:
    """Handle /edge-yolo on - enable dispatch mode."""
    # Check prerequisites
    yaml_state = load_yaml_state() or {}
    objective = yaml_state.get("objective")

    if not objective:
        return "\n".join([
            "=" * 70,
            "DISPATCH MODE: CANNOT START",
            "=" * 70,
            "",
            "No objective set in active_context.yaml.",
            "Set an objective first, then run /edge-yolo on",
            "",
            "=" * 70,
        ])

    # Start dispatch
    state = start_dispatch()

    lines = [
        "=" * 70,
        "DISPATCH MODE: ENABLED",
        "=" * 70,
        "",
        "Autopilot engaged. Running /edge commands until objective complete.",
        "Will stop at junctions (irreversible, external, ambiguous actions).",
        "",
        f"Objective: {objective[:60]}...",
        "",
        "Starting dispatch loop...",
        "",
        "-" * 70,
        "DISPATCH LOOP ACTIVE",
        "-" * 70,
        "",
        "Run /edge to execute the next step.",
        "The system will continue automatically until a junction or completion.",
        "",
        "Commands:",
        "  /edge          - Execute next action",
        "  /edge-yolo off - Stop autopilot",
        "",
        "=" * 70,
    ]
    return "\n".join(lines)


def handle_off() -> str:
    """Handle /edge-yolo off - disable dispatch mode."""
    state = load_dispatch_state()
    old_stats = state.get("stats", {})

    stop_dispatch("User stopped")

    lines = [
        "=" * 70,
        "DISPATCH MODE: DISABLED",
        "=" * 70,
        "",
        "Autopilot disengaged.",
        "",
        f"Session stats:",
        f"  - Iterations: {state.get('iteration', 0)}",
        f"  - Junctions hit: {old_stats.get('junctions_hit', 0)}",
        f"  - Objectives completed: {old_stats.get('objectives_completed', 0)}",
        "",
        "State preserved in active_context.yaml",
        "",
        "=" * 70,
    ]
    return "\n".join(lines)


def handle_approve() -> tuple[str, bool]:
    """Handle /edge-yolo approve - approve junction and continue."""
    pending = get_pending_junction()
    if not pending:
        return ("[APPROVE] No pending junction. Run /edge to continue.", True)

    try:
        cleared, warning = clear_pending_junction("approve")
    except TimeoutError as exc:
        return (f"[ERROR] State lock busy: {exc}", False)

    if warning:
        return (f"[WARNING] {warning}", False)

    # Also update dispatch state
    dispatch = load_dispatch_state()
    if dispatch.get("state") == DispatchState.JUNCTION.value:
        dispatch["state"] = DispatchState.RUNNING.value
        dispatch["junction"] = None
        save_dispatch_state(dispatch)

    lines = [
        "=" * 70,
        "JUNCTION APPROVED",
        "=" * 70,
        "",
        "Continuing dispatch loop...",
        "",
        "Run /edge to execute the next action.",
        "",
        "=" * 70,
    ]
    return ("\n".join(lines), True)


def handle_skip() -> tuple[str, bool]:
    """Handle /edge-yolo skip - skip current action."""
    pending = get_pending_junction()
    junction_type = pending.get("type", "unknown") if pending else "unknown"

    try:
        cleared, warning = clear_pending_junction("skip")
    except TimeoutError as exc:
        return (f"[ERROR] State lock busy: {exc}", False)

    if warning:
        return (f"[WARNING] {warning}", False)

    # Update dispatch state
    dispatch = load_dispatch_state()
    if dispatch.get("state") == DispatchState.JUNCTION.value:
        dispatch["state"] = DispatchState.RUNNING.value
        dispatch["junction"] = None
        save_dispatch_state(dispatch)

    lines = [
        "=" * 70,
        "ACTION SKIPPED",
        "=" * 70,
        "",
        f"Skipped: {junction_type} junction",
        "",
        "Attempting to find alternative path...",
        "Run /edge to continue.",
        "",
        "=" * 70,
    ]
    return ("\n".join(lines), True)


def handle_dismiss(args: str = "") -> tuple[str, bool]:
    """Handle /edge-yolo dismiss [minutes] - dismiss junction temporarily."""
    pending = get_pending_junction()
    junction_type = pending.get("type", "unknown") if pending else "unknown"

    # Parse TTL
    ttl_minutes = None
    if args.strip():
        try:
            ttl_minutes = int(args.strip())
            if ttl_minutes <= 0:
                return ("[ERROR] TTL must be positive.", False)
        except ValueError:
            return (f"[ERROR] Invalid TTL '{args}'. Use /edge-yolo dismiss <minutes>", False)

    try:
        cleared, warning = clear_pending_junction("dismiss", suppress_minutes=ttl_minutes)
    except TimeoutError as exc:
        return (f"[ERROR] State lock busy: {exc}", False)

    if warning:
        return (f"[WARNING] {warning}", False)

    # Update dispatch state
    dispatch = load_dispatch_state()
    if dispatch.get("state") == DispatchState.JUNCTION.value:
        dispatch["state"] = DispatchState.RUNNING.value
        dispatch["junction"] = None
        save_dispatch_state(dispatch)

    ttl_display = ttl_minutes if ttl_minutes else 60
    lines = [
        "=" * 70,
        "JUNCTION DISMISSED",
        "=" * 70,
        "",
        f"Dismissed: {junction_type} junction for {ttl_display} minutes",
        "Similar junctions will auto-approve during this window.",
        "",
        "Continuing dispatch loop...",
        "Run /edge to execute the next action.",
        "",
        "=" * 70,
    ]
    return ("\n".join(lines), True)


def main():
    """Main entry point - processes /edge-yolo command from user input."""
    # Get user input from stdin
    user_input = ""
    if not sys.stdin.isatty():
        user_input = sys.stdin.read()

    # Backup: environment variable
    if not user_input:
        user_input = os.environ.get("CLAUDE_USER_INPUT", "")

    # Parse command
    parsed = parse_yolo_args(user_input)
    command = parsed["command"]
    args = parsed["args"]

    # Route to handler
    if command == "on":
        print(handle_on())
    elif command in ("off", "stop"):
        print(handle_off())
    elif command == "approve":
        message, _ = handle_approve()
        print(message)
    elif command == "skip":
        message, _ = handle_skip()
        print(message)
    elif command == "dismiss":
        message, _ = handle_dismiss(args)
        print(message)
    else:
        # Default: show status
        print(format_dispatch_status())


if __name__ == "__main__":
    main()
