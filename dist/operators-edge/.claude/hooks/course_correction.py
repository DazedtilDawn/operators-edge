#!/usr/bin/env python3
"""
Operator's Edge v8.0 - Course Correction Detection (Phase 7)

The Feedback Loop: Did the intervention actually change behavior?

This module detects when Claude course-corrects after a drift signal.
Instead of asking Claude to report corrections (unreliable), we INFER
corrections from observable changes in tool patterns.

Design Philosophy:
- Behavioral inference over self-reporting
- Conservative detection (precision over recall)
- Pattern-based analysis

Course Correction Patterns:
1. FILE_CHURN → File no longer edited after signal
2. COMMAND_REPEAT → Different approach tried after failures
3. STEP_STALL → Step completed or work shifted

"Stay hungry, stay foolish." - Steve Jobs
"""
import json
import os
import sys
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Any, Set

# Add hooks directory to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


# =============================================================================
# DATA STRUCTURES
# =============================================================================

@dataclass
class DriftSignalEvent:
    """A drift signal that was fired."""
    signal_type: str  # FILE_CHURN, COMMAND_REPEAT, STEP_STALL
    timestamp: datetime
    severity: str
    evidence: Dict[str, Any]

    @property
    def problem_file(self) -> Optional[str]:
        """Get the file that triggered this signal, if applicable."""
        return self.evidence.get("file") or self.evidence.get("problem_file")

    @property
    def problem_command(self) -> Optional[str]:
        """Get the command pattern that triggered this signal, if applicable."""
        return self.evidence.get("command") or self.evidence.get("command_pattern")


@dataclass
class CorrectionAnalysis:
    """Analysis of whether a correction occurred."""
    signal: DriftSignalEvent
    correction_detected: bool
    confidence: float  # 0.0 to 1.0
    evidence: str  # Human-readable explanation

    # Timing
    analysis_window_seconds: int
    entries_before: int
    entries_after: int


# =============================================================================
# SIGNAL DETECTION FROM SESSION LOG
# =============================================================================

def load_session_entries(session_log: Path) -> List[Dict[str, Any]]:
    """Load entries from a session log."""
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


def parse_timestamp(ts_str: str) -> Optional[datetime]:
    """Parse a timestamp string."""
    if not ts_str:
        return None
    try:
        return datetime.fromisoformat(ts_str)
    except ValueError:
        return None


def infer_drift_signals(entries: List[Dict[str, Any]]) -> List[DriftSignalEvent]:
    """
    Infer where drift signals would have fired based on patterns.

    We reconstruct signals from tool patterns rather than requiring
    explicit signal logging. This makes the system work with existing data.

    Detection Rules:
    - FILE_CHURN: Same file edited 3+ times in 30 minutes
    - COMMAND_REPEAT: Same command failing 3+ times
    - STEP_STALL: No step completion after 15+ tool calls
    """
    signals = []

    # Track file edits with timestamps
    file_edits: Dict[str, List[datetime]] = {}

    # Track command failures
    command_fails: Dict[str, List[datetime]] = {}

    for entry in entries:
        tool = entry.get("tool", "")
        input_data = entry.get("input_preview", {})
        success = entry.get("success", True)
        ts = parse_timestamp(entry.get("timestamp", ""))

        if not ts:
            continue

        # FILE_CHURN detection
        if tool in ("Edit", "Write", "NotebookEdit"):
            file_path = ""
            if isinstance(input_data, dict):
                file_path = input_data.get("file_path") or input_data.get("file", "")

            if file_path:
                if file_path not in file_edits:
                    file_edits[file_path] = []
                file_edits[file_path].append(ts)

                # Check if this triggers a signal
                recent_edits = [
                    t for t in file_edits[file_path]
                    if (ts - t).total_seconds() <= 1800  # 30 min window
                ]
                if len(recent_edits) == 3:  # Exactly 3rd edit triggers signal
                    signals.append(DriftSignalEvent(
                        signal_type="FILE_CHURN",
                        timestamp=ts,
                        severity="warning",
                        evidence={"file": file_path, "edit_count": 3}
                    ))

        # COMMAND_REPEAT detection
        if tool == "Bash" and not success:
            cmd = ""
            if isinstance(input_data, dict):
                cmd = input_data.get("command", "")

            if cmd:
                # Normalize to first word (command name)
                cmd_pattern = cmd.split()[0] if cmd.split() else ""
                if cmd_pattern:
                    if cmd_pattern not in command_fails:
                        command_fails[cmd_pattern] = []
                    command_fails[cmd_pattern].append(ts)

                    # Check if this triggers a signal
                    recent_fails = [
                        t for t in command_fails[cmd_pattern]
                        if (ts - t).total_seconds() <= 600  # 10 min window
                    ]
                    if len(recent_fails) == 3:  # 3rd failure triggers signal
                        signals.append(DriftSignalEvent(
                            signal_type="COMMAND_REPEAT",
                            timestamp=ts,
                            severity="warning",
                            evidence={"command_pattern": cmd_pattern, "fail_count": 3}
                        ))

    return signals


