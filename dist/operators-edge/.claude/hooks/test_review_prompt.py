#!/usr/bin/env python3
"""Tests for review_prompt.py"""

import os
import sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from review_prompt import (
    build_review_prompt, parse_review_response,
    validate_review_response, get_empty_diff_message,
    _fallback_parse
)
from review_context import ReviewContext


def test_build_review_prompt_basic():
    """Test basic prompt generation."""
    ctx = ReviewContext(
        diff="+ new_line = True",
        files_changed=["test.py"],
        step_intent="Add feature",
        is_empty=False
    )
    prompt = build_review_prompt(ctx)

    # Check key sections exist
    assert "senior code reviewer" in prompt
    assert "FIND ISSUES" in prompt
    assert "Security" in prompt
    assert "Correctness" in prompt
    assert "YAML" in prompt


def test_build_review_prompt_with_constraints():
    """Test prompt includes constraints."""
    ctx = ReviewContext(
        diff="+ code",
        is_empty=False,
        constraints=["No breaking changes", "Must have tests"]
    )
    prompt = build_review_prompt(ctx)

    assert "No breaking changes" in prompt
    assert "Must have tests" in prompt


def test_build_review_prompt_with_risks():
    """Test prompt includes risks."""
    ctx = ReviewContext(
        diff="+ code",
        is_empty=False,
        risks=[{"risk": "May cause data loss", "mitigation": "backup first"}]
    )
    prompt = build_review_prompt(ctx)

    assert "May cause data loss" in prompt


def test_get_empty_diff_message():
    """Test empty diff message."""
    msg = get_empty_diff_message()
    assert "NO CHANGES TO REVIEW" in msg
    assert "/edge-review" in msg


def test_parse_review_response_yaml_block():
    """Test parsing YAML from code block."""
    response = '''
Here is my review:

```yaml
findings:
  - severity: critical
    category: security
    issue: SQL injection vulnerability
    file: db.py
    line: 42

summary:
  verdict: request_changes
  confidence: high
  key_concerns: Security issue found
```
'''
    data = parse_review_response(response)

    assert "findings" in data
    assert len(data["findings"]) == 1
    assert data["findings"][0]["severity"] == "critical"
    assert data["summary"]["verdict"] == "request_changes"


def test_parse_review_response_bare_yaml():
    """Test parsing bare YAML without code block."""
    response = '''findings:
  - severity: minor
    category: style
    issue: Long function name
summary:
  verdict: approve
  confidence: high
  key_concerns: Minor style issues only
'''
    data = parse_review_response(response)

    assert "findings" in data
    assert data["summary"]["verdict"] == "approve"


def test_parse_review_response_fallback():
    """Test fallback parsing for malformed response."""
    response = "This is not valid YAML at all. Just some text."
    data = parse_review_response(response)

    assert "_parse_error" in data
    assert len(data["findings"]) >= 1
    assert "non-standard" in data["findings"][0]["issue"].lower()


def test_validate_review_response_valid():
    """Test validation of valid response."""
    data = {
        "findings": [
            {
                "severity": "minor",
                "category": "style",
                "issue": "Could use better names"
            }
        ],
        "summary": {
            "verdict": "approve",
            "confidence": "high",
            "key_concerns": "Minor issues"
        }
    }
    is_valid, errors = validate_review_response(data)

    assert is_valid
    assert len(errors) == 0


def test_validate_review_response_no_findings():
    """Test validation catches missing findings."""
    data = {
        "findings": [],
        "summary": {"verdict": "approve"}
    }
    is_valid, errors = validate_review_response(data)

    assert not is_valid
    assert any("no findings" in e.lower() for e in errors)


def test_validate_review_response_invalid_severity():
    """Test validation catches invalid severity."""
    data = {
        "findings": [
            {"severity": "blocker", "category": "bug", "issue": "test"}
        ],
        "summary": {"verdict": "approve"}
    }
    is_valid, errors = validate_review_response(data)

    assert not is_valid
    assert any("severity" in e.lower() for e in errors)


def test_validate_review_response_invalid_category():
    """Test validation catches invalid category."""
    data = {
        "findings": [
            {"severity": "minor", "category": "typo", "issue": "test"}
        ],
        "summary": {"verdict": "approve"}
    }
    is_valid, errors = validate_review_response(data)

    assert not is_valid
    assert any("category" in e.lower() for e in errors)


def test_validate_review_response_missing_issue():
    """Test validation catches missing issue text."""
    data = {
        "findings": [
            {"severity": "minor", "category": "style", "issue": ""}
        ],
        "summary": {"verdict": "approve"}
    }
    is_valid, errors = validate_review_response(data)

    assert not is_valid
    assert any("issue" in e.lower() for e in errors)


def test_validate_review_response_invalid_verdict():
    """Test validation catches invalid verdict."""
    data = {
        "findings": [
            {"severity": "minor", "category": "style", "issue": "test"}
        ],
        "summary": {"verdict": "ship_it"}
    }
    is_valid, errors = validate_review_response(data)

    assert not is_valid
    assert any("verdict" in e.lower() for e in errors)


def test_validate_review_response_missing_summary():
    """Test validation catches missing summary."""
    data = {
        "findings": [
            {"severity": "minor", "category": "style", "issue": "test"}
        ]
    }
    is_valid, errors = validate_review_response(data)

    assert not is_valid
    assert any("summary" in e.lower() for e in errors)


def test_fallback_parse():
    """Test fallback parsing directly."""
    response = "Some random text that isn't YAML"
    data = _fallback_parse(response)

    assert data["_parse_error"] == True
    assert data["summary"]["verdict"] == "needs_discussion"
    assert len(data["findings"]) >= 1


if __name__ == "__main__":
    # Run tests manually
    test_funcs = [
        test_build_review_prompt_basic,
        test_build_review_prompt_with_constraints,
        test_build_review_prompt_with_risks,
        test_get_empty_diff_message,
        test_parse_review_response_yaml_block,
        test_parse_review_response_bare_yaml,
        test_parse_review_response_fallback,
        test_validate_review_response_valid,
        test_validate_review_response_no_findings,
        test_validate_review_response_invalid_severity,
        test_validate_review_response_invalid_category,
        test_validate_review_response_missing_issue,
        test_validate_review_response_invalid_verdict,
        test_validate_review_response_missing_summary,
        test_fallback_parse,
    ]

    passed = 0
    failed = 0
    for test in test_funcs:
        try:
            test()
            print(f"✓ {test.__name__}")
            passed += 1
        except Exception as e:
            print(f"✗ {test.__name__}: {e}")
            failed += 1

    print(f"\n{passed} passed, {failed} failed")
