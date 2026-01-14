# /edge and /edge-loop Canonical Contract (v4.0)

Status: v4.0 Phase 1 implemented; mode awareness added to /edge command.

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
- Optional field: mode (plan|active|review|done) - if not set, auto-detected from state
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

## Mode System (v4.0)

Modes represent workflow phases and influence /edge behavior.

### Mode Values
| Mode | Purpose | When Detected |
|------|---------|---------------|
| PLAN | Explore codebase, create plan | No objective set |
| ACTIVE | Execute plan steps | Has objective + incomplete steps |
| REVIEW | Verify completion | Has objective + all steps complete |
| DONE | Archive and clear | Explicit only (user sets) |

### Mode Detection
If `mode` field is set in active_context.yaml, use it directly.
Otherwise, auto-detect from state:
1. No objective → PLAN
2. Has objective, no plan → ACTIVE
3. Has objective, has pending/in_progress steps → ACTIVE
4. Has objective, all steps completed → REVIEW

### Mode Commands
- `/edge plan` - Set mode to PLAN
- `/edge active` - Set mode to ACTIVE
- `/edge review` - Set mode to REVIEW
- `/edge done` - Set mode to DONE

Mode persists to active_context.yaml and affects /edge output and guidance.

### Mode Behaviors (Phase 2)
| Mode | /edge Behavior |
|------|----------------|
| PLAN | Shows objective/plan status, suggests next steps, NO gear engine |
| ACTIVE | Runs gear engine (ACTIVE/PATROL/DREAM), shows transitions/junctions |
| REVIEW | Shows verification checklist, plan completion status, command hints |
| DONE | Shows archive options, prune/score commands, new objective guidance |

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
- /edge status: show gear + junction state + mode (no execution)
- /edge stop/off: disable dispatch/automation and reset gear_state
- /edge approve: resolve pending junction (one-time allowance) then continue run
- /edge skip: reject current candidate and continue run
- /edge dismiss [TTL]: clear junction and suppress matching junctions for TTL minutes (default: 60)
- /edge plan|active|review|done: set mode and show guidance (v4.0)
- /edge (no args or on): execute one engine cycle with mode-aware output

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

## Current Deviations (as of v4.0)

The following differences exist between code and this contract:
- /edge run ignores free-form args.

### v4.0 Phase 1 Completed
- Mode field added to active_context.yaml
- detect_mode() auto-detects mode from state
- /edge plan|active|review|done subcommands implemented
- /edge output shows mode + gear in header
- Deprecation warnings added to legacy commands

### v4.0 Phase 2 Completed
- Mode-specific handlers: handle_plan_mode(), handle_review_mode(), handle_done_mode(), handle_active_mode()
- PLAN mode: Exploration output, no gear engine - shows objective/plan status, next steps
- REVIEW mode: Verification checklist, plan completion status, command hints
- DONE mode: Archive options, prune/score commands, new objective guidance
- ACTIVE mode: Runs gear engine (unchanged behavior)

### v4.0 Phase 3 Completed
- suggest_mode_transition() detects when transition is appropriate
- PLAN mode suggests ACTIVE when plan has pending steps
- ACTIVE mode suggests REVIEW when all steps completed
- mode_transition junction type gates transitions (user must approve)
- handle_approve() performs set_mode() on mode_transition junction approval

### Mode Transition Graph
```
PLAN ──(plan ready)──> ACTIVE ──(all complete)──> REVIEW ──(user)──> DONE
  ^                                                                    │
  └────────────────────────(new objective)─────────────────────────────┘
```

All transitions require user approval via `/edge approve`.
