#!/usr/bin/env python3
"""
Operator's Edge - Review Context Gatherer (v4.1)
Collects context for code review: git diff, intent, constraints, patterns.

This module gathers everything the review prompt needs:
- Git diff (capped at token limit)
- Current step intent from plan
- Active constraints
- Relevant patterns from lessons
"""

import subprocess
import re
from typing import Optional, List, Dict, Any
from dataclasses import dataclass, field
from pathlib import Path
from state_utils import get_project_dir, load_yaml_state


# =============================================================================
# CONFIGURATION
# =============================================================================

MAX_DIFF_TOKENS = 8000  # ~32k chars at 4 chars/token
MAX_DIFF_CHARS = MAX_DIFF_TOKENS * 4


# =============================================================================
# CONTEXT DATACLASS
# =============================================================================

@dataclass
class ReviewContext:
    """
    All context needed for a code review.

    Diff:
        diff: The git diff content
        diff_truncated: Whether diff was truncated
        files_changed: List of changed file paths
        lines_added: Count of added lines
        lines_removed: Count of removed lines

    Intent:
        step_intent: Description of current step
        objective: Overall objective
        step_number: Which step we're on

    Constraints:
        constraints: List of active constraints
        risks: List of known risks with mitigations

    Patterns:
        relevant_lessons: Lessons that may apply to this change
    """
    # Diff
    diff: str = ""
    diff_truncated: bool = False
    files_changed: List[str] = field(default_factory=list)
    lines_added: int = 0
    lines_removed: int = 0

    # Intent
    step_intent: Optional[str] = None
    objective: Optional[str] = None
    step_number: int = 0

    # Constraints
    constraints: List[str] = field(default_factory=list)
    risks: List[Dict[str, str]] = field(default_factory=list)

    # Patterns
    relevant_lessons: List[Dict[str, str]] = field(default_factory=list)

    # Metadata
    is_empty: bool = True  # True if no changes to review

    def to_dict(self) -> dict:
        """Convert to dict for serialization."""
        return {
            "diff": {
                "content": self.diff,
                "truncated": self.diff_truncated,
                "files_changed": self.files_changed,
                "lines_added": self.lines_added,
                "lines_removed": self.lines_removed,
            },
            "intent": {
                "step": self.step_intent,
                "objective": self.objective,
                "step_number": self.step_number,
            },
            "constraints": self.constraints,
            "risks": self.risks,
            "relevant_lessons": self.relevant_lessons,
            "is_empty": self.is_empty,
        }


# =============================================================================
# GIT UTILITIES
# =============================================================================

def get_git_diff(staged_only: bool = False, max_chars: int = MAX_DIFF_CHARS) -> tuple[str, bool, List[str]]:
    """
    Get git diff with optional truncation.

    Args:
        staged_only: If True, only show staged changes (git diff --cached)
        max_chars: Maximum characters to return

    Returns:
        (diff_content, was_truncated, files_changed)
    """
    project_dir = get_project_dir()

    try:
        # Get the diff
        cmd = ["git", "diff"]
        if staged_only:
            cmd.append("--cached")

        result = subprocess.run(
            cmd,
            cwd=project_dir,
            capture_output=True,
            text=True,
            timeout=30
        )

        if result.returncode != 0:
            return "", False, []

        diff = result.stdout
        truncated = False

        # Truncate if too long
        if len(diff) > max_chars:
            diff = diff[:max_chars]
            diff += "\n\n[... DIFF TRUNCATED - showing first {:,} chars ...]".format(max_chars)
            truncated = True

        # Get list of changed files
        files_result = subprocess.run(
            ["git", "diff", "--name-only"] + (["--cached"] if staged_only else []),
            cwd=project_dir,
            capture_output=True,
            text=True,
            timeout=10
        )
        files = [f.strip() for f in files_result.stdout.strip().split("\n") if f.strip()]

        return diff, truncated, files

    except subprocess.TimeoutExpired:
        return "[TIMEOUT: git diff took too long]", False, []
    except Exception as e:
        return f"[ERROR: {e}]", False, []


def get_diff_stats(diff: str) -> tuple[int, int]:
    """
    Parse diff to count added/removed lines.

    Returns:
        (lines_added, lines_removed)
    """
    added = 0
    removed = 0

    for line in diff.split("\n"):
        if line.startswith("+") and not line.startswith("+++"):
            added += 1
        elif line.startswith("-") and not line.startswith("---"):
            removed += 1

    return added, removed


def has_uncommitted_changes() -> bool:
    """Check if there are any uncommitted changes."""
    project_dir = get_project_dir()
    try:
        result = subprocess.run(
            ["git", "status", "--porcelain"],
            cwd=project_dir,
            capture_output=True,
            text=True,
            timeout=10
        )
        return bool(result.stdout.strip())
    except Exception:
        return False


# =============================================================================
# STATE EXTRACTION
# =============================================================================

def get_current_step_intent(state: dict) -> tuple[Optional[str], int]:
    """
    Extract current step description from plan.

    Returns:
        (step_description, step_number)
    """
    plan = state.get("plan", [])
    current_step = state.get("current_step", 1)

    # Find in_progress step first
    for i, step in enumerate(plan, 1):
        if step.get("status") == "in_progress":
            return step.get("description"), i

    # Fall back to current_step pointer
    if 1 <= current_step <= len(plan):
        return plan[current_step - 1].get("description"), current_step

    return None, 0


