# Trustworthy Autonomy Spec (TAS) v1.0

**Goal:** A rail you can trust that (1) runs autonomously, (2) stops only at real junctions, and (3) gets measurably better over time—**without expanding user-facing surface area** (no new commands; only stronger internal contracts).

---

## 0) Non-negotiables

1. **Mechanical > behavioral.** If it matters, it must be enforced by hooks/state, not "Claude remembers."
2. **Autonomy must be bounded.** Hard safety limits (iterations, stuck threshold) and "stop at junctions" are mandatory.
3. **No silent success.** Errors must surface truthfully; transitions must not pretend success.
4. **State + proof are the source of truth.** Stop gate enforces "state changed" + "proof exists".

---

## 1) User Contract: "Autonomy You Can Trust"

### Primary user experience

* You run: **`/edge-yolo on`**.
* The system loops autonomously until:
  * objective complete, or
  * it reaches a **junction** requiring your decision, or
  * it hits a safety bound (iterations/stuck), or
  * it needs clarification (true ambiguity).
* When it stops, it must present:
  * *what it tried*,
  * *what it observed*,
  * *what it proposes next*,
  * *exactly what decision you need to make* (approve/skip/dismiss/stop).

### "Less responsibility" guarantee

You should never have to:
* babysit routine step execution,
* remember to collect proof (automatic via PostToolUse),
* remember to prune (autopilot does it when entropy is high),
* manually convert mismatches into reusable lessons (prune extracts lessons from resolved mismatches).

---

## 2) Surface Area Freeze

**Allowed user-facing commands remain exactly:**
* `/edge` (hook-driven gear engine)
* `/edge-prune` (hook-driven prune + auto edge-loop)
* `/edge-yolo` (autopilot)
* plus existing subcommands: `/edge-plan`, `/edge-step`, `/edge-score`, `/edge-verify`, `/edge-loop`

**We are allowed to change:**
* internal state schemas (versioned),
* hook behavior,
* how `/edge-yolo` is implemented (mechanical vs prompt-only),
* metrics and how they're computed.

---

## 3) Canonical State + Single Truth

### Canonical files (authoritative)

* `active_context.yaml` (intent + plan + risks + runtime state)
* `.proof/session_log.jsonl` (proof log)
* `.proof/archive.jsonl` (long memory)

### Drift-killer requirement

**SessionStart output must reflect Dispatch Mode reality.**
SessionStart must show **Dispatch Mode** status from `dispatch_utils.get_dispatch_status()`, not legacy YOLO state.

---

## 4) Autonomy Rail (mechanical loop, junction-only stops)

### Junction taxonomy (workflow-level)

* `irreversible`, `external`, `ambiguous`, `blocked`, `none`

**Requirement:** `/edge-yolo` must pause *only* on junctions. Routine work must proceed automatically.

### Tool-level safety (hard gates)

PreTool gate must remain authoritative:
* hard-block destructive commands
* ask confirmation on risky commands
* block blind retries after repeated failures
* require plan + risks before edits (or explicit confirmation)

### Mechanical "done gate"

Stop gate: cannot end session unless:
* `active_context.yaml` hash changed
* `.proof/session_log.jsonl` exists and has entries

---

## 5) Learning Rail (Memory That Changes Behavior)

### Requirement: "Memory must be present at decision time"

Before executing any step in autopilot (or before any risky action):
1. Build context: `objective + current_step.description + planned action`
2. Call `surface_relevant_memory(state, context)` to pull **top 3** lessons
3. Inject those lessons into the step execution prompt

### Requirement: "Reinforcement tied to outcomes"

After a step completes successfully:
* Reinforce every memory trigger that was *used* (referenced in step execution)
* Reinforcement only when there is proof-backed success

### Requirement: "Failures become structured learning"

* Every failure that causes a block/junction must produce a mismatch candidate
* When resolved, it must be pruned/archived to become memory

### Requirement: "Evergreen principles"

* `memory[].evergreen: true|false`
* `identify_decayed_memory` must skip evergreen items

---

## 6) Metrics That Drive Decisions

### Outcome-based Scorecard (per objective)

Compute and persist at objective completion:

1. **Objective Success:** completed vs not completed
2. **Efficiency:** dispatch iterations / steps completed
3. **Junction Rate:** junctions_hit / total_iterations
4. **Stuck Events:** count of stuck threshold hits
5. **Quality:** quality gate pass/fail, eval invariant failures
6. **Learning Impact:** new memory items, reinforcements, repeat-mismatch rate

### Autonomy Governor (self-tuning)

Based on last N objectives:
* If quality failures rise or stuck events increase → reduce autonomy (more junctions)
* If success high and efficiency improves → increase autonomy (fewer pauses)

---

## 7) Quality Enforcement Upgrade

### Step completion must be verifiable

When a step is marked `completed`, require at least one:
* verification command output in proof log, or
* explicit proof artifact path, or
* explicit documented skip reason

---

## 8) Implementation Phases

### Phase A — Make the UI truthful (drift-killer)
* Update SessionStart to display Dispatch Mode status from `dispatch_utils.get_dispatch_status()`
* Stop referencing legacy yolo_state in the banner

### Phase B — Make `/edge-yolo` mechanical (trust leap)
* Convert `/edge-yolo` from prompt-only loop into hook-driven loop
* Use `dispatch_utils` as the control plane

### Phase C — Couple memory to execution
* At each autopilot action, surface top 3 lessons via `surface_relevant_memory`
* After successful completion, reinforce used triggers via `reinforce_memory`

### Phase D — Outcome scorecard + governor
* On objective completion, write autonomy scorecard into archive
* Detect recurring weak checks and bias behavior accordingly

---

## 9) Acceptance Criteria

1. **Autopilot reliability**
   * `/edge-yolo on` runs until completion or junction, respecting limits

2. **Junction correctness**
   * Any irreversible/external action pauses (junction_state is sole truth)

3. **Proof integrity**
   * Every tool use logged with tool + input_preview + success + output_preview

4. **Learning loop**
   * At least one objective shows: memory surfaced → applied → reinforced

5. **Self-improvement**
   * Over 5+ objectives, scorecard shows improvement in efficiency or reduction in repeat mismatches

---

## Summary

**Autonomy without mechanical rails is unsafe; rails without outcome-coupled learning are busywork.**

The only path that satisfies "trust + learning + hands-off" is:
**mechanical autonomy loop + memory-at-decision-time + outcome scorecard that self-tunes.**
