#!/usr/bin/env python3
"""
Operator's Edge - Fork Indexer
Session scanning and indexing for Smart Forking (/edge-fork).

Provides:
- Session file discovery
- JSONL message parsing
- Summary extraction for embedding
- Index building and incremental updates
"""
import json
import os
import hashlib
from pathlib import Path
from datetime import datetime
from typing import List, Optional, Dict, Any, Tuple, Generator

# Add hooks directory to path for imports
import sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from fork_utils import (
    generate_embedding,
    load_index,
    save_index,
    get_embeddings_dir,
    DEFAULT_EMBEDDING_MODEL,
    EMBEDDING_DIMENSION,
)


def get_claude_sessions_dir() -> Optional[Path]:
    """
    Find the Claude sessions directory for the current project.

    Sessions are stored in ~/.claude/projects/<project_hash>/*.jsonl
    """
    # Get project directory to compute hash
    project_dir = Path(os.environ.get("CLAUDE_PROJECT_DIR", Path.cwd()))

    # Claude Code hashes the project path
    # The hash is the first 8 chars of SHA-256 of the absolute path
    project_path_str = str(project_dir.resolve())
    path_hash = hashlib.sha256(project_path_str.encode()).hexdigest()[:8]

    # Try the new location format: ~/.claude/projects/-path-segments-hash
    home = Path.home()

    # Claude uses the path with slashes and spaces replaced by dashes
    # e.g., /Users/andy/my project -> -Users-andy-my-project
    safe_path = project_path_str.replace("/", "-").replace("\\", "-").replace(" ", "-")
    sessions_dir = home / ".claude" / "projects" / safe_path

    if sessions_dir.exists():
        return sessions_dir

    # Fallback: try to find any matching directory
    projects_base = home / ".claude" / "projects"
    if projects_base.exists():
        # Look for directories that might match our project
        for d in projects_base.iterdir():
            if d.is_dir() and project_dir.name in d.name:
                return d

    return None


def get_all_project_dirs() -> List[Path]:
    """
    Find all Claude project directories.

    Returns:
        List of paths to project session directories
    """
    home = Path.home()
    projects_base = home / ".claude" / "projects"

    if not projects_base.exists():
        return []

    # Find all directories containing .jsonl files
    project_dirs = []
    for d in projects_base.iterdir():
        if d.is_dir():
            # Check if it has any .jsonl files (actual sessions)
            if any(d.glob("*.jsonl")):
                project_dirs.append(d)

    return project_dirs


def extract_project_name(project_dir: Path) -> str:
    """
    Extract a readable project name from a project directory path.

    The directory name is like: -Users-andy-Documents-MyProject
    We want to extract: MyProject
    """
    name = project_dir.name

    # Remove leading dash and split by dash
    parts = name.strip("-").split("-")

    # The last few parts are typically the project name
    # Look for meaningful parts (skip common path segments)
    skip = {"Users", "Documents", "Projects", "Code", "home", "src", "dev"}
    meaningful_parts = [p for p in parts[-3:] if p and p not in skip]

    if meaningful_parts:
        return meaningful_parts[-1]

    # Fallback: just return the last part
    return parts[-1] if parts else "unknown"


