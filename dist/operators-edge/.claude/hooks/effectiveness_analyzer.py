#!/usr/bin/env python3
"""
Operator's Edge v8.0 - Effectiveness Analyzer (Phase 7 + Phase 9)

The Brain: Answers the question "Is v8.0 actually helping?"

This module analyzes session data to determine:
1. Are drift signals leading to behavior changes?
2. Are suggested fixes being followed?
3. Are handoffs improving session starts?
4. Is context being used efficiently?
5. [Phase 9] Are fixes actually working when followed?

Design Philosophy:
- Inference over instrumentation (work with existing data)
- Confidence-weighted conclusions
- Actionable recommendations
- [Phase 9] Closed-loop outcome tracking

"The only way to do great work is to love what you do." - Steve Jobs
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
# DATA STRUCTURES
# =============================================================================

@dataclass
class EffectivenessMetric:
    """A single effectiveness measurement with confidence."""
    value: float  # 0.0 to 1.0
    sample_size: int
    confidence: float  # 0.0 to 1.0, based on sample size
    trend: str = "stable"  # "improving", "stable", "declining"

    @property
    def display_value(self) -> str:
        """Format value as percentage."""
        return f"{self.value * 100:.0f}%"

    @property
    def bar(self) -> str:
        """Visual bar representation (10 chars)."""
        filled = int(self.value * 10)
        return "█" * filled + "░" * (10 - filled)


@dataclass
class EffectivenessReport:
    """Complete effectiveness analysis."""
    # Core metrics
    drift_effectiveness: EffectivenessMetric
    fix_hit_rate: EffectivenessMetric
    handoff_adoption: EffectivenessMetric
    context_efficiency: EffectivenessMetric

    # Summary stats
    sessions_analyzed: int = 0
    time_range_days: int = 7
    avg_session_duration_min: float = 0.0
    avg_drift_signals_per_session: float = 0.0

    # Phase 9: Fix outcome details (closed-loop tracking)
    fix_outcome_details: Dict[str, Any] = field(default_factory=dict)

    # Recommendations
    recommendations: List[str] = field(default_factory=list)
    threshold_adjustments: Dict[str, float] = field(default_factory=dict)

    # Meta
    generated_at: str = ""
    overall_confidence: float = 0.0

    def to_dict(self) -> dict:
        return {
            "drift_effectiveness": {
                "value": self.drift_effectiveness.value,
                "sample_size": self.drift_effectiveness.sample_size,
                "confidence": self.drift_effectiveness.confidence,
            },
            "fix_hit_rate": {
                "value": self.fix_hit_rate.value,
                "sample_size": self.fix_hit_rate.sample_size,
                "confidence": self.fix_hit_rate.confidence,
            },
            "handoff_adoption": {
                "value": self.handoff_adoption.value,
                "sample_size": self.handoff_adoption.sample_size,
                "confidence": self.handoff_adoption.confidence,
            },
            "context_efficiency": {
                "value": self.context_efficiency.value,
                "sample_size": self.context_efficiency.sample_size,
                "confidence": self.context_efficiency.confidence,
            },
            "sessions_analyzed": self.sessions_analyzed,
            "time_range_days": self.time_range_days,
            "avg_session_duration_min": self.avg_session_duration_min,
            "avg_drift_signals_per_session": self.avg_drift_signals_per_session,
            "fix_outcome_details": self.fix_outcome_details,  # Phase 9
            "recommendations": self.recommendations,
            "threshold_adjustments": self.threshold_adjustments,
            "generated_at": self.generated_at,
            "overall_confidence": self.overall_confidence,
        }


@dataclass
class SessionAnalysis:
    """Analysis of a single session."""
    session_id: str
    started_at: datetime
    duration_minutes: float

    # Drift
    drift_signals_fired: int = 0
    drift_corrections_detected: int = 0

    # Fixes
    fixes_surfaced: int = 0
    fixes_followed: int = 0

    # Handoff
    handoff_available: bool = False
    handoff_used: bool = False
    time_to_first_action_seconds: float = 0.0

    # Context
    peak_context_usage: float = 0.0
    tool_calls: int = 0
    files_modified: int = 0

    # Outcome
    objective_completed: bool = False


# =============================================================================
# SESSION LOG ANALYSIS
# =============================================================================

def load_session_entries(session_log: Path) -> List[Dict[str, Any]]:
    """Load entries from a session log file."""
    entries = []
    if not session_log.exists():
        return entries

    try:
        with open(session_log) as f:
            for line in f:
                line = line.strip()
                if line:
                    try:
                        entries.append(json.loads(line))
                    except json.JSONDecodeError:
                        continue
    except OSError:
        pass

    return entries


def analyze_session(session_log: Path) -> Optional[SessionAnalysis]:
    """
    Analyze a single session log for effectiveness metrics.

    This is where inference happens - we deduce behavior from tool patterns.
    """
    entries = load_session_entries(session_log)
    if not entries:
        return None

    # Parse session ID from filename
    session_id = session_log.stem

    # Get timestamps
    timestamps = []
    for entry in entries:
        ts_str = entry.get("timestamp", "")
        if ts_str:
            try:
                timestamps.append(datetime.fromisoformat(ts_str))
            except ValueError:
                continue

    if not timestamps:
        return None

    started_at = min(timestamps)
    ended_at = max(timestamps)
    duration_minutes = (ended_at - started_at).total_seconds() / 60

    analysis = SessionAnalysis(
        session_id=session_id,
        started_at=started_at,
        duration_minutes=duration_minutes,
        tool_calls=len(entries)
    )

    # Analyze tool patterns
    file_edit_times: Dict[str, List[datetime]] = {}
    command_patterns: Dict[str, List[datetime]] = {}

    for entry in entries:
        tool = entry.get("tool", "")
        input_data = entry.get("input_preview", {})
        success = entry.get("success", True)
        ts_str = entry.get("timestamp", "")

        try:
            ts = datetime.fromisoformat(ts_str) if ts_str else None
        except ValueError:
            ts = None

        # Track file edits
        if tool in ("Edit", "Write", "NotebookEdit"):
            file_path = ""
            if isinstance(input_data, dict):
                file_path = input_data.get("file_path") or input_data.get("file", "")
            if file_path and ts:
                if file_path not in file_edit_times:
                    file_edit_times[file_path] = []
                file_edit_times[file_path].append(ts)
                analysis.files_modified += 1

        # Track command patterns (for repeat detection)
        if tool == "Bash" and not success:
            cmd = ""
            if isinstance(input_data, dict):
                cmd = input_data.get("command", "")
            if cmd and ts:
                # Normalize command for pattern matching
                cmd_pattern = cmd.split()[0] if cmd else ""
                if cmd_pattern not in command_patterns:
                    command_patterns[cmd_pattern] = []
                command_patterns[cmd_pattern].append(ts)

    # Infer drift signals from patterns
    # FILE_CHURN: Same file edited 3+ times
    for file_path, edit_times in file_edit_times.items():
        if len(edit_times) >= 3:
            analysis.drift_signals_fired += 1
            # Check for course correction: was file edited again within 5 min of 3rd edit?
            if len(edit_times) >= 4:
                time_to_4th = (edit_times[3] - edit_times[2]).total_seconds()
                if time_to_4th > 300:  # > 5 minutes = likely paused to think
                    analysis.drift_corrections_detected += 1

    # COMMAND_REPEAT: Same command pattern failing 3+ times
    for cmd_pattern, fail_times in command_patterns.items():
        if len(fail_times) >= 3:
            analysis.drift_signals_fired += 1
            # Course correction: did a different approach follow?
            # (This is harder to detect, so we're conservative)

    # Calculate peak context usage (estimate based on tool calls)
    # Rough estimate: each tool call adds ~500 tokens average
    estimated_tokens = len(entries) * 500
    max_tokens = 200000  # Approximate Claude context
    analysis.peak_context_usage = min(1.0, estimated_tokens / max_tokens)

    return analysis


def get_session_logs(proof_dir: Path, days: int = 7) -> List[Path]:
    """Get session log files from the last N days."""
    sessions_dir = proof_dir / "sessions"
    if not sessions_dir.exists():
        return []

    cutoff = datetime.now() - timedelta(days=days)
    logs = []

    for log_file in sessions_dir.glob("*.jsonl"):
        # Parse date from filename (format: YYYYMMDD-HHMMSS.jsonl)
        try:
            date_str = log_file.stem[:8]
            file_date = datetime.strptime(date_str, "%Y%m%d")
            if file_date >= cutoff:
                logs.append(log_file)
        except ValueError:
            continue

    return sorted(logs, key=lambda p: p.stem, reverse=True)


# =============================================================================
# EFFECTIVENESS CALCULATION
# =============================================================================

def calculate_confidence(sample_size: int, min_samples: int = 5, ideal_samples: int = 30) -> float:
    """
    Calculate confidence based on sample size.

    - Below min_samples: Low confidence (0.3)
    - min_samples to ideal: Linear interpolation
    - Above ideal: High confidence (capped at 0.95)
    """
    if sample_size < min_samples:
        return 0.3
    if sample_size >= ideal_samples:
        return 0.95

    # Linear interpolation
    range_size = ideal_samples - min_samples
    progress = (sample_size - min_samples) / range_size
    return 0.3 + (0.65 * progress)


def analyze_drift_effectiveness(analyses: List[SessionAnalysis]) -> EffectivenessMetric:
    """
    Calculate how effective drift detection is.

    Effectiveness = corrections / signals
    """
    total_signals = sum(a.drift_signals_fired for a in analyses)
    total_corrections = sum(a.drift_corrections_detected for a in analyses)

    if total_signals == 0:
        # No signals fired - can't measure effectiveness
        return EffectivenessMetric(
            value=0.0,
            sample_size=0,
            confidence=0.0,
            trend="stable"
        )

    effectiveness = total_corrections / total_signals
    confidence = calculate_confidence(total_signals)

    return EffectivenessMetric(
        value=effectiveness,
        sample_size=total_signals,
        confidence=confidence,
        trend="stable"
    )


def analyze_fix_effectiveness(analyses: List[SessionAnalysis]) -> EffectivenessMetric:
    """
    Calculate fix suggestion effectiveness.

    Effectiveness = fixes_followed / fixes_surfaced

    Note: This is the LEGACY method using inference. Phase 9 adds
    analyze_fix_outcomes_from_tracking() for precise outcome data.
    """
    total_surfaced = sum(a.fixes_surfaced for a in analyses)
    total_followed = sum(a.fixes_followed for a in analyses)

    if total_surfaced == 0:
        return EffectivenessMetric(
            value=0.0,
            sample_size=0,
            confidence=0.0,
            trend="stable"
        )

    effectiveness = total_followed / total_surfaced
    confidence = calculate_confidence(total_surfaced)

    return EffectivenessMetric(
        value=effectiveness,
        sample_size=total_surfaced,
        confidence=confidence,
        trend="stable"
    )


def analyze_fix_outcomes_from_tracking(proof_dir: Path, days: int = 7) -> Tuple[EffectivenessMetric, Dict[str, Any]]:
    """
    Phase 9: Analyze fix outcomes from closed-loop tracking.

    This uses actual outcome data from fix_outcomes.py rather than inference.
    Returns (metric, details) where details includes:
    - total_surfaced: Total fixes shown to user
    - followed: Number of fixes where user ran suggested command
    - followed_success: Number of followed fixes that succeeded
    - followed_failure: Number of followed fixes that failed
    - ignored: Number of fixes user ignored (5+ unrelated commands)
    - success_rate: followed_success / followed (when followed > 0)
    """
    try:
        from fix_outcomes import analyze_fix_outcomes

        effectiveness = analyze_fix_outcomes(days=days)

        # Calculate the metric value based on overall effectiveness
        # (What % of surfaced fixes lead to successful outcomes?)
        if effectiveness.total_surfaced == 0:
            return EffectivenessMetric(
                value=0.0,
                sample_size=0,
                confidence=0.0,
                trend="stable"
            ), {}

        # Primary metric: follow rate (what % of fixes are followed)
        metric = EffectivenessMetric(
            value=effectiveness.follow_rate,
            sample_size=effectiveness.total_surfaced,
            confidence=calculate_confidence(effectiveness.total_surfaced),
            trend="stable"
        )

        details = {
            "total_surfaced": effectiveness.total_surfaced,
            "followed": effectiveness.followed,
            "followed_success": effectiveness.followed_success,
            "followed_failure": effectiveness.followed_failure,
            "ignored": effectiveness.ignored,
            "follow_rate": effectiveness.follow_rate,
            "success_rate": effectiveness.success_rate,
            "overall_effectiveness": effectiveness.overall_effectiveness,
        }

        return metric, details

    except ImportError:
        # fix_outcomes module not available
        return EffectivenessMetric(
            value=0.0,
            sample_size=0,
            confidence=0.0,
            trend="stable"
        ), {}
    except Exception:
        return EffectivenessMetric(
            value=0.0,
            sample_size=0,
            confidence=0.0,
            trend="stable"
        ), {}


def analyze_handoff_effectiveness(analyses: List[SessionAnalysis]) -> EffectivenessMetric:
    """
    Calculate handoff adoption rate.

    Effectiveness = handoffs_used / handoffs_available
    """
    available = sum(1 for a in analyses if a.handoff_available)
    used = sum(1 for a in analyses if a.handoff_used)

    if available == 0:
        return EffectivenessMetric(
            value=0.0,
            sample_size=0,
            confidence=0.0,
            trend="stable"
        )

    effectiveness = used / available
    confidence = calculate_confidence(available)

    return EffectivenessMetric(
        value=effectiveness,
        sample_size=available,
        confidence=confidence,
        trend="stable"
    )


def analyze_context_efficiency(analyses: List[SessionAnalysis]) -> EffectivenessMetric:
    """
    Calculate context efficiency.

    Efficiency is based on:
    - Lower peak context usage is better
    - More work done (files modified) per context used is better

    Score: (1 - avg_peak_usage) * 0.5 + (files/tool_calls) * 0.5
    """
    if not analyses:
        return EffectivenessMetric(
            value=0.0,
            sample_size=0,
            confidence=0.0,
            trend="stable"
        )

    # Average peak usage (lower is better, so invert)
    avg_peak = sum(a.peak_context_usage for a in analyses) / len(analyses)
    context_score = 1 - avg_peak

    # Work efficiency (files modified per 100 tool calls)
    total_files = sum(a.files_modified for a in analyses)
    total_calls = sum(a.tool_calls for a in analyses)
    work_score = min(1.0, (total_files / max(total_calls, 1)) * 10)

    # Combined score
    efficiency = context_score * 0.6 + work_score * 0.4
    confidence = calculate_confidence(len(analyses))

    return EffectivenessMetric(
        value=efficiency,
        sample_size=len(analyses),
        confidence=confidence,
        trend="stable"
    )


# =============================================================================
# RECOMMENDATION ENGINE
# =============================================================================

def generate_recommendations(
    drift: EffectivenessMetric,
    fix: EffectivenessMetric,
    handoff: EffectivenessMetric,
    context: EffectivenessMetric,
    current_thresholds: Dict[str, float]
) -> Tuple[List[str], Dict[str, float]]:
    """
    Generate actionable recommendations and threshold adjustments.

    Returns (recommendations, threshold_adjustments)
    """
    recommendations = []
    adjustments = {}

    # Drift recommendations
    if drift.confidence >= 0.5:
        if drift.value >= 0.8:
            recommendations.append("✓ Drift detection working well")
        elif drift.value >= 0.5:
            # Signals fire but only half lead to corrections
            # Maybe signals are too sensitive?
            current_churn = current_thresholds.get("file_churn", 3)
            if current_churn <= 3:
                recommendations.append("Consider raising FILE_CHURN threshold (many ignored signals)")
                adjustments["file_churn"] = current_churn + 1
        else:
            # Low effectiveness - signals may be too late
            current_churn = current_thresholds.get("file_churn", 3)
            recommendations.append("Drift signals may fire too late - consider lowering threshold")
            adjustments["file_churn"] = max(2, current_churn - 1)
    else:
        recommendations.append("⚠ Not enough data for drift analysis")

    # Fix recommendations
    if fix.confidence >= 0.5:
        if fix.value >= 0.7:
            recommendations.append("✓ Fix suggestions being followed")
            # High success = could lower confidence threshold
            current_conf = current_thresholds.get("auto_fix_confidence", 0.6)
            if current_conf > 0.5:
                recommendations.append("📈 Could lower auto_fix confidence threshold (high success)")
                adjustments["auto_fix_confidence"] = max(0.4, current_conf - 0.1)
        elif fix.value >= 0.4:
            recommendations.append("Fix suggestions moderately effective")
        else:
            recommendations.append("⚠ Fix suggestions rarely followed - review quality")

    # Handoff recommendations
    if handoff.confidence >= 0.5:
        if handoff.value >= 0.8:
            recommendations.append("✓ Handoffs well-adopted")
        elif handoff.value >= 0.5:
            recommendations.append("Handoff adoption could improve - check handoff content quality")
        else:
            recommendations.append("⚠ Low handoff adoption - sessions may not benefit from continuity")

    # Context recommendations
    if context.confidence >= 0.5:
        if context.value >= 0.7:
            recommendations.append("✓ Context being used efficiently")
        elif context.value >= 0.5:
            current_checkpoint = current_thresholds.get("context_checkpoint", 0.75)
            if current_checkpoint > 0.70:
                recommendations.append("Consider earlier checkpoint warnings")
                adjustments["context_checkpoint"] = 0.70
        else:
            recommendations.append("⚠ Context usage inefficient - consider more aggressive checkpoints")
            adjustments["context_checkpoint"] = 0.65

    return recommendations, adjustments


# =============================================================================
# MAIN ANALYSIS
# =============================================================================

def generate_effectiveness_report(
    proof_dir: Path,
    days: int = 7,
    current_thresholds: Optional[Dict[str, float]] = None
) -> EffectivenessReport:
    """
    Generate a complete effectiveness report.

    This is the main entry point for the metrics CLI.
    """
    if current_thresholds is None:
        current_thresholds = {
            "file_churn": 3,
            "command_repeat": 2,
            "context_checkpoint": 0.75,
            "auto_fix_confidence": 0.6,
        }

    # Get session logs
    session_logs = get_session_logs(proof_dir, days)

    # Analyze each session
    analyses = []
    for log_path in session_logs:
        analysis = analyze_session(log_path)
        if analysis:
            analyses.append(analysis)

    # Calculate metrics
    drift = analyze_drift_effectiveness(analyses)
    handoff = analyze_handoff_effectiveness(analyses)
    context = analyze_context_efficiency(analyses)

    # Phase 9: Try closed-loop fix outcome tracking first
    fix, fix_details = analyze_fix_outcomes_from_tracking(proof_dir, days)

    # Fall back to inference-based analysis if no tracking data
    if fix.sample_size == 0:
        fix = analyze_fix_effectiveness(analyses)
        fix_details = {}

    # Generate recommendations
    recommendations, adjustments = generate_recommendations(
        drift, fix, handoff, context, current_thresholds
    )

    # Summary stats
    avg_duration = sum(a.duration_minutes for a in analyses) / len(analyses) if analyses else 0
    total_signals = sum(a.drift_signals_fired for a in analyses)
    avg_signals = total_signals / len(analyses) if analyses else 0

    # Overall confidence (weighted average)
    confidences = [drift.confidence, fix.confidence, handoff.confidence, context.confidence]
    overall_confidence = sum(confidences) / len(confidences) if confidences else 0

    return EffectivenessReport(
        drift_effectiveness=drift,
        fix_hit_rate=fix,
        handoff_adoption=handoff,
        context_efficiency=context,
        sessions_analyzed=len(analyses),
        time_range_days=days,
        avg_session_duration_min=avg_duration,
        avg_drift_signals_per_session=avg_signals,
        fix_outcome_details=fix_details,  # Phase 9
        recommendations=recommendations,
        threshold_adjustments=adjustments,
        generated_at=datetime.now().isoformat(),
        overall_confidence=overall_confidence,
    )


# =============================================================================
# FORMATTING
# =============================================================================

def format_compact_report(report: EffectivenessReport) -> str:
    """
    Format a compact, beautiful report for terminal display.

    Design: Clean, informative, no clutter.
    """
    lines = [
        "",
        "📊 v8.0 EFFECTIVENESS " + f"(Last {report.time_range_days} days)",
        "━" * 50,
        "",
    ]

    # Core metrics with visual bars
    metrics = [
        ("DRIFT DETECTION", report.drift_effectiveness),
        ("KNOWN FIX SUGGESTIONS", report.fix_hit_rate),
        ("SESSION HANDOFFS", report.handoff_adoption),
        ("CONTEXT EFFICIENCY", report.context_efficiency),
    ]

    for name, metric in metrics:
        if metric.sample_size > 0:
            lines.append(f"   {name:24} {metric.bar}  {metric.display_value}")
        else:
            lines.append(f"   {name:24} {'░' * 10}  --")

    # Phase 9: Add fix outcome breakdown if available
    if report.fix_outcome_details:
        details = report.fix_outcome_details
        if details.get("total_surfaced", 0) > 0:
            lines.append("")
            lines.append("📈 FIX OUTCOMES (Phase 9)")
            total = details["total_surfaced"]
            followed = details.get("followed", 0)
            success = details.get("followed_success", 0)
            ignored = details.get("ignored", 0)
            success_rate = details.get("success_rate", 0)

            lines.append(f"   Surfaced: {total}  Followed: {followed}  Ignored: {ignored}")
            if followed > 0:
                lines.append(f"   Success when followed: {success}/{followed} ({success_rate*100:.0f}%)")

    # Recommendations
    if report.recommendations:
        lines.append("")
        lines.append("🔧 INSIGHTS")
        for rec in report.recommendations[:5]:  # Limit to top 5
            lines.append(f"   {rec}")

    # Footer
    lines.append("")
    lines.append(f"{report.sessions_analyzed} sessions • {report.avg_session_duration_min:.0f} min avg • {report.avg_drift_signals_per_session:.1f} signals/session")
    lines.append("")

    return "\n".join(lines)


def format_detailed_report(report: EffectivenessReport) -> str:
    """Format a detailed report with all metrics."""
    lines = [
        "",
        "=" * 60,
        "📊 v8.0 EFFECTIVENESS REPORT (DETAILED)",
        "=" * 60,
        "",
        f"Generated: {report.generated_at}",
        f"Sessions Analyzed: {report.sessions_analyzed}",
        f"Time Range: Last {report.time_range_days} days",
        f"Overall Confidence: {report.overall_confidence * 100:.0f}%",
        "",
        "-" * 60,
        "DRIFT DETECTION",
        "-" * 60,
        f"  Effectiveness: {report.drift_effectiveness.display_value}",
        f"  Sample Size: {report.drift_effectiveness.sample_size} signals",
        f"  Confidence: {report.drift_effectiveness.confidence * 100:.0f}%",
        "",
        "-" * 60,
        "KNOWN FIX SUGGESTIONS",
        "-" * 60,
        f"  Follow Rate: {report.fix_hit_rate.display_value}",
        f"  Sample Size: {report.fix_hit_rate.sample_size} fixes",
        f"  Confidence: {report.fix_hit_rate.confidence * 100:.0f}%",
    ]

    # Phase 9: Add detailed fix outcome breakdown
    if report.fix_outcome_details:
        details = report.fix_outcome_details
        if details.get("total_surfaced", 0) > 0:
            lines.extend([
                "",
                "  --- Phase 9 Closed-Loop Tracking ---",
                f"  Total Surfaced: {details['total_surfaced']}",
                f"  Followed: {details.get('followed', 0)} ({details.get('follow_rate', 0)*100:.0f}%)",
                f"    - Success: {details.get('followed_success', 0)}",
                f"    - Failure: {details.get('followed_failure', 0)}",
                f"  Ignored: {details.get('ignored', 0)}",
                f"  Success Rate (when followed): {details.get('success_rate', 0)*100:.0f}%",
                f"  Overall Effectiveness: {details.get('overall_effectiveness', 0)*100:.0f}%",
            ])

    lines.extend([
        "",
        "-" * 60,
        "SESSION HANDOFFS",
        "-" * 60,
        f"  Adoption Rate: {report.handoff_adoption.display_value}",
        f"  Sample Size: {report.handoff_adoption.sample_size} handoffs",
        f"  Confidence: {report.handoff_adoption.confidence * 100:.0f}%",
        "",
        "-" * 60,
        "CONTEXT EFFICIENCY",
        "-" * 60,
        f"  Efficiency Score: {report.context_efficiency.display_value}",
        f"  Avg Session Duration: {report.avg_session_duration_min:.1f} min",
        f"  Avg Drift Signals: {report.avg_drift_signals_per_session:.1f}/session",
        "",
    ])

    if report.recommendations:
        lines.extend([
            "-" * 60,
            "RECOMMENDATIONS",
            "-" * 60,
        ])
        for rec in report.recommendations:
            lines.append(f"  • {rec}")
        lines.append("")

    if report.threshold_adjustments:
        lines.extend([
            "-" * 60,
            "SUGGESTED THRESHOLD ADJUSTMENTS",
            "-" * 60,
        ])
        for key, value in report.threshold_adjustments.items():
            lines.append(f"  {key}: {value}")
        lines.append("")

    lines.append("=" * 60)

    return "\n".join(lines)


# =============================================================================
# QUICK TEST
# =============================================================================

if __name__ == "__main__":
    print("Effectiveness Analyzer - Self Test")
    print("=" * 40)

    # Try to find proof directory
    test_proof_dir = Path(__file__).parent.parent.parent / ".proof"

    if test_proof_dir.exists():
        print(f"Found proof directory: {test_proof_dir}")
        report = generate_effectiveness_report(test_proof_dir, days=30)
        print(format_compact_report(report))
    else:
        print(f"No proof directory at {test_proof_dir}")

        # Create mock data for testing
        mock_analyses = [
            SessionAnalysis(
                session_id="test-1",
                started_at=datetime.now() - timedelta(hours=2),
                duration_minutes=30,
                drift_signals_fired=2,
                drift_corrections_detected=1,
                fixes_surfaced=1,
                fixes_followed=1,
                tool_calls=50,
                files_modified=10,
                peak_context_usage=0.6,
            ),
            SessionAnalysis(
                session_id="test-2",
                started_at=datetime.now() - timedelta(hours=5),
                duration_minutes=45,
                drift_signals_fired=3,
                drift_corrections_detected=2,
                fixes_surfaced=2,
                fixes_followed=1,
                handoff_available=True,
                handoff_used=True,
                tool_calls=80,
                files_modified=15,
                peak_context_usage=0.75,
            ),
        ]

        # Calculate metrics from mock data
        drift = analyze_drift_effectiveness(mock_analyses)
        fix = analyze_fix_effectiveness(mock_analyses)
        handoff = analyze_handoff_effectiveness(mock_analyses)
        context = analyze_context_efficiency(mock_analyses)

        print(f"\nDrift Effectiveness: {drift.display_value} (confidence: {drift.confidence*100:.0f}%)")
        print(f"Fix Hit Rate: {fix.display_value} (confidence: {fix.confidence*100:.0f}%)")
        print(f"Handoff Adoption: {handoff.display_value} (confidence: {handoff.confidence*100:.0f}%)")
        print(f"Context Efficiency: {context.display_value} (confidence: {context.confidence*100:.0f}%)")

    print("\nSelf-test complete.")
