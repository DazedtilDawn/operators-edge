# Structured Brainstorming Session

A research-backed ideation process with three phases: DIVERGE, TRANSFORM, CONVERGE.

## Current State
@active_context.yaml

## Instructions

### Mode Detection

**If NO argument provided**: Run SCAN MODE first
- Analyze the project for improvement opportunities
- Present suggested challenges for brainstorming
- User selects one to proceed with Topic Mode

**If argument provided**: Run TOPIC MODE directly
- Use the provided challenge/topic
- Proceed directly to DIVERGE phase

---

## SCAN MODE (No Argument)

Analyze the project for improvement opportunities:

### 1. Code Quality Scan
- Search for TODO, FIXME, HACK, XXX comments
- Look for files with high complexity indicators
- Identify large files (>500 lines) that might need refactoring

### 2. State Pattern Analysis
- Review archive for recurring mismatches
- Check lessons for patterns that keep appearing
- Identify constraints that repeatedly cause friction

### 3. Architecture Review
- Look for missing error handling patterns
- Check for inconsistent naming conventions
- Identify potential performance bottlenecks

### 4. Reflection Analysis (v2.4)
- Load `.proof/archive.jsonl` and analyze scored objectives
- Identify checks that have failed 2+ times across sessions
- For each recurring weak check, auto-generate a challenge:

| Weak Check | Generated Challenge |
|------------|---------------------|
| mismatch_detection | "How might we detect mismatches earlier in the workflow?" |
| plan_revision | "How might we make plan revision feel natural rather than like failure?" |
| tool_switching | "How might we recognize tool limits faster and switch more fluidly?" |
| memory_update | "How might we make lesson capture automatic rather than manual?" |
| proof_generation | "How might we generate proof inline as a natural part of work?" |
| stop_condition | "How might we recognize uncertainty earlier and frame better questions?" |

These reflection-based challenges appear **first** in suggested challenges since they address systemic issues.

### 5. Output Scan Results

```
═══════════════════════════════════════════════════════════
PROJECT IMPROVEMENT SCAN
═══════════════════════════════════════════════════════════

Scanned: [project name]

FINDINGS:

Code Quality:
  • [file:line] TODO: [description]
  • [file:line] FIXME: [description]

Complexity Concerns:
  • [file] - [reason]

State Patterns:
  • [pattern] - appears N times in archive

Reflection Analysis:
  • Sessions scored: N
  • Recurring weak checks: [check_name] (failed N times)

SUGGESTED CHALLENGES:

🔴 From Reflection (systemic):
1. "How might we [improve weak check]?" ← addresses recurring failure

📊 From Code Analysis:
2. "How might we [code improvement]?"
3. "How might we [architecture improvement]?"

Select a challenge number, or provide your own topic.
═══════════════════════════════════════════════════════════
```

---

## TOPIC MODE (With Argument)

Run structured brainstorming on the provided challenge.

### PHASE 1: DIVERGE

#### Step 1.1 — Expert Activation

Generate a detailed expert persona for this challenge:

```
═══════════════════════════════════════════════════════════
EXPERT PERSONA ACTIVATED
═══════════════════════════════════════════════════════════

Name: [Full name with title]
Title: [Specific professional role]
Background: [15+ years, named institutions]
Notable Achievement: [Something establishing credibility]
Contrarian Belief: [Something most peers disagree with]
Cross-Domain Knowledge: [Unexpected field they draw from]

"I'll be approaching this challenge from the perspective of
[brief statement of their unique viewpoint]"
═══════════════════════════════════════════════════════════
```

#### Step 1.2 — Idea Generation Waves

**Wave A: Spectrum (6 ideas)**
Generate ideas ranging from obvious to unexpected:

| # | Type | Idea |
|---|------|------|
| 1 | Safe | The industry-standard approach |
| 2 | Modest | A small improvement on the standard |
| 3 | Combo | Combination of two existing approaches |
| 4 | Adjacent | Borrowed from adjacent industry |
| 5 | Unrelated | From completely unrelated field (biology, music, games) |
| 6 | Absurd | Seems crazy but might work |

**Wave B: Denial (3 ideas)**
Generate 3 solutions where NONE can use ANY mechanism from Wave A.
Pretend those approaches are physically impossible.

**Wave C: Perspective Shifts (3 ideas)**
| Perspective | Viewpoint | Idea |
|-------------|-----------|------|
| Child | A 10-year-old who doesn't know the rules | |
| Future | Someone from 2075 with tech we don't have | |
| Opposite | Expert from the exact opposite field | |

```
═══════════════════════════════════════════════════════════
DIVERGE COMPLETE - 12 Ideas Generated
═══════════════════════════════════════════════════════════

[List all 12 ideas with brief descriptions]

Select 4 most promising ideas for TRANSFORM phase (comma-separated):
═══════════════════════════════════════════════════════════
```