def parse_session_jsonl(path: Path) -> List[Dict[str, Any]]:
    """
    Parse a Claude session JSONL file.

    Each line is a JSON object representing a message or event.

    Args:
        path: Path to the session JSONL file

    Returns:
        List of parsed message dictionaries
    """
    messages = []
    try:
        with open(path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    try:
                        msg = json.loads(line)
                        messages.append(msg)
                    except json.JSONDecodeError:
                        continue
    except Exception as e:
        if os.environ.get("EDGE_DEBUG"):
            print(f"[fork] parse_session_jsonl({path.name}): {e}", file=sys.stderr)
    return messages


def clean_message_content(text: str) -> str:
    """
    Clean user message content by removing system noise.

    Removes:
    - <system-reminder> blocks
    - Hook output (lines starting with ===, ---, etc.)
    - Command prefixes (/edge-*, etc.)
    - Very long code blocks

    Args:
        text: Raw message content

    Returns:
        Cleaned message text
    """
    import re

    if not text:
        return ""

    # Remove <system-reminder> blocks
    text = re.sub(r'<system-reminder>.*?</system-reminder>', '', text, flags=re.DOTALL)

    # Remove <command-message> and <command-name> blocks
    text = re.sub(r'<command-\w+>.*?</command-\w+>', '', text, flags=re.DOTALL)

    # Remove hook output blocks (=== lines, --- lines, status blocks)
    lines = text.split('\n')
    cleaned_lines = []
    skip_until_separator = False

    for line in lines:
        stripped = line.strip()

        # Skip hook output headers
        if stripped.startswith('===') or stripped.startswith('---'):
            skip_until_separator = True
            continue

        # Only skip status-like lines when in hook output mode (after === or ---)
        if skip_until_separator:
            # Skip lines that look like status output
            if any(stripped.startswith(prefix) for prefix in [
                'DISPATCH MODE', 'OPERATOR\'S EDGE', 'PRUNE', 'EDGE LOOP',
                'Mode:', 'State:', 'Objective:', 'Progress:', 'Stats:',
                'Steps:', 'Mismatches:', 'Lessons:', 'CTI:', 'Drift:',
                'Constraints:', 'Top lessons', 'Suggested:', 'Enforcement',
            ]):
                continue

            # Skip indented status lines (bullet points)
            if stripped.startswith('-') and ':' in stripped and len(stripped) < 80:
                continue

            # Skip empty lines in hook output
            if not stripped:
                continue

            # Stop skipping after seeing real content (non-hook-like text)
            if not stripped.startswith(('=', '-', '[', '>')):
                skip_until_separator = False

        if not skip_until_separator:
            cleaned_lines.append(line)

    text = '\n'.join(cleaned_lines)

    # Remove /edge-* command prefixes
    text = re.sub(r'^/edge-\w+\s*', '', text, flags=re.MULTILINE)

    # Collapse multiple newlines
    text = re.sub(r'\n{3,}', '\n\n', text)

    return text.strip()


def extract_user_messages(messages: List[Dict], clean: bool = True) -> List[str]:
    """
    Extract user message content from parsed messages.

    Handles Claude Code session format where messages are nested.

    Args:
        messages: List of message dictionaries
        clean: If True, filter out system noise from messages

    Returns:
        List of user message text strings
    """
    user_texts = []
    for msg in messages:
        # Claude Code session format: {"type": "user", "message": {"role": "user", "content": "..."}}
        if msg.get("type") == "user":
            nested_msg = msg.get("message", {})
            content = nested_msg.get("content", "")
            if isinstance(content, str):
                cleaned = clean_message_content(content) if clean else content
                if cleaned:
                    user_texts.append(cleaned)
            elif isinstance(content, list):
                # Handle structured content (text blocks)
                for block in content:
                    if isinstance(block, dict) and block.get("type") == "text":
                        text = block.get("text", "")
                        cleaned = clean_message_content(text) if clean else text
                        if cleaned:
                            user_texts.append(cleaned)
                    elif isinstance(block, str):
                        cleaned = clean_message_content(block) if clean else block
                        if cleaned:
                            user_texts.append(cleaned)
        # Fallback: simple format
        elif msg.get("type") == "human" or msg.get("role") == "user":
            content = msg.get("content", "")
            if isinstance(content, str):
                cleaned = clean_message_content(content) if clean else content
                if cleaned:
                    user_texts.append(cleaned)
            elif isinstance(content, list):
                for block in content:
                    if isinstance(block, dict) and block.get("type") == "text":
                        text = block.get("text", "")
                        cleaned = clean_message_content(text) if clean else text
                        if cleaned:
                            user_texts.append(cleaned)
                    elif isinstance(block, str):
                        cleaned = clean_message_content(block) if clean else block
                        if cleaned:
                            user_texts.append(cleaned)
    return user_texts


def extract_objective(messages: List[Dict]) -> Optional[str]:
    """
    Try to extract the objective/goal from messages.

    Looks for:
    - First user message (often contains the main task)
    - Messages with "objective:", "goal:", "task:" patterns
    """
    user_messages = extract_user_messages(messages)

    if not user_messages:
        return None

    # First user message is often the main objective
    first_msg = user_messages[0]

    # Look for explicit objective markers
    for msg in user_messages[:10]:  # Check first 10 messages
        lower = msg.lower()
        for marker in ["objective:", "goal:", "task:", "implement:", "fix:", "add:"]:
            if marker in lower:
                # Extract the part after the marker
                idx = lower.index(marker)
                return msg[idx:idx + 200].strip()

    # Default to first message (truncated)
    return first_msg[:200] if first_msg else None


def extract_summary(messages: List[Dict], max_user_messages: int = 3) -> str:
    """
    Build embeddable summary text from session messages.

    v1.1: Uses cleaned messages with system noise removed.

    Combines:
    - Extracted objective (cleaned)
    - First N user messages (cleaned, non-empty)

    Args:
        messages: Parsed message list
        max_user_messages: Max user messages to include (default: 3)

    Returns:
        Summary text suitable for embedding
    """
    parts = []

    # Get objective (uses cleaned extraction)
    objective = extract_objective(messages)
    if objective:
        # Clean the objective too
        cleaned_objective = clean_message_content(objective)
        if cleaned_objective:
            parts.append(f"Objective: {cleaned_objective}")

    # Get first N cleaned user messages (skip empty after cleaning)
    user_messages = extract_user_messages(messages, clean=True)

    # Filter to non-trivial messages (more than just whitespace or short commands)
    # Threshold of 10 chars catches real noise while keeping short legitimate messages
    meaningful_messages = [
        msg for msg in user_messages
        if len(msg.strip()) > 10 and not msg.strip().startswith('/')
    ][:max_user_messages]

    if meaningful_messages:
        parts.append("User intent:")
        for i, msg in enumerate(meaningful_messages, 1):
            # Truncate long messages but keep more context
            truncated = msg[:500] if len(msg) > 500 else msg
            parts.append(f"{i}. {truncated}")

    return "\n".join(parts)


def get_session_metadata(path: Path, messages: List[Dict]) -> Dict[str, Any]:
    """
    Extract metadata about a session.

    Args:
        path: Path to session file
        messages: Parsed messages

    Returns:
        Dict with session metadata
    """
    # Get session ID from filename (UUID format)
    session_id = path.stem

    # Get timestamps
    timestamps = []
    for msg in messages:
        ts = msg.get("timestamp") or msg.get("created_at")
        if ts:
            timestamps.append(ts)

    first_timestamp = timestamps[0] if timestamps else None
    last_timestamp = timestamps[-1] if timestamps else None

    # Count by type
    user_count = len(extract_user_messages(messages))
    total_count = len(messages)

    return {
        "session_id": session_id,
        "session_path": str(path),
        "message_count": total_count,
        "user_message_count": user_count,
        "first_timestamp": first_timestamp,
        "last_timestamp": last_timestamp,
        "file_size": path.stat().st_size if path.exists() else 0,
        "file_mtime": path.stat().st_mtime if path.exists() else 0,
    }


def _process_session_file(path: Path, project_name: str) -> Optional[Dict[str, Any]]:
    """
    Process a single session file into metadata and summary.

    Args:
        path: Path to session JSONL file
        project_name: Project name to include in metadata

    Returns:
        Dict with session metadata and summary, or None if parsing fails
    """
    messages = parse_session_jsonl(path)
    if not messages:
        return None

    metadata = get_session_metadata(path, messages)
    metadata["project_name"] = project_name
    summary = extract_summary(messages)

    return {
        **metadata,
        "summary": summary,
    }


def _scan_single_project(
    sessions_dir: Path,
    max_sessions: int
) -> Generator[Dict[str, Any], None, None]:
    """
    Scan sessions from a single project directory.

    Args:
        sessions_dir: Directory containing session JSONL files
        max_sessions: Maximum number of sessions to scan

    Yields:
        Dict with session metadata and summary
    """
    if not sessions_dir or not sessions_dir.exists():
        return

    project_name = extract_project_name(sessions_dir)

    # Find all JSONL files, sorted by modification time (newest first)
    session_files = list(sessions_dir.glob("*.jsonl"))
    session_files.sort(key=lambda p: p.stat().st_mtime, reverse=True)

    for path in session_files[:max_sessions]:
        result = _process_session_file(path, project_name)
        if result:
            yield result


def _scan_all_projects(max_sessions: int) -> Generator[Dict[str, Any], None, None]:
    """
    Scan sessions across all project directories.

    Args:
        max_sessions: Maximum number of sessions to scan (across all projects)

    Yields:
        Dict with session metadata and summary
    """
    project_dirs = get_all_project_dirs()
    all_session_files = []

    for project_dir in project_dirs:
        project_name = extract_project_name(project_dir)
        for path in project_dir.glob("*.jsonl"):
            all_session_files.append((path, project_name))

    # Sort all sessions by modification time (newest first)
    all_session_files.sort(key=lambda x: x[0].stat().st_mtime, reverse=True)

    for path, project_name in all_session_files[:max_sessions]:
        result = _process_session_file(path, project_name)
        if result:
            yield result


def scan_sessions(
    max_sessions: int = 100,
    sessions_dir: Path = None,
    all_projects: bool = False
) -> Generator[Dict[str, Any], None, None]:
    """
    Scan and yield session info for indexing.

    Delegates to internal functions based on all_projects flag.

    Args:
        max_sessions: Maximum number of sessions to scan
        sessions_dir: Override sessions directory (single-project mode only)
        all_projects: If True, scan all projects (cross-project search)

    Yields:
        Dict with session metadata and summary
    """
    if all_projects:
        yield from _scan_all_projects(max_sessions)
    else:
        if sessions_dir is None:
            sessions_dir = get_claude_sessions_dir()
        yield from _scan_single_project(sessions_dir, max_sessions)


def build_index(
    max_sessions: int = 100,
    force_rebuild: bool = False,
    all_projects: bool = False
) -> Tuple[int, int, List[str]]:
    """
    Build or update the embedding index.

    Args:
        max_sessions: Maximum sessions to index
        force_rebuild: If True, rebuild from scratch
        all_projects: If True, index all projects (cross-project)

    Returns:
        Tuple of (sessions_indexed, sessions_skipped, errors)
    """
    # Load existing index
    existing_metadata, existing_vectors = load_index()
    if force_rebuild or existing_metadata is None:
        existing_metadata = {
            "version": "1.1",
            "model": DEFAULT_EMBEDDING_MODEL,
            "dimension": EMBEDDING_DIMENSION,
            "sessions": [],
            "last_updated": None,
            "all_projects": all_projects,
        }
        existing_vectors = []

    # Build lookup of existing sessions by ID
    existing_sessions = {
        s["session_id"]: (i, s)
        for i, s in enumerate(existing_metadata.get("sessions", []))
    }

    indexed = 0
    skipped = 0
    errors = []
    new_sessions = []
    new_vectors = []

    for session in scan_sessions(max_sessions, all_projects=all_projects):
        session_id = session["session_id"]
        file_mtime = session.get("file_mtime", 0)

        # Check if already indexed and unchanged
        if session_id in existing_sessions and not force_rebuild:
            idx, existing = existing_sessions[session_id]
            if existing.get("file_mtime", 0) >= file_mtime:
                # Keep existing
                new_sessions.append(existing)
                if idx < len(existing_vectors):
                    new_vectors.append(existing_vectors[idx])
                skipped += 1
                continue

        # Generate embedding for summary
        summary = session.get("summary", "")
        if not summary:
            skipped += 1
            continue

        embedding = generate_embedding(summary)
        if embedding is None:
            errors.append(f"Failed to embed session {session_id}")
            skipped += 1
            continue

        # Store session metadata (without summary to save space)
        session_meta = {
            k: v for k, v in session.items()
            if k != "summary"
        }
        session_meta["summary_preview"] = summary[:200]
        session_meta["indexed_at"] = datetime.now().isoformat()

        new_sessions.append(session_meta)
        new_vectors.append(embedding)
        indexed += 1

    # Update metadata
    existing_metadata["sessions"] = new_sessions
    existing_metadata["last_updated"] = datetime.now().isoformat()

    # Save index
    save_index(existing_metadata, new_vectors)

    return indexed, skipped, errors


def incremental_update() -> Tuple[int, int, List[str]]:
    """
    Update index with only new/changed sessions.

    Returns:
        Tuple of (sessions_added, sessions_unchanged, errors)
    """
    return build_index(force_rebuild=False)


def suggest_similar_sessions(
    objective: str,
    top_k: int = None,
    min_score: float = None,
    timeout: float = None
) -> List[Dict[str, Any]]:
    """
    Suggest similar sessions based on an objective.

    This is designed to be called at session start to surface relevant
    historical context. It's optimized for speed with a timeout.

    Args:
        objective: The current session's objective
        top_k: Maximum number of suggestions to return
        min_score: Minimum similarity score to include
        timeout: Maximum time to wait for embedding (seconds)

    Returns:
        List of session dicts with: session_id, project_name, score, summary_preview
    """
    import threading
    import queue
    from fork_utils import search_similar
    from fork_config import (
        FORK_DEFAULT_TOP_K,
        FORK_MIN_SIMILARITY_SCORE,
        FORK_SUGGESTION_TIMEOUT,
        FORK_MIN_OBJECTIVE_LENGTH,
    )

    # Apply defaults from config
    if top_k is None:
        top_k = FORK_DEFAULT_TOP_K
    if min_score is None:
        min_score = FORK_MIN_SIMILARITY_SCORE
    if timeout is None:
        timeout = FORK_SUGGESTION_TIMEOUT

    if not objective or len(objective.strip()) < FORK_MIN_OBJECTIVE_LENGTH:
        return []

    # Load index (fast, from disk)
    metadata, vectors = load_index()
    if metadata is None or not vectors:
        return []

    sessions = metadata.get("sessions", [])
    if not sessions:
        return []

    # Generate embedding with timeout (daemon thread to avoid orphan leak)
    result_queue = queue.Queue()

    def embed_with_timeout():
        try:
            vec = generate_embedding(objective)
            result_queue.put(vec)
        except Exception as e:
            if os.environ.get("EDGE_DEBUG"):
                print(f"[fork] embed_with_timeout failed: {e}", file=sys.stderr)
            result_queue.put(None)

    thread = threading.Thread(target=embed_with_timeout, daemon=True)
    thread.start()
    thread.join(timeout=timeout)

    if thread.is_alive():
        # Timeout - return empty
        return []

    try:
        query_vector = result_queue.get_nowait()
    except queue.Empty:
        return []

    if query_vector is None:
        return []

    # Search for similar sessions
    results = search_similar(query_vector, vectors, top_k=top_k)

    # Format results
    suggestions = []
    for idx, score in results:
        if score < min_score:
            continue
        if idx >= len(sessions):
            continue

        session = sessions[idx]
        suggestions.append({
            "session_id": session.get("session_id", ""),
            "project_name": session.get("project_name", ""),
            "score": score,
            "summary_preview": session.get("summary_preview", "")[:100],
            "message_count": session.get("message_count", 0),
            "first_timestamp": session.get("first_timestamp"),
        })

    return suggestions
