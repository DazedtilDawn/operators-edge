# YOLO Mode Action Classification Schema

## Overview

Actions are classified into three categories based on reversibility:

| Category | Trust Level | Behavior in YOLO Mode |
|----------|-------------|----------------------|
| **Reversible** | `auto` | Execute immediately, no confirmation |
| **Irreversible** | `supervised` | Stage for batch approval |
| **Blocked** | `blocked` | Always require explicit approval |

## Action Categories

### 1. REVERSIBLE (Auto-Execute)

These actions can be undone or have no lasting side effects.

| Tool | Action Pattern | Why Reversible |
|------|----------------|----------------|
| Read | Any file read | No state change |
| Glob | File pattern matching | No state change |
| Grep | Content search | No state change |
| LSP | Code intelligence queries | No state change |
| Bash | `git status` | Read-only |
| Bash | `git diff` | Read-only |
| Bash | `git log` | Read-only |
| Bash | `ls`, `pwd`, `cat` | Read-only |
| Bash | `npm test`, `pytest` | Tests don't modify state |
| Bash | `npm run lint`, `eslint` | Linting is read-only |
| Bash | Type checking (`tsc --noEmit`) | No output files |

### 2. IRREVERSIBLE (Supervised - Batch Staging)

These actions modify state but are common development operations.

| Tool | Action Pattern | Why Supervised |
|------|----------------|----------------|
| Edit | Any file edit | Changes code (git can revert) |
| Write | Any file write | Creates/overwrites files |
| NotebookEdit | Jupyter changes | Modifies notebooks |
| Bash | `git add` | Stages changes |
| Bash | `git commit` | Creates commits (can be undone) |
| Bash | `mkdir`, `touch` | Creates filesystem structures |
| Bash | `npm install` | Modifies node_modules |
| Bash | `pip install` | Modifies environment |

### 3. BLOCKED (Always Confirm)

These actions have potentially destructive or external effects.

| Tool | Action Pattern | Why Blocked |
|------|----------------|-------------|
| Bash | `rm -rf /`, `rm -rf ~` | Catastrophic deletion |
| Bash | `git reset --hard` | Loses uncommitted work |
| Bash | `git push --force` | Rewrites remote history |
| Bash | `git clean -fdx` | Deletes untracked files |
| Bash | `git push` | External effect |
| Bash | `kubectl *` | Cluster changes |
| Bash | `terraform *` | Infrastructure changes |
| Bash | `docker push` | Registry changes |
| Bash | `npm publish` | Package publication |
| Bash | `aws *`, `gcloud *` | Cloud operations |
| Bash | `chmod -R 777` | Security risk |
| Bash | `dd if=*/dev/*` | Device operations |

## Trust Level Configuration

Users can override default trust levels per action type:

```yaml
# In .claude/state/yolo_config.yaml
yolo:
  enabled: false  # Master switch
  trust_levels:
    # Override defaults
    Edit: auto          # Trust all edits (risky but fast)
    "git commit": auto  # Trust commits
    "npm install": blocked  # Always confirm installs
  batch:
    max_staged: 10      # Prompt approval after N staged actions
    timeout_minutes: 5  # Prompt approval after N minutes
```

## Classification Logic

```python
def classify_action(tool_name: str, tool_input: dict) -> str:
    """
    Returns: 'auto' | 'supervised' | 'blocked'
    """
    # Check user overrides first
    override = get_user_override(tool_name, tool_input)
    if override:
        return override

    # Hard-blocked patterns (never auto)
    if is_hard_blocked(tool_name, tool_input):
        return 'blocked'

    # Tool-level defaults
    if tool_name in ['Read', 'Glob', 'Grep', 'LSP']:
        return 'auto'

    if tool_name in ['Edit', 'Write', 'NotebookEdit']:
        return 'supervised'

    # Bash requires pattern matching
    if tool_name == 'Bash':
        return classify_bash_command(tool_input.get('command', ''))

    # Default to supervised for unknown tools
    return 'supervised'
```

## Batch Staging UX

When actions are staged (supervised in YOLO mode):

```
════════════════════════════════════════════════════════════
YOLO MODE: 3 actions staged for approval
════════════════════════════════════════════════════════════

[1] Edit src/utils.py:42 - Add error handling
[2] Edit src/utils.py:58 - Update return type
[3] Write tests/test_utils.py - New test file

Press [Enter] to approve all, [1-3] to review specific, [x] to cancel
════════════════════════════════════════════════════════════
```

## Integration Points

1. **pre_tool.py** - Classifies action, either approves/stages/blocks
2. **yolo_state.json** - Tracks staged actions awaiting approval
3. **edge-yolo.md** - Command to toggle mode, view staged, configure
4. **session_start.py** - Shows YOLO status on session init
5. **edge.md** - Orchestrator suggests YOLO mode when appropriate

## Safety Invariants

1. **Blocked actions never auto-execute** - Regardless of config
2. **Logging always happens** - YOLO mode doesn't skip proof collection
3. **Plan requirement remains** - YOLO skips confirmations, not planning
4. **Batch has limits** - Staged actions prompt after threshold
5. **Easy escape** - User can always interrupt or disable YOLO mode
