#!/usr/bin/env python3
"""
Operator's Edge v7.0 - Outcome Tracker
Connects rule/context surfacing to tool outcomes.

The Key Insight:
- We surface rules and context at decision time
- We need to know if that surfacing actually helped
- By correlating surface events to outcomes, we can measure effectiveness

This enables:
1. Auto-graduating lessons that prove effective
2. Demoting rules that get overridden without consequence
3. Measuring real impact instead of just "surfaced count"
"""
import json
import os
import random
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

# Add hooks directory to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from state_utils import get_proof_dir


# =============================================================================
# CORRELATION ID MANAGEMENT
# =============================================================================

# In-memory store for pending correlations (per-session)
_pending_correlations: Dict[str, Dict[str, Any]] = {}


def generate_correlation_id() -> str:
    """Generate a unique correlation ID for tracking."""
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    random_hex = format(random.randint(0, 0xFFFF), '04x')
    return f"corr_{timestamp}_{random_hex}"


def log_surface_event(
    correlation_id: str,
    file_path: str,
    rules_fired: List[str],
    context_shown: List[str],
    tool_name: str = ""
) -> None:
    """
    Log when rules/context are surfaced to Claude.

    Called by pre_tool.py when rules fire or context is shown.
    """
    event = {
        "type": "surface",
        "correlation_id": correlation_id,
        "timestamp": datetime.now().isoformat(),
        "file_path": file_path,
        "tool_name": tool_name,
        "rules_fired": rules_fired,
        "context_shown": context_shown,
    }

    # Store in memory for correlation
    _pending_correlations[correlation_id] = event

    # Also persist to disk for analysis
    _append_to_log(event)


def log_outcome_event(
    correlation_id: str,
    success: bool,
    override: bool = False,
    error_message: str = ""
) -> None:
    """
    Log the outcome of a tool execution.

    Called by post_tool.py when a tool completes.

    Args:
        correlation_id: The ID from the surface event
        success: Whether the tool succeeded
        override: Whether the user overrode a rule warning
        error_message: Error details if failed
    """
    # Get the original surface event
    surface_event = _pending_correlations.pop(correlation_id, None)

    event = {
        "type": "outcome",
        "correlation_id": correlation_id,
        "timestamp": datetime.now().isoformat(),
        "success": success,
        "override": override,
        "error_message": error_message[:500] if error_message else "",
        "surface_event": surface_event,  # Include for analysis
    }

    _append_to_log(event)

    # Update rule effectiveness stats
    if surface_event:
        _update_rule_stats(surface_event, success, override)


def get_pending_correlation(file_path: str) -> Optional[str]:
    """
    Get the correlation ID for a pending file operation.

    Used by post_tool to find the correlation ID for the current file.
    """
    for corr_id, event in _pending_correlations.items():
        if event.get("file_path") == file_path:
            return corr_id
    return None


# =============================================================================
# RULE EFFECTIVENESS TRACKING
# =============================================================================

def _get_stats_file() -> Path:
    """Get the path to the rule stats file."""
    return get_proof_dir() / "rule_stats.json"


def _load_rule_stats() -> Dict[str, Any]:
    """Load rule effectiveness statistics."""
    stats_file = _get_stats_file()
    if stats_file.exists():
        try:
            return json.loads(stats_file.read_text())
        except (json.JSONDecodeError, IOError):
            pass
    return {"rules": {}, "updated": None}


def _save_rule_stats(stats: Dict[str, Any]) -> None:
    """Save rule effectiveness statistics."""
    stats_file = _get_stats_file()
    stats_file.parent.mkdir(parents=True, exist_ok=True)
    stats["updated"] = datetime.now().isoformat()
    stats_file.write_text(json.dumps(stats, indent=2))


def _update_rule_stats(
    surface_event: Dict[str, Any],
    success: bool,
    override: bool
) -> None:
    """Update effectiveness stats for rules that fired."""
    rules_fired = surface_event.get("rules_fired", [])
    if not rules_fired:
        return

    stats = _load_rule_stats()

    for rule_id in rules_fired:
        if rule_id not in stats["rules"]:
            stats["rules"][rule_id] = {
                "times_fired": 0,
                "times_success": 0,
                "times_override": 0,
                "times_override_success": 0,
                "times_override_failure": 0,
                "effectiveness": 0.0,
            }

        rule_stats = stats["rules"][rule_id]
        rule_stats["times_fired"] += 1

        if success:
            rule_stats["times_success"] += 1

        if override:
            rule_stats["times_override"] += 1
            if success:
                rule_stats["times_override_success"] += 1
            else:
                rule_stats["times_override_failure"] += 1

        # Calculate effectiveness
        # A rule is effective if:
        # - User follows it and succeeds (good advice)
        # - User overrides it and fails (warning was correct)
        # A rule is ineffective if:
        # - User overrides it and succeeds (unnecessary warning)
        if rule_stats["times_fired"] > 0:
            effective_outcomes = (
                rule_stats["times_success"] - rule_stats["times_override_success"]
                + rule_stats["times_override_failure"]
            )
            rule_stats["effectiveness"] = effective_outcomes / rule_stats["times_fired"]

    _save_rule_stats(stats)


