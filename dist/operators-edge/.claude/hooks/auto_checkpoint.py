#!/usr/bin/env python3
"""
Operator's Edge v8.0 - Auto-Checkpoint (Phase 10.4)

RLM-Inspired: Generate compressed checkpoints at natural breakpoints
to maintain continuity without full context bloat.

The Problem:
- Sessions drift and context fills up
- No structured stopping points
- Handoffs lose continuity or carry too much baggage

The Solution:
- Detect natural breakpoints (step complete, phase change, time threshold)
- Generate compressed checkpoint summaries
- Offer context compaction while preserving continuity

"Checkpoint often, compact wisely."
"""
import json
import os
import sys
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Any

# Add hooks directory to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


# =============================================================================
# CONFIGURATION
# =============================================================================

# Default breakpoint detection thresholds (can be overridden via v8_config.json)
DEFAULT_TIME_THRESHOLD_MINUTES = 30          # Suggest checkpoint after this many minutes
DEFAULT_TOOL_CALLS_THRESHOLD = 50            # Suggest checkpoint after this many tool calls
DEFAULT_CONTEXT_THRESHOLD_PERCENT = 60       # Suggest checkpoint when context exceeds this
DEFAULT_ERROR_RESOLVED_THRESHOLD = 3         # Checkpoint after resolving 3+ errors

# Checkpoint storage
CHECKPOINTS_DIR = "checkpoints"
MAX_CHECKPOINTS = 20  # Keep last N checkpoints

# Cooldown to prevent checkpoint spam (seconds)
CHECKPOINT_COOLDOWN_SECONDS = 600  # 10 minutes between checkpoint offers

# Track last checkpoint offer time (in-memory, resets on process restart)
_last_checkpoint_offer: Optional[datetime] = None


# =============================================================================
# CONFIGURATION LOADING
# =============================================================================

def _get_config_path() -> Path:
    """Get path to v8 config file."""
    return Path(__file__).parent.parent.parent / ".proof" / "v8_config.json"


def _load_checkpoint_config() -> dict:
    """
    Load checkpoint thresholds from v8_config.json.

    Falls back to defaults if config doesn't exist or is invalid.
    This allows tuning thresholds without code changes.
    """
    defaults = {
        "time_threshold_minutes": DEFAULT_TIME_THRESHOLD_MINUTES,
        "tool_calls_threshold": DEFAULT_TOOL_CALLS_THRESHOLD,
        "context_threshold_percent": DEFAULT_CONTEXT_THRESHOLD_PERCENT,
        "error_resolved_threshold": DEFAULT_ERROR_RESOLVED_THRESHOLD,
        "cooldown_seconds": CHECKPOINT_COOLDOWN_SECONDS,
    }

    config_path = _get_config_path()
    if not config_path.exists():
        return defaults

    try:
        with open(config_path) as f:
            data = json.load(f)
        checkpoint_config = data.get("checkpoint", {})
        return {**defaults, **checkpoint_config}
    except (json.JSONDecodeError, OSError):
        return defaults


def _get_threshold(key: str) -> float:
    """Get a specific threshold value from config."""
    config = _load_checkpoint_config()
    return config.get(key, 0)


# =============================================================================
# COOLDOWN MANAGEMENT
# =============================================================================

def _can_offer_checkpoint() -> bool:
    """
    Check if enough time has passed since last checkpoint offer.

    Prevents nagging the user with repeated checkpoint suggestions.
    """
    global _last_checkpoint_offer

    if _last_checkpoint_offer is None:
        return True

    cooldown = _load_checkpoint_config().get("cooldown_seconds", CHECKPOINT_COOLDOWN_SECONDS)
    elapsed = (datetime.now() - _last_checkpoint_offer).total_seconds()
    return elapsed >= cooldown


def _mark_checkpoint_offered() -> None:
    """Mark that a checkpoint offer was shown."""
    global _last_checkpoint_offer
    _last_checkpoint_offer = datetime.now()


def reset_checkpoint_cooldown() -> None:
    """Reset checkpoint cooldown (for testing)."""
    global _last_checkpoint_offer
    _last_checkpoint_offer = None


# =============================================================================
# DEBUG LOGGING
# =============================================================================

