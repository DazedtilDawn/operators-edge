#!/usr/bin/env python3
"""
Operator's Edge - Scout Mode Scanner
Autonomous codebase exploration to surface actionable findings.

This scanner runs when Dispatch Mode has no objective, looking for:
- TODO/FIXME comments
- Large files that might need refactoring
- Missing tests
- Other improvement opportunities
"""

import os
import re
import time
from pathlib import Path
from typing import List, Optional, Tuple
from datetime import datetime

from scout_config import (
    ScoutFinding,
    FindingType,
    FindingPriority,
    TODO_PATTERNS,
    SCANNABLE_EXTENSIONS,
    SKIP_DIRECTORIES,
    SCOUT_THRESHOLDS,
    TYPE_PRIORITY_BOOST,
    sort_findings,
)


# =============================================================================
# FILE DISCOVERY
# =============================================================================

def discover_files(root_path: Path, max_files: int = None) -> List[Path]:
    """
    Discover scannable files in the project.

    Args:
        root_path: Project root directory
        max_files: Maximum files to return (for time-boxing)

    Returns:
        List of file paths to scan
    """
    if max_files is None:
        max_files = SCOUT_THRESHOLDS["max_files_to_scan"]

    files = []

    for root, dirs, filenames in os.walk(root_path):
        # Filter out skip directories in-place
        dirs[:] = [d for d in dirs if d not in SKIP_DIRECTORIES]

        for filename in filenames:
            # Check extension
            ext = Path(filename).suffix.lower()
            if ext not in SCANNABLE_EXTENSIONS:
                continue

            filepath = Path(root) / filename
            files.append(filepath)

            if len(files) >= max_files:
                return files

    return files


# =============================================================================
# TODO/FIXME SCANNER
# =============================================================================

def scan_todos(filepath: Path) -> List[ScoutFinding]:
    """
    Scan a file for TODO/FIXME comments.

    Returns list of findings for each TODO found.
    """
    findings = []

    try:
        content = filepath.read_text(encoding='utf-8', errors='ignore')
        lines = content.split('\n')

        for line_num, line in enumerate(lines, 1):
            for pattern in TODO_PATTERNS:
                if re.search(pattern, line, re.IGNORECASE):
                    # Extract the TODO message
                    match = re.search(r'(TODO|FIXME|HACK|XXX)[:\s]*(.+)', line, re.IGNORECASE)
                    message = match.group(2).strip() if match else line.strip()

                    # Determine priority based on keyword
                    todo_type = match.group(1).upper() if match else "TODO"
                    priority = FindingPriority.HIGH if todo_type == "FIXME" else FindingPriority.MEDIUM

                    finding = ScoutFinding(
                        type=FindingType.TODO,
                        priority=priority,
                        title=f"{todo_type}: {message[:60]}{'...' if len(message) > 60 else ''}",
                        description=f"Found {todo_type} comment that may need attention",
                        location=f"{filepath}:{line_num}",
                        context=line.strip()[:100],
                        suggested_action=f"Address the {todo_type} comment"
                    )
                    findings.append(finding)
                    break  # Only one finding per line

    except Exception as e:
        pass  # Skip files we can't read

    return findings


# =============================================================================
# LARGE FILE SCANNER
# =============================================================================

def scan_large_files(files: List[Path]) -> List[ScoutFinding]:
    """
    Find files exceeding the line count threshold.

    Large files often benefit from refactoring or splitting.
    """
    findings = []
    threshold = SCOUT_THRESHOLDS["large_file_lines"]

    for filepath in files:
        try:
            content = filepath.read_text(encoding='utf-8', errors='ignore')
            line_count = content.count('\n') + 1

            if line_count > threshold:
                finding = ScoutFinding(
                    type=FindingType.LARGE_FILE,
                    priority=FindingPriority.LOW,
                    title=f"Large file: {filepath.name} ({line_count} lines)",
                    description=f"File exceeds {threshold} line threshold, may benefit from refactoring",
                    location=str(filepath),
                    context=f"{line_count} lines total",
                    suggested_action="Consider splitting into smaller modules"
                )
                findings.append(finding)

        except Exception:
            pass

    return findings


