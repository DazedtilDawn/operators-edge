#!/usr/bin/env python3
"""
Tests for lesson_schema.py - Lesson/memory item schema module.
"""

import pytest
from datetime import datetime, timedelta
from lesson_schema import (
    Lesson,
    validate_lesson,
    normalize_lesson,
)


# =============================================================================
# Lesson Dataclass Tests
# =============================================================================

class TestLessonBasic:
    """Basic tests for Lesson dataclass."""

    def test_create_minimal(self):
        lesson = Lesson(trigger="test", lesson="Test lesson")
        assert lesson.trigger == "test"
        assert lesson.lesson == "Test lesson"
        assert lesson.reinforced == 1

    def test_create_with_defaults(self):
        lesson = Lesson(trigger="test", lesson="Test")
        assert lesson.reinforced == 1
        assert lesson.last_used is None
        assert lesson.applies_to == []
        assert lesson.source is None
        assert lesson.audit_pattern is None
        assert lesson.audit_scope == []
        assert lesson.last_audit is None
        assert lesson.violations_found == 0

    def test_create_with_all_fields(self):
        lesson = Lesson(
            trigger="hooks",
            lesson="Always use hooks",
            reinforced=5,
            last_used="2025-01-01",
            applies_to=["python", "hooks"],
            source="session-123",
            audit_pattern=r"direct\s+call",
            audit_scope=["*.py"],
            last_audit="2025-01-01T00:00:00",
            violations_found=3,
        )
        assert lesson.trigger == "hooks"
        assert lesson.reinforced == 5
        assert len(lesson.applies_to) == 2
        assert lesson.violations_found == 3

    def test_reinforced_default(self):
        lesson = Lesson(trigger="t", lesson="l")
        assert lesson.reinforced == 1


class TestLessonToDict:
    """Tests for Lesson.to_dict() method."""

    def test_minimal_to_dict(self):
        lesson = Lesson(trigger="test", lesson="Test lesson")
        d = lesson.to_dict()
        assert d["trigger"] == "test"
        assert d["lesson"] == "Test lesson"
        assert d["reinforced"] == 1
        assert "last_used" not in d
        assert "applies_to" not in d

    def test_with_optional_fields(self):
        lesson = Lesson(
            trigger="test",
            lesson="Test",
            last_used="2025-01-01",
            applies_to=["context1"],
            source="test-session",
        )
        d = lesson.to_dict()
        assert d["last_used"] == "2025-01-01"
        assert d["applies_to"] == ["context1"]
        assert d["source"] == "test-session"

    def test_audit_fields_only_with_pattern(self):
        lesson = Lesson(
            trigger="test",
            lesson="Test",
            audit_pattern=r"pattern",
            audit_scope=["*.py"],
            last_audit="2025-01-01",
            violations_found=5,
        )
        d = lesson.to_dict()
        assert d["audit_pattern"] == r"pattern"
        assert d["audit_scope"] == ["*.py"]
        assert d["last_audit"] == "2025-01-01"
        assert d["violations_found"] == 5

    def test_audit_fields_omitted_without_pattern(self):
        lesson = Lesson(
            trigger="test",
            lesson="Test",
            audit_scope=["*.py"],  # Set but no audit_pattern
            last_audit="2025-01-01",
        )
        d = lesson.to_dict()
        assert "audit_pattern" not in d
        assert "audit_scope" not in d
        assert "last_audit" not in d

    def test_zero_violations_not_included(self):
        lesson = Lesson(
            trigger="test",
            lesson="Test",
            audit_pattern="pattern",
            violations_found=0,
        )
        d = lesson.to_dict()
        assert "violations_found" not in d

    def test_empty_lists_not_included(self):
        lesson = Lesson(
            trigger="test",
            lesson="Test",
            applies_to=[],
        )
        d = lesson.to_dict()
        assert "applies_to" not in d