def get_rule_effectiveness(rule_id: str) -> Optional[Dict[str, Any]]:
    """Get effectiveness statistics for a specific rule."""
    stats = _load_rule_stats()
    return stats["rules"].get(rule_id)


def get_all_rule_stats() -> Dict[str, Any]:
    """Get all rule effectiveness statistics."""
    return _load_rule_stats()


def get_ineffective_rules(threshold: float = 0.3) -> List[Tuple[str, float]]:
    """
    Get rules that are below the effectiveness threshold.

    These are candidates for demotion (rule → warning → removal).
    """
    stats = _load_rule_stats()
    ineffective = []

    for rule_id, rule_stats in stats["rules"].items():
        # Need at least 5 samples to judge
        if rule_stats["times_fired"] >= 5:
            if rule_stats["effectiveness"] < threshold:
                ineffective.append((rule_id, rule_stats["effectiveness"]))

    return sorted(ineffective, key=lambda x: x[1])


def get_highly_effective_rules(threshold: float = 0.8) -> List[Tuple[str, float]]:
    """
    Get rules that are above the effectiveness threshold.

    These are candidates for stricter enforcement (warn → block).
    """
    stats = _load_rule_stats()
    effective = []

    for rule_id, rule_stats in stats["rules"].items():
        # Need at least 5 samples to judge
        if rule_stats["times_fired"] >= 5:
            if rule_stats["effectiveness"] >= threshold:
                effective.append((rule_id, rule_stats["effectiveness"]))

    return sorted(effective, key=lambda x: x[1], reverse=True)


# =============================================================================
# LOG FILE MANAGEMENT
# =============================================================================

def _get_log_file() -> Path:
    """Get the path to the outcome tracking log."""
    return get_proof_dir() / "outcome_tracking.jsonl"


def _append_to_log(event: Dict[str, Any]) -> None:
    """Append an event to the outcome tracking log."""
    log_file = _get_log_file()
    log_file.parent.mkdir(parents=True, exist_ok=True)

    with open(log_file, "a") as f:
        f.write(json.dumps(event) + "\n")


def load_outcome_log(limit: int = 100) -> List[Dict[str, Any]]:
    """Load recent entries from the outcome tracking log."""
    log_file = _get_log_file()
    if not log_file.exists():
        return []

    events = []
    try:
        with open(log_file) as f:
            for line in f:
                if line.strip():
                    events.append(json.loads(line))
    except (json.JSONDecodeError, IOError):
        pass

    return events[-limit:]


# =============================================================================
# ANALYSIS FUNCTIONS
# =============================================================================

def analyze_rule_impact() -> Dict[str, Any]:
    """
    Analyze the overall impact of rules on outcomes.

    Returns summary statistics about rule effectiveness.
    """
    stats = _load_rule_stats()

    total_fires = sum(r["times_fired"] for r in stats["rules"].values())
    total_success = sum(r["times_success"] for r in stats["rules"].values())
    total_overrides = sum(r["times_override"] for r in stats["rules"].values())
    override_failures = sum(r["times_override_failure"] for r in stats["rules"].values())

    return {
        "total_rule_fires": total_fires,
        "total_successes": total_success,
        "success_rate": total_success / total_fires if total_fires > 0 else 0,
        "total_overrides": total_overrides,
        "override_failure_rate": override_failures / total_overrides if total_overrides > 0 else 0,
        "rules_tracked": len(stats["rules"]),
        "ineffective_rules": len(get_ineffective_rules()),
        "highly_effective_rules": len(get_highly_effective_rules()),
    }


# =============================================================================
# TESTING
# =============================================================================

if __name__ == "__main__":
    print("=" * 60)
    print("   OUTCOME TRACKER TEST")
    print("=" * 60)
    print()

    # Simulate a rule firing and outcome
    corr_id = generate_correlation_id()
    print(f"Generated correlation ID: {corr_id}")

    # Log surface event
    log_surface_event(
        correlation_id=corr_id,
        file_path="/test/file.py",
        rules_fired=["python-shebang"],
        context_shown=["cochange: test_file.py"],
        tool_name="Write"
    )
    print("Logged surface event")

    # Log outcome
    log_outcome_event(
        correlation_id=corr_id,
        success=True,
        override=False
    )
    print("Logged outcome event")

    # Check stats
    stats = get_rule_effectiveness("python-shebang")
    print(f"\nRule stats: {json.dumps(stats, indent=2)}")

    # Analyze impact
    impact = analyze_rule_impact()
    print(f"\nOverall impact: {json.dumps(impact, indent=2)}")

    print()
    print("=" * 60)
    print("Outcome tracker ready.")
