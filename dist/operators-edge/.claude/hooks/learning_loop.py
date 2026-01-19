#!/usr/bin/env python3
"""
Operator's Edge v6.0 - Learning Loop
Phase 3: Close the feedback cycle by tracking pattern effectiveness.

The Loop:
1. SURFACE - Show patterns before action (pattern_engine.py)
2. ACT - User works on the step
3. EVALUATE - Check if step succeeded or failed
4. LEARN - Reinforce helpful patterns, decay unhelpful ones

Key Insight:
- We don't ask "was this pattern helpful?" (annoying)
- Instead, we infer from OUTCOMES:
  - Step succeeded → patterns shown were probably helpful
  - Step failed/blocked → patterns might have been ignored or unhelpful
"""
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple
import json
from pathlib import Path

from pattern_engine import Pattern, PatternBundle, PatternType


@dataclass
class PatternOutcome:
    """Records the outcome of a surfaced pattern."""
    pattern_type: str
    pattern_trigger: str
    pattern_content: str
    surfaced_at: str
    intent_action: str
    step_description: str
    outcome: str  # "success", "failure", "blocked", "skipped"
    evaluated_at: str = field(default_factory=lambda: datetime.now().isoformat())
    reinforcement_applied: int = 0  # +1, -1, or 0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "pattern_type": self.pattern_type,
            "pattern_trigger": self.pattern_trigger,
            "pattern_content": self.pattern_content[:100],
            "surfaced_at": self.surfaced_at,
            "intent_action": self.intent_action,
            "step_description": self.step_description[:100],
            "outcome": self.outcome,
            "evaluated_at": self.evaluated_at,
            "reinforcement_applied": self.reinforcement_applied,
        }


# =============================================================================
# TRACKING - Remember what patterns were surfaced
# =============================================================================

_active_pattern_bundles: Dict[str, PatternBundle] = {}


def track_surfaced_patterns(bundle: PatternBundle, step_key: str) -> None:
    """
    Remember what patterns were shown for a step.
    Called after surface_patterns() in gear_engine.
    """
    if bundle.patterns:
        _active_pattern_bundles[step_key] = bundle


def get_tracked_patterns(step_key: str) -> Optional[PatternBundle]:
    """Get patterns that were surfaced for a step."""
    return _active_pattern_bundles.get(step_key)


def clear_tracked_patterns(step_key: str) -> None:
    """Clear tracked patterns after evaluation."""
    _active_pattern_bundles.pop(step_key, None)


def make_step_key(objective: str, step_index: int) -> str:
    """Create a unique key for tracking patterns per step."""
    return f"{objective[:50]}:step{step_index}"


# =============================================================================
# EVALUATION - Determine outcomes from step status
# =============================================================================

def evaluate_step_outcome(
    state: Dict[str, Any],
    step_index: int,
    previous_status: str,
    current_status: str
) -> str:
    """
    Determine the outcome of a step based on status transition.

    Returns: "success", "failure", "blocked", "skipped", or "in_progress"
    """
    if current_status == "completed" and previous_status in ("pending", "in_progress"):
        return "success"
    elif current_status == "blocked":
        return "blocked"
    elif current_status == "failed":
        return "failure"
    elif current_status == "skipped":
        return "skipped"
    else:
        return "in_progress"


def infer_pattern_helpfulness(outcome: str) -> int:
    """
    Infer if patterns were helpful based on step outcome.

    Returns: +1 (helpful), -1 (unhelpful), 0 (neutral/unknown)
    """
    if outcome == "success":
        # Step succeeded - patterns shown were probably relevant
        return 1
    elif outcome in ("blocked", "failure"):
        # Step failed - patterns might have been ignored or weren't enough
        # We don't penalize hard, but we don't reinforce either
        return 0
    elif outcome == "skipped":
        # Step skipped - user chose different approach
        # Slight negative signal
        return -1
    else:
        return 0


# =============================================================================
# REINFORCEMENT - Update pattern strength based on outcomes
# =============================================================================

def reinforce_lesson_pattern(state: Dict[str, Any], trigger: str, delta: int) -> bool:
    """
    Adjust reinforcement count for a lesson pattern.

    Args:
        state: The state dict containing memory
        trigger: The lesson trigger to find
        delta: Amount to adjust (+1, -1, etc.)

    Returns: True if pattern was found and updated
    """
    memory = state.get("memory", [])
    today = datetime.now().strftime("%Y-%m-%d")

    for m in memory:
        if isinstance(m, dict) and m.get("trigger", "").lower() == trigger.lower():
            current = m.get("reinforced", 0)
            m["reinforced"] = max(0, current + delta)  # Never go below 0
            m["last_used"] = today
            return True

    return False


def reinforce_risk_pattern(state: Dict[str, Any], risk_text: str, was_helpful: bool) -> bool:
    """
    Track risk pattern effectiveness.
    Risks don't have reinforcement counts, but we can track if they helped.
    """
    risks = state.get("risks", [])
    today = datetime.now().strftime("%Y-%m-%d")

    for r in risks:
        if isinstance(r, dict) and risk_text.lower() in r.get("risk", "").lower():
            if was_helpful:
                r["times_helped"] = r.get("times_helped", 0) + 1
            r["last_surfaced"] = today
            return True

    return False


