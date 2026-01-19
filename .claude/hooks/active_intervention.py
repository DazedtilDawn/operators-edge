#!/usr/bin/env python3
"""
Operator's Edge v8.0 - Active Intervention (Phase 8)

Moving from passive supervision to active guidance.

The Core Insight:
When we KNOW how to fix something, we shouldn't just whisper it -
we should make it impossible to ignore.

Intervention Levels:
1. observe  - Collect metrics only, no output
2. advise   - Surface suggestions (current behavior)
3. guide    - Inject context before tool calls
4. intervene - Block risky actions, require acknowledgment

Design Philosophy:
- Start conservative (advise by default)
- Escalate automatically based on session health
- Always maintain audit trail
- Never surprise the user

"The people who are crazy enough to think they can change the world
 are the ones who do." - Steve Jobs
"""
import json
import os
import sys
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Any, Tuple

# Add hooks directory to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


# =============================================================================
# DATA STRUCTURES
# =============================================================================

@dataclass
class InterventionEvent:
    """A logged intervention for audit purposes."""
    timestamp: str
    intervention_type: str  # "context_inject", "fix_prompt", "escalation", "block"
    trigger: str            # What caused this intervention
    action_taken: str       # What was done
    session_id: str = ""
    outcome: str = ""       # Filled in later if we can detect it
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "timestamp": self.timestamp,
            "intervention_type": self.intervention_type,
            "trigger": self.trigger,
            "action_taken": self.action_taken,
            "session_id": self.session_id,
            "outcome": self.outcome,
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "InterventionEvent":
        return cls(
            timestamp=data.get("timestamp", ""),
            intervention_type=data.get("intervention_type", ""),
            trigger=data.get("trigger", ""),
            action_taken=data.get("action_taken", ""),
            session_id=data.get("session_id", ""),
            outcome=data.get("outcome", ""),
            metadata=data.get("metadata", {}),
        )


@dataclass
class SessionHealth:
    """Current health metrics for intervention level determination."""
    context_usage_percent: float = 0.0
    drift_signals_fired: int = 0
    drift_signals_ignored: int = 0
    same_error_count: int = 0
    session_duration_minutes: float = 0.0
    tool_calls: int = 0

    # Pending issues
    pending_error: Optional[str] = None
    pending_fix: Optional[Any] = None  # KnownFix from codebase_knowledge


@dataclass
class InterventionConfig:
    """Configuration for active intervention."""
    enabled: bool = True
    default_level: str = "advise"  # observe, advise, guide, intervene
    max_level: str = "guide"       # Cap escalation at this level
    auto_escalate: bool = True

    # Auto-fix settings
    auto_fix_enabled: bool = False
    auto_fix_confidence: float = 0.9
    auto_fix_min_uses: int = 3

    # Context injection settings
    context_injection_enabled: bool = True
    max_context_injection_chars: int = 500

    # Dangerous command patterns to block at 'intervene' level
    blocked_patterns: List[str] = field(default_factory=lambda: [
        "rm -rf /",
        "rm -rf ~",
        "git push --force",
        "DROP TABLE",
        "DELETE FROM",
    ])


# =============================================================================
# CONFIGURATION
# =============================================================================

DEFAULT_CONFIG = InterventionConfig()


def get_config_path() -> Path:
    """Get path to intervention config."""
    return Path(__file__).parent.parent.parent / ".proof" / "v8_config.json"


def load_intervention_config() -> InterventionConfig:
    """Load intervention config from disk."""
    config_path = get_config_path()
    if not config_path.exists():
        return DEFAULT_CONFIG

    try:
        with open(config_path) as f:
            data = json.load(f)
            intervention = data.get("intervention", {})

            return InterventionConfig(
                enabled=intervention.get("enabled", True),
                default_level=intervention.get("default_level", "advise"),
                max_level=intervention.get("max_level", "guide"),
                auto_escalate=intervention.get("auto_escalate", True),
                auto_fix_enabled=intervention.get("auto_fix_enabled", False),
                auto_fix_confidence=intervention.get("auto_fix_confidence", 0.9),
                auto_fix_min_uses=intervention.get("auto_fix_min_uses", 3),
                context_injection_enabled=intervention.get("context_injection_enabled", True),
                max_context_injection_chars=intervention.get("max_context_injection_chars", 500),
                blocked_patterns=intervention.get("blocked_patterns", DEFAULT_CONFIG.blocked_patterns),
            )
    except (json.JSONDecodeError, OSError):
        return DEFAULT_CONFIG