---

### PHASE 2: TRANSFORM

For each of the 4 selected ideas, apply SCAMPER:

#### SCAMPER Analysis

| Lens | Question | Variation |
|------|----------|-----------|
| **S**ubstitute | Replace core component with something from distant field | |
| **C**ombine | Merge with unrelated trend or technology | |
| **A**dapt | Borrow from nature, history, or another industry | |
| **M**odify | Make key dimension 10x larger/smaller/faster/slower | |
| **P**ut to Other Use | What unexpected secondary problem could this solve? | |
| **E**liminate | What if you removed what seems most essential? | |
| **R**everse | What if you did the exact opposite? | |

#### Cross-Domain Analogies

For top 3 transformed ideas, find parallels:

| Domain | Question | Transferable Principle |
|--------|----------|----------------------|
| Biology/Nature | What organism or ecosystem solved this? | |
| Game Design | What mechanic or rule system applies? | |
| History | What past event or campaign mirrors this? | |

```
═══════════════════════════════════════════════════════════
TRANSFORM COMPLETE - Ideas Evolved
═══════════════════════════════════════════════════════════

[Show transformed ideas with SCAMPER variations and analogies]

Proceeding to CONVERGE phase...
═══════════════════════════════════════════════════════════
```

---

### PHASE 3: CONVERGE

#### Step 3.1 — Score Each Transformed Idea

Rate 0-10 on each dimension:

| Idea | Novelty | Feasibility | Impact | Elegance | Total |
|------|---------|-------------|--------|----------|-------|
| ... | /10 | /10 | /10 | /10 | /40 |

- **Novelty**: How different from existing solutions?
- **Feasibility**: Can this actually be built/implemented?
- **Impact**: If successful, how significant?
- **Elegance**: Is this simpler than expected?

#### Step 3.2 — Adversarial Stress Test

For top 3 scoring ideas:

| Question | Idea 1 | Idea 2 | Idea 3 |
|----------|--------|--------|--------|
| What would DEFINITELY cause this to fail? | | | |
| What assumption might be wrong? | | | |
| Who would actively oppose this and why? | | | |
| Realistic worst-case scenario? | | | |

#### Step 3.3 — Synthesis

Combine strongest surviving elements into 2-3 hybrid concepts.

---

## FINAL OUTPUT

```
═══════════════════════════════════════════════════════════
BRAINSTORM COMPLETE
═══════════════════════════════════════════════════════════

Challenge: [original challenge]
Expert: [persona name]
Ideas Generated: 12 → Transformed: 4 → Final: 3

───────────────────────────────────────────────────────────
🏆 TOP RECOMMENDATION: [Name]
───────────────────────────────────────────────────────────

Core Idea (for a 10-year-old):
[One sentence explanation]

Why This Wins:
• Novelty: [What's genuinely new]
• Feasibility: [Why we can actually do this]
• Impact: [What changes if this works]

Cross-Domain Validation:
[Analogy proving the mechanism works]

Primary Risk + Mitigation:
[Risk] → [How to address it]

First 3 Actions:
1. [Action]
2. [Action]
3. [Action]

───────────────────────────────────────────────────────────
🥈 RUNNER-UP: [Name]
───────────────────────────────────────────────────────────

Core Idea: [One sentence]
Key Advantage: [Why keep this as backup]
Actions: [Brief list]

───────────────────────────────────────────────────────────
🃏 WILD CARD: [Name]
───────────────────────────────────────────────────────────

Core Idea: [One sentence]
Risk/Reward: [High risk but potentially transformative because...]
When to Consider: [Under what circumstances this becomes viable]

═══════════════════════════════════════════════════════════
NEXT STEPS
═══════════════════════════════════════════════════════════

→ /edge-plan "[top recommendation name]"
  Create implementation plan for the top recommendation

→ /edge-research "[specific aspect]"
  Deep dive on any uncertain aspects before committing

→ Save wild card to lessons for future consideration
═══════════════════════════════════════════════════════════
```

## Tips

- **Be genuinely creative** in DIVERGE - the absurd ideas often contain kernels of brilliance
- **Don't self-censor** - capture everything, filter later
- **Use the expert persona** - it helps break out of your usual thinking patterns
- **SCAMPER systematically** - force yourself through each lens even when it feels awkward
- **Stress test honestly** - the goal is to find weaknesses, not defend ideas
- **Synthesize boldly** - the best ideas often combine elements from multiple sources

## Arguments

- No arguments: Run scan mode first, then topic mode on selected challenge
- `"challenge text"`: Skip scan, run topic mode directly on provided challenge
