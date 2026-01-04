# Operator's Edge v2 - Schema Specification

## Design Principles

1. **Constant Memory** - Only living context stays in state; completed work archives
2. **Trigger-Linked Memory** - Lessons tied to patterns, not prose
3. **Checkpoint Instrumentation** - Each step tracks expected vs actual
4. **Graceful Degradation** - New fields optional; v1 files still work

---

## Schema: `active_context.yaml`

```yaml
# ═══════════════════════════════════════════════════════════════════════════════
# OPERATOR'S EDGE v2 - ACTIVE CONTEXT
# This file is the Internal State (<IS>) - the living mind of the agent
# ═══════════════════════════════════════════════════════════════════════════════

# ─────────────────────────────────────────────────────────────────────────────
# SESSION METADATA (auto-managed by hooks)
# ─────────────────────────────────────────────────────────────────────────────
session:
  id: "20250115-103000"           # Unique session identifier
  started_at: "2025-01-15T10:30:00"
  state_hash_start: "abc123..."   # Hash at session start (for change detection)

# ─────────────────────────────────────────────────────────────────────────────
# OBJECTIVE (what we're trying to achieve)
# ─────────────────────────────────────────────────────────────────────────────
objective: "Clear, one-sentence goal"

# ─────────────────────────────────────────────────────────────────────────────
# PLAN (only ACTIVE steps - completed steps are archived)
# ─────────────────────────────────────────────────────────────────────────────
current_step: 2   # 1-indexed pointer to current step

plan:
  # v1 fields (backward compatible)
  - description: "Step description"
    status: pending | in_progress | completed | blocked
    proof: null | "proof description or path"

    # v2 fields (optional, for instrumentation)
    expected: "What should happen when this step succeeds"
    actual: "What actually happened (filled after execution)"
    delta: "Difference between expected and actual (if any)"

# ─────────────────────────────────────────────────────────────────────────────
# OPEN QUESTIONS (unresolved uncertainties blocking or informing work)
# ─────────────────────────────────────────────────────────────────────────────
open_questions:
  - question: "What's the best approach for X?"
    blocking: true              # true = can't proceed until resolved
    context: "We need this for step 3"
    raised_at: "2025-01-15T10:35:00"

# ─────────────────────────────────────────────────────────────────────────────
# RESEARCH (external deep research needs - prompts for outside LLM tools)
# ─────────────────────────────────────────────────────────────────────────────
research:
  - id: "R001"                          # Unique identifier
    topic: "Best caching strategy for real-time updates"
    priority: critical                  # critical | optional
    status: pending                     # pending | in_progress | completed | cancelled
    blocking_step: 1                    # Step this blocks (null if optional)
    context: |
      Why this matters to the objective and what we already know.
      This becomes part of the generated prompt.
    prompt: |                           # Generated prompt for external LLM
      ## Research Request
      [Full self-contained prompt with context]
    results: null                       # User pastes external LLM output here
    action_items: []                    # Extracted from results
      # - "Use Redis for session caching"
      # - "Implement TTL of 5 minutes"
    created: "2025-01-15T10:30:00"
    completed: null                     # Timestamp when results processed

# ─────────────────────────────────────────────────────────────────────────────
# CONSTRAINTS (hard rules that must not be violated)
# ─────────────────────────────────────────────────────────────────────────────
constraints:
  - "No destructive operations without confirmation"
  - "Must work on Windows and Mac"

# ─────────────────────────────────────────────────────────────────────────────
# NEXT ACTION (immediate next thing to do)
# ─────────────────────────────────────────────────────────────────────────────
next_action: "Call the API with refreshed token"

# ─────────────────────────────────────────────────────────────────────────────
# MISMATCHES (when reality diverged from expectations - UNRESOLVED only)
# ─────────────────────────────────────────────────────────────────────────────
mismatches:
  - id: "mismatch-001"
    step: 2
    timestamp: "2025-01-15T11:00:00"
    expectation: "API returns 200 with user list"
    observation: "API returns 403 Forbidden"
    delta: "Auth state changed"
    suspected_cause: "Token expired during long operation"
    confidence: 0.8             # 0.0-1.0 how sure about cause
    resolved: false
    resolution: null            # Filled when resolved, then archived

# ─────────────────────────────────────────────────────────────────────────────
# MEMORY (trigger-linked lessons - only high-value, reinforced ones)
# ─────────────────────────────────────────────────────────────────────────────
memory:
  - trigger: "API returns 403"
    lesson: "Check token expiry; refresh if < 5 min remaining"
    applies_to:
      - "API calls"
      - "long operations"
    reinforced: 3               # Times this lesson proved useful
    last_used: "2025-01-15"
    source: "session-20250110"  # Where we learned this

# ─────────────────────────────────────────────────────────────────────────────
# RISKS (known risks and mitigations - still active)
# ─────────────────────────────────────────────────────────────────────────────
risks:
  - risk: "What could go wrong"
    mitigation: "How we're preventing or detecting it"
    status: active | mitigated | realized

# ─────────────────────────────────────────────────────────────────────────────
# SELF SCORE (6-check assessment - updated at checkpoints/session end)
# ─────────────────────────────────────────────────────────────────────────────
self_score:
  timestamp: "2025-01-15T12:00:00"
  checks:
    mismatch_detection:
      met: true
      note: "Caught API 403 immediately"
    plan_revision:
      met: true
      note: "Added token refresh to plan"
    tool_switching:
      met: false
      note: "N/A - no tool failures"
    memory_update:
      met: true
      note: "Added lesson about token expiry"
    proof_generation:
      met: true
      note: "Attached error log and fix diff"
    stop_condition:
      met: true
      note: "Asked about auth approach before proceeding"
  total: 5                      # Out of 6 (only count applicable)
  level: "real_agent"           # 0-2: demo, 3-4: promising, 5-6: real_agent

# ─────────────────────────────────────────────────────────────────────────────
# ARCHIVE POINTER (reference to archived content)
# ─────────────────────────────────────────────────────────────────────────────
archive:
  path: ".proof/archive.jsonl"
  last_prune: "2025-01-15T12:00:00"
  entries_archived: 15
```