# =============================================================================
# CYCLOMATIC COMPLEXITY SCANNER
# =============================================================================

# Patterns that indicate branching (roughly approximates cyclomatic complexity)
COMPLEXITY_PATTERNS = [
    r'\bif\b',
    r'\belif\b',
    r'\bfor\b',
    r'\bwhile\b',
    r'\btry\b',
    r'\bexcept\b',
    r'\band\b',
    r'\bor\b',
    r'\?\s*:',  # Ternary operator
    r'\bcatch\b',
    r'\bcase\b',
]

COMPLEXITY_THRESHOLD = 15  # Functions with higher complexity get flagged


def extract_python_functions(content: str) -> List[Tuple[str, int, int]]:
    """
    Extract function definitions from Python code.

    Returns list of (function_name, start_line, end_line).
    """
    functions = []
    lines = content.split('\n')
    current_func = None
    current_indent = 0

    for i, line in enumerate(lines, 1):
        # Detect function definition
        match = re.match(r'^(\s*)def\s+(\w+)\s*\(', line)
        if match:
            # Close previous function if any
            if current_func:
                functions.append((current_func[0], current_func[1], i - 1))

            indent = len(match.group(1))
            func_name = match.group(2)
            current_func = (func_name, i)
            current_indent = indent
        elif current_func:
            # Check if we've left the function (dedent)
            stripped = line.lstrip()
            if stripped and not stripped.startswith('#'):
                current_line_indent = len(line) - len(line.lstrip())
                if current_line_indent <= current_indent and not line.strip() == '':
                    functions.append((current_func[0], current_func[1], i - 1))
                    current_func = None

    # Close final function
    if current_func:
        functions.append((current_func[0], current_func[1], len(lines)))

    return functions


def calculate_complexity(code_block: str) -> int:
    """
    Estimate cyclomatic complexity of a code block.

    Uses a simplified pattern-matching approach.
    Actual complexity = edges - nodes + 2, but this approximation works well.
    """
    complexity = 1  # Base complexity

    for pattern in COMPLEXITY_PATTERNS:
        matches = re.findall(pattern, code_block)
        complexity += len(matches)

    return complexity


def scan_complexity(filepath: Path) -> List[ScoutFinding]:
    """
    Scan for functions with high cyclomatic complexity.

    Only supports Python files currently.
    """
    findings = []

    if filepath.suffix.lower() != '.py':
        return findings

    try:
        content = filepath.read_text(encoding='utf-8', errors='ignore')
        lines = content.split('\n')
        functions = extract_python_functions(content)

        for func_name, start_line, end_line in functions:
            # Extract function body
            func_body = '\n'.join(lines[start_line-1:end_line])
            complexity = calculate_complexity(func_body)

            if complexity > COMPLEXITY_THRESHOLD:
                finding = ScoutFinding(
                    type=FindingType.COMPLEXITY,
                    priority=FindingPriority.MEDIUM if complexity < 25 else FindingPriority.HIGH,
                    title=f"High complexity: {func_name}() (score: {complexity})",
                    description=f"Function has cyclomatic complexity of {complexity}, threshold is {COMPLEXITY_THRESHOLD}",
                    location=f"{filepath}:{start_line}",
                    context=f"Lines {start_line}-{end_line} ({end_line - start_line + 1} lines)",
                    suggested_action="Consider breaking into smaller functions"
                )
                findings.append(finding)

    except Exception:
        pass

    return findings


# =============================================================================
# DEAD CODE SCANNER
# =============================================================================

