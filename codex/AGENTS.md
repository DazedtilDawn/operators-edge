# Operator's Edge - Codex CLI Edition

This project uses Operator's Edge for structured workflow management.

## Global Skills + Project Context

Skills are loaded from `~/.codex/skills`. This project supplies the local context
(`AGENTS.md`, `active_context.yaml`, `tools/`, docs). If you update global skills,
restart Codex CLI to load the changes.

## CRITICAL BEHAVIORAL GUIDELINES

These guidelines replace mechanical enforcement. Follow them as if they were unbreakable rules.

### Before ANY Edit or Write Operation

**STOP. Check `active_context.yaml` first.**

1. Does `objective` have a clear goal? If empty or "null", run `$edge-plan` first.
2. Does `plan` have at least one step? If `[]`, run `$edge-plan` first.
3. Is there a step with `status: in_progress`? If not, run `$edge-step` first.

**If any check fails: DO NOT proceed with the edit. Plan first.**

**Exception (allowed writes):** Updates to `active_context.yaml` and `.proof/session_log.jsonl`
that occur as part of `$edge-context`, `$edge-plan`, `$edge-step`, `$edge-log`,
`$edge-verify`, or `$edge-done` are permitted.

### Dangerous Commands - NEVER Execute Without Explicit Approval

These commands are irreversible. Always ask for confirmation:

| Command Pattern | Risk Level | Required Action |
|-----------------|------------|-----------------|
| `rm -rf`, `rm -r` | CRITICAL | Ask user explicitly |
| `git reset --hard` | CRITICAL | Ask user explicitly |
| `git push --force` | CRITICAL | Ask user explicitly |
| `DROP TABLE`, `DELETE FROM` | CRITICAL | Ask user explicitly |
| Any `--force` flag | HIGH | Explain consequences first |

### Failed Commands - No Blind Retries

If a command fails:
1. **DO NOT** immediately retry the same command
2. **DO** analyze why it failed
3. **DO** try a different approach or ask for clarification
4. If stuck after 2 attempts, escalate to user

### Session Discipline

**Before ending work:**
1. Ensure `active_context.yaml` reflects current progress
2. Mark completed steps as `status: completed`
3. Add any learned lessons to `memory` section
4. Run `$edge-done` to validate state

## State File: `active_context.yaml`

This is the source of truth. It contains:

```yaml
objective: "What you're trying to achieve"
current_step: 1
plan:
  - description: "Step description"
    status: pending | in_progress | completed | blocked
    proof: null | "evidence of completion"
constraints:
  - "Things that must NOT happen"
memory:
  - trigger: "keyword"
    lesson: "What you learned"
```

## Available Skills

Use these skills to maintain workflow discipline:

| Skill | When to Use |
|-------|-------------|
| `$edge-plan` | Create or update the plan for a new objective |
| `$edge-step` | Execute the current step from the plan |
| `$edge-log` | Record proof of completed work |
| `$edge-verify` | Run quality checks before marking done |
| `$edge-loop` | Generate proof visualization (if tools/edge_loop.sh exists) |
| `$edge-score` | Self-assess work quality against the 6-check rubric |
| `$edge-done` | Validate state before ending session |
| `$edge-context` | Load current state and get oriented |

## Workflow

1. **Start**: Run `$edge-context` to load current state
2. **Plan**: If no plan exists, run `$edge-plan` with user's objective
3. **Execute**: Run `$edge-step` to work on current step (then `$edge-log`)
4. **Verify**: Run `$edge-verify` (optional) or `$edge-loop` if available
5. **End**: Run `$edge-done` to validate before stopping

## Memory System

The `memory` section in `active_context.yaml` contains lessons learned:

```yaml
memory:
  - trigger: "hooks"
    lesson: "Policy is not enforcement - hooks are enforcement"
    reinforced: 4
```

**Before starting work**, scan memory for relevant lessons based on the task keywords.

## Self-Assessment (6-Check Rubric)

After completing significant work, evaluate against these checks:

| Check | Question |
|-------|----------|
| **Mismatch Detection** | Did I notice when reality differed from expectations? |
| **Plan Revision** | Did I update the plan when things changed? |
| **Tool Switching** | Did I switch approaches when tools failed? |
| **Memory Update** | Did I capture lessons learned? |
| **Proof Generation** | Did I provide evidence of completion? |
| **Stop Condition** | Did I ask clarifying questions when uncertain? |

Score yourself 0-6. A score of 5+ indicates strong adaptive behavior.

## Key Differences from Claude Code Version

| Aspect | Claude Code | Codex CLI |
|--------|-------------|-----------|
| Edit blocking | Hard block (PreToolUse hook) | Behavioral guidance (this file) |
| Proof capture | Automatic (PostToolUse hook) | Manual (`$edge-log`, usually after `$edge-step`) |
| Session end | Gated (Stop hook) | Voluntary (`$edge-done`) |
| Context injection | Automatic (hook) | Manual (`$edge-context`) |

**The workflow is identical. The enforcement is voluntary but strongly encouraged.**

## Files Structure

```
active_context.yaml          # Your plan and progress
.proof/session_log.jsonl     # Proof log (manually maintained)
.proof/archive.jsonl         # Archived completed work
.claude/state/               # Shared state directory
```

## Remember

> "The value is in the workflow discipline, not the enforcement mechanism."

Users who adopt this system want structure. Follow these guidelines as if they were enforced - because the discipline, not the blocking, is what makes you effective.
