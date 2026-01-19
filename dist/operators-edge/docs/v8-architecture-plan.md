# Operator's Edge v8.0: Context Engineering Architecture

## The Problem Statement

**What we built in v7.1:** A pattern recognition system that suggests approaches like "for refactoring, try: scope → test → extract → integrate" based on past completions.

**Why it doesn't work:** Claude already knows these patterns. Its training data includes thousands of software projects. Teaching Claude that "refactoring involves extracting then integrating" is like teaching a surgeon that "appendectomy involves incision then removal."

**The real problem:** Claude doesn't fail because it doesn't know patterns. Claude fails because:
1. **Context window limits** - It forgets the objective as sessions grow long
2. **Circular behavior** - It doesn't recognize when it's repeating failed approaches
3. **Codebase blindness** - It lacks project-specific knowledge that a human developer builds over months
4. **Session discontinuity** - Each new session starts with a cold cache, even on familiar problems

## The Paradigm Shift

**v7.1 Assumption:** Claude needs to *learn* from examples (pattern recognition, feedback loops, confidence updates)

**v8.0 Assumption:** Claude needs to *stay on track* (context compression, failure detection, knowledge injection)

This isn't ML. This is context engineering.

---

## Architecture Overview

### What We Keep (High Value)

1. **Hook Enforcement** - The mechanical constraints work
   - Pre-tool blocking (dangerous commands, plan requirements)
   - Post-tool logging (proof capture)
   - Stop gate (state modification required)

2. **Proof System** - Observation infrastructure is solid
   - Session logs capture what actually happened
   - Archive provides historical data
   - This is the "telemetry" layer

3. **Memory/Lessons** - The concept is right, but needs refocusing
   - FROM: Generic lessons ("refactoring needs tests")
   - TO: Codebase-specific lessons ("auth/ imports require __init__.py")

### What We Transform (Medium Value → High Value)

1. **Pattern Recognition → Failure Recovery**
   - FROM: "Here's what usually works for refactoring"
   - TO: "You've seen this error 3 times before. Last fix: check PYTHONPATH"

2. **Confidence Updates → Drift Detection**
   - FROM: Adjusting pattern confidence based on outcomes
   - TO: Detecting when Claude is drifting from the objective or repeating failures

3. **Suggestion Surfacing → Context Compression**
   - FROM: Injecting suggested approaches at session start
   - TO: Compressing completed work to preserve context window for active problems

### What We Add (New Capabilities)

1. **Context Window Monitor** - Track how much context is "used up" and trigger compression
2. **Circular Behavior Detector** - Recognize when Claude is editing the same files repeatedly without progress
3. **Session Handoff Protocol** - Structured summaries for cross-session continuity
4. **Codebase Knowledge Graph** - File relationships, change patterns, common errors

---

## Module Design

### 1. Context Monitor (`context_monitor.py`)

**Purpose:** Track context window utilization and trigger compression when needed.

**Key Insight:** Claude doesn't have access to its own context window size, but we can estimate it by tracking:
- Tool calls this session
- Characters in recent outputs
- Lines of code read

**Interface:**
```python
def estimate_context_usage(session_log: Path) -> ContextEstimate:
    """Estimate how much of context window is consumed."""

def should_compress(estimate: ContextEstimate) -> bool:
    """Returns True when approaching context limits."""

def generate_checkpoint(state: dict, session_log: Path) -> str:
    """Generate a compressed summary of work so far."""
```

**Trigger:** PreToolUse hook checks context usage. When > 70% estimated, surfaces: "Context is getting long. Here's a checkpoint summary: [compressed state]"

### 2. Drift Detector (`drift_detector.py`)

**Purpose:** Recognize when Claude is going in circles or drifting from the objective.

**Signals:**
- Same file edited 3+ times in short span without new information
- Same command run 2+ times with same failure
- Tool calls increasing but plan completion stalled
- Time on current step exceeds 2x average

**Interface:**
```python
def detect_drift(session_log: Path, state: dict) -> Optional[DriftSignal]:
    """Check for circular behavior or objective drift."""

def format_intervention(signal: DriftSignal) -> str:
    """Generate intervention message for Claude."""
```

**Trigger:** PostToolUse hook checks after each tool. If drift detected, surfaces: "⚠️ Drift detected: You've edited utils.py 4 times. Consider: [analysis]"

### 3. Knowledge Base (`codebase_knowledge.py`)

**Purpose:** Store and surface codebase-specific knowledge that Claude can't derive from training.

