#!/usr/bin/env python3
"""
Operator's Edge Core - Platform-Agnostic Workflow System

This package contains the platform-agnostic core logic for Operator's Edge.
It can be used by both Claude Code (via hooks) and Codex CLI (via skills).

Usage:
    from edge_core import get_project_dir, load_state, save_state

Platform Detection:
    - Claude Code: Uses CLAUDE_PROJECT_DIR environment variable
    - Codex CLI: Uses CODEX_PROJECT_DIR environment variable
    - Fallback: Uses current working directory
"""

from edge_core.platform import (
    get_project_dir,
    get_state_dir,
    get_proof_dir,
    get_archive_file,
    detect_platform,
    Platform,
)

__version__ = "1.0.0"
__all__ = [
    "get_project_dir",
    "get_state_dir",
    "get_proof_dir",
    "get_archive_file",
    "detect_platform",
    "Platform",
]
