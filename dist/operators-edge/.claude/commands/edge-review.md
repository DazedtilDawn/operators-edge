---
description: Run a self-review of uncommitted changes
allowed-tools: Read, Bash, Glob, Grep
---

> **[v4.0 NOTE]** This command focuses on code diff review. For workflow completion verification, use `/edge review` mode.

# Code Review

Run a structured self-review of your current changes before committing.

## When to Use

- After completing a plan step
- Before committing changes
- When you want a sanity check on your work
- When the diff is getting large

## Instructions

### 1. Gather Context

Run the context gatherer to collect:
- Git diff (staged or all changes)
- Current step intent
- Active constraints
- Known risks
- Relevant lessons from memory

```bash
cd "$CLAUDE_PROJECT_DIR" && python3 .claude/hooks/review_context.py
```

If `--staged` is passed as an argument, add that flag to only review staged changes.

### 2. Check for Empty Diff

If there are no changes to review, inform the user:

```
════════════════════════════════════════════════════════════
NO CHANGES TO REVIEW
════════════════════════════════════════════════════════════

There are no uncommitted changes in the working directory.

To run a review:
  1. Make some code changes
  2. Run /edge-review again

To review staged changes only:
  /edge-review --staged
════════════════════════════════════════════════════════════
```

### 3. Perform Critical Review

Using the context gathered, perform a thorough code review. You are a senior reviewer whose job is to FIND ISSUES, not rubber-stamp approval.

**Security Checklist:**
- [ ] SQL injection, XSS, command injection
- [ ] Hardcoded secrets, API keys
- [ ] Insecure randomness, weak crypto
- [ ] Path traversal, file inclusion
- [ ] Race conditions

**Correctness Checklist:**
- [ ] Edge cases: null, empty, zero, negative
- [ ] Off-by-one errors, boundary conditions
- [ ] Error handling: what if this fails?
- [ ] Type mismatches
- [ ] Logic errors

**Constraints Check:**
Review each constraint from `active_context.yaml`:
- Does this change violate any constraint?
- Could this change accidentally break something?

**Risks Check:**
Review each known risk:
- Has any risk materialized?
- Are mitigations in place?

**Architecture Check:**
- [ ] Breaking changes to interfaces?
- [ ] Tight coupling created?
- [ ] Testable code?
- [ ] Performance concerns?

### 4. Produce Structured Findings

Format your review as:

```
════════════════════════════════════════════════════════════
CODE REVIEW
════════════════════════════════════════════════════════════

Scope: [N] files, +[added] / -[removed] lines

────────────────────────────────────────────────────────────
FINDINGS
────────────────────────────────────────────────────────────

[1] ! CRITICAL: [issue]
    Location: [file:line]
    Suggestion: [how to fix]

[2] ~ IMPORTANT: [issue]
    Location: [file:line]
    Suggestion: [how to fix]

[3] . Minor: [issue]
    Location: [file:line]
    Suggestion: [how to fix]

────────────────────────────────────────────────────────────
SUMMARY
────────────────────────────────────────────────────────────

Findings: [total] (critical: [N], important: [N], minor: [N])
Verdict: [approve | request_changes | needs_discussion]
Key Concerns: [one sentence summary]

════════════════════════════════════════════════════════════
```

### 5. Store Review (Optional)

If `--save` flag is passed, save the review to `.proof/reviews/`:

```
.proof/reviews/YYYY-MM-DDTHH-MM-SS.yaml
```

### 6. Rules

1. **At least ONE finding** - Even excellent code has something to improve.
2. **Be specific** - "line 42 in auth.py" not "somewhere"
3. **Be actionable** - Suggestions, not just criticism
4. **Severity guide:**
   - **critical**: Security flaw, data loss, crash. Must fix.
   - **important**: Bug likely, bad pattern. Should fix.
   - **minor**: Style, nitpick. Optional.

## Arguments

- `--staged` - Only review staged changes
- `--save` - Save review to .proof/reviews/

## Example Output

```
════════════════════════════════════════════════════════════
CODE REVIEW
════════════════════════════════════════════════════════════

Scope: 3 files, +127 / -15 lines

────────────────────────────────────────────────────────────
FINDINGS
────────────────────────────────────────────────────────────

[1] ~ IMPORTANT: Function exceeds 50 lines, hard to test
    Location: .claude/hooks/review_context.py:gather_review_context
    Suggestion: Extract git operations into separate helper functions

[2] . Minor: Magic number 8000 should be a named constant
    Location: .claude/hooks/review_context.py:12
    Suggestion: Define MAX_DIFF_TOKENS at module level with comment

────────────────────────────────────────────────────────────
SUMMARY
────────────────────────────────────────────────────────────

Findings: 2 (critical: 0, important: 1, minor: 1)
Verdict: approve
Key Concerns: Code quality is good, minor structural improvements possible

════════════════════════════════════════════════════════════
```
