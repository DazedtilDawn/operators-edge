#!/usr/bin/env python3
"""
Operator's Edge v3.9 - Prune Skill Hook
Mechanically executes prune logic when /edge-prune is invoked.

This hook computes what should be pruned and outputs the plan,
providing mechanical enforcement instead of behavioral compliance.

Triggered by: UserPromptSubmit (matcher: "/edge-prune")
"""
import json
import os
import sys
import subprocess
from pathlib import Path
from datetime import datetime

# Add hooks directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from archive_utils import (
    compute_prune_plan,
    estimate_entropy_reduction,
    check_state_entropy,
    archive_completed_step,
    archive_resolved_mismatch,
    archive_decayed_lesson,
    validate_mismatch_for_archive,
    log_to_archive,
)
from state_utils import load_yaml_state


def get_session_id(state: dict = None) -> str:
    """Get session ID from state or file."""
    if state:
        return state.get('session', {}).get('id', 'unknown')
    # Fallback: try to read from state file
    from state_utils import get_state_dir
    session_file = get_state_dir() / "session_id"
    if session_file.exists():
        return session_file.read_text().strip()
    return "unknown"


def format_prune_report(state: dict, prune_plan: dict) -> str:
    """
    Format the prune analysis for display.

    Returns a formatted string showing what will be pruned.
    """
    estimate = estimate_entropy_reduction(prune_plan)

    lines = [
        "=" * 70,
        "OPERATOR'S EDGE v3.9 - PRUNE ANALYSIS",
        "=" * 70,
        "",
    ]

    # Current state summary
    objective = state.get("objective") or "(none)"
    plan = state.get("plan", [])
    completed = sum(1 for s in plan if isinstance(s, dict) and s.get("status") == "completed")

    lines.extend([
        f"Current State:",
        f"  Objective: {objective[:50]}{'...' if len(str(objective)) > 50 else ''}",
        f"  Plan: {len(plan)} steps ({completed} completed)",
        "",
    ])

    # Entropy check
    needs_pruning, reasons = check_state_entropy(state)
    if needs_pruning:
        lines.append("Entropy Status: HIGH")
        for reason in reasons[:3]:
            lines.append(f"  - {reason}")
    else:
        lines.append("Entropy Status: OK")
    lines.append("")

    # Prune breakdown
    lines.extend([
        "-" * 70,
        "PRUNE PLAN",
        "-" * 70,
        "",
    ])

    # Steps to prune
    prunable_steps = prune_plan.get("steps", [])
    if prunable_steps:
        lines.append(f"Steps to archive: {len(prunable_steps)}")
        for item in prunable_steps[:5]:
            # Handle tuple (index, step) format from identify_prunable_steps
            if isinstance(item, tuple):
                idx, step = item
            else:
                step = item
            desc = step.get("description", "Unknown step")[:40] if isinstance(step, dict) else str(step)[:40]
            lines.append(f"  - {desc}...")
        if len(prunable_steps) > 5:
            lines.append(f"  ... and {len(prunable_steps) - 5} more")
    else:
        lines.append("Steps to archive: 0")
    lines.append("")

    # Mismatches to prune
    prunable_mismatches = prune_plan.get("mismatches", [])
    if prunable_mismatches:
        lines.append(f"Mismatches to archive: {len(prunable_mismatches)}")
        for mm in prunable_mismatches[:3]:
            mm_id = mm.get("id", "unknown")[:20]
            lines.append(f"  - {mm_id}")
        if len(prunable_mismatches) > 3:
            lines.append(f"  ... and {len(prunable_mismatches) - 3} more")
    else:
        lines.append("Mismatches to archive: 0")
    lines.append("")

    # Memory to decay
    decayed_memory = prune_plan.get("memory", [])
    if decayed_memory:
        lines.append(f"Lessons to decay: {len(decayed_memory)}")
        for item in decayed_memory[:3]:
            # Handle both tuple (mem, reason) and dict formats
            if isinstance(item, tuple):
                mem, reason = item
            else:
                mem, reason = item, ""
            trigger = mem.get("trigger", "unknown")[:30] if isinstance(mem, dict) else "unknown"
            lines.append(f"  - [{trigger}]")
        if len(decayed_memory) > 3:
            lines.append(f"  ... and {len(decayed_memory) - 3} more")
    else:
        lines.append("Lessons to decay: 0")
    lines.append("")

    # Summary
    lines.extend([
        "-" * 70,
        "ESTIMATE",
        "-" * 70,
        f"Total items to prune: {estimate['items_to_prune']}",
        f"Estimated lines saved: ~{estimate['estimated_lines_saved']}",
        "",
    ])

    # Actions
    if estimate['items_to_prune'] > 0:
        lines.extend([
            "Actions:",
            "  - Archive completed steps (keep only most recent)",
            "  - Archive resolved mismatches (with lesson extraction)",
            "  - Decay stale memory items",
            "",
            "Claude will now execute the prune based on this plan.",
        ])
    else:
        lines.extend([
            "No pruning needed - state is clean.",
        ])

    lines.extend(["", "=" * 70])

    return "\n".join(lines)