def apply_pattern_reinforcement(
    state: Dict[str, Any],
    pattern: Pattern,
    delta: int
) -> bool:
    """
    Apply reinforcement to a pattern based on its type.

    Returns: True if reinforcement was applied
    """
    if delta == 0:
        return False

    if pattern.type == PatternType.LESSON:
        return reinforce_lesson_pattern(state, pattern.trigger, delta)
    elif pattern.type == PatternType.RISK:
        return reinforce_risk_pattern(state, pattern.trigger, delta > 0)
    else:
        # COCHANGE and RHYTHM patterns don't have persistent state (yet)
        return False


# =============================================================================
# DECAY - Reduce strength of unused patterns
# =============================================================================

def decay_stale_patterns(state: Dict[str, Any], days_threshold: int = 14) -> List[Dict]:
    """
    Decay patterns that haven't been used recently.

    Returns: List of decayed pattern info
    """
    from datetime import datetime, timedelta

    memory = state.get("memory", [])
    cutoff = (datetime.now() - timedelta(days=days_threshold)).strftime("%Y-%m-%d")
    decayed = []

    for m in memory:
        if not isinstance(m, dict):
            continue

        last_used = m.get("last_used", "")
        reinforced = m.get("reinforced", 0)

        # Decay if old and weakly reinforced
        if last_used and last_used < cutoff and reinforced <= 1:
            m["reinforced"] = max(0, reinforced - 1)
            decayed.append({
                "trigger": m.get("trigger"),
                "old_reinforced": reinforced,
                "new_reinforced": m["reinforced"],
                "reason": f"Not used since {last_used}"
            })

    return decayed


# =============================================================================
# MAIN LEARNING LOOP
# =============================================================================

def process_step_completion(
    state: Dict[str, Any],
    objective: str,
    step_index: int,
    previous_status: str,
    current_status: str
) -> Dict[str, Any]:
    """
    Main entry point: Process a step completion and learn from it.

    Called when a step status changes (e.g., pending → completed).

    Returns: Learning result with outcomes and reinforcements
    """
    step_key = make_step_key(objective, step_index)
    bundle = get_tracked_patterns(step_key)

    result = {
        "step_key": step_key,
        "outcome": "unknown",
        "patterns_evaluated": 0,
        "reinforcements_applied": [],
        "outcomes": [],
    }

    # Determine outcome
    outcome = evaluate_step_outcome(state, step_index, previous_status, current_status)
    result["outcome"] = outcome

    if not bundle or not bundle.patterns:
        return result

    # Evaluate each pattern
    helpfulness = infer_pattern_helpfulness(outcome)
    step_desc = ""
    plan = state.get("plan", [])
    if step_index < len(plan) and isinstance(plan[step_index], dict):
        step_desc = plan[step_index].get("description", "")

    for pattern in bundle.patterns:
        # Record outcome
        pattern_outcome = PatternOutcome(
            pattern_type=pattern.type.value,
            pattern_trigger=pattern.trigger,
            pattern_content=pattern.content,
            surfaced_at=bundle.surfaced_at,
            intent_action=bundle.intent_action,
            step_description=step_desc,
            outcome=outcome,
            reinforcement_applied=helpfulness
        )
        result["outcomes"].append(pattern_outcome.to_dict())

        # Apply reinforcement
        if helpfulness != 0:
            applied = apply_pattern_reinforcement(state, pattern, helpfulness)
            if applied:
                result["reinforcements_applied"].append({
                    "type": pattern.type.value,
                    "trigger": pattern.trigger,
                    "delta": helpfulness
                })

    result["patterns_evaluated"] = len(bundle.patterns)

    # Clean up tracking
    clear_tracked_patterns(step_key)

    return result


def run_periodic_decay(state: Dict[str, Any]) -> Dict[str, Any]:
    """
    Run periodic decay on stale patterns.
    Called during prune or at session end.
    """
    decayed = decay_stale_patterns(state)

    return {
        "patterns_decayed": len(decayed),
        "details": decayed
    }


# =============================================================================
# ANALYTICS - Understand pattern effectiveness over time
# =============================================================================

def get_pattern_stats(state: Dict[str, Any]) -> Dict[str, Any]:
    """
    Get statistics about pattern effectiveness.
    """
    memory = state.get("memory", [])
    risks = state.get("risks", [])

    lesson_stats = {
        "total": len([m for m in memory if isinstance(m, dict)]),
        "high_value": len([m for m in memory if isinstance(m, dict) and m.get("reinforced", 0) >= 3]),
        "medium_value": len([m for m in memory if isinstance(m, dict) and 1 <= m.get("reinforced", 0) < 3]),
        "at_risk": len([m for m in memory if isinstance(m, dict) and m.get("reinforced", 0) == 0]),
    }

    risk_stats = {
        "total": len([r for r in risks if isinstance(r, dict)]),
        "helpful": len([r for r in risks if isinstance(r, dict) and r.get("times_helped", 0) > 0]),
    }

    return {
        "lessons": lesson_stats,
        "risks": risk_stats,
        "health": _calculate_pattern_health(lesson_stats)
    }


