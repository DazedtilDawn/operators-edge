#!/usr/bin/env python3
"""
Operator's Edge - Review Prompt (v4.1)
The adversarial prompt that forces genuine code review, not rubber-stamping.

Design principles:
1. Adversarial framing - assume there ARE issues, task is to find them
2. Structured output - schema-validated findings
3. Forced specificity - no generic "looks good" allowed
4. Multi-perspective - security, correctness, style, architecture
"""

from typing import List
from review_context import ReviewContext, format_context_for_prompt


# =============================================================================
# REVIEW PROMPT TEMPLATE
# =============================================================================

REVIEW_PROMPT = '''You are a senior code reviewer performing a critical security and quality audit.

## YOUR ROLE

You are NOT here to approve code. You are here to FIND ISSUES. Your reputation depends on catching problems before they ship. If you say "looks good" and a bug ships, that's your failure.

## CONTEXT

{context}

## YOUR TASK

Analyze the diff above and produce a structured code review. You MUST find at least ONE issue - even in good code, there's always something to improve or question.

### Review Checklist

Go through EACH of these systematically:

**Security (look hard)**
- [ ] SQL injection, XSS, command injection
- [ ] Hardcoded secrets, API keys, credentials
- [ ] Insecure randomness, weak crypto
- [ ] Path traversal, file inclusion
- [ ] Race conditions, TOCTOU

**Correctness (be skeptical)**
- [ ] Edge cases: null, empty, zero, negative
- [ ] Off-by-one errors, boundary conditions
- [ ] Error handling: what if this fails?
- [ ] Type mismatches, implicit conversions
- [ ] Logic errors, inverted conditions

**Constraints Violated?**
{constraints_section}

**Known Risks Materialized?**
{risks_section}

**Architecture (think about tomorrow)**
- [ ] Breaking changes to public interfaces
- [ ] Coupling: does this create tight dependencies?
- [ ] Testability: can this be unit tested?
- [ ] Performance: O(n²)? unbounded loops?

**Style (consistency matters)**
- [ ] Naming: is it clear what things do?
- [ ] Complexity: can this be simpler?
- [ ] Documentation: will someone understand this in 6 months?

## OUTPUT FORMAT

Produce your findings as a YAML block. This is the ONLY acceptable output format:

```yaml
findings:
  - severity: critical|important|minor
    category: security|bug|performance|style|architecture|compatibility|testing|documentation|other
    issue: "Brief description of the problem"
    file: "path/to/file.py"  # optional
    line: 42  # optional
    suggestion: "How to fix it"  # optional
    notes: "Additional context"  # optional

  - severity: minor
    category: style
    issue: "At minimum, one finding required"

summary:
  verdict: "approve|request_changes|needs_discussion"
  confidence: "high|medium|low"
  key_concerns: "One sentence summary of top issues"
```

## RULES

1. You MUST produce at least ONE finding. Zero findings = review failure.
2. If the diff is genuinely excellent, find style or documentation improvements.
3. Be specific: "line 42 in auth.py" not "somewhere in the code"
4. Provide actionable suggestions, not just criticism.
5. Severity guide:
   - **critical**: Security flaw, data loss, crash. Must fix before merge.
   - **important**: Bug likely, bad pattern, will cause problems. Should fix.
   - **minor**: Style, nitpick, could be better. Optional.

## BEGIN REVIEW

Analyze the diff. Think step by step. Output ONLY the YAML block.
'''


# =============================================================================
# PROMPT BUILDER
# =============================================================================

def build_review_prompt(ctx: ReviewContext) -> str:
    """
    Build the complete review prompt from context.

    Args:
        ctx: ReviewContext with all gathered information

    Returns:
        Complete prompt string ready for LLM
    """
    # Format context
    context_str = format_context_for_prompt(ctx)

    # Format constraints section
    if ctx.constraints:
        constraints_section = "\n".join(f"- [ ] {c}" for c in ctx.constraints)
    else:
        constraints_section = "(No constraints specified)"

    # Format risks section
    if ctx.risks:
        risks_section = "\n".join(
            f"- [ ] {r.get('risk', str(r))}"
            for r in ctx.risks
        )
    else:
        risks_section = "(No known risks)"

    # Build final prompt
    return REVIEW_PROMPT.format(
        context=context_str,
        constraints_section=constraints_section,
        risks_section=risks_section,
    )


def get_empty_diff_message() -> str:
    """Return message when there's nothing to review."""
    return """
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
"""


# =============================================================================
# RESPONSE PARSING
# =============================================================================

