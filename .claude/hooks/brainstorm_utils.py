#!/usr/bin/env python3
"""
Operator's Edge - Brainstorm Utilities
Project scanning for improvement opportunities.
"""
import json
from datetime import datetime

from state_utils import get_project_dir, load_yaml_state
from edge_config import SCAN_PATTERNS, COMPLEXITY_THRESHOLDS


# =============================================================================
# CODE MARKER SCANNING
# =============================================================================

def scan_code_markers(project_dir=None):
    """
    Scan codebase for TODO, FIXME, HACK, XXX markers.
    Returns list of {file, line, marker, text, priority}.
    """
    if project_dir is None:
        project_dir = get_project_dir()

    findings = []
    files_scanned = 0

    for ext in SCAN_PATTERNS["code_extensions"]:
        for file_path in project_dir.rglob(f"*{ext}"):
            # Skip excluded directories
            if any(skip in str(file_path) for skip in SCAN_PATTERNS["skip_dirs"]):
                continue

            files_scanned += 1
            if files_scanned > COMPLEXITY_THRESHOLDS["max_files_to_scan"]:
                break

            try:
                content = file_path.read_text(errors='ignore')
                lines = content.split('\n')

                for i, line in enumerate(lines, 1):
                    for marker in SCAN_PATTERNS["code_markers"]:
                        if marker in line.upper():
                            # Extract the comment text
                            text = line.strip()
                            if len(text) > 100:
                                text = text[:100] + "..."

                            priority = "high" if marker in ["FIXME", "BUG"] else "medium"

                            findings.append({
                                "file": str(file_path.relative_to(project_dir)),
                                "line": i,
                                "marker": marker,
                                "text": text,
                                "priority": priority
                            })
                            break  # Only count each line once
            except Exception:
                continue

    return findings


# =============================================================================
# LARGE FILE SCANNING
# =============================================================================

def scan_large_files(project_dir=None):
    """
    Find files that might need refactoring due to size.
    Returns list of {file, lines, priority}.
    """
    if project_dir is None:
        project_dir = get_project_dir()

    findings = []
    files_scanned = 0

    for ext in SCAN_PATTERNS["code_extensions"]:
        for file_path in project_dir.rglob(f"*{ext}"):
            # Skip excluded directories
            if any(skip in str(file_path) for skip in SCAN_PATTERNS["skip_dirs"]):
                continue

            files_scanned += 1
            if files_scanned > COMPLEXITY_THRESHOLDS["max_files_to_scan"]:
                break

            try:
                content = file_path.read_text(errors='ignore')
                line_count = len(content.split('\n'))

                if line_count >= COMPLEXITY_THRESHOLDS["very_large_file_lines"]:
                    findings.append({
                        "file": str(file_path.relative_to(project_dir)),
                        "lines": line_count,
                        "priority": "high",
                        "reason": f"Very large file ({line_count} lines) - consider splitting"
                    })
                elif line_count >= COMPLEXITY_THRESHOLDS["large_file_lines"]:
                    findings.append({
                        "file": str(file_path.relative_to(project_dir)),
                        "lines": line_count,
                        "priority": "medium",
                        "reason": f"Large file ({line_count} lines) - may need refactoring"
                    })
            except Exception:
                continue

    return sorted(findings, key=lambda x: x["lines"], reverse=True)


# =============================================================================
# ARCHIVE PATTERN ANALYSIS
# =============================================================================

