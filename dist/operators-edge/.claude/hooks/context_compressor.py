#!/usr/bin/env python3
"""
Operator's Edge v8.0 - Context Compressor (Phase 10.1)

RLM-Inspired: Don't just warn about high context - actively compress it.

The Problem:
- Context window fills up with verbose file reads and bash outputs
- Claude sees "⚠️ Context at 78%" and... keeps going
- Passive warnings don't change behavior
- Long sessions degrade in quality ("context rot")

The Solution:
- Identify large, compressible context segments
- Generate compressed summaries preserving key information
- Store full content for retrieval if needed
- Offer compression suggestions or auto-compress based on intervention level

"The best code is no code. The best context is compressed context."
"""
import hashlib
import json
import os
import re
import sys
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Any

# Add hooks directory to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


# =============================================================================
# CONFIGURATION
# =============================================================================

# Compression thresholds (can be overridden via v8_config.json)
DEFAULT_CONTEXT_TRIGGER_PERCENT = 70    # Trigger compression at 70%+ context
DEFAULT_MIN_SEGMENT_CHARS = 5000        # Minimum chars for a segment to be compressible
DEFAULT_MIN_SEGMENT_TOKENS = 1250       # ~5000 chars / 4 chars per token

# Segment types
SEGMENT_TYPE_FILE_READ = "file_read"
SEGMENT_TYPE_BASH_OUTPUT = "bash_output"
SEGMENT_TYPE_CONVERSATION = "conversation"

# Storage
SNAPSHOTS_DIR = "context_snapshots"
MAX_SNAPSHOTS = 50  # Keep last N snapshots

# Cooldown to prevent compression spam (seconds)
COMPRESSION_COOLDOWN_SECONDS = 300  # 5 minutes between offers

# Track last compression offer time
_last_compression_offer: Optional[datetime] = None


# =============================================================================
# CONFIGURATION LOADING
# =============================================================================

def _get_config_path() -> Path:
    """Get path to v8 config file."""
    return Path(__file__).parent.parent.parent / ".proof" / "v8_config.json"


def _load_compression_config() -> dict:
    """
    Load compression settings from v8_config.json.

    Falls back to defaults if config doesn't exist or is invalid.
    """
    defaults = {
        "context_trigger_percent": DEFAULT_CONTEXT_TRIGGER_PERCENT,
        "min_segment_chars": DEFAULT_MIN_SEGMENT_CHARS,
        "min_segment_tokens": DEFAULT_MIN_SEGMENT_TOKENS,
        "cooldown_seconds": COMPRESSION_COOLDOWN_SECONDS,
    }

    config_path = _get_config_path()
    if not config_path.exists():
        return defaults

    try:
        with open(config_path) as f:
            data = json.load(f)
        compression_config = data.get("compression", {})
        return {**defaults, **compression_config}
    except (json.JSONDecodeError, OSError):
        return defaults


def _get_config_value(key: str) -> Any:
    """Get a specific config value."""
    config = _load_compression_config()
    return config.get(key, 0)


# =============================================================================
# COOLDOWN MANAGEMENT
# =============================================================================

def _can_offer_compression() -> bool:
    """Check if enough time has passed since last compression offer."""
    global _last_compression_offer

    if _last_compression_offer is None:
        return True

    cooldown = _load_compression_config().get("cooldown_seconds", COMPRESSION_COOLDOWN_SECONDS)
    elapsed = (datetime.now() - _last_compression_offer).total_seconds()
    return elapsed >= cooldown


def _mark_compression_offered() -> None:
    """Mark that a compression offer was shown."""
    global _last_compression_offer
    _last_compression_offer = datetime.now()


def reset_compression_cooldown() -> None:
    """Reset compression cooldown (for testing)."""
    global _last_compression_offer
    _last_compression_offer = None


# =============================================================================
# DEBUG LOGGING
# =============================================================================

