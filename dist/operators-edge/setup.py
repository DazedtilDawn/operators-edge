#!/usr/bin/env python3
"""
Operator's Edge - Setup Script
Run this in any Claude Code project to install enforcement hooks.

Usage:
    python setup.py          # Install in current directory
    python setup.py --check  # Verify Python works
"""
import json
import os
import platform
import shutil
import sys
from pathlib import Path

def get_python_command():
    """Detect the correct Python command for this platform."""
    if platform.system() == "Windows":
        # Windows: try 'python' first (standard), then 'py' (launcher)
        return "python"
    else:
        # Mac/Linux: use python3
        return "python3"

def get_project_dir_var():
    """Get the correct environment variable syntax for the platform."""
    if platform.system() == "Windows":
        # Windows CMD uses %VAR% syntax
        return "%CLAUDE_PROJECT_DIR%"
    else:
        # Mac/Linux bash uses $VAR syntax
        return "$CLAUDE_PROJECT_DIR"

def create_settings(project_dir: Path, python_cmd: str):
    """Create .claude/settings.json with correct Python command."""
    project_dir_var = get_project_dir_var()
    settings = {
        "permissions": {
            "allow": [
                "Bash(git status:*)",
                "Bash(git diff:*)",
                "Bash(git log:*)",
                "Bash(npm test:*)",
                "Bash(npm run:*)",
                "Bash(pytest:*)",
                "Bash(ls:*)",
                "Bash(cat:*)",
                "Bash(pwd:*)",
                "Bash(echo:*)",
                "Bash(mkdir:*)",
                "Bash(touch:*)"
            ],
            "deny": [
                "Read(./.env)",
                "Read(./.env.*)",
                "Read(./secrets/**)"
            ]
        },
        "hooks": {
            "UserPromptSubmit": [
                {
                    "matcher": "/edge-prune",
                    "hooks": [{
                        "type": "command",
                        "command": f'{python_cmd} "{project_dir_var}/.claude/hooks/prune_skill_hook.py"'
                    }]
                },
                {
                    "matcher": "/edge",
                    "hooks": [{
                        "type": "command",
                        "command": f'{python_cmd} "{project_dir_var}/.claude/hooks/edge_skill_hook.py"'
                    }]
                }
            ],
            "SessionStart": [{
                "matcher": "",
                "hooks": [{
                    "type": "command",
                    "command": f'{python_cmd} "{project_dir_var}/.claude/hooks/session_start.py"'
                }]
            }],
            "PreToolUse": [{
                "matcher": "Bash|Edit|Write|NotebookEdit",
                "hooks": [{
                    "type": "command",
                    "command": f'{python_cmd} "{project_dir_var}/.claude/hooks/pre_tool.py"'
                }]
            }],
            "PostToolUse": [{
                "matcher": "Bash|Edit|Write|Read|NotebookEdit",
                "hooks": [{
                    "type": "command",
                    "command": f'{python_cmd} "{project_dir_var}/.claude/hooks/post_tool.py"'
                }]
            }],
            "Stop": [{
                "matcher": "",
                "hooks": [{
                    "type": "command",
                    "command": f'{python_cmd} "{project_dir_var}/.claude/hooks/stop_gate.py"'
                }]
            }]
        }
    }

    settings_file = project_dir / ".claude" / "settings.json"
    with open(settings_file, "w") as f:
        json.dump(settings, f, indent=2)

    return settings_file

def create_active_context(project_dir: Path):
    """Create initial active_context.yaml."""
    content = '''# Operator's Edge - Active Context
# This file is mechanically validated. Structure matters.

# Current session (updated by session_start hook)
session:
  id: null
  started_at: null

# What are we trying to achieve?
objective: "Set your objective here"

# Current position in the plan
current_step: 0

# The plan - each step must have description, status, and proof
# Status: pending | in_progress | completed | blocked
plan: []

# Hard constraints - things that must not happen
constraints:
  - "No destructive operations without confirmation"
  - "No edits without a plan"
  - "All work must be provable"

# Known risks and how we're mitigating them
risks: []

# Lessons learned (carried forward between sessions)
lessons: []
'''
    context_file = project_dir / "active_context.yaml"
    if not context_file.exists():
        context_file.write_text(content)
        return context_file
    return None

def copy_hooks(source_dir: Path, project_dir: Path):
    """Copy hook files to project."""
    hooks_source = source_dir / ".claude" / "hooks"
    hooks_dest = project_dir / ".claude" / "hooks"
    hooks_dest.mkdir(parents=True, exist_ok=True)

    # Copy all .py files (v3.9.3 has 66 hook files including tests)
    copied = []
    for src in hooks_source.glob("*.py"):
        dst = hooks_dest / src.name
        shutil.copy2(src, dst)
        copied.append(src.name)

    return copied

def copy_commands(source_dir: Path, project_dir: Path):
    """Copy slash command files to project."""
    cmds_source = source_dir / ".claude" / "commands"
    cmds_dest = project_dir / ".claude" / "commands"
    cmds_dest.mkdir(parents=True, exist_ok=True)

    copied = []
    if cmds_source.exists():
        for cmd_file in cmds_source.glob("*.md"):
            dst = cmds_dest / cmd_file.name
            shutil.copy2(cmd_file, dst)
            copied.append(cmd_file.name)
    else:
        print(f"  WARNING: Commands source not found at {cmds_source}")

    return copied

