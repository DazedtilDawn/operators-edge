#!/usr/bin/env python3
"""
Operator's Edge - Lesson Utilities
Lesson similarity, deduplication, and consolidation.

Split from orchestration_utils.py for better modularity.
"""

# =============================================================================
# LESSON SIMILARITY - Deduplication and consolidation
# =============================================================================

# Thematic keywords for grouping lessons
LESSON_THEMES = {
    "cross_platform": ["windows", "mac", "linux", "platform", "dotfile", "path", "cross-platform"],
    "imports_modules": ["import", "module", "sys.path", "require", "export", "facade"],
    "enforcement": ["enforce", "hook", "policy", "block", "gate", "validation"],
    "memory_state": ["memory", "state", "archive", "prune", "constant", "decay", "lesson"],
    "architecture": ["pattern", "refactor", "facade", "entry", "modular", "structure"],
    "claude_code": ["claude", "command", "restart", "skill", "subagent"],
}

# Words to ignore in similarity comparison
STOPWORDS = {
    "the", "a", "an", "is", "are", "was", "were", "be", "been", "being",
    "have", "has", "had", "do", "does", "did", "will", "would", "could",
    "should", "may", "might", "must", "shall", "can", "need", "dare",
    "to", "of", "in", "for", "on", "with", "at", "by", "from", "as",
    "into", "through", "during", "before", "after", "above", "below",
    "between", "under", "again", "further", "then", "once", "here",
    "there", "when", "where", "why", "how", "all", "each", "few",
    "more", "most", "other", "some", "such", "no", "nor", "not",
    "only", "own", "same", "so", "than", "too", "very", "just",
    "that", "this", "these", "those", "what", "which", "who",
    "and", "but", "if", "or", "because", "until", "while"
}


def get_lesson_text(lesson):
    """Extract text from a lesson (handles both dict and string formats)."""
    if isinstance(lesson, dict):
        return lesson.get('lesson', str(lesson))
    return str(lesson)


def get_lesson_keywords(lesson_text):
    """
    Extract significant keywords from a lesson.

    Returns set of lowercase keywords (excluding stopwords).
    """
    # Normalize: lowercase, replace separators with spaces
    text = lesson_text.lower()
    for sep in ['-', '_', '/', '.', ',', '(', ')', "'", '"', ':']:
        text = text.replace(sep, ' ')

    # Split into words and filter
    words = text.split()
    keywords = set()

    for word in words:
        # Skip short words, stopwords, and numbers
        if len(word) < 3:
            continue
        if word in STOPWORDS:
            continue
        if word.isdigit():
            continue
        keywords.add(word)

    return keywords


def detect_lesson_theme(lesson_text):
    """
    Detect the primary theme(s) of a lesson.

    Returns list of matching theme names.
    """
    text_lower = lesson_text.lower()
    themes = []

    for theme_name, keywords in LESSON_THEMES.items():
        for keyword in keywords:
            if keyword in text_lower:
                themes.append(theme_name)
                break  # One match per theme is enough

    return themes if themes else ["other"]


def compare_lessons(lesson1, lesson2, threshold=0.4):
    """
    Compare two lessons for similarity.

    Uses multiple signals:
    1. Exact match (after normalization)
    2. Keyword overlap (Jaccard similarity)
    3. Theme match

    Args:
        lesson1: First lesson (dict or string)
        lesson2: Second lesson (dict or string)
        threshold: Minimum Jaccard similarity to consider similar (default 0.4)

    Returns:
        dict with:
        - is_similar: bool
        - is_exact: bool
        - keyword_similarity: float (0-1)
        - theme_match: bool
        - shared_keywords: set
        - shared_themes: list
    """
    text1 = get_lesson_text(lesson1)
    text2 = get_lesson_text(lesson2)

    # Normalize for exact comparison
    norm1 = ' '.join(text1.lower().split())
    norm2 = ' '.join(text2.lower().split())
    is_exact = norm1 == norm2

    # Keyword analysis
    kw1 = get_lesson_keywords(text1)
    kw2 = get_lesson_keywords(text2)

    shared = kw1 & kw2
    union = kw1 | kw2
    jaccard = len(shared) / len(union) if union else 0

    # Theme analysis
    themes1 = set(detect_lesson_theme(text1))
    themes2 = set(detect_lesson_theme(text2))
    shared_themes = list(themes1 & themes2)
    theme_match = bool(shared_themes) and "other" not in shared_themes

    # Determine overall similarity
    # Similar if: exact match OR (keyword overlap >= threshold AND theme matches)
    is_similar = is_exact or (jaccard >= threshold and theme_match)

    return {
        "is_similar": is_similar,
        "is_exact": is_exact,
        "keyword_similarity": round(jaccard, 3),
        "theme_match": theme_match,
        "shared_keywords": shared,
        "shared_themes": shared_themes
    }


