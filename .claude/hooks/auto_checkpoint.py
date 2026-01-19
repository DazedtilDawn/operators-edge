#!/usr/bin/env python3
"""
Operator's Edge v8.0 - Auto-Checkpoint (Phase 10.4)

Natural Breakpoint Detection - Offer checkpoints at natural stopping points.

The Problem:
- Sessions run long without natural stopping points
- Context accumulates without compression
- No structured handoff when context gets high

The Solution:
- Detect natural breakpoints (step completion, time threshold, error resolved)
- Generate compressed checkpoint summaries
- Offer to compact context for fresh continuation

"Pause wisely, continue smoothly."
"""
import json
import os
import sys
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Any

# Add hooks directory to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


# =============================================================================
# CONFIGURATION
# =============================================================================

# Time thresholds
TIME_THRESHOLD_MINUTES = 30          # Suggest checkpoint after this duration
TIME_WARNING_MINUTES = 45            # Stronger suggestion
TIME_CRITICAL_MINUTES = 60           # Critical - should definitely checkpoint

# Activity thresholds
TOOL_CALLS_THRESHOLD = 50            # After this many tool calls
FILE_EDITS_THRESHOLD = 15            # After this many file edits
ERRORS_RESOLVED_THRESHOLD = 3        # After resolving this many errors

# Checkpoint storage
CHECKPOINT_DIR = ".proof/checkpoints"


# =============================================================================
# DATA STRUCTURES
# =============================================================================

