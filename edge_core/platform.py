#!/usr/bin/env python3
"""
Operator's Edge Core - Platform Detection

Abstracts platform-specific paths and environment variables.
Supports: Claude Code, Codex CLI, and generic fallback.
"""
import os
from enum import Enum
from pathlib import Path


class Platform(Enum):
    """Detected runtime platform."""
    CLAUDE_CODE = "claude_code"
    CODEX_CLI = "codex_cli"
    GENERIC = "generic"


def detect_platform() -> Platform:
    """
    Detect which platform we're running on based on environment.

    Returns:
        Platform enum indicating the detected runtime.
    """
    if os.environ.get("CLAUDE_PROJECT_DIR"):
        return Platform.CLAUDE_CODE
    if os.environ.get("CODEX_PROJECT_DIR"):
        return Platform.CODEX_CLI
    # Could also check for CODEX_HOME or other Codex-specific vars
    if os.environ.get("CODEX_HOME"):
        return Platform.CODEX_CLI
    return Platform.GENERIC


def get_project_dir() -> Path:
    """
    Get the project directory, auto-detecting platform.

    Priority:
        1. CLAUDE_PROJECT_DIR (Claude Code)
        2. CODEX_PROJECT_DIR (Codex CLI)
        3. Current working directory (fallback)

    Returns:
        Path to the project root directory.
    """
    # Claude Code sets this
    claude_dir = os.environ.get("CLAUDE_PROJECT_DIR")
    if claude_dir:
        return Path(claude_dir)

    # Codex CLI might set this (to be confirmed)
    codex_dir = os.environ.get("CODEX_PROJECT_DIR")
    if codex_dir:
        return Path(codex_dir)

    # Fallback to current directory
    return Path(os.getcwd())


def get_state_dir() -> Path:
    """
    Get the state directory for storing session data.

    Claude Code: .claude/state/
    Codex CLI: .codex/state/ (or .claude/state/ for compatibility)

    For now, we use .claude/state/ universally for schema compatibility.
    """
    return get_project_dir() / ".claude" / "state"


def get_proof_dir() -> Path:
    """Get the .proof directory for logs and archives."""
    return get_project_dir() / ".proof"


def get_archive_file() -> Path:
    """Get the archive file path."""
    return get_proof_dir() / "archive.jsonl"


def get_active_context_file() -> Path:
    """Get the active_context.yaml file path."""
    return get_project_dir() / "active_context.yaml"


def get_config_dir() -> Path:
    """
    Get the configuration directory for the current platform.

    Claude Code: .claude/
    Codex CLI: .codex/ (but may also use .claude/ for compatibility)
    """
    platform = detect_platform()
    if platform == Platform.CODEX_CLI:
        # Check if .codex exists, otherwise fall back to .claude
        codex_dir = get_project_dir() / ".codex"
        if codex_dir.exists():
            return codex_dir
    return get_project_dir() / ".claude"
