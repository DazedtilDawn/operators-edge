#!/usr/bin/env python3
"""
Operator's Edge v8.0 - Smart Suggestions (Phase 6)

Move from passive surfacing to active guidance.

Capabilities:
1. Auto-Fix Offers - "Known fix found. Apply automatically? [Y/n]"
2. Related File Warnings - "You modified auth.py. billing.py usually changes with it."
3. Checkpoint Reminders - At 75% context: "Consider /compact now"
4. Drift Prevention - "You've edited this file 3 times. Step back and verify approach."
5. Pattern Nudges - "This type of file usually requires X"

This is proactive supervision, not reactive surfacing.
"""
import json
import os
import sys
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Any, Callable

# Add hooks directory to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


# =============================================================================
# CONFIGURATION
# =============================================================================

# Suggestion thresholds
FILE_CHURN_THRESHOLD = 3  # Edits before warning
CONTEXT_CHECKPOINT_THRESHOLD = 0.75  # 75% usage
CONTEXT_CRITICAL_THRESHOLD = 0.90  # 90% usage
RELATED_FILE_MIN_STRENGTH = 0.5  # Minimum strength to suggest

# Cooldown to avoid nagging (seconds)
SUGGESTION_COOLDOWN = 300  # 5 minutes between same suggestion type


# =============================================================================
# DATA STRUCTURES
# =============================================================================

@dataclass
class Suggestion:
    """A proactive suggestion to surface."""
    suggestion_type: str  # "auto_fix", "related_file", "checkpoint", "drift_warning", "pattern"
    severity: str  # "info", "warning", "action"
    title: str
    message: str
    action_prompt: Optional[str] = None  # For actionable suggestions
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "suggestion_type": self.suggestion_type,
            "severity": self.severity,
            "title": self.title,
            "message": self.message,
            "action_prompt": self.action_prompt,
            "metadata": self.metadata,
        }


@dataclass
class SuggestionContext:
    """Context for generating suggestions."""
    tool_name: str
    tool_input: Dict[str, Any]
    session_state: Dict[str, Any]
    session_log_path: Optional[Path] = None

    # Metrics from other v8.0 modules
    context_usage_percent: float = 0.0
    file_edit_counts: Dict[str, int] = field(default_factory=dict)
    recent_failures: List[Dict[str, Any]] = field(default_factory=list)
    known_fix: Optional[Any] = None  # KnownFix from codebase_knowledge
    related_files: List[Any] = field(default_factory=list)  # RelatedFile from codebase_knowledge
    drift_signals: List[Any] = field(default_factory=list)  # DriftSignal from drift_detector


# =============================================================================
# SUGGESTION TRACKING (avoid nagging)
# =============================================================================

# Track when suggestions were last shown
_suggestion_history: Dict[str, datetime] = {}


def _can_show_suggestion(suggestion_type: str, key: str = "") -> bool:
    """Check if enough time has passed to show this suggestion again."""
    full_key = f"{suggestion_type}:{key}" if key else suggestion_type
    last_shown = _suggestion_history.get(full_key)

    if last_shown is None:
        return True

    elapsed = (datetime.now() - last_shown).total_seconds()
    return elapsed >= SUGGESTION_COOLDOWN


def _mark_suggestion_shown(suggestion_type: str, key: str = "") -> None:
    """Mark that a suggestion was shown."""
    full_key = f"{suggestion_type}:{key}" if key else suggestion_type
    _suggestion_history[full_key] = datetime.now()


def reset_suggestion_history() -> None:
    """Reset suggestion history (for testing)."""
    global _suggestion_history
    _suggestion_history = {}


# =============================================================================
# SUGGESTION GENERATORS
# =============================================================================

