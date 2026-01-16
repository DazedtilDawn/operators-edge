#!/usr/bin/env python3
"""
Operator's Edge v7.1 - Rules Engine
Graduated lessons become enforceable rules.

The Paradigm Shift:
- Before: Lessons surface as reminders (ignorable)
- After: Proven lessons become rules that block/warn (enforcement)

Graduation Criteria:
- reinforced >= 10 AND NOT evergreen → promote to rule
- Evergreen lessons stay as lessons (they should always surface)
- User can manually promote/demote via /edge-graduate

v7.1 adds:
- rules.yaml persistence (version-controlled, auditable)
- Shadow mode: new rules warn-only until proven effective
- Auto-promotion: 2 weeks or 10 fires with 80%+ effectiveness → enforce
- Auto-demotion: <50% effectiveness → demote back to lesson
"""
import os
import re
import sys
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

# Add hooks directory to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


# =============================================================================
# CONFIGURATION
# =============================================================================

GRADUATION_THRESHOLD = 10  # Minimum reinforcements to consider graduation
SHADOW_MODE_DURATION_DAYS = 14  # 2 weeks in shadow mode
SHADOW_MODE_MIN_FIRES = 10  # Minimum fires before auto-promotion
PROMOTION_EFFECTIVENESS_THRESHOLD = 0.8  # 80% to promote to enforce
DEMOTION_EFFECTIVENESS_THRESHOLD = 0.5  # <50% to demote back to lesson

# Using JSON instead of YAML for portability (no external dependencies)
RULES_FILE = Path(".claude/rules.json")


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

    # v7.1: Shadow mode tracking
    shadow_mode: bool = True  # New rules start in shadow mode (warn only)
    promoted_at: Optional[str] = None  # When rule was promoted from lesson
    fire_count: int = 0  # How many times this rule has fired in shadow mode

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
            "shadow_mode": self.shadow_mode,
            "promoted_at": self.promoted_at,
            "fire_count": self.fire_count,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Rule":
        """Create Rule from dictionary (for YAML loading)."""
        return cls(
            id=data.get("id", ""),
            trigger_pattern=data.get("trigger_pattern", ""),
            check_fn=data.get("check_fn", ""),
            message=data.get("message", ""),
            action=data.get("action", "warn"),
            source_lesson=data.get("source_lesson", {}),
            enabled=data.get("enabled", True),
            created_at=data.get("created_at", datetime.now().isoformat()),
            shadow_mode=data.get("shadow_mode", True),
            promoted_at=data.get("promoted_at"),
            fire_count=data.get("fire_count", 0),
        )

    def is_ready_for_promotion(self) -> bool:
        """Check if shadow mode period is complete."""
        if not self.shadow_mode:
            return False  # Already promoted

        # Need minimum fires
        if self.fire_count < SHADOW_MODE_MIN_FIRES:
            return False

        # Check time since promotion
        if self.promoted_at:
            try:
                promoted_time = datetime.fromisoformat(self.promoted_at)
                if datetime.now() - promoted_time >= timedelta(days=SHADOW_MODE_DURATION_DAYS):
                    return True
            except ValueError:
                pass

        return False


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

# Default graduated rules (from proven lessons - these are pre-established, not in shadow mode)
DEFAULT_RULES: List[Rule] = [
    Rule(
        id="policy-enforcement",
        trigger_pattern=r"\.(md|txt)$",
        check_fn="check_policy_has_enforcement",
        message="Policy is not enforcement - hooks are enforcement",
        action="warn",
        source_lesson={"trigger": "hooks", "reinforced": 32, "evergreen": True},
        shadow_mode=False,  # Pre-established rule
    ),
    Rule(
        id="python-shebang",
        trigger_pattern=r"\.py$",
        check_fn="check_python_shebang",
        message="Use 'python3' not 'python' for cross-platform compatibility",
        action="warn",
        source_lesson={"trigger": "python", "reinforced": 20},
        shadow_mode=False,  # Pre-established rule
    ),
    Rule(
        id="resolved-archived",
        trigger_pattern=r"active_context\.yaml$",
        check_fn="check_resolved_archived",
        message="Resolved = archived; only living context stays in active state",
        action="warn",
        source_lesson={"trigger": "archive", "reinforced": 14},
        shadow_mode=False,  # Pre-established rule
    ),
]


# =============================================================================
# RULES PERSISTENCE (v7.1) - Using JSON for portability
# =============================================================================

