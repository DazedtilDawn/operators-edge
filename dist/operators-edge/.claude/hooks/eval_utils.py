#!/usr/bin/env python3
"""
Operator's Edge - Eval Utilities
Core eval primitives: snapshots, diffs, invariant checks, eval logging.

Designed to be lightweight, deterministic, and safe by default.
"""
import json
import hashlib
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from state_utils import (
    get_project_dir,
    get_proof_dir,
    get_state_dir,
    parse_simple_yaml,
    file_hash,
    write_text_atomic,
)


# =============================================================================
# DEFAULTS
# =============================================================================

DEFAULT_EVALS_CONFIG = {
    "enabled": True,
    "mode": "auto",  # auto | manual
    "level": 0,      # 0 | 1 | 2
    "triage": {
        "signals": [],
        "score": 0,
        "thresholds": {"level1": 3, "level2": 5},
    },
    "policy": {
        "warn_only": True,
        "gate_on_fail": False,
    },
    "snapshots": {
        "enabled": True,
        "format": "json",
        "max_bytes": 2_000_000,
        "redactions": [],
    },
    "trials": {"count": 5},
    "task_bank": [],
    "ship_block_rule": "All invariants pass on task bank",
}

REQUIRED_STATE_KEYS = ["objective", "plan", "current_step"]
STATEFUL_KEYWORDS = [
    "memory", "db", "database", "schema", "migrate", "migration",
    "tasks", "sync", "state", "eval", "guardrail", "autonomous",
]


# =============================================================================
# CONFIG
# =============================================================================

def _deep_merge(base: Dict[str, Any], override: Dict[str, Any]) -> Dict[str, Any]:
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(base.get(key), dict):
            base[key] = _deep_merge(base[key], value)
        else:
            base[key] = value
    return base


def get_evals_config(state: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """Return evals config merged with defaults."""
    merged = json.loads(json.dumps(DEFAULT_EVALS_CONFIG))
    if not state:
        return merged
    evals = state.get("evals") or {}
    if isinstance(evals, dict):
        merged = _deep_merge(merged, evals)
    return merged


# =============================================================================
# EVAL STATE (SESSION CACHE)
# =============================================================================

def get_eval_state_file() -> Path:
    return get_state_dir() / "eval_state.json"


def load_eval_state() -> Dict[str, Any]:
    path = get_eval_state_file()
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text())
    except Exception:
        return {}


def save_eval_state(state: Dict[str, Any]) -> None:
    path = get_eval_state_file()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(state, ensure_ascii=True, default=str, indent=2))


# =============================================================================
# AUTO TRIAGE
# =============================================================================

def _objective_is_stateful(objective: Optional[str]) -> bool:
    if not objective:
        return False
    text = objective.lower()
    return any(keyword in text for keyword in STATEFUL_KEYWORDS)


def _has_recent_eval_failures(max_lines: int = 200) -> bool:
    log_file = get_proof_dir() / "session_log.jsonl"
    if not log_file.exists():
        return False
    try:
        lines = log_file.read_text().splitlines()[-max_lines:]
        for line in lines:
            try:
                entry = json.loads(line)
            except Exception:
                continue
            if entry.get("type") == "eval_run" and entry.get("invariants_failed"):
                if len(entry.get("invariants_failed", [])) > 0:
                    return True
    except Exception:
        return False
    return False


def auto_triage(state: Optional[Dict[str, Any]], evals_config: Dict[str, Any],
                tool_name: Optional[str] = None) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    """Return evals config updated with auto-triage results."""
    if not evals_config.get("enabled", True):
        return evals_config, {"result": "disabled"}

    if evals_config.get("mode") == "manual":
        return evals_config, {"result": "manual"}

    signals = []
    if state:
        signals.append("persistent_state")

    proof_dir = get_proof_dir()
    if proof_dir.exists():
        signals.append("proof_dir")

    objective = state.get("objective") if isinstance(state, dict) else None
    if _objective_is_stateful(objective):
        signals.append("stateful_objective")

    if tool_name in ("Edit", "Write", "NotebookEdit"):
        signals.append("writes")

    if _has_recent_eval_failures():
        signals.append("recent_eval_failures")

    score = len(signals)
    thresholds = evals_config.get("triage", {}).get("thresholds", {"level1": 3, "level2": 5})
    level = 0
    if score >= thresholds.get("level2", 5):
        level = 2
    elif score >= thresholds.get("level1", 3):
        level = 1

    triage = {
        "signals": signals,
        "score": score,
        "thresholds": thresholds,
        "updated_at": datetime.now().isoformat(),
    }
    evals_config["level"] = level
    evals_config["triage"] = triage
    return evals_config, triage


