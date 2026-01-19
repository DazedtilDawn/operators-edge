# v8.0 Architecture Diagram

## The Paradigm Shift

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                                                                             │
│                        v7.1: PATTERN TEACHING                               │
│                        (Wrong Problem)                                      │
│                                                                             │
│    ┌──────────┐     ┌──────────────┐     ┌──────────────┐                  │
│    │ Archive  │────▶│   Pattern    │────▶│  Suggestion  │                  │
│    │ History  │     │ Recognition  │     │  Surfacing   │                  │
│    └──────────┘     └──────────────┘     └──────────────┘                  │
│         │                  │                    │                          │
│         │                  ▼                    ▼                          │
│         │          ┌──────────────┐     ┌──────────────┐                  │
│         └─────────▶│   Feedback   │────▶│  Confidence  │                  │
│                    │    Loop      │     │   Updates    │                  │
│                    └──────────────┘     └──────────────┘                  │
│                                                                             │
│    PROBLEM: Claude already knows patterns. This teaches nothing new.       │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘


┌─────────────────────────────────────────────────────────────────────────────┐
│                                                                             │
│                      v8.0: CONTEXT ENGINEERING                              │
│                      (Right Problem)                                        │
│                                                                             │
│                         ┌────────────────┐                                  │
│                         │   OBJECTIVE    │                                  │
│                         │  (Source of    │                                  │
│                         │    Truth)      │                                  │
│                         └───────┬────────┘                                  │
│                                 │                                           │
│         ┌───────────────────────┼───────────────────────┐                  │
│         │                       │                       │                  │
│         ▼                       ▼                       ▼                  │
│  ┌─────────────┐        ┌─────────────┐        ┌─────────────┐            │
│  │   CONTEXT   │        │    DRIFT    │        │  CODEBASE   │            │
│  │   MONITOR   │        │  DETECTOR   │        │  KNOWLEDGE  │            │
│  │             │        │             │        │             │            │
│  │ "You're at  │        │ "You've     │        │ "This error │            │
│  │  70% ctx,   │        │  edited X   │        │  was fixed  │            │
│  │  compress"  │        │  4 times"   │        │  last time  │            │
│  │             │        │             │        │  by Y"      │            │
│  └──────┬──────┘        └──────┬──────┘        └──────┬──────┘            │
│         │                      │                      │                    │
│         └──────────────────────┼──────────────────────┘                    │
│                                │                                           │
│                                ▼                                           │
│                     ┌────────────────────┐                                 │
│                     │    INTERVENTION    │                                 │
│                     │                    │                                 │
│                     │  Surface to Claude │                                 │
│                     │  at Decision Time  │                                 │
│                     └────────────────────┘                                 │
│                                                                             │
│    INSIGHT: Claude doesn't need teaching. Claude needs supervision.        │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

## Data Flow