def copy_claude_md(source_dir: Path, project_dir: Path):
    """Copy CLAUDE.md to project."""
    src = source_dir / "CLAUDE.md"
    dst = project_dir / "CLAUDE.md"
    if src.exists() and not dst.exists():
        shutil.copy2(src, dst)
        return dst
    return None

def check_python():
    """Verify Python is working correctly."""
    print(f"Python version: {sys.version}")
    print(f"Platform: {platform.system()} {platform.release()}")
    print(f"Executable: {sys.executable}")

    cmd = get_python_command()
    print(f"\nRecommended command for this platform: {cmd}")

    # Test that pathlib works
    try:
        p = Path.cwd()
        print(f"Working directory: {p}")
        print("\nPython installation looks good!")
        return True
    except Exception as e:
        print(f"\nError: {e}")
        return False

def verify_installation(project_dir: Path):
    """Verify all files were installed correctly."""
    print("\n" + "=" * 60)
    print("Verification")
    print("=" * 60)

    checks = [
        (".claude/settings.json", "Settings"),
        (".claude/hooks/edge_utils.py", "Hooks - edge_utils"),
        (".claude/hooks/session_start.py", "Hooks - session_start"),
        (".claude/hooks/pre_tool.py", "Hooks - pre_tool"),
        (".claude/hooks/post_tool.py", "Hooks - post_tool"),
        (".claude/hooks/stop_gate.py", "Hooks - stop_gate"),
        (".claude/hooks/discovery_scanner.py", "Hooks - discovery (v3.1)"),
        (".claude/hooks/clickup_utils.py", "Hooks - clickup (v3.2)"),
        (".claude/hooks/gear_engine.py", "Hooks - gear_engine (v3.7)"),
        (".claude/hooks/edge_skill_hook.py", "Hooks - edge_skill_hook (v3.8)"),
        (".claude/hooks/quality_gate.py", "Hooks - quality_gate (v3.9)"),
        (".claude/commands/edge.md", "Command - /edge"),
        (".claude/commands/edge-plan.md", "Command - /edge-plan"),
        (".claude/commands/edge-yolo.md", "Command - /edge-yolo"),
        ("active_context.yaml", "State file"),
        ("CLAUDE.md", "Instructions"),
    ]

    all_ok = True
    for path, name in checks:
        full_path = project_dir / path
        if full_path.exists():
            print(f"  OK: {name}")
        else:
            print(f"  MISSING: {name} ({path})")
            all_ok = False

    # Count total hooks
    hooks_dir = project_dir / ".claude" / "hooks"
    if hooks_dir.exists():
        hook_count = len(list(hooks_dir.glob("*.py")))
        print(f"\n  Total hooks: {hook_count} files")

    if all_ok:
        print("\nAll files installed correctly!")
        print("\nIMPORTANT: Restart Claude Code to load the new commands.")
    else:
        print("\nSome files are missing. Check the setup output above.")

    return all_ok

def main():
    if len(sys.argv) > 1 and sys.argv[1] == "--check":
        sys.exit(0 if check_python() else 1)

    if len(sys.argv) > 1 and sys.argv[1] == "--verify":
        project_dir = Path.cwd().resolve()
        sys.exit(0 if verify_installation(project_dir) else 1)

    # Determine directories
    script_dir = Path(__file__).parent.resolve()
    project_dir = Path.cwd().resolve()

    print("=" * 60)
    print("Operator's Edge - Setup")
    print("=" * 60)
    print(f"\nPlatform: {platform.system()}")
    print(f"Source:   {script_dir}")
    print(f"Target:   {project_dir}")

    # Detect Python command
    python_cmd = get_python_command()
    print(f"Python:   {python_cmd}")

    # Create directories
    (project_dir / ".claude" / "hooks").mkdir(parents=True, exist_ok=True)
    (project_dir / ".claude" / "state").mkdir(parents=True, exist_ok=True)
    (project_dir / ".proof").mkdir(parents=True, exist_ok=True)

    # Copy files
    print("\nInstalling...")

    hooks = copy_hooks(script_dir, project_dir)
    print(f"  Hooks: {len(hooks)} files")

    commands = copy_commands(script_dir, project_dir)
    print(f"  Commands: {len(commands)} files")

    settings_file = create_settings(project_dir, python_cmd)
    print(f"  Settings: {settings_file.name}")

    context_file = create_active_context(project_dir)
    if context_file:
        print(f"  Context: {context_file.name}")
    else:
        print("  Context: (already exists, skipped)")

    claude_md = copy_claude_md(script_dir, project_dir)
    if claude_md:
        print(f"  Docs: CLAUDE.md")

    # Run verification
    verify_installation(project_dir)

    print("\n" + "=" * 60)
    print("Next steps:")
    print("=" * 60)
    print("1. RESTART Claude Code (required to load commands)")
    print("2. Edit active_context.yaml to set your objective")
    print("3. Run /edge-plan to create your plan")
    print("\nTo verify installation later:")
    print(f"  python {Path(__file__).name} --verify")

if __name__ == "__main__":
    main()
