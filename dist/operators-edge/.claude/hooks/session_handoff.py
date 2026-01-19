#!/usr/bin/env python3
"""
Operator's Edge v8.0 - Session Handoff

Enable continuity across sessions with structured state transfer.

Key Insight: A new session gets raw state, not an optimized summary.
This module creates intelligent handoffs that:
1. Compress completed work
2. Highlight active problems
3. Surface approaches tried (and their outcomes)
4. Carry forward key insights and warnings

This builds on Phase 1-3:
- Phase 1 (drift_detector): Drift signals to carry forward
- Phase 2 (context_monitor): Context estimation and checkpoint generation
- Phase 3 (codebase_knowledge): Known fixes encountered this session

This is context engineering, not machine learning.
"""
import json
import os
import sys
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple

# Add hooks directory to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


# =============================================================================
# CONFIGURATION
# =============================================================================

# Handoff storage location
HANDOFFS_DIR = "handoffs"

# Retention policy
MAX_HANDOFFS = 10  # Keep last N handoffs


# =============================================================================
# DATA STRUCTURES
# =============================================================================

@dataclass
class ApproachTried:
    """An approach that was tried during the session."""
    description: str
    outcome: str  # "success", "partial", "failed"
    reason: str   # Why it succeeded/failed
    commands_run: List[str] = field(default_factory=list)
    files_modified: List[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "description": self.description,
            "outcome": self.outcome,
            "reason": self.reason,
            "commands_run": self.commands_run,
            "files_modified": self.files_modified,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "ApproachTried":
        return cls(
            description=data.get("description", ""),
            outcome=data.get("outcome", "unknown"),
            reason=data.get("reason", ""),
            commands_run=data.get("commands_run", []),
            files_modified=data.get("files_modified", []),
        )


@dataclass
class HandoffSummary:
    """Structured summary for session handoff."""
    # Core state
    objective: str
    progress: str  # "3/7 steps complete"

    # Current work
    active_problem: str
    next_action: str

    # History
    approaches_tried: List[ApproachTried] = field(default_factory=list)
    key_insights: List[str] = field(default_factory=list)

    # Warnings from v8.0 systems
    drift_warnings: List[str] = field(default_factory=list)
    known_fixes_used: List[str] = field(default_factory=list)
    churned_files: List[Tuple[str, int]] = field(default_factory=list)

    # Context metrics
    context_usage_percent: float = 0.0
    session_duration_minutes: float = 0.0
    tool_calls: int = 0

    # Metadata
    session_id: str = ""
    created_at: str = ""

    def to_dict(self) -> dict:
        return {
            "objective": self.objective,
            "progress": self.progress,
            "active_problem": self.active_problem,
            "next_action": self.next_action,
            "approaches_tried": [a.to_dict() for a in self.approaches_tried],
            "key_insights": self.key_insights,
            "drift_warnings": self.drift_warnings,
            "known_fixes_used": self.known_fixes_used,
            "churned_files": self.churned_files,
            "context_usage_percent": self.context_usage_percent,
            "session_duration_minutes": self.session_duration_minutes,
            "tool_calls": self.tool_calls,
            "session_id": self.session_id,
            "created_at": self.created_at,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "HandoffSummary":
        return cls(
            objective=data.get("objective", ""),
            progress=data.get("progress", ""),
            active_problem=data.get("active_problem", ""),
            next_action=data.get("next_action", ""),
            approaches_tried=[
                ApproachTried.from_dict(a)
                for a in data.get("approaches_tried", [])
            ],
            key_insights=data.get("key_insights", []),
            drift_warnings=data.get("drift_warnings", []),
            known_fixes_used=data.get("known_fixes_used", []),
            churned_files=data.get("churned_files", []),
            context_usage_percent=data.get("context_usage_percent", 0.0),
            session_duration_minutes=data.get("session_duration_minutes", 0.0),
            tool_calls=data.get("tool_calls", 0),
            session_id=data.get("session_id", ""),
            created_at=data.get("created_at", ""),
        )


# =============================================================================
# HANDOFF STORAGE
# =============================================================================

def _get_handoffs_dir() -> Path:
    """Get path to handoffs directory."""
    proof_dir = Path(__file__).parent.parent.parent / ".proof"
    handoffs_dir = proof_dir / HANDOFFS_DIR
    handoffs_dir.mkdir(parents=True, exist_ok=True)
    return handoffs_dir


def save_handoff(handoff: HandoffSummary) -> Path:
    """Save handoff to disk."""
    handoffs_dir = _get_handoffs_dir()

    # Use timestamp-based filename
    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    filename = f"handoff-{timestamp}.json"
    filepath = handoffs_dir / filename

    with open(filepath, 'w') as f:
        json.dump(handoff.to_dict(), f, indent=2)

    # Cleanup old handoffs
    _cleanup_old_handoffs()

    return filepath


def load_latest_handoff() -> Optional[HandoffSummary]:
    """Load the most recent handoff."""
    handoffs_dir = _get_handoffs_dir()

    handoff_files = sorted(handoffs_dir.glob("handoff-*.json"), reverse=True)
    if not handoff_files:
        return None

    try:
        with open(handoff_files[0]) as f:
            data = json.load(f)
        return HandoffSummary.from_dict(data)
    except (json.JSONDecodeError, OSError):
        return None


def load_handoff_by_session(session_id: str) -> Optional[HandoffSummary]:
    """Load handoff by session ID."""
    handoffs_dir = _get_handoffs_dir()

    for filepath in handoffs_dir.glob("handoff-*.json"):
        try:
            with open(filepath) as f:
                data = json.load(f)
            if data.get("session_id") == session_id:
                return HandoffSummary.from_dict(data)
        except (json.JSONDecodeError, OSError):
            continue

    return None


def _cleanup_old_handoffs():
    """Remove old handoffs beyond retention limit."""
    handoffs_dir = _get_handoffs_dir()
    handoff_files = sorted(handoffs_dir.glob("handoff-*.json"), reverse=True)

    for filepath in handoff_files[MAX_HANDOFFS:]:
        try:
            filepath.unlink()
        except OSError:
            pass


# =============================================================================
# HANDOFF GENERATION
# =============================================================================

def generate_handoff_summary(
    state: dict,
    session_log: Path,
    session_id: str = ""
) -> HandoffSummary:
    """
    Generate a handoff summary from current session state.

    Integrates data from:
    - Current state (objective, plan, progress)
    - Session log (tool calls, outcomes)
    - Drift detector (warnings)
    - Context monitor (usage metrics)
    - Codebase knowledge (fixes used)
    """
    # Initialize with placeholder values, will populate below
    handoff = HandoffSummary(
        objective="",
        progress="",
        active_problem="",
        next_action="",
        session_id=session_id,
        created_at=datetime.now().isoformat(),
    )

    # Extract core state
    handoff.objective = state.get("objective", "No objective set")

    plan = state.get("plan", [])
    completed = [s for s in plan if isinstance(s, dict) and s.get("status") == "completed"]
    in_progress = [s for s in plan if isinstance(s, dict) and s.get("status") == "in_progress"]
    pending = [s for s in plan if isinstance(s, dict) and s.get("status") == "pending"]

    total_steps = len(plan)
    completed_steps = len(completed)
    handoff.progress = f"{completed_steps}/{total_steps} steps complete"

    # Active problem (current step)
    if in_progress:
        step = in_progress[0]
        handoff.active_problem = step.get("description", "Working on current step")
    elif pending:
        handoff.active_problem = "Ready for next step"
    else:
        handoff.active_problem = "All steps complete" if completed else "No plan defined"

    # Next action
    if pending:
        handoff.next_action = pending[0].get("description", "Continue with plan")
    elif in_progress:
        handoff.next_action = "Complete current step"
    else:
        handoff.next_action = "Review results and close objective"

    # Integrate context monitor data
    try:
        from context_monitor import estimate_context_usage, load_session_entries

        estimate = estimate_context_usage(session_log)
        handoff.context_usage_percent = estimate.usage_percentage * 100
        handoff.session_duration_minutes = estimate.session_duration_minutes
        handoff.tool_calls = estimate.tool_calls

        # Find churned files
        entries = load_session_entries(session_log)
        file_edits = {}
        for entry in entries:
            if entry.get("tool") in ("Edit", "Write"):
                input_data = entry.get("input_preview", {})
                if isinstance(input_data, dict):
                    fp = input_data.get("file_path") or input_data.get("file", "")
                    if fp:
                        file_edits[fp] = file_edits.get(fp, 0) + 1

        # Files with 3+ edits are "churned"
        handoff.churned_files = [
            (f, c) for f, c in sorted(file_edits.items(), key=lambda x: -x[1])
            if c >= 3
        ][:5]

    except ImportError:
        pass
    except Exception:
        pass

    # Integrate drift detector data
    try:
        from drift_detector import detect_drift

        signals = detect_drift(session_log, state, lookback_minutes=60)
        handoff.drift_warnings = [
            f"{s.signal_type}: {s.message}"
            for s in signals
            if s.severity in ("warning", "critical")
        ]
    except ImportError:
        pass
    except Exception:
        pass

    # Extract approaches tried from session log
    handoff.approaches_tried = _extract_approaches_from_log(session_log)

    # Key insights from state
    if state.get("risks"):
        handoff.key_insights.extend([
            f"Risk: {r}" for r in state.get("risks", [])[:3]
        ])
    if state.get("constraints"):
        handoff.key_insights.extend([
            f"Constraint: {c}" for c in state.get("constraints", [])[:2]
        ])

    return handoff


def _extract_approaches_from_log(session_log: Path) -> List[ApproachTried]:
    """
    Extract approach patterns from session log.

    Looks for:
    - Failed command → retry → success (learned something)
    - Multiple edits to same file (iteration)
    - Test failures → fixes → passes
    """
    approaches = []

    try:
        from context_monitor import load_session_entries
        entries = load_session_entries(session_log)
    except ImportError:
        return approaches
    except Exception:
        return approaches

    if not entries:
        return approaches

    # Track command failures and successes
    command_results = {}  # cmd -> [(success, output)]
    file_edits = {}  # file -> [timestamps]

    for entry in entries:
        tool = entry.get("tool", "")
        success = entry.get("success", True)

        if tool == "Bash":
            input_data = entry.get("input_preview", {})
            cmd = ""
            if isinstance(input_data, dict):
                cmd = input_data.get("command", "")
            elif isinstance(input_data, str):
                cmd = input_data

            if cmd:
                # Normalize command (first 50 chars)
                cmd_key = cmd.strip()[:50]
                if cmd_key not in command_results:
                    command_results[cmd_key] = []
                command_results[cmd_key].append((
                    success,
                    entry.get("output_preview", "")[:100]
                ))

        elif tool in ("Edit", "Write"):
            input_data = entry.get("input_preview", {})
            if isinstance(input_data, dict):
                fp = input_data.get("file_path") or input_data.get("file", "")
                if fp:
                    if fp not in file_edits:
                        file_edits[fp] = []
                    file_edits[fp].append(entry.get("timestamp", ""))

    # Convert patterns to approaches

    # Pattern 1: Failed then succeeded commands
    for cmd, results in command_results.items():
        if len(results) >= 2:
            had_failure = any(not r[0] for r in results[:-1])
            final_success = results[-1][0]

            if had_failure and final_success:
                approaches.append(ApproachTried(
                    description=f"Retry after failure: {cmd[:40]}...",
                    outcome="success",
                    reason="Resolved after investigation",
                    commands_run=[cmd],
                ))
            elif had_failure and not final_success:
                approaches.append(ApproachTried(
                    description=f"Attempted: {cmd[:40]}...",
                    outcome="failed",
                    reason=results[-1][1][:50] if results[-1][1] else "Unknown error",
                    commands_run=[cmd],
                ))

    # Pattern 2: High churn files (iterated heavily)
    for fp, timestamps in file_edits.items():
        if len(timestamps) >= 3:
            approaches.append(ApproachTried(
                description=f"Iterated on {Path(fp).name}",
                outcome="partial",
                reason=f"Modified {len(timestamps)} times",
                files_modified=[fp],
            ))

    return approaches[:10]  # Limit to 10 approaches


# =============================================================================
# HANDOFF INJECTION
# =============================================================================

def format_handoff_for_injection(handoff: HandoffSummary) -> str:
    """
    Format handoff summary for injection at session start.

    This is the text that gets shown to Claude at the beginning
    of a new session to provide continuity.
    """
    lines = [
        "",
        "=" * 60,
        "📋 PREVIOUS SESSION HANDOFF",
        "=" * 60,
        "",
        f"**Objective:** {handoff.objective}",
        f"**Progress:** {handoff.progress}",
        "",
        f"**Where We Left Off:** {handoff.active_problem}",
        f"**Recommended Next:** {handoff.next_action}",
        "",
    ]

    # Approaches tried
    if handoff.approaches_tried:
        lines.append("**Approaches Tried:**")
        for approach in handoff.approaches_tried[:5]:
            icon = {"success": "✓", "partial": "◐", "failed": "✗"}.get(approach.outcome, "?")
            lines.append(f"  {icon} {approach.description}")
            if approach.outcome != "success" and approach.reason:
                lines.append(f"      → {approach.reason}")
        lines.append("")

    # Key insights
    if handoff.key_insights:
        lines.append("**Key Insights:**")
        for insight in handoff.key_insights[:5]:
            lines.append(f"  • {insight}")
        lines.append("")

    # Drift warnings (important!)
    if handoff.drift_warnings:
        lines.append("**⚠️ Drift Warnings from Previous Session:**")
        for warning in handoff.drift_warnings:
            lines.append(f"  ⚠️ {warning}")
        lines.append("")

    # Churned files
    if handoff.churned_files:
        lines.append("**Files That Needed Multiple Edits:**")
        for fp, count in handoff.churned_files[:3]:
            lines.append(f"  - {fp} ({count} edits)")
        lines.append("")

    # Session stats
    lines.extend([
        f"**Previous Session Stats:**",
        f"  - Duration: {handoff.session_duration_minutes:.0f} min",
        f"  - Tool calls: {handoff.tool_calls}",
        f"  - Context usage: {handoff.context_usage_percent:.0f}%",
        "",
        "-" * 60,
        ""
    ])

    return "\n".join(lines)


def get_handoff_for_new_session() -> Optional[str]:
    """
    Get formatted handoff for injection at session start.

    Returns None if no relevant handoff exists.
    """
    handoff = load_latest_handoff()
    if not handoff:
        return None

    # Check if handoff is recent enough (within 24 hours)
    if handoff.created_at:
        try:
            created = datetime.fromisoformat(handoff.created_at)
            age_hours = (datetime.now() - created).total_seconds() / 3600
            if age_hours > 24:
                return None  # Too old
        except ValueError:
            pass

    return format_handoff_for_injection(handoff)


# =============================================================================
# QUICK TEST
# =============================================================================

if __name__ == "__main__":
    print("Session Handoff - Self Test")
    print("=" * 40)

    # Test handoff generation with mock data
    state = {
        "objective": "Implement v8.0 context engineering",
        "plan": [
            {"description": "Phase 1: Drift Detection", "status": "completed"},
            {"description": "Phase 2: Context Monitor", "status": "completed"},
            {"description": "Phase 3: Codebase Knowledge", "status": "completed"},
            {"description": "Phase 4: Session Handoff", "status": "in_progress"},
        ],
        "risks": ["Context window exhaustion"],
        "constraints": ["Must be backward compatible"],
    }

    # Create mock session log
    import tempfile
    with tempfile.TemporaryDirectory() as tmpdir:
        log_path = Path(tmpdir) / "test_session.jsonl"

        # Write some mock entries
        entries = [
            {"tool": "Edit", "input_preview": {"file_path": "/app/test.py"}, "success": True, "timestamp": "2026-01-18T10:00:00"},
            {"tool": "Bash", "input_preview": {"command": "pytest"}, "success": False, "output_preview": "FAILED", "timestamp": "2026-01-18T10:01:00"},
            {"tool": "Edit", "input_preview": {"file_path": "/app/test.py"}, "success": True, "timestamp": "2026-01-18T10:02:00"},
            {"tool": "Bash", "input_preview": {"command": "pytest"}, "success": True, "timestamp": "2026-01-18T10:03:00"},
        ]

        with open(log_path, 'w') as f:
            for entry in entries:
                f.write(json.dumps(entry) + "\n")

        # Generate handoff
        handoff = generate_handoff_summary(state, log_path, "test-session")

        print(f"Objective: {handoff.objective}")
        print(f"Progress: {handoff.progress}")
        print(f"Active Problem: {handoff.active_problem}")
        print(f"Next Action: {handoff.next_action}")
        print(f"Approaches Tried: {len(handoff.approaches_tried)}")

        # Test formatting
        print("\n--- Formatted Handoff ---")
        formatted = format_handoff_for_injection(handoff)
        print(formatted[:500] + "..." if len(formatted) > 500 else formatted)

    print()
    print("Self-test complete.")