def _calculate_pattern_health(lesson_stats: Dict) -> str:
    """Calculate overall pattern health."""
    total = lesson_stats["total"]
    if total == 0:
        return "empty"

    high_ratio = lesson_stats["high_value"] / total
    at_risk_ratio = lesson_stats["at_risk"] / total

    if high_ratio >= 0.3 and at_risk_ratio < 0.3:
        return "healthy"
    elif at_risk_ratio >= 0.5:
        return "stale"
    else:
        return "growing"


def format_pattern_stats(stats: Dict[str, Any]) -> str:
    """Format pattern stats for display."""
    lessons = stats["lessons"]
    risks = stats["risks"]
    health = stats["health"]

    health_emoji = {
        "healthy": "🟢",
        "growing": "🟡",
        "stale": "🟠",
        "empty": "⚪"
    }.get(health, "⚪")

    lines = [
        "### 📊 Pattern Health",
        "",
        f"**Status**: {health_emoji} {health.title()}",
        "",
        f"**Lessons**: {lessons['total']} total",
        f"  - ★★★ High value: {lessons['high_value']}",
        f"  - ★★ Medium: {lessons['medium_value']}",
        f"  - ⚠️ At risk of decay: {lessons['at_risk']}",
        "",
        f"**Risks**: {risks['total']} tracked, {risks['helpful']} proven helpful",
    ]

    return "\n".join(lines)


# =============================================================================
# TOOL-LEVEL LEARNING (v6.0 Decision-Time Feedback)
# =============================================================================

# Track patterns surfaced per file for tool-level feedback
_file_pattern_tracking: Dict[str, Dict[str, Any]] = {}


def track_file_patterns(file_path: str, patterns: List[Pattern]) -> None:
    """
    Track which patterns were surfaced when about to modify a file.
    Called by pre_tool.py before Write/Edit.
    """
    if not patterns:
        return

    _file_pattern_tracking[file_path] = {
        "patterns": patterns,
        "surfaced_at": datetime.now().isoformat(),
    }


def track_tool_outcome(
    state: Dict[str, Any],
    tool_name: str,
    file_path: str,
    success: bool
) -> Dict[str, Any]:
    """
    Process a tool outcome and learn from it.

    This is evidence-based learning - we know which file was modified
    and whether the edit succeeded. We can reinforce patterns that
    were shown for this file.

    Called by post_tool.py after Write/Edit.
    """
    result = {
        "file_path": file_path,
        "success": success,
        "patterns_reinforced": 0,
    }

    # Get patterns that were shown for this file
    tracking = _file_pattern_tracking.get(file_path)
    if not tracking:
        return result

    patterns = tracking.get("patterns", [])
    if not patterns:
        return result

    # Reinforce patterns based on outcome
    # Success = helpful (+1), Failure = might be bad advice (-1)
    delta = 1 if success else -1

    for pattern in patterns:
        if pattern.type == PatternType.LESSON:
            # Reinforce the lesson in state
            applied = apply_pattern_reinforcement(state, pattern, delta)
            if applied:
                result["patterns_reinforced"] += 1

    # Clean up tracking
    _file_pattern_tracking.pop(file_path, None)

    return result


# =============================================================================
# TESTING
# =============================================================================

if __name__ == "__main__":
    # Test the learning loop
    from pattern_engine import surface_patterns

    test_state = {
        "objective": "Add dark mode",
        "plan": [
            {"description": "Update ThemeContext", "status": "completed"},
            {"description": "Add CSS variables", "status": "in_progress"},
        ],
        "memory": [
            {"trigger": "theme css", "lesson": "Use CSS variables", "reinforced": 2, "last_used": "2025-01-10"},
        ],
        "risks": [
            {"risk": "CSS browser support", "mitigation": "Check caniuse"},
        ]
    }

    # Simulate: surface patterns, then complete step
    bundle = surface_patterns(test_state, "Add CSS variables for theming", "ready_to_execute")

    step_key = make_step_key("Add dark mode", 1)
    track_surfaced_patterns(bundle, step_key)

    print("=" * 60)
    print("LEARNING LOOP TEST")
    print("=" * 60)
    print(f"Patterns surfaced: {len(bundle.patterns)}")
    print(f"Tracked under key: {step_key}")
    print()

    # Simulate step completion
    result = process_step_completion(
        test_state,
        "Add dark mode",
        1,
        "in_progress",
        "completed"
    )

    print(f"Outcome: {result['outcome']}")
    print(f"Patterns evaluated: {result['patterns_evaluated']}")
    print(f"Reinforcements applied: {result['reinforcements_applied']}")
    print()

    # Check stats
    stats = get_pattern_stats(test_state)
    print(format_pattern_stats(stats))