def suggest_auto_fix(ctx: SuggestionContext) -> Optional[Suggestion]:
    """
    Suggest applying a known fix automatically.

    Triggers when:
    - A Bash command failed
    - We have a known fix for the error
    - Fix has high confidence (>= 60%)
    """
    if ctx.tool_name != "Bash":
        return None

    if ctx.known_fix is None:
        return None

    # Check confidence threshold
    if ctx.known_fix.confidence < 0.6:
        return None

    fix_key = ctx.known_fix.error_signature[:50]
    if not _can_show_suggestion("auto_fix", fix_key):
        return None

    _mark_suggestion_shown("auto_fix", fix_key)

    # Build suggestion
    commands_hint = ""
    if ctx.known_fix.fix_commands:
        commands_hint = f"\n\nSuggested commands:\n" + "\n".join(
            f"  `{cmd}`" for cmd in ctx.known_fix.fix_commands[:3]
        )

    return Suggestion(
        suggestion_type="auto_fix",
        severity="action",
        title="💡 Known Fix Available",
        message=(
            f"This error has been fixed before: **{ctx.known_fix.fix_description}**\n"
            f"Confidence: {ctx.known_fix.confidence*100:.0f}% "
            f"(used {ctx.known_fix.times_used}x)"
            f"{commands_hint}"
        ),
        action_prompt="Apply this fix?",
        metadata={
            "fix_description": ctx.known_fix.fix_description,
            "fix_commands": ctx.known_fix.fix_commands,
            "fix_files": ctx.known_fix.fix_files,
            "confidence": ctx.known_fix.confidence,
        }
    )


def suggest_related_files(ctx: SuggestionContext) -> Optional[Suggestion]:
    """
    Suggest checking related files that usually change together.

    Triggers when:
    - Editing a file
    - File has known co-change patterns
    - Related files have strength >= threshold
    """
    if ctx.tool_name not in ("Edit", "Write", "NotebookEdit"):
        return None

    if not ctx.related_files:
        return None

    file_path = ctx.tool_input.get("file_path", "")
    if not file_path:
        return None

    # Filter to strong relations
    strong_relations = [
        r for r in ctx.related_files
        if r.strength >= RELATED_FILE_MIN_STRENGTH
    ]

    if not strong_relations:
        return None

    # Check cooldown
    if not _can_show_suggestion("related_file", file_path):
        return None

    _mark_suggestion_shown("related_file", file_path)

    # Build suggestion
    file_list = "\n".join(
        f"  - `{r.file_path}` ({r.strength*100:.0f}% correlated)"
        for r in strong_relations[:5]
    )

    return Suggestion(
        suggestion_type="related_file",
        severity="info",
        title="🔗 Related Files",
        message=(
            f"When modifying `{Path(file_path).name}`, these files often change too:\n"
            f"{file_list}\n\n"
            "Consider whether they need updates as well."
        ),
        metadata={
            "source_file": file_path,
            "related_files": [r.file_path for r in strong_relations],
        }
    )


def suggest_checkpoint(ctx: SuggestionContext) -> Optional[Suggestion]:
    """
    Suggest creating a checkpoint when context usage is high.

    Triggers when:
    - Context usage >= 75%
    - Haven't suggested recently
    """
    if ctx.context_usage_percent < CONTEXT_CHECKPOINT_THRESHOLD * 100:
        return None

    if not _can_show_suggestion("checkpoint"):
        return None

    _mark_suggestion_shown("checkpoint")

    is_critical = ctx.context_usage_percent >= CONTEXT_CRITICAL_THRESHOLD * 100

    if is_critical:
        return Suggestion(
            suggestion_type="checkpoint",
            severity="warning",
            title="🔴 Context Critical",
            message=(
                f"Context window is at **{ctx.context_usage_percent:.0f}%** capacity.\n\n"
                "Recommended actions:\n"
                "1. Generate a checkpoint summary\n"
                "2. Consider starting a new session\n"
                "3. Use `/compact` to compress context"
            ),
            action_prompt="Generate checkpoint now?",
            metadata={
                "context_usage": ctx.context_usage_percent,
                "severity": "critical"
            }
        )
    else:
        return Suggestion(
            suggestion_type="checkpoint",
            severity="info",
            title="📊 Context Checkpoint Reminder",
            message=(
                f"Context window is at **{ctx.context_usage_percent:.0f}%** capacity.\n\n"
                "Consider:\n"
                "- Summarizing completed work\n"
                "- Focusing on the immediate task\n"
                "- Using `/compact` if available"
            ),
            metadata={
                "context_usage": ctx.context_usage_percent,
                "severity": "warning"
            }
        )


