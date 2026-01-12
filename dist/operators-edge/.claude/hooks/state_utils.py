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
from pathlib import Path


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


@contextmanager
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
    if value.startswith('"') and value.endswith('"'):
        return value[1:-1]
    if value.startswith("'") and value.endswith("'"):
        return value[1:-1]
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
    """Check if next non-empty line starts a nested dict."""
    if i + 1 >= len(lines):
        return False, 0

    next_line = lines[i + 1]
    next_stripped = next_line.strip()
    next_indent = len(next_line) - len(next_line.lstrip())

    if next_stripped and not next_stripped.startswith('#') and not next_stripped.startswith('- '):
        if ':' in next_stripped and next_indent > indent:
            return True, next_indent
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
    """Parse a nested dictionary block."""
    result = {}
    i = start_idx

    while i < len(lines):
        line = lines[i]
        stripped = line.strip()

        if not stripped or stripped.startswith('#'):
            i += 1
            continue

        indent = len(line) - len(line.lstrip())

        # If dedented, we're done
        if indent < base_indent:
            break

        if ':' in stripped:
            key, _, value = stripped.partition(':')
            key = key.strip()
            value = value.strip()

            if value:
                result[key] = parse_yaml_value(value)
            else:
                result[key] = None

        i += 1

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
    """Append to session proof log."""
    proof_dir = get_proof_dir()
    proof_dir.mkdir(parents=True, exist_ok=True)

    log_file = proof_dir / "session_log.jsonl"

    # Preserve dict structure if it's a dict (for Edit old_string/new_string)
    # Otherwise convert to string preview
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
