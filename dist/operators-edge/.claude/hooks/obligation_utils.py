#!/usr/bin/env python3
"""
Operator's Edge v3.11 - Obligation Utilities
Mechanical Learning: Track whether surfaced lessons are applied.

An Obligation bridges "lesson surfaced" to "lesson applied":
- Created when a lesson is surfaced (PreToolUse)
- Resolved when the tool completes (PostToolUse)
- Status: pending | applied | dismissed | violated

This closes the learning loop:
    Surface -> Apply -> Verify -> Reinforce
       ✓        ✓        ✓          ✓

v3.11.1: Added dismissal reason categories for matching quality measurement.
"""
import json
import os
import uuid
from dataclasses import dataclass, field, asdict
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Optional, List, Dict, Any

from state_utils import get_state_dir


# =============================================================================
# DISMISSAL REASONS (v3.11.1 - Matching Quality Measurement)
# =============================================================================

class DismissReason(Enum):
    """
    Categorized reasons for dismissing an obligation.

    These categories help measure matching quality:
    - FALSE_POSITIVE: Lesson surfaced but was irrelevant (matching too broad)
    - WRONG_LESSON: A different lesson would have been more helpful (matching missed)
    - ALREADY_KNEW: Lesson was obvious/redundant (value question, not matching)
    - CONTEXT_CHANGED: Situation changed, lesson no longer applies (timing issue)
    - OTHER: Uncategorized dismissal
    """
    # Matching quality signals
    FALSE_POSITIVE = "false_positive"      # Lesson irrelevant to this action
    WRONG_LESSON = "wrong_lesson"          # Should have surfaced a different lesson

    # Non-matching signals (still useful to track)
    ALREADY_KNEW = "already_knew"          # Lesson was obvious, didn't need reminder
    CONTEXT_CHANGED = "context_changed"    # Plan changed, no longer doing this action
    OTHER = "other"                        # Uncategorized

    @classmethod
    def from_string(cls, value: str) -> "DismissReason":
        """Parse a string into a DismissReason, defaulting to OTHER."""
        try:
            return cls(value.lower().replace(" ", "_").replace("-", "_"))
        except ValueError:
            return cls.OTHER

    @classmethod
    def choices(cls) -> List[str]:
        """Return list of valid choices for display."""
        return [r.value for r in cls]


# =============================================================================
# OBLIGATION SCHEMA
# =============================================================================

@dataclass
class Obligation:
    """
    An obligation to apply a surfaced lesson.

    Created when a lesson is surfaced during PreToolUse.
    Resolved automatically when the tool completes (applied/violated)
    or explicitly by the user (dismissed).
    """
    # Core identity
    id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])
    lesson_trigger: str = ""
    lesson_text: str = ""

    # Context
    tool_name: str = ""
    tool_input_summary: str = ""  # First 100 chars of relevant input
    session_id: str = ""

    # Status: pending | applied | dismissed | violated
    status: str = "pending"

    # Timing
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())
    resolved_at: Optional[str] = None
    success_window: str = "same_turn"  # When to auto-resolve

    # Resolution
    outcome: Optional[str] = None  # What happened
    dismiss_reason: Optional[str] = None  # If dismissed, free-text why
    dismiss_reason_category: Optional[str] = None  # Categorized reason (v3.11.1)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Obligation":
        """Create from dictionary."""
        return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})


# =============================================================================
# STATE MANAGEMENT
# =============================================================================

def get_obligations_path() -> Path:
    """Get path to obligations state file."""
    return get_state_dir() / "obligations.json"


def load_obligations() -> List[Obligation]:
    """Load pending obligations from state file."""
    path = get_obligations_path()
    if not path.exists():
        return []

    try:
        with open(path, 'r') as f:
            data = json.load(f)
        return [Obligation.from_dict(ob) for ob in data.get("pending", [])]
    except (json.JSONDecodeError, IOError):
        return []


def save_obligations(obligations: List[Obligation]) -> bool:
    """Save pending obligations to state file."""
    path = get_obligations_path()
    path.parent.mkdir(parents=True, exist_ok=True)

    try:
        data = {
            "pending": [ob.to_dict() for ob in obligations if ob.status == "pending"],
            "last_updated": datetime.now().isoformat()
        }
        with open(path, 'w') as f:
            json.dump(data, f, indent=2)
        return True
    except IOError:
        return False


# =============================================================================
# OBLIGATION CRUD
# =============================================================================

