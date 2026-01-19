#!/usr/bin/env python3
"""
Operator's Edge - Patrol Gear (v3.7, v7.1 graduation)
Scans for issues after objective completion - the "vigilance" mode.

Patrol Gear is engaged after an objective completes. It:
- Runs a quick scout scan for new issues
- Checks lesson violations (v3.6 integration)
- Surfaces findings that could become new objectives
- v7.1: Checks graduation candidates and shadow rule promotion
"""

from typing import Dict, Any, Optional, List, Tuple
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from gear_config import Gear, GearState, GearTransition, PATROL_LIMITS


# =============================================================================
# PATROL RESULT
# =============================================================================

@dataclass
class PatrolGearResult:
    """Result of running Patrol Gear."""
    scan_completed: bool
    findings_count: int
    findings: List[Dict[str, Any]]  # Top findings to surface
    lesson_violations: int
    scan_duration_seconds: float
    recommended_action: Optional[str]  # e.g., "Select finding [1]"
    error: Optional[str]

    # v7.1: Graduation scanning
    graduation_candidates: List[Dict[str, Any]] = field(default_factory=list)
    shadow_rule_actions: List[Dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "scan_completed": self.scan_completed,
            "findings_count": self.findings_count,
            "findings": self.findings,
            "lesson_violations": self.lesson_violations,
            "scan_duration_seconds": self.scan_duration_seconds,
            "recommended_action": self.recommended_action,
            "error": self.error,
            "graduation_candidates": self.graduation_candidates,
            "shadow_rule_actions": self.shadow_rule_actions,
        }


# =============================================================================
# PATROL SCANNING
# =============================================================================

def run_patrol_scan(
    state: Dict[str, Any],
    project_dir: Optional[Path] = None
) -> PatrolGearResult:
    """
    Run Patrol Gear - quick scan for issues.

    This is a lightweight scan focused on:
    1. Lesson violations (from v3.6)
    2. TODO/FIXME comments
    3. Recently introduced issues

    Args:
        state: The active_context state
        project_dir: Project root (defaults to cwd)

    Returns:
        PatrolGearResult with scan summary
    """
    import time
    start_time = time.time()

    try:
        # Import scout scanner
        from scout_scanner import run_scout_scan
        from scout_config import FindingType

        # Run scout scan with state (for lesson violations)
        findings, meta = run_scout_scan(project_dir, state)

        # Filter to actionable findings (skip test fixtures)
        actionable = _filter_actionable_findings(findings)

        # Limit findings per patrol config
        max_findings = PATROL_LIMITS["max_findings_to_surface"]
        surfaced = actionable[:max_findings]

        # Count lesson violations specifically
        lesson_violations = sum(
            1 for f in findings
            if f.type == FindingType.LESSON_VIOLATION
        )

        # Determine recommended action
        recommendation = None
        if surfaced:
            top = surfaced[0]
            recommendation = f"Select finding: {top.title[:40]}"

        duration = time.time() - start_time

        # Enforce scan timeout (soft fail with error)
        if duration > PATROL_LIMITS["scan_timeout_seconds"]:
            return PatrolGearResult(
                scan_completed=False,
                findings_count=len(surfaced),
                findings=[_finding_to_dict(f) for f in surfaced],
                lesson_violations=lesson_violations,
                scan_duration_seconds=round(duration, 2),
                recommended_action=recommendation,
                error=f"Scan exceeded timeout ({PATROL_LIMITS['scan_timeout_seconds']}s)",
            )

        # v7.1: Check for graduation candidates and shadow rule promotions
        graduation_candidates = []
        shadow_rule_actions = []

        try:
            from rules_engine import (
                get_graduation_candidates,
                check_shadow_rules_for_promotion,
            )

            # Find lessons ready for graduation
            candidates = get_graduation_candidates(state, project_dir)
            graduation_candidates = [
                {
                    "trigger": c.get("trigger", ""),
                    "lesson": c.get("lesson", "")[:80],
                    "reinforced": c.get("reinforced", 0),
                }
                for c in candidates[:3]  # Limit to top 3
            ]

            # Check shadow rules for promotion/demotion
            shadow_rule_actions = check_shadow_rules_for_promotion(project_dir)

        except (ImportError, Exception):
            pass  # Graduation scanning optional

        return PatrolGearResult(
            scan_completed=True,
            findings_count=len(surfaced),
            findings=[_finding_to_dict(f) for f in surfaced],
            lesson_violations=lesson_violations,
            scan_duration_seconds=round(duration, 2),
            recommended_action=recommendation,
            error=None,
            graduation_candidates=graduation_candidates,
            shadow_rule_actions=shadow_rule_actions,
        )

    except Exception as e:
        duration = time.time() - start_time
        return PatrolGearResult(
            scan_completed=False,
            findings_count=0,
            findings=[],
            lesson_violations=0,
            scan_duration_seconds=round(duration, 2),
            recommended_action=None,
            error=str(e),
            graduation_candidates=[],
            shadow_rule_actions=[],
        )