def suggest_drift_prevention(ctx: SuggestionContext) -> Optional[Suggestion]:
    """
    Proactively warn about potential drift before it becomes a problem.

    Triggers when:
    - Same file edited multiple times
    - Same command pattern failing
    - Drift signals detected
    """
    suggestions = []

    # Check file churn
    file_path = ctx.tool_input.get("file_path", "")
    if file_path:
        edit_count = ctx.file_edit_counts.get(file_path, 0)
        if edit_count >= FILE_CHURN_THRESHOLD:
            if _can_show_suggestion("drift_file", file_path):
                _mark_suggestion_shown("drift_file", file_path)
                suggestions.append(Suggestion(
                    suggestion_type="drift_warning",
                    severity="warning",
                    title="⚠️ File Churn Detected",
                    message=(
                        f"You've edited `{Path(file_path).name}` **{edit_count} times** this session.\n\n"
                        "This might indicate:\n"
                        "- Incremental fixes instead of understanding root cause\n"
                        "- Missing a pattern or requirement\n\n"
                        "Consider: What are you trying to achieve? Is there a different approach?"
                    ),
                    metadata={
                        "file": file_path,
                        "edit_count": edit_count
                    }
                ))

    # Check drift signals from detector
    if ctx.drift_signals:
        critical_signals = [s for s in ctx.drift_signals if s.severity == "critical"]
        if critical_signals and _can_show_suggestion("drift_critical"):
            _mark_suggestion_shown("drift_critical")
            signal = critical_signals[0]
            suggestions.append(Suggestion(
                suggestion_type="drift_warning",
                severity="warning",
                title=f"🔴 {signal.signal_type}",
                message=f"{signal.message}\n\n**Suggestion:** {signal.suggestion}",
                metadata={
                    "signal_type": signal.signal_type,
                    "evidence": signal.evidence
                }
            ))

    return suggestions[0] if suggestions else None


def suggest_pattern_nudge(ctx: SuggestionContext) -> Optional[Suggestion]:
    """
    Nudge towards patterns based on file type or context.

    Triggers when:
    - Editing certain file types that have common patterns
    - Context suggests a particular workflow
    """
    file_path = ctx.tool_input.get("file_path", "")
    if not file_path:
        return None

    # Simple pattern nudges based on file type
    patterns = {
        "test_": "Remember to run tests after modifications.",
        "_test.py": "Remember to run tests after modifications.",
        ".test.": "Remember to run tests after modifications.",
        "__init__.py": "Changes to __init__.py may affect imports in dependent modules.",
        "migration": "Migrations should be tested in a clean database state.",
        "config": "Configuration changes may require service restart.",
        ".env": "Environment changes require reloading the application.",
        "package.json": "Don't forget to run npm install after package.json changes.",
        "requirements.txt": "Don't forget to pip install after requirements.txt changes.",
    }

    for pattern, nudge in patterns.items():
        if pattern in file_path.lower():
            nudge_key = f"{pattern}:{file_path}"
            if _can_show_suggestion("pattern_nudge", nudge_key):
                _mark_suggestion_shown("pattern_nudge", nudge_key)
                return Suggestion(
                    suggestion_type="pattern",
                    severity="info",
                    title="💡 Pattern Reminder",
                    message=nudge,
                    metadata={"pattern": pattern, "file": file_path}
                )

    return None


# =============================================================================
# MAIN INTERFACE
# =============================================================================

def generate_suggestions(ctx: SuggestionContext) -> List[Suggestion]:
    """
    Generate all applicable suggestions for the current context.

    Returns suggestions sorted by severity (warning > action > info).
    """
    suggestions = []

    # Run all suggestion generators
    generators = [
        suggest_auto_fix,
        suggest_related_files,
        suggest_checkpoint,
        suggest_drift_prevention,
        suggest_pattern_nudge,
    ]

    for generator in generators:
        try:
            suggestion = generator(ctx)
            if suggestion:
                suggestions.append(suggestion)
        except Exception:
            continue  # Don't fail on individual generators

    # Sort by severity (warning first, then action, then info)
    severity_order = {"warning": 0, "action": 1, "info": 2}
    suggestions.sort(key=lambda s: severity_order.get(s.severity, 3))

    return suggestions


def format_suggestions(suggestions: List[Suggestion], max_display: int = 3) -> str:
    """
    Format suggestions for display to Claude.

    Limits output to avoid overwhelming context.
    """
    if not suggestions:
        return ""

    lines = [
        "",
        "=" * 60,
        "🎯 SMART SUGGESTIONS",
        "=" * 60,
        ""
    ]

    for i, suggestion in enumerate(suggestions[:max_display]):
        icon = {
            "warning": "⚠️",
            "action": "💡",
            "info": "ℹ️"
        }.get(suggestion.severity, "•")

        lines.append(f"{icon} **{suggestion.title}**")
        lines.append("")
        lines.append(suggestion.message)

        if suggestion.action_prompt:
            lines.append("")
            lines.append(f"**→ {suggestion.action_prompt}**")

        lines.append("")
        lines.append("-" * 40)
        lines.append("")

    if len(suggestions) > max_display:
        lines.append(f"({len(suggestions) - max_display} more suggestions available)")
        lines.append("")

    return "\n".join(lines)


