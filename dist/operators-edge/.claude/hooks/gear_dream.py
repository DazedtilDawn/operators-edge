#!/usr/bin/env python3
"""
Operator's Edge - Dream Gear (v3.7)
Reflects, consolidates, and proposes when truly idle - the "wisdom" mode.

Dream Gear is engaged when there's nothing active and patrol found nothing.
It:
- Consolidates similar lessons
- Analyzes patterns in completed work
- Generates strategic proposals for improvements
"""

from typing import Dict, Any, Optional, List, Tuple
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from gear_config import Gear, GearState, GearTransition, DREAM_LIMITS


# =============================================================================
# DREAM RESULT
# =============================================================================

@dataclass
class DreamGearResult:
    """Result of running Dream Gear."""
    reflection_completed: bool
    lessons_consolidated: int
    patterns_identified: List[str]
    proposal: Optional[Dict[str, Any]]  # Strategic proposal if generated
    insights: List[str]  # Observations from reflection
    error: Optional[str]

    def to_dict(self) -> dict:
        return {
            "reflection_completed": self.reflection_completed,
            "lessons_consolidated": self.lessons_consolidated,
            "patterns_identified": self.patterns_identified,
            "proposal": self.proposal,
            "insights": self.insights,
            "error": self.error,
        }


# =============================================================================
# LESSON CONSOLIDATION
# =============================================================================

def consolidate_lessons(state: Dict[str, Any]) -> Tuple[int, List[str]]:
    """
    Analyze lessons for consolidation opportunities.

    This identifies:
    - Similar lessons that could be merged
    - Low-value lessons that could be pruned
    - High-value lessons that should be reinforced

    Returns:
        (consolidation_count, insights)
    """
    memory = state.get("memory", [])
    insights = []
    consolidation_opportunities = 0

    if not memory:
        return 0, ["No lessons to analyze"]

    # Group lessons by trigger keywords
    trigger_groups = {}
    for lesson in memory:
        if not isinstance(lesson, dict):
            continue
        trigger = lesson.get("trigger", "").lower()
        # Extract primary keyword
        primary = trigger.split()[0] if trigger else "general"
        if primary not in trigger_groups:
            trigger_groups[primary] = []
        trigger_groups[primary].append(lesson)

    # Find consolidation opportunities
    for trigger, group in trigger_groups.items():
        if len(group) > 1:
            consolidation_opportunities += len(group) - 1
            insights.append(f"'{trigger}' has {len(group)} related lessons - could consolidate")

    # Find low-value lessons (reinforced=1, old)
    low_value = [
        l for l in memory
        if isinstance(l, dict) and l.get("reinforced", 1) <= 1
    ]
    if low_value:
        insights.append(f"{len(low_value)} lessons with low reinforcement (≤1)")

    # Find high-value lessons
    high_value = [
        l for l in memory
        if isinstance(l, dict) and l.get("reinforced", 0) >= 3
    ]
    if high_value:
        triggers = [l.get("trigger", "unknown")[:20] for l in high_value[:3]]
        insights.append(f"High-value lessons (≥3 reinforcements): {', '.join(triggers)}")

    # Audit pattern coverage
    auditable = [l for l in memory if isinstance(l, dict) and l.get("audit_pattern")]
    if auditable:
        insights.append(f"{len(auditable)}/{len(memory)} lessons have audit patterns")
    else:
        insights.append("No lessons have audit patterns - consider adding some")

    return consolidation_opportunities, insights


# =============================================================================
# PATTERN ANALYSIS
# =============================================================================

def analyze_work_patterns(state: Dict[str, Any]) -> List[str]:
    """
    Analyze patterns in completed work.

    Looks at:
    - Archive for recurring themes
    - Completed objectives for patterns
    - Common issues that keep arising

    Returns:
        List of identified patterns
    """
    patterns = []

    # Analyze self_score history if available
    self_score = state.get("self_score", {})
    if self_score:
        checks = self_score.get("checks", {})
        # Find weak areas
        for check, data in checks.items():
            if isinstance(data, dict) and not data.get("met", True):
                patterns.append(f"Recurring weakness: {check}")

    # Analyze memory for theme clusters
    memory = state.get("memory", [])
    themes = {}
    for lesson in memory:
        if not isinstance(lesson, dict):
            continue
        trigger = lesson.get("trigger", "").lower()
        # Count trigger word frequency
        for word in trigger.split():
            if len(word) > 3:  # Skip short words
                themes[word] = themes.get(word, 0) + 1

    # Find dominant themes
    top_themes = sorted(themes.items(), key=lambda x: x[1], reverse=True)[:3]
    if top_themes:
        pattern_str = ", ".join(f"{t[0]} ({t[1]}x)" for t in top_themes)
        patterns.append(f"Dominant themes: {pattern_str}")

    # Check for growth indicators
    if len(memory) > 15:
        patterns.append(f"Memory is growing ({len(memory)} lessons) - consider pruning")
    elif len(memory) < 5:
        patterns.append("Memory is sparse - capture more lessons")

    return patterns


# =============================================================================
# PROPOSAL GENERATION
# =============================================================================

