#!/usr/bin/env python3
"""
Operator's Edge v6.0 - Pattern Metrics
Measure the impact of decision-time pattern surfacing.

Metrics tracked:
1. Pattern surface events (when, what, confidence)
2. Edit outcomes (success/failure with/without patterns)
3. Reinforcement history (graduation velocity)
4. Session efficiency (steps, blocks, mismatches)
"""
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional
import json
import os
from pathlib import Path


@dataclass
class PatternSurfaceEvent:
    """Record of a pattern being surfaced."""
    timestamp: str
    file_path: str
    context: str
    patterns_count: int
    pattern_types: List[str]
    confidence_levels: List[str]
    objective: str = ""
    step_description: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "timestamp": self.timestamp,
            "file_path": self.file_path,
            "context": self.context[:100],
            "patterns_count": self.patterns_count,
            "pattern_types": self.pattern_types,
            "confidence_levels": self.confidence_levels,
            "objective": self.objective[:50],
            "step_description": self.step_description[:50],
        }


@dataclass
class EditOutcomeEvent:
    """Record of an edit outcome for correlation analysis."""
    timestamp: str
    file_path: str
    success: bool
    patterns_shown: int
    patterns_reinforced: int

    def to_dict(self) -> Dict[str, Any]:
        return {
            "timestamp": self.timestamp,
            "file_path": self.file_path,
            "success": self.success,
            "patterns_shown": self.patterns_shown,
            "patterns_reinforced": self.patterns_reinforced,
        }


def get_metrics_file() -> Path:
    """Get the path to the metrics file."""
    proof_dir = Path(os.environ.get("CLAUDE_PROJECT_DIR", ".")) / ".proof"
    proof_dir.mkdir(exist_ok=True)
    return proof_dir / "pattern_metrics.jsonl"


def log_pattern_surface(
    file_path: str,
    context: str,
    patterns: List[Any],
    objective: str = "",
    step_description: str = ""
) -> None:
    """Log a pattern surface event."""
    event = PatternSurfaceEvent(
        timestamp=datetime.now().isoformat(),
        file_path=file_path,
        context=context,
        patterns_count=len(patterns),
        pattern_types=[p.type.value for p in patterns],
        confidence_levels=[p.confidence for p in patterns],
        objective=objective,
        step_description=step_description,
    )

    try:
        metrics_file = get_metrics_file()
        with open(metrics_file, "a") as f:
            f.write(json.dumps({"type": "surface", **event.to_dict()}) + "\n")
    except Exception:
        pass  # Don't fail if metrics can't be written


def log_edit_outcome(
    file_path: str,
    success: bool,
    patterns_shown: int,
    patterns_reinforced: int
) -> None:
    """Log an edit outcome event."""
    event = EditOutcomeEvent(
        timestamp=datetime.now().isoformat(),
        file_path=file_path,
        success=success,
        patterns_shown=patterns_shown,
        patterns_reinforced=patterns_reinforced,
    )

    try:
        metrics_file = get_metrics_file()
        with open(metrics_file, "a") as f:
            f.write(json.dumps({"type": "outcome", **event.to_dict()}) + "\n")
    except Exception:
        pass


def load_metrics() -> List[Dict[str, Any]]:
    """Load all metrics events."""
    metrics_file = get_metrics_file()
    if not metrics_file.exists():
        return []

    events = []
    try:
        with open(metrics_file) as f:
            for line in f:
                line = line.strip()
                if line:
                    events.append(json.loads(line))
    except Exception:
        pass

    return events


