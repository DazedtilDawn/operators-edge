#!/usr/bin/env python3
"""
Operator's Edge - Plan Mode Detection
Automatically detects and tracks when Claude is in plan mode.

This module provides functions to:
- Set plan mode flag when EnterPlanMode is called
- Clear plan mode flag when ExitPlanMode is called
- Check if currently in plan mode

The flag file is stored at .claude/state/plan_mode
"""
import os
import sys
import json
from pathlib import Path

# Add hooks directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from state_utils import get_state_dir


def _plan_mode_flag_path() -> Path:
    """Get path to the plan mode flag file."""
    return get_state_dir() / "plan_mode"


def is_plan_mode() -> bool:
    """
    Check if Claude is currently in plan mode.

    Returns True if the plan_mode flag file exists.
    """
    return _plan_mode_flag_path().exists()


def enter_plan_mode() -> None:
    """
    Mark that Claude has entered plan mode.

    Creates the plan_mode flag file.
    """
    flag_path = _plan_mode_flag_path()
    flag_path.parent.mkdir(parents=True, exist_ok=True)
    flag_path.write_text("1")


def exit_plan_mode() -> None:
    """
    Mark that Claude has exited plan mode.

    Removes the plan_mode flag file.
    """
    flag_path = _plan_mode_flag_path()
    try:
        flag_path.unlink()
    except FileNotFoundError:
        pass


def main():
    """
    Hook entry point - handles EnterPlanMode and ExitPlanMode tool calls.

    Called by PreToolUse hook with tool info on stdin.
    """
    # Read tool info from stdin
    tool_input = ""
    if not sys.stdin.isatty():
        tool_input = sys.stdin.read()

    try:
        data = json.loads(tool_input) if tool_input else {}
    except json.JSONDecodeError:
        data = {}

    tool_name = data.get("tool_name", "")

    if tool_name == "EnterPlanMode":
        enter_plan_mode()
        # Output for hook - allow the tool to proceed
        print(json.dumps({"decision": "approve", "reason": "Plan mode flag set"}))
    elif tool_name == "ExitPlanMode":
        exit_plan_mode()
        print(json.dumps({"decision": "approve", "reason": "Plan mode flag cleared"}))
    else:
        # Not a plan mode tool - just approve
        print(json.dumps({"decision": "approve"}))


if __name__ == "__main__":
    main()
