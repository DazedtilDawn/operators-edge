# Codex CLI Test Plan

This document outlines how to test the Operator's Edge integration with Codex CLI.

## Prerequisites

1. **Codex CLI installed**: Follow OpenAI's installation instructions
2. **Project setup**: Copy the `codex/` directory to your Codex-enabled project
3. **State file**: Ensure `active_context.yaml` exists in project root

## Installation

```bash
# From your project root
cp -r /path/to/operators-edge/codex/* ./

# Verify structure
ls -la AGENTS.md skills/
```

Expected structure:
```
your-project/
├── AGENTS.md              # Auto-loaded at session start
├── active_context.yaml    # State file
├── skills/
│   ├── edge-plan/SKILL.md
│   ├── edge-step/SKILL.md
│   ├── edge-score/SKILL.md
│   ├── edge-context/SKILL.md
│   ├── edge-log/SKILL.md
│   └── edge-done/SKILL.md
└── .proof/                # Created as needed
```

## Test Cases

### T1: AGENTS.md Auto-Loading

**Goal**: Verify session context is injected at startup

**Steps**:
1. Start Codex CLI in the project directory
2. Check if context was loaded

**Expected**:
- AGENTS.md content should be visible or referenced
- Session guidance should be active

**Verification**:
```
Ask: "What workflow guidelines are active?"
Expected: Reference to state file, proof logging, skill invocation
```

### T2: Implicit Context Loading

**Goal**: Verify edge-context triggers automatically

**Steps**:
1. Start a new Codex CLI session
2. Say "Let's work on implementing the user auth feature"

**Expected**:
- edge-context should invoke automatically (based on description match)
- State from `active_context.yaml` should be displayed
- Current step and progress should be shown

**Verification**:
```
Look for output containing:
- Current objective
- Plan progress
- Current gear (ACTIVE/PATROL/DREAM)
```

### T3: Skill Invocation

**Goal**: Verify skills can be invoked explicitly

**Steps**:
1. Invoke each skill explicitly:
   - `$edge-plan`
   - `$edge-step`
   - `$edge-score`
   - `$edge-log`
   - `$edge-done`

**Expected**:
Each skill should:
- Read `active_context.yaml`
- Perform its documented function
- Update state as needed

**Verification**:
```
After $edge-plan: Plan should exist in active_context.yaml
After $edge-step: Step should be marked in_progress, then completed
After $edge-score: self_score section should be updated
After $edge-log: .proof/session_log.jsonl should have entries
After $edge-done: Session summary should appear
```

### T4: Planning Workflow

**Goal**: Verify the planning workflow functions

**Steps**:
1. Set a new objective
2. Run `$edge-plan`
3. Provide description of what needs to be done

**Expected**:
- Plan should be created in `active_context.yaml`
- Steps should have description, status: pending, proof: null
- current_step should be set to 1

**Verification**:
```yaml
# Check active_context.yaml
objective: "The new objective"
current_step: 1
plan:
  - description: "Step 1..."
    status: pending
    proof: null
```

### T5: Step Execution

**Goal**: Verify step execution workflow

**Steps**:
1. Have a plan with pending steps
2. Run `$edge-step`
3. Complete the work
4. Verify completion

**Expected**:
- Step should be marked in_progress
- Work should be executed
- Step should be marked completed with proof
- current_step should advance

**Verification**:
```yaml
# Check active_context.yaml after completion
plan:
  - description: "Step 1..."
    status: completed
    proof: "Description of what was done"
```

### T6: Proof Logging

**Goal**: Verify manual proof capture works

**Steps**:
1. Do some work (edit files, run tests)
2. Run `$edge-log`
3. Check proof file

**Expected**:
- `.proof/session_log.jsonl` should exist
- Entry should be appended with timestamp, action, outcome

**Verification**:
```bash
cat .proof/session_log.jsonl
# Should contain JSON entries with recent work
```

### T7: Session Completion

**Goal**: Verify done validation works

**Steps**:
1. Complete some work
2. Run `$edge-done`

**Expected**:
- Summary of session should appear
- State modification check should pass (if work was done)
- Proof check should pass (if logging was done)

**Verification**:
```
Session validation PASSED
- State modified: yes
- Proof exists: yes
- Ready to end: yes
```

### T8: Soft Enforcement

**Goal**: Verify behavioral guidance is followed

**Steps**:
1. Try to edit a file without a plan
2. Observe response

**Expected**:
- AGENTS.md guidance should remind about planning
- Note: This is SOFT enforcement - Codex may still allow the edit
- The difference from Claude Code: no hard block

**Verification**:
```
Ideally: Reminder about needing a plan before editing
Reality: May edit anyway (soft enforcement limitation)
```

### T9: Memory Surfacing

**Goal**: Verify lessons are surfaced when relevant

**Steps**:
1. Have lessons in `active_context.yaml` memory section
2. Start work on a task that matches lesson triggers
3. Run `$edge-context`

**Expected**:
- Matching lessons should be displayed
- Trigger keywords should match task description

**Verification**:
```
RELEVANT LESSON: [trigger keyword]
  [lesson text]
  (reinforced N times)
```

### T10: Three Gears Mode

**Goal**: Verify gear detection works

**Steps**:
1. With objective + pending steps: should be ACTIVE
2. With all steps completed: should be PATROL
3. With no objective: should be DREAM

**Expected**:
- Gear should be displayed when running $edge-context
- Different behavior based on gear

**Verification**:
```
Gear: ACTIVE (when working on plan)
Gear: PATROL (when plan complete, reviewing)
Gear: DREAM (when no objective, exploring)
```

## Known Limitations

| Feature | Claude Code | Codex CLI | Impact |
|---------|-------------|-----------|--------|
| Edit blocking | Hard (hook) | Soft (guidance) | Edits may happen without plan |
| Session end validation | Automatic | Manual (`$edge-done`) | User must remember to validate |
| Proof capture | Automatic (PostToolUse) | Manual (`$edge-log`) | User must log explicitly |
| Context injection | Automatic (UserPromptSubmit) | Via AGENTS.md | Similar effect |
| Dangerous command blocking | Hard (hook) | Soft (guidance) | Commands may run |

## Troubleshooting

### Skills not recognized
- Check SKILL.md has valid YAML frontmatter
- Verify skills/ directory is in project root
- May need to restart Codex CLI

### State not loading
- Verify `active_context.yaml` exists and is valid YAML
- Check file permissions
- Run `$edge-context` explicitly

### Proof not captured
- Ensure `.proof/` directory exists
- Run `$edge-log` after completing work
- Check file permissions on .proof/session_log.jsonl

## Success Criteria

All 10 test cases should pass for the integration to be considered complete:

| Test | Description | Status |
|------|-------------|--------|
| T1 | AGENTS.md auto-loading | [ ] |
| T2 | Implicit context loading | [ ] |
| T3 | Skill invocation | [ ] |
| T4 | Planning workflow | [ ] |
| T5 | Step execution | [ ] |
| T6 | Proof logging | [ ] |
| T7 | Session completion | [ ] |
| T8 | Soft enforcement | [ ] |
| T9 | Memory surfacing | [ ] |
| T10 | Three gears mode | [ ] |

## Next Steps After Testing

1. If tests pass: Proceed to S9 (documentation)
2. If tests fail: Document failures and create fixes
3. Consider: Is soft enforcement acceptable for the use case?