def create_obligation(
    lesson_trigger: str,
    lesson_text: str,
    tool_name: str,
    tool_input: Dict[str, Any],
    session_id: str = ""
) -> Obligation:
    """
    Create a new pending obligation when a lesson is surfaced.

    Called from PreToolUse when a relevant lesson is found.
    """
    # Build input summary from tool input
    input_summary = ""
    if "file_path" in tool_input:
        input_summary = tool_input["file_path"][:100]
    elif "command" in tool_input:
        input_summary = tool_input["command"][:100]

    obligation = Obligation(
        lesson_trigger=lesson_trigger,
        lesson_text=lesson_text,
        tool_name=tool_name,
        tool_input_summary=input_summary,
        session_id=session_id,
        status="pending"
    )

    # Add to pending obligations
    obligations = load_obligations()
    obligations.append(obligation)
    save_obligations(obligations)

    return obligation


def resolve_obligation(
    obligation_id: str,
    status: str,
    outcome: Optional[str] = None,
    dismiss_reason: Optional[str] = None,
    dismiss_reason_category: Optional[str] = None
) -> Optional[Obligation]:
    """
    Resolve a pending obligation.

    status: "applied" | "violated" | "dismissed"
    dismiss_reason_category: One of DismissReason values (for quality tracking)
    """
    if status not in ("applied", "violated", "dismissed"):
        return None

    obligations = load_obligations()
    resolved = None

    for ob in obligations:
        if ob.id == obligation_id:
            ob.status = status
            ob.resolved_at = datetime.now().isoformat()
            ob.outcome = outcome
            if status == "dismissed":
                ob.dismiss_reason = dismiss_reason
                ob.dismiss_reason_category = dismiss_reason_category
            resolved = ob
            break

    # Save updated list (will filter out resolved ones)
    save_obligations(obligations)

    return resolved


def get_pending_obligations(tool_name: Optional[str] = None) -> List[Obligation]:
    """
    Get pending obligations, optionally filtered by tool name.

    Called from PostToolUse to check if any obligations should be resolved.
    """
    obligations = load_obligations()

    if tool_name:
        return [ob for ob in obligations if ob.tool_name == tool_name and ob.status == "pending"]

    return [ob for ob in obligations if ob.status == "pending"]


def dismiss_obligation(
    obligation_id: str,
    reason: str,
    category: Optional[str] = None
) -> Optional[Obligation]:
    """
    Explicitly dismiss an obligation with a reason.

    Args:
        obligation_id: The obligation to dismiss
        reason: Free-text explanation
        category: One of DismissReason values for quality tracking:
            - "false_positive": Lesson was irrelevant
            - "wrong_lesson": Should have surfaced different lesson
            - "already_knew": Lesson was obvious
            - "context_changed": No longer doing this action
            - "other": Uncategorized

    Use when the lesson doesn't apply to this situation.
    """
    # Validate and normalize category
    if category:
        dismiss_category = DismissReason.from_string(category).value
    else:
        dismiss_category = DismissReason.OTHER.value

    return resolve_obligation(
        obligation_id=obligation_id,
        status="dismissed",
        dismiss_reason=reason,
        dismiss_reason_category=dismiss_category
    )


def auto_resolve_obligations(
    tool_name: str,
    success: bool,
    tool_input: Dict[str, Any]
) -> List[Obligation]:
    """
    Auto-resolve pending obligations for a completed tool.

    Called from PostToolUse after a tool completes.

    Resolution logic (v3.11.1 - auto-categorization):
    - Matching input + success=True  → "applied"
    - Matching input + success=False → "violated"
    - Non-matching input (same tool) → "dismissed" as false_positive
      (lesson was surfaced but user worked on different file/command)
    """
    pending = get_pending_obligations(tool_name)
    resolved = []

    # Build context for matching
    input_summary = ""
    if "file_path" in tool_input:
        input_summary = tool_input["file_path"][:100]
    elif "command" in tool_input:
        input_summary = tool_input["command"][:100]

    for ob in pending:
        # Check if input matches
        input_matches = (
            ob.tool_input_summary == input_summary or
            not ob.tool_input_summary
        )

        if input_matches:
            # Direct match - resolve based on success
            status = "applied" if success else "violated"
            outcome = f"Tool {tool_name} {'succeeded' if success else 'failed'}"
            resolved_ob = resolve_obligation(ob.id, status, outcome)
        else:
            # Same tool but different input = false positive
            # Lesson surfaced for wrong context (too generic)
            resolved_ob = resolve_obligation(
                ob.id,
                status="dismissed",
                outcome=f"Lesson surfaced for {ob.tool_input_summary} but tool used on {input_summary}",
                dismiss_reason="Auto-detected: lesson surfaced for different file/command",
                dismiss_reason_category=DismissReason.FALSE_POSITIVE.value
            )

        if resolved_ob:
            resolved.append(resolved_ob)

    return resolved


