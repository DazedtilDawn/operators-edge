#!/usr/bin/env python3
"""
Operator's Edge v3.9 - Edge Skill Hook
Mechanically executes gear engine when /edge is invoked.

This hook intercepts /edge commands and runs the gear engine,
providing mechanical enforcement instead of behavioral compliance.

Triggered by: UserPromptSubmit (matcher: "/edge")
"""
import json
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
        pending = sum(1 for s in plan if isinstance(s, dict) and s.get("status") == "pending")
        completed = sum(1 for s in plan if isinstance(s, dict) and s.get("status") == "completed")
        lines.append(f"Plan: {len(plan)} steps ({completed} completed, {pending} pending)")

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


def handle_approve() -> str:
    """Handle /edge approve - clear junction and continue."""
    # Load dispatch state to check for pending junction
    state_dir = Path(os.environ.get("CLAUDE_PROJECT_DIR", ".")) / ".claude" / "state"
    dispatch_file = state_dir / "dispatch_state.json"

    if dispatch_file.exists():
        try:
            dispatch = json.loads(dispatch_file.read_text())
            if dispatch.get("pending_junction"):
                # Clear the junction
                dispatch["pending_junction"] = None
                dispatch["junction_type"] = None
                dispatch_file.write_text(json.dumps(dispatch, indent=2))
                return "[APPROVED] Junction cleared. Continuing execution..."
        except (json.JSONDecodeError, IOError):
            pass

    return "[APPROVE] No pending junction found. Running gear cycle..."


def handle_skip() -> str:
    """Handle /edge skip - skip current action."""
    state_dir = Path(os.environ.get("CLAUDE_PROJECT_DIR", ".")) / ".claude" / "state"
    dispatch_file = state_dir / "dispatch_state.json"

    if dispatch_file.exists():
        try:
            dispatch = json.loads(dispatch_file.read_text())
            if dispatch.get("pending_junction"):
                junction_type = dispatch.get("junction_type", "unknown")
                dispatch["pending_junction"] = None
                dispatch["junction_type"] = None
                dispatch["skipped_last"] = True
                dispatch_file.write_text(json.dumps(dispatch, indent=2))
                return f"[SKIPPED] {junction_type} junction skipped. Trying next action..."
        except (json.JSONDecodeError, IOError):
            pass

    return "[SKIP] Nothing to skip. Running gear cycle..."


def handle_run(args: str = "") -> str:
    """Handle /edge (run) - execute gear cycle."""
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
        _save_junction_state(result.junction_type, result.junction_reason)

    # Add continuation hint
    if result.continue_loop and not result.junction_hit:
        lines.extend([
            "",
            "[Loop continues - run /edge again or /edge-yolo for autopilot]",
        ])

    lines.extend(["", "=" * 70])
    return "\n".join(lines)


def _save_junction_state(junction_type: str, reason: str):
    """Save junction state for later approve/skip handling."""
    state_dir = Path(os.environ.get("CLAUDE_PROJECT_DIR", ".")) / ".claude" / "state"
    state_dir.mkdir(parents=True, exist_ok=True)
    dispatch_file = state_dir / "dispatch_state.json"

    try:
        if dispatch_file.exists():
            dispatch = json.loads(dispatch_file.read_text())
        else:
            dispatch = {"enabled": True, "iteration": 0}

        dispatch["pending_junction"] = True
        dispatch["junction_type"] = junction_type
        dispatch["junction_reason"] = reason

        dispatch_file.write_text(json.dumps(dispatch, indent=2))
    except (json.JSONDecodeError, IOError):
        pass


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
        result = handle_approve()
        print(result)
        if "Continuing" in result or "No pending" in result:
            # Also run a gear cycle after approving
            print(handle_run())
    elif command == "skip":
        result = handle_skip()
        print(result)
        if "Trying next" in result or "Nothing to skip" in result:
            print(handle_run())
    else:
        # Default: run gear cycle
        print(handle_run(args))


if __name__ == "__main__":
    main()
