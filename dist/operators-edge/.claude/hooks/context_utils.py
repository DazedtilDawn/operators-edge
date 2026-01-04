#!/usr/bin/env python3
"""
Operator's Edge - Context Utilities
Session context detection and orchestrator suggestions.

Split from orchestration_utils.py for better modularity.
"""
from state_utils import get_unresolved_mismatches, get_step_by_status
from archive_utils import check_state_entropy
from research_utils import get_blocking_research
from edge_config import SessionContext


# =============================================================================
# CONTEXT DETECTION HELPERS
# =============================================================================

def _check_plan_exists(state):
    """Check if a valid plan and objective exist."""
    plan = state.get('plan', [])
    if not plan:
        return (SessionContext.NEEDS_PLAN, {"reason": "No plan defined"})

    objective = state.get('objective', '')
    if not objective or objective in ("Set your objective here", "null"):
        return (SessionContext.NEEDS_PLAN, {"reason": "No objective set"})

    return None


def _check_research_status(state):
    """Check for blocking research items."""
    blocking_research = get_blocking_research(state)
    if not blocking_research:
        return None

    in_progress = [r for r in blocking_research if r.get('status') == 'in_progress']
    pending = [r for r in blocking_research if r.get('status') == 'pending']

    if in_progress:
        return (SessionContext.AWAITING_RESEARCH, {
            "reason": f"{len(in_progress)} research item(s) awaiting results",
            "research": in_progress
        })
    if pending:
        return (SessionContext.NEEDS_RESEARCH, {
            "reason": f"{len(pending)} critical research item(s) pending",
            "research": pending
        })
    return None


def _check_mismatches(state):
    """Check for unresolved mismatches."""
    unresolved = get_unresolved_mismatches(state)
    if unresolved:
        return (SessionContext.NEEDS_ADAPTATION, {
            "reason": f"{len(unresolved)} unresolved mismatch(es)",
            "mismatches": unresolved
        })
    return None


def _check_entropy(state):
    """Check if state needs pruning."""
    needs_pruning, prune_reasons = check_state_entropy(state)
    if needs_pruning:
        return (SessionContext.NEEDS_PRUNING, {
            "reason": "State needs pruning",
            "details": prune_reasons
        })
    return None


def _check_plan_progress(state):
    """Check plan step statuses and return appropriate context."""
    in_progress = get_step_by_status(state, 'in_progress')
    pending = get_step_by_status(state, 'pending')
    blocked = get_step_by_status(state, 'blocked')

    # All done?
    if not pending and not in_progress and not blocked:
        if not state.get('self_score'):
            return (SessionContext.NEEDS_SCORING, {
                "reason": "All steps complete, needs self-assessment"
            })
        return (SessionContext.ALL_COMPLETE, {
            "reason": "All steps complete and scored"
        })

    # Something blocked?
    if blocked:
        return (SessionContext.NEEDS_ADAPTATION, {
            "reason": f"{len(blocked)} step(s) blocked",
            "blocked": blocked
        })

    # Step in progress?
    if in_progress:
        return (SessionContext.STEP_IN_PROGRESS, {
            "reason": "Step in progress",
            "step": in_progress[0] if in_progress else None
        })

    # Ready for next step?
    if pending:
        current_step = state.get('current_step', 1)
        return (SessionContext.READY_FOR_STEP, {
            "reason": f"Ready for step {current_step}",
            "next_step": pending[0] if pending else None
        })

    return (SessionContext.READY_FOR_STEP, {"reason": "Ready to proceed"})


# =============================================================================
# MAIN CONTEXT DETECTION
# =============================================================================

def detect_session_context(state, recent_error=None):
    """
    Detect the current context based on state and recent activity.
    Returns (context_type, details).

    Checks in priority order:
    1. Plan/objective existence
    2. Blocking research
    3. Unresolved mismatches
    4. Recent errors
    5. State entropy
    6. Plan progress
    """
    if not state:
        return (SessionContext.NEEDS_PLAN, {"reason": "No state file found"})

    # Check each condition in priority order
    result = _check_plan_exists(state)
    if result:
        return result

    result = _check_research_status(state)
    if result:
        return result

    result = _check_mismatches(state)
    if result:
        return result

    if recent_error:
        return (SessionContext.POTENTIAL_MISMATCH, {
            "reason": "Recent error detected",
            "error": recent_error
        })

    result = _check_entropy(state)
    if result:
        return result

    return _check_plan_progress(state)


def get_orchestrator_suggestion(context_type, details):
    """Get the suggested action based on context."""
    suggestions = {
        SessionContext.NEEDS_PLAN: {
            "action": "Create a plan",
            "command": "/edge-plan",
            "message": "No plan exists. Let's define your objective and break it into steps."
        },
        SessionContext.NEEDS_RESEARCH: {
            "action": "Complete research",
            "command": "/edge-research",
            "message": "Critical research blocks progress. Generate prompts for external deep research."
        },
        SessionContext.AWAITING_RESEARCH: {
            "action": "Process research results",
            "command": "/edge-research-results",
            "message": "Research in progress. Paste your results from the external tool."
        },
        SessionContext.READY_FOR_STEP: {
            "action": "Start next step",
            "command": "/edge-step",
            "message": f"Ready to start: {details.get('next_step', {}).get('description', 'next step')}"
        },
        SessionContext.STEP_IN_PROGRESS: {
            "action": "Continue current step",
            "command": None,
            "message": f"Currently working on: {details.get('step', {}).get('description', 'current step')}"
        },
        SessionContext.POTENTIAL_MISMATCH: {
            "action": "Log the mismatch",
            "command": "/edge-mismatch",
            "message": "An error occurred. Let's capture what happened before proceeding."
        },
        SessionContext.UNRESOLVED_MISMATCH: {
            "action": "Log the mismatch",
            "command": "/edge-mismatch",
            "message": "Something unexpected happened. Capture it before retrying."
        },
        SessionContext.NEEDS_ADAPTATION: {
            "action": "Adapt the plan",
            "command": "/edge-adapt",
            "message": f"Unresolved issue(s) need attention. Let's revise the approach."
        },
        SessionContext.NEEDS_PRUNING: {
            "action": "Prune the state",
            "command": "/edge-prune",
            "message": "State is getting bloated. Let's archive completed work."
        },
        SessionContext.NEEDS_SCORING: {
            "action": "Score this session",
            "command": "/edge-score",
            "message": "All steps complete! Let's assess how we did."
        },
        SessionContext.ALL_COMPLETE: {
            "action": "Session complete",
            "command": None,
            "message": "All work complete and scored. Ready to end session."
        }
    }
    return suggestions.get(context_type, {
        "action": "Unknown state",
        "command": "/edge-plan",
        "message": "State unclear. Start with a plan."
    })
