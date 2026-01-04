---
description: Self-assessment against the 6-check adaptation rubric
allowed-tools: Read, Edit, Write
---

# Self-Score: 6-Check Assessment

Evaluate your adaptive behavior during this session against the 6-check rubric.

## Current State
@active_context.yaml

## The 6 Checks

Score yourself honestly on each:

### 1. Mismatch Detection
**Question:** Did I spot divergences between expectations and reality quickly?

| Score | Meaning |
|-------|---------|
| ✅ Met | Caught mismatches immediately, logged them with deltas |
| ❌ Missed | Plowed forward despite signals, retried without noticing |

### 2. Plan Revision
**Question:** When things went wrong, did I change my approach (not just retry)?

| Score | Meaning |
|-------|---------|
| ✅ Met | Wrote new strategies, reduced step size, added guards |
| ❌ Missed | Repeated the same step 3+ times |

### 3. Tool Switching
**Question:** Did I abandon tools that weren't working and try alternatives?

| Score | Meaning |
|-------|---------|
| ✅ Met | Switched methods when one failed, preferred simpler approaches |
| ⚪ N/A | No tool failures occurred |
| ❌ Missed | Kept hammering same tool despite failures |

### 4. Memory Update
**Question:** Did I capture reusable lessons from what I learned?

| Score | Meaning |
|-------|---------|
| ✅ Met | Added trigger-linked lessons to memory |
| ❌ Missed | Solved problems but didn't record patterns |

### 5. Proof Generation
**Question:** Did I attach evidence, not just claims?

| Score | Meaning |
|-------|---------|
| ✅ Met | Every major step has proof (logs, diffs, test results) |
| ❌ Missed | "Trust me" summaries without evidence |

### 6. Stop Condition
**Question:** Did I escalate appropriately when blocked or uncertain?

| Score | Meaning |
|-------|---------|
| ✅ Met | Asked crisp questions, presented bounded options |
| ⚪ N/A | Never hit uncertainty requiring escalation |
| ❌ Missed | Guessed when should have asked, or asked trivial questions |

## Instructions

1. **Review the session**
   - What mismatches occurred?
   - How did you respond?
   - What lessons were captured?

2. **Score each check**
   Be honest. Mark:
   - `met: true` if you satisfied the check
   - `met: false` if you missed it
   - Include a brief note explaining why

3. **Update active_context.yaml**

   ```yaml
   self_score:
     timestamp: "<current_iso_timestamp>"
     checks:
       mismatch_detection:
         met: true
         note: "Caught API 403 immediately, logged delta"
       plan_revision:
         met: true
         note: "Added token refresh step instead of retrying"
       tool_switching:
         met: false
         note: "N/A - no tool failures"
       memory_update:
         met: true
         note: "Added lesson about token expiry"
       proof_generation:
         met: true
         note: "Attached error log and fix diff"
       stop_condition:
         met: true
         note: "Asked about auth approach before proceeding"
     total: 5
     level: "real_agent"
   ```

4. **Determine level**

   | Score | Level | Meaning |
   |-------|-------|---------|
   | 0-2 | `demo_automation` | Just following scripts |
   | 3-4 | `promising_fragile` | Some adaptation, gaps remain |
   | 5-6 | `real_agent` | True adaptive behavior |

## Output

After scoring, provide:
- Score: N/6
- Level: demo_automation | promising_fragile | real_agent
- Strongest check: which one you did best
- Weakest check: which one to improve
- Carry-forward: what to do better next session

## Improvement Suggestions

Based on your weakest check, here are concrete improvements:

### If mismatch_detection is weak:
- Add explicit "Expected vs Actual" statements before major operations
- Use diff/delta logging more aggressively
- Check assumptions at step boundaries, not just at failures

### If plan_revision is weak:
- After any failure, write a NEW step before retrying
- Break large steps into smaller ones when stuck
- Ask "what would I do differently?" before each retry

### If tool_switching is weak:
- Keep a mental list of alternative tools for each operation
- If a tool fails twice, switch tools immediately
- Prefer simpler tools when complex ones struggle

### If memory_update is weak:
- After each step, ask "what did I learn that applies beyond this step?"
- Add lessons with specific triggers, not vague wisdom
- Review lessons at session end - did any apply?

### If proof_generation is weak:
- Attach evidence inline, not after the fact
- For code changes: show the diff
- For tests: show the output
- For claims: show the source

### If stop_condition is weak:
- When uncertain, frame as bounded options (not open questions)
- Escalate BEFORE guessing, not after failing
- Ask crisp questions with 2-3 specific choices

## Review Past Patterns (v2.4)

Before scoring, check if there are recurring patterns from past sessions:

1. **Load archive**: Read `.proof/archive.jsonl`
2. **Count scored sessions**: Look for `type: "completed_objective"` entries with scores
3. **Find recurring weak checks**: If any check appears as "missed" 2+ times, flag it

If you find recurring failures, call them out explicitly:
```
⚠️ RECURRING WEAKNESS: memory_update
   Failed in 3 of last 5 sessions
   Improvement focus: Add trigger-linked lessons, not vague wisdom
```

This helps identify systemic issues, not just this session's performance.

## Reflection Questions

1. **What would I do differently next time?**
2. **Which check was hardest to satisfy?**
3. **What lessons should I carry forward?**
4. **Does my weak check match a recurring pattern?** (If yes, prioritize fixing it)

## Extract Lessons (v2.5)

After scoring, analyze the completed work for potential lessons:

1. **Check resolved mismatches** - Each one contains a learning (expectation vs reality)
2. **Check step proofs** - Look for "learned", "realized", "found", "fixed", "issue" indicators
3. **Check constraints** - Things we learned to avoid during this work

For each potential lesson, consider:
- Is this reusable beyond this specific task?
- What trigger would surface this lesson at the right time?
- Is it already captured in existing lessons?

Output suggested lessons:
```
★ High confidence (from mismatch):
  Trigger: [trigger words]
  Lesson: [what was learned]

◆ Medium confidence (from step/constraint):
  Trigger: [trigger words]
  Lesson: [what was learned]
```

Present suggestions to user for confirmation before adding.

## Example

```yaml
self_score:
  timestamp: "2025-01-15T14:30:00"
  checks:
    mismatch_detection:
      met: true
      note: "Spotted Windows path issue immediately"
    plan_revision:
      met: true
      note: "Switched from manual copy to ZIP distribution"
    tool_switching:
      met: true
      note: "Abandoned direct copy for ZIP when dotfiles failed"
    memory_update:
      met: true
      note: "Captured 'dotfiles need ZIP to transfer'"
    proof_generation:
      met: true
      note: "Verified ZIP contents, showed extraction"
    stop_condition:
      met: false
      note: "Could have asked about Windows setup earlier"
  total: 5
  level: "real_agent"
```