def generate_proposal(
    state: Dict[str, Any],
    gear_state: GearState
) -> Optional[Dict[str, Any]]:
    """
    Generate a strategic improvement proposal.

    Only generates if:
    - Haven't hit proposal limit
    - Have enough data to propose meaningfully

    Returns:
        Proposal dict or None
    """
    # Check rate limit
    if not gear_state or gear_state.dream_proposals_count >= DREAM_LIMITS["max_proposals_per_session"]:
        return None

    memory = state.get("memory", [])
    patterns = analyze_work_patterns(state)

    # Generate proposal based on state analysis
    proposal = None

    # Proposal 1: Lesson consolidation
    _, insights = consolidate_lessons(state)
    consolidation_insights = [i for i in insights if "consolidate" in i.lower()]
    if consolidation_insights:
        proposal = {
            "type": "consolidation",
            "title": "Consolidate related lessons",
            "description": consolidation_insights[0],
            "priority": "low",
            "effort": "small",
        }

    # Proposal 2: Add audit patterns
    auditable_count = sum(
        1 for l in memory
        if isinstance(l, dict) and l.get("audit_pattern")
    )
    if auditable_count < len(memory) * 0.3 and len(memory) > 5:
        proposal = {
            "type": "enhancement",
            "title": "Add audit patterns to more lessons",
            "description": f"Only {auditable_count}/{len(memory)} lessons have audit patterns",
            "priority": "medium",
            "effort": "medium",
        }

    # Proposal 3: Based on weak areas
    weak_patterns = [p for p in patterns if "weakness" in p.lower()]
    if weak_patterns:
        proposal = {
            "type": "improvement",
            "title": "Address recurring weakness",
            "description": weak_patterns[0],
            "priority": "medium",
            "effort": "medium",
        }

    return proposal


# =============================================================================
# DREAM GEAR EXECUTION
# =============================================================================

def run_dream_gear(
    state: Dict[str, Any],
    gear_state: GearState,
) -> DreamGearResult:
    """
    Run Dream Gear - reflect and propose.

    This is the contemplative mode that:
    1. Consolidates lessons
    2. Analyzes patterns
    3. Generates strategic proposals

    Args:
        state: The active_context state
        gear_state: Current gear state tracking

    Returns:
        DreamGearResult with reflection summary
    """
    try:
        # Run consolidation analysis
        consolidation_count, consolidation_insights = consolidate_lessons(state)

        # Analyze patterns
        patterns = analyze_work_patterns(state)

        # Generate proposal (if allowed)
        proposal = generate_proposal(state, gear_state)

        # Combine insights
        all_insights = consolidation_insights + patterns

        return DreamGearResult(
            reflection_completed=True,
            lessons_consolidated=consolidation_count,
            patterns_identified=patterns,
            proposal=proposal,
            insights=all_insights,
            error=None,
        )

    except Exception as e:
        return DreamGearResult(
            reflection_completed=False,
            lessons_consolidated=0,
            patterns_identified=[],
            proposal=None,
            insights=[],
            error=str(e),
        )


# =============================================================================
# TRANSITION DETECTION
# =============================================================================

def should_transition_from_dream(
    result: DreamGearResult,
    gear_state: GearState
) -> Tuple[bool, Optional[GearTransition]]:
    """
    Check if Dream Gear should transition to another gear.

    Returns:
        (should_transition, transition_type)
    """
    # Do not transition on reflection errors
    if result.error or not result.reflection_completed:
        return False, None

    # If proposal generated and needs action -> wait for user
    if result.proposal:
        # Stay in Dream until user acts on proposal
        return False, None

    # After reflection, go back to Patrol to check again
    return True, GearTransition.DREAM_TO_PATROL


# =============================================================================
# DISPLAY HELPERS
# =============================================================================

def format_dream_status(result: DreamGearResult) -> str:
    """Format Dream Gear results for display."""
    lines = [
        f"💭 DREAM GEAR",
        f"   Reflection: {'Complete' if result.reflection_completed else 'Failed'}",
    ]

    if result.lessons_consolidated > 0:
        lines.append(f"   Consolidation opportunities: {result.lessons_consolidated}")

    if result.patterns_identified:
        lines.append("")
        lines.append("   Patterns identified:")
        for pattern in result.patterns_identified[:3]:
            lines.append(f"   • {pattern}")

    if result.insights:
        lines.append("")
        lines.append("   Insights:")
        for insight in result.insights[:3]:
            lines.append(f"   • {insight[:60]}{'...' if len(insight) > 60 else ''}")

    if result.proposal:
        lines.append("")
        lines.append("   PROPOSAL:")
        lines.append(f"   Title: {result.proposal['title']}")
        lines.append(f"   Type: {result.proposal['type']} | Priority: {result.proposal['priority']}")
        lines.append(f"   {result.proposal['description']}")

    if result.error:
        lines.append(f"   Error: {result.error}")

    return "\n".join(lines)


def format_proposal(proposal: Dict[str, Any]) -> str:
    """Format a proposal for user review."""
    if not proposal:
        return "No proposal generated."

    lines = [
        "═" * 50,
        "💭 DREAM PROPOSAL",
        "═" * 50,
        "",
        f"Title: {proposal['title']}",
        f"Type: {proposal['type']}",
        f"Priority: {proposal['priority']}",
        f"Effort: {proposal['effort']}",
        "",
        f"Description: {proposal['description']}",
        "",
        "Options:",
        "  /edge approve  - Accept and start this objective",
        "  /edge skip     - Dismiss proposal",
        "  /edge stop     - Stop autonomous mode",
        "═" * 50,
    ]

    return "\n".join(lines)
