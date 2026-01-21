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
    QualityGateOverride,
    detect_current_gear,
    format_gear_status,
    GEAR_EMOJI,
)
from state_utils import (
    load_yaml_state, Mode, detect_mode, set_mode, suggest_mode_transition,
    set_new_objective, is_objective_text, extract_objective_text,
)
from junction_utils import (
    get_pending_junction,
    set_pending_junction,
    clear_pending_junction,
)
from dispatch_utils import (
    load_dispatch_state,
    save_dispatch_state,
    get_dispatch_status,
    check_stuck,
    check_iteration_limit,
    increment_iteration,
    reset_stuck_counter,
    increment_stuck_counter,
)
from dispatch_config import DispatchState, DISPATCH_DEFAULTS
from eval_utils import cleanup_orphaned_eval_state, cleanup_old_snapshots
from obligation_utils import clear_stale_obligations
from proof_utils import get_current_session_id
from datetime import datetime


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

    # Check for subcommands like /edge-plan, /edge-step
    if after_edge.startswith("-"):
        subcommand = after_edge[1:].split()[0].lower()  # e.g., "-plan" → "plan"
        rest = after_edge[1 + len(subcommand):].strip()
        return {"command": "subcommand", "args": subcommand, "rest": rest}

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
    # Mode commands (v4.0)
    elif first_word in ("plan", "active", "review", "done"):
        return {"command": "mode", "args": first_word}
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
    _, reset_error = reset_gear_state()

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
    ]

    if reset_error:
        lines.append(f"[WARNING] Reset not persisted: {reset_error}")
        lines.append("")

    lines.extend([
        "Gear state reset. Run /edge to restart.",
        "=" * 70,
    ])
    return "\n".join(lines)


def _parse_check_specifier(specifier: str, failed_checks: list) -> list:
    """
    Parse user's check specifier into list of check names (v5.2).

    Supports:
    - Numeric indices (1-based): "1", "2", "1,2"
    - Check names: "steps_have_proof", "no_dangling_in_progress"
    - Mixed: "1,no_dangling_in_progress"

    Args:
        specifier: User input (e.g., "1,2" or "steps_have_proof")
        failed_checks: List of failed check dicts with "name" field

    Returns:
        List of check names to approve
    """
    if not specifier:
        return []

    parts = [p.strip() for p in specifier.split(",")]
    check_names = []

    for part in parts:
        if part.isdigit():
            # Numeric index (1-based)
            idx = int(part) - 1
            if 0 <= idx < len(failed_checks):
                name = failed_checks[idx].get("name", "")
                if name:
                    check_names.append(name)
        else:
            # Check name directly
            check_names.append(part)

    return [n for n in check_names if n]