import json


def get_rules_file_path(project_dir: Optional[Path] = None) -> Path:
    """Get path to rules.json file."""
    if project_dir:
        return project_dir / RULES_FILE
    return RULES_FILE


def load_rules_from_file(project_dir: Optional[Path] = None) -> List[Rule]:
    """
    Load rules from rules.json file.
    Returns empty list if file doesn't exist.
    """
    rules_file = get_rules_file_path(project_dir)

    if not rules_file.exists():
        return []

    try:
        content = rules_file.read_text()
        data = json.loads(content)

        if not data or "rules" not in data:
            return []

        rules = []
        for rule_data in data.get("rules", []):
            if isinstance(rule_data, dict):
                rules.append(Rule.from_dict(rule_data))

        return rules
    except Exception:
        return []


def save_rules_to_file(rules: List[Rule], project_dir: Optional[Path] = None) -> bool:
    """
    Save rules to rules.json file.
    Returns True on success.
    """
    rules_file = get_rules_file_path(project_dir)

    try:
        # Ensure directory exists
        rules_file.parent.mkdir(parents=True, exist_ok=True)

        # Build data structure
        data = {
            "_comment": "Operator's Edge - Graduated Rules. Edit with care.",
            "version": "7.1",
            "updated_at": datetime.now().isoformat(),
            "rules": [r.to_dict() for r in rules],
        }

        content = json.dumps(data, indent=2)
        rules_file.write_text(content)
        return True
    except Exception:
        return False


def add_rule_to_file(rule: Rule, project_dir: Optional[Path] = None) -> bool:
    """Add a new rule to rules.json (used for graduation)."""
    existing = load_rules_from_file(project_dir)

    # Check for duplicate
    if any(r.id == rule.id for r in existing):
        return False  # Rule already exists

    existing.append(rule)
    return save_rules_to_file(existing, project_dir)


def update_rule_in_file(rule: Rule, project_dir: Optional[Path] = None) -> bool:
    """Update an existing rule in rules.json."""
    existing = load_rules_from_file(project_dir)

    for i, r in enumerate(existing):
        if r.id == rule.id:
            existing[i] = rule
            return save_rules_to_file(existing, project_dir)

    return False  # Rule not found


def remove_rule_from_file(rule_id: str, project_dir: Optional[Path] = None) -> bool:
    """Remove a rule from rules.json (used for demotion)."""
    existing = load_rules_from_file(project_dir)
    original_count = len(existing)

    existing = [r for r in existing if r.id != rule_id]

    if len(existing) == original_count:
        return False  # Rule not found

    return save_rules_to_file(existing, project_dir)


# Aliases for backward compatibility
load_rules_from_yaml = load_rules_from_file
save_rules_to_yaml = save_rules_to_file
add_rule_to_yaml = add_rule_to_file
update_rule_in_yaml = update_rule_in_file
remove_rule_from_yaml = remove_rule_from_file


# =============================================================================
# RULE ENGINE
# =============================================================================

def load_rules(project_dir: Optional[Path] = None) -> List[Rule]:
    """
    Load rules from rules.json + defaults.
    File rules take precedence over defaults with same ID.
    """
    # Load from file
    file_rules = load_rules_from_file(project_dir)
    file_rule_ids = {r.id for r in file_rules}

    # Add defaults that aren't overridden
    all_rules = list(file_rules)
    for default_rule in DEFAULT_RULES:
        if default_rule.id not in file_rule_ids:
            all_rules.append(default_rule)

    return [r for r in all_rules if r.enabled]


def check_lesson_pattern(tool_input: Dict[str, Any], rule: Rule) -> Optional[RuleViolation]:
    """
    Generic check function for graduated lessons.
    Unlike built-in rules, these don't have specific check logic -
    they fire whenever the file pattern matches and the lesson content is relevant.

    For now, this always returns a violation when the pattern matches.
    Future: Could add smarter content-based matching.
    """
    # For graduated lessons, we always fire when the pattern matches
    # The lesson text IS the warning
    return RuleViolation(
        rule_id=rule.id,
        rule_message=rule.message,
        action="warn" if rule.shadow_mode else rule.action,
        context=f"Graduated from lesson: {rule.source_lesson.get('trigger', 'unknown')}\n"
                f"Reinforced {rule.source_lesson.get('reinforced', 0)} times"
    )


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

        if check_fn:
            # Built-in rule with specific check logic
            violation = check_fn(tool_input)
        elif rule.check_fn == "check_lesson_pattern":
            # Graduated lesson - use generic checker
            violation = check_lesson_pattern(tool_input, rule)
        else:
            # Unknown check function, skip
            continue

        if violation:
            violations.append(violation)

            # v7.1: Track fires for shadow mode rules
            if rule.shadow_mode:
                increment_rule_fire_count(rule.id)

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
# LESSON GRADUATION (v7.1)
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