def _log_debug(message: str) -> None:
    """
    Log debug message to .proof/debug.log (not stderr).

    Silent on failure - debugging shouldn't break the hook.
    """
    try:
        debug_path = Path(__file__).parent.parent.parent / ".proof" / "debug.log"
        debug_path.parent.mkdir(parents=True, exist_ok=True)
        with open(debug_path, "a") as f:
            f.write(f"[{datetime.now().isoformat()}] auto_checkpoint: {message}\n")
    except:
        pass  # Truly silent - debug logging should never fail the hook


def _extract_commit_message(output: str) -> Optional[str]:
    """
    Extract commit message from git output, locale-agnostic.

    Git output format varies by locale and version:
    - English: "[main abc123] Commit message"
    - German: "[main abc123] Commit-Nachricht"
    - With newlines: "[main abc123] Message\n 1 file changed..."

    Degrades gracefully to "commit made" if parsing fails.
    """
    if not output:
        return None

    # Try bracket format first (most common)
    if "]" in output:
        after_bracket = output.split("]", 1)[-1]
        # Take first line only (avoid file change stats)
        first_line = after_bracket.split("\n")[0].strip()
        if first_line:
            return first_line[:50]

    # Fallback: if we have any output, just note a commit was made
    if output.strip():
        return "commit made"

    return None


# =============================================================================
# DATA STRUCTURES
# =============================================================================

