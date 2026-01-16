#!/usr/bin/env python3
"""
Operator's Edge - Proof Utilities
Session-scoped, atomic, recoverable proof logging.

Design Philosophy:
  "The user should never be trapped. Even if every system fails,
   there must be a path forward."

This module provides:
  - Atomic proof logging (lock + temp file + rename)
  - Session-scoped log files (bounded growth)
  - Recovery from missing/corrupted logs
  - Backward compatibility via symlink
"""

import json
import os
from contextlib import contextmanager
from datetime import datetime, timedelta
from pathlib import Path

# Import existing patterns from state_utils
from state_utils import (
    get_proof_dir,
    get_state_dir,
    get_project_dir,
    file_lock,
    atomic_write_text,
    get_start_hash,
    file_hash,
    DEFAULT_LOCK_TIMEOUT,
)


# =============================================================================
# CONSTANTS
# =============================================================================

MAX_SESSION_AGE_DAYS = 7        # Archive sessions older than this
BACKWARD_COMPAT_SYMLINK = True  # Maintain session_log.jsonl symlink


# =============================================================================
# SESSION MANAGEMENT
# =============================================================================

def get_sessions_dir() -> Path:
    """Get the sessions directory for session-scoped logs."""
    return get_proof_dir() / "sessions"


def get_current_session_id() -> str:
    """
    Get the current session ID.

    Returns the session ID from state directory if available,
    otherwise generates a new one from the current timestamp.
    """
    session_file = get_state_dir() / "session_id"
    if session_file.exists():
        try:
            return session_file.read_text().strip()
        except Exception:
            pass

    # Fallback: generate new session ID from timestamp
    return datetime.now().strftime("%Y%m%d-%H%M%S")


def save_session_id(session_id: str) -> None:
    """Save the current session ID to state directory."""
    state_dir = get_state_dir()
    state_dir.mkdir(parents=True, exist_ok=True)
    session_file = state_dir / "session_id"
    session_file.write_text(session_id)


def get_session_log_path(session_id: str = None) -> Path:
    """
    Get the log path for a specific session.

    If session_id is None, uses the current session.
    Creates the sessions directory if it doesn't exist.
    """
    if session_id is None:
        session_id = get_current_session_id()

    sessions_dir = get_sessions_dir()
    sessions_dir.mkdir(parents=True, exist_ok=True)

    return sessions_dir / f"{session_id}.jsonl"


def get_legacy_log_path() -> Path:
    """Get the legacy session_log.jsonl path for backward compatibility."""
    return get_proof_dir() / "session_log.jsonl"


# =============================================================================
# ATOMIC PROOF LOGGING
# =============================================================================

def log_proof_entry(tool_name: str, tool_input, result, success: bool) -> dict:
    """
    Log a proof entry atomically to the session log.

    Uses lock + atomic write pattern:
    1. Acquire lock on session log
    2. Read existing content
    3. Append new entry
    4. Atomic write via temp file + rename
    5. Release lock

    Args:
        tool_name: Name of the tool (Bash, Edit, Write, etc.)
        tool_input: The input provided to the tool
        result: The output/result from the tool
        success: Whether the tool execution succeeded

    Returns:
        The entry that was logged (dict)
    """
    session_id = get_current_session_id()
    log_path = get_session_log_path(session_id)

    # Build entry
    timestamp = datetime.now().isoformat()

    # Preserve dict structure if it's a dict (for Edit old_string/new_string)
    # Otherwise convert to string preview
    if isinstance(tool_input, dict):
        input_data = tool_input
    else:
        input_data = str(tool_input)[:500]

    entry = {
        "timestamp": timestamp,
        "tool": tool_name,
        "input_preview": input_data,
        "success": success,
        "output_preview": str(result)[:1000] if result else None,
        "session_id": session_id
    }

    try:
        with file_lock(log_path, timeout_seconds=DEFAULT_LOCK_TIMEOUT):
            # Read existing content
            existing = ""
            if log_path.exists():
                try:
                    existing = log_path.read_text()
                except Exception:
                    existing = ""

            # Append new entry
            new_content = existing
            if new_content and not new_content.endswith('\n'):
                new_content += '\n'
            new_content += json.dumps(entry) + '\n'

            # Atomic write (temp file + rename + fsync)
            atomic_write_text(log_path, new_content)

    except TimeoutError:
        # If we can't acquire lock, fall back to simple append
        # This is a degraded mode but ensures proof is captured
        log_path.parent.mkdir(parents=True, exist_ok=True)
        with open(log_path, "a") as f:
            f.write(json.dumps(entry) + "\n")

    # Update legacy symlink for backward compatibility
    if BACKWARD_COMPAT_SYMLINK:
        _update_legacy_symlink(log_path)

    return entry


