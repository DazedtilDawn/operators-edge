#!/usr/bin/env python3
"""
Operator's Edge - Pre-Tool Gate
Unified enforcement before any tool execution.

Enforces:
1. Dangerous command blocking (rm -rf, git reset --hard, etc.)
2. Deploy/push confirmation gates
3. Retry blocking for repeated failures
4. Plan requirement for file edits
5. Graduated rules enforcement (v7.0 - proven lessons become rules)
6. File context surfacing (v7.0 - related files, risks)
7. Context window monitoring (v8.0 - context engineering)
8. Related files from codebase knowledge (v8.0 - co-change patterns)
9. Smart read suggestions (v8.0 Phase 10 - RLM-inspired)

v7.0 Paradigm Shift:
- LESSONS → became RULES (enforcement, not suggestion)
- PATTERNS → became CONTEXT (related files, not wisdom)
- RHYTHM → removed (low value)

v8.0 Context Engineering:
- Context monitor: Track context usage, surface compression recommendations
- Codebase knowledge: Surface files that usually change together
- Smart suggestions: Proactive guidance based on context (Phase 6)
- Active intervention: Escalating intervention based on session health (Phase 8)
- Smart read: Suggest targeted file reads for large files (Phase 10)
- This is supervision, not training

Note: YOLO/Dispatch mode is handled by the /edge-yolo command orchestration,
not by this hook. This hook only enforces safety constraints.
"""
import json
import os
import re
import sys
from pathlib import Path

# Add hooks directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from edge_utils import (
    load_yaml_state,
    get_recent_failures,
    respond,
    get_state_dir,
)


def check_bash_command(cmd):
    """
    Gate Bash commands by risk level.
    Returns: (decision, reason) or None to continue checking
    """
    cmd_norm = cmd.strip()

    # HARD BLOCK - Never allow these
    BLOCK_PATTERNS = [
        (r"(^|\s|&&|\|)rm\s+-rf\s+/", "Blocked: rm -rf on root"),
        (r"(^|\s|&&|\|)rm\s+-rf\s+~", "Blocked: rm -rf on home"),
        (r"(^|\s|&&|\|)rm\s+-rf\s+\.\.", "Blocked: rm -rf on parent"),
        (r"(^|\s|&&|\|)git\s+reset\s+--hard", "Blocked: git reset --hard"),
        (r"(^|\s|&&|\|)git\s+clean\s+-fdx", "Blocked: git clean -fdx"),
        (r"(^|\s|&&|\|)git\s+push\s+.*--force", "Blocked: force push"),
        (r"(^|\s|&&|\|)chmod\s+-R\s+777", "Blocked: chmod 777 recursive"),
        (r"(^|\s|&&|\|):()\s*{\s*:|:&\s*};:", "Blocked: fork bomb"),
        (r"(^|\s|&&|\|)mkfs\.", "Blocked: filesystem format"),
        (r"(^|\s|&&|\|)dd\s+if=.*/dev/", "Blocked: dd from device"),
    ]

    for pattern, reason in BLOCK_PATTERNS:
        if re.search(pattern, cmd_norm, re.IGNORECASE):
            return ("block", reason)

    # ASK CONFIRMATION - Risky but sometimes necessary
    ASK_PATTERNS = [
        (r"(^|\s|&&|\|)git\s+push(\s|$)", "Confirm: git push"),
        (r"(^|\s|&&|\|)rm\s+(-r\s+)?[^|&;]+", "Confirm: file deletion"),
        (r"(^|\s|&&|\|)kubectl\s+", "Confirm: kubernetes operation"),
        (r"(^|\s|&&|\|)terraform\s+", "Confirm: terraform operation"),
        (r"(^|\s|&&|\|)docker\s+push", "Confirm: docker push"),
        (r"(^|\s|&&|\|)npm\s+publish", "Confirm: npm publish"),
        (r"(^|\s|&&|\|)aws\s+", "Confirm: AWS operation"),
        (r"(^|\s|&&|\|)gcloud\s+", "Confirm: GCloud operation"),
    ]

    for pattern, reason in ASK_PATTERNS:
        if re.search(pattern, cmd_norm, re.IGNORECASE):
            return ("ask", f"{reason}: {cmd_norm[:80]}")

    return None

