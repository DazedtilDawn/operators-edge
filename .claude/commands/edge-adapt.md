---
description: Revise the plan after a mismatch - adapt, don't retry
allowed-tools: Read, Edit, Write
---

# Adapt the Plan

After detecting a mismatch, revise the plan. This is NOT "try again" - it's "try differently."

## Current State
@active_context.yaml

## The Principle

> "When reality changes, do I change?"

If you're here, reality diverged from expectations. The old plan assumed something false. The new plan must account for what you now know.

## Instructions

1. **Review unresolved mismatches**
   Look at the `mismatches:` array for items with `resolved: false`.

2. **For each mismatch, decide:**

   **Option A: Revise the current step**
   - Change the approach, not just retry
   - Add guards or checks
   - Reduce step size

   **Option B: Add new steps**
   - Insert prerequisite steps
   - Add recovery steps

   **Option C: Remove/replace steps**
   - If the original approach is fundamentally flawed
   - Switch to a simpler method

   **Option D: Escalate**
   - If you need clarification or permission
   - If risk is too high to proceed

3. **Update the plan**

   ```yaml
   plan:
     - description: "Revised step with new approach"
       status: in_progress
       expected: "Updated expectation based on new knowledge"
       # Note what changed:
       # OLD: "Call API directly"
       # NEW: "Refresh token first, then call API"
   ```

4. **Add guardrails**

   If this mismatch could recur, add a constraint or risk:
   ```yaml
   constraints:
     - "Always refresh token before API calls > 5 min after last refresh"

   risks:
     - risk: "Token could expire during long operations"
       mitigation: "Check expiry before each API call"
       status: active
   ```

5. **Extract a lesson (if applicable)**

   If this mismatch taught something reusable:
   ```yaml
   memory:
     - trigger: "API returns 403"
       lesson: "Refresh token before retry"
       applies_to: ["API calls"]
       reinforced: 1
       last_used: "<today>"
       source: "<session_id>"
   ```

6. **Mark mismatch as resolved**

   ```yaml
   mismatches:
     - id: "mismatch-xxx"
       # ... other fields ...
       resolved: true
       resolution: "Added token refresh before API calls"
   ```

## Output

After adapting, summarize:
- Mismatches addressed: N
- Steps revised: list
- Steps added: list
- Steps removed: list
- Guardrails added: list
- Lessons captured: list

## Anti-Patterns (Avoid These)

| Bad | Good |
|-----|------|
| "Try the same command again" | "Try a different approach" |
| "Maybe it will work this time" | "Here's why it failed and what's different now" |
| "Just increase timeout" | "Understand why it timed out, address root cause" |
| "Skip this step" | "Replace with working alternative or escalate" |

## The Adaptation Test

Before proceeding, answer:
1. What did I learn from this mismatch?
2. How is my new approach fundamentally different?
3. What would cause the same failure again?
4. Have I added guards against that?

If you can't answer these, you're not adapting - you're retrying.
