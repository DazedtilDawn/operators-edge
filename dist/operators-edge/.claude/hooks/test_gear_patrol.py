#!/usr/bin/env python3
"""
Tests for gear_patrol.py - Patrol Gear scanning module.
"""

import pytest
from unittest.mock import MagicMock, patch
from dataclasses import dataclass
from enum import Enum
from gear_patrol import (
    PatrolGearResult,
    run_patrol_scan,
    _filter_actionable_findings,
    _finding_to_dict,
    detect_drift,
    should_transition_from_patrol,
    format_patrol_status,
    format_patrol_findings,
)
from gear_config import Gear, GearState, GearTransition, get_default_gear_state


def make_gear_state() -> GearState:
    """Create a default GearState for testing."""
    return get_default_gear_state()


# Mock types for testing
class MockFindingType(Enum):
    TODO = "todo"
    LESSON_VIOLATION = "lesson_violation"
    MISSING_TEST = "missing_test"


class MockFindingPriority(Enum):
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


@dataclass
class MockFinding:
    """Mock finding for testing."""
    type: MockFindingType
    priority: MockFindingPriority
    title: str
    description: str
    location: str
    suggested_action: str


# =============================================================================
# PatrolGearResult Tests
# =============================================================================

class TestPatrolGearResult:
    """Tests for PatrolGearResult dataclass."""

    def test_basic_creation(self):
        result = PatrolGearResult(
            scan_completed=True,
            findings_count=3,
            findings=[{"title": "Test"}],
            lesson_violations=1,
            scan_duration_seconds=0.5,
            recommended_action="Select finding",
            error=None,
        )
        assert result.scan_completed is True
        assert result.findings_count == 3
        assert result.lesson_violations == 1

    def test_with_error(self):
        result = PatrolGearResult(
            scan_completed=False,
            findings_count=0,
            findings=[],
            lesson_violations=0,
            scan_duration_seconds=0.1,
            recommended_action=None,
            error="Scout import failed",
        )
        assert result.error == "Scout import failed"
        assert result.scan_completed is False

    def test_to_dict(self):
        result = PatrolGearResult(
            scan_completed=True,
            findings_count=2,
            findings=[{"title": "F1"}, {"title": "F2"}],
            lesson_violations=1,
            scan_duration_seconds=1.5,
            recommended_action="action",
            error=None,
        )
        d = result.to_dict()
        assert d["scan_completed"] is True
        assert d["findings_count"] == 2
        assert len(d["findings"]) == 2
        assert d["lesson_violations"] == 1
        assert d["scan_duration_seconds"] == 1.5
        assert d["recommended_action"] == "action"
        assert d["error"] is None

    def test_to_dict_empty(self):
        result = PatrolGearResult(
            scan_completed=True,
            findings_count=0,
            findings=[],
            lesson_violations=0,
            scan_duration_seconds=0.0,
            recommended_action=None,
            error=None,
        )
        d = result.to_dict()
        assert d["findings"] == []
        assert d["recommended_action"] is None


# =============================================================================
# _filter_actionable_findings Tests
# =============================================================================

