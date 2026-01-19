#!/usr/bin/env python3
"""
Operator's Edge v7.1 - Feedback Loop

DEPRECATED (v8.0): This module is superseded by context engineering.

The v7.1 feedback loop adjusted pattern confidence based on whether
suggestions were followed and outcomes were successful. However, this
is ML infrastructure without actual ML - confidence scores don't
meaningfully affect Claude's behavior since they're just prompt text.

v8.0 pivots to "Context Engineering" - keeping Claude on track through
supervision (drift detection, context compression) rather than training.

This module is preserved for backward compatibility but will not be
extended. See docs/v8-strategic-pivot.md for the rationale.

Original Purpose (Phase 4 of Learned Track Guidance):
- get_suggestion_for_objective() - Find suggestion shown for an objective
- compare_approach_to_suggestion() - Check if suggestion was followed
- update_pattern_confidence() - Adjust confidence based on outcome
- process_completion_feedback() - Main entry point for feedback processing
"""
import json
import os
import sys
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

# Add hooks directory to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


# =============================================================================
# DATA STRUCTURES
# =============================================================================

@dataclass
class FeedbackResult:
    """Result of processing feedback for an objective completion."""
    suggestion_found: bool
    pattern_id: Optional[str]
    pattern_source: Optional[str]  # "seed" | "learned"
    suggestion_followed: Optional[bool]
    follow_score: float  # 0.0-1.0 how closely suggestion was followed
    outcome_success: bool
    confidence_delta: float  # How much confidence changed
    new_confidence: Optional[float]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "suggestion_found": self.suggestion_found,
            "pattern_id": self.pattern_id,
            "pattern_source": self.pattern_source,
            "suggestion_followed": self.suggestion_followed,
            "follow_score": self.follow_score,
            "outcome_success": self.outcome_success,
            "confidence_delta": self.confidence_delta,
            "new_confidence": self.new_confidence
        }


# =============================================================================
# CONFIGURATION
# =============================================================================

def _get_feedback_settings() -> Dict[str, Any]:
    """Get feedback/confidence update settings."""
    try:
        import yaml
        config_file = Path(__file__).parent / "guidance_config.yaml"
        if config_file.exists():
            with open(config_file) as f:
                config = yaml.safe_load(f) or {}
            return config.get("confidence", {}).get("update", {})
    except Exception:
        pass

    # Defaults
    return {
        "followed_success_boost": 0.2,
        "followed_failure_penalty": 0.7,
        "ignored_success_penalty": 0.9,
        "ignored_failure_change": 1.0
    }


def _get_patterns_file() -> Path:
    """Get the path to the patterns store file."""
    return Path(__file__).parent / "patterns.yaml"


# =============================================================================
# SUGGESTION LOOKUP
# =============================================================================

def get_suggestion_for_objective(
    objective: str,
    lookback_entries: int = 50
) -> Optional[Dict[str, Any]]:
    """
    Find the most recent suggestion_shown entry for an objective.

    Args:
        objective: The objective text (or first 200 chars)
        lookback_entries: How many archive entries to search

    Returns:
        The suggestion_shown entry dict, or None if not found
    """
    from archive_utils import load_archive

    entries = load_archive(limit=lookback_entries)

    # Search from newest to oldest
    for entry in reversed(entries):
        if entry.get("type") != "suggestion_shown":
            continue

        # Match on objective (may be truncated)
        entry_obj = entry.get("objective", "")
        if not entry_obj:
            continue

        # Check if objectives match (accounting for truncation)
        if objective.startswith(entry_obj[:50]) or entry_obj.startswith(objective[:50]):
            return entry

    return None


def get_suggestions_for_session(
    session_id: str,
    lookback_entries: int = 200
) -> List[Dict[str, Any]]:
    """
    Find all suggestion_shown entries for a session.

    Useful for analyzing session-level patterns.
    """
    from archive_utils import load_archive

    entries = load_archive(limit=lookback_entries)
    suggestions = []

    for entry in entries:
        if entry.get("type") == "suggestion_shown":
            # Suggestions don't have session_id, but are temporally related
            suggestions.append(entry)

    return suggestions


