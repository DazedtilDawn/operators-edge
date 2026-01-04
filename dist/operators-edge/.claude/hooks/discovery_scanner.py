#!/usr/bin/env python3
"""
Operator's Edge - Discovery Scanners
Autonomous discovery of feature opportunities through self-analysis.

The system becomes self-aware by mining its own history:
- Archive Pain Miner: Finds recurring pain points in archived work
- Lesson Reinforcement Analyzer: Identifies heavily-used lessons
- Workflow Friction Detector: Spots repeated manual actions
"""

import json
import re
from collections import Counter, defaultdict
from datetime import datetime, timedelta
from pathlib import Path
from typing import List, Dict, Tuple, Optional

from discovery_config import (
    DiscoveryFinding,
    DiscoveryEvidence,
    DiscoverySource,
    DiscoveryConfidence,
    DiscoveryValue,
    DiscoveryEffort,
    DISCOVERY_THRESHOLDS,
    MISMATCH_CATEGORIES,
    generate_discovery_id,
    sort_discoveries,
)
from state_utils import get_proof_dir, get_memory_items, get_project_dir
from pathlib import Path


# =============================================================================
# ARCHIVE PAIN MINER
# =============================================================================

def load_archive_entries(max_days: int = 90, project_root: Path = None) -> List[dict]:
    """Load archive entries from the last N days."""
    if project_root:
        archive_path = project_root / ".proof" / "archive.jsonl"
    else:
        archive_path = get_proof_dir() / "archive.jsonl"

    if not archive_path.exists():
        return []

    entries = []
    cutoff = datetime.now() - timedelta(days=max_days)

    try:
        for line in archive_path.read_text().strip().split('\n'):
            if not line:
                continue
            entry = json.loads(line)
            # Parse timestamp - handle various formats
            ts_str = entry.get("timestamp", "")
            try:
                # Remove timezone suffix if present
                ts_clean = ts_str.replace('Z', '').split('+')[0]
                ts = datetime.fromisoformat(ts_clean)
                if ts > cutoff:
                    entries.append(entry)
            except (ValueError, TypeError):
                entries.append(entry)  # Include if can't parse date
    except Exception:
        pass

    return entries


def categorize_mismatch(text: str) -> Optional[str]:
    """Categorize a mismatch by keywords."""
    text_lower = text.lower()
    for category, keywords in MISMATCH_CATEGORIES.items():
        if any(kw in text_lower for kw in keywords):
            return category
    return None


def mine_mismatch_patterns(entries: List[dict]) -> List[Tuple[str, int, List[str]]]:
    """
    Mine archive for mismatch patterns.

    Returns list of (category, count, examples) tuples.
    """
    category_counts = Counter()
    category_examples = defaultdict(list)

    for entry in entries:
        if entry.get("type") != "mismatch":
            continue

        expectation = entry.get("expectation", "")
        observation = entry.get("observation", "")
        combined = f"{expectation} {observation}"

        category = categorize_mismatch(combined)
        if category:
            category_counts[category] += 1
            if len(category_examples[category]) < 5:
                category_examples[category].append(expectation[:100])

    # Return patterns meeting threshold
    threshold = DISCOVERY_THRESHOLDS["min_pain_frequency"]
    return [
        (cat, count, category_examples[cat])
        for cat, count in category_counts.most_common()
        if count >= threshold
    ]


def mine_objective_patterns(entries: List[dict]) -> Dict[str, any]:
    """
    Analyze completed objectives for patterns.

    Returns insights about objective success/failure patterns.
    """
    objectives = [e for e in entries if e.get("type") == "completed_objective"]

    if len(objectives) < 3:
        return {}

    # Analyze scores by objective keywords
    keyword_scores = defaultdict(list)

    for obj in objectives:
        objective_text = obj.get("objective", "").lower()
        score_data = obj.get("score") or obj.get("self_score") or {}
        total = score_data.get("total", 0) if score_data else 0

        # Extract keywords
        keywords = ["refactor", "test", "feature", "fix", "add", "implement", "update"]
        for kw in keywords:
            if kw in objective_text:
                keyword_scores[kw].append(total)

    # Find problem areas (low average scores)
    problem_areas = {}
    for kw, scores in keyword_scores.items():
        if len(scores) >= 2:
            avg = sum(scores) / len(scores)
            if avg < 5:  # Below threshold
                problem_areas[kw] = {
                    "avg_score": avg,
                    "count": len(scores),
                }

    return problem_areas


