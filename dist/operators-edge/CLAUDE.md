# Operator's Edge

This project runs under mechanical enforcement, not just policy.

## What's Enforced (You Cannot Bypass These)

| Rule | Enforcement | What Happens |
|------|-------------|--------------|
| **No edits without a plan** | PreToolUse hook | Edit/Write blocked until `active_context.yaml` has a plan |
| **No dangerous commands** | PreToolUse hook | `rm -rf`, `git reset --hard`, etc. are hard-blocked |
| **No blind retries** | PreToolUse hook | Commands that failed twice require new approach |
| **No stopping without progress** | Stop hook | Session end blocked until `active_context.yaml` is modified |
| **No stopping without proof** | Stop hook | Session end blocked until `.proof/session_log.jsonl` exists |
| **All tool use logged** | PostToolUse hook | Every command, edit, and read automatically captured |

## State File: `active_context.yaml`

This is the source of truth. It must contain:
- `objective`: What you're trying to achieve
- `plan`: List of steps with `description`, `status`, `proof`
- `current_step`: Which step you're on
- `constraints`: Things that must not happen
- `lessons`: What you've learned (carried forward)

**Status values**: `pending` | `in_progress` | `completed` | `blocked`

## Workflow

1. **Start**: Session begins, hook injects current state
2. **Plan**: Update `active_context.yaml` with your plan (use `/edge-plan`)
3. **Execute**: Work step by step, marking `in_progress` → `completed`
4. **Prove**: Proof is captured automatically; review in `.proof/session_log.jsonl`
5. **Stop**: Only possible after state modified + proof exists

## Commands

- `/edge` - Smart orchestrator - figures out what you need
- `/edge-plan` - Create or update the plan in `active_context.yaml`
- `/edge-yolo` - Dispatch Mode - autopilot that runs until objective complete
- `/edge-step` - Execute the current step

## Dispatch Mode (Autopilot)

Enable autopilot: `/edge-yolo on`

Dispatch Mode runs /edge commands automatically until the objective is complete,
stopping only at "junctions" (decision points requiring human input):

| Junction Type | Examples | Behavior |
|---------------|----------|----------|
| **irreversible** | git push, rm, delete | Always pause |
| **external** | API calls, deploys | Always pause |
| **ambiguous** | Plan creation, multiple approaches | Always pause |
| **blocked** | Step failed, needs adaptation | Always pause |

Everything else (executing plan steps, read operations) runs automatically.

**Commands:**
- `/edge-yolo on` - Start autopilot
- `/edge-yolo off` - Stop autopilot
- `/edge-yolo approve` - Approve junction and continue
- `/edge-yolo` - Check status

## Files That Matter

```
active_context.yaml          # Your plan and progress (YAML, validated)
.proof/session_log.jsonl     # Auto-captured proof of all actions
.claude/state/dispatch_state.json  # Dispatch mode state
.claude/state/               # Hook state (hashes, failure logs)
```

## What's NOT Enforced (Policy Only)

- Quality of your plan (you can make a bad plan)
- Quality of your work (you can write bad code)
- Whether you actually understand the problem
- Whether your "completed" status is honest

These remain your responsibility. The system ensures you *can't skip* state and proof; it doesn't ensure you do them *well*.