class TestLessonFromDict:
    """Tests for Lesson.from_dict() class method."""

    def test_from_minimal_dict(self):
        data = {"trigger": "test", "lesson": "Test lesson"}
        lesson = Lesson.from_dict(data)
        assert lesson.trigger == "test"
        assert lesson.lesson == "Test lesson"
        assert lesson.reinforced == 1

    def test_from_full_dict(self):
        data = {
            "trigger": "hooks",
            "lesson": "Use hooks",
            "reinforced": 5,
            "last_used": "2025-01-01",
            "applies_to": ["python"],
            "source": "test",
            "audit_pattern": "pattern",
            "audit_scope": ["*.py"],
            "last_audit": "2025-01-01",
            "violations_found": 3,
        }
        lesson = Lesson.from_dict(data)
        assert lesson.trigger == "hooks"
        assert lesson.reinforced == 5
        assert lesson.violations_found == 3

    def test_from_string(self):
        lesson = Lesson.from_dict("Simple string lesson")
        assert lesson.trigger == "*"
        assert lesson.lesson == "Simple string lesson"
        assert lesson.reinforced == 1

    def test_missing_trigger_uses_default(self):
        data = {"lesson": "Just lesson"}
        lesson = Lesson.from_dict(data)
        assert lesson.trigger == "*"

    def test_missing_lesson_uses_str(self):
        data = {"trigger": "test"}
        lesson = Lesson.from_dict(data)
        assert lesson.trigger == "test"

    def test_defaults_for_optional_fields(self):
        data = {"trigger": "t", "lesson": "l"}
        lesson = Lesson.from_dict(data)
        assert lesson.applies_to == []
        assert lesson.audit_scope == []
        assert lesson.source is None


class TestLessonAuditCapability:
    """Tests for Lesson audit methods."""

    def test_has_audit_capability_true(self):
        lesson = Lesson(
            trigger="test",
            lesson="Test",
            audit_pattern=r"some\s+pattern",
        )
        assert lesson.has_audit_capability() is True

    def test_has_audit_capability_false(self):
        lesson = Lesson(trigger="test", lesson="Test")
        assert lesson.has_audit_capability() is False

    def test_has_audit_capability_empty_pattern(self):
        lesson = Lesson(
            trigger="test",
            lesson="Test",
            audit_pattern="",
        )
        assert lesson.has_audit_capability() is False

    def test_needs_audit_without_capability(self):
        lesson = Lesson(trigger="test", lesson="Test")
        assert lesson.needs_audit() is False

    def test_needs_audit_never_audited(self):
        lesson = Lesson(
            trigger="test",
            lesson="Test",
            audit_pattern="pattern",
        )
        assert lesson.needs_audit() is True

    def test_needs_audit_recently_audited(self):
        recent = datetime.now().isoformat()
        lesson = Lesson(
            trigger="test",
            lesson="Test",
            audit_pattern="pattern",
            last_audit=recent,
        )
        assert lesson.needs_audit(days_threshold=7) is False

    def test_needs_audit_old_audit(self):
        old = (datetime.now() - timedelta(days=10)).isoformat()
        lesson = Lesson(
            trigger="test",
            lesson="Test",
            audit_pattern="pattern",
            last_audit=old,
        )
        assert lesson.needs_audit(days_threshold=7) is True

    def test_needs_audit_custom_threshold(self):
        recent = (datetime.now() - timedelta(days=2)).isoformat()
        lesson = Lesson(
            trigger="test",
            lesson="Test",
            audit_pattern="pattern",
            last_audit=recent,
        )
        assert lesson.needs_audit(days_threshold=1) is True
        assert lesson.needs_audit(days_threshold=3) is False

    def test_needs_audit_invalid_date(self):
        lesson = Lesson(
            trigger="test",
            lesson="Test",
            audit_pattern="pattern",
            last_audit="invalid-date",
        )
        # Should return True when date is invalid
        assert lesson.needs_audit() is True


# =============================================================================
# validate_lesson Tests
# =============================================================================

