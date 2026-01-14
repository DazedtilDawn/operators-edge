#!/usr/bin/env python3
"""
Operator's Edge - Post-Tool Proof Capture
Automatically captures proof artifacts after tool execution.

Captures:
1. All Bash command outputs (success and failure)
2. File edit summaries
3. Failures logged for retry blocking
4. Post-commit test suggestions
"""
import json
import os
import re
import subprocess
import sys
from datetime import datetime

# Add hooks directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from edge_utils import (
    get_proof_dir,
    log_failure,
    log_proof,
    load_yaml_state,
    get_evals_config,
    auto_triage,
    load_eval_state,
    save_eval_state,
    finish_eval_run,
    normalize_current_step_file,
    handle_eval_failure,
)


def is_git_commit_command(cmd):
    """Check if command is a git commit."""
    if not cmd:
        return False
    # Match "git commit" but not "git commit --amend" alone
    return bool(re.search(r'\bgit\s+commit\b', cmd))


def reinforce_relevant_lessons(tool_name, tool_input, success):
    """
    Log relevant lessons that applied to this tool use (v3.10).
    This surfaces lessons for potential reinforcement - actual persistence
    happens via normal workflow when Claude edits active_context.yaml.
    """
    if not success:
        return

    # Only track for action tools
    if tool_name not in ("Edit", "Write", "NotebookEdit", "Bash"):
        return

    try:
        from memory_utils import surface_relevant_memory

        state = load_yaml_state()
        if not state:
            return

        # Build context from tool input
        file_path = tool_input.get("file_path", "")
        command = tool_input.get("command", "")
        context = f"{tool_name} {file_path} {command}"

        # Find relevant lessons (v3.12: pass file_path for pattern filtering)
        relevant = surface_relevant_memory(state, context, file_path=file_path if file_path else None)

        # Log relevant lessons for visibility (reinforcement happens via normal workflow)
        if relevant:
            triggers = [l.get("trigger", "?") for l in relevant]
            log_proof("lesson_match", {"triggers": triggers, "context": context[:100]},
                     f"Lessons [{', '.join(triggers)}] matched tool use", True)

    except (ImportError, Exception):
        pass  # Best effort - don't fail tool execution


def run_tests_after_commit():
    """Run tests and return (success, summary)."""
    hooks_dir = os.path.dirname(os.path.abspath(__file__))

    try:
        # Try to run unittest discover on the hooks test files
        result = subprocess.run(
            [sys.executable, '-m', 'unittest', 'discover', '-s', hooks_dir, '-p', 'test_*.py', '-v'],
            capture_output=True,
            text=True,
            timeout=120,
            cwd=hooks_dir
        )

        # Parse output for test count
        output = result.stderr + result.stdout
        match = re.search(r'Ran (\d+) tests? in', output)
        test_count = match.group(1) if match else "?"

        if result.returncode == 0:
            return True, f"{test_count} tests passed"
        else:
            # Find failure details
            failures = re.findall(r'FAIL: (\w+)', output)
            errors = re.findall(r'ERROR: (\w+)', output)
            issues = failures + errors
            return False, f"{len(issues)} test(s) failed: {', '.join(issues[:3])}"
    except subprocess.TimeoutExpired:
        return False, "Tests timed out after 120s"
    except Exception as e:
        return False, f"Could not run tests: {e}"

def main():
    try:
        data = json.load(sys.stdin)
    except json.JSONDecodeError:
        # Can't parse, nothing to log
        return

    tool_name = data.get("tool_name", "")
    tool_input = data.get("tool_input", {}) or {}
    tool_result = data.get("tool_result", {}) or {}

    # Determine success/failure
    # For Bash, check exit code
    if tool_name == "Bash":
        exit_code = tool_result.get("exit_code", 0)
        stdout = tool_result.get("stdout", "")
        stderr = tool_result.get("stderr", "")
        cmd = tool_input.get("command", "")
        success = (exit_code == 0)

        # Log the command execution
        result_preview = stdout[:500] if stdout else stderr[:500]
        log_proof(tool_name, tool_input, result_preview, success)

        # If failed, log for retry blocking
        if not success:
            error_msg = stderr or stdout or f"Exit code {exit_code}"
            log_failure(cmd, error_msg)

        # Post-commit test runner
        if success and is_git_commit_command(cmd):
            print("\n🧪 POST-COMMIT: Running tests...", file=sys.stderr)
            test_success, test_summary = run_tests_after_commit()
            if test_success:
                print(f"✅ {test_summary}", file=sys.stderr)
            else:
                print(f"❌ {test_summary}", file=sys.stderr)
                print("⚠️  Consider amending the commit after fixing tests.", file=sys.stderr)

    # For Edit/Write, log the file change with diff content
    elif tool_name in ("Edit", "Write", "NotebookEdit"):
        file_path = tool_input.get("file_path", "unknown")
        success = tool_result.get("success", True)

        # Capture old_string/new_string for Edit operations (for diff preview)
        if tool_name == "Edit":
            old_string = tool_input.get("old_string", "")
            new_string = tool_input.get("new_string", "")
            log_proof(tool_name, {
                "file": file_path,
                "old_string": old_string[:2000] if old_string else "",  # Truncate large diffs
                "new_string": new_string[:2000] if new_string else ""
            }, f"Modified: {file_path}", success)
        else:
            log_proof(tool_name, {"file": file_path}, f"Modified: {file_path}", success)

        # Auto-normalize current_step when active_context.yaml is edited
        if "active_context.yaml" in file_path:
            normalize_current_step_file()

        # Eval automation: finalize eval run for write/edit tools
        eval_state = load_eval_state()
        pending_run = eval_state.get("pending_run")
        if pending_run and pending_run.get("tool") == tool_name:
            state = load_yaml_state()
            evals_config = get_evals_config(state)
            evals_config, _triage = auto_triage(state, evals_config, tool_name)

            if evals_config.get("enabled", True) and evals_config.get("mode") != "manual":
                if evals_config.get("level", 0) >= 1:
                    eval_entry = finish_eval_run(pending_run, evals_config, success)

                    # Auto-mismatch on eval failure (v3.9.8)
                    if eval_entry and eval_entry.get("invariants_failed"):
                        handle_eval_failure(eval_entry)

            eval_state["last_run"] = pending_run
            eval_state["pending_run"] = None
            save_eval_state(eval_state)
        elif pending_run:
            eval_state["pending_run"] = None
            save_eval_state(eval_state)

    # For Read, just note what was read (lightweight)
    elif tool_name == "Read":
        file_path = tool_input.get("file_path", "unknown")
        log_proof(tool_name, {"file": file_path}, "Read file", True)
        success = True

    # For other tools, generic logging
    else:
        log_proof(tool_name, tool_input, str(tool_result)[:500], True)
        success = True

    # v3.10: Reinforce relevant lessons after successful tool use
    reinforce_relevant_lessons(tool_name, tool_input, success)

    # v3.11: Auto-resolve pending obligations (Mechanical Learning)
    try:
        from obligation_utils import auto_resolve_obligations, log_obligation_event
        from proof_utils import log_to_session

        resolved = auto_resolve_obligations(tool_name, success, tool_input)

        # Log resolution to proof
        state = load_yaml_state()
        session_id = state.get('session', {}).get('id', '') if state else ''

        for ob in resolved:
            log_entry = log_obligation_event(ob.status, ob, session_id)
            log_to_session(log_entry)
    except (ImportError, Exception):
        pass  # Obligation system unavailable, continue without

if __name__ == "__main__":
    main()
