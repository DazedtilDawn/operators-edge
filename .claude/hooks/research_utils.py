#!/usr/bin/env python3
"""
Operator's Edge - Research Utilities
Detect unknowns, generate prompts for external deep research tools.
"""
import re
from datetime import datetime
from pathlib import Path

from state_utils import get_memory_items
from archive_utils import log_to_archive
from edge_config import RESEARCH_INDICATORS


# =============================================================================
# RESEARCH KEYWORDS FOR CODEBASE SCANNING
# =============================================================================

RESEARCH_TODO_KEYWORDS = [
    "research",
    "unclear",
    "investigate",
    "why",
    "understand",
    "figure out",
    "look into",
    "need to know",
    "not sure",
    "question",
    "unknown",
]

ALTERNATIVE_PATTERNS = [
    r"#\s*(?:Alternative|OR|Could also|Option \d|Instead):",
    r"//\s*(?:Alternative|OR|Could also|Option \d|Instead):",
    r"#\s*(?:TODO|FIXME).*(?:or|alternative|option)",
]


# =============================================================================
# CODEBASE SCANNING FOR RESEARCH NEEDS
# =============================================================================

def scan_for_research_todos(root_path=None, max_files=100):
    """
    Scan codebase for TODOs/FIXMEs that indicate research needs.

    Only returns findings that contain research-related keywords like
    "research", "unclear", "investigate", "why", etc.

    Args:
        root_path: Directory to scan (defaults to cwd)
        max_files: Max files to scan (time-boxing)

    Returns:
        List of research needs in standard format
    """
    from scout_scanner import discover_files, TODO_PATTERNS
    from scout_config import SCANNABLE_EXTENSIONS

    if root_path is None:
        root_path = Path.cwd()
    else:
        root_path = Path(root_path)

    research_findings = []
    files = discover_files(root_path, max_files)

    for filepath in files:
        try:
            content = filepath.read_text(encoding='utf-8', errors='ignore')
            lines = content.split('\n')

            for line_num, line in enumerate(lines, 1):
                line_lower = line.lower()

                # Check if it's a TODO/FIXME line
                is_todo = any(re.search(p, line, re.IGNORECASE) for p in TODO_PATTERNS)
                if not is_todo:
                    continue

                # Check if it contains research keywords
                has_research_keyword = any(kw in line_lower for kw in RESEARCH_TODO_KEYWORDS)
                if not has_research_keyword:
                    continue

                # Extract the TODO message
                match = re.search(r'(TODO|FIXME|HACK|XXX)[:\s]*(.+)', line, re.IGNORECASE)
                message = match.group(2).strip() if match else line.strip()

                research_findings.append({
                    "topic": message[:100],
                    "priority": "optional",
                    "reason": f"TODO/FIXME with research keyword in {filepath.name}",
                    "blocking_step": None,
                    "context": f"{filepath}:{line_num}: {line.strip()[:80]}"
                })

        except Exception:
            pass  # Skip unreadable files

    return research_findings


def scan_for_alternatives(root_path=None, max_files=100):
    """
    Scan codebase for commented-out alternatives that might need research.

    Looks for patterns like:
    - "# Alternative: ..."
    - "# OR: ..."
    - "# Could also: ..."

    Args:
        root_path: Directory to scan
        max_files: Max files to scan

    Returns:
        List of research needs in standard format
    """
    from scout_scanner import discover_files

    if root_path is None:
        root_path = Path.cwd()
    else:
        root_path = Path(root_path)

    findings = []
    files = discover_files(root_path, max_files)

    for filepath in files:
        try:
            content = filepath.read_text(encoding='utf-8', errors='ignore')
            lines = content.split('\n')

            for line_num, line in enumerate(lines, 1):
                for pattern in ALTERNATIVE_PATTERNS:
                    if re.search(pattern, line, re.IGNORECASE):
                        # Extract the alternative description
                        match = re.search(r'(?:Alternative|OR|Could also|Option \d|Instead)[:\s]*(.+)',
                                          line, re.IGNORECASE)
                        message = match.group(1).strip() if match else line.strip()

                        findings.append({
                            "topic": f"Evaluate alternative: {message[:80]}",
                            "priority": "optional",
                            "reason": f"Commented alternative found in {filepath.name}",
                            "blocking_step": None,
                            "context": f"{filepath}:{line_num}: {line.strip()[:80]}"
                        })
                        break  # One finding per line

        except Exception:
            pass

    return findings


# =============================================================================
# RESEARCH ID GENERATION
# =============================================================================

def generate_research_id():
    """Generate a unique research ID."""
    return f"R{datetime.now().strftime('%Y%m%d%H%M%S')}"


# =============================================================================
# RESEARCH STATE ACCESS
# =============================================================================

def get_research_items(state):
    """Get research items from state."""
    if not state:
        return []
    return state.get('research', [])


def get_pending_research(state):
    """Get research items that are pending or in progress."""
    research = get_research_items(state)
    return [r for r in research if isinstance(r, dict)
            and r.get('status') in ['pending', 'in_progress']]


