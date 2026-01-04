---
description: Execute the current step from the plan
allowed-tools: Read, Write, Edit, Bash, Glob, Grep
---

# Execute Current Step

@active_context.yaml

## Instructions

1. **Read the current step** from `active_context.yaml`
   - Find the step matching `current_step`
   - Understand what needs to be done

2. **Check for reminders (v2.4)** - Read `.proof/archive.jsonl` for recurring weak checks
   - If any check has failed 2+ times across sessions, show a reminder:

   ```
   ⚠️ REMINDER: [check_name] has been weak across sessions
   Focus: [specific improvement tip]
   ```

   Common reminders:
   | Weak Check | Reminder |
   |------------|----------|
   | mismatch_detection | "Add Expected vs Actual before major operations" |
   | plan_revision | "If this step fails, write a NEW step before retrying" |
   | tool_switching | "If tool fails twice, switch immediately" |
   | memory_update | "After this step, ask: what did I learn?" |
   | proof_generation | "Attach evidence inline, not after" |
   | stop_condition | "If uncertain, frame as bounded options" |

3. **Mark it in_progress** - Update the step's status in active_context.yaml

4. **Do the work** - Execute the step
   - Keep changes minimal and focused
   - If something unexpected happens, STOP and reassess
   - **Apply the reminder** if one was shown

5. **Verify it worked** - Run a test or check

6. **Mark complete** - Update status to `completed` and set proof path

7. **Advance current_step** - Increment to next pending step

## After Completion

Update active_context.yaml:
```yaml
current_step: [next step number]
plan:
  - description: "The step you just did"
    status: completed
    proof: ".proof/session_log.jsonl"  # or specific artifact
```

Add any lessons learned:
```yaml
lessons:
  - "What you learned that might help future work"
```

## If Blocked

If you cannot complete the step:
1. Mark status as `blocked`
2. Add a note explaining why
3. Do NOT advance current_step
4. Report the blocker clearly
