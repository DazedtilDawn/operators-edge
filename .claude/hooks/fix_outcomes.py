#!/usr/bin/env python3
"""
Operator's Edge v8.0 - Fix Outcome Tracking (Phase 9)

Closing the feedback loop: Did the surfaced fix actually work?

The Core Problem:
When we surface a fix, we don't track whether:
1. Claude followed the suggestion
2. The suggested command succeeded
3. The fix actually resolved the original error

This module tracks the complete lifecycle of fix suggestions,
enabling confidence to reflect actual outcomes.

Design Philosophy:
- Automatic detection (no manual reporting required)
- Conservative matching (precision over recall)
- Feedback to codebase_knowledge (fixes get smarter)

"The only way to do great work is to love what you do." - Steve Jobs
"""
import json
import os
import re
import sys
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Any, Tuple

# Add hooks directory to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


# =============================================================================
# CONFIGURATION
# =============================================================================

# Outcomes storage location
OUTCOMES_FILE = "fix_outcomes.jsonl"

# How many commands before considering a fix "ignored"
IGNORE_THRESHOLD = 5

# Maximum age for pending outcomes (prevent memory leaks)
MAX_PENDING_AGE_MINUTES = 30


# =============================================================================
# DATA STRUCTURES
# =============================================================================

@dataclass
class FixOutcome:
    """Track the outcome of a surfaced fix."""
    outcome_id: str
    fix_signature: str       # Hash from codebase_knowledge
    error_signature: str     # Original error text (truncated)
    surfaced_at: str
    surfaced_commands: List[str]

    # Outcome tracking
    followed: bool = False
    followed_at: Optional[str] = None
    followed_command: Optional[str] = None

    success: bool = False
    success_verified_at: Optional[str] = None

    # Correlation data
    next_commands: List[str] = field(default_factory=list)

    # Resolution
    resolved: bool = False
    resolution: str = ""  # "followed_success", "followed_failure", "ignored", "timeout"

    def to_dict(self) -> dict:
        return {
            "outcome_id": self.outcome_id,
            "fix_signature": self.fix_signature,
            "error_signature": self.error_signature,
            "surfaced_at": self.surfaced_at,
            "surfaced_commands": self.surfaced_commands,
            "followed": self.followed,
            "followed_at": self.followed_at,
            "followed_command": self.followed_command,
            "success": self.success,
            "success_verified_at": self.success_verified_at,
            "next_commands": self.next_commands,
            "resolved": self.resolved,
            "resolution": self.resolution,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "FixOutcome":
        return cls(
            outcome_id=data.get("outcome_id", ""),
            fix_signature=data.get("fix_signature", ""),
            error_signature=data.get("error_signature", ""),
            surfaced_at=data.get("surfaced_at", ""),
            surfaced_commands=data.get("surfaced_commands", []),
            followed=data.get("followed", False),
            followed_at=data.get("followed_at"),
            followed_command=data.get("followed_command"),
            success=data.get("success", False),
            success_verified_at=data.get("success_verified_at"),
            next_commands=data.get("next_commands", []),
            resolved=data.get("resolved", False),
            resolution=data.get("resolution", ""),
        )


# =============================================================================
# COMMAND MATCHING
# =============================================================================

def normalize_command(cmd: str) -> str:
    """
    Normalize a command for comparison.

    Handles common variations:
    - pip/pip3, python/python3
    - sudo prefix
    - Whitespace
    """
    if not cmd:
        return ""

    cmd = cmd.strip()

    # Normalize pip/pip3
    cmd = re.sub(r'^pip3\b', 'pip', cmd)

    # Normalize python/python3
    cmd = re.sub(r'^python3\b', 'python', cmd)

    # Remove sudo prefix
    cmd = re.sub(r'^sudo\s+', '', cmd)

    # Normalize npm aliases (npm i → npm install)
    cmd = re.sub(r'^npm\s+i\b', 'npm install', cmd)

    return cmd.lower()


def get_base_command(cmd: str) -> str:
    """
    Extract base command (e.g., 'pip install' from 'pip install requests').

    For common package managers and tools, returns the two-word command.
    """
    parts = cmd.split()
    if not parts:
        return ""

    if len(parts) >= 2:
        # Common two-word commands
        if parts[0] in ('pip', 'npm', 'yarn', 'git', 'docker', 'kubectl', 'cargo', 'go', 'brew'):
            return ' '.join(parts[:2])

    return parts[0]


def get_command_target(cmd: str) -> str:
    """
    Extract target (e.g., 'requests' from 'pip install requests==2.0').

    For install commands, extracts the package name without version.
    """
    parts = cmd.split()
    if len(parts) < 3:
        return ""

    # For install commands, get the package name
    target = parts[2]

    # Remove version specifiers (==, >=, <=, ~=, !=, @)
    target = re.split(r'[=<>~!@\[]', target)[0]

    return target.lower()


def command_matches_fix(actual: str, suggested_commands: List[str]) -> bool:
    """
    Check if the actual command matches any suggested fix command.

    Matching rules (in order):
    1. Exact match (normalized)
    2. Same base command + same target
    3. Base command match for simple commands
    """
    if not actual or not suggested_commands:
        return False

    actual_norm = normalize_command(actual)
    actual_base = get_base_command(actual_norm)
    actual_target = get_command_target(actual_norm)

    for suggested in suggested_commands:
        suggested_norm = normalize_command(suggested)

        # Rule 1: Exact match
        if actual_norm == suggested_norm:
            return True

        suggested_base = get_base_command(suggested_norm)
        suggested_target = get_command_target(suggested_norm)

        # Rule 2: Same base command + same target
        if actual_base and suggested_base and actual_base == suggested_base:
            if actual_target and suggested_target and actual_target == suggested_target:
                return True

            # Rule 3: Base match for simple commands (no target)
            if not suggested_target:
                # e.g., "git pull" matches "git pull origin main"
                return True

    return False


# =============================================================================
# OUTCOME STORAGE
# =============================================================================

def _get_outcomes_path() -> Path:
    """Get path to outcomes storage file."""
    proof_dir = Path(__file__).parent.parent.parent / ".proof"
    proof_dir.mkdir(parents=True, exist_ok=True)
    return proof_dir / OUTCOMES_FILE


def _save_outcome(outcome: FixOutcome) -> bool:
    """Append an outcome to the outcomes file."""
    path = _get_outcomes_path()
    try:
        with open(path, 'a') as f:
            f.write(json.dumps(outcome.to_dict()) + '\n')
        return True
    except OSError:
        return False


def load_outcomes(days: int = 7) -> List[FixOutcome]:
    """Load outcomes from the last N days."""
    path = _get_outcomes_path()
    if not path.exists():
        return []

    cutoff = datetime.now() - timedelta(days=days)
    outcomes = []

    try:
        with open(path) as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    data = json.loads(line)
                    outcome = FixOutcome.from_dict(data)

                    # Filter by date
                    if outcome.surfaced_at:
                        try:
                            surfaced = datetime.fromisoformat(outcome.surfaced_at)
                            if surfaced >= cutoff:
                                outcomes.append(outcome)
                        except ValueError:
                            outcomes.append(outcome)  # Include if date parse fails
                except json.JSONDecodeError:
                    continue
    except OSError:
        pass

    return outcomes


# =============================================================================
# PENDING OUTCOME TRACKING (In-Memory)
# =============================================================================

# Current pending outcome (one at a time)
_pending_outcome: Optional[FixOutcome] = None


def _get_pending_outcome() -> Optional[FixOutcome]:
    """Get the current pending outcome, if any."""
    global _pending_outcome

    if _pending_outcome is None:
        return None

    # Check for timeout
    try:
        surfaced = datetime.fromisoformat(_pending_outcome.surfaced_at)
        if (datetime.now() - surfaced).total_seconds() > MAX_PENDING_AGE_MINUTES * 60:
            # Timed out - resolve as timeout
            _pending_outcome.resolved = True
            _pending_outcome.resolution = "timeout"
            _save_outcome(_pending_outcome)
            _pending_outcome = None
            return None
    except ValueError:
        pass

    return _pending_outcome


def _store_pending_outcome(outcome: FixOutcome) -> None:
    """Store a pending outcome for tracking."""
    global _pending_outcome

    # If there's already a pending outcome, resolve it as ignored
    if _pending_outcome and not _pending_outcome.resolved:
        _pending_outcome.resolved = True
        _pending_outcome.resolution = "superseded"
        _save_outcome(_pending_outcome)

    _pending_outcome = outcome


def _clear_pending_outcome() -> None:
    """Clear the pending outcome."""
    global _pending_outcome
    _pending_outcome = None


def get_pending_fix_signature() -> Optional[str]:
    """Get the signature of the pending fix, if any."""
    pending = _get_pending_outcome()
    return pending.fix_signature if pending else None


# =============================================================================
# MAIN TRACKING INTERFACE
# =============================================================================

def generate_outcome_id() -> str:
    """Generate a unique outcome ID."""
    return uuid.uuid4().hex[:12]


def track_fix_surfaced(
    fix_signature: str,
    error_signature: str,
    fix_commands: List[str]
) -> str:
    """
    Record that a fix was surfaced and return tracking ID.

    Called from post_tool.py when lookup_known_fix finds a match.

    Args:
        fix_signature: Hash of the error (from codebase_knowledge)
        error_signature: The error text (truncated)
        fix_commands: Commands suggested by the fix

    Returns:
        The outcome ID for tracking
    """
    outcome_id = generate_outcome_id()

    outcome = FixOutcome(
        outcome_id=outcome_id,
        fix_signature=fix_signature,
        error_signature=error_signature[:200],
        surfaced_at=datetime.now().isoformat(),
        surfaced_commands=fix_commands,
    )

    _store_pending_outcome(outcome)

    return outcome_id


def track_command_after_fix(command: str, success: bool) -> Optional[str]:
    """
    Track a command executed after a fix was surfaced.

    Called after any Bash command to check if it relates to a pending fix.

    Args:
        command: The command that was executed
        success: Whether the command succeeded

    Returns:
        Resolution type if outcome was determined, None if still pending
    """
    pending = _get_pending_outcome()
    if not pending:
        return None

    # Record this command
    pending.next_commands.append(command)

    # Check if this command matches a suggested fix command
    if command_matches_fix(command, pending.surfaced_commands):
        pending.followed = True
        pending.followed_at = datetime.now().isoformat()
        pending.followed_command = command

        if success:
            pending.success = True
            pending.success_verified_at = datetime.now().isoformat()
            pending.resolved = True
            pending.resolution = "followed_success"

            # Feedback to codebase_knowledge
            _boost_fix_confidence(pending.fix_signature)

            # Record in session metrics
            try:
                from session_metrics import record_fix_followed
                record_fix_followed(success=True)
            except ImportError:
                pass

        else:
            pending.resolved = True
            pending.resolution = "followed_failure"

            # Decay confidence for failed fix
            _decay_fix_confidence(pending.fix_signature)

            # Record in session metrics
            try:
                from session_metrics import record_fix_followed
                record_fix_followed(success=False)
            except ImportError:
                pass

        # Save and clear
        _save_outcome(pending)
        _clear_pending_outcome()

        return pending.resolution

    # Check for ignore threshold
    if len(pending.next_commands) >= IGNORE_THRESHOLD:
        pending.resolved = True
        pending.resolution = "ignored"

        # Record in session metrics
        try:
            from session_metrics import record_fix_ignored
            record_fix_ignored()
        except ImportError:
            pass

        # Save and clear
        _save_outcome(pending)
        _clear_pending_outcome()

        return "ignored"

    return None  # Still pending


# =============================================================================
# CONFIDENCE FEEDBACK
# =============================================================================

def _boost_fix_confidence(sig_hash: str, amount: float = 0.1) -> bool:
    """
    Boost confidence when a fix is verified to work.

    Called when fix surfaced → user ran suggested command → command succeeded.
    """
    try:
        from codebase_knowledge import boost_fix_confidence
        return boost_fix_confidence(sig_hash, amount)
    except ImportError:
        # Fallback: direct update
        try:
            from codebase_knowledge import _load_knowledge, _save_knowledge

            knowledge = _load_knowledge()
            fix_data = knowledge["fixes"].get(sig_hash)

            if not fix_data:
                return False

            fix_data["confidence"] = min(0.95, fix_data.get("confidence", 0.5) + amount)
            fix_data["times_used"] = fix_data.get("times_used", 0) + 1
            fix_data["last_success"] = datetime.now().isoformat()
            fix_data["verified_successes"] = fix_data.get("verified_successes", 0) + 1

            knowledge["fixes"][sig_hash] = fix_data
            return _save_knowledge(knowledge)
        except Exception:
            return False
    except Exception:
        return False


def _decay_fix_confidence(sig_hash: str, amount: float = 0.15) -> bool:
    """
    Decay confidence when a fix fails to work.

    Called when fix surfaced → user ran suggested command → command FAILED.
    """
    try:
        from codebase_knowledge import decay_fix_confidence
        return decay_fix_confidence(sig_hash, amount)
    except ImportError:
        # Fallback: direct update
        try:
            from codebase_knowledge import _load_knowledge, _save_knowledge

            knowledge = _load_knowledge()
            fix_data = knowledge["fixes"].get(sig_hash)

            if not fix_data:
                return False

            fix_data["confidence"] = max(0.1, fix_data.get("confidence", 0.5) - amount)
            fix_data["failures"] = fix_data.get("failures", 0) + 1

            knowledge["fixes"][sig_hash] = fix_data
            return _save_knowledge(knowledge)
        except Exception:
            return False
    except Exception:
        return False


# =============================================================================
# OUTCOME ANALYSIS
# =============================================================================

@dataclass
class FixEffectiveness:
    """Aggregated fix effectiveness metrics."""
    total_surfaced: int = 0
    followed: int = 0
    followed_success: int = 0
    followed_failure: int = 0
    ignored: int = 0
    timeout: int = 0

    @property
    def follow_rate(self) -> float:
        """Rate at which surfaced fixes are followed."""
        if self.total_surfaced == 0:
            return 0.0
        return self.followed / self.total_surfaced

    @property
    def success_rate(self) -> float:
        """Rate at which followed fixes succeed."""
        if self.followed == 0:
            return 0.0
        return self.followed_success / self.followed

    @property
    def overall_effectiveness(self) -> float:
        """Overall rate: surfaced → followed → success."""
        if self.total_surfaced == 0:
            return 0.0
        return self.followed_success / self.total_surfaced

    def to_dict(self) -> dict:
        return {
            "total_surfaced": self.total_surfaced,
            "followed": self.followed,
            "followed_success": self.followed_success,
            "followed_failure": self.followed_failure,
            "ignored": self.ignored,
            "timeout": self.timeout,
            "follow_rate": round(self.follow_rate * 100, 1),
            "success_rate": round(self.success_rate * 100, 1),
            "overall_effectiveness": round(self.overall_effectiveness * 100, 1),
        }


def analyze_fix_outcomes(days: int = 7) -> FixEffectiveness:
    """
    Analyze fix outcomes to determine effectiveness.

    Args:
        days: Number of days to analyze

    Returns:
        FixEffectiveness with aggregated metrics
    """
    outcomes = load_outcomes(days)

    effectiveness = FixEffectiveness(total_surfaced=len(outcomes))

    for outcome in outcomes:
        if outcome.followed:
            effectiveness.followed += 1
            if outcome.success:
                effectiveness.followed_success += 1
            else:
                effectiveness.followed_failure += 1
        elif outcome.resolution == "ignored":
            effectiveness.ignored += 1
        elif outcome.resolution == "timeout":
            effectiveness.timeout += 1

    return effectiveness


# =============================================================================
# QUICK TEST
# =============================================================================

if __name__ == "__main__":
    print("Fix Outcomes - Self Test")
    print("=" * 40)

    # Test command matching
    print("\nCommand Matching Tests:")
    tests = [
        ("pip install requests", ["pip install requests"], True),
        ("pip3 install requests==2.28.0", ["pip install requests"], True),
        ("npm install express", ["npm i express"], True),
        ("git pull origin main", ["git pull"], True),
        ("pip install flask", ["pip install requests"], False),
        ("ls -la", ["pip install requests"], False),
    ]

    for actual, suggested, expected in tests:
        result = command_matches_fix(actual, suggested)
        status = "✓" if result == expected else "✗"
        print(f"  {status} '{actual}' matches {suggested}: {result}")

    # Test tracking flow
    print("\nTracking Flow Test:")

    # Simulate: error occurs, fix surfaced
    outcome_id = track_fix_surfaced(
        fix_signature="abc123",
        error_signature="ModuleNotFoundError: No module named 'requests'",
        fix_commands=["pip install requests"]
    )
    print(f"  1. Fix surfaced with ID: {outcome_id}")

    # Simulate: some unrelated commands
    result = track_command_after_fix("ls -la", True)
    print(f"  2. Unrelated command (ls): {result}")

    result = track_command_after_fix("cd /app", True)
    print(f"  3. Unrelated command (cd): {result}")

    # Simulate: user runs the suggested command
    result = track_command_after_fix("pip install requests", True)
    print(f"  4. Fix command (success): {result}")

    # Analyze outcomes
    print("\nOutcome Analysis:")
    effectiveness = analyze_fix_outcomes(days=1)
    print(f"  Total surfaced: {effectiveness.total_surfaced}")
    print(f"  Follow rate: {effectiveness.follow_rate*100:.0f}%")
    print(f"  Success rate: {effectiveness.success_rate*100:.0f}%")

    print("\nSelf-test complete.")
