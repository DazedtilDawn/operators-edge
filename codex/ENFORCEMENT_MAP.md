# Enforcement Mapping: Claude Code → Codex CLI

## Hook-to-Guidance Equivalents

| Claude Code Hook | Enforcement | Codex CLI Equivalent | Mechanism |
|------------------|-------------|---------------------|-----------|
| `PreToolUse` | Blocks edits without plan | AGENTS.md "Before ANY Edit" section | Behavioral guidance |
| `PreToolUse` | Blocks dangerous commands | AGENTS.md "Dangerous Commands" section | Awareness + confirmation |
| `PreToolUse` | Blocks blind retries | AGENTS.md "Failed Commands" section | Self-discipline |
| `PostToolUse` | Logs all tool use | `$edge-step` skill | Manual invocation |
| `Stop` | Blocks stop without state change | `$edge-done` skill | Voluntary validation |
| `UserPromptSubmit` | Injects context at session start | `$edge-context` skill | Explicit invocation |
| `UserPromptSubmit` | Runs gear engine | `$edge-context` skill | Embedded in skill |

## Enforcement Strength Comparison

```
HARD ENFORCEMENT (Claude Code)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
│ Hook intercepts request → Validates → BLOCKS if invalid │
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

SOFT ENFORCEMENT (Codex CLI)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
│ AGENTS.md loaded → Model reads guidelines → CHOOSES to follow │
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
```

## What's Lost

| Feature | Claude Code | Codex CLI | Impact |
|---------|-------------|-----------|--------|
| Guaranteed blocking | Yes | No | Model may ignore guidelines |
| Automatic logging | Yes | No | Must manually invoke skills |
| Session gating | Yes | No | Session can end without validation |

## What's Preserved

| Feature | How |
|---------|-----|
| Workflow discipline | AGENTS.md guidance |
| State management | Same `active_context.yaml` schema |
| Memory system | Same memory format in state file |
| Skills/commands | Ported to SKILL.md format |
| Planning structure | Same step-by-step approach |
| Self-assessment | Same 6-check rubric |

## Confidence Levels

| Enforcement Type | Compliance Confidence |
|------------------|----------------------|
| Hard blocking (hooks) | 100% - physically prevented |
| Strong guidance (AGENTS.md) | 95% - model follows well-written guidance |
| Weak guidance (comments) | 70% - may be ignored under pressure |
| No guidance | 50% - model uses general training |

**Target: AGENTS.md should achieve 95%+ compliance through clear, compelling guidance.**

## Design Principles for Soft Enforcement

1. **Be specific** - "Check active_context.yaml" not "follow the rules"
2. **Explain why** - Motivation increases compliance
3. **Provide alternatives** - "If X fails, do Y" not just "don't do X"
4. **Reference skills** - Point to specific tools, not abstract concepts
5. **Use tables** - Structured info is easier to follow than prose
