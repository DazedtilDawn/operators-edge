# Phase 10: Active Context Management

**Status:** Planning
**Inspired by:** Recursive LLM (RLM) research - "don't just warn, actively manage"

---

## The Problem

Phase 7-8 data revealed a critical gap:
- **7% drift correction rate** - signals fire but don't change behavior
- **Passive warnings don't work** - Claude sees "⚠️ Context at 78%" and... keeps going
- **Context degrades quality** - longer sessions = worse outputs (the "context rot" phenomenon)

Our current approach: **observe → warn → hope Claude adjusts**

RLM insight: **observe → actively compress → maintain quality**

---

## Core Insight from RLM Research

The RLM paper's key finding isn't about infinite context - it's about **recursive decomposition**:

> "Instead of processing massive context directly, recursively partition and summarize"

Applied to Operator's Edge:
- Don't warn about high context → **actively compress it**
- Don't suggest checkpoints → **auto-generate them**
- Don't hope Claude reads less → **help Claude read smarter**

---

## Phase 10 Components

### 10.1: Context Compression Engine (`context_compressor.py`)

**Trigger:** Context usage > 70% (configurable)

**What it does:**
```
1. Identify context segments:
   - File reads (often largest)
   - Bash outputs (can be verbose)
   - Conversation history (accumulates)

2. For each large segment (>5000 tokens estimated):
   - Extract key facts/structure
   - Generate compressed summary
   - Store full version in .proof/context_snapshots/

3. Inject compressed version with retrieval hint:
   "Summary of src/app.py (full: .proof/context_snapshots/abc123)"
```

**Implementation approach:**
```python
# context_compressor.py

@dataclass
class ContextSegment:
    segment_type: str  # "file_read", "bash_output", "conversation"
    content: str
    estimated_tokens: int
    timestamp: str
    source: str  # file path, command, etc.

def identify_compressible_segments(session_log: Path) -> List[ContextSegment]:
    """Find segments that could be compressed."""
    pass

def compress_segment(segment: ContextSegment) -> Tuple[str, str]:
    """
    Compress a segment, return (summary, snapshot_id).

    For file reads: Extract structure, key functions, imports
    For bash output: Extract errors, key lines, summary
    For conversation: Extract decisions, outcomes, pending items
    """
    pass

def inject_compression_suggestion(segment: ContextSegment) -> str:
    """Generate suggestion to use compressed version."""
    pass
```

**Key design decisions:**
- Compression happens via **prompting Claude** (not external summarizer)
- Full content stored for retrieval if needed
- Suggestion-based (advise level) or automatic (guide/intervene level)

---

### 10.2: REPL-Assisted File Reading (`smart_read.py`)

**Trigger:** Pre-tool hook sees Read on file > 500 lines

**What it does:**
```
Before: Claude reads entire 5000-line file into context

After:
1. Detect large file read request
2. Surface suggestion:
   "This file is 5000 lines. Consider:
    - grep 'function.*error' to find relevant sections
    - head -100 to see structure first
    - Read specific line ranges after identifying targets"
3. If at guide/intervene level, inject as strong recommendation
```

**Why this helps:**
- Prevents context bloat from full file reads
- Claude already has REPL access - we just need to encourage using it
- Targeted reads = better comprehension + less context used

**Implementation:**
```python
# smart_read.py

def check_read_size(file_path: str) -> Optional[int]:
    """Return line count if file exists, None otherwise."""
    pass

def suggest_smart_read(file_path: str, line_count: int) -> str:
    """Generate smart read suggestion based on file type and size."""

    suggestions = []

    # Generic suggestions
    if line_count > 1000:
        suggestions.append(f"File has {line_count} lines - consider reading in sections")

    # File-type specific
    if file_path.endswith('.py'):
        suggestions.append("Try: grep -n 'def \\|class ' to see structure")
    elif file_path.endswith('.json'):
        suggestions.append("Try: head -50 to see schema, or jq for specific keys")
    elif file_path.endswith('.log'):
        suggestions.append("Try: tail -100 for recent entries, or grep for errors")

    return format_suggestion(suggestions)
```