def clear_stale_obligations(max_age_hours: int = 24) -> List[Obligation]:
    """
    Clear obligations that are older than max_age_hours.

    v3.11.1: Stale obligations are now categorized as "context_changed"
    (user never performed the action the lesson was surfaced for).

    Returns list of cleared obligations (for logging).
    """
    obligations = load_obligations()
    now = datetime.now()
    cleared = []

    active = []
    for ob in obligations:
        try:
            created = datetime.fromisoformat(ob.created_at)
            age_hours = (now - created).total_seconds() / 3600
            if age_hours < max_age_hours:
                active.append(ob)
            else:
                # Stale = context changed (user never did the action)
                ob.status = "dismissed"
                ob.resolved_at = now.isoformat()
                ob.dismiss_reason = "Auto-detected: obligation timed out without action"
                ob.dismiss_reason_category = DismissReason.CONTEXT_CHANGED.value
                ob.outcome = f"Stale after {age_hours:.1f} hours"
                cleared.append(ob)
        except ValueError:
            active.append(ob)  # Keep if timestamp is invalid

    save_obligations(active)
    return cleared


# =============================================================================
# LOGGING HELPERS
# =============================================================================

def log_obligation_event(
    event_type: str,
    obligation: Obligation,
    session_id: str = ""
) -> Dict[str, Any]:
    """
    Create a log entry for an obligation event.

    event_type: "created" | "applied" | "dismissed" | "violated"

    Returns dict suitable for logging to proof.
    """
    entry = {
        "type": f"obligation:{event_type}",
        "obligation_id": obligation.id,
        "lesson_trigger": obligation.lesson_trigger,
        "tool_name": obligation.tool_name,
        "status": obligation.status,
        "timestamp": datetime.now().isoformat(),
        "session_id": session_id or obligation.session_id,
    }

    # Include dismissal category for quality tracking (v3.11.1)
    if event_type == "dismissed" and obligation.dismiss_reason_category:
        entry["dismiss_reason_category"] = obligation.dismiss_reason_category
        entry["dismiss_reason"] = obligation.dismiss_reason

    return entry


def format_obligation_for_display(obligation: Obligation) -> str:
    """Format an obligation for CLI display."""
    status_icons = {
        "pending": "⏳",
        "applied": "✅",
        "dismissed": "❌",
        "violated": "⚠️"
    }
    icon = status_icons.get(obligation.status, "?")
    return f"{icon} [{obligation.lesson_trigger}]: {obligation.lesson_text[:60]}..."


# =============================================================================
# MATCHING QUALITY ANALYSIS (v3.11.1)
# =============================================================================

