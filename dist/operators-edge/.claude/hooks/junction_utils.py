#!/usr/bin/env python3
"""
Operator's Edge - Junction Utilities
Single-source junction state management for human-in-the-loop gating.

v5 Schema: Junction state now lives in active_context.yaml under runtime.junction
Legacy JSON files are read for migration but new writes go to YAML.
"""
import json
import hashlib
import os
from datetime import datetime, timedelta
from pathlib import Path
from uuid import uuid4
from typing import Optional, Dict, Any, Tuple

from state_utils import (
    get_state_dir, write_json_atomic, load_yaml_state,
    get_runtime_section, update_runtime_section
)

JUNCTION_SCHEMA_VERSION = 2  # v2 = YAML runtime section
JUNCTION_STATE_FILE = "junction_state.json"  # Legacy, for migration
LEGACY_DISPATCH_FILE = "dispatch_state.json"

# Feature flag: set to True to use YAML runtime section (v5 schema)
USE_YAML_RUNTIME = True


def is_readonly() -> bool:
    """
    Check if the system is in read-only mode.

    Read-only mode is enabled when:
    1. EDGE_READONLY=1 environment variable is set (manual override)
    2. Claude is in plan mode (automatic detection via flag file)

    In this mode, no state mutations occur - useful for Plan mode
    where Claude explores but doesn't execute.
    """
    # Manual override via environment variable
    if os.environ.get("EDGE_READONLY", "").lower() in ("1", "true", "yes"):
        return True

    # Automatic detection: check if plan mode flag exists
    try:
        from plan_mode import is_plan_mode
        if is_plan_mode():
            return True
    except ImportError:
        pass

    return False


def _default_state() -> dict:
    return {
        "schema_version": JUNCTION_SCHEMA_VERSION,
        "pending": None,
        "history_tail": [],
        "suppression": [],
    }


def _state_path() -> Path:
    return get_state_dir() / JUNCTION_STATE_FILE


def _legacy_dispatch_path() -> Path:
    return get_state_dir() / LEGACY_DISPATCH_FILE


def _ensure_shape(state: dict) -> dict:
    if not isinstance(state, dict):
        state = {}
    state.setdefault("schema_version", JUNCTION_SCHEMA_VERSION)
    state.setdefault("pending", None)
    state.setdefault("history_tail", [])
    state.setdefault("suppression", [])
    return state


def _load_legacy_pending() -> Optional[dict]:
    """Load legacy pending junction from dispatch_state.json if present."""
    legacy_path = _legacy_dispatch_path()
    if not legacy_path.exists():
        return None
    try:
        legacy = json.loads(legacy_path.read_text())
    except (json.JSONDecodeError, IOError):
        return None

    if legacy.get("pending_junction"):
        return {
            "type": legacy.get("junction_type", "unknown"),
            "reason": legacy.get("junction_reason"),
        }

    junction = legacy.get("junction")
    if isinstance(junction, dict) and junction.get("type"):
        return {
            "type": junction.get("type"),
            "reason": junction.get("reason"),
        }

    return None


def _load_from_yaml_runtime() -> Optional[dict]:
    """Load junction state from YAML runtime section (v5 schema)."""
    if not USE_YAML_RUNTIME:
        return None

    yaml_state = load_yaml_state()
    if not yaml_state:
        return None

    junction = get_runtime_section(yaml_state, "junction")
    if not junction:
        return None

    # Convert YAML format to internal format
    return {
        "schema_version": JUNCTION_SCHEMA_VERSION,
        "pending": junction.get("pending"),
        "history_tail": junction.get("history_tail", []),
        "suppression": junction.get("suppressions", []),  # Note: YAML uses 'suppressions'
    }


def _load_from_json_file() -> Optional[dict]:
    """Load junction state from legacy JSON file."""
    state_path = _state_path()
    if not state_path.exists():
        return None
    try:
        return json.loads(state_path.read_text())
    except (json.JSONDecodeError, IOError):
        return None


def load_junction_state(readonly: Optional[bool] = None) -> Tuple[dict, Optional[str]]:
    """
    Load junction state (YAML runtime section preferred, JSON fallback).

    v5 Schema: First tries runtime.junction in active_context.yaml,
    then falls back to junction_state.json for migration.

    Args:
        readonly: If True, skip migration writes. If None, uses is_readonly().

    Returns:
        Tuple of (state_dict, warning_message_or_none)
    """
    if readonly is None:
        readonly = is_readonly()

    state = None
    warning = None
    migrated_from = None

    # v5: Try YAML runtime section first
    state = _load_from_yaml_runtime()
    if state:
        return _ensure_shape(state), None

    # Fallback: Load from JSON file
    state = _load_from_json_file()
    if state:
        migrated_from = "json"

    if state is None:
        state = _default_state()

    state = _ensure_shape(state)

    # Migrate legacy pending from dispatch_state.json if no pending exists
    if not state.get("pending"):
        legacy = _load_legacy_pending()
        if legacy:
            pending = _build_pending(legacy["type"], {"reason": legacy.get("reason")}, source="legacy")
            state["pending"] = pending
            migrated_from = "legacy_dispatch"

    # If we loaded from JSON or legacy, migrate to YAML
    if migrated_from and USE_YAML_RUNTIME:
        if readonly:
            warning = f"Read-only mode: junction state from {migrated_from} not migrated to YAML"
        else:
            save_junction_state(state, readonly=False)

    return state, warning