def scan_archive_patterns(project_dir=None):
    """
    Analyze archive for recurring mismatches and patterns.
    Returns list of {pattern, count, description, priority}.
    """
    if project_dir is None:
        project_dir = get_project_dir()

    archive_path = project_dir / ".proof" / "archive.jsonl"

    if not archive_path.exists():
        return []

    findings = []
    mismatch_causes = {}
    error_patterns = {}

    try:
        content = archive_path.read_text()
        for line in content.strip().split('\n'):
            if not line.strip():
                continue
            try:
                entry = json.loads(line)

                # Count mismatch causes
                if entry.get('type') == 'resolved_mismatch':
                    cause = entry.get('delta', 'Unknown')
                    mismatch_causes[cause] = mismatch_causes.get(cause, 0) + 1

                # Look for error patterns in completed steps
                if entry.get('type') == 'completed_step':
                    proof = entry.get('proof', '')
                    if 'error' in proof.lower() or 'fix' in proof.lower():
                        pattern = proof[:50]
                        error_patterns[pattern] = error_patterns.get(pattern, 0) + 1

            except json.JSONDecodeError:
                continue
    except Exception:
        return []

    # Convert to findings
    for cause, count in mismatch_causes.items():
        if count >= 2:
            findings.append({
                "pattern": "recurring_mismatch",
                "cause": cause,
                "count": count,
                "description": f"'{cause}' has caused mismatches {count} times",
                "priority": "high" if count >= 3 else "medium"
            })

    return findings


# =============================================================================
# STATE PATTERN ANALYSIS
# =============================================================================

def scan_state_patterns(state):
    """
    Analyze current state for patterns that suggest improvement opportunities.
    Returns list of {pattern, description, priority}.
    """
    findings = []

    if not state:
        return findings

    # Check for unresolved mismatches
    mismatches = state.get('mismatches', [])
    unresolved = [m for m in mismatches if isinstance(m, dict) and not m.get('resolved')]
    if len(unresolved) >= 2:
        findings.append({
            "pattern": "multiple_unresolved_mismatches",
            "description": f"{len(unresolved)} unresolved mismatches - may indicate systemic issue",
            "priority": "high"
        })

    # Check for blocked steps
    plan = state.get('plan', [])
    blocked = [p for p in plan if isinstance(p, dict) and p.get('status') == 'blocked']
    if blocked:
        findings.append({
            "pattern": "blocked_steps",
            "description": f"{len(blocked)} blocked step(s) in plan",
            "priority": "high"
        })

    # Check for stale research
    research = state.get('research', [])
    pending_research = [r for r in research if isinstance(r, dict) and r.get('status') == 'pending']
    if len(pending_research) >= 2:
        findings.append({
            "pattern": "pending_research",
            "description": f"{len(pending_research)} research items pending - knowledge gaps",
            "priority": "medium"
        })

    # Check for unreinforced lessons (may need validation)
    lessons = state.get('lessons', []) or state.get('memory', [])
    unreinforced = [l for l in lessons if isinstance(l, dict) and l.get('reinforced', 0) == 0]
    if len(unreinforced) >= 3:
        findings.append({
            "pattern": "unreinforced_lessons",
            "description": f"{len(unreinforced)} lessons never validated - may be wrong",
            "priority": "low"
        })

    return findings


# =============================================================================
# CHALLENGE GENERATION
# =============================================================================

def generate_suggested_challenges(findings):
    """
    Generate "How might we..." challenges from scan findings.
    Returns list of challenge strings.
    """
    challenges = []

    # From code markers
    marker_files = set()
    for f in findings.get('code_markers', []):
        marker_files.add(f['file'])
    if len(marker_files) >= 3:
        challenges.append(f"How might we reduce technical debt? ({len(marker_files)} files have TODO/FIXME markers)")

    # From large files
    large_files = findings.get('large_files', [])
    if large_files:
        biggest = large_files[0]
        challenges.append(f"How might we improve code organization? ({biggest['file']} is {biggest['lines']} lines)")

    # From archive patterns
    for pattern in findings.get('archive_patterns', []):
        if pattern['pattern'] == 'recurring_mismatch':
            challenges.append(f"How might we prevent '{pattern['cause']}' errors from recurring?")

    # From state patterns
    for pattern in findings.get('state_patterns', []):
        if pattern['pattern'] == 'multiple_unresolved_mismatches':
            challenges.append("How might we improve our error handling and recovery process?")
        elif pattern['pattern'] == 'blocked_steps':
            challenges.append("How might we reduce blockers in our development process?")
        elif pattern['pattern'] == 'pending_research':
            challenges.append("How might we better identify and resolve unknowns early?")

    # Add generic challenges if we don't have enough specific ones
    if len(challenges) < 3:
        generic = [
            "How might we improve developer experience in this codebase?",
            "How might we make this system more maintainable?",
            "How might we reduce cognitive load when working on this project?"
        ]
        for g in generic:
            if g not in challenges:
                challenges.append(g)
                if len(challenges) >= 3:
                    break

    return challenges[:5]  # Return top 5