def handle_approve(args: str = "") -> tuple[str, bool]:
    """
    Handle /edge approve [check_specifier] - clear junction and continue.

    Args:
        args: Optional check specifier for quality gate (v5.2)
              - Empty: Full override (bypass all checks)
              - "1" or "1,2": Approve specific checks by number
              - "check_name": Approve specific check by name
    """
    # Check junction type before clearing
    pending_junction = get_pending_junction()
    is_mode_transition = (
        pending_junction and
        pending_junction.get("type") == "mode_transition"
    )
    is_quality_gate = (
        pending_junction and
        pending_junction.get("type") == "quality_gate"
    )

    try:
        pending, warning = clear_pending_junction("approve")
    except TimeoutError as exc:
        return (f"[ERROR] State lock busy while clearing junction. {exc}", False)
    if warning:
        return (f"[WARNING] {warning}", False)

    if pending:
        # If quality_gate, persist session-scoped override (v5.2)
        if is_quality_gate:
            try:
                state = load_yaml_state()
                gear_state = load_gear_state()
                objective = state.get("objective", "") if state else ""

                # Get failed checks from junction payload
                payload = pending_junction.get("payload", {})
                failed_checks = payload.get("failed_checks", [])

                # Parse check specifier (v5.2)
                check_specifier = args.strip() if args else ""

                if check_specifier:
                    # Check-specific override
                    approved_checks = _parse_check_specifier(check_specifier, failed_checks)
                    if not approved_checks:
                        return (f"[ERROR] Invalid check specifier: '{check_specifier}'. Use numbers (1,2) or check names.", False)
                    mode = "check_specific"
                    message = f"Approved {len(approved_checks)} check(s): {', '.join(approved_checks)}"
                else:
                    # Full override (v5.1 behavior)
                    approved_checks = []
                    mode = "full"
                    message = "All quality gate checks approved"

                # Set session-scoped quality gate override
                gear_state.quality_gate_override = QualityGateOverride(
                    mode=mode,
                    approved_at=datetime.now().isoformat(),
                    session_id=get_current_session_id(),
                    objective_hash=hash(objective),
                    approved_checks=approved_checks,
                    reason=payload.get("reason", "user_approved"),
                )
                save_gear_state(gear_state)

                if mode == "full":
                    return (f"[OVERRIDE SET] {message}. Gate will be bypassed on subsequent runs.", True)
                else:
                    return (f"[OVERRIDE SET] {message}. Only these checks will be bypassed.", True)
            except Exception as e:
                # Override failed, but junction is cleared - continue anyway
                return (f"[APPROVED] Quality gate cleared (override failed: {e}). Continuing...", True)

        # If it was a mode_transition, perform the mode switch
        if is_mode_transition:
            payload = pending_junction.get("payload", {})
            to_mode_str = payload.get("to", "")
            try:
                to_mode = Mode(to_mode_str)
                set_mode(to_mode)
                from_mode = payload.get("from", "unknown")
                to_emoji = MODE_EMOJI.get(to_mode, "?")
                return (f"[MODE SWITCH] {from_mode.upper()} -> {to_emoji} {to_mode.value.upper()}", True)
            except ValueError:
                return ("[APPROVED] Junction cleared (invalid mode). Continuing...", True)
        return ("[APPROVED] Junction cleared. Continuing execution...", True)
    return ("[APPROVE] No pending junction found. Running gear cycle...", True)


def handle_skip() -> tuple[str, bool]:
    """Handle /edge skip - skip current action."""
    pending = get_pending_junction()
    junction_type = pending.get("type", "unknown") if pending else "unknown"
    try:
        cleared, warning = clear_pending_junction("skip")
    except TimeoutError as exc:
        return (f"[ERROR] State lock busy while skipping junction. {exc}", False)
    if warning:
        return (f"[WARNING] {warning}", False)
    if cleared:
        return (f"[SKIPPED] {junction_type} junction skipped. Trying next action...", True)
    return ("[SKIP] Nothing to skip. Running gear cycle...", True)


def handle_dismiss(args: str = "") -> tuple[str, bool]:
    """Handle /edge dismiss [minutes] - dismiss current junction temporarily.

    Args:
        args: Optional TTL in minutes (default: 60)
    """
    pending = get_pending_junction()
    junction_type = pending.get("type", "unknown") if pending else "unknown"

    # Parse TTL from args
    ttl_minutes = None
    if args.strip():
        try:
            ttl_minutes = int(args.strip())
            if ttl_minutes <= 0:
                return ("[ERROR] TTL must be a positive number of minutes.", False)
        except ValueError:
            return (f"[ERROR] Invalid TTL '{args.strip()}'. Use /edge dismiss <minutes>", False)

    try:
        cleared, warning = clear_pending_junction("dismiss", suppress_minutes=ttl_minutes)
    except TimeoutError as exc:
        return (f"[ERROR] State lock busy while dismissing junction. {exc}", False)
    if warning:
        return (f"[WARNING] {warning}", False)
    if cleared:
        ttl_display = ttl_minutes if ttl_minutes else 60
        return (f"[DISMISSED] {junction_type} junction dismissed for {ttl_display} minutes. Continuing...", True)
    return ("[DISMISS] Nothing to dismiss. Running gear cycle...", True)


