# Operator's Edge v2.6

A constant-memory, context-aware agent system with the 6-Check Adaptation Loop, External Research, Structured Brainstorming, Automated Reflection, Smart Lesson Management, and YOLO Mode.

## What's New in v2.6

- **YOLO Mode** (`/edge-yolo`) - Autonomous execution with guardrails for faster iteration
- **Reversibility-Gated Actions** - Auto-execute reversible actions (reads, tests), stage irreversible ones (edits, commits)
- **Action Batching** - Irreversible actions queue up for single-key batch approval
- **Trust Levels** - Configure per-action autonomy: `auto`, `supervised`, `blocked`
- **Session Status** - See YOLO mode stats (auto-executed, staged, blocked) at session start

## What's New in v2.5

- **Lesson Deduplication** - When adding lessons, similar existing ones are automatically reinforced instead of duplicating
- **Lesson Consolidation** - `/edge-prune` now merges similar lessons by theme (cross_platform, enforcement, memory_state, etc.)
- **Lesson Extraction** - `/edge-score` analyzes completed work and suggests lessons from mismatches, proofs, and constraints
- **Theme-Based Grouping** - Lessons are organized into 6 themes for better similarity detection
- **Backward Compatible** - Existing lessons work unchanged; new features enhance management

## What's New in v2.4

- **Reflection Analysis** - Automatically analyze score patterns across sessions, surface recurring weak checks
- **Improvement Suggestions** - Concrete tips for each of the 6 checks based on common failures
- **Auto-Generated Challenges** - `/edge-brainstorm` scan mode now generates "How might we..." challenges from recurring failures
- **Step Reminders** - `/edge-step` shows targeted reminders for checks you've struggled with
- **Score Trends** - Session start now shows your improvement trajectory

## What's New in v2.3

- **Modular Architecture** - Core utilities split into 6 focused modules (1719 → ~200 lines each)
- **Cleaner Code Organization** - `edge_config.py`, `state_utils.py`, `archive_utils.py`, `research_utils.py`, `brainstorm_utils.py`, `orchestration_utils.py`
- **Backward Compatible** - `edge_utils.py` facade re-exports everything; existing hooks work unchanged

> "When reality changes, do I change?"

## What's New in v2.2

- **Structured Brainstorming** (`/edge-brainstorm`) - Project scanning + 3-phase ideation (DIVERGE/TRANSFORM/CONVERGE) with expert personas
- **External Research Integration** (`/edge-research`) - Detect research needs, generate prompts for external deep research tools (Gemini, Perplexity, etc.)
- **Smart Orchestrator** (`/edge`) - One command that figures out what you need
- **Mismatch Detection** - Capture when reality diverges from expectations
- **Constant Memory** - Pruning system keeps state lean; completed work archives
- **Memory Decay** - Lessons that prove useful stay; unused ones fade
- **Self-Assessment** - Score yourself against the 6-check adaptation rubric

## What Gets Enforced

| Rule | How | Effect |
|------|-----|--------|
| No edits without a plan | PreToolUse hook | Edit/Write blocked until plan exists |
| No dangerous commands | PreToolUse hook | `rm -rf /`, `git reset --hard`, etc. blocked |
| No blind retries | PreToolUse hook | Commands failing 2+ times require new approach |
| Must modify state | Stop hook | Can't end session without updating active_context.yaml |
| Must have proof | Stop hook | Can't end session without work logged |

## Installation

### Prerequisites

- **Python 3.8+** installed and in your PATH
- **Claude Code** CLI installed

### Windows

```cmd
cd C:\path\to\your\project
python C:\path\to\operators-edge\setup.py
```

**Windows verification checklist**
1. Confirm files were created:
   - `.claude\settings.json`
   - `.claude\hooks\`
   - `.claude\commands\`
   - `active_context.yaml` (if missing before)
2. Open `.claude\settings.json` and verify:
   - Python command is `python` (not `python3`)
3. Restart Claude Code and run:
   - `/edge-context`
   - `/edge-plan` (if no objective yet)

### macOS / Linux

```bash
cd /path/to/your/project
python3 /path/to/operators-edge/setup.py
```

**Important:** Restart Claude Code after setup to load the new commands.

## Commands

| Command | Purpose |
|---------|---------|
| `/edge` | Smart orchestrator - figures out what you need |
| `/edge-plan` | Create or update your plan |
| `/edge-yolo` | Toggle YOLO mode, review staged actions, configure trust |
| `/edge-brainstorm` | Structured ideation - scan project or run 3-phase brainstorm |
| `/edge-research` | Scan for research needs, generate prompts for external LLMs |
| `/edge-research-results` | Process pasted research results, extract action items |
| `/edge-step` | Execute the current step |
| `/edge-mismatch` | Log when reality diverges from expectations |
| `/edge-adapt` | Revise the plan after a mismatch |
| `/edge-prune` | Archive completed work to keep state lean |
| `/edge-score` | Self-assessment against 6-check rubric |

## The 6-Check Adaptation Loop

1. **Mismatch Detection** - Spot divergences quickly
2. **Plan Revision** - Change approach, not just retry
3. **Tool Switching** - Abandon what doesn't work
4. **Memory Update** - Capture reusable lessons
5. **Proof Generation** - Evidence, not just claims
6. **Stop Condition** - Know when to escalate

## Workflow

1. **Start session** - Hooks inject current state, surface relevant memory
2. **Run `/edge`** - Orchestrator guides you to the right action
3. **Enable YOLO mode** - `/edge-yolo on` for autonomous iteration
4. **Research if needed** - `/edge-research` generates prompts, paste results back with `/edge-research-results`
5. **Work step by step** - Mark steps `in_progress` → `completed`
6. **Review staged actions** - `/edge-yolo approve` to batch approve edits
7. **On mismatch** - Run `/edge-mismatch`, then `/edge-adapt`
8. **Before ending** - Run `/edge-prune` to archive, `/edge-score` to assess

## Release / Dist Sync

`dist/operators-edge` is a generated artifact and should not be edited directly.

Before releasing or distributing:

```bash
# 1) Check for drift (fails if dist differs from source)
python3 tools/build_dist.py --check

