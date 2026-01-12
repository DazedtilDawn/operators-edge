---
description: Dispatch Mode - autopilot that runs /edge commands until objective is complete
allowed-tools: Read, Edit, Write, Glob, Grep, Bash, Task, Skill
---

# Dispatch Mode (Autopilot)

Run /edge commands automatically until the objective is complete, stopping only at junctions.

## Current State

@active_context.yaml

Read dispatch state from `.claude/state/dispatch_state.json` if it exists.
Junction source of truth is `.claude/state/junction_state.json` (dispatch mirrors a subset).

## Commands

### No Arguments: Show Status & Continue

If dispatch is **enabled and running**: Continue the dispatch loop (see Dispatch Loop below)

If dispatch is **at a junction**: Show junction details and wait for approval

If dispatch is **disabled**: Show status

```
================================================================
DISPATCH MODE STATUS
================================================================

Mode: [ENABLED | DISABLED]
State: [IDLE | RUNNING | JUNCTION | COMPLETE | STUCK]

Objective: [current objective or "None set"]
Progress: [N/M] steps completed

Stats this session:
  - Iterations: [N]
  - Auto-executed: [N]
  - Junctions hit: [N]

[If at junction:]
────────────────────────────────────────────────────────────────
JUNCTION: [type]
────────────────────────────────────────────────────────────────
Reason: [why we stopped]
Proposed action: [what we want to do]

Options:
  /edge-yolo approve  - Approve and continue
  /edge-yolo skip     - Skip this action, continue
  /edge-yolo stop     - Stop dispatch mode
================================================================
```

### `on` - Enable Dispatch Mode

Start the autopilot loop:

```
================================================================
DISPATCH MODE: ENABLED
================================================================

Autopilot engaged. Running /edge commands until objective complete.
Will stop at junctions (irreversible, external, ambiguous actions).

Starting dispatch loop...
================================================================
```

Then immediately begin the **Dispatch Loop**.

### `off` or `stop` - Disable Dispatch Mode

```
================================================================
DISPATCH MODE: DISABLED
================================================================

Autopilot disengaged.
Completed [N] iterations, hit [N] junctions.

Objective status: [complete | in_progress | not started]
================================================================
```

### `approve` - Approve Junction and Continue

Clear the current junction and resume the dispatch loop:

```
================================================================
JUNCTION APPROVED
================================================================

Continuing dispatch loop...
================================================================
```

Then resume the **Dispatch Loop**.

### `skip` - Skip Current Action

Skip the junction action and try to continue:

```
================================================================
ACTION SKIPPED
================================================================

Attempting to find alternative path...
================================================================
```

### `approve N` - Approve Scout Finding (Scout Mode Only)

When at a scout junction, approve finding N to make it the new objective:

```
================================================================
FINDING APPROVED
================================================================

Converting to objective: "[finding title]"
Running /edge-plan...
================================================================
```

### `dismiss N` - Dismiss Scout Finding (Scout Mode Only)

Dismiss finding N so it won't appear in future scans:

```
================================================================
FINDING DISMISSED
================================================================

"[finding title]" will not appear in future scans.
Showing remaining findings...
================================================================
```

### `rescan` - Run Fresh Scout Scan

Force a new scout scan even if findings exist:

```
================================================================
RESCANNING
================================================================

Running fresh codebase scan...
================================================================
```

---

## Dispatch Loop (v3.0 Continuous)

This is the core autopilot logic. In v3.0, the loop is continuous - it prunes, scouts, plans, and executes in an endless cycle until stopped.

### The Continuous Loop

```
┌─────────────────────────────────────────────────────────────┐
│                  CONTINUOUS DISPATCH LOOP                    │
├─────────────────────────────────────────────────────────────┤
│                                                              │
│    ┌─────────┐                                              │
│    │  START  │                                              │
│    └────┬────┘                                              │
│         │                                                    │
│         ▼                                                    │
│    ┌─────────┐      high entropy                            │
│    │  PRUNE  │◄─────────────────────────┐                   │
│    └────┬────┘                          │                   │
│         │                               │                   │
│         ▼                               │                   │
│    ┌─────────┐      no objective        │                   │
│    │  SCOUT  │◄─────────────────────┐   │                   │
│    └────┬────┘                      │   │                   │
│         │ auto-select               │   │                   │
│         ▼                           │   │                   │
│    ┌─────────┐      simple task     │   │                   │
│    │  PLAN   │ ─────auto-plan─────┐ │   │                   │
│    └────┬────┘                    │ │   │                   │
│         │ complex/medium          │ │   │                   │
│         │ [JUNCTION]              │ │   │                   │
│         ▼                         ▼ │   │                   │
│    ┌─────────┐                      │   │                   │
│    │ EXECUTE │◄─────────────────────┘   │                   │
│    └────┬────┘                          │                   │
│         │                               │                   │
│         ├──── step done ────────────────┤                   │
│         │                               │                   │
│         ├──── all done ─────────────────┘                   │
│         │     (back to scout)                               │
│         │                                                    │
│         └──── dangerous op ────► [JUNCTION]                 │
│                                                              │
└─────────────────────────────────────────────────────────────┘
```

