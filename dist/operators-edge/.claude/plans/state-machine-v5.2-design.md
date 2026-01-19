# Operator's Edge v5.2: State Machine Improvements
## SOTA Design Document

---

## Executive Summary

Four improvements to make the state machine more robust, observable, and safe:

| Priority | Feature | Impact | Effort |
|----------|---------|--------|--------|
| P0 | Check-specific overrides | Prevents blind approval of all checks | Medium |
| P1 | Integration test suite | Confidence in real-world behavior | Medium |
| P2 | Metrics visibility | User empowerment and debugging | Low |
| P3 | Transactional state updates | Edge case hardening | High |

---

## P0: Check-Specific Quality Gate Overrides

### Problem
Current override bypasses the entire quality gate. Approving once skips ALL 6 checks:
- `steps_have_proof`
- `no_dangling_in_progress`
- `verifications_tested`
- `no_unresolved_mismatches`
- `eval_gate`
- `verification_step_exists`

This is dangerous - a new issue might appear that the user genuinely needs to address.

### Solution: Granular Override with Full-Override Option

```python
# gear_config.py - Enhanced GearState
@dataclass
class QualityGateOverride:
    """Granular quality gate override (v5.2)."""
    mode: str  # "full" | "check_specific"
    approved_at: str
    session_id: str
    objective_hash: int

    # For check_specific mode:
    approved_checks: List[str] = field(default_factory=list)
    # e.g., ["steps_have_proof", "no_dangling_in_progress"]

    # For full mode (legacy behavior):
    reason: str = ""

    def to_dict(self) -> dict:
        return {
            "mode": self.mode,
            "approved_at": self.approved_at,
            "session_id": self.session_id,
            "objective_hash": self.objective_hash,
            "approved_checks": self.approved_checks,
            "reason": self.reason,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "QualityGateOverride":
        return cls(
            mode=data.get("mode", "full"),
            approved_at=data.get("approved_at", ""),
            session_id=data.get("session_id", ""),
            objective_hash=data.get("objective_hash", 0),
            approved_checks=data.get("approved_checks", []),
            reason=data.get("reason", ""),
        )
```

### Override Check Logic

```python
# gear_engine.py
def _check_quality_gate_override(
    gear_state: GearState,
    state: Dict[str, Any],
    failed_checks: List[QualityCheck]
) -> Tuple[bool, List[QualityCheck]]:
    """
    Check if override applies to failed checks (v5.2).

    Returns:
        (skip_gate, remaining_failures)
        - skip_gate: True if all failures are overridden
        - remaining_failures: Checks that aren't overridden
    """
    override = gear_state.quality_gate_override
    if not override:
        return (False, failed_checks)

    # Validate session + objective match
    if not _validate_override_scope(override, state):
        gear_state.quality_gate_override = None
        save_gear_state(gear_state)
        return (False, failed_checks)

    # Full override - bypass everything
    if override.mode == "full":
        return (True, [])

    # Check-specific override - filter failures
    if override.mode == "check_specific":
        remaining = [
            c for c in failed_checks
            if c.name not in override.approved_checks
        ]
        skip = len(remaining) == 0
        return (skip, remaining)

    return (False, failed_checks)
```

### User Interface

```
$ /edge                    # Quality gate fails with 2 errors
Quality gate FAILED - 2 error(s)
  [1] steps_have_proof: Step 3 missing proof
  [2] no_dangling_in_progress: Step 2 still in_progress

Options:
  /edge approve            - Approve ALL checks (full override)
  /edge approve 1          - Approve only check #1
  /edge approve 1,2        - Approve checks #1 and #2
  /edge approve steps_have_proof  - Approve by name
```

### handle_approve Enhancement

