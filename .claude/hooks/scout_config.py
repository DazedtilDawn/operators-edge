#!/usr/bin/env python3
"""
Operator's Edge - Scout Mode Configuration
Finding types, priority scoring, and scan settings for autonomous exploration.

Scout Mode activates when Dispatch has no objective - it explores the codebase
and surfaces actionable findings that can become new objectives.
"""

from enum import Enum
from dataclasses import dataclass
from typing import List, Optional
from datetime import datetime

# =============================================================================
# FINDING TYPES
# =============================================================================

class FindingType(Enum):
    """Types of issues Scout Mode can discover."""
    TODO = "todo"                  # TODO/FIXME comments in code
    LARGE_FILE = "large_file"      # Files exceeding size threshold
    MISSING_TEST = "missing_test"  # Code without test coverage
    DEAD_CODE = "dead_code"        # Unused exports/functions
    OUTDATED_DEP = "outdated_dep"  # Outdated dependencies
    SECURITY = "security"          # Potential security issues
    COMPLEXITY = "complexity"      # High cyclomatic complexity
    DUPLICATION = "duplication"    # Code duplication detected
    LESSON_VIOLATION = "lesson_violation"  # Code violating a learned lesson (v3.6)
    UNVERIFIED_COMPLETION = "unverified_completion"  # Completed step with verification but no matching test (v3.9.2)


class FindingPriority(Enum):
    """Priority levels for findings."""
    HIGH = "high"      # Should address soon
    MEDIUM = "medium"  # Worth addressing
    LOW = "low"        # Nice to have


# =============================================================================
# FINDING DATA STRUCTURE
# =============================================================================

@dataclass
class ScoutFinding:
    """A single finding from Scout Mode scan."""
    type: FindingType
    priority: FindingPriority
    title: str                      # Short description (becomes objective if approved)
    description: str                # Detailed context
    location: str                   # File path and line number
    context: Optional[str] = None   # Surrounding code snippet
    suggested_action: Optional[str] = None  # What to do about it

    def to_dict(self) -> dict:
        """Convert to JSON-serializable dict."""
        return {
            "type": self.type.value,
            "priority": self.priority.value,
            "title": self.title,
            "description": self.description,
            "location": self.location,
            "context": self.context,
            "suggested_action": self.suggested_action
        }

    @classmethod
    def from_dict(cls, data: dict) -> "ScoutFinding":
        """Create from dict."""
        return cls(
            type=FindingType(data["type"]),
            priority=FindingPriority(data["priority"]),
            title=data["title"],
            description=data["description"],
            location=data["location"],
            context=data.get("context"),
            suggested_action=data.get("suggested_action")
        )


# =============================================================================
# SCAN PATTERNS
# =============================================================================

# Patterns to find TODOs and FIXMEs
TODO_PATTERNS = [
    r"#\s*TODO[:\s]",
    r"#\s*FIXME[:\s]",
    r"#\s*HACK[:\s]",
    r"#\s*XXX[:\s]",
    r"//\s*TODO[:\s]",
    r"//\s*FIXME[:\s]",
    r"\*\s*TODO[:\s]",
    r"\*\s*FIXME[:\s]",
]

# File extensions to scan
SCANNABLE_EXTENSIONS = [
    ".py", ".js", ".ts", ".tsx", ".jsx",
    ".go", ".rs", ".java", ".rb", ".php",
    ".c", ".cpp", ".h", ".hpp",
    ".sh", ".bash", ".zsh",
    ".yaml", ".yml", ".json", ".toml",
    ".md", ".txt",
]

# Directories to skip during scan
SKIP_DIRECTORIES = [
    "node_modules",
    ".git",
    "__pycache__",
    ".venv",
    "venv",
    ".env",
    "dist",
    "build",
    ".next",
    "coverage",
    ".pytest_cache",
    ".mypy_cache",
]

# =============================================================================
# THRESHOLDS
# =============================================================================

SCOUT_THRESHOLDS = {
    "large_file_lines": 500,        # Files with more lines are "large"
    "max_findings": 10,             # Max findings to store before pruning
    "display_findings": 3,          # How many to show at junction
    "scan_timeout_seconds": 120,    # Max time for full scan
    "max_files_to_scan": 200,       # Safety limit on file count
}

# =============================================================================
# PRIORITY SCORING
# =============================================================================

# Priority weights for sorting findings
PRIORITY_WEIGHTS = {
    FindingPriority.HIGH: 100,
    FindingPriority.MEDIUM: 50,
    FindingPriority.LOW: 10,
}