def _log_debug(message: str) -> None:
    """Log debug message to .proof/debug.log (not stderr)."""
    try:
        debug_path = Path(__file__).parent.parent.parent / ".proof" / "debug.log"
        debug_path.parent.mkdir(parents=True, exist_ok=True)
        with open(debug_path, "a") as f:
            f.write(f"[{datetime.now().isoformat()}] context_compressor: {message}\n")
    except:
        pass


# =============================================================================
# DATA STRUCTURES
# =============================================================================

@dataclass
class ContextSegment:
    """A segment of context that could be compressed."""
    segment_id: str
    segment_type: str  # file_read, bash_output, conversation
    content: str
    estimated_tokens: int
    timestamp: str
    source: str  # file path, command, etc.

    # Compression metadata
    is_compressed: bool = False
    compressed_content: str = ""
    snapshot_id: Optional[str] = None

    def to_dict(self) -> dict:
        return {
            "segment_id": self.segment_id,
            "segment_type": self.segment_type,
            "estimated_tokens": self.estimated_tokens,
            "timestamp": self.timestamp,
            "source": self.source,
            "is_compressed": self.is_compressed,
            "snapshot_id": self.snapshot_id,
        }


@dataclass
class CompressionResult:
    """Result of compressing a segment."""
    segment_id: str
    original_tokens: int
    compressed_tokens: int
    compression_ratio: float
    summary: str
    snapshot_path: Optional[Path] = None

    def to_dict(self) -> dict:
        return {
            "segment_id": self.segment_id,
            "original_tokens": self.original_tokens,
            "compressed_tokens": self.compressed_tokens,
            "compression_ratio": round(self.compression_ratio, 2),
            "snapshot_path": str(self.snapshot_path) if self.snapshot_path else None,
        }


@dataclass
class CompressionOffer:
    """An offer to compress context."""
    segments: List[ContextSegment]
    total_tokens_compressible: int
    estimated_savings: int
    urgency: str  # "suggestion", "recommendation", "urgent"
    formatted_offer: str


# =============================================================================
# SEGMENT IDENTIFICATION
# =============================================================================

def _estimate_tokens(text: str) -> int:
    """Estimate token count from text (rough: ~4 chars per token)."""
    return len(text) // 4


def _generate_segment_id(segment_type: str, source: str, timestamp: str) -> str:
    """Generate unique segment ID."""
    content = f"{segment_type}:{source}:{timestamp}"
    return hashlib.md5(content.encode()).hexdigest()[:12]


def identify_compressible_segments(session_log: Path) -> List[ContextSegment]:
    """
    Find segments in the session that could be compressed.

    Looks for:
    - Large file reads (Read tool outputs)
    - Verbose bash outputs (Bash tool outputs)
    - Long conversation chunks (accumulated context)
    """
    segments = []
    min_chars = _get_config_value("min_segment_chars")

    try:
        from context_monitor import load_session_entries
        entries = load_session_entries(session_log)
    except ImportError:
        return segments
    except Exception as e:
        _log_debug(f"Error loading session entries: {e}")
        return segments

    for entry in entries:
        tool = entry.get("tool", "")
        output = entry.get("output_preview", "")
        timestamp = entry.get("timestamp", datetime.now().isoformat())

        if not output or not isinstance(output, str):
            continue

        output_len = len(output)
        if output_len < min_chars:
            continue

        # File reads
        if tool == "Read":
            input_data = entry.get("input_preview", {})
            file_path = ""
            if isinstance(input_data, dict):
                file_path = input_data.get("file_path", "")
            elif isinstance(input_data, str):
                file_path = input_data

            segment_id = _generate_segment_id(SEGMENT_TYPE_FILE_READ, file_path, timestamp)
            segments.append(ContextSegment(
                segment_id=segment_id,
                segment_type=SEGMENT_TYPE_FILE_READ,
                content=output,
                estimated_tokens=_estimate_tokens(output),
                timestamp=timestamp,
                source=file_path,
            ))

        # Bash outputs
        elif tool == "Bash":
            input_data = entry.get("input_preview", {})
            command = ""
            if isinstance(input_data, dict):
                command = input_data.get("command", "")
            elif isinstance(input_data, str):
                command = input_data

            segment_id = _generate_segment_id(SEGMENT_TYPE_BASH_OUTPUT, command[:100], timestamp)
            segments.append(ContextSegment(
                segment_id=segment_id,
                segment_type=SEGMENT_TYPE_BASH_OUTPUT,
                content=output,
                estimated_tokens=_estimate_tokens(output),
                timestamp=timestamp,
                source=command[:200],  # Truncate long commands
            ))

    return segments