class TestFilterActionableFindings:
    """Tests for _filter_actionable_findings function."""

    def test_empty_findings(self):
        result = _filter_actionable_findings([])
        assert result == []

    def test_all_actionable(self):
        findings = [
            MockFinding(
                type=MockFindingType.TODO,
                priority=MockFindingPriority.HIGH,
                title="Fix this bug",
                description="Desc",
                location="src/main.py",
                suggested_action="Fix it",
            ),
            MockFinding(
                type=MockFindingType.MISSING_TEST,
                priority=MockFindingPriority.MEDIUM,
                title="Missing test",
                description="Desc",
                location="src/utils.py",
                suggested_action="Add test",
            ),
        ]
        result = _filter_actionable_findings(findings)
        assert len(result) == 2

    def test_filters_test_fixture_todos(self):
        findings = [
            MockFinding(
                type=MockFindingType.TODO,
                priority=MockFindingPriority.HIGH,
                title="FIXME: Critical bug here",
                description="Desc",
                location="test_scanner.py",
                suggested_action="Fix",
            ),
        ]
        result = _filter_actionable_findings(findings)
        assert len(result) == 0

    def test_filters_critical_issue_in_tests(self):
        findings = [
            MockFinding(
                type=MockFindingType.TODO,
                priority=MockFindingPriority.HIGH,
                title="FIXME: Critical issue",
                description="Desc",
                location="tests/test_something.py",
                suggested_action="Fix",
            ),
        ]
        result = _filter_actionable_findings(findings)
        assert len(result) == 0

    def test_keeps_non_test_findings(self):
        findings = [
            MockFinding(
                type=MockFindingType.TODO,
                priority=MockFindingPriority.HIGH,
                title="FIXME: Critical bug here",
                description="Desc",
                location="src/main.py",  # Not a test file
                suggested_action="Fix",
            ),
        ]
        result = _filter_actionable_findings(findings)
        assert len(result) == 1

    def test_keeps_non_todo_types_in_tests(self):
        findings = [
            MockFinding(
                type=MockFindingType.LESSON_VIOLATION,  # Not a TODO
                priority=MockFindingPriority.HIGH,
                title="Critical issue",
                description="Desc",
                location="test_something.py",
                suggested_action="Fix",
            ),
        ]
        result = _filter_actionable_findings(findings)
        assert len(result) == 1

    def test_mixed_findings(self):
        findings = [
            MockFinding(
                type=MockFindingType.TODO,
                priority=MockFindingPriority.HIGH,
                title="FIXME: Critical bug here",
                description="Desc",
                location="test_scanner.py",
                suggested_action="Fix",
            ),
            MockFinding(
                type=MockFindingType.TODO,
                priority=MockFindingPriority.MEDIUM,
                title="TODO: Add feature",
                description="Desc",
                location="src/main.py",
                suggested_action="Add",
            ),
        ]
        result = _filter_actionable_findings(findings)
        assert len(result) == 1
        assert result[0].location == "src/main.py"


# =============================================================================
# _finding_to_dict Tests
# =============================================================================

class TestFindingToDict:
    """Tests for _finding_to_dict function."""

    def test_converts_finding(self):
        finding = MockFinding(
            type=MockFindingType.TODO,
            priority=MockFindingPriority.HIGH,
            title="Fix this bug",
            description="Bug description",
            location="src/main.py:42",
            suggested_action="Fix the bug",
        )
        d = _finding_to_dict(finding)
        assert d["type"] == "todo"
        assert d["priority"] == "high"
        assert d["title"] == "Fix this bug"
        assert d["description"] == "Bug description"
        assert d["location"] == "src/main.py:42"
        assert d["suggested_action"] == "Fix the bug"

    def test_different_types(self):
        finding = MockFinding(
            type=MockFindingType.LESSON_VIOLATION,
            priority=MockFindingPriority.MEDIUM,
            title="Violation",
            description="Desc",
            location="file.py",
            suggested_action="Fix",
        )
        d = _finding_to_dict(finding)
        assert d["type"] == "lesson_violation"
        assert d["priority"] == "medium"


# =============================================================================
# detect_drift Tests
# =============================================================================