---

## Schema: `.proof/archive.jsonl`

Each line is a JSON object. Types:

### Completed Step
```json
{
  "type": "completed_step",
  "timestamp": "2025-01-15T11:30:00",
  "objective": "Build Operator's Edge v2",
  "step_number": 1,
  "description": "Design enhanced YAML schema",
  "proof": "docs/schema-v2.md created",
  "expected": "Schema spec document",
  "actual": "Schema spec document created",
  "session": "20250115-103000"
}
```

### Resolved Mismatch
```json
{
  "type": "resolved_mismatch",
  "timestamp": "2025-01-15T11:45:00",
  "mismatch_id": "mismatch-001",
  "expectation": "API returns 200",
  "observation": "API returns 403",
  "delta": "Auth state changed",
  "resolution": "Added token refresh before API calls",
  "lesson_extracted": {
    "trigger": "API returns 403",
    "lesson": "Refresh token first"
  },
  "session": "20250115-103000"
}
```

### Completed Objective
```json
{
  "type": "completed_objective",
  "timestamp": "2025-01-15T14:00:00",
  "objective": "Build Operator's Edge v2",
  "summary": "Created orchestrator with 6-check adaptation loop",
  "steps_completed": 17,
  "lessons_captured": 5,
  "self_score": 5,
  "session_range": ["20250115-103000", "20250115-140000"]
}
```

### Decayed Lesson
```json
{
  "type": "decayed_lesson",
  "timestamp": "2025-01-15T12:00:00",
  "trigger": "Use setTimeout",
  "lesson": "Check Node vs browser first",
  "reason": "Never reinforced, 14+ days old",
  "originally_learned": "2025-01-01",
  "reinforced": 0
}
```

