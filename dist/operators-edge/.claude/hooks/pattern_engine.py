#!/usr/bin/env python3
"""
Operator's Edge v6.0 - Pattern Engine
The Generative Layer: Extract and surface patterns at decision points.

Pattern Types:
1. LESSON - Learned patterns from memory (existing)
2. COCHANGE - Files that changed together historically
3. RISK - Patterns that led to failures/blocks
4. RHYTHM - Time-based patterns (when things succeed/fail)

Design Philosophy:
- Patterns are SURFACED, not enforced
- Proactive guidance, not reactive blocking
- "Here's what I've seen before" not "Don't do this"
"""
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple
import json
import os
import re
import subprocess
from pathlib import Path


class PatternType(Enum):
    """Types of patterns we extract and surface."""
    LESSON = "lesson"       # From memory/lessons in state
    COCHANGE = "cochange"   # Files that change together (git)
    RISK = "risk"           # Patterns that led to failures
    RHYTHM = "rhythm"       # Time-based success/failure patterns


@dataclass
class Pattern:
    """A surfaced pattern with context."""
    type: PatternType
    trigger: str            # What triggered surfacing
    content: str            # The pattern content
    relevance: float        # 0-1 relevance score
    source: str             # Where it came from
    confidence: str = "medium"  # high/medium/low
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "type": self.type.value,
            "trigger": self.trigger,
            "content": self.content,
            "relevance": self.relevance,
            "source": self.source,
            "confidence": self.confidence,
            "metadata": self.metadata,
        }


@dataclass
class PatternBundle:
    """Collection of patterns for a decision point."""
    context: str                    # What we're deciding
    patterns: List[Pattern]         # Relevant patterns
    total_found: int               # Before filtering
    intent_action: str             # The intent we're surfacing for
    surfaced_at: str = field(default_factory=lambda: datetime.now().isoformat())

    def to_dict(self) -> Dict[str, Any]:
        return {
            "context": self.context,
            "patterns": [p.to_dict() for p in self.patterns],
            "total_found": self.total_found,
            "intent_action": self.intent_action,
            "surfaced_at": self.surfaced_at,
        }

    def format_guidance(self) -> str:
        """Format patterns as readable guidance."""
        if not self.patterns:
            return ""

        lines = ["### 📖 Patterns for this decision"]
        lines.append("")

        # Group by type
        by_type: Dict[PatternType, List[Pattern]] = {}
        for p in self.patterns:
            if p.type not in by_type:
                by_type[p.type] = []
            by_type[p.type].append(p)

        # Format each group
        for ptype, patterns in by_type.items():
            icon = _pattern_icon(ptype)
            lines.append(f"**{icon} {ptype.value.title()}**")
            for p in patterns[:2]:  # Max 2 per type
                confidence_marker = {"high": "★", "medium": "◆", "low": "○"}.get(p.confidence, "○")
                lines.append(f"  {confidence_marker} {p.content[:120]}")
            lines.append("")

        return "\n".join(lines)


def _pattern_icon(ptype: PatternType) -> str:
    """Get icon for pattern type."""
    return {
        PatternType.LESSON: "📚",
        PatternType.COCHANGE: "🔗",
        PatternType.RISK: "⚠️",
        PatternType.RHYTHM: "🕐",
    }.get(ptype, "•")


# =============================================================================
# PATTERN EXTRACTION
# =============================================================================

# =============================================================================
# GRADUATION LIFECYCLE
# =============================================================================

# Thresholds for lesson lifecycle
GRADUATION_THRESHOLD = 10  # Stop surfacing after this many reinforcements
ESTABLISHED_THRESHOLD = 5  # Only surface high-confidence matches


def should_surface_lesson(lesson: Dict[str, Any], match_score: float = 0.5) -> bool:
    """
    Determine if a lesson should be surfaced based on graduation lifecycle.

    Lifecycle:
    - NEW (0-4 reinforcements): Always surface when relevant
    - ESTABLISHED (5-9): Only surface if high-confidence match (>0.7)
    - GRADUATED (10+): Don't surface - user has internalized this
    - EVERGREEN: Always surface regardless of reinforcement
    """
    reinforced = lesson.get("reinforced", 0)

    # Evergreen lessons always surface
    if lesson.get("evergreen", False):
        return True

    # Graduated - don't surface
    if reinforced >= GRADUATION_THRESHOLD:
        return False

    # Established - only high-confidence matches
    if reinforced >= ESTABLISHED_THRESHOLD:
        return match_score >= 0.7

    # New - always surface when relevant
    return True


def get_lesson_lifecycle_stage(lesson: Dict[str, Any]) -> str:
    """Get the lifecycle stage of a lesson."""
    if lesson.get("evergreen", False):
        return "evergreen"
    reinforced = lesson.get("reinforced", 0)
    if reinforced >= GRADUATION_THRESHOLD:
        return "graduated"
    if reinforced >= ESTABLISHED_THRESHOLD:
        return "established"
    return "new"


