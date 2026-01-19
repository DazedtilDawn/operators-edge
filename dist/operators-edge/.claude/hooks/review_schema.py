#!/usr/bin/env python3
"""
Operator's Edge - Review Schema (v4.1)
Defines the structure for code review findings.

Reviews are stored in .proof/reviews/ as YAML files.
The schema is designed to be:
- Stable: Future tooling can depend on it
- Flexible: Free-text notes for nuanced issues
- Prioritized: Severity guides attention, doesn't gate
"""

from dataclasses import dataclass, field
from typing import Optional, List
from datetime import datetime
from enum import Enum


# =============================================================================
# SEVERITY LEVELS
# =============================================================================

class Severity(Enum):
    """Finding severity levels - guide attention, not gates."""
    CRITICAL = "critical"   # Must address before proceeding
    IMPORTANT = "important" # Should address in this session
    MINOR = "minor"         # Nice to have, style suggestions


# =============================================================================
# CATEGORY TYPES
# =============================================================================

class Category(Enum):
    """Finding categories for grouping and filtering."""
    SECURITY = "security"           # Security vulnerabilities
    BUG = "bug"                     # Logic errors, potential bugs
    PERFORMANCE = "performance"     # Performance issues
    STYLE = "style"                 # Code style, readability
    ARCHITECTURE = "architecture"   # Design concerns
    COMPATIBILITY = "compatibility" # Breaking changes, API issues
    TESTING = "testing"             # Missing tests, test quality
    DOCUMENTATION = "documentation" # Missing or outdated docs
    OTHER = "other"                 # Uncategorized


# =============================================================================
# FINDING SCHEMA
# =============================================================================

@dataclass
class Finding:
    """
    A single code review finding.

    Required fields:
        severity: How important is this finding
        category: What type of issue is this
        issue: Brief description of the problem

    Location fields (at least one recommended):
        file: Path to the file
        line: Line number (if applicable)
        function: Function name (if applicable)

    Action fields:
        suggestion: How to fix this
        notes: Free-text for nuanced explanation
        code_snippet: Relevant code (for context)
    """
    # Required
    severity: Severity
    category: Category
    issue: str

    # Location (optional but recommended)
    file: Optional[str] = None
    line: Optional[int] = None
    function: Optional[str] = None

    # Action
    suggestion: Optional[str] = None
    notes: Optional[str] = None
    code_snippet: Optional[str] = None

    def to_dict(self) -> dict:
        """Convert to dict for YAML serialization."""
        result = {
            "severity": self.severity.value,
            "category": self.category.value,
            "issue": self.issue,
        }

        # Location fields
        if self.file:
            result["file"] = self.file
        if self.line is not None:
            result["line"] = self.line
        if self.function:
            result["function"] = self.function

        # Action fields
        if self.suggestion:
            result["suggestion"] = self.suggestion
        if self.notes:
            result["notes"] = self.notes
        if self.code_snippet:
            result["code_snippet"] = self.code_snippet

        return result

    @classmethod
    def from_dict(cls, data: dict) -> "Finding":
        """Create from dict (YAML parsing result)."""
        return cls(
            severity=Severity(data.get("severity", "minor")),
            category=Category(data.get("category", "other")),
            issue=data.get("issue", "Unknown issue"),
            file=data.get("file"),
            line=data.get("line"),
            function=data.get("function"),
            suggestion=data.get("suggestion"),
            notes=data.get("notes"),
            code_snippet=data.get("code_snippet"),
        )

    def format_location(self) -> str:
        """Format location as human-readable string."""
        parts = []
        if self.file:
            parts.append(self.file)
            if self.line is not None:
                parts[-1] += f":{self.line}"
        if self.function:
            parts.append(f"in {self.function}()")
        return " ".join(parts) if parts else "unknown location"


# =============================================================================
# REVIEW SCHEMA
# =============================================================================

