# v8.0 Phase 7: Metrics Dashboard & Effectiveness Tuning

## Overview

Phase 7 closes the loop on observability by making metrics actionable. We've been collecting data in Phase 5 and surfacing suggestions in Phase 6, but we can't yet:
1. **View** the aggregated effectiveness data
2. **Tune** thresholds based on actual results
3. **Detect** if interventions are actually working

## Problem Statement

Currently:
- Metrics are collected but invisible to users
- We record `drift_signals_fired` but not `course_corrections` (did Claude actually change behavior?)
- Thresholds are hardcoded (FILE_CHURN=3, CONTEXT_CHECKPOINT=75%) without evidence they're optimal
- No way to compare effectiveness across projects/users

## Proposed Components

### 7.1: Metrics CLI Command

```bash
/edge metrics           # Show summary for current project
/edge metrics --all     # Show aggregated across all sessions
/edge metrics --export  # Export to JSON for analysis
```

Output example:
```
============================================================
📊 v8.0 EFFECTIVENESS REPORT (Last 30 days)
============================================================

Sessions: 47 | Avg Duration: 32 min | Avg Context: 68%

DRIFT DETECTION
  Signals Fired: 23 (FILE_CHURN: 14, COMMAND_REPEAT: 6, STEP_STALL: 3)
  Course Corrections: 18 (78% effectiveness)
  Ignored Signals: 5

CODEBASE KNOWLEDGE
  Fixes Surfaced: 12
  Fixes Followed: 9 (75% follow rate)
  Fixes Successful: 8 (89% success rate)
  New Fixes Learned: 15

SESSION HANDOFF
  Handoffs Generated: 42
  Handoffs Used: 38 (90% adoption)
  Avg Time to First Action: 45s

SMART SUGGESTIONS
  Suggestions Shown: 67
  Suggestions Followed: 41 (61%)
  Top Effective: checkpoint (85%), auto_fix (73%)
  Low Effective: pattern_nudge (34%)

RECOMMENDATIONS
  ⚠️ Consider disabling pattern_nudge (low effectiveness)
  ✓ FILE_CHURN detection working well
  📈 Fix confidence threshold could be lowered (high success rate)
============================================================
```

### 7.2: Course Correction Detection

**Problem**: We fire drift signals but don't know if Claude changed behavior.

**Solution**: Compare tool patterns before/after signal:

```python
def detect_course_correction(session_log, signal_timestamp, lookback=5, lookahead=5):
    """
    Compare the N tool calls before a signal vs N after.

    A course correction is detected if:
    - File churn: Different file edited after signal
    - Command repeat: Different approach tried
    - Step stall: Step marked complete or abandoned
    """
    entries_before = get_entries_in_window(session_log, signal_timestamp - 5min, signal_timestamp)
    entries_after = get_entries_in_window(session_log, signal_timestamp, signal_timestamp + 5min)

    # Analyze pattern change
    files_before = extract_files(entries_before)
    files_after = extract_files(entries_after)

    # If the "problem file" (churned file) is no longer being edited, that's a correction
    problem_files = signal.metadata.get("problem_files", [])
    if problem_files and not any(f in files_after for f in problem_files):
        return True

    return False
```

This requires:
1. Storing signal timestamps in session log
2. Post-session analysis to determine corrections
3. Updating metrics with correction counts

### 7.3: Suggestion Effectiveness Tracking

**Problem**: We show suggestions but don't know if they helped.

**Solution**: Track follow-through:

```python
@dataclass
class SuggestionOutcome:
    suggestion_type: str
    suggestion_key: str
    shown_at: datetime
    followed: bool = False
    outcome_success: Optional[bool] = None  # Did following help?
```

For each suggestion type:
- **auto_fix**: Track if the suggested command was run
- **related_file**: Track if the related files were edited
- **checkpoint**: Track if /compact was used
- **drift_warning**: Track course correction
- **pattern_nudge**: Track if the suggested action was taken

### 7.4: Adaptive Thresholds

**Problem**: Hardcoded thresholds may not suit all projects.

**Solution**: Learn optimal thresholds from data:

```python
def calculate_optimal_threshold(metric_type, sessions):
    """
    Calculate optimal threshold based on intervention effectiveness.

    For FILE_CHURN:
    - Too low (1-2): Too many false positives, users ignore
    - Too high (5+): Signals fire too late to help
    - Optimal: Threshold where correction rate is highest
    """
    # Group sessions by threshold at time of signal
    # Calculate correction rate per threshold
    # Return threshold with best correction rate
```

Store learned thresholds in project config:
```yaml
# .proof/config.yaml
v8_thresholds:
  file_churn: 3  # default
  command_repeat: 2
  context_checkpoint: 0.75
  auto_fix_confidence: 0.6
  learned_at: "2024-01-15"
  sample_size: 47
```

## Implementation Plan

### Files to Create
- `metrics_cli.py` - CLI interface for metrics viewing
- `course_correction.py` - Post-hoc correction detection
- `suggestion_tracker.py` - Suggestion follow-through tracking
- `threshold_optimizer.py` - Adaptive threshold calculation

### Files to Modify
- `session_metrics.py` - Add suggestion outcome tracking
- `smart_suggestions.py` - Log suggestions for tracking
- `drift_detector.py` - Store signal timestamps in session log
- `post_tool.py` - Check for course corrections
- `stop_gate.py` - Run post-session analysis

### Tests
- `test_metrics_cli.py` - CLI output formatting
- `test_course_correction.py` - Correction detection logic
- `test_suggestion_tracker.py` - Follow-through tracking
- `test_threshold_optimizer.py` - Threshold calculation

## Success Criteria

1. User can run `/edge metrics` and see clear effectiveness data
2. Course corrections are detected with >80% accuracy
3. Suggestion effectiveness is tracked for all 5 types
4. At least one threshold is auto-tuned based on data

## Dependencies

- Phase 5 (Metrics) - collecting the raw data
- Phase 6 (Suggestions) - generating the suggestions to track

## Risks

1. **Privacy**: Metrics contain session details - need clear data retention policy
2. **Noise**: Early data may have too few samples for reliable thresholds
3. **Complexity**: Course correction detection may be too fuzzy

## Timeline Estimate

- 7.1 Metrics CLI: 2-3 hours
- 7.2 Course Correction: 3-4 hours
- 7.3 Suggestion Tracking: 2-3 hours
- 7.4 Adaptive Thresholds: 3-4 hours
- Testing: 3-4 hours

Total: ~15-18 hours of implementation work
