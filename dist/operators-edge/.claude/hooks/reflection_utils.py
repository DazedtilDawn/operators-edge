#!/usr/bin/env python3
"""
Operator's Edge - Reflection Utilities
Score pattern analysis and improvement suggestions.

Split from orchestration_utils.py for better modularity.
"""

# =============================================================================
# REFLECTION ANALYSIS - Learn from past scores to improve
# =============================================================================

# The 6 adaptation checks
ADAPTATION_CHECKS = [
    "mismatch_detection",
    "plan_revision",
    "tool_switching",
    "memory_update",
    "proof_generation",
    "stop_condition"
]

# Improvement suggestions for each check
CHECK_IMPROVEMENTS = {
    "mismatch_detection": {
        "description": "Spot divergences between expectations and reality",
        "improvements": [
            "Add explicit 'expected:' field to each plan step",
            "Compare expected vs actual after each tool use",
            "Log any surprises immediately with /edge-mismatch"
        ],
        "brainstorm_challenge": "How might we detect mismatches earlier in the workflow?"
    },
    "plan_revision": {
        "description": "Change approach when things go wrong (not just retry)",
        "improvements": [
            "After 2 failures, stop and revise the plan",
            "Break large steps into smaller ones when blocked",
            "Ask: 'What assumption might be wrong?'"
        ],
        "brainstorm_challenge": "How might we make plan revision more automatic?"
    },
    "tool_switching": {
        "description": "Abandon tools that aren't working",
        "improvements": [
            "Keep a list of alternative approaches for each step",
            "Set a 'try limit' for each tool before switching",
            "Prefer simpler tools when complex ones fail"
        ],
        "brainstorm_challenge": "How might we know when to switch tools sooner?"
    },
    "memory_update": {
        "description": "Capture reusable lessons from what you learn",
        "improvements": [
            "After each mismatch, ask: 'What lesson is here?'",
            "Add trigger-linked lessons immediately",
            "Review lessons at session end"
        ],
        "brainstorm_challenge": "How might we capture lessons automatically?"
    },
    "proof_generation": {
        "description": "Attach evidence, not just claims",
        "improvements": [
            "Run a verification command after each step",
            "Include test output in proof",
            "Screenshot or log key results"
        ],
        "brainstorm_challenge": "How might we automate proof collection?"
    },
    "stop_condition": {
        "description": "Escalate appropriately when blocked or uncertain",
        "improvements": [
            "Ask crisp questions with bounded options",
            "Present what you know AND what you don't know",
            "Set explicit criteria for when to ask vs proceed"
        ],
        "brainstorm_challenge": "How might we know when to escalate?"
    }
}


def analyze_score_patterns(archive_entries):
    """
    Analyze archived objectives to find patterns in scores.

    Args:
        archive_entries: List of archive entries (from load_archive)

    Returns:
        dict with:
        - total_objectives: count
        - avg_score: float
        - level_distribution: {level: count}
        - check_failures: {check: count} (if check data available)
        - weakest_checks: list of checks that fail most
        - score_trend: "improving" | "stable" | "declining"
    """
    objectives = [e for e in archive_entries if e.get('type') == 'completed_objective']

    if not objectives:
        return {
            "total_objectives": 0,
            "avg_score": 0,
            "level_distribution": {},
            "check_failures": {},
            "weakest_checks": [],
            "score_trend": "unknown"
        }

    # Calculate stats
    scores = []
    level_counts = {}
    check_failures = {check: 0 for check in ADAPTATION_CHECKS}

    for obj in objectives:
        # Support both 'score' and 'self_score' keys
        score_data = obj.get('score') or obj.get('self_score') or {}
        total = score_data.get('total', 0)
        level = score_data.get('level', 'unknown')

        # Only count entries that have actual score data
        if score_data and 'total' in score_data:
            scores.append(total)
            level_counts[level] = level_counts.get(level, 0) + 1
        else:
            # No score data - count as unknown but don't include in average
            level_counts['unknown'] = level_counts.get('unknown', 0) + 1

        # If detailed check data is available
        checks = score_data.get('checks', {})
        for check_name, check_data in checks.items():
            if isinstance(check_data, dict) and check_data.get('met') == False:
                check_failures[check_name] = check_failures.get(check_name, 0) + 1

    # Calculate average
    avg_score = sum(scores) / len(scores) if scores else 0

    # Find weakest checks (failed 2+ times)
    weakest = sorted(
        [(k, v) for k, v in check_failures.items() if v >= 2],
        key=lambda x: x[1],
        reverse=True
    )
    weakest_checks = [k for k, v in weakest]

    # Determine trend (if enough data)
    trend = "unknown"
    if len(scores) >= 3:
        recent = scores[-3:]  # Last 3 scores
        older = scores[:-3] if len(scores) > 3 else scores[:1]
        recent_avg = sum(recent) / len(recent)
        older_avg = sum(older) / len(older)

        if recent_avg > older_avg + 0.5:
            trend = "improving"
        elif recent_avg < older_avg - 0.5:
            trend = "declining"
        else:
            trend = "stable"

    return {
        "total_objectives": len(objectives),
        "avg_score": round(avg_score, 1),
        "level_distribution": level_counts,
        "check_failures": check_failures,
        "weakest_checks": weakest_checks,
        "score_trend": trend
    }