```python
def handle_approve(args: str = "") -> tuple[str, bool]:
    """Handle /edge approve [check_specifier]"""
    pending_junction = get_pending_junction()

    if not pending_junction or pending_junction.get("type") != "quality_gate":
        # ... existing non-quality-gate logic
        pass

    # Parse check specifier
    check_specifier = args.strip() if args else ""

    # Get failed checks from junction payload
    failed_checks = pending_junction.get("payload", {}).get("failed_checks", [])

    if not check_specifier:
        # Full override (legacy behavior)
        mode = "full"
        approved_checks = []
        message = "Quality gate FULLY approved"
    else:
        # Parse specifier: "1,2" or "steps_have_proof,eval_gate"
        mode = "check_specific"
        approved_checks = _parse_check_specifier(check_specifier, failed_checks)
        message = f"Approved checks: {', '.join(approved_checks)}"

    # Set override
    state = load_yaml_state()
    gear_state = load_gear_state()
    gear_state.quality_gate_override = QualityGateOverride(
        mode=mode,
        approved_at=datetime.now().isoformat(),
        session_id=get_current_session_id(),
        objective_hash=hash(state.get("objective", "")),
        approved_checks=approved_checks,
        reason="user_approved",
    )
    save_gear_state(gear_state)

    return (f"[OVERRIDE SET] {message}", True)
```

---

## P1: Integration Test Framework

### Problem
Current tests mock file I/O extensively. They verify logic but not real-world behavior.

### Solution: Real-File Test Framework

```python
# test_integration.py
import tempfile
import shutil
from pathlib import Path
from contextlib import contextmanager

@contextmanager
def integration_env():
    """Create a real temporary environment for integration tests."""
    with tempfile.TemporaryDirectory() as tmpdir:
        tmpdir = Path(tmpdir)

        # Create directory structure
        state_dir = tmpdir / ".claude" / "state"
        state_dir.mkdir(parents=True)
        proof_dir = tmpdir / ".proof" / "sessions"
        proof_dir.mkdir(parents=True)

        # Initialize state files
        (state_dir / "gear_state.json").write_text('{}')
        (state_dir / "junction_state.json").write_text('{}')
        (state_dir / "dispatch_state.json").write_text('{}')
        (state_dir / "session_id").write_text("test-session")

        # Create active_context.yaml
        active_context = tmpdir / "active_context.yaml"
        active_context.write_text("""
objective: "Test objective"
plan:
  - description: "Step 1"
    status: "completed"
    proof: "Done"
current_step: 2
""")

        # Patch module paths to use temp dir
        import state_utils
        import proof_utils

        original_get_state_dir = state_utils.get_state_dir
        original_get_proof_dir = proof_utils.get_proof_dir

        state_utils.get_state_dir = lambda: state_dir
        proof_utils.get_proof_dir = lambda: proof_dir

        try:
            yield {
                "root": tmpdir,
                "state_dir": state_dir,
                "proof_dir": proof_dir,
                "active_context": active_context,
            }
        finally:
            state_utils.get_state_dir = original_get_state_dir
            proof_utils.get_proof_dir = original_get_proof_dir


class TestQualityGateOverrideIntegration(unittest.TestCase):
    """Integration tests with real file I/O."""

    def test_full_override_flow(self):
        """End-to-end test: fail gate → approve → bypass."""
        with integration_env() as env:
            from gear_engine import run_gear_engine, load_gear_state
            from edge_skill_hook import handle_approve
            from state_utils import load_yaml_state

            state = load_yaml_state(env["active_context"])

            # First run: should hit quality gate
            result1 = run_gear_engine(state)
            self.assertTrue(result1.junction_hit)
            self.assertEqual(result1.junction_type, "quality_gate")

            # Approve
            message, success = handle_approve()
            self.assertTrue(success)
            self.assertIn("OVERRIDE SET", message)

            # Verify override was persisted to real file
            gear_state = load_gear_state()
            self.assertIsNotNone(gear_state.quality_gate_override)

            # Second run: should bypass
            result2 = run_gear_engine(state)
            self.assertFalse(result2.junction_hit)
            self.assertIn("bypassed", result2.display_message.lower())

    def test_check_specific_override_partial(self):
        """Check-specific override doesn't bypass other checks."""
        with integration_env() as env:
            # Set up state that fails 2 checks
            env["active_context"].write_text("""
objective: "Test"
plan:
  - description: "Step 1"
    status: "completed"
    # Missing proof! (fails steps_have_proof)
  - description: "Step 2"
    status: "in_progress"
    # Still in_progress! (fails no_dangling_in_progress)
current_step: 3
""")
            state = load_yaml_state(env["active_context"])

            # Approve only steps_have_proof
            handle_approve("steps_have_proof")

            # Run gate - should still fail on no_dangling_in_progress
            result = run_gear_engine(state)
            self.assertTrue(result.junction_hit)
            # Remaining failure should be the one we didn't approve
            self.assertIn("in_progress", result.junction_reason)
```

