#!/usr/bin/env python3
"""
Operator's Edge - Outcome Scorecard Utilities
Per-objective scoring and autonomy governor.

TAS v1.0 Phase D: Outcome-based metrics that drive autonomous behavior.

Scorecard computed at objective completion:
1. Objective Success: completed vs not completed
2. Efficiency: dispatch iterations / steps completed
3. Junction Rate: junctions_hit / total_iterations
4. Stuck Events: count of stuck threshold hits
5. Quality: quality gate pass/fail
6. Learning Impact: new memory items, reinforcements
"""
import json
import os
import sys
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Any, Tuple

# Add hooks directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from state_utils import load_yaml_state
from archive_utils import log_to_archive, search_archive


# =============================================================================
# SCORECARD COMPUTATION
# =============================================================================

def compute_objective_scorecard(
    objective: str,
    dispatch_state: dict,
    yaml_state: dict,
    quality_gate_passed: bool = True,
    quality_gate_reason: str = ""
) -> Dict[str, Any]:
    """
    Compute an outcome scorecard for a completed objective.

    Args:
        objective: The objective that was completed
        dispatch_state: Dispatch state at completion
        yaml_state: Active context YAML state
        quality_gate_passed: Whether quality gate passed
        quality_gate_reason: Reason if failed

    Returns:
        Scorecard dict with all metrics
    """
    stats = dispatch_state.get("stats", {})
    plan = yaml_state.get("plan", [])
    memory = yaml_state.get("memory", [])

    # 1. Objective Success
    completed_steps = len([s for s in plan if isinstance(s, dict) and s.get("status") == "completed"])
    total_steps = len(plan)
    success = completed_steps == total_steps and total_steps > 0

    # 2. Efficiency: iterations per step
    iterations = dispatch_state.get("iteration", 0)
    efficiency = iterations / completed_steps if completed_steps > 0 else float('inf')

    # 3. Junction Rate
    junctions_hit = stats.get("junctions_hit", 0)
    junction_rate = junctions_hit / iterations if iterations > 0 else 0

    # 4. Stuck Events
    stuck_count = dispatch_state.get("stuck_count", 0)

    # 5. Quality
    quality = {
        "passed": quality_gate_passed,
        "reason": quality_gate_reason
    }

    # 6. Learning Impact
    # Count lessons with recent last_used
    today = datetime.now().strftime('%Y-%m-%d')
    recent_lessons = [m for m in memory if isinstance(m, dict) and m.get('last_used') == today]
    total_reinforcements = sum(m.get('reinforced', 0) for m in memory if isinstance(m, dict))

    learning = {
        "lessons_used_today": len(recent_lessons),
        "total_reinforcements": total_reinforcements,
        "memory_items": len(memory)
    }

    return {
        "type": "objective_scorecard",
        "timestamp": datetime.now().isoformat(),
        "objective": objective,
        "success": success,
        "metrics": {
            "steps_completed": completed_steps,
            "steps_total": total_steps,
            "iterations": iterations,
            "efficiency": round(efficiency, 2),
            "junctions_hit": junctions_hit,
            "junction_rate": round(junction_rate, 3),
            "stuck_count": stuck_count,
        },
        "quality": quality,
        "learning": learning
    }


def persist_scorecard(scorecard: Dict[str, Any]) -> bool:
    """
    Persist a scorecard to the archive.

    Returns True if successful.
    """
    try:
        log_to_archive(scorecard)
        return True
    except Exception:
        return False


# =============================================================================
# AUTONOMY GOVERNOR
# =============================================================================

def get_recent_scorecards(count: int = 5) -> List[Dict[str, Any]]:
    """
    Get the most recent objective scorecards from archive.
    """
    return search_archive(entry_type="objective_scorecard", limit=count)


