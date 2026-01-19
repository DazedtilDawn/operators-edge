#!/bin/bash
# Operator's Edge v8.0 - Mac/Linux Upgrade Script
# Run this from the extracted operators-edge folder

set -e

usage() {
    cat << EOF

Operator's Edge v8.0 - Upgrade Script
======================================

USAGE:
  ./upgrade.sh /path/to/your/project

WHAT IT DOES:
  1. Backs up your active_context.yaml
  2. Copies v8.0 hooks to .claude/hooks/
  3. Updates commands in .claude/commands/
  4. Preserves your .proof/ metrics data
  5. Runs setup.py to update settings.json

EXAMPLES:
  ./upgrade.sh ~/Projects/MyProject
  ./upgrade.sh .   # Current directory

NEW IN v8.0:
  - Drift Detection (warns when Claude is spinning)
  - Context Monitor (tracks token usage)
  - Codebase Knowledge (remembers what fixed errors)
  - Session Handoffs (passes context between sessions)
  - Effectiveness Metrics (/edge metrics)
  - Outcome Tracking (learns which fixes work)

EOF
}

if [ -z "$1" ] || [ "$1" == "-h" ] || [ "$1" == "--help" ]; then
    usage
    exit 0
fi

SOURCE_DIR="$(cd "$(dirname "$0")" && pwd)"
TARGET_DIR="$(cd "$1" && pwd)"

echo "========================================"
echo " Operator's Edge v8.0 Upgrade"
echo "========================================"
echo ""
echo "Source: $SOURCE_DIR"
echo "Target: $TARGET_DIR"
echo ""

# Verify source has hooks
if [ ! -d "$SOURCE_DIR/.claude/hooks" ]; then
    echo "ERROR: Source does not contain .claude/hooks"
    exit 1
fi

# Verify target exists
if [ ! -d "$TARGET_DIR" ]; then
    echo "ERROR: Target project does not exist: $TARGET_DIR"
    exit 1
fi

# Backup active_context.yaml if exists
if [ -f "$TARGET_DIR/active_context.yaml" ]; then
    echo "[1/5] Backing up active_context.yaml..."
    cp "$TARGET_DIR/active_context.yaml" "$TARGET_DIR/active_context.yaml.pre-v8.bak"
    echo "      Saved to: active_context.yaml.pre-v8.bak"
else
    echo "[1/5] No active_context.yaml to backup"
fi

# Create target directories
echo "[2/5] Creating directories..."
mkdir -p "$TARGET_DIR/.claude/hooks"
mkdir -p "$TARGET_DIR/.claude/commands"
echo "      .claude/hooks/ and .claude/commands/ ready"

# Copy hooks
echo "[3/5] Copying v8.0 hooks..."
cp -r "$SOURCE_DIR/.claude/hooks/"* "$TARGET_DIR/.claude/hooks/"
HOOK_COUNT=$(ls "$TARGET_DIR/.claude/hooks/"*.py 2>/dev/null | wc -l)
echo "      Copied $HOOK_COUNT Python modules"

# Copy commands
echo "[4/5] Copying commands..."
cp -r "$SOURCE_DIR/.claude/commands/"* "$TARGET_DIR/.claude/commands/"
CMD_COUNT=$(ls "$TARGET_DIR/.claude/commands/"*.md 2>/dev/null | wc -l)
echo "      Copied $CMD_COUNT slash commands"

# Copy CLAUDE.md and CHANGELOG.md
cp "$SOURCE_DIR/CLAUDE.md" "$TARGET_DIR/" 2>/dev/null || true
cp "$SOURCE_DIR/CHANGELOG.md" "$TARGET_DIR/" 2>/dev/null || true
echo "      Copied CLAUDE.md and CHANGELOG.md"

# Run setup.py
echo "[5/5] Running setup.py..."
cd "$TARGET_DIR"
if [ -f "setup.py" ]; then
    python3 setup.py || python setup.py || echo "      WARNING: setup.py failed"
    echo "      Settings configured"
else
    echo "      WARNING: setup.py not found"
fi

echo ""
echo "========================================"
echo " Upgrade Complete!"
echo "========================================"
echo ""
echo "Your .proof/ data and active_context.yaml are preserved."
echo ""
echo "Next steps:"
echo "  1. Open Claude Code in your project"
echo "  2. Try: /edge metrics  (see effectiveness report)"
echo "  3. Try: /edge \"your objective\""
echo ""
echo "v8.0 Features now active:"
echo "  - Drift Detection (warns on file churn, command repeats)"
echo "  - Context Monitor (warns at 75%+ token usage)"
echo "  - Codebase Knowledge (remembers what fixed errors)"
echo "  - Outcome Tracking (learns which fixes actually work)"
echo ""
