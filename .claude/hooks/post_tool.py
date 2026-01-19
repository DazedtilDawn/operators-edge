#!/usr/bin/env python3
"""
Operator's Edge - Post-Tool Proof Capture
Automatically captures proof artifacts after tool execution.

Captures:
1. All Bash command outputs (success and failure)
2. File edit summaries
3. Failures logged for retry blocking
4. Post-commit test suggestions
5. Pattern learning feedback (v6.0 Generative Layer)
6. Outcome tracking for rule effectiveness (v7.0)
7. Drift detection and intervention (v8.0 Context Engineering)
8. Known fix lookup and learning (v8.0 Codebase Knowledge)
9. Co-change pattern tracking (v8.0 Codebase Knowledge)
10. Session metrics collection (v8.0 Phase 5 - Observability)
11. Active intervention health tracking (v8.0 Phase 8)
12. Fix outcome tracking (v8.0 Phase 9 - Closed Loop)
13. Auto-checkpoint tracking and offers (v8.0 Phase 10)
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
)


def is_git_commit_command(cmd):
    """Check if command is a git commit."""
    if not cmd:
        return False
    # Match "git commit" but not "git commit --amend" alone
    return bool(re.search(r'\bgit\s+commit\b', cmd))


def check_drift_and_intervene():
    """
    v8.0: Check for drift patterns and surface intervention if detected.

    This is supervision, not training. We detect circular behavior
    and alert Claude before too much context is wasted.
    """
    try:
        from drift_detector import detect_drift, format_drift_intervention
        from proof_utils import get_session_log_path

        # Get current session log
        session_log = get_session_log_path()
        if not session_log or not session_log.exists():
            return

        # Load state for step stall detection
        state = load_yaml_state() or {}

        # Run drift detection
        signals = detect_drift(session_log, state, lookback_minutes=30)

        if signals:
            # Only surface if we have warning or critical severity
            significant = [s for s in signals if s.severity in ("warning", "critical")]
            if significant:
                intervention = format_drift_intervention(significant)
                print(intervention, file=sys.stderr)

                # v8.0 Phase 5: Record drift signals in metrics
                try:
                    from session_metrics import record_drift_signal
                    for signal in significant:
                        record_drift_signal(signal.signal_type, signal.severity)
                except ImportError:
                    pass

    except ImportError:
        pass  # Drift detector not available
    except Exception:
        pass  # Don't fail the hook if drift detection fails


def lookup_known_fix(error_output: str):
    """
    v8.0: Check if we've seen this error before and surface known fix.

    This is codebase-specific knowledge - not generic patterns, but
    actual fixes that worked in THIS codebase.

    Returns the fix object if found (for active intervention system).
    """
    if not error_output:
        return None

    try:
        from codebase_knowledge import lookup_fix, format_known_fix, compute_signature_hash

        fix = lookup_fix(error_output)
        if fix and fix.confidence >= 0.4:  # Only surface reasonably confident fixes
            formatted = format_known_fix(fix)
            print(formatted, file=sys.stderr)

            # v8.0 Phase 5: Record fix surfaced in metrics
            try:
                from session_metrics import record_fix_surfaced
                record_fix_surfaced()
            except ImportError:
                pass

            # v8.0 Phase 9: Track fix surfacing for outcome correlation
            try:
                from fix_outcomes import track_fix_surfaced
                track_fix_surfaced(
                    fix_signature=compute_signature_hash(fix.error_signature),
                    error_signature=fix.error_signature,
                    fix_commands=fix.fix_commands
                )
            except ImportError:
                pass  # Fix outcomes not available
            except Exception:
                pass  # Don't fail the hook

            return fix  # Return for active intervention tracking

    except ImportError:
        pass  # Codebase knowledge not available
    except Exception:
        pass  # Don't fail the hook

    return None


def record_successful_fix(error_output: str, cmd: str, files_modified: list = None) -> None:
    """
    v8.0: Record what fixed an error for future reference.

    Called when a command succeeds after a previous failure with the same signature.
    """
    if not error_output:
        return

    try:
        from codebase_knowledge import record_fix

        record_fix(
            error_output=error_output,
            fix_description=f"Fixed by running: {cmd[:100]}",
            fix_commands=[cmd],
            fix_files=files_modified or [],
            context_hints=[]
        )

        # v8.0 Phase 5: Record fix learned in metrics
        try:
            from session_metrics import record_fix_learned, record_fix_followed
            record_fix_learned()
            record_fix_followed(success=True)
        except ImportError:
            pass

    except ImportError:
        pass
    except Exception:
        pass


def track_cochange_patterns(files_modified_this_session: list) -> None:
    """
    v8.0: Track files that are modified together (co-change patterns).

    If multiple files are modified in the same session, they likely
    need to change together. This knowledge helps future sessions.
    """
    if not files_modified_this_session or len(files_modified_this_session) < 2:
        return

    try:
        from codebase_knowledge import record_cochange

        # Record co-change between recently modified files
        # Only pair up the last few files to avoid noise
        recent = files_modified_this_session[-5:]
        for i, file1 in enumerate(recent):
            for file2 in recent[i+1:]:
                # Skip if same directory (likely already known)
                if os.path.dirname(file1) == os.path.dirname(file2):
                    continue
                record_cochange(file1, file2, "Modified together in session")

    except ImportError:
        pass
    except Exception:
        pass


# Track state for fix learning (error -> subsequent success)
_recent_bash_failure = {"cmd": "", "error": "", "timestamp": None}
_files_modified_this_session = []


def record_tool_outcome(tool_name, tool_input, success, error_message=""):
    """
    Record tool outcome for pattern learning (v6.0) and rule effectiveness (v7.0).

    This is evidence-based reinforcement - we only reinforce patterns
    when there's observable evidence of tool success/failure.
    """
    # Only track file modifications
    if tool_name not in ("Edit", "Write", "NotebookEdit"):
        return

    file_path = tool_input.get("file_path", "")
    if not file_path:
        return

    # Skip internal paths
    safe_paths = ["active_context.yaml", ".proof/", "checklist.md", "archive.md"]
    if any(safe in file_path for safe in safe_paths):
        return

    # v7.0: Log outcome for rule effectiveness tracking
    try:
        from outcome_tracker import get_pending_correlation, log_outcome_event

        corr_id = get_pending_correlation(file_path)
        if corr_id:
            log_outcome_event(
                correlation_id=corr_id,
                success=success,
                override=False,  # TODO: detect when user overrode a warning
                error_message=error_message
            )
    except ImportError:
        pass  # Outcome tracker not available
    except Exception:
        pass  # Don't fail the hook if tracking fails

    # v6.0: Pattern learning (legacy, kept for backward compatibility)
    try:
        from learning_loop import track_tool_outcome, _file_pattern_tracking
        from pattern_metrics import log_edit_outcome

        state = load_yaml_state()
        patterns_shown = 0

        # Check how many patterns were shown for this file
        tracking = _file_pattern_tracking.get(file_path, {})
        patterns_shown = len(tracking.get("patterns", []))

        if state:
            result = track_tool_outcome(
                state=state,
                tool_name=tool_name,
                file_path=file_path,
                success=success
            )
            patterns_reinforced = result.get("patterns_reinforced", 0)
        else:
            patterns_reinforced = 0

        # Log metrics for impact measurement
        log_edit_outcome(
            file_path=file_path,
            success=success,
            patterns_shown=patterns_shown,
            patterns_reinforced=patterns_reinforced
        )

    except ImportError:
        pass  # Learning loop not available
    except Exception:
        pass  # Don't fail the hook if learning fails


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

            # v8.0: Surface known fix if we've seen this error before
            fix = lookup_known_fix(error_msg)

            # v8.0 Phase 8: Update active intervention health tracking
            try:
                from active_intervention import update_health_from_error
                update_health_from_error(error_msg, fix)
            except ImportError:
                pass  # Active intervention not available
            except Exception:
                pass  # Don't fail the hook

            # Track this failure for fix learning
            _recent_bash_failure["cmd"] = cmd
            _recent_bash_failure["error"] = error_msg
            _recent_bash_failure["timestamp"] = datetime.now()

        else:
            # v8.0 Phase 8: Update health on success (clears pending errors)
            try:
                from active_intervention import update_health_from_success
                update_health_from_success()
            except ImportError:
                pass
            except Exception:
                pass

            # v8.0: Check if this success fixed a recent failure
            if (_recent_bash_failure["error"] and
                _recent_bash_failure["timestamp"] and
                (datetime.now() - _recent_bash_failure["timestamp"]).seconds < 300):
                # Success within 5 minutes of a failure - might be a fix
                record_successful_fix(
                    error_output=_recent_bash_failure["error"],
                    cmd=cmd,
                    files_modified=_files_modified_this_session[-3:]  # Recent files
                )
                # Clear the failure record
                _recent_bash_failure["error"] = ""

        # v8.0 Phase 9: Track command for fix outcome correlation
        # This tracks ALL Bash commands (success and failure) to correlate with pending fixes
        try:
            from fix_outcomes import track_command_after_fix
            track_command_after_fix(cmd, success)
        except ImportError:
            pass  # Fix outcomes not available
        except Exception:
            pass  # Don't fail the hook

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
        error_message = tool_result.get("error", "") or tool_result.get("message", "")

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

        # v6.0 + v7.0: Record outcome for pattern learning and rule effectiveness
        record_tool_outcome(tool_name, tool_input, success, error_message)

        # v8.0: Track file for co-change pattern learning
        if success and file_path != "unknown":
            # Skip internal paths
            safe_paths = ["active_context.yaml", ".proof/", "checklist.md"]
            if not any(safe in file_path for safe in safe_paths):
                _files_modified_this_session.append(file_path)
                # Periodically track co-changes (every 5 files)
                if len(_files_modified_this_session) >= 5:
                    track_cochange_patterns(_files_modified_this_session)
                    # Keep only recent files to avoid memory growth
                    _files_modified_this_session[:] = _files_modified_this_session[-10:]

    # For Read, just note what was read (lightweight)
    elif tool_name == "Read":
        file_path = tool_input.get("file_path", "unknown")
        log_proof(tool_name, {"file": file_path}, "Read file", True)

    # For other tools, generic logging
    else:
        log_proof(tool_name, tool_input, str(tool_result)[:500], True)

    # v8.0: Check for drift patterns after every tool execution
    # Only check on tools that indicate active work (not just reading)
    if tool_name in ("Edit", "Write", "NotebookEdit", "Bash"):
        check_drift_and_intervene()

        # v8.0 Phase 8: Update health metrics for intervention system
        try:
            from active_intervention import update_health_metrics
            from context_monitor import estimate_context_usage
            from proof_utils import get_session_log_path

            session_log = get_session_log_path()
            if session_log and session_log.exists():
                estimate = estimate_context_usage(session_log)
                update_health_metrics(
                    context_usage=estimate.usage_percentage * 100,
                    drift_signals=0,  # Counted in check_drift_and_intervene
                )
        except ImportError:
            pass  # Modules not available
        except Exception:
            pass  # Don't fail the hook

    # v8.0 Phase 10: Auto-checkpoint tracking
    # Record tool calls for session state and check for breakpoints
    try:
        from auto_checkpoint import (
            record_tool_call as checkpoint_record_tool,
            record_error as checkpoint_record_error,
            record_error_resolved as checkpoint_record_resolved,
            check_and_offer_checkpoint,
        )

        # Record tool call
        file_path = None
        if tool_name in ("Edit", "Write"):
            file_path = tool_input.get("file_path")
        checkpoint_record_tool(tool_name, file_path)

        # Track errors and resolutions for Bash
        if tool_name == "Bash":
            exit_code = tool_result.get("exit_code", 0)
            if exit_code != 0:
                # Record error
                stderr = tool_result.get("stderr", "")
                checkpoint_record_error(stderr[:200] if stderr else f"Exit code {exit_code}")
            elif _recent_bash_failure.get("error"):
                # Success after failure - might be resolved
                checkpoint_record_resolved()

        # Check for natural breakpoints (only after active work)
        if tool_name in ("Edit", "Write", "NotebookEdit", "Bash"):
            offer = check_and_offer_checkpoint("tick")
            if offer:
                print(f"\n{offer}", file=sys.stderr)
    except ImportError:
        pass  # auto_checkpoint not available
    except Exception:
        pass  # Don't fail the hook

if __name__ == "__main__":
    main()
