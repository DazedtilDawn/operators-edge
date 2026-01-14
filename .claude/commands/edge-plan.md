---
description: Create or update the plan in active_context.yaml
allowed-tools: Read, Write, Glob, Grep
---

> **[v4.0 MIGRATION]** Consider using `/edge plan` to enter PLAN mode instead.
> The `/edge-plan` command still works but `/edge plan` provides better mode awareness.

# Create/Update Plan

Read the current state and help create or refine a plan.

## Current State
@active_context.yaml

## Instructions

### 0. Check for Research Needs First

Before creating a plan, scan the objective for research needs:

**Check for these signals:**
- Complex technologies mentioned (kubernetes, websocket, CRDT, etc.)
- Ambiguity signals ("best way", "should I", "optimize", "compare")
- Explicit research verbs ("evaluate", "investigate", "research")

**If critical research needs detected:**
```
═══════════════════════════════════════════════════════════
RESEARCH RECOMMENDED BEFORE PLANNING
═══════════════════════════════════════════════════════════

Detected [N] research need(s) that may block planning:

CRITICAL:
  • [topic] - [reason]

Recommendation: Run /edge-research to generate prompts
for external deep research before creating the plan.

Continue anyway? (Some decisions may need to be revisited)
═══════════════════════════════════════════════════════════
```

If no critical research needs, proceed with planning.

### 1. Understand the objective

What are we trying to achieve? If no objective is set, ask the user.

### 2. Break it into steps

Each step should be:
- Small enough to complete in one focused effort
- Testable (you can verify it worked)
- Independent where possible

### 3. Update active_context.yaml

```yaml
objective: "Clear statement of goal"
current_step: 1
plan:
  - description: "First step"
    status: pending
    proof: null
  - description: "Second step"
    status: pending
    proof: null
constraints:
  - "What must NOT happen"
risks:
  - risk: "What could go wrong"
    mitigation: "How to prevent/detect it"

# Optional v3.5: I/O Contract (for integrations)
io_contract:
  input: "JSON file with user records from CRM export"
  output: "SQLite database with normalized schema"
```

### 4. Identify constraints

What should NOT change? What's off-limits?

### 5. Identify Risks (REQUIRED - v3.5)

**This is mandatory.** The pre-tool hook will ask for confirmation if risks are empty.

Ask yourself: "What are 3 ways this could fail?"

| Risk Type | Examples |
|-----------|----------|
| **Technical** | Wrong library, API changes, version conflicts |
| **Scope** | Feature creep, unclear requirements, missing edge cases |
| **Integration** | Breaks existing code, data format mismatch |
| **External** | Network failures, rate limits, auth issues |

```yaml
risks:
  - risk: "psycopg2 writes to PostgreSQL but app uses SQLite"
    mitigation: "Verify database connection string matches app config"
  - risk: "Sync might timeout on large datasets"
    mitigation: "Add batch processing with progress logging"
  - risk: "Breaking change to existing API consumers"
    mitigation: "Version the API endpoint, deprecate old"
```

**Tip:** If you can't think of risks, the objective may be too vague.

## Output

After updating active_context.yaml, summarize:
- The objective
- Number of steps
- Key constraints
- **Top risks (at least 1 required)**
- Any research recommendations

Do NOT start implementation. Just plan.

## Research Integration

If research items exist in state:

**Blocking research (critical, pending):**
- Warn that planning may need revision after research completes
- Suggest running `/edge-research` first

**Completed research:**
- Incorporate action items from research results into the plan
- Reference research findings in relevant steps

Example incorporating research:
```yaml
plan:
  - description: "Implement CRDT sync using Yjs library"
    status: pending
    proof: null
    # From research R20250115103000: Use Yjs for simpler offline-first
```

## Arguments

- No arguments: Create plan for current objective, or ask for one
- `"objective text"`: Set this as the new objective and create plan
