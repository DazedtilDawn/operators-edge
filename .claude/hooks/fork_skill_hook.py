#!/usr/bin/env python3
"""
Operator's Edge - Fork Skill Hook
Command handler for /edge-fork.

Triggered by: UserPromptSubmit (matcher: "/edge-fork")

Usage:
    /edge-fork                    # Show usage and status
    /edge-fork "query"            # Search for similar sessions
    /edge-fork --index            # Build/rebuild index
    /edge-fork --status           # Show connection and index info
    /edge-fork <session-id>       # Show fork command for session
"""
import json
import os
import sys
import re
from datetime import datetime
from pathlib import Path
from typing import Optional, List, Tuple

# Add hooks directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from fork_utils import (
    check_lmstudio_available,
    generate_embedding,
    load_index,
    search_similar,
    get_index_stats,
    get_lmstudio_url,
    get_search_backend,
)
from fork_indexer import (
    build_index,
    get_claude_sessions_dir,
    get_all_project_dirs,
    extract_project_name,
    scan_sessions,
)


def format_timestamp(ts: str) -> str:
    """Format ISO timestamp to readable date."""
    if not ts:
        return "unknown"
    try:
        dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
        return dt.strftime("%b %d")
    except (ValueError, TypeError):
        return ts[:10] if ts else "unknown"


def handle_status(show_all_projects: bool = False) -> str:
    """Handle --status command - show connection and index info."""
    lines = [
        "=" * 60,
        "SMART FORK - Status",
        "=" * 60,
        "",
    ]

    # LM Studio connection
    lines.append("LM Studio Connection:")
    available, msg = check_lmstudio_available()
    if available:
        lines.append(f"  [OK] {msg}")
    else:
        lines.append(f"  [FAIL] {msg}")
    lines.append(f"  URL: {get_lmstudio_url()}")
    lines.append("")

    # Sessions directory
    lines.append("Current Project Sessions:")
    sessions_dir = get_claude_sessions_dir()
    if sessions_dir and sessions_dir.exists():
        session_count = len(list(sessions_dir.glob("*.jsonl")))
        lines.append(f"  [OK] {sessions_dir.name}")
        lines.append(f"  Sessions found: {session_count}")
    else:
        lines.append(f"  [FAIL] Sessions directory not found")
    lines.append("")

    # All projects (if requested or index is cross-project)
    if show_all_projects:
        lines.append("All Projects:")
        all_projects = get_all_project_dirs()
        total_sessions = 0
        for project_dir in all_projects:
            project_name = extract_project_name(project_dir)
            session_count = len(list(project_dir.glob("*.jsonl")))
            total_sessions += session_count
            lines.append(f"  - {project_name}: {session_count} sessions")
        lines.append(f"  Total: {total_sessions} sessions across {len(all_projects)} projects")
        lines.append("")

    # Index status
    lines.append("Embedding Index:")
    stats = get_index_stats()
    if stats["exists"]:
        lines.append(f"  [OK] Index exists")
        lines.append(f"  Sessions indexed: {stats['sessions']}")
        lines.append(f"  Model: {stats['model']}")
        lines.append(f"  Search backend: {stats.get('search_backend', 'unknown')}")
        lines.append(f"  Last updated: {format_timestamp(stats['last_updated'])}")
    else:
        lines.append(f"  [NONE] No index found")
        lines.append(f"  Search backend: {get_search_backend()}")
        lines.append(f"  Run '/edge-fork --index' to build")
    lines.append("")

    lines.extend(["=" * 60])
    return "\n".join(lines)


