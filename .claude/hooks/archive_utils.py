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
from edge_config import ENTROPY_THRESHOLDS, MEMORY_SETTINGS, ARCHIVE_SETTINGS, ARCHIVE_RETENTION


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
# LEARNED GUIDANCE - Objective Completion Capture (v7.1)
# =============================================================================

def _get_default_taxonomy() -> dict:
    """
    Default verb taxonomy when guidance_config.yaml is unavailable.

    This ensures the system works even without PyYAML installed.
    """
    return {
        "scope": {
            "description": "Define boundaries, identify what to work on",
            "synonyms": ["define", "identify", "bound", "scope", "map", "analyze", "understand", "explore", "discover", "find"]
        },
        "plan": {
            "description": "Design the approach, create structure",
            "synonyms": ["plan", "design", "architect", "structure", "outline", "draft", "sketch", "propose"]
        },
        "test": {
            "description": "Verify behavior, validate assumptions",
            "synonyms": ["test", "verify", "validate", "check", "assert", "confirm", "ensure", "prove"]
        },
        "build": {
            "description": "Create new functionality",
            "synonyms": ["build", "create", "implement", "add", "write", "develop", "construct", "make"]
        },
        "extract": {
            "description": "Pull out, separate, modularize",
            "synonyms": ["extract", "pull", "separate", "modularize", "isolate", "split", "factor"]
        },
        "integrate": {
            "description": "Combine, wire together, connect",
            "synonyms": ["integrate", "wire", "connect", "combine", "merge", "link", "join", "hook"]
        },
        "fix": {
            "description": "Repair broken behavior",
            "synonyms": ["fix", "repair", "resolve", "correct", "patch", "debug", "address"]
        },
        "clean": {
            "description": "Remove cruft, simplify",
            "synonyms": ["clean", "remove", "delete", "simplify", "prune", "trim", "eliminate"]
        },
        "document": {
            "description": "Write docs, comments, explanations",
            "synonyms": ["document", "comment", "explain", "describe", "annotate", "note"]
        },
        "deploy": {
            "description": "Ship, release, publish",
            "synonyms": ["deploy", "ship", "release", "publish", "push", "launch", "roll out"]
        }
    }


def _load_verb_taxonomy() -> dict:
    """
    Load the verb taxonomy from guidance_config.yaml.

    Falls back to built-in defaults if:
    - YAML file doesn't exist
    - PyYAML isn't installed
    - Any other error loading config
    """
    from pathlib import Path

    config_file = Path(__file__).parent / "guidance_config.yaml"
    if not config_file.exists():
        return _get_default_taxonomy()

    try:
        import yaml
        with open(config_file) as f:
            config = yaml.safe_load(f)
        return config.get("verb_taxonomy", _get_default_taxonomy())
    except ImportError:
        # PyYAML not installed - use defaults
        return _get_default_taxonomy()
    except Exception:
        # Any other error - use defaults
        return _get_default_taxonomy()


def _normalize_step_to_verb(step_description: str, taxonomy: dict) -> str:
    """
    Normalize a step description to a canonical verb.

    Searches for synonym matches in the taxonomy and returns
    the canonical verb. Falls back to 'other' if no match.
    """
    if not step_description or not taxonomy:
        return "other"

    description_lower = step_description.lower()

    # Check each canonical verb's synonyms
    for verb, verb_data in taxonomy.items():
        synonyms = verb_data.get("synonyms", [])
        for synonym in synonyms:
            if synonym in description_lower:
                return verb

    return "other"


def _extract_approach_summary(plan: list, taxonomy: dict) -> list:
    """
    Extract normalized approach from completed plan steps.

    Returns list of dicts with verb and original description.
    """
    approach = []
    for step in plan:
        if not isinstance(step, dict):
            continue
        if step.get("status") != "completed":
            continue

        description = step.get("description", "")
        verb = _normalize_step_to_verb(description, taxonomy)

        approach.append({
            "verb": verb,
            "description": description[:100],  # Truncate for storage
            "proof": (step.get("proof") or "")[:200]  # Truncate proof
        })

    return approach