def parse_review_response(response: str) -> dict:
    """
    Parse the LLM's YAML response into a structured dict.

    Handles:
    - YAML block extraction from markdown code blocks
    - Graceful fallback for malformed responses

    Args:
        response: Raw LLM response

    Returns:
        Parsed dict with 'findings' and 'summary'
    """
    import re

    # Try to extract YAML from code block
    yaml_pattern = r'```(?:yaml)?\s*([\s\S]*?)```'
    match = re.search(yaml_pattern, response)

    if match:
        yaml_content = match.group(1).strip()
    else:
        # Maybe the whole response is YAML
        yaml_content = response.strip()

    # Parse YAML - try pyyaml first, fallback to simple parser
    try:
        import yaml
        data = yaml.safe_load(yaml_content)

        if not isinstance(data, dict):
            return _fallback_parse(response)

        return data

    except ImportError:
        # pyyaml not available, use simple parser
        return _simple_yaml_parse(yaml_content, response)
    except Exception:
        return _fallback_parse(response)


def _simple_yaml_parse(yaml_content: str, original: str) -> dict:
    """
    Simple YAML-like parser for when pyyaml isn't available.
    Handles the specific schema we expect from reviews.
    """
    import re

    findings = []
    summary = {}

    # Parse findings section
    findings_match = re.search(r'findings:\s*([\s\S]*?)(?=summary:|$)', yaml_content)
    if findings_match:
        findings_text = findings_match.group(1)
        # Split by "- severity:" to get each finding
        finding_blocks = re.split(r'(?=- severity:)', findings_text)
        for block in finding_blocks:
            if '- severity:' not in block:
                continue
            finding = {}
            for line in block.split('\n'):
                line = line.strip().lstrip('- ')
                if ':' in line:
                    key, _, value = line.partition(':')
                    key = key.strip()
                    value = value.strip().strip('"\'')
                    if key and value:
                        finding[key] = value
            if finding:
                findings.append(finding)

    # Parse summary section
    summary_match = re.search(r'summary:\s*([\s\S]*?)$', yaml_content)
    if summary_match:
        summary_text = summary_match.group(1)
        for line in summary_text.split('\n'):
            line = line.strip()
            if ':' in line and not line.startswith('-'):
                key, _, value = line.partition(':')
                key = key.strip()
                value = value.strip().strip('"\'')
                if key and value:
                    summary[key] = value

    if findings or summary:
        return {"findings": findings, "summary": summary}
    else:
        return _fallback_parse(original)


def _fallback_parse(response: str) -> dict:
    """
    Fallback parsing when YAML fails.
    Extracts what we can from freeform text.
    """
    return {
        "findings": [
            {
                "severity": "minor",
                "category": "other",
                "issue": "Review produced non-standard output",
                "notes": response[:500] if response else "Empty response"
            }
        ],
        "summary": {
            "verdict": "needs_discussion",
            "confidence": "low",
            "key_concerns": "Could not parse review output"
        },
        "_parse_error": True
    }


def validate_review_response(data: dict) -> tuple[bool, List[str]]:
    """
    Validate parsed review response.

    Returns:
        (is_valid, list_of_errors)
    """
    errors = []

    # Check findings exist
    findings = data.get("findings", [])
    if not findings:
        errors.append("No findings provided (at least one required)")

    # Validate each finding
    valid_severities = {"critical", "important", "minor"}
    valid_categories = {
        "security", "bug", "performance", "style",
        "architecture", "compatibility", "testing", "documentation", "other"
    }

    for i, finding in enumerate(findings):
        if not isinstance(finding, dict):
            errors.append(f"Finding {i}: not a valid dict")
            continue

        if "severity" not in finding:
            errors.append(f"Finding {i}: missing severity")
        elif finding["severity"] not in valid_severities:
            errors.append(f"Finding {i}: invalid severity '{finding['severity']}'")

        if "category" not in finding:
            errors.append(f"Finding {i}: missing category")
        elif finding["category"] not in valid_categories:
            errors.append(f"Finding {i}: invalid category '{finding['category']}'")

        if "issue" not in finding or not finding.get("issue", "").strip():
            errors.append(f"Finding {i}: missing or empty issue")

    # Check summary
    summary = data.get("summary", {})
    if not summary:
        errors.append("Missing summary section")
    else:
        if "verdict" not in summary:
            errors.append("Summary missing verdict")
        elif summary["verdict"] not in {"approve", "request_changes", "needs_discussion"}:
            errors.append(f"Invalid verdict: {summary['verdict']}")

    return len(errors) == 0, errors


# =============================================================================
# CLI ENTRY POINT
# =============================================================================

if __name__ == "__main__":
    # Demo: show the prompt that would be generated
    from review_context import gather_review_context

    ctx = gather_review_context()

    if ctx.is_empty:
        print(get_empty_diff_message())
    else:
        prompt = build_review_prompt(ctx)
        print("=" * 60)
        print("GENERATED REVIEW PROMPT")
        print("=" * 60)
        print(f"Prompt length: {len(prompt)} chars")
        print("=" * 60)
        print(prompt[:3000])
        if len(prompt) > 3000:
            print(f"\n... [truncated, {len(prompt) - 3000} more chars]")