# =============================================================================
# SNAPSHOTS
# =============================================================================

def _safe_payload(data: Any, max_bytes: int) -> Tuple[Any, bool]:
    raw = json.dumps(data, ensure_ascii=True, default=str)
    size = len(raw.encode("utf-8"))
    if size <= max_bytes:
        return data, False
    summary: Dict[str, Any] = {
        "_truncated": True,
        "size_bytes": size,
        "hash": hashlib.sha256(raw.encode("utf-8")).hexdigest(),
    }
    if isinstance(data, dict):
        summary["keys"] = list(data.keys())[:50]
    return summary, True


def _load_active_context() -> Tuple[Optional[Dict[str, Any]], Optional[str], Optional[str]]:
    state_file = get_project_dir() / "active_context.yaml"
    if not state_file.exists():
        return None, "active_context.yaml missing", None
    try:
        content = state_file.read_text()
        state = parse_simple_yaml(content)
        return state, None, content
    except Exception as exc:
        return None, f"parse_error: {exc}", None


def build_state_snapshot() -> Dict[str, Any]:
    """Build a snapshot of active_context.yaml and basic metadata."""
    state_file = get_project_dir() / "active_context.yaml"
    state, error, raw = _load_active_context()

    snapshot = {
        "timestamp": datetime.now().isoformat(),
        "source": "active_context.yaml",
        "meta": {
            "path": str(state_file),
            "hash": file_hash(state_file),
            "size_bytes": len(raw.encode("utf-8")) if raw else None,
            "parse_ok": error is None,
            "error": error,
        },
        "state": state,
    }
    return snapshot


def get_eval_base_dir() -> Path:
    return get_proof_dir() / "evals"


def create_eval_run_dir(date_str: Optional[str] = None) -> Tuple[Path, int]:
    """Create a run directory under .proof/evals/YYYY-MM-DD/run-XX."""
    base_dir = get_eval_base_dir()
    date_str = date_str or datetime.now().strftime("%Y-%m-%d")
    day_dir = base_dir / date_str
    day_dir.mkdir(parents=True, exist_ok=True)

    run_ids: List[int] = []
    for entry in day_dir.glob("run-*"):
        try:
            run_ids.append(int(entry.name.split("-")[1]))
        except Exception:
            continue

    next_id = max(run_ids) + 1 if run_ids else 1
    run_dir = day_dir / f"run-{next_id:02d}"
    run_dir.mkdir(parents=True, exist_ok=True)
    return run_dir, next_id


def write_snapshot(run_dir: Path, label: str, evals_config: Dict[str, Any]) -> Path:
    """Write a snapshot JSON file and return its path."""
    snapshot = build_state_snapshot()
    max_bytes = int(evals_config.get("snapshots", {}).get("max_bytes", 2_000_000))
    payload, truncated = _safe_payload(snapshot, max_bytes)
    if truncated:
        payload = {
            "timestamp": snapshot.get("timestamp"),
            "source": snapshot.get("source"),
            "meta": snapshot.get("meta"),
            "snapshot": payload,
        }

    path = run_dir / f"{label}.json"
    path.write_text(json.dumps(payload, ensure_ascii=True, default=str, indent=2))
    return path


# =============================================================================
# DIFFS
# =============================================================================

