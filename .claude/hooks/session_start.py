#!/usr/bin/env python3
"""
Operator's Edge v2.6 - Session Start Hook
Initializes session state and captures baseline for verification.

Actions:
1. Captures hash of active_context.yaml for later comparison
2. Clears old failure logs
3. Outputs current state for context injection
4. Surfaces relevant memory (v2)
5. Warns about entropy issues (v2)
6. Shows unresolved mismatches (v2)
7. Shows YOLO mode status (v2.6)
"""
import json
import os
import sys
from datetime import datetime
from pathlib import Path

# Add hooks directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from edge_utils import (
    get_project_dir,
    get_state_dir,
    get_proof_dir,
    save_state_hash,
    load_yaml_state,
    file_hash,
    get_schema_version,
    get_memory_items,
    get_unresolved_mismatches,
    check_state_entropy,
    detect_session_context,
    get_orchestrator_suggestion,
    load_archive,
    generate_reflection_summary,
    get_default_yolo_state
)
from proof_utils import initialize_proof_session, archive_old_sessions
from archive_utils import cleanup_archive

def generate_session_id():
    """Generate a unique session ID."""
    return datetime.now().strftime("%Y%m%d-%H%M%S")

def clear_old_state():
    """Clear failure logs from previous sessions."""
    state_dir = get_state_dir()
    failure_log = state_dir / "failure_log.jsonl"
    if failure_log.exists():
        failure_log.unlink()


def load_yolo_state():
    """Load YOLO mode state from file."""
    state_dir = get_state_dir()
    yolo_file = state_dir / "yolo_state.json"
    if yolo_file.exists():
        try:
            with open(yolo_file, 'r') as f:
                return json.load(f)
        except (json.JSONDecodeError, IOError):
            pass
    return get_default_yolo_state()

def _output_plan(state):
    """Output the plan section."""
    plan = state.get('plan', [])
    if plan:
        print(f"\nPlan ({len(plan)} steps):")
        for i, step in enumerate(plan):
            if isinstance(step, dict):
                status = step.get('status', 'pending')
                desc = step.get('description', str(step))
                marker = ">" if i + 1 == state.get('current_step') else " "
                print(f"  {marker} {i+1}. [{status}] {desc}")
            else:
                print(f"    {i+1}. {step}")
    else:
        print("\nNo plan defined. Run /edge-plan to create one.")


def _output_constraints(constraints):
    """Output the constraints section."""
    if constraints:
        print(f"\nConstraints:")
        for c in constraints:
            print(f"  - {c}")


def _output_memory(memory):
    """Output the memory/lessons section."""
    if memory:
        print(f"\nLessons from previous work:")
        for m in memory:
            if isinstance(m, dict):
                trigger = m.get('trigger', '*')
                lesson = m.get('lesson', str(m))
                reinforced = m.get('reinforced', 0)
                evergreen = m.get('evergreen', False)
                strength = "+" * min(reinforced, 3) if reinforced > 0 else ""
                prefix = "*" if evergreen else strength  # * = evergreen (never decays)
                print(f"  - {prefix} When [{trigger}]: {lesson}")
            else:
                print(f"  - {m}")


def _output_warnings(state):
    """Output warnings for unresolved mismatches and high entropy."""
    unresolved = get_unresolved_mismatches(state)
    if unresolved:
        print(f"\n⚠️  UNRESOLVED MISMATCHES ({len(unresolved)}):")
        for m in unresolved[:3]:
            print(f"  - {m.get('expectation', '?')} ≠ {m.get('observation', '?')}")
        print("  Run /edge-adapt to address these.")

    needs_pruning, prune_reasons = check_state_entropy(state)
    if needs_pruning:
        print(f"\n⚠️  STATE ENTROPY HIGH:")
        for reason in prune_reasons[:3]:
            print(f"  - {reason}")
        print("  Run /edge-prune to archive completed work.")


def _output_reflection():
    """Output reflection summary from past scores."""
    try:
        archive = load_archive()
        reflection = generate_reflection_summary(archive)
        if reflection:
            print(f"\n📊 REFLECTION (from past sessions):")
            for line in reflection.split('\n'):
                print(f"  {line}")
    except Exception:
        pass  # Silently skip if reflection fails