### Completed Research
```json
{
  "type": "completed_research",
  "timestamp": "2025-01-15T13:00:00",
  "research_id": "R001",
  "topic": "Best caching strategy for real-time updates",
  "priority": "critical",
  "blocking_step": 1,
  "results_summary": "Redis recommended for session caching with 5-min TTL",
  "action_items": [
    "Use Redis for session caching",
    "Implement TTL of 5 minutes",
    "Add cache invalidation on user logout"
  ],
  "session": "20250115-103000"
}
```

---

## Migration: v1 → v2

v2 is **backward compatible**. A v1 file works unchanged.

New fields are **optional**:
- `expected`, `actual`, `delta` on steps → default to null
- `open_questions` → default to []
- `next_action` → default to null
- `mismatches` → default to []
- `memory` → uses `lessons` if present (renamed)
- `research` → default to []
- `self_score` → default to null
- `archive` → default to null

The hooks detect schema version by presence of v2-specific fields and handle gracefully.

---

## Validation Rules

### Required (v1 + v2)
- `objective` must be non-empty string
- `plan` must be array (can be empty for new session)
- `constraints` must be array

### Soft Validation (warnings, not errors)
- Step with `status: completed` should have `proof`
- Step with `status: in_progress` should have `expected`
- `memory` items should have `trigger` and `lesson`
- `mismatches` with `resolved: true` should be archived

### Entropy Checks
- Warn if `plan` has > 3 completed steps (should archive)
- Warn if `mismatches` has > 2 resolved items (should archive)
- Warn if `memory` has items with `reinforced: 0` and `last_used > 14 days`
- Warn if total file exceeds 150 lines

---

## Field Reference

### Step Status Values
| Status | Meaning |
|--------|---------|
| `pending` | Not started |
| `in_progress` | Currently working |
| `completed` | Done, proof attached |
| `blocked` | Cannot proceed, needs resolution |

### Self-Score Levels
| Score | Level | Meaning |
|-------|-------|---------|
| 0-2 | `demo_automation` | Just following scripts |
| 3-4 | `promising_fragile` | Some adaptation, gaps remain |
| 5-6 | `real_agent` | True adaptive behavior |

### Memory Decay Rules
| Condition | Action |
|-----------|--------|
| `reinforced >= 2` | Keep in active memory |
| `reinforced == 1` AND `last_used < 7 days` | Keep |
| `reinforced == 1` AND `last_used >= 7 days` | Archive |
| `reinforced == 0` AND `last_used < 14 days` | Archive |
| `reinforced == 0` AND `last_used >= 14 days` | Discard (log to archive) |

### Research Priority Values
| Priority | Meaning |
|----------|---------|
| `critical` | Blocks planning or execution - must be resolved |
| `optional` | Would improve quality but not blocking |

### Research Status Values
| Status | Meaning |
|--------|---------|
| `pending` | Identified but not yet sent for research |
| `in_progress` | Prompt copied out, awaiting results |
| `completed` | Results received and action items extracted |
| `cancelled` | No longer needed (scope changed) |

### Research Workflow
```
1. /edge-research scan     → Identify unknowns, generate prompts
2. User copies prompt      → Paste into Gemini/Perplexity/etc
3. User pastes results     → /edge-research-results R001
4. Claude extracts actions → Updates state, unblocks steps
5. Archive when pruned     → Completed research moves to archive
```

---

## Brainstorm System

