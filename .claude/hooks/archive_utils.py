#!/usr/bin/env python3
"""
Operator's Edge - Archive Utilities
Archive system, pruning, and entropy management for constant-memory operation.
"""
import json
from datetime import datetime

from state_utils import (
    get_proof_dir, get_archive_file, get_memory_items,
    count_completed_steps, get_step_by_status
)
from edge_config import ENTROPY_THRESHOLDS, MEMORY_SETTINGS, ARCHIVE_SETTINGS


# =============================================================================
# ARCHIVE SYSTEM - Constant-memory through structured archiving
# =============================================================================

def log_to_archive(entry_type, data):
    """Append an entry to the archive."""
    archive_file = get_archive_file()
    archive_file.parent.mkdir(parents=True, exist_ok=True)

    entry = {
        "type": entry_type,
        "timestamp": datetime.now().isoformat(),
        **data
    }
    with open(archive_file, "a") as f:
        f.write(json.dumps(entry) + "\n")


def archive_completed_step(step, step_number, objective, session_id):
    """Archive a completed step."""
    log_to_archive("completed_step", {
        "objective": objective,
        "step_number": step_number,
        "description": step.get('description', ''),
        "proof": step.get('proof'),
        "expected": step.get('expected'),
        "actual": step.get('actual'),
        "session": session_id
    })


def validate_mismatch_for_archive(mismatch):
    """
    Validate that a resolved mismatch is ready for archiving.
    v3.4: Resolved mismatches MUST have a trigger for lesson extraction.

    Returns (is_valid, error_message)
    """
    if not mismatch.get('resolved'):
        return False, "Mismatch must be resolved before archiving"

    if not mismatch.get('trigger'):
        return False, (
            "Resolved mismatch requires 'trigger' field for lesson extraction. "
            "Add trigger words that would surface this lesson for future-me."
        )

    if not mismatch.get('resolution'):
        return False, (
            "Resolved mismatch requires 'resolution' field. "
            "What fixed this issue? (one sentence)"
        )

    return True, None


def derive_lesson_from_mismatch(mismatch):
    """
    Derive a lesson entry from a resolved mismatch.
    v3.4: MISMATCH + TRIGGER = LESSON

    Returns a lesson dict ready for add_memory_item().
    """
    trigger = mismatch.get('trigger', '')
    resolution = mismatch.get('resolution', '')
    expectation = mismatch.get('expectation', '')
    observation = mismatch.get('observation', '')

    # Derive lesson text - prefer resolution, fall back to delta insight
    if resolution:
        lesson = resolution
    else:
        lesson = f"Expected: {expectation}. Reality: {observation}"

    return {
        "trigger": trigger,
        "lesson": lesson,
        "source": f"mismatch-{mismatch.get('id', 'unknown')}",
        "mismatch_id": mismatch.get('id')
    }


def archive_resolved_mismatch(mismatch, lesson_extracted=None, state=None):
    """
    Archive a resolved mismatch and extract lesson to memory.

    v3.4: Automatically creates a lesson from the mismatch.
    If state is provided, adds the lesson to memory.

    Returns (success, lesson_or_error)
    """
    # Validate mismatch is ready
    is_valid, error = validate_mismatch_for_archive(mismatch)
    if not is_valid:
        return False, error

    # Derive lesson if not already provided
    if not lesson_extracted:
        lesson_extracted = derive_lesson_from_mismatch(mismatch)

    # Add lesson to memory if state provided
    if state is not None:
        try:
            from memory_utils import add_memory_item
            add_memory_item(
                state,
                trigger=lesson_extracted.get('trigger'),
                lesson=lesson_extracted.get('lesson'),
                source=lesson_extracted.get('source')
            )
        except ImportError:
            pass  # memory_utils not available

    # Archive the mismatch
    log_to_archive("resolved_mismatch", {
        "mismatch_id": mismatch.get('id'),
        "expectation": mismatch.get('expectation'),
        "observation": mismatch.get('observation'),
        "delta": mismatch.get('delta'),
        "resolution": mismatch.get('resolution'),
        "trigger": mismatch.get('trigger'),
        "lesson_extracted": lesson_extracted
    })

    return True, lesson_extracted


