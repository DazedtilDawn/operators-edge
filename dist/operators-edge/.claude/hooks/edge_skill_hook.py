#!/usr/bin/env python3
"""
Operator's Edge v3.9 - Edge Skill Hook
Mechanically executes gear engine when /edge is invoked.

This hook intercepts /edge commands and runs the gear engine,
providing mechanical enforcement instead of behavioral compliance.

Triggered by: UserPromptSubmit (matcher: "/edge")
"""
import os
import sys
from pathlib import Path

# Add hooks directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from gear_engine import (
    run_gear_engine,
    load_gear_state,
    save_gear_state,
    reset_gear_state,
    format_engine_status,
)
from gear_config import (
    Gear,
    GearTransition,
    detect_current_gear,
    format_gear_status,
    GEAR_EMOJI,
)
from state_utils import load_yaml_state
from junction_utils import (
    get_pending_junction,
    set_pending_junction,
    clear_pending_junction,
)


def parse_edge_args(user_input: str) -> dict:
    """
    Parse /edge command arguments.

    Returns:
        dict with 'command' and 'args' keys
    """
    # Find /edge in the input
    input_lower = user_input.lower()

    # Extract everything after /edge
    idx = input_lower.find("/edge")
    if idx == -1:
        return {"command": "run", "args": ""}

    after_edge = user_input[idx + 5:].strip()

    # Check for subcommands
    if after_edge.startswith("-"):
        # This is a subcommand like /edge-plan, /edge-step
        # Let those be handled by their own skills
        return {"command": "subcommand", "args": after_edge}

    # Parse first word as command
    parts = after_edge.split(None, 1)
    if not parts:
        return {"command": "run", "args": ""}

    first_word = parts[0].lower()
    rest = parts[1] if len(parts) > 1 else ""

    # Known commands
    if first_word in ("status", "on", "off", "stop", "approve", "skip"):
        return {"command": first_word, "args": rest}
    elif first_word.startswith("dismiss"):
        return {"command": "dismiss", "args": rest}
    else:
        # Treat as run with extra context
        return {"command": "run", "args": after_edge}


def handle_status() -> str:
    """Handle /edge status - show gear state without executing."""
    gear_state = load_gear_state()
    state = load_yaml_state() or {}
    detected = detect_current_gear(state)
    pending_junction = get_pending_junction()

    lines = [
        "=" * 70,
        "OPERATOR'S EDGE v3.9 - GEAR STATUS",
        "=" * 70,
        "",
        format_gear_status(gear_state),
        "",
        f"Detected gear (from state): {GEAR_EMOJI.get(detected, '?')} {detected.value.upper()}",
        "",
        f"Objective: {state.get('objective', '(none)')[:50]}",
    ]

    plan = state.get("plan", [])
    if plan:
        pending_steps_count = sum(1 for s in plan if isinstance(s, dict) and s.get("status") == "pending")
        completed = sum(1 for s in plan if isinstance(s, dict) and s.get("status") == "completed")
        lines.append(f"Plan: {len(plan)} steps ({completed} completed, {pending_steps_count} pending)")

    if pending_junction:
        reason = (pending_junction.get("payload") or {}).get("reason", "No reason provided")
        lines.extend([
            "",
            f"Pending junction: {pending_junction.get('type')} - {reason}",
        ])

    lines.extend(["", "=" * 70])
    return "\n".join(lines)


def handle_stop() -> str:
    """Handle /edge stop - disable dispatch mode."""
    gear_state = load_gear_state()

    # Reset to default state
    reset_gear_state()

    lines = [
        "=" * 70,
        "OPERATOR'S EDGE v3.9 - DISPATCH STOPPED",
        "=" * 70,
        "",
        "Session stats:",
        f"  Patrol findings surfaced: {gear_state.patrol_findings_count}",
        f"  Dream proposals made: {gear_state.dream_proposals_count}",
        f"  Iterations: {gear_state.iterations}",
        "",
        "Gear state reset. Run /edge to restart.",
        "=" * 70,
    ]
    return "\n".join(lines)


def handle_approve() -> tuple[str, bool]:
    """Handle /edge approve - clear junction and continue."""
    try:
        pending = clear_pending_junction("approve")
    except TimeoutError as exc:
        return (f"[ERROR] State lock busy while clearing junction. {exc}", False)
    if pending:
        return ("[APPROVED] Junction cleared. Continuing execution...", True)
    return ("[APPROVE] No pending junction found. Running gear cycle...", True)


def handle_skip() -> tuple[str, bool]:
    """Handle /edge skip - skip current action."""
    pending = get_pending_junction()
    junction_type = pending.get("type", "unknown") if pending else "unknown"
    try:
        cleared = clear_pending_junction("skip")
    except TimeoutError as exc:
        return (f"[ERROR] State lock busy while skipping junction. {exc}", False)
    if cleared:
        return (f"[SKIPPED] {junction_type} junction skipped. Trying next action...", True)
    return ("[SKIP] Nothing to skip. Running gear cycle...", True)


