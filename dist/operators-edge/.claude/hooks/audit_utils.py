#!/usr/bin/env python3
"""
Operator's Edge - Audit Utilities (v3.6)
Scan codebase for lesson violations and infer audit patterns.

This module enables "Lessons as Living Audits" - lessons that can
automatically scan the codebase for violations of their wisdom.
"""

import re
import os
from pathlib import Path
from typing import List, Dict, Optional, Tuple
from datetime import datetime

from state_utils import get_project_dir
from scout_config import SKIP_DIRECTORIES, SCANNABLE_EXTENSIONS


# =============================================================================
# AUDIT PATTERN INFERENCE
# =============================================================================

# Keywords that suggest a lesson is about code patterns (and thus auditable)
CODE_RELATED_KEYWORDS = {
    # Languages/tools
    "python", "javascript", "typescript", "bash", "git", "npm", "pip",
    # Code concepts
    "import", "function", "class", "variable", "path", "file", "module",
    "pathlib", "os.path", "require", "async", "await",
    # Patterns
    "pattern", "syntax", "format", "naming", "convention",
    # Anti-patterns
    "avoid", "don't use", "instead of", "rather than", "not",
}

# Common anti-patterns and their regex equivalents
KNOWN_ANTI_PATTERNS = {
    # Python path handling
    "os.path": r"os\.path\.(join|dirname|basename|exists|isfile|isdir)",
    "string concatenation for paths": r"['\"][^'\"]+[/\\][^'\"]+['\"]",
    # Imports
    "relative import": r"from \.\.",
    "star import": r"from .+ import \*",
    # Python 2 vs 3
    "print statement": r"\bprint\s+['\"]",
    # Common issues
    "bare except": r"except\s*:",
    "eval(": r"\beval\s*\(",
    "exec(": r"\bexec\s*\(",
}


def _is_code_related(text: str) -> bool:
    """Check if text contains code-related keywords."""
    return any(kw in text for kw in CODE_RELATED_KEYWORDS)


def _match_known_anti_pattern(text: str) -> Optional[str]:
    """Check for known anti-patterns and return regex if found."""
    for anti_pattern, regex in KNOWN_ANTI_PATTERNS.items():
        if anti_pattern.lower() in text:
            return regex
    return None


def _extract_instead_of_pattern(text: str) -> Optional[str]:
    """Extract pattern from 'instead of X' phrase."""
    match = re.search(r"instead of\s+['\"]?(\w+(?:\.\w+)?)['\"]?", text)
    if match:
        return re.escape(match.group(1))
    return None


def _extract_avoid_pattern(text: str) -> Optional[str]:
    """Extract pattern from 'don't use X' or 'avoid X' phrase."""
    match = re.search(r"(?:don't use|avoid|never use)\s+['\"]?(\w+(?:\.\w+)?)['\"]?", text)
    if match:
        return re.escape(match.group(1))
    return None


def _extract_quoted_code_reference(text: str) -> Optional[str]:
    """Extract code references from quoted strings (e.g., 'os.path')."""
    match = re.search(r"['\"](\w+(?:\.\w+)+)['\"]", text)
    if match and "." in match.group(1):
        return re.escape(match.group(1))
    return None


def infer_audit_pattern(lesson_text: str, trigger: str) -> Optional[str]:
    """
    Infer a regex audit pattern from a lesson's text and trigger.

    Only returns a pattern if the lesson appears to be about code patterns.
    Returns None for meta-lessons or non-technical lessons.

    Args:
        lesson_text: The lesson content
        trigger: The lesson's trigger keywords

    Returns:
        A regex pattern string, or None if not inferable
    """
    combined = f"{trigger} {lesson_text}".lower()

    # Early return if not code-related
    if not _is_code_related(combined):
        return None

    # Try each extraction strategy in order of specificity
    return (
        _match_known_anti_pattern(combined) or
        _extract_instead_of_pattern(combined) or
        _extract_avoid_pattern(combined) or
        _extract_quoted_code_reference(lesson_text)
    )


def infer_audit_scope(lesson_text: str, trigger: str) -> List[str]:
    """
    Infer file scope for auditing based on lesson content.

    Args:
        lesson_text: The lesson content
        trigger: The lesson's trigger keywords

    Returns:
        List of file glob patterns (e.g., ["*.py"])
    """
    combined = f"{trigger} {lesson_text}".lower()

    scopes = []

    # Language-specific scopes
    if any(kw in combined for kw in ["python", "pathlib", "import", "pip", ".py"]):
        scopes.append("*.py")

    if any(kw in combined for kw in ["javascript", "typescript", "npm", "require", ".js", ".ts"]):
        scopes.extend(["*.js", "*.ts", "*.jsx", "*.tsx"])

    if any(kw in combined for kw in ["bash", "shell", "script", ".sh"]):
        scopes.append("*.sh")

    if any(kw in combined for kw in ["yaml", "yml", "config"]):
        scopes.extend(["*.yaml", "*.yml"])

    if any(kw in combined for kw in ["json", "package.json"]):
        scopes.append("*.json")

    # Default to Python if no specific scope found but lesson is code-related
    if not scopes and any(kw in combined for kw in CODE_RELATED_KEYWORDS):
        scopes.append("*.py")

    return scopes


# =============================================================================
# VIOLATION SCANNING
# =============================================================================