def find_similar_lesson(new_lesson, existing_lessons, threshold=0.4):
    """
    Find if a similar lesson already exists.

    Args:
        new_lesson: The lesson to check (dict or string)
        existing_lessons: List of existing lessons
        threshold: Similarity threshold

    Returns:
        (index, comparison) of most similar lesson, or (None, None) if no match
    """
    new_text = get_lesson_text(new_lesson)
    best_match = None
    best_index = None
    best_score = 0

    for i, existing in enumerate(existing_lessons):
        comparison = compare_lessons(new_text, existing, threshold)

        if comparison['is_exact']:
            return (i, comparison)

        if comparison['is_similar']:
            # Use keyword similarity as tie-breaker
            if comparison['keyword_similarity'] > best_score:
                best_score = comparison['keyword_similarity']
                best_match = comparison
                best_index = i

    return (best_index, best_match)


def group_lessons_by_theme(lessons):
    """
    Group lessons by their primary theme.

    Args:
        lessons: List of lessons (dicts or strings)

    Returns:
        dict mapping theme -> list of (index, lesson_text)
    """
    groups = {}

    for i, lesson in enumerate(lessons):
        text = get_lesson_text(lesson)
        themes = detect_lesson_theme(text)
        primary_theme = themes[0] if themes else "other"

        if primary_theme not in groups:
            groups[primary_theme] = []
        groups[primary_theme].append((i, text))

    return groups


def identify_consolidation_candidates(lessons, threshold=0.4):
    """
    Identify pairs of lessons that could be consolidated.

    Args:
        lessons: List of lessons
        threshold: Similarity threshold

    Returns:
        List of (idx1, idx2, similarity, shared_themes) tuples
    """
    candidates = []

    for i in range(len(lessons)):
        for j in range(i + 1, len(lessons)):
            comparison = compare_lessons(lessons[i], lessons[j], threshold)
            if comparison['is_similar']:
                candidates.append((
                    i, j,
                    comparison['keyword_similarity'],
                    comparison['shared_themes']
                ))

    # Sort by similarity descending
    candidates.sort(key=lambda x: x[2], reverse=True)
    return candidates


def consolidate_lessons(state, threshold=0.4, dry_run=False):
    """
    Consolidate similar lessons in state.

    Strategy:
    - Find similar lesson pairs
    - Keep the one with higher reinforcement
    - Merge context from the other
    - Archive the merged-away lesson

    Args:
        state: The state dict
        threshold: Similarity threshold for consolidation
        dry_run: If True, return what would be consolidated without modifying

    Returns:
        dict with:
        - consolidated: list of {kept, merged, reason}
        - lessons_before: count
        - lessons_after: count
        - savings: count of lessons removed
    """
    from archive_utils import archive_decayed_lesson

    lessons = state.get('lessons', [])
    if not lessons:
        lessons = state.get('memory', [])

    if len(lessons) < 2:
        return {
            "consolidated": [],
            "lessons_before": len(lessons),
            "lessons_after": len(lessons),
            "savings": 0
        }

    # Find consolidation candidates
    candidates = identify_consolidation_candidates(lessons, threshold)

    if not candidates:
        return {
            "consolidated": [],
            "lessons_before": len(lessons),
            "lessons_after": len(lessons),
            "savings": 0
        }

    # Track which indices to remove (merged away)
    to_remove = set()
    consolidations = []

    for idx1, idx2, similarity, themes in candidates:
        # Skip if either already merged
        if idx1 in to_remove or idx2 in to_remove:
            continue

        lesson1 = lessons[idx1]
        lesson2 = lessons[idx2]

        # Get reinforcement counts
        r1 = lesson1.get('reinforced', 1) if isinstance(lesson1, dict) else 1
        r2 = lesson2.get('reinforced', 1) if isinstance(lesson2, dict) else 1

        # Keep the one with higher reinforcement
        if r1 >= r2:
            keep_idx, merge_idx = idx1, idx2
            keep_lesson, merge_lesson = lesson1, lesson2
        else:
            keep_idx, merge_idx = idx2, idx1
            keep_lesson, merge_lesson = lesson2, lesson1

        to_remove.add(merge_idx)
        consolidations.append({
            "kept_idx": keep_idx,
            "merged_idx": merge_idx,
            "kept": get_lesson_text(keep_lesson),
            "merged": get_lesson_text(merge_lesson),
            "similarity": similarity,
            "themes": themes,
            "reason": f"Similar ({similarity:.0%}) in theme {themes[0] if themes else 'unknown'}"
        })

    if dry_run:
        return {
            "consolidated": consolidations,
            "lessons_before": len(lessons),
            "lessons_after": len(lessons) - len(to_remove),
            "savings": len(to_remove),
            "dry_run": True
        }

    # Actually perform consolidation
    for c in consolidations:
        merge_idx = c['merged_idx']
        keep_idx = c['kept_idx']
        merged_lesson = lessons[merge_idx]

        # Increase reinforcement of kept lesson
        kept_lesson = lessons[keep_idx]
        if isinstance(kept_lesson, dict):
            kept_lesson['reinforced'] = kept_lesson.get('reinforced', 1) + 1
            # Add note about consolidation
            if 'consolidated_from' not in kept_lesson:
                kept_lesson['consolidated_from'] = []
            kept_lesson['consolidated_from'].append(get_lesson_text(merged_lesson))

        # Archive the merged-away lesson
        archive_decayed_lesson(
            {"lesson": get_lesson_text(merged_lesson), "reinforced": merged_lesson.get('reinforced', 1) if isinstance(merged_lesson, dict) else 1},
            f"Consolidated into similar lesson"
        )

    # Remove merged lessons (reverse order to preserve indices)
    for idx in sorted(to_remove, reverse=True):
        if 'lessons' in state:
            del state['lessons'][idx]
        elif 'memory' in state:
            del state['memory'][idx]

    return {
        "consolidated": consolidations,
        "lessons_before": len(lessons),
        "lessons_after": len(lessons) - len(to_remove),
        "savings": len(to_remove)
    }