### Test Categories

```
tests/
├── unit/                    # Mocked tests (fast, isolated)
│   ├── test_gear_config.py
│   ├── test_gear_engine.py
│   └── ...
├── integration/             # Real file I/O tests (slower, realistic)
│   ├── test_quality_gate_integration.py
│   ├── test_dispatch_integration.py
│   └── test_junction_integration.py
└── e2e/                     # Full system tests (slowest, comprehensive)
    └── test_edge_command_flow.py
```

---

## P2: Metrics Visibility

### Problem
State machine events are invisible. Users can't see:
- Override usage patterns
- STUCK trigger frequency
- Cleanup events
- Junction drift incidents

### Solution: Metrics Tracking + /edge metrics Command

```python
# metrics_utils.py
from dataclasses import dataclass, field
from typing import Dict, List, Any
from datetime import datetime
from pathlib import Path
import json

@dataclass
class StateMetrics:
    """Session-scoped state machine metrics."""

    # Override metrics
    quality_gate_overrides: int = 0
    full_overrides: int = 0
    check_specific_overrides: int = 0
    override_invalidations: int = 0  # Session/objective changed

    # STUCK metrics
    stuck_triggers: int = 0
    stuck_recoveries: int = 0  # Resolved by plan change
    max_stuck_count_reached: int = 0

    # Cleanup metrics
    orphan_cleanups: int = 0
    stale_obligation_cleanups: int = 0
    snapshot_cleanups: int = 0

    # Junction metrics
    junctions_hit: int = 0
    junctions_approved: int = 0
    junctions_skipped: int = 0
    junctions_dismissed: int = 0

    # Drift detection (should always be 0 after v5.1)
    junction_drift_events: int = 0

    # Timestamps
    session_start: str = ""
    last_updated: str = ""

    def to_dict(self) -> dict:
        return {
            "quality_gate": {
                "overrides": self.quality_gate_overrides,
                "full": self.full_overrides,
                "check_specific": self.check_specific_overrides,
                "invalidations": self.override_invalidations,
            },
            "stuck": {
                "triggers": self.stuck_triggers,
                "recoveries": self.stuck_recoveries,
                "max_reached": self.max_stuck_count_reached,
            },
            "cleanup": {
                "orphans": self.orphan_cleanups,
                "stale_obligations": self.stale_obligation_cleanups,
                "snapshots": self.snapshot_cleanups,
            },
            "junctions": {
                "hit": self.junctions_hit,
                "approved": self.junctions_approved,
                "skipped": self.junctions_skipped,
                "dismissed": self.junctions_dismissed,
            },
            "health": {
                "drift_events": self.junction_drift_events,
            },
            "session_start": self.session_start,
            "last_updated": self.last_updated,
        }


# Global metrics instance (session-scoped)
_metrics: StateMetrics = None

def get_metrics() -> StateMetrics:
    """Get current session metrics."""
    global _metrics
    if _metrics is None:
        _metrics = StateMetrics(
            session_start=datetime.now().isoformat()
        )
    return _metrics

def record_metric(category: str, metric: str, increment: int = 1):
    """Record a metric event."""
    m = get_metrics()
    m.last_updated = datetime.now().isoformat()

    # Quality gate metrics
    if category == "override":
        m.quality_gate_overrides += increment
        if metric == "full":
            m.full_overrides += increment
        elif metric == "check_specific":
            m.check_specific_overrides += increment
        elif metric == "invalidation":
            m.override_invalidations += increment

    # STUCK metrics
    elif category == "stuck":
        if metric == "trigger":
            m.stuck_triggers += increment
        elif metric == "recovery":
            m.stuck_recoveries += increment
        elif metric == "max_reached":
            m.max_stuck_count_reached += increment

    # ... etc for other categories


def format_metrics_display() -> str:
    """Format metrics for /edge metrics display."""
    m = get_metrics()

    lines = [
        "=" * 60,
        "STATE MACHINE METRICS",
        "=" * 60,
        "",
        f"Session: {m.session_start}",
        f"Updated: {m.last_updated or 'never'}",
        "",
        "─" * 60,
        "QUALITY GATE OVERRIDES",
        "─" * 60,
        f"  Total overrides:      {m.quality_gate_overrides}",
        f"    Full (all checks):  {m.full_overrides}",
        f"    Check-specific:     {m.check_specific_overrides}",
        f"  Invalidations:        {m.override_invalidations}",
        "",
        "─" * 60,
        "STUCK DETECTION",
        "─" * 60,
        f"  STUCK triggers:       {m.stuck_triggers}",
        f"  Recoveries:           {m.stuck_recoveries}",
        f"  Max count reached:    {m.max_stuck_count_reached}",
        "",
        "─" * 60,
        "CLEANUP",
        "─" * 60,
        f"  Orphan evals:         {m.orphan_cleanups}",
        f"  Stale obligations:    {m.stale_obligation_cleanups}",
        f"  Old snapshots:        {m.snapshot_cleanups}",
        "",
        "─" * 60,
        "JUNCTIONS",
        "─" * 60,
        f"  Hit:                  {m.junctions_hit}",
        f"  Approved:             {m.junctions_approved}",
        f"  Skipped:              {m.junctions_skipped}",
        f"  Dismissed:            {m.junctions_dismissed}",
        "",
        "─" * 60,
        "HEALTH",
        "─" * 60,
        f"  Junction drift:       {m.junction_drift_events} " +
        ("✓ (healthy)" if m.junction_drift_events == 0 else "⚠ (investigate)"),
        "",
        "=" * 60,
    ]
    return "\n".join(lines)
```

