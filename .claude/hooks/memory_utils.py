#!/usr/bin/env python3
"""
Operator's Edge - Memory Utilities
Memory surfacing, reinforcement, and retrieval.

Split from orchestration_utils.py for better modularity.

v3.12: Auto-learn file patterns from proof - zero config lesson targeting.
"""
import fnmatch
import os
from datetime import datetime
from typing import Dict, List, Optional, Any

import state_utils
from archive_utils import search_archive


# Re-export for backward compatibility
def get_memory_items(state):
    """Wrapper for testability - allows mocking."""
    return state_utils.get_memory_items(state)


# =============================================================================
# MEMORY SYSTEM - Surfacing, decay, and retrieval
# =============================================================================

def surface_relevant_memory(state, context_text, file_path=None):
    """
    Find memory items whose triggers match the current context.
    Returns list of relevant memory items.

    v3.12: If file_path provided and lesson has learned_patterns,
    only surface if file matches the learned pattern.
    """
    if not state or not context_text:
        return []

    memory = get_memory_items(state)
    context_lower = context_text.lower()
    relevant = []

    for m in memory:
        if not isinstance(m, dict):
            continue

        trigger = m.get('trigger', '').lower()
        if not trigger or trigger == '*':
            continue

        # Check if trigger words appear in context
        trigger_words = trigger.split()
        matches = sum(1 for word in trigger_words if word in context_lower)

        # Consider relevant if >50% of trigger words match
        if matches > len(trigger_words) / 2:
            # v3.12: Check learned pattern if file_path provided
            if file_path and not matches_learned_pattern(m, file_path):
                continue  # Skip - lesson doesn't apply to this file type

            relevant.append({
                "trigger": m.get('trigger'),
                "lesson": m.get('lesson'),
                "reinforced": m.get('reinforced', 0),
                "match_score": matches / len(trigger_words),
                "learned_patterns": m.get('learned_patterns')  # Include for transparency
            })

    # Sort by match score and reinforcement
    relevant.sort(key=lambda x: (x['match_score'], x['reinforced']), reverse=True)

    return relevant[:3]  # Return top 3


def reinforce_memory(state, trigger):
    """
    Reinforce a memory item when it proves useful.
    Returns True if found and reinforced.

    Note (v3.10.1): This function modifies in-memory state but hooks cannot
    persist YAML changes. It's available for Claude to use when manually
    updating active_context.yaml, but not called automatically from hooks.
    Instead, hooks log lesson_match to proof, and decay decisions check
    proof vitality (observations > claims).
    """
    memory = state.get('memory', [])
    today = datetime.now().strftime('%Y-%m-%d')

    for m in memory:
        if isinstance(m, dict) and m.get('trigger', '').lower() == trigger.lower():
            m['reinforced'] = m.get('reinforced', 0) + 1
            m['last_used'] = today
            return True

    return False


def add_memory_item(state, trigger, lesson, applies_to=None, source=None, dedup=True, threshold=0.4):
    """
    Add a new memory item to state, with optional deduplication.

    If dedup=True (default), checks for similar existing lessons:
    - If exact match found: reinforce existing, return it
    - If similar found: reinforce existing, return it with 'deduplicated' flag
    - Otherwise: add new lesson

    Args:
        state: The state dict
        trigger: Trigger for the lesson
        lesson: The lesson text
        applies_to: Optional list of contexts
        source: Optional source identifier
        dedup: Whether to check for duplicates (default True)
        threshold: Similarity threshold (default 0.4)

    Returns:
        dict with the memory item and optional 'deduplicated' flag
    """
    # Import here to avoid circular dependency
    from lesson_utils import find_similar_lesson

    if 'memory' not in state:
        state['memory'] = []

    today = datetime.now().strftime('%Y-%m-%d')
    session_id = state.get('session', {}).get('id', 'unknown')

    # Check for similar existing lesson if dedup enabled
    if dedup and state['memory']:
        idx, match = find_similar_lesson(lesson, state['memory'], threshold)
        if match and match.get('is_similar'):
            # Found similar - reinforce existing instead of adding
            existing = state['memory'][idx]
            if isinstance(existing, dict):
                existing['reinforced'] = existing.get('reinforced', 0) + 1
                existing['last_used'] = today
                return {
                    **existing,
                    'deduplicated': True,
                    'similarity': match.get('keyword_similarity', 0),
                    'original_lesson': lesson
                }
            else:
                # Old format (string) - convert to dict and reinforce
                state['memory'][idx] = {
                    "trigger": trigger,
                    "lesson": existing,
                    "applies_to": applies_to or [],
                    "reinforced": 2,
                    "last_used": today,
                    "source": source or session_id
                }
                return {
                    **state['memory'][idx],
                    'deduplicated': True,
                    'original_lesson': lesson
                }

    # No duplicate found - add new lesson
    new_item = {
        "trigger": trigger,
        "lesson": lesson,
        "applies_to": applies_to or [],
        "reinforced": 1,
        "last_used": today,
        "source": source or session_id
    }

    # v3.6: Auto-infer audit pattern for code-related lessons
    try:
        from audit_utils import infer_audit_pattern, infer_audit_scope
        audit_pattern = infer_audit_pattern(lesson, trigger)
        if audit_pattern:
            new_item["audit_pattern"] = audit_pattern
            audit_scope = infer_audit_scope(lesson, trigger)
            if audit_scope:
                new_item["audit_scope"] = audit_scope
    except ImportError:
        pass  # audit_utils not available, skip pattern inference

    state['memory'].append(new_item)
    return new_item


