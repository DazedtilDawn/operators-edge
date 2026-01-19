#!/usr/bin/env python3
"""
Operator's Edge v8.0 - Codebase Knowledge

Store and surface codebase-specific knowledge that Claude can't derive from training.

Types of Knowledge:
1. ERROR → FIX mappings: "ImportError in auth/ → add __init__.py to path"
2. FILE → DEPENDENCIES: "Changing config.yaml requires restarting dev server"
3. CHANGE PATTERNS: "payment.py and billing.py usually change together"

This is codebase-specific knowledge, not generic patterns.
It's learned from THIS codebase's history, not from software methodology.

This is context engineering, not machine learning.
"""
import hashlib
import json
import os
import re
import sys
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple

# Add hooks directory to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


# =============================================================================
# CONFIGURATION
# =============================================================================

# Knowledge store location
KNOWLEDGE_FILE = "codebase_knowledge.json"

# Error signature extraction patterns
# These help normalize errors for matching
ERROR_PATTERNS = [
    # Python
    (r"(ModuleNotFoundError|ImportError): No module named ['\"]([^'\"]+)['\"]",
     "import_error", r"\1: \2"),
    (r"(FileNotFoundError): \[Errno \d+\] .* ['\"]([^'\"]+)['\"]",
     "file_not_found", r"\1: \2"),
    (r"(KeyError): ['\"]([^'\"]+)['\"]",
     "key_error", r"\1: \2"),
    (r"(TypeError|AttributeError): (.{0,100})",
     "type_error", r"\1: \2"),

    # JavaScript/Node
    (r"Error: Cannot find module ['\"]([^'\"]+)['\"]",
     "module_not_found", r"Cannot find module: \1"),
    (r"(SyntaxError|ReferenceError|TypeError): (.{0,100})",
     "js_error", r"\1: \2"),

    # Build/compile
    (r"error: (.{0,100})",
     "build_error", r"error: \1"),
    (r"failed with exit code (\d+)",
     "exit_code", r"exit code: \1"),

    # General
    (r"(FAIL|ERROR|FAILED): (.{0,100})",
     "general_failure", r"\1: \2"),
]

# Confidence decay - older fixes are less reliable
CONFIDENCE_DECAY_DAYS = 30


# =============================================================================
# DATA STRUCTURES
# =============================================================================

