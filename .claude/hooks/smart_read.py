#!/usr/bin/env python3
"""
Operator's Edge v8.0 - Smart Read (Phase 10.2)

RLM-Inspired: Instead of reading entire large files into context,
suggest targeted approaches using REPL capabilities Claude already has.

The Problem:
- Claude reads 5000-line file → context bloat
- Most of those lines aren't relevant
- Claude already has grep/head/tail access but doesn't always use it

The Solution:
- Detect large file reads before they happen
- Suggest targeted approaches based on file type
- At higher intervention levels, inject as strong recommendation

"Read less, understand more."
"""
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Optional, List, Tuple


# =============================================================================
# CONFIGURATION
# =============================================================================

# Thresholds for suggestions
LINE_THRESHOLD_SUGGEST = 500      # Suggest smart read above this
LINE_THRESHOLD_WARN = 2000        # Stronger warning above this
LINE_THRESHOLD_CRITICAL = 5000    # Critical warning above this

# File type patterns for targeted suggestions
FILE_TYPE_SUGGESTIONS = {
    # Python files
    ".py": [
        "grep -n 'def \\|class ' {file} | head -50  # See structure",
        "grep -n 'import\\|from.*import' {file}  # See dependencies",
        "head -100 {file}  # See module docstring and initial code",
    ],
    # JavaScript/TypeScript
    ".js": [
        "grep -n 'function\\|const.*=.*=>\\|export' {file} | head -50  # See functions",
        "head -100 {file}  # See imports and initial code",
    ],
    ".ts": [
        "grep -n 'function\\|interface\\|class\\|export' {file} | head -50  # See structure",
        "head -100 {file}  # See imports and types",
    ],
    ".tsx": [
        "grep -n 'function\\|const.*=.*=>\\|interface\\|export' {file} | head -50",
        "head -100 {file}  # See component structure",
    ],
    # Config files
    ".json": [
        "head -50 {file}  # See schema structure",
        "python -c \"import json; d=json.load(open('{file}')); print(list(d.keys())[:20])\"  # See top-level keys",
    ],
    ".yaml": [
        "head -80 {file}  # See structure",
        "grep -n '^[a-zA-Z]' {file} | head -30  # See top-level keys",
    ],
    ".yml": [
        "head -80 {file}  # See structure",
        "grep -n '^[a-zA-Z]' {file} | head -30  # See top-level keys",
    ],
    # Log files
    ".log": [
        "tail -100 {file}  # See recent entries",
        "grep -i 'error\\|exception\\|fail' {file} | tail -50  # See errors",
        "wc -l {file}  # See total lines",
    ],
    # Markdown/docs
    ".md": [
        "grep -n '^#' {file}  # See section headers",
        "head -100 {file}  # See introduction",
    ],
    # HTML
    ".html": [
        "grep -n '<h[1-6]\\|<div.*id=\\|<section' {file} | head -30  # See structure",
        "head -100 {file}  # See head and initial body",
    ],
    # CSS
    ".css": [
        "grep -n '^\\.' {file} | head -50  # See class definitions",
        "grep -n '^#' {file} | head -30  # See ID definitions",
    ],
    # SQL
    ".sql": [
        "grep -ni 'CREATE TABLE\\|ALTER TABLE\\|CREATE INDEX' {file}  # See schema",
        "head -100 {file}  # See initial statements",
    ],
    # Shell scripts
    ".sh": [
        "grep -n '^function\\|^[a-zA-Z_]*()' {file}  # See functions",
        "head -50 {file}  # See shebang and setup",
    ],
    ".bash": [
        "grep -n '^function\\|^[a-zA-Z_]*()' {file}  # See functions",
        "head -50 {file}  # See shebang and setup",
    ],
    # Go
    ".go": [
        "grep -n '^func\\|^type' {file} | head -50  # See functions and types",
        "head -50 {file}  # See package and imports",
    ],
    # Rust
    ".rs": [
        "grep -n '^fn\\|^struct\\|^enum\\|^impl' {file} | head -50  # See structure",
        "head -50 {file}  # See module and use statements",
    ],
    # Java
    ".java": [
        "grep -n 'class\\|interface\\|public.*void\\|public.*static' {file} | head -50",
        "head -50 {file}  # See package and imports",
    ],
}

