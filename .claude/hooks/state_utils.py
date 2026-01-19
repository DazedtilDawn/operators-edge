#!/usr/bin/env python3
"""
Operator's Edge - State Utilities
Core state management: paths, YAML parsing, hashing, logging.

NOTE: This module is platform-agnostic. It auto-detects:
  - Claude Code (CLAUDE_PROJECT_DIR)
  - Codex CLI (CODEX_PROJECT_DIR)
  - Generic (current working directory)
"""
import hashlib
import re
import json
import os
import sys
import time
from contextlib import contextmanager
from datetime import datetime
from enum import Enum
from pathlib import Path


# =============================================================================
# MODE ENUM (Protocol v4.0)
# =============================================================================

class Mode(Enum):
    """
    Operator mode - the workflow phase.

    PLAN: Exploration, research, thinking (default on session start)
    ACTIVE: Executing work toward objective
    REVIEW: Verification, testing, reflection
    DONE: Clean completion and archival
    """
    PLAN = "plan"
    ACTIVE = "active"
    REVIEW = "review"
    DONE = "done"


def detect_mode(state: dict = None) -> Mode:
    """
    Detect the current mode from state.

    Priority:
    1. Explicit 'mode' field in state
    2. Inferred from state:
       - No objective → PLAN
       - Has objective + incomplete steps → ACTIVE
       - Has objective + all steps complete → REVIEW
       - Explicit mode=done → DONE

    Args:
        state: The active_context state dict. If None, loads from file.

    Returns:
        Mode enum value
    """
    if state is None:
        state = load_yaml_state() or {}

    # Check explicit mode field
    mode_str = state.get("mode")
    if mode_str:
        try:
            return Mode(mode_str.lower())
        except ValueError:
            pass  # Invalid mode string, fall through to inference

    # Infer from state
    objective = state.get("objective")
    plan = state.get("plan", [])

    # No objective → PLAN mode (exploring)
    if not objective:
        return Mode.PLAN

    # Has objective, check plan status
    if not plan:
        # Has objective but no plan → ACTIVE (needs planning)
        return Mode.ACTIVE

    # Count step statuses
    completed = sum(1 for s in plan if isinstance(s, dict) and s.get("status") == "completed")
    in_progress = sum(1 for s in plan if isinstance(s, dict) and s.get("status") == "in_progress")
    pending = sum(1 for s in plan if isinstance(s, dict) and s.get("status") == "pending")

    # All steps complete → REVIEW mode
    if completed > 0 and in_progress == 0 and pending == 0:
        return Mode.REVIEW

    # Work in progress → ACTIVE mode
    return Mode.ACTIVE


def suggest_mode_transition(state: dict = None) -> tuple[Mode, Mode, str] | None:
    """
    Suggest a mode transition based on current state.

    Returns:
        Tuple of (current_mode, suggested_mode, reason) if transition suggested,
        None if no transition appropriate.

    Transition rules:
    - PLAN → ACTIVE: When objective exists and plan has pending steps
    - ACTIVE → REVIEW: When all steps are completed
    - REVIEW → DONE: Only on explicit user action (no auto-suggest)
    - DONE → PLAN: When state is cleared (no auto-suggest)
    """
    if state is None:
        state = load_yaml_state() or {}

    current_mode = detect_mode(state)
    objective = state.get("objective")
    plan = state.get("plan", [])

    # Count step statuses
    completed = sum(1 for s in plan if isinstance(s, dict) and s.get("status") == "completed")
    in_progress = sum(1 for s in plan if isinstance(s, dict) and s.get("status") == "in_progress")
    pending = sum(1 for s in plan if isinstance(s, dict) and s.get("status") == "pending")

    # PLAN → ACTIVE: Has objective and plan with pending steps
    if current_mode == Mode.PLAN:
        if objective and plan and pending > 0:
            return (Mode.PLAN, Mode.ACTIVE, f"Plan ready with {pending} pending steps")

    # ACTIVE → REVIEW: All steps completed
    elif current_mode == Mode.ACTIVE:
        if plan and completed > 0 and in_progress == 0 and pending == 0:
            return (Mode.ACTIVE, Mode.REVIEW, f"All {completed} steps completed - ready for review")

    # No transition suggested
    return None


def set_mode(mode: Mode, state: dict = None) -> dict:
    """
    Set the mode in state.

    Args:
        mode: The Mode to set
        state: State dict to modify. If None, loads and saves to file.

    Returns:
        Updated state dict
    """
    if state is None:
        state = load_yaml_state() or {}

    state["mode"] = mode.value

    # Persist to file using text manipulation (preserves YAML structure)
    state_file = get_project_dir() / "active_context.yaml"
    if state_file.exists():
        content = state_file.read_text()
        lines = content.split('\n')
        new_lines = []
        mode_found = False

        for line in lines:
            if line.startswith('mode:'):
                new_lines.append(f'mode: "{mode.value}"')
                mode_found = True
            else:
                new_lines.append(line)

        # If mode field doesn't exist, add it after session block
        if not mode_found:
            insert_lines = []
            inserted = False
            for i, line in enumerate(new_lines):
                insert_lines.append(line)
                # Insert after session block (after first blank line following session)
                if not inserted and line.strip() == '' and i > 0:
                    prev_line = new_lines[i-1].strip() if i > 0 else ''
                    if prev_line.startswith('state_hash') or prev_line.startswith('note:'):
                        insert_lines.append(f'mode: "{mode.value}"')
                        inserted = True
            if not inserted:
                # Fallback: add at beginning after comments
                for i, line in enumerate(insert_lines):
                    if line.strip() and not line.strip().startswith('#'):
                        insert_lines.insert(i, f'mode: "{mode.value}"')
                        break
            new_lines = insert_lines

        state_file.write_text('\n'.join(new_lines))

    return state


# =============================================================================
# PATH UTILITIES (Platform-Agnostic)
# =============================================================================

