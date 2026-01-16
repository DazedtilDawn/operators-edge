#!/usr/bin/env python3
"""
Operator's Edge - Quality Gate (v3.9.3)
Objective completion quality checks before ACTIVE→PATROL transition.

The Quality Gate ensures that work meets standards before being considered "done":
- All completed steps have proof
- No steps stuck in "in_progress"
- Verifications (if present) have matching tests
- No unresolved mismatches
"""

from dataclasses import dataclass, field
from typing import Dict, Any, List, Optional
from pathlib import Path


# =============================================================================
# QUALITY CHECK RESULT
# =============================================================================

@dataclass
class QualityCheck:
    """A single quality check result."""
    name: str
    passed: bool
    message: str
    severity: str = "error"  # error, warning
    details: Optional[List[str]] = None

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "passed": self.passed,
            "message": self.message,
            "severity": self.severity,
            "details": self.details,
        }


@dataclass
class QualityGateResult:
    """Result of running the quality gate."""
    passed: bool
    checks: List[QualityCheck] = field(default_factory=list)
    failed_checks: List[QualityCheck] = field(default_factory=list)
    warning_checks: List[QualityCheck] = field(default_factory=list)
    summary: str = ""

    def to_dict(self) -> dict:
        return {
            "passed": self.passed,
            "checks": [c.to_dict() for c in self.checks],
            "failed_checks": [c.to_dict() for c in self.failed_checks],
            "warning_checks": [c.to_dict() for c in self.warning_checks],
            "summary": self.summary,
        }


# =============================================================================
# QUALITY CHECKS
# =============================================================================

def check_steps_have_proof(state: Dict[str, Any]) -> QualityCheck:
    """
    Check that all completed steps have proof field populated.

    A completed step without proof is suspicious - how do we know it's done?
    """
    plan = state.get("plan", [])
    if not plan:
        return QualityCheck(
            name="steps_have_proof",
            passed=True,
            message="No plan steps to check",
        )

    missing_proof = []
    for i, step in enumerate(plan):
        if not isinstance(step, dict):
            continue
        if step.get("status") == "completed":
            proof = step.get("proof")
            if not proof or proof == "null" or str(proof).strip() == "":
                desc = step.get("description", f"Step {i+1}")[:40]
                missing_proof.append(f"Step {i+1}: {desc}")

    if missing_proof:
        return QualityCheck(
            name="steps_have_proof",
            passed=False,
            message=f"{len(missing_proof)} completed step(s) missing proof",
            severity="error",
            details=missing_proof,
        )

    completed_count = sum(1 for s in plan if isinstance(s, dict) and s.get("status") == "completed")
    return QualityCheck(
        name="steps_have_proof",
        passed=True,
        message=f"All {completed_count} completed steps have proof",
    )


def check_no_dangling_in_progress(state: Dict[str, Any]) -> QualityCheck:
    """
    Check that no steps are stuck in "in_progress" status.

    If objective is complete, no steps should be in_progress.
    """
    plan = state.get("plan", [])
    if not plan:
        return QualityCheck(
            name="no_dangling_in_progress",
            passed=True,
            message="No plan steps to check",
        )

    in_progress = []
    for i, step in enumerate(plan):
        if not isinstance(step, dict):
            continue
        if step.get("status") == "in_progress":
            desc = step.get("description", f"Step {i+1}")[:40]
            in_progress.append(f"Step {i+1}: {desc}")

    if in_progress:
        return QualityCheck(
            name="no_dangling_in_progress",
            passed=False,
            message=f"{len(in_progress)} step(s) still in_progress",
            severity="error",
            details=in_progress,
        )

    return QualityCheck(
        name="no_dangling_in_progress",
        passed=True,
        message="No dangling in_progress steps",
    )