def _compute_objective_metrics(state: dict) -> dict:
    """
    Compute metrics from objective completion.

    Returns dict with step counts, mismatch stats, lesson stats.
    """
    plan = state.get("plan", [])
    mismatches = state.get("mismatches", [])
    memory = state.get("memory", [])

    # Count steps by status
    steps_planned = len(plan)
    steps_completed = sum(1 for s in plan if isinstance(s, dict) and s.get("status") == "completed")
    steps_abandoned = sum(1 for s in plan if isinstance(s, dict) and s.get("status") in ("pending", "blocked", "in_progress"))

    # Count mismatches
    mismatches_encountered = len(mismatches)
    mismatches_resolved = sum(1 for m in mismatches if isinstance(m, dict) and m.get("resolved"))

    # Count lessons (approximation - we don't track which were added this session)
    lessons_count = len(memory) if isinstance(memory, list) else 0

    return {
        "steps_planned": steps_planned,
        "steps_completed": steps_completed,
        "steps_abandoned": steps_abandoned,
        "mismatches_encountered": mismatches_encountered,
        "mismatches_resolved": mismatches_resolved,
        "lessons_in_memory": lessons_count
    }


def _infer_tags_from_objective(objective: str) -> list:
    """
    Infer tags from objective text for pattern matching.

    Returns list of lowercase tags.
    """
    if not objective:
        return []

    objective_lower = objective.lower()
    tags = []

    # Common objective type indicators
    tag_keywords = {
        "refactoring": ["refactor", "reorganize", "restructure", "modular"],
        "feature": ["add", "implement", "create", "build", "new"],
        "bugfix": ["fix", "bug", "broken", "error", "issue"],
        "migration": ["migrate", "upgrade", "move", "transition"],
        "documentation": ["document", "docs", "readme", "guide"],
        "testing": ["test", "coverage", "spec", "validation"],
        "performance": ["optimize", "performance", "speed", "fast"],
        "security": ["security", "auth", "permission", "access"],
        "cleanup": ["clean", "remove", "delete", "prune", "deprecate"],
        "integration": ["integrate", "connect", "api", "external"]
    }

    for tag, keywords in tag_keywords.items():
        if any(kw in objective_lower for kw in keywords):
            tags.append(tag)

    return tags


def capture_objective_completion(
    state: dict,
    session_id: str,
    outcome_quality: str = "clean",
    outcome_notes: str = ""
) -> dict:
    """
    Capture comprehensive objective completion data for learned guidance.

    This is the core Phase 1 function that creates rich data for pattern
    recognition. Called when an objective is marked complete.

    Args:
        state: The active_context state dict
        session_id: Current session ID
        outcome_quality: "clean" | "messy" | "partial"
        outcome_notes: Free-text notes on the outcome

    Returns:
        The archive entry that was created
    """
    taxonomy = _load_verb_taxonomy()

    objective = state.get("objective", "Unknown")
    plan = state.get("plan", [])

    # Extract normalized approach
    approach_summary = _extract_approach_summary(plan, taxonomy)

    # Just the verbs for pattern matching
    approach_verbs = [step["verb"] for step in approach_summary]

    # Compute metrics
    metrics = _compute_objective_metrics(state)

    # Infer tags
    tags = _infer_tags_from_objective(objective)

    # Get self-score if available
    self_score = state.get("self_score")
    score_level = None
    score_total = None
    if self_score and isinstance(self_score, dict):
        score_level = self_score.get("level")
        score_total = self_score.get("total")

    # Phase 4: Process feedback loop - check if suggestion was followed
    guidance_data = {
        "pattern_suggested": None,
        "suggestion_confidence": None,
        "suggestion_followed": None,
        "follow_score": None,
        "confidence_updated": None
    }

    try:
        from feedback_loop import process_completion_feedback
        feedback = process_completion_feedback(
            objective=objective,
            approach_verbs=approach_verbs,
            success=True,  # This function is for completions
            session_id=session_id
        )
        if feedback.suggestion_found:
            guidance_data = {
                "pattern_suggested": feedback.pattern_id,
                "pattern_source": feedback.pattern_source,
                "suggestion_confidence": feedback.new_confidence,
                "suggestion_followed": feedback.suggestion_followed,
                "follow_score": round(feedback.follow_score, 3) if feedback.follow_score else None,
                "confidence_updated": round(feedback.confidence_delta, 3) if feedback.confidence_delta else None
            }
    except ImportError:
        pass  # feedback_loop not available
    except Exception:
        pass  # Non-critical feedback processing failure

    # Build the entry
    entry_data = {
        "objective": objective,
        "objective_hash": _hash_objective(objective),
        "session_id": session_id,
        "approach_summary": approach_summary,
        "approach_verbs": approach_verbs,
        "metrics": metrics,
        "outcome": {
            "success": True,  # This function is for completions
            "quality": outcome_quality,
            "notes": outcome_notes[:500] if outcome_notes else ""
        },
        "tags": tags,
        "self_score": {
            "level": score_level,
            "total": score_total
        } if score_level else None,
        # Phase 4: Track guidance feedback
        "guidance": guidance_data
    }

    log_to_archive("objective_completion", entry_data)
    # Include type in returned dict for consistency with archive format
    return {"type": "objective_completion", **entry_data}


