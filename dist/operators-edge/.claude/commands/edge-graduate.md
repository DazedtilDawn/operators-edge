# /edge-graduate - Graduate Lessons to Rules

Review and approve lessons for graduation to enforceable rules.

## Usage

```
/edge-graduate              # List graduation candidates
/edge-graduate status       # Show shadow mode rules status
/edge-graduate approve <n>  # Approve candidate #n for graduation
/edge-graduate promote <id> # Promote shadow rule to enforce
/edge-graduate demote <id>  # Demote rule back to lesson
```

## What This Does

1. **List candidates**: Shows lessons with reinforced >= 10 that are ready for graduation
2. **Status**: Shows rules in shadow mode and their effectiveness
3. **Approve**: Graduates a lesson to a rule in shadow mode (warn only)
4. **Promote**: Promotes a shadow rule to enforcement after proving effective
5. **Demote**: Removes an ineffective rule, returning it to lesson status

## Graduation Flow

```
LESSON (memory)
  → reinforced >= 10 times
  → PATROL surfaces as candidate
  → /edge-graduate approve <n>
  → rules.yaml (shadow_mode: true, action: warn)
  → 2 weeks / 10 fires with 80%+ effectiveness
  → Auto-promote to enforce (or demote if <50%)
```

## Shadow Mode

New rules start in **shadow mode**:
- Always warn, never block
- Track fire count and effectiveness
- Auto-promote when: 10+ fires AND 2+ weeks AND 80%+ effective
- Auto-demote when: 10+ fires AND <50% effective

## Instructions

When user runs `/edge-graduate`:

1. **Load state**: Read active_context.yaml and rules.yaml
2. **Find candidates**: Use `get_graduation_candidates()` from rules_engine
3. **Display options**: Format with `format_graduation_candidates()`
4. **Handle commands**:
   - No args: List candidates
   - `status`: Show shadow rules with `format_shadow_rules_status()`
   - `approve N`: Call `graduate_lesson_to_rule()` for candidate N
   - `promote ID`: Call `promote_rule(ID)`
   - `demote ID`: Call `demote_rule(ID)`

## Example Output

### List Candidates

```
🎓 Graduation Candidates

These lessons have been reinforced enough to become rules:

1. [react hooks] - Use useCallback for event handlers in lists...
   Reinforced: 15 times

2. [error handling] - Always wrap async operations in try-catch...
   Reinforced: 12 times

Run `/edge-graduate approve 1` to graduate a lesson.
```

### Status

```
🌙 Shadow Mode Rules

- graduated-react-hooks: Use useCallback for event handlers...
  Fires: 8, Effectiveness: 87%, Status: 🔄 Collecting data

- graduated-error-handling: Always wrap async operations...
  Fires: 12, Effectiveness: 92%, Status: ✅ Ready for promotion
```

## Implementation Notes

- Rules are stored in `.claude/rules.json` (version-controlled)
- Effectiveness is computed from outcome tracking data
- Shadow mode duration: 14 days or 10 fires minimum
- Promotion threshold: 80% effectiveness
- Demotion threshold: <50% effectiveness