def get_blocking_research(state):
    """Get critical research items that block progress."""
    research = get_research_items(state)
    return [r for r in research if isinstance(r, dict)
            and r.get('priority') == 'critical'
            and r.get('status') in ['pending', 'in_progress']]


# =============================================================================
# RESEARCH NEED DETECTION - HELPERS
# =============================================================================

def _scan_objective_technologies(objective):
    """Scan objective for technology indicators."""
    needs = []
    objective_lower = objective.lower() if objective else ''

    for tech in RESEARCH_INDICATORS['technologies']:
        if tech.lower() in objective_lower:
            needs.append({
                "topic": f"Best practices for {tech}",
                "priority": "optional",
                "reason": f"Objective mentions '{tech}' - may need current best practices",
                "blocking_step": None,
                "context": f"The objective is: {objective}"
            })
    return needs


def _scan_objective_ambiguity(objective):
    """Scan objective for ambiguity signals."""
    objective_lower = objective.lower() if objective else ''

    for signal in RESEARCH_INDICATORS['ambiguity_signals']:
        if signal.lower() in objective_lower:
            return [{
                "topic": f"Clarify approach for: {objective[:50]}...",
                "priority": "critical",
                "reason": f"Objective contains ambiguity signal: '{signal}'",
                "blocking_step": 1,
                "context": "Need to resolve ambiguity before planning"
            }]
    return []


def _scan_open_questions(open_questions):
    """Convert open questions to research needs."""
    needs = []
    for q in open_questions:
        if isinstance(q, dict):
            needs.append({
                "topic": q.get('question', 'Unclear question'),
                "priority": "critical" if q.get('blocking') else "optional",
                "reason": "Explicit open question in state",
                "blocking_step": 1 if q.get('blocking') else None,
                "context": q.get('context', '')
            })
    return needs


def _scan_plan_step(step, step_num):
    """Scan a single plan step for research needs."""
    needs = []
    desc = step.get('description', '').lower()

    # Check for technology indicators
    for tech in RESEARCH_INDICATORS['technologies']:
        if tech.lower() in desc:
            needs.append({
                "topic": f"How to implement: {step.get('description', '')[:50]}",
                "priority": "optional",
                "reason": f"Step {step_num} involves '{tech}'",
                "blocking_step": step_num,
                "context": f"Step {step_num}: {step.get('description', '')}"
            })
            break

    # Check for research verbs
    for verb in RESEARCH_INDICATORS['research_verbs']:
        if desc.startswith(verb) or f" {verb} " in desc:
            needs.append({
                "topic": step.get('description', ''),
                "priority": "critical",
                "reason": f"Step explicitly calls for '{verb}'",
                "blocking_step": step_num,
                "context": "This step should be research before execution"
            })
            break

    return needs


def _scan_plan_steps(plan):
    """Scan all plan steps for research needs."""
    needs = []
    for i, step in enumerate(plan):
        if not isinstance(step, dict):
            continue
        if step.get('status') == 'completed':
            continue
        needs.extend(_scan_plan_step(step, i + 1))
    return needs


def _deduplicate_and_sort(needs):
    """Deduplicate by topic and sort by priority."""
    seen_topics = set()
    unique_needs = []

    for need in needs:
        topic_key = need['topic'].lower()[:50]
        if topic_key not in seen_topics:
            seen_topics.add(topic_key)
            unique_needs.append(need)

    unique_needs.sort(key=lambda x: (
        0 if x['priority'] == 'critical' else 1,
        x.get('blocking_step') or 999
    ))
    return unique_needs


# =============================================================================
# RESEARCH NEED DETECTION - MAIN
# =============================================================================

def scan_for_research_needs(state, codebase_context=None):
    """
    Scan objective, plan, and optional codebase context for research needs.

    Returns list of detected research needs with:
    - topic: What needs research
    - priority: critical | optional
    - reason: Why this was flagged
    - blocking_step: Which step this affects (if any)
    - context: Additional context for prompt generation
    """
    if not state:
        return []

    needs = []
    objective = state.get('objective', '')
    plan = state.get('plan', [])
    open_questions = state.get('open_questions', [])

    # Scan each source
    needs.extend(_scan_objective_technologies(objective))
    needs.extend(_scan_objective_ambiguity(objective))
    needs.extend(_scan_open_questions(open_questions))
    needs.extend(_scan_plan_steps(plan))

    # Scan codebase if context provided
    if codebase_context:
        needs.extend(scan_for_research_todos(codebase_context, max_files=50))
        needs.extend(scan_for_alternatives(codebase_context, max_files=50))

    return _deduplicate_and_sort(needs)


# =============================================================================
# PROMPT GENERATION
# =============================================================================

