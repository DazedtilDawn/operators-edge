#!/usr/bin/env python3
"""
Operator's Edge - Verification Utilities (Understanding-First v1.0)

Subagent verification support for reducing confirmation bias in work validation.

The key insight: verification run by the same context that did the work has
confirmation bias. A fresh subagent with only the spec and current state is
more objective - like code review by a different engineer.

v1.1 adds:
- Mechanical detection of verification tool usage (observation-based, not heuristic)
- Structured success criteria evaluation
- Auto-mismatch on verification failure
"""

import json
import os
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, List, Optional


# =============================================================================
# VERIFICATION OBSERVATION LOGGING (v1.1)
# =============================================================================

# Verification subagent types that count as independent verification
VERIFICATION_SUBAGENT_TYPES = frozenset({
    "edge-reviewer",
    "edge-test-runner",
})

# Other subagent types that count as "inline" (delegated but not verification-specific)
DELEGATED_SUBAGENT_TYPES = frozenset({
    "Explore",
    "Plan",
    "general-purpose",
})


def get_observations_path() -> Path:
    """Get path to the verification observations file (session-scoped)."""
    proof_dir = Path(".proof")
    proof_dir.mkdir(exist_ok=True)
    return proof_dir / "verification_observations.json"


def log_verification_observation(
    subagent_type: str,
    tool_input: Dict[str, Any],
    timestamp: Optional[str] = None
) -> Dict[str, Any]:
    """
    Log a verification tool observation (v1.1).

    Called by PostToolUse hook when Task tool is used.
    Records mechanical evidence of verification method.

    Args:
        subagent_type: The subagent_type from Task tool input
        tool_input: The full tool input dict
        timestamp: Optional timestamp (defaults to now)

    Returns:
        The observation dict that was logged
    """
    observation = {
        "type": "verification_tool_used",
        "subagent_type": subagent_type,
        "is_verification_subagent": subagent_type in VERIFICATION_SUBAGENT_TYPES,
        "is_delegated": subagent_type in DELEGATED_SUBAGENT_TYPES,
        "prompt_snippet": (tool_input.get("prompt", "")[:200] + "...") if tool_input.get("prompt") else None,
        "timestamp": timestamp or datetime.now().isoformat(),
    }

    # Append to observations file
    observations_path = get_observations_path()
    observations = load_verification_observations()
    observations.append(observation)

    try:
        with open(observations_path, "w") as f:
            json.dump(observations, f, indent=2)
    except Exception:
        pass  # Best effort - don't fail the tool

    return observation


def load_verification_observations() -> List[Dict[str, Any]]:
    """
    Load all verification observations from the current session.

    Returns:
        List of observation dicts
    """
    observations_path = get_observations_path()

    if not observations_path.exists():
        return []

    try:
        with open(observations_path, "r") as f:
            return json.load(f)
    except (json.JSONDecodeError, Exception):
        return []


def get_verification_method() -> str:
    """
    Determine verification method from observations (v1.1).

    Returns:
        "subagent": Task tool with edge-reviewer/edge-test-runner detected
        "inline": Task tool with other subagent type detected
        "self": No Task tool evidence (self-verified)
    """
    observations = load_verification_observations()

    if not observations:
        return "self"

    # Check for verification-specific subagent usage
    for obs in observations:
        if obs.get("is_verification_subagent"):
            return "subagent"

    # Check for any delegated work
    for obs in observations:
        if obs.get("is_delegated"):
            return "inline"

    return "self"


def clear_verification_observations() -> None:
    """Clear verification observations (call at session start or objective completion)."""
    observations_path = get_observations_path()
    if observations_path.exists():
        try:
            observations_path.unlink()
        except Exception:
            pass


@dataclass
class VerificationPolicy:
    """Policy for how verification steps should be executed."""
    mode: str = "subagent"  # subagent | inline | hybrid
    require_subagent: bool = False  # If True, blocks inline verification
    auto_suggest: bool = True  # If True, suggests subagent when appropriate


