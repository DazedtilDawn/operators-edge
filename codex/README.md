# Operator's Edge for Codex CLI

A workflow system that brings structured planning, proof capture, and adaptive learning to OpenAI's Codex CLI.

## Quick Start

1. **Install global skills** (required):
   ```bash
   cp -r codex/skills/* ~/.codex/skills/
   ```
   Then restart Codex CLI to load updated skills.

2. **Copy context to your project**:
   ```bash
   cp -r codex/* your-project/
   ```

3. **Create state file**:
   ```bash
   cat > active_context.yaml << 'EOF'
   objective: null
   current_step: 0
   plan: []
   constraints: []
   memory: []
   EOF
   ```

4. **Start Codex CLI** in your project directory

5. **Begin work**:
   ```
   Let's work on [your objective]
   ```
   The edge-context skill should trigger automatically.

## Windows Install (Quick)

```cmd
cd C:\path\to\your\project
python C:\path\to\operators-edge\setup.py
```

**Verify (Windows)**
1. Check `.claude\settings.json` exists.
2. Confirm `.claude\hooks\` and `.claude\commands\` were created.
3. Run `/edge-context` after restarting Codex CLI.

## Skills

| Skill | Description | When to Use |
|-------|-------------|-------------|
| `$edge-context` | Load project state and context | Session start (often implicit) |
| `$edge-plan` | Create or update implementation plan | Before starting work |
| `$edge-step` | Execute current step in plan | During work |
| `$edge-log` | Record proof of completed work | After significant actions |
| `$edge-verify` | Run quality checks | Before marking done |
| `$edge-loop` | Generate proof visualization | End of session (if tools exist) |
| `$edge-score` | Self-assess adaptive behavior | After completing work |
| `$edge-done` | Validate session completion | Before ending session |
| `$edge-eval` | Run eval snapshots/checks/reports | When evals are enabled or on demand |

## Workflow

```
Session Start                    During Work                    Session End
     │                                │                              │
     ▼                                ▼                              ▼
$edge-context ──► $edge-plan ──► $edge-step ──► $edge-log ──► $edge-done
     │                 │              │              │              │
     │                 │              │              │              │
  Load state      Create plan    Execute work   Record proof   Validate

## Release / Dist Sync

`dist/operators-edge` is generated from source and should not be edited directly.

Before releasing or distributing:

```bash
# 1) Check for drift (fails if dist differs from source)
python3 tools/build_dist.py --check

# 2) Regenerate dist if needed
python3 tools/build_dist.py
```

If `--check` reports mismatches, re-run the build and re-check.

## Files

```
~/.codex/skills/               # Global skills (execution source)
├── edge-context/SKILL.md
├── edge-plan/SKILL.md
├── edge-step/SKILL.md
├── edge-log/SKILL.md
├── edge-verify/SKILL.md
├── edge-loop/SKILL.md
├── edge-score/SKILL.md
├── edge-done/SKILL.md
└── edge-eval/SKILL.md

your-project/
├── AGENTS.md                  # Session guidance (auto-loaded)
├── active_context.yaml        # State file (your plan + memory)
├── tools/                     # Optional scripts (edge_guard, edge_run, edge_start/end)
├── .proof/
│   └── session_log.jsonl      # Audit trail (created as needed)
└── (documentation)
    ├── ENFORCEMENT_MAP.md     # How hooks map to guidance
    ├── PLATFORM_COMPARISON.md # Claude Code vs Codex CLI
    └── TEST_PLAN.md           # Testing checklist
```

## Key Differences from Claude Code

| Feature | Claude Code | Codex CLI |
|---------|-------------|-----------|
| Edit blocking | Hard enforcement | Soft guidance |
| Proof capture | Automatic | Manual (`$edge-log`) |
| Session validation | Required | Voluntary (`$edge-done`) |
| Context injection | Hook | AGENTS.md |

See [PLATFORM_COMPARISON.md](PLATFORM_COMPARISON.md) for full details.

## Three Gears Mode

The system operates in three modes based on state:

| Gear | Condition | Behavior |
|------|-----------|----------|
| **ACTIVE** | Has objective + pending steps | Execute work |
| **PATROL** | Plan complete, reviewing | Validate, suggest |
| **DREAM** | No objective | Explore, brainstorm |

## Tips

1. **Start with context**: Run `$edge-context` if it doesn't trigger automatically
2. **Plan before editing**: The system works best with upfront planning
3. **Log as you go**: Run `$edge-log` after significant actions
4. **Validate before ending**: Run `$edge-done` before closing Codex

## Troubleshooting

### Skills not recognized
- Ensure `skills/` directory is in project root
- Check SKILL.md has valid YAML frontmatter
- Restart Codex CLI

### State not loading
- Verify `active_context.yaml` is valid YAML
- Run `$edge-context` explicitly

### Proof not captured
- Ensure `.proof/` directory exists
- Run `$edge-log` after completing work

## License

Same as parent Operator's Edge project.
