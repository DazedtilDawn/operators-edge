# v8.0 Phase 9: Outcome Tracking & Closed Loop

## Where We Are

Phase 8 built **active intervention** - escalating guidance based on session health. But the effectiveness data reveals a fundamental problem:

```
DRIFT DETECTION          7%   ← Signals fire but behavior doesn't change
KNOWN FIX SUGGESTIONS    --   ← No data yet (tracking gap!)
SESSION HANDOFFS         --   ← No data yet
CONTEXT EFFICIENCY       81%  ← This works!
```

The system **observes** and **warns** but rarely **corrects**. Phase 8's intervention levels (observe → advise → guide → intervene) are the infrastructure. Phase 9 completes the loop.

## Research Findings

### Current Infrastructure Analysis

**`codebase_knowledge.py`** (Phase 3):
- ✅ `KnownFix` dataclass with confidence, times_used, commands, files
- ✅ `record_fix()` - records what fixed an error
- ✅ `lookup_fix()` - finds fixes by error signature
- ✅ Confidence decay over 30 days
- ❌ No tracking of fix **outcomes** (did it actually work when applied?)
- ❌ Confidence only increases on re-use, not on verified success

**`session_metrics.py`** (Phase 5):
- ✅ `record_fix_surfaced()` - when fix is shown
- ✅ `record_fix_followed()` - manual call when fix applied
- ✅ `record_fix_ignored()` - manual call when ignored
- ❌ No **automatic** detection of fix follow/ignore
- ❌ No correlation between "fix surfaced" and "next command success"

**`post_tool.py`** (Integration):
- ✅ `lookup_known_fix()` - surfaces fix on error
- ✅ `record_successful_fix()` - records fix when command succeeds after failure
- ✅ `_recent_bash_failure` - tracks error→success pairs
- ❌ Gap: No correlation between **surfaced fix** and subsequent success
- ❌ Gap: `record_fix_followed()` never called automatically

**`active_intervention.py`** (Phase 8):
- ✅ `SessionHealth.pending_error` and `pending_fix` tracking
- ✅ `update_health_from_error(error, fix)` - stores pending fix
- ✅ `update_health_from_success()` - clears pending error
- ❌ Gap: Success doesn't check if it matches the pending fix
- ❌ Gap: No outcome feedback to codebase_knowledge

### The Core Gap

When a fix is surfaced and then Claude runs the suggested command:
1. We know the fix was surfaced ✅
2. We know a command succeeded ✅
3. We don't know if the **success was because of the fix** ❌

This breaks the feedback loop. Fixes can't get smarter.

## Phase 9: Outcome Tracking & Closed Loop

### 9.1: Fix Outcome Tracking (`fix_outcomes.py`)

**Problem:** We surface fixes but don't track if they actually work.

**Solution:** Track the complete fix lifecycle with correlation IDs.