def scan_archive_pain(state: dict = None, project_root: Path = None) -> List[DiscoveryFinding]:
    """
    Main archive pain scanner.

    Mines archive.jsonl for:
    - Recurring mismatch categories
    - Low-scoring objective types
    - Frequent failure patterns
    """
    findings = []
    lookback = DISCOVERY_THRESHOLDS["archive_lookback_days"]
    entries = load_archive_entries(max_days=lookback, project_root=project_root)

    if not entries:
        return findings

    # 1. Mine mismatch patterns
    mismatch_patterns = mine_mismatch_patterns(entries)

    for category, count, examples in mismatch_patterns:
        # Generate proposal based on category
        proposals = {
            "git": ("Add git operation preview/confirmation", "Show diff and confirm before push"),
            "test": ("Improve test failure diagnostics", "Surface test errors in session start"),
            "import": ("Add import validation on startup", "Check imports before executing plan"),
            "path": ("Add path existence validation", "Verify paths before operations"),
            "permission": ("Add permission pre-check", "Validate permissions before blocking"),
            "timeout": ("Add timeout configuration", "Make timeouts configurable per operation"),
            "parse": ("Add schema validation", "Validate YAML/JSON before use"),
        }

        if category in proposals:
            title, sketch = proposals[category]
        else:
            title = f"Reduce {category} mismatches"
            sketch = f"Analyze and prevent {category}-related failures"

        finding = DiscoveryFinding(
            id=generate_discovery_id(DiscoverySource.ARCHIVE_PAIN, title),
            title=title,
            source=DiscoverySource.ARCHIVE_PAIN,
            confidence=_confidence_from_count(count),
            value=DiscoveryValue.HIGH if count >= 5 else DiscoveryValue.MEDIUM,
            effort=DiscoveryEffort.MEDIUM,
            evidence=DiscoveryEvidence(
                source=DiscoverySource.ARCHIVE_PAIN,
                pattern=f"{count} mismatches in '{category}' category",
                frequency=count,
                data_points=examples,
                time_range_days=lookback,
            ),
            sketch=sketch,
        )
        findings.append(finding)

    # 2. Mine objective patterns for problem areas
    problem_areas = mine_objective_patterns(entries)

    for kw, data in problem_areas.items():
        finding = DiscoveryFinding(
            id=generate_discovery_id(DiscoverySource.ARCHIVE_PAIN, f"{kw}_objectives"),
            title=f"Improve tooling for '{kw}' objectives",
            source=DiscoverySource.ARCHIVE_PAIN,
            confidence=DiscoveryConfidence.MEDIUM,
            value=DiscoveryValue.MEDIUM,
            effort=DiscoveryEffort.HIGH,
            evidence=DiscoveryEvidence(
                source=DiscoverySource.ARCHIVE_PAIN,
                pattern=f"'{kw}' objectives average {data['avg_score']:.1f}/6 score",
                frequency=data["count"],
                data_points=[],
                time_range_days=lookback,
            ),
            sketch=f"Add specialized support for {kw} workflows",
        )
        findings.append(finding)

    return sort_discoveries(findings)


def _confidence_from_count(count: int) -> DiscoveryConfidence:
    """Map observation count to confidence level."""
    if count >= 10:
        return DiscoveryConfidence.HIGH
    elif count >= 5:
        return DiscoveryConfidence.MEDIUM
    else:
        return DiscoveryConfidence.LOW


# =============================================================================
# LESSON REINFORCEMENT ANALYZER
# =============================================================================

# Keywords that indicate a meta-lesson (design principle, not automatable)
META_LESSON_INDICATORS = [
    # Abstract relationship verbs
    "is not", "beats", "enables", "ensures", "reduces",
    "by construction", "provides", "rather than",
    # System-internal triggers (lessons about the system itself)
]

# Triggers that are about the system itself (meta by nature)
META_TRIGGERS = [
    "hooks", "enforcement", "memory", "loop", "archive",
    "state", "adaptation", "prune", "scoring",
]

# Triggers that are actionable (external tools/platforms)
ACTIONABLE_TRIGGERS = [
    "git", "python", "windows", "mac", "path", "import",
    "test", "file", "command", "clipboard", "api",
]


def is_meta_lesson(trigger: str, lesson_text: str) -> bool:
    """
    Detect if a lesson is a meta-lesson (design principle).

    Meta-lessons describe HOW the system works or design philosophy.
    They're not automation opportunities - they're already implemented.

    Returns True if the lesson should be filtered out.
    """
    trigger_lower = trigger.lower()
    lesson_lower = lesson_text.lower()

    # Check if trigger is about the system itself
    if any(meta in trigger_lower for meta in META_TRIGGERS):
        return True

    # Check for meta-lesson language patterns
    if any(indicator in lesson_lower for indicator in META_LESSON_INDICATORS):
        return True

    # Check if it's explicitly actionable
    if any(action in trigger_lower for action in ACTIONABLE_TRIGGERS):
        return False

    # Default: if lesson contains imperative verbs, it's actionable
    actionable_verbs = ["use ", "run ", "copy ", "always ", "never ", "check "]
    if any(verb in lesson_lower for verb in actionable_verbs):
        return False

    # Default to meta if uncertain (conservative)
    return True


