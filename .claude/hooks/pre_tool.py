#!/usr/bin/env python3
"""
Operator's Edge - Pre-Tool Gate
Unified enforcement before any tool execution.

Enforces:
1. Dangerous command blocking (rm -rf, git reset --hard, etc.)
2. Deploy/push confirmation gates
3. Retry blocking for repeated failures
4. Plan requirement for file edits

Note: YOLO/Dispatch mode is handled by the /edge-yolo command orchestration,
not by this hook. This hook only enforces safety constraints.
"""
import json
import os
import re
import sys
from pathlib import Path

# Add hooks directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from edge_utils import (
    load_yaml_state,
    get_recent_failures,
    respond,
    get_state_dir,
    get_evals_config,
    auto_triage,
    start_eval_run,
    load_eval_state,
    save_eval_state,
)


def check_bash_command(cmd):
    """
    Gate Bash commands by risk level.
    Returns: (decision, reason) or None to continue checking
    """
    cmd_norm = cmd.strip()

    # HARD BLOCK - Never allow these
    BLOCK_PATTERNS = [
        (r"(^|\s|&&|\|)rm\s+-rf\s+/", "Blocked: rm -rf on root"),
        (r"(^|\s|&&|\|)rm\s+-rf\s+~", "Blocked: rm -rf on home"),
        (r"(^|\s|&&|\|)rm\s+-rf\s+\.\.", "Blocked: rm -rf on parent"),
        (r"(^|\s|&&|\|)git\s+reset\s+--hard", "Blocked: git reset --hard"),
        (r"(^|\s|&&|\|)git\s+clean\s+-fdx", "Blocked: git clean -fdx"),
        (r"(^|\s|&&|\|)git\s+push\s+.*--force", "Blocked: force push"),
        (r"(^|\s|&&|\|)chmod\s+-R\s+777", "Blocked: chmod 777 recursive"),
        (r"(^|\s|&&|\|):()\s*{\s*:|:&\s*};:", "Blocked: fork bomb"),
        (r"(^|\s|&&|\|)mkfs\.", "Blocked: filesystem format"),
        (r"(^|\s|&&|\|)dd\s+if=.*/dev/", "Blocked: dd from device"),
    ]

    for pattern, reason in BLOCK_PATTERNS:
        if re.search(pattern, cmd_norm, re.IGNORECASE):
            return ("block", reason)

    # ASK CONFIRMATION - Risky but sometimes necessary
    ASK_PATTERNS = [
        (r"(^|\s|&&|\|)git\s+push(\s|$)", "Confirm: git push"),
        (r"(^|\s|&&|\|)rm\s+(-r\s+)?[^|&;]+", "Confirm: file deletion"),
        (r"(^|\s|&&|\|)kubectl\s+", "Confirm: kubernetes operation"),
        (r"(^|\s|&&|\|)terraform\s+", "Confirm: terraform operation"),
        (r"(^|\s|&&|\|)docker\s+push", "Confirm: docker push"),
        (r"(^|\s|&&|\|)npm\s+publish", "Confirm: npm publish"),
        (r"(^|\s|&&|\|)aws\s+", "Confirm: AWS operation"),
        (r"(^|\s|&&|\|)gcloud\s+", "Confirm: GCloud operation"),
    ]

    for pattern, reason in ASK_PATTERNS:
        if re.search(pattern, cmd_norm, re.IGNORECASE):
            return ("ask", f"{reason}: {cmd_norm[:80]}")

    return None

def check_retry_blocking(cmd):
    """
    Block commands that have failed recently without a new approach.
    """
    failures = get_recent_failures(cmd, window_minutes=15)
    if failures >= 2:
        return ("block",
                f"This command failed {failures} times recently. "
                "Explain your new approach before retrying.")
    return None

def check_plan_requirement(tool_name, tool_input):
    """
    Require a plan in active_context.yaml before allowing edits.
    v3.5: Also requires risks to be identified (failure mode planning).
    """
    if tool_name not in ("Edit", "Write", "NotebookEdit"):
        return None

    # Allow writes to specific safe paths without any checks
    file_path = tool_input.get("file_path", "")
    safe_paths = [
        "active_context.yaml",
        ".proof/",
        "checklist.md",
        "archive.md"
    ]
    if any(safe in file_path for safe in safe_paths):
        return None

    state = load_yaml_state()
    if state is None:
        return ("block",
                "Cannot edit files: active_context.yaml is missing or invalid. "
                "Run /edge-plan first.")

    plan = state.get("plan", [])
    if not plan:
        return ("ask",
                "No plan exists in active_context.yaml. "
                "Consider running /edge-plan first, or confirm to proceed without a plan.")

    # v3.5: Require risks to be identified
    risks = state.get("risks", [])
    if not risks:
        return ("ask",
                "No risks identified in active_context.yaml. "
                "What could go wrong? Add at least one risk before proceeding, "
                "or confirm to proceed without failure mode planning.")

    return None

def main():
    try:
        data = json.load(sys.stdin)
    except json.JSONDecodeError:
        respond("approve", "Could not parse input, allowing by default")
        return

    tool_name = data.get("tool_name", "")
    tool_input = data.get("tool_input", {}) or {}

    # Check 1: Bash-specific risk gating
    if tool_name == "Bash":
        cmd = tool_input.get("command", "")

        # Check dangerous commands (hard block)
        result = check_bash_command(cmd)
        if result and result[0] == "block":
            respond(*result)

        # Check retry blocking
        retry_result = check_retry_blocking(cmd)
        if retry_result:
            respond(*retry_result)

        # If we had an "ask" from bash check (not hard block), apply it now
        if result and result[0] == "ask":
            respond(*result)

    # Check 2: Plan requirement for edits
    result = check_plan_requirement(tool_name, tool_input)
    if result:
        respond(*result)

    # Eval automation: capture pre-tool snapshot for write/edit tools
    if tool_name in ("Edit", "Write", "NotebookEdit"):
        state = load_yaml_state()
        evals_config = get_evals_config(state)
        evals_config, _triage = auto_triage(state, evals_config, tool_name)

        if evals_config.get("enabled", True) and evals_config.get("mode") != "manual":
            if evals_config.get("level", 0) >= 1 and evals_config.get("snapshots", {}).get("enabled", True):
                pending_run = start_eval_run(evals_config, tool_name)
                eval_state = load_eval_state()
                eval_state["pending_run"] = pending_run
                eval_state["triage"] = evals_config.get("triage", {})
                save_eval_state(eval_state)

    # All checks passed
    respond("approve", "Passed all pre-tool checks")

if __name__ == "__main__":
    main()