def retrieve_from_archive(keyword, entry_type="resolved_mismatch", limit=5):
    """
    Retrieve relevant items from archive based on keyword search.
    Useful for finding past solutions to similar problems.
    """
    return search_archive(entry_type=entry_type, keyword=keyword, limit=limit)


def resurrect_archived_lesson(archived_item, state):
    """
    Bring an archived lesson back into active memory.
    Used when a past lesson becomes relevant again.
    """
    lesson_data = archived_item.get('lesson_extracted', {})
    if not lesson_data:
        return None

    return add_memory_item(
        state,
        trigger=lesson_data.get('trigger', 'unknown'),
        lesson=lesson_data.get('lesson', 'no lesson'),
        source=f"resurrected-{archived_item.get('timestamp', 'unknown')}"
    )


def get_memory_summary(state):
    """Get a summary of current memory state."""
    memory = get_memory_items(state)

    if not memory:
        return {"count": 0, "high_value": 0, "at_risk": 0}

    high_value = len([m for m in memory if isinstance(m, dict) and m.get('reinforced', 0) >= 2])
    at_risk = len([m for m in memory if isinstance(m, dict) and m.get('reinforced', 0) == 0])

    return {
        "count": len(memory),
        "high_value": high_value,
        "at_risk": at_risk,
        "items": [
            {
                "trigger": m.get('trigger'),
                "reinforced": m.get('reinforced', 0)
            }
            for m in memory if isinstance(m, dict)
        ]
    }


# =============================================================================
# AUTO-LEARN FILE PATTERNS (v3.12 - Zero Config Lesson Targeting)
# =============================================================================

def get_lesson_applications(trigger: str, days_lookback: int = 14) -> List[Dict[str, Any]]:
    """
    Get all files where a lesson was successfully applied.

    Scans proof logs for obligation:applied events matching the trigger.
    Returns list of file paths where the lesson led to successful tool use.
    """
    try:
        from proof_utils import get_sessions_dir
    except ImportError:
        return []

    sessions_dir = get_sessions_dir()
    if not sessions_dir.exists():
        return []

    import json
    from datetime import timedelta
    cutoff = datetime.now() - timedelta(days=days_lookback)

    applications = []

    for log_file in sessions_dir.glob("*.jsonl"):
        try:
            session_id = log_file.stem
            session_date = datetime.strptime(session_id, "%Y%m%d-%H%M%S")

            if session_date < cutoff:
                continue

            content = log_file.read_text()
            for line in content.strip().split('\n'):
                if not line.strip():
                    continue

                try:
                    entry = json.loads(line)

                    # Look for applied obligations with matching trigger
                    if entry.get("type") == "obligation:applied":
                        if entry.get("lesson_trigger", "").lower() == trigger.lower():
                            # Get file path from input_preview
                            input_data = entry.get("input_preview", {})
                            if isinstance(input_data, dict):
                                file_path = input_data.get("file_path") or input_data.get("file")
                                if file_path:
                                    applications.append({
                                        "file_path": file_path,
                                        "timestamp": entry.get("timestamp"),
                                        "tool": entry.get("tool_name")
                                    })

                    # Also check Edit/Write proof entries with lesson_match
                    if entry.get("tool") in ("Edit", "Write", "NotebookEdit"):
                        input_data = entry.get("input_preview", {})
                        if isinstance(input_data, dict):
                            file_path = input_data.get("file") or input_data.get("file_path")
                            if file_path and entry.get("success"):
                                applications.append({
                                    "file_path": file_path,
                                    "timestamp": entry.get("timestamp"),
                                    "tool": entry.get("tool")
                                })

                except (json.JSONDecodeError, KeyError):
                    continue

        except (ValueError, OSError):
            continue

    return applications


