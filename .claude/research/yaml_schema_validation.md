# Research Request: YAML Schema Validation with Pydantic

## Project Context

**Objective:** Add schema validation to `active_context.yaml` to catch errors early and provide helpful feedback when the file is malformed.

**Current State:** The system uses a custom YAML parser (`parse_simple_yaml()` in `state_utils.py`) that:
- Handles basic YAML structures (scalars, lists, nested dicts)
- Returns `None` silently on parse errors
- Has no schema validation - any structure is accepted
- Errors surface later as cryptic KeyErrors or AttributeErrors

**The Problem:**
```yaml
# User typo - "stauts" instead of "status"
plan:
  - description: "Fix the bug"
    stauts: completed  # <-- Silent failure, step appears pending
    proof: "done"
```

**Constraints:**
- Must work with existing custom YAML parser (no PyYAML dependency)
- Should provide actionable error messages
- Must handle schema evolution (v1 → v2 format differences)
- Cannot break existing valid state files

## Why This Research Is Needed

Manual YAML editing is error-prone. Common mistakes:
- Typos in field names (`stauts` vs `status`)
- Wrong types (`current_step: "1"` vs `current_step: 1`)
- Missing required fields
- Invalid enum values (`status: done` vs `status: completed`)

These errors cause silent failures or cryptic downstream errors. Schema validation would:
- Catch errors at load time with clear messages
- Document the expected structure (schema = documentation)
- Enable IDE autocompletion if we generate JSON Schema
- Support graceful migration between versions

## Current active_context.yaml Structure

```yaml
# Session metadata
session:
  id: string
  started_at: string (ISO datetime)
  note: string (optional)

# Core fields
objective: string
current_step: integer (1-indexed)

# Plan (list of steps)
plan:
  - description: string
    status: enum [pending, in_progress, completed, blocked]
    proof: string (optional)

# Optional sections
constraints: list[string]
risks: list[string]

# Memory (v2 format)
memory:
  - trigger: string
    lesson: string
    reinforced: integer
    last_used: string (date)

# Mismatches (when things go wrong)
mismatches:
  - id: string
    expectation: string
    observation: string
    resolution: string (optional)
    status: enum [unresolved, resolved]
    resolved: boolean

# Self-assessment
self_score:
  timestamp: string
  checks:
    mismatch_detection: {met: bool, note: string}
    plan_revision: {met: bool, note: string}
    tool_switching: {met: bool, note: string}
    memory_update: {met: bool, note: string}
    proof_generation: {met: bool, note: string}
    stop_condition: {met: bool, note: string}
  total: integer (0-6)
  level: enum [demo_automation, promising_fragile, real_agent]

# Archive reference
archive:
  path: string
  last_prune: string (ISO datetime)
  entries_archived: integer
```

## Questions to Answer

### 1. Pydantic Design Patterns

1. How should nested structures be modeled?
   - Separate model per section (SessionModel, PlanStepModel)?
   - Single monolithic model?
   - Composition vs inheritance?

2. How to handle optional sections gracefully?
   - `Optional[List[str]]` with default `[]`?
   - Separate models for "minimal" vs "full" state?

3. What's the best pattern for enum validation?
   - Python Enum class?
   - Literal types?
   - Custom validator?

### 2. Error Messages

1. How to make Pydantic errors user-friendly?
   - Custom error messages per field?
   - Error formatting/pretty-printing?
   - Suggestions for common typos?

2. How to show the location of the error in YAML?
   - Line numbers?
   - Path to field (`plan[0].status`)?

3. Should validation errors block or warn?
   - Strict mode (block on any error)?
   - Lenient mode (warn but continue)?

### 3. Schema Evolution

1. How to handle v1 vs v2 format differences?
   - `lessons` (v1) vs `memory` (v2)
   - Automatic migration?
   - Version detection?

2. How to add new fields without breaking old files?
   - Default values for new fields?
   - Optional with `None` default?

3. How to deprecate old fields gracefully?
   - Warning on deprecated fields?
   - Automatic conversion?

### 4. Integration with Custom Parser

1. Should Pydantic validate the dict after custom parsing?
   - `parse_simple_yaml()` → dict → Pydantic model?
   - Or replace custom parser entirely?

2. How to handle parser limitations?
   - Custom parser doesn't support all YAML features
   - Some valid Pydantic defaults might not serialize correctly

3. Should we generate YAML from Pydantic models?
   - `model.model_dump()` → write to file?
   - Preserve comments and formatting?

### 5. Performance

1. What's the validation overhead?
   - Time to validate typical state file?
   - Memory usage?

2. Should validation be lazy or eager?
   - Validate on every `load_yaml_state()`?
   - Cache validated state?

3. Any concerns with Pydantic v2 vs v1?
   - Breaking changes?
   - Performance differences?

### 6. JSON Schema Generation

1. Can Pydantic generate JSON Schema for IDE support?
   - `model.model_json_schema()`?
   - VS Code YAML extension integration?

2. How to document the schema for users?
   - Auto-generated docs?
   - Example templates?

## Requested Output Format

Please provide:

1. **Recommendation**: Suggested Pydantic model structure (1-2 sentences)

2. **Model Skeleton**:
   ```python
   from pydantic import BaseModel, Field
   from typing import Optional, List
   from enum import Enum

   class StepStatus(str, Enum):
       ...

   class PlanStep(BaseModel):
       ...

   class ActiveContext(BaseModel):
       ...
   ```

3. **Validation Integration**: How to integrate with existing code
   - Where to call validation
   - How to handle errors
   - Migration strategy

4. **Error Message Examples**: What good error messages look like
   ```
   Validation Error in active_context.yaml:
     plan[0].status: Invalid value 'done'.
     Expected one of: pending, in_progress, completed, blocked
   ```

5. **Warnings**: Potential pitfalls
   - Edge cases
   - Migration risks
   - Performance concerns

## Integration Points

Key files to modify:
- `state_utils.py` - Add validation to `load_yaml_state()`
- `edge_config.py` - Could hold schema models
- New file `schema.py` - Pydantic models

Key functions affected:
- `load_yaml_state()` - Add validation call
- `parse_simple_yaml()` - Returns dict for Pydantic
- Any function that writes to `active_context.yaml`

## Success Criteria

A successful implementation would:
1. Catch typos in field names with helpful suggestions
2. Validate enum values (status, level)
3. Ensure required fields are present
4. Handle v1/v2 format differences
5. Provide line-number or path context in errors
6. Add no runtime overhead for valid files
7. Generate JSON Schema for IDE support (bonus)