**Types of Knowledge:**
- **Error → Fix mappings:** "ImportError in auth/ → add __init__.py to path"
- **File → Dependencies:** "Changing config.yaml requires restarting dev server"
- **Change patterns:** "payment.py and billing.py usually change together"

**Interface:**
```python
def record_fix(error_signature: str, fix_applied: str) -> None:
    """Record what fixed an error for future reference."""

def lookup_fix(error_output: str) -> Optional[KnownFix]:
    """Check if we've seen this error before and know a fix."""

def get_related_files(file_path: str) -> List[RelatedFile]:
    """Files that usually change together or depend on this one."""
```

**Trigger:**
- PostToolUse: If command failed, check for known fixes
- PreToolUse (Edit): Surface related files that might also need changes

### 4. Session Handoff (`session_handoff.py`)

**Purpose:** Enable continuity across sessions with structured state transfer.

**Key Insight:** The current system stores state in YAML, but doesn't compress intelligently for handoff. A new session gets the raw state, not an optimized summary.

**Interface:**
```python
def generate_handoff_summary(state: dict, session_log: Path) -> HandoffSummary:
    """Create compressed summary for next session."""

def inject_previous_context(handoff: HandoffSummary) -> str:
    """Format previous session context for injection."""
```

**Structure:**
```yaml
handoff:
  objective: "Refactor authentication module"
  progress: "3/7 steps complete"
  active_problem: "Test failures in auth/login_test.py"
  approaches_tried:
    - "Updated import paths (failed: circular import)"
    - "Split module (failed: missing dependency)"
  key_insight: "The issue is auth/__init__.py importing from submodules"
  next_action: "Create lazy imports in __init__.py"
```

---

## Implementation Phases

### Phase 1: Drift Detection (Highest Impact)
**Why first:** This addresses Claude's most common failure mode - going in circles. The infrastructure (session logs) already exists.

- Implement `drift_detector.py`
- Add detection to PostToolUse hook
- Surface interventions when detected

### Phase 2: Context Compression
**Why second:** Long sessions fail from context exhaustion. Compression extends effective session length.

- Implement `context_monitor.py`
- Add checkpoint generation
- Integrate with session_start and mid-session triggers

### Phase 3: Codebase Knowledge
**Why third:** This is the "learning" that actually helps - codebase-specific, not pattern-generic.

- Implement `codebase_knowledge.py`
- Record error→fix mappings automatically
- Surface known fixes when errors recur

### Phase 4: Session Handoff
**Why last:** Builds on the compression and knowledge systems.

- Implement `session_handoff.py`
- Generate handoff summaries at session end
- Inject previous context at session start

---

## What We DON'T Build

1. **Pattern confidence updates** - Claude doesn't use confidence scores
2. **Approach suggestions** - Claude knows software methodology
3. **Verb taxonomies** - Abstraction without value
4. **Feedback loops** - ML infrastructure for a prompt engineering problem

---

## Success Metrics

**Before (v7.1):**
- Suggestions shown: N/A (Claude already knows patterns)
- Suggestions followed: N/A (not meaningful)
- Pattern confidence: Changes without impacting behavior

**After (v8.0):**
- **Drift interventions triggered:** How often did we catch circular behavior?
- **Context checkpoints used:** How many sessions exceeded 70% context?
- **Known fixes surfaced:** How many errors had prior solutions?
- **Session continuity:** Did handoff summaries reduce cold-start time?

---

## Relationship to Existing Code

### Keep Unchanged
- `pre_tool.py` - Add drift/context hooks, don't restructure
- `proof_utils.py` - Continues logging, provides data for detectors
- `state_utils.py` - Core state management stays
- `session_start.py` - Add context injection, keep structure

### Deprecate (Don't Delete)
- `pattern_recognition.py` - v7.1, keep for historical reference
- `feedback_loop.py` - v7.1, keep for historical reference
- `guidance_config.yaml` - v7.1 verb taxonomy

### Transform
- `archive_utils.py` - Completion capture stays, pattern matching removed
- Learned guidance functions → Codebase knowledge functions

---

## The Vision

Operator's Edge v8.0 is not a "smarter" Claude. It's a Claude that **stays on track**.

The hooks constrain behavior (you can't skip the plan).
The proof system observes behavior (we see what you did).
The new modules **intervene** when behavior drifts (you're going in circles, here's help).

This is supervision, not training.
This is context engineering, not machine learning.
This is what actually helps.