def _extract_trigger_words(text):
    """Extract trigger words from text, filtering stopwords."""
    trigger_words = []
    for word in text.lower().split()[:3]:
        if len(word) > 3 and word not in STOPWORDS:
            trigger_words.append(word)
    return ' '.join(trigger_words) if trigger_words else None


def _extract_from_mismatches(mismatches):
    """Extract lessons from resolved mismatches."""
    suggestions = []
    resolved = [m for m in mismatches if isinstance(m, dict) and m.get('status') == 'resolved']

    for m in resolved:
        expectation = m.get('expectation', '')
        resolution = m.get('resolution', '')

        if resolution:
            trigger = _extract_trigger_words(expectation) or "similar situation"
            suggestions.append({
                "trigger": trigger,
                "lesson": resolution[:200],
                "source": f"mismatch: {expectation[:50]}",
                "confidence": "high"
            })

    return suggestions


def _extract_from_steps(plan):
    """Extract lessons from completed steps with learning indicators."""
    suggestions = []
    learning_indicators = ['learned', 'realized', 'found', 'discovered', 'issue', 'problem', 'fixed', 'solved']

    completed = [s for s in plan if isinstance(s, dict)
                 and s.get('status') == 'completed'
                 and s.get('proof')]

    for step in completed:
        proof = step.get('proof', '')
        desc = step.get('description', '')

        has_learning = any(ind in proof.lower() for ind in learning_indicators)
        if has_learning and len(proof) > 20:
            trigger = _extract_trigger_words(desc) or "similar work"
            suggestions.append({
                "trigger": trigger,
                "lesson": proof[:200],
                "source": f"step: {desc[:50]}",
                "confidence": "medium"
            })

    return suggestions


def _extract_from_constraints(constraints):
    """Extract lessons from constraints."""
    suggestions = []

    for constraint in constraints:
        if isinstance(constraint, str) and len(constraint) > 10:
            if constraint.lower().startswith("don't") or constraint.lower().startswith("do not"):
                lesson = constraint
            else:
                lesson = f"Remember: {constraint}"

            suggestions.append({
                "trigger": "planning",
                "lesson": lesson,
                "source": "constraint",
                "confidence": "medium"
            })

    return suggestions


def _deduplicate_suggestions(suggestions):
    """Remove duplicate suggestions based on lesson similarity."""
    unique = []
    for s in suggestions:
        is_dup = any(compare_lessons(s['lesson'], existing['lesson'])['is_similar']
                     for existing in unique)
        if not is_dup:
            unique.append(s)
    return unique


def extract_lessons_from_objective(state):
    """
    Analyze completed work and suggest lessons to extract.

    Sources for lessons:
    - Mismatches that were resolved (what went wrong, how it was fixed)
    - Plan steps that had to be revised (what changed approach)
    - Constraints that were added during work (what we learned to avoid)

    Returns:
        List of suggested lessons with:
        - trigger: when this applies
        - lesson: what was learned
        - source: where it came from
        - confidence: high/medium/low
    """
    mismatches = state.get('mismatches', [])
    plan = state.get('plan', [])
    constraints = state.get('constraints', [])

    suggestions = []
    suggestions.extend(_extract_from_mismatches(mismatches))
    suggestions.extend(_extract_from_steps(plan))
    suggestions.extend(_extract_from_constraints(constraints))

    return _deduplicate_suggestions(suggestions)


def format_lesson_suggestions(suggestions):
    """
    Format lesson suggestions for display.

    Returns formatted string.
    """
    if not suggestions:
        return "No lesson suggestions found."

    lines = ["Suggested lessons from this work:"]
    lines.append("")

    for i, s in enumerate(suggestions, 1):
        confidence_marker = {"high": "★", "medium": "◆", "low": "○"}.get(s.get('confidence', 'low'), '○')
        lines.append(f"{confidence_marker} Suggestion {i}:")
        lines.append(f"  Trigger: {s.get('trigger', 'unknown')}")
        lines.append(f"  Lesson: {s.get('lesson', '')}")
        lines.append(f"  Source: {s.get('source', 'unknown')}")
        lines.append("")

    lines.append("Add a lesson with: /edge-plan add-lesson \"<trigger>\" \"<lesson>\"")
    return "\n".join(lines)