@dataclass
class Review:
    """
    A complete code review with metadata and findings.

    Metadata:
        timestamp: When the review was created
        trigger: What triggered this review (manual, step_complete, pre_commit)
        reviewer: Who/what did the review (self, codex, linter)

    Scope:
        files_changed: Number of files in the diff
        lines_changed: Lines added + removed
        step_intent: What the current step was trying to do
        constraints: Active constraints from plan

    Findings:
        findings: List of Finding objects
        summary: Counts by severity
    """
    # Metadata
    timestamp: str
    trigger: str = "manual"
    reviewer: str = "self"

    # Scope
    files_changed: int = 0
    lines_changed: int = 0
    step_intent: Optional[str] = None
    constraints: List[str] = field(default_factory=list)

    # Findings
    findings: List[Finding] = field(default_factory=list)

    def to_dict(self) -> dict:
        """Convert to dict for YAML serialization."""
        return {
            "review": {
                "timestamp": self.timestamp,
                "trigger": self.trigger,
                "reviewer": self.reviewer,
                "scope": {
                    "files_changed": self.files_changed,
                    "lines_changed": self.lines_changed,
                    "step_intent": self.step_intent,
                    "constraints": self.constraints,
                },
                "findings": [f.to_dict() for f in self.findings],
                "summary": self.get_summary(),
            }
        }

    @classmethod
    def from_dict(cls, data: dict) -> "Review":
        """Create from dict (YAML parsing result)."""
        review_data = data.get("review", data)
        scope = review_data.get("scope", {}) or {}

        findings = []
        findings_data = review_data.get("findings", []) or []
        for f in findings_data:
            if isinstance(f, dict):
                findings.append(Finding.from_dict(f))

        return cls(
            timestamp=review_data.get("timestamp", datetime.now().isoformat()),
            trigger=review_data.get("trigger", "manual"),
            reviewer=review_data.get("reviewer", "self"),
            files_changed=scope.get("files_changed", 0),
            lines_changed=scope.get("lines_changed", 0),
            step_intent=scope.get("step_intent"),
            constraints=scope.get("constraints", []),
            findings=findings,
        )

    def get_summary(self) -> dict:
        """Get counts by severity."""
        return {
            "critical": sum(1 for f in self.findings if f.severity == Severity.CRITICAL),
            "important": sum(1 for f in self.findings if f.severity == Severity.IMPORTANT),
            "minor": sum(1 for f in self.findings if f.severity == Severity.MINOR),
            "total": len(self.findings),
        }

    def has_critical(self) -> bool:
        """Check if any critical findings exist."""
        return any(f.severity == Severity.CRITICAL for f in self.findings)

    def add_finding(self, finding: Finding):
        """Add a finding to the review."""
        self.findings.append(finding)


# =============================================================================
# VALIDATION
# =============================================================================

def validate_finding(data: dict) -> tuple[bool, str]:
    """
    Validate a finding dict against the schema.

    Returns:
        (is_valid, error_message)
    """
    if not isinstance(data, dict):
        return False, "Finding must be a dict"

    # Check required fields
    required = ["severity", "category", "issue"]
    for field_name in required:
        if field_name not in data:
            return False, f"Missing required field: {field_name}"

    # Validate severity
    try:
        Severity(data["severity"])
    except ValueError:
        valid = [s.value for s in Severity]
        return False, f"Invalid severity: {data['severity']}. Must be one of: {valid}"

    # Validate category
    try:
        Category(data["category"])
    except ValueError:
        valid = [c.value for c in Category]
        return False, f"Invalid category: {data['category']}. Must be one of: {valid}"

    # Validate types
    if not isinstance(data["issue"], str) or not data["issue"].strip():
        return False, "issue must be a non-empty string"

    if "line" in data and data["line"] is not None:
        if not isinstance(data["line"], int) or data["line"] < 1:
            return False, "line must be a positive integer"

    return True, ""


def validate_review(data: dict) -> tuple[bool, str]:
    """
    Validate a review dict against the schema.

    Returns:
        (is_valid, error_message)
    """
    if not isinstance(data, dict):
        return False, "Review must be a dict"

    review_data = data.get("review", data)

    # Check timestamp
    if "timestamp" not in review_data:
        return False, "Missing required field: timestamp"

    # Validate findings
    for i, finding in enumerate(review_data.get("findings", [])):
        is_valid, error = validate_finding(finding)
        if not is_valid:
            return False, f"Finding {i}: {error}"

    return True, ""


# =============================================================================
# HELPERS
# =============================================================================