def get_largest_segments(segments: List[ContextSegment], limit: int = 5) -> List[ContextSegment]:
    """Get the largest segments by token count."""
    sorted_segments = sorted(segments, key=lambda s: s.estimated_tokens, reverse=True)
    return sorted_segments[:limit]


# =============================================================================
# COMPRESSION STRATEGIES
# =============================================================================

def compress_file_read(segment: ContextSegment) -> str:
    """
    Compress a file read segment.

    Strategy: Extract structure, key elements, and metadata.
    """
    content = segment.content
    lines = content.split('\n')
    file_path = segment.source

    summary_parts = []

    # File metadata
    line_count = len(lines)
    char_count = len(content)
    summary_parts.append(f"📄 **{Path(file_path).name}** ({line_count} lines, {char_count:,} chars)")

    # Detect file type and extract structure
    ext = Path(file_path).suffix.lower()

    if ext in ('.py',):
        summary_parts.append(_extract_python_structure(content))
    elif ext in ('.js', '.ts', '.tsx', '.jsx'):
        summary_parts.append(_extract_js_structure(content))
    elif ext in ('.json',):
        summary_parts.append(_extract_json_structure(content))
    elif ext in ('.yaml', '.yml'):
        summary_parts.append(_extract_yaml_structure(content))
    elif ext in ('.md',):
        summary_parts.append(_extract_markdown_structure(content))
    else:
        # Generic: first and last few lines
        summary_parts.append(_extract_generic_structure(content))

    return "\n".join(filter(None, summary_parts))


def compress_bash_output(segment: ContextSegment) -> str:
    """
    Compress a bash output segment.

    Strategy: Extract errors, key lines, and summary.
    """
    content = segment.content
    command = segment.source
    lines = content.split('\n')

    summary_parts = []
    summary_parts.append(f"💻 Command: `{command[:80]}{'...' if len(command) > 80 else ''}`")
    summary_parts.append(f"   Output: {len(lines)} lines")

    # Extract errors
    error_lines = [l for l in lines if any(kw in l.lower() for kw in ['error', 'fail', 'exception', 'traceback'])]
    if error_lines:
        summary_parts.append("   ❌ Errors detected:")
        for err in error_lines[:3]:
            summary_parts.append(f"      • {err[:100]}")

    # Extract warnings
    warning_lines = [l for l in lines if 'warning' in l.lower()]
    if warning_lines and len(warning_lines) <= 5:
        summary_parts.append(f"   ⚠️ {len(warning_lines)} warning(s)")

    # Check for success indicators
    success_indicators = ['success', 'passed', 'completed', 'done', 'ok']
    if any(ind in content.lower() for ind in success_indicators):
        summary_parts.append("   ✅ Success indicators present")

    return "\n".join(summary_parts)


def _extract_python_structure(content: str) -> str:
    """Extract Python file structure."""
    lines = content.split('\n')
    imports = []
    classes = []
    functions = []

    for line in lines:
        stripped = line.strip()
        if stripped.startswith('import ') or stripped.startswith('from '):
            imports.append(stripped)
        elif stripped.startswith('class '):
            match = re.match(r'class\s+(\w+)', stripped)
            if match:
                classes.append(match.group(1))
        elif stripped.startswith('def '):
            match = re.match(r'def\s+(\w+)', stripped)
            if match:
                functions.append(match.group(1))

    parts = []
    if imports:
        parts.append(f"   Imports: {len(imports)} ({', '.join(imports[:3])}{'...' if len(imports) > 3 else ''})")
    if classes:
        parts.append(f"   Classes: {', '.join(classes[:5])}{'...' if len(classes) > 5 else ''}")
    if functions:
        parts.append(f"   Functions: {', '.join(functions[:10])}{'...' if len(functions) > 10 else ''}")

    return "\n".join(parts) if parts else "   (No structure extracted)"


