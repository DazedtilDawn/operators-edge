# Operator's Edge Protocol Specification v4.0

## Core Principle

> **Enforcement happens before actions, not after.**
> **Continuity is derived from observation, not compliance.**

---

## 1. State Schema

Single source of truth: `active_context.yaml`

```yaml
schema_version: 4

# Operator mode (the only mode that matters)
mode: plan | active | review | done

# What we're working on
objective: "string"
plan:
  - description: "Step 1"
    status: pending | in_progress | completed | blocked
    proof: "optional evidence"

current_step: 1  # 1-indexed

# Session tracking
session:
  id: "uuid"
  started_at: "ISO8601"
  start_hash: "sha256 of this file at session start"

# Junction gate (at most one pending)
junction: null | {
  id: "uuid",
  type: "irreversible | external | ambiguous | quality_gate",
  reason: "human-readable explanation",
  created_at: "ISO8601",
  fingerprint: "sha256 for allowance matching"
}

# Allowances (approved junctions that open a one-time gate)
allowances:
  - fingerprint: "sha256"
    granted_at: "ISO8601"
    consumed: false  # becomes true after first use

# Dismissals (allow-until rules that auto-approve matching junctions)
dismissals:
  - fingerprint: "sha256"
    expires_at: "ISO8601"
    dismissed_at: "ISO8601"

# Observations (auto-captured progress when Claude doesn't update state)
observations:
  files_modified: []
  tools_used: {}  # Counter: {"Edit": 5, "Bash": 12}
  tests_run: false
  last_activity: "ISO8601"

# Progress tracking (for auto-capture)
progress:
  last_tool_at: "ISO8601"
  last_edit_hash: "sha256 of files touched"
  tools_used: 47  # count this session

# Memory (lessons, carried forward)
memory:
  - trigger: "context"
    lesson: "what was learned"
```

**Invariants:**
- No other state files. Junction, dispatch, gear, plan_mode flags are GONE.
- `mode` is the only behavioral switch.
- `junction` is singular (at most one pending decision).

---

## 2. Mode Semantics

### PLAN Mode
- **Purpose:** Exploration, research, thinking
- **Entry:** Default on session start, or `/edge plan`
- **Constraints:** None
- **Stop behavior:** Always approve (no state change required)
- **Enforcement:** Only block catastrophic commands

