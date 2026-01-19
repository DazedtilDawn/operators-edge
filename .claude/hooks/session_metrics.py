#!/usr/bin/env python3
"""
Operator's Edge v8.0 - Session Metrics (Phase 5)

Measure the effectiveness of v8.0 supervision systems.

Key Metrics:
1. Drift Interventions - How often drift signals fired, did Claude course-correct?
2. Fix Hit Rate - Known fixes surfaced vs. followed vs. successful
3. Handoff Quality - Did next session start faster? Use handoff info?
4. Context Efficiency - Session duration vs. context consumed

This is observability for context engineering.
"""
import json
import os
import sys
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Any

# Add hooks directory to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


# =============================================================================
# CONFIGURATION
# =============================================================================

# Metrics storage location
METRICS_FILE = "session_metrics.json"

# Retention policy
MAX_SESSIONS = 50  # Keep metrics for last N sessions


# =============================================================================
# DATA STRUCTURES
# =============================================================================

@dataclass
class DriftMetrics:
    """Metrics about drift detection effectiveness."""
    signals_fired: Dict[str, int] = field(default_factory=dict)  # {FILE_CHURN: 2, ...}
    interventions_shown: int = 0
    course_corrections: int = 0  # Times work pattern changed after signal
    ignored_signals: int = 0

    def to_dict(self) -> dict:
        return {
            "signals_fired": self.signals_fired,
            "interventions_shown": self.interventions_shown,
            "course_corrections": self.course_corrections,
            "ignored_signals": self.ignored_signals,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "DriftMetrics":
        return cls(
            signals_fired=data.get("signals_fired", {}),
            interventions_shown=data.get("interventions_shown", 0),
            course_corrections=data.get("course_corrections", 0),
            ignored_signals=data.get("ignored_signals", 0),
        )


@dataclass
class FixMetrics:
    """Metrics about codebase knowledge fix suggestions."""
    fixes_surfaced: int = 0
    fixes_followed: int = 0  # User applied the suggested fix
    fixes_successful: int = 0  # Fix actually resolved the issue
    fixes_ignored: int = 0
    new_fixes_learned: int = 0

    def to_dict(self) -> dict:
        return {
            "fixes_surfaced": self.fixes_surfaced,
            "fixes_followed": self.fixes_followed,
            "fixes_successful": self.fixes_successful,
            "fixes_ignored": self.fixes_ignored,
            "new_fixes_learned": self.new_fixes_learned,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "FixMetrics":
        return cls(
            fixes_surfaced=data.get("fixes_surfaced", 0),
            fixes_followed=data.get("fixes_followed", 0),
            fixes_successful=data.get("fixes_successful", 0),
            fixes_ignored=data.get("fixes_ignored", 0),
            new_fixes_learned=data.get("new_fixes_learned", 0),
        )


@dataclass
class HandoffMetrics:
    """Metrics about session handoff effectiveness."""
    handoff_generated: bool = False
    handoff_used_by_next: bool = False
    previous_handoff_available: bool = False
    previous_handoff_used: bool = False
    time_to_first_action_seconds: float = 0.0  # How fast did next session start working?

    def to_dict(self) -> dict:
        return {
            "handoff_generated": self.handoff_generated,
            "handoff_used_by_next": self.handoff_used_by_next,
            "previous_handoff_available": self.previous_handoff_available,
            "previous_handoff_used": self.previous_handoff_used,
            "time_to_first_action_seconds": self.time_to_first_action_seconds,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "HandoffMetrics":
        return cls(
            handoff_generated=data.get("handoff_generated", False),
            handoff_used_by_next=data.get("handoff_used_by_next", False),
            previous_handoff_available=data.get("previous_handoff_available", False),
            previous_handoff_used=data.get("previous_handoff_used", False),
            time_to_first_action_seconds=data.get("time_to_first_action_seconds", 0.0),
        )


@dataclass
class ContextMetrics:
    """Metrics about context window efficiency."""
    peak_usage_percent: float = 0.0
    final_usage_percent: float = 0.0
    compression_recommendations: int = 0
    compressions_performed: int = 0
    session_duration_minutes: float = 0.0
    tool_calls_total: int = 0
    files_read: int = 0
    files_modified: int = 0

    def to_dict(self) -> dict:
        return {
            "peak_usage_percent": round(self.peak_usage_percent, 1),
            "final_usage_percent": round(self.final_usage_percent, 1),
            "compression_recommendations": self.compression_recommendations,
            "compressions_performed": self.compressions_performed,
            "session_duration_minutes": round(self.session_duration_minutes, 1),
            "tool_calls_total": self.tool_calls_total,
            "files_read": self.files_read,
            "files_modified": self.files_modified,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "ContextMetrics":
        return cls(
            peak_usage_percent=data.get("peak_usage_percent", 0.0),
            final_usage_percent=data.get("final_usage_percent", 0.0),
            compression_recommendations=data.get("compression_recommendations", 0),
            compressions_performed=data.get("compressions_performed", 0),
            session_duration_minutes=data.get("session_duration_minutes", 0.0),
            tool_calls_total=data.get("tool_calls_total", 0),
            files_read=data.get("files_read", 0),
            files_modified=data.get("files_modified", 0),
        )


@dataclass
class SessionMetrics:
    """Complete metrics for a single session."""
    session_id: str
    started_at: str
    ended_at: str = ""
    objective: str = ""

    # Sub-metrics
    drift: DriftMetrics = field(default_factory=DriftMetrics)
    fixes: FixMetrics = field(default_factory=FixMetrics)
    handoff: HandoffMetrics = field(default_factory=HandoffMetrics)
    context: ContextMetrics = field(default_factory=ContextMetrics)

    # Outcome
    objective_completed: bool = False
    steps_completed: int = 0
    steps_total: int = 0

    def to_dict(self) -> dict:
        return {
            "session_id": self.session_id,
            "started_at": self.started_at,
            "ended_at": self.ended_at,
            "objective": self.objective,
            "drift": self.drift.to_dict(),
            "fixes": self.fixes.to_dict(),
            "handoff": self.handoff.to_dict(),
            "context": self.context.to_dict(),
            "objective_completed": self.objective_completed,
            "steps_completed": self.steps_completed,
            "steps_total": self.steps_total,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "SessionMetrics":
        return cls(
            session_id=data.get("session_id", ""),
            started_at=data.get("started_at", ""),
            ended_at=data.get("ended_at", ""),
            objective=data.get("objective", ""),
            drift=DriftMetrics.from_dict(data.get("drift", {})),
            fixes=FixMetrics.from_dict(data.get("fixes", {})),
            handoff=HandoffMetrics.from_dict(data.get("handoff", {})),
            context=ContextMetrics.from_dict(data.get("context", {})),
            objective_completed=data.get("objective_completed", False),
            steps_completed=data.get("steps_completed", 0),
            steps_total=data.get("steps_total", 0),
        )


# =============================================================================
# METRICS STORAGE
# =============================================================================

def _get_metrics_path() -> Path:
    """Get path to metrics storage file."""
    proof_dir = Path(__file__).parent.parent.parent / ".proof"
    proof_dir.mkdir(parents=True, exist_ok=True)
    return proof_dir / METRICS_FILE


def _load_all_metrics() -> Dict[str, Any]:
    """Load all metrics from disk."""
    path = _get_metrics_path()
    if not path.exists():
        return {"sessions": {}, "metadata": {"version": 1}}

    try:
        with open(path) as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return {"sessions": {}, "metadata": {"version": 1}}


def _save_all_metrics(data: Dict[str, Any]) -> bool:
    """Save all metrics to disk."""
    path = _get_metrics_path()
    try:
        with open(path, 'w') as f:
            json.dump(data, f, indent=2)
        return True
    except OSError:
        return False


def _cleanup_old_metrics(data: Dict[str, Any]) -> Dict[str, Any]:
    """Remove old sessions beyond retention limit."""
    sessions = data.get("sessions", {})
    if len(sessions) <= MAX_SESSIONS:
        return data

    # Sort by started_at and keep most recent
    sorted_sessions = sorted(
        sessions.items(),
        key=lambda x: x[1].get("started_at", ""),
        reverse=True
    )

    data["sessions"] = dict(sorted_sessions[:MAX_SESSIONS])
    return data


# =============================================================================
# METRICS TRACKING - In-Session
# =============================================================================

# In-memory metrics for current session
_current_session_metrics: Optional[SessionMetrics] = None
_peak_context_usage: float = 0.0


def start_session_metrics(session_id: str, objective: str = "") -> SessionMetrics:
    """Initialize metrics tracking for a new session."""
    global _current_session_metrics, _peak_context_usage

    _current_session_metrics = SessionMetrics(
        session_id=session_id,
        started_at=datetime.now().isoformat(),
        objective=objective,
    )
    _peak_context_usage = 0.0

    return _current_session_metrics


def get_current_metrics() -> Optional[SessionMetrics]:
    """Get the current session's metrics (in-memory)."""
    global _current_session_metrics
    return _current_session_metrics


def ensure_session_metrics(session_id: str = "") -> SessionMetrics:
    """Ensure we have session metrics, creating if needed."""
    global _current_session_metrics
    if _current_session_metrics is None:
        _current_session_metrics = start_session_metrics(
            session_id or datetime.now().strftime("%Y%m%d-%H%M%S"),
            ""
        )
    return _current_session_metrics


# =============================================================================
# METRICS TRACKING - Event Handlers
# =============================================================================

def record_drift_signal(signal_type: str, severity: str) -> None:
    """Record that a drift signal was fired."""
    metrics = ensure_session_metrics()

    # Increment signal count
    current = metrics.drift.signals_fired.get(signal_type, 0)
    metrics.drift.signals_fired[signal_type] = current + 1

    # Count as intervention if warning or critical
    if severity in ("warning", "critical"):
        metrics.drift.interventions_shown += 1


def record_drift_response(course_corrected: bool) -> None:
    """Record whether Claude course-corrected after drift signal."""
    metrics = ensure_session_metrics()

    if course_corrected:
        metrics.drift.course_corrections += 1
    else:
        metrics.drift.ignored_signals += 1


def record_fix_surfaced(fix_id: str = "") -> None:
    """Record that a known fix was surfaced."""
    metrics = ensure_session_metrics()
    metrics.fixes.fixes_surfaced += 1


def record_fix_followed(success: bool = True) -> None:
    """Record that a suggested fix was followed."""
    metrics = ensure_session_metrics()
    metrics.fixes.fixes_followed += 1
    if success:
        metrics.fixes.fixes_successful += 1


def record_fix_ignored() -> None:
    """Record that a suggested fix was ignored."""
    metrics = ensure_session_metrics()
    metrics.fixes.fixes_ignored += 1


def record_fix_learned() -> None:
    """Record that a new fix was learned."""
    metrics = ensure_session_metrics()
    metrics.fixes.new_fixes_learned += 1


def record_handoff_generated() -> None:
    """Record that a handoff was generated."""
    metrics = ensure_session_metrics()
    metrics.handoff.handoff_generated = True


def record_handoff_used(time_to_first_action: float = 0.0) -> None:
    """Record that a previous handoff was used."""
    metrics = ensure_session_metrics()
    metrics.handoff.previous_handoff_available = True
    metrics.handoff.previous_handoff_used = True
    metrics.handoff.time_to_first_action_seconds = time_to_first_action


def record_handoff_available_but_not_used() -> None:
    """Record that handoff was available but not used."""
    metrics = ensure_session_metrics()
    metrics.handoff.previous_handoff_available = True
    metrics.handoff.previous_handoff_used = False


def record_context_usage(usage_percent: float, recommended_compression: bool = False) -> None:
    """Record context usage checkpoint."""
    global _peak_context_usage
    metrics = ensure_session_metrics()

    # Update peak
    if usage_percent > _peak_context_usage:
        _peak_context_usage = usage_percent
        metrics.context.peak_usage_percent = usage_percent

    # Track compression recommendations
    if recommended_compression:
        metrics.context.compression_recommendations += 1


def record_compression_performed() -> None:
    """Record that context compression was performed."""
    metrics = ensure_session_metrics()
    metrics.context.compressions_performed += 1


def update_context_metrics(
    duration_minutes: float,
    tool_calls: int,
    files_read: int,
    files_modified: int,
    final_usage: float
) -> None:
    """Update context metrics at session end."""
    metrics = ensure_session_metrics()
    metrics.context.session_duration_minutes = duration_minutes
    metrics.context.tool_calls_total = tool_calls
    metrics.context.files_read = files_read
    metrics.context.files_modified = files_modified
    metrics.context.final_usage_percent = final_usage


def update_objective_metrics(completed: bool, steps_done: int, steps_total: int) -> None:
    """Update objective completion metrics."""
    metrics = ensure_session_metrics()
    metrics.objective_completed = completed
    metrics.steps_completed = steps_done
    metrics.steps_total = steps_total


# =============================================================================
# METRICS PERSISTENCE
# =============================================================================

def save_session_metrics() -> Optional[Path]:
    """Save current session metrics to disk."""
    global _current_session_metrics

    if _current_session_metrics is None:
        return None

    _current_session_metrics.ended_at = datetime.now().isoformat()

    # Load existing metrics
    all_metrics = _load_all_metrics()

    # Add current session
    all_metrics["sessions"][_current_session_metrics.session_id] = _current_session_metrics.to_dict()

    # Cleanup old sessions
    all_metrics = _cleanup_old_metrics(all_metrics)

    # Save
    if _save_all_metrics(all_metrics):
        return _get_metrics_path()
    return None


def load_session_metrics(session_id: str) -> Optional[SessionMetrics]:
    """Load metrics for a specific session."""
    all_metrics = _load_all_metrics()
    session_data = all_metrics.get("sessions", {}).get(session_id)

    if session_data:
        return SessionMetrics.from_dict(session_data)
    return None


def get_recent_sessions(limit: int = 10) -> List[SessionMetrics]:
    """Get metrics for recent sessions."""
    all_metrics = _load_all_metrics()
    sessions = all_metrics.get("sessions", {})

    # Sort by started_at descending
    sorted_sessions = sorted(
        sessions.values(),
        key=lambda x: x.get("started_at", ""),
        reverse=True
    )

    return [SessionMetrics.from_dict(s) for s in sorted_sessions[:limit]]


# =============================================================================
# METRICS AGGREGATION
# =============================================================================

@dataclass
class AggregatedMetrics:
    """Aggregated metrics across multiple sessions."""
    sessions_analyzed: int = 0

    # Drift effectiveness
    total_drift_signals: int = 0
    total_course_corrections: int = 0
    drift_effectiveness_rate: float = 0.0  # corrections / signals

    # Fix effectiveness
    total_fixes_surfaced: int = 0
    total_fixes_followed: int = 0
    fix_follow_rate: float = 0.0
    fix_success_rate: float = 0.0

    # Handoff effectiveness
    handoffs_generated: int = 0
    handoffs_used: int = 0
    handoff_adoption_rate: float = 0.0
    avg_time_to_first_action: float = 0.0

    # Context efficiency
    avg_context_usage: float = 0.0
    avg_session_duration: float = 0.0
    compression_recommendation_rate: float = 0.0

    # Objective completion
    objectives_completed: int = 0
    completion_rate: float = 0.0
    avg_steps_per_session: float = 0.0

    def to_dict(self) -> dict:
        return {
            "sessions_analyzed": self.sessions_analyzed,
            "drift": {
                "total_signals": self.total_drift_signals,
                "total_corrections": self.total_course_corrections,
                "effectiveness_rate": round(self.drift_effectiveness_rate * 100, 1),
            },
            "fixes": {
                "total_surfaced": self.total_fixes_surfaced,
                "total_followed": self.total_fixes_followed,
                "follow_rate": round(self.fix_follow_rate * 100, 1),
                "success_rate": round(self.fix_success_rate * 100, 1),
            },
            "handoff": {
                "generated": self.handoffs_generated,
                "used": self.handoffs_used,
                "adoption_rate": round(self.handoff_adoption_rate * 100, 1),
                "avg_time_to_first_action": round(self.avg_time_to_first_action, 1),
            },
            "context": {
                "avg_usage": round(self.avg_context_usage, 1),
                "avg_duration_minutes": round(self.avg_session_duration, 1),
                "compression_rate": round(self.compression_recommendation_rate * 100, 1),
            },
            "objectives": {
                "completed": self.objectives_completed,
                "completion_rate": round(self.completion_rate * 100, 1),
                "avg_steps": round(self.avg_steps_per_session, 1),
            },
        }


def aggregate_metrics(sessions: List[SessionMetrics]) -> AggregatedMetrics:
    """Aggregate metrics across multiple sessions."""
    if not sessions:
        return AggregatedMetrics()

    agg = AggregatedMetrics(sessions_analyzed=len(sessions))

    # Drift
    for s in sessions:
        agg.total_drift_signals += sum(s.drift.signals_fired.values())
        agg.total_course_corrections += s.drift.course_corrections

    if agg.total_drift_signals > 0:
        agg.drift_effectiveness_rate = agg.total_course_corrections / agg.total_drift_signals

    # Fixes
    for s in sessions:
        agg.total_fixes_surfaced += s.fixes.fixes_surfaced
        agg.total_fixes_followed += s.fixes.fixes_followed

    if agg.total_fixes_surfaced > 0:
        agg.fix_follow_rate = agg.total_fixes_followed / agg.total_fixes_surfaced

    fixes_successful = sum(s.fixes.fixes_successful for s in sessions)
    if agg.total_fixes_followed > 0:
        agg.fix_success_rate = fixes_successful / agg.total_fixes_followed

    # Handoff
    for s in sessions:
        if s.handoff.handoff_generated:
            agg.handoffs_generated += 1
        if s.handoff.previous_handoff_used:
            agg.handoffs_used += 1

    handoffs_available = sum(1 for s in sessions if s.handoff.previous_handoff_available)
    if handoffs_available > 0:
        agg.handoff_adoption_rate = agg.handoffs_used / handoffs_available

    times_to_action = [s.handoff.time_to_first_action_seconds for s in sessions if s.handoff.time_to_first_action_seconds > 0]
    if times_to_action:
        agg.avg_time_to_first_action = sum(times_to_action) / len(times_to_action)

    # Context
    context_usages = [s.context.peak_usage_percent for s in sessions if s.context.peak_usage_percent > 0]
    if context_usages:
        agg.avg_context_usage = sum(context_usages) / len(context_usages)

    durations = [s.context.session_duration_minutes for s in sessions if s.context.session_duration_minutes > 0]
    if durations:
        agg.avg_session_duration = sum(durations) / len(durations)

    compression_recs = sum(s.context.compression_recommendations for s in sessions)
    if len(sessions) > 0:
        agg.compression_recommendation_rate = compression_recs / len(sessions)

    # Objectives
    for s in sessions:
        if s.objective_completed:
            agg.objectives_completed += 1

    if len(sessions) > 0:
        agg.completion_rate = agg.objectives_completed / len(sessions)

    steps = [s.steps_completed for s in sessions]
    if steps:
        agg.avg_steps_per_session = sum(steps) / len(steps)

    return agg


# =============================================================================
# METRICS FORMATTING
# =============================================================================

def format_session_summary(metrics: SessionMetrics) -> str:
    """Format a single session's metrics for display."""
    lines = [
        f"📊 **Session Metrics** ({metrics.session_id})",
        "",
        f"**Objective:** {metrics.objective or 'Not set'}",
        f"**Progress:** {metrics.steps_completed}/{metrics.steps_total} steps",
        f"**Completed:** {'✓' if metrics.objective_completed else '○'}",
        "",
    ]

    # Drift
    if metrics.drift.interventions_shown > 0:
        lines.append(f"**Drift Detection:**")
        lines.append(f"  - Signals fired: {sum(metrics.drift.signals_fired.values())}")
        lines.append(f"  - Course corrections: {metrics.drift.course_corrections}")
        lines.append("")

    # Fixes
    if metrics.fixes.fixes_surfaced > 0:
        lines.append(f"**Known Fixes:**")
        lines.append(f"  - Surfaced: {metrics.fixes.fixes_surfaced}")
        lines.append(f"  - Followed: {metrics.fixes.fixes_followed}")
        lines.append(f"  - Successful: {metrics.fixes.fixes_successful}")
        lines.append("")

    # Context
    lines.append(f"**Context:**")
    lines.append(f"  - Duration: {metrics.context.session_duration_minutes:.0f} min")
    lines.append(f"  - Peak usage: {metrics.context.peak_usage_percent:.0f}%")
    lines.append(f"  - Tool calls: {metrics.context.tool_calls_total}")
    lines.append("")

    return "\n".join(lines)


def format_aggregated_summary(agg: AggregatedMetrics) -> str:
    """Format aggregated metrics for display."""
    lines = [
        "=" * 60,
        "📈 **v8.0 EFFECTIVENESS REPORT**",
        "=" * 60,
        "",
        f"Sessions analyzed: {agg.sessions_analyzed}",
        "",
        "**Drift Detection:**",
        f"  - Total signals: {agg.total_drift_signals}",
        f"  - Course corrections: {agg.total_course_corrections}",
        f"  - Effectiveness: {agg.drift_effectiveness_rate*100:.0f}%",
        "",
        "**Codebase Knowledge:**",
        f"  - Fixes surfaced: {agg.total_fixes_surfaced}",
        f"  - Follow rate: {agg.fix_follow_rate*100:.0f}%",
        f"  - Success rate: {agg.fix_success_rate*100:.0f}%",
        "",
        "**Session Handoff:**",
        f"  - Generated: {agg.handoffs_generated}",
        f"  - Adoption rate: {agg.handoff_adoption_rate*100:.0f}%",
        f"  - Avg time to action: {agg.avg_time_to_first_action:.0f}s",
        "",
        "**Context Efficiency:**",
        f"  - Avg usage: {agg.avg_context_usage:.0f}%",
        f"  - Avg duration: {agg.avg_session_duration:.0f} min",
        "",
        "**Objectives:**",
        f"  - Completion rate: {agg.completion_rate*100:.0f}%",
        f"  - Avg steps/session: {agg.avg_steps_per_session:.1f}",
        "",
        "=" * 60,
    ]

    return "\n".join(lines)


# =============================================================================
# QUICK TEST
# =============================================================================

if __name__ == "__main__":
    print("Session Metrics - Self Test")
    print("=" * 40)

    # Test session metrics creation
    metrics = start_session_metrics("test-session", "Test objective")
    print(f"Created session: {metrics.session_id}")

    # Record some events
    record_drift_signal("FILE_CHURN", "warning")
    record_drift_signal("COMMAND_REPEAT", "critical")
    record_drift_response(True)  # Course corrected

    record_fix_surfaced()
    record_fix_followed(success=True)
    record_fix_learned()

    record_context_usage(45.0, recommended_compression=False)
    record_context_usage(70.0, recommended_compression=False)
    record_context_usage(80.0, recommended_compression=True)

    update_context_metrics(
        duration_minutes=30,
        tool_calls=50,
        files_read=15,
        files_modified=8,
        final_usage=75.0
    )

    update_objective_metrics(completed=True, steps_done=5, steps_total=7)
    record_handoff_generated()

    # Print summary
    metrics = get_current_metrics()
    if metrics:
        print(format_session_summary(metrics))

    # Test aggregation
    print("\n--- Aggregation Test ---")
    agg = aggregate_metrics([metrics])
    print(format_aggregated_summary(agg))

    print()
    print("Self-test complete.")
