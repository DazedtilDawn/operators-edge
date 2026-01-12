# Operator's Edge: Platform Comparison

A comprehensive comparison of Operator's Edge running on Claude Code vs Codex CLI.

## Executive Summary

| Aspect | Claude Code | Codex CLI |
|--------|-------------|-----------|
| Enforcement model | Hard (hooks block actions) | Soft (guidance suggests) |
| Context injection | Automatic (UserPromptSubmit hook) | Automatic (AGENTS.md) |
| Proof capture | Automatic (PostToolUse hook) | Manual (skill invocation) |
| Session validation | Automatic (Stop hook) | Manual (`$edge-done`) |
| Skill invocation | `/slash-command` | `$skill-name` |
| Reliability | 100% enforcement | ~80% (depends on compliance) |

## Architecture Comparison

### Claude Code Architecture

```
┌─────────────────────────────────────────────┐
│                Claude Code                   │
├─────────────────────────────────────────────┤
│  Hooks (Mechanical Enforcement)              │
│  ├── UserPromptSubmit → inject context       │
│  ├── PreToolUse → block edits without plan   │
│  ├── PostToolUse → log proof automatically   │
│  └── Stop → validate before session end      │
├─────────────────────────────────────────────┤
│  Commands (User-Triggered Skills)            │
│  ├── /edge → smart orchestrator              │
│  ├── /edge-plan → create plan                │
│  └── /edge-step → execute step               │
├─────────────────────────────────────────────┤
│  State Files                                 │
│  ├── active_context.yaml → plan + memory     │
│  └── .proof/session_log.jsonl → evidence     │
└─────────────────────────────────────────────┘
```

### Codex CLI Architecture

```
┌─────────────────────────────────────────────┐
│                 Codex CLI                    │
├─────────────────────────────────────────────┤
│  AGENTS.md (Soft Guidance)                   │
│  └── Loaded at session start                 │
│      Behavioral suggestions, not enforcement │
├─────────────────────────────────────────────┤
│  Skills (User-Triggered Commands)            │
│  ├── $edge-context → load context            │
│  ├── $edge-plan → create plan                │
│  ├── $edge-step → execute step               │
│  ├── $edge-log → manual proof logging        │
│  ├── $edge-score → self-assessment           │
│  └── $edge-done → session validation         │
├─────────────────────────────────────────────┤
│  State Files (Identical)                     │
│  ├── active_context.yaml → plan + memory     │
│  └── .proof/session_log.jsonl → evidence     │
└─────────────────────────────────────────────┘
```

## Feature-by-Feature Comparison

### 1. Context Injection

**Claude Code**:
- UserPromptSubmit hook runs on every user message
- Automatically injects current state, objective, and relevant lessons
- Cannot be bypassed

**Codex CLI**:
- AGENTS.md is loaded at session start
- Contains behavioral guidance, not live state
- `$edge-context` skill must be invoked for live state
- Implicit invocation may trigger on "starting any coding task"

**Trade-off**: Codex requires user discipline or relies on implicit invocation.

### 2. Edit Blocking

**Claude Code**:
- PreToolUse hook checks for plan before Edit/Write
- Hard block: edit literally cannot happen without plan
- Dangerous commands (rm -rf, git reset --hard) are blocked

**Codex CLI**:
- AGENTS.md suggests checking for plan before editing
- Soft guidance: Codex may still allow the edit
- Dangerous command warnings but no hard blocks

**Trade-off**: Codex sacrifices enforcement for user freedom.

### 3. Proof Capture

**Claude Code**:
- PostToolUse hook logs every tool invocation automatically
- No user action required
- Complete audit trail

**Codex CLI**:
- `$edge-log` skill must be invoked manually
- User must remember to log after significant actions
- Incomplete audit trail if user forgets

**Trade-off**: Codex requires manual discipline for proof.

### 4. Session End Validation

**Claude Code**:
- Stop hook blocks session end if no state change or proof
- Enforces completeness automatically

**Codex CLI**:
- `$edge-done` skill provides voluntary validation
- User can end session without running it
- No enforcement, only validation

**Trade-off**: Codex trusts users to validate their own sessions.

### 5. Retry Prevention

**Claude Code**:
- PreToolUse hook tracks command failures
- Blocks identical commands that failed twice
- Forces approach change

**Codex CLI**:
- AGENTS.md guidance suggests changing approach on failure
- No mechanical prevention of retry loops
- User must self-regulate

**Trade-off**: Codex relies on user awareness to avoid retry loops.

## When to Use Each Platform

### Choose Claude Code When:
- **Enforcement is critical**: You need guarantees, not suggestions
- **Audit trails matter**: Proof must be captured automatically
- **New users**: Learning the workflow needs guardrails
- **Production workflows**: Can't risk skipping steps

### Choose Codex CLI When:
- **Flexibility is valued**: You want suggestions, not blocks
- **Experienced users**: Already internalized the workflow
- **Speed matters**: Less friction in the process
- **OpenAI ecosystem**: Already using Codex for other work

## Migration Guide

### From Claude Code to Codex CLI

1. **Copy files**:
   ```bash
   cp -r codex/AGENTS.md codex/skills/ your-project/
   cp active_context.yaml your-project/
   ```

2. **Adjust workflow**:
   - Start sessions with `$edge-context` (or trust implicit invocation)
   - Log proof manually with `$edge-log` after major actions
   - Validate sessions with `$edge-done` before ending

3. **Accept trade-offs**:
   - Edits may happen without plans (your discipline prevents this)
   - Proof may be incomplete (your logging prevents this)
   - Sessions may end without validation (your discipline prevents this)

### From Codex CLI to Claude Code

1. **Copy hooks**:
   ```bash
   cp -r .claude/hooks/ your-project/.claude/
   cp -r .claude/commands/ your-project/.claude/
   ```

2. **Install hooks**: Follow Claude Code hook installation

3. **Expect enforcement**:
   - Edits will be blocked without plans (create plans first)
   - Sessions can't end without state changes (do real work)
   - Commands that fail twice can't be retried (change approach)

## Quantified Comparison

| Metric | Claude Code | Codex CLI | Notes |
|--------|-------------|-----------|-------|
| Setup complexity | Medium | Low | Hooks require more setup |
| Enforcement reliability | 100% | ~80% | Depends on user compliance |
| Proof completeness | 100% | ~60-80% | Depends on manual logging |
| Workflow friction | Medium | Low | Fewer blocks means faster |
| Learning curve | Steeper | Gentler | Enforcement teaches, but blocks |
| Portability | Claude Code only | OpenAI only | Platform lock-in |

## Shared Components

These work identically on both platforms:

1. **active_context.yaml schema**: Identical structure
2. **Plan format**: Same YAML format for steps
3. **Memory system**: Same trigger-based lessons
4. **6-check rubric**: Same self-assessment
5. **Three Gears mode**: Same ACTIVE/PATROL/DREAM logic

## Future Improvements

### For Codex CLI version:
1. **Implicit skill chaining**: `$edge-step` could auto-invoke `$edge-log`
2. **Session reminders**: AGENTS.md could prompt for `$edge-done` at idle
3. **Stricter guidance**: Stronger language in AGENTS.md

### For both platforms:
1. **Shared core library**: Python package usable by both
2. **State sync**: Sync active_context.yaml between platforms
3. **Cross-platform testing**: Verify identical behavior

## Conclusion

Claude Code offers **reliability through enforcement** - the system prevents mistakes.

Codex CLI offers **flexibility through guidance** - the user prevents mistakes.

Choose based on your needs: trust the system or trust yourself.