```python
@dataclass
class FixOutcome:
    """Track the outcome of a surfaced fix."""
    outcome_id: str          # Unique ID for this outcome event
    fix_signature: str       # Hash of the error signature
    surfaced_at: str         # When fix was shown
    surfaced_commands: List[str]  # Commands suggested

    # Outcome tracking
    followed: bool = False   # Did Claude run a suggested command?
    followed_at: Optional[str] = None
    followed_command: Optional[str] = None

    success: bool = False    # Did the next command succeed?
    success_verified_at: Optional[str] = None

    # Correlation data
    next_commands: List[str] = field(default_factory=list)  # Commands run after surfacing

def track_fix_surfaced(fix: KnownFix) -> str:
    """
    Record that a fix was surfaced and return tracking ID.
    Called from post_tool.py when lookup_known_fix finds a match.
    """
    outcome_id = generate_outcome_id()

    outcome = FixOutcome(
        outcome_id=outcome_id,
        fix_signature=compute_signature_hash(fix.error_signature),
        surfaced_at=datetime.now().isoformat(),
        surfaced_commands=fix.fix_commands,
    )

    _store_pending_outcome(outcome)
    return outcome_id

def track_command_after_fix(command: str, success: bool) -> None:
    """
    Called after any Bash command to check if it relates to a pending fix.
    """
    pending = _get_pending_outcome()
    if not pending:
        return

    # Record this command
    pending.next_commands.append(command)

    # Check if this command matches a suggested fix command
    if _command_matches_fix(command, pending.surfaced_commands):
        pending.followed = True
        pending.followed_at = datetime.now().isoformat()
        pending.followed_command = command

        if success:
            pending.success = True
            pending.success_verified_at = datetime.now().isoformat()

            # Update fix confidence in codebase_knowledge!
            _boost_fix_confidence(pending.fix_signature)

            # Record in metrics
            record_fix_followed(success=True)
        else:
            # They followed the fix but it failed
            _decay_fix_confidence(pending.fix_signature)
            record_fix_followed(success=False)

        # Outcome determined, save and clear
        _save_outcome(pending)
        _clear_pending_outcome()

    # Timeout: if 5+ commands pass without following, consider it ignored
    elif len(pending.next_commands) >= 5:
        record_fix_ignored()
        _save_outcome(pending)
        _clear_pending_outcome()
```

**Key Features:**
- Automatic detection of "followed" vs "ignored"
- Command matching (fuzzy - handles variations)
- Confidence feedback loop to codebase_knowledge
- Timeout-based ignore detection

### 9.2: Integration into post_tool.py

**Changes to `post_tool.py`:**

```python
# At module level
_pending_fix_outcome_id: Optional[str] = None

def lookup_known_fix(error_output: str):
    """Modified to track fix surfacing."""
    global _pending_fix_outcome_id

    fix = lookup_fix(error_output)
    if fix and fix.confidence >= 0.4:
        # Phase 9: Track this fix surfacing
        try:
            from fix_outcomes import track_fix_surfaced
            _pending_fix_outcome_id = track_fix_surfaced(fix)
        except ImportError:
            pass

        # ... existing display logic ...

# In main(), after Bash success/failure handling:
def main():
    # ... existing code ...

    if tool_name == "Bash":
        # ... existing error handling ...

        # Phase 9: Track command for fix outcome correlation
        try:
            from fix_outcomes import track_command_after_fix
            track_command_after_fix(cmd, success)
        except ImportError:
            pass
```

**This closes the loop:**
1. Error occurs → `lookup_known_fix()` surfaces fix and starts tracking
2. Any subsequent Bash command → `track_command_after_fix()` checks correlation
3. If command matches suggested fix → update outcome + feedback to knowledge
4. If 5+ commands pass without match → mark as ignored

### 9.3: Confidence Feedback to codebase_knowledge.py

**New functions in `codebase_knowledge.py`:**

```python
def boost_fix_confidence(sig_hash: str, amount: float = 0.1) -> bool:
    """
    Boost confidence when a fix is verified to work.

    Called when:
    - Fix surfaced → user ran suggested command → command succeeded
    """
    knowledge = _load_knowledge()
    fix_data = knowledge["fixes"].get(sig_hash)

    if not fix_data:
        return False

    # Boost confidence (cap at 0.95)
    fix_data["confidence"] = min(0.95, fix_data.get("confidence", 0.5) + amount)
    fix_data["times_used"] = fix_data.get("times_used", 0) + 1
    fix_data["last_success"] = datetime.now().isoformat()

    knowledge["fixes"][sig_hash] = fix_data
    return _save_knowledge(knowledge)


def decay_fix_confidence(sig_hash: str, amount: float = 0.15) -> bool:
    """
    Decay confidence when a fix fails to work.

    Called when:
    - Fix surfaced → user ran suggested command → command FAILED
    """
    knowledge = _load_knowledge()
    fix_data = knowledge["fixes"].get(sig_hash)

    if not fix_data:
        return False

    # Decay confidence (floor at 0.1)
    fix_data["confidence"] = max(0.1, fix_data.get("confidence", 0.5) - amount)

    # Track failures
    fix_data["failures"] = fix_data.get("failures", 0) + 1

    knowledge["fixes"][sig_hash] = fix_data
    return _save_knowledge(knowledge)
```