def compute_metrics_summary() -> Dict[str, Any]:
    """Compute summary statistics from metrics."""
    events = load_metrics()

    if not events:
        return {
            "status": "no_data",
            "message": "No metrics collected yet",
        }

    # Separate event types
    surface_events = [e for e in events if e.get("type") == "surface"]
    outcome_events = [e for e in events if e.get("type") == "outcome"]

    # 1. Pattern Surface Rate
    surface_rate = {
        "total_surfaces": len(surface_events),
        "avg_patterns_per_surface": (
            sum(e.get("patterns_count", 0) for e in surface_events) / len(surface_events)
            if surface_events else 0
        ),
    }

    # 2. Pattern Relevance (confidence distribution)
    all_confidences = []
    for e in surface_events:
        all_confidences.extend(e.get("confidence_levels", []))

    relevance = {
        "total_patterns_surfaced": len(all_confidences),
        "high_confidence": all_confidences.count("high"),
        "medium_confidence": all_confidences.count("medium"),
        "low_confidence": all_confidences.count("low"),
        "high_confidence_rate": (
            all_confidences.count("high") / len(all_confidences)
            if all_confidences else 0
        ),
    }

    # 3. Edit Success Rate (with vs without patterns)
    edits_with_patterns = [e for e in outcome_events if e.get("patterns_shown", 0) > 0]
    edits_without_patterns = [e for e in outcome_events if e.get("patterns_shown", 0) == 0]

    success_with = sum(1 for e in edits_with_patterns if e.get("success", False))
    success_without = sum(1 for e in edits_without_patterns if e.get("success", False))

    edit_success = {
        "total_edits": len(outcome_events),
        "edits_with_patterns": len(edits_with_patterns),
        "edits_without_patterns": len(edits_without_patterns),
        "success_rate_with_patterns": (
            success_with / len(edits_with_patterns)
            if edits_with_patterns else None
        ),
        "success_rate_without_patterns": (
            success_without / len(edits_without_patterns)
            if edits_without_patterns else None
        ),
    }

    # 4. Pattern Types Distribution
    all_types = []
    for e in surface_events:
        all_types.extend(e.get("pattern_types", []))

    type_distribution = {}
    for t in set(all_types):
        type_distribution[t] = all_types.count(t)

    return {
        "status": "ok",
        "collection_period": {
            "first_event": events[0].get("timestamp") if events else None,
            "last_event": events[-1].get("timestamp") if events else None,
            "total_events": len(events),
        },
        "surface_rate": surface_rate,
        "relevance": relevance,
        "edit_success": edit_success,
        "pattern_types": type_distribution,
    }


def format_metrics_report(summary: Dict[str, Any]) -> str:
    """Format metrics summary as a readable report."""
    if summary.get("status") == "no_data":
        return "📊 **Pattern Metrics**: No data collected yet."

    lines = ["### 📊 Pattern Impact Metrics", ""]

    # Collection period
    period = summary.get("collection_period", {})
    lines.append(f"**Data Collection**: {period.get('total_events', 0)} events")
    if period.get("first_event"):
        lines.append(f"  From: {period['first_event'][:10]} to {period['last_event'][:10]}")
    lines.append("")

    # Surface Rate
    sr = summary.get("surface_rate", {})
    lines.append(f"**Pattern Surfacing**:")
    lines.append(f"  - Total surface events: {sr.get('total_surfaces', 0)}")
    lines.append(f"  - Avg patterns per event: {sr.get('avg_patterns_per_surface', 0):.1f}")
    lines.append("")

    # Relevance
    rel = summary.get("relevance", {})
    if rel.get("total_patterns_surfaced", 0) > 0:
        lines.append(f"**Pattern Relevance**:")
        lines.append(f"  - High confidence: {rel.get('high_confidence', 0)} ({rel.get('high_confidence_rate', 0):.0%})")
        lines.append(f"  - Medium confidence: {rel.get('medium_confidence', 0)}")
        lines.append(f"  - Low confidence: {rel.get('low_confidence', 0)}")
        lines.append("")

    # Edit Success Correlation
    es = summary.get("edit_success", {})
    if es.get("total_edits", 0) > 0:
        lines.append(f"**Edit Success Correlation**:")
        lines.append(f"  - Total edits tracked: {es.get('total_edits', 0)}")

        with_rate = es.get("success_rate_with_patterns")
        without_rate = es.get("success_rate_without_patterns")

        if with_rate is not None:
            lines.append(f"  - With patterns: {es.get('edits_with_patterns', 0)} edits, {with_rate:.0%} success")
        if without_rate is not None:
            lines.append(f"  - Without patterns: {es.get('edits_without_patterns', 0)} edits, {without_rate:.0%} success")

        if with_rate is not None and without_rate is not None:
            diff = with_rate - without_rate
            if diff > 0.05:
                lines.append(f"  - 📈 Patterns correlated with +{diff:.0%} success rate")
            elif diff < -0.05:
                lines.append(f"  - 📉 Patterns correlated with {diff:.0%} success rate")
            else:
                lines.append(f"  - ➡️ No significant correlation detected")
        lines.append("")

    # Pattern Types
    types = summary.get("pattern_types", {})
    if types:
        lines.append(f"**Pattern Types Used**:")
        for t, count in sorted(types.items(), key=lambda x: x[1], reverse=True):
            lines.append(f"  - {t}: {count}")

    return "\n".join(lines)