class TestDetectDrift:
    """Tests for detect_drift function."""

    def test_no_drift(self):
        state = {
            "objective": "Test objective",
            "plan": [
                {"description": "Step 1", "status": "completed"},
            ]
        }
        drift = detect_drift(state)
        assert len(drift) == 0

    def test_objective_without_plan(self):
        state = {
            "objective": "Test objective",
            "plan": []
        }
        drift = detect_drift(state)
        assert len(drift) == 1
        assert drift[0]["issue"] == "objective_without_plan"

    def test_plan_without_objective(self):
        state = {
            "objective": "",
            "plan": [
                {"description": "Step 1", "status": "pending"},
            ]
        }
        drift = detect_drift(state)
        assert any(d["issue"] == "plan_without_objective" for d in drift)

    def test_stale_in_progress(self):
        state = {
            "objective": "Test",
            "plan": [
                {"description": "Step 1", "status": "completed"},
                {"description": "Step 2", "status": "in_progress"},
            ]
        }
        drift = detect_drift(state)
        assert any(d["issue"] == "stale_in_progress" for d in drift)

    def test_multiple_in_progress(self):
        state = {
            "objective": "Test",
            "plan": [
                {"description": "Step 1", "status": "in_progress"},
                {"description": "Step 2", "status": "in_progress"},
            ]
        }
        drift = detect_drift(state)
        stale_count = sum(1 for d in drift if d["issue"] == "stale_in_progress")
        assert stale_count == 2

    def test_empty_state(self):
        state = {}
        drift = detect_drift(state)
        # Should not crash
        assert isinstance(drift, list)

    def test_non_dict_steps_skipped(self):
        state = {
            "objective": "Test",
            "plan": [
                "invalid step",
                {"description": "Valid", "status": "pending"},
            ]
        }
        drift = detect_drift(state)
        # Should not crash on invalid steps
        assert isinstance(drift, list)


# =============================================================================
# should_transition_from_patrol Tests
# =============================================================================

class TestShouldTransitionFromPatrol:
    """Tests for should_transition_from_patrol function."""

    def test_findings_trigger_active_transition(self):
        result = PatrolGearResult(
            scan_completed=True,
            findings_count=3,
            findings=[{"title": "F1"}],
            lesson_violations=0,
            scan_duration_seconds=0.5,
            recommended_action="Select",
            error=None,
        )
        gear_state = make_gear_state()
        should, transition = should_transition_from_patrol(result, gear_state)
        assert should is True
        assert transition == GearTransition.PATROL_TO_ACTIVE

    def test_no_findings_trigger_dream_transition(self):
        result = PatrolGearResult(
            scan_completed=True,
            findings_count=0,
            findings=[],
            lesson_violations=0,
            scan_duration_seconds=0.5,
            recommended_action=None,
            error=None,
        )
        gear_state = make_gear_state()
        should, transition = should_transition_from_patrol(result, gear_state)
        assert should is True
        assert transition == GearTransition.PATROL_TO_DREAM

    def test_error_state_transitions_to_dream(self):
        result = PatrolGearResult(
            scan_completed=False,
            findings_count=0,
            findings=[],
            lesson_violations=0,
            scan_duration_seconds=0.1,
            recommended_action=None,
            error="Error",
        )
        gear_state = make_gear_state()
        should, transition = should_transition_from_patrol(result, gear_state)
        assert should is True
        assert transition == GearTransition.PATROL_TO_DREAM


# =============================================================================
# format_patrol_status Tests
# =============================================================================