def _hash_objective(objective: str) -> str:
    """Create a short hash of objective for deduplication."""
    import hashlib
    if not objective:
        return "unknown"
    return hashlib.sha256(objective.encode()).hexdigest()[:12]


def capture_objective_partial(
    state: dict,
    session_id: str,
    reason: str = "unknown",
    new_objective: str = ""
) -> dict:
    """
    Capture data when an objective is abandoned or changed mid-way.

    This captures valuable data about what was working before the change,
    which can inform pattern recognition.

    Args:
        state: The active_context state dict (before change)
        session_id: Current session ID
        reason: "scope_changed" | "blocked" | "superseded" | "abandoned" | "unknown"
        new_objective: The new objective being set (if any)

    Returns:
        The archive entry that was created
    """
    taxonomy = _load_verb_taxonomy()

    objective = state.get("objective", "Unknown")
    plan = state.get("plan", [])

    # Extract what was completed before abandonment
    approach_summary = _extract_approach_summary(plan, taxonomy)
    approach_verbs = [step["verb"] for step in approach_summary]

    # Find where we stopped
    last_completed_idx = -1
    for i, step in enumerate(plan):
        if isinstance(step, dict) and step.get("status") == "completed":
            last_completed_idx = i

    # Find the next step that wasn't completed
    abandoned_at = None
    if last_completed_idx + 1 < len(plan):
        next_step = plan[last_completed_idx + 1]
        if isinstance(next_step, dict):
            desc = next_step.get("description", "")
            abandoned_at = {
                "step_index": last_completed_idx + 1,
                "description": desc[:100],
                "verb": _normalize_step_to_verb(desc, taxonomy),
                "status": next_step.get("status", "pending")
            }

    # Compute metrics
    metrics = _compute_objective_metrics(state)

    # Infer tags
    tags = _infer_tags_from_objective(objective)

    entry_data = {
        "objective": objective,
        "objective_hash": _hash_objective(objective),
        "session_id": session_id,
        "reason": reason,
        "new_objective": new_objective[:200] if new_objective else None,
        "approach_summary": approach_summary,
        "approach_verbs": approach_verbs,
        "abandoned_at": abandoned_at,
        "metrics": metrics,
        "tags": tags
    }

    log_to_archive("objective_partial", entry_data)
    # Include type in returned dict for consistency with archive format
    return {"type": "objective_partial", **entry_data}


def get_objective_completions(limit: int = 50) -> list:
    """
    Retrieve objective completion records from archive.

    Used by pattern recognition (Phase 2) to analyze past work.
    """
    entries = load_archive(limit=500)  # Load more, filter down

    completions = [
        e for e in entries
        if e.get("type") == "objective_completion"
    ]

    return completions[-limit:] if len(completions) > limit else completions


def get_objective_partials(limit: int = 50) -> list:
    """
    Retrieve partial/abandoned objective records from archive.

    Used to understand what approaches don't work.
    """
    entries = load_archive(limit=500)

    partials = [
        e for e in entries
        if e.get("type") == "objective_partial"
    ]

    return partials[-limit:] if len(partials) > limit else partials


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


# =============================================================================
# MEMORY DECAY HELPERS (extracted for clarity)
# =============================================================================

def parse_last_used_date(last_used: str) -> datetime:
    """
    Parse a last_used date string into a datetime object.

    Handles both formats:
    - Full ISO datetime: "2026-01-13T12:00:00"
    - Date only: "2026-01-13"

    Returns:
        datetime object, or None if parsing fails
    """
    if not last_used:
        return None
    try:
        if 'T' in last_used:
            return datetime.fromisoformat(last_used.replace('Z', '+00:00'))
        else:
            return datetime.strptime(last_used, '%Y-%m-%d')
    except (ValueError, TypeError):
        return None


