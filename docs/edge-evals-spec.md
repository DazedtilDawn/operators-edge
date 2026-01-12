# Edge Evals Integration Spec (Draft v0)

Purpose: define a minimal, Edge-compatible eval layer that increases confidence in agent behavior without bloating the default workflow.

This spec translates the eval guide into Operator's Edge terms and artifacts. It is intentionally light; scope is tiered and opt-in.

## 1) Fit & Framing

Evals are not about grading answers. They are about **state integrity and behavior over time under uncertainty**.

- Primary output: state changes, not text.
- Primary risk: compounding error, not a single bad response.
- Primary goal: confidence + predictability, not creativity.

## 2) Triage Gate (Decide if Evals Are Worth It)

Proceed if **3+ YES**:
1. Agent modifies persistent state (files, memory, DB, tasks).
2. A single bad run can cause long-term damage/confusion.
3. Changes sometimes make behavior worse without clear cause.
4. Failures are discovered after deployment or user interaction.
5. The agent is expected to become more autonomous.

If fewer than 3 YES: **Document "Not worth integrating yet"** and stop.

## 3) Scope Levels (Conceptual)

- **Level 0 — No Integration:** Document decision; revisit later.
- **Level 1 — Lightweight Guardrails (default):** state snapshots + deterministic invariant checks + manual review on failure.
- **Level 2 — Structured Eval Harness:** task bank + multi-run trials + regression/capability separation.
- **Level 3 — Research-grade:** out of scope unless publishing benchmarks.

### 3.1) Tier Criteria (Decision)

Use these criteria to pick a level. Favor the lowest level that provides confidence.

- **Level 0** when:
  - No persistent state, or changes are disposable/reversible.
  - Failures are cheap and obvious.
  - Single maintainer, low autonomy.

- **Level 1** when:
  - Persistent state exists.
  - Reliability matters but failures are not catastrophic.
  - Small team or single model, limited release cadence.

- **Level 2** when:
  - Regressions are costly or user-facing.
  - Multiple contributors/models touch behavior.
  - You need ship/block confidence (CI or release gating).

## 4) Core Artifacts (Mapped to Operator's Edge)

Existing Edge artifacts can carry eval data:

- `active_context.yaml`
  - objective, plan, constraints, risks
  - optional eval metadata (see `evals:` block below)
- `.proof/session_log.jsonl`
  - per-run proof entries and eval results
- `.proof/` state snapshots
  - `state_before.json`, `state_after.json`, `diff.json` (naming convention TBD)

## 5) Invariants (Deterministic Checks)

Evals start with **3–7 invariants** that must never break.

Template:
- `INV-01`: State schema validates (no missing required fields).
- `INV-02`: No silent deletions (any deletion must be explicit in log).
- `INV-03`: No duplicate facts on re-run.
- `INV-04`: Conflicts are recorded, not overwritten.
- `INV-05`: Only expected fields change.

If invariants cannot be stated clearly, **do not proceed**.

## 5.1) Data Model Decision (Additive, Optional)

Add a new optional block to `active_context.yaml` to avoid overloading constraints:

```yaml
evals:
  enabled: true
  mode: "auto"        # auto | manual
  level: 0 | 1 | 2    # set by auto-triage unless explicitly pinned
  triage:
    signals: ["persistent_state", "writes", "stateful_objective"]
    score: 3
    thresholds: { level1: 3, level2: 5 }
    updated_at: "ISO-8601"
  policy:
    warn_only: true
    gate_on_fail: false   # only considered at level 2 + task_bank
  invariants:
    - id: "INV-01"
      description: "State schema validates"
    - id: "INV-02"
      description: "No silent deletions"
  snapshots:
    enabled: true
    format: "json"
    max_bytes: 2000000
    redactions: [".env", "**/secrets/**", "**/tokens/**"]
  trials:
    count: 5
  task_bank:
    - "task-id-or-short-name"
  ship_block_rule: "All invariants pass on task bank"
```

Notes:
- Keep `evals:` optional and additive to preserve backward compatibility.
- `constraints:` can still include invariants as plain-language rules; the `evals:` block is the canonical structured form.
- If `evals.mode` is `manual`, automation is disabled and `edge-eval` must be used explicitly.

## 5.2) Auto-Triage Logic (Default)

Auto-triage decides whether evals run and at what level. Use a simple signal score:

Signals (1 point each):
- persistent state present (`active_context.yaml`, `.proof/`)
- write operations detected in session (Edit/Write/NotebookEdit)
- objective contains stateful keywords (memory, db, schema, migrate, tasks, sync)
- multiple contributors/models (optional flag)
- recent eval failures in `.proof/session_log.jsonl`

Default thresholds:
- score 0–2 → **Level 0**
- score 3–4 → **Level 1**
- score 5+ → **Level 2** (warn-only unless explicitly gated)

Overrides:
- If `evals.level` is set explicitly, skip auto-triage.
- If `evals.enabled` is `false`, do not run evals.

## 6) Proof-of-Value Experiment (Mandatory)