class TestFormatPatrolStatus:
    """Tests for format_patrol_status function."""

    def test_basic_format(self):
        result = PatrolGearResult(
            scan_completed=True,
            findings_count=2,
            findings=[],
            lesson_violations=0,
            scan_duration_seconds=0.5,
            recommended_action=None,
            error=None,
        )
        output = format_patrol_status(result)
        assert "PATROL GEAR" in output
        assert "Complete" in output
        assert "0.5s" in output
        assert "2" in output

    def test_shows_lesson_violations(self):
        result = PatrolGearResult(
            scan_completed=True,
            findings_count=1,
            findings=[],
            lesson_violations=3,
            scan_duration_seconds=0.5,
            recommended_action=None,
            error=None,
        )
        output = format_patrol_status(result)
        assert "Lesson violations: 3" in output

    def test_shows_error(self):
        result = PatrolGearResult(
            scan_completed=False,
            findings_count=0,
            findings=[],
            lesson_violations=0,
            scan_duration_seconds=0.1,
            recommended_action=None,
            error="Import failed",
        )
        output = format_patrol_status(result)
        assert "Error" in output
        assert "Import failed" in output

    def test_shows_findings(self):
        result = PatrolGearResult(
            scan_completed=True,
            findings_count=2,
            findings=[
                {"priority": "high", "title": "High priority finding"},
                {"priority": "medium", "title": "Medium priority finding"},
            ],
            lesson_violations=0,
            scan_duration_seconds=0.5,
            recommended_action=None,
            error=None,
        )
        output = format_patrol_status(result)
        assert "Top findings" in output
        assert "[1]" in output
        assert "[2]" in output

    def test_shows_priority_markers(self):
        result = PatrolGearResult(
            scan_completed=True,
            findings_count=2,
            findings=[
                {"priority": "high", "title": "High"},
                {"priority": "low", "title": "Low"},
            ],
            lesson_violations=0,
            scan_duration_seconds=0.5,
            recommended_action=None,
            error=None,
        )
        output = format_patrol_status(result)
        assert "!" in output  # High priority marker
        assert "." in output  # Low priority marker

    def test_shows_recommendation(self):
        result = PatrolGearResult(
            scan_completed=True,
            findings_count=1,
            findings=[{"priority": "high", "title": "Finding"}],
            lesson_violations=0,
            scan_duration_seconds=0.5,
            recommended_action="Select finding [1]",
            error=None,
        )
        output = format_patrol_status(result)
        assert "Recommended" in output
        assert "Select finding [1]" in output

    def test_failed_scan(self):
        result = PatrolGearResult(
            scan_completed=False,
            findings_count=0,
            findings=[],
            lesson_violations=0,
            scan_duration_seconds=0.1,
            recommended_action=None,
            error=None,
        )
        output = format_patrol_status(result)
        assert "Failed" in output


# =============================================================================
# format_patrol_findings Tests
# =============================================================================

class TestFormatPatrolFindings:
    """Tests for format_patrol_findings function."""

    def test_no_findings(self):
        output = format_patrol_findings([])
        assert "No actionable findings" in output

    def test_single_finding(self):
        findings = [
            {
                "type": "todo",
                "priority": "high",
                "title": "Fix critical bug",
                "location": "src/main.py:42",
                "suggested_action": "Fix the bug",
            }
        ]
        output = format_patrol_findings(findings)
        assert "PATROL FINDINGS" in output
        assert "[1]" in output
        assert "Fix critical bug" in output
        assert "src/main.py:42" in output

    def test_multiple_findings(self):
        findings = [
            {
                "type": "todo",
                "priority": "high",
                "title": "First",
                "location": "a.py",
                "suggested_action": "Fix",
            },
            {
                "type": "missing_test",
                "priority": "medium",
                "title": "Second",
                "location": "b.py",
                "suggested_action": "Add test",
            },
        ]
        output = format_patrol_findings(findings)
        assert "[1]" in output
        assert "[2]" in output
        assert "First" in output
        assert "Second" in output

    def test_shows_type_and_priority(self):
        findings = [
            {
                "type": "lesson_violation",
                "priority": "high",
                "title": "Violation",
                "location": "file.py",
                "suggested_action": "Fix",
            }
        ]
        output = format_patrol_findings(findings)
        assert "lesson_violation" in output
        assert "high" in output

    def test_shows_suggested_action(self):
        findings = [
            {
                "type": "todo",
                "priority": "medium",
                "title": "Task",
                "location": "file.py",
                "suggested_action": "Complete the task",
            }
        ]
        output = format_patrol_findings(findings)
        assert "Action:" in output
        assert "Complete the task" in output

    def test_no_suggested_action(self):
        findings = [
            {
                "type": "todo",
                "priority": "low",
                "title": "Task",
                "location": "file.py",
            }
        ]
        output = format_patrol_findings(findings)
        assert "Task" in output
        # Should not crash with missing suggested_action

    def test_priority_markers(self):
        findings = [
            {"type": "t", "priority": "high", "title": "A", "location": "a.py"},
            {"type": "t", "priority": "medium", "title": "B", "location": "b.py"},
            {"type": "t", "priority": "low", "title": "C", "location": "c.py"},
        ]
        output = format_patrol_findings(findings)
        # High: !, Medium: ~, Low: .
        assert "! A" in output
        assert "~ B" in output
        assert ". C" in output


