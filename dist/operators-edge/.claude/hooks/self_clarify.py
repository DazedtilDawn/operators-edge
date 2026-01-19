#!/usr/bin/env python3
"""
Operator's Edge v8.0 - Self-Clarification (Phase 10.3)

RLM-Inspired: When stuck, force stepping back to clarify the actual problem.

The Problem:
- Claude gets stuck in loops (editing same file repeatedly)
- Drift signals fire but don't change behavior
- Same errors repeat without resolution
- The "try same thing again" anti-pattern

The Solution:
- Detect "stuck" patterns (repeated edits, ignored drift, cycling errors)
- Trigger self-clarification prompts
- Inject clarifying context to break the cycle
- Surface the meta-question: "What is the actual problem?"

"If I had an hour to solve a problem, I'd spend 55 minutes thinking
 about the problem and 5 minutes thinking about solutions." - Einstein
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

# Default thresholds for "stuck" detection (can be overridden via v8_config.json)
DEFAULT_DRIFT_THRESHOLD = 3           # Fire clarification after N ignored drift signals
DEFAULT_ERROR_REPEAT_THRESHOLD = 3    # Fire after same error N times
DEFAULT_SAME_FILE_EDIT_THRESHOLD = 5  # Fire after editing same file N times
DEFAULT_TOOL_LOOP_THRESHOLD = 10      # Fire after N tools without progress

# Cooldown to prevent clarification spam (seconds)
CLARIFICATION_COOLDOWN_SECONDS = 900  # 15 minutes between clarifications

# Track last clarification time (in-memory, resets on process restart)
_last_clarification_offer: Optional[datetime] = None


# =============================================================================
# CONFIGURATION LOADING
# =============================================================================

def _get_config_path() -> Path:
    """Get path to v8 config file."""
    return Path(__file__).parent.parent.parent / ".proof" / "v8_config.json"


def _load_clarification_config() -> dict:
    """
    Load clarification thresholds from v8_config.json.

    Falls back to defaults if config doesn't exist or is invalid.
    """
    defaults = {
        "drift_threshold": DEFAULT_DRIFT_THRESHOLD,
        "error_repeat_threshold": DEFAULT_ERROR_REPEAT_THRESHOLD,
        "same_file_edit_threshold": DEFAULT_SAME_FILE_EDIT_THRESHOLD,
        "tool_loop_threshold": DEFAULT_TOOL_LOOP_THRESHOLD,
        "cooldown_seconds": CLARIFICATION_COOLDOWN_SECONDS,
    }

    config_path = _get_config_path()
    if not config_path.exists():
        return defaults

    try:
        with open(config_path) as f:
            data = json.load(f)
        clarification_config = data.get("clarification", {})
        return {**defaults, **clarification_config}
    except (json.JSONDecodeError, OSError):
        return defaults


def _get_threshold(key: str) -> int:
    """Get a specific threshold value from config."""
    config = _load_clarification_config()
    return config.get(key, 0)


# =============================================================================
# COOLDOWN MANAGEMENT
# =============================================================================

def _can_offer_clarification() -> bool:
    """
    Check if enough time has passed since last clarification.

    Prevents nagging the user with repeated clarification prompts.
    """
    global _last_clarification_offer

    if _last_clarification_offer is None:
        return True

    cooldown = _load_clarification_config().get("cooldown_seconds", CLARIFICATION_COOLDOWN_SECONDS)
    elapsed = (datetime.now() - _last_clarification_offer).total_seconds()
    return elapsed >= cooldown


def _mark_clarification_offered() -> None:
    """Mark that a clarification was shown."""
    global _last_clarification_offer
    _last_clarification_offer = datetime.now()


def reset_clarification_cooldown() -> None:
    """Reset clarification cooldown (for testing)."""
    global _last_clarification_offer
    _last_clarification_offer = None


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
            f.write(f"[{datetime.now().isoformat()}] self_clarify: {message}\n")
    except:
        pass  # Truly silent


# =============================================================================
# DATA STRUCTURES
# =============================================================================

@dataclass
class StuckPattern:
    """A detected pattern indicating Claude is stuck."""
    pattern_type: str  # "drift_ignored", "error_repeat", "file_loop", "tool_loop"
    severity: str      # "mild", "moderate", "severe"
    evidence: List[str] = field(default_factory=list)
    count: int = 0

    def to_dict(self) -> dict:
        return {
            "pattern_type": self.pattern_type,
            "severity": self.severity,
            "evidence": self.evidence,
            "count": self.count,
        }


@dataclass
class ClarificationContext:
    """Context gathered for self-clarification."""
    recent_tools: List[Dict[str, Any]] = field(default_factory=list)
    recent_errors: List[str] = field(default_factory=list)
    files_being_edited: List[str] = field(default_factory=list)
    current_objective: str = ""
    stuck_patterns: List[StuckPattern] = field(default_factory=list)
    session_duration_minutes: float = 0.0
    total_tool_calls: int = 0


@dataclass
class ClarificationResult:
    """Result of clarification analysis."""
    should_clarify: bool
    urgency: str  # "suggestion", "recommendation", "urgent"
    patterns: List[StuckPattern] = field(default_factory=list)
    prompt: str = ""
    injection: str = ""


# =============================================================================
# STUCK PATTERN DETECTION
# =============================================================================

def detect_drift_ignored(
    drift_signals_fired: int,
    drift_signals_acted_on: int
) -> Optional[StuckPattern]:
    """Detect if drift signals are being ignored."""
    threshold = _get_threshold("drift_threshold")
    ignored = drift_signals_fired - drift_signals_acted_on

    if ignored >= threshold:
        severity = "mild" if ignored < threshold * 2 else "moderate" if ignored < threshold * 3 else "severe"
        return StuckPattern(
            pattern_type="drift_ignored",
            severity=severity,
            evidence=[f"Fired {drift_signals_fired} drift signals, acted on {drift_signals_acted_on}"],
            count=ignored,
        )
    return None


def detect_error_repeat(
    error_messages: List[str],
    threshold_override: Optional[int] = None
) -> Optional[StuckPattern]:
    """Detect if the same error is repeating."""
    threshold = threshold_override or _get_threshold("error_repeat_threshold")

    if not error_messages:
        return None

    # Count error message occurrences (normalize by removing line numbers)
    normalized = []
    for err in error_messages:
        # Strip line numbers for comparison
        import re
        normalized_err = re.sub(r'line \d+', 'line N', err.lower())
        normalized_err = re.sub(r':\d+:', ':N:', normalized_err)
        normalized.append(normalized_err[:200])  # Truncate for comparison

    from collections import Counter
    counts = Counter(normalized)

    for error, count in counts.most_common(1):
        if count >= threshold:
            severity = "mild" if count == threshold else "moderate" if count < threshold * 2 else "severe"
            return StuckPattern(
                pattern_type="error_repeat",
                severity=severity,
                evidence=[f"Error repeated {count}x: {error[:100]}..."],
                count=count,
            )

    return None


def detect_file_loop(
    file_edits: List[str],
    threshold_override: Optional[int] = None
) -> Optional[StuckPattern]:
    """Detect if the same file is being edited repeatedly."""
    threshold = threshold_override or _get_threshold("same_file_edit_threshold")

    if not file_edits:
        return None

    from collections import Counter
    counts = Counter(file_edits)

    for file_path, count in counts.most_common(1):
        if count >= threshold:
            severity = "mild" if count == threshold else "moderate" if count < threshold * 2 else "severe"
            return StuckPattern(
                pattern_type="file_loop",
                severity=severity,
                evidence=[f"Edited {Path(file_path).name} {count} times"],
                count=count,
            )

    return None


def detect_tool_loop(
    recent_tools: List[Dict[str, Any]],
    threshold_override: Optional[int] = None
) -> Optional[StuckPattern]:
    """Detect tool call patterns without apparent progress."""
    threshold = threshold_override or _get_threshold("tool_loop_threshold")

    if len(recent_tools) < threshold:
        return None

    # Check for alternating patterns (edit-error-edit-error)
    tool_sequence = [t.get("tool", "") for t in recent_tools[-threshold:]]

    # Detect edit-bash-edit-bash loops (common when stuck)
    alternating_count = 0
    for i in range(1, len(tool_sequence)):
        if tool_sequence[i] != tool_sequence[i-1]:
            alternating_count += 1

    # High alternation with many failures suggests stuck
    failures = sum(1 for t in recent_tools[-threshold:] if not t.get("success", True))

    if alternating_count >= threshold * 0.6 and failures >= threshold * 0.3:
        return StuckPattern(
            pattern_type="tool_loop",
            severity="moderate",
            evidence=[f"Alternating tool pattern detected ({alternating_count} switches, {failures} failures)"],
            count=alternating_count,
        )

    return None


def detect_stuck_patterns(context: ClarificationContext) -> List[StuckPattern]:
    """Detect all stuck patterns from context."""
    patterns = []

    # These would be populated from session health
    # For now, use what we can extract from context

    # File loop detection from recent edits
    file_edits = context.files_being_edited
    if pattern := detect_file_loop(file_edits):
        patterns.append(pattern)

    # Error repeat detection
    if pattern := detect_error_repeat(context.recent_errors):
        patterns.append(pattern)

    # Tool loop detection
    if pattern := detect_tool_loop(context.recent_tools):
        patterns.append(pattern)

    return patterns


# =============================================================================
# CLARIFICATION GENERATION
# =============================================================================

def generate_clarification_prompt(context: ClarificationContext) -> str:
    """
    Generate a self-clarification prompt based on context.

    This prompt is designed to force Claude to step back and articulate
    the actual problem being solved.
    """
    lines = []

    lines.append("Given the recent activity pattern:")
    lines.append("")

    # Recent actions summary
    if context.recent_tools:
        lines.append("📋 Recent actions:")
        for tool in context.recent_tools[-5:]:
            if not tool or not isinstance(tool, dict):
                continue
            tool_name = tool.get("tool", "Unknown")
            success = "✓" if tool.get("success", True) else "✗"
            input_preview = tool.get("input_preview", "")
            if isinstance(input_preview, dict):
                input_preview = str(input_preview)[:50]
            else:
                input_preview = str(input_preview)[:50]
            lines.append(f"  {success} {tool_name}: {input_preview}")
        lines.append("")

    # Errors
    if context.recent_errors:
        lines.append("❌ Recent errors:")
        for err in context.recent_errors[-3:]:
            lines.append(f"  • {err[:80]}")
        lines.append("")

    # Files being edited
    if context.files_being_edited:
        from collections import Counter
        file_counts = Counter(context.files_being_edited)
        lines.append("📁 Files being edited:")
        for file_path, count in file_counts.most_common(3):
            lines.append(f"  • {Path(file_path).name} ({count}x)")
        lines.append("")

    # The clarifying questions
    lines.append("🤔 Clarification needed:")
    lines.append("")
    lines.append("1. What is the ACTUAL problem being solved?")
    lines.append("   (Not the symptom, but the root cause)")
    lines.append("")
    lines.append("2. Why haven't previous attempts worked?")
    lines.append("   (What's different about the current approach?)")
    lines.append("")
    lines.append("3. What would success look like?")
    lines.append("   (Concrete verification criteria)")
    lines.append("")

    if context.stuck_patterns:
        lines.append("4. Given these detected patterns:")
        for pattern in context.stuck_patterns:
            lines.append(f"   • {pattern.pattern_type}: {pattern.evidence[0] if pattern.evidence else 'detected'}")
        lines.append("   What fundamental approach change is needed?")
        lines.append("")

    return "\n".join(lines)


def generate_clarification_injection(
    context: ClarificationContext,
    urgency: str = "suggestion"
) -> str:
    """
    Generate the clarification injection for display.

    This is formatted to be prominent and impossible to ignore.
    """
    prompt = generate_clarification_prompt(context)

    lines = []

    # Header based on urgency
    if urgency == "urgent":
        lines.append("╭─ ⚠️ SELF-CLARIFICATION REQUIRED ──────────────────╮")
    elif urgency == "recommendation":
        lines.append("╭─ 🔍 SELF-CLARIFICATION RECOMMENDED ───────────────╮")
    else:
        lines.append("╭─ 💡 CONSIDER CLARIFYING APPROACH ─────────────────╮")

    # Add pattern warnings
    if context.stuck_patterns:
        lines.append("│")
        lines.append("│ ⚠️ Stuck patterns detected:")
        for pattern in context.stuck_patterns:
            desc = pattern.evidence[0] if pattern.evidence else pattern.pattern_type
            lines.append(f"│   • {desc[:50]}")

    lines.append("│")

    # Add the prompt
    for line in prompt.split("\n"):
        lines.append(f"│ {line}")

    lines.append("│")
    lines.append("│ Take a moment to answer these questions before")
    lines.append("│ continuing with the same approach.")
    lines.append("╰────────────────────────────────────────────────────╯")

    return "\n".join(lines)


# =============================================================================
# CONTEXT GATHERING
# =============================================================================

def gather_clarification_context(session_log: Optional[Path] = None) -> ClarificationContext:
    """
    Gather context from the current session for clarification.

    Imports are deferred to avoid circular dependencies.
    """
    context = ClarificationContext()

    try:
        from context_monitor import load_session_entries
        from proof_utils import get_session_log_path
        from edge_utils import load_yaml_state

        # Get session log
        if session_log is None:
            session_log = get_session_log_path()

        if session_log and session_log.exists():
            entries = load_session_entries(session_log)

            # Recent tools (last 20)
            context.recent_tools = entries[-20:] if entries else []

            # Extract errors
            for entry in entries[-20:]:
                if not entry.get("success", True):
                    output = entry.get("output_preview", "")
                    if output:
                        context.recent_errors.append(str(output)[:200])

            # Extract file edits
            for entry in entries:
                tool = entry.get("tool", "")
                if tool in ("Edit", "Write"):
                    input_data = entry.get("input_preview", {})
                    if isinstance(input_data, dict):
                        fp = input_data.get("file_path") or input_data.get("file", "")
                        if fp:
                            context.files_being_edited.append(fp)

            # Session metrics
            if entries:
                context.total_tool_calls = len(entries)
                first_ts = entries[0].get("timestamp", "")
                if first_ts:
                    try:
                        start = datetime.fromisoformat(first_ts.replace("Z", "+00:00"))
                        duration = (datetime.now() - start.replace(tzinfo=None)).total_seconds() / 60
                        context.session_duration_minutes = duration
                    except (ValueError, TypeError):
                        pass

        # Get current objective from state
        state = load_yaml_state() or {}
        context.current_objective = state.get("objective", "")

    except ImportError:
        _log_debug("Could not import dependencies for context gathering")
    except Exception as e:
        _log_debug(f"Error gathering context: {e}")

    # Detect stuck patterns
    context.stuck_patterns = detect_stuck_patterns(context)

    return context


# =============================================================================
# MAIN INTERFACE
# =============================================================================

def should_trigger_clarification(
    drift_signals_fired: int = 0,
    drift_signals_acted_on: int = 0,
    same_error_count: int = 0,
    same_file_edits: int = 0
) -> bool:
    """
    Check if clarification should be triggered based on session health.

    This is a quick check before gathering full context.
    """
    # Check cooldown first
    if not _can_offer_clarification():
        return False

    drift_threshold = _get_threshold("drift_threshold")
    error_threshold = _get_threshold("error_repeat_threshold")
    file_threshold = _get_threshold("same_file_edit_threshold")

    drift_ignored = drift_signals_fired - drift_signals_acted_on

    return (
        drift_ignored >= drift_threshold or
        same_error_count >= error_threshold or
        same_file_edits >= file_threshold
    )


def check_and_offer_clarification(
    intervention_level: str = "advise"
) -> Optional[str]:
    """
    Main integration point for pre_tool.py.

    Checks if clarification is warranted and returns formatted injection.
    Returns None if no clarification needed.

    Imports are deferred to avoid circular dependencies. This module may import:
    - proof_utils (get_session_log_path)
    - context_monitor (load_session_entries)
    - edge_utils (load_yaml_state)
    - active_intervention (SessionHealth)
    """
    if intervention_level == "observe":
        return None

    # Check cooldown
    if not _can_offer_clarification():
        return None

    try:
        # Get session health for quick check
        from active_intervention import _current_health as health

        if not should_trigger_clarification(
            drift_signals_fired=health.drift_signals_fired,
            drift_signals_acted_on=health.drift_signals_fired - health.drift_signals_ignored,
            same_error_count=health.same_error_count,
            same_file_edits=0,  # Would need tracking
        ):
            return None

        # Gather full context
        context = gather_clarification_context()

        if not context.stuck_patterns:
            return None

        # Determine urgency
        urgency = "suggestion"
        severe_count = sum(1 for p in context.stuck_patterns if p.severity == "severe")
        moderate_count = sum(1 for p in context.stuck_patterns if p.severity == "moderate")

        if severe_count >= 1 or moderate_count >= 2:
            urgency = "urgent"
        elif moderate_count >= 1:
            urgency = "recommendation"

        # Only surface based on intervention level
        if intervention_level == "advise" and urgency == "suggestion":
            return None  # Too subtle for advise level

        # Mark that we offered clarification (for cooldown)
        _mark_clarification_offered()

        # Generate injection
        return generate_clarification_injection(context, urgency)

    except ImportError:
        return None
    except Exception as e:
        _log_debug(f"check_and_offer_clarification error: {e}")
        return None


def get_clarification_for_health(
    health: Any,  # SessionHealth from active_intervention
    intervention_level: str = "advise"
) -> Optional[str]:
    """
    Alternative entry point using SessionHealth directly.

    Useful when pre_tool.py already has health metrics.
    """
    if intervention_level == "observe":
        return None

    if not _can_offer_clarification():
        return None

    try:
        # Quick check
        drift_ignored = getattr(health, 'drift_signals_ignored', 0)
        same_error = getattr(health, 'same_error_count', 0)

        if not should_trigger_clarification(
            drift_signals_fired=getattr(health, 'drift_signals_fired', 0),
            drift_signals_acted_on=getattr(health, 'drift_signals_fired', 0) - drift_ignored,
            same_error_count=same_error,
        ):
            return None

        # Gather context and generate
        context = gather_clarification_context()

        if not context.stuck_patterns:
            return None

        urgency = "recommendation" if same_error >= 3 or drift_ignored >= 3 else "suggestion"

        if intervention_level == "advise" and urgency == "suggestion":
            return None

        _mark_clarification_offered()
        return generate_clarification_injection(context, urgency)

    except Exception as e:
        _log_debug(f"get_clarification_for_health error: {e}")
        return None


# =============================================================================
# CLARIFICATION STORAGE (for analytics)
# =============================================================================

def _get_clarifications_path() -> Path:
    """Get path to clarifications log."""
    return Path(__file__).parent.parent.parent / ".proof" / "clarifications.jsonl"


def log_clarification(
    context: ClarificationContext,
    was_helpful: Optional[bool] = None
) -> bool:
    """Log a clarification event for later analysis."""
    clarifications_path = _get_clarifications_path()

    try:
        clarifications_path.parent.mkdir(parents=True, exist_ok=True)

        entry = {
            "timestamp": datetime.now().isoformat(),
            "patterns": [p.to_dict() for p in context.stuck_patterns],
            "tool_calls": context.total_tool_calls,
            "duration_minutes": context.session_duration_minutes,
            "files_edited": len(set(context.files_being_edited)),
            "errors_count": len(context.recent_errors),
            "was_helpful": was_helpful,
        }

        with open(clarifications_path, 'a') as f:
            f.write(json.dumps(entry) + '\n')

        return True
    except OSError:
        return False


# =============================================================================
# QUICK TEST
# =============================================================================

if __name__ == "__main__":
    print("Self-Clarification - Self Test")
    print("=" * 50)

    # Test stuck pattern detection
    print("\n--- Stuck Pattern Detection ---")

    # Test error repeat
    errors = ["Error: undefined variable 'x' at line 5"] * 4
    pattern = detect_error_repeat(errors, threshold_override=3)
    print(f"Error repeat detection: {pattern}")

    # Test file loop
    file_edits = ["src/app.py"] * 6
    pattern = detect_file_loop(file_edits, threshold_override=5)
    print(f"File loop detection: {pattern}")

    # Test drift ignored
    pattern = detect_drift_ignored(drift_signals_fired=5, drift_signals_acted_on=1)
    print(f"Drift ignored detection: {pattern}")

    # Test clarification generation
    print("\n--- Clarification Generation ---")

    test_context = ClarificationContext(
        recent_tools=[
            {"tool": "Edit", "input_preview": {"file_path": "src/app.py"}, "success": True},
            {"tool": "Bash", "input_preview": {"command": "python app.py"}, "success": False},
            {"tool": "Edit", "input_preview": {"file_path": "src/app.py"}, "success": True},
            {"tool": "Bash", "input_preview": {"command": "python app.py"}, "success": False},
        ],
        recent_errors=[
            "NameError: name 'user' is not defined",
            "NameError: name 'user' is not defined",
            "NameError: name 'user' is not defined",
        ],
        files_being_edited=["src/app.py"] * 5,
        current_objective="Fix authentication bug",
        session_duration_minutes=35.0,
        total_tool_calls=45,
    )

    # Detect patterns
    test_context.stuck_patterns = detect_stuck_patterns(test_context)
    print(f"Detected patterns: {[p.pattern_type for p in test_context.stuck_patterns]}")

    # Generate injection
    print("\n--- Clarification Injection ---")
    injection = generate_clarification_injection(test_context, "recommendation")
    print(injection)

    print("\nSelf-test complete.")
