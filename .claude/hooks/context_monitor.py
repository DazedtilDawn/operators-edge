#!/usr/bin/env python3
"""
Operator's Edge v8.0 - Context Monitor

Tracks context window utilization and triggers compression when needed.

Key Insight: Claude doesn't have direct access to its context window size,
but we can estimate it by tracking:
- Tool calls this session
- Characters in inputs/outputs
- Files read/written
- Session duration

This enables proactive compression before context exhaustion causes
degraded performance or loss of objective focus.

This is context engineering, not machine learning.
"""
import json
import os
import sys
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Tuple

# Add hooks directory to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


# =============================================================================
# CONFIGURATION
# =============================================================================

# Estimated context window limits (tokens)
# These are conservative estimates - actual limits may vary
CONTEXT_WINDOW_ESTIMATE = 200_000  # Claude's effective working window

# Heuristic: ~4 characters per token (rough average for code/text)
CHARS_PER_TOKEN = 4

# Compression thresholds
WARN_THRESHOLD = 0.60   # Surface warning at 60% usage
COMPRESS_THRESHOLD = 0.75  # Strong recommendation at 75% usage
CRITICAL_THRESHOLD = 0.90  # Critical warning at 90% usage

# Session duration thresholds (minutes)
LONG_SESSION_WARNING = 45  # Warn after 45 minutes
VERY_LONG_SESSION = 90     # Critical after 90 minutes


# =============================================================================
# DATA STRUCTURES
# =============================================================================

@dataclass
class ContextEstimate:
    """Estimate of context window utilization."""
    # Raw counts
    tool_calls: int = 0
    total_input_chars: int = 0
    total_output_chars: int = 0
    files_read: int = 0
    files_written: int = 0

    # Computed estimates
    estimated_tokens: int = 0
    usage_percentage: float = 0.0

    # Session info
    session_duration_minutes: float = 0.0
    first_entry_time: Optional[datetime] = None
    last_entry_time: Optional[datetime] = None

    # Per-tool breakdown
    tool_breakdown: Dict[str, int] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "tool_calls": self.tool_calls,
            "total_input_chars": self.total_input_chars,
            "total_output_chars": self.total_output_chars,
            "files_read": self.files_read,
            "files_written": self.files_written,
            "estimated_tokens": self.estimated_tokens,
            "usage_percentage": round(self.usage_percentage * 100, 1),
            "session_duration_minutes": round(self.session_duration_minutes, 1),
            "tool_breakdown": self.tool_breakdown
        }


@dataclass
class CompressionRecommendation:
    """Recommendation for context compression."""
    should_compress: bool
    severity: str  # "none", "info", "warning", "critical"
    reason: str
    suggestion: str
    checkpoint_summary: Optional[str] = None


# =============================================================================
# CONTEXT ESTIMATION
# =============================================================================

def load_session_entries(session_log: Path) -> List[dict]:
    """Load all entries from session log."""
    if not session_log.exists():
        return []

    entries = []
    try:
        with open(session_log) as f:
            for line in f:
                if not line.strip():
                    continue
                try:
                    entry = json.loads(line)
                    entries.append(entry)
                except json.JSONDecodeError:
                    continue
    except Exception:
        return []

    return entries


def estimate_entry_tokens(entry: dict) -> int:
    """Estimate token count for a single entry."""
    chars = 0

    # Input preview
    input_preview = entry.get("input_preview", "")
    if isinstance(input_preview, dict):
        chars += len(json.dumps(input_preview))
    else:
        chars += len(str(input_preview))

    # Output preview
    output_preview = entry.get("output_preview", "")
    if output_preview:
        chars += len(str(output_preview))

    return chars // CHARS_PER_TOKEN


def estimate_context_usage(session_log: Path) -> ContextEstimate:
    """
    Estimate how much of context window is consumed.

    This is a heuristic estimate based on:
    - Accumulated tool call inputs/outputs
    - Number of files read (code tends to stay in context)
    - Session duration (proxy for conversation length)
    """
    entries = load_session_entries(session_log)

    if not entries:
        return ContextEstimate()

    estimate = ContextEstimate()
    estimate.tool_calls = len(entries)

    # Parse timestamps
    timestamps = []
    for entry in entries:
        ts_str = entry.get("timestamp", "")
        if ts_str:
            try:
                ts = datetime.fromisoformat(ts_str.replace("Z", "+00:00"))
                timestamps.append(ts.replace(tzinfo=None))
            except ValueError:
                pass

    if timestamps:
        estimate.first_entry_time = min(timestamps)
        estimate.last_entry_time = max(timestamps)
        duration = estimate.last_entry_time - estimate.first_entry_time
        estimate.session_duration_minutes = duration.total_seconds() / 60

    # Analyze each entry
    tool_counts = {}
    for entry in entries:
        tool = entry.get("tool", "unknown")
        tool_counts[tool] = tool_counts.get(tool, 0) + 1

        # Estimate token usage
        tokens = estimate_entry_tokens(entry)

        # Track input/output separately
        input_preview = entry.get("input_preview", "")
        if isinstance(input_preview, dict):
            estimate.total_input_chars += len(json.dumps(input_preview))
        else:
            estimate.total_input_chars += len(str(input_preview))

        output_preview = entry.get("output_preview", "")
        if output_preview:
            estimate.total_output_chars += len(str(output_preview))

        # Track file operations
        if tool == "Read":
            estimate.files_read += 1
        elif tool in ("Edit", "Write", "NotebookEdit"):
            estimate.files_written += 1

    estimate.tool_breakdown = tool_counts

    # Compute total estimated tokens
    total_chars = estimate.total_input_chars + estimate.total_output_chars
    estimate.estimated_tokens = total_chars // CHARS_PER_TOKEN

    # Add session conversation overhead (each tool call includes conversation)
    # Heuristic: ~500 tokens per tool call for conversation context
    conversation_overhead = estimate.tool_calls * 500
    estimate.estimated_tokens += conversation_overhead

    # Files read stay in context - add weight
    # Heuristic: each file read adds ~2000 tokens average
    file_context = estimate.files_read * 2000
    estimate.estimated_tokens += file_context

    # Compute usage percentage
    estimate.usage_percentage = min(1.0, estimate.estimated_tokens / CONTEXT_WINDOW_ESTIMATE)

    return estimate