# Generic suggestions for unknown file types
GENERIC_SUGGESTIONS = [
    "head -100 {file}  # See beginning",
    "tail -50 {file}  # See end",
    "wc -l {file}  # Count lines",
    "grep -n 'TODO\\|FIXME\\|XXX' {file}  # Find markers",
]


# =============================================================================
# DATA STRUCTURES
# =============================================================================

@dataclass
class SmartReadSuggestion:
    """A smart read suggestion for a file."""
    file_path: str
    line_count: int
    severity: str  # "info", "warning", "critical"
    suggestions: List[str]
    message: str


# =============================================================================
# CORE FUNCTIONS
# =============================================================================

def get_file_line_count(file_path: str) -> Optional[int]:
    """
    Get the line count of a file.

    Returns None if file doesn't exist or can't be read.
    """
    try:
        path = Path(file_path)
        if not path.exists() or not path.is_file():
            return None

        # Quick line count without loading entire file
        with open(path, 'r', errors='ignore') as f:
            return sum(1 for _ in f)
    except (OSError, IOError):
        return None


def get_file_extension(file_path: str) -> str:
    """Get lowercase file extension."""
    return Path(file_path).suffix.lower()


def get_suggestions_for_file(file_path: str) -> List[str]:
    """
    Get appropriate suggestions based on file type.

    Returns list of shell commands with {file} placeholder.
    """
    ext = get_file_extension(file_path)

    # Get file-specific suggestions or fall back to generic
    suggestions = FILE_TYPE_SUGGESTIONS.get(ext, GENERIC_SUGGESTIONS)

    # Replace placeholder with actual file path
    # Quote the path to handle spaces
    quoted_path = f'"{file_path}"'
    return [s.format(file=quoted_path) for s in suggestions]


def determine_severity(line_count: int) -> str:
    """Determine severity based on line count."""
    if line_count >= LINE_THRESHOLD_CRITICAL:
        return "critical"
    elif line_count >= LINE_THRESHOLD_WARN:
        return "warning"
    elif line_count >= LINE_THRESHOLD_SUGGEST:
        return "info"
    return "none"


def should_suggest_smart_read(file_path: str) -> Tuple[bool, Optional[int]]:
    """
    Check if we should suggest a smart read approach.

    Returns (should_suggest, line_count).
    """
    line_count = get_file_line_count(file_path)

    if line_count is None:
        return False, None

    return line_count >= LINE_THRESHOLD_SUGGEST, line_count


def generate_smart_read_suggestion(file_path: str) -> Optional[SmartReadSuggestion]:
    """
    Generate a smart read suggestion for a file.

    Returns None if file is small enough to read directly.
    """
    should_suggest, line_count = should_suggest_smart_read(file_path)

    if not should_suggest or line_count is None:
        return None

    severity = determine_severity(line_count)
    suggestions = get_suggestions_for_file(file_path)

    # Generate message based on severity
    file_name = Path(file_path).name

    if severity == "critical":
        message = f"⚠️ LARGE FILE: {file_name} has {line_count:,} lines - reading entirely will consume significant context"
    elif severity == "warning":
        message = f"📄 {file_name} has {line_count:,} lines - consider targeted reads"
    else:
        message = f"💡 {file_name} has {line_count:,} lines - targeted reads may be more efficient"

    return SmartReadSuggestion(
        file_path=file_path,
        line_count=line_count,
        severity=severity,
        suggestions=suggestions,
        message=message
    )


# =============================================================================
# FORMATTING
# =============================================================================

