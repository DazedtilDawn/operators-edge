#!/usr/bin/env python3
"""
Operator's Edge v6.0 Validation Test
=====================================

Run this script on Windows to verify your installation is correct and updated.

Usage:
    python validate_v6.py

Expected: All tests PASS (green checkmarks)

If any tests FAIL, the installation is incomplete or corrupted.
"""

import sys
import os
from pathlib import Path

# Colors for Windows terminal (ANSI codes work in Windows 10+)
GREEN = "\033[92m"
RED = "\033[91m"
YELLOW = "\033[93m"
RESET = "\033[0m"
BOLD = "\033[1m"

def check(condition, name, details=""):
    """Print a check result."""
    if condition:
        print(f"  {GREEN}✓{RESET} {name}")
        return True
    else:
        print(f"  {RED}✗{RESET} {name}")
        if details:
            print(f"    {YELLOW}→ {details}{RESET}")
        return False


def find_project_root():
    """Find the Operator's Edge project root."""
    # Try current directory first
    if (Path(".") / "CLAUDE.md").exists():
        return Path(".").resolve()

    # Try parent directories
    for parent in Path(__file__).resolve().parents:
        if (parent / "CLAUDE.md").exists():
            return parent

    return None


def main():
    print(f"\n{BOLD}=" * 60)
    print("OPERATOR'S EDGE v6.0 - VALIDATION TEST")
    print("=" * 60 + RESET)

    results = []

    # =========================================================================
    # SECTION 1: File Structure
    # =========================================================================
    print(f"\n{BOLD}[1/5] FILE STRUCTURE{RESET}")

    root = find_project_root()
    if not root:
        print(f"  {RED}✗ Could not find project root (CLAUDE.md not found){RESET}")
        print(f"    Run this script from the Operator's Edge folder")
        sys.exit(1)

    os.chdir(root)
    print(f"  Project root: {root}")

    required_files = [
        ("CLAUDE.md", "Main documentation"),
        (".claude/settings.json", "Hook configuration"),
        (".claude/hooks/edge_skill_hook.py", "Main edge command handler"),
        (".claude/hooks/state_utils.py", "State management utilities"),
        (".claude/hooks/gear_engine.py", "Gear engine"),
        (".claude/hooks/verification_utils.py", "Verification utilities (v5.3+)"),
        (".claude/commands/edge.md", "Edge command definition"),
        (".claude/commands/edge-yolo.md", "Dispatch mode command"),
    ]

    for filepath, description in required_files:
        exists = Path(filepath).exists()
        results.append(check(exists, f"{filepath}", f"Missing: {description}"))

    # =========================================================================
    # SECTION 2: Module Imports
    # =========================================================================
    print(f"\n{BOLD}[2/5] MODULE IMPORTS{RESET}")

    # Add hooks to path
    hooks_path = root / ".claude" / "hooks"
    sys.path.insert(0, str(hooks_path))

    modules_to_import = [
        "state_utils",
        "edge_skill_hook",
        "gear_engine",
        "gear_config",
        "junction_utils",
        "dispatch_utils",
        "verification_utils",
    ]

    imported_modules = {}
    for mod_name in modules_to_import:
        try:
            imported_modules[mod_name] = __import__(mod_name)
            results.append(check(True, f"import {mod_name}"))
        except ImportError as e:
            results.append(check(False, f"import {mod_name}", str(e)))

    # =========================================================================
    # SECTION 3: v6.0 Feature - Objective Functions
    # =========================================================================
    print(f"\n{BOLD}[3/5] v6.0 OBJECTIVE FUNCTIONS{RESET}")

    if "state_utils" in imported_modules:
        su = imported_modules["state_utils"]

        # Check for new v6.0 functions
        has_set_new_objective = hasattr(su, "set_new_objective")
        results.append(check(has_set_new_objective, "set_new_objective() exists"))

        has_is_objective_text = hasattr(su, "is_objective_text")
        results.append(check(has_is_objective_text, "is_objective_text() exists"))

        has_extract_objective = hasattr(su, "extract_objective_text")
        results.append(check(has_extract_objective, "extract_objective_text() exists"))

        # Test is_objective_text logic
        if has_is_objective_text:
            # Should be True for objectives
            test1 = su.is_objective_text('"Deploy auth system"')
            results.append(check(test1, 'is_objective_text("Deploy auth system") == True'))

            # Should be False for commands
            test2 = not su.is_objective_text("status")
            results.append(check(test2, 'is_objective_text("status") == False'))

            test3 = not su.is_objective_text("approve")
            results.append(check(test3, 'is_objective_text("approve") == False'))

        # Test extract_objective_text
        if has_extract_objective:
            test4 = su.extract_objective_text('"Test objective"') == "Test objective"
            results.append(check(test4, 'extract_objective_text() removes quotes'))
    else:
        results.append(check(False, "state_utils module not loaded"))

    # =========================================================================
    # SECTION 4: Edge Skill Hook Integration
    # =========================================================================
    print(f"\n{BOLD}[4/5] EDGE SKILL HOOK INTEGRATION{RESET}")

    if "edge_skill_hook" in imported_modules:
        esh = imported_modules["edge_skill_hook"]

        # Check parse_edge_args
        has_parse = hasattr(esh, "parse_edge_args")
        results.append(check(has_parse, "parse_edge_args() exists"))

        if has_parse:
            # Test objective routing
            result = esh.parse_edge_args('/edge "Deploy auth"')
            routes_correctly = result.get("command") == "run" and "Deploy" in result.get("args", "")
            results.append(check(routes_correctly, '/edge "objective" routes to run command'))

        # Check handle_new_objective exists
        has_handle_new = hasattr(esh, "handle_new_objective")
        results.append(check(has_handle_new, "handle_new_objective() exists"))

        # Check handle_run accepts args
        has_handle_run = hasattr(esh, "handle_run")
        if has_handle_run:
            import inspect
            sig = inspect.signature(esh.handle_run)
            has_args_param = "args" in sig.parameters
            results.append(check(has_args_param, "handle_run(args) accepts args parameter"))
    else:
        results.append(check(False, "edge_skill_hook module not loaded"))

    # =========================================================================
    # SECTION 5: Understanding-First Architecture (v5.3)
    # =========================================================================
    print(f"\n{BOLD}[5/5] UNDERSTANDING-FIRST ARCHITECTURE (v5.3){RESET}")

    if "state_utils" in imported_modules:
        su = imported_modules["state_utils"]

        # Check intent functions
        has_get_intent = hasattr(su, "get_intent")
        results.append(check(has_get_intent, "get_intent() exists"))

        has_is_confirmed = hasattr(su, "is_intent_confirmed")
        results.append(check(has_is_confirmed, "is_intent_confirmed() exists"))

    if "verification_utils" in imported_modules:
        vu = imported_modules["verification_utils"]

        has_build_prompt = hasattr(vu, "build_verification_prompt")
        results.append(check(has_build_prompt, "build_verification_prompt() exists"))

        has_should_subagent = hasattr(vu, "should_use_subagent_verification")
        results.append(check(has_should_subagent, "should_use_subagent_verification() exists"))

    # =========================================================================
    # SUMMARY
    # =========================================================================
    print(f"\n{BOLD}{'=' * 60}")
    print("VALIDATION SUMMARY")
    print("=" * 60 + RESET)

    passed = sum(results)
    total = len(results)

    if passed == total:
        print(f"\n  {GREEN}{BOLD}ALL {total} TESTS PASSED ✓{RESET}")
        print(f"\n  Operator's Edge v6.0 is correctly installed!")
        print(f"  The 'just works' objective flow is ready:")
        print(f"    /edge \"Your objective here\"")
        return 0
    else:
        failed = total - passed
        print(f"\n  {RED}{BOLD}{failed} of {total} TESTS FAILED ✗{RESET}")
        print(f"\n  Your installation may be incomplete or outdated.")
        print(f"  Re-extract the v6.0 zip and try again.")
        return 1


if __name__ == "__main__":
    sys.exit(main())