def _extract_js_structure(content: str) -> str:
    """Extract JavaScript/TypeScript file structure."""
    lines = content.split('\n')
    imports = []
    exports = []
    functions = []

    for line in lines:
        stripped = line.strip()
        if 'import ' in stripped:
            imports.append(stripped[:60])
        elif 'export ' in stripped:
            exports.append(stripped[:60])
        elif 'function ' in stripped or '=>' in stripped:
            match = re.search(r'(?:function\s+)?(\w+)\s*(?:\(|=)', stripped)
            if match:
                functions.append(match.group(1))

    parts = []
    if imports:
        parts.append(f"   Imports: {len(imports)}")
    if exports:
        parts.append(f"   Exports: {len(exports)}")
    if functions:
        parts.append(f"   Functions: {', '.join(functions[:10])}{'...' if len(functions) > 10 else ''}")

    return "\n".join(parts) if parts else "   (No structure extracted)"


def _extract_json_structure(content: str) -> str:
    """Extract JSON structure (top-level keys)."""
    try:
        data = json.loads(content)
        if isinstance(data, dict):
            keys = list(data.keys())[:10]
            return f"   Top-level keys: {', '.join(keys)}{'...' if len(data) > 10 else ''}"
        elif isinstance(data, list):
            return f"   Array with {len(data)} items"
    except json.JSONDecodeError:
        pass
    return "   (Invalid JSON or too complex)"


def _extract_yaml_structure(content: str) -> str:
    """Extract YAML structure (top-level keys)."""
    lines = content.split('\n')
    top_keys = []
    for line in lines:
        if line and not line.startswith(' ') and not line.startswith('#') and ':' in line:
            key = line.split(':')[0].strip()
            if key:
                top_keys.append(key)

    if top_keys:
        return f"   Top-level keys: {', '.join(top_keys[:10])}{'...' if len(top_keys) > 10 else ''}"
    return "   (No structure extracted)"


def _extract_markdown_structure(content: str) -> str:
    """Extract Markdown structure (headers)."""
    lines = content.split('\n')
    headers = [l for l in lines if l.startswith('#')]

    if headers:
        return f"   Headers: {len(headers)} ({headers[0][:50]}...)"
    return "   (No headers found)"


def _extract_generic_structure(content: str) -> str:
    """Generic structure extraction (first/last lines)."""
    lines = content.split('\n')
    if len(lines) <= 10:
        return "   (Short file, no compression needed)"

    preview = []
    preview.append("   First 3 lines:")
    for line in lines[:3]:
        preview.append(f"      {line[:80]}")
    preview.append("   ...")
    preview.append("   Last 2 lines:")
    for line in lines[-2:]:
        preview.append(f"      {line[:80]}")

    return "\n".join(preview)


# =============================================================================
# SNAPSHOT STORAGE
# =============================================================================

def _get_snapshots_dir() -> Path:
    """Get path to snapshots directory."""
    proof_dir = Path(__file__).parent.parent.parent / ".proof"
    snapshots_dir = proof_dir / SNAPSHOTS_DIR
    snapshots_dir.mkdir(parents=True, exist_ok=True)
    return snapshots_dir


def save_snapshot(segment: ContextSegment) -> Path:
    """Save full content to snapshot file."""
    snapshots_dir = _get_snapshots_dir()

    timestamp = datetime.now().strftime('%Y%m%d-%H%M%S')
    filename = f"snapshot-{timestamp}-{segment.segment_id}.json"
    filepath = snapshots_dir / filename

    snapshot_data = {
        "segment_id": segment.segment_id,
        "segment_type": segment.segment_type,
        "source": segment.source,
        "timestamp": segment.timestamp,
        "saved_at": datetime.now().isoformat(),
        "content": segment.content,
        "estimated_tokens": segment.estimated_tokens,
    }

    with open(filepath, 'w') as f:
        json.dump(snapshot_data, f, indent=2)

    _cleanup_old_snapshots()
    return filepath