DEFAULT_POLICY = VerificationPolicy()


def get_verification_policy(state: Dict[str, Any]) -> VerificationPolicy:
    """
    Get verification policy from state.

    Args:
        state: The active_context state dict

    Returns:
        VerificationPolicy with settings from state or defaults
    """
    policy_dict = state.get("verification_policy", {})

    return VerificationPolicy(
        mode=policy_dict.get("mode", "subagent"),
        require_subagent=policy_dict.get("require_subagent", False),
        auto_suggest=policy_dict.get("auto_suggest", True),
    )


def should_use_subagent_verification(step: Dict[str, Any], state: Dict[str, Any]) -> bool:
    """
    Determine if a verification step should use a subagent.

    Args:
        step: The plan step to check
        state: The active_context state

    Returns:
        True if this step should use subagent verification
    """
    # Only applies to verification steps
    if not step.get("is_verification"):
        return False

    policy = get_verification_policy(state)

    # Policy-based decision
    if policy.mode == "subagent":
        return True
    elif policy.mode == "inline":
        return False
    elif policy.mode == "hybrid":
        # In hybrid mode, suggest subagent but don't require
        return policy.auto_suggest

    return False


def build_verification_prompt(state: Dict[str, Any], include_criteria_results: bool = True) -> str:
    """
    Build a prompt for the verification subagent.

    The prompt gives the subagent:
    - What the user wanted (intent.user_wants)
    - Success criteria (intent.success_looks_like)
    - Structured criteria results if available (v1.1)
    - Claimed proof from completed steps
    - NO context about HOW the work was done (reduces bias)

    Args:
        state: The active_context state
        include_criteria_results: If True and structured criteria exist, evaluate
            and include automated results (v1.1). Default True.

    Returns:
        Formatted prompt string for the verification subagent
    """
    intent = state.get("intent", {})
    plan = state.get("plan", [])
    objective = state.get("objective", "Not specified")

    # Get user's stated intent
    user_wants = intent.get("user_wants", "Not specified")
    success_looks_like = intent.get("success_looks_like", "Not specified")

    # v1.1: Evaluate structured criteria if available
    criteria_section = ""
    if include_criteria_results and intent.get("success_criteria"):
        # Import here to avoid circular dependency at module load
        criteria_results = evaluate_structured_criteria(state)
        if criteria_results:
            criteria_section = f"""

---

{format_criteria_results(criteria_results)}

**Note**: The above automated checks have been run for you. Focus on:
- Verifying the manual criteria
- Double-checking any failed automated criteria
- Confirming the overall intent was satisfied

"""

    # Get completed step proofs (excluding verification steps)
    completed = [
        s for s in plan
        if isinstance(s, dict)
        and s.get("status") == "completed"
        and not s.get("is_verification")
    ]

    proof_lines = []
    for i, step in enumerate(completed, 1):
        desc = step.get("description", "Step")
        proof = step.get("proof", "no proof provided")
        proof_lines.append(f"{i}. {desc}\n   Claimed proof: {proof}")

    proof_summary = "\n".join(proof_lines) if proof_lines else "No completed steps with proof"

    # Build the prompt
    prompt = f"""## Verification Task

You are an independent verifier. Your job is to verify that work was completed successfully.

**IMPORTANT**: You have NOT seen how this work was done. You only see the requirements and claimed results. This isolation is intentional - verify independently without bias.

---

### Objective
{objective}

### What the user wanted
{user_wants}

### Success criteria
{success_looks_like}
{criteria_section}
---

### Work completed (claimed)

{proof_summary}

---

### Your task

1. **Independently verify** that the success criteria are met
   - Run tests if applicable
   - Check files were created/modified as expected
   - Verify behavior matches requirements

2. **Do NOT trust the proof summaries** - they are claims, not facts
   - Actually run the tests
   - Actually check the files
   - Actually try the functionality

3. **Report your findings**:
   - PASS: If ALL success criteria are verifiably met
   - FAIL: If ANY criterion is not met (explain which and why)

4. **Be specific** in your findings
   - Include actual test output
   - Include actual file contents checked
   - Include actual behavior observed

---

### Output format

```
## Verification Result: [PASS/FAIL]

### Criteria Checked
1. [Criterion]: [PASS/FAIL] - [Evidence]
2. [Criterion]: [PASS/FAIL] - [Evidence]

### Summary
[Brief explanation of overall result]

### Issues Found (if FAIL)
- [Issue 1]
- [Issue 2]
```
"""

    return prompt