# Type-based priority adjustments
TYPE_PRIORITY_BOOST = {
    FindingType.SECURITY: FindingPriority.HIGH,
    FindingType.TODO: FindingPriority.MEDIUM,
    FindingType.LARGE_FILE: FindingPriority.LOW,
    FindingType.MISSING_TEST: FindingPriority.MEDIUM,
    FindingType.DEAD_CODE: FindingPriority.LOW,
    FindingType.OUTDATED_DEP: FindingPriority.MEDIUM,
    FindingType.COMPLEXITY: FindingPriority.MEDIUM,
    FindingType.DUPLICATION: FindingPriority.LOW,
    FindingType.LESSON_VIOLATION: FindingPriority.MEDIUM,  # v3.6: Lessons as audits
    FindingType.UNVERIFIED_COMPLETION: FindingPriority.MEDIUM,  # v3.9.2: Verification without test
}


def score_finding(finding: ScoutFinding) -> int:
    """
    Score a finding for sorting/prioritization.
    Higher score = more important.
    """
    base = PRIORITY_WEIGHTS.get(finding.priority, 10)

    # Boost for certain keywords
    boost = 0
    title_lower = finding.title.lower()
    if "security" in title_lower or "vulnerability" in title_lower:
        boost += 50
    if "fixme" in title_lower or "urgent" in title_lower:
        boost += 30
    if "todo" in title_lower:
        boost += 10

    return base + boost


def sort_findings(findings: List[ScoutFinding]) -> List[ScoutFinding]:
    """Sort findings by priority score, highest first."""
    return sorted(findings, key=score_finding, reverse=True)


# =============================================================================
# SCOUT STATE STRUCTURE
# =============================================================================

def get_default_scout_state() -> dict:
    """Return default scout state structure (embedded in dispatch_state)."""
    return {
        "last_scan": None,              # ISO timestamp of last scan
        "scan_duration_seconds": None,  # How long last scan took
        "files_scanned": 0,             # Number of files in last scan
        "findings": [],                 # List of finding dicts
        "dismissed": [],                # Finding titles user dismissed
        "explored_paths": [],           # Paths we've already explored (for continuity)
    }


# =============================================================================
# CONVERSION HELPERS
# =============================================================================

def finding_to_objective(finding: ScoutFinding) -> str:
    """
    Convert a scout finding to an objective string.
    This becomes the objective in active_context.yaml when approved.
    """
    return finding.title


# =============================================================================
# TASK COMPLEXITY CLASSIFICATION (v3.0)
# =============================================================================

class TaskComplexity(Enum):
    """Task complexity levels for autonomous decision-making."""
    SIMPLE = "simple"      # Auto-plan, 1-2 steps, no junction needed
    MEDIUM = "medium"      # May need guidance, junction at plan phase
    COMPLEX = "complex"    # Requires review, junction always


# Keywords indicating simple tasks (clear, bounded work)
SIMPLE_TASK_KEYWORDS = [
    "add comment",
    "add docstring",
    "fix typo",
    "rename",
    "create test",
    "add test",
    "missing test",
    "update import",
    "remove unused",
    "add type hint",
]

# Keywords indicating complex tasks (architectural, risky)
COMPLEX_TASK_KEYWORDS = [
    "refactor",
    "redesign",
    "migrate",
    "rewrite",
    "architecture",
    "security",
    "performance",
    "optimize",
    "large file",
    "split",
    "merge",
    "integration",
    "api change",
    "breaking change",
    "database",
    "schema",
]

# Finding types that are typically simple
SIMPLE_FINDING_TYPES = {
    FindingType.MISSING_TEST,      # Clear action: write a test
    FindingType.LESSON_VIOLATION,  # Clear action: apply the lesson (v3.6)
    FindingType.UNVERIFIED_COMPLETION,  # Clear action: write test matching verification (v3.9.2)
}

# Finding types that are typically complex
COMPLEX_FINDING_TYPES = {
    FindingType.LARGE_FILE,     # Refactoring decision needed
    FindingType.SECURITY,       # High-risk, needs review
    FindingType.COMPLEXITY,     # Architectural decision
    FindingType.DUPLICATION,    # Design decision needed
}


