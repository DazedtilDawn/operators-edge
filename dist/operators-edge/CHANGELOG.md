# Operator's Edge - Changelog

This file contains the version history of Operator's Edge. Previously stored as comments in `active_context.yaml`, now properly maintained as documentation.

---

## v8.0 - Context Engineering (Strategic Pivot)

**Paradigm Shift:** From teaching Claude patterns to keeping Claude on track.

### The Insight
Claude already knows software methodology patterns from training. The real problem
is context window exhaustion and circular behavior during long sessions.

### Phase 1: Drift Detection (`drift_detector.py`) ✓
- **FILE_CHURN**: Detects same file edited 3+ times → suggests stepping back
- **COMMAND_REPEAT**: Detects same command failing repeatedly → suggests new approach
- **STEP_STALL**: Detects current step taking 3x longer than average → suggests decomposition
- Integrated into `post_tool.py` - surfaces warnings in real-time after Edit/Write/Bash
- 24 tests

### Phase 2: Context Monitor (`context_monitor.py`) ✓
- **Token Estimation**: Tracks accumulated input/output, files read, conversation overhead
- **Usage Thresholds**: Info at 60%, Warning at 75%, Critical at 90%
- **Session Duration**: Warns at 45 min, critical at 90 min
- **Checkpoint Generation**: Creates compressed summaries for session continuity
- Integrated into `pre_tool.py` - surfaces warnings before tool execution
- 33 tests

### Phase 3: Codebase Knowledge (`codebase_knowledge.py`) ✓
- **Error → Fix Mappings**: Records what fixed errors for future reference
- **Error Signature Extraction**: Normalizes Python/JS/general errors for matching
- **Confidence Decay**: Older fixes decay in confidence over 30 days
- **Co-change Patterns**: Tracks files that change together
- **Related Files**: Surface files that usually change with current file
- 31 tests

### Phase 4: Session Handoff (`session_handoff.py`) ✓
- **Handoff Generation**: Creates structured summary at session end
- **Approach Extraction**: Identifies what was tried and outcomes (success/failure)
- **Drift Warning Carry-forward**: Passes drift signals to next session
- **Churn Detection**: Highlights files that needed multiple edits
- **Handoff Injection**: Surfaces handoff at session start for continuity
- Integrated into `session_start.py` - shows previous session context
- Integrated into `stop_gate.py` - auto-generates handoff at session end
- 23 tests

### Full Integration (Codebase Knowledge)
All v8.0 modules are now fully integrated into the hook system:

**post_tool.py (PostToolUse)**:
- Drift detection after Edit/Write/Bash
- Known fix lookup on Bash failures
- Fix learning when failures are resolved
- Co-change pattern tracking across files

**pre_tool.py (PreToolUse)**:
- Context window monitoring
- Related files surfacing from codebase knowledge

**session_start.py (SessionStart)**:
- Previous session handoff injection

**stop_gate.py (Stop)**:
- Automatic handoff generation at session end

### Deprecated (Preserved, Not Extended)
- `pattern_recognition.py` - v7.1 pattern matching (Claude knows patterns)
- `feedback_loop.py` - v7.1 confidence updates (ML infrastructure without ML)

### Documentation
- `docs/v8-architecture-plan.md` - Full architecture design
- `docs/v8-architecture-diagram.md` - Visual diagrams
- `docs/v8-strategic-pivot.md` - Executive summary of the pivot

### Phase 5: Session Metrics (`session_metrics.py`) ✓
**Purpose:** Measure whether v8.0 actually helps

- **Drift Metrics**: Track signals fired, interventions shown, course corrections
- **Fix Metrics**: Track fixes surfaced, followed, successful, learned
- **Handoff Metrics**: Track generation, usage, time-to-first-action
- **Context Metrics**: Track peak usage, compression recommendations, session duration
- **Aggregation**: Roll up metrics across sessions for effectiveness reporting
- Integrated into `post_tool.py` - records drift signals and fix events
- Integrated into `pre_tool.py` - records context usage
- Integrated into `stop_gate.py` - saves final metrics at session end
- 37 tests

### Phase 6: Smart Suggestions (`smart_suggestions.py`) ✓
**Purpose:** Move from passive surfacing to active guidance

- **Auto-Fix Offers**: Surface known fixes with actionable prompts
- **Related File Warnings**: Alert when modifying files that usually change together
- **Checkpoint Reminders**: Proactive reminders at 75%+ context usage
- **Drift Prevention**: Warn before file churn/command repeat becomes a problem
- **Pattern Nudges**: Contextual reminders (test files → run tests, package.json → npm install)
- **Cooldown System**: Prevents nagging with 5-minute cooldown per suggestion type
- Integrated into `pre_tool.py` - surfaces suggestions before tool execution
- 35 tests

