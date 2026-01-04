#!/usr/bin/env python3
"""
Operator's Edge - Configuration and Constants
Centralized configuration for all edge utilities.
"""

# =============================================================================
# SESSION CONTEXT STATES
# =============================================================================

class SessionContext:
    """Represents the current context for orchestrator decisions."""
    NEEDS_PLAN = "needs_plan"
    NEEDS_RESEARCH = "needs_research"
    AWAITING_RESEARCH = "awaiting_research"
    READY_FOR_STEP = "ready_for_step"
    STEP_IN_PROGRESS = "step_in_progress"
    POTENTIAL_MISMATCH = "potential_mismatch"
    UNRESOLVED_MISMATCH = "unresolved_mismatch"
    NEEDS_ADAPTATION = "needs_adaptation"
    ALL_COMPLETE = "all_complete"
    NEEDS_PRUNING = "needs_pruning"
    NEEDS_SCORING = "needs_scoring"


# =============================================================================
# RESEARCH INDICATORS
# =============================================================================

# Technology/framework patterns that suggest research might be needed
RESEARCH_INDICATORS = {
    # Unfamiliar or complex technologies (extend as needed)
    "technologies": [
        "kubernetes", "k8s", "docker", "terraform", "aws", "gcp", "azure",
        "graphql", "grpc", "websocket", "webrtc", "crdt", "raft", "paxos",
        "oauth", "oidc", "saml", "jwt", "encryption", "ssl", "tls",
        "machine learning", "ml", "neural", "transformer", "llm", "embedding",
        "blockchain", "smart contract", "web3", "crypto",
        "real-time", "streaming", "pubsub", "kafka", "rabbitmq", "redis",
        "microservice", "distributed", "sharding", "replication",
        "concurrency", "parallel", "async", "multithreading"
    ],
    # Phrases that suggest ambiguity
    "ambiguity_signals": [
        "best way", "best approach", "should i", "which one", "recommend",
        "optimize", "performance", "scalable", "production-ready",
        "secure", "security", "architecture", "design pattern",
        "trade-off", "tradeoff", "pros and cons", "compare", "vs",
        "not sure", "unclear", "maybe", "might", "could"
    ],
    # Action verbs that suggest research-first approach
    "research_verbs": [
        "evaluate", "assess", "investigate", "analyze", "research",
        "understand", "learn", "explore", "compare", "benchmark"
    ]
}


# =============================================================================
# BRAINSTORM SCANNING PATTERNS
# =============================================================================

# File patterns to scan for improvement opportunities
SCAN_PATTERNS = {
    "code_markers": ["TODO", "FIXME", "HACK", "XXX", "BUG", "OPTIMIZE"],
    "skip_dirs": [".git", "node_modules", ".venv", "venv", "__pycache__", ".proof", "dist", "build"],
    "code_extensions": [".py", ".js", ".ts", ".tsx", ".jsx", ".go", ".rs", ".java", ".rb", ".php"]
}

# Complexity thresholds
COMPLEXITY_THRESHOLDS = {
    "large_file_lines": 500,
    "very_large_file_lines": 1000,
    "max_files_to_scan": 100  # Limit for performance
}


# =============================================================================
# MEMORY DECAY SETTINGS
# =============================================================================

MEMORY_SETTINGS = {
    "decay_threshold_days": 14,
    "reinforcement_threshold": 2,  # Lessons with 2+ reinforcements are kept
    "max_memory_items": 20
}


# =============================================================================
# ARCHIVE SETTINGS
# =============================================================================

ARCHIVE_SETTINGS = {
    "max_completed_steps_in_state": 1,  # Keep only 1 completed step in active state
    "max_archive_entries_to_load": 100,
    "max_search_entries": 500
}


# =============================================================================
# ENTROPY THRESHOLDS
# =============================================================================

ENTROPY_THRESHOLDS = {
    "max_completed_steps": 3,  # More than this triggers pruning suggestion
    "max_resolved_mismatches": 0  # Any resolved mismatch should be archived
}