def _diff_values(before: Any, after: Any, path: str, changes: List[Dict[str, Any]],
                 max_changes: int, truncated: List[bool]) -> None:
    if len(changes) >= max_changes:
        truncated[0] = True
        return

    if isinstance(before, dict) and isinstance(after, dict):
        before_keys = set(before.keys())
        after_keys = set(after.keys())

        for key in sorted(before_keys - after_keys):
            if len(changes) >= max_changes:
                truncated[0] = True
                return
            changes.append({"path": f"{path}.{key}" if path else str(key),
                            "kind": "removed", "before": before.get(key), "after": None})

        for key in sorted(after_keys - before_keys):
            if len(changes) >= max_changes:
                truncated[0] = True
                return
            changes.append({"path": f"{path}.{key}" if path else str(key),
                            "kind": "added", "before": None, "after": after.get(key)})

        for key in sorted(before_keys & after_keys):
            _diff_values(before.get(key), after.get(key),
                         f"{path}.{key}" if path else str(key),
                         changes, max_changes, truncated)
        return

    if isinstance(before, list) and isinstance(after, list):
        min_len = min(len(before), len(after))
        for idx in range(min_len):
            _diff_values(before[idx], after[idx], f"{path}[{idx}]", changes, max_changes, truncated)
            if truncated[0]:
                return
        for idx in range(min_len, len(before)):
            if len(changes) >= max_changes:
                truncated[0] = True
                return
            changes.append({"path": f"{path}[{idx}]", "kind": "removed",
                            "before": before[idx], "after": None})
        for idx in range(min_len, len(after)):
            if len(changes) >= max_changes:
                truncated[0] = True
                return
            changes.append({"path": f"{path}[{idx}]", "kind": "added",
                            "before": None, "after": after[idx]})
        return

    if before != after:
        changes.append({"path": path, "kind": "changed", "before": before, "after": after})


def compute_state_diff(before_state: Optional[Dict[str, Any]],
                       after_state: Optional[Dict[str, Any]],
                       max_changes: int = 500) -> Dict[str, Any]:
    changes: List[Dict[str, Any]] = []
    truncated = [False]
    _diff_values(before_state, after_state, "", changes, max_changes, truncated)
    summary = {
        "added": sum(1 for c in changes if c["kind"] == "added"),
        "removed": sum(1 for c in changes if c["kind"] == "removed"),
        "changed": sum(1 for c in changes if c["kind"] == "changed"),
    }
    return {"changes": changes, "summary": summary, "truncated": truncated[0]}


def write_diff(run_dir: Path, diff: Dict[str, Any], evals_config: Dict[str, Any]) -> Path:
    max_bytes = int(evals_config.get("snapshots", {}).get("max_bytes", 2_000_000))
    payload, truncated = _safe_payload(diff, max_bytes)
    if truncated:
        payload = {"diff": payload, "truncated": True}
    path = run_dir / "diff.json"
    path.write_text(json.dumps(payload, ensure_ascii=True, default=str, indent=2))
    return path


def _load_snapshot_state(snapshot_path: Path) -> Tuple[Optional[Dict[str, Any]], bool]:
    """Load snapshot JSON and return (state, truncated)."""
    if not snapshot_path.exists():
        return None, False
    try:
        payload = json.loads(snapshot_path.read_text())
    except Exception:
        return None, False
    if isinstance(payload, dict) and "state" in payload:
        return payload.get("state"), False
    if isinstance(payload, dict) and "snapshot" in payload:
        return None, True
    return None, False


def start_eval_run(evals_config: Dict[str, Any], tool_name: str) -> Dict[str, Any]:
    """Create a run dir and write the before snapshot."""
    run_dir, run_id = create_eval_run_dir()
    before_path = write_snapshot(run_dir, "before", evals_config)
    return {
        "run_dir": str(run_dir),
        "run_id": run_id,
        "before": str(before_path),
        "tool": tool_name,
        "level": evals_config.get("level", 0),
        "invariants": evals_config.get("invariants", []),
        "policy": evals_config.get("policy", {}),
        "triage": evals_config.get("triage", {}),
        "started_at": datetime.now().isoformat(),
    }