def scan_for_violations(
    pattern: str,
    scope: List[str] = None,
    project_dir: Path = None,
    max_results: int = 10
) -> List[Dict]:
    """
    Scan the codebase for pattern violations.

    Args:
        pattern: Regex pattern to search for
        scope: File globs to limit scan (e.g., ["*.py"])
        project_dir: Project root (defaults to current project)
        max_results: Maximum violations to return

    Returns:
        List of violation dicts with location, context, and match info
    """
    if project_dir is None:
        project_dir = get_project_dir()

    violations = []

    try:
        regex = re.compile(pattern, re.IGNORECASE)
    except re.error:
        return []  # Invalid pattern

    # Determine which files to scan
    files_to_scan = _get_files_to_scan(project_dir, scope)

    for file_path in files_to_scan:
        if len(violations) >= max_results:
            break

        file_violations = _scan_file(file_path, regex, project_dir)
        violations.extend(file_violations[:max_results - len(violations)])

    return violations


def _get_files_to_scan(project_dir: Path, scope: List[str] = None) -> List[Path]:
    """Get list of files to scan based on scope."""
    files = []

    # If no scope, use all scannable extensions
    if not scope:
        scope = [f"*{ext}" for ext in SCANNABLE_EXTENSIONS]

    for root, dirs, filenames in os.walk(project_dir):
        # Skip ignored directories
        dirs[:] = [d for d in dirs if d not in SKIP_DIRECTORIES]

        root_path = Path(root)
        for filename in filenames:
            file_path = root_path / filename

            # Check if file matches any scope pattern
            for pattern in scope:
                if file_path.match(pattern):
                    files.append(file_path)
                    break

    return files


def _scan_file(file_path: Path, regex: re.Pattern, project_dir: Path) -> List[Dict]:
    """Scan a single file for pattern matches."""
    violations = []

    try:
        content = file_path.read_text(encoding='utf-8', errors='ignore')
    except (OSError, IOError):
        return []

    lines = content.split('\n')
    rel_path = file_path.relative_to(project_dir)

    for line_num, line in enumerate(lines, 1):
        matches = regex.finditer(line)
        for match in matches:
            violations.append({
                "location": f"{rel_path}:{line_num}",
                "line": line.strip()[:100],  # Truncate long lines
                "match": match.group(0),
                "column": match.start() + 1,
            })

    return violations


# =============================================================================
# AUDIT EXECUTION
# =============================================================================

def audit_lesson(lesson: Dict, project_dir: Path = None) -> Dict:
    """
    Run an audit for a single lesson.

    Args:
        lesson: Lesson dict with audit_pattern
        project_dir: Project root

    Returns:
        Audit result dict with violations and metadata
    """
    pattern = lesson.get("audit_pattern")
    if not pattern:
        return {
            "audited": False,
            "reason": "no_pattern",
        }

    scope = lesson.get("audit_scope", [])
    violations = scan_for_violations(pattern, scope, project_dir)

    return {
        "audited": True,
        "trigger": lesson.get("trigger", "unknown"),
        "pattern": pattern,
        "scope": scope,
        "violations": violations,
        "violation_count": len(violations),
        "timestamp": datetime.now().isoformat(),
    }


def audit_all_lessons(
    lessons: List[Dict],
    project_dir: Path = None,
    max_per_lesson: int = 3
) -> List[Dict]:
    """
    Audit all lessons that have audit patterns.

    Args:
        lessons: List of lesson dicts
        project_dir: Project root
        max_per_lesson: Max violations to return per lesson

    Returns:
        List of findings (violations across all lessons)
    """
    all_findings = []

    # Prioritize high-reinforced lessons
    auditable = [l for l in lessons if l.get("audit_pattern")]
    auditable.sort(key=lambda x: x.get("reinforced", 0), reverse=True)

    for lesson in auditable:
        result = audit_lesson(lesson, project_dir)

        if result.get("violations"):
            # Limit violations per lesson
            for violation in result["violations"][:max_per_lesson]:
                all_findings.append({
                    "type": "lesson_violation",
                    "trigger": lesson.get("trigger"),
                    "lesson": lesson.get("lesson"),
                    "reinforced": lesson.get("reinforced", 0),
                    **violation,
                })

    return all_findings


# =============================================================================
# HELPERS
# =============================================================================

def update_lesson_audit_stats(lesson: Dict, audit_result: Dict) -> Dict:
    """
    Update a lesson dict with audit results.

    Args:
        lesson: The lesson to update
        audit_result: Result from audit_lesson()

    Returns:
        Updated lesson dict (modified in place)
    """
    if audit_result.get("audited"):
        lesson["last_audit"] = audit_result.get("timestamp", datetime.now().isoformat())
        lesson["violations_found"] = audit_result.get("violation_count", 0)

    return lesson


def get_auditable_lessons(lessons: List[Dict]) -> List[Dict]:
    """Get lessons that have audit capability."""
    return [l for l in lessons if l.get("audit_pattern")]


def get_lessons_needing_audit(lessons: List[Dict], days_threshold: int = 7) -> List[Dict]:
    """Get lessons that are due for an audit."""
    now = datetime.now()
    needing_audit = []

    for lesson in lessons:
        if not lesson.get("audit_pattern"):
            continue

        last_audit = lesson.get("last_audit")
        if not last_audit:
            needing_audit.append(lesson)
            continue

        try:
            last = datetime.fromisoformat(last_audit)
            days_since = (now - last).days
            if days_since >= days_threshold:
                needing_audit.append(lesson)
        except (ValueError, TypeError):
            needing_audit.append(lesson)

    return needing_audit
