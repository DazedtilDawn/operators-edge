#!/usr/bin/env python3
"""
Operator's Edge - Discovery Mode Configuration
Self-aware feature proposal system that mines archive and patterns
to discover what the system should become.

Discovery Mode activates alongside Scout Mode - while Scout finds
maintenance work (what's broken), Discovery finds innovation
opportunities (what's missing).
"""

from enum import Enum
from dataclasses import dataclass, field
from typing import List, Optional, Dict
from datetime import datetime


# =============================================================================
# DISCOVERY SOURCES
# =============================================================================

class DiscoverySource(Enum):
    """Where the discovery insight came from."""
    ARCHIVE_PAIN = "archive_pain"           # Pattern mined from archive.jsonl
    LESSON_REINFORCEMENT = "lesson_reinforcement"  # High-reinforcement lesson
    WORKFLOW_FRICTION = "workflow_friction"  # Repeated manual action pattern
    INTEGRATION_GAP = "integration_gap"      # Available but unused capability
    DOCUMENTATION_GAP = "documentation_gap"  # Promised but missing feature
    CONSISTENCY_GAP = "consistency_gap"      # Asymmetric patterns in codebase


class DiscoveryConfidence(Enum):
    """How confident we are in this discovery."""
    HIGH = "high"      # Strong evidence (10+ data points, clear pattern)
    MEDIUM = "medium"  # Moderate evidence (5-10 data points)
    LOW = "low"        # Weak evidence (suggestive but sparse)


class DiscoveryValue(Enum):
    """Estimated value if implemented."""
    HIGH = "high"      # Would significantly reduce friction
    MEDIUM = "medium"  # Would noticeably improve workflow
    LOW = "low"        # Nice to have


class DiscoveryEffort(Enum):
    """Estimated implementation effort."""
    LOW = "low"        # < 50 lines, single file
    MEDIUM = "medium"  # 50-200 lines, 2-3 files
    HIGH = "high"      # > 200 lines, architectural change


# =============================================================================
# DISCOVERY FINDING DATA STRUCTURE
# =============================================================================

@dataclass
class DiscoveryEvidence:
    """Evidence supporting a discovery finding."""
    source: DiscoverySource
    pattern: str                    # What pattern was detected
    frequency: int                  # How many times observed
    data_points: List[str] = field(default_factory=list)  # Specific examples
    time_range_days: int = 30       # How far back evidence goes