def save_intervention_config(config: InterventionConfig) -> bool:
    """Save intervention config to disk."""
    config_path = get_config_path()

    try:
        # Load existing config
        existing = {}
        if config_path.exists():
            with open(config_path) as f:
                existing = json.load(f)

        # Update intervention section
        existing["intervention"] = {
            "enabled": config.enabled,
            "default_level": config.default_level,
            "max_level": config.max_level,
            "auto_escalate": config.auto_escalate,
            "auto_fix_enabled": config.auto_fix_enabled,
            "auto_fix_confidence": config.auto_fix_confidence,
            "auto_fix_min_uses": config.auto_fix_min_uses,
            "context_injection_enabled": config.context_injection_enabled,
            "max_context_injection_chars": config.max_context_injection_chars,
            "blocked_patterns": config.blocked_patterns,
        }

        config_path.parent.mkdir(parents=True, exist_ok=True)
        with open(config_path, 'w') as f:
            json.dump(existing, f, indent=2)

        return True
    except OSError:
        return False


# =============================================================================
# AUDIT LOGGING
# =============================================================================

def get_audit_path() -> Path:
    """Get path to intervention audit log."""
    return Path(__file__).parent.parent.parent / ".proof" / "intervention_audit.jsonl"


def log_intervention(event: InterventionEvent) -> bool:
    """Log an intervention event to the audit trail."""
    audit_path = get_audit_path()

    try:
        audit_path.parent.mkdir(parents=True, exist_ok=True)
        with open(audit_path, 'a') as f:
            f.write(json.dumps(event.to_dict()) + '\n')
        return True
    except OSError:
        return False


def get_recent_interventions(limit: int = 50) -> List[InterventionEvent]:
    """Get recent interventions from the audit log."""
    audit_path = get_audit_path()
    if not audit_path.exists():
        return []

    events = []
    try:
        with open(audit_path) as f:
            for line in f:
                line = line.strip()
                if line:
                    try:
                        events.append(InterventionEvent.from_dict(json.loads(line)))
                    except json.JSONDecodeError:
                        continue
    except OSError:
        return []

    # Return most recent
    return events[-limit:]


# =============================================================================
# INTERVENTION LEVEL DETERMINATION
# =============================================================================

LEVEL_ORDER = ["observe", "advise", "guide", "intervene"]


def level_value(level: str) -> int:
    """Get numeric value for level comparison."""
    try:
        return LEVEL_ORDER.index(level)
    except ValueError:
        return 1  # Default to advise


def determine_intervention_level(
    health: SessionHealth,
    config: InterventionConfig
) -> str:
    """
    Determine appropriate intervention level based on session health.

    Escalation triggers:
    - High context usage (>85%) → guide
    - Multiple ignored drift signals → guide
    - Same error repeated 3+ times → intervene
    - Very long session (>60 min) → guide

    Always respects config.max_level as ceiling.
    """
    if not config.enabled:
        return "observe"

    if not config.auto_escalate:
        return config.default_level

    level = config.default_level

    # Escalate based on session health
    escalation_reasons = []

    # High context usage
    if health.context_usage_percent >= 85:
        if level_value("guide") > level_value(level):
            level = "guide"
            escalation_reasons.append("high context usage")

    # Ignored drift signals
    if health.drift_signals_ignored >= 3:
        if level_value("guide") > level_value(level):
            level = "guide"
            escalation_reasons.append("ignored drift signals")

    # Same error repeated
    if health.same_error_count >= 3:
        if level_value("intervene") > level_value(level):
            level = "intervene"
            escalation_reasons.append("repeated errors")

    # Long session
    if health.session_duration_minutes >= 60:
        if level_value("guide") > level_value(level):
            level = "guide"
            escalation_reasons.append("long session")

    # Cap at max level
    if level_value(level) > level_value(config.max_level):
        level = config.max_level

    return level


# =============================================================================
# INTERVENTION ACTIONS
# =============================================================================

def should_inject_fix_context(
    health: SessionHealth,
    config: InterventionConfig,
    level: str
) -> bool:
    """Determine if we should inject fix context before next tool call."""
    # Need a pending error and fix
    if not health.pending_error or not health.pending_fix:
        return False

    # Context injection must be enabled
    if not config.context_injection_enabled:
        return False

    # At guide level or higher, always inject
    if level_value(level) >= level_value("guide"):
        return True

    # At advise level, inject for high-confidence fixes
    if level == "advise" and health.pending_fix:
        fix = health.pending_fix
        if hasattr(fix, 'confidence') and fix.confidence >= 0.7:
            return True

    return False


