#!/usr/bin/env python3
"""Tests for review_schema.py"""

import pytest
from datetime import datetime
from review_schema import (
    Severity, Category, Finding, Review,
    validate_finding, validate_review,
    create_finding, create_review, format_review_summary
)


# =============================================================================
# SEVERITY TESTS
# =============================================================================

class TestSeverity:
    def test_severity_values(self):
        assert Severity.CRITICAL.value == "critical"
        assert Severity.IMPORTANT.value == "important"
        assert Severity.MINOR.value == "minor"

    def test_severity_from_string(self):
        assert Severity("critical") == Severity.CRITICAL
        assert Severity("important") == Severity.IMPORTANT
        assert Severity("minor") == Severity.MINOR

    def test_invalid_severity(self):
        with pytest.raises(ValueError):
            Severity("blocker")


# =============================================================================
# CATEGORY TESTS
# =============================================================================

class TestCategory:
    def test_all_categories_exist(self):
        categories = [
            "security", "bug", "performance", "style",
            "architecture", "compatibility", "testing",
            "documentation", "other"
        ]
        for cat in categories:
            assert Category(cat).value == cat


# =============================================================================
# FINDING TESTS
# =============================================================================

class TestFinding:
    def test_create_minimal_finding(self):
        f = Finding(
            severity=Severity.MINOR,
            category=Category.STYLE,
            issue="Line too long"
        )
        assert f.issue == "Line too long"
        assert f.severity == Severity.MINOR
        assert f.file is None

    def test_create_full_finding(self):
        f = Finding(
            severity=Severity.CRITICAL,
            category=Category.SECURITY,
            issue="SQL injection vulnerability",
            file="src/db.py",
            line=42,
            function="execute_query",
            suggestion="Use parameterized queries",
            notes="User input is passed directly to query",
            code_snippet="cursor.execute(f'SELECT * FROM users WHERE id = {user_id}')"
        )
        assert f.severity == Severity.CRITICAL
        assert f.file == "src/db.py"
        assert f.line == 42

    def test_finding_to_dict(self):
        f = Finding(
            severity=Severity.IMPORTANT,
            category=Category.BUG,
            issue="Off-by-one error",
            file="src/utils.py",
            line=100
        )
        d = f.to_dict()
        assert d["severity"] == "important"
        assert d["category"] == "bug"
        assert d["issue"] == "Off-by-one error"
        assert d["file"] == "src/utils.py"
        assert d["line"] == 100
        assert "notes" not in d  # Optional field not included

    def test_finding_from_dict(self):
        d = {
            "severity": "critical",
            "category": "security",
            "issue": "Hardcoded password",
            "file": "config.py",
            "line": 10
        }
        f = Finding.from_dict(d)
        assert f.severity == Severity.CRITICAL
        assert f.category == Category.SECURITY
        assert f.issue == "Hardcoded password"

    def test_format_location_with_all(self):
        f = Finding(
            severity=Severity.MINOR,
            category=Category.STYLE,
            issue="test",
            file="src/utils.py",
            line=42,
            function="do_something"
        )
        assert f.format_location() == "src/utils.py:42 in do_something()"

    def test_format_location_file_only(self):
        f = Finding(
            severity=Severity.MINOR,
            category=Category.STYLE,
            issue="test",
            file="src/utils.py"
        )
        assert f.format_location() == "src/utils.py"

    def test_format_location_none(self):
        f = Finding(
            severity=Severity.MINOR,
            category=Category.STYLE,
            issue="test"
        )
        assert f.format_location() == "unknown location"


# =============================================================================
# REVIEW TESTS
# =============================================================================

class TestReview:
    def test_create_empty_review(self):
        r = Review(timestamp="2025-01-01T00:00:00")
        assert r.findings == []
        assert r.trigger == "manual"
        assert r.reviewer == "self"

    def test_review_with_findings(self):
        r = Review(
            timestamp="2025-01-01T00:00:00",
            trigger="step_complete",
            files_changed=3,
            lines_changed=150
        )
        r.add_finding(Finding(
            severity=Severity.CRITICAL,
            category=Category.SECURITY,
            issue="SQL injection"
        ))
        r.add_finding(Finding(
            severity=Severity.MINOR,
            category=Category.STYLE,
            issue="Long line"
        ))
        assert len(r.findings) == 2

    def test_review_summary(self):
        r = Review(timestamp="2025-01-01T00:00:00")
        r.add_finding(Finding(Severity.CRITICAL, Category.SECURITY, "issue1"))
        r.add_finding(Finding(Severity.CRITICAL, Category.BUG, "issue2"))
        r.add_finding(Finding(Severity.IMPORTANT, Category.STYLE, "issue3"))
        r.add_finding(Finding(Severity.MINOR, Category.STYLE, "issue4"))

        summary = r.get_summary()
        assert summary["critical"] == 2
        assert summary["important"] == 1
        assert summary["minor"] == 1
        assert summary["total"] == 4

    def test_has_critical(self):
        r = Review(timestamp="2025-01-01T00:00:00")
        assert not r.has_critical()

        r.add_finding(Finding(Severity.MINOR, Category.STYLE, "minor"))
        assert not r.has_critical()

        r.add_finding(Finding(Severity.CRITICAL, Category.SECURITY, "critical"))
        assert r.has_critical()

    def test_review_to_dict(self):
        r = Review(
            timestamp="2025-01-01T00:00:00",
            trigger="manual",
            files_changed=2,
            lines_changed=50,
            step_intent="Add logging"
        )
        r.add_finding(Finding(Severity.MINOR, Category.STYLE, "test"))

        d = r.to_dict()
        assert "review" in d
        assert d["review"]["timestamp"] == "2025-01-01T00:00:00"
        assert d["review"]["scope"]["files_changed"] == 2
        assert len(d["review"]["findings"]) == 1

    def test_review_from_dict(self):
        d = {
            "review": {
                "timestamp": "2025-01-01T00:00:00",
                "trigger": "pre_commit",
                "scope": {
                    "files_changed": 5,
                    "lines_changed": 200
                },
                "findings": [
                    {"severity": "minor", "category": "style", "issue": "test"}
                ]
            }
        }
        r = Review.from_dict(d)
        assert r.trigger == "pre_commit"
        assert r.files_changed == 5
        assert len(r.findings) == 1


