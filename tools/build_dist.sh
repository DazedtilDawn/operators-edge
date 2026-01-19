#!/bin/bash
#
# Operator's Edge - Build Distribution
#
# Syncs canonical source (.claude/hooks/) to distribution (dist/operators-edge/).
# Run this after making changes to create a distributable package.
#
# Usage:
#   ./tools/build_dist.sh        # Sync hooks to dist
#   ./tools/build_dist.sh --dry  # Show what would be copied
#

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"

SOURCE_HOOKS="$PROJECT_ROOT/.claude/hooks"
DIST_HOOKS="$PROJECT_ROOT/dist/operators-edge/.claude/hooks"

SOURCE_COMMANDS="$PROJECT_ROOT/.claude/commands"
DIST_COMMANDS="$PROJECT_ROOT/dist/operators-edge/.claude/commands"

DRY_RUN=false
if [[ "$1" == "--dry" ]]; then
    DRY_RUN=true
    echo "=== DRY RUN - showing what would be copied ==="
    echo ""
fi

# Ensure dist directories exist
mkdir -p "$DIST_HOOKS"
mkdir -p "$DIST_COMMANDS"

echo "Building Operator's Edge distribution..."
echo "  Source: $SOURCE_HOOKS"
echo "  Dest:   $DIST_HOOKS"
echo ""

# Sync hooks (Python files only, exclude tests and state)
echo "=== Syncing hooks ==="
for f in "$SOURCE_HOOKS"/*.py; do
    filename=$(basename "$f")
    
    # Skip test files in distribution (they're for development)
    if [[ "$filename" == test_* ]]; then
        continue
    fi
    
    if $DRY_RUN; then
        echo "  Would copy: $filename"
    else
        cp "$f" "$DIST_HOOKS/$filename"
        echo "  Copied: $filename"
    fi
done

# Sync commands (markdown files)
echo ""
echo "=== Syncing commands ==="
for f in "$SOURCE_COMMANDS"/*.md; do
    if [[ -f "$f" ]]; then
        filename=$(basename "$f")
        if $DRY_RUN; then
            echo "  Would copy: $filename"
        else
            cp "$f" "$DIST_COMMANDS/$filename"
            echo "  Copied: $filename"
        fi
    fi
done

# Count files
echo ""
echo "=== Summary ==="
hooks_count=$(ls -1 "$SOURCE_HOOKS"/*.py 2>/dev/null | grep -v test_ | wc -l | tr -d ' ')
commands_count=$(ls -1 "$SOURCE_COMMANDS"/*.md 2>/dev/null | wc -l | tr -d ' ')

if $DRY_RUN; then
    echo "Would sync $hooks_count hooks and $commands_count commands"
else
    echo "Synced $hooks_count hooks and $commands_count commands to dist/"
    echo ""
    echo "Distribution ready at: dist/operators-edge/"
fi