**Integration:**
- Hook into `pre_tool.py` before Read tool
- At advise level: surface as suggestion
- At guide level: inject prominently
- At intervene level: could block and require confirmation

---

### 10.3: Recursive Self-Clarification (`self_clarify.py`)

**Trigger:** Drift signals fire 3+ times without resolution

**What it does:**
```
When stuck (repeated drift signals):

1. Capture recent context:
   - Last 3-5 tool calls
   - Any error messages
   - Files being edited

2. Spawn clarification query:
   "Given these recent actions:
    - Edit app.py (4 times)
    - Error: undefined variable 'user'
    - Edit app.py again

    What is the actual problem being solved?
    What approach would break this cycle?"

3. Inject clarification as context:
   "🔍 Self-clarification: The core issue appears to be..."
```

**Why this helps:**
- Forces stepping back when Claude is spinning
- The act of articulating the problem often reveals the solution
- Breaks the "try same thing again" loop

**Implementation:**
```python
# self_clarify.py

def should_trigger_clarification(session_health: SessionHealth) -> bool:
    """Check if clarification is warranted."""
    return (
        session_health.drift_signals_ignored >= 3 or
        session_health.same_error_count >= 3 or
        session_health.same_file_edits >= 5
    )

def gather_clarification_context() -> Dict[str, Any]:
    """Collect recent actions for clarification."""
    pass

def generate_clarification_prompt(context: Dict[str, Any]) -> str:
    """Generate the self-clarification prompt."""
    pass

def inject_clarification(clarification: str) -> str:
    """Format clarification for injection."""
    return f"""
╭─ 🔍 SELF-CLARIFICATION ─────────────────────────╮
│ {clarification}
╰──────────────────────────────────────────────────╯
"""
```

**Note:** This doesn't actually call Claude recursively (we can't do that from hooks). Instead:
- Generate the clarification prompt
- Inject it as a strong suggestion Claude should address
- The "recursion" happens through Claude's own reasoning

---

### 10.4: Auto-Checkpoint with Compression (`auto_checkpoint.py`)

**Trigger:** Natural breakpoints (step completion, phase change, time threshold)

**What it does:**
```
At natural breakpoints:

1. Detect breakpoint:
   - Step marked complete
   - 30 minutes elapsed
   - Major file committed
   - Error resolved after struggle

2. Generate compressed checkpoint:
   - What was accomplished (1-2 sentences)
   - Key decisions made
   - Files modified (just names)
   - Pending items

3. Offer to "compact" context:
   "Checkpoint available. Compact context to continue fresh?
    - Accomplished: Fixed auth bug in login.py
    - Pending: Add tests, update docs
    [Yes - compact and continue] [No - keep full context]"
```

**Why this helps:**
- Structured stopping points prevent context bloat
- Compressed summaries maintain continuity without full history
- User control over when to compact

**Implementation:**
```python
# auto_checkpoint.py

@dataclass
class Checkpoint:
    checkpoint_id: str
    timestamp: str
    accomplished: List[str]
    decisions: List[str]
    files_modified: List[str]
    pending: List[str]
    context_snapshot_id: Optional[str]  # Full context backup

def detect_breakpoint(event: str, session_state: Dict) -> bool:
    """Check if current event is a natural breakpoint."""
    pass

def generate_checkpoint(session_log: Path) -> Checkpoint:
    """Generate checkpoint from recent session activity."""
    pass

def offer_compaction(checkpoint: Checkpoint) -> str:
    """Generate compaction offer message."""
    pass
```

---

## Integration Points

### Pre-Tool Hook (`pre_tool.py`)

