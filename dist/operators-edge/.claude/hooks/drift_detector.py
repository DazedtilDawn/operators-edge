#!/usr/bin/env python3
"""
Operator's Edge v8.0 - Drift Detector (Proof of Concept)

Detects when Claude is going in circles or drifting from the objective.

Drift Signals:
1. FILE_CHURN - Same file edited multiple times in short span
2. COMMAND_REPEAT - Same command run multiple times with failures
3. STEP_STALL - Current step taking much longer than average
4. OBJECTIVE_DRIFT - Actions don't relate to stated objective

This is supervision, not training.
"""
import json
import os
import sys
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from collections import Counter, defaultdict

# Add hooks directory to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


@dataclass
class DriftSignal:
    """A detected drift pattern."""
    signal_type: str  # FILE_CHURN, COMMAND_REPEAT, STEP_STALL, OBJECTIVE_DRIFT
    severity: str     # info, warning, critical
    message: str      # Human-readable description
    evidence: dict    # Supporting data
    suggestion: str   # What to do about it


# =============================================================================
# SESSION LOG ANALYSIS
# =============================================================================

def load_recent_session_entries(
    session_log: Path,
    lookback_minutes: int = 30
) -> List[dict]:
    """Load recent entries from session log."""
    if not session_log.exists():
        return []

    cutoff = datetime.now() - timedelta(minutes=lookback_minutes)
    entries = []

    try:
        with open(session_log) as f:
            for line in f:
                if not line.strip():
                    continue
                try:
                    entry = json.loads(line)
                    # Parse timestamp
                    ts_str = entry.get("timestamp", "")
                    if ts_str:
                        ts = datetime.fromisoformat(ts_str.replace("Z", "+00:00"))
                        if ts.replace(tzinfo=None) >= cutoff:
                            entries.append(entry)
                except (json.JSONDecodeError, ValueError):
                    continue
    except Exception:
        return []

    return entries


def extract_file_edits(entries: List[dict]) -> List[Tuple[str, datetime]]:
    """Extract file edit events from session entries."""
    edits = []
    for entry in entries:
        tool = entry.get("tool", "")
        if tool in ("Edit", "Write", "NotebookEdit"):
            input_data = entry.get("input_preview", {})

            # Extract file path - handle different formats
            file_path = None
            if isinstance(input_data, dict):
                # Try common keys: file_path, file, path
                file_path = (
                    input_data.get("file_path") or
                    input_data.get("file") or
                    input_data.get("path")
                )
            elif isinstance(input_data, str):
                # Try to extract from string representation
                import re
                match = re.search(r"(?:file_path|file|path)['\"]?\s*[:=]\s*['\"]?([^'\"}\s,]+)", input_data)
                file_path = match.group(1) if match else None

            if not file_path:
                continue

            ts_str = entry.get("timestamp", "")
            try:
                ts = datetime.fromisoformat(ts_str.replace("Z", "+00:00"))
                edits.append((file_path, ts.replace(tzinfo=None)))
            except ValueError:
                pass

    return edits


def extract_bash_commands(entries: List[dict]) -> List[Tuple[str, bool, datetime]]:
    """Extract bash command events with success/failure status."""
    commands = []
    for entry in entries:
        tool = entry.get("tool", "")
        if tool == "Bash":
            cmd = entry.get("input_preview", "")
            if isinstance(cmd, dict):
                cmd = cmd.get("command", str(cmd))
            success = entry.get("success", True)

            ts_str = entry.get("timestamp", "")
            try:
                ts = datetime.fromisoformat(ts_str.replace("Z", "+00:00"))
                commands.append((str(cmd)[:200], success, ts.replace(tzinfo=None)))
            except ValueError:
                pass

    return commands


# =============================================================================
# DRIFT DETECTION
# =============================================================================

