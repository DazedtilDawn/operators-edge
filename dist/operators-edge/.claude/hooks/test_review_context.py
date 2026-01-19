#!/usr/bin/env python3
"""Tests for review_context.py"""

import os
import sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from review_context import (
    ReviewContext, get_diff_stats, get_current_step_intent,
    get_relevant_lessons, format_context_for_prompt
)


def test_review_context_defaults():
    """Test ReviewContext has sensible defaults."""
    ctx = ReviewContext()
    assert ctx.diff == ""
    assert ctx.is_empty == True
    assert ctx.files_changed == []
    assert ctx.constraints == []


def test_review_context_to_dict():
    """Test ReviewContext serialization."""
    ctx = ReviewContext(
        diff="+ added line",
        files_changed=["test.py"],
        step_intent="Add feature",
        constraints=["No breaking changes"]
    )
    d = ctx.to_dict()
    assert d["diff"]["content"] == "+ added line"
    assert d["intent"]["step"] == "Add feature"
    assert "No breaking changes" in d["constraints"]


def test_get_diff_stats():
    """Test diff line counting."""
    diff = """
diff --git a/test.py b/test.py
--- a/test.py
+++ b/test.py
@@ -1,3 +1,5 @@
 def foo():
-    old_line
+    new_line
+    another_new
+    third_new
"""
    added, removed = get_diff_stats(diff)
    assert added == 3
    assert removed == 1


def test_get_diff_stats_empty():
    """Test diff stats with empty diff."""
    added, removed = get_diff_stats("")
    assert added == 0
    assert removed == 0


def test_get_current_step_intent():
    """Test extracting step intent from state."""
    state = {
        "plan": [
            {"description": "Step 1", "status": "completed"},
            {"description": "Step 2 - in progress", "status": "in_progress"},
            {"description": "Step 3", "status": "pending"},
        ],
        "current_step": 2
    }
    intent, num = get_current_step_intent(state)
    assert intent == "Step 2 - in progress"
    assert num == 2


def test_get_current_step_intent_no_in_progress():
    """Test step intent when none in progress."""
    state = {
        "plan": [
            {"description": "Step 1", "status": "pending"},
            {"description": "Step 2", "status": "pending"},
        ],
        "current_step": 1
    }
    intent, num = get_current_step_intent(state)
    assert intent == "Step 1"
    assert num == 1


def test_get_current_step_intent_empty():
    """Test step intent with empty state."""
    intent, num = get_current_step_intent({})
    assert intent is None
    assert num == 0


def test_get_relevant_lessons():
    """Test finding relevant lessons for changed files."""
    state = {
        "memory": [
            {"trigger": "python", "lesson": "Use type hints", "reinforced": 3},
            {"trigger": "javascript", "lesson": "Use const", "reinforced": 2},
            {"trigger": "hooks", "lesson": "Test hooks", "reinforced": 1},
        ]
    }
    files = ["src/app.py", "tests/test_app.py"]
    lessons = get_relevant_lessons(state, files)

    # Should find python-related lessons
    triggers = [l["trigger"] for l in lessons]
    assert "python" in triggers


def test_get_relevant_lessons_empty():
    """Test relevant lessons with no memory."""
    lessons = get_relevant_lessons({}, ["test.py"])
    assert lessons == []


def test_format_context_for_prompt():
    """Test formatting context for prompt."""
    ctx = ReviewContext(
        diff="+ new line",
        diff_truncated=False,
        files_changed=["test.py"],
        lines_added=1,
        lines_removed=0,
        step_intent="Add tests",
        objective="Test the feature",
        step_number=2,
        constraints=["No breaking changes"],
        is_empty=False
    )

    output = format_context_for_prompt(ctx)

    # Check sections exist
    assert "CODE REVIEW CONTEXT" in output
    assert "SCOPE" in output
    assert "Files changed: 1" in output
    assert "+1 / -0" in output
    assert "INTENT" in output
    assert "Test the feature" in output
    assert "CONSTRAINTS" in output
    assert "No breaking changes" in output
    assert "FILES CHANGED" in output
    assert "test.py" in output
    assert "DIFF" in output
    assert "+ new line" in output


def test_format_context_with_risks():
    """Test formatting includes risks."""
    ctx = ReviewContext(
        diff="change",
        is_empty=False,
        risks=[{"risk": "May break API", "mitigation": "Add tests"}]
    )

    output = format_context_for_prompt(ctx)
    assert "KNOWN RISKS" in output
    assert "May break API" in output


def test_format_context_truncated_diff():
    """Test formatting shows truncation warning."""
    ctx = ReviewContext(
        diff="+ line",
        diff_truncated=True,
        is_empty=False
    )

    output = format_context_for_prompt(ctx)
    assert "truncated" in output.lower()


if __name__ == "__main__":
    # Run tests manually
    test_funcs = [
        test_review_context_defaults,
        test_review_context_to_dict,
        test_get_diff_stats,
        test_get_diff_stats_empty,
        test_get_current_step_intent,
        test_get_current_step_intent_no_in_progress,
        test_get_current_step_intent_empty,
        test_get_relevant_lessons,
        test_get_relevant_lessons_empty,
        test_format_context_for_prompt,
        test_format_context_with_risks,
        test_format_context_truncated_diff,
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