def get_graduation_candidates(state: Dict[str, Any], project_dir: Optional[Path] = None) -> List[Dict[str, Any]]:
    """
    Get lessons that are candidates for graduation to rules.
    Excludes lessons that are already rules.
    """
    memory = state.get("memory", [])
    existing_rules = load_rules(project_dir)
    existing_rule_messages = {r.message.lower() for r in existing_rules}

    candidates = []

    for lesson in memory:
        if not isinstance(lesson, dict):
            continue

        # Check if already a rule (by message match)
        lesson_text = lesson.get("lesson", "").lower()
        if lesson_text in existing_rule_messages:
            continue

        if should_graduate_lesson(lesson):
            candidates.append(lesson)

    return candidates


def generate_rule_id(lesson: Dict[str, Any]) -> str:
    """Generate a rule ID from a lesson."""
    trigger = lesson.get("trigger", "unknown")
    # Sanitize trigger to make a valid ID
    rule_id = re.sub(r'[^a-z0-9]+', '-', trigger.lower()).strip('-')
    return f"graduated-{rule_id}"


def generate_trigger_pattern(lesson: Dict[str, Any]) -> str:
    """
    Generate a trigger pattern for a rule based on lesson context.
    Returns a regex pattern for file matching.
    """
    trigger = lesson.get("trigger", "").lower()
    learned_patterns = lesson.get("learned_patterns", {})

    # Use learned pattern if available
    if learned_patterns and learned_patterns.get("inferred_pattern"):
        pattern = learned_patterns["inferred_pattern"]
        # Convert glob to regex
        pattern = pattern.replace("**/*", ".*")
        pattern = pattern.replace("*", "[^/]*")
        pattern = pattern.replace(".", r"\.")
        return pattern

    # Infer from trigger keywords
    if any(word in trigger for word in ["python", "py", "shebang"]):
        return r"\.py$"
    elif any(word in trigger for word in ["react", "jsx", "tsx", "component"]):
        return r"\.(jsx|tsx)$"
    elif any(word in trigger for word in ["css", "style", "theme"]):
        return r"\.(css|scss|less)$"
    elif any(word in trigger for word in ["test", "spec"]):
        return r"(test_.*|.*_test|.*\.spec)\.(py|js|ts)$"
    elif any(word in trigger for word in ["yaml", "config"]):
        return r"\.(ya?ml|json)$"
    elif any(word in trigger for word in ["markdown", "docs", "readme"]):
        return r"\.md$"

    # Default: match all files
    return r".*"


def graduate_lesson_to_rule(
    lesson: Dict[str, Any],
    project_dir: Optional[Path] = None
) -> Optional[Rule]:
    """
    Graduate a lesson to a rule in shadow mode.

    Returns the created Rule, or None if graduation failed.
    """
    rule_id = generate_rule_id(lesson)
    trigger_pattern = generate_trigger_pattern(lesson)

    # Create rule in shadow mode
    rule = Rule(
        id=rule_id,
        trigger_pattern=trigger_pattern,
        check_fn="check_lesson_pattern",  # Generic checker for graduated lessons
        message=lesson.get("lesson", ""),
        action="warn",  # Always start as warn
        source_lesson={
            "trigger": lesson.get("trigger", ""),
            "reinforced": lesson.get("reinforced", 0),
            "last_used": lesson.get("last_used", ""),
        },
        enabled=True,
        created_at=datetime.now().isoformat(),
        shadow_mode=True,  # Start in shadow mode
        promoted_at=datetime.now().isoformat(),
        fire_count=0,
    )

    # Save to rules.json
    if add_rule_to_file(rule, project_dir):
        return rule

    return None