def scan_dead_code(filepath: Path) -> List[ScoutFinding]:
    """
    Scan for potentially dead code.

    Currently detects:
    - Unused imports (Python only)
    - Functions that are defined but never called within the file
    """
    findings = []

    if filepath.suffix.lower() != '.py':
        return findings

    try:
        content = filepath.read_text(encoding='utf-8', errors='ignore')

        # Find imports
        import_pattern = r'^(?:from\s+\S+\s+)?import\s+(.+?)(?:\s+as\s+\w+)?$'
        imports = set()
        import_lines = {}

        for i, line in enumerate(content.split('\n'), 1):
            line = line.strip()
            match = re.match(import_pattern, line)
            if match:
                # Extract imported names
                import_str = match.group(1)
                # Handle "import a, b, c" and "from x import a, b, c"
                for item in import_str.split(','):
                    item = item.strip()
                    # Handle "import x as y" -> use y
                    if ' as ' in item:
                        item = item.split(' as ')[1].strip()
                    if item and not item.startswith('('):
                        imports.add(item)
                        import_lines[item] = i

        # Check each import for usage
        # Remove the import lines from content for checking
        for imported_name in imports:
            # Skip common re-exports and dunder imports
            if imported_name.startswith('_') or imported_name in ['*', 'annotations']:
                continue

            # Count usages (excluding the import line itself)
            usage_pattern = rf'\b{re.escape(imported_name)}\b'
            usages = len(re.findall(usage_pattern, content))

            # If only 1 usage (the import itself) or 0, it might be unused
            if usages <= 1:
                line_num = import_lines.get(imported_name, 1)
                finding = ScoutFinding(
                    type=FindingType.DEAD_CODE,
                    priority=FindingPriority.LOW,
                    title=f"Potentially unused import: {imported_name}",
                    description=f"Import '{imported_name}' appears unused in this file",
                    location=f"{filepath}:{line_num}",
                    suggested_action="Remove unused import if not needed for re-export"
                )
                findings.append(finding)

    except Exception:
        pass

    return findings


# =============================================================================
# MISSING TEST SCANNER
# =============================================================================

def scan_missing_tests(files: List[Path], root_path: Path) -> List[ScoutFinding]:
    """
    Find source files without corresponding test files.

    Looks for patterns like:
    - foo.py should have test_foo.py or foo_test.py
    - bar.ts should have bar.test.ts or bar.spec.ts
    """
    findings = []

    # Build set of test file basenames
    test_patterns = set()
    for f in files:
        name = f.stem.lower()
        if name.startswith('test_') or name.endswith('_test') or \
           name.endswith('.test') or name.endswith('.spec'):
            # Extract the base name being tested
            base = name.replace('test_', '').replace('_test', '')
            base = base.replace('.test', '').replace('.spec', '')
            test_patterns.add(base)

    # Find source files without tests
    for filepath in files:
        # Skip test files themselves
        name = filepath.stem.lower()
        if 'test' in name or 'spec' in name:
            continue

        # Skip non-code files
        if filepath.suffix.lower() not in ['.py', '.js', '.ts', '.tsx', '.jsx', '.go', '.rs']:
            continue

        # Skip small files (probably not worth testing)
        try:
            content = filepath.read_text(encoding='utf-8', errors='ignore')
            if content.count('\n') < 20:
                continue
        except Exception:
            continue

        # Check if there's a corresponding test
        if name not in test_patterns:
            # Check it's not in common untested directories
            path_str = str(filepath).lower()
            if any(skip in path_str for skip in ['config', 'types', 'constants', 'migrations']):
                continue

            finding = ScoutFinding(
                type=FindingType.MISSING_TEST,
                priority=FindingPriority.MEDIUM,
                title=f"No tests for {filepath.name}",
                description="Source file has no corresponding test file detected",
                location=str(filepath),
                suggested_action=f"Create test file: test_{filepath.stem}{filepath.suffix}"
            )
            findings.append(finding)

    return findings


# =============================================================================
# UNVERIFIED COMPLETION SCANNER (v3.9.2)
# =============================================================================