def handle_index(force: bool = False, all_projects: bool = False) -> str:
    """Handle --index command - build or rebuild index."""
    scope = "All Projects" if all_projects else "Current Project"
    lines = [
        "=" * 60,
        f"SMART FORK - Building Index ({scope})",
        "=" * 60,
        "",
    ]

    # Check LM Studio first
    available, msg = check_lmstudio_available()
    if not available:
        lines.extend([
            "ERROR: LM Studio not available",
            f"  {msg}",
            "",
            "Make sure LM Studio is running with an embedding model loaded.",
            f"  Expected URL: {get_lmstudio_url()}",
            "=" * 60,
        ])
        return "\n".join(lines)

    lines.append(f"LM Studio: {msg}")
    if all_projects:
        project_dirs = get_all_project_dirs()
        lines.append(f"Scanning {len(project_dirs)} projects...")
    lines.append("")

    # Build index
    lines.append("Indexing sessions...")
    indexed, skipped, errors = build_index(force_rebuild=force, all_projects=all_projects)

    lines.extend([
        "",
        f"Results:",
        f"  Sessions indexed: {indexed}",
        f"  Sessions skipped: {skipped}",
    ])

    if errors:
        lines.append(f"  Errors: {len(errors)}")
        for err in errors[:3]:
            lines.append(f"    - {err}")
        if len(errors) > 3:
            lines.append(f"    ... and {len(errors) - 3} more")

    # Show stats
    stats = get_index_stats()
    lines.extend([
        "",
        f"Index now contains {stats['sessions']} sessions",
        "",
        "=" * 60,
    ])

    return "\n".join(lines)


def handle_search(query: str, top_k: int = 5) -> str:
    """Handle search query - find similar sessions."""
    lines = [
        "=" * 60,
        "SMART FORK - Search Results",
        "=" * 60,
        "",
        f"Query: \"{query}\"",
        "",
    ]

    # Load index
    metadata, vectors = load_index()
    if metadata is None or not vectors:
        lines.extend([
            "ERROR: No index found",
            "",
            "Run '/edge-fork --index' to build the index first.",
            "=" * 60,
        ])
        return "\n".join(lines)

    # Check LM Studio
    available, msg = check_lmstudio_available()
    if not available:
        lines.extend([
            "ERROR: LM Studio not available",
            f"  {msg}",
            "",
            "LM Studio is needed to generate query embedding.",
            "=" * 60,
        ])
        return "\n".join(lines)

    # Generate query embedding
    query_vector = generate_embedding(query)
    if query_vector is None:
        lines.extend([
            "ERROR: Failed to generate query embedding",
            "",
            "Check LM Studio logs for details.",
            "=" * 60,
        ])
        return "\n".join(lines)

    # Search
    results = search_similar(query_vector, vectors, top_k=top_k)
    sessions = metadata.get("sessions", [])

    if not results:
        lines.extend([
            "No matching sessions found.",
            "=" * 60,
        ])
        return "\n".join(lines)

    # Format results
    for i, (idx, score) in enumerate(results, 1):
        if idx >= len(sessions):
            continue

        session = sessions[idx]
        session_id = session.get("session_id", "unknown")
        short_id = session_id[:8]
        timestamp = format_timestamp(session.get("first_timestamp"))
        msg_count = session.get("message_count", 0)
        project_name = session.get("project_name", "")
        preview = session.get("summary_preview", "")[:60]

        # Include project name if cross-project search
        project_tag = f" [{project_name}]" if project_name else ""
        lines.extend([
            f"{i}. [{score:.2f}] {short_id}{project_tag} - {timestamp} ({msg_count} messages)",
            f"   \"{preview}...\"",
            "",
        ])

    # Fork instructions
    if results:
        best_idx, best_score = results[0]
        best_session = sessions[best_idx] if best_idx < len(sessions) else None
        if best_session:
            full_id = best_session.get("session_id", "")
            lines.extend([
                "-" * 60,
                "To fork from top result:",
                f"  claude --resume {full_id} --fork-session",
                "",
            ])

    lines.extend(["=" * 60])
    return "\n".join(lines)


def handle_session_id(session_id: str) -> str:
    """Handle session ID lookup - show fork command."""
    lines = [
        "=" * 60,
        "SMART FORK - Session Details",
        "=" * 60,
        "",
    ]

    # Load index
    metadata, _ = load_index()
    if metadata is None:
        lines.extend([
            "ERROR: No index found",
            "",
            "Run '/edge-fork --index' to build the index first.",
            "=" * 60,
        ])
        return "\n".join(lines)

    sessions = metadata.get("sessions", [])

    # Find matching session
    matching = None
    for session in sessions:
        sid = session.get("session_id", "")
        if sid.startswith(session_id) or session_id in sid:
            matching = session
            break

    if not matching:
        # Try scanning unindexed sessions
        sessions_dir = get_claude_sessions_dir()
        if sessions_dir:
            for path in sessions_dir.glob("*.jsonl"):
                if session_id in path.stem:
                    matching = {"session_id": path.stem, "session_path": str(path)}
                    break

    if not matching:
        lines.extend([
            f"Session '{session_id}' not found",
            "",
            "Try searching with /edge-fork \"query\" first.",
            "=" * 60,
        ])
        return "\n".join(lines)

    # Show session details
    full_id = matching.get("session_id", "")
    lines.extend([
        f"Session ID: {full_id}",
        f"Messages: {matching.get('message_count', 'unknown')}",
        f"Date: {format_timestamp(matching.get('first_timestamp'))}",
        "",
    ])

    if matching.get("summary_preview"):
        lines.extend([
            "Preview:",
            f"  {matching['summary_preview'][:200]}...",
            "",
        ])

    lines.extend([
        "-" * 60,
        "Fork command:",
        f"  claude --resume {full_id} --fork-session",
        "",
        "=" * 60,
    ])

    return "\n".join(lines)