def _update_legacy_symlink(target_path: Path) -> None:
    """
    Update the legacy session_log.jsonl symlink to point to current session.

    On platforms that don't support symlinks (Windows), creates a small
    redirect file instead.
    """
    legacy_path = get_legacy_log_path()

    try:
        # Remove existing symlink/file
        if legacy_path.exists() or legacy_path.is_symlink():
            legacy_path.unlink()

        # Create relative symlink
        rel_target = target_path.relative_to(legacy_path.parent)
        legacy_path.symlink_to(rel_target)

    except (OSError, NotImplementedError):
        # Windows or symlink not supported - copy approach
        # Just leave the legacy file as-is; backward compat is best-effort
        pass


# =============================================================================
# PROOF VERIFICATION
# =============================================================================

def check_proof_for_session(session_id: str = None) -> tuple:
    """
    Check if proof exists for a session.

    Args:
        session_id: The session to check (defaults to current)

    Returns:
        Tuple of (exists: bool, message: str, entry_count: int)
    """
    if session_id is None:
        session_id = get_current_session_id()

    log_path = get_session_log_path(session_id)

    # Check session-specific log first
    if log_path.exists():
        try:
            content = log_path.read_text().strip()
            if content:
                entries = [l for l in content.split('\n') if l.strip()]
                return (True, f"Proof log has {len(entries)} entries", len(entries))
            else:
                return (False, "Proof log is empty.", 0)
        except Exception as e:
            return (False, f"Error reading proof log: {e}", 0)

    # Check legacy log as fallback
    legacy_path = get_legacy_log_path()
    if legacy_path.exists() and not legacy_path.is_symlink():
        try:
            content = legacy_path.read_text().strip()
            if content:
                entries = [l for l in content.split('\n') if l.strip()]
                return (True, f"Proof log (legacy) has {len(entries)} entries", len(entries))
        except Exception:
            pass

    return (False, "No proof log exists for this session.", 0)


def count_proof_entries(session_id: str = None) -> int:
    """Count the number of proof entries for a session."""
    exists, _, count = check_proof_for_session(session_id)
    return count if exists else 0


# =============================================================================
# RECOVERY MECHANISM
# =============================================================================