def scan_unverified_completions(state: dict, files: List[Path]) -> List[ScoutFinding]:
    """
    Scan for completed plan steps with verification criteria but no matching test.

    This catches the case where:
    - A step was marked "completed"
    - The step had a "verification" field specifying expected behavior
    - But no test file contains text matching that verification

    Args:
        state: The active_context state containing plan
        files: List of project files (used to find test files)

    Returns:
        List of ScoutFindings for unverified completions
    """
    findings = []

    if not state or not isinstance(state, dict):
        return findings

    plan = state.get("plan", [])
    if not plan:
        return findings

    # Find test files
    test_files = [f for f in files if 'test' in f.name.lower()]

    # Build a searchable corpus of test content
    test_content = ""
    for tf in test_files:
        try:
            test_content += tf.read_text(encoding='utf-8', errors='ignore').lower()
        except Exception:
            pass

    # Check each completed step with verification
    for i, step in enumerate(plan):
        if not isinstance(step, dict):
            continue

        status = step.get("status", "")
        verification = step.get("verification", "")

        if status != "completed" or not verification:
            continue

        # Search for verification keywords in test files
        # Extract key words from verification (ignore common words)
        verification_lower = verification.lower()
        keywords = _extract_verification_keywords(verification_lower)

        # Check if any keywords appear in test content
        matches = sum(1 for kw in keywords if kw in test_content)
        match_ratio = matches / len(keywords) if keywords else 0

        # If less than 50% of keywords found, flag as unverified
        if match_ratio < 0.5:
            description = step.get("description", f"Step {i+1}")
            finding = ScoutFinding(
                type=FindingType.UNVERIFIED_COMPLETION,
                priority=FindingPriority.MEDIUM,
                title=f"Unverified completion: {description[:50]}",
                description=f"Step completed with verification criteria, but no matching test found",
                location=f"active_context.yaml:plan[{i}]",
                context=verification[:100],  # Store the verification criteria
                suggested_action=f"Write test that verifies: {verification[:80]}"
            )
            findings.append(finding)

    return findings


def _extract_verification_keywords(text: str) -> List[str]:
    """
    Extract meaningful keywords from verification text.

    Filters out common words to focus on domain-specific terms.
    """
    # Common words to ignore
    stop_words = {
        'a', 'an', 'the', 'is', 'are', 'was', 'were', 'be', 'been', 'being',
        'have', 'has', 'had', 'do', 'does', 'did', 'will', 'would', 'could',
        'should', 'may', 'might', 'must', 'shall', 'can', 'need', 'to', 'of',
        'in', 'for', 'on', 'with', 'at', 'by', 'from', 'as', 'into', 'through',
        'during', 'before', 'after', 'above', 'below', 'between', 'under',
        'again', 'further', 'then', 'once', 'here', 'there', 'when', 'where',
        'why', 'how', 'all', 'each', 'every', 'both', 'few', 'more', 'most',
        'other', 'some', 'such', 'no', 'nor', 'not', 'only', 'own', 'same',
        'so', 'than', 'too', 'very', 'just', 'and', 'but', 'if', 'or', 'because',
        'until', 'while', 'that', 'this', 'these', 'those', 'it', 'its',
        'returns', 'return', 'valid', 'invalid', 'correct', 'correctly',
        'should', 'must', 'works', 'work', 'test', 'tests', 'check', 'verify'
    }

    # Split on non-alphanumeric and filter
    words = re.split(r'[^a-z0-9]+', text)
    keywords = [w for w in words if w and len(w) > 2 and w not in stop_words]

    return keywords


# =============================================================================
# LESSON VIOLATION SCANNER (v3.6)
# =============================================================================