@dataclass
class Checkpoint:
    """A compressed checkpoint of session state."""
    checkpoint_id: str
    timestamp: str

    # What was accomplished
    accomplished: List[str] = field(default_factory=list)
    decisions: List[str] = field(default_factory=list)
    files_modified: List[str] = field(default_factory=list)

    # What's pending
    pending: List[str] = field(default_factory=list)
    current_focus: str = ""

    # Session metrics at checkpoint
    context_usage_percent: float = 0.0
    tool_calls: int = 0
    session_duration_minutes: float = 0.0
    errors_encountered: int = 0
    errors_resolved: int = 0

    # Full context backup reference (optional)
    context_snapshot_id: Optional[str] = None

    def to_dict(self) -> dict:
        return {
            "checkpoint_id": self.checkpoint_id,
            "timestamp": self.timestamp,
            "accomplished": self.accomplished,
            "decisions": self.decisions,
            "files_modified": self.files_modified,
            "pending": self.pending,
            "current_focus": self.current_focus,
            "context_usage_percent": self.context_usage_percent,
            "tool_calls": self.tool_calls,
            "session_duration_minutes": self.session_duration_minutes,
            "errors_encountered": self.errors_encountered,
            "errors_resolved": self.errors_resolved,
            "context_snapshot_id": self.context_snapshot_id,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "Checkpoint":
        return cls(
            checkpoint_id=data.get("checkpoint_id", ""),
            timestamp=data.get("timestamp", ""),
            accomplished=data.get("accomplished", []),
            decisions=data.get("decisions", []),
            files_modified=data.get("files_modified", []),
            pending=data.get("pending", []),
            current_focus=data.get("current_focus", ""),
            context_usage_percent=data.get("context_usage_percent", 0.0),
            tool_calls=data.get("tool_calls", 0),
            session_duration_minutes=data.get("session_duration_minutes", 0.0),
            errors_encountered=data.get("errors_encountered", 0),
            errors_resolved=data.get("errors_resolved", 0),
            context_snapshot_id=data.get("context_snapshot_id"),
        )


@dataclass
class BreakpointDetection:
    """Result of breakpoint detection."""
    is_breakpoint: bool
    reason: str
    urgency: str  # "suggestion", "recommendation", "urgent"
    checkpoint: Optional[Checkpoint] = None


# =============================================================================
# BREAKPOINT DETECTION
# =============================================================================

def detect_time_breakpoint(session_duration_minutes: float) -> Optional[str]:
    """Check if session duration warrants a checkpoint."""
    threshold = _get_threshold("time_threshold_minutes")
    if session_duration_minutes >= threshold:
        intervals = int(session_duration_minutes // threshold)
        if intervals >= 1:
            return f"Session running for {session_duration_minutes:.0f} minutes"
    return None


def detect_tool_calls_breakpoint(tool_calls: int) -> Optional[str]:
    """Check if tool call count warrants a checkpoint."""
    threshold = _get_threshold("tool_calls_threshold")
    if tool_calls >= threshold:
        intervals = int(tool_calls // threshold)
        if intervals >= 1:
            return f"{tool_calls} tool calls in session"
    return None


def detect_context_breakpoint(context_usage_percent: float) -> Optional[str]:
    """Check if context usage warrants a checkpoint."""
    threshold = _get_threshold("context_threshold_percent")
    if context_usage_percent >= threshold:
        return f"Context at {context_usage_percent:.0f}%"
    return None


def detect_step_completion(current_event: str, state: dict) -> Optional[str]:
    """Check if a step was just completed."""
    # Check if event indicates step completion
    completion_indicators = [
        "step complete",
        "phase complete",
        "task done",
        "milestone reached",
        "tests passing",
    ]

    event_lower = current_event.lower()
    for indicator in completion_indicators:
        if indicator in event_lower:
            return f"Step completed: {current_event[:50]}"

    # Check state for recently completed steps
    plan = state.get("plan", [])
    for step in plan:
        if isinstance(step, dict):
            status = step.get("status", "")
            # If we find a step marked completed recently, it's a breakpoint
            if status == "completed":
                desc = step.get("description", "step")
                return f"Completed: {desc[:40]}"

    return None


def detect_error_resolved(errors_encountered: int, errors_resolved: int) -> Optional[str]:
    """Check if significant errors were resolved."""
    threshold = _get_threshold("error_resolved_threshold")
    if errors_resolved >= threshold:
        return f"Resolved {errors_resolved} error(s)"
    return None


def detect_git_commit(current_event: str) -> Optional[str]:
    """Check if a git commit was just made."""
    if "git commit" in current_event.lower():
        return "Git commit made"
    return None


def detect_breakpoint(
    current_event: str,
    session_state: dict,
    session_metrics: dict
) -> Optional[BreakpointDetection]:
    """
    Detect if the current state represents a natural breakpoint.

    Returns BreakpointDetection if a breakpoint is detected, None otherwise.
    """
    # Extract metrics
    duration = session_metrics.get("session_duration_minutes", 0)
    tool_calls = session_metrics.get("tool_calls", 0)
    context_usage = session_metrics.get("context_usage_percent", 0)
    errors_encountered = session_metrics.get("errors_encountered", 0)
    errors_resolved = session_metrics.get("errors_resolved", 0)

    reasons = []
    urgency = "suggestion"

    # Check various breakpoint conditions

    # 1. Git commit (always a good breakpoint)
    if reason := detect_git_commit(current_event):
        reasons.append(reason)
        urgency = "recommendation"

    # 2. Step completion
    if reason := detect_step_completion(current_event, session_state):
        reasons.append(reason)
        if urgency == "suggestion":
            urgency = "recommendation"

    # 3. Error resolved (significant)
    if reason := detect_error_resolved(errors_encountered, errors_resolved):
        reasons.append(reason)
        urgency = "recommendation"

    # 4. Context usage (urgent if high)
    if reason := detect_context_breakpoint(context_usage):
        reasons.append(reason)
        if context_usage >= 80:
            urgency = "urgent"
        elif context_usage >= 70:
            urgency = "recommendation"

    # 5. Time threshold
    if reason := detect_time_breakpoint(duration):
        reasons.append(reason)

    # 6. Tool calls threshold
    if reason := detect_tool_calls_breakpoint(tool_calls):
        reasons.append(reason)

    if not reasons:
        return None

    return BreakpointDetection(
        is_breakpoint=True,
        reason="; ".join(reasons),
        urgency=urgency,
        checkpoint=None,  # Will be generated separately
    )


# =============================================================================
# CHECKPOINT GENERATION
# =============================================================================

def extract_accomplished_from_log(session_log: Path) -> List[str]:
    """Extract accomplishments from session log."""
    accomplished = []

    try:
        from context_monitor import load_session_entries
        entries = load_session_entries(session_log)
    except ImportError:
        return accomplished
    except Exception:
        return accomplished

    # Track unique accomplishments
    seen = set()

    for entry in entries:
        tool = entry.get("tool", "")
        success = entry.get("success", True)

        if not success:
            continue

        # Git commits are accomplishments
        if tool == "Bash":
            input_data = entry.get("input_preview", {})
            cmd = ""
            if isinstance(input_data, dict):
                cmd = input_data.get("command", "")
            elif isinstance(input_data, str):
                cmd = input_data

            if cmd and "git commit" in cmd.lower():
                output = entry.get("output_preview", "")
                # Extract commit message - defensive against locale variations
                msg = _extract_commit_message(output)
                if msg and msg not in seen:
                    accomplished.append(f"Committed: {msg}")
                    seen.add(msg)

        # Test passes are accomplishments
        if tool == "Bash":
            output = entry.get("output_preview", "")
            if output and "passed" in output.lower() and "test" in output.lower():
                # Extract test count
                import re
                match = re.search(r'(\d+)\s+(?:tests?\s+)?passed', output, re.IGNORECASE)
                if match:
                    count = match.group(1)
                    item = f"Tests passing: {count}"
                    if item not in seen:
                        accomplished.append(item)
                        seen.add(item)

    return accomplished[:10]  # Limit to 10


def extract_files_modified_from_log(session_log: Path) -> List[str]:
    """Extract unique files modified from session log."""
    files = set()

    try:
        from context_monitor import load_session_entries
        entries = load_session_entries(session_log)
    except ImportError:
        return []
    except Exception:
        return []

    for entry in entries:
        tool = entry.get("tool", "")
        if tool in ("Edit", "Write"):
            input_data = entry.get("input_preview", {})
            if isinstance(input_data, dict):
                fp = input_data.get("file_path") or input_data.get("file", "")
                if fp:
                    # Store just the filename for brevity
                    files.add(Path(fp).name)

    return sorted(list(files))[:15]  # Limit to 15


def extract_pending_from_state(state: dict) -> List[str]:
    """Extract pending items from state."""
    pending = []

    plan = state.get("plan", [])
    for step in plan:
        if isinstance(step, dict):
            status = step.get("status", "")
            if status in ("pending", "in_progress"):
                desc = step.get("description", "")
                if desc:
                    pending.append(desc[:60])

    return pending[:5]  # Limit to 5


def generate_checkpoint(
    session_log: Path,
    state: dict,
    session_metrics: dict
) -> Checkpoint:
    """
    Generate a checkpoint from current session state.
    """
    import uuid

    checkpoint_id = f"ckpt-{datetime.now().strftime('%Y%m%d-%H%M%S')}-{uuid.uuid4().hex[:6]}"

    # Extract data
    accomplished = extract_accomplished_from_log(session_log)
    files_modified = extract_files_modified_from_log(session_log)
    pending = extract_pending_from_state(state)

    # Determine current focus
    current_focus = ""
    for step in state.get("plan", []):
        if isinstance(step, dict) and step.get("status") == "in_progress":
            current_focus = step.get("description", "")
            break

    if not current_focus:
        current_focus = state.get("objective", "No specific focus")

    # Extract decisions from state
    decisions = []
    if state.get("risks"):
        decisions.append(f"Risks identified: {len(state['risks'])}")
    if state.get("constraints"):
        decisions.append(f"Constraints: {len(state['constraints'])}")

    return Checkpoint(
        checkpoint_id=checkpoint_id,
        timestamp=datetime.now().isoformat(),
        accomplished=accomplished,
        decisions=decisions,
        files_modified=files_modified,
        pending=pending,
        current_focus=current_focus[:100],
        context_usage_percent=session_metrics.get("context_usage_percent", 0),
        tool_calls=session_metrics.get("tool_calls", 0),
        session_duration_minutes=session_metrics.get("session_duration_minutes", 0),
        errors_encountered=session_metrics.get("errors_encountered", 0),
        errors_resolved=session_metrics.get("errors_resolved", 0),
    )


# =============================================================================
# CHECKPOINT STORAGE
# =============================================================================

def _get_checkpoints_dir() -> Path:
    """Get path to checkpoints directory."""
    proof_dir = Path(__file__).parent.parent.parent / ".proof"
    checkpoints_dir = proof_dir / CHECKPOINTS_DIR
    checkpoints_dir.mkdir(parents=True, exist_ok=True)
    return checkpoints_dir


def save_checkpoint(checkpoint: Checkpoint) -> Path:
    """Save checkpoint to disk."""
    checkpoints_dir = _get_checkpoints_dir()

    filename = f"{checkpoint.checkpoint_id}.json"
    filepath = checkpoints_dir / filename

    with open(filepath, 'w') as f:
        json.dump(checkpoint.to_dict(), f, indent=2)

    # Cleanup old checkpoints
    _cleanup_old_checkpoints()

    return filepath


def load_checkpoint(checkpoint_id: str) -> Optional[Checkpoint]:
    """Load a checkpoint by ID."""
    checkpoints_dir = _get_checkpoints_dir()
    filepath = checkpoints_dir / f"{checkpoint_id}.json"

    if not filepath.exists():
        return None

    try:
        with open(filepath) as f:
            data = json.load(f)
        return Checkpoint.from_dict(data)
    except (json.JSONDecodeError, OSError):
        return None


def load_latest_checkpoint() -> Optional[Checkpoint]:
    """Load the most recent checkpoint."""
    checkpoints_dir = _get_checkpoints_dir()

    checkpoint_files = sorted(checkpoints_dir.glob("ckpt-*.json"), reverse=True)
    if not checkpoint_files:
        return None

    try:
        with open(checkpoint_files[0]) as f:
            data = json.load(f)
        return Checkpoint.from_dict(data)
    except (json.JSONDecodeError, OSError):
        return None


def _cleanup_old_checkpoints():
    """Remove old checkpoints beyond retention limit."""
    checkpoints_dir = _get_checkpoints_dir()
    checkpoint_files = sorted(checkpoints_dir.glob("ckpt-*.json"), reverse=True)

    for filepath in checkpoint_files[MAX_CHECKPOINTS:]:
        try:
            filepath.unlink()
        except OSError:
            pass


# =============================================================================
# COMPACTION OFFER
# =============================================================================

def format_checkpoint_summary(checkpoint: Checkpoint) -> str:
    """Format checkpoint as a brief summary."""
    lines = []

    # Header
    lines.append(f"📌 Checkpoint: {checkpoint.checkpoint_id}")
    lines.append(f"   Time: {checkpoint.timestamp[:16]}")
    lines.append("")

    # Accomplished
    if checkpoint.accomplished:
        lines.append("✅ Accomplished:")
        for item in checkpoint.accomplished[:5]:
            lines.append(f"   • {item}")

    # Files modified
    if checkpoint.files_modified:
        files_str = ", ".join(checkpoint.files_modified[:5])
        if len(checkpoint.files_modified) > 5:
            files_str += f" (+{len(checkpoint.files_modified) - 5} more)"
        lines.append(f"📁 Files: {files_str}")

    # Pending
    if checkpoint.pending:
        lines.append("⏳ Pending:")
        for item in checkpoint.pending[:3]:
            lines.append(f"   • {item}")

    # Metrics
    lines.append("")
    lines.append(f"📊 Context: {checkpoint.context_usage_percent:.0f}% | "
                 f"Tools: {checkpoint.tool_calls} | "
                 f"Duration: {checkpoint.session_duration_minutes:.0f}min")

    return "\n".join(lines)


def offer_compaction(checkpoint: Checkpoint, urgency: str = "suggestion") -> str:
    """
    Generate a compaction offer message.

    This suggests to Claude that it might be a good time to checkpoint.
    """
    lines = []

    # Header based on urgency
    if urgency == "urgent":
        lines.append("╭─ ⚠️ CHECKPOINT RECOMMENDED (URGENT) ──────────────╮")
    elif urgency == "recommendation":
        lines.append("╭─ 📌 CHECKPOINT AVAILABLE ──────────────────────────╮")
    else:
        lines.append("╭─ 💡 CHECKPOINT SUGGESTION ─────────────────────────╮")

    # Summary
    summary = format_checkpoint_summary(checkpoint)
    for line in summary.split("\n"):
        lines.append(f"│ {line}")

    lines.append("│")
    lines.append("│ Consider compacting context to continue fresh.")
    lines.append("│ Checkpoint saved - state preserved if needed.")
    lines.append("╰────────────────────────────────────────────────────╯")

    return "\n".join(lines)


# =============================================================================
# INTEGRATION HELPERS
# =============================================================================

def check_and_offer_checkpoint(
    current_event: str,
    intervention_level: str = "advise"
) -> Optional[str]:
    """
    Main integration point for post_tool.py.

    Checks if we should offer a checkpoint and returns formatted offer.
    Returns None if no checkpoint needed.

    Imports are deferred to avoid circular dependencies. This module may import:
    - proof_utils (get_session_log_path)
    - context_monitor (estimate_context_usage)
    - edge_utils (load_yaml_state)
    """
    if intervention_level == "observe":
        return None

    # Check cooldown - don't spam checkpoint offers
    if not _can_offer_checkpoint():
        return None

    try:
        from proof_utils import get_session_log_path
        from context_monitor import estimate_context_usage
        from edge_utils import load_yaml_state

        # Get session data
        session_log = get_session_log_path()
        if not session_log or not session_log.exists():
            return None

        state = load_yaml_state() or {}

        # Get metrics
        estimate = estimate_context_usage(session_log)
        session_metrics = {
            "session_duration_minutes": estimate.session_duration_minutes,
            "tool_calls": estimate.tool_calls,
            "context_usage_percent": estimate.usage_percentage * 100,
            "errors_encountered": 0,  # Would need tracking
            "errors_resolved": 0,
        }

        # Detect breakpoint
        detection = detect_breakpoint(current_event, state, session_metrics)

        if not detection or not detection.is_breakpoint:
            return None

        # Generate checkpoint
        checkpoint = generate_checkpoint(session_log, state, session_metrics)

        # Save checkpoint
        save_checkpoint(checkpoint)

        # Only surface based on intervention level
        if intervention_level == "advise" and detection.urgency == "suggestion":
            return None  # Too subtle for advise level

        # Mark that we're offering a checkpoint (for cooldown)
        _mark_checkpoint_offered()

        # Generate offer
        return offer_compaction(checkpoint, detection.urgency)

    except ImportError:
        return None
    except Exception as e:
        _log_debug(f"check_and_offer_checkpoint error: {e}")
        return None


def get_checkpoint_for_injection() -> Optional[str]:
    """
    Get the latest checkpoint formatted for session injection.

    Used when starting a new session to provide continuity.
    """
    checkpoint = load_latest_checkpoint()
    if not checkpoint:
        return None

    # Check if checkpoint is recent enough (within 2 hours)
    try:
        created = datetime.fromisoformat(checkpoint.timestamp)
        age_hours = (datetime.now() - created).total_seconds() / 3600
        if age_hours > 2:
            return None  # Too old
    except ValueError:
        pass

    lines = [
        "",
        "=" * 50,
        "📌 LAST CHECKPOINT",
        "=" * 50,
        "",
        format_checkpoint_summary(checkpoint),
        "",
        "-" * 50,
        "",
    ]

    return "\n".join(lines)


# =============================================================================
# QUICK TEST
# =============================================================================

if __name__ == "__main__":
    print("Auto-Checkpoint - Self Test")
    print("=" * 50)

    # Test checkpoint creation
    test_checkpoint = Checkpoint(
        checkpoint_id="ckpt-test-001",
        timestamp=datetime.now().isoformat(),
        accomplished=["Implemented smart_read.py", "All 39 tests passing"],
        decisions=["Use grep/head for large files"],
        files_modified=["smart_read.py", "test_smart_read.py", "pre_tool.py"],
        pending=["Implement auto-checkpoint", "Update CHANGELOG"],
        current_focus="Phase 10.4 implementation",
        context_usage_percent=45.0,
        tool_calls=78,
        session_duration_minutes=42.0,
        errors_encountered=3,
        errors_resolved=3,
    )

    print("\n--- Checkpoint Summary ---")
    print(format_checkpoint_summary(test_checkpoint))

    print("\n--- Compaction Offer (suggestion) ---")
    print(offer_compaction(test_checkpoint, "suggestion"))

    print("\n--- Compaction Offer (urgent) ---")
    print(offer_compaction(test_checkpoint, "urgent"))

    # Test breakpoint detection
    print("\n--- Breakpoint Detection Tests ---")

    # Test time breakpoint
    result = detect_time_breakpoint(45)
    print(f"Time breakpoint (45 min): {result}")

    result = detect_time_breakpoint(15)
    print(f"Time breakpoint (15 min): {result}")

    # Test context breakpoint
    result = detect_context_breakpoint(75)
    print(f"Context breakpoint (75%): {result}")

    result = detect_context_breakpoint(40)
    print(f"Context breakpoint (40%): {result}")

    # Test git commit detection
    result = detect_git_commit("git commit -m 'Add feature'")
    print(f"Git commit detection: {result}")

    print("\nSelf-test complete.")