def get_relevant_lessons(state: dict, files: List[str]) -> List[Dict[str, str]]:
    """
    Find lessons that may be relevant to the changed files.

    Uses:
    - File extensions to match trigger keywords
    - File paths to match specific patterns
    """
    memory = state.get("memory", [])
    if not memory:
        return []

    # Extract keywords from file paths
    keywords = set()
    for f in files:
        # Add extension
        if "." in f:
            ext = f.split(".")[-1].lower()
            keywords.add(ext)
            if ext == "py":
                keywords.add("python")
            elif ext in ("ts", "tsx"):
                keywords.add("typescript")
            elif ext in ("js", "jsx"):
                keywords.add("javascript")

        # Add path components
        parts = f.replace("\\", "/").split("/")
        for part in parts:
            if part and part not in (".", ".."):
                keywords.add(part.lower())

    # Common keywords
    keywords.add("code")
    keywords.add("edit")

    # Find matching lessons
    relevant = []
    for lesson in memory:
        trigger = lesson.get("trigger", "").lower()
        # Check if any keyword matches the trigger
        if any(kw in trigger for kw in keywords):
            relevant.append({
                "trigger": lesson.get("trigger", ""),
                "lesson": lesson.get("lesson", ""),
            })

    # Limit to most relevant (by reinforcement count)
    relevant_sorted = sorted(
        relevant,
        key=lambda x: state.get("memory", [{}])[0].get("reinforced", 1),
        reverse=True
    )

    return relevant_sorted[:5]  # Top 5 relevant lessons


# =============================================================================
# MAIN GATHERER
# =============================================================================

def gather_review_context(
    state: Optional[dict] = None,
    staged_only: bool = False,
) -> ReviewContext:
    """
    Gather all context needed for a code review.

    Args:
        state: Pre-loaded state dict (will load if None)
        staged_only: Only review staged changes

    Returns:
        ReviewContext with all gathered information
    """
    # Load state if not provided
    if state is None:
        state = load_yaml_state() or {}

    ctx = ReviewContext()

    # Get git diff
    diff, truncated, files = get_git_diff(staged_only=staged_only)
    ctx.diff = diff
    ctx.diff_truncated = truncated
    ctx.files_changed = files

    # Check if empty
    if not diff.strip() or diff.startswith("["):
        ctx.is_empty = True
        return ctx

    ctx.is_empty = False

    # Parse diff stats
    ctx.lines_added, ctx.lines_removed = get_diff_stats(diff)

    # Get intent
    ctx.step_intent, ctx.step_number = get_current_step_intent(state)
    ctx.objective = state.get("objective")

    # Get constraints
    ctx.constraints = state.get("constraints", [])

    # Get risks
    ctx.risks = state.get("risks", [])

    # Get relevant lessons
    ctx.relevant_lessons = get_relevant_lessons(state, files)

    return ctx


def format_context_for_prompt(ctx: ReviewContext) -> str:
    """
    Format ReviewContext as a string for inclusion in a prompt.

    Returns:
        Formatted string with all context sections
    """
    sections = []

    # Header
    sections.append("=" * 60)
    sections.append("CODE REVIEW CONTEXT")
    sections.append("=" * 60)

    # Scope
    sections.append("\n## SCOPE")
    sections.append(f"Files changed: {len(ctx.files_changed)}")
    sections.append(f"Lines: +{ctx.lines_added} / -{ctx.lines_removed}")
    if ctx.diff_truncated:
        sections.append("(Diff was truncated due to size)")

    # Intent
    if ctx.step_intent or ctx.objective:
        sections.append("\n## INTENT")
        if ctx.objective:
            sections.append(f"Objective: {ctx.objective}")
        if ctx.step_intent:
            sections.append(f"Current step ({ctx.step_number}): {ctx.step_intent}")

    # Constraints
    if ctx.constraints:
        sections.append("\n## CONSTRAINTS (must not violate)")
        for c in ctx.constraints:
            sections.append(f"  - {c}")

    # Risks
    if ctx.risks:
        sections.append("\n## KNOWN RISKS")
        for r in ctx.risks:
            risk = r.get("risk", str(r))
            sections.append(f"  - {risk}")

    # Relevant lessons
    if ctx.relevant_lessons:
        sections.append("\n## RELEVANT PATTERNS")
        for lesson in ctx.relevant_lessons:
            sections.append(f"  [{lesson['trigger']}]: {lesson['lesson']}")

    # Files changed
    if ctx.files_changed:
        sections.append("\n## FILES CHANGED")
        for f in ctx.files_changed:
            sections.append(f"  - {f}")

    # Diff
    sections.append("\n## DIFF")
    sections.append("-" * 60)
    sections.append(ctx.diff)
    sections.append("-" * 60)

    return "\n".join(sections)


# =============================================================================
# CLI ENTRY POINT
# =============================================================================

if __name__ == "__main__":
    import sys

    # Gather context
    staged = "--staged" in sys.argv
    ctx = gather_review_context(staged_only=staged)

    if ctx.is_empty:
        print("No changes to review.")
        sys.exit(0)

    # Print formatted context
    print(format_context_for_prompt(ctx))