def scan_lesson_violations(lessons: List[dict], root_path: Path) -> List[ScoutFinding]:
    """
    Scan for code that violates learned lessons.

    Only scans lessons that have an audit_pattern defined.
    Prioritizes high-reinforced lessons.

    Args:
        lessons: List of lesson dicts from state['memory']
        root_path: Project root

    Returns:
        List of ScoutFindings for violations
    """
    from audit_utils import scan_for_violations

    findings = []

    # Filter to auditable lessons and sort by reinforcement
    auditable = [l for l in lessons if isinstance(l, dict) and l.get("audit_pattern")]
    auditable.sort(key=lambda x: x.get("reinforced", 0), reverse=True)

    # Limit to top 5 most reinforced lessons to avoid scan overhead
    for lesson in auditable[:5]:
        pattern = lesson.get("audit_pattern")
        scope = lesson.get("audit_scope", [])
        trigger = lesson.get("trigger", "unknown")
        lesson_text = lesson.get("lesson", "")

        violations = scan_for_violations(pattern, scope, root_path, max_results=3)

        for violation in violations:
            finding = ScoutFinding(
                type=FindingType.LESSON_VIOLATION,
                priority=FindingPriority.MEDIUM if lesson.get("reinforced", 0) < 3 else FindingPriority.HIGH,
                title=f"Lesson violation: {trigger}",
                description=f"Code violates lesson: {lesson_text[:80]}{'...' if len(lesson_text) > 80 else ''}",
                location=violation["location"],
                context=violation.get("line", "")[:100],
                suggested_action=lesson_text
            )
            findings.append(finding)

    return findings


# =============================================================================
# EVAL FAILURE SCANNER (v3.9.7)
# =============================================================================

def scan_eval_failures() -> List[ScoutFinding]:
    """
    Scan .proof/session_log.jsonl for recent eval invariant failures.

    Returns findings for:
    - INV-01 failures (schema validation)
    - INV-02 failures (silent deletions)
    - Any other invariant failures
    """
    findings = []

    try:
        from eval_utils import load_eval_runs
    except ImportError:
        return findings

    runs = load_eval_runs(max_lines=100)

    for run in runs:
        failed = run.get("invariants_failed", [])
        if not failed:
            continue

        tool = run.get("tool", "unknown")
        diff_path = run.get("snapshots", {}).get("diff", "unknown")
        timestamp = run.get("timestamp", "")[:19]
        diff_summary = run.get("diff_summary", {})

        for inv_id in failed:
            finding = ScoutFinding(
                type=FindingType.EVAL_FAILURE,
                priority=FindingPriority.HIGH,
                title=f"Eval invariant {inv_id} failed",
                description=f"Invariant {inv_id} failed during {tool} operation at {timestamp}",
                location=diff_path,
                context=f"Changes: +{diff_summary.get('added', 0)} -{diff_summary.get('removed', 0)} ~{diff_summary.get('changed', 0)}",
                suggested_action=f"Review diff at {diff_path} and resolve the violation"
            )
            findings.append(finding)

    return findings


# =============================================================================
# MAIN SCANNER
# =============================================================================

def run_scout_scan(root_path: Optional[Path] = None, state: dict = None) -> Tuple[List[ScoutFinding], dict]:
    """
    Run a full scout scan on the project.

    Args:
        root_path: Project root (defaults to current directory)
        state: Active context state containing memory/lessons (optional, for v3.6 lesson audits)

    Returns:
        Tuple of (findings list, scan metadata dict)
    """
    if root_path is None:
        root_path = Path.cwd()

    start_time = time.time()
    all_findings = []

    # Discover files
    files = discover_files(root_path)

    # Run scanners (time-boxed by file limit)
    for filepath in files:
        # Scan for TODO/FIXME comments
        all_findings.extend(scan_todos(filepath))

        # Scan for complexity issues (Python only)
        all_findings.extend(scan_complexity(filepath))

        # Scan for dead code (Python only)
        all_findings.extend(scan_dead_code(filepath))

    # Large file scanner
    all_findings.extend(scan_large_files(files))

    # Missing test scanner
    all_findings.extend(scan_missing_tests(files, root_path))

    # Lesson violation scanner (v3.6)
    if state and isinstance(state, dict):
        lessons = state.get("memory", [])
        if lessons:
            all_findings.extend(scan_lesson_violations(lessons, root_path))

    # Unverified completion scanner (v3.9.2)
    if state and isinstance(state, dict):
        all_findings.extend(scan_unverified_completions(state, files))

    # Eval failure scanner (v3.9.7)
    all_findings.extend(scan_eval_failures())

    # Sort by priority
    sorted_findings = sort_findings(all_findings)

    # Limit to max findings
    max_findings = SCOUT_THRESHOLDS["max_findings"]
    if len(sorted_findings) > max_findings:
        sorted_findings = sorted_findings[:max_findings]

    # Calculate metadata
    duration = time.time() - start_time
    metadata = {
        "last_scan": datetime.now().isoformat(),
        "scan_duration_seconds": round(duration, 2),
        "files_scanned": len(files),
        "findings_count": len(sorted_findings),
        "root_path": str(root_path),
    }

    return sorted_findings, metadata


