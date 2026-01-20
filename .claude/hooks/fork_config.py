#!/usr/bin/env python3
"""
Operator's Edge - Fork Configuration
Named constants for Smart Forking (/edge-fork).

Centralizes magic numbers for maintainability and documentation.
"""

# =============================================================================
# SIMILARITY THRESHOLDS
# =============================================================================
FORK_MIN_SIMILARITY_SCORE = 0.45    # Minimum cosine similarity for suggestions
FORK_DEFAULT_TOP_K = 3              # Default number of suggestions to return
FORK_SEARCH_TOP_K = 5               # Default for explicit search queries

# =============================================================================
# TIMEOUTS (seconds)
# =============================================================================
FORK_SUGGESTION_TIMEOUT = 2.0       # Max time for auto-suggest at session start
FORK_EMBEDDING_TIMEOUT = 30.0       # Max time for single embedding generation

# =============================================================================
# VALIDATION THRESHOLDS (characters)
# =============================================================================
FORK_MIN_OBJECTIVE_LENGTH = 10      # Min chars to attempt objective search
FORK_MIN_OBJECTIVE_DISPLAY = 20     # Min chars to show suggestions
FORK_MIN_MESSAGE_LENGTH = 10        # Min chars for meaningful message in summary

# =============================================================================
# INDEX CONFIGURATION
# =============================================================================
FORK_MAX_SESSIONS_DEFAULT = 100     # Default max sessions to scan/index
FORK_SUMMARY_MAX_MESSAGES = 3       # User messages to include in summary
FORK_SUMMARY_MAX_CHARS = 500        # Max chars per message in summary
FORK_PREVIEW_LENGTH = 200           # Summary preview length in index

# =============================================================================
# SEARCH BACKEND THRESHOLDS
# =============================================================================
FORK_FAISS_MIN_VECTORS = 10         # Min vectors to use FAISS (below this, linear is fine)
