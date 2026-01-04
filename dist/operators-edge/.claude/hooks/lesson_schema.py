#!/usr/bin/env python3
"""
Operator's Edge - Lesson Schema (v3.6)
Defines the structure of lesson/memory items with optional audit fields.

Lessons are stored in active_context.yaml under the 'memory' key.
All fields except trigger and lesson are optional.
"""

from dataclasses import dataclass, field
from typing import Optional, List
from datetime import datetime


# =============================================================================
# LESSON SCHEMA
# =============================================================================

@dataclass
class Lesson:
    """
    A lesson/memory item with optional audit capabilities.

    Core fields (required):
        trigger: Keywords that activate this lesson
        lesson: The wisdom/pattern to apply

    Reinforcement fields (auto-managed):
        reinforced: How many times this lesson was useful
        last_used: Last date this lesson was applied
        applies_to: Contexts where this lesson applies
        source: Session or source that created this lesson

    Audit fields (v3.6, optional):
        audit_pattern: Regex pattern to find violations in code
        audit_scope: File globs to limit scan scope (e.g., ["*.py"])
        last_audit: When this lesson was last audited
        violations_found: Count from last audit
    """
    # Core fields
    trigger: str
    lesson: str

    # Reinforcement fields
    reinforced: int = 1
    last_used: Optional[str] = None
    applies_to: List[str] = field(default_factory=list)
    source: Optional[str] = None

    # Audit fields (v3.6)
    audit_pattern: Optional[str] = None
    audit_scope: List[str] = field(default_factory=list)
    last_audit: Optional[str] = None
    violations_found: int = 0

    def to_dict(self) -> dict:
        """Convert to dict for YAML serialization."""
        result = {
            "trigger": self.trigger,
            "lesson": self.lesson,
            "reinforced": self.reinforced,
        }

        # Only include optional fields if they have values
        if self.last_used:
            result["last_used"] = self.last_used
        if self.applies_to:
            result["applies_to"] = self.applies_to
        if self.source:
            result["source"] = self.source

        # Audit fields (only if audit_pattern is set)
        if self.audit_pattern:
            result["audit_pattern"] = self.audit_pattern
            if self.audit_scope:
                result["audit_scope"] = self.audit_scope
            if self.last_audit:
                result["last_audit"] = self.last_audit
            if self.violations_found > 0:
                result["violations_found"] = self.violations_found

        return result

    @classmethod
    def from_dict(cls, data: dict) -> "Lesson":
        """Create from dict (YAML parsing result)."""
        if isinstance(data, str):
            # Handle legacy string format
            return cls(trigger="*", lesson=data)

        return cls(
            trigger=data.get("trigger", "*"),
            lesson=data.get("lesson", str(data)),
            reinforced=data.get("reinforced", 1),
            last_used=data.get("last_used"),
            applies_to=data.get("applies_to", []),
            source=data.get("source"),
            audit_pattern=data.get("audit_pattern"),
            audit_scope=data.get("audit_scope", []),
            last_audit=data.get("last_audit"),
            violations_found=data.get("violations_found", 0),
        )

    def has_audit_capability(self) -> bool:
        """Check if this lesson can perform audits."""
        return bool(self.audit_pattern)

    def needs_audit(self, days_threshold: int = 7) -> bool:
        """Check if this lesson is due for an audit."""
        if not self.has_audit_capability():
            return False

        if not self.last_audit:
            return True

        try:
            last = datetime.fromisoformat(self.last_audit)
            days_since = (datetime.now() - last).days
            return days_since >= days_threshold
        except (ValueError, TypeError):
            return True


# =============================================================================
# SCHEMA VALIDATION
# =============================================================================

def validate_lesson(data: dict) -> tuple[bool, str]:
    """
    Validate a lesson dict against the schema.

    Returns:
        (is_valid, error_message)
    """
    if not isinstance(data, dict):
        if isinstance(data, str):
            return True, ""  # Legacy string format is valid
        return False, "Lesson must be a dict or string"

    # Check required fields
    if "trigger" not in data and "lesson" not in data:
        return False, "Lesson must have 'trigger' or 'lesson' field"

    # Validate types
    if "trigger" in data and not isinstance(data["trigger"], str):
        return False, "trigger must be a string"

    if "lesson" in data and not isinstance(data["lesson"], str):
        return False, "lesson must be a string"

    if "reinforced" in data and not isinstance(data["reinforced"], int):
        return False, "reinforced must be an integer"

    if "audit_pattern" in data and data["audit_pattern"]:
        if not isinstance(data["audit_pattern"], str):
            return False, "audit_pattern must be a string (regex)"
        # Try compiling the regex
        import re
        try:
            re.compile(data["audit_pattern"])
        except re.error as e:
            return False, f"audit_pattern is invalid regex: {e}"

    if "audit_scope" in data:
        if not isinstance(data["audit_scope"], list):
            return False, "audit_scope must be a list of file globs"

    return True, ""


def normalize_lesson(data) -> dict:
    """
    Normalize a lesson to the current schema format.
    Handles legacy formats and missing fields.
    """
    if isinstance(data, str):
        return {
            "trigger": "*",
            "lesson": data,
            "reinforced": 1,
        }

    if not isinstance(data, dict):
        return {
            "trigger": "*",
            "lesson": str(data),
            "reinforced": 1,
        }

    # Ensure required fields
    result = {
        "trigger": data.get("trigger", "*"),
        "lesson": data.get("lesson", str(data)),
        "reinforced": data.get("reinforced", 1),
    }

    # Copy optional fields if present
    for key in ["last_used", "applies_to", "source",
                "audit_pattern", "audit_scope", "last_audit", "violations_found"]:
        if key in data and data[key] is not None:
            result[key] = data[key]

    return result
