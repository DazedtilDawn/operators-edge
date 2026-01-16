#!/usr/bin/env python3
"""
Operator's Edge - Pre-Tool Gate
Unified enforcement before any tool execution.

Enforces:
1. Dangerous command blocking (rm -rf, git reset --hard, etc.)
2. Deploy/push confirmation gates
3. Retry blocking for repeated failures
4. Plan requirement for file edits
5. v7.0: Graduated rules enforcement with outcome tracking

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

# v7.0: Pending correlation ID for outcome tracking
_pending_correlation_id = None


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

def check_relevant_lessons(tool_name, tool_input, state):
    """
    Surface lessons relevant to this tool execution (v3.10).
    Returns list of relevant lessons (guidance, not a gate).
    """
    if tool_name not in ("Edit", "Write", "NotebookEdit", "Bash"):
        return []

    if not state:
        return []

    try:
        from memory_utils import surface_relevant_memory

        # Build context from tool input
        file_path = tool_input.get("file_path", "")
        command = tool_input.get("command", "")
        context = f"{tool_name} {file_path} {command}"

        # v3.12: Pass file_path for learned pattern filtering
        return surface_relevant_memory(state, context, file_path=file_path if file_path else None)
    except (ImportError, Exception):
        return []


def check_intent_confirmed(tool_name, tool_input):
    """
    Require intent to be confirmed before planning/editing (v1.0 Understanding-First).

    Intent verification ensures we understand what the user wants before we start
    making changes. This is the first gate in the Understanding → Plan → Execute → Verify rail.

    BACKWARD COMPATIBILITY: This check only applies when:
    - The intent section exists in active_context.yaml
    - AND user_wants is set (indicating intent system is being used)

    This allows existing projects without intent sections to continue working.
    """
    if tool_name not in ("Edit", "Write", "NotebookEdit"):
        return None

    # Safe paths bypass intent check (allow bootstrapping)
    file_path = tool_input.get("file_path", "")
    safe_paths = [
        "active_context.yaml",
        ".proof/",
        "checklist.md",
        "archive.md",
        ".claude/plans/",  # Plan files are safe
    ]
    if any(safe in file_path for safe in safe_paths):
        return None

    state = load_yaml_state()
    if state is None:
        return None  # No state = let plan_requirement handle it

    intent = state.get("intent", {})
    user_wants = intent.get("user_wants", "")

    # BACKWARD COMPATIBILITY: Only check intent if user_wants is set
    # This means the project has opted into the intent system
    if not user_wants:
        return None  # No intent system in use, skip check

    # Intent system is in use - check if confirmed
    if not intent.get("confirmed", False):
        return ("ask",
                f"Intent not confirmed.\n"
                f"  user_wants: {user_wants[:80]}{'...' if len(user_wants) > 80 else ''}\n"
                "Set intent.confirmed: true in active_context.yaml, "
                "or confirm to proceed without intent verification.")

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


def check_graduated_rules(tool_name, tool_input):
    """
    v7.0: Check graduated rules for violations.
    Returns (violations, rules_fired) where:
    - violations: list of RuleViolation objects
    - rules_fired: list of rule IDs that were checked (for outcome tracking)
    """
    if tool_name not in ("Edit", "Write", "NotebookEdit"):
        return [], []

    try:
        from rules_engine import check_rules, get_blocking_violation, format_violations

        violations = check_rules(tool_name, tool_input)
        rules_fired = [v.rule_id for v in violations]

        return violations, rules_fired
    except (ImportError, Exception):
        return [], []


def log_surface_event_for_outcome(tool_name, tool_input, rules_fired, context_shown):
    """
    v7.0: Log surface event and store correlation ID for outcome tracking.
    """
    global _pending_correlation_id

    if not rules_fired and not context_shown:
        return None

    try:
        from outcome_tracker import generate_correlation_id, log_surface_event

        file_path = tool_input.get("file_path", "")
        correlation_id = generate_correlation_id()

        log_surface_event(
            correlation_id=correlation_id,
            file_path=file_path,
            rules_fired=rules_fired,
            context_shown=context_shown,
            tool_name=tool_name
        )

        _pending_correlation_id = correlation_id
        return correlation_id
    except (ImportError, Exception):
        return None


def get_pending_correlation_id():
    """Get the pending correlation ID for outcome tracking."""
    global _pending_correlation_id
    cid = _pending_correlation_id
    _pending_correlation_id = None
    return cid

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

    # Check 2: Intent verification (Understanding-First v1.0)
    result = check_intent_confirmed(tool_name, tool_input)
    if result:
        respond(*result)

    # Check 3: Plan requirement for edits
    result = check_plan_requirement(tool_name, tool_input)
    if result:
        respond(*result)

    # Load state for lesson surfacing and evals
    state = load_yaml_state()

    # v7.0: Check graduated rules (enforcement, not just guidance)
    violations, rules_fired = check_graduated_rules(tool_name, tool_input)

    # v3.10: Surface relevant lessons (guidance, not a gate)
    relevant_lessons = check_relevant_lessons(tool_name, tool_input, state)
    context_shown = [l.get('lesson', '') for l in relevant_lessons]

    # v7.0: Log surface event for outcome tracking
    log_surface_event_for_outcome(tool_name, tool_input, rules_fired, context_shown)

    # v7.0: Handle blocking rule violations
    if violations:
        try:
            from rules_engine import get_blocking_violation, format_violations
            blocking = get_blocking_violation(violations)
            if blocking:
                decision, message = blocking.to_response()
                respond(decision, message)
        except (ImportError, Exception):
            pass

    # v3.11: Create obligations for surfaced lessons (Mechanical Learning)
    if relevant_lessons:
        try:
            from obligation_utils import create_obligation, log_obligation_event
            from proof_utils import log_to_session

            session_id = state.get('session', {}).get('id', '') if state else ''

            for lesson in relevant_lessons:
                ob = create_obligation(
                    lesson_trigger=lesson.get('trigger', ''),
                    lesson_text=lesson.get('lesson', ''),
                    tool_name=tool_name,
                    tool_input=tool_input,
                    session_id=session_id
                )
                # Log to proof
                log_entry = log_obligation_event("created", ob, session_id)
                log_to_session(log_entry)
        except (ImportError, Exception):
            pass  # Obligation system unavailable, continue without

    # Eval automation: capture pre-tool snapshot for write/edit tools
    if tool_name in ("Edit", "Write", "NotebookEdit"):
        if state:
            evals_config = get_evals_config(state)
            evals_config, _triage = auto_triage(state, evals_config, tool_name)

            if evals_config.get("enabled", True) and evals_config.get("mode") != "manual":
                if evals_config.get("level", 0) >= 1 and evals_config.get("snapshots", {}).get("enabled", True):
                    pending_run = start_eval_run(evals_config, tool_name)
                    eval_state = load_eval_state()
                    eval_state["pending_run"] = pending_run
                    eval_state["triage"] = evals_config.get("triage", {})
                    save_eval_state(eval_state)

    # Build approval message with all relevant info
    messages = []

    # v7.0: Include rule violations (warnings)
    if violations:
        try:
            from rules_engine import format_violations
            messages.append(format_violations(violations))
        except (ImportError, Exception):
            pass

    # Include relevant lessons
    if relevant_lessons:
        lesson_text = "\n".join([f"  - [{l['trigger']}]: {l['lesson']}" for l in relevant_lessons])
        messages.append(f"Relevant lessons:\n{lesson_text}")

    if messages:
        respond("approve", "\n\n".join(messages))
    else:
        respond("approve", "Passed all pre-tool checks")

if __name__ == "__main__":
    main()