def recover_proof_from_state() -> tuple:
    """
    Attempt to recover proof when session log is missing.

    Recovery strategy:
    1. Check if state (active_context.yaml) was modified (hash changed)
    2. If so, create a minimal recovery entry documenting the modification
    3. This allows the session to end gracefully

    Returns:
        Tuple of (recovered: bool, message: str)
    """
    session_id = get_current_session_id()

    # Check if state was modified
    start_hash = get_start_hash()
    if not start_hash:
        return (False, "No session start hash available for recovery")

    yaml_file = get_project_dir() / "active_context.yaml"
    if not yaml_file.exists():
        return (False, "State file missing, cannot recover")

    try:
        current_hash = file_hash(yaml_file)
    except Exception as e:
        return (False, f"Cannot compute state hash: {e}")

    if current_hash == start_hash:
        return (False, "No state modification detected, cannot recover proof")

    # State was modified - create recovery entry
    recovery_entry = {
        "timestamp": datetime.now().isoformat(),
        "tool": "_recovery",
        "input_preview": {
            "reason": "proof_log_recovery",
            "state_hash_start": start_hash[:16] + "...",
            "state_hash_current": current_hash[:16] + "...",
        },
        "success": True,
        "output_preview": "Proof recovered from state modification evidence",
        "session_id": session_id,
        "recovery": True
    }

    log_path = get_session_log_path(session_id)
    log_path.parent.mkdir(parents=True, exist_ok=True)

    try:
        with file_lock(log_path, timeout_seconds=DEFAULT_LOCK_TIMEOUT):
            atomic_write_text(log_path, json.dumps(recovery_entry) + '\n')
    except TimeoutError:
        # Fallback to simple write
        with open(log_path, "w") as f:
            f.write(json.dumps(recovery_entry) + '\n')

    # Update legacy symlink
    if BACKWARD_COMPAT_SYMLINK:
        _update_legacy_symlink(log_path)

    return (True, "Proof recovered from state modification evidence")


def graceful_fallback() -> tuple:
    """
    Ultimate fallback when all else fails.

    Philosophy: The user should NEVER be trapped.

    If state was modified but recovery failed, allow exit with warning.
    This is the safety valve that ensures users can always exit.

    Returns:
        Tuple of (should_allow: bool, message: str)
    """
    start_hash = get_start_hash()

    if start_hash is None:
        # No session tracking - allow exit
        return (True, "No session tracking (session_start may not have run)")

    yaml_file = get_project_dir() / "active_context.yaml"
    if not yaml_file.exists():
        return (False, "State file missing")

    try:
        current_hash = file_hash(yaml_file)
        if current_hash != start_hash:
            return (True,
                "WARNING: Proof log missing but state was modified. "
                "Session allowed to end to avoid trapping user.")
    except Exception:
        pass

    return (False, "No evidence of work in this session")


# =============================================================================
# SESSION LIFECYCLE
# =============================================================================

def initialize_proof_session(session_id: str = None) -> str:
    """
    Initialize the proof system for a new session.

    Called by session_start.py to set up session-scoped logging.

    Args:
        session_id: Optional explicit session ID (defaults to timestamp)

    Returns:
        The session ID that was initialized
    """
    if session_id is None:
        session_id = datetime.now().strftime("%Y%m%d-%H%M%S")

    # Save session ID
    save_session_id(session_id)

    # Ensure sessions directory exists
    sessions_dir = get_sessions_dir()
    sessions_dir.mkdir(parents=True, exist_ok=True)

    # Create empty session log
    log_path = sessions_dir / f"{session_id}.jsonl"
    if not log_path.exists():
        log_path.touch()

    # Update legacy symlink
    if BACKWARD_COMPAT_SYMLINK:
        _update_legacy_symlink(log_path)

    return session_id


# =============================================================================
# RETENTION / ARCHIVAL
# =============================================================================

def archive_old_sessions(days_threshold: int = MAX_SESSION_AGE_DAYS) -> int:
    """
    Archive session logs older than threshold.

    Merges old session entries into archive.jsonl and removes the session files.

    Args:
        days_threshold: Sessions older than this are archived

    Returns:
        Count of sessions archived
    """
    sessions_dir = get_sessions_dir()
    if not sessions_dir.exists():
        return 0

    cutoff = datetime.now() - timedelta(days=days_threshold)
    archived = 0

    for log_file in sessions_dir.glob("*.jsonl"):
        try:
            # Parse session ID as date
            session_id = log_file.stem
            # Format: 20260113-091500
            session_date = datetime.strptime(session_id, "%Y%m%d-%H%M%S")

            if session_date < cutoff:
                # Merge entries to main archive
                _merge_session_to_archive(log_file)
                log_file.unlink()
                archived += 1
        except (ValueError, OSError):
            # Skip files that don't match expected format
            continue

    return archived


