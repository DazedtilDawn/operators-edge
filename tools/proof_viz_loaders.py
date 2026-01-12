#!/usr/bin/env python3
"""
Proof Visualizer - Data Loading
File I/O functions for loading proof logs and CTI history.
"""
import json
import re
from pathlib import Path
from typing import List, Dict, Any, Optional


def load_proof_log(path: Path) -> List[Dict[str, Any]]:
    """Load JSONL proof log."""
    entries = []
    with open(path) as f:
        for line in f:
            line = line.strip()
            if line:
                try:
                    entries.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
    return entries


def extract_file_path(input_preview: Any) -> Optional[str]:
    """Extract file path from various input_preview formats."""
    if isinstance(input_preview, dict):
        for key in ('file', 'file_path', 'path'):
            if key in input_preview:
                return input_preview[key]
    elif isinstance(input_preview, str):
        # Check if it looks like a file path
        if '/' in input_preview or '\\' in input_preview:
            # Extract path from string like "{'file': '/path/to/file'}"
            match = re.search(r"['\"]?(?:file|file_path|path)['\"]?\s*:\s*['\"]([^'\"]+)['\"]", input_preview)
            if match:
                return match.group(1)
            # Or just return if it looks like a path
            if input_preview.startswith('/') or input_preview.startswith('C:'):
                return input_preview
    return None


def load_cti_history(history_path: Path) -> List[Dict]:
    """Load CTI history from CSV."""
    if not history_path.exists():
        return []
    history = []
    with open(history_path) as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith('timestamp'):  # skip header
                parts = line.split(',')
                if len(parts) >= 4:
                    history.append({
                        'timestamp': parts[0],
                        'events': int(parts[1]),
                        'cti': float(parts[2]),
                        'success_rate': float(parts[3]),
                    })
    return history