### Integration Points

```python
# In handle_approve():
from metrics_utils import record_metric

if is_quality_gate:
    record_metric("override", "full" if mode == "full" else "check_specific")

# In dispatch_hook.py handle_approve():
if is_stuck:
    record_metric("stuck", "trigger")

# In cleanup_orphaned_eval_state():
if cleared:
    record_metric("cleanup", "orphan")
```

---

## P3: Transactional State Updates

### Problem
Multiple state files can become inconsistent if a crash happens mid-update:
- Junction cleared but override not set
- Gear transitioned but dispatch not updated
- Override set but save failed

### Solution: Write-Ahead Log (WAL) Pattern

```python
# transaction_utils.py
from contextlib import contextmanager
from pathlib import Path
from datetime import datetime
import json
import shutil

WAL_FILE = ".claude/state/wal.json"

@dataclass
class Transaction:
    """A pending transaction with rollback capability."""
    id: str
    started_at: str
    operations: List[Dict[str, Any]]
    completed: bool = False

    def add_operation(self, op_type: str, target: str, old_value: Any, new_value: Any):
        self.operations.append({
            "type": op_type,
            "target": target,
            "old": old_value,
            "new": new_value,
        })


def _get_wal_path() -> Path:
    return get_state_dir() / "wal.json"

def _load_wal() -> Optional[Transaction]:
    """Load pending transaction from WAL."""
    wal_path = _get_wal_path()
    if not wal_path.exists():
        return None
    try:
        data = json.loads(wal_path.read_text())
        return Transaction(**data)
    except Exception:
        return None

def _save_wal(tx: Transaction):
    """Persist transaction to WAL."""
    wal_path = _get_wal_path()
    wal_path.write_text(json.dumps({
        "id": tx.id,
        "started_at": tx.started_at,
        "operations": tx.operations,
        "completed": tx.completed,
    }))

def _clear_wal():
    """Clear WAL after successful commit."""
    wal_path = _get_wal_path()
    if wal_path.exists():
        wal_path.unlink()

def _rollback(tx: Transaction):
    """Rollback a failed transaction."""
    for op in reversed(tx.operations):
        if op["type"] == "file_write":
            target = Path(op["target"])
            if op["old"] is not None:
                target.write_text(op["old"])
            elif target.exists():
                target.unlink()


@contextmanager
def atomic_state_update():
    """
    Context manager for atomic multi-file state updates.

    Usage:
        with atomic_state_update() as tx:
            tx.add_operation("file_write", "gear_state.json", old_content, new_content)
            write_file(...)

            tx.add_operation("file_write", "junction_state.json", old_j, new_j)
            write_file(...)

    If any operation fails, all changes are rolled back.
    """
    # Check for incomplete transaction from crash
    existing_tx = _load_wal()
    if existing_tx and not existing_tx.completed:
        print(f"[RECOVERY] Rolling back incomplete transaction {existing_tx.id}")
        _rollback(existing_tx)
        _clear_wal()

    # Start new transaction
    tx = Transaction(
        id=datetime.now().strftime("%Y%m%d%H%M%S%f"),
        started_at=datetime.now().isoformat(),
        operations=[],
    )
    _save_wal(tx)

    try:
        yield tx

        # Mark complete
        tx.completed = True
        _save_wal(tx)
        _clear_wal()

    except Exception as e:
        # Rollback on failure
        _rollback(tx)
        _clear_wal()
        raise


# Usage in handle_approve():
def handle_approve_transactional(args: str = "") -> tuple[str, bool]:
    with atomic_state_update() as tx:
        # Read current states
        old_junction = junction_state_path.read_text()
        old_gear = gear_state_path.read_text()

        # Record what we're about to do
        tx.add_operation("file_write", str(junction_state_path), old_junction, None)
        clear_pending_junction("approve")

        tx.add_operation("file_write", str(gear_state_path), old_gear, new_gear_json)
        save_gear_state(gear_state)

    # If we get here, both writes succeeded
    return ("[APPROVED]", True)
```