def generate_research_prompt(research_need, state, additional_context=None):
    """
    Generate a self-contained prompt for external deep research tools.

    The prompt should be copy-pasteable to Gemini Deep Research, Perplexity, etc.
    """
    objective = state.get('objective', 'No objective set')
    constraints = state.get('constraints', [])
    lessons = get_memory_items(state)

    topic = research_need.get('topic', 'Unknown topic')
    reason = research_need.get('reason', '')
    context = research_need.get('context', '')
    priority = research_need.get('priority', 'optional')
    blocking_step = research_need.get('blocking_step')

    # Build the prompt
    prompt_parts = []

    # Header
    prompt_parts.append(f"## Research Request: {topic}")
    prompt_parts.append("")

    # Project context
    prompt_parts.append("### Project Context")
    prompt_parts.append(f"**Objective:** {objective}")
    if constraints:
        prompt_parts.append(f"**Constraints:**")
        for c in constraints[:5]:  # Limit to 5 constraints
            if isinstance(c, str):
                prompt_parts.append(f"- {c}")
    prompt_parts.append("")

    # Why this research
    prompt_parts.append("### Why This Research Is Needed")
    prompt_parts.append(reason)
    if context:
        prompt_parts.append(f"\n**Additional context:** {context}")
    if blocking_step:
        prompt_parts.append(f"\n**This blocks:** Step {blocking_step} of the implementation plan")
    prompt_parts.append("")

    # What we already know
    if lessons:
        relevant_lessons = [l for l in lessons if isinstance(l, dict)][:3]
        if relevant_lessons:
            prompt_parts.append("### What We Already Know")
            for lesson in relevant_lessons:
                if isinstance(lesson, dict):
                    prompt_parts.append(f"- {lesson.get('lesson', lesson.get('trigger', 'Unknown'))}")
                elif isinstance(lesson, str):
                    prompt_parts.append(f"- {lesson}")
            prompt_parts.append("")

    # Specific questions
    prompt_parts.append("### Questions to Answer")
    prompt_parts.append(f"1. What is the recommended approach for: {topic}?")
    prompt_parts.append("2. What are the key trade-offs to consider?")
    prompt_parts.append("3. What are common pitfalls or mistakes to avoid?")
    prompt_parts.append("4. What would a minimal viable implementation look like?")
    if priority == 'critical':
        prompt_parts.append("5. What must be decided before proceeding?")
    prompt_parts.append("")

    # Output format
    prompt_parts.append("### Requested Output Format")
    prompt_parts.append("Please provide:")
    prompt_parts.append("1. **Recommendation**: Your suggested approach (1-2 sentences)")
    prompt_parts.append("2. **Reasoning**: Why this approach (2-3 bullet points)")
    prompt_parts.append("3. **Action Items**: Specific next steps to implement (3-5 bullets)")
    prompt_parts.append("4. **Warnings**: Things to watch out for (2-3 bullets)")
    if additional_context:
        prompt_parts.append(f"\n**Note:** {additional_context}")

    return "\n".join(prompt_parts)


# =============================================================================
# RESEARCH ITEM MANAGEMENT
# =============================================================================

def create_research_item(research_need, state):
    """
    Create a full research item with generated prompt.
    Returns the research item ready to add to state.
    """
    research_id = generate_research_id()
    prompt = generate_research_prompt(research_need, state)

    return {
        "id": research_id,
        "topic": research_need.get('topic', 'Unknown'),
        "priority": research_need.get('priority', 'optional'),
        "status": "pending",
        "blocking_step": research_need.get('blocking_step'),
        "context": research_need.get('context', ''),
        "reason": research_need.get('reason', ''),
        "prompt": prompt,
        "results": None,
        "action_items": [],
        "created": datetime.now().isoformat(),
        "completed": None
    }


def add_research_to_state(state, research_item):
    """Add a research item to state."""
    if 'research' not in state:
        state['research'] = []
    state['research'].append(research_item)
    return research_item


def update_research_status(state, research_id, new_status):
    """Update the status of a research item."""
    research = state.get('research', [])
    for r in research:
        if isinstance(r, dict) and r.get('id') == research_id:
            r['status'] = new_status
            if new_status == 'completed':
                r['completed'] = datetime.now().isoformat()
            return True
    return False


def add_research_results(state, research_id, results, action_items=None):
    """Add results to a research item and mark as completed."""
    research = state.get('research', [])
    for r in research:
        if isinstance(r, dict) and r.get('id') == research_id:
            r['results'] = results
            r['action_items'] = action_items or []
            r['status'] = 'completed'
            r['completed'] = datetime.now().isoformat()
            return True
    return False


def archive_completed_research(research_item):
    """Archive a completed research item."""
    log_to_archive("completed_research", {
        "research_id": research_item.get('id'),
        "topic": research_item.get('topic'),
        "priority": research_item.get('priority'),
        "blocking_step": research_item.get('blocking_step'),
        "results_summary": (research_item.get('results', '') or '')[:500],
        "action_items": research_item.get('action_items', [])
    })


# =============================================================================
# RESEARCH SUMMARY
# =============================================================================

def get_research_summary(state):
    """Get a summary of research state."""
    research = get_research_items(state)

    if not research:
        return {"total": 0, "pending": 0, "blocking": 0, "completed": 0}

    pending = len([r for r in research if r.get('status') == 'pending'])
    in_progress = len([r for r in research if r.get('status') == 'in_progress'])
    completed = len([r for r in research if r.get('status') == 'completed'])
    blocking = len(get_blocking_research(state))

    return {
        "total": len(research),
        "pending": pending,
        "in_progress": in_progress,
        "completed": completed,
        "blocking": blocking
    }