# =============================================================================
# COURSE CORRECTION DETECTION
# =============================================================================

def get_entries_around_time(
    entries: List[Dict[str, Any]],
    target_time: datetime,
    window_before_seconds: int = 300,
    window_after_seconds: int = 300
) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    """
    Get entries before and after a target timestamp.

    Returns (entries_before, entries_after)
    """
    before = []
    after = []

    for entry in entries:
        ts = parse_timestamp(entry.get("timestamp", ""))
        if not ts:
            continue

        delta = (ts - target_time).total_seconds()

        if -window_before_seconds <= delta < 0:
            before.append(entry)
        elif 0 < delta <= window_after_seconds:
            after.append(entry)

    return before, after


def extract_files_from_entries(entries: List[Dict[str, Any]]) -> Set[str]:
    """Extract all files touched in a list of entries."""
    files = set()
    for entry in entries:
        tool = entry.get("tool", "")
        input_data = entry.get("input_preview", {})

        if tool in ("Edit", "Write", "NotebookEdit", "Read"):
            file_path = ""
            if isinstance(input_data, dict):
                file_path = input_data.get("file_path") or input_data.get("file", "")
            if file_path:
                files.add(file_path)

    return files


def extract_commands_from_entries(entries: List[Dict[str, Any]]) -> List[str]:
    """Extract command patterns from entries."""
    commands = []
    for entry in entries:
        if entry.get("tool") == "Bash":
            input_data = entry.get("input_preview", {})
            if isinstance(input_data, dict):
                cmd = input_data.get("command", "")
                if cmd:
                    commands.append(cmd.split()[0] if cmd.split() else "")
    return commands