def finish_eval_run(pending_run: Dict[str, Any],
                    evals_config: Dict[str, Any],
                    tool_success: bool) -> Dict[str, Any]:
    """Finalize a run: write after snapshot, diff, invariants, and log."""
    run_dir = Path(pending_run["run_dir"])
    before_path = Path(pending_run["before"])
    after_path = write_snapshot(run_dir, "after", evals_config)

    before_state, before_truncated = _load_snapshot_state(before_path)
    after_state, after_truncated = _load_snapshot_state(after_path)

    if before_state is None or after_state is None:
        diff = {"changes": [], "summary": {}, "truncated": True, "reason": "snapshot_truncated"}
    else:
        diff = compute_state_diff(before_state, after_state, max_changes=500)

    diff_path = write_diff(run_dir, diff, evals_config)

    invariants = pending_run.get("invariants") or evals_config.get("invariants", [])
    if before_state is None or after_state is None:
        results = {
            "passed": [],
            "failed": [],
            "skipped": [{
                "id": inv.get("id") if isinstance(inv, dict) else str(inv),
                "status": "skipped",
                "message": "Snapshot truncated; invariants skipped",
                "details": None,
            } for inv in invariants]
        }
    else:
        results = run_invariant_checks(invariants, before_state, after_state, diff, evals_config)

    passed_ids = [r["id"] for r in results.get("passed", [])]
    failed_ids = [r["id"] for r in results.get("failed", [])]
    skipped_ids = [r["id"] for r in results.get("skipped", [])]

    entry = {
        "type": "eval_run",
        "level": pending_run.get("level", evals_config.get("level", 0)),
        "tool": pending_run.get("tool"),
        "success": tool_success,
        "invariants_passed": passed_ids,
        "invariants_failed": failed_ids,
        "invariants_skipped": skipped_ids,
        "snapshots": {
            "before": str(before_path),
            "after": str(after_path),
            "diff": str(diff_path),
        },
        "diff_summary": diff.get("summary", {}),
        "triage": pending_run.get("triage", {}),
        "truncated": before_truncated or after_truncated or diff.get("truncated"),
    }
    log_eval_run(entry)
    return entry


# =============================================================================
# INVARIANTS
# =============================================================================

def _check_schema_valid(after_state: Optional[Dict[str, Any]]) -> Tuple[str, str, Optional[List[str]]]:
    if not after_state or not isinstance(after_state, dict):
        return ("failed", "State is missing or invalid", None)
    missing = [key for key in REQUIRED_STATE_KEYS if key not in after_state]
    if missing:
        return ("failed", "Missing required keys", missing)
    return ("passed", "State schema looks valid", None)


def _path_allowed(path: str, allow_list: List[str]) -> bool:
    return any(path.startswith(prefix) for prefix in allow_list)


def _check_no_silent_deletions(diff: Dict[str, Any], allow_list: List[str]) -> Tuple[str, str, Optional[List[str]]]:
    removed_paths = [c["path"] for c in diff.get("changes", []) if c.get("kind") == "removed"]
    if not removed_paths:
        return ("passed", "No deletions detected", None)
    if allow_list:
        remaining = [p for p in removed_paths if not _path_allowed(p, allow_list)]
    else:
        remaining = removed_paths
    if not remaining:
        return ("passed", "Only allowed deletions detected", None)
    return ("failed", "Silent deletions detected", remaining)


def _check_expected_changes_only(diff: Dict[str, Any], expected: List[str]) -> Tuple[str, str, Optional[List[str]]]:
    if not expected:
        return ("skipped", "No expected_changes configured", None)
    unexpected = []
    for change in diff.get("changes", []):
        path = change.get("path", "")
        if not _path_allowed(path, expected):
            unexpected.append(path)
    if unexpected:
        return ("failed", "Unexpected changes detected", unexpected)
    return ("passed", "All changes are expected", None)


INVARIANT_CHECKS = {
    "INV-01": lambda before, after, diff, config: _check_schema_valid(after),
    "INV-02": lambda before, after, diff, config: _check_no_silent_deletions(
        diff, config.get("allow_deletions", [])),
    "INV-05": lambda before, after, diff, config: _check_expected_changes_only(
        diff, config.get("expected_changes", [])),
}


def run_invariant_checks(
    invariants: List[Dict[str, Any]],
    before_state: Optional[Dict[str, Any]],
    after_state: Optional[Dict[str, Any]],
    diff: Dict[str, Any],
    evals_config: Dict[str, Any],
) -> Dict[str, List[Dict[str, Any]]]:
    results = {"passed": [], "failed": [], "skipped": []}
    for inv in invariants:
        inv_id = inv.get("id") if isinstance(inv, dict) else str(inv)
        if inv_id in INVARIANT_CHECKS:
            status, message, details = INVARIANT_CHECKS[inv_id](before_state, after_state, diff, evals_config)
        else:
            status, message, details = ("skipped", "Invariant not implemented", None)

        record = {
            "id": inv_id,
            "status": status,
            "message": message,
            "details": details,
        }
        results[status].append(record)
    return results


