#!/usr/bin/env python3
"""
Proof Visualizer Configuration
Constants, thresholds, and tool classifications.
"""

# Tool classification for action types
READ_TOOLS = ('Read', 'Glob', 'Grep', 'LSP', 'WebFetch', 'WebSearch')
EDIT_TOOLS = ('Edit', 'Write', 'NotebookEdit')
RUN_TOOLS = ('Bash',)

# Phase detection defaults
DEFAULT_MIN_STREAK = 3
DEFAULT_MIN_PHASE_SIZE = 10

# Anomaly detection (3σ threshold)
ANOMALY_SIGMA = 3

# CTI drift threshold
CTI_DRIFT_THRESHOLD = 10.0

# Constellation mode settings
CONSTELLATION_STARS = 7      # Top N nodes get full opacity
CONSTELLATION_CONTEXT = 15   # Next N nodes get medium opacity

# Visualization defaults
HOVER_REVEAL_RADIUS = 100    # Pixels for hover proximity reveal


def get_action_type(tool: str, success: bool) -> str:
    """Classify tool into action type for visualization."""
    if not success:
        return 'fail'
    elif tool in READ_TOOLS:
        return 'read'
    elif tool in EDIT_TOOLS:
        return 'edit'
    elif tool in RUN_TOOLS:
        return 'run'
    else:
        return 'other'