def _merge_session_to_archive(session_log: Path) -> None:
    """Merge a session log's entries into the main archive."""
    from archive_utils import log_to_archive

    try:
        content = session_log.read_text()
        for line in content.strip().split('\n'):
            if not line.strip():
                continue
            try:
                entry = json.loads(line)
                log_to_archive("session_entry", entry)
            except json.JSONDecodeError:
                continue
    except Exception:
        pass  # Best effort archival


def get_all_sessions() -> list:
    """
    Get metadata for all session logs.

    Returns:
        List of dicts with session_id, entry_count, first_entry, last_entry
    """
    sessions_dir = get_sessions_dir()
    if not sessions_dir.exists():
        return []

    sessions = []
    for log_file in sorted(sessions_dir.glob("*.jsonl"), reverse=True):
        session_id = log_file.stem
        try:
            content = log_file.read_text().strip()
            lines = [l for l in content.split('\n') if l.strip()]

            first_ts = None
            last_ts = None
            if lines:
                try:
                    first_entry = json.loads(lines[0])
                    first_ts = first_entry.get("timestamp")
                except Exception:
                    pass
                try:
                    last_entry = json.loads(lines[-1])
                    last_ts = last_entry.get("timestamp")
                except Exception:
                    pass

            sessions.append({
                "session_id": session_id,
                "entry_count": len(lines),
                "first_entry": first_ts,
                "last_entry": last_ts,
                "path": str(log_file)
            })
        except Exception:
            sessions.append({
                "session_id": session_id,
                "entry_count": 0,
                "first_entry": None,
                "last_entry": None,
                "path": str(log_file),
                "error": True
            })

    return sessions


# =============================================================================
# PROOF VITALITY (v3.10.1 - Proof-Grounded Memory)
# =============================================================================

def get_proof_vitality(trigger: str, days_lookback: int = 14) -> dict:
    """
    Check proof logs for lesson usage evidence.

    When claims (reinforced count in YAML) and observations (lesson_match in proof)
    conflict, observations win. This function checks proof logs to determine if
    a lesson has been actively used, regardless of what the YAML claims.

    Args:
        trigger: The lesson trigger to look for (e.g., "hooks", "paths")
        days_lookback: How many days of proof logs to scan

    Returns:
        dict with:
            - matches: int - number of times lesson was matched
            - last_match: str - ISO timestamp of most recent match
            - sessions: list - session IDs where matches occurred
    """
    sessions_dir = get_sessions_dir()
    if not sessions_dir.exists():
        return {"matches": 0, "last_match": None, "sessions": []}

    cutoff = datetime.now() - timedelta(days=days_lookback)
    matches = 0
    last_match = None
    sessions_with_matches = []

    # Scan all session logs within lookback period
    for log_file in sessions_dir.glob("*.jsonl"):
        try:
            # Parse session ID as date
            session_id = log_file.stem
            # Format: 20260113-091500
            session_date = datetime.strptime(session_id, "%Y%m%d-%H%M%S")

            if session_date < cutoff:
                continue  # Skip old sessions

            # Read and parse entries
            content = log_file.read_text()
            for line in content.strip().split('\n'):
                if not line.strip():
                    continue

                try:
                    entry = json.loads(line)

                    # Look for lesson_match entries
                    if entry.get("tool") == "lesson_match":
                        input_data = entry.get("input_preview", {})
                        if isinstance(input_data, dict):
                            triggers = input_data.get("triggers", [])
                            if trigger in triggers:
                                matches += 1
                                ts = entry.get("timestamp")
                                if ts and (last_match is None or ts > last_match):
                                    last_match = ts
                                if session_id not in sessions_with_matches:
                                    sessions_with_matches.append(session_id)
                except json.JSONDecodeError:
                    continue

        except (ValueError, OSError):
            continue

    return {
        "matches": matches,
        "last_match": last_match,
        "sessions": sessions_with_matches
    }