# Mode emoji mapping
MODE_EMOJI = {
    Mode.PLAN: "\U0001F4DD",      # Memo
    Mode.ACTIVE: "\U0001F3AF",    # Target
    Mode.REVIEW: "\U0001F50D",    # Magnifying glass
    Mode.DONE: "\u2705",          # Check mark
}


def handle_mode(mode_name: str) -> str:
    """
    Handle /edge plan|active|review|done - set explicit mode.

    Args:
        mode_name: The mode to set (plan, active, review, done)

    Returns:
        Status message
    """
    try:
        new_mode = Mode(mode_name.lower())
    except ValueError:
        return f"[ERROR] Unknown mode: {mode_name}. Use plan|active|review|done"

    # Get current mode before changing
    current_mode = detect_mode()

    # Set the new mode (auto-saves to file)
    set_mode(new_mode)

    emoji = MODE_EMOJI.get(new_mode, "?")
    old_emoji = MODE_EMOJI.get(current_mode, "?")

    lines = [
        "=" * 70,
        f"OPERATOR'S EDGE v4.0 - MODE SET",
        "=" * 70,
        "",
        f"Mode: {old_emoji} {current_mode.value.upper()} -> {emoji} {new_mode.value.upper()}",
        "",
    ]

    # Add mode-specific guidance
    if new_mode == Mode.PLAN:
        lines.extend([
            "You are now in PLAN mode.",
            "  - Explore the codebase and understand requirements",
            "  - Create or refine your plan in active_context.yaml",
            "  - Run /edge to get planning assistance",
        ])
    elif new_mode == Mode.ACTIVE:
        lines.extend([
            "You are now in ACTIVE mode.",
            "  - Execute plan steps one at a time",
            "  - Mark steps as completed with proof",
            "  - Run /edge to execute the current step",
        ])
    elif new_mode == Mode.REVIEW:
        lines.extend([
            "You are now in REVIEW mode.",
            "  - Verify all work is complete",
            "  - Run tests and quality checks",
            "  - Run /edge to verify completion",
        ])
    elif new_mode == Mode.DONE:
        lines.extend([
            "You are now in DONE mode.",
            "  - Archive completed work",
            "  - Clear state for next objective",
            "  - Run /edge to finalize",
        ])

    lines.extend(["", "=" * 70])
    return "\n".join(lines)


def _format_junction_pending(pending: dict) -> str:
    """Format pending junction output."""
    reason = (pending.get("payload") or {}).get("reason", "No reason provided")
    lines = [
        "=" * 70,
        "OPERATOR'S EDGE v4.0 - JUNCTION PENDING",
        "=" * 70,
        "",
        f"JUNCTION: {pending.get('type')}",
        "",
        f"Reason: {reason}",
        "",
        "Options:",
        "  /edge approve      - Continue with proposed action (one-time)",
        "  /edge skip         - Skip this, try next approach",
        "  /edge dismiss      - Dismiss for 60 minutes (auto-approve matching)",
        "  /edge dismiss 120  - Dismiss for custom TTL (minutes)",
        "  /edge stop         - Stop autonomous mode",
        "",
        "=" * 70,
    ]
    return "\n".join(lines)