def archive_completed_objective(objective, steps_completed, lessons_captured, self_score, session_range):
    """Archive a completed objective."""
    log_to_archive("completed_objective", {
        "objective": objective,
        "summary": f"Completed {steps_completed} steps, captured {lessons_captured} lessons",
        "steps_completed": steps_completed,
        "lessons_captured": lessons_captured,
        "self_score": self_score,
        "session_range": session_range
    })

    # Mark ClickUp task as complete if integration is enabled
    try:
        from clickup_utils import on_objective_complete
        on_objective_complete()
    except ImportError:
        pass  # ClickUp integration not available


def archive_decayed_lesson(memory_item, reason):
    """Archive a decayed (removed) lesson."""
    log_to_archive("decayed_lesson", {
        "trigger": memory_item.get('trigger'),
        "lesson": memory_item.get('lesson'),
        "reason": reason,
        "originally_learned": memory_item.get('source'),
        "reinforced": memory_item.get('reinforced', 0)
    })


def archive_completed_research(research_item):
    """Archive a completed research item."""
    log_to_archive("completed_research", {
        "research_id": research_item.get('id'),
        "topic": research_item.get('topic'),
        "priority": research_item.get('priority'),
        "blocking_step": research_item.get('blocking_step'),
        "results_summary": (research_item.get('results', '') or '')[:500],
        "action_items": research_item.get('action_items', [])
    })


# =============================================================================
# ARCHIVE RETRIEVAL
# =============================================================================

def load_archive(limit=None):
    """Load recent archive entries."""
    if limit is None:
        limit = ARCHIVE_SETTINGS["max_archive_entries_to_load"]

    archive_file = get_archive_file()
    if not archive_file.exists():
        return []

    entries = []
    try:
        for line in archive_file.read_text().strip().split('\n'):
            if line:
                entries.append(json.loads(line))
    except Exception:
        pass

    # Return most recent entries
    return entries[-limit:] if len(entries) > limit else entries


def search_archive(entry_type=None, keyword=None, limit=None):
    """Search archive entries by type and/or keyword."""
    if limit is None:
        limit = 50

    entries = load_archive(limit=ARCHIVE_SETTINGS["max_search_entries"])

    results = []
    for entry in entries:
        # Filter by type
        if entry_type and entry.get('type') != entry_type:
            continue

        # Filter by keyword (search all string values)
        if keyword:
            keyword_lower = keyword.lower()
            found = False
            for v in entry.values():
                if isinstance(v, str) and keyword_lower in v.lower():
                    found = True
                    break
            if not found:
                continue

        results.append(entry)

    return results[-limit:] if len(results) > limit else results


def get_archive_stats():
    """Get statistics about the archive."""
    entries = load_archive(limit=10000)
    if not entries:
        return {"total": 0}

    stats = {
        "total": len(entries),
        "by_type": {},
        "oldest": entries[0].get('timestamp') if entries else None,
        "newest": entries[-1].get('timestamp') if entries else None
    }

    for entry in entries:
        t = entry.get('type', 'unknown')
        stats["by_type"][t] = stats["by_type"].get(t, 0) + 1

    return stats


# =============================================================================
# ENTROPY CHECKING
# =============================================================================

def check_state_entropy(state):
    """
    Check if state is getting bloated and needs pruning.
    Returns (needs_pruning, reasons).
    """
    if not state:
        return False, []

    reasons = []

    # Check completed steps
    completed = count_completed_steps(state)
    if completed > ENTROPY_THRESHOLDS["max_completed_steps"]:
        reasons.append(f"{completed} completed steps should be archived")

    # Check resolved mismatches
    mismatches = state.get('mismatches', [])
    resolved = len([m for m in mismatches if isinstance(m, dict) and m.get('resolved')])
    if resolved > ENTROPY_THRESHOLDS["max_resolved_mismatches"]:
        reasons.append(f"{resolved} resolved mismatches should be archived")

    # Check memory for stale items
    memory = get_memory_items(state)
    stale = []
    for m in memory:
        if isinstance(m, dict):
            reinforced = m.get('reinforced', 0)
            last_used = m.get('last_used', '')
            if reinforced == 0 and last_used:
                stale.append(m.get('trigger', 'unknown'))
    if stale:
        reasons.append(f"{len(stale)} unreinforced memory items may be stale")

    return len(reasons) > 0, reasons