# =============================================================================
# FULL SCAN RUNNER
# =============================================================================

def run_brainstorm_scan(project_dir=None, state=None):
    """
    Run full project scan for improvement opportunities.
    Returns scan_findings structure matching schema.
    """
    if project_dir is None:
        project_dir = get_project_dir()

    if state is None:
        state = load_yaml_state() or {}

    findings = {
        "timestamp": datetime.now().isoformat(),
        "code_markers": scan_code_markers(project_dir),
        "large_files": scan_large_files(project_dir),
        "archive_patterns": scan_archive_patterns(project_dir),
        "state_patterns": scan_state_patterns(state)
    }

    # Generate suggested challenges
    findings["suggested_challenges"] = generate_suggested_challenges(findings)

    # Summary stats
    findings["summary"] = {
        "code_markers_found": len(findings["code_markers"]),
        "large_files_found": len(findings["large_files"]),
        "archive_patterns_found": len(findings["archive_patterns"]),
        "state_issues_found": len(findings["state_patterns"]),
        "challenges_generated": len(findings["suggested_challenges"])
    }

    return findings


# =============================================================================
# RESULT FORMATTING
# =============================================================================

def format_scan_results(findings):
    """
    Format scan findings for display.
    Returns formatted string.
    """
    lines = []
    lines.append("=" * 59)
    lines.append("PROJECT IMPROVEMENT SCAN")
    lines.append("=" * 59)
    lines.append("")

    lines.append(f"Scanned at: {findings.get('timestamp', 'Unknown')}")
    lines.append("")

    lines.append("FINDINGS:")
    lines.append("")

    # Code markers
    markers = findings.get("code_markers", [])
    if markers:
        lines.append("Code Quality Issues:")
        for m in markers[:10]:  # Limit display
            lines.append(f"  [{m['marker']}] {m['file']}:{m['line']}")
            if m.get('text'):
                lines.append(f"    {m['text'][:60]}...")
        if len(markers) > 10:
            lines.append(f"  ... and {len(markers) - 10} more")
        lines.append("")
    else:
        lines.append("Code Quality: No TODO/FIXME markers found")
        lines.append("")

    # Large files
    large = findings.get("large_files", [])
    if large:
        lines.append("Complexity Concerns:")
        for f in large[:5]:
            lines.append(f"  {f['file']} - {f['lines']} lines ({f['priority']} priority)")
        lines.append("")

    # Archive patterns
    archive = findings.get("archive_patterns", [])
    if archive:
        lines.append("Recurring Patterns from History:")
        for p in archive:
            lines.append(f"  {p['description']}")
        lines.append("")

    # State patterns
    state_patterns = findings.get("state_patterns", [])
    if state_patterns:
        lines.append("Current State Issues:")
        for p in state_patterns:
            lines.append(f"  {p['description']}")
        lines.append("")

    # Suggested challenges
    challenges = findings.get("suggested_challenges", [])
    if challenges:
        lines.append("-" * 59)
        lines.append("SUGGESTED CHALLENGES:")
        lines.append("")
        for i, c in enumerate(challenges, 1):
            lines.append(f"  {i}. {c}")
        lines.append("")

    lines.append("=" * 59)
    lines.append("Select a challenge number, or provide your own topic.")
    lines.append("=" * 59)

    return "\n".join(lines)
