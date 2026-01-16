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


# =============================================================================
# STORAGE PATHS
# =============================================================================

def get_proof_dir() -> Path:
    """Get the proof directory, creating if needed."""
    proof_dir = Path(".proof")
    proof_dir.mkdir(exist_ok=True)
    return proof_dir


def get_outcome_log_path() -> Path:
    """Get the path to the outcome tracking log."""
    return get_proof_dir() / "outcome_tracking.jsonl"


def get_rule_stats_path() -> Path:
    """Get the path to aggregated rule statistics."""
    return get_proof_dir() / "rule_stats.json"


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


def store_pending_correlation(correlation_id: str, data: Dict[str, Any]) -> None:
    """Store correlation data for later outcome matching."""
    _pending_correlations[correlation_id] = {
        **data,
        "stored_at": datetime.now().isoformat(),
    }


def get_pending_correlation(correlation_id: str) -> Optional[Dict[str, Any]]:
    """Retrieve and remove pending correlation data."""
    return _pending_correlations.pop(correlation_id, None)


def get_latest_pending_correlation() -> Optional[Tuple[str, Dict[str, Any]]]:
    """Get the most recent pending correlation (for cases where ID wasn't passed)."""
    if not _pending_correlations:
        return None
    # Get most recent by stored_at
    latest_id = max(
        _pending_correlations.keys(),
        key=lambda k: _pending_correlations[k].get("stored_at", "")
    )
    data = _pending_correlations.pop(latest_id)
    return (latest_id, data)


def clear_stale_correlations(max_age_seconds: int = 300) -> int:
    """Clear correlations older than max_age_seconds. Returns count cleared."""
    from datetime import timedelta
    cutoff = datetime.now() - timedelta(seconds=max_age_seconds)
    stale = []
    for cid, data in _pending_correlations.items():
        stored_at = data.get("stored_at", "")
        if stored_at:
            try:
                stored_time = datetime.fromisoformat(stored_at)
                if stored_time < cutoff:
                    stale.append(cid)
            except ValueError:
                stale.append(cid)  # Invalid timestamp, clear it
    for cid in stale:
        _pending_correlations.pop(cid, None)
    return len(stale)


# =============================================================================
# SURFACE EVENT LOGGING
# =============================================================================