# =============================================================================
# APPROACH COMPARISON
# =============================================================================

def compare_approach_to_suggestion(
    actual_verbs: List[str],
    suggested_verbs: List[str]
) -> Tuple[bool, float]:
    """
    Compare actual approach verbs to suggested approach verbs.

    Returns:
        (followed: bool, score: float 0.0-1.0)

    Following is determined by:
    - 70%+ verb overlap = followed
    - Score is exact overlap percentage
    """
    if not actual_verbs or not suggested_verbs:
        return False, 0.0

    actual_set = set(actual_verbs)
    suggested_set = set(suggested_verbs)

    # Set overlap
    overlap = len(actual_set & suggested_set)
    union = len(actual_set | suggested_set)

    if union == 0:
        return False, 0.0

    overlap_score = overlap / union

    # Sequence similarity bonus
    # If verbs appear in similar order, add a bonus
    sequence_bonus = _compute_sequence_similarity(actual_verbs, suggested_verbs)

    # Combined score: 70% overlap, 30% sequence
    score = (0.7 * overlap_score) + (0.3 * sequence_bonus)

    # Followed threshold: 50% combined score
    followed = score >= 0.5

    return followed, score


def _compute_sequence_similarity(seq1: List[str], seq2: List[str]) -> float:
    """Compute how similar two sequences are in order."""
    if not seq1 or not seq2:
        return 0.0

    # LCS-based similarity
    m, n = len(seq1), len(seq2)
    dp = [[0] * (n + 1) for _ in range(m + 1)]

    for i in range(1, m + 1):
        for j in range(1, n + 1):
            if seq1[i - 1] == seq2[j - 1]:
                dp[i][j] = dp[i - 1][j - 1] + 1
            else:
                dp[i][j] = max(dp[i - 1][j], dp[i][j - 1])

    lcs_len = dp[m][n]
    max_len = max(m, n)

    return lcs_len / max_len if max_len > 0 else 0.0


# =============================================================================
# CONFIDENCE UPDATES
# =============================================================================

def compute_confidence_update(
    current_confidence: float,
    followed: bool,
    success: bool,
    settings: Dict[str, Any] = None
) -> Tuple[float, float]:
    """
    Compute new confidence based on outcome.

    Formula:
    - Followed + Success: confidence + (1 - confidence) * boost
    - Followed + Failure: confidence * penalty
    - Ignored + Success: confidence * slight_penalty (we missed something)
    - Ignored + Failure: no change

    Returns:
        (new_confidence, delta)
    """
    if settings is None:
        settings = _get_feedback_settings()

    if followed:
        if success:
            # Boost: Asymptotic approach to 1.0
            boost = settings.get("followed_success_boost", 0.2)
            new_conf = current_confidence + (1 - current_confidence) * boost
            delta = new_conf - current_confidence
        else:
            # Penalty: Multiplicative reduction
            penalty = settings.get("followed_failure_penalty", 0.7)
            new_conf = current_confidence * penalty
            delta = new_conf - current_confidence
    else:
        if success:
            # Slight penalty: User found a better way
            penalty = settings.get("ignored_success_penalty", 0.9)
            new_conf = current_confidence * penalty
            delta = new_conf - current_confidence
        else:
            # No change: Both failed, no signal
            change = settings.get("ignored_failure_change", 1.0)
            new_conf = current_confidence * change
            delta = 0.0

    # Clamp to valid range
    new_conf = max(0.1, min(0.95, new_conf))

    return new_conf, delta