# =============================================================================
# COMPRESSION DECISIONS
# =============================================================================

def should_compress(estimate: ContextEstimate) -> CompressionRecommendation:
    """
    Determine if context compression is needed.

    Returns recommendation with severity and suggested action.
    """
    # Check various factors

    # Factor 1: Token usage percentage
    if estimate.usage_percentage >= CRITICAL_THRESHOLD:
        return CompressionRecommendation(
            should_compress=True,
            severity="critical",
            reason=f"Context usage at {estimate.usage_percentage*100:.0f}% - approaching limit",
            suggestion=(
                "CRITICAL: Context window nearly full. Consider:\n"
                "1. Generating a checkpoint summary of progress so far\n"
                "2. Starting a new session with the checkpoint\n"
                "3. Focusing only on the immediate next step"
            )
        )

    if estimate.usage_percentage >= COMPRESS_THRESHOLD:
        return CompressionRecommendation(
            should_compress=True,
            severity="warning",
            reason=f"Context usage at {estimate.usage_percentage*100:.0f}%",
            suggestion=(
                "Context getting long. Consider:\n"
                "- Summarizing completed work\n"
                "- Dropping details of resolved issues\n"
                "- Focusing on active problem only"
            )
        )

    if estimate.usage_percentage >= WARN_THRESHOLD:
        return CompressionRecommendation(
            should_compress=False,
            severity="info",
            reason=f"Context usage at {estimate.usage_percentage*100:.0f}%",
            suggestion="Context healthy but monitor usage."
        )

    # Factor 2: Session duration
    if estimate.session_duration_minutes >= VERY_LONG_SESSION:
        return CompressionRecommendation(
            should_compress=True,
            severity="warning",
            reason=f"Session running for {estimate.session_duration_minutes:.0f} minutes",
            suggestion=(
                "Very long session. Even if context isn't full, consider:\n"
                "- Creating a checkpoint for continuity\n"
                "- Verifying you're still on track with the original objective\n"
                "- Breaking remaining work into a fresh session"
            )
        )

    if estimate.session_duration_minutes >= LONG_SESSION_WARNING:
        return CompressionRecommendation(
            should_compress=False,
            severity="info",
            reason=f"Session running for {estimate.session_duration_minutes:.0f} minutes",
            suggestion="Long session - keep an eye on focus and context."
        )

    # No compression needed
    return CompressionRecommendation(
        should_compress=False,
        severity="none",
        reason="Context usage healthy",
        suggestion=""
    )


# =============================================================================
# CHECKPOINT GENERATION
# =============================================================================