### Phase 7: Effectiveness Analysis (`effectiveness_analyzer.py`, `course_correction.py`, `metrics_cli.py`) ✓
**Purpose:** Close the feedback loop - measure if v8.0 actually helps

- **Effectiveness Analyzer**: Calculates drift effectiveness, fix hit rate, handoff adoption, context efficiency
- **Course Correction Detection**: Infers whether drift signals led to behavior changes
  - FILE_CHURN correction: Did Claude stop editing the problem file?
  - COMMAND_REPEAT correction: Did Claude try a different approach?
- **Metrics CLI**: `/edge metrics` command for visibility
  - Compact report with visual bars
  - Detailed report with all metrics
  - JSON export for analysis
- **Adaptive Thresholds**: Thresholds auto-tuned based on effectiveness data
  - `/edge metrics --tune` applies recommended adjustments
  - Thresholds stored in `.proof/v8_config.json`
- **Configurable Detection**: `drift_detector.py` now loads thresholds from config
- 50 new tests (26 effectiveness_analyzer + 24 course_correction)

### Phase 8: Active Intervention (`active_intervention.py`) ✓
**Purpose:** Move from passive observation to active supervision

**The Problem:** Phase 7 data showed only 7% drift correction rate. Signals fire but
don't lead to behavior changes. Passive surfacing isn't enough.

**The Solution:** Escalating intervention levels based on session health:
- **observe**: Just track, no intervention (for healthy sessions)
- **advise**: Surface context and suggestions (default level)
- **guide**: Inject known fixes prominently, proactive warnings
- **intervene**: Can block dangerous commands, strong guidance

**Session Health Tracking:**
- Context usage percentage (escalates at 80%+)
- Drift signals ignored (escalates at 3+)
- Same error repeated (escalates at 3+ repeats)
- Pending error and known fix tracking

**Key Features:**
- **Context Injection**: Known fixes surfaced prominently with visual formatting
- **Command Blocking**: Dangerous commands blocked at intervene level
- **Auto-Escalation**: Level automatically increases as session health degrades
- **Audit Logging**: All interventions logged to `.proof/intervention_audit.jsonl`
- **Configurable**: Levels, thresholds, and behavior configurable via `.proof/v8_config.json`

**Integration:**
- `post_tool.py`: Health tracking on errors (`update_health_from_error`)
- `post_tool.py`: Health reset on success (`update_health_from_success`)
- `pre_tool.py`: Intervention check before tool execution (`get_intervention_for_tool`)

- 41 tests

### Phase 9: Outcome Tracking & Closed Loop (`fix_outcomes.py`) ✓
**Purpose:** Close the feedback loop - make the knowledge base learn from outcomes

**The Problem:** Phase 8 data showed fixes were surfaced but we had no data on whether
they actually worked. The system observed and warned but couldn't verify if guidance helped.

**The Core Gap:**
When a fix is surfaced and Claude runs the suggested command:
1. We know the fix was surfaced ✅
2. We know a command succeeded ✅
3. We didn't know if the **success was because of the fix** ❌

**The Solution:** Automatic outcome tracking with correlation IDs:

**Fix Outcome Tracking:**
- `track_fix_surfaced()`: Records when a fix is shown, starts tracking
- `track_command_after_fix()`: Checks if subsequent commands match suggested fix
- Automatic detection of "followed" vs "ignored" (no manual reporting)
- 5-command threshold before marking fix as "ignored"
- 30-minute timeout for pending outcomes

**Command Matching:**
- Fuzzy matching handles variations (`pip3` ↔ `pip`, `npm i` ↔ `npm install`)
- Version specifiers stripped (`requests==2.28.0` matches `requests`)
- Sudo prefix removed, case normalized
- Target extraction for package commands

**Confidence Feedback Loop:**
- `boost_fix_confidence()`: Called when fix followed + command succeeded (+0.1)
- `decay_fix_confidence()`: Called when fix followed + command failed (-0.15)
- Fixes that work get stronger, fixes that fail get weaker
- Bad fixes naturally decay below 0.4 display threshold
- Good fixes rise toward 0.9+ (auto-fix territory for Phase 10)

**Effectiveness Reporting:**
- Real fix outcome data replaces inference-based metrics
- Shows: total surfaced, followed, ignored, success rate
- Phase 9 breakdown in compact and detailed reports

**Storage:** `.proof/fix_outcomes.jsonl`

