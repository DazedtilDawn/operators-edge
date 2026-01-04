---
description: Smart orchestrator - figures out what you need based on context
allowed-tools: Read, Edit, Write, Bash, Glob, Grep, Skill
---

# Operator's Edge - Smart Orchestrator (v3.8)

One command to rule them all. Now with Three Gears.

## Current State
@active_context.yaml
@.claude/state/dispatch_state.json (if exists)

## v3.8 Three Gears System

The system automatically operates in one of three gears based on state:

| Gear | Emoji | When Active | Behavior |
|------|-------|-------------|----------|
| **ACTIVE** | `[ACTIVE]` | Has objective + pending/in_progress steps | Execute steps, hit junctions |
| **PATROL** | `[PATROL]` | Just completed objective OR scout found issues | Scan for issues, surface findings |
| **DREAM** | `[DREAM]` | Nothing actionable, truly idle | Reflect, consolidate, propose improvements |

### Gear Detection Logic

```python
def detect_gear(state):
    objective = state.get("objective", "")
    plan = state.get("plan", [])

    # Has work to do?
    has_pending = any(s.get("status") in ("pending", "in_progress") for s in plan if isinstance(s, dict))
    if objective and has_pending:
        return "ACTIVE"

    # Scout found actionable issues?
    if scout_has_findings():
        return "PATROL"

    # Nothing to do
    return "DREAM"
```

### Gear Transitions

```
        ┌─────────────────────────┐
        │       [ACTIVE]          │
        │   (executing steps)     │
        └───────────┬─────────────┘
                    │ objective complete
                    ▼
        ┌─────────────────────────┐
        │       [PATROL]          │◄───┐
        │   (scanning issues)     │    │
        └───────────┬─────────────┘    │
         findings?  │  no findings     │
            │       ▼                  │
            │    [DREAM] ──────────────┘
            │       │     periodic re-scan or
            │       │     user input
            ▼       ▼
         ACTIVE  (proposes improvements)
```

## Instructions

When `/edge` is called:

### Step 1: Detect Current Gear

Read `active_context.yaml` and determine the gear:

```
[GEAR] Detecting state...
[GEAR] Objective: "..." (or empty)
[GEAR] Plan: N steps (M pending, K completed)
[GEAR] Current gear: ACTIVE | PATROL | DREAM
```

### Step 2: Execute Gear-Specific Logic

#### If ACTIVE Gear:
1. Check for high entropy (>3 completed steps) → Run `/edge-prune`
2. Find current step (first pending or in_progress)
3. Check for junctions (dangerous/complex operations)
4. Execute step or pause at junction
5. On completion → transition to PATROL

```
[ACTIVE] Executing step 2/5: "Add validation logic"
[ACTIVE] Step complete - 3/5 done
```

#### If PATROL Gear:
1. Run scout scan for issues (TODOs, missing tests, violations)
2. Surface top findings
3. If findings exist:
   - SIMPLE findings → auto-select, auto-plan, transition to ACTIVE
   - MEDIUM/COMPLEX → JUNCTION for user approval
4. If no findings → transition to DREAM

```
[PATROL] Scanning codebase...
[PATROL] Found 3 actionable items
[PATROL] Top finding: "Missing tests for utils.py" (Simple)
[PATROL] Auto-selecting and planning...
```

#### If DREAM Gear:
1. Analyze lessons for consolidation opportunities
2. Identify patterns in completed work
3. Generate improvement proposals (rate-limited: max 3 per session)
4. If proposal generated → JUNCTION for user approval
5. If no proposals → stay in DREAM, display insights

```
[DREAM] Reflecting on session...
[DREAM] Consolidation opportunities: 2 similar lessons
[DREAM] Pattern detected: Dominant theme is "testing" (5x)
[DREAM] Proposal: "Add audit patterns to more lessons"
```

### Step 3: Handle Arguments

| Argument | Action |
|----------|--------|
| (none) / `on` | Run gear cycle |
| `status` | Show current gear and state, don't execute |
| `off` / `stop` | Disable dispatch, show stats |
| `approve` | Clear junction, continue |
| `skip` | Skip current action, try next |
| `dismiss N` | Dismiss finding N from scout |

## Output Format

### Gear Status Header

Always show current gear at the top:

```
═══════════════════════════════════════════════════════════════════════════════
OPERATOR'S EDGE v3.8 - [ACTIVE] Gear
═══════════════════════════════════════════════════════════════════════════════
```

### ACTIVE Gear Output

```
═══════════════════════════════════════════════════════════════════════════════
OPERATOR'S EDGE v3.8 - [ACTIVE] Gear
═══════════════════════════════════════════════════════════════════════════════

Objective: "Add dark mode toggle"
Progress: 3/5 steps completed

[ACTIVE] Executing step 4: "Add CSS variables"
... (execution output) ...
[ACTIVE] Step 4 complete

[ACTIVE] Executing step 5: "Run tests"
... (execution output) ...
[ACTIVE] Step 5 complete

════════════════════════════════════════════════════════════════════════════════
OBJECTIVE COMPLETE - Transitioning to [PATROL]
════════════════════════════════════════════════════════════════════════════════
```

### PATROL Gear Output

```
═══════════════════════════════════════════════════════════════════════════════
OPERATOR'S EDGE v3.8 - [PATROL] Gear
═══════════════════════════════════════════════════════════════════════════════

[PATROL] Scanning codebase for issues...
[PATROL] Scanned 45 files in 0.8s

Findings:
  [1] ~ Missing tests for validator.py (Simple)
  [2] ! FIXME: Refactor auth module (Complex)
  [3] . TODO: Add logging (Simple)

[PATROL] Auto-selecting [1] (Simple complexity)
[PATROL] Transitioning to [ACTIVE]
```