def load_snapshot(snapshot_path: Path) -> Optional[dict]:
    """Load a snapshot from disk."""
    if not snapshot_path.exists():
        return None

    try:
        with open(snapshot_path) as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return None


def _cleanup_old_snapshots():
    """Remove old snapshots beyond retention limit."""
    snapshots_dir = _get_snapshots_dir()
    snapshot_files = sorted(snapshots_dir.glob("snapshot-*.json"), reverse=True)

    for filepath in snapshot_files[MAX_SNAPSHOTS:]:
        try:
            filepath.unlink()
        except OSError:
            pass


# =============================================================================
# COMPRESSION EXECUTION
# =============================================================================

def compress_segment(segment: ContextSegment, save_full: bool = True) -> CompressionResult:
    """
    Compress a segment and optionally save the full content.

    Returns CompressionResult with summary and snapshot path.
    """
    # Generate summary based on type
    if segment.segment_type == SEGMENT_TYPE_FILE_READ:
        summary = compress_file_read(segment)
    elif segment.segment_type == SEGMENT_TYPE_BASH_OUTPUT:
        summary = compress_bash_output(segment)
    else:
        summary = f"[{segment.segment_type}] {segment.source[:100]}"

    # Save full content if requested
    snapshot_path = None
    if save_full:
        snapshot_path = save_snapshot(segment)

    # Calculate compression ratio
    original_tokens = segment.estimated_tokens
    compressed_tokens = _estimate_tokens(summary)
    ratio = compressed_tokens / original_tokens if original_tokens > 0 else 1.0

    return CompressionResult(
        segment_id=segment.segment_id,
        original_tokens=original_tokens,
        compressed_tokens=compressed_tokens,
        compression_ratio=ratio,
        summary=summary,
        snapshot_path=snapshot_path,
    )


# =============================================================================
# COMPRESSION OFFER
# =============================================================================

def format_compression_offer(
    segments: List[ContextSegment],
    results: List[CompressionResult],
    urgency: str = "suggestion"
) -> str:
    """Format a compression offer for display."""
    total_original = sum(r.original_tokens for r in results)
    total_compressed = sum(r.compressed_tokens for r in results)
    savings = total_original - total_compressed
    savings_percent = (savings / total_original * 100) if total_original > 0 else 0

    lines = []

    # Header based on urgency
    if urgency == "urgent":
        lines.append("╭─ ⚠️ CONTEXT COMPRESSION RECOMMENDED (URGENT) ─────╮")
    elif urgency == "recommendation":
        lines.append("╭─ 📦 CONTEXT COMPRESSION AVAILABLE ─────────────────╮")
    else:
        lines.append("╭─ 💡 COMPRESSION SUGGESTION ─────────────────────────╮")

    lines.append("│")
    lines.append(f"│ {len(segments)} large context segment(s) detected:")

    for segment, result in zip(segments[:3], results[:3]):
        source_short = segment.source.split('/')[-1][:30] if segment.source else "unknown"
        lines.append(f"│   • {segment.segment_type}: {source_short} ({segment.estimated_tokens} tokens)")

    if len(segments) > 3:
        lines.append(f"│   ... and {len(segments) - 3} more")

    lines.append("│")
    lines.append(f"│ Potential savings: ~{savings:,} tokens ({savings_percent:.0f}% reduction)")
    lines.append("│")

    # Show sample compression
    if results:
        lines.append("│ Sample compressed summary:")
        for line in results[0].summary.split('\n')[:4]:
            lines.append(f"│   {line}")

    lines.append("│")
    lines.append("│ Full content saved to .proof/context_snapshots/")
    lines.append("│ for retrieval if needed.")
    lines.append("╰────────────────────────────────────────────────────╯")

    return "\n".join(lines)


