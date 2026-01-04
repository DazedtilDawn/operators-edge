#!/usr/bin/env python3
"""
Operator's Edge - ClickUp Integration Utilities
Automatic task sync between active_context.yaml and ClickUp.

Creates tasks when objectives are set, updates status on completion.
"""

import json
import urllib.request
import urllib.error
from pathlib import Path
from typing import Optional, Dict, Any

# =============================================================================
# CONFIGURATION
# =============================================================================

def get_config_path() -> Path:
    """Get path to ClickUp config file."""
    return Path(__file__).parent.parent / "state" / "clickup_config.json"


def load_config() -> Optional[Dict[str, Any]]:
    """Load ClickUp configuration."""
    config_path = get_config_path()
    if not config_path.exists():
        return None

    try:
        with open(config_path) as f:
            return json.load(f)
    except (json.JSONDecodeError, IOError):
        return None


def is_enabled() -> bool:
    """Check if ClickUp integration is enabled."""
    config = load_config()
    return config is not None and config.get("enabled", False)


# =============================================================================
# API HELPERS
# =============================================================================

def _api_request(
    method: str,
    endpoint: str,
    data: Optional[Dict] = None,
    config: Optional[Dict] = None
) -> Optional[Dict]:
    """Make a ClickUp API request."""
    if config is None:
        config = load_config()

    if not config or not config.get("api_token"):
        return None

    url = f"https://api.clickup.com/api/v2{endpoint}"
    headers = {
        "Authorization": config["api_token"],
        "Content-Type": "application/json",
    }

    body = json.dumps(data).encode() if data else None

    try:
        req = urllib.request.Request(url, data=body, headers=headers, method=method)
        with urllib.request.urlopen(req, timeout=10) as response:
            return json.loads(response.read().decode())
    except (urllib.error.URLError, json.JSONDecodeError, TimeoutError) as e:
        print(f"ClickUp API error: {e}")
        return None


# =============================================================================
# TASK OPERATIONS
# =============================================================================

def create_task(
    objective: str,
    plan_steps: Optional[list] = None,
    list_id: Optional[str] = None
) -> Optional[str]:
    """
    Create a ClickUp task for an objective.

    Args:
        objective: The objective text (becomes task name)
        plan_steps: Optional list of plan step descriptions
        list_id: Override default list ID

    Returns:
        Task ID if successful, None otherwise
    """
    config = load_config()
    if not config or not is_enabled():
        return None

    target_list = list_id or config.get("default_list_id")
    if not target_list:
        return None

    # Build task description
    description_parts = ["Created by Operator's Edge"]
    if plan_steps:
        description_parts.append("\n**Plan:**")
        for i, step in enumerate(plan_steps, 1):
            step_text = step.get("description", step) if isinstance(step, dict) else step
            description_parts.append(f"{i}. {step_text}")

    description = "\n".join(description_parts)

    # Get initial status from mapping
    status_mapping = config.get("status_mapping", {})
    initial_status = status_mapping.get("objective_set", "in development")

    # Create the task
    data = {
        "name": f"[Edge] {objective}",
        "description": description,
        "status": initial_status,
    }

    result = _api_request("POST", f"/list/{target_list}/task", data, config)

    if result and "id" in result:
        task_id = result["id"]
        # Store task ID for later updates
        _save_current_task(task_id, result.get("url", ""))
        return task_id

    return None


def update_task_status(task_id: str, status: str) -> bool:
    """
    Update a ClickUp task's status.

    Args:
        task_id: The ClickUp task ID
        status: New status name

    Returns:
        True if successful
    """
    config = load_config()
    if not config or not is_enabled():
        return False

    result = _api_request("PUT", f"/task/{task_id}", {"status": status}, config)
    return result is not None


def complete_current_task() -> bool:
    """Mark the current objective's task as complete."""
    config = load_config()
    if not config or not is_enabled():
        return False

    task_info = _load_current_task()
    if not task_info or not task_info.get("task_id"):
        return False

    status_mapping = config.get("status_mapping", {})
    complete_status = status_mapping.get("objective_complete", "shipped")

    success = update_task_status(task_info["task_id"], complete_status)

    if success:
        _clear_current_task()

    return success


# =============================================================================
# TASK STATE TRACKING
# =============================================================================

def _get_task_state_path() -> Path:
    """Get path to current task state file."""
    return Path(__file__).parent.parent / "state" / "clickup_task.json"


def _save_current_task(task_id: str, url: str) -> None:
    """Save current task info for later updates."""
    state_path = _get_task_state_path()
    state_path.parent.mkdir(parents=True, exist_ok=True)

    with open(state_path, "w") as f:
        json.dump({"task_id": task_id, "url": url}, f)


def _load_current_task() -> Optional[Dict[str, str]]:
    """Load current task info."""
    state_path = _get_task_state_path()
    if not state_path.exists():
        return None

    try:
        with open(state_path) as f:
            return json.load(f)
    except (json.JSONDecodeError, IOError):
        return None


def _clear_current_task() -> None:
    """Clear current task tracking."""
    state_path = _get_task_state_path()
    if state_path.exists():
        state_path.unlink()


def get_current_task_url() -> Optional[str]:
    """Get the URL of the current objective's ClickUp task."""
    task_info = _load_current_task()
    return task_info.get("url") if task_info else None


# =============================================================================
# INTEGRATION HOOKS
# =============================================================================

def on_objective_set(objective: str, plan: Optional[list] = None) -> Optional[str]:
    """
    Hook called when an objective is set.

    Returns task URL if created.
    """
    if not is_enabled():
        return None

    task_id = create_task(objective, plan)
    if task_id:
        return get_current_task_url()
    return None


def on_objective_complete() -> bool:
    """
    Hook called when an objective is completed.

    Returns True if task was updated.
    """
    return complete_current_task()


# =============================================================================
# CLI TESTING
# =============================================================================

if __name__ == "__main__":
    import sys

    if len(sys.argv) < 2:
        print("Usage: python clickup_utils.py <test|status>")
        sys.exit(1)

    cmd = sys.argv[1]

    if cmd == "test":
        print("Testing ClickUp integration...")
        config = load_config()
        if not config:
            print("No config found")
            sys.exit(1)

        print(f"Enabled: {is_enabled()}")
        print(f"List ID: {config.get('default_list_id')}")

        # Test task creation
        task_id = create_task("Test objective from CLI", ["Step 1", "Step 2"])
        if task_id:
            print(f"Created task: {task_id}")
            print(f"URL: {get_current_task_url()}")
        else:
            print("Failed to create task")

    elif cmd == "status":
        task_url = get_current_task_url()
        if task_url:
            print(f"Current task: {task_url}")
        else:
            print("No current task")