def handle_plan_mode(state: dict) -> str:
    """Handle /edge in PLAN mode - exploration, no gear engine."""
    mode_emoji = MODE_EMOJI.get(Mode.PLAN, "?")
    objective = state.get("objective", "")
    plan = state.get("plan", [])

    lines = [
        "=" * 70,
        f"OPERATOR'S EDGE v4.0 - {mode_emoji} PLAN mode",
        "=" * 70,
        "",
        "[PLAN MODE] Explore the codebase and create your plan",
        "",
    ]

    if objective:
        lines.extend([
            f"Current objective: {objective[:60]}...",
            "",
        ])

    # Check for suggested transition
    transition = suggest_mode_transition(state)

    if plan:
        pending = sum(1 for s in plan if isinstance(s, dict) and s.get("status") == "pending")
        completed = sum(1 for s in plan if isinstance(s, dict) and s.get("status") == "completed")
        lines.extend([
            f"Plan exists: {len(plan)} steps ({completed} completed, {pending} pending)",
            "",
        ])

        if transition:
            _, to_mode, reason = transition
            to_emoji = MODE_EMOJI.get(to_mode, "?")
            lines.extend([
                "-" * 70,
                f"TRANSITION AVAILABLE: {mode_emoji} PLAN -> {to_emoji} {to_mode.value.upper()}",
                f"Reason: {reason}",
                "",
                "Run /edge approve to switch, or /edge skip to stay in PLAN mode",
                "",
            ])
            # Set junction for transition
            try:
                set_pending_junction(
                    "mode_transition",
                    {"from": "plan", "to": to_mode.value, "reason": reason},
                    source="edge"
                )
            except TimeoutError:
                pass  # Non-fatal - junction just won't be set
        else:
            lines.extend([
                "Ready to execute? Run: /edge active",
                "",
            ])
    else:
        lines.extend([
            "No plan yet. Suggested next steps:",
            "  1. Explore the codebase to understand the problem",
            "  2. Identify key files and patterns",
            "  3. Create a plan in active_context.yaml",
            "  4. Run /edge active to start executing",
            "",
        ])

    lines.extend([
        "-" * 70,
        "Commands:",
        "  /edge active  - Switch to ACTIVE mode and start executing",
        "  /edge-plan    - Get help creating a plan",
        "=" * 70,
    ])
    return "\n".join(lines)


def handle_review_mode(state: dict) -> str:
    """Handle /edge in REVIEW mode - verification checks."""
    mode_emoji = MODE_EMOJI.get(Mode.REVIEW, "?")
    objective = state.get("objective", "")
    plan = state.get("plan", [])

    lines = [
        "=" * 70,
        f"OPERATOR'S EDGE v4.0 - {mode_emoji} REVIEW mode",
        "=" * 70,
        "",
        "[REVIEW MODE] Verify all work is complete",
        "",
    ]

    if objective:
        lines.append(f"Objective: {objective[:60]}...")
        lines.append("")

    # Check plan status
    if plan:
        completed = sum(1 for s in plan if isinstance(s, dict) and s.get("status") == "completed")
        pending = sum(1 for s in plan if isinstance(s, dict) and s.get("status") == "pending")
        in_progress = sum(1 for s in plan if isinstance(s, dict) and s.get("status") == "in_progress")

        lines.extend([
            f"Plan: {len(plan)} steps",
            f"  Completed: {completed}",
            f"  In Progress: {in_progress}",
            f"  Pending: {pending}",
            "",
        ])

        if pending > 0 or in_progress > 0:
            lines.extend([
                "WARNING: Not all steps complete!",
                "  Run /edge active to continue working",
                "",
            ])
        else:
            lines.extend([
                "All steps marked complete.",
                "",
            ])

    lines.extend([
        "-" * 70,
        "Verification checklist:",
        "  [ ] All plan steps have proof",
        "  [ ] Tests pass (if applicable)",
        "  [ ] No unresolved mismatches",
        "  [ ] Code compiles/runs correctly",
        "",
        "Commands:",
        "  /edge-verify  - Run automated checks",
        "  /edge-review  - Self-review code changes",
        "  /edge done    - Mark as complete and archive",
        "=" * 70,
    ])
    return "\n".join(lines)


