---
description: Log a mismatch between expectation and reality
allowed-tools: Read, Edit, Write
---

# Log Mismatch

Capture when reality diverged from expectations. This is the first step in the adaptation loop.

## Current State
@active_context.yaml

## Instructions

A mismatch has occurred. Before trying again or moving on, capture it:

1. **Identify the mismatch**
   - What step were you on?
   - What did you expect to happen?
   - What actually happened?

2. **Analyze the delta**
   - What's the difference between expected and actual?
   - What's your suspected cause? (0.0-1.0 confidence)

3. **Update active_context.yaml**

Add to the `mismatches` array:

```yaml
mismatches:
  - id: "mismatch-YYYYMMDDHHMMSS"  # Use current timestamp
    step: <step_number>
    timestamp: "<current_iso_timestamp>"
    expectation: "What you expected"
    observation: "What actually happened"
    delta: "The key difference"
    suspected_cause: "Your hypothesis for why"
    confidence: 0.7  # How sure are you (0.0-1.0)
    resolved: false
    resolution: null
    trigger: null  # REQUIRED when resolved (v3.4)
```

4. **Update the current step** (if applicable)

If this mismatch affects the current step, update its `actual` and `delta` fields:

```yaml
plan:
  - description: "The step"
    status: in_progress
    expected: "What should happen"
    actual: "What actually happened"  # ← Fill this in
    delta: "The difference"           # ← Fill this in
```

5. **Decide next action**

After logging, you have options:
- Run `/edge-adapt` to revise the plan
- Continue if the mismatch is minor
- Escalate if you need clarification

## Output

After updating active_context.yaml, summarize:
- The mismatch ID
- Expectation vs Observation (one line each)
- Your suspected cause and confidence
- Recommended next action

## Example

```yaml
mismatches:
  - id: "mismatch-20250115110000"
    step: 3
    timestamp: "2025-01-15T11:00:00"
    expectation: "API returns 200 with user list"
    observation: "API returns 403 Forbidden"
    delta: "Auth rejected instead of success"
    suspected_cause: "Token expired during long file processing"
    confidence: 0.8
    resolved: false
    resolution: null
```

**Do NOT** just retry. Capture first, then adapt.

## Resolving Mismatches (v3.4)

When you **resolve** a mismatch, you MUST add:
- `resolution`: What fixed it (one sentence)
- `trigger`: Keywords that would surface this lesson for future-me

**Why?** Resolved mismatches ARE lessons. The `trigger` makes them searchable.
At prune time, resolved mismatches with triggers auto-become lessons in memory.

```yaml
# BEFORE resolution
- id: "mismatch-20250103"
  expectation: "Sync script writes to same DB as app"
  observation: "psycopg2 writes to PostgreSQL, app uses SQLite"
  resolved: false
  resolution: null
  trigger: null

# AFTER resolution
- id: "mismatch-20250103"
  expectation: "Sync script writes to same DB as app"
  observation: "psycopg2 writes to PostgreSQL, app uses SQLite"
  resolved: true
  resolution: "Changed sync to use sqlite3 module"
  trigger: "sync script + data not appearing + database mismatch"
```

The archive hook will **block** archiving a resolved mismatch without a trigger.