# =============================================================================
# LESSON LIFECYCLE METRICS
# =============================================================================

def compute_lesson_metrics(state: Dict[str, Any]) -> Dict[str, Any]:
    """Compute metrics about lesson lifecycle and graduation."""
    memory = state.get("memory", [])

    if not memory:
        return {"status": "no_lessons"}

    # Lifecycle distribution
    from pattern_engine import get_lesson_lifecycle_stage

    lifecycle_counts = {"new": 0, "established": 0, "graduated": 0, "evergreen": 0}
    reinforcement_values = []

    for m in memory:
        if isinstance(m, dict):
            stage = get_lesson_lifecycle_stage(m)
            lifecycle_counts[stage] = lifecycle_counts.get(stage, 0) + 1
            reinforcement_values.append(m.get("reinforced", 0))

    return {
        "status": "ok",
        "total_lessons": len(memory),
        "lifecycle_distribution": lifecycle_counts,
        "reinforcement_stats": {
            "min": min(reinforcement_values) if reinforcement_values else 0,
            "max": max(reinforcement_values) if reinforcement_values else 0,
            "avg": sum(reinforcement_values) / len(reinforcement_values) if reinforcement_values else 0,
        },
        "graduation_rate": (
            lifecycle_counts["graduated"] / len(memory)
            if memory else 0
        ),
    }


def format_lesson_metrics(metrics: Dict[str, Any]) -> str:
    """Format lesson metrics as readable report."""
    if metrics.get("status") == "no_lessons":
        return "📚 **Lesson Metrics**: No lessons in memory."

    lines = ["### 📚 Lesson Lifecycle Metrics", ""]

    lines.append(f"**Total Lessons**: {metrics.get('total_lessons', 0)}")
    lines.append("")

    # Lifecycle distribution
    lc = metrics.get("lifecycle_distribution", {})
    lines.append("**Lifecycle Distribution**:")
    lines.append(f"  - 🌱 New (learning): {lc.get('new', 0)}")
    lines.append(f"  - 🌿 Established (proven): {lc.get('established', 0)}")
    lines.append(f"  - 🎓 Graduated (internalized): {lc.get('graduated', 0)}")
    lines.append(f"  - 🌲 Evergreen (always relevant): {lc.get('evergreen', 0)}")
    lines.append("")

    # Reinforcement stats
    rs = metrics.get("reinforcement_stats", {})
    lines.append("**Reinforcement Stats**:")
    lines.append(f"  - Average: {rs.get('avg', 0):.1f}")
    lines.append(f"  - Range: {rs.get('min', 0)} - {rs.get('max', 0)}")
    lines.append("")

    # Graduation rate
    grad_rate = metrics.get("graduation_rate", 0)
    if grad_rate > 0.3:
        lines.append(f"📈 **Graduation Rate**: {grad_rate:.0%} (high retention)")
    elif grad_rate > 0.1:
        lines.append(f"➡️ **Graduation Rate**: {grad_rate:.0%} (moderate)")
    else:
        lines.append(f"🌱 **Graduation Rate**: {grad_rate:.0%} (still learning)")

    return "\n".join(lines)


if __name__ == "__main__":
    # Demo
    summary = compute_metrics_summary()
    print(format_metrics_report(summary))