def extract_lesson_patterns(state: Dict[str, Any], context: str) -> List[Pattern]:
    """
    Extract relevant lessons from memory.
    Uses existing surface_relevant_memory but wraps in Pattern objects.
    Respects graduation lifecycle - highly reinforced lessons are not surfaced.
    """
    from memory_utils import surface_relevant_memory

    relevant = surface_relevant_memory(state, context)
    patterns = []

    for r in relevant:
        reinforced = r.get("reinforced", 0)
        match_score = r.get("match_score", 0.5)

        # Check graduation lifecycle
        if not should_surface_lesson(r, match_score):
            continue

        confidence = "high" if reinforced >= 3 else "medium" if reinforced >= 1 else "low"

        patterns.append(Pattern(
            type=PatternType.LESSON,
            trigger=r.get("trigger", ""),
            content=r.get("lesson", ""),
            relevance=match_score,
            source="memory",
            confidence=confidence,
            metadata={"reinforced": reinforced, "lifecycle": get_lesson_lifecycle_stage(r)}
        ))

    return patterns


def extract_cochange_patterns(context: str, project_dir: Optional[Path] = None) -> List[Pattern]:
    """
    Extract co-change patterns from git history.

    Find files that frequently change together - if editing file A,
    suggest that file B often changes with it.
    """
    if project_dir is None:
        project_dir = Path.cwd()

    # Try to extract file paths from context
    file_pattern = r'[a-zA-Z0-9_\-./]+\.(py|js|ts|tsx|jsx|yaml|yml|json|md)'
    files_mentioned = re.findall(file_pattern, context)

    if not files_mentioned:
        return []

    patterns = []

    for file_ref in files_mentioned[:3]:  # Limit to 3 files
        cochanged = _find_cochanged_files(file_ref, project_dir)
        for cofile, count in cochanged[:2]:  # Top 2 co-changed
            confidence = "high" if count >= 5 else "medium" if count >= 2 else "low"
            patterns.append(Pattern(
                type=PatternType.COCHANGE,
                trigger=file_ref,
                content=f"When changing `{file_ref}`, also check `{cofile}` (changed together {count} times)",
                relevance=min(count / 10, 1.0),
                source="git_history",
                confidence=confidence,
                metadata={"cochanged_file": cofile, "change_count": count}
            ))

    return patterns


def _find_cochanged_files(file_path: str, project_dir: Path, limit: int = 5) -> List[Tuple[str, int]]:
    """
    Find files that frequently change with the given file.
    Uses git log to find commits that touched this file, then counts other files.
    """
    try:
        # Get commits that touched this file
        result = subprocess.run(
            ["git", "log", "--pretty=format:%H", "-n", "50", "--", file_path],
            cwd=project_dir,
            capture_output=True,
            text=True,
            timeout=5
        )
        if result.returncode != 0:
            return []

        commits = result.stdout.strip().split("\n")
        if not commits or not commits[0]:
            return []

        # Count co-changed files
        cochange_counts: Dict[str, int] = {}
        for commit_hash in commits[:30]:  # Limit commits
            files_result = subprocess.run(
                ["git", "show", "--name-only", "--pretty=format:", commit_hash],
                cwd=project_dir,
                capture_output=True,
                text=True,
                timeout=5
            )
            if files_result.returncode != 0:
                continue

            for f in files_result.stdout.strip().split("\n"):
                f = f.strip()
                if f and f != file_path and not f.startswith("."):
                    cochange_counts[f] = cochange_counts.get(f, 0) + 1

        # Sort by count and return top N
        sorted_files = sorted(cochange_counts.items(), key=lambda x: x[1], reverse=True)
        return sorted_files[:limit]

    except (subprocess.TimeoutExpired, FileNotFoundError):
        return []


def extract_risk_patterns(state: Dict[str, Any], context: str) -> List[Pattern]:
    """
    Extract risk patterns from past failures.

    Sources:
    - Resolved mismatches (what went wrong before)
    - Blocked steps (what caused blocks)
    - Risk items with triggered status
    """
    patterns = []

    # From mismatches
    mismatches = state.get("mismatches", [])
    for m in mismatches:
        if not isinstance(m, dict):
            continue

        expectation = m.get("expectation", "").lower()
        resolution = m.get("resolution", "")

        # Check if context relates to this mismatch
        context_lower = context.lower()
        if any(word in context_lower for word in expectation.split()[:3]):
            patterns.append(Pattern(
                type=PatternType.RISK,
                trigger=m.get("expectation", "")[:50],
                content=f"Past issue: {resolution}" if resolution else f"Watch out: {expectation}",
                relevance=0.7,
                source="mismatch_history",
                confidence="high" if m.get("status") == "resolved" else "medium",
                metadata={"mismatch_id": m.get("id", "unknown")}
            ))

    # From risks list
    risks = state.get("risks", [])
    for r in risks:
        if not isinstance(r, dict):
            continue

        risk_text = r.get("risk", "").lower()
        context_lower = context.lower()

        # Check relevance
        risk_words = set(risk_text.split())
        context_words = set(context_lower.split())
        overlap = len(risk_words & context_words)

        if overlap >= 2:
            patterns.append(Pattern(
                type=PatternType.RISK,
                trigger=r.get("risk", "")[:50],
                content=f"Risk: {r.get('risk', '')} | Mitigation: {r.get('mitigation', 'none')}",
                relevance=overlap / max(len(risk_words), 1),
                source="risk_register",
                confidence="medium",
                metadata={"status": r.get("status", "active")}
            ))

    return patterns