# =============================================================================
# LOGGING
# =============================================================================

def log_eval_run(entry: Dict[str, Any]) -> None:
    """Append an eval_run entry to the session log."""
    proof_dir = get_proof_dir()
    proof_dir.mkdir(parents=True, exist_ok=True)
    log_file = proof_dir / "session_log.jsonl"
    entry = dict(entry)
    entry.setdefault("timestamp", datetime.now().isoformat())
    with open(log_file, "a") as f:
        f.write(json.dumps(entry, ensure_ascii=True, default=str) + "\n")


def load_eval_runs(max_lines: int = 200) -> List[Dict[str, Any]]:
    """Load recent eval_run entries from session_log.jsonl."""
    log_file = get_proof_dir() / "session_log.jsonl"
    if not log_file.exists():
        return []
    try:
        lines = log_file.read_text().splitlines()[-max_lines:]
    except Exception:
        return []
    runs = []
    for line in lines:
        try:
            entry = json.loads(line)
        except Exception:
            continue
        if entry.get("type") == "eval_run":
            runs.append(entry)
    return runs


def has_eval_run_since(timestamp: Optional[str]) -> bool:
    """Check if any eval_run exists since a given ISO timestamp."""
    runs = load_eval_runs(max_lines=500)
    if not runs:
        return False
    if not timestamp:
        return True
    try:
        cutoff = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
    except Exception:
        return True
    for run in runs:
        ts = run.get("timestamp")
        if not ts:
            continue
        try:
            rt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
        except Exception:
            continue
        if rt >= cutoff:
            return True
    return False


# =============================================================================
# AUTO-MISMATCH ON EVAL FAILURE (v3.9.8)
# =============================================================================