**Integration:**
- `post_tool.py`: `track_fix_surfaced()` when fix is surfaced
- `post_tool.py`: `track_command_after_fix()` for all Bash commands
- `codebase_knowledge.py`: `boost_fix_confidence()` / `decay_fix_confidence()`
- `effectiveness_analyzer.py`: `analyze_fix_outcomes_from_tracking()`

- 51 tests

### Test Coverage
- 325 new tests for v8.0:
  - Phase 1 (drift): 24 tests
  - Phase 2 (context): 33 tests
  - Phase 3 (knowledge): 31 tests
  - Phase 4 (handoff): 23 tests
  - Phase 5 (metrics): 37 tests
  - Phase 6 (suggestions): 35 tests
  - Phase 7 (effectiveness): 50 tests
  - Phase 8 (intervention): 41 tests
  - Phase 9 (outcomes): 51 tests
- Total core tests: 440+

---

## v7.1 - Learned Track Guidance (Deprecated)
- **Phase 1 - Success Pattern Capture**: Objective completions captured to archive with approach verbs, metrics, tags
- **Phase 2 - Pattern Recognition**: New `pattern_recognition.py` module finds similar objectives and builds patterns
- **Phase 3 - Suggestion Surfacing**: `/edge "objective"` shows suggested approaches from learned guidance
- **Phase 4 - Feedback Loop**: New `feedback_loop.py` closes the learning cycle
  - Tracks if suggestions were followed (verb overlap + sequence similarity)
  - Updates pattern confidence based on outcomes (success/failure)
  - Persists pattern updates in `patterns.yaml`
  - Logs `pattern_feedback` entries to archive for analysis
- **Verb Taxonomy**: 10 canonical verbs (scope, plan, test, build, extract, integrate, fix, clean, document, deploy)
- **Seed Patterns**: 5 pre-defined patterns for cold-start guidance (refactoring, bugfix, feature, testing, documentation)
- **YAML Fallback**: Verb taxonomy has built-in defaults when PyYAML unavailable
- **126 new tests** for guidance system (53 archive + 34 pattern recognition + 39 feedback loop)

## v7.0 - Context Engineering
- **Slim Context**: active_context.yaml reduced from 351 to ~100 lines
- **Auto-Archive**: Completed steps auto-archive at session start (keeps last 3 visible)
- **Memory Optimization**: Only top 3 lessons shown at session start (all still enforced at tool use)
- **Changelog Extraction**: Version history moved to CHANGELOG.md
- **Runtime Clarification**: YAML runtime is source of truth, JSON files are deprecated fallbacks
- **Template v7**: New `active_context_v7.yaml` template with runtime section

## v6.1
- History Preservation - archive plan before setting new objective
- Objective Transitions tracked in `.proof/archive.jsonl`

## v6.0
- `/edge "objective"` just works - set objective inline
- Objective detection and routing in edge_skill_hook.py

## v5.3
- Codex Architecture Review - external GPT assessment
- HIGH: quality_gate_override not persisted in YAML runtime, objective_hash uses non-deterministic hash()
- MEDIUM: GEAR_BEHAVIORS/TRANSITION_RULES unused by engine
- Verdict: Net-positive for complex work, net-negative for small tasks

## v5.2
- Check-Specific Overrides - granular quality gate approval (approve specific checks vs all)
- 7 new tests

## v5.1
- State Machine Logic Audit - quality_gate_override bypass, orphan cleanup, junction single-source, STUCK enforcement
- 5 phases, 80 tests

## v5.0
- State Consolidation - junction/gear/dispatch state now in active_context.yaml runtime section
- YAML-first with JSON fallback
- 7 steps

## v4.0
- Protocol v4.0 Complete - mode awareness, mode behavior, auto transitions
- Mode field: plan|active|review|done
- detect_mode(), /edge plan|active|review|done subcommands
- PLAN/REVIEW/DONE skip gears, ACTIVE runs gear engine

## v3.12
- Auto-Learn File Patterns - zero-config lesson targeting, infers globs from proof
- 4 steps, 12 new tests

## v3.11
- Obligations MVP - Mechanical Learning - obligations track lesson application, LAR/RWR metrics
- Auto-Categorization - system infers dismissal reasons from behavior
- Matching Quality Instrumentation - dismissal reason tracking, false positive/negative rates
- 6 steps, 19 new tests

## v3.10
- Living Memory Architecture - evergreen lessons, active surfacing, archive retention
- Proof-Grounded Memory - lessons protected by proof vitality (observations > claims)
- 6 steps, 199 tests