def get_project_dir():
    """
    Get the project directory, auto-detecting platform.

    Priority:
        1. CLAUDE_PROJECT_DIR (Claude Code)
        2. CODEX_PROJECT_DIR (Codex CLI)
        3. Current working directory (fallback)
    """
    # Claude Code sets this
    claude_dir = os.environ.get("CLAUDE_PROJECT_DIR")
    if claude_dir:
        return Path(claude_dir)

    # Codex CLI may set this
    codex_dir = os.environ.get("CODEX_PROJECT_DIR")
    if codex_dir:
        return Path(codex_dir)

    # Fallback to current directory
    return Path(os.getcwd())


def get_state_dir():
    """Get the .claude/state directory (used by both platforms for compatibility)."""
    return get_project_dir() / ".claude" / "state"


def get_proof_dir():
    """Get the .proof directory."""
    return get_project_dir() / ".proof"


def get_archive_file():
    """Get the archive file path."""
    return get_proof_dir() / "archive.jsonl"


# =============================================================================
# FILE LOCKING + ATOMIC WRITES
# =============================================================================

DEFAULT_LOCK_TIMEOUT = 5.0
DEFAULT_LOCK_POLL = 0.1


def _lock_path_for(target_path: Path) -> Path:
    """Create a lock path alongside the target file."""
    target = Path(target_path)
    return target.with_suffix(target.suffix + ".lock")


def _read_lock_info(lock_path: Path) -> dict:
    """Read lock metadata from file."""
    try:
        raw = lock_path.read_text().strip()
    except Exception:
        return {}
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return {}


def _pid_alive(pid: int) -> bool:
    """Best-effort check for a live PID (cross-platform)."""
    if pid is None:
        return False
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