def update_pattern_confidence(
    pattern_id: str,
    pattern_source: str,
    new_confidence: float
) -> bool:
    """
    Update pattern confidence in the patterns store.

    For seed patterns: Updates are stored in patterns.yaml overrides
    For learned patterns: Updates the pattern directly

    Returns:
        True if update succeeded
    """
    patterns_file = _get_patterns_file()

    # Load existing patterns
    patterns = _load_patterns()

    if pattern_source == "seed":
        # Store seed pattern confidence overrides
        if "seed_overrides" not in patterns:
            patterns["seed_overrides"] = {}
        patterns["seed_overrides"][pattern_id] = {
            "confidence": new_confidence,
            "updated_at": datetime.now().isoformat()
        }
    else:
        # Update learned pattern directly
        if "learned" not in patterns:
            patterns["learned"] = {}
        if pattern_id not in patterns["learned"]:
            patterns["learned"][pattern_id] = {}
        patterns["learned"][pattern_id]["confidence"] = new_confidence
        patterns["learned"][pattern_id]["updated_at"] = datetime.now().isoformat()

    # Save patterns
    return _save_patterns(patterns)


def _load_patterns() -> Dict[str, Any]:
    """Load patterns from patterns.yaml."""
    patterns_file = _get_patterns_file()

    if not patterns_file.exists():
        return {"seed_overrides": {}, "learned": {}}

    try:
        import yaml
        with open(patterns_file) as f:
            return yaml.safe_load(f) or {"seed_overrides": {}, "learned": {}}
    except Exception:
        return {"seed_overrides": {}, "learned": {}}


def _save_patterns(patterns: Dict[str, Any]) -> bool:
    """Save patterns to patterns.yaml."""
    patterns_file = _get_patterns_file()

    try:
        import yaml
        with open(patterns_file, 'w') as f:
            yaml.dump(patterns, f, default_flow_style=False, sort_keys=False)
        return True
    except Exception:
        # Fallback to JSON if YAML fails
        try:
            json_file = patterns_file.with_suffix('.json')
            with open(json_file, 'w') as f:
                json.dump(patterns, f, indent=2)
            return True
        except Exception:
            return False


def get_pattern_confidence(pattern_id: str, pattern_source: str, default: float = 0.5) -> float:
    """
    Get the current confidence for a pattern.

    Checks for overrides in patterns.yaml first.
    """
    patterns = _load_patterns()

    if pattern_source == "seed":
        overrides = patterns.get("seed_overrides", {})
        if pattern_id in overrides:
            return overrides[pattern_id].get("confidence", default)
    else:
        learned = patterns.get("learned", {})
        if pattern_id in learned:
            return learned[pattern_id].get("confidence", default)

    return default


# =============================================================================
# MAIN FEEDBACK PROCESSING
# =============================================================================

def process_completion_feedback(
    objective: str,
    approach_verbs: List[str],
    success: bool,
    session_id: str = None
) -> FeedbackResult:
    """
    Process feedback for an objective completion.

    This is the main entry point called when an objective completes.

    Args:
        objective: The completed objective text
        approach_verbs: List of verbs from the completed steps
        success: Whether the objective succeeded
        session_id: Optional session ID for logging

    Returns:
        FeedbackResult with all feedback data
    """
    # Find the suggestion that was shown for this objective
    suggestion = get_suggestion_for_objective(objective)

    if not suggestion:
        # No suggestion was shown - nothing to update
        return FeedbackResult(
            suggestion_found=False,
            pattern_id=None,
            pattern_source=None,
            suggestion_followed=None,
            follow_score=0.0,
            outcome_success=success,
            confidence_delta=0.0,
            new_confidence=None
        )

    # Extract suggestion details
    pattern_id = suggestion.get("pattern_id")
    pattern_source = suggestion.get("pattern_source", "seed")
    suggested_verbs = suggestion.get("approach_verbs", [])
    original_confidence = suggestion.get("confidence", 0.5)

    # Compare approaches
    followed, follow_score = compare_approach_to_suggestion(
        approach_verbs, suggested_verbs
    )

    # Compute confidence update
    new_confidence, delta = compute_confidence_update(
        original_confidence, followed, success
    )

    # Update pattern confidence in store
    if pattern_id:
        update_pattern_confidence(pattern_id, pattern_source, new_confidence)

    # Log feedback to archive
    _log_feedback_to_archive(
        objective=objective,
        pattern_id=pattern_id,
        pattern_source=pattern_source,
        followed=followed,
        follow_score=follow_score,
        success=success,
        original_confidence=original_confidence,
        new_confidence=new_confidence,
        delta=delta,
        session_id=session_id
    )

    return FeedbackResult(
        suggestion_found=True,
        pattern_id=pattern_id,
        pattern_source=pattern_source,
        suggestion_followed=followed,
        follow_score=follow_score,
        outcome_success=success,
        confidence_delta=delta,
        new_confidence=new_confidence
    )