def check_lesson_vitality(trigger: str, threshold: int = 1, days_lookback: int = 14) -> tuple:
    """
    Check if a lesson has proof-based vitality above threshold.

    This is the key function for proof-grounded decay decisions:
    - If proof shows recent matches >= threshold, lesson is vital (protected from decay)
    - If proof shows no matches, defer to YAML claims

    Args:
        trigger: The lesson trigger to check
        threshold: Minimum matches required for vitality
        days_lookback: How many days of proof to scan

    Returns:
        Tuple of (is_vital: bool, reason: str)
    """
    vitality = get_proof_vitality(trigger, days_lookback)

    if vitality["matches"] >= threshold:
        return (True, f"Proof shows {vitality['matches']} matches in last {days_lookback} days")

    return (False, f"No proof vitality (0 matches in last {days_lookback} days)")


# =============================================================================
# PROOF VALIDATION
# =============================================================================

def validate_proof_integrity(session_id: str = None) -> tuple:
    """
    Validate the integrity of a session's proof log.

    Checks:
    - File exists and is readable
    - All lines are valid JSON
    - Required fields present in each entry
    - Timestamps are monotonically increasing

    Args:
        session_id: Session to validate (defaults to current)

    Returns:
        Tuple of (valid: bool, issues: list[str])
    """
    if session_id is None:
        session_id = get_current_session_id()

    log_path = get_session_log_path(session_id)
    issues = []

    if not log_path.exists():
        return (False, ["Proof log does not exist"])

    try:
        content = log_path.read_text()
    except Exception as e:
        return (False, [f"Cannot read proof log: {e}"])

    if not content.strip():
        return (False, ["Proof log is empty"])

    lines = content.strip().split('\n')
    last_ts = None
    required_fields = {"timestamp", "tool", "success"}

    for i, line in enumerate(lines, 1):
        if not line.strip():
            continue

        try:
            entry = json.loads(line)
        except json.JSONDecodeError as e:
            issues.append(f"Line {i}: Invalid JSON - {e}")
            continue

        # Check required fields
        missing = required_fields - set(entry.keys())
        if missing:
            issues.append(f"Line {i}: Missing fields: {missing}")

        # Check timestamp ordering
        ts = entry.get("timestamp")
        if ts and last_ts and ts < last_ts:
            issues.append(f"Line {i}: Timestamp not monotonic ({ts} < {last_ts})")
        last_ts = ts

    return (len(issues) == 0, issues)


# =============================================================================
# SIMPLIFIED LOGGING (v3.11 - Mechanical Learning)
# =============================================================================

def log_to_session(entry: dict) -> dict:
    """
    Log a structured entry to the current session log.

    This is a simplified logging function for non-tool events like:
    - Obligation created/resolved
    - Lesson matches
    - Learning metrics

    Args:
        entry: Dict with event data (must include 'type' key)

    Returns:
        The entry that was logged (with timestamp added)
    """
    session_id = get_current_session_id()
    log_path = get_session_log_path(session_id)

    # Ensure required fields
    entry = {
        "timestamp": datetime.now().isoformat(),
        "session_id": session_id,
        "tool": entry.get("type", "event"),  # Use 'type' as 'tool' for consistency
        "input_preview": entry,
        "success": True,
        **entry
    }

    try:
        with file_lock(log_path, timeout_seconds=DEFAULT_LOCK_TIMEOUT):
            existing = ""
            if log_path.exists():
                try:
                    existing = log_path.read_text()
                except Exception:
                    existing = ""

            new_content = existing
            if new_content and not new_content.endswith('\n'):
                new_content += '\n'
            new_content += json.dumps(entry) + '\n'

            atomic_write_text(log_path, new_content)

    except TimeoutError:
        log_path.parent.mkdir(parents=True, exist_ok=True)
        with open(log_path, "a") as f:
            f.write(json.dumps(entry) + "\n")

    return entry