```
SESSION START
     │
     ▼
┌─────────────────────────────────────────────────────────────────┐
│                    SESSION HANDOFF INJECTION                     │
│                                                                  │
│  "Previous session worked on: [objective]                       │
│   Progress: 3/7 steps                                           │
│   Last obstacle: circular import in auth/                       │
│   Approaches tried: [X, Y] - both failed                        │
│   Key insight: __init__.py lazy imports needed"                 │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
     │
     ▼
┌─────────────────────────────────────────────────────────────────┐
│                         TOOL EXECUTION                           │
│                                                                  │
│  PreToolUse ─────┬─────────────────────────────────────────────│
│     │            │                                              │
│     │   ┌────────▼────────┐    ┌──────────────┐                │
│     │   │ Context Check   │    │ Known Fixes? │                │
│     │   │ >70%? Compress  │    │ Surface them │                │
│     │   └─────────────────┘    └──────────────┘                │
│     │                                                           │
│     ▼                                                           │
│  [Tool Runs]                                                    │
│     │                                                           │
│  PostToolUse ────┬─────────────────────────────────────────────│
│     │            │                                              │
│     │   ┌────────▼────────┐    ┌──────────────┐                │
│     │   │ Drift Check     │    │ Record Fix?  │                │
│     │   │ Circles? Alert  │    │ Error→Fix    │                │
│     │   └─────────────────┘    └──────────────┘                │
│     │                                                           │
└─────┼───────────────────────────────────────────────────────────┘
      │
      ▼
SESSION END
      │
      ▼
┌─────────────────────────────────────────────────────────────────┐
│                    HANDOFF SUMMARY GENERATION                    │
│                                                                  │
│  "This session:                                                 │
│   - Objective: [X]                                              │
│   - Completed: steps 4-6                                        │
│   - Current blocker: [Y]                                        │
│   - For next session: Try [Z]"                                  │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

## Module Responsibilities

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                                                                             │
│  SUPERVISION LAYER (New in v8.0)                                           │
│  ════════════════════════════════                                          │
│                                                                             │
│  ┌─────────────────┐  ┌─────────────────┐  ┌─────────────────┐             │
│  │ context_monitor │  │ drift_detector  │  │codebase_knowledge│            │
│  │                 │  │                 │  │                 │             │
│  │ - Estimate ctx  │  │ - File edit     │  │ - Error→Fix DB  │             │
│  │ - Trigger       │  │   frequency     │  │ - File deps     │             │
│  │   compression   │  │ - Command       │  │ - Change        │             │
│  │ - Generate      │  │   repetition    │  │   patterns      │             │
│  │   checkpoints   │  │ - Step stall    │  │                 │             │
│  └─────────────────┘  └─────────────────┘  └─────────────────┘             │
│                                                                             │
│  ┌───────────────────────────────────────────────────────────────┐         │
│  │                      session_handoff                          │         │
│  │                                                               │         │
│  │  - Generate end-of-session summaries                         │         │
│  │  - Inject previous context at session start                  │         │
│  │  - Compress completed work into key insights                 │         │
│  └───────────────────────────────────────────────────────────────┘         │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
│
│ Builds on top of
▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                                                                             │
│  ENFORCEMENT LAYER (Unchanged from v7)                                     │
│  ═════════════════════════════════════                                     │
│                                                                             │
│  ┌─────────────────┐  ┌─────────────────┐  ┌─────────────────┐             │
│  │   pre_tool.py   │  │  post_tool.py   │  │    stop.py      │             │
│  │                 │  │                 │  │                 │             │
│  │ - Block danger  │  │ - Log proof     │  │ - Require state │             │
│  │ - Require plan  │  │ - Track outcome │  │   modification  │             │
│  │ - Block retries │  │                 │  │ - Require proof │             │
│  └─────────────────┘  └─────────────────┘  └─────────────────┘             │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
│
│ Stores data to
▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                                                                             │
│  OBSERVATION LAYER (Unchanged from v7)                                     │
│  ═════════════════════════════════════                                     │
│                                                                             │
│  ┌─────────────────────────────────────────────────────────────────┐       │
│  │                        proof_utils.py                           │       │
│  │                                                                 │       │
│  │  Session logs ─▶ sessions/YYYYMMDD-HHMMSS.jsonl                │       │
│  │  Archive      ─▶ archive.jsonl                                 │       │
│  │                                                                 │       │
│  │  Every tool call, every outcome, every state change            │       │
│  └─────────────────────────────────────────────────────────────────┘       │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

## Comparison

| Aspect | v7.1 (Pattern Teaching) | v8.0 (Context Engineering) |
|--------|------------------------|---------------------------|
| **Core assumption** | Claude needs to learn patterns | Claude needs to stay focused |
| **Data use** | Train on completions | Detect drift, compress state |
| **Intervention timing** | Session start (suggestions) | Any time (when needed) |
| **Value source** | Historical patterns | Real-time supervision |
| **Codebase specificity** | Generic methodology | Project-specific knowledge |
| **Feedback mechanism** | Confidence updates | Direct intervention |

## Implementation Priority

```
PHASE 1: Drift Detection          PHASE 2: Context Compression
═══════════════════════           ═══════════════════════════
         │                                    │
    ┌────▼────┐                         ┌────▼────┐
    │ HIGHEST │                         │  HIGH   │
    │ IMPACT  │                         │ IMPACT  │
    └─────────┘                         └─────────┘
         │                                    │
    "Stop going                         "Work longer
     in circles"                         before limits"


PHASE 3: Codebase Knowledge       PHASE 4: Session Handoff
═══════════════════════════       ════════════════════════
         │                                    │
    ┌────▼────┐                         ┌────▼────┐
    │ MEDIUM  │                         │ MEDIUM  │
    │ IMPACT  │                         │ IMPACT  │
    └─────────┘                         └─────────┘
         │                                    │
    "Learn from                         "Continue across
     this repo"                          sessions"
```

---

## The Core Insight

**v7.1 asked:** "What patterns can we teach Claude?"

**v8.0 asks:** "How do we keep Claude on track?"

The answer isn't more training.
The answer is better supervision.
