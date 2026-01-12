---
description: Run quality checks on active_context.yaml and proof without ending the session
allowed-tools: Read
---

# Edge Verify - Quality Checks

Run lightweight quality checks on the current state and proof. This is a read-only diagnostic that does not modify state.

## Current State
@active_context.yaml

## Quality Checks

Run the following checks and report results:

### 1. Plan Exists
- `active_context.yaml` has a non-empty `plan` array
- At least one step exists

### 2. No Dangling In-Progress
- No steps are stuck in `status: in_progress`
- All work should be either pending or completed

### 3. Completed Steps Have Proof
- Every step with `status: completed` has a non-empty `proof` field
- Proof should describe what was done, not just "done"

### 4. Current Step Valid
- `current_step` points to a valid step index
- Current step should not point to a completed step (if more work remains)

### 5. Verifications Addressed
- If steps have `verification` criteria, ensure tests were run
- Or document why verification was skipped

### 6. No Unresolved Mismatches
- All entries in `mismatches` array should have `status: resolved`
- Unresolved mismatches indicate incomplete learning

### 7. Proof Log Exists
- `.proof/session_log.jsonl` exists
- Session has captured some proof entries

### 8. Eval Gate (if enabled)
- If evals are active (level >= 1), check for invariant failures
- Eval failures may block completion if `gate_on_fail: true`

## Output Format

```
════════════════════════════════════════════════════════════════════════════════
EDGE VERIFY - QUALITY CHECKS
════════════════════════════════════════════════════════════════════════════════

Objective: [objective text or "None"]
Current Step: [N] / [total steps]

Checks:
  [✓] Plan exists (N steps)
  [✓] No dangling in_progress steps
  [✗] Completed steps have proof (2 missing)
      - Step 1: "Setup environment"
      - Step 3: "Add validation"
  [✓] Current step valid
  [⚠] Verifications not run for Step 2
  [✓] No unresolved mismatches
  [✓] Proof log exists (N entries)
  [✓] Eval gate passed

Actions Required:
  1. Add proof to Step 1 and Step 3
  2. Run verification for Step 2 or document skip reason

Status: PASS | FAIL | WARN
════════════════════════════════════════════════════════════════════════════════
```

## Check Legend

| Symbol | Meaning |
|--------|---------|
| `[✓]` | Check passed |
| `[✗]` | Check failed (blocking) |
| `[⚠]` | Warning (non-blocking) |
| `[○]` | Check skipped (N/A) |

## Instructions

1. **Read state**
   - Load `active_context.yaml`
   - Note objective, current_step, plan

2. **Run each check**
   - Mark pass/fail/warn for each
   - Collect details for failures

3. **Check proof log**
   - Verify `.proof/session_log.jsonl` exists
   - Count entries if accessible

4. **Report results**
   - Show all check results
   - List specific failures with details
   - Provide actionable fixes

5. **Determine status**
   - PASS: All checks passed
   - WARN: Only warnings, no errors
   - FAIL: At least one error

## Notes

- This command is **read-only** - it does not modify state
- Use `/edge-step` or edit `active_context.yaml` to fix issues
- Use `/edge` after fixing to continue work
- Quality gate runs automatically at objective completion

## See Also

- `/edge-score` - Self-assess adaptive behavior (6-check rubric)
- `/edge-prune` - Archive completed work to reduce entropy
- `/edge` - Main orchestrator
