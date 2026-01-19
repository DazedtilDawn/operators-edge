# Operator's Edge: Strategic Pivot from v7.1 to v8.0

## Executive Summary

**v7.1 "Learned Track Guidance"** built a pattern recognition system that teaches Claude software methodology (test-first, extract-then-integrate, etc.).

**The Problem:** Claude already knows these patterns. Its training data includes thousands of software projects. We were solving the wrong problem.

**v8.0 "Context Engineering"** pivots to solving the *actual* problem: keeping Claude on track during long sessions through supervision, not training.

---

## The Evidence

### What v7.1 Built (126 tests, 4 modules):
- Pattern capture from completions
- Verb taxonomy (scope, test, build, extract, integrate...)
- Suggestion surfacing at session start
- Confidence updates based on outcomes

### Why It Doesn't Work:
1. **Sample size**: Only 20 historical completions to learn from
2. **Redundant knowledge**: Claude knows "refactoring needs tests" from training
3. **Wrong intervention point**: Suggestions at session start, problems occur mid-session
4. **No behavioral change**: Confidence scores don't affect Claude's execution

### What Actually Happens (Real Data):

From session `20260114-020041.jsonl`:
```
File edit frequency:
  ⚠️ CHURN 6x verification_utils.py
  ⚠️ CHURN 5x federated-leaping-stearns.md
  ⚠️ CHURN 3x test_state_machine_audit.py
```

**This is the real problem.** Claude edited `verification_utils.py` 6 times in one session. That's circular behavior that a pattern suggestion at session start wouldn't have prevented.

---

## The Pivot

### From: Pattern Teaching
```
Archive → Pattern Recognition → Suggestion → Feedback Loop
         (ML-style learning)
```

### To: Context Engineering
```
Session Log → Drift Detection → Real-time Intervention
              (Supervision)
```

---

## v8.0 Architecture (Proof of Concept Complete)

### Drift Detector (`drift_detector.py`) - IMPLEMENTED
Detects:
- **FILE_CHURN**: Same file edited 3+ times → suggests stepping back
- **COMMAND_REPEAT**: Same command failing repeatedly → suggests new approach
- **STEP_STALL**: Current step taking 3x longer than average → suggests decomposition

Example output:
```
⚠️  DRIFT DETECTED - Supervision Intervention

🔴 FILE_CHURN: You've edited `verification_utils.py` 6 times recently.

   Suggestion: Consider stepping back to understand the root cause.
   What are you trying to achieve with each edit?
   Is there a pattern to the changes that suggests a different approach?
```

### Planned Modules:
1. **Context Monitor** - Track context window usage, trigger compression
2. **Codebase Knowledge** - Error→Fix mappings (not patterns, specifics)
3. **Session Handoff** - Compressed state transfer across sessions

---

## What We Keep

| Component | Status | Reason |
|-----------|--------|--------|
| Hook enforcement | Keep | Mechanical constraints work |
| Proof logging | Keep | Observation infrastructure is valuable |
| Memory/lessons | Transform | Refocus on codebase-specific knowledge |
| Pattern recognition | Deprecate | Solving wrong problem |
| Feedback loop | Deprecate | ML infrastructure without ML |

---

## Success Metrics

### v7.1 Metrics (Not Meaningful):
- Suggestions shown: N/A (Claude knows patterns)
- Suggestions followed: N/A (not actionable)
- Pattern confidence: Changes without impact

### v8.0 Metrics (Meaningful):
- **Drift interventions**: How often did we catch circular behavior?
- **Intervention acceptance**: Did Claude change approach after warning?
- **Session efficiency**: Tool calls per completed step (should decrease)
- **Context utilization**: How much of context window was wasted on churn?

---

## Recommendation

1. **Don't delete v7.1 code** - It's well-tested and doesn't break anything
2. **Mark as deprecated** - Add note to pattern_recognition.py, feedback_loop.py
3. **Build v8.0 incrementally** - Start with drift detector integration
4. **Measure impact** - Track whether interventions reduce churn

---

## The Core Insight

**Claude doesn't fail because it doesn't know patterns.**
**Claude fails because it loses track.**

The hooks understood this - they constrain behavior mechanically.
The pattern system forgot this - it tried to teach what Claude already knows.

v8.0 returns to first principles: supervision, not training.