## v3.9
- Hook-Based Gear Execution - UserPromptSubmit hook calls gear_engine
- Hook-Based Prune - /edge-prune triggers prune_skill_hook.py
- Verification Field - optional verification on plan steps, PATROL flags unverified completions
- Quality Gate - objective completion checks before ACTIVE→PATROL transition
- Resilient Proof Logging - atomic writes, session isolation, recovery mechanism
- Live Server Mode - edge_server.py at localhost:8080
- 1350+ tests

## v3.8
- Gear Integration - /edge skill executes Three Gears logic
- Architecture Review - identified skill-as-documentation vs hook-based execution gap
- 1251 tests

## v3.7
- Three Gears Mode - automatic mode switching (Active→Patrol→Dream)
- 8 steps, 1011 tests, score 6/6

## v3.6
- Lessons as Living Audits - lessons auto-scan codebase for violations
- 7 steps, 961 tests

## v3.5
- Risks Enforcement - mandatory failure mode planning before edits
- 5 steps

## v3.4
- Lesson Extraction - mismatch + trigger = lesson, auto-capture at resolution
- 4 steps

## v3.3
- Discovery Filter - meta-lesson detection to reduce false positives
- 3 steps

## v3.2
- ClickUp Integration - auto-create tasks from objectives, sync completion status
- 5 steps

## v3.1
- Discovery Mode - self-aware feature proposals from archive/lessons/patterns
- 6 steps

## v3.0
- Autonomous Edge - /edge unified command, continuous loop, complexity classification, auto-plan
- 7 steps

## v2.8
- Scout Mode - autonomous codebase exploration when no objective
- 7 steps

## v2.7
- Dispatch Mode - YOLO as autopilot with junction gates
- 7 steps

## v2.6
- YOLO Mode with Guardrails - reversibility-gated auto-execution
- 9 steps, score 6/6

## v2.5
- Lesson deduplication and consolidation
- 9 steps, score 5/6

## v2.4
- Automated reflection - score patterns, recurring failures, improvement suggestions
- 8 steps, score 5/6

## v2.3
- Pragmatic Layering refactor - edge_utils.py split into 6 focused modules
- 10 steps, score 5/6

## v2.2
- Brainstorm command - project scanning, 3-phase ideation, expert personas

## v2.1
- Research command system - scan, prompt generation, results tracking

## v2.0
- Smart orchestrator, 6-check loop, constant memory, pruning

## v1.0
- YAML state, enforcement hooks, Windows packaging

---

## Proof Visualizer History

### v2.2
- Code Review Fixes - quadtree animation fallback, splitLines() for cross-platform line endings

### v2.1
- Enhanced LLM Export - session context (phases, duration), related files, work timeline, phase-aware diffs

### v2.0
- Performance & Quality Fixes - quadtree O(log N), search+reveal fix, diff cap 2000 chars

### v1.9
- LLM-Friendly Diff Export - one-click export (E key or button), markdown format

### v1.8
- Diff Takeover Polish - flex layout fills card space, max-width 900px

### v1.7
- Diff Takeover Mode - click label or D key to expand diff

### v1.6
- Multi-Layout Label Visibility - tooltips with full path on all layouts

### v1.5
- Multi-Layout Visualization - 6 layouts (Force, EdgeBundling, Treemap, CirclePacking, Sunburst, Grid)

### v1.4
- Proof Visualizer Refactor - split 4,371 line file into 7 focused modules (94% reduction)

### v1.3
- Constellation Mode - brightness tiers, hover reveal, search promotes
- Story Mode Polish - Clouds toggle button, shine/fade on touch

### v1.2
- Cluster Islands Layout - ring positioning, group forces

### v0.9.9
- Soft Territory - node auras merge into organic cluster boundaries

### v0.9.8
- Diff Preview - show code changes in insight card

### v0.9.7
- Import Graph - structural dependency edges in Explorer (151 edges)

### v0.9.6
- Luminous Membranes - focus terrain, density contours, extension colors

### v0.9.5
- Explorer focus mode, related files fix, dashboard skeleton, digest sparklines

### v0.9
- Edge Digest - automated reflection, recommendations to next_focus

### v0.8
- Explorer Mode - static codebase map, Story↔Explorer toggle, phase heat overlay

### v0.7
- Story Mode - Insight Card 2.0: phase context, related files, persistence
- UX Polish: keyboard navigation (← → Space Esc)

### v0.6
- SOTA Insight Card with fullscreen node click, sparklines, smart insights
- Interaction Mode Coloring + Intensity Glow

### v0.5
- Story Mode - timeline scrubber, intent phases, playback controls