def create_mismatch_from_eval(eval_entry: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """
    Create a mismatch dict from an eval_run entry with failed invariants.
    Returns None if no failures.
    """
    failed = eval_entry.get("invariants_failed", [])
    if not failed:
        return None

    tool = eval_entry.get("tool", "unknown")
    diff_path = eval_entry.get("snapshots", {}).get("diff", "unknown")
    diff_summary = eval_entry.get("diff_summary", {})
    timestamp = eval_entry.get("timestamp", datetime.now().isoformat())[:19]

    return {
        "expected": f"All invariants pass during {tool}",
        "actual": f"Invariant(s) failed: {', '.join(failed)}",
        "status": "unresolved",
        "source": "eval_auto",
        "location": diff_path,
        "context": f"+{diff_summary.get('added', 0)} -{diff_summary.get('removed', 0)} ~{diff_summary.get('changed', 0)}",
        "timestamp": timestamp,
    }


def _mismatch_exists(content: str, mismatch: Dict[str, Any]) -> bool:
    """Check if a similar mismatch already exists in the file content."""
    # Simple dedup: check if the actual message already appears
    actual = mismatch.get("actual", "")
    return actual in content


def append_mismatch_to_file(mismatch: Dict[str, Any]) -> Tuple[bool, str]:
    """
    Append a mismatch entry to active_context.yaml.
    Creates mismatches section if it doesn't exist.
    Returns (success, message).
    """
    import re

    yaml_file = get_project_dir() / "active_context.yaml"
    if not yaml_file.exists():
        return (False, "active_context.yaml not found")

    try:
        content = yaml_file.read_text()
    except Exception as exc:
        return (False, f"Could not read file: {exc}")

    # Check for duplicates
    if _mismatch_exists(content, mismatch):
        return (False, "Mismatch already exists (deduped)")

    lines = content.splitlines(keepends=True)

    # Format the mismatch YAML entry
    mismatch_yaml = f'''  - expected: "{mismatch.get('expected', '')}"
    actual: "{mismatch.get('actual', '')}"
    status: "{mismatch.get('status', 'unresolved')}"
    source: "{mismatch.get('source', 'eval_auto')}"
    location: "{mismatch.get('location', '')}"
    timestamp: "{mismatch.get('timestamp', '')}"
'''

    # Look for existing mismatches section
    mismatches_pattern = re.compile(r'^mismatches:\s*$')
    mismatches_idx = None
    for idx, line in enumerate(lines):
        if mismatches_pattern.match(line):
            mismatches_idx = idx
            break

    if mismatches_idx is not None:
        # Find the end of the mismatches section (next top-level key)
        insert_idx = mismatches_idx + 1
        for idx in range(mismatches_idx + 1, len(lines)):
            line = lines[idx]
            # Check if it's a new top-level key (not indented, not a comment, not empty)
            if line and not line.startswith(' ') and not line.startswith('#') and ':' in line:
                insert_idx = idx
                break
            insert_idx = idx + 1

        # Insert the mismatch before the next section
        lines.insert(insert_idx, mismatch_yaml)
    else:
        # Need to create mismatches section - insert after risks:
        risks_pattern = re.compile(r'^risks:\s*$')
        risks_idx = None
        for idx, line in enumerate(lines):
            if risks_pattern.match(line):
                risks_idx = idx
                break

        if risks_idx is not None:
            # Find end of risks section
            insert_idx = risks_idx + 1
            for idx in range(risks_idx + 1, len(lines)):
                line = lines[idx]
                if line and not line.startswith(' ') and not line.startswith('#') and ':' in line:
                    insert_idx = idx
                    break
                insert_idx = idx + 1

            # Insert new mismatches section
            new_section = f"\nmismatches:\n{mismatch_yaml}"
            lines.insert(insert_idx, new_section)
        else:
            # No risks section, append at end
            if not content.endswith('\n'):
                lines.append('\n')
            lines.append(f"\nmismatches:\n{mismatch_yaml}")

    try:
        write_text_atomic(yaml_file, ''.join(lines))
    except Exception as exc:
        return (False, f"Could not write file: {exc}")

    return (True, f"Added mismatch: {mismatch.get('actual', '')[:50]}")


def handle_eval_failure(eval_entry: Dict[str, Any]) -> Tuple[bool, str]:
    """
    Handle an eval failure by creating a mismatch entry.
    Called from post_tool.py after finish_eval_run returns failures.
    """
    mismatch = create_mismatch_from_eval(eval_entry)
    if not mismatch:
        return (False, "No failures in eval entry")

    return append_mismatch_to_file(mismatch)


# =============================================================================
# SNAPSHOT RETENTION (v3.9.8)
# =============================================================================

DEFAULT_RETENTION_DAYS = 7
FAILURE_RETENTION_DAYS = 30


def _run_has_failures(run_dir: Path) -> bool:
    """Check if a run directory contains failure evidence."""
    # Check diff.json for any invariant failures logged
    diff_path = run_dir / "diff.json"
    if not diff_path.exists():
        return False

    # Also check if this run was logged with failures
    # by looking for invariants_failed in the log
    log_file = get_proof_dir() / "session_log.jsonl"
    if not log_file.exists():
        return False

    run_path_str = str(run_dir)
    try:
        for line in log_file.read_text().splitlines():
            try:
                entry = json.loads(line)
            except Exception:
                continue
            if entry.get("type") != "eval_run":
                continue
            snapshots = entry.get("snapshots", {})
            # Check if any snapshot path matches this run dir
            for path in snapshots.values():
                if run_path_str in str(path):
                    if entry.get("invariants_failed"):
                        return True
    except Exception:
        pass

    return False


def _get_run_age_days(run_dir: Path) -> int:
    """Get the age of a run directory in days."""
    try:
        # Parse date from path: .proof/evals/YYYY-MM-DD/run-XX
        date_str = run_dir.parent.name
        run_date = datetime.strptime(date_str, "%Y-%m-%d")
        age = datetime.now() - run_date
        return age.days
    except Exception:
        # If we can't parse, assume it's old
        return 999


def cleanup_orphaned_eval_state(max_age_minutes: int = 60) -> bool:
    """
    Clear stale pending_run from previous crashed sessions.

    A pending_run is created in pre_tool.py before eval execution.
    If post_tool.py never runs (crash, timeout), it lingers forever.
    This function clears pending_runs older than max_age_minutes.

    Args:
        max_age_minutes: Maximum age before considering pending_run stale (default 60)

    Returns:
        True if a stale pending_run was cleared, False otherwise
    """
    eval_state = load_eval_state()
    pending_run = eval_state.get("pending_run")

    if not pending_run:
        return False

    started_at = pending_run.get("started_at")
    if not started_at:
        # No timestamp - consider it stale
        eval_state["pending_run"] = None
        save_eval_state(eval_state)
        return True

    try:
        started = datetime.fromisoformat(started_at)
        age_minutes = (datetime.now() - started).total_seconds() / 60

        if age_minutes > max_age_minutes:
            # Stale - clear it and log
            eval_state["pending_run"] = None
            save_eval_state(eval_state)

            # Try to log to proof (optional - don't fail if proof logging unavailable)
            try:
                from proof_utils import log_to_session
                log_to_session({
                    "type": "cleanup_orphaned_eval",
                    "stale_run": pending_run,
                    "age_minutes": round(age_minutes, 2),
                    "message": "Cleared orphaned eval run from previous session",
                    "timestamp": datetime.now().isoformat(),
                })
            except Exception:
                pass  # Proof logging is optional

            return True
    except (ValueError, TypeError):
        # Can't parse timestamp - clear it
        eval_state["pending_run"] = None
        save_eval_state(eval_state)
        return True

    return False


def cleanup_old_snapshots(
    retention_days: int = DEFAULT_RETENTION_DAYS,
    failure_retention_days: int = FAILURE_RETENTION_DAYS,
    dry_run: bool = False
) -> Dict[str, Any]:
    """
    Clean up old eval snapshots.

    - Normal runs: delete after retention_days (default 7)
    - Failed runs: keep for failure_retention_days (default 30)

    Args:
        retention_days: Days to keep successful runs
        failure_retention_days: Days to keep failed runs
        dry_run: If True, don't actually delete, just report

    Returns:
        Summary with counts of deleted, kept, failures preserved
    """
    import shutil

    evals_dir = get_eval_base_dir()
    if not evals_dir.exists():
        return {"deleted": 0, "kept": 0, "failures_preserved": 0, "errors": []}

    deleted = 0
    kept = 0
    failures_preserved = 0
    errors = []

    # Iterate through date directories
    for date_dir in sorted(evals_dir.glob("*")):
        if not date_dir.is_dir():
            continue

        # Check if entire date directory is old enough
        try:
            date_str = date_dir.name
            dir_date = datetime.strptime(date_str, "%Y-%m-%d")
            age_days = (datetime.now() - dir_date).days
        except Exception:
            continue

        # Iterate through run directories
        for run_dir in sorted(date_dir.glob("run-*")):
            if not run_dir.is_dir():
                continue

            has_failures = _run_has_failures(run_dir)
            threshold = failure_retention_days if has_failures else retention_days

            if age_days > threshold:
                # Should delete
                if dry_run:
                    deleted += 1
                else:
                    try:
                        shutil.rmtree(run_dir)
                        deleted += 1
                    except Exception as exc:
                        errors.append(f"Failed to delete {run_dir}: {exc}")
            else:
                # Keep
                if has_failures:
                    failures_preserved += 1
                kept += 1

        # Clean up empty date directories
        if not dry_run and date_dir.exists():
            remaining = list(date_dir.glob("run-*"))
            if not remaining:
                try:
                    date_dir.rmdir()
                except Exception:
                    pass

    return {
        "deleted": deleted,
        "kept": kept,
        "failures_preserved": failures_preserved,
        "errors": errors,
        "dry_run": dry_run,
    }


def get_snapshot_stats() -> Dict[str, Any]:
    """Get statistics about current snapshot storage."""
    evals_dir = get_eval_base_dir()
    if not evals_dir.exists():
        return {"total_runs": 0, "total_size_bytes": 0, "oldest_date": None, "newest_date": None}

    total_runs = 0
    total_size = 0
    dates = []

    for date_dir in evals_dir.glob("*"):
        if not date_dir.is_dir():
            continue
        dates.append(date_dir.name)

        for run_dir in date_dir.glob("run-*"):
            if not run_dir.is_dir():
                continue
            total_runs += 1
            for f in run_dir.glob("*.json"):
                try:
                    total_size += f.stat().st_size
                except Exception:
                    pass

    return {
        "total_runs": total_runs,
        "total_size_bytes": total_size,
        "oldest_date": min(dates) if dates else None,
        "newest_date": max(dates) if dates else None,
    }