def is_lesson_vital(trigger: str) -> bool:
    """
    Check if a lesson is protected by proof vitality.

    Uses lazy import to avoid circular dependency with proof_utils.

    Returns:
        True if lesson has recent proof observations, False otherwise
    """
    if not trigger:
        return False

    try:
        from proof_utils import check_lesson_vitality
        vitality_threshold = MEMORY_SETTINGS.get("vitality_threshold", 1)
        vitality_lookback = MEMORY_SETTINGS.get("vitality_lookback_days", 14)
        is_vital, _ = check_lesson_vitality(trigger, vitality_threshold, vitality_lookback)
        return is_vital
    except ImportError:
        return False


def check_lesson_decay(lesson: dict, days_threshold: int, now: datetime) -> tuple:
    """
    Check if a single lesson should decay.

    Args:
        lesson: The memory/lesson dict
        days_threshold: Days of inactivity before decay
        now: Current datetime for age calculation

    Returns:
        (should_decay: bool, reason: str or None)
    """
    reinforced = lesson.get('reinforced', 0)

    # High-value lessons always stay
    if reinforced >= MEMORY_SETTINGS["reinforcement_threshold"]:
        return (False, None)

    last_used = lesson.get('last_used', '')
    last_dt = parse_last_used_date(last_used)

    if last_dt:
        days_old = (now - last_dt).days

        # Unreinforced and old enough to decay
        if reinforced == 0 and days_old >= days_threshold:
            return (True, f"Unreinforced for {days_old} days")
        elif reinforced == 1 and days_old >= 7:
            return (True, f"Single use, {days_old} days old")
    elif reinforced == 0:
        # No last_used date and never reinforced
        return (True, "Never used, no date")

    return (False, None)


