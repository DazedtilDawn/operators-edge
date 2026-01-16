---
description: Smart orchestrator - one command to rule them all (v6.0)
allowed-tools: Read, Edit, Write, Bash, Glob, Grep, Skill
---

# Operator's Edge - Unified Command (v6.0)

**One command. The system figures out the rest.**

## The Contract

```
/edge                    → Do the right thing based on context
/edge "objective text"   → Start new objective (triggers planning)
/edge approve            → Approve pending junction
/edge approve 1,2        → Approve specific quality checks
/edge skip               → Skip pending junction
/edge dismiss            → Dismiss pending junction
/edge status             → Show status without acting
/edge stop               → Stop autonomous mode
/edge --plan             → Force planning mode
/edge --verify           → Force verification mode
/edge --auto             → Force autonomous mode
```

That's it. Five core variations instead of fifteen commands.

## Current State

@active_context.yaml
@.claude/state/gear_state.json (if exists)

## How It Works

The unified `/edge` uses **Intent Detection** to determine what should happen:

```
User → /edge [args]
     → Intent Detection (what should we do?)
     → Pattern Surfacing (what worked before?)
     → Action Execution (do it)
     → Result (continue or wait)
```

### Intent Detection Flow

```
1. Parse arguments (overrides, commands, objectives)
2. Check for pending junction (must address first)
3. Detect current gear (ACTIVE / PATROL / DREAM)
4. Determine gear-specific intent
5. Surface relevant patterns
6. Execute or pause
```

### The Three Gears

| Gear | When Active | What Happens |
|------|-------------|--------------|
| **ACTIVE** | Has objective + pending steps | Execute steps, hit junctions |
| **PATROL** | Objective complete | Scan for issues, surface findings |
| **DREAM** | No objective or work | Reflect, consolidate, propose |

## Instructions

When `/edge` is called:

### Step 1: Run the Unified Entry Point

The gear_engine.py contains `run_unified_edge()` which handles everything:

```python
from gear_engine import run_unified_edge
from edge_utils import load_yaml_state

state = load_yaml_state()
result = run_unified_edge(state, args="$ARGUMENTS")

# Display the result
print(result.display_message)

# If guidance was surfaced, it's already in display_message
# If action requires user input, requires_user_input=True
# If loop should continue, continue_loop=True
```

### Step 2: Display Output

The result contains everything:
- `display_message`: Human-readable output (show this)
- `intent_action`: What was decided
- `gear`: Which gear we're in
- `guidance`: Pattern guidance (Phase 2)
- `continue_loop`: Should we continue?
- `requires_user_input`: Waiting for user?

### Step 3: Act Based on Intent

| Intent | Action |
|--------|--------|
| `needs_objective` | Prompt user for objective |
| `needs_plan` | Run planning (create steps) |
| `needs_risks` | Prompt for risk identification |
| `ready_to_execute` | Execute the current step |
| `at_junction` | Display junction, wait for decision |
| `ready_to_complete` | Run quality gate |
| `run_scan` | Execute patrol scan |
| `has_findings` | Display findings, wait for selection |
| `reflect` | Run dream reflection |
| `has_proposal` | Display proposal, wait for decision |

### Step 4: Handle Execution

When `intent_action` is `ready_to_execute`:

1. The step description is in `result.result["step"]["description"]`
2. Pattern guidance (if any) is in `result.guidance`
3. Execute the step
4. Mark it complete in active_context.yaml
5. Run `/edge` again to continue

## Output Format

### Unified Header

```
═══════════════════════════════════════════════════════════════
OPERATOR'S EDGE v6.0 - [GEAR] Mode
═══════════════════════════════════════════════════════════════
```

### With Pattern Guidance (Phase 2)

```
═══════════════════════════════════════════════════════════════
OPERATOR'S EDGE v6.0 - [ACTIVE] Gear
═══════════════════════════════════════════════════════════════

## Executing Step 3: Add validation logic

### 📖 Relevant Lessons
- +++ **hooks**: Policy is not enforcement - hooks are enforcement
- + **refactoring**: Facade pattern enables refactoring without...

────────────────────────────────────────────────────────────────
Progress: 2/5
────────────────────────────────────────────────────────────────

Proceeding with execution...
```

### Junction Display

```
────────────────────────────────────────────────────────────────
JUNCTION: dangerous
────────────────────────────────────────────────────────────────

Gear: [ACTIVE]
Reason: Step involves 'deploy' operation

Options:
  `/edge approve`  - Continue with proposed action
  `/edge skip`     - Skip this, try next
  `/edge dismiss`  - Dismiss this junction
  `/edge stop`     - Stop autonomous mode
────────────────────────────────────────────────────────────────
```

## Examples

### Example 1: Fresh Start

```
User: /edge

═══════════════════════════════════════════════════════════════
OPERATOR'S EDGE v6.0 - [DREAM] Gear
═══════════════════════════════════════════════════════════════

No objective set.

Usage:
  `/edge "Your objective here"`
  `/edge --plan` to enter planning mode
```

### Example 2: New Objective

```
User: /edge "Add dark mode toggle"

## New Objective: Add dark mode toggle

### 📖 Relevant Lessons
- + **refactoring**: Facade pattern enables refactoring...

Creating plan...
```

### Example 3: Ready to Execute

```
User: /edge

═══════════════════════════════════════════════════════════════
OPERATOR'S EDGE v6.0 - [ACTIVE] Gear
═══════════════════════════════════════════════════════════════

## Executing Step 2: Add CSS variables

### 📖 Relevant Lessons
- **paths**: pathlib.Path handles cross-platform paths correctly

────────────────────────────────────────────────────────────────
Progress: 1/5
────────────────────────────────────────────────────────────────

Proceeding with execution...
```

### Example 4: Junction

```
User: /edge

────────────────────────────────────────────────────────────────
JUNCTION: dangerous
────────────────────────────────────────────────────────────────

Gear: [ACTIVE]
Reason: Step involves 'deploy' operation

Options:
  `/edge approve`  - Continue with proposed action
  `/edge skip`     - Skip this, try next
  `/edge dismiss`  - Dismiss this junction
  `/edge stop`     - Stop autonomous mode
────────────────────────────────────────────────────────────────

User: /edge approve

Junction approved. Continuing...
```

### Example 5: Quality Gate

```
User: /edge

═══════════════════════════════════════════════════════════════
OBJECTIVE COMPLETE
═══════════════════════════════════════════════════════════════

Quality Gate Results:
  ✓ All steps completed
  ✓ Verification step present
  ✓ Intent confirmed
  ✗ Tests passing (skipped)

Options:
  `/edge approve`    - Override all checks
  `/edge approve 4`  - Override check 4 only
  Fix the issues and run `/edge` again
```

## Migration Notes

The following commands still work but are deprecated:

| Old Command | New Equivalent |
|-------------|----------------|
| `/edge-plan` | `/edge --plan` or `/edge "objective"` |
| `/edge-step` | `/edge` (auto-detects) |
| `/edge-verify` | `/edge --verify` |
| `/edge-yolo on` | `/edge --auto` |
| `/edge-yolo approve` | `/edge approve` |
| `/edge-score` | `/edge status` |

## The Philosophy (v6.0)

> "Complexity hidden, intelligence visible."

The user types `/edge`. The system:
1. Knows where we are (intent detection)
2. Knows what worked before (pattern surfacing)
3. Knows what could go wrong (risk awareness)
4. Does the right thing (smart execution)
5. Learns from the outcome (feedback loop)

This is the difference between a tool and a partner.