# =============================================================================
# INTEGRATION HELPERS
# =============================================================================

def build_suggestion_context(
    tool_name: str,
    tool_input: Dict[str, Any],
    state: Dict[str, Any],
    session_log: Optional[Path] = None
) -> SuggestionContext:
    """
    Build suggestion context by integrating with other v8.0 modules.

    This is the main entry point for hooks to get suggestions.
    """
    ctx = SuggestionContext(
        tool_name=tool_name,
        tool_input=tool_input,
        session_state=state,
        session_log_path=session_log
    )

    # Get context usage from context_monitor
    try:
        from context_monitor import estimate_context_usage
        if session_log and session_log.exists():
            estimate = estimate_context_usage(session_log)
            ctx.context_usage_percent = estimate.usage_percentage * 100
    except ImportError:
        pass
    except Exception:
        pass

    # Get file edit counts from session log
    if session_log and session_log.exists():
        try:
            from context_monitor import load_session_entries
            entries = load_session_entries(session_log)
            file_counts = {}
            for entry in entries:
                if entry.get("tool") in ("Edit", "Write"):
                    input_data = entry.get("input_preview", {})
                    if isinstance(input_data, dict):
                        fp = input_data.get("file_path") or input_data.get("file", "")
                        if fp:
                            file_counts[fp] = file_counts.get(fp, 0) + 1
            ctx.file_edit_counts = file_counts
        except ImportError:
            pass
        except Exception:
            pass

    # Get related files from codebase_knowledge
    file_path = tool_input.get("file_path", "")
    if file_path and tool_name in ("Edit", "Write", "NotebookEdit"):
        try:
            from codebase_knowledge import get_related_files
            ctx.related_files = get_related_files(file_path, min_strength=0.3)
        except ImportError:
            pass
        except Exception:
            pass

    # Get drift signals from drift_detector
    if session_log and session_log.exists():
        try:
            from drift_detector import detect_drift
            ctx.drift_signals = detect_drift(session_log, state, lookback_minutes=30)
        except ImportError:
            pass
        except Exception:
            pass

    return ctx


def get_suggestions_for_tool(
    tool_name: str,
    tool_input: Dict[str, Any],
    state: Dict[str, Any],
    session_log: Optional[Path] = None,
    known_fix: Optional[Any] = None
) -> str:
    """
    Main entry point: Get formatted suggestions for a tool call.

    Returns formatted string ready for display, or empty string if no suggestions.
    """
    ctx = build_suggestion_context(tool_name, tool_input, state, session_log)

    # Add known fix if provided
    if known_fix:
        ctx.known_fix = known_fix

    suggestions = generate_suggestions(ctx)

    if suggestions:
        return format_suggestions(suggestions)

    return ""


# =============================================================================
# QUICK TEST
# =============================================================================

if __name__ == "__main__":
    print("Smart Suggestions - Self Test")
    print("=" * 40)

    # Reset history for clean test
    reset_suggestion_history()

    # Test checkpoint suggestion
    print("\n--- Checkpoint Suggestion ---")
    ctx = SuggestionContext(
        tool_name="Bash",
        tool_input={"command": "pytest"},
        session_state={},
        context_usage_percent=80.0
    )
    suggestions = generate_suggestions(ctx)
    for s in suggestions:
        print(f"  {s.severity}: {s.title}")

    # Test file churn suggestion
    print("\n--- File Churn Suggestion ---")
    ctx = SuggestionContext(
        tool_name="Edit",
        tool_input={"file_path": "/app/utils.py"},
        session_state={},
        file_edit_counts={"/app/utils.py": 4}
    )
    suggestions = generate_suggestions(ctx)
    for s in suggestions:
        print(f"  {s.severity}: {s.title}")

    # Test pattern nudge
    print("\n--- Pattern Nudge ---")
    ctx = SuggestionContext(
        tool_name="Edit",
        tool_input={"file_path": "/app/test_utils.py"},
        session_state={},
    )
    suggestions = generate_suggestions(ctx)
    for s in suggestions:
        print(f"  {s.severity}: {s.title}")

    print()
    print("Self-test complete.")