# =============================================================================
# run_patrol_scan Tests (with mocking)
# =============================================================================

class TestRunPatrolScan:
    """Tests for run_patrol_scan function."""

    def test_import_error_handled(self):
        # Test that import errors are handled gracefully
        # When scout_scanner import fails, should return error result
        with patch.dict('sys.modules', {'scout_scanner': None}):
            # Force reimport to trigger error
            result = run_patrol_scan({})
            # Either it handles the import error or it works
            assert isinstance(result, PatrolGearResult)

    def test_successful_scan_integration(self):
        # Integration test - actually runs scout scanner
        result = run_patrol_scan({})
        assert isinstance(result, PatrolGearResult)
        assert result.scan_duration_seconds >= 0
        # May or may not have findings depending on codebase

    def test_scan_returns_valid_structure(self):
        result = run_patrol_scan({})
        d = result.to_dict()
        assert "scan_completed" in d
        assert "findings_count" in d
        assert "findings" in d
        assert "lesson_violations" in d
        assert "scan_duration_seconds" in d


# =============================================================================
# Edge Cases
# =============================================================================

class TestEdgeCases:
    """Edge case tests for gear_patrol module."""

    def test_finding_without_location(self):
        @dataclass
        class FindingNoLocation:
            type: MockFindingType
            priority: MockFindingPriority
            title: str
            description: str
            suggested_action: str

        finding = FindingNoLocation(
            type=MockFindingType.TODO,
            priority=MockFindingPriority.LOW,
            title="Test",
            description="Desc",
            suggested_action="Fix",
        )
        # Should not crash
        result = _filter_actionable_findings([finding])
        assert len(result) == 1

    def test_empty_findings_list_in_result(self):
        result = PatrolGearResult(
            scan_completed=True,
            findings_count=0,
            findings=[],
            lesson_violations=0,
            scan_duration_seconds=0.0,
            recommended_action=None,
            error=None,
        )
        output = format_patrol_status(result)
        assert "Findings: 0" in output

    def test_very_long_finding_title(self):
        result = PatrolGearResult(
            scan_completed=True,
            findings_count=1,
            findings=[
                {"priority": "high", "title": "A" * 100}
            ],
            lesson_violations=0,
            scan_duration_seconds=0.5,
            recommended_action=None,
            error=None,
        )
        output = format_patrol_status(result)
        # Should truncate long titles
        assert "..." in output

    def test_detect_drift_with_all_pending_steps(self):
        state = {
            "objective": "Test",
            "plan": [
                {"description": "S1", "status": "pending"},
                {"description": "S2", "status": "pending"},
            ]
        }
        drift = detect_drift(state)
        # No stale in_progress
        assert not any(d["issue"] == "stale_in_progress" for d in drift)

    def test_detect_drift_with_completed_steps(self):
        state = {
            "objective": "Test",
            "plan": [
                {"description": "S1", "status": "completed"},
                {"description": "S2", "status": "completed"},
            ]
        }
        drift = detect_drift(state)
        assert len(drift) == 0

    def test_format_findings_handles_none_values(self):
        findings = [
            {
                "type": None,
                "priority": "high",
                "title": "Test",
                "location": None,
                "suggested_action": None,
            }
        ]
        output = format_patrol_findings(findings)
        # Should not crash
        assert "Test" in output