### Recovery on Session Start

```python
# session_start.py
def recover_from_incomplete_transactions():
    """Check for and recover from incomplete transactions."""
    from transaction_utils import _load_wal, _rollback, _clear_wal

    tx = _load_wal()
    if tx and not tx.completed:
        log_proof("transaction_recovery", {
            "transaction_id": tx.id,
            "operations": len(tx.operations),
        }, "Recovered from incomplete transaction", success=True)
        _rollback(tx)
        _clear_wal()
        return True
    return False
```

---

## Implementation Order

| Phase | Tasks | Risk | Dependencies |
|-------|-------|------|--------------|
| 1 | P0: Check-specific overrides | Low | None |
| 2 | P2: Metrics tracking | Low | None |
| 3 | P1: Integration tests | Low | Phases 1-2 (to verify) |
| 4 | P3: Transactional updates | Medium | All (requires careful refactor) |

---

## Files to Modify

| File | Changes |
|------|---------|
| `gear_config.py` | Add `QualityGateOverride` dataclass |
| `gear_engine.py` | Update override check to be check-specific |
| `edge_skill_hook.py` | Parse check specifier in handle_approve |
| `metrics_utils.py` | NEW: Metrics tracking module |
| `transaction_utils.py` | NEW: WAL-based transactions |
| `session_start.py` | Add transaction recovery |
| `test_integration.py` | NEW: Integration test suite |

---

## Design Decisions

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Override granularity | Full OR check-specific | Flexibility for different use cases |
| Metrics scope | Session-only | Avoid bloating persistent state |
| Integration tests | Separate directory | Keep fast unit tests fast |
| Transaction recovery | On session start | Clean slate for each session |
| WAL persistence | JSON file | Simple, human-readable, atomic rename |