def _log_feedback_to_archive(
    objective: str,
    pattern_id: str,
    pattern_source: str,
    followed: bool,
    follow_score: float,
    success: bool,
    original_confidence: float,
    new_confidence: float,
    delta: float,
    session_id: str = None
):
    """Log feedback processing to archive for analysis."""
    try:
        from archive_utils import log_to_archive

        log_to_archive("pattern_feedback", {
            "objective": objective[:200],
            "pattern_id": pattern_id,
            "pattern_source": pattern_source,
            "suggestion_followed": followed,
            "follow_score": round(follow_score, 3),
            "outcome_success": success,
            "original_confidence": round(original_confidence, 3),
            "new_confidence": round(new_confidence, 3),
            "confidence_delta": round(delta, 3),
            "session_id": session_id
        })
    except Exception:
        pass  # Non-critical logging failure


# =============================================================================
# ANALYSIS FUNCTIONS
# =============================================================================

def get_pattern_stats(pattern_id: str = None) -> Dict[str, Any]:
    """
    Get statistics about pattern usage and effectiveness.

    Args:
        pattern_id: Specific pattern to analyze, or None for all

    Returns:
        Dict with stats (times_suggested, times_followed, success_rate, etc.)
    """
    from archive_utils import load_archive

    entries = load_archive(limit=500)

    # Collect feedback entries
    feedback_entries = [
        e for e in entries
        if e.get("type") == "pattern_feedback"
        and (pattern_id is None or e.get("pattern_id") == pattern_id)
    ]

    if not feedback_entries:
        return {
            "pattern_id": pattern_id,
            "times_used": 0,
            "times_followed": 0,
            "follow_rate": 0.0,
            "success_rate": 0.0,
            "followed_success_rate": 0.0,
            "ignored_success_rate": 0.0
        }

    times_used = len(feedback_entries)
    times_followed = sum(1 for e in feedback_entries if e.get("suggestion_followed"))
    times_success = sum(1 for e in feedback_entries if e.get("outcome_success"))

    followed_entries = [e for e in feedback_entries if e.get("suggestion_followed")]
    ignored_entries = [e for e in feedback_entries if not e.get("suggestion_followed")]

    followed_success = sum(1 for e in followed_entries if e.get("outcome_success"))
    ignored_success = sum(1 for e in ignored_entries if e.get("outcome_success"))

    return {
        "pattern_id": pattern_id,
        "times_used": times_used,
        "times_followed": times_followed,
        "follow_rate": times_followed / times_used if times_used > 0 else 0.0,
        "success_rate": times_success / times_used if times_used > 0 else 0.0,
        "followed_success_rate": followed_success / len(followed_entries) if followed_entries else 0.0,
        "ignored_success_rate": ignored_success / len(ignored_entries) if ignored_entries else 0.0,
        "current_confidence": get_pattern_confidence(pattern_id, "seed") if pattern_id else None
    }


def get_all_pattern_stats() -> List[Dict[str, Any]]:
    """Get stats for all patterns that have feedback data."""
    from archive_utils import load_archive

    entries = load_archive(limit=500)

    # Find all unique pattern IDs
    pattern_ids = set()
    for e in entries:
        if e.get("type") == "pattern_feedback":
            pid = e.get("pattern_id")
            if pid:
                pattern_ids.add(pid)

    # Get stats for each
    return [get_pattern_stats(pid) for pid in sorted(pattern_ids)]