@dataclass
class KnownFix:
    """A recorded error → fix mapping."""
    error_signature: str
    error_type: str
    fix_description: str
    fix_commands: List[str]  # Commands that were run to fix it
    fix_files: List[str]     # Files that were modified
    confidence: float        # 0.0-1.0, decays over time
    times_used: int          # How many times this fix was applied
    last_success: Optional[str] = None  # ISO timestamp
    created_at: str = ""
    context_hints: List[str] = field(default_factory=list)  # Additional context

    def to_dict(self) -> dict:
        return {
            "error_signature": self.error_signature,
            "error_type": self.error_type,
            "fix_description": self.fix_description,
            "fix_commands": self.fix_commands,
            "fix_files": self.fix_files,
            "confidence": self.confidence,
            "times_used": self.times_used,
            "last_success": self.last_success,
            "created_at": self.created_at,
            "context_hints": self.context_hints,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "KnownFix":
        return cls(
            error_signature=data.get("error_signature", ""),
            error_type=data.get("error_type", "unknown"),
            fix_description=data.get("fix_description", ""),
            fix_commands=data.get("fix_commands", []),
            fix_files=data.get("fix_files", []),
            confidence=data.get("confidence", 0.5),
            times_used=data.get("times_used", 0),
            last_success=data.get("last_success"),
            created_at=data.get("created_at", ""),
            context_hints=data.get("context_hints", []),
        )


@dataclass
class RelatedFile:
    """A file that's related to another (usually changes together)."""
    file_path: str
    relation_type: str  # "cochange", "dependency", "import"
    strength: float     # 0.0-1.0, how strongly related
    reason: str         # Why they're related

    def to_dict(self) -> dict:
        return {
            "file_path": self.file_path,
            "relation_type": self.relation_type,
            "strength": self.strength,
            "reason": self.reason,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "RelatedFile":
        return cls(
            file_path=data.get("file_path", ""),
            relation_type=data.get("relation_type", "unknown"),
            strength=data.get("strength", 0.5),
            reason=data.get("reason", ""),
        )


# =============================================================================
# KNOWLEDGE STORE
# =============================================================================

def _get_knowledge_path() -> Path:
    """Get path to knowledge store file."""
    # Store in .proof directory alongside other data
    proof_dir = Path(__file__).parent.parent.parent / ".proof"
    proof_dir.mkdir(parents=True, exist_ok=True)
    return proof_dir / KNOWLEDGE_FILE


def _load_knowledge() -> dict:
    """Load knowledge store from disk."""
    path = _get_knowledge_path()
    if not path.exists():
        return {"fixes": {}, "relations": {}, "metadata": {"version": 1}}

    try:
        with open(path) as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return {"fixes": {}, "relations": {}, "metadata": {"version": 1}}


def _save_knowledge(data: dict) -> bool:
    """Save knowledge store to disk."""
    path = _get_knowledge_path()
    try:
        with open(path, 'w') as f:
            json.dump(data, f, indent=2)
        return True
    except OSError:
        return False


# =============================================================================
# ERROR SIGNATURE EXTRACTION
# =============================================================================

def extract_error_signature(error_output: str) -> Tuple[str, str]:
    """
    Extract a normalized error signature from raw output.

    Returns (signature, error_type) tuple.
    The signature is a normalized version for matching.
    """
    if not error_output:
        return "", "unknown"

    # Try each pattern
    for pattern, error_type, replacement in ERROR_PATTERNS:
        match = re.search(pattern, error_output, re.MULTILINE | re.IGNORECASE)
        if match:
            # Create normalized signature
            try:
                signature = re.sub(pattern, replacement, match.group(0))
                return signature.strip()[:200], error_type
            except Exception:
                pass

    # Fallback: hash first significant line
    lines = [l.strip() for l in error_output.split('\n') if l.strip()]
    error_lines = [l for l in lines if any(
        kw in l.lower() for kw in ('error', 'fail', 'exception', 'traceback')
    )]

    if error_lines:
        sig = error_lines[0][:200]
        return sig, "general"

    # Last resort: first non-empty line
    if lines:
        return lines[0][:200], "unknown"

    return "", "unknown"


def compute_signature_hash(signature: str) -> str:
    """Compute a hash for a signature (for storage key)."""
    return hashlib.md5(signature.encode()).hexdigest()[:12]


# =============================================================================
# FIX RECORDING AND LOOKUP
# =============================================================================

def record_fix(
    error_output: str,
    fix_description: str,
    fix_commands: List[str] = None,
    fix_files: List[str] = None,
    context_hints: List[str] = None
) -> Optional[str]:
    """
    Record what fixed an error for future reference.

    Args:
        error_output: The raw error output that was fixed
        fix_description: Human-readable description of the fix
        fix_commands: Commands that were run to fix it
        fix_files: Files that were modified as part of the fix
        context_hints: Additional context (e.g., "when working with auth/")

    Returns:
        The signature hash if recorded, None if failed
    """
    signature, error_type = extract_error_signature(error_output)
    if not signature:
        return None

    sig_hash = compute_signature_hash(signature)
    knowledge = _load_knowledge()

    # Check if we already have this fix
    existing = knowledge["fixes"].get(sig_hash)
    if existing:
        # Update existing fix
        fix = KnownFix.from_dict(existing)
        fix.times_used += 1
        fix.last_success = datetime.now().isoformat()
        # Boost confidence on re-use
        fix.confidence = min(0.95, fix.confidence + 0.1)
        # Merge any new commands/files
        if fix_commands:
            fix.fix_commands = list(set(fix.fix_commands + fix_commands))
        if fix_files:
            fix.fix_files = list(set(fix.fix_files + fix_files))
        if context_hints:
            fix.context_hints = list(set(fix.context_hints + context_hints))
    else:
        # Create new fix
        fix = KnownFix(
            error_signature=signature,
            error_type=error_type,
            fix_description=fix_description,
            fix_commands=fix_commands or [],
            fix_files=fix_files or [],
            confidence=0.6,  # Start with moderate confidence
            times_used=1,
            last_success=datetime.now().isoformat(),
            created_at=datetime.now().isoformat(),
            context_hints=context_hints or [],
        )

    knowledge["fixes"][sig_hash] = fix.to_dict()
    _save_knowledge(knowledge)

    return sig_hash


def lookup_fix(error_output: str) -> Optional[KnownFix]:
    """
    Check if we've seen this error before and know a fix.

    Returns the known fix if found, None otherwise.
    """
    signature, _ = extract_error_signature(error_output)
    if not signature:
        return None

    sig_hash = compute_signature_hash(signature)
    knowledge = _load_knowledge()

    fix_data = knowledge["fixes"].get(sig_hash)
    if not fix_data:
        return None

    fix = KnownFix.from_dict(fix_data)

    # Apply confidence decay based on age
    if fix.last_success:
        try:
            last_success = datetime.fromisoformat(fix.last_success)
            days_old = (datetime.now() - last_success).days
            decay = max(0.3, 1.0 - (days_old / CONFIDENCE_DECAY_DAYS) * 0.5)
            fix.confidence *= decay
        except ValueError:
            pass

    return fix


def get_all_fixes() -> List[KnownFix]:
    """Get all recorded fixes."""
    knowledge = _load_knowledge()
    return [KnownFix.from_dict(f) for f in knowledge["fixes"].values()]


def boost_fix_confidence(sig_hash: str, amount: float = 0.1) -> bool:
    """
    Boost confidence when a fix is verified to work.

    Called by fix_outcomes.py when:
    - Fix surfaced → user ran suggested command → command succeeded

    This closes the feedback loop - fixes that actually work
    become more confident over time.

    Args:
        sig_hash: Hash of the error signature
        amount: Amount to boost confidence by

    Returns:
        True if update succeeded
    """
    knowledge = _load_knowledge()
    fix_data = knowledge["fixes"].get(sig_hash)

    if not fix_data:
        return False

    # Boost confidence (cap at 0.95)
    fix_data["confidence"] = min(0.95, fix_data.get("confidence", 0.5) + amount)
    fix_data["times_used"] = fix_data.get("times_used", 0) + 1
    fix_data["last_success"] = datetime.now().isoformat()

    # Track verified successes (distinct from times_used)
    fix_data["verified_successes"] = fix_data.get("verified_successes", 0) + 1

    knowledge["fixes"][sig_hash] = fix_data
    return _save_knowledge(knowledge)


def decay_fix_confidence(sig_hash: str, amount: float = 0.15) -> bool:
    """
    Decay confidence when a fix fails to work.

    Called by fix_outcomes.py when:
    - Fix surfaced → user ran suggested command → command FAILED

    This prevents bad fixes from persisting - if following a fix
    doesn't help, it gets weaker and eventually falls below the
    display threshold.

    Args:
        sig_hash: Hash of the error signature
        amount: Amount to decay confidence by

    Returns:
        True if update succeeded
    """
    knowledge = _load_knowledge()
    fix_data = knowledge["fixes"].get(sig_hash)

    if not fix_data:
        return False

    # Decay confidence (floor at 0.1)
    fix_data["confidence"] = max(0.1, fix_data.get("confidence", 0.5) - amount)

    # Track failures
    fix_data["failures"] = fix_data.get("failures", 0) + 1

    knowledge["fixes"][sig_hash] = fix_data
    return _save_knowledge(knowledge)


def get_file_fixes(file_path: str) -> List[KnownFix]:
    """
    Get known fixes related to a specific file.

    Used by active_intervention.py to inject file-specific context.
    """
    knowledge = _load_knowledge()
    fixes = []

    file_path = str(file_path)
    file_name = Path(file_path).name

    for fix_data in knowledge["fixes"].values():
        # Check if this fix involves this file
        fix_files = fix_data.get("fix_files", [])
        if any(file_name in f or file_path in f for f in fix_files):
            fix = KnownFix.from_dict(fix_data)
            if fix.confidence >= 0.4:
                fixes.append(fix)

        # Also check context hints
        hints = fix_data.get("context_hints", [])
        if any(file_name in hint or file_path in hint for hint in hints):
            fix = KnownFix.from_dict(fix_data)
            if fix.confidence >= 0.4 and fix not in fixes:
                fixes.append(fix)

    # Sort by confidence descending
    fixes.sort(key=lambda f: -f.confidence)
    return fixes[:5]  # Max 5 fixes


# =============================================================================
# FILE RELATIONS
# =============================================================================

def record_cochange(file1: str, file2: str, reason: str = "") -> None:
    """
    Record that two files changed together (co-change pattern).

    Call this when files are modified together in a session.
    """
    knowledge = _load_knowledge()

    # Normalize paths
    file1 = str(file1)
    file2 = str(file2)

    # Create bidirectional relation
    for (a, b) in [(file1, file2), (file2, file1)]:
        if a not in knowledge["relations"]:
            knowledge["relations"][a] = []

        # Check if relation exists
        existing = None
        for i, rel in enumerate(knowledge["relations"][a]):
            if rel.get("file_path") == b:
                existing = i
                break

        if existing is not None:
            # Strengthen existing relation
            knowledge["relations"][a][existing]["strength"] = min(
                0.95,
                knowledge["relations"][a][existing].get("strength", 0.5) + 0.1
            )
        else:
            # Create new relation
            knowledge["relations"][a].append({
                "file_path": b,
                "relation_type": "cochange",
                "strength": 0.5,
                "reason": reason or "Changed together in session",
            })

    _save_knowledge(knowledge)


def get_related_files(file_path: str, min_strength: float = 0.3) -> List[RelatedFile]:
    """
    Get files that usually change together with or depend on this file.

    Args:
        file_path: The file to find relations for
        min_strength: Minimum relation strength to include

    Returns:
        List of related files, sorted by strength descending
    """
    knowledge = _load_knowledge()
    file_path = str(file_path)

    relations = knowledge["relations"].get(file_path, [])
    result = []

    for rel in relations:
        if rel.get("strength", 0) >= min_strength:
            result.append(RelatedFile.from_dict(rel))

    # Sort by strength descending
    result.sort(key=lambda r: -r.strength)

    return result


# =============================================================================
# FORMATTING
# =============================================================================

def format_known_fix(fix: KnownFix) -> str:
    """Format a known fix for display."""
    lines = [
        "",
        "=" * 60,
        "💡 KNOWN FIX FOUND",
        "=" * 60,
        "",
        f"**Error Pattern:** {fix.error_type}",
        f"  `{fix.error_signature[:100]}`",
        "",
        f"**Fix:** {fix.fix_description}",
        "",
    ]

    if fix.fix_commands:
        lines.append("**Commands that helped:**")
        for cmd in fix.fix_commands[:3]:
            lines.append(f"  ```{cmd}```")
        lines.append("")

    if fix.fix_files:
        lines.append("**Files involved:**")
        for f in fix.fix_files[:5]:
            lines.append(f"  - {f}")
        lines.append("")

    if fix.context_hints:
        lines.append("**Context:**")
        for hint in fix.context_hints[:3]:
            lines.append(f"  - {hint}")
        lines.append("")

    lines.extend([
        f"**Confidence:** {fix.confidence*100:.0f}% (used {fix.times_used}x)",
        "",
        "-" * 60,
        ""
    ])

    return "\n".join(lines)


def format_related_files(relations: List[RelatedFile]) -> str:
    """Format related files for display."""
    if not relations:
        return ""

    lines = [
        "",
        "🔗 **Related Files:**",
    ]

    for rel in relations[:5]:
        strength_bar = "█" * int(rel.strength * 5) + "░" * (5 - int(rel.strength * 5))
        lines.append(f"  [{strength_bar}] {rel.file_path}")
        if rel.reason:
            lines.append(f"         {rel.reason}")

    lines.append("")
    return "\n".join(lines)


# =============================================================================
# QUICK TEST
# =============================================================================

if __name__ == "__main__":
    print("Codebase Knowledge - Self Test")
    print("=" * 40)

    # Test error signature extraction
    test_errors = [
        "ImportError: No module named 'mymodule'",
        "FileNotFoundError: [Errno 2] No such file: '/app/config.yaml'",
        "Error: Cannot find module 'lodash'",
        "FAIL: test_authentication",
    ]

    print("\nError signature extraction:")
    for error in test_errors:
        sig, err_type = extract_error_signature(error)
        print(f"  {err_type}: {sig}")

    # Test fix recording
    print("\nRecording a fix...")
    sig_hash = record_fix(
        error_output="ImportError: No module named 'utils.auth'",
        fix_description="Add __init__.py to utils directory",
        fix_commands=["touch utils/__init__.py"],
        fix_files=["utils/__init__.py"],
        context_hints=["Python import issue"]
    )
    print(f"  Recorded with hash: {sig_hash}")

    # Test fix lookup
    print("\nLooking up fix...")
    fix = lookup_fix("ImportError: No module named 'utils.auth'")
    if fix:
        print(f"  Found: {fix.fix_description}")
        print(f"  Confidence: {fix.confidence*100:.0f}%")
    else:
        print("  No fix found")

    print()
    print("Self-test complete.")