def analyze_matching_quality(days_lookback: int = 14) -> Dict[str, Any]:
    """
    Analyze lesson matching quality from obligation dismissal patterns.

    Scans proof logs for obligation:dismissed events and categorizes them:
    - False Positive Rate: Irrelevant lessons surfaced / total surfaced
    - Wrong Lesson Rate: Wrong lesson surfaced / total surfaced
    - Noise Rate: (FP + Wrong) / total surfaced

    Args:
        days_lookback: How many days of proof logs to scan

    Returns:
        dict with:
            - false_positive_rate: Proportion of irrelevant lessons
            - wrong_lesson_rate: Proportion where different lesson was needed
            - noise_rate: Combined matching quality issue rate
            - total_surfaced: Total obligations created
            - total_dismissed: Total obligations dismissed
            - by_category: Counts per dismissal category
            - recommendation: Suggested action based on rates
    """
    try:
        from proof_utils import get_sessions_dir
    except ImportError:
        return {"error": "proof_utils not available"}

    sessions_dir = get_sessions_dir()
    if not sessions_dir.exists():
        return {
            "false_positive_rate": 0.0,
            "wrong_lesson_rate": 0.0,
            "noise_rate": 0.0,
            "total_surfaced": 0,
            "total_dismissed": 0,
            "by_category": {},
            "recommendation": "No data yet"
        }

    from datetime import timedelta
    cutoff = datetime.now() - timedelta(days=days_lookback)

    total_surfaced = 0
    total_dismissed = 0
    by_category = {r.value: 0 for r in DismissReason}

    # Scan all session logs
    for log_file in sessions_dir.glob("*.jsonl"):
        try:
            session_id = log_file.stem
            session_date = datetime.strptime(session_id, "%Y%m%d-%H%M%S")

            if session_date < cutoff:
                continue

            content = log_file.read_text()
            for line in content.strip().split('\n'):
                if not line.strip():
                    continue

                try:
                    entry = json.loads(line)
                    event_type = entry.get("type", "")

                    if event_type == "obligation:created":
                        total_surfaced += 1

                    elif event_type == "obligation:dismissed":
                        total_dismissed += 1
                        category = entry.get("dismiss_reason_category", "other")
                        if category in by_category:
                            by_category[category] += 1
                        else:
                            by_category["other"] += 1

                except json.JSONDecodeError:
                    continue

        except (ValueError, OSError):
            continue

    # Calculate rates
    fp_count = by_category.get("false_positive", 0)
    wrong_count = by_category.get("wrong_lesson", 0)

    fp_rate = fp_count / total_surfaced if total_surfaced > 0 else 0.0
    wrong_rate = wrong_count / total_surfaced if total_surfaced > 0 else 0.0
    noise_rate = (fp_count + wrong_count) / total_surfaced if total_surfaced > 0 else 0.0

    # Generate recommendation
    recommendation = _generate_matching_recommendation(
        fp_rate, wrong_rate, noise_rate, total_surfaced
    )

    return {
        "false_positive_rate": round(fp_rate, 3),
        "wrong_lesson_rate": round(wrong_rate, 3),
        "noise_rate": round(noise_rate, 3),
        "total_surfaced": total_surfaced,
        "total_dismissed": total_dismissed,
        "by_category": by_category,
        "recommendation": recommendation
    }


def _generate_matching_recommendation(
    fp_rate: float,
    wrong_rate: float,
    noise_rate: float,
    total: int
) -> str:
    """Generate actionable recommendation based on matching quality."""
    if total < 10:
        return "Insufficient data - need at least 10 obligations to assess quality"

    if noise_rate > 0.3:
        return (
            f"HIGH NOISE ({noise_rate:.0%}): Consider adding semantic embeddings "
            "as fallback layer. Current keyword matching is too broad."
        )

    if fp_rate > 0.2:
        return (
            f"High false positives ({fp_rate:.0%}): Triggers may be too generic. "
            "Consider adding file_patterns or tool filters to lessons."
        )

    if wrong_rate > 0.1:
        return (
            f"Wrong lessons surfacing ({wrong_rate:.0%}): May need better trigger "
            "keywords or consider embedding-based deduplication."
        )

    if noise_rate < 0.05:
        return "Excellent matching quality. No changes recommended."

    return f"Matching quality acceptable (noise rate {noise_rate:.0%})"


def format_matching_quality_report(analysis: Dict[str, Any] = None) -> str:
    """
    Format matching quality analysis for display.

    Args:
        analysis: Optional pre-calculated analysis (calls analyze_matching_quality if None)

    Returns:
        Formatted string for CLI display
    """
    if analysis is None:
        analysis = analyze_matching_quality()

    if "error" in analysis:
        return f"Matching Quality Analysis Error: {analysis['error']}"

    lines = [
        "-" * 60,
        "MATCHING QUALITY ANALYSIS (v3.11.1)",
        "-" * 60,
        "",
        f"Total Lessons Surfaced: {analysis['total_surfaced']}",
        f"Total Dismissed: {analysis['total_dismissed']}",
        "",
        "Quality Metrics:",
        f"  False Positive Rate: {analysis['false_positive_rate']:.1%}",
        f"  Wrong Lesson Rate:   {analysis['wrong_lesson_rate']:.1%}",
        f"  Overall Noise Rate:  {analysis['noise_rate']:.1%}",
        "",
        "Dismissal Breakdown:",
    ]

    for category, count in analysis.get("by_category", {}).items():
        if count > 0:
            lines.append(f"  {category}: {count}")

    lines.extend([
        "",
        f"Recommendation: {analysis['recommendation']}",
        "-" * 60,
    ])

    return "\n".join(lines)
