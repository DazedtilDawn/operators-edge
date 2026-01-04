# Process Research Results

Paste external research results and extract action items.

## Current State
@active_context.yaml

## Arguments

This command expects either:
- A research ID (e.g., `R20250115103000`)
- Or the user will paste results after invoking

## Instructions

### 1. Identify the Research Item

If a research ID is provided, find it in `active_context.yaml`:

```yaml
research:
  - id: "R20250115103000"
    topic: "CRDT vs OT for collaborative editing"
    status: pending  # or in_progress
    ...
```

If no ID provided and there's exactly one pending/in_progress research item, use that.

If multiple pending items exist, ask which one the results are for.

### 2. Receive Results

Prompt the user to paste the research results:

```
Paste the research results for: [topic]
(The output from Gemini/Perplexity/etc.)
```

### 3. Process Results

Extract from the pasted results:

1. **Recommendation**: The main suggested approach
2. **Action Items**: Specific next steps (as a list)
3. **Warnings**: Things to watch out for
4. **Key Learnings**: Insights worth remembering

### 4. Update State

Update the research item in `active_context.yaml`:

```yaml
research:
  - id: "R20250115103000"
    topic: "CRDT vs OT for collaborative editing"
    priority: critical
    status: completed  # Changed from pending
    blocking_step: 1
    prompt: |
      [original prompt]
    results: |
      [paste full results here or summary]
    action_items:
      - "Use Yjs library for CRDT implementation"
      - "Start with basic text syncing before rich text"
      - "Implement awareness protocol for cursors"
    created: "2025-01-15T10:30:00"
    completed: "2025-01-15T11:00:00"  # Added
```

### 5. Consider Memory Extraction

If the research yielded valuable lessons, consider adding to memory:

```yaml
memory:
  - trigger: "collaborative editing"
    lesson: "Use CRDT (Yjs) over OT for simpler offline-first architecture"
    applies_to:
      - "real-time collaboration"
      - "offline-first apps"
    reinforced: 1
    source: "research-R20250115103000"
```

### 6. Report Status

After processing:

```
═══════════════════════════════════════════════════════════
RESEARCH COMPLETED: R20250115103000
═══════════════════════════════════════════════════════════

Topic: CRDT vs OT for collaborative editing

Recommendation:
Use CRDT with Yjs library for simpler offline-first architecture.

Action Items Extracted:
  1. Use Yjs library for CRDT implementation
  2. Start with basic text syncing before rich text
  3. Implement awareness protocol for cursors

Warnings:
  - CRDT can have larger memory footprint than OT
  - Need garbage collection strategy for long documents

Status: Step 1 is now unblocked

Next: Run /edge-plan to continue planning
═══════════════════════════════════════════════════════════
```

## Output Format

```
═══════════════════════════════════════════════════════════
RESEARCH COMPLETED: [ID]
═══════════════════════════════════════════════════════════

Topic: [topic]

Recommendation:
[1-2 sentence summary]

Action Items Extracted:
  1. [action item]
  2. [action item]
  ...

Warnings:
  - [warning]
  ...

[If memory was added:]
Memory Added:
  Trigger: "[trigger]"
  Lesson: "[lesson]"

Status: [what was unblocked, if anything]

Next: [suggested next action]
═══════════════════════════════════════════════════════════
```

## Example Usage

### Example 1: With Research ID
```
/edge-research-results R20250115103000

> Paste the research results for: CRDT vs OT
> (The output from Gemini/Perplexity/etc.)

[User pastes results]

═══════════════════════════════════════════════════════════
RESEARCH COMPLETED: R20250115103000
...
```

### Example 2: Auto-detect (single pending)
```
/edge-research-results

Found 1 pending research item: R20250115103000 (CRDT vs OT)
Using this one.

> Paste the research results:

[User pastes results]
...
```

### Example 3: Multiple pending items
```
/edge-research-results

Multiple pending research items:
  1. R20250115103000 - CRDT vs OT for collaborative editing (critical)
  2. R20250115103001 - WebSocket scaling strategies (optional)

Which one are these results for? (Enter ID or number)
```

## Tips

- **Full results preferred**: Paste the complete output from the external tool, Claude will extract what's relevant
- **Structured is better**: If the external tool provided structured output, it's easier to extract action items
- **Add to memory**: If the research reveals a reusable pattern, add it to memory for future sessions