def compute_governor_recommendation(scorecards: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Compute autonomy governor recommendation based on recent scorecards.

    Returns recommendation dict with:
    - direction: "increase" | "decrease" | "maintain"
    - reason: explanation
    - suggested_changes: specific adjustments
    """
    if len(scorecards) < 2:
        return {
            "direction": "maintain",
            "reason": "Insufficient data (need at least 2 scorecards)",
            "suggested_changes": []
        }

    # Compute averages
    success_rate = sum(1 for s in scorecards if s.get("success")) / len(scorecards)
    avg_efficiency = sum(s.get("metrics", {}).get("efficiency", 0) for s in scorecards) / len(scorecards)
    avg_junction_rate = sum(s.get("metrics", {}).get("junction_rate", 0) for s in scorecards) / len(scorecards)
    avg_stuck_count = sum(s.get("metrics", {}).get("stuck_count", 0) for s in scorecards) / len(scorecards)
    quality_pass_rate = sum(1 for s in scorecards if s.get("quality", {}).get("passed", True)) / len(scorecards)

    # Trend analysis (compare first half to second half)
    mid = len(scorecards) // 2
    first_half = scorecards[:mid]
    second_half = scorecards[mid:]

    first_stuck = sum(s.get("metrics", {}).get("stuck_count", 0) for s in first_half) / max(len(first_half), 1)
    second_stuck = sum(s.get("metrics", {}).get("stuck_count", 0) for s in second_half) / max(len(second_half), 1)
    stuck_trend = "rising" if second_stuck > first_stuck * 1.2 else "falling" if second_stuck < first_stuck * 0.8 else "stable"

    first_efficiency = sum(s.get("metrics", {}).get("efficiency", 0) for s in first_half) / max(len(first_half), 1)
    second_efficiency = sum(s.get("metrics", {}).get("efficiency", 0) for s in second_half) / max(len(second_half), 1)
    efficiency_trend = "improving" if second_efficiency < first_efficiency * 0.9 else "degrading" if second_efficiency > first_efficiency * 1.1 else "stable"

    # Decision logic
    suggested_changes = []

    # Check for quality concerns
    if quality_pass_rate < 0.8:
        return {
            "direction": "decrease",
            "reason": f"Quality pass rate low ({quality_pass_rate:.0%})",
            "suggested_changes": [
                "Add more verification steps",
                "Require quality gate before objective completion",
                "Pause at more junction types"
            ],
            "stats": {
                "success_rate": round(success_rate, 2),
                "avg_efficiency": round(avg_efficiency, 2),
                "avg_junction_rate": round(avg_junction_rate, 3),
                "avg_stuck_count": round(avg_stuck_count, 2),
                "quality_pass_rate": round(quality_pass_rate, 2),
                "stuck_trend": stuck_trend,
                "efficiency_trend": efficiency_trend
            }
        }

    # Check for stuck trend
    if stuck_trend == "rising":
        suggested_changes.append("Reduce stuck threshold to pause earlier")
        suggested_changes.append("Add junction at step failures")
        return {
            "direction": "decrease",
            "reason": f"Stuck events rising (trend: {first_stuck:.1f} → {second_stuck:.1f})",
            "suggested_changes": suggested_changes,
            "stats": {
                "success_rate": round(success_rate, 2),
                "avg_efficiency": round(avg_efficiency, 2),
                "avg_junction_rate": round(avg_junction_rate, 3),
                "avg_stuck_count": round(avg_stuck_count, 2),
                "quality_pass_rate": round(quality_pass_rate, 2),
                "stuck_trend": stuck_trend,
                "efficiency_trend": efficiency_trend
            }
        }

    # Check for success + efficiency improvement → increase autonomy
    if success_rate >= 0.8 and efficiency_trend == "improving":
        suggested_changes.append("Reduce junction pauses for routine actions")
        suggested_changes.append("Increase stuck threshold")
        suggested_changes.append("Auto-approve simple junctions")
        return {
            "direction": "increase",
            "reason": f"High success ({success_rate:.0%}) + improving efficiency",
            "suggested_changes": suggested_changes,
            "stats": {
                "success_rate": round(success_rate, 2),
                "avg_efficiency": round(avg_efficiency, 2),
                "avg_junction_rate": round(avg_junction_rate, 3),
                "avg_stuck_count": round(avg_stuck_count, 2),
                "quality_pass_rate": round(quality_pass_rate, 2),
                "stuck_trend": stuck_trend,
                "efficiency_trend": efficiency_trend
            }
        }

    # Default: maintain
    return {
        "direction": "maintain",
        "reason": "Metrics stable - no adjustment needed",
        "suggested_changes": [],
        "stats": {
            "success_rate": round(success_rate, 2),
            "avg_efficiency": round(avg_efficiency, 2),
            "avg_junction_rate": round(avg_junction_rate, 3),
            "avg_stuck_count": round(avg_stuck_count, 2),
            "quality_pass_rate": round(quality_pass_rate, 2),
            "stuck_trend": stuck_trend,
            "efficiency_trend": efficiency_trend
        }
    }


def get_autonomy_level(scorecards: Optional[List[Dict[str, Any]]] = None) -> Dict[str, Any]:
    """
    Get current autonomy level based on recent performance.

    Returns dict with:
    - level: "high" | "medium" | "low"
    - junction_types: list of junction types that should pause
    - stuck_threshold: when to declare stuck
    - auto_approve_types: junction types that can auto-approve
    """
    if scorecards is None:
        scorecards = get_recent_scorecards(5)

    if len(scorecards) < 2:
        # Default: medium autonomy
        return {
            "level": "medium",
            "junction_types": ["irreversible", "external", "ambiguous", "blocked"],
            "stuck_threshold": 3,
            "auto_approve_types": []
        }

    recommendation = compute_governor_recommendation(scorecards)

    if recommendation["direction"] == "increase":
        return {
            "level": "high",
            "junction_types": ["irreversible", "external"],  # Fewer pauses
            "stuck_threshold": 5,  # More tolerance
            "auto_approve_types": ["ambiguous"]  # Auto-approve some
        }
    elif recommendation["direction"] == "decrease":
        return {
            "level": "low",
            "junction_types": ["irreversible", "external", "ambiguous", "blocked", "step_failure"],
            "stuck_threshold": 2,  # Less tolerance
            "auto_approve_types": []
        }
    else:
        return {
            "level": "medium",
            "junction_types": ["irreversible", "external", "ambiguous", "blocked"],
            "stuck_threshold": 3,
            "auto_approve_types": []
        }


# =============================================================================
# OBJECTIVE COMPLETION HOOK
# =============================================================================

def on_objective_complete(dispatch_state: dict, quality_passed: bool = True, quality_reason: str = "") -> Dict[str, Any]:
    """
    Called when an objective completes. Computes and persists scorecard.

    Returns the scorecard.
    """
    yaml_state = load_yaml_state() or {}
    objective = yaml_state.get("objective", "Unknown objective")

    scorecard = compute_objective_scorecard(
        objective=objective,
        dispatch_state=dispatch_state,
        yaml_state=yaml_state,
        quality_gate_passed=quality_passed,
        quality_gate_reason=quality_reason
    )

    persist_scorecard(scorecard)

    # Update dispatch stats
    if "stats" in dispatch_state:
        dispatch_state["stats"]["objectives_completed"] = dispatch_state["stats"].get("objectives_completed", 0) + 1

    return scorecard


def format_scorecard(scorecard: Dict[str, Any]) -> str:
    """Format a scorecard for display."""
    lines = [
        "=" * 70,
        "OBJECTIVE SCORECARD",
        "=" * 70,
        "",
        f"Objective: {scorecard.get('objective', 'Unknown')[:50]}...",
        f"Result: {'✓ SUCCESS' if scorecard.get('success') else '✗ INCOMPLETE'}",
        "",
        "Metrics:",
        f"  Steps: {scorecard.get('metrics', {}).get('steps_completed', 0)}/{scorecard.get('metrics', {}).get('steps_total', 0)}",
        f"  Iterations: {scorecard.get('metrics', {}).get('iterations', 0)}",
        f"  Efficiency: {scorecard.get('metrics', {}).get('efficiency', 0):.2f} iter/step",
        f"  Junctions: {scorecard.get('metrics', {}).get('junctions_hit', 0)} ({scorecard.get('metrics', {}).get('junction_rate', 0):.1%} rate)",
        f"  Stuck events: {scorecard.get('metrics', {}).get('stuck_count', 0)}",
        "",
        f"Quality: {'✓ Passed' if scorecard.get('quality', {}).get('passed') else '✗ Failed - ' + scorecard.get('quality', {}).get('reason', '')}",
        "",
        f"Learning: {scorecard.get('learning', {}).get('lessons_used_today', 0)} lessons used, {scorecard.get('learning', {}).get('total_reinforcements', 0)} total reinforcements",
        "",
        "=" * 70,
    ]
    return "\n".join(lines)


def format_governor_recommendation(recommendation: Dict[str, Any]) -> str:
    """Format governor recommendation for display."""
    direction = recommendation.get("direction", "maintain")
    emoji = "↑" if direction == "increase" else "↓" if direction == "decrease" else "→"

    lines = [
        "-" * 70,
        f"AUTONOMY GOVERNOR: {emoji} {direction.upper()}",
        "-" * 70,
        "",
        f"Reason: {recommendation.get('reason', 'No reason')}",
        "",
    ]

    stats = recommendation.get("stats", {})
    if stats:
        lines.extend([
            "Historical metrics:",
            f"  Success rate: {stats.get('success_rate', 0):.0%}",
            f"  Avg efficiency: {stats.get('avg_efficiency', 0):.2f}",
            f"  Quality pass rate: {stats.get('quality_pass_rate', 0):.0%}",
            f"  Stuck trend: {stats.get('stuck_trend', 'unknown')}",
            "",
        ])

    changes = recommendation.get("suggested_changes", [])
    if changes:
        lines.append("Suggested changes:")
        for change in changes:
            lines.append(f"  - {change}")
        lines.append("")

    lines.append("-" * 70)
    return "\n".join(lines)