def check_verifications_tested(
    state: Dict[str, Any],
    project_dir: Optional[Path] = None
) -> QualityCheck:
    """
    Check that completed steps with verification criteria have matching tests.

    Uses keyword matching to find if test files contain verification terms.
    """
    plan = state.get("plan", [])
    if not plan:
        return QualityCheck(
            name="verifications_tested",
            passed=True,
            message="No plan steps to check",
        )

    # Find completed steps with verification
    steps_with_verification = []
    for i, step in enumerate(plan):
        if not isinstance(step, dict):
            continue
        if step.get("status") == "completed" and step.get("verification"):
            steps_with_verification.append((i, step))

    if not steps_with_verification:
        return QualityCheck(
            name="verifications_tested",
            passed=True,
            message="No steps with verification criteria",
        )

    # Find test files
    if project_dir is None:
        project_dir = Path.cwd()

    test_files = list(project_dir.glob("**/*test*.py"))
    test_files.extend(project_dir.glob("**/test_*.py"))

    # Build test content corpus
    test_content = ""
    for tf in test_files:
        try:
            # Skip dist and cache directories
            if "dist" in str(tf) or "__pycache__" in str(tf) or ".pytest_cache" in str(tf):
                continue
            test_content += tf.read_text(encoding='utf-8', errors='ignore').lower()
        except Exception:
            pass

    # Check each verification
    unverified = []
    for i, step in steps_with_verification:
        verification = step.get("verification", "")
        keywords = _extract_keywords(verification.lower())

        if not keywords:
            continue

        # Check keyword coverage
        matches = sum(1 for kw in keywords if kw in test_content)
        match_ratio = matches / len(keywords)

        if match_ratio < 0.5:
            desc = step.get("description", f"Step {i+1}")[:40]
            unverified.append(f"Step {i+1}: {desc} (verification: {verification[:30]}...)")

    if unverified:
        return QualityCheck(
            name="verifications_tested",
            passed=False,
            message=f"{len(unverified)} step(s) have untested verification criteria",
            severity="warning",  # Warning, not error - verification is optional
            details=unverified,
        )

    return QualityCheck(
        name="verifications_tested",
        passed=True,
        message=f"All {len(steps_with_verification)} verification criteria appear tested",
    )


def check_eval_gate(state: Dict[str, Any]) -> QualityCheck:
    """
    Eval gate: warn or block if evals are enabled and failures exist.

    v3.9.8: Enforcement at level >= 1 when gate_on_fail is true.
    - Level 1: Warn by default, block if gate_on_fail=true
    - Level 2: Stricter checks with task bank support

    Blocking behavior:
    - passed=True: No failures or gate not active
    - passed=False + severity=warning: Failures exist but warn-only
    - passed=False + severity=error: Failures exist and gate_on_fail=true (blocks)
    """
    try:
        from edge_utils import get_evals_config, auto_triage, load_eval_runs
    except Exception:
        return QualityCheck(
            name="eval_gate",
            passed=True,
            message="Eval gate unavailable",
        )

    evals_config = get_evals_config(state)
    if not evals_config.get("enabled", True):
        return QualityCheck(name="eval_gate", passed=True, message="Evals disabled")

    if evals_config.get("mode") != "manual":
        evals_config, _triage = auto_triage(state, evals_config, None)

    level = evals_config.get("level", 0)
    gate_on_fail = evals_config.get("policy", {}).get("gate_on_fail", False)

    # Level 0: No gate active
    if level < 1:
        return QualityCheck(
            name="eval_gate",
            passed=True,
            message="Eval gate not active (level 0)",
        )

    # Level 1+: Check for failures
    runs = load_eval_runs(max_lines=500)
    if not runs:
        # No runs = no failures to check
        return QualityCheck(
            name="eval_gate",
            passed=True,
            message="No eval runs to check",
        )

    failed = [r for r in runs if r.get("invariants_failed")]
    if failed:
        # Determine severity based on gate_on_fail policy
        if gate_on_fail:
            # Blocking mode: error severity means passed=False blocks transition
            return QualityCheck(
                name="eval_gate",
                passed=False,
                severity="error",
                message=f"{len(failed)} eval run(s) with failed invariants - blocking transition",
            )
        else:
            # Warn-only mode: warn but don't block
            return QualityCheck(
                name="eval_gate",
                passed=False,
                severity="warning",
                message=f"{len(failed)} eval run(s) with failed invariants",
            )

    return QualityCheck(
        name="eval_gate",
        passed=True,
        message="Eval gate passed",
    )


