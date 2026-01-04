# Operator's Edge v2 - Rebuild Checklist

## Phase 1: Real Enforcement (Complete)
- [x] Create YAML state format with schema validation
- [x] Build unified pre_tool.py (risk gate + retry blocking + plan enforcement)
- [x] Build post_tool.py (automatic proof capture)
- [x] Build session_start.py (inject state + capture hash)
- [x] Rewrite stop_gate.py (hash verification + proof validation)
- [x] Create edge_utils.py shared module

## Phase 2: Configuration (Complete)
- [x] Update settings.json with new hook wiring
- [x] Simplify CLAUDE.md to reflect mechanical enforcement

## Phase 3: Cleanup (Complete)
- [x] Delete non-functional agents/ directory
- [x] Delete non-functional skills/ directory
- [x] Delete old hook scripts (risk_gate.py, stop_gate.sh)
- [x] Delete old commands (edge-task, edge-implement, edge-proof)
- [x] Delete active_context.md (replaced by .yaml)

## Phase 4: New Commands (Complete)
- [x] Create edge-plan.md
- [x] Create edge-step.md

## Phase 5: Testing (Complete)
- [x] Test session_start.py - displays state correctly
- [x] Test pre_tool.py - blocks dangerous commands
- [x] Test pre_tool.py - gates git push
- [x] Test pre_tool.py - requires plan for edits
- [x] Test stop_gate.py - blocks without state change
- [x] Test stop_gate.py - blocks without proof
- [x] Test stop_gate.py - approves with state change + proof

---

## Final File Structure

```
Operators Edge/
├── CLAUDE.md                     # Policy (what's enforced)
├── active_context.yaml           # State (YAML, validated)
├── checklist.md                  # This file
├── archive.md                    # Completed work
├── .proof/
│   ├── session_log.jsonl         # Auto-captured proof
│   └── latest.md                 # Human-readable summary
└── .claude/
    ├── settings.json             # Hook configuration
    ├── state/                    # Runtime state
    │   ├── session_id
    │   ├── session_start_hash
    │   └── failure_log.jsonl
    ├── hooks/
    │   ├── edge_utils.py         # Shared utilities
    │   ├── session_start.py      # SessionStart hook
    │   ├── pre_tool.py           # PreToolUse hook
    │   ├── post_tool.py          # PostToolUse hook
    │   └── stop_gate.py          # Stop hook
    └── commands/
        ├── edge-plan.md          # /edge-plan command
        └── edge-step.md          # /edge-step command
```

## What's Enforced vs Policy

| Behavior | Enforcement Level |
|----------|-------------------|
| No dangerous commands | HARD (pre_tool blocks) |
| No blind retries | HARD (failure log + blocking) |
| No edits without plan | SOFT (asks, doesn't block) |
| State must change | HARD (stop_gate blocks) |
| Proof must exist | HARD (stop_gate blocks) |
| Quality of work | POLICY ONLY |