# =============================================================================
# VALIDATION TESTS
# =============================================================================

class TestValidation:
    def test_validate_finding_valid(self):
        d = {
            "severity": "critical",
            "category": "security",
            "issue": "SQL injection"
        }
        is_valid, error = validate_finding(d)
        assert is_valid
        assert error == ""

    def test_validate_finding_missing_severity(self):
        d = {"category": "bug", "issue": "test"}
        is_valid, error = validate_finding(d)
        assert not is_valid
        assert "severity" in error

    def test_validate_finding_invalid_severity(self):
        d = {"severity": "blocker", "category": "bug", "issue": "test"}
        is_valid, error = validate_finding(d)
        assert not is_valid
        assert "severity" in error

    def test_validate_finding_invalid_category(self):
        d = {"severity": "minor", "category": "typo", "issue": "test"}
        is_valid, error = validate_finding(d)
        assert not is_valid
        assert "category" in error

    def test_validate_finding_empty_issue(self):
        d = {"severity": "minor", "category": "style", "issue": ""}
        is_valid, error = validate_finding(d)
        assert not is_valid
        assert "issue" in error

    def test_validate_finding_invalid_line(self):
        d = {"severity": "minor", "category": "style", "issue": "test", "line": -1}
        is_valid, error = validate_finding(d)
        assert not is_valid
        assert "line" in error

    def test_validate_review_valid(self):
        d = {
            "review": {
                "timestamp": "2025-01-01T00:00:00",
                "findings": [
                    {"severity": "minor", "category": "style", "issue": "test"}
                ]
            }
        }
        is_valid, error = validate_review(d)
        assert is_valid

    def test_validate_review_missing_timestamp(self):
        d = {"review": {"findings": []}}
        is_valid, error = validate_review(d)
        assert not is_valid
        assert "timestamp" in error

    def test_validate_review_invalid_finding(self):
        d = {
            "review": {
                "timestamp": "2025-01-01T00:00:00",
                "findings": [
                    {"severity": "invalid", "category": "style", "issue": "test"}
                ]
            }
        }
        is_valid, error = validate_review(d)
        assert not is_valid
        assert "Finding 0" in error


# =============================================================================
# HELPER TESTS
# =============================================================================

class TestHelpers:
    def test_create_finding_helper(self):
        f = create_finding(
            issue="Test issue",
            severity="critical",
            category="security",
            file="test.py"
        )
        assert f.severity == Severity.CRITICAL
        assert f.category == Category.SECURITY
        assert f.file == "test.py"

    def test_create_review_helper(self):
        r = create_review(
            trigger="step_complete",
            step_intent="Add feature",
            constraints=["No breaking changes"]
        )
        assert r.trigger == "step_complete"
        assert r.step_intent == "Add feature"
        assert "No breaking changes" in r.constraints
        assert r.timestamp  # Should have a timestamp

    def test_format_review_summary(self):
        r = create_review(trigger="manual")
        r.add_finding(create_finding(
            issue="SQL injection",
            severity="critical",
            category="security",
            file="db.py",
            line=42,
            suggestion="Use parameterized queries"
        ))
        r.add_finding(create_finding(
            issue="Long line",
            severity="minor",
            category="style",
            file="utils.py"
        ))

        output = format_review_summary(r)
        assert "REVIEW SUMMARY" in output
        assert "Critical: 1" in output
        assert "Minor: 1" in output
        assert "SQL injection" in output
        assert "parameterized queries" in output


# =============================================================================
# SERIALIZATION ROUND-TRIP TESTS
# =============================================================================

class TestRoundTrip:
    def test_finding_round_trip(self):
        original = Finding(
            severity=Severity.CRITICAL,
            category=Category.SECURITY,
            issue="Test issue",
            file="test.py",
            line=42,
            function="do_thing",
            suggestion="Fix it",
            notes="Important note"
        )
        d = original.to_dict()
        restored = Finding.from_dict(d)

        assert restored.severity == original.severity
        assert restored.category == original.category
        assert restored.issue == original.issue
        assert restored.file == original.file
        assert restored.line == original.line
        assert restored.function == original.function
        assert restored.suggestion == original.suggestion
        assert restored.notes == original.notes

    def test_review_round_trip(self):
        original = Review(
            timestamp="2025-01-01T12:00:00",
            trigger="pre_commit",
            reviewer="self",
            files_changed=5,
            lines_changed=150,
            step_intent="Add feature",
            constraints=["No breaking changes"]
        )
        original.add_finding(Finding(
            Severity.CRITICAL, Category.SECURITY, "issue1", "file1.py", 10
        ))
        original.add_finding(Finding(
            Severity.MINOR, Category.STYLE, "issue2", "file2.py"
        ))

        d = original.to_dict()
        restored = Review.from_dict(d)

        assert restored.timestamp == original.timestamp
        assert restored.trigger == original.trigger
        assert restored.files_changed == original.files_changed
        assert len(restored.findings) == 2
        assert restored.findings[0].severity == Severity.CRITICAL