### Step 1: Check Safety Limits

```python
# Pseudo-logic
if iteration > 50:
    STOP: "Safety limit reached (50 iterations)"
if stuck_count > 3:
    STOP: "Stuck - same action failed 3 times"
```

### Step 2: Check Entropy (Prune First)

If state has high entropy (>3 completed steps, resolved mismatches):
1. Show: `[AUTO] Pruning completed work...`
2. Run `/edge-prune` automatically
3. Continue to next step

### Step 3: Determine Next Action

Based on `active_context.yaml`:

| State | Complexity | Next Action |
|-------|------------|-------------|
| No objective | - | **SCOUT MODE** - auto-select top finding |
| Finding selected | SIMPLE | **AUTO-PLAN** - generate 1-2 step plan, execute |
| Finding selected | MEDIUM/COMPLEX | Run `/edge-plan` (JUNCTION) |
| Has blocked step | - | Run `/edge-adapt` (JUNCTION - adaptation needs approval) |
| Has in_progress step | - | Run `/edge-step` (AUTO) |
| Has pending step | - | Run `/edge-step` (AUTO) |
| All steps complete | - | **LOOP**: Clear objective → back to SCOUT |

### Step 4: Check if Junction (v3.0 Reduced Junctions)

**Junctions (always pause):**
- Plan creation for MEDIUM/COMPLEX tasks
- Adapting after failure (`/edge-adapt`)
- Irreversible bash commands (git push, rm -rf, deploy)
- External API calls affecting production
- Dangerous file operations (delete, overwrite config)

**Auto-execute (no pause):**
- `/edge-step` for all steps
- `/edge-prune` cleanup
- `/edge-score` self-assessment
- Scout mode auto-select
- Auto-plan for SIMPLE tasks
- Read/write operations (reversible)
- Local git operations (add, commit - not push)

### Step 5: Execute or Pause

**If AUTO action:**
1. Show: `[AUTO] Running: <action>`
2. Execute the command
3. Check result for errors/blocks
4. If success: increment iteration, reset stuck counter, GOTO Step 2
5. If failure: increment stuck counter, GOTO Step 2

**If JUNCTION:**
1. Show junction details with options
2. Save junction state
3. STOP and wait for user approval

### Step 6: Handle Completion (Continuous Mode)

When all steps are complete, v3.0 loops back to scout:

```
================================================================
OBJECTIVE COMPLETE
================================================================

Objective: [objective]
Steps completed: [N]

[AUTO] Clearing objective, returning to Scout Mode...

────────────────────────────────────────────────────────────────
SCOUT MODE: Finding next task...
────────────────────────────────────────────────────────────────

[Shows next findings with auto-select]
================================================================
```

### Stopping the Loop

The loop continues indefinitely until:
- User runs `/edge-yolo stop` or `/edge stop`
- Safety limit reached (50 iterations)
- Stuck count exceeded (3 failures on same action)
- No more findings in scout mode

```
User: /edge-yolo stop

================================================================
DISPATCH MODE: DISABLED
================================================================

Autopilot disengaged.
Session stats:
  - Objectives completed: [N]
  - Total iterations: [N]
  - Junctions hit: [N]

State preserved in active_context.yaml
================================================================
```

---

## Example Session

```
User: /edge-yolo on

Claude:
================================================================
DISPATCH MODE: ENABLED
================================================================

Autopilot engaged. Running /edge commands until objective complete.

[DISPATCH] Checking state...
[DISPATCH] Objective: "Add dark mode toggle"
[DISPATCH] Plan: 5 steps, 2 completed, step 3 in_progress

[DISPATCH] Running: /edge-step
... (executes step 3) ...
[DISPATCH] Step 3 complete

[DISPATCH] Running: /edge-step
... (executes step 4) ...
[DISPATCH] Step 4 complete

[DISPATCH] Running: /edge-step
... (step 5 involves git push) ...

────────────────────────────────────────────────────────────────
JUNCTION: irreversible
────────────────────────────────────────────────────────────────
Reason: git push detected
Proposed: Push changes to origin/main

  /edge-yolo approve  - Push and continue
  /edge-yolo skip     - Skip push, mark complete anyway
  /edge-yolo stop     - Stop dispatch mode

User: /edge-yolo approve

Claude:
================================================================
JUNCTION APPROVED
================================================================

[DISPATCH] Executing: git push
[DISPATCH] Push successful

================================================================
DISPATCH COMPLETE
================================================================

Objective: "Add dark mode toggle"
Steps completed: 5/5
Total iterations: 8
Junctions hit: 1

Autopilot disengaged. Great work!
```

---

## Junction Types