def format_fix_injection(fix: Any, health: SessionHealth) -> str:
    """
    Format a known fix for prominent injection.

    This is designed to be IMPOSSIBLE TO IGNORE.
    """
    lines = [
        "",
        "╔" + "═" * 58 + "╗",
        "║" + " 🔧 KNOWN FIX AVAILABLE".center(58) + "║",
        "╠" + "═" * 58 + "╣",
        "║" + "".center(58) + "║",
    ]

    # Fix description
    desc = getattr(fix, 'fix_description', str(fix))[:50]
    lines.append("║" + f"  {desc}".ljust(58) + "║")
    lines.append("║" + "".center(58) + "║")

    # Commands
    commands = getattr(fix, 'fix_commands', [])
    if commands:
        lines.append("║" + "  Suggested commands:".ljust(58) + "║")
        for cmd in commands[:3]:
            cmd_line = f"    $ {cmd}"[:54]
            lines.append("║" + cmd_line.ljust(58) + "║")
        lines.append("║" + "".center(58) + "║")

    # Confidence and usage
    confidence = getattr(fix, 'confidence', 0) * 100
    times_used = getattr(fix, 'times_used', 0)
    lines.append("║" + f"  Confidence: {confidence:.0f}% (used {times_used}x)".ljust(58) + "║")

    lines.append("║" + "".center(58) + "║")
    lines.append("║" + "  ⚡ Consider applying this fix before retrying".ljust(58) + "║")
    lines.append("║" + "".center(58) + "║")
    lines.append("╚" + "═" * 58 + "╝")
    lines.append("")

    return "\n".join(lines)


def should_block_command(
    command: str,
    config: InterventionConfig,
    level: str
) -> Tuple[bool, str]:
    """
    Check if a command should be blocked at current intervention level.

    Returns (should_block, reason)
    """
    if level != "intervene":
        return False, ""

    # Check against blocked patterns
    cmd_lower = command.lower()
    for pattern in config.blocked_patterns:
        if pattern.lower() in cmd_lower:
            return True, f"Matches blocked pattern: {pattern}"

    return False, ""


def format_block_warning(command: str, reason: str) -> str:
    """Format a command block warning."""
    return f"""
╔════════════════════════════════════════════════════════════╗
║  🛑 COMMAND BLOCKED                                        ║
╠════════════════════════════════════════════════════════════╣
║                                                            ║
║  The following command was blocked for safety:             ║
║                                                            ║
║    {command[:50].ljust(50)}  ║
║                                                            ║
║  Reason: {reason[:45].ljust(45)}  ║
║                                                            ║
║  To proceed, either:                                       ║
║  1. Modify the command to be safer                         ║
║  2. Disable intervention with: /edge intervention off      ║
║                                                            ║
╚════════════════════════════════════════════════════════════╝
"""


# =============================================================================
# PROACTIVE CONTEXT INJECTION
# =============================================================================

def get_proactive_context(
    tool_name: str,
    tool_input: Dict[str, Any],
    health: SessionHealth,
    config: InterventionConfig
) -> Optional[str]:
    """
    Build proactive context to inject before tool execution.

    This surfaces relevant knowledge from previous sessions
    to help Claude avoid rediscovering things.
    """
    if not config.context_injection_enabled:
        return None

    context_parts = []

    # 1. Inject known fix if available
    if should_inject_fix_context(health, config, determine_intervention_level(health, config)):
        fix_context = format_fix_injection(health.pending_fix, health)
        context_parts.append(fix_context)

    # 2. Inject file-specific knowledge for edits
    if tool_name in ("Edit", "Write", "NotebookEdit"):
        file_path = tool_input.get("file_path", "")
        if file_path:
            file_context = get_file_specific_context(file_path)
            if file_context:
                context_parts.append(file_context)

    # 3. Inject co-change reminders
    if tool_name in ("Edit", "Write", "NotebookEdit"):
        file_path = tool_input.get("file_path", "")
        if file_path:
            cochange_context = get_cochange_context(file_path)
            if cochange_context:
                context_parts.append(cochange_context)

    if not context_parts:
        return None

    # Respect size limit
    combined = "\n".join(context_parts)
    if len(combined) > config.max_context_injection_chars:
        # Truncate intelligently (keep fix injection, trim others)
        combined = combined[:config.max_context_injection_chars] + "\n..."

    return combined


def get_file_specific_context(file_path: str) -> Optional[str]:
    """Get context about common issues with this file."""
    try:
        from codebase_knowledge import get_file_fixes

        fixes = get_file_fixes(file_path)
        if not fixes:
            return None

        # Format as context
        lines = [
            f"📁 Note about {Path(file_path).name}:",
        ]
        for fix in fixes[:2]:  # Max 2 fixes
            lines.append(f"  • Previous issue: {fix.fix_description[:60]}")

        return "\n".join(lines)

    except ImportError:
        return None
    except Exception:
        return None