def handle_dismiss() -> tuple[str, bool]:
    """Handle /edge dismiss - dismiss current junction temporarily."""
    pending = get_pending_junction()
    junction_type = pending.get("type", "unknown") if pending else "unknown"
    try:
        cleared = clear_pending_junction("dismiss")
    except TimeoutError as exc:
        return (f"[ERROR] State lock busy while dismissing junction. {exc}", False)
    if cleared:
        return (f"[DISMISSED] {junction_type} junction dismissed. Continuing...", True)
    return ("[DISMISS] Nothing to dismiss. Running gear cycle...", True)


def handle_run(args: str = "") -> str:
    """Handle /edge (run) - execute gear cycle."""
    pending = get_pending_junction()
    if pending:
        reason = (pending.get("payload") or {}).get("reason", "No reason provided")
        lines = [
            "=" * 70,
            "OPERATOR'S EDGE v3.9 - JUNCTION PENDING",
            "=" * 70,
            "",
            f"JUNCTION: {pending.get('type')}",
            "",
            f"Reason: {reason}",
            "",
            "Options:",
            "  /edge approve  - Continue with proposed action",
            "  /edge skip     - Skip this, try next",
            "  /edge dismiss  - Dismiss this junction",
            "  /edge stop     - Stop autonomous mode",
            "",
            "=" * 70,
        ]
        return "\n".join(lines)

    state = load_yaml_state() or {}
    project_dir = Path(os.environ.get("CLAUDE_PROJECT_DIR", "."))

    # Run the gear engine
    result = run_gear_engine(state, project_dir)

    # Build output
    gear_emoji = GEAR_EMOJI.get(result.gear_executed, "?")
    gear_name = result.gear_executed.value.upper()

    lines = [
        "=" * 70,
        f"OPERATOR'S EDGE v3.9 - [{gear_name}] Gear",
        "=" * 70,
        "",
    ]

    # Add the gear's display message
    lines.append(result.display_message)

    # Handle transitions
    if result.transitioned and result.new_gear:
        new_emoji = GEAR_EMOJI.get(result.new_gear, "?")
        new_name = result.new_gear.value.upper()
        lines.extend([
            "",
            "-" * 70,
            f"TRANSITION: {gear_emoji} {gear_name} -> {new_emoji} {new_name}",
            "-" * 70,
        ])

    # Handle junctions
    if result.junction_hit:
        lines.extend([
            "",
            "-" * 70,
            f"JUNCTION: {result.junction_type}",
            "-" * 70,
            "",
            f"Reason: {result.junction_reason}",
            "",
            "Options:",
            "  /edge approve  - Continue with proposed action",
            "  /edge skip     - Skip this, try next",
            "  /edge stop     - Stop autonomous mode",
        ])

        # Save junction state for approve/skip handling
        try:
            set_pending_junction(
                result.junction_type,
                {"reason": result.junction_reason, "gear": gear_name.lower()},
                source="edge"
            )
        except TimeoutError as exc:
            lines.extend([
                "",
                f"[ERROR] State lock busy while saving junction. {exc}",
                "Try again in a moment. If this persists, ensure no other /edge run is active.",
                "=" * 70,
            ])
            return "\n".join(lines)

    # Add continuation hint
    if result.continue_loop and not result.junction_hit:
        lines.extend([
            "",
            "[Loop continues - run /edge again or /edge-yolo for autopilot]",
        ])

    lines.extend(["", "=" * 70])
    return "\n".join(lines)


def main():
    """Main entry point - processes /edge command from user input."""
    # Get user input from stdin (Claude Code passes it via hook)
    user_input = ""
    if not sys.stdin.isatty():
        user_input = sys.stdin.read()

    # Also check environment variable (backup method)
    if not user_input:
        user_input = os.environ.get("CLAUDE_USER_INPUT", "")

    # Parse the command
    parsed = parse_edge_args(user_input)
    command = parsed["command"]
    args = parsed["args"]

    # Handle subcommands (let their skills handle them)
    if command == "subcommand":
        # Don't interfere with /edge-plan, /edge-step, etc.
        sys.exit(0)

    # Route to appropriate handler
    if command == "status":
        print(handle_status())
    elif command in ("off", "stop"):
        print(handle_stop())
    elif command == "approve":
        message, should_run = handle_approve()
        print(message)
        if should_run:
            # Also run a gear cycle after approving
            print(handle_run())
    elif command == "skip":
        message, should_run = handle_skip()
        print(message)
        if should_run:
            print(handle_run())
    elif command == "dismiss":
        message, should_run = handle_dismiss()
        print(message)
        if should_run:
            print(handle_run())
    else:
        # Default: run gear cycle
        print(handle_run(args))


if __name__ == "__main__":
    main()
