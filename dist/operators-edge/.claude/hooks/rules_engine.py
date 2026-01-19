#!/usr/bin/env python3
"""
Operator's Edge v7.0 - Rules Engine
Graduated lessons become enforceable rules.

The Paradigm Shift:
- Before: Lessons surface as reminders (ignorable)
- After: Proven lessons become rules that block/warn (enforcement)

Graduation Criteria:
- reinforced >= 10 AND NOT evergreen → promote to rule
- Evergreen lessons stay as lessons (they should always surface)
- User can manually promote/demote via /edge rules
"""
import os
import re
import sys
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

# Add hooks directory to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


@dataclass
class Rule:
    """An enforceable rule graduated from a proven lesson."""
    id: str
    trigger_pattern: str  # Regex for file paths this applies to
    check_fn: str  # Name of check function to call
    message: str  # The original lesson text
    action: str = "warn"  # "warn" shows message, "block" requires confirmation
    source_lesson: Dict[str, Any] = field(default_factory=dict)
    enabled: bool = True
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "trigger_pattern": self.trigger_pattern,
            "check_fn": self.check_fn,
            "message": self.message,
            "action": self.action,
            "source_lesson": self.source_lesson,
            "enabled": self.enabled,
            "created_at": self.created_at,
        }


@dataclass
class RuleViolation:
    """Result of a rule check that found a violation."""
    rule_id: str
    rule_message: str
    action: str  # "warn" or "block"
    context: str  # Additional context about the violation

    def to_response(self) -> Tuple[str, str]:
        """Convert to pre_tool response format."""
        if self.action == "block":
            return ("ask", f"⚠️ Rule violation: {self.rule_message}\n\n{self.context}\n\nProceed anyway?")
        else:
            # Warn just returns the message but doesn't block
            return ("warn", f"📋 Rule: {self.rule_message}")


# =============================================================================
# GRADUATED RULES
# These are lessons that have been reinforced enough to become enforcement
# =============================================================================

GRADUATION_THRESHOLD = 10


def _is_policy_file(file_path: str) -> bool:
    """Check if file is a policy/documentation file."""
    policy_patterns = [
        r"CLAUDE\.md$",
        r"AGENTS\.md$",
        r"README\.md$",
        r"CONTRIBUTING\.md$",
        r"GUIDELINES\.md$",
    ]
    return any(re.search(p, file_path, re.IGNORECASE) for p in policy_patterns)


def _has_should_must_without_hook_ref(content: str) -> bool:
    """Check if content has 'should' or 'must' without mentioning hooks."""
    lines = content.lower().split('\n')
    for line in lines:
        # Skip lines that mention hooks, enforcement, or are code
        if 'hook' in line or 'enforce' in line or line.strip().startswith('#'):
            continue
        if 'should' in line or 'must' in line:
            return True
    return False


def check_policy_has_enforcement(tool_input: Dict[str, Any]) -> Optional[RuleViolation]:
    """
    Rule: Policy is not enforcement - hooks are enforcement.

    Triggers when editing policy files that add 'should'/'must' statements
    without referencing how they'll be enforced.
    """
    file_path = tool_input.get("file_path", "")

    if not _is_policy_file(file_path):
        return None

    # Get the new content being written
    new_content = tool_input.get("new_string", "") or tool_input.get("content", "")
    if not new_content:
        return None

    if _has_should_must_without_hook_ref(new_content):
        return RuleViolation(
            rule_id="policy-enforcement",
            rule_message="Policy is not enforcement - hooks are enforcement",
            action="warn",
            context="This content adds requirements ('should'/'must') without mentioning how they're enforced.\n"
                    "Consider: What hook or check makes this a rule, not just a suggestion?"
        )

    return None


def check_python_shebang(tool_input: Dict[str, Any]) -> Optional[RuleViolation]:
    """
    Rule: Use 'python3' not 'python' for cross-platform compatibility.

    Triggers when writing Python files with 'python' shebang.
    """
    file_path = tool_input.get("file_path", "")

    if not file_path.endswith(".py"):
        return None

    new_content = tool_input.get("new_string", "") or tool_input.get("content", "")
    if not new_content:
        return None

    # Check first line for shebang
    first_line = new_content.split('\n')[0] if new_content else ""

    # Bad: #!/usr/bin/env python or #!/usr/bin/python
    # Good: #!/usr/bin/env python3 or no shebang
    if re.match(r'^#!.*\bpython\b(?!3)', first_line):
        return RuleViolation(
            rule_id="python-shebang",
            rule_message="Use 'python3' not 'python' for cross-platform compatibility",
            action="warn",
            context=f"Found shebang: {first_line}\n"
                    "Windows uses 'python', Mac uses 'python3'. Use 'python3' for portability."
        )

    return None


def check_resolved_archived(tool_input: Dict[str, Any]) -> Optional[RuleViolation]:
    """
    Rule: Resolved = archived; only living context stays in active state.

    Triggers when adding resolved/completed items to active_context.yaml
    instead of archiving them.
    """
    file_path = tool_input.get("file_path", "")

    if "active_context.yaml" not in file_path:
        return None

    new_content = tool_input.get("new_string", "") or tool_input.get("content", "")
    if not new_content:
        return None

    # Check if adding resolved mismatches or completed items to active state
    # (This is a simplified check - could be more sophisticated)
    content_lower = new_content.lower()

    if 'status: "resolved"' in content_lower or 'status: resolved' in content_lower:
        if 'mismatches:' in content_lower:
            return RuleViolation(
                rule_id="resolved-archived",
                rule_message="Resolved = archived; only living context stays in active state",
                action="warn",
                context="Adding resolved mismatch to active_context.yaml.\n"
                        "Consider archiving resolved items to .proof/archive.jsonl instead."
            )

    return None