# 2) Regenerate dist if needed
python3 tools/build_dist.py
```

If `--check` reports mismatches, re-run the build and re-check.

## YOLO Mode

YOLO mode enables autonomous execution with safety guardrails:

```
/edge-yolo on       # Enable autonomous mode
/edge-yolo          # Check status and staged actions
/edge-yolo approve  # Batch approve all staged actions
/edge-yolo off      # Return to normal confirmation flow
```

### How It Works

| Action Type | Trust Level | Behavior |
|-------------|-------------|----------|
| Read, Glob, Grep, git status | `auto` | Execute immediately |
| Edit, Write, git add/commit | `supervised` | Stage for batch approval |
| git push, rm, kubectl, aws | `blocked` | Always require confirmation |

### Custom Trust Levels

```
/edge-yolo trust Edit auto         # Auto-approve all edits (risky)
/edge-yolo trust "bash:npm" blocked  # Always confirm npm commands
/edge-yolo reset                    # Return to defaults
```

> "Trust, but verify... later, in batches."

## Research Flow

When objectives involve unfamiliar territory:

```
/edge-plan "Build real-time collaborative editor"
    │
    ▼
┌─────────────────────────────────────┐
│ Orchestrator detects research need  │
└─────────────────────────────────────┘
    │
    ▼
/edge-research
    │
    ▼
┌─────────────────────────────────────┐
│ Copy prompt to Gemini/Perplexity    │
│ Paste results back                   │
└─────────────────────────────────────┘
    │
    ▼
/edge-research-results R001
    │
    ▼
Action items extracted, planning continues
```

## Files Created

```
your-project/
├── active_context.yaml     # Your plan and progress (the "mind")
├── CLAUDE.md               # Instructions for Claude
├── .claude/
│   ├── settings.json       # Hook configuration
│   ├── hooks/              # Enforcement scripts
│   │   ├── edge_utils.py   # Facade (~230 lines, re-exports from modules)
│   │   ├── edge_config.py  # Constants and SessionContext
│   │   ├── state_utils.py  # YAML parsing, paths, hashing
│   │   ├── archive_utils.py # Archive and pruning system
│   │   ├── research_utils.py # Research detection and prompts
│   │   ├── brainstorm_utils.py # Project scanning
│   │   ├── orchestration_utils.py # Context detection, memory
│   │   ├── yolo_config.py  # YOLO mode trust levels
│   │   ├── session_start.py
│   │   ├── pre_tool.py
│   │   ├── post_tool.py
│   │   └── stop_gate.py
│   ├── commands/           # Slash commands
│   │   ├── edge.md
│   │   ├── edge-plan.md
│   │   ├── edge-yolo.md
│   │   ├── edge-brainstorm.md
│   │   ├── edge-research.md
│   │   ├── edge-research-results.md
│   │   ├── edge-step.md
│   │   ├── edge-mismatch.md
│   │   ├── edge-adapt.md
│   │   ├── edge-prune.md
│   │   └── edge-score.md
│   └── state/              # Session state (auto-managed)
└── .proof/
    ├── session_log.jsonl   # Proof of all actions
    └── archive.jsonl       # Archived completed work
```

## The Internal State Contract

**LIVE (in active_context.yaml):**
- Current objective
- Active steps only (pending/in_progress)
- Open questions
- Active constraints
- High-value lessons (reinforced 2+)

**ARCHIVED (in .proof/archive.jsonl):**
- Completed steps with proofs
- Resolved mismatches
- Past objectives
- Superseded lessons

## Troubleshooting

### "python is not recognized" (Windows)
Python isn't in your PATH. Reinstall Python and check "Add Python to PATH".

### Commands not showing up
Restart Claude Code after running setup.

### Hooks not running
Check `.claude/settings.json` has the correct Python command (`python` on Windows, `python3` on Mac).

## Schema Reference

See `docs/schema-v2.md` for the complete schema specification.

## License

MIT