| Type | Examples | Why It's a Junction |
|------|----------|---------------------|
| **irreversible** | git push, rm, database delete | Can't undo |
| **external** | API calls, deploys, publish | Affects outside world |
| **ambiguous** | Plan creation, multiple approaches | Needs human decision |
| **blocked** | Step failed, unexpected error | Needs adaptation |
| **scout** | Finding selection | User must choose which finding to pursue |

---

## Scout Mode

When dispatch has no objective, it automatically enters **Scout Mode** - an autonomous exploration that finds work to do.

### Scout Activation

Scout Mode activates when:
- `objective` is `null` or empty in `active_context.yaml`
- Dispatch is enabled (`/edge-yolo on`)

### Scout Scan

Run a time-boxed scan looking for:

1. **TODO/FIXME Comments** - Unfinished work marked in code
2. **Large Files** - Files over 500 lines that may need refactoring
3. **Missing Tests** - Source files without corresponding test files

The scan is limited to:
- 200 files maximum
- 2 minutes timeout
- Top 10 findings stored

### Scout Report (v3.0 Autonomous Mode)

Findings now include **complexity classification** to enable autonomous operation:

```
────────────────────────────────────────────────────────────────
SCOUT MODE: Found Work
────────────────────────────────────────────────────────────────

Scanned 87 files in 1.2s

Top Findings:

  [1] ~ No tests for validator.py
      Type: missing_test | Priority: medium
      Location: src/validator.py
      Complexity: 🟢 Simple (auto-plan)
      Action: Create test file: test_validator.py

  [2] ! FIXME: Handle edge case for empty arrays
      Type: todo | Priority: high
      Location: src/parser.py:142
      Complexity: 🟡 Medium (plan review)
      Action: Address the FIXME comment

  [3] . Large file: utils.py (623 lines)
      Type: large_file | Priority: low
      Location: src/utils.py
      Complexity: 🔴 Complex (full review)
      Action: Consider splitting into smaller modules

[AUTO] Selecting finding [1] - simple task, auto-planning...
────────────────────────────────────────────────────────────────
```

### Complexity Levels

| Level | When | Behavior |
|-------|------|----------|
| 🟢 Simple | Clear, bounded tasks (missing test, simple TODO) | Auto-select, auto-plan |
| 🟡 Medium | Needs some guidance | Auto-select, junction at plan |
| 🔴 Complex | Architectural, risky (refactor, security) | Junction always |

### Auto-Select (v3.0)

In v3.0, dispatch **auto-selects** the highest priority finding without junction:

1. Sort findings by priority (HIGH > MEDIUM > LOW)
2. Among same priority, prefer SIMPLE complexity
3. Auto-select the top finding
4. If SIMPLE: also auto-plan (1-2 steps)
5. If MEDIUM/COMPLEX: junction at plan creation

User can still:
- `/edge-yolo skip` - skip current finding, try next
- `/edge-yolo dismiss N` - dismiss a specific finding
- `/edge-yolo stop` - stop dispatch mode

### Legacy Junction Mode

To force junction at scout (old behavior), check if any finding is COMPLEX:

```
────────────────────────────────────────────────────────────────
JUNCTION: scout (complex finding detected)
────────────────────────────────────────────────────────────────
Reason: Finding [3] is complex - needs human decision
...
────────────────────────────────────────────────────────────────
```

### Scout Commands

- `approve N` - Convert finding N to objective, run `/edge-plan` with it
- `dismiss N` - Mark finding N as dismissed (won't appear in future scans)
- `skip` - Skip scout mode, wait for manual objective
- `rescan` - Run a fresh scan

### Finding to Objective Flow

When user approves a finding:

1. Extract the finding's `title` as the objective
2. Clear scout findings from state
3. Trigger `/edge-plan` with the objective (JUNCTION - needs approval)
4. Once plan approved, dispatch continues normally

Example:
```
User: /edge-yolo approve 1

Claude:
================================================================
FINDING APPROVED
================================================================

Converting to objective: "FIXME: Handle edge case for empty arrays"

Running /edge-plan...

────────────────────────────────────────────────────────────────
JUNCTION: ambiguous
────────────────────────────────────────────────────────────────
Reason: Plan creation requires approval
Proposed plan: [4 steps...]

  /edge-yolo approve  - Approve plan and continue
  /edge-yolo stop     - Stop and revise
────────────────────────────────────────────────────────────────
```

---

## Safety Features

1. **Iteration Limit**: Stops after 50 iterations (configurable)
2. **Stuck Detection**: Stops after 3 failed attempts at same action
3. **Junction Gates**: Always pauses for dangerous/ambiguous actions
4. **State Persistence**: Can resume after interruption
5. **Easy Stop**: `/edge-yolo off` immediately disengages

---

## The Philosophy

> "Like a train on tracks - runs automatically but stops at switches."

Dispatch Mode lets you set an objective and watch it get done. Routine work
(executing plan steps) proceeds automatically. Decision points (creating plans,
adapting to failures, dangerous commands) pause for your input.

It's autopilot for development - you're still the pilot, just not hand-flying
every moment.