# =============================================================================
# RULE REGISTRY
# =============================================================================

# Map check function names to actual functions
CHECK_FUNCTIONS: Dict[str, Callable] = {
    "check_policy_has_enforcement": check_policy_has_enforcement,
    "check_python_shebang": check_python_shebang,
    "check_resolved_archived": check_resolved_archived,
}

# Default graduated rules (from proven lessons)
DEFAULT_RULES: List[Rule] = [
    Rule(
        id="policy-enforcement",
        trigger_pattern=r"\.(md|txt)$",
        check_fn="check_policy_has_enforcement",
        message="Policy is not enforcement - hooks are enforcement",
        action="warn",
        source_lesson={"trigger": "hooks", "reinforced": 32, "evergreen": True}
    ),
    Rule(
        id="python-shebang",
        trigger_pattern=r"\.py$",
        check_fn="check_python_shebang",
        message="Use 'python3' not 'python' for cross-platform compatibility",
        action="warn",
        source_lesson={"trigger": "python", "reinforced": 20}
    ),
    Rule(
        id="resolved-archived",
        trigger_pattern=r"active_context\.yaml$",
        check_fn="check_resolved_archived",
        message="Resolved = archived; only living context stays in active state",
        action="warn",
        source_lesson={"trigger": "archive", "reinforced": 14}
    ),
]


# =============================================================================
# RULE ENGINE
# =============================================================================

def load_rules(project_dir: Optional[Path] = None) -> List[Rule]:
    """
    Load rules from rules.yaml if it exists, otherwise use defaults.
    """
    # For now, just return default rules
    # TODO: Load from .claude/rules.yaml for user customization
    return [r for r in DEFAULT_RULES if r.enabled]


def check_rules(tool_name: str, tool_input: Dict[str, Any]) -> List[RuleViolation]:
    """
    Check all applicable rules for the given tool invocation.

    Returns list of violations (may be empty).
    """
    if tool_name not in ("Edit", "Write", "NotebookEdit"):
        return []

    file_path = tool_input.get("file_path", "")
    if not file_path:
        return []

    violations = []
    rules = load_rules()

    for rule in rules:
        # Check if rule applies to this file
        if not re.search(rule.trigger_pattern, file_path):
            continue

        # Get the check function
        check_fn = CHECK_FUNCTIONS.get(rule.check_fn)
        if not check_fn:
            continue

        # Run the check
        violation = check_fn(tool_input)
        if violation:
            violations.append(violation)

    return violations


def format_violations(violations: List[RuleViolation]) -> str:
    """Format violations for display."""
    if not violations:
        return ""

    lines = ["📋 **Rule checks:**"]
    for v in violations:
        icon = "⚠️" if v.action == "block" else "📝"
        lines.append(f"  {icon} {v.rule_message}")

    return "\n".join(lines)


def get_blocking_violation(violations: List[RuleViolation]) -> Optional[RuleViolation]:
    """Get the first blocking violation, if any."""
    for v in violations:
        if v.action == "block":
            return v
    return None


# =============================================================================
# LESSON GRADUATION
# =============================================================================

def should_graduate_lesson(lesson: Dict[str, Any]) -> bool:
    """
    Determine if a lesson should be promoted to a rule.

    Criteria:
    - reinforced >= GRADUATION_THRESHOLD
    - NOT marked as evergreen (evergreen lessons stay as lessons)
    """
    reinforced = lesson.get("reinforced", 0)
    evergreen = lesson.get("evergreen", False)

    # Evergreen lessons are wisdom that should always surface
    # They don't graduate because they're already "always on"
    if evergreen:
        return False

    return reinforced >= GRADUATION_THRESHOLD


def get_graduation_candidates(state: Dict[str, Any]) -> List[Dict[str, Any]]:
    """
    Get lessons that are candidates for graduation to rules.
    """
    memory = state.get("memory", [])
    candidates = []

    for lesson in memory:
        if not isinstance(lesson, dict):
            continue
        if should_graduate_lesson(lesson):
            candidates.append(lesson)

    return candidates


# =============================================================================
# TESTING
# =============================================================================

if __name__ == "__main__":
    print("=" * 60)
    print("   RULES ENGINE TEST")
    print("=" * 60)
    print()

    # Test policy enforcement rule
    test_input = {
        "file_path": "/project/CLAUDE.md",
        "new_string": "Users should always verify their input before submitting."
    }

    violations = check_rules("Write", test_input)
    print(f"Policy test: {len(violations)} violations")
    if violations:
        print(f"  → {violations[0].rule_message}")
    print()

    # Test Python shebang rule
    test_input = {
        "file_path": "/project/script.py",
        "new_string": "#!/usr/bin/env python\nprint('hello')"
    }

    violations = check_rules("Write", test_input)
    print(f"Shebang test: {len(violations)} violations")
    if violations:
        print(f"  → {violations[0].rule_message}")
    print()

    # Test resolved-archived rule
    test_input = {
        "file_path": "/project/.claude/active_context.yaml",
        "new_string": 'mismatches:\n  - status: "resolved"'
    }

    violations = check_rules("Write", test_input)
    print(f"Archive test: {len(violations)} violations")
    if violations:
        print(f"  → {violations[0].rule_message}")
    print()

    # Test no violation
    test_input = {
        "file_path": "/project/script.py",
        "new_string": "#!/usr/bin/env python3\nprint('hello')"
    }

    violations = check_rules("Write", test_input)
    print(f"Clean test: {len(violations)} violations (expected 0)")
    print()

    print("=" * 60)
    print("Rules engine ready.")
