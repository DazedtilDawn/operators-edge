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
    log_proof
)


def is_git_commit_command(cmd):
    """Check if command is a git commit."""
    if not cmd:
        return False
    # Match "git commit" but not "git commit --amend" alone
    return bool(re.search(r'\bgit\s+commit\b', cmd))


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

    # For Read, just note what was read (lightweight)
    elif tool_name == "Read":
        file_path = tool_input.get("file_path", "unknown")
        log_proof(tool_name, {"file": file_path}, "Read file", True)

    # For other tools, generic logging
    else:
        log_proof(tool_name, tool_input, str(tool_result)[:500], True)

if __name__ == "__main__":
    main()