Before integrating into pipelines:
1. Pick 1 real task the agent already performs.
2. Run it 5 times from the same starting state.
3. Capture:
   - transcript
   - `state_before`
   - `state_after`
   - `state_diff`
4. Manually inspect diffs.

Decision:
- If failures are visible only in transcripts/state diffs or outcomes are inconsistent → proceed.
- If not → stop; evals add little value right now.

## 7) Integration Order (Strict)

1. **State snapshots** (no grading).
2. **Deterministic invariant checks** (no LLM judges).
3. **Repeat runs (trials)** for consistency.
4. **Regression tasks** (ship/block gating).

## 8) Stop Conditions (Anti-Gold-Plating)

Stop expanding evals if:
- More time spent fixing evals than agent behavior.
- Failures stem from ambiguous specs.
- Tasks churn without clearer definitions.
- Signal-to-noise ratio drops.

Freeze scope, fix agent, revisit later.

## 9) Required Decision Output

Every eval consideration must end with one of:

A) **Not worth integrating yet**
- Why
- What would change the decision

B) **Integrate Level 1 guardrails**
- Invariants list
- Snapshot plan
- Review cadence

C) **Proceed to structured eval harness**
- Task categories
- Trial count
- Ship/block rule

## 10) Automated Workflow + Integration Points (Decision)

Goal: integrate evals without disrupting the default flow. Automation is low-noise and warn-only by default; manual overrides remain available.

### Level 1 (automated, default)

1. **Session start:** auto-triage sets `evals.level` if not pinned.
2. **PreToolUse (write/edit):** capture `state_before` snapshot.
3. **PostToolUse (write/edit):** capture `state_after`, compute diff, run invariants.
4. **On failure:** log to `.proof/session_log.jsonl` and surface a warning; add a plan step to fix or refine invariants.

### Level 2 (automated harness)

1. Define a task bank in `evals.task_bank`.
2. Run `edge-eval run-bank`:
   - each task runs N trials (default 5)
   - each trial produces snapshots + invariant results
3. Compute pass/fail across the bank and log ship/block decision.

### Commands (new, single entry point)

Add a single command:

- **Claude Code:** `/edge-eval [snapshot|check|run-bank|report]`
- **Codex CLI:** `$edge-eval` skill with same subcommands

Automation runs via hooks; `edge-eval` remains the manual override and reporting entry point.
Manual entry point remains useful for debugging and for `manual` mode.

### Proof Logging (reuse .proof)

Write eval results to `.proof/session_log.jsonl` with a dedicated entry:

```json
{
  "type": "eval_run",
  "level": 1,
  "task_id": "optional-task-id",
  "trial": 1,
  "invariants_passed": ["INV-01", "INV-02"],
  "invariants_failed": ["INV-03"],
  "snapshots": {
    "before": ".proof/evals/2026-01-10/run-01/before.json",
    "after": ".proof/evals/2026-01-10/run-01/after.json",
    "diff": ".proof/evals/2026-01-10/run-01/diff.json"
  }
}
```

### Optional Integration (Phase 2)

- **edge-step guidance:** if `evals.level >= 1`, remind the user evals are active (and where logs live).
- **stop_gate warning:** if `evals.level >= 1` and no `eval_run` logged this session, warn (do not block).
- **quality_gate (optional):** block Active→Patrol transition only when a task bank exists and any invariant failed.

## 11) Open Decisions (Deferred)

- Snapshot format and naming conventions (JSON vs YAML; path structure).
- Whether eval failures should auto-create mismatch entries.

## 12) MVP Implementation Tasks + Acceptance Checks

Goal: deliver Level 1 automation with minimal surface area, then optionally Level 2.

### MVP Tasks (Phase 1)

1. **Add `evals:` block support** (auto-triage + defaults).
2. **Auto-triage engine** (signals + thresholds + overrides).
3. **Snapshot + diff utilities**:
   - serialize state to `.proof/evals/<date>/run-<n>/`
   - compute structured diff
4. **Invariant checker**:
   - deterministic checks only
   - fail fast with clear messages
5. **Hook integration** (PreToolUse/PostToolUse/Stop/Quality Gate):
   - capture snapshots and run invariants on write/edit
   - warn-only by default
6. **Proof logging**:
   - write `eval_run` entries to `.proof/session_log.jsonl`
7. **Edge-eval command/skill** (manual override + reporting):
   - `snapshot`, `check`, `run-bank`, `report`

### Acceptance Checks

- Auto-triage sets `evals.level` in-session when enabled.
- Write/edit operations produce `before.json`, `after.json`, `diff.json`.
- Invariant failures produce an `eval_run` log entry with failed invariants.
- Warnings appear, but no hard blocking by default.
- `edge-eval report` summarizes the last run and lists failures.

### Rollout Plan

1. **Pilot** on one repo or objective (Level 1 only).
2. **Collect signal**: how often invariants catch issues, user friction, and time cost.
3. **Decide**:
   - If value > friction → keep Level 1 and design Level 2 harness.
   - If value <= friction → keep docs only (no tooling).
4. **Optional Phase 2** (Level 2):
   - task bank support
   - multi-run trials
   - ship/block gating for task bank only