def handle_done_mode(state: dict) -> str:
    """Handle /edge in DONE mode - archiving workflow."""
    mode_emoji = MODE_EMOJI.get(Mode.DONE, "?")
    objective = state.get("objective", "")
    plan = state.get("plan", [])

    lines = [
        "=" * 70,
        f"OPERATOR'S EDGE v4.0 - {mode_emoji} DONE mode",
        "=" * 70,
        "",
        "[DONE MODE] Archive and prepare for next objective",
        "",
    ]

    if objective:
        lines.append(f"Completed: {objective[:60]}...")
        lines.append("")

    if plan:
        completed = sum(1 for s in plan if isinstance(s, dict) and s.get("status") == "completed")
        lines.append(f"Steps completed: {completed}/{len(plan)}")
        lines.append("")

    # Generate scorecard if objective is complete
    if plan and completed == len(plan):
        try:
            from scorecard_utils import (
                compute_objective_scorecard,
                format_scorecard,
                get_recent_scorecards,
                compute_governor_recommendation,
                format_governor_recommendation
            )

            dispatch_state = load_dispatch_state()
            scorecard = compute_objective_scorecard(
                objective=objective,
                dispatch_state=dispatch_state,
                yaml_state=state
            )
            lines.append(format_scorecard(scorecard))
            lines.append("")

            # Show governor recommendation
            recent = get_recent_scorecards(5)
            if len(recent) >= 2:
                recommendation = compute_governor_recommendation(recent)
                lines.append(format_governor_recommendation(recommendation))
                lines.append("")
        except (ImportError, Exception):
            pass  # Scorecard unavailable

    lines.extend([
        "-" * 70,
        "Archive options:",
        "  /edge-prune   - Archive completed work, reduce state entropy",
        "  /edge-score   - Self-assess against 6-check rubric",
        "",
        "To start a new objective:",
        "  1. Update active_context.yaml with new objective",
        "  2. Run /edge plan to enter planning mode",
        "",
        "=" * 70,
    ])
    return "\n".join(lines)