def generate_checkpoint(state: dict, session_log: Path) -> str:
    """
    Generate a compressed summary of work so far.

    This creates a "checkpoint" that can be used to:
    1. Resume in a new session with context preserved
    2. Provide a summary to review progress
    3. Hand off to another session/agent
    """
    estimate = estimate_context_usage(session_log)
    entries = load_session_entries(session_log)

    # Extract key information from state
    objective = state.get("objective", "Unknown objective")
    plan = state.get("plan", [])
    current_step = state.get("current_step", 0)

    # Count completed steps
    completed = [s for s in plan if isinstance(s, dict) and s.get("status") == "completed"]
    in_progress = [s for s in plan if isinstance(s, dict) and s.get("status") == "in_progress"]
    pending = [s for s in plan if isinstance(s, dict) and s.get("status") == "pending"]

    # Find recent failures
    recent_failures = []
    for entry in reversed(entries[-20:]):  # Last 20 entries
        if not entry.get("success", True):
            tool = entry.get("tool", "")
            preview = entry.get("output_preview", "")[:100]
            recent_failures.append(f"{tool}: {preview}")

    # Find most-edited files (potential trouble spots)
    file_edits = {}
    for entry in entries:
        if entry.get("tool") in ("Edit", "Write"):
            input_data = entry.get("input_preview", {})
            if isinstance(input_data, dict):
                file_path = input_data.get("file_path") or input_data.get("file", "")
                if file_path:
                    file_edits[file_path] = file_edits.get(file_path, 0) + 1

    # Sort by edit count
    churned_files = sorted(file_edits.items(), key=lambda x: -x[1])[:5]

    # Build checkpoint
    lines = [
        "# Session Checkpoint",
        "",
        f"**Objective:** {objective}",
        "",
        f"**Progress:** {len(completed)}/{len(plan)} steps completed",
        "",
    ]

    # Current step
    if in_progress:
        lines.append("**Currently Working On:**")
        for step in in_progress:
            desc = step.get("description", "Unknown step")
            lines.append(f"- {desc}")
        lines.append("")

    # What's done
    if completed:
        lines.append("**Completed Steps:**")
        for step in completed:
            desc = step.get("description", "Unknown step")
            lines.append(f"- ✓ {desc}")
        lines.append("")

    # What's left
    if pending:
        lines.append("**Remaining Steps:**")
        for step in pending:
            desc = step.get("description", "Unknown step")
            lines.append(f"- ○ {desc}")
        lines.append("")

    # Recent issues
    if recent_failures:
        lines.append("**Recent Issues:**")
        for failure in recent_failures[:3]:
            lines.append(f"- ❌ {failure}")
        lines.append("")

    # Files with high churn
    if churned_files:
        high_churn = [(f, c) for f, c in churned_files if c >= 3]
        if high_churn:
            lines.append("**Files With High Edit Count:**")
            for file_path, count in high_churn:
                lines.append(f"- {file_path} ({count} edits)")
            lines.append("")

    # Session stats
    lines.extend([
        "**Session Statistics:**",
        f"- Duration: {estimate.session_duration_minutes:.0f} minutes",
        f"- Tool calls: {estimate.tool_calls}",
        f"- Files read: {estimate.files_read}",
        f"- Files modified: {estimate.files_written}",
        f"- Estimated context usage: {estimate.usage_percentage*100:.0f}%",
        ""
    ])

    return "\n".join(lines)


# =============================================================================
# INTERVENTION FORMATTING
# =============================================================================

def format_context_intervention(recommendation: CompressionRecommendation, estimate: ContextEstimate) -> str:
    """Format context warning for display."""
    if recommendation.severity == "none":
        return ""

    icon = {
        "critical": "🔴",
        "warning": "🟡",
        "info": "🔵"
    }.get(recommendation.severity, "⚪")

    lines = [
        "",
        "=" * 60,
        f"{icon} CONTEXT MONITOR - {recommendation.severity.upper()}",
        "=" * 60,
        "",
        f"**Status:** {recommendation.reason}",
        "",
        f"**Metrics:**",
        f"  - Estimated tokens: {estimate.estimated_tokens:,}",
        f"  - Session duration: {estimate.session_duration_minutes:.0f} min",
        f"  - Tool calls: {estimate.tool_calls}",
        f"  - Files read: {estimate.files_read}",
        "",
    ]

    if recommendation.suggestion:
        lines.extend([
            f"**Recommendation:**",
            recommendation.suggestion,
            ""
        ])

    lines.extend([
        "-" * 60,
        ""
    ])

    return "\n".join(lines)


# =============================================================================
# MAIN INTERFACE
# =============================================================================

def check_context_and_recommend(session_log: Path, state: dict) -> Tuple[ContextEstimate, CompressionRecommendation]:
    """
    Main entry point: Check context usage and get recommendation.

    Returns (estimate, recommendation) tuple.
    """
    estimate = estimate_context_usage(session_log)
    recommendation = should_compress(estimate)

    # If compression recommended, generate checkpoint
    if recommendation.should_compress:
        checkpoint = generate_checkpoint(state, session_log)
        recommendation.checkpoint_summary = checkpoint

    return estimate, recommendation


# =============================================================================
# QUICK TEST
# =============================================================================

if __name__ == "__main__":
    print("Context Monitor - Self Test")
    print("=" * 40)

    # Test with empty estimate
    estimate = ContextEstimate()
    recommendation = should_compress(estimate)
    print(f"Empty session: {recommendation.severity} - {recommendation.reason}")

    # Test with high usage
    estimate = ContextEstimate(
        tool_calls=100,
        estimated_tokens=160_000,
        usage_percentage=0.80,
        session_duration_minutes=60
    )
    recommendation = should_compress(estimate)
    print(f"High usage: {recommendation.severity} - {recommendation.reason}")

    # Test with long session
    estimate = ContextEstimate(
        tool_calls=50,
        estimated_tokens=50_000,
        usage_percentage=0.25,
        session_duration_minutes=100
    )
    recommendation = should_compress(estimate)
    print(f"Long session: {recommendation.severity} - {recommendation.reason}")

    print()
    print("Self-test complete.")