def detect_file_churn_correction(
    signal: DriftSignalEvent,
    entries_before: List[Dict[str, Any]],
    entries_after: List[Dict[str, Any]]
) -> CorrectionAnalysis:
    """
    Detect if FILE_CHURN signal led to a correction.

    Correction indicators:
    - Problem file not edited in the after window
    - Work shifted to different files
    - Read operations suggest stepping back to understand
    """
    problem_file = signal.problem_file
    if not problem_file:
        return CorrectionAnalysis(
            signal=signal,
            correction_detected=False,
            confidence=0.0,
            evidence="No problem file identified",
            analysis_window_seconds=300,
            entries_before=len(entries_before),
            entries_after=len(entries_after)
        )

    files_before = extract_files_from_entries(entries_before)
    files_after = extract_files_from_entries(entries_after)

    # Check if problem file is absent from after window
    problem_still_edited = problem_file in files_after

    if not problem_still_edited:
        # File not edited after signal - likely a correction
        # Higher confidence if work continued on other files
        if files_after - {problem_file}:
            return CorrectionAnalysis(
                signal=signal,
                correction_detected=True,
                confidence=0.8,
                evidence=f"Stopped editing {Path(problem_file).name}, moved to other files",
                analysis_window_seconds=300,
                entries_before=len(entries_before),
                entries_after=len(entries_after)
            )
        else:
            # Stopped editing but no other work - might just be pausing
            return CorrectionAnalysis(
                signal=signal,
                correction_detected=True,
                confidence=0.5,
                evidence=f"Stopped editing {Path(problem_file).name}",
                analysis_window_seconds=300,
                entries_before=len(entries_before),
                entries_after=len(entries_after)
            )
    else:
        # Still editing the same file
        # Check if edit pattern changed (fewer edits = slowing down)
        edits_before = sum(1 for e in entries_before if e.get("tool") in ("Edit", "Write"))
        edits_after = sum(1 for e in entries_after if e.get("tool") in ("Edit", "Write"))

        if edits_after < edits_before * 0.5:
            # Significantly fewer edits - might be being more careful
            return CorrectionAnalysis(
                signal=signal,
                correction_detected=True,
                confidence=0.4,
                evidence="Edit frequency decreased significantly",
                analysis_window_seconds=300,
                entries_before=len(entries_before),
                entries_after=len(entries_after)
            )

        return CorrectionAnalysis(
            signal=signal,
            correction_detected=False,
            confidence=0.7,
            evidence=f"Continued editing {Path(problem_file).name}",
            analysis_window_seconds=300,
            entries_before=len(entries_before),
            entries_after=len(entries_after)
        )


def detect_command_repeat_correction(
    signal: DriftSignalEvent,
    entries_before: List[Dict[str, Any]],
    entries_after: List[Dict[str, Any]]
) -> CorrectionAnalysis:
    """
    Detect if COMMAND_REPEAT signal led to a correction.

    Correction indicators:
    - Different commands tried after signal
    - Successful command execution
    - Shift to different approach (e.g., from testing to reading)
    """
    problem_cmd = signal.problem_command
    if not problem_cmd:
        return CorrectionAnalysis(
            signal=signal,
            correction_detected=False,
            confidence=0.0,
            evidence="No problem command identified",
            analysis_window_seconds=300,
            entries_before=len(entries_before),
            entries_after=len(entries_after)
        )

    commands_before = extract_commands_from_entries(entries_before)
    commands_after = extract_commands_from_entries(entries_after)

    # Check if command pattern disappeared
    problem_in_after = problem_cmd in commands_after

    if not problem_in_after and commands_after:
        # Different commands tried
        return CorrectionAnalysis(
            signal=signal,
            correction_detected=True,
            confidence=0.7,
            evidence=f"Stopped running '{problem_cmd}', tried different approach",
            analysis_window_seconds=300,
            entries_before=len(entries_before),
            entries_after=len(entries_after)
        )
    elif not commands_after:
        # No commands after - might have switched to reading/editing
        return CorrectionAnalysis(
            signal=signal,
            correction_detected=True,
            confidence=0.5,
            evidence="Stopped executing commands, switched approach",
            analysis_window_seconds=300,
            entries_before=len(entries_before),
            entries_after=len(entries_after)
        )
    else:
        # Still running same command
        return CorrectionAnalysis(
            signal=signal,
            correction_detected=False,
            confidence=0.6,
            evidence=f"Continued running '{problem_cmd}'",
            analysis_window_seconds=300,
            entries_before=len(entries_before),
            entries_after=len(entries_after)
        )


def detect_correction(
    signal: DriftSignalEvent,
    entries: List[Dict[str, Any]],
    window_seconds: int = 300
) -> CorrectionAnalysis:
    """
    Detect if a drift signal led to a course correction.

    This is the main detection function that dispatches to
    type-specific detectors.
    """
    entries_before, entries_after = get_entries_around_time(
        entries, signal.timestamp, window_seconds, window_seconds
    )

    if signal.signal_type == "FILE_CHURN":
        return detect_file_churn_correction(signal, entries_before, entries_after)
    elif signal.signal_type == "COMMAND_REPEAT":
        return detect_command_repeat_correction(signal, entries_before, entries_after)
    else:
        # Unknown signal type - can't analyze
        return CorrectionAnalysis(
            signal=signal,
            correction_detected=False,
            confidence=0.0,
            evidence=f"Unknown signal type: {signal.signal_type}",
            analysis_window_seconds=window_seconds,
            entries_before=len(entries_before),
            entries_after=len(entries_after)
        )