def build_verification_context(state: Dict[str, Any]) -> Dict[str, Any]:
    """
    Build context dict for verification subagent.

    This provides structured data that can be passed to the Task tool.

    Args:
        state: The active_context state

    Returns:
        Dict with verification context
    """
    intent = state.get("intent", {})
    plan = state.get("plan", [])

    # Get completed steps
    completed_steps = [
        {
            "description": s.get("description", ""),
            "proof": s.get("proof", ""),
        }
        for s in plan
        if isinstance(s, dict)
        and s.get("status") == "completed"
        and not s.get("is_verification")
    ]

    # Get files modified (from proof entries if available)
    # This would integrate with proof_utils in a full implementation
    modified_files = []  # Placeholder

    return {
        "objective": state.get("objective", ""),
        "intent": {
            "user_wants": intent.get("user_wants", ""),
            "success_looks_like": intent.get("success_looks_like", ""),
        },
        "completed_steps": completed_steps,
        "modified_files": modified_files,
        "verification_timestamp": datetime.now().isoformat(),
    }


def parse_verification_result(output: str) -> Dict[str, Any]:
    """
    Parse the output from a verification subagent.

    Args:
        output: The raw output from the verification subagent

    Returns:
        Dict with parsed result:
        - passed: bool
        - criteria: List of (name, passed, evidence)
        - summary: str
        - issues: List of str
        - raw_output: str
    """
    result = {
        "passed": False,
        "criteria": [],
        "summary": "",
        "issues": [],
        "raw_output": output,
    }

    # Simple parsing - look for PASS/FAIL in the result
    output_upper = output.upper()

    if "VERIFICATION RESULT: PASS" in output_upper or "## PASS" in output_upper:
        result["passed"] = True
    elif "VERIFICATION RESULT: FAIL" in output_upper or "## FAIL" in output_upper:
        result["passed"] = False
    else:
        # Ambiguous result - look for more clues
        pass_count = output_upper.count(": PASS")
        fail_count = output_upper.count(": FAIL")
        result["passed"] = pass_count > 0 and fail_count == 0

    # Extract issues (lines starting with "- " after "Issues Found")
    if "ISSUES FOUND" in output_upper:
        issues_section = output.split("Issues Found")[-1] if "Issues Found" in output else ""
        for line in issues_section.split("\n"):
            line = line.strip()
            if line.startswith("- "):
                result["issues"].append(line[2:])

    return result