### ACTIVE Mode
- **Purpose:** Executing work toward objective
- **Entry:** `/edge active` or `/edge active "new objective"`
- **Constraints:**
  - Must have objective
  - Should have plan (warn if missing, don't block)
- **Stop behavior:** Approve + auto-capture progress
- **Enforcement:** Block risky actions without junction approval

### REVIEW Mode
- **Purpose:** Verification, testing, reflection
- **Entry:** `/edge review`
- **Constraints:** Should have completed work to review
- **Stop behavior:** Approve + auto-capture
- **Enforcement:** Light gates, encourage proof generation

### DONE Mode
- **Purpose:** Clean completion and archival
- **Entry:** `/edge done` (requires quality gate pass in ACTIVE/REVIEW)
- **Constraints:** Quality gate must pass
- **Stop behavior:** Always approve, trigger archive
- **Enforcement:** None (already validated)

---

## 3. Tool Gating Matrix

| Tool | PLAN | ACTIVE | REVIEW | DONE |
|------|------|--------|--------|------|
| Read, Glob, Grep | Allow | Allow | Allow | Allow |
| Edit, Write | Allow | Warn if no plan* | Allow | Allow |
| Bash (safe) | Allow | Allow | Allow | Allow |
| Bash (risky)** | Junction | Junction | Junction | Junction |
| git push/reset | Junction | Junction | Junction | Junction |
| rm -rf, truncate | Block | Block | Block | Block |

*"Warn if no plan" = Emit warning in response, but allow the action. Not a hard block.

**Risky bash: deploy, migrate, DROP, DELETE FROM, curl -X POST to prod, etc.

### PreToolUse Decision Logic

```python
def on_pre_tool_use(tool: str, input: dict, mode: Mode) -> Decision:
    # Layer 1: Always blocked (catastrophic)
    if is_catastrophic(tool, input):
        return Decision.BLOCK, "This command is blocked for safety."

    # Layer 2: Junction required (risky/irreversible)
    if requires_junction(tool, input):
        fingerprint = compute_fingerprint(tool, input)

        # Check for unconsumed allowance (from /edge approve)
        allowance = find_allowance(fingerprint)
        if allowance and not allowance.consumed:
            allowance.consumed = True  # One-time use
            save_state()
            return Decision.APPROVE

        # Check for active dismissal (from /edge dismiss)
        dismissal = find_dismissal(fingerprint)
        if dismissal and not expired(dismissal):
            return Decision.APPROVE  # Auto-approved until TTL

        # No allowance or dismissal: create junction and block
        junction = create_junction(tool, input, fingerprint)
        return Decision.BLOCK, f"Junction required: {junction.reason}"

    # Layer 3: Mode-specific warnings (not blocks)
    if mode == Mode.ACTIVE:
        if tool in ("Edit", "Write") and not has_plan():
            return Decision.APPROVE, "Warning: No plan exists. Consider /edge plan first."

    # Default: allow
    return Decision.APPROVE
```

---

## 4. Junction Contract

### What Creates a Junction

| Trigger | Junction Type | Auto-created |
|---------|--------------|--------------|
| `git push`, `git reset --hard` | irreversible | Yes |
| Deploy commands, prod API calls | external | Yes |
| Multiple valid approaches detected | ambiguous | No (manual) |
| Quality gate failure on `/edge done` | quality_gate | Yes |

### Junction Lifecycle

```
                         ┌─────────────────────────────────┐
                         │                                 │
Created → Pending → Decided                                │
                    │                                      │
                    ├─ approve → Allowance created         │
                    │            (one-time gate opens)     │
                    │                    │                 │
                    │                    └─ consumed ──────┘
                    │                       (gate closes)
                    │
                    ├─ skip → Junction cleared
                    │         (no allowance, no retry)
                    │
                    └─ dismiss → Dismissal created
                                 (auto-approve until TTL)
```

### Approve vs Dismiss

| Command | Creates | Scope | Duration | Use Case |
|---------|---------|-------|----------|----------|
| `/edge approve` | Allowance | This exact action | One use | "Yes, do this specific thing" |
| `/edge dismiss` | Dismissal | All matching actions | Until TTL | "Stop asking about this class of thing" |

**Approve** grants a one-time pass for the blocked action. The allowance is consumed when the action executes. If the action fails or Claude tries again, a new junction is created.

**Dismiss** creates a time-limited rule that auto-approves all matching junctions. Useful for "I trust git push for the next hour" scenarios.

### Allowance Rules

When a junction is approved:
1. Compute fingerprint: `sha256(type + reason + key_params)`
2. Add to `allowances` with `consumed: false`
3. On next PreToolUse check, find matching unconsumed allowance
4. If found: mark `consumed: true` and approve action
5. Consumed allowances are cleaned up at session end

**Allowances are checked before junction creation.**

### Dismissal Rules

When a junction is dismissed:
1. Compute fingerprint: `sha256(type + key_params)` (reason excluded for broader matching)
2. Add to `dismissals` with TTL (default: 60 minutes)
3. On PreToolUse, check if fingerprint has active dismissal
4. If found and not expired: approve without creating junction

**Dismissals are checked before junction creation.**

### Junction Commands

| Command | Effect |
|---------|--------|
| `/edge approve` | Clear junction, create one-time allowance |
| `/edge skip` | Clear junction, no allowance (try different approach) |
| `/edge dismiss` | Clear junction, create dismissal with 60min TTL |
| `/edge dismiss 120` | Clear junction, create dismissal with custom TTL (minutes) |

---

## 5. Auto-Capture Contract (Observations)

### What Gets Captured

On every PostToolUse:
```yaml
# Appended to .proof/session_log.jsonl
{
  "timestamp": "ISO8601",
  "tool": "Edit",
  "input_preview": "first 500 chars",
  "output_preview": "first 1000 chars",
  "success": true,
  "file_touched": "/path/to/file.py",  # if applicable
  "diff_hash": "sha256"  # if file edit
}
```

### Observations Derivation

On stop (or next session start if unclean exit), derive observations from proof log:

```python
def derive_observations() -> dict:
    """Derive what actually happened from the proof log."""
    log = read_session_log()

    observations = {
        "files_modified": [],
        "tools_used": {},  # Counter
        "tests_run": False,
        "last_activity": None,
    }

    for entry in log:
        tool = entry["tool"]
        observations["tools_used"][tool] = observations["tools_used"].get(tool, 0) + 1

        if entry.get("file_touched"):
            if entry["file_touched"] not in observations["files_modified"]:
                observations["files_modified"].append(entry["file_touched"])

        if "test" in entry.get("input_preview", "").lower():
            observations["tests_run"] = True

        observations["last_activity"] = entry["timestamp"]

    return observations
```

### Observations vs Plan

**Key distinction**: Observations record what *did* happen. Plan records what *should* happen. These may diverge.

| Field | Source | What It Means |
|-------|--------|---------------|
| `plan[].status` | Claude (explicit) | Claude's claim about step completion |
| `observations.files_modified` | System (automatic) | Files that were actually modified |
| `observations.tools_used` | System (automatic) | Tool usage counts |
| `observations.tests_run` | System (automatic) | Whether test commands ran |

The quality gate uses *observations* to validate *claims*. If Claude marks a step "completed" but observations show no activity, the quality gate can flag the discrepancy.

### Auto-Update on Stop

```python
def on_stop(mode: Mode) -> Decision:
    if mode == Mode.PLAN:
        return Decision.APPROVE  # No requirements

    if mode == Mode.DONE:
        archive_session()
        return Decision.APPROVE

    # ACTIVE or REVIEW: always capture observations
    observations = derive_observations()
    state = load_state()
    state["observations"] = observations
    save_state(state)

    return Decision.APPROVE  # Never block
```

**The system always captures observations. Claude's explicit updates to plan status are separate and optional.**

---

## 6. Transition Rules

### Valid Transitions

```
PLAN → ACTIVE (requires objective)
PLAN → REVIEW (allowed, warn if nothing to review)
PLAN → DONE (blocked: nothing to complete)

ACTIVE → PLAN (allowed, preserves state)
ACTIVE → REVIEW (allowed)
ACTIVE → DONE (requires quality gate)

REVIEW → PLAN (allowed)
REVIEW → ACTIVE (allowed)
REVIEW → DONE (requires quality gate)

DONE → (session ends, archive triggered)
```

### Quality Gate for DONE

```python
def quality_gate() -> tuple[bool, list[str]]:
    issues = []
    state = load_state()
    observations = state.get("observations", {})

    # Check 1: Objective exists
    if not state.get("objective"):
        issues.append("No objective defined")

    # Check 2: Plan has completed steps
    plan = state.get("plan", [])
    completed = [s for s in plan if s.get("status") == "completed"]
    if not completed:
        issues.append("No steps marked completed")

    # Check 3: No in_progress steps
    in_progress = [s for s in plan if s.get("status") == "in_progress"]
    if in_progress:
        issues.append(f"{len(in_progress)} steps still in progress")

    # Check 4: Observations show activity (validates claims)
    tools_used = observations.get("tools_used", {})
    total_tools = sum(tools_used.values())
    if total_tools < 3:
        issues.append("Very little activity observed")

    # Check 5: Claims vs observations sanity check
    if completed and not observations.get("files_modified"):
        issues.append("Steps marked completed but no files modified")

    passed = len(issues) == 0
    return passed, issues
```

If quality gate fails: create `quality_gate` junction with issues list.

**Note**: The quality gate validates *observations* against *claims*. It catches both "nothing happened" and "claims don't match reality."

---

## 7. Stop Behavior (The Critical Change)

### Old Behavior (Broken)
```
Stop → Check state modified → BLOCK if not → Loop forever
```

### New Behavior (Correct)
```
Stop → Auto-capture progress → APPROVE always
```

### What "Progress Required" Actually Means

It doesn't mean "block until progress."
It means:
1. System captures what happened (from proof log)
2. System updates state automatically if Claude didn't
3. Next session starts with accurate context

**The burden shifts from Claude to the system.**

---

## 8. Session Lifecycle

### Start
1. Load `active_context.yaml`
2. Capture `start_hash`
3. Detect mode (default: PLAN)
4. Inject context into Claude's prompt
5. Clear any stale suppressions

### During
1. PreToolUse gates dangerous actions
2. PostToolUse logs everything
3. Mode transitions via `/edge` commands
4. Junction gates for human decisions

### Stop
1. Determine current mode
2. If ACTIVE/REVIEW: auto-capture if needed
3. If DONE: archive session
4. Always approve exit
5. Save final state

### Next Start (Continuity)
1. Load state from previous session
2. Detect if previous exit was clean
3. If unclean: surface auto-captured state
4. Resume from where we were

---

## 9. Transactional State Updates

All state mutations follow a strict transactional pattern to prevent corruption and race conditions.

### Lock Protocol

```python
LOCK_TIMEOUT = 5.0  # seconds
LOCK_FILE = ".claude/state/state.lock"

def with_state_lock(fn: Callable) -> Any:
    """Execute function while holding exclusive state lock."""
    lock_path = get_state_dir() / "state.lock"
    lock_path.parent.mkdir(parents=True, exist_ok=True)

    start = time.time()
    while True:
        try:
            # Atomic create-if-not-exists
            fd = os.open(str(lock_path), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            os.write(fd, f"{os.getpid()}\n".encode())
            os.close(fd)
            break
        except FileExistsError:
            if time.time() - start > LOCK_TIMEOUT:
                raise TimeoutError(f"State lock held for >{LOCK_TIMEOUT}s")
            time.sleep(0.1)

    try:
        return fn()
    finally:
        lock_path.unlink(missing_ok=True)
```

### State Update Pattern

```python
def update_state(patch: dict) -> None:
    """Atomically patch state file."""
    def _do_update():
        # 1. Read current state
        state = load_yaml_state()

        # 2. Validate patch doesn't violate invariants
        validate_patch(state, patch)

        # 3. Apply patch
        for key, value in patch.items():
            if value is None:
                state.pop(key, None)
            else:
                state[key] = value

        # 4. Write atomically (write to temp, then rename)
        write_yaml_atomic(state)

    with_state_lock(_do_update)
```

### Atomic Write

```python
def write_yaml_atomic(state: dict) -> None:
    """Write state file atomically using temp file + rename."""
    yaml_path = get_project_dir() / "active_context.yaml"
    temp_path = yaml_path.with_suffix(".yaml.tmp")

    # Write to temp file
    with open(temp_path, "w") as f:
        yaml.dump(state, f, default_flow_style=False, sort_keys=False)

    # Atomic rename (POSIX guarantees atomicity)
    temp_path.rename(yaml_path)
```

### Fail-Fast on Errors

State operations must fail fast and surface errors:

```python
def save_state_or_fail(state: dict) -> None:
    """Save state or raise with actionable error."""
    try:
        write_yaml_atomic(state)
    except PermissionError as e:
        raise StateError(f"Cannot write state: {e}. Check file permissions.") from e
    except OSError as e:
        raise StateError(f"State write failed: {e}. Disk full?") from e
```

### Invariants

The following invariants are enforced on every state update:

1. **Schema version present**: `schema_version` must exist
2. **Mode valid**: `mode` must be one of `plan`, `active`, `review`, `done`
3. **Single pending junction**: At most one `junction` (null or dict)
4. **Allowances have fingerprints**: Each allowance must have `fingerprint` and `consumed`
5. **Dismissals have expiry**: Each dismissal must have `fingerprint` and `expires_at`

---

## 10. File Structure

```
project/
├── active_context.yaml      # THE state file (schema v4)
├── .proof/
│   ├── session_log.jsonl    # Append-only audit trail
│   └── archive.jsonl        # Archived sessions
└── .claude/
    ├── hooks/
    │   ├── edge_protocol.py # THE protocol (all logic)
    │   ├── session_start.py # Thin: protocol.on_session_start()
    │   ├── pre_tool.py      # Thin: protocol.on_pre_tool_use()
    │   ├── post_tool.py     # Thin: protocol.on_post_tool_use()
    │   └── stop.py          # Thin: protocol.on_stop()
    └── settings.json        # Hook configuration
```

**No other state files. No junction_state. No dispatch_state. No gear_state. No plan_mode flag.**

---

## 10. Migration Path

### Phase 1: Protocol Facade
- Create `edge_protocol.py` with new logic
- Hooks call protocol but old state files still exist
- Protocol reads from old + new, writes to new
- Run in shadow mode: log differences, don't enforce

### Phase 2: Single State
- Migrate all state to `active_context.yaml`
- Stop reading from old state files
- Auto-capture replaces stop-blocking

### Phase 3: Cleanup
- Delete old state files
- Delete old utility modules (junction_utils, dispatch_utils, etc.)
- Simplify hooks to thin shims

### Phase 4: Validation
- Test all modes and transitions
- Verify no blocking loops
- Verify junction suppression works
- Verify auto-capture provides continuity

---

## Summary

| Concern | How It's Addressed |
|---------|-------------------|
| Claude ignores warnings | Warnings don't block; gates do |
| Stop loops | Never block stop; capture observations instead |
| State drift | Single state file + automatic observations |
| Risky actions | Junction gates at PreToolUse |
| Approve doesn't stick | Allowances (one-time) checked before junction creation |
| Dismiss doesn't work | Dismissals (time-limited) checked before junction creation |
| Claims vs reality | Observations validate plan status claims |
| Too many state files | One file: active_context.yaml |
| Complex mode detection | One field: `mode` |
| Race conditions | Transactional updates with file locks |

**Key Concepts:**

| Term | Definition |
|------|------------|
| **Junction** | A decision gate requiring human input before risky action |
| **Allowance** | One-time approval created by `/edge approve`, consumed on use |
| **Dismissal** | Time-limited auto-approval created by `/edge dismiss`, expires after TTL |
| **Observation** | System-captured record of what actually happened (files, tools, tests) |
| **Claim** | Claude's explicit statement (plan status = "completed") |

**The protocol doesn't make Claude obedient. It makes the system resilient to disobedience.**
