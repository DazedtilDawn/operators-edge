# Installing Operator's Edge v8.0 in Any Claude Code Project

## Quick Start (30 seconds)

```bash
# 1. Copy the operators-edge folder to your project
cp -r operators-edge /path/to/your/project/

# 2. Navigate to your project
cd /path/to/your/project/operators-edge

# 3. Run setup
python setup.py
```

That's it! Start Claude Code in your project and use `/edge`.

---

## What's New in v8.0: Context Engineering

v8.0 is a strategic pivot: **keep Claude on track** instead of teaching patterns.

### New Capabilities

1. **Drift Detection** - Warns when Claude is spinning (file churn, command repeats)
2. **Context Monitor** - Tracks token usage, warns at 75%+, suggests checkpoints
3. **Codebase Knowledge** - Remembers what fixed errors before
4. **Session Handoffs** - Passes context between sessions automatically
5. **Smart Suggestions** - Proactive guidance, not just reactive warnings
6. **Effectiveness Metrics** - `/edge metrics` shows what's actually helping
7. **Active Intervention** - Escalating warnings when session goes off-track
8. **Outcome Tracking** - Learns which fixes actually work

### Quick Commands

```bash
/edge metrics           # See effectiveness report
/edge metrics --tune    # Auto-adjust thresholds
```

---

## What Gets Installed

```
your-project/
├── .claude/
│   ├── settings.json      # Hook configuration (created by setup.py)
│   ├── commands/          # Slash commands (/edge, /edge-plan, etc.)
│   └── hooks/             # Python enforcement hooks (v8.0 modules included)
├── .proof/                # Metrics data (created on first use)
│   ├── sessions/          # Session logs
│   ├── knowledge.json     # Known fixes database
│   └── fix_outcomes.jsonl # Fix success tracking
├── CLAUDE.md              # Instructions Claude reads on startup
├── active_context.yaml    # Your plan and state (created on first use)
└── CHANGELOG.md           # Version history
```

---

## Installation Options

### Option A: Copy Entire Folder (Recommended)

Best for: New projects or when you want full control

```bash
# Copy to your project root
cp -r operators-edge/* /path/to/your/project/

# Run setup
cd /path/to/your/project
python setup.py
```

### Option B: Upgrade Existing Installation

Best for: Updating from v6.x/v7.x to v8.0

```bash
# Backup your current state
cp active_context.yaml active_context.yaml.bak

# Copy new files
cp -r new-operators-edge/.claude/* your-project/.claude/
cp new-operators-edge/CLAUDE.md your-project/
cp new-operators-edge/CHANGELOG.md your-project/

# Re-run setup
python setup.py

# Your .proof/ data and active_context.yaml are preserved
```

### Windows-Specific Upgrade

```powershell
# PowerShell commands
Copy-Item -Recurse -Force .\operators-edge\.claude\* .\your-project\.claude\
Copy-Item .\operators-edge\CLAUDE.md .\your-project\
Copy-Item .\operators-edge\CHANGELOG.md .\your-project\
python setup.py
```

---

## Platform Notes

### Windows
- Uses `python` command
- Paths use backslashes internally but setup.py handles this
- Works with Python 3.8+

### Mac/Linux
- Uses `python3` command
- Standard Unix paths

The setup.py auto-detects your platform and configures hooks correctly.

---

## Verify Installation

```bash
# Run v8 module tests
cd .claude/hooks
python -m unittest test_drift_detector test_fix_outcomes -v

# Expected: All tests pass
```

---

## Using Operator's Edge

Once installed, start Claude Code and use:

```bash
# The "just works" way
/edge "Build a login system"

# Check effectiveness
/edge metrics

# Classic commands
/edge-plan          # Create a plan
/edge-step          # Execute current step
/edge-yolo on       # Enable autopilot
/edge               # Smart orchestrator
```

### v8.0 Features in Action

When Claude encounters an error it's seen before:
```
╭─ KNOWN FIX AVAILABLE ─────────────────────────╮
│ This error was fixed before (confidence: 82%) │
│                                                │
│ Try: pip install requests                      │
╰────────────────────────────────────────────────╯
```

When Claude is editing the same file repeatedly:
```
⚠️ FILE_CHURN: src/app.py edited 4 times this session
   Consider: Step back and review your approach
```

When context is running low:
```
📊 Context Usage: 78% (warning threshold)
   Suggestion: Consider creating a checkpoint
```

---

## Updating

To update an existing installation:

```bash
# Pull latest (if using git)
git pull origin main

# Or re-copy from new version
cp -r new-operators-edge/.claude/* your-project/.claude/
cp new-operators-edge/CLAUDE.md your-project/
cp new-operators-edge/CHANGELOG.md your-project/

# Re-run setup to update settings.json
python setup.py

# Your .proof/ metrics data is preserved
```

---

## Uninstalling

```bash
# Remove Edge files (preserves your code)
rm -rf .claude/hooks .claude/commands
rm CLAUDE.md active_context.yaml CHANGELOG.md
rm -rf .proof

# Keep .claude/settings.json if you have other customizations
# Or remove it too: rm .claude/settings.json
```

---

## Troubleshooting

### "Python not found"
- Windows: Install Python from python.org, ensure "Add to PATH" is checked
- Mac: `brew install python3` or use system Python

### "Hook not firing"
- Check `.claude/settings.json` exists and has hooks configured
- Run `python setup.py` again

### "Permission denied"
- Mac/Linux: `chmod +x .claude/hooks/*.py`

### "Module not found"
- All hooks are self-contained, no pip install needed
- Check that `.claude/hooks/` contains all .py files

### v8.0 Metrics Not Working
- Ensure `.proof/` directory exists (created on first use)
- Try `/edge metrics --detailed` for debugging info

---

## Support

- GitHub: https://github.com/DazedtilDawn/operators-edge
- Issues: https://github.com/DazedtilDawn/operators-edge/issues
- CHANGELOG: See CHANGELOG.md for full version history