def check_shadow_rules_for_promotion(project_dir: Optional[Path] = None) -> List[Dict[str, Any]]:
    """
    Check shadow mode rules and determine which should be promoted or demoted.

    Returns list of actions: [{"rule_id": ..., "action": "promote"|"demote", "reason": ...}]
    """
    try:
        from outcome_tracker import compute_rule_effectiveness
    except ImportError:
        return []

    rules = load_rules_from_yaml(project_dir)
    actions = []

    for rule in rules:
        if not rule.shadow_mode:
            continue  # Already promoted

        effectiveness = compute_rule_effectiveness(rule.id)

        if effectiveness is None:
            continue  # No data yet

        # Check if ready for promotion decision
        if rule.is_ready_for_promotion():
            if effectiveness >= PROMOTION_EFFECTIVENESS_THRESHOLD:
                actions.append({
                    "rule_id": rule.id,
                    "action": "promote",
                    "reason": f"Effectiveness {effectiveness:.0%} >= {PROMOTION_EFFECTIVENESS_THRESHOLD:.0%} threshold",
                    "effectiveness": effectiveness,
                    "fire_count": rule.fire_count,
                })
            elif effectiveness < DEMOTION_EFFECTIVENESS_THRESHOLD:
                actions.append({
                    "rule_id": rule.id,
                    "action": "demote",
                    "reason": f"Effectiveness {effectiveness:.0%} < {DEMOTION_EFFECTIVENESS_THRESHOLD:.0%} threshold",
                    "effectiveness": effectiveness,
                    "fire_count": rule.fire_count,
                })

    return actions


def promote_rule(rule_id: str, project_dir: Optional[Path] = None) -> bool:
    """
    Promote a rule from shadow mode to enforce mode.
    """
    rules = load_rules_from_yaml(project_dir)

    for rule in rules:
        if rule.id == rule_id:
            rule.shadow_mode = False
            rule.action = "warn"  # Could upgrade to "block" for critical rules
            return save_rules_to_yaml(rules, project_dir)

    return False


def demote_rule(rule_id: str, project_dir: Optional[Path] = None) -> bool:
    """
    Demote a rule back to a lesson (remove from rules.yaml).
    The lesson remains in memory - it just won't be enforced.
    """
    return remove_rule_from_yaml(rule_id, project_dir)


def increment_rule_fire_count(rule_id: str, project_dir: Optional[Path] = None) -> bool:
    """Increment the fire count for a shadow mode rule."""
    rules = load_rules_from_yaml(project_dir)

    for rule in rules:
        if rule.id == rule_id and rule.shadow_mode:
            rule.fire_count += 1
            return save_rules_to_yaml(rules, project_dir)

    return False


def format_graduation_candidates(candidates: List[Dict[str, Any]]) -> str:
    """Format graduation candidates for display."""
    if not candidates:
        return "No lessons ready for graduation."

    lines = ["### 🎓 Graduation Candidates", ""]
    lines.append("These lessons have been reinforced enough to become rules:")
    lines.append("")

    for i, lesson in enumerate(candidates, 1):
        trigger = lesson.get("trigger", "unknown")
        text = lesson.get("lesson", "")[:60]
        reinforced = lesson.get("reinforced", 0)
        lines.append(f"{i}. **[{trigger}]** - {text}...")
        lines.append(f"   Reinforced: {reinforced} times")
        lines.append("")

    lines.append("Run `/edge-graduate approve <number>` to graduate a lesson.")
    return "\n".join(lines)


def format_shadow_rules_status(project_dir: Optional[Path] = None) -> str:
    """Format shadow mode rules status for display."""
    rules = load_rules_from_yaml(project_dir)
    shadow_rules = [r for r in rules if r.shadow_mode]

    if not shadow_rules:
        return "No rules in shadow mode."

    try:
        from outcome_tracker import compute_rule_effectiveness
    except ImportError:
        compute_rule_effectiveness = lambda x: None

    lines = ["### 🌙 Shadow Mode Rules", ""]

    for rule in shadow_rules:
        effectiveness = compute_rule_effectiveness(rule.id)
        eff_str = f"{effectiveness:.0%}" if effectiveness is not None else "N/A"

        status = "🔄 Collecting data"
        if rule.is_ready_for_promotion():
            if effectiveness and effectiveness >= PROMOTION_EFFECTIVENESS_THRESHOLD:
                status = "✅ Ready for promotion"
            elif effectiveness and effectiveness < DEMOTION_EFFECTIVENESS_THRESHOLD:
                status = "⚠️ May be demoted"

        lines.append(f"- **{rule.id}**: {rule.message[:50]}...")
        lines.append(f"  Fires: {rule.fire_count}, Effectiveness: {eff_str}, Status: {status}")
        lines.append("")

    return "\n".join(lines)


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