# =============================================================================
# PRUNING SYSTEM - Identify what should be archived from active state
# =============================================================================

def identify_prunable_steps(state):
    """
    Identify completed steps that should be archived.
    Keep only the most recent completed step; archive the rest.
    """
    if not state:
        return []

    plan = state.get('plan', [])
    completed = []

    for i, step in enumerate(plan):
        if isinstance(step, dict) and step.get('status') == 'completed':
            completed.append((i, step))

    # Keep the last completed step, archive the rest
    max_to_keep = ARCHIVE_SETTINGS["max_completed_steps_in_state"]
    if len(completed) > max_to_keep:
        return completed[:-max_to_keep]

    return []


def identify_prunable_mismatches(state):
    """
    Identify resolved mismatches that should be archived.
    v3.4: Only mismatches with triggers can be pruned (lesson extraction required).

    Returns list of (mismatch, validation_result) tuples.
    """
    if not state:
        return []

    mismatches = state.get('mismatches', [])
    prunable = []

    for m in mismatches:
        if not isinstance(m, dict) or not m.get('resolved', False):
            continue

        is_valid, error = validate_mismatch_for_archive(m)
        prunable.append({
            "mismatch": m,
            "valid": is_valid,
            "error": error
        })

    return prunable


def identify_decayed_memory(state, days_threshold=None):
    """
    Identify memory items that should decay out.
    Rules:
    - reinforced >= 2: Keep
    - reinforced == 1 and used within 7 days: Keep
    - reinforced == 0 and unused for days_threshold: Decay
    """
    if days_threshold is None:
        days_threshold = MEMORY_SETTINGS["decay_threshold_days"]

    if not state:
        return []

    memory = get_memory_items(state)
    decayed = []
    now = datetime.now()

    for m in memory:
        if not isinstance(m, dict):
            continue

        reinforced = m.get('reinforced', 0)

        # High-value lessons always stay
        if reinforced >= MEMORY_SETTINGS["reinforcement_threshold"]:
            continue

        last_used = m.get('last_used', '')
        if last_used:
            try:
                # Parse date (could be just date or full datetime)
                if 'T' in last_used:
                    last_dt = datetime.fromisoformat(last_used.replace('Z', '+00:00'))
                else:
                    last_dt = datetime.strptime(last_used, '%Y-%m-%d')

                days_old = (now - last_dt).days

                # Unreinforced and old enough to decay
                if reinforced == 0 and days_old >= days_threshold:
                    decayed.append((m, f"Unreinforced for {days_old} days"))
                elif reinforced == 1 and days_old >= 7:
                    # Single reinforcement but getting stale
                    decayed.append((m, f"Single use, {days_old} days old"))
            except (ValueError, TypeError):
                # Can't parse date, keep it for now
                pass
        elif reinforced == 0:
            # No last_used date and never reinforced - candidate for decay
            decayed.append((m, "Never used, no date"))

    return decayed


def compute_prune_plan(state):
    """
    Compute what should be pruned from the current state.
    Returns a dict with prunable items by category.
    """
    return {
        "steps": identify_prunable_steps(state),
        "mismatches": identify_prunable_mismatches(state),
        "memory": identify_decayed_memory(state),
        "summary": None  # Will be filled by caller
    }


def estimate_entropy_reduction(prune_plan):
    """Estimate how much the state will shrink after pruning."""
    steps = len(prune_plan.get("steps", []))
    mismatches = len(prune_plan.get("mismatches", []))
    memory = len(prune_plan.get("memory", []))

    # Rough estimate: each step ~5 lines, each mismatch ~8 lines, each memory ~4 lines
    lines_saved = (steps * 5) + (mismatches * 8) + (memory * 4)

    return {
        "items_to_prune": steps + mismatches + memory,
        "estimated_lines_saved": lines_saved,
        "breakdown": {
            "steps": steps,
            "mismatches": mismatches,
            "memory": memory
        }
    }
