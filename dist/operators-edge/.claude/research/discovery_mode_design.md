# Reimagining Scout: From Janitor to Innovator

> **Status:** IMPLEMENTED as v3.1 Discovery Mode (2025-12-30)
> **Coverage:** ~90% of proposal implemented

You asked me to ultrathink. To breathe. To find the solution that feels inevitable.

Here is the truth: The "Product Manager" proposal (todo.md parsing) is boring. It turns your agent into a glorified task-runner. It asks, "What work has the human defined for me?"

That is not the future.

The future is an agent that asks: **"Based on everything we've done, what should we build next?"**

We are going to build **Discovery Mode**.

## The Vision: Self-Evolving Intelligence

Right now, your Scout looks at the *code* (`.py` files) and finds maintenance issues (complexity, missing tests). It's a janitor.

**Discovery Mode** will look at the *experience* (`archive.jsonl`, logs, lessons) and find **innovation opportunities**.

It turns the system's history into a roadmap.

| Current Scout (The Janitor) | Discovery Scout (The Innovator) |
|-----------------------------|---------------------------------|
| "This function is too complex." | "You've manually pruned state 10 times. I should build an auto-pruner." |
| "This file has no tests." | "You've struggled with Git mismatches 40% of the time. I should build a Git Safety Wrapper." |
| "There are TODOs here." | "You consistently reinforce the 'research' lesson. I should integrate the research tool." |

## Why This Is The Only Path

1.  **It Uses Your Unfair Advantage:** You have 84+ archived sessions. Most agents have zero memory. That archive isn't just logs; it's training data for what causes you pain.
2.  **It Closes the Loop:** The system doesn't just execute; it *learns* from the execution to propose better tools for the execution.
3.  **It scales:** The more you work, the more data it has, the smarter the suggestions get.

## The Architecture: `DiscoveryScanner`

We don't need a `todo.md` parser. We need **Pattern Miners**.

### 1. The Schema (The "WorkItem" Evolved)

We introduce a `DiscoveryFinding` that sits alongside `ScoutFinding`.

```python
@dataclass
class DiscoveryFinding:
    id: str
    title: str                  # "Feature: Auto-Prune System"
    trigger: str                # "High Workflow Friction"
    evidence: str               # "User manually pruned 12 times in last 50 steps"
    proposal: str               # "Implement auto_prune_threshold in session_start.py"
    value_score: int            # 0-100 (Frequency * Impact)
    impl_complexity: str        # Low/Medium/High
```

### 2. The Miners (The Brains)

We implement three specific miners to start:

#### A. The Friction Miner (Log Analysis)
Reads `session_log.jsonl`. Looks for repeated manual commands.
*   *Detection:* "User runs `/edge-prune` immediately after `High Entropy` warning."
*   *Proposal:* "Add `auto_prune_config` to automate this step."

#### B. The Pain Miner (Archive Analysis)
Reads `archive.jsonl`. Looks for clusters of `mismatch` or `failure`.
*   *Detection:* "40% of mismatches involve `git push` or `git commit`."
*   *Proposal:* "Create `git_safe_mode` wrapper to pre-validate states."

#### C. The Gap Miner (Capability Analysis)
Looks at available tools vs. actual usage.
*   *Detection:* "ClickUp MCP is loaded but we only utilize `get_tasks`, never `create_task`."
*   *Proposal:* "Implement `report_bug_to_clickup` command."

## The User Experience

When you run Scout, you don't just see "Clean up this code." You see a menu of **Upgrades**.

```text
════════════════════════════════════════════════════════════════
SCOUT REPORT: SYSTEM EVOLUTION
════════════════════════════════════════════════════════════════

MAINTENANCE (The Chores)
────────────────────────────────────────────────────────────────
  [1] Refactor complex function: parse_yaml_block (Score: 20)
  [2] Add missing tests: validator.py

DISCOVERY (The Upgrades)
────────────────────────────────────────────────────────────────
  [3] ★ FEATURE: Auto-Prune System
      Why: You manually pruned 12 times this week.
      Value: High | Effort: Low

  [4] ★ TOOL: Git Safety Wrapper
      Why: 40% of recent mismatches were Git-related.
      Value: Medium | Effort: Medium
```

## The Execution Plan

We don't need to rewrite the universe. We can inject this soul into the machine in 3 steps:

1.  **Define `DiscoveryFinding`**: A simple data structure in `scout_scanner.py`.
2.  **Build One Miner**: The **Archive Pain Miner** is the easiest high-value target. It just reads JSONL and counts mismatch keywords.
3.  **Update Display**: Show these findings in the Scout report.

This transforms the agent from a passive tool into an active partner. It notices your pain and offers to fix it.

---

## Implementation Notes (Added Post-Implementation)

### What Was Built

| Proposed | Implemented | File |
|----------|-------------|------|
| DiscoveryFinding schema | DiscoveryFinding + DiscoveryEvidence | `discovery_config.py` |
| Pain Miner | `scan_archive_pain()` | `discovery_scanner.py` |
| Gap Miner | `scan_integration_gaps()` | `discovery_scanner.py` |
| Friction Miner | Replaced with `scan_lesson_reinforcement()` | `discovery_scanner.py` |
| Combined display | `format_combined_report()` | `scout_scanner.py` |

### Future Enhancement

The **Friction Miner** (session_log.jsonl analysis for repeated command patterns) was not implemented. The Lesson Reinforcement Analyzer captures similar patterns at a higher abstraction level, but direct command sequence analysis could complement it.
