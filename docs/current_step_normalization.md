# current_step Normalization

This guide defines when and how `current_step` should be auto-normalized to
avoid pointing at completed steps.

## Goal

When a plan is fully completed, `current_step` should not reference a completed
step. The normalized pointer should reflect "no remaining steps" without
breaking existing workflows.

## Normalization Rule (Unambiguous Cases Only)

Auto-normalize only when the plan state is unambiguous:

1. **Plan exists and all steps are completed**:
   - Set `current_step` to `len(plan) + 1`.
2. **Plan is empty**:
   - Set `current_step` to `0`.

## When NOT to Auto-Normalize

- If any steps are `pending` or `in_progress`.
- If the plan is malformed or missing.

In these cases, warn instead of changing the file.

## Rationale

- `len(plan) + 1` keeps the pointer in a valid "next step" position without
  referencing a completed step.
- Avoids rewriting YAML when state is ambiguous, preventing unintended changes.

