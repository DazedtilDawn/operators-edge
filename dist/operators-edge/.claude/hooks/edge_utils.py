#!/usr/bin/env python3
"""
Operator's Edge - Shared Hook Utilities
Facade module that re-exports all utilities for backward compatibility.

After v2.3 refactor, functionality is split into:
- edge_config.py: Constants, patterns, SessionContext
- state_utils.py: YAML parsing, paths, hashing, state helpers
- archive_utils.py: Archive system, pruning, entropy
- research_utils.py: Research detection and prompt generation
- brainstorm_utils.py: Project scanning for improvements
- orchestration_utils.py: Context detection, memory, orchestrator

This file re-exports everything for backward compatibility.
Hooks can continue to `from edge_utils import X` and it will work.
"""

# =============================================================================
# RE-EXPORTS FROM edge_config.py
# =============================================================================
from edge_config import (
    SessionContext,
    RESEARCH_INDICATORS,
    SCAN_PATTERNS,
    COMPLEXITY_THRESHOLDS,
    MEMORY_SETTINGS,
    ARCHIVE_SETTINGS,
    ENTROPY_THRESHOLDS,
)

# =============================================================================
# RE-EXPORTS FROM state_utils.py
# =============================================================================
from state_utils import (
    # Path utilities
    get_project_dir,
    get_state_dir,
    get_proof_dir,
    get_archive_file,
    # YAML parsing
    parse_yaml_value,
    parse_simple_yaml,
    parse_yaml_block,
    parse_nested_dict,
    load_yaml_state,
    # Hashing
    file_hash,
    save_state_hash,
    get_start_hash,
    # Failure logging
    log_failure,
    get_recent_failures,
    # Proof logging
    log_proof,
    # Hook response
    respond,
    # State helpers
    get_current_step,
    get_step_by_status,
    count_completed_steps,
    get_unresolved_mismatches,
    get_memory_items,
    get_schema_version,
    generate_mismatch_id,
    compute_normalized_current_step,
    normalize_current_step_file,
)

# =============================================================================
# RE-EXPORTS FROM archive_utils.py
# =============================================================================
from archive_utils import (
    # Archive logging
    log_to_archive,
    archive_completed_step,
    archive_resolved_mismatch,
    archive_completed_objective,
    archive_decayed_lesson,
    archive_completed_research,
    # Archive retrieval
    load_archive,
    search_archive,
    get_archive_stats,
    # Entropy checking
    check_state_entropy,
    # Pruning
    identify_prunable_steps,
    identify_prunable_mismatches,
    identify_decayed_memory,
    compute_prune_plan,
    estimate_entropy_reduction,
)

# =============================================================================
# RE-EXPORTS FROM research_utils.py
# =============================================================================
from research_utils import (
    # ID generation
    generate_research_id,
    # State access
    get_research_items,
    get_pending_research,
    get_blocking_research,
    # Need detection
    scan_for_research_needs,
    # Prompt generation
    generate_research_prompt,
    # Item management
    create_research_item,
    add_research_to_state,
    update_research_status,
    add_research_results,
    # Summary
    get_research_summary,
)

# =============================================================================
# RE-EXPORTS FROM brainstorm_utils.py
# =============================================================================
from brainstorm_utils import (
    # Scanning
    scan_code_markers,
    scan_large_files,
    scan_archive_patterns,
    scan_state_patterns,
    # Challenge generation
    generate_suggested_challenges,
    # Full scan
    run_brainstorm_scan,
    format_scan_results,
)

# =============================================================================
# RE-EXPORTS FROM yolo_config.py
# =============================================================================
from yolo_config import (
    # Enums
    TrustLevel,
    # Constants
    AUTO_TOOLS,
    SUPERVISED_TOOLS,
    COMMAND_CLASSIFIED_TOOLS,
    AUTO_BASH_PATTERNS,
    SUPERVISED_BASH_PATTERNS,
    BLOCKED_BASH_PATTERNS,
    CONFIRM_BASH_PATTERNS,
    BATCH_DEFAULTS,
    YOLO_STATE_FILE,
    YOLO_CONFIG_FILE,
    # Classification
    classify_bash_command,
    classify_action,
    is_hard_blocked,
    # State management
    get_default_yolo_state,
    get_default_yolo_config,
)

# =============================================================================
# RE-EXPORTS FROM eval_utils.py
# =============================================================================
from eval_utils import (
    DEFAULT_EVALS_CONFIG,
    get_evals_config,
    get_eval_state_file,
    load_eval_state,
    save_eval_state,
    auto_triage,
    build_state_snapshot,
    get_eval_base_dir,
    create_eval_run_dir,
    write_snapshot,
    compute_state_diff,
    write_diff,
    run_invariant_checks,
    start_eval_run,
    finish_eval_run,
    log_eval_run,
    load_eval_runs,
    has_eval_run_since,
    handle_eval_failure,
    create_mismatch_from_eval,
    append_mismatch_to_file,
    cleanup_old_snapshots,
    get_snapshot_stats,
    DEFAULT_RETENTION_DAYS,
    FAILURE_RETENTION_DAYS,
)

