# Pydantic Schema Validation Research

Research on adding schema validation to `active_context.yaml` using Pydantic.

## Recommendation

Use a **compositional schema**: one Pydantic model per top-level section (Session, PlanStep, MemoryEntry, etc.) composed into a root `ActiveContext` model, with **strict validation inside list items** (to catch typos like `stauts`) and **root-level forward-compatibility** (allow unknown top-level keys with warnings).

## Key Design Decisions

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Nested models | Yes | Precise error locations for deeply nested data |
| `extra="forbid"` on sections | Yes | Catches typos like `stauts` instead of silent drift |
| `extra="allow"` on root | Yes | Forward compatibility - new keys don't break old code |
| Strict typing | Selective | Only where it matters (ints, bools) to avoid string coercion issues |

## Model Skeleton

```python
# schema.py
from __future__ import annotations

from enum import Enum
from typing import Any, Dict, List, Optional

from datetime import datetime, date
import difflib

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    ValidationError,
    ValidationInfo,
    field_validator,
    model_validator,
)

# ----------------------------
# Helpers
# ----------------------------

def _is_iso_datetime(s: str) -> bool:
    try:
        if s.endswith("Z"):
            s = s[:-1] + "+00:00"
        datetime.fromisoformat(s)
        return True
    except ValueError:
        return False


def _is_iso_date(s: str) -> bool:
    try:
        date.fromisoformat(s)
        return True
    except ValueError:
        return False


def _warn(info: ValidationInfo, msg: str) -> None:
    if info.context is None:
        return
    info.context.setdefault("warnings", []).append(msg)


# ----------------------------
# Enums
# ----------------------------

class StepStatus(str, Enum):
    pending = "pending"
    in_progress = "in_progress"
    completed = "completed"
    blocked = "blocked"


class MismatchStatus(str, Enum):
    unresolved = "unresolved"
    resolved = "resolved"


class SelfScoreLevel(str, Enum):
    demo_automation = "demo_automation"
    promising_fragile = "promising_fragile"
    real_agent = "real_agent"


# ----------------------------
# Section models
# ----------------------------

class SessionModel(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    started_at: str
    note: Optional[str] = None

    @field_validator("started_at")
    @classmethod
    def _validate_started_at(cls, v: str) -> str:
        if not _is_iso_datetime(v):
            raise ValueError("must be ISO-8601 datetime")
        return v


class PlanStep(BaseModel):
    model_config = ConfigDict(extra="forbid")

    description: str
    status: StepStatus
    proof: Optional[str] = None


class MemoryEntry(BaseModel):
    model_config = ConfigDict(extra="forbid")

    trigger: str
    lesson: str
    reinforced: int = Field(default=0, ge=0, strict=True)
    last_used: Optional[str] = None

    @field_validator("last_used")
    @classmethod
    def _validate_last_used(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return v
        if not _is_iso_date(v):
            raise ValueError("must be ISO date (YYYY-MM-DD)")
        return v


class MismatchEntry(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    expectation: str
    observation: str
    resolution: Optional[str] = None
    status: MismatchStatus
    resolved: bool = Field(strict=True)

    @model_validator(mode="after")
    def _validate_consistency(self) -> "MismatchEntry":
        if self.resolved and self.status != MismatchStatus.resolved:
            raise ValueError("status must be 'resolved' when resolved=true")
        if (not self.resolved) and self.status != MismatchStatus.unresolved:
            raise ValueError("status must be 'unresolved' when resolved=false")
        return self


class SelfCheck(BaseModel):
    model_config = ConfigDict(extra="forbid")
    met: bool = Field(strict=True)
    note: str


class SelfScore(BaseModel):
    model_config = ConfigDict(extra="forbid")

    timestamp: str
    checks: Dict[str, SelfCheck]
    total: int = Field(ge=0, le=6, strict=True)
    level: SelfScoreLevel


class ArchiveRef(BaseModel):
    model_config = ConfigDict(extra="forbid")

    path: str
    last_prune: str
    entries_archived: int = Field(ge=0, strict=True)


# ----------------------------
# Root model
# ----------------------------

class ActiveContext(BaseModel):
    model_config = ConfigDict(extra="allow")

    schema_version: Optional[int] = None
    session: Optional[SessionModel] = None
    objective: str
    current_step: int = Field(ge=1, strict=True)
    plan: List[PlanStep] = Field(default_factory=list)
    constraints: List[str] = Field(default_factory=list)
    risks: List[str] = Field(default_factory=list)
    memory: List[MemoryEntry] = Field(default_factory=list)
    mismatches: List[MismatchEntry] = Field(default_factory=list)
    self_score: Optional[SelfScore] = None
    archive: Optional[ArchiveRef] = None

    @model_validator(mode="before")
    @classmethod
    def _migrate_v1_to_v2(cls, data: Any, info: ValidationInfo) -> Any:
        """Migrate lessons (v1) -> memory (v2)"""
        if not isinstance(data, dict):
            return data

        if "schema_version" not in data:
            if "lessons" in data and "memory" not in data:
                data["schema_version"] = 1
            else:
                data["schema_version"] = 2

        if "lessons" in data:
            _warn(info, "Deprecated field 'lessons' detected; migrating to 'memory'.")
            # migration logic...
            data.pop("lessons", None)

        return data
```