def classify_task_complexity(finding: ScoutFinding) -> "TaskComplexity":
    """
    Classify a finding's task complexity for autonomous decision-making.

    Simple tasks: Auto-plan without junction
    Medium tasks: Junction at plan creation
    Complex tasks: Junction always, may need research

    Returns TaskComplexity enum value.
    """
    title_lower = finding.title.lower()
    desc_lower = finding.description.lower()
    combined = f"{title_lower} {desc_lower}"

    # Check for complex keywords first (safety: if in doubt, junction)
    for keyword in COMPLEX_TASK_KEYWORDS:
        if keyword in combined:
            return TaskComplexity.COMPLEX

    # Check finding type
    if finding.type in COMPLEX_FINDING_TYPES:
        return TaskComplexity.COMPLEX

    if finding.type in SIMPLE_FINDING_TYPES:
        # Double-check: large files even for tests are complex
        if "large" in combined or finding.type == FindingType.LARGE_FILE:
            return TaskComplexity.COMPLEX
        return TaskComplexity.SIMPLE

    # Check for simple keywords
    for keyword in SIMPLE_TASK_KEYWORDS:
        if keyword in combined:
            return TaskComplexity.SIMPLE

    # For TODO type findings: check if actionable and bounded
    if finding.type == FindingType.TODO:
        # FIXMEs are usually more urgent/complex
        if "fixme" in title_lower:
            return TaskComplexity.MEDIUM
        # Short, clear TODOs are simple
        if len(finding.title) < 50 and finding.suggested_action:
            return TaskComplexity.SIMPLE
        return TaskComplexity.MEDIUM

    # Default: medium (junction at plan phase, but allow auto-select)
    return TaskComplexity.MEDIUM


def get_complexity_label(complexity: "TaskComplexity") -> str:
    """Get a human-readable label for complexity level."""
    labels = {
        TaskComplexity.SIMPLE: "🟢 Simple (auto-plan)",
        TaskComplexity.MEDIUM: "🟡 Medium (plan review)",
        TaskComplexity.COMPLEX: "🔴 Complex (full review)",
    }
    return labels.get(complexity, "Unknown")


def should_auto_plan(finding: ScoutFinding) -> bool:
    """
    Determine if a finding can be auto-planned without junction.

    Returns True if the task is simple enough for automatic planning.
    """
    complexity = classify_task_complexity(finding)
    return complexity == TaskComplexity.SIMPLE


def should_auto_select(findings: List[ScoutFinding]) -> bool:
    """
    Determine if we can auto-select the top finding without junction.

    Returns True if there are findings and the top one is actionable.
    In v3.0, auto-select is enabled by default - junction only for dangerous ops.
    """
    if not findings:
        return False

    # Always auto-select the highest priority finding
    # User can /edge stop or /edge skip if they disagree
    return True


def get_auto_plan_steps(finding: ScoutFinding) -> List[dict]:
    """
    Generate automatic plan steps for simple findings.

    Returns a list of plan step dicts ready for active_context.yaml.
    """
    complexity = classify_task_complexity(finding)

    if complexity != TaskComplexity.SIMPLE:
        return []  # Don't auto-plan non-simple tasks

    steps = []

    # Generate steps based on finding type
    if finding.type == FindingType.MISSING_TEST:
        steps = [
            {
                "description": f"Create test file for {finding.location.split('/')[-1]}",
                "status": "pending",
                "proof": None
            },
            {
                "description": "Run tests to verify coverage",
                "status": "pending",
                "proof": None
            }
        ]

    elif finding.type == FindingType.TODO:
        # Single step to address the TODO
        steps = [
            {
                "description": f"Address: {finding.title}",
                "status": "pending",
                "proof": None
            }
        ]

    elif finding.type == FindingType.UNVERIFIED_COMPLETION:
        # Write a test that verifies the completion criteria (v3.9.2)
        steps = [
            {
                "description": f"Write test matching verification: {finding.context or finding.title}",
                "status": "pending",
                "proof": None,
                "verification": finding.context  # Preserve the original verification
            },
            {
                "description": "Run tests to confirm verification passes",
                "status": "pending",
                "proof": None
            }
        ]

    else:
        # Generic single step
        steps = [
            {
                "description": finding.suggested_action or f"Address: {finding.title}",
                "status": "pending",
                "proof": None
            }
        ]

    return steps


# =============================================================================
# FINDING DISPLAY
# =============================================================================

def format_finding_for_display(finding: ScoutFinding, index: int, show_complexity: bool = True) -> str:
    """Format a finding for terminal display at junction."""
    priority_emoji = {
        FindingPriority.HIGH: "!",
        FindingPriority.MEDIUM: "~",
        FindingPriority.LOW: ".",
    }

    lines = [
        f"  [{index + 1}] {priority_emoji.get(finding.priority, '?')} {finding.title}",
        f"      Type: {finding.type.value} | Priority: {finding.priority.value}",
        f"      Location: {finding.location}",
    ]

    # Show complexity classification (v3.0)
    if show_complexity:
        complexity = classify_task_complexity(finding)
        lines.append(f"      Complexity: {get_complexity_label(complexity)}")

    if finding.context:
        # Truncate context to first line
        context_preview = finding.context.split('\n')[0][:60]
        lines.append(f"      Context: {context_preview}...")

    if finding.suggested_action:
        lines.append(f"      Action: {finding.suggested_action}")

    return '\n'.join(lines)