# =============================================================================
# RE-EXPORTS FROM orchestration_utils.py
# =============================================================================
from orchestration_utils import (
    # Context detection
    detect_session_context,
    get_orchestrator_suggestion,
    # Memory system
    surface_relevant_memory,
    reinforce_memory,
    add_memory_item,
    retrieve_from_archive,
    resurrect_archived_lesson,
    get_memory_summary,
    # Lesson similarity (v2.5)
    LESSON_THEMES,
    STOPWORDS,
    get_lesson_text,
    get_lesson_keywords,
    detect_lesson_theme,
    compare_lessons,
    find_similar_lesson,
    group_lessons_by_theme,
    identify_consolidation_candidates,
    consolidate_lessons,
    extract_lessons_from_objective,
    format_lesson_suggestions,
    # Reflection analysis
    ADAPTATION_CHECKS,
    CHECK_IMPROVEMENTS,
    analyze_score_patterns,
    get_recurring_failures,
    get_improvement_suggestion,
    generate_reflection_summary,
    generate_improvement_challenges,
)

# =============================================================================
# MODULE INFO
# =============================================================================
__version__ = "2.6.0"
__all__ = [
    # Config
    "SessionContext",
    "RESEARCH_INDICATORS",
    "SCAN_PATTERNS",
    "COMPLEXITY_THRESHOLDS",
    "MEMORY_SETTINGS",
    "ARCHIVE_SETTINGS",
    "ENTROPY_THRESHOLDS",
    # State
    "get_project_dir",
    "get_state_dir",
    "get_proof_dir",
    "get_archive_file",
    "parse_yaml_value",
    "parse_simple_yaml",
    "parse_yaml_block",
    "parse_nested_dict",
    "load_yaml_state",
    "file_hash",
    "save_state_hash",
    "get_start_hash",
    "log_failure",
    "get_recent_failures",
    "log_proof",
    "respond",
    "get_current_step",
    "get_step_by_status",
    "count_completed_steps",
    "get_unresolved_mismatches",
    "get_memory_items",
    "get_schema_version",
    "generate_mismatch_id",
    "compute_normalized_current_step",
    "normalize_current_step_file",
    # Archive
    "log_to_archive",
    "archive_completed_step",
    "archive_resolved_mismatch",
    "archive_completed_objective",
    "archive_decayed_lesson",
    "archive_completed_research",
    "load_archive",
    "search_archive",
    "get_archive_stats",
    "check_state_entropy",
    "identify_prunable_steps",
    "identify_prunable_mismatches",
    "identify_decayed_memory",
    "compute_prune_plan",
    "estimate_entropy_reduction",
    # Research
    "generate_research_id",
    "get_research_items",
    "get_pending_research",
    "get_blocking_research",
    "scan_for_research_needs",
    "generate_research_prompt",
    "create_research_item",
    "add_research_to_state",
    "update_research_status",
    "add_research_results",
    "get_research_summary",
    # Brainstorm
    "scan_code_markers",
    "scan_large_files",
    "scan_archive_patterns",
    "scan_state_patterns",
    "generate_suggested_challenges",
    "run_brainstorm_scan",
    "format_scan_results",
    # Orchestration
    "detect_session_context",
    "get_orchestrator_suggestion",
    "surface_relevant_memory",
    "reinforce_memory",
    "add_memory_item",
    "retrieve_from_archive",
    "resurrect_archived_lesson",
    "get_memory_summary",
    # Lesson similarity
    "LESSON_THEMES",
    "STOPWORDS",
    "get_lesson_text",
    "get_lesson_keywords",
    "detect_lesson_theme",
    "compare_lessons",
    "find_similar_lesson",
    "group_lessons_by_theme",
    "identify_consolidation_candidates",
    "consolidate_lessons",
    "extract_lessons_from_objective",
    "format_lesson_suggestions",
    # Reflection
    "ADAPTATION_CHECKS",
    "CHECK_IMPROVEMENTS",
    "analyze_score_patterns",
    "get_recurring_failures",
    "get_improvement_suggestion",
    "generate_reflection_summary",
    "generate_improvement_challenges",
    # YOLO mode
    "TrustLevel",
    "AUTO_TOOLS",
    "SUPERVISED_TOOLS",
    "COMMAND_CLASSIFIED_TOOLS",
    "AUTO_BASH_PATTERNS",
    "SUPERVISED_BASH_PATTERNS",
    "BLOCKED_BASH_PATTERNS",
    "CONFIRM_BASH_PATTERNS",
    "BATCH_DEFAULTS",
    "YOLO_STATE_FILE",
    "YOLO_CONFIG_FILE",
    "classify_bash_command",
    "classify_action",
    "is_hard_blocked",
    "get_default_yolo_state",
    "get_default_yolo_config",
    # Evals
    "DEFAULT_EVALS_CONFIG",
    "get_evals_config",
    "get_eval_state_file",
    "load_eval_state",
    "save_eval_state",
    "auto_triage",
    "build_state_snapshot",
    "get_eval_base_dir",
    "create_eval_run_dir",
    "write_snapshot",
    "compute_state_diff",
    "write_diff",
    "run_invariant_checks",
    "start_eval_run",
    "finish_eval_run",
    "log_eval_run",
    "load_eval_runs",
    "has_eval_run_since",
]