# =============================================================================
# LEARNING METRICS (v3.11 - Mechanical Learning)
# =============================================================================

def calculate_learning_metrics(days_lookback: int = 14) -> dict:
    """
    Calculate learning metrics from obligation logs.

    Metrics:
    - LAR (Lesson Application Rate): applied / surfaced
    - RWR (Rework Rate): violated / applied
    - JB (Junction Burden): junctions / sessions
    - Total counts for each obligation status

    Args:
        days_lookback: How many days of proof logs to scan

    Returns:
        dict with metrics and counts
    """
    sessions_dir = get_sessions_dir()
    if not sessions_dir.exists():
        return {
            "lar": 0.0,
            "rwr": 0.0,
            "jb": 0.0,
            "counts": {
                "created": 0,
                "applied": 0,
                "dismissed": 0,
                "violated": 0
            },
            "sessions_scanned": 0
        }

    cutoff = datetime.now() - timedelta(days=days_lookback)
    counts = {
        "created": 0,
        "applied": 0,
        "dismissed": 0,
        "violated": 0
    }
    junction_count = 0
    sessions_scanned = 0

    # Scan all session logs within lookback period
    for log_file in sessions_dir.glob("*.jsonl"):
        try:
            session_id = log_file.stem
            session_date = datetime.strptime(session_id, "%Y%m%d-%H%M%S")

            if session_date < cutoff:
                continue

            sessions_scanned += 1

            # Read and parse entries
            content = log_file.read_text()
            for line in content.strip().split('\n'):
                if not line.strip():
                    continue

                try:
                    entry = json.loads(line)
                    tool = entry.get("tool", "")

                    # Count obligation events
                    if tool.startswith("obligation:"):
                        event_type = tool.split(":")[1]
                        if event_type in counts:
                            counts[event_type] += 1

                    # Count junctions
                    if tool == "junction" or entry.get("type", "").startswith("junction"):
                        junction_count += 1

                except json.JSONDecodeError:
                    continue

        except (ValueError, OSError):
            continue

    # Calculate rates
    surfaced = counts["created"]
    applied = counts["applied"]
    violated = counts["violated"]

    lar = (applied / surfaced) if surfaced > 0 else 0.0
    rwr = (violated / applied) if applied > 0 else 0.0
    jb = (junction_count / sessions_scanned) if sessions_scanned > 0 else 0.0

    return {
        "lar": round(lar, 3),
        "rwr": round(rwr, 3),
        "jb": round(jb, 3),
        "counts": counts,
        "junctions": junction_count,
        "sessions_scanned": sessions_scanned
    }


def format_learning_metrics(metrics: dict = None) -> str:
    """
    Format learning metrics for display.

    Args:
        metrics: Optional pre-calculated metrics (calls calculate_learning_metrics if None)

    Returns:
        Formatted string for CLI display
    """
    if metrics is None:
        metrics = calculate_learning_metrics()

    lines = [
        "-" * 50,
        "LEARNING METRICS (v3.11)",
        "-" * 50,
        "",
        f"LAR (Lesson Application Rate): {metrics['lar']:.1%}",
        f"  Applied: {metrics['counts']['applied']} / Surfaced: {metrics['counts']['created']}",
        "",
        f"RWR (Rework Rate): {metrics['rwr']:.1%}",
        f"  Violated: {metrics['counts']['violated']} / Applied: {metrics['counts']['applied']}",
        "",
        f"Dismissed: {metrics['counts']['dismissed']}",
        f"Junction Burden: {metrics['jb']:.1f} per session",
        f"Sessions Scanned: {metrics['sessions_scanned']}",
        "-" * 50,
    ]

    return "\n".join(lines)