def create_finding(
    issue: str,
    severity: str = "minor",
    category: str = "other",
    file: str = None,
    line: int = None,
    suggestion: str = None,
    **kwargs
) -> Finding:
    """
    Helper to create a Finding with string inputs.

    Example:
        finding = create_finding(
            issue="SQL injection vulnerability",
            severity="critical",
            category="security",
            file="src/db.py",
            line=42,
            suggestion="Use parameterized queries"
        )
    """
    return Finding(
        severity=Severity(severity),
        category=Category(category),
        issue=issue,
        file=file,
        line=line,
        suggestion=suggestion,
        **kwargs
    )


def create_review(
    trigger: str = "manual",
    step_intent: str = None,
    constraints: List[str] = None,
) -> Review:
    """
    Helper to create a new Review with current timestamp.

    Example:
        review = create_review(
            trigger="step_complete",
            step_intent="Add authentication middleware",
            constraints=["No breaking changes to API"]
        )
    """
    return Review(
        timestamp=datetime.now().isoformat(),
        trigger=trigger,
        step_intent=step_intent,
        constraints=constraints or [],
    )


def get_reviews_dir():
    """Get the .proof/reviews directory, creating if needed."""
    from state_utils import get_proof_dir
    reviews_dir = get_proof_dir() / "reviews"
    reviews_dir.mkdir(parents=True, exist_ok=True)
    return reviews_dir


def save_review(review: Review, filename: str = None) -> str:
    """
    Save a review to .proof/reviews/ as JSON.

    Args:
        review: Review object to save
        filename: Optional filename (default: timestamp-based)

    Returns:
        Path to saved file
    """
    import json

    reviews_dir = get_reviews_dir()

    # Generate filename from timestamp if not provided
    if filename is None:
        # Convert ISO timestamp to filename-safe format
        ts = review.timestamp.replace(":", "-").replace(".", "-")
        filename = f"{ts}.json"

    filepath = reviews_dir / filename

    # Convert to JSON
    data = review.to_dict()
    json_content = json.dumps(data, indent=2)

    filepath.write_text(json_content)
    return str(filepath)


def load_review(filepath: str) -> Review:
    """
    Load a review from a JSON file.

    Args:
        filepath: Path to the review file

    Returns:
        Review object
    """
    import json
    from pathlib import Path

    content = Path(filepath).read_text()
    data = json.loads(content)
    return Review.from_dict(data)


def list_reviews(limit: int = 10) -> list:
    """
    List recent reviews.

    Args:
        limit: Max number of reviews to return

    Returns:
        List of (filepath, timestamp) tuples, most recent first
    """
    reviews_dir = get_reviews_dir()

    reviews = []
    for f in reviews_dir.glob("*.json"):
        # Extract timestamp from filename
        ts = f.stem.replace("-", ":").replace("T", " ")[:19]
        reviews.append((str(f), ts))

    # Sort by timestamp descending
    reviews.sort(key=lambda x: x[1], reverse=True)
    return reviews[:limit]


def format_review_summary(review: Review) -> str:
    """
    Format a review as a human-readable summary.

    Returns:
        Formatted string suitable for CLI output
    """
    summary = review.get_summary()
    lines = [
        "═" * 60,
        "REVIEW SUMMARY",
        "═" * 60,
        "",
        f"Trigger: {review.trigger}",
        f"Scope: {review.files_changed} files, {review.lines_changed} lines",
    ]

    if review.step_intent:
        lines.append(f"Intent: {review.step_intent}")

    lines.extend([
        "",
        f"Findings: {summary['total']}",
        f"  Critical: {summary['critical']}",
        f"  Important: {summary['important']}",
        f"  Minor: {summary['minor']}",
        "",
    ])

    if review.findings:
        lines.append("─" * 60)
        for i, f in enumerate(review.findings, 1):
            severity_icon = {
                Severity.CRITICAL: "!",
                Severity.IMPORTANT: "~",
                Severity.MINOR: ".",
            }[f.severity]

            lines.append(f"[{i}] {severity_icon} {f.issue}")
            lines.append(f"    Location: {f.format_location()}")
            if f.suggestion:
                lines.append(f"    Suggestion: {f.suggestion}")
            lines.append("")

    lines.append("═" * 60)
    return "\n".join(lines)