def check_retry_blocking(cmd):
    """
    Block commands that have failed recently without a new approach.
    """
    failures = get_recent_failures(cmd, window_minutes=15)
    if failures >= 2:
        return ("block",
                f"This command failed {failures} times recently. "
                "Explain your new approach before retrying.")
    return None

def check_plan_requirement(tool_name, tool_input):
    """
    Require a plan in active_context.yaml before allowing edits.
    v3.5: Also requires risks to be identified (failure mode planning).
    """
    if tool_name not in ("Edit", "Write", "NotebookEdit"):
        return None

    # Allow writes to specific safe paths without any checks
    file_path = tool_input.get("file_path", "")
    safe_paths = [
        "active_context.yaml",
        ".proof/",
        "checklist.md",
        "archive.md"
    ]
    if any(safe in file_path for safe in safe_paths):
        return None

    state = load_yaml_state()
    if state is None:
        return ("block",
                "Cannot edit files: active_context.yaml is missing or invalid. "
                "Run /edge-plan first.")

    plan = state.get("plan", [])
    if not plan:
        return ("ask",
                "No plan exists in active_context.yaml. "
                "Consider running /edge-plan first, or confirm to proceed without a plan.")

    # v3.5: Require risks to be identified
    risks = state.get("risks", [])
    if not risks:
        return ("ask",
                "No risks identified in active_context.yaml. "
                "What could go wrong? Add at least one risk before proceeding, "
                "or confirm to proceed without failure mode planning.")

    return None


def check_graduated_rules(tool_name, tool_input):
    """
    v7.0: Enforce graduated rules (proven lessons that became enforcement).

    Returns (action, message, rules_fired) if a blocking rule is violated.
    Returns (None, None, rules_fired) if only warnings.
    Returns (None, None, []) if no violations.
    Non-blocking violations print to stderr as warnings.
    """
    rules_fired = []

    try:
        from rules_engine import check_rules, format_violations, get_blocking_violation

        violations = check_rules(tool_name, tool_input)

        if not violations:
            return None, None, []

        # Track which rules fired
        rules_fired = [v.rule_id for v in violations]

        # Check for blocking violations
        blocking = get_blocking_violation(violations)
        if blocking:
            action, message = blocking.to_response()
            return action, message, rules_fired

        # Non-blocking: print warnings to stderr
        formatted = format_violations(violations)
        if formatted:
            print(f"\n{formatted}\n", file=sys.stderr)

        return None, None, rules_fired

    except ImportError:
        pass  # Rules engine not available
    except Exception:
        pass  # Don't fail the hook if rules check fails

    return None, None, rules_fired


def check_context_window():
    """
    v8.0: Check context window usage and surface warnings if high.

    This is context engineering - supervision to prevent context exhaustion.
    Surfaces warnings at 60%+, compression recommendations at 75%+.

    Returns intervention string to print (or empty string if none needed).
    """
    try:
        from context_monitor import (
            check_context_and_recommend,
            format_context_intervention
        )
        from proof_utils import get_session_log_path

        session_log = get_session_log_path()
        if not session_log or not session_log.exists():
            return ""

        state = load_yaml_state() or {}
        estimate, recommendation = check_context_and_recommend(session_log, state)

        # v8.0 Phase 5: Record context usage in metrics
        try:
            from session_metrics import record_context_usage
            record_context_usage(
                usage_percent=estimate.usage_percentage * 100,
                recommended_compression=recommendation.should_compress
            )
        except ImportError:
            pass

        # Only surface warnings and above
        if recommendation.severity in ("warning", "critical"):
            return format_context_intervention(recommendation, estimate)

    except ImportError:
        pass  # Context monitor not available
    except Exception:
        pass  # Don't fail the hook if context check fails

    return ""


def get_smart_suggestions(tool_name, tool_input, known_fix=None):
    """
    v8.0 Phase 6: Get smart suggestions for this tool call.

    Proactive guidance based on:
    - Auto-fix offers for known errors
    - Related file warnings
    - Checkpoint reminders
    - Drift prevention
    - Pattern nudges

    Returns formatted string to print (or empty string if none).
    """
    try:
        from smart_suggestions import get_suggestions_for_tool
        from proof_utils import get_session_log_path

        session_log = get_session_log_path()
        state = load_yaml_state() or {}

        return get_suggestions_for_tool(
            tool_name=tool_name,
            tool_input=tool_input,
            state=state,
            session_log=session_log,
            known_fix=known_fix
        )

    except ImportError:
        pass  # Smart suggestions not available
    except Exception:
        pass  # Don't fail the hook

    return ""