def _save_to_yaml_runtime(state: dict) -> bool:
    """Save junction state to YAML runtime section (v5 schema)."""
    if not USE_YAML_RUNTIME:
        return False

    # Check if YAML state exists with runtime section before attempting write
    yaml_state = load_yaml_state()
    if not yaml_state or "runtime" not in yaml_state:
        return False  # No YAML runtime section, fall back to JSON

    # Convert internal format to YAML format
    yaml_data = {
        "pending": state.get("pending"),
        "suppressions": state.get("suppression", []),  # YAML uses 'suppressions'
        "history_tail": state.get("history_tail", []),
    }

    return update_runtime_section("junction", yaml_data)


def _save_to_json_file(state: dict) -> None:
    """Save junction state to legacy JSON file (fallback)."""
    state_dir = get_state_dir()
    state_dir.mkdir(parents=True, exist_ok=True)
    state_path = _state_path()
    write_json_atomic(state_path, state, indent=2)


def save_junction_state(state: dict, readonly: Optional[bool] = None) -> Optional[str]:
    """
    Persist junction state to disk.

    v5 Schema: Writes to runtime.junction in active_context.yaml.
    Falls back to JSON if YAML write fails.

    Args:
        state: Junction state dict to save
        readonly: If True, skip write. If None, uses is_readonly().

    Returns:
        Warning message if in readonly mode or on fallback, None otherwise.
    """
    if readonly is None:
        readonly = is_readonly()

    if readonly:
        return "Read-only mode: junction state not saved"

    state = _ensure_shape(state)

    # v5: Try YAML runtime section first (if available)
    if USE_YAML_RUNTIME and _save_to_yaml_runtime(state):
        return None

    # Fall back to JSON (either YAML not available or write failed)
    _save_to_json_file(state)
    return None


def _build_pending(junction_type: str, payload: Optional[Dict[str, Any]], source: str) -> dict:
    return {
        "id": str(uuid4()),
        "type": junction_type,
        "payload": payload or {},
        "created_at": datetime.now().isoformat(),
        "source": source,
    }


def set_pending_junction(
    junction_type: str,
    payload: Optional[Dict[str, Any]] = None,
    source: str = "edge",
    readonly: Optional[bool] = None
) -> Tuple[dict, Optional[str]]:
    """
    Set a new pending junction (overwrites any existing pending).

    Args:
        junction_type: Type of junction (e.g., "finding_selection", "irreversible")
        payload: Additional data for the junction
        source: Source of the junction (e.g., "edge", "patrol")
        readonly: If True, build pending but don't save. If None, uses is_readonly().

    Returns:
        Tuple of (pending_dict, warning_message_or_none)
    """
    if readonly is None:
        readonly = is_readonly()

    state, _ = load_junction_state(readonly=readonly)
    pending = _build_pending(junction_type, payload, source)
    state["pending"] = pending

    if readonly:
        return pending, "Read-only mode: junction set in memory but not persisted"

    save_junction_state(state, readonly=False)
    return pending, None


def _fingerprint_pending(pending: dict) -> str:
    payload = pending.get("payload") or {}
    base = {
        "type": pending.get("type"),
        "payload": payload,
    }
    encoded = json.dumps(base, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def clear_pending_junction(
    decision: str,
    suppress_minutes: Optional[int] = None,
    readonly: Optional[bool] = None
) -> Tuple[Optional[dict], Optional[str]]:
    """
    Clear the pending junction and record history.

    Args:
        decision: The decision made ("approve", "skip", "dismiss")
        suppress_minutes: For dismiss, how long to suppress this junction type
        readonly: If True, don't persist changes. If None, uses is_readonly().

    Returns:
        Tuple of (cleared_pending_or_none, warning_message_or_none)
    """
    if readonly is None:
        readonly = is_readonly()

    state, _ = load_junction_state(readonly=readonly)
    pending = state.get("pending")

    if pending:
        state["history_tail"].append({
            "id": pending.get("id"),
            "type": pending.get("type"),
            "decision": decision,
            "decided_at": datetime.now().isoformat(),
        })
        # Keep last 10 decisions
        if len(state["history_tail"]) > 10:
            state["history_tail"] = state["history_tail"][-10:]

        if decision == "dismiss":
            ttl = suppress_minutes if suppress_minutes is not None else 60
            state["suppression"].append({
                "fingerprint": _fingerprint_pending(pending),
                "expires_at": (datetime.now() + timedelta(minutes=ttl)).isoformat(),
            })

        state["pending"] = None

        if readonly:
            return pending, "Read-only mode: junction cleared in memory but not persisted"

        save_junction_state(state, readonly=False)

    # Best-effort clear legacy flags if present (skip in readonly mode)
    if not readonly:
        _clear_legacy_dispatch()

    return pending, None


def _clear_legacy_dispatch() -> None:
    legacy_path = _legacy_dispatch_path()
    if not legacy_path.exists():
        return
    try:
        legacy = json.loads(legacy_path.read_text())
    except (json.JSONDecodeError, IOError):
        return

    updated = False
    if legacy.get("pending_junction"):
        legacy["pending_junction"] = None
        legacy["junction_type"] = None
        legacy["junction_reason"] = None
        updated = True

    if legacy.get("junction"):
        legacy["junction"] = None
        updated = True

    if updated:
        write_json_atomic(legacy_path, legacy, indent=2)


def get_pending_junction(readonly: Optional[bool] = None) -> Optional[dict]:
    """
    Return pending junction if present.

    Args:
        readonly: If True, don't trigger legacy migration. If None, uses is_readonly().

    Returns:
        Pending junction dict or None
    """
    # Reading is always safe, but we pass readonly to avoid migration writes
    if readonly is None:
        readonly = True  # Default to readonly for get operations
    state, _ = load_junction_state(readonly=readonly)
    return state.get("pending")