class TestValidateLesson:
    """Tests for validate_lesson function."""

    def test_valid_minimal(self):
        data = {"trigger": "test", "lesson": "Test"}
        valid, error = validate_lesson(data)
        assert valid is True
        assert error == ""

    def test_valid_string_format(self):
        valid, error = validate_lesson("Simple string lesson")
        assert valid is True

    def test_invalid_type(self):
        valid, error = validate_lesson(123)
        assert valid is False
        assert "dict or string" in error

    def test_invalid_list(self):
        valid, error = validate_lesson([1, 2, 3])
        assert valid is False

    def test_missing_both_required(self):
        valid, error = validate_lesson({})
        assert valid is False
        assert "trigger" in error or "lesson" in error

    def test_only_trigger_valid(self):
        valid, error = validate_lesson({"trigger": "test"})
        assert valid is True

    def test_only_lesson_valid(self):
        valid, error = validate_lesson({"lesson": "test"})
        assert valid is True

    def test_invalid_trigger_type(self):
        valid, error = validate_lesson({"trigger": 123, "lesson": "test"})
        assert valid is False
        assert "trigger must be a string" in error

    def test_invalid_lesson_type(self):
        valid, error = validate_lesson({"trigger": "test", "lesson": 123})
        assert valid is False
        assert "lesson must be a string" in error

    def test_invalid_reinforced_type(self):
        valid, error = validate_lesson({
            "trigger": "test",
            "lesson": "test",
            "reinforced": "5"
        })
        assert valid is False
        assert "reinforced must be an integer" in error

    def test_valid_audit_pattern(self):
        valid, error = validate_lesson({
            "trigger": "test",
            "lesson": "test",
            "audit_pattern": r"valid\s+regex",
        })
        assert valid is True

    def test_invalid_audit_pattern_type(self):
        valid, error = validate_lesson({
            "trigger": "test",
            "lesson": "test",
            "audit_pattern": 123,
        })
        assert valid is False
        assert "audit_pattern must be a string" in error

    def test_invalid_audit_pattern_regex(self):
        valid, error = validate_lesson({
            "trigger": "test",
            "lesson": "test",
            "audit_pattern": "[invalid(regex",
        })
        assert valid is False
        assert "invalid regex" in error

    def test_invalid_audit_scope_type(self):
        valid, error = validate_lesson({
            "trigger": "test",
            "lesson": "test",
            "audit_scope": "*.py",  # Should be list
        })
        assert valid is False
        assert "audit_scope must be a list" in error

    def test_valid_audit_scope(self):
        valid, error = validate_lesson({
            "trigger": "test",
            "lesson": "test",
            "audit_scope": ["*.py", "*.js"],
        })
        assert valid is True

    def test_empty_audit_pattern_skipped(self):
        valid, error = validate_lesson({
            "trigger": "test",
            "lesson": "test",
            "audit_pattern": "",  # Empty string
        })
        assert valid is True


# =============================================================================
# normalize_lesson Tests
# =============================================================================

class TestNormalizeLesson:
    """Tests for normalize_lesson function."""

    def test_normalize_string(self):
        result = normalize_lesson("Simple lesson")
        assert result["trigger"] == "*"
        assert result["lesson"] == "Simple lesson"
        assert result["reinforced"] == 1

    def test_normalize_dict_minimal(self):
        result = normalize_lesson({"trigger": "test", "lesson": "Test"})
        assert result["trigger"] == "test"
        assert result["lesson"] == "Test"
        assert result["reinforced"] == 1

    def test_normalize_preserves_fields(self):
        data = {
            "trigger": "test",
            "lesson": "Test",
            "reinforced": 5,
            "last_used": "2025-01-01",
            "applies_to": ["python"],
        }
        result = normalize_lesson(data)
        assert result["reinforced"] == 5
        assert result["last_used"] == "2025-01-01"
        assert result["applies_to"] == ["python"]

    def test_normalize_non_dict(self):
        result = normalize_lesson(12345)
        assert result["trigger"] == "*"
        assert result["lesson"] == "12345"

    def test_normalize_adds_missing_trigger(self):
        result = normalize_lesson({"lesson": "Just lesson"})
        assert result["trigger"] == "*"

    def test_normalize_adds_missing_reinforced(self):
        result = normalize_lesson({"trigger": "t", "lesson": "l"})
        assert result["reinforced"] == 1

    def test_normalize_preserves_audit_fields(self):
        data = {
            "trigger": "test",
            "lesson": "Test",
            "audit_pattern": "pattern",
            "audit_scope": ["*.py"],
            "last_audit": "2025-01-01",
            "violations_found": 3,
        }
        result = normalize_lesson(data)
        assert result["audit_pattern"] == "pattern"
        assert result["audit_scope"] == ["*.py"]
        assert result["last_audit"] == "2025-01-01"
        assert result["violations_found"] == 3

    def test_normalize_skips_none_values(self):
        data = {
            "trigger": "test",
            "lesson": "Test",
            "last_used": None,
            "source": None,
        }
        result = normalize_lesson(data)
        assert "last_used" not in result
        assert "source" not in result

    def test_normalize_empty_dict(self):
        result = normalize_lesson({})
        assert result["trigger"] == "*"
        assert result["reinforced"] == 1