def check_no_unresolved_mismatches(state: Dict[str, Any]) -> QualityCheck:
    """
    Check that there are no unresolved mismatches.

    Mismatches should be resolved (learned from) before objective is complete.
    v1.1: Special handling for intent-linked mismatches from verification failures.
    """
    mismatches = state.get("mismatches", [])

    if not mismatches:
        return QualityCheck(
            name="no_unresolved_mismatches",
            passed=True,
            message="No mismatches recorded",
        )

    unresolved = []
    intent_linked = []  # v1.1: Track intent-linked mismatches separately

    for i, mm in enumerate(mismatches):
        if not isinstance(mm, dict):
            continue
        if mm.get("status") != "resolved":
            expected = mm.get("expectation", mm.get("expected", "?"))[:30]

            # v1.1: Check for intent-linked mismatch
            if mm.get("intent_link"):
                intent_linked.append(f"Mismatch {i+1}: Intent criteria '{expected}...'")
            else:
                unresolved.append(f"Mismatch {i+1}: Expected '{expected}...'")

    if unresolved or intent_linked:
        # Build message with special handling for intent-linked mismatches
        details = unresolved + intent_linked
        total = len(unresolved) + len(intent_linked)

        # v1.1: Add guidance for intent-linked mismatches
        if intent_linked:
            details.append("")
            details.append("💡 Intent-linked mismatches suggest:")
            details.append("   1. Implementation may not fully match user intent")
            details.append("   2. Success criteria (success_looks_like) may need clarification")
            details.append("   3. Review and update intent before re-verifying")

        return QualityCheck(
            name="no_unresolved_mismatches",
            passed=False,
            message=f"{total} unresolved mismatch(es)" + (f" ({len(intent_linked)} intent-linked)" if intent_linked else ""),
            severity="error",
            details=details,
        )

    return QualityCheck(
        name="no_unresolved_mismatches",
        passed=True,
        message=f"All {len(mismatches)} mismatches resolved",
    )


def _extract_keywords(text: str) -> List[str]:
    """Extract meaningful keywords from text."""
    import re

    stop_words = {
        'a', 'an', 'the', 'is', 'are', 'was', 'were', 'be', 'been', 'being',
        'have', 'has', 'had', 'do', 'does', 'did', 'will', 'would', 'could',
        'should', 'may', 'might', 'must', 'shall', 'can', 'need', 'to', 'of',
        'in', 'for', 'on', 'with', 'at', 'by', 'from', 'as', 'into', 'through',
        'and', 'but', 'if', 'or', 'because', 'that', 'this', 'these', 'those',
        'returns', 'return', 'valid', 'invalid', 'correct', 'correctly',
        'should', 'must', 'works', 'work', 'test', 'tests', 'check', 'verify'
    }

    words = re.split(r'[^a-z0-9]+', text)
    return [w for w in words if w and len(w) > 2 and w not in stop_words]


def check_verification_step_exists(state: Dict[str, Any]) -> QualityCheck:
    """
    Check that at least one verification step exists and is completed (Understanding-First v1.0).

    A verification step has is_verification: true and validates that the intent's
    success criteria are met. This ensures work is independently verified before
    being considered done.

    Returns:
        QualityCheck with passed=False if:
        - No verification step exists in plan
        - Verification step exists but is not completed
    """
    plan = state.get("plan", [])
    intent = state.get("intent", {})

    # If no intent set, skip this check (backward compatibility)
    if not intent.get("user_wants"):
        return QualityCheck(
            name="verification_step_exists",
            passed=True,
            message="No intent set - verification step not required",
        )

    if not plan:
        return QualityCheck(
            name="verification_step_exists",
            passed=False,
            message="No plan steps - cannot verify objective completion",
            severity="error",
        )

    # Find verification steps (is_verification: true)
    verification_steps = [
        s for s in plan
        if isinstance(s, dict) and s.get("is_verification")
    ]

    if not verification_steps:
        return QualityCheck(
            name="verification_step_exists",
            passed=False,
            message="No verification step in plan",
            severity="error",
            details=[
                "Add a step with is_verification: true that validates success criteria",
                f"Success criteria: {intent.get('success_looks_like', 'not specified')[:60]}..."
            ]
        )

    # Check if any verification step is completed
    completed_verification = [
        s for s in verification_steps
        if s.get("status") == "completed"
    ]

    if not completed_verification:
        first_verification = verification_steps[0]
        status = first_verification.get("status", "pending")
        desc = first_verification.get("description", "verification step")[:50]
        return QualityCheck(
            name="verification_step_exists",
            passed=False,
            message=f"Verification step exists but not completed (status: {status})",
            severity="error",
            details=[f"Complete: {desc}"]
        )

    # Verification step exists and is completed
    return QualityCheck(
        name="verification_step_exists",
        passed=True,
        message=f"Verification step completed ({len(completed_verification)} of {len(verification_steps)})",
    )


