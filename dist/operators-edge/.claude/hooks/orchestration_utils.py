#!/usr/bin/env python3
"""
Operator's Edge - Orchestration Utilities
Session context detection, memory management, and orchestrator suggestions.

FACADE MODULE: Re-exports from specialized modules for backward compatibility.
Actual implementation is in:
- context_utils.py: State detection, orchestrator suggestions
- memory_utils.py: Memory surfacing, reinforcement, retrieval
- lesson_utils.py: Similarity, deduplication, consolidation
- reflection_utils.py: Score patterns, improvement suggestions
"""

# =============================================================================
# CONTEXT UTILITIES - State detection and orchestrator suggestions
# =============================================================================
from context_utils import (
    detect_session_context,
    get_orchestrator_suggestion,
)

# =============================================================================
# MEMORY UTILITIES - Surfacing, decay, and retrieval
# =============================================================================
from memory_utils import (
    surface_relevant_memory,
    reinforce_memory,
    add_memory_item,
    retrieve_from_archive,
    resurrect_archived_lesson,
    get_memory_summary,
)

# =============================================================================
# LESSON UTILITIES - Similarity, deduplication, consolidation
# =============================================================================
from lesson_utils import (
    # Constants
    LESSON_THEMES,
    STOPWORDS,
    # Functions
    get_lesson_text,
    get_lesson_keywords,
    detect_lesson_theme,
    compare_lessons,
    find_similar_lesson,
    group_lessons_by_theme,
    identify_consolidation_candidates,
    consolidate_lessons,
    extract_lessons_from_objective,
    format_lesson_suggestions,
)

# =============================================================================
# REFLECTION UTILITIES - Score patterns, improvement suggestions
# =============================================================================
from reflection_utils import (
    # Constants
    ADAPTATION_CHECKS,
    CHECK_IMPROVEMENTS,
    # Functions
    analyze_score_patterns,
    get_recurring_failures,
    get_improvement_suggestion,
    generate_reflection_summary,
    generate_improvement_challenges,
)

# =============================================================================
# ALL EXPORTS (for `from orchestration_utils import *`)
# =============================================================================
__all__ = [
    # Context
    'detect_session_context',
    'get_orchestrator_suggestion',
    # Memory
    'surface_relevant_memory',
    'reinforce_memory',
    'add_memory_item',
    'retrieve_from_archive',
    'resurrect_archived_lesson',
    'get_memory_summary',
    # Lesson
    'LESSON_THEMES',
    'STOPWORDS',
    'get_lesson_text',
    'get_lesson_keywords',
    'detect_lesson_theme',
    'compare_lessons',
    'find_similar_lesson',
    'group_lessons_by_theme',
    'identify_consolidation_candidates',
    'consolidate_lessons',
    'extract_lessons_from_objective',
    'format_lesson_suggestions',
    # Reflection
    'ADAPTATION_CHECKS',
    'CHECK_IMPROVEMENTS',
    'analyze_score_patterns',
    'get_recurring_failures',
    'get_improvement_suggestion',
    'generate_reflection_summary',
    'generate_improvement_challenges',
]