def identify_decayed_memory(state, days_threshold=None):
    """
    Identify memory items that should decay out.
    Rules (in priority order):
    - evergreen: true: Keep (v3.10)
    - proof vitality >= threshold: Keep (v3.10.1 - observations override claims)
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

        # Evergreen lessons never decay (v3.10)
        if m.get('evergreen'):
            continue

        # Proof-grounded vitality check (v3.10.1)
        if is_lesson_vital(m.get('trigger', '')):
            continue  # Protected by proof vitality

        # Check if lesson should decay based on reinforcement and age
        should_decay, reason = check_lesson_decay(m, days_threshold, now)
        if should_decay:
            decayed.append((m, reason))

    return decayed


def get_vitality_protected_lessons(state):
    """
    Identify lessons that would decay but are protected by proof vitality (v3.10.1).

    Returns list of (lesson, vitality_info) tuples for lessons where:
    - Would normally decay (low reinforcement, old)
    - But proof shows recent usage (vitality >= threshold)
    """
    if not state:
        return []

    memory = get_memory_items(state)
    protected = []

    # Import proof vitality checker (lazy to avoid circular imports)
    try:
        from proof_utils import get_proof_vitality
        vitality_threshold = MEMORY_SETTINGS.get("vitality_threshold", 1)
        vitality_lookback = MEMORY_SETTINGS.get("vitality_lookback_days", 14)
    except ImportError:
        return []

    days_threshold = MEMORY_SETTINGS.get("decay_threshold_days", 14)
    now = datetime.now()

    for m in memory:
        if not isinstance(m, dict):
            continue

        # Skip evergreen (different protection mechanism)
        if m.get('evergreen'):
            continue

        reinforced = m.get('reinforced', 0)

        # Only check lessons that would normally be decay candidates
        if reinforced >= MEMORY_SETTINGS.get("reinforcement_threshold", 2):
            continue

        # Check if this lesson has proof vitality
        trigger = m.get('trigger', '')
        if trigger:
            vitality = get_proof_vitality(trigger, vitality_lookback)
            if vitality["matches"] >= vitality_threshold:
                # This lesson would decay but is protected by vitality
                last_used = m.get('last_used', '')
                if last_used:
                    try:
                        if 'T' in last_used:
                            last_dt = datetime.fromisoformat(last_used.replace('Z', '+00:00'))
                        else:
                            last_dt = datetime.strptime(last_used, '%Y-%m-%d')

                        days_old = (now - last_dt).days

                        # Would it have decayed?
                        would_decay = (reinforced == 0 and days_old >= days_threshold) or \
                                     (reinforced == 1 and days_old >= 7)

                        if would_decay:
                            protected.append((m, vitality))
                    except (ValueError, TypeError):
                        pass

    return protected


def get_memory_reconciliation_info(state):
    """
    Compare proof observations to YAML claims for memory items (v3.10.1).

    Returns list of dicts showing discrepancies between:
    - proof_matches: Actual usage observed in proof logs
    - yaml_reinforced: Claimed reinforcement count in YAML

    This helps Claude decide whether to manually update YAML counts.
    """
    if not state:
        return []

    memory = get_memory_items(state)
    reconciliation = []

    # Import proof vitality checker
    try:
        from proof_utils import get_proof_vitality
        vitality_lookback = MEMORY_SETTINGS.get("vitality_lookback_days", 14)
    except ImportError:
        return []

    for m in memory:
        if not isinstance(m, dict):
            continue

        trigger = m.get('trigger', '')
        if not trigger:
            continue

        yaml_reinforced = m.get('reinforced', 0)
        vitality = get_proof_vitality(trigger, vitality_lookback)
        proof_matches = vitality.get("matches", 0)

        # Only report if there's a discrepancy (proof shows more usage than YAML claims)
        if proof_matches > yaml_reinforced:
            reconciliation.append({
                "trigger": trigger,
                "proof_matches": proof_matches,
                "yaml_reinforced": yaml_reinforced,
                "discrepancy": proof_matches - yaml_reinforced,
                "last_match": vitality.get("last_match")
            })

    # Sort by discrepancy (biggest gaps first)
    reconciliation.sort(key=lambda x: x["discrepancy"], reverse=True)

    return reconciliation


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


# =============================================================================
# ARCHIVE RETENTION POLICY (v3.10 - Living Memory)
# =============================================================================

def cleanup_archive(dry_run=False):
    """
    Clean up archive based on type-specific retention policy.
    Returns (entries_removed, entries_kept) or just analysis in dry_run mode.
    """
    archive_file = get_archive_file()
    if not archive_file.exists():
        return (0, 0) if not dry_run else {"removed": 0, "kept": 0, "by_type": {}}

    now = datetime.now()
    entries_to_keep = []
    entries_removed = 0
    by_type = {}

    with open(archive_file, 'r') as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                entry = json.loads(line)
                entry_type = entry.get("type", "unknown")
                timestamp_str = entry.get("timestamp", "")

                # Get retention days for this type
                retention_days = ARCHIVE_RETENTION.get(
                    entry_type,
                    ARCHIVE_RETENTION.get("default", 90)
                )

                # Track by type
                if entry_type not in by_type:
                    by_type[entry_type] = {"total": 0, "removed": 0, "kept": 0}
                by_type[entry_type]["total"] += 1

                # Parse timestamp and check age
                try:
                    if 'T' in timestamp_str:
                        entry_time = datetime.fromisoformat(timestamp_str.replace('Z', '+00:00'))
                    else:
                        entry_time = datetime.strptime(timestamp_str, '%Y-%m-%d')

                    days_old = (now - entry_time).days

                    if days_old > retention_days:
                        entries_removed += 1
                        by_type[entry_type]["removed"] += 1
                    else:
                        entries_to_keep.append(entry)
                        by_type[entry_type]["kept"] += 1
                except (ValueError, TypeError):
                    # Can't parse timestamp, keep it
                    entries_to_keep.append(entry)
                    by_type[entry_type]["kept"] += 1

            except json.JSONDecodeError:
                # Keep malformed entries
                entries_to_keep.append({"_raw": line})

    if dry_run:
        return {
            "removed": entries_removed,
            "kept": len(entries_to_keep),
            "by_type": by_type
        }

    # Write back cleaned archive
    if entries_removed > 0:
        with open(archive_file, 'w') as f:
            for entry in entries_to_keep:
                if "_raw" in entry:
                    f.write(entry["_raw"] + "\n")
                else:
                    f.write(json.dumps(entry) + "\n")

    return (entries_removed, len(entries_to_keep))