def get_cochange_context(file_path: str) -> Optional[str]:
    """Get context about files that usually change together."""
    try:
        from codebase_knowledge import get_related_files

        related = get_related_files(file_path, min_strength=0.6)
        if not related:
            return None

        # Only show strong relationships
        strong = [r for r in related if r.strength >= 0.6][:3]
        if not strong:
            return None

        lines = [
            f"🔗 Files often changed with {Path(file_path).name}:",
        ]
        for rel in strong:
            pct = int(rel.strength * 100)
            lines.append(f"  • {Path(rel.file_path).name} ({pct}% correlation)")

        return "\n".join(lines)

    except ImportError:
        return None
    except Exception:
        return None


# =============================================================================
# MAIN INTERVENTION INTERFACE
# =============================================================================

# Session health state (in-memory for current session)
_current_health = SessionHealth()


def update_health_from_error(error_output: str, known_fix: Any = None) -> None:
    """Update session health after an error."""
    global _current_health

    _current_health.pending_error = error_output
    _current_health.pending_fix = known_fix

    # Track repeated errors
    if error_output:
        _current_health.same_error_count += 1


def update_health_from_success() -> None:
    """Update session health after a success."""
    global _current_health

    _current_health.pending_error = None
    _current_health.pending_fix = None
    _current_health.same_error_count = 0


def update_health_metrics(
    context_usage: float = 0,
    drift_signals: int = 0,
    drift_ignored: int = 0,
    duration_minutes: float = 0,
    tool_calls: int = 0
) -> None:
    """Update general health metrics."""
    global _current_health

    if context_usage > 0:
        _current_health.context_usage_percent = context_usage
    if drift_signals > 0:
        _current_health.drift_signals_fired = drift_signals
    if drift_ignored > 0:
        _current_health.drift_signals_ignored = drift_ignored
    if duration_minutes > 0:
        _current_health.session_duration_minutes = duration_minutes
    if tool_calls > 0:
        _current_health.tool_calls = tool_calls


def get_intervention_for_tool(
    tool_name: str,
    tool_input: Dict[str, Any],
    session_id: str = ""
) -> Tuple[str, bool]:
    """
    Get intervention output for a tool call.

    Returns (intervention_text, should_block)

    This is the main entry point called from pre_tool.py.
    """
    global _current_health

    config = load_intervention_config()
    if not config.enabled:
        return "", False

    level = determine_intervention_level(_current_health, config)

    # Check for command blocking (intervene level only)
    if tool_name == "Bash":
        command = tool_input.get("command", "")
        should_block, reason = should_block_command(command, config, level)
        if should_block:
            # Log the block
            log_intervention(InterventionEvent(
                timestamp=datetime.now().isoformat(),
                intervention_type="block",
                trigger=f"Command: {command[:100]}",
                action_taken=f"Blocked: {reason}",
                session_id=session_id,
            ))
            return format_block_warning(command, reason), True

    # Get proactive context
    context = get_proactive_context(tool_name, tool_input, _current_health, config)

    if context:
        # Log the injection
        log_intervention(InterventionEvent(
            timestamp=datetime.now().isoformat(),
            intervention_type="context_inject",
            trigger=f"Tool: {tool_name}",
            action_taken=f"Injected {len(context)} chars of context",
            session_id=session_id,
            metadata={"level": level}
        ))

    return context or "", False


def reset_health() -> None:
    """Reset session health (for new session or testing)."""
    global _current_health
    _current_health = SessionHealth()


# =============================================================================
# QUICK TEST
# =============================================================================

if __name__ == "__main__":
    print("Active Intervention - Self Test")
    print("=" * 40)

    # Test config loading
    config = load_intervention_config()
    print(f"Config loaded: enabled={config.enabled}, level={config.default_level}")

    # Test health tracking
    health = SessionHealth(
        context_usage_percent=75,
        drift_signals_fired=2,
        same_error_count=1,
        session_duration_minutes=30,
    )

    level = determine_intervention_level(health, config)
    print(f"Intervention level for healthy session: {level}")

    # Test escalation
    health.context_usage_percent = 90
    health.drift_signals_ignored = 4
    level = determine_intervention_level(health, config)
    print(f"Intervention level after issues: {level}")

    # Test fix injection formatting
    class MockFix:
        fix_description = "Install missing dependency"
        fix_commands = ["pip install requests"]
        confidence = 0.85
        times_used = 3

    health.pending_fix = MockFix()
    health.pending_error = "ModuleNotFoundError: No module named 'requests'"

    if should_inject_fix_context(health, config, "guide"):
        print("\n--- Fix Injection Preview ---")
        print(format_fix_injection(MockFix(), health))

    # Test command blocking
    should_block, reason = should_block_command("rm -rf /", config, "intervene")
    print(f"\nBlock 'rm -rf /': {should_block} ({reason})")

    should_block, reason = should_block_command("ls -la", config, "intervene")
    print(f"Block 'ls -la': {should_block}")

    print("\nSelf-test complete.")