def _filter_actionable_findings(findings: List[Any]) -> List[Any]:
    """Filter findings to those that are truly actionable."""
    actionable = []

    for finding in findings:
        location = str(getattr(finding, 'location', ''))

        # Skip test fixture findings (FIXME/TODO in test files that test the scanner)
        if 'test_' in location.lower() and finding.type.value == 'todo':
            # Check if it looks like a test fixture
            title = getattr(finding, 'title', '').lower()
            if 'critical bug' in title or 'critical issue' in title:
                continue  # Skip test fixture mock FIXMEs

        actionable.append(finding)

    return actionable


def _finding_to_dict(finding: Any) -> Dict[str, Any]:
    """Convert a ScoutFinding to a dict."""
    return {
        "type": finding.type.value,
        "priority": finding.priority.value,
        "title": finding.title,
        "description": finding.description,
        "location": finding.location,
        "suggested_action": finding.suggested_action,
    }


# =============================================================================
# DRIFT DETECTION
# =============================================================================

def detect_drift(state: Dict[str, Any]) -> List[Dict[str, Any]]:
    """
    Detect drift from expected patterns.

    Drift includes:
    - Files modified outside the plan
    - Unexpected state changes
    - Regression indicators

    Returns:
        List of drift findings
    """
    drift_findings = []

    # Check for state inconsistencies
    plan = state.get("plan", [])
    objective = state.get("objective", "")

    # Objective set but no plan
    if objective and not plan:
        drift_findings.append({
            "type": "drift",
            "issue": "objective_without_plan",
            "description": "Objective is set but no plan exists",
            "severity": "medium",
        })

    # Plan exists but no objective
    if plan and not objective:
        drift_findings.append({
            "type": "drift",
            "issue": "plan_without_objective",
            "description": "Plan exists but no objective is set",
            "severity": "low",
        })

    # Check for stale in_progress steps
    for i, step in enumerate(plan):
        if isinstance(step, dict) and step.get("status") == "in_progress":
            # Could check timestamps if available
            drift_findings.append({
                "type": "drift",
                "issue": "stale_in_progress",
                "description": f"Step {i+1} stuck in_progress",
                "severity": "low",
            })

    return drift_findings


# =============================================================================
# TRANSITION DETECTION
# =============================================================================

def should_transition_from_patrol(
    result: PatrolGearResult,
    gear_state: GearState
) -> Tuple[bool, Optional[GearTransition]]:
    """
    Check if Patrol Gear should transition to another gear.

    Returns:
        (should_transition, transition_type)
    """
    # Do not transition on patrol errors
    if result.error or not result.scan_completed:
        return False, None

    # Found actionable findings -> go to Active (via finding selection)
    if result.findings_count > 0:
        return True, GearTransition.PATROL_TO_ACTIVE

    # No findings -> go to Dream
    return True, GearTransition.PATROL_TO_DREAM


# =============================================================================
# DISPLAY HELPERS
# =============================================================================

def format_patrol_status(result: PatrolGearResult) -> str:
    """Format Patrol Gear results for display."""
    lines = [
        f"🔍 PATROL GEAR",
        f"   Scan: {'Complete' if result.scan_completed else 'Failed'}",
        f"   Duration: {result.scan_duration_seconds}s",
        f"   Findings: {result.findings_count}",
    ]

    if result.lesson_violations > 0:
        lines.append(f"   Lesson violations: {result.lesson_violations}")

    if result.error:
        lines.append(f"   Error: {result.error}")

    if result.findings:
        lines.append("")
        lines.append("   Top findings:")
        for i, f in enumerate(result.findings[:3]):
            priority_marker = "!" if f["priority"] == "high" else "~" if f["priority"] == "medium" else "."
            lines.append(f"   [{i+1}] {priority_marker} {f['title'][:45]}...")

    # v7.1: Graduation candidates
    if result.graduation_candidates:
        lines.append("")
        lines.append("   🎓 Graduation candidates:")
        for c in result.graduation_candidates[:3]:
            lines.append(f"      - [{c['trigger']}] (reinforced {c['reinforced']}x)")
        lines.append("   Run /edge-graduate to review")

    # v7.1: Shadow rule actions
    if result.shadow_rule_actions:
        lines.append("")
        lines.append("   🌙 Shadow rule updates:")
        for action in result.shadow_rule_actions[:3]:
            icon = "✅" if action["action"] == "promote" else "⚠️"
            lines.append(f"      {icon} {action['rule_id']}: {action['action']}")
            lines.append(f"         {action['reason']}")

    if result.recommended_action:
        lines.append("")
        lines.append(f"   Recommended: {result.recommended_action}")

    return "\n".join(lines)


def format_patrol_findings(findings: List[Dict[str, Any]]) -> str:
    """Format patrol findings for selection display."""
    if not findings:
        return "No actionable findings found."

    lines = ["PATROL FINDINGS:", ""]

    for i, f in enumerate(findings):
        priority_marker = "!" if f["priority"] == "high" else "~" if f["priority"] == "medium" else "."
        lines.append(f"  [{i+1}] {priority_marker} {f['title']}")
        lines.append(f"      Type: {f['type']} | Priority: {f['priority']}")
        lines.append(f"      Location: {f['location']}")
        if f.get("suggested_action"):
            lines.append(f"      Action: {f['suggested_action']}")
        lines.append("")

    return "\n".join(lines)