@dataclass
class Checkpoint:
    """A session checkpoint."""
    checkpoint_id: str
    timestamp: str
    trigger: str  # "step_complete", "time", "error_resolved", "manual"
    
    # Summary
    accomplished: List[str] = field(default_factory=list)
    decisions: List[str] = field(default_factory=list)
    files_modified: List[str] = field(default_factory=list)
    pending: List[str] = field(default_factory=list)
    
    # Metrics
    tool_calls: int = 0
    errors_encountered: int = 0
    errors_resolved: int = 0
    duration_minutes: float = 0.0
    
    # Context info
    context_usage_percent: float = 0.0
    context_snapshot_id: Optional[str] = None

    def to_dict(self) -> dict:
        return {
            "checkpoint_id": self.checkpoint_id,
            "timestamp": self.timestamp,
            "trigger": self.trigger,
            "accomplished": self.accomplished,
            "decisions": self.decisions,
            "files_modified": self.files_modified,
            "pending": self.pending,
            "tool_calls": self.tool_calls,
            "errors_encountered": self.errors_encountered,
            "errors_resolved": self.errors_resolved,
            "duration_minutes": self.duration_minutes,
            "context_usage_percent": self.context_usage_percent,
            "context_snapshot_id": self.context_snapshot_id,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "Checkpoint":
        return cls(
            checkpoint_id=data.get("checkpoint_id", ""),
            timestamp=data.get("timestamp", ""),
            trigger=data.get("trigger", ""),
            accomplished=data.get("accomplished", []),
            decisions=data.get("decisions", []),
            files_modified=data.get("files_modified", []),
            pending=data.get("pending", []),
            tool_calls=data.get("tool_calls", 0),
            errors_encountered=data.get("errors_encountered", 0),
            errors_resolved=data.get("errors_resolved", 0),
            duration_minutes=data.get("duration_minutes", 0.0),
            context_usage_percent=data.get("context_usage_percent", 0.0),
            context_snapshot_id=data.get("context_snapshot_id"),
        )


@dataclass
class BreakpointSignal:
    """A signal that a breakpoint has been reached."""
    trigger_type: str
    urgency: str  # "info", "suggestion", "recommended", "critical"
    message: str
    context: Dict[str, Any] = field(default_factory=dict)


# =============================================================================
# SESSION STATE TRACKING
# =============================================================================

# In-memory session state (persisted to .proof/)
_session_state: Dict[str, Any] = {
    "started_at": None,
    "tool_calls": 0,
    "file_edits": 0,
    "files_modified": [],
    "errors_encountered": 0,
    "errors_resolved": 0,
    "last_error": None,
    "steps_completed": 0,
    "last_checkpoint": None,
}


def _get_state_path() -> Path:
    """Get path to session state file."""
    proof_dir = Path(__file__).parent.parent.parent / ".proof"
    proof_dir.mkdir(parents=True, exist_ok=True)
    return proof_dir / "checkpoint_state.json"


def _load_session_state() -> Dict[str, Any]:
    """Load session state from disk."""
    global _session_state
    path = _get_state_path()

    if path.exists():
        try:
            with open(path) as f:
                loaded = json.load(f)
                # Update in place to preserve references
                _session_state.clear()
                _session_state.update(loaded)
        except (json.JSONDecodeError, OSError):
            pass

    return _session_state


def _save_session_state() -> bool:
    """Save session state to disk."""
    path = _get_state_path()
    try:
        with open(path, 'w') as f:
            json.dump(_session_state, f, indent=2)
        return True
    except OSError:
        return False


def init_session():
    """Initialize a new session."""
    global _session_state
    # Update in place to preserve references
    _session_state.clear()
    _session_state.update({
        "started_at": datetime.now().isoformat(),
        "tool_calls": 0,
        "file_edits": 0,
        "files_modified": [],
        "errors_encountered": 0,
        "errors_resolved": 0,
        "last_error": None,
        "steps_completed": 0,
        "last_checkpoint": None,
    })
    _save_session_state()


def record_tool_call(tool_name: str, file_path: Optional[str] = None):
    """Record a tool call."""
    _load_session_state()
    _session_state["tool_calls"] = _session_state.get("tool_calls", 0) + 1
    
    if tool_name in ("Edit", "Write") and file_path:
        _session_state["file_edits"] = _session_state.get("file_edits", 0) + 1
        files = _session_state.get("files_modified", [])
        if file_path not in files:
            files.append(file_path)
            _session_state["files_modified"] = files[-20:]  # Keep last 20
    
    _save_session_state()


def record_error(error_msg: str):
    """Record an error."""
    _load_session_state()
    _session_state["errors_encountered"] = _session_state.get("errors_encountered", 0) + 1
    _session_state["last_error"] = error_msg[:200]
    _save_session_state()


def record_error_resolved():
    """Record that an error was resolved."""
    _load_session_state()
    _session_state["errors_resolved"] = _session_state.get("errors_resolved", 0) + 1
    _session_state["last_error"] = None
    _save_session_state()


def record_step_completed():
    """Record that a step was completed."""
    _load_session_state()
    _session_state["steps_completed"] = _session_state.get("steps_completed", 0) + 1
    _save_session_state()


def get_session_duration_minutes() -> float:
    """Get session duration in minutes."""
    _load_session_state()
    started_at = _session_state.get("started_at")
    if not started_at:
        return 0.0
    
    try:
        start = datetime.fromisoformat(started_at)
        return (datetime.now() - start).total_seconds() / 60
    except ValueError:
        return 0.0


# =============================================================================
# BREAKPOINT DETECTION
# =============================================================================

def detect_breakpoint(event: str, context: Dict[str, Any] = None) -> Optional[BreakpointSignal]:
    """
    Check if current event represents a natural breakpoint.
    
    Args:
        event: Event type ("tool_complete", "step_complete", "error_resolved", "tick")
        context: Additional context (tool_name, etc.)
    
    Returns:
        BreakpointSignal if breakpoint detected, None otherwise
    """
    context = context or {}
    _load_session_state()
    
    # Step completion is always a breakpoint
    if event == "step_complete":
        return BreakpointSignal(
            trigger_type="step_complete",
            urgency="suggestion",
            message="Step completed - good checkpoint opportunity",
            context={"step": context.get("step_name", "unknown")}
        )
    
    # Error resolved after struggle
    if event == "error_resolved":
        errors_resolved = _session_state.get("errors_resolved", 0)
        if errors_resolved >= ERRORS_RESOLVED_THRESHOLD:
            return BreakpointSignal(
                trigger_type="errors_resolved",
                urgency="recommended",
                message=f"Resolved {errors_resolved} errors - consider checkpointing progress",
                context={"errors_resolved": errors_resolved}
            )
    
    # Time-based breakpoints
    duration = get_session_duration_minutes()
    
    if duration >= TIME_CRITICAL_MINUTES:
        return BreakpointSignal(
            trigger_type="time",
            urgency="critical",
            message=f"Session running {duration:.0f} minutes - checkpoint recommended",
            context={"duration_minutes": duration}
        )
    elif duration >= TIME_WARNING_MINUTES:
        # Only suggest on tick events to avoid spam
        if event == "tick":
            return BreakpointSignal(
                trigger_type="time",
                urgency="recommended",
                message=f"Session at {duration:.0f} minutes - checkpoint available",
                context={"duration_minutes": duration}
            )
    elif duration >= TIME_THRESHOLD_MINUTES:
        if event == "tick":
            return BreakpointSignal(
                trigger_type="time",
                urgency="suggestion",
                message=f"Session at {duration:.0f} minutes - checkpoint available if needed",
                context={"duration_minutes": duration}
            )
    
    # Tool call threshold
    tool_calls = _session_state.get("tool_calls", 0)
    if tool_calls > 0 and tool_calls % TOOL_CALLS_THRESHOLD == 0:
        return BreakpointSignal(
            trigger_type="activity",
            urgency="info",
            message=f"Reached {tool_calls} tool calls - checkpoint available",
            context={"tool_calls": tool_calls}
        )
    
    return None


# =============================================================================
# CHECKPOINT GENERATION
# =============================================================================

def generate_checkpoint_id() -> str:
    """Generate unique checkpoint ID."""
    return datetime.now().strftime("%Y%m%d-%H%M%S")


def generate_checkpoint(trigger: str) -> Checkpoint:
    """
    Generate a checkpoint from current session state.
    
    Args:
        trigger: What triggered this checkpoint
    
    Returns:
        Checkpoint with current session summary
    """
    _load_session_state()
    
    checkpoint = Checkpoint(
        checkpoint_id=generate_checkpoint_id(),
        timestamp=datetime.now().isoformat(),
        trigger=trigger,
        files_modified=_session_state.get("files_modified", [])[-10:],  # Last 10
        tool_calls=_session_state.get("tool_calls", 0),
        errors_encountered=_session_state.get("errors_encountered", 0),
        errors_resolved=_session_state.get("errors_resolved", 0),
        duration_minutes=get_session_duration_minutes(),
    )
    
    # Try to get context usage
    try:
        from context_monitor import get_context_usage
        checkpoint.context_usage_percent = get_context_usage() * 100
    except ImportError:
        pass
    
    return checkpoint


def save_checkpoint(checkpoint: Checkpoint) -> bool:
    """Save checkpoint to disk."""
    proof_dir = Path(__file__).parent.parent.parent / ".proof"
    checkpoint_dir = proof_dir / "checkpoints"
    checkpoint_dir.mkdir(parents=True, exist_ok=True)
    
    path = checkpoint_dir / f"{checkpoint.checkpoint_id}.json"
    try:
        with open(path, 'w') as f:
            json.dump(checkpoint.to_dict(), f, indent=2)
        
        # Update session state
        _session_state["last_checkpoint"] = checkpoint.checkpoint_id
        _save_session_state()
        
        return True
    except OSError:
        return False


def load_checkpoint(checkpoint_id: str) -> Optional[Checkpoint]:
    """Load a checkpoint by ID."""
    proof_dir = Path(__file__).parent.parent.parent / ".proof"
    path = proof_dir / "checkpoints" / f"{checkpoint_id}.json"
    
    if not path.exists():
        return None
    
    try:
        with open(path) as f:
            data = json.load(f)
        return Checkpoint.from_dict(data)
    except (json.JSONDecodeError, OSError):
        return None


def get_last_checkpoint() -> Optional[Checkpoint]:
    """Get the most recent checkpoint."""
    _load_session_state()
    checkpoint_id = _session_state.get("last_checkpoint")
    if checkpoint_id:
        return load_checkpoint(checkpoint_id)
    return None


# =============================================================================
# CHECKPOINT OFFER FORMATTING
# =============================================================================

def format_checkpoint_offer(signal: BreakpointSignal, checkpoint: Optional[Checkpoint] = None) -> str:
    """
    Format a checkpoint offer for display.
    
    Args:
        signal: The breakpoint signal
        checkpoint: Optional pre-generated checkpoint
    
    Returns:
        Formatted offer string
    """
    lines = []
    
    # Header based on urgency
    if signal.urgency == "critical":
        lines.append("╭─ 🔴 CHECKPOINT RECOMMENDED ────────────────────────╮")
    elif signal.urgency == "recommended":
        lines.append("╭─ 🟠 CHECKPOINT AVAILABLE ──────────────────────────╮")
    else:
        lines.append("╭─ 💡 CHECKPOINT OPPORTUNITY ──────────────────────────╮")
    
    # Message
    lines.append(f"│ {signal.message}")
    lines.append("│")
    
    # Session stats
    _load_session_state()
    duration = get_session_duration_minutes()
    tool_calls = _session_state.get("tool_calls", 0)
    files = len(_session_state.get("files_modified", []))
    
    lines.append(f"│ Session: {duration:.0f} min | {tool_calls} tools | {files} files modified")
    
    # Context usage if available
    if checkpoint and checkpoint.context_usage_percent > 0:
        lines.append(f"│ Context: {checkpoint.context_usage_percent:.0f}% used")
    
    lines.append("│")
    lines.append("│ Options:")
    lines.append("│   • Continue working (context preserved)")
    lines.append("│   • Create checkpoint summary for handoff")
    lines.append("│   • Compact context and continue fresh")
    lines.append("╰───────────────────────────────────────────────────────╯")
    
    return "\n".join(lines)


def format_compact_offer() -> str:
    """Format a compact one-line checkpoint reminder."""
    duration = get_session_duration_minutes()
    return f"💡 Session at {duration:.0f} min - /checkpoint available"


# =============================================================================
# INTEGRATION HELPERS
# =============================================================================

def check_and_offer_checkpoint(event: str, context: Dict[str, Any] = None) -> Optional[str]:
    """
    Main integration point for hooks.
    
    Returns formatted checkpoint offer or None.
    """
    signal = detect_breakpoint(event, context)
    if signal is None:
        return None
    
    # Don't spam - only critical/recommended get full format
    if signal.urgency in ("critical", "recommended"):
        checkpoint = generate_checkpoint(signal.trigger_type)
        return format_checkpoint_offer(signal, checkpoint)
    else:
        return format_compact_offer()


def create_checkpoint_now(trigger: str = "manual") -> Checkpoint:
    """Create and save a checkpoint immediately."""
    checkpoint = generate_checkpoint(trigger)
    save_checkpoint(checkpoint)
    return checkpoint


# =============================================================================
# QUICK TEST
# =============================================================================

if __name__ == "__main__":
    print("Auto-Checkpoint - Self Test")
    print("=" * 50)
    
    # Initialize session
    init_session()
    print("Session initialized")
    
    # Simulate some activity
    for i in range(5):
        record_tool_call("Read")
    record_tool_call("Edit", "/path/to/file.py")
    record_tool_call("Write", "/path/to/new_file.py")
    record_error("ImportError: No module named 'foo'")
    record_error_resolved()
    
    print(f"\nSession state:")
    print(f"  Duration: {get_session_duration_minutes():.1f} min")
    print(f"  Tool calls: {_session_state.get('tool_calls', 0)}")
    print(f"  Files modified: {len(_session_state.get('files_modified', []))}")
    
    # Test breakpoint detection
    print("\n--- Breakpoint Detection ---")
    signal = detect_breakpoint("step_complete", {"step_name": "Implement feature"})
    if signal:
        print(f"Step complete signal: {signal.urgency}")
    
    # Test checkpoint generation
    print("\n--- Checkpoint Generation ---")
    checkpoint = generate_checkpoint("test")
    print(f"Checkpoint ID: {checkpoint.checkpoint_id}")
    print(f"Files modified: {checkpoint.files_modified}")
    print(f"Tool calls: {checkpoint.tool_calls}")
    
    # Test formatting
    print("\n--- Checkpoint Offer ---")
    test_signal = BreakpointSignal(
        trigger_type="time",
        urgency="recommended",
        message="Session at 45 minutes - checkpoint available"
    )
    print(format_checkpoint_offer(test_signal, checkpoint))
    
    print("\nSelf-test complete.")