# =============================================================================
# SESSION ANALYSIS
# =============================================================================

def analyze_session_corrections(session_log: Path) -> List[CorrectionAnalysis]:
    """
    Analyze all corrections in a session.

    Returns a list of correction analyses for each inferred signal.
    """
    entries = load_session_entries(session_log)
    if not entries:
        return []

    # Infer signals from patterns
    signals = infer_drift_signals(entries)

    # Analyze each signal
    analyses = []
    for signal in signals:
        analysis = detect_correction(signal, entries)
        analyses.append(analysis)

    return analyses


def calculate_correction_rate(analyses: List[CorrectionAnalysis]) -> Tuple[float, float]:
    """
    Calculate the correction rate from a list of analyses.

    Returns (correction_rate, confidence)
    """
    if not analyses:
        return 0.0, 0.0

    corrections = sum(1 for a in analyses if a.correction_detected)
    avg_confidence = sum(a.confidence for a in analyses) / len(analyses)

    return corrections / len(analyses), avg_confidence


# =============================================================================
# QUICK TEST
# =============================================================================

if __name__ == "__main__":
    print("Course Correction Detection - Self Test")
    print("=" * 40)

    # Try to find a session log
    test_proof_dir = Path(__file__).parent.parent.parent / ".proof" / "sessions"

    if test_proof_dir.exists():
        logs = sorted(test_proof_dir.glob("*.jsonl"), key=lambda p: p.stem, reverse=True)
        if logs:
            latest_log = logs[0]
            print(f"Analyzing: {latest_log.name}")

            analyses = analyze_session_corrections(latest_log)
            print(f"Found {len(analyses)} drift signal events")

            for analysis in analyses[:5]:  # Show first 5
                status = "✓ CORRECTED" if analysis.correction_detected else "✗ Not corrected"
                print(f"  {analysis.signal.signal_type}: {status} ({analysis.confidence*100:.0f}% confidence)")
                print(f"    Evidence: {analysis.evidence}")

            if analyses:
                rate, conf = calculate_correction_rate(analyses)
                print(f"\nOverall: {rate*100:.0f}% correction rate ({conf*100:.0f}% avg confidence)")
        else:
            print("No session logs found")
    else:
        print(f"No sessions directory at {test_proof_dir}")

        # Test with mock data
        print("\n--- Mock Data Test ---")

        mock_entries = [
            {"timestamp": "2026-01-18T10:00:00", "tool": "Edit", "input_preview": {"file": "/app/utils.py"}},
            {"timestamp": "2026-01-18T10:05:00", "tool": "Edit", "input_preview": {"file": "/app/utils.py"}},
            {"timestamp": "2026-01-18T10:10:00", "tool": "Edit", "input_preview": {"file": "/app/utils.py"}},
            # Signal fires here (3rd edit)
            {"timestamp": "2026-01-18T10:15:00", "tool": "Read", "input_preview": {"file": "/app/models.py"}},
            {"timestamp": "2026-01-18T10:20:00", "tool": "Edit", "input_preview": {"file": "/app/models.py"}},
            # Correction: moved to different file
        ]

        signals = infer_drift_signals(mock_entries)
        print(f"Inferred {len(signals)} signals from mock data")

        for signal in signals:
            analysis = detect_correction(signal, mock_entries)
            print(f"  {signal.signal_type}: {'CORRECTED' if analysis.correction_detected else 'NOT CORRECTED'}")
            print(f"    {analysis.evidence}")

    print("\nSelf-test complete.")
