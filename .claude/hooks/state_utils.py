#!/usr/bin/env python3
"""
Operator's Edge - State Utilities
Core state management: paths, YAML parsing, hashing, logging.
"""
import hashlib
import json
import os
import sys
from datetime import datetime
from pathlib import Path


# =============================================================================
# PATH UTILITIES
# =============================================================================

def get_project_dir():
    """Get the project directory from environment."""
    return Path(os.environ.get("CLAUDE_PROJECT_DIR", os.getcwd()))


def get_state_dir():
    """Get the .claude/state directory."""
    return get_project_dir() / ".claude" / "state"


def get_proof_dir():
    """Get the .proof directory."""
    return get_project_dir() / ".proof"


def get_archive_file():
    """Get the archive file path."""
    return get_proof_dir() / "archive.jsonl"


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
        (state_dir / "session_start_hash").write_text(h)
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
    entry = {
        "timestamp": datetime.now().isoformat(),
        "tool": tool_name,
        "input_preview": str(tool_input)[:500],
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
