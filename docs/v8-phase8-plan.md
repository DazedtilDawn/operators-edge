# v8.0 Phase 8: Active Intervention

## Overview

Phase 8 moves from **passive supervision** to **active intervention**. Instead of just warning Claude about problems, the system can take corrective action.

## Current State (Phases 1-6)

Currently, v8.0 operates in "supervisor mode":
- Surfaces warnings (drift signals, context alerts)
- Suggests fixes (known fix lookup)
- Recommends actions (smart suggestions)

But Claude must choose to act on these. The system is advisory only.

## The Opportunity

High-confidence interventions could be automated:
- Known fix with 90%+ confidence → auto-apply
- Context at 95%+ → auto-checkpoint
- Same error 3x → auto-inject previous fix context

This requires:
1. **Confidence calibration** from Phase 7 metrics
2. **User opt-in** for autonomous actions
3. **Rollback mechanisms** for mistakes

## Proposed Components

### 8.1: Auto-Apply Known Fixes

**Trigger**: Bash command fails with error that matches known fix at ≥90% confidence

**Action**: Automatically inject fix commands into Claude's next response

```python
def should_auto_apply_fix(fix: KnownFix, config: ProjectConfig) -> bool:
    """Determine if a fix should be auto-applied."""
    if not config.auto_fix_enabled:
        return False

    if fix.confidence < config.auto_fix_threshold:  # Default 0.9
        return False

    if fix.times_used < config.auto_fix_min_uses:  # Default 3
        return False

    # Additional safety checks
    if fix.involves_destructive_commands():
        return False

    return True

def inject_auto_fix(fix: KnownFix) -> str:
    """Generate context injection for auto-fix."""
    return f"""
🔧 AUTO-FIX ACTIVATED (Confidence: {fix.confidence*100:.0f}%)

This error was fixed {fix.times_used} times before using:
{chr(10).join(f'  $ {cmd}' for cmd in fix.fix_commands)}

Proceeding with fix automatically. If this doesn't work, the
auto-fix will be disabled for this error pattern.
"""
```

**Hook Integration**: In `pre_tool.py`, when a Bash command is about to execute:
1. Check if previous command failed
2. Look up known fix for that error
3. If auto-apply criteria met, modify the command or inject context

### 8.2: Proactive Context Injection

**Problem**: Claude often rediscovers things it learned in previous sessions.

**Solution**: Inject relevant context at session start and at key decision points.

```python
def get_proactive_context(objective: str, current_file: str) -> Optional[str]:
    """
    Build proactive context injection based on:
    - Previous session handoffs
    - Known fixes for this file
    - Co-change patterns
    - Learned patterns from archive
    """
    context_parts = []

    # Check if this file has known issues
    file_knowledge = get_file_knowledge(current_file)
    if file_knowledge.common_errors:
        context_parts.append(format_file_warnings(file_knowledge))

    # Check if similar objective was attempted before
    similar_sessions = find_similar_objectives(objective, max_results=3)
    if similar_sessions:
        context_parts.append(format_prior_attempts(similar_sessions))

    # Check for co-change patterns
    related = get_related_files(current_file, min_strength=0.7)
    if related:
        context_parts.append(format_cochange_reminder(related))

    if context_parts:
        return "\n\n".join([
            "📚 PROACTIVE CONTEXT (from previous sessions)",
            "=" * 50,
            *context_parts,
            "=" * 50
        ])

    return None
```

**Hook Integration**: In `session_start.py` and `pre_tool.py`:
1. At session start: Inject objective-relevant context
2. Before file edits: Inject file-specific knowledge
3. After failures: Inject error-specific context

### 8.3: Adaptive Warning Escalation

**Problem**: Fixed warning thresholds don't account for context.

**Solution**: Escalate intervention based on session state:

```python
def get_intervention_level(session_state: SessionState) -> str:
    """
    Determine intervention level based on session health.

    Levels:
    - "observe": Just collect metrics, no warnings
    - "advise": Show suggestions, let Claude decide
    - "guide": Stronger suggestions, inject context
    - "intervene": Auto-apply fixes, block risky actions
    """
    # Start in advise mode
    level = "advise"

    # Escalate based on drift signals
    if session_state.drift_signals_ignored >= 3:
        level = "guide"

    # Escalate based on context exhaustion
    if session_state.context_usage > 0.85:
        level = "guide"

    # Escalate based on repeated failures
    if session_state.same_error_count >= 3:
        level = "intervene"

    # Escalate if session is very long
    if session_state.duration_minutes > 60:
        level = max(level, "guide")

    return level
```

**Hook Integration**: All hooks check intervention level and adjust behavior:
- `observe`: Collect metrics only
- `advise`: Current behavior (warnings + suggestions)
- `guide`: Add proactive context injection
- `intervene`: Auto-apply fixes, stronger blocking

### 8.4: Intervention Audit Log

**Requirement**: All automated interventions must be logged and reviewable.

```python
@dataclass
class InterventionEvent:
    timestamp: datetime
    intervention_type: str  # "auto_fix", "context_inject", "action_block"
    trigger: str  # What triggered the intervention
    action_taken: str  # What was done
    outcome: Optional[str] = None  # What happened (filled in later)
    user_feedback: Optional[str] = None  # Did user approve/reject?

def log_intervention(event: InterventionEvent) -> None:
    """Log intervention to audit trail."""
    audit_path = get_proof_dir() / "intervention_audit.jsonl"
    with open(audit_path, 'a') as f:
        f.write(json.dumps(event.to_dict()) + '\n')
```

## Configuration

Users control intervention level in project config:

```yaml
# active_context.yaml or .proof/config.yaml
v8_intervention:
  enabled: true
  level: "advise"  # observe, advise, guide, intervene

  auto_fix:
    enabled: false  # Opt-in
    confidence_threshold: 0.9
    min_uses: 3
    exclude_patterns:
      - "rm *"
      - "git push"

  proactive_context:
    enabled: true
    max_injection_size: 500  # chars

  escalation:
    auto_escalate: true  # Escalate based on session state
    max_level: "guide"  # Never go beyond this
```

## Safety Considerations

### Guardrails

1. **Opt-in by default**: All active interventions require explicit opt-in
2. **Audit trail**: Every intervention is logged
3. **Rollback**: Auto-fixes must be reversible
4. **Confidence threshold**: Only high-confidence actions are automated
5. **Escalation cap**: Users can cap maximum intervention level

### Risks

1. **Wrong auto-fix**: If auto-fix is wrong, could make things worse
   - Mitigation: High confidence threshold, usage minimum, audit log
2. **Context overflow**: Proactive injection could waste context
   - Mitigation: Size limits, relevance scoring
3. **User frustration**: Too much intervention feels controlling
   - Mitigation: Configurable levels, clear opt-out

## Implementation Order

1. **8.1 Auto-Apply** (highest value, most risk)
   - Start with dry-run mode (suggest but don't apply)
   - Graduate to auto-apply with user confirmation
   - Finally, silent auto-apply for very high confidence

2. **8.2 Proactive Context** (medium value, low risk)
   - Start with session start injection only
   - Add file-edit context
   - Add failure context

3. **8.3 Adaptive Escalation** (enables the above)
   - Implement intervention levels
   - Wire into all hooks

4. **8.4 Audit Log** (required for all above)
   - Implement first, required for safety

## Dependencies

- Phase 7 (Metrics Dashboard) - Need calibrated confidence scores
- Phase 5/6 (Metrics/Suggestions) - Foundation for tracking

## Success Criteria

1. Auto-fix correctly applied in ≥80% of cases
2. User can view intervention audit log
3. No regressions (interventions don't make sessions worse)
4. Positive user feedback on proactive context

## Timeline Estimate

- 8.1 Auto-Apply: 4-5 hours
- 8.2 Proactive Context: 3-4 hours
- 8.3 Adaptive Escalation: 3-4 hours
- 8.4 Audit Log: 2-3 hours
- Testing: 4-5 hours

Total: ~18-22 hours