## Validation Integration

Keep the custom parser and validate its output:

```
parse_simple_yaml() -> dict -> ActiveContext.model_validate()
```

### Error Formatting

```python
def loc_to_yaml_path(loc: List[Any]) -> str:
    out = ""
    for part in loc:
        if isinstance(part, int):
            out += f"[{part}]"
        else:
            out += ("" if not out else ".") + str(part)
    return out


def suggest_key(bad_key: str, valid_keys: List[str]) -> Optional[str]:
    matches = difflib.get_close_matches(bad_key, valid_keys, n=1, cutoff=0.75)
    return matches[0] if matches else None
```

## Error Message Examples

### Typo in field (`stauts`)

```
Validation Error in active_context.yaml:
  plan[0].stauts: Unknown field 'stauts'. Did you mean 'status'?
  plan[0].status: Field required
```

### Invalid enum (`status: done`)

```
Validation Error in active_context.yaml:
  plan[0].status: Invalid value 'done'. Expected one of: pending, in_progress, completed, blocked
```

### Wrong type (`current_step: "1"`)

```
Validation Error in active_context.yaml:
  current_step: Input should be a valid integer
```

### Deprecated field (`lessons`)

```
Warning: Deprecated field 'lessons' detected; migrating to 'memory'.
```

## Warnings and Pitfalls

1. **Line numbers not available** - Pydantic validates dicts, not YAML text. Would need parser enhancement.

2. **Strict mode selectively** - Only where it matters (ints, bools) to avoid string coercion issues.

3. **`extra="forbid"` placement** - Use in high typo-risk areas (plan steps), but allow at root for forward compatibility.

4. **Parser limitations** - Schema validation can only validate what the parser preserves.

5. **Pydantic v2 vs v1** - Use v2 (`model_validate`, `model_dump`, `ConfigDict`).

6. **JSON Schema dialect** - Pydantic generates Draft 2020-12, VS Code YAML extension uses Draft 7. Usually works for simple schemas.

## JSON Schema for IDE Support

```python
# Generate schema
schema = ActiveContext.model_json_schema()
Path("schemas/active_context.schema.json").write_text(json.dumps(schema, indent=2))
```

VS Code integration:
```yaml
# yaml-language-server: $schema=./schemas/active_context.schema.json
```

Or `.vscode/settings.json`:
```json
{
  "yaml.schemas": {
    "./schemas/active_context.schema.json": ["active_context.yaml"]
  }
}
```

## Implementation Estimate

- Core schema models: ~200 lines
- Error formatting: ~50 lines
- Integration with state_utils.py: ~100 lines
- Tests: ~150 lines

Total: ~500 lines for full implementation

## Sources

- [Pydantic Models](https://docs.pydantic.dev/latest/concepts/models/)
- [Pydantic Config](https://docs.pydantic.dev/latest/api/config/)
- [Pydantic Error Handling](https://docs.pydantic.dev/latest/errors/errors/)
- [Pydantic Validators](https://docs.pydantic.dev/latest/concepts/validators/)
- [Pydantic Strict Mode](https://docs.pydantic.dev/latest/concepts/strict_mode/)
- [VS Code YAML Extension](https://marketplace.visualstudio.com/items?itemName=redhat.vscode-yaml)