def _sync_clickup(state):
    """Sync objective with ClickUp if integration is enabled."""
    try:
        from clickup_utils import is_enabled, get_current_task_url, on_objective_set
        if not is_enabled():
            return None

        objective = state.get("objective")
        if not objective:
            return None

        # Check if we already have a linked task
        existing_url = get_current_task_url()
        if existing_url:
            return existing_url

        # Create new task
        plan = state.get("plan", [])
        task_url = on_objective_set(objective, plan)
        if task_url:
            print(f"\n📋 ClickUp: {task_url}")
        return task_url

    except ImportError:
        return None  # ClickUp integration not available


def _output_yolo_status(state, yolo_state):
    """Output YOLO mode status."""
    if yolo_state.get("enabled"):
        stats = yolo_state.get("stats", {})
        staged = len(yolo_state.get("staged_actions", []))
        auto = stats.get("auto_executed", 0)
        blocked = stats.get("blocked", 0)
        print(f"\n🚀 YOLO MODE: ENABLED")
        print(f"  Auto-executed: {auto} | Staged: {staged} | Blocked: {blocked}")
        if staged > 0:
            print(f"  ⚠️  {staged} actions staged - run /edge-yolo to review")
        print(f"  Tip: /edge-yolo off to disable")
    elif state.get("objective") and state.get("plan"):
        print(f"\n💡 Tip: Run /edge-yolo on for autonomous mode")


def _output_suggestion(state):
    """Output orchestrator suggestion."""
    context_type, details = detect_session_context(state)
    suggestion = get_orchestrator_suggestion(context_type, details)
    if suggestion.get('command'):
        print(f"\nSuggested: {suggestion['message']}")


def output_context():
    """Output current state for Claude to see."""
    state = load_yaml_state()

    print("=" * 60)
    print("OPERATOR'S EDGE - Session Initialized")
    print("=" * 60)

    if state:
        print(f"\nObjective: {state.get('objective', 'Not set')}")
        print(f"Current Step: {state.get('current_step', 0)}")

        _output_plan(state)
        _output_constraints(state.get('constraints', []))
        _output_memory(get_memory_items(state))
        _output_warnings(state)
        _output_reflection()
        _sync_clickup(state)
        _output_yolo_status(state, load_yolo_state())
        _output_suggestion(state)
    else:
        print("\nWARNING: active_context.yaml missing or invalid!")
        print("Create it or run /edge-plan to initialize.")

    print("\n" + "=" * 60)
    print("Enforcement Active:")
    print("  - Edits require a plan (or confirmation)")
    print("  - Dangerous commands are blocked")
    print("  - Failed commands cannot be blindly retried")
    print("  - Session end requires state modification + proof")
    print("=" * 60)

def main():
    # Initialize state directory
    state_dir = get_state_dir()
    state_dir.mkdir(parents=True, exist_ok=True)

    # Initialize proof directory
    proof_dir = get_proof_dir()
    proof_dir.mkdir(parents=True, exist_ok=True)

    # Generate and save session ID
    session_id = generate_session_id()
    (state_dir / "session_id").write_text(session_id)

    # Initialize proof session (session-scoped logs with symlink)
    initialize_proof_session(session_id)

    # Archive old session logs (retention policy: 7 days)
    try:
        archived = archive_old_sessions()
        if archived > 0:
            print(f"[Proof] Archived {archived} old session log(s)")
    except Exception:
        pass  # Best effort cleanup

    # v3.10: Archive retention cleanup (type-based retention)
    try:
        removed, kept = cleanup_archive()
        if removed > 0:
            print(f"[Archive] Cleaned {removed} expired entries ({kept} remaining)")
    except Exception:
        pass  # Best effort cleanup

    # Capture starting hash of state file
    start_hash = save_state_hash()

    # Clear old failure logs
    clear_old_state()

    # Output context for Claude
    output_context()

if __name__ == "__main__":
    main()