# =============================================================================
# COMBINED SCAN (SCOUT + DISCOVERY)
# =============================================================================

def run_full_scan(root_path: Optional[Path] = None, state: dict = None) -> dict:
    """
    Run both Scout (maintenance) and Discovery (innovation) scans.

    Args:
        root_path: Project root for Scout scan
        state: Current active_context state for Discovery scan

    Returns:
        Combined results with both finding types
    """
    from discovery_scanner import run_discovery_scan, format_discovery_report

    # Run Scout scan (maintenance findings)
    scout_findings, scout_meta = run_scout_scan(root_path, state)

    # Run Discovery scan (innovation findings)
    discovery_findings, discovery_meta = run_discovery_scan(state)

    return {
        "scout": {
            "findings": scout_findings,
            "metadata": scout_meta,
        },
        "discovery": {
            "findings": discovery_findings,
            "metadata": discovery_meta,
        },
        "combined_metadata": {
            "total_findings": len(scout_findings) + len(discovery_findings),
            "scout_count": len(scout_findings),
            "discovery_count": len(discovery_findings),
            "scan_time": scout_meta["scan_duration_seconds"] + discovery_meta["scan_duration_seconds"],
        }
    }


def format_combined_report(scan_results: dict) -> str:
    """Format combined Scout + Discovery report for display."""
    from scout_config import format_finding_for_display
    from discovery_config import format_discovery_for_display

    lines = []

    # Scout findings (maintenance)
    scout_findings = scan_results["scout"]["findings"]
    if scout_findings:
        lines.append("")
        lines.append("MAINTENANCE FINDINGS (what's broken)")
        lines.append("─" * 60)
        for i, finding in enumerate(scout_findings[:5]):  # Limit display
            lines.append(format_finding_for_display(finding, i))
            lines.append("")

    # Discovery findings (innovation)
    discovery_findings = scan_results["discovery"]["findings"]
    if discovery_findings:
        lines.append("")
        lines.append("DISCOVERY FINDINGS (what's missing)")
        lines.append("─" * 60)
        for i, finding in enumerate(discovery_findings[:3]):  # Limit display
            lines.append(format_discovery_for_display(finding, i))
            lines.append("")

    if not scout_findings and not discovery_findings:
        lines.append("")
        lines.append("No findings - codebase is well-maintained and optimized!")

    return '\n'.join(lines)


# =============================================================================
# ENTRY POINT
# =============================================================================

if __name__ == "__main__":
    # Test run
    findings, meta = run_scout_scan()

    print(f"Scout Scan Complete")
    print(f"  Files scanned: {meta['files_scanned']}")
    print(f"  Duration: {meta['scan_duration_seconds']}s")
    print(f"  Findings: {meta['findings_count']}")
    print()

    for i, f in enumerate(findings[:5]):
        print(f"[{i+1}] {f.priority.value.upper()}: {f.title}")
        print(f"    Location: {f.location}")
        print()