### DREAM Gear Output

```
═══════════════════════════════════════════════════════════════════════════════
OPERATOR'S EDGE v3.8 - [DREAM] Gear
═══════════════════════════════════════════════════════════════════════════════

[DREAM] Entering reflection mode...

Consolidation Opportunities:
  • 'hooks' has 2 similar lessons - could merge
  • 'memory' has 2 similar lessons - could merge

Patterns Identified:
  • Dominant themes: testing (5x), hooks (3x)
  • Memory growth: 26 lessons (consider pruning)

Session Insights:
  • High-value lessons: hooks, paths, refactoring
  • 0/26 lessons have audit patterns

────────────────────────────────────────────────────────────────────────────────
DREAM PROPOSAL
────────────────────────────────────────────────────────────────────────────────

Title: Add audit patterns to more lessons
Type: enhancement | Priority: medium
Description: Only 0/26 lessons have audit patterns - adding them enables
             automatic violation detection

Options:
  /edge approve  - Accept proposal as new objective
  /edge skip     - Dismiss and stay in DREAM
  /edge stop     - Stop autonomous mode
```

### Junction Output

```
────────────────────────────────────────────────────────────────────────────────
JUNCTION: [type]
────────────────────────────────────────────────────────────────────────────────

Gear: [ACTIVE | PATROL | DREAM]
Reason: [why we paused]
Proposed: [what we want to do]

Options:
  /edge approve  - Continue with proposed action
  /edge skip     - Skip this, try next
  /edge stop     - Stop autonomous mode
```

## Decision Tree (v3.8)

```
/edge
  │
  ├─ `status`? ────────────────────────→ Show gear + state, don't run
  │
  ├─ `off` / `stop`? ──────────────────→ Disable dispatch, show stats
  │
  ├─ `approve`? ───────────────────────→ Clear junction, continue
  │
  ├─ `skip`? ──────────────────────────→ Skip current, continue
  │
  └─ (no args or `on`) ────────────────→ DETECT GEAR:
        │
        ├─ ACTIVE gear? ───────────────→ Execute steps until:
        │     │                           - Junction (dangerous/complex)
        │     │                           - All complete → PATROL
        │     └─ Entropy high? ────────→ /edge-prune first
        │
        ├─ PATROL gear? ───────────────→ Scout scan, then:
        │     │                           - Findings (simple) → ACTIVE
        │     │                           - Findings (complex) → JUNCTION
        │     └─ No findings? ─────────→ DREAM
        │
        └─ DREAM gear? ────────────────→ Reflect, then:
              │                           - Proposal ready → JUNCTION
              └─ No proposal? ─────────→ Show insights, stay DREAM
```

## Examples

### Example 1: Starting Fresh (DREAM → PATROL → ACTIVE)
```
User: /edge

═══════════════════════════════════════════════════════════════════════════════
OPERATOR'S EDGE v3.8 - [DREAM] Gear
═══════════════════════════════════════════════════════════════════════════════

[DREAM] No objective, entering reflection mode...
[DREAM] Analyzing 26 lessons for patterns...
[DREAM] No proposals generated (clean state)
[DREAM] Transitioning to PATROL for scout scan...

═══════════════════════════════════════════════════════════════════════════════
OPERATOR'S EDGE v3.8 - [PATROL] Gear
═══════════════════════════════════════════════════════════════════════════════

[PATROL] Scanning codebase...
[PATROL] Found 1 actionable item:
  [1] ~ Missing tests for new_module.py (Simple)

[PATROL] Auto-selecting [1], transitioning to ACTIVE...

═══════════════════════════════════════════════════════════════════════════════
OPERATOR'S EDGE v3.8 - [ACTIVE] Gear
═══════════════════════════════════════════════════════════════════════════════

Objective: "Add tests for new_module.py"
Plan: 2 steps

[ACTIVE] Executing step 1: "Create test file"
... (creates test_new_module.py) ...
[ACTIVE] Step 1 complete

[ACTIVE] Executing step 2: "Run tests"
... (pytest passes) ...
[ACTIVE] Step 2 complete

════════════════════════════════════════════════════════════════════════════════
OBJECTIVE COMPLETE: Add tests for new_module.py
════════════════════════════════════════════════════════════════════════════════
```

### Example 2: DREAM Proposal Junction
```
User: /edge

═══════════════════════════════════════════════════════════════════════════════
OPERATOR'S EDGE v3.8 - [DREAM] Gear
═══════════════════════════════════════════════════════════════════════════════

[DREAM] Reflection complete

Insights:
  • 5 lessons could be consolidated
  • 0/26 lessons have audit patterns
  • Pattern: "testing" appears in 40% of recent work

────────────────────────────────────────────────────────────────────────────────
JUNCTION: proposal
────────────────────────────────────────────────────────────────────────────────

Proposal: "Consolidate related lessons"
Description: 5 lessons share the same trigger keywords and could be merged

Options:
  /edge approve  - Accept as new objective
  /edge skip     - Dismiss proposal
  /edge stop     - Stop autonomous mode
```

## The Philosophy (v3.8)

> "Three gears: doing, checking, thinking. Like a productive human."

- **ACTIVE**: When there's work, do the work
- **PATROL**: After work, check for issues
- **DREAM**: When truly idle, reflect and propose

The gears transition automatically. You only intervene at junctions.