### Brainstorm State Schema
```yaml
brainstorm:
  id: "B20250130"                      # Unique session ID
  challenge: "How to improve X"        # The problem/opportunity
  mode: "topic"                        # topic | scan
  expert:
    name: "Dr. Jane Chen"
    title: "Principal Systems Architect"
    background: "15 years at Google, MIT PhD"
    contrarian_belief: "Monoliths are often better than microservices"
    cross_domain: "Jazz improvisation and ensemble coordination"
  phase: "converge"                    # diverge | transform | converge | complete
  ideas:
    # Wave A: Spectrum (6 ideas)
    - id: "I001"
      wave: "spectrum"
      type: "safe"                     # safe | modest | combo | adjacent | unrelated | absurd
      title: "Industry standard approach"
      description: "..."
      selected: false                  # Selected for TRANSFORM phase
    # Wave B: Denial (3 ideas)
    - id: "I007"
      wave: "denial"
      title: "..."
      description: "..."
      selected: true
    # Wave C: Perspective (3 ideas)
    - id: "I010"
      wave: "perspective"
      perspective: "child"             # child | future | opposite
      title: "..."
      description: "..."
      selected: false
  transformed:
    - idea_id: "I007"
      scamper:
        substitute: "..."
        combine: "..."
        adapt: "..."
        modify: "..."
        put_to_other_use: "..."
        eliminate: "..."
        reverse: "..."
      analogies:
        biology: "..."
        game_design: "..."
        history: "..."
      scores:
        novelty: 8
        feasibility: 7
        impact: 9
        elegance: 6
        total: 30
      stress_test:
        failure_mode: "..."
        wrong_assumption: "..."
        opposition: "..."
        worst_case: "..."
  recommendations:
    top:
      name: "Hybrid Approach X"
      core_idea: "One sentence a 10-year-old could understand"
      novelty: "What's genuinely new"
      feasibility: "Why we can actually do this"
      impact: "What changes if this works"
      validation: "Cross-domain analogy proving it works"
      risk: "Primary risk"
      mitigation: "How to address the risk"
      actions:
        - "First action"
        - "Second action"
        - "Third action"
    runner_up:
      name: "..."
      core_idea: "..."
      actions: []
    wild_card:
      name: "..."
      core_idea: "..."
      risk_reward: "High risk but potentially transformative"
  created: "2025-01-30T10:00:00"
  completed: null
```

### Scan Mode Findings Schema
```yaml
scan_findings:
  timestamp: "2025-01-30T10:00:00"
  categories:
    code_quality:
      - file: "src/utils.py"
        issue: "TODO: Refactor this mess"
        line: 142
        priority: "medium"
    missing_tests:
      - file: "src/auth.py"
        coverage: "12%"
        priority: "high"
    complexity:
      - file: "src/parser.py"
        metric: "cyclomatic_complexity"
        value: 45
        threshold: 10
        priority: "high"
    state_patterns:
      - pattern: "recurring_mismatch"
        description: "API timeouts appear 3 times in archive"
        priority: "medium"
    architecture:
      - issue: "No error boundaries"
        description: "Errors propagate without graceful handling"
        priority: "high"
  suggested_challenges:
    - "How might we reduce complexity in parser.py?"
    - "How might we improve API reliability?"
    - "How might we increase test coverage for auth?"
```

### Brainstorm Archive Entry
```json
{
  "type": "completed_brainstorm",
  "timestamp": "2025-01-30T12:00:00",
  "brainstorm_id": "B20250130",
  "challenge": "How to improve X",
  "mode": "topic",
  "ideas_generated": 12,
  "top_recommendation": "Hybrid Approach X",
  "actions_extracted": 3,
  "outcome": "implemented | deferred | rejected"
}
```

### Brainstorm Workflow
```
1. /edge-brainstorm              → Scan mode: find improvement opportunities
2. /edge-brainstorm "challenge"  → Topic mode: run structured ideation
3. DIVERGE phase                 → Expert persona + 3 idea waves
4. TRANSFORM phase               → SCAMPER + analogies on top 4 ideas
5. CONVERGE phase                → Score, stress test, synthesize
6. Output                        → Top recommendation + runner-up + wild card
7. Next steps                    → /edge-plan or /edge-research
```