@contextmanager
def file_lock(target_path: Path, timeout_seconds: float = DEFAULT_LOCK_TIMEOUT,
              poll_interval: float = DEFAULT_LOCK_POLL):
    """Acquire a simple lock file to serialize writes."""
    lock_path = _lock_path_for(target_path)
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    start = time.time()
    fd = None
    host_name = "unknown"
    try:
        if hasattr(os, "uname"):
            host_name = os.uname().nodename
    except Exception:
        host_name = "unknown"

    lock_info = {
        "pid": os.getpid(),
        "created_at": datetime.now().isoformat(),
        "host": host_name,
    }

    while True:
        try:
            fd = os.open(str(lock_path), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            os.write(fd, json.dumps(lock_info).encode("utf-8"))
            break
        except FileExistsError:
            # Attempt stale lock recovery
            info = _read_lock_info(lock_path)
            age_ok = False
            try:
                created = info.get("created_at")
                if created:
                    created_ts = datetime.fromisoformat(created).timestamp()
                    age_ok = (time.time() - created_ts) > timeout_seconds
                else:
                    # Legacy/unknown lock format - allow stale recovery
                    age_ok = True
            except Exception:
                age_ok = True

            pid = info.get("pid")
            if age_ok and not _pid_alive(pid):
                try:
                    lock_path.unlink()
                    continue
                except FileNotFoundError:
                    continue
                except Exception:
                    pass

            if time.time() - start >= timeout_seconds:
                raise TimeoutError(f"Timeout acquiring lock for {target_path}")
            time.sleep(poll_interval)
        except OSError:
            # Unexpected OS error - surface as a timeout-style failure
            raise TimeoutError(f"Failed acquiring lock for {target_path}")

    try:
        yield
    finally:
        try:
            if fd is not None:
                os.close(fd)
        finally:
            try:
                lock_path.unlink()
            except FileNotFoundError:
                pass


def atomic_write_text(path: Path, content: str) -> None:
    """Write a file atomically by writing to a temp file and renaming."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_suffix(f"{path.suffix}.tmp-{os.getpid()}-{int(time.time() * 1000)}")
    with open(tmp_path, "w", encoding="utf-8") as f:
        f.write(content)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp_path, path)


def atomic_write_json(path: Path, data: dict, indent: int = 2) -> None:
    """Serialize JSON and write atomically."""
    payload = json.dumps(data, indent=indent)
    atomic_write_text(path, payload)


def write_text_atomic(path: Path, content: str,
                      timeout_seconds: float = DEFAULT_LOCK_TIMEOUT) -> None:
    """Lock + atomic write for text files."""
    with file_lock(path, timeout_seconds=timeout_seconds):
        atomic_write_text(path, content)


def write_json_atomic(path: Path, data: dict, indent: int = 2,
                      timeout_seconds: float = DEFAULT_LOCK_TIMEOUT) -> None:
    """Lock + atomic write for JSON files."""
    with file_lock(path, timeout_seconds=timeout_seconds):
        atomic_write_json(path, data, indent=indent)


# =============================================================================
# YAML PARSING (No external dependencies)
# =============================================================================

def parse_yaml_value(value):
    """Parse a YAML value string into Python type."""
    value = value.strip()

    # Handle quoted strings first - extract just the quoted portion
    if value.startswith('"'):
        # Find matching end quote
        end_idx = value.find('"', 1)
        if end_idx > 0:
            return value[1:end_idx]
    if value.startswith("'"):
        # Find matching end quote
        end_idx = value.find("'", 1)
        if end_idx > 0:
            return value[1:end_idx]

    # Strip inline comments from unquoted values
    comment_idx = value.find('  #')
    if comment_idx > 0:
        value = value[:comment_idx].strip()

    if not value or value == 'null':
        return None
    if value == '[]':
        return []
    if value == '{}':
        return {}
    if value == 'true':
        return True
    if value == 'false':
        return False
    # Try number
    try:
        if '.' in value:
            return float(value)
        return int(value)
    except ValueError:
        pass
    return value


def parse_simple_yaml(content):
    """
    Enhanced YAML parser for Operator's Edge v2 schema.
    Handles: scalars, lists, nested dicts, list items with properties.
    Not a full YAML parser - but handles our active_context.yaml structure.
    """
    lines = content.split('\n')
    return parse_yaml_block(lines, 0, 0)[0]


def _parse_nested_list_items(lines, start_idx, base_indent):
    """Parse nested list items (values under a property with no inline value)."""
    nested_list = []
    i = start_idx

    while i < len(lines):
        line = lines[i]
        stripped = line.strip()

        if not stripped or stripped.startswith('#'):
            i += 1
            continue

        indent = len(line) - len(line.lstrip())
        if indent <= base_indent:
            break

        if stripped.startswith('- '):
            item = stripped[2:].strip()
            if item.startswith('"') and item.endswith('"'):
                item = item[1:-1]
            nested_list.append(item)
        i += 1

    return nested_list if nested_list else None, i


def _parse_dict_list_item_properties(lines, start_idx, item_indent, item_dict):
    """Parse additional properties of a list item dict."""
    i = start_idx

    while i < len(lines):
        line = lines[i]
        stripped = line.strip()

        if not stripped or stripped.startswith('#'):
            i += 1
            continue

        indent = len(line) - len(line.lstrip())
        if indent <= item_indent:
            break

        if ':' in stripped and not stripped.startswith('- '):
            key, _, value = stripped.partition(':')
            key = key.strip()
            value = value.strip()

            if value:
                item_dict[key] = parse_yaml_value(value)
            else:
                # Parse nested list
                nested_list, i = _parse_nested_list_items(lines, i + 1, indent)
                item_dict[key] = nested_list
                continue
        i += 1

    return item_dict, i


def _parse_dict_list_item(lines, idx, indent, item_content):
    """Parse a list item that contains a dict (- key: value ...)."""
    item_dict = {}
    key, _, value = item_content.partition(':')
    key = key.strip()
    value = value.strip()

    item_dict[key] = parse_yaml_value(value) if value else None

    # Parse additional properties
    return _parse_dict_list_item_properties(lines, idx + 1, indent, item_dict)


def _parse_simple_list_item(item_content):
    """Parse a simple list item (- value)."""
    if item_content.startswith('"') and item_content.endswith('"'):
        item_content = item_content[1:-1]
    return item_content


def _check_for_nested_dict(lines, i, indent):
    """Check if next non-empty, non-comment line starts a nested dict."""
    # Skip comments and empty lines to find actual next content
    j = i + 1
    while j < len(lines):
        next_line = lines[j]
        next_stripped = next_line.strip()

        # Skip empty lines and comments
        if not next_stripped or next_stripped.startswith('#'):
            j += 1
            continue

        next_indent = len(next_line) - len(next_line.lstrip())

        if not next_stripped.startswith('- '):
            if ':' in next_stripped and next_indent > indent:
                return True, next_indent
        return False, 0

    return False, 0


def parse_yaml_block(lines, start_idx, base_indent):
    """
    Recursively parse a YAML block starting at given index and indentation.
    Returns (parsed_dict, next_line_index).
    """
    result = {}
    i = start_idx
    current_key = None
    current_list = None

    while i < len(lines):
        line = lines[i]
        stripped = line.strip()

        # Skip comments and empty lines
        if not stripped or stripped.startswith('#'):
            i += 1
            continue

        indent = len(line) - len(line.lstrip())

        # Dedented past base - done with this block
        if indent < base_indent and stripped:
            break

        # List item
        if stripped.startswith('- '):
            if current_key is None:
                i += 1
                continue

            if current_list is None:
                current_list = []

            item_content = stripped[2:].strip()

            if ':' in item_content:
                # Dict list item
                item_dict, i = _parse_dict_list_item(lines, i, indent, item_content)
                current_list.append(item_dict)
            else:
                # Simple list item
                current_list.append(_parse_simple_list_item(item_content))
                i += 1
            continue

        # Key: value pair
        if ':' in stripped:
            # Save previous list
            if current_key and current_list is not None:
                result[current_key] = current_list
                current_list = None

            key, _, value = stripped.partition(':')
            key = key.strip()
            value = value.strip()

            if value:
                result[key] = parse_yaml_value(value)
                current_key = None
            else:
                current_key = key
                current_list = None

                # Check for nested dict
                is_nested, next_indent = _check_for_nested_dict(lines, i, indent)
                if is_nested:
                    nested_dict, i = parse_nested_dict(lines, i + 1, next_indent)
                    result[key] = nested_dict
                    current_key = None
                    continue

            i += 1
            continue

        i += 1

    # Save final list
    if current_key and current_list is not None:
        result[current_key] = current_list

    return result, i


def parse_nested_dict(lines, start_idx, base_indent):
    """Parse a nested dictionary block with recursive nesting support."""
    result = {}
    i = start_idx
    current_key = None
    current_list = None

    while i < len(lines):
        line = lines[i]
        stripped = line.strip()

        if not stripped or stripped.startswith('#'):
            i += 1
            continue

        indent = len(line) - len(line.lstrip())

        # If dedented past base, we're done
        if indent < base_indent:
            break

        # List item handling
        if stripped.startswith('- '):
            if current_key is not None:
                if current_list is None:
                    current_list = []
                item_content = stripped[2:].strip()
                if ':' in item_content:
                    # Dict list item
                    item_dict, i = _parse_dict_list_item(lines, i, indent, item_content)
                    current_list.append(item_dict)
                else:
                    # Simple list item
                    current_list.append(_parse_simple_list_item(item_content))
                    i += 1
                continue
            i += 1
            continue

        if ':' in stripped:
            # Save previous list if any
            if current_key and current_list is not None:
                result[current_key] = current_list
                current_list = None

            key, _, value = stripped.partition(':')
            key = key.strip()
            value = value.strip()

            if value:
                result[key] = parse_yaml_value(value)
                current_key = None
            else:
                current_key = key
                current_list = None

                # Check for nested dict (recursive)
                is_nested, next_indent = _check_for_nested_dict(lines, i, indent)
                if is_nested:
                    nested_dict, i = parse_nested_dict(lines, i + 1, next_indent)
                    result[key] = nested_dict
                    current_key = None
                    continue

        i += 1

    # Save final list
    if current_key and current_list is not None:
        result[current_key] = current_list

    return result, i


# =============================================================================
# STATE LOADING
# =============================================================================

def load_yaml_state():
    """Load active_context.yaml, return dict or None if missing/invalid."""
    state_file = get_project_dir() / "active_context.yaml"
    if not state_file.exists():
        return None
    try:
        content = state_file.read_text()
        return parse_simple_yaml(content)
    except Exception:
        return None


# =============================================================================
# RUNTIME STATE (v5 schema - consolidated junction/gear/dispatch)
# =============================================================================

def get_runtime_section(state: dict = None, key: str = None) -> dict:
    """
    Get a runtime subsection from state.

    Args:
        state: The full state dict. If None, loads from file.
        key: The runtime subsection key (junction, gear, dispatch).
             If None, returns the entire runtime section.

    Returns:
        The requested section dict, or empty dict if not found.
    """
    if state is None:
        state = load_yaml_state() or {}

    runtime = state.get("runtime", {})

    if key is None:
        return runtime

    return runtime.get(key, {})


def _serialize_runtime_value(value, indent_level: int = 0) -> str:
    """Serialize a Python value to YAML format."""
    indent = "  " * indent_level

    if value is None:
        return "null"
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        return str(value)
    if isinstance(value, str):
        # Quote strings that might be ambiguous
        if value in ("null", "true", "false") or value.isdigit():
            return f'"{value}"'
        if any(c in value for c in ":#{}[]&*!|>'\"%@`"):
            return f'"{value}"'
        return f'"{value}"'
    if isinstance(value, list):
        if not value:
            return "[]"
        lines = []
        for item in value:
            if isinstance(item, dict):
                # Dict item in list
                first = True
                for k, v in item.items():
                    prefix = "- " if first else "  "
                    lines.append(f"{indent}{prefix}{k}: {_serialize_runtime_value(v)}")
                    first = False
            else:
                lines.append(f"{indent}- {_serialize_runtime_value(item)}")
        return "\n" + "\n".join(lines)
    if isinstance(value, dict):
        if not value:
            return "{}"
        lines = []
        for k, v in value.items():
            serialized = _serialize_runtime_value(v, indent_level + 1)
            if isinstance(v, (list, dict)) and v and "\n" in serialized:
                lines.append(f"{indent}  {k}:{serialized}")
            else:
                lines.append(f"{indent}  {k}: {serialized}")
        return "\n" + "\n".join(lines)

    return str(value)


def update_runtime_section(key: str, data: dict,
                           timeout_seconds: float = DEFAULT_LOCK_TIMEOUT) -> bool:
    """
    Update a runtime subsection in active_context.yaml atomically.

    Args:
        key: The runtime subsection key (junction, gear, dispatch)
        data: The new data for that subsection
        timeout_seconds: Lock timeout

    Returns:
        True on success, False on failure
    """
    yaml_file = get_project_dir() / "active_context.yaml"

    with file_lock(yaml_file, timeout_seconds=timeout_seconds):
        try:
            content = yaml_file.read_text()
            lines = content.split('\n')
        except Exception:
            return False

        # Find the runtime section and the specific key
        runtime_line_idx = None
        key_line_idx = None
        key_end_idx = None
        key_indent = None

        for i, line in enumerate(lines):
            stripped = line.strip()
            if stripped == "runtime:":
                runtime_line_idx = i
            elif runtime_line_idx is not None and stripped.startswith(f"{key}:"):
                # Found our key under runtime
                key_line_idx = i
                key_indent = len(line) - len(line.lstrip())

        if key_line_idx is None:
            # Key doesn't exist yet - need to add it
            # This is a more complex case, skip for now
            return False

        # Find where this key's section ends (next key at same or lower indent)
        for i in range(key_line_idx + 1, len(lines)):
            line = lines[i]
            if not line.strip() or line.strip().startswith('#'):
                continue
            indent = len(line) - len(line.lstrip())
            if indent <= key_indent:
                key_end_idx = i
                break
        else:
            key_end_idx = len(lines)

        # Build the new section
        new_lines = [f"{'  ' * (key_indent // 2)}{key}:"]
        for k, v in data.items():
            serialized = _serialize_runtime_value(v, key_indent // 2 + 1)
            if isinstance(v, (list, dict)) and v and "\n" in serialized:
                new_lines.append(f"{'  ' * (key_indent // 2 + 1)}{k}:{serialized}")
            else:
                new_lines.append(f"{'  ' * (key_indent // 2 + 1)}{k}: {serialized}")

        # Replace the section
        result_lines = lines[:key_line_idx] + new_lines + lines[key_end_idx:]

        try:
            atomic_write_text(yaml_file, '\n'.join(result_lines))
            return True
        except Exception:
            return False


def migrate_json_runtime_state() -> dict:
    """
    Migrate existing JSON state files to runtime section.

    Reads from junction_state.json, gear_state.json, dispatch_state.json
    and returns a dict suitable for the runtime section.

    Returns:
        Dict with migrated data, or empty dict if no files found.
    """
    state_dir = get_state_dir()
    result = {"junction": {}, "gear": {}, "dispatch": {}}

    # Migrate junction state
    junction_file = state_dir / "junction_state.json"
    if junction_file.exists():
        try:
            data = json.loads(junction_file.read_text())
            result["junction"] = {
                "pending": data.get("pending"),
                "suppressions": data.get("suppression", []),
                "history_tail": data.get("history_tail", [])[-10:],
            }
        except Exception:
            pass

    # Migrate gear state
    gear_file = state_dir / "gear_state.json"
    if gear_file.exists():
        try:
            data = json.loads(gear_file.read_text())
            result["gear"] = {
                "current": data.get("current_gear", "active"),
                "entered_at": data.get("entered_at"),
                "last_run_at": data.get("last_run_at"),
                "last_transition": data.get("last_transition"),
                "iterations": data.get("iterations", 0),
                "patrol_findings_count": data.get("patrol_findings_count", 0),
                "dream_proposals_count": data.get("dream_proposals_count", 0),
            }
        except Exception:
            pass

    # Migrate dispatch state
    dispatch_file = state_dir / "dispatch_state.json"
    if dispatch_file.exists():
        try:
            data = json.loads(dispatch_file.read_text())
            result["dispatch"] = {
                "enabled": data.get("enabled", False),
                "state": data.get("state", "stopped"),
                "iteration": data.get("iteration", 0),
                "stuck_count": data.get("stuck_count", 0),
                "stats": data.get("stats", {
                    "auto_executed": 0,
                    "junctions_hit": 0,
                    "objectives_completed": 0,
                }),
            }
        except Exception:
            pass

    return result


def compute_normalized_current_step(state):
    """
    Compute the normalized current_step for unambiguous plan states.

    Rules:
      - If plan is empty: return 0
      - If all steps are completed: return len(plan) + 1
      - Otherwise: return None (no normalization)
    """
    if not state or not isinstance(state, dict):
        return None

    plan = state.get("plan")
    if plan is None or not isinstance(plan, list):
        return None

    if len(plan) == 0:
        return 0

    for step in plan:
        if not isinstance(step, dict):
            return None
        if step.get("status") != "completed":
            return None

    return len(plan) + 1


def normalize_current_step_file():
    """
    Normalize current_step in active_context.yaml using a targeted line replace.
    Returns (updated: bool, message: str).
    """
    state = load_yaml_state()
    if not state:
        return (False, "State missing or invalid")

    desired = compute_normalized_current_step(state)
    if desired is None:
        return (False, "No normalization needed")

    current = state.get("current_step")
    if current == desired:
        return (False, "Already normalized")

    yaml_file = get_project_dir() / "active_context.yaml"
    try:
        lines = yaml_file.read_text().splitlines(keepends=True)
    except Exception as exc:
        return (False, f"Could not read state file: {exc}")

    pattern = re.compile(r'^(\s*)current_step:\s*.*$')
    for idx, line in enumerate(lines):
        match = pattern.match(line)
        if match:
            indent = match.group(1)
            lines[idx] = f"{indent}current_step: {desired}\n"
            try:
                write_text_atomic(yaml_file, ''.join(lines))
            except Exception as exc:
                return (False, f"Could not write state file: {exc}")
            return (True, f"Normalized current_step to {desired}")

    return (False, "current_step line not found")


# =============================================================================
# HASHING
# =============================================================================

def file_hash(filepath):
    """Calculate SHA256 hash of a file."""
    path = Path(filepath)
    if not path.exists():
        return None
    return hashlib.sha256(path.read_bytes()).hexdigest()


def save_state_hash():
    """Save current hash of active_context.yaml."""
    state_dir = get_state_dir()
    state_dir.mkdir(parents=True, exist_ok=True)

    yaml_file = get_project_dir() / "active_context.yaml"
    h = file_hash(yaml_file)
    if h:
        try:
            atomic_write_text(state_dir / "session_start_hash", h)
        except Exception:
            pass
    return h


def get_start_hash():
    """Get the hash captured at session start."""
    hash_file = get_state_dir() / "session_start_hash"
    if hash_file.exists():
        return hash_file.read_text().strip()
    return None


# =============================================================================
# FAILURE LOGGING
# =============================================================================

def log_failure(command, error):
    """Log a command failure for retry tracking."""
    state_dir = get_state_dir()
    state_dir.mkdir(parents=True, exist_ok=True)

    log_file = state_dir / "failure_log.jsonl"
    entry = {
        "timestamp": datetime.now().isoformat(),
        "command": command[:200],  # Truncate long commands
        "error_preview": str(error)[:200]
    }
    with open(log_file, "a") as f:
        f.write(json.dumps(entry) + "\n")


def get_recent_failures(command, window_minutes=30):
    """Count recent failures of similar commands."""
    log_file = get_state_dir() / "failure_log.jsonl"
    if not log_file.exists():
        return 0

    count = 0
    cutoff = datetime.now().timestamp() - (window_minutes * 60)
    cmd_normalized = command.strip().lower()[:100]

    try:
        for line in log_file.read_text().strip().split('\n'):
            if not line:
                continue
            entry = json.loads(line)
            entry_time = datetime.fromisoformat(entry["timestamp"]).timestamp()
            if entry_time > cutoff:
                logged_cmd = entry.get("command", "").strip().lower()[:100]
                # Fuzzy match - same command prefix
                if logged_cmd.startswith(cmd_normalized[:50]) or cmd_normalized.startswith(logged_cmd[:50]):
                    count += 1
    except Exception:
        pass

    return count


# =============================================================================
# PROOF LOGGING
# =============================================================================

def log_proof(tool_name, tool_input, result, success):
    """
    Append to session proof log.

    Delegates to proof_utils.log_proof_entry() for atomic, session-scoped logging.
    This function maintains backward compatibility while using the new resilient
    proof logging infrastructure.
    """
    try:
        from proof_utils import log_proof_entry
        log_proof_entry(tool_name, tool_input, result, success)
    except ImportError:
        # Fallback to original implementation if proof_utils not available
        proof_dir = get_proof_dir()
        proof_dir.mkdir(parents=True, exist_ok=True)

        log_file = proof_dir / "session_log.jsonl"

        if isinstance(tool_input, dict):
            input_data = tool_input
        else:
            input_data = str(tool_input)[:500]

        entry = {
            "timestamp": datetime.now().isoformat(),
            "tool": tool_name,
            "input_preview": input_data,
            "success": success,
            "output_preview": str(result)[:1000] if result else None
        }
        with open(log_file, "a") as f:
            f.write(json.dumps(entry) + "\n")


# =============================================================================
# HOOK RESPONSE
# =============================================================================

def respond(decision, reason):
    """Output hook response and exit."""
    print(json.dumps({"decision": decision, "reason": reason}))
    sys.exit(0)


# =============================================================================
# STATE HELPERS
# =============================================================================

def get_current_step(state):
    """Get the current step from state, handling both v1 and v2 formats."""
    if not state:
        return None
    plan = state.get('plan', [])
    current_idx = state.get('current_step', 1) - 1  # 1-indexed to 0-indexed
    if 0 <= current_idx < len(plan):
        return plan[current_idx]
    return None


def get_step_by_status(state, status):
    """Get all steps with a given status."""
    if not state:
        return []
    plan = state.get('plan', [])
    return [s for s in plan if isinstance(s, dict) and s.get('status') == status]


def count_completed_steps(state):
    """Count completed steps in the plan."""
    return len(get_step_by_status(state, 'completed'))


def get_unresolved_mismatches(state):
    """Get mismatches that haven't been resolved."""
    if not state:
        return []
    mismatches = state.get('mismatches', [])
    return [m for m in mismatches if isinstance(m, dict) and not m.get('resolved', False)]


def get_memory_items(state):
    """Get memory items, supporting both 'memory' and legacy 'lessons' keys."""
    if not state:
        return []
    # v2 uses 'memory', v1 used 'lessons'
    memory = state.get('memory', [])
    if not memory:
        # Fallback to lessons for v1 compatibility
        lessons = state.get('lessons', [])
        # Convert simple strings to memory format
        return [{'trigger': '*', 'lesson': l, 'reinforced': 1}
                if isinstance(l, str) else l for l in lessons]
    return memory


def get_schema_version(state):
    """Detect schema version from state content."""
    if not state:
        return 1
    # v2 indicators: memory (not lessons), mismatches, self_score, archive
    if any(k in state for k in ['mismatches', 'self_score', 'archive', 'open_questions', 'next_action']):
        return 2
    if 'memory' in state and state.get('memory'):
        first_mem = state['memory'][0] if state['memory'] else None
        if isinstance(first_mem, dict) and 'trigger' in first_mem:
            return 2
    return 1


def generate_mismatch_id():
    """Generate a unique mismatch ID."""
    return f"mismatch-{datetime.now().strftime('%Y%m%d%H%M%S')}"


# =============================================================================
# INTENT VERIFICATION (Understanding-First v1.0)
# =============================================================================

def get_intent(state: dict = None) -> dict:
    """
    Get the intent section from state.

    Args:
        state: The active_context state dict. If None, loads from file.

    Returns:
        Intent dict with keys: user_wants, success_looks_like, confirmed, confirmed_at
        Returns empty dict if intent section doesn't exist.
    """
    if state is None:
        state = load_yaml_state() or {}

    return state.get("intent", {})


def is_intent_confirmed(state: dict = None) -> bool:
    """
    Check if intent is confirmed.

    Args:
        state: The active_context state dict. If None, loads from file.

    Returns:
        True if intent.confirmed is true, False otherwise.
    """
    intent = get_intent(state)
    return intent.get("confirmed", False) is True


def set_intent_confirmed(confirmed: bool = True, state: dict = None) -> bool:
    """
    Set the intent.confirmed flag in state file.

    Args:
        confirmed: Whether to mark intent as confirmed
        state: State dict (used to check if intent section exists)

    Returns:
        True on success, False on failure
    """
    if state is None:
        state = load_yaml_state() or {}

    # Check if intent section exists
    intent = state.get("intent", {})
    if not intent.get("user_wants"):
        return False  # Can't confirm without user_wants

    yaml_file = get_project_dir() / "active_context.yaml"
    if not yaml_file.exists():
        return False

    try:
        content = yaml_file.read_text()
        lines = content.split('\n')
        new_lines = []
        in_intent_section = False
        confirmed_line_found = False

        for line in lines:
            stripped = line.strip()
            indent_level = len(line) - len(line.lstrip())

            # Track when we enter/exit intent section
            if stripped == "intent:" or stripped.startswith("intent: "):
                in_intent_section = True
                new_lines.append(line)
                continue
            elif in_intent_section and indent_level == 0 and stripped and not stripped.startswith("#"):
                # Back to root level (no indentation) = exit intent section
                in_intent_section = False

            # Update confirmed field within intent section
            if in_intent_section and stripped.startswith("confirmed:") and not stripped.startswith("confirmed_at"):
                new_lines.append(f"{' ' * indent_level}confirmed: {'true' if confirmed else 'false'}")
                confirmed_line_found = True
                continue
            elif in_intent_section and stripped.startswith("confirmed_at:"):
                if confirmed:
                    new_lines.append(f"{' ' * indent_level}confirmed_at: \"{datetime.now().isoformat()}\"")
                    continue

            new_lines.append(line)

        if not confirmed_line_found:
            return False  # No confirmed field to update

        write_text_atomic(yaml_file, '\n'.join(new_lines))
        return True
    except Exception:
        return False


def get_intent_summary(state: dict = None) -> str:
    """
    Get a one-line summary of current intent state.

    Returns:
        String like "Intent: confirmed" or "Intent: NOT confirmed (user_wants set)"
    """
    intent = get_intent(state)
    if not intent:
        return "Intent: not set"

    user_wants = intent.get("user_wants", "")
    confirmed = intent.get("confirmed", False)

    if confirmed:
        return "Intent: confirmed"
    elif user_wants:
        return f"Intent: NOT confirmed (user_wants: {user_wants[:40]}...)"
    else:
        return "Intent: not set"


def get_success_criteria(state: dict = None) -> list:
    """
    Get structured success criteria from intent (v1.1).

    Success criteria are optional testable assertions that complement
    the free-text success_looks_like field.

    Example schema:
        success_criteria:
          - type: file_exists
            path: src/components/DarkModeToggle.tsx
          - type: test_passes
            command: npm test -- DarkModeToggle
          - type: manual
            description: "Toggle visible in settings"

    Args:
        state: The active_context state dict. If None, loads from file.

    Returns:
        List of criterion dicts, or empty list if not defined
    """
    intent = get_intent(state)
    return intent.get("success_criteria", [])


def has_structured_criteria(state: dict = None) -> bool:
    """
    Check if intent has structured success criteria (v1.1).

    Returns:
        True if success_criteria array exists and is non-empty
    """
    criteria = get_success_criteria(state)
    return bool(criteria)


# =============================================================================
# OBJECTIVE MANAGEMENT (v6.0)
# =============================================================================

def set_new_objective(objective_text: str, clear_plan: bool = True) -> tuple[bool, str]:
    """
    Set a new objective in active_context.yaml.

    This is the core function for `/edge "objective"` flow.
    It updates the objective, resets intent for confirmation, and optionally
    clears the existing plan.

    IMPORTANT (v6.1): Before clearing, existing plan is archived to preserve history.
    Completed steps are recorded, incomplete steps are noted as "abandoned".

    Args:
        objective_text: The new objective text
        clear_plan: If True, archive then clear existing plan. If False, keep it.

    Returns:
        Tuple of (success: bool, message: str)
    """
    yaml_file = get_project_dir() / "active_context.yaml"

    if not yaml_file.exists():
        return (False, "active_context.yaml not found")

    # v6.1: Archive existing plan before clearing (preserve history)
    if clear_plan:
        try:
            _archive_plan_before_new_objective(objective_text)
        except Exception:
            pass  # Archive failure shouldn't block new objective

    try:
        lines = yaml_file.read_text().split('\n')
        new_lines = []

        # Track what we've updated
        updated_objective = False
        updated_intent = False
        in_intent_section = False
        in_plan_section = False
        intent_indent = 0
        plan_indent = 0
        skip_until_unindent = False
        skip_indent_level = 0

        i = 0
        while i < len(lines):
            line = lines[i]
            stripped = line.lstrip()
            current_indent = len(line) - len(stripped)

            # Handle skipping sections (for plan clearing)
            if skip_until_unindent:
                if stripped and current_indent <= skip_indent_level:
                    skip_until_unindent = False
                else:
                    i += 1
                    continue

            # Update objective line
            if stripped.startswith("objective:"):
                new_lines.append(f'objective: "{objective_text}"')
                updated_objective = True
                i += 1
                continue

            # Track intent section for updating
            if stripped.startswith("intent:"):
                in_intent_section = True
                intent_indent = current_indent
                new_lines.append(line)
                i += 1
                continue

            # Update intent fields
            if in_intent_section and current_indent > intent_indent:
                if stripped.startswith("user_wants:"):
                    new_lines.append(f'{" " * current_indent}user_wants: "{objective_text}"')
                    updated_intent = True
                    i += 1
                    continue
                elif stripped.startswith("success_looks_like:"):
                    new_lines.append(f'{" " * current_indent}success_looks_like: "To be determined during planning"')
                    i += 1
                    continue
                elif stripped.startswith("confirmed:"):
                    new_lines.append(f'{" " * current_indent}confirmed: false')
                    i += 1
                    continue
                elif stripped.startswith("confirmed_at:"):
                    new_lines.append(f'{" " * current_indent}confirmed_at: null')
                    i += 1
                    continue
            elif in_intent_section and stripped and current_indent <= intent_indent:
                in_intent_section = False

            # Handle plan section (clear if requested)
            if clear_plan and stripped.startswith("plan:"):
                in_plan_section = True
                plan_indent = current_indent
                new_lines.append(f'{" " * current_indent}plan: []')
                # Skip all plan content
                skip_until_unindent = True
                skip_indent_level = plan_indent
                i += 1
                continue

            # Reset current_step if clearing plan
            if clear_plan and stripped.startswith("current_step:"):
                new_lines.append(f'{" " * current_indent}current_step: 0')
                i += 1
                continue

            # Update mode to 'plan' for new objectives
            if stripped.startswith("mode:"):
                new_lines.append(f'{" " * current_indent}mode: "plan"')
                i += 1
                continue

            new_lines.append(line)
            i += 1

        if not updated_objective:
            return (False, "Could not find objective field in YAML")

        write_text_atomic(yaml_file, '\n'.join(new_lines))
        return (True, f"Objective set: {objective_text[:60]}...")

    except Exception as e:
        return (False, f"Error updating objective: {e}")


def is_objective_text(text: str) -> bool:
    """
    Determine if text looks like an objective (vs a command).

    An objective is freeform text that describes what to achieve.
    Commands are specific keywords like 'status', 'approve', etc.

    Args:
        text: The text to check

    Returns:
        True if this looks like an objective
    """
    if not text or not text.strip():
        return False

    text = text.strip()

    # Known commands - these are NOT objectives
    commands = {
        'status', 'on', 'off', 'stop', 'approve', 'skip', 'dismiss',
        'plan', 'active', 'review', 'done',  # Mode commands
        '--plan', '--verify', '--auto',  # Flag commands
    }

    # Check if it's a known command
    first_word = text.split()[0].lower()
    if first_word in commands:
        return False

    # If it starts with --, it's a flag
    if text.startswith('--'):
        return False

    # If it's quoted, it's definitely an objective
    if (text.startswith('"') and text.endswith('"')) or \
       (text.startswith("'") and text.endswith("'")):
        return True

    # If it's multiple words, likely an objective
    if len(text.split()) > 2:
        return True

    # Single/double word that's not a command - treat as objective
    # (e.g., "Refactoring" or "Add authentication")
    return True


def extract_objective_text(text: str) -> str:
    """
    Extract the objective text, removing quotes if present.

    Args:
        text: Raw text that may be quoted

    Returns:
        Clean objective text
    """
    text = text.strip()

    # Remove surrounding quotes
    if (text.startswith('"') and text.endswith('"')) or \
       (text.startswith("'") and text.endswith("'")):
        text = text[1:-1]

    return text.strip()


def _rewrite_plan_section(new_plan: list, new_current_step: int) -> bool:
    """
    Rewrite the plan section in active_context.yaml (v7.0 helper).

    This function handles the complex task of replacing the plan array
    in the YAML file while preserving all other content and formatting.

    Args:
        new_plan: The new plan list to write
        new_current_step: The new current_step value

    Returns:
        True if successful, False otherwise
    """
    project_dir = get_project_dir()
    if not project_dir:
        return False

    yaml_file = project_dir / "active_context.yaml"
    if not yaml_file.exists():
        return False

    try:
        content = yaml_file.read_text()
        lines = content.split('\n')

        new_lines = []
        i = 0
        in_plan_section = False
        plan_indent = 0

        while i < len(lines):
            line = lines[i]
            stripped = line.lstrip()
            current_indent = len(line) - len(stripped)

            # Handle current_step
            if stripped.startswith("current_step:"):
                new_lines.append(f"current_step: {new_current_step}")
                i += 1
                continue

            # Detect start of plan section
            if stripped.startswith("plan:"):
                in_plan_section = True
                plan_indent = current_indent

                # Write the new plan
                if not new_plan:
                    new_lines.append(f"{' ' * plan_indent}plan: []")
                else:
                    new_lines.append(f"{' ' * plan_indent}plan:")
                    for step in new_plan:
                        if isinstance(step, dict):
                            desc = step.get('description', '')
                            status = step.get('status', 'pending')
                            proof = step.get('proof', '')
                            is_verification = step.get('is_verification', False)

                            # Write step with proper indentation
                            new_lines.append(f"{' ' * (plan_indent + 2)}- description: \"{desc}\"")
                            new_lines.append(f"{' ' * (plan_indent + 4)}status: \"{status}\"")
                            if proof:
                                # Escape any quotes in proof
                                proof_escaped = proof.replace('"', '\\"')
                                new_lines.append(f"{' ' * (plan_indent + 4)}proof: \"{proof_escaped}\"")
                            if is_verification:
                                new_lines.append(f"{' ' * (plan_indent + 4)}is_verification: true")

                # Skip old plan content
                i += 1
                while i < len(lines):
                    next_line = lines[i]
                    next_stripped = next_line.lstrip()
                    next_indent = len(next_line) - len(next_stripped)

                    # Check if we've exited the plan section
                    if next_stripped and not next_stripped.startswith('#'):
                        if next_indent <= plan_indent and not next_line.startswith(' ' * (plan_indent + 1)):
                            # Back to same or lower indent = end of plan
                            in_plan_section = False
                            break
                    elif not next_stripped:
                        # Blank line might be end of plan
                        # Check the next non-blank line
                        peek = i + 1
                        while peek < len(lines) and not lines[peek].strip():
                            peek += 1
                        if peek < len(lines):
                            peek_stripped = lines[peek].lstrip()
                            peek_indent = len(lines[peek]) - len(peek_stripped)
                            if peek_indent <= plan_indent and peek_stripped and not peek_stripped.startswith('#'):
                                in_plan_section = False
                                break
                    i += 1
                continue

            new_lines.append(line)
            i += 1

        write_text_atomic(yaml_file, '\n'.join(new_lines))
        return True

    except Exception:
        return False


def auto_archive_completed_steps(max_completed: int = 3) -> tuple[int, str]:
    """
    Auto-archive completed steps when there are too many (v7.0).

    This keeps the active_context.yaml slim by archiving completed steps
    immediately rather than waiting for manual /edge-prune.

    Args:
        max_completed: Maximum completed steps to keep visible (default 3).
                       The most recent N completed steps are preserved.

    Returns:
        (archived_count, message)
    """
    try:
        from archive_utils import archive_completed_step
        from proof_utils import get_current_session_id
    except ImportError:
        return (0, "Archive utilities not available")

    state = load_yaml_state()
    if not state:
        return (0, "No state file found")

    plan = state.get("plan", [])
    objective = state.get("objective", "Unknown")

    # Find completed steps with their indices
    completed_indices = []
    for i, step in enumerate(plan):
        if isinstance(step, dict) and step.get("status") == "completed":
            completed_indices.append(i)

    # Keep the most recent N completed steps (highest indices)
    if len(completed_indices) <= max_completed:
        return (0, "No pruning needed")

    # Archive older completed steps (lower indices)
    indices_to_archive = completed_indices[:-max_completed]  # All but last N

    session_id = "unknown"
    try:
        session_id = get_current_session_id()
    except Exception:
        pass

    # Archive each step (in reverse to preserve indices while removing)
    archived_count = 0
    for idx in sorted(indices_to_archive, reverse=True):
        step = plan[idx]
        step_number = idx + 1  # 1-based

        # Archive the step
        archive_completed_step(step, step_number, objective, session_id)

        # Remove from plan
        plan.pop(idx)
        archived_count += 1

    if archived_count > 0:
        # Adjust current_step pointer if needed
        current_step = state.get("current_step", 0)
        new_current_step = current_step
        if current_step > len(plan):
            new_current_step = len(plan)

        # Rewrite the plan section in the YAML file
        _rewrite_plan_section(plan, new_current_step)

    return (archived_count, f"Archived {archived_count} completed steps")


def _archive_plan_before_new_objective(new_objective: str) -> None:
    """
    Archive the existing plan before setting a new objective (v6.1).

    This preserves history of completed work and notes abandoned steps.
    The archive entry includes:
    - Old objective name
    - New objective name
    - List of completed steps with their proof
    - List of incomplete steps (abandoned)

    Archives to .proof/archive.jsonl
    """
    try:
        from archive_utils import log_to_archive
    except ImportError:
        return  # Archive not available

    state = load_yaml_state()
    if not state:
        return

    old_objective = state.get("objective", "")
    plan = state.get("plan", [])

    if not plan or not old_objective:
        return  # Nothing to archive

    # Don't archive if objectives are the same (re-running same objective)
    if old_objective.strip().lower() == new_objective.strip().lower():
        return

    # Categorize steps
    completed = []
    incomplete = []
    for i, step in enumerate(plan):
        if isinstance(step, dict):
            status = step.get("status", "pending")
            step_info = {
                "step_number": i + 1,
                "description": step.get("description", "")[:200],  # Truncate long descriptions
                "status": status,
                "proof": step.get("proof", "")[:500] if step.get("proof") else ""
            }
            if status == "completed":
                completed.append(step_info)
            else:
                incomplete.append(step_info)

    # Get session ID if available
    try:
        from proof_utils import get_current_session_id
        session_id = get_current_session_id()
    except (ImportError, Exception):
        session_id = "unknown"

    # Archive the transition
    log_to_archive("objective_transition", {
        "old_objective": old_objective[:200],
        "new_objective": new_objective[:200],
        "completed_steps": len(completed),
        "incomplete_steps": len(incomplete),
        "total_steps": len(plan),
        "completed_details": completed,
        "incomplete_details": incomplete,
        "session_id": session_id,
        "reason": "new_objective_set",
        "note": "Incomplete steps were abandoned when new objective was set"
    })

    # v7.1: Capture partial objective data for learned guidance
    # This captures what was working in the abandoned approach
    try:
        from archive_utils import capture_objective_partial
        capture_objective_partial(
            state=state,
            session_id=session_id,
            reason="objective_changed",
            new_objective=new_objective
        )
    except Exception:
        pass  # Guidance capture failure shouldn't block objective change
