# Research Scanner

Detect research needs and generate prompts for external deep research tools.

## Current State
@active_context.yaml

## Instructions

### 1. Scan for Research Needs

Analyze the objective, plan, and context for unknowns that need research:

**Technology Indicators** (may need best practices):
- Complex technologies: kubernetes, websocket, oauth, distributed systems, etc.
- Unfamiliar frameworks or patterns mentioned

**Ambiguity Signals** (likely needs clarification):
- "best way", "should I", "which one", "recommend", "optimize"
- "pros and cons", "compare", "vs", "trade-off"

**Explicit Research Needs**:
- Open questions in state
- Steps that start with: evaluate, assess, investigate, research, compare

### 2. Categorize Findings

| Priority | Criteria | Effect |
|----------|----------|--------|
| **CRITICAL** | Ambiguity in objective, blocking open questions, research verbs | Blocks planning/execution |
| **OPTIONAL** | Technology best practices, optimization opportunities | Improves quality |

### 3. Generate Prompts

For each research need, generate a self-contained prompt that includes:
- Project objective and constraints
- Why this research is needed
- What we already know (relevant lessons)
- Specific questions to answer
- Requested output format

### 4. Output Format

```
═══════════════════════════════════════════════════════════
RESEARCH SCAN RESULTS
═══════════════════════════════════════════════════════════

Scanned: [objective]

CRITICAL (blocks progress):
  1. [R001] Topic: ...
     Reason: ...
     Blocks: Step X

OPTIONAL (improves quality):
  2. [R002] Topic: ...
     Reason: ...

═══════════════════════════════════════════════════════════
PROMPT FOR R001 (Copy to external research tool)
═══════════════════════════════════════════════════════════

[Full self-contained prompt]

═══════════════════════════════════════════════════════════
```

### 5. Update State

After generating prompts, add research items to `active_context.yaml`:

```yaml
research:
  - id: "R001"
    topic: "Best caching strategy for real-time updates"
    priority: critical
    status: pending
    blocking_step: 1
    prompt: |
      [generated prompt]
    results: null
    action_items: []
    created: "2025-01-15T10:30:00"
```

## Workflow

1. **Run scan**: `/edge-research`
2. **Copy prompt**: User copies the generated prompt
3. **External research**: Paste into Gemini Deep Research, Perplexity, etc.
4. **Paste results**: `/edge-research-results R001` (separate command)
5. **Extract actions**: Claude processes results, extracts action items
6. **Unblock**: Research marked complete, planning/execution can proceed

## When No Research Needed

If scan finds no research needs:

```
═══════════════════════════════════════════════════════════
RESEARCH SCAN RESULTS
═══════════════════════════════════════════════════════════

Scanned: [objective]

No research needs detected.

Ready to proceed with planning/execution.
═══════════════════════════════════════════════════════════
```

## Example Output

```
═══════════════════════════════════════════════════════════
RESEARCH SCAN RESULTS
═══════════════════════════════════════════════════════════

Scanned: Build real-time collaborative text editor

CRITICAL (blocks progress):
  1. [R20250115103000] CRDT vs OT for collaborative editing
     Reason: Objective contains ambiguity signal: 'real-time'
     Blocks: Step 1 (planning)

OPTIONAL (improves quality):
  2. [R20250115103001] Best practices for websocket
     Reason: Objective mentions 'real-time' technology

═══════════════════════════════════════════════════════════
PROMPT FOR R20250115103000 (CRITICAL - Copy to external tool)
═══════════════════════════════════════════════════════════

## Research Request: CRDT vs OT for collaborative editing

### Project Context
**Objective:** Build real-time collaborative text editor
**Constraints:**
- Must work offline
- Sub-100ms latency for local edits

### Why This Research Is Needed
Building a collaborative editor requires choosing between
Conflict-free Replicated Data Types (CRDT) or Operational
Transformation (OT). This decision affects the entire architecture.

**This blocks:** Step 1 of the implementation plan

### Questions to Answer
1. What is the recommended approach for: CRDT vs OT?
2. What are the key trade-offs to consider?
3. What are common pitfalls or mistakes to avoid?
4. What would a minimal viable implementation look like?
5. What must be decided before proceeding?

### Requested Output Format
Please provide:
1. **Recommendation**: Your suggested approach (1-2 sentences)
2. **Reasoning**: Why this approach (2-3 bullet points)
3. **Action Items**: Specific next steps to implement (3-5 bullets)
4. **Warnings**: Things to watch out for (2-3 bullets)

═══════════════════════════════════════════════════════════
```

## Tips

- **Be selective**: Not every technology mention needs research
- **Focus on blockers**: Prioritize critical items that block progress
- **Context matters**: Include enough context for the external tool to give relevant answers
- **Action-oriented**: Request specific, actionable output from research

## Arguments

- No arguments: Scan current state for research needs
- `--topic "specific topic"`: Generate a prompt for a specific topic (manual mode)