```python
# Add to pre_tool.py

def phase10_pre_tool(tool_name: str, tool_input: Dict) -> Optional[str]:
    """Phase 10: Active context management before tool execution."""

    messages = []

    # 10.2: Smart read suggestions
    if tool_name == "Read":
        file_path = tool_input.get("file_path", "")
        from smart_read import check_read_size, suggest_smart_read
        line_count = check_read_size(file_path)
        if line_count and line_count > 500:
            messages.append(suggest_smart_read(file_path, line_count))

    # 10.1: Context compression check
    from context_monitor import get_context_usage
    usage = get_context_usage()
    if usage > 0.70:
        from context_compressor import suggest_compression
        messages.append(suggest_compression())

    # 10.3: Self-clarification check
    from active_intervention import get_session_health
    health = get_session_health()
    from self_clarify import should_trigger_clarification, generate_clarification
    if should_trigger_clarification(health):
        messages.append(generate_clarification())

    return "\n\n".join(messages) if messages else None
```

### Post-Tool Hook (`post_tool.py`)

```python
# Add to post_tool.py

def phase10_post_tool(tool_name: str, tool_output: str) -> Optional[str]:
    """Phase 10: Checkpoint detection after tool execution."""

    # 10.4: Check for natural breakpoints
    from auto_checkpoint import detect_breakpoint, offer_compaction
    if detect_breakpoint(tool_name, tool_output):
        checkpoint = generate_checkpoint()
        return offer_compaction(checkpoint)

    return None
```

---

## Configuration

Add to `.proof/v8_config.json`:

```json
{
  "phase10": {
    "context_compression": {
      "enabled": true,
      "threshold": 0.70,
      "min_segment_tokens": 5000,
      "auto_compress_at_intervene": true
    },
    "smart_read": {
      "enabled": true,
      "line_threshold": 500,
      "suggest_at_advise": true,
      "require_at_intervene": false
    },
    "self_clarification": {
      "enabled": true,
      "drift_threshold": 3,
      "error_repeat_threshold": 3
    },
    "auto_checkpoint": {
      "enabled": true,
      "time_threshold_minutes": 30,
      "offer_compaction": true
    }
  }
}
```

---

## Implementation Order

1. **10.2: Smart Read** (simplest, immediate value)
   - Just suggestions, no complex logic
   - Integrates with existing pre_tool.py
   - ~2 hours to implement

2. **10.4: Auto-Checkpoint** (builds on existing handoff)
   - Extends session_handoff.py concepts
   - Natural breakpoint detection
   - ~3 hours to implement

3. **10.3: Self-Clarification** (moderate complexity)
   - Needs drift signal integration
   - Prompt engineering for clarification
   - ~4 hours to implement

4. **10.1: Context Compression** (most complex)
   - Requires segment identification
   - Storage infrastructure
   - Token estimation refinement
   - ~6 hours to implement

**Total estimate:** 15-20 hours

---

## Success Metrics

| Metric | Current (Phase 8) | Target (Phase 10) |
|--------|-------------------|-------------------|
| Drift correction rate | 7% | 25%+ |
| Context warnings acted on | ~10% | 50%+ (via auto-compress) |
| Average session context at end | 85%+ | <70% |
| "Stuck" sessions (5+ same-file edits) | Common | Rare |

---

## What We're NOT Doing

1. **Actual recursive LLM calls** - Can't spawn sub-Claude from hooks
2. **Training/fine-tuning** - We work with base Claude
3. **Massive document retrieval** - Not our use case
4. **Multi-model arbitrage** - Single model (Claude)

---

## Risk Assessment

| Risk | Mitigation |
|------|------------|
| Over-aggressive compression loses info | Store full context in .proof/, offer retrieval |
| Smart read suggestions annoying | Respect intervention level, add cooldowns |
| Self-clarification feels robotic | Natural language, contextual prompts |
| Checkpoint fatigue | Only at genuine breakpoints, user can dismiss |

---

## Next Steps

1. Review this plan
2. Implement 10.2 (Smart Read) as proof of concept
3. Measure impact on context usage
4. Iterate based on data

---

*"The best way to predict the future is to implement it."*