**This creates a true learning loop:**
- Fixes that work get stronger (confidence ↑)
- Fixes that fail get weaker (confidence ↓)
- Bad fixes naturally decay below the 0.4 display threshold
- Good fixes naturally rise toward 0.9+ (auto-fix territory)

### 9.4: Command Matching Logic

**The key challenge:** How do we know if a command "matches" a suggested fix?

```python
def command_matches_fix(actual: str, suggested_commands: List[str]) -> bool:
    """
    Check if the actual command matches any suggested fix command.

    Matching rules:
    1. Exact match (normalized)
    2. Same base command with different args
    3. Equivalent commands (pip install == pip3 install)
    """
    actual_norm = normalize_command(actual)

    for suggested in suggested_commands:
        suggested_norm = normalize_command(suggested)

        # Exact match
        if actual_norm == suggested_norm:
            return True

        # Same base command
        if get_base_command(actual_norm) == get_base_command(suggested_norm):
            # Check if target is same (e.g., "pip install requests" matches "pip install requests==2.0")
            if get_command_target(actual_norm) == get_command_target(suggested_norm):
                return True

    return False


def normalize_command(cmd: str) -> str:
    """Normalize a command for comparison."""
    # Remove leading/trailing whitespace
    cmd = cmd.strip()
    # Normalize pip/pip3
    cmd = re.sub(r'^pip3\b', 'pip', cmd)
    # Normalize python/python3
    cmd = re.sub(r'^python3\b', 'python', cmd)
    # Remove common prefix variations
    cmd = re.sub(r'^(sudo\s+)', '', cmd)
    return cmd.lower()


def get_base_command(cmd: str) -> str:
    """Extract base command (e.g., 'pip install' from 'pip install requests')."""
    parts = cmd.split()
    if len(parts) >= 2:
        # Common two-word commands
        if parts[0] in ('pip', 'npm', 'yarn', 'git', 'docker', 'kubectl'):
            return ' '.join(parts[:2])
    return parts[0] if parts else ""


def get_command_target(cmd: str) -> str:
    """Extract target (e.g., 'requests' from 'pip install requests==2.0')."""
    parts = cmd.split()
    if len(parts) >= 3:
        # For install commands, get the package name without version
        target = parts[2]
        # Remove version specifiers
        target = re.split(r'[=<>~!]', target)[0]
        return target.lower()
    return ""
```

**Examples:**
- `pip install requests` matches `pip3 install requests==2.28.0` ✅
- `npm install express` matches `npm i express` ✅ (with alias handling)
- `git pull` matches `git pull origin main` ✅
- `pip install requests` does NOT match `pip install flask` ❌

### 9.5: Outcome Storage & Reporting

**Storage:** `.proof/fix_outcomes.jsonl`

```jsonl
{"outcome_id":"abc123","fix_signature":"1184ab339d04","surfaced_at":"2026-01-18T10:00:00","followed":true,"success":true,"followed_command":"pip install requests"}
{"outcome_id":"def456","fix_signature":"5678ef901234","surfaced_at":"2026-01-18T11:00:00","followed":false,"success":false,"next_commands":["ls","cd","vim"]}
```

**Reporting in `effectiveness_analyzer.py`:**