def format_smart_read_suggestion(suggestion: SmartReadSuggestion, intervention_level: str = "advise") -> str:
    """
    Format a smart read suggestion for display.

    intervention_level affects formatting:
    - "observe": No suggestion shown
    - "advise": Gentle suggestion
    - "guide": Prominent recommendation
    - "intervene": Strong warning
    """
    if intervention_level == "observe":
        return ""

    lines = []

    # Header based on severity and intervention level
    if intervention_level == "intervene" or suggestion.severity == "critical":
        lines.append("╭─ ⚠️ SMART READ RECOMMENDED ─────────────────────╮")
    elif intervention_level == "guide" or suggestion.severity == "warning":
        lines.append("╭─ 📖 SMART READ SUGGESTION ──────────────────────╮")
    else:
        lines.append("╭─ 💡 TIP ────────────────────────────────────────╮")

    # Message
    lines.append(f"│ {suggestion.message}")
    lines.append("│")
    lines.append("│ Try one of these targeted approaches:")

    # Suggestions (limit to 3)
    for i, cmd in enumerate(suggestion.suggestions[:3], 1):
        # Truncate long commands
        if len(cmd) > 60:
            cmd = cmd[:57] + "..."
        lines.append(f"│   {i}. {cmd}")

    # Footer with context impact
    context_estimate = suggestion.line_count * 40  # ~40 chars per line average
    context_kb = context_estimate / 1024
    lines.append("│")
    lines.append(f"│ Full read ≈ {context_kb:.0f}KB context | Targeted ≈ 5-10KB")
    lines.append("╰────────────────────────────────────────────────────╯")

    return "\n".join(lines)


def format_compact_suggestion(suggestion: SmartReadSuggestion) -> str:
    """Format a compact one-line suggestion."""
    return f"💡 {Path(suggestion.file_path).name}: {suggestion.line_count:,} lines - try `head -100` or `grep` first"


# =============================================================================
# INTEGRATION HELPER
# =============================================================================

def check_read_and_suggest(
    file_path: str,
    intervention_level: str = "advise"
) -> Optional[str]:
    """
    Main integration point for pre_tool.py.

    Returns formatted suggestion string or None.
    """
    suggestion = generate_smart_read_suggestion(file_path)

    if suggestion is None:
        return None

    return format_smart_read_suggestion(suggestion, intervention_level)


# =============================================================================
# QUICK TEST
# =============================================================================

if __name__ == "__main__":
    print("Smart Read - Self Test")
    print("=" * 50)

    # Test with this file
    test_file = __file__
    line_count = get_file_line_count(test_file)
    print(f"\nThis file ({Path(test_file).name}): {line_count} lines")

    # Test suggestion generation
    suggestion = generate_smart_read_suggestion(test_file)
    if suggestion:
        print(f"Would suggest: {suggestion.severity}")
        print(format_smart_read_suggestion(suggestion))
    else:
        print("No suggestion needed (file is small)")

    # Test with a hypothetically large file
    print("\n--- Simulated Large Python File ---")
    mock_suggestion = SmartReadSuggestion(
        file_path="/project/src/big_module.py",
        line_count=3500,
        severity="warning",
        suggestions=get_suggestions_for_file("/project/src/big_module.py"),
        message="📄 big_module.py has 3,500 lines - consider targeted reads"
    )
    print(format_smart_read_suggestion(mock_suggestion, "guide"))

    print("\n--- Simulated Critical JSON File ---")
    mock_json = SmartReadSuggestion(
        file_path="/project/data/large_config.json",
        line_count=8000,
        severity="critical",
        suggestions=get_suggestions_for_file("/project/data/large_config.json"),
        message="⚠️ LARGE FILE: large_config.json has 8,000 lines"
    )
    print(format_smart_read_suggestion(mock_json, "intervene"))

    print("\nSelf-test complete.")