def extract_rhythm_patterns(state: Dict[str, Any], context: str) -> List[Pattern]:
    """
    Extract time-based patterns.

    Examples:
    - "Commits after 10pm have 2x failure rate"
    - "Friday deploys tend to cause weekend alerts"
    - "Step completion slows after 5+ steps in session"
    """
    patterns = []

    # Check current time patterns
    now = datetime.now()
    hour = now.hour
    weekday = now.weekday()

    # Late night warning
    if hour >= 22 or hour <= 5:
        patterns.append(Pattern(
            type=PatternType.RHYTHM,
            trigger="late_night",
            content="Late night work - consider extra verification or saving for tomorrow",
            relevance=0.5,
            source="time_analysis",
            confidence="low",
            metadata={"hour": hour}
        ))

    # Friday deployment warning
    if weekday == 4 and any(word in context.lower() for word in ["deploy", "release", "push"]):
        patterns.append(Pattern(
            type=PatternType.RHYTHM,
            trigger="friday_deploy",
            content="Friday deployment detected - ensure rollback plan is ready",
            relevance=0.6,
            source="time_analysis",
            confidence="medium",
            metadata={"weekday": "friday"}
        ))

    # Session length patterns
    plan = state.get("plan", [])
    completed_count = len([s for s in plan if isinstance(s, dict) and s.get("status") == "completed"])

    if completed_count >= 5:
        patterns.append(Pattern(
            type=PatternType.RHYTHM,
            trigger="long_session",
            content=f"Session has {completed_count} completed steps - consider /edge --verify before continuing",
            relevance=0.4,
            source="session_analysis",
            confidence="low",
            metadata={"completed_steps": completed_count}
        ))

    return patterns


# =============================================================================
# MAIN PATTERN SURFACING
# =============================================================================

def surface_patterns(
    state: Dict[str, Any],
    context: str,
    intent_action: str,
    project_dir: Optional[Path] = None,
    max_patterns: int = 5
) -> PatternBundle:
    """
    Main entry point: Surface all relevant patterns for a decision point.

    Args:
        state: Current active_context state
        context: Text describing current context (step, objective, etc.)
        intent_action: The intent action we're surfacing for
        project_dir: Project directory for git operations
        max_patterns: Maximum patterns to return

    Returns:
        PatternBundle with relevant patterns
    """
    all_patterns: List[Pattern] = []

    # Extract from each source
    all_patterns.extend(extract_lesson_patterns(state, context))
    all_patterns.extend(extract_cochange_patterns(context, project_dir))
    all_patterns.extend(extract_risk_patterns(state, context))
    all_patterns.extend(extract_rhythm_patterns(state, context))

    # Sort by relevance
    all_patterns.sort(key=lambda p: p.relevance, reverse=True)

    # Ensure diversity - max 2 per type
    diverse_patterns: List[Pattern] = []
    type_counts: Dict[PatternType, int] = {}

    for p in all_patterns:
        count = type_counts.get(p.type, 0)
        if count < 2:
            diverse_patterns.append(p)
            type_counts[p.type] = count + 1

        if len(diverse_patterns) >= max_patterns:
            break

    return PatternBundle(
        context=context[:100],
        patterns=diverse_patterns,
        total_found=len(all_patterns),
        intent_action=intent_action
    )


def format_pattern_guidance(bundle: PatternBundle) -> str:
    """Format pattern bundle as guidance text."""
    return bundle.format_guidance()


# =============================================================================
# PATTERN LEARNING (for future)
# =============================================================================

def record_pattern_outcome(pattern: Pattern, was_useful: bool, state: Dict[str, Any]) -> None:
    """
    Record whether a surfaced pattern was useful.
    This feeds the learning loop (Phase 3).
    """
    # For now, just reinforce lessons if useful
    if pattern.type == PatternType.LESSON and was_useful:
        from memory_utils import reinforce_memory
        reinforce_memory(state, pattern.trigger)


# =============================================================================
# TESTING / DEBUG
# =============================================================================

if __name__ == "__main__":
    # Simple test
    test_state = {
        "objective": "Add dark mode toggle",
        "plan": [
            {"description": "Update ThemeContext.tsx", "status": "in_progress"},
            {"description": "Add CSS variables", "status": "pending"},
        ],
        "memory": [
            {"trigger": "theme css", "lesson": "Use CSS variables for theme switching", "reinforced": 3},
            {"trigger": "context react", "lesson": "Wrap provider at app root", "reinforced": 2},
        ],
        "risks": [
            {"risk": "CSS variable browser support", "mitigation": "Check caniuse.com"}
        ]
    }

    bundle = surface_patterns(
        test_state,
        "Update ThemeContext.tsx for dark mode",
        "ready_to_execute"
    )

    print(f"Found {bundle.total_found} patterns, surfacing {len(bundle.patterns)}")
    print()
    print(bundle.format_guidance())