@dataclass
class DiscoveryFinding:
    """
    A self-discovered feature proposal.

    Unlike ScoutFinding (which finds maintenance work in code),
    DiscoveryFinding proposes new capabilities based on usage patterns.
    """
    id: str                         # Unique identifier
    title: str                      # Short proposal (becomes objective if approved)
    source: DiscoverySource         # Where this insight came from
    confidence: DiscoveryConfidence # How confident in the evidence
    value: DiscoveryValue           # Estimated impact
    effort: DiscoveryEffort         # Estimated implementation effort

    evidence: DiscoveryEvidence     # Supporting data

    sketch: str                     # Initial implementation thoughts
    affected_files: List[str] = field(default_factory=list)  # Files to modify

    created_at: str = field(default_factory=lambda: datetime.now().isoformat())

    def to_dict(self) -> dict:
        """Convert to JSON-serializable dict."""
        return {
            "id": self.id,
            "title": self.title,
            "source": self.source.value,
            "confidence": self.confidence.value,
            "value": self.value.value,
            "effort": self.effort.value,
            "evidence": {
                "source": self.evidence.source.value,
                "pattern": self.evidence.pattern,
                "frequency": self.evidence.frequency,
                "data_points": self.evidence.data_points[:5],  # Limit stored examples
                "time_range_days": self.evidence.time_range_days,
            },
            "sketch": self.sketch,
            "affected_files": self.affected_files,
            "created_at": self.created_at,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "DiscoveryFinding":
        """Create from dict."""
        evidence_data = data.get("evidence", {})
        evidence = DiscoveryEvidence(
            source=DiscoverySource(evidence_data.get("source", "archive_pain")),
            pattern=evidence_data.get("pattern", ""),
            frequency=evidence_data.get("frequency", 0),
            data_points=evidence_data.get("data_points", []),
            time_range_days=evidence_data.get("time_range_days", 30),
        )

        return cls(
            id=data["id"],
            title=data["title"],
            source=DiscoverySource(data["source"]),
            confidence=DiscoveryConfidence(data.get("confidence", "medium")),
            value=DiscoveryValue(data.get("value", "medium")),
            effort=DiscoveryEffort(data.get("effort", "medium")),
            evidence=evidence,
            sketch=data.get("sketch", ""),
            affected_files=data.get("affected_files", []),
            created_at=data.get("created_at", datetime.now().isoformat()),
        )


# =============================================================================
# SCORING AND PRIORITIZATION
# =============================================================================

# Value scores (higher = more important)
VALUE_SCORES = {
    DiscoveryValue.HIGH: 100,
    DiscoveryValue.MEDIUM: 60,
    DiscoveryValue.LOW: 30,
}

# Effort penalties (higher effort = lower priority)
EFFORT_PENALTIES = {
    DiscoveryEffort.LOW: 0,
    DiscoveryEffort.MEDIUM: -20,
    DiscoveryEffort.HIGH: -40,
}

# Confidence boosts
CONFIDENCE_BOOSTS = {
    DiscoveryConfidence.HIGH: 30,
    DiscoveryConfidence.MEDIUM: 10,
    DiscoveryConfidence.LOW: 0,
}


def score_discovery(finding: DiscoveryFinding) -> int:
    """
    Score a discovery finding for prioritization.

    Formula: value + confidence_boost + effort_penalty + frequency_bonus
    Higher score = more actionable opportunity.
    """
    base = VALUE_SCORES.get(finding.value, 50)
    confidence = CONFIDENCE_BOOSTS.get(finding.confidence, 0)
    effort = EFFORT_PENALTIES.get(finding.effort, 0)

    # Frequency bonus: more observations = more reliable
    frequency_bonus = min(finding.evidence.frequency * 2, 20)

    return base + confidence + effort + frequency_bonus


def sort_discoveries(findings: List[DiscoveryFinding]) -> List[DiscoveryFinding]:
    """Sort discovery findings by score, highest first."""
    return sorted(findings, key=score_discovery, reverse=True)


# =============================================================================
# PATTERN THRESHOLDS
# =============================================================================

DISCOVERY_THRESHOLDS = {
    # Minimum observations to surface a pattern
    "min_pain_frequency": 3,        # At least 3 mismatches of same type
    "min_lesson_reinforcement": 2,  # Lesson used 2+ times
    "min_workflow_repetition": 3,   # Same action sequence 3+ times

    # Time windows
    "archive_lookback_days": 90,    # How far back to mine archive
    "session_log_lookback": 30,     # Days of session logs to analyze

    # Output limits
    "max_discoveries": 5,           # Max discoveries to surface
    "display_discoveries": 3,       # How many to show in report
}


# =============================================================================
# ARCHIVE MINING PATTERNS
# =============================================================================

# Types of archive entries to analyze
ARCHIVE_ENTRY_TYPES = {
    "completed_objective": "objectives",
    "mismatch": "mismatches",
    "completed_step": "steps",
    "completed_research": "research",
    "decay": "lessons",
    "consolidation": "lessons",
}

# Mismatch categories that suggest feature opportunities
MISMATCH_CATEGORIES = {
    "git": ["git push", "git commit", "git reset", "branch"],
    "test": ["test", "assert", "coverage", "pytest", "unittest"],
    "import": ["import", "module", "dependency", "package"],
    "path": ["path", "file", "directory", "not found"],
    "permission": ["permission", "access", "denied", "blocked"],
    "timeout": ["timeout", "slow", "hang", "freeze"],
    "parse": ["parse", "syntax", "yaml", "json", "format"],
}


# =============================================================================
# DISPLAY FORMATTING
# =============================================================================

def format_discovery_for_display(finding: DiscoveryFinding, index: int) -> str:
    """Format a discovery finding for terminal display."""
    confidence_emoji = {
        DiscoveryConfidence.HIGH: "★",
        DiscoveryConfidence.MEDIUM: "◆",
        DiscoveryConfidence.LOW: "○",
    }

    value_label = {
        DiscoveryValue.HIGH: "High",
        DiscoveryValue.MEDIUM: "Med",
        DiscoveryValue.LOW: "Low",
    }

    effort_label = {
        DiscoveryEffort.LOW: "Low",
        DiscoveryEffort.MEDIUM: "Med",
        DiscoveryEffort.HIGH: "High",
    }

    emoji = confidence_emoji.get(finding.confidence, "?")

    lines = [
        f"  [{index + 1}] {emoji} {finding.title}",
        f"      Source: {finding.source.value.replace('_', ' ')}",
        f"      Evidence: {finding.evidence.pattern} ({finding.evidence.frequency}x)",
        f"      Value: {value_label[finding.value]} | Effort: {effort_label[finding.effort]}",
    ]

    if finding.sketch:
        # Show first line of sketch
        sketch_preview = finding.sketch.split('\n')[0][:60]
        lines.append(f"      Sketch: {sketch_preview}...")

    return '\n'.join(lines)


def discovery_to_objective(finding: DiscoveryFinding) -> str:
    """Convert a discovery finding to an objective string."""
    return finding.title


# =============================================================================
# DISCOVERY STATE
# =============================================================================

def get_default_discovery_state() -> dict:
    """Return default discovery state structure."""
    return {
        "last_scan": None,
        "findings": [],
        "dismissed": [],           # Discovery IDs user dismissed
        "implemented": [],         # Discovery IDs that became objectives
    }


def generate_discovery_id(source: DiscoverySource, title: str) -> str:
    """Generate a stable discovery ID."""
    import hashlib
    content = f"{source.value}:{title[:50]}"
    h = hashlib.sha1(content.encode()).hexdigest()[:12]
    return f"discovery-{h}"