def check_and_offer_compression(
    intervention_level: str = "advise"
) -> Optional[str]:
    """
    Main integration point for hooks.

    Checks if compression should be offered and returns formatted offer.
    Returns None if no compression needed.
    """
    if intervention_level == "observe":
        return None

    if not _can_offer_compression():
        return None

    try:
        from proof_utils import get_session_log_path
        from context_monitor import estimate_context_usage

        session_log = get_session_log_path()
        if not session_log or not session_log.exists():
            return None

        # Check context usage
        estimate = estimate_context_usage(session_log)
        trigger_percent = _get_config_value("context_trigger_percent") / 100

        if estimate.usage_percentage < trigger_percent:
            return None

        # Find compressible segments
        segments = identify_compressible_segments(session_log)
        if not segments:
            return None

        # Get largest segments
        largest = get_largest_segments(segments, limit=5)
        if not largest:
            return None

        # Compress them
        results = [compress_segment(seg, save_full=True) for seg in largest]

        # Determine urgency
        if estimate.usage_percentage >= 0.90:
            urgency = "urgent"
        elif estimate.usage_percentage >= 0.80:
            urgency = "recommendation"
        else:
            urgency = "suggestion"

        # Only surface based on intervention level
        if intervention_level == "advise" and urgency == "suggestion":
            return None

        _mark_compression_offered()
        return format_compression_offer(largest, results, urgency)

    except ImportError:
        return None
    except Exception as e:
        _log_debug(f"check_and_offer_compression error: {e}")
        return None


def get_compression_summary() -> Optional[str]:
    """
    Get a summary of available compressions.

    Useful for checkpoint generation.
    """
    try:
        from proof_utils import get_session_log_path

        session_log = get_session_log_path()
        if not session_log or not session_log.exists():
            return None

        segments = identify_compressible_segments(session_log)
        if not segments:
            return None

        total_tokens = sum(s.estimated_tokens for s in segments)

        return f"📦 {len(segments)} compressible segments (~{total_tokens:,} tokens)"

    except ImportError:
        return None
    except Exception:
        return None


# =============================================================================
# QUICK TEST
# =============================================================================

if __name__ == "__main__":
    print("Context Compressor - Self Test")
    print("=" * 50)

    # Test segment creation
    test_segment = ContextSegment(
        segment_id="test-001",
        segment_type=SEGMENT_TYPE_FILE_READ,
        content="""#!/usr/bin/env python3
import os
import sys
from pathlib import Path

class MyClass:
    def __init__(self):
        pass

    def method_one(self):
        pass

def helper_function():
    pass

def another_function():
    pass

if __name__ == "__main__":
    main()
""",
        estimated_tokens=500,
        timestamp=datetime.now().isoformat(),
        source="test_file.py",
    )

    print("\n--- Test Python Compression ---")
    result = compress_segment(test_segment, save_full=False)
    print(result.summary)
    print(f"Compression ratio: {result.compression_ratio:.2f}")

    # Test bash output compression
    bash_segment = ContextSegment(
        segment_id="test-002",
        segment_type=SEGMENT_TYPE_BASH_OUTPUT,
        content="""Running tests...
test_one PASSED
test_two PASSED
test_three FAILED: AssertionError at line 45
test_four PASSED
warning: deprecated function used
ERROR: Connection refused
Total: 3 passed, 1 failed
""",
        estimated_tokens=200,
        timestamp=datetime.now().isoformat(),
        source="python -m pytest tests/",
    )

    print("\n--- Test Bash Compression ---")
    result = compress_segment(bash_segment, save_full=False)
    print(result.summary)

    # Test offer formatting
    print("\n--- Test Compression Offer ---")
    results = [compress_segment(test_segment, save_full=False)]
    offer = format_compression_offer([test_segment], results, "recommendation")
    print(offer)

    print("\nSelf-test complete.")