def get_recurring_failures(archive_entries, threshold=2):
    """
    Find checks that have failed repeatedly across sessions.

    Args:
        archive_entries: List of archive entries
        threshold: Minimum failures to be considered "recurring"

    Returns:
        List of {check, failure_count, improvement_suggestions}
    """
    analysis = analyze_score_patterns(archive_entries)

    recurring = []
    for check, count in analysis.get('check_failures', {}).items():
        if count >= threshold:
            check_info = CHECK_IMPROVEMENTS.get(check, {})
            recurring.append({
                "check": check,
                "failure_count": count,
                "description": check_info.get('description', 'Unknown check'),
                "improvements": check_info.get('improvements', []),
                "brainstorm_challenge": check_info.get('brainstorm_challenge', '')
            })

    # Sort by failure count
    recurring.sort(key=lambda x: x['failure_count'], reverse=True)

    return recurring


def get_improvement_suggestion(weak_check):
    """
    Get concrete improvement suggestion for a specific check.

    Args:
        weak_check: Name of the check that failed

    Returns:
        dict with suggestion details
    """
    check_info = CHECK_IMPROVEMENTS.get(weak_check, {})

    if not check_info:
        return {
            "check": weak_check,
            "suggestion": f"Improve {weak_check}",
            "actions": ["Review the check criteria", "Practice intentionally"]
        }

    return {
        "check": weak_check,
        "description": check_info.get('description', ''),
        "suggestion": f"Focus on improving {weak_check}",
        "actions": check_info.get('improvements', []),
        "brainstorm": check_info.get('brainstorm_challenge', '')
    }


def generate_reflection_summary(archive_entries):
    """
    Generate a human-readable summary of reflection patterns.

    Returns formatted string for display at session start.
    """
    analysis = analyze_score_patterns(archive_entries)

    if analysis['total_objectives'] == 0:
        return None

    lines = []

    # Overall stats
    lines.append(f"Sessions scored: {analysis['total_objectives']}")
    lines.append(f"Average score: {analysis['avg_score']}/6")

    # Level distribution
    levels = analysis.get('level_distribution', {})
    if levels:
        level_str = ", ".join([f"{l}: {c}" for l, c in sorted(levels.items())])
        lines.append(f"Levels: {level_str}")

    # Trend
    trend = analysis.get('score_trend', 'unknown')
    if trend != 'unknown':
        trend_emoji = {"improving": "📈", "stable": "➡️", "declining": "📉"}.get(trend, "")
        lines.append(f"Trend: {trend_emoji} {trend}")

    # Recurring failures (the actionable part)
    recurring = get_recurring_failures(archive_entries, threshold=2)
    if recurring:
        lines.append("")
        lines.append("⚠️  RECURRING WEAK CHECKS:")
        for r in recurring[:2]:  # Show top 2
            lines.append(f"  • {r['check']} (failed {r['failure_count']}x)")
            if r['improvements']:
                lines.append(f"    Try: {r['improvements'][0]}")

    return "\n".join(lines)


def generate_improvement_challenges(archive_entries):
    """
    Generate brainstorm challenges from recurring failures.

    Returns list of "How might we..." challenges.
    """
    recurring = get_recurring_failures(archive_entries, threshold=2)

    challenges = []
    for r in recurring:
        if r.get('brainstorm_challenge'):
            challenges.append(r['brainstorm_challenge'])

    return challenges