# =============================================================================
# MAIN QUALITY GATE
# =============================================================================

def run_quality_gate(
    state: Dict[str, Any],
    project_dir: Optional[Path] = None
) -> QualityGateResult:
    """
    Run all quality checks for objective completion.

    Args:
        state: The active_context state
        project_dir: Project root for file scanning

    Returns:
        QualityGateResult with pass/fail and individual check results
    """
    checks = []

    # Run all checks
    checks.append(check_steps_have_proof(state))
    checks.append(check_no_dangling_in_progress(state))
    checks.append(check_verifications_tested(state, project_dir))
    checks.append(check_no_unresolved_mismatches(state))
    checks.append(check_eval_gate(state))
    checks.append(check_verification_step_exists(state))  # Understanding-First v1.0

    # Categorize results
    failed = [c for c in checks if not c.passed and c.severity == "error"]
    warnings = [c for c in checks if not c.passed and c.severity == "warning"]

    # Determine overall pass (errors block, warnings don't)
    passed = len(failed) == 0

    # Generate summary
    if passed and not warnings:
        summary = f"Quality gate PASSED - {len(checks)} checks OK"
    elif passed and warnings:
        summary = f"Quality gate PASSED with {len(warnings)} warning(s)"
    else:
        summary = f"Quality gate FAILED - {len(failed)} error(s), {len(warnings)} warning(s)"

    return QualityGateResult(
        passed=passed,
        checks=checks,
        failed_checks=failed,
        warning_checks=warnings,
        summary=summary,
    )


# =============================================================================
# DISPLAY HELPERS
# =============================================================================

def format_quality_gate_result(result: QualityGateResult) -> str:
    """Format quality gate result for display."""
    lines = [
        "─" * 60,
        "QUALITY GATE" if result.passed else "QUALITY GATE FAILED",
        "─" * 60,
    ]

    # Show all checks
    for check in result.checks:
        status = "✓" if check.passed else "✗" if check.severity == "error" else "⚠"
        lines.append(f"  {status} {check.name}: {check.message}")

        if check.details and not check.passed:
            for detail in check.details[:3]:  # Limit to 3 details
                lines.append(f"      - {detail}")
            if len(check.details) > 3:
                lines.append(f"      ... and {len(check.details) - 3} more")

    lines.append("")
    lines.append(result.summary)
    lines.append("─" * 60)

    return "\n".join(lines)


def format_quality_junction(result: QualityGateResult) -> str:
    """Format quality gate failure as a junction message."""
    lines = [
        "─" * 60,
        "JUNCTION: quality_gate",
        "─" * 60,
        "",
        "Objective completion blocked by quality gate.",
        "",
        "Failed checks:",
    ]

    for check in result.failed_checks:
        lines.append(f"  ✗ {check.name}: {check.message}")
        if check.details:
            for detail in check.details[:2]:
                lines.append(f"      - {detail}")

    if result.warning_checks:
        lines.append("")
        lines.append("Warnings:")
        for check in result.warning_checks:
            lines.append(f"  ⚠ {check.name}: {check.message}")

    lines.append("")
    lines.append("Options:")
    lines.append("  Fix the issues and try again")
    lines.append("  /edge approve  - Override and complete anyway")
    lines.append("─" * 60)

    return "\n".join(lines)