def handle_usage() -> str:
    """Show usage information."""
    return """
======================================================================
SMART FORK (/edge-fork)
======================================================================

Semantic search across past Claude sessions and fork from relevant
historical context.

USAGE:
  /edge-fork                     Show this help and status
  /edge-fork "query"             Search for similar sessions
  /edge-fork --index             Build/rebuild embedding index
  /edge-fork --status            Show connection and index info
  /edge-fork <session-id>        Show fork command for session

CROSS-PROJECT SEARCH:
  /edge-fork --all-projects --index    Index all projects
  /edge-fork --all-projects "query"    Search across all projects
  /edge-fork --all-projects --status   Show all projects

EXAMPLES:
  /edge-fork "authentication hooks"
  /edge-fork "refactoring database queries"
  /edge-fork --all-projects "performance optimization"
  /edge-fork 5ce9f4a1

SETUP:
  1. Start LM Studio with embedding model (nomic-embed-text-v1.5)
  2. Run '/edge-fork --index' to build the index
  3. Search with '/edge-fork "your query"'

CONFIGURATION:
  LM Studio URL: Set LMSTUDIO_URL env var or edit config
  Default: http://192.168.254.68:1234

======================================================================
""" + handle_status()


def parse_args(user_input: str) -> Tuple[str, Optional[str], bool]:
    """
    Parse /edge-fork command arguments.

    Returns:
        Tuple of (command, argument, all_projects)
        Commands: 'help', 'status', 'index', 'search', 'session'
    """
    # Remove /edge-fork prefix
    text = user_input.strip()
    for prefix in ["/edge-fork", "edge-fork"]:
        if text.lower().startswith(prefix):
            text = text[len(prefix):].strip()
            break

    # Check for --all-projects flag
    all_projects = False
    if "--all-projects" in text or "-a" in text.split():
        all_projects = True
        text = text.replace("--all-projects", "").replace(" -a ", " ").strip()
        # Clean up any double spaces
        text = re.sub(r'\s+', ' ', text).strip()

    if not text:
        return "help", None, all_projects

    # Check for flags
    if text in ["--status", "-s", "status"]:
        return "status", None, all_projects

    if text in ["--index", "-i", "index", "--rebuild"]:
        return "index", None, all_projects

    if text == "--force":
        return "index_force", None, all_projects

    # Check for quoted search query
    match = re.match(r'^["\'](.+?)["\']', text)
    if match:
        return "search", match.group(1), all_projects

    # Check for session ID (alphanumeric, 6+ chars)
    if re.match(r'^[a-f0-9-]{6,}$', text, re.IGNORECASE):
        return "session", text, all_projects

    # Treat unquoted text as search query
    return "search", text, all_projects


def main():
    """Main entry point - process /edge-fork command."""
    # Get user input from stdin
    user_input = ""
    if not sys.stdin.isatty():
        user_input = sys.stdin.read()

    # Parse arguments
    command, arg, all_projects = parse_args(user_input)

    # Route to handler
    if command == "help":
        print(handle_usage())
    elif command == "status":
        print(handle_status(show_all_projects=all_projects))
    elif command == "index":
        print(handle_index(force=False, all_projects=all_projects))
    elif command == "index_force":
        print(handle_index(force=True, all_projects=all_projects))
    elif command == "search":
        print(handle_search(arg))
    elif command == "session":
        print(handle_session_id(arg))
    else:
        print(handle_usage())


if __name__ == "__main__":
    main()