def log_surface_event(
    correlation_id: str,
    file_path: str,
    rules_fired: List[str],
    context_shown: List[str],
    tool_name: str = ""
) -> None:
    """
    Log when rules fire or context is surfaced.
    Called by pre_tool.py before tool execution.
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
    
    # Store for correlation
    store_pending_correlation(correlation_id, event)
    
    # Append to log
    _append_to_log(event)


def log_outcome_event(
    correlation_id: str,
    success: bool,
    tool_name: str,
    was_overridden: bool = False,
    error_message: str = ""
) -> None:
    """
    Log the outcome of a tool execution.
    Called by post_tool.py after tool execution.
    """
    # Try to get the correlated surface event
    surface_data = get_pending_correlation(correlation_id)
    
    event = {
        "type": "outcome",
        "correlation_id": correlation_id,
        "timestamp": datetime.now().isoformat(),
        "success": success,
        "tool_name": tool_name,
        "was_overridden": was_overridden,
        "error_message": error_message[:200] if error_message else "",
    }
    
    # If we have surface data, include the rules that fired
    if surface_data:
        event["rules_fired"] = surface_data.get("rules_fired", [])
        event["context_shown"] = surface_data.get("context_shown", [])
        event["file_path"] = surface_data.get("file_path", "")
    
    # Append to log
    _append_to_log(event)
    
    # Update rule statistics
    if surface_data and surface_data.get("rules_fired"):
        _update_rule_stats(
            rules=surface_data["rules_fired"],
            success=success,
            was_overridden=was_overridden
        )


def _append_to_log(event: Dict[str, Any]) -> None:
    """Append an event to the outcome tracking log."""
    try:
        log_path = get_outcome_log_path()
        with open(log_path, "a") as f:
            f.write(json.dumps(event) + "\n")
    except (IOError, OSError):
        pass  # Best effort logging


# =============================================================================
# RULE STATISTICS
# =============================================================================

def _load_rule_stats() -> Dict[str, Dict[str, Any]]:
    """Load rule statistics from disk."""
    try:
        stats_path = get_rule_stats_path()
        if stats_path.exists():
            return json.loads(stats_path.read_text())
    except (json.JSONDecodeError, IOError):
        pass
    return {}


def _save_rule_stats(stats: Dict[str, Dict[str, Any]]) -> None:
    """Save rule statistics to disk."""
    try:
        stats_path = get_rule_stats_path()
        stats_path.write_text(json.dumps(stats, indent=2))
    except (IOError, OSError):
        pass  # Best effort


def _update_rule_stats(
    rules: List[str],
    success: bool,
    was_overridden: bool
) -> None:
    """Update statistics for rules that fired."""
    stats = _load_rule_stats()
    
    for rule_id in rules:
        if rule_id not in stats:
            stats[rule_id] = {
                "fired": 0,
                "successes": 0,
                "failures": 0,
                "overrides": 0,
                "override_successes": 0,
                "override_failures": 0,
                "last_fired": None,
            }
        
        rule_stats = stats[rule_id]
        rule_stats["fired"] += 1
        rule_stats["last_fired"] = datetime.now().isoformat()
        
        if was_overridden:
            rule_stats["overrides"] += 1
            if success:
                rule_stats["override_successes"] += 1
            else:
                rule_stats["override_failures"] += 1
        else:
            if success:
                rule_stats["successes"] += 1
            else:
                rule_stats["failures"] += 1
    
    _save_rule_stats(stats)


def get_rule_stats(rule_id: str) -> Optional[Dict[str, Any]]:
    """Get statistics for a specific rule."""
    stats = _load_rule_stats()
    return stats.get(rule_id)


def get_all_rule_stats() -> Dict[str, Dict[str, Any]]:
    """Get statistics for all rules."""
    return _load_rule_stats()


# =============================================================================
# EFFECTIVENESS ANALYSIS
# =============================================================================

def compute_rule_effectiveness(rule_id: str) -> Optional[float]:
    """
    Compute effectiveness score for a rule.
    
    Effectiveness = (successes - override_successes + override_failures) / fired
    
    Logic:
    - Successes when NOT overridden = rule helped
    - Override + success = rule was wrong (false positive)
    - Override + failure = rule was right but ignored
    
    Returns None if no data, otherwise 0.0 to 1.0
    """
    stats = get_rule_stats(rule_id)
    if not stats or stats.get("fired", 0) == 0:
        return None
    
    fired = stats["fired"]
    successes = stats.get("successes", 0)
    override_successes = stats.get("override_successes", 0)
    override_failures = stats.get("override_failures", 0)
    
    # Adjusted score: penalize false positives, reward catching real issues
    adjusted = successes - override_successes + override_failures
    
    return max(0.0, min(1.0, adjusted / fired))


def get_ineffective_rules(threshold: float = 0.3, min_fires: int = 5) -> List[Dict[str, Any]]:
    """
    Get rules that are performing poorly.
    
    Returns rules with effectiveness below threshold and at least min_fires.
    """
    stats = get_all_rule_stats()
    ineffective = []
    
    for rule_id, rule_stats in stats.items():
        if rule_stats.get("fired", 0) < min_fires:
            continue
        
        effectiveness = compute_rule_effectiveness(rule_id)
        if effectiveness is not None and effectiveness < threshold:
            ineffective.append({
                "rule_id": rule_id,
                "effectiveness": effectiveness,
                "fired": rule_stats["fired"],
                "overrides": rule_stats.get("overrides", 0),
                "override_success_rate": (
                    rule_stats.get("override_successes", 0) / rule_stats.get("overrides", 1)
                    if rule_stats.get("overrides", 0) > 0 else 0
                ),
            })
    
    # Sort by effectiveness (worst first)
    ineffective.sort(key=lambda x: x["effectiveness"])
    return ineffective


def get_highly_effective_rules(threshold: float = 0.8, min_fires: int = 5) -> List[Dict[str, Any]]:
    """
    Get rules that are performing well.
    
    Returns rules with effectiveness above threshold and at least min_fires.
    """
    stats = get_all_rule_stats()
    effective = []
    
    for rule_id, rule_stats in stats.items():
        if rule_stats.get("fired", 0) < min_fires:
            continue
        
        effectiveness = compute_rule_effectiveness(rule_id)
        if effectiveness is not None and effectiveness >= threshold:
            effective.append({
                "rule_id": rule_id,
                "effectiveness": effectiveness,
                "fired": rule_stats["fired"],
                "successes": rule_stats.get("successes", 0),
            })
    
    # Sort by effectiveness (best first)
    effective.sort(key=lambda x: -x["effectiveness"])
    return effective


def analyze_rule_impact() -> Dict[str, Any]:
    """
    Analyze the overall impact of the rules system.
    
    Returns summary statistics and recommendations.
    """
    stats = get_all_rule_stats()
    
    if not stats:
        return {
            "total_rules": 0,
            "total_fires": 0,
            "overall_effectiveness": None,
            "recommendations": ["No rule data yet - outcomes will be tracked as rules fire"],
        }
    
    total_fires = sum(s.get("fired", 0) for s in stats.values())
    total_successes = sum(s.get("successes", 0) for s in stats.values())
    total_overrides = sum(s.get("overrides", 0) for s in stats.values())
    total_override_successes = sum(s.get("override_successes", 0) for s in stats.values())
    
    overall_effectiveness = (
        (total_successes - total_override_successes) / total_fires
        if total_fires > 0 else None
    )
    
    recommendations = []
    
    ineffective = get_ineffective_rules()
    if ineffective:
        worst = ineffective[0]
        recommendations.append(
            f"Consider demoting rule '{worst['rule_id']}' "
            f"(effectiveness: {worst['effectiveness']:.0%}, "
            f"overridden {worst['overrides']} times)"
        )
    
    effective = get_highly_effective_rules()
    if effective:
        best = effective[0]
        recommendations.append(
            f"Rule '{best['rule_id']}' is highly effective "
            f"({best['effectiveness']:.0%}) - consider stricter enforcement"
        )
    
    override_rate = total_overrides / total_fires if total_fires > 0 else 0
    if override_rate > 0.3:
        recommendations.append(
            f"High override rate ({override_rate:.0%}) - rules may be too aggressive"
        )
    
    return {
        "total_rules": len(stats),
        "total_fires": total_fires,
        "total_successes": total_successes,
        "total_overrides": total_overrides,
        "overall_effectiveness": overall_effectiveness,
        "override_rate": override_rate,
        "ineffective_rules": len(ineffective),
        "effective_rules": len(effective),
        "recommendations": recommendations,
    }


# =============================================================================
# TESTING SUPPORT
# =============================================================================

def reset_for_testing() -> None:
    """Reset in-memory state for testing."""
    global _pending_correlations
    _pending_correlations = {}


if __name__ == "__main__":
    # Quick self-test
    print("Outcome Tracker Self-Test")
    print("=" * 40)
    
    # Generate correlation
    cid = generate_correlation_id()
    print(f"Generated correlation ID: {cid}")
    
    # Log surface event
    log_surface_event(
        correlation_id=cid,
        file_path="test.py",
        rules_fired=["python-shebang"],
        context_shown=["Use python3 for portability"],
        tool_name="Write"
    )
    print("Logged surface event")
    
    # Log outcome
    log_outcome_event(
        correlation_id=cid,
        success=True,
        tool_name="Write",
        was_overridden=False
    )
    print("Logged outcome event")
    
    # Check stats
    stats = get_rule_stats("python-shebang")
    print(f"Rule stats: {stats}")
    
    # Analyze
    impact = analyze_rule_impact()
    print(f"Impact analysis: {impact}")