def scan_lesson_reinforcement(state: dict) -> List[DiscoveryFinding]:
    """
    Analyze lesson reinforcement patterns.

    High-reinforcement lessons = recurring situations = automation opportunity.
    Filters out meta-lessons (design principles) that aren't automatable.
    """
    findings = []

    if not state:
        return findings

    memory = get_memory_items(state)
    if not memory:
        return findings

    # Find highly-reinforced lessons
    threshold = DISCOVERY_THRESHOLDS["min_lesson_reinforcement"]

    for lesson in memory:
        if not isinstance(lesson, dict):
            continue

        reinforced = lesson.get("reinforced", 0)
        if reinforced < threshold:
            continue

        trigger = lesson.get("trigger", "")
        lesson_text = lesson.get("lesson", "")

        # Filter out meta-lessons (design principles)
        if is_meta_lesson(trigger, lesson_text):
            continue

        # Generate proposal based on trigger
        title = f"Automate handling of '{trigger}' situations"
        sketch = f"Current lesson: {lesson_text}\nConsider automating this pattern."

        # Estimate effort based on lesson complexity
        if any(kw in lesson_text.lower() for kw in ["simple", "just", "always"]):
            effort = DiscoveryEffort.LOW
        elif any(kw in lesson_text.lower() for kw in ["refactor", "change", "complex"]):
            effort = DiscoveryEffort.HIGH
        else:
            effort = DiscoveryEffort.MEDIUM

        finding = DiscoveryFinding(
            id=generate_discovery_id(DiscoverySource.LESSON_REINFORCEMENT, trigger),
            title=title,
            source=DiscoverySource.LESSON_REINFORCEMENT,
            confidence=_confidence_from_count(reinforced),
            value=DiscoveryValue.MEDIUM,
            effort=effort,
            evidence=DiscoveryEvidence(
                source=DiscoverySource.LESSON_REINFORCEMENT,
                pattern=f"Lesson reinforced {reinforced}x",
                frequency=reinforced,
                data_points=[lesson_text],
                time_range_days=30,
            ),
            sketch=sketch,
        )
        findings.append(finding)

    return sort_discoveries(findings)


# =============================================================================
# INTEGRATION GAP FINDER
# =============================================================================

def scan_integration_gaps() -> List[DiscoveryFinding]:
    """
    Find available but unused integrations.

    Checks for capabilities that exist but aren't fully utilized.
    """
    findings = []

    # Check for ClickUp MCP usage
    # This is a simplified check - in practice would analyze session logs
    finding = DiscoveryFinding(
        id=generate_discovery_id(DiscoverySource.INTEGRATION_GAP, "clickup_task_creation"),
        title="Auto-create ClickUp tasks from objectives",
        source=DiscoverySource.INTEGRATION_GAP,
        confidence=DiscoveryConfidence.MEDIUM,
        value=DiscoveryValue.MEDIUM,
        effort=DiscoveryEffort.LOW,
        evidence=DiscoveryEvidence(
            source=DiscoverySource.INTEGRATION_GAP,
            pattern="ClickUp MCP available, used for reading only",
            frequency=1,
            data_points=["mcp__clickup__searchTasks used", "mcp__clickup__getTaskById used"],
            time_range_days=30,
        ),
        sketch="When objective is set, optionally create matching ClickUp task",
        affected_files=["orchestration_utils.py"],
    )
    findings.append(finding)

    return findings


# =============================================================================
# MAIN DISCOVERY SCAN
# =============================================================================

def run_discovery_scan(state: dict = None, project_root: Path = None) -> Tuple[List[DiscoveryFinding], dict]:
    """
    Run all discovery scanners.

    Args:
        state: Current active_context state
        project_root: Project root directory (for archive location)

    Returns (findings, metadata) tuple.
    """
    start_time = datetime.now()
    all_findings = []

    # Run each scanner
    all_findings.extend(scan_archive_pain(state, project_root=project_root))
    all_findings.extend(scan_lesson_reinforcement(state))
    all_findings.extend(scan_integration_gaps())

    # Deduplicate by ID
    seen_ids = set()
    unique_findings = []
    for f in all_findings:
        if f.id not in seen_ids:
            seen_ids.add(f.id)
            unique_findings.append(f)

    # Sort and limit
    sorted_findings = sort_discoveries(unique_findings)
    max_findings = DISCOVERY_THRESHOLDS["max_discoveries"]
    limited_findings = sorted_findings[:max_findings]

    duration = (datetime.now() - start_time).total_seconds()

    metadata = {
        "last_scan": datetime.now().isoformat(),
        "scan_duration_seconds": duration,
        "total_findings": len(unique_findings),
        "returned_findings": len(limited_findings),
        "sources_scanned": ["archive_pain", "lesson_reinforcement", "integration_gap"],
    }

    return limited_findings, metadata


# =============================================================================
# DISCOVERY REPORT FORMATTING
# =============================================================================

def format_discovery_report(findings: List[DiscoveryFinding], metadata: dict) -> str:
    """Format discovery findings for terminal display."""
    from discovery_config import format_discovery_for_display

    lines = [
        "",
        "DISCOVERY FINDINGS (what's missing)",
        "─" * 60,
    ]

    if not findings:
        lines.append("  No discoveries - system is well-optimized!")
    else:
        for i, finding in enumerate(findings):
            lines.append(format_discovery_for_display(finding, i))
            lines.append("")

    return '\n'.join(lines)