def detect_file_churn(
    entries: List[dict],
    threshold: int = 3,
    window_minutes: int = 10
) -> Optional[DriftSignal]:
    """
    Detect when the same file is being edited repeatedly.

    This often indicates Claude is making incremental fixes instead of
    understanding the root cause.
    """
    edits = extract_file_edits(entries)
    if not edits:
        return None

    # Count edits per file
    file_counts = Counter(path for path, _ in edits)

    # Find files edited more than threshold times
    churned = [(f, c) for f, c in file_counts.items() if c >= threshold]

    if not churned:
        return None

    # Get the most churned file
    worst_file, count = max(churned, key=lambda x: x[1])

    return DriftSignal(
        signal_type="FILE_CHURN",
        severity="warning" if count < 5 else "critical",
        message=f"You've edited `{worst_file}` {count} times recently.",
        evidence={
            "file": worst_file,
            "edit_count": count,
            "all_churned": dict(churned)
        },
        suggestion=(
            "Consider stepping back to understand the root cause. "
            "What are you trying to achieve with each edit? "
            "Is there a pattern to the changes that suggests a different approach?"
        )
    )


def detect_command_repeat(
    entries: List[dict],
    threshold: int = 2
) -> Optional[DriftSignal]:
    """
    Detect when the same command is being run repeatedly with failures.

    This indicates Claude is hoping for a different result without changing approach.
    """
    commands = extract_bash_commands(entries)
    if not commands:
        return None

    # Group commands by similarity (first 100 chars)
    command_results = defaultdict(list)
    for cmd, success, ts in commands:
        cmd_key = cmd[:100]
        command_results[cmd_key].append(success)

    # Find commands with multiple failures
    repeated_failures = []
    for cmd, results in command_results.items():
        failures = sum(1 for r in results if not r)
        if failures >= threshold:
            repeated_failures.append((cmd, failures, len(results)))

    if not repeated_failures:
        return None

    worst_cmd, failures, total = max(repeated_failures, key=lambda x: x[1])

    return DriftSignal(
        signal_type="COMMAND_REPEAT",
        severity="warning" if failures < 3 else "critical",
        message=f"Command failed {failures}/{total} times: `{worst_cmd[:60]}...`",
        evidence={
            "command_preview": worst_cmd,
            "failure_count": failures,
            "total_attempts": total
        },
        suggestion=(
            "This command keeps failing. Before retrying, ask: "
            "What specifically is failing? Is the error message telling you something? "
            "What would need to be true for this to succeed?"
        )
    )


def detect_step_stall(
    state: dict,
    entries: List[dict],
    stall_multiplier: float = 3.0
) -> Optional[DriftSignal]:
    """
    Detect when the current step is taking much longer than average.

    This might indicate Claude is stuck but not recognizing it.
    """
    plan = state.get("plan", [])
    current_step = state.get("current_step", 0)

    if not plan or current_step <= 0:
        return None

    # Count tool calls in this session
    tool_calls = len(entries)

    # Get completed steps to estimate average
    completed_steps = [
        s for s in plan
        if isinstance(s, dict) and s.get("status") == "completed"
    ]

    if len(completed_steps) < 2:
        # Not enough history to compare
        return None

    # Estimate: if we've made many tool calls without completing the step,
    # we might be stalled. Use tool_calls as proxy for "effort"
    avg_effort = tool_calls / max(1, len(completed_steps))

    # If we're on current step and have exceeded average by multiplier
    current_in_progress = any(
        s.get("status") == "in_progress"
        for s in plan
        if isinstance(s, dict)
    )

    if not current_in_progress:
        return None

    # Check if current step seems stalled (many recent tool calls)
    recent_for_current = len([
        e for e in entries
        if e.get("tool") in ("Edit", "Write", "Bash", "Read")
    ])

    if recent_for_current < avg_effort * stall_multiplier:
        return None

    return DriftSignal(
        signal_type="STEP_STALL",
        severity="info",
        message=f"Current step has {recent_for_current} operations (avg: {avg_effort:.1f}).",
        evidence={
            "current_step": current_step,
            "operations_this_step": recent_for_current,
            "average_per_step": round(avg_effort, 1)
        },
        suggestion=(
            "This step is taking longer than usual. Consider: "
            "Is the step too broad? Should it be split? "
            "Are you blocked by something that should be a mismatch?"
        )
    )


# =============================================================================
# CONFIGURABLE THRESHOLDS (v8.0 Phase 7)
# =============================================================================

DEFAULT_THRESHOLDS = {
    "file_churn": 3,
    "command_repeat": 2,
    "stall_multiplier": 3.0,
}


