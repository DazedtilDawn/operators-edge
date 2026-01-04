---
description: Prune completed work from active state to keep memory constant
allowed-tools: Read, Edit, Write
---

# Prune Active State

Distill and archive completed work to keep the active context lean.

## Current State
@active_context.yaml

## The Principle

> "The only thing that grows is capability, not context."

After work is done, it should move from active memory to archive. Only living context stays in the state file.

## What Gets Pruned

| Category | Rule | Destination |
|----------|------|-------------|
| Completed steps | Keep only the last one | `.proof/archive.jsonl` |
| Resolved mismatches | All resolved ones | `.proof/archive.jsonl` |
| Stale memory | Unreinforced for 14+ days | Logged then discarded |

## Instructions

1. **Analyze current state** - Count what can be pruned:
   - Completed steps (keep only the most recent)
   - Resolved mismatches (all should be archived)
   - Stale memory items (unreinforced and old)

2. **Archive completed steps**
   For each completed step (except the most recent), move to archive:
   ```yaml
   # Remove from plan:
   - description: "Old completed step"
     status: completed
     proof: "..."
   ```

   Log to `.proof/archive.jsonl`:
   ```json
   {"type": "completed_step", "timestamp": "...", "description": "...", "proof": "..."}
   ```

3. **Archive resolved mismatches**
   Remove from `mismatches:` array, log to archive.

4. **Decay stale memory**
   Remove memory items that are:
   - `reinforced: 0` AND `last_used` > 14 days ago
   - `reinforced: 1` AND `last_used` > 7 days ago

   Log the decay to archive for audit trail.

5. **Consolidate similar lessons (v2.5)**
   Check for lessons that cover the same topic:
   - Use theme-based grouping (cross_platform, enforcement, memory_state, etc.)
   - Look for lessons with >40% keyword overlap in the same theme
   - Keep the lesson with higher reinforcement count
   - Archive the merged-away lesson
   - Increase reinforcement on the kept lesson

   Example consolidation:
   ```
   BEFORE:
   - "Windows uses 'python', Mac uses 'python3'" (reinforced: 3)
   - "Mac uses python3, Windows uses python command" (reinforced: 1)

   AFTER:
   - "Windows uses 'python', Mac uses 'python3'" (reinforced: 4)
     consolidated_from: ["Mac uses python3, Windows uses python command"]
   ```

6. **Update archive reference**
   ```yaml
   archive:
     path: ".proof/archive.jsonl"
     last_prune: "<current_timestamp>"
     entries_archived: <updated_count>
   ```

## Output

After pruning, report:
- Steps archived: N
- Mismatches archived: N
- Memory items decayed: N
- Lessons consolidated: N (v2.5)
- Estimated lines saved: N
- New state size vs old

## Example

Before:
```yaml
plan:
  - description: "Step 1"
    status: completed
    proof: "done"
  - description: "Step 2"
    status: completed
    proof: "done"
  - description: "Step 3"
    status: completed
    proof: "done"
  - description: "Step 4"
    status: in_progress
```

After:
```yaml
plan:
  - description: "Step 3"  # Keep only most recent completed
    status: completed
    proof: "done"
  - description: "Step 4"
    status: in_progress

archive:
  path: ".proof/archive.jsonl"
  last_prune: "2025-01-15T12:00:00"
  entries_archived: 2  # Steps 1 and 2
```

## When to Prune

- Before ending a session (stop gate may require it)
- After completing a major phase
- When the orchestrator suggests it (entropy check)
- Manually when state feels bloated

## Safety

- Everything is archived, never truly deleted
- You can search the archive if you need old context
- Pruning is reversible by examining `.proof/archive.jsonl`