def infer_file_pattern(paths: List[str], min_sample: int = 3) -> Optional[str]:
    """
    Infer a common glob pattern from a list of file paths.

    Returns the most specific pattern that covers most paths.
    Returns None if no clear pattern emerges.
    """
    if len(paths) < min_sample:
        return None

    # Extract components
    dirs = [os.path.dirname(p) for p in paths]
    filenames = [os.path.basename(p) for p in paths]
    extensions = [os.path.splitext(p)[1] for p in paths]

    # Find common directory
    common_dir = os.path.commonpath(dirs) if dirs and all(dirs) else ""

    # Find common extension
    ext_counts = {}
    for ext in extensions:
        ext_counts[ext] = ext_counts.get(ext, 0) + 1

    most_common_ext = max(ext_counts, key=ext_counts.get) if ext_counts else ""
    ext_ratio = ext_counts.get(most_common_ext, 0) / len(paths)

    # Build pattern
    if common_dir and ext_ratio >= 0.8:
        # Strong pattern: common directory + common extension
        pattern = f"{common_dir}/*{most_common_ext}"
        coverage = sum(1 for p in paths if fnmatch.fnmatch(p, pattern)) / len(paths)
        if coverage >= 0.7:
            return pattern

    if ext_ratio >= 0.9:
        # Extension-only pattern
        pattern = f"**/*{most_common_ext}"
        return pattern

    if common_dir:
        # Directory-only pattern
        pattern = f"{common_dir}/*"
        coverage = sum(1 for p in paths if fnmatch.fnmatch(p, pattern)) / len(paths)
        if coverage >= 0.7:
            return pattern

    return None


def learn_lesson_patterns(state: dict, days_lookback: int = 14) -> Dict[str, Dict]:
    """
    Learn file patterns for all lessons from proof data.

    Analyzes which files each lesson was successfully applied to,
    then infers glob patterns that can filter future surfacing.

    Returns dict of trigger -> learned_pattern info.
    Does NOT modify state (caller should update YAML if desired).
    """
    memory = get_memory_items(state)
    learned = {}

    for m in memory:
        if not isinstance(m, dict):
            continue

        trigger = m.get('trigger', '')
        if not trigger:
            continue

        # Get successful applications
        applications = get_lesson_applications(trigger, days_lookback)

        if len(applications) >= 3:
            # Extract unique file paths
            paths = list(set(a['file_path'] for a in applications if a.get('file_path')))

            if len(paths) >= 3:
                pattern = infer_file_pattern(paths)

                if pattern:
                    # Calculate coverage
                    coverage = sum(1 for p in paths if fnmatch.fnmatch(p, pattern)) / len(paths)

                    learned[trigger] = {
                        "inferred_pattern": pattern,
                        "sample_paths": paths[:5],
                        "applications": len(applications),
                        "coverage": round(coverage, 2),
                        "learned_at": datetime.now().isoformat()
                    }

    return learned


def matches_learned_pattern(lesson: dict, file_path: str) -> bool:
    """
    Check if a file matches a lesson's learned pattern.

    Returns True if:
    - No pattern learned (backward compatible - match by keywords only)
    - File matches the learned pattern
    """
    learned = lesson.get('learned_patterns', {})

    if not learned:
        return True  # No pattern - allow match

    pattern = learned.get('inferred_pattern')
    if not pattern:
        return True  # No pattern - allow match

    # Check coverage threshold - only enforce if confident
    coverage = learned.get('coverage', 0)
    if coverage < 0.7:
        return True  # Low confidence - don't enforce

    return fnmatch.fnmatch(file_path, pattern)
