#!/usr/bin/env python3
"""
Operator's Edge - Memory Utilities
Memory surfacing, reinforcement, and retrieval.

Split from orchestration_utils.py for better modularity.
"""
from datetime import datetime

from state_utils import get_memory_items
from archive_utils import search_archive


# =============================================================================
# MEMORY SYSTEM - Surfacing, decay, and retrieval
# =============================================================================

def surface_relevant_memory(state, context_text):
    """
    Find memory items whose triggers match the current context.
    Returns list of relevant memory items.
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
            relevant.append({
                "trigger": m.get('trigger'),
                "lesson": m.get('lesson'),
                "reinforced": m.get('reinforced', 0),
                "match_score": matches / len(trigger_words)
            })

    # Sort by match score and reinforcement
    relevant.sort(key=lambda x: (x['match_score'], x['reinforced']), reverse=True)

    return relevant[:3]  # Return top 3


def reinforce_memory(state, trigger):
    """
    Reinforce a memory item when it proves useful.
    Returns True if found and reinforced.
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