def get_verification_step(state: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """
    Get the first verification step from the plan.

    Args:
        state: The active_context state

    Returns:
        The verification step dict, or None if no verification step exists
    """
    plan = state.get("plan", [])

    for step in plan:
        if isinstance(step, dict) and step.get("is_verification"):
            return step

    return None


def suggest_verification_approach(state: Dict[str, Any]) -> str:
    """
    Suggest how to approach verification based on current state.

    Args:
        state: The active_context state

    Returns:
        Suggestion string for the user
    """
    verification_step = get_verification_step(state)
    policy = get_verification_policy(state)

    if not verification_step:
        return (
            "No verification step found in plan. Add a step with is_verification: true "
            "that validates the success criteria."
        )

    if verification_step.get("status") == "completed":
        return "Verification step is already completed."

    if policy.mode == "subagent" or (policy.mode == "hybrid" and policy.auto_suggest):
        return (
            "Use the Task tool with subagent_type='edge-reviewer' to run verification "
            "with fresh context. This reduces confirmation bias.\n\n"
            "Example:\n"
            "Task(subagent_type='edge-reviewer', prompt=build_verification_prompt(state))"
        )

    return "Mark the verification step as in_progress and complete the verification checks."


# =============================================================================
# STRUCTURED SUCCESS CRITERIA (v1.1)
# =============================================================================

@dataclass
class CriterionResult:
    """Result of evaluating a single success criterion."""
    criterion_type: str
    description: str
    passed: Optional[bool]  # None for manual criteria (needs human)
    output: str
    error: Optional[str] = None


def evaluate_criterion(criterion: Dict[str, Any]) -> CriterionResult:
    """
    Evaluate a single success criterion (v1.1).

    Supports:
    - file_exists: Check if file exists
    - test_passes: Run command, check exit code 0
    - command_succeeds: Run command, check exit code 0
    - manual: Return None (requires human verification)

    Args:
        criterion: The criterion dict with type and params

    Returns:
        CriterionResult with evaluation outcome
    """
    import subprocess

    ctype = criterion.get("type", "unknown")

    if ctype == "file_exists":
        path = criterion.get("path", "")
        exists = Path(path).exists()
        return CriterionResult(
            criterion_type=ctype,
            description=f"File exists: {path}",
            passed=exists,
            output=f"{'Found' if exists else 'Not found'}: {path}",
        )

    elif ctype in ("test_passes", "command_succeeds"):
        command = criterion.get("command", "")
        if not command:
            return CriterionResult(
                criterion_type=ctype,
                description=f"Command: (empty)",
                passed=False,
                output="",
                error="No command specified",
            )

        try:
            result = subprocess.run(
                command,
                shell=True,
                capture_output=True,
                text=True,
                timeout=120,
            )
            passed = result.returncode == 0
            output = result.stdout[:1000] if result.stdout else result.stderr[:1000]
            return CriterionResult(
                criterion_type=ctype,
                description=f"Command: {command[:50]}",
                passed=passed,
                output=output,
                error=None if passed else f"Exit code: {result.returncode}",
            )
        except subprocess.TimeoutExpired:
            return CriterionResult(
                criterion_type=ctype,
                description=f"Command: {command[:50]}",
                passed=False,
                output="",
                error="Command timed out (120s)",
            )
        except Exception as e:
            return CriterionResult(
                criterion_type=ctype,
                description=f"Command: {command[:50]}",
                passed=False,
                output="",
                error=str(e),
            )

    elif ctype == "manual":
        description = criterion.get("description", "Manual verification required")
        return CriterionResult(
            criterion_type=ctype,
            description=description,
            passed=None,  # Requires human
            output="Requires human verification",
        )

    else:
        return CriterionResult(
            criterion_type=ctype,
            description=f"Unknown criterion type: {ctype}",
            passed=None,
            output="",
            error=f"Unknown criterion type: {ctype}",
        )


def evaluate_structured_criteria(state: Dict[str, Any]) -> List[CriterionResult]:
    """
    Evaluate all structured success criteria from intent (v1.1).

    Args:
        state: The active_context state

    Returns:
        List of CriterionResult for each criterion
    """
    intent = state.get("intent", {})
    criteria = intent.get("success_criteria", [])

    results = []
    for criterion in criteria:
        if isinstance(criterion, dict):
            result = evaluate_criterion(criterion)
            results.append(result)

    return results


def format_criteria_results(results: List[CriterionResult]) -> str:
    """
    Format criteria results for inclusion in verification prompt.

    Args:
        results: List of CriterionResult

    Returns:
        Formatted string for prompt
    """
    if not results:
        return "No structured criteria defined."

    lines = ["### Automated Criteria Results", ""]

    for i, r in enumerate(results, 1):
        status = "✓ PASS" if r.passed is True else "✗ FAIL" if r.passed is False else "? MANUAL"
        lines.append(f"{i}. [{status}] {r.description}")
        if r.output:
            lines.append(f"   Output: {r.output[:200]}")
        if r.error:
            lines.append(f"   Error: {r.error}")
        lines.append("")

    # Summary
    automated = [r for r in results if r.passed is not None]
    passed = sum(1 for r in automated if r.passed)
    failed = sum(1 for r in automated if not r.passed)
    manual = sum(1 for r in results if r.passed is None)

    lines.append(f"**Summary**: {passed} passed, {failed} failed, {manual} manual")

    return "\n".join(lines)


# =============================================================================
# VERIFICATION MISMATCH (v1.1)
# =============================================================================

def create_verification_mismatch(
    verification_result: Dict[str, Any],
    intent: Dict[str, Any],
    mismatch_id: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Create a mismatch linking verification failure to intent (v1.1).

    This auto-creates a mismatch when verification fails, forcing review
    before objective completion. The mismatch links back to the intent's
    success criteria, prompting the question: "Did we misunderstand the intent?"

    Args:
        verification_result: The parsed verification result (from parse_verification_result)
        intent: The intent dict from state
        mismatch_id: Optional ID (generates if not provided)

    Returns:
        Mismatch dict ready for appending to active_context.yaml:mismatches[]
    """
    from state_utils import generate_mismatch_id

    # Extract issues from verification result
    issues = verification_result.get("issues", [])
    issue_summary = issues[0] if issues else "Verification failed - criteria not met"

    return {
        "id": mismatch_id or generate_mismatch_id(),
        "timestamp": datetime.now().isoformat(),
        "expectation": intent.get("success_looks_like", "Intent criteria met"),
        "observation": issue_summary,
        "delta": "Verification failed - implementation may not match intent",
        "suspected_cause": "Implementation incomplete, or success criteria need clarification",
        "source": "verification_failure",
        "intent_link": True,  # Flag for special handling
        "confidence": 0.6,
        "resolved": False,
        "status": "unresolved",
    }


def should_create_verification_mismatch(verification_result: Dict[str, Any]) -> bool:
    """
    Determine if a verification mismatch should be created (v1.1).

    Args:
        verification_result: The parsed verification result

    Returns:
        True if verification failed and mismatch should be created
    """
    return not verification_result.get("passed", True)


def handle_verification_result(
    raw_output: str,
    state: Dict[str, Any],
    auto_create_mismatch: bool = True,
) -> Dict[str, Any]:
    """
    Process verification result and handle failure (v1.1).

    This is the main entry point for handling verification output.
    It parses the result, and if verification failed, auto-creates
    a mismatch linking back to intent.

    Args:
        raw_output: Raw output from verification subagent
        state: The active_context state
        auto_create_mismatch: If True (default), create mismatch on failure

    Returns:
        Dict with:
        - result: The parsed verification result
        - mismatch: The mismatch dict if created, None otherwise
        - mismatch_appended: True if mismatch was added to state file
    """
    # Parse the verification output
    result = parse_verification_result(raw_output)

    response = {
        "result": result,
        "mismatch": None,
        "mismatch_appended": False,
    }

    # If passed, no mismatch needed
    if result["passed"]:
        return response

    # Verification failed - create mismatch if enabled
    if auto_create_mismatch:
        intent = state.get("intent", {})
        mismatch = create_verification_mismatch(result, intent)
        response["mismatch"] = mismatch

        # Append to YAML file using eval_utils
        success = append_verification_mismatch(mismatch)
        response["mismatch_appended"] = success

    return response


def append_verification_mismatch(mismatch: Dict[str, Any]) -> bool:
    """
    Append a verification mismatch to active_context.yaml (v1.1).

    Helper function to add a mismatch to the mismatches array.
    Uses the same mechanism as eval_utils.append_mismatch_to_file.

    Args:
        mismatch: The mismatch dict to append

    Returns:
        True if successfully appended
    """
    try:
        from eval_utils import append_mismatch_to_file
        success, _ = append_mismatch_to_file(mismatch)
        return success
    except Exception:
        return False