def surface_related_files_from_knowledge(tool_name, tool_input):
    """
    v8.0: Surface related files from codebase knowledge.

    This uses the co-change patterns learned from past sessions.
    If file A and file B have been modified together before,
    when editing A we remind Claude about B.

    Returns string to print (or empty if none).
    """
    if tool_name not in ("Edit", "Write", "NotebookEdit"):
        return ""

    file_path = tool_input.get("file_path", "")
    if not file_path:
        return ""

    # Skip internal paths
    safe_paths = ["active_context.yaml", ".proof/", "checklist.md", "archive.md"]
    if any(safe in file_path for safe in safe_paths):
        return ""

    try:
        from codebase_knowledge import get_related_files, format_related_files

        relations = get_related_files(file_path, min_strength=0.4)
        if relations:
            return format_related_files(relations)

    except ImportError:
        pass  # Codebase knowledge not available
    except Exception:
        pass  # Don't fail the hook

    return ""


def check_active_intervention(tool_name, tool_input):
    """
    v8.0 Phase 8: Check if active intervention system has guidance or blocks.

    The intervention level escalates based on session health:
    - observe: No intervention, just tracking
    - advise: Surface context, suggestions (default)
    - guide: Inject known fixes prominently, proactive warnings
    - intervene: Can block dangerous commands, strong guidance

    Returns (intervention_text, should_block) tuple.
    """
    try:
        from active_intervention import get_intervention_for_tool

        intervention_text, should_block = get_intervention_for_tool(
            tool_name=tool_name,
            tool_input=tool_input
        )

        return intervention_text, should_block

    except ImportError:
        pass  # Active intervention not available
    except Exception:
        pass  # Don't fail the hook

    return "", False


def check_smart_read(tool_name, tool_input):
    """
    v8.0 Phase 10: Smart read suggestions for large files.

    RLM-inspired: Instead of reading entire large files into context,
    suggest targeted approaches using REPL capabilities.

    Returns formatted suggestion string (or empty if not applicable).
    """
    if tool_name != "Read":
        return ""

    file_path = tool_input.get("file_path", "")
    if not file_path:
        return ""

    try:
        from smart_read import check_read_and_suggest

        # Get intervention level for formatting
        intervention_level = "advise"  # Default
        try:
            from active_intervention import get_current_level
            intervention_level = get_current_level()
        except ImportError:
            pass

        suggestion = check_read_and_suggest(file_path, intervention_level)
        return suggestion or ""

    except ImportError:
        pass  # Smart read not available
    except Exception:
        pass  # Don't fail the hook

    return ""


def surface_file_context(tool_name, tool_input):
    """
    v7.0: Surface file context at decision time.

    Shows CONTEXT (related files, risks) not WISDOM (lessons).
    Lessons are now handled by rules_engine.py as enforcement.

    Pattern types surfaced:
    - COCHANGE: Files that changed together in git history
    - RISK: Known risk patterns for this file/context

    Pattern types NOT surfaced (handled elsewhere or cut):
    - LESSON: Handled by rules_engine.py as enforcement
    - RHYTHM: Low value, removed

    Returns (context_string, context_list) where context_list is for tracking.
    """
    # Only surface for file modifications
    if tool_name not in ("Edit", "Write", "NotebookEdit"):
        return "", []

    file_path = tool_input.get("file_path", "")
    if not file_path:
        return "", []

    # Skip for safe/internal paths
    safe_paths = ["active_context.yaml", ".proof/", "checklist.md", "archive.md"]
    if any(safe in file_path for safe in safe_paths):
        return "", []

    # Load state for context extraction
    state = load_yaml_state()
    if not state:
        return "", []

    # Build context from file path and current objective/step
    context_parts = [file_path]
    if state.get("objective"):
        context_parts.append(state["objective"])

    plan = state.get("plan", [])
    for step in plan:
        if isinstance(step, dict) and step.get("status") == "in_progress":
            context_parts.append(step.get("description", ""))
            break

    context = " ".join(context_parts)
    context_shown = []

    try:
        from pattern_engine import surface_patterns, PatternType

        bundle = surface_patterns(
            state=state,
            context=context,
            intent_action="file_modify",
            max_patterns=5  # Get more, we'll filter
        )

        if not bundle.patterns:
            return "", []

        # v7.0: Filter to only CONTEXT patterns (not LESSON/RHYTHM)
        context_patterns = [
            p for p in bundle.patterns
            if p.type in (PatternType.COCHANGE, PatternType.RISK)
        ]

        if not context_patterns:
            return "", []

        # Format as context, not hints
        lines = ["📁 **File context:**"]
        for p in context_patterns[:3]:  # Max 3 context items
            if p.type == PatternType.COCHANGE:
                lines.append(f"  🔗 {p.content[:100]}")
                context_shown.append(f"cochange:{p.content[:50]}")
            elif p.type == PatternType.RISK:
                lines.append(f"  ⚠️ {p.content[:100]}")
                context_shown.append(f"risk:{p.content[:50]}")

        return "\n".join(lines), context_shown

    except ImportError:
        pass  # Pattern engine not available
    except Exception:
        pass  # Don't fail the hook if context fails

    return "", []