def load_thresholds() -> dict:
    """
    Load drift detection thresholds from config.

    Thresholds can be tuned via /edge metrics --tune based on
    effectiveness analysis from Phase 7.
    """
    config_path = Path(__file__).parent.parent.parent / ".proof" / "v8_config.json"

    if config_path.exists():
        try:
            with open(config_path) as f:
                config = json.load(f)
                thresholds = config.get("thresholds", {})
                # Merge with defaults
                return {**DEFAULT_THRESHOLDS, **thresholds}
        except (json.JSONDecodeError, OSError):
            pass

    return DEFAULT_THRESHOLDS.copy()


# =============================================================================
# MAIN DETECTION INTERFACE
# =============================================================================

def detect_drift(
    session_log: Path,
    state: dict,
    lookback_minutes: int = 30,
    thresholds: Optional[dict] = None
) -> List[DriftSignal]:
    """
    Run all drift detectors and return any signals.

    This is the main entry point called from PostToolUse hook.

    Args:
        session_log: Path to session log file
        state: Current YAML state
        lookback_minutes: How far back to analyze
        thresholds: Optional threshold overrides (loads from config if None)
    """
    entries = load_recent_session_entries(session_log, lookback_minutes)

    if not entries:
        return []

    # Load thresholds from config if not provided
    if thresholds is None:
        thresholds = load_thresholds()

    signals = []

    # Check for file churn (uses configurable threshold)
    churn = detect_file_churn(entries, threshold=thresholds.get("file_churn", 3))
    if churn:
        signals.append(churn)

    # Check for command repetition (uses configurable threshold)
    repeat = detect_command_repeat(entries, threshold=thresholds.get("command_repeat", 2))
    if repeat:
        signals.append(repeat)

    # Check for step stall (uses configurable multiplier)
    stall = detect_step_stall(state, entries, stall_multiplier=thresholds.get("stall_multiplier", 3.0))
    if stall:
        signals.append(stall)

    return signals


def format_drift_intervention(signals: List[DriftSignal]) -> str:
    """
    Format drift signals into an intervention message for Claude.
    """
    if not signals:
        return ""

    # Sort by severity
    severity_order = {"critical": 0, "warning": 1, "info": 2}
    signals.sort(key=lambda s: severity_order.get(s.severity, 3))

    lines = [
        "",
        "=" * 60,
        "⚠️  DRIFT DETECTED - Supervision Intervention",
        "=" * 60,
        ""
    ]

    for signal in signals:
        icon = {"critical": "🔴", "warning": "🟡", "info": "🔵"}.get(signal.severity, "⚪")
        lines.extend([
            f"{icon} {signal.signal_type}: {signal.message}",
            "",
            f"   Suggestion: {signal.suggestion}",
            ""
        ])

    lines.extend([
        "-" * 60,
        "Take a moment to assess: Are you making progress toward the objective?",
        "-" * 60,
        ""
    ])

    return "\n".join(lines)


# =============================================================================
# QUICK TEST
# =============================================================================

if __name__ == "__main__":
    # Self-test with simulated data
    print("Drift Detector - Self Test")
    print("=" * 40)

    # Simulate file churn
    fake_entries = []
    base_time = datetime.now()
    for i in range(5):
        fake_entries.append({
            "tool": "Edit",
            "input_preview": {"file_path": "/app/utils.py"},
            "timestamp": (base_time - timedelta(minutes=i)).isoformat(),
            "success": True
        })

    signal = detect_file_churn(fake_entries, threshold=3)
    if signal:
        print(f"✓ File churn detected: {signal.message}")
    else:
        print("✗ File churn not detected")

    # Simulate command repeat
    fake_entries = []
    for i in range(3):
        fake_entries.append({
            "tool": "Bash",
            "input_preview": "npm test",
            "timestamp": (base_time - timedelta(minutes=i)).isoformat(),
            "success": False
        })

    signal = detect_command_repeat(fake_entries, threshold=2)
    if signal:
        print(f"✓ Command repeat detected: {signal.message}")
    else:
        print("✗ Command repeat not detected")

    print()
    print("Self-test complete.")