```python
def analyze_fix_outcomes(proof_dir: Path, days: int = 7) -> FixEffectiveness:
    """
    Analyze fix outcomes to determine effectiveness.
    """
    outcomes_path = proof_dir / "fix_outcomes.jsonl"
    if not outcomes_path.exists():
        return FixEffectiveness()

    outcomes = load_outcomes(outcomes_path, days)

    return FixEffectiveness(
        total_surfaced=len(outcomes),
        followed=sum(1 for o in outcomes if o.followed),
        followed_success=sum(1 for o in outcomes if o.followed and o.success),
        ignored=sum(1 for o in outcomes if not o.followed),
        follow_rate=...,
        success_rate=...,
    )
```

**This enables:**
- Real fix hit rate data (currently "--" in effectiveness report)
- Trend analysis (are fixes getting better over time?)
- Per-fix effectiveness (which fixes work, which don't?)

## Implementation Order

1. **9.1 Fix Outcome Tracking** (`fix_outcomes.py`) - Core module
2. **9.2 Integration** - Wire into post_tool.py
3. **9.3 Confidence Feedback** - Add boost/decay to codebase_knowledge.py
4. **9.4 Command Matching** - Fuzzy match logic
5. **9.5 Reporting** - Update effectiveness_analyzer.py

## Configuration

No new configuration needed. Outcome tracking is automatic and transparent.

The existing thresholds in `codebase_knowledge.py` control behavior:
- `0.4` - Minimum confidence to surface a fix
- `0.6` - Starting confidence for new fixes
- `0.95` - Maximum confidence cap
- `30 days` - Decay period
```

## Success Criteria

1. **Fix hit rate becomes measurable** - Currently "--", should show real data
2. **Confidence reflects reality** - Fixes that work get stronger, fixes that don't get weaker
3. **Follow rate > 50%** - Most surfaced fixes should be followed
4. **Success rate when followed > 70%** - Following fixes should usually help

## Risk Mitigation

| Risk | Mitigation |
|------|------------|
| False positive match | Conservative command matching, exact target match required |
| Feedback loop diverges | Decay caps (0.1 floor, 0.95 ceiling) |
| Performance impact | Minimal - one JSON check per Bash command |
| Storage growth | JSONL format, easy to truncate old entries |

## Timeline Estimate

- 9.1 Fix Outcome Tracking: 3-4 hours
- 9.2 Integration: 1-2 hours
- 9.3 Confidence Feedback: 1-2 hours
- 9.4 Command Matching: 2-3 hours
- 9.5 Reporting: 2-3 hours
- Testing: 4-5 hours

Total: ~14-18 hours

## Files to Create/Modify

**New:**
- `fix_outcomes.py` - Outcome tracking module (~200 lines)
- `test_fix_outcomes.py` - Tests (~30 tests)

**Modified:**
- `codebase_knowledge.py` - Add boost_fix_confidence, decay_fix_confidence
- `post_tool.py` - Add track_command_after_fix integration
- `effectiveness_analyzer.py` - Add fix outcome analysis
- `CHANGELOG.md` - Phase 9 documentation

## The Philosophy

Phase 8 made it **impossible to miss** the guidance.
Phase 9 makes the guidance **learn from outcomes**.

The difference:
- Phase 8: "Here's a fix!" (one-way communication)
- Phase 9: "Here's a fix... did it work? Let me remember that." (feedback loop)

We're not making Claude smarter. We're making the **knowledge base** smarter through verified outcomes.

## Future: Phase 10 Auto-Fix

Once Phase 9 establishes reliable outcome tracking with high success rates for followed fixes, Phase 10 can safely implement auto-fix:

**Prerequisites from Phase 9:**
- ✅ Verified confidence (fixes that reach 0.9+ actually work)
- ✅ Success rate data (we know which fixes are reliable)
- ✅ Failure tracking (we know which fixes to never auto-apply)

**Phase 10 would add:**
- Auto-apply for fixes with confidence ≥ 0.9 AND success_rate ≥ 90%
- Destructive command blocking (rm, git push, etc.)
- User opt-in configuration

Phase 9 is the foundation that makes Phase 10 safe.