def handle_active_mode(state: dict) -> str:
    """Handle /edge in ACTIVE mode - run gear engine."""
    project_dir = Path(os.environ.get("CLAUDE_PROJECT_DIR", "."))

    # Check dispatch mode state
    dispatch_state = load_dispatch_state()
    dispatch_enabled = dispatch_state.get("enabled", False)
    dispatch_running = dispatch_state.get("state") == DispatchState.RUNNING.value

    # If dispatch is enabled, check safety limits
    if dispatch_enabled and dispatch_running:
        is_stuck, stuck_reason = check_stuck(dispatch_state)
        if is_stuck:
            dispatch_state["state"] = DispatchState.STUCK.value
            save_dispatch_state(dispatch_state)
            return "\n".join([
                "=" * 70,
                "DISPATCH MODE: STUCK",
                "=" * 70,
                "",
                f"Reason: {stuck_reason}",
                "",
                "Options:",
                "  /edge-adapt   - Try a new approach",
                "  /edge-yolo off - Stop dispatch mode",
                "",
                "=" * 70,
            ])

        limit_reached, limit_reason = check_iteration_limit(dispatch_state)
        if limit_reached:
            dispatch_state["state"] = DispatchState.IDLE.value
            dispatch_state["enabled"] = False
            save_dispatch_state(dispatch_state)
            return "\n".join([
                "=" * 70,
                "DISPATCH MODE: SAFETY LIMIT",
                "=" * 70,
                "",
                f"Reason: {limit_reason}",
                "",
                f"Completed {dispatch_state.get('iteration', 0)} iterations.",
                "Autopilot disengaged for safety.",
                "",
                "Run /edge-yolo on to restart.",
                "",
                "=" * 70,
            ])

        # Increment iteration counter
        increment_iteration(dispatch_state)
        save_dispatch_state(dispatch_state)

    # Run the gear engine
    result = run_gear_engine(state, project_dir)

    # Build output
    mode_emoji = MODE_EMOJI.get(Mode.ACTIVE, "?")
    gear_emoji = GEAR_EMOJI.get(result.gear_executed, "?")
    gear_name = result.gear_executed.value.upper()

    # Add dispatch header if enabled
    if dispatch_enabled:
        lines = [
            "=" * 70,
            f"DISPATCH MODE [Iteration {dispatch_state.get('iteration', 0)}] | {gear_emoji} {gear_name} gear",
            "=" * 70,
            "",
        ]
    else:
        lines = [
            "=" * 70,
            f"OPERATOR'S EDGE v4.0 - {mode_emoji} ACTIVE mode | {gear_emoji} {gear_name} gear",
            "=" * 70,
            "",
            "[ACTIVE MODE] Execute plan steps - mark completed with proof",
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
        # Update dispatch state if in dispatch mode
        if dispatch_enabled:
            dispatch_state["state"] = DispatchState.JUNCTION.value
            dispatch_state["junction"] = {
                "type": result.junction_type,
                "reason": result.junction_reason,
            }
            save_dispatch_state(dispatch_state)
            # Reset progress counter on junction (not stuck)
            reset_stuck_counter(dispatch_state)
            save_dispatch_state(dispatch_state)

        lines.extend([
            "",
            "-" * 70,
            f"JUNCTION: {result.junction_type}",
            "-" * 70,
            "",
            f"Reason: {result.junction_reason}",
            "",
            "Options:",
            "  /edge approve      - Continue with proposed action (one-time)",
            "  /edge skip         - Skip this, try next approach",
            "  /edge dismiss      - Dismiss for 60 minutes (auto-approve matching)",
            "  /edge dismiss 120  - Dismiss for custom TTL (minutes)",
            "  /edge stop         - Stop autonomous mode",
        ])

        # Save junction state for approve/skip handling
        try:
            _, warning = set_pending_junction(
                result.junction_type,
                {"reason": result.junction_reason, "gear": gear_name.lower()},
                source="edge"
            )
            if warning:
                lines.extend([
                    "",
                    f"[WARNING] {warning}",
                ])
        except TimeoutError as exc:
            lines.extend([
                "",
                f"[ERROR] State lock busy while saving junction. {exc}",
                "Try again in a moment. If this persists, ensure no other /edge run is active.",
                "=" * 70,
            ])
            return "\n".join(lines)
    else:
        # Success - reset stuck counter if in dispatch mode
        if dispatch_enabled:
            reset_stuck_counter(dispatch_state)
            save_dispatch_state(dispatch_state)

    # Check for mode transition (ACTIVE → REVIEW when all steps complete)
    if not result.junction_hit:
        # Reload state to get latest (gear engine may have updated it)
        fresh_state = load_yaml_state() or {}
        transition = suggest_mode_transition(fresh_state)
        if transition:
            _, to_mode, reason = transition
            to_emoji = MODE_EMOJI.get(to_mode, "?")
            lines.extend([
                "",
                "-" * 70,
                f"TRANSITION AVAILABLE: {mode_emoji} ACTIVE -> {to_emoji} {to_mode.value.upper()}",
                f"Reason: {reason}",
                "",
                "Run /edge approve to switch to REVIEW mode, or /edge skip to continue",
                "",
            ])
            # Set junction for transition
            try:
                set_pending_junction(
                    "mode_transition",
                    {"from": "active", "to": to_mode.value, "reason": reason},
                    source="edge"
                )
            except TimeoutError:
                pass  # Non-fatal

    # Add continuation hint based on dispatch mode
    if result.continue_loop and not result.junction_hit:
        if dispatch_enabled and dispatch_running:
            lines.extend([
                "",
                "-" * 70,
                "[DISPATCH] Loop continues. Run /edge to execute next action.",
                "-" * 70,
            ])
        else:
            lines.extend([
                "",
                "[Loop continues - run /edge again or /edge-yolo for autopilot]",
            ])

    lines.extend(["", "=" * 70])
    return "\n".join(lines)


def handle_run(args: str = "") -> str:
    """Handle /edge (run) - dispatch to mode-specific handler.

    If args contains an objective (e.g., /edge "Deploy auth system"),
    set that as the new objective and enter planning mode.
    """
    # Check if args looks like a new objective
    if args and is_objective_text(args):
        objective_text = extract_objective_text(args)
        return handle_new_objective(objective_text)

    # Check for pending junction first (applies to all modes)
    pending = get_pending_junction()
    if pending:
        return _format_junction_pending(pending)

    # Load state and detect mode
    state = load_yaml_state() or {}
    current_mode = detect_mode(state)

    # Dispatch to mode-specific handler
    if current_mode == Mode.PLAN:
        return handle_plan_mode(state)
    elif current_mode == Mode.REVIEW:
        return handle_review_mode(state)
    elif current_mode == Mode.DONE:
        return handle_done_mode(state)
    else:
        # ACTIVE mode (default) - runs gear engine
        return handle_active_mode(state)


def handle_subcommand(subcommand: str, rest: str = "") -> str:
    """
    Handle /edge-<subcommand> by invoking the corresponding skill.

    Instead of exiting and expecting Claude Code to find the skill,
    we read the skill file and output its content directly.
    This ensures /edge-plan, /edge-step, etc. work correctly.

    Args:
        subcommand: The subcommand name (e.g., "plan", "step", "verify")
        rest: Any additional arguments after the subcommand

    Returns:
        The skill content or error message
    """
    project_dir = Path(os.environ.get("CLAUDE_PROJECT_DIR", "."))

    # Look for the skill file in .claude/commands/
    skill_file = project_dir / ".claude" / "commands" / f"edge-{subcommand}.md"

    if not skill_file.exists():
        # Try without "edge-" prefix
        skill_file = project_dir / ".claude" / "commands" / f"{subcommand}.md"

    if not skill_file.exists():
        # Unknown subcommand - suggest alternatives
        return "\n".join([
            "=" * 70,
            f"OPERATOR'S EDGE - Unknown subcommand: /edge-{subcommand}",
            "=" * 70,
            "",
            "Available subcommands:",
            "  /edge-plan     - Get planning assistance",
            "  /edge-step     - Execute current step",
            "  /edge-verify   - Run quality checks",
            "  /edge-review   - Self-review code changes",
            "  /edge-prune    - Archive completed work",
            "  /edge-fork     - Search and fork past sessions",
            "  /edge-yolo     - Enable/disable autopilot",
            "",
            "Or use the unified syntax:",
            "  /edge plan     - Set mode to PLAN",
            "  /edge active   - Set mode to ACTIVE",
            "  /edge review   - Set mode to REVIEW",
            "  /edge done     - Set mode to DONE",
            "",
            "=" * 70,
        ])

    # Read and output the skill content
    try:
        skill_content = skill_file.read_text()

        # Add header and any arguments
        lines = [
            "=" * 70,
            f"OPERATOR'S EDGE - /edge-{subcommand}",
            "=" * 70,
            "",
        ]

        if rest:
            lines.extend([
                f"Arguments: {rest}",
                "",
            ])

        lines.extend([
            "-" * 70,
            "SKILL INSTRUCTIONS (from edge-{}.md):".format(subcommand),
            "-" * 70,
            "",
            skill_content,
            "",
            "=" * 70,
        ])

        return "\n".join(lines)
    except Exception as e:
        return f"[ERROR] Failed to read skill file: {e}"


def handle_new_objective(objective_text: str) -> str:
    """Handle /edge "objective" - set new objective and enter planning.

    This is the "just works" flow:
    1. Set the objective in active_context.yaml
    2. Clear the existing plan
    3. Set mode to PLAN
    4. Show planning guidance

    The user then explores, creates a plan, and runs /edge again
    to start execution.
    """
    lines = [
        "=" * 70,
        "OPERATOR'S EDGE v6.0 - NEW OBJECTIVE",
        "=" * 70,
        "",
    ]

    # Check if there's an existing objective
    state = load_yaml_state() or {}
    existing_objective = state.get("objective", "")
    existing_plan = state.get("plan", [])

    if existing_objective and existing_plan:
        incomplete = sum(1 for s in existing_plan
                        if isinstance(s, dict) and s.get("status") in ("pending", "in_progress"))
        if incomplete > 0:
            lines.extend([
                "⚠️  EXISTING WORK IN PROGRESS",
                f"   Current objective: {existing_objective[:50]}...",
                f"   Incomplete steps: {incomplete}",
                "",
                "   Setting new objective will CLEAR the existing plan.",
                "",
            ])

    # Set the new objective
    success, message = set_new_objective(objective_text, clear_plan=True)

    if not success:
        lines.extend([
            f"❌ Failed to set objective: {message}",
            "",
            "Please check active_context.yaml and try again.",
        ])
        return "\n".join(lines)

    lines.extend([
        f"✓ Objective: {objective_text}",
        "",
    ])

    # v7.1: Get pattern suggestion from learned guidance
    suggestion_text = None
    try:
        from pattern_recognition import suggest_approach_for_objective
        suggestion_text, pattern_match = suggest_approach_for_objective(objective_text)

        if suggestion_text and pattern_match:
            lines.extend([
                "-" * 70,
                "🎯 LEARNED GUIDANCE - Suggested Approach",
                "-" * 70,
                "",
                suggestion_text,
                "",
            ])

            # Track that we showed a suggestion (for Phase 4 learning)
            try:
                from archive_utils import log_to_archive
                log_to_archive("suggestion_shown", {
                    "objective": objective_text[:200],
                    "pattern_id": pattern_match.pattern_id,
                    "pattern_source": pattern_match.source,
                    "confidence": pattern_match.confidence,
                    "approach_verbs": [s.get("verb", "") for s in pattern_match.approach]
                })
            except Exception:
                pass  # Logging failure shouldn't block the flow
    except ImportError:
        pass  # pattern_recognition not available
    except Exception:
        pass  # Suggestion failure shouldn't block objective setting

    lines.extend([
        "-" * 70,
        "📋 PLAN MODE - Ready to plan",
        "-" * 70,
        "",
    ])

    if suggestion_text:
        lines.extend([
            "The objective is set and a suggested approach is shown above.",
            "You can:",
            "",
            "  • FOLLOW the suggestion - Create plan steps matching the approach",
            "  • MODIFY it - Use parts that make sense, skip others",
            "  • IGNORE it - Create your own plan from scratch",
            "",
        ])
    else:
        lines.extend([
            "The objective is set. Now:",
            "",
            "  1. EXPLORE - Understand the codebase and problem",
            "     • Read relevant files",
            "     • Search for patterns",
            "     • Identify key components",
            "",
            "  2. PLAN - Create steps in active_context.yaml",
            "     • Add plan steps with descriptions",
            "     • Include a verification step",
            "     • Set success criteria",
            "",
        ])

    lines.extend([
        "  CONFIRM - Run /edge to review and approve",
        "",
        "-" * 70,
        "Commands:",
        "  /edge           - Check status and continue",
        "  /edge approve   - Approve plan and start execution",
        "  /edge-yolo on   - Enable autopilot (executes until done)",
        "-" * 70,
        "",
        "💡 TIP: For simple tasks, just describe what you want to do and",
        "   I'll create a plan. For complex tasks, explore first.",
        "",
        "=" * 70,
    ])

    return "\n".join(lines)


def main():
    """Main entry point - processes /edge command from user input."""
    # Session-start cleanup (idempotent - safe to run every invocation)
    # Clears orphaned state from previous crashed sessions
    try:
        cleanup_orphaned_eval_state(max_age_minutes=60)
        cleanup_old_snapshots(retention_days=7, dry_run=False)
        clear_stale_obligations(max_age_hours=24)
    except Exception:
        pass  # Cleanup failure shouldn't block /edge execution

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

    # Handle subcommands by invoking skill content directly
    if command == "subcommand":
        rest = parsed.get("rest", "")
        print(handle_subcommand(args, rest))
        return

    # Route to appropriate handler
    if command == "status":
        print(handle_status())
    elif command in ("off", "stop"):
        print(handle_stop())
    elif command == "approve":
        message, should_run = handle_approve(args)
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
        message, should_run = handle_dismiss(args)
        print(message)
        if should_run:
            print(handle_run())
    elif command == "mode":
        # /edge plan|active|review|done
        print(handle_mode(args))
    else:
        # Default: run gear cycle
        print(handle_run(args))


if __name__ == "__main__":
    main()
