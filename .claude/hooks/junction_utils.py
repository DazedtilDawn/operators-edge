#!/usr/bin/env python3
"""
Operator's Edge - Junction Utilities
Single-source junction state management for human-in-the-loop gating.
"""
import json
import hashlib
from datetime import datetime, timedelta
from pathlib import Path
from uuid import uuid4
from typing import Optional, Dict, Any

from state_utils import get_state_dir, write_json_atomic

JUNCTION_SCHEMA_VERSION = 1
JUNCTION_STATE_FILE = "junction_state.json"
LEGACY_DISPATCH_FILE = "dispatch_state.json"


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


def load_junction_state() -> dict:
    """Load junction state from file (with legacy migration fallback)."""
    state_path = _state_path()
    state = None
    if state_path.exists():
        try:
            state = json.loads(state_path.read_text())
        except (json.JSONDecodeError, IOError):
            state = None

    if state is None:
        state = _default_state()

    state = _ensure_shape(state)

    # Migrate legacy pending if no pending exists
    if not state.get("pending"):
        legacy = _load_legacy_pending()
        if legacy:
            pending = _build_pending(legacy["type"], {"reason": legacy.get("reason")}, source="legacy")
            state["pending"] = pending
            save_junction_state(state)

    return state


def save_junction_state(state: dict) -> None:
    """Persist junction state to disk."""
    state = _ensure_shape(state)
    state_dir = get_state_dir()
    state_dir.mkdir(parents=True, exist_ok=True)
    state_path = _state_path()
    write_json_atomic(state_path, state, indent=2)


def _build_pending(junction_type: str, payload: Optional[Dict[str, Any]], source: str) -> dict:
    return {
        "id": str(uuid4()),
        "type": junction_type,
        "payload": payload or {},
        "created_at": datetime.now().isoformat(),
        "source": source,
    }


def set_pending_junction(junction_type: str, payload: Optional[Dict[str, Any]] = None, source: str = "edge") -> dict:
    """Set a new pending junction (overwrites any existing pending)."""
    state = load_junction_state()
    pending = _build_pending(junction_type, payload, source)
    state["pending"] = pending
    save_junction_state(state)
    return pending


def _fingerprint_pending(pending: dict) -> str:
    payload = pending.get("payload") or {}
    base = {
        "type": pending.get("type"),
        "payload": payload,
    }
    encoded = json.dumps(base, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def clear_pending_junction(decision: str, suppress_minutes: Optional[int] = None) -> Optional[dict]:
    """Clear the pending junction and record history.

    Returns the cleared pending junction (if any).
    """
    state = load_junction_state()
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
        save_junction_state(state)

    # Best-effort clear legacy flags if present
    _clear_legacy_dispatch()

    return pending


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


def get_pending_junction() -> Optional[dict]:
    """Return pending junction if present."""
    state = load_junction_state()
    return state.get("pending")
