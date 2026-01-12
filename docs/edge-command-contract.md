# /edge and /edge-loop Canonical Contract (vNext)

Status: proposed contract; current implementation may differ (see "Current Deviations").

## Scope

This contract defines the canonical behavior for:
- /edge command (CLI orchestration + gear engine + junction gating)
- /edge-loop (reporting + observability routine)

Out of scope: /edge-* subcommands (plan, step, prune, yolo, etc.) except where
explicitly referenced for junction gating.

## Core Model

/edge is a human-in-the-loop dispatcher:
- Gears (ACTIVE / PATROL / DREAM) are autonomous modes.
- Junctions are explicit human handshake points that pause autonomy.
- /edge-loop is reporting and hygiene (proof viz, drift summary, server health).

## Canonical State Files

### active_context.yaml (source of truth)
- Required fields: objective, plan, current_step, constraints, risks
- This file is the only source for "what should happen" (intent and plan).

### .claude/state/gear_state.json (gear runtime state)
Purpose: track current gear, iterations, and session-level counts.

Schema (v2):
```
{
  "schema_version": 2,
  "current_gear": "active|patrol|dream",
  "entered_at": "<ISO8601>",
  "last_run_at": "<ISO8601>",
  "iterations": <int>,
  "last_transition": "active_to_patrol|patrol_to_active|patrol_to_dream|dream_to_active|dream_to_patrol|null",
  "patrol_findings_count": <int>,
  "dream_proposals_count": <int>,
  "completion_epoch": "<hash or null>"
}
```

Invariants:
- gear_state is persisted on every /edge run (even if no transition).
- iterations increments on every run.
- completion_epoch updates only when objective transitions from incomplete to complete.

### .claude/state/junction_state.json (single source of junction truth)
Purpose: coordinate pending human decisions in a deterministic way.

Schema (v1):
```
{
  "schema_version": 1,
  "pending": {
    "id": "<uuid>",
    "type": "quality_gate|finding_selection|proposal|dangerous|complexity|blocked|external|ambiguous",
    "payload": {"...": "..."},
    "created_at": "<ISO8601>",
    "source": "edge"
  },
  "history_tail": [
    {
      "id": "<uuid>",
      "type": "...",
      "decision": "approve|skip|dismiss",
      "decided_at": "<ISO8601>"
    }
  ],
  "suppression": [
    {
      "fingerprint": "<hash>",
      "expires_at": "<ISO8601>"
    }
  ]
}
```

Invariants:
- At most one pending junction at any time.
- approve/skip/dismiss operate exclusively on this file.
- Junction writes are atomic and validated against schema_version.

## Gear Transition Graph (Complete)

All gears are reachable; detection implies reachability:
- ACTIVE -> PATROL
- ACTIVE -> DREAM
- PATROL -> ACTIVE
- PATROL -> DREAM
- DREAM -> PATROL
- DREAM -> ACTIVE

No detected gear may be unreachable from current_gear.

## Structured Result Contract

Each gear returns a structured result (no string parsing):
```
{
  "status": "ok|warning|error",
  "progress_made": true|false,
  "junction": {"type": "...", "payload": {...}} | null,
  "suggested_next_gear": "active|patrol|dream|none",
  "telemetry": {"...": "..."}
}
```

Engine uses only structured fields to decide transitions and auto-run behavior.
CLI output is presentation only.

## /edge Command Semantics

### Command Routing
- /edge status: show gear + junction state (no execution)
- /edge stop/off: disable dispatch/automation and reset gear_state
- /edge approve: resolve pending junction then continue run
- /edge skip: reject current candidate and continue run
- /edge dismiss: clear junction and suppress it temporarily
- /edge (no args or on): execute one engine cycle

### Junction Gate (first-class, early)
If a pending junction exists and the command is not approve/skip/dismiss:
- Output the junction details
- Do not run gears

### Quality Gate (completion epoch)
Run quality gate only when a completion epoch changes from incomplete -> complete.
Warnings do not block transitions. Errors block with a junction.

### Error Semantics
- Errors are never converted into "no findings" or "no proposal".
- On error, remain in the same gear unless the operator approves a transition.
- If persistence or schema integrity fails, halt and report.

## /edge-loop Semantics

Required steps (order):
1. Proof visualizer (--history)
2. CTI drift summary (if history available)
3. Archive report (proof_viz.html)
4. Generate digest (non-fatal)
5. Ensure server running (honor EDGE_PORT)

Error policy:
- Visualizer failure: warn and continue (loop still completes)
- Archive failure: warn but keep output
- Digest failure: warn only
- Server start: verify after spawn; if still down, warn

## Concurrency and Persistence

- State files must be guarded with a lock (file-based lock with timeout).
- All writes are atomic (write temp -> rename).
- Reports use unique filenames (date + time suffix on collision).

## Current Deviations (as of v3.9)

The following differences exist between code and this contract:
- /edge run ignores free-form args.

These deviations must be closed before this contract is fully enforced.