# =============================================================================
# Edge Cases
# =============================================================================

class TestEdgeCases:
    """Edge case tests for lesson_schema module."""

    def test_roundtrip_conversion(self):
        # Create -> to_dict -> from_dict should preserve data
        original = Lesson(
            trigger="hooks",
            lesson="Always use hooks",
            reinforced=3,
            last_used="2025-01-01",
            applies_to=["python"],
            source="test",
            audit_pattern="pattern",
            audit_scope=["*.py"],
            last_audit="2025-01-01T00:00:00",
            violations_found=2,
        )
        d = original.to_dict()
        restored = Lesson.from_dict(d)
        assert restored.trigger == original.trigger
        assert restored.lesson == original.lesson
        assert restored.reinforced == original.reinforced
        assert restored.audit_pattern == original.audit_pattern

    def test_unicode_in_lesson(self):
        lesson = Lesson(
            trigger="emoji test",
            lesson="Use emoji: 🎉🔥✅"
        )
        d = lesson.to_dict()
        assert "🎉" in d["lesson"]

    def test_multiline_lesson(self):
        lesson = Lesson(
            trigger="test",
            lesson="Line 1\nLine 2\nLine 3"
        )
        d = lesson.to_dict()
        assert "\n" in d["lesson"]

    def test_special_chars_in_audit_pattern(self):
        # Complex regex with special chars
        lesson = Lesson(
            trigger="test",
            lesson="Test",
            audit_pattern=r"foo\s+bar.*\d{3}[a-z]+",
        )
        assert lesson.has_audit_capability() is True
        d = lesson.to_dict()
        assert d["audit_pattern"] == r"foo\s+bar.*\d{3}[a-z]+"

    def test_empty_string_trigger(self):
        lesson = Lesson(trigger="", lesson="Test")
        d = lesson.to_dict()
        assert d["trigger"] == ""

    def test_very_long_lesson(self):
        long_text = "A" * 10000
        lesson = Lesson(trigger="test", lesson=long_text)
        assert len(lesson.lesson) == 10000
        d = lesson.to_dict()
        assert len(d["lesson"]) == 10000

    def test_negative_reinforced(self):
        lesson = Lesson(trigger="test", lesson="Test", reinforced=-1)
        d = lesson.to_dict()
        assert d["reinforced"] == -1

    def test_zero_reinforced(self):
        lesson = Lesson(trigger="test", lesson="Test", reinforced=0)
        d = lesson.to_dict()
        assert d["reinforced"] == 0

    def test_validate_complex_valid_lesson(self):
        valid, error = validate_lesson({
            "trigger": "complex trigger with spaces",
            "lesson": "A very detailed lesson\nwith multiple lines\nand special chars: @#$%",
            "reinforced": 100,
            "last_used": "2025-12-31T23:59:59",
            "applies_to": ["context1", "context2", "context3"],
            "source": "session-abc123",
            "audit_pattern": r"(foo|bar)\s+\d+",
            "audit_scope": ["*.py", "**/*.js", "src/**/*.ts"],
        })
        assert valid is True

    def test_needs_audit_boundary(self):
        # Exactly at the boundary
        exactly_7_days = (datetime.now() - timedelta(days=7)).isoformat()
        lesson = Lesson(
            trigger="test",
            lesson="Test",
            audit_pattern="pattern",
            last_audit=exactly_7_days,
        )
        assert lesson.needs_audit(days_threshold=7) is True
        assert lesson.needs_audit(days_threshold=8) is False

    def test_from_dict_preserves_all_optional_fields(self):
        data = {
            "trigger": "t",
            "lesson": "l",
            "reinforced": 5,
            "last_used": "date",
            "applies_to": ["a", "b"],
            "source": "src",
            "audit_pattern": "p",
            "audit_scope": ["*.py"],
            "last_audit": "audit_date",
            "violations_found": 10,
        }
        lesson = Lesson.from_dict(data)
        d = lesson.to_dict()
        # All fields should be preserved
        assert d["reinforced"] == 5
        assert d["last_used"] == "date"
        assert d["applies_to"] == ["a", "b"]
        assert d["source"] == "src"
        assert d["audit_pattern"] == "p"
        assert d["audit_scope"] == ["*.py"]
        assert d["last_audit"] == "audit_date"
        assert d["violations_found"] == 10