def main():
    try:
        data = json.load(sys.stdin)
    except json.JSONDecodeError:
        respond("approve", "Could not parse input, allowing by default")
        return

    tool_name = data.get("tool_name", "")
    tool_input = data.get("tool_input", {}) or {}

    # Check 1: Bash-specific risk gating
    if tool_name == "Bash":
        cmd = tool_input.get("command", "")

        # Check dangerous commands (hard block)
        result = check_bash_command(cmd)
        if result and result[0] == "block":
            respond(*result)

        # Check retry blocking
        retry_result = check_retry_blocking(cmd)
        if retry_result:
            respond(*retry_result)

        # If we had an "ask" from bash check (not hard block), apply it now
        if result and result[0] == "ask":
            respond(*result)

    # Check 2: Plan requirement for edits
    result = check_plan_requirement(tool_name, tool_input)
    if result:
        respond(*result)

    # Check 3: Graduated rules enforcement (v7.0)
    # Proven lessons become enforceable rules
    action, message, rules_fired = check_graduated_rules(tool_name, tool_input)

    # Check 4: Surface file context (v7.0)
    # Shows CONTEXT (related files, risks) not WISDOM (lessons)
    # Lessons are handled by rules (Check 3)
    file_context, context_shown = surface_file_context(tool_name, tool_input)
    if file_context:
        print(f"\n{file_context}\n", file=sys.stderr)

    # Check 5: Context window monitoring (v8.0)
    # Supervision to prevent context exhaustion
    context_warning = check_context_window()
    if context_warning:
        print(context_warning, file=sys.stderr)

    # Check 6: Related files from codebase knowledge (v8.0)
    # Surface files that have been modified together in past sessions
    related_files = surface_related_files_from_knowledge(tool_name, tool_input)
    if related_files:
        print(related_files, file=sys.stderr)

    # Check 7: Smart suggestions (v8.0 Phase 6)
    # Proactive guidance based on context, patterns, and known fixes
    smart_suggestions = get_smart_suggestions(tool_name, tool_input)
    if smart_suggestions:
        print(smart_suggestions, file=sys.stderr)

    # Check 8: Active intervention (v8.0 Phase 8)
    # Escalating intervention based on session health
    intervention_text, should_block = check_active_intervention(tool_name, tool_input)
    if intervention_text:
        print(intervention_text, file=sys.stderr)
    if should_block:
        respond("block", "Active intervention: Command blocked based on session health. See warning above.")

    # Check 9: Smart read suggestions (v8.0 Phase 10)
    # RLM-inspired: Suggest targeted file reads for large files
    smart_read_suggestion = check_smart_read(tool_name, tool_input)
    if smart_read_suggestion:
        print(smart_read_suggestion, file=sys.stderr)

    # v7.0: Log surface event for outcome tracking
    if rules_fired or context_shown:
        try:
            from outcome_tracker import generate_correlation_id, log_surface_event
            file_path = tool_input.get("file_path", "")
            corr_id = generate_correlation_id()
            log_surface_event(
                correlation_id=corr_id,
                file_path=file_path,
                rules_fired=rules_fired,
                context_shown=context_shown,
                tool_name=tool_name
            )
        except ImportError:
            pass  # Outcome tracker not available
        except Exception:
            pass  # Don't fail the hook if tracking fails

    # If rules had a blocking violation, respond now
    if action:
        respond(action, message)

    # All checks passed
    respond("approve", "Passed all pre-tool checks")

if __name__ == "__main__":
    main()