def execute_prune(state: dict, prune_plan: dict) -> dict:
    """
    Execute the prune plan - archive items and return summary.

    Returns dict with counts of what was pruned.
    """
    session_id = get_session_id(state)
    objective = state.get("objective", "")

    results = {
        "steps_archived": 0,
        "mismatches_archived": 0,
        "lessons_decayed": 0,
        "lessons_extracted": 0,
        "errors": [],
    }

    # Archive completed steps
    for item in prune_plan.get("steps", []):
        try:
            # Handle tuple (index, step) format from identify_prunable_steps
            if isinstance(item, tuple):
                step_num, step = item
            else:
                step = item.get("step", item) if isinstance(item, dict) else item
                step_num = item.get("index", 0) if isinstance(item, dict) else 0
            archive_completed_step(step, step_num, objective, session_id)
            results["steps_archived"] += 1
        except Exception as e:
            results["errors"].append(f"Step archive error: {e}")

    # Archive resolved mismatches (with lesson extraction)
    for mismatch in prune_plan.get("mismatches", []):
        try:
            is_valid, error = validate_mismatch_for_archive(mismatch)
            if is_valid:
                archive_resolved_mismatch(mismatch, state=state)
                results["mismatches_archived"] += 1
                if mismatch.get("trigger"):
                    results["lessons_extracted"] += 1
            else:
                results["errors"].append(f"Mismatch validation: {error}")
        except Exception as e:
            results["errors"].append(f"Mismatch archive error: {e}")

    # Decay stale memory
    for item in prune_plan.get("memory", []):
        try:
            # Handle both tuple (mem, reason) and dict formats
            if isinstance(item, tuple):
                memory_item, reason = item
            else:
                memory_item = item
                reason = item.get("decay_reason", "stale") if isinstance(item, dict) else "stale"
            archive_decayed_lesson(memory_item, reason)
            results["lessons_decayed"] += 1
        except Exception as e:
            results["errors"].append(f"Memory decay error: {e}")

    return results


def format_prune_results(results: dict) -> str:
    """Format the prune execution results."""
    lines = [
        "",
        "-" * 70,
        "PRUNE COMPLETE",
        "-" * 70,
        f"Steps archived: {results['steps_archived']}",
        f"Mismatches archived: {results['mismatches_archived']}",
        f"Lessons extracted: {results['lessons_extracted']}",
        f"Lessons decayed: {results['lessons_decayed']}",
    ]

    if results["errors"]:
        lines.append("")
        lines.append(f"Errors ({len(results['errors'])}):")
        for err in results["errors"][:5]:
            lines.append(f"  - {err}")

    lines.extend([
        "",
        "NOTE: Claude should now update active_context.yaml to remove",
        "the pruned items. The archive is at .proof/archive.jsonl",
        "-" * 70,
    ])

    return "\n".join(lines)


def handle_prune() -> str:
    """
    Handle /edge-prune - compute and optionally execute prune plan.
    """
    state = load_yaml_state() or {}

    # Compute what should be pruned
    prune_plan = compute_prune_plan(state)

    # Format the report
    report = format_prune_report(state, prune_plan)

    # Check if there's anything to prune
    estimate = estimate_entropy_reduction(prune_plan)

    if estimate["items_to_prune"] > 0:
        # Execute the prune (archive items)
        results = execute_prune(state, prune_plan)
        report += format_prune_results(results)

        # Run Edge Loop after successful prune (non-blocking)
        report += run_edge_loop()

    return report


def run_edge_loop() -> str:
    """
    Run edge_loop.sh after prune to close the feedback loop.
    Non-blocking: failures are logged but don't stop the prune.
    """
    lines = ["", "-" * 70, "EDGE LOOP", "-" * 70]

    try:
        # Find the edge_loop.sh script
        script_path = Path(__file__).parent.parent.parent / "tools" / "edge_loop.sh"
        if not script_path.exists():
            lines.append("Edge Loop script not found - skipping")
            return "\n".join(lines)

        # Run the script (with subprocess timeout)
        result = subprocess.run(
            ["bash", str(script_path)],
            capture_output=True,
            text=True,
            timeout=60,
            cwd=str(script_path.parent.parent),
        )

        if result.returncode == 0:
            lines.append("Edge Loop completed successfully")
            # Extract key info from output
            for line in result.stdout.split("\n"):
                if "CTI" in line or "Saved to" in line:
                    lines.append(f"  {line.strip()}")
        else:
            lines.append(f"Edge Loop exited with code {result.returncode}")
            if result.stderr:
                lines.append(f"  Error: {result.stderr[:100]}")

    except subprocess.TimeoutExpired:
        lines.append("Edge Loop timed out (60s) - skipped")
    except Exception as e:
        lines.append(f"Edge Loop error: {e}")
        # Log to file for debugging
        log_path = Path(__file__).parent.parent.parent / ".proof" / "edge_loop.log"
        log_path.parent.mkdir(parents=True, exist_ok=True)
        with open(log_path, "a") as f:
            f.write(f"{datetime.now().isoformat()} - Error: {e}\n")

    lines.append("-" * 70)
    return "\n".join(lines)


def main():
    """Main entry point - processes /edge-prune command."""
    # Get user input from stdin (Claude Code passes it via hook)
    user_input = ""
    if not sys.stdin.isatty():
        user_input = sys.stdin.read()

    # Check for subcommands (currently none, but extensible)
    # /edge-prune             -> run prune
    # /edge-prune --dry-run   -> show plan only (future)

    print(handle_prune())


if __name__ == "__main__":
    main()
