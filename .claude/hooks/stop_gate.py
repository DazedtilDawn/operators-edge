#!/usr/bin/env python3
"""
Operator's Edge v2 - Stop Gate
Blocks session end until requirements are met.

Requirements:
1. active_context.yaml must have been MODIFIED (hash changed)
2. Proof must exist (session_log.jsonl has entries)

Warnings (v2):
3. Unresolved mismatches should be addressed
4. High entropy should be pruned
5. In-progress steps should be resolved

This is the key enforcement mechanism - you cannot claim "done"
without actually changing state and having proof of work.
"""
import json
import os
import sys
from pathlib import Path

# Add hooks directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from edge_utils import (
    get_project_dir,
    get_state_dir,
    get_proof_dir,
    get_start_hash,
    file_hash,
    load_yaml_state,
    get_unresolved_mismatches,
    check_state_entropy,
    get_evals_config,
    auto_triage,
    has_eval_run_since,
)

def respond(decision, reason):
    """Output hook response."""
    print(json.dumps({"decision": decision, "reason": reason}))

def check_state_modified():
    """Verify active_context.yaml was modified during this session."""
    start_hash = get_start_hash()
    if not start_hash:
        # No start hash captured - can't verify, allow with warning
        return (True, "No session start hash (session_start hook may not have run)")

    yaml_file = get_project_dir() / "active_context.yaml"
    if not yaml_file.exists():
        return (False, "active_context.yaml does not exist")

    current_hash = file_hash(yaml_file)
    if current_hash == start_hash:
        return (False,
                "active_context.yaml was NOT modified during this session. "
                "Update it with your progress before stopping.")

    return (True, "State file was modified")

def check_proof_exists():
    """Verify proof was captured during this session."""
    proof_dir = get_proof_dir()
    session_log = proof_dir / "session_log.jsonl"

    if not session_log.exists():
        return (False, "No proof log exists. Some tool usage should have been captured.")

    # Check the log has content
    content = session_log.read_text().strip()
    if not content:
        return (False, "Proof log is empty. Did any work happen?")

    # Count entries
    entries = [l for l in content.split('\n') if l.strip()]
    if len(entries) < 1:
        return (False, "Proof log has no entries.")

    return (True, f"Proof log has {len(entries)} entries")

def check_no_in_progress_steps():
    """Warn if steps are still marked in_progress."""
    state = load_yaml_state()
    if not state:
        return (True, "Could not load state to check")

    plan = state.get('plan', [])
    in_progress = []
    for i, step in enumerate(plan):
        if isinstance(step, dict) and step.get('status') == 'in_progress':
            in_progress.append(i + 1)

    if in_progress:
        return (True,  # Warning, not blocking
                f"Steps still in_progress: {in_progress}. Consider marking complete or blocked.")

    return (True, "No steps left in_progress")

def check_unresolved_mismatches():
    """Warn if there are unresolved mismatches."""
    state = load_yaml_state()
    if not state:
        return (True, "Could not load state")

    unresolved = get_unresolved_mismatches(state)
    if unresolved:
        return (True,  # Warning only
                f"{len(unresolved)} unresolved mismatch(es). Run /edge-adapt before stopping.")

    return (True, "No unresolved mismatches")

def check_entropy():
    """Warn if state entropy is high."""
    state = load_yaml_state()
    if not state:
        return (True, "Could not load state")

    needs_pruning, reasons = check_state_entropy(state)
    if needs_pruning:
        return (True,  # Warning only
                f"High entropy: {reasons[0] if reasons else 'needs pruning'}. Run /edge-prune.")

    return (True, "State entropy OK")


def check_eval_activity():
    """Warn if evals are enabled but no eval_run recorded this session."""
    state = load_yaml_state()
    if not state:
        return (True, "Could not load state")

    evals_config = get_evals_config(state)
    if not evals_config.get("enabled", True):
        return (True, "Evals disabled")

    if evals_config.get("mode") != "manual":
        evals_config, _triage = auto_triage(state, evals_config, None)

    level = evals_config.get("level", 0)
    if level < 1:
        return (True, "Evals not active for this session")

    started_at = None
    session = state.get("session", {})
    if isinstance(session, dict):
        started_at = session.get("started_at")

    if has_eval_run_since(started_at):
        return (True, "Eval activity recorded")

    return (True, "No eval activity recorded this session")

def main():
    all_passed = True
    messages = []

    # Check 1: State was modified (BLOCKING)
    passed, msg = check_state_modified()
    if not passed:
        all_passed = False
        messages.append(f"BLOCKED: {msg}")
    else:
        messages.append(f"OK: {msg}")

    # Check 2: Proof exists (BLOCKING)
    passed, msg = check_proof_exists()
    if not passed:
        all_passed = False
        messages.append(f"BLOCKED: {msg}")
    else:
        messages.append(f"OK: {msg}")

    # Check 3: In-progress steps (WARNING)
    passed, msg = check_no_in_progress_steps()
    if "in_progress" in msg.lower():
        messages.append(f"WARNING: {msg}")
    else:
        messages.append(f"OK: {msg}")

    # Check 4: Unresolved mismatches (WARNING - v2)
    passed, msg = check_unresolved_mismatches()
    if "unresolved" in msg.lower():
        messages.append(f"WARNING: {msg}")

    # Check 5: Entropy (WARNING - v2)
    passed, msg = check_entropy()
    if "entropy" in msg.lower() or "pruning" in msg.lower():
        messages.append(f"WARNING: {msg}")

    # Check 6: Eval activity (WARNING)
    passed, msg = check_eval_activity()
    if "no eval activity" in msg.lower():
        messages.append(f"WARNING: {msg}")

    # Final decision
    if all_passed:
        respond("approve", " | ".join(messages))
    else:
        respond("block", " | ".join(messages))

if __name__ == "__main__":
    main()
